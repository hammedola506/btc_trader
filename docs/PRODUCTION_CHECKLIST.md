# NSFLUX Trading Bot – Master Production Deployment Checklist

This document is the mandatory pre-flight and launch readiness checklist. Every section must be verified and checked off prior to promoting NSFLUX to live trading operations.

---

## 1. Environment & Configuration Checklist

- [ ] `.env` file created in `/opt/nsflux/app/.env` with `0600` permissions owned by `nsflux:nsflux`.
- [ ] `USE_DEMO_TRADING` set to `True` for initial dry-run (or `False` for live trading).
- [ ] `DASHBOARD_AUTH_ENABLED` set to `True`.
- [ ] `DASHBOARD_USERNAME` set to secure custom username (changed from default `admin`).
- [ ] `DASHBOARD_PASSWORD` set to a strong 20+ character random password.
- [ ] `SECRET_KEY` set to a 64-character random hexadecimal string.
- [ ] `EXCHANGE_API_KEY` & `EXCHANGE_API_SECRET` verified against Bybit API console.
- [ ] `NOTIFICATION_ENABLED` set to `True`.
- [ ] `TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID` verified with test message dispatch.

---

## 2. Docker & Container Security Checklist

- [ ] Dockerfile uses multi-stage build (`builder` -> `runtime`).
- [ ] Base image pinned to `python:3.11-slim-bookworm`.
- [ ] Application runs under dedicated non-root user `nsflux` (`UID:GID 10001:10001`).
- [ ] Container root filesystem is read-only except for volume mount `/app/logs`.
- [ ] Docker HEALTHCHECK defined and passing (`healthy`).
- [ ] Gunicorn execution uses `--workers 1 --threads 4` (single worker preserves state).
- [ ] Image built and tagged in Google Artifact Registry (or DOCR).

---

## 3. Host Server Infrastructure Checklist

- [ ] Server OS updated (`apt-get update && apt-get dist-upgrade`).
- [ ] Time synchronization active (`systemd-timesyncd` verified with `timedatectl`).
- [ ] 2 GB Swap space allocated and enabled (`/swapfile`).
- [ ] Dedicated persistent disk formatted (ext4) and mounted to `/opt/nsflux/logs`.
- [ ] `/etc/fstab` configured with `nofail,discard,defaults` for data disk.
- [ ] Host disk space checked (`df -h /opt/nsflux/logs` shows > 10GB free).

---

## 4. Network & Security Hardening Checklist

- [ ] SSH password authentication disabled (`PasswordAuthentication no` in `/etc/ssh/sshd_config`).
- [ ] SSH root login disabled (`PermitRootLogin no`).
- [ ] UFW firewall enabled (`ufw default deny incoming`, allowing ports 22, 80, 443).
- [ ] Fail2ban active for SSH (`fail2ban-client status sshd`).
- [ ] Cloud VPC Firewall rules set to restrict incoming traffic to ports 80 & 443.

---

## 5. Nginx & Reverse Proxy Checklist

- [ ] Nginx installed and running (`systemctl status nginx`).
- [ ] Proxy pass configured to `127.0.0.1:5000`.
- [ ] Security headers enabled (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`).
- [ ] Let's Encrypt SSL certificate issued via Certbot (`certbot --nginx`).
- [ ] HTTP to HTTPS redirect active (301 Permanent Redirect).
- [ ] Certbot auto-renewal timer active (`systemctl status certbot.timer`).

---

## 6. Database & Persistence Checklist

- [ ] SQLite database file `/opt/nsflux/logs/trade_journal.db` created with schema initialized.
- [ ] SQLite WAL (Write-Ahead Logging) mode enabled (`PRAGMA journal_mode=WAL`).
- [ ] Atomic bot state persistence file `/opt/nsflux/logs/bot_state.json` initialized.
- [ ] Automated daily backup cron job configured (`/etc/cron.daily/nsflux-backup`).

---

## 7. Monitoring & Alerting Checklist

- [ ] Telegram notifications tested and working (`test_exchange_disconnect_telegram.py`).
- [ ] Log rotation configured (`/etc/logrotate.d/nsflux`).
- [ ] Systemd auto-restart service enabled (`systemctl status nsflux-bot.service`).
- [ ] HTTP endpoint `/api/health` returning `HTTP 200 OK`.

---

## 8. Deployment Sign-off Verification

```bash
# Final check command suite
docker inspect --format='{{json .State.Health.Status}}' nsflux_bot
curl -i https://yourdomain.com/api/health
```

**STATUS:** **READY FOR DEPLOYMENT**
