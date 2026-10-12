"""Off-palette check: every pixel must lie near a mix of two palette colours (lavender, magenta, navy, white, black)
or a grey (mono/grey layers). Glitch frames are exempt. Samples 2 fps.
usage: python3 tools/palette_check.py <video>"""
import sys, subprocess, json
import numpy as np
P = np.array([(0xF1, 0xB5, 0xFB), (0xEB, 0x00, 0x8D), (0x15, 0x18, 0x3C), (255, 255, 255), (0, 0, 0)], np.float32)
raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", sys.argv[1], "-vf", "fps=2,scale=320:180", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
F = np.frombuffer(raw, np.uint8).reshape(-1, 180, 320, 3).astype(np.float32)
def seg_dist(x, a, b):
    ab = b - a; t = np.clip(((x - a) @ ab) / (ab @ ab), 0, 1)[..., None]
    return np.linalg.norm(x - (a + t * ab), axis=-1)
bad_frames = []; frac = []
for i, f in enumerate(F):
    x = f.reshape(-1, 3)
    d = np.full(len(x), 1e9, np.float32)
    for a in range(5):
        for b in range(a + 1, 5): d = np.minimum(d, seg_dist(x, P[a], P[b]))
    d = np.minimum(d, np.abs(x - x.mean(1, keepdims=True)).max(1))           # greys (mono / grey layers)
    g = (x[:, 1] > x[:, 0] + 25) & (x[:, 1] > x[:, 2] + 5)                  # glitch green strips are exempt
    off = (d > 40) & ~g
    frac.append(float(off.mean()))
    if off.mean() > 0.01: bad_frames.append((round(i / 2, 1), round(float(off.mean()) * 100, 2)))
print(json.dumps(dict(frames=len(F), mean_off_palette_pct=round(100 * float(np.mean(frac)), 3), frames_over_1pct=len(bad_frames), worst=sorted(bad_frames, key=lambda b: -b[1])[:8])))
