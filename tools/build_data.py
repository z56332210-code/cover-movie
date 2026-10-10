"""Bundle analysis + timed lyrics + character meta into web/data.js (window.DATA) so the page needs no fetches."""
import json
A = json.load(open("data/analysis.json"))
L = json.load(open("data/lyrics_timed.json", encoding="utf-8"))
S = json.load(open("data/sections.json"))
M = json.load(open("web/img/meta.json"))
D = dict(fps=A["fps"], duration=A["duration"], bpm=A["bpm"], beats=A["beats"], downbeats=A["downbeats"],
         onsets=A["onsets"], energy=A["energy"], onsetCurve=A["onset_curve"], sections=S, lyrics=L, chars=M)
open("web/data.js", "w", encoding="utf-8").write("window.DATA=" + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";\n")
print("web/data.js", len(json.dumps(D)) // 1024, "KB")
