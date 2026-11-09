"""构建种子池：全量抓取 -> 抽样 -> TCP 预筛 -> 分片测速 -> 二轮复测。"""
import sys, os, json, time, shutil
sys.path.insert(0, r'D:\VPN\app')
from backend import pool, subs, core as C

HOME = r'D:\VPN\tools\seedhome'
CORE = r'D:\VPN\runtime\core\mihomo.exe'
OUT = r'D:\VPN\app\assets\seed_pool.json'
os.makedirs(HOME, exist_ok=True)
for f in ['GEOIP.metadb', 'GEOSITE.dat', 'ASN.mmdb']:
    s = os.path.join(r'D:\VPN\runtime\core', f)
    if os.path.exists(s) and not os.path.exists(os.path.join(HOME, f)):
        shutil.copy(s, os.path.join(HOME, f))
os.makedirs(os.path.dirname(OUT), exist_ok=True)

P = lambda m: print(m, flush=True)
t0 = time.time()
PX = {'http': 'http://127.0.0.1:7899', 'https': 'http://127.0.0.1:7899'}
proxies, report = subs.harvest(logger=P, proxies=PX)
if len(proxies) < 500:
    P('直连不足，尝试无代理抓取…')
    proxies2, report2 = subs.harvest(logger=P, proxies=None)
    if len(proxies2) > len(proxies):
        proxies, report = proxies2, report2
P(f'harvested {len(proxies)} in {time.time()-t0:.1f}s')
if len(proxies) < 200:
    raise SystemExit('订阅源不可达，终止以免覆盖种子池')

cand = pool.diversify(proxies, limit=20000, per_country=3000, per_host=12,
                      prefer=['香港', '台湾', '日本', '新加坡', '美国', '韩国'], max_plain_ratio=0.35)
P(f'candidates {len(cand)}')

reach = pool.tcp_prefilter(cand, logger=P)
alive1 = pool.verify(CORE, HOME, reach, timeout_ms=6000, keep=6000, logger=P, batch=400)
P(f'round1 alive {len(alive1)} / {len(reach)}')

alive1b = [dict(p) for p in alive1]
for p in alive1b:
    p.pop('delay', None)
alive2 = pool.verify(CORE, HOME, alive1b, timeout_ms=6000, keep=2000, logger=P, batch=400)
P(f'round2 alive {len(alive2)} / {len(alive1b)}')

plain = [p for p in alive2 if p.get('type') in ('http', 'socks5')]
real = [p for p in alive2 if p.get('type') not in ('http', 'socks5')]
plain = plain[:int(len(real) * 0.45) + 40]
alive2 = sorted(real + plain, key=lambda p: p.get('delay', 9999))
P(f'final kept {len(alive2)} (real={len(real)} plain={len(plain)})')

merged = pool.merge_pool(alive2, reach, total=1500, max_plain_ratio=0.42)
P(f'merged pool {len(merged)} (verified={sum(1 for p in merged if p.get("delay"))})')
alive2 = merged

clean = [{k: v for k, v in p.items() if not k.startswith('_')} for p in alive2]
payload = pool.save(OUT, clean, meta={'sources': report, 'harvested': len(proxies),
                                      'sampled': len(cand), 'reachable': len(reach),
                                      'round1': len(alive1), 'cost': round(time.time() - t0, 1)})
P(f"SEED SAVED {payload['count']} at {payload['updated_text']} cost {time.time()-t0:.0f}s")
from collections import Counter
P(str(Counter(p['name'].split(' ')[1] for p in clean).most_common(20)))
P(str(Counter(p['type'] for p in clean).most_common()))
for p in clean[:8]:
    P(f"  {p['delay']}ms {p['name']} [{p['type']}]")
