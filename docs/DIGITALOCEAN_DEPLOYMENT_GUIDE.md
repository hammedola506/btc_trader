# NSFLUX Trading Bot – DigitalOcean Deployment Guide

This guide details the secondary fallback deployment path using **DigitalOcean Infrastructure**: DigitalOcean Droplet (Ubuntu 22.04 LTS) + Reserved IP + Attached Block Storage Volume + DigitalOcean Container Registry (DOCR).

---

## 1. DigitalOcean Architecture Overview

```text
                                [ Internet Traffic ]
                                         │
                        ┌────────────────┴────────────────┐
                        │ DigitalOcean Reserved IPv4      │
                        └────────────────┬────────────────┘
                                         │
                        ┌────────────────┴────────────────┐
                        │ DigitalOcean Cloud Firewall     │
                        │ (Allow Ports 22, 80, 443)       │
                        └────────────────┬────────────────┘
                                         │
             ┌───────────────────────────┴───────────────────────────┐
             │ DigitalOcean Droplet (2 vCPU / 2GB RAM / Ubuntu)     │
             │                                                       │
             │  ┌─────────────────────────────────────────────────┐  │
             │  │ Nginx (SSL Termination & Basic Auth Reverse Proxy)│  │
             │  └────────────────────────┬────────────────────────┘  │
             │                           │ (http://127.0.0.1:5000)   │
             │  ┌────────────────────────▼────────────────────────┐  │
             │  │ Docker Engine (Container from DOCR)             │  │
             │  └────────────────────────┬────────────────────────┘  │
             │                           │                           │
             │  ┌────────────────────────▼────────────────────────┐  │
             │  │ DigitalOcean Block Storage Volume (/mnt/nsflux) │  │
             │  │ (10GB Persistent Volume for SQLite DB & Logs)   │  │
             │  └─────────────────────────────────────────────────┘  │
             └───────────────────────────────────────────────────────┘
```

---

## 2. Phase 1: Resource Provisioning (doctl CLI / Web Console)

### Step 1: Create DigitalOcean Droplet

Using the `doctl` CLI tool or DigitalOcean Control Panel:

```bash
# Provision 2 vCPU / 2 GB RAM Droplet (s-2vcpu-2gb) in NYC3 region
doctl compute droplet create nsflux-droplet \
    --region nyc3 \
    --image ubuntu-22-04-x64 \
    --size s-2vcpu-2gb \
    --ssh-keys YOUR_SSH_KEY_FINGERPRINT \
    --wait
```

### Step 2: Create & Attach Block Storage Volume

```bash
# Create 10GB Block Storage Volume for database persistence
doctl compute volume create nsflux-data-vol \
    --region nyc3 \
    --size 10GiB \
    --fs-type ext4

# Attach volume to Droplet
doctl compute volume-action attach nsflux-data-vol DROPLET_ID
```

### Step 3: Assign Reserved IP

```bash
# Assign static Reserved IP address to Droplet
doctl compute floating-ip create --droplet-id DROPLET_ID
```

---

## 3. Phase 2: Droplet Storage & Environment Setup

SSH into the Droplet:

```bash
ssh root@YOUR_RESERVED_IP
```

Mount Block Storage Volume:

```bash
# Create mount directory
mkdir -p /mnt/nsflux-data-vol /opt/nsflux/logs

# Mount volume
mount -o discard,defaults,noatime /dev/disk/by-id/scsi-0DO_Volume_nsflux-data-vol /mnt/nsflux-data-vol

# Bind mount volume to /opt/nsflux/logs
mount --bind /mnt/nsflux-data-vol /opt/nsflux/logs

# Make mount permanent in /etc/fstab
echo '/dev/disk/by-id/scsi-0DO_Volume_nsflux-data-vol /mnt/nsflux-data-vol ext4 discard,defaults,noatime,nofail 0 2' >> /etc/fstab
echo '/mnt/nsflux-data-vol /opt/nsflux/logs none defaults,bind 0 0' >> /etc/fstab
```

---

## 4. Phase 3: Deployment & Execution

### Step 1: Install Docker & Clone Repository

```bash
# Install Docker Engine
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker

# Clone repository
git clone https://github.com/hammedola506/btc_trader.git /opt/nsflux/app
cd /opt/nsflux/app
```

### Step 2: Configure Environment Variables (`.env`)

Create `/opt/nsflux/app/.env`:

```ini
USE_DEMO_TRADING=True
DASHBOARD_AUTH_ENABLED=True
DASHBOARD_USERNAME=admin_trader
DASHBOARD_PASSWORD=SecureProductionPassword2026!
SECRET_KEY=c839f182e0a4b790d9a8f7b6c5e4d3a2b10f9e8d7c6b5a4
EXCHANGE_API_KEY=your_actual_bybit_api_key
EXCHANGE_API_SECRET=your_actual_bybit_api_secret
NOTIFICATION_ENABLED=True
TELEGRAM_BOT_TOKEN=8607017007:AAENis-LlbfciiLNvnUrZvHgUvgoTyIkMHA
TELEGRAM_CHAT_ID=5957450774
PORT=5000
```

### Step 3: Run Docker Container

```bash
# Build container image on Droplet
docker compose build

# Start container service
docker compose up -d
```

### Step 4: Configure Nginx & Certbot SSL

```bash
# Install Nginx and Certbot
apt-get install -y nginx certbot python3-certbot-nginx

# Configure Nginx site
cat <<EOF > /etc/nginx/sites-available/nsflux
server {
    listen 80;
    server_name do-trading.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Activate site and issue Let's Encrypt SSL certificate
ln -sf /etc/nginx/sites-available/nsflux /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
certbot --nginx -d do-trading.yourdomain.com --non-interactive --agree-tos -m your-email@domain.com
```

---

## 5. Verification

```bash
# Check running container health
docker inspect --format='{{json .State.Health.Status}}' nsflux_bot

# Verify HTTP response
curl -i https://do-trading.yourdomain.com/api/health
```
