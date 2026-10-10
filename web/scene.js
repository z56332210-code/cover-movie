// Scene composition. seek(t) draws one complete frame from t alone (no carried state).
"use strict";

const L = (i) => lyric(i);
const S = (n) => section(n);
// sung time of the k-th character of line i
const charT = (i, k) => L(i).chars[Math.min(k, L(i).chars.length - 1)];

// ---------------------------------------------------------------- key times (measured)
const T = {};
function buildTimes() {
  T.open = snapOnset(L(8).end, 0.3);                // letterbox opens after "ドクター"
  T.doctor = snapOnset(charT(8, 13), 0.2);           // nurse silhouette appears on ド of ドクター
  T.title = snapOnset(23.75, 0.3);
  T.hud = snapOnset(25.0, 0.3);
  T.reveal = snapOnset(29.94, 0.3);
  T.a2 = S("A2").start;
  T.pre = L(17).start;
  T.ch1 = snapOnset(S("chorus1").start, 0.2);
  T.c = S("inter2").start;
  T.ch2 = snapOnset(L(30).start, 0.25);
  T.climax = snapOnset(charT(35, 9), 0.4, 0.3);      // 嗚呼 at the end of line 35
  T.white = L(36).end - 0.35;
  T.outro = L(37).start;
  T.color = L(40).start + 0.2;
  T.end = L(40).end;
}

// ---------------------------------------------------------------- palettes
const PAL = {
  cool: { bg: hex("#c9cdd0"), fg: hex("#15171a"), tex: 0.55, light: true },
  dark: { bg: hex("#0b0c0f"), fg: hex("#eceff1"), tex: 0.18, light: false },
  sepia: { bg: hex("#d6c6af"), fg: hex("#1c1410"), tex: 0.6, light: true },
  navy: { bg: hex("#0d1526"), fg: hex("#e4edf5"), tex: 0.15, light: false },
  white: { bg: hex("#f6f4f0"), fg: hex("#2a2928"), tex: 0.25, light: true },
  paper: { bg: hex("#e3e0da"), fg: hex("#1f1e1c"), tex: 0.45, light: true },
};
let PAL_KEYS;
function buildPalettes() {
  PAL_KEYS = [
    [0, "cool", 0], [T.pre - 0.15, "dark", 0.3], [T.ch1, "sepia", 0], [L(25).start, "dark", 0],
    [T.c, "navy", 1.2], [T.ch2, "sepia", 0], [T.white, "white", 0.35], [T.outro + 2, "paper", 4],
  ];
}
function paletteAt(t) {
  let cur = PAL[PAL_KEYS[0][1]];
  for (let i = 1; i < PAL_KEYS.length; i++) {
    const [kt, name, dur] = PAL_KEYS[i];
    if (t < kt) break;
    const k = dur > 0 ? smooth((t - kt) / dur) : 1, nx = PAL[name];
    cur = { bg: mixc(cur.bg, nx.bg, k), fg: mixc(cur.fg, nx.fg, k), tex: lerp(cur.tex, nx.tex, k), light: k > 0.5 ? nx.light : cur.light };
  }
  return cur;
}

// ---------------------------------------------------------------- character drawing
const TWO = { px: 520, nx: 1400, y: 330, s: 0.62 };
function bodyToScreen(name, o, bx, by) {
  const m = ASSETS.char[name].meta.body;
  return [o.x + (o.mirror ? -1 : 1) * (bx - m.face[0]) * o.s, o.y + (by - m.face[1]) * o.s];
}
function drawBody(ctx, name, o) {
  if (o.alpha <= 0.003) return;
  const A = ASSETS.char[name], m = A.meta.body;
  ctx.save();
  ctx.translate(o.x, o.y); if (o.mirror) ctx.scale(-1, 1);
  const dx = -m.face[0] * o.s, dy = -m.face[1] * o.s, w = m.w * o.s, h = m.h * o.s;
  const blur = clamp(o.blur || 0), sil = clamp(o.sil || 0), sat = clamp(o.sat ?? 0.4);
  if (blur > 0) { ctx.globalAlpha = o.alpha * blur; ctx.drawImage(A.blurGray, dx, dy, w, h); }
  const sharp = o.alpha * (1 - blur);
  if (sharp > 0.003) {
    if (sil < 1) {
      ctx.globalAlpha = sharp * (1 - sil); ctx.drawImage(A.bodyGray, dx, dy, w, h);
      if (sat > 0.01) { ctx.globalAlpha = sharp * (1 - sil) * sat; ctx.drawImage(A.body, dx, dy, w, h); }
    }
    if (sil > 0) { ctx.globalAlpha = sharp * sil; ctx.drawImage(o.silLight ? A.silLight : A.silDark, dx, dy, w, h); }
  }
  ctx.restore();
}
function drawFace(ctx, name, o) { // close-up cut-in
  if (o.alpha <= 0.003) return;
  const A = ASSETS.char[name], m = A.meta.face;
  ctx.save(); ctx.translate(o.x, o.y); if (o.mirror) ctx.scale(-1, 1);
  const dx = -m.face[0] * o.s, dy = -m.face[1] * o.s, w = m.w * o.s, h = m.h * o.s;
  ctx.globalAlpha = o.alpha; ctx.drawImage(A.faceGray, dx, dy, w, h);
  if (o.sat > 0.01) { ctx.globalAlpha = o.alpha * o.sat; ctx.drawImage(A.face, dx, dy, w, h); }
  ctx.restore();
}
const HAND = { patient: [43, 857], nurse: [496, 593], heart: [180, 640], ivbag: [597, 208] };

// ---------------------------------------------------------------- tracks (pure functions of t)
let TR;
function buildTracks() {
  TR = {
    // A1 -> two-shot reframe of the patient
    pX: track(640, [[T.open, TWO.px, { w: 3.2, z: 1 }], [L(29).start, TWO.px, {}]]),
    pS: track(0.95, [[T.open, TWO.s, { w: 3.2, z: 1 }]]),
    pY: track(370, [[T.open, TWO.y, { w: 3.2, z: 1 }]]),
    pSil: track(0, [[T.open + 0.3, 0.85, { w: 4, z: 1 }], [T.reveal, 0, { w: 5, z: 1 }]]),
    nAlpha: track(0, [[T.doctor, 0.85, { w: 9, z: 0.9 }], [T.reveal, 1, { w: 6, z: 1 }]]),
    nX: track(1650, [[T.open, TWO.nx, { w: 3.2, z: 1 }], [L(29).start + 0.2, TWO.px, { w: 3.5, z: 1 }], [L(30).start, TWO.nx, { cut: true }]]),
    nS: track(0.8, [[T.open, TWO.s, { w: 3.2, z: 1 }]]),
    nSil: track(1, [[T.reveal, 0, { w: 5, z: 1 }]]),
    sat: track(0.4, [[T.ch1, 0.55, { cut: true }], [L(25).start, 0.4, { cut: true }], [T.c, 0.3, { w: 2 }], [T.ch2, 0.62, { cut: true }],
                     [T.white, 0.35, { cut: true }], [T.color, 1.0, { w: 2.6, z: 1 }]]),
    mirror: track(0, [[L(29).start + 0.2, 0.5, { w: 3.5, z: 1 }], [T.ch2, 0, { cut: true }]]),
    // chorus 2 converging split: gap width and character offset from centre
    gap: track(160, [[L(31).start, 120, {}], [L(32).start, 90, {}], [L(33).start, 60, {}], [L(34).start, 30, {}], [L(35).start, 0, { w: 5, z: 1 }]]),
    off: track(440, [[L(33).start, 330, { w: 6, z: 0.9 }], [L(34).start, 210, { w: 6, z: 0.9 }], [L(35).start, 0, { w: 4.2, z: 1 }]]),
    // outro: nurse dissolves into the patient
    nDissolve: track(0.55, [[L(38).start, 0.32, { w: 2, z: 1 }], [L(39).start, 0.12, { w: 2, z: 1 }], [L(40).start, 0, { w: 3, z: 1 }]]),
    outroZoom: track(1.0, [[T.outro, 0.92, { w: 0.5, z: 1 }]]),
    letterbox: track(1, [[T.open, 0, { w: 5, z: 1 }]]),
  };
}

// ---------------------------------------------------------------- event lists (all on measured onsets)
let EV;
function buildEvents() {
  const lineStarts = (ids) => ids.map((i) => snapOnset(L(i).start, 0.12));
  const hard = (a, b, minS) => onsetsIn(a, b, minS).map((o) => o.t);
  EV = {
    flash: [T.a2, T.ch1, ...lineStarts([20, 21, 22, 23, 25, 30, 31, 32, 33, 35]), T.climax],
    ca: [...hard(T.pre, S("inter2").start, 0.62), ...hard(T.ch2, T.white, 0.6), T.ch1, T.ch2],
    glitch: [[T.ch1, 0.18], [L(19).end - 0.22, 0.22], [L(25).start, 0.12], [L(25).end - 0.35, 0.35], [T.ch2, 0.15]],
    speed: [[L(13).end - 0.32, 0.36, "h"], [L(14).start, 0.4, "h"], [T.ch1, 0.42, "r"], [snapOnset(L(20).start, 0.12), 0.35, "r"],
            [T.ch2, 0.42, "r"], [snapOnset(L(30).start, 0.12), 0.35, "r"], [T.climax, 0.6, "r"]],
    pops: [...hard(T.ch1, S("inter2").start, 0.5), ...hard(T.ch2, T.white, 0.5)].map((t) => [t, 0.022])
      .concat(lineStarts([9, 10, 11, 12, 13, 14, 15, 16]).map((t) => [t, 0.012]))
      .concat([[T.a2, 0.04], [T.ch1, 0.08], [T.ch2, 0.08], [T.climax, 0.06]]),
  };
}
const sumImpulse = (list, t, decay) => list.reduce((acc, et) => acc + impulse(t - et, decay), 0);
function needsBlur(t) { return EV.speed.some(([st, d]) => t >= st && t < st + Math.min(d, 0.25)); }

// ---------------------------------------------------------------- camera
function camera(t) {
  let z = 1, x = 0, y = 0, r = 0;
  if (t < T.open) z = 1 + 0.07 * smooth(t / T.open);
  else if (t < T.a2) z = 1 + 0.04 * smooth((t - (T.a2 - 1.8)) / 1.8);
  else if (t < T.pre) { z = 1.0 + 0.01 * Math.sin((t - T.a2) * 0.4); x = 6 * Math.sin((t - T.a2) * 0.21); }
  else if (t < T.ch1) z = 1 + 0.05 * smooth((t - T.pre) / (T.ch1 - T.pre));
  else if (t < T.c) { r = -0.006 * Math.sin((t - T.ch1) * 0.5); z = 1.02; }
  else if (t < T.ch2) { z = 1.02 + 0.03 * smooth((t - T.c) / (T.ch2 - T.c)); y = 6 * Math.sin((t - T.c) * 0.35); }
  else if (t < T.white) { z = 1.03; r = 0.005 * Math.sin((t - T.ch2) * 0.6); }
  else z = TR.outroZoom(t);
  for (const [et, amp] of EV.pops) z += amp * impulse(t - et, 8);
  return { z, x, y, r };
}
function applyCam(ctx, c, depth = 1) {
  const z = 1 + (c.z - 1) * depth;
  ctx.translate(W / 2, H / 2); ctx.scale(z, z); ctx.rotate(c.r * depth); ctx.translate(-W / 2 + c.x * depth, -H / 2 + c.y * depth);
}

// ---------------------------------------------------------------- background layers
function drawBackground(ctx, t, pal) {
  ctx.fillStyle = rgb(pal.bg); ctx.fillRect(-60, -60, W + 120, H + 120);
  ctx.save();
  ctx.globalCompositeOperation = pal.light ? "multiply" : "screen";
  ctx.globalAlpha = pal.tex * (pal.light ? 1 : 0.6);
  ctx.drawImage(ASSETS.paper, -40, -30, W + 80, H + 60);
  ctx.restore();
  // window light (inter1 + A2)
  const wl = 0.32 * env(t, T.open, T.pre, 1.5, 1.0);
  if (wl > 0) {
    ctx.save(); ctx.globalAlpha = wl; ctx.globalCompositeOperation = "soft-light";
    ctx.drawImage(ASSETS.window, (t - T.open) * 9 - 200, 0); ctx.restore();
  }
  // starfield (C): fixed seeded stars, twinkle follows the energy curve
  const sf = env(t, T.c, T.ch2, 1.2, 0.05);
  if (sf > 0) {
    const e = energyAt(t);
    for (let i = 0; i < 140; i++) {
      const x = hash(i * 3 + 1) * W, y0 = hash(i * 3 + 2) * H, sp = 4 + hash(i * 7) * 14;
      const y = ((y0 - (t - T.c) * sp) % H + H) % H;
      const tw = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * (1 + hash(i) * 3) + i)) * (0.6 + 0.4 * e);
      const r = 0.8 + hash(i * 11) * 1.8;
      ctx.fillStyle = `rgba(220,232,255,${sf * tw * 0.8})`; ctx.fillRect(x, y, r, r);
    }
  }
}

// ---------------------------------------------------------------- characters per section
function drawCharacters(ctx, t, pal) {
  const sat = TR.sat(t);
  if (t < T.pre) { // A1, inter1, A2
    const pBlur = t < T.open ? 1 - smooth(t / 9) : 0;
    drawBody(ctx, "nurse", { x: TR.nX(t), y: TWO.y, s: TR.nS(t), alpha: TR.nAlpha(t), sil: TR.nSil(t), sat });
    drawBody(ctx, "patient", { x: TR.pX(t), y: TR.pY(t), s: TR.pS(t), alpha: clamp(t / 0.6), blur: pBlur, sil: TR.pSil(t), sat });
    // cyan IV bag accent on 薬
    const l16 = L(16), k = env(t, l16.start, l16.end, 0.2, 0.3);
    if (k > 0) {
      const [bx, by] = bodyToScreen("patient", { x: TR.pX(t), y: TR.pY(t), s: TR.pS(t) }, ...HAND.ivbag);
      ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = 0.7 * k;
      ctx.drawImage(ASSETS.glow.white, bx - 110, by - 110, 220, 220);
      ctx.fillStyle = rgb(ACCENT.cyan, 0.35 * k); ctx.globalCompositeOperation = "multiply"; ctx.fillRect(bx - 50, by - 70, 100, 140);
      ctx.restore();
    }
    return;
  }
  if (t < T.ch1) { drawFilmStrip(ctx, t); return; }
  if (t < T.c) { drawChorus1(ctx, t, sat); return; }
  if (t < T.ch2) { // C: floating, dim; nurse mirrors onto the patient on 正体と擬態した
    const fl = (k) => 8 * Math.sin((t - T.c) * 0.7 + k);
    const m = TR.mirror(t);
    drawBody(ctx, "patient", { x: TWO.px, y: TWO.y + fl(0), s: TWO.s, alpha: 0.6, sat });
    drawBody(ctx, "nurse", { x: TR.nX(t), y: TWO.y + fl(2), s: TWO.s, alpha: 0.6 - m * 0.3, sat, mirror: m > 0.25 });
    return;
  }
  if (t < T.white) { drawChorus2(ctx, t, sat); return; }
  // inter3 + outro + end: merged figure at centre
  const o = { x: 960, y: TWO.y + 10, s: TWO.s };
  if (t < T.outro) {
    const pulse = sumImpulse(onsetsIn(T.white, T.outro, 0.4).map((x) => x.t), t, 6) * 0.15;
    drawBody(ctx, "nurse", { ...o, x: o.x + 30, alpha: 0.45 + pulse, blur: 0.5, sat });
    drawBody(ctx, "patient", { ...o, x: o.x - 30, alpha: 0.55 + pulse, blur: 0.5, sat });
  } else {
    const nd = TR.nDissolve(t);
    drawBody(ctx, "patient", { ...o, alpha: 1, sat });
    drawBody(ctx, "nurse", { ...o, alpha: nd, sat });
  }
}

function drawFilmStrip(ctx, t) { // pre-chorus: panels multiply line by line
  const line = t < L(18).start ? 0 : t < L(19).start ? 1 : 2;
  const rows = line === 2 ? [[300, 0.75, 1], [560, 0.75, -1]] : [[420, line ? 0.85 : 1, 1]];
  const pw0 = 480, ph0 = 270, gap = 36;
  for (const [cy, sc, dir] of rows) {
    const pw = pw0 * sc, ph = ph0 * sc, step = pw + gap, speed = (line === 0 ? 170 : line === 1 ? 240 : 330) * dir;
    const n = Math.ceil(W / step) + 2, shift = ((t - T.pre) * speed) % step;
    for (let i = -1; i < n; i++) {
      const x = i * step - shift, k = (i + Math.floor((t - T.pre) * speed / step) + (dir < 0 ? 1 : 0)) & 1;
      const name = k ? "nurse" : "patient";
      ctx.save();
      ctx.beginPath(); ctx.rect(x, cy - ph / 2, pw, ph); ctx.clip();
      ctx.fillStyle = "#16171a"; ctx.fillRect(x, cy - ph / 2, pw, ph);
      drawFace(ctx, name, { x: x + pw / 2, y: cy + ph * 0.05, s: 0.42 * sc, alpha: 0.9, sat: 0.25 });
      ctx.restore();
      ctx.strokeStyle = "rgba(235,238,240,0.55)"; ctx.lineWidth = 1.5; ctx.strokeRect(x + 0.5, cy - ph / 2 + 0.5, pw - 1, ph - 1);
    }
    ctx.fillStyle = "rgba(235,238,240,0.35)"; // sprocket ticks
    for (let x = -((t - T.pre) * speed % 40) - 40; x < W + 40; x += 40) { ctx.fillRect(x, cy - ph / 2 - 22, 16, 8); ctx.fillRect(x, cy + ph / 2 + 14, 16, 8); }
  }
}

function drawChorus1(ctx, t, sat) {
  const ls = (i) => snapOnset(L(i).start, 0.12);
  if (t < ls(20)) { // diagonal red / navy split (reference) on the chorus hit
    const k = spring(t - T.ch1, 18, 0.85), sx = 960 + (1 - k) * 400;
    ctx.save(); ctx.beginPath(); ctx.moveTo(-60, -60); ctx.lineTo(sx + 260, -60); ctx.lineTo(sx - 260, H + 60); ctx.lineTo(-60, H + 60); ctx.closePath();
    ctx.fillStyle = "#1b2740"; ctx.fill(); ctx.clip();
    drawBody(ctx, "patient", { x: 700, y: 360, s: 0.8, alpha: 1, sat: 0.3 });
    ctx.globalCompositeOperation = "multiply"; ctx.fillStyle = "rgba(60,90,140,0.55)"; ctx.fillRect(-60, -60, W + 120, H + 120);
    ctx.restore();
    ctx.save(); ctx.beginPath(); ctx.moveTo(sx + 260, -60); ctx.lineTo(W + 60, -60); ctx.lineTo(W + 60, H + 60); ctx.lineTo(sx - 260, H + 60); ctx.closePath();
    ctx.fillStyle = "#6e1620"; ctx.fill(); ctx.clip();
    drawBody(ctx, "nurse", { x: 1280, y: 360, s: 0.8, alpha: 1, sat: 0.3 });
    ctx.globalCompositeOperation = "multiply"; ctx.fillStyle = "rgba(200,40,50,0.5)"; ctx.fillRect(-60, -60, W + 120, H + 120);
    ctx.restore();
    ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(sx + 260, -60); ctx.lineTo(sx - 260, H + 60); ctx.stroke();
    return;
  }
  if (t >= L(25).start) return; // 今日をくらった: black, text only
  const shot = t < ls(21) ? "two" : t < ls(22) ? "pFace" : t < ls(23) ? "nFace" : "two";
  if (shot === "two") {
    const wide = t >= ls(24) ? 0.92 : 1;
    drawBody(ctx, "patient", { x: 960 - 440 * wide, y: TWO.y, s: TWO.s * (2 - wide), alpha: 1, sat });
    drawBody(ctx, "nurse", { x: 960 + 440 * wide, y: TWO.y, s: TWO.s * (2 - wide), alpha: 1, sat });
  } else {
    const st = shot === "pFace" ? ls(21) : ls(22), push = 1 + 0.05 * clamp((t - st) / 3);
    if (shot === "pFace") drawFace(ctx, "patient", { x: 640, y: 430, s: 1.0 * push, alpha: 1, sat });
    else drawFace(ctx, "nurse", { x: 1300, y: 430, s: 1.0 * push, alpha: 1, sat });
  }
}

function drawChorus2(ctx, t, sat) {
  const ls = (i) => snapOnset(L(i).start, 0.12);
  const g = Math.max(0, TR.gap(t)), off = TR.off(t);
  const faces = t >= ls(31) && t < ls(33);
  const emph = t < ls(32) ? "patient" : "nurse";
  const panel = (side, fn) => {
    ctx.save();
    if (g > 0.5) { ctx.beginPath(); side < 0 ? ctx.rect(-80, -80, 960 - g / 2 + 80, H + 160) : ctx.rect(960 + g / 2, -80, 960 + 80, H + 160); ctx.clip(); }
    fn(); ctx.restore();
  };
  if (faces) {
    panel(-1, () => drawFace(ctx, "patient", { x: 960 - g / 2 - 380, y: 440, s: 0.95, alpha: emph === "patient" ? 1 : 0.45, sat }));
    panel(1, () => drawFace(ctx, "nurse", { x: 960 + g / 2 + 380, y: 440, s: 0.95, alpha: emph === "nurse" ? 1 : 0.45, sat }));
  } else {
    const merged = g < 0.5;
    panel(1, () => drawBody(ctx, "nurse", { x: 960 + off, y: TWO.y, s: TWO.s, alpha: merged ? 0.55 : 1, sat }));
    panel(-1, () => drawBody(ctx, "patient", { x: 960 - off, y: TWO.y, s: TWO.s, alpha: 1, sat }));
  }
  if (g > 0.5) { // the split itself: dark band + red thread
    ctx.fillStyle = "#0b0c0f"; ctx.fillRect(960 - g / 2, -80, g, H + 160);
    ctx.fillStyle = rgb(ACCENT.red, 0.9); ctx.fillRect(959, -80, 2, H + 160);
  }
}

// ---------------------------------------------------------------- red thread
function drawThread(ctx, t) {
  let a = 0, p0, p1, prog = 1;
  const l5 = L(5);
  if (t >= l5.start && t < T.pre) {
    a = t < T.open ? 0.9 : 0.55 * clamp((T.pre - t) / 0.4);
    prog = clamp((t - l5.start) / (l5.end - l5.start));
    p0 = bodyToScreen("patient", { x: TR.pX(t), y: TR.pY(t), s: TR.pS(t) }, ...HAND.patient);
    p1 = t < T.open ? [1980, 260] : bodyToScreen("nurse", { x: TR.nX(t), y: TWO.y, s: TR.nS(t) }, ...HAND.nurse);
    if (t >= T.open) { const k = spring(t - T.open, 3.2, 1); p1 = [lerp(1980, p1[0], k), lerp(260, p1[1], k)]; }
  } else if (t >= T.c && t < T.ch2) {
    a = 0.6 * env(t, T.c, T.ch2, 1.5, 0.3);
    p0 = bodyToScreen("patient", { x: TWO.px, y: TWO.y + 8 * Math.sin((t - T.c) * 0.7), s: TWO.s }, ...HAND.patient);
    p1 = bodyToScreen("nurse", { x: TR.nX(t), y: TWO.y + 8 * Math.sin((t - T.c) * 0.7 + 2), s: TWO.s, mirror: TR.mirror(t) > 0.25 }, ...HAND.nurse);
  } else if (t >= T.outro && t < T.end) { // both ends collapse into one point at the heart
    const k = smooth((t - T.outro) / (L(40).start - T.outro));
    const c = bodyToScreen("patient", { x: 960, y: TWO.y + 10, s: TWO.s }, ...HAND.heart);
    a = 0.85 * (1 - smooth((t - L(40).start) / 1.2));
    p0 = [lerp(200, c[0], k), lerp(700, c[1], k)]; p1 = [lerp(1720, c[0], k), lerp(700, c[1], k)];
    if (k > 0.98) { ctx.save(); ctx.globalAlpha = a; ctx.globalCompositeOperation = "screen"; ctx.drawImage(ASSETS.glow.red, c[0] - 40, c[1] - 40, 80, 80); ctx.restore(); }
  }
  if (a <= 0) return;
  const mx = (p0[0] + p1[0]) / 2, my = Math.max(p0[1], p1[1]) + 120 + 10 * Math.sin(t * 1.3);
  ctx.save(); ctx.strokeStyle = rgb(ACCENT.red, a); ctx.lineWidth = 2.2; ctx.lineCap = "round";
  ctx.beginPath(); const N = 48;
  for (let i = 0; i <= N * prog; i++) {
    const u = i / N, x = (1 - u) * (1 - u) * p0[0] + 2 * u * (1 - u) * mx + u * u * p1[0], y = (1 - u) * (1 - u) * p0[1] + 2 * u * (1 - u) * my + u * u * p1[1];
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.stroke(); ctx.restore();
}

// ---------------------------------------------------------------- particles (closed form, capped)
function drawParticles(ctx, t) {
  const l26 = L(26), l28 = L(28);
  const em = env(t, l26.start, l26.end + 0.6, 0.3, 0.6);
  if (em > 0) { // embers rising from 火
    for (let i = 0; i < 22; i++) {
      const life = 1.8, age = ((t - l26.start) + hash(i) * life) % life, k = age / life;
      const x = 994 + (hash(i * 5) - 0.5) * 160 + Math.sin(age * 3 + i) * 12, y = 260 - k * 220 + hash(i * 9) * 40;
      const s = (1 - k) * (18 + hash(i * 13) * 26);
      ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = em * (1 - k) * 0.9;
      ctx.drawImage(ASSETS.glow.orange, x - s, y - s, s * 2, s * 2); ctx.restore();
    }
  }
  const pe = env(t, l28.start, l28.end + 0.5, 0.4, 0.5);
  if (pe > 0) { // pale petals rising (咲いて)
    for (let i = 0; i < 46; i++) {
      const life = 3.2, age = ((t - l28.start) + hash(i + 40) * life) % life, k = age / life;
      const x = hash(i * 17 + 3) * W + Math.sin(age * 1.7 + i) * 30, y = H * 0.85 - k * H * 0.75;
      ctx.save(); ctx.translate(x, y); ctx.rotate(age * 2 + i); ctx.globalAlpha = pe * Math.sin(k * Math.PI) * 0.75;
      ctx.fillStyle = "#f4f2ee"; ctx.beginPath(); ctx.ellipse(0, 0, 7, 3.5, 0, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    }
  }
}

// ---------------------------------------------------------------- screen-space effects
function drawSpeed(ctx, t) {
  for (const [st, d, kind] of EV.speed) {
    const k = (t - st) / d; if (k < 0 || k > 1) continue;
    const a = Math.sin(k * Math.PI) * 0.75;
    ctx.save(); ctx.globalCompositeOperation = "screen";
    for (let i = 0; i < 26; i++) {
      const h = hash2(Math.floor(st * 100), i);
      if (kind === "h") {
        const y = 180 + h * 720, len = 300 + hash(i * 3) * 700, x = -len + (k * 1.4 + hash(i * 7) * 0.5) * (W + len);
        ctx.globalAlpha = a * (0.25 + hash(i * 11) * 0.5); ctx.drawImage(ASSETS.streak, x, y - 6, len, 12);
      } else {
        const ang = h * Math.PI * 2, r0 = 380 + k * 500, r1 = r0 + 160 + hash(i * 5) * 300;
        ctx.globalAlpha = a * 0.6; ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1 + hash(i * 19) * 2.5;
        ctx.beginPath(); ctx.moveTo(960 + Math.cos(ang) * r0, 470 + Math.sin(ang) * r0 * 0.6); ctx.lineTo(960 + Math.cos(ang) * r1, 470 + Math.sin(ang) * r1 * 0.6); ctx.stroke();
      }
    }
    ctx.restore();
  }
}
function postEffects(ctx, cv, t, px) { // px = output pixels per scene pixel
  const layer = ASSETS.layer, lx = layer.getContext("2d"), cw = cv.width, ch = cv.height;
  // chromatic aberration (hard onsets only): R channel shifted, G/B kept
  const ca = Math.min(1.2, sumImpulse(EV.ca, t, 14));
  if (ca > 0.04) {
    const dx = Math.round(10 * ca * px);
    lx.globalCompositeOperation = "copy"; lx.drawImage(cv, 0, 0);
    lx.globalCompositeOperation = "multiply"; lx.fillStyle = "#ff0000"; lx.fillRect(0, 0, cw, ch);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "multiply"; ctx.fillStyle = "#00ffff"; ctx.fillRect(0, 0, cw, ch);
    ctx.globalCompositeOperation = "lighter"; ctx.drawImage(layer, dx, 0);
    ctx.restore();
  }
  // glitch slices
  for (const [gt, d] of EV.glitch) {
    if (t < gt || t > gt + d) continue;
    const fr = Math.floor(t * 30);
    lx.globalCompositeOperation = "copy"; lx.drawImage(cv, 0, 0);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
    for (let i = 0; i < 9; i++) {
      const y = hash2(fr, i) * ch, h = (8 + hash2(i, fr) * 60) * px, off = (hash2(fr + 7, i) - 0.5) * 160 * px;
      ctx.drawImage(layer, 0, y, cw, h, off, y, cw, h);
      if (i % 3 === 0) { ctx.fillStyle = i % 2 ? "rgba(200,16,46,0.5)" : "rgba(143,211,216,0.45)"; ctx.fillRect(hash2(i, fr + 3) * cw, y, (40 + hash2(fr, i + 9) * 300) * px, h * 0.5); }
    }
    ctx.restore();
  }
  // bloom on the final chorus hit: downscale/upscale copy, screen blended
  const bl = t < T.climax ? 0 : 0.9 * Math.exp(-(t - T.climax) * 0.45) * clamp((t - T.climax) / 0.08);
  if (bl > 0.02 && t < T.outro) {
    const sm = ASSETS.small, sx = sm.getContext("2d");
    sx.globalCompositeOperation = "copy"; sx.drawImage(cv, 0, 0, sm.width, sm.height);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = bl;
    ctx.drawImage(sm, 0, 0, cw, ch); ctx.drawImage(sm, -cw * 0.02, -ch * 0.02, cw * 1.04, ch * 1.04); ctx.restore();
  }
}

function drawHUD(ctx, t, pal) {
  const a = 0.55 * env(t, T.hud, T.ch2, 1.0, 0.3) * (t >= T.pre && t < T.c ? 0 : 1);
  if (a <= 0) return;
  const c = rgb(pal.fg, a);
  ctx.save(); ctx.strokeStyle = c; ctx.fillStyle = c; ctx.lineWidth = 1.5;
  const m = 44, L0 = 54;
  for (const [x, y, sx, sy] of [[m, m, 1, 1], [W - m, m, -1, 1], [m, 900, 1, -1], [W - m, 900, -1, -1]]) {
    ctx.beginPath(); ctx.moveTo(x, y + sy * L0); ctx.lineTo(x, y); ctx.lineTo(x + sx * L0, y); ctx.stroke();
  }
  ctx.font = "400 22px Mincho"; ctx.textBaseline = "top"; ctx.fillText("S L O W D O W N E R", m + 20, m + 16);
  for (let i = 0; i < 18; i++) { // level meter reading the precomputed energy curve
    const e = energyAt(Math.max(0, t - i * 0.05));
    ctx.globalAlpha = a; ctx.fillRect(W - m - 20 - i * 9, m + 40 - e * 26, 5, Math.max(1, e * 26));
  }
  for (let y = 300; y < 760; y += 30) ctx.fillRect(m - 10, y, y % 150 ? 6 : 14, 1.5); // side ticks
  ctx.restore();
}
function drawTitleCard(ctx, t) {
  const a = env(t, T.title, T.a2 - 1.2, 0.25, 0.4);
  if (a <= 0) return;
  ctx.save(); ctx.globalAlpha = a;
  const w = 330, h = 62, k = spring(t - T.title, 12, 0.8);
  ctx.fillStyle = "#111214"; ctx.fillRect(960 - w / 2 * k, 470 - h / 2, w * k, h);
  ctx.font = "700 34px Mincho"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = "#f2f2f2";
  ctx.globalAlpha = a * clamp((t - T.title - 0.12) / 0.2); ctx.fillText("スロウダウナー", 960, 472);
  ctx.restore();
}
function drawCredits(ctx, t) {
  const rows = [["作詞・作曲", "ろくろ"], ["Vocal", "暁山瑞希"], ["Movie", "meel"]];
  ctx.save(); ctx.textBaseline = "middle";
  rows.forEach(([k, v], i) => {
    const ts = T.end + 0.2 + i * 0.35, a = clamp((t - ts) / 0.4);
    if (a <= 0) return;
    const y = 400 + i * 64;
    ctx.globalAlpha = a; ctx.fillStyle = "#24231f";
    ctx.font = "400 30px Mincho"; ctx.textAlign = "right"; ctx.fillText(k, 1560, y);
    ctx.font = "700 44px Mincho"; ctx.textAlign = "left"; ctx.fillText(v, 1600, y);
  });
  ctx.restore();
}

// ---------------------------------------------------------------- frame
let CV, CTX, PX = 1;
function drawScene(ctx, t) {
  const pal = paletteAt(t), cam = camera(t);
  ctx.save(); applyCam(ctx, cam, 0.35); drawBackground(ctx, t, pal); ctx.restore();
  ctx.save(); applyCam(ctx, cam, 1);
  for (const d of LINES) if (d.ghost) drawGhost(ctx, d.ghost, L(d.id), t, pal);
  drawCharacters(ctx, t, pal);
  drawThread(ctx, t);
  for (const d of LINES) { const l = L(d.id); if (t >= l.start - 0.6 && t <= l.end) { if (d.subs) drawSubs(ctx, d.subs, l, t, pal); drawLine(ctx, d, l, t, pal); } }
  drawParticles(ctx, t);
  drawTitleCard(ctx, t);
  ctx.restore();
  drawSpeed(ctx, t);
}
function renderFrame(t, opts = {}) {
  const ctx = CTX;
  ctx.setTransform(PX, 0, 0, PX, 0, 0);
  ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
  drawScene(ctx, t);
  if (opts.blur) { // cheap 2-sample motion blur, only on speed-line hits
    const prev = ASSETS.prev, px = prev.getContext("2d");
    px.globalCompositeOperation = "copy"; px.drawImage(CV, 0, 0);
    ctx.setTransform(PX, 0, 0, PX, 0, 0); drawScene(ctx, t - opts.blur);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 0.5; ctx.drawImage(prev, 0, 0); ctx.restore();
  }
  ctx.setTransform(PX, 0, 0, PX, 0, 0);
  postEffects(ctx, CV, t, PX);
  ctx.setTransform(PX, 0, 0, PX, 0, 0);
  const pal = paletteAt(t);
  const fl = Math.min(1, sumImpulse(EV.flash, t, 22)); // flash frames on cuts
  if (fl > 0.02) { ctx.fillStyle = `rgba(255,255,255,${0.85 * fl})`; ctx.fillRect(0, 0, W, H); }
  const wo = env(t, T.white, T.outro, 0.35, 2.5) * 0.4; // whiteout after こうやってアイは終わった
  if (wo > 0) { ctx.fillStyle = `rgba(250,249,246,${wo})`; ctx.fillRect(0, 0, W, H); }
  ctx.drawImage(ASSETS.vignette, 0, 0, W, H);
  ctx.save(); ctx.globalAlpha = 0.06 + 0.03 * energyAt(t); ctx.globalCompositeOperation = "overlay";
  const tile = ASSETS.grain[Math.floor(t * 30) % ASSETS.grain.length]; ctx.fillStyle = ctx.createPattern(tile, "repeat");
  ctx.fillRect(0, 0, W, H); ctx.restore();
  const lb = TR.letterbox(t) * 132; // 2.35:1 letterbox in the intro
  if (lb > 0.5) { ctx.fillStyle = "#050506"; ctx.fillRect(0, 0, W, lb); ctx.fillRect(0, H - lb, W, lb); }
  drawHUD(ctx, t, pal);
  drawCredits(ctx, t);
  drawSubtitle(ctx, t);
  const fb = clamp((t - (D.duration - 1.1)) / 1.0); // final fade to black
  if (fb > 0) { ctx.fillStyle = `rgba(0,0,0,${fb})`; ctx.fillRect(0, 0, W, H); }
}

async function init(width = 1920) {
  PX = width / W;
  CV = document.getElementById("c"); CV.width = width; CV.height = Math.round(H * PX);
  CTX = CV.getContext("2d");
  await loadAssets();
  for (const k of ["layer", "prev"]) { ASSETS[k].width = CV.width; ASSETS[k].height = CV.height; }
  buildTimes(); buildPalettes(); buildTracks(); buildEvents();
  for (const d of LINES) layoutLine(d, CTX); // validates every design against the lyric text
  return { fallbacks: ASSETS.fontFallbacks, duration: D.duration, T };
}
window.init = init;
window.seek = (t, opts) => renderFrame(t, opts);
// representative times for the per-section stills
window.stillTimes = () => {
  const mid = (i) => (L(i).start + L(i).end) / 2;
  return [mid(5), T.title + 1.2, mid(13) - 0.3, mid(19), mid(20) + 0.4, mid(22), mid(26), mid(29) + 0.8, mid(33), T.climax + 0.25, 126.5, mid(40), 141.2];
};

// Layout check: Japanese text (lines + ghosts + subs) must stay out of the subtitle band and inside safe margins.
window.checkText = () => {
  const c = document.createElement("canvas"); c.width = W / 2; c.height = H / 2; const x = c.getContext("2d", { willReadFrequently: true });
  const bad = [];
  for (const d of LINES) {
    const l = L(d.id);
    for (const t of [l.start + 0.3, (l.start + l.end) / 2, l.end - (d.exitDur ?? 0.22) - 0.02]) {
      x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, c.width, c.height);
      x.setTransform(0.5, 0, 0, 0.5, 0, 0); applyCam(x, camera(t), 1);
      const pal = paletteAt(t);
      if (d.ghost) drawGhost(x, d.ghost, l, t, pal);
      if (d.subs) drawSubs(x, d.subs, l, t, pal);
      drawLine(x, d, l, t, pal);
      const px = x.getImageData(0, 0, c.width, c.height).data;
      let band = 0, out = 0;
      for (let yy = 0; yy < c.height; yy++) for (let xx = 0; xx < c.width; xx++) {
        if (px[(yy * c.width + xx) * 4 + 3] < 40) continue;
        if (yy * 2 > 915) band++;
        if (xx * 2 < 60 || xx * 2 > W - 60 || yy * 2 < 40) out++;
      }
      if (band || out) bad.push({ id: d.id, t: +t.toFixed(2), bandPx: band, outsidePx: out });
    }
  }
  return bad;
};
