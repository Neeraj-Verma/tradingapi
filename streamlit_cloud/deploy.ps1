# Deploy Streamlit Trading App to Cloud Run
# Usage: .\deploy.ps1

$ErrorActionPreference = "Stop"

# Add gcloud to PATH if not found
$gcloudPath = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    if (Test-Path "$gcloudPath\gcloud.cmd") {
        $env:PATH = "$gcloudPath;$env:PATH"
        Write-Host "Added gcloud to PATH: $gcloudPath" -ForegroundColor Yellow
    } else {
        Write-Host "ERROR: gcloud not found. Install Google Cloud SDK first." -ForegroundColor Red
        exit 1
    }
}

# Configuration
$PROJECT_ID = "genai-treding"
$REGION = "us-central1"
$SERVICE_NAME = "kite-trading-v3"

# Load environment variables from .env
$envFile = ".env"
if (Test-Path $envFile) {
    Write-Host "Loading environment variables from $envFile..." -ForegroundColor Cyan
    $envVars = @{}
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim().Trim('"').Trim("'")
            if ($key -and $value) {
                $envVars[$key] = $value
            }
        }
    }
} else {
    Write-Host "Warning: $envFile not found. Using defaults." -ForegroundColor Yellow
    $envVars = @{}
}

# Add required environment variables
$envVars["AUTH_ENABLED"] = if ($envVars["AUTH_ENABLED"]) { $envVars["AUTH_ENABLED"] } else { "true" }
$envVars["AUTH_USERS"] = if ($envVars["AUTH_USERS"]) { $envVars["AUTH_USERS"] } else { "admin:admin123" }
$envVars["SESSION_TIMEOUT_HOURS"] = if ($envVars["SESSION_TIMEOUT_HOURS"]) { $envVars["SESSION_TIMEOUT_HOURS"] } else { "8" }

# Create env-vars YAML file for Cloud Run (avoids escaping issues)
$envVarsYaml = "env_vars.yaml"
$yamlContent = @()
foreach ($kv in $envVars.GetEnumerator()) {
    # Quote values to handle special characters
    $yamlContent += "$($kv.Key): `"$($kv.Value)`""
}
$yamlContent | Out-File -FilePath $envVarsYaml -Encoding utf8
Write-Host "Created $envVarsYaml with $($envVars.Count) variables" -ForegroundColor Cyan

Write-Host ""
Write-Host "=== Deploying Streamlit App to Cloud Run ===" -ForegroundColor Green
Write-Host "Project: $PROJECT_ID"
Write-Host "Region: $REGION"
Write-Host "Service: $SERVICE_NAME"
Write-Host ""

# Set project
Write-Host "Setting GCP project..." -ForegroundColor Cyan
gcloud config set project $PROJECT_ID

# Deploy to Cloud Run
Write-Host ""
Write-Host "Deploying to Cloud Run..." -ForegroundColor Cyan
Write-Host "This will build the Docker image and deploy. This may take 5-10 minutes..."
Write-Host ""

gcloud run deploy $SERVICE_NAME `
    --source . `
    --region $REGION `
    --platform managed `
    --allow-unauthenticated `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 3 `
    --timeout 300 `
    --env-vars-file $envVarsYaml

# Cleanup temp file
if (Test-Path $envVarsYaml) { Remove-Item $envVarsYaml -Force }

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== Deployment Successful! ===" -ForegroundColor Green
    
    # Get the service URL
    $SERVICE_URL = gcloud run services describe $SERVICE_NAME --region $REGION --format "value(status.url)"
    Write-Host ""
    Write-Host "Streamlit App URL: $SERVICE_URL" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Default Login Credentials:" -ForegroundColor Yellow
    Write-Host "  Username: admin"
    Write-Host "  Password: admin123"
    Write-Host ""
    Write-Host "To change credentials, update AUTH_USERS in .env and redeploy"
    Write-Host "Format: user1:pass1,user2:pass2"
} else {
    Write-Host ""
    Write-Host "Deployment failed!" -ForegroundColor Red
    exit 1
}
