"""
Backtester: replays historical BTC/USDT candles through strategy.evaluate()
one candle at a time (so it only ever sees "past" data, like it would live),
simulates trade entries/exits against stop-loss/take-profit, and reports
performance metrics.

Three ways to get historical data:
  1. Fetch last N days from Bybit:  python3 backtest.py --fetch --days 90
  2. Fetch explicit date range:     python3 backtest.py --start 2025-10-01 --end 2025-12-31
  3. Use a saved CSV:               python3 backtest.py --csv historical_data.csv
     (CSV must have columns: timestamp, open, high, low, close, volume)
"""
import argparse
import pandas as pd

import config
from data import data_fetcher
from strategies import strategy
from execution import risk_manager
from strategies import trading_style


def fetch_historical(days):
    """Fetch `days` worth of historical candles counting back from now.

    Bybit V5 returns at most 1000 candles per request. We page forward by
    advancing `since` to the timestamp after the last candle in each batch,
    repeating until we have all the candles we need or the exchange has no
    more data to return.
    """
    exchange = data_fetcher.get_exchange()
    timeframe_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    minutes = timeframe_minutes.get(config.TIMEFRAME, 15)
    candles_needed = int((days * 24 * 60) / minutes)

    print(f"  Need {candles_needed} candles for {days} days at {config.TIMEFRAME} intervals.")

    all_candles = []
    since = exchange.milliseconds() - days * 24 * 60 * 60 * 1000

    while len(all_candles) < candles_needed:
        batch = exchange.fetch_ohlcv(config.SYMBOL, timeframe=config.TIMEFRAME, since=since, limit=1000)

        # No more data from the exchange — we've reached the present
        if not batch:
            break

        all_candles += batch
        last_ts = batch[-1][0]
        since = last_ts + 1  # advance past the last received candle

        print(f"  Fetched {len(all_candles)}/{candles_needed} candles...", end="\r")

        # If the last candle is in the future (or at current time), we're done
        now_ms = exchange.milliseconds()
        if last_ts >= now_ms:
            break

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp").reset_index(drop=True)
    return df


def fetch_historical_range(start_date, end_date):
    """Fetch candles for an explicit calendar date range (UTC).

    Args:
        start_date: ISO date string, e.g. "2025-10-01"  (inclusive, start of day UTC)
        end_date:   ISO date string, e.g. "2025-12-31"  (inclusive, end of day UTC)

    Pages through the exchange the same way fetch_historical() does, but uses
    the supplied timestamps as hard boundaries instead of counting back from now.
    """
    import datetime

    # Parse to UTC midnight timestamps
    start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").replace(
        tzinfo=datetime.timezone.utc
    )
    # End date: use end-of-day (23:59:59) so the full day is included
    end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").replace(
        tzinfo=datetime.timezone.utc,
        hour=23, minute=59, second=59,
    )

    since_ms = int(start_dt.timestamp() * 1000)
    until_ms  = int(end_dt.timestamp() * 1000)

    if since_ms >= until_ms:
        raise ValueError(f"--start ({start_date}) must be before --end ({end_date})")

    exchange = data_fetcher.get_exchange()
    all_candles = []
    since = since_ms

    print(f"  Fetching {config.SYMBOL} {config.TIMEFRAME} candles "
          f"from {start_date} to {end_date} (UTC)...")

    while True:
        raw_batch = exchange.fetch_ohlcv(
            config.SYMBOL, timeframe=config.TIMEFRAME, since=since, limit=1000
        )

        # Exchange returned nothing — no more data available at all
        if not raw_batch:
            break

        # Trim candles that fall past the end boundary AFTER capturing raw length.
        # BUG FIX: we must check len(raw_batch) < 1000 (not the trimmed batch)
        # to detect end-of-exchange-data.  The trimmed batch can be short simply
        # because boundary filtering removed candles, not because the exchange
        # ran out — using the trimmed length caused a false early exit at ~1999
        # candles for any range where the first 1000-candle page overlapped the
        # end date.
        raw_count = len(raw_batch)
        batch = [c for c in raw_batch if c[0] <= until_ms]
        all_candles += batch

        last_ts = raw_batch[-1][0]  # use raw last ts to detect boundary crossing
        print(f"  Fetched {len(all_candles)} candles...", end="\r")

        # Stop conditions (order matters):
        #   1. The last candle the exchange returned is at or past our end date
        #      — we've collected everything up to the boundary.
        #   2. The exchange returned fewer than the requested 1000 — it has no
        #      more data in this direction (use raw_count, not trimmed length).
        if last_ts >= until_ms or raw_count < 1000:
            break

        since = last_ts + 1

    print()  # newline after the \r progress line

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp").reset_index(drop=True)
    return df


def load_csv(path):
    df = pd.read_csv(path, parse_dates=["timestamp"])
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")
    return df.sort_values("timestamp").reset_index(drop=True)


def run_backtest(df, starting_balance=10000, min_window=50):
    """
    Walk forward through the candles one at a time. At each step, only the
    candles up to "now" are visible to the strategy (no lookahead bias).
    """
    balance = starting_balance
    trades = []
    open_trade = None

    for i in range(min_window, len(df)):
        window = df.iloc[: i + 1]
        current_candle = df.iloc[i]

        # ── Manage an open trade: check if stop-loss or take-profit was hit ──
        if open_trade:
            if open_trade["side"] in ("BUY", "LONG"):
                hit_sl = current_candle["low"] <= open_trade["stop_loss"]
                hit_tp = current_candle["high"] >= open_trade["take_profit"]
            elif open_trade["side"] in ("SELL", "SHORT"):
                hit_sl = current_candle["high"] >= open_trade["stop_loss"]
                hit_tp = current_candle["low"] <= open_trade["take_profit"]
            else:
                raise ValueError(f"Unrecognized side in backtest: {open_trade['side']}")

            exit_price = None
            outcome = None
            if hit_sl:
                exit_price = open_trade["stop_loss"]
                outcome = "loss"
            elif hit_tp:
                exit_price = open_trade["take_profit"]
                outcome = "win"

            if exit_price is not None:
                # Calculate gross PnL
                pnl_per_coin = (
                    exit_price - open_trade["entry"]
                    if open_trade["side"] in ("BUY", "LONG")
                    else open_trade["entry"] - exit_price
                )
                gross_pnl_usdt = pnl_per_coin * open_trade["amount"]

                # Deduct fees and slippage (Assume 0.1% per side for market orders)
                # 0.1% = 0.05% taker fee + 0.05% slippage
                entry_value = open_trade["entry"] * open_trade["amount"]
                exit_value = exit_price * open_trade["amount"]
                total_fees = (entry_value * 0.001) + (exit_value * 0.001)

                net_pnl_usdt = gross_pnl_usdt - total_fees
                
                # A trade is only a win if the net PnL is positive
                final_outcome = "win" if net_pnl_usdt > 0 else "loss"

                balance += net_pnl_usdt

                trades.append({
                    "entry_time": open_trade["entry_time"],
                    "exit_time": current_candle["timestamp"],
                    "side": open_trade["side"],
                    "entry": open_trade["entry"],
                    "exit": exit_price,
                    "outcome": final_outcome,
                    "gross_pnl": gross_pnl_usdt,
                    "fees": total_fees,
                    "pnl_usdt": net_pnl_usdt,
                    "balance_after": balance,
                })
                open_trade = None

        # ── Look for a new entry if flat ──────────────────────────────────
        if not open_trade:
            signal = strategy.evaluate(window)

            if signal["action"] in ("LONG", "SHORT") and signal["confidence"] >= config.MIN_CONFIDENCE_TO_TRADE:
                amount = risk_manager.calculate_position_size(balance, signal["price"], signal["atr"])
                if amount > 0:
                    stop_loss, take_profit = risk_manager.calculate_stop_and_target(
                        signal["price"], signal["atr"], signal["action"]
                    )
                    open_trade = {
                        "side": signal["action"],
                        "entry": signal["price"],
                        "amount": amount,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "entry_time": current_candle["timestamp"],
                    }

    return trades, balance


def report(trades, starting_balance, ending_balance):
    if not trades:
        print("No trades were triggered during this backtest period.")
        return

    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    win_rate = len(wins) / len(trades) * 100

    total_return_pct = (ending_balance - starting_balance) / starting_balance * 100

    equity = starting_balance
    peak = starting_balance
    max_drawdown = 0
    for t in trades:
        equity = t["balance_after"]
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak * 100
        max_drawdown = max(max_drawdown, drawdown)

    avg_win = sum(t["pnl_usdt"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_usdt"] for t in losses) / len(losses) if losses else 0

    print("=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)
    print(f"Total trades:      {len(trades)}")
    print(f"Win rate:          {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"Starting balance:  ${starting_balance:,.2f}")
    print(f"Ending balance:    ${ending_balance:,.2f}")
    print(f"Total return:      {total_return_pct:+.2f}%")
    print(f"Max drawdown:      {max_drawdown:.2f}%")
    print(f"Avg win:           ${avg_win:,.2f}")
    print(f"Avg loss:          ${avg_loss:,.2f}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backtest the BTC/USDT strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python3 backtest.py --fetch --days 90 --style daily
  python3 backtest.py --start 2025-10-01 --end 2025-12-31 --style daily
  python3 backtest.py --csv historical_data.csv --style weekly
""",
    )
    # ── Data source (mutually exclusive modes) ────────────────────────
    parser.add_argument("--fetch", action="store_true",
                        help="Fetch data from Bybit counting back --days from today")
    parser.add_argument("--days", type=int, default=90,
                        help="Number of days to fetch (used with --fetch, default: 90)")
    parser.add_argument("--start", type=str, metavar="YYYY-MM-DD",
                        help="Start date for explicit date-range fetch (UTC, inclusive)")
    parser.add_argument("--end", type=str, metavar="YYYY-MM-DD",
                        help="End date for explicit date-range fetch (UTC, inclusive)")
    parser.add_argument("--csv", type=str,
                        help="Path to a saved CSV file of OHLCV data (skips network fetch)")
    # ── Simulation settings ───────────────────────────────────────────
    parser.add_argument("--balance", type=float, default=10000,
                        help="Starting balance in USDT (default: 10000)")
    parser.add_argument("--style", choices=["daily", "weekly"], default="daily",
                        help="Trading style profile (default: daily)")
    args = parser.parse_args()

    # Validate: --start and --end must both be present if either is used
    if bool(args.start) != bool(args.end):
        parser.error("--start and --end must be used together")

    trading_style.apply_profile(args.style, config)
    print(f"Using '{args.style}' profile: timeframe={config.TIMEFRAME}, "
          f"min_confidence={config.MIN_CONFIDENCE_TO_TRADE}")

    # ── Choose data source ────────────────────────────────────────────
    if args.csv:
        data = load_csv(args.csv)
        out_csv = "backtest_trades.csv"

    elif args.start and args.end:
        data = fetch_historical_range(args.start, args.end)
        slug = f"{args.start}_to_{args.end}".replace("-", "")
        range_csv = f"historical_{slug}.csv"
        data.to_csv(range_csv, index=False)
        print(f"Saved {len(data)} candles to {range_csv}")
        out_csv = f"backtest_trades_{slug}.csv"

    elif args.fetch:
        print(f"Fetching {args.days} days of {config.SYMBOL} {config.TIMEFRAME} candles...")
        data = fetch_historical(args.days)
        data.to_csv("historical_data.csv", index=False)
        print(f"Saved {len(data)} candles to historical_data.csv")
        out_csv = "backtest_trades.csv"

    else:
        parser.error("Provide one of: --fetch, --start/--end, or --csv <path>")

    print(f"Running backtest over {len(data)} candles...")
    trade_log, final_balance = run_backtest(data, starting_balance=args.balance)
    report(trade_log, args.balance, final_balance)

    if trade_log:
        pd.DataFrame(trade_log).to_csv(out_csv, index=False)
        print(f"Full trade log saved to {out_csv}")
