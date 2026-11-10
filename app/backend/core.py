"""mihomo 内核进程管理与 REST API 封装。"""
from __future__ import annotations

import json
import os
import random
import socket
import string
import subprocess
import threading
import time
from collections import deque

import requests
import yaml

APP_NAME = "QuChen"
MIXED_PORT = 7890
CTRL_PORT = 9090
API_HOST = "127.0.0.1"


def free_port(default: int) -> int:
    s = socket.socket()
    try:
        s.bind((API_HOST, default))
        s.close()
        return default
    except OSError:
        s.close()
        return 0


def pick_port(start=MIXED_PORT, span=400) -> int:
    for p in range(start, start + span):
        if free_port(p):
            return p
    return random.randint(20000, 60000)


def rand_secret(n=20) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


class SafeDumper(yaml.SafeDumper):
    """所有字符串强制加双引号，避免 YAML 1.2 把 "08"/"on"/"no" 之类误解析成数字或布尔。"""


def _str_repr(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")


SafeDumper.add_representer(str, _str_repr)


def dump_yaml(cfg: dict) -> str:
    return yaml.dump(cfg, Dumper=SafeDumper, allow_unicode=True, sort_keys=False,
                     default_flow_style=False, width=100000)


# ---------------------------------------------------------------- 配置生成
GROUP_SELECT = "🚀 节点选择"
GROUP_AUTO = "♻️ 自动选择"
GROUP_FALLBACK = "🔯 故障转移"

BASE_RULES = [
    # 局域网 / 保留地址直连
    "GEOIP,LAN,DIRECT,no-resolve",
    "GEOIP,PRIVATE,DIRECT,no-resolve",
    # 国内直连
    "GEOSITE,private,DIRECT",
    "GEOSITE,cn,DIRECT",
    "GEOIP,CN,DIRECT,no-resolve",
    # 需要代理的常见服务
    "GEOSITE,geolocation-!cn,🚀 节点选择",
    "MATCH,🚀 节点选择",
]


def build_config(proxies, *, mixed_port, secret, ctrl_port, mode="rule",
                 tun=False, dns_mode="fake-ip", home=None, extra_groups=None, compact_groups=False):
    names = [p["name"] for p in proxies]
    groups = [
        {"name": GROUP_SELECT, "type": "select", "proxies": [GROUP_AUTO, GROUP_FALLBACK] + names},
        {"name": GROUP_AUTO, "type": "url-test", "proxies": names,
         "url": "http://www.gstatic.com/generate_204", "interval": 300, "tolerance": 50, "lazy": True},
        {"name": GROUP_FALLBACK, "type": "fallback", "proxies": names,
         "url": "http://www.gstatic.com/generate_204", "interval": 300, "lazy": True},
    ]
    if compact_groups:
        # 大批量测速时只保留必要分组，减少调度压力
        groups = [
            {"name": GROUP_SELECT, "type": "select", "proxies": names},
            {"name": GROUP_AUTO, "type": "url-test", "proxies": names,
             "url": "http://www.gstatic.com/generate_204", "interval": 7200,
             "tolerance": 50, "lazy": True},
        ]
    if extra_groups:
        groups.extend(extra_groups)
    rules = list(BASE_RULES)
    if mode == "global":
        pass  # mihomo 的 global 模式在 /configs 里切换，规则表仍保留
    cfg = {
        "mixed-port": mixed_port,
        "allow-lan": False,
        "bind-address": "*",
        "mode": "rule" if mode != "global" else "global",
        "log-level": "info",
        "ipv6": True,
        "external-controller": f"{API_HOST}:{ctrl_port}",
        "secret": secret,
        "unified-delay": True,
        "tcp-concurrent": True,
        "find-process-mode": "off",
        "profile": {"store-selected": True, "store-fake-ip": True},
        "sniffer": {
            "enable": True,
            "sniff": {
                "HTTP": {"ports": [80, "8080-8880"], "override-destination": True},
                "TLS":  {"ports": [443, 8443]},
                "QUIC": {"ports": [443, 8443]},
            },
            "skip-domain": ["+.push.apple.com"],
        },
        "dns": {
            "enable": True,
            "ipv6": True,
            "listen": f"{API_HOST}:0",
            "prefer-h3": False,
            "use-hosts": True,
            "use-system-hosts": True,
            "respect-rules": True,
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "fake-ip-filter": [
                "*.lan", "*.local", "*.localdomain", "*.*.*.local",
                "localhost.ptlogin2.qq.com", "localhost.*.weixin.qq.com",
                "+.msftconnecttest.com", "+.msftncsi.com", "stun.*", "+.stun.*",
                "time.*.com", "ntp.*.com", "+.pool.ntp.org", "localhost.work.weixin.qq.com",
            ],
            "default-nameserver": ["223.5.5.5", "119.29.29.29"],
            "nameserver": ["https://doh.pub/dns-query", "https://dns.alidns.com/dns-query"],
            "proxy-server-nameserver": ["https://doh.pub/dns-query", "223.5.5.5"],
            "nameserver-policy": {
                "geosite:cn,private": ["https://doh.pub/dns-query", "223.5.5.5"],
                "geosite:geolocation-!cn": ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"],
            },
        },
        "proxies": proxies,
        "proxy-groups": groups,
        "rules": rules,
    }
    if tun:
        cfg["tun"] = {
            "enable": True,
            "stack": "mixed",
            "dns-hijack": ["any:53", "tcp://any:53"],
            "auto-route": True,
            "auto-detect-interface": True,
            "mtu": 9000,
        }
    if home:
        cfg["geodata-mode"] = False
        cfg["geo-auto-update"] = False
    return cfg


# ---------------------------------------------------------------- 内核管理
class Core:
    def __init__(self, exe: str, home: str, log_cb=None):
        self.exe = exe
        self.home = home
        self.proc: subprocess.Popen | None = None
        self.mixed_port = 0
        self.ctrl_port = 0
        self.secret = rand_secret()
        self.cfg = None
        self.logs = deque(maxlen=600)
        self._log_thread = None
        self._traffic_thread = None
        self.up = 0
        self.down = 0
        self.upload_total = 0
        self.download_total = 0
        self.connected = False
        self.started_at = 0
        self.log_cb = log_cb
        self._stop_flag = threading.Event()

    # -------------------------------------------------- 构建配置
    def build(self, proxies, mode="rule", tun=False, prefer_port=None,
              extra_groups=None, compact_groups=False):
        self._proxies = proxies
        self._opts = dict(mode=mode, tun=tun, prefer_port=prefer_port,
                          extra_groups=extra_groups, compact_groups=compact_groups)
        self._apply_ports(pick_port(prefer_port or MIXED_PORT), self._random_port())
        return self.cfg

    def _apply_ports(self, mixed, ctrl):
        o = getattr(self, "_opts", {})
        self.mixed_port = mixed
        self.ctrl_port = ctrl
        self.secret = rand_secret(24)
        self.cfg = build_config(
            self._proxies, mixed_port=mixed, secret=self.secret, ctrl_port=ctrl,
            mode=o.get("mode", "rule"), tun=o.get("tun", False), home=self.home,
            extra_groups=o.get("extra_groups"), compact_groups=o.get("compact_groups", False),
        )

    @staticmethod
    def _random_port() -> int:
        for _ in range(60):
            p = random.randint(20000, 60000)
            if free_port(p):
                return p
        return random.randint(20000, 60000)


    # -------------------------------------------------- 日志
    def log(self, msg: str):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        self.logs.append(line)
        if self.log_cb:
            try:
                self.log_cb(line)
            except Exception:
                pass

    def _pipe_logs(self):
        if not self.proc or not self.proc.stdout:
            return
        for raw in iter(self.proc.stdout.readline, b""):
            try:
                line = raw.decode("utf-8", "ignore").rstrip()
            except Exception:
                continue
            if line:
                self.log(line)

    def _pipe_stderr(self):
        if not self.proc or not self.proc.stderr:
            return
        for raw in iter(self.proc.stderr.readline, b""):
            try:
                line = raw.decode("utf-8", "ignore").rstrip()
            except Exception:
                continue
            if line:
                self.log(line)

    # -------------------------------------------------- API
    @property
    def api(self) -> str:
        return f"http://{API_HOST}:{self.ctrl_port}"

    def _h(self):
        return {"Authorization": f"Bearer {self.secret}"}

    def request(self, method, path, **kw):
        url = self.api + path
        kw.setdefault("timeout", 4)
        kw.setdefault("headers", self._h())
        # 本机控制口不能走系统/环境里的代理：环境变量里一个失效的 HTTP_PROXY 会让控制面全部超时
        sess = requests.Session()
        sess.trust_env = False
        try:
            return sess.request(method, url, **kw)
        finally:
            sess.close()

    def version(self, timeout=4):
        try:
            return self.request("GET", "/version", timeout=timeout).json()
        except Exception:
            return {}

    def proxies(self):
        try:
            return self.request("GET", "/proxies").json().get("proxies", {})
        except Exception:
            return {}

    def delay(self, name, timeout=3000, url="http://www.gstatic.com/generate_204"):
        try:
            r = self.request("GET", f"/proxies/{requests.utils.quote(name, safe='')}/delay",
                             params={"timeout": timeout, "url": url}, timeout=timeout / 1000 + 3)
            return int(r.json().get("delay", 0)) or None
        except Exception:
            return None

    def group_delay(self, group, timeout=5000, url="http://www.gstatic.com/generate_204"):
        try:
            r = self.request("GET", f"/group/{requests.utils.quote(group, safe='')}/delay",
                             params={"timeout": timeout, "url": url}, timeout=timeout / 1000 + 10)
            return r.json()
        except Exception:
            return {}

    def select(self, group, name):
        r = self.request("PUT", f"/proxies/{requests.utils.quote(group, safe='')}",
                         json={"name": name})
        return r.status_code in (200, 204)

    def current(self, group=GROUP_SELECT):
        p = self.proxies().get(group) or {}
        return p.get("now", "")

    def set_mode(self, mode):
        r = self.request("PATCH", "/configs", json={"mode": mode})
        return r.status_code in (200, 204)

    def connections(self):
        try:
            return self.request("GET", "/connections").json()
        except Exception:
            return {}

    # -------------------------------------------------- 流量线程
    def _traffic_loop(self, stop: threading.Event):
        sess = requests.Session()
        sess.trust_env = False
        sess.headers.update(self._h())
        while not stop.is_set():
            try:
                with sess.get(f"{self.api}/traffic", stream=True, timeout=10) as r:
                    for line in r.iter_lines():
                        if stop.is_set():
                            break
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except Exception:
                            continue
                        self.up = int(d.get("up", 0))
                        self.down = int(d.get("down", 0))
                        self.upload_total += self.up
                        self.download_total += self.down
            except Exception:
                time.sleep(1.0)

    # -------------------------------------------------- 生命周期
    def start(self, cfg: dict | None = None):
        """启动内核；若控制口/混合端口被其他实例占用（表现为 401 或无响应）则换端口重试。"""
        self.stop()
        attempts = 3
        for attempt in range(attempts):
            cfg = cfg or self.cfg
            if cfg is None:
                raise RuntimeError("尚未构建配置")
            os.makedirs(self.home, exist_ok=True)
            cfg_path = os.path.join(self.home, "config.yaml")
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(dump_yaml(cfg))

            env = dict(os.environ)
            env["MIHOMO_HOME"] = self.home
            self.log(f"[core] 启动内核 {os.path.basename(self.exe)} 端口 {self.mixed_port} 控制台 {self.ctrl_port}")
            creation = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            self.proc = subprocess.Popen(
                [self.exe, "-d", self.home, "-f", cfg_path],
                cwd=self.home, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, creationflags=creation,
            )
            self._stop_flag = threading.Event()
            self._log_thread = threading.Thread(target=self._pipe_logs, daemon=True)
            self._log_thread.start()
            threading.Thread(target=self._pipe_stderr, daemon=True).start()

            ok = False
            for _ in range(24):
                time.sleep(0.25)
                if self.proc.poll() is not None:
                    break
                if self.version(timeout=0.8):
                    ok = True
                    break
            if ok:
                break
            self.stop()
            if attempt == attempts - 1:
                self.log("[core] 内核启动失败")
                raise RuntimeError("内核启动失败，请查看日志")
            # 换一组随机端口再试，避开被其他实例 SO_REUSEADDR 抢占的端口
            self._apply_ports(self._random_port(), self._random_port())
            cfg = self.cfg
            self.log(f"[core] 端口不可用，改用 {self.mixed_port} / {self.ctrl_port} 重试")

        self.connected = True
        self.started_at = time.time()
        self.upload_total = 0
        self.download_total = 0
        self._traffic_thread = threading.Thread(target=self._traffic_loop, args=(self._stop_flag,), daemon=True)
        self._traffic_thread.start()
        self.log(f"[core] 内核就绪 {self.version().get('version', '')}")
        return True

    def write_overrides(self, cfg):
        """把内嵌的 geo 文件链接到 home，避免内核联网下载。"""
        pass

    def stop(self):
        self._stop_flag.set()
        self.connected = False
        self.up = self.down = 0
        if self.proc and self.proc.poll() is None:
            try:
                self.request("PUT", "/configs", json={"mode": "direct"}, timeout=1)
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        for t in (self._log_thread, self._traffic_thread):
            if t and t.is_alive():
                t.join(timeout=2)
        self._log_thread = None
        self._traffic_thread = None

    def alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)
