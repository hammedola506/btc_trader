# NSFLUX Trading Bot – Google Compute Engine (GCE) Deployment Guide

This guide details the primary production deployment path using **Google Cloud Platform (GCP)** infrastructure: Google Compute Engine (GCE) Compute Virtual Machine + Google Artifact Registry + Cloud Secret Manager.

---

## 1. Google Cloud Infrastructure Architecture

```text
                                [ GCP Network Security ]
                                           │
                        ┌──────────────────┴──────────────────┐
                        │ Static External IP (Reserved IPv4)  │
                        └──────────────────┬──────────────────┘
                                           │
                                  ┌────────┴────────┐
                                  │ GCE VPC Network │
                                  │ Firewall Rules  │
                                  │ (Allow 80, 443) │
                                  └────────┬────────┘
                                           │
                ┌──────────────────────────┴──────────────────────────┐
                │ Google Compute Engine Instance (e2-standard-2)       │
                │                                                     │
                │ ┌─────────────────────────────────────────────────┐ │
                │ │ Nginx (SSL Termination & Rate Limiting)        │ │
                │ └────────────────────────┬────────────────────────┘ │
                │                          │ (http://127.0.0.1:5000)   │
                │ ┌────────────────────────▼────────────────────────┐ │
                │ │ Docker Runtime (nsflux-bot:latest)              │ │
                │ │ Container pulls from GCP Artifact Registry      │ │
                │ └────────────────────────┬────────────────────────┘ │
                │                          │                          │
                │ ┌────────────────────────▼────────────────────────┐ │
                │ │ Persistent Disk Mount (/opt/nsflux/logs)        │ │
                │ │ (ext4 Persistent SSD Disk - 20GB)               │ │
                │ └─────────────────────────────────────────────────┘ │
                └─────────────────────────────────────────────────────┘
```

---

## 2. Phase 1: GCP Resource Provisioning Commands

### Step 1: Set GCP CLI Environment Variables

```bash
# Set GCP environment parameters
export GCP_PROJECT_ID="nsflux-trading-prod"
export GCP_REGION="us-central1"
export GCP_ZONE="us-central1-a"
export INSTANCE_NAME="nsflux-bot-vm"
export ARTIFACT_REPO="nsflux-repo"

gcloud config set project $GCP_PROJECT_ID
gcloud config set compute/region $GCP_REGION
gcloud config set compute/zone $GCP_ZONE
```

### Step 2: Enable Required GCP APIs

```bash
gcloud services enable \
    compute.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    logging.googleapis.com
```

### Step 3: Create Google Artifact Registry Repository

```bash
# Create Docker repository in Artifact Registry
gcloud artifacts repositories create $ARTIFACT_REPO \
    --repository-format=docker \
    --location=$GCP_REGION \
    --description="NSFLUX Trading Bot Container Images"

# Authenticate local Docker daemon with Artifact Registry
gcloud auth configure-docker ${GCP_REGION}-docker.pkg.dev
```

### Step 4: Create Static External IP Address

```bash
# Reserve static external IP address
gcloud compute addresses create nsflux-static-ip --region=$GCP_REGION

# Retrieve reserved IP
gcloud compute addresses describe nsflux-static-ip \
    --region=$GCP_REGION \
    --format='value(address)'
```

### Step 5: Configure VPC Firewall Rules

```bash
# Allow HTTP traffic (Port 80)
gcloud compute firewall-rules create allow-http-nsflux \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:80 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=nsflux-web

# Allow HTTPS traffic (Port 443)
gcloud compute firewall-rules create allow-https-nsflux \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:443 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=nsflux-web
```

---

## 3. Phase 2: Create GCE Instance with Persistent Storage

Create the Compute Engine instance attached to a dedicated persistent disk:

```bash
# Create 20GB Persistent Disk for DB & Log storage
gcloud compute disks create nsflux-data-disk \
    --size=20GB \
    --type=pd-ssd \
    --zone=$GCP_ZONE

# Provision GCE Instance (e2-standard-2, Ubuntu 22.04 LTS)
gcloud compute instances create $INSTANCE_NAME \
    --zone=$GCP_ZONE \
    --machine-type=e2-standard-2 \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-balanced \
    --disk=name=nsflux-data-disk,mode=rw,device-name=nsflux-data-disk \
    --address=nsflux-static-ip \
    --tags=nsflux-web \
    --scopes=cloud-platform \
    --metadata=enable-oslogin=TRUE
```

---

## 4. Phase 3: Cloud Secret Manager Setup

Store sensitive credentials in GCP Secret Manager:

```bash
# Create secrets in Cloud Secret Manager
echo -n "your_actual_bybit_api_key" | gcloud secrets create BYBIT_API_KEY --data-file=-
echo -n "your_actual_bybit_api_secret" | gcloud secrets create BYBIT_API_SECRET --data-file=-
echo -n "SecureProductionPassword2026!" | gcloud secrets create DASHBOARD_PASSWORD --data-file=-
echo -n "8607017007:AAENis-LlbfciiLNvnUrZvHgUvgoTyIkMHA" | gcloud secrets create TELEGRAM_BOT_TOKEN --data-file=-
```

---

## 5. Phase 4: Container Build & Push to Artifact Registry

Build and push the production image from your local environment:

```bash
# Define full Artifact Registry image path
IMAGE_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REPO}/nsflux-bot:v1.0.0"

# Build production container image
docker build -t $IMAGE_URI .

# Push image to GCP Artifact Registry
docker push $IMAGE_URI
```

---

## 6. Phase 5: GCE VM Deployment Execution

SSH into your GCE VM:

```bash
gcloud compute ssh $INSTANCE_NAME --zone=$GCP_ZONE
```

Run VM startup setup inside SSH session:

```bash
# 1. Format and mount persistent data disk to /opt/nsflux/logs
sudo mkdir -p /opt/nsflux/logs
sudo mkfs.ext4 -F /dev/disk/by-id/google-nsflux-data-disk
sudo mount -o discard,defaults /dev/disk/by-id/google-nsflux-data-disk /opt/nsflux/logs

# Make mount permanent in /etc/fstab
echo '/dev/disk/by-id/google-nsflux-data-disk /opt/nsflux/logs ext4 discard,defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo chmod 777 /opt/nsflux/logs

# 2. Authenticate Docker with GCP Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

# 3. Pull container image and launch container
docker pull us-central1-docker.pkg.dev/nsflux-trading-prod/nsflux-repo/nsflux-bot:v1.0.0

docker run -d \
  --name nsflux_bot \
  --restart=always \
  -p 127.0.0.1:5000:5000 \
  --env-file /opt/nsflux/app/.env \
  -v /opt/nsflux/logs:/app/logs \
  us-central1-docker.pkg.dev/nsflux-trading-prod/nsflux-repo/nsflux-bot:v1.0.0
```

---

## 7. Verification

Confirm GCE VM container execution:

```bash
docker ps
docker inspect --format='{{json .State.Health.Status}}' nsflux_bot
```
