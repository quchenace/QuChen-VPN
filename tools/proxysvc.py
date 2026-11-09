"""Persistent proxy: keep the client core connected and expose a local HTTP proxy."""
import json
import sys
import time

import requests

sys.path.insert(0, r'D:\VPN\app')
from backend.service import Service

idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
names = json.load(open(r'D:\VPN\tools\good_nodes.json', encoding='utf-8'))
node = names[idx] if names else ""

svc = Service()
if svc.core.alive():
    svc.disconnect()
svc.settings["sys_proxy"] = False
svc.settings["node"] = node
r = svc.connect(node or None)
print("connect", r.get("ok"), r.get("msg"), "->", svc.core.current(), "port", svc.core.mixed_port, flush=True)
open(r"D:\VPN\tools\proxy_port.txt", "w").write(str(svc.core.mixed_port))

while True:
    time.sleep(20)
    port = svc.core.mixed_port
    px = {"http": f"http://127.0.0.1:{port}", "https": f"http://127.0.0.1:{port}"}
    try:
        if requests.get("https://api.github.com/zen", proxies=px, timeout=12).status_code != 200:
            raise RuntimeError("bad")
    except Exception:
        print("node unhealthy, rotating...", flush=True)
        for nm in names:
            try:
                if svc.core.alive() and svc.core.select("🚀 节点选择", nm):
                    time.sleep(2)
                    if requests.get("https://api.github.com/zen", proxies=px, timeout=12).status_code == 200:
                        print("node ok:", nm, flush=True)
                        break
            except Exception:
                continue
