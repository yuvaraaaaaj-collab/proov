import os
import json
import logging
import asyncio
import datetime
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import zoneinfo
    IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
    EST_TZ = zoneinfo.ZoneInfo("America/New_York")
except Exception:
    import pytz
    IST_TZ = pytz.timezone("Asia/Kolkata")
    EST_TZ = pytz.timezone("America/New_York")

logger = logging.getLogger("notifier")

SETTINGS_FILE = Path(__file__).resolve().parent / "alert_settings.json"

DEFAULT_SETTINGS = {
    "vip_pin": "7788",
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_ids": [],  # List of chat IDs (user + friends)
    "whatsapp_enabled": False,
    "whatsapp_apikey": "",
    "whatsapp_phones": [],    # List of phone numbers with country code e.g. +91XXXXXXXXXX
    "push_enabled": True
}

_cached_settings: Optional[Dict[str, Any]] = None
_async_http_client = None

def get_async_http_client():
    global _async_http_client
    if HAS_HTTPX:
        if _async_http_client is None or getattr(_async_http_client, "is_closed", False):
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=40, keepalive_expiry=60.0)
            _async_http_client = httpx.AsyncClient(timeout=4.0, limits=limits)
        return _async_http_client
    return None

def load_alert_settings() -> Dict[str, Any]:
    global _cached_settings
    if _cached_settings is not None:
        return _cached_settings
    loaded = DEFAULT_SETTINGS.copy()
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                loaded.update(data)
        except Exception as e:
            logger.error(f"Error loading alert settings: {e}")

    # Fallback to Environment Variables (vital for Railway persistence across restarts)
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if env_token:
        loaded["telegram_bot_token"] = env_token
        loaded["telegram_enabled"] = True
    env_chat_ids = os.environ.get("TELEGRAM_CHAT_IDS")
    if env_chat_ids:
        if env_chat_ids.startswith("["):
            try:
                loaded["telegram_chat_ids"] = json.loads(env_chat_ids)
            except Exception:
                loaded["telegram_chat_ids"] = [c.strip() for c in env_chat_ids.split(",") if c.strip()]
        else:
            loaded["telegram_chat_ids"] = [c.strip() for c in env_chat_ids.split(",") if c.strip()]
        loaded["telegram_enabled"] = True

    _cached_settings = loaded
    return _cached_settings

def save_alert_settings(settings: Dict[str, Any]) -> bool:
    global _cached_settings
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        _cached_settings = settings
        return True
    except Exception as e:
        logger.error(f"Error saving alert settings: {e}")
        return False

def format_telegram_message(symbol: str, strategy_name: str, eval_data: Dict[str, Any], current_price: float) -> str:
    decision = eval_data.get("decision", "TRADE ALERT")
    ticket = eval_data.get("order_ticket") or {}
    order_type = ticket.get("Order Type", decision.upper())
    entry = ticket.get("Entry Price", current_price)
    sl = ticket.get("Stop Loss", "---")
    tp = ticket.get("Take Profit", "---")
    rr = ticket.get("R:R", "1:2+")
    risk = ticket.get("Risk Amount", "$2.50 (Goat Safe)")
    gain = ticket.get("Projected Profit", "---")
    reason = eval_data.get("reason", "")
    
    now_ist = datetime.datetime.now(IST_TZ).strftime("%I:%M:%S %p IST")
    now_est = datetime.datetime.now(EST_TZ).strftime("%I:%M:%S %p EST")

    emoji = "🟢" if "buy" in decision.lower() else "🔴"

    msg = (
        f"{emoji} <b>TRADERPRO VIP ALERT: {order_type}</b>\n\n"
        f"<b>Asset:</b> {symbol} (Capital.com)\n"
        f"<b>Strategy:</b> {strategy_name}\n"
        f"<b>Live Price:</b> {current_price}\n"
        f"⏰ <b>Signal Time:</b> <code>{now_ist} ({now_est})</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Entry:</b> <code>{entry}</code>\n"
        f"🛑 <b>Stop Loss:</b> <code>{sl}</code>\n"
        f"💰 <b>Take Profit:</b> <code>{tp}</code>\n"
        f"⚖️ <b>Risk/Reward:</b> {rr}\n"
        f"🛡️ <b>Risk:</b> {risk}\n"
        f"💵 <b>Target Gain:</b> {gain}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>{reason}</i>\n\n"
        f"👉 <a href=\"https://traderpro-app-production.up.railway.app\">Open TraderPro Terminal</a>"
    )
    return msg

def format_plain_message(symbol: str, strategy_name: str, eval_data: Dict[str, Any], current_price: float) -> str:
    decision = eval_data.get("decision", "TRADE ALERT")
    ticket = eval_data.get("order_ticket") or {}
    order_type = ticket.get("Order Type", decision.upper())
    entry = ticket.get("Entry Price", current_price)
    sl = ticket.get("Stop Loss", "---")
    tp = ticket.get("Take Profit", "---")
    rr = ticket.get("R:R", "1:2+")
    risk = ticket.get("Risk Amount", "$2.50")
    
    msg = (
        f"🚨 TRADERPRO VIP: {order_type} on {symbol}\n"
        f"Strategy: {strategy_name}\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"TP: {tp}\n"
        f"R:R: {rr} | Risk: {risk}\n"
        f"Open App: https://traderpro-app-production.up.railway.app"
    )
    return msg

# High-Speed Async Telegram Delivery (Zero Blocking, Parallel HTTP/2)
async def async_send_telegram(bot_token: str, chat_ids: List[str], text: str) -> Dict[str, Any]:
    if not bot_token or not chat_ids:
        return {"error": "Missing bot token or chat ID"}
    
    client = get_async_http_client()
    if not client:
        return await asyncio.to_thread(send_telegram, bot_token, chat_ids, text)

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    async def send_single(cid: str):
        cid_clean = str(cid).strip()
        if not cid_clean:
            return None, None
        payload = {
            "chat_id": cid_clean,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        try:
            res = await client.post(url, json=payload)
            return cid_clean, res.json()
        except Exception as e:
            logger.error(f"[Telegram Instant Delivery Error] {cid_clean}: {e}")
            return cid_clean, {"error": str(e)}

    tasks = [send_single(cid) for cid in chat_ids if str(cid).strip()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = {}
    for item in results:
        if isinstance(item, tuple) and item[0]:
            out[item[0]] = item[1]
    return out

# High-Speed Async WhatsApp Delivery
async def async_send_whatsapp(phones: List[str], apikey: str, text: str) -> Dict[str, Any]:
    if not apikey or not phones:
        return {"error": "Missing CallMeBot apikey or phone number"}
    
    client = get_async_http_client()
    if not client:
        return await asyncio.to_thread(send_whatsapp_callmebot, phones, apikey, text)

    encoded_text = urllib.parse.quote(text)
    
    async def send_single_wa(phone: str):
        phone_clean = str(phone).strip().replace(" ", "").replace("+", "")
        if not phone_clean:
            return None, None
        url = f"https://api.callmebot.com/whatsapp.php?phone={phone_clean}&text={encoded_text}&apikey={apikey}"
        try:
            res = await client.get(url)
            return phone_clean, {"status": res.status_code, "text": res.text[:100]}
        except Exception as e:
            return phone_clean, {"error": str(e)}

    tasks = [send_single_wa(p) for p in phones if str(p).strip()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = {}
    for item in results:
        if isinstance(item, tuple) and item[0]:
            out[item[0]] = item[1]
    return out

# Synchronous fallback wrappers for existing endpoints
def send_telegram(bot_token: str, chat_ids: List[str], text: str) -> Dict[str, Any]:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(async_send_telegram(bot_token, chat_ids, text), loop)
            return future.result(timeout=4.0)
    except Exception:
        pass
    # Direct requests fallback
    results = {}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    with requests.Session() as s:
        for cid in chat_ids:
            cid_clean = str(cid).strip()
            if not cid_clean:
                continue
            try:
                payload = {"chat_id": cid_clean, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
                res = s.post(url, json=payload, timeout=4)
                results[cid_clean] = res.json()
            except Exception as e:
                results[cid_clean] = {"error": str(e)}
    return results

def send_whatsapp_callmebot(phones: List[str], apikey: str, text: str) -> Dict[str, Any]:
    results = {}
    encoded_text = urllib.parse.quote(text)
    with requests.Session() as s:
        for phone in phones:
            phone_clean = str(phone).strip().replace(" ", "").replace("+", "")
            if not phone_clean:
                continue
            try:
                url = f"https://api.callmebot.com/whatsapp.php?phone={phone_clean}&text={encoded_text}&apikey={apikey}"
                res = s.get(url, timeout=5)
                results[phone_clean] = {"status": res.status_code, "text": res.text[:100]}
            except Exception as e:
                results[phone_clean] = {"error": str(e)}
    return results

# Instant Trade Alert Dispatcher (Zero delay, non-blocking background task)
async def dispatch_trade_alert(symbol: str, strategy_name: str, eval_data: Dict[str, Any], current_price: float):
    # Strictly disable notification push for Session Momentum Breakout
    if "session momentum breakout" in str(strategy_name).lower() or "session_breakout" in str(strategy_name).lower():
        logger.info(f"Notification push is disabled for {strategy_name}.")
        return

    # Enforce non-empty order ticket before dispatching any VIP alert
    ticket = eval_data.get("order_ticket")
    if not isinstance(ticket, dict) or not ticket.get("Stop Loss") or str(ticket.get("Stop Loss")) == "---":
        logger.warning(f"Skipping notification dispatch for {symbol} - {strategy_name}: order ticket is missing or has no values.")
        return

    settings = load_alert_settings()
    
    # 1. Instant Parallel Telegram Dispatch
    if settings.get("telegram_enabled") and settings.get("telegram_bot_token"):
        chat_ids = settings.get("telegram_chat_ids", [])
        if chat_ids:
            tg_text = format_telegram_message(symbol, strategy_name, eval_data, current_price)
            asyncio.create_task(async_send_telegram(settings["telegram_bot_token"], chat_ids, tg_text))
            
    # 2. Instant Parallel WhatsApp Dispatch
    if settings.get("whatsapp_enabled") and settings.get("whatsapp_apikey"):
        phones = settings.get("whatsapp_phones", [])
        if phones:
            wa_text = format_plain_message(symbol, strategy_name, eval_data, current_price)
            asyncio.create_task(async_send_whatsapp(phones, settings["whatsapp_apikey"], wa_text))
