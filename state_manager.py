"""
State Manager: Hardened Disaster Recovery & State Persistence Module.
Persists the bot's open position state to disk with atomic file operations,
SHA-256 checksum verification, automatic backup recovery (.bak), and
Exchange Source-of-Truth Position Re-hydration.
"""
import json
import os
import shutil
import hashlib
import time
import logging

import config
from data import data_fetcher

log = logging.getLogger("state_manager")

STATE_FILE = "logs/bot_state.json"
BACKUP_FILE = "logs/bot_state.json.bak"
TEMP_FILE = "logs/bot_state.json.tmp"


def _compute_checksum(data_dict):
    """Computes SHA-256 hash string for data payload dictionary."""
    if data_dict is None:
        return "none"
    serialized = json.dumps(data_dict, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def save_state(open_position):
    """
    Atomically saves open_position payload to disk with SHA-256 checksum,
    flushes kernel buffers to storage via fsync, creates .bak backup,
    and replaces target atomically using os.replace().
    """
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

    if open_position is not None:
        payload = dict(open_position)
        # Strip internal checksum fields before computing hash
        core_payload = {k: v for k, v in payload.items() if k not in ("_checksum", "_version")}
        payload["_checksum"] = _compute_checksum(core_payload)
        payload["_version"] = "1.0"
    else:
        payload = None

    try:
        # Step 1: Write to temporary staging file
        with open(TEMP_FILE, "w") as f:
            json.dump(payload, f, indent=4)
            f.flush()
            os.fsync(f.fileno())

        # Step 2: Atomic backup creation if valid existing state file exists
        if os.path.exists(STATE_FILE):
            try:
                shutil.copyfile(STATE_FILE, BACKUP_FILE)
            except Exception as copy_err:
                log.warning(f"[state_manager] Could not update backup file: {copy_err}")

        # Step 3: Atomic replace
        os.replace(TEMP_FILE, STATE_FILE)
        return True
    except Exception as e:
        log.error(f"[state_manager] Failed atomic save_state: {e}")
        if os.path.exists(TEMP_FILE):
            try:
                os.remove(TEMP_FILE)
            except Exception:
                pass
        return False


def _read_and_validate_file(filepath):
    """
    Reads a state JSON file, validates JSON parsing and SHA-256 checksum.
    Supports legacy state files without checksum.
    Returns tuple: (state_dict_or_none, is_valid_bool).
    """
    if not os.path.exists(filepath):
        return None, False

    try:
        with open(filepath, "r") as f:
            data = json.load(f)

        if data is None:
            return None, True

        if not isinstance(data, dict):
            return None, False

        # If checksum present, perform SHA-256 validation
        if "_checksum" in data:
            expected = data.get("_checksum")
            core = {k: v for k, v in data.items() if k not in ("_checksum", "_version")}
            actual = _compute_checksum(core)
            if expected == actual:
                return core, True
            else:
                log.warning(f"[state_manager] SHA-256 Checksum Mismatch in {filepath}!")
                return None, False

        # Legacy file support (no _checksum)
        if "side" in data and "amount" in data and "entry" in data:
            log.info(f"[state_manager] Loaded legacy unchecksummed state file from {filepath}.")
            return data, True

        return None, False

    except Exception as e:
        log.warning(f"[state_manager] Read error on {filepath}: {e}")
        return None, False


def _rebuild_state_from_exchange(exchange, symbol):
    """
    Queries exchange as ultimate source of truth to re-hydrate state
    if local state files are corrupt or missing.
    """
    log.info(f"[state_manager] Querying exchange source of truth for active {symbol} position...")

    try:
        if config.TRADE_DERIVATIVES:
            positions = data_fetcher.retry_api_call(
                lambda: exchange.fetch_positions([symbol], params={"category": "linear"}),
                func_name="rehydrate_fetch_positions"
            )
            for pos in positions:
                if pos.get("symbol") == symbol and float(pos.get("contracts", 0)) > 0:
                    contracts = float(pos["contracts"])
                    entry_p = float(pos.get("entryPrice", 0.0))
                    raw_side = str(pos.get("side", "")).upper()
                    side = "BUY" if raw_side in ("BUY", "LONG") else "SELL"
                    sl = float(pos.get("stopLoss", 0.0)) if pos.get("stopLoss") else None
                    tp = float(pos.get("takeProfit", 0.0)) if pos.get("takeProfit") else None
                    now_ms = int(time.time() * 1000)
                    ts = pos.get("timestamp") or now_ms

                    rehydrated = {
                        "trade_id": f"rehydrated_{now_ms}",
                        "side": side,
                        "amount": contracts,
                        "entry": entry_p,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "entry_timestamp": ts,
                        "is_phantom": False,
                        "is_rehydrated": True,
                        "leverage": int(pos.get("leverage", 1)),
                    }
                    save_state(rehydrated)
                    log.info(
                        f"[state_manager] REHYDRATION SUCCESSFUL: Found active {side} position "
                        f"({contracts} BTC @ ${entry_p:.2f}) on exchange. State saved."
                    )
                    return rehydrated
        else:
            open_orders = data_fetcher.retry_api_call(
                lambda: exchange.fetch_open_orders(symbol),
                func_name="rehydrate_fetch_open_orders"
            )
            if open_orders:
                order = open_orders[0]
                now_ms = int(time.time() * 1000)
                rehydrated = {
                    "trade_id": f"rehydrated_{now_ms}",
                    "side": order.get("side", "buy").upper(),
                    "amount": float(order.get("amount", 0.0)),
                    "entry": float(order.get("price", 0.0)),
                    "stop_loss": None,
                    "take_profit": None,
                    "entry_timestamp": now_ms,
                    "is_phantom": False,
                    "is_rehydrated": True,
                }
                save_state(rehydrated)
                return rehydrated

    except Exception as e:
        log.error(f"[state_manager] Failed exchange position re-hydration: {e}")

    return None


def load_state(exchange, symbol):
    """
    Loads open position from disk with checksum validation, .bak fallback,
    and Exchange Source-of-Truth re-hydration/reconciliation.
    """
    state, valid = _read_and_validate_file(STATE_FILE)

    # Attempt recovery from backup file if primary file invalid/missing
    if not valid and os.path.exists(BACKUP_FILE):
        log.warning("[state_manager] Primary state file invalid or missing. Attempting backup restore...")
        state, valid = _read_and_validate_file(BACKUP_FILE)
        if valid:
            log.info("[state_manager] Backup state restore successful. Updating primary state file.")
            save_state(state)

    # If local state files completely missing or invalid, attempt exchange re-hydration
    if not valid or state is None:
        if exchange and not config.DRY_RUN:
            return _rebuild_state_from_exchange(exchange, symbol)
        return None

    # Ignore exchange check for phantom (paper trading) positions or DRY_RUN mode
    if state.get("is_phantom") or config.DRY_RUN:
        return state

    # If exchange object provided, reconcile local state against exchange source of truth
    if exchange:
        try:
            ex_state = _rebuild_state_from_exchange(exchange, symbol)
            if ex_state is None:
                log.warning(
                    f"[state_manager] Local state exists for {symbol}, but no active position/orders "
                    "found on exchange. Clearing local state to prevent phantom monitoring."
                )
                clear_state()
                return None
            else:
                # Exchange position verified active. Return local state to preserve original trade_id & timestamp
                return state
        except Exception as e:
            log.warning(f"[state_manager] Could not verify position with exchange: {e}. Resuming with local state.")
            return state

    return state


def clear_state():
    """Clear saved state cleanly using atomic save."""
    save_state(None)
