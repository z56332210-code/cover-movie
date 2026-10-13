#!/usr/bin/env python3
"""Lyric video renderer (nightcord v3).

    python3 tools/render.py [--preview|--final] --still 10.4 22.0 76.3      # stills (PNG)
    python3 tools/render.py [--preview|--final] [--range 0 20] [--out out.mp4] # video

--preview (default): 960x540, heavy post (grain / bloom / blur) off.
--final:             1920x1080, all post on.  Direction logic is identical in both.
"""
import argparse, bisect, json, math, os, re, subprocess, sys
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


# ------------------------------------------------------------------ easing (no linear motion anywhere)
def clamp(u, a=0.0, b=1.0):
    return a if u < a else b if u > b else u


def bezier(x1, y1, x2, y2):
    def f(u):
        if u <= 0:
            return 0.0
        if u >= 1:
            return 1.0
        s = u
        for _ in range(10):
            x = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s * s * x2 + s ** 3 - u
            dx = 3 * (1 - s) ** 2 * x1 + 6 * (1 - s) * s * (x2 - x1) + 3 * s * s * (1 - x2)
            if abs(dx) < 1e-6:
                break
            s = clamp(s - x / dx)
        return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s * s * y2 + s ** 3
    return f


EASE_OUT = bezier(0.16, 1, 0.3, 1)      # entrances, 8~12 frames
EASE_IN = bezier(0.7, 0, 0.84, 0)       # exits, 4~6 frames


def ease_inout(u):
    return 0.5 - 0.5 * math.cos(math.pi * clamp(u))


def arrive(u, over=0.045):
    """ease-out arrival that overshoots by ~over and settles (incoming cuts)."""
    u = clamp(u)
    return EASE_OUT(u) + over * 1.9 * math.sin(math.pi * u) ** 2 * u


def pop(u):
    """popup scale 0 -> 1.08 -> 1.00 over u in [0, 1] (10 frames)."""
    u = clamp(u)
    return 1.08 * EASE_OUT(u / 0.6) if u < 0.6 else 1.08 - 0.08 * ease_inout((u - 0.6) / 0.4)


BEATS = json.load(open(ROOT / "plan/audio_analysis.json"))["beats"]
BEATS_IN_CUT = [[b for b in BEATS if c["start"] + 3 / FPS < b < c["start"] + c["dur"] - 5 / FPS] for c in CUTS]


BEAT_PULSE_ZOOM = float(os.environ.get("BEAT_PULSE_ZOOM", "0"))   # 0 = no zoom pulse on the beat (default)
HANDHELD = 0.0005                                                  # handheld drift: 0.05 % of width, 0.5~1 Hz, no rotation
IMPACT_ZOOM = 0.03                                                 # 1.00 -> 1.03 -> 1.00 over 6 frames, impact cuts only


def cam_motion(ci, c, t):
    """Calm camera: exactly one move per cut (push in / pull out / pan / still), one direction, eased; the beat is
    carried by decorations, not by the camera. Channels: zoom or pan, plus a ~1 px handheld drift. No rotation."""
    W, H = Q.W, Q.H
    u = clamp((t - c["start"]) / max(c["dur"], 1e-3))
    e = ease_inout(u)                                                 # monotonic: the direction never reverses
    cam = c.get("cam", "static"); amt = c.get("cam_amount", 0.0)
    zoom = px = py = 0.0
    if cam == "push_in":
        zoom = amt * e
    elif cam == "pull_out":
        zoom = amt * (1 - e)
    elif cam == "pan_x":
        px = c.get("pan_dir", 1) * amt * W * (e - 0.5)
    elif cam == "pan_y":
        py = c.get("pan_dir", 1) * amt * H * (e - 0.5)
    f = (t - c["start"]) * FPS
    if c.get("impact") and 0 <= f < 6:
        zoom += IMPACT_ZOOM * math.sin(math.pi * f / 6)
    if BEAT_PULSE_ZOOM:                                               # legacy beat pulse, off unless switched on
        for k, b in enumerate(BEATS_IN_CUT[ci]):
            if b > t:
                break
            zoom += BEAT_PULSE_ZOOM * 0.05 * (1 if k % 2 == 0 else -1) * EASE_OUT(clamp((t - b) * FPS / 4))
    px += snoise(t, ci * 7919 + 1, (0.5, 0.75, 1.0)) * HANDHELD * W
    py += snoise(t, ci * 7919 + 2, (0.5, 0.75, 1.0)) * HANDHELD * W
    return 1 + zoom, px, py, 0.0


def fast_motion(ci, c, t):
    return bool(c.get("impact")) and 0 <= (t - c["start"]) * FPS < 6


def beat_flash(t, frames=4):
    """1 on the beat, fading to 0 over `frames` (drives decoration / text flashes)."""
    bi = bisect.bisect_right(BEATS, t)
    if not bi:
        return 0.0
    return clamp(1 - (t - BEATS[bi - 1]) * FPS / frames)


def focus_target_px(c):
    ft = c.get("focus_target") or (0.5, 0.5)
    return ft[0] * Q.W, ft[1] * Q.H


def cut_transform(ci, c, t):
    """Affine (output px -> source px). The crop's focus point (eye / mask / hand) is pinned to its rule-of-thirds target."""
    W, H = Q.W, Q.H
    src = CROPS[c["crop"]][0]
    w = (c.get("crop_box") or {}).get("w") or CROPS[c["crop"]][2]
    im = art(src)
    k = (im.size[1] / ART_UP / (H * 0.86)) if w is None else w / W
    k /= 1.04
    zm, px, py, rot = cam_motion(ci, c, t)
    k /= zm
    th = math.radians(c.get("rot", 0) + rot)
    fx = -1 if c.get("flip_h") else 1
    fy = -1 if c.get("flip_v") else 1
    ca, sa = math.cos(th), math.sin(th)
    A = np.diag([1.0, fy]) @ np.array([[ca, sa], [-sa, ca]]) @ np.diag([k * fx, k])
    fs = c.get("focus_src") or list(CROPS[c["crop"]][1])
    tx, ty = focus_target_px(c)
    tx += px; ty += py
    c0 = fs[0] - A[0, 0] * tx - A[0, 1] * ty
    f0 = fs[1] - A[1, 0] * tx - A[1, 1] * ty
    inv = tuple(v * ART_UP for v in (A[0, 0], A[0, 1], c0, A[1, 0], A[1, 1], f0))
    Ai = np.linalg.inv(A)
    def fwd(sx, sy):
        v = Ai @ np.array([sx - c0, sy - f0]); return float(v[0]), float(v[1])
    return src, inv, fwd


def torn_mask(ci, c):
    """Torn-paper edge that cuts the illustration (the art is torn away there, the background shows)."""
    r = np.random.default_rng(ci * 31)
    W, H = Q.W, Q.H
    tx, ty = focus_target_px(c)
    side = 1 if tx < W / 2 else 0                       # tear on the side away from the subject's eye
    if r.random() < 0.5:
        side = 3 if ty < H / 2 else 2
    cover = r.uniform(0.18, 0.30); n = 60
    tear = [r.uniform(-1, 1) * S(10) + math.sin(k * 0.7) * S(6) for k in range(n + 1)]
    if side in (0, 1):
        x_top = W * (cover + 0.10); x_bot = W * (cover - 0.10)
        edge = [(x_top + (x_bot - x_top) * k / n + tear[k], H * k / n) for k in range(n + 1)]
        poly = [(0, 0)] + edge + [(0, H)]
        if side == 1:
            edge = [(W - x, y) for x, y in edge]; poly = [(W - x, y) for x, y in poly]
    else:
        y_l = H * (cover + 0.08); y_r = H * (cover - 0.08)
        edge = [(W * k / n, y_l + (y_r - y_l) * k / n + tear[k]) for k in range(n + 1)]
        poly = [(0, 0)] + edge + [(W, 0)]
        if side == 3:
            edge = [(x, H - y) for x, y in edge]; poly = [(x, H - y) for x, y in poly]
    m = Image.new("L", (W, H), 255); ImageDraw.Draw(m).polygon(poly, fill=0)
    return m, edge


def _image_once(ci, c, t):
    src, inv, fwd = cut_transform(ci, c, t)
    neg = (c["scene"] in (8, 9) and c["crop"] == "silhouette") or c.get("variant") == "negative"
    return art(src, negative=neg).transform((Q.W, Q.H), Image.AFFINE, inv, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0)), fwd, src


def image_layer(ci, c, t):
    """RGBA illustration layer (exactly one crop) + its focus point on screen + eye boxes."""
    if not c.get("crop"):
        return None, focus_target_px(c), []
    acc, fwd, src = _image_once(ci, c, t)
    if Q.post:                                           # 180-degree shutter motion blur (final only)
        for k, dt in enumerate((-1 / (4 * FPS), 1 / (4 * FPS))):
            acc = Image.blend(acc, _image_once(ci, c, t + dt)[0], 1 / (k + 2))
    if fast_motion(ci, c, t):                            # 2-frame after-image trail on fast moves
        trail = Image.new("RGBA", acc.size, (0, 0, 0, 0))
        for dt, a in ((2 / FPS, 0.18), (1 / FPS, 0.35)):
            L, _, _ = _image_once(ci, c, t - dt)
            L.putalpha(L.getchannel("A").point(lambda v, a=a: int(v * a)))
            trail.alpha_composite(L)
        trail.alpha_composite(acc); acc = trail
    W, H = Q.W, Q.H
    if c.get("variant") == "strip":
        m = Image.new("L", (W, H), 0); r = np.random.default_rng(ci)
        fy_ = focus_target_px(c)[1]
        hgt = H * r.uniform(0.36, 0.46); y0 = fy_ - hgt / 2; sl = H * r.uniform(-0.08, 0.08)
        ImageDraw.Draw(m).polygon([(0, y0), (W, y0 + sl), (W, y0 + sl + hgt), (0, y0 + hgt)], fill=255)
        acc.putalpha(ImageChops.multiply(acc.getchannel("A"), m))
    if "torn_edge" in (c.get("deco") or []):
        m, _ = torn_mask(ci, c)
        acc.putalpha(ImageChops.multiply(acc.getchannel("A"), m))
    fsrc = c.get("focus_src") or list(CROPS[c["crop"]][1])
    focus = fwd(*fsrc)
    eyes = []
    if src == "upper":
        bw = (c.get("crop_box") or {}).get("w") or CROPS[c["crop"]][2] or 2000
        for ex, ey in EYES_SRC:
            px, py = fwd(ex, ey); r_ = 70 / bw * W
            eyes.append((px - r_, py - r_ * 0.7, px + r_, py + r_ * 0.7))
    if c["scene"] == 16:
        acc = Image.blend(acc, acc.filter(ImageFilter.GaussianBlur(S(2))), 0.5)
    return acc, focus, eyes



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
        while len(p) > 9:
            cand = [k + 1 for k, ch in enumerate(p[:-2]) if ch in "でにはをのてがとも" and 2 <= k + 1 <= len(p) - 2
                    and p[k + 1] not in "っゃゅょぁぃぅぇぉー"]
            if not cand:
                cand = [k for k in range(2, len(p) - 1) if p[k - 1] == " " or not (p[k - 1].isascii() and p[k].isascii())]
            if not cand:
                break
            cut = min(cand, key=lambda k: abs(k - len(p) / 2))
            res.append(p[:cut].rstrip()); p = p[cut:].lstrip()
        res.append(p)
    return tuple(res)


try:
    _AC = {int(k): v for k, v in json.load(open(ROOT / "plan/align_chars.json")).items()}
except FileNotFoundError:
    _AC = {}
sys.path.insert(0, str(ROOT / "tools"))


@lru_cache(None)
def chunk_starts(i):
    """Start time of each chunk of line i: from Whisper character matches when available, else spread over the line."""
    from align_lyrics_kana import kana
    ch = chunks(i)
    t0 = LINE_T[i]; t1 = LINE_T.get(i + 1, LT["end_sec"])
    m = _AC.get(i, [])
    # only trust whisper chars for lines whose start came from whisper
    src = next((s for k, _, s in LT["lines"] if k == i), "")
    out, pos = [], 0
    total = max(1, len(kana(line_text(i))))
    for j, piece in enumerate(ch):
        if j == 0:
            out.append(t0)
        else:
            cand = [tt for kp, tt in m if kp >= pos] if src.startswith("whisper") else []
            ts = cand[0] if cand else t0 + (t1 - t0) * 0.85 * pos / total
            out.append(max(out[-1] + 0.12, min(ts, t1 - 0.1)))
        pos += len(kana(piece))
    return tuple(out)


LEAD_FRAMES = 4          # every line appears 4 frames before it is sung
TAIL_SEC = 0.2           # ... and stays 0.2 s after the singing ends (never overlapping the next line)


def _line_end(i):
    nxt = LINE_T.get(i + 1, LT["end_sec"] + 0.6)
    src = next((s for k, _, s in LT["lines"] if k == i), "")
    m = _AC.get(i)
    e = (max(tt for _, tt in m) + 0.28) if (m and src.startswith("whisper")) else nxt - 0.05
    return min(max(e, LINE_T[i] + 0.3), nxt)


LINE_END = {i: _line_end(i) for i in LINE_T}


@lru_cache(None)
def line_window(i):
    if i not in LINE_T:
        return (1e9, 1e9)
    w0 = LINE_T[i] - LEAD_FRAMES / FPS
    w1 = LINE_END[i] + TAIL_SEC
    w1 = min(w1, LINE_T[i + 1] - LEAD_FRAMES / FPS) if i + 1 in LINE_T else min(w1, LT["end_sec"] + 0.4)
    return w0, w1


def tail_end(i):
    return max(line_window(i)[1], LINE_END[i] + TAIL_SEC)


def active_line(t):
    for i in LINE_T:
        w0, w1 = line_window(i)
        if w0 <= t < w1:
            return i
    return None


@lru_cache(None)
def chunk_appear(i):
    """Appear time of every chunk: 4 frames before it is sung, staggered >= 3 frames in reading order."""
    w0, _ = line_window(i)
    out = []
    for j, st in enumerate(chunk_starts(i)):
        a = max(st - LEAD_FRAMES / FPS, w0)
        if out:
            a = max(a, out[-1] + 3 / FPS)
        out.append(a)
    return tuple(out)



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
# ------------------------------------------------------------------ lyric layout (presets P1..P5, one line at a time)
LYRIC_MODE = os.environ.get("LYRIC_MODE", "vertical")   # "horizontal": every lyric becomes a left-to-right box
BOX_PX_MIN_1080 = 56
CAPTION_PX_1080 = 36
CAPTION_BAND_ALPHA = 0.6
CAPTION_BAND_H_1080 = 70
EXCL_PX_1080 = 60
RED_TEXT = {33: "神っぽいな", 34: "憧れちゃう！", 43: "神っぽいな", 55: "憧れちゃうわ！", 56: "「風」", 57: "「風」"}
BOX_PX = {"verse_a": 60, "pre_chorus": 60, "chorus_a": 70, "verse_b": 62, "audio_edit": 66, "chorus_b": 66,
          "last_chorus": 70, "ending": 60, "intro": 60}
DEBUG = {}


def rel_lum(rgb):
    def ch(v):
        v = v / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(rgb[0]) + 0.7152 * ch(rgb[1]) + 0.0722 * ch(rgb[2])


def contrast(l1, l2):
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)


@lru_cache(4096)
def hbox(text, size, fg=PAPER_L, bg=INK, pad=0.30, fontpath=F_L):
    """Black box with white left-to-right text (LYRIC_MODE=horizontal)."""
    f = font(fontpath, size)
    bb = f.getbbox(text)
    p = int(size * pad)
    im = Image.new("RGBA", (bb[2] - bb[0] + 2 * p, bb[3] - bb[1] + 2 * p), bg + (255,))
    ImageDraw.Draw(im).text((p - bb[0], p - bb[1]), text, font=f, fill=fg + (255,))
    return im


def line_cut(i):
    ci, c = cut_at(LINE_T[i] + 1e-3)
    if c["scene"] == 10:                      # the edit mask is 0.4 s of flash; the line belongs to the next cut
        ci += 1; c = CUTS[ci]
    return ci, c


def rects_px(c):
    r = c.get("lyric_rect")
    if not r:
        return []
    rs = r if isinstance(r[0], list) else [r]
    return [(a * Q.W, b * Q.H, cc * Q.W, d * Q.H) for a, b, cc, d in rs]


@lru_cache(None)
def line_ctx(i):
    ci, c = line_cut(i)
    orient = c.get("lyric_orient")
    red = bool(c.get("red")) and i in RED_TEXT
    text = RED_TEXT[i] if red else line_text(i).replace('"', "")
    if orient == "vertical":
        orient = "hbox" if LYRIC_MODE == "horizontal" else "vbox"
    elif orient == "horizontal":
        orient = "giant"
    return dict(ci=ci, section=c.get("section"), preset=c.get("layout"), orient=orient, red=red, text=text)


def is_giant_line(i):
    return line_ctx(i)["orient"] == "giant"


@lru_cache(None)
def giant_rows(i):
    ctx = line_ctx(i); text = ctx["text"]
    if len(text) <= 8:
        return (text,)
    ch = list(chunks(i)) if not ctx["red"] else [text]
    if len(ch) < 2:                               # split on a kana boundary, never inside a latin word
        cands = [k for k in range(2, len(text) - 1) if text[k - 1] == " " or not (text[k - 1].isascii() and text[k].isascii())]
        if not cands:
            return (text,)
        k = min(cands, key=lambda k: abs(k - len(text) / 2)); return (text[:k].rstrip(), text[k:].lstrip())
    best = min(range(1, len(ch)), key=lambda k: abs(len("".join(ch[:k])) - len("".join(ch[k:]))))
    return ("".join(ch[:best]), "".join(ch[best:]))


@lru_cache(None)
def giant_layout(i, W_, H_):
    """Rows of a giant line inside the preset rect: whole words, first and last glyph always inside the frame."""
    ctx = line_ctx(i); c = CUTS[ctx["ci"]]
    x0, y0, x1, y1 = rects_px(c)[0]
    rows = giant_rows(i)
    fp = F_L if ctx["red"] else F_XL
    size = min(int(H_ * 0.22), int((y1 - y0) / (len(rows) * 1.12)))
    widest = max(font(fp, size).getlength(r) for r in rows)
    if widest > (x1 - x0) * 0.96:
        size = int(size * (x1 - x0) * 0.96 / widest)
    f = font(fp, size)
    asc = f.getbbox("国")[1]
    lh = size * 1.12
    top = (y0 + y1) / 2 - lh * len(rows) / 2
    chars = []
    for r, row in enumerate(rows):
        wrow = f.getlength(row); x = (x0 + x1) / 2 - wrow / 2
        for k, ch_ in enumerate(row):
            chars.append((ch_, x + f.getlength(row[:k]), top + r * lh - asc * 0.2))
    boxes = [((x0 + x1) / 2 - f.getlength(row) / 2, top + r * lh, (x0 + x1) / 2 + f.getlength(row) / 2, top + r * lh + size * 1.05)
             for r, row in enumerate(rows)]
    return dict(size=size, font=fp, chars=chars, boxes=boxes)


@lru_cache(None)
def giant_plan(i):
    """(entrance frames, stagger frames, hold frames): hold >= 12 frames whenever the window allows."""
    w0, w1 = line_window(i)
    N = int(round((w1 - w0) * FPS))
    n = max(1, len(line_ctx(i)["text"].replace(" ", "")))
    for ent, stg in ((10, 2), (10, 1), (8, 1), (8, 0)):
        hold = N - (ent + stg * (n - 1)) - 5
        if hold >= 12:
            return ent, stg, hold
    return 8, 0, N - 8 - 5


def giant_hold_frames(i):
    return giant_plan(i)[2]


def _enter_exit(t, appear, w1, ent=10):
    e = EASE_OUT(clamp((t - appear) * FPS / ent))
    x = clamp((w1 - t) * FPS / 5)
    out = 1 - EASE_IN(1 - x) if x < 1 else 1.0
    return e * out, -S(26) * (1 - e) + S(16) * (1 - out)


def lyric_layout(t):
    """Geometry of everything lyric on screen at t. One line is bright; the line before may linger at 25 %
    until 0.2 s after its singing ends (then it is gone)."""
    li = active_line(t)
    items, cap, dbg = _line_layout(t, li)
    p = (li - 1) if li else None
    if li is None:                                  # gap: the last line may still be in its tail
        p = max((i for i in LINE_T if line_window(i)[1] <= t < tail_end(i)), default=None)
    if p and p in LINE_T and line_window(p)[1] <= t < tail_end(p):
        w1 = line_window(p)[1]
        old, _, _ = _line_layout(w1 - 1e-3, p)
        fade = clamp((tail_end(p) - t) * FPS / 5)
        for it in old:
            it["alpha"] *= 0.25 * fade; it["dim"] = True
        items = old + items
    return items, cap, dbg


def _line_layout(t, li):
    W, H = Q.W, Q.H
    items, cap = [], None
    dbg = dict(line=li, giant_boxes=[], order_ok=True, lines_bright=0)
    if li is None:
        return items, cap, dbg
    w0, w1 = line_window(li)
    ctx = line_ctx(li); c = CUTS[ctx["ci"]]
    rects = rects_px(c)
    ko = KO[li - 1].strip()
    if ko:
        a, dy = _enter_exit(t, w0, w1, 8)
        cap = dict(text=ko, alpha=a, dy=dy)
    if not rects or ctx["orient"] is None:
        return items, cap, dbg
    dbg["lines_bright"] = 1
    if ctx["orient"] == "giant":
        L = giant_layout(li, W, H)
        ent, stg, _ = giant_plan(li)
        for k, (ch_, x, y) in enumerate(L["chars"]):
            a, dy = _enter_exit(t, w0 + k * stg / FPS, w1, ent)
            items.append(dict(kind="giant", text=ch_, size=L["size"], font=L["font"], x=x, y=y, alpha=a, dy=dy, red=ctx["red"], still=True))
        dbg["giant_boxes"] = list(L["boxes"])
        return items, cap, dbg
    size = max(S(BOX_PX_MIN_1080), S(BOX_PX.get(ctx["section"], 62)))
    if ctx["red"]:                                   # red keyword, written in the section's own direction
        x0, y0, x1, y1 = rects[0]
        n = len(ctx["text"])
        if ctx["orient"] == "vbox":
            sz = int(min((x1 - x0) * 0.8, (y1 - y0) / (n * 1.04), S(150)))
            im = vtext(ctx["text"], sz, RED + (255,), F_L)
            x, y = x1 - im.size[0], y0
        else:
            sz = int(min((y1 - y0) * 0.5, (x1 - x0) / (n * 1.04), S(150)))
            im = htext(ctx["text"], sz, RED + (255,), F_L)
            x, y = x0, y0
        a, dy = _enter_exit(t, w0, w1)
        items.append(dict(kind="red", img=im, x=x, y=y, alpha=a, dy=dy, red=True))
        return items, cap, dbg
    vis = [(j, p) for j, (p, ap) in enumerate(zip(chunks(li), chunk_appear(li))) if ap <= t][-3:]   # max 3 boxes
    xs = [r[2] for r in rects]; ys = [r[1] for r in rects]
    last_x = None
    for n_, (j, piece) in enumerate(vis):
        ri = 0 if (len(rects) == 1 or n_ < 2) else 1          # P4: right rect takes the first two columns, then the left rect
        if ctx["orient"] == "vbox":
            box = vbox(piece, size); bright = vbox(piece, size, fg=(255, 255, 255))
            x = xs[ri] - box.size[0]; xs[ri] = x - int(size * 0.35)
            y = rects[ri][1] + (n_ % 2) * S(40)
            if last_x is not None and x >= last_x:          # reading order must run right -> left across the screen
                dbg["order_ok"] = False
            last_x = x
        else:
            box = hbox(piece, size); bright = hbox(piece, size, fg=(255, 255, 255))
            x = rects[ri][0]; y = ys[ri]; ys[ri] = y + box.size[1] + int(size * 0.3)
        a, dy = _enter_exit(t, chunk_appear(li)[j], w1)
        items.append(dict(kind="box", img=box, bright=bright, x=x, y=y, alpha=a, dy=dy, red=False))
    return items, cap, dbg


def item_bbox(it):
    if it["kind"] == "giant":
        f = font(it["font"], it["size"]); bb = f.getbbox(it["text"])
        return (it["x"] + bb[0], it["y"] + bb[1], it["x"] + bb[2], it["y"] + bb[3])
    return (it["x"], it["y"], it["x"] + it["img"].size[0], it["y"] + it["img"].size[1])


def caption_rect(cap):
    f = font(F_L, S(CAPTION_PX_1080), 1)
    w = f.getlength(cap["text"]) + S(80); hb = S(CAPTION_BAND_H_1080)
    yc = Q.H - S(78)
    return (Q.W / 2 - w / 2, yc - hb / 2, Q.W / 2 + w / 2, yc + hb / 2)


def exclusion_mask(items, cap):
    """255 where decorations may draw; lyric boxes (+60 px @1080) and the caption band are kept clear."""
    W, H = Q.W, Q.H
    m = Image.new("L", (W, H), 255); d = ImageDraw.Draw(m)
    e = S(EXCL_PX_1080)
    boxes = [item_bbox(it) for it in items if it["alpha"] > 0.01]
    if cap:
        boxes.append(caption_rect(cap))
    for x0, y0, x1, y1 in boxes:
        d.rectangle((x0 - e, y0 - e - S(30), x1 + e, y1 + e + S(30)), fill=0)
    return m, boxes


def _plate_for(img_rgb, bbox, text_rgb, target=5.0):
    """Measure luminance contrast of text against what is behind it; return (plate_rgb, alpha) needed to reach target."""
    x0, y0, x1, y1 = [int(v) for v in bbox]
    x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(Q.W, x1), min(Q.H, y1)
    if x1 <= x0 or y1 <= y0:
        return None, 0.0, 21.0
    reg = np.asarray(img_rgb.crop((x0, y0, x1, y1)).resize((max(1, (x1 - x0) // 8), max(1, (y1 - y0) // 8)))).reshape(-1, 3)
    lt = rel_lum(text_rgb)
    lums = np.array([rel_lum(p) for p in reg[:: max(1, len(reg) // 400)]])
    worst = lums.max() if lt < 0.2 else lums.min()          # the background pixel least like the text
    cr = contrast(lt, worst)
    if cr >= target:
        return None, 0.0, cr
    plate = PAPER_L if lt < 0.2 else INK
    lp = rel_lum(plate)
    for a in np.arange(0.5, 1.0001, 0.05):
        if contrast(lt, a * lp + (1 - a) * worst) >= target:
            return plate, float(a), contrast(lt, a * lp + (1 - a) * worst)
    return plate, 1.0, contrast(lt, lp)


t_now = [0.0]


def draw_lyrics(out, items, cap, dbg, hx, hy):
    """Draw lyrics + caption onto the RGB frame; giant type stays still once it has landed."""
    L = Image.new("RGBA", out.size, (0, 0, 0, 0))
    crs = []
    giant = [it for it in items if it["kind"] == "giant" and not it.get("dim")]
    for it in items:
        if it["kind"] == "giant" and it.get("dim"):
            paste(L, htext(it["text"], it["size"], GRAY_M + (255,), it["font"]), it["x"] - 2, it["y"] - 2 + it["dy"], it["alpha"])
    if giant:
        bb = [item_bbox(it) for it in giant]
        ub = (min(b[0] for b in bb) - S(20), min(b[1] for b in bb) - S(16), max(b[2] for b in bb) + S(20), max(b[3] for b in bb) + S(16))
        reg = np.asarray(out.crop(tuple(int(v) for v in (max(0, ub[0]), max(0, ub[1]), min(Q.W, ub[2]), min(Q.H, ub[3]))))).reshape(-1, 3)
        dark = reg.mean() < 128
        col = RED if giant[0]["red"] else (PAPER_L if dark else INK)
        plate, pa, cr = _plate_for(out, ub, col)
        amax = max(it["alpha"] for it in giant)
        if plate:
            pl = Image.new("RGBA", out.size, (0, 0, 0, 0))
            ImageDraw.Draw(pl).rounded_rectangle(ub, radius=S(18), fill=plate + (int(255 * pa * amax),))
            L.alpha_composite(pl.filter(ImageFilter.GaussianBlur(S(6))))
        for it in giant:
            g = htext(it["text"], it["size"], col + (255,), it["font"])
            paste(L, g, it["x"] - 2, it["y"] - 2 + it["dy"], it["alpha"])
        crs.append(cr)
    for it in items:
        if it["kind"] == "box":
            paste(L, box_shadow(it["img"]), it["x"] + hx + S(7), it["y"] + hy + it["dy"] + S(9), it["alpha"] * 0.45)
            paste(L, it["img"], it["x"] + hx, it["y"] + hy + it["dy"], it["alpha"])
            bf = beat_flash(t_now[0])
            if bf > 0 and not it.get("dim"):
                paste(L, it.get("bright") or it["img"], it["x"] + hx, it["y"] + hy + it["dy"], it["alpha"] * 0.7 * bf)
            crs.append(contrast(rel_lum(PAPER_L), rel_lum(INK)))
        elif it["kind"] == "red":
            bb = item_bbox(it)
            plate, pa, cr = _plate_for(out, (bb[0] - S(14), bb[1] - S(10), bb[2] + S(14), bb[3] + S(10)), RED)
            if plate:
                pl = Image.new("RGBA", out.size, (0, 0, 0, 0))
                ImageDraw.Draw(pl).rounded_rectangle((bb[0] - S(14) + hx, bb[1] - S(10) + hy + it["dy"], bb[2] + S(14) + hx, bb[3] + S(10) + hy + it["dy"]),
                                                     radius=S(14), fill=plate + (int(255 * pa * it["alpha"]),))
                L.alpha_composite(pl)
            paste(L, it["img"], it["x"] + hx, it["y"] + hy + it["dy"], it["alpha"])
            crs.append(cr)
    if cap and cap["alpha"] > 0.01:
        x0, y0, x1, y1 = caption_rect(cap)
        reg = np.asarray(out.crop((int(x0), int(y0), int(x1), int(y1))).resize((40, 4))).reshape(-1, 3)
        bgw = max(rel_lum(p) for p in reg)
        ba = CAPTION_BAND_ALPHA                     # 60 %, darkened only as much as the picture behind needs
        while ba < 0.97 and contrast(rel_lum(PAPER_L), bgw * (1 - ba) + rel_lum(INK) * ba) < 4.8:
            ba += 0.03
        band = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(band).rectangle((x0, y0 + cap["dy"] * 0.3, x1, y1 + cap["dy"] * 0.3), fill=INK + (int(255 * ba * cap["alpha"]),))
        L.alpha_composite(band)
        f = font(F_L, S(CAPTION_PX_1080), 1)
        bb = f.getbbox(cap["text"])
        ImageDraw.Draw(L).text((Q.W / 2 - (bb[2] - bb[0]) / 2 - bb[0], (y0 + y1) / 2 - (bb[1] + bb[3]) / 2 + cap["dy"] * 0.3), cap["text"],
                               font=f, fill=PAPER_L + (int(255 * cap["alpha"]),))
        worst = bgw * (1 - ba) + rel_lum(INK) * ba
        crs.append(contrast(rel_lum(PAPER_L), worst))
    out = out.convert("RGBA"); out.alpha_composite(L)
    dbg["contrast"] = [round(float(x), 2) for x in crs]
    return out.convert("RGB")

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
    s = f"BPM 142.4   BEAT {bisect.bisect_right(BEATS, t):03d}   CUT {cut_at(t)[0] + 1:03d}"
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


def draw_clock(L, t, cx, cy, color, alpha, scale=1.0, t_real=None):
    """Numeral ring rotates slowly (12 fps); the hand ticks one numeral on every beat."""
    ring = clock_ring(color)
    if scale != 1.0:
        ring = ring.resize((int(ring.size[0] * scale), int(ring.size[1] * scale)), Image.BICUBIC)
    r = ring.rotate(-t * 6.0, resample=Image.BICUBIC)
    paste(L, r, cx - r.size[0] / 2, cy - r.size[1] / 2, alpha)
    d = ImageDraw.Draw(L)
    col = color + (int(255 * alpha),)
    R = Q.H * 0.40 * scale
    tr = t if t_real is None else t_real
    bi = bisect.bisect_right(BEATS, tr)
    last = BEATS[bi - 1] if bi else 0.0
    ang = (bi - 1) * 30 + 30 * EASE_OUT(clamp((tr - last) * FPS / 3))
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


def checker_floor(L, t, blur=0.0, alpha=1.0):
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
            d.polygon(q, fill=GRAY_M + (int(150 * alpha),))
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


def speed_lines(L, t, ci, color, alpha=0.55, cx=None, cy=None):
    """Radial concentration lines (ref B t033)."""
    r = np.random.default_rng(ci * 7 + int(t * 12))
    W, H = Q.W, Q.H
    cx = W / 2 if cx is None else cx; cy = H * 0.45 if cy is None else cy
    d = ImageDraw.Draw(L)
    for k in range(70):
        a = r.uniform(0, 2 * math.pi)
        r0 = r.uniform(0.22, 0.34) * H; r1 = r0 + r.uniform(0.15, 0.55) * H
        d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
               fill=color + (int(255 * alpha * r.uniform(0.4, 1)),), width=max(1, S(r.uniform(1, 2.5))))


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
    return rgb.convert("RGBA")


def _masked(L, excl):
    L.putalpha(ImageChops.multiply(L.getchannel("A"), excl))
    return L


def decorations(ci, c, t, focus, bg, excl):
    """Exactly one decoration kind per cut, animated on twos (12 fps), kept 60 px away from the lyrics.
    Returns (back layer drawn behind the illustration, front layer)."""
    W, H = Q.W, Q.H
    td = math.floor(t * 12) / 12
    back = Image.new("RGBA", (W, H), (0, 0, 0, 0)); front = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    kinds = c.get("deco") or []
    fx, fy = focus
    tc = text_color_for(bg)
    for k in kinds:
        if k == "clock":            # behind the subject, centred on its eye point
            if c.get("nochar") == "clock_type":
                draw_clock(back, td * 2.5, fx, fy, PAPER_L, 0.85, 1.25, t_real=t)
            else:
                faint = c["scene"] in (1, 17)
                draw_clock(back, td * (4 if faint else 1), fx, fy, GRAY_M if faint else (GRAY_D if sum(bg) > 380 else GRAY_M), 0.34 if faint else 0.6, 1.0, t_real=t)
        elif k == "band":
            rows = 5 if c.get("nochar") == "band_only" or (c["scene"] == 14 and active_line(t) in (56, 57, 58)) else 1
            text_D(back, td, c, GRAY_M if c["scene"] in (8, 9) else tc, rows=rows, size_h=0.13 if rows > 1 else 0.15)
        elif k == "checker":
            checker_floor(back, td * (3 if c["scene"] == 9 else 1), blur=(10 + 40 * (t - c["start"])) if c["scene"] == 9 else 0,
                          alpha=0.65 + 0.35 * beat_flash(t))
        elif k == "speed_lines":
            speed_lines(back, td, ci, GRAY_M, alpha=0.8, cx=fx, cy=fy)
        elif k == "guides":
            circle_guides(front, td, [(fx - 1, fy - 1, fx + 1, fy + 1)], GRAY_M)
        elif k == "code":
            cb = code_block(); off = int(td * S(30)) % max(1, cb.size[1] // 2)
            x = S(70) if fx > W / 2 else W - S(70) - cb.size[0]
            paste(front, cb.crop((0, off, cb.size[0], off + H // 3)), x, H * 0.56, 0.85)
        elif k == "starburst":      # red sections only; pops 0 -> 1.08 -> 1.00, staggered 3 frames
            for j, (px_, py_, R) in enumerate(((0.07 if fx > W / 2 else 0.93, 0.14, 0.17), (0.93 if fx > W / 2 else 0.07, 0.86, 0.22),
                                              (0.50, 0.06, 0.09))):
                u = ((t - c["start"]) * FPS - 3 * j) / 10
                if u <= 0:
                    continue
                starburst(front, W * px_, H * py_, H * R * pop(u), td, ci * 10 + j, alpha=0.72 + 0.28 * beat_flash(t))
        elif k == "torn_edge":      # edge line of the tear that cuts the illustration
            _, edge = torn_mask(ci, c)
            ImageDraw.Draw(front).line(edge, fill=GRAY_M + (170,), width=max(1, S(2)))
    return _masked(back, excl), _masked(front, excl)


def scene_layer(ci, t, excl):
    """Background + decoration + illustration for cut ci at time t (no lyrics)."""
    W, H = Q.W, Q.H
    c = CUTS[ci]
    bg = scene_bg(c)
    base = Image.new("RGB", (W, H), bg)
    if sum(bg) > 380:
        pt = paper_tex()
        base = ImageChops.multiply(base, Image.merge("RGB", [pt.point(lambda v: 255 - abs(v - 128) // 2)] * 3))
    if c["scene"] == 16:  # grayscale room with long window light (background, not a decoration)
        g = np.linspace(0.18, 0.42, W)[None, :].repeat(H, 0)
        base = Image.fromarray((np.stack([g] * 3, -1) * 255).astype(np.uint8))
        shaft = Image.new("L", (W, H), 0); d = ImageDraw.Draw(shaft)
        for k in range(4):
            x = W * (0.15 + 0.12 * k) + ease_inout((t - c["start"]) / max(c["dur"], 0.5)) * S(40)
            d.polygon([(x, 0), (x + S(70), 0), (x + S(70) + H * 0.9, H), (x + H * 0.9, H)], fill=150)
        shaft = shaft.filter(ImageFilter.GaussianBlur(S(30)))
        base = ImageChops.screen(base, Image.merge("RGB", [shaft.point(lambda v: int(v * 0.6))] * 3))
    frame = base.convert("RGBA")
    src_ci, src_c = (ci + 1, dict(CUTS[ci + 1], transition_in="T3")) if c["scene"] == 10 else (ci, c)   # edit mask: borrowed art, already in place
    img, focus, eyes = image_layer(src_ci, src_c, t)
    back, front = decorations(ci, c, t, focus, bg, excl)
    frame.alpha_composite(back)
    if img is not None:
        if c["scene"] in CROP_SCENES + (4, 5, 16):
            frame.alpha_composite(ghost_echo(img, ci, t))
        frame.alpha_composite(img)
    frame.alpha_composite(front)
    if img is None and c["scene"] not in (10, 18):
        zm, px, py, rot = cam_motion(ci, c, t)
        cx, cy = W / 2, H / 2
        k = 1 / zm
        frame = frame.transform((W, H), Image.AFFINE, (k, 0, cx - k * (cx + px), 0, k, cy - k * (cy + py)), resample=Image.BILINEAR,
                                fillcolor=bg + (255,))
    if img is not None and c["scene"] not in (10, 13, 17, 18):
        frame = shade(frame, ci, sum(bg) <= 380)
    if c["scene"] in (3, 8, 14):  # cinema letterbox like ref B's band scenes (framing)
        d = ImageDraw.Draw(frame); lb = int(H * 0.115)
        d.rectangle((0, 0, W, lb), fill=INK + (255,)); d.rectangle((0, H - lb, W, H), fill=INK + (255,))
    if c["scene"] == 13:
        frame = Image.blend(frame, Image.new("RGBA", (W, H), (250, 250, 250, 255)), 0.82)
    deco_px = int((np.asarray(back.getchannel("A")) > 8).sum() + (np.asarray(front.getchannel("A")) > 8).sum()) if excl is not None else 0
    return frame, dict(focus=focus, eyes=eyes, bg=bg, deco_px=deco_px)


# ------------------------------------------------------------------ transition library T1..T6
def slice_glitch(img, seed, strength=1.0):
    r = np.random.default_rng(seed)
    W, H = Q.W, Q.H
    n = int(r.integers(4, 7))
    cuts = sorted(r.uniform(0.08, 0.92, n - 1)); edges = [0] + [int(H * v) for v in cuts] + [H]
    out = Image.new(img.mode, img.size, INK + ((255,) if img.mode == "RGBA" else ()))
    for k in range(n):
        y0, y1 = edges[k], edges[k + 1]
        dx = int(r.choice([-1, 1]) * r.uniform(40, 120) * Q.s * strength)
        out.paste(img.crop((0, y0, W, y1)), (dx, y0))
        if r.random() < 0.5:
            bw = int(r.uniform(0.08, 0.3) * W); bx = int(r.uniform(0, W - bw))
            ImageDraw.Draw(out).rectangle((bx, y0, bx + bw, y0 + max(2, (y1 - y0) // 3)), fill=INK)
    return out


def hblur(img, px):
    if px < 1:
        return img
    W, H = img.size
    k = max(1.0, px / 3)
    return img.resize((max(1, int(W / k)), H), Image.BILINEAR).resize((W, H), Image.BILINEAR)


def boundary(t):
    f = t * FPS
    for i in range(1, len(CUTS)):
        d = f - CUTS[i]["start"] * FPS
        if -6 <= d < 8:
            return i, d
    return None, None


def compose_scene(t, excl):
    W, H = Q.W, Q.H
    ci, c = cut_at(t)
    frame, info = scene_layer(ci, t, excl)
    i, f = boundary(t)
    if i is None:
        return frame, info, None
    kind = CUTS[i]["transition_in"]
    seed = i * 977
    if kind == "T1":                     # circle wipe: ink disc grows (6 f), then shrinks into the next ring (6 f)
        d = ImageDraw.Draw(frame); diag = math.hypot(W, H) * 0.62
        if -6 <= f < 0:
            cx, cy = focus_target_px(CUTS[i - 1]); r = diag * EASE_IN((f + 6) / 6)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK + (255,), outline=PAPER_L + (255,), width=max(2, S(5)))
        elif 0 <= f < 6:
            cx, cy = info["focus"]; u = EASE_OUT(f / 6); r = diag + (H * 0.36 - diag) * u
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
            od.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK + (int(255 * (1 - u)),), outline=PAPER_L + (int(255 * (1 - 0.6 * u)),), width=max(2, S(4)))
            frame.alpha_composite(ov)
    elif kind == "T2" and -5 <= f < 1:   # slice glitch, 6 frames
        frame = slice_glitch(frame, seed + int(f), 0.5 + 0.5 * (f + 5) / 5)
    elif kind == "T3" and -2 <= f < 0:   # flash match cut (white 2 frames, then the same spot in another crop)
        frame = Image.blend(frame, Image.new("RGBA", (W, H), (250, 250, 250, 255)), 0.55 if f < -1 else 0.92)
    elif kind == "T4" and -6 <= f < 2:   # torn-paper wipe carries the next illustration in (8 frames)
        other, _ = scene_layer(i if f < 0 else i - 1, t, excl)
        out_l, in_l = (frame, other) if f < 0 else (other, frame)
        u = ease_inout((f + 6) / 8)
        p = -0.25 + 1.5 * u
        y, x = np.mgrid[0:H:2, 0:W:2].astype(np.float32)
        g = (x / W * 0.62 + y / H * 0.38)
        m = Image.fromarray(((g < p) * 255).astype(np.uint8), "L").resize((W, H))
        frame = Image.composite(in_l, out_l, m)
        strip = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        r = np.random.default_rng(seed)
        band = ((g > p - 0.06 + (r.random(g.shape) * 0.012)) & (g < p + 0.02 + (r.random(g.shape) * 0.012))) * 1
        sa = Image.fromarray((band * 235).astype(np.uint8), "L").resize((W, H))
        strip = Image.new("RGBA", (W, H), PAPER + (0,)); strip.putalpha(sa)
        frame.alpha_composite(strip)
    elif kind == "T5" and -6 <= f < 0:   # whip blur 0 -> 160 px over 6 frames into the cut
        u = (f + 6) / 6
        frame = hblur(ImageChops.offset(frame, int(W * 0.08 * u * u), 0), S(160) * u)
    elif kind == "cut_to_black" and 0 <= f < 3:
        frame = Image.blend(frame, Image.new("RGBA", (W, H), INK + (255,)), 0.8 - 0.25 * f)
    return frame, info, kind


def render_frame(t):
    W, H = Q.W, Q.H
    ci, c = cut_at(t)
    items, cap, dbg = lyric_layout(t)
    excl, lyric_boxes = exclusion_mask(items, cap)
    frame, info, tr = compose_scene(t, excl)
    if c["scene"] == 10:                 # audio edit mask: white hit + mosaic over the incoming cut
        u = (t - c["start"]) * FPS
        frame = Image.blend(frame, Image.new("RGBA", (W, H), (250, 250, 250, 255)), 0.92 if u < 1.5 else max(0, 0.75 - (u - 1.5) * 0.25))
        if 1.5 <= u < 7.5:
            frame = glitch(frame.convert("RGB"), t, 9090, 2.2).convert("RGBA")
    out = ambient(frame.convert("RGB"), t, sum(info["bg"]) <= 380)
    if c["scene"] == 1:                  # title card (not lyrics)
        T = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a = min(1, t / 3)
        im = htext("神っぽいな", S(54), PAPER_L + (int(220 * a),), F_XL)
        paste(T, im, W / 2 - im.size[0] / 2, H / 2 - S(60))
        im2 = htext("cover  /  暁山 瑞希", S(20), GRAY_M + (int(220 * a),), F_L)
        paste(T, im2, W / 2 - im2.size[0] / 2, H / 2 + S(30))
        out = out.convert("RGBA"); out.alpha_composite(T); out = out.convert("RGB")
    hx = snoise(t, ci * 7919 + 14, (0.5, 0.75, 1.0)) * HANDHELD * W * 0.4   # boxes follow 40% of the handheld; giant type stays still
    hy = snoise(t, ci * 7919 + 15, (0.5, 0.75, 1.0)) * HANDHELD * W * 0.4
    t_now[0] = t
    out = draw_lyrics(out, items, cap, dbg, int(round(hx)), int(round(hy)))
    if c["scene"] not in (10, 13, 17, 18):
        a = 0.35 if any(o.endswith(":dim") for o in c.get("overlays", [])) else 0.62
        hud = hud_layer().copy(); hud.putalpha(hud.getchannel("A").point(lambda v: int(v * a)))
        hud_dynamic(hud, t, 1.0)
        out = out.convert("RGBA"); out.alpha_composite(hud); out = out.convert("RGB")
    if c["scene"] == 18:
        u = (t - c["start"]) / max(c["dur"], 0.1)
        d = ImageDraw.Draw(out)
        for k in range(5):
            x = W * (0.3 + 0.1 * k); a = max(0, 1 - ease_inout(u) * 1.2 - k * 0.05)
            d.rectangle((x, H * 0.2, x + S(18), H * 0.8), fill=tuple(int(PAPER_L[j] + (GRAY_M[j] - PAPER_L[j]) * a) for j in range(3)))
        out = Image.blend(out, Image.new("RGB", (W, H), (0, 0, 0)), ease_inout((t - (DUR - 0.8)) / 0.8))
    # always-moving scanline band (flickers on twos)
    band = Image.new("L", (W, H), 0); d = ImageDraw.Draw(band)
    t12 = math.floor(t * 12) / 12
    y = (t12 * S(140)) % (H + S(200)) - S(100)
    d.rectangle((0, y, W, y + S(60)), fill=28 if c["scene"] in (1, 17) or c.get("type") == "black_card" else 14)
    for k in range(6):
        yy = (y * 0.37 + k * H / 6) % H
        d.line((0, yy, W, yy), fill=18, width=1)
    out = ImageChops.screen(out, Image.merge("RGB", [band.filter(ImageFilter.GaussianBlur(S(18)))] * 3))
    fr = int(round(t * FPS))
    k = 1 + 0.03 * math.sin(2 * math.pi * 0.22 * t) + 0.015 * (np.random.default_rng(fr).random() * 2 - 1)
    out = out.point(lambda v: min(255, int(v * k)))
    out = ImageChops.multiply(out, Image.merge("RGB", [vignette()] * 3))
    if c["scene"] == 1:
        out = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), out, EASE_OUT(t / 1.5))
    if Q.post:
        hi = out.convert("L").point(lambda v: max(0, v - 200) * 4)
        bl = hi.filter(ImageFilter.GaussianBlur(S(18)))
        out = ImageChops.screen(out, Image.merge("RGB", [bl.point(lambda v: int(v * 0.18))] * 3))
        n = np.random.default_rng(fr + 1).normal(0, 9.0, (H, W)).astype(np.float32)
        out = Image.fromarray(np.clip(np.asarray(out).astype(np.float32) + n[..., None], 0, 255).astype(np.uint8))
    DEBUG.clear()
    DEBUG.update(dbg, cut=ci, focus=None if c.get("nochar") else info["focus"], transition=tr,
                 deco_over_lyrics=0 if not lyric_boxes else _deco_overlap(t, ci, c, info, lyric_boxes))
    return out


def _deco_overlap(t, ci, c, info, boxes):
    """Re-draw the decorations unmasked and count pixels that would fall inside the lyric keep-out zone (after masking: must be 0)."""
    W, H = Q.W, Q.H
    excl = Image.new("L", (W, H), 255); d = ImageDraw.Draw(excl); e = S(EXCL_PX_1080)
    for x0, y0, x1, y1 in boxes:
        d.rectangle((x0 - e, y0 - e, x1 + e, y1 + e), fill=0)
    keep, _ = exclusion_mask(*lyric_layout(t)[:2])
    back, front = decorations(ci, c, t, info["focus"], info["bg"], keep)
    z = np.asarray(excl) == 0
    return int(((np.asarray(back.getchannel("A")) > 8) & z).sum() + ((np.asarray(front.getchannel("A")) > 8) & z).sum())

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--preview", action="store_true"); g.add_argument("--final", action="store_true")
    ap.add_argument("--still", type=float, nargs="*")
    ap.add_argument("--range", type=float, nargs=2)
    ap.add_argument("--out", default=None)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--lyric-mode", choices=["vertical", "horizontal"], default=None)
    a = ap.parse_args()
    if a.lyric_mode:
        global LYRIC_MODE
        os.environ["LYRIC_MODE"] = LYRIC_MODE = a.lyric_mode
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
