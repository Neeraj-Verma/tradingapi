# PowerShell deployment script for Windows
# Usage: .\deploy.ps1 -ProjectId "your-project" -Region "us-central1"

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,
    
    [Parameter(Mandatory=$false)]
    [string]$Region = "us-central1",
    
    [Parameter(Mandatory=$false)]
    [string]$ServiceName = "gemini-adk-agents"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Deploying Gemini ADK Agents to Cloud Run" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Project: $ProjectId"
Write-Host "Region: $Region"
Write-Host "Service: $ServiceName"
Write-Host ""

$ImageName = "gcr.io/$ProjectId/$ServiceName"

# Navigate to project directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$ScriptDir\.."

# ==================== LOAD .ENV FILE ====================
Write-Host "Loading environment variables from .env..." -ForegroundColor Yellow
$EnvFile = ".\.env"
$EnvVars = @{}

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        # Skip comments and empty lines
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Length -eq 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim()
                $EnvVars[$key] = $value
            }
        }
    }
    Write-Host "  Loaded $($EnvVars.Count) variables from .env" -ForegroundColor Green
} else {
    Write-Host "  Warning: .env file not found, using defaults" -ForegroundColor Yellow
}

# Build env vars string for Cloud Run
$CloudEnvVars = @(
    "GCP_PROJECT_ID=$ProjectId",
    "GCP_LOCATION=$Region"
)

# Add keys from .env if they exist
$KeysToInclude = @("GOOGLE_API_KEY", "ADK_MODEL", "SERPER_API_KEY", "TAVILY_API_KEY", "API_SECRET_KEY", "ADK_TEMPERATURE", "ADK_MAX_OUTPUT_TOKENS", "LOG_LEVEL")
foreach ($key in $KeysToInclude) {
    if ($EnvVars.ContainsKey($key) -and $EnvVars[$key]) {
        $CloudEnvVars += "$key=$($EnvVars[$key])"
    }
}
$EnvVarsString = $CloudEnvVars -join ","

Write-Host "  Environment variables to deploy:" -ForegroundColor Cyan
foreach ($var in $CloudEnvVars) {
    $name = ($var -split "=")[0]
    Write-Host "    - $name" -ForegroundColor Gray
}
Write-Host ""

# Set project
Write-Host "Setting GCP project..." -ForegroundColor Yellow
gcloud config set project $ProjectId

# Enable required APIs
Write-Host "Enabling required APIs..." -ForegroundColor Yellow
gcloud services enable `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    containerregistry.googleapis.com `
    secretmanager.googleapis.com `
    aiplatform.googleapis.com

# Build and push image
Write-Host "Building Docker image..." -ForegroundColor Yellow
gcloud builds submit --tag $ImageName .

# Deploy to Cloud Run
Write-Host "Deploying to Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --image $ImageName `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --memory 2Gi `
    --cpu 2 `
    --timeout 300 `
    --concurrency 80 `
    --set-env-vars $EnvVarsString

# Get service URL
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

$ServiceUrl = gcloud run services describe $ServiceName --region $Region --format 'value(status.url)'
Write-Host "Service URL: $ServiceUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "Test with:"
Write-Host "  curl $ServiceUrl/health"
Write-Host ""
Write-Host "API Docs:"
Write-Host "  $ServiceUrl/docs"
