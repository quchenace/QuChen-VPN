# Build QuChen VPN (PyInstaller onedir)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$assetCheck = @'
from pathlib import Path
import hashlib
import sys

source = Path(sys.argv[1]) / "app" / "web"
packed = Path(sys.argv[2]) / "_internal" / "web"
extensions = {".html", ".css", ".js"}

def assets(root):
    return {
        path.relative_to(root): path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    }

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if not packed.is_dir():
    raise SystemExit(f"packaged web folder missing: {packed}")
source_files = assets(source)
packed_files = assets(packed)
if not source_files:
    raise SystemExit(f"no web assets found: {source}")
problems = []
for relative in sorted(source_files.keys() | packed_files.keys()):
    if relative not in packed_files:
        problems.append(f"missing: {relative}")
    elif relative not in source_files:
        problems.append(f"unexpected: {relative}")
    elif sha256(source_files[relative]) != sha256(packed_files[relative]):
        problems.append(f"stale: {relative}")
if problems:
    raise SystemExit("packaged web asset verification failed:\n" + "\n".join(problems))
print(f"web assets ok: {len(source_files)} HTML/CSS/JS files match app\\web (SHA-256)")
'@

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

# PyInstaller onedir 会把 --add-data 放进 _internal。逐字节核对打包页面，
# 防止 exe 已经更新、界面却仍是旧 HTML/CSS/JS 的半新包流入发布目录。
python -c $assetCheck $root $dist
if ($LASTEXITCODE -ne 0) { throw "web asset verification failed" }

$rel = Join-Path $root "release"
New-Item -ItemType Directory -Force -Path $rel | Out-Null
$zip = Join-Path $rel "QuChenVPN-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($dist, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $true)

$mb = (Get-Item $zip).Length / 1MB
Write-Host ("package ok: {0} ({1:N1} MB)" -f $zip, $mb)
