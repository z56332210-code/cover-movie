"""v2 cached assets (deterministic): concrete wall, desaturated full-res characters, blurred/shadow layers, red smears.
Writes web/img/v2/*. Run once; the renderer only loads these."""
import os
import numpy as np
from PIL import Image, ImageFilter, ImageOps

OUT = "web/img/v2"; os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(20241010)

def fbm(h, w, octaves=6, base=4):
    out = np.zeros((h, w), np.float32); amp = 1.0; tot = 0
    for o in range(octaves):
        gh, gw = base * 2 ** o + 1, int(base * 2 ** o * w / h) + 1
        g = rng.random((gh, gw)).astype(np.float32)
        layer = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
        out += layer * amp; tot += amp; amp *= 0.55
    return out / tot

# ---- concrete wall: fine, uniform; pits and grain everywhere, a few hairline cracks, no large stains
from PIL import ImageDraw
H, W = 1350, 2400
wall = np.full((H, W), 0.56, np.float32)
wall += (fbm(H, W, 3, 2) - 0.5) * 0.04                              # barely-there large variation
g = rng.normal(0, 1, (H, W)).astype(np.float32)
g = np.asarray(Image.fromarray(((g * 0.12 + 0.5) * 255).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255 - 0.5
wall += g * 0.5                                                     # fine aggregate grain
pim = Image.new("L", (W, H), 128); dr = ImageDraw.Draw(pim)
for _ in range(16000):                                              # small pits, evenly spread
    x, y = rng.uniform(0, W), rng.uniform(0, H); r = rng.choice([0.6, 0.9, 1.3, 1.8, 2.6], p=[.3, .3, .22, .13, .05])
    dr.ellipse([x - r, y - r, x + r, y + r], fill=int(128 - rng.uniform(25, 80)))
for _ in range(6000):
    x, y = rng.uniform(0, W), rng.uniform(0, H); r = rng.uniform(0.5, 1.1)
    dr.ellipse([x - r, y - r, x + r, y + r], fill=int(rng.uniform(140, 165)))
for _ in range(7):                                                  # hairline cracks
    x, y = rng.uniform(0, W), rng.uniform(0, H); ang = rng.uniform(0, np.pi)
    pts = []
    for _ in range(40):
        ang += rng.normal(0, 0.35); x += np.cos(ang) * 14; y += np.sin(ang) * 14; pts.append((x, y))
    dr.line(pts, fill=95, width=1)
wall += (np.asarray(pim.filter(ImageFilter.GaussianBlur(0.5)), np.float32) / 128 - 1) * 0.45
Image.fromarray((wall.clip(0, 1) * 255).astype(np.uint8)).save(f"{OUT}/concrete.png", optimize=True)
Image.fromarray((wall.clip(0, 1) * 255).astype(np.uint8)).resize((W // 2, H // 2)).filter(ImageFilter.GaussianBlur(5)).save(f"{OUT}/concrete_blur.png")

# ---- characters: desaturated (12%), slightly darkened whites so they sit on the wall, plus blur + wall shadow
def desat(im, s=0.12):
    rgb = np.asarray(im.convert("RGB"), np.float32) / 255
    mx, mn = rgb.max(-1), rgb.min(-1); sat = (mx - mn) / (mx + 1e-4)
    r, g_, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.degrees(np.arctan2(np.sqrt(3) * (g_ - b), 2 * r - g_ - b)) % 360
    L = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    garment = ((hue > 140) & (hue < 260) & (sat > 0.07)).astype(np.float32)          # jacket, uniform, IV fluid
    garment = np.asarray(Image.fromarray((garment * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5)), np.float32) / 255
    Lt = 0.06 + 0.64 * L ** 1.3                                                     # low contrast, whites -> ~0.77
    Lt = Lt * (1 - 0.68 * garment)                                                   # garments near black
    out = Lt[..., None] + (rgb - L[..., None]) * s * 0.6
    o = Image.fromarray((out.clip(0, 1) * 255).astype(np.uint8)); o.putalpha(im.getchannel("A")); return o
for name in ("patient", "nurse"):
    src = Image.open(f"assets/character/{name}.png").convert("RGBA")
    src.save(f"{OUT}/{name}_color.png", optimize=True)
    m = desat(src); m.save(f"{OUT}/{name}_mono.png", optimize=True)
    small = m.resize((1080, 1920), Image.LANCZOS)
    small.filter(ImageFilter.GaussianBlur(10)).save(f"{OUT}/{name}_blur.png", optimize=True)
    a = src.getchannel("A").resize((1080, 1920), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14))
    sh = Image.new("RGBA", a.size, (8, 8, 10, 0)); sh.putalpha(a); sh.save(f"{OUT}/{name}_shadow.png", optimize=True)

# ---- crimson smears (red_burst): ragged blobs, soft core, used only in accent scenes
for k in range(3):
    h, w = 1000, 1000
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) / h
    wx, wy = fbm(h, w, 4, 3) - 0.5, fbm(h, w, 4, 3) - 0.5     # domain warp
    lobes = np.zeros((h, w), np.float32)
    for _ in range(4):
        cx, cy, sx, sy = rng.uniform(.3, .7), rng.uniform(.3, .7), rng.uniform(.08, .2), rng.uniform(.03, .12)
        lobes += np.exp(-(((xx + wx * .5 - cx) / sx) ** 2 + ((yy + wy * .5 - cy) / sy) ** 2))
    tex = fbm(h, w, 7, 6)
    m = np.clip(lobes * 1.2, 0, 1) * np.clip((tex - 0.42) * 6, 0, 1)
    fib = np.clip((fbm(h, w, 6, 24) - 0.6) * 7, 0, 1) * np.clip(lobes, 0, 1) * 0.8   # torn fibres
    m = np.clip(m + fib, 0, 1)
    rgba = np.zeros((h, w, 4), np.uint8)
    core = np.clip(m * 1.6 - 0.6, 0, 1)                        # hot core goes brighter red
    rgba[..., 0] = (150 + 70 * core).astype(np.uint8); rgba[..., 1] = (12 + 20 * core).astype(np.uint8); rgba[..., 2] = (34 + 14 * core).astype(np.uint8)
    rgba[..., 3] = (m * 255).astype(np.uint8)
    Image.fromarray(rgba).filter(ImageFilter.GaussianBlur(1.2)).save(f"{OUT}/smear{k}.png", optimize=True)
print("ok", sorted(os.listdir(OUT)))
