"""QuChen VPN 客户端入口。"""
from __future__ import annotations

import ctypes
import functools
import os
import re
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
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindow.argtypes = [ctypes.c_void_p]
user32.IsWindow.restype = ctypes.c_bool
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_long * 4)]
user32.GetWindowRect.restype = ctypes.c_bool
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.SetWindowPos.restype = ctypes.c_bool
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

#: 上次解析到的窗口句柄。pywebview 的 native 对象不一定一直可用（见 _hwnd），
#: 一旦按标题/枚举找到过就缓存，避免每次拖动都重新枚举。
_hwnd_cache = 0


def _title_hwnd() -> int:
    """按标题 / 枚举顶层窗口找自己的主窗口句柄。"""
    global _hwnd_cache
    try:
        h = user32.FindWindowW(None, APP_TITLE)
        if h:
            _hwnd_cache = int(h)
            return _hwnd_cache
    except Exception:
        pass
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        try:
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if APP_TITLE in buf.value and user32.IsWindowVisible(hwnd):
                    found.append(int(hwnd))
                    return False
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(_cb, 0)
    except Exception:
        pass
    _hwnd_cache = found[0] if found else 0
    return _hwnd_cache
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_kernel32.CloseHandle.restype = ctypes.c_bool

#: 单实例互斥体：开机自启 + 手动双击、或提权重启，都可能同时跑两个客户端；
#: 两个内核会抢端口、两份系统代理互相覆盖，关机时还原顺序也会错。
_INSTANCE_NAME = "Local\\QuChenVPN.SingleInstance"
_instance_handle = None


def _guard_path() -> str:
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "QuChenVPN", "boot_guard.flag")


def _gpu_off_path() -> str:
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "QuChenVPN", "gpu_off.flag")


def _arm_boot_guard() -> bool:
    """记录本次启动；前端 ready 后把标记改成 ok。

    若上次首屏根本没渲染出来（WebView2 被 GPU 合成卡住是最常见原因），本次带 --disable-gpu 兜底，
    并且落一个 gpu_off 持久标记：否则“卡死一次 → 重开正常 → 又恢复到正常启动 → 下次再卡死”，
    用户看到的就是“每次第一次打开都要卡死，只能关掉重开”。
    """
    path = _guard_path()
    off = _gpu_off_path()
    try:
        prev_failed = False
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    prev_failed = f.read().strip() != "ok"
            except Exception:
                prev_failed = True
        if prev_failed:
            try:
                os.makedirs(os.path.dirname(off), exist_ok=True)
                with open(off, "w", encoding="utf-8") as f:
                    f.write("1")
            except Exception:
                pass
        sticky = os.path.exists(off)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return prev_failed or sticky
    except Exception:
        return os.path.exists(off)


def _clear_boot_guard():
    try:
        path = _guard_path()
        if os.path.isdir(os.path.dirname(path)):
            with open(path, "w", encoding="utf-8") as f:
                f.write("ok")
    except Exception:
        pass


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


def _safe_win(fn):
    """窗口类操作一律兜底：js_api 抛异常时前端只会得到一个 rejected promise，
    表现为点了右上角没反应/控制台报错。这里统一转成 {ok: False, msg} 让界面能提示。"""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            return {"ok": False, "msg": f"{type(e).__name__}: {e}"}
    return wrapper


class Api:
    def __init__(self, svc: Service):
        self.svc = svc
        self.window = None

    # -------------------------------------------------- 内部
    def _hwnd(self):
        """解析主窗口句柄。

        旧实现只在 window.native 上取 Form.Handle，pythonnet 版本一变就抛异常，
        异常被吞成 0，前端的拖动/最大化/最小化全部静默失效（表现为“窗口拖不动”
        “点右上角没反应”）。这里改为 native → 标题查找 → 枚举可见窗口三级兜底。
        """
        global _hwnd_cache
        if _hwnd_cache:
            try:
                if user32.IsWindow(_hwnd_cache):
                    return _hwnd_cache
            except Exception:
                pass
        try:
            form = self.window.native
            h = getattr(form, "Handle", None)
            if h is not None:
                v = int(h.ToInt64() if hasattr(h, "ToInt64") else h)
                if v:
                    _hwnd_cache = v
                    return v
        except Exception:
            pass
        return _title_hwnd()

    # -------------------------------------------------- 基础数据
    def bootstrap(self):
        # 旧实现启动 1.5s 就跑 maybe_autotest（最多 2500 条并发测速），
        # 与首屏渲染抢 CPU/内核，表现就是“第一次打开必卡死，关掉重开才好”。
        # 这里推迟到 25s，并把首屏节点截断（全量改由 node_page 按需拉）。
        try:
            timer = threading.Timer(25.0, self.svc.maybe_autotest)
            timer.daemon = True
            timer.start()
        except Exception:
            pass
        return {
            "state": self.svc.state(),
            "nodes": self.svc.node_list(head=240),
            "node_total": len(self.svc.pool.get("nodes") or []),
            "home": self.svc.home,
        }

    def state(self):
        return self.svc.state()

    def nodes(self):
        return self.svc.node_list()

    def node_page(self, offset=0, limit=400):
        """节点页需要全量时按需分页取，避免一次把 2500 条塞进 WebView。"""
        try:
            nodes = self.svc.node_list()
            offset = max(0, int(offset))
            limit = int(limit) if limit else len(nodes)
            return {"ok": True, "nodes": nodes[offset:offset + limit], "total": len(nodes)}
        except Exception as e:
            return {"ok": False, "msg": str(e), "nodes": [], "total": 0}

    def logs(self):
        return self.svc.log_list()

    # -------------------------------------------------- 连接
    def connect(self):
        """后台线程执行连接，立即返回，前端靠 state 轮询看进度（避免界面卡死）。"""
        running_kind = (self.svc.task or {}).get("kind") if self.svc.task.get("running") else ""
        # 测速是纯后台任务，不应该拦住用户点连接（旧实现一律拒绝，用户只能干等）
        if self.svc.task.get("running") and running_kind != "speed":
            return {"ok": True, "pending": True, "msg": "任务进行中，请稍候"}
        svc = self.svc
        # Claim the task before the thread starts, so a second click cannot start a second connect.
        svc.task = {"running": True, "kind": "connect", "msg": "正在连接…", "progress": 5}

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
        """Restart in the background: disconnect + connect can take 20 s, and the old code blocked the UI thread."""
        was = self.svc.core.alive()
        svc = self.svc

        def _run():
            try:
                if was:
                    svc.disconnect()
                    time.sleep(0.4)
                if was or svc.settings.get("auto_connect"):
                    svc.connect()
            except Exception as e:
                svc._log(f"[core] 重启内核异常 {type(e).__name__}: {e}")

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "pending": True, "msg": "正在重启内核…"}

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
            timer = threading.Timer(1.2, lambda: self.window.destroy())
            timer.daemon = True
            timer.start()
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
        # Only report what the registry actually took: a denied write must not leave the switch "on".
        self.svc.settings["auto_start"] = bool(on) if ok else False
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
        """Only http(s). os.startfile on an arbitrary string is a local-execution path, and the page only
        ever sends links."""
        u = str(url or "").strip()
        if not re.match(r"^https?://", u, re.I):
            return {"ok": False, "msg": "只打开 http/https 链接"}
        try:
            import webbrowser
            return {"ok": bool(webbrowser.open(u))}
        except Exception:
            return {"ok": False}

    def copy(self, text):
        try:
            import subprocess
            subprocess.run(["clip"], input=str(text).encode("utf-16le"),
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

    def ready(self):
        """前端首屏渲染完成后回调：自动连接要等界面真出来再跑，
        否则启动瞬间「WebView2 首次初始化 + 内核构建 2500 节点配置」抢同一波 CPU/IO，
        表现就是第一次打开必卡死，关掉重开（内核已在跑）反而正常。"""
        evt = getattr(self, "ready_evt", None)
        if evt is not None:
            evt.set()
        try:
            _clear_boot_guard()
        except Exception:
            pass
        return {"ok": True}

    # -------------------------------------------------- 窗口
    @_safe_win
    def win_min(self):
        hwnd = self._hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, SW_MINIMIZE)
        else:
            self.window.minimize()
        return {"ok": True}

    @_safe_win
    def win_max(self):
        hwnd = self._hwnd()
        if hwnd:
            try:
                user32.IsZoomed.argtypes = [ctypes.c_void_p]
                user32.IsZoomed.restype = ctypes.c_bool
                user32.ShowWindow(hwnd, SW_RESTORE if user32.IsZoomed(hwnd) else SW_MAXIMIZE)
                return {"ok": True}
            except Exception:
                pass
        # 句柄拿不到时不能让按钮变成“点了没反应”
        try:
            self.window.toggle_fullscreen()
        except Exception as e:
            return {"ok": False, "msg": str(e)}
        return {"ok": True}

    @_safe_win
    def win_close(self):
        # 先把内核/系统代理的清理丢到后台，立刻收起窗口；
        # 旧实现在 UI 线程同步 shutdown（等内核退出最多 5s），点关闭后整个窗口僵住。
        # window.destroy() 在非 UI 线程偶发卡在 WebView2 的 DestroyWindow 上，
        # 所以再加一层进程兜底退出，保证点关闭就一定关得掉。
        threading.Thread(target=self._cleanup_quiet, daemon=True).start()

        def _bye():
            time.sleep(0.05)
            try:
                self.window.destroy()
            except Exception:
                pass
            time.sleep(0.35)
            os._exit(0)

        threading.Timer(0.06, _bye).start()
        return {"ok": True}

    def _cleanup_quiet(self):
        try:
            self.svc.shutdown()
        except Exception:
            pass
        try:
            _release_instance()
        except Exception:
            pass

    @_safe_win
    def win_pos(self):
        """返回窗口在屏幕上的位置，供前端做自定义拖动。"""
        hwnd = self._hwnd()
        if not hwnd:
            return {"ok": False}
        r = (ctypes.c_long * 4)()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return {"ok": False}
        # 前端拿到的是 CSS 像素，SetWindowPos 要的是物理像素；125%/150% 缩放下不做换算，
        # 窗口就会“拖得比鼠标慢半拍”，看着像拖动失灵。
        scale = 1.0
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(ctypes.c_void_p(hwnd))
            if dpi:
                scale = float(dpi) / 96.0
        except Exception:
            pass
        return {"ok": True, "x": r[0], "y": r[1], "w": r[2] - r[0], "h": r[3] - r[1],
                "scale": scale}

    @_safe_win
    def win_move(self, x, y):
        """把窗口移到指定屏幕坐标（自定义拖动的兜底通道）。"""
        hwnd = self._hwnd()
        if not hwnd:
            return {"ok": False}
        try:
            ok = user32.SetWindowPos(hwnd, None, int(x), int(y), 0, 0,
                                     SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            return {"ok": bool(ok)}
        except Exception:
            return {"ok": False}

    @_safe_win
    def drag(self):
        hwnd = self._hwnd()
        if hwnd:
            user32.ReleaseCapture()
            user32.PostMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
            return {"ok": True}
        return {"ok": False}

    @_safe_win
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
    if _arm_boot_guard():
        # 上次首屏没渲染完，本次禁用 GPU 合成兜底（正常启动不会带这个参数）
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--disable-gpu"
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

    ready_evt = threading.Event()
    api.ready_evt = ready_evt

    def autoconnect():
        # 等界面渲染完（最多 25s）再自动连接；界面没起来就不连，优先保证窗口可用
        if not ready_evt.wait(25):
            svc._log("[app] 界面未就绪，本次跳过自动连接")
            return
        time.sleep(1.2)
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
