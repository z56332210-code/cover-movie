"""Measure a clip the way the brief defines it (2 fps frames, PIL/numpy):
mean brightness (visible picture area and whole frame), visible-area ratio (rows not black), cut count (frame difference).
usage: python3 tools/measure.py <video> [start] [dur]"""
import sys, subprocess, json
import numpy as np

def frames(path, ss=0.0, dur=20.0, w=480):
    h = None
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", path]))
    W0, H0 = info["streams"][0]["width"], info["streams"][0]["height"]; h = round(w * H0 / W0 / 2) * 2
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(ss), "-t", str(dur), "-i", path, "-vf", f"fps=2,scale={w}:{h},format=gray", "-f", "rawvideo", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)

def measure(path, ss=0.0, dur=20.0):
    F = frames(path, ss, dur)
    rows = F.mean(axis=2)                                   # per-row mean, per frame
    vis = rows > 14                                         # a row counts as picture if it is not letterbox black
    vis_ratio = float(vis.mean())
    mean_all = float(F.mean())
    mean_vis = float(np.mean([f[v].mean() for f, v in zip(F, vis) if v.any()]))
    d = np.abs(np.diff(F, axis=0)).mean(axis=(1, 2))        # frame-to-frame difference (raw, grain included)
    # cut = low correlation between consecutive blurred 24x(h) thumbnails of the picture area (grain-proof)
    def thumb(f, v):
        a = f[v] if v.any() else f
        hh, ww = a.shape; a = a[: hh - hh % 6, : ww - ww % 20].reshape(6, (hh - hh % 6) // 6, 20, (ww - ww % 20) // 20).mean(axis=(1, 3))
        return (a - a.mean()) / (a.std() + 1e-3)
    T = [thumb(f, v) for f, v in zip(F, vis)]
    corr = [float((T[i] * T[i + 1]).mean()) for i in range(len(T) - 1)]
    lit = [bool(v.any()) for v in vis]
    cuts = sum(1 for i, c in enumerate(corr) if lit[i] and lit[i + 1] and c < 0.5)
    cut_at = [round((i + 1) / 2, 1) for i, c in enumerate(corr) if lit[i] and lit[i + 1] and c < 0.5]
    return dict(cut_times=cut_at, frames=len(F), mean_visible=round(mean_vis, 1), mean_whole=round(mean_all, 1), visible_ratio=round(vis_ratio, 3),
                cuts=cuts, diffs=[round(float(x), 1) for x in d])

if __name__ == "__main__":
    r = measure(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0, float(sys.argv[3]) if len(sys.argv) > 3 else 20)
    print(json.dumps({k: v for k, v in r.items() if k != "diffs"}))
    print("diffs", r["diffs"])
