"""Align the user's lyric lines to Whisper word timestamps (character-level sequence matching).
Whisper text is only a timing source; displayed text always comes from data/lyrics.tsv."""
import json, difflib, unicodedata
import numpy as np

words = json.load(open("data/whisper_words.json", encoding="utf-8"))
rows = [l.rstrip("\n").split("\t") for l in open("data/lyrics.tsv", encoding="utf-8") if l[0].isdigit()]
sections = json.load(open("data/sections.json"))

def norm_char(c):
    c = unicodedata.normalize("NFKC", c).lower()
    o = ord(c)
    if 0x30A1 <= o <= 0x30F6: c = chr(o - 0x60)  # katakana -> hiragana
    return c

def keep(c):
    return c.isalnum() or "぀" <= c <= "ヿ" or "一" <= c <= "鿿"

# whisper char stream with per-char times (linear inside each word)
wc, wt = [], []
for w in words:
    cs = [c for c in w["w"] if keep(c)]
    for i, c in enumerate(cs):
        wc.append(norm_char(c))
        wt.append((w["s"] + (w["e"] - w["s"]) * i / len(cs), w["s"] + (w["e"] - w["s"]) * (i + 1) / len(cs)))

# lyric char stream, remembering the line of each char
lc, li = [], []
for k, r in enumerate(rows):
    for c in r[1]:
        if keep(c): lc.append(norm_char(c)); li.append(k)

sm = difflib.SequenceMatcher(None, lc, wc, autojunk=False)
hits = {k: [] for k in range(len(rows))}
for a, b, n in sm.get_matching_blocks():
    for j in range(n):
        hits[li[a + j]].append((a + j, wt[b + j]))

n_chars = [sum(1 for x in li if x == k) for k in range(len(rows))]
out = []
for k, r in enumerate(rows):
    h = hits[k]
    cover = len(h) / max(1, n_chars[k])
    if h:
        first_idx = min(x[0] for x in h); last_idx = max(x[0] for x in h)
        line_first = li.index(k); line_last = line_first + n_chars[k] - 1
        s = min(x[1][0] for x in h); e = max(x[1][1] for x in h)
        # extrapolate unmatched head/tail chars at ~0.17 s/char
        s -= (first_idx - line_first) * 0.17; e += (line_last - last_idx) * 0.17
    else:
        s = e = None
    out.append(dict(id=int(r[0]), ja=r[1], ko=r[2], start=s, end=e, cover=round(cover, 2)))

# unmatched lines: interpolate between neighbours
for k, o in enumerate(out):
    if o["start"] is None or o["cover"] < 0.3:
        prev_e = next((out[j]["end"] for j in range(k - 1, -1, -1) if out[j]["start"] is not None and out[j]["cover"] >= 0.3), 0)
        nxt_s = next((out[j]["start"] for j in range(k + 1, len(out)) if out[j]["start"] is not None and out[j]["cover"] >= 0.3), prev_e + 3)
        o["start"], o["end"], o["flag"] = prev_e + 0.1, nxt_s - 0.1, "interpolated"

# snap starts to the measured 16th-note grid when Whisper is close to it
A = json.load(open("data/analysis.json")); bt = np.array(A["beats"])
grid = np.sort(np.concatenate([bt] + [bt[:-1] + (bt[1:] - bt[:-1]) * q for q in (0.25, 0.5, 0.75)]))
for o in out:
    g = grid[np.argmin(np.abs(grid - o["start"]))]
    if abs(g - o["start"]) < 0.12: o["start"] = float(g)
    o["start"] = max(0.0, o["start"])

# display windows: no overlap, min 0.4 s, hold short gaps
for k, o in enumerate(out):
    nxt = out[k + 1]["start"] if k + 1 < len(out) else 143.0
    if o["end"] > nxt - 0.05: o["end"] = nxt - 0.05
    if nxt - o["end"] < 0.8: o["end"] = nxt - 0.05          # bridge tiny gaps so subtitles don't flicker
    else: o["end"] = min(o["end"] + 0.4, nxt - 0.05)        # short tail hold
    if o["end"] - o["start"] < 0.4: o["flag"] = "short"
    for sec in sections:
        if sec["start"] - 1.0 <= o["start"] < sec["end"]: o["section"] = sec["name"]
    o["start"], o["end"] = round(o["start"], 2), round(o["end"], 2)

# per-character sung time (matched chars from Whisper, the rest interpolated) for karaoke-synced reveals
ctime = {}
for k in range(len(rows)):
    for idx, (s0, _) in hits[k]: ctime[idx] = s0
pos = 0
for k, (r, o) in enumerate(zip(rows, out)):
    ts = []
    for c in r[1]:
        if keep(c):
            ts.append(ctime.get(pos)); pos += 1
        else:
            ts.append(None)
    known = [(i, x) for i, x in enumerate(ts) if x is not None and o["start"] - 0.3 <= x <= o["end"]]
    if len(known) < 2:
        known = [(0, o["start"]), (len(ts) - 1, max(o["start"], o["end"] - 0.4))]
    xi = np.array([i for i, _ in known], float); xt = np.array([x for _, x in known])
    full = np.interp(np.arange(len(ts)), xi, xt)
    full = np.maximum.accumulate(np.clip(full, o["start"], max(o["start"], o["end"] - 0.25)))
    o["chars"] = [round(float(x), 3) for x in full]

json.dump(out, open("data/lyrics_timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for o in out:
    print(f'{o["id"]:2d} {o.get("section","?"):8s} {o["start"]:7.2f}-{o["end"]:7.2f} cov {o["cover"]:.2f} {o.get("flag","")} {o["ja"]}')
