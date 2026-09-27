"""
TraderPro Unified Market Data Provider.
Single live data source for all strategies, streaming authentic TradingView candles
and real-time tick prices via tv_feed.
Zero Yahoo Finance scraping, zero synthetic offset hacks.
"""

import time
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple
from backend.tv_feed import tv_feed, TV_INSTRUMENTS

logger = logging.getLogger("market_data")

# Exchange-qualified TradingView tickers across all referenced instruments
TV_TICKERS: Dict[str, str] = {
    "NAS100": "CAPITALCOM:US100",
    "NQ": "CAPITALCOM:US100",
    "SPX500": "CAPITALCOM:SPX500",
    "MES": "CAPITALCOM:SPX500",
    "GOLD": "CAPITALCOM:GOLD",
}

# Explicit, documented SMT Correlated Equity-Index Pairs (Never GOLD)
SMT_PAIRS: Dict[str, str] = {
    "NAS100": "SPX500",
    "NQ": "MES",
    "SPX500": "NAS100",
    "MES": "NQ",
}


def resample_candles(base_candles: List[Dict[str, Any]], target_minutes: int) -> List[Dict[str, Any]]:
    """
    Resamples a smaller native timeframe (e.g. 1m) into a target minute timeframe (5m, 15m, 30m, 60m, 240m).
    Used as an immediate fallback if a higher timeframe feed is initializing.
    """
    if not base_candles:
        return []

    target_sec = target_minutes * 60
    resampled: List[Dict[str, Any]] = []
    bucket_map: Dict[int, List[Dict[str, Any]]] = {}

    for c in base_candles:
        ts = int(c["timestamp"])
        bucket_ts = (ts // target_sec) * target_sec
        if bucket_ts not in bucket_map:
            bucket_map[bucket_ts] = []
        bucket_map[bucket_ts].append(c)

    for b_ts in sorted(bucket_map.keys()):
        bars = bucket_map[b_ts]
        resampled.append({
            "timestamp": b_ts,
            "open": bars[0]["open"],
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
            "close": bars[-1]["close"],
            "volume": sum(b.get("volume", 0.0) for b in bars)
        })

    return resampled


def align_series(
    series_a: List[Dict[str, Any]],
    series_b: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Aligns two candle series so they share identical timestamps before any SMT comparison.
    Only candles present in both series are retained in order.
    """
    if not series_a or not series_b:
        return series_a or [], series_b or []

    map_b = {int(c["timestamp"]): c for c in series_b}
    aligned_a: List[Dict[str, Any]] = []
    aligned_b: List[Dict[str, Any]] = []

    for c_a in series_a:
        ts = int(c_a["timestamp"])
        if ts in map_b:
            aligned_a.append(c_a)
            aligned_b.append(map_b[ts])

    return aligned_a, aligned_b


class MarketDataProvider:
    """
    Thread-safe market data provider serving authentic TradingView candles and real-time prices
    to all registered trading strategies.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {}
        self._last_fetch: Dict[str, float] = {}
        self.symbols = TV_TICKERS

    def _normalize_symbol(self, symbol_key: str) -> str:
        s = str(symbol_key).upper()
        if "GOLD" in s:
            return "GOLD"
        elif "SPX" in s or "MES" in s or "500" in s:
            return "SPX500"
        return "NAS100"

    def get_live_price(self, symbol_key: str = "NAS100") -> float:
        """Returns the current real-time tick price from TradingView feed."""
        norm_sym = self._normalize_symbol(symbol_key)
        # Check overrides first
        with self._lock:
            override = self._cache.get("overrides", {}).get(norm_sym)
            if override and (time.time() - override.get("updated_at", 0)) < 6:
                return float(override.get("price", 0.0))

        tv_ticker = TV_TICKERS.get(norm_sym, "CAPITALCOM:US100")
        price = tv_feed.get_price(tv_ticker)
        if price > 0:
            return float(price)

        # Fallback to last candle close
        candles_1m = tv_feed.get_candles(tv_ticker, "1")
        if candles_1m:
            return float(candles_1m[-1]["close"])
        return 0.0

    def update_live_price(self, symbol_key: str, price: float, high: Optional[float] = None, low: Optional[float] = None):
        """Allows webhook or external price override."""
        norm_sym = self._normalize_symbol(symbol_key)
        with self._lock:
            if "overrides" not in self._cache:
                self._cache["overrides"] = {}
            self._cache["overrides"][norm_sym] = {
                "price": price,
                "high": high,
                "low": low,
                "updated_at": time.time()
            }

    def get_market_data(self, symbol_key: str = "NAS100", force_fresh: bool = False) -> Dict[str, Any]:
        """
        Supplies a comprehensive market_data dictionary containing all authentic TradingView
        timeframe candles, timestamp-aligned correlated candles, and metadata.
        """
        try:
            norm_sym = self._normalize_symbol(symbol_key)
            tv_ticker = TV_TICKERS.get(norm_sym, "CAPITALCOM:US100")
            now = time.time()

            # 1. Fetch live quotes from TradingView feed
            quote = tv_feed.get_quote(tv_ticker)
            current_price = float(quote.get("price", 0.0))
            tv_high = float(quote.get("high", 0.0))
            tv_low = float(quote.get("low", 0.0))

            # 2. Extract authentic multi-timeframe candles directly from TradingView feed
            c_1m = tv_feed.get_candles(tv_ticker, "1")
            c_5m = tv_feed.get_candles(tv_ticker, "5")
            c_15m = tv_feed.get_candles(tv_ticker, "15")
            c_30m = tv_feed.get_candles(tv_ticker, "30")
            c_1h = tv_feed.get_candles(tv_ticker, "60")
            c_4h = tv_feed.get_candles(tv_ticker, "240")
            c_1d = tv_feed.get_candles(tv_ticker, "1D")
            c_1w = tv_feed.get_candles(tv_ticker, "1W")

            # Fallback resampling if TV stream is initializing higher timeframes
            if c_1m:
                if not c_5m:
                    c_5m = resample_candles(c_1m, 5)
                if not c_15m:
                    c_15m = resample_candles(c_1m, 15)
                if not c_30m:
                    c_30m = resample_candles(c_1m, 30)
                if not c_1h:
                    c_1h = resample_candles(c_1m, 60)
                if not c_4h:
                    c_4h = resample_candles(c_1m, 240)

            # Ensure current_price is populated from last bar if quote is pending
            if current_price <= 0 and c_1m:
                current_price = float(c_1m[-1]["close"])

            # 3. Check for webhook overrides
            with self._lock:
                override = self._cache.get("overrides", {}).get(norm_sym)
                if override and (now - override.get("updated_at", 0)) < 6:
                    current_price = float(override.get("price", current_price))
                    if override.get("high"):
                        tv_high = float(override["high"])
                    if override.get("low"):
                        tv_low = float(override["low"])

            # Live update open 1M candle close to match current_price
            if c_1m and current_price > 0:
                c_1m[-1]["close"] = current_price
                c_1m[-1]["high"] = max(c_1m[-1]["high"], current_price)
                c_1m[-1]["low"] = min(c_1m[-1]["low"], current_price)

            # 4. Correct SMT Correlated Pair mapping (Never GOLD for equity index)
            correlated_sym = SMT_PAIRS.get(norm_sym, "")
            corr_ticker = TV_TICKERS.get(correlated_sym, "") if correlated_sym else ""

            corr_1m: List[Dict[str, Any]] = []
            corr_5m: List[Dict[str, Any]] = []
            corr_15m: List[Dict[str, Any]] = []

            if corr_ticker:
                raw_corr_1m = tv_feed.get_candles(corr_ticker, "1")
                raw_corr_5m = tv_feed.get_candles(corr_ticker, "5")
                raw_corr_15m = tv_feed.get_candles(corr_ticker, "15")

                if raw_corr_1m and not raw_corr_5m:
                    raw_corr_5m = resample_candles(raw_corr_1m, 5)
                if raw_corr_1m and not raw_corr_15m:
                    raw_corr_15m = resample_candles(raw_corr_1m, 15)

                # Strictly timestamp-align correlated series with primary series
                _, corr_1m = align_series(c_1m, raw_corr_1m)
                _, corr_5m = align_series(c_5m, raw_corr_5m)
                _, corr_15m = align_series(c_15m, raw_corr_15m)

            # 5. Check data freshness
            last_quote_time = quote.get("updated_at", 0.0)
            data_stale = (len(c_1m) == 0) or ((now - last_quote_time) > 60.0 and last_quote_time > 0)

            return {
                "symbol_name": symbol_key,
                "normalized_symbol": norm_sym,
                "ticker": tv_ticker,
                "current_price": current_price,
                "day_high": tv_high,
                "day_low": tv_low,
                "candles_1m": c_1m or [],
                "candles_5m": c_5m or [],
                "candles_15m": c_15m or [],
                "candles_30m": c_30m or [],
                "candles_1h": c_1h or [],
                "candles_4h": c_4h or [],
                "candles_1d": c_1d or [],
                "candles_1w": c_1w or [],
                "correlated_symbol": correlated_sym,
                "correlated_ticker": corr_ticker,
                "correlated_candles_1m": corr_1m,
                "correlated_candles_5m": corr_5m,
                "correlated_candles_15m": corr_15m,
                "data_stale": data_stale,
                "last_updated": now,
                "timestamp": now
            }

        except Exception as e:
            logger.error(f"[MarketDataProvider] Failed to get market data for {symbol_key}: {e}", exc_info=True)
            return {
                "symbol_name": symbol_key,
                "normalized_symbol": symbol_key,
                "ticker": TV_TICKERS.get(symbol_key, ""),
                "current_price": 0.0,
                "day_high": 0.0,
                "day_low": 0.0,
                "candles_1m": [],
                "candles_5m": [],
                "candles_15m": [],
                "candles_30m": [],
                "candles_1h": [],
                "candles_4h": [],
                "candles_1d": [],
                "candles_1w": [],
                "correlated_symbol": "",
                "correlated_ticker": "",
                "correlated_candles_1m": [],
                "correlated_candles_5m": [],
                "correlated_candles_15m": [],
                "data_stale": True,
                "last_updated": time.time(),
                "timestamp": time.time()
            }


# Module singleton instance and convenience accessor
market_data_provider = MarketDataProvider()

def get_market_data(symbol_key: str = "NAS100", force_fresh: bool = False) -> Dict[str, Any]:
    return market_data_provider.get_market_data(symbol_key=symbol_key, force_fresh=force_fresh)
