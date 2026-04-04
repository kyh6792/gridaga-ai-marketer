# Cloud Run 배포 (Google Cloud SDK gcloud 필요)
# 사용 전: gcloud auth login, gcloud config set project YOUR_PROJECT_ID
# Secret Manager에 streamlit-secrets 버전이 있어야 합니다. (README_CLOUD_RUN.md 참고)
#
# 속도(특히 F5·첫 접속):
#   - 기본으로 --cpu-boost 사용(시작 시 CPU 가속, 콜드 스타트 완화).
#   - 트래픽이 없을 때도 컨테이너를 띄워 두려면 -MinInstances 1 (비용 증가, 대기 시간 대폭 감소).

param(
    [string]$Service = "giridaga-marketer",
    [string]$Region = "asia-northeast3",
    [string]$SecretName = "streamlit-secrets",
    [int]$MinInstances = 0,
    [switch]$NoCpuBoost
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Error "gcloud CLI가 없습니다. https://cloud.google.com/sdk 설치 후 다시 실행하세요."
}

$deployArgs = @(
    "run", "deploy", $Service
    "--source", "."
    "--region", $Region
    "--allow-unauthenticated"
    "--memory", "1024Mi"
    "--cpu", "1"
    "--set-env-vars", "STREAMLIT_SERVER_HEADLESS=true"
    "--update-secrets", "/root/.streamlit/secrets.toml=${SecretName}:latest"
)
if (-not $NoCpuBoost) {
    $deployArgs += "--cpu-boost"
}
if ($MinInstances -gt 0) {
    $deployArgs += "--min-instances=$MinInstances"
}
& gcloud @deployArgs

Write-Host "배포 완료 후 URL은 gcloud run services describe $Service --region $Region --format='value(status.url)' 로 확인하세요."
