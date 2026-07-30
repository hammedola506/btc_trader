# BTC/USDT Candlestick + TA Trading Bot

An AI-assisted trading bot for BTC/USDT that reads candlestick patterns and
technical indicators the way a discretionary trader would, then scores its
confidence before acting.

## How it thinks (like a human trader)

1. **Looks at the chart shape** — detects 17 candlestick patterns: hammer,
   shooting star, doji, spinning top, bullish/bearish engulfing,
   bullish/bearish harami, piercing line, dark cloud cover, morning/evening
   star, three white soldiers, three black crows, bullish/bearish marubozu,
   tweezer top/bottom (`candlestick_patterns.py`). Patterns are weighted by
   strength — a confirmed 3-candle reversal counts for more than a single
   indecisive candle.
2. **Checks momentum & trend** — EMA crossovers, RSI, MACD, volume
   confirmation (`indicators.py`)
3. **Weighs the evidence** — combines all signals into a 0-100 confidence
   score and a BUY/SELL/HOLD decision (`strategy.py`)
4. **Manages risk before acting** — position size is based on account
   balance and current volatility (ATR), with stop-loss/take-profit
   calculated automatically (`risk_manager.py`)
5. **Executes (or simulates) the trade** — places a live order, or just
   logs what it *would* do if `DRY_RUN = True` (`executor.py`)

## Trading style: Daily vs Weekly

When you run `python3 main.py`, the bot asks you upfront:

```
How do you want this bot to trade BTC/USDT?
  1) Daily  - 15-minute candles, checks every minute, frequent trades, tighter stops
  2) Weekly - 4-hour candles, checks hourly, fewer high-conviction trades, wider stops
```

Your answer reconfigures the timeframe, confidence threshold, and stop/target
distances (`trading_style.py`) — you don't need to hand-edit `config.py` for
this. The backtester supports the same choice: `python3 backtest.py --fetch --days 90 --style weekly`.

## Choosing an exchange: Bybit

Set in `config.py`:
```python
EXCHANGE_ID = "bybit"
```

- **Bybit testnet keys:** testnet.bybit.com

Whichever you pick, put the key/secret in `.env` as `EXCHANGE_API_KEY` /
`EXCHANGE_API_SECRET` — same variable names regardless of exchange.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and add your real Bybit API key/secret (this file is
gitignored and will never be committed). Then in `config.py` or `.env`:
- Keep `DRY_RUN = True` while you test
- Set `AUTO_TRADE_ENABLED=True` (or `False` for safe observation/signal-only mode without executing orders)
- Adjust `RISK_PER_TRADE_PCT`, `MIN_CONFIDENCE_TO_TRADE`, and `TIMEFRAME`
  to your preference

### Environment Configuration & Google Cloud Deployment
You can set safety switches via environment variables in `.env` or container environment settings (e.g. Google Cloud Run / Compute Engine):
```env
EXCHANGE_API_KEY=your_key
EXCHANGE_API_SECRET=your_secret
AUTO_TRADE_ENABLED=False   # Set False on Google Cloud for safe observation mode (SIGNAL_ONLY)
```
- When `AUTO_TRADE_ENABLED=False`, the trading loop evaluates market setups and records decisions into the trade journal as `SIGNAL_ONLY` without placing orders on Bybit.
- When running the web dashboard, `AUTO_TRADE_ENABLED` sets the default startup state, which can also be toggled dynamically via the dashboard UI.

## Run

```bash
python3 main.py
```

Logs print to console and to `trading_bot.log`.

## Backtesting

Test the strategy against historical data before ever going live:

```bash
# Fetch fresh history from Bybit and backtest it
python3 backtest.py --fetch --days 90

# Or reuse a previously saved CSV
python3 backtest.py --csv historical_data.csv
```

This replays candles one at a time (no lookahead bias), simulates entries
against your stop-loss/take-profit levels, and reports win rate, total
return, max drawdown, and average win/loss. Full trade-by-trade results
are saved to `backtest_trades.csv`.

**Reality check:** don't expect this default strategy to be immediately
profitable. Its purpose is to give you a measurable baseline — run it,
look at `backtest_trades.csv`, adjust the scoring weights or thresholds
in `strategy.py`, and re-run until performance is something you're
actually comfortable risking money on.

## ⚠️ Before you go live

- **Backtest first, on at least 90 days of data**, ideally across
  different market conditions (trending and choppy periods).
- **Run in `DRY_RUN = True` for at least a week after that** and read the
  logged reasoning for every signal.
- **Start with a small amount of capital** you can afford to lose
  entirely. Crypto is highly volatile and no strategy — rule-based or
  ML-based — guarantees profit.
- **API keys**: create a Bybit API key with trading permissions only
  (no withdrawal permission). Keep it in `.env` (gitignored), never in
  `config.py` or committed to source control.
- This project is a technical starting point, not financial advice.

## Extending it

- Add more candlestick patterns to `candlestick_patterns.py`
- Add more indicators (Bollinger Bands, ADX, Fibonacci levels) to `indicators.py`
- Swap the rule-based scoring in `strategy.py` for a trained ML model once
  you've collected enough labeled historical decisions
- Add a backtesting script that replays historical candles through
  `strategy.evaluate()` to measure win rate before ever going live
