"""Detect visual change points in ref B, mapped to song (audio) time."""
import sys, subprocess, numpy as np, json
src, out = sys.argv[1:3]
W, H, FPS = 160, 90, 10
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-vf', f'fps={FPS},scale={W}:{H},format=gray', '-f', 'rawvideo', '-'],
                     capture_output=True).stdout
f = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
d = np.abs(np.diff(f, axis=0)).mean((1, 2))
tB = (np.arange(1, len(f)) ) / FPS
def b2a(t):
    if t < 91.63: return t - 0.83
    if t >= 147.5: return t - 56.70
    return None
pts = []
for i in range(1, len(d) - 1):
    if d[i] > 6 and d[i] >= d[i-1] and d[i] >= d[i+1]:
        a = b2a(tB[i])
        if a is not None and a >= 0: pts.append((round(a, 2), round(float(d[i]), 1)))
json.dump(pts, open(out, 'w'))
print(len(pts)); print(pts)
