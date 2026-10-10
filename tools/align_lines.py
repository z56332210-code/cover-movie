"""Draft lyric timing without an ASR model.
Sections (measured from audio) get their lyric block; inside a section, line boundaries start at
syllable-weighted positions and snap to the deepest vocal dip near the expected point, then to the 16th grid."""
import json, re, numpy as np
A = json.load(open("data/analysis.json"))
t, v = np.load("data/vocal_curve.npy")
beats = np.array(A["beats"]); db = np.array(A["downbeats"])
rows = [l.rstrip("\n").split("\t") for l in open("data/lyrics.tsv", encoding="utf-8") if l[0].isdigit()]
pron = [l.strip() for l in open("data/pron.txt", encoding="utf-8")]
syl = [len(re.sub(r"[^가-힣]", "", p)) for p in pron]

def bar(i): return float(db[i])
# section blocks: (name, start, end, first line id, last line id)
SECTIONS = json.load(open("data/sections.json"))
grid = np.sort(np.concatenate([beats, (beats[:-1] + beats[1:]) / 2, beats[:-1] * 0.75 + beats[1:] * 0.25, beats[:-1] * 0.25 + beats[1:] * 0.75]))
vs = np.convolve(v, np.ones(9) / 9, mode="same")
def vocal_at(a, b): return vs[(t >= a) & (t < b)]

out = []
for sec in SECTIONS:
    if not sec.get("lines"): continue
    a, b = sec["start"], sec["end"]; ids = list(range(sec["lines"][0], sec["lines"][1] + 1))
    # sung span = first/last time vocal is above threshold inside section
    w = np.array([syl[i - 1] for i in ids], float)
    cum = np.concatenate([[0], np.cumsum(w)]) / w.sum()
    starts = [a]
    beat = np.median(np.diff(beats))
    for c in cum[1:-1]:
        exp = a + c * (b - a)
        lo, hi = exp - 1.2 * beat, exp + 1.2 * beat
        m = (t >= lo) & (t <= hi)
        k = np.argmin(vs[m] + 0.15 * np.abs(t[m] - exp) / beat)  # dip, mildly biased to expected point
        tb = t[m][k]
        tb = grid[np.argmin(np.abs(grid - tb))]
        starts.append(max(tb, starts[-1] + 0.6))
    starts.append(b)
    for j, i in enumerate(ids):
        s, e = starts[j], starts[j + 1]
        out.append(dict(id=i, section=sec["name"], start=round(s, 2), end=round(e - 0.05, 2), ja=rows[i - 1][1], ko=rows[i - 1][2]))
json.dump(out, open("data/lyrics_timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for o in out: print(f'{o["id"]:2d} {o["section"]:8s} {o["start"]:7.2f}-{o["end"]:7.2f} ({o["end"]-o["start"]:4.2f}s) {o["ja"]}')
