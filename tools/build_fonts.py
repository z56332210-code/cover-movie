"""Subset thin display/UI/subtitle fonts to the glyphs the video uses and verify full coverage.
usage: python3 tools/build_fonts.py <dir with NotoSerifJP[wght].ttf, Inter[opsz,wght].ttf, pretendard package>"""
import sys, os, io
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

src = sys.argv[1]
rows = [l.rstrip("\n").split("\t") for l in open("data/lyrics.tsv", encoding="utf-8") if l[0].isdigit()]
EXTRA_JA = "スロウダウナー作詞・作曲ろくろ暁山瑞希"
ASCII = "".join(chr(c) for c in range(0x20, 0x7f))
ja = set("".join(r[1] for r in rows) + EXTRA_JA + ASCII + "、。「」・ー")
ko = set("".join(r[2] for r in rows) + ASCII + "…")
ui = set(ASCII)

def instance(path, **axes):
    f = TTFont(os.path.join(src, path)); return instancer.instantiateVariableFont(f, axes)

jobs = [
    (lambda: instance("NotoSerifJP.ttf", wght=200), "serif-200.woff2", ja),
    (lambda: instance("NotoSerifJP.ttf", wght=300), "serif-300.woff2", ja),
    (lambda: instance("NotoSerifJP.ttf", wght=400), "serif-400.woff2", ja),
    (lambda: instance("Inter.ttf", wght=300, opsz=32), "inter-300.woff2", ui),
    (lambda: TTFont(os.path.join(src, "package/dist/public/static/Pretendard-Light.otf")), "pretendard-300.woff2", ko),
]
for f in os.listdir("web/fonts"):
    if f.endswith(".woff2"): os.remove(os.path.join("web/fonts", f))
ok = True
for load, out, chars in jobs:
    font = load(); cmap = font.getBestCmap()
    missing = sorted(c for c in chars if c.strip() and ord(c) not in cmap)
    if missing: print(f"{out}: MISSING {''.join(missing)}"); ok = False
    opts = subset.Options(); opts.flavor = "woff2"; opts.layout_features = ["*"]
    s = subset.Subsetter(opts); s.populate(unicodes=[ord(c) for c in chars]); s.subset(font)
    font.flavor = "woff2"; font.save(os.path.join("web/fonts", out))
    print(f"{out}: {len(chars)} chars, {os.path.getsize(os.path.join('web/fonts', out)) // 1024} KB")
sys.exit(0 if ok else 1)
