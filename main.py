"""
Main entry point. Runs the BTC/USDT trading loop:
  1. Fetch candles
  2. If a position is open, check whether price hit stop-loss/take-profit
  3. Run the decision engine (patterns + indicators + Fib + S/R + ADX)
  4. Log every decision to the trade journal
  5. If confidence is high enough and flat, size the trade and execute it
  6. Sleep, repeat
"""
import time
import logging
import sys

import config
from data import data_fetcher
from strategies import strategy
from execution import risk_manager
from execution import executor
from strategies import trading_style
from journal import trade_journal
import state_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("btc_trader")


def check_position_exit(exchange, open_position, current_price):
    """
    Check if the position is closed. In DRY_RUN, simulates via price.
    In LIVE, queries the exchange for actual position state.
    """
    if config.DRY_RUN:
        side = open_position["side"]
        sl = open_position["stop_loss"]
        tp = open_position["take_profit"]

        if side in ("BUY", "LONG"):
            if current_price <= sl: return "loss", sl
            if current_price >= tp: return "win", tp
        elif side in ("SELL", "SHORT"):
            if current_price >= sl: return "loss", sl
            if current_price <= tp: return "win", tp
        else:
            raise ValueError(f"Unrecognized side in check_position_exit: {side}")
        return None, None
    else:
        try:
            positions = exchange.fetch_positions([config.SYMBOL])
            for pos in positions:
                if pos['symbol'] == config.SYMBOL:
                    if pos['contracts'] == 0:
                        # Position is closed
                        is_win = (current_price > open_position["entry"] if open_position["side"] in ("BUY", "LONG") else current_price < open_position["entry"])
                        outcome = "win" if is_win else "loss"
                        # Estimate exit price based on outcome to keep journal clean
                        exit_price = open_position["take_profit"] if outcome == "win" else open_position["stop_loss"]
                        return outcome, exit_price
                    else:
                        return None, None
                        
            # If no position object was returned for the symbol at all, it's closed
            is_win = (current_price > open_position["entry"] if open_position["side"] in ("BUY", "LONG") else current_price < open_position["entry"])
            outcome = "win" if is_win else "loss"
            exit_price = open_position["take_profit"] if outcome == "win" else open_position["stop_loss"]
            return outcome, exit_price
            
        except Exception as e:
            log.error(f"Failed to check position exit state: {e}")
            return None, None


def run_once(exchange, open_position, state_callback=None):
    df = data_fetcher.fetch_candles(exchange)
    current_price = df["close"].iloc[-1]
    
    if state_callback:
        state_callback(price=current_price)

    # ── Manage an existing position first ─────────────────────────────
    if open_position:
        outcome, exit_price = check_position_exit(exchange, open_position, current_price)
        if outcome:
            pnl_per_coin = (
                exit_price - open_position["entry"]
                if open_position["side"] in ("BUY", "LONG")
                else open_position["entry"] - exit_price
            )
            pnl_usdt = pnl_per_coin * open_position["amount"]

            log.info(
                f"Position closed | {open_position['side']} | outcome={outcome} | "
                f"exit={exit_price} | pnl={pnl_usdt:.2f} USDT"
            )
            trade_journal.close_trade(
                open_position["trade_id"], exit_price, outcome, round(pnl_usdt, 2)
            )
            state_manager.clear_state()
            return None  # flat again, free to look for a new entry next cycle

        log.info(
            f"Position still open ({open_position['side']} @ {open_position['entry']}) | "
            f"current={current_price:.2f} | SL={open_position['stop_loss']} | "
            f"TP={open_position['take_profit']}"
        )

    # ── Flat: evaluate a new signal ─────────────────────────────────────
    signal = strategy.evaluate(df)

    hypo_risk = None
    if not open_position:
        bull_count = len(signal.get("bull_case", []))
        bear_count = len(signal.get("bear_case", []))
        
        if signal["action"] in ("LONG", "SHORT"):
            hypo_dir = signal["action"]
        else:
            hypo_dir = "LONG" if bull_count >= bear_count else "SHORT"
            
        try:
            balance = data_fetcher.get_account_balance(exchange, "USDT")
            if config.TRADE_DERIVATIVES:
                hypo_risk = risk_manager.calculate_derivative_position(
                    balance, signal["price"], signal["atr"], hypo_dir
                )
            else:
                amt = risk_manager.calculate_position_size(balance, signal["price"], signal["atr"])
                sl, tp = risk_manager.calculate_stop_and_target(signal["price"], signal["atr"], hypo_dir)
                hypo_risk = {
                    "position_size_btc": amt,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "leverage": 1,
                    "margin_required_usdt": (amt * signal["price"]) if amt else 0
                }
        except Exception as e:
            log.warning(f"Could not calculate hypothetical risk for UI: {e}")

    ui_signal = signal["action"]
    if ui_signal in ("LONG", "SHORT") and signal["confidence"] < config.MIN_CONFIDENCE_TO_TRADE:
        ui_signal = "WAIT"

    if state_callback:
        state_callback(
            signal=ui_signal, 
            confidence=signal["confidence"], 
            reasons=signal.get("reasons", []),
            bull_case=signal.get("bull_case", []),
            bear_case=signal.get("bear_case", []),
            hypothetical_risk=hypo_risk
        )
        
    if open_position:
        return open_position

    log.info(
        f"Price={signal['price']:.2f} | Action={signal['action']} | "
        f"Confidence={signal['confidence']}"
    )
    for reason in signal["reasons"]:
        log.info(f"  - {reason}")

    if signal["action"] == "WAIT":
        trade_journal.log_decision(
            signal, decision="WAIT", exchange_id=config.EXCHANGE_ID, symbol=config.SYMBOL
        )
        return None

    if signal["confidence"] < config.MIN_CONFIDENCE_TO_TRADE:
        log.info(
            f"Confidence {signal['confidence']} below threshold "
            f"{config.MIN_CONFIDENCE_TO_TRADE}, skipping trade."
        )
        trade_journal.log_decision(
            signal, decision="WAIT", exchange_id=config.EXCHANGE_ID, symbol=config.SYMBOL
        )
        return None

    # Guard: Ensure we successfully calculated position sizing
    if hypo_risk is None:
        log.error("Execution aborted: hypothetical risk data is missing (likely a balance fetch failure).")
        trade_journal.log_decision(
            signal, decision="WAIT", exchange_id=config.EXCHANGE_ID, symbol=config.SYMBOL
        )
        return None

    amount_btc = hypo_risk["position_size_btc"]
    stop_loss = hypo_risk["stop_loss"]
    take_profit = hypo_risk["take_profit"]

    if amount_btc <= 0:
        log.warning("Calculated position size is 0, skipping trade.")
        trade_journal.log_decision(
            signal, decision="WAIT", exchange_id=config.EXCHANGE_ID, symbol=config.SYMBOL
        )
        return None

    trade_id = trade_journal.new_trade_id()
    trade_journal.log_decision(
        signal,
        decision=signal["action"],
        exchange_id=config.EXCHANGE_ID,
        symbol=config.SYMBOL,
        risk_pct=config.RISK_PER_TRADE_PCT,
        entry_price=signal["price"],
        stop_loss=stop_loss,
        take_profit=take_profit,
        trade_id=trade_id,
    )

    if config.TRADE_DERIVATIVES:
        result = executor.place_order(
            exchange, signal["action"], amount_btc, stop_loss, take_profit, leverage=hypo_risk["leverage"]
        )
    else:
        result = executor.place_order(exchange, signal["action"], amount_btc, stop_loss, take_profit)
        
    log.info(f"Order result: {result}")

    open_position = {
        "trade_id": trade_id,
        "side": signal["action"],
        "amount": amount_btc,
        "entry": signal["price"],
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }
    state_manager.save_state(open_position)
    return open_position


def confirm_live_trading():
    print("\n" + "!" * 60)
    print("WARNING: USE_TESTNET is False and DRY_RUN is False.")
    print("This run will place REAL orders with REAL money.")
    print("!" * 60)
    answer = input("\nType 'I UNDERSTAND' to proceed, or anything else to cancel: ").strip()
    if answer != "I UNDERSTAND":
        print("Cancelled. No orders will be placed.")
        raise SystemExit(0)


def main():
    style = trading_style.ask_trading_style()
    trading_style.apply_profile(style, config)

    if not config.USE_TESTNET and not config.DRY_RUN:
        confirm_live_trading()

    mode = "TESTNET" if config.USE_TESTNET else "LIVE"
    if config.DRY_RUN:
        mode += " (DRY RUN - no orders will be placed)"

    log.info(f"Trading style selected: {style.upper()}")
    log.info(f"  Timeframe: {config.TIMEFRAME} | Poll every {config.POLL_INTERVAL_SECONDS}s | "
              f"Min confidence: {config.MIN_CONFIDENCE_TO_TRADE} | "
              f"SL/TP ATR mult: {config.STOP_LOSS_ATR_MULT}/{config.TAKE_PROFIT_ATR_MULT}")
    log.info(f"Starting BTC/USDT bot | MODE={mode} | Exchange={config.EXCHANGE_ID}")

    exchange = data_fetcher.get_exchange()
    open_position = state_manager.load_state(exchange, config.SYMBOL)
    
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    while True:
        try:
            open_position = run_once(exchange, open_position)
            consecutive_errors = 0  # reset on success
        except Exception as e:
            consecutive_errors += 1
            log.error(f"Error in main loop ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.critical("CIRCUIT BREAKER TRIGGERED: Too many consecutive errors. Safely halting operations.")
                break

        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
