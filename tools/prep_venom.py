"""Prepare image layers for the engine -> web/venom/img/*.png + web/venom/img/meta.json
- props: cropped to their opaque bbox; meta keeps the bbox on the 3840x2160 layout canvas the illustrator delivered
  (layer order: bg1 < bg2 < bg3 < character < fg1 < ... < fg5; larger number = further front)
- character layers derived in code (the original line/colour is never modified, derived layers are separate files):
  *_sil   silhouette: alpha filled with navy
  *_mono  B manga: navy lines -> black, magenta -> black, white kept
  *_monom B manga keeping the magenta accents (eyes)
  *_grey  E: luminance squeezed into mid greys
- eye boxes (magenta irises) for the "no glyph on the eyes" check
usage: python3 tools/prep_venom.py"""
import json, os
import numpy as np
from PIL import Image
from scipy import ndimage

OUT = "web/venom/img"; os.makedirs(OUT, exist_ok=True)
NAVY = np.array([0x15, 0x18, 0x3C], np.float32)
meta = {"canvas": [3840, 2160], "props": {}, "chars": {}}

def save(arr, name):
    Image.fromarray(arr.astype(np.uint8), "RGBA").save(os.path.join(OUT, name + ".png"), optimize=True)

for f in sorted(os.listdir("assets/props")):
    im = np.array(Image.open(os.path.join("assets/props", f)).convert("RGBA"))
    ys, xs = np.where(im[..., 3] > 8)
    x0, x1, y0, y1 = max(0, xs.min() - 4), min(im.shape[1], xs.max() + 5), max(0, ys.min() - 4), min(im.shape[0], ys.max() + 5)
    name = f[:-4]; save(im[y0:y1, x0:x1], name)
    # edges where the illustrator's canvas cut the drawing: these straight cuts must never be on screen
    cuts = []
    H, W = im.shape[:2]
    for row, yy in (("top", 0), ("bottom", H - 1)):
        xs_ = np.where(im[yy, :, 3] > 8)[0]
        if len(xs_) > 20: cuts.append([int(xs_.min() - x0), int(yy - y0), int(xs_.max() - x0), int(yy - y0)])
    for col, xx in (("left", 0), ("right", W - 1)):
        ys_ = np.where(im[:, xx, 3] > 8)[0]
        if len(ys_) > 20: cuts.append([int(xx - x0), int(ys_.min() - y0), int(xx - x0), int(ys_.max() - y0)])
    meta["props"][name] = dict(x=int(x0), y=int(y0), w=int(x1 - x0), h=int(y1 - y0), layer=name[:3], cuts=cuts)

def derive(src, name, scale=1.0):
    im = Image.open(src).convert("RGBA")
    if scale != 1.0: im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    a = np.array(im).astype(np.float32)
    ys, xs = np.where(a[..., 3] > 8)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    a = a[y0:y1, x0:x1]
    rgb, al = a[..., :3], a[..., 3:]
    save(a, name)
    # silhouette: navy at the top fading to near-black at the bottom (reference silhouette ~#080C26)
    ramp = np.linspace(0, 1, rgb.shape[0], dtype=np.float32)[:, None, None]
    sil_rgb = np.array([16, 19, 50], np.float32) * (1 - ramp) + np.array([9, 12, 38], np.float32) * ramp
    sil = np.concatenate([np.broadcast_to(sil_rgb, rgb.shape), al], -1); save(sil, name + "_sil")
    lum = (rgb @ np.array([0.299, 0.587, 0.114], np.float32)) / 255
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    magenta = (r > 150) & (b > 120) & (g < 110)
    m = np.clip((lum - 0.35) / 0.4, 0, 1)                       # navy line -> 0, paper -> 1
    m[magenta] = 0.0
    mono = np.stack([m * 255] * 3, -1); save(np.concatenate([mono, al], -1), name + "_mono")
    monom = mono.copy(); monom[magenta] = rgb[magenta]; save(np.concatenate([monom, al], -1), name + "_monom")
    gr = 70 + lum * 120                                          # E: mid greys, lines stay darker
    save(np.concatenate([np.stack([gr] * 3, -1), al], -1), name + "_grey")
    # eye boxes: largest magenta blobs in the upper half
    lab, n = ndimage.label(ndimage.binary_dilation(magenta, iterations=3))
    sizes = ndimage.sum(magenta, lab, range(1, n + 1))
    eyes = []
    objs = ndimage.find_objects(lab)
    for k in np.argsort(sizes)[::-1][:6]:
        sl = objs[k]
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if sizes[k] > 0.00002 * magenta.size and h < a.shape[0] * 0.08 and sl[0].start < a.shape[0] * 0.5:
            eyes.append([int(sl[1].start), int(sl[0].start), int(w), int(h)])
    eyes = sorted(eyes, key=lambda e: -e[2] * e[3])[:2]
    meta["chars"][name] = dict(w=int(a.shape[1]), h=int(a.shape[0]), crop=[int(x0), int(y0)], scale=scale, eyes=eyes)
    print(name, a.shape[1], "x", a.shape[0], "eyes", eyes)

derive("assets/character/bust.png", "bust")                    # 4096 source: close-ups / face
derive("assets/character/bust.png", "bust_m", 0.5)             # 2048: wide / mid shots (lighter to draw)
derive("assets/character/character.png", "body")               # full body: only as crop margin / key visual
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1)
print(json.dumps(meta["props"], indent=0))
