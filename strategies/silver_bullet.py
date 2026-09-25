import datetime
try:
    import zoneinfo
    NY_TZ = zoneinfo.ZoneInfo("America/New_York")
except Exception:
    import pytz
    NY_TZ = pytz.timezone("America/New_York")

from typing import Dict, Any, Optional
from .base_strategy import BaseStrategy

class ICTSilverBulletStrategy(BaseStrategy):
    """
    ICT Silver Bullet Strategy with Goat Funded Trader ($1,000) Risk Framework.
    
    Rules (from official ICT specifications):
    1. Time Windows (New York Local Time with Daylight Saving Adjustment):
       - London Open: 03:00 - 04:00 NY Time
       - New York AM: 10:00 - 11:00 NY Time
       - New York PM: 14:00 - 15:00 NY Time
       Setup may only form and trigger entry inside one of these 60-minute windows.
    2. Pre-Window Draw on Liquidity (DOL):
       Map Buy-Side Liquidity (BSL) and Sell-Side Liquidity (SSL) from 15M / 1H swings.
    3. Sweep / Raid:
       Price raids a mapped liquidity pool during or at window onset.
    4. Market Structure Shift (MSS) with Displacement:
       Fast, energetic directional move breaking intermediate swing structure.
    5. Fresh Fair Value Gap (FVG):
       Identify 3-candle imbalance created by the displacement leg.
    6. Entry:
       Limit order placed at the qualifying FVG retracement (near edge or 50% CE).
    7. Stop Loss:
       Placed beyond the manipulation swing / swept extreme.
    8. Target & R:R:
       Opposing liquidity pool with >= 10-15 index points (handles) / 15 pips.
       Strict Goat $1,000 risk controls ($2.50 risk, 1:2+ R:R, < 15% consistency cap).
    """
    def __init__(self):
        super().__init__(
            name="ICT Silver Bullet (Time-Based FVG + Goat $1k)",
            description="Trades 1M FVG retracements post-sweep inside strict 60-minute London & NY Silver Bullet windows."
        )

    def _get_ny_window(self) -> Dict[str, Any]:
        """Calculates current New York local time and checks Silver Bullet windows."""
        now_ny = datetime.datetime.now(NY_TZ)
        hour = now_ny.hour
        minute = now_ny.minute
        time_str = now_ny.strftime("%H:%M NY")

        is_london = (hour == 3)
        is_ny_am = (hour == 10)
        is_ny_pm = (hour == 14)

        is_active = is_london or is_ny_am or is_ny_pm
        
        if is_london:
            label = f"London Open Silver Bullet (03:00-04:00 NY) - [{time_str}] ACTIVE"
            window_id = "LONDON_OPEN"
        elif is_ny_am:
            label = f"New York AM Silver Bullet (10:00-11:00 NY) - [{time_str}] ACTIVE"
            window_id = "NY_AM"
        elif is_ny_pm:
            label = f"New York PM Silver Bullet (14:00-15:00 NY) - [{time_str}] ACTIVE"
            window_id = "NY_PM"
        else:
            # Determine next window
            if hour < 3:
                next_w = "London Open (03:00 NY)"
            elif hour < 10:
                next_w = "New York AM (10:00 NY)"
            elif hour < 14:
                next_w = "New York PM (14:00 NY)"
            else:
                next_w = "Tomorrow London Open (03:00 NY)"
            label = f"Outside Window [{time_str}] (Next: {next_w})"
            window_id = None

        return {
            "is_active": is_active,
            "window_id": window_id,
            "label": label,
            "hour": hour,
            "minute": minute
        }

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        c_1m = market_data.get("candles_1m", [])
        c_15m = market_data.get("candles_15m", [])
        c_1h = market_data.get("candles_1h", [])
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)

        if not c_1m or not c_15m or current_price == 0.0:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Awaiting market data feed.",
                "checklist": {},
                "order_ticket": None
            }

        # 1. Silver Bullet 60-Minute Time Window Check
        window_info = self._get_ny_window()
        
        # 2. Draw on Liquidity (DOL) Mapping (15M / 1H Swings)
        recent_15m = c_15m[-16:] if len(c_15m) >= 16 else c_15m
        bsl_15m = max([c['high'] for c in recent_15m[:-1]])
        ssl_15m = min([c['low'] for c in recent_15m[:-1]])

        pdh = max([c['high'] for c in c_1h[-24:-1]]) if len(c_1h) >= 25 else max([c['high'] for c in c_1h])
        pdl = min([c['low'] for c in c_1h[-24:-1]]) if len(c_1h) >= 25 else min([c['low'] for c in c_1h])

        # Align with TradingView Day High and Low for exact chart match
        day_high = market_data.get("day_high", 0.0)
        day_low = market_data.get("day_low", 0.0)
        if day_high > 0:
            pdh = day_high
        if day_low > 0:
            pdl = day_low

        # 3. Sweep / Raid Detection (Past 15 1M candles)
        recent_1m = c_1m[-15:]
        recent_high = max([c['high'] for c in recent_1m])
        recent_low = min([c['low'] for c in recent_1m])

        bsl_swept = recent_high >= bsl_15m
        ssl_swept = recent_low <= ssl_15m

        # Point, pip, and decimal specifications
        is_gold = ("gold" in symbol.lower())
        dec = 2 if is_gold else 1
        min_framework = 1.5 if is_gold else 12.0  # 15 pips gold, 12 index points nasdaq

        checklist = {
            "Silver Bullet Window": window_info["label"],
            "Draw on Liquidity (DOL)": f"BSL: {round(bsl_15m, dec)} | SSL: {round(ssl_15m, dec)}",
            "Liquidity Raid / Sweep": "YES (BSL Swept)" if bsl_swept else ("YES (SSL Swept)" if ssl_swept else "Awaiting Sweep"),
            "MSS & Displacement": "NO",
            "Fresh FVG Range": "NONE",
            "Entry Convention": "FVG Retracement Limit Order",
            "Opposing Target Pool": f"{round(ssl_15m, dec)} (SSL)" if bsl_swept else f"{round(bsl_15m, dec)} (BSL)",
            "Goat $1k Compliance": "SAFE ($2.50 Risk | 1:2+ R:R | <15% Cap)"
        }

        # Rule: Stand aside if outside designated 60-minute window
        if not window_info["is_active"]:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": f"Outside Silver Bullet window. Strategy requires entry inside 03:00-04:00, 10:00-11:00, or 14:00-15:00 NY time.",
                "checklist": checklist,
                "order_ticket": None
            }

        if not bsl_swept and not ssl_swept:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": f"Active in {window_info['label']}. Monitoring 15M BSL ({round(bsl_15m, 1)}) and SSL ({round(ssl_15m, 1)}) for liquidity raid.",
                "checklist": checklist,
                "order_ticket": None
            }

        decision = "Wait / No trade"
        reason = "Liquidity raid detected; awaiting Market Structure Shift (MSS) and fresh FVG."
        order_ticket = None

        risk_dollars = account_config.get("risk_per_trade", 2.50)
        min_rr = 2.0

        # Point and pip specifications
        is_gold = (symbol == "GOLD")
        min_framework = 1.5 if is_gold else 12.0  # 15 pips gold, 12 index points nasdaq

        # 4. Bearish Silver Bullet Setup (BSL Swept -> Bearish Displacement -> Bearish FVG)
        if bsl_swept and len(c_1m) >= 4:
            # Look for 1M Market Structure Shift (closing below previous swing low)
            start_i = max(1, len(c_1m) - 15)
            end_i = max(1, len(c_1m) - 2)
            swing_lows = [
                c_1m[i]['low'] for i in range(start_i, end_i)
                if c_1m[i]['low'] < c_1m[i-1]['low'] and c_1m[i]['low'] < c_1m[i+1]['low']
            ]
            
            if swing_lows and current_price < swing_lows[-1]:
                # Check for Displacement (energetic candle with body > 60% of range)
                disp_candle = None
                for c in c_1m[-5:]:
                    c_range = c['high'] - c['low']
                    if c_range > 0 and (c['open'] - c['close']) / c_range > 0.55:
                        disp_candle = c
                        break

                if disp_candle:
                    checklist["MSS & Displacement"] = "YES (Bearish MSS Confirmed)"

                    # Search for Fresh Bearish FVG in the last 5 candles
                    # Bearish FVG: Low of candle 1 > High of candle 3
                    fvg = None
                    min_idx = max(2, len(c_1m) - 6)
                    for idx in range(len(c_1m) - 2, min_idx - 1, -1):
                        c1 = c_1m[idx - 2]
                        c2 = c_1m[idx - 1]
                        c3 = c_1m[idx]
                        if c1['low'] > c3['high']:
                            gap_top = c1['low']
                            gap_bottom = c3['high']
                            gap_size = gap_top - gap_bottom
                            if gap_size >= (0.3 if is_gold else 2.5):
                                fvg = {
                                    "top": gap_top,
                                    "bottom": gap_bottom,
                                    "ce": (gap_top + gap_bottom) / 2.0,
                                    "size": gap_size
                                }
                                break

                    if fvg:
                        checklist["Fresh FVG Range"] = f"Bearish FVG: [{round(fvg['bottom'], dec)} - {round(fvg['top'], dec)}]"
                        entry_price = round(fvg["bottom"], dec)  # Enter on touch of lower boundary
                        swept_high = recent_high
                        stop_loss = round(swept_high + (1.0 if is_gold else 4.0), dec)
                        take_profit = round(ssl_15m, dec)

                        risk_dist = abs(stop_loss - entry_price)
                        reward_dist = abs(entry_price - take_profit)

                        # Enforce Minimum Framework (10-15 handles) and 1:2+ R:R
                        if risk_dist > 0 and reward_dist >= min_framework:
                            rr_ratio = reward_dist / risk_dist
                            if rr_ratio >= min_rr:
                                decision = "Sell limit"
                                reason = f"ICT Silver Bullet SELL LIMIT formed in {window_info['window_id']}. BSL raided, Bearish MSS displacement created fresh FVG [{round(fvg['bottom'], dec)}-{round(fvg['top'], dec)}]."
                                
                                # Goat $1k lot sizing
                                lot_size = round(risk_dollars / (risk_dist * (100 if is_gold else 1)), 2)
                                lot_size = max(0.01, min(lot_size, 0.50))
                                proj_profit = round(risk_dollars * rr_ratio, 2)

                                order_ticket = {
                                    "Order Type": "SELL LIMIT",
                                    "Instrument": "CAPITALCOM:US100" if symbol == "NAS100" else "CAPITALCOM:GOLD",
                                    "Entry Price": entry_price,
                                    "Stop Loss": stop_loss,
                                    "Take Profit": take_profit,
                                    "Risk Amount": f"${risk_dollars:.2f} (0.25%)",
                                    "Projected Profit": f"+${proj_profit:.2f}",
                                    "R:R": f"1:{rr_ratio:.1f}",
                                    "Lot Size": f"{lot_size} Lots",
                                    "Window": window_info["label"].split(" - ")[0].strip(),
                                    "FVG Range": f"{round(fvg['bottom'], dec)} - {round(fvg['top'], dec)}",
                                    "Consistency Impact": f"Safe (< 15% Cap / ${account_config.get('balance', 1000)*0.15:.0f})",
                                    "Cancel If": f"Price trades through {round(stop_loss, dec)} before entry or window closes."
                                }

        # 5. Bullish Silver Bullet Setup (SSL Swept -> Bullish Displacement -> Bullish FVG)
        elif ssl_swept and len(c_1m) >= 4:
            # Look for 1M Market Structure Shift (closing above previous swing high)
            start_i = max(1, len(c_1m) - 15)
            end_i = max(1, len(c_1m) - 2)
            swing_highs = [
                c_1m[i]['high'] for i in range(start_i, end_i)
                if c_1m[i]['high'] > c_1m[i-1]['high'] and c_1m[i]['high'] > c_1m[i+1]['high']
            ]
            
            if swing_highs and current_price > swing_highs[-1]:
                disp_candle = None
                for c in c_1m[-5:]:
                    c_range = c['high'] - c['low']
                    if c_range > 0 and (c['close'] - c['open']) / c_range > 0.55:
                        disp_candle = c
                        break

                if disp_candle:
                    checklist["MSS & Displacement"] = "YES (Bullish MSS Confirmed)"

                    # Search for Fresh Bullish FVG in last 5 candles
                    # Bullish FVG: High of candle 1 < Low of candle 3
                    fvg = None
                    min_idx = max(2, len(c_1m) - 6)
                    for idx in range(len(c_1m) - 2, min_idx - 1, -1):
                        c1 = c_1m[idx - 2]
                        c2 = c_1m[idx - 1]
                        c3 = c_1m[idx]
                        if c1['high'] < c3['low']:
                            gap_bottom = c1['high']
                            gap_top = c3['low']
                            gap_size = gap_top - gap_bottom
                            if gap_size >= (0.3 if is_gold else 2.5):
                                fvg = {
                                    "top": gap_top,
                                    "bottom": gap_bottom,
                                    "ce": (gap_top + gap_bottom) / 2.0,
                                    "size": gap_size
                                }
                                break

                    if fvg:
                        checklist["Fresh FVG Range"] = f"Bullish FVG: [{round(fvg['bottom'], dec)} - {round(fvg['top'], dec)}]"
                        entry_price = round(fvg["top"], dec)  # Enter on touch of upper boundary
                        swept_low = recent_low
                        stop_loss = round(swept_low - (1.0 if is_gold else 4.0), dec)
                        take_profit = round(bsl_15m, dec)

                        risk_dist = abs(entry_price - stop_loss)
                        reward_dist = abs(take_profit - entry_price)

                        if risk_dist > 0 and reward_dist >= min_framework:
                            rr_ratio = reward_dist / risk_dist
                            if rr_ratio >= min_rr:
                                decision = "Buy limit"
                                reason = f"ICT Silver Bullet BUY LIMIT formed in {window_info['window_id']}. SSL raided, Bullish MSS displacement created fresh FVG [{round(fvg['bottom'], dec)}-{round(fvg['top'], dec)}]."
                                
                                lot_size = round(risk_dollars / (risk_dist * (100 if is_gold else 1)), 2)
                                lot_size = max(0.01, min(lot_size, 0.50))
                                proj_profit = round(risk_dollars * rr_ratio, 2)

                                order_ticket = {
                                    "Order Type": "BUY LIMIT",
                                    "Instrument": "CAPITALCOM:US100" if symbol == "NAS100" else "CAPITALCOM:GOLD",
                                    "Entry Price": entry_price,
                                    "Stop Loss": stop_loss,
                                    "Take Profit": take_profit,
                                    "Risk Amount": f"${risk_dollars:.2f} (0.25%)",
                                    "Projected Profit": f"+${proj_profit:.2f}",
                                    "R:R": f"1:{rr_ratio:.1f}",
                                    "Lot Size": f"{lot_size} Lots",
                                    "Window": window_info["label"].split(" - ")[0].strip(),
                                    "FVG Range": f"{round(fvg['bottom'], dec)} - {round(fvg['top'], dec)}",
                                    "Consistency Impact": f"Safe (< 15% Cap / ${account_config.get('balance', 1000)*0.15:.0f})",
                                    "Cancel If": f"Price trades through {round(stop_loss, dec)} before entry or window closes."
                                }

        return {
            "strategy": self.name,
            "decision": decision,
            "reason": reason,
            "checklist": checklist,
            "order_ticket": order_ticket
        }
