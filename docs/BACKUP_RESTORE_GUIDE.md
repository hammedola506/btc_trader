# NSFLUX Trading Bot – Backup & Data Restoration Guide

This document defines backup strategies, automated snapshot routines, and disaster restoration procedures for the SQLite trading journal (`trade_journal.db`) and bot state files (`bot_state.json`).

---

## 1. Backup Strategy Overview

| Backup Target | Frequency | Retention Period | Storage Location | Strategy |
| :--- | :--- | :--- | :--- | :--- |
| `trade_journal.db` | Daily (02:00 UTC) | 30 Days | `/opt/nsflux/backups/` & GCS Bucket | SQLite `.backup` online API (Locks avoided) |
| `bot_state.json` | Hourly | 7 Days | `/opt/nsflux/backups/state/` | Atomic file copy (`bot_state.json.bak`) |
| `.env` Configuration| On Change | Indefinite | GCP Secret Manager / Off-site Secure Vault | Manual / Encrypted backup |

---

## 2. Online SQLite Backup Script

SQLite Write-Ahead Logging (WAL) allows hot backups while the trading bot is actively executing trades without locking the database.

Create `/opt/nsflux/app/backup_db.sh`:

```bash
#!/bin/bash
# NSFLUX Automated SQLite Hot Backup Script
BACKUP_DIR="/opt/nsflux/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DB_PATH="/opt/nsflux/logs/trade_journal.db"
BACKUP_FILE="${BACKUP_DIR}/trade_journal_${TIMESTAMP}.db"
GZ_FILE="${BACKUP_FILE}.gz"

mkdir -p $BACKUP_DIR

# Execute online hot backup using sqlite3 backup command
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

if [ $? -eq 0 ]; then
    # Compress backup file
    gzip -f "$BACKUP_FILE"
    echo "$(date) - SUCCESS: Database backup created at ${GZ_FILE}" >> /opt/nsflux/logs/backup.log
    
    # Optional: Upload to GCP Cloud Storage bucket if gsutil is available
    if command -v gsutil &> /dev/null; then
        gsutil cp "$GZ_FILE" gs://nsflux-db-backups/
    fi
else
    echo "$(date) - ERROR: Database backup failed!" >> /opt/nsflux/logs/backup.log
fi

# Purge local backups older than 30 days
find "$BACKUP_DIR" -name "trade_journal_*.db.gz" -mtime +30 -exec rm -f {} \;
```

Make executable and add to crontab:

```bash
chmod +x /opt/nsflux/app/backup_db.sh
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/nsflux/app/backup_db.sh") | crontab -
```

---

## 3. Step-by-Step Database Restoration Procedure

In the event of database corruption or hardware failover:

### Step 1: Stop the Container Service
```bash
docker stop -t 30 nsflux_bot
```

### Step 2: Verify Database Corruption
```bash
sqlite3 /opt/nsflux/logs/trade_journal.db "PRAGMA integrity_check;"
```

### Step 3: Backup Corrupted File
```bash
mv /opt/nsflux/logs/trade_journal.db /opt/nsflux/logs/trade_journal_corrupt_$(date +%Y%m%d).db
```

### Step 4: Restore Most Recent Backup
```bash
# Locate latest valid compressed backup
LATEST_BACKUP=$(ls -t /opt/nsflux/backups/trade_journal_*.db.gz | head -n 1)

# Decompress and restore
gunzip -c "$LATEST_BACKUP" > /opt/nsflux/logs/trade_journal.db
chmod 666 /opt/nsflux/logs/trade_journal.db
chown nsflux:nsflux /opt/nsflux/logs/trade_journal.db
```

### Step 5: Verify Restored Database Integrity
```bash
sqlite3 /opt/nsflux/logs/trade_journal.db "PRAGMA integrity_check;"
sqlite3 /opt/nsflux/logs/trade_journal.db "SELECT count(*) FROM journal;"
```

### Step 6: Restart Trading Bot Container
```bash
docker start nsflux_bot
```
