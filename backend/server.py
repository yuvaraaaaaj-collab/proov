import asyncio
import time
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from strategies.strategy_manager import StrategyManager
from backend.market_data import MarketDataProvider
from backend.notifier import (
    load_alert_settings,
    save_alert_settings,
    dispatch_trade_alert,
    send_telegram,
    send_whatsapp_callmebot,
    format_telegram_message,
    format_plain_message
)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Live Trading Strategy Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# State & Providers
strategy_mgr = StrategyManager()
market_data_provider = MarketDataProvider()

account_config = {
    "account_model": "Goat Funded Trader ($1,000)",
    "balance": 1000.0,
    "risk_per_trade": 2.50,
    "max_daily_dd": 30.0,
    "max_floating_loss": 20.0,
    "consistency_limit": 15.0, # < 15%
    "active_symbol": "NAS100"
}

connected_clients = set()
latest_evaluation = {}

# Pydantic models for API
class StrategySelectRequest(BaseModel):
    strategy_id: str

class AccountConfigRequest(BaseModel):
    risk_per_trade: float
    active_symbol: str

@app.get("/api/strategies")
def get_strategies():
    return {
        "active_id": strategy_mgr.get_active_strategy_id(),
        "strategies": strategy_mgr.get_available_strategies()
    }

@app.post("/api/strategies/select")
def select_strategy(req: StrategySelectRequest):
    success = strategy_mgr.set_active_strategy(req.strategy_id)
    return {"success": success, "active_id": strategy_mgr.get_active_strategy_id()}

@app.get("/api/config")
def get_config():
    return account_config

@app.post("/api/config")
def update_config(req: AccountConfigRequest):
    account_config["risk_per_trade"] = req.risk_per_trade
    account_config["active_symbol"] = req.active_symbol
    return {"success": True, "config": account_config}

class PinVerifyRequest(BaseModel):
    pin: str

@app.post("/api/auth/verify")
def verify_pin(req: PinVerifyRequest):
    settings = load_alert_settings()
    correct_pin = str(settings.get("vip_pin", "7788")).strip()
    user_pin = str(req.pin).strip()
    return {"valid": user_pin == correct_pin}

@app.get("/api/alerts/settings")
def get_alert_settings():
    return load_alert_settings()

@app.post("/api/alerts/settings")
def update_alert_settings(req: Dict[str, Any]):
    current = load_alert_settings()
    current.update(req)
    success = save_alert_settings(current)
    return {"success": success, "settings": current}

@app.post("/api/alerts/test")
async def trigger_test_alert(req: Dict[str, Any] = None):
    settings = load_alert_settings()
    results = {}
    test_eval = {
        "decision": "Buy limit",
        "reason": "Test Signal: 15M SSL Swept -> 1M Bullish MSS + FVG entry setup.",
        "order_ticket": {
            "Order Type": "BUY LIMIT (TEST)",
            "Entry Price": 30250.0,
            "Stop Loss": 30230.0,
            "Take Profit": 30295.0,
            "R:R": "1:2.3",
            "Risk Amount": "$2.50 (Goat Safe)",
            "Projected Profit": "+$5.75"
        }
    }
    
    # 1. Test Telegram
    if settings.get("telegram_bot_token") and settings.get("telegram_chat_ids"):
        msg = format_telegram_message("NAS100", "SMC Master (TEST)", test_eval, 30250.0)
        tg_res = await asyncio.to_thread(send_telegram, settings["telegram_bot_token"], settings["telegram_chat_ids"], msg)
        results["telegram"] = tg_res
    else:
        results["telegram"] = "Telegram not configured or disabled"
        
    # 2. Test WhatsApp
    if settings.get("whatsapp_apikey") and settings.get("whatsapp_phones"):
        wa_msg = format_plain_message("NAS100", "SMC Master (TEST)", test_eval, 30250.0)
        wa_res = await asyncio.to_thread(send_whatsapp_callmebot, settings["whatsapp_phones"], settings["whatsapp_apikey"], wa_msg)
        results["whatsapp"] = wa_res
    else:
        results["whatsapp"] = "WhatsApp not configured or disabled"
        
    return {"status": "dispatched", "results": results}

@app.get("/api/status")
async def get_status():
    global latest_evaluation
    if not latest_evaluation:
        symbol = account_config.get("active_symbol", "NAS100")
        data = await asyncio.to_thread(market_data_provider.get_market_data, symbol)
        eval_result = strategy_mgr.evaluate_active(data, account_config)
        latest_evaluation = {
            "type": "MARKET_UPDATE",
            "timestamp": data.get("timestamp"),
            "symbol": symbol,
            "current_price": data.get("current_price"),
            "strategy_id": strategy_mgr.get_active_strategy_id(),
            "evaluation": eval_result,
            "is_alert": eval_result.get("decision") not in ["Wait / No trade", None],
            "account_config": account_config
        }
    return latest_evaluation

@app.get("/api/refresh")
@app.post("/api/refresh")
async def trigger_refresh(symbol: str = None, strategy_id: str = None):
    global latest_evaluation
    sym = symbol or account_config.get("active_symbol", "NAS100")
    if strategy_id:
        strategy_mgr.set_active_strategy(strategy_id)
    # Fetch fresh market data bypassing 30s cache
    data = await asyncio.to_thread(market_data_provider.get_market_data, sym, True)
    eval_result = strategy_mgr.evaluate_active(data, account_config)
    
    payload = {
        "type": "MARKET_UPDATE",
        "timestamp": data.get("timestamp"),
        "symbol": sym,
        "current_price": data.get("current_price"),
        "strategy_id": strategy_mgr.get_active_strategy_id(),
        "evaluation": eval_result,
        "is_alert": eval_result.get("decision") not in ["Wait / No trade", None],
        "account_config": account_config
    }
    latest_evaluation = payload
    if connected_clients:
        msg_str = json.dumps(payload)
        for client in list(connected_clients):
            try:
                await client.send_text(msg_str)
            except Exception:
                pass
    return payload

@app.get("/api/price")
@app.get("/api/webhook")
async def get_price_update(price: float, symbol: str = "NAS100"):
    global latest_evaluation
    sym = "NAS100" if ("100" in symbol or "nas" in symbol.lower()) else "GOLD"
    market_data_provider.update_live_price(sym, price)
    mdata = market_data_provider.get_market_data(sym)
    mdata["current_price"] = price
    eval_result = strategy_mgr.evaluate_active(mdata, account_config)
    payload = {
        "type": "MARKET_UPDATE",
        "timestamp": time.time(),
        "symbol": sym,
        "current_price": price,
        "strategy_id": strategy_mgr.get_active_strategy_id(),
        "evaluation": eval_result,
        "is_alert": eval_result.get("decision") not in ["Wait / No trade", None],
        "account_config": account_config
    }
    latest_evaluation = payload
    if connected_clients:
        msg_str = json.dumps(payload)
        for client in list(connected_clients):
            try:
                await client.send_text(msg_str)
            except Exception:
                pass
    return {"status": "success", "symbol": sym, "price": price}

@app.post("/api/webhook")
async def tradingview_webhook(req: Request):
    global latest_evaluation
    try:
        body_bytes = await req.body()
        body_str = body_bytes.decode("utf-8")
        data = {}
        try:
            data = json.loads(body_str)
        except Exception:
            # Parse key-values or raw number from string
            import re
            p_match = re.search(r'([0-9]+\.?[0-9]*)', body_str)
            if p_match:
                data["price"] = float(p_match.group(1))
            if "gold" in body_str.lower() or "xau" in body_str.lower():
                data["symbol"] = "GOLD"
            else:
                data["symbol"] = "NAS100"

        symbol = data.get("symbol", "NAS100").upper()
        if "US100" in symbol or "NAS" in symbol or "NDX" in symbol:
            symbol = "NAS100"
        elif "GOLD" in symbol or "XAU" in symbol:
            symbol = "GOLD"

        price = float(data.get("price", 0.0))
        high = float(data.get("high")) if "high" in data else None
        low = float(data.get("low")) if "low" in data else None

        if price > 0:
            market_data_provider.update_live_price(symbol, price, high, low)
            mdata = market_data_provider.get_market_data(symbol)
            mdata["current_price"] = price
            eval_result = strategy_mgr.evaluate_active(mdata, account_config)
            payload = {
                "type": "MARKET_UPDATE",
                "timestamp": time.time(),
                "symbol": symbol,
                "current_price": price,
                "strategy_id": strategy_mgr.get_active_strategy_id(),
                "evaluation": eval_result,
                "is_alert": eval_result.get("decision") not in ["Wait / No trade", None],
                "account_config": account_config
            }
            latest_evaluation = payload
            if connected_clients:
                msg_str = json.dumps(payload)
                for client in list(connected_clients):
                    try:
                        await client.send_text(msg_str)
                    except Exception:
                        pass
            return {"status": "success", "symbol": symbol, "price": price}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    return {"status": "ignored"}

# Serve Web App Manifest & Service Worker
FRONTEND_DIR = BASE_DIR / "frontend"

@app.get("/manifest.json")
def get_manifest():
    return FileResponse(FRONTEND_DIR / "manifest.json", media_type="application/manifest+json")

@app.get("/sw.js")
def get_sw():
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")

# WebSocket for real-time live streaming to phone/desktop
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        # Send initial state immediately
        if not latest_evaluation:
            symbol = account_config.get("active_symbol", "NAS100")
            data = await asyncio.to_thread(market_data_provider.get_market_data, symbol)
            eval_result = strategy_mgr.evaluate_active(data, account_config)
            latest_evaluation = {
                "type": "MARKET_UPDATE",
                "timestamp": data.get("timestamp"),
                "symbol": symbol,
                "current_price": data.get("current_price"),
                "strategy_id": strategy_mgr.get_active_strategy_id(),
                "evaluation": eval_result,
                "is_alert": eval_result.get("decision") not in ["Wait / No trade", None],
                "account_config": account_config
            }
        await websocket.send_text(json.dumps(latest_evaluation))
        while True:
            # Keep connection alive & receive client messages (e.g. symbol switch)
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if "switch_symbol" in msg:
                    account_config["active_symbol"] = msg["switch_symbol"]
                if "switch_strategy" in msg:
                    strategy_mgr.set_active_strategy(msg["switch_strategy"])
                if "refresh" in msg:
                    sym = msg.get("symbol", account_config.get("active_symbol", "NAS100"))
                    if "strategy_id" in msg and msg["strategy_id"]:
                        strategy_mgr.set_active_strategy(msg["strategy_id"])
                    data = await asyncio.to_thread(market_data_provider.get_market_data, sym, True)
                    eval_result = strategy_mgr.evaluate_active(data, account_config)
                    payload = {
                        "type": "MARKET_UPDATE",
                        "timestamp": data.get("timestamp"),
                        "symbol": sym,
                        "current_price": data.get("current_price"),
                        "strategy_id": strategy_mgr.get_active_strategy_id(),
                        "evaluation": eval_result,
                        "is_alert": eval_result.get("decision") not in ["Wait / No trade", None],
                        "account_config": account_config
                    }
                    latest_evaluation = payload
                    await websocket.send_text(json.dumps(payload))
            except Exception:
                pass
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
    except Exception:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

# Background scanner loop running every second
async def market_scanner_loop():
    global latest_evaluation
    last_decision = "Wait / No trade"
    
    while True:
        try:
            symbol = account_config.get("active_symbol", "NAS100")
            # Fetch market data
            data = await asyncio.to_thread(market_data_provider.get_market_data, symbol)
            
            # Evaluate active strategy
            eval_result = strategy_mgr.evaluate_active(data, account_config)
            
            # Check for alert trigger
            current_decision = eval_result.get("decision", "Wait / No trade")
            is_new_alert = (current_decision != "Wait / No trade") and (current_decision != last_decision)
            last_decision = current_decision
            
            if is_new_alert:
                asyncio.create_task(dispatch_trade_alert(
                    symbol,
                    strategy_mgr.get_active_strategy_id(),
                    eval_result,
                    data.get("current_price", 0.0)
                ))
            
            payload = {
                "type": "MARKET_UPDATE",
                "timestamp": data.get("timestamp"),
                "symbol": symbol,
                "current_price": data.get("current_price"),
                "strategy_id": strategy_mgr.get_active_strategy_id(),
                "evaluation": eval_result,
                "is_alert": is_new_alert,
                "account_config": account_config
            }
            
            latest_evaluation = payload
            
            # Broadcast to all connected phone and desktop clients
            if connected_clients:
                msg_str = json.dumps(payload)
                disconnected = set()
                for client in connected_clients:
                    try:
                        await client.send_text(msg_str)
                    except Exception:
                        disconnected.add(client)
                connected_clients.difference_update(disconnected)
                
        except Exception as e:
            print(f"[Scanner Loop Error] {e}")
            
        await asyncio.sleep(1.5)

@app.on_event("startup")
async def startup_event():
    from backend.tv_feed import tv_feed
    asyncio.create_task(tv_feed.run())
    asyncio.create_task(market_scanner_loop())

# Mount frontend directory for static assets
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.server:app", host="0.0.0.0", port=port, reload=False)
