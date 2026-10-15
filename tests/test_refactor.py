import sys
import os
sys.path.insert(0, os.path.abspath("."))
from strategies.strategy_manager import StrategyManager
from backend.risk_engine import build_order_ticket, sl_buffer, MIN_RR, consistency_pct
from backend.smt_engine import check_smt_divergence, check_ssmt_divergence
from backend.market_data import get_market_data, SMT_PAIRS, TV_TICKERS

print("1. Testing Imports...")
sm = StrategyManager()
strategies = [s["id"] for s in sm.get_available_strategies()]
print("Strategies loaded:", strategies)

print("\n2. Testing Risk Engine...")
ticket = build_order_ticket(
    direction="BUY", symbol="NAS100", entry=20000.0, stop_loss=19990.0, take_profit=20025.0,
    risk_dollars=2.50, account_balance=1000.0
)
print("Ticket test:", ticket)
assert ticket["R:R"] == "1:2.50"
assert ticket["Projected Profit"] == "+$6.25"
assert "0.62%" in ticket["Consistency Impact"]
assert sl_buffer("NAS100") == 3.0
assert sl_buffer("SPX500") == 1.5
assert sl_buffer("GOLD") == 1.0

print("\n3. Testing SMT Engine Correlated Pairs...")
assert SMT_PAIRS["NAS100"] == "SPX500"
assert SMT_PAIRS["NQ"] == "MES"
assert SMT_PAIRS.get("GOLD") is None

print("\n4. Testing Strategy Evaluations on Synthetic Data...")
base_ts = 1710000000
dummy_md = {
    "symbol_name": "NAS100",
    "current_price": 20050.0,
    "candles_1m": [{"timestamp": base_ts + i*60, "open": 20000, "high": 20010, "low": 19990, "close": 20005, "volume": 100} for i in range(150)],
    "candles_15m": [{"timestamp": base_ts + i*900, "open": 20000, "high": 20020, "low": 19980, "close": 20015, "volume": 1000} for i in range(50)],
    "candles_30m": [{"timestamp": base_ts + i*1800, "open": 20000, "high": 20030, "low": 19970, "close": 20020, "volume": 2000} for i in range(50)],
    "candles_1h": [{"timestamp": base_ts + i*3600, "open": 20000, "high": 20050, "low": 19950, "close": 20030, "volume": 5000} for i in range(30)],
    "candles_4h": [{"timestamp": base_ts + i*14400, "open": 20000, "high": 20100, "low": 19900, "close": 20040, "volume": 20000} for i in range(20)],
    "candles_1d": [{"timestamp": base_ts + i*86400, "open": 20000, "high": 20200, "low": 19800, "close": 20050, "volume": 100000} for i in range(10)],
    "candles_1w": [{"timestamp": base_ts + i*604800, "open": 20000, "high": 20500, "low": 19500, "close": 20100, "volume": 500000} for i in range(5)],
    "correlated_candles_1m": [{"timestamp": base_ts + i*60, "open": 5500, "high": 5505, "low": 5495, "close": 5502, "volume": 50} for i in range(150)],
}
account_cfg = {"risk_per_trade": 2.50, "balance": 1000.0}

results = sm.evaluate_all(dummy_md, account_cfg)
for sid, res in results.items():
    print(f"Strategy [{sid}]: decision = '{res.get('decision')}', reason = '{res.get('reason', '')[:65]}'")
    assert "decision" in res
    assert "checklist" in res

print("\nSUCCESS! All strategies evaluated without errors.")
