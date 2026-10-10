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
  ctx.save(); roll(ctx, cr);
  if (MASK) { ctx.fillStyle = "#000"; ctx.fillRect(-200, -200, W + 400, H + 400); }
  else if (shot.dustBack) { drawDustBack(ctx, t, vp); drawKeyLight(ctx, vp, 0.5); }
  else { drawWall(ctx, shot, cr); if (shot.keyLight) drawKeyLight(ctx, vp); else drawLight(ctx, t, shot); }
  drawLayers(ctx, shot, cr, t);
  if (shot.thread) drawThread2(ctx, shot, cr, t);
  ctx.restore();
  if (!MASK) for (const f of shot.fx || []) FX[f](ctx, t - shot.t0, vp, shot);   // decoration above the character
  ctx.restore();
  return cr;
}

// ---------------------------------------------------------------- overlays above the character (neutral light only, no saturated colour)
const FX = {
  // warm-white light leak drifting in from an edge
  leak(ctx, u, vp, sh) {
    const side = sh.leakSide ?? 1, x = vp.x + (side > 0 ? vp.w * 0.92 : vp.w * 0.08) - side * 60 * Math.sin(u * 0.6), y = vp.y + vp.h * 0.25 + 40 * Math.sin(u * 0.4);
    const r = vp.w * 0.55, g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, "rgba(252,250,244,0.55)"); g.addColorStop(0.4, "rgba(250,247,240,0.18)"); g.addColorStop(1, "rgba(250,247,240,0)");
    ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = g; ctx.fillRect(vp.x, vp.y, vp.w, vp.h); ctx.restore();
  },
  // diagonal light beam crossing the figure
  beam(ctx, u, vp) {
    const p = vp.x - 500 + ((u * 160) % (vp.w + 1000)), w = 260;
    const g = ctx.createLinearGradient(p, 0, p + w, 0);
    g.addColorStop(0, "rgba(255,255,250,0)"); g.addColorStop(0.5, "rgba(255,255,250,0.22)"); g.addColorStop(1, "rgba(255,255,250,0)");
    ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = g;
    ctx.beginPath(); ctx.moveTo(p + 300, vp.y); ctx.lineTo(p + 300 + w, vp.y); ctx.lineTo(p + w - 200, vp.y + vp.h); ctx.lineTo(p - 200, vp.y + vp.h); ctx.fill(); ctx.restore();
  },
  // window-blind shadows sliding across
  blinds(ctx, u, vp) {
    ctx.save(); ctx.globalCompositeOperation = "multiply"; ctx.globalAlpha = 0.24;
    ctx.translate(vp.x + vp.w / 2, vp.y + vp.h / 2); ctx.rotate(-0.38); ctx.translate(-700, -700 + (u * 26) % 150);
    ctx.drawImage(A2.blinds, 0, 0); ctx.restore();
  },
  // floating dust + out-of-focus foreground specks
  dust(ctx, u, vp, sh) {
    const seed = Math.round(sh.t0 * 10);
    ctx.save(); ctx.globalCompositeOperation = "screen";
    for (let i = 0; i < 46; i++) {
      const big = i < 6, x = vp.x + ((hash(seed + i * 7) * vp.w + u * (hash(i * 3 + seed) - 0.5) * 40) % vp.w + vp.w) % vp.w;
      const y = vp.y + ((hash(seed + i * 13) * vp.h - u * (8 + hash(i) * 18)) % vp.h + vp.h) % vp.h;
      const r = big ? 26 + hash(i * 5 + seed) * 40 : 1.2 + hash(i * 11) * 2.6;
      ctx.globalAlpha = big ? 0.08 + hash(i * 17) * 0.08 : 0.35 + 0.35 * Math.sin(u * 2 + i);
      ctx.drawImage(A2.dot, x - r, y - r, r * 2, r * 2);
    }
    ctx.restore();
  },
  // haze rising from the bottom
  haze(ctx, u, vp) {
    const g = ctx.createLinearGradient(0, vp.y + vp.h, 0, vp.y + vp.h * 0.45);
    g.addColorStop(0, `rgba(245,245,240,${0.28 + 0.05 * Math.sin(u)})`); g.addColorStop(1, "rgba(245,245,240,0)");
    ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = g; ctx.fillRect(vp.x, vp.y, vp.w, vp.h); ctx.restore();
  },
  // thin flickering film scratches
  scratch(ctx, u, vp, sh) {
    const fr = Math.floor((sh.t0 + u) * 15);
    ctx.save(); ctx.fillStyle = "rgba(240,240,236,0.22)";
    for (let i = 0; i < 3; i++) if (hash2(fr, i) > 0.45) ctx.fillRect(vp.x + hash2(i, fr) * vp.w, vp.y, 1.2, vp.h);
    ctx.restore();
  },
};
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
  ctx.fillStyle = shot.dark ? "#5e6061" : shot.keyLight ? "#b4b6b8" : "#8a8c8d"; ctx.fillRect(-100, -100, W + 200, H + 200);       // wall_gray token
  ctx.save(); ctx.globalCompositeOperation = "overlay"; ctx.globalAlpha = 0.75;
  ctx.drawImage(img, dx, dy, 2400 * z, 1350 * z); ctx.restore();
}
function drawDustBack(ctx, t, vp) {
  // soft grey air (same tone range as the old wall), slightly uneven so it reads as space, not a flat card
  ctx.fillStyle = "#f5f5f3"; ctx.fillRect(vp.x - 200, vp.y - 200, vp.w + 400, vp.h + 400);   // bright air for contrast with the figure
  const g = ctx.createRadialGradient(vp.x + vp.w * 0.28, vp.y + vp.h * 0.15, 40, vp.x + vp.w * 0.28, vp.y + vp.h * 0.15, vp.w * 0.9);
  g.addColorStop(0, "rgba(255,255,250,0.22)"); g.addColorStop(1, "rgba(255,255,250,0)");
  ctx.fillStyle = g; ctx.fillRect(vp.x - 200, vp.y - 200, vp.w + 400, vp.h + 400);
  // three depths of dust: far = many/tiny/slow, mid, near = few/large/soft
  const layers = [[170, 1.4, 2.8, 5, 0.6], [80, 3.0, 5.5, 11, 0.5], [18, 10, 24, 22, 0.2]];   // dark dust on the bright air
  ctx.save(); ctx.globalCompositeOperation = "source-over";
  layers.forEach(([n, r0, r1, speed, a0], li) => {
    for (let i = 0; i < n; i++) {
      const k = i * 13 + li * 1000;
      const x = vp.x + (((hash(k + 1) * vp.w + t * speed * (hash(k + 2) - 0.3)) % vp.w) + vp.w) % vp.w;
      const y = vp.y - 40 + (((hash(k + 3) * (vp.h + 80) - t * speed * (0.4 + hash(k + 4))) % (vp.h + 80)) + vp.h + 80) % (vp.h + 80);
      const r = r0 + hash(k + 5) * (r1 - r0);
      ctx.globalAlpha = a0 * (0.55 + 0.45 * Math.sin(t * (0.6 + hash(k + 6)) + k));
      ctx.drawImage(A2.dotDark, x - r, y - r, r * 2, r * 2);
    }
  });
  ctx.restore();
}
function drawKeyLight(ctx, vp, soft = 1) { // soft light from the upper left, opposite side and bottom fall off
  const g = ctx.createLinearGradient(vp.x, vp.y, vp.x + vp.w * 0.9, vp.y + vp.h * 1.4);
  g.addColorStop(0, "rgba(255,255,250,0.30)"); g.addColorStop(0.45, "rgba(255,255,250,0)"); g.addColorStop(0.46, "rgba(0,0,0,0)"); g.addColorStop(1, `rgba(0,0,0,${0.38 * soft})`);
  ctx.save(); ctx.globalCompositeOperation = "soft-light"; ctx.fillStyle = g; ctx.fillRect(vp.x - 200, vp.y - 200, vp.w + 400, vp.h + 400); ctx.restore();
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
    if (shot.shadow !== false && !MASK) {
      const [sx, sy, sa] = shot.longShadow ? [300, 190, 0.36] : [110, 50, 0.4];
      ctx.globalAlpha = sa * (L.alpha ?? 1); ctx.drawImage(C.shadow, sx, sy, C.w * 1.03, C.h * 1.03);
    }
    // focus: blurred -> sharp (pull) or constant blur
    let sharp = shot.focus === "pull" ? sease((t - shot.t0 - 0.15) / 1.1) : shot.focus === "soft" ? 0 : shot.focus === "half" ? 0.3 : 1;
    if (shot.rack) sharp *= 1 - shot.rack * (0.5 + 0.5 * Math.sin(2 * Math.PI * (t - shot.t0) / 3.7 - Math.PI / 2));   // slow focus breathing
    if (sharp < 1) { ctx.globalAlpha = (L.alpha ?? 1) * (1 - sharp * 0.999); ctx.drawImage(C.blur, 0, 0, C.w, C.h); }
    if (sharp > 0) { ctx.globalAlpha = (L.alpha ?? 1) * sharp; ctx.drawImage(C.mono, 0, 0); }
    if (shot.keyLight) { ctx.globalAlpha = 0.5 * (L.alpha ?? 1); ctx.drawImage(C.rim, 0, 0); }       // rim light from behind, upper left
    if (MASK) {                                                                                      // measurement pass
      ctx.globalAlpha = 1; ctx.fillStyle = "#000"; ctx.drawImage(C.sil, 0, 0);
      if (MASK === 2) { const b = KP[L.n].eyeBox; ctx.fillStyle = "#f00"; ctx.fillRect(b[0] - 30, b[1] - 60, b[2] - b[0] + 60, b[3] - b[1] + 260); }
    }
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
R.letterbox_closeup = (ctx, sc, t) => {
  const sh = shotAt(sc, t);
  if (sh.black) { ctx.fillStyle = "#000"; ctx.fillRect(-100, -100, W + 200, H + 200); return { bars: sc.bars ?? 78, black: true }; }
  drawShot(ctx, sh, t); return { bars: sc.bars ?? 78 };
};
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
    { type: "letterbox_closeup", t0: 0, t1: 20.0, hud: false, bars: 264, vignette: 0.38, lightOverlay: true,
      shots: [
        { t0: 0, t1: 2.4, black: true, layers: [], c0: [0, 0, 1], c1: [0, 0, 1] },
        // upper body centre (garment + crossed arms), wall on both sides
        { t0: 2.4, t1: 7.3, tin: "bleed", layers: [P()], c0: [1150, 1480, 2560], c1: [1000, 1400, 2260], keyLight: true, dustBack: true, longShadow: true, r0: -0.8, r1: 0.6, focus: "pull", rack: 0.15 },
        // face, eyes visible
        { t0: 7.3, t1: 12.3, tin: "bleed", layers: [P()], c0: [990, 900, 1640], c1: [880, 860, 1400], keyLight: true, dustBack: true, longShadow: true, r0: 0.7, r1: -0.7, focus: "pull", rack: 0.15 },
        // second figure: chest and the clipboard held in both hands
        { t0: 12.3, t1: 17.0, tin: "bleed", layers: [N()], c0: [1160, 1600, 2120], c1: [1300, 1520, 1840], keyLight: true, dustBack: true, longShadow: true, r0: -0.7, r1: 0.7, focus: "pull", rack: 0.15 },
        // second figure: face (whip pan in)
        { t0: 17.0, t1: 20.0, tin: "whip", layers: [N()], c0: [1110, 890, 1600], c1: [1010, 860, 1420], keyLight: true, dustBack: true, longShadow: true, r0: 0.7, r1: -0.5, focus: "pull", rack: 0.15 },
      ],
      text: {
        1: { lvl: "A", layout: "vert", x: 1010, y: 345, size: 29, cols: ["僕は最上最愛の"], holdUntil: 2 },
        2: { lvl: "A", layout: "vert", x: 1010 - 29 * 1.3, y: 345, size: 29, gap: 1.3, cols: ["この世界に産み落とされた", "モンスター"] },
        3: { lvl: "A", layout: "vert", x: 1010, y: 345, size: 29, gap: 1.3, cols: ["そこは", "従順傀儡の"] },
        4: { lvl: "A", layout: "vert", x: 560, ink: "dark", y: 345, size: 29, gap: 1.3, cols: ["嫌な時代に", "振り落とされたもんだ"] },
        5: { lvl: "A", layout: "vert", x: 560, ink: "dark", y: 345, size: 29, gap: 1.3, cols: ["赤い糸を", "放ったスパイダー"] },
        6: { lvl: "A", layout: "vert", x: 860, y: 345, size: 29, cols: ["予想通り絡まるハンター"], holdUntil: 7 },
        7: { lvl: "A", layout: "vert", x: 860 - 29 * 1.3, y: 345, size: 29, gap: 1.3, cols: ["どうか", "一生淡々と"] },
        8: { lvl: "A", layout: "vert", x: 1290, y: 345, size: 29, gap: 1.3, cols: ["生きるだけの", "理由をください", "ドクター"] },
      } },
    { type: "title_card_shadow", t0: 20.0, t1: 34.14 },
    { type: "hud_portrait", t0: 34.14, t1: s(13),
      shots: [
        { t0: 34.14, t1: s(11), layers: [P()], c0: [1000, 1260, 2300], c1: [990, 1230, 2120], lightX: 200, fx: ["leak", "dust"] },
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
        { t0: 62.11, t1: s(21), layers: [P()], c0: [960, 1250, 1900], c1: [950, 1215, 1760], lightX: 600, fx: ["beam", "dust", "scratch"] },
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
let CV2, CX2, PX2 = 1, GRAIN = 0.07, FLICKER = 0.05;
function post(ctx, t) {
  // film grain: ~2 px clumps, new random offset every frame (part of the look in preview and final)
  const fr = Math.floor(t * 30), tile = A2.grain[fr % A2.grain.length];
  ctx.save(); ctx.globalCompositeOperation = "overlay"; ctx.globalAlpha = GRAIN;
  ctx.translate(-hash(fr) * 256, -hash(fr + 9) * 256);
  ctx.fillStyle = ctx.createPattern(tile, "repeat"); ctx.fillRect(0, 0, W, H); ctx.restore();
  if (!POST) return;
  // low-contrast bloom: tiny downscale, screen back
  const sm = A2.small, sx = sm.getContext("2d"); sx.globalCompositeOperation = "copy"; sx.drawImage(CV2, 0, 0, 240, 135);
  ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = 0.16; ctx.drawImage(sm, 0, 0, W, H); ctx.restore();
}
// ---- camera: smoothed value noise (deterministic), breathing scale, cut kick
function vnoise(x, seed) { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return (lerp(hash2(i, seed), hash2(i + 1, seed), u) - 0.5) * 2; }
let CUTS = [];
function handheld(t) {
  let dx = 4.4 * (vnoise(t * 0.8, 11) + 0.5 * vnoise(t * 1.4, 12));          // ~2 px std horizontally
  let dy = 5.6 * (vnoise(t * 0.7, 21) + 0.5 * vnoise(t * 1.3, 22));          // a little more vertically
  const r = 0.15 * vnoise(t * 0.4, 31) * Math.PI / 180;
  const s = 1.0075 + 0.0075 * Math.sin(2 * Math.PI * t / 3.0);                // breathing 1.000-1.015, 3 s period
  for (let i = 0; i < CUTS.length; i++) {                                     // impact shake right after each cut
    const dt = t - CUTS[i].t; if (dt < 0 || dt > 0.45) continue;
    const a = 18 * Math.exp(-dt * 14) * Math.cos(dt * 30), ang = hash(i * 7 + 3) * Math.PI * 2;
    dx += a * Math.cos(ang); dy += a * Math.sin(ang);
  }
  return { dx, dy, r, s };
}
// ---- transitions on the image layer only (8 frames at 30 fps centred on the cut)
const TR_HALF = 4 / 30;
function transitionAt(t) {
  for (const c of CUTS) { const u = (t - (c.t - TR_HALF)) / (2 * TR_HALF); if (u >= 0 && u < 1) return { kind: c.kind, u, from: c.from }; }
  return null;
}
function blitBlur(ctx, img, len, ang, alpha = 1) { // directional blur by averaging shifted copies
  const n = len < 2 ? 1 : 7;
  for (let i = 0; i < n; i++) {
    const o = n === 1 ? 0 : (i / (n - 1) - 0.5) * len;
    ctx.globalAlpha = alpha / (i + 1) * (n === 1 ? 1 : 1);
    ctx.drawImage(img, Math.cos(ang) * o, Math.sin(ang) * o, W, H);
  }
  ctx.globalAlpha = 1;
}
// ---- light overlay: blind bars + dust lit only inside the bars
const STRIPE_ANG = -20 * Math.PI / 180;
function stripeIntensity(x, y, flow) {
  const xr = (x - W / 2) * Math.cos(-STRIPE_ANG) - (y - H / 2) * Math.sin(-STRIPE_ANG) + 1500 - flow;
  const p = ((xr % 1500) + 1500) % 1500; let v = 0;
  for (const [c, w, b] of A2.stripes) for (const k of [-1500, 0, 1500]) { const d = (p - c - k) / (w * 0.5 + 60); v += b * Math.exp(-d * d); }
  return Math.min(1, v);
}
function drawLightOverlay(ctx, t) {
  const flow = (t * 60) % 1500, breathe = 1 + 0.2 * Math.sin(2 * Math.PI * t / 4.5);
  ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = 0.2 * breathe;
  ctx.translate(W / 2, H / 2); ctx.rotate(STRIPE_ANG); ctx.translate(-1500 + flow - 1500, -1500); ctx.drawImage(A2.stripeTex, 0, 0); ctx.restore();
  ctx.save(); ctx.globalCompositeOperation = "source-over";
  for (let i = 0; i < 24; i++) {                                             // fewer than the backdrop dust
    const big = i < 5;
    const x = ((hash(i * 3 + 1) * W + t * (hash(i) - 0.5) * (big ? 30 : 18)) % W + W) % W, y = ((hash(i * 5 + 2) * H - t * (big ? 10 : 4 + hash(i * 7) * 9)) % H + H) % H;
    const lit = stripeIntensity(x, y, flow);
    const r = big ? 26 + hash(i * 11) * 40 : 1.8 + hash(i * 11) * 3.6;
    ctx.globalAlpha = big ? 0.18 + 0.1 * lit : 0.55 + 0.25 * lit;
    ctx.drawImage(A2.dotMid, x - r, y - r, r * 2, r * 2);
  }
  ctx.restore();
}

let IMG, IX, MASK = 0;
function renderImage(t) { // the picture (wall, figure, light) without text/HUD
  const ctx = IX; ctx.setTransform(PX2, 0, 0, PX2, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over"; ctx.filter = "none";
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
  const sc = sceneAt(t);
  const info = (R[sc.type] || R.placeholder)(ctx, sc, t) || {};
  if (!info.black && sc.lightOverlay && !MASK) drawLightOverlay(ctx, t);
  return { sc, info };
}
function composeFrame(t, measure = false) {
  const ctx = CX2;
  const { sc, info } = renderImage(t);
  if (measure) {   // geometry only: same camera, no transitions/text/grain/overlays
    ctx.setTransform(PX2, 0, 0, PX2, 0, 0); ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
    const cam = handheld(t); ctx.save(); ctx.translate(W / 2 + cam.dx, H / 2 + cam.dy); ctx.rotate(cam.r); ctx.scale(cam.s * 1.035, cam.s * 1.035); ctx.translate(-W / 2, -H / 2);
    ctx.drawImage(IMG, 0, 0, W, H); ctx.restore(); drawBars(ctx, info.bars || 0); return;
  }
  ctx.setTransform(PX2, 0, 0, PX2, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over"; ctx.filter = "none";
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
  const cam = handheld(t), tr = transitionAt(t);
  ctx.save();
  ctx.translate(W / 2 + cam.dx, H / 2 + cam.dy); ctx.rotate(cam.r); ctx.scale(cam.s * 1.035, cam.s * 1.035); ctx.translate(-W / 2, -H / 2);  // 3.5 % overscan
  if (!tr) ctx.drawImage(IMG, 0, 0, W, H);
  else if (tr.kind === "whip") {          // horizontal blur + fast pan, no white; image scaled so no edge shows
    const u = tr.u, k = u < 0.5 ? sease(u * 2) : 1 - sease((u - 0.5) * 2), pan = (u < 0.5 ? -1 : 1) * 200 * k, z = 1 + 0.32 * k;
    ctx.save(); ctx.translate(W / 2 + pan, H / 2); ctx.scale(z, z); ctx.translate(-W / 2, -H / 2); blitBlur(ctx, IMG, 40 + 220 * k, 0); ctx.restore();
  } else {                                 // light bleed: exposure up + diagonal blur, peak near white, new shot resolves
    const u = tr.u, ang = -30 * Math.PI / 180;
    const blur = u < 3 / 8 ? lerp(40, 120, u / (3 / 8)) : u < 5 / 8 ? 120 : lerp(120, 0, (u - 5 / 8) / (3 / 8));
    blitBlur(ctx, IMG, blur, ang);
  }
  ctx.restore();
  INK_DARK = 0;
  if (tr && tr.kind !== "whip") {         // exposure curve: rises to near-white at frames 3-4, falls back on the new shot
    const u = tr.u, ex = u < 3 / 8 ? sease(u / (3 / 8)) * 0.88 : u < 5 / 8 ? 0.94 : (1 - sease((u - 5 / 8) / (3 / 8))) * 0.88;
    INK_DARK = clamp((ex - 0.35) / 0.5);
    ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = `rgba(250,249,244,${ex})`; ctx.fillRect(0, 0, W, H);
    if (u >= 3 / 8 && u < 5 / 8) { ctx.globalAlpha = 0.9; ctx.translate(W / 2, H / 2); ctx.rotate(STRIPE_ANG); ctx.translate(-3000 + (t * 60) % 1500, -1500); ctx.drawImage(A2.stripeTex, 0, 0); }
    ctx.restore();
  }
  // brightness breathing +-3 % (0.3 Hz) and +-1.5 % per-frame flicker on the picture
  // light flicker stepped at 15 fps like the reference (its picture mean jumps ~+-10 % between frames)
  const f = 0.02 * Math.sin(2 * Math.PI * 0.3 * t) + FLICKER * (hash(Math.floor(t * 15) + 77) - 0.5) * 2;
  ctx.fillStyle = f > 0 ? `rgba(255,255,255,${f})` : `rgba(0,0,0,${-f})`; ctx.fillRect(0, 0, W, H);
  // lyrics ride the camera at 40 % (parallax), never cut by transitions
  ctx.save(); ctx.translate(cam.dx * 0.4, cam.dy * 0.4);
  for (const [id, spec] of Object.entries(sc.text || {})) drawLyric(ctx, spec, L2(+id), t);
  ctx.restore();
  ctx.setTransform(PX2, 0, 0, PX2, 0, 0);
  ctx.globalAlpha = sc.vignette ?? 0.8; ctx.drawImage(A2.vignette, 0, 0, W, H); ctx.globalAlpha = 1;
  post(ctx, t);
  if (sc.hud !== false && R[sc.type]) drawHUD2(ctx, t, 1, info.drift || 0);
  drawBars(ctx, info.bars || 0);
  drawKo(ctx, t);
}
// final: 180-degree shutter = average of 3 samples across 1/60 s; preview: single sample
let SUBS = 1;
function render2(t) {
  if (SUBS === 1) return composeFrame(t);
  const acc = ACC, ax = acc.getContext("2d");
  for (let i = 0; i < SUBS; i++) {
    composeFrame(t + (i / (SUBS - 1) - 0.5) / 60);
    ax.globalAlpha = 1 / (i + 1); ax.globalCompositeOperation = "source-over"; ax.drawImage(CV2, 0, 0);
  }
  CX2.setTransform(1, 0, 0, 1, 0, 0); CX2.globalAlpha = 1; CX2.drawImage(acc, 0, 0);
}
let ACC;
async function init2(width = 960, opts = {}) {
  PX2 = width / W; POST = !!opts.post;
  CV2 = document.getElementById("c"); CV2.width = width; CV2.height = Math.round(H * PX2); CX2 = CV2.getContext("2d");
  await loadAssets2(); buildScenes();
  IMG = cnv(CV2.width, CV2.height); IX = IMG.getContext("2d"); ACC = cnv(CV2.width, CV2.height);
  SUBS = opts.post ? 3 : 1;
  CUTS = [];
  for (const sc of SCENES2) (sc.shots || []).forEach((sh, i) => { if (sh.tin) CUTS.push({ t: sh.t0, kind: sh.tin }); });
  return { fallbacks: A2.fontFallbacks, duration: D.duration };
}
window.init = init2;
// Mean luminance of figure / wall / face regions of the final picture at time t.
window.lumaStats = (t) => {
  const grab = () => CX2.getImageData(0, 0, CV2.width, CV2.height).data;
  composeFrame(t); const pic = grab();
  MASK = 1; composeFrame(t, true); const m1 = grab();
  MASK = 2; composeFrame(t, true); const m2 = grab(); MASK = 0;
  let fs = 0, fn = 0, ws = 0, wn = 0, cs = 0, cn = 0;
  const Wd = CV2.width, rowBar = [];
  for (let r = 0; r < CV2.height; r++) { let m = 0; for (let x = 0; x < Wd; x += 8) m += m1[(r * Wd + x) * 4 + 2]; rowBar.push(m / (Wd / 8) < 8 && (() => { let q = 0; for (let x = 0; x < Wd; x += 8) q += pic[(r * Wd + x) * 4]; return q / (Wd / 8) < 6; })()); }
  for (let i = 0; i < pic.length; i += 4) {
    const y = 0.299 * pic[i] + 0.587 * pic[i + 1] + 0.114 * pic[i + 2];
    const fig = m1[i] > 200 && m1[i + 1] > 200, face = fig && m2[i] > 200 && m2[i + 1] < 60, bar = rowBar[Math.floor(i / 4 / Wd)];
    if (face) { cs += y; cn++; } else if (fig) { fs += y; fn++; } else if (!bar) { ws += y; wn++; }
  }
  return { t, figure: fn ? +(fs / fn).toFixed(1) : null, wall: wn ? +(ws / wn).toFixed(1) : null, face: cn ? +(cs / cn).toFixed(1) : null };
};
window.seek = (t) => render2(t);
window.needsBlur = () => false;
window.stillTimes = () => [3.6, 8.9, 12.0, 16.2, 18.8, 36.3, 66.95, 81.6];
window.faceCheck = (times) => times.map((t) => { const sc = sceneAt(t); const sh = sc.shots && (sc.shots.find((s) => t >= s.t0 && t < s.t1)); return sh ? { t, eyes: eyeRects(sh, t) } : { t, eyes: [] }; });
