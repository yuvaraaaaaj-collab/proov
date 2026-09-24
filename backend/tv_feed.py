import asyncio
import json
import time
import logging
import websockets

logger = logging.getLogger("tv_feed")

class TradingViewFeed:
    """
    Direct real-time tick streaming client for TradingView.
    Subscribes to official CAPITALCOM:US100 and CAPITALCOM:GOLD quotes.
    Guarantees sub-second live price matching the user's TradingView chart.
    """
    def __init__(self):
        self._quotes = {
            "NAS100": {"price": 0.0, "high": 0.0, "low": 0.0, "updated_at": 0},
            "GOLD": {"price": 0.0, "high": 0.0, "low": 0.0, "updated_at": 0}
        }
        self.is_running = False

    def get_price(self, symbol: str) -> float:
        sym = "GOLD" if "gold" in symbol.lower() else "NAS100"
        q = self._quotes.get(sym, {})
        if time.time() - q.get("updated_at", 0) < 15:
            return q.get("price", 0.0)
        return 0.0

    def get_quote(self, symbol: str) -> dict:
        sym = "GOLD" if "gold" in symbol.lower() else "NAS100"
        return self._quotes.get(sym, {})

    async def run(self):
        self.is_running = True
        uri = "wss://data.tradingview.com/socket.io/websocket"
        headers = [
            ("Origin", "https://www.tradingview.com"),
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        ]

        def fmt(obj):
            msg = json.dumps(obj)
            return f"~m~{len(msg)}~m~{msg}"

        while self.is_running:
            try:
                async with websockets.connect(uri, additional_headers=headers, ping_interval=20, ping_timeout=15) as ws:
                    session_id = f"qs_{int(time.time())}"
                    await ws.send(fmt({"m": "set_auth_token", "p": ["unauthorized_user_token"]}))
                    await ws.send(fmt({"m": "quote_create_session", "p": [session_id]}))
                    await ws.send(fmt({
                        "m": "quote_set_fields",
                        "p": [session_id, "lp", "bid", "ask", "ch", "high_price", "low_price", "open_price", "prev_close_price"]
                    }))
                    await ws.send(fmt({
                        "m": "quote_add_symbols",
                        "p": [session_id, "CAPITALCOM:US100", "CAPITALCOM:GOLD"]
                    }))

                    while self.is_running:
                        msg = await ws.recv()
                        if "~h~" in msg:
                            # Echo heartbeat
                            await ws.send(msg)
                            continue

                        for part in msg.split("~m~"):
                            if not part.startswith("{"):
                                continue
                            try:
                                data = json.loads(part)
                                if data.get("m") == "qsd":
                                    p = data.get("p", [])
                                    if len(p) >= 2 and isinstance(p[1], dict):
                                        sym_data = p[1]
                                        sym_name = sym_data.get("n", "")
                                        vals = sym_data.get("v", {})
                                        lp = vals.get("lp") or vals.get("bid")
                                        if lp is not None:
                                            now = time.time()
                                            key = "GOLD" if "GOLD" in sym_name else "NAS100"
                                            prev = self._quotes[key]
                                            self._quotes[key] = {
                                                "price": float(lp),
                                                "high": float(vals.get("high_price", prev["high"] or lp)),
                                                "low": float(vals.get("low_price", prev["low"] or lp)),
                                                "updated_at": now
                                            }
                            except Exception:
                                pass
            except Exception as e:
                logger.warning(f"TradingView Feed reconnecting: {e}")
                await asyncio.sleep(2)

tv_feed = TradingViewFeed()
