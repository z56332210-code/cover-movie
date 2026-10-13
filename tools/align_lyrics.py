"""Align lyrics.txt lines to Whisper word timestamps (kana-level DP) -> lyrics/line_times.json"""
import json
from pathlib import Path
import numpy as np, pykakasi

ROOT = Path(__file__).resolve().parent.parent
kks = pykakasi.kakasi()
def kana(s):
    s = s.replace("IQ", "あいきゅー").replace("THE END", "じえんど").replace("My God", "まいごっど").replace("Oh my god", "おーまいごっど")
    s = s.replace("I want you", "あいうぉんちゅー").replace("I hate you", "あいへいちゅー").replace("Gott ist tot", "ごっといすとと")
    out = "".join(x["hira"] for x in kks.convert(s))
    out = out.replace("ぅ", "う").replace("ぃ", "い").replace("ゅ", "ゆ").replace("ょ", "よ").replace("ゃ", "や").replace("っ", "つ").replace("ー", "う")
    return "".join(ch for ch in out if "ぁ" <= ch <= "ゟ")

lines = (ROOT / "lyrics/lyrics.txt").read_text(encoding="utf-8").splitlines()
W = json.load(open(ROOT / "plan/whisper_words.json"))["words"]
# whisper chars with times
wc, wt = [], []
for w in W:
    k = kana(w["w"])
    for j, ch in enumerate(k):
        wc.append(ch); wt.append(w["s"] + (w["e"] - w["s"]) * j / max(1, len(k)))
lc, lid = [], []
for i, l in enumerate(lines, 1):
    for ch in kana(l):
        lc.append(ch); lid.append(i)
n, m = len(lc), len(wc)
GAP_L, GAP_W = -1.0, -0.6   # skipping whisper chars is cheap (hallucinations), skipping lyric chars a bit dearer
S = np.full((n + 1, m + 1), -1e9, np.float32); S[0, :] = 0; S[:, 0] = np.arange(n + 1) * GAP_L
B = np.zeros((n + 1, m + 1), np.int8)
for i in range(1, n + 1):
    for j in range(1, m + 1):
        a = S[i - 1, j - 1] + (2.0 if lc[i - 1] == wc[j - 1] else -1.0)
        b = S[i - 1, j] + GAP_L
        c = S[i, j - 1] + GAP_W
        if a >= b and a >= c: S[i, j], B[i, j] = a, 0
        elif b >= c: S[i, j], B[i, j] = b, 1
        else: S[i, j], B[i, j] = c, 2
i, j = n, int(np.argmax(S[n]))
match = {}
while i > 0 and j > 0:
    if B[i, j] == 0:
        if lc[i - 1] == wc[j - 1]: match[i - 1] = wt[j - 1]
        i, j = i - 1, j - 1
    elif B[i, j] == 1: i -= 1
    else: j -= 1
res = {}
for k, t in sorted(match.items()):
    li = lid[k]
    res.setdefault(li, []).append((k, t))
out = []
for li in range(1, len(lines) + 1):
    ks = [k for k in range(n) if lid[k] == li]
    got = res.get(li, [])
    if len(got) >= max(2, 0.35 * len(ks)):
        # first matched char, extrapolated back to line start (~0.11 s per char)
        k0, t0 = got[0]
        out.append([li, round(t0 - (k0 - ks[0]) * 0.11, 2), f"whisper {len(got)}/{len(ks)}"])
    else:
        out.append([li, None, f"whisper {len(got)}/{len(ks)}"])
for o in out: print(o, lines[o[0] - 1])
json.dump(out, open(ROOT / "plan/align_raw.json", "w"), ensure_ascii=False)

# per-line matched character times (kana index within the line -> time), used to time each lyric chunk
chars = {}
for k, t in sorted(match.items()):
    li = lid[k]; k0 = lid.index(li)
    chars.setdefault(li, []).append([k - k0, round(t, 3)])
json.dump(chars, open(ROOT / "plan/align_chars.json", "w"))
