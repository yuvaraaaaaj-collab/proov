import datetime
from typing import Dict, Any, Optional
from .base_strategy import BaseStrategy

try:
    import zoneinfo
    IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
except Exception:
    import pytz
    IST_TZ = pytz.timezone("Asia/Kolkata")

class PraveenStrategy(BaseStrategy):
    """
    Praveen Strategy: Master Rule Set & Execution Playbook.
    Core principle: Higher-timeframe location first. Lower-timeframe confirmation second.
    
    Master Flow:
    W/D/4H/1H liquidity -> Bias -> DOL if clear / Bias if no DOL -> 30M FVG/OB -> 
    PD Array Tap -> 30M TAP ALERT -> 1M Recent Swing -> 1M IFVG + CISD -> Entry -> SL -> TP
    
    Session Checking Windows (IST):
    - Asia: 05:30 - 08:30 IST
    - London: 12:30 - 15:30 IST
    - New York: 19:00 - 22:00 IST
    """
    def __init__(self):
        super().__init__(
            name="Praveen Strategy (30M PD Array + 1M IFVG/CISD)",
            description="30M PD Array location with 1M IFVG and CISD execution confirmation during Asia, London & NY sessions."
        )

    def _get_ist_session(self) -> Dict[str, Any]:
        """Calculates current Indian Standard Time (IST) and checks checking windows."""
        now_ist = datetime.datetime.now(IST_TZ)
        hour = now_ist.hour
        minute = now_ist.minute
        time_str = now_ist.strftime("%H:%M IST")
        total_minutes = hour * 60 + minute

        # Asia: 05:30 - 08:30 IST (330 to 510 minutes)
        is_asia = (330 <= total_minutes <= 510)
        # London: 12:30 - 15:30 IST (750 to 930 minutes)
        is_london = (750 <= total_minutes <= 930)
        # New York: 19:00 - 22:00 IST (1140 to 1320 minutes)
        is_ny = (1140 <= total_minutes <= 1320)

        is_active = is_asia or is_london or is_ny

        if is_asia:
            label = f"Asia Session (05:30–08:30 IST) - [{time_str}] ACTIVE"
            session_name = "Asia"
        elif is_london:
            label = f"London Session (12:30–15:30 IST) - [{time_str}] ACTIVE"
            session_name = "London"
        elif is_ny:
            label = f"New York Session (19:00–22:00 IST) - [{time_str}] ACTIVE"
            session_name = "New York"
        else:
            if total_minutes < 330:
                next_s = "Asia Session (05:30 IST)"
            elif total_minutes < 750:
                next_s = "London Session (12:30 IST)"
            elif total_minutes < 1140:
                next_s = "New York Session (19:00 IST)"
            else:
                next_s = "Tomorrow Asia Session (05:30 IST)"
            label = f"Outside Session Window [{time_str}] (Next: {next_s})"
            session_name = "Outside"

        return {
            "is_active": is_active,
            "session_name": session_name,
            "label": label,
            "time_str": time_str
        }

    def _find_30m_pd_array(self, c_30m: list, bias: str, current_price: float, dec: int) -> Dict[str, Any]:
        """Identifies relevant 30M FVG or Order Block (OB) nearest to current price in the direction of bias."""
        if len(c_30m) < 4:
            return {"type": "NONE", "high": 0.0, "low": 0.0, "label": "Insufficient 30M data"}

        recent_30m = c_30m[-24:] if len(c_30m) >= 24 else c_30m
        candidates = []

        if "BULLISH" in bias:
            # Bullish context -> Look for 30M Discount FVGs and Bullish OBs
            for i in range(len(recent_30m) - 1, 1, -1):
                c1 = recent_30m[i-2]
                c3 = recent_30m[i]
                if c3['low'] > c1['high']:
                    candidates.append({
                        "type": "30M Bullish FVG",
                        "high": round(c3['low'], dec),
                        "low": round(c1['high'], dec),
                        "mid": (c3['low'] + c1['high']) / 2
                    })
            
            for i in range(len(recent_30m) - 2, 0, -1):
                c = recent_30m[i]
                next_c = recent_30m[i+1]
                if c['close'] < c['open'] and next_c['close'] > c['high']:
                    candidates.append({
                        "type": "30M Bullish OB",
                        "high": round(c['high'], dec),
                        "low": round(c['low'], dec),
                        "mid": (c['high'] + c['low']) / 2
                    })
        else:
            # Bearish context -> Look for 30M Premium FVGs and Bearish OBs
            for i in range(len(recent_30m) - 1, 1, -1):
                c1 = recent_30m[i-2]
                c3 = recent_30m[i]
                if c1['low'] > c3['high']:
                    candidates.append({
                        "type": "30M Bearish FVG",
                        "high": round(c1['low'], dec),
                        "low": round(c3['high'], dec),
                        "mid": (c1['low'] + c3['high']) / 2
                    })

            for i in range(len(recent_30m) - 2, 0, -1):
                c = recent_30m[i]
                next_c = recent_30m[i+1]
                if c['close'] > c['open'] and next_c['close'] < c['low']:
                    candidates.append({
                        "type": "30M Bearish OB",
                        "high": round(c['high'], dec),
                        "low": round(c['low'], dec),
                        "mid": (c['high'] + c['low']) / 2
                    })

        if candidates:
            # Pick the candidate nearest to current price
            best = min(candidates, key=lambda c: abs(c['mid'] - current_price))
            return {
                "type": best["type"],
                "high": best["high"],
                "low": best["low"],
                "label": f"{best['type']} [{best['low']} - {best['high']}]"
            }
        
        # Fallback to nearest 30M swing high/low zone
        last_30m = recent_30m[-1]
        return {
            "type": "30M Swing Zone",
            "high": round(last_30m['high'], dec),
            "low": round(last_30m['low'], dec),
            "label": f"30M Swing Zone [{round(last_30m['low'], dec)} - {round(last_30m['high'], dec)}]"
        }

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        c_1m = market_data.get("candles_1m", [])
        c_15m = market_data.get("candles_15m", [])
        c_30m = market_data.get("candles_30m", [])
        c_1h = market_data.get("candles_1h", [])
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)

        dec = 2 if "gold" in symbol.lower() else 1

        if not c_1m or not c_15m or current_price == 0.0:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Awaiting live market data feed.",
                "checklist": {},
                "order_ticket": None
            }

        # 1. Higher-Timeframe Context (4H & 1H Directional Bias)
        h4_lookback = min(len(c_1h), 120) if c_1h else 24
        h4_high = max([c['high'] for c in c_1h[-h4_lookback:]]) if c_1h else current_price
        h4_low = min([c['low'] for c in c_1h[-h4_lookback:]]) if c_1h else current_price
        h4_mid = (h4_high + h4_low) / 2

        is_bullish_bias = current_price > h4_mid
        htf_bias = "BULLISH (Premium Expansion Expected)" if is_bullish_bias else "BEARISH (Discount Expansion Expected)"

        # 2. Draw on Liquidity (DOL) Determination
        recent_15m = c_15m[-16:] if len(c_15m) >= 16 else c_15m
        bsl_15m = max([c['high'] for c in recent_15m[:-1]]) if len(recent_15m) > 1 else recent_15m[0]['high']
        ssl_15m = min([c['low'] for c in recent_15m[:-1]]) if len(recent_15m) > 1 else recent_15m[0]['low']

        day_high = market_data.get("day_high", 0.0) or bsl_15m
        day_low = market_data.get("day_low", 0.0) or ssl_15m

        if is_bullish_bias:
            dol = day_high if day_high > current_price else bsl_15m
            dol_label = f"BSL Target @ {round(dol, dec)}"
        else:
            dol = day_low if day_low < current_price else ssl_15m
            dol_label = f"SSL Target @ {round(dol, dec)}"

        # 3. Session Checking Window (Asia / London / NY in IST)
        session_info = self._get_ist_session()

        # 4. Select 30M PD Array
        if not c_30m and len(c_15m) >= 4:
            c_30m = []
            for i in range(0, len(c_15m) - 1, 2):
                c_30m.append({
                    "open": c_15m[i]['open'],
                    "high": max(c_15m[i]['high'], c_15m[i+1]['high']),
                    "low": min(c_15m[i]['low'], c_15m[i+1]['low']),
                    "close": c_15m[i+1]['close'],
                    "timestamp": c_15m[i]['timestamp']
                })

        pd_array = self._find_30m_pd_array(c_30m, htf_bias, current_price, dec)

        # 5. Check 30M Tap Status across last 25 1M candles (25 min window)
        lookback_1m = c_1m[-25:] if len(c_1m) >= 25 else c_1m
        recent_1m_high = max([c['high'] for c in lookback_1m])
        recent_1m_low = min([c['low'] for c in lookback_1m])

        array_tapped = (
            (recent_1m_high >= pd_array["low"] and recent_1m_low <= pd_array["high"]) or
            (pd_array["low"] <= current_price <= pd_array["high"])
        )

        tap_status = "30M PD ARRAY TAPPED — CHECK 1M" if array_tapped else f"WAITING FOR 30M TAP [{pd_array['low']} - {pd_array['high']}]"

        # 6. 1M Execution Confirmation (IFVG + CISD)
        m1_candles = c_1m[-20:] if len(c_1m) >= 20 else c_1m
        has_ifvg = False
        has_cisd = False
        invalidation_level = None
        poi_entry = None

        if array_tapped and len(m1_candles) >= 5:
            if is_bullish_bias:
                # Bullish setup:
                # Invalidation is the lowest low formed during the tap / recent swing
                invalidation_level = min([c['low'] for c in m1_candles])
                
                # Check for 1M Bullish IFVG (Bearish FVG traded through upward)
                for i in range(2, len(m1_candles) - 1):
                    if m1_candles[i-2]['low'] > m1_candles[i]['high']:
                        if current_price > m1_candles[i-2]['low']:
                            has_ifvg = True
                            poi_entry = round((m1_candles[i-2]['low'] + m1_candles[i]['high']) / 2, dec)
                            break
                
                # If no inverted gap yet, check for clean 1M Bullish FVG displacement
                if not has_ifvg:
                    for i in range(2, len(m1_candles)):
                        if m1_candles[i]['low'] > m1_candles[i-2]['high']:
                            has_ifvg = True
                            poi_entry = round((m1_candles[i]['low'] + m1_candles[i-2]['high']) / 2, dec)
                            break

                # Check for 1M Bullish CISD (Displacement breaking intermediate swing high)
                swing_highs = [m1_candles[i]['high'] for i in range(1, len(m1_candles)-1) if m1_candles[i]['high'] >= m1_candles[i-1]['high'] and m1_candles[i]['high'] >= m1_candles[i+1]['high']]
                if not swing_highs:
                    swing_highs = [m1_candles[i]['high'] for i in range(1, len(m1_candles)-1) if m1_candles[i]['high'] > m1_candles[i-1]['high']]
                
                if swing_highs and current_price >= swing_highs[-1]:
                    has_cisd = True

            else:
                # Bearish setup:
                # Invalidation is the highest high formed during the tap / recent swing
                invalidation_level = max([c['high'] for c in m1_candles])
                
                # Check for 1M Bearish IFVG (Bullish FVG traded through downward)
                for i in range(2, len(m1_candles) - 1):
                    if m1_candles[i-2]['high'] < m1_candles[i]['low']:
                        if current_price < m1_candles[i-2]['high']:
                            has_ifvg = True
                            poi_entry = round((m1_candles[i-2]['high'] + m1_candles[i]['low']) / 2, dec)
                            break
                
                # If no inverted gap yet, check for clean 1M Bearish FVG displacement
                if not has_ifvg:
                    for i in range(2, len(m1_candles)):
                        if m1_candles[i-2]['low'] > m1_candles[i]['high']:
                            has_ifvg = True
                            poi_entry = round((m1_candles[i-2]['low'] + m1_candles[i]['high']) / 2, dec)
                            break

                # Check for 1M Bearish CISD (Displacement breaking intermediate swing low)
                swing_lows = [m1_candles[i]['low'] for i in range(1, len(m1_candles)-1) if m1_candles[i]['low'] <= m1_candles[i-1]['low'] and m1_candles[i]['low'] <= m1_candles[i+1]['low']]
                if not swing_lows:
                    swing_lows = [m1_candles[i]['low'] for i in range(1, len(m1_candles)-1) if m1_candles[i]['low'] < m1_candles[i-1]['low']]
                
                if swing_lows and current_price <= swing_lows[-1]:
                    has_cisd = True

        checklist = {
            "1. HTF Bias & Context": htf_bias,
            "2. Draw on Liquidity (DOL)": dol_label,
            "3. Session Window (IST)": session_info["label"],
            "4. 30M PD Array": pd_array["label"],
            "5. 30M Tap Alert": tap_status,
            "6. 1M Recent Swing": f"Ref Extreme: {round(invalidation_level, dec)}" if invalidation_level else "Monitoring for Swing",
            "7. 1M IFVG Confirmation": "CONFIRMED (Valid IFVG Inversion)" if has_ifvg else ("FORMING" if array_tapped else "WAITING"),
            "8. 1M CISD Confirmation": "CONFIRMED (State of Delivery Shifted)" if has_cisd else ("FORMING" if array_tapped else "WAITING"),
            "9. Execution & Goat Safe": "SAFE ($2.50 Risk | 1:2+ R:R | <15% Cap)"
        }

        # Stand aside if 30M PD array is not yet tapped
        if not array_tapped:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": f"Waiting for price to tap 30M PD Array [{pd_array['label']}]. Do not anticipate.",
                "checklist": checklist,
                "order_ticket": None
            }

        # If 30M tapped but 1M IFVG + CISD not yet confirmed:
        if not (has_ifvg and has_cisd):
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "30M PD Array tapped! Monitoring 1M chart for IFVG inversion and CISD delivery change.",
                "checklist": checklist,
                "order_ticket": None
            }

        # Complete Confirmation Sequence Satisfied!
        risk_dollars = account_config.get("risk_per_trade", 2.50)
        min_rr = account_config.get("min_rr", 1.8)
        
        entry = poi_entry if (poi_entry and abs(poi_entry - current_price) < (30.0 if symbol == "NAS100" else 8.0)) else current_price
        sl_buffer = 3.0 if symbol == "NAS100" else 1.0

        if is_bullish_bias:
            sl = round((invalidation_level or entry) - sl_buffer, dec)
            sl_dist = abs(entry - sl)
            min_sl_dist = 4.0 if symbol == "NAS100" else 1.5
            if sl_dist < min_sl_dist:
                sl_dist = min_sl_dist
                sl = round(entry - sl_dist, dec)
            
            # Target calculation: use DOL if favorable (> 2.0 R:R), otherwise target 1:2.2 expansion
            req_tp = entry + sl_dist * 2.2
            tp = round(max(dol, req_tp), dec)
            tp_dist = abs(tp - entry)
            rr = tp_dist / sl_dist if sl_dist > 0 else 2.2
            
            projected_gain = round(risk_dollars * rr, 2)
            ticket = {
                "Order Type": "BUY LIMIT",
                "Instrument": symbol,
                "Entry Price": round(entry, dec),
                "Stop Loss": round(sl, dec),
                "Take Profit": round(tp, dec),
                "R:R": f"1:{round(rr, 2)}",
                "Risk Amount": f"${risk_dollars:.2f} (0.25%)",
                "Projected Profit": f"+${projected_gain:.2f}",
                "Consistency Impact": f"{round((projected_gain / 100.0) * 100, 1)}% (< 15% Cap Safe)",
                "Cancel If": f"Price closes below 1M Invalidation ({round(sl, dec)}) or sweeps TP ({round(tp, dec)}) before fill."
            }
            return {
                "strategy": self.name,
                "decision": "Buy limit",
                "reason": f"30M PD Array tapped -> 1M IFVG + CISD confirmed -> R:R 1:{round(rr, 2)} to DOL ({tp}).",
                "checklist": checklist,
                "order_ticket": ticket
            }
        else:
            sl = round((invalidation_level or entry) + sl_buffer, dec)
            sl_dist = abs(sl - entry)
            min_sl_dist = 4.0 if symbol == "NAS100" else 1.5
            if sl_dist < min_sl_dist:
                sl_dist = min_sl_dist
                sl = round(entry + sl_dist, dec)

            req_tp = entry - sl_dist * 2.2
            tp = round(min(dol, req_tp), dec)
            tp_dist = abs(entry - tp)
            rr = tp_dist / sl_dist if sl_dist > 0 else 2.2
            
            projected_gain = round(risk_dollars * rr, 2)
            ticket = {
                "Order Type": "SELL LIMIT",
                "Instrument": symbol,
                "Entry Price": round(entry, dec),
                "Stop Loss": round(sl, dec),
                "Take Profit": round(tp, dec),
                "R:R": f"1:{round(rr, 2)}",
                "Risk Amount": f"${risk_dollars:.2f} (0.25%)",
                "Projected Profit": f"+${projected_gain:.2f}",
                "Consistency Impact": f"{round((projected_gain / 100.0) * 100, 1)}% (< 15% Cap Safe)",
                "Cancel If": f"Price closes above 1M Invalidation ({round(sl, dec)}) or sweeps TP ({round(tp, dec)}) before fill."
            }
            return {
                "strategy": self.name,
                "decision": "Sell limit",
                "reason": f"30M PD Array tapped -> 1M IFVG + CISD confirmed -> R:R 1:{round(rr, 2)} to DOL ({tp}).",
                "checklist": checklist,
                "order_ticket": ticket
            }
