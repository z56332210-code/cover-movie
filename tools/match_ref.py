"""For each 6 s window of the song, find the best-matching offset in the reference audio (chroma xcorr, key shift allowed)."""
import sys, numpy as np, librosa
hop = 1024; sr = 22050
def feat(path):
    y, _ = librosa.load(path, sr=sr)
    c = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(y), sr=sr, hop_length=hop)
    return librosa.util.normalize(c, axis=0)
A = feat("assets/audio/song.mp3"); B = feat(sys.argv[1])
fr = sr / hop; W = int(6 * fr)
for s in range(0, A.shape[1] - W, int(3 * fr)):
    best = (-1, 0, 0)
    for k in range(12):
        Bk = np.roll(B, k, axis=0)
        # sliding dot product
        sc = np.array([np.sum(A[:, s:s+W] * Bk[:, o:o+W]) for o in range(0, B.shape[1] - W)]) / W
        o = int(sc.argmax())
        if sc[o] > best[0]: best = (sc[o], o, k)
    print(f"song {s/fr:6.1f}s -> ref {best[1]/fr:6.1f}s  shift {best[2]:2d}  score {best[0]:.2f}  delta {best[1]/fr - s/fr:6.1f}")
