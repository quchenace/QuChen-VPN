"""QuChen VPN 登录墙自测（不依赖 pywebview，直接测 Api 层门禁）。

    cd D:\QUCHENALL\QuChenDev\QuChen-VPN
    python tools\auth_gate_test.py

覆盖：未登录拦截业务 API、登录成功放行、退出登录重新拦截、开关关闭直通、会话文件不存密码。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
sys.path.insert(0, os.path.abspath(APP_DIR))

# main.py 顶部 import webview；自测只测 Api 层，注入桩避免拉起 GUI 依赖。
if "webview" not in sys.modules:
    import types

    _stub = types.ModuleType("webview")
    _stub.create_window = lambda *a, **k: None
    _stub.start = lambda *a, **k: None
    sys.modules["webview"] = _stub

PASSED = 0
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}  {detail}")


class FakeAccountHandler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def _send(self, code, obj):
        buf = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(buf)))
        self.end_headers()
        self.wfile.write(buf)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            body = {}
        if self.path == "/api/auth/login":
            if body.get("password") == "RightPass1!":
                return self._send(200, {
                    "access_token": "at-1", "refresh_token": "rt-1", "expires_in": 1800,
                    "user": {"email": body.get("email"), "role": "user"},
                })
            return self._send(401, {"code": "bad_credentials", "message": "邮箱或密码不正确"})
        if self.path == "/api/auth/refresh":
            if body.get("refresh_token") == "rt-1":
                return self._send(200, {"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 1800})
            return self._send(401, {"code": "invalid_refresh", "message": "refresh 无效"})
        if self.path == "/api/auth/logout":
            return self._send(200, {"ok": True})
        return self._send(404, {"code": "not_found"})


class StubService:
    """只实现 Api 会用到的最小面。"""

    def __init__(self):
        self.task = {"running": False}
        self.home = tempfile.gettempdir()
        self.logs = []
        self.pool = {"nodes": []}

    def _log(self, msg):
        self.logs.append(msg)

    def connect(self):
        return {"ok": True, "msg": "connected"}

    def disconnect(self):
        return {"ok": True, "msg": "disconnected"}

    def toggle(self):
        return {"ok": True}

    def select_node(self, name):
        return {"ok": True, "name": name}

    def set_group(self, group, value):
        return {"ok": True}

    def set_mode(self, mode):
        return {"ok": True}

    def set_sys_proxy(self, on):
        return {"ok": True}

    def set_tun(self, on):
        return {"ok": True}

    def state(self):
        return {"running": False}

    def node_list(self, head=None):
        return []

    def log_list(self):
        return []

    def test_speed(self):
        return {"ok": True}

    def refresh(self):
        return {"ok": True}

    def diagnose(self):
        return {"ok": True}

    def maybe_autotest(self):
        pass


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), FakeAccountHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    session_file = os.path.join(tempfile.mkdtemp(prefix="quchen-vpn-gate-"), "vpn.json")
    os.environ["QUCHEN_AUTH_BASE"] = base
    os.environ["QUCHEN_AUTH_SESSION_FILE"] = session_file
    os.environ.pop("QUCHEN_ACCOUNT_GATE_DISABLED", None)

    from main import Api, _install_account_guard  # noqa: E402

    api = Api(StubService())
    _install_account_guard(api)

    print("[1] 未登录：业务 API 一律 AUTH_REQUIRED")
    r = api.bootstrap()
    check("bootstrap 被拦", r.get("error") == "AUTH_REQUIRED" and r.get("auth_required") is True, str(r)[:80])
    r = api.connect()
    check("connect 被拦", r.get("error") == "AUTH_REQUIRED", str(r)[:80])
    r = api.select_node("HK-01")
    check("select_node 被拦", r.get("error") == "AUTH_REQUIRED", str(r)[:80])
    st = api.account_state()
    check("account_state 仍可调且未解锁", st.get("unlocked") is False, str(st)[:80])

    print("[2] 参数缺失")
    r = api.account_login("", "")
    check("空邮箱密码 -> bad_request", r.get("code") == "bad_request", str(r)[:80])

    print("[3] 密码错误")
    r = api.account_login("ace@quchen.local", "wrong")
    check("bad_credentials", r.get("code") == "bad_credentials" and r.get("status") == 401, str(r)[:80])
    check("未登录状态未变", api.bootstrap().get("error") == "AUTH_REQUIRED")

    print("[4] 登录成功")
    r = api.account_login("ace@quchen.local", "RightPass1!")
    check("login ok", r.get("ok") is True, str(r)[:120])
    st = api.account_state()
    check("已解锁", st.get("unlocked") is True and st.get("email") == "ace@quchen.local", str(st)[:120])
    check("bootstrap 放行", "state" in api.bootstrap(), str(api.bootstrap())[:80])
    check("connect 放行", api.connect().get("ok") is True)

    print("[5] 会话文件")
    with open(session_file, "r", encoding="utf-8") as f:
        raw = json.load(f)
    for key in ("app", "email", "role", "access_token", "refresh_token", "expires_at", "issued_at", "last_verified", "revoked"):
        check(f"字段 {key}", key in raw)
    check("app=vpn", raw.get("app") == "vpn")
    check("不存密码", "password" not in raw)

    print("[6] 退出登录后重新被拦")
    api.account_logout()
    check("已退出", api.account_state().get("unlocked") is False)
    check("connect 再次被拦", api.connect().get("error") == "AUTH_REQUIRED")

    print("[7] 开关关闭直通")
    os.environ["QUCHEN_ACCOUNT_GATE_DISABLED"] = "1"
    api2 = Api(StubService())
    _install_account_guard(api2)
    check("disabled 时 connect 直通", api2.connect().get("ok") is True)
    check("reason=disabled", api2.account_state().get("why") == "disabled", str(api2.account_state())[:80])
    os.environ.pop("QUCHEN_ACCOUNT_GATE_DISABLED", None)

    server.shutdown()
    print(f"\n{PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
