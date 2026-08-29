# NSFLUX Trading Bot – Secret Management Guide

This document defines the lifecycle, injection methods, rotation policies, and emergency revocation procedures for all production secrets in **NSFLUX**.

---

## 1. Secret Inventory & Classification

| Secret Name | Description | Rotation Interval | Storage Location |
| :--- | :--- | :--- | :--- |
| `EXCHANGE_API_KEY` | Bybit Exchange API Key | 90 Days | GCP Secret Manager / `.env` (0600) |
| `EXCHANGE_API_SECRET` | Bybit Exchange API Secret | 90 Days | GCP Secret Manager / `.env` (0600) |
| `DASHBOARD_PASSWORD` | Web Dashboard Admin Password | 60 Days | GCP Secret Manager / `.env` (0600) |
| `SECRET_KEY` | Flask Session Signing Key | 180 Days | GCP Secret Manager / `.env` (0600) |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API Token | On Compromise | GCP Secret Manager / `.env` (0600) |

---

## 2. GCP Secret Manager Integration

### Step 1: Storing Secrets in GCP Secret Manager

```bash
# Set GCP Project
gcloud config set project nsflux-trading-prod

# Store Bybit API credentials
echo -n "actual_bybit_api_key" | gcloud secrets create BYBIT_API_KEY --data-file=-
echo -n "actual_bybit_api_secret" | gcloud secrets create BYBIT_API_SECRET --data-file=-

# Store Dashboard authentication password
echo -n "SecureProdPass2026!" | gcloud secrets create DASHBOARD_PASSWORD --data-file=-
```

### Step 2: Injecting Secrets into GCE Instance at Boot

Fetch secrets securely inside GCE startup scripts:

```bash
# Retrieve secret value from Cloud Secret Manager via gcloud CLI
export EXCHANGE_API_KEY=$(gcloud secrets versions access latest --secret="BYBIT_API_KEY")
export EXCHANGE_API_SECRET=$(gcloud secrets versions access latest --secret="BYBIT_API_SECRET")
export DASHBOARD_PASSWORD=$(gcloud secrets versions access latest --secret="DASHBOARD_PASSWORD")
```

---

## 3. Local File Secret Security (`.env`)

When using local file storage (`.env`):

```bash
# Set strict file permissions
sudo chmod 0600 /opt/nsflux/app/.env
sudo chown nsflux:nsflux /opt/nsflux/app/.env
```

`.dockerignore` and `.gitignore` safety checks:
Ensure `.env`, `*.pem`, `*.key`, `trade_journal.db` are explicitly listed in `.gitignore` and `.dockerignore`.

---

## 4. Emergency Secret Revocation Protocol

If API keys or passwords are exposed or compromised:

1. **Immediate Revocation**: Log into Bybit API Management console immediately and **DELETE** the compromised API key.
2. **Halt Bot Instance**:
   ```bash
   docker stop -t 5 nsflux_bot
   ```
3. **Generate New Key Pair**: Create a new API key on Bybit with restricted IP permissions.
4. **Update Secret Storage**: Update GCP Secret Manager or `/opt/nsflux/app/.env`.
5. **Restart Service**:
   ```bash
   docker compose up -d
   ```
