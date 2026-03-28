param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [Parameter(Mandatory=$false)][string]$SecretsName = "streamlit-secrets",
  [Parameter(Mandatory=$false)][string]$SecretsFile = ".streamlit/secrets.toml"
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

& $gcloudCmd config set project $ProjectId
& $gcloudCmd services enable secretmanager.googleapis.com

if (!(Test-Path $SecretsFile)) {
  throw "Secrets file not found: $SecretsFile"
}

Write-Host "Creating/updating secret: $SecretsName from $SecretsFile"

& $gcloudCmd secrets describe $SecretsName | Out-Null
if ($LASTEXITCODE -eq 0) {
  & $gcloudCmd secrets versions add $SecretsName --data-file=$SecretsFile
} else {
  & $gcloudCmd secrets create $SecretsName --data-file=$SecretsFile
}

Write-Host "Done."

