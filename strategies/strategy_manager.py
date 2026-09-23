from typing import Dict, List, Any
from .base_strategy import BaseStrategy
from .smc_liquidity_master import SMCLiquidityMasterStrategy
from .session_breakout import SessionBreakoutStrategy

class StrategyManager:
    """
    Registry that manages all active and available strategies.
    Supports dynamic registration of custom strategies at runtime.
    """
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}
        self._active_strategy_id: str = "smc_master"
        
        # Register default built-in strategies
        self.register_strategy("smc_master", SMCLiquidityMasterStrategy())
        self.register_strategy("session_breakout", SessionBreakoutStrategy())

    def register_strategy(self, strategy_id: str, strategy_instance: BaseStrategy):
        self._strategies[strategy_id] = strategy_instance

    def get_available_strategies(self) -> List[Dict[str, str]]:
        return [
            {"id": s_id, "name": s.name, "description": s.description}
            for s_id, s in self._strategies.items()
        ]

    def set_active_strategy(self, strategy_id: str) -> bool:
        if strategy_id in self._strategies:
            self._active_strategy_id = strategy_id
            return True
        return False

    def get_active_strategy_id(self) -> str:
        return self._active_strategy_id

    def evaluate_active(self, market_data: Dict[str, Any], account_config: Dict[str, Any]) -> Dict[str, Any]:
        strategy = self._strategies.get(self._active_strategy_id)
        if not strategy:
            return {"decision": "Wait / No trade", "reason": "No active strategy found."}
        return strategy.evaluate(market_data, account_config)
