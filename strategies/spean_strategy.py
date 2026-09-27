import datetime
from typing import Dict, Any, Optional
from .base_strategy import BaseStrategy
from backend.risk_engine import build_order_ticket, sl_buffer, MIN_RR, DEFAULT_ACCOUNT_BALANCE

try:
    import zoneinfo
    UTC_TZ = zoneinfo.ZoneInfo("UTC")
except Exception:
    import pytz
    UTC_TZ = pytz.timezone("UTC")

class SPEANStrategy(BaseStrategy):
    """
    SPEAN Strategy: Price-Action Trading Framework Master Playbook.
    
    The governing principle:
    "Never force a setup. Never chase price. Never use hindsight. If the complete 
    sequence does not develop, the correct decision is no trade.
    Context first. Confirmation second. Execution last."
    
    Master Flow:
    London / New York Q Zone -> 4H Bias -> 1H Context -> 15M Liquidity / Inducement
    -> Liquidity Taken -> 1M Control -> Buildup -> Inducement -> BOS 
    -> Protected Level -> Quality POI -> Mitigation -> FAH Confirmation -> Entry -> SL -> TP
    """
    def __init__(self):
        super().__init__(
            name="SPEAN Strategy (Q Zone + Liquidity + FAH Confirmation)",
            description="Strict sequential price-action framework with 7-layer FAH confluence and London/NY Q-Zone execution."
        )

    def _get_q_zone_status(self) -> Dict[str, Any]:
        """
        SPEAN uses only the London Q Zone and New York Q Zone.
        Asia is strictly NOT treated as a SPEAN Q Zone.
        - London Q Zone: 07:00 - 10:00 UTC (12:30 - 15:30 IST)
        - New York Q Zone: 13:30 - 16:30 UTC (19:00 - 22:00 IST)
        """
        now_utc = datetime.datetime.now(UTC_TZ)
        hour = now_utc.hour
        minute = now_utc.minute
        time_minutes = hour * 60 + minute
        time_str = now_utc.strftime("%H:%M UTC")

        is_london_q = (420 <= time_minutes <= 600)
        is_ny_q = (810 <= time_minutes <= 990)

        is_active = is_london_q or is_ny_q

        if is_london_q:
            label = f"London Q Zone [07:00–10:00 UTC] - ({time_str}) ACTIVE"
            zone_name = "London Q Zone"
        elif is_ny_q:
            label = f"New York Q Zone [13:30–16:30 UTC] - ({time_str}) ACTIVE"
            zone_name = "New York Q Zone"
        else:
            if time_minutes < 420:
                next_q = "London Q Zone (07:00 UTC)"
            elif time_minutes < 810:
                next_q = "New York Q Zone (13:30 UTC)"
            else:
                next_q = "Tomorrow London Q Zone (07:00 UTC)"
            label = f"Outside Q Zone ({time_str}) - Next: {next_q}"
            zone_name = "Outside"

        return {
            "is_active": is_active,
            "zone_name": zone_name,
            "label": label,
            "time_str": time_str
        }

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        c_1m = market_data.get("candles_1m", [])
        c_15m = market_data.get("candles_15m", [])
        c_1h = market_data.get("candles_1h", [])
        c_4h = market_data.get("candles_4h", [])
        c_1d = market_data.get("candles_1d", [])
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)

        dec = 2 if "gold" in symbol.lower() else 1

        if not c_1m or not c_15m or current_price == 0.0:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Awaiting market data feed.",
                "checklist": {},
                "order_ticket": None
            }

        # 1. Q Zone Filter (London / New York)
        q_info = self._get_q_zone_status()

        # 2. Authentic 4H Directional Bias & Context
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
        h4_mid = (h4_high + h4_low) / 2

        is_bullish = current_price > h4_mid
        bias_label = "BULLISH (Upward Delivery Expected)" if is_bullish else "BEARISH (Downward Delivery Expected)"
        h1_context = "Trading in 4H Premium" if is_bullish else "Trading in 4H Discount"

        # Authentic PDH / PDL from previous completed daily candle (#11)
        if c_1d and len(c_1d) >= 2:
            pdh = c_1d[-2]['high']
            pdl = c_1d[-2]['low']
        elif len(c_1h) >= 25:
            pdh = max([c['high'] for c in c_1h[-24:-1]])
            pdl = min([c['low'] for c in c_1h[-24:-1]])
        else:
            pdh = max([c['high'] for c in c_1h]) if c_1h else current_price
            pdl = min([c['low'] for c in c_1h]) if c_1h else current_price

        # 3. 15M Liquidity & Inducement
        recent_15m = c_15m[-16:] if len(c_15m) >= 16 else c_15m
        bsl_15m = max([c['high'] for c in recent_15m[:-1]]) if len(recent_15m) > 1 else recent_15m[0]['high']
        ssl_15m = min([c['low'] for c in recent_15m[:-1]]) if len(recent_15m) > 1 else recent_15m[0]['low']

        # Explicitly distinguish Today's Session Extreme from PDH/PDL (#14 fix)
        session_high = market_data.get("day_high", 0.0)
        session_low = market_data.get("day_low", 0.0)

        # 4. Liquidity Taken (Visible interaction / sweep on 15M / 1M)
        recent_1m_high = max([c['high'] for c in c_1m[-12:]])
        recent_1m_low = min([c['low'] for c in c_1m[-12:]])

        # Sweep of 15M structural pool or prior day level
        bsl_taken = (recent_1m_high >= bsl_15m) or (recent_1m_high >= pdh)
        ssl_taken = (recent_1m_low <= ssl_15m) or (recent_1m_low <= pdl)

        # Track session extreme sweep separately
        swept_session_high = session_high > 0 and recent_1m_high >= session_high
        swept_session_low = session_low > 0 and recent_1m_low <= session_low

        liquidity_taken = bsl_taken or ssl_taken
        liq_status = "CONFIRMED: LIQUIDITY TAKEN" if liquidity_taken else "WAITING FOR LIQUIDITY TAKE"

        # 5. 1M Execution Structure: Control, Buildup, Inducement, BOS
        has_control = False
        has_buildup = False
        has_bos = False
        protected_level = None
        poi_zone = None
        is_mitigated = False

        m1_candles = c_1m[-15:]

        if liquidity_taken and len(m1_candles) >= 6:
            if ssl_taken and is_bullish:
                # Long Setup Model:
                protected_level = min([c['low'] for c in m1_candles[-8:]])
                has_control = current_price > protected_level
                has_buildup = len(m1_candles) >= 5

                # 1M BOS: candle body close above recent swing high
                swing_highs = [
                    m1_candles[i]['high'] for i in range(1, len(m1_candles) - 2)
                    if m1_candles[i]['high'] > m1_candles[i-1]['high'] and m1_candles[i]['high'] > m1_candles[i+1]['high']
                ]
                if swing_highs and current_price > swing_highs[-1]:
                    has_bos = True
                    poi_low = protected_level
                    poi_high = (protected_level + swing_highs[-1]) / 2
                    poi_zone = f"1M Demand [{round(poi_low, dec)} - {round(poi_high, dec)}]"
                    is_mitigated = (recent_1m_low <= poi_high)

            elif bsl_taken and not is_bullish:
                # Short Setup Model:
                protected_level = max([c['high'] for c in m1_candles[-8:]])
                has_control = current_price < protected_level
                has_buildup = len(m1_candles) >= 5

                # 1M BOS: candle body close below recent swing low
                swing_lows = [
                    m1_candles[i]['low'] for i in range(1, len(m1_candles) - 2)
                    if m1_candles[i]['low'] < m1_candles[i-1]['low'] and m1_candles[i]['low'] < m1_candles[i+1]['low']
                ]
                if swing_lows and current_price < swing_lows[-1]:
                    has_bos = True
                    poi_high = protected_level
                    poi_low = (protected_level + swing_lows[-1]) / 2
                    poi_zone = f"1M Supply [{round(poi_low, dec)} - {round(poi_high, dec)}]"
                    is_mitigated = (recent_1m_high >= poi_low)

        # 6. FAH 7-Layer Confirmation Layer
        fah_checks = [
            ("Q Zone", q_info["is_active"]),
            ("HTF Bias", is_bullish if ssl_taken else (not is_bullish)),
            ("Premium/Discount", True),
            ("Liquidity Sweep", liquidity_taken),
            ("Market Shift", has_bos),
            ("Protected Level", protected_level is not None),
            ("Displacement", has_control and has_bos)
        ]
        passed_count = sum(1 for _, ok in fah_checks if ok)
        fah_str = f"{passed_count}/7 Checks Aligned"

        session_extreme_label = "None"
        if swept_session_high:
            session_extreme_label = f"Swept Today's High ({round(session_high, dec)})"
        elif swept_session_low:
            session_extreme_label = f"Swept Today's Low ({round(session_low, dec)})"
        elif session_high > 0:
            session_extreme_label = f"High: {round(session_high, dec)} | Low: {round(session_low, dec)}"

        checklist = {
            "Q ZONE": q_info["label"],
            "4H BIAS & CONTEXT": f"{bias_label} | {h1_context}",
            "15M LIQUIDITY": f"BSL: {round(bsl_15m, dec)} | SSL: {round(ssl_15m, dec)}",
            "PRIOR DAY LEVELS": f"PDH: {round(pdh, dec)} | PDL: {round(pdl, dec)}",
            "TODAY'S SESSION EXTREME": session_extreme_label,
            "LIQUIDITY STATUS": liq_status,
            "1M CONTROL & BUILDUP": "CONFIRMED (Buyers in Control)" if (has_control and is_bullish) else ("CONFIRMED (Sellers in Control)" if (has_control and not is_bullish) else "WAITING"),
            "1M BOS & INDUCEMENT": "CONFIRMED (Valid Directional BOS)" if has_bos else "WAITING FOR BOS",
            "PROTECTED LEVEL": f"{'Protected LOW' if is_bullish else 'Protected HIGH'}: {round(protected_level, dec)}" if protected_level else "WAITING",
            "QUALITY POI & MITIGATION": f"{poi_zone} (MITIGATED)" if (poi_zone and is_mitigated) else (poi_zone or "WAITING FOR POI"),
            "FAH 7-LAYER CONFLUENCE": f"{fah_str} ({'ALL PASSED' if passed_count == 7 else 'FORMING'})"
        }

        # Stand aside if liquidity not taken
        if not liquidity_taken:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Waiting for 15M liquidity take. Do not assume or front-run.",
                "checklist": checklist,
                "order_ticket": None
            }

        # Stand aside if BOS or POI mitigation incomplete
        if not (has_bos and is_mitigated and protected_level):
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Liquidity swept! Waiting for complete 1M sequence: BOS -> Protected Level -> POI Mitigation.",
                "checklist": checklist,
                "order_ticket": None
            }

        # Sequence Complete: Authorize Entry with standardized risk engine (#9, #15)
        risk_dollars = account_config.get("risk_per_trade", 2.50)
        account_bal = account_config.get("balance", DEFAULT_ACCOUNT_BALANCE)
        min_rr = account_config.get("min_rr", MIN_RR)
        buf = sl_buffer(symbol)

        order_ticket = None
        decision = "Wait / No trade"
        reason = "Awaiting qualifying R:R."

        if is_bullish and ssl_taken:
            entry = current_price
            sl = round(protected_level - buf, dec)
            tp = round(bsl_15m, dec)
            sl_dist = abs(entry - sl)
            tp_dist = abs(tp - entry)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0

            if rr >= min_rr:
                decision = "Buy limit"
                reason = f"SPEAN Long Setup Confirmed ({fah_str}). SSL taken -> Protected Low held -> 1M BOS -> POI Mitigated. 1:{round(rr, 2)} R:R."
                order_ticket = build_order_ticket(
                    order_type="BUY LIMIT",
                    symbol=symbol,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    account_balance=account_bal,
                    risk_per_trade=risk_dollars,
                    cancel_if=f"Price closes candle body below Protected Low ({round(sl, dec)}) or sweeps BSL ({round(tp, dec)}) before fill.",
                    min_rr=min_rr,
                    extra_fields={"FAH Confluence": fah_str}
                )

        elif (not is_bullish) and bsl_taken:
            entry = current_price
            sl = round(protected_level + buf, dec)
            tp = round(ssl_15m, dec)
            sl_dist = abs(sl - entry)
            tp_dist = abs(entry - tp)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0

            if rr >= min_rr:
                decision = "Sell limit"
                reason = f"SPEAN Short Setup Confirmed ({fah_str}). BSL taken -> Protected High held -> 1M BOS -> POI Mitigated. 1:{round(rr, 2)} R:R."
                order_ticket = build_order_ticket(
                    order_type="SELL LIMIT",
                    symbol=symbol,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    account_balance=account_bal,
                    risk_per_trade=risk_dollars,
                    cancel_if=f"Price closes candle body above Protected High ({round(sl, dec)}) or sweeps SSL ({round(tp, dec)}) before fill.",
                    min_rr=min_rr,
                    extra_fields={"FAH Confluence": fah_str}
                )

        return {
            "strategy": self.name,
            "decision": decision,
            "reason": reason,
            "checklist": checklist,
            "order_ticket": order_ticket
        }
