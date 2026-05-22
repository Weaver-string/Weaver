$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "Models\MatterEnergyScheduler"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

function Test-PythonInvocation {
  param(
    [string]$Command,
    [string[]]$Arguments = @()
  )

  try {
    & $Command @Arguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  }
}

function Test-VenvPython {
  param([string]$PythonPath)

  if (-not (Test-Path $PythonPath)) {
    return $false
  }

  return Test-PythonInvocation -Command $PythonPath
}

function Resolve-Python {
  $candidates = @(
    @{ Command = "python"; Arguments = @() },
    @{ Command = "py"; Arguments = @("-3") }
  )

  foreach ($candidate in $candidates) {
    $command = Get-Command $candidate.Command -ErrorAction SilentlyContinue
    if ($command -and (Test-PythonInvocation -Command $command.Source -Arguments $candidate.Arguments)) {
      return @{
        Command = $command.Source
        Arguments = $candidate.Arguments
      }
    }
  }

  $pythonRoots = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python"),
    $env:ProgramFiles,
    ${env:ProgramFiles(x86)}
  ) | Where-Object { $_ -and (Test-Path $_) }

  $pythonExecutables = foreach ($pythonRoot in $pythonRoots) {
    Get-ChildItem -Path $pythonRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue
  }

  foreach ($pythonExecutable in ($pythonExecutables | Sort-Object FullName -Descending)) {
    if (Test-PythonInvocation -Command $pythonExecutable.FullName) {
      return @{
        Command = $pythonExecutable.FullName
        Arguments = @()
      }
    }
  }

  Write-Error "Python 3.11 or newer was not found. Install Python 3.13 from https://www.python.org/downloads/windows/, enable 'Add python.exe to PATH', reopen PowerShell, then run .\install.ps1 again."
}

Write-Host "Installing Weaver backend dependencies..."
Set-Location $backend

if (-not (Test-VenvPython $venvPython)) {
  if (Test-Path ".venv") {
    Write-Host "Backend Python environment is missing or broken. Rebuilding it..."
    Remove-Item -LiteralPath ".venv" -Recurse -Force
  }

  Write-Host "Creating backend Python environment..."
  $python = Resolve-Python
  $pythonArgs = $python.Arguments
  & $python.Command @pythonArgs -m venv .venv
} else {
  Write-Host "Backend Python environment already exists. Reusing it."
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt -r requirements-dev.txt

Write-Host "Installing Weaver frontend dependencies..."
Set-Location $frontend
if (Test-Path "node_modules") {
  Write-Host "Frontend dependencies already exist. Running npm install to verify them."
} else {
  Write-Host "Installing frontend dependencies for the first time..."
}
npm.cmd install

Write-Host "Matter Server is installed with the backend Python dependencies."
Write-Host "Weaver install complete."
