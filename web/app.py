import sys
import os
# Add parent directory to path so we can import root modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import hmac
from functools import wraps
from flask import Flask, jsonify, render_template, request, Response, make_response
import config

from web.controller import get_state, start_bot, stop_bot, set_trading_style, start_backtest, get_backtest_state, set_auto_trade, toggle_auto_trade
from journal import trade_journal
from flask.json.provider import DefaultJSONProvider
import numpy as np

import logging

log = logging.getLogger("dashboard_auth")

# ── Fail-Fast Startup Security Check ─────────────────────────────────
def validate_dashboard_security():
    if config.DASHBOARD_AUTH_ENABLED:
        if not config.DASHBOARD_USERNAME or not config.DASHBOARD_PASSWORD:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: DASHBOARD_AUTH_ENABLED is True, "
                "but DASHBOARD_USERNAME or DASHBOARD_PASSWORD is not configured in environment/.env file. "
                "Set DASHBOARD_USERNAME and DASHBOARD_PASSWORD before starting the dashboard."
            )
        logging.warning(
            "SECURITY NOTICE: HTTP Basic Authentication is enabled. Ensure TLS/HTTPS termination "
            "via reverse proxy (Nginx, Traefik, GCP Cloud Run) in production to protect credentials in transit."
        )

validate_dashboard_security()

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

# ── Authentication Helper Functions ──────────────────────────────────
def check_auth(username, password):
    if not username or not password:
        return False
    user_ok = hmac.compare_digest(username.encode("utf-8"), config.DASHBOARD_USERNAME.encode("utf-8"))
    pass_ok = hmac.compare_digest(password.encode("utf-8"), config.DASHBOARD_PASSWORD.encode("utf-8"))
    return user_ok and pass_ok

def add_security_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

def authenticate():
    log.warning(
        f"FAILED AUTHENTICATION ATTEMPT | IP={request.remote_addr} | "
        f"Path={request.path} | Method={request.method}"
    )
    if request.path.startswith("/api/"):
        response = jsonify({
            "error": "Unauthorized",
            "message": "Could not verify your access level. Valid credentials required."
        })
        response.status_code = 401
    else:
        response = Response(
            'Could not verify your access level. Please log in with proper credentials.',
            401
        )
    response.headers['WWW-Authenticate'] = 'Basic realm="NoStressCapital Dashboard Login Required"'
    return add_security_headers(response)

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config.DASHBOARD_AUTH_ENABLED:
            res = make_response(f(*args, **kwargs))
            return add_security_headers(res)
            
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
            
        res = make_response(f(*args, **kwargs))
        return add_security_headers(res)
    return decorated


@app.route("/", methods=["GET"])
@requires_auth
def index():
    return render_template("index.html")

@app.route("/api/health", methods=["GET"])
def health():
    """Returns the operational health of the system (Unauthenticated for health checks)."""
    state = get_state()
    
    db_connected = False
    try:
        with trade_journal.get_db_connection(read_only=True) as conn:
            conn.execute("SELECT 1")
            db_connected = True
    except Exception:
        pass
        
    return jsonify({
        "status": "ok",
        "exchange_connected": True,
        "db_connected": db_connected,
        "bot_thread_alive": state["status"] == "running",
        "uptime_seconds": state["uptime_seconds"]
    })

@app.route("/api/status", methods=["GET"])
@requires_auth
def status():
    """Returns the safe, read-only copy of the bot's shared state."""
    return jsonify(get_state())

@app.route("/api/stats", methods=["GET"])
@requires_auth
def stats():
    """Returns performance stats from the SQLite journal."""
    return jsonify(trade_journal.summary_stats())

@app.route("/api/journal", methods=["GET"])
@requires_auth
def journal():
    """Returns the most recent 50 trades from the SQLite journal."""
    return jsonify(trade_journal.get_recent_trades(50))

@app.route("/api/journal/export", methods=["GET"])
@requires_auth
def export_journal_csv():
    """Exports trades from the SQLite journal as a downloadable CSV file."""
    import csv
    from io import StringIO
    from flask import Response

    trades = trade_journal.get_recent_trades(1000)
    if not trades:
        return Response(
            "No trade history available.\n",
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=trade_journal.csv"}
        )

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(trades[0].keys()))
    writer.writeheader()
    writer.writerows(trades)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=trade_journal.csv"}
    )

@app.route("/api/start", methods=["POST"])
@requires_auth
def start():
    """Starts the bot thread."""
    success, message = start_bot()
    return jsonify({"success": success, "message": message})

@app.route("/api/stop", methods=["POST"])
@requires_auth
def stop():
    """Signals the bot thread to stop gracefully."""
    success, message = stop_bot()
    return jsonify({"success": success, "message": message})

@app.route("/api/style", methods=["POST"])
@requires_auth
def style():
    """Changes the trading style."""
    data = request.json or {}
    success, message = set_trading_style(data.get("style", "daily"))
    return jsonify({"success": success, "message": message})

@app.route("/api/auto-trade", methods=["POST"])
@requires_auth
def auto_trade():
    """Toggles or sets the auto_trade_enabled state."""
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        success, current_state = set_auto_trade(data["enabled"])
    else:
        success, current_state = toggle_auto_trade()
    return jsonify({
        "success": success,
        "auto_trade_enabled": current_state,
        "message": f"Auto-Trade is now {'ON' if current_state else 'OFF'}"
    })

@app.route("/api/backtest/start", methods=["POST"])
@requires_auth
def backtest_start():
    success, message = start_backtest()
    return jsonify({"success": success, "message": message})

@app.route("/api/backtest/status", methods=["GET"])
@requires_auth
def backtest_status():
    return jsonify(get_backtest_state())

@app.route("/api/ticker", methods=["GET"])
@requires_auth
def ticker():
    """Returns live ticker details (last, 24h change %, high, low, volume, bid, ask, spread)."""
    state = get_state()
    ticker_data = state.get("ticker", {})
    if not ticker_data.get("last"):
        from web.controller import get_exchange_instance, update_state
        from data import data_fetcher
        ex = get_exchange_instance()
        if ex:
            try:
                t_info = data_fetcher.get_ticker_data(ex, config.SYMBOL)
                if t_info and t_info.get("last"):
                    update_state(ticker=t_info, price=t_info["last"])
                    return jsonify(t_info)
            except Exception:
                pass
    return jsonify(ticker_data)

@app.route("/api/journal/sync", methods=["POST"])
@requires_auth
def journal_sync():
    """Synchronizes historical trades executed on Bybit into the SQLite journal."""
    from web.controller import sync_bybit_history
    success, message = sync_bybit_history()
    return jsonify({"success": success, "message": message})

@app.route("/api/journal/clear", methods=["POST"])
@requires_auth
def journal_clear():
    """Clears test rows from the SQLite journal database (requires auth)."""
    from web.controller import clear_trade_journal
    success, message = clear_trade_journal()
    return jsonify({"success": success, "message": message})

if __name__ == "__main__":
    # Localhost binding is the correct default security posture
    app.run(host="127.0.0.1", port=5000, debug=False)
