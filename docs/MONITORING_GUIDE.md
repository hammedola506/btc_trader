# NSFLUX Trading Bot – Monitoring & Health Observability Guide

This document defines the metrics, health checks, log monitoring strategies, and alerting thresholds for maintaining 24/7 observability over **NSFLUX**.

---

## 1. System Metrics & Observability Matrix

| Metric Category | Target Component | Monitoring Tool / Command | Warning Threshold | Critical Threshold | Action Required |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **System CPU** | Host VM (GCE / DO) | `htop` / `mpstat` / GCP Cloud Monitoring | > 70% for 10 min | > 90% for 5 min | Check background processes, restart container. |
| **System Memory** | Host RAM + Swap | `free -m` / `htop` | > 80% RAM | > 95% RAM (Swap active) | Inspect memory leaks, restart Gunicorn worker. |
| **Disk Storage** | Persistent Volume `/opt/nsflux/logs` | `df -h /opt/nsflux/logs` | > 75% capacity | > 90% capacity | Run log rotation, purge old backups. |
| **Container Status**| Docker Daemon | `docker inspect nsflux_bot` | Container restart count > 2 | Container Status `unhealthy` | Inspect `docker logs nsflux_bot`. |
| **HTTP Readiness** | Gunicorn WSGI (`/api/health`) | `curl` / Docker HEALTHCHECK | Response time > 2s | Status Code != 200 | Restart Gunicorn service. |
| **Database** | SQLite `trade_journal.db` | `sqlite3 PRAGMA integrity_check;` | File size > 500 MB | DB locked / corrupt | Run WAL checkpoint, restore from backup. |
| **Exchange Link** | Bybit API Connectivity | `test_exchange_disconnect_telegram.py` | 1 Network Failure | 2 Consecutive Failures | Auto-trigger Telegram Disconnect Alert. |

---

## 2. Docker Healthcheck & Monitoring Setup

### 2.1 Native Container Healthcheck
The production container runs an internal healthcheck every 30 seconds against `/api/health`:

```bash
# Query health status of container
docker inspect --format='{{json .State.Health}}' nsflux_bot | jq .
```

Sample Healthy Output:
```json
{
  "Status": "healthy",
  "FailingStreak": 0,
  "Log": [
    {
      "ExitCode": 0,
      "Output": "{\"bot_thread_alive\":true,\"db_connected\":true,\"exchange_connected\":true,\"status\":\"ok\"}"
    }
  ]
}
```

---

## 3. Log Management & Logrotate Setup

Configure host log rotation to prevent `/app/logs/trading_bot.log` from exhausting disk space.

Create `/etc/logrotate.d/nsflux`:

```text
/opt/nsflux/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0666 nsflux nsflux
    postrotate
        docker kill -s HUP nsflux_bot 2>/dev/null || true
    endscript
}
```

Test logrotate configuration:

```bash
sudo logrotate -d /etc/logrotate.d/nsflux
```

---

## 4. Automated Uptime Health Probe Script

Create a cron health probe `/opt/nsflux/app/health_probe.sh`:

```bash
#!/bin/bash
# NSFLUX Automated Uptime Probe
HEALTH_URL="http://127.0.0.1:5000/api/health"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ "$HTTP_STATUS" -ne 200 ]; then
    echo "$(date) - CRITICAL: Health probe failed with HTTP status $HTTP_STATUS" >> /opt/nsflux/logs/probe_errors.log
    # Trigger restart if unreachable
    docker restart nsflux_bot
fi
```

Make executable and add to crontab:

```bash
chmod +x /opt/nsflux/app/health_probe.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/nsflux/app/health_probe.sh") | crontab -
```
