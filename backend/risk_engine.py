"""
TraderPro Risk Engine & Order Ticket Generator
Standardized risk framework compliant with Goat Funded Trader ($1,000 Account Model).
Provides uniform risk parameters, ATR/instrument SL buffers, consistency impact calculations,
and centralized order ticket creation across all trading strategies.
"""

from typing import Dict, Any, Optional

# Standard Goat Funded Trader ($1,000) Constants
DEFAULT_ACCOUNT_BALANCE: float = 1000.0
DEFAULT_RISK_PER_TRADE: float = 2.50      # $2.50 per trade (0.25% of $1,000 balance)
MIN_RR: float = 2.0                      # Strict 1:2+ R:R minimum standardized across all ICT strategies
CONSISTENCY_CAP_PCT: float = 0.15        # 15% consistency rule: no single trade > 15% of total profits


# Standard Stop Loss Buffers per Instrument (points/pips)
STANDARD_SL_BUFFERS: Dict[str, float] = {
    "NAS100": 3.0,
    "NQ": 3.0,
    "SPX500": 1.5,
    "MES": 1.5,
    "GOLD": 1.0,
}


def consistency_pct(
    projected_gain: float,
    account_balance: float = DEFAULT_ACCOUNT_BALANCE,
    cap_pct: float = CONSISTENCY_CAP_PCT
) -> float:
    """
    Computes projected trade gain as a genuine percentage of the actual account balance.
    Replaces the previous no-op '(x / 100.0) * 100' calculation.
    """
    balance = account_balance if account_balance > 0 else DEFAULT_ACCOUNT_BALANCE
    return round((projected_gain / balance) * 100.0, 2)


def consistency_impact_str(
    projected_gain: float,
    account_balance: float = DEFAULT_ACCOUNT_BALANCE,
    cap_pct: float = CONSISTENCY_CAP_PCT
) -> str:
    """
    Returns user-facing consistency impact string, verifying compliance with the 15% cap.
    """
    pct = consistency_pct(projected_gain, account_balance, cap_pct)
    cap_int = int(cap_pct * 100)
    is_safe = pct < (cap_pct * 100.0)
    status = f"< {cap_int}% Cap Safe" if is_safe else f"EXCEEDS {cap_int}% CAP"
    return f"{pct}% ({status})"


def sl_buffer(symbol: str, atr: Optional[float] = None) -> float:
    """
    Standard SL buffer function across all strategies.
    If ATR (1M or 30M) is provided, calculates an ATR-proportional buffer: max(0.5 * ATR, min_buffer).
    Otherwise returns the standardized per-instrument buffer.
    """
    sym = symbol.upper()
    if "GOLD" in sym:
        base_buffer = STANDARD_SL_BUFFERS.get("GOLD", 1.0)
    elif "SPX" in sym or "MES" in sym:
        base_buffer = STANDARD_SL_BUFFERS.get("SPX500", 1.5)
    else:
        base_buffer = STANDARD_SL_BUFFERS.get("NAS100", 3.0)

    if atr is not None and atr > 0:
        return round(max(atr * 0.5, base_buffer * 0.8), 2)
    return base_buffer


def build_order_ticket(
    order_type: Optional[str] = None,
    symbol: str = "NAS100",
    entry_price: Optional[float] = None,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    account_balance: float = DEFAULT_ACCOUNT_BALANCE,
    risk_per_trade: Optional[float] = None,
    cancel_if: str = "",
    extra_fields: Optional[Dict[str, Any]] = None,
    min_rr: float = MIN_RR,
    direction: Optional[str] = None,
    entry: Optional[float] = None,
    risk_dollars: Optional[float] = None,
    cancel_condition: Optional[str] = None,
    strategy_name: Optional[str] = None,
    strategy: Optional[str] = None,
    **kwargs: Any
) -> Optional[Dict[str, Any]]:
    """
    Constructs a uniform, compliant order ticket dictionary for all strategies.
    Enforces minimum 1:2 R:R and Goat $1k compliance formatting.
    Supports flexible keyword arguments and aliases.
    """
    # Resolve aliases
    strat = strategy_name or strategy or kwargs.get("strategy_id", "TraderPro Strategy")
    if order_type is None:
        order_type = f"{direction.upper()} LIMIT" if direction else "LIMIT"
    if entry_price is None:
        entry_price = entry if entry is not None else 0.0
    if risk_per_trade is None:
        risk_per_trade = risk_dollars if risk_dollars is not None else DEFAULT_RISK_PER_TRADE
    if not cancel_if and cancel_condition:
        cancel_if = cancel_condition

    dec = 2 if "gold" in symbol.lower() else 1
    entry_val = round(entry_price, dec)
    sl = round(stop_loss, dec)
    tp = round(take_profit, dec)

    risk_dist = abs(entry_val - sl)
    reward_dist = abs(tp - entry_val)

    if risk_dist <= 0:
        return None

    calculated_rr = reward_dist / risk_dist

    # Verify minimum R:R compliance
    if calculated_rr < (min_rr - 0.05):
        return None

    projected_gain = round(risk_per_trade * calculated_rr, 2)
    consistency_str = consistency_impact_str(projected_gain, account_balance)

    ticket: Dict[str, Any] = {
        "Order Type": order_type.upper(),
        "Instrument": symbol.upper(),
        "Strategy": strat,
        "strategy": strat,
        "Entry Price": entry_val,
        "Stop Loss": sl,
        "Take Profit": tp,
        "R:R": f"1:{calculated_rr:.2f}",
        "Risk Amount": f"${risk_per_trade:.2f} ({round((risk_per_trade / account_balance) * 100, 2)}%)",
        "Projected Profit": f"+${projected_gain:.2f}",
        "Consistency Impact": consistency_str,
        "Cancel If": cancel_if
    }

    if extra_fields:
        for k, v in extra_fields.items():
            ticket[k] = v

    return ticket
