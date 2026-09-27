"""
TraderPro SMT Engine (Smart Money Technique & SSMT Divergence)
Provides unified, swing-point & timestamp-tolerance SMT divergence analysis across
correlated equity index pairs (NAS100 vs SPX500, NQ vs MES).
"""

from typing import Dict, Any, List, Optional, Union
import pandas as pd
import datetime

# Documented Equity Index SMT Pairs (Never GOLD)
SMT_PAIRS: Dict[str, str] = {
    "NAS100": "SPX500",
    "NQ": "MES",
    "SPX500": "NAS100",
    "MES": "NQ",
}


def _to_clean_df(candles: Union[List[Dict[str, Any]], pd.DataFrame]) -> pd.DataFrame:
    """Converts a candle list or DataFrame into a timestamp-indexed DataFrame with swing points."""
    if isinstance(candles, pd.DataFrame):
        df = candles.copy()
        if not isinstance(df.index, pd.DatetimeIndex) and "timestamp" in df.columns:
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
            df.set_index("datetime", inplace=True)
        return df

    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles)
    if "timestamp" not in df.columns:
        return pd.DataFrame()

    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df.set_index("datetime", inplace=True)
    df.sort_index(inplace=True)
    return df


def _find_swings_df(df: pd.DataFrame, swing_length: int = 2) -> pd.DataFrame:
    """Identifies confirmed swing highs and lows."""
    if len(df) < (swing_length * 2 + 1):
        df["swing_high"] = False
        df["swing_low"] = False
        return df

    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    is_sh = [False] * n
    is_sl = [False] * n

    for i in range(swing_length, n - swing_length):
        h = highs[i]
        l = lows[i]
        if all(h >= highs[i - k] for k in range(1, swing_length + 1)) and all(h >= highs[i + k] for k in range(1, swing_length + 1)):
            is_sh[i] = True
        if all(l <= lows[i - k] for k in range(1, swing_length + 1)) and all(l <= lows[i + k] for k in range(1, swing_length + 1)):
            is_sl[i] = True

    df["swing_high"] = is_sh
    df["swing_low"] = is_sl
    return df


def check_smt_divergence(
    primary_candles: Union[List[Dict[str, Any]], pd.DataFrame],
    correlated_candles: Optional[Union[List[Dict[str, Any]], pd.DataFrame]] = None,
    symbol: str = "NAS100",
    correlated_symbol: Optional[str] = None,
    lookback_bars: int = 30,
    tolerance_bars: int = 3,
    timeframe_minutes: int = 1,
    lookback: Optional[int] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Detects confirmed Smart Money Technique (SMT) Divergence between correlated symbols.
    
    Rules:
    - Only equity index pairs (NAS100 <-> SPX500, NQ <-> MES).
    - Commodities like GOLD return detected=False immediately.
    - Uses confirmed swing highs and lows within timestamp tolerance.
    - Bullish SMT: One asset makes a Lower Low (sweeps liquidity) while the correlated asset
      fails to make a lower low (holds a Higher Low / institutional accumulation).
    - Bearish SMT: One asset makes a Higher High (sweeps liquidity) while the correlated asset
      fails to make a higher high (holds a Lower High / institutional distribution).
    """
    if lookback is not None:
        lookback_bars = lookback

    sym_upper = (symbol or "NAS100").upper()
    corr_sym = (correlated_symbol or SMT_PAIRS.get(sym_upper, "")).upper()

    if correlated_candles is None or not corr_sym or "GOLD" in sym_upper or "GOLD" in corr_sym:
        return {
            "detected": False,
            "type": "NONE",
            "direction": None,
            "divergence": None,
            "symbol": sym_upper,
            "correlated_symbol": corr_sym or "NONE",
            "label": "None (No SMT for Commodity)" if ("GOLD" in sym_upper or "GOLD" in corr_sym) else "None (Correlated In Line)",
            "details": {}
        }

    df_a = _to_clean_df(primary_candles)
    df_b = _to_clean_df(correlated_candles)

    if len(df_a) < 10 or len(df_b) < 10:
        return {
            "detected": False,
            "type": "NONE",
            "direction": None,
            "divergence": None,
            "symbol": sym_upper,
            "correlated_symbol": corr_sym,
            "label": "None (Awaiting SMT Bars)",
            "details": {}
        }

    # Ensure swing flags exist
    if "swing_high" not in df_a.columns or "swing_low" not in df_a.columns:
        df_a = _find_swings_df(df_a, swing_length=2)
    if "swing_high" not in df_b.columns or "swing_low" not in df_b.columns:
        df_b = _find_swings_df(df_b, swing_length=2)

    a_sub = df_a.tail(lookback_bars)
    tol = pd.Timedelta(minutes=tolerance_bars * max(1, timeframe_minutes))
    b_sub = df_b.tail(lookback_bars + tolerance_bars * 2)

    # 1. Check Bearish SMT Divergence (Highs)
    a_highs = a_sub[a_sub["swing_high"]]["high"]
    if len(a_highs) >= 2:
        curr_a_h = float(a_highs.iloc[-1])
        prev_a_h = float(a_highs.iloc[-2])
        ts_a = a_highs.index[-1]

        # Case 1: Primary makes Higher High, Correlated holds Lower High
        if curr_a_h > prev_a_h:
            b_window = b_sub[(b_sub.index >= ts_a - tol) & (b_sub.index <= ts_a + tol)]
            b_prior = b_sub[b_sub.index < (b_window.index.min() if not b_window.empty else ts_a)]["high"]
            if not b_window.empty and not b_prior.empty:
                b_prior_max = float(b_prior.max())
                b_window_max = float(b_window["high"].max())
                if b_window_max <= b_prior_max:
                    return {
                        "detected": True,
                        "type": "BEARISH",
                        "direction": "bearish",
                        "divergence": "bearish",
                        "symbol": sym_upper,
                        "correlated_symbol": corr_sym,
                        "label": f"CONFIRMED (Bearish SMT: {sym_upper} swept high {curr_a_h:.1f} vs {corr_sym} held {b_window_max:.1f} < {b_prior_max:.1f})",
                        "details": {
                            "primary_high": curr_a_h,
                            "primary_prior_high": prev_a_h,
                            "correlated_high": b_window_max,
                            "correlated_prior_high": b_prior_max,
                            "divergence": f"{sym_upper} Higher High vs {corr_sym} Lower High"
                        }
                    }

        # Case 2: Primary holds Lower High, Correlated makes Higher High
        elif curr_a_h < prev_a_h:
            b_window = b_sub[(b_sub.index >= ts_a - tol) & (b_sub.index <= ts_a + tol)]
            b_prior = b_sub[b_sub.index < (b_window.index.min() if not b_window.empty else ts_a)]["high"]
            if not b_window.empty and not b_prior.empty:
                b_prior_max = float(b_prior.max())
                b_window_max = float(b_window["high"].max())
                if b_window_max > b_prior_max:
                    return {
                        "detected": True,
                        "type": "BEARISH",
                        "direction": "bearish",
                        "divergence": "bearish",
                        "symbol": sym_upper,
                        "correlated_symbol": corr_sym,
                        "label": f"CONFIRMED (Bearish SMT: {sym_upper} held lower high {curr_a_h:.1f} vs {corr_sym} swept {b_window_max:.1f} > {b_prior_max:.1f})",
                        "details": {
                            "primary_high": curr_a_h,
                            "primary_prior_high": prev_a_h,
                            "correlated_high": b_window_max,
                            "correlated_prior_high": b_prior_max,
                            "divergence": f"{sym_upper} Lower High vs {corr_sym} Higher High"
                        }
                    }

    # 2. Check Bullish SMT Divergence (Lows)
    a_lows = a_sub[a_sub["swing_low"]]["low"]
    if len(a_lows) >= 2:
        curr_a_l = float(a_lows.iloc[-1])
        prev_a_l = float(a_lows.iloc[-2])
        ts_a = a_lows.index[-1]

        # Case 1: Primary makes Lower Low, Correlated holds Higher Low
        if curr_a_l < prev_a_l:
            b_window = b_sub[(b_sub.index >= ts_a - tol) & (b_sub.index <= ts_a + tol)]
            b_prior = b_sub[b_sub.index < (b_window.index.min() if not b_window.empty else ts_a)]["low"]
            if not b_window.empty and not b_prior.empty:
                b_prior_min = float(b_prior.min())
                b_window_min = float(b_window["low"].min())
                if b_window_min >= b_prior_min:
                    return {
                        "detected": True,
                        "type": "BULLISH",
                        "direction": "bullish",
                        "divergence": "bullish",
                        "symbol": sym_upper,
                        "correlated_symbol": corr_sym,
                        "label": f"CONFIRMED (Bullish SMT: {sym_upper} swept low {curr_a_l:.1f} vs {corr_sym} held {b_window_min:.1f} >= {b_prior_min:.1f})",
                        "details": {
                            "primary_low": curr_a_l,
                            "primary_prior_low": prev_a_l,
                            "correlated_low": b_window_min,
                            "correlated_prior_low": b_prior_min,
                            "divergence": f"{sym_upper} Lower Low vs {corr_sym} Higher Low"
                        }
                    }

        # Case 2: Primary holds Higher Low, Correlated makes Lower Low
        elif curr_a_l > prev_a_l:
            b_window = b_sub[(b_sub.index >= ts_a - tol) & (b_sub.index <= ts_a + tol)]
            b_prior = b_sub[b_sub.index < (b_window.index.min() if not b_window.empty else ts_a)]["low"]
            if not b_window.empty and not b_prior.empty:
                b_prior_min = float(b_prior.min())
                b_window_min = float(b_window["low"].min())
                if b_window_min < b_prior_min:
                    return {
                        "detected": True,
                        "type": "BULLISH",
                        "direction": "bullish",
                        "divergence": "bullish",
                        "symbol": sym_upper,
                        "correlated_symbol": corr_sym,
                        "label": f"CONFIRMED (Bullish SMT: {sym_upper} held {curr_a_l:.1f} vs {corr_sym} swept low {b_window_min:.1f} < {b_prior_min:.1f})",
                        "details": {
                            "primary_low": curr_a_l,
                            "primary_prior_low": prev_a_l,
                            "correlated_low": b_window_min,
                            "correlated_prior_low": b_prior_min,
                            "divergence": f"{sym_upper} Higher Low vs {corr_sym} Lower Low"
                        }
                    }

    return {
        "detected": False,
        "type": "NONE",
        "direction": None,
        "divergence": None,
        "symbol": sym_upper,
        "correlated_symbol": corr_sym,
        "label": f"None ({sym_upper} vs {corr_sym} In Line)",
        "details": {}
    }


def check_ssmt_divergence(
    primary_candles: Union[List[Dict[str, Any]], pd.DataFrame],
    correlated_candles: Union[List[Dict[str, Any]], pd.DataFrame],
    symbol: str,
    quarter_name: str = "",
    correlated_symbol: Optional[str] = None
) -> Dict[str, Any]:
    """
    Quarterly Theory SSMT (90-Minute Cycle) Divergence Check.
    Checks SMT divergence on 5m or 15m candles specifically formed at quarter cycle boundaries.
    """
    base_smt = check_smt_divergence(
        primary_candles,
        correlated_candles,
        symbol=symbol,
        correlated_symbol=correlated_symbol,
        lookback_bars=24,
        tolerance_bars=2,
        timeframe_minutes=5
    )

    if base_smt["detected"]:
        base_smt["label"] = f"CONFIRMED SSMT ({base_smt['type']} at {quarter_name or 'Quarter Boundary'})"
        return base_smt

    return {
        "detected": False,
        "type": "NONE",
        "direction": None,
        "symbol": symbol.upper(),
        "correlated_symbol": base_smt.get("correlated_symbol", "NONE"),
        "label": f"None ({quarter_name or 'Quarter Boundary'})",
        "details": {}
    }
