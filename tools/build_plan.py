"""Scene plan for our song -> data/plan.json.
Shot section/type/lyric method follow the reference scene_plan.json; lengths are placed on OUR bar grid (152 BPM, bar = 1.579 s)
or on lyric character times (cuts that land on a sung word, as in the reference). Every cut is moved 2 frames early
(the reference cuts lead the beat by ~70 ms).
usage: python3 tools/build_plan.py"""
import json
import numpy as np

A = json.load(open("data/analysis.json"))
L = {o["id"]: o for o in json.load(open("data/lyrics_timed.json", encoding="utf-8"))}
DB0, BAR = A["downbeats"][0], 240 / 152
LEAD = 2 / 30
END = round(A["duration"], 3)

def bar(b): return DB0 + b * BAR - LEAD                      # cut time for bar b (bar 0 = first downbeat)
def ln(i, k=0): return L[i]["chars"][k] - LEAD                 # cut on the k-th character of lyric line i
LYR15_END = L[15]["end"] + 0.05
def beat(n): return DB0 + n * BAR / 4 - LEAD

# (t0, type, framing, lyric method, transition into this shot, section, lyric lines shown, ref shot it copies, note)
# types A colour / B mono manga / C silhouette / D magenta-solid, navy or black / E grey + motion blur
# methods 1 navy box / 1b small white horizontal / 2 vertical + black bars / 2b small white vertical / 3 diagonal band along prop /
#         4 giant cut glyphs / 5 small text in ink-blot centre / 6 magenta bold slanted / credit / title / small (tiny text on D)
# RULES (user, after the full preview): every lyric line appears once, in one representation; a cut or transition only at a
# line boundary (line start) or inside an instrumental gap; at most two lyric representations per scene (shot group).
# Ink spreads inside a shot during its last 0.5 s ("ink_out") and the cut that follows lands on the next line's start.
S = [
 (0.0,              "D", "black",       "-",      "start",         "intro",   [],          0,  "black (pickup bar, near silence)"),
 (1.30,             "D", "magenta",     "-",      "flash_magenta", "intro",   [],          1,  "magenta flash 0.4 s into the first downbeat"),
 (bar(0),           "C", "keyvisual",   "title",  "cut",           "intro",   [],          2,  "key visual silhouette + props, title logo, glitch strips"),
 (ln(1) - 0.40,     "D", "black",       "-",      "black",         "intro",   [],          3,  "black gap before the first line"),
 (ln(1),            "A", "prop_close",  "1b",     "cut",           "verse1",  [1, 2],      4,  "props close-up, ink + halftone, fast pan decelerating"),
 (ln(3),            "A", "prop_band",   "3",      "flash_magenta", "verse1",  [3, 4],      5,  "one long prop across the frame, band along the blade"),
 (ln(5),            "A", "char_close",  "1",      "cut",           "verse1",  [5],         7,  "character close-up, navy box"),
 (bar(12) + 1.10,   "D", "black",       "-",      "glitch",        "verse1",  [],          8,  "(instrumental) RGB-slice glitch then short black"),
 (bar(13),          "C", "keyvisual",   "-",      "cut",           "verse1",  [],          9,  "(instrumental) key visual silhouette, frequent glitch strips"),
 (ln(6) - 0.40,     "D", "black",       "-",      "black",         "verse1",  [],          36, "black gap before line 6"),
 (ln(6),            "B", "prop_manga",  "3",      "cut",           "verse1",  [6],         37, "mono manga props, band along the blade"),
 (ln(7),            "B", "prop_manga",  "4",      "text",          "verse1",  [7],         38, "same shot: giant black glyph rows"),
 (ln(8),            "B", "char_manga",  "2",      "cut",           "verse1",  [8],         40, "mono character, vertical text on black bars"),
 (ln(9),            "B", "char_manga",  "4",      "text",          "verse1",  [9],         40, "same shot: giant black rows"),
 (ln(10),           "B", "char_manga",  "2",      "text",          "verse1",  [10],        40, "same shot: vertical bars again (max 2 representations per scene)"),
 (ln(11),           "A", "ink_centre",  "5",      "flash_magenta", "pre",     [11],        17, "lavender + magenta ink blot, small text in its centre"),
 (ln(12),           "C", "bust_ink",    "2b",     "cut",           "pre",     [12],        18, "silhouette bust in ink; ink spreads over it in the last 0.5 s"),
 (ln(13),           "C", "keyvisual",   "1b",     "ink_wipe",      "pre",     [13],        21, "key visual, small white text"),
 (ln(14),           "C", "keyvisual",   "6",      "text",          "pre",     [14],        22, "same shot: big slanted line 14"),
 (ln(15),           "D", "magenta",     "small",  "flash_magenta", "pre",     [15],        23, "magenta solid, tiny 'さよなラ。'"),
 (LYR15_END,        "D", "navy",        "-",      "cut",           "pre",     [],          24, "(gap) navy solid"),
 (LYR15_END + 0.40, "D", "black_inset", "-",      "black",         "pre",     [],          25, "(gap) black, manga panel flickers in, magenta ink eats it"),
 (ln(16),           "A", "char_wide",   "4",      "cut",           "chorus1", [16],        27, "character + giant highlight words (あらま 求愛性 孤独 ドク 流るルル)"),
 (ln(17),           "A", "ink_centre",  "5",      "cut",           "chorus1", [17],        28, "ink blot centre text; ink spreads in the last 0.5 s"),
 (ln(18),           "A", "prop_ink",    "4",      "ink_wipe",      "chorus1", [18],        29, "props in ink + giant 存在感 / 血 / ドクドク / 零るルル"),
 (ln(19),           "A", "char_wide",   "6",      "cut",           "chorus1", [19],        33, "magenta slanted 愛/哀 with navy echo (giant would repeat line 18's method)"),
 (ln(20),           "A", "char_wide",   "2",      "text",          "chorus1", [20],        33, "same shot: vertical bars '叫べベベノム'"),
 (ln(21),           "A", "char_close",  "4",      "cut",           "chorus1", [21],        34, "close-up, navy 'メッ'"),
 (L[21]["end"] + 0.02, "C", "body_credits", "credit", "cut",          "interlude", [],        54, "(instrumental) full-body navy silhouette, credits in thin Mincho inside it (user)"),
 (ln(22),           "E", "backlit",     "thin",   "cut",           "bridge",  [22],        55, "(user) monochrome, backlit character, weak handheld, thin Mincho one glyph at a time, film texture"),
 (ln(23),           "D", "black_text",  "emph",   "cut",           "bridge",  [23],        55, "(user) black background, text only for emphasis, film texture until line 24"),
 (ln(24),           "A", "char_wide",   "4",      "cut",           "chorus_last", [24],    56, "giant 存在 / 抹消 / 毒ドク / 消えるルル, pills denser"),
 (ln(25),           "A", "char_wide",   "6",      "text",          "chorus_last", [25],    56, "same shot: magenta slanted 愛/哀 x4"),
 (ln(26),           "A", "char_tight",  "4",      "grey_blur",     "chorus_last", [26],    58, "white whip into a tighter crop + giant 求愛性 孤独 ドク 流るルル"),
 (ln(27),           "A", "ink_centre",  "5",      "cut",           "chorus_last", [27],    59, "ink blot centre text; ink spreads in the last 0.5 s"),
 (ln(28),           "A", "prop_ink",    "4",      "ink_wipe",      "chorus_last", [28],    61, "props in ink + giant 存在感 / 血 / ドクドク / 零るルル"),
 (ln(29),           "A", "char_wide",   "6",      "cut",           "chorus_last", [29],    63, "magenta slanted 愛/哀 with navy echo"),
 (ln(30),           "A", "char_close",  "2",      "cut",           "chorus_last", [30],    64, "close crop, vertical bars '叫べベベノム'"),
 (ln(31),           "A", "char_close",  "6",      "text",          "chorus_last", [31],    64, "same shot: magenta slanted"),
 (ln(32),           "A", "char_close",  "2",      "text",          "chorus_last", [32],    64, "same shot: vertical bars"),
 (ln(33),           "A", "face_close",  "4",      "cut",           "outro",   [33],        65, "face close-up (the only one): navy 'メッ'"),
 (bar(72) + BAR / 2,"A", "face_close",  "title",  "text",          "outro",   [],          65, "(instrumental) same shot: title logo"),
 (123.60,           "D", "black",       "-",      "ink_wipe_black","end",     [],          66, "black to end"),
]

ref = json.load(open("scene_plan.json"))["shots"]
# the picture animates on 15 fps steps (like the reference), so every cut sits on the 15 fps grid
S = [(np.floor(e[0] * 15 + 1e-6) / 15,) + tuple(e[1:]) for e in S]
shots = []
for i, (t0, ty, fr, m, tr, sec, lines, ri, note) in enumerate(S):
    t1 = S[i + 1][0] if i + 1 < len(S) else END
    shots.append(dict(i=i, t0=round(t0, 3), t1=round(t1, 3), dur=round(t1 - t0, 3), bars=round((t1 - t0) / BAR, 2),
                      start_bar=round((t0 + LEAD - DB0) / BAR, 2), type=ty, framing=fr, method=m, trans_in=tr, section=sec,
                      lines=lines, ref_shot=ri, ref_t0=ref[ri]["t0"], note=note))
assert all(s["dur"] > 0.1 for s in shots), [(s["i"], s["dur"]) for s in shots if s["dur"] <= 0.1]

for k, sh in enumerate(shots):
    nx = shots[k + 1] if k + 1 < len(shots) else None
    sh["ink_out"] = None
    if nx and nx["trans_in"] in ("ink_wipe", "ink_wipe_black"):
        sh["ink_out"] = "black" if nx["trans_in"] == "ink_wipe_black" else "magenta"
        # the ink belongs to the picture group that ends here (text events of the same picture carry it too)
# camera from the reference measurements: verse/B close-ups fast after the cut then decelerate, chorus/silhouette/credits near-static
CAM = {"backlit": "handheld", "prop_close": "fast_decel", "prop_band": "fast_decel", "char_close": "fast_decel", "prop_manga": "fast_decel",
       "char_manga": "slow_push", "grey_blur": "drift", "face_close": "slow_push", "char_tight": "pan_mid"}
for s in shots: s["camera"] = CAM.get(s["framing"], "static")

# pills per frame (rises toward the end; to be checked against the reference count once the counter exists)
PILLS = {"intro": 3, "verse1": 4, "pre": 5, "chorus1": 8, "interlude": 8, "bridge": 0, "chorus_last": 30, "outro": 20, "end": 0}
for s in shots: s["pills"] = 0 if s["type"] in ("D", "B", "E") else PILLS[s["section"]]
# film texture (user): from the bridge's first line up to line 24 (存在抹消)
FILM = (L[22]["start"] - 0.1, L[24]["start"] - LEAD)
for s in shots: s["film"] = bool(s["t0"] < FILM[1] and s["t1"] > FILM[0])

json.dump(dict(bar_s=BAR, first_downbeat=DB0, cut_lead_s=LEAD, duration=END, film=[round(FILM[0], 3), round(FILM[1], 3)], shots=shots), open("data/plan.json", "w"), ensure_ascii=False, indent=1)

# --- checks
real = [s for s in shots if s["trans_in"] != "text" and not (s["trans_in"] == "ink_wipe" and s["i"] > 0 and shots[s["i"] - 1]["framing"] == s["framing"])]   # text events / overlays are not cuts
tot = END
share = {k: sum(s["dur"] for s in shots if s["type"] == k) / tot for k in "ABCDE"}
print("type share:", {k: round(v, 3) for k, v in share.items()}, " ref:", ref and json.load(open("scene_plan.json"))["measured"]["type_share"])
seq_t = [(s["type"], s["framing"]) for s in real]
print("same type+framing back to back:", [(real[i]["i"], seq_t[i]) for i in range(1, len(seq_t)) if seq_t[i] == seq_t[i - 1]])
tr = [s["trans_in"] for s in shots if s["trans_in"] not in ("cut", "text", "start", "hold")]
print("same transition back to back:", [tr[i] for i in range(1, len(tr)) if tr[i] == tr[i - 1]])
overlay = {s["i"] for s in shots if s["trans_in"] == "ink_wipe" and s["i"] > 0 and shots[s["i"] - 1]["framing"] == s["framing"]}
ms = [s["method"] for s in shots if s["method"] not in ("-", "small") and s["i"] not in overlay]
print("same lyric method back to back:", [(i, ms[i]) for i in range(1, len(ms)) if ms[i] == ms[i - 1]])
# a cut / transition strictly inside a lyric line (tolerance 0.15 s around line boundaries)
mid = []
for sh in shots[1:]:
    if sh["trans_in"] in ("text", "hold"): continue
    for l in L.values():
        if l["start"] + 0.15 < sh["t0"] < l["end"] - 0.15: mid.append((sh["i"], sh["t0"], l["id"]))
print("cuts/transitions inside a lyric line:", mid)
seen = {}
for sh in shots:
    for i in sh["lines"]: seen.setdefault(i, set()).add(sh["method"])
print("lines with more than one representation:", {k: v for k, v in seen.items() if len(v) > 1}, " lines never shown:", sorted(set(L) - set(seen)))
grp = {}
for sh in shots:
    g = grp.setdefault(sh["i"] if sh["trans_in"] not in ("text", "hold") else max(grp), set())
    if sh["lines"] and sh["method"] not in ("-",): g.add(sh["method"])
print("scenes with more than 2 lyric representations:", {k: v for k, v in grp.items() if len(v) > 2})
st = np.array([s["t0"] for s in real[1:]])
print("cuts per 20 s:", [int(((st >= a) & (st < a + 20)).sum()) for a in range(0, 126, 20)])
