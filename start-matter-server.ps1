$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "Models\MatterEnergyScheduler"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$matterServer = Join-Path $backend ".venv\Scripts\matter-server.exe"
$dataDir = Join-Path $root ".weaver\matter-server"
$logDir = Join-Path $root ".weaver\logs"
$logFile = Join-Path $logDir "matter-server.log"

if (-not (Test-Path $python)) {
  Write-Error "Backend virtual environment was not found. Run .\install.ps1 first."
}

try {
  & $python -c "import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] < (3, 14) else 1)" 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Error "Backend Python environment is broken or using an unsupported Python version. Run .\install.ps1 first. Weaver currently requires Python 3.12 or 3.13 for Matter Server support."
  }
} catch {
  Write-Error "Backend Python environment is broken or using an unsupported Python version. Run .\install.ps1 first. Weaver currently requires Python 3.12 or 3.13 for Matter Server support."
}

if (-not (Test-Path $matterServer)) {
  Write-Error "Local Matter Server is not installed. Native Windows Matter Server support is not available because the upstream CHIP core package does not publish Windows builds. Use Matter Server on a Raspberry Pi and set MATTER_SERVER_WS_URL."
}

& $python -c "import chip.exceptions" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Error "Local Matter Server cannot start because chip.exceptions is unavailable. Native Windows Matter Server support is not available because the upstream CHIP core package does not publish Windows builds. Use Matter Server on a Raspberry Pi and set MATTER_SERVER_WS_URL."
}

$existing = Get-NetTCPConnection -LocalPort 5580 -ErrorAction SilentlyContinue |
  Where-Object { $_.State -eq "Listen" } |
  Select-Object -First 1

if ($existing) {
  Write-Host "Matter Server already appears to be listening at ws://127.0.0.1:5580/ws."
  exit 0
}

New-Item -ItemType Directory -Force $dataDir | Out-Null
New-Item -ItemType Directory -Force $logDir | Out-Null

Write-Host "Starting local Matter Server at ws://127.0.0.1:5580/ws..."
Start-Process powershell.exe -WindowStyle Normal -ArgumentList @(
  "-NoExit",
  "-Command",
  "& '$matterServer' --storage-path '$dataDir' --port 5580 --listen-address 127.0.0.1 --log-file '$logFile'"
)
