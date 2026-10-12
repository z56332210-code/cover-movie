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
def beat(n): return DB0 + n * BAR / 4 - LEAD

# (t0, type, framing, lyric method, transition into this shot, section, lyric lines shown, ref shot it copies, note)
# types A colour / B mono manga / C silhouette / D magenta-solid, navy or black / E grey + motion blur
# methods 1 navy box / 1b small white horizontal / 2 vertical + black bars / 2b small white vertical / 3 diagonal band along prop /
#         4 giant cut glyphs / 5 small text in ink-blot centre / 6 magenta bold slanted / credit / title / small (tiny text on D)
S = [
 (0.0,              "D", "black",       "-",      "start",         "intro",   [],          0,  "black (pickup bar, near silence)"),
 (1.30,             "D", "magenta",     "-",      "flash_magenta", "intro",   [],          1,  "magenta flash 0.4 s into the first downbeat"),
 (bar(0),           "C", "keyvisual",   "title",  "cut",           "intro",   [],          2,  "key visual silhouette + props, title logo, glitch strips"),
 (bar(4) - BAR / 4, "D", "black",       "-",      "black",         "intro",   [1],         3,  "black gap 1 beat; pickup あー sung here (lyric stays visible)"),
 (bar(4),           "A", "prop_close",  "1b",     "cut",           "verse1",  [1, 2],      4,  "props close-up (plush/syringe/pill), ink + halftone, fast pan decelerating"),
 (ln(3),            "A", "prop_band",   "3",      "flash_magenta",           "verse1",  [3, 4],      5,  "guitar/harp, diagonal band along the neck, words revealed in chunks"),
 (ln(5) - 0.47,     "D", "black",       "-",      "black",         "verse1",  [4],         6,  "black gap"),
 (ln(5),            "A", "char_close",  "1",      "cut",           "verse1",  [5],         7,  "character close-up, navy box, fast zoom-out then settle"),
 (bar(12) + 1.10,   "D", "black",       "-",      "glitch",        "verse1",  [5],         8,  "RGB-slice glitch then short black into the silhouette"),
 (bar(13),          "C", "keyvisual",   "-",      "cut",           "verse1",  [],          9,  "instrumental: key visual silhouette, frequent glitch strips"),
 (ln(6) - 0.06,     "D", "black",       "-",      "black",         "verse1",  [6],         36, "black gap (pickup あー on black)"),
 (bar(16) - 0.06,   "B", "prop_manga",  "3",      "cut",           "verse1",  [6],         37, "mono manga props on white + halftone, band along the guitar neck"),
 (ln(7),            "B", "prop_manga",  "4",      "text",          "verse1",  [7],         38, "same shot: giant black glyph rows (text event, no cut)"),
 (bar(20),          "B", "char_manga",  "2",      "cut",           "verse1",  [8],         40, "mono character, vertical text on black bars, slow push"),
 (ln(9),            "B", "char_manga",  "4",      "text",          "verse1",  [9],         40, "same shot: giant black glyphs"),
 (ln(10),           "B", "char_manga",  "1",      "text",          "verse1",  [10],        40, "same shot: navy box"),
 (ln(11) - 0.40,    "D", "magenta",     "-",      "flash_magenta", "pre",     [10],        16, "magenta flash into the pre-chorus"),
 (ln(11),           "A", "ink_centre",  "5",      "cut",           "pre",     [11],        17, "lavender + magenta ink blot, small text in its centre"),
 (ln(12),           "C", "bust_ink",    "2b",     "cut",           "pre",     [12],        18, "silhouette bust in ink, small vertical text both sides"),
 (ln(13) - 1.30,    "C", "bust_ink",    "2b",     "ink_wipe",      "pre",     [12],        19, "magenta ink blobs grow in ~0.1 s steps over the bust"),
 (ln(13) - 0.30,    "D", "navy",        "-",      "flash_navy",    "pre",     [12],        20, "navy flash 0.27 s"),
 (ln(13),           "C", "keyvisual",   "1b",     "cut",           "pre",     [13, 14],    21, "key visual, small white horizontal text"),
 (ln(14, 7),        "C", "keyvisual",   "6",      "text",          "pre",     [14],        22, "same shot: big slanted 'ベノベノム' (text event)"),
 (ln(15),           "D", "magenta",     "small",  "flash_magenta", "pre",     [15],        23, "magenta solid, tiny 'さよなラ。'"),
 (ln(15) + 1.10,    "D", "navy",        "-",      "cut",           "pre",     [15],        24, "navy solid"),
 (ln(15) + 1.50,    "D", "black_inset", "-",      "black",         "pre",     [15],          25, "black, framed manga panel flickers in, magenta ink blobs eat it"),
 (ln(16),           "D", "magenta",     "1b",     "flash_magenta", "pre",     [16],        26, "magenta field, white italic 'あらま' (pickup)"),
 (ln(16, 3),        "A", "char_wide",   "4",      "cut",           "chorus1", [16, 17],    27, "character wide + giant glyphs magenta/navy, pop-in per syllable"),
 (ln(17, 4),        "A", "ink_centre",  "5",      "cut",           "chorus1", [17],        28, "ink blot centre: 'ねぇ痛い痛いのとんでけ'"),
 (ln(18),           "A", "char_wide",   "4",      "cut",           "chorus1", [18],        29, "giant 存在感, ink blobs start"),
 (ln(18, 3),        "D", "magenta",     "2b",     "ink_wipe",      "chorus1", [18],        30, "magenta ink field, white vertical '血ドクドク'"),
 (ln(18, 8),        "A", "prop_ink",    "3",      "cut",           "chorus1", [18],        31, "props + ink, band along the prop '零るルル'"),
 (ln(18, 12),       "D", "black",       "small",  "black",         "chorus1", [18],        32, "black + tiny '（無いの？もっと）'"),
 (ln(19),           "A", "char_wide",   "4",      "cut",           "chorus1", [19],        33, "giant 愛/哀 split magenta | navy"),
 (ln(20),           "A", "char_wide",   "6",      "text",          "chorus1", [20],        33, "same shot: magenta slanted '叫べベベノム'"),
 (ln(21),           "A", "char_close",  "4",      "cut",           "chorus1", [21],        34, "close-up, navy glyphs 'メッ。'"),
 (bar(42),          "A", "char_wide",   "credit", "cut",           "interlude", [],        54, "character wide one-shot, credits one at a time (3 bars each)"),
 (ln(22),           "E", "grey_blur",   "4",      "cut",           "bridge",  [22],    55, "grey character + motion blur on white, blurred giant magenta glyphs, magenta slice glitch"),
 (ln(23),           "E", "grey_blur",   "6",      "text",          "bridge",  [23],        55, "same shot: big slanted magenta 'SICK SICK'"),
 (ln(24),           "A", "char_wide",   "4",      "cut",           "chorus_last", [24],    56, "giant 存在抹消, pills denser"),
 (ln(24, 7),        "A", "char_wide",   "2b",     "text",          "chorus_last", [24],    56, "same shot: small white vertical '消えるルル（無いのずっと）'"),
 (ln(25),           "A", "char_wide",   "6",      "text",          "chorus_last", [25],    56, "same shot: magenta slanted 愛/哀 x4, one per beat"),
 (ln(26) - 0.40,    "E", "white_blur",  "-",      "grey_blur",     "chorus_last", [25],    57, "white/grey motion-blur whip"),
 (ln(26),           "A", "char_wide",   "4",      "cut",           "chorus_last", [26, 27], 58, "giant 求愛性孤独ドク, navy pills fill background"),
 (ln(27, 4),        "A", "ink_centre",  "5",      "cut",           "chorus_last", [27],    59, "ink blot centre text"),
 (ln(28),           "A", "char_wide",   "4",      "cut",           "chorus_last", [28],    60, "giant 存在感, ink blobs start"),
 (ln(28, 3),        "D", "magenta",     "2b",     "ink_wipe",      "chorus_last", [28],    60, "magenta ink field, white vertical '血ドクドク'"),
 (ln(28, 8),        "A", "prop_ink",    "3",      "cut",           "chorus_last", [28],    61, "props + ink, band along the prop '零るルル'"),
 (ln(28, 12),       "D", "black",       "small",  "black",         "chorus_last", [28],    62, "black + tiny text"),
 (ln(29),           "A", "char_wide",   "4",      "cut",           "chorus_last", [29],    63, "giant 愛/哀 split"),
 (ln(30),           "A", "char_tight",  "6",      "cut",           "chorus_last", [30],    64, "tighter character crop, magenta slanted '叫べベベノム'"),
 (ln(31),           "A", "char_tight",  "2",      "text",          "chorus_last", [31],    64, "same shot: vertical text on black bars"),
 (ln(32),           "A", "char_tight",  "6",      "text",          "chorus_last", [32],    64, "same shot: magenta slanted"),
 (ln(33),           "A", "face_close",  "4",      "cut",           "outro",   [33],        65, "face close-up (the only one): navy 'メッ。'"),
 (bar(72) + BAR / 2,"A", "face_close",  "title",  "text",          "outro",   [],          65, "same shot: title logo"),
 (bar(74) + BAR / 2,"A", "face_close",  "credit", "text",          "outro",   [],          65, "same shot: music credit"),
 (123.10,           "D", "black_ink",   "-",      "ink_wipe_black","end",     [],          66, "black ink blobs close the frame on the last hit"),
 (123.80,           "D", "black",       "-",      "hold",          "end",     [],          67, "black to end"),
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

# camera from the reference measurements: verse/B close-ups fast after the cut then decelerate, chorus/silhouette/credits near-static
CAM = {"prop_close": "fast_decel", "prop_band": "fast_decel", "char_close": "fast_decel", "prop_manga": "fast_decel",
       "char_manga": "slow_push", "grey_blur": "drift", "face_close": "slow_push", "char_tight": "pan_mid"}
for s in shots: s["camera"] = CAM.get(s["framing"], "static")

# pills per frame (rises toward the end; to be checked against the reference count once the counter exists)
PILLS = {"intro": 3, "verse1": 4, "pre": 5, "chorus1": 8, "interlude": 8, "bridge": 0, "chorus_last": 30, "outro": 20, "end": 0}
for s in shots: s["pills"] = 0 if s["type"] in ("D", "B", "E") else PILLS[s["section"]]

json.dump(dict(bar_s=BAR, first_downbeat=DB0, cut_lead_s=LEAD, duration=END, shots=shots), open("data/plan.json", "w"), ensure_ascii=False, indent=1)

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
st = np.array([s["t0"] for s in real[1:]])
print("cuts per 20 s:", [int(((st >= a) & (st < a + 20)).sum()) for a in range(0, 126, 20)])
