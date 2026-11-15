"""QuChen 账号登录墙（客户端侧门禁）。

一套逻辑，四端共用（AI / Radio / VPN / Debug 各放一份同实现，接口一致）：

  * 登录  -> POST {base}/api/auth/login   拿 access/refresh，落盘到本地会话文件
  * 续期  -> POST {base}/api/auth/refresh 轮换 refresh（每次成功后刷新 last_verified）
  * 门禁  -> ``Gate.unlocked()``：令牌有效 或 处于离线宽限期内（默认 30 天）
  * 退出  -> POST {base}/api/auth/logout  并清空本地会话文件

会话文件放在 ``%APPDATA%\\QuChen\\auth\\<app>.json``（POSIX: ``~/.config/QuChen/auth/<app>.json``），
只存令牌与邮箱，不存密码。账号服务不可达时按 30 天宽限放行，到期强制重新验证。

本模块只用标准库，零第三方依赖，便于四端各自打包。
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
import ssl
from urllib.parse import urlparse

# 自家服务（frp-any.com / natfrp.cloud / traesite.cn）使用自签证书，客户端放宽校验
_SELF_SUFFIXES = ("frp-any.com", "natfrp.cloud", "traesite.cn")


def _ssl_ctx(url):
    try:
        host = (urlparse(str(url)).hostname or "").lower()
    except Exception:
        return None
    if any(host == s or host.endswith("." + s) for s in _SELF_SUFFIXES):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None

from pathlib import Path

DEFAULT_BASE = os.environ.get("QUCHEN_AUTH_BASE", "https://frp-any.com:19549")
OFFLINE_GRACE_DAYS = 30
REFRESH_SKEW = 24 * 3600          # access 快到期时提前续


def session_dir() -> Path:
    if os.name == "nt":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "QuChen" / "auth"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "QuChen" / "auth"


class AuthError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


class Gate:
    """单个应用的登录门禁。线程安全，可被 HTTP 处理线程并发调用。"""

    def __init__(self, app: str, base_url: str | None = None, grace_days: int = OFFLINE_GRACE_DAYS,
                 session_file: Path | None = None, enabled: bool = True):
        self.app = app
        self.base_url = (base_url or os.environ.get("QUCHEN_AUTH_BASE") or DEFAULT_BASE).rstrip("/")
        self.grace_days = grace_days
        self.enabled = enabled
        self.path = Path(session_file) if session_file else session_dir() / f"{app}.json"
        self._lock = threading.RLock()
        self._state = self._load()

    # ---------- 会话文件 ----------
    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, state: dict) -> None:
        self._state = state
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass                                  # 只读盘时不致命：本次进程内仍按内存状态放行

    def state(self) -> dict:
        with self._lock:
            return dict(self._state)

    # ---------- 判定 ----------
    def unlocked(self) -> bool:
        """已登录（在线校验过或仍在离线宽限期内）返回 True。"""
        if not self.enabled:
            return True
        with self._lock:
            st = self._state
            if not st.get("refresh_token"):
                return False
            if st.get("revoked"):
                return False
            verified = float(st.get("last_verified") or 0)
            if verified and (time.time() - verified) <= self.grace_days * 86400:
                return True
            # 从没校验成功过，但手里有还没到期的 refresh：按首次登录时间算宽限
            issued = float(st.get("issued_at") or 0)
            return bool(issued and (time.time() - issued) <= self.grace_days * 86400)

    def reason(self) -> dict:
        """给登录页显示的状态：为什么没放行。"""
        with self._lock:
            st = self._state
            if not self.enabled:
                return {"unlocked": True, "why": "disabled"}
            if not st.get("refresh_token"):
                return {"unlocked": False, "why": "no_session"}
            if st.get("revoked"):
                return {"unlocked": False, "why": "revoked"}
            if self.unlocked():
                age = int((time.time() - float(st.get("last_verified") or st.get("issued_at") or 0)) / 86400)
                return {"unlocked": True, "why": "session", "email": st.get("email"), "offline_days": age}
            return {"unlocked": False, "why": "grace_expired", "email": st.get("email")}

    # ---------- 联网动作 ----------
    def _request(self, path: str, payload: dict, token: str | None = None) -> dict:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=12, context=_ssl_ctx(req.full_url)) as res:
                return json.loads(res.read().decode() or "{}")
        except urllib.error.HTTPError as err:
            raw = err.read().decode(errors="replace")
            try:
                data = json.loads(raw or "{}")
            except ValueError:
                data = {}
            raise AuthError(err.code, data.get("code") or "http_error",
                            data.get("message") or f"账号服务返回 {err.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise AuthError(0, "unreachable", f"账号服务不可达：{err}") from None

    def login(self, email: str, password: str, device_name: str | None = None) -> dict:
        payload = {"email": email, "password": password,
                   "device_id": self.app, "device_name": device_name or self.app}
        data = self._request("/api/auth/login", payload)
        now = time.time()
        state = {
            "app": self.app,
            "email": (data.get("user") or {}).get("email") or email,
            "role": (data.get("user") or {}).get("role"),
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "expires_at": now + float(data.get("expires_in") or 1800),
            "issued_at": now,
            "last_verified": now,
            "revoked": False,
        }
        self._save(state)
        return state

    def refresh(self) -> dict:
        with self._lock:
            rt = self._state.get("refresh_token")
        if not rt:
            raise AuthError(401, "no_session", "尚未登录")
        data = self._request("/api/auth/refresh", {"refresh_token": rt})
        with self._lock:
            state = dict(self._state)
            state.update({
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token") or rt,
                "expires_at": time.time() + float(data.get("expires_in") or 1800),
                "last_verified": time.time(),
                "revoked": False,
            })
            self._save(state)
            return state

    def ensure_fresh(self) -> bool:
        """access 快过期就续一次；网络不通时返回 False 但不清会话（离线宽限内继续可用）。"""
        with self._lock:
            st = dict(self._state)
        if not st.get("refresh_token"):
            return False
        if float(st.get("expires_at") or 0) - time.time() > REFRESH_SKEW:
            return True
        try:
            self.refresh()
            return True
        except AuthError as err:
            if err.status in (401, 403):
                with self._lock:
                    st = dict(self._state)
                    st["revoked"] = True
                    self._save(st)
            return False

    def logout(self) -> None:
        with self._lock:
            st = dict(self._state)
        if st.get("refresh_token"):
            try:
                self._request("/api/auth/logout", {"refresh_token": st["refresh_token"]},
                              token=st.get("access_token"))
            except AuthError:
                pass
        self._save({})

    def entitlement(self) -> dict:
        """客户端可用的功能位（服务端 /api/auth/entitlement）。失败返回空 dict，不阻断离线使用。"""
        with self._lock:
            st = dict(self._state)
        if not st.get("access_token"):
            return {}
        try:
            req = urllib.request.Request(f"{self.base_url}/api/auth/entitlement",
                                         headers={"Authorization": f"Bearer {st['access_token']}"})
            with urllib.request.urlopen(req, timeout=8, context=_ssl_ctx(req.full_url)) as res:
                return json.loads(res.read().decode() or "{}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
            return {}
