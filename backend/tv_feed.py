"""
TradingView Real-Time Multi-Symbol & Multi-Timeframe Streaming Client.
Direct WebSocket stream to official TradingView data servers.
Subscribes to:
  - CAPITALCOM:US100 (NAS100 / NQ)
  - CAPITALCOM:SPX500 (SPX500 / MES - SMT Correlated Equity Index)
  - CAPITALCOM:GOLD (Commodity)
Streams sub-second quotes and multi-resolution OHLCV series (1m, 5m, 15m, 30m, 1h, 4h, 1D, 1W)
with zero delay.
"""

import asyncio
import json
import time
import logging
import inspect
import threading
import websockets
from typing import Dict, List, Any, Optional

logger = logging.getLogger("tv_feed")

# Exchange-qualified TradingView tickers
TV_INSTRUMENTS: Dict[str, str] = {
    "NAS100": "CAPITALCOM:US100",
    "SPX500": "CAPITALCOM:SPX500",
    "GOLD": "CAPITALCOM:GOLD"
}

# Resolutions and requested historical bar counts
TV_RESOLUTIONS: List[tuple] = [
    ("1", 300),    # 1-minute
    ("5", 100),    # 5-minute
    ("15", 100),   # 15-minute
    ("30", 100),   # 30-minute
    ("60", 100),   # 1-hour
    ("240", 80),   # 4-hour
    ("1D", 80),    # Daily
    ("1W", 50),    # Weekly
]


class TradingViewFeed:
    """
    Unified real-time quote and candle streaming client for TradingView.
    Maintains synchronized multi-timeframe candles for US100, SPX500, and GOLD.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._quotes: Dict[str, Dict[str, Any]] = {
            sym: {"price": 0.0, "high": 0.0, "low": 0.0, "updated_at": 0.0}
            for sym in TV_INSTRUMENTS.keys()
        }
        # Nested dict: _candles[sym][resolution] -> list of candle dicts
        self._candles: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
            sym: {res: [] for res, _ in TV_RESOLUTIONS}
            for sym in TV_INSTRUMENTS.keys()
        }
        self.is_running = False
        self._last_connected_at: float = 0.0
        self._last_heartbeat: float = 0.0

    def _normalize_key(self, sym_or_ticker: str) -> str:
        s = str(sym_or_ticker).upper()
        if "GOLD" in s:
            return "GOLD"
        elif "SPX" in s or "MES" in s or "500" in s:
            return "SPX500"
        elif "US100" in s or "NAS" in s or "NQ" in s:
            return "NAS100"
        return "NAS100"

    def get_price(self, symbol: str) -> float:
        key = self._normalize_key(symbol)
        with self._lock:
            q = self._quotes.get(key, {})
            return float(q.get("price", 0.0))

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        key = self._normalize_key(symbol)
        with self._lock:
            return dict(self._quotes.get(key, {}))

    def get_candles(self, symbol: str, resolution: str = "1") -> List[Dict[str, Any]]:
        key = self._normalize_key(symbol)
        with self._lock:
            series = self._candles.get(key, {}).get(resolution, [])
            return [dict(c) for c in series]

    def is_healthy(self) -> bool:
        with self._lock:
            now = time.time()
            return (now - self._last_heartbeat) < 45.0 and self.is_running

    async def _connect_ws(self, uri: str):
        headers_list = [
            ("Origin", "https://www.tradingview.com"),
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        ]
        # Attempt 1: additional_headers (websockets >= 14 or asyncio client)
        try:
            return await websockets.connect(
                uri,
                additional_headers=headers_list,
                ping_interval=20,
                ping_timeout=15,
                open_timeout=20
            )
        except TypeError:
            pass

        # Attempt 2: extra_headers dict (websockets legacy)
        try:
            return await websockets.connect(
                uri,
                extra_headers=dict(headers_list),
                ping_interval=20,
                ping_timeout=15,
                open_timeout=20
            )
        except TypeError:
            pass

        # Attempt 3: clean connect without extra header parameters
        return await websockets.connect(
            uri,
            ping_interval=20,
            ping_timeout=15,
            open_timeout=20
        )

    async def run(self):
        self.is_running = True
        uri = "wss://data.tradingview.com/socket.io/websocket"

        def fmt(obj: dict) -> str:
            msg = json.dumps(obj)
            return f"~m~{len(msg)}~m~{msg}"

        while self.is_running:
            ws = None
            try:
                ws = await self._connect_ws(uri)
                now_ts = int(time.time())
                self._last_connected_at = time.time()
                self._last_heartbeat = time.time()
                qs = f"qs_{now_ts}"

                await ws.send(fmt({"m": "set_auth_token", "p": ["unauthorized_user_token"]}))

                # 1. Quote Session (sub-second tick prices)
                await ws.send(fmt({"m": "quote_create_session", "p": [qs]}))
                await ws.send(fmt({
                    "m": "quote_set_fields",
                    "p": [qs, "lp", "bid", "ask", "ch", "high_price", "low_price", "open_price", "prev_close_price"]
                }))
                await ws.send(fmt({
                    "m": "quote_add_symbols",
                    "p": [qs] + list(TV_INSTRUMENTS.values())
                }))
                await ws.send(fmt({
                    "m": "quote_fast_symbols",
                    "p": [qs] + list(TV_INSTRUMENTS.values())
                }))

                # 2. Multi-Timeframe Chart Sessions across symbols
                series_map: Dict[str, tuple] = {}
                for sym_key, tv_ticker in TV_INSTRUMENTS.items():
                    for res, cnt in TV_RESOLUTIONS:
                        sds_id = f"s_{sym_key}_{res}"
                        cs = f"cs_{sym_key}_{res}_{now_ts}"
                        series_map[sds_id] = (sym_key, res)
                        await ws.send(fmt({"m": "chart_create_session", "p": [cs, ""]}))
                        sym_spec = json.dumps({"adjustment": "splits", "symbol": tv_ticker})
                        await ws.send(fmt({"m": "resolve_symbol", "p": [cs, f"sym_{sds_id}", f"={sym_spec}"]}))
                        await ws.send(fmt({"m": "create_series", "p": [cs, sds_id, "s1", f"sym_{sds_id}", res, cnt, ""]}))

                print(f"[TV Feed] Connected to TradingView; registered {list(TV_INSTRUMENTS.keys())} across 8 resolutions.", flush=True)
                logger.info("[TV Feed] Connected to TradingView; registered 3 instruments across 8 timeframe resolutions.")

                while self.is_running:
                    msg = await ws.recv()
                    self._last_heartbeat = time.time()
                    if "~h~" in msg:
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
                                        key = self._normalize_key(sym_name)
                                        price_val = float(lp)
                                        now_f = time.time()
                                        with self._lock:
                                            prev = self._quotes[key]
                                            self._quotes[key] = {
                                                "price": price_val,
                                                "high": float(vals.get("high_price", prev["high"] or price_val)),
                                                "low": float(vals.get("low_price", prev["low"] or price_val)),
                                                "updated_at": now_f
                                            }
                                            # Update current open candle close
                                            c_1m = self._candles[key].get("1")
                                            if c_1m:
                                                c_1m[-1]["close"] = price_val
                                                c_1m[-1]["high"] = max(c_1m[-1]["high"], price_val)
                                                c_1m[-1]["low"] = min(c_1m[-1]["low"], price_val)

                            # Process chart bar timescale updates
                            elif m_type == "timescale_update":
                                p = data.get("p", [])
                                if len(p) >= 2 and isinstance(p[1], dict):
                                    sds = p[1]
                                    for sds_id, s_info in series_map.items():
                                        if sds_id in sds and "s" in sds[sds_id]:
                                            sym_k, res_k = s_info
                                            new_bars = []
                                            for bar_item in sds[sds_id]["s"]:
                                                v = bar_item.get("v")
                                                if v and len(v) >= 5:
                                                    new_bars.append({
                                                        "timestamp": int(v[0]),
                                                        "open": float(v[1]),
                                                        "high": float(v[2]),
                                                        "low": float(v[3]),
                                                        "close": float(v[4]),
                                                        "volume": float(v[5]) if len(v) > 5 else 0.0
                                                    })
                                            if new_bars:
                                                with self._lock:
                                                    target = self._candles[sym_k][res_k]
                                                    bar_dict = {b["timestamp"]: b for b in target}
                                                    for b in new_bars:
                                                        bar_dict[b["timestamp"]] = b
                                                    sorted_bars = [bar_dict[ts] for ts in sorted(bar_dict.keys())]
                                                    max_len = 300 if res_k == "1" else 120
                                                    self._candles[sym_k][res_k] = sorted_bars[-max_len:]
                        except Exception as parse_err:
                            logger.debug(f"[TV Feed] Message parse error: {parse_err}")

            except Exception as e:
                print(f"[TV Feed] Disconnected or error: {e}. Reconnecting in 3s...", flush=True)
                logger.warning(f"[TV Feed] Disconnected or error: {e}. Reconnecting in 3s...")
                await asyncio.sleep(3)
            finally:
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:
                        pass


tv_feed = TradingViewFeed()
