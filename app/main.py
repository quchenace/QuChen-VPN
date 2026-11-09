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
            threading.Timer(1.5, self.svc.maybe_autotest).start()
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
        return self.svc.connect()

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
        return {"ok": sysproxy.run_as_admin()}

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
    try:
        webview.start(
            debug=False,
            gui="edgechromium",
            private_mode=False,
            storage_path=os.path.join(svc.home, "webview"),
            icon=icon or None,
        )
    finally:
        svc.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(os.path.join(os.environ.get("TEMP", "."), "quchen_error.log"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
