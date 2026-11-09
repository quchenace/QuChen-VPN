"""Test candidate free subscription sources through the local proxy."""
import requests, concurrent.futures as cf, re, sys, json, time

PX = {'http': 'http://127.0.0.1:7990', 'https': 'http://127.0.0.1:7990'}
UA = 'clash.meta/1.19.33'

CANDS = [
    ("aiboboxx/v2rayfree", "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2"),
    ("aiboboxx/clashfree", "https://raw.githubusercontent.com/aiboboxx/clashfree/main/clash.yml"),
    ("mfuu/v2ray", "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray"),
    ("mfuu/clash", "https://raw.githubusercontent.com/mfuu/v2ray/master/clash.yaml"),
    ("ermaozi/get_subscribe", "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/clash.yml"),
    ("anaer/Sub", "https://raw.githubusercontent.com/anaer/Sub/main/clash.yaml"),
    ("vveg26/get_proxy", "https://raw.githubusercontent.com/vveg26/get_proxy/main/dist/clash.config.yaml"),
    ("Pawdroid/Free-servers", "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"),
    ("freefq/free", "https://raw.githubusercontent.com/freefq/free/master/v2"),
    ("mahdibland/Aggregator", "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity.yml"),
    ("ripaojiedian/freenode", "https://raw.githubusercontent.com/ripaojiedian/freenode/main/clash"),
    ("ts-sf/fly", "https://raw.githubusercontent.com/ts-sf/fly/main/clash"),
    ("peasoft/NoMoreWalls", "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.yml"),
    ("ermaozi clash", "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt"),
    ("barry-far/V2ray-Config", "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/All_Configs_Sub.txt"),
    ("openrunner/clash-freenode", "https://raw.githubusercontent.com/openrunner/clash-freenode/main/clash.yaml"),
    ("mianfeifq/share", "https://raw.githubusercontent.com/mianfeifq/share/main/data2024078.txt"),
    ("qjlxg/clashfree", "https://raw.githubusercontent.com/qjlxg/clashfree/main/clash.yaml"),
    ("Ruk1ng001/freeSub", "https://raw.githubusercontent.com/Ruk1ng001/freeSub/main/clash.yaml"),
    ("Alvin9999/pac2", "https://raw.githubusercontent.com/Alvin9999/pac2/master/clash/config.yaml"),
    ("Epodonios/v2ray", "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt"),
    ("soroushmirzaei/telegram-configs-collector", "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/splitted/mixed"),
    ("Kwinshadow/telegramV2rayCollector", "https://raw.githubusercontent.com/Kwinshadow/telegramV2rayCollector/main/sublinks/mix.txt"),
    ("v2ray-links-collector", "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray_subscribe"),
    ("yuchen2025/clash-node", "https://raw.githubusercontent.com/yuchen2025/clash-node/main/clash.yaml"),
    ("hans-thomas/v2ray", "https://raw.githubusercontent.com/hans-thomas/v2ray/main/sub"),
    ("free node sub (sharecentre)", "https://sub.sharecentre.online/sub"),
    ("clashnode", "https://clashnode.xyz/wp-content/uploads/2024/01/20240117.yaml"),
    ("nodefree", "https://nodefree.org/dy/2025/01/20250115.yaml"),
    ("freeclashnode", "https://freeclashnode.com/wp-content/uploads/2025/01/20250115.yaml"),
]


def probe(item):
    name, url = item
    out = {'name': name, 'url': url, 'status': None, 'bytes': 0, 'nodes': 0, 'err': ''}
    try:
        t0 = time.time()
        r = requests.get(url, proxies=PX, timeout=25,
                         headers={'User-Agent': UA}, allow_redirects=True)
        out['status'] = r.status_code
        out['bytes'] = len(r.content)
        out['ms'] = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            txt = r.text
            if 'proxies:' in txt[:200000] or 'proxy-groups:' in txt[:200000]:
                # crude yaml node count
                out['nodes'] = len(re.findall(r'^\s*-\s*\{?\s*name:', txt, re.M)) or txt.count('- name:')
                out['kind'] = 'clash-yaml'
            else:
                import base64
                try:
                    dec = base64.b64decode(txt.strip() + '==').decode('utf-8', 'ignore')
                except Exception:
                    dec = txt
                schemes = re.findall(r'(vmess|vless|ss|ssr|trojan|hysteria2?|hy2|tuic)://', dec)
                out['nodes'] = len(schemes)
                out['kind'] = 'uri-list'
                if out['nodes'] > 0:
                    with open(r'D:\VPN\tools\raw_' + re.sub(r'\W+', '_', name) + '.txt', 'w', encoding='utf-8') as f:
                        f.write(dec)
    except Exception as e:
        out['err'] = type(e).__name__ + ': ' + str(e)[:120]
    return out


with cf.ThreadPoolExecutor(max_workers=12) as ex:
    res = list(ex.map(probe, CANDS))

res.sort(key=lambda x: (-x['nodes'], x['name']))
for r in res:
    print(f"{r['name'][:34]:34} {str(r['status']):>4} {r['bytes']:>9} nodes={r['nodes']:<5} {r.get('kind','')[:10]:10} {r['err'][:60]}")
print('\nOK sources:', sum(1 for r in res if r['nodes'] > 0))
