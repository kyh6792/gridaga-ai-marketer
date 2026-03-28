param(
  [Parameter(Mandatory=$false)][int]$Port = 8080,
  [Parameter(Mandatory=$false)][string]$ImageName = "giridaga-marketer",
  [Parameter(Mandatory=$false)][string]$ContainerName = "giridaga_local_test",
  [Parameter(Mandatory=$false)][string]$SecretsFile = ".streamlit/secrets.local.toml",
  [Parameter(Mandatory=$false)][switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker CLI not found. Please install/start Docker Desktop first."
}

if (!(Test-Path $SecretsFile)) {
  throw "Local secrets file not found: $SecretsFile"
}

$secretsAbs = (Resolve-Path $SecretsFile).Path

Write-Host "Image:     $ImageName"
Write-Host "Container: $ContainerName"
Write-Host "Port:      $Port"
Write-Host "Secrets:   $secretsAbs"

if (-not $SkipBuild) {
  Write-Host "[1/3] Building local image..."
  & docker build -t $ImageName .
  if ($LASTEXITCODE -ne 0) { throw "Docker build failed." }
} else {
  Write-Host "[1/3] Skip build (-SkipBuild)."
}

Write-Host "[2/3] Removing existing container if present..."
$containerExists = (& docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $ContainerName })
if ($containerExists) {
  & docker rm -f $ContainerName | Out-Null
}

Write-Host "[3/3] Starting container..."
& docker run --rm `
  --name $ContainerName `
  -p "${Port}:8080" `
  -e "PORT=8080" `
  -v "${secretsAbs}:/root/.streamlit/secrets.toml:ro" `
  $ImageName

