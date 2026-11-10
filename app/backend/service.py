"""应用业务层：设置、节点池、内核生命周期、系统代理、诊断。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time

import requests

from . import core as C
from . import nodes as N
from . import pool as P
from . import subs
from . import sysproxy
from . import updater

APP_TITLE = "QuChen VPN"
APP_VER = "1.0.8"
UPDATE_REPO = "quchenace/QuChen-VPN"


def _base_dir() -> str:
    """定位包含 runtime/ 与 web/ 的资源根目录（源码运行 / PyInstaller 打包都适用）。"""
    cands = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        cands += [exe_dir, getattr(sys, "_MEIPASS", "") or exe_dir]
    here = os.path.dirname(os.path.abspath(__file__))
    cands += [os.path.dirname(os.path.dirname(here)), os.path.dirname(here), here]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "runtime", "core")):
            return c
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "web")):
            return c
    return cands[0] or here


class Service:
    def __init__(self, log_cb=None):
        self.base = _base_dir()
        self.core_dir = os.path.join(self.base, "runtime", "core")
        here = os.path.dirname(os.path.abspath(__file__))
        asset_cands = [
            os.path.join(self.base, "assets"),
            os.path.join(os.path.dirname(here), "assets"),
            os.path.join(getattr(sys, "_MEIPASS", "") or "", "assets"),
        ]
        self.assets = next((p for p in asset_cands if os.path.isdir(p)), asset_cands[0])
        self.home = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "QuChenVPN")
        os.makedirs(self.home, exist_ok=True)
        self.settings_path = os.path.join(self.home, "settings.json")
        self.pool_path = os.path.join(self.home, "pool.json")
        self.stats_path = os.path.join(self.home, "stats.json")
        self.core_exe = os.path.join(self.core_dir, "mihomo.exe")
        self.logs: list[str] = []
        self._lock = threading.RLock()
        self.settings = self._load_settings()
        self.core = C.Core(self.core_exe, self.home, log_cb=self._log)
        self.pool = self._load_pool()
        self.task = {"running": False, "kind": "", "msg": "", "progress": 0}
        self.update = {"ok": True, "checking": False, "downloading": False, "has_update": False,
                       "latest": "", "current": APP_VER, "msg": "尚未检查", "progress": 0}
        self.stats = self._load_stats()
        self._ensure_geo()
        self._last_stat = time.time()
        # 本次内核会话上一次读到的累计字节：tick_stats 只把增量记进当天/总计，内核重启（计数归零）时自动重置
        self._last_core_up = 0
        self._last_core_down = 0
        self._last_save = 0.0

    # ------------------------------------------------------------ 基础
    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        line = msg if msg.startswith(ts) else f"{ts} {msg}"
        with self._lock:
            self.logs.append(line)
            if len(self.logs) > 1500:
                del self.logs[:500]

    def _load_settings(self) -> dict:
        default = {
            "mode": "rule",              # rule | global
            "sys_proxy": True,
            "tun": False,
            "node": "",
            "auto_connect": False,
            "auto_start": False,
            "theme": "light",
            "port": C.MIXED_PORT,
            "close_to_tray": True,
            "update_token": "",          # 私有仓库拉取 Release 用（可选）
        }
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                default.update(json.load(f) or {})
        except Exception:
            pass
        return default

    def save_settings(self):
        with self._lock:
            tmp = self.settings_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.settings_path)

    def _load_pool(self) -> dict:
        data = P.load(self.pool_path)
        if not data.get("nodes"):
            seed = os.path.join(self.assets, "seed_pool.json")
            data = P.load(seed)
            if data.get("nodes"):
                P.save(self.pool_path, data["nodes"], meta=data.get("meta"))
                self._log(f"[pool] 载入内置线路 {data['count']} 条")
        return data

    def _load_stats(self) -> dict:
        try:
            with open(self.stats_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"days": {}, "total_up": 0, "total_down": 0}

    def save_stats(self):
        try:
            tmp = self.stats_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False)
            os.replace(tmp, self.stats_path)
        except Exception:
            pass

    def _ensure_geo(self):
        import shutil
        for f in ("GEOIP.metadb", "GEOSITE.dat", "ASN.mmdb", "geoip.metadb"):
            src = os.path.join(self.core_dir, f)
            dst = os.path.join(self.home, f)
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    shutil.copy(src, dst)
                except Exception:
                    pass

    # ------------------------------------------------------------ 节点
    def nodes(self):
        return self.pool.get("nodes", [])

    def node_by_name(self, name):
        for n in self.nodes():
            if n.get("name") == name:
                return n
        return None

    # ------------------------------------------------------------ 状态
    def state(self) -> dict:
        c = self.core
        alive = c.alive()
        uptime = int(time.time() - c.started_at) if alive and c.started_at else 0
        cur = ""
        if alive:
            try:
                cur = c.current()
            except Exception:
                cur = ""
        node = self.node_by_name(self.settings.get("node") or "") or {}
        return {
            "version": APP_VER,
            "connected": alive,
            "node": cur or self.settings.get("node", ""),
            "node_country": node.get("_country") or N.guess_country(node.get("name", "")),
            "node_type": node.get("type", ""),
            "node_count": len(self.nodes()),
            "pool_updated": self.pool.get("updated_text", ""),
            "uptime": uptime,
            "up": c.up if alive else 0,
            "down": c.down if alive else 0,
            "total_up": c.upload_total if alive else 0,
            "total_down": c.download_total if alive else 0,
            "mode": self.settings.get("mode", "rule"),
            "sys_proxy": bool(alive and c.mixed_port and
                              sysproxy.proxy_effective(f"127.0.0.1:{c.mixed_port}")),
            "sys_proxy_server": sysproxy.get_proxy().get("server", ""),
            "sys_proxy_setting": bool(self.settings.get("sys_proxy", True)),
            "tun": bool(self.settings.get("tun")),
            "mixed_port": c.mixed_port if alive else self.settings.get("port", C.MIXED_PORT),
            "ctrl_port": c.ctrl_port if alive else 0,
            "admin": sysproxy.is_admin(),
            "task": dict(self.task),
            "logs": self.logs[-200:],
            "theme": self.settings.get("theme", "light"),
            "auto_start": sysproxy.get_autostart(),
            "auto_connect": bool(self.settings.get("auto_connect")),
            "sources": self.pool.get("meta", {}).get("sources", []),
            "harvested": self.pool.get("meta", {}).get("harvested", 0),
            "stats_days": sorted(self.stats.get("days", {}).items(), reverse=True)[:14],
            "stat_total": {"up": self.stats.get("total_up", 0), "down": self.stats.get("total_down", 0)},
            "update": dict(self.update),
            "update_token_set": bool(self.settings.get("update_token")),
            "repo": UPDATE_REPO,
        }

    def log_list(self):
        return self.logs[-400:]

    # ------------------------------------------------------------ 连接
    def connect(self, node_name: str | None = None) -> dict:
        with self._lock:
            if self.core.alive():
                # 内核还在跑不代表代理真的生效：上次异常退出、用户手动关了系统代理、
                # 或系统启用了 PAC 都会造成"显示已连接但没走代理"。这里必须重新核对。
                if node_name:
                    self.settings["node"] = node_name
                    if self.core.select(C.GROUP_SELECT, node_name):
                        self._log(f"[core] 已切换线路 {node_name}")
                fixed = self._ensure_sysproxy()
                self.save_settings()
                if not fixed:
                    return {"ok": False, "msg": "内核在运行，但系统代理接管失败",
                            "node": self.core.current()}
                ok_exit, detail = self._verify_exit()
                msg = "已连接" if ok_exit else f"已连接，但出口未连通（{detail}）"
                return {"ok": ok_exit, "msg": msg, "node": self.core.current()}
            if not self.nodes():
                return {"ok": False, "msg": "节点池为空，请先更新线路"}
            if node_name:
                self.settings["node"] = node_name
            self.task = {"running": True, "kind": "connect", "msg": "正在启动内核…", "progress": 10}
            try:
                want_tun = bool(self.settings.get("tun"))
                if want_tun and not sysproxy.is_admin():
                    want_tun = False
                    self._log("[core] 当前未以管理员身份运行，本次改用系统代理模式（TUN 已跳过）")
                self.core.build(
                    self.nodes(), mode=self.settings.get("mode", "rule"),
                    tun=want_tun, prefer_port=self.settings.get("port"),
                )
                self.task["msg"] = "内核启动中…"
                self.task["progress"] = 45
                self.core.start()
                self.task["msg"] = "等待内核端口就绪…"
                if not self._wait_mixed(12.0):
                    self._log("[core] 混合端口未就绪，重启内核一次")
                    try:
                        self.core.stop()
                        time.sleep(0.6)
                        self.core.start()
                    except Exception as e:
                        self._log(f"[core] 内核重启异常 {type(e).__name__}")
                    if not self._wait_mixed(10.0):
                        self._log("[core] 混合端口仍未就绪，代理可能无法使用")
                self.task["progress"] = 70
                target = self.settings.get("node")
                if target and self.node_by_name(target) and self.node_by_name(target).get("delay"):
                    ok = self.core.select(C.GROUP_SELECT, target)
                    if not ok:
                        self._log(f"[core] 节点选择失败 {target}")
                else:
                    # 优先选已知延迟最低的节点，否则现场快速探测
                    best = self._fastest()
                    if best:
                        self.core.select(C.GROUP_SELECT, best)
                        self.settings["node"] = best
                    else:
                        self.task["msg"] = "正在探测可用线路…"
                        self.task["progress"] = 78
                        best = self._quick_pick()
                        if best:
                            self.core.select(C.GROUP_SELECT, best)
                            self.settings["node"] = best
                            self._log(f"[core] 探测到可用线路 {best}")
                        else:
                            self.core.select(C.GROUP_SELECT, C.GROUP_AUTO)
                            self._log("[core] 暂未探到可用线路，交给自动选择组")
                proxy_ok = self._ensure_sysproxy()
                if self.settings.get("sys_proxy", True) and not proxy_ok:
                    self._log("[sys] 系统代理接管失败：可能被安全软件或组策略锁定")
                self.settings["port"] = self.core.mixed_port
                self.save_settings()

                self.task["msg"] = "正在校验出口连通性…"
                self.task["progress"] = 90
                ok_exit, detail = self._verify_exit()
                if not ok_exit:
                    self._log(f"[core] 出口校验失败（{detail}），尝试换线")
                    alt = self._quick_pick(exclude=self.settings.get("node"))
                    if alt:
                        if self.core.select(C.GROUP_SELECT, alt):
                            self.settings["node"] = alt
                            self.save_settings()
                            ok_exit, detail = self._verify_exit()
                            self._log(f"[core] 切换到 {alt} 后{'校验通过' if ok_exit else '仍不通'}")

                if not ok_exit:
                    # 出口不通就不要继续占着系统代理，否则用户会觉得“连上了但整台电脑没网”
                    try:
                        sysproxy.set_proxy(False, f"127.0.0.1:{self.core.mixed_port}")
                        self._log("[sys] 出口不可用，已还原系统代理")
                    except Exception:
                        pass
                    proxy_ok = False
                if ok_exit and proxy_ok:
                    msg = "连接成功"
                elif ok_exit and not proxy_ok:
                    msg = "内核已就绪，但系统代理未接管"
                elif not ok_exit:
                    msg = f"已启动内核，但出口未连通（{detail}）"
                else:
                    msg = "连接成功"
                self.task = {"running": False, "kind": "connect", "msg": msg,
                             "progress": 100 if ok_exit else 85}
                self._log(f"[core] {msg}")
                return {"ok": bool(ok_exit), "msg": msg, "node": self.core.current(),
                        "sys_proxy": proxy_ok, "verified": ok_exit}
            except Exception as e:
                self.task = {"running": False, "kind": "connect", "msg": f"连接失败: {e}", "progress": 0}
                self._log(f"[core] 连接失败 {e}")
                try:
                    self.core.stop()
                except Exception:
                    pass
                return {"ok": False, "msg": f"连接失败: {e}"}

    def _fastest(self):
        nodes = [n for n in self.nodes() if isinstance(n.get("delay"), int)]
        if not nodes:
            return ""
        nodes.sort(key=lambda n: n.get("delay", 9999))
        return nodes[0]["name"]

    def _save_delays(self, mapping):
        for n in self.nodes():
            if n["name"] in mapping:
                n["delay"] = mapping[n["name"]] or None

    def _delay_many(self, names, workers=48, timeout=4000, progress=None, core=None):
        """并发逐节点测速，返回 {name: delay}。"""
        import concurrent.futures as cf
        core = core or self.core
        out = {}
        total = len(names) or 1
        done = 0
        cursor = 0
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            while cursor < len(names):
                batch = names[cursor:cursor + workers]
                cursor += len(batch)
                futs = {ex.submit(core.delay, n, timeout): n for n in batch}
                for f in cf.as_completed(futs):
                    try:
                        d = f.result()
                    except Exception:
                        d = None
                    if d:
                        out[futs[f]] = int(d)
                    done += 1
                if progress:
                    progress(done, total)
        return out

    def _quick_pick(self, limit=180, timeout=3500, exclude: str = ""):
        """没有已测速节点时，快速探测前若干候选，返回第一个可用的。"""
        if not self.core.alive():
            return ""
        nodes = self.nodes()
        prefer = [n for n in nodes if n.get("type") not in ("http", "socks5")] + \
                 [n for n in nodes if n.get("type") in ("http", "socks5")]
        names = [n["name"] for n in prefer[:limit] if n["name"] != exclude]
        import concurrent.futures as cf
        for i in range(0, len(names), 36):
            batch = names[i:i + 36]
            with cf.ThreadPoolExecutor(max_workers=36) as ex:
                futs = {ex.submit(self.core.delay, n, timeout): n for n in batch}
                for f in cf.as_completed(futs):
                    try:
                        d = f.result()
                    except Exception:
                        d = None
                    if d:
                        self._save_delays({futs[f]: d})
                        return futs[f]
        return ""

    def _wait_mixed(self, timeout=12.0) -> bool:
        """等待内核的混合代理端口真正进入监听状态。"""
        port = self.core.mixed_port
        if not port:
            return False
        end = time.time() + timeout
        while time.time() < end:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                    return True
            except OSError:
                if not self.core.alive():
                    return False
                time.sleep(0.25)
        return False

    # ------------------------------------------------------------ 代理生效校验
    def _ensure_sysproxy(self) -> bool:
        """确保系统代理指向当前内核端口；返回是否真正生效。"""
        if not self.settings.get("sys_proxy", True):
            return True
        port = self.core.mixed_port
        if not port:
            return False
        server = f"127.0.0.1:{port}"
        if sysproxy.proxy_effective(server):
            return True
        ok = sysproxy.set_proxy(True, server)
        self._log(f"[sys] 系统代理{'已接管 ' if ok else '接管失败 '}{server}")
        return ok

    def _verify_exit(self, timeout=8, rounds=2) -> tuple:
        """通过本地混合端口做出口探测，判断代理是否真的能用（多轮重试）。"""
        port = self.core.mixed_port
        if not port:
            return False, "内核端口未知"
        px = {"http": f"http://127.0.0.1:{port}", "https": f"http://127.0.0.1:{port}"}
        last = ""
        for rnd in range(max(1, rounds)):
            ok, detail = self._verify_once(px, timeout)
            if ok:
                return True, detail
            last = detail
            if rnd + 1 < rounds:
                time.sleep(1.0)
        return False, last or "无响应"

    def _verify_once(self, px, timeout=8) -> tuple:
        last = ""
        sess = requests.Session()
        sess.trust_env = False          # 只用内核端口，别被系统里的坏代理干扰
        for url in ("https://www.gstatic.com/generate_204",
                    "http://connectivitycheck.platform.hicloud.com/generate_204",
                    "https://cp.cloudflare.com/generate_204"):
            try:
                r = sess.get(url, proxies=px, timeout=timeout, allow_redirects=False)
                if r.status_code in (200, 204):
                    return True, f"HTTP {r.status_code}"
                last = f"HTTP {r.status_code}"
            except Exception as e:
                last = type(e).__name__
        return False, last or "无响应"

    def disconnect(self) -> dict:
        with self._lock:
            port = self.core.mixed_port
            try:
                # 先还原系统代理再停内核，否则端口信息丢失后无法判断是否为自身写入
                if self.settings.get("sys_proxy", True) or sysproxy.has_backup():
                    sysproxy.set_proxy(False, f"127.0.0.1:{port}" if port else "")
                    self._log("[sys] 系统代理已还原")
            except Exception:
                pass
            self.core.stop()
            self.task = {"running": False, "kind": "", "msg": "", "progress": 0}
            self._log("[core] 已断开")
            return {"ok": True}

    def toggle(self) -> dict:
        return self.disconnect() if self.core.alive() else self.connect()

    def set_mode(self, mode: str) -> dict:
        if mode not in ("rule", "global"):
            return {"ok": False}
        self.settings["mode"] = mode
        self.save_settings()
        if self.core.alive():
            self.core.set_mode(mode)
        return {"ok": True, "mode": mode}

    def set_sys_proxy(self, on: bool) -> dict:
        self.settings["sys_proxy"] = bool(on)
        self.save_settings()
        if self.core.alive():
            if on:
                ok = sysproxy.set_proxy(True, f"127.0.0.1:{self.core.mixed_port}")
                self._log(f"[sys] 系统代理{'已开启' if ok else '开启失败'}")
                return {"ok": ok, "msg": "" if ok else "系统代理写入失败，可能被安全软件拦截"}
            sysproxy.set_proxy(False, f"127.0.0.1:{self.core.mixed_port}")
            self._log("[sys] 系统代理已还原")
        elif not on:
            # 内核没在跑也要确保不留下我们写入的代理
            sysproxy.restore_proxy()
        return {"ok": True}

    def set_tun(self, on: bool) -> dict:
        self.settings["tun"] = bool(on)
        self.save_settings()
        if self.core.alive():
            self._log("[core] TUN 模式变更，需重连生效")
        return {"ok": True}

    def select_node(self, name: str) -> dict:
        node = self.node_by_name(name)
        if not node:
            return {"ok": False, "msg": "节点不存在"}
        self.settings["node"] = name
        self.save_settings()
        if self.core.alive():
            ok = self.core.select(C.GROUP_SELECT, name)
            self._log(f"[core] 切换线路 -> {name}")
            return {"ok": ok, "node": name}
        return {"ok": True, "node": name}

    def set_group(self, group: str, value: str) -> dict:
        if self.core.alive():
            return {"ok": self.core.select(group, value)}
        return {"ok": False}

    # ------------------------------------------------------------ 节点列表
    def node_list(self):
        out = []
        for n in self.nodes():
            out.append({
                "name": n.get("name", ""),
                "type": n.get("type", ""),
                "server": n.get("server", ""),
                "port": n.get("port", 0),
                "delay": n.get("delay", None),
                "country": n.get("_country") or N.guess_country(n.get("name", "")),
                "flag": N.FLAGS.get(n.get("_country") or N.guess_country(n.get("name", "")), "🌐"),
            })
        # 已测速且延迟低的排前面，未测速的排后面
        out.sort(key=lambda x: (0 if x["delay"] else 1, x["delay"] or 99999))
        return out

    def maybe_autotest(self):
        """节点池里未测速节点过多时，后台自动跑一轮测速（6 小时内只跑一次）。"""
        nodes = self.nodes()
        if not nodes or self.task.get("running"):
            return False
        verified = sum(1 for n in nodes if isinstance(n.get("delay"), int))
        if verified >= max(30, len(nodes) * 0.5):
            return False
        last = float(self.settings.get("last_autotest", 0) or 0)
        if time.time() - last < 6 * 3600:
            return False
        self.settings["last_autotest"] = time.time()
        self.save_settings()
        self._log("[speed] 节点池未测速较多，自动开始后台测速")
        self.test_speed()
        return True

    def test_speed(self, names=None):
        """后台测速：返回任务状态。"""
        if self.task.get("running"):
            return {"ok": False, "msg": "已有任务在运行"}
        self.task = {"running": True, "kind": "speed", "msg": "正在测速…", "progress": 5}

        def run():
            tmp = None
            try:
                targets = names or [n["name"] for n in self.nodes()]
                core = self.core
                if not self.core.alive():
                    self.task["msg"] = "启动临时内核…"
                    tmp = C.Core(self.core_exe, self.home, log_cb=lambda m: None)
                    tmp.build(self.nodes(), mode="rule", compact_groups=True)
                    tmp.start()
                    core = tmp

                def progress(done, total):
                    self.task["msg"] = f"测速中 {done}/{total}"
                    self.task["progress"] = min(95, int(done * 95 / max(total, 1)))

                res = self._delay_many(targets, workers=56, timeout=4000, progress=progress, core=core)
                self._save_delays(res)
                P.save(self.pool_path, self.nodes(), meta=self.pool.get("meta", {}))
                self.pool = P.load(self.pool_path)
                self.task = {"running": False, "kind": "speed", "msg": "测速完成", "progress": 100}
                self._log(f"[speed] 测速完成，可用 {len(res)} 条")
            except Exception as e:
                self.task = {"running": False, "kind": "speed", "msg": f"测速失败: {e}", "progress": 0}
                self._log(f"[speed] 失败 {e}")
            finally:
                if tmp is not None:
                    tmp.stop()

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def refresh(self):
        if self.task.get("running"):
            return {"ok": False, "msg": "已有任务在运行"}
        self.task = {"running": True, "kind": "refresh", "msg": "抓取订阅源…", "progress": 5}

        def step(msg):
            self.task["msg"] = msg
            self._log(msg)

        def run():
            was_connected = self.core.alive()
            try:
                # 国内直连 GitHub 经常被重置：先借现有线路做引导代理
                if not was_connected and self.nodes():
                    step("先连接现有线路以便抓取订阅…")
                    r = self.connect()
                    self.connect_ok = bool(r.get("ok"))
                    time.sleep(1.0)
                px = self._proxies()
                nodes_raw, report = subs.harvest(logger=step, proxies=px)
                if len(nodes_raw) < 50 and px:
                    step("代理抓取不足，改走直连…")
                    nodes_raw, report2 = subs.harvest(logger=step, proxies=None)
                    if len(nodes_raw) >= 50:
                        report = report2
                self.task["progress"] = 35
                step(f"合并 {len(nodes_raw)} 条线路")
                if len(nodes_raw) < 10:
                    raise RuntimeError("订阅源全部不可达，请检查网络")
                # 放宽同域名/同国家抽样上限：原来限制过紧，订阅里大量节点会被丢掉，
                # 造成"节点库显示不全"。
                cand = P.diversify(nodes_raw, limit=12000, per_country=900, per_host=30,
                                   prefer=["香港", "台湾", "日本", "新加坡", "美国", "韩国"],
                                   max_plain_ratio=0.35)
                step(f"抽样 {len(cand)} 条进入预筛")
                self.task["progress"] = 45
                if self.core.alive():
                    self.core.stop()
                    sysproxy.set_proxy(False, "")
                reach = P.tcp_prefilter(cand, logger=step)
                self.task["progress"] = 55
                alive = P.verify(self.core_exe, self.home, reach, timeout_ms=6000,
                                 keep=1800, logger=step, batch=400)
                self.task["progress"] = 85
                merged = P.merge_pool(alive, reach, total=2500, max_plain_ratio=0.42)
                clean = [{k: v for k, v in p.items() if not k.startswith("_")} for p in merged]
                if clean:
                    self.pool = P.save(self.pool_path, clean, meta={
                        "sources": report, "harvested": len(nodes_raw), "sampled": len(cand),
                        "reachable": len(reach), "cost": 0})
                else:
                    step("本轮没有测到可用线路，保留原有节点池")
                step(f"可用线路 {len(self.nodes())} 条")
                if was_connected or getattr(self, "connect_ok", False):
                    self.task["msg"] = "重新连接…"
                    best = self._fastest()
                    self.connect(best)
                self.task = {"running": False, "kind": "refresh", "msg": "线路更新完成", "progress": 100}
            except Exception as e:
                self.task = {"running": False, "kind": "refresh", "msg": f"更新失败: {e}", "progress": 0}
                self._log(f"[pool] 更新失败 {e}")

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    # ------------------------------------------------------------ 诊断
    def diagnose(self):
        items = []

        def add(name, ok, msg):
            items.append({"name": name, "ok": bool(ok), "msg": msg})

        alive = self.core.alive()
        add("内核进程", alive, "mihomo 运行中" if alive else "内核未启动")
        port = self.core.mixed_port if alive else 0
        if alive:
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=2)
                s.close()
                add("本地端口", True, f"127.0.0.1:{port} 可连接")
            except Exception:
                add("本地端口", False, "端口未监听")
            try:
                px = {"http": f"http://127.0.0.1:{port}", "https": f"http://127.0.0.1:{port}"}
                t0 = time.time()
                r = requests.get("https://www.gstatic.com/generate_204", proxies=px, timeout=8)
                add("出口连通", r.status_code in (200, 204),
                    f"HTTP {r.status_code} · {int((time.time() - t0) * 1000)}ms")
            except Exception as e:
                add("出口连通", False, f"请求失败 {type(e).__name__}")
            try:
                px = {"http": f"http://127.0.0.1:{port}", "https": f"http://127.0.0.1:{port}"}
                r = requests.get("https://www.google.com/generate_204", proxies=px, timeout=8)
                add("Google 204", r.status_code in (200, 204), f"HTTP {r.status_code}")
            except Exception as e:
                add("Google 204", False, f"{type(e).__name__}")
        else:
            add("本地端口", False, "内核未启动")
        p = sysproxy.get_proxy()
        if alive and p.get("pac"):
            add("系统代理", False, f"系统启用了 PAC 自动脚本（{p.get('pac')[:60]}），会覆盖手动代理")
        elif alive and port:
            ok = sysproxy.proxy_effective(f"127.0.0.1:{port}")
            add("系统代理", ok, (p.get("server") or "未设置") +
                ("（已指向本机）" if ok else "（未指向本机端口）"))
        else:
            add("系统代理", p.get("enable"), (p.get("server") or "未设置"))
        has_bk = sysproxy.has_backup()
        add("代理配置备份", has_bk, "接管前的系统代理已记录，断开时自动还原" if has_bk else "当前未接管系统代理")

        add("节点数量", len(self.nodes()) > 0, f"{len(self.nodes())} 条")
        return {"items": items}

    # ------------------------------------------------------------ 在线更新
    def _proxies(self):
        if self.core.alive() and self.core.mixed_port:
            p = f"http://127.0.0.1:{self.core.mixed_port}"
            return {"http": p, "https": p}
        return None

    def check_update(self, force: bool = False) -> dict:
        if self.update.get("checking"):
            return self.update
        self.update.update({"checking": True, "msg": "正在检查更新…"})
        try:
            # 先直连（GitHub API 直连失败时 updater 内部还会走镜像），
            # 仍失败且本地内核在跑时再借代理重试一次。
            token = (self.settings.get("update_token") or "").strip() or None
            res = updater.check(repo=UPDATE_REPO, current=APP_VER, proxies=None, token=token)
            if not res.get("ok"):
                px = self._proxies()
                if px:
                    res2 = updater.check(repo=UPDATE_REPO, current=APP_VER, proxies=px, token=token)
                    if res2.get("ok"):
                        res = res2
            res["checking"] = False
            res["checked_at"] = time.strftime("%H:%M:%S")
            # 合并而非整体覆盖：否则刚下载好的 ready/progress 会被清空，导致"更新页点不动"
            self.update.update(res)
            if res.get("ok"):
                self._log(f"[update] {res.get('msg')} (当前 {APP_VER} / 最新 {res.get('latest')})")
            else:
                self._log(f"[update] 检查失败：{res.get('msg')}")
        except Exception as e:
            self.update.update({"ok": False, "checking": False, "msg": f"检查失败: {e}"})
        return self.update

    def download_update(self) -> dict:
        if self.update.get("downloading"):
            return {"ok": False, "msg": "正在下载中"}
        url = self.update.get("asset_url")
        if not url:
            return {"ok": False, "msg": "没有可下载的更新包"}
        self.update["downloading"] = True
        self.update["progress"] = 0

        def run():
            try:
                up_dir = os.path.join(self.home, "update")
                os.makedirs(up_dir, exist_ok=True)
                # 先清掉上一次的残留包，避免旧包被当成新包安装
                for name in os.listdir(up_dir):
                    if name.lower().endswith((".zip", ".part", ".exe")):
                        try:
                            os.remove(os.path.join(up_dir, name))
                        except Exception:
                            pass
                dest = os.path.join(up_dir, self.update.get("asset_name") or "update.zip")
                self.update.update({"msg": "正在下载更新包…", "progress": 0})
                updater.download(url, dest,
                                 progress=lambda p: self.update.update({"progress": p}),
                                 proxies=None,
                                 token=(self.settings.get("update_token") or "").strip() or None,
                                 sha256=self.update.get("asset_digest") or "",
                                 expect_size=int(self.update.get("asset_size") or 0))
                self._log(f"[update] 下载完成 {dest}")
                self.update["downloading"] = False
                self.update["progress"] = 100
                self.update["ready"] = dest
                self.update["msg"] = "更新包已就绪，点击「重启并安装」"
            except Exception as e:
                self.update["downloading"] = False
                self.update["progress"] = 0
                self.update["ready"] = ""
                self.update["msg"] = f"下载失败: {e}"
                self._log(f"[update] 下载失败 {e}")

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def install_update(self) -> dict:
        pkg = self.update.get("ready")
        if not pkg or not os.path.exists(pkg):
            return {"ok": False, "msg": "更新包不存在，请重新下载"}
        if not pkg.lower().endswith(".zip"):
            return {"ok": False, "msg": "更新包格式异常，请重新下载"}
        exe = os.path.basename(sys.executable) if getattr(sys, "frozen", False) else "QuChenVPN.exe"
        try:
            # 替换前先释放系统代理并停内核，否则 mihomo 等文件被占用会导致覆盖失败
            try:
                self.disconnect()
            except Exception:
                pass
            try:
                self.core.stop()
            except Exception:
                pass
            updater.apply_update(pkg, exe_name=exe)
            self._log("[update] 已启动替换脚本（先清理旧文件再写入，失败自动回滚），程序即将退出")
            return {"ok": True}
        except Exception as e:
            self._log(f"[update] 安装失败 {e}")
            return {"ok": False, "msg": f"安装失败: {e}"}

    def update_info(self) -> dict:
        return dict(self.update)

    def set_update_token(self, token: str) -> dict:
        """保存 GitHub Token（仅本地存储，用于访问私有仓库的 Release）。"""
        token = (token or "").strip()
        self.settings["update_token"] = token
        self.save_settings()
        self._log("[update] 已保存仓库 Token" if token else "[update] 已清除仓库 Token")
        return {"ok": True, "msg": "已保存" if token else "已清除", "set": bool(token)}

    # ------------------------------------------------------------ 统计
    def tick_stats(self):
        """把本次内核会话新增的流量累加到当天与总计。

        内核的 upload_total/download_total 每次 start() 都从 0 开始，所以这里只记增量：
        旧写法 max(当天, 会话累计) 在第二次连接后会少记，而 state() 又把会话累计和当天相加，
        导致“本次流量”翻倍。增量法同时解决这两个问题。"""
        if not self.core.alive():
            self._last_core_up = self._last_core_down = 0
            return
        now = time.time()
        if now - self._last_stat < 5:
            return
        self._last_stat = now
        up, down = int(self.core.upload_total or 0), int(self.core.download_total or 0)
        if up < self._last_core_up or down < self._last_core_down:      # 内核重启：计数归零
            self._last_core_up = self._last_core_down = 0
        du, dd = max(0, up - self._last_core_up), max(0, down - self._last_core_down)
        self._last_core_up, self._last_core_down = up, down
        if not du and not dd:
            return
        day = time.strftime("%Y-%m-%d")
        d = self.stats.setdefault("days", {}).setdefault(day, {"up": 0, "down": 0})
        d["up"] = int(d.get("up", 0)) + du
        d["down"] = int(d.get("down", 0)) + dd
        self.stats["total_up"] = int(self.stats.get("total_up", 0)) + du
        self.stats["total_down"] = int(self.stats.get("total_down", 0)) + dd
        if now - self._last_save > 60:                                   # 崩溃最多丢一分钟
            self._last_save = now
            self.save_stats()

    def flush_stats(self):
        self.tick_stats()
        self.save_stats()

    def shutdown(self):
        try:
            self.flush_stats()
            if self.core.alive():
                self.disconnect()
        except Exception:
            pass
        try:
            # 兜底还原：内核已死或异常退出时也要把自己的系统代理设置摘除
            sysproxy.restore_proxy()
        except Exception:
            pass
