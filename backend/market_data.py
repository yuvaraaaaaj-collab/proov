import time
import requests
from typing import Dict, Any, Optional

class MarketDataProvider:
    def __init__(self):
        self._cache = {}
        self._last_fetch = {}
        self._headers = {"User-Agent": "Mozilla/5.0"}
        
        # Ticker mappings (Spot Cash Index for NAS100 / US100)
        self.symbols = {
            "NAS100": "^NDX",
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

    def get_market_data(self, symbol_key: str = "NAS100") -> Dict[str, Any]:
        ticker = self.symbols.get(symbol_key, "NQ=F")
        now = time.time()
        
        # Cache HTF (15m, 1h) for 30s to keep it fast
        cache_key = f"{symbol_key}_htf"
        if cache_key not in self._cache or (now - self._last_fetch.get(cache_key, 0)) > 30:
            c_15m = self.fetch_ohlcv(ticker, "15m", "5d")
            c_1h = self.fetch_ohlcv(ticker, "1h", "1mo")
            if c_15m and c_1h:
                self._cache[cache_key] = {"c_15m": c_15m, "c_1h": c_1h}
                self._last_fetch[cache_key] = now
        
        # Fetch 1m candles fresh
        c_1m = self.fetch_ohlcv(ticker, "1m", "1d")
        htf = self._cache.get(cache_key, {"c_15m": [], "c_1h": []})
        
        current_price = c_1m[-1]['close'] if c_1m else 0.0
        
        # Check for webhook override & auto-calibrated live offset
        if symbol_key in self._cache.get("overrides", {}):
            override = self._cache["overrides"][symbol_key]
            override_age = now - override.get("updated_at", 0)
            
            if override_age < 6:
                # Active tab stream: use exact price and calibrate broker offset
                current_price = override.get("price", current_price)
                if c_1m:
                    self._cache[f"{symbol_key}_offset"] = current_price - c_1m[-1]['close']
            else:
                # Tab closed: apply calibrated broker offset to live cloud feed so it NEVER freezes!
                last_offset = self._cache.get(f"{symbol_key}_offset", 0.0)
                current_price = round(current_price + last_offset, 1)
            
            if c_1m:
                c_1m[-1]['close'] = current_price
                if override_age < 6:
                    if override.get('high') is not None and override['high'] > c_1m[-1]['high']:
                        c_1m[-1]['high'] = override['high']
                    if override.get('low') is not None and override['low'] < c_1m[-1]['low']:
                        c_1m[-1]['low'] = override['low']
        
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
