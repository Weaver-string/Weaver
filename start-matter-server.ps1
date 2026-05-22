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

if (-not (Test-Path $matterServer)) {
  Write-Error "Matter Server was not found. Run .\install.ps1 first."
}

& $python -c "import cryptography" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Matter Server dependency missing: cryptography. Installing it now..."
  & $python -m pip install cryptography
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
