"""订阅源抓取与聚合。

- 多源并发拉取（含 GitHub 镜像回退）
- 兼容 Clash YAML 订阅与 base64/明文分享链接列表
- 去重、清洗命名、地区归类
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import re
import time

import requests
import yaml

from . import nodes as N

UA = "clash.meta/1.19.33 mihomo/1.19.33"

# ---------------------------------------------------------------- 源定义
SOURCES = [
    {"name": "barry-far 全量池", "url": "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/All_Configs_Sub.txt"},
    {"name": "anaer 聚合", "url": "https://raw.githubusercontent.com/anaer/Sub/main/clash.yaml"},
    {"name": "mahdibland 全量", "url": "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge_base64.txt"},
    {"name": "ALIILAPRO", "url": "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/server.txt"},
    {"name": "ermaozi 订阅", "url": "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/clash.yml"},
    {"name": "ermaozi v2ray", "url": "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt"},
    {"name": "Ruk1ng001", "url": "https://raw.githubusercontent.com/Ruk1ng001/freeSub/main/clash.yaml"},
    {"name": "mahdibland 聚合", "url": "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity.yml"},
    {"name": "peasoft NoMoreWalls", "url": "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.yml"},
    {"name": "ripaojiedian", "url": "https://raw.githubusercontent.com/ripaojiedian/freenode/main/clash"},
    {"name": "Kwinshadow TG", "url": "https://raw.githubusercontent.com/Kwinshadow/telegramV2rayCollector/main/sublinks/mix.txt"},
    {"name": "ts-sf fly", "url": "https://raw.githubusercontent.com/ts-sf/fly/main/clash"},
    {"name": "ts-sf fly v2", "url": "https://raw.githubusercontent.com/ts-sf/fly/main/v2"},
    {"name": "Pawdroid", "url": "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"},
    {"name": "freefq", "url": "https://raw.githubusercontent.com/freefq/free/master/v2"},
    {"name": "roosterkid", "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"},
    {"name": "ermaozi01", "url": "https://raw.githubusercontent.com/ermaozi01/free_clash_vpn/main/subscribe/clash.yml"},
]

_RAW = re.compile(r"^https://raw\.githubusercontent\.com/([^/]+/[^/]+)/([^/]+)/(.+)$")

#: 单个订阅源最多读 8 MB、最多解析 6 MB：公开源不可信，一枚超大响应或 YAML 别名炸弹就能把客户端吃满内存
MAX_FETCH = 8 * 1024 * 1024
MAX_PARSE = 6 * 1024 * 1024


def _mirror_urls(url: str):
    yield url
    m = _RAW.match(url)
    if m:
        repo, branch, file = m.group(1), m.group(2), m.group(3)
        yield f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{file}"
        yield f"https://fastly.jsdelivr.net/gh/{repo}@{branch}/{file}"
        yield f"https://ghfast.top/{url}"
        yield f"https://gh-proxy.com/{url}"


# ---------------------------------------------------------------- YAML
class ClashLoader(yaml.SafeLoader):
    pass


def _unknown(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


ClashLoader.add_multi_constructor("!", _unknown)


def load_yaml(text: str):
    try:
        return yaml.load(text, Loader=ClashLoader)
    except (Exception, MemoryError):
        return None


# ---------------------------------------------------------------- 解析
def parse_payload(text: str):
    """返回 (proxies, kind)。proxies 中保留 _raw_name 原始节点名。"""
    out = []
    text = (text or "").strip()
    if not text:
        return out, "empty"

    data = None
    text = text[:MAX_PARSE]
    head = text[:300000]
    # YAML 的 &锚点 / *引用 可以指数级展开（billion laughs）。正常订阅远低于这个数，超了就不按 YAML 解析。
    if ("proxies:" in head or "proxy-groups:" in head) and text.count("&") + text.count("*") <= 4000:
        data = load_yaml(text)
    if isinstance(data, dict) and isinstance(data.get("proxies"), list):
        for p in data["proxies"]:
            if not isinstance(p, dict):
                continue
            p = dict(p)
            raw = str(p.get("name", ""))
            if not N.valid(p):
                continue
            p["_raw_name"] = raw
            out.append(p)
        return out, "clash"

    # base64 链接列表
    body = text
    if "://" not in body[:4000]:
        try:
            dec = base64.b64decode(body + "=" * (-len(body) % 4)).decode("utf-8", "ignore")
            if "://" in dec:
                body = dec
        except Exception:
            pass

    for line in re.split(r"[\r\n]+", body):
        line = line.strip()
        if "://" not in line:
            continue
        for tok in re.split(r"\s+", line):
            if "://" not in tok:
                continue
            p = N.parse_uri(tok)
            if not p:
                continue
            raw = str(p.pop("name", "") or "")
            if not N.valid(p):
                continue
            p["_raw_name"] = raw
            out.append(p)
    return out, "uri"


def fetch(url: str, timeout: int = 25, proxies=None) -> str:
    last = ""
    for u in _mirror_urls(url):
        try:
            with requests.get(u, timeout=timeout, headers={"User-Agent": UA}, proxies=proxies,
                              stream=True) as r:
                if r.status_code != 200:
                    last = f"HTTP {r.status_code}"
                    continue
                announced = int(r.headers.get("Content-Length") or 0)
                if announced > MAX_FETCH:
                    last = f"too large ({announced} bytes)"
                    continue
                buf = bytearray()
                for chunk in r.iter_content(64 * 1024):
                    if not chunk:
                        continue
                    buf += chunk
                    if len(buf) > MAX_FETCH:
                        raise RuntimeError("too large")
                if len(buf) > 64:
                    return bytes(buf).decode("utf-8", "ignore")
                last = "empty"
        except Exception as e:
            last = type(e).__name__
    raise RuntimeError(last or "fail")


def harvest(sources=None, timeout: int = 25, logger=None, proxies=None):
    """并发抓取 + 解析 + 去重 + 命名。返回 (proxies, report)。"""
    sources = sources or SOURCES
    log = logger or (lambda m: None)
    report = []

    def job(src):
        t0 = time.time()
        try:
            text = fetch(src["url"], timeout=timeout, proxies=proxies)
        except Exception as e:
            return {"name": src["name"], "nodes": [], "bytes": 0, "err": str(e)[:90], "ms": 0, "kind": "-"}
        got, kind = parse_payload(text)
        return {"name": src["name"], "nodes": got, "bytes": len(text),
                "err": "", "ms": int((time.time() - t0) * 1000), "kind": kind}

    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(job, sources))

    seen, merged = set(), []
    for r in results:
        report.append({"name": r["name"], "nodes": len(r["nodes"]), "bytes": r["bytes"],
                       "err": r["err"], "ms": r["ms"], "kind": r["kind"]})
        if r["err"]:
            log(f"[sub] {r['name']} 失败: {r['err']}")
            continue
        log(f"[sub] {r['name']}: {len(r['nodes'])} 节点 / {r['ms']}ms")
        for p in r["nodes"]:
            fp = N.fingerprint(p)
            if fp in seen:
                continue
            seen.add(fp)
            p["_source"] = r["name"]
            merged.append(p)

    merged.sort(key=lambda p: (N.guess_country(p.get("_raw_name", "")), p.get("_raw_name", "")))
    for i, p in enumerate(merged, 1):
        raw = p.pop("_raw_name", "") or p.get("server", "")
        src = p.pop("_source", "")
        p["_country"] = N.guess_country(raw)
        p["name"] = N.display_name(raw, i)
        p["_src"] = src
    return merged, report
