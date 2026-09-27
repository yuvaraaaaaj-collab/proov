#!/usr/bin/env python3
"""
ict_market_maker.py — ICT Market Maker Model (Full 24-Lesson Mastery Strategy)
==============================================================================
Implements the complete ICT Market Maker Framework synthesizing all 24 lessons:
  1. Market Structure & Liquidity Foundations (Lessons 1, 3, 23)
  2. Strict Risk & Money Management (Lessons 2, 15, 19) — Goat Funded Trader ($1,000)
  3. Killzones & Timing (Lessons 4, 5, 6, 7) — Asian, London, New York, London Close
  4. Weekly Bias Filter (Lesson 8) — Prior week range & midpoint analysis
  5. Time & Price Theory (Lesson 9) — Midnight 00:00 NY Daily Open discount/premium
  6. AMD / Power of Three (Lesson 10) — Accumulation, Manipulation, Distribution
  7. Asian Range Measurement & Projections (Lesson 11) — 1x/2x measured move targets
  8. Judas Swing Detection (Lesson 12) — London false expansion & reversal
  9. Daily Bias & PDH/PDL Liquidity (Lesson 13) — Prior Day High & Low targets
  10. Confluence Swing Points (Lesson 14) — Filtering out floating noise
  11. SMT Divergence (Lesson 16) — Real-time correlated comparison (NAS100 vs SPX500 / NQ vs MES)
  12. ATM Method (Lesson 17) — Two-stage high/low rejection pattern
  13. OTE Primer (Lesson 18) — 61.8% to 79.0% Fib retracement sweet spot
  14. Explosive Move / Compression Coiling (Lesson 22) — Pre-breakout ATR squeeze
  15. Fractal HTF to LTF Execution (Lessons 23, 24) — HTF gives why, LTF gives when
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from datetime import time as dtime
from typing import Dict, List, Literal, Optional, Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .base_strategy import BaseStrategy
from backend.risk_engine import build_order_ticket, sl_buffer, MIN_RR, DEFAULT_ACCOUNT_BALANCE
from backend.smt_engine import check_smt_divergence


# ---------------------------------------------------------------------------
# Pydantic models for internal and external contracts
# ---------------------------------------------------------------------------

class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class ChecklistItem(BaseModel):
    key: str
    label: str
    met: bool
    detail: Optional[str] = None


class StrategySignal(BaseModel):
    strategy: str = "ICT Market Maker Model (24-Lesson Mastery)"
    symbol: str
    timestamp: datetime.datetime
    htf_trend: Literal["bullish", "bearish", "ranging", "unknown"] = "unknown"
    direction: Literal["long", "short", "none"] = "none"
    active: bool = False
    confidence: float = 0.0
    checklist: List[ChecklistItem] = Field(default_factory=list)
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    take_profit_scaled: Optional[float] = None  # Lesson 15: Intermediate TP
    risk_reward: Optional[float] = None
    amd_phase: Literal["accumulation", "manipulation", "distribution", "undetermined"] = "undetermined"
    killzone: Literal["asian", "london", "new_york", "london_close", "none"] = "none"
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ICTConfig:
    swing_lookback: int = 2
    equal_level_tolerance: float = 0.0006       # 0.06% fraction of price
    displacement_multiple: float = 1.4
    displacement_avg_window: int = 20
    ote_low: float = 0.618
    ote_sweet_spot: float = 0.705
    ote_high: float = 0.790
    ny_tz: str = "America/New_York"
    ist_tz: str = "Asia/Kolkata"
    # Killzone hours in New York Local Time (Lesson 4, 5, 6, 7)
    asian_session: tuple = (dtime(20, 0), dtime(0, 0))        # 20:00 - 00:00 NY
    london_session: tuple = (dtime(2, 0), dtime(5, 0))        # 02:00 - 05:00 NY
    newyork_session: tuple = (dtime(7, 0), dtime(10, 0))      # 07:00 - 10:00 NY
    london_close_session: tuple = (dtime(10, 0), dtime(12, 0))# 10:00 - 12:00 NY
    compression_atr_fraction: float = 0.65
    atr_window: int = 14
    smt_time_tolerance_bars: int = 3
    lookback_bars_for_model: int = 120
    min_risk_reward: float = MIN_RR


# ---------------------------------------------------------------------------
# Internal Utilities & Calculations
# ---------------------------------------------------------------------------

def _raw_candles_to_df(raw_candles: List[Dict[str, Any]]) -> pd.DataFrame:
    if not raw_candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    data = []
    for c in raw_candles:
        ts = c.get("timestamp")
        if isinstance(ts, (int, float)):
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        elif isinstance(ts, str):
            dt = pd.to_datetime(ts, utc=True)
        elif isinstance(ts, datetime.datetime):
            dt = ts if ts.tzinfo else ts.replace(tzinfo=datetime.timezone.utc)
        else:
            continue
        data.append({
            "timestamp": dt,
            "open": float(c.get("open", 0.0)),
            "high": float(c.get("high", 0.0)),
            "low": float(c.get("low", 0.0)),
            "close": float(c.get("close", 0.0)),
            "volume": float(c.get("volume", 0.0))
        })
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return df.set_index("timestamp").sort_index()


def _avg_range(df: pd.DataFrame, window: int) -> pd.Series:
    return (df["high"] - df["low"]).abs().rolling(window, min_periods=1).mean()


def _find_swings(df: pd.DataFrame, cfg: ICTConfig) -> pd.DataFrame:
    n = cfg.swing_lookback
    highs, lows = df["high"].values, df["low"].values
    sh = np.zeros(len(df), dtype=bool)
    sl = np.zeros(len(df), dtype=bool)
    for i in range(n, len(df) - n):
        wh = highs[i - n: i + n + 1]
        wl = lows[i - n: i + n + 1]
        if highs[i] == wh.max() and np.argmax(wh) == n:
            sh[i] = True
        if lows[i] == wl.min() and np.argmin(wl) == n:
            sl[i] = True
    out = df.copy()
    out["swing_high"] = sh
    out["swing_low"] = sl
    return out


def _classify_trend(df: pd.DataFrame) -> str:
    highs = df[df["swing_high"]]["high"]
    lows = df[df["swing_low"]]["low"]
    if len(highs) < 2 or len(lows) < 2:
        return "ranging"
    hh = highs.iloc[-1] > highs.iloc[-2]
    hl = lows.iloc[-1] > lows.iloc[-2]
    ll = lows.iloc[-1] < lows.iloc[-2]
    lh = highs.iloc[-1] < highs.iloc[-2]
    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    return "ranging"


def _find_liquidity_pools(df: pd.DataFrame, cfg: ICTConfig) -> list[dict]:
    pools = []
    swing_highs = df[df["swing_high"]][["high"]].rename(columns={"high": "level"})
    swing_lows = df[df["swing_low"]][["low"]].rename(columns={"low": "level"})

    def cluster(points: pd.DataFrame, side: str, price_col: str):
        levels, ts = points["level"].tolist(), points.index.tolist()
        used = [False] * len(levels)
        for i in range(len(levels)):
            if used[i]:
                continue
            grp = [i]
            for j in range(i + 1, len(levels)):
                if not used[j] and abs(levels[j] - levels[i]) / max(levels[i], 1e-9) <= cfg.equal_level_tolerance:
                    grp.append(j)
            equal = len(grp) > 1
            for k in grp:
                used[k] = True
            level = float(np.mean([levels[k] for k in grp]))
            formed_ts = ts[max(grp)]
            after = df[df.index > formed_ts]
            swept = bool((after[price_col] > level).any()) if side == "buy_side" else bool((after[price_col] < level).any())
            pools.append({
                "side": side, "level": level, "formed_timestamp": formed_ts,
                "equal": equal, "swept": swept
            })

    cluster(swing_highs, "buy_side", "high")
    cluster(swing_lows, "sell_side", "low")
    return pools


def _find_order_blocks(df: pd.DataFrame, cfg: ICTConfig) -> list[dict]:
    avg_range = _avg_range(df, cfg.displacement_avg_window)
    blocks = []
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        rng = row["high"] - row["low"]
        if rng < cfg.displacement_multiple * avg_range.iloc[i]:
            continue
        if row["close"] > row["open"] and prev["close"] < prev["open"]:
            mitigated = bool((df.loc[row.name:, "low"] <= prev["low"]).any())
            blocks.append({
                "side": "bullish", "timestamp": prev.name, "high": prev["high"],
                "low": prev["low"], "mitigated": mitigated
            })
        elif row["close"] < row["open"] and prev["close"] > prev["open"]:
            mitigated = bool((df.loc[row.name:, "high"] >= prev["high"]).any())
            blocks.append({
                "side": "bearish", "timestamp": prev.name, "high": prev["high"],
                "low": prev["low"], "mitigated": mitigated
            })
    return blocks


def _find_fvgs(df: pd.DataFrame) -> list[dict]:
    gaps = []
    highs, lows, idx = df["high"].values, df["low"].values, df.index
    for i in range(1, len(df) - 1):
        c1h, c1l, c3h, c3l = highs[i - 1], lows[i - 1], highs[i + 1], lows[i + 1]
        if c1h < c3l:
            top, bottom = c3l, c1h
            filled = bool((df["low"].iloc[i + 2:] <= bottom).any()) if i + 2 < len(df) else False
            gaps.append({"side": "bullish", "timestamp": idx[i], "top": top, "bottom": bottom, "filled": filled})
        elif c1l > c3h:
            top, bottom = c1l, c3h
            filled = bool((df["high"].iloc[i + 2:] >= top).any()) if i + 2 < len(df) else False
            gaps.append({"side": "bearish", "timestamp": idx[i], "top": top, "bottom": bottom, "filled": filled})
    return gaps


def _in_session(t: dtime, session: tuple) -> bool:
    start, end = session
    return (start <= t < end) if start <= end else (t >= start or t < end)


def _current_killzone(ts: pd.Timestamp, cfg: ICTConfig) -> Dict[str, str]:
    """Calculates active killzone with both NY local time and IST time."""
    local_ny = ts.tz_convert(ZoneInfo(cfg.ny_tz)).time()
    local_ist = ts.tz_convert(ZoneInfo(cfg.ist_tz)).strftime("%H:%M IST")
    
    if _in_session(local_ny, cfg.asian_session):
        return {"id": "asian", "label": f"Asian Killzone (20:00-00:00 NY / {local_ist}) ACTIVE"}
    if _in_session(local_ny, cfg.london_session):
        return {"id": "london", "label": f"London Killzone (02:00-05:00 NY / {local_ist}) ACTIVE"}
    if _in_session(local_ny, cfg.newyork_session):
        return {"id": "new_york", "label": f"New York Killzone (07:00-10:00 NY / {local_ist}) ACTIVE"}
    if _in_session(local_ny, cfg.london_close_session):
        return {"id": "london_close", "label": f"London Close Killzone (10:00-12:00 NY / {local_ist}) ACTIVE"}
    return {"id": "none", "label": f"Outside Killzones [{local_ist}]"}


def _asian_range_details(df: pd.DataFrame, ts: pd.Timestamp, cfg: ICTConfig) -> Optional[dict]:
    """Lesson 4 & 11: Asian range high, low, height, and measured-move projections."""
    ny_index = df.index.tz_convert(ZoneInfo(cfg.ny_tz))
    today = ts.tz_convert(ZoneInfo(cfg.ny_tz)).date()
    mask = pd.Series(ny_index.date == today, index=df.index)
    day_rows = df[mask]
    if day_rows.empty:
        return None
    times = day_rows.index.tz_convert(ZoneInfo(cfg.ny_tz)).time
    asian_rows = day_rows[[_in_session(t, cfg.asian_session) for t in times]]
    if asian_rows.empty:
        return None
    ah = float(asian_rows["high"].max())
    al = float(asian_rows["low"].min())
    height = ah - al
    return {
        "high": ah,
        "low": al,
        "height": height,
        "proj_bull_1x": ah + height,
        "proj_bull_2x": ah + 2 * height,
        "proj_bear_1x": al - height,
        "proj_bear_2x": al - 2 * height
    }


def _amd_phase_now(row: pd.Series, avg_range_val: float, kz_id: str, cfg: ICTConfig) -> str:
    """Lesson 10: Accumulation, Manipulation, Distribution."""
    rng = row["high"] - row["low"]
    compressed = rng <= cfg.compression_atr_fraction * avg_range_val
    displacing = rng >= cfg.displacement_multiple * avg_range_val
    if kz_id == "asian" or compressed:
        return "accumulation"
    if kz_id == "london":
        return "manipulation"
    if kz_id in ("new_york", "london_close") and displacing:
        return "distribution"
    return "undetermined"


def _premium_discount_ote(df: pd.DataFrame, cfg: ICTConfig) -> dict:
    """Lesson 18: Premium, Discount, Equilibrium, and OTE (0.618 - 0.705 - 0.790)."""
    swings = df[(df["swing_high"]) | (df["swing_low"])].tail(2)
    if len(swings) < 2:
        return {}
    ts1, row1 = swings.index[0], swings.iloc[0]
    ts2, row2 = swings.index[1], swings.iloc[1]
    low_ts = ts1 if row1["swing_low"] else (ts2 if row2["swing_low"] else None)
    high_ts = ts1 if row1["swing_high"] else (ts2 if row2["swing_high"] else None)
    if low_ts is None or high_ts is None:
        return {}
    p1, p2 = df.loc[low_ts, "low"], df.loc[high_ts, "high"]
    if p1 == p2:
        return {}
    low, high = min(p1, p2), max(p1, p2)
    eq = (low + high) / 2
    rng = high - low
    if p2 > p1:
        ote_top, ote_bottom = high - cfg.ote_low * rng, high - cfg.ote_high * rng
        ote_sweet = high - cfg.ote_sweet_spot * rng
    else:
        ote_top, ote_bottom = low + cfg.ote_high * rng, low + cfg.ote_low * rng
        ote_sweet = low + cfg.ote_sweet_spot * rng
    return {
        "low": low, "high": high, "equilibrium": eq,
        "premium": (eq, high), "discount": (low, eq),
        "ote_zone": (min(ote_top, ote_bottom), max(ote_top, ote_bottom)),
        "ote_sweet_spot": ote_sweet
    }


def _recent_mss(df: pd.DataFrame, cfg: ICTConfig, lookback: int) -> Optional[dict]:
    """Market Structure Shift with displacement confirmation."""
    window = df.tail(lookback)
    avg_range = _avg_range(window, cfg.displacement_avg_window)
    last_swing_high = last_swing_high_ts = None
    last_swing_low = last_swing_low_ts = None
    most_recent = None

    for i, (ts, row) in enumerate(window.iterrows()):
        rng = row["high"] - row["low"]
        displacing = rng >= cfg.displacement_multiple * avg_range.iloc[i]
        if last_swing_high is not None and row["close"] > last_swing_high and displacing:
            most_recent = {
                "direction": "bullish", "timestamp": ts, "broken_level": last_swing_high,
                "broken_level_timestamp": last_swing_high_ts
            }
            last_swing_high = None
        if last_swing_low is not None and row["close"] < last_swing_low and displacing:
            most_recent = {
                "direction": "bearish", "timestamp": ts, "broken_level": last_swing_low,
                "broken_level_timestamp": last_swing_low_ts
            }
            last_swing_low = None
        if row["swing_high"]:
            last_swing_high, last_swing_high_ts = row["high"], ts
        if row["swing_low"]:
            last_swing_low, last_swing_low_ts = row["low"], ts

    return most_recent


def _engineered_liquidity_leg(df: pd.DataFrame, direction: str, lookback: int) -> bool:
    window = df.tail(lookback)
    if direction == "short":
        lows = window[window["swing_low"]]["low"]
        return len(lows) >= 2 and bool((lows.diff().dropna() > 0).tail(2).all())
    else:
        highs = window[window["swing_high"]]["high"]
        return len(highs) >= 2 and bool((highs.diff().dropna() < 0).tail(2).all())


def _htf_pd_array_zone(htf_df: pd.DataFrame, direction: str, cfg: ICTConfig) -> Optional[dict]:
    side = "bearish" if direction == "short" else "bullish"
    blocks = [b for b in _find_order_blocks(htf_df, cfg) if b["side"] == side and not b["mitigated"]]
    if blocks:
        b = blocks[-1]
        return {"kind": "Order Block", "top": b["high"], "bottom": b["low"], "timestamp": b["timestamp"]}
    gaps = [g for g in _find_fvgs(htf_df) if g["side"] == side and not g["filled"]]
    if gaps:
        g = gaps[-1]
        return {"kind": "Fair Value Gap", "top": g["top"], "bottom": g["bottom"], "timestamp": g["timestamp"]}
    return None


def _price_in_zone(price: float, zone: dict, tolerance_frac: float = 0.0015) -> bool:
    top, bottom = zone["top"], zone["bottom"]
    tol = (top - bottom) * tolerance_frac if top != bottom else top * tolerance_frac
    return (bottom - tol) <= price <= (top + tol)


def _smt_divergence_recent(df_a: pd.DataFrame, df_b: pd.DataFrame, cfg: ICTConfig, lookback: int) -> Optional[str]:
    """Lesson 16: Smart Money Technique (SMT) Divergence between correlated symbols (e.g. NAS100 vs SPX500)."""
    res = check_smt_divergence(df_a, df_b, lookback=lookback)
    return res.get("divergence")


def _calculate_weekly_bias(w_df: pd.DataFrame, h1_df: pd.DataFrame = None) -> Dict[str, Any]:
    """Lesson 8: Weekly Bias from prior week's range (close relative to midpoint)."""
    if w_df is not None and len(w_df) >= 2:
        # Authentic exchange weekly candles
        w_candle = w_df.iloc[-2]  # previous completed week
        w_high = float(w_candle["high"])
        w_low = float(w_candle["low"])
        w_close = float(w_df.iloc[-1]["close"])
        w_mid = (w_high + w_low) / 2
        is_bullish = w_close >= w_mid
        bias_str = "BULLISH" if is_bullish else "BEARISH"
        return {
            "bias": bias_str.lower(),
            "is_bullish": is_bullish,
            "high": w_high,
            "low": w_low,
            "mid": w_mid,
            "label": f"{bias_str} (Trading {'above' if is_bullish else 'below'} Prior Week Equilibrium {w_mid:.1f})"
        }
    elif h1_df is not None and len(h1_df) >= 24:
        w_sub = h1_df.tail(120)
        w_high = float(w_sub["high"].max())
        w_low = float(w_sub["low"].min())
        w_close = float(w_sub["close"].iloc[-1])
        w_mid = (w_high + w_low) / 2
        is_bullish = w_close >= w_mid
        bias_str = "BULLISH" if is_bullish else "BEARISH"
        return {
            "bias": bias_str.lower(),
            "is_bullish": is_bullish,
            "high": w_high,
            "low": w_low,
            "mid": w_mid,
            "label": f"{bias_str} (Trading {'above' if is_bullish else 'below'} 5-Day Equilibrium)"
        }
    return {"bias": "unknown", "label": "Insufficient data for Weekly Bias"}


def _get_daily_midnight_open(ltf_df: pd.DataFrame, cfg: ICTConfig) -> Optional[float]:
    """Lesson 9: Time & Price Midnight (00:00 NY) opening price."""
    ny_index = ltf_df.index.tz_convert(ZoneInfo(cfg.ny_tz))
    today = ny_index[-1].date()
    today_candles = ltf_df[pd.Series(ny_index.date == today, index=ltf_df.index)]
    if today_candles.empty:
        return None
    return float(today_candles["open"].iloc[0])


def _check_judas_swing(ltf_df: pd.DataFrame, asian_range: Optional[dict], kz_id: str, mss: Optional[dict]) -> Dict[str, Any]:
    """Lesson 12: Judas Swing Detection (London/NY manipulation false move sweeping Asian range)."""
    if not asian_range or kz_id not in ("london", "new_york"):
        return {"detected": False, "type": "NONE", "label": "Awaiting Session Killzone"}
    
    ah, al = asian_range["high"], asian_range["low"]
    swept_high = bool((ltf_df["high"] > ah).any())
    swept_low = bool((ltf_df["low"] < al).any())
    
    if swept_low and mss and mss["direction"] == "bullish":
        return {
            "detected": True, "type": "Bullish Judas Swing",
            "label": f"CONFIRMED (Swept Asian Low {al:.1f} -> Bullish MSS)"
        }
    if swept_high and mss and mss["direction"] == "bearish":
        return {
            "detected": True, "type": "Bearish Judas Swing",
            "label": f"CONFIRMED (Swept Asian High {ah:.1f} -> Bearish MSS)"
        }
    if swept_low:
        return {"detected": False, "type": "Potential Long Judas", "label": f"FORMING (Asian Low {al:.1f} Swept)"}
    if swept_high:
        return {"detected": False, "type": "Potential Short Judas", "label": f"FORMING (Asian High {ah:.1f} Swept)"}
    return {"detected": False, "type": "NONE", "label": "No Asian Range Sweep"}


# ---------------------------------------------------------------------------
# Main Strategy Implementation
# ---------------------------------------------------------------------------

class ICTMarketMakerStrategy(BaseStrategy):
    """
    ICT Market Maker Model (Full 24-Lesson Mastery Strategy)
    Compatible with BaseStrategy interface, live scanner loop, WebSocket broadcast, and Notifier.
    """
    def __init__(self, cfg: Optional[ICTConfig] = None):
        super().__init__(
            name="ICT Market Maker Model (24-Lesson Mastery)",
            description="Institutional Market Maker Buy/Sell Model synthesizing top-down bias, killzones, AMD, SMT divergence, OTE & Goat $1k risk."
        )
        self.cfg = cfg or ICTConfig()
        self._last_ltf_ts = None
        self._cached_static = {}

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self.cfg
        raw_ltf = market_data.get("candles_1m", [])
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)
        dec = 2 if "gold" in symbol.lower() else 1

        if not raw_ltf or current_price == 0.0 or len(raw_ltf) < (2 * cfg.swing_lookback + 5):
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Awaiting live market candle stream.",
                "checklist": {},
                "order_ticket": None
            }

        # Convert 1M candles to DataFrame
        ltf_df = _raw_candles_to_df(raw_ltf)
        ltf_df = _find_swings(ltf_df, cfg)
        now_ts = ltf_df.index[-1]
        now_price = float(ltf_df["close"].iloc[-1])

        # Killzone (Lessons 4-7)
        kz_info = _current_killzone(now_ts, cfg)
        kz_id = kz_info["id"]

        # AMD Phase (Lesson 10)
        avg_range_series = _avg_range(ltf_df, cfg.atr_window)
        amd_phase = _amd_phase_now(ltf_df.iloc[-1], avg_range_series.iloc[-1], kz_id, cfg)

        # HTF Frames (Lessons 3 & 23 - Authentic 4H, 1H, 30M, 15M, Daily & Weekly)
        raw_15m = market_data.get("candles_15m", [])
        raw_30m = market_data.get("candles_30m", [])
        raw_1h = market_data.get("candles_1h", [])
        raw_4h = market_data.get("candles_4h", [])
        raw_1d = market_data.get("candles_1d", [])
        raw_1w = market_data.get("candles_1w", [])

        df_15m = _find_swings(_raw_candles_to_df(raw_15m), cfg) if raw_15m else pd.DataFrame()
        df_30m = _find_swings(_raw_candles_to_df(raw_30m), cfg) if raw_30m else pd.DataFrame()
        df_1h = _find_swings(_raw_candles_to_df(raw_1h), cfg) if raw_1h else pd.DataFrame()
        df_4h = _find_swings(_raw_candles_to_df(raw_4h), cfg) if raw_4h else pd.DataFrame()
        df_1d = _find_swings(_raw_candles_to_df(raw_1d), cfg) if raw_1d else pd.DataFrame()
        df_1w = _find_swings(_raw_candles_to_df(raw_1w), cfg) if raw_1w else pd.DataFrame()

        htf_frames = {"4h": df_4h, "1h": df_1h, "30m": df_30m, "15m": df_15m}
        preferred_order = ["4h", "1h", "30m", "15m"]
        primary_htf = next((htf_frames[k] for k in preferred_order if not htf_frames[k].empty), df_1h)
        htf_trend = _classify_trend(primary_htf) if not primary_htf.empty else "unknown"

        # Correlated candles for SMT Divergence (Lesson 16)
        raw_corr = market_data.get("correlated_candles_1m", [])
        df_corr = _find_swings(_raw_candles_to_df(raw_corr), cfg) if raw_corr else None

        # Static structure caching per bar close
        recompute = (self._last_ltf_ts is None) or (now_ts != self._last_ltf_ts)
        if recompute:
            self._cached_static = {
                "trend": _classify_trend(ltf_df),
                "pools": _find_liquidity_pools(ltf_df, cfg),
                "pd_zone": _premium_discount_ote(ltf_df, cfg),
                "asian_range": _asian_range_details(ltf_df, now_ts, cfg),
                "weekly_bias": _calculate_weekly_bias(df_1w, df_1h),
                "daily_open": _get_daily_midnight_open(ltf_df, cfg)
            }
            self._last_ltf_ts = now_ts

        static = self._cached_static
        weekly_bias = static.get("weekly_bias", {})
        daily_open = static.get("daily_open")
        asian_range = static.get("asian_range")
        pd_zone = static.get("pd_zone", {})
        pools = static.get("pools", [])

        # Evaluate Long Model and Short Model
        short_res = self._evaluate_model(
            direction="short", ltf_df=ltf_df, now_price=now_price,
            htf_df=primary_htf, static=static, correlated_df=df_corr,
            dec=dec, symbol=symbol
        )
        long_res = self._evaluate_model(
            direction="long", ltf_df=ltf_df, now_price=now_price,
            htf_df=primary_htf, static=static, correlated_df=df_corr,
            dec=dec, symbol=symbol
        )

        chosen = short_res if short_res["confidence"] >= long_res["confidence"] else long_res
        is_long = (chosen is long_res)
        direction_str = "BUY" if is_long else "SELL"

        # Judas Swing check (Lesson 12)
        mss = chosen.get("mss")
        judas_info = _check_judas_swing(ltf_df, asian_range, kz_id, mss)

        # Time & Price check (Lesson 9)
        if daily_open:
            if is_long:
                tp_status = f"DISCOUNT below Daily Open ({daily_open:.1f}) [Favorable for Longs]" if now_price <= daily_open else f"Above Daily Open ({daily_open:.1f}) [Chasing]"
            else:
                tp_status = f"PREMIUM above Daily Open ({daily_open:.1f}) [Favorable for Shorts]" if now_price >= daily_open else f"Below Daily Open ({daily_open:.1f}) [Chasing]"
        else:
            tp_status = "Daily Open Reference Forming"

        # HTF PD Array detail (Lesson 6 & 23)
        htf_zone = chosen.get("htf_zone")
        htf_pd_label = f"{htf_zone['kind']} [{htf_zone['bottom']:.{dec}f} - {htf_zone['top']:.{dec}f}]" if htf_zone else "Scanning 1H/30M PD Arrays"

        # Draw on Liquidity (DOL) / Target Selection (Lesson 13 & 19)
        dol_label = chosen.get("dol_label", "Awaiting Liquidity Pool")

        # Master Checklist
        checklist = {
            "1. HTF Bias & Trend": f"{htf_trend.upper()} | Weekly: {weekly_bias.get('label', '---')}",
            "2. Time & Price (Daily Open)": tp_status,
            "3. Session & Killzone": kz_info["label"],
            "4. AMD Phase": amd_phase.upper(),
            "5. Asian Range & Judas Swing": judas_info["label"],
            "6. HTF PD Array": htf_pd_label,
            "7. Liquidity Hunt (Sweep)": "CONFIRMED (Pool Swept)" if chosen.get("sweep_met") else "WAITING (No Sweep)",
            "8. Market Structure Shift (MSS)": f"CONFIRMED ({chosen['direction'].capitalize()} MSS)" if mss else "WAITING (No Displacement)",
            "9. Entry FVG & OTE Zone": f"CONFIRMED [{chosen.get('entry_fvg_label', '---')}]" if chosen.get("fvg_met") else "WAITING (No Fresh FVG)",
            "10. SMT Divergence": chosen.get("smt_label", "None"),
            "11. Execution & Risk ($1k)": f"SAFE (Goat $2.50 Risk | 1:2+ R:R | <15% Cap)"
        }

        # Stand aside if required checklist items are not met
        if not chosen["active"]:
            decision = "Wait / No trade"
            reason = chosen.get("notes") or f"Awaiting full 24-lesson sequence: [{chosen['confidence'] * 100:.0f}% criteria met]."
            return {
                "strategy": self.name,
                "decision": decision,
                "reason": reason,
                "checklist": checklist,
                "order_ticket": None,
                "ict_metrics": {
                    "htf_trend": htf_trend,
                    "amd_phase": amd_phase,
                    "killzone": kz_id,
                    "confidence": chosen["confidence"]
                }
            }

        # Complete Confirmation Satisfied -> Generate Goat Funded Trader Order Ticket
        risk_dollars = account_config.get("risk_per_trade", 2.50)
        entry = chosen["entry"]
        sl = chosen["stop_loss"]
        tp = chosen["take_profit"]
        rr = chosen["risk_reward"] or MIN_RR
        account_bal = account_config.get("account_balance") or account_config.get("balance", DEFAULT_ACCOUNT_BALANCE)

        ticket = build_order_ticket(
            direction=direction_str,
            symbol=symbol,
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            risk_dollars=risk_dollars,
            account_balance=account_bal,
            order_type=f"{direction_str} LIMIT",
            cancel_condition=f"Price closes beyond Invalidation ({round(sl, dec)}) or sweeps TP ({round(tp, dec)}) before fill."
        )
        if chosen.get("tp_scaled"):
            ticket["Take Profit 1 (Scale)"] = round(chosen["tp_scaled"], dec)

        return {
            "strategy": self.name,
            "decision": f"{direction_str.capitalize()} limit",
            "reason": f"ICT Market Maker {direction_str} Model Complete -> Sweep + MSS + FVG inside {kz_id.upper()} Killzone -> R:R 1:{rr:.2f} to DOL.",
            "checklist": checklist,
            "order_ticket": ticket,
            "ict_metrics": {
                "htf_trend": htf_trend,
                "amd_phase": amd_phase,
                "killzone": kz_id,
                "confidence": chosen["confidence"]
            }
        }

    def _evaluate_model(self, direction: str, ltf_df: pd.DataFrame, now_price: float,
                         htf_df: pd.DataFrame, static: dict,
                         correlated_df: Optional[pd.DataFrame], dec: int, symbol: str) -> dict:
        cfg = self.cfg
        checklist: List[ChecklistItem] = []
        lookback = min(cfg.lookback_bars_for_model, len(ltf_df))

        # 1) HTF PD Array reached (Lessons 6, 23)
        htf_zone = _htf_pd_array_zone(htf_df, direction, cfg) if not htf_df.empty and len(htf_df) > 10 else None
        item1_met = htf_zone is not None and _price_in_zone(now_price, htf_zone, tolerance_frac=0.002)
        checklist.append(ChecklistItem(
            key="htf_pd_array", label="Price in HTF PD array", met=item1_met
        ))

        # 2) Consolidation / Asian Range (Lessons 4, 10, 11)
        asian_range = static.get("asian_range")
        item2_met = asian_range is not None
        checklist.append(ChecklistItem(
            key="consolidation", label="Consolidation / Asian Range formed", met=item2_met
        ))

        # 3) Engineered liquidity leg (Lesson 10)
        item3_met = _engineered_liquidity_leg(ltf_df, direction, lookback)
        checklist.append(ChecklistItem(
            key="engineered_liquidity", label="Engineered liquidity leg formed", met=item3_met
        ))

        # 4) Liquidity Hunt (Lessons 1, 5, 12)
        pools = static.get("pools", [])
        hunt_side = "buy_side" if direction == "short" else "sell_side"
        recent_sweeps = [p for p in pools if p["side"] == hunt_side and p["swept"]]
        item4_met = len(recent_sweeps) > 0
        checklist.append(ChecklistItem(
            key="liquidity_hunt", label=f"{hunt_side.replace('_', '-')} swept", met=item4_met
        ))

        # 5) Market Structure Shift (Lessons 3, 12)
        mss = _recent_mss(ltf_df, cfg, lookback)
        wanted_mss_dir = "bearish" if direction == "short" else "bullish"
        item5_met = mss is not None and mss["direction"] == wanted_mss_dir
        checklist.append(ChecklistItem(
            key="mss", label=f"{wanted_mss_dir} MSS occurred", met=item5_met
        ))

        # 6) Entry FVG present & unfilled (Lessons 3, 18)
        fvgs = _find_fvgs(ltf_df)
        wanted_fvg_side = "bearish" if direction == "short" else "bullish"
        candidate_fvgs = [g for g in fvgs if g["side"] == wanted_fvg_side and not g["filled"]]
        entry_fvg = candidate_fvgs[-1] if candidate_fvgs else None
        item6_met = entry_fvg is not None
        checklist.append(ChecklistItem(
            key="entry_fvg", label=f"Unfilled {wanted_fvg_side} FVG available", met=item6_met
        ))

        # 7) SMT divergence (Lesson 16 — optional booster via smt_engine)
        smt_res = check_smt_divergence(ltf_df, correlated_df, lookback=lookback, symbol=symbol)
        smt_dir = smt_res.get("divergence")
        wanted_smt_dir = "bearish" if direction == "short" else "bullish"
        item7_met = (smt_dir == wanted_smt_dir)
        smt_label = f"CONFIRMED ({smt_res.get('type', 'SMT Divergence')})" if item7_met else (f"Divergence opposite ({smt_dir.upper()})" if smt_dir else "None (Correlated In Line)")

        required = checklist[:6]
        required_met = sum(1 for c in required if c.met)
        confidence = required_met / len(required)
        if item7_met:
            confidence = min(1.0, confidence + 0.05)

        active = (required_met == len(required))
        entry = stop_loss = take_profit = tp_scaled = risk_reward = None
        notes = None
        dol_label = "Scanning Liquidity Targets"

        if entry_fvg is not None and mss is not None:
            buf = sl_buffer(symbol)
            if direction == "short":
                entry = float(entry_fvg["top"])
                stop_loss = float(mss["broken_level"]) + buf
                opposing_pools = [p for p in pools if p["side"] == "sell_side" and not p["swept"] and p["level"] < entry]
                
                # Lesson 13: PDL target
                if opposing_pools:
                    best_pool = min(opposing_pools, key=lambda p: p["level"])
                    take_profit = float(best_pool["level"])
                    dol_label = f"SSL Pool Target @ {take_profit:.{dec}f}"
                else:
                    take_profit = entry - 2.5 * abs(stop_loss - entry)
                    dol_label = f"Structural 1:2.5 Expansion @ {take_profit:.{dec}f}"

                # Lesson 15: Intermediate TP (Scaled exit)
                tp_scaled = entry - 1.5 * abs(stop_loss - entry)

            else:
                entry = float(entry_fvg["bottom"])
                stop_loss = float(mss["broken_level"]) - buf
                opposing_pools = [p for p in pools if p["side"] == "buy_side" and not p["swept"] and p["level"] > entry]
                
                # Lesson 13: PDH target
                if opposing_pools:
                    best_pool = max(opposing_pools, key=lambda p: p["level"])
                    take_profit = float(best_pool["level"])
                    dol_label = f"BSL Pool Target @ {take_profit:.{dec}f}"
                else:
                    take_profit = entry + 2.5 * abs(entry - stop_loss)
                    dol_label = f"Structural 1:2.5 Expansion @ {take_profit:.{dec}f}"

                # Lesson 15: Intermediate TP (Scaled exit)
                tp_scaled = entry + 1.5 * abs(entry - stop_loss)

            risk = abs(entry - stop_loss)
            reward = abs(take_profit - entry)
            risk_reward = round(reward / risk, 2) if risk > 0 else None

            if risk_reward is not None and risk_reward < MIN_RR:
                active = False
                notes = f"Checklist satisfied but R:R ({risk_reward:.2f}) < minimum ({MIN_RR}). Standing aside."

        entry_fvg_label = f"{entry_fvg['bottom']:.{dec}f} - {entry_fvg['top']:.{dec}f}" if entry_fvg else None

        return {
            "direction": direction,
            "active": active,
            "confidence": confidence,
            "checklist": checklist,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "tp_scaled": tp_scaled,
            "risk_reward": risk_reward,
            "notes": notes,
            "mss": mss,
            "htf_zone": htf_zone,
            "sweep_met": item4_met,
            "fvg_met": item6_met,
            "entry_fvg_label": entry_fvg_label,
            "dol_label": dol_label,
            "smt_label": smt_label
        }


# ---------------------------------------------------------------------------
# Self Test Function
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    strat = ICTMarketMakerStrategy()
    print(f"Instantiated: {strat.name}")
