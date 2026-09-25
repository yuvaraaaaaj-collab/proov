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
        
        # Cache HTF (15m, 30m, 1h) for 30s to keep it fast (bypassed on force_fresh)
        cache_key = f"{symbol_key}_htf"
        if force_fresh or cache_key not in self._cache or (now - self._last_fetch.get(cache_key, 0)) > 30:
            c_15m = self.fetch_ohlcv(ticker, "15m", "5d")
            c_30m = self.fetch_ohlcv(ticker, "30m", "5d")
            c_1h = self.fetch_ohlcv(ticker, "1h", "1mo")
            if c_15m and c_1h:
                self._cache[cache_key] = {"c_15m": c_15m, "c_30m": c_30m or [], "c_1h": c_1h}
                self._last_fetch[cache_key] = now
        
        # Fetch 1m candles fresh with cache fallback
        fresh_1m = self.fetch_ohlcv(ticker, "1m", "1d")
        if fresh_1m and len(fresh_1m) > 0:
            self._cache[f"{symbol_key}_1m"] = fresh_1m
            c_1m = fresh_1m
        else:
            c_1m = self._cache.get(f"{symbol_key}_1m", [])

        htf = self._cache.get(cache_key, {"c_15m": [], "c_30m": [], "c_1h": []})
        
        # Base broker offset for Capital.com quotes
        default_offset = 0.0
        broker_offset = self._cache.get(f"{symbol_key}_offset", default_offset)
        
        current_price = c_1m[-1]['close'] if c_1m else 0.0
        decimals = 2 if "gold" in symbol_key.lower() else 1
        
        # 1. Check TradingView real-time feed for exact Capital.com tick
        tv_price = tv_feed.get_price(symbol_key)
        tv_quote = tv_feed.get_quote(symbol_key)
        tv_high = tv_quote.get("high", 0.0)
        tv_low = tv_quote.get("low", 0.0)
        
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
                current_price = round(current_price + broker_offset, decimals)

        # Calibrate candle levels with broker offset so PDH/PDL, BSL/SSL and 1M structure align with Capital.com
        if broker_offset != 0.0:
            if c_1m:
                calibrated_1m = []
                for c in c_1m:
                    calibrated_1m.append({
                        **c,
                        "open": round(c["open"] + broker_offset, decimals),
                        "high": round(c["high"] + broker_offset, decimals),
                        "low": round(c["low"] + broker_offset, decimals),
                        "close": round(c["close"] + broker_offset, decimals),
                    })
                c_1m = calibrated_1m
                c_1m[-1]['close'] = current_price
                c_1m[-1]['high'] = max(c_1m[-1]['high'], current_price)
                c_1m[-1]['low'] = min(c_1m[-1]['low'], current_price)
            calibrated_15m = []
            for c in htf.get("c_15m", []):
                calibrated_15m.append({
                    **c,
                    "open": round(c["open"] + broker_offset, decimals),
                    "high": round(c["high"] + broker_offset, decimals),
                    "low": round(c["low"] + broker_offset, decimals),
                    "close": round(c["close"] + broker_offset, decimals),
                })
            calibrated_30m = []
            for c in htf.get("c_30m", []):
                calibrated_30m.append({
                    **c,
                    "open": round(c["open"] + broker_offset, decimals),
                    "high": round(c["high"] + broker_offset, decimals),
                    "low": round(c["low"] + broker_offset, decimals),
                    "close": round(c["close"] + broker_offset, decimals),
                })
            calibrated_1h = []
            for c in htf.get("c_1h", []):
                calibrated_1h.append({
                    **c,
                    "open": round(c["open"] + broker_offset, decimals),
                    "high": round(c["high"] + broker_offset, decimals),
                    "low": round(c["low"] + broker_offset, decimals),
                    "close": round(c["close"] + broker_offset, decimals),
                })
            htf = {"c_15m": calibrated_15m, "c_30m": calibrated_30m, "c_1h": calibrated_1h}
        else:
            if c_1m:
                c_1m[-1]['close'] = current_price
                c_1m[-1]['high'] = max(c_1m[-1]['high'], current_price)
                c_1m[-1]['low'] = min(c_1m[-1]['low'], current_price)
        
        return {
            "symbol_name": symbol_key,
            "ticker": ticker,
            "current_price": current_price,
            "day_high": tv_high,
            "day_low": tv_low,
            "candles_1m": c_1m or [],
            "candles_15m": htf.get("c_15m", []),
            "candles_30m": htf.get("c_30m", []),
            "candles_1h": htf.get("c_1h", []),
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

    def get_live_price(self, symbol_key: str = "NAS100") -> float:
        if "overrides" in self._cache and symbol_key in self._cache["overrides"]:
            p = self._cache["overrides"][symbol_key].get("price")
            if p and p > 0:
                return float(p)
        tv_sym = "CAPITALCOM:GOLD" if symbol_key == "GOLD" else "CAPITALCOM:US100"
        tv_quote = tv_feed.get_quote(tv_sym)
        if tv_quote and tv_quote.get("price", 0) > 0:
            return float(tv_quote["price"])
        m = self.get_market_data(symbol_key)
        return float(m.get("current_price", 0.0))
