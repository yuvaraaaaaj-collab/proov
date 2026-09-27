import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
from backend.market_data import market_data_provider, TV_TICKERS, SMT_PAIRS
from strategies.strategy_manager import StrategyManager

print("Initializing live market data test...")
time.sleep(3) # allow tv_feed to stream initial bars

sm = StrategyManager()
account_cfg = {"risk_per_trade": 2.50, "balance": 1000.0}

for sym in ["NAS100", "GOLD", "SPX500"]:
    print(f"\n==================== Testing Symbol: {sym} ====================")
    md = market_data_provider.get_market_data(sym)
    price = md.get("current_price", 0.0)
    stale = md.get("data_stale", True)
    c1m_len = len(md.get("candles_1m", []))
    c15m_len = len(md.get("candles_15m", []))
    c1h_len = len(md.get("candles_1h", []))
    c1d_len = len(md.get("candles_1d", []))
    corr_sym = md.get("correlated_symbol")
    corr_1m_len = len(md.get("correlated_candles_1m", []))

    print(f"Ticker: {md.get('ticker')}")
    print(f"Live Price: {price} | Stale: {stale}")
    print(f"Candles count: 1m={c1m_len}, 15m={c15m_len}, 1h={c1h_len}, 1d={c1d_len}")
    print(f"Correlated Symbol: {corr_sym} | Correlated 1m count: {corr_1m_len}")

    if sym in ["NAS100", "GOLD"]:
        eval_results = sm.evaluate_all(md, account_cfg)
        for s_id, res in eval_results.items():
            print(f"[{sym}] Strategy: {s_id}")
            print(f"     Decision: {res.get('decision')}")
            print(f"     Reason:   {res.get('reason', '')[:80]}")
            checklist_items = list(res.get("checklist", {}).items())[:2]
            print(f"     Checklist (sample): {checklist_items}")
            if res.get("order_ticket"):
                print(f"     Order Ticket: {res.get('order_ticket')}")

print("\nLIVE TEST COMPLETED SUCCESSFULLY!")
