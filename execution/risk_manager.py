"""
Risk management: figures out how much to trade and where to place
stop-loss / take-profit levels, based on account balance and volatility (ATR).
"""
import logging
import time
from typing import Optional
import config
from notifications import notify
from notifications.templates import build_trade_skipped_lot_size

log = logging.getLogger("btc_trader.risk_manager")

_last_lot_size_skip_time = 0
_LOT_SIZE_SKIP_COOLDOWN_SEC = 3600  # 1 hour suppression window


def reset_lot_size_skip_cooldown():
    """Reset lot size skip cooldown timestamp (primarily for testing)."""
    global _last_lot_size_skip_time
    _last_lot_size_skip_time = 0


def _notify_lot_size_skipped(
    calculated_size_btc: float,
    min_lot_size_btc: float,
    balance_usdt: float,
    confidence: Optional[float] = None
):
    global _last_lot_size_skip_time
    now = time.time()
    if now - _last_lot_size_skip_time < _LOT_SIZE_SKIP_COOLDOWN_SEC:
        log.debug(f"Lot size skip notification suppressed by cooldown (last sent {now - _last_lot_size_skip_time:.1f}s ago).")
        return
    _last_lot_size_skip_time = now
    try:
        event = build_trade_skipped_lot_size(
            calculated_size_btc=calculated_size_btc,
            min_lot_size_btc=min_lot_size_btc,
            risk_pct=config.RISK_PER_TRADE_PCT,
            balance_usdt=balance_usdt,
            confidence=confidence
        )
        notify(event)
    except Exception as e:
        log.error(f"Failed to dispatch trade skipped notification: {e}")


def calculate_position_size(balance_usdt, entry_price, atr, confidence=None):
    """
    Risk a fixed % of account balance per trade. Position size is derived
    from how far away the stop-loss is (in ATR terms), so bigger stops
    automatically mean smaller position size.
    """
    risk_amount = balance_usdt * (config.RISK_PER_TRADE_PCT / 100)
    stop_distance = atr * config.STOP_LOSS_ATR_MULT

    if stop_distance <= 0:
        return 0

    # How many BTC we can buy such that a stop-out only loses `risk_amount`
    position_size_btc = risk_amount / stop_distance
    position_value_usdt = position_size_btc * entry_price

    # Minimum lot size on Bybit for BTC/USDT perpetuals is 0.001 BTC
    MIN_LOT_SIZE_BTC = 0.001
    final_size = round(position_size_btc, 6)
    if final_size < MIN_LOT_SIZE_BTC:
        _notify_lot_size_skipped(position_size_btc, MIN_LOT_SIZE_BTC, balance_usdt, confidence)
        return 0

    return final_size


def calculate_stop_and_target(entry_price, atr, direction):
    """Return (stop_loss_price, take_profit_price) for a BUY or SELL."""
    stop_distance = atr * config.STOP_LOSS_ATR_MULT
    target_distance = atr * config.TAKE_PROFIT_ATR_MULT

    if direction in ("BUY", "LONG"):
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + target_distance
    elif direction in ("SELL", "SHORT"):
        stop_loss = entry_price + stop_distance
        take_profit = entry_price - target_distance
    else:
        raise ValueError(f"Unrecognized direction in calculate_stop_and_target: {direction}")

    return round(stop_loss, 2), round(take_profit, 2)


# ── Derivatives (futures/perpetual) risk management ──────────────────

def suggest_leverage(entry_price, atr):
    """
    Suggest a leverage value within config.LEVERAGE_MIN/MAX, scaled down
    when volatility is elevated. Higher ATR relative to price means a
    given stop distance represents a bigger % move, so we lean toward
    lower leverage to keep the liquidation price a safe distance away.
    """
    volatility_pct = (atr / entry_price) * 100  # ATR as % of price

    # These thresholds are rough starting points, not tuned to live data -
    # adjust based on what you observe in your own backtests.
    if volatility_pct > 0.6:
        leverage = config.LEVERAGE_MIN
    elif volatility_pct > 0.35:
        leverage = round((config.LEVERAGE_MIN + config.LEVERAGE_MAX) / 2)
    else:
        leverage = config.LEVERAGE_MAX

    return max(config.LEVERAGE_MIN, min(config.LEVERAGE_MAX, leverage))


def calculate_liquidation_price(entry_price, leverage, direction, maintenance_margin_rate=None):
    """
    Estimate the liquidation price for an isolated-margin position.
    This is an approximation - actual liquidation price depends on the
    exchange's exact margin tier rules, funding payments, and fees. Treat
    this as a safety estimate, not an exact figure, and always check the
    exchange's own liquidation price display before trusting it fully.
    """
    mmr = maintenance_margin_rate if maintenance_margin_rate is not None else config.MAINTENANCE_MARGIN_RATE

    if direction in ("BUY", "LONG"):
        liquidation_price = entry_price * (1 - (1 / leverage) + mmr)
    elif direction in ("SELL", "SHORT"):
        liquidation_price = entry_price * (1 + (1 / leverage) - mmr)
    else:
        raise ValueError(f"Unrecognized direction in calculate_liquidation_price: {direction}")

    return round(liquidation_price, 2)


def calculate_derivative_position(balance_usdt, entry_price, atr, direction, leverage=None, confidence=None):
    """
    Full derivatives position sizing: how much to trade, how much margin
    it requires, and where liquidation sits - all based on risking a fixed
    % of account balance, same principle as spot sizing. Leverage changes
    how much margin is tied up, NOT how much you're risking - risk is
    always governed by the stop-loss distance and RISK_PER_TRADE_PCT.

    Returns:
        {
            "position_size_btc": float,
            "position_value_usdt": float,
            "leverage": int,
            "margin_required_usdt": float,
            "liquidation_price": float,
            "stop_loss": float,
            "take_profit": float,
            "distance_to_liquidation_pct": float,  # how far the stop is from liquidation, as a safety check
        }
    """
    if leverage is None:
        leverage = suggest_leverage(entry_price, atr)
    leverage = max(config.LEVERAGE_MIN, min(config.LEVERAGE_MAX, leverage))

    risk_amount = balance_usdt * (config.RISK_PER_TRADE_PCT / 100)
    stop_distance = atr * config.STOP_LOSS_ATR_MULT

    if stop_distance <= 0:
        return None

    # Position size is still driven by risk-per-trade, same as spot -
    # leverage does not increase how much we're willing to lose.
    position_size_btc = risk_amount / stop_distance
    position_value_usdt = position_size_btc * entry_price

    margin_required = position_value_usdt / leverage

    # Never require more margin than the account actually has.
    if margin_required > balance_usdt:
        margin_required = balance_usdt
        position_value_usdt = margin_required * leverage
        position_size_btc = position_value_usdt / entry_price

    stop_loss, take_profit = calculate_stop_and_target(entry_price, atr, direction)
    liquidation_price = calculate_liquidation_price(entry_price, leverage, direction)

    # Sanity check: the stop-loss should trigger well before liquidation.
    # If it doesn't, the leverage is too high for this stop distance.
    if direction in ("BUY", "LONG"):
        distance_to_liq_pct = ((entry_price - liquidation_price) / entry_price) * 100
        stop_is_safe = stop_loss > liquidation_price
    elif direction in ("SELL", "SHORT"):
        distance_to_liq_pct = ((liquidation_price - entry_price) / entry_price) * 100
        stop_is_safe = stop_loss < liquidation_price
    else:
        raise ValueError(f"Unrecognized direction in calculate_derivative_position: {direction}")

    MIN_LOT_SIZE_BTC = 0.001
    final_size = round(position_size_btc, 6)
    if final_size < MIN_LOT_SIZE_BTC:
        _notify_lot_size_skipped(position_size_btc, MIN_LOT_SIZE_BTC, balance_usdt, confidence)
        return None

    return {
        "position_size_btc": final_size,
        "position_value_usdt": round(position_value_usdt, 2),
        "leverage": leverage,
        "margin_required_usdt": round(margin_required, 2),
        "liquidation_price": liquidation_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "distance_to_liquidation_pct": round(distance_to_liq_pct, 2),
        "stop_is_safe": stop_is_safe,
    }

