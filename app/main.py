"""QuChen VPN 客户端入口。"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
import traceback

import webview

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.service import Service, APP_TITLE, APP_VER  # noqa: E402
from backend import sysproxy  # noqa: E402

user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# 64 位 Windows 的 HWND / HANDLE 是 64 位；不声明 argtypes/restype 时 ctypes 默认按 C int 传，句柄会被截断。
user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.ShowWindow.restype = ctypes.c_bool
user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.SetForegroundWindow.restype = ctypes.c_bool
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowW.restype = ctypes.c_void_p
user32.IsZoomed.argtypes = [ctypes.c_void_p]
user32.IsZoomed.restype = ctypes.c_bool
user32.ReleaseCapture.restype = ctypes.c_bool
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
user32.PostMessageW.restype = ctypes.c_bool
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_kernel32.CloseHandle.restype = ctypes.c_bool

#: 单实例互斥体：开机自启 + 手动双击、或提权重启，都可能同时跑两个客户端；
#: 两个内核会抢端口、两份系统代理互相覆盖，关机时还原顺序也会错。
_INSTANCE_NAME = "Local\\QuChenVPN.SingleInstance"
_instance_handle = None


def _release_instance():
    global _instance_handle
    if _instance_handle:
        try:
            _kernel32.CloseHandle(_instance_handle)
        except Exception:
            pass
        _instance_handle = None


def _acquire_instance() -> bool:
    """True: 本进程是唯一实例（或 --elevated 的新实例）。False: 已有一个在跑，已把它叫到前台。"""
    global _instance_handle
    if "--elevated" in sys.argv:
        return True
    kernel32 = _kernel32
    try:
        handle = kernel32.CreateMutexW(None, False, _INSTANCE_NAME)
        if not handle:
            return True
        if kernel32.GetLastError() == 183:          # ERROR_ALREADY_EXISTS
            hwnd = user32.FindWindowW(None, "QuChen VPN")
            if hwnd:
                user32.ShowWindow(hwnd, 9)          # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
            kernel32.CloseHandle(handle)
            return False
        _instance_handle = handle
        return True
    except Exception:
        return True

SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9
WM_SYSCOMMAND, SC_SIZE = 0x0112, 0xF000
WM_NCLBUTTONDOWN, HTCAPTION = 0x00A1, 2
WMSZ = {"left": 1, "right": 2, "top": 3, "topleft": 4, "topright": 5,
        "bottom": 6, "bottomleft": 7, "bottomright": 8,
        "w": 1, "e": 2, "n": 3, "nw": 4, "ne": 5, "s": 6, "sw": 7, "se": 8}


class Api:
    def __init__(self, svc: Service):
        self.svc = svc
        self.window = None

    # -------------------------------------------------- 内部
    def _hwnd(self):
        try:
            import System  # noqa: F401  (pythonnet)
            form = self.window.native
            return int(form.Handle.ToInt64())
        except Exception:
            return 0

    # -------------------------------------------------- 基础数据
    def bootstrap(self):
        try:
            timer = threading.Timer(1.5, self.svc.maybe_autotest)
            timer.daemon = True
            timer.start()
        except Exception:
            pass
        return {
            "state": self.svc.state(),
            "nodes": self.svc.node_list(),
            "home": self.svc.home,
        }

    def state(self):
        return self.svc.state()

    def nodes(self):
        return self.svc.node_list()

    def logs(self):
        return self.svc.log_list()

    # -------------------------------------------------- 连接
    def connect(self):
        """后台线程执行连接，立即返回，前端靠 state 轮询看进度（避免界面卡死）。"""
        if self.svc.task.get("running"):
            return {"ok": True, "pending": True, "msg": "任务进行中，请稍候"}
        svc = self.svc

        def _run():
            try:
                svc.connect()
            except Exception as e:
                svc._log(f"[core] 连接异常 {type(e).__name__}: {e}")
                svc.task = {"running": False, "kind": "connect", "msg": "连接失败", "progress": 0}
        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "pending": True, "msg": "正在连接…"}

    def disconnect(self):
        return self.svc.disconnect()

    def toggle(self):
        return self.svc.toggle()

    def restart_core(self):
        was = self.svc.core.alive()
        if was:
            self.svc.disconnect()
            time.sleep(0.4)
        if was or self.svc.settings.get("auto_connect"):
            r = self.svc.connect()
            return {"ok": r.get("ok", False), "msg": r.get("msg", "内核已重置")}
        return {"ok": True, "msg": "内核已重置"}

    def select_node(self, name):
        return self.svc.select_node(name)

    def set_group(self, group, value):
        return self.svc.set_group(group, value)

    def set_mode(self, mode):
        return self.svc.set_mode(mode)

    def set_sys_proxy(self, on):
        return self.svc.set_sys_proxy(bool(on))

    def set_tun(self, on):
        return self.svc.set_tun(bool(on))

    def test_speed(self):
        return self.svc.test_speed()

    def refresh(self):
        return self.svc.refresh()

    def diagnose(self):
        return self.svc.diagnose()

    # -------------------------------------------------- 在线更新
    def check_update(self, force=False):
        return self.svc.check_update(bool(force))

    def download_update(self):
        return self.svc.download_update()

    def install_update(self):
        r = self.svc.install_update()
        if r.get("ok"):
            threading.Timer(1.2, lambda: self.window.destroy()).start()
        return r

    def set_update_token(self, token):
        return self.svc.set_update_token(token)

    def update_info(self):
        return self.svc.update_info()

    # -------------------------------------------------- 设置
    def set_autostart(self, on):
        exe = sys.executable
        if getattr(sys, "frozen", False):
            cmd = f'"{exe}" --min'
        else:
            cmd = f'"{exe}" "{os.path.join(self.svc.base, "app", "main.py")}" --min'
        ok = sysproxy.set_autostart(bool(on), cmd)
        self.svc.settings["auto_start"] = bool(on)
        self.svc.save_settings()
        return {"ok": ok}

    def set_auto_connect(self, on):
        self.svc.settings["auto_connect"] = bool(on)
        self.svc.save_settings()
        return {"ok": True}

    def set_theme(self, theme):
        self.svc.settings["theme"] = "dark" if theme == "dark" else "light"
        self.svc.save_settings()
        return {"ok": True}

    def open_url(self, url):
        try:
            os.startfile(url)
        except Exception:
            pass
        return {"ok": True}

    def copy(self, text):
        try:
            import subprocess
            subprocess.run("clip", input=str(text).encode("utf-16le"), shell=True,
                           creationflags=0x08000000, timeout=5)
            return {"ok": True}
        except Exception:
            return {"ok": False}

    def elevate(self):
        ok = sysproxy.run_as_admin("--elevated")
        if ok:
            # 提权实例已经带着 --elevated 起来；本实例退出，避免两个内核、两份系统代理
            _release_instance()
            threading.Timer(1.0, self.window.destroy).start()
        return {"ok": ok}

    # -------------------------------------------------- 窗口
    def win_min(self):
        hwnd = self._hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, SW_MINIMIZE)
        else:
            self.window.minimize()
        return {"ok": True}

    def win_max(self):
        hwnd = self._hwnd()
        if hwnd:
            import ctypes.wintypes as wt
            IsZoomed = user32.IsZoomed
            IsZoomed.restype = ctypes.c_bool
            IsZoomed.argtypes = [wt.HWND]
            user32.ShowWindow(hwnd, SW_RESTORE if IsZoomed(hwnd) else SW_MAXIMIZE)
        return {"ok": True}

    def win_close(self):
        try:
            self.svc.shutdown()
        finally:
            self.window.destroy()
        return {"ok": True}

    def drag(self):
        hwnd = self._hwnd()
        if hwnd:
            user32.ReleaseCapture()
            user32.PostMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
        return {"ok": True}

    def resize_edge(self, direction):
        hwnd = self._hwnd()
        code = WMSZ.get(str(direction).lower())
        if hwnd and code:
            user32.ReleaseCapture()
            user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_SIZE + code, 0)
        return {"ok": True}


def _icon_path(base: str) -> str:
    for name in ("app.ico", "icon.ico"):
        p = os.path.join(base, "assets", name)
        if os.path.exists(p):
            return p
    return ""


def main():
    if not _acquire_instance():
        return
    start_min = "--min" in sys.argv
    svc = Service()
    svc._log(f"[app] {APP_TITLE} v{APP_VER} 启动")
    api = Api(svc)
    base = svc.base
    html = os.path.join(base, "web", "index.html")
    if getattr(sys, "frozen", False):
        html = os.path.join(os.path.dirname(sys.executable), "web", "index.html")
    if not os.path.exists(html):
        html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")

    window = webview.create_window(
        APP_TITLE,
        url=html,
        js_api=api,
        width=1000,
        height=680,
        min_size=(940, 620),
        frameless=True,
        easy_drag=False,
        background_color="#FFFFFF",
        text_select=False,
        confirm_close=False,
    )
    api.window = window

    def stats_loop():
        while True:
            time.sleep(6)
            try:
                svc.tick_stats()
            except Exception:
                pass

    threading.Thread(target=stats_loop, daemon=True).start()

    def autoconnect():
        time.sleep(2.2)
        if svc.settings.get("auto_connect"):
            svc._log("[app] 自动连接")
            svc.connect()

    threading.Thread(target=autoconnect, daemon=True).start()

    icon = _icon_path(base)

    def _started():
        # 开机自启写的是 --min：GUI 起来后最小化，别占着桌面
        if start_min:
            time.sleep(0.8)
            try:
                window.minimize()
            except Exception:
                pass

    try:
        webview.start(
            _started,
            debug=False,
            gui="edgechromium",
            private_mode=False,
            storage_path=os.path.join(svc.home, "webview"),
            icon=icon or None,
        )
    finally:
        svc.shutdown()
        _release_instance()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(os.path.join(os.environ.get("TEMP", "."), "quchen_error.log"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
