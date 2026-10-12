"""Bundle everything the page needs into web/venom/data.js (window.DATA)."""
import json
A = json.load(open("data/analysis.json"))
D = dict(plan=json.load(open("data/plan.json")), lyrics=json.load(open("data/lyrics_timed.json", encoding="utf-8")),
         credits=json.load(open("data/credits.json", encoding="utf-8")), typo=json.load(open("data/typo.json", encoding="utf-8")),
         meta=json.load(open("web/venom/img/meta.json")), beats=A["beats"], downbeats=A["downbeats"], energy=A["energy"],
         onsets=A["onsets"], duration=A["duration"], fps=A["fps"])
# Korean subtitles always from data/lyrics.tsv (edited after alignment)
KO = {int(r[0]): r[2] for r in (l.rstrip("\n").split("\t") for l in open("data/lyrics.tsv", encoding="utf-8") if l[0].isdigit())}
for l in D["lyrics"]: l["ko"] = KO[l["id"]]
# a line whose display window runs < 0.2 s past the last shot that shows it ends at that cut (no 1-2 frame leftovers)
for l in D["lyrics"]:
    own = [sh for sh in D["plan"]["shots"] if l["id"] in sh["lines"]]
    if own:
        t1 = max(sh["t1"] for sh in own)
        if 0 < l["end"] - t1 < 0.2: l["end"] = round(t1 - 0.001, 3)
open("web/venom/data.js", "w", encoding="utf-8").write("window.DATA = " + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";\n")
print("data.js", sum(len(json.dumps(v)) for v in D.values()) // 1024, "KB")
