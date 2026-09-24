import time
import requests
from typing import Dict, Any, Optional
from backend.tv_feed import tv_feed

class MarketDataProvider:
    def __init__(self):
        self._cache = {}
        self._last_fetch = {}
        self._headers = {"User-Agent": "Mozilla/5.0"}
        
        # Ticker mappings (CME E-mini Futures matching Capital.com CFD quotes)
        self.symbols = {
            "NAS100": "NQ=F",
            "GOLD": "GC=F"
        }

    def fetch_ohlcv(self, ticker: str, interval: str, range_str: str) -> Optional[list]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={range_str}"
        try:
            r = requests.get(url, headers=self._headers, timeout=5)
            if r.status_code != 200:
                return None
            data = r.json()
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            quotes = result['indicators']['quote'][0]
            
            candles = []
            for i in range(len(timestamps)):
                if quotes['open'][i] is not None and quotes['close'][i] is not None:
                    candles.append({
                        'timestamp': timestamps[i],
                        'open': quotes['open'][i],
                        'high': quotes['high'][i],
                        'low': quotes['low'][i],
                        'close': quotes['close'][i],
                        'volume': quotes['volume'][i] if 'volume' in quotes and quotes['volume'][i] is not None else 0
                    })
            return candles
        except Exception:
            return None

    def get_market_data(self, symbol_key: str = "NAS100", force_fresh: bool = False) -> Dict[str, Any]:
        ticker = self.symbols.get(symbol_key, "NQ=F")
        now = time.time()
        
        # Cache HTF (15m, 1h) for 30s to keep it fast (bypassed on force_fresh)
        cache_key = f"{symbol_key}_htf"
        if force_fresh or cache_key not in self._cache or (now - self._last_fetch.get(cache_key, 0)) > 30:
            c_15m = self.fetch_ohlcv(ticker, "15m", "5d")
            c_1h = self.fetch_ohlcv(ticker, "1h", "1mo")
            if c_15m and c_1h:
                self._cache[cache_key] = {"c_15m": c_15m, "c_1h": c_1h}
                self._last_fetch[cache_key] = now
        
        # Fetch 1m candles fresh
        c_1m = self.fetch_ohlcv(ticker, "1m", "1d")
        htf = self._cache.get(cache_key, {"c_15m": [], "c_1h": []})
        
        # Base broker offset for Capital.com quotes
        default_offset = 0.0
        broker_offset = self._cache.get(f"{symbol_key}_offset", default_offset)
        
        current_price = c_1m[-1]['close'] if c_1m else 0.0
        
        # 1. Check TradingView real-time feed for exact Capital.com tick
        tv_price = tv_feed.get_price(symbol_key)
        
        # 2. Check for webhook override
        has_active_webhook = False
        if symbol_key in self._cache.get("overrides", {}):
            override = self._cache["overrides"][symbol_key]
            override_age = now - override.get("updated_at", 0)
            if override_age < 6:
                current_price = override.get("price", current_price)
                has_active_webhook = True
                if c_1m:
                    broker_offset = current_price - c_1m[-1]['close']
                    self._cache[f"{symbol_key}_offset"] = broker_offset

        if not has_active_webhook:
            if tv_price > 0:
                current_price = tv_price
                if c_1m:
                    broker_offset = current_price - c_1m[-1]['close']
                    self._cache[f"{symbol_key}_offset"] = broker_offset
            else:
                current_price = round(current_price + broker_offset, 1)

        # Calibrate candle levels with broker offset so PDH/PDL and sweeps align with Capital.com
        if broker_offset != 0.0:
            if c_1m:
                c_1m[-1]['close'] = current_price
            calibrated_15m = []
            for c in htf["c_15m"]:
                calibrated_15m.append({
                    **c,
                    "open": round(c["open"] + broker_offset, 1),
                    "high": round(c["high"] + broker_offset, 1),
                    "low": round(c["low"] + broker_offset, 1),
                    "close": round(c["close"] + broker_offset, 1),
                })
            calibrated_1h = []
            for c in htf["c_1h"]:
                calibrated_1h.append({
                    **c,
                    "open": round(c["open"] + broker_offset, 1),
                    "high": round(c["high"] + broker_offset, 1),
                    "low": round(c["low"] + broker_offset, 1),
                    "close": round(c["close"] + broker_offset, 1),
                })
            htf = {"c_15m": calibrated_15m, "c_1h": calibrated_1h}
        
        return {
            "symbol_name": symbol_key,
            "ticker": ticker,
            "current_price": current_price,
            "candles_1m": c_1m or [],
            "candles_15m": htf["c_15m"],
            "candles_1h": htf["c_1h"],
            "timestamp": now
        }

    def update_live_price(self, symbol_key: str, price: float, high: float = None, low: float = None):
        if "overrides" not in self._cache:
            self._cache["overrides"] = {}
        self._cache["overrides"][symbol_key] = {
            "price": price,
            "high": high,
            "low": low,
            "updated_at": time.time()
        }
