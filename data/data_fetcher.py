"""
Handles all market-data retrieval from the exchange.
"""
import ccxt
import pandas as pd
import config


def get_exchange():
    """Create and return a configured ccxt exchange instance for whichever
    exchange is set in config.EXCHANGE_ID."""
    if not hasattr(ccxt, config.EXCHANGE_ID):
        raise ValueError(
            f"'{config.EXCHANGE_ID}' is not a valid ccxt exchange id. "
            f"Check config.EXCHANGE_ID."
        )

    market_type = config.MARKET_TYPE if config.TRADE_DERIVATIVES else "spot"

    exchange_class = getattr(ccxt, config.EXCHANGE_ID)
    exchange = exchange_class({
        "apiKey": config.API_KEY,
        "secret": config.API_SECRET,
        "enableRateLimit": True,
        "options": {
            "defaultType": market_type,
            "recvWindow": 60000,
        },
    })

    if config.USE_TESTNET:
        exchange.set_sandbox_mode(True)
        print(f"[data_fetcher] Connected to {config.EXCHANGE_ID.upper()} TESTNET "
              f"({market_type.upper()}, fake funds).")
    else:
        print(f"[data_fetcher] Connected to {config.EXCHANGE_ID.upper()} LIVE "
              f"({market_type.upper()}, real funds).")

    return exchange


def set_leverage_and_margin(exchange, leverage, symbol=None):
    """
    Configure leverage and margin mode on the exchange for a derivatives
    position. Must be called BEFORE placing an entry order - most exchanges
    reject changing leverage/margin mode while a position is already open.

    No-op (returns immediately) if config.TRADE_DERIVATIVES is False, since
    spot trading has no concept of leverage or margin mode.
    """
    if not config.TRADE_DERIVATIVES:
        return

    symbol = symbol or config.SYMBOL

    try:
        exchange.set_margin_mode(config.MARGIN_MODE, symbol)
    except Exception as e:
        # Some exchanges error if margin mode is already set to the requested
        # value - that's not a real failure, just log and continue.
        print(f"[data_fetcher] set_margin_mode note: {e}")

    try:
        exchange.set_leverage(leverage, symbol)
        print(f"[data_fetcher] Leverage set to {leverage}x ({config.MARGIN_MODE}) for {symbol}")
    except Exception as e:
        print(f"[data_fetcher] WARNING: could not set leverage: {e}")
        raise  # leverage not being set correctly is serious enough to stop the trade


def fetch_candles(exchange, symbol=None, timeframe=None, limit=None):
    """
    Fetch OHLCV candles and return as a pandas DataFrame with columns:
    timestamp, open, high, low, close, volume
    """
    symbol = symbol or config.SYMBOL
    timeframe = timeframe or config.TIMEFRAME
    limit = limit or config.CANDLE_LOOKBACK

    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def get_account_balance(exchange, currency="USDT"):
    """Return free balance of a currency. Returns 0 if unavailable (e.g. dry run w/o keys)."""
    try:
        balance = exchange.fetch_balance()
        return balance["free"].get(currency, 0)
    except Exception as e:
        print(f"[data_fetcher] Could not fetch balance: {e}")
        return 0
