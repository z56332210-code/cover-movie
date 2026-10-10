// v2 engine: scenes from scene_plan.json (section/type only), re-timed to this song's lyrics.
// seek(t) draws everything from t alone. Preview and final share all logic; only resolution/fps/post differ.
"use strict";
const L2 = (i) => lyric(i);
// measured character landmarks in source pixels (2160x3840 art)
const KP = {
  patient: { eyes: [[826, 830], [964, 824]], eyeBox: [780, 770, 1010, 880], face: [910, 880] },
  nurse: { eyes: [[974, 826], [1110, 820]], eyeBox: [930, 765, 1160, 875], face: [1040, 880] },
};
const sease = (k) => 0.5 - 0.5 * Math.cos(Math.PI * clamp(k));

// ---------------------------------------------------------------- shot = layered crop of the art with a slow Ken Burns move
const FULL = { x: 0, y: 0, w: W, h: H };
function cropAt(shot, t, vp = FULL) {
  const k = sease((t - shot.t0) / (shot.t1 - shot.t0));
  const c = shot.c0.map((v, i) => lerp(v, shot.c1[i], k));
  const w = c[2], h = w * vp.h / vp.w, s = vp.w / w;
  // x0/y0 are expressed so that screen = (stage - x0) * s works inside the viewport
  return { x0: c[0] - w / 2 - vp.x / s, y0: c[1] - h / 2 - vp.y / s, w, h, s, k, vp, rot: lerp(shot.r0 || 0, shot.r1 || 0, k) * Math.PI / 180 };
}
function roll(ctx, cr) { const v = cr.vp || FULL, cx = v.x + v.w / 2, cy = v.y + v.h / 2; ctx.translate(cx, cy); ctx.rotate(cr.rot); ctx.translate(-cx, -cy); }
function drawShot(ctx, shot, t, vp = FULL) {
  const cr = cropAt(shot, t, vp);
  ctx.save();
  if (vp !== FULL) { ctx.beginPath(); ctx.rect(vp.x, vp.y, vp.w, vp.h); ctx.clip(); }
  roll(ctx, cr);
  drawWall(ctx, shot, cr); drawLight(ctx, t, shot); drawLayers(ctx, shot, cr, t);
  if (shot.thread) drawThread2(ctx, shot, cr, t);
  ctx.restore();
  return cr;
}
// thin red thread (kept from the demo): drawn progressively along the IV line on 赤い糸
function drawThread2(ctx, shot, cr, t) {
  const th = shot.thread, k = clamp((t - th.t0) / (th.t1 - th.t0));
  if (k <= 0) return;
  ctx.save(); ctx.scale(cr.s, cr.s); ctx.translate(-cr.x0, -cr.y0);
  ctx.strokeStyle = "rgba(179,18,43,0.9)"; ctx.lineWidth = 2.2 / cr.s * 1.4; ctx.lineCap = "round";
  ctx.beginPath(); const N = 60;
  for (let i = 0; i <= N * k; i++) {
    const u = i / N, x = (1 - u) ** 3 * th.p[0][0] + 3 * u * (1 - u) ** 2 * th.p[1][0] + 3 * u * u * (1 - u) * th.p[2][0] + u ** 3 * th.p[3][0];
    const y = (1 - u) ** 3 * th.p[0][1] + 3 * u * (1 - u) ** 2 * th.p[1][1] + 3 * u * u * (1 - u) * th.p[2][1] + u ** 3 * th.p[3][1];
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.stroke(); ctx.restore();
}
function drawWall(ctx, shot, cr) {
  const img = shot.dof ? A2.wallBlur : A2.wall;
  const z = 1.0 + 0.06 * cr.k, dx = -180 - 120 * cr.k * (shot.pan || 1), dy = -120;
  ctx.fillStyle = shot.dark ? "#6a6c6d" : "#8a8c8d"; ctx.fillRect(-100, -100, W + 200, H + 200);       // wall_gray token
  ctx.save(); ctx.globalCompositeOperation = "overlay"; ctx.globalAlpha = 0.75;
  ctx.drawImage(img, dx, dy, 2400 * z, 1350 * z); ctx.restore();
}
function drawLight(ctx, t, shot) { // diagonal light sliding across the wall
  const p = (t - shot.t0) * (shot.lightSpeed ?? 22) + (shot.lightX ?? 300);
  const g = ctx.createLinearGradient(p, 0, p + 520, -300);
  g.addColorStop(0, "rgba(0,0,0,0.28)"); g.addColorStop(0.35, "rgba(255,255,250,0.10)"); g.addColorStop(0.65, "rgba(255,255,250,0.10)"); g.addColorStop(1, "rgba(0,0,0,0.28)");
  ctx.save(); ctx.globalCompositeOperation = "soft-light"; ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); ctx.restore();
}
function drawLayers(ctx, shot, cr, t) {
  ctx.save(); ctx.scale(cr.s, cr.s); ctx.translate(-cr.x0, -cr.y0);
  for (const L of shot.layers) {
    const C = A2.ch[L.n], ox = L.ox || 0, oy = L.oy || 0;
    ctx.save(); ctx.translate(ox, oy);
    if (L.mirror) { ctx.translate(C.w, 0); ctx.scale(-1, 1); }
    if (L.flipV) { ctx.translate(0, C.h); ctx.scale(1, -1); }
    if (shot.shadow !== false) { ctx.globalAlpha = 0.55 * (L.alpha ?? 1); ctx.drawImage(C.shadow, 110, 50, C.w, C.h); }
    // focus: blurred -> sharp (pull) or constant blur
    const sharp = shot.focus === "pull" ? sease((t - shot.t0 - 0.15) / 1.1) : shot.focus === "soft" ? 0 : shot.focus === "half" ? 0.3 : 1;
    if (sharp < 1) { ctx.globalAlpha = (L.alpha ?? 1) * (1 - sharp * 0.999); ctx.drawImage(C.blur, 0, 0, C.w, C.h); }
    if (sharp > 0) { ctx.globalAlpha = (L.alpha ?? 1) * sharp; ctx.drawImage(C.mono, 0, 0); }
    ctx.restore();
  }
  ctx.restore();
}
function eyeRects(shot, t) { // screen-space eye boxes, used by the face-safety check
  const cr = cropAt(shot, t);
  return shot.layers.filter((L) => (L.alpha ?? 1) > 0.3).map((L) => {
    const b = KP[L.n].eyeBox, C = A2.ch[L.n], ox = L.ox || 0, oy = L.oy || 0;
    let [x0, y0, x1, y1] = b;
    if (L.mirror) [x0, x1] = [C.w - x1, C.w - x0];
    if (L.flipV) [y0, y1] = [C.h - y1, C.h - y0];
    return [(x0 + ox - cr.x0) * cr.s, (y0 + oy - cr.y0) * cr.s, (x1 + ox - cr.x0) * cr.s, (y1 + oy - cr.y0) * cr.s];
  });
}

// ---------------------------------------------------------------- scene renderers by type
const R = {};
const shotAt = (sc, t) => sc.shots.find((s) => t >= s.t0 && t < s.t1) || sc.shots[sc.shots.length - 1];
R.hud_portrait = (ctx, sc, t) => { const cr = drawShot(ctx, shotAt(sc, t), t); return { drift: cr.k * 40 }; };
R.giant_type = R.hud_portrait;
R.letterbox_closeup = (ctx, sc, t) => { drawShot(ctx, shotAt(sc, t), t); return { bars: 78 }; };
// left/right split: the right panel pushes in and shoves the left image aside
R.split_slide = (ctx, sc, t) => {
  const [left, right] = sc.shots, k = sease((t - sc.slideAt) / 0.7), div = lerp(W, W / 2, k);
  drawShot(ctx, left, t, { x: div - W, y: 0, w: W, h: H });
  ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = "rgba(255,255,255,0.06)"; ctx.fillRect(0, 0, div, H); ctx.restore(); // left a touch brighter
  if (k > 0) {
    drawShot(ctx, right, t, { x: div, y: 0, w: W / 2, h: H });
    ctx.fillStyle = "rgba(236,236,232,0.7)"; ctx.fillRect(div - 1, 0, 2, H);
  }
  return { bars: 78 };
};
R.red_burst = (ctx, sc, t) => {
  const shot = sc.shots[0], cr = cropAt(shot, t), k = (t - sc.t0) / (sc.t1 - sc.t0);
  ctx.fillStyle = "#050506"; ctx.fillRect(0, 0, W, H);
  // dust + bokeh (deterministic, slow drift)
  for (let i = 0; i < 170; i++) {
    const big = i < 26, x = hash(i * 3 + 7) * W + (t - sc.t0) * (hash(i) - 0.5) * 30, y = hash(i * 5 + 1) * H - (t - sc.t0) * (6 + hash(i * 7) * 10);
    const r = big ? 14 + hash(i * 11) * 30 : 1.5 + hash(i * 13) * 3.5;
    ctx.globalAlpha = big ? 0.10 + hash(i * 17) * 0.12 : 0.25 + hash(i * 19) * 0.5;
    ctx.drawImage(A2.dot, x - r, y - r, r * 2, r * 2);
  }
  ctx.globalAlpha = 1;
  // crimson smears spreading from the frame edges
  const grow = 0.85 + 0.3 * sease(k);
  [[1620, 330, 1250, 0, 1], [1800, 880, 900, 1, 0.95], [150, 170, 700, 2, 0.6]].forEach(([x, y, s, i, a]) => {
    const z = s * grow; ctx.globalAlpha = a; ctx.drawImage(A2.smear[i], x - z / 2, y - z / 2, z, z);
  });
  ctx.globalAlpha = 1;
  ctx.save(); roll(ctx, cr); ctx.globalAlpha = 0.9; drawLayers(ctx, shot, cr, t); ctx.restore();
  ctx.save(); ctx.globalCompositeOperation = "multiply"; ctx.fillStyle = "rgba(40,40,44,1)"; ctx.globalAlpha = 0.72; ctx.fillRect(0, 0, W, H); ctx.restore();
  return { drift: k * 30 };
};
R.placeholder = (ctx, sc, t) => { ctx.fillStyle = "#3a3b3c"; ctx.fillRect(0, 0, W, H); return {}; };

// ---------------------------------------------------------------- scene table (types from scene_plan.json, timed to this song)
let SCENES2;
function buildScenes() {
  const s = (i) => L2(i).start, e = (i) => L2(i).end;
  const P = (o = {}) => ({ n: "patient", ...o }), N = (o = {}) => ({ n: "nurse", ...o });
  SCENES2 = [
    { type: "letterbox_closeup", t0: 0, t1: s(8), hud: false,
      shots: [
        { t0: 0, t1: s(3), layers: [P()], c0: [900, 1490, 1450], c1: [905, 1445, 1300], lightX: -200 },
        { t0: s(3), t1: s(5), layers: [P()], c0: [870, 1105, 780], c1: [935, 1092, 700], focus: "pull", dof: true },
        { t0: s(5), t1: s(7), layers: [P()], c0: [1700, 760, 980], c1: [1640, 790, 880], lightX: 500,
          thread: { t0: s(5), t1: e(5), p: [[1478, 805], [1640, 690], [1820, 1000], [2200, 760]] } },
        { t0: s(7), t1: s(8), layers: [P()], c0: [895, 845, 720], c1: [900, 835, 620], focus: "pull", dof: true },
      ],
      text: {
        1: { lvl: "A", layout: "vert", x: 1640, y: 230, size: 40, cols: ["僕は", "最上最愛の"] },
        2: { lvl: "A", layout: "vert", x: 1660, y: 220, size: 38, cols: ["この世界に", "産み落とされた", "モンスター"] },
        3: { lvl: "A", layout: "line", x: 960, y: 900, size: 34 },
        4: { lvl: "A", layout: "line", x: 960, y: 900, size: 34 },
        5: { lvl: "A", layout: "vert", x: 1720, y: 230, size: 40, cols: ["赤い糸を", "放ったスパイダー"], red: "糸" },
        6: { lvl: "A", layout: "vert", x: 1720, y: 230, size: 40, cols: ["予想通り", "絡まるハンター"] },
        7: { lvl: "A", layout: "vert", x: 1760, y: 250, size: 38, cols: ["どうか", "一生淡々と"] },
      } },
    { type: "split_slide", t0: s(8), t1: 20.0, hud: false, slideAt: snapOnset(charT2(8, 13), 0.2),
      shots: [
        { t0: s(7), t1: 20.0, layers: [P()], c0: [895, 845, 720], c1: [905, 830, 650], dof: true, r0: -0.6, r1: 0.6 },
        { t0: s(8), t1: 20.0, layers: [N()], c0: [1042, 840, 600], c1: [1042, 835, 540], dof: true, r0: 0.8, r1: -0.4 },
      ],
      text: { 8: { lvl: "A", layout: "vert", x: 170, y: 150, size: 34, cols: ["生きるだけの", "理由をください", "ドクター"] } } },
    { type: "title_card_shadow", t0: 20.0, t1: 34.14 },
    { type: "hud_portrait", t0: 34.14, t1: s(13),
      shots: [
        { t0: 34.14, t1: s(11), layers: [P()], c0: [1000, 1260, 2300], c1: [990, 1230, 2120], lightX: 200 },
        { t0: s(11), t1: s(12), layers: [P()], c0: [905, 930, 1000], c1: [925, 920, 900], dof: true, dark: false },
        { t0: s(12), t1: s(13), layers: [P()], c0: [700, 1640, 1200], c1: [760, 1620, 1100], pan: -1 },
      ],
      text: {
        9: { lvl: "A", layout: "line", x: 1640, y: 505, size: 40, mirror: { x: 300, y: 560 } },
        10: { lvl: "A", layout: "vert", x: 1720, y: 250, size: 38, cols: ["この世界に", "産み落とされたモンスター"] },
        11: { lvl: "A", layout: "vert", x: 300, y: 260, size: 40, cols: ["そこは", "一見散漫な"], mirror: { x: 1620, y: 300 } },
        12: { lvl: "A", layout: "line", x: 960, y: 930, size: 36 },
      } },
    { type: "blur_focus_pull", t0: s(13), t1: s(17) },
    { type: "filmstrip", t0: s(17), t1: 61.3 },
    { type: "flash_cut_cluster", t0: 61.3, t1: 62.11 },
    { type: "giant_type", t0: 62.11, t1: s(22),
      shots: [
        { t0: 62.11, t1: s(21), layers: [P()], c0: [960, 1250, 1900], c1: [950, 1215, 1760], lightX: 600 },
        { t0: s(21), t1: s(22), layers: [P()], c0: [820, 1520, 1300], c1: [780, 1490, 1180], lightX: 900 },
      ],
      text: {
        20: { lvl: "B", x: 0, y: 500, rot: -5, size: 0.31 * H, weight: 300, red: "愛",
              rows: [{ t: "嗚呼", y: 300, scale: 0.55 }, { t: "人類最後に", x: 330, y: 300 }, { t: "愛を持ったって", x: 1190, y: 560 }] },
        21: { lvl: "B", x: -40, y: 300, rot: -7, size: 0.34 * H, weight: 300,
              rows: [{ t: "僕に居場所は", y: 300 }, { t: "ないでしょうか", x: 560, y: 590 }] },
      } },
    { type: "hud_portrait_n", t0: s(22), t1: s(23) },
    { type: "giant_type_n", t0: s(23), t1: s(25) },
    { type: "red_burst", t0: s(25), t1: 82.54, accent: 1,
      shots: [{ t0: s(25), t1: 82.54, layers: [P()], c0: [930, 1250, 1900], c1: [930, 1250, 2150], focus: "half", shadow: false }],
      text: { 25: { lvl: "A", layout: "line", x: 960, y: 930, size: 34 } } },
    { type: "white_flash_glitch", t0: 82.54, t1: s(26) },
    { type: "sunset_letterbox", t0: s(26), t1: s(28), accent: 2 },
    { type: "black_line", t0: s(28), t1: s(29) },
    { type: "mirror_flip", t0: s(29), t1: s(30) },
    { type: "kinetic_cluster", t0: s(30), t1: s(31) },
    { type: "hud_two_shot", t0: s(31), t1: s(33) },
    { type: "red_burst", t0: s(33), t1: s(35), accent: 3 },
    { type: "giant_type", t0: s(35), t1: s(36) },
    { type: "full_body_whiteout", t0: s(36), t1: e(36) },
    { type: "white_soft", t0: e(36), t1: s(37) },
    { type: "black_line", t0: s(37), t1: s(38) },
    { type: "hud_two_shot", t0: s(38), t1: s(40) },
    { type: "giant_type", t0: s(40), t1: e(40) },
    { type: "title_card_shadow", t0: e(40), t1: 142.3 },
    { type: "fade_out", t0: 142.3, t1: 143.4 },
  ];
  for (const sc of SCENES2) (sc.shots || []).forEach((sh, i) => {
    const d = (i + Math.round(sc.t0)) % 2 ? 1 : -1;
    if (sh.r0 === undefined) sh.r0 = 0.9 * d;
    if (sh.r1 === undefined) sh.r1 = -0.5 * d;
  });
  for (let i = 1; i < SCENES2.length; i++) if (SCENES2[i].type === SCENES2[i - 1].type) throw new Error("adjacent scenes share a type at " + SCENES2[i].t0);
  // every B/C row set must spell the lyric exactly
  for (const sc of SCENES2) for (const [id, sp] of Object.entries(sc.text || {}))
    if (sp.lvl === "B" && sp.rows.map((r) => r.t).join("") !== L2(+id).ja) throw new Error(`B rows for ${id} != lyric`);
}
function charT2(i, k) { const c = L2(i).chars; return c[Math.min(k, c.length - 1)]; }
const sceneAt = (t) => SCENES2.find((s) => t >= s.t0 && t < s.t1) || SCENES2[SCENES2.length - 1];

// ---------------------------------------------------------------- frame
let CV2, CX2, PX2 = 1;
function post(ctx, t) {
  if (!POST) return;
  // low-contrast bloom: tiny downscale, screen back
  const sm = A2.small, sx = sm.getContext("2d"); sx.globalCompositeOperation = "copy"; sx.drawImage(CV2, 0, 0, 240, 135);
  ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = 0.16; ctx.drawImage(sm, 0, 0, W, H); ctx.restore();
  ctx.drawImage(A2.vignette, 0, 0, W, H);
  ctx.save(); ctx.globalCompositeOperation = "overlay"; ctx.globalAlpha = 0.16;
  ctx.fillStyle = ctx.createPattern(A2.grain[Math.floor(t * 30) % A2.grain.length], "repeat"); ctx.fillRect(0, 0, W, H); ctx.restore();
}
function render2(t) {
  const ctx = CX2; ctx.setTransform(PX2, 0, 0, PX2, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over"; ctx.filter = "none";
  const sc = sceneAt(t);
  const info = (R[sc.type] || R.placeholder)(ctx, sc, t) || {};
  for (const [id, spec] of Object.entries(sc.text || {})) drawLyric(ctx, spec, L2(+id), t);
  ctx.setTransform(PX2, 0, 0, PX2, 0, 0);
  post(ctx, t);
  if (sc.hud !== false && R[sc.type]) drawHUD2(ctx, t, 1, info.drift || 0);
  drawBars(ctx, info.bars || 0);
  drawKo(ctx, t);
}
async function init2(width = 960, opts = {}) {
  PX2 = width / W; POST = !!opts.post;
  CV2 = document.getElementById("c"); CV2.width = width; CV2.height = Math.round(H * PX2); CX2 = CV2.getContext("2d");
  await loadAssets2(); buildScenes();
  return { fallbacks: A2.fontFallbacks, duration: D.duration };
}
window.init = init2;
window.seek = (t) => render2(t);
window.needsBlur = () => false;
window.stillTimes = () => [3.6, 8.9, 12.0, 16.2, 18.8, 36.3, 66.95, 81.6];
window.faceCheck = (times) => times.map((t) => { const sc = sceneAt(t); const sh = sc.shots && (sc.shots.find((s) => t >= s.t0 && t < s.t1)); return sh ? { t, eyes: eyeRects(sh, t) } : { t, eyes: [] }; });
