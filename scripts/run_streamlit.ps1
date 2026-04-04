# Docker 없이 로컬에서 Streamlit만 실행 (개발용)
# 사용: 프로젝트 아무 경로에서든 .\scripts\run_streamlit.ps1

param(
  [Parameter(Mandatory = $false)][int]$Port = 8501
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command streamlit -ErrorAction SilentlyContinue)) {
  throw "streamlit 명령을 찾을 수 없습니다. 가상환경 활성화 후 `pip install -r requirements.txt` 를 실행하세요."
}

$secretsMain = Join-Path $Root ".streamlit/secrets.toml"
$secretsLocal = Join-Path $Root ".streamlit/secrets.local.toml"
$templatePath = Join-Path $Root ".streamlit/secrets.template.toml"

if (-not (Test-Path $secretsMain)) {
  if (Test-Path $secretsLocal) {
    Copy-Item -Path $secretsLocal -Destination $secretsMain -Force
    Write-Host "Streamlit은 .streamlit/secrets.toml 만 읽습니다. secrets.local.toml 을 secrets.toml 로 복사했습니다." -ForegroundColor Cyan
  }
  elseif (Test-Path $templatePath) {
    Copy-Item -Path $templatePath -Destination $secretsMain -Force
    Write-Warning ".streamlit/secrets.toml 이 없어 템플릿으로 생성했습니다. 키·URL 등을 채운 뒤 다시 실행하세요."
  }
  else {
    throw ".streamlit/secrets.toml 이 없고, secrets.local.toml / secrets.template.toml 도 없습니다."
  }
}

Write-Host "Root: $Root" -ForegroundColor DarkGray
Write-Host "Open: http://localhost:$Port" -ForegroundColor Green
& streamlit run app.py --server.port $Port
