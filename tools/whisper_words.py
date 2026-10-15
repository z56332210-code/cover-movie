"""Transcribe the song with faster-whisper (word timestamps) -> plan/whisper_words.json"""
import json, sys
from pathlib import Path
from faster_whisper import WhisperModel
ROOT = Path(__file__).resolve().parent.parent
model_name = sys.argv[1] if len(sys.argv) > 1 else "large-v3"
m = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
prompt = "神っぽいな。とぅとぅるとぅとぅとぅる「風」。ぽいじゃんぽいじゃん。愛のネタバレ「別れ」っぽいな。"
import librosa
audio, _ = librosa.load(str(ROOT / "audio/song.mp3"), sr=16000, mono=True)
segs, info = m.transcribe(audio, language="ja", word_timestamps=True, vad_filter=False,
                          initial_prompt=prompt, condition_on_previous_text=False, beam_size=5)
words = []
for s in segs:
    print(f"[{s.start:7.2f}-{s.end:7.2f}] {s.text}", flush=True)
    for w in s.words or []:
        words.append(dict(s=round(w.start, 3), e=round(w.end, 3), w=w.word, p=round(w.probability, 3)))
json.dump(dict(model=model_name, words=words), open(ROOT / "plan/whisper_words.json", "w"), ensure_ascii=False, indent=0)
print("words", len(words))
