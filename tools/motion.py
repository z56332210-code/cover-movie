"""Frame-to-frame change (grey 480x270), pairs 1/15 s apart (the reference animates at 15 fps inside a 30 fps file),
excluding transition windows (+-0.3 s) and black frames.
usage: python3 tools/motion.py <video> [start] [dur]"""
import sys, subprocess, json
import numpy as np

def grab(path, ss, dur):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(ss), "-t", str(dur), "-i", path,
                                   "-vf", "fps=30,scale=480:270,format=gray", "-f", "rawvideo", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, 270, 480).astype(np.float32)

def motion(path, ss=0.0, dur=20.0):
    F = grab(path, ss, dur)[::2]                                     # 15 fps sampling
    d = np.abs(np.diff(F, axis=0)).mean(axis=(1, 2))
    # cut = a difference spike far above the local median (structural, after 8x8 block averaging)
    B = F[:, :264, :480].reshape(len(F), 33, 8, 60, 8).mean(axis=(2, 4))
    bd = np.abs(np.diff(B, axis=0)).mean(axis=(1, 2))
    cut = np.where(bd > 30)[0]
    keep = np.ones(len(d), bool)
    for c in cut: keep[max(0, c - 4): c + 5] = False                  # +-0.3 s around each transition
    lit = F.mean(axis=(1, 2)) > 10
    keep &= lit[:-1] & lit[1:]
    return dict(motion=round(float(d[keep].mean()), 2), frames_used=int(keep.sum()), cut_times=[round((c + 1) / 15 + ss, 2) for c in cut])

if __name__ == "__main__":
    print(json.dumps(motion(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0, float(sys.argv[3]) if len(sys.argv) > 3 else 20)))
