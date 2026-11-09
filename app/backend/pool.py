"""节点池：抓取 -> 抽样 -> 实测 -> 持久化。"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict

from . import core as C
from . import nodes as N
from . import subs

PROTO_RANK = {
    "hysteria2": 0, "tuic": 1, "vless": 2, "trojan": 3,
    "vmess": 4, "ss": 5, "hysteria": 6, "anytls": 7, "http": 8, "socks5": 9,
}


def diversify(proxies, limit=1000, per_country=80, per_host=4, prefer=None, max_plain_ratio=0.4):
    """按地区/协议/主机分散抽样，避免节点池被单一机场或公共 HTTP 代理刷屏。"""
    prefer = prefer or []
    buckets = defaultdict(list)
    host_count = defaultdict(int)
    plain_cap = int(limit * max_plain_ratio)
    plain = 0

    def rank(p):
        c = N.guess_country(p.get("_raw_name") or p.get("name", ""))
        pref = prefer.index(c) if c in prefer else 99
        return (pref, PROTO_RANK.get(p.get("type", ""), 99))

    ordered = sorted(proxies, key=rank)
    out = []
    for p in ordered:
        country = N.guess_country(p.get("_raw_name") or p.get("name", ""))
        host = str(p.get("server", ""))
        is_plain = p.get("type") in ("http", "socks5")
        if is_plain and plain >= plain_cap:
            continue
        if host_count[host] >= per_host:
            continue
        if len(buckets[country]) >= per_country:
            continue
        buckets[country].append(p)
        host_count[host] += 1
        if is_plain:
            plain += 1
        out.append(p)
        if len(out) >= limit:
            break
    return out


UDP_PROTOCOLS = ("hysteria2", "hysteria", "tuic", "wireguard")


def tcp_prefilter(proxies, workers=600, timeout=2.5, logger=print):
    """并行 TCP 连通性预筛；UDP 协议（hysteria2/tuic）不做 TCP 探测，直接保留。"""
    import concurrent.futures as cf
    import socket

    def probe(p):
        if str(p.get("type", "")).lower() in UDP_PROTOCOLS:
            return p
        try:
            s = socket.create_connection((str(p.get("server")), int(p.get("port"))), timeout=timeout)
            s.close()
            return p
        except Exception:
            return None

    out = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(probe, proxies, chunksize=20):
            if r:
                out.append(r)
    logger(f"[verify] TCP 预筛 {len(out)}/{len(proxies)} 可达")
    return out


def verify(core_exe, home, proxies, timeout_ms=5000, logger=print, keep=600, batch=500):
    """启动临时内核，分批并发测速，返回存活节点（含 delay）。

    单次 group delay 节点过多时内核会限流导致误判，因此按 batch 拆分分组。
    """
    if not proxies:
        return []
    nodes = list(proxies)
    c = None
    for _ in range(12):
        batches = [nodes[i:i + batch] for i in range(0, len(nodes), batch)]
        extra = [
            {"name": f"__b{i}", "type": "url-test",
             "proxies": [p["name"] for p in b],
             "url": "http://www.gstatic.com/generate_204", "interval": 7200,
             "tolerance": 50, "lazy": True}
            for i, b in enumerate(batches)
        ]
        c = C.Core(core_exe, home)
        c.build(nodes, mode="rule", extra_groups=extra, compact_groups=True)
        try:
            c.start()
            break
        except Exception:
            bad = None
            for line in list(c.logs):
                m = re.search(r"proxy (\d+):", line)
                if m:
                    bad = int(m.group(1))
                    break
            if bad is not None and 0 <= bad < len(nodes):
                logger(f"[verify] 剔除异常节点 #{bad}: {str(nodes[bad].get('name', ''))[:40]}")
                nodes.pop(bad)
                c.stop()
                continue
            raise

    try:
        logger(f"[verify] 共 {len(nodes)} 个节点，分 {len(batches)} 批测速")
        by_name = {p["name"]: p for p in nodes}
        alive = {}
        for i in range(len(batches)):
            res = c.group_delay(f"__b{i}", timeout=timeout_ms)
            for name, delay in (res or {}).items():
                if isinstance(delay, int) and 0 < delay < timeout_ms:
                    alive[name] = delay
            logger(f"[verify] 第 {i + 1}/{len(batches)} 批：累计存活 {len(alive)}")
        out = []
        for name, delay in sorted(alive.items(), key=lambda kv: kv[1])[:keep]:
            p = dict(by_name[name])
            p["delay"] = delay
            out.append(p)
        logger(f"[verify] 存活 {len(alive)} 个，保留 {len(out)} 个")
        return out
    finally:
        c.stop()


def merge_pool(alive, reachable, total=1200, max_plain_ratio=0.45):
    """实测存活节点优先，再用 TCP 可达但未确认的节点补足数量（客户端会自动挑活的）。"""
    alive_names = {p["name"] for p in alive}
    extra_real, extra_plain = [], []
    for p in reachable:
        if p["name"] in alive_names:
            continue
        if p.get("type") in ("http", "socks5"):
            extra_plain.append(p)
        else:
            extra_real.append(p)
    plain_quota = max(0, int(total * max_plain_ratio) - sum(1 for p in alive if p.get("type") in ("http", "socks5")))
    merged = list(alive) + extra_real + extra_plain[:plain_quota]
    return merged[:max(total, len(alive))]


def save(path, nodes, meta=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "updated": int(time.time()),
        "updated_text": time.strftime("%m-%d %H:%M", time.localtime()),
        "count": len(nodes),
        "meta": meta or {},
        "nodes": nodes,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)
    return payload


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updated": 0, "updated_text": "", "count": 0, "nodes": [], "meta": {}}


def refresh(core_exe, home, pool_path, limit=1000, per_country=80, logger=print, keep=600, proxies=None):
    """完整刷新流程：抓取 -> 抽样 -> TCP 预筛 -> 分片测速 -> 入库。"""
    t0 = time.time()
    proxies_list, report = subs.harvest(logger=logger, proxies=proxies)
    logger(f"[pool] 抓取到 {len(proxies_list)} 个去重节点，用时 {time.time() - t0:.1f}s")
    picked = diversify(proxies_list, limit=limit, per_country=per_country)
    logger(f"[pool] 抽样 {len(picked)} 个节点进入预筛")
    reachable = tcp_prefilter(picked, logger=logger)
    alive = verify(core_exe, home, reachable, logger=logger, keep=keep)
    payload = save(pool_path, [{k: v for k, v in p.items() if not k.startswith("_")} for p in alive],
                   meta={"sources": report, "harvested": len(proxies_list), "sampled": len(picked),
                         "reachable": len(reachable), "cost": round(time.time() - t0, 1)})
    logger(f"[pool] 完成：{payload['count']} 条可用线路，耗时 {time.time() - t0:.1f}s")
    return payload
