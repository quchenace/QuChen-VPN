"""在线更新：查询 GitHub Release、下载、替换目录并重启。

替换策略（修复要点）：
- 采用 robocopy /MIR 镜像写入：先删除新版本中已不存在的旧文件，再复制新文件，
  避免旧版本残留文件（旧模块、旧内核、旧依赖）导致升级后行为异常。
- 替换前整目录备份，robocopy 返回码 >= 8 时自动回滚并从备份启动，防止变砖。
- 等待旧进程退出改为带最大重试次数的精确 PID 匹配，避免死循环卡住更新。
- 替换脚本使用纯 ASCII，规避 chcp 与文件编码冲突导致的乱码/执行异常。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import requests

REPO = "quchenace/QuChen-VPN"
ASSET_KEYWORD = "QuChenVPN-win64"

# 国内直连 GitHub API 常被重置，检查更新时依次尝试的镜像前缀
API_MIRRORS = (
    "",
    "https://ghproxy.net/",
    "https://gh.nxnow.top/",
    "https://ghfast.top/",
    "https://gh-proxy.com/",
)

DOWNLOAD_MIRRORS = (
    # Measured 2026-11-11: these two answer from CN; ghfast/gh-proxy time out. Direct GitHub is last
    # because a stalled GitHub connection would otherwise spend a minute before the first mirror.
    "https://ghproxy.net/",
    "https://gh.nxnow.top/",
    "",
    "https://ghfast.top/",
    "https://gh-proxy.com/",
)


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


def _mirror(url: str, prefix: str) -> str:
    if not prefix:
        return url
    return prefix.rstrip("/") + "/" + url


def _sessions(proxies=None):
    """依次返回：直连会话（忽略系统代理/环境变量）、走系统代理的会话。

    连接 VPN 之前，Windows 系统代理常常指向一个并未监听的本地端口，
    requests 默认会走它，导致检查更新/下载全部 SSLError。所以先直连。
    """
    direct = requests.Session()
    direct.trust_env = False
    out = [direct]
    if proxies is None:
        out.append(requests.Session())
    return out


def check(repo: str = None, current: str = "", token: str = None, proxies=None,
          mirrors: bool = True) -> dict:
    """查询最新 Release。直连失败时依次尝试镜像，全部失败才返回错误。"""
    repo = repo or REPO
    if "/" not in repo or repo.upper().startswith("OWNER"):
        repo = REPO
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    prefixes = API_MIRRORS if mirrors else ("",)
    errors = []
    data = None
    sessions = _sessions(proxies)
    for prefix in prefixes:
        r = None
        for sess in sessions:
            try:
                r = sess.get(_mirror(url, prefix), headers=_api_headers(token),
                             timeout=15, proxies=proxies)
                break
            except Exception as e:
                errors.append(f"{prefix or 'direct'}/{('direct' if not sess.trust_env else 'sysproxy')}: {type(e).__name__}")
        if r is None:
            continue
        if r.status_code == 404:
            hint = "仓库暂无 Release 发布"
            if token:
                hint = "仓库暂无 Release 发布（或 Token 无权访问）"
            else:
                hint = "仓库暂无 Release 发布；若仓库为私有，请在设置里填写 GitHub Token"
            return {"ok": False, "msg": hint, "latest": ""}
        if r.status_code == 403 and "rate limit" in (r.text or "").lower():
            errors.append(f"{prefix or 'direct'}: API 限流")
            continue
        if r.status_code != 200:
            errors.append(f"{prefix or 'direct'}: HTTP {r.status_code}")
            continue
        try:
            data = r.json()
            break
        except Exception as e:
            errors.append(f"{prefix or 'direct'}: 解析失败 {type(e).__name__}")
    if data is None:
        return {"ok": False, "msg": "网络错误（" + "；".join(errors[:3]) + "）", "latest": ""}

    tag = data.get("tag_name") or data.get("name") or ""
    assets = data.get("assets") or []
    # 只认 zip 便携包：安装器 exe 无法用于“解压后覆盖”的热更新
    zip_assets = [a for a in assets if a.get("name", "").lower().endswith(".zip")]
    asset = None
    for a in zip_assets:
        if ASSET_KEYWORD in a.get("name", ""):
            asset = a
            break
    if asset is None and zip_assets:
        asset = zip_assets[0]
    newer = is_newer(tag, current)
    return {
        "ok": True,
        "latest": tag,
        "current": current,
        "has_update": newer,
        "notes": (data.get("body") or "")[:1200],
        "asset_name": (asset or {}).get("name", ""),
        "asset_url": (asset or {}).get("browser_download_url", ""),
        "asset_size": (asset or {}).get("size", 0),
        "asset_digest": (asset or {}).get("digest") or "",        # "sha256:..." when GitHub records it
        "published": (data.get("published_at") or "")[:19].replace("T", " "),
        "page": data.get("html_url", ""),
        "msg": (f"发现新版本 {tag}" if newer else f"已是最新版本（{current}）"),
    }


def download(url: str, dest: str, progress=None, proxies=None,
             expect_size: int = 0, token: str = None, sha256: str = "") -> str:
    """下载更新包；自动尝试镜像，下载后校验大小、SHA-256（GitHub 给出时）与 zip 完整性。"""
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    headers = {"User-Agent": "QuChenVPN-updater"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last_err = None
    sessions = _sessions(proxies)
    for prefix in DOWNLOAD_MIRRORS:
        tmp = dest + ".part"
        try:
            sess = sessions[0]
            try:
                resp = sess.get(_mirror(url, prefix), stream=True, timeout=60,
                                proxies=proxies, headers=headers)
            except Exception:
                sess = sessions[-1]
                resp = sess.get(_mirror(url, prefix), stream=True, timeout=60,
                                proxies=proxies, headers=headers)
            with resp as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length") or 0) or int(expect_size or 0)
                done = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(256 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                        if progress and total:
                            progress(min(99, int(done * 100 / total)))
            size = os.path.getsize(tmp)
            if expect_size and size != int(expect_size):
                raise IOError(f"大小不符 {size}/{expect_size}")
            want = (sha256 or "").strip().lower()
            if want.startswith("sha256:"):
                want = want[7:]
            if want:
                h = hashlib.sha256()
                with open(tmp, "rb") as fh:
                    for block in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(block)
                if h.hexdigest() != want:
                    raise IOError("更新包校验失败（SHA-256 不符）")
            if dest.lower().endswith(".zip"):
                with zipfile.ZipFile(tmp) as z:
                    bad = z.testzip()
                    if bad:
                        raise IOError(f"压缩包损坏 {bad}")
            os.replace(tmp, dest)
            if progress:
                progress(100)
            return dest
        except Exception as e:
            last_err = e
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
    raise IOError(f"下载失败: {last_err}")


def _install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_SCRIPT = r"""@echo off
setlocal enableextensions
set "SRC={src}"
set "DST={dst}"
set "BAK={bak}"
set "EXE={exe}"
set "PID={pid}"
set "PKG={pkg}"

rem ---- wait for the running instance to exit (max 90s) ----
set /a TRY=0
:wait
tasklist /FI "PID eq %PID%" /NH 2>nul | findstr /R /C:"[^0-9]%PID%[^0-9]" >nul
if errorlevel 1 goto closed
set /a TRY+=1
if %TRY% GEQ 90 goto closed
timeout /t 1 /nobreak >nul
goto wait
:closed

rem ---- backup current install dir ----
if exist "%BAK%" rmdir /s /q "%BAK%"
robocopy "%DST%" "%BAK%" /E /NFL /NDL /NJH /NJS /NC /NS >nul

rem ---- write new build ----
rem Full package: mirror mode, purge obsolete program files FIRST then copy (delete-then-update).
rem Suspicious dirs that must never be purged by the mirror pass: user data / logs.
rem The kernel under runtime/  IS part of the package and is meant to be refreshed.
rem unins* is the installer's uninstall entry: a zip never contains it, so a mirror copy would delete
rem it and leave "Apps & features" pointing at a file that no longer exists.
robocopy "%SRC%" "%DST%" {mode} /XD "{dxdata}" "{dxlogs}" /XF "settings.json" "unins*" /R:2 /W:1 /NFL /NDL /NJH /NJS /NC /NS >nul
if errorlevel 8 goto rollback

rem ---- launch new build ----
if exist "%DST%\%EXE%" start "" "%DST%\%EXE%"
if exist "%BAK%" rmdir /s /q "%BAK%" >nul 2>nul
if exist "%PKG%" del /f /q "%PKG%" >nul 2>nul
if exist "%SRC%" rmdir /s /q "%SRC%" >nul 2>nul
exit /b 0

:rollback
echo [rollback] copy failed, restoring previous version...
if exist "%BAK%" (
  robocopy "%BAK%" "%DST%" /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NC /NS >nul
)
if exist "%DST%\%EXE%" start "" "%DST%\%EXE%"
exit /b 1
"""


MAX_UNPACKED = 3 * 1024 * 1024 * 1024
MAX_MEMBERS = 50000


def _check_archive(z: zipfile.ZipFile):
    """A corrupt or hostile archive must not fill the disk or escape the work folder."""
    total = 0
    members = z.infolist()
    if len(members) > MAX_MEMBERS:
        raise IOError(f"更新包文件过多（{len(members)}）")
    for m in members:
        total += m.file_size
        if total > MAX_UNPACKED:
            raise IOError("更新包解压后超过 3 GB，已中止")
        name = m.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise IOError(f"更新包含非法路径：{m.filename}")


def apply_update(package: str, exe_name: str = "QuChenVPN.exe", on_stage=None) -> str:
    """解压更新包，生成替换脚本并启动，返回脚本路径。"""
    work = os.path.join(tempfile.gettempdir(), "QuChenVPN_update")
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    if package.lower().endswith(".zip"):
        with zipfile.ZipFile(package) as z:
            _check_archive(z)
            z.extractall(work)
        entries = [e for e in os.listdir(work) if not e.startswith("__")]
        if len(entries) == 1 and os.path.isdir(os.path.join(work, entries[0])):
            work = os.path.join(work, entries[0])
    else:
        shutil.copy2(package, os.path.join(work, os.path.basename(package)))

    src = work.rstrip("\\/")
    target = _install_dir().rstrip("\\/")
    if os.path.normcase(src) == os.path.normcase(target):
        raise RuntimeError("更新包目录与安装目录相同，已中止")

    # 判断是否为完整安装包（含 web/ 或 backend/ 目录）：完整包才允许删除旧文件，
    # 否则只覆盖同名文件，避免把 web/backend 等目录整片删掉。
    try:
        names = set(os.listdir(src))
    except OSError:
        names = set()
    if exe_name not in names:
        found = [n for n in names if n.lower().endswith(".exe")]
        if found:
            exe_name = found[0]
    # A partial archive that happens to hold one folder (a new web/ only) must not get /MIR: that would
    # delete runtime/, the exe and everything else. Full means the exe plus one of the runtime folders.
    is_full = (exe_name in names and bool(names & {"web", "runtime", "backend"})) or {"web", "runtime"} <= names
    mode = "/MIR" if is_full else "/E"

    backup = os.path.join(tempfile.gettempdir(), "QuChenVPN_backup")
    bat = os.path.join(tempfile.gettempdir(), "quchen_update.bat")
    script = _SCRIPT.format(
        src=src, dst=target, bak=backup, mode=mode,
        exe=exe_name, pid=os.getpid(), pkg=os.path.abspath(package),
        dxdata=os.path.join(target, "data"),
        dxlogs=os.path.join(target, "logs"),
    )
    with open(bat, "w", encoding="ascii", errors="ignore", newline="\r\n") as f:
        f.write(script)
    if on_stage:
        on_stage(bat)
    subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.CREATE_NEW_CONSOLE)
    return bat
