# NSFLUX Trading Bot – Production Rollback Plan

This document defines standard emergency rollback procedures for reverting container images, database state, and configuration changes in production.

---

## 1. Rollback Trigger Criteria

Initiate a rollback if any of the following occur following a production deployment:
- Unhandled runtime exceptions causing continuous container crashes (`CrashLoopBackOff` / `FailingStreak` > 3).
- Signal calculation regressions or incorrect order size calculation.
- Database locking errors preventing trade journal updates.
- Inability to establish exchange API connections due to build/dependency breaking changes.

---

## 2. Emergency Container Rollback Procedure (10 Minutes)

### Step 1: Stop Current Failed Container
```bash
docker stop -t 10 nsflux_bot
```

### Step 2: Identify Previous Stable Docker Image
List available local or remote Artifact Registry container image tags:

```bash
# Local image tags
docker images nsflux-bot

# GCP Artifact Registry tags
gcloud artifacts docker images list us-central1-docker.pkg.dev/nsflux-trading-prod/nsflux-repo/nsflux-bot
```

### Step 3: Re-Tag and Launch Previous Stable Image
```bash
# Re-tag previous stable release (e.g. v1.0.0-previous)
docker tag us-central1-docker.pkg.dev/nsflux-trading-prod/nsflux-repo/nsflux-bot:v1.0.0-previous nsflux-bot:latest

# Launch container with previous stable image
cd /opt/nsflux/app
docker compose up -d --force-recreate
```

### Step 4: Verify Service Restoration
```bash
docker inspect --format='{{json .State.Health.Status}}' nsflux_bot
curl -i http://127.0.0.1:5000/api/health
```

---

## 3. Database State Rollback Procedure

If a deployment modified SQLite database tables or corrupted journal entries:

```bash
# 1. Stop container
docker stop -t 10 nsflux_bot

# 2. Restore pre-deployment DB snapshot (created before deployment)
cp /opt/nsflux/backups/pre_deploy_trade_journal.db /opt/nsflux/logs/trade_journal.db

# 3. Verify SQLite integrity
sqlite3 /opt/nsflux/logs/trade_journal.db "PRAGMA integrity_check;"

# 4. Restart container
docker start nsflux_bot
```

---

## 4. Git Code Revert Procedure

To revert source code changes to a previous git commit hash:

```bash
cd /opt/nsflux/app

# Checkout previous stable commit or release tag
git checkout main
git reset --hard COMMIT_HASH

# Rebuild container image locally
docker compose build --no-cache
docker compose up -d
```
