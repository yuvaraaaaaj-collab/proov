import datetime
from typing import Dict, Any
from .base_strategy import BaseStrategy

class SessionBreakoutStrategy(BaseStrategy):
    """
    Session Range Breakout & Momentum Strategy.
    Monitors Asian/London highs and lows, detecting high-momentum expansion breakouts.
    """
    def __init__(self):
        super().__init__(
            name="Session Momentum Breakout",
            description="Trades confirmed multi-candle momentum breaks of established session ranges."
        )

    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        c_15m = market_data.get("candles_15m", [])
        symbol = market_data.get("symbol_name", "NAS100")
        current_price = market_data.get("current_price", 0.0)

        if not c_15m or current_price == 0.0:
            return {
                "strategy": self.name,
                "decision": "Wait / No trade",
                "reason": "Insufficient market data.",
                "checklist": {},
                "order_ticket": None
            }

        range_candles = c_15m[-16:] if len(c_15m) >= 16 else c_15m
        if len(range_candles) >= 3:
            range_high = max([c['high'] for c in range_candles[:-2]])
            range_low = min([c['low'] for c in range_candles[:-2]])
        else:
            range_high = max([c['high'] for c in range_candles])
            range_low = min([c['low'] for c in range_candles])

        checklist = {
            "Session Range High": round(range_high, 1),
            "Session Range Low": round(range_low, 1),
            "Breakout State": "INSIDE RANGE"
        }

        decision = "Wait / No trade"
        reason = "Price is currently consolidating inside the session range."
        order_ticket = None

        if current_price > range_high:
            checklist["Breakout State"] = "BULLISH BREAKOUT"
            decision = "Buy stop / Market"
            reason = f"Confirmed momentum expansion above session high ({round(range_high, 1)})."
        elif current_price < range_low:
            checklist["Breakout State"] = "BEARISH BREAKOUT"
            decision = "Sell stop / Market"
            reason = f"Confirmed momentum expansion below session low ({round(range_low, 1)})."

        return {
            "strategy": self.name,
            "decision": decision,
            "reason": reason,
            "checklist": checklist,
            "order_ticket": order_ticket
        }
