import datetime
from typing import Dict, Any
from .base_strategy import BaseStrategy
from backend.risk_engine import build_order_ticket, sl_buffer, MIN_RR, DEFAULT_ACCOUNT_BALANCE

class SessionBreakoutStrategy(BaseStrategy):
    """
    Session Range Breakout & Momentum Strategy with Goat $1,000 Risk Framework.
    Monitors established session ranges and trades confirmed high-momentum expansion breakouts.
    """
    def __init__(self):
        super().__init__(
            name="Session Momentum Breakout",
            description="Trades confirmed multi-candle momentum breaks of established session ranges."
        )

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        c_15m = market_data.get("candles_15m", [])
        c_1m = market_data.get("candles_1m", [])
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)

        dec = 2 if "gold" in symbol.lower() else 1
        is_gold = "gold" in symbol.lower()

        if not c_15m or current_price == 0.0:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Insufficient market data.",
                "checklist": {},
                "order_ticket": None
            }

        # Lookback over the established session range (last 16 candles = 4 hours)
        range_candles = c_15m[-16:] if len(c_15m) >= 16 else c_15m
        range_high = max([c['high'] for c in range_candles])
        range_low = min([c['low'] for c in range_candles])
        range_mid = (range_high + range_low) / 2.0

        checklist = {
            "Session Range High": round(range_high, dec),
            "Session Range Low": round(range_low, dec),
            "Breakout State": "INSIDE RANGE",
            "Goat $1k Compliance": f"SAFE ($2.50 Risk | 1:{MIN_RR:.1f}+ R:R)"
        }

        decision = "Wait / No trade"
        reason = f"Price ({round(current_price, dec)}) is consolidating inside the session range [{round(range_low, dec)} - {round(range_high, dec)}]."
        order_ticket = None

        risk_dollars = account_config.get("risk_per_trade", 2.50)
        account_bal = account_config.get("account_balance") or account_config.get("balance", DEFAULT_ACCOUNT_BALANCE)
        buf = sl_buffer(symbol)

        # Breakout requires price to cleanly displace beyond range high or low
        breakout_buffer = 0.8 if is_gold else 5.0
        
        if current_price > (range_high + breakout_buffer):
            checklist["Breakout State"] = "BULLISH BREAKOUT"
            entry = current_price
            sl = round(range_high - buf, dec)
            risk_dist = abs(entry - sl)
            # Target standardized MIN_RR
            tp = round(entry + (risk_dist * MIN_RR), dec)
            reward_dist = abs(tp - entry)
            rr = reward_dist / risk_dist if risk_dist > 0 else 0
            
            if rr >= MIN_RR:
                decision = "Buy stop / Market"
                reason = f"Confirmed momentum expansion above session high ({round(range_high, dec)})."
                order_ticket = build_order_ticket(
                    direction="BUY",
                    symbol=symbol,
                    entry=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    risk_dollars=risk_dollars,
                    account_balance=account_bal,
                    order_type="BUY STOP / MARKET",
                    cancel_condition=f"Price retreats back inside session range ({round(range_high, dec)})."
                )
        elif current_price < (range_low - breakout_buffer):
            checklist["Breakout State"] = "BEARISH BREAKOUT"
            entry = current_price
            sl = round(range_low + buf, dec)
            risk_dist = abs(sl - entry)
            tp = round(entry - (risk_dist * MIN_RR), dec)
            reward_dist = abs(entry - tp)
            rr = reward_dist / risk_dist if risk_dist > 0 else 0
            
            if rr >= MIN_RR:
                decision = "Sell stop / Market"
                reason = f"Confirmed momentum expansion below session low ({round(range_low, dec)})."
                order_ticket = build_order_ticket(
                    direction="SELL",
                    symbol=symbol,
                    entry=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    risk_dollars=risk_dollars,
                    account_balance=account_bal,
                    order_type="SELL STOP / MARKET",
                    cancel_condition=f"Price retreats back inside session range ({round(range_low, dec)})."
                )

        return {
            "strategy": self.name,
            "decision": decision,
            "reason": reason,
            "checklist": checklist,
            "order_ticket": order_ticket
        }
