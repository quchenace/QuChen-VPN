"""在线更新：查询 GitHub Release、下载、替换目录并重启。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import requests

REPO = "OWNER/QuChen-VPN"      # 运行时会被 build 脚本替换为真实仓库
ASSET_KEYWORD = "QuChenVPN-win64"


def _api_headers(token: str | None = None):
    h = {"Accept": "application/vnd.github+json", "User-Agent": "QuChenVPN-updater"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def parse_version(v: str) -> tuple:
    v = (v or "").strip().lstrip("vV")
    out = []
    for part in v.split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:4])


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def check(repo: str = None, current: str = "", token: str = None, proxies=None) -> dict:
    repo = repo or REPO
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        r = requests.get(url, headers=_api_headers(token), timeout=15, proxies=proxies)
        if r.status_code == 404:
            return {"ok": False, "msg": "仓库暂无 Release 发布", "latest": ""}
        if r.status_code != 200:
            return {"ok": False, "msg": f"接口返回 {r.status_code}", "latest": ""}
        data = r.json()
    except Exception as e:
        return {"ok": False, "msg": f"网络错误: {type(e).__name__}", "latest": ""}

    tag = data.get("tag_name") or data.get("name") or ""
    assets = data.get("assets") or []
    asset = None
    for a in assets:
        if ASSET_KEYWORD in a.get("name", ""):
            asset = a
            break
    if asset is None and assets:
        asset = assets[0]
    return {
        "ok": True,
        "latest": tag,
        "current": current,
        "has_update": is_newer(tag, current),
        "notes": (data.get("body") or "")[:1200],
        "asset_name": (asset or {}).get("name", ""),
        "asset_url": (asset or {}).get("browser_download_url", ""),
        "asset_size": (asset or {}).get("size", 0),
        "published": (data.get("published_at") or "")[:19].replace("T", " "),
        "page": data.get("html_url", ""),
        "msg": "发现新版本" if is_newer(tag, current) else "已是最新版本",
    }


def download(url: str, dest: str, progress=None, proxies=None) -> str:
    with requests.get(url, stream=True, timeout=60, proxies=proxies,
                      headers={"User-Agent": "QuChenVPN-updater"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(int(done * 100 / total))
    return dest


def _install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def apply_update(package: str, exe_name: str = "QuChenVPN.exe", on_stage=None) -> str:
    """解压更新包，生成替换脚本并启动，返回脚本路径。"""
    work = os.path.join(tempfile.gettempdir(), "QuChenVPN_update")
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    if package.lower().endswith(".zip"):
        with zipfile.ZipFile(package) as z:
            z.extractall(work)
        # 如果压缩包内只有一层目录，进入该目录
        entries = [e for e in os.listdir(work) if not e.startswith("__")]
        if len(entries) == 1 and os.path.isdir(os.path.join(work, entries[0])):
            work = os.path.join(work, entries[0])
    else:
        shutil.copy2(package, os.path.join(work, os.path.basename(package)))

    target = _install_dir()
    pid = os.getpid()
    bat = os.path.join(tempfile.gettempdir(), "quchen_update.bat")
    exe = os.path.join(target, exe_name)
    script = f"""@echo off
chcp 65001 >nul
echo 正在更新 QuChen VPN...
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
robocopy "{work}" "{target}" /E /IS /IT /NFL /NDL /NJH /NJS /NC /NS >nul
start "" "{exe}"
"""
    with open(bat, "w", encoding="gbk", errors="ignore") as f:
        f.write(script)
    if on_stage:
        on_stage(bat)
    subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.CREATE_NEW_CONSOLE)
    return bat
