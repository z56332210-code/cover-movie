# スロウダウナー — lyric video (cover)

1920×1080 30fps lyric video for YouTube. The Japanese lyrics carry all the kinetic typography. The Korean translation is a plain subtitle band.

## Layout
| Path | What |
|---|---|
| `assets/` | Source song, character art, references |
| `data/lyrics.tsv` | Japanese / Korean lines (source of truth for displayed text) |
| `data/lyrics_timed.json` | Line and per-character sung times (Whisper large-v3 alignment) |
| `data/analysis.json` | BPM, beats, downbeats, onsets, energy curve |
| `data/sections.json` | Section boundaries |
| `docs/` | Timing table and section plan |
| `web/` | The video itself: one HTML page, `seek(t)` draws a frame from `t` alone |
| `tools/render.mjs` | Playwright renderer: chunked per section, parallel, resumable |
| `tools/verify_sync.py` | A/V sync check at start / middle / end |

## Render the final video on your laptop
You need Node 18+, ffmpeg and Python 3 (with numpy, used only by the sync check).

```bash
npm install
npx playwright install chromium     # once
npm run bench                       # times 10 frames of the heaviest section, prints the ETA
npm run render                      # 1920x1080 30fps -> out/final/slowdowner.mp4
python3 tools/verify_sync.py out/final/slowdowner.mp4
```

- **Progress:** written to `out/final/render.log`.
- **Crash or sleep:** run `npm run render` again. Chunks that finished are kept, see `out/final/manifest.json`.
- **Keep the laptop awake:**
  - macOS: `caffeinate -i npm run render`
  - Windows: Power settings → Sleep "Never" while plugged in

## Iterate (960×540, 15fps)
```bash
npm run preview                                       # whole song
node tools/render.mjs --preview --sections chorus1,C   # re-render only changed sections, then re-concat
node tools/render.mjs --preview --range 62-67          # short clip with audio
npm run stills                                        # one still per section
node tools/render.mjs --preview --check                # text vs subtitle band / safe margins
```

Real-time check in a browser: `npx http-server web` (with `song.mp3` copied into `web/`), then open `index.html?play`.

## Rebuilding data
```bash
python3 tools/analyze_audio.py
python3 tools/whisper_words.py assets/audio/song.mp3 data/whisper_words.json large-v3   # needs huggingface.co
python3 tools/align_whisper.py
python3 tools/prep_characters.py
python3 tools/build_fonts.py <dir with Shippori Mincho B1 / Dela Gothic One / Pretendard sources>
python3 tools/build_data.py
```

Fonts: Shippori Mincho B1, Dela Gothic One, and Pretendard, all under the SIL Open Font License. They are subset to the glyphs used.

Credits: 作詞・作曲 ろくろ / Vocal 暁山瑞希 / Movie meel
