param(
  [Parameter(Mandatory=$false)][int]$Port = 8080,
  [Parameter(Mandatory=$false)][string]$ImageName = "giridaga-marketer",
  [Parameter(Mandatory=$false)][string]$ContainerName = "giridaga_local_test",
  [Parameter(Mandatory=$false)][string]$SecretsFile = ".streamlit/secrets.local.toml",
  [Parameter(Mandatory=$false)][switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker CLI 가 없습니다. Docker Desktop 설치 후 다시 시도하세요.`n`nDocker 없이 실행: 프로젝트 루트에서 .\scripts\run_streamlit.ps1"
}

# 데몬 미기동 시 dockerDesktopLinuxEngine 파이프 오류가 남
$dockerOk = $false
try {
  docker info 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
} catch { }
if (-not $dockerOk) {
  throw @"
Docker 데몬에 연결할 수 없습니다. (Docker Desktop 이 꺼져 있거나 아직 완전히 켜지지 않았을 수 있습니다.)

[해결]
  1) Docker Desktop 을 실행하고, 트레이 아이콘이 준비될 때까지 기다린 뒤 다시: .\scripts\run_local.ps1

[Docker 없이 로컬 실행 — 배포 이미지와는 다름]
  프로젝트 루트에서:
    .\scripts\run_streamlit.ps1
  또는:
    pip install -r requirements.txt
    streamlit run app.py
"@
}

function Resolve-SecretsPath {
  param([string]$RelPath)
  if ([System.IO.Path]::IsPathRooted($RelPath)) {
    return $RelPath
  }
  return (Join-Path $Root ($RelPath -replace '^[\\/]', ''))
}

$secretsPath = Resolve-SecretsPath $SecretsFile
$templatePath = Join-Path $Root ".streamlit/secrets.template.toml"
$fallbackToml = Join-Path $Root ".streamlit/secrets.toml"

if (!(Test-Path $secretsPath)) {
  if (Test-Path $fallbackToml) {
    Write-Host "Using .streamlit/secrets.toml (secrets.local.toml 없음)" -ForegroundColor Yellow
    $secretsPath = $fallbackToml
  }
  elseif (Test-Path $templatePath) {
    $localDefault = Join-Path $Root ".streamlit/secrets.local.toml"
    Copy-Item -Path $templatePath -Destination $localDefault -Force
    Write-Warning ".streamlit/secrets.local.toml 이 없어 secrets.template.toml 로 생성했습니다. API 키·시트 URL 등을 채운 뒤 다시 실행하세요."
    $secretsPath = $localDefault
  }
  else {
    throw "Secrets 파일을 찾을 수 없습니다. 다음 중 하나를 만드세요: $SecretsFile, .streamlit/secrets.toml, 또는 .streamlit/secrets.template.toml"
  }
}

$secretsAbs = (Resolve-Path $secretsPath).Path

Write-Host "Image:     $ImageName"
Write-Host "Container: $ContainerName"
Write-Host "Port:      $Port"
Write-Host "Secrets:   $secretsAbs"

if (-not $SkipBuild) {
  Write-Host "[1/3] Building local image..."
  & docker build -t $ImageName $Root
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
# Streamlit은 작업 디렉터리(/app)의 .streamlit/secrets.toml 을 우선합니다.
# /root 만 마운트하면 프로젝트 쪽 파일이 있을 때 시크릿이 무시되어 클라우드와 다른 DB/시트에 붙을 수 있습니다.
& docker run --rm `
  --name $ContainerName `
  -p "${Port}:8080" `
  -e "PORT=8080" `
  -v "${secretsAbs}:/app/.streamlit/secrets.toml:ro" `
  -v "${secretsAbs}:/root/.streamlit/secrets.toml:ro" `
  $ImageName

