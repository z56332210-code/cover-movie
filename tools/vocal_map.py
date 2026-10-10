"""Center-channel spectral subtraction -> vocal activity per 8th note, printed per bar."""
import json, numpy as np, librosa
A = json.load(open("data/analysis.json"))
y, sr = librosa.load("assets/audio/song.mp3", sr=22050, mono=False)
hop = 256
M = np.abs(librosa.stft((y[0] + y[1]) / 2, n_fft=2048, hop_length=hop))
Sd = np.abs(librosa.stft((y[0] - y[1]) / 2, n_fft=2048, hop_length=hop))
f = librosa.fft_frequencies(sr=sr, n_fft=2048)
band = (f > 250) & (f < 4000)
V = np.clip(M[band] - 1.5 * Sd[band], 0, None)
# harmonic only, suppress drums
V = librosa.decompose.hpss(V, margin=2.0)[0]
v = np.log1p(V.sum(0)); v = (v - np.percentile(v, 10)) / (np.percentile(v, 95) - np.percentile(v, 10))
t = librosa.frames_to_time(np.arange(len(v)), sr=sr, hop_length=hop)
np.save("data/vocal_curve.npy", np.vstack([t, v]))
beats = np.array(A["beats"]); db = np.array(A["downbeats"])
chars = " .:-=+*#%@"
for i in range(len(db)):
    s = db[i]; e = db[i + 1] if i + 1 < len(db) else s + 1.86
    cells = np.linspace(s, e, 9)
    row = ""
    for a, b in zip(cells[:-1], cells[1:]):
        x = v[(t >= a) & (t < b)].mean()
        row += chars[int(np.clip(x, 0, 0.999) * len(chars))]
    print(f"bar{i:3d} {s:7.2f} |{row}|")
