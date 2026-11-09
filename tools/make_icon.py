"""生成应用图标（云朵 + 波浪，配色与界面一致）。4 倍超采样保证边缘平滑。"""
import math
from PIL import Image, ImageDraw, ImageFilter

SS = 4                 # 超采样倍数
S = 1024               # 输出尺寸
W = S * SS

mask = Image.new("L", (W, W), 0)
d = ImageDraw.Draw(mask)
d.ellipse([int(0.20 * W), int(0.14 * W), int(0.80 * W), int(0.74 * W)], fill=255)
d.ellipse([int(0.04 * W), int(0.36 * W), int(0.50 * W), int(0.80 * W)], fill=255)
d.ellipse([int(0.52 * W), int(0.34 * W), int(0.97 * W), int(0.79 * W)], fill=255)
d.rounded_rectangle([int(0.13 * W), int(0.50 * W), int(0.88 * W), int(0.80 * W)],
                    radius=int(0.11 * W), fill=255)
mask = mask.resize((S, S), Image.LANCZOS)

# 对角渐变
grad = Image.new("RGB", (S, S))
px = grad.load()
c1, c2, c3 = (116, 201, 255), (76, 141, 250), (40, 93, 229)
for y in range(S):
    for x in range(S):
        t = (x * 0.25 + y * 0.75) / (S - 1)
        if t < 0.5:
            k = t / 0.5
            col = tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3))
        else:
            k = (t - 0.5) / 0.5
            col = tuple(int(c2[i] + (c3[i] - c2[i]) * k) for i in range(3))
        px[x, y] = col

icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
icon.paste(grad, (0, 0), mask)

# 白色高光弧（超采样后缩小）
hl = Image.new("RGBA", (W, W), (0, 0, 0, 0))
hd = ImageDraw.Draw(hl)
hd.arc([int(0.30 * W), int(0.22 * W), int(0.72 * W), int(0.64 * W)],
       start=196, end=284, fill=(255, 255, 255, 232), width=int(0.062 * W))
hl = hl.resize((S, S), Image.LANCZOS)

# 白色波浪
wv = Image.new("RGBA", (W, W), (0, 0, 0, 0))
wd = ImageDraw.Draw(wv)
pts = []
n = 60
for i in range(n + 1):
    t = i / n
    x = 0.26 * W + t * 0.50 * W
    y = 0.585 * W + math.sin(t * math.pi * 2.15 - 0.55) * 0.058 * W
    pts.append((x, y))
wd.line(pts, fill=(255, 255, 255, 255), width=int(0.060 * W), joint="curve")
r = int(0.030 * W)
for p in (pts[0], pts[-1]):
    wd.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=(255, 255, 255, 255))
wv = wv.resize((S, S), Image.LANCZOS)

icon = Image.alpha_composite(icon, hl)
icon = Image.alpha_composite(icon, wv)

bbox = icon.getbbox()
if bbox:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    side = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 1.06
    box = (int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2))
    icon = icon.crop(box).resize((S, S), Image.LANCZOS)

icon.save(r"D:\VPN\app\assets\icon.png")
icon.save(r"D:\VPN\app\assets\app.ico",
          sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon written")
