# Build QuChen VPN (PyInstaller onedir)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m PyInstaller --noconfirm --clean --windowed `
    --name QuChenVPN `
    --icon "app\assets\app.ico" `
    --add-data "app\web;web" `
    --add-data "app\assets;assets" `
    --add-data "runtime;runtime" `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import webview.platforms.winforms `
    --hidden-import clr `
    --hidden-import pythonnet `
    --exclude-module tkinter `
    --exclude-module PyQt5 `
    --exclude-module PyQt6 `
    --exclude-module PySide6 `
    --exclude-module numpy `
    --exclude-module pandas `
    app\main.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$dist = Join-Path $root "dist\QuChenVPN"
if (-not (Test-Path $dist)) { throw "dist folder missing: $dist" }

$rel = Join-Path $root "release"
New-Item -ItemType Directory -Force -Path $rel | Out-Null
$zip = Join-Path $rel "QuChenVPN-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($dist, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $true)

$mb = (Get-Item $zip).Length / 1MB
Write-Host ("package ok: {0} ({1:N1} MB)" -f $zip, $mb)
