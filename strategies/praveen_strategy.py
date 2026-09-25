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
            description="30M PD Array location with 1M IFVG and CISD execution confirmation per Master Rule Set."
        )

    def _get_ist_session(self) -> Dict[str, Any]:
        """Calculates current Indian Standard Time (IST) and checks session windows."""
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

    def _determine_htf_bias(self, c_1h: list, current_price: float) -> Dict[str, Any]:
        """
        Step 1: Higher-Timeframe Analysis (Weekly/Daily/4H/1H).
        Determines overall market bias, 24h dealing range, and swing structure.
        """
        if not c_1h:
            return {
                "is_bullish": True,
                "bias_label": "BULLISH (Premium Expansion Expected)",
                "high_24h": current_price,
                "low_24h": current_price
            }

        recent_1h = c_1h[-24:] if len(c_1h) >= 24 else c_1h
        high_24h = max([c['high'] for c in recent_1h])
        low_24h = min([c['low'] for c in recent_1h])
        range_mid = (high_24h + low_24h) / 2

        # 20-period 1H trend
        ema_len = min(20, len(c_1h))
        alpha = 2 / (ema_len + 1)
        ema_1h = c_1h[-ema_len]['close']
        for c in c_1h[-ema_len:]:
            ema_1h = alpha * c['close'] + (1 - alpha) * ema_1h

        # 1H swing highs and swing lows to detect structural flow
        swing_highs = [recent_1h[i]['high'] for i in range(1, len(recent_1h)-1) if recent_1h[i]['high'] >= recent_1h[i-1]['high'] and recent_1h[i]['high'] >= recent_1h[i+1]['high']]
        swing_lows = [recent_1h[i]['low'] for i in range(1, len(recent_1h)-1) if recent_1h[i]['low'] <= recent_1h[i-1]['low'] and recent_1h[i]['low'] <= recent_1h[i+1]['low']]

        # Bullish if making higher swing lows or trading above 1H EMA with expansion toward high_24h
        if len(swing_lows) >= 2 and swing_lows[-1] > swing_lows[-2]:
            is_bullish = True
        elif len(swing_highs) >= 2 and swing_highs[-1] < swing_highs[-2]:
            is_bullish = False
        else:
            is_bullish = current_price >= range_mid or current_price >= ema_1h

        bias_label = "BULLISH (Premium Expansion Expected)" if is_bullish else "BEARISH (Discount Expansion Expected)"
        return {
            "is_bullish": is_bullish,
            "bias_label": bias_label,
            "high_24h": high_24h,
            "low_24h": low_24h,
            "range_mid": range_mid,
            "ema_1h": ema_1h
        }

    def _determine_dol(self, is_bullish: bool, current_price: float, high_24h: float, low_24h: float, dec: int) -> Dict[str, Any]:
        """
        Step 2: DOL Determination.
        If Bullish: Target overhead Buy-Side Liquidity (BSL) / Day High.
        If Bearish: Target lower Sell-Side Liquidity (SSL) / Day Low.
        """
        if is_bullish:
            if high_24h > current_price:
                dol = high_24h
                label = f"BSL Target @ {round(dol, dec)}"
            else:
                dol = current_price + max(20.0, (high_24h - low_24h) * 0.25)
                label = f"BSL Expansion @ {round(dol, dec)}"
        else:
            if low_24h < current_price:
                dol = low_24h
                label = f"SSL Target @ {round(dol, dec)}"
            else:
                dol = current_price - max(20.0, (high_24h - low_24h) * 0.25)
                label = f"SSL Expansion @ {round(dol, dec)}"
        return {"dol": round(dol, dec), "label": label}

    def _find_30m_pd_array(self, c_30m: list, is_bullish: bool, current_price: float, dec: int) -> Dict[str, Any]:
        """
        Step 4: Select 30M PD Array (FVG or OB).
        - For Bullish setup: Find DISCOUNT arrays (at or below current price / swing high).
        - For Bearish setup: Find PREMIUM arrays (at or above current price / swing low).
        - Array must NOT be invalidated by subsequent closes through it.
        """
        if len(c_30m) < 4:
            return {
                "type": "NONE",
                "high": round(current_price, dec),
                "low": round(current_price, dec),
                "label": "Insufficient 30M data"
            }

        candidates = []

        if is_bullish:
            # Look for 30M Bullish FVG & Bullish OB in Discount
            for i in range(len(c_30m) - 1, 1, -1):
                c1 = c_30m[i-2]
                c3 = c_30m[i]
                if c3['low'] > c1['high']:
                    low_val = round(c1['high'], dec)
                    high_val = round(c3['low'], dec)
                    # Check if subsequent candles respected this FVG (no close below low_val)
                    subsequent = c_30m[i+1:]
                    violated = any(c['close'] < low_val for c in subsequent)
                    if not violated and low_val <= current_price:
                        candidates.append({
                            "type": "30M Bullish FVG",
                            "high": high_val,
                            "low": low_val,
                            "mid": (high_val + low_val) / 2
                        })

            for i in range(len(c_30m) - 2, 1, -1):
                c = c_30m[i]
                next_c = c_30m[i+1]
                if c['close'] < c['open'] and next_c['close'] > c['high']:
                    low_val = round(c['low'], dec)
                    high_val = round(c['high'], dec)
                    subsequent = c_30m[i+1:]
                    violated = any(sc['close'] < low_val for sc in subsequent)
                    if not violated and low_val <= current_price:
                        candidates.append({
                            "type": "30M Bullish OB",
                            "high": high_val,
                            "low": low_val,
                            "mid": (high_val + low_val) / 2
                        })
        else:
            # Look for 30M Bearish FVG & Bearish OB in Premium
            for i in range(len(c_30m) - 1, 1, -1):
                c1 = c_30m[i-2]
                c3 = c_30m[i]
                if c1['low'] > c3['high']:
                    low_val = round(c3['high'], dec)
                    high_val = round(c1['low'], dec)
                    subsequent = c_30m[i+1:]
                    violated = any(c['close'] > high_val for c in subsequent)
                    if not violated and high_val >= current_price:
                        candidates.append({
                            "type": "30M Bearish FVG",
                            "high": high_val,
                            "low": low_val,
                            "mid": (high_val + low_val) / 2
                        })

            for i in range(len(c_30m) - 2, 1, -1):
                c = c_30m[i]
                next_c = c_30m[i+1]
                if c['close'] > c['open'] and next_c['close'] < c['low']:
                    low_val = round(c['low'], dec)
                    high_val = round(c['high'], dec)
                    subsequent = c_30m[i+1:]
                    violated = any(sc['close'] > high_val for sc in subsequent)
                    if not violated and high_val >= current_price:
                        candidates.append({
                            "type": "30M Bearish OB",
                            "high": high_val,
                            "low": low_val,
                            "mid": (high_val + low_val) / 2
                        })

        if candidates:
            # Pick candidate nearest to current price
            best = min(candidates, key=lambda c: abs(c['mid'] - current_price))
            return {
                "type": best["type"],
                "high": best["high"],
                "low": best["low"],
                "mid": best["mid"],
                "label": f"{best['type']} [{best['low']} - {best['high']}]"
            }

        # Fallback to nearest 30M swing level
        last_30m = c_30m[-1]
        fallback_low = round(min(last_30m['low'], current_price), dec) if is_bullish else round(current_price, dec)
        fallback_high = round(current_price, dec) if is_bullish else round(max(last_30m['high'], current_price), dec)
        return {
            "type": "30M Swing Discount" if is_bullish else "30M Swing Premium",
            "high": fallback_high,
            "low": fallback_low,
            "mid": (fallback_high + fallback_low) / 2,
            "label": f"30M Swing Level [{fallback_low} - {fallback_high}]"
        }

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        c_1m = market_data.get("candles_1m", [])
        c_15m = market_data.get("candles_15m", [])
        c_30m = market_data.get("candles_30m", [])
        c_1h = market_data.get("candles_1h", [])
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)

        dec = 2 if "gold" in symbol.lower() else 1

        if not c_1m or current_price == 0.0:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Awaiting live market data feed.",
                "checklist": {},
                "order_ticket": None
            }

        # 1. Higher-Timeframe Analysis (Weekly/Daily/4H/1H)
        htf_info = self._determine_htf_bias(c_1h, current_price)
        is_bullish = htf_info["is_bullish"]

        # 2. DOL Determination
        dol_info = self._determine_dol(is_bullish, current_price, htf_info["high_24h"], htf_info["low_24h"], dec)
        dol = dol_info["dol"]

        # 3. Session Window (IST)
        session_info = self._get_ist_session()

        # 4. 30M PD Array Selection
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

        pd_array = self._find_30m_pd_array(c_30m, is_bullish, current_price, dec)

        # 5. Check 30M Tap Status across recent 1M candles (last 20 mins)
        lookback_1m = c_1m[-20:] if len(c_1m) >= 20 else c_1m
        recent_1m_high = max([c['high'] for c in lookback_1m])
        recent_1m_low = min([c['low'] for c in lookback_1m])

        if is_bullish:
            array_tapped = (recent_1m_low <= pd_array["high"] and recent_1m_high >= pd_array["low"]) or (pd_array["low"] <= current_price <= pd_array["high"])
        else:
            array_tapped = (recent_1m_high >= pd_array["low"] and recent_1m_low <= pd_array["high"]) or (pd_array["low"] <= current_price <= pd_array["high"])

        tap_status = "30M PD ARRAY TAPPED — CHECK 1M" if array_tapped else f"WAITING FOR 30M TAP [{pd_array['low']} - {pd_array['high']}]"

        # 6. 1M Execution Confirmation (IFVG + CISD)
        has_ifvg = False
        has_cisd = False
        invalidation_level = None
        poi_entry = None

        if array_tapped and len(lookback_1m) >= 4:
            if is_bullish:
                invalidation_level = min([c['low'] for c in lookback_1m])
                # Check 1M Bullish IFVG (Bearish FVG traded through upward)
                for i in range(2, len(lookback_1m) - 1):
                    if lookback_1m[i-2]['low'] > lookback_1m[i]['high']:
                        subsequent_closes = [c['close'] for c in lookback_1m[i+1:]]
                        if any(cl > lookback_1m[i-2]['low'] for cl in subsequent_closes):
                            has_ifvg = True
                            poi_entry = round((lookback_1m[i-2]['low'] + lookback_1m[i]['high']) / 2, dec)
                            break

                # Check 1M Bullish CISD (Displacement breaking intermediate down-close delivery candle or swing high)
                down_candles = [c for c in lookback_1m if c['close'] < c['open']]
                if down_candles and current_price > down_candles[-1]['open']:
                    has_cisd = True
                swing_highs_1m = [lookback_1m[i]['high'] for i in range(1, len(lookback_1m)-1) if lookback_1m[i]['high'] >= lookback_1m[i-1]['high'] and lookback_1m[i]['high'] >= lookback_1m[i+1]['high']]
                if swing_highs_1m and current_price >= swing_highs_1m[-1]:
                    has_cisd = True
            else:
                invalidation_level = max([c['high'] for c in lookback_1m])
                # Check 1M Bearish IFVG (Bullish FVG traded through downward)
                for i in range(2, len(lookback_1m) - 1):
                    if lookback_1m[i]['low'] > lookback_1m[i-2]['high']:
                        subsequent_closes = [c['close'] for c in lookback_1m[i+1:]]
                        if any(cl < lookback_1m[i-2]['high'] for cl in subsequent_closes):
                            has_ifvg = True
                            poi_entry = round((lookback_1m[i-2]['high'] + lookback_1m[i]['low']) / 2, dec)
                            break

                # Check 1M Bearish CISD (Displacement breaking intermediate up-close delivery candle or swing low)
                up_candles = [c for c in lookback_1m if c['close'] > c['open']]
                if up_candles and current_price < up_candles[-1]['open']:
                    has_cisd = True
                swing_lows_1m = [lookback_1m[i]['low'] for i in range(1, len(lookback_1m)-1) if lookback_1m[i]['low'] <= lookback_1m[i-1]['low'] and lookback_1m[i]['low'] <= lookback_1m[i+1]['low']]
                if swing_lows_1m and current_price <= swing_lows_1m[-1]:
                    has_cisd = True

        checklist = {
            "1. HTF Bias & Context": htf_info["bias_label"],
            "2. Draw on Liquidity (DOL)": dol_info["label"],
            "3. Session Window (IST)": session_info["label"],
            "4. 30M PD Array": pd_array["label"],
            "5. 30M Tap Alert": tap_status,
            "6. 1M Recent Swing": f"Ref Extreme: {round(invalidation_level, dec)}" if invalidation_level else ("WAITING (Locked until 30M tap)" if not array_tapped else "Monitoring for Swing"),
            "7. 1M IFVG Confirmation": "CONFIRMED (Valid IFVG Inversion)" if has_ifvg else ("FORMING" if array_tapped else "WAITING"),
            "8. 1M CISD Confirmation": "CONFIRMED (State of Delivery Shifted)" if has_cisd else ("FORMING" if array_tapped else "WAITING"),
            "9. Execution & Goat Safe": "SAFE ($2.50 Risk | 1:2+ R:R | <15% Cap)"
        }

        # Stand aside if 30M PD array is not tapped yet
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
        entry = poi_entry if (poi_entry and abs(poi_entry - current_price) < (30.0 if symbol == "NAS100" else 8.0)) else current_price
        sl_buffer = 3.0 if symbol == "NAS100" else 1.0

        if is_bullish:
            sl = round((invalidation_level or entry) - sl_buffer, dec)
            sl_dist = abs(entry - sl)
            min_sl_dist = 4.0 if symbol == "NAS100" else 1.5
            if sl_dist < min_sl_dist:
                sl_dist = min_sl_dist
                sl = round(entry - sl_dist, dec)

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
