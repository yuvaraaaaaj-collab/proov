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
    async_send_telegram,
    async_send_whatsapp,
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
last_valid_tickets = {}

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
    
    sym = "NAS100"
    if req and "symbol" in req:
        sym = "GOLD" if "gold" in str(req["symbol"]).lower() else "NAS100"
    else:
        sym = account_config.get("active_symbol", "NAS100")
        
    is_gold = (sym == "GOLD")
    live_price = market_data_provider.get_live_price(sym)
    
    if is_gold:
        entry = round(live_price if live_price > 0 else 4306.50, 2)
        sl = round(entry - 6.50, 2)
        tp = round(entry + 15.00, 2)
    else:
        entry = round(live_price if live_price > 0 else 30650.0, 1)
        sl = round(entry - 25.0, 1)
        tp = round(entry + 60.0, 1)

    test_eval = {
        "strategy": "TraderPro VIP System",
        "decision": "Buy limit",
        "reason": f"Test VIP Alert: Verified real-time notification delivery pipeline for {sym}.",
        "order_ticket": {
            "Order Type": "BUY LIMIT (TEST)",
            "Instrument": sym,
            "Entry Price": entry,
            "Stop Loss": sl,
            "Take Profit": tp,
            "R:R": "1:2.3",
            "Risk Amount": "$2.50 (Goat Safe)",
            "Projected Profit": "+$5.75"
        }
    }
    
    # 1. Test Telegram (Instant Async)
    if settings.get("telegram_bot_token") and settings.get("telegram_chat_ids"):
        msg = format_telegram_message(sym, f"TraderPro VIP ({sym} Test)", test_eval, entry)
        tg_res = await async_send_telegram(settings["telegram_bot_token"], settings["telegram_chat_ids"], msg)
        results["telegram"] = tg_res
    else:
        results["telegram"] = "Telegram not configured or disabled"
        
    # 2. Test WhatsApp (Instant Async)
    if settings.get("whatsapp_apikey") and settings.get("whatsapp_phones"):
        wa_msg = format_plain_message(sym, f"TraderPro VIP ({sym} Test)", test_eval, entry)
        wa_res = await async_send_whatsapp(settings["whatsapp_phones"], settings["whatsapp_apikey"], wa_msg)
        results["whatsapp"] = wa_res
    else:
        results["whatsapp"] = "WhatsApp not configured or disabled"
        
    return {"status": "dispatched", "symbol": sym, "results": results}

@app.get("/api/status")
async def get_status():
    global latest_evaluation
    symbol = account_config.get("active_symbol", "NAS100")
    if not latest_evaluation:
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
            "last_valid_ticket": last_valid_tickets.get(symbol),
            "account_config": account_config
        }
    else:
        latest_evaluation["last_valid_ticket"] = last_valid_tickets.get(latest_evaluation.get("symbol", symbol))
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
        "last_valid_ticket": last_valid_tickets.get(sym),
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

@app.post("/api/alerts/dismiss")
def dismiss_alert(req: Dict[str, Any] = None):
    sym = (req or {}).get("symbol", account_config.get("active_symbol", "NAS100"))
    if sym in last_valid_tickets:
        del last_valid_tickets[sym]
    return {"status": "cleared", "symbol": sym}

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
                "last_valid_ticket": last_valid_tickets.get(symbol),
                "account_config": account_config
            }
        else:
            latest_evaluation["last_valid_ticket"] = last_valid_tickets.get(latest_evaluation.get("symbol", account_config.get("active_symbol", "NAS100")))
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
                        "last_valid_ticket": last_valid_tickets.get(sym),
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

# Background scanner loop running every 1.5 seconds (Multi-Strategy, Dual-Symbol Concurrent Engine)
async def market_scanner_loop():
    global latest_evaluation
    # Tracks last decision per (symbol, strategy_id)
    last_decision = {}
    symbols_to_scan = ["NAS100", "GOLD"]
    
    while True:
        try:
            active_sym = account_config.get("active_symbol", "NAS100")
            active_strat = strategy_mgr.get_active_strategy_id()
            
            for symbol in symbols_to_scan:
                # Fetch fresh market data
                data = await asyncio.to_thread(market_data_provider.get_market_data, symbol)
                current_price = data.get("current_price", 0.0)
                
                # Automatic cleanup of stale or price-invalidated tickets
                exist_t = last_valid_tickets.get(symbol)
                if exist_t:
                    t_age = time.time() - exist_t.get("timestamp", 0)
                    t_entry = float(exist_t.get("Entry Price") or exist_t.get("Entry") or 0)
                    t_sl = float(exist_t.get("Stop Loss") or 0)
                    t_tp = float(exist_t.get("Take Profit") or 0)
                    is_buy = "BUY" in str(exist_t.get("Order Type", "")).upper()
                    
                    is_stale = (t_age > 1500)
                    if current_price > 0 and t_sl > 0 and t_tp > 0:
                        if is_buy and (current_price <= t_sl or current_price >= t_tp):
                            is_stale = True
                        elif not is_buy and (current_price >= t_sl or current_price <= t_tp):
                            is_stale = True
                        max_dist = 40.0 if symbol == "GOLD" else 200.0
                        if abs(current_price - t_entry) > max_dist:
                            is_stale = True
                    if is_stale:
                        del last_valid_tickets[symbol]
                
                # Concurrently evaluate ALL registered strategies on this symbol!
                all_evals = strategy_mgr.evaluate_all(data, account_config)
                
                # Check for alert triggers across all strategies
                for strat_id, eval_result in all_evals.items():
                    current_decision = eval_result.get("decision", "Wait / No trade")
                    ticket = eval_result.get("order_ticket")
                    key = (symbol, strat_id)
                    prev_decision = last_decision.get(key, "Wait / No trade")
                    
                    # A TRUE actionable entry alert REQUIRES a non-empty order ticket with Entry, SL, and TP!
                    has_valid_ticket = (
                        isinstance(ticket, dict)
                        and bool(ticket.get("Entry Price") or ticket.get("Entry"))
                        and bool(ticket.get("Stop Loss"))
                        and bool(ticket.get("Take Profit"))
                        and str(ticket.get("Stop Loss")) != "---"
                    )
                    
                    # Persist valid ticket so it stays constant and does not disappear across updates
                    if has_valid_ticket and strat_id != "session_breakout":
                        last_valid_tickets[symbol] = {
                            **ticket,
                            "strategy": eval_result.get("strategy", strat_id),
                            "strategy_id": strat_id,
                            "symbol": symbol,
                            "timestamp": time.time()
                        }
                    
                    is_new_alert = (
                        current_decision not in ["Wait / No trade", None]
                        and has_valid_ticket
                        and (current_decision != prev_decision)
                    )
                    last_decision[key] = current_decision
                    
                    strat_name = eval_result.get("strategy", strat_id)
                    
                    # Whenever ANY strategy detects a valid entry on EITHER NAS100 or GOLD:
                    # Note: Notification push is explicitly disabled for session momentum breakout
                    if is_new_alert and strat_id != "session_breakout":
                        # 1. Dispatch background alerts: Telegram, WhatsApp, etc.
                        asyncio.create_task(dispatch_trade_alert(
                            symbol,
                            strat_name,
                            eval_result,
                            current_price
                        ))
                        
                        # 2. If this alert is NOT the exact symbol + strategy currently on screen, broadcast a CROSS_ALERT
                        if not (symbol == active_sym and strat_id == active_strat):
                            alert_payload = {
                                "type": "CROSS_ALERT",
                                "symbol": symbol,
                                "current_price": current_price,
                                "strategy_id": strat_id,
                                "strategy_name": strat_name,
                                "evaluation": eval_result,
                                "is_alert": True
                            }
                            if connected_clients:
                                msg_str = json.dumps(alert_payload)
                                for client in list(connected_clients):
                                    try:
                                        await client.send_text(msg_str)
                                    except Exception:
                                        pass
                
                # If this is the active symbol being viewed on screen, broadcast its active strategy update
                if symbol == active_sym:
                    active_eval = all_evals.get(active_strat, {})
                    active_ticket = active_eval.get("order_ticket")
                    is_active_alert = (
                        active_eval.get("decision") not in ["Wait / No trade", None]
                        and isinstance(active_ticket, dict)
                        and bool(active_ticket.get("Entry Price") or active_ticket.get("Entry"))
                        and active_strat != "session_breakout"
                    )
                    active_name = active_eval.get("strategy", active_strat)
                    
                    # Prepare multi-strategy radar summary for UI
                    all_radar = {
                        s_id: {
                            "name": ev.get("strategy", s_id),
                            "decision": ev.get("decision", "Wait / No trade"),
                            "has_setup": ev.get("decision") not in ["Wait / No trade", None]
                        }
                        for s_id, ev in all_evals.items()
                    }
                    
                    payload = {
                        "type": "MARKET_UPDATE",
                        "timestamp": data.get("timestamp"),
                        "symbol": symbol,
                        "current_price": current_price,
                        "strategy_id": active_strat,
                        "strategy_name": active_name,
                        "evaluation": active_eval,
                        "is_alert": is_active_alert,
                        "last_valid_ticket": last_valid_tickets.get(symbol),
                        "account_config": account_config,
                        "radar": all_radar
                    }
                    latest_evaluation = payload
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
