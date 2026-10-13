#!/usr/bin/env python3
"""Lyric video renderer (nightcord v3).

    python3 tools/render.py [--preview|--final] --still 10.4 22.0 76.3      # stills (PNG)
    python3 tools/render.py [--preview|--final] [--range 0 20] [--out out.mp4] # video

--preview (default): 960x540, heavy post (grain / bloom / blur) off.
--final:             1920x1080, all post on.  Direction logic is identical in both.
"""
import argparse, json, math, os, re, subprocess, sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
FPS = 30
PLAN = json.load(open(ROOT / "plan/cutlist_draft.json"))
CUTS = PLAN["cuts"]
SCENES = {s["id"]: s for s in PLAN["scenes"]}
LT = json.load(open(ROOT / "lyrics/line_times.json"))
LINE_T = {i: t for i, t, _ in LT["lines"]}
JA = (ROOT / "lyrics/lyrics.txt").read_text(encoding="utf-8").splitlines()
PRON = (ROOT / "lyrics/pron_ko.txt").read_text(encoding="utf-8").splitlines()
KO = (ROOT / "lyrics/ko.txt").read_text(encoding="utf-8").splitlines()
DUR = PLAN["audio"]["duration"]
JUMP = PLAN["audio"]["jump_sec"]

INK = (10, 10, 11); GRAY_D = (58, 56, 57); GRAY_M = (138, 134, 136)
PAPER = (216, 214, 214); PAPER_L = (236, 235, 235); RED = (192, 22, 31)

FONT_DIR = "/usr/share/fonts/opentype/noto/"
F_XL, F_L, F_R = FONT_DIR + "NotoSerifCJK-ExtraLight.ttc", FONT_DIR + "NotoSerifCJK-Light.ttc", FONT_DIR + "NotoSerifCJK-Regular.ttc"
F_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

ART_UP = 2  # art is processed at 2x so close crops stay crisp

# eyes in char_upper.webp source pixels (for "giant type must not cover the eyes")
EYES_SRC = [(935, 415), (1030, 460)]


class Q:  # quality settings, filled by setup()
    W = 960; H = 540; s = 0.5; post = False


def setup(final):
    Q.W, Q.H = (1920, 1080) if final else (960, 540)
    Q.s = Q.W / 1920; Q.post = final


def S(v):
    return int(round(v * Q.s))


@lru_cache(None)
def font(path, size, index=0):
    return ImageFont.truetype(path, max(6, size), index=index)


def line_text(i):
    return JA[i - 1] if 1 <= i <= len(JA) else ""


# ------------------------------------------------------------------ smooth noise
def snoise(t, seed, freqs=(0.5, 0.9, 1.4)):
    r = np.random.default_rng(seed)
    ph = r.uniform(0, 2 * np.pi, len(freqs))
    return float(sum(math.sin(2 * math.pi * f * t + p) for f, p in zip(freqs, ph)) / math.sqrt(len(freqs) / 2))


# ------------------------------------------------------------------ art
@lru_cache(None)
def art(name, negative=False):
    """Monochrome high-contrast art; red (eyes / liner) kept as the single accent hue."""
    im = Image.open(ROOT / f"art/char_{name}.webp").convert("RGBA")
    im = im.resize((im.size[0] * ART_UP, im.size[1] * ART_UP), Image.LANCZOS)   # line-art upscale, then crisp curve
    a = np.asarray(im).astype(np.float32) / 255
    rgb, al = a[..., :3], a[..., 3:]
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    redness = rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2])
    rm = np.clip((redness - 0.12) / 0.25, 0, 1)[..., None]
    l = np.clip((lum - 0.10) / 0.78, 0, 1) ** 1.15                         # contrast up
    l = l * l * (3 - 2 * l)                                                 # smoothstep: crisper ink edges
    al = np.clip((al - 0.5) * 1.6 + 0.5, 0, 1)
    if negative:
        l = 1 - l
    ink, pap = np.array(INK, np.float32) / 255, np.array(PAPER, np.float32) / 255   # highlights = paper, not pure white
    mono = ink + (pap - ink) * l[..., None]
    red = np.array(RED, np.float32) / 255 * (0.55 + 0.75 * np.clip(lum, 0, 1))[..., None]
    out = mono * (1 - rm) + np.clip(red, 0, 1) * rm
    return Image.fromarray((np.concatenate([out, al], -1) * 255).astype(np.uint8), "RGBA")


CROPS = {}  # filled from build_cutlist (single source of truth)
sys.path.insert(0, str(ROOT / "tools"))
import build_cutlist as _B  # noqa: E402  (rebuilds the plan json; cheap)
CROPS = _B.CROPS


def cut_at(t):
    for i, c in enumerate(CUTS):
        if c["start"] <= t < c["start"] + c["dur"] + 1e-6:
            return i, c
    return len(CUTS) - 1, CUTS[-1]


def scene_bg(c):
    sc = c["scene"]
    nc = c.get("nochar")
    if nc in ("ink_type", "clock_type"):
        return INK
    if nc == "paper_type":
        return PAPER_L
    if c.get("type") == "black_card" or sc in (1, 2, 12, 17, 10):
        return INK
    if sc in (3, 4, 5, 14, 18):
        return PAPER_L
    if sc == 13:
        return (246, 246, 246)
    if sc in (8, 9):
        return (22, 22, 23)
    if sc == 16:
        return GRAY_D
    return PAPER


def cut_transform(ci, c, t):
    """Affine (output px -> source px) for the image layer of cut ci at time t; also returns forward map."""
    W, H = Q.W, Q.H
    u = t - c["start"]
    seed = ci * 7919 + 13
    rng = np.random.default_rng(seed)
    src, (cx, cy), w = CROPS[c["crop"]]
    im = art(src)
    if w is None:  # silhouette: whole figure fits ~86% of height
        k = im.size[1] / ART_UP / (H * 0.86)
    else:
        k = w / W
    k /= 1.04                                                   # 4% oversize, edges never empty
    relaxed = c["scene"] in (4, 16)
    push = (0.045 if relaxed else 0.03) * min(1, u / max(c["dur"], 0.01))
    breathe = 0.0075 * (1 + math.sin(2 * math.pi * 0.35 * t + seed))      # scale 1.000~1.015
    k /= (1 + push + breathe)
    drift = rng.uniform(-1, 1, 2) * (0.035 if relaxed else 0.05) * W * u / max(c["dur"], 0.5)
    # handheld: std ~0.1% of width, 0.5~1.5 Hz; rotation +-0.15 deg
    hx = snoise(t, seed + 1) * 0.001 * W * 1.0
    hy = snoise(t, seed + 2) * 0.001 * W * 1.0
    rot = c.get("rot", 0) + 0.15 * snoise(t, seed + 3, (0.6, 1.1))
    # impact shake right after a cut: 10~25 px (1920 basis), decays in ~9 frames
    amp = (25 if c.get("transition_in") == "cut_shake" else 12) * Q.s
    f = u * FPS
    if f < 10:
        decay = math.exp(-f / 3.0) * (1 - f / 10)
        hx += amp * decay * math.sin(f * 2.3 + seed)
        hy += amp * decay * math.cos(f * 2.9 + seed)
    th = math.radians(rot)
    fy = -1 if c.get("flip_v") else 1
    # out(x,y) -> centered -> rotate -> scale -> flip -> source
    ca, sa = math.cos(th), math.sin(th)
    a, b = k * ca, k * sa
    d, e = -k * sa * fy, k * ca * fy
    ox, oy = W / 2 + hx + drift[0], H / 2 + hy + drift[1]
    c0 = cx - a * ox - b * oy
    f0 = cy - d * ox - e * oy
    inv = tuple(v * ART_UP for v in (a, b, c0, d, e, f0))
    M = np.array([[a, b], [d, e]]); Mi = np.linalg.inv(M)
    def fwd(px, py):
        v = Mi @ np.array([px - c0, py - f0]); return float(v[0]), float(v[1])
    return src, inv, fwd


def image_layer(ci, c, t):
    """RGBA image layer (or None) for the cut; returns (layer, eye_boxes_on_screen)."""
    if not c.get("crop"):
        return None, []
    src, inv, fwd = cut_transform(ci, c, t)
    neg = c["scene"] in (8, 9) and c["crop"] == "silhouette"
    im = art(src, negative=neg)
    samples = [0.0]
    if Q.post:  # 180-degree shutter motion blur
        samples = [-1 / (4 * FPS), 0.0, 1 / (4 * FPS)]
    acc = None
    for dt in samples:
        _, inv2, _ = cut_transform(ci, c, t + dt) if dt else (src, inv, fwd)
        L = im.transform((Q.W, Q.H), Image.AFFINE, inv2, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
        acc = L if acc is None else Image.blend(acc, L, 1 / (samples.index(dt) + 1))
    eyes = []
    if src == "upper":
        for ex, ey in EYES_SRC:
            px, py = fwd(ex, ey)
            r = 70 / (CROPS[c["crop"]][2] or 2000) * Q.W
            eyes.append((px - r, py - r * 0.7, px + r, py + r * 0.7))
    if c["scene"] == 16:  # grayscale photo-ish: lower contrast, slight blur
        acc = Image.blend(acc, acc.filter(ImageFilter.GaussianBlur(S(2))), 0.5)
    return acc, eyes


# ------------------------------------------------------------------ lyric chunking (segmentation only, no new words)
_SPLIT = re.compile(r"(?=その)|(?<=っぽいな)|(?<=ぽいな)|(?<=」)|(?<=じゃん)|(?<=いぜ)|(?<=いね)|(?<=…)|(?<=！)|(?<=チュー)|(?<=健康)|(?<=哀愁)|(?<=ネタバレ)|(?<=卑怯)|(?<=畢竟)|(?<=比況)|(?=それ)")


@lru_cache(None)
def chunks(i):
    s = line_text(i).replace('"', "")
    parts = [p for p in _SPLIT.split(s) if p]
    out = []
    for p in parts:
        if out and (len(p) <= 1 or len(out[-1]) <= 1):
            out[-1] += p
        else:
            out.append(p)
    res = []
    for p in out:
        while len(p) > 10:
            cand = [k + 1 for k, ch in enumerate(p[:-2]) if ch in "でにはをのてがとも" and 2 <= k + 1 <= len(p) - 2]
            cut = min(cand, key=lambda k: abs(k - len(p) / 2)) if cand else len(p) // 2
            res.append(p[:cut]); p = p[cut:]
        res.append(p)
    return tuple(res)


def active_line(t):
    cur = None
    for i, lt in LINE_T.items():
        if lt <= t:
            cur = i
    if cur is None or t >= LT["end_sec"] + 1.5:
        return None
    return cur


# ------------------------------------------------------------------ text primitives
@lru_cache(4096)
def vbox(text, size, fg=PAPER_L, bg=INK, pad=0.32, fontpath=F_L):
    """Black box with white vertical (top-to-bottom) text."""
    f = font(fontpath, size)
    bb = f.getbbox(text, direction="ttb", features=["vert"])
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    p = int(size * pad)
    im = Image.new("RGBA", (tw + 2 * p, th + 2 * p), bg + (255,) if bg else (0, 0, 0, 0))
    ImageDraw.Draw(im).text((p - bb[0], p - bb[1]), text, font=f, fill=fg + (255,), direction="ttb", features=["vert"])
    return im


_SH = {}


def box_shadow(box):
    if id(box) in _SH:
        return _SH[id(box)]
    _SH[id(box)] = _box_shadow(box); return _SH[id(box)]


def _box_shadow(box):
    a = box.getchannel("A").filter(ImageFilter.GaussianBlur(max(1, S(6))))
    im = Image.new("RGBA", box.size, INK + (0,)); im.putalpha(a); return im


@lru_cache(512)
def htext(text, size, fill, fontpath=F_XL, stroke=0):
    f = font(fontpath, size)
    bb = f.getbbox(text, stroke_width=stroke)
    im = Image.new("RGBA", (bb[2] - bb[0] + 4, bb[3] - bb[1] + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - bb[0], 2 - bb[1]), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=fill)
    return im


@lru_cache(512)
def vtext(text, size, fill, fontpath=F_XL):
    f = font(fontpath, size)
    bb = f.getbbox(text, direction="ttb", features=["vert"])
    im = Image.new("RGBA", (bb[2] - bb[0] + 4, bb[3] - bb[1] + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - bb[0], 2 - bb[1]), text, font=f, fill=fill, direction="ttb", features=["vert"])
    return im


def paste(dst, im, x, y, alpha=1.0):
    if alpha < 1:
        im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    dst.alpha_composite(im, (int(x), int(y))) if 0 <= x and 0 <= y and x + im.size[0] <= dst.size[0] and y + im.size[1] <= dst.size[1] \
        else dst.paste(im, (int(x), int(y)), im)


def overlap_area(box, boxes):
    x0, y0, x1, y1 = box
    return sum(max(0, min(x1, c) - max(x0, a)) * max(0, min(y1, d) - max(y0, b)) for a, b, c, d in boxes)


def best_pos(cands, w, h, eyes):
    return min(cands, key=lambda p: (overlap_area((p[0], p[1], p[0] + w, p[1] + h), eyes), cands.index(p)))


def overlaps(box, boxes):
    x0, y0, x1, y1 = box
    return any(not (x1 < a or x0 > c or y1 < b or y0 > d) for a, b, c, d in boxes)


# ------------------------------------------------------------------ text levels
def text_A(L, t, c, stack_size, side="right", mirror=False, max_lines=3):
    """Small vertical lyric boxes; chunks of the current line appear one by one, older lines stay (2~3 deep)."""
    li = active_line(t)
    if li is None:
        return
    cols = []
    for k, i in enumerate(range(li, max(0, li - max_lines), -1)):
        if i < 1 or (k > 0 and t - LINE_T[i] > 9):
            break
        ch = chunks(i)
        span = (LINE_T.get(i + 1, LT["end_sec"]) - LINE_T[i])
        n_vis = len(ch) if k > 0 else max(1, min(len(ch), 1 + int((t - LINE_T[i]) / max(span, 0.3) * len(ch) * 1.6)))
        cols.append((k, ch[:n_vis]))
    size = S(stack_size)
    gap = int(size * 0.35)
    x = Q.W - S(120) if side == "right" else S(120)
    order = []
    for k, ch in cols:
        for j, piece in enumerate(ch):
            order.append((k, j, piece))
    total, kept = 0, []
    for k, ch in cols:                       # at most ~6 columns on screen
        if total + len(ch) > 6 and kept:
            break
        kept.append((k, ch)); total += len(ch)
    cols = kept
    # right-to-left columns (vertical writing): newest line at the outer edge
    xs = x
    y0 = S(90)
    for k, ch in cols:
        for j, piece in enumerate(ch):
            box = vbox(piece, size)
            age_alpha = [1.0, 0.82, 0.6][min(k, 2)]
            yy = y0 + (j % 2) * S(54) + k * S(36)
            if side == "right":
                xs -= box.size[0] + gap; px = xs + gap
            else:
                px = xs; xs += box.size[0] + gap
            sh = box_shadow(box)
            if mirror:  # mirror-symmetric twin on the other side
                paste(L, sh, Q.W - px - box.size[0] + S(7), yy + S(9), age_alpha * 0.45)
                paste(L, box, Q.W - px - box.size[0], yy, age_alpha * 0.9)
            paste(L, sh, px + S(7), yy + S(9), age_alpha * 0.45)
            paste(L, box, px, yy, age_alpha)


def text_B(L, t, c, eyes, color, text=None, size_h=0.42, rows=None, slide=0.12):
    """Giant thin serif, cropped off-frame, slides; placed to avoid the eyes."""
    li = active_line(t)
    if text is None:
        if li is None:
            return
        text = line_text(li).replace('"', "")
    pieces = rows or ([text] if len(text) <= 7 else [text[:len(text) // 2 + (len(text) % 2)], text[len(text) // 2 + (len(text) % 2):]])
    size = int(Q.H * size_h / (1 if len(pieces) == 1 else 1.55))
    u = (t - c["start"]) / max(c["dur"], 0.3)
    for r, p in enumerate(pieces):
        im = htext(p, size, color + (235,))
        x = Q.W * 0.5 - im.size[0] / 2 + (0.5 - u) * Q.W * slide * (1 if r % 2 == 0 else -1)
        ys = [Q.H * 0.5 - im.size[1] / 2 + (r - (len(pieces) - 1) / 2) * size * 1.05,
              Q.H * 0.62 - im.size[1] / 2 + r * size, Q.H * 0.08 + r * size, Q.H * 0.70 + r * size * 0.9]
        x, y = best_pos([(x, yy) for yy in ys], im.size[0], im.size[1], eyes)
        paste(L, im, x, y)


def text_D(L, t, c, color, rows=1, size_h=0.14, echo=True):
    """Repeat band: the onomatopoeia line repeated across the full width, scrolling."""
    li = active_line(t)
    if li is None:
        return
    s = line_text(li).replace('"', "")
    size = int(Q.H * size_h)
    im = htext(s + "　", size, color + (230,), F_L)
    ghost = htext(s + "　", size, color + (90,), F_XL)
    for r in range(rows):
        y = Q.H / 2 - size * 0.62 if rows == 1 else Q.H * (r + 0.5) / rows - size * 0.6
        off = ((t * Q.W * 0.06 * (1 if r % 2 == 0 else -1.3)) % im.size[0])
        x = -off - im.size[0]
        while x < Q.W:
            if echo:
                paste(L, ghost, x + size * 0.06, y + size * 0.05)
            paste(L, im, x, y)
            x += im.size[0]


def caption(img, t):
    """Korean pronunciation + translation, small and thin, bottom centre, colour adapts to background."""
    li = active_line(t)
    if li is None:
        return
    a = PRON[li - 1].strip(); b = KO[li - 1].strip()
    region = img.crop((Q.W // 4, Q.H - S(120), Q.W * 3 // 4, Q.H - S(20))).convert("L")
    dark = np.asarray(region).mean() < 128
    col = PAPER_L if dark else INK
    f1, f2 = font(F_L, S(25), 1), font(F_L, S(21), 1)
    d = ImageDraw.Draw(img)
    for txt, f, y, al in ((a, f1, Q.H - S(86), 235), (b, f2, Q.H - S(50), 205)):
        w = d.textlength(txt, font=f)
        d.text((Q.W / 2 - w / 2, y), txt, font=f, fill=col + (al,))


# ------------------------------------------------------------------ overlays (pre-rendered per resolution)
@lru_cache(None)
def hud_layer():
    W, H = Q.W, Q.H
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    col = GRAY_M + (255,)
    m1, m2 = S(26), S(34)
    lw = max(1, S(1.5))
    d.rectangle((m1, m1, W - m1, H - m1), outline=col, width=lw)
    d.rectangle((m2, m2, W - m2, H - m2), outline=col, width=max(1, S(1)))
    for (x, y, sx, sy) in ((m1, m1, 1, 1), (W - m1, m1, -1, 1), (m1, H - m1, 1, -1), (W - m1, H - m1, -1, -1)):
        d.line((x, y + sy * S(46), x + sx * S(46), y), fill=col, width=lw)                     # corner bevel
        d.ellipse((x + sx * S(14) - S(5), y + sy * S(14) - S(5), x + sx * S(14) + S(5), y + sy * S(14) + S(5)), outline=col, width=lw)
        d.line((x + sx * S(58), y + sy * S(3), x + sx * S(96), y + sy * S(3)), fill=col, width=1)
    for k in range(40):  # tick rows top / bottom
        x = W * 0.3 + k * W * 0.4 / 39
        hgt = S(7) if k % 5 == 0 else S(3)
        d.line((x, m2 + S(4), x, m2 + S(4) + hgt), fill=col, width=1)
        d.line((x, H - m2 - S(4), x, H - m2 - S(4) - hgt), fill=col, width=1)
    for cx in (W / 2,):
        for y in (m1, H - m1):
            d.ellipse((cx - S(9), y - S(9), cx + S(9), y + S(9)), fill=(0, 0, 0, 0), outline=col, width=lw)
            d.ellipse((cx - S(3), y - S(3), cx + S(3), y + S(3)), fill=col)
    f = font(F_MONO, S(13))
    d.text((m2 + S(16), m2 + S(14)), "25:00 // NIGHTCORD", font=f, fill=col)
    tr = "KAMIPPOINA — cover"
    d.text((W - m2 - S(16) - d.textlength(tr, font=f), m2 + S(14)), tr, font=f, fill=col)
    return L


def hud_dynamic(L, t, alpha):
    d = ImageDraw.Draw(L)
    col = GRAY_M + (int(255 * alpha),)
    f = font(F_MONO, S(13))
    fr = int(t * FPS)
    tc = f"{fr // (FPS * 3600):02d}:{fr // (FPS * 60) % 60:02d}:{fr // FPS % 60:02d}:{fr % FPS:02d}"
    m2 = S(34)
    d.text((m2 + S(16), Q.H - m2 - S(28)), "TC " + tc, font=f, fill=col)
    s = f"BPM 142.4   CUT {cut_at(t)[0] + 1:03d}"
    d.text((Q.W - m2 - S(16) - d.textlength(s, font=f), Q.H - m2 - S(28)), s, font=f, fill=col)


@lru_cache(None)
def clock_ring(color):
    R = int(Q.H * 0.40); P = S(60)
    size = 2 * (R + P)
    L = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    c = size / 2; col = color + (255,)
    for rr, wdt in ((R, max(1, S(2))), (R - S(10), 1), (R - S(92), 1)):
        d.ellipse((c - rr, c - rr, c + rr, c + rr), outline=col, width=wdt)
    for k in range(60):
        a = 2 * math.pi * k / 60
        r0 = R - (S(26) if k % 5 == 0 else S(16))
        d.line((c + r0 * math.sin(a), c - r0 * math.cos(a), c + (R - S(10)) * math.sin(a), c - (R - S(10)) * math.cos(a)), fill=col, width=1)
    nums = ["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"]
    f = font(F_L, S(44))
    for k, n in enumerate(nums):
        a = 2 * math.pi * k / 12
        g = htext(n, S(44), col, F_L).rotate(-math.degrees(a), resample=Image.BICUBIC, expand=True)
        rr = R - S(58)
        L.alpha_composite(g, (int(c + rr * math.sin(a) - g.size[0] / 2), int(c - rr * math.cos(a) - g.size[1] / 2)))
    return L


def draw_clock(L, t, cx, cy, color, alpha, scale=1.0):
    ring = clock_ring(color)
    if scale != 1.0:
        ring = ring.resize((int(ring.size[0] * scale), int(ring.size[1] * scale)), Image.BICUBIC)
    r = ring.rotate(-t * 6.0, resample=Image.BICUBIC)
    paste(L, r, cx - r.size[0] / 2, cy - r.size[1] / 2, alpha)
    d = ImageDraw.Draw(L)
    col = color + (int(255 * alpha),)
    R = Q.H * 0.40 * scale
    step = math.floor(t / 1.6855)                    # minute hand jumps every bar, with a small overshoot
    ph = (t / 1.6855) % 1
    ang = step * 30 + (8 * math.exp(-ph * 12) * math.sin(ph * 30))
    for a, ln, wdt in ((ang, R * 0.78, max(1, S(2))), (ang / 12 + 140, R * 0.5, max(1, S(4)))):
        ar = math.radians(a)
        d.line((cx, cy, cx + ln * math.sin(ar), cy - ln * math.cos(ar)), fill=col, width=wdt)
    d.ellipse((cx - S(8), cy - S(8), cx + S(8), cy + S(8)), outline=col, width=max(1, S(2)))


@lru_cache(None)
def streak_layer():
    W, H = Q.W, Q.H
    L = Image.new("L", (int(W * 1.6), int(H * 1.6)), 0); d = ImageDraw.Draw(L)
    r = np.random.default_rng(5)
    for k in range(7):
        x = r.uniform(0, L.size[0]); w = r.uniform(30, 160) * Q.s
        d.polygon([(x, 0), (x + w, 0), (x + w - L.size[1] * 0.6, L.size[1]), (x - L.size[1] * 0.6, L.size[1])], fill=int(r.uniform(120, 255)))
    return L.filter(ImageFilter.GaussianBlur(S(60)))


@lru_cache(None)
def smoke_tex():
    r = np.random.default_rng(9)
    small = Image.fromarray((r.random((40, 72)) * 255).astype(np.uint8), "L").resize((int(Q.W * 1.5), int(Q.H * 1.5)), Image.BICUBIC)
    return small.filter(ImageFilter.GaussianBlur(S(40)))


@lru_cache(None)
def vignette():
    W, H = Q.W, Q.H
    y, x = np.mgrid[0:H, 0:W]
    d = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    v = 1 - 0.42 * np.clip(d - 0.45, 0, 1) ** 1.3
    return Image.fromarray((v * 255).astype(np.uint8), "L")


@lru_cache(None)
def paper_tex():
    r = np.random.default_rng(3)
    n = r.normal(0, 1, (Q.H // 2, Q.W // 2)).astype(np.float32)
    im = Image.fromarray(np.clip(128 + n * 9, 0, 255).astype(np.uint8), "L").resize((Q.W, Q.H), Image.BICUBIC)
    return im.filter(ImageFilter.GaussianBlur(max(1, S(1.2))))


def ambient(img, t, dark):
    """Diagonal light streaks (screen 10~20%), dust, smoke / ink wash."""
    W, H = Q.W, Q.H
    st = streak_layer()
    ox = int((t * 18 * Q.s) % (st.size[0] - W)); oy = int(st.size[1] * 0.15)
    s = st.crop((ox, oy, ox + W, oy + H))
    amt = 0.16 if dark else 0.10
    light = Image.merge("RGB", [s.point(lambda v: int(v * amt))] * 3)
    img = ImageChops.screen(img, light)
    sm = smoke_tex()
    sx = int((t * 9 * Q.s) % (sm.size[0] - W)); sy = int((t * 5 * Q.s) % (sm.size[1] - H))
    s2 = sm.crop((sx, sy, sx + W, sy + H))
    if dark:
        img = ImageChops.screen(img, Image.merge("RGB", [s2.point(lambda v: int(max(0, v - 135) * 0.16))] * 3))
    else:
        img = ImageChops.multiply(img, Image.merge("RGB", [s2.point(lambda v: 255 - int(max(0, v - 130) * 0.22))] * 3))
    d = ImageDraw.Draw(img)
    r = np.random.default_rng(77)
    n = 30
    px = r.uniform(0, 1, n); py = r.uniform(0, 1, n); sp = r.uniform(0.01, 0.04, n); sz = r.uniform(1, 3.2, n)
    for k in range(n):
        x = ((px[k] + t * sp[k] * 0.6) % 1) * W
        y = ((py[k] - t * sp[k]) % 1) * H + math.sin(t * 0.7 + k) * S(6)
        rad = sz[k] * Q.s * 1.3
        col = (PAPER_L if dark else GRAY_D) + (0,)
        d.ellipse((x - rad, y - rad, x + rad, y + rad), fill=col[:3])
    return img


# ------------------------------------------------------------------ MV motifs
def starburst(L, cx, cy, R, t, seed, color=RED, alpha=1.0):
    r = np.random.default_rng(seed)
    n = int(r.integers(18, 28))
    rot = t * 20 + seed
    pts = []
    for k in range(2 * n):
        a = math.pi * k / n + math.radians(rot)
        rr = R * (1.0 if k % 2 == 0 else r.uniform(0.62, 0.78))
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d = ImageDraw.Draw(L)
    d.polygon(pts, fill=color + (int(255 * alpha),))
    d.ellipse((cx - R * 0.38, cy - R * 0.38, cx + R * 0.38, cy + R * 0.38), outline=PAPER_L + (int(200 * alpha),), width=max(1, S(2)))


def red_slash(L, t0, t, seed):
    u = (t - t0) * FPS / 4.0
    if u <= 0:
        return
    r = np.random.default_rng(seed)
    W, H = Q.W, Q.H
    x0, y0 = -0.05 * W, r.uniform(0.15, 0.4) * H
    x1, y1 = 1.05 * W, r.uniform(0.6, 0.9) * H
    k = min(1, u)
    xe, ye = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
    wdt = S(16)
    nx, ny = -(ye - y0), (xe - x0); ln = math.hypot(nx, ny) or 1; nx, ny = nx / ln * wdt, ny / ln * wdt
    ImageDraw.Draw(L).polygon([(x0, y0), ((x0 + xe) / 2 + nx, (y0 + ye) / 2 + ny), (xe, ye), ((x0 + xe) / 2 - nx * 0.4, (y0 + ye) / 2 - ny * 0.4)], fill=RED + (240,))


def checker_strip(L, t, angle=-18, width=150, sq=34, y_frac=0.82):
    W, H = Q.W, Q.H
    sqp = S(sq); bw = S(width)
    strip = Image.new("RGBA", (int(W * 1.6), bw), (0, 0, 0, 0)); d = ImageDraw.Draw(strip)
    off = int(t * S(60)) % (2 * sqp)
    for i in range(-2, strip.size[0] // sqp + 3):
        for j in range(bw // sqp + 1):
            col = (INK if (i + j) % 2 == 0 else (PAPER_L if j % 2 == 0 else GRAY_M)) + (235,)
            x = i * sqp - off
            d.rectangle((x, j * sqp, x + sqp - 1, j * sqp + sqp - 1), fill=col)
    strip = strip.rotate(angle, resample=Image.BICUBIC, expand=True)
    paste(L, strip, W / 2 - strip.size[0] / 2, H * y_frac - strip.size[1] / 2)


def checker_floor(L, t, blur=0.0):
    W, H = Q.W, Q.H
    floor = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(floor)
    hz = H * 0.58
    cols, rows = 16, 9
    z = (t * 0.9) % 1
    for r in range(rows + 1):
        for cidx in range(-cols, cols):
            def P(x, rr):
                depth = (rr - z + 1) / (rows + 1)
                yy = hz + (H - hz) * depth ** 1.8
                return (W / 2 + (x / cols) * W * (0.2 + 1.6 * depth ** 1.8), yy)
            if (r + cidx) % 2:
                continue
            q = [P(cidx, r), P(cidx + 1, r), P(cidx + 1, r + 1), P(cidx, r + 1)]
            d.polygon(q, fill=GRAY_M + (150,))
    if blur > 0:
        floor = floor.filter(ImageFilter.BoxBlur(S(blur)))
    L.alpha_composite(floor)


def torn_strips(L, t, seed):
    r = np.random.default_rng(seed)
    W, H = Q.W, Q.H
    for k in range(3):
        h = r.uniform(60, 130) * Q.s
        ln = W * 1.8
        strip = Image.new("RGBA", (int(ln), int(h * 1.6)), (0, 0, 0, 0)); d = ImageDraw.Draw(strip)
        top = [(x, h * 0.3 + r.uniform(-1, 1) * h * 0.12) for x in np.linspace(0, ln, 120)]
        bot = [(x, h * 1.3 + r.uniform(-1, 1) * h * 0.12) for x in np.linspace(ln, 0, 120)]
        d.polygon(top + bot, fill=(PAPER_L if k % 2 == 0 else GRAY_M) + (225,))
        strip = strip.rotate(r.uniform(15, 30) * (1 if k % 2 else -1), resample=Image.BICUBIC, expand=True)
        x = -strip.size[0] * 0.25 + ((t * 0.12 + k * 0.33) % 1 - 0.5) * W * 0.6
        paste(L, strip, x, r.uniform(-0.3, 0.6) * H)


def circle_guides(L, t, eyes, color):
    d = ImageDraw.Draw(L)
    col = color + (170,)
    if eyes:
        x0, y0, x1, y1 = eyes[0]; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    else:
        cx, cy = Q.W * 0.62, Q.H * 0.42
    for k, rr in enumerate((S(70), S(130), S(210))):
        rr = rr * (1 + 0.04 * math.sin(t * 2 + k))
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=col, width=1)
    d.line((cx - S(260), cy, cx + S(260), cy), fill=col, width=1)
    d.line((cx, cy - S(260), cx, cy + S(260)), fill=col, width=1)


def mini_icons(L, color):
    d = ImageDraw.Draw(L)
    col = color + (190,)
    x, y = Q.W - S(110), Q.H - S(150)
    d.ellipse((x - S(18), y - S(18), x + S(18), y + S(18)), outline=col, width=max(1, S(1.5)))
    d.line((x, y, x, y - S(12)), fill=col, width=1); d.line((x, y, x + S(9), y + S(4)), fill=col, width=1)
    x, y = S(110), Q.H - S(160)  # dress-form mannequin
    d.ellipse((x - S(5), y - S(30), x + S(5), y - S(20)), outline=col, width=1)
    d.polygon([(x - S(14), y - S(18)), (x + S(14), y - S(18)), (x + S(9), y + S(4)), (x + S(16), y + S(26)), (x - S(16), y + S(26)), (x - S(9), y + S(4))], outline=col)
    d.line((x, y + S(26), x, y + S(42)), fill=col, width=1); d.line((x - S(10), y + S(42), x + S(10), y + S(42)), fill=col, width=1)


@lru_cache(None)
def code_block():
    r = np.random.default_rng(11)
    f = font(F_MONO, S(11))
    lines = []
    for k in range(40):
        lines.append(" ".join(f"{int(v):04X}" for v in r.integers(0, 65535, 6)) + f"  ::{k:02d}")
    im = Image.new("RGBA", (S(330), int(len(lines) * S(15))), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for k, s in enumerate(lines):
        d.text((0, k * S(15)), s, font=f, fill=GRAY_M + (150,))
    return im


def glitch(img, t, seed, strength=1.0):
    r = np.random.default_rng(seed + int(t * FPS))
    W, H = Q.W, Q.H
    out = img.copy()
    for _ in range(int(6 * strength) + 3):
        bw = int(r.uniform(0.1, 0.5) * W); bh = int(r.uniform(0.04, 0.2) * H)
        x = int(r.uniform(0, W - bw)); y = int(r.uniform(0, H - bh))
        blk = max(4, S(r.choice([24, 32, 48, 64])))
        reg = img.crop((x, y, x + bw, y + bh))
        reg = reg.resize((max(1, bw // blk), max(1, bh // blk)), Image.BILINEAR).resize((bw, bh), Image.NEAREST)
        dx = int(r.uniform(-0.06, 0.06) * W)
        out.paste(reg, (min(max(0, x + dx), W - bw), y))
    return out


# ------------------------------------------------------------------ transitions (image layer only; text stays continuous)
def transition_state(t):
    """Returns (kind, phase in [-4..4] frames around the cut boundary, cut index of the incoming cut)."""
    f = t * FPS
    for i, c in enumerate(CUTS):
        if i == 0:
            continue
        b = c["start"] * FPS
        if -4 <= f - b < 5:
            return c.get("transition_in"), f - b, i
    return None, None, None


def dir_blur(im, px):
    if px < 1 or not Q.post:
        return im
    n = 8
    acc = None
    for k in range(n):
        o = (k / (n - 1) - 0.5) * px
        sh = ImageChops.offset(im, int(o * 0.82), int(o * 0.57))
        acc = sh if acc is None else Image.blend(acc, sh, 1 / (k + 1))
    return acc


def expose(im, amt):
    if amt <= 0:
        return im
    white = Image.new(im.mode, im.size, (255, 255, 255) + ((0,) if im.mode == "RGBA" else ()))
    if im.mode == "RGBA":
        rgb = Image.blend(im.convert("RGB"), white.convert("RGB"), min(1, amt))
        rgb.putalpha(im.getchannel("A")); return rgb
    return Image.blend(im, white, min(1, amt))


# ------------------------------------------------------------------ scene look & text routing
def text_color_for(bg):
    return INK if sum(bg) > 380 else PAPER_L


def scene_text(L, img_layer_eyes, t, c, ci, bg):
    sc = c["scene"]; typ = c.get("type")
    tc = text_color_for(bg)
    li = active_line(t)
    red = c.get("red")
    nc = c.get("nochar")
    if nc == "ink_type":       # typography only: giant thin serif + small stacked boxes
        text_B(L, t, c, [], PAPER_L, size_h=0.40, slide=0.22)
        return
    if nc == "band_only":
        return                 # bands are drawn in band_text
    if nc == "clock_type":
        text_A(L, t, c, 60, side="right", mirror=True, max_lines=2)
        return
    if nc == "paper_type":
        text_A(L, t, c, 64, side="right", max_lines=3)
        return
    if nc == "empty_room":
        text_B(L, t, c, [], PAPER_L, size_h=0.32, slide=0.06)
        return
    if typ == "black_card":
        if li:
            im = htext(line_text(li), S(30), PAPER_L + (230,), F_L)
            paste(L, im, Q.W / 2 - im.size[0] / 2, Q.H / 2 - im.size[1] / 2)
        return
    if sc == 1:
        if t > 5.5 and li == 1:
            im = htext("“Oh my god”", S(28), PAPER_L + (220,), F_L)
            paste(L, im, Q.W / 2 - im.size[0] / 2, Q.H / 2 - im.size[1] / 2)
        else:
            a = min(1, t / 3)
            im = htext("神っぽいな", S(54), PAPER_L + (int(220 * a),), F_XL)
            paste(L, im, Q.W / 2 - im.size[0] / 2, Q.H / 2 - S(60))
            im2 = htext("cover  /  25時、ナイトコードで。", S(18), GRAY_M + (int(220 * a),), F_L)
            paste(L, im2, Q.W / 2 - im2.size[0] / 2, Q.H / 2 + S(30))
        return
    if sc in (2, 12):
        text_A(L, t, c, 58 if sc == 2 else 62, side="right" if (ci % 2) else "left")
    elif sc == 3:
        if li == 13:
            text_B(L, t, c, img_layer_eyes, tc, text="神っぽいな", size_h=0.5)
    elif sc == 4:
        text_A(L, t, c, 44, side="right")
    elif sc == 5:
        text_A(L, t, c, 44, side="right", mirror=True, max_lines=2)
        text_B(L, t, c, img_layer_eyes, tc, size_h=0.36)
    elif sc in (6, 15):
        if li in (63,):
            text_B(L, t, c, img_layer_eyes, tc, text="神っぽいな", size_h=0.55, slide=0.25)
        text_A(L, t, c, 70 if sc == 6 else 76, side="right", mirror=(sc == 15))
    elif sc == 7:
        if red:
            word = "憧れちゃう！" if li == 34 else "神っぽいな"
            text_C(L, t, c, word, img_layer_eyes, horizontal=(li == 34))
        else:
            text_A(L, t, c, 86, side="right", max_lines=2)
    elif sc == 9:
        if li == 42:
            text_B(L, t, c, [], PAPER_L, text="神っぽいな", size_h=0.5, slide=0.4)
    elif sc == 10:
        pass
    elif sc == 11:
        if red:
            text_C(L, t, c, "神っぽいな", img_layer_eyes, horizontal=False)
        else:
            text_A(L, t, c, 64, side="left")
    elif sc == 13:
        text_A(L, t, c, 44, side="right", max_lines=1)
    elif sc == 14:
        if red:
            text_C(L, t, c, "憧" if li == 55 else "風", [], horizontal=True, center=True)
    elif sc == 16:
        text_B(L, t, c, img_layer_eyes, PAPER_L, size_h=0.30, slide=0.08)
    elif sc == 17:
        if li == 68:
            im = htext("人生", S(120), PAPER_L + (235,), F_XL)
        else:
            im = htext(line_text(li) if li else "", S(30), PAPER_L + (220,), F_L)
        paste(L, im, Q.W / 2 - im.size[0] / 2, Q.H / 2 - im.size[1] / 2)


def band_text(L, t, c, bg):
    sc = c["scene"]; li = active_line(t); tc = text_color_for(bg)
    if c.get("nochar") == "band_only":   # full-screen repeat grid, no figure (ref B t081)
        text_D(L, t, c, GRAY_M if sc == 8 else tc, rows=5, size_h=0.13)
        return
    if sc == 3 and li != 13:
        text_D(L, t, c, tc)
    elif sc == 8:
        text_D(L, t, c, GRAY_M, rows=1, size_h=0.15)
    elif sc == 9 and li != 42:
        text_D(L, t, c, GRAY_M)
    elif sc == 14:
        rows = 5 if li in (56, 57, 58) else 1
        text_D(L, t, c, tc, rows=rows, size_h=0.13 if rows > 1 else 0.14)


def text_C(L, t, c, word, eyes, horizontal=False, center=False):
    """Red keyword, half the screen, thin serif."""
    if horizontal:
        size = int(Q.H * (0.66 if center else 0.34))
        im = htext(word, size, RED + (245,), F_R if center else F_L)
        u = (t - c["start"]) / max(c["dur"], 0.3)
        x = Q.W / 2 - im.size[0] / 2 + (0.5 - u) * Q.W * 0.05
        y = Q.H / 2 - im.size[1] / 2
        if not center:
            x, y = best_pos([(x, Q.H * f - im.size[1] / 2) for f in (0.68, 0.50, 0.30, 0.76, 0.20)], im.size[0], im.size[1], eyes)
        paste(L, im, x + S(26), y + S(14), 0.28)       # offset echo (ref B doubles its big type)
        paste(L, im, x, y, 0.93)
    else:
        size = int(Q.H * 0.34)
        im = vtext(word, size, RED + (245,), F_L)
        y = -size * 0.2 + (t - c["start"]) * S(60)
        x, _ = best_pos([(Q.W * f, y) for f in (0.05, 0.80, 0.02, 0.86, 0.40)], im.size[0], im.size[1], eyes)
        paste(L, im, x + S(22), y + S(30), 0.28)
        paste(L, im, x, y, 0.93)


CROP_SCENES = (2, 6, 7, 11, 12, 15)


def ghost_echo(img, ci, t):
    """Enlarged, blurred, faint double of the image layer behind it (ref B's after-image look)."""
    W, H = Q.W, Q.H
    k = 1.07 + 0.01 * math.sin(t * 1.3 + ci)
    g = img.resize((int(W * k), int(H * k)), Image.BILINEAR)
    g = g.crop(((g.size[0] - W) // 2 + S(18), (g.size[1] - H) // 2 - S(10), (g.size[0] - W) // 2 + S(18) + W, (g.size[1] - H) // 2 - S(10) + H))
    g = g.filter(ImageFilter.GaussianBlur(max(1, S(5))))
    g.putalpha(g.getchannel("A").point(lambda v: int(v * 0.30)))
    return g


def black_wedge(L, ci, t, c):
    """Large black shape with a torn edge that cuts across the frame (ref B crops are half swallowed by black)."""
    if ci % 4 == 3:
        return
    r = np.random.default_rng(ci * 31)
    W, H = Q.W, Q.H
    side = int(r.integers(0, 4))
    cover = r.uniform(0.22, 0.38)
    u = min(1, (t - c["start"]) * FPS / 6)
    slide = (1 - u) ** 2 * 0.08
    n = 60
    tear = lambda k: r.uniform(-1, 1) * S(10) + math.sin(k * 0.7) * S(6)
    if side in (0, 1):  # diagonal from left / right edge
        x_top = W * (cover + 0.12 - slide); x_bot = W * (cover - 0.12 - slide)
        edge = [(x_top + (x_bot - x_top) * k / n + tear(k), H * k / n) for k in range(n + 1)]
        poly = [(0, 0)] + edge + [(0, H)]
        if side == 1:
            poly = [(W - x, y) for x, y in poly]
    else:  # from top / bottom
        y_l = H * (cover + 0.1 - slide); y_r = H * (cover - 0.12 - slide)
        edge = [(W * k / n, y_l + (y_r - y_l) * k / n + tear(k)) for k in range(n + 1)]
        poly = [(0, 0)] + edge + [(W, 0)]
        if side == 3:
            poly = [(x, H - y) for x, y in poly]
    d = ImageDraw.Draw(L)
    d.polygon(poly, fill=INK + (255,))
    d.line(edge if side in (0, 2) else [(W - x, y) if side == 1 else (x, H - y) for x, y in edge], fill=GRAY_M + (150,), width=max(1, S(2)))


def slice_bars(L, ci, t, color, cx=None, cy=None):
    """Short horizontal glitch bars around the figure (ref B t024 / t081)."""
    r = np.random.default_rng(ci * 17 + int(t * 6))
    W, H = Q.W, Q.H
    cx = W / 2 if cx is None else cx; cy = H / 2 if cy is None else cy
    d = ImageDraw.Draw(L)
    for k in range(int(r.integers(3, 7))):
        w = r.uniform(0.04, 0.16) * W; h = r.uniform(0.008, 0.03) * H
        x = cx + r.uniform(-0.22, 0.14) * W; y = cy + r.uniform(-0.38, 0.38) * H
        d.rectangle((x, y, x + w, y + h), fill=color + (235,))


def speed_lines(L, t, ci, color, alpha=0.55, cx=None, cy=None):
    """Radial concentration lines (ref B t033)."""
    r = np.random.default_rng(ci * 7 + int(t * 10))
    W, H = Q.W, Q.H
    cx = W / 2 if cx is None else cx; cy = H * 0.45 if cy is None else cy
    d = ImageDraw.Draw(L)
    for k in range(70):
        a = r.uniform(0, 2 * math.pi)
        r0 = r.uniform(0.22, 0.34) * H; r1 = r0 + r.uniform(0.15, 0.55) * H
        d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
               fill=color + (int(255 * alpha * r.uniform(0.4, 1)),), width=max(1, S(r.uniform(1, 2.5))))


def smoke_wisps(L, t, ci, color=PAPER_L):
    """Curling ink-smoke strokes drifting upward (ref B cigarette smoke, here as an overlay)."""
    r = np.random.default_rng(ci * 53)
    W, H = Q.W, Q.H
    tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(tmp)
    for k in range(3):
        x0 = r.uniform(0.15, 0.85) * W; y0 = r.uniform(0.6, 1.0) * H
        ph = r.uniform(0, 6.28); amp = r.uniform(0.03, 0.08) * W
        pts = []
        for j in range(40):
            v = j / 39
            y = y0 - v * H * 0.75 - (t * S(40)) % S(120)
            x = x0 + amp * math.sin(v * 7 + ph + t * 1.2) * (0.3 + v)
            pts.append((x, y))
        for j in range(len(pts) - 1):
            wdt = max(1, int(S(12) * (1 - j / 40) + S(2)))
            d.line(pts[j] + pts[j + 1], fill=color + (int(150 * (1 - j / 45)),), width=wdt)
    tmp = tmp.filter(ImageFilter.GaussianBlur(max(1, S(4))))
    L.alpha_composite(tmp)


def shade(frame, ci, dark):
    """Directional shading + soft highlight so flat line art gets depth (ref B gray mid-tones)."""
    W, H = Q.W, Q.H
    r = np.random.default_rng(ci * 3)
    ang = r.uniform(0, 2 * math.pi)
    y, x = np.mgrid[0:H:4, 0:W:4].astype(np.float32)
    g = ((x / W - 0.5) * math.cos(ang) + (y / H - 0.5) * math.sin(ang)) + 0.5
    m = 1 - 0.38 * np.clip(g, 0, 1) ** 1.4
    mi = Image.fromarray((m * 255).astype(np.uint8), "L").resize((W, H), Image.BILINEAR)
    rgb = ImageChops.multiply(frame.convert("RGB"), Image.merge("RGB", [mi] * 3))
    hl = Image.fromarray(((1 - np.clip(g, 0, 1)) ** 3 * (40 if not dark else 26)).astype(np.uint8), "L").resize((W, H), Image.BILINEAR)
    rgb = ImageChops.add(rgb, Image.merge("RGB", [hl] * 3))
    out = rgb.convert("RGBA"); return out


def motifs(L, t, c, ci, eyes, bg, layer):
    """MV decoration for the cut. layer: 'back' (behind image) or 'front'."""
    sc = c["scene"]; ov = c.get("overlays", [])
    col = text_color_for(bg) if sc not in (6, 15) else GRAY_D
    if layer == "back":
        if c.get("nochar") == "clock_type":   # the clock itself is the subject
            draw_clock(L, t * 2.5, Q.W / 2, Q.H / 2, PAPER_L, 0.85, 1.25)
            draw_clock(L, -t * 1.5, Q.W / 2, Q.H / 2, GRAY_M, 0.35, 0.7)
            return
        if c.get("nochar") == "paper_type":
            circle_guides(L, t, [], GRAY_M); mini_icons(L, GRAY_D)
            return
        if c.get("nochar") == "ink_type":
            speed_lines(L, t, ci, GRAY_D, alpha=0.6)
            slice_bars(L, ci, t, GRAY_D)
            return
        if any(o.startswith("roman_clock_ring") for o in ov):
            faint = any(o.endswith(":faint") for o in ov); passing = any(o.endswith(":pass") for o in ov)
            if passing:  # numerals and hands sweep past in the background
                cx = Q.W * (0.2 + ((t - c["start"]) / max(c["dur"], 0.4)) * 0.6)
                draw_clock(L, t, cx, Q.H * 0.5, GRAY_M, 0.45, 1.25)
            else:
                draw_clock(L, t, Q.W / 2, Q.H / 2, GRAY_M if faint else col, 0.22 if faint else 0.55)
        if "checker_floor" in ov:
            checker_floor(L, t)
        if "checker_blur" in ov:
            checker_floor(L, t * 3, blur=10 + 40 * (t - c["start"]))
        return
    if "circle_guides" in ov:
        circle_guides(L, t, eyes, GRAY_M)
    if "mini_icon" in ov:
        mini_icons(L, GRAY_D)
    if "code_text_block" in ov:
        cb = code_block(); off = int(t * S(30)) % max(1, cb.size[1] // 2)
        paste(L, cb.crop((0, off, cb.size[0], off + Q.H // 3)), S(60) if ci % 2 else Q.W - S(60) - cb.size[0], Q.H * 0.58, 0.8)
    if "torn_paper_strips" in ov:
        torn_strips(L, t, ci)
    if c.get("red"):
        u0 = c["start"]
        r = np.random.default_rng(ci)
        if "starburst_red" in ov:
            for k, (fx, fy, R) in enumerate(((0.06, 0.12, 0.17), (0.95, 0.85, 0.24), (0.88, 0.08, 0.10))):
                pop = min(1, (t - u0) * FPS / 3 + 0.2)
                starburst(L, Q.W * fx, Q.H * fy, Q.H * R * pop * (1 + 0.03 * math.sin(t * 9 + k)), t, ci * 10 + k)
        if "red_slash" in ov:
            red_slash(L, u0, t, ci)
        if "checker_strip" in ov:
            checker_strip(L, t)


def render_frame(t):
    W, H = Q.W, Q.H
    ci, c = cut_at(t)
    bg = scene_bg(c)
    base = Image.new("RGB", (W, H), bg)
    if sum(bg) > 380:  # paper grain texture
        pt = paper_tex()
        base = ImageChops.multiply(base, Image.merge("RGB", [pt.point(lambda v: 255 - abs(v - 128) // 2)] * 3))
    if c["scene"] == 16:  # grayscale room with long window light
        g = np.linspace(0.18, 0.42, W)[None, :].repeat(H, 0)
        base = Image.fromarray((np.stack([g] * 3, -1) * 255).astype(np.uint8))
        shaft = Image.new("L", (W, H), 0); d = ImageDraw.Draw(shaft)
        for k in range(4):
            x = W * (0.15 + 0.12 * k) + (t - c["start"]) * S(6)
            d.polygon([(x, 0), (x + S(70), 0), (x + S(70) + H * 0.9, H), (x + H * 0.9, H)], fill=150)
        shaft = shaft.filter(ImageFilter.GaussianBlur(S(30)))
        base = ImageChops.screen(base, Image.merge("RGB", [shaft.point(lambda v: int(v * 0.6))] * 3))
    frame = base.convert("RGBA")

    # back motifs
    back = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    motifs(back, t, c, ci, [], bg, "back")
    frame.alpha_composite(back)

    # repeat bands (text level D) sit behind the figure, like ref B
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band_text(band, t, c, bg)
    frame.alpha_composite(band)

    # image layer + transition
    img, eyes = image_layer(ci, c, t)
    kind, ph, inc = transition_state(t)
    if kind and img is not None or kind in ("lightleak_8f", "white_blowout"):
        if kind == "lightleak_8f":
            amt = {-4: 0.25, -3: 0.5, -2: 0.75, -1: 0.92, 0: 0.92, 1: 0.7, 2: 0.45, 3: 0.2, 4: 0.05}.get(int(math.floor(ph)), 0)
            blur = (40 + 80 * (ph + 4) / 4) if ph < 0 else 120 * (1 - ph / 4)
            if img is not None:
                img = dir_blur(expose(img, amt), S(blur))
        elif kind == "flip" and img is not None and 0 <= ph < 3:
            sy = max(0.05, ph / 3)
            img = img.resize((W, max(1, int(H * sy))), Image.BILINEAR).transpose(Image.FLIP_TOP_BOTTOM)
            pad = Image.new("RGBA", (W, H), (0, 0, 0, 0)); pad.paste(img, (0, (H - img.size[1]) // 2)); img = pad
        elif kind == "whip" and img is not None and -2 <= ph < 3:
            off = int((1 - abs(ph) / 3) * W * 0.18 * (1 if ph < 0 else -1))
            img = dir_blur(ImageChops.offset(img, off, 0), S(90 * (1 - abs(ph) / 3)))
        elif kind == "black" and 0 <= ph < 2:
            img = None
    sc = c["scene"]
    if img is not None:
        if sc in CROP_SCENES + (4, 5, 16):
            frame.alpha_composite(ghost_echo(img, ci, t))
        frame.alpha_composite(img)
    rich = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if img is not None and sc in CROP_SCENES and c.get("type") != "black_card":
        black_wedge(rich, ci, t, c)
    if sc in (3, 8, 9, 14) and img is not None:
        slice_bars(rich, ci, t, INK if sum(bg) > 380 else PAPER_L)
    if (sc in (3, 15) and active_line(t) in (13, 63)) or sc == 9 or (c.get("red") and sc == 14):
        speed_lines(rich, t, ci, INK if sum(bg) > 380 else PAPER_L)
    if img is not None and sc in (2, 4, 7, 12, 16):
        smoke_wisps(rich, t, ci, PAPER_L if sc != 4 else GRAY_M)
    frame.alpha_composite(rich)
    if img is not None and sc not in (10, 13, 17, 18):
        frame = shade(frame, ci, sum(bg) <= 380)
    if sc in (3, 8, 14):  # cinema letterbox like ref B's band scenes
        d = ImageDraw.Draw(frame); lb = int(H * 0.115)
        d.rectangle((0, 0, W, lb), fill=INK + (255,)); d.rectangle((0, H - lb, W, H), fill=INK + (255,))

    # front motifs
    front = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    motifs(front, t, c, ci, eyes, bg, "front")
    frame.alpha_composite(front)

    # white flash / edit mask
    if c["scene"] == 13:
        frame = Image.blend(frame, Image.new("RGBA", (W, H), (250, 250, 250, 255)), 0.82)
    out = frame.convert("RGB")
    out = ambient(out, t, sum(bg) <= 380)

    # text layer (separate; moves 40% of the image handheld for parallax; survives transitions)
    T = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    scene_text(T, eyes, t, c, ci, bg)
    hx = snoise(t, ci * 7919 + 14) * 0.001 * W * 0.4
    hy = snoise(t, ci * 7919 + 15) * 0.001 * W * 0.4
    T = ImageChops.offset(T, int(round(hx)), int(round(hy)))
    out = out.convert("RGBA"); out.alpha_composite(T)

    # HUD (always, dim on giant-type scenes)
    if c["scene"] not in (10, 13, 17, 18):
        a = 0.35 if any(o.endswith(":dim") for o in c.get("overlays", [])) else 0.62
        hud = hud_layer().copy(); hud.putalpha(hud.getchannel("A").point(lambda v: int(v * a)))
        hud_dynamic(hud, t, 1.0)
        out.alpha_composite(hud)
    out = out.convert("RGB")
    giant = c.get("red") or (c["scene"] in (3, 9, 15) and active_line(t) in (13, 42, 63))
    if c["scene"] not in (1, 10, 13, 17, 18) and c.get("type") != "black_card" and not giant:
        caption(out, t)

    # glitch events (<=0.2 s) and the audio edit mask
    gl = [c2 for c2 in CUTS if c2.get("transition_in") == "glitch_mosaic_0.2s"]
    for c2 in gl:
        if c2["start"] - 0.03 <= t < c2["start"] + 0.2:
            out = glitch(out, t, int(c2["start"] * 100), 1.6 if c2["scene"] == 10 else 1.0)
    if c["scene"] == 10:
        u = (t - c["start"]) * FPS
        wa = 0.95 if u < 2 else max(0, 0.95 - (u - 2) * 0.12)
        out = Image.blend(out, Image.new("RGB", (W, H), (250, 250, 250)), wa)
    if c["scene"] == 18:
        u = (t - c["start"]) / max(c["dur"], 0.1)
        d = ImageDraw.Draw(out)
        for k in range(5):
            x = W * (0.3 + 0.1 * k); a = max(0, 1 - u * 1.2 - k * 0.05)
            d.rectangle((x, H * 0.2, x + S(18), H * 0.8), fill=tuple(int(PAPER_L[j] + (GRAY_M[j] - PAPER_L[j]) * a) for j in range(3)))
        fade = min(1, max(0, (t - (DUR - 0.8)) / 0.8))
        out = Image.blend(out, Image.new("RGB", (W, H), (0, 0, 0)), fade)

    # breathing +-3%, per-frame flicker +-1.5%, vignette
    fr = int(t * FPS)
    k = 1 + 0.03 * math.sin(2 * math.pi * 0.22 * t) + 0.015 * (np.random.default_rng(fr).random() * 2 - 1)
    out = out.point(lambda v: min(255, int(v * k)))
    v = vignette()
    out = ImageChops.multiply(out, Image.merge("RGB", [v] * 3))
    if c["scene"] == 1:
        out = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), out, min(1, t / 1.5))

    if Q.post:  # bloom + grain (final only)
        hi = out.convert("L").point(lambda v: max(0, v - 200) * 4)
        bl = hi.filter(ImageFilter.GaussianBlur(S(18)))
        out = ImageChops.screen(out, Image.merge("RGB", [bl.point(lambda v: int(v * 0.18))] * 3))
        n = np.random.default_rng(fr + 1).normal(0, 9.0, (H, W)).astype(np.float32)
        a = np.asarray(out).astype(np.float32) + n[..., None]
        out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return out


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--preview", action="store_true"); g.add_argument("--final", action="store_true")
    ap.add_argument("--still", type=float, nargs="*")
    ap.add_argument("--range", type=float, nargs=2)
    ap.add_argument("--out", default=None)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args()
    setup(a.final)
    tag = "final" if a.final else "preview"
    if a.still:
        od = Path(a.out or ROOT / f"renders/stills_{tag}"); od.mkdir(parents=True, exist_ok=True)
        for t in a.still:
            p = od / f"still_{t:07.2f}.png"
            render_frame(t).save(p); print(p)
        return
    t0, t1 = a.range or (0, DUR)
    out = Path(a.out or ROOT / f"renders/{tag}_{t0:g}-{t1:g}.mp4"); out.parent.mkdir(parents=True, exist_ok=True)
    render_video(t0, t1, out, a.final, a.jobs)


def _worker(args):
    t0, t1, path, final = args
    setup(final)
    n0, n1 = int(round(t0 * FPS)), int(round(t1 * FPS))
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{Q.W}x{Q.H}", "-r", str(FPS),
                          "-i", "-", "-c:v", "libx264", "-preset", "medium" if final else "veryfast", "-crf", "16" if final else "23",
                          "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    for n in range(n0, n1):
        p.stdin.write(render_frame(n / FPS).tobytes())
    p.stdin.close(); p.wait()
    return path


def render_video(t0, t1, out, final, jobs):
    from multiprocessing import Pool
    n = max(1, jobs)
    edges = [t0 + (t1 - t0) * k / n for k in range(n + 1)]
    edges = [round(e * FPS) / FPS for e in edges]
    tmp = out.parent / f".parts_{out.stem}"; tmp.mkdir(exist_ok=True)
    tasks = [(edges[k], edges[k + 1], str(tmp / f"p{k:02d}.mp4"), final) for k in range(n)]
    with Pool(n) as pool:
        parts = pool.map(_worker, tasks)
    lst = tmp / "list.txt"; lst.write_text("".join(f"file '{Path(p).name}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ss", str(t0), "-t", str(t1 - t0),
                    "-i", str(ROOT / "audio/song.mp3"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(out)], check=True)
    print(out)


if __name__ == "__main__":
    main()
