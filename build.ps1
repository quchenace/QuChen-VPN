# 打包 QuChen VPN（PyInstaller onedir）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = "python"
& $py -m PyInstaller --noconfirm --clean --windowed `
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

if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }

$dist = Join-Path $root "dist\QuChenVPN"
if (-not (Test-Path $dist)) { throw "产物目录不存在: $dist" }

# 图标与种子池随包（PyInstaller 已包含 assets，这里再确保根目录有一份 ico）
$rel = Join-Path $root "release"
New-Item -ItemType Directory -Force -Path $rel | Out-Null
$zip = Join-Path $rel "QuChenVPN-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $dist "*") -DestinationPath $zip -CompressionLevel Optimal
Write-Host "打包完成: $zip"
Write-Host ("大小: {0:N1} MB" -f ((Get-Item $zip).Length / 1MB))
