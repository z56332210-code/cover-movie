"""Measure a video window the same way for the reference and our render.
cuts, palette area shares, halftone area, contrast (luma std), motion (1/15 s frame difference, transitions excluded),
glitch events, camera speed per shot thirds (Farneback flow, px/s at 1080p).
usage: python3 tools/metrics.py <video> <start> <dur> [label]"""
import sys, subprocess, json
import numpy as np, cv2
from scipy import ndimage

PAL = {"lav": (0xF1, 0xB5, 0xFB), "mag": (0xEB, 0x00, 0x8D), "navy": (0x15, 0x18, 0x3C), "white": (0xFF, 0xFF, 0xFF), "black": (0, 0, 0)}

def grab(path, ss, dur, w, h, fps=30):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(ss), "-t", str(dur), "-i", path, "-vf", f"fps={fps},scale={w}:{h}",
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)

def metrics(path, ss, dur):
    F = grab(path, ss, dur, 320, 180).astype(np.float32)
    n = len(F)
    P = np.array(list(PAL.values()), np.float32)
    d = np.sqrt(((F.reshape(n, -1, 1, 3) - P[None, None]) ** 2).sum(-1))
    near, dmin = d.argmin(-1), d.min(-1)
    share = {k: float(((near == i) & (dmin < 60)).mean()) for i, k in enumerate(PAL)}
    share["tint_or_edge"] = float((dmin >= 60).mean())
    luma = F @ np.array([0.299, 0.587, 0.114], np.float32)
    contrast = float(luma.reshape(n, -1).std(1).mean())
    # cuts: block-difference spike (same rule used on the reference scene analysis)
    B = luma.reshape(n, 18, 10, 32, 10).mean((2, 4))
    bd = np.r_[0, np.abs(np.diff(B, axis=0)).mean((1, 2))]
    med = np.array([np.median(bd[max(0, i - 8): i + 9]) for i in range(n)])
    cut = [i for i in range(1, n) if bd[i] > 18 and bd[i] > 3 * med[i] + 4]
    cuts = []
    for c in cut:                                     # merge 1-2 frame double hits
        if not cuts or c - cuts[-1] > 2: cuts.append(c)
    # motion: 15 fps pairs, +-0.3 s around cuts and black frames excluded
    G = luma[::2]; md = np.abs(np.diff(G, axis=0)).mean((1, 2))
    keep = np.ones(len(md), bool)
    for c in cuts: keep[max(0, c // 2 - 4): c // 2 + 5] = False
    lit = G.mean((1, 2)) > 12; keep &= lit[:-1] & lit[1:]
    motion = float(md[keep].mean()) if keep.any() else 0.0
    # glitch: transient green/yellow-green pixels (never in the palette)
    r, g, b = F[..., 0], F[..., 1], F[..., 2]
    odd = (g > r + 25) & (g > b + 5) & (g > 80)
    tr = odd.copy(); tr[3:-3] &= ~odd[:-6] & ~odd[6:]
    on = tr.reshape(n, -1).mean(1) > 0.0003
    ev = []; i = 0
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]: j += 1
            ev.append(j - i); i = j
        else: i += 1
    # halftone: 640x360, dark/magenta dots (3-45 px components, roundish) counted per 20x20 block
    H = grab(path, ss, dur, 640, 360, fps=2).astype(np.float32)
    ht = []
    for fr in H:
        dd = np.sqrt(((fr.reshape(-1, 1, 3) - P[None]) ** 2).sum(-1)).argmin(-1).reshape(360, 640)
        ink = (dd == 1) | (dd == 2) | (dd == 4)
        lab, k = ndimage.label(ink)
        if k == 0: ht.append(0.0); continue
        area = ndimage.sum(ink, lab, range(1, k + 1))
        objs = ndimage.find_objects(lab)
        small = np.zeros((18, 32))
        for a, sl in zip(area, objs):
            hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            if 3 <= a <= 45 and max(hh, ww) <= 9 and a >= 0.45 * hh * ww:
                small[min(17, (sl[0].start + hh // 2) // 20), min(31, (sl[1].start + ww // 2) // 20)] += 1
        ht.append(float((small >= 5).mean()))
    # camera speed per shot thirds (median Farneback flow magnitude), shots = between detected cuts
    Gs = luma[::2].astype(np.uint8); bounds = [0] + [c // 2 for c in cuts] + [len(Gs)]
    cam = []
    for a, e in zip(bounds, bounds[1:]):
        a2, e2 = a + 2, e - 2
        if e2 - a2 < 6 or Gs[a2:e2].mean() < 12: continue
        mags = [float(np.median(np.linalg.norm(cv2.calcOpticalFlowFarneback(Gs[k], Gs[k + 1], None, 0.5, 3, 21, 3, 5, 1.1, 0), axis=-1))) * 15 * 6
                for k in range(a2, e2 - 1)]
        m3 = len(mags) // 3
        cam.append(dict(t=round(ss + a / 15, 2), thirds=[round(float(np.mean(x)), 1) for x in (mags[:max(1, m3)], mags[m3:max(m3 + 1, 2 * m3)], mags[2 * m3:])]))
    return dict(frames=n, cuts=len(cuts), cut_times=[round(ss + c / 30, 2) for c in cuts], palette={k: round(v, 3) for k, v in share.items()},
                halftone=round(float(np.mean(ht)), 3), contrast=round(contrast, 1), motion=round(motion, 2),
                glitch_events=len(ev), glitch_mean_frames=round(float(np.mean(ev)), 1) if ev else 0, camera=cam)

if __name__ == "__main__":
    r = metrics(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]))
    print(json.dumps(r, ensure_ascii=False))
