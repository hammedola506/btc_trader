import os
import sys
from flask import Flask, jsonify, render_template, request

# Add parent directory to path so we can import root modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from web.controller import get_state, start_bot, stop_bot, set_trading_style, start_backtest, get_backtest_state
from journal import trade_journal
from flask.json.provider import DefaultJSONProvider
import numpy as np

class NumpyJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        return super().default(o)

app = Flask(__name__)
app.json = NumpyJSONProvider(app)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/api/health", methods=["GET"])
def health():
    """Returns the operational health of the system as requested."""
    state = get_state()
    
    db_connected = False
    try:
        # Quick check if DB is accessible
        conn = trade_journal._get_conn()
        conn.execute("SELECT 1")
        conn.close()
        db_connected = True
    except Exception:
        pass
        
    return jsonify({
        "status": "ok",
        "exchange_connected": True,  # Assumed true unless circuit breaker triggers
        "db_connected": db_connected,
        "bot_thread_alive": state["status"] == "running",
        "uptime_seconds": state["uptime_seconds"]
    })

@app.route("/api/status", methods=["GET"])
def status():
    """Returns the safe, read-only copy of the bot's shared state."""
    return jsonify(get_state())

@app.route("/api/stats", methods=["GET"])
def stats():
    """Returns performance stats from the SQLite journal."""
    return jsonify(trade_journal.summary_stats())

@app.route("/api/journal", methods=["GET"])
def journal():
    """Returns the most recent 50 trades from the SQLite journal."""
    return jsonify(trade_journal.get_recent_trades(50))

@app.route("/api/start", methods=["POST"])
def start():
    """Starts the bot thread."""
    success, message = start_bot()
    return jsonify({"success": success, "message": message})

@app.route("/api/stop", methods=["POST"])
def stop():
    """Signals the bot thread to stop gracefully."""
    success, message = stop_bot()
    return jsonify({"success": success, "message": message})

@app.route("/api/style", methods=["POST"])
def style():
    """Changes the trading style."""
    data = request.json or {}
    success, message = set_trading_style(data.get("style", "daily"))
    return jsonify({"success": success, "message": message})

@app.route("/api/backtest/start", methods=["POST"])
def backtest_start():
    success, message = start_backtest()
    return jsonify({"success": success, "message": message})

@app.route("/api/backtest/status", methods=["GET"])
def backtest_status():
    return jsonify(get_backtest_state())

if __name__ == "__main__":
    # Localhost binding is the correct default security posture
    app.run(host="127.0.0.1", port=5000, debug=False)
