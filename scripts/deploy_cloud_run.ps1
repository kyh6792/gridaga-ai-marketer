param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [Parameter(Mandatory=$false)][string]$Region = "asia-northeast3",
  [Parameter(Mandatory=$false)][string]$ServiceName = "giridaga-marketer",
  [Parameter(Mandatory=$false)][string]$SecretsName = "streamlit-secrets"
)

$ErrorActionPreference = "Stop"

$gcloud = Get-Command gcloud -ErrorAction SilentlyContinue
if (-not $gcloud) {
  $candidate = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
  if (Test-Path $candidate) {
    $gcloudCmd = $candidate
  } else {
    throw "gcloud CLI not found. Install Cloud SDK or add gcloud to PATH."
  }
} else {
  $gcloudCmd = $gcloud.Source
}

Write-Host "Project: $ProjectId"
Write-Host "Region:  $Region"
Write-Host "Service: $ServiceName"
Write-Host "Secret:  $SecretsName (mounted to /root/.streamlit/secrets.toml)"

& $gcloudCmd config set project $ProjectId
& $gcloudCmd services enable run.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

Write-Host "Deploying to Cloud Run..."
& $gcloudCmd run deploy $ServiceName `
  --quiet `
  --source . `
  --region $Region `
  --allow-unauthenticated `
  --memory 1024Mi `
  --cpu 1 `
  --min-instances 0 `
  --set-env-vars "STREAMLIT_SERVER_HEADLESS=true,PERF_DEBUG=1" `
  --update-secrets "/root/.streamlit/secrets.toml=${SecretsName}:latest"

Write-Host "Done."

