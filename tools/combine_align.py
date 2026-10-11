"""Pick, per lyric line, the best of the per-pass alignments (out/align_<pass>.json from tools/align_whisper.py),
apply manual fixes, spread characters that Whisper bunched onto one time, rebuild display windows -> data/lyrics_timed.json.
Passes: full = whole mix, sec = mix per section, vfull = separated vocals whole, vsec = separated vocals per section."""
import json
import numpy as np

P = {k: json.load(open(f"out/align_{k}.json", encoding="utf-8")) for k in ("full", "sec", "vfull", "vsec")}
A = json.load(open("data/analysis.json"))
# chosen pass per line (all passes agree within ~0.1 s where more than one has full coverage)
PICK = {**{i: "vsec" for i in range(1, 6)}, **{i: "sec" for i in range(6, 11)}, **{i: "vsec" for i in range(11, 22)},
        22: "full", 23: "full", **{i: "vsec" for i in range(24, 34)}}
# MANUAL per-char times (index into the line string -> seconds)
#  line 6: Whisper put あー into the instrumental gap (19.9 s); separated-vocal onset is 26.57 s
#  lines 22-23: low recognition everywhere; times read from the whole-mix pass words (もう 86.56, 一度=悪性, ドクドク=届く毒,
#  回るルルル, 障害なんねぇ, 解体の=痛い痛いの, シクシク=SICK SICK); backing (哀でもっと) not heard by Whisper, placed at the line tail
MANUAL_START = {}
MANUAL_CHARS = {
    # line 6 from the separated-vocal whole pass (検体も毒だ 僕らの人生 = 倦怠モード「苦」だ僕らの人生), onset 26.57
    6: [26.57, 26.63, 26.70, 27.10, 27.26, 27.33, 27.40, 27.53, 27.53, 27.53, 27.66, 28.22, 28.44, 28.60, 28.80, 29.04],
    22: [86.56, 86.78, 87.00, 87.28, 87.40, 87.86, 87.94, 88.14, 88.32, 88.64, 89.06, 89.20, 89.28, 89.30, 89.34, 89.38, 89.42, 89.44],
    23: [89.46, 90.24, 90.62, 91.04, 91.22, 91.42, 91.60, 91.75, 91.90, 92.16, 92.32, 92.32, 92.40, 92.48, 92.56, 92.66, 92.66, 92.78, 92.90, 93.00],
}
# 愛/哀 call-and-response lines: one syllable per beat, main then chorus echo (confirmed by ear by the user for line 25:
# "愛 once, chorus once, x4") and by separated-vocal onsets on every beat. Brackets share the time of the echo they wrap.
BT = np.array(A["beats"])
def on_beats(t0, text):
    b = BT[np.argmin(np.abs(BT - t0)):]; k = -1; out_ = []; inside = False
    for ch in text:
        if ch == "（": inside = True; k += 1; out_.append(float(b[k])); continue
        if ch == "）": inside = False; out_.append(float(b[k])); continue
        if not inside: k += 1
        out_.append(float(b[k]))
    return [round(x, 3) for x in out_]
# bridge: the whole-mix pass ran ~0.6-0.7 s late; user heard line 22 at ~85.9 s and line 23 at ~88.9 s,
# matching separated-vocal onsets at 85.86 s and 88.86 s -> shift both lines as a whole
MANUAL_CHARS[22] = [round(t - 0.70, 3) for t in MANUAL_CHARS[22]]
MANUAL_CHARS[23] = [round(t - 0.60, 3) for t in MANUAL_CHARS[23]]
MANUAL_CHARS[19] = on_beats(64.93, "愛（愛）哀（哀）")
MANUAL_CHARS[25] = on_beats(96.12, "愛（愛）哀（哀）愛（愛）哀（哀）")
MANUAL_CHARS[29] = on_beats(109.15, "愛（愛）哀（哀）")
LOW = {}
out = []
for i in range(1, 34):
    o = dict(P[PICK[i]][i - 1]); o["pass"] = PICK[i]
    if i in MANUAL_CHARS:
        assert len(MANUAL_CHARS[i]) == len(o["ja"]), (i, len(o["ja"]), o["ja"])
        o["chars"] = MANUAL_CHARS[i]; o["start"] = MANUAL_CHARS[i][0]; o["fix"] = "manual chars"
    if i in MANUAL_START:
        s0 = MANUAL_START[i]; c = np.array(o["chars"]); span_end = c[-1]
        o["chars"] = list(np.round(s0 + (c - c[0]) * (span_end - s0) / max(1e-3, span_end - c[0]), 3)) if c[0] < s0 else o["chars"]
        o["start"] = s0; o["fix"] = "manual start"
    out.append(o)

# last chorus repeats chorus 1 exactly 28 bars later (vocal onset cross-correlation: 44.218 s, r=0.81; 28 bars = 44.211 s).
# Pairs (chorus1 line, last-chorus line, char offset in chorus1 line, rule): take the better-recognised line, or average both.
SHIFT = 28 * 240 / 152
PAIRS = [(16, 26, 3, "a"), (17, 27, 0, "a"), (18, 28, 0, "a"), (20, 30, 0, "a")]
byid = {o["id"]: o for o in out}
for a, b, off, rule in PAIRS:
    A_, B_ = byid[a], byid[b]
    ca = np.array(A_["chars"][off:off + len(B_["chars"])]); cb = np.array(B_["chars"])
    assert A_["ja"][off:] == B_["ja"], (A_["ja"], B_["ja"])
    if rule == "avg": m = (ca + cb - SHIFT) / 2
    elif rule == "a": m = ca
    else: m = cb - SHIFT
    m = np.maximum.accumulate(m)
    A_["chars"][off:] = list(np.round(m, 3)); B_["chars"] = list(np.round(m + SHIFT, 3))
    A_["paired"] = B_["paired"] = f"{a}<->{b} ({'avg' if rule == 'avg' else 'from ' + str(a if rule == 'a' else b)})"

# line 24 sings line 18's melody exactly 20 bars later (vocal onset cross-correlation r=0.79 at 31.578 s; 20 bars = 31.579 s).
# Same morae: 存在|抹消=感血|毒=ドク|ドク|消える=零る|ルル|（無いの ずっと）=（無いの？もっと）. Index map 24 -> 18:
M24 = [0, 1, 2, 3, 4, 6, 7, 8, None, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20]
c18 = byid[18]["chars"]; s20 = 20 * 240 / 152
c24 = [None if m is None else round(c18[m] + s20, 3) for m in M24]
c24[8] = round((c24[7] + c24[9]) / 2, 3)
byid[24]["chars"] = c24; byid[24]["paired"] = "18->24 (from 18, +20 bars)"

# spread bunched characters: >=3 visible chars within 40 ms -> even spread up to the next distinct time
def visible(ch): return not ch in "（）()「」？?。、 ～ー" or ch == "ー"
for o in out:
    c = list(o["chars"]); n = len(c); fixed = []
    k = 0
    while k < n:
        j = k
        while j + 1 < n and c[j + 1] - c[k] < 0.04: j += 1
        run = [m for m in range(k, j + 1) if visible(o["ja"][m])]
        if len(run) >= 3:
            nxt = next((c[m] for m in range(j + 1, n) if c[m] - c[k] >= 0.04), None)
            if nxt is None: nxt = c[k] + 0.12 * (j - k + 1)
            for q, m in enumerate(range(k, j + 1)): c[m] = round(c[k] + (nxt - c[k]) * q / (j - k + 1), 3)
            fixed.append(o["ja"][k:j + 1])
        k = j + 1
    o["chars"] = c
    if fixed: o["spread"] = fixed

for k, o in enumerate(out[:-1]):
    lim = out[k + 1]["chars"][0] - 0.05; c = o["chars"]
    if max(c) > lim and "（" in o["ja"]:
        p0 = o["ja"].index("（"); a0 = c[p0]; hi = max(c[p0:])
        if a0 < lim:
            o["chars"] = c[:p0] + [round(a0 + (x - a0) * (lim - a0) / max(1e-3, hi - a0), 3) for x in c[p0:]]

# display windows: start = first char, end = next line start - 0.05 (bridge gaps < 0.8 s), else +0.4 s tail
starts = [o["chars"][0] for o in out]
vocal_end = {5: 21.4, 15: 52.7, 21: 67.9, 33: 116.2}          # separated-vocal activity ends before instrumental gaps
for k, o in enumerate(out):
    o["start"] = round(starts[k], 2)
    nxt = starts[k + 1] if k + 1 < len(out) else A["duration"]
    last = max(o["chars"])
    end = vocal_end.get(o["id"], last + 0.4)
    o["end"] = round(nxt - 0.05 if nxt - end < 0.8 else min(end + 0.4, nxt - 0.05), 2)
    o["low"] = (o["cover"] < 0.75 and not o.get("paired", "").endswith(")") or o["id"] in (22, 23)) and not ("from" in o.get("paired", "") and not o.get("paired", "").endswith(f"from {o['id']})"))
for o in out:
    if o["id"] in (19, 25, 29): o["low"] = False; o["fix"] = "on beats (user-confirmed pattern)"
    if o["id"] in (22, 23): o["low"] = False; o["fix"] = "manual chars, start confirmed by ear"
json.dump(out, open("data/lyrics_timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for o in out:
    print(f'{o["id"]:2d} {o["start"]:7.2f}-{o["end"]:7.2f} {o["pass"]:5s} cov {o["cover"]:.2f} {"LOW " if o["low"] else ""}{o.get("fix","")} {o.get("paired","")} {o.get("spread","")} {o["ja"]}')
