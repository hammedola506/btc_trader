"""
NSFLUX Docker Verification Script
Verifies all HTTP endpoints, authentication, bot lifecycle, SQLite persistence,
and notification system via Flask's built-in test client.
This simulates exactly what the container would serve.
"""
import sys
import os
import json
import time
import tempfile

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

RESULTS = []
PASS = 0
FAIL = 0
WARN = 0


def record(label, passed, detail="", warn=False):
    global PASS, FAIL, WARN
    status = "PASS" if passed else ("WARN" if warn else "FAIL")
    if passed:
        PASS += 1
    elif warn:
        WARN += 1
    else:
        FAIL += 1
    icon = "✅" if passed else ("⚠️ " if warn else "❌")
    RESULTS.append((icon, status, label, detail))
    print(f"  {icon}  [{status}]  {label}" + (f"  →  {detail}" if detail else ""))


print("\n" + "=" * 70)
print("  NSFLUX Production Docker Verification Suite")
print("=" * 70 + "\n")

# ── Environment check ────────────────────────────────────────────────────────
print("─── 1. Environment Variables ───────────────────────────────────────────")
required_vars = {
    "DASHBOARD_USERNAME": os.environ.get("DASHBOARD_USERNAME", ""),
    "DASHBOARD_PASSWORD": os.environ.get("DASHBOARD_PASSWORD", ""),
}
optional_vars = {
    "EXCHANGE_API_KEY":    os.environ.get("EXCHANGE_API_KEY", "(not set)"),
    "TELEGRAM_BOT_TOKEN":  os.environ.get("TELEGRAM_BOT_TOKEN", "(not set)"),
    "TELEGRAM_CHAT_ID":    os.environ.get("TELEGRAM_CHAT_ID", "(not set)"),
    "PORT":                os.environ.get("PORT", "5000"),
    "USE_DEMO_TRADING":    os.environ.get("USE_DEMO_TRADING", "True"),
    "NOTIFICATION_ENABLED":os.environ.get("NOTIFICATION_ENABLED", "True"),
}
for var, val in required_vars.items():
    record(f"Required env: {var}", bool(val), val[:3] + "***" if val else "MISSING")
for var, val in optional_vars.items():
    record(f"Optional env: {var}", True, val, warn=False)

# ── Python & package check ───────────────────────────────────────────────────
print("\n─── 2. Python Runtime & Dependencies ───────────────────────────────────")
import importlib
packages = ["flask", "gunicorn", "ccxt", "numpy", "pandas", "ta", "dotenv", "sqlite3"]
for pkg in packages:
    try:
        m = importlib.import_module(pkg if pkg != "dotenv" else "dotenv")
        ver = getattr(m, "__version__", "n/a")
        record(f"Package: {pkg}", True, ver)
    except ImportError as e:
        record(f"Package: {pkg}", False, str(e))

# ── Logs directory writable check ────────────────────────────────────────────
print("\n─── 3. Persistent Volume – /app/logs Write Check ───────────────────────")
logs_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(logs_dir, exist_ok=True)
test_file = os.path.join(logs_dir, ".write_check")
try:
    with open(test_file, "w") as f:
        f.write("ok")
    os.remove(test_file)
    record("logs/ directory writable", True, logs_dir)
except Exception as e:
    record("logs/ directory writable", False, str(e))

db_path = os.path.join(logs_dir, "trade_journal.db")
record("SQLite database exists", os.path.exists(db_path), db_path)

# ── SQLite journal operations ─────────────────────────────────────────────────
print("\n─── 4. SQLite Journal Persistence ──────────────────────────────────────")
try:
    from journal import trade_journal
    trade_journal._ensure_db()
    record("DB schema init (_ensure_db)", True)

    stats = trade_journal.summary_stats()
    record("summary_stats() returns dict", isinstance(stats, dict),
           f"total_trades={stats.get('total_trades')}")

    trades = trade_journal.get_recent_trades(10)
    record("get_recent_trades() returns list", isinstance(trades, list),
           f"rows={len(trades)}")

    # Write test row
    import sqlite3
    with trade_journal.get_db_connection(read_only=False) as conn:
        conn.execute("""
            INSERT OR IGNORE INTO journal (trade_id, timestamp, exchange, symbol, decision)
            VALUES ('docker_verify_001', '2026-01-01T00:00:00+00:00', 'bybit', 'BTC/USDT', 'WAIT')
        """)
    record("SQLite write (INSERT) succeeds", True, "trade_id=docker_verify_001")

    with trade_journal.get_db_connection(read_only=True) as conn:
        row = conn.execute(
            "SELECT trade_id FROM journal WHERE trade_id='docker_verify_001'"
        ).fetchone()
    record("SQLite read (SELECT) verifies write", row is not None, str(dict(row)) if row else "NOT FOUND")

    # Cleanup test row
    with trade_journal.get_db_connection(read_only=False) as conn:
        conn.execute("DELETE FROM journal WHERE trade_id='docker_verify_001'")
    record("SQLite cleanup (DELETE) succeeds", True)

except Exception as e:
    record("SQLite journal operations", False, str(e))

# ── Flask application – HTTP endpoint tests ──────────────────────────────────
print("\n─── 5. HTTP Endpoints (via Flask Test Client) ───────────────────────────")
try:
    from web.app import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    client = flask_app.test_client()

    import config as cfg
    AUTH = (cfg.DASHBOARD_USERNAME, cfg.DASHBOARD_PASSWORD)

    # /api/health  (unauthenticated)
    r = client.get("/api/health")
    data = json.loads(r.data)
    record("/api/health → 200 OK", r.status_code == 200,
           f"status={data.get('status')}, db={data.get('db_connected')}")

    # /login GET (unauthenticated)
    r = client.get("/login")
    record("/login → 200 (renders HTML)", r.status_code == 200,
           f"content-type={r.content_type}")

    # /login POST – valid credentials
    r = client.post("/login",
                    data=json.dumps({"username": cfg.DASHBOARD_USERNAME,
                                     "password": cfg.DASHBOARD_PASSWORD}),
                    content_type="application/json",
                    headers={"Accept": "application/json"})
    login_ok = r.status_code == 200
    login_data = json.loads(r.data)
    record("/login POST (valid credentials) → 200", login_ok,
           f"success={login_data.get('success')}")

    # /login POST – invalid credentials
    r = client.post("/login",
                    data=json.dumps({"username": "hacker", "password": "wrong"}),
                    content_type="application/json",
                    headers={"Accept": "application/json"})
    record("/login POST (invalid credentials) → 401", r.status_code == 401,
           f"code={r.status_code}")

    # /api/status (via HTTP Basic Auth)
    r = client.get("/api/status", headers={
        "Authorization": "Basic " + __import__("base64").b64encode(
            f"{cfg.DASHBOARD_USERNAME}:{cfg.DASHBOARD_PASSWORD}".encode()
        ).decode()
    })
    record("/api/status (with auth) → 200", r.status_code == 200,
           f"mode={json.loads(r.data).get('mode','?')}")

    # Unauthenticated /api/status → 302 redirect to login
    clean_client = flask_app.test_client()
    r = clean_client.get("/api/status")
    record("/api/status (no auth) → 302 redirect", r.status_code in (302, 401),
           f"code={r.status_code}")

    # /api/stats
    r = client.get("/api/stats", headers={
        "Authorization": "Basic " + __import__("base64").b64encode(
            f"{cfg.DASHBOARD_USERNAME}:{cfg.DASHBOARD_PASSWORD}".encode()
        ).decode()
    })
    stats_data = json.loads(r.data)
    record("/api/stats → 200 with keys", r.status_code == 200,
           f"total_trades={stats_data.get('total_trades')}, win_rate={stats_data.get('win_rate')}")

    # /api/journal
    r = client.get("/api/journal", headers={
        "Authorization": "Basic " + __import__("base64").b64encode(
            f"{cfg.DASHBOARD_USERNAME}:{cfg.DASHBOARD_PASSWORD}".encode()
        ).decode()
    })
    trades_data = json.loads(r.data)
    record("/api/journal → 200 list", r.status_code == 200,
           f"trades_returned={len(trades_data)}")

    # /api/notifications/history
    r = client.get("/api/notifications/history", headers={
        "Authorization": "Basic " + __import__("base64").b64encode(
            f"{cfg.DASHBOARD_USERNAME}:{cfg.DASHBOARD_PASSWORD}".encode()
        ).decode()
    })
    record("/api/notifications/history → 200", r.status_code == 200,
           f"code={r.status_code}")

    # /api/notifications/stats
    r = client.get("/api/notifications/stats", headers={
        "Authorization": "Basic " + __import__("base64").b64encode(
            f"{cfg.DASHBOARD_USERNAME}:{cfg.DASHBOARD_PASSWORD}".encode()
        ).decode()
    })
    record("/api/notifications/stats → 200", r.status_code == 200,
           f"code={r.status_code}")

    # /api/start  (POST)
    r = client.post("/api/start", headers={
        "Authorization": "Basic " + __import__("base64").b64encode(
            f"{cfg.DASHBOARD_USERNAME}:{cfg.DASHBOARD_PASSWORD}".encode()
        ).decode()
    })
    start_data = json.loads(r.data)
    record("/api/start → 200", r.status_code == 200,
           f"success={start_data.get('success')}, msg={start_data.get('message','')[:40]}")

    # Give the bot thread a moment to initialise
    time.sleep(1.5)

    # /api/stop  (POST)
    r = client.post("/api/stop", headers={
        "Authorization": "Basic " + __import__("base64").b64encode(
            f"{cfg.DASHBOARD_USERNAME}:{cfg.DASHBOARD_PASSWORD}".encode()
        ).decode()
    })
    stop_data = json.loads(r.data)
    record("/api/stop → 200", r.status_code == 200,
           f"success={stop_data.get('success')}, msg={stop_data.get('message','')[:40]}")

    # /api/journal/export
    r = client.get("/api/journal/export", headers={
        "Authorization": "Basic " + __import__("base64").b64encode(
            f"{cfg.DASHBOARD_USERNAME}:{cfg.DASHBOARD_PASSWORD}".encode()
        ).decode()
    })
    record("/api/journal/export → 200 CSV", r.status_code == 200,
           f"content-type={r.content_type}")

    # /logout
    r = client.post("/logout",
                    headers={"Accept": "application/json"})
    record("/logout → 200", r.status_code == 200)

except Exception as e:
    import traceback
    record("Flask endpoint suite", False, traceback.format_exc()[:200])

# ── Notification system ──────────────────────────────────────────────────────
print("\n─── 6. Notification System ──────────────────────────────────────────────")
try:
    import notifications
    import config as cfg2
    notifications.init_notifications(cfg2)
    from notifications import NotificationEvent, NotificationLevel, EventCategory
    ev = NotificationEvent(
        event_type="docker_verify",
        category=EventCategory.BOT_LIFECYCLE,
        level=NotificationLevel.INFO,
        title="Docker Verification",
        message="Container verification test event.",
        details={}
    )
    notifications.notify(ev)
    record("notifications.notify() non-blocking call", True, "event enqueued")
    time.sleep(0.2)
    history = notifications.get_history(limit=5)
    record("notifications.get_history() returns list", isinstance(history, list),
           f"entries={len(history)}")
    stats_n = notifications.get_statistics()
    record("notifications.get_statistics() returns dict", isinstance(stats_n, dict),
           f"keys={list(stats_n.keys())[:4]}")
except Exception as e:
    record("Notification system", False, str(e))

# ── Cloud Run compatibility ───────────────────────────────────────────────────
print("\n─── 7. Cloud Run Compatibility ─────────────────────────────────────────")

# PORT env var handling
port = os.environ.get("PORT", "5000")
record("PORT env var resolves", port.isdigit(), f"PORT={port}")

# Non-root user check (inside container this would be uid 10001)
uid = os.getuid()
is_nonroot = uid != 0
record("Non-root execution", is_nonroot, f"uid={uid}" + (" (root – expected inside Docker)" if not is_nonroot else ""))

# PYTHONUNBUFFERED (stdout/stderr for Cloud Logging)
unbuffered = os.environ.get("PYTHONUNBUFFERED", "")
record("PYTHONUNBUFFERED set (Cloud Logging)", bool(unbuffered), f"PYTHONUNBUFFERED={unbuffered or 'NOT SET (normal outside container)'}", warn=not bool(unbuffered))

# Health endpoint is unauthenticated
try:
    from web.app import app as flask_app2
    flask_app2.config["TESTING"] = True
    c2 = flask_app2.test_client()
    r = c2.get("/api/health")
    d = json.loads(r.data)
    record("Health check unauthenticated (Cloud Run readiness)", r.status_code == 200,
           f"status={d.get('status')}")
except Exception as e:
    record("Health check unauthenticated", False, str(e))

# gunicorn importable
try:
    import gunicorn
    record("gunicorn importable", True, getattr(gunicorn, "__version__", "n/a"))
except ImportError as e:
    record("gunicorn importable", False, str(e))

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"  RESULTS:  ✅ PASS={PASS}   ❌ FAIL={FAIL}   ⚠️  WARN={WARN}")
total = PASS + FAIL + WARN
score = round((PASS / total) * 100) if total else 0
print(f"  SCORE:    {score}/100")
print("=" * 70 + "\n")

# Write structured JSON summary for the audit report
summary = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "pass": PASS,
    "fail": FAIL,
    "warn": WARN,
    "score": score,
    "results": [{"status": s, "label": l, "detail": d} for _, s, l, d in RESULTS]
}
out = os.path.join(os.path.dirname(__file__), "logs", "docker_verification_results.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump(summary, f, indent=2)
print(f"  Results written to: {out}\n")

sys.exit(0 if FAIL == 0 else 1)
