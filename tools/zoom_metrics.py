"""Camera zoom report from the rendered video (feature tracking, not from the plan's numbers).

    python3 tools/zoom_metrics.py renders/x.mp4 <song time of the file's first frame> [plan json]

For every frame pair: Shi-Tomasi corners + Lucas-Kanade flow + RANSAC similarity -> scale.
Per cut: net zoom % (transition / impact frames excluded), zoom-direction flips per second, peak zoom speed %/s.
"""
import json, math, subprocess, sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
vid, t0 = sys.argv[1], float(sys.argv[2])
plan = json.load(open(sys.argv[3] if len(sys.argv) > 3 else ROOT / "plan/cutlist_draft.json"))
FPS = 30
W, H = 480, 270
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", vid, "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W)
n = len(fr)

scale = np.ones(n - 1); ok = np.zeros(n - 1, bool)
for k in range(n - 1):
    p0 = cv2.goodFeaturesToTrack(fr[k], maxCorners=500, qualityLevel=0.01, minDistance=5)
    if p0 is None or len(p0) < 20:
        continue
    p1, st, _ = cv2.calcOpticalFlowPyrLK(fr[k], fr[k + 1], p0, None, winSize=(21, 21), maxLevel=3)
    g = st.ravel() == 1
    if g.sum() < 20:
        continue
    M, inl = cv2.estimateAffinePartial2D(p0[g], p1[g], method=cv2.RANSAC, ransacReprojThreshold=1.0)
    if M is None or inl is None or inl.sum() < 15:
        continue
    scale[k] = math.hypot(M[0, 0], M[1, 0]); ok[k] = True

ls = np.log(scale)
cuts = [c for c in plan["cuts"] if t0 - 1e-6 <= c["start"] < t0 + n / FPS]
rows = []
for ci, c in enumerate(cuts):
    k0 = math.ceil((c["start"] - t0) * FPS - 1e-6)
    k1 = min(n - 1, math.ceil((c["start"] + c["dur"] - t0) * FPS - 1e-6) - 1)     # last frame of the cut
    excl_head = 7 if (c.get("impact") or c.get("transition_in") in ("T1", "T2", "T3", "T4", "T5", "T6", "edit_mask")) else 2
    a, b = k0 + excl_head, k1 - 6                                                  # pairs inside the cut, transitions excluded
    seg = ls[a:b]; okseg = ok[a:b]
    dur = c["dur"]
    if len(seg) < 4:
        rows.append(dict(t=round(c["start"], 2), dur=round(dur, 2), cam=c.get("cam"), net_zoom=None, flips=0, flips_per_s=0.0,
                         peak_speed=None, impact=bool(c.get("impact")), note="측정 구간 짧음"))
        continue
    seg = np.where(okseg, seg, 0.0)
    net = (math.exp(seg.sum()) - 1) * 100
    sm = np.convolve(seg, np.ones(5) / 5, mode="same")
    thr = 0.0004                                                                   # 1.2 %/s
    sgn = [1 if v > thr else -1 if v < -thr else 0 for v in sm]
    nz = [s for s in sgn if s]
    flips = sum(1 for x, y in zip(nz, nz[1:]) if x != y)
    win = 8
    sp = max(abs(seg[i:i + win].sum()) for i in range(0, max(1, len(seg) - win + 1))) * FPS / win * 100
    rows.append(dict(t=round(c["start"], 2), dur=round(dur, 2), cam=c.get("cam"), net_zoom=round(net, 2), flips=flips,
                     flips_per_s=round(flips / dur, 2), peak_speed=round(sp, 1), impact=bool(c.get("impact"))))
long_ = [r for r in rows if r["dur"] >= 1.0 and r["net_zoom"] is not None]
imp = [c["start"] for c in cuts if c.get("impact")]
res = dict(file=vid, range=[t0, round(t0 + n / FPS, 2)],
           flips_per_s_long_cuts=round(sum(r["flips"] for r in long_) / max(1e-6, sum(r["dur"] for r in long_)), 2),
           max_flips_per_s=max((r["flips_per_s"] for r in long_), default=0),
           max_abs_net_zoom=max((abs(r["net_zoom"]) for r in long_), default=0),
           max_peak_speed=max((r["peak_speed"] for r in long_), default=0),
           impacts=len(imp), min_impact_gap=round(min((b - a for a, b in zip(imp, imp[1:])), default=99), 2),
           tracked_pairs_pct=round(ok.mean() * 100, 1), cuts=rows)
print(json.dumps({k: v for k, v in res.items() if k != "cuts"}, ensure_ascii=False))
for r in rows:
    print(r)
json.dump(res, open(Path(vid).with_name(Path(vid).stem + "_zoom.json"), "w"), ensure_ascii=False, indent=1)
