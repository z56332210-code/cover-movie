"""Glitch events (off-palette green/cyan/yellow strips, 1-6 frames) and camera speed per shot thirds (Farneback flow, 15 fps).
usage: python3 tools/ref_glitch_cam.py <video> <shots.json> <out.json>"""
import sys, json, subprocess
import numpy as np, cv2
W, H = 320, 180
raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", sys.argv[1], "-vf", f"fps=30,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
F = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
r, g, b = [F[..., i].astype(np.int16) for i in range(3)]
odd = (g > r + 25) & (g > b + 5) & (g > 80)                            # green / yellow-green pixels never occur in the palette
# transient only: odd now, not odd 3 frames before and after (static green props would not count)
tr = odd.copy(); tr[3:-3] &= ~odd[:-6] & ~odd[6:]
frac = tr.reshape(len(F), -1).mean(1)
on = frac > 0.0003
ev = []; i = 0
while i < len(on):
    if on[i]:
        j = i
        while j < len(on) and on[j]: j += 1
        ev.append([round(i / 30, 3), j - i]); i = j
    else: i += 1
shots = json.load(open(sys.argv[2]))["shots"]
gray = F[::2].mean(-1).astype(np.uint8)
cam = []
for s in shots:
    a, e = int(s["t0"] * 15) + 2, int(s["t1"] * 15) - 2
    if e - a < 6 or s["type"] in ("D",): cam.append(None); continue
    mags = []
    for k in range(a, e - 1):
        fl = cv2.calcOpticalFlowFarneback(gray[k], gray[k + 1], None, 0.5, 3, 21, 3, 5, 1.1, 0)
        mags.append(float(np.median(np.linalg.norm(fl, axis=-1))) * 15 * (1920 / W))   # px/s at 1080p
    n = len(mags); th = [np.mean(mags[:max(1, n // 3)]), np.mean(mags[n // 3: max(n // 3 + 1, 2 * n // 3)]), np.mean(mags[2 * n // 3:])]
    cam.append([round(x, 1) for x in th])
json.dump(dict(glitch_events=ev, glitch_frac=frac.round(5).tolist(), cam=cam), open(sys.argv[3], "w"))
print("glitch events", len(ev), "mean len frames", np.mean([e[1] for e in ev]) if ev else 0)
