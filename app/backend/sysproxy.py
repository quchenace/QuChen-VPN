"""WinINET 系统代理设置 / 恢复 / 管理员提权。"""
from __future__ import annotations

import ctypes
import os
import sys

import winreg

INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def _notify():
    try:
        import ctypes.wintypes as wt
        INTERNET_OPTION_SETTINGS_CHANGED = 39
        INTERNET_OPTION_REFRESH = 37
        wininet = ctypes.WinDLL("wininet.dll")
        wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
    except Exception:
        pass


def get_proxy() -> dict:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as k:
            try:
                enable = winreg.QueryValueEx(k, "ProxyEnable")[0]
            except FileNotFoundError:
                enable = 0
            try:
                server = winreg.QueryValueEx(k, "ProxyServer")[0]
            except FileNotFoundError:
                server = ""
            try:
                override = winreg.QueryValueEx(k, "ProxyOverride")[0]
            except FileNotFoundError:
                override = ""
            try:
                pac = winreg.QueryValueEx(k, "AutoConfigURL")[0]
            except FileNotFoundError:
                pac = ""
            return {"enable": bool(enable), "server": server, "override": override, "pac": pac}
    except Exception:
        return {"enable": False, "server": "", "override": "", "pac": ""}


def set_proxy(enabled: bool, server: str = "", bypass_extra: str = ""):
    """开启时把系统代理指向本地 mixed 端口；关闭时只清除我们写入的值。"""
    base_bypass = "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.2*;172.30.*;172.31.*;192.168.*;<local>"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_ALL_ACCESS) as k:
        if enabled:
            winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
            winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ,
                              base_bypass + (";" + bypass_extra if bypass_extra else ""))
        else:
            cur = ""
            try:
                cur = winreg.QueryValueEx(k, "ProxyServer")[0]
            except FileNotFoundError:
                pass
            winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            if cur == server or not server:
                winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, "")
    _notify()


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_as_admin():
    """以管理员身份重新启动自身。"""
    try:
        if getattr(sys, "frozen", False):
            exe, args = sys.executable, " ".join(sys.argv[1:])
        else:
            exe = sys.executable
            args = " ".join(f'"{a}"' for a in sys.argv)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, os.getcwd(), 1)
        return True
    except Exception:
        return False


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
