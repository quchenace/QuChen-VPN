"""构建内置种子节点池：全量抓取 -> 抽样 -> TCP 预筛 -> 分片测速 -> 二轮复测。

用法：python tools/build_seed.py [--limit 25000] [--keep 2500]
"""
import argparse
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

from backend import core as C  # noqa: E402
from backend import pool, subs  # noqa: E402

HOME = os.path.join(ROOT, "tools", "seedhome")
CORE = os.path.join(ROOT, "runtime", "core", "mihomo.exe")
OUT = os.path.join(ROOT, "app", "assets", "seed_pool.json")

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=20000)
ap.add_argument("--keep", type=int, default=2500)
ap.add_argument("--proxy", default="", help="可选：抓取用的 HTTP 代理，如 http://127.0.0.1:7890")
args = ap.parse_args()

P = lambda m: print(m, flush=True)
os.makedirs(HOME, exist_ok=True)
for f in ("GEOIP.metadb", "GEOSITE.dat"):
    s = os.path.join(ROOT, "runtime", "core", f)
    if os.path.exists(s) and not os.path.exists(os.path.join(HOME, f)):
        shutil.copy(s, os.path.join(HOME, f))
os.makedirs(os.path.dirname(OUT), exist_ok=True)

PX = {"http": args.proxy, "https": args.proxy} if args.proxy else None

t0 = time.time()
proxies, report = subs.harvest(logger=P, proxies=PX)
P(f"harvested {len(proxies)} in {time.time() - t0:.1f}s")
if len(proxies) < 200:
    raise SystemExit("订阅源不可达，终止以免覆盖节点池")

cand = pool.diversify(proxies, limit=args.limit, per_country=5000, per_host=14,
                      prefer=["香港", "台湾", "日本", "新加坡", "美国", "韩国"],
                      max_plain_ratio=0.30)
P(f"candidates {len(cand)}")

reach = pool.tcp_prefilter(cand, logger=P)
alive1 = pool.verify(CORE, HOME, reach, timeout_ms=6000, keep=6000, logger=P, batch=400)
P(f"round1 alive {len(alive1)} / {len(reach)}")

alive1b = [dict(p) for p in alive1]
for p in alive1b:
    p.pop("delay", None)
alive2 = pool.verify(CORE, HOME, alive1b, timeout_ms=6000, keep=4000, logger=P, batch=400)
P(f"round2 alive {len(alive2)} / {len(alive1b)}")

real = [p for p in alive2 if p.get("type") not in ("http", "socks5")]
plain = [p for p in alive2 if p.get("type") in ("http", "socks5")]
plain = plain[:int(len(real) * 0.45) + 40]
verified = sorted(real + plain, key=lambda p: p.get("delay", 9999))

merged = pool.merge_pool(verified, reach, total=args.keep, max_plain_ratio=0.35)
payload = pool.save(OUT, [{k: v for k, v in p.items() if not k.startswith("_")} for p in merged],
                    meta={"sources": report, "harvested": len(proxies), "sampled": len(cand),
                          "reachable": len(reach), "verified": len(verified),
                          "cost": round(time.time() - t0, 1)})
P(f"SEED SAVED {payload['count']} (verified {len(verified)}) at {payload['updated_text']} "
  f"cost {time.time() - t0:.0f}s")

from collections import Counter  # noqa: E402
P(str(Counter(p["type"] for p in payload["nodes"]).most_common()))
