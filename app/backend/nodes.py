"""节点解析、命名、去重、国旗/地区识别。

支持两类输入：
1) Clash YAML 订阅里的 proxies 列表（dict）
2) 分享链接：vmess / vless / ss / trojan / hysteria2 / tuic / ssr(跳过)
统一输出为 mihomo 可直接使用的 proxy dict。
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.parse as up

# ---------------------------------------------------------------- 地区识别
FLAGS = {
    "香港": "🇭🇰", "台湾": "🇹🇼", "日本": "🇯🇵", "新加坡": "🇸🇬", "韩国": "🇰🇷",
    "美国": "🇺🇸", "英国": "🇬🇧", "德国": "🇩🇪", "法国": "🇫🇷", "荷兰": "🇳🇱",
    "加拿大": "🇨🇦", "澳大利亚": "🇦🇺", "印度": "🇮🇳", "俄罗斯": "🇷🇺", "土耳其": "🇹🇷",
    "越南": "🇻🇳", "马来西亚": "🇲🇾", "泰国": "🇹🇭", "菲律宾": "🇵🇭", "印尼": "🇮🇩",
    "阿联酋": "🇦🇪", "巴西": "🇧🇷", "阿根廷": "🇦🇷", "南非": "🇿🇦", "波兰": "🇵🇱",
    "瑞典": "🇸🇪", "芬兰": "🇫🇮", "瑞士": "🇨🇭", "西班牙": "🇪🇸", "意大利": "🇮🇹",
    "爱尔兰": "🇮🇪", "乌克兰": "🇺🇦", "以色列": "🇮🇱", "智利": "🇨🇱", "墨西哥": "🇲🇽",
    "奥地利": "🇦🇹", "挪威": "🇳🇴", "丹麦": "🇩🇰", "比利时": "🇧🇪", "捷克": "🇨🇿",
    "罗马尼亚": "🇷🇴", "匈牙利": "🇭🇺", "葡萄牙": "🇵🇹", "希腊": "🇬🇷", "埃及": "🇪🇬",
    "沙特": "🇸🇦", "巴基斯坦": "🇵🇰", "孟加拉": "🇧🇩", "柬埔寨": "🇰🇭", "新西兰": "🇳🇿",
    "哈萨克斯坦": "🇰🇿", "立陶宛": "🇱🇹", "爱沙尼亚": "🇪🇪", "拉脱维亚": "🇱🇻", "保加利亚": "🇧🇬",
    "其他": "🌐",
}

# 关键字 -> 地区（顺序敏感，长的优先）
ALIAS = [
    ("🇭🇰", "香港"), ("🇹🇼", "台湾"), ("🇯🇵", "日本"), ("🇸🇬", "新加坡"), ("🇰🇷", "韩国"),
    ("🇺🇸", "美国"), ("🇬🇧", "英国"), ("🇩🇪", "德国"), ("🇫🇷", "法国"), ("🇳🇱", "荷兰"),
    ("🇨🇦", "加拿大"), ("🇦🇺", "澳大利亚"), ("🇮🇳", "印度"), ("🇷🇺", "俄罗斯"), ("🇹🇷", "土耳其"),
    ("🇻🇳", "越南"), ("🇲🇾", "马来西亚"), ("🇹🇭", "泰国"), ("🇵🇭", "菲律宾"), ("🇮🇩", "印尼"),
    ("🇦🇪", "阿联酋"), ("🇧🇷", "巴西"), ("🇦🇷", "阿根廷"), ("🇿🇦", "南非"), ("🇵🇱", "波兰"),
    ("🇸🇪", "瑞典"), ("🇫🇮", "芬兰"), ("🇨🇭", "瑞士"), ("🇪🇸", "西班牙"), ("🇮🇹", "意大利"),
    ("🇮🇪", "爱尔兰"), ("🇺🇦", "乌克兰"), ("🇮🇱", "以色列"), ("🇨🇱", "智利"), ("🇲🇽", "墨西哥"),
    ("🇦🇹", "奥地利"), ("🇳🇴", "挪威"), ("🇩🇰", "丹麦"), ("🇧🇪", "比利时"), ("🇨🇿", "捷克"),
    ("🇷🇴", "罗马尼亚"), ("🇭🇺", "匈牙利"), ("🇵🇹", "葡萄牙"), ("🇬🇷", "希腊"), ("🇪🇬", "埃及"),
    ("🇸🇦", "沙特"), ("🇵🇰", "巴基斯坦"), ("🇧🇩", "孟加拉"), ("🇰🇭", "柬埔寨"), ("🇳🇿", "新西兰"),
    ("🇰🇿", "哈萨克斯坦"), ("🇱🇹", "立陶宛"), ("🇪🇪", "爱沙尼亚"), ("🇱🇻", "拉脱维亚"), ("🇧🇬", "保加利亚"),
    ("香港", "香港"), ("HK", "香港"), ("HongKong", "香港"), ("Hong Kong", "香港"), ("HKG", "香港"),
    ("深港", "香港"), ("沪港", "香港"), ("京港", "香港"), ("广港", "香港"), ("九龙", "香港"),
    ("台湾", "台湾"), ("台灣", "台湾"), ("TW", "台湾"), ("Taiwan", "台湾"), ("台北", "台湾"),
    ("新北", "台湾"), ("彰化", "台湾"), ("日本", "日本"), ("JP", "日本"), ("Japan", "日本"),
    ("东京", "日本"), ("大阪", "日本"), ("埼玉", "日本"), ("沪日", "日本"), ("京日", "日本"),
    ("狮城", "新加坡"), ("新加坡", "新加坡"), ("SG", "新加坡"), ("Singapore", "新加坡"),
    ("韩国", "韩国"), ("KR", "韩国"), ("Korea", "韩国"), ("首尔", "韩国"),
    ("美国", "美国"), ("US", "美国"), ("United States", "美国"), ("洛杉矶", "美国"),
    ("圣何塞", "美国"), ("硅谷", "美国"), ("西雅图", "美国"), ("达拉斯", "美国"), ("纽约", "美国"),
    ("芝加哥", "美国"), ("凤凰城", "美国"), ("迈阿密", "美国"), ("波特兰", "美国"), ("拉斯维加斯", "美国"),
    ("英国", "英国"), ("UK", "英国"), ("United Kingdom", "英国"), ("伦敦", "英国"),
    ("德国", "德国"), ("DE", "德国"), ("Germany", "德国"), ("法兰克福", "德国"),
    ("法国", "法国"), ("FR", "法国"), ("France", "法国"), ("巴黎", "法国"),
    ("荷兰", "荷兰"), ("NL", "荷兰"), ("Netherlands", "荷兰"), ("阿姆斯特丹", "荷兰"),
    ("加拿大", "加拿大"), ("CA", "加拿大"), ("Canada", "加拿大"), ("多伦多", "加拿大"),
    ("澳大利亚", "澳大利亚"), ("AU", "澳大利亚"), ("Australia", "澳大利亚"), ("悉尼", "澳大利亚"),
    ("印度", "印度"), ("IN", "印度"), ("India", "印度"), ("孟买", "印度"),
    ("俄罗斯", "俄罗斯"), ("RU", "俄罗斯"), ("Russia", "俄罗斯"), ("莫斯科", "俄罗斯"),
    ("土耳其", "土耳其"), ("TR", "土耳其"), ("Turkey", "土耳其"), ("伊斯坦布尔", "土耳其"),
    ("越南", "越南"), ("VN", "越南"), ("Vietnam", "越南"), ("胡志明", "越南"),
    ("马来", "马来西亚"), ("MY", "马来西亚"), ("Malaysia", "马来西亚"), ("吉隆坡", "马来西亚"),
    ("泰国", "泰国"), ("TH", "泰国"), ("Thailand", "泰国"), ("曼谷", "泰国"),
    ("菲律宾", "菲律宾"), ("PH", "菲律宾"), ("Philippines", "菲律宾"), ("马尼拉", "菲律宾"),
    ("印尼", "印尼"), ("印度尼西亚", "印尼"), ("ID", "印尼"), ("Indonesia", "印尼"), ("雅加达", "印尼"),
    ("阿联酋", "阿联酋"), ("AE", "阿联酋"), ("迪拜", "阿联酋"), ("Emirates", "阿联酋"),
    ("巴西", "巴西"), ("BR", "巴西"), ("Brazil", "巴西"), ("圣保罗", "巴西"),
    ("阿根廷", "阿根廷"), ("AR", "阿根廷"), ("Argentina", "阿根廷"),
    ("南非", "南非"), ("ZA", "南非"), ("South Africa", "南非"),
    ("波兰", "波兰"), ("PL", "波兰"), ("Poland", "波兰"), ("华沙", "波兰"),
    ("瑞典", "瑞典"), ("SE", "瑞典"), ("Sweden", "瑞典"), ("斯德哥尔摩", "瑞典"),
    ("芬兰", "芬兰"), ("FI", "芬兰"), ("Finland", "芬兰"), ("赫尔辛基", "芬兰"),
    ("瑞士", "瑞士"), ("CH", "瑞士"), ("Switzerland", "瑞士"), ("苏黎世", "瑞士"),
    ("西班牙", "西班牙"), ("ES", "西班牙"), ("Spain", "西班牙"), ("马德里", "西班牙"),
    ("意大利", "意大利"), ("IT", "意大利"), ("Italy", "意大利"), ("米兰", "意大利"),
    ("爱尔兰", "爱尔兰"), ("IE", "爱尔兰"), ("Ireland", "爱尔兰"), ("都柏林", "爱尔兰"),
    ("乌克兰", "乌克兰"), ("UA", "乌克兰"), ("Ukraine", "乌克兰"),
    ("以色列", "以色列"), ("IL", "以色列"), ("Israel", "以色列"),
    ("智利", "智利"), ("CL", "智利"), ("Chile", "智利"),
    ("墨西哥", "墨西哥"), ("MX", "墨西哥"), ("Mexico", "墨西哥"),
    ("奥地利", "奥地利"), ("AT", "奥地利"), ("Austria", "奥地利"),
    ("挪威", "挪威"), ("NO", "挪威"), ("Norway", "挪威"),
    ("丹麦", "丹麦"), ("DK", "丹麦"), ("Denmark", "丹麦"),
    ("比利时", "比利时"), ("BE", "比利时"), ("Belgium", "比利时"),
    ("捷克", "捷克"), ("CZ", "捷克"), ("Czech", "捷克"),
    ("罗马尼亚", "罗马尼亚"), ("RO", "罗马尼亚"), ("Romania", "罗马尼亚"),
    ("匈牙利", "匈牙利"), ("HU", "匈牙利"), ("Hungary", "匈牙利"),
    ("葡萄牙", "葡萄牙"), ("PT", "葡萄牙"), ("Portugal", "葡萄牙"),
    ("希腊", "希腊"), ("GR", "希腊"), ("Greece", "希腊"),
    ("埃及", "埃及"), ("EG", "埃及"), ("Egypt", "埃及"),
    ("沙特", "沙特"), ("SA", "沙特"), ("Saudi", "沙特"),
    ("巴基斯坦", "巴基斯坦"), ("PK", "巴基斯坦"), ("Pakistan", "巴基斯坦"),
    ("孟加拉", "孟加拉"), ("BD", "孟加拉"), ("Bangladesh", "孟加拉"),
    ("柬埔寨", "柬埔寨"), ("KH", "柬埔寨"), ("Cambodia", "柬埔寨"),
    ("新西兰", "新西兰"), ("NZ", "新西兰"), ("New Zealand", "新西兰"),
    ("哈萨克", "哈萨克斯坦"), ("KZ", "哈萨克斯坦"),
    ("立陶宛", "立陶宛"), ("LT", "立陶宛"), ("Lithuania", "立陶宛"),
    ("爱沙尼亚", "爱沙尼亚"), ("EE", "爱沙尼亚"),
    ("拉脱维亚", "拉脱维亚"), ("LV", "拉脱维亚"),
    ("保加利亚", "保加利亚"), ("BG", "保加利亚"),
]

_FLAG_RE = re.compile("[\U0001F1E6-\U0001F1FF]{2}")
_AD_RE = re.compile(
    r"(https?://\S+|t\.me/\S+|@\S+\.(?:com|net|cn|org)|"
    r"官网|续费|剩余流量|套餐|到期|过期|重置|流量[:：]|过期时间|请勿|禁止|禁止白嫖|"
    r"广告|推广|机场|邀请码|注册|首月|折扣|优惠|群组|TG群|电报群|客服)", re.I)


def guess_country(name: str) -> str:
    n = name or ""
    # 1) 直接带国旗
    for flag, country in ALIAS:
        if flag in n and len(flag) == 4:  # 区域指示符
            return country
    # 2) 关键字（先长串，避免 "IN" 命中 "China" 之类）
    for key, country in sorted(ALIAS, key=lambda x: -len(x[0])):
        if len(key) == 4:
            continue
        if re.search(r"(?<![A-Za-z])" + re.escape(key) + r"(?![A-Za-z])", n) if key.isascii() else (key in n):
            return country
    return "其他"


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3\u25A0-\u25FF\u2605\u2606]")
_EMOJI_RE_KEEP_FLAG = re.compile(
    "(?<![\U0001F1E6-\U0001F1FF])[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3]")
_HEXTAIL = re.compile(r"[_\-]?[0-9a-f]{6,}$", re.I)
_DOMAINTOK = re.compile(r"[A-Za-z0-9\-]+\.(?:com|net|org|xyz|top|cc|io|me|info|club|vip|site|online|shop|dev|app|link|fun|space|tech|cn|hk|tw|jp|us|uk|de|nl|sg|kr|ru)\b", re.I)


def clean_name(name: str) -> str:
    n = _FLAG_RE.sub("", name or "")
    n = _AD_RE.sub(" ", n)
    n = _DOMAINTOK.sub(" ", n)
    n = _EMOJI_RE_KEEP_FLAG.sub(" ", n)
    n = _HEXTAIL.sub("", n.strip())
    n = re.sub(r"[\[\]【】()（）<>《》|@#*~^`]+", " ", n)
    n = n.replace("_", " ")
    n = re.sub(r"\s+", " ", n).strip(" -_·.,:：")
    # 去掉纯协议名/无意义 token
    toks = [t for t in n.split(" ") if t and not re.fullmatch(r"(?i)(vmess|vless|ss|ssr|trojan|hy2?|hysteria2?|tuic|node|speednode|relay|cdn|ws|grpc|tls)", t)]
    n = " ".join(toks)
    return n[:18].strip()


def display_name(raw: str, idx: int) -> str:
    country = guess_country(raw)
    flag = FLAGS.get(country, "🌐")
    tag = clean_name(raw)
    base = f"{flag} {country} {idx:02d}"
    return f"{base} · {tag}" if tag else base


# ---------------------------------------------------------------- 工具
def _b64d(s: str) -> str:
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s).decode("utf-8", "ignore")


def _q(url_query: str) -> dict:
    return {k: v[0] for k, v in up.parse_qs(url_query, keep_blank_values=True).items()}


def _truthy(v) -> bool:
    return str(v).lower() in ("1", "true", "yes")


def _ws_opts(q: dict) -> dict:
    opt = {"path": q.get("path") or "/"}
    host = q.get("host") or q.get("sni")
    if host:
        opt["headers"] = {"Host": host}
    return opt


# ---------------------------------------------------------------- 分享链接 -> dict
def parse_uri(uri: str):
    uri = uri.strip()
    if not uri or "#" in uri and uri.startswith("#"):
        return None
    try:
        if uri.startswith("vmess://"):
            return _vmess(uri[8:])
        if uri.startswith("vless://"):
            return _vless(uri[8:])
        if uri.startswith("ss://"):
            return _ss(uri[5:])
        if uri.startswith("trojan://"):
            return _trojan(uri[9:])
        if uri.startswith("hysteria2://") or uri.startswith("hy2://"):
            return _hy2(re.sub(r"^(hysteria2|hy2)://", "", uri))
        if uri.startswith("tuic://"):
            return _tuic(uri[7:])
    except Exception:
        return None
    return None


def _vmess(body: str):
    raw = _b64d(body)
    j = json.loads(raw)
    net = (j.get("net") or "tcp").lower()
    tls = (j.get("tls") or "").lower() in ("tls", "reality", "xtls")
    p = {
        "type": "vmess",
        "server": j.get("add"),
        "port": int(j.get("port") or 0),
        "uuid": j.get("id"),
        "alterId": int(j.get("aid") or 0),
        "cipher": j.get("scy") or "auto",
        "udp": True,
        "name": j.get("ps") or "",
    }
    if tls:
        p["tls"] = True
        sni = j.get("sni") or j.get("host")
        if sni:
            p["servername"] = sni
    if net == "ws":
        p["network"] = "ws"
        p["ws-opts"] = {"path": j.get("path") or "/"}
        if j.get("host"):
            p["ws-opts"]["headers"] = {"Host": j["host"]}
    elif net == "grpc":
        p["network"] = "grpc"
        p["grpc-opts"] = {"grpc-service-name": j.get("path") or ""}
    elif net in ("h2", "http"):
        p["network"] = "h2"
        p["h2-opts"] = {"path": j.get("path") or "/", "host": [j.get("host")] if j.get("host") else []}
    elif net == "tcp" and (j.get("type") or "").lower() == "http":
        p["network"] = "http"
    return p


def _vless(body: str):
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        frag = up.unquote(frag)
    head, _, qs = body.partition("?")
    q = _q(qs)
    ui, _, hp = head.rpartition("@")
    host, _, port = hp.rpartition(":")
    sec = (q.get("security") or "none").lower()
    p = {
        "type": "vless",
        "server": host.strip("[]"),
        "port": int(port),
        "uuid": up.unquote(ui),
        "udp": True,
        "name": frag,
    }
    if q.get("flow"):
        p["flow"] = q["flow"]
    if sec in ("tls", "reality"):
        p["tls"] = True
        p["servername"] = q.get("sni") or q.get("host") or ""
        if q.get("fp"):
            p["client-fingerprint"] = q["fp"]
        if q.get("alpn"):
            p["alpn"] = q["alpn"].split(",")
        if sec == "reality":
            p["reality-opts"] = {"public-key": q.get("pbk", ""), "short-id": q.get("sid", "")}
        if _truthy(q.get("allowInsecure")):
            p["skip-cert-verify"] = True
    net = (q.get("type") or "tcp").lower()
    if net == "ws":
        p["network"] = "ws"
        p["ws-opts"] = _ws_opts(q)
    elif net == "grpc":
        p["network"] = "grpc"
        p["grpc-opts"] = {"grpc-service-name": q.get("serviceName") or ""}
    elif net == "h2":
        p["network"] = "h2"
        p["h2-opts"] = {"path": q.get("path") or "/", "host": [q.get("host")] if q.get("host") else []}
    return p


def _ss(body: str):
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        frag = up.unquote(frag)
    body = body.split("?")[0]
    if "@" in body:
        u, hp = body.rsplit("@", 1)
        if ":" in u and "=" not in u:  # 明文 method:pass
            method, _, password = u.partition(":")
        else:
            dec = _b64d(u)
            method, _, password = dec.partition(":")
        method, password = up.unquote(method), up.unquote(password)
        host, _, port = hp.rpartition(":")
    else:
        dec = _b64d(body)
        up_, _, hp = dec.rpartition("@")
        method, _, password = up_.partition(":")
        host, _, port = hp.rpartition(":")
    return {
        "type": "ss", "server": host.strip("[]"), "port": int(port),
        "cipher": method, "password": password, "udp": True, "name": frag,
    }


def _trojan(body: str):
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        frag = up.unquote(frag)
    head, _, qs = body.partition("?")
    q = _q(qs)
    pw, _, hp = head.rpartition("@")
    host, _, port = hp.rpartition(":")
    p = {
        "type": "trojan", "server": host.strip("[]"), "port": int(port),
        "password": up.unquote(pw), "udp": True, "name": frag,
        "sni": q.get("sni") or q.get("peer") or "",
    }
    if _truthy(q.get("allowInsecure")) or _truthy(q.get("insecure")):
        p["skip-cert-verify"] = True
    if q.get("type") == "ws":
        p["network"] = "ws"
        p["ws-opts"] = _ws_opts(q)
    elif q.get("type") == "grpc":
        p["network"] = "grpc"
        p["grpc-opts"] = {"grpc-service-name": q.get("serviceName") or ""}
    if not p["sni"]:
        p.pop("sni")
    return p


def _hy2(body: str):
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        frag = up.unquote(frag)
    head, _, qs = body.partition("?")
    q = _q(qs)
    pw, _, hp = head.rpartition("@")
    host, _, port = hp.rpartition(":")
    return {
        "type": "hysteria2", "server": host.strip("[]"), "port": int(port),
        "password": up.unquote(pw), "name": frag,
        "sni": q.get("sni") or q.get("peer") or "",
        "skip-cert-verify": _truthy(q.get("insecure")),
        "obfs": q.get("obfs") or None,
        "obfs-password": q.get("obfs-password") or None,
    }


def _tuic(body: str):
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        frag = up.unquote(frag)
    head, _, qs = body.partition("?")
    q = _q(qs)
    cred, _, hp = head.rpartition("@")
    uuid, _, pw = cred.partition(":")
    host, _, port = hp.rpartition(":")
    return {
        "type": "tuic", "server": host.strip("[]"), "port": int(port),
        "uuid": uuid, "password": up.unquote(pw), "name": frag,
        "sni": q.get("sni") or "", "alpn": (q.get("alpn") or "h3").split(","),
        "congestion-controller": q.get("congestion_control") or "bbr",
        "udp-relay-mode": q.get("udp_relay_mode") or "native",
        "skip-cert-verify": _truthy(q.get("allow_insecure")),
    }


# ---------------------------------------------------------------- 校验 / 归一
SUPPORTED = {"ss", "ssr", "vmess", "vless", "trojan", "hysteria", "hysteria2", "tuic", "wireguard", "http", "socks5", "anytls"}

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]*$")
_B64_RE = re.compile(r"^[A-Za-z0-9_\-+/=]{16,}$")
SS_CIPHERS = {
    "aes-128-gcm", "aes-192-gcm", "aes-256-gcm", "aes-128-cfb", "aes-192-cfb", "aes-256-cfb",
    "aes-128-ctr", "aes-192-ctr", "aes-256-ctr", "rc4-md5", "chacha20-ietf", "xchacha20",
    "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305", "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305", "none", "plain",
}


def sanitize(p: dict) -> bool:
    """剔除内核会拒绝的字段组合，返回是否仍可用。"""
    t = str(p.get("type", "")).lower()

    if t in ("vmess", "vless"):
        u = str(p.get("uuid", ""))
        if not _UUID_RE.match(u):
            return False
        p["uuid"] = u.lower()
    if t == "tuic":
        if not _UUID_RE.match(str(p.get("uuid", ""))):
            return False

    if t == "ss":
        if str(p.get("cipher", "")).lower() not in SS_CIPHERS:
            return False

    # REALITY
    ro = p.get("reality-opts")
    if isinstance(ro, dict):
        pbk = str(ro.get("public-key", ""))
        sid = str(ro.get("short-id", "") or "")
        if not _B64_RE.match(pbk):
            p.pop("reality-opts", None)
            p["tls"] = True
        else:
            if sid.isdigit() or sid.lower() in ("true", "false", "null", "yes", "no", "on", "off", "~"):
                sid = ""
            if not _HEX_RE.match(sid) or len(sid) > 16:
                sid = ""
            sid = sid[:len(sid) - (len(sid) % 2)]
            ro["short-id"] = sid
            ro["public-key"] = pbk
    # flow
    if p.get("flow") not in (None, "", "xtls-rprx-vision"):
        p.pop("flow", None)
    # grpc / ws 选项类型
    if not isinstance(p.get("ws-opts", {}), dict):
        p.pop("ws-opts", None)
    if not isinstance(p.get("grpc-opts", {}), dict):
        p.pop("grpc-opts", None)
    # hysteria2 obfs
    if t == "hysteria2":
        if str(p.get("obfs", "")).lower() != "salamander":
            p.pop("obfs", None)
            p.pop("obfs-password", None)
        elif not p.get("obfs-password"):
            p.pop("obfs", None)
    # alpn 必须是字符串列表
    if "alpn" in p and not (isinstance(p["alpn"], list) and all(isinstance(a, str) and a for a in p["alpn"])):
        p.pop("alpn", None)
    # tls 相关布尔值统一
    for k in ("tls", "udp", "skip-cert-verify"):
        if k in p:
            p[k] = bool(p[k])
    if t in ("trojan", "hysteria2", "anytls"):
        p["tls"] = True
    return True


def valid(p: dict) -> bool:
    if not isinstance(p, dict):
        return False
    t = str(p.get("type", "")).lower()
    if t not in SUPPORTED:
        return False
    if not p.get("server") or not p.get("port"):
        return False
    try:
        port = int(p["port"])
        if not (0 < port < 65536):
            return False
        p["port"] = port
    except Exception:
        return False
    if t in ("vmess", "vless") and not p.get("uuid"):
        return False
    if t in ("ss", "trojan", "hysteria2", "anytls") and not (p.get("password") or p.get("cipher")):
        return False
    if t == "tuic" and not (p.get("uuid") and p.get("password")):
        return False
    if not sanitize(p):
        return False
    # 清掉 None / 空串字段
    for k in [k for k, v in p.items() if v is None or v == "" or v == []]:
        p.pop(k, None)
    p.pop("name", None)
    p.pop("_source", None)
    p.pop("_raw_name", None)
    p.pop("_country", None)
    p.pop("_src", None)
    p.pop("delay", None)
    return True


def fingerprint(p: dict) -> str:
    """A stable identity for dedupe. The wire options matter: the same server/uuid with two WebSocket
    paths, gRPC services or REALITY short ids are different nodes, and collapsing them dropped working
    lines (the first one seen won, whatever its path)."""
    key = json.dumps({
        k: p.get(k) for k in
        ("type", "server", "port", "uuid", "password", "cipher", "network", "servername", "sni",
         "flow", "tls", "ws-opts", "grpc-opts", "h2-opts", "reality-opts", "alpn", "obfs", "obfs-password")
    }, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(key.encode("utf-8")).hexdigest()
