# ─────────────────────────────────────────────────────────────────────────────
# NSFLUX BTC/USDT Trading Bot – Production Dockerfile
# Optimised for Google Cloud Run and Compute Engine.
#
# Key design decisions:
#  • python:3.11-slim-bookworm  – small, CVE-maintained base image
#  • Two-stage build            – builder isolates gcc/build tools; runtime
#                                 image contains only what is needed to run
#  • venv at /app/venv          – preserves existing subprocess references
#                                 (controller.py calls venv/bin/python for
#                                 backtesting) without modifying any Python code
#  • Non-root user nsflux       – UID/GID 10001 for container security
#  • /app/logs only writable    – all other paths are read-only after COPY
#  • PORT env var               – Cloud Run injects PORT at runtime
#  • SIGTERM → graceful shutdown – gunicorn forwards SIGTERM to workers;
#                                 workers call atexit/signal handlers already
#                                 present in controller.py
# ─────────────────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1: builder
#   Install all Python build-time dependencies into a standalone venv.
#   This stage is discarded after the second COPY, keeping the runtime image
#   free of gcc, headers, and other build tools.
# ══════════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim-bookworm AS builder

# ── ISP-proxy bypass: rewrite apt sources to HTTPS before any apt-get call ──
# Some ISPs (e.g. MTN Nigeria via bemobi) run a transparent HTTP proxy that
# returns 302/410 on Debian package downloads. Forcing HTTPS prevents the
# proxy from intercepting these connections.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list 2>/dev/null || true

# Install C build tooling required by some Python packages (e.g. numpy, ta)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create an isolated virtual environment at /app/venv (matching runtime stage destination)
RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Layer-cache: copy only the requirements file first so that pip install is
# re-run only when requirements.txt actually changes.
COPY requirements.txt .

# Install all Python dependencies in a single pip command.
# --no-cache-dir keeps the layer lean.
# --upgrade pip first to avoid resolver warnings in older bundled pip.
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2: runtime
#   Lean production image – no build tools, no source caches.
# ══════════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim-bookworm AS runtime

# ── Non-root user ─────────────────────────────────────────────────────────────
# Cloud Run and Compute Engine best practice: never run as root.
# UID/GID 10001 is chosen to be above the reserved system range.
ARG UID=10001
ARG GID=10001
RUN groupadd --gid ${GID} nsflux && \
    useradd  --uid ${UID} --gid ${GID} --no-create-home --shell /bin/false nsflux

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Copy the pre-built virtual environment from the builder stage ─────────────
COPY --from=builder /app/venv /app/venv

# ── Application source files ──────────────────────────────────────────────────
# Copy only the directories and files that are needed to run the application.
# .dockerignore ensures venv/, __pycache__, .env, logs/, large CSVs, etc.
# are excluded from the build context before Docker ever sees them.
COPY config.py         ./config.py
COPY main.py           ./main.py
COPY state_manager.py  ./state_manager.py
COPY backtest.py       ./backtest.py
COPY data/             ./data/
COPY execution/        ./execution/
COPY journal/          ./journal/
COPY notifications/    ./notifications/
COPY strategies/       ./strategies/
COPY web/              ./web/

# ── Persistent data directory ─────────────────────────────────────────────────
# /app/logs is the single writable location in the container.
# It holds:
#   - trading_bot.log       (application logs)
#   - trade_journal.db      (SQLite trading journal)
#   - bot_state.json        (open position state)
#   - bot_state.json.bak    (atomic backup)
#   - bot_state.json.tmp    (temp during atomic write)
#
# Mount a persistent volume here in production:
#   Cloud Run:         --volume <cloud-storage-bucket>:/app/logs
#   Compute Engine:    -v /mnt/nsflux-data:/app/logs
#   docker-compose:    ./logs:/app/logs
RUN mkdir -p /app/logs && \
    chown -R nsflux:nsflux /app/logs

# Transfer ownership of the application to the non-root user.
# /app/venv and source are read-only for the running process – only /app/logs
# requires write access.
RUN chown -R nsflux:nsflux /app

# ── Switch to non-root user ───────────────────────────────────────────────────
USER nsflux

# ── Environment variables ─────────────────────────────────────────────────────
# Python behaviour
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HOME=/tmp

# Virtual-env activation (makes `python` and `gunicorn` resolve to /app/venv/bin/)
ENV PATH="/app/venv/bin:$PATH"

# Default port – Cloud Run overrides this with its own PORT at runtime.
ENV PORT=5000

# ── Port declaration ──────────────────────────────────────────────────────────
# EXPOSE is informational; the actual bind is controlled by the CMD below.
EXPOSE ${PORT}

# ── Health check ──────────────────────────────────────────────────────────────
# /api/health is unauthenticated and returns {"status": "ok"}.
# Cloud Run and Compute Engine load-balancers use this to determine instance
# readiness.
#   --interval  30s  : check every 30 seconds
#   --timeout   10s  : fail if no response within 10 seconds
#   --start-period 30s: allow 30 s for gunicorn workers to boot
#   --retries   3    : mark unhealthy after 3 consecutive failures
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/api/health')" || exit 1

# ── Production startup command ────────────────────────────────────────────────
# gunicorn is the production WSGI server for Flask.
#
# --workers 1      : single worker because the trading bot's shared state is
#                    held in-process. Multiple workers would create isolated,
#                    inconsistent bot state. Use --threads for concurrency.
# --threads 4      : handle up to 4 concurrent HTTP requests within the worker
# --timeout 120    : allow long-running operations (e.g. backtest) up to 2 min
# --access-logfile -: write access logs to stdout (Google Cloud Logging picks these up)
# --error-logfile -: write error logs to stderr
# --forwarded-allow-ips '*': trust Cloud Run / GCP load balancer X-Forwarded-For
# --graceful-timeout 30: give the worker 30 s to finish in-flight requests on SIGTERM
#
# gunicorn forwards SIGTERM to workers. The existing atexit and threading.Event
# stop_event in controller.py handle clean shutdown of the trading engine.
CMD ["sh", "-c", \
    "/app/venv/bin/gunicorn web.app:app \
     --bind 0.0.0.0:${PORT} \
     --workers 1 \
     --threads 4 \
     --timeout 120 \
     --graceful-timeout 30 \
     --access-logfile - \
     --error-logfile - \
     --forwarded-allow-ips '*' \
     --log-level info"]
