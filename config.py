"""
Central configuration for the BTC/USDT trading bot.
Edit the values below to match your setup.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads variables from a local .env file, if present

# ── Exchange selection ────────────────────────────────────────────────
# Which exchange to trade on. Must be a valid ccxt exchange id.
# Hardcoded to bybit for this system.
EXCHANGE_ID = "bybit"

# ── Exchange credentials ─────────────────────────────────────────────
# Keys live in .env (which is gitignored), never in this file directly.
# Copy .env.example to .env and fill in your real values there.
# NOTE: testnet keys are DIFFERENT from live keys - generate them from
# the exchange's own testnet portal (see README).
API_KEY = os.environ.get("EXCHANGE_API_KEY", "")
API_SECRET = os.environ.get("EXCHANGE_API_SECRET", "")

# ── Trading pair & timeframe ─────────────────────────────────────────
SYMBOL = "BTC/USDT"
TIMEFRAME = "15m"          # candle size: 1m, 5m, 15m, 1h, 4h, 1d
CANDLE_LOOKBACK = 200       # how many candles to pull each cycle

# ── Safety switches ───────────────────────────────────────────────────
# USE_TESTNET: True  -> connects to Bybit's Testnet (fake funds,
#                        real order engine and real market data). This is
#                        the recommended way to validate the bot before
#                        risking real money.
#              False -> connects to real Bybit (real funds)
#
# DRY_RUN:     True  -> never sends any order, even to testnet. Just logs
#                        what it would do.
#              False -> actually places orders (on testnet or live,
#                        depending on USE_TESTNET above)
#
# Recommended path: USE_TESTNET=True, DRY_RUN=False for at least a week,
# watch the results, THEN flip USE_TESTNET=False when you're ready for
# real money.
USE_DEMO_TRADING = os.environ.get("USE_DEMO_TRADING", "False").lower() in ("true", "1", "yes")
USE_TESTNET = os.environ.get("USE_TESTNET", "True").lower() in ("true", "1", "yes")
DRY_RUN = os.environ.get("DRY_RUN", "False").lower() in ("true", "1", "yes")
AUTO_TRADE_ENABLED = os.environ.get("AUTO_TRADE_ENABLED", "True").lower() in ("true", "1", "yes")

# ── Dashboard Security ────────────────────────────────────────────────
DASHBOARD_USERNAME = os.environ.get("DASHBOARD_USERNAME", "")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
DASHBOARD_AUTH_ENABLED = os.environ.get("DASHBOARD_AUTH_ENABLED", "True").lower() in ("true", "1", "yes")

# ── Circuit Breaker & Error Resilience ───────────────────────────────
MAX_CONSECUTIVE_API_ERRORS = int(os.environ.get("MAX_CONSECUTIVE_API_ERRORS", "5"))
CIRCUIT_BREAKER_COOLDOWN_SEC = int(os.environ.get("CIRCUIT_BREAKER_COOLDOWN_SEC", "300"))

# ── Risk management ──────────────────────────────────────────────────
RISK_PER_TRADE_PCT = 1.0     # % of account balance risked per trade
STOP_LOSS_ATR_MULT = 1.5     # stop loss = entry -/+ (ATR * this multiplier)
TAKE_PROFIT_ATR_MULT = 3.0   # take profit = entry -/+ (ATR * this multiplier)
MAX_OPEN_POSITIONS = 1       # only one BTC/USDT position at a time

# ── Derivatives (futures/perpetual) settings ────────────────────────
# Only relevant if you're trading derivatives rather than spot.
TRADE_DERIVATIVES = True     # True = futures/perpetual (Long/Short + leverage), False = spot
# ccxt unified market type for perpetual futures. "swap" works for
# Bybit linear perpetuals. Verify against ccxt's docs
# for your specific exchange if orders fail to route correctly.
MARKET_TYPE = "swap"
MARGIN_MODE = "isolated"      # "isolated" or "cross" - isolated limits risk to that position's margin
LEVERAGE_MIN = 2              # bot will never suggest below this
LEVERAGE_MAX = 5              # bot will never suggest above this
# Maintenance margin rate used for liquidation price estimates. This varies
# by exchange and position size tier - 0.5% is a reasonable default for BTC
# perpetuals at low leverage, but check your exchange's actual margin
# tiers for precise numbers before relying on this for real risk decisions.
MAINTENANCE_MARGIN_RATE = 0.005

# ── Decision engine thresholds ───────────────────────────────────────
# FIX: raised from 65 → 80. Backtest shows 60-79 confidence has negative
# expected value. Only 80+ trades (after scoring-inflation fixes) are taken.
MIN_CONFIDENCE_TO_TRADE = 80  # 0-100 score required to actually place a trade

# ── Loop timing ───────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 60    # how often the bot checks the market

# ── Notification System Settings ──────────────────────────────────────
NOTIFICATION_ENABLED = os.environ.get("NOTIFICATION_ENABLED", "True").lower() in ("true", "1", "yes")
NOTIFICATION_MIN_LEVEL = os.environ.get("NOTIFICATION_MIN_LEVEL", "INFO")
NOTIFICATION_DEDUP_COOLDOWN_SEC = int(os.environ.get("NOTIFICATION_DEDUP_COOLDOWN_SEC", "60"))
NOTIFICATION_HISTORY_SIZE = int(os.environ.get("NOTIFICATION_HISTORY_SIZE", "500"))
NOTIFICATION_RATE_LIMIT = int(os.environ.get("NOTIFICATION_RATE_LIMIT", "30"))

# Telegram Integration
TELEGRAM_ENABLED = os.environ.get("TELEGRAM_ENABLED", "True").lower() in ("true", "1", "yes")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Logging ───────────────────────────────────────────────────────────
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "trading_bot.log")

