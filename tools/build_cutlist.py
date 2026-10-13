"""Build the draft cut list (plan/cutlist_draft.json) from the scene plan, line times and beats.

Every cut boundary snaps to a tracked beat. Lyric line starts inside a scene are forced cut points;
the gaps between them are filled with a beat pattern (fast scenes ~3 beats/cut, relaxed ~10 beats/cut).
"""
import json
import math
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
beats = json.load(open(ROOT / "plan/audio_analysis.json"))["beats"]
LT = json.load(open(ROOT / "lyrics/line_times.json"))
lines = {i: t for i, t, _ in LT["lines"]}
L = lines
ja = (ROOT / "lyrics/lyrics.txt").read_text(encoding="utf-8").splitlines()
DUR = 146.84
JUMP = LT["jump_sec"]


def snap(t):
    return min(beats, key=lambda b: abs(b - t))


def bidx(t):
    return beats.index(snap(t))


# ---- crop presets: source, center (px), width (px) of a 16:9 window, rotation (deg), flip_v ----
CROPS = {
    "eyes":        ("upper", (985, 440), 540),
    "eye_r":       ("upper", (925, 425), 360),
    "eye_l":       ("upper", (1030, 455), 360),
    "face":        ("upper", (965, 450), 760),
    "mouth":       ("upper", (965, 585), 440),
    "point_hand":  ("upper", (1160, 560), 560),
    "lolly_hand":  ("upper", (330, 760), 560),
    "neck_frill":  ("upper", (935, 700), 420),
    "collar_L":    ("upper", (760, 1090), 460),
    "collar_R":    ("upper", (1190, 1000), 460),
    "buttons":     ("upper", (1000, 1010), 520),
    "halo":        ("upper", (1090, 110), 440),
    "ribbon_R":    ("upper", (1540, 780), 560),
    "ribbon_L":    ("upper", (420, 1190), 560),
    "skirt":       ("upper", (1100, 1650), 1000),
    "bust":        ("upper", (965, 760), 1400),
    "lolly":       ("upper", (300, 690), 320),
    "nails":       ("upper", (430, 800), 400),
    "cuff_L":      ("upper", (470, 960), 440),
    "cuff_R":      ("upper", (1450, 660), 440),
    "hood_top":    ("upper", (930, 260), 760),
    "hair_L":      ("upper", (720, 720), 520),
    "cross_close": ("upper", (760, 1100), 280),
    "tongue":      ("upper", (960, 595), 260),
    "finger_eye":  ("upper", (1070, 500), 340),
    "wide_upper":  ("upper", (1000, 950), 1900),
    "sleeve_R":    ("upper", (1500, 1100), 700),
    "silhouette":  ("full", (562, 1000), None),   # whole figure fit to height (band scenes)
    "legs":        ("full", (560, 1500), 900),
    "shoes":       ("full", (560, 1780), 760),
}

# ---- focus point (eye / mask / hand / prop) of every crop preset, source px ----
FOCUS = {
    "eyes": (980, 438), "eye_r": (935, 415), "eye_l": (1030, 460), "face": (935, 415), "mouth": (960, 594),
    "tongue": (960, 594), "point_hand": (1060, 500), "finger_eye": (1040, 490), "lolly_hand": (330, 700),
    "lolly": (300, 690), "nails": (440, 760), "neck_frill": (935, 690), "collar_L": (730, 1050), "collar_R": (1150, 960),
    "cross_close": (730, 1060), "buttons": (1000, 960), "halo": (1090, 110), "ribbon_R": (1540, 760),
    "ribbon_L": (420, 1180), "cuff_L": (470, 960), "cuff_R": (1450, 660), "hood_top": (935, 415), "hair_L": (720, 720),
    "wide_upper": (935, 415), "sleeve_R": (1500, 1100), "skirt": (1100, 1600), "bust": (935, 415),
    "silhouette": (548, 300), "legs": (560, 1500), "shoes": (560, 1780),
}

# ---- 5 layout presets (normalised rects; lyric rects stay fixed for a whole section) ----
TH = (1 / 3, 2 / 3)
PRESETS = {
    "P1": dict(name="right_column", orient="vertical", rects=[[0.68, 0.11, 0.95, 0.84]], focus=[(TH[0], TH[0]), (TH[0], TH[1])]),
    "P2": dict(name="left_column", orient="vertical", rects=[[0.05, 0.11, 0.32, 0.84]], focus=[(TH[1], TH[0]), (TH[1], TH[1])]),
    "P3": dict(name="center_giant", orient="horizontal", rects=[[0.04, 0.56, 0.96, 0.86]], focus=[(TH[0], TH[0]), (TH[1], TH[0])]),
    "P4": dict(name="mirror", orient="vertical", rects=[[0.74, 0.11, 0.96, 0.84], [0.04, 0.11, 0.26, 0.84]],
               focus=[(TH[0], TH[0]), (TH[1], TH[0])]),
    "P5": dict(name="illustration_only", orient=None, rects=[], focus=[(TH[0], TH[0]), (TH[1], TH[0]), (TH[1], TH[1]), (TH[0], TH[1])]),
}
SECTION = {1: "intro", 2: "verse_a", 3: "verse_a", 4: "verse_a", 5: "pre_chorus", 6: "chorus_a", 7: "chorus_a",
           8: "verse_b", 9: "verse_b", 10: "audio_edit", 11: "chorus_b", 12: "chorus_b", 13: "chorus_b",
           14: "last_chorus", 15: "last_chorus", 16: "ending", 17: "ending", 18: "ending"}
SECTION_PRESET = {"intro": "P5", "verse_a": "P1", "pre_chorus": "P3", "chorus_a": "P4", "verse_b": "P2",
                  "audio_edit": "P5", "chorus_b": "P2", "last_chorus": "P3", "ending": "P3"}
CHORUS = {"chorus_a", "chorus_b", "last_chorus"}
# one decoration kind per cut, each with a reason (clock behind the subject, starburst only in red, torn edge cuts the art)
DECO = {1: ["clock"], 2: ["torn_edge", "code"], 3: ["band"], 4: ["guides"], 5: ["torn_edge"], 6: ["clock"], 7: ["torn_edge"],
        8: ["band", "checker"], 9: ["checker"], 10: [], 11: ["torn_edge"], 12: ["code", "torn_edge"], 13: [], 14: ["band"],
        15: ["clock"], 16: [], 17: ["clock"], 18: []}
NOCHAR_DECO = {"ink_type": "clock_crop", "band_only": "band", "clock_type": "clock", "paper_type": "guides", "empty_room": None}
T2_AT = [L[6], L[22], L[48], L[63]]          # slice glitch: 4 times, >= 15 s apart

# ---- scenes (audio sec), aligned to lyric lines; mirrors scene_plan_nightcord_v3.json ids ----
# pool entries: (crop, rotation_deg, flip_v)
S = [
    dict(id=1, start=0.0, end=L[2], type="title_card_hud", mode="hold", text="UI", color="black",
         ov=["hud_frame_ornate", "roman_clock_ring:faint"], pool=[(None, 0, False)], cuts_at=[L[1]]),
    dict(id=2, start=L[2], end=L[6], type="black_crop_vertical", mode="fast", text="A", color="mono",
         ov=["hud_frame_ornate", "code_text_block"],
         pool=[("mouth", -18, False), ("lolly", 24, False), ("hood_top", 8, False), ("finger_eye", -30, False),
               ("collar_L", 12, False), ("eye_r", -8, False), ("cuff_L", 35, False), ("buttons", -20, False),
               ("nails", -12, False), ("hair_L", 18, False), ("cross_close", -25, False), ("wide_upper", 4, False)]),
    dict(id=3, start=L[6], end=L[14], type="repeat_band_clock", mode="fast", text="D", color="paper+ink",
         ov=["roman_clock_ring", "hud_frame_ornate"],
         pool=[("silhouette", 0, False), ("halo", 0, False), ("silhouette", 0, False), ("shoes", 0, False)],
         special={13: dict(text="B", note="giant 神っぽいな + mono radial lines (B t033)")}),
    dict(id=4, start=L[14], end=L[19], type="paper_crop_vertical", mode="relaxed", text="A", color="paper+ink",
         ov=["circle_guides", "mini_icon", "hud_frame_ornate"], zone="relaxed",
         pool=[("collar_R", -6, False), ("neck_frill", 4, False), ("sleeve_R", -3, False), ("wide_upper", 0, False)]),
    dict(id=5, start=L[19], end=L[22], type="giant_type_mirror", mode="fast", text="B+A(mirror)", color="paper+ink",
         ov=["mirror_symmetry", "hud_frame_ornate:dim"],
         pool=[("face", 0, False), ("eyes", 0, False), ("mouth", 0, False), ("bust", 0, False), ("halo", 0, False), ("nails", 0, False)],
         special={21: dict(type="black_card", text="small", note='"Gott ist tot" tiny on black (B t048)')}),
    dict(id=6, start=L[22], end=L[30], type="inverted_crop_box_text", mode="fast", text="A(stack)", color="mono",
         ov=["roman_clock_ring:pass", "circle_guides", "hud_frame_ornate"],
         pool=[("point_hand", 180, True), ("face", 160, False), ("lolly_hand", 0, True), ("collar_L", -32, False),
               ("eye_l", 180, True), ("ribbon_L", 28, False), ("mouth", 0, True), ("halo", 200, False),
               ("neck_frill", -25, False), ("tongue", 170, False), ("cuff_R", 0, True), ("hood_top", 190, False),
               ("nails", 150, True), ("wide_upper", 180, True)],
         special={23: dict(type="black_card", text="small", note='"My God" tiny'),
                  26: dict(type="black_card", text="small", note='"My God" tiny')}),
    dict(id=7, start=L[30], end=L[35], type="red_starburst_slash", mode="fast", text="A→C(red)", color="mono→RED#1",
         ov=["hud_frame_ornate"], red=(L[33], L[35]),
         red_ov=["starburst_red", "checker_strip", "red_slash"],
         pool=[("eye_r", -12, False), ("point_hand", -10, False), ("face", 6, False), ("eye_l", 15, False),
               ("eyes", 0, False), ("mouth", 6, False)]),
    dict(id=8, start=L[35], end=L[41], type="repeat_band_silhouette", mode="fast", text="D", color="ink+gray",
         ov=["checker_floor", "halftone", "hud_frame_ornate"],
         pool=[("silhouette", 0, False), ("legs", 0, False), ("silhouette", 0, False), ("shoes", 0, False)]),
    dict(id=9, start=L[41], end=JUMP, type="checker_blur_transition", mode="fast", text="B(神っぽいな)", color="mono+gray smear",
         ov=["checker_blur", "whip_blur"],
         pool=[("silhouette", 0, False), ("silhouette", 0, False)]),
    dict(id=10, start=JUMP, end=JUMP + 0.36, type="audio_edit_mask", mode="hold", text="-", color="white+mosaic",
         ov=["white_flash", "glitch_mosaic"], pool=[(None, 0, False)]),
    dict(id=11, start=JUMP + 0.36, end=L[46], type="red_starburst_slash", mode="fast", text="C(red)+A", color="RED#2→mono",
         ov=["hud_frame_ornate"], red=(JUMP + 0.36, L[44]), red_ov=["starburst_red", "red_slash"],
         pool=[("eyes", 0, False), ("eye_l", -14, False), ("face", 10, False), ("eye_r", 6, False), ("point_hand", -20, False),
               ("finger_eye", 12, False), ("tongue", -8, False)],
         special={44: dict(type="black_card", text="small", note='"My God" tiny')}),
    dict(id=12, start=L[46], end=L[50], type="black_crop_vertical", mode="fast", text="A", color="mono",
         ov=["glitch_mosaic", "code_text_block", "hud_frame_ornate"],
         pool=[("collar_R", 20, False), ("ribbon_L", -30, False), ("lolly_hand", -15, False), ("buttons", 25, False),
               ("neck_frill", -12, False), ("point_hand", 30, False), ("ribbon_R", -22, False), ("sleeve_R", 14, False),
               ("finger_eye", -20, False), ("cross_close", 30, False), ("hair_L", -10, False)],
         special={47: dict(type="black_card", text="small", note='"My God" tiny')}),
    dict(id=13, start=L[50], end=L[51], type="white_flash", mode="hold", text="small", color="white",
         ov=[], pool=[(None, 0, False)]),
    dict(id=14, start=L[51], end=L[59], type="repeat_band_red", mode="fast", text="D+C(red)", color="paper→RED#3",
         ov=["torn_paper_strips", "hud_frame_ornate:dim"], red=(L[55], L[57] + 1.4),
         red_ov=["starburst_red", "checker_strip"],
         pool=[("silhouette", 0, False), ("halo", 0, False), ("silhouette", 0, False), ("skirt", 0, False),
               ("silhouette", 0, False), ("shoes", 0, False)]),
    dict(id=15, start=L[59], end=L[64], type="inverted_crop_box_text", mode="fast", text="A", color="mono",
         ov=["roman_clock_ring", "mirror_symmetry", "hud_frame_ornate"],
         pool=[("face", 180, True), ("lolly_hand", 160, False), ("collar_R", 0, True), ("eye_r", 190, False),
               ("ribbon_R", -28, False), ("halo", 0, True), ("tongue", 0, True), ("cuff_L", 200, False),
               ("hood_top", 0, True), ("finger_eye", 170, False)],
         special={63: dict(text="B", note="giant 神っぽいな thin serif, cropped off-frame")}),
    dict(id=16, start=L[64], end=L[67], type="giant_type_window_light", mode="relaxed", text="B", color="grayscale+window light",
         ov=["window_light", "hud_frame_ornate:dim"], zone="relaxed",
         pool=[("face", 0, False), ("wide_upper", 0, False), ("eyes", 0, False)]),
    dict(id=17, start=L[67], end=145.3, type="black_word", mode="hold", text="small→人生", color="black",
         ov=["roman_clock_ring:faint"], pool=[(None, 0, False)], cuts_at=[L[68]]),
    dict(id=18, start=145.3, end=DUR, type="white_bar_end", mode="hold", text="-", color="paper",
         ov=[], pool=[(None, 0, False)]),
]

FAST_PATTERN = [3, 3, 2, 4, 3, 2, 3, 4, 3, 2]   # beats per cut (avg 2.9 beats ≈ 1.22 s → ~8 cuts / 10 s)
RELAX_PATTERN = [10, 12, 9]


def scene_points(sc):
    """Cut start times inside a scene (beat-snapped)."""
    s0 = sc["start"] if sc["id"] in (1, 10) or sc["start"] == 0 else snap(sc["start"])
    s1 = DUR if sc["id"] == 18 else snap(sc["end"])
    if sc["id"] == 10:
        return [snap(JUMP)], snap(JUMP + 0.36)
    if sc["id"] == 9:
        s1 = snap(JUMP)
    if sc["id"] == 11:
        s0 = snap(JUMP + 0.36)
    forced = sorted({snap(lines[i]) for i in lines if sc["start"] < lines[i] < sc["end"]} |
                    {snap(t) for t in sc.get("cuts_at", [])} |
                    {snap(t) for t in sc.get("red", ())[:1] if t > s0 + 0.2})
    forced = [f for f in forced if s0 + 0.3 < f < s1 - 0.3]
    if sc["mode"] == "hold":
        return [s0] + forced, s1
    beat_len = 2.9 if sc["mode"] == "fast" else 8.0    # target beats per cut
    if sc["mode"] == "relaxed":                        # keep only line cuts >= 6 beats apart
        kept = []
        for f in forced:
            if beats.index(f) - beats.index(kept[-1] if kept else s0) >= 6:
                kept.append(f)
        forced = kept
    pts, carry = [s0], 0.0
    anchors = [s0] + forced + [s1]
    for a, b in zip(anchors, anchors[1:]):
        ia, ib = beats.index(a), (beats.index(b) if b in beats else len(beats) - 1)
        n = ib - ia
        parts = max(1, round((n + carry) / beat_len))
        carry = (n + carry) - parts * beat_len
        step = [round(n * (q + 1) / parts) for q in range(parts - 1)]
        pts += [beats[ia + q] for q in step if 0 < q < n]
        if b < s1:
            pts.append(b)
    return sorted(set(pts)), s1


TRANS_ALT = ["cut_shake", "flip", "whip", "cut_shake", "black", "cut_shake"]
GLITCH_AT = [L[6], L[22], L[28], JUMP, L[48], L[49], L[63]]  # 7 glitches incl. the mandatory edit mask
glitch_beats = {snap(t) for t in GLITCH_AT}

cuts, prev_tr, alt_i, run, recent, tr_used = [], None, 0, 0, [], {}
for sc in S:
    pts, s1 = scene_points(sc)
    for j, t0 in enumerate(pts):
        t1 = pts[j + 1] if j + 1 < len(pts) else s1
        if t1 - t0 < 0.05:
            continue
        pool = sc["pool"]; st = (j + sc["id"]) % len(pool)
        crop, rot, flip = pool[st]
        for q in range(len(pool)):            # no preset reused within the last 5 cuts (silhouette scenes excepted)
            cand = pool[(st + q) % len(pool)]
            if cand[0] in (None, "silhouette") or cand[0] not in recent[-5:]:
                crop, rot, flip = cand; break
        active = [i for i in lines if lines[i] < t1 and (lines.get(i + 1, LT["end_sec"]) > t0)]
        start_line = next((i for i in lines if abs(snap(lines[i]) - t0) < 0.01), None)
        c = dict(start=round(t0, 3), dur=round(t1 - t0, 3), scene=sc["id"], type=sc["type"], text_level=sc["text"],
                 lyric_lines=active, crop=crop, rot=rot, flip_v=flip, overlays=list(sc["ov"]))
        if crop:
            src, (cx, cy), w = CROPS[crop]
            jr = np.random.default_rng(len(cuts) * 101 + 7)
            if w is not None:                 # every cut gets its own framing
                w = int(w * jr.uniform(0.82, 1.28)); cx = int(cx + jr.uniform(-0.12, 0.12) * w); cy = int(cy + jr.uniform(-0.10, 0.10) * w)
                c["rot"] = round(rot + float(jr.uniform(-7, 7)), 1)
            c["crop_src"] = f"art/char_{src}.webp"
            c["crop_box"] = dict(cx=cx, cy=cy, w=w)
            if w is not None and sc["id"] in (2, 4, 5, 6, 12, 15, 16):
                v = jr.choice(["single", "negative", "strip"], p=[0.72, 0.14, 0.14])
                if sc["id"] in (4, 16) and v != "single":
                    v = "strip" if v == "strip" else "single"
                c["variant"] = str(v)
                if v == "split":
                    other = [p_ for p_ in pool if p_[0] not in (crop, None, "silhouette")]
                    if other:
                        o = other[int(jr.integers(len(other)))]
                        s2, (ox, oy), ow = CROPS[o[0]]
                        c["split"] = dict(crop=o[0], cx=ox, cy=oy, w=int(ow * jr.uniform(0.85, 1.2)), rot=o[1], flip_v=o[2],
                                          angle=float(jr.uniform(55, 80)) * (1 if jr.random() < 0.5 else -1))
                    else:
                        c["variant"] = "single"
            recent.append(crop)
        if start_line and start_line in sc.get("special", {}):
            c.update({k: v for k, v in sc["special"][start_line].items() if k != "note"})
            c["note"] = sc["special"][start_line]["note"]
            if c.get("type") == "black_card":
                c["crop"] = None; c["rot"] = 0; c["flip_v"] = False; c.pop("crop_src", None); c.pop("crop_box", None)
        # inverted_crop_box_text: at most 3 in a row -> every 4th cut becomes an upright crop
        if c["type"] == "inverted_crop_box_text":
            run = run + 1 if cuts and cuts[-1]["type"] == "inverted_crop_box_text" else 1
            if run > 3:
                c.update(type="black_crop_vertical", rot=-12, flip_v=False); run = 0
        # character-less cuts: every ~5th cut in fast scenes, one per relaxed zone (no wall-to-wall character)
        NOCHAR = {2: "ink_type", 12: "ink_type", 11: "ink_type", 3: "band_only", 8: "band_only", 14: "band_only",
                  6: "clock_type", 15: "clock_type", 7: "ink_type", 4: "paper_type", 16: "empty_room", 5: "paper_type"}
        is_red = bool(sc.get("red") and snap(sc["red"][0]) - 0.01 <= t0 < snap(sc["red"][1]) - 0.01)
        if sc["id"] in NOCHAR and c.get("type") != "black_card" and not is_red and not c.get("note"):
            relaxed_pick = sc.get("zone") == "relaxed" and j == (1 if sc["id"] == 4 else 0)
            fast_pick = sc.get("zone") != "relaxed" and j % 5 == 3
            if relaxed_pick or fast_pick:
                c.update(nochar=NOCHAR[sc["id"]], crop=None, rot=0, flip_v=False)
                c.pop("crop_src", None); c.pop("crop_box", None)
        red = sc.get("red")
        c["red"] = bool(red and snap(red[0]) - 0.01 <= t0 < snap(red[1]) - 0.01)
        if c["red"]:
            c["overlays"] += sc["red_ov"]
        # ---- section / layout preset / lyric rect / focus target / single decoration ----
        sec = SECTION[sc["id"]]; pre = PRESETS[SECTION_PRESET[sec]]
        k_in_sec = sum(1 for q in cuts if q["section"] == sec)
        c.update(section=sec, layout=SECTION_PRESET[sec], lyric_orient=pre["orient"], lyric_rect=pre["rects"][0] if len(pre["rects"]) == 1 else pre["rects"],
                 focus_target=list(pre["focus"][k_in_sec % len(pre["focus"])]), flip_h=bool(k_in_sec % 2))
        if c.get("crop") == "silhouette":           # whole figure: head on an upper third, body stays in frame, never mirrored
            c["focus_target"][1] = TH[0]; c["flip_h"] = False
        if c.get("crop"):
            c["focus_src"] = list(FOCUS[c["crop"]])
        if c.get("nochar"):
            dk = NOCHAR_DECO[c["nochar"]]; c["deco"] = [dk] if dk else []
        elif c["red"]:
            c["deco"] = ["starburst"]
        elif c.get("type") == "black_card":
            c["deco"] = []
        else:
            opts = DECO[sc["id"]]; c["deco"] = [opts[j % len(opts)]] if opts else []
        if "clock" in c["deco"]:
            c["clock_at"] = "focus"
        # ---- transition library T1..T6 (never twice in a row), specials for title / edit / white / black ----
        allowed = ["T1", "T4", "T6"] if sec in CHORUS else ["T3", "T5", "T6"]
        if j == 0 and sc["id"] == 1:
            tr = "fade_in"
        elif sc["id"] == 10:
            tr = "edit_mask"
        elif sc["id"] == 13 and j == 0:
            tr = "white_blowout"
        elif sc["id"] == 17 and j == 0:
            tr = "cut_to_black"
        elif any(abs(t0 - snap(x)) < 0.01 for x in T2_AT):
            tr = "T2"
        else:
            cand = [x for x in allowed if x != prev_tr]
            tr = min(cand, key=lambda x: (tr_used.get(x, 0), allowed.index(x)))
        tr_used[tr] = tr_used.get(tr, 0) + 1
        if tr == "T3" and cuts and cuts[-1].get("focus_target"):
            c["focus_target"] = list(cuts[-1]["focus_target"])     # flash match: same screen position
        c["transition_in"] = tr
        prev_tr = tr
        cuts.append(c)

# ---- camera policy: one move per cut, in one direction (or none) ----
VERSE_LIKE = {"intro", "verse_a", "pre_chorus", "verse_b", "ending"}
ZOOM_SPEED_MAX = 0.08          # per second (peak of the eased move)
IMPACT_GAP = 1.7               # full-screen impact zoom at most once per 1.7 s


def _zoom_amount(dur):
    cap = ZOOM_SPEED_MAX * dur / 3.0                    # ease-out cubic: fastest at the start, peak speed = amount * 3 / dur
    return math.floor(min(0.04, cap) * 10000) / 10000   # round down: never above the speed cap


push_run, last_impact = 0, -99.0
red_starts = {round(snap(sc["red"][0]), 3) for sc in S if sc.get("red")}
for idx, c in enumerate(cuts):
    sec = c["section"]; dur = c["dur"]
    first = idx == 0 or cuts[idx - 1]["section"] != sec
    last = idx + 1 == len(cuts) or cuts[idx + 1]["section"] != sec
    prev_cam = cuts[idx - 1].get("cam") if idx else None
    cam, amt = "static", 0.0
    if dur > 1.0 and c["scene"] not in (10, 18) and c.get("crop") != "silhouette":   # full figure: camera stays still
        if last and prev_cam != "pull_out" and _zoom_amount(dur) >= 0.02:
            cam = "pull_out"                                  # breathe out once at the end of a section
        elif sec in VERSE_LIKE:
            cam = "push_in" if push_run < 3 and _zoom_amount(dur) >= 0.02 else "static"
        elif sec in CHORUS:
            k = sum(1 for q in cuts[:idx] if q["section"] == sec)
            cam = ("pan_x", "static", "pan_y", "static")[k % 4]
    if cam in ("push_in", "pull_out"):
        amt = _zoom_amount(dur)
    elif cam in ("pan_x", "pan_y"):
        amt = 0.025
    push_run = push_run + 1 if cam == "push_in" else 0
    c.update(cam=cam, cam_amount=amt, pan_dir=(1 if idx % 2 else -1))
    # impact zoom (1.00 -> 1.03 -> 1.00): chorus first beat, section start, big accent (red start); >= 1.7 s apart
    accent = first or round(c["start"], 3) in red_starts
    c["impact"] = bool(accent and c["start"] - last_impact >= IMPACT_GAP and c["scene"] not in (1, 10, 13, 17, 18)
                       and c["transition_in"] not in ("T2", "edit_mask", "fade_in", "white_blowout", "cut_to_black")
                       and not (idx and cuts[idx - 1].get("impact")))
    if c["impact"]:
        last_impact = c["start"]

# ---- transitions again: T6 (beat cut + impact zoom) only on impact cuts, otherwise T1/T4 (chorus) or T3/T5 (verse) ----
prev_tr, tr_used = None, {}
for idx, c in enumerate(cuts):
    tr = c["transition_in"]
    if tr in ("fade_in", "edit_mask", "white_blowout", "cut_to_black", "T2"):
        prev_tr = tr; continue
    if c["impact"] and prev_tr != "T6":
        tr = "T6"
    else:
        c["impact"] = False
        allowed = ["T1", "T4"] if c["section"] in CHORUS else ["T3", "T5"]
        cand = [x for x in allowed if x != prev_tr]
        tr = min(cand, key=lambda x: (tr_used.get(x, 0), allowed.index(x)))
    tr_used[tr] = tr_used.get(tr, 0) + 1
    c["transition_in"] = tr; prev_tr = tr
    sec = c["section"]; pre = PRESETS[SECTION_PRESET[sec]]
    k_in_sec = sum(1 for q in cuts[:idx] if q["section"] == sec)
    c["focus_target"] = list(pre["focus"][k_in_sec % len(pre["focus"])])
    if tr == "T3" and idx:
        c["focus_target"] = list(cuts[idx - 1]["focus_target"])     # flash match: same screen position
    if c.get("crop") == "silhouette":
        c["focus_target"][1] = TH[0]; c["flip_h"] = False

# ---- density table (cuts starting in each 10 s window) ----
dens = []
for w in range(0, 150, 10):
    n = sum(1 for c in cuts if w <= c["start"] < w + 10)
    zone = sorted({c["scene"] for c in cuts if w <= c["start"] < w + 10})
    dens.append(dict(window=f"{w}-{min(w + 10, 146.8)}", cuts=n, scenes=zone))
reds = []
for c in cuts:
    if c["red"]:
        if reds and abs(reds[-1][1] - c["start"]) < 0.01:
            reds[-1][1] = c["start"] + c["dur"]
        else:
            reds.append([c["start"], c["start"] + c["dur"]])
err = [min(abs(c["start"] - b) for b in beats) * 1000 for c in cuts if c["start"] > 0]
out = dict(
    _readme="장면 목록 초안. start/dur=음원 초. lyric_lines=lyrics.txt 행 번호(1부터). crop_box=원본 픽셀 중심/폭(16:9 창). "
            "transition_in=이 컷으로 들어오는 전환. red=빨강 구간 여부.",
    audio=dict(duration=DUR, bpm=round(60 / 0.4214, 1), jump_sec=JUMP,
               jump_note="원곡(=레퍼런스 B 음원) 91.63초 → 147.50초로 점프. scene_plan의 88.0~89.3초 추정을 90.80초로 보정."),
    stats=dict(total_cuts=len(cuts), nochar_cuts=sum(1 for c in cuts if not c.get("crop")), mean_beat_err_ms=round(sum(err) / len(err), 1),
               red_windows=[[round(a, 2), round(b, 2), round(b - a, 2)] for a, b in reds],
               glitches=[round(snap(t), 3) for t in T2_AT] + [round(snap(JUMP), 3)],
               clock_scenes=sorted({c["scene"] for c in cuts if "clock" in c.get("deco", [])}),
               presets={k: v["name"] for k, v in PRESETS.items()}, section_preset=SECTION_PRESET,
               camera={k: sum(1 for c in cuts if c["cam"] == k) for k in ("push_in", "pull_out", "pan_x", "pan_y", "static")},
               impacts=[c["start"] for c in cuts if c["impact"]]),
    density=dens, scenes=[{k: s[k] for k in ("id", "start", "end", "type", "color")} for s in S], cuts=cuts)
if __name__ == "__main__":
    json.dump(out, open(ROOT / "plan/cutlist_draft.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out["stats"], ensure_ascii=False))
    for d in dens:
        print(d)
