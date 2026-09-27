# TraderPro Architecture & Strategy Refactor Audit Report

**Date**: September 27, 2026  
**Scope**: Repo-wide ICT strategy refactor, shared risk & SMT infrastructure, data pipeline unification, and bug eradication.

---

## Executive Summary

A comprehensive refactor across `backend/` and `strategies/` has eliminated all synthetic broker offsets, removed legacy Yahoo Finance scrapers, and unified all strategies onto a single authoritative TradingView WebSocket feed. All six ICT strategies and session breakout strategies now utilize centralized Goat Funded Trader ($1,000 account model) risk parameters, standardized SL buffers, synchronized SMT divergence logic against true equity indices (NAS100 vs SPX500, NQ vs MES), and the critical PDH/PDL overwriting bug in `smc_liquidity_master.py` and `silver_bullet.py` has been resolved.

---

## 1. Summary of Files Changed (Tasks 1 – 17)

| File | Status | Description of Changes |
| :--- | :--- | :--- |
| [`backend/risk_engine.py`](file:///d:/Project/trading_app/backend/risk_engine.py) | **Created** | Shared risk & order-ticket engine implementing Goat $1k account model: `DEFAULT_RISK_PER_TRADE = 2.50` (0.25%), `MIN_RR = 2.0`, `CONSISTENCY_CAP_PCT = 0.15` (15% profit cap), `sl_buffer()`, `consistency_pct()`, `consistency_impact_str()`, and `build_order_ticket()`. |
| [`backend/smt_engine.py`](file:///d:/Project/trading_app/backend/smt_engine.py) | **Created** | Centralized Smart Money Technique (SMT) and SSMT (Quarterly 90-min cycle) engine. Implements swing-point detection with timestamp tolerance (`pd.Timedelta`). Strictly pairs `NAS100 <-> SPX500` and `NQ <-> MES`, excluding commodities like `GOLD`. |
| [`backend/tv_feed.py`](file:///d:/Project/trading_app/backend/tv_feed.py) | **Refactored** | Subscribes to official TradingView WebSocket for `CAPITALCOM:US100`, `CAPITALCOM:SPX500`, and `CAPITALCOM:GOLD`. Streams real-time tick quotes and 8 concurrent timeframe resolutions (`1`, `5`, `15`, `30`, `60`, `240`, `1D`, `1W`). Thread-safe with `threading.Lock()`. |
| [`backend/market_data.py`](file:///d:/Project/trading_app/backend/market_data.py) | **Refactored** | Completely removed Yahoo Finance scraping (`requests`, `query1.finance.yahoo.com`), removed `broker_offset` and `_calib()` synthetic offsets. Pulls authentic quotes and multi-timeframe candles exclusively from `tv_feed`. Implemented `resample_candles()` and `align_series()` for SMT timestamp synchronization. SMT correlated pair is strictly `SPX500` for `NAS100`. |
| [`strategies/smc_liquidity_master.py`](file:///d:/Project/trading_app/strategies/smc_liquidity_master.py) | **Refactored** | **Fixed PDH/PDL Bug (#11)**: Removed `if day_high > 0: pdh = day_high`. PDH/PDL strictly derived from completed prior daily bar `c_1d[-2]`. Intraday high/low separated to "Today's Intraday Range". **Session check (#13)** made load-bearing (stands aside outside 12:00–20:00 UTC). Integrated `risk_engine` (`build_order_ticket`, `sl_buffer`, `MIN_RR`). |
| [`strategies/silver_bullet.py`](file:///d:/Project/trading_app/strategies/silver_bullet.py) | **Refactored** | **Fixed PDH/PDL Bug (#11)**: Removed `if day_high > 0: pdh = day_high`. **Removed duplicate conflicting `is_gold` definition (#12)**: Unified to `is_gold = "gold" in symbol.lower()`. Integrated `risk_engine` (`build_order_ticket`, `sl_buffer`, `MIN_RR`). |
| [`strategies/spean_strategy.py`](file:///d:/Project/trading_app/strategies/spean_strategy.py) | **Refactored** | **Clarified Session Extreme vs PDH/PDL (#14)**: Labeled `day_high`/`day_low` as `"TODAY'S SESSION EXTREME"`, while PDH/PDL is derived from prior daily candle `c_1d[-2]`. Integrated `risk_engine` (`build_order_ticket`, `sl_buffer`, `MIN_RR`). |
| [`strategies/praveen_strategy.py`](file:///d:/Project/trading_app/strategies/praveen_strategy.py) | **Refactored** | **Replaced rolling-window SMT (#10)** with `smt_engine.check_smt_divergence` and `check_ssmt_divergence`. Correlated SMT pair set to `SPX500` (excluding GOLD). Integrated `risk_engine` (`build_order_ticket`, `sl_buffer`, `MIN_RR`). |
| [`strategies/ict_market_maker.py`](file:///d:/Project/trading_app/strategies/ict_market_maker.py) | **Refactored** | **Updated SMT pairing (#16)**: Line 16 docstring corrected from `NAS100 vs GOLD` to `NAS100 vs SPX500 / NQ vs MES`. Replaced internal `_smt_divergence_recent` with `smt_engine.check_smt_divergence`. Updated `min_risk_reward = MIN_RR (2.0)` and integrated `risk_engine` (`build_order_ticket`, `sl_buffer`). |
| [`strategies/session_breakout.py`](file:///d:/Project/trading_app/strategies/session_breakout.py) | **Refactored** | **Standardized SL buffer & risk (#15)**: Replaced hardcoded buffers (6.0/1.0) with `sl_buffer(symbol)`. Replaced manual ticket creation with `build_order_ticket`. Replaced `(proj_profit / 100.0) * 100` with genuine `consistency_pct` against account balance. Set `MIN_RR = 2.0`. |
| [`strategies/strategy_manager.py`](file:///d:/Project/trading_app/strategies/strategy_manager.py) | **Verified** | Verified strategy registry, constructor signatures, and polymorphic `evaluate()` methods across all strategies. |

---

## 2. Before & After Code: PDH/PDL Bug Resolution

### The Bug (Identified in `smc_liquidity_master.py` & `silver_bullet.py`)
Previously, the code correctly read the prior daily candle `c_1d[-2]` into `pdh` and `pdl`. However, it immediately followed with:
```python
if day_high > 0:
    pdh = day_high
if day_low > 0:
    pdl = day_low
```
Because `day_high` and `day_low` represent **today's live intraday session high and low**, this logic overwrote the **Prior Day's High and Low** with **Today's High and Low** as soon as the market opened. Any sweep of PDH was actually measuring a sweep of today's current session extreme, invalidating ICT daily bias, liquidity sweeps, and DOL (Draw On Liquidity).

### The Fix

#### `smc_liquidity_master.py`
```diff
-        # Overnight / Prior session levels
-        pdh = c_1d[-2]['high'] if len(c_1d) >= 2 else (c_1h[-24]['high'] if len(c_1h) >= 24 else current_price)
-        pdl = c_1d[-2]['low'] if len(c_1d) >= 2 else (c_1h[-24]['low'] if len(c_1h) >= 24 else current_price)
-        if day_high > 0:
-            pdh = day_high
-        if day_low > 0:
-            pdl = day_low
+        # Authentic Prior Day High / Low (PDH/PDL) strictly from prior completed daily candle
+        if len(c_1d) >= 2:
+            pdh = float(c_1d[-2]["high"])
+            pdl = float(c_1d[-2]["low"])
+        elif len(c_1h) >= 24:
+            pdh = max(float(c["high"]) for c in c_1h[-24:])
+            pdl = min(float(c["low"]) for c in c_1h[-24:])
+        else:
+            pdh = current_price
+            pdl = current_price
+
+        # Today's live intraday session extremes are tracked separately
+        today_high = float(day_high) if day_high > 0 else current_price
+        today_low = float(day_low) if day_low > 0 else current_price
```

#### `silver_bullet.py`
```diff
-        pdh = c_1d[-2]['high'] if len(c_1d) >= 2 else (c_1h[-24]['high'] if len(c_1h) >= 24 else current_price)
-        pdl = c_1d[-2]['low'] if len(c_1d) >= 2 else (c_1h[-24]['low'] if len(c_1h) >= 24 else current_price)
-        if day_high > 0:
-            pdh = day_high
-        if day_low > 0:
-            pdl = day_low
+        # Authentic Prior Day High / Low (PDH/PDL) strictly from prior completed daily bar
+        if len(c_1d) >= 2:
+            pdh = float(c_1d[-2]["high"])
+            pdl = float(c_1d[-2]["low"])
+        elif len(c_1h) >= 24:
+            pdh = max(float(c["high"]) for c in c_1h[-24:])
+            pdl = min(float(c["low"]) for c in c_1h[-24:])
+        else:
+            pdh = current_price
+            pdl = current_price
```

---

## 3. SMT Correlated Pair Mapping Matrix

Under ICT principles, SMT Divergence compares **correlated assets in the same asset class** (equity index vs equity index) that should move together. SMT between an equity index (NAS100) and a commodity (GOLD) is invalid due to divergent macro drivers, market hours, and currency dynamics.

| Strategy | Legacy SMT Pairing | Refactored SMT Pairing | Engine / Module |
| :--- | :--- | :--- | :--- |
| **`praveen_strategy.py`** | NAS100 <-> GOLD | **NAS100 <-> SPX500**, **NQ <-> MES** | `backend.smt_engine` (`check_smt_divergence`, `check_ssmt_divergence`) |
| **`ict_market_maker.py`** | NAS100 <-> GOLD (docstring & code) | **NAS100 <-> SPX500**, **NQ <-> MES** | `backend.smt_engine` (`check_smt_divergence`) |
| **`market_data.py`** | NAS100 <-> GOLD | **NAS100 <-> SPX500**, **SPX500 <-> NAS100** | `backend.market_data` (`SMT_PAIRS`, `align_series`) |
| **`backend.smt_engine`** | None | Enforces `SMT_PAIRS`, rejects `GOLD` immediately | `backend.smt_engine` |

Timestamp alignment is guaranteed prior to swing analysis via `align_series()`: only candles with identical UTC minute timestamps are evaluated.

---

## 4. Standardized Risk & Consistency Parameters

All strategies now import directly from [`backend/risk_engine.py`](file:///d:/Project/trading_app/backend/risk_engine.py).

### Enforced Constants
- **Account Model**: Goat Funded Trader \$1,000 Challenge
- **Risk Per Trade**: \$2.50 (0.25% of balance)
- **Minimum R:R (`MIN_RR`)**: **1:2.0** strictly enforced
- **Consistency Rule**: 15% Maximum Profit Cap (`CONSISTENCY_CAP_PCT = 0.15`)
- **True Consistency Calculation**:
  $$\text{Consistency \%} = \left(\frac{\text{Projected Profit}}{\text{Account Balance}}\right) \times 100$$
  *(Replaced the previous no-op `(profit / 100.0) * 100`)*

### Instrument Stop-Loss Buffers (`sl_buffer`)
| Instrument | Standard SL Buffer | ATR Fallback Formula |
| :--- | :--- | :--- |
| **NAS100 / NQ** | **3.0 pts** | $\max(0.5 \times \text{ATR}, 2.4\text{ pts})$ |
| **SPX500 / MES** | **1.5 pts** | $\max(0.5 \times \text{ATR}, 1.2\text{ pts})$ |
| **GOLD (XAUUSD)** | **1.0 pt (\$0.10)** | $\max(0.5 \times \text{ATR}, 0.8\text{ pts})$ |

---

## 5. Yahoo Finance Elimination Verification

Execution of `git grep -i "yahoo"` across the repository confirms complete removal:
```
backend/market_data.py:Zero Yahoo Finance scraping, zero synthetic offset hacks.
```
Execution of `git grep -i "query1"`:
```
(No results - 0 matches)
```
Execution of `git grep -i "broker_offset"` and `_calib`:
```
(No results - 0 matches)
```

---

## 6. Live TradingView WebSocket Feed Verification

Live test execution via `backend/tv_feed.py` and `backend/market_data.py` confirmed live multi-instrument reception:
```
tv_feed task launched. Listening for real-time prices & candles...
Second 1: US100=0.0 (0 bars), SPX500=0.0 (0 bars), GOLD=0.0
Second 2: US100=0.0 (0 bars), SPX500=0.0 (0 bars), GOLD=0.0
Second 3: US100=30635.2 (300 bars), SPX500=7743.4 (100 bars), GOLD=4285.39
VERIFIED! Live stream active for all instruments.
```

All 6 strategies (`smc_master`, `ict_market_maker`, `praveen_strategy`, `spean_strategy`, `silver_bullet`, `session_breakout`) evaluate cleanly and output uniform Goat \$1,000 order tickets.
