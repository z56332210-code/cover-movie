"""Per-frame features at 30 fps (320x180): palette area fractions, luma std, block difference to the previous frame,
RGB channel misalignment (glitch cue). Same script for the reference and our renders.
usage: python3 tools/frame_features.py <video> <out.npz>"""
import sys, subprocess, json
import numpy as np

PALETTE = {"lav": (0xF1, 0xB5, 0xFB), "mag": (0xEB, 0x00, 0x8D), "navy": (0x15, 0x18, 0x3C), "white": (0xFF, 0xFF, 0xFF), "black": (0, 0, 0)}
W, H = 320, 180

def frames(path):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps=30,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = W * H * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n: break
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)

def features(path):
    P = np.array(list(PALETTE.values()), np.float32)
    names = list(PALETTE)
    out = {k: [] for k in names + ["other", "gray", "luma_mean", "luma_std", "bdiff", "chroma_split", "sat"]}
    prev = None
    for f in frames(path):
        x = f.reshape(-1, 3).astype(np.float32)
        d = np.sqrt(((x[:, None, :] - P[None]) ** 2).sum(-1))
        near = d.argmin(1); dmin = d.min(1)
        for i, k in enumerate(names): out[k].append(float(((near == i) & (dmin < 60)).mean()))
        out["other"].append(float((dmin >= 60).mean()))
        mx, mn = x.max(1), x.min(1)
        sat = (mx - mn) / (mx + 1e-3)
        out["sat"].append(float(sat.mean()))
        out["gray"].append(float(((mx - mn) < 18).mean()))                        # achromatic share (white/grey/black)
        luma = x @ np.array([0.299, 0.587, 0.114], np.float32)
        out["luma_mean"].append(float(luma.mean())); out["luma_std"].append(float(luma.std()))
        b = luma.reshape(H // 10, 10, W // 10, 10).mean((1, 3))
        out["bdiff"].append(float(np.abs(b - prev).mean()) if prev is not None else 0.0); prev = b
        # glitch cue: R and B edges horizontally offset against G
        g = f[..., 1].astype(np.float32); r = f[..., 0].astype(np.float32)
        e0 = np.abs(r - g).mean()
        e1 = min(np.abs(np.roll(r, s, 1) - g).mean() for s in (-6, -3, 3, 6))
        out["chroma_split"].append(float(e0 - e1))
    return {k: np.array(v, np.float32) for k, v in out.items()}

if __name__ == "__main__":
    r = features(sys.argv[1]); np.savez_compressed(sys.argv[2], **r)
    print(len(r["bdiff"]), "frames")
