#!/usr/bin/env python3
"""Rule checker for the cut data (run before every render; render only when violations == 0).

    python3 tools/lint.py                      # checks plan/cutlist_draft.json (+ layout/contrast via the renderer)
    python3 tools/lint.py --plan plan/cutlist_legacy.json --legacy   # old preview data, renderer behaviour inferred
    python3 tools/lint.py --range 9 27         # only cuts that start in this range
    python3 tools/lint.py --static             # data rules only (skip renderer layout / contrast sampling)

Exit code 1 when any violation is found. Writes plan/lint_report.json.
"""
import argparse, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--plan", default=str(ROOT / "plan/cutlist_draft.json"))
ap.add_argument("--legacy", action="store_true")
ap.add_argument("--range", type=float, nargs=2)
ap.add_argument("--static", action="store_true")
A = ap.parse_args()

PLAN = json.load(open(A.plan))
CUTS = PLAN["cuts"]
LT = json.load(open(ROOT / "lyrics/line_times.json"))
LINES = {i: t for i, t, _ in LT["lines"]}
JA = (ROOT / "lyrics/lyrics.txt").read_text(encoding="utf-8").splitlines()
beats = np.array(json.load(open(ROOT / "plan/audio_analysis.json"))["beats"])
FPS = 30
T0, T1 = A.range or (-1, 1e9)

RULES = {
    "1-2": "시선점이 3등분 교차점 밖 / 가사가 반대쪽 1/3에 없음",
    "1-3": "같은 구간 안에서 가사 박스 위치가 바뀜",
    "1-4": "이유 없는 장식 (시계≠주인공 뒤 / 빨강 밖 스타버스트 / 떠 있는 찢어진 종이)",
    "1-5": "장식이 가사 박스(+60px)와 겹침",
    "1-6": "레이아웃 프리셋(5종) 미지정",
    "2-1": "최고 위계(100%) 가사가 두 줄 이상",
    "2-2": "세로 순서(오른쪽→왼쪽) 위반 / 한 장면에 세로·가로 혼용",
    "2-3": "큰 글자: 첫·끝 글자 잘림 / 5열 이상 / 단어 중간 줄바꿈 / 글자 위 장식",
    "2-4": "글자 크기 미달 (세로 박스 46px, 자막 34px @1080)",
    "2-5": "한국어 자막 띠(60%, 70px) 없음",
    "2-6": "가사 타이밍 (3~5프레임 먼저 / 0.2초 꼬리 / 큰 글자 12프레임 정지)",
    "2-7": "글자 대비 4.5:1 미달",
    "3-1": "T1~T6 이외의 전환",
    "3-2": "같은 전환이 연속",
    "3-3": "T2 횟수(4~5회)·간격(15초에 1번) 위반",
    "3-4": "구간별 추천 전환이 아님 (후렴 T1/T4/T6, 절 T3/T5/T6)",
    "3-5": "전환이 박자에 안 맞음 (>50ms)",
    "4-1": "박자 줌 펄스가 켜져 있음 (BEAT_PULSE_ZOOM≠0)",
    "4-2": "1초 이하 컷에서 카메라가 움직임 / 카메라 동작 미지정",
    "4-3": "줌 양 2~6% 밖 또는 줌 속도 초당 8% 초과",
    "4-4": "카메라 방향 정책 위반 (절=푸시인, 후렴=팬/정지, 풀아웃은 구간 끝 1번·연속 금지, 푸시인 연속 3컷 초과)",
    "4-5": "충격 줌이 1.7초에 1번 넘음 / 후렴 첫 박·구간 시작·큰 악센트가 아닌 곳",
    "4-6": "움직이는 채널 3개 이상 / 핸드헬드 0.05% 초과 / 회전 떨림",
    "2-8": "활성 가사가 얼굴/눈을 가림",
    "1-7": "얼굴 클로즈업 컷이 연속",
    "2-9": "낮은 위계 글자 불투명도 45% 초과",
    "5-1": "레이어 수 최소치 미달 (절 4 / 후렴 6 / 릴렉스 3)",
    "5-2": "후렴 구성 미달 (컷아웃 3~5 / 에코 4~8줄 / 장식 2종 이상)",
    "5-3": "고밀도 타이포 레시피 2가지 미만 (장면 단위)",
}
V = []


def bad(rule, ci, detail):
    c = CUTS[ci] if ci is not None else None
    t = c["start"] if c else None
    if c is not None and not (T0 <= t < T1):
        return
    V.append(dict(rule=rule, cut=ci, t=None if t is None else round(t, 2), scene=c["scene"] if c else None, detail=detail))


SECTION_OF_SCENE = {1: "intro", 2: "verse_a", 3: "verse_a", 4: "verse_a", 5: "pre_chorus", 6: "chorus_a", 7: "chorus_a",
                    8: "verse_b", 9: "verse_b", 10: "audio_edit", 11: "chorus_b", 12: "chorus_b", 13: "chorus_b",
                    14: "last_chorus", 15: "last_chorus", 16: "ending", 17: "ending", 18: "ending"}
CHORUS = {"chorus_a", "chorus_b", "last_chorus"}
FACE = {"eyes", "eye_r", "eye_l", "face", "mouth", "tongue", "hood_top", "finger_eye", "point_hand", "wide_upper", "bust"}
SPECIAL_TR = {"fade_in", "edit_mask", "cut_to_black", "white_blowout", "hard_cut"}


# ---------------------------------------------------------------- legacy inference (old renderer behaviour)
def legacy_frame_model(ci, c):
    """What the old renderer drew for this cut: deco kinds, lyric style/orientation, layout key, sizes."""
    sc = c["scene"]; ov = c.get("overlays", []); crop = c.get("crop"); nc = c.get("nochar")
    deco = set()
    for o in ov:
        k = o.split(":")[0]
        if k in ("hud_frame_ornate", "mirror_symmetry", "window_light", "white_flash", "halftone", "whip_blur", "glitch_mosaic"):
            continue
        deco.add({"roman_clock_ring": "clock", "torn_paper_strips": "torn_floating", "starburst_red": "starburst",
                  "checker_strip": "checker", "checker_floor": "checker", "checker_blur": "checker", "red_slash": "slash",
                  "code_text_block": "code", "circle_guides": "guides", "mini_icon": "icons"}.get(k, k))
    if crop and sc in (2, 6, 7, 11, 12, 15) and c.get("type") != "black_card" and ci % 4 != 3:
        deco.add("torn_edge")
    if crop and sc in (3, 8, 9, 14):
        deco.add("slice_bars")
    if crop and sc in (2, 4, 7, 12, 16):
        deco.add("smoke")
    if sc == 9 or (c.get("red") and sc == 14):
        deco.add("speed_lines")
    if nc == "ink_type":
        deco |= {"speed_lines", "slice_bars"}
    if nc == "paper_type":
        deco |= {"guides", "icons"}
    if nc == "clock_type":
        deco = {"clock"}
    protag = 0 if not crop else (2 if c.get("variant") == "split" else 1)
    # lyric styles (A vertical boxes, B giant horizontal, C red, D band, card horizontal)
    lines = c.get("lyric_lines", [])
    styles = set()
    if c.get("type") == "black_card":
        styles.add("h")
    elif sc in (2, 4, 12, 13) or nc in ("clock_type", "paper_type"):
        styles.add("v")
    elif sc == 5:
        styles |= {"v", "h"}
    elif sc in (6, 15):
        styles.add("v")
        if 63 in lines:
            styles.add("h")
    elif sc == 7:
        styles.add("h" if 34 in lines and c.get("red") else "v")
    elif sc == 11:
        styles.add("v")
    elif sc in (3, 8, 9, 14, 16, 17) or nc in ("ink_type", "empty_room", "band_only"):
        styles.add("h")
    side = None
    if sc in (2, 12):
        side = "R" if ci % 2 else "L"
    elif sc in (4, 6, 7, 13, 15) or nc in ("clock_type", "paper_type"):
        side = "R"
    elif sc == 11:
        side = "L"
    else:
        side = "C"
    giant = sc in (5, 16) or nc in ("ink_type", "empty_room") or (sc in (3, 9, 15) and set(lines) & {13, 42, 63}) or (c.get("red") and sc in (7, 14))
    vsize = {2: 58, 12: 62, 4: 44, 5: 44, 6: 70, 15: 76, 7: 86, 11: 64, 13: 44}.get(sc, 60 if nc == "clock_type" else 64)
    return dict(deco=deco, protag=protag, styles=styles, side=side, giant=giant, vsize=vsize, caption=26, caption_band=False,
                lead_frames=0, tail=0.0, giant_slides=True, preset=None)


def legacy_checks():
    sec_side = {}
    scene_styles = defaultdict(set)
    for ci, c in enumerate(CUTS):
        m = legacy_frame_model(ci, c)
        sec = SECTION_OF_SCENE[c["scene"]]
        if len(m["deco"]) > 1 or m["protag"] > 1:
            bad("1-1", ci, f"장식 {sorted(m['deco'])}" + (" + 크롭 2개(split)" if m["protag"] > 1 else ""))
        if m["protag"]:
            bad("1-2", ci, "시선점 배치 규칙 없음 (크롭 중심 기준)")
        if "clock" in m["deco"] and m["protag"]:
            bad("1-4", ci, "시계 링이 주인공 시선점이 아닌 화면 중앙/이동 위치")
        if "torn_floating" in m["deco"]:
            bad("1-4", ci, "찢어진 종이 띠가 공중에 떠 있음")
        if m["deco"] & {"code", "guides", "icons", "smoke", "slice_bars", "speed_lines", "checker"} and m["styles"]:
            bad("1-5", ci, "장식 위치가 가사 영역을 피하지 않음(제외 영역 없음)")
        if sec in sec_side and m["styles"] and sec_side[sec] != m["side"]:
            bad("1-3", ci, f"{sec}: 가사 위치 {sec_side[sec]} → {m['side']}")
        if m["styles"]:
            sec_side[sec] = m["side"]
        scene_styles[c["scene"]] |= m["styles"]
        if m["styles"] and m["vsize"] < 46 and "v" in m["styles"]:
            bad("2-4", ci, f"세로 박스 {m['vsize']}px")
        if m["giant"]:
            bad("2-3", ci, "큰 글자가 화면 밖으로 잘림/슬라이드(첫·끝 글자 보장 없음)")
            bad("2-6", ci, "큰 글자가 계속 움직임(12프레임 정지 없음)")
        tr = c.get("transition_in")
        if tr not in SPECIAL_TR and not re.match(r"T[1-6]$", tr or ""):
            bad("3-1", ci, f"전환 '{tr}'")
        if ci and tr == CUTS[ci - 1].get("transition_in"):
            bad("3-2", ci, f"'{tr}' 연속")
    for sc, st in scene_styles.items():
        if {"v", "h"} <= st:
            ci = next(i for i, c in enumerate(CUTS) if c["scene"] == sc)
            bad("2-2", ci, f"장면 {sc}: 세로·가로 가사 혼용")
    for sec in sorted(set(SECTION_OF_SCENE.values())):
        ci = next(i for i, c in enumerate(CUTS) if SECTION_OF_SCENE[c["scene"]] == sec)
        bad("1-6", ci, f"{sec}: 프리셋 기록 없음")
    bad("2-4", None, "한국어 자막 26px (34px 미만)")
    bad("2-5", None, "자막 뒤 반투명 띠 없음")
    for i in LINES:
        bad("2-6", None, f"{i}행: 소리와 동시에 등장(선행 0프레임), 꼬리 0초")
    t2 = [c for c in CUTS if c.get("transition_in") == "T2"]
    bad("3-3", None, f"T2 {len(t2)}회 (4~5회 필요)")


# ---------------------------------------------------------------- checks on the new data model
def new_checks():
    sys.path.insert(0, str(ROOT / "tools"))
    sec_rect, sec_preset = {}, {}
    scene_orient = defaultdict(set)
    prev_tr = None
    t2_times = []
    for ci, c in enumerate(CUTS):
        sec = c.get("section")
        if not sec or c.get("layout") not in ("P1", "P2", "P3", "P4", "P5"):
            bad("1-6", ci, "section/layout 미지정")
            continue
        if sec in sec_preset and sec_preset[sec] != c["layout"]:
            bad("1-3", ci, f"{sec}: {sec_preset[sec]} → {c['layout']}")
        sec_preset.setdefault(sec, c["layout"])
        if sec in sec_rect and sec_rect[sec] != c.get("lyric_rect"):
            bad("1-3", ci, f"{sec}: 가사 영역 변경")
        sec_rect.setdefault(sec, c.get("lyric_rect"))
        deco = c.get("deco") or []
        kd = c.get("density")
        if ci and c.get("crop") in FACE and CUTS[ci - 1].get("crop") in FACE:
            bad("1-7", ci, f"{CUTS[ci - 1].get('crop')} → {c.get('crop')}")
        if kd == "chorus" and not c.get("nochar"):
            nc = len(c.get("cutouts", [])) + (1 if c.get("crop") else 0)
            if not 3 <= nc <= 5:
                bad("5-2", ci, f"컷아웃 {nc}개")
            if not 4 <= c.get("echo_rows", 0) <= 8:
                bad("5-2", ci, f"에코 {c.get('echo_rows', 0)}줄")
            if len([d for d in deco if d != "band"]) < 2:
                bad("5-2", ci, f"장식 {deco}")
        if kd and len(c.get("recipes", [])) < 2:
            bad("5-3", ci, f"레시피 {c.get('recipes')}")
        for d in deco:
            if d == "starburst" and not c.get("red"):
                bad("1-4", ci, "빨강 밖 스타버스트")
            if d == "torn_floating":
                bad("1-4", ci, "떠 있는 찢어진 종이")
            if d == "clock" and c.get("crop") and c.get("clock_at") != "focus":
                bad("1-4", ci, "시계 링이 주인공 뒤가 아님")
        if c.get("lyric_orient"):
            scene_orient[c["scene"]].add(c["lyric_orient"])
        tr = c.get("transition_in")
        if tr not in SPECIAL_TR and not re.match(r"T[1-6]$", tr or ""):
            bad("3-1", ci, f"전환 '{tr}'")
        if prev_tr and tr == prev_tr:
            bad("3-2", ci, f"'{tr}' 연속")
        prev_tr = tr
        if tr == "T2":
            t2_times.append(c["start"])
        elif tr in ("T1", "T3", "T4", "T5", "T6"):
            ok = {"T1", "T4", "T6"} if sec in CHORUS else {"T3", "T5", "T6"}
            if tr not in ok:
                bad("3-4", ci, f"{sec}에 {tr}")
        if ci and c["start"] > 0 and tr not in ("edit_mask",):
            err = abs(beats - round(c["start"] * FPS) / FPS).min() * 1000
            if err > 50:
                bad("3-5", ci, f"박자 오차 {err:.0f}ms")
    for sc, o in scene_orient.items():
        if len(o) > 1:
            ci = next(i for i, c in enumerate(CUTS) if c["scene"] == sc)
            bad("2-2", ci, f"장면 {sc}: {sorted(o)} 혼용")
    if not (4 <= len(t2_times) <= 5) and A.range is None:
        bad("3-3", None, f"T2 {len(t2_times)}회")
    for a, b in zip(t2_times, t2_times[1:]):
        if b - a < 15:
            bad("3-3", None, f"T2 간격 {b - a:.1f}s ({a:.1f}→{b:.1f})")
    # camera rules
    import math as _m
    import render as R
    if R.BEAT_PULSE_ZOOM != 0:
        bad("4-1", None, f"BEAT_PULSE_ZOOM={R.BEAT_PULSE_ZOOM}")
    if R.HANDHELD > 0.0005 + 1e-9:
        bad("4-6", None, f"핸드헬드 {R.HANDHELD * 100:.2f}%")
    verse_like = {"intro", "verse_a", "pre_chorus", "verse_b", "ending"}
    push_run, last_imp = 0, -99.0
    red_starts = set()
    for ci, c in enumerate(CUTS):
        if c.get("red") and not (ci and CUTS[ci - 1].get("red")):
            red_starts.add(ci)
    for ci, c in enumerate(CUTS):
        cam = c.get("cam"); amt = c.get("cam_amount", 0)
        if cam not in ("push_in", "pull_out", "pan_x", "pan_y", "static"):
            bad("4-2", ci, f"cam={cam}"); continue
        if c.get("crop") == "silhouette" and (cam != "static" or c.get("flip_h")):
            bad("4-2", ci, "전신 컷에 카메라 이동/좌우반전")
        if c["dur"] <= 1.0 and cam != "static":
            bad("4-2", ci, f"{c['dur']:.2f}s 컷에 {cam}")
        if cam in ("push_in", "pull_out"):
            if not 0.02 - 1e-9 <= amt <= 0.06 + 1e-9:
                bad("4-3", ci, f"줌 {amt * 100:.1f}%")
            if amt * 3 / c["dur"] > 0.08 + 1e-9:          # ease-out cubic peak speed at the start of the cut
                bad("4-3", ci, f"줌 속도 {amt * 3 / c['dur'] * 100:.1f}%/s")
        sec = c.get("section"); last = ci + 1 == len(CUTS) or CUTS[ci + 1].get("section") != sec
        if cam == "pull_out" and (not last or (ci and CUTS[ci - 1].get("cam") == "pull_out")):
            bad("4-4", ci, "풀아웃이 구간 끝이 아니거나 연속")
        if cam == "push_in" and sec in CHORUS:
            bad("4-4", ci, "후렴에 푸시인")
        if cam in ("pan_x", "pan_y") and sec in verse_like:
            bad("4-4", ci, "절에 팬")
        push_run = push_run + 1 if cam == "push_in" else 0
        if push_run > 3:
            bad("4-4", ci, "푸시인 4컷 연속")
        if c.get("impact"):
            first = ci == 0 or CUTS[ci - 1].get("section") != sec
            if not (first or ci in red_starts):
                bad("4-5", ci, "후렴 첫 박/구간 시작/큰 악센트가 아닌 충격 줌")
            if c["start"] - last_imp < 1.7:
                bad("4-5", ci, f"충격 줌 간격 {c['start'] - last_imp:.2f}s")
            last_imp = c["start"]
    if R.IMPACT_ZOOM > 0.03 + 1e-9:
        bad("4-5", None, f"충격 줌 {R.IMPACT_ZOOM * 100:.0f}%")
    # lyric timing (data side)
    R.setup(False)
    for i in LINES:
        if not (T0 - 1 <= LINES[i] < T1):
            continue
        w0, w1 = R.line_window(i)
        lead = round((LINES[i] - w0) * FPS)
        if not 3 <= lead <= 5:
            bad("2-6", None, f"{i}행 선행 {lead}프레임")
        end = R.LINE_END.get(i, LINES[i])
        nxt = R.line_window(i + 1)[0] if i + 1 in LINES else 1e9
        if R.tail_end(i) + 1e-6 < end + 0.2:
            bad("2-6", None, f"{i}행 꼬리 {R.tail_end(i) - end:.2f}s")
        if i + 1 in LINES and w1 > nxt + 1e-6:
            bad("2-1", None, f"{i}행과 {i + 1}행이 동시에 보임")
        if R.is_giant_line(i):
            hold = R.giant_hold_frames(i)
            if hold < 12:
                bad("2-6", None, f"{i}행 큰 글자 정지 {hold}프레임")
            rows = R.giant_rows(i)
            if len(rows) > 4:
                bad("2-3", None, f"{i}행 큰 세로 글자 {len(rows)}열")
            full = R.line_ctx(i)["text"]; pos = 0
            for a, b in zip(rows, rows[1:]):
                pos = full.index(a, pos) + len(a)
                if re.search(r"[A-Za-z]$", a) and re.match(r"[A-Za-z]", b) and full[pos:pos + 1] != " ":
                    bad("2-3", None, f"{i}행 영어 단어 중간 줄바꿈: {a}|{b}")
    low_alpha = max(max(v) for v in R.ECHO_ALPHA.values())
    if low_alpha > 0.45 + 1e-9:
        bad("2-9", None, f"에코 불투명도 {low_alpha:.2f}")
    if R.CAPTION_PX_1080 < 34:
        bad("2-4", None, f"자막 {R.CAPTION_PX_1080}px")
    if R.BOX_PX_MIN_1080 < 46:
        bad("2-4", None, f"세로 박스 최소 {R.BOX_PX_MIN_1080}px")
    if not (abs(R.CAPTION_BAND_ALPHA - 0.6) < 0.01 and R.CAPTION_BAND_H_1080 == 70):
        bad("2-5", None, "자막 띠 설정")
    if A.static:
        return
    # ---------------- renderer layout sampling: focus, rects, overlaps, giant clipping, contrast
    samples = []
    for ci, c in enumerate(CUTS):
        if T0 <= c["start"] < T1 and c["dur"] > 0.15:
            samples.append((ci, c["start"] + min(c["dur"] * 0.6, max(0.4, c["dur"] - 0.1))))
    for i in LINES:
        if T0 <= LINES[i] < T1:
            samples.append((None, min(R.line_window(i)[1] - 0.05, LINES[i] + 0.45)))
    for ci, t in samples:
        R.render_frame(t)
        D = R.DEBUG
        cj = D["cut"]; c = CUTS[cj]
        W, H = R.Q.W, R.Q.H
        if D.get("focus") and c.get("layout") != "P5" or (D.get("focus") and c.get("layout") == "P5"):
            fx, fy = D["focus"]
            dmin = min(np.hypot(fx - W * a, fy - H * b) for a in (1 / 3, 2 / 3) for b in (1 / 3, 2 / 3))
            if dmin > 0.06 * W and not c.get("nochar"):
                bad("1-2", cj, f"시선점 {fx / W:.2f},{fy / H:.2f} (교차점에서 {dmin / W * 100:.0f}%W)")
            rect = c.get("lyric_rect")
            if rect and c["layout"] in ("P1", "P2"):
                mid = (rect[0] + rect[2]) / 2
                if (fx / W < 0.5) == (mid < 0.5):
                    bad("1-2", cj, "가사가 시선점과 같은 쪽")
            if rect and c["layout"] == "P3" and fx / W > 0.5:
                bad("1-2", cj, "큰 세로 글자와 시선점이 같은 오른쪽")
        if D.get("deco_over_lyrics", 0) > 0:
            bad("1-5", cj, f"장식이 가사 제외영역에 {D['deco_over_lyrics']}px")
        for (x0, y0, x1, y1) in D.get("giant_boxes", []):
            m = 0.03 * W
            if x0 < m - 1 or x1 > W - m + 1 or y0 < 0 or y1 > H:
                bad("2-3", cj, f"큰 글자가 화면 밖 ({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f})")
        if D.get("lines_bright", 0) > 1:
            bad("2-1", cj, f"밝은 줄 {D['lines_bright']}개")
        if D.get("eye_cover"):
            bad("2-8", cj, "활성 가사가 눈 위에 있음")
        kd = CUTS[cj].get("density")
        need = {"verse": 4, "chorus": 6, "relax": 3}.get(kd)
        nl = len(D.get("layers", []))
        if need and nl < need and (t - CUTS[cj]["start"]) * 30 > 6:
            bad("5-1", cj, f"{kd} 레이어 {nl}개 {D.get('layers')}")
        if D.get("order_ok") is False:
            bad("2-2", cj, "세로 박스 순서 위반")
        for kind, cr in D.get("contrast", []):
            if kind == "red":                       # red keywords: exempted by the user (no backing allowed)
                continue
            if cr < 4.5:
                bad("2-7", cj, f"{kind} 대비 {cr:.2f}:1")


if A.legacy:
    legacy_checks()
else:
    new_checks()

cnt = Counter(v["rule"] for v in V)
print(f"{'규칙':5} {'위반':>5}  내용")
for r, desc in RULES.items():
    print(f"{r:5} {cnt.get(r, 0):5d}  {desc}")
print(f"합계 {len(V)}")
json.dump(dict(total=len(V), by_rule=dict(cnt), violations=V), open(ROOT / ("plan/lint_report_legacy.json" if A.legacy else "plan/lint_report.json"), "w"),
          ensure_ascii=False, indent=1)
sys.exit(1 if V else 0)
