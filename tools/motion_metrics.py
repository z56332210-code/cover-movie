"""Pass/fail motion numbers for a rendered range (gray 160x90, mean absolute frame difference).

    python3 tools/motion_metrics.py renders/x.mp4 <t0 of the file in song time> [plan json]

pre_cut   : mean change over the 6 frame pairs right before each cut (target >= 8)
settle    : after each cut, time until the change falls to <= 25% of its post-cut peak (target 0.35~0.5 s)
non_cut   : mean change over all frame pairs except the 2 around each cut boundary (target >= 4)
same_tr   : consecutive identical transitions in the range (target 0)
"""
import json, math, subprocess, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
vid, t0 = sys.argv[1], float(sys.argv[2])
plan = json.load(open(sys.argv[3] if len(sys.argv) > 3 else ROOT / "plan/cutlist_draft.json"))
FPS = 30
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", vid, "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160).astype(np.float32)
d = np.abs(np.diff(fr, axis=0)).mean((1, 2))          # d[k] = change between frame k and k+1
n = len(fr); t1 = t0 + n / FPS
cuts = [c for c in plan["cuts"] if t0 + 0.25 < c["start"] < t1 - 0.6]
pre, settle, rows = [], [], []
mask = np.ones(len(d), bool)
strict = np.ones(len(d), bool)
for c in cuts:
    k = math.ceil((c["start"] - t0) * FPS - 1e-6)      # first frame that shows the new cut
    mask[max(0, k - 2):k + 1] = False                  # pairs (k-2,k-1),(k-1,k): the cut itself
    strict[max(0, k - 7):k + 12] = False               # strict: also drop the whole transition window
    p = d[max(0, k - 7):k - 1].mean()                  # 6 pairs before the boundary pair
    post = d[k:k + 24]
    peak = post[:3].max()
    s = next((j for j in range(3, len(post)) if post[j] <= 0.25 * peak), len(post)) / FPS
    pre.append(p); settle.append(s)
    rows.append(dict(t=round(c["start"], 2), tr=c.get("transition_in"), pre=round(float(p), 2), settle=round(s, 2)))
same = sum(1 for a, b in zip(cuts, cuts[1:]) if a.get("transition_in") == b.get("transition_in"))
res = dict(file=vid, range=[round(t0, 2), round(t1, 2)], cuts=len(cuts),
           pre_cut=round(float(np.mean(pre)), 2) if pre else None, pre_cut_min=round(float(np.min(pre)), 2) if pre else None,
           settle_mean=round(float(np.mean(settle)), 3) if settle else None,
           settle_min=round(float(np.min(settle)), 3) if settle else None, settle_max=round(float(np.max(settle)), 3) if settle else None,
           non_cut=round(float(d[mask].mean()), 2), non_cut_strict=round(float(d[strict].mean()), 2) if strict.any() else None, same_transition_in_a_row=same, per_cut=rows)
print(json.dumps({k: v for k, v in res.items() if k != "per_cut"}, ensure_ascii=False))
json.dump(res, open(Path(vid).with_name(Path(vid).stem + "_motion.json"), "w"), ensure_ascii=False, indent=1)
