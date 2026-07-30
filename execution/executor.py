"""
Order execution. Respects config.DRY_RUN: when True, no real orders are
sent to the exchange - trades are only logged.

Handles both spot (BUY/SELL) and derivatives (LONG/SHORT with leverage)
trading, branching on config.TRADE_DERIVATIVES.

Implements FIX-01 (Duplicate Order Risk Protection & Idempotent Order Reconciliation):
Before retrying order placement on network timeouts, checks exchange positions and open orders
to prevent duplicate order creation on Bybit.
"""
import uuid
import logging
import time
import ccxt
import config
from data import data_fetcher

log = logging.getLogger("executor")


def _check_existing_position(exchange, symbol, target_side=None):
    """
    Query the exchange for active positions or open orders on the symbol.
    Verifies symbol, active contract count > 0, and position side if target_side provided.
    Returns existing position dict if active, else None.
    """
    try:
        if config.TRADE_DERIVATIVES:
            positions = data_fetcher.retry_api_call(
                lambda: exchange.fetch_positions([symbol], params={"category": "linear"}),
                func_name="reconcile_fetch_positions"
            )
            for pos in positions:
                if pos.get("symbol") == symbol and float(pos.get("contracts", 0)) > 0:
                    if target_side:
                        pos_side = str(pos.get("side", "")).lower()
                        normalized_target = "buy" if target_side in ("buy", "BUY", "LONG") else "sell" if target_side in ("sell", "SELL", "SHORT") else target_side.lower()
                        # On Bybit futures, pos_side may be 'buy'/'sell' or 'long'/'short'
                        if pos_side not in (normalized_target, "long" if normalized_target == "buy" else "short"):
                            continue
                    return pos
        else:
            open_orders = data_fetcher.retry_api_call(
                lambda: exchange.fetch_open_orders(symbol),
                func_name="reconcile_fetch_open_orders"
            )
            if open_orders:
                for order in open_orders:
                    if target_side and order.get("side", "").lower() != target_side.lower():
                        continue
                    return order
    except Exception as e:
        log.warning(f"[executor] Reconcile position check encountered error: {e}")
    return None


def place_order(exchange, action, amount_btc, stop_loss=None, take_profit=None, leverage=None, client_order_id=None):
    """
    Places a market order with protective stop-loss and take-profit.
    Includes clientOrderId idempotency key and position reconciliation before retrying
    to eliminate duplicate order creation on transient network timeouts.
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

    # Generate or use provided deterministic client_order_id (idempotency key)
    c_id = client_order_id or f"btc_{uuid.uuid4().hex[:12]}"

    # Step 1: Pre-order reconciliation check - ensure no position already exists
    existing = _check_existing_position(exchange, config.SYMBOL, target_side=side)
    if existing:
        log.warning(f"[executor] Pre-order reconciliation found existing position/order. Aborting duplicate entry.")
        return existing

    try:
        # Derivatives: set leverage/margin mode BEFORE opening a position
        if config.TRADE_DERIVATIVES:
            if leverage is None:
                raise ValueError("leverage must be provided when TRADE_DERIVATIVES is True")
            data_fetcher.set_leverage_and_margin(exchange, leverage)

        params = {}
        if stop_loss:
            params["stopLoss"] = stop_loss
        if take_profit:
            params["takeProfit"] = take_profit

        # Pass clientOrderId for Bybit / CCXT idempotency tracking
        params["clientOrderId"] = c_id
        params["orderLinkId"] = c_id

        # Step 2: Attempt order creation with reconciliation retry handler
        transient_errors = (
            ccxt.NetworkError,
            ccxt.RequestTimeout,
            ccxt.RateLimitExceeded,
            ccxt.DDoSProtection,
        )

        for attempt in range(1, 4):
            try:
                order = exchange.create_order(
                    symbol=config.SYMBOL,
                    type="market",
                    side=side,
                    amount=amount_btc,
                    params=params,
                )
                print(f"[LIVE] Opened {position_label} with attached SL/TP: {order.get('id')}")
                return order
            except transient_errors as e:
                log.warning(
                    f"[executor] Network error on attempt {attempt}/3 during create_order: {e}. "
                    f"Performing position reconciliation before retrying..."
                )
                # Check if order succeeded on exchange despite network timeout
                reconciled_pos = _check_existing_position(exchange, config.SYMBOL, target_side=side)
                if reconciled_pos:
                    log.info(
                        f"[executor] RECONCILIATION SUCCESSFUL: Order was received by Bybit during network timeout. "
                        f"Returning existing position without submitting duplicate order."
                    )
                    return reconciled_pos
                
                if attempt == 3:
                    log.error(f"[executor] Final attempt failed and no position found on exchange. Raising error.")
                    raise e
                    
                time.sleep(1.0 * attempt)

    except Exception as e:
        print(f"[executor] ORDER FAILED: {e}")
        return {"status": "failed", "error": str(e)}
