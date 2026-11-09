import requests, concurrent.futures as cf, re, base64
PX = {'http': 'http://127.0.0.1:7990', 'https': 'http://127.0.0.1:7990'}
UA = 'clash.meta/1.19.33'
CANDS = [
 ("ermaozi01/free_clash_vpn", "https://raw.githubusercontent.com/ermaozi01/free_clash_vpn/main/subscribe/clash.yml"),
 ("mahdibland V2RayAggregator", "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/Eternity.yml"),
 ("mahdibland merge", "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge_base64.txt"),
 ("vxiaov/free_proxies", "https://raw.githubusercontent.com/vxiaov/free_proxies/main/clash/clash.provider.yaml"),
 ("ALIILAPRO v2rayNG", "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/server.txt"),
 ("yebekhe collector", "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/mix"),
 ("Epodonios vless", "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/Splitted-By-Protocol/vless.txt"),
 ("Epodonios trojan", "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/Splitted-By-Protocol/trojan.txt"),
 ("Epodonios vmess", "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/Splitted-By-Protocol/vmess.txt"),
 ("Vauth/node", "https://raw.githubusercontent.com/Vauth/node/main/Main"),
 ("miladtahanian dumper", "https://raw.githubusercontent.com/miladtahanian/V2RayCFGDumper/main/config.txt"),
 ("MrPooyaX reality", "https://raw.githubusercontent.com/MrPooyaX/VpnsFucking/main/RealityConfigs.txt"),
 ("MrPooyaX mix", "https://raw.githubusercontent.com/MrPooyaX/VpnsFucking/main/Servers.txt"),
 ("sashalsk V2Ray", "https://raw.githubusercontent.com/sashalsk/V2Ray/main/V2Config"),
 ("free-nodes clashfree", "https://raw.githubusercontent.com/free-nodes/clashfree/main/clash.yml"),
 ("mermeroo", "https://raw.githubusercontent.com/mermeroo/V2RAY-and-CLASH-configs/main/v2ray.txt"),
 ("roosterkid openproxylist", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"),
 ("mahdibland clash", "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge_yaml.yml"),
 ("ts-sf fly2", "https://raw.githubusercontent.com/ts-sf/fly/main/v2"),
 ("hans-thomas sub", "https://raw.githubusercontent.com/hans-thomas/v2ray/main/sub.txt"),
 ("Pawdroid sub2", "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub2"),
 ("ripaojiedian v2", "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub"),
 ("aiboboxx clash", "https://raw.githubusercontent.com/aiboboxx/clashfree/main/clash.yml"),
 ("mfuu mihomo", "https://raw.githubusercontent.com/mfuu/v2ray/master/mihomo.yaml"),
 ("Alvin9999 config", "https://raw.githubusercontent.com/Alvin9999/pac2/master/clash/1/config.yaml"),
]
def probe(item):
    name,url = item
    try:
        r = requests.get(url, proxies=PX, timeout=25, headers={'User-Agent':UA})
        if r.status_code != 200: return (name, r.status_code, 0, '')
        t = r.text
        if 'proxies:' in t[:300000]:
            n = len(re.findall(r'^\s*-\s*(\{)?\s*name:', t, re.M))
            return (name, 200, n, 'yaml')
        b = t.strip()
        if '://' not in b[:2000]:
            try: b = base64.b64decode(b + '=='*2).decode('utf-8','ignore')
            except Exception: pass
        n = len(re.findall(r'(vmess|vless|ss|trojan|hysteria2)://', b))
        return (name, 200, n, 'uri')
    except Exception as e:
        return (name, 'ERR', 0, type(e).__name__)
with cf.ThreadPoolExecutor(max_workers=12) as ex:
    for name, st, n, kind in ex.map(probe, CANDS):
        print(f"{name[:34]:34} {str(st):>5} {n:>6} {kind}")
