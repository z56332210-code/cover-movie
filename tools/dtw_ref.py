"""Map song time -> reference-video time with chroma DTW (subsequence allowed)."""
import sys, numpy as np, librosa
hop = 2048
a, sr = librosa.load("assets/audio/song.mp3", sr=22050)
b, _ = librosa.load(sys.argv[1], sr=22050)
fa = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(a), sr=sr, hop_length=hop)
fb = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(b), sr=sr, hop_length=hop)
D, wp = librosa.sequence.dtw(X=fa, Y=fb, metric="cosine", subseq=True)
wp = wp[::-1]
ta = wp[:, 0] * hop / sr; tb = wp[:, 1] * hop / sr
np.save("data/song_to_ref.npy", np.vstack([ta, tb]))
for t in range(0, 144, 4):
    i = np.searchsorted(ta, t); print(f"song {t:5.1f}s -> ref {tb[min(i, len(tb)-1)]:6.1f}s")
