# NSFLUX Trading Bot – Disaster Recovery Plan (DRP)

This document defines disaster recovery procedures for catastrophic infrastructure failures, persistent storage failure, exchange outages, and security compromises.

---

## 1. Disaster Classification & RTO / RPO Targets

| Disaster Scenario | Maximum Recovery Time Objective (RTO) | Maximum Recovery Point Objective (RPO) | Severity |
| :--- | :--- | :--- | :--- |
| **GCE VM Instance Crash** | < 15 Minutes | 0 Data Loss (Persistent Disk intact) | 🔴 CRITICAL |
| **Persistent Disk Failure** | < 1 Hour | < 24 Hours (Latest SQLite Backup) | 🔴 CRITICAL |
| **Bybit Exchange Outage** | Automated Circuit Breaker | 0 Data Loss | 🟡 HIGH |
| **API Key Compromise** | < 10 Minutes | 0 Data Loss | 🔴 CRITICAL |
| **Network / ISP Outage** | Automated Retries (15m) | 0 Data Loss | 🟡 HIGH |

---

## 2. Recovery Scenario A: GCE Host Instance Crash

If the underlying GCE Virtual Machine crashes or is terminated by GCP maintenance:

```text
[ VM Crash Detected ] ──> GCP Auto-Restart / Manual Instance Spin-up
                                │
                                ▼ Attach Existing Persistent Disk (nsflux-data-disk)
                                │
                                ▼ Run Startup Command (docker compose up -d)
                                │
                                ▼ Verify Bot State Sync with Bybit Exchange
```

### Execution Commands:

```bash
# 1. Spin up replacement GCE Instance attached to existing persistent disk
gcloud compute instances create nsflux-bot-vm-recovered \
    --zone=us-central1-a \
    --machine-type=e2-standard-2 \
    --disk=name=nsflux-data-disk,mode=rw,device-name=nsflux-data-disk \
    --address=nsflux-static-ip \
    --tags=nsflux-web

# 2. SSH into replacement VM and launch service
gcloud compute ssh nsflux-bot-vm-recovered --zone=us-central1-a --command="
  sudo mkdir -p /opt/nsflux/logs && \
  sudo mount /dev/disk/by-id/google-nsflux-data-disk /opt/nsflux/logs && \
  cd /opt/nsflux/app && \
  docker compose up -d
"
```

---

## 3. Recovery Scenario B: Bybit Exchange Outage

When Bybit API experiences downtime or network unreachability:

1. **Automated Defense**: The bot's built-in exponential backoff retry system (`fetch_ticker`, `fetch_balance`) catches `ccxt.NetworkError` and `ccxt.ExchangeError`.
2. **Disconnect Alert**: After 2 consecutive failures, an automated Telegram disconnect alert is sent.
3. **Circuit Breaker**: If errors persist across 5 cycles, the circuit breaker trips, putting the bot in a safe `WAIT` state without submitting orders.
4. **Restoration**: Upon API recovery, the bot sends a Telegram reconnect alert and resumes state verification automatically.

---

## 4. Recovery Scenario C: API Key Compromise Emergency Response

If exchange API keys are leaked:

1. **Revoke Immediately**: Log into Bybit Web Console -> Account & Security -> API Management -> **Delete Key**.
2. **Stop Container**:
   ```bash
   docker stop -t 5 nsflux_bot
   ```
3. **Issue New Credentials**: Generate a new API Key on Bybit (Contract Trading only, IP restricted).
4. **Update `.env`**:
   ```bash
   sudo nano /opt/nsflux/app/.env
   ```
5. **Restart Service**:
   ```bash
   docker compose up -d
   ```
