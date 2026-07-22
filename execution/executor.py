"""
Order execution. Respects config.DRY_RUN: when True, no real orders are
sent to the exchange - trades are only logged.

Handles both spot (BUY/SELL) and derivatives (LONG/SHORT with leverage)
trading, branching on config.TRADE_DERIVATIVES.
"""
import config
from data import data_fetcher


def place_order(exchange, action, amount_btc, stop_loss=None, take_profit=None, leverage=None):
    """
    Places a market order, then attaches a stop-loss and take-profit as
    protective orders when live.

    For derivatives (config.TRADE_DERIVATIVES=True), this also sets leverage
    and margin mode on the exchange BEFORE placing the entry order.

    action: "BUY"/"LONG" to open a long, "SELL"/"SHORT" to open a short.
    In DRY_RUN mode, nothing is actually sent to the exchange.
    """
    if action in ("BUY", "LONG"):
        side = "buy"
    elif action in ("SELL", "SHORT"):
        side = "sell"
    else:
        raise ValueError(f"Unrecognized action in place_order: {action}")
    if config.TRADE_DERIVATIVES:
        position_label = "LONG" if side == "buy" else "SHORT"
    else:
        position_label = "BUY" if side == "buy" else "SELL"

    if config.DRY_RUN:
        leverage_note = f" | Leverage={leverage}x" if config.TRADE_DERIVATIVES else ""
        print(f"[DRY RUN] Would open {position_label} for {amount_btc} BTC "
              f"| SL={stop_loss} TP={take_profit}{leverage_note}")
        return {
            "status": "simulated",
            "side": side,
            "position": position_label,
            "amount": amount_btc,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "leverage": leverage,
        }

    try:
        # ── Derivatives: set leverage/margin mode BEFORE opening a position ──
        if config.TRADE_DERIVATIVES:
            if leverage is None:
                raise ValueError("leverage must be provided when TRADE_DERIVATIVES is True")
            data_fetcher.set_leverage_and_margin(exchange, leverage)

        # ── Bybit: unified API lets you attach SL/TP directly on entry ──
        params = {}
        if stop_loss:
            params["stopLoss"] = stop_loss
        if take_profit:
            params["takeProfit"] = take_profit

        order = exchange.create_order(
            symbol=config.SYMBOL,
            type="market",
            side=side,
            amount=amount_btc,
            params=params,
        )
        print(f"[LIVE] Opened {position_label} with attached SL/TP: {order.get('id')}")
        return order

    except Exception as e:
        print(f"[executor] ORDER FAILED: {e}")
        return {"status": "failed", "error": str(e)}
