"""Subset the display/subtitle fonts to exactly the glyphs the video uses and verify full coverage.
usage: python3 tools/build_fonts.py <dir with source .ttf/.otf>"""
import sys, os
from fontTools import subset
from fontTools.ttLib import TTFont

src = sys.argv[1]
rows = [l.rstrip("\n").split("\t") for l in open("data/lyrics.tsv", encoding="utf-8") if l[0].isdigit()]
EXTRA_JA = "スロウダウナー作詞・作曲ろくろVocal暁山瑞希Moviemeel"     # title card + credits
ASCII = "".join(chr(c) for c in range(0x20, 0x7f))
ja = set("".join(r[1] for r in rows) + EXTRA_JA + ASCII + "、。「」・ー")
ko = set("".join(r[2] for r in rows) + ASCII + "…")

jobs = [
    ("ShipporiMinchoB1-Regular.ttf", "mincho-400.woff2", ja),
    ("ShipporiMinchoB1-Bold.ttf", "mincho-700.woff2", ja),
    ("ShipporiMinchoB1-ExtraBold.ttf", "mincho-800.woff2", ja),
    ("DelaGothicOne-Regular.ttf", "dela.woff2", ja),
    ("package/dist/public/static/Pretendard-SemiBold.otf", "pretendard-600.woff2", ko),
]
ok = True
for f, out, chars in jobs:
    font = TTFont(os.path.join(src, f))
    cmap = font.getBestCmap()
    missing = sorted(c for c in chars if c.strip() and ord(c) not in cmap)
    if missing:
        print(f"{f}: MISSING {''.join(missing)}"); ok = ok and f.startswith("Dela")  # Dela is accent-only
    opts = subset.Options(); opts.flavor = "woff2"; opts.layout_features = ["*"]
    s = subset.Subsetter(opts); s.populate(unicodes=[ord(c) for c in chars]); s.subset(font)
    font.flavor = "woff2"; font.save(os.path.join("web/fonts", out))
    print(f"{out}: {len(chars)} chars, {os.path.getsize(os.path.join('web/fonts', out)) // 1024} KB")
sys.exit(0 if ok else 1)
