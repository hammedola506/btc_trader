# NSFLUX Trading Bot – Security Hardening & Compliance Manual

This document defines the production security posture, hardening guidelines, and threat mitigation strategies for the **NSFLUX BTC/USDT Trading Bot**.

---

## 1. Security Architecture & Threat Model

```text
[ Attacker / Public Internet ]
           │
           │ (Blocked on all ports except 80, 443, 22)
           ▼
┌─────────────────────────────────────────────────────────────┐
│ Host Security Layer (Ubuntu 22.04 LTS)                      │
│   • UFW Firewall (Deny all incoming except 22, 80, 443)    │
│   • Fail2ban (Ban IPs with >3 failed SSH attempts)          │
│   • SSH Hardening (Ed25519 Keys only, Root Login disabled)  │
│   • Automatic Security Updates (unattended-upgrades)        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Nginx Reverse Proxy Layer                                   │
│   • SSL/TLS Termination (TLS 1.2 / 1.3 only via Certbot)   │
│   • HTTP Basic Auth & Session Cookie Protection             │
│   • Security Headers (HSTS, X-Frame-Options, CSP)           │
│   • Anti-Brute-Force Rate Limiting                          │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Loopback 127.0.0.1:5000)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Isolated Container Boundary (Docker)                        │
│   • Non-Root Execution (nsflux user UID 10001)              │
│   • Read-Only Root Filesystem (Except /app/logs)            │
│   • Secrets injected via environment variables (chmod 0600) │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Security Hardening Specifications

### 2.1 SSH Hardening (`/etc/ssh/sshd_config.d/nsflux_security.conf`)
- Disallow root SSH login (`PermitRootLogin no`).
- Disable password-based SSH authentication (`PasswordAuthentication no`).
- Use SSH Ed25519 cryptographic keys exclusively.
- Restrict authentication attempts (`MaxAuthTries 3`).

### 2.2 UFW Firewall Hardening
- Set default policy to DENY all incoming connections (`ufw default deny incoming`).
- Expose ONLY SSH (port 22), HTTP (port 80), and HTTPS (port 443).
- Block exposure of Gunicorn port 5000 directly to the internet (bind Gunicorn container to `127.0.0.1:5000`).

### 2.3 Container Isolation & Non-Root Execution
- Container executes under non-root user `nsflux` (`UID:GID 10001:10001`).
- Container filesystem is read-only except for the volume mount path `/app/logs`.
- Environment variable secrets injected via protected `.env` file (`chmod 0600`).

### 2.4 Nginx Web Security Headers
Configure Nginx to send modern enterprise security headers:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com;" always;
```

### 2.5 Unattended Security Updates
Enable automatic security updates for Ubuntu host OS:

```bash
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

---

## 3. Secret Management Security Standards

1. **No Secrets in Source Control**: `.env`, `.pem`, `.db`, `.key` files are strictly excluded via `.gitignore` and `.dockerignore`.
2. **Environment Variable Security**: All API keys, secrets, and passwords are loaded via environment variables at runtime.
3. **Bybit API Key Permissions**:
   - Enable: **Contract Trading - Orders & Positions**.
   - Disable: **Withdrawals** (NEVER grant withdrawal permission to API keys!).
   - Restrict to static IP: Bind Bybit API keys to the server's static egress IP.

---

## 4. Security Audit Verification Commands

```bash
# 1. Verify SSH password authentication is disabled
ssh -o PubkeyAuthentication=no root@localhost

# 2. Verify firewall rules
sudo ufw status verbose

# 3. Test non-root user inside running container
docker exec nsflux_bot id

# 4. Check for open host ports
sudo netstat -tulpn
```
