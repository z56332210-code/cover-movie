"""Audio analysis: beats, onsets, edit-point (jump) detection, alignment to ref B."""
import json, sys
import numpy as np, librosa

song_path, refb_path, out_path = sys.argv[1:4]
SR, HOP = 22050, 256
y, _ = librosa.load(song_path, sr=SR, mono=True)
r, _ = librosa.load(refb_path, sr=SR, mono=True)
dur = len(y) / SR

def feat(x):
    c = librosa.feature.chroma_cqt(y=x, sr=SR, hop_length=HOP)
    o = librosa.onset.onset_strength(y=x, sr=SR, hop_length=HOP)
    return c, o
cy, oy = feat(y); cr, orr = feat(r)
fps = SR / HOP

def best_offset(t0, t1, search):
    """Offset d (sec) so that song[t0:t1] ~ refB[t0+d : t1+d]."""
    a = cy[:, int(t0*fps):int(t1*fps)]
    best = (-1e9, None)
    for d in np.arange(search[0], search[1], 1/fps):
        s = int((t0 + d) * fps)
        if s < 0 or s + a.shape[1] > cr.shape[1]: continue
        b = cr[:, s:s + a.shape[1]]
        sc = float((a * b).sum() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        if sc > best[0]: best = (sc, d)
    return best

seg = []
for t0 in np.arange(2, dur - 6, 4):
    sc, d = best_offset(t0, t0 + 4, (-2, 70))
    seg.append((float(t0), d, sc))
# per-frame jump: spectral flux discontinuity near 85-92
S = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP))
flux = np.sqrt((np.diff(np.log1p(S), axis=1).clip(0) ** 2).sum(0))
times = librosa.frames_to_time(np.arange(len(flux)), sr=SR, hop_length=HOP)

tempo, beats = librosa.beat.beat_track(y=y, sr=SR, hop_length=HOP, units='time', tightness=200)
onsets = librosa.onset.onset_detect(y=y, sr=SR, hop_length=HOP, units='time', backtrack=False)
json.dump({"duration": dur, "tempo": float(np.atleast_1d(tempo)[0]), "beats": [round(float(b), 3) for b in beats],
           "onsets": [round(float(o), 3) for o in onsets], "align": seg}, open(out_path, "w"), indent=1)
print("dur", dur, "tempo", tempo, "beats", len(beats))
for t0, d, sc in seg: print(f"{t0:6.1f} off={d:6.2f} sc={sc:.3f}")
m = (times > 84) & (times < 93)
idx = np.argsort(flux[m])[-6:][::-1]
print("top flux 84-93:", [(round(float(times[m][i]), 3), round(float(flux[m][i]), 1)) for i in idx])
