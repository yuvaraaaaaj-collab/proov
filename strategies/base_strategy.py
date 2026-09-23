from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseStrategy(ABC):
    """
    Universal Base Class for Trading Strategies.
    Any new strategy added in the future simply inherits from this class.
    """
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def evaluate(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates multi-timeframe market data and returns a structured decision.
        Returns:
            {
                "strategy": str,
                "decision": "Wait / No trade" | "Buy limit" | "Sell limit" | "Buy stop" | "Sell stop",
                "reason": str,
                "checklist": dict of checklist steps,
                "order_ticket": Optional[dict]
            }
        """
        pass
