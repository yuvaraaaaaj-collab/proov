import os
import json
import logging
import asyncio
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List
import requests

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

def load_alert_settings() -> Dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_SETTINGS, **data}
        except Exception as e:
            logger.error(f"Error loading alert settings: {e}")
    return DEFAULT_SETTINGS.copy()

def save_alert_settings(settings: Dict[str, Any]) -> bool:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
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
    
    emoji = "🟢" if "buy" in decision.lower() else "🔴"

    msg = (
        f"{emoji} <b>TRADERPRO VIP ALERT: {order_type}</b>\n\n"
        f"<b>Asset:</b> {symbol} (Capital.com)\n"
        f"<b>Strategy:</b> {strategy_name}\n"
        f"<b>Live Price:</b> {current_price}\n"
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

def send_telegram(bot_token: str, chat_ids: List[str], text: str) -> Dict[str, Any]:
    results = {}
    if not bot_token or not chat_ids:
        return {"error": "Missing bot token or chat ID"}
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for cid in chat_ids:
        cid_clean = str(cid).strip()
        if not cid_clean:
            continue
        try:
            payload = {
                "chat_id": cid_clean,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            res = requests.post(url, json=payload, timeout=8)
            results[cid_clean] = res.json()
        except Exception as e:
            results[cid_clean] = {"error": str(e)}
    return results

def send_whatsapp_callmebot(phones: List[str], apikey: str, text: str) -> Dict[str, Any]:
    results = {}
    if not apikey or not phones:
        return {"error": "Missing CallMeBot apikey or phone number"}
    
    encoded_text = urllib.parse.quote(text)
    for phone in phones:
        phone_clean = str(phone).strip().replace(" ", "").replace("+", "")
        if not phone_clean:
            continue
        try:
            # CallMeBot WhatsApp Gateway API
            url = f"https://api.callmebot.com/whatsapp.php?phone={phone_clean}&text={encoded_text}&apikey={apikey}"
            res = requests.get(url, timeout=10)
            results[phone_clean] = {"status": res.status_code, "text": res.text[:100]}
        except Exception as e:
            results[phone_clean] = {"error": str(e)}
    return results

async def dispatch_trade_alert(symbol: str, strategy_name: str, eval_data: Dict[str, Any], current_price: float):
    # Enforce non-empty order ticket before dispatching any VIP alert
    ticket = eval_data.get("order_ticket")
    if not isinstance(ticket, dict) or not ticket.get("Stop Loss") or str(ticket.get("Stop Loss")) == "---":
        logger.warning(f"Skipping notification dispatch for {symbol} - {strategy_name}: order ticket is missing or has no values.")
        return

    settings = load_alert_settings()
    
    # 1. Telegram Dispatch
    if settings.get("telegram_enabled") and settings.get("telegram_bot_token"):
        tg_text = format_telegram_message(symbol, strategy_name, eval_data, current_price)
        chat_ids = settings.get("telegram_chat_ids", [])
        if chat_ids:
            await asyncio.to_thread(send_telegram, settings["telegram_bot_token"], chat_ids, tg_text)
            
    # 2. WhatsApp Dispatch
    if settings.get("whatsapp_enabled") and settings.get("whatsapp_apikey"):
        wa_text = format_plain_message(symbol, strategy_name, eval_data, current_price)
        phones = settings.get("whatsapp_phones", [])
        if phones:
            await asyncio.to_thread(send_whatsapp_callmebot, phones, settings["whatsapp_apikey"], wa_text)
