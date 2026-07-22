"""
Trade journal: logs the FULL context behind every decision the bot makes.
Uses SQLite for robust, lock-free performance in production.
"""
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_FILE = os.path.join("logs", "trade_journal.db")


def _get_conn():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_db():
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('''
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
            pnl_usdt REAL
        )
    ''')
    conn.commit()
    conn.close()


def new_trade_id():
    return uuid.uuid4().hex[:8]


def log_decision(signal, decision, exchange_id, symbol, risk_pct=None,
                  entry_price=None, stop_loss=None, take_profit=None, trade_id=None):
    """
    Append one row for a single decision cycle. `signal` is the dict
    returned by strategy.evaluate() (must include a "details" key).
    """
    _ensure_db()
    details = signal.get("details", {})

    risk_reward = None
    if entry_price and stop_loss and take_profit:
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        if risk > 0:
            risk_reward = round(reward / risk, 2)

    conn = _get_conn()
    cursor = conn.cursor()
    
    # Generate an ID if this is just a HOLD so it has a primary key
    t_id = trade_id or new_trade_id()
    
    cursor.execute('''
        INSERT INTO journal (
            trade_id, timestamp, exchange, symbol, current_price, trend_direction,
            ema_fast, ema_slow, rsi, macd, macd_signal, macd_hist, adx, atr,
            volume, volume_sma, candlestick_patterns, swing_high, swing_low,
            fib_level, fib_signal, nearest_support, nearest_resistance,
            support_distance_pct, resistance_distance_pct, confidence_score,
            confidence_breakdown, risk_pct, entry_price, stop_loss, take_profit,
            risk_reward, decision, outcome, exit_price, pnl_usdt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        t_id,
        datetime.now(timezone.utc).isoformat(),
        exchange_id, symbol,
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
        " | ".join(signal.get("reasons", [])),
        risk_pct, entry_price, stop_loss, take_profit, risk_reward,
        decision, "", None, None
    ))
    conn.commit()
    conn.close()


def close_trade(trade_id, exit_price, outcome, pnl_usdt):
    """Find the row for this trade_id and fill in how it ended."""
    if not trade_id:
        return
    _ensure_db()
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE journal 
        SET outcome = ?, exit_price = ?, pnl_usdt = ?
        WHERE trade_id = ?
    ''', (str(outcome), exit_price, pnl_usdt, trade_id))
    conn.commit()
    conn.close()


def summary_stats():
    """Quick win-rate / performance summary from the journal so far."""
    _ensure_db()
    conn = _get_conn()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM journal WHERE outcome IN ('win', 'loss')")
    row = cursor.fetchone()
    total = row[0] if row else 0
    
    if total == 0:
        conn.close()
        return {"total_trades": 0}
        
    cursor.execute("SELECT COUNT(*) FROM journal WHERE outcome = 'win'")
    wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(pnl_usdt) FROM journal WHERE outcome IN ('win', 'loss')")
    pnl_total = cursor.fetchone()[0] or 0.0
    
    conn.close()
    
    return {
        "total_trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate_pct": round(wins / total * 100, 1) if total > 0 else 0.0,
        "total_pnl_usdt": round(pnl_total, 2),
    }


def export_to_csv(filepath="logs/journal_export.csv"):
    """Export the SQLite journal back to a CSV for external analysis."""
    import csv
    _ensure_db()
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM journal")
    rows = cursor.fetchall()
    
    if not rows:
        conn.close()
        return
        
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(rows[0].keys())  # headers
        for row in rows:
            writer.writerow(row)
    conn.close()

def get_recent_trades(limit=50):
    """Retrieve the most recent trades for the web dashboard."""
    _ensure_db()
    conn = _get_conn()
    cursor = conn.cursor()
    # Ensure rows are returned as dictionaries for JSON serialization
    cursor.execute('''
        SELECT timestamp, decision, confidence_score, entry_price, exit_price, pnl_usdt, outcome 
        FROM journal 
        WHERE decision NOT IN ('WAIT', 'HOLD')
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]
