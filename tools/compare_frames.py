"""Side-by-side: reference vs mine at the same timestamps (first 20 s), 8 rows."""
import sys
from PIL import Image, ImageDraw, ImageFont
ts = ["2.5", "5", "7.5", "10", "12.5", "15", "17.5", "19.9"]
font = ImageFont.load_default(size=20)
out = Image.new("RGB", (1928, 8 * 548 + 40), (20, 20, 20)); d = ImageDraw.Draw(out)
d.text((10, 10), "REFERENCE", fill=(230, 230, 230), font=font); d.text((978, 10), "MINE (--preview)", fill=(230, 230, 230), font=font)
for i, t in enumerate(ts):
    out.paste(Image.open(f"out/preview/cmp/ref_{t}.png").convert("RGB"), (0, 40 + i * 548))
    out.paste(Image.open(f"out/preview/cmp/mine_{t}.png").convert("RGB"), (968, 40 + i * 548))
    d.text((8, 44 + i * 548), f"{t}s", fill=(255, 220, 0), font=font); d.text((976, 44 + i * 548), f"{t}s", fill=(255, 220, 0), font=font)
out.save(sys.argv[1])
