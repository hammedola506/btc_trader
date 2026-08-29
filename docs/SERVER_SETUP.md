# NSFLUX Trading Bot – Server Setup & Infrastructure Provisioning Guide

This guide details the complete provisioning, OS tuning, security baseline, and runtime installation required to prepare a fresh Linux Ubuntu 22.04 LTS server (Google Compute Engine or DigitalOcean Droplet) for hosting the NSFLUX trading bot.

---

## 1. Prerequisites & System Requirements

| Metric | Minimum Recommended | Production Ideal |
| :--- | :--- | :--- |
| **OS** | Ubuntu 22.04 / 24.04 LTS (x86_64) | Ubuntu 22.04 LTS (x86_64) |
| **CPU** | 1 vCPU (Compute-Optimized) | 2 vCPU |
| **RAM** | 1 GB RAM + 2 GB Swap | 2 GB RAM + 2 GB Swap |
| **Disk** | 20 GB SSD (NVMe preferred) | 30 GB SSD (Persistent SSD Disk) |
| **Network** | Dedicated IPv4 + Static Egress IP | Static External IP |
| **NTP** | Active Time Synchronization (`systemd-timesyncd`) | Required for exchange API HMAC signature timestamps |

---

## 2. Phase 1: Initial System Preparation & Tuning

### 2.1 Package Updates & Base Tools
Log into the fresh server as root (or administrative user) via SSH:

```bash
# Update APT package indexes and upgrade existing packages
sudo apt-get update && sudo apt-get dist-upgrade -y

# Install core system management utilities
sudo apt-get install -y \
    curl \
    wget \
    git \
    ufw \
    fail2ban \
    htop \
    iotop \
    net-tools \
    unzip \
    ca-certificates \
    gnupg \
    lsb-release \
    systemd-timesyncd \
    logrotate \
    sqlite3
```

### 2.2 Time Synchronization (Crucial for Exchange API Signatures)
Bybit and crypto exchange APIs require accurate request timestamps (within 5000 ms). Configure time synchronization:

```bash
# Enable systemd-timesyncd service
sudo systemctl enable --now systemd-timesyncd

# Configure NTP servers
sudo bash -c 'cat <<EOF > /etc/systemd/timesyncd.conf
[Time]
NTP=0.ubuntu.pool.ntp.org 1.ubuntu.pool.ntp.org time.google.com
FallbackNTP=ntp.ubuntu.com
EOF'

# Restart timesyncd and verify status
sudo systemctl restart systemd-timesyncd
timedatectl status
```

### 2.3 Swap File Creation (2 GB Memory Buffer)
Prevent Out-Of-Memory (OOM) process termination during heavy backtests or data processing:

```bash
# Create 2GB swap allocation if no swap exists
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make swap permanent across reboots
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Tune kernel swappiness for server workload
sudo sysctl vm.swappiness=20
echo 'vm.swappiness=20' | sudo tee -a /etc/sysctl.conf
```

---

## 3. Phase 2: User Access & SSH Hardening

### 3.1 Create Service User (`nsflux`)
Isolate application processes from system administrative users:

```bash
# Create dedicated system user nsflux without shell access
sudo groupadd --gid 10001 nsflux
sudo useradd --uid 10001 --gid 10001 --create-home --shell /bin/bash nsflux

# Add deployment user to docker group (after docker installation below)
```

### 3.2 Hardening SSH (`/etc/ssh/sshd_config`)

```bash
# Backup existing SSH configuration
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

# Apply hardening settings
sudo bash -c 'cat <<EOF > /etc/ssh/sshd_config.d/nsflux_security.conf
# NSFLUX Production SSH Hardening
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
AllowTcpForwarding no
EOF'

# Test SSH configuration syntax and restart SSH service
sudo sshd -t && sudo systemctl restart ssh
```

---

## 4. Phase 3: Firewall & Network Security (UFW & Fail2ban)

### 4.1 UFW Firewall Configuration
Expose ONLY SSH (port 22), HTTP (port 80), and HTTPS (port 443). Block all other incoming ports:

```bash
# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow essential ports
sudo ufw allow 22/tcp comment 'SSH Access'
sudo ufw allow 80/tcp comment 'HTTP (Certbot ACME)'
sudo ufw allow 443/tcp comment 'HTTPS (Web Dashboard)'

# Enable firewall
sudo ufw --force enable
sudo ufw status verbose
```

### 4.2 Fail2ban Configuration
Protect SSH against brute-force intrusion:

```bash
# Create local fail2ban jail configuration
sudo bash -c 'cat <<EOF > /etc/fail2ban/jail.local
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 3

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
EOF'

# Start fail2ban service
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```

---

## 5. Phase 4: Container Runtime Installation (Docker & Docker Compose)

Install official Docker Engine binaries (not snap):

```bash
# Add Docker official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine, CLI, Containerd, and Docker Compose plugin
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable Docker service auto-start
sudo systemctl enable --now docker

# Grant nsflux and current admin user docker access
sudo usermod -aG docker nsflux
sudo usermod -aG docker $USER
```

---

## 6. Phase 5: Production Directory Structure

Prepare dedicated directory structure on host disk:

```bash
# Create application root directory
sudo mkdir -p /opt/nsflux /opt/nsflux/logs /opt/nsflux/backups /opt/nsflux/nginx/conf.d

# Set directory permissions
sudo chown -R nsflux:nsflux /opt/nsflux
sudo chmod 755 /opt/nsflux
sudo chmod 777 /opt/nsflux/logs
sudo chmod 750 /opt/nsflux/backups
```

Directory Layout Overview:
```text
/opt/nsflux/
├── docker-compose.yml       # Production orchestrator
├── .env                     # Production environment variables (0600 permissions)
├── logs/                    # Volume mount for SQLite DB, logs, atomic states
│   ├── trade_journal.db
│   ├── bot_state.json
│   └── trading_bot.log
├── backups/                 # Local daily compressed SQLite snapshots
└── nginx/                   # Nginx reverse proxy configuration
    └── conf.d/
        └── nsflux.conf
```

---

## 7. Verification Checklist

Run these commands to confirm server readiness:

```bash
# 1. Check Docker & Compose version
docker --version && docker compose version

# 2. Check UFW status
sudo ufw status

# 3. Check time sync status
timedatectl | grep 'System clock synchronized'

# 4. Check swap space
swapon --show
```
