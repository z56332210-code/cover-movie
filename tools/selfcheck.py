"""Self-check for a rendered range:  python3 tools/selfcheck.py renders/preview_0-20.mp4 0 20

Reports: cuts per 10 s vs target, frame-to-frame change outside cuts (480x270 gray), cut-vs-beat error (ms),
colour audit (mono + red only), and writes an 8-frame side-by-side with ref B at the same song time.
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
vid, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
FPS = 30
plan = json.load(open(ROOT / "plan/cutlist_draft.json"))
beats = np.array(json.load(open(ROOT / "plan/audio_analysis.json"))["beats"])
cuts = [c for c in plan["cuts"] if t0 <= c["start"] < t1]
JUMP = plan["audio"]["jump_sec"]
RELAX = {4, 16}
HOLD = {1, 10, 13, 17, 18}

# 1) density
rows = []
for w in np.arange(t0, t1, 10):
    cs = [c for c in cuts if w <= c["start"] < w + 10]
    span = min(10, t1 - w)
    sc = sorted({c["scene"] for c in cs})
    tgt = "1~3" if sc and set(sc) <= RELAX else ("예외(인트로/아웃트로)" if sc and set(sc) & HOLD else "7~9")
    rows.append(dict(window=f"{w:g}-{w + span:g}", cuts=len(cs), per10s=round(len(cs) / span * 10, 1), scenes=sc, target=tgt))
fast = [c for c in cuts if c["scene"] not in RELAX | HOLD]
fast_span = sum(c["dur"] for c in fast)

# 2) frame change (gray 480x270), excluding +-3 frames around cuts
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", vid, "-vf", "scale=480:270,format=gray", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, 270, 480).astype(np.float32)
diff = np.abs(np.diff(fr, axis=0)).mean((1, 2))
cut_frames = {int(round((c["start"] - t0) * FPS)) for c in plan["cuts"] if t0 <= c["start"] < t1}
mask = np.ones(len(diff), bool)
for f in cut_frames:
    mask[max(0, f - 4):f + 4] = False
d_in = diff[mask]
static = float((d_in < 0.15).mean() * 100)

# 3) beat error of cut frames
err = []
for c in cuts:
    if c["start"] <= 0:
        continue
    tf = round(c["start"] * FPS) / FPS
    err.append(abs(beats - tf).min() * 1000)

# 4) colour audit on 2 fps samples
other, red_frac = [], []
for k in range(0, len(fr), FPS // 2):
    pass
rgb = subprocess.run(["ffmpeg", "-v", "error", "-i", vid, "-vf", "fps=2,scale=480:270", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                     capture_output=True).stdout
im = np.frombuffer(rgb, np.uint8).reshape(-1, 270, 480, 3).astype(np.int16)
mx, mn = im.max(-1), im.min(-1); ch = mx - mn
r, g, b = im[..., 0], im[..., 1], im[..., 2]
col = ch > 24
redish = col & (r == mx) & (np.abs(g - b) < 0.35 * ch + 8)
oth = col & ~redish
other_pct = float(oth.mean() * 100); red_pct = float(redish.mean() * 100)
worst = float(oth.mean((1, 2)).max() * 100)

# 5) side-by-side with ref B at the same song time
times = [t0 + (t1 - t0) * (k + 0.5) / 8 for k in range(8)]
f = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Light.ttc", 18, index=1)
W, H = 480, 270
sheet = Image.new("RGB", (W * 2, (H + 26) * 8), (20, 20, 21)); dr = ImageDraw.Draw(sheet)
for k, t in enumerate(times):
    tb = t + 0.83 if t < JUMP else t + 56.70
    a = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t - t0:.3f}", "-i", vid, "-frames:v", "1", "-vf", f"scale={W}:{H}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    bb = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tb:.3f}", "-i", str(ROOT / "ref_B_video/ref_B.mp4"), "-frames:v", "1",
                         "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    y = k * (H + 26)
    dr.text((6, y + 3), f"{t:.2f}s  ours  |  ref_B {tb:.2f}s", font=f, fill=(230, 230, 230))
    sheet.paste(Image.frombytes("RGB", (W, H), a), (0, y + 26))
    if len(bb) == W * H * 3:
        sheet.paste(Image.frombytes("RGB", (W, H), bb), (W, y + 26))
out_img = Path(vid).with_name(Path(vid).stem + "_vs_refB.jpg")
sheet.save(out_img, quality=88)

rep = dict(
    density=rows, fast_zone_per10s=round(len(fast) / max(fast_span, 1e-6) * 10, 1),
    motion=dict(mean_diff=round(float(d_in.mean()), 2), min_diff=round(float(d_in.min()), 3), static_frames_pct=round(static, 1)),
    beat_err_ms=dict(mean=round(float(np.mean(err)), 1), max=round(float(np.max(err)), 1), n=len(err)),
    colour=dict(red_pct=round(red_pct, 2), other_pct=round(other_pct, 4), worst_frame_other_pct=round(worst, 3)),
    red_windows=[w for w in plan["stats"]["red_windows"] if w[0] < t1 and w[1] > t0],
    glitches=[g for g in plan["stats"]["glitches"] if t0 <= g < t1],
    nochar_cuts=sum(1 for c in cuts if not c.get("crop")), cuts=len(cuts),
    compare=str(out_img))
print(json.dumps(rep, ensure_ascii=False, indent=1))
json.dump(rep, open(Path(vid).with_name(Path(vid).stem + "_selfcheck.json"), "w"), ensure_ascii=False, indent=1)
