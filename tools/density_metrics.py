"""Screen-density report (per section kind) for a rendered range.

    python3 tools/density_metrics.py renders/x.mp4 <song time of first frame> [plan json] [--layers]

filled %  : frame -> 480x270 gray -> Canny(50, 150) -> 16 x 18 grid of blocks (30 x 15 px); share of blocks whose edge pixels >= 3 %
edge %    : edge pixels / all pixels
Sampled at 10 fps. Sections: verse (verse / pre-chorus / intro), chorus, relax (relaxed scenes 4 / 16 and the ending cards).
--layers  : also re-render the sampled frames to read the renderer's layer list (slow).
"""
import json, math, subprocess, sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
vid, t0 = args[0], float(args[1])
plan = json.load(open(args[2] if len(args) > 2 else ROOT / "plan/cutlist_draft.json"))
W, H = 480, 270
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", vid, "-vf", f"fps=10,scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W)
CHORUS = {"chorus_a", "chorus_b", "last_chorus"}


def kind_of(c):
    if c["scene"] in (10, 13):
        return None
    if c["scene"] in (4, 16, 17, 18, 1):
        return "relax"
    return "chorus" if c.get("section") in CHORUS else "verse"


def cut_at(t):
    for c in plan["cuts"]:
        if c["start"] <= t < c["start"] + c["dur"]:
            return c
    return plan["cuts"][-1]


acc = defaultdict(lambda: dict(filled=[], edge=[], layers=[]))
for k, g in enumerate(fr):
    t = t0 + k / 10
    c = cut_at(t)
    kd = kind_of(c)
    f = (t - c["start"]) * 30; fe = (c["start"] + c["dur"] - t) * 30
    if kd is None or f < 6 or fe < 6:            # skip transition frames
        continue
    e = cv2.Canny(g, 50, 150) > 0
    blocks = e.reshape(18, H // 18, 16, W // 16).mean((1, 3))
    acc[kd]["filled"].append(float((blocks >= 0.03).mean() * 100))
    acc[kd]["edge"].append(float(e.mean() * 100))
    acc[kd]["t"] = acc[kd].get("t", []) + [round(t, 2)]

if "--layers" in sys.argv:
    sys.path.insert(0, str(ROOT / "tools"))
    import render as R
    R.setup(False)
    for kd, a in acc.items():
        for t in a.get("t", [])[::5]:
            R.render_frame(t)
            a["layers"].append(len(R.DEBUG.get("layers", [])))
            a.setdefault("layer_names", []).append(R.DEBUG.get("layers", []))

res = {}
for kd, a in acc.items():
    res[kd] = dict(frames=len(a["filled"]), filled_pct=round(float(np.mean(a["filled"])), 1),
                   filled_min=round(float(np.min(a["filled"])), 1), filled_max=round(float(np.max(a["filled"])), 1),
                   edge_pct=round(float(np.mean(a["edge"])), 2), edge_min=round(float(np.min(a["edge"])), 2),
                   edge_max=round(float(np.max(a["edge"])), 2))
    if a["layers"]:
        res[kd]["layers_mean"] = round(float(np.mean(a["layers"])), 1)
        res[kd]["layers_min"] = int(np.min(a["layers"]))
        res[kd]["layer_example"] = a["layer_names"][len(a["layer_names"]) // 2]
print(json.dumps(res, ensure_ascii=False))
json.dump(res, open(Path(vid).with_name(Path(vid).stem + "_density.json"), "w"), ensure_ascii=False, indent=1)
