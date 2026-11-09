"""保持一个可用代理常驻（用于本机构建/推送时的联网引导）。"""
import sys, os, json, shutil, time, threading
sys.path.insert(0, r'D:\VPN\app')
from backend import core as C

HOME = r'D:\VPN\tools\bootproxy'
os.makedirs(HOME, exist_ok=True)
for f in ['GEOIP.metadb', 'GEOSITE.dat', 'ASN.mmdb']:
    s = os.path.join(r'D:\VPN\runtime\core', f)
    if os.path.exists(s) and not os.path.exists(os.path.join(HOME, f)):
        shutil.copy(s, os.path.join(HOME, f))

pool = json.load(open(r'D:\VPN\app\assets\seed_pool.json', encoding='utf-8'))['nodes']
c = C.Core(r'D:\VPN\runtime\core\mihomo.exe', HOME, log_cb=lambda m: None)
c.build(pool, prefer_port=int(sys.argv[1]) if len(sys.argv) > 1 else 7899)
c.start()
print('mixed', c.mixed_port, 'ctrl', c.ctrl_port, flush=True)


def watchdog():
    """节点失效时自动切换到可用节点。"""
    import requests
    while True:
        time.sleep(20)
        try:
            px = {'http': f'http://127.0.0.1:{c.mixed_port}', 'https': f'http://127.0.0.1:{c.mixed_port}'}
            r = requests.get('https://www.gstatic.com/generate_204', proxies=px, timeout=12)
            if r.status_code in (200, 204):
                continue
        except Exception:
            pass
        for p in pool[:25]:
            d = c.delay(p['name'], 4000)
            if d:
                c.select(C.GROUP_SELECT, p['name'])
                print('switch ->', p['name'], d, flush=True)
                break


threading.Thread(target=watchdog, daemon=True).start()
while True:
    time.sleep(3600)
