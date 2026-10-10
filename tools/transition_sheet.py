"""8 consecutive frames of each transition, reference vs mine, plus peak brightness on the picture strip."""
import subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
REF, MINE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
def frames(path, start, n=8, w=320, h=180):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path, "-frames:v", str(n), "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    a = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3); return [Image.fromarray(x) for x in a]
font = ImageFont.load_default(size=16)
rows = [("REF 7.20", frames(REF, 7.20)), ("MINE bleed 7.17", frames(MINE, 7.3 - 4 / 30)),
        ("REF 12.20", frames(REF, 12.20)), ("MINE bleed 12.17", frames(MINE, 12.3 - 4 / 30)),
        ("REF 17.20", frames(REF, 17.20)), ("MINE whip 16.87", frames(MINE, 17.0 - 4 / 30)),
        ("MINE black>bleed 2.27", frames(MINE, 2.4 - 4 / 30))]
img = Image.new("RGB", (8 * 324 + 150, len(rows) * 204 + 10), (20, 20, 20)); d = ImageDraw.Draw(img)
for r, (label, fr) in enumerate(rows):
    d.text((6, r * 204 + 90), label, fill=(255, 220, 0), font=font)
    for i, f in enumerate(fr):
        img.paste(f, (150 + i * 324, r * 204 + 10)); d.text((154 + i * 324, r * 204 + 12), f"f{i}", fill=(255, 255, 0), font=font)
img.save(OUT)
for label, fr in rows:
    g = [np.asarray(f.convert("L"), np.float32) for f in fr]
    strip = [x[x.mean(axis=1) > 14] for x in g]
    print(f"{label:22s} strip mean per frame:", [int(s.mean()) if len(s) else 0 for s in strip])
