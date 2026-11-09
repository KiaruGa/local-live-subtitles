# Builds the portable application and the Windows installer.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -SkipModels
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -SkipInstaller
#
# Requirements (one-time):
#   pip install -r requirements-dev.txt
#   winget install -e --id JRSoftware.InnoSetup

[CmdletBinding()]
param(
    [switch]$SkipModels,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-Step {
    param([string]$Title, [scriptblock]$Action)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Title (exit code $LASTEXITCODE)"
    }
}

if (-not $SkipModels) {
    Invoke-Step "Preparing local models" { python scripts\prepare_models.py }
} else {
    Write-Host "Skipping model preparation." -ForegroundColor Yellow
}

Invoke-Step "Rendering application icon" { python scripts\make_icon.py }

Invoke-Step "Building application with PyInstaller" {
    python -m PyInstaller --noconfirm --clean LocalLiveSubtitles.spec
}

$appDir = Join-Path $root "dist\LocalLiveSubtitles"
$appExe = Join-Path $appDir "LocalLiveSubtitles.exe"
if (-not (Test-Path $appExe)) {
    throw "Expected executable not found: $appExe"
}
$appSize = (Get-ChildItem $appDir -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("Portable build: {0} ({1:N0} MB)" -f $appDir, ($appSize / 1MB)) -ForegroundColor Green

if ($SkipInstaller) {
    Write-Host "Skipping installer build." -ForegroundColor Yellow
    exit 0
}

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
}
if (-not $iscc) {
    throw "Inno Setup not found. Install it with: winget install -e --id JRSoftware.InnoSetup"
}

Invoke-Step "Building Windows installer" {
    & $iscc "installer\LocalLiveSubtitles.iss"
}

$installer = Get-ChildItem "dist\LocalLiveSubtitles-Setup-*.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($installer) {
    Write-Host ("Installer: {0} ({1:N0} MB)" -f $installer.FullName, ($installer.Length / 1MB)) -ForegroundColor Green
}
