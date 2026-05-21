param(
  [switch]$RemoveData
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pathsToRemove = @(
  (Join-Path $root "frontend\node_modules"),
  (Join-Path $root "frontend\.next"),
  (Join-Path $root "Models\MatterEnergyScheduler\.venv"),
  (Join-Path $root "Models\MatterEnergyScheduler\.pytest_cache"),
  (Join-Path $root "Models\MatterEnergyScheduler\.ruff_cache")
)

if ($RemoveData) {
  $pathsToRemove += Join-Path $root ".weaver"
}

Write-Host "Stopping Weaver..."
& (Join-Path $root "stop-weaver.ps1")

foreach ($path in $pathsToRemove) {
  $resolvedRoot = [System.IO.Path]::GetFullPath($root)
  $resolvedPath = [System.IO.Path]::GetFullPath($path)

  if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Error "Refusing to remove a path outside the Weaver folder: $resolvedPath"
  }

  if (Test-Path $resolvedPath) {
    Write-Host "Removing $resolvedPath"
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
  }
}

Write-Host "Weaver dependencies have been removed."

if ($RemoveData) {
  Write-Host "Local Weaver app data was also removed."
} else {
  Write-Host "Local Weaver app data was kept. Run .\uninstall.ps1 -RemoveData to remove it too."
}
