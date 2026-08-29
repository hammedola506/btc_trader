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

from flask import Flask, jsonify, render_template, request, Response, make_response, session, redirect, url_for

app = Flask(__name__)
app.json = NumpyJSONProvider(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.environ.get("SECRET_KEY", "nsflux_production_session_secret_key_2026_nostress"))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_PERMANENT"] = False

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
        return add_security_headers(response)
    else:
        return redirect(url_for("login"))

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config.DASHBOARD_AUTH_ENABLED:
            res = make_response(f(*args, **kwargs))
            return add_security_headers(res)
            
        # Check Session Authentication
        if session.get("authenticated") is True:
            res = make_response(f(*args, **kwargs))
            return add_security_headers(res)

        # Check HTTP Basic Auth (for backward compatibility with test scripts)
        auth = request.authorization
        if auth and check_auth(auth.username, auth.password):
            res = make_response(f(*args, **kwargs))
            return add_security_headers(res)

        return authenticate()
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("authenticated") is True:
            return redirect(url_for("index"))
        return render_template("login.html")

    # POST handling
    data = request.get_json(silent=True) or request.form or {}
    username = data.get("username", "")
    password = data.get("password", "")
    remember = data.get("remember", False)
    if isinstance(remember, str):
        remember = remember.lower() in ("true", "1", "on", "yes")

    if check_auth(username, password):
        session.clear()
        session["authenticated"] = True
        if remember:
            session.permanent = True

        if request.is_json or "json" in request.headers.get("Accept", ""):
            res = jsonify({"success": True, "redirect": "/"})
            return add_security_headers(res)
        return redirect(url_for("index"))
    else:
        log.warning(
            f"FAILED LOGIN ATTEMPT | IP={request.remote_addr} | Username={username}"
        )
        if request.is_json or "json" in request.headers.get("Accept", ""):
            res = jsonify({
                "success": False,
                "message": "Invalid username or password. Please check your credentials and try again."
            })
            res.status_code = 401
            return add_security_headers(res)
        return render_template("login.html", error="Invalid username or password.")

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    if request.is_json or "json" in request.headers.get("Accept", ""):
        res = jsonify({"success": True, "redirect": "/login"})
        return add_security_headers(res)
    return redirect(url_for("login"))

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

@app.route("/api/notifications/history", methods=["GET"])
@requires_auth
def notifications_history():
    """Returns rolling notification history for the dashboard."""
    import notifications
    limit = int(request.args.get("limit", 50))
    level = request.args.get("level", None)
    category = request.args.get("category", None)
    return jsonify(notifications.get_history(limit=limit, level=level, category=category))

@app.route("/api/notifications/stats", methods=["GET"])
@requires_auth
def notifications_stats():
    """Returns runtime notification statistics for the dashboard."""
    import notifications
    return jsonify(notifications.get_statistics())

if __name__ == "__main__":
    if os.environ.get("AUTO_START_BOT", "false").lower() in ("true", "1", "yes"):
        log.info("AUTO_START_BOT is enabled. Launching trading bot engine thread...")
        start_bot()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    log.info(f"Starting NSLUX Web Dashboard on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
