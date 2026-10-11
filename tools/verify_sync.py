"""Check A/V sync of a rendered mp4: audio offset vs the original at start/middle/end, and stream durations."""
import json, subprocess, sys
import numpy as np

mp4 = sys.argv[1]
sr = 22050
def decode(path):  # ffmpeg decode (works for mp4/aac and mp3 alike)
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"])
    return np.frombuffer(raw, np.float32)
ref, out = decode("assets/audio/song.mp3"), decode(mp4)
info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration,nb_frames,r_frame_rate", "-of", "json", mp4]))
for s in info["streams"]: print(s)
ok = True
for name, t in (("start", 1.0), ("middle", len(ref) / sr / 2), ("end", len(ref) / sr - 6.0)):
    a = ref[int(t * sr): int((t + 4) * sr)]
    b = out[int((t - 0.2) * sr): int((t + 4.2) * sr)]
    c = np.correlate(b, a, mode="valid")
    lag_ms = (np.argmax(c) - int(0.2 * sr)) / sr * 1000
    ok &= abs(lag_ms) < 25
    print(f"{name:6s} @ {t:6.1f}s  audio offset {lag_ms:+.1f} ms")
v = next(s for s in info["streams"] if s["codec_type"] == "video"); a = next(s for s in info["streams"] if s["codec_type"] == "audio")
dv, da = float(v["duration"]), float(a["duration"])
print(f"video {dv:.3f}s, audio {da:.3f}s, source {len(ref) / sr:.3f}s, diff {abs(dv - da) * 1000:.0f} ms")
ok &= abs(dv - len(ref) / sr) < 0.1
print("SYNC OK" if ok else "SYNC PROBLEM")
