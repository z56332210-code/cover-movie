"""Compare matched windows of the reference and our render with tools/metrics.py; prints a table with % differences.
usage: python3 tools/compare_windows.py <our.mp4> <our_offset_in_file> name:ref_t0:ref_t1:our_t0:our_t1 ..."""
import sys, json
sys.path.insert(0, "tools")
from metrics import metrics
ours, off = sys.argv[1], float(sys.argv[2])
rows = []
for spec in sys.argv[3:]:
    name, a0, a1, b0, b1 = spec.split(":"); a0, a1, b0, b1 = map(float, (a0, a1, b0, b1))
    R = metrics("ref/reference/reference.mp4", a0, a1 - a0); O = metrics(ours, b0 - off, b1 - b0)
    da, db = a1 - a0, b1 - b0
    def row(k, ra, ro):
        pct = (ro - ra) / ra * 100 if ra else float("nan")
        rows.append((name, k, ra, ro, pct))
    row("cuts / 20 s", R["cuts"] / da * 20, O["cuts"] / db * 20)
    for k in ("lav", "mag", "navy", "white", "black"): row("area " + k, R["palette"][k], O["palette"][k])
    row("halftone area", R["halftone"], O["halftone"]); row("contrast (luma std)", R["contrast"], O["contrast"]); row("motion", R["motion"], O["motion"])
    row("glitch / min", R["glitch_events"] / da * 60, O["glitch_events"] / db * 60); row("glitch frames", R["glitch_mean_frames"], O["glitch_mean_frames"])
    cr = [c["thirds"] for c in R["camera"] if max(c["thirds"]) > 5]; co = [c["thirds"] for c in O["camera"] if max(c["thirds"]) > 5]
    for j, nm in enumerate(("front", "mid", "back")):
        if cr and co: row(f"camera {nm} px/s", sum(c[j] for c in cr) / len(cr), sum(c[j] for c in co) / len(co))
print("| window | metric | reference | ours | diff |\n|---|---|---|---|---|")
for n, k, a, b, p in rows: print(f"| {n} | {k} | {a:.3f} | {b:.3f} | {p:+.0f}% {'OK' if abs(p) <= 15 else ''} |")
