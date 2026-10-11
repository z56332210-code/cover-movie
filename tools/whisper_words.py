"""Transcribe the song with word timestamps (helper for lyric alignment only)."""
import json, sys
import librosa
from faster_whisper import WhisperModel

audio, out, model_name = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "medium")
lyrics = [l.split("\t")[1] for l in open("data/lyrics.tsv", encoding="utf-8") if l[0].isdigit()]
model = WhisperModel(model_name, device="cpu", compute_type="int8")
pcm, _ = librosa.load(audio, sr=16000, mono=True)  # decode ourselves (PyAV API mismatch)
segs, info = model.transcribe(pcm, language="ja", word_timestamps=True, vad_filter=False, beam_size=5,
                              initial_prompt="".join(lyrics[:8]), condition_on_previous_text=False)
words = []
for s in segs:
    print(f"[{s.start:7.2f}-{s.end:7.2f}] {s.text}", flush=True)
    words += [{"w": w.word, "s": w.start, "e": w.end, "p": w.probability} for w in s.words]
json.dump(words, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
