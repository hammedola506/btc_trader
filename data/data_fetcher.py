import time
import logging
import ccxt
import pandas as pd
import config

log = logging.getLogger("data_fetcher")


_is_disconnected = False
_disconnected_since = 0.0
_consecutive_api_failures = 0
_DISCONNECT_NOTIFY_THRESHOLD = 2  # Trigger notification after 2 consecutive failures


def reset_connection_state():
    """Reset connection tracking state (primarily for testing)."""
    global _is_disconnected, _disconnected_since, _consecutive_api_failures
    _is_disconnected = False
    _disconnected_since = 0.0
    _consecutive_api_failures = 0


def retry_api_call(fn, func_name="API Call", max_retries=3, initial_delay=1.0):
    """
    Wrap an exchange API call with exponential backoff for transient CCXT network errors
    (NetworkError, RequestTimeout, RateLimitExceeded, DDoSProtection).
    """
    global _is_disconnected, _disconnected_since, _consecutive_api_failures
    delay = initial_delay
    transient_errors = (
        ccxt.NetworkError,
        ccxt.RequestTimeout,
        ccxt.RateLimitExceeded,
        ccxt.DDoSProtection,
    )
    start_t = time.time()
    for attempt in range(1, max_retries + 1):
        try:
            res = fn()
            # Recovered from network disruption
            if _is_disconnected:
                downtime = time.time() - _disconnected_since
                _is_disconnected = False
                _consecutive_api_failures = 0
                try:
                    import notifications
                    from notifications.templates import build_exchange_reconnected
                    event = build_exchange_reconnected(
                        downtime_sec=downtime,
                        recovered_function=func_name,
                        exchange_name=getattr(config, "EXCHANGE_ID", "BYBIT")
                    )
                    notifications.notify(event)
                except Exception as ne:
                    log.error(f"Failed to dispatch exchange reconnected notification: {ne}")
            else:
                _consecutive_api_failures = 0
            return res
        except transient_errors as e:
            elapsed = time.time() - start_t
            exc_class = e.__class__.__name__
            _consecutive_api_failures += 1

            if _consecutive_api_failures >= _DISCONNECT_NOTIFY_THRESHOLD and not _is_disconnected:
                _is_disconnected = True
                _disconnected_since = time.time()
                try:
                    import notifications
                    from notifications.templates import build_exchange_disconnected
                    event = build_exchange_disconnected(
                        error_type=exc_class,
                        error_msg=str(e),
                        consecutive_failures=_consecutive_api_failures,
                        exchange_name=getattr(config, "EXCHANGE_ID", "BYBIT")
                    )
                    notifications.notify(event)
                except Exception as ne:
                    log.error(f"Failed to dispatch exchange disconnected notification: {ne}")

            if attempt == max_retries:
                log.error(
                    f"[{func_name} FAILED] Final attempt {attempt}/{max_retries} failed after {elapsed:.2f}s | "
                    f"Exception: {exc_class} | Message: {e}"
                )
                raise e
            log.warning(
                f"[Retry {attempt}/{max_retries}] Function: {func_name} | "
                f"Exception: {exc_class} | Message: {e} | "
                f"Delay: {delay:.1f}s | Elapsed: {elapsed:.2f}s"
            )
            time.sleep(delay)
            delay *= 2.0


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

    if getattr(config, "USE_DEMO_TRADING", False):
        exchange.enable_demo_trading(True)
        print(f"[data_fetcher] Connected to {config.EXCHANGE_ID.upper()} DEMO TRADING "
              f"({market_type.upper()}, api-demo.bybit.com).")
    elif config.USE_TESTNET:
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
    position with retry backoff.
    """
    if not config.TRADE_DERIVATIVES:
        return

    symbol = symbol or config.SYMBOL

    try:
        retry_api_call(lambda: exchange.set_margin_mode(config.MARGIN_MODE, symbol), func_name="set_margin_mode")
    except Exception as e:
        print(f"[data_fetcher] set_margin_mode note: {e}")

    try:
        retry_api_call(lambda: exchange.set_leverage(leverage, symbol), func_name="set_leverage")
        print(f"[data_fetcher] Leverage set to {leverage}x ({config.MARGIN_MODE}) for {symbol}")
    except Exception as e:
        print(f"[data_fetcher] WARNING: could not set leverage: {e}")
        raise


def fetch_candles(exchange, symbol=None, timeframe=None, limit=None):
    """
    Fetch OHLCV candles with retry backoff and return as a pandas DataFrame.
    """
    symbol = symbol or config.SYMBOL
    timeframe = timeframe or config.TIMEFRAME
    limit = limit or config.CANDLE_LOOKBACK

    raw = retry_api_call(lambda: exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit), func_name="fetch_ohlcv")
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def get_wallet_info(exchange, currency="USDT"):
    """Return dictionary of wallet metrics: wallet_balance, available_balance, used_margin."""
    try:
        balance = retry_api_call(lambda: exchange.fetch_balance(), func_name="fetch_balance")
        total = float(balance.get("total", {}).get(currency, 0) or 0.0)
        free = float(balance.get("free", {}).get(currency, 0) or 0.0)
        used = float(balance.get("used", {}).get(currency, 0) or 0.0)
        return {
            "wallet_balance": round(total, 2),
            "available_balance": round(free, 2),
            "used_margin": round(used, 2),
            "max_risk_pct": config.RISK_PER_TRADE_PCT
        }
    except Exception as e:
        log.warning(f"[data_fetcher] Could not fetch wallet info: {e}")
        return {
            "wallet_balance": 0.0,
            "available_balance": 0.0,
            "used_margin": 0.0,
            "max_risk_pct": config.RISK_PER_TRADE_PCT
        }


def get_account_balance(exchange, currency="USDT"):
    """Return free balance of a currency with retry backoff. Returns 0 if unavailable."""
    info = get_wallet_info(exchange, currency)
    return info["available_balance"]


_ticker_cache = {"timestamp": 0, "data": None}

def get_ticker_data(exchange, symbol=None):
    """
    Fetch ticker details (last, 24h change %, high, low, volume, bid, ask, spread)
    with a 3-second cache to prevent exchange rate limit abuse.
    """
    symbol = symbol or config.SYMBOL
    now = time.time()
    if _ticker_cache["data"] and (now - _ticker_cache["timestamp"]) < 3.0:
        return _ticker_cache["data"]

    start_t = time.time()
    try:
        raw = retry_api_call(lambda: exchange.fetch_ticker(symbol), func_name="fetch_ticker")
        latency_ms = int((time.time() - start_t) * 1000)
        
        last_price = raw.get("last") or raw.get("close") or 0.0
        bid = raw.get("bid") or last_price
        ask = raw.get("ask") or last_price
        spread = round(ask - bid, 2) if (ask and bid) else 0.0

        ticker_info = {
            "symbol": symbol,
            "last": last_price,
            "change_24h_pct": round(float(raw.get("percentage") or 0.0), 2),
            "high_24h": raw.get("high") or last_price,
            "low_24h": raw.get("low") or last_price,
            "volume_24h": round(float(raw.get("baseVolume") or raw.get("quoteVolume") or 0.0), 2),
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "latency_ms": latency_ms
        }
        _ticker_cache["timestamp"] = now
        _ticker_cache["data"] = ticker_info
        return ticker_info
    except Exception as e:
        log.warning(f"Failed to fetch ticker: {e}")
        return _ticker_cache["data"] or {
            "symbol": symbol,
            "last": None,
            "change_24h_pct": 0.0,
            "high_24h": None,
            "low_24h": None,
            "volume_24h": 0.0,
            "bid": None,
            "ask": None,
            "spread": 0.0,
            "latency_ms": 0
        }
