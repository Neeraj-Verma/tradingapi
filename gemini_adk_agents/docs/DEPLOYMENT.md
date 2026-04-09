# GCP Deployment Guide

Deploy Gemini ADK Agents to Google Cloud Platform and access from any machine.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Deploy (5 minutes)](#quick-deploy)
3. [Manual Deployment](#manual-deployment)
4. [CI/CD Setup](#cicd-setup)
5. [Accessing the API](#accessing-the-api)
6. [Security Best Practices](#security-best-practices)
7. [Monitoring & Logging](#monitoring--logging)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### 1. Google Cloud Account
- Create a GCP account at [console.cloud.google.com](https://console.cloud.google.com)
- Create a new project or select an existing one
- Enable billing for the project

### 2. Install Google Cloud SDK
```bash
# Windows (PowerShell as Admin)
(New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
& $env:Temp\GoogleCloudSDKInstaller.exe

# macOS
brew install google-cloud-sdk

# Linux
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

### 3. Authenticate
```bash
# Login to GCP
gcloud auth login

# Set application default credentials (for local testing)
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID
```

### 4. Enable Required APIs
```bash
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    secretmanager.googleapis.com \
    aiplatform.googleapis.com
```

---

## Quick Deploy

### Option A: Using Deployment Script (Recommended)

**Windows:**
```powershell
cd gemini_adk_agents/deploy
.\deploy.ps1 -ProjectId "genai-treding"
```

**Linux/macOS:**
```bash
cd gemini_adk_agents/deploy
chmod +x deploy.sh
./deploy.sh genai-treding
```

### Option B: One-Liner Deploy
```bash
# From gemini_adk_agents directory
gcloud run deploy gemini-adk-agents \
    --source . \
    --region us-central1 \
    --allow-unauthenticated
```

After deployment, you'll get a URL like:
```
https://gemini-adk-agents-abc123-uc.a.run.app
```

---

## Manual Deployment

### Step 1: Build Docker Image

```bash
# Navigate to project directory
cd gemini_adk_agents

# Build locally (optional, for testing)
docker build -t gemini-adk-agents .

# Test locally
docker run -p 8080:8080 -e GOOGLE_API_KEY=your-key gemini-adk-agents

# Build with Cloud Build
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/gemini-adk-agents
```

### Step 2: Deploy to Cloud Run

```bash
gcloud run deploy gemini-adk-agents \
    --image gcr.io/YOUR_PROJECT_ID/gemini-adk-agents \
    --region us-central1 \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --set-env-vars "GCP_PROJECT_ID=YOUR_PROJECT_ID,ADK_MODEL=gemini-2.0-flash"
```

### Step 3: Configure Secrets (Recommended)

Store API keys securely in Secret Manager:

```bash
# Create secret
echo -n "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-

# Grant Cloud Run access
gcloud secrets add-iam-policy-binding gemini-api-key \
    --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

# Deploy with secret
gcloud run deploy gemini-adk-agents \
    --image gcr.io/YOUR_PROJECT_ID/gemini-adk-agents \
    --region us-central1 \
    --set-secrets "GOOGLE_API_KEY=gemini-api-key:latest"
```

---

## CI/CD Setup

### GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [main]
    paths:
      - 'gemini_adk_agents/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      
      - uses: google-github-actions/setup-gcloud@v2
      
      - name: Deploy to Cloud Run
        run: |
          cd gemini_adk_agents
          gcloud run deploy gemini-adk-agents \
            --source . \
            --region us-central1 \
            --allow-unauthenticated
```

### Cloud Build Trigger

```bash
# Connect your repository
gcloud source repos create gemini-adk-agents
gcloud builds triggers create github \
    --repo-name=your-repo \
    --branch-pattern="^main$" \
    --build-config=gemini_adk_agents/cloudbuild.yaml
```

---

## Accessing the API

### Get Service URL

```bash
gcloud run services describe gemini-adk-agents --region us-central1 --format 'value(status.url)'
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check |
| `/docs` | GET | API documentation (Swagger UI) |
| `/research` | POST | Run research agent |
| `/analyze` | POST | Run analysis agent |
| `/report` | POST | Generate report |
| `/chat` | POST | Chat with Gemini |

### Example API Calls

**Health Check:**
```bash
curl https://YOUR-SERVICE-URL/health
```

**Research:**
```bash
curl -X POST https://YOUR-SERVICE-URL/research \
    -H "Content-Type: application/json" \
    -d '{"query": "Indian drone companies for defense", "num_results": 10}'
```

**Chat with Gemini:**
```bash
curl -X POST https://YOUR-SERVICE-URL/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "Explain quantum computing in simple terms", "model": "gemini-2.0-flash"}'
```

**Python Client:**
```python
import requests

BASE_URL = "https://your-service-url.run.app"

# Research
response = requests.post(
    f"{BASE_URL}/research",
    json={"query": "AI trends 2024", "num_results": 5}
)
print(response.json())

# Chat
response = requests.post(
    f"{BASE_URL}/chat",
    json={"message": "Hello, how are you?"}
)
print(response.json())
```

---

## Security Best Practices

### 1. Authentication (Recommended for Production)

Remove `--allow-unauthenticated` and use IAM:

```bash
# Deploy with authentication required
gcloud run deploy gemini-adk-agents \
    --image gcr.io/YOUR_PROJECT_ID/gemini-adk-agents \
    --region us-central1 \
    --no-allow-unauthenticated

# Call with identity token
TOKEN=$(gcloud auth print-identity-token)
curl -H "Authorization: Bearer $TOKEN" https://YOUR-SERVICE-URL/health
```

### 2. API Key Authentication

Add API key validation in `api_server.py`:

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

@app.post("/research")
async def run_research(request: ResearchRequest, api_key: str = Security(verify_api_key)):
    ...
```

### 3. VPC Connector (Private Access)

```bash
# Create VPC connector
gcloud compute networks vpc-access connectors create my-connector \
    --region us-central1 \
    --range 10.8.0.0/28

# Deploy with VPC
gcloud run deploy gemini-adk-agents \
    --vpc-connector my-connector \
    --vpc-egress private-ranges-only
```

---

## Monitoring & Logging

### View Logs

```bash
# Stream logs
gcloud run services logs read gemini-adk-agents --region us-central1 --tail 50

# View in Cloud Console
# https://console.cloud.google.com/run/detail/us-central1/gemini-adk-agents/logs
```

### Set Up Alerts

```bash
# Create alert for error rate > 1%
gcloud alpha monitoring policies create \
    --display-name="Cloud Run Error Rate" \
    --condition-display-name="Error rate > 1%" \
    --condition-filter='resource.type="cloud_run_revision" AND metric.type="run.googleapis.com/request_count"'
```

---

## Troubleshooting

### Common Issues

**1. "Permission denied" errors**
```bash
# Ensure service account has required roles
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/aiplatform.user"
```

**2. Cold start timeout**
```bash
# Increase min instances
gcloud run services update gemini-adk-agents \
    --min-instances 1 \
    --region us-central1
```

**3. Out of memory**
```bash
# Increase memory
gcloud run services update gemini-adk-agents \
    --memory 4Gi \
    --region us-central1
```

**4. API key not working**
```bash
# Verify secret
gcloud secrets versions access latest --secret=gemini-api-key

# Check service account permissions
gcloud secrets get-iam-policy gemini-api-key
```

---

## Cost Optimization

### Pricing Summary
- Cloud Run: $0.00002400/vCPU-second, $0.00000250/GiB-second
- Free tier: 2 million requests/month, 360,000 GiB-seconds

### Tips
1. Set `--min-instances 0` for dev environments
2. Use `--cpu-throttling` for non-latency-critical workloads
3. Set appropriate `--timeout` to avoid long-running charges
4. Use Cloud Scheduler for periodic tasks instead of always-on

---

## Next Steps

1. **Custom Domain**: Add your own domain via Cloud Run domain mapping
2. **Load Balancer**: Add Cloud Load Balancing for global distribution
3. **CDN**: Use Cloud CDN for caching responses
4. **Vertex AI**: Switch to Vertex AI for enterprise features
