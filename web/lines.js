// One typographic treatment per Japanese line. Text is split only at word/phrase boundaries.
// Coordinates are 1920x1080 scene space. Nothing may reach the subtitle band (y > 905).
"use strict";
const LINES = [
  // ---- A1: letterboxed, small vertical mincho on the right, restrained
  { id: 1, layout: "vert", x: 1560, y: 230, size: 54, weight: 400, enter: "fade", cols: ["僕は", "最上最愛の"] },
  { id: 2, layout: "vert", x: 1600, y: 200, size: 50, weight: 400, enter: "fade",
    cols: ["この世界に", "産み落とされた", [{ t: "モンスター", size: 76, weight: 800 }]],
    ghost: { t: "モンスター", vert: true, x: 1180, y: 540, size: 150, alpha: 0.06, weight: 800 } },
  { id: 3, layout: "vert", x: 1540, y: 250, size: 52, enter: "fade", cols: ["そこは", "従順傀儡の"] },
  { id: 4, layout: "vert", x: 1620, y: 200, size: 50, enter: "fade", cols: ["嫌な時代に", "振り落とされた", "もんだ"] },
  { id: 5, layout: "vert", x: 1580, y: 210, size: 58, weight: 700, enter: "fade",
    cols: [[{ t: "赤い糸", color: "red", size: 72, weight: 800 }, { t: "を" }], "放った", [{ t: "スパイダー", weight: 800 }]] },
  { id: 6, layout: "vert", x: 1560, y: 220, size: 56, weight: 700, enter: "pop", cols: ["予想通り", "絡まる", [{ t: "ハンター", size: 70, weight: 800 }]] },
  { id: 7, layout: "vert", x: 1520, y: 260, size: 46, enter: "fade", drift: -4, cols: ["どうか", "一生淡々と"] },
  { id: 8, layout: "vert", x: 1300, y: 180, size: 50, weight: 700, enter: "fade",
    cols: ["生きるだけの", "理由をください", [{ t: "ドクター", size: 84, weight: 800 }]] },

  // ---- A2: two-shot, horizontal centre column, mixed scales, tilted toward the speaker
  { id: 9, x: 930, y: 470, rot: -5, size: 64, enter: "fade",
    rows: [[{ t: "僕は" }], [{ t: "新旧曖昧", size: 132, weight: 800 }], [{ t: "な" }]],
    subs: [{ t: "新旧", x: 700, y: 250, size: 26, vert: true }, { t: "曖昧", x: 1210, y: 640, size: 26, vert: true }] },
  { id: 10, x: 960, y: 480, size: 56, enter: "fade",
    rows: [[{ t: "この世界に" }], [{ t: "産み落とされた", size: 74, weight: 700 }], [{ t: "モンスター", size: 128, weight: 800 }]],
    ghost: { t: "モンスター", x: 960, y: 520, size: 320, alpha: 0.07 } },
  { id: 11, x: 960, y: 470, size: 92, weight: 700, enter: "jitter", scatter: 0.35, rows: [[{ t: "そこは", size: 60 }], [{ t: "一見散漫な" }]] },
  { id: 12, x: 960, y: 470, size: 66, enter: "drop", springZ: 0.6, exit: "fall", exitDur: 0.3,
    rows: [[{ t: "手のひらから" }], [{ t: "振り落とされた", size: 96, weight: 800 }], [{ t: "ようだ" }]] },
  { id: 13, x: 960, y: 470, size: 64, enter: "slide", dir: 1, exit: "slideout", exitDur: 0.32,
    rows: [[{ t: "外側に放った" }], [{ t: "スライダー", size: 140, weight: 800 }]], speed: true },
  { id: 14, x: 960, y: 470, size: 62, enter: "pop", block: { rotFrom: -38, w: 13, z: 0.55 },
    rows: [[{ t: "予想通り" }], [{ t: "空振る", size: 150, weight: 800 }], [{ t: "バッター", size: 80, weight: 700 }]], swing: true },
  { id: 15, x: 960, y: 470, size: 58, tracking: 0.12, enter: "fade",
    rows: [[{ t: "ここは" }], [{ t: "心痛最大", size: 140, weight: 800, tracking: 0.02 }, { t: "の" }], [{ t: "すまし顔だ", size: 70 }]] },
  { id: 16, x: 1010, y: 470, rot: 6, size: 64, enter: "pop",
    rows: [[{ t: "薬", size: 170, weight: 800, color: "cyan" }, { t: "をください" }], [{ t: "ドクター", size: 120, weight: 800 }]] },

  // ---- Pre: black, film strip, jitter on the 16th grid
  { id: 17, x: 960, y: 760, size: 62, enter: "jitter", shake: 0.05, haloColor: "black",
    rows: [[{ t: "だから" }, { t: "ちんぷんかん", size: 92, weight: 800 }, { t: "な" }], [{ t: "呪文を唱えて", size: 76 }]] },
  { id: 18, x: 960, y: 760, size: 70, reveal: "sung", enter: "type", tracking: 0.18, rows: [[{ t: "指を咥えて" }], [{ t: "待っていたんだ", weight: 700 }]] },
  { id: 19, x: 960, y: 760, size: 64, enter: "jitter", shake: 0.09, exit: "glitch",
    rows: [[{ t: "とんちんかん", size: 100, weight: 800, color: "red" }, { t: "な" }], [{ t: "名前呼ばれたんだ" }]] },

  // ---- Chorus 1: warm, layered, cut-ins
  { id: 20, x: 960, y: 560, rot: -4, size: 90, enter: "stamp", reveal: "sung",
    rows: [[{ t: "嗚呼", size: 70, color: "red" }], [{ t: "人類最後に", size: 176, weight: 800 }], [{ t: "愛", size: 160, font: "dela", color: "red" }, { t: "を持ったって", size: 92, weight: 700 }]],
    ghost: { t: "人類最後", x: 960, y: 470, size: 420, alpha: 0.11, rot: -4, drift: -10 },
    subs: [{ t: "最後に", x: 330, y: 820, size: 28 }, { t: "愛を", x: 1630, y: 200, size: 28, vert: true }] },
  { id: 21, layout: "vert", x: 1500, y: 110, size: 68, enter: "pop", reveal: "sung",
    cols: [[{ t: "僕に" }, { t: "居場所は", size: 128, weight: 800 }], [{ t: "ないでしょうか", size: 70 }]],
    ghost: { t: "居場所", vert: true, x: 1170, y: 470, size: 260, alpha: 0.08 } },
  { id: 22, x: 560, y: 470, rot: 3, size: 80, enter: "pop", reveal: "sung",
    rows: [[{ t: "心中泣いて", size: 84, weight: 700 }], [{ t: "痛いから", size: 150, font: "dela", color: "red" }], [{ t: "思い出してよ", size: 108, weight: 800 }]] },
  { id: 23, x: 960, y: 560, rot: 4, size: 90, enter: "stamp", reveal: "sung",
    rows: [[{ t: "人類最後に", size: 176, weight: 800 }], [{ t: "愛", size: 160, font: "dela", color: "red" }, { t: "を持ったって", size: 92, weight: 700 }]],
    ghost: { t: "人類最後", x: 960, y: 470, size: 420, alpha: 0.11, rot: 4, drift: 10 } },
  { id: 24, x: 960, y: 520, skew: -10, size: 76, enter: "slide", dir: -1,
    rows: [[{ t: "それを知る日は" }], [{ t: "ないでしょう", size: 150, weight: 800 }], [{ t: "なんて", size: 60 }]] },
  { id: 25, x: 960, y: 470, size: 110, enter: "stamp", exit: "glitch", exitDur: 0.35, haloColor: "black",
    rows: [[{ t: "今日を", size: 84, weight: 700 }, { t: "くらった", size: 170, font: "dela", color: "red" }]] },

  // ---- C: navy, vertical, restrained then building
  { id: 26, layout: "vert", x: 1080, y: 170, size: 64, enter: "fade", reveal: "sung",
    cols: ["有終最後の", [{ t: "火", size: 120, weight: 800, color: "orange" }, { t: "を灯したって" }]] },
  { id: 27, layout: "vert", x: 1040, y: 200, size: 56, enter: "fade", drift: 3, cols: ["心苦しく", "なるでしょうか"] },
  { id: 28, x: 960, y: 520, size: 70, enter: "rise", reveal: "sung",
    rows: [[{ t: "本当は" }, { t: "咲いて", size: 130, weight: 800 }, { t: "みたいってこと" }], [{ t: "思い出したんだ", size: 96, weight: 700 }]] },
  { id: 29, x: 960, y: 500, size: 74, enter: "pop", reveal: "sung",
    rows: [[{ t: "たどり着いたんだ" }], [{ t: "正体", size: 150, weight: 800 }, { t: "と" }, { t: "擬態", size: 150, weight: 800 }, { t: "した" }], [{ t: "アイ", size: 130, font: "dela", color: "red" }, { t: "を" }]] },

  // ---- Chorus 2: maximal, split converging
  { id: 30, x: 960, y: 560, rot: -4, size: 90, enter: "stamp", reveal: "sung",
    rows: [[{ t: "嗚呼", size: 70, color: "red" }], [{ t: "人類最後に", size: 176, weight: 800 }], [{ t: "アイ", size: 160, font: "dela", color: "red" }, { t: "を持ったって", size: 92, weight: 700 }]],
    ghost: { t: "人類最後", x: 960, y: 470, size: 420, alpha: 0.12, rot: -4, drift: -12 } },
  { id: 31, layout: "vert", x: 1060, y: 130, size: 80, enter: "pop", reveal: "sung",
    cols: [[{ t: "僕の" }, { t: "印", size: 170, weight: 800, color: "red" }, { t: "は" }], [{ t: "ないでしょうか", size: 72 }]] },
  { id: 32, x: 960, y: 520, rot: -3, size: 64, enter: "pop", reveal: "sung",
    rows: [[{ t: "きっと" }, { t: "ふさわしくないけど", size: 78, weight: 700 }], [{ t: "思い出してよ", size: 160, weight: 800 }]] },
  { id: 33, x: 960, y: 500, size: 80, enter: "stamp", reveal: "sung",
    rows: [[{ t: "九十九回", size: 190, font: "dela" }], [{ t: "一人で泣いたって", size: 84, weight: 700 }]],
    ghost: { t: "九十九回", x: 960, y: 430, size: 260, alpha: 0.09, font: "dela", echo: 6, echoStep: 46 } },
  { id: 34, x: 960, y: 520, skew: 8, size: 80, enter: "slide", dir: 1, rows: [[{ t: "次の一つは" }], [{ t: "ないでしょう", size: 150, weight: 800 }]] },
  { id: 35, x: 960, y: 640, size: 80, enter: "pop", reveal: "sung",
    rows: [[{ t: "やっと" }], [{ t: "僕を見つけたんだ", size: 136, weight: 800 }], [{ t: "嗚呼", size: 110, color: "red", weight: 800 }]] },
  { id: 36, x: 960, y: 520, size: 80, enter: "pop", exit: "blow", exitDur: 0.5, reveal: "sung",
    rows: [[{ t: "こうやって" }], [{ t: "アイ", size: 150, font: "dela", color: "red" }, { t: "は" }, { t: "終わった", size: 150, weight: 800 }]] },

  // ---- Outro: clean, small, no effects
  { id: 37, x: 960, y: 800, size: 60, enter: "fade", reveal: "sung", halo: false, rows: [[{ t: "see you " }, { t: "最愛な", size: 96, weight: 700 }]] },
  { id: 38, x: 960, y: 790, size: 54, enter: "fade", reveal: "sung", halo: false, rows: [[{ t: "この世界に産み落とされた" }], [{ t: "モンスター", size: 92, weight: 700 }]] },
  { id: 39, x: 960, y: 790, size: 56, enter: "fade", reveal: "sung", halo: false, rows: [[{ t: "僕は人生最大の" }], [{ t: "したり顔で", size: 100, weight: 700 }]] },
  { id: 40, x: 960, y: 790, size: 60, enter: "fade", reveal: "sung", halo: false, exitDur: 0.6, rows: [[{ t: "今この世界と" }], [{ t: "一つになった。", size: 110, weight: 800 }]] },
];
for (const d of LINES) d.ja = lyric(d.id).ja;
