"""Colour audit: every pixel must be neutral (mono) or red-hued. Prints fractions per image."""
import sys, numpy as np
from PIL import Image
for p in sys.argv[1:]:
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.int16)
    mx, mn = a.max(-1), a.min(-1); chroma = mx - mn
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    colored = chroma > 24
    redish = colored & (r == mx) & (np.abs(g - b) < 0.35 * chroma + 8)
    other = colored & ~redish
    print(f"{p}: mono {100 * (~colored).mean():.2f}%  red {100 * redish.mean():.2f}%  OTHER {100 * other.mean():.3f}%")
