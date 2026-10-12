"""Subset the video's fonts to the glyphs it uses and verify full coverage (no fallback glyphs).
  serif-jp-900.woff2   Noto Serif JP 900  (Japanese lyrics, giant glyphs, credits names; slanted in code, it has no italic)
  serif-jp-700.woff2   Noto Serif JP 700  (small lyric text)
  en-<cand>.woff2      English bold serif italic candidates for credits / labels (900 instances)
  pretendard-300.woff2 Korean subtitles
usage: python3 tools/build_fonts.py <dir with NotoSerifJP.ttf, PlayfairDisplay-Italic.ttf, BodoniModa-Italic.ttf,
                                     NotoSerifDisplay-Italic.ttf and the unpacked pretendard npm package>"""
import sys, os, json
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

src = sys.argv[1]
rows = [l.rstrip("\n").split("\t") for l in open("data/lyrics.tsv", encoding="utf-8") if l[0].isdigit()]
CRED = json.load(open("data/credits.json", encoding="utf-8"))
ASCII = "".join(chr(c) for c in range(0x20, 0x7f))
EXTRA_JA = "ベノムかいりきベアcovered by" + "".join(c["name"] for c in CRED["items"]) + CRED["title"] + CRED["subtitle"]
ja = set("".join(r[1] for r in rows) + EXTRA_JA + ASCII + "、。「」・ー～？！（）")
ko = set("".join(r[2] for r in rows) + ASCII + "…'")
en = set(ASCII)

def instance(path, **axes):
    return instancer.instantiateVariableFont(TTFont(os.path.join(src, path)), axes)

jobs = [
    (lambda: instance("NotoSerifJP.ttf", wght=900), "serif-jp-900.woff2", ja),
    (lambda: instance("NotoSerifJP.ttf", wght=700), "serif-jp-700.woff2", ja),
    (lambda: instance("PlayfairDisplay-Italic.ttf", wght=900), "en-playfair.woff2", en),
    (lambda: instance("BodoniModa-Italic.ttf", wght=900, opsz=96), "en-bodoni.woff2", en),
    (lambda: instance("NotoSerifDisplay-Italic.ttf", wght=900, wdth=100), "en-notodisplay.woff2", en),
    (lambda: TTFont(os.path.join(src, "package/dist/public/static/Pretendard-Light.otf")), "pretendard-300.woff2", ko),
]
os.makedirs("web/venom/fonts", exist_ok=True)
ok = True
for load, out, chars in jobs:
    font = load(); cmap = font.getBestCmap()
    missing = sorted(c for c in chars if c.strip() and ord(c) not in cmap)
    if missing: print(f"{out}: MISSING {''.join(missing)}"); ok = False
    opts = subset.Options(); opts.flavor = "woff2"; opts.layout_features = ["*"]
    s = subset.Subsetter(opts); s.populate(unicodes=[ord(c) for c in chars]); s.subset(font)
    font.flavor = "woff2"; font.save(os.path.join("web/venom/fonts", out))
    print(f"{out}: {len(chars)} chars, {os.path.getsize(os.path.join('web/venom/fonts', out)) // 1024} KB")
sys.exit(0 if ok else 1)
