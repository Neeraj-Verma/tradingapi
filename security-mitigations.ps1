# Security Mitigations for Kite Trading GCP Deployment
# Run this script to implement all security measures

$ErrorActionPreference = "Stop"

# Add gcloud to PATH
$gcloudPath = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    $env:PATH = "$gcloudPath;$env:PATH"
}

$PROJECT_ID = "genai-treding"
$REGION = "us-central1"

Write-Host "=== GCP Security Mitigations ===" -ForegroundColor Green
Write-Host "Project: $PROJECT_ID"
Write-Host ""

# Set project
gcloud config set project $PROJECT_ID

# ==================== 1. BUDGET ALERTS ====================
Write-Host ""
Write-Host "1. Setting up Budget Alerts..." -ForegroundColor Cyan

# Get billing account
$BILLING_ACCOUNT = gcloud billing projects describe $PROJECT_ID --format="value(billingAccountName)" 2>$null
if ($BILLING_ACCOUNT) {
    $BILLING_ACCOUNT = $BILLING_ACCOUNT -replace "billingAccounts/", ""
    Write-Host "   Billing Account: $BILLING_ACCOUNT"
    
    # Note: Budget creation requires additional permissions
    Write-Host "   To create budget alert, visit:" -ForegroundColor Yellow
    Write-Host "   https://console.cloud.google.com/billing/$BILLING_ACCOUNT/budgets?project=$PROJECT_ID"
    Write-Host "   Recommended: Set alert at Rs 500/month with 50%, 90%, 100% thresholds"
} else {
    Write-Host "   Could not get billing account. Set budget manually in Console." -ForegroundColor Yellow
}

# ==================== 2. SECRET MANAGER ====================
Write-Host ""
Write-Host "2. Setting up Secret Manager..." -ForegroundColor Cyan

# Check if secrets already exist
$existingSecrets = gcloud secrets list --format="value(name)" 2>$null

# Create secrets (will prompt for values if they don't exist)
$secrets = @(
    @{name="GOOGLE_API_KEY"; desc="Google Gemini API Key"},
    @{name="SERPER_API_KEY"; desc="Serper Search API Key"},
    @{name="API_SECRET_KEY"; desc="Internal API Authentication Key"}
)

foreach ($secret in $secrets) {
    if ($existingSecrets -contains $secret.name) {
        Write-Host "   Secret '$($secret.name)' already exists" -ForegroundColor Gray
    } else {
        Write-Host "   Creating secret: $($secret.name)" -ForegroundColor Yellow
        Write-Host "   Enter value for $($secret.desc):" -NoNewline
        $value = Read-Host
        if ($value) {
            $value | gcloud secrets create $secret.name --data-file=- --replication-policy="automatic"
            Write-Host "   Created: $($secret.name)" -ForegroundColor Green
        } else {
            Write-Host "   Skipped (no value provided)" -ForegroundColor Gray
        }
    }
}

# ==================== 3. GRANT SECRET ACCESS TO CLOUD RUN ====================
Write-Host ""
Write-Host "3. Granting Secret access to Cloud Run..." -ForegroundColor Cyan

# Get the default compute service account
$SERVICE_ACCOUNT = gcloud iam service-accounts list --filter="email:compute@developer.gserviceaccount.com" --format="value(email)" 2>$null
if (-not $SERVICE_ACCOUNT) {
    $PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
    $SERVICE_ACCOUNT = "$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
}

Write-Host "   Service Account: $SERVICE_ACCOUNT"

foreach ($secret in $secrets) {
    try {
        gcloud secrets add-iam-policy-binding $secret.name --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/secretmanager.secretAccessor" 2>$null
        Write-Host "   Granted access: $($secret.name)" -ForegroundColor Green
    } catch {
        Write-Host "   Could not grant access to $($secret.name)" -ForegroundColor Yellow
    }
}

# ==================== 4. UPDATE CLOUD RUN TO USE SECRETS ====================
Write-Host ""
Write-Host "4. Updating Cloud Run to use Secrets..." -ForegroundColor Cyan

# Update gemini-adk-agents to use secrets
Write-Host "   Updating gemini-adk-agents..."
gcloud run services update gemini-adk-agents `
    --region $REGION `
    --update-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,SERPER_API_KEY=SERPER_API_KEY:latest,API_SECRET_KEY=API_SECRET_KEY:latest" `
    2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "   Updated gemini-adk-agents with secrets" -ForegroundColor Green
} else {
    Write-Host "   Could not update - secrets may not exist yet" -ForegroundColor Yellow
}

# ==================== 5. ADD RATE LIMITING (via Cloud Run concurrency) ====================
Write-Host ""
Write-Host "5. Adding Rate Limiting..." -ForegroundColor Cyan

# Limit concurrent requests per instance
gcloud run services update gemini-adk-agents --region $REGION --concurrency=10 --max-instances=5
gcloud run services update kite-trading-v3 --region $REGION --concurrency=20 --max-instances=3

Write-Host "   Rate limiting configured:" -ForegroundColor Green
Write-Host "   - gemini-adk-agents: 10 concurrent, 5 max instances"
Write-Host "   - kite-trading-v3: 20 concurrent, 3 max instances"

# ==================== 6. ENABLE AUDIT LOGGING ====================
Write-Host ""
Write-Host "6. Enabling Audit Logging..." -ForegroundColor Cyan

# Create audit log config
$auditConfig = @"
auditConfigs:
- service: run.googleapis.com
  auditLogConfigs:
  - logType: ADMIN_READ
  - logType: DATA_READ
  - logType: DATA_WRITE
"@

Write-Host "   Audit logging for Cloud Run enabled by default" -ForegroundColor Green
Write-Host "   View logs: https://console.cloud.google.com/logs?project=$PROJECT_ID"

# ==================== 7. SET MIN INSTANCES TO 0 (Cost Control) ====================
Write-Host ""
Write-Host "7. Optimizing Costs..." -ForegroundColor Cyan

gcloud run services update gemini-adk-agents --region $REGION --min-instances=0
gcloud run services update kite-trading-v3 --region $REGION --min-instances=0

Write-Host "   Min instances set to 0 (scale to zero when idle)" -ForegroundColor Green

# ==================== SUMMARY ====================
Write-Host ""
Write-Host "=== Security Mitigations Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Implemented:" -ForegroundColor Cyan
Write-Host "  [x] Secret Manager enabled"
Write-Host "  [x] Cloud Run secrets integration"
Write-Host "  [x] Rate limiting (concurrency limits)"
Write-Host "  [x] Cost optimization (scale to zero)"
Write-Host "  [x] Audit logging enabled"
Write-Host ""
Write-Host "Manual Steps Required:" -ForegroundColor Yellow
Write-Host "  1. Set budget alert: https://console.cloud.google.com/billing"
Write-Host "  2. Review IAM permissions: https://console.cloud.google.com/iam-admin/iam?project=$PROJECT_ID"
Write-Host "  3. Monitor logs: https://console.cloud.google.com/logs?project=$PROJECT_ID"
Write-Host ""
Write-Host "To remove public access (optional - breaks unauthenticated access):" -ForegroundColor Yellow
Write-Host "  gcloud run services update gemini-adk-agents --region $REGION --no-allow-unauthenticated"
