# スロウダウナー — lyric video (cover)

1920×1080 / 30 fps lyric video for YouTube. Everything is drawn by `web/index.html` (`seek(t)` draws one frame from `t` alone) and rendered with Playwright + ffmpeg.

## 노트북에서 최종본 렌더하기

### 1. 한 번만 준비
필요한 프로그램은 세 가지예요.
- **Node.js 18 이상:** https://nodejs.org
- **ffmpeg:** 명령어 창에서 `ffmpeg -version`이 실행돼야 해요.
  - macOS: `brew install ffmpeg`
  - Windows: `winget install ffmpeg`
- **Git**

```bash
git clone -b claude/utaite-lyric-video-m4afkj https://github.com/z56332210-code/cover-movie.git
cd cover-movie
npm install
npx playwright install chromium
```

### 2. 예상 시간 확인 (선택)
```bash
npm run bench
```
가장 무거운 구간 10프레임을 렌더해 보고, 이 노트북 기준 전체 예상 시간을 출력해요. 참고로 4코어 클라우드 머신에서는 21분 걸렸어요.

### 3. 최종 렌더
```bash
npm run render
```
- **결과물:** `out/final/slowdowner.mp4` (1920×1080, 30fps, H.264, AAC 320kbps, 약 420MB)
- **진행 상황:** `out/final/render.log`에 섹션별로 기록돼요.
- **중간에 꺼지거나 잠자기 모드가 됐을 때:** `npm run render`를 다시 실행하면 끝난 섹션은 건너뛰고 이어서 해요. 끝난 섹션 목록은 `out/final/manifest.json`에 있어요.
- **잠자기 방지:**
  - macOS: `caffeinate -i npm run render`
  - Windows: 전원 설정에서 "절전 모드: 안 함"(전원 연결 시)
- **CPU가 너무 뜨겁거나 메모리가 부족할 때:** 동시 작업 수를 줄여요. 예: `node tools/render.mjs --final --workers 2`

### 4. 싱크 확인 (선택, Python + numpy 필요)
```bash
python3 tools/verify_sync.py out/final/slowdowner.mp4
```
시작, 중간, 끝의 오디오 오프셋이 0ms면 정상이에요.

## Iterating
| Command | What |
|---|---|
| `npm run preview` | Whole song at 960×540, 30 fps → `out/preview/preview.mp4` |
| `node tools/render.mjs --sections outro` | Re-render only changed sections (preview), then re-concat |
| `node tools/render.mjs --range 130-140` | Short clip with audio |
| `npm run stills` / `node tools/render.mjs --final --stills --times 66.5,136.4` | Still frames |
| `npm run check` | Every lyric: no glyph on eyes/face, contrast under the text |
| `node tools/render.mjs --camspeed` / `--luma 9,14` | Camera speed per shot / figure-wall-face brightness |
| `python3 tools/motion.py <mp4>` / `python3 tools/measure.py <mp4>` | Motion, brightness, visible area, cut count (same method used on the reference) |

## Layout
| Path | What |
|---|---|
| `scene_plan.json`, `ref/` | Design source: scene types and reference frames |
| `data/lyrics.tsv` | Japanese / Korean lines (source of truth for displayed text) |
| `data/lyrics_timed.json` | Line and per-character sung times (Whisper large-v3 alignment + one manual fix) |
| `data/analysis.json`, `data/sections.json` | Beats, onsets, energy, section boundaries |
| `web/v2/engine.js` | Scene table, scene renderers, camera, transitions, post |
| `web/v2/text.js` | Japanese typography (A/B/C levels, fragment build) and the Korean subtitle band |
| `web/v2/hud.js` | HUD frame, geometric layer, title box |
| `tools/prep_v2.py` | Bakes concrete, desaturated art + backlight/rim layers, shadows, smears |
| `tools/render.mjs` | Chunked, parallel, resumable renderer |

Fonts: Noto Serif JP, Inter, and Pretendard, all under the SIL Open Font License. They are subset to the glyphs used.

Credits: 作詞・作曲 ろくろ / Vocal 暁山瑞希 / Movie meel
