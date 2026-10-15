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
    e = 1 - (1 - u) ** 3                                              # ease-out: fastest at the cut, then decelerating; never reverses
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
            px, py = fwd(ex, ey); r_ = 48 / bw * W                # eye ~48 px radius in the source art
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
def vtext(text, size, fill, fontpath=F_XL, stroke=0, stroke_fill=None):
    """Vertical text. With stroke the image grows by `stroke` px on every side (paste at x - stroke, y - stroke)."""
    f = font(fontpath, size)
    bb = f.getbbox(text, direction="ttb", features=["vert"])
    im = Image.new("RGBA", (bb[2] - bb[0] + 4 + 2 * stroke, bb[3] - bb[1] + 4 + 2 * stroke), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 + stroke - bb[0], 2 + stroke - bb[1]), text, font=f, fill=fill, direction="ttb", features=["vert"],
                            stroke_width=stroke, stroke_fill=stroke_fill or fill)
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
        w0, w1 = line_window(i)
        orient = "giant" if (w1 - w0) * FPS >= 26 else "vbox"     # a quick shout can't land + hold 12 f: same spot, vertical box
    return dict(ci=ci, section=c.get("section"), preset=c.get("layout"), orient=orient, red=red, text=text)


def is_giant_line(i):
    return line_ctx(i)["orient"] == "giant"


@lru_cache(None)
def giant_rows(i):
    """Columns of an emphasised line (vertical writing): phrase chunks, at most 3 (one box each), never splitting a latin word."""
    ctx = line_ctx(i); text = ctx["text"]
    ch = list(chunks(i)) if not ctx["red"] else ([text] if len(text) <= 7 else [text[:len(text) // 2], text[len(text) // 2:]])
    while len(ch) > 3:                                    # merge the two shortest neighbours
        k = min(range(len(ch) - 1), key=lambda k: len(ch[k]) + len(ch[k + 1]))
        ch[k:k + 2] = [ch[k] + ch[k + 1]]
    return tuple(ch)


SMALL_KANA = set("っゃゅょぁぃぅぇぉッャュョァィゥェォ、。・ー〜…")


@lru_cache(None)
def giant_layout(i, W_, H_):
    """Vertical kinetic typography: one column per phrase, first column on the right, columns of different sizes,
    staggered heights, the leading glyph enlarged. Every glyph stays inside the frame."""
    ctx = line_ctx(i); c = CUTS[ctx["ci"]]
    x0, y0, x1, y1 = rects_px(c)[0]
    cols = giant_rows(i)
    fp = F_R                                         # Regular: ExtraLight hairlines broke up in the encoded video
    r = np.random.default_rng(i * 97)
    scale = [1.0 if k == 0 else (0.62 if k % 2 else 0.78) for k in range(len(cols))]
    if len(cols) > 1:
        big = max(range(len(cols)), key=lambda k: len(cols[k]) <= 6 and -abs(len(cols[k]) - 4))
        scale = [0.62 if k % 2 else 0.78 for k in range(len(cols))]; scale[big] = 1.0
    rh, rw = y1 - y0, x1 - x0
    def col_h(col, sz):
        return sum(sz * (0.82 if ch_ in SMALL_KANA else 1.0) for ch_ in col) + sz * 0.25   # + enlarged lead glyph
    U = min(H_ * 0.24, *[rh * 0.94 / max(1e-6, col_h(col, scale[k])) for k, col in enumerate(cols)])
    U = min(U, rw / max(1e-6, sum(scale[k] * 1.18 for k in range(len(cols)))))
    chars, boxes = [], []
    xr = x1
    for k, col in enumerate(cols):
        sz = U * scale[k]
        h = col_h(col, sz)
        off = (rh - h) * (0.08 + 0.84 * r.random()) if rh > h else 0.0          # staggered, never aligned
        y = y0 + off
        cw = sz * 1.18
        x = xr - cw
        bx0, by0 = x, y
        for j, ch_ in enumerate(col):
            gs = int(sz * (1.25 if j == 0 else 0.82 if ch_ in SMALL_KANA else 1.0))
            chars.append((ch_, x + (cw - gs) / 2, y, gs))
            y += gs
        boxes.append((bx0, by0, x + cw, y))
        xr = x - sz * 0.10 * (1 + r.random())
    return dict(font=fp, chars=chars, boxes=boxes)


@lru_cache(None)
def emph_layout(i, W_, H_):
    """Emphasised line as vertical boxes: right-to-left columns, the most fitting column 1.3x, staggered heights, inside the rect."""
    ctx = line_ctx(i); c = CUTS[ctx["ci"]]
    x0, y0, x1, y1 = rects_px(c)[0]
    cols = giant_rows(i)
    base = max(S(BOX_PX_MIN_1080), S(BOX_PX.get(ctx["section"], 62)))
    big = max(range(len(cols)), key=lambda k: len(cols[k]) <= 6 and -abs(len(cols[k]) - 4))
    r = np.random.default_rng(i * 97)
    out, xr = [], x1
    for k, col in enumerate(cols):
        sz = int(base * (1.3 if k == big else 1.0))
        while sz > S(BOX_PX_MIN_1080) and vbox(col, sz).size[1] > (y1 - y0):
            sz -= 2
        b = vbox(col, sz)
        free = (y1 - y0) - b.size[1]
        y = y0 + max(0, free) * (0.05 + 0.6 * r.random())
        x = xr - b.size[0]
        out.append((col, x, y, sz))
        xr = x - int(sz * 0.35)
    return tuple(out)


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
    if ctx["orient"] == "giant":                     # emphasis: vertical boxes, a size step up from normal boxes, staggered
        base = max(S(BOX_PX_MIN_1080), S(BOX_PX.get(ctx["section"], 62)))
        for k, (piece, x, y, sz) in enumerate(emph_layout(li, W, H)):
            a, dy = _enter_exit(t, w0 + k * 3 / FPS, w1)
            items.append(dict(kind="box", text=piece, size=sz, key=(li, k), x=x, y=y, alpha=a, dy=dy, red=ctx["red"], emph=True))
            dbg["giant_boxes"].append((x, y, x + vbox(piece, sz).size[0], y + vbox(piece, sz).size[1]))
        return items, cap, dbg
    size = max(S(BOX_PX_MIN_1080), S(BOX_PX.get(ctx["section"], 62)))
    if ctx["red"]:                                   # red keyword: a box like any lyric, red type, one size step up
        x0, y0, x1, y1 = rects[0]
        vert = ctx["orient"] == "vbox"
        sz = int(size * 1.3)
        while sz > S(BOX_PX_MIN_1080) and ((vbox if vert else hbox)(ctx["text"], sz).size[1 if vert else 0] > ((y1 - y0) if vert else (x1 - x0))):
            sz -= 2
        im = (vbox if vert else hbox)(ctx["text"], sz)
        x, y = (x1 - im.size[0], y0) if vert else (x0, y0)
        a, dy = _enter_exit(t, w0, w1)
        items.append(dict(kind="box", text=ctx["text"], size=sz, key=(li, 0), vert=vert, x=x, y=y, alpha=a, dy=dy, red=True))
        return items, cap, dbg
    vis = [(j, p) for j, (p, ap) in enumerate(zip(chunks(li), chunk_appear(li))) if ap <= t][-3:]   # max 3 boxes
    xs = [r[2] for r in rects]; ys = [r[1] for r in rects]
    last_x = None
    for n_, (j, piece) in enumerate(vis):
        ri = 0 if (len(rects) == 1 or n_ < 2) else 1          # P4: right rect takes the first two columns, then the left rect
        if ctx["orient"] == "vbox":
            box = vbox(piece, size)
            x = xs[ri] - box.size[0]; xs[ri] = x - int(size * 0.35)
            y = rects[ri][1] + (n_ % 2) * S(40)
            if last_x is not None and x >= last_x:          # reading order must run right -> left across the screen
                dbg["order_ok"] = False
            last_x = x
        else:
            box = hbox(piece, size)
            x = rects[ri][0]; y = ys[ri]; ys[ri] = y + box.size[1] + int(size * 0.3)
        a, dy = _enter_exit(t, chunk_appear(li)[j], w1)
        items.append(dict(kind="box", text=piece, size=size, key=(li, j), vert=ctx["orient"] == "vbox", x=x, y=y, alpha=a, dy=dy, red=False))
    return items, cap, dbg


def item_bbox(it):
    if it["kind"] == "giant":
        g = vtext(it["text"], it["size"], (255, 255, 255, 255), it["font"])
        return (it["x"], it["y"], it["x"] + g.size[0], it["y"] + g.size[1])
    if it["kind"] == "box":
        im = box_img(it, False)
        return (it["x"], it["y"], it["x"] + im.size[0], it["y"] + im.size[1])
    return (it["x"], it["y"], it["x"] + it["img"].size[0], it["y"] + it["img"].size[1])


def box_img(it, on_dark, bright=False):
    """On a dark background: white box, black type. On a bright background: black box, white type. Red type keeps its red."""
    fg, bg = (INK, PAPER_L) if on_dark else (PAPER_L, INK)
    if it.get("red"):
        fg = RED
    if bright:
        fg, bg = (fg, (255, 255, 255)) if on_dark else ((255, 255, 255) if not it.get("red") else fg, bg)
    mk = vbox if it.get("vert", True) else hbox
    return mk(it["text"], it["size"], fg=fg, bg=bg)


_TONE = {}


def box_on_dark(it):
    """Is the background behind this box dark? Decided once per (line, box, cut) from the scene at three moments of its stay,
    so the box never flips colour mid-line (and every render process agrees)."""
    ci, c = cut_at(t_now[0])
    k = (it["key"], ci)
    if k not in _TONE:
        w0, w1 = line_window(it["key"][0])
        lo, hi = max(w0, c["start"]), min(w1, c["start"] + c["dur"])
        x0, y0, x1, y1 = [int(v) for v in item_bbox(it)]
        vals = []
        for u in (0.25, 0.5, 0.75):                  # three moments of its stay in this cut (clear of transitions); mean tone
            tr = lo + (hi - lo) * u
            items, cap, _ = lyric_layout(tr)
            excl, _ = exclusion_mask(items, cap)
            fr = compose_scene(tr, excl)[0].convert("L")
            reg = np.asarray(fr.crop((max(0, x0), max(0, y0), min(Q.W, x1), min(Q.H, y1))))
            if reg.size:
                vals.append(float(reg.mean()))
        _TONE[k] = bool(not vals or np.mean(vals) < 118)
    return _TONE[k]


def caption_rect(cap):
    f = font(F_L, S(CAPTION_PX_1080), 1)
    w = f.getlength(cap["text"]) + S(80); hb = S(CAPTION_BAND_H_1080)
    yc = Q.H - S(78)
    return (Q.W / 2 - w / 2, yc - hb / 2, Q.W / 2 + w / 2, yc + hb / 2)


def exclusion_mask(items, cap):
    """Layers draw everywhere: the boxes sit on top of them (the keep-out zone that erased layers under the boxes is gone)."""
    boxes = [item_bbox(it) for it in items if it["alpha"] > 0.01]
    if cap:
        boxes.append(caption_rect(cap))
    return _FULL_MASK(Q.W, Q.H), boxes


@lru_cache(4)
def _FULL_MASK(W, H):
    return Image.new("L", (W, H), 255)


def _plate_for(img_rgb, bbox, text_rgb, target=5.0):
    """Measure luminance contrast of text against what is behind it; return (plate_rgb, alpha) needed to reach target."""
    x0, y0, x1, y1 = [int(v) for v in bbox]
    x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(Q.W, x1), min(Q.H, y1)
    if x1 <= x0 or y1 <= y0:
        return None, 0.0, 21.0
    reg = np.asarray(img_rgb.crop((x0, y0, x1, y1)).resize((max(1, (x1 - x0) // 8), max(1, (y1 - y0) // 8)))).reshape(-1, 3)
    lt = rel_lum(text_rgb)
    lums = np.array([rel_lum(p) for p in reg[:: max(1, len(reg) // 400)]])
    worst = float(np.percentile(lums, 25 if lt < 0.2 else 75))   # background behind the text (typical, leaning to the bad side)
    cr = contrast(lt, worst)
    if cr >= target:
        return None, 0.0, cr
    if lt < 0.2:                                            # dark / red text: no white glow behind letters, ever
        return None, 0.0, cr
    plate = INK                                             # light text: dark shadow only
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
            paste(L, vtext(it["text"], it["size"], GRAY_M + (255,), it["font"]), it["x"], it["y"] + it["dy"], it["alpha"])
    if giant:
        bb = [item_bbox(it) for it in giant]
        ub = (min(b[0] for b in bb) - S(20), min(b[1] for b in bb) - S(16), max(b[2] for b in bb) + S(20), max(b[3] for b in bb) + S(16))
        if giant[0]["red"]:                          # red keywords: drawn as they are (contrast rule exempted by the user)
            for it in giant:
                paste(L, vtext(it["text"], it["size"], RED + (255,), it["font"]), it["x"], it["y"] + it["dy"], it["alpha"])
            cr = _plate_for(out, ub, RED)[2]
        else:                                        # tone chosen per column, so a column over a bright area doesn't vanish
            groups = []
            for it in sorted(giant, key=lambda it: it["x"] + it["size"] / 2):     # glyphs of one column share a centre x
                cx = it["x"] + it["size"] / 2
                if groups and cx - groups[-1][-1]["x"] - groups[-1][-1]["size"] / 2 < S(8):
                    groups[-1].append(it)
                else:
                    groups.append([it])
            cr = 21.0
            for grp in groups:
                bb = [item_bbox(it) for it in grp]
                cb = (min(b[0] for b in bb) - S(8), min(b[1] for b in bb) - S(8), max(b[2] for b in bb) + S(8), max(b[3] for b in bb) + S(8))
                amax = max(it["alpha"] for it in grp)
                cd = _plate_for(out, cb, INK)[2]; cl = _plate_for(out, cb, PAPER_L)
                if cd >= max(4.5, cl[2]):            # dark type on a bright area: solid, no backing
                    for it in grp:
                        paste(L, vtext(it["text"], it["size"], INK + (255,), it["font"]), it["x"], it["y"] + it["dy"], it["alpha"])
                    cr = min(cr, cd); continue
                plate, pa, c2 = cl                   # white type: crisp dark keyline (no blur) + a tight dark shadow if needed
                sw = max(2, S(3))
                if plate:
                    hm = Image.new("L", out.size, 0)
                    for it in grp:
                        g = vtext(it["text"], it["size"], (255, 255, 255, 255), it["font"])
                        hm.paste(g.getchannel("A"), (int(it["x"]), int(it["y"] + it["dy"])), g.getchannel("A"))
                    hm = hm.filter(ImageFilter.MaxFilter(max(3, S(5) | 1))).filter(ImageFilter.GaussianBlur(S(2.5)))
                    halo = Image.new("RGBA", out.size, INK + (0,)); halo.putalpha(hm.point(lambda v: int(v * pa * amax)))
                    L.alpha_composite(halo)
                for it in grp:
                    g = vtext(it["text"], it["size"], PAPER_L + (255,), it["font"], sw, INK + (255,))
                    paste(L, g, it["x"] - sw, it["y"] + it["dy"] - sw, it["alpha"])
                cr = min(cr, c2)
        crs.append(("red" if giant[0]["red"] else "giant", cr))
    for it in items:
        if it["kind"] == "box":
            dark = box_on_dark(it)
            img = box_img(it, dark)
            if not dark:
                paste(L, box_shadow(img), it["x"] + hx + S(7), it["y"] + hy + it["dy"] + S(9), it["alpha"] * 0.45)
            paste(L, img, it["x"] + hx, it["y"] + hy + it["dy"], it["alpha"])
            bf = beat_flash(t_now[0])
            if bf > 0 and not it.get("dim"):
                paste(L, box_img(it, dark, True), it["x"] + hx, it["y"] + hy + it["dy"], it["alpha"] * 0.7 * bf)
            crs.append(("red" if it.get("red") else "box", contrast(rel_lum(PAPER_L), rel_lum(INK))))
        elif it["kind"] == "red":                    # red keyword: no backing of any kind
            bb = item_bbox(it)
            cr = _plate_for(out, (bb[0] - S(14), bb[1] - S(10), bb[2] + S(14), bb[3] + S(10)), RED)[2]
            paste(L, it["img"], it["x"] + hx, it["y"] + hy + it["dy"], it["alpha"])
            crs.append(("red", cr))
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
        crs.append(("caption", contrast(rel_lum(PAPER_L), worst)))
    out = out.convert("RGBA"); out.alpha_composite(L)
    dbg["contrast"] = [(k, round(float(x), 2)) for k, x in crs]
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
        elif k == "clock_crop":     # roman numeral ring, enlarged and cropped by the frame edge
            cx_ = W * (0.86 if fx < W / 2 else 0.14); cy_ = H * 0.72
            draw_clock(back, td * 1.5, cx_, cy_, GRAY_M, 0.75, 2.1, t_real=t)
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
        elif k == "torn_strip":
            torn_strip_deco(front, t, ci)
        elif k == "checker_strip":
            checker_strip(front, td, y_frac=0.86 if fy < H / 2 else 0.18)
        elif k == "band":
            pass                    # the repeat band lives in the echo layer now
        elif k == "torn_edge":      # edge line of the tear that cuts the illustration
            _, edge = torn_mask(ci, c)
            ImageDraw.Draw(front).line(edge, fill=GRAY_M + (170,), width=max(1, S(2)))
    return _masked(back, excl), _masked(front, excl)


# ------------------------------------------------------------------ density layers (low tier: 15~45 % or outline only)
ECHO_SIZES_1080 = {"chorus": [220, 60, 140, 40, 100, 180, 70, 120], "verse": [170, 60, 120, 80], "relax": [110]}
ECHO_ALPHA = {"chorus": [0.30, 0.42, 0.22, 0.38, 0.18, 0.28, 0.40, 0.25], "verse": [0.30, 0.42, 0.24, 0.36], "relax": [0.18]}


@lru_cache(256)
def echo_strip(text, size, outline, color):
    """Vertical strip of the text (top to bottom), filled or outline only."""
    f = font(F_L, size)
    tt = text + "　"
    bb = f.getbbox(tt, direction="ttb", features=["vert"])
    sw = max(1, size // 28)
    w, h = bb[2] - bb[0] + 8 + 2 * sw, bb[3] - bb[1] + 8 + 2 * sw
    full = Image.new("L", (w, h), 0)
    ImageDraw.Draw(full).text((sw + 4 - bb[0], sw + 4 - bb[1]), tt, font=f, fill=255, direction="ttb", features=["vert"],
                              stroke_width=sw if outline else 0, stroke_fill=255)
    if outline:
        inner = Image.new("L", full.size, 0)
        ImageDraw.Draw(inner).text((sw + 4 - bb[0], sw + 4 - bb[1]), tt, font=f, fill=255, direction="ttb", features=["vert"])
        full = ImageChops.subtract(full, inner)
    im = Image.new("RGBA", full.size, color + (0,)); im.putalpha(full)
    return im


def echo_text_for(t):
    li = active_line(t)
    if li is None:
        li = max((i for i in LINE_T if line_window(i)[0] <= t), default=None)
    return li


def echo_layer(L, t, c, kd, rows, color):
    """Current line repeated in vertical columns of different size, scrolling up / down at 0.5~3x; some outline-only (recipe 1)."""
    li = echo_text_for(t)
    if li is None or rows <= 0:
        return 0
    text = line_text(li).replace('"', "")
    sizes = ECHO_SIZES_1080[kd]; alphas = ECHO_ALPHA[kd]
    n = min(rows, len(sizes))
    xs = np.linspace(0.06, 0.94, n) if n > 1 else [0.5]
    order = [0, 3, 1, 5, 2, 4, 6, 7][:n] if n > 1 else [0]
    for r in range(n):
        size = S(sizes[order[r] % len(sizes)]); outline = r % 2 == 1
        im = echo_strip(text, size, outline, color)
        sp = (0.5 + 2.5 * ((r * 37) % 10) / 9) * S(60) * (1 if r % 2 == 0 else -1)   # 0.5x ~ 3x, alternating up / down
        off = (t * sp) % im.size[1]
        y = -off - im.size[1]
        x = xs[r] * Q.W - im.size[0] / 2
        a = alphas[r % len(alphas)]
        while y < Q.H:
            paste(L, im, x, y, a)
            y += im.size[1]
    return n


def H_(fy):
    return fy * Q.H


@lru_cache(None)
def halftone_tex(kind):
    W, H = int(Q.W * 1.3), int(Q.H * 1.3)
    L = Image.new("L", (W, H), 0); d = ImageDraw.Draw(L)
    step = S(22) if kind != "chorus" else S(18)
    for yy in range(0, H, step):
        for xx in range(0, W, step):
            r = step * (0.12 + 0.18 * (0.5 + 0.5 * math.sin(xx * 0.01 + yy * 0.013)))
            ox = step / 2 if (yy // step) % 2 else 0
            d.ellipse((xx + ox - r, yy - r, xx + ox + r, yy + r), fill=255)
    if kind == "chorus":                                     # faint checker under the dots
        sq = S(64)
        for yy in range(0, H, sq):
            for xx in range(0, W, sq):
                if (xx // sq + yy // sq) % 2:
                    d.rectangle((xx, yy, xx + sq - 1, yy + sq - 1), fill=60)
    return L


def bg_pattern(frame, t, kd, bg):
    """Slow background layer (parallax: slowest)."""
    tex = halftone_tex("chorus" if kd == "chorus" else "verse")
    ox = int((t * S(8)) % (tex.size[0] - Q.W)); oy = int((t * S(4)) % (tex.size[1] - Q.H))
    m = tex.crop((ox, oy, ox + Q.W, oy + Q.H))
    a = {"chorus": 0.16, "verse": 0.25, "relax": 0.09}[kd]
    col = GRAY_M if sum(bg) <= 380 else GRAY_D
    lay = Image.new("RGBA", (Q.W, Q.H), col + (0,)); lay.putalpha(m.point(lambda v: int(v * a)))
    frame.alpha_composite(lay)


@lru_cache(512)
def cutout_card(crop, w_px, rot, flip, neg):
    src, (cx, cy), cw = CROPS[crop]
    cw = cw or 600
    im = art(src, negative=neg)
    k = ART_UP
    ch = int(cw * 0.75)
    box = (int((cx - cw / 2) * k), int((cy - ch / 2) * k), int((cx + cw / 2) * k), int((cy + ch / 2) * k))
    card = im.crop(box).resize((w_px, int(w_px * 0.75)), Image.LANCZOS)
    base = Image.new("RGBA", card.size, PAPER + (255,))
    base.alpha_composite(card)
    ImageDraw.Draw(base).rectangle((0, 0, base.size[0] - 1, base.size[1] - 1), outline=INK + (255,), width=max(1, S(3)))
    if flip:
        base = base.transpose(Image.FLIP_LEFT_RIGHT)
    return base.rotate(rot, resample=Image.BICUBIC, expand=True)


SLOTS = [(0.17, 0.24), (0.83, 0.22), (0.18, 0.78), (0.82, 0.80), (0.50, 0.16), (0.50, 0.84), (0.10, 0.50), (0.90, 0.52)]


def free_slots(c, avoid):
    fx, fy = focus_target_px(c)
    out = []
    for sx, sy in SLOTS:
        x, y = sx * Q.W, sy * Q.H
        if math.hypot(x - fx, y - fy) < 0.20 * Q.W:          # keep the subject's face clear
            continue
        if any(a[0] - S(120) < x < a[2] + S(120) and a[1] - S(90) < y < a[3] + S(90) for a in avoid):
            continue
        out.append((x, y))
    return out


def popped(t, idx, n):
    """Element `idx` of `n` pops on its beat: 0.9 -> 1.0 with a small overshoot over 5 frames (one element per beat)."""
    bi = bisect.bisect_right(BEATS, t)
    if not bi or n <= 0 or (bi - 1) % n != idx:
        return 1.0
    u = clamp((t - BEATS[bi - 1]) * FPS / 5)
    return 0.9 + 0.1 * arrive(u, 0.05)


WORD_HITS = {45: "健康"}      # the cutouts jump on every sung "健康" (超健康 / 健康)


@lru_cache(None)
def word_hit_times(li):
    w = WORD_HITS.get(li)
    if not w:
        return ()
    return tuple(a for p, a in zip(chunks(li), chunk_appear(li)) if w in p)


def word_hit(t):
    """(hit index, eased progress) of the last word hit on the active line, or None."""
    li = active_line(t)
    hits = [h for h in word_hit_times(li)] if li else []
    k = bisect.bisect_right(hits, t)
    if not k:
        return None
    return k, EASE_OUT(clamp((t - hits[k - 1]) * FPS / 4))


# ------------------------------------------------------------------ props (makeup / scissors / ribbon / signal) on 「その…」
PROP_LINES = (31, 32, 52, 53)                  # その名言 その意見 その批評 / そのカリスマ そのギャグ そのセンス (twice)
PROP_ORDER = ["ribbon", "scissors", "compact", "lipstick", "brush2", "signal", "lipstick2", "brush"]
PROP_KEEP = 1                                  # one prop at a time: each 「その…」 beat swaps it for the next


@lru_cache(None)
def prop_hits():
    """(time, line, prop name) for every sung 「その…」 chunk, snapped to the nearest beat."""
    out = []
    for li in PROP_LINES:
        for p, a in zip(chunks(li), chunk_appear(li)):
            if p.startswith("その"):
                b = min(BEATS, key=lambda x: abs(x - a))
                out.append([b if abs(b - a) < 0.2 else a, li])
    return tuple((t, li, PROP_ORDER[n % len(PROP_ORDER)]) for n, (t, li) in enumerate(out))


def prop_group_end(li):
    """Props of a pair of lines leave when the second line's tail ends."""
    last = li if li in (32, 53) else li + 1
    return tail_end(last)


@lru_cache(64)
def prop_img(name, h_px):
    im = Image.open(ROOT / f"art/props/{name}.png").convert("RGBA")
    k = h_px / im.size[1]
    im = im.resize((max(1, int(im.size[0] * k)), max(1, int(h_px))), Image.LANCZOS)
    pad = S(8)
    a = Image.new("L", (im.size[0] + 2 * pad, im.size[1] + 2 * pad), 0); a.paste(im.getchannel("A"), (pad, pad))
    edge = a.filter(ImageFilter.MaxFilter(max(3, S(7) | 1)))                 # crisp paper edge: a cut-out sticker
    out = Image.new("RGBA", a.size, PAPER_L + (0,)); out.putalpha(edge)
    out.alpha_composite(im, (pad, pad))
    return out




@lru_cache(None)
def prop_place(n):
    """Centre, size and rotation of hit n: the prop fills the open side of the frame (everything left of the lyric
    boxes), big, with a small offset per hit; decided once at its hit, then it stays put."""
    t, li, name = prop_hits()[n]
    items, _, _ = lyric_layout(line_window(li)[1] - 0.05)             # every box this line will show
    boxes = [item_bbox(it) for it in items if not it.get("dim")]
    x1 = min([b[0] for b in boxes] + [Q.W * 0.62]) - S(50)             # open area: left edge -> lyric column
    x0 = Q.W * 0.04
    t1 = prop_group_end(li)
    lb = max([letterbox_px(cc) for cc in CUTS if cc["start"] < t1 and cc["start"] + cc["dur"] > t] + [0])
    y0, y1 = max(Q.H * 0.06, lb + S(40)), min(Q.H * 0.86, Q.H - lb - S(40))   # inside the letterbox, above the caption
    r = np.random.default_rng(n * 131 + 7)
    rot = float(r.uniform(-16, 16))
    src = Image.open(ROOT / f"art/props/{name}.png")
    k = min((x1 - x0) * 0.92 / src.size[0], (y1 - y0) * 0.92 / src.size[1])   # as big as the open area allows
    if name == "signal":                                               # pole runs off the bottom: may use the full height
        k = min((x1 - x0) * 0.92 / src.size[0], (Q.H - lb - y0) * 1.0 / src.size[1])
    h = src.size[1] * k
    cx = (x0 + x1) / 2 + (x1 - x0) * 0.06 * r.uniform(-1, 1)
    cy = (y0 + y1) / 2 + (y1 - y0) * 0.04 * r.uniform(-1, 1)
    return cx, cy, int(h), rot


LETTERBOX_SCENES = (3, 8, 14)


def letterbox_px(c):
    return int(Q.H * 0.115) if c["scene"] in LETTERBOX_SCENES else 0


def zero_g(t, th, n):
    """Weightless drift after the prop lands: slow figure-eight float, a lazy sway and a slow spin (per-prop phases)."""
    r = np.random.default_rng(n * 977 + 3)
    ph = r.uniform(0, 2 * math.pi, 4)
    spin = r.choice([-1, 1]) * r.uniform(2.0, 4.0)                # deg / s
    a = clamp((t - th) * FPS / 8)                                  # eases in once the slam has settled
    u = t - th
    dx = S(26) * math.sin(2 * math.pi * 0.21 * u + ph[0]) + S(9) * math.sin(2 * math.pi * 0.47 * u + ph[1])
    dy = S(20) * math.sin(2 * math.pi * 0.16 * u + ph[2]) - S(14) * u               # bob + a slow rise
    dr = 5.0 * math.sin(2 * math.pi * 0.12 * u + ph[3]) + spin * u
    return dx * a, dy * a, dr * a


def props_active(t):
    """True while a prop is on screen (first 「その」 hit of a pair of lines -> that pair's tail end): the character is left out."""
    for th, li, _ in prop_hits():
        if th <= t < prop_group_end(li):
            return True
    return False


def prop_layer(t):
    """Props slam in on each 「その…」 beat (scale 1.35 -> 1, a twist), then float weightless; kept inside the letterbox."""
    hits = prop_hits()
    k = bisect.bisect_right([h[0] for h in hits], t)
    if not k:
        return None, 0
    L = Image.new("RGBA", (Q.W, Q.H), (0, 0, 0, 0))
    drawn = 0
    for n in range(max(0, k - PROP_KEEP), k):
        th, li, name = hits[n]
        if t >= prop_group_end(li) or prop_group_end(li) != prop_group_end(hits[k - 1][1]):   # only the current pair of lines
            continue
        cx, cy, hpx, rot = prop_place(n)
        u = clamp((t - th) * FPS / 6)
        e = arrive(u, 0.08)
        sc = 1.35 - 0.35 * e
        rr = rot + 14 * (1 - e) * (1 if n % 2 else -1)
        fx_, fy_, fr_ = zero_g(t, th, n)                      # then it floats as if weightless
        rr += fr_
        im = prop_img(name, hpx)
        im = im.resize((max(1, int(im.size[0] * sc)), max(1, int(im.size[1] * sc))), Image.BICUBIC)
        im = im.rotate(rr, resample=Image.BICUBIC, expand=True)
        x, y = cx - im.size[0] / 2 + fx_, cy - im.size[1] / 2 + fy_
        if name == "signal":                                  # the pole runs off the bottom of the picture
            y = Q.H - letterbox_px(cut_at(th + 0.05)[1]) - im.size[1] * 0.92 + fy_
        sh = Image.new("RGBA", im.size, INK + (0,)); sh.putalpha(im.getchannel("A").point(lambda v: int(v * 0.5)))
        paste(L, sh, x + S(10), y + S(12))
        paste(L, im, x, y, min(1.0, u * 3))
        drawn += 1
    lb = letterbox_px(cut_at(t)[1])
    if lb and drawn:                                         # never over the cinema bars
        d = ImageDraw.Draw(L)
        d.rectangle((0, 0, Q.W, lb), fill=(0, 0, 0, 0)); d.rectangle((0, Q.H - lb, Q.W, Q.H), fill=(0, 0, 0, 0))
    return L, drawn


def cutout_layer(L, t, ci, c, avoid):
    """Cutout cluster: other crops of the same character, rotated / mirrored / half-transparent (recipe 6)."""
    specs = c.get("cutouts") or []
    slots = free_slots(c, avoid)
    r = np.random.default_rng(ci * 41)
    order = list(r.permutation(len(slots))) if slots else []
    drawn = 0
    for k, sp in enumerate(specs):
        if k >= len(order):
            break
        x, y = slots[order[k]]
        card = cutout_card(sp["crop"], S(sp["w"] * 1920), sp["rot"], sp["flip"], False)
        s = popped(t, k, len(specs) + 1)
        wh = word_hit(t)
        jx = jy = 0.0
        if wh:                                                # word hit: every card steps once, two of them pop
            n_hit, e = wh
            for h in range(n_hit):
                prog = e if h == n_hit - 1 else 1.0
                jx += (1 if (k + h) % 2 else -1) * S(46) * prog; jy += (1 if h % 2 else -1) * S(22) * prog
            if (k + n_hit) % len(specs) < 2 and e < 1:
                s = 0.9 + 0.1 * arrive(e, 0.06)
        if s != 1.0:
            card = card.resize((max(1, int(card.size[0] * s)), max(1, int(card.size[1] * s))), Image.BICUBIC)
        drift = (t - c["start"]) * S(14) * (1 if k % 2 else -1)              # slow, opposite to the echo rows
        paste(L, card, x - card.size[0] / 2 + drift + jx, y - card.size[1] / 2 - drift * 0.4 + jy, sp["alpha"])
        drawn += 1
    return drawn


def keyword_pop(L, t, c, avoid):
    """Big keyword in a vertical column, outline only; letters pop in 2 frames apart, one turns red on every beat (recipe 2)."""
    li = active_line(t)
    if li is None:
        return False
    word = (RED_TEXT.get(li) or chunks(li)[0])[:6]
    size = int(Q.H * 0.13)
    fx, fy = focus_target_px(c)
    hgt = size * len(word) * 1.02
    cands = [(Q.W * 0.04, Q.H * 0.08), (Q.W * 0.96 - size * 1.1, Q.H * 0.08), (Q.W * 0.44, Q.H * 0.08), (Q.W * 0.30, Q.H * 0.10)]
    pos = None
    for x, y in cands:
        box = (x, y, x + size * 1.1, y + hgt)
        if box[3] > Q.H * 0.88:
            continue
        if overlaps(box, [(a[0] - S(60), a[1] - S(60), a[2] + S(60), a[3] + S(60)) for a in avoid]):
            continue
        if box[0] - S(80) < fx < box[2] + S(80) and box[1] - S(80) < fy < box[3] + S(80):
            continue
        pos = (x, y); break
    if pos is None:
        return False
    w0, _ = line_window(li)
    bi = bisect.bisect_right(BEATS, t)
    y = pos[1]
    for k, ch in enumerate(word):
        u = ((t - w0) * FPS - 2 * k) / 10
        if u > 0:
            s_ = max(4, int(size * min(1.1, pop(u))))
            g = echo_strip(ch, s_, True, GRAY_M)
            paste(L, g, pos[0] + (size - s_) / 2, y, 0.42)
            if bi and (bi - 1) % len(word) == k:          # beat letter flips to red
                paste(L, vtext(ch, s_, RED + (255,), F_L), pos[0] + (size - s_) / 2 + S(4), y + S(4), 0.45)
        y += size * 1.02
    return True


def ring_text(L, t, cx, cy, color):
    """Current line written around the clock ring, slowly turning (recipe 3, on twos)."""
    li = echo_text_for(t)
    if li is None:
        return False
    text = (line_text(li).replace('"', "") + "　") * 2
    R = Q.H * 0.47; td = math.floor(t * 12) / 12
    n = len(text)
    for k, ch in enumerate(text):
        a = 2 * math.pi * k / n + math.radians(td * 4)
        g = htext(ch, S(30), color + (255,), F_L).rotate(-math.degrees(a), resample=Image.BICUBIC, expand=True)
        paste(L, g, cx + R * math.sin(a) - g.size[0] / 2, cy - R * math.cos(a) - g.size[1] / 2, 0.34)
    return True


def micro_text(L, t, color):
    """Tiny translation / pronunciation / roman numerals running down the side edges (recipe 5)."""
    li = echo_text_for(t)
    if li is None:
        return False
    s_ = f"{line_text(li)}　{PRON[li - 1].strip()}　{KO[li - 1].strip()}　"
    g = vtext(s_, S(14), color + (255,), F_L)
    oy = (t * S(30)) % max(1, g.size[1])
    for k in range(3):
        paste(L, g, S(52), S(90) - oy + k * g.size[1], 0.30)
    nums = "  ".join(["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"])
    g2 = vtext(nums, S(13), color + (255,), F_L)
    oy2 = (t * S(20)) % max(1, g2.size[1])
    for k in range(3):
        paste(L, g2, Q.W - S(52), S(90) - oy2 + k * g2.size[1], 0.26)
    return True


def torn_strip_deco(L, t, ci):
    """Paper strips with torn edges crossing the frame edge to edge (attached to the frame, never floating)."""
    r = np.random.default_rng(ci * 61)
    W, H = Q.W, Q.H
    for k in range(2):
        h = r.uniform(50, 100) * Q.s; ln = W * 2.0
        strip = Image.new("RGBA", (int(ln), int(h * 1.6)), (0, 0, 0, 0)); d = ImageDraw.Draw(strip)
        top = [(x, h * 0.3 + r.uniform(-1, 1) * h * 0.12) for x in np.linspace(0, ln, 120)]
        bot = [(x, h * 1.3 + r.uniform(-1, 1) * h * 0.12) for x in np.linspace(ln, 0, 120)]
        d.polygon(top + bot, fill=(PAPER_L if k == 0 else GRAY_M) + (215,))
        ang = r.uniform(12, 24) * (1 if k else -1)
        strip = strip.rotate(ang, resample=Image.BICUBIC, expand=True)
        slide = ((math.floor(t * 12) / 12) * S(40) * (1 if k else -1)) % S(200)
        paste(L, strip, W / 2 - strip.size[0] / 2 + slide - S(100), H * (0.30 + 0.38 * k) - strip.size[1] / 2)


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
    if props_active(t):                              # props replace the character: no illustration / cutouts / ghost
        img, eyes = None, []
    back, front = decorations(ci, c, t, focus, bg, excl)
    kd = c.get("density"); layers = []
    if kd:
        bg_pattern(frame, t, kd, bg); layers.append("bg_pattern")
    frame.alpha_composite(back)
    if any(k in (c.get("deco") or []) for k in ("clock", "clock_crop", "checker", "speed_lines")):
        layers.append("deco_back")
    tc = text_color_for(bg)
    low = Image.new("RGBA", (W, H), (0, 0, 0, 0))            # low-tier typography, behind the illustration
    if kd:
        if echo_layer(low, t, c, kd, c.get("echo_rows", 0), tc):
            layers.append("echo")
        if c.get("ring_text") and ring_text(low, t, focus[0], focus[1], tc):
            layers.append("ring_text")
        if c.get("micro_text") and micro_text(low, t, GRAY_M):
            layers.append("micro_text")
    frame.alpha_composite(_masked(low, excl))
    avoid = DEBUG_ACTIVE_BOXES[0]
    if kd and c.get("cutouts") and not props_active(t):
        cl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        n_c = cutout_layer(cl, t, ci, c, avoid)
        frame.alpha_composite(cl)
        if n_c:
            layers.append(f"cutouts:{n_c}")
    if img is not None:
        if c["scene"] in CROP_SCENES + (4, 5, 16):
            frame.alpha_composite(ghost_echo(img, ci, t))
        frame.alpha_composite(img)
        layers.append("illustration")
    frame.alpha_composite(front)
    if any(k in (c.get("deco") or []) for k in ("starburst", "torn_strip", "checker_strip", "guides", "code", "torn_edge")):
        layers.append("deco_front")
    if kd and c.get("keyword_pop"):
        kp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if keyword_pop(kp, t, c, avoid):
            frame.alpha_composite(_masked(kp, excl)); layers.append("keyword_pop")
    if img is None and c["scene"] not in (10, 18):
        zm, px, py, rot = cam_motion(ci, c, t)
        cx, cy = W / 2, H / 2
        k = 1 / zm
        frame = frame.transform((W, H), Image.AFFINE, (k, 0, cx - k * (cx + px), 0, k, cy - k * (cy + py)), resample=Image.BILINEAR,
                                fillcolor=bg + (255,))
    if img is not None and c["scene"] not in (10, 13, 17, 18):
        frame = shade(frame, ci, sum(bg) <= 380)
    if c["scene"] in LETTERBOX_SCENES:  # cinema letterbox like ref B's band scenes (framing)
        d = ImageDraw.Draw(frame); lb = int(H * 0.115)
        d.rectangle((0, 0, W, lb), fill=INK + (255,)); d.rectangle((0, H - lb, W, H), fill=INK + (255,))
    if c["scene"] == 13:
        frame = Image.blend(frame, Image.new("RGBA", (W, H), (250, 250, 250, 255)), 0.82)
    deco_px = int((np.asarray(back.getchannel("A")) > 8).sum() + (np.asarray(front.getchannel("A")) > 8).sum()) if excl is not None else 0
    return frame, dict(focus=focus, eyes=eyes, bg=bg, deco_px=deco_px, layers=layers,
                       deco_kinds=[k for k in (c.get("deco") or []) if k != "band"])


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


DEBUG_ACTIVE_BOXES = [[]]


def render_frame(t):
    W, H = Q.W, Q.H
    ci, c = cut_at(t)
    items, cap, dbg = lyric_layout(t)
    excl, lyric_boxes = exclusion_mask(items, cap)
    DEBUG_ACTIVE_BOXES[0] = [item_bbox(it) for it in items if not it.get("dim")]
    frame, info, tr = compose_scene(t, excl)
    pl, n_props = prop_layer(t)
    if pl is not None and n_props:
        frame.alpha_composite(pl); info.setdefault("layers", []).append(f"props:{n_props}")
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
    act = [item_bbox(it) for it in items if not it.get("dim") and it["alpha"] > 0.5]
    layers = list(info.get("layers", [])) + (["active_lyric"] if act else []) + (["hud"] if c["scene"] not in (10, 13, 17, 18) else [])
    DEBUG.update(dbg, cut=ci, focus=None if (c.get("nochar") or props_active(t)) else info["focus"], transition=tr, layers=layers,
                 deco_kinds=info.get("deco_kinds", []), eye_cover=any(overlaps(b, info.get("eyes", [])) for b in act),
                 deco_over_lyrics=0)
    return out


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
