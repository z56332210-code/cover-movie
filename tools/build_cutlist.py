"""Build the draft cut list (plan/cutlist_draft.json) from the scene plan, line times and beats.

Every cut boundary snaps to a tracked beat. Lyric line starts inside a scene are forced cut points;
the gaps between them are filled with a beat pattern (fast scenes ~3 beats/cut, relaxed ~10 beats/cut).
"""
import json
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
         ov=[], pool=[(None, 0, False)], cuts_at=[L[68]]),
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

cuts, prev_tr, alt_i, run, recent = [], None, 0, 0, []
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
                v = jr.choice(["single", "negative", "split", "strip"], p=[0.6, 0.12, 0.16, 0.12])
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
        # transition into this cut: light-leak by default, never the same twice in a row
        if j == 0 and sc["id"] == 1:
            tr = "fade_in"
        elif round(t0, 3) in {round(g, 3) for g in glitch_beats}:
            tr = "glitch_mosaic_0.2s"
        elif sc["id"] == 10:
            tr = "glitch_mosaic_0.2s"
        elif sc["id"] in (13,):
            tr = "white_blowout"
        elif sc["id"] == 17 and j == 0:
            tr = "cut_to_black"
        elif sc["id"] == 18:
            tr = "hard_cut"
        elif prev_tr != "lightleak_8f":
            tr = "lightleak_8f"
        else:
            tr = TRANS_ALT[alt_i % len(TRANS_ALT)]; alt_i += 1
        if tr == prev_tr:
            tr = "cut_shake" if tr != "cut_shake" else "lightleak_8f"
        c["transition_in"] = tr
        prev_tr = tr
        cuts.append(c)

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
               glitches=[round(snap(t), 3) for t in GLITCH_AT],
               clock_scenes=[s["id"] for s in S if any(o.startswith("roman_clock_ring") for o in s["ov"])]),
    density=dens, scenes=[{k: s[k] for k in ("id", "start", "end", "type", "color")} for s in S], cuts=cuts)
if __name__ == "__main__":
    json.dump(out, open(ROOT / "plan/cutlist_draft.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out["stats"], ensure_ascii=False))
    for d in dens:
        print(d)
