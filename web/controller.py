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
    "signal": "WAIT",
    "confidence": 0,
    "reasons": [],
    "bull_case": [],
    "bear_case": [],
    "hypothetical_risk": None,
    "position": None,
    "status": "stopped",
    "mode": "TESTNET (DRY RUN)" if config.DRY_RUN else "TESTNET" if config.USE_TESTNET else "LIVE",
    "style": "daily",
    "consecutive_errors": 0,
    "uptime_seconds": 0
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

def get_state():
    """Return a safe, read-only copy of the shared state."""
    with state_lock:
        # Calculate uptime if running
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
    
    update_state(status="running", consecutive_errors=0)
    
    try:
        exchange = data_fetcher.get_exchange()
        open_position = state_manager.load_state(exchange, config.SYMBOL)
        update_state(position=open_position)
    except Exception as e:
        log.error(f"Failed to initialize exchange in thread: {e}")
        update_state(status="stopped")
        return
    
    MAX_CONSECUTIVE_ERRORS = 5
    consecutive_errors = 0
    
    while not stop_event.is_set():
        try:
            # We pass _state_callback so run_once can report live price and signals
            open_position = run_once(exchange, open_position, state_callback=_state_callback)
            
            # Update position in global state
            update_state(position=open_position)
            
            consecutive_errors = 0  # reset on success
            update_state(consecutive_errors=0)
            
        except Exception as e:
            consecutive_errors += 1
            update_state(consecutive_errors=consecutive_errors)
            log.error(f"Error in controller loop ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.critical("CIRCUIT BREAKER TRIGGERED: Too many consecutive errors. Safely halting operations.")
                break
                
        # Sleep incrementally so we can break out quickly if stop_event is set
        for _ in range(config.POLL_INTERVAL_SECONDS):
            if stop_event.is_set():
                break
            time.sleep(1)

    update_state(status="stopped", uptime_seconds=0)

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
