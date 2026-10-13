"""Find exact edit point: frame-wise log-mel distance of song vs refB at the two offsets."""
import sys, numpy as np, librosa
song, refb = sys.argv[1:3]
SR, HOP = 22050, 220  # 10 ms
y, _ = librosa.load(song, sr=SR); r, _ = librosa.load(refb, sr=SR)
M = lambda x: librosa.power_to_db(librosa.feature.melspectrogram(y=x, sr=SR, n_fft=2048, hop_length=HOP, n_mels=64))
my, mr = M(y), M(r)
fps = SR / HOP
def dist(d, t0, t1):
    i0, i1 = int(t0*fps), int(t1*fps); s = int(round(d*fps))
    return np.abs(my[:, i0:i1] - mr[:, i0+s:i1+s]).mean(0)
def tune(d, t0, t1):
    return min(np.arange(d-0.05, d+0.05, 0.01), key=lambda dd: dist(dd, t0, t1).mean())
d1 = tune(0.83, 70, 85); d2 = tune(56.70, 92, 110)
print("tuned offsets", round(d1, 3), round(d2, 3))
t0, t1 = 84.0, 92.0
a, b = dist(d1, t0, t1), dist(d2, t0, t1)
k = np.ones(5)/5; a, b = np.convolve(a, k, 'same'), np.convolve(b, k, 'same')
ts = t0 + np.arange(len(a))/fps
for t, x, z in zip(ts[::10], a[::10], b[::10]):
    print(f"{t:6.2f} d1={x:5.1f} d2={z:5.1f} {'<1' if x < z else '  2>'}")

# what does the 89.9-90.9 gap match? search all offsets on short windows
for w0 in np.arange(89.8, 91.0, 0.2):
    best = min(np.arange(-1, 70, 0.01), key=lambda dd: dist(dd, w0, w0+0.2).mean() if int((w0+dd)*fps) > 0 else 1e9)
    print(f"win {w0:.1f}: best off {best:.2f} d={dist(best, w0, w0+0.2).mean():.1f}  d1={dist(d1, w0, w0+0.2).mean():.1f} d2={dist(d2, w0, w0+0.2).mean():.1f}")
rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
print("rms song 89.5-91.2:", [round(float(v), 3) for v in rms[int(89.5*fps):int(91.2*fps):5]])
