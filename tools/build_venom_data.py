"""Bundle everything the page needs into web/venom/data.js (window.DATA)."""
import json
A = json.load(open("data/analysis.json"))
D = dict(plan=json.load(open("data/plan.json")), lyrics=json.load(open("data/lyrics_timed.json", encoding="utf-8")),
         credits=json.load(open("data/credits.json", encoding="utf-8")), typo=json.load(open("data/typo.json", encoding="utf-8")),
         meta=json.load(open("web/venom/img/meta.json")), beats=A["beats"], downbeats=A["downbeats"], energy=A["energy"],
         onsets=A["onsets"], duration=A["duration"], fps=A["fps"])
open("web/venom/data.js", "w", encoding="utf-8").write("window.DATA = " + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";\n")
print("data.js", sum(len(json.dumps(v)) for v in D.values()) // 1024, "KB")
