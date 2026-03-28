param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [Parameter(Mandatory=$false)][string]$Region = "asia-northeast3",
  [Parameter(Mandatory=$false)][string]$ServiceName = "giridaga-marketer",
  [Parameter(Mandatory=$false)][string]$SecretsName = "streamlit-secrets",
  [Parameter(Mandatory=$false)][string]$CloudSecretsFile = ".streamlit/secrets.cloud.toml"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $CloudSecretsFile)) {
  throw "Cloud secrets file not found: $CloudSecretsFile"
}

Write-Host "[1/2] Refresh secret version from $CloudSecretsFile"
.\scripts\create_secret.ps1 -ProjectId $ProjectId -SecretsName $SecretsName -SecretsFile $CloudSecretsFile

Write-Host "[2/2] Redeploy Cloud Run service"
.\scripts\deploy_cloud_run.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName -SecretsName $SecretsName

Write-Host "Redeploy completed."

