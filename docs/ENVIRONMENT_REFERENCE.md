# NSFLUX Trading Bot – Environment Variables Reference

This document provides a comprehensive reference for all environment variables supported by the NSFLUX trading bot, including requirements, default values, security sensitivity levels, and examples.

---

## 1. Environment Variable Specification Matrix

| Variable | Required / Optional | Default Value | Security Level | Description | Example Value |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `DASHBOARD_USERNAME` | **Required** | `admin` | 🔴 **HIGH (Secret)** | Username for web dashboard authentication. | `admin_trader` |
| `DASHBOARD_PASSWORD` | **Required** | None | 🔴 **HIGH (Secret)** | Password for web dashboard authentication. | `Pass#2026!Secure` |
| `SECRET_KEY` | **Required** | Auto-generated | 🔴 **HIGH (Secret)** | Flask session signing key. Must be persistent in production. | `e9f8a7...64chars` |
| `EXCHANGE_API_KEY` | Optional (Required for trading) | `""` | 🔴 **HIGH (Secret)** | Bybit API Key (Demo or Live account). | `gza3oB9Yy60Nq7x` |
| `EXCHANGE_API_SECRET` | Optional (Required for trading) | `""` | 🔴 **HIGH (Secret)** | Bybit API Secret key. Never expose in logs. | `K9xL2mQ8...` |
| `TELEGRAM_BOT_TOKEN` | Optional | `""` | 🔴 **HIGH (Secret)** | Telegram Bot API token from `@BotFather`. | `8607017007:AAEN...` |
| `TELEGRAM_CHAT_ID` | Optional | `""` | 🟡 **MEDIUM (Private)** | Telegram Chat/Channel ID for alert delivery. | `5957450774` |
| `USE_DEMO_TRADING` | Optional | `True` | 🟢 **LOW (Public)** | Toggle Bybit Demo Trading endpoint (`api-demo.bybit.com`). | `True` |
| `DASHBOARD_AUTH_ENABLED` | Optional | `True` | 🟢 **LOW (Public)** | Enforce login session authentication on dashboard. | `True` |
| `NOTIFICATION_ENABLED` | Optional | `True` | 🟢 **LOW (Public)** | Master toggle for background notification manager. | `True` |
| `PORT` | Optional | `5000` | 🟢 **LOW (Public)** | Port on which Gunicorn WSGI server listens inside container. | `5000` |
| `PYTHONUNBUFFERED` | Optional | `1` | 🟢 **LOW (Public)** | Force unbuffered stdout/stderr output for Cloud Logging. | `1` |
| `LOG_LEVEL` | Optional | `INFO` | 🟢 **LOW (Public)** | Logging granularity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` |

---

## 2. Production `.env` Example Template

Copy and modify this template for production deployment (`/opt/nsflux/app/.env`):

```ini
# ==============================================================================
# NSFLUX Production Environment Configuration
# Location: /opt/nsflux/app/.env
# Permissions: 0600 (Owned by nsflux:nsflux)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Web Dashboard & Authentication Secrets
# ------------------------------------------------------------------------------
DASHBOARD_AUTH_ENABLED=True
DASHBOARD_USERNAME=prod_trader_admin
DASHBOARD_PASSWORD=SuperSecretComplexPassword2026!
SECRET_KEY=9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e

# ------------------------------------------------------------------------------
# 2. Exchange API Configuration (Bybit Demo / Live)
# ------------------------------------------------------------------------------
USE_DEMO_TRADING=True
EXCHANGE_API_KEY=gza3oB9Yy60Nq7xPL3
EXCHANGE_API_SECRET=your_bybit_api_secret_key_here

# ------------------------------------------------------------------------------
# 3. Telegram Notification System
# ------------------------------------------------------------------------------
NOTIFICATION_ENABLED=True
TELEGRAM_BOT_TOKEN=8607017007:AAENis-LlbfciiLNvnUrZvHgUvgoTyIkMHA
TELEGRAM_CHAT_ID=5957450774

# ------------------------------------------------------------------------------
# 4. Runtime & Container Bindings
# ------------------------------------------------------------------------------
PORT=5000
PYTHONUNBUFFERED=1
LOG_LEVEL=INFO
```

---

## 3. Validation Script Usage

To verify all environment variables before running the container:

```bash
# Export environment variables from .env
export $(grep -v '^#' .env | xargs)

# Run verification suite environment check
python docker_verify.py
```
