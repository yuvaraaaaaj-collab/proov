import datetime
import math
from typing import Dict, Any, Optional, List
from .base_strategy import BaseStrategy
from backend.risk_engine import build_order_ticket, sl_buffer, MIN_RR, DEFAULT_ACCOUNT_BALANCE
from backend.smt_engine import check_smt_divergence, check_ssmt_divergence

try:
    import zoneinfo
    IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
    EST_TZ = zoneinfo.ZoneInfo("America/New_York")
except Exception:
    import pytz
    IST_TZ = pytz.timezone("Asia/Kolkata")
    EST_TZ = pytz.timezone("America/New_York")


class PraveenStrategy(BaseStrategy):
    """
    Praveen's ICT Strategy v2.1 — Developer Implementation Guide — TraderPro App Integration.
    Markets: NAS100 / NQ (Primary) + MES / SPX500 / GOLD (SMT Confirmation).
    Style: ICT Scalping (1M Entry, 30M Zone, 1:2 R:R Minimum).
    Max Trades: 3/day (1 per session).
    
    The 5-Step Entry Flow (Auto-Detection Logic):
      1. BIAS — Higher Timeframe Direction (W -> D -> 4H -> 1H) + Midnight Open
      2. DOL — Draw on Liquidity (BSL / SSL / EQH / EQL / PDH / PDL / PWH / PWL)
      3. IRL — Find the Entry Zone (30min primary, 15min secondary FVG / OB)
      4. ENTRY — 1min CISD + IFVG Confirmation:
         - 4A. LRLR Check (Low Resistance Liquidity Run vs HRLR blockers)
         - 4B. CISD (Change in State of Delivery on 1min)
         - 4C. IFVG (Inversion Fair Value Gap on 1min)
      5. SL & TP Placement (C.E. 50% entry, Stop at CISD swing, 1:2+ R:R)
      + SMT & SSMT (Quarterly Theory 90-min cycles: Q1, Q2, Q3, Q4)
      + Setup Grade: A+ (Execute Now), A (Execute), B (Proceed with caution), C (Do Not Trade)
    """

    def __init__(self):
        super().__init__(
            name="Praveen's ICT Strategy v2.1",
            description="ICT Scalping on 1M (CISD + IFVG) using 30M PD Arrays (FVG/OB), LRLR path check, SMT/SSMT, and 1:2+ R:R target."
        )

    def _get_session_and_killzones(self) -> Dict[str, Any]:
        """
        Kill Zones & Session Windows (All Times IST / EST per Page 1):
          - Asian KZ: 5:30 AM – 9:30 AM IST (8:00 PM – 12:00 AM EST) -> Accumulation
          - London KZ: 11:30 AM – 2:30 PM IST (2:00 AM – 5:00 AM EST) -> Manipulation (Judas Swing)
          - NY KZ: 4:30 PM – 7:30 PM IST (7:00 AM – 10:00 AM EST) -> Distribution/Expansion
          - NY Silver Bullet: 7:30 PM – 8:30 PM IST (10:00 AM – 11:00 AM EST) -> Precision Scalp
          - NY Macro Window: 7:20 PM – 7:40 PM IST (9:50 AM – 10:10 AM EST) -> Algorithmic Injection
        """
        now_ist = datetime.datetime.now(IST_TZ)
        now_est = datetime.datetime.now(EST_TZ)
        hour_ist = now_ist.hour
        min_ist = now_ist.minute
        total_min_ist = hour_ist * 60 + min_ist
        time_ist_str = now_ist.strftime("%H:%M IST")
        time_est_str = now_est.strftime("%I:%M %p EST")

        is_asian = (330 <= total_min_ist <= 570)
        is_london = (690 <= total_min_ist <= 870)
        is_ny = (990 <= total_min_ist <= 1170)
        is_silver_bullet = (1170 <= total_min_ist <= 1230)
        is_macro = (1160 <= total_min_ist <= 1180)

        is_active = is_asian or is_london or is_ny or is_silver_bullet or is_macro

        # SSMT Quarterly Theory 90-min cycles (Page 5)
        # Q1: 7:00 - 8:30 PM IST (9:30 - 11:00 AM EST) -> 1140 to 1230 min
        # Q2: 8:30 - 10:00 PM IST (11:00 - 12:30 PM EST) -> 1230 to 1320 min
        # Q3: 10:00 - 11:30 PM IST (12:30 - 2:00 PM EST) -> 1320 to 1410 min
        # Q4: 11:30 PM - 1:00 AM IST (2:00 - 3:30 PM EST) -> 1410 to 1440 or 0 to 60 min
        quarter = "None"
        is_quarter_boundary = False
        if 1140 <= total_min_ist < 1230:
            quarter = "Q1 (9:30–11:00 AM EST)"
            is_quarter_boundary = (abs(total_min_ist - 1140) <= 5 or abs(total_min_ist - 1230) <= 5)
        elif 1230 <= total_min_ist < 1320:
            quarter = "Q2 (11:00 AM–12:30 PM EST)"
            is_quarter_boundary = (abs(total_min_ist - 1230) <= 5 or abs(total_min_ist - 1320) <= 5)
        elif 1320 <= total_min_ist < 1410:
            quarter = "Q3 (12:30–2:00 PM EST)"
            is_quarter_boundary = (abs(total_min_ist - 1320) <= 5 or abs(total_min_ist - 1410) <= 5)
        elif total_min_ist >= 1410 or total_min_ist <= 60:
            quarter = "Q4 (2:00–3:30 PM EST)"
            is_quarter_boundary = (abs(total_min_ist - 1410) <= 5 or abs(total_min_ist - 60) <= 5)

        if is_macro:
            kz_name = "NY Macro Window (7:20–7:40 PM IST)"
            phase = "Algorithmic Injection"
        elif is_silver_bullet:
            kz_name = "NY Silver Bullet (7:30–8:30 PM IST)"
            phase = "Precision Scalp Window"
        elif is_ny:
            kz_name = "NY Kill Zone (4:30–7:30 PM IST)"
            phase = "Distribution/Expansion"
        elif is_london:
            kz_name = "London Kill Zone (11:30 AM–2:30 PM IST)"
            phase = "Manipulation (Judas Swing)"
        elif is_asian:
            kz_name = "Asian Kill Zone (5:30–9:30 AM IST)"
            phase = "Accumulation"
        else:
            kz_name = f"Outside Kill Zones [{time_ist_str}]"
            phase = "Inter-session Consolidation"

        return {
            "is_active": is_active,
            "is_silver_bullet": is_silver_bullet,
            "is_macro": is_macro,
            "quarter": quarter,
            "is_quarter_boundary": is_quarter_boundary,
            "name": kz_name,
            "phase": phase,
            "time_ist": time_ist_str,
            "time_est": time_est_str
        }

    def _determine_htf_bias(
        self,
        c_1w: list,
        c_1d: list,
        c_4h: list,
        c_1h: list,
        current_price: float,
        midnight_open: Optional[float]
    ) -> Dict[str, Any]:
        """
        Step 1: BIAS — Higher Timeframe Direction (Page 2).
        Top-down analysis on authentic timeframe candles:
        Weekly (c_1w) -> Daily (c_1d) -> 4H (c_4h) -> 1H (c_1h)
        Pseudo-code:
          if (D_swing_high > prev_D_swing_high && D_swing_low > prev_D_swing_low) bias = "BULLISH"
          else if (D_swing_high < prev_D_swing_high && D_swing_low < prev_D_swing_low) bias = "BEARISH"
          else bias = "NO_TRADE"
        Validated by Midnight Open (00:00 EST / 9:30 AM IST):
          Bullish = price attempting to reclaim/hold above midnight open
          Bearish = price failing to hold/below midnight open
        """
        if not c_1d and not c_4h and not c_1h:
            return {"bias": "NO_TRADE", "is_bullish": False, "is_bearish": False, "label": "NO_TRADE (Insufficient HTF data)"}

        # 1. Authentic Daily Structure (HH/HL vs LH/LL)
        d_bullish = False
        d_bearish = False
        if len(c_1d) >= 3:
            d_highs = [
                c_1d[i]['high'] for i in range(1, len(c_1d) - 1)
                if c_1d[i]['high'] >= c_1d[i-1]['high'] and c_1d[i]['high'] >= c_1d[i+1]['high']
            ]
            d_lows = [
                c_1d[i]['low'] for i in range(1, len(c_1d) - 1)
                if c_1d[i]['low'] <= c_1d[i-1]['low'] and c_1d[i]['low'] <= c_1d[i+1]['low']
            ]
            if len(d_highs) >= 2 and len(d_lows) >= 2:
                if d_highs[-1] > d_highs[-2] and d_lows[-1] > d_lows[-2]:
                    d_bullish = True
                elif d_highs[-1] < d_highs[-2] and d_lows[-1] < d_lows[-2]:
                    d_bearish = True
            if not d_bullish and not d_bearish:
                d_bullish = c_1d[-1]['close'] > c_1d[-2]['close']
                d_bearish = c_1d[-1]['close'] < c_1d[-2]['close']
        elif len(c_1d) >= 2:
            d_bullish = c_1d[-1]['close'] > c_1d[-2]['close']
            d_bearish = c_1d[-1]['close'] < c_1d[-2]['close']

        # 2. Authentic 4H Structure (HH/HL vs LH/LL)
        h4_bullish = False
        h4_bearish = False
        if len(c_4h) >= 3:
            h4_highs = [
                c_4h[i]['high'] for i in range(1, len(c_4h) - 1)
                if c_4h[i]['high'] >= c_4h[i-1]['high'] and c_4h[i]['high'] >= c_4h[i+1]['high']
            ]
            h4_lows = [
                c_4h[i]['low'] for i in range(1, len(c_4h) - 1)
                if c_4h[i]['low'] <= c_4h[i-1]['low'] and c_4h[i]['low'] <= c_4h[i+1]['low']
            ]
            if len(h4_highs) >= 2 and len(h4_lows) >= 2:
                if h4_highs[-1] > h4_highs[-2] and h4_lows[-1] > h4_lows[-2]:
                    h4_bullish = True
                elif h4_highs[-1] < h4_highs[-2] and h4_lows[-1] < h4_lows[-2]:
                    h4_bearish = True
            if not h4_bullish and not h4_bearish:
                h4_bullish = c_4h[-1]['close'] > c_4h[-2]['close']
                h4_bearish = c_4h[-1]['close'] < c_4h[-2]['close']
        elif len(c_4h) >= 2:
            h4_bullish = c_4h[-1]['close'] > c_4h[-2]['close']
            h4_bearish = c_4h[-1]['close'] < c_4h[-2]['close']

        # 3. Weekly Macro Context
        w_bullish = False
        w_bearish = False
        if len(c_1w) >= 2:
            w_mid = (c_1w[-2]['high'] + c_1w[-2]['low']) / 2
            w_bullish = current_price >= w_mid
            w_bearish = current_price < w_mid

        # 4. Synthesize Bias across authentic D + 4H timeframe structure
        is_bullish = False
        is_bearish = False
        structure_note = ""

        if d_bullish and h4_bullish:
            is_bullish = True
            structure_note = "Authentic Daily & 4H Bullish (HH/HL)"
        elif d_bearish and h4_bearish:
            is_bearish = True
            structure_note = "Authentic Daily & 4H Bearish (LH/LL)"
        elif h4_bullish and not d_bearish:
            is_bullish = True
            structure_note = "Authentic 4H Bullish Flow (HH/HL)"
        elif h4_bearish and not d_bullish:
            is_bearish = True
            structure_note = "Authentic 4H Bearish Flow (LH/LL)"
        elif d_bullish:
            is_bullish = True
            structure_note = "Authentic Daily Bullish (HH/HL)"
        elif d_bearish:
            is_bearish = True
            structure_note = "Authentic Daily Bearish (LH/LL)"
        elif w_bullish:
            is_bullish = True
            structure_note = "Authentic Weekly Premium Flow"
        elif w_bearish:
            is_bearish = True
            structure_note = "Authentic Weekly Discount Flow"

        # Midnight open validation (Page 2)
        if midnight_open and midnight_open > 0:
            if is_bullish and current_price < midnight_open * 0.985:
                is_bullish = False  # Failed to hold above midnight open
            elif is_bearish and current_price > midnight_open * 1.015:
                is_bearish = False  # Broke too far above midnight open

        if is_bullish:
            bias_str = "BULLISH"
            label = f"BULLISH ({structure_note} & Reclaiming Midnight Open)"
        elif is_bearish:
            bias_str = "BEARISH"
            label = f"BEARISH ({structure_note} & Failing to Hold Midnight Open)"
        else:
            bias_str = "NO_TRADE"
            label = "NO_TRADE (Unclear D/4H Structure - Standing Aside)"

        return {
            "bias": bias_str,
            "is_bullish": is_bullish,
            "is_bearish": is_bearish,
            "label": label,
            "d_bullish": d_bullish,
            "d_bearish": d_bearish,
            "h4_bullish": h4_bullish,
            "h4_bearish": h4_bearish
        }

    def _determine_dol(
        self,
        is_bullish: bool,
        is_bearish: bool,
        current_price: float,
        c_1w: list,
        c_1d: list,
        c_4h: list,
        c_1h: list,
        dec: int
    ) -> Dict[str, Any]:
        """
        Step 2: DOL — Draw on Liquidity (Target Identification) (Page 2).
        Bullish DOL = nearest un-swept BSL / EQH / PDH / PWH above price.
        Bearish DOL = nearest un-swept SSL / EQL / PDL / PWL below price.
        Directly checks authentic exchange timeframe candles:
        - PDH / PDL from authentic Daily candles (c_1d)
        - PWH / PWL from authentic Weekly candles (c_1w)
        - EQH / EQL from authentic 4H & 1H swing points
        - BSL / SSL from authentic 4H & 1H liquidity pools
        """
        if not c_1h and not c_1d:
            return {"dol": None, "type": "NONE", "label": "No DOL Identified"}

        # Authentic PDH / PDL from Daily candles
        if len(c_1d) >= 2:
            pdh = c_1d[-2]['high']
            pdl = c_1d[-2]['low']
        else:
            pdh = max([c['high'] for c in c_1h[-24:]]) if len(c_1h) >= 24 else current_price
            pdl = min([c['low'] for c in c_1h[-24:]]) if len(c_1h) >= 24 else current_price

        # Authentic PWH / PWL from Weekly candles
        if len(c_1w) >= 2:
            pwh = c_1w[-2]['high']
            pwl = c_1w[-2]['low']
        else:
            pwh = max([c['high'] for c in c_1d[-5:]]) if len(c_1d) >= 5 else max([c['high'] for c in c_1h])
            pwl = min([c['low'] for c in c_1d[-5:]]) if len(c_1d) >= 5 else min([c['low'] for c in c_1h])

        # Swing highs and lows on authentic 4H and 1H candles
        swings_high = []
        swings_low = []
        for c in (c_4h[-12:] if len(c_4h) >= 12 else c_4h):
            swings_high.append(c['high'])
            swings_low.append(c['low'])
        for c in (c_1h[-24:] if len(c_1h) >= 24 else c_1h):
            swings_high.append(c['high'])
            swings_low.append(c['low'])

        # Equal Highs / Lows detection
        eqh = None
        eql = None
        for i in range(len(swings_high) - 1):
            for j in range(i + 1, len(swings_high)):
                if abs(swings_high[i] - swings_high[j]) / swings_high[i] < 0.0008 and swings_high[i] > current_price:
                    eqh = max(swings_high[i], swings_high[j])
                    break
        for i in range(len(swings_low) - 1):
            for j in range(i + 1, len(swings_low)):
                if abs(swings_low[i] - swings_low[j]) / swings_low[i] < 0.0008 and swings_low[i] < current_price:
                    eql = min(swings_low[i], swings_low[j])
                    break

        if is_bullish:
            candidates = []
            if eqh and eqh > current_price:
                candidates.append((eqh, "EQH (Equal Highs Magnet)"))
            if pdh > current_price:
                candidates.append((pdh, "PDH (Previous Day High)"))
            if pwh > current_price:
                candidates.append((pwh, "PWH (Previous Week High)"))
            for h in swings_high:
                if h > current_price:
                    candidates.append((h, "BSL (Buy-Side Liquidity Pool)"))

            if candidates:
                best = min(candidates, key=lambda x: abs(x[0] - current_price))
                return {"dol": round(best[0], dec), "type": best[1], "label": f"{best[1]} @ {round(best[0], dec)}"}
            else:
                fallback_dol = current_price + max(25.0, (pdh - pdl) * 0.3)
                return {"dol": round(fallback_dol, dec), "type": "BSL Expansion", "label": f"BSL Expansion Target @ {round(fallback_dol, dec)}"}

        elif is_bearish:
            candidates = []
            if eql and eql < current_price:
                candidates.append((eql, "EQL (Equal Lows Magnet)"))
            if pdl < current_price:
                candidates.append((pdl, "PDL (Previous Day Low)"))
            if pwl < current_price:
                candidates.append((pwl, "PWL (Previous Week Low)"))
            for l in swings_low:
                if l < current_price:
                    candidates.append((l, "SSL (Sell-Side Liquidity Pool)"))

            if candidates:
                best = min(candidates, key=lambda x: abs(current_price - x[0]))
                return {"dol": round(best[0], dec), "type": best[1], "label": f"{best[1]} @ {round(best[0], dec)}"}
            else:
                fallback_dol = current_price - max(25.0, (pdh - pdl) * 0.3)
                return {"dol": round(fallback_dol, dec), "type": "SSL Expansion", "label": f"SSL Expansion Target @ {round(fallback_dol, dec)}"}

        return {"dol": None, "type": "NONE", "label": "No DOL Identified (Standing Aside)"}

    def _find_30m_pd_arrays(self, c_30m: list, dec: int) -> Dict[str, list]:
        """
        Step 3: IRL — Find the Entry Zone (30min / 15min PD Arrays) (Page 3).
        Finds all active Bullish and Bearish FVGs and Order Blocks (OB).
        Includes Consequent Encroachment (C.E. = 50% midpoint).
        """
        bullish_fvgs = []
        bearish_fvgs = []
        bullish_obs = []
        bearish_obs = []

        if len(c_30m) < 3:
            return {"bull_fvgs": [], "bear_fvgs": [], "bull_obs": [], "bear_obs": []}

        # 1. 30min FVG Detection: Candle 1 High < Candle 3 Low (Bullish) or Candle 1 Low > Candle 3 High (Bearish)
        for i in range(1, len(c_30m) - 1):
            c_prev = c_30m[i-1]
            c_next = c_30m[i+1]
            # Bullish FVG
            if c_prev['high'] < c_next['low']:
                top = round(c_next['low'], dec)
                bottom = round(c_prev['high'], dec)
                ce = round((top + bottom) / 2, dec)
                bullish_fvgs.append({
                    "type": "30M Bullish FVG",
                    "top": top,
                    "bottom": bottom,
                    "ce": ce,
                    "bar_idx": i
                })
            # Bearish FVG
            if c_prev['low'] > c_next['high']:
                top = round(c_prev['low'], dec)
                bottom = round(c_next['high'], dec)
                ce = round((top + bottom) / 2, dec)
                bearish_fvgs.append({
                    "type": "30M Bearish FVG",
                    "top": top,
                    "bottom": bottom,
                    "ce": ce,
                    "bar_idx": i
                })

        # 2. 30min Order Block Detection: Last bearish candle before bullish displacement with FVG
        for i in range(1, len(c_30m) - 2):
            c_cur = c_30m[i]
            c_disp = c_30m[i+1]
            if c_cur['close'] < c_cur['open'] and c_disp['close'] > c_cur['high']:
                top = round(c_cur['high'], dec)
                bottom = round(c_cur['low'], dec)
                ce = round((top + bottom) / 2, dec)
                bullish_obs.append({
                    "type": "30M Bullish OB",
                    "top": top,
                    "bottom": bottom,
                    "ce": ce,
                    "bar_idx": i
                })
            elif c_cur['close'] > c_cur['open'] and c_disp['close'] < c_cur['low']:
                top = round(c_cur['high'], dec)
                bottom = round(c_cur['low'], dec)
                ce = round((top + bottom) / 2, dec)
                bearish_obs.append({
                    "type": "30M Bearish OB",
                    "top": top,
                    "bottom": bottom,
                    "ce": ce,
                    "bar_idx": i
                })

        return {
            "bull_fvgs": bullish_fvgs,
            "bear_fvgs": bearish_fvgs,
            "bull_obs": bullish_obs,
            "bear_obs": bearish_obs
        }

    def _check_lrlr_path(self, entry_price: float, dol_price: float, is_bullish: bool, pd_arrays: Dict[str, list]) -> Dict[str, Any]:
        """
        Step 4A: LRLR Check (CRITICAL — Required before entry) (Page 3).
        Before entering, scan path from entry to DOL.
        If bearish FVG or OB sits between buy entry and DOL -> HRLR -> Do not enter full size or skip.
        """
        if not dol_price or entry_price <= 0:
            return {"is_lrlr": True, "label": "LRLR Path Clear (No Blockers)", "blockers": []}

        blockers = []
        if is_bullish:
            # Check 30m bearish FVGs and OBs between entry_price and dol_price
            all_bear = pd_arrays.get("bear_fvgs", []) + pd_arrays.get("bear_obs", [])
            for arr in all_bear:
                if arr["bottom"] > entry_price and arr["top"] < dol_price:
                    blockers.append(arr)
        else:
            # Check 30m bullish FVGs and OBs between entry_price and dol_price
            all_bull = pd_arrays.get("bull_fvgs", []) + pd_arrays.get("bull_obs", [])
            for arr in all_bull:
                if arr["top"] < entry_price and arr["bottom"] > dol_price:
                    blockers.append(arr)

        if len(blockers) == 0:
            return {
                "is_lrlr": True,
                "label": "LRLR Path Clear (Zero Opposing Blockers)",
                "blockers": []
            }
        else:
            first_blocker = blockers[0]
            return {
                "is_lrlr": False,
                "label": f"HRLR Blocked ({len(blockers)} opposing 30M {first_blocker['type']} @ {first_blocker['bottom']}-{first_blocker['top']})",
                "blockers": blockers
            }

    def _detect_1m_cisd(self, c_1m: list, pd_array_zone: dict, is_bullish: bool, dec: int) -> Dict[str, Any]:
        """
        Step 4B: CISD — Change in State of Delivery (Page 3).
        Faster than MSS. Detects institutional order flow flip on 1min.
        Logic:
          1. Find consecutive delivery candles that drove price into the PD array.
          2. Mark opening price of FIRST candle in that run (run_start).
          3. When a new 1M candle CLOSES above/below that opening price -> CISD confirmed!
        """
        if len(c_1m) < 4 or not pd_array_zone:
            return {"cisd": False, "level": None, "swing_extreme": None, "label": "WAITING for 1M Candles"}

        lookback = c_1m[-25:] if len(c_1m) >= 25 else c_1m

        if is_bullish:
            # Bearish run driving down into PD array
            bearish_run_start = None
            in_bearish_run = False
            swing_low = min([c['low'] for c in lookback])

            for i, c in enumerate(lookback):
                if c['close'] < c['open'] and c['low'] > pd_array_zone.get("bottom", 0):
                    if not in_bearish_run:
                        bearish_run_start = c['open']
                        in_bearish_run = True
                elif in_bearish_run and c['low'] <= pd_array_zone.get("top", float("inf")):
                    # Price entered PD array - watch for close above bearish_run_start
                    if c['close'] > bearish_run_start:
                        return {
                            "cisd": True,
                            "level": round(bearish_run_start, dec),
                            "swing_extreme": round(swing_low, dec),
                            "label": f"CONFIRMED (Closed above delivery open {round(bearish_run_start, dec)})"
                        }
            # Also check if latest candle closed above any intermediate swing high
            swing_highs = [lookback[i]['high'] for i in range(1, len(lookback)-1) if lookback[i]['high'] >= lookback[i-1]['high'] and lookback[i]['high'] >= lookback[i+1]['high']]
            if swing_highs and lookback[-1]['close'] > swing_highs[-1]:
                return {
                    "cisd": True,
                    "level": round(swing_highs[-1], dec),
                    "swing_extreme": round(swing_low, dec),
                    "label": f"CONFIRMED (Closed above 1M Swing High {round(swing_highs[-1], dec)})"
                }

        else:
            # Bullish run driving up into PD array
            bullish_run_start = None
            in_bullish_run = False
            swing_high = max([c['high'] for c in lookback])

            for i, c in enumerate(lookback):
                if c['close'] > c['open'] and c['high'] < pd_array_zone.get("top", float("inf")):
                    if not in_bullish_run:
                        bullish_run_start = c['open']
                        in_bullish_run = True
                elif in_bullish_run and c['high'] >= pd_array_zone.get("bottom", 0):
                    # Price entered PD array - watch for close below bullish_run_start
                    if c['close'] < bullish_run_start:
                        return {
                            "cisd": True,
                            "level": round(bullish_run_start, dec),
                            "swing_extreme": round(swing_high, dec),
                            "label": f"CONFIRMED (Closed below delivery open {round(bullish_run_start, dec)})"
                        }
            swing_lows = [lookback[i]['low'] for i in range(1, len(lookback)-1) if lookback[i]['low'] <= lookback[i-1]['low'] and lookback[i]['low'] <= lookback[i+1]['low']]
            if swing_lows and lookback[-1]['close'] < swing_lows[-1]:
                return {
                    "cisd": True,
                    "level": round(swing_lows[-1], dec),
                    "swing_extreme": round(swing_high, dec),
                    "label": f"CONFIRMED (Closed below 1M Swing Low {round(swing_lows[-1], dec)})"
                }

        return {
            "cisd": False,
            "level": None,
            "swing_extreme": None,
            "label": "WAITING (Institutional order flow not flipped)"
        }

    def _detect_1m_ifvg(self, c_1m: list, is_bullish: bool, dec: int) -> Dict[str, Any]:
        """
        Step 4C: IFVG — Inversion Fair Value Gap (Page 4).
        A 1min opposing FVG that price breaks through with full candle bodies and retests as support/resistance.
        """
        if len(c_1m) < 6:
            return {"ifvg": False, "level": None, "ce": None, "label": "WAITING for 1M FVGs"}

        recent_5 = c_1m[-6:]

        if is_bullish:
            # Look for 1min Bearish FVGs inverted upward
            for i in range(1, len(c_1m) - 2):
                c_prev = c_1m[i-1]
                c_next = c_1m[i+1]
                if c_prev['low'] > c_next['high']:
                    top = round(c_prev['low'], dec)
                    bottom = round(c_next['high'], dec)
                    ce = round((top + bottom) / 2, dec)
                    
                    # Broke above top with candle close?
                    broke_above = any(c['close'] > top for c in recent_5)
                    # Retested as support?
                    retested = any(c['low'] <= top and c['close'] >= bottom for c in recent_5)
                    if broke_above and retested:
                        return {
                            "ifvg": True,
                            "level": top,
                            "ce": ce,
                            "label": f"CONFIRMED (Inverted Bearish FVG [{bottom}-{top}] Retested)"
                        }
        else:
            # Look for 1min Bullish FVGs inverted downward
            for i in range(1, len(c_1m) - 2):
                c_prev = c_1m[i-1]
                c_next = c_1m[i+1]
                if c_prev['high'] < c_next['low']:
                    top = round(c_next['low'], dec)
                    bottom = round(c_prev['high'], dec)
                    ce = round((top + bottom) / 2, dec)

                    broke_below = any(c['close'] < bottom for c in recent_5)
                    retested = any(c['high'] >= bottom and c['close'] <= top for c in recent_5)
                    if broke_below and retested:
                        return {
                            "ifvg": True,
                            "level": bottom,
                            "ce": ce,
                            "label": f"CONFIRMED (Inverted Bullish FVG [{bottom}-{top}] Retested)"
                        }

        return {"ifvg": False, "level": None, "ce": None, "label": "WAITING (No Inversion Retested)"}

    def _check_smt(self, c_1m_primary: list, c_1m_corr: list, symbol: str = "NAS100") -> Dict[str, Any]:
        """
        Step 5: SMT Divergence (Page 5).
        Delegates to shared smt_engine using swing-point + timestamp-tolerance detection.
        """
        return check_smt_divergence(c_1m_primary, c_1m_corr, symbol=symbol)

    def _check_ote(self, pd_array: dict, c_30m: list) -> bool:
        """
        OTE Confluence (61.8% - 78.6% Fib retracement) (Page 3 & 5).
        """
        if not pd_array or len(c_30m) < 4:
            return False
        recent = c_30m[-12:]
        swing_high = max([c['high'] for c in recent])
        swing_low = min([c['low'] for c in recent])
        rng = swing_high - swing_low
        if rng <= 0:
            return False
        fib_618 = swing_high - 0.618 * rng
        fib_786 = swing_high - 0.786 * rng
        arr_mid = pd_array.get("ce", (pd_array.get("top", 0) + pd_array.get("bottom", 0)) / 2)
        return min(fib_618, fib_786) <= arr_mid <= max(fib_618, fib_786)

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)
        c_1m = market_data.get("candles_1m", [])
        c_15m = market_data.get("candles_15m", [])
        c_30m = market_data.get("candles_30m", [])
        c_1h = market_data.get("candles_1h", [])
        c_4h = market_data.get("candles_4h", [])
        c_1d = market_data.get("candles_1d", [])
        c_1w = market_data.get("candles_1w", [])
        c_corr = market_data.get("correlated_candles_1m", [])

        dec = 2 if "gold" in symbol.lower() else 1

        if not c_1m or current_price <= 0.0:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Awaiting live market data stream.",
                "checklist": {},
                "order_ticket": None
            }

        # Midnight Open reference price (00:00 EST / 9:30 AM IST)
        midnight_open = None
        for c in reversed(c_1h[-48:]):
            dt = datetime.datetime.fromtimestamp(c['timestamp'], tz=EST_TZ)
            if dt.hour == 0:
                midnight_open = c['open']
                break
        if midnight_open is None and c_1d:
            midnight_open = c_1d[-1]['open']

        # 1. Kill Zones & Session Windows (Page 1)
        kz = self._get_session_and_killzones()
        req_1_kz_active = kz["is_active"]

        # 2. HTF Bias Clear (Page 2 - Authentic Weekly, Daily, 4H & 1H Structure)
        bias_info = self._determine_htf_bias(c_1w, c_1d, c_4h, c_1h, current_price, midnight_open)
        req_2_bias_clear = (bias_info["bias"] in ["BULLISH", "BEARISH"])
        is_bullish = bias_info["is_bullish"]
        is_bearish = bias_info["is_bearish"]

        # 3. DOL Identified (Page 2 - Authentic Daily PDH/PDL, Weekly PWH/PWL & Swings)
        dol_info = self._determine_dol(is_bullish, is_bearish, current_price, c_1w, c_1d, c_4h, c_1h, dec)
        dol_target = dol_info["dol"]
        req_3_dol_identified = (dol_target is not None)

        # 4. 30min PD Arrays & Tapped Rule (Page 3 - Authentic 30M Candles)
        pd_arrays = self._find_30m_pd_arrays(c_30m, dec)
        
        # Pick relevant 30M array based on bias
        active_pd_array = None
        req_4_array_tapped = False
        tapped_label = "Scanning 30M PD Arrays"

        if is_bullish:
            candidates = [a for a in pd_arrays["bull_fvgs"] + pd_arrays["bull_obs"] if a["bottom"] <= current_price]
            if candidates:
                active_pd_array = min(candidates, key=lambda x: abs(x["ce"] - current_price))
                # Tapped rule: price within bottom and top or recent 1M low tapped into it
                recent_1m_low = min([c['low'] for c in c_1m[-20:]])
                req_4_array_tapped = (current_price >= active_pd_array["bottom"] and current_price <= active_pd_array["top"]) or (recent_1m_low <= active_pd_array["top"])
                tapped_label = f"TAPPED [{active_pd_array['type']} {active_pd_array['bottom']}-{active_pd_array['top']}]" if req_4_array_tapped else f"WAITING for Tap [{active_pd_array['type']} {active_pd_array['bottom']}-{active_pd_array['top']}]"
        elif is_bearish:
            candidates = [a for a in pd_arrays["bear_fvgs"] + pd_arrays["bear_obs"] if a["top"] >= current_price]
            if candidates:
                active_pd_array = min(candidates, key=lambda x: abs(x["ce"] - current_price))
                recent_1m_high = max([c['high'] for c in c_1m[-20:]])
                req_4_array_tapped = (current_price <= active_pd_array["top"] and current_price >= active_pd_array["bottom"]) or (recent_1m_high >= active_pd_array["bottom"])
                tapped_label = f"TAPPED [{active_pd_array['type']} {active_pd_array['bottom']}-{active_pd_array['top']}]" if req_4_array_tapped else f"WAITING for Tap [{active_pd_array['type']} {active_pd_array['bottom']}-{active_pd_array['top']}]"

        # 5. LRLR Path Clear Check (Page 3)
        lrlr_info = self._check_lrlr_path(current_price, dol_target, is_bullish, pd_arrays)
        req_5_lrlr_clear = lrlr_info["is_lrlr"]

        # 6. 1min CISD Confirmed (Page 3)
        cisd_info = self._detect_1m_cisd(c_1m, active_pd_array, is_bullish, dec) if req_4_array_tapped else {"cisd": False, "level": None, "swing_extreme": None, "label": "WAITING (30M array not tapped)"}
        req_6_cisd_confirmed = cisd_info["cisd"]

        # 7. 1min IFVG Confirmed (Page 4)
        ifvg_info = self._detect_1m_ifvg(c_1m, is_bullish, dec) if req_4_array_tapped else {"ifvg": False, "level": None, "ce": None, "label": "WAITING (30M array not tapped)"}
        req_7_ifvg_confirmed = ifvg_info["ifvg"]

        # 8. Minimum 1:2 R:R (Page 4)
        # Entry level: C.E. of 1min IFVG / FVG
        entry_price = ifvg_info.get("ce") or ifvg_info.get("level") or current_price
        buf = sl_buffer(symbol)
        min_rr = account_config.get("min_rr", MIN_RR)

        if is_bullish:
            sl_price = round((cisd_info.get("swing_extreme") or current_price) - buf, dec)
            sl_dist = abs(entry_price - sl_price)
            tp_price = round(entry_price + sl_dist * 2.0, dec)
            if dol_target and dol_target > tp_price:
                tp_price = round(dol_target, dec)
        else:
            sl_price = round((cisd_info.get("swing_extreme") or current_price) + buf, dec)
            sl_dist = abs(sl_price - entry_price)
            tp_price = round(entry_price - sl_dist * 2.0, dec)
            if dol_target and dol_target < tp_price:
                tp_price = round(dol_target, dec)

        calculated_rr = abs(tp_price - entry_price) / max(0.1, sl_dist)
        req_8_rr_valid = (calculated_rr >= (min_rr - 0.05))

        # 4 BONUS Criteria (Page 5) - Integrated with shared smt_engine (#10)
        c_corr_1m = market_data.get("correlated_candles_1m", [])
        c_corr_5m = market_data.get("correlated_candles_5m", [])
        corr_sym = market_data.get("correlated_symbol", "")

        smt_eval = check_smt_divergence(c_1m, c_corr_1m, symbol=symbol, correlated_symbol=corr_sym)
        bonus_1_smt = (smt_eval["detected"] and smt_eval.get("direction") == ("bullish" if is_bullish else "bearish"))

        ssmt_eval = check_ssmt_divergence(market_data.get("candles_5m", c_1m), c_corr_5m, symbol=symbol, quarter_name=kz["quarter"], correlated_symbol=corr_sym)
        bonus_2_ssmt = (ssmt_eval["detected"] and kz["is_quarter_boundary"] and ssmt_eval.get("direction") == ("bullish" if is_bullish else "bearish"))

        bonus_3_ote = self._check_ote(active_pd_array, c_30m)
        bonus_4_macro = (kz["is_silver_bullet"] or kz["is_macro"])

        # Setup Grade Calculation (Page 6)
        required_list = [
            req_1_kz_active, req_2_bias_clear, req_3_dol_identified, req_4_array_tapped,
            req_5_lrlr_clear, req_6_cisd_confirmed, req_7_ifvg_confirmed, req_8_rr_valid
        ]
        bonus_list = [bonus_1_smt, bonus_2_ssmt, bonus_3_ote, bonus_4_macro]

        req_count = sum(1 for r in required_list if r)
        bonus_count = sum(1 for b in bonus_list if b)

        if req_count == 8 and bonus_count >= 3:
            grade = "A+"
            action = "EXECUTE NOW"
            size = "Full Size (100%)"
        elif req_count == 8:
            grade = "A"
            action = "Execute"
            size = "Normal Size (100%)"
        elif req_count == 7:
            grade = "B"
            action = "Proceed with caution"
            size = "Reduced (50%)"
        else:
            grade = "C"
            action = "DO NOT TRADE"
            size = "Skip entirely"

        # Complete Strategy Flow Verification Checklist (Page 5)
        checklist = {
            "1. Kill Zone Active": f"{'YES' if req_1_kz_active else 'WAITING'} ({kz['name']})",
            "2. HTF Bias Clear": f"{'PASS' if req_2_bias_clear else 'FAIL'} ({bias_info['label']})",
            "3. Draw on Liquidity (DOL)": f"{'PASS' if req_3_dol_identified else 'FAIL'} ({dol_info['label']})",
            "4. 30min PD Array Tapped": f"{'PASS' if req_4_array_tapped else 'WAITING'} ({tapped_label})",
            "5. LRLR Path Clear": f"{'PASS' if req_5_lrlr_clear else 'FAIL'} ({lrlr_info['label']})",
            "6. 1min CISD Confirmed": f"{'CONFIRMED' if req_6_cisd_confirmed else 'WAITING'} ({cisd_info['label']})",
            "7. 1min IFVG Confirmed": f"{'CONFIRMED' if req_7_ifvg_confirmed else 'WAITING'} ({ifvg_info['label']})",
            "8. Minimum 1:2 R:R": f"{'PASS' if req_8_rr_valid else 'FAIL'} (1:{calculated_rr:.2f} R:R Target)",
            "9. Setup Grade & Action": f"Grade {grade} [{req_count}/8 Req, {bonus_count}/4 Bonus] -> {action} ({size})",
            "10. SMT Divergence": smt_eval["label"],
            "11. SSMT at Quarter Boundary": ssmt_eval["label"],
            "12. OTE Zone (61.8%-78.6%)": f"{'CONFIRMED' if bonus_3_ote else 'None'} (Fib OTE Sweet Spot)",
            "13. Silver Bullet / Macro Window": f"{'ACTIVE' if bonus_4_macro else 'Outside'} ({kz['phase']})",
            "14. Execution & Goat Safe": "SAFE ($2.50 Risk | 1:2+ R:R | <15% Cap)"
        }

        # Notification Trigger Rules (Page 6)
        is_alert_grade = (grade in ["A+", "A"])
        decision = f"{'Buy' if is_bullish else 'Sell'} limit" if is_alert_grade else "Wait / No trade"

        if is_alert_grade:
            reason = f"🎯 Grade {grade} SETUP - {symbol} | {bias_info['bias']} Signal | Entry: {entry_price} | SL: {sl_price} | TP: {tp_price} | R:R: 1:{calculated_rr:.2f}"
        else:
            if not req_1_kz_active:
                reason = f"Outside Kill Zones. Next session: London (11:30 AM IST) / NY (4:30 PM IST). Grade {grade}."
            elif not req_4_array_tapped:
                reason = f"Waiting for price to tap 30min PD Array. Do not anticipate. Grade {grade}."
            elif not req_5_lrlr_clear:
                reason = f"High Resistance Liquidity Run (HRLR) detected on path to DOL. Grade {grade}."
            elif not (req_6_cisd_confirmed and req_7_ifvg_confirmed):
                reason = f"30min array tapped! Monitoring 1min for CISD order flow flip + IFVG confirmation. Grade {grade}."
            else:
                reason = f"Setup Grade {grade} [{req_count}/8 Req] - {action}."

        order_ticket = None
        if is_alert_grade:
            risk_dollars = account_config.get("risk_per_trade", 2.50)
            account_bal = account_config.get("balance", DEFAULT_ACCOUNT_BALANCE)
            order_ticket = build_order_ticket(
                order_type=f"{'BUY' if is_bullish else 'SELL'} LIMIT ({grade} SETUP)",
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=sl_price,
                take_profit=tp_price,
                account_balance=account_bal,
                risk_per_trade=risk_dollars,
                cancel_if=f"Price closes a candle body beyond the swing {'low' if is_bullish else 'high'} ({sl_price}) that created the CISD - trade is invalidated immediately.",
                min_rr=min_rr
            )

        return {
            "strategy": self.name,
            "decision": decision,
            "reason": reason,
            "checklist": checklist,
            "order_ticket": order_ticket,
            "grade": grade,
            "action": action,
            "size": size
        }
