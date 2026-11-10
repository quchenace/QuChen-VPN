"""WinINET 系统代理设置 / 恢复 / 管理员提权。

要点：
1. 接管前先把用户原有的 Internet Settings 备份到注册表，断开时原样还原，
   避免"用一次客户端就把系统代理弄丢"。
2. 系统若启用了 PAC（AutoConfigURL），手动代理会被 PAC 覆盖，导致"连接成功但
   流量没走代理"。接管期间临时移除 PAC，断开时还原。
3. 每次写入后回读校验，调用方可据此判断是否真正生效。
"""
from __future__ import annotations

import ctypes
import os
import sys

import winreg

INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
BACKUP_SUBKEY = r"Software\QuChenVPN"
BACKUP_VALUE = "ProxyBackup"

BASE_BYPASS = ("localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;"
               "172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;"
               "172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*;<local>")

_VALUES = ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL")


# --------------------------------------------------------------- 基础读写
def _notify() -> bool:
    """通知系统代理设置已变更（新开的进程才会读到新值）。"""
    try:
        wininet = ctypes.WinDLL("wininet.dll", use_last_error=True)
        wininet.InternetSetOptionW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                               ctypes.c_void_p, ctypes.c_int]
        wininet.InternetSetOptionW.restype = ctypes.c_bool
        changed = wininet.InternetSetOptionW(None, 39, None, 0)   # SETTINGS_CHANGED
        refresh = wininet.InternetSetOptionW(None, 37, None, 0)   # REFRESH
        return bool(changed or refresh)
    except Exception:
        return False


def _read_raw() -> dict:
    """读取原始注册表值，缺失的值记为 None（区别于空字符串）。"""
    raw = {k: None for k in _VALUES}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as k:
            for name in _VALUES:
                try:
                    raw[name] = winreg.QueryValueEx(k, name)[0]
                except FileNotFoundError:
                    raw[name] = None
    except Exception:
        pass
    return raw


def get_proxy() -> dict:
    raw = _read_raw()
    return {
        "enable": bool(raw.get("ProxyEnable")),
        "server": raw.get("ProxyServer") or "",
        "override": raw.get("ProxyOverride") or "",
        "pac": raw.get("AutoConfigURL") or "",
    }


def _norm_server(server: str) -> str:
    return (server or "").strip().replace(" ", "").lower()


def proxy_effective(server: str = "") -> bool:
    """系统代理当前是否真正指向我们（且没有被 PAC 覆盖）。"""
    p = get_proxy()
    if not p.get("enable"):
        return False
    if p.get("pac"):
        return False
    if not server:
        return True
    return _norm_server(p.get("server")) == _norm_server(server)


# --------------------------------------------------------------- 备份 / 还原
def _save_backup(raw: dict) -> bool:
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, BACKUP_SUBKEY, 0,
                                winreg.KEY_ALL_ACCESS) as k:
            payload = {k2: (None if v is None else str(v)) for k2, v in raw.items()}
            winreg.SetValueEx(k, BACKUP_VALUE, 0, winreg.REG_SZ,
                              "|".join(f"{k2}={payload[k2]}" for k2 in _VALUES) +
                              "|EnableType=" + type(raw.get("ProxyEnable")).__name__)
            return True
    except Exception:
        return False


def _load_backup() -> dict | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BACKUP_SUBKEY) as k:
            text = winreg.QueryValueEx(k, BACKUP_VALUE)[0]
    except Exception:
        return None
    out = {}
    try:
        for part in str(text).split("|"):
            if "=" not in part:
                continue
            k2, v = part.split("=", 1)
            if k2 == "EnableType":
                out["__enable_type__"] = v
            else:
                out[k2] = None if v == "None" else v
    except Exception:
        return None
    return out if out else None


def _clear_backup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BACKUP_SUBKEY, 0,
                            winreg.KEY_ALL_ACCESS) as k:
            try:
                winreg.DeleteValue(k, BACKUP_VALUE)
            except FileNotFoundError:
                pass
    except Exception:
        pass


def has_backup() -> bool:
    return _load_backup() is not None


# --------------------------------------------------------------- 设置 / 还原
def set_proxy(enabled: bool, server: str = "", bypass_extra: str = "") -> bool:
    """开启时把系统代理指向本地 mixed 端口；关闭时还原接管前的用户配置。

    返回是否写入并校验成功。
    """
    if enabled:
        raw = _read_raw()
        if not has_backup():
            _save_backup(raw)
        ok = False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0,
                                winreg.KEY_ALL_ACCESS) as k:
                winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
                winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ,
                                  BASE_BYPASS + (";" + bypass_extra if bypass_extra else ""))
                # PAC 优先级高于手动代理，接管期间必须移除
                if raw.get("AutoConfigURL"):
                    try:
                        winreg.DeleteValue(k, "AutoConfigURL")
                    except FileNotFoundError:
                        pass
            _notify()
            p = get_proxy()
            ok = bool(p.get("enable")) and \
                _norm_server(p.get("server")) == _norm_server(server) and \
                not p.get("pac")
        except Exception:
            ok = False
        return ok

    # ---- 关闭：优先还原备份，没有备份才做保守清理
    backup = _load_backup()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0,
                            winreg.KEY_ALL_ACCESS) as k:
            if backup:
                enable = backup.get("ProxyEnable")
                try:
                    enable_val = int(enable) if enable not in (None, "") else 0
                except Exception:
                    enable_val = 0
                winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, enable_val)
                winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ,
                                  backup.get("ProxyServer") or "")
                if backup.get("ProxyOverride") is not None:
                    winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ,
                                      backup.get("ProxyOverride") or "")
                if backup.get("AutoConfigURL"):
                    winreg.SetValueEx(k, "AutoConfigURL", 0, winreg.REG_SZ,
                                      backup.get("AutoConfigURL"))
                _clear_backup()
            else:
                # 没有备份，就不知道自己有没有写过：只有在当前 ProxyServer 确实是我们写的那个时才清，
                # 否则会把用户自己（或别的软件）设的代理一并关掉，整台电脑没网。
                cur = ""
                try:
                    cur = winreg.QueryValueEx(k, "ProxyServer")[0]
                except FileNotFoundError:
                    pass
                if server and _norm_server(cur) == _norm_server(server):
                    winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                    winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, "")
        _notify()
        return True
    except Exception:
        return False


def restore_proxy() -> bool:
    """退出/卸载时兜底：只要有我们的备份就还原。"""
    if not has_backup():
        return False
    return set_proxy(False, "")


# --------------------------------------------------------------- 提权
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_as_admin(extra: str = ""):
    """以管理员身份重新启动自身。extra 追加到命令行（提权实例用 --elevated 跳过单实例检查）。"""
    try:
        if getattr(sys, "frozen", False):
            exe, args = sys.executable, " ".join(sys.argv[1:])
        else:
            exe = sys.executable
            args = " ".join(f'"{a}"' for a in sys.argv)
        if extra and extra not in args:
            args = (args + " " + extra).strip()
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, os.getcwd(), 1)
        return int(rc) > 32                      # ShellExecuteW 返回值 <=32 是错误码
    except Exception:
        return False


# --------------------------------------------------------------- 开机自启
def set_autostart(enable: bool, cmd: str):
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    name = "QuChenVPN"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_ALL_ACCESS) as k:
            if enable:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, name)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def get_autostart() -> bool:
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.QueryValueEx(k, "QuChenVPN")
            return True
    except Exception:
        return False
