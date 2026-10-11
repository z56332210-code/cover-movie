"""data/lyrics_timed.json -> docs/lyric_table.md (time / Japanese / Korean / notes)"""
import json, os
L = json.load(open("data/lyrics_timed.json", encoding="utf-8"))
def mmss(t): return f"{int(t // 60)}:{t % 60:05.2f}"
rows = ["| # | 시간 | 일본어 | 한국어 | 비고 |", "|---|---|---|---|---|"]
for o in L:
    note = []
    if o.get("low"): note.append("⚠ 인식률 낮음 (%d%%)" % round(100 * o["cover"]))
    if o.get("fix"): note.append("직접 수정")
    if o.get("paired"): note.append("반복 멜로디 대조 " + o["paired"].split(" ")[0])
    if o.get("spread"): note.append("몰린 글자 분산: " + ", ".join(o["spread"]))
    rows.append(f"| {o['id']} | {mmss(o['start'])}–{mmss(o['end'])} | {o['ja']} | {o['ko']} | {'; '.join(note)} |")
os.makedirs("docs", exist_ok=True)
open("docs/lyric_table.md", "w", encoding="utf-8").write("# 가사 정렬표\n\n" + "\n".join(rows) + "\n")
print("\n".join(rows))
