# ADK Deep Search Agent (Vertex AI)

This repo includes an ADK-based deep search agent in `deep_search_agent/`.

## 1) Install dependencies

From the repo root (Windows PowerShell):

```powershell
# If you're using the existing venv
.\.venv\Scripts\Activate.ps1
pip install -U google-adk google-genai
```

## 2) Configure Vertex AI auth

ADK uses **Application Default Credentials (ADC)** for Vertex AI.

If `gcloud` is not found, install the Google Cloud CLI first (Windows):

```powershell
# Option A: Winget (recommended)
winget install -e --id Google.CloudSDK

# Close & reopen PowerShell after install, then verify:
where.exe gcloud
gcloud --version
```

If you don't have winget, install via the official installer and make sure it
adds `gcloud` to PATH:

- https://cloud.google.com/sdk/docs/install

### If Cloud SDK is installed but `gcloud` is still not recognized

On some Windows setups the Cloud SDK is installed but its `bin` folder isn’t on
your PATH.

**One-time (current terminal only):**

```powershell
$sdkBin = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin"
$env:PATH = "$sdkBin;$env:PATH"
gcloud --version
```

**Permanent (User PATH):**

```powershell
$sdkBin = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$sdkBin*") {
	[Environment]::SetEnvironmentVariable('Path', "$sdkBin;$userPath", 'User')
	"Updated User PATH. Close & reopen PowerShell."
} else {
	"SDK bin already present in User PATH."
}
```

**Direct invocation (no PATH changes):**

```powershell
& "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" --version
```

```powershell
gcloud auth application-default login
```

### Quota project warning (recommended fix)

If you see:

> Cannot find a quota project to add to ADC...

Set the quota/billing project for ADC (use the same project you set in
`GOOGLE_CLOUD_PROJECT`):

```powershell
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

Quick verification:

```powershell
gcloud config get-value project
gcloud auth application-default list
gcloud auth application-default print-access-token | Select-Object -First 1
```

Notes:
- You may need permission `serviceusage.services.use` on the quota project.
- If you later get `API not enabled` errors, enable Vertex AI in that project.

### Alternative (no gcloud): Service account key

If you cannot install `gcloud`, you can still use ADC by pointing
`GOOGLE_APPLICATION_CREDENTIALS` at a service account JSON key file.

```powershell
# Path to the downloaded service-account JSON key
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\service-account.json"

# Optional sanity check
python -c "import google.auth; c,p=google.auth.default(); print('ADC project:', p)"
```

Notes:
- Ensure the service account has access to Vertex AI in the target project.
- Keep the JSON key file private (don’t commit it to git).

## 3) Configure environment

Copy the template:

- `deep_search_agent/.env.example` → `deep_search_agent/.env`

Set:
- `GOOGLE_GENAI_USE_VERTEXAI=TRUE`
- `GOOGLE_CLOUD_PROJECT=...`
- `GOOGLE_CLOUD_LOCATION=...` (example: `us-central1`)

Your `deep_search_agent/.env` should look like this (note: **no** `$env:` in a `.env` file):

```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=product-claims-poc
GOOGLE_CLOUD_LOCATION=us-central1
```

If you prefer setting them in the terminal instead of a file, use PowerShell:

```powershell
$env:GOOGLE_GENAI_USE_VERTEXAI = "TRUE"
$env:GOOGLE_CLOUD_PROJECT = "product-claims-poc"
$env:GOOGLE_CLOUD_LOCATION = "us-central1"
```

## 4) Run

From the repo root:

```powershell
adk run deep_search_agent
```

Or launch the dev UI:

```powershell
adk web --no-reload
```

Then open the printed URL and select `deep_search_agent`.

## Example prompts

- `Deep research RELIANCE (NSE): recent news, results, risks, catalysts. Provide sources.`
- `Compare TCS vs INFY with citations; focus on last 90 days.`
- `Create order_book CSV for Top5 private banks with Allocation=400000 each. Output strictly as CSV with the exact header: Symbol,Quantity,Price,Transaction,Variety,Product,Order_Type,Rank,Allocation,TargetValue,Rationale`.

## Source allowlist

`deep_search_agent` is configured to use and cite only the curated sources in `src/research_sources.py`. It builds Google queries with `site:` filters to stay within that allowlist.

## Tips file generator

This repo also includes `tips_research_agent/` which generates `data/tips_research_data.csv` from `data/research_data.csv` using live Kite LTP prices and `DAILY_BUDGET`.

Run:

```powershell
adk run tips_research_agent
```

Prompt example:

- `Generate tips_research_data.csv for Top15 using DAILY_BUDGET.`

Artifacts generated (in addition to the CSV):
- `data/tips_research_generation.md` (audit/trace: inputs, parameters, preview)
- `data/tips_research_report.md` (grounded research report using allowlisted sources)
