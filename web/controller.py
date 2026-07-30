import threading
import time
import logging

import config
from data import data_fetcher
from execution import risk_manager, executor
from journal import trade_journal
import state_manager
from main import run_once
from strategies import trading_style
import subprocess
import re

log = logging.getLogger("btc_trader.controller")

# Shared state dictionary representing the live view of the bot
SHARED_STATE = {
    "price": None,
    "ticker": {
        "symbol": config.SYMBOL,
        "last": None,
        "change_24h_pct": 0.0,
        "high_24h": None,
        "low_24h": None,
        "volume_24h": 0.0,
        "bid": None,
        "ask": None,
        "spread": 0.0,
        "latency_ms": 0
    },
    "signal": "WAIT",
    "raw_direction": "NEUTRAL",
    "confidence": 0,
    "indicator_scores": {
        "ema_trend": 0,
        "rsi_momentum": 0,
        "macd": 0,
        "adx": 0,
        "support_resistance": 0,
        "fibonacci": 0,
        "candlestick": 0
    },
    "reasons": [],
    "bull_case": [],
    "bear_case": [],
    "hypothetical_risk": None,
    "position": None,
    "status": "stopped",
    "mode": (
        "DEMO TRADING (DRY RUN)" if config.DRY_RUN and getattr(config, "USE_DEMO_TRADING", False)
        else "TESTNET (DRY RUN)" if config.DRY_RUN and config.USE_TESTNET
        else "DRY RUN" if config.DRY_RUN
        else "DEMO TRADING" if getattr(config, "USE_DEMO_TRADING", False)
        else "TESTNET" if config.USE_TESTNET
        else "LIVE"
    ),
    "style": "daily",
    "consecutive_errors": 0,
    "circuit_breaker_tripped": False,
    "uptime_seconds": 0,
    "auto_trade_enabled": True,
    "wallet": {
        "wallet_balance": 0.0,
        "available_balance": 0.0,
        "used_margin": 0.0,
        "max_risk_pct": config.RISK_PER_TRADE_PCT
    },
    "system": {
        "last_scan_time": None,
        "next_scan_seconds": config.POLL_INTERVAL_SECONDS,
        "db_connected": True
    }
}

BACKTEST_STATE = {
    "status": "idle",
    "results": None,
    "error": None
}

state_lock = threading.Lock()
bot_thread = None
stop_event = threading.Event()
start_time = None
cached_exchange = None

def get_exchange_instance():
    global cached_exchange
    if cached_exchange is None:
        try:
            cached_exchange = data_fetcher.get_exchange()
        except Exception as e:
            log.warning(f"Could not initialize exchange instance: {e}")
    return cached_exchange

def get_state():
    """Return a safe, read-only copy of the shared state instantly (non-blocking)."""
    with state_lock:
        if SHARED_STATE["status"] == "running" and start_time:
            SHARED_STATE["uptime_seconds"] = int(time.time() - start_time)
        return dict(SHARED_STATE)

def update_state(**kwargs):
    """Safely update the shared state dictionary."""
    with state_lock:
        SHARED_STATE.update(kwargs)

def _state_callback(**kwargs):
    """Callback passed to run_once to inject live data into shared state."""
    update_state(**kwargs)

def _bot_loop():
    """The background thread running the core trading engine."""
    global start_time
    start_time = time.time()

    import socket
    import notifications
    from notifications import templates, NotificationEvent, NotificationLevel, EventCategory

    notifications.init_notifications(config)

    update_state(status="running", consecutive_errors=0, circuit_breaker_tripped=False)

    try:
        exchange = data_fetcher.get_exchange()
        open_position = state_manager.load_state(exchange, config.SYMBOL)
        initial_wallet = data_fetcher.get_wallet_info(exchange, "USDT")
        update_state(position=open_position, wallet=initial_wallet)

        # Dispatch Startup Notification
        hostname = socket.gethostname()
        mode_str = "DEMO TRADING" if getattr(config, "USE_DEMO_TRADING", False) else ("TESTNET" if config.USE_TESTNET else "LIVE")
        startup_notif = templates.build_startup_summary(
            bot_version="2.0.0",
            environment=mode_str,
            exchange=config.EXCHANGE_ID,
            symbol=config.SYMBOL,
            wallet_balance=initial_wallet.get("wallet_balance", 0.0),
            risk_pct=config.RISK_PER_TRADE_PCT,
            strategy="Quantitative AI (Scalp/Daily)",
            hostname=hostname
        )
        notifications.notify(startup_notif)

    except Exception as e:
        log.error(f"Failed to initialize exchange in thread: {e}")
        update_state(status="stopped", consecutive_errors=1, circuit_breaker_tripped=True)
        notifications.notify(NotificationEvent(
            event_type="bot_crashed",
            category=EventCategory.BOT_LIFECYCLE,
            level=NotificationLevel.CRITICAL,
            title="Bot Startup Failed",
            message=f"<b>🚨 BOT CRASHED ON INITIALIZATION:</b> {e}",
            details={"error": str(e)}
        ))
        return

    max_errors = config.MAX_CONSECUTIVE_API_ERRORS
    consecutive_errors = 0
    
    last_heartbeat_time = time.time()
    last_daily_time = time.time()

    while not stop_event.is_set():
        try:
            auto_trade = get_state().get("auto_trade_enabled", True)
            # We pass _state_callback so run_once can report live price and signals
            open_position = run_once(exchange, open_position, state_callback=_state_callback, auto_trade_enabled=auto_trade)

            # Update position in global state
            update_state(position=open_position, consecutive_errors=0, circuit_breaker_tripped=False)
            consecutive_errors = 0  # reset on success

            # Heartbeat check (every 6 hours)
            now = time.time()
            if now - last_heartbeat_time >= 21600:
                last_heartbeat_time = now
                current_price = get_state().get("price", 0.0)
                wallet_info = get_state().get("wallet", {})
                hb_notif = templates.build_heartbeat(
                    status="running",
                    wallet_balance=wallet_info.get("wallet_balance", 0.0),
                    current_price=current_price,
                    open_positions=1 if open_position else 0,
                    cpu_pct=0.0,
                    mem_pct=0.0,
                    api_latency_ms=0,
                    queue_len=0,
                    last_notif_time=""
                )
                notifications.notify(hb_notif)

        except Exception as e:
            consecutive_errors += 1
            log.error(f"Error in controller loop ({consecutive_errors}/{max_errors}): {e}")
            if consecutive_errors >= max_errors:
                log.critical(
                    f"CIRCUIT BREAKER TRIGGERED: Exceeded {max_errors} consecutive API/system errors. "
                    f"Safely halting trading operations."
                )
                update_state(
                    status="stopped",
                    consecutive_errors=consecutive_errors,
                    circuit_breaker_tripped=True
                )
                cb_notif = templates.build_circuit_breaker(
                    reason=f"Exceeded {max_errors} consecutive API errors: {e}",
                    errors_count=consecutive_errors
                )
                notifications.notify(cb_notif)
                break
            else:
                update_state(consecutive_errors=consecutive_errors)

        # Sleep incrementally so we can break out quickly if stop_event is set
        for _ in range(config.POLL_INTERVAL_SECONDS):
            if stop_event.is_set():
                break
            time.sleep(1)

    update_state(status="stopped", uptime_seconds=0)
    notifications.notify(NotificationEvent(
        event_type="bot_stopped",
        category=EventCategory.BOT_LIFECYCLE,
        level=NotificationLevel.WARNING,
        title="Bot Engine Stopped",
        message="<b>🛑 NSFLUX Trading Engine Stopped</b>",
        details={"status": "stopped"}
    ))


def set_auto_trade(enabled):
    with state_lock:
        SHARED_STATE["auto_trade_enabled"] = bool(enabled)
        val = SHARED_STATE["auto_trade_enabled"]
        return True, val

def toggle_auto_trade():
    with state_lock:
        SHARED_STATE["auto_trade_enabled"] = not SHARED_STATE.get("auto_trade_enabled", True)
        val = SHARED_STATE["auto_trade_enabled"]
        return True, val

def start_bot():
    global bot_thread
    with state_lock:
        if SHARED_STATE["status"] == "running":
            return False, "Bot is already running."
            
    stop_event.clear()
    bot_thread = threading.Thread(target=_bot_loop, daemon=True)
    bot_thread.start()
    return True, "Bot started successfully."

def stop_bot():
    with state_lock:
        if SHARED_STATE["status"] == "stopped":
            return False, "Bot is already stopped."
            
    stop_event.set()
    return True, "Stop signal sent. Bot will halt shortly."

def set_trading_style(style):
    with state_lock:
        if SHARED_STATE["status"] == "running":
            return False, "Cannot change style while bot is running."
        if BACKTEST_STATE["status"] == "running":
            return False, "Cannot change style while backtest is running."
            
        try:
            trading_style.apply_profile(style, config)
            SHARED_STATE["style"] = style
            return True, f"Trading style set to {style}."
        except ValueError as e:
            return False, str(e)
            
def get_backtest_state():
    with state_lock:
        return dict(BACKTEST_STATE)
        
def _backtest_worker(style):
    with state_lock:
        BACKTEST_STATE["status"] = "running"
        BACKTEST_STATE["error"] = None
        BACKTEST_STATE["results"] = None

    try:
        # Run backtest as an isolated subprocess
        process = subprocess.run(
            ["venv/bin/python", "backtest.py", "--fetch", "--days", "90", "--style", style],
            capture_output=True,
            text=True
        )
        
        if process.returncode != 0:
            with state_lock:
                BACKTEST_STATE["status"] = "error"
                BACKTEST_STATE["error"] = f"Process failed:\n{process.stderr}"
            return

        out = process.stdout
        
        # Regex parse results
        results = {
            "total_trades": "0",
            "win_rate": "0%",
            "total_return": "0%",
            "max_drawdown": "0%"
        }
        
        match_trades = re.search(r"Total trades:\s+(\d+)", out)
        match_winrate = re.search(r"Win rate:\s+([\d\.]+%)", out)
        match_return = re.search(r"Total return:\s+([+-]?[\d\.]+%)", out)
        match_dd = re.search(r"Max drawdown:\s+([\d\.]+%)", out)
        
        if match_trades: results["total_trades"] = match_trades.group(1)
        if match_winrate: results["win_rate"] = match_winrate.group(1)
        if match_return: results["total_return"] = match_return.group(1)
        if match_dd: results["max_drawdown"] = match_dd.group(1)
            
        with state_lock:
            BACKTEST_STATE["status"] = "done"
            BACKTEST_STATE["results"] = results
            
    except Exception as e:
        with state_lock:
            BACKTEST_STATE["status"] = "error"
            BACKTEST_STATE["error"] = str(e)

def start_backtest():
    with state_lock:
        if BACKTEST_STATE["status"] == "running":
            return False, "Backtest is already running."
        current_style = SHARED_STATE["style"]
        
    thread = threading.Thread(target=_backtest_worker, args=(current_style,), daemon=True)
    thread.start()
    return True, f"Started backtest with {current_style} style."


def sync_bybit_history():
    """Trigger Bybit testnet history synchronization."""
    ex = get_exchange_instance()
    if not ex:
        return False, "Exchange connection unavailable."
    success, result = trade_journal.sync_bybit_trades(ex, config.SYMBOL)
    if success:
        return True, f"Successfully imported {result} historical trades from Bybit."
    else:
        return False, f"Failed to sync Bybit history: {result}"


def clear_trade_journal():
    """Clear test data from journal database."""
    try:
        trade_journal.clear_journal_data()
        return True, "Trade journal cleared successfully."
    except Exception as e:
        return False, str(e)
