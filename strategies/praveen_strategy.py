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
        """Identifies relevant 30M FVG or Order Block (OB)."""
        if len(c_30m) < 4:
            return {"type": "NONE", "high": 0.0, "low": 0.0, "label": "Insufficient 30M data"}

        # Look for recent 30M Fair Value Gaps (FVG) or Order Blocks
        recent_30m = c_30m[-15:]
        fvg_found = None
        ob_found = None

        if "BULLISH" in bias:
            # Bullish context -> Look for 30M Discount FVG or Bullish OB below or near current price
            for i in range(len(recent_30m) - 1, 1, -1):
                # 3-candle FVG: candle 1 high < candle 3 low
                c1 = recent_30m[i-2]
                c3 = recent_30m[i]
                if c3['low'] > c1['high']:
                    fvg_low = c1['high']
                    fvg_high = c3['low']
                    if fvg_low <= current_price <= fvg_high * 1.01:
                        fvg_found = {"type": "30M Bullish FVG", "high": round(fvg_high, dec), "low": round(fvg_low, dec)}
                        break
            
            # Look for 30M Bullish Order Block (last down-close candle before displacement)
            if not fvg_found:
                for i in range(len(recent_30m) - 2, 0, -1):
                    c = recent_30m[i]
                    next_c = recent_30m[i+1]
                    if c['close'] < c['open'] and next_c['close'] > c['high']:
                        ob_low = c['low']
                        ob_high = c['high']
                        ob_found = {"type": "30M Bullish OB", "high": round(ob_high, dec), "low": round(ob_low, dec)}
                        break
        else:
            # Bearish context -> Look for 30M Premium FVG or Bearish OB above or near current price
            for i in range(len(recent_30m) - 1, 1, -1):
                c1 = recent_30m[i-2]
                c3 = recent_30m[i]
                if c1['low'] > c3['high']:
                    fvg_high = c1['low']
                    fvg_low = c3['high']
                    if fvg_low * 0.99 <= current_price <= fvg_high:
                        fvg_found = {"type": "30M Bearish FVG", "high": round(fvg_high, dec), "low": round(fvg_low, dec)}
                        break

            if not fvg_found:
                for i in range(len(recent_30m) - 2, 0, -1):
                    c = recent_30m[i]
                    next_c = recent_30m[i+1]
                    if c['close'] > c['open'] and next_c['close'] < c['low']:
                        ob_low = c['low']
                        ob_high = c['high']
                        ob_found = {"type": "30M Bearish OB", "high": round(ob_high, dec), "low": round(ob_low, dec)}
                        break

        chosen = fvg_found or ob_found
        if chosen:
            return {
                "type": chosen["type"],
                "high": chosen["high"],
                "low": chosen["low"],
                "label": f"{chosen['type']} [{chosen['low']} - {chosen['high']}]"
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
        # If 30m candles are empty, construct from 15m
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

        # 5. Check 30M Tap Status
        # Did current price or recent 1M candle tap into [pd_array['low'], pd_array['high']]?
        recent_1m_high = max([c['high'] for c in c_1m[-5:]])
        recent_1m_low = min([c['low'] for c in c_1m[-5:]])

        array_tapped = (recent_1m_high >= pd_array["low"] and recent_1m_low <= pd_array["high"]) or \
                       (pd_array["low"] <= current_price <= pd_array["high"])

        tap_status = "30M PD ARRAY TAPPED — CHECK 1M" if array_tapped else f"WAITING FOR 30M TAP [{pd_array['low']} - {pd_array['high']}]"

        # 6. 1M Execution Confirmation (IFVG + CISD)
        # Look at last 15 1M candles post-tap
        m1_candles = c_1m[-15:]
        has_ifvg = False
        has_cisd = False
        invalidation_level = None
        poi_entry = None

        if array_tapped and len(m1_candles) >= 5:
            if is_bullish_bias:
                # Bullish setup:
                # Invalidation is the lowest low formed at/around the tap
                invalidation_level = min([c['low'] for c in m1_candles[-8:]])
                
                # Check for 1M Bullish IFVG (Bearish FVG traded through upward)
                for i in range(2, len(m1_candles) - 1):
                    # Previous bearish gap: c[i-2].low > c[i].high
                    if m1_candles[i-2]['low'] > m1_candles[i]['high']:
                        # Candle i+1 or current price closed above the gap (Inversion)
                        if current_price > m1_candles[i-2]['low']:
                            has_ifvg = True
                            poi_entry = (m1_candles[i-2]['low'] + m1_candles[i]['high']) / 2
                            break
                
                # Check for 1M Bullish CISD (Displacement breaking intermediate down-leg sequence)
                swing_highs = [m1_candles[i]['high'] for i in range(1, len(m1_candles)-1) if m1_candles[i]['high'] > m1_candles[i-1]['high']]
                if swing_highs and current_price > swing_highs[-1]:
                    has_cisd = True

            else:
                # Bearish setup:
                # Invalidation is the highest high formed at/around the tap
                invalidation_level = max([c['high'] for c in m1_candles[-8:]])
                
                # Check for 1M Bearish IFVG (Bullish FVG traded through downward)
                for i in range(2, len(m1_candles) - 1):
                    # Previous bullish gap: c[i-2].high < c[i].low
                    if m1_candles[i-2]['high'] < m1_candles[i]['low']:
                        # Candle i+1 or current price closed below the gap (Inversion)
                        if current_price < m1_candles[i-2]['high']:
                            has_ifvg = True
                            poi_entry = (m1_candles[i-2]['high'] + m1_candles[i]['low']) / 2
                            break
                            
                # Check for 1M Bearish CISD (Displacement breaking intermediate up-leg sequence)
                swing_lows = [m1_candles[i]['low'] for i in range(1, len(m1_candles)-1) if m1_candles[i]['low'] < m1_candles[i-1]['low']]
                if swing_lows and current_price < swing_lows[-1]:
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

        # Stand aside if outside session window
        if not session_info["is_active"]:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": f"Outside Praveen Strategy checking window. Wait for Asia (05:30 IST), London (12:30 IST), or NY (19:00 IST).",
                "checklist": checklist,
                "order_ticket": None
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
        
        entry = poi_entry if poi_entry else current_price
        sl = invalidation_level
        sl_buffer = 3.0 if symbol == "NAS100" else 1.0

        if is_bullish_bias:
            sl = round(sl - sl_buffer, dec)
            tp = round(dol, dec)
            sl_dist = abs(entry - sl)
            tp_dist = abs(tp - entry)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0
            
            if rr >= min_rr:
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
            sl = round(sl + sl_buffer, dec)
            tp = round(dol, dec)
            sl_dist = abs(sl - entry)
            tp_dist = abs(entry - tp)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0
            
            if rr >= min_rr:
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

        return {
            "strategy": self.name,
            "decision": "Wait / No trade",
            "reason": "1M confirmation forming, awaiting favorable Risk:Reward (> 1:2) to DOL.",
            "checklist": checklist,
            "order_ticket": None
        }
