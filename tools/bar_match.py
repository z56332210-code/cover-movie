"""Match every bar of our song to the reference audio (chroma + MFCC per bar, cosine similarity) -> data/song_to_ref_bars.json
usage: python3 tools/bar_match.py"""
import json
import numpy as np, librosa

def bar_feats(path, ana):
    y, sr = librosa.load(path, sr=22050)
    hop = 512
    ch = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    mf = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=20)[1:]
    db = np.array(ana["downbeats"]); bar = 4 * 60 / ana["bpm"]
    starts = np.concatenate([np.arange(db[0], -0.01, -bar)[::-1][:-1], db])          # include pickup bars before the first downbeat
    fr = librosa.time_to_frames(starts, sr=sr, hop_length=hop)
    out = []
    for a, b in zip(fr, fr[1:]):
        if b - a < 4: continue
        # 8 sub-steps per bar keep rhythm/melody order
        seg = np.array_split(np.arange(a, b), 8)
        v = np.concatenate([np.concatenate([ch[:, s].mean(1), mf[:, s].mean(1) / 50]) for s in seg])
        out.append(v / (np.linalg.norm(v) + 1e-9))
    return starts[:len(out)], np.array(out)

A = json.load(open("data/analysis.json")); R = json.load(open("data/ref_analysis.json"))
ts, S = bar_feats("assets/audio/song.mp3", A)
tr, Rf = bar_feats("out/ref/ref_audio.wav", R)
M = S @ Rf.T
best = M.argmax(1)
rows = [dict(bar=i, t=round(float(ts[i]), 3), ref_bar=int(best[i]), ref_t=round(float(tr[best[i]]), 3), sim=round(float(M[i, best[i]]), 3),
             second=round(float(np.sort(M[i])[-2]), 3)) for i in range(len(S))]
json.dump(dict(song_bar_t=ts.round(3).tolist(), ref_bar_t=tr.round(3).tolist(), rows=rows), open("data/song_to_ref_bars.json", "w"), indent=1)
for r in rows: print(f"bar {r['bar']:3d} {r['t']:7.2f}s -> ref bar {r['ref_bar']:3d} {r['ref_t']:7.2f}s  sim {r['sim']:.3f} (2nd {r['second']:.3f})")

# --- contiguous alignment: DP over ref bars, step j->j+1 free, any other jump costs PEN (edits are block cuts)
Z = (M - M.mean(1, keepdims=True)) / (M.std(1, keepdims=True) + 1e-9)
PEN = 6.0
n, m = Z.shape
D = np.full((n, m), -1e9); B = np.zeros((n, m), int)
D[0] = Z[0]
for i in range(1, n):
    best_any = D[i - 1].argmax()
    for j in range(m):
        cont = D[i - 1, j - 1] if j > 0 else -1e9
        jump = D[i - 1, best_any] - PEN
        if cont >= jump: D[i, j], B[i, j] = cont + Z[i, j], j - 1
        else: D[i, j], B[i, j] = jump + Z[i, j], best_any
path = [int(D[-1].argmax())]
for i in range(n - 1, 0, -1): path.append(int(B[i, path[-1]]))
path = path[::-1]
segs = []
for i, j in enumerate(path):
    if segs and j == segs[-1]["ref_bar1"] + 1: segs[-1].update(song_bar1=i, ref_bar1=j)
    else: segs.append(dict(song_bar0=i, song_bar1=i, ref_bar0=j, ref_bar1=j))
for s in segs:
    s.update(song_t0=round(float(ts[s["song_bar0"]]), 3), ref_t0=round(float(tr[s["ref_bar0"]]), 3), bars=s["song_bar1"] - s["song_bar0"] + 1)
    s["mean_z"] = round(float(np.mean([Z[i, path[i]] for i in range(s["song_bar0"], s["song_bar1"] + 1)])), 2)
d = json.load(open("data/song_to_ref_bars.json")); d["path"] = path; d["segments"] = segs
json.dump(d, open("data/song_to_ref_bars.json", "w"), indent=1)
print("\nsegments")
for s in segs: print(f"song bars {s['song_bar0']:3d}-{s['song_bar1']:3d} ({s['song_t0']:7.2f}s, {s['bars']:2d} bars) <- ref bars {s['ref_bar0']:3d}-{s['ref_bar1']:3d} ({s['ref_t0']:7.2f}s)  z {s['mean_z']}")
