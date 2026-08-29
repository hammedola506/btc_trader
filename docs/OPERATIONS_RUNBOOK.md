# NSFLUX Trading Bot – Operations Runbook

This runbook defines standard operating procedures (SOP) for day-to-day operations, routine maintenance, emergency interventions, and service monitoring for the **NSFLUX BTC/USDT Trading Bot**.

---

## 1. Routine Maintenance Schedules

### Daily Maintenance Checklist (5 Minutes)
1. **Check Container Status**:
   ```bash
   docker inspect --format='{{.State.Status}} (Health: {{.State.Health.Status}})' nsflux_bot
   ```
2. **Inspect Container Log Stream for Errors**:
   ```bash
   docker logs --tail 100 nsflux_bot | grep -iE 'error|exception|warning|circuit'
   ```
3. **Verify Dashboard Health Endpoint**:
   ```bash
   curl -s http://127.0.0.1:5000/api/health
   ```
4. **Check Telegram Dispatch Status**: Ensure heartbeat or daily PnL summaries arrived in Telegram.

---

### Weekly Maintenance Checklist (15 Minutes)
1. **Verify SQLite Database Backup Integrity**:
   ```bash
   ls -lh /opt/nsflux/backups/
   sqlite3 /opt/nsflux/logs/trade_journal.db "PRAGMA integrity_check;"
   ```
2. **Check Disk Space Usage**:
   ```bash
   df -h /opt/nsflux/logs
   ```
3. **Inspect Nginx Access & Error Logs**:
   ```bash
   tail -n 50 /var/log/nginx/error.log
   ```

---

### Monthly Maintenance Checklist (30 Minutes)
1. **Host Package Updates**:
   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   ```
2. **Docker System Cleanup**:
   ```bash
   docker system prune -f
   ```
3. **Certbot SSL Certificate Auto-Renewal Check**:
   ```bash
   sudo certbot renew --dry-run
   ```

---

## 2. Standard Operating Procedures (SOP)

### SOP-01: Start the Trading Bot Service
```bash
cd /opt/nsflux/app
docker compose up -d
```

### SOP-02: Graceful Stop of Trading Bot
```bash
# Gracefully stop container (30s timeout allows loop thread termination)
docker stop -t 30 nsflux_bot
```

### SOP-03: Restart the Trading Bot Service
```bash
docker restart nsflux_bot
```

### SOP-04: View Real-Time Application Logs
```bash
docker logs -f --tail 200 nsflux_bot
```

### SOP-05: Emergency Bot Halt (Kill Switch)
If the trading bot executes erroneous signals or market volatility trips abnormal behavior:

```bash
# Method 1: Via Authenticated REST API (Immediate thread stop)
curl -X POST -u admin_trader:SecurePassword \
  http://127.0.0.1:5000/api/stop

# Method 2: Container Emergency Stop (SIGTERM)
docker stop -t 5 nsflux_bot
```

### SOP-06: Clear Tripped Circuit Breaker
If the circuit breaker trips due to consecutive API network failures:

1. Inspect error cause in logs:
   ```bash
   docker logs nsflux_bot | grep -i "circuit_breaker"
   ```
2. Restart container to reset in-memory circuit breaker counter:
   ```bash
   docker restart nsflux_bot
   ```

---

## 3. Incident Escalation & Response Flowchart

```text
[ Alert Triggered ] ──> Telegram Disconnect Alert / Container Down
         │
         ├──> Step 1: Check HTTP /api/health endpoint
         ├──> Step 2: Check docker logs nsflux_bot
         ├──> Step 3: Check Bybit Exchange API status page
         │
         ├──> [ If DB issue ]: Run sqlite3 integrity_check (See BACKUP_RESTORE_GUIDE.md)
         └──> [ If Server unreachable ]: Reboot instance via GCP Console / DO Control Panel
```
