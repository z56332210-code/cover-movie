"""Beat grid, downbeats, sections, per-frame energy and onset curves.
usage: python3 tools/analyze_audio.py [audio] [out.json] [k_sections]"""
import json, sys
import numpy as np, librosa

FPS = 30
SRC = sys.argv[1] if len(sys.argv) > 1 else "assets/audio/song.mp3"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/analysis.json"
y, sr = librosa.load(SRC, sr=22050, mono=True)
dur = len(y) / sr
hop = 256

# --- beats (dynamic programming tracker, then local-tempo check for drift)
oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
tempo, beat_frames = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=hop, tightness=400)
beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
ibi = np.diff(beats)

# --- downbeats: phase of 4 with the strongest low-frequency accent
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
low = S[freqs < 150].sum(0)
low_at = low[np.clip(beat_frames, 0, len(low) - 1)]
phase = int(np.argmax([low_at[p::4].mean() for p in range(4)]))
downbeats = beats[phase::4]

# --- energy curve per video frame (RMS, normalised 0..1)
rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
t_rms = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
tf = np.arange(int(np.ceil(dur * FPS))) / FPS
energy = np.interp(tf, t_rms, rms)
energy = (energy - np.percentile(energy, 2)) / (np.percentile(energy, 98) - np.percentile(energy, 2))
energy = np.clip(energy, 0, 1)

# --- onsets: strong percussive hits for accents
y_h, y_p = librosa.effects.hpss(y)
oenv_p = librosa.onset.onset_strength(y=y_p, sr=sr, hop_length=hop)
on_frames = librosa.onset.onset_detect(onset_envelope=oenv_p, sr=sr, hop_length=hop, backtrack=False)
on_t = librosa.frames_to_time(on_frames, sr=sr, hop_length=hop)
on_s = oenv_p[on_frames] / oenv_p.max()
onset_curve = np.interp(tf, librosa.frames_to_time(np.arange(len(oenv_p)), sr=sr, hop_length=hop), oenv_p / oenv_p.max())

# --- section boundaries: chroma+mfcc recurrence, agglomerative on downbeat-synced features
chroma = librosa.feature.chroma_cqt(y=y_h, sr=sr, hop_length=hop)
mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)
db_frames = librosa.time_to_frames(downbeats, sr=sr, hop_length=hop)
feat = np.vstack([librosa.util.normalize(chroma), librosa.util.normalize(mfcc), rms[None] * 5])
sync = librosa.util.sync(feat, db_frames, aggregate=np.median)
k = int(sys.argv[3]) if len(sys.argv) > 3 else 12
bounds = librosa.segment.agglomerative(sync, k)
bound_t = [float(downbeats[b - 1]) if b > 0 else 0.0 for b in bounds]

# --- vocal-band activity (harmonic part, 300-3400 Hz) for lyric-phrase detection
H = np.abs(librosa.stft(y_h, n_fft=2048, hop_length=hop))
vb = H[(freqs > 300) & (freqs < 3400)].sum(0)
vb = librosa.util.normalize(np.log1p(vb))
vocal = np.interp(tf, librosa.frames_to_time(np.arange(len(vb)), sr=sr, hop_length=hop), vb)

out = dict(fps=FPS, duration=dur, bpm=float(np.atleast_1d(tempo)[0]),
           beats=beats.round(4).tolist(), downbeats=downbeats.round(4).tolist(),
           ibi_std=float(ibi.std()), section_bounds=bound_t,
           onsets=[[round(float(a), 4), round(float(b), 3)] for a, b in zip(on_t, on_s)],
           energy=energy.round(3).tolist(), onset_curve=onset_curve.round(3).tolist(),
           vocal=vocal.round(3).tolist())
json.dump(out, open(OUT, "w"))
print("bpm", out["bpm"], "beats", len(beats), "ibi std", out["ibi_std"], "downbeat phase", phase)
print("first downbeats", downbeats[:6].round(3))
print("bounds", [round(b, 2) for b in bound_t])
# local bpm by 8-bar windows
for i in range(0, len(downbeats) - 8, 8):
    print(f"{downbeats[i]:6.2f}s  bpm {240 / np.median(np.diff(downbeats[i:i + 9])):.2f}")
