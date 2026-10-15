"""Grade the prop drawings (art/props_src) to the film's palette: navy/grey/white -> monochrome, magenta -> red.

    python3 tools/props_grade.py      -> art/props/<name>.png (trimmed, straight alpha)
"""
import glob
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
INK, PAPER_L, RED = np.array((10, 10, 11)), np.array((236, 235, 235)), np.array((192, 22, 31))

for f in sorted(glob.glob(str(ROOT / "art/props_src/*.png"))):
    im = np.asarray(Image.open(f).convert("RGBA")).astype(np.float32)
    rgb, a = im[..., :3], im[..., 3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    u = np.clip((lum - 40) / (225 - 40), 0, 1)[..., None]
    out = INK + (PAPER_L - INK) * u                               # navy -> ink, grey card stays mid grey, white -> paper
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mag = (r > 150) & (b > 150) & (g < 120)                        # magenta lamp -> the film's red
    out[mag] = RED
    a = np.clip((a - 60) / 140, 0, 1) * 255                        # drop the faint ghost smudges around the drawings
    res = Image.fromarray(np.dstack([out, a]).astype(np.uint8), "RGBA")
    res = res.crop(res.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox())
    res.save(ROOT / "art/props" / Path(f).name)
    print(Path(f).stem, res.size, int(mag.sum()))
