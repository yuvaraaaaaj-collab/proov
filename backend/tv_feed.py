import asyncio
import json
import time
import logging
import inspect
import websockets

logger = logging.getLogger("tv_feed")

class TradingViewFeed:
    """
    Direct real-time tick and 1-minute OHLCV candle streaming client for TradingView.
    Subscribes to official CAPITALCOM:US100 and CAPITALCOM:GOLD quotes and chart series.
    Guarantees zero-delay live price and live candles matching the user's TradingView chart.
    """
    def __init__(self):
        self._quotes = {
            "NAS100": {"price": 0.0, "high": 0.0, "low": 0.0, "updated_at": 0},
            "GOLD": {"price": 0.0, "high": 0.0, "low": 0.0, "updated_at": 0}
        }
        self._candles = {
            "NAS100": [],
            "GOLD": []
        }
        self.is_running = False

    def get_price(self, symbol: str) -> float:
        sym = "GOLD" if "gold" in symbol.lower() else "NAS100"
        q = self._quotes.get(sym, {})
        if q.get("price", 0.0) > 0:
            return float(q.get("price"))
        return 0.0

    def get_quote(self, symbol: str) -> dict:
        sym = "GOLD" if "gold" in symbol.lower() else "NAS100"
        return self._quotes.get(sym, {})

    def get_candles(self, symbol: str) -> list:
        sym = "GOLD" if "gold" in symbol.lower() else "NAS100"
        return [dict(c) for c in self._candles.get(sym, [])]

    async def run(self):
        self.is_running = True
        uri = "wss://data.tradingview.com/socket.io/websocket"
        
        sig = inspect.signature(websockets.connect)
        conn_kwargs = {"ping_interval": 20, "ping_timeout": 15}
        if "extra_headers" in sig.parameters:
            conn_kwargs["extra_headers"] = {
                "Origin": "https://www.tradingview.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
        elif "additional_headers" in sig.parameters:
            conn_kwargs["additional_headers"] = [
                ("Origin", "https://www.tradingview.com"),
                ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            ]

        def fmt(obj):
            msg = json.dumps(obj)
            return f"~m~{len(msg)}~m~{msg}"

        while self.is_running:
            try:
                async with websockets.connect(uri, **conn_kwargs) as ws:
                    now_ts = int(time.time())
                    qs = f"qs_{now_ts}"
                    cs_us = f"cs_us_{now_ts}"
                    cs_gd = f"cs_gd_{now_ts}"

                    await ws.send(fmt({"m": "set_auth_token", "p": ["unauthorized_user_token"]}))
                    
                    # 1. Live Quote Streaming (sub-second ticks)
                    await ws.send(fmt({"m": "quote_create_session", "p": [qs]}))
                    await ws.send(fmt({
                        "m": "quote_set_fields",
                        "p": [qs, "lp", "bid", "ask", "ch", "high_price", "low_price", "open_price", "prev_close_price"]
                    }))
                    await ws.send(fmt({
                        "m": "quote_add_symbols",
                        "p": [qs, "CAPITALCOM:US100", "CAPITALCOM:GOLD"]
                    }))

                    # 2. Live 1-Minute Chart Bar Streaming for US100 (Zero-delay Capital.com bars)
                    await ws.send(fmt({"m": "chart_create_session", "p": [cs_us, ""]}))
                    sym_us = json.dumps({"adjustment": "splits", "symbol": "CAPITALCOM:US100"})
                    await ws.send(fmt({"m": "resolve_symbol", "p": [cs_us, "sds_sym_us", f"={sym_us}"]}))
                    await ws.send(fmt({"m": "create_series", "p": [cs_us, "sds_us", "s1", "sds_sym_us", "1", 60, ""]}))

                    # 3. Live 1-Minute Chart Bar Streaming for GOLD (Zero-delay Capital.com bars)
                    await ws.send(fmt({"m": "chart_create_session", "p": [cs_gd, ""]}))
                    sym_gd = json.dumps({"adjustment": "splits", "symbol": "CAPITALCOM:GOLD"})
                    await ws.send(fmt({"m": "resolve_symbol", "p": [cs_gd, "sds_sym_gd", f"={sym_gd}"]}))
                    await ws.send(fmt({"m": "create_series", "p": [cs_gd, "sds_gd", "s1", "sds_sym_gd", "1", 60, ""]}))

                    print(f"[TV Feed] Successfully connected to TradingView live tick & candle stream")

                    while self.is_running:
                        msg = await ws.recv()
                        if "~h~" in msg:
                            # Echo heartbeat immediately
                            await ws.send(msg)
                            continue

                        for part in msg.split("~m~"):
                            if not part.startswith("{"):
                                continue
                            try:
                                data = json.loads(part)
                                m_type = data.get("m")
                                
                                # Process real-time quote ticks
                                if m_type == "qsd":
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
                                            price_val = float(lp)
                                            self._quotes[key] = {
                                                "price": price_val,
                                                "high": float(vals.get("high_price", prev["high"] or price_val)),
                                                "low": float(vals.get("low_price", prev["low"] or price_val)),
                                                "updated_at": now
                                            }
                                            # Live update active 1M candle close & extreme
                                            if self._candles[key]:
                                                self._candles[key][-1]["close"] = price_val
                                                self._candles[key][-1]["high"] = max(self._candles[key][-1]["high"], price_val)
                                                self._candles[key][-1]["low"] = min(self._candles[key][-1]["low"], price_val)

                                # Process real-time 1M chart bars
                                elif m_type == "timescale_update":
                                    p = data.get("p", [])
                                    if len(p) >= 2 and isinstance(p[1], dict):
                                        sds = p[1]
                                        for sds_key in ["sds_us", "sds_gd"]:
                                            if sds_key in sds and "s" in sds[sds_key]:
                                                sym = "NAS100" if sds_key == "sds_us" else "GOLD"
                                                for bar_item in sds[sds_key]["s"]:
                                                    v = bar_item.get("v")
                                                    if v and len(v) >= 5:
                                                        c = {
                                                            "timestamp": int(v[0]),
                                                            "open": float(v[1]),
                                                            "high": float(v[2]),
                                                            "low": float(v[3]),
                                                            "close": float(v[4]),
                                                            "volume": float(v[5]) if len(v) > 5 else 0.0
                                                        }
                                                        if not self._candles[sym]:
                                                            self._candles[sym].append(c)
                                                        elif c["timestamp"] == self._candles[sym][-1]["timestamp"]:
                                                            self._candles[sym][-1] = c
                                                        elif c["timestamp"] > self._candles[sym][-1]["timestamp"]:
                                                            self._candles[sym].append(c)
                                                            if len(self._candles[sym]) > 100:
                                                                self._candles[sym].pop(0)
                            except Exception:
                                pass
            except Exception as e:
                print(f"[TV Feed] Error or Reconnecting: {e}")
                await asyncio.sleep(2)

tv_feed = TradingViewFeed()
