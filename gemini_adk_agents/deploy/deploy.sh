#!/bin/bash
# Quick deployment script for Cloud Run (Mac/Linux)
# Usage: ./deploy.sh PROJECT_ID [REGION]

set -e

PROJECT_ID="${1:-}"
REGION="${2:-us-central1}"
SERVICE_NAME="gemini-adk-agents"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

if [ -z "$PROJECT_ID" ]; then
    echo "Usage: ./deploy.sh PROJECT_ID [REGION]"
    echo "Example: ./deploy.sh my-gcp-project us-central1"
    exit 1
fi

echo "=========================================="
echo "Deploying Gemini ADK Agents to Cloud Run"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Navigate to project directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# ==================== LOAD .ENV FILE ====================
echo "Loading environment variables from .env..."
ENV_FILE="./.env"
declare -A ENV_VARS

if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip comments and empty lines
        line=$(echo "$line" | xargs)  # trim whitespace
        if [[ -n "$line" && ! "$line" =~ ^# ]]; then
            key=$(echo "$line" | cut -d'=' -f1 | xargs)
            value=$(echo "$line" | cut -d'=' -f2- | xargs)
            if [[ -n "$key" && -n "$value" ]]; then
                ENV_VARS[$key]="$value"
            fi
        fi
    done < "$ENV_FILE"
    echo "  Loaded ${#ENV_VARS[@]} variables from .env"
else
    echo "  Warning: .env file not found, using defaults"
fi

# Build env vars string for Cloud Run
CLOUD_ENV_VARS="GCP_PROJECT_ID=$PROJECT_ID,GCP_LOCATION=$REGION"

# Keys to include from .env
KEYS_TO_INCLUDE=("GOOGLE_API_KEY" "ADK_MODEL" "SERPER_API_KEY" "TAVILY_API_KEY" "API_SECRET_KEY" "ADK_TEMPERATURE" "ADK_MAX_OUTPUT_TOKENS" "LOG_LEVEL")

echo "  Environment variables to deploy:"
echo "    - GCP_PROJECT_ID"
echo "    - GCP_LOCATION"

for key in "${KEYS_TO_INCLUDE[@]}"; do
    if [[ -n "${ENV_VARS[$key]}" ]]; then
        CLOUD_ENV_VARS="${CLOUD_ENV_VARS},${key}=${ENV_VARS[$key]}"
        echo "    - $key"
    fi
done
echo ""

# Set project
echo "Setting GCP project..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    secretmanager.googleapis.com \
    aiplatform.googleapis.com

# Build and push image
echo "Building Docker image..."
gcloud builds submit --tag $IMAGE_NAME .

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --concurrency 80 \
    --set-env-vars "$CLOUD_ENV_VARS"

# Get service URL
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')
echo "Service URL: $SERVICE_URL"
echo ""
echo "Test with:"
echo "  curl $SERVICE_URL/health"
echo ""
echo "API Docs:"
echo "  $SERVICE_URL/docs"
