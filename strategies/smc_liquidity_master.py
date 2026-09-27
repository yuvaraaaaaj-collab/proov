import datetime
from typing import Dict, Any, Optional
from .base_strategy import BaseStrategy
from backend.risk_engine import build_order_ticket, sl_buffer, MIN_RR, DEFAULT_ACCOUNT_BALANCE

class SMCLiquidityMasterStrategy(BaseStrategy):
    """
    ICT / SMC Liquidity Master Strategy with Goat Funded Trader Risk Framework.
    Flow:
    4H Bias -> 1H Context -> 15M BSL/SSL -> Session Timing -> Sweep ->
    1M Control -> Buildup -> Inducement -> BOS -> Protected Level -> POI -> Mitigation -> Entry -> SL -> TP
    """
    def __init__(self):
        super().__init__(
            name="SMC Liquidity Master (ICT + Goat $1k)",
            description="Trades post-sweep displacement on 1M after 15M liquidity takes during NY/Pre-NY sessions."
        )

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        c_1m = market_data.get("candles_1m", [])
        c_15m = market_data.get("candles_15m", [])
        c_1h = market_data.get("candles_1h", [])
        c_4h = market_data.get("candles_4h", [])
        c_1d = market_data.get("candles_1d", [])
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)

        if not c_1m or not c_15m or current_price == 0.0:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Insufficient market data.",
                "checklist": {},
                "order_ticket": None
            }

        dec = 2 if "gold" in symbol.lower() else 1

        # 1. Authentic 4H Environment & Dealing Range
        if c_4h and len(c_4h) >= 6:
            recent_4h = c_4h[-30:]  # 5 days of authentic 4H candles
            h4_high = max([c['high'] for c in recent_4h])
            h4_low = min([c['low'] for c in recent_4h])
        elif c_1h:
            h4_lookback = min(len(c_1h), 120)
            h4_high = max([c['high'] for c in c_1h[-h4_lookback:]])
            h4_low = min([c['low'] for c in c_1h[-h4_lookback:]])
        else:
            h4_high = current_price
            h4_low = current_price
        h4_range_mid = (h4_high + h4_low) / 2
        h4_bias = "BULLISH FLOW (Trading in Premium)" if current_price > h4_range_mid else "BEARISH FLOW (Trading in Discount)"

        # 2. Authentic Session Context & PDH/PDL from Previous Completed Daily Candle ONLY (#11 fix)
        if c_1d and len(c_1d) >= 2:
            pdh = c_1d[-2]['high']
            pdl = c_1d[-2]['low']
        elif len(c_1h) >= 25:
            pdh = max([c['high'] for c in c_1h[-24:-1]])
            pdl = min([c['low'] for c in c_1h[-24:-1]])
        else:
            pdh = max([c['high'] for c in c_1h]) if c_1h else current_price
            pdl = min([c['low'] for c in c_1h]) if c_1h else current_price

        # Intraday reference levels kept strictly separate from PDH/PDL
        day_high = market_data.get("day_high", 0.0)
        day_low = market_data.get("day_low", 0.0)

        # 3. 15M Liquidity & Inducement
        recent_15m = c_15m[-16:] if len(c_15m) >= 16 else c_15m
        bsl_15m = max([c['high'] for c in recent_15m[:-1]]) if len(recent_15m) > 1 else recent_15m[0]['high']
        ssl_15m = min([c['low'] for c in recent_15m[:-1]]) if len(recent_15m) > 1 else recent_15m[0]['low']

        # 4. Session Timing (NY / Pre-NY Priority Window: 12:00 to 20:00 UTC) (#13 load-bearing gate)
        now_utc = datetime.datetime.utcnow()
        is_ny_session = (12 <= now_utc.hour <= 20)
        session_label = f"Pre-NY / NY Session [{now_utc.strftime('%H:%M')} UTC] (ACTIVE)" if is_ny_session else f"Outside Priority Window [{now_utc.strftime('%H:%M')} UTC] (GATED)"

        # 5. Liquidity Sweep Detection (Past 12 1M candles)
        recent_1m_high = max([c['high'] for c in c_1m[-12:]])
        recent_1m_low = min([c['low'] for c in c_1m[-12:]])

        bsl_swept = recent_1m_high >= bsl_15m
        ssl_swept = recent_1m_low <= ssl_15m

        checklist = {
            "4H Swing Bias": h4_bias,
            "1H Session Context": f"PDH: {round(pdh, dec)} | PDL: {round(pdl, dec)}",
            "Today's Intraday Range": f"High: {round(day_high, dec)} | Low: {round(day_low, dec)}" if day_high > 0 else "---",
            "15M Liquidity": f"BSL: {round(bsl_15m, dec)} | SSL: {round(ssl_15m, dec)}",
            "Session Timing": session_label,
            "Liquidity Taken": "YES" if (bsl_swept or ssl_swept) else "NO",
            "1M Control & BOS": "NO",
            "Protected Level": "NONE",
            "POI Formed": "NO",
            "Mitigation Check": "WAITING"
        }

        # Gate on session timing (#13)
        if not is_ny_session:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": f"Outside London/NY Priority Session Window [{now_utc.strftime('%H:%M')} UTC]. Stand aside.",
                "checklist": checklist,
                "order_ticket": None
            }

        decision = "Wait / No trade"
        reason = "Awaiting 15M liquidity sweep and subsequent 1M structural sequence."
        order_ticket = None

        # Standardized Risk parameters (#9, #15)
        risk_dollars = account_config.get("risk_per_trade", 2.50)
        account_bal = account_config.get("balance", DEFAULT_ACCOUNT_BALANCE)
        min_rr = account_config.get("min_rr", MIN_RR)
        buf = sl_buffer(symbol)

        # 6. Evaluation of 1M Structure Post-Sweep
        if bsl_swept and len(c_1m) >= 4:
            # Look for 1M Bearish BOS (closing below recent 1M swing low)
            start_i = max(1, len(c_1m) - 15)
            end_i = max(1, len(c_1m) - 2)
            m1_swing_lows = [
                c_1m[i]['low'] for i in range(start_i, end_i)
                if c_1m[i]['low'] < c_1m[i-1]['low'] and c_1m[i]['low'] < c_1m[i+1]['low']
            ]
            
            if m1_swing_lows and current_price < m1_swing_lows[-1]:
                checklist["1M Control & BOS"] = "YES (Bearish BOS Confirmed)"
                protected_high = recent_1m_high
                checklist["Protected Level"] = f"Protected HIGH: {round(protected_high, dec)}"
                
                # POI: 1M Bearish FVG / Supply midpoint
                poi_entry = (protected_high + current_price) / 2
                checklist["POI Formed"] = f"1M Supply @ {round(poi_entry, dec)}"
                
                # SL: beyond Protected High with standardized buffer
                sl = protected_high + buf
                sl_distance = abs(sl - poi_entry)

                # TP: Target opposing SSL, capped at 1:3.0 R:R for Goat consistency
                ideal_tp = ssl_15m
                max_tp_dist = sl_distance * 3.0
                if abs(poi_entry - ideal_tp) > max_tp_dist:
                    tp = poi_entry - max_tp_dist
                else:
                    tp = ideal_tp
                
                tp_distance = abs(poi_entry - tp)
                rr = tp_distance / sl_distance if sl_distance > 0 else 0
                
                if rr >= min_rr:
                    decision = "Sell limit"
                    reason = f"15M BSL swept -> 1M Bearish BOS -> Valid POI Retracement with 1:{round(rr, 2)} R:R."
                    order_ticket = build_order_ticket(
                        order_type="SELL LIMIT",
                        symbol=symbol,
                        entry_price=poi_entry,
                        stop_loss=sl,
                        take_profit=tp,
                        account_balance=account_bal,
                        risk_per_trade=risk_dollars,
                        cancel_if=f"Price breaks above Protected High ({round(protected_high, dec)}) or sweeps TP ({round(tp, dec)}) before fill.",
                        min_rr=min_rr
                    )

        elif ssl_swept and len(c_1m) >= 4:
            # Look for 1M Bullish BOS (closing above recent 1M swing high)
            start_i = max(1, len(c_1m) - 15)
            end_i = max(1, len(c_1m) - 2)
            m1_swing_highs = [
                c_1m[i]['high'] for i in range(start_i, end_i)
                if c_1m[i]['high'] > c_1m[i-1]['high'] and c_1m[i]['high'] > c_1m[i+1]['high']
            ]
            
            if m1_swing_highs and current_price > m1_swing_highs[-1]:
                checklist["1M Control & BOS"] = "YES (Bullish BOS Confirmed)"
                protected_low = recent_1m_low
                checklist["Protected Level"] = f"Protected LOW: {round(protected_low, dec)}"
                
                # POI: 1M Bullish Demand midpoint
                poi_entry = (protected_low + current_price) / 2
                checklist["POI Formed"] = f"1M Demand @ {round(poi_entry, dec)}"
                
                sl = protected_low - buf
                sl_distance = abs(poi_entry - sl)

                # TP: Target opposing BSL, capped at 1:3.0 R:R for Goat consistency
                ideal_tp = bsl_15m
                max_tp_dist = sl_distance * 3.0
                if abs(ideal_tp - poi_entry) > max_tp_dist:
                    tp = poi_entry + max_tp_dist
                else:
                    tp = ideal_tp
                
                tp_distance = abs(tp - poi_entry)
                rr = tp_distance / sl_distance if sl_distance > 0 else 0
                
                if rr >= min_rr:
                    decision = "Buy limit"
                    reason = f"15M SSL swept -> 1M Bullish BOS -> Valid POI Retracement with 1:{round(rr, 2)} R:R."
                    order_ticket = build_order_ticket(
                        order_type="BUY LIMIT",
                        symbol=symbol,
                        entry_price=poi_entry,
                        stop_loss=sl,
                        take_profit=tp,
                        account_balance=account_bal,
                        risk_per_trade=risk_dollars,
                        cancel_if=f"Price drops below Protected Low ({round(protected_low, dec)}) or sweeps TP ({round(tp, dec)}) before fill.",
                        min_rr=min_rr
                    )

        return {
            "strategy": self.name,
            "decision": decision,
            "reason": reason,
            "checklist": checklist,
            "order_ticket": order_ticket
        }
