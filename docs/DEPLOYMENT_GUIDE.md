# NSFLUX Trading Bot – Master Production Deployment Guide

This document presents the complete, end-to-end production deployment instructions for deploying the **NSFLUX BTC/USDT Trading Bot** to Google Compute Engine (Primary) or DigitalOcean VPS (Secondary).

---

## 1. High-Level Deployment Architecture

The production setup uses a containerized model behind an Nginx reverse proxy:

```text
[ Client Web Browser ]
         │ (HTTPS Port 443)
         ▼
[ Nginx Reverse Proxy (Host) ] ── (TLS Termination via Let's Encrypt)
         │ (HTTP 127.0.0.1:5000)
         ▼
[ Docker Container: nsflux_bot ]
         ├── Gunicorn WSGI Server (1 worker, 4 threads)
         ├── Flask Dashboard & REST API
         └── Async Trading Loop (Bybit Demo/Live API)
         │
         ▼ Volume Mount (-v /opt/nsflux/logs:/app/logs)
[ Persistent Host Volume ]
         ├── trade_journal.db (SQLite Journal)
         ├── bot_state.json   (Atomic State)
         └── trading_bot.log  (App Log Stream)
```

---

## 2. Step-by-Step Production Deployment Workflow

### Step 1: Clone Repository & Create Directory Layout

Log in to your server and initialize `/opt/nsflux`:

```bash
# Navigate to application base directory
cd /opt/nsflux

# Clone codebase (or copy source tarball)
git clone https://github.com/hammedola506/btc_trader.git /opt/nsflux/app
cd /opt/nsflux/app
```

### Step 2: Configure Production Environment (`.env`)

Create the secure production environment configuration file `/opt/nsflux/app/.env`:

```bash
sudo touch /opt/nsflux/app/.env
sudo chmod 600 /opt/nsflux/app/.env
sudo chown nsflux:nsflux /opt/nsflux/app/.env
```

Populate `/opt/nsflux/app/.env` with your production variables:

```ini
# Production Environment Configuration
USE_DEMO_TRADING=True
DASHBOARD_AUTH_ENABLED=True

# Security Credentials (CHANGE THESE IN PRODUCTION!)
DASHBOARD_USERNAME=admin_trader
DASHBOARD_PASSWORD=SecureProductionPassword2026!
SECRET_KEY=c839f182e0a4b790d9a8f7b6c5e4d3a2b10f9e8d7c6b5a4

# Exchange API Credentials (Bybit Demo / Live)
EXCHANGE_API_KEY=your_actual_bybit_api_key
EXCHANGE_API_SECRET=your_actual_bybit_api_secret

# Telegram Notification Credentials
NOTIFICATION_ENABLED=True
TELEGRAM_BOT_TOKEN=8607017007:AAENis-LlbfciiLNvnUrZvHgUvgoTyIkMHA
TELEGRAM_CHAT_ID=5957450774

# Runtime Settings
PORT=5000
PYTHONUNBUFFERED=1
```

### Step 3: Production `docker-compose.yml` Configuration

Ensure `/opt/nsflux/app/docker-compose.yml` is present:

```yaml
version: '3.8'

services:
  nsflux-bot:
    build:
      context: .
      dockerfile: Dockerfile
    image: nsflux-bot:latest
    container_name: nsflux_bot
    restart: always
    env_file:
      - .env
    ports:
      - "127.0.0.1:5000:5000"
    volumes:
      - /opt/nsflux/logs:/app/logs
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
```

### Step 4: Build & Launch Docker Container

Build and start the application container:

```bash
# Build Docker image locally
docker compose build --no-cache

# Run container in detached mode
docker compose up -d

# Verify running container status
docker compose ps
```

### Step 5: Configure Nginx Reverse Proxy

Install Nginx:

```bash
sudo apt-get install -y nginx
```

Create Nginx site configuration file `/etc/nginx/sites-available/nsflux`:

```nginx
server {
    listen 80;
    server_name trading.yourdomain.com; # Replace with your domain or server IP

    # Block common exploit scans
    location ~ /\. {
        deny all;
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for live dashboard updates)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts for long operations
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
```

Enable site configuration and test Nginx:

```bash
sudo ln -sf /etc/nginx/sites-available/nsflux /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
```

### Step 6: Enable HTTPS with Let's Encrypt (Certbot)

Obtain free automated SSL certificate:

```bash
# Install Certbot Nginx plugin
sudo apt-get install -y certbot python3-certbot-nginx

# Obtain SSL Certificate (replace with actual domain)
sudo certbot --nginx -d trading.yourdomain.com --non-interactive --agree-tos -m your-email@domain.com

# Verify automated renewal cron/timer
sudo systemctl status certbot.timer
```

---

## 3. Post-Deployment Verification Commands

Run these verification commands immediately after deployment:

```bash
# 1. Verify container HEALTHCHECK status
docker inspect --format='{{json .State.Health.Status}}' nsflux_bot

# 2. Check Gunicorn process & HTTP logs inside container
docker logs --tail 30 nsflux_bot

# 3. Test HTTP Health Endpoint
curl -i https://trading.yourdomain.com/api/health

# 4. Test Authenticated Status Endpoint
curl -i -u admin_trader:SecureProductionPassword2026! https://trading.yourdomain.com/api/status

# 5. Confirm Volume Write Access (SQLite Journal)
ls -la /opt/nsflux/logs/
```

---

## 4. Systemd Auto-Restart Service

Ensure Docker container restarts automatically on server reboots:

Create `/etc/systemd/system/nsflux-bot.service`:

```ini
[Unit]
Description=NSFLUX Trading Bot Container Service
After=docker.service nginx.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/nsflux/app
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable systemd service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable nsflux-bot.service
```
