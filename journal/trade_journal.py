"""
Trade journal: logs the FULL context behind every decision the bot makes.
Uses SQLite with Write-Ahead Logging (WAL) and explicit isolation levels
for high-concurrency, lock-free performance in production.
"""
import os
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

DB_FILE = os.path.join("logs", "trade_journal.db")
_db_initialized = False
_db_init_lock = threading.Lock()


@contextmanager
def get_db_connection(read_only=False):
    """
    Thread-safe SQLite context manager.
    - read_only=True: Uses autocommit (isolation_level=None), starting no write transactions.
    - read_only=False: Acquires immediate write transaction ('IMMEDIATE') to prevent lock escalation deadlocks.
    """
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    if read_only:
        conn = sqlite3.connect(DB_FILE, timeout=30.0, isolation_level=None)
    else:
        conn = sqlite3.connect(DB_FILE, timeout=30.0, isolation_level="IMMEDIATE")

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")

    try:
        yield conn
        if not read_only:
            conn.commit()
    except Exception as e:
        if not read_only:
            conn.rollback()
        raise e
    finally:
        conn.close()


def _ensure_db():
    global _db_initialized
    if _db_initialized:
        return

    with _db_init_lock:
        if _db_initialized:
            return

        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        with sqlite3.connect(DB_FILE, timeout=30.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA wal_autocheckpoint=1000;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS journal (
                    trade_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    exchange TEXT,
                    symbol TEXT,
                    current_price REAL,
                    trend_direction TEXT,
                    ema_fast REAL,
                    ema_slow REAL,
                    rsi REAL,
                    macd REAL,
                    macd_signal REAL,
                    macd_hist REAL,
                    adx REAL,
                    atr REAL,
                    volume REAL,
                    volume_sma REAL,
                    candlestick_patterns TEXT,
                    swing_high REAL,
                    swing_low REAL,
                    fib_level REAL,
                    fib_signal TEXT,
                    nearest_support REAL,
                    nearest_resistance REAL,
                    support_distance_pct REAL,
                    resistance_distance_pct REAL,
                    confidence_score REAL,
                    confidence_breakdown TEXT,
                    risk_pct REAL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    risk_reward REAL,
                    decision TEXT,
                    outcome TEXT,
                    exit_price REAL,
                    pnl_usdt REAL,
                    client_order_id TEXT,
                    exchange_order_id TEXT,
                    leverage INTEGER,
                    amount_btc REAL,
                    fees_usdt REAL,
                    strategy TEXT,
                    is_imported INTEGER DEFAULT 0,
                    duration_sec INTEGER
                )
            ''')
            # Migrate existing DB schemas gracefully
            for col_name, col_type in [
                ("client_order_id", "TEXT"),
                ("exchange_order_id", "TEXT"),
                ("leverage", "INTEGER"),
                ("amount_btc", "REAL"),
                ("fees_usdt", "REAL"),
                ("strategy", "TEXT"),
                ("is_imported", "INTEGER DEFAULT 0"),
                ("duration_sec", "INTEGER")
            ]:
                try:
                    conn.execute(f"ALTER TABLE journal ADD COLUMN {col_name} {col_type};")
                except Exception:
                    pass

        _db_initialized = True


def new_trade_id():
    return uuid.uuid4().hex[:8]


def log_decision(signal, decision, exchange_id, symbol, risk_pct=None,
                  entry_price=None, stop_loss=None, take_profit=None, trade_id=None,
                  client_order_id=None, exchange_order_id=None, leverage=None, amount_btc=None):
    """
    Append one row for a single decision cycle.
    All data processing & payload prep is performed BEFORE opening the write transaction
    to minimize write lock hold duration.
    """
    _ensure_db()
    
    # 1. Perform all data extraction & calculations BEFORE acquiring DB connection
    details = signal.get("details", {})

    risk_reward = None
    if entry_price and stop_loss and take_profit:
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        if risk > 0:
            risk_reward = round(reward / risk, 2)

    t_id = trade_id or new_trade_id()
    now_iso = datetime.now(timezone.utc).isoformat()
    reasons_str = " | ".join(signal.get("reasons", []))

    payload = (
        t_id, now_iso, exchange_id, symbol,
        signal.get("price"), details.get("trend_direction"),
        details.get("ema_fast"), details.get("ema_slow"), details.get("rsi"),
        details.get("macd"), details.get("macd_signal"), details.get("macd_hist"),
        details.get("adx"), signal.get("atr"),
        details.get("volume"), details.get("volume_sma"),
        details.get("candlestick_patterns"),
        details.get("swing_high"), details.get("swing_low"),
        details.get("fib_level"), details.get("fib_signal"),
        details.get("nearest_support"), details.get("nearest_resistance"),
        details.get("support_distance_pct"), details.get("resistance_distance_pct"),
        signal.get("confidence"),
        reasons_str,
        risk_pct, entry_price, stop_loss, take_profit, risk_reward,
        decision, "", None, None,
        client_order_id, exchange_order_id, leverage or 1, amount_btc or 0.0, 0.0,
        "Multi-Indicator V1", 0, None
    )

    # 2. Acquire write connection for shortest possible duration
    with get_db_connection(read_only=False) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO journal (
                trade_id, timestamp, exchange, symbol, current_price, trend_direction,
                ema_fast, ema_slow, rsi, macd, macd_signal, macd_hist, adx, atr,
                volume, volume_sma, candlestick_patterns, swing_high, swing_low,
                fib_level, fib_signal, nearest_support, nearest_resistance,
                support_distance_pct, resistance_distance_pct, confidence_score,
                confidence_breakdown, risk_pct, entry_price, stop_loss, take_profit,
                risk_reward, decision, outcome, exit_price, pnl_usdt,
                client_order_id, exchange_order_id, leverage, amount_btc, fees_usdt,
                strategy, is_imported, duration_sec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', payload)


def close_trade(trade_id, exit_price, outcome, pnl_usdt, fees_usdt=0.0):
    """Find the row for this trade_id and fill in how it ended."""
    if not trade_id:
        return
    _ensure_db()
    
    outcome_str = str(outcome)
    with get_db_connection(read_only=False) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE journal 
            SET outcome = ?, exit_price = ?, pnl_usdt = ?, fees_usdt = ?
            WHERE trade_id = ?
        ''', (outcome_str, exit_price, pnl_usdt, fees_usdt, trade_id))


def sync_bybit_trades(exchange, symbol=None):
    """
    Fetch historical trades from exchange (fetch_my_trades) and insert them using
    INSERT OR IGNORE into SQLite journal with is_imported=1 to avoid duplication.
    """
    symbol = symbol or config.SYMBOL
    _ensure_db()
    from data import data_fetcher
    try:
        my_trades = data_fetcher.retry_api_call(
            lambda: exchange.fetch_my_trades(symbol, limit=100),
            func_name="fetch_my_trades"
        )
        if not my_trades:
            return True, 0

        inserted_count = 0
        with get_db_connection(read_only=False) as conn:
            cursor = conn.cursor()
            for t in my_trades:
                trade_id = f"bybit_{t.get('id') or t.get('order')}"
                ts_ms = t.get("timestamp")
                ts_iso = datetime.fromtimestamp(ts_ms / 1000.0, timezone.utc).isoformat() if ts_ms else datetime.now(timezone.utc).isoformat()
                side = str(t.get("side", "")).upper()
                price = float(t.get("price") or 0.0)
                amount = float(t.get("amount") or 0.0)
                fee_info = t.get("fee", {})
                fee_cost = float(fee_info.get("cost") or 0.0) if isinstance(fee_info, dict) else 0.0

                cursor.execute('''
                    INSERT OR IGNORE INTO journal (
                        trade_id, timestamp, exchange, symbol, current_price,
                        entry_price, decision, outcome, amount_btc, fees_usdt,
                        exchange_order_id, is_imported, strategy
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'Bybit Testnet Import')
                ''', (
                    trade_id, ts_iso, config.EXCHANGE_ID, symbol, price,
                    price, side, "WIN" if side == "BUY" else "LOSS", amount, fee_cost,
                    t.get("order")
                ))
                if cursor.rowcount > 0:
                    inserted_count += 1
        return True, inserted_count
    except Exception as e:
        return False, str(e)


def clear_journal_data():
    """Clear journal table records for a fresh state (requires confirmation)."""
    _ensure_db()
    with get_db_connection(read_only=False) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM journal;")
    return True


def summary_stats():
    """Quick win-rate / performance summary from the journal so far (Read-Only)."""
    _ensure_db()
    with get_db_connection(read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM journal WHERE outcome IN ('win', 'loss', 'WIN', 'LOSS')")
        row = cursor.fetchone()
        total = row[0] if row else 0
        
        if total == 0:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "win_rate_pct": 0.0, "total_pnl_usdt": 0.0,
                "pnl_today": 0.0, "pnl_weekly": 0.0, "total_fees_usdt": 0.0
            }
            
        cursor.execute("SELECT COUNT(*) FROM journal WHERE outcome IN ('win', 'WIN')")
        wins = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(pnl_usdt) FROM journal WHERE outcome IN ('win', 'loss', 'WIN', 'LOSS')")
        pnl_total = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT SUM(fees_usdt) FROM journal")
        total_fees = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT SUM(pnl_usdt) FROM journal WHERE timestamp >= datetime('now', '-1 day') AND outcome IN ('win', 'loss', 'WIN', 'LOSS')")
        pnl_today = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT SUM(pnl_usdt) FROM journal WHERE timestamp >= datetime('now', '-7 days') AND outcome IN ('win', 'loss', 'WIN', 'LOSS')")
        pnl_weekly = cursor.fetchone()[0] or 0.0

        win_rate_val = round(wins / total * 100, 1) if total > 0 else 0.0
        return {
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": win_rate_val,
            "win_rate_pct": win_rate_val,
            "total_pnl_usdt": round(pnl_total, 2),
            "pnl_today": round(pnl_today, 2),
            "pnl_weekly": round(pnl_weekly, 2),
            "total_fees_usdt": round(total_fees, 2)
        }


def export_to_csv(filepath="logs/journal_export.csv"):
    """Export the SQLite journal back to a CSV for external analysis (Read-Only)."""
    import csv
    _ensure_db()
    with get_db_connection(read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM journal")
        rows = cursor.fetchall()
        
        if not rows:
            return
            
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())  # headers
            for row in rows:
                writer.writerow(row)


def get_recent_trades(limit=50):
    """Retrieve the most recent trades for the web dashboard (Read-Only)."""
    _ensure_db()
    with get_db_connection(read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                trade_id, timestamp, exchange, symbol, decision, confidence_score,
                entry_price, exit_price, pnl_usdt, outcome, client_order_id,
                exchange_order_id, leverage, amount_btc, fees_usdt, strategy,
                is_imported, duration_sec
            FROM journal 
            WHERE decision NOT IN ('WAIT', 'HOLD')
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
