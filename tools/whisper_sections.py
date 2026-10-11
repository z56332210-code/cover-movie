"""Whisper word timestamps per lyric section (clip + padding, that section's own lyrics as the prompt).
A single whole-song pass loses the last chorus to hallucination; short clips with the right prompt do not.
Timing source only: displayed text always comes from data/lyrics.tsv.
usage: python3 tools/whisper_sections.py <audio (ideally separated vocals)> <out.json> [model]"""
import json, sys
import librosa
from faster_whisper import WhisperModel

audio, out = sys.argv[1], sys.argv[2]
model = WhisperModel(sys.argv[3] if len(sys.argv) > 3 else "large-v3", device="cpu", compute_type="int8")
rows = [l.rstrip("\n").split("\t") for l in open("data/lyrics.tsv", encoding="utf-8") if l[0].isdigit()]
SM = json.load(open("data/section_map.json"))
secs = {s["name"]: s for s in SM["sections"]}
# lyric-line ranges per section; verse1 split in two (around the instrumental gap) for shorter clips
# (name, first line, last line, clip t0, clip t1, keep t0, keep t1): clips overlap, keep windows do not
CLIPS = [("verse1", 1, 5, 7.0, 27.5, 7.0, 26.0), ("verse1", 6, 10, 24.5, 40.5, 26.0, 39.4), ("pre", 11, 15, 38.5, 56.0, 39.4, 55.0),
         ("chorus1", 16, 21, 54.0, 69.0, 55.0, 69.0), ("bridge", 22, 23, 85.5, 94.5, 85.5, 93.2), ("chorus_last", 24, 27, 92.5, 105.5, 93.2, 104.3),
         ("chorus_last", 28, 33, 103.0, 117.0, 104.3, 117.0)]
pcm, _ = librosa.load(audio, sr=16000, mono=True)
words = []
for name, a, b, t0, t1, k0, k1 in CLIPS:
    prompt = "".join(r[1] for r in rows if a <= int(r[0]) <= b)
    clip = pcm[int(t0 * 16000): int(t1 * 16000)]
    segs, _ = model.transcribe(clip, language="ja", word_timestamps=True, vad_filter=False, beam_size=5,
                               initial_prompt=prompt, condition_on_previous_text=False)
    for s in segs:
        print(f"{name} [{s.start + t0:7.2f}-{s.end + t0:7.2f}] {s.text}", flush=True)
        for w in s.words:
            if not (k0 <= w.start + t0 < k1): continue
            words.append({"w": w.word, "s": round(w.start + t0, 3), "e": round(w.end + t0, 3), "p": round(w.probability, 3), "clip": f"{a}-{b}"})
words.sort(key=lambda w: w["s"])
json.dump(words, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
