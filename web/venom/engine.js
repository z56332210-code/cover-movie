// Venom-style lyric video engine. seek(t) draws one frame from t alone (no state carried between frames).
// World coordinates are 1920x1080; preview/final differ only in canvas size, fps and post effects.
"use strict";
const D = window.DATA;
const W0 = 1920, H0 = 1080;
const PAL = { lav: "#F1B5FB", mag: "#EB008D", navy: "#15183C", white: "#FFFFFF", black: "#000000" };
const FONT = { jp: "VJP", jp7: "VJP7", ko: "VKO", en: "VEN" };
let cv, ctx, SC = 1, OPTS = {}, IMG = {};
let EN_FONT = "en-playfair";

// ------------------------------------------------------------------ small helpers
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const lerp = (a, b, k) => a + (b - a) * k;
const easeOut3 = (k) => 1 - Math.pow(1 - clamp(k), 3);
function hash(a, b = 0) {
  let h = (Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16; return (h >>> 0) / 4294967296;
}
function rng(seed) {
  let s = (seed >>> 0) || 1;
  return () => { s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const q15 = (t) => Math.floor(t * 15) / 15;          // the reference animates ink/glitch on 15 fps steps
const LYR = {}; D.lyrics.forEach((l) => (LYR[l.id] = l));
const SHOTS = D.plan.shots;

// shot groups: text events and ink overlays continue the same picture (camera keeps running)
(function groupShots() {
  SHOTS.forEach((s, i) => {
    const p = SHOTS[i - 1];
    const cont = p && (s.trans_in === "text" || s.trans_in === "hold" || (s.trans_in === "ink_wipe" && p.framing === s.framing));
    s.g0 = cont ? p.g0 : s.t0; s.gid = cont ? p.gid : i;
  });
  for (let i = SHOTS.length - 1; i >= 0; i--) { const n = SHOTS[i + 1]; SHOTS[i].g1 = n && n.gid === SHOTS[i].gid ? n.g1 : SHOTS[i].t1; }
})();
const shotAt = (t) => SHOTS.find((s) => t >= s.t0 && t < s.t1) || SHOTS[SHOTS.length - 1];

// ------------------------------------------------------------------ assets
function loadImg(name) {
  return new Promise((ok, err) => { const im = new Image(); im.onload = () => ok((IMG[name] = im)); im.onerror = () => err(new Error("img " + name)); im.src = "img/" + name + ".png"; });
}
async function loadFonts() {
  const faces = [[FONT.jp, "serif-jp-900", "900"], [FONT.jp7, "serif-jp-700", "700"], [FONT.ko, "pretendard-300", "300"], [FONT.en, EN_FONT, "900"]];
  const out = [];
  for (const [fam, file, w] of faces) {
    const f = new FontFace(fam, `url(fonts/${file}.woff2)`, { weight: w, style: "normal" });
    await f.load(); document.fonts.add(f); out.push(f);
  }
  return out;
}
// coverage check: every char we draw must have a glyph in our font (no system fallback)
function fallbackChars() {
  const texts = D.lyrics.map((l) => l.ja).join("") + D.credits.items.map((c) => c.name).join("") + D.credits.title + D.credits.subtitle;
  const probe = document.createElement("canvas").getContext("2d");
  const miss = new Set();
  for (const ch of new Set(texts)) {
    if (!ch.trim()) continue;
    probe.font = `900 40px ${FONT.jp}, monospace`; const a = probe.measureText(ch).width;
    probe.font = `900 40px ${FONT.jp}, serif`; const b = probe.measureText(ch).width;
    if (Math.abs(a - b) > 0.01) miss.add(ch);
  }
  return [...miss];
}

// ------------------------------------------------------------------ primitives
function blobPath(cx, cy, r, seed, bumps = 22, amp = 0.09) {
  const R = rng(seed), ph = [R() * 6.283, R() * 6.283, R() * 6.283, R() * 6.283], N = 180, p = new Path2D();
  for (let i = 0; i <= N; i++) {
    const a = (i / N) * 6.2832;
    let k = 1 + 0.10 * Math.sin(2 * a + ph[0]) + 0.07 * Math.sin(3 * a + ph[1]) + 0.04 * Math.sin(5 * a + ph[2]);
    k += amp * (Math.pow(Math.abs(Math.sin((bumps * a) / 2 + ph[3])), 0.45) - 0.6);   // scalloped edge like the reference blots
    const x = cx + Math.cos(a) * r * k, y = cy + Math.sin(a) * r * k;
    i ? p.lineTo(x, y) : p.moveTo(x, y);
  }
  p.closePath(); return p;
}
function inkCluster(c, cx, cy, r, seed, color = PAL.mag, alpha = 1) {
  const R = rng(seed); c.save(); c.globalAlpha = alpha; c.fillStyle = color;
  c.fill(blobPath(cx, cy, r, seed));
  for (let i = 0; i < 7; i++) {
    const a = R() * 6.283, d = r * (0.7 + R() * 0.6), rr = r * (0.12 + R() * 0.25);
    c.fill(blobPath(cx + Math.cos(a) * d, cy + Math.sin(a) * d, rr, seed * 31 + i, 14, 0.12));
  }
  c.restore();
}
// watercolour splashes (tints of magenta over lavender) + specks
function splatter(c, cx, cy, r, seed, n = 18, alpha = 0.45, specks = 1) {
  const R = rng(seed); c.save(); c.fillStyle = PAL.mag;
  for (let i = 0; i < n; i++) {
    const a = R() * 6.283, d = Math.sqrt(R()) * r, rr = 10 + R() * r * 0.16;
    c.globalAlpha = alpha * (0.35 + R() * 0.65);
    c.fill(blobPath(cx + Math.cos(a) * d, cy + Math.sin(a) * d, rr, seed * 7 + i, 10, 0.18));
  }
  c.globalAlpha = 0.9;
  for (let i = 0; i < n * 3 * specks; i++) {
    const a = R() * 6.283, d = r * (0.3 + R() * 0.9), rr = 1.5 + R() * 5;
    c.beginPath(); c.arc(cx + Math.cos(a) * d, cy + Math.sin(a) * d, rr, 0, 6.283); c.fill();
  }
  c.restore();
}
// halftone: dots on a 45 degree grid, size falls off from the centre (or follows a custom field)
function halftone(c, cx, cy, R, cell, color, field) {
  const p = new Path2D(), ca = Math.SQRT1_2;
  const n = Math.ceil(R / cell) + 1;
  for (let i = -n; i <= n; i++) for (let j = -n; j <= n; j++) {
    const u = i * cell, v = j * cell, x = cx + (u - v) * ca, y = cy + (u + v) * ca;
    const k = field ? field(x, y) : 1 - Math.hypot(x - cx, y - cy) / R;
    if (k <= 0.02) continue;
    const rr = cell * 0.5 * Math.pow(clamp(k), 0.75);
    if (rr < 0.6) continue;
    p.moveTo(x + rr, y); p.arc(x, y, rr, 0, 6.283);
  }
  c.fillStyle = color; c.fill(p);
}
function pill(c, x, y, len, wid, rot, flip) {
  c.save(); c.translate(x, y); c.rotate(rot);
  const r = wid / 2, h = len / 2, lw = Math.max(2, wid * 0.09);
  const cap = (s) => { c.beginPath(); c.moveTo(0, -r); c.lineTo(s * (h - r), -r); c.arc(s * (h - r), 0, r, -Math.PI / 2, Math.PI / 2, s < 0); c.lineTo(0, r); c.closePath(); };
  cap(-1); c.fillStyle = flip ? PAL.navy : PAL.white; c.fill();
  cap(1); c.fillStyle = flip ? PAL.white : PAL.navy; c.fill();
  c.beginPath(); c.moveTo(-(h - r), -r); c.lineTo(h - r, -r); c.arc(h - r, 0, r, -Math.PI / 2, Math.PI / 2); c.lineTo(-(h - r), r); c.arc(-(h - r), 0, r, Math.PI / 2, -Math.PI / 2);
  c.lineWidth = lw; c.strokeStyle = PAL.navy; c.stroke();
  c.fillStyle = PAL.white; c.globalAlpha = 0.9; c.fillRect(-h * 0.55, -r * 0.55, h * 0.35, r * 0.22); // highlight
  c.restore();
}
function pills(c, n, seed, t, area = { x: 0, y: 0, w: W0, h: H0 }) {
  const R = rng(seed);
  for (let i = 0; i < n; i++) {
    const x = area.x + R() * area.w, y = area.y + R() * area.h, len = 60 + R() * 90, rot = R() * 6.283, flip = R() < 0.5;
    const dr = (R() - 0.5) * 0.3, dx = (R() - 0.5) * 14, dy = (R() - 0.5) * 14;
    pill(c, x + dx * t, y + dy * t, len, len * 0.42, rot + dr * t, flip);
  }
}
const CUTS = [];   // screen-space segments of props' canvas-cut edges drawn this frame (must stay off screen)
function drawImg(c, name, cx, cy, s, rot = 0, alpha = 1) {
  const im = IMG[name]; if (!im) return;
  c.save(); c.globalAlpha = alpha; c.translate(cx, cy); if (rot) c.rotate(rot);
  c.drawImage(im, (-im.width * s) / 2, (-im.height * s) / 2, im.width * s, im.height * s);
  const pm = D.meta.props[name];
  if (pm && pm.cuts && pm.cuts.length) {
    const m = c.getTransform(), P = (x, y) => { const u = (x - im.width / 2) * s, v = (y - im.height / 2) * s; return [(m.a * u + m.c * v + m.e) / SC, (m.b * u + m.d * v + m.f) / SC]; };
    pm.cuts.forEach(([x0, y0, x1, y1]) => CUTS.push([...P(x0, y0), ...P(x1, y1), name]));
  }
  c.restore();
}

// ------------------------------------------------------------------ camera
function camera(s, t) {
  const g = Math.max(0.001, s.g1 - s.g0), tau = t - s.g0, u = clamp(tau / g);
  const dec = 1 - Math.exp(-tau / 0.55);                    // fast right after the cut, then settles (ref: ~180 -> 50 -> 15 px/s)
  switch (s.camera) {
    case "fast_decel": { const R = rng(s.gid * 13 + 5), dir = R() < 0.5 ? -1 : 1, dec2 = 1 - Math.exp(-tau / 0.38);
      return { z: 1.07 - 0.05 * dec2, x: dir * (170 * (1 - dec2) - 37 * tau), y: -30 * (1 - dec2) + 6 * tau }; }
    case "slow_push": return { z: 1.0 + 0.06 * u, x: lerp(40, -40, u), y: lerp(-25, 10, u) };   // ref outro: ~10 px/s drift
    case "drift": return { z: 1.04, x: lerp(-45, 45, u), y: 0 };
    case "pan_mid": return { z: 1.06, x: lerp(-120, 120, Math.sin(u * Math.PI / 2)), y: 0 };
    default: return { z: 1.0 + 0.02 * u, x: 0, y: 0 };
  }
}
function applyCam(c, cam) { c.translate(W0 / 2 + cam.x, H0 / 2 + cam.y); c.scale(cam.z, cam.z); c.translate(-W0 / 2, -H0 / 2); }
function camPoint(cam, x, y) { return [(x - W0 / 2) * cam.z + W0 / 2 + cam.x, (y - H0 / 2) * cam.z + H0 / 2 + cam.y]; }

// ------------------------------------------------------------------ character placement (default = bust shot like the cover)
const CHAR = {
  bust:  { img: "bust_m", cx: 960, top: 30, h: 1260 },     // head to chest (waist falls below the frame)
  close: { img: "bust", cx: 1010, top: -260, h: 2350 },    // upper face to hands
  face:  { img: "bust", cx: 900, top: -560, h: 3200 },     // eyes fill the frame (outro, once)
  key:   { img: "bust_m", cx: 960, top: 220, h: 1120 },
  tight: { img: "bust", cx: 980, top: -120, h: 1750 },     // tighter than the bust shot (last chorus)    // key visual silhouette
};
let EYES = [];   // screen-space eye boxes of the last drawn character (for the text check)
function drawChar(c, cam, place, variant = "") {
  const P = CHAR[place], im = IMG[P.img + variant]; if (!im) return;
  const s = P.h / im.height, w = im.width * s, x = P.cx - w / 2, y = P.top;
  c.drawImage(im, x, y, w, P.h);
  const m = D.meta.chars[P.img];
  if (variant === "_sil") { EYES = []; return; }            // a silhouette has no visible eyes
  EYES = m.eyes.map(([ex, ey, ew, eh]) => {
    const pad = 0.6;
    const [ax, ay] = camPoint(cam, x + (ex - ew * pad) * s, y + (ey - eh * pad) * s);
    const [bx, by] = camPoint(cam, x + (ex + ew * (1 + pad)) * s, y + (ey + eh * (1 + pad)) * s);
    return [ax, ay, bx - ax, by - ay];
  });
}

// ------------------------------------------------------------------ prop layouts (positions in world px; scale relative to the 4K source)
// radial burst around the character with lavender breathing room (reference key visual); props may run off the frame
const BG_PROPS = {
  // traffic light (pole) and scissors (both ends) were cut by the illustrator's canvas: placed so the cuts stay off screen
  // (tools/stills_venom.mjs --cutcheck verifies every frame)
  wide: [["bg1_ribbon", 430, 330, 0.40, -0.50], ["bg3_scissors", 1010, 760, 0.86, 0.15], ["bg2_traffic_light", 1560, 480, 0.80, -0.18]],
  key:  [["bg1_ribbon", 360, 300, 0.40, -0.55], ["bg3_scissors", 830, 890, 0.86, -0.50], ["bg2_traffic_light", 1620, 450, 0.80, -0.25]],
  manga:[["bg3_scissors", 1500, 640, 0.68, 0.65]],
};
const FG_PROPS = {
  wide: [["fg3_brush_long", 190, 150, 0.46, -0.9], ["fg2_lipstick_long", 1800, 600, 0.50, 0.9], ["fg5_foundation", 1640, 960, 0.52, -0.2],
         ["fg1_lipstick_short", 300, 960, 0.60, 0.7], ["fg4_brush_short", 90, 640, 0.50, 0.3]],
  key:  [["fg3_brush_long", 150, 130, 0.42, -0.9], ["fg2_lipstick_long", 1850, 640, 0.44, 0.9]],
};
// props float on their own (reference: each prop drifts a little, the silhouette stays still)
let FLOAT_AMP = 1, PARX = 0, PARY = 0;     // PAR*: extra parallax offset for props (foreground layers move more than the ink/background)
function floatOf(n, t) { const ph = hash(n.length * 97 + n.charCodeAt(4), 5) * 6.283, ph2 = hash(n.charCodeAt(2), 9) * 6.283;
  const k = FLOAT_AMP; return [Math.sin(t * 0.55 + ph) * 16 * k + PARX, Math.cos(t * 0.47 + ph2) * 11 * k + PARY, Math.sin(t * 0.38 + ph2) * 0.03 * k]; }
function drawProps(c, list, filter, t = 0) {
  if (filter) c.filter = filter;
  list.forEach(([n, x, y, s, r]) => { const [dx, dy, dr] = floatOf(n, t); drawImg(c, n, x + dx, y + dy, s, r + dr); });
  if (filter) c.filter = "none";
}
function drawProp(c, n, x, y, s, r, t) { const [dx, dy, dr] = floatOf(n, t); drawImg(c, n, x + dx, y + dy, s, r + dr); }

// ------------------------------------------------------------------ text
const jpFont = (px, w = 900) => `${w} ${px}px ${w === 900 ? FONT.jp : FONT.jp7}`;
const isLatin = (s) => /^[\x20-\x7e]+$/.test(s);
function shadowOn(c, px) { c.shadowColor = PAL.navy; c.shadowOffsetX = px * 0.025 * SC; c.shadowOffsetY = px * 0.02 * SC; c.shadowBlur = 0; }
function shadowOff(c) { c.shadowColor = "transparent"; c.shadowOffsetX = c.shadowOffsetY = 0; }
function slanted(c, x, y, rot, fn) { c.save(); c.translate(x, y); c.rotate(rot); c.transform(1, 0, -0.22, 1, 0, 0); fn(); c.restore(); }
const visibleLine = (id, t) => { const l = LYR[id]; return l && t >= l.start - 0.02 && t < l.end; };
const TEXTBOX = [];   // screen-space boxes of drawn lyric text (for the eye-overlap check)
function noteBox(c, x, y, w, h) { const m = c.getTransform(); const pts = [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].map(([a, b]) => [m.a * a + m.c * b + m.e, m.b * a + m.d * b + m.f]); const xs = pts.map((p) => p[0] / SC), ys = pts.map((p) => p[1] / SC); TEXTBOX.push([Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)]); }

// ---- small lyric text (methods 1, 1b, 2, 2b, 3, 5). Reference: ~40 px at 1080p, wide tracking (~0.38 em),
// characters appear as they are sung (short fade), and the lines of a shot stay on screen so two blocks fill the frame.
const TRACK = 0.38;
function spacedW(c, str, sp) { let w = 0; for (const ch of str) w += c.measureText(ch).width + sp; return Math.max(0, w - sp); }
function fillSpaced(c, str, x, y, sp) { for (const ch of str) { c.fillText(ch, x, y); x += c.measureText(ch).width + sp; } }
const charAlpha = (l, k, t) => (l ? clamp((t - l.chars[Math.min(k, l.chars.length - 1)] + 0.06) / 0.12) : 1);
function fillReveal(c, l, off, str, x, y, sp, t) {
  [...str].forEach((ch, k) => { const a = charAlpha(l, off + k, t); if (a > 0) { c.globalAlpha = a; c.fillText(ch, x, y); } x += c.measureText(ch).width + sp; });
  c.globalAlpha = 1;
}
// split a line in two at a natural break; returns [[text, charOffset], ...]
function splitTwo(str, max = 11) {
  const ch = [...str]; if (ch.length <= max) return [[str, 0]];
  const mb = D.typo.breaks && D.typo.breaks[str];                       // manual break (data/typo.json)
  if (mb !== undefined) { const k = [...str.slice(0, mb)].length; return [[ch.slice(0, k).join("").replace(/ $/, ""), 0], [ch.slice(k).join(""), k]]; }
  let best = Math.ceil(ch.length / 2), bd = 99;
  const kanjiNext = (nx) => /[一-龯ァ-ヶA-Za-z「（]/.test(nx || "");
  const bonus = (x, nx) => (/[？。 ]/.test(x) ? 8 : /[」）]/.test(x) ? 6 : /[だよ]/.test(x) && !/[ーぁぃぅぇぉゃゅょっ]/.test(nx || "") ? 4
    : /[はでものなにをがて]/.test(x) && kanjiNext(nx) ? 3 : 0);
  ch.forEach((x, i) => { if (i < 2 || i > ch.length - 3) return; const d = Math.abs(i + 1 - ch.length / 2) - bonus(x, ch[i + 1]); if (d < bd) { bd = d; best = i + 1; } });
  return [[ch.slice(0, best).join(""), 0], [ch.slice(best).join("").replace(/^ /, ""), best + (ch[best] === " " ? 1 : 0)]];
}
function softShadow(c, on) { if (on) { c.shadowColor = "rgba(21,24,60,0.9)"; c.shadowBlur = 6 * SC; c.shadowOffsetX = 2 * SC; c.shadowOffsetY = 2 * SC; } else shadowOff(c); }
// 1: navy box, sized with the tracking so no glyph sticks out
function textBox(c, l, t, x, y, px = 36) {
  c.font = jpFont(px, 700); const sp = px * TRACK * 0.6, parts = splitTwo(l.ja);
  const lw = Math.max(...parts.map(([p]) => spacedW(c, p, sp)));
  const padX = px * 0.7, lh = px * 1.5, w = lw + padX * 2, h = parts.length * lh + px * 0.5;
  c.fillStyle = PAL.navy; c.fillRect(x, y, w, h); noteBox(c, x, y, w, h);
  c.fillStyle = PAL.white; c.textBaseline = "middle";
  parts.forEach(([p, off], i) => fillReveal(c, l, off, p, x + padX, y + px * 0.25 + lh * (i + 0.5), sp, t));
}
// 1b: white horizontal, two lines
function textSmall(c, l, t, x, y, px = 40, color = PAL.white) {
  c.font = jpFont(px, 700); c.fillStyle = color; c.textBaseline = "middle"; softShadow(c, color === PAL.white);
  const sp = px * TRACK;
  splitTwo(l.ja).forEach(([p, off], i) => { fillReveal(c, l, off, p, x, y + i * px * 1.55, sp, t); noteBox(c, x, y - px / 2 + i * px * 1.55, spacedW(c, p, sp), px); });
  softShadow(c, false);
}
// 2 / 2b / 5: vertical, long lines in two columns (right column first)
function textVertical(c, l, t, x, y, px = 38, bar = null, color = PAL.white) {
  c.font = jpFont(px, 700); const step = px * (1 + TRACK * 0.7);
  const parts = splitTwo(l.ja, 10);
  parts.forEach(([p, off], col) => {
    const cx = x - col * px * 1.9, chars = [...p], hgt = step * chars.filter((q) => q !== " ").length + px * 0.6;
    if (bar) { c.fillStyle = bar; c.fillRect(cx - px * 0.8, y - px * 0.85, px * 1.6, hgt); }
    noteBox(c, cx - px * 0.8, y - px * 0.85, px * 1.6, hgt);
    c.fillStyle = color; c.textAlign = "center"; c.textBaseline = "middle"; softShadow(c, !bar && color === PAL.white);
    let row = 0;
    chars.forEach((ch, i) => {
      if (ch === " ") return; const r = row++;
      const a = charAlpha(l, off + i, t); if (a <= 0) return;
      c.save(); c.globalAlpha = a; c.translate(cx, y + r * step); if (/[ー～（）「」]/.test(ch)) c.rotate(Math.PI / 2); c.fillText(ch, 0, 0); c.restore();
    });
    c.textAlign = "left"; softShadow(c, false);
  });
}
// 3: navy band along a prop, the whole band is laid first, glyphs appear as sung; the two halves of the line get a wide gap
function textBand(c, l, t, x, y, rot, px = 38) {
  c.save(); c.translate(x, y); c.rotate(rot); c.font = jpFont(px, 700);
  const sp = px * TRACK * 0.7, gap = px * 1.4, parts = splitTwo(l.ja, 8);
  const ws = parts.map(([p]) => spacedW(c, p, sp)), w = ws.reduce((a, b) => a + b, 0) + gap * (parts.length - 1) + px * 1.4;
  c.fillStyle = PAL.navy; c.fillRect(-px * 0.7, -px * 0.8, w, px * 1.6); noteBox(c, -px * 0.7, -px * 0.8, w, px * 1.6);
  c.fillStyle = PAL.white; c.textBaseline = "middle"; let xx = 0;
  parts.forEach(([p, off], i) => { fillReveal(c, l, off, p, xx, 0, sp, t); xx += ws[i] + gap; });
  c.restore();
}
// 4: giant cut glyphs. A: split magenta/navy; B: black rows behind the character
function wordsOf(id) {
  const l = LYR[id], words = D.typo[String(id)]; if (!words) return [];
  const out = []; let pos = 0;
  for (const w of words) {
    const at = l.ja.indexOf(w, pos); if (at < 0) continue;
    const echo = l.ja.lastIndexOf("（", at) > l.ja.lastIndexOf("）", at);
    out.push({ w, echo, t: [...w].map((_, k) => l.chars[at + k]) }); pos = at + w.length;
  }
  out.forEach((o, i) => (o.until = i + 1 < out.length ? out[i + 1].t[0] : l.end));
  return out;
}
const SLOTS = {
  1: [[300, 330]], 2: [[150, 300], [1430, 620]], 3: [[120, 230], [760, 520], [1400, 780]],
  4: [[120, 230], [1380, 230], [120, 780], [1380, 780]], 5: [[60, 200], [700, 140], [1380, 260], [220, 800], [1240, 820]],
};
function giantA(c, id, t, seed) {
  for (const wd of wordsOf(id)) {
    if (t < wd.t[0] - 0.02 || t >= wd.until) continue;
    const chars = [...wd.w], n = Math.min(chars.length, 5), slots = SLOTS[n] || SLOTS[5], R = rng(seed + wd.t[0] * 100);
    chars.forEach((ch, k) => {
      if (t < wd.t[k] - 0.02) return;
      const [sx, sy] = slots[Math.min(k, slots.length - 1)], px = (n <= 2 ? 470 : 400) * (0.92 + R() * 0.16);
      const x = sx + (R() - 0.5) * 80, y = sy + (R() - 0.5) * 60 + px * 0.85, rot = (R() - 0.5) * 0.12;
      const col = wd.echo || /メッ/.test(wd.w) ? PAL.navy : PAL.mag;
      cutGlyph(c, ch, x, y, px, rot, col, col, R());
    });
  }
}
function cutGlyph(c, ch, x, y, px, rot, c1, c2, r) {
  c.save(); c.translate(x, y); c.rotate(rot); c.transform(1, 0, -0.12, 1, 0, 0);
  c.font = isLatin(ch) ? `900 italic ${px}px ${FONT.en}` : jpFont(px); c.textBaseline = "alphabetic";
  const w = c.measureText(ch).width; noteBox(c, 0, -px * 0.88, w, px);
  const ang = (r - 0.5) * 0.7, cx = w / 2, cy = -px * (0.25 + r * 0.35);
  const half = (side) => { c.save(); c.beginPath(); c.translate(cx, cy); c.rotate(ang); c.rect(-px * 2, side < 0 ? -px * 2 : 0, px * 4, px * 2); c.rotate(-ang); c.translate(-cx, -cy); c.clip(); };
  if (c1 === PAL.mag) shadowOn(c, px);
  half(-1); c.fillStyle = c1; c.fillText(ch, 0, 0); c.restore();
  half(1); c.translate(px * 0.035, px * 0.025); c.fillStyle = c2; c.fillText(ch, 0, 0); c.restore();
  shadowOff(c);
  c.restore();
}
// B: two rows of giant black glyphs (first half of the line on top, second half at the bottom), cut by the frame edges
function giantRowsB(c, id, t, seed) {
  const words = wordsOf(id), half = Math.ceil(words.length / 2), R = rng(seed);
  [words.slice(0, half), words.slice(half)].forEach((row, r) => {
    const px = 360 + R() * 50; let x = r === 0 ? -60 - R() * 80 : 200 + R() * 160; const y = r === 0 ? px * 0.80 : 1080 - px * 0.05;
    c.fillStyle = PAL.black;
    row.forEach((wd) => [...wd.w].forEach((ch, k) => {
      const lat = isLatin(ch); c.font = lat ? `900 italic ${px * 1.05}px ${FONT.en}` : jpFont(px);
      if (t >= wd.t[k] - 0.02) c.fillText(ch, x, y);
      x += c.measureText(ch).width * (lat ? 1.0 : 0.96);
    }));
  });
}
// 6: magenta bold slanted
function textMagenta(c, str, x, y, px = 150, rot = -0.2, color = PAL.mag) {
  slanted(c, x, y, rot, () => { c.font = isLatin(str) ? `900 italic ${px}px ${FONT.en}` : jpFont(px); c.fillStyle = color; c.textBaseline = "alphabetic"; if (color === PAL.mag) shadowOn(c, px); c.fillText(str, 0, 0); shadowOff(c); noteBox(c, 0, -px * 0.88, c.measureText(str).width, px); });
}
// Korean subtitle: bottom centre, small, thin, fade only; dark on light backgrounds
function subtitle(c, t) {
  const l = D.lyrics.find((o) => t >= o.start && t < o.end); if (!l) return;
  const a = clamp((t - l.start) / 0.15) * clamp((l.end - t) / 0.15);
  c.font = `300 30px ${FONT.ko}`; const w = c.measureText(l.ko).width, x = (W0 - w) / 2, y = 1032;
  const img = ctx.getImageData(Math.max(0, x * SC), (y - 26) * SC, Math.max(1, w * SC), 36 * SC).data;
  let lum = 0; for (let i = 0; i < img.length; i += 16) lum += 0.299 * img[i] + 0.587 * img[i + 1] + 0.114 * img[i + 2];
  lum /= img.length / 16;
  const dark = lum > 140;
  c.globalAlpha = a; c.textBaseline = "alphabetic";
  c.shadowColor = dark ? "rgba(255,255,255,0.85)" : "rgba(21,24,60,0.85)"; c.shadowBlur = 8 * SC;
  c.fillStyle = dark ? PAL.navy : PAL.white; c.fillText(l.ko, x, y); c.fillText(l.ko, x, y);
  c.shadowBlur = 0; c.shadowColor = "transparent"; c.globalAlpha = 1;
}

// ------------------------------------------------------------------ glitch strips (1-3 frames, small off-palette colour bars)
const GLITCH_RATE = { C: 4.8, A: 3.0, B: 0.05, D: 0, E: 0 };
// the reference glitches almost only in the intro and verse 1 (65 of 69 events); choruses/interlude/outro stay clean
const GLITCH_SECTION = { intro: 1, verse1: 1, pre: 0.08, chorus1: 0.06, interlude: 0, bridge: 0, chorus_last: 0.06, outro: 0, end: 0 };    // tuned so tools/metrics.py counts what it counts on the reference      // events per second, from the reference measurement
const GLITCH_COLS = ["#7CFF5A", "#E9FF4A", "#46E8FF", "#FF5AC8", "#FFFFFF", "#15183C"];
function glitch(c, t, s) {
  let rate = (GLITCH_RATE[s.type] || 0) * (GLITCH_SECTION[s.section] ?? 1); const f = Math.floor(t * 15 + 1e-6); let drawn = 0;
  if (s.trans_in === "glitch" && t - s.t0 < 0.15) rate = 15 * 4;          // transition burst
  for (let k = 0; k < 2; k++) {
    const f0 = f - k; if (hash(f0, 911) > rate / 15 && !(rate > 15 && k === 0)) continue;
    const len = hash(f0, 912) < 0.12 ? 2 : 1; if (k >= len) continue;
    const R = rng(f0 * 7 + 3), nb = 1 + Math.floor(R() * 3);
    for (let b = 0; b < nb; b++) {
      const x = R() * W0 * 0.85, y = R() * H0, w = 90 + R() * 300, h = 6 + R() * 18, dx = (R() < 0.5 ? -1 : 1) * (20 + R() * 120);
      c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
      c.drawImage(cv, x * SC, y * SC, w * SC, h * SC, (x + dx) * SC, y * SC, w * SC, h * SC);      // displaced slice
      const mode = R();
      if (mode < 0.55) { c.globalAlpha = 0.75; c.fillStyle = "#A0F08C"; c.fillRect((x + dx + w * R() * 0.5) * SC, y * SC, w * (0.3 + R() * 0.5) * SC, h * SC); }
      else { c.globalCompositeOperation = "saturation"; c.fillStyle = "#808080"; c.fillRect((x + dx) * SC, y * SC, w * SC, h * SC); }
      c.restore();
      drawn++;
    }
  }
  return drawn;
}

// ------------------------------------------------------------------ scenes
function bgA(c, s, t, seed, inkX = 960, inkY = 620, inkR = 380) {
  c.fillStyle = PAL.lav; c.fillRect(-200, -200, W0 + 400, H0 + 400);
  splatter(c, inkX - 380, inkY + 160, 420, seed + 1, 16, 0.40);
  splatter(c, inkX + 420, inkY - 260, 360, seed + 2, 12, 0.35);
  splatter(c, inkX - 120, inkY - 300, 600, seed + 4, 30, 0.48, 0.1);
  splatter(c, inkX + 200, inkY + 300, 520, seed + 5, 24, 0.48, 0.1);
  halftone(c, inkX + 120, inkY - 80, inkR * 1.0, 17, PAL.mag);
  inkCluster(c, inkX, inkY, inkR, seed + 3);
}
const SCENE = {
  keyvisual(c, s, t, cam) {
    bgA(c, s, t, 101, 960, 640, 90);
    halftone(c, 1350, 380, 190, 17, PAL.mag);
    drawProps(c, BG_PROPS.key, null, t);
    pills(c, s.pills, 77, t - s.g0, { x: 0, y: 380, w: W0, h: 700 });
    drawChar(c, cam, "key", "_sil");
    drawProps(c, FG_PROPS.key, null, t);
  },
  char_wide(c, s, t, cam) {
    bgA(c, s, t, 202, 980, 560, 400);
    drawProps(c, BG_PROPS.wide, null, t);
    pills(c, s.pills, 55 + s.gid, t - s.g0);
    drawChar(c, cam, "bust");
    drawProps(c, FG_PROPS.wide, null, t);
  },
  // A: props close-up (ref: plush/syringe close-up) - our traffic light + lipstick, ink diagonal, halftone, pills
  prop_close(c, s, t, cam) {
    bgA(c, s, t, 303, 1250, 620, 400);
    drawProp(c, "bg2_traffic_light", 420, 330, 0.95, -0.35, t);
    pills(c, s.pills, 31, t - s.g0, { x: 200, y: 600, w: 1400, h: 450 });
    drawProp(c, "fg2_lipstick_long", 1440, 860, 1.05, 0.55, t);
    drawProp(c, "fg4_brush_short", 1700, 260, 1.3, -0.4, t);
  },
  // A: one long prop across the frame, the lyric band runs along it (ref: guitar neck)
  prop_band(c, s, t, cam) {
    bgA(c, s, t, 404, 760, 560, 470);
    drawProp(c, "bg3_scissors", 950, 550, 1.0, -1.15, t);
    pills(c, s.pills, 41, t - s.g0, { x: 0, y: 650, w: 900, h: 430 });
    drawProp(c, "fg3_brush_long", 1660, 780, 0.85, 0.75, t);
  },
  // A: character close-up, navy box text beside the face
  char_close(c, s, t, cam) {
    bgA(c, s, t, 505, 1300, 560, 420);
    drawChar(c, cam, "close");
  },
  black(c) { c.fillStyle = PAL.black; c.fillRect(-200, -200, W0 + 400, H0 + 400); },
  magenta(c) { c.fillStyle = PAL.mag; c.fillRect(-200, -200, W0 + 400, H0 + 400); },
  navy(c) { c.fillStyle = PAL.navy; c.fillRect(-200, -200, W0 + 400, H0 + 400); },
  char_manga(c, s, t, cam) {
    mangaBg(c);
    drawProps(c, BG_PROPS.manga, "grayscale(1) contrast(1.8)", t);
    if (s.method === "4" && !NO_TEXT) giantRowsB(c, s.lines[0], t, 300 + s.gid);
    drawChar(c, cam, "bust", "_mono");
  },
  // B: mono manga props (white paper, black screen tone), band then giant black rows
  prop_manga(c, s, t, cam) {
    mangaBg(c);
    c.filter = "grayscale(1) contrast(1.8)";
    drawProp(c, "bg3_scissors", 950, 550, 1.0, -1.15, t); drawProp(c, "fg3_brush_long", 1660, 780, 0.85, 0.75, t);
    c.filter = "none";
    if (s.method === "4" && !NO_TEXT) giantRowsB(c, s.lines[0], t, 310 + s.gid);
  },
  // A: lavender + one big magenta blot with halftone, the small text sits in its centre
  ink_centre(c, s, t, cam) {
    c.fillStyle = PAL.lav; c.fillRect(-200, -200, W0 + 400, H0 + 400);
    splatter(c, 600, 700, 700, 606 + s.gid, 24, 0.40, 0.2);
    halftone(c, 960, 520, 620, 18, PAL.mag);
    const k = easeOut3((t - s.t0) / 0.5);                   // the blot spreads in when the shot starts
    inkCluster(c, 960, 540, 330 + 40 * k, 707 + s.gid);
    pills(c, s.pills, 61 + s.gid, t - s.g0);
  },
  // C: silhouette bust sunk in ink, small vertical text both sides
  bust_ink(c, s, t, cam) {
    c.fillStyle = PAL.lav; c.fillRect(-200, -200, W0 + 400, H0 + 400);
    splatter(c, 960, 560, 760, 808, 26, 0.42, 0.2);
    halftone(c, 1180, 380, 420, 17, PAL.mag);
    inkCluster(c, 960, 640, 360, 809);
    drawChar(c, cam, "key", "_sil");
  },
  // A: props in ink with a band (chorus '零るルル')
  prop_ink(c, s, t, cam) {
    bgA(c, s, t, 909 + s.gid, 900, 560, 380);
    drawProp(c, "bg1_ribbon", 520, 420, 0.75, -0.3, t);
    drawProp(c, "fg2_lipstick_long", 1450, 700, 1.3, 0.62, t);
    pills(c, s.pills, 71 + s.gid, t - s.g0);
  },
  // A: tighter bust crop (last chorus 'さけべ')
  char_tight(c, s, t, cam) {
    bgA(c, s, t, 1010, 1100, 520, 420);
    pills(c, s.pills, 81, t - s.g0);
    drawChar(c, cam, "tight");
  },
  // A: face close-up, used once (outro)
  face_close(c, s, t, cam) {
    bgA(c, s, t, 1111, 1300, 480, 420);
    pills(c, Math.round(s.pills * 0.6), 91, t - s.g0);
    drawChar(c, cam, "face");
  },
  // E: grey character + horizontal motion blur on white (bridge)
  grey_blur(c, s, t, cam) {
    c.fillStyle = PAL.white; c.fillRect(-200, -200, W0 + 400, H0 + 400);
    const im = IMG.bust_m_grey, P = CHAR.bust, sc = P.h / im.height, w = im.width * sc;
    for (let k = -3; k <= 3; k++) { c.globalAlpha = k === 0 ? 0.55 : 0.16; c.drawImage(im, P.cx - w / 2 + k * 26, P.top, w, P.h); }
    c.globalAlpha = 1;
  },
  // E: white whip between chorus phrases
  white_blur(c, s, t, cam) {
    c.fillStyle = PAL.white; c.fillRect(-200, -200, W0 + 400, H0 + 400);
    const im = IMG.bust_m_grey, P = CHAR.bust, sc = P.h / im.height, w = im.width * sc, u = clamp((t - s.t0) / (s.t1 - s.t0));
    for (let k = -6; k <= 6; k++) { c.globalAlpha = 0.07; c.drawImage(im, P.cx - w / 2 + k * 70 + lerp(-300, 300, u), P.top, w, P.h); }
    c.globalAlpha = 1;
  },
  // D: black with a framed mono manga panel flickering in, magenta ink eats it
  black_inset(c, s, t, cam) {
    c.fillStyle = PAL.black; c.fillRect(-200, -200, W0 + 400, H0 + 400);
    const u = (t - s.t0) / (s.t1 - s.t0), on = u > 0.35 || (u > 0.2 && Math.floor(t * 15) % 2 === 0);
    if (on) {
      const x = 560, y = 330, w = 800, h = 420;
      c.fillStyle = PAL.white; c.fillRect(x + 14, y + 14, w, h);
      c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); c.fillStyle = PAL.white; c.fillRect(x, y, w, h);
      const im = IMG.bust_mono, sc = 1.15; c.drawImage(im, 960 - im.width * sc * 0.5, 20 - 640 * sc, im.width * sc, im.height * sc); c.restore();
      c.lineWidth = 6; c.strokeStyle = PAL.white; c.strokeRect(x, y, w, h);
    }
    if (u > 0.55) inkWipe(c, (u - 0.55) / 0.45, 4242, PAL.mag);
  },
};
function mangaBg(c) {
  c.fillStyle = PAL.white; c.fillRect(-200, -200, W0 + 400, H0 + 400);
  halftone(c, 960, 540, 1500, 15, "#000", (x, y) => 0.55 * clamp(1 - Math.abs((x - y * 0.6) - 500) / 700) + 0.35 * clamp((x - 1300) / 600));
}
// ink wipe: scalloped blots appear one by one on 15 fps steps and grow until they cover the frame
function inkWipePath(u, seed) {
  const R = rng(seed), p = new Path2D(), n = 9;
  const spots = [[480, 380], [1300, 640], [900, 260], [260, 860], [1620, 300], [1100, 960], [620, 720], [1740, 900], [180, 220]];
  for (let k = 0; k < n; k++) {
    const t0 = k / n * 0.75, g = clamp((u - t0) / 0.25); if (g <= 0) continue;
    const [x, y] = spots[(k + Math.floor(R() * 3)) % n], r = (300 + R() * 160) * (0.55 + 0.45 * easeOut3(g)) * (u > 0.92 ? 1.6 : 1);
    p.addPath(blobPath(x + (R() - 0.5) * 120, y + (R() - 0.5) * 120, r, seed * 13 + k, 20, 0.10));
  }
  return p;
}
function inkWipe(c, u, seed, color) {
  const q = Math.floor(clamp(u) * 15 * 0.9) / (15 * 0.9);
  c.save(); c.setTransform(SC, 0, 0, SC, 0, 0); c.fillStyle = color;
  if (q >= 0.999) c.fillRect(0, 0, W0, H0); else c.fill(inkWipePath(q, seed));
  c.restore();
}

// ------------------------------------------------------------------ lyric layer per shot (screen space, after the camera)
const TEXT_METHODS = new Set(["1", "1b", "2", "2b", "3", "5", "6"]);
// two slots per method: the 1st line of a shot takes slot 0, the next slot 1; the last two sung lines of the shot stay up
const SLOT = {
  "1b": [[110, 560], [1130, 650]],
  "2b": [[1760, 140], [260, 170]],
  "2":  [[1740, 120], [240, 150]],
  "3":  [[330, 700, -0.52], [560, 760, -0.52]],      // along the scissor blade (prop_band)
  "1":  [[1240, 610], [150, 200]],
  "5":  [[1000, 260], [1000, 260]],
};
function lyricsLayer(c, s, t) {
  let method = s.method, own = s;
  if (s.type === "D" && method === "-") {          // gap: keep the look and slot of the shot the line belongs to
    const n = SHOTS[s.i + 1], p = SHOTS[s.i - 1], id = s.lines[s.lines.length - 1];
    own = id && p && p.lines.includes(id) && TEXT_METHODS.has(p.method) ? p : n && TEXT_METHODS.has(n.method) ? n : p && TEXT_METHODS.has(p.method) ? p : null;
    method = own ? own.method : "small"; own = own || s;
  }
  const keep = s.type !== "D" && TEXT_METHODS.has(method) && method !== "6";
  const shown = s.lines.filter((id) => LYR[id] && t >= LYR[id].start - 0.02 && (keep ? t < s.t1 : t < LYR[id].end)).slice(-2);
  for (const id of shown) {
    const l = LYR[id], k = Math.max(0, own.lines.indexOf(id)) % 2, sl = (SLOT[method] || [[0, 0], [0, 0]])[k];
    switch (method) {
      case "1": textBox(c, l, t, sl[0], s.framing === "char_close" && k === 0 ? 610 : sl[1]); break;
      case "1b": textSmall(c, l, t, sl[0], sl[1]); break;
      case "2": textVertical(c, l, t, sl[0], sl[1], 40, PAL.navy); break;
      case "2b": textVertical(c, l, t, sl[0], sl[1], 38); break;
      case "3": textBand(c, l, t, sl[0], sl[1], sl[2]); break;
      case "4": if (s.type === "A") giantA(c, id, t, 500 + s.gid);
        else if (s.type === "E") { c.filter = `blur(${5 * SC}px)`; giantA(c, id, t, 520 + s.gid); c.filter = "none"; } break;
      case "5": textVertical(c, l, t, sl[0], sl[1], 36); break;
      case "6": if (/^叫べ/.test(l.ja)) textMagenta(c, l.ja, k ? 760 : 120, k ? 980 : 860, 170, -0.18);
        else if ([...l.ja].length > 9) splitTwo(l.ja, 9).forEach(([p], r) => textMagenta(c, p, 100 + r * 260, 790 + r * 150, 120, -0.12));
        else textMagenta(c, l.ja, 140, 820, 150, -0.2); break;
      default: textSmall(c, l, t, 700, 520, 34, s.type === "E" ? PAL.navy : PAL.white);
    }
  }
}
function creditLayer(c, s, t) {
  const items = D.credits.items.filter((i) => i.where === (s.section === "outro" ? "outro" : "interlude"));
  if (!items.length) return;
  const k = Math.min(items.length - 1, Math.floor(((t - s.t0) / (s.t1 - s.t0)) * items.length)), it = items[k];
  const R = rng(900 + k), x = 60 + R() * 100, y = 790 + R() * 40;
  slanted(c, x, y, -0.2, () => {
    c.fillStyle = PAL.mag; c.textBaseline = "alphabetic"; shadowOn(c, 215);
    c.font = `900 italic 215px ${FONT.en}`; c.fillText(it.label, 0, 0); noteBox(c, 0, -185, c.measureText(it.label).width, 215);
    c.font = isLatin(it.name) ? `900 italic 240px ${FONT.en}` : jpFont(200); c.fillText(it.name, 330, 215); noteBox(c, 330, 20, c.measureText(it.name).width, 215); shadowOff(c);
  });
}
function titleLayer(c, s) {
  const outro = s && s.section === "outro";
  slanted(c, outro ? 560 : 960, outro ? 900 : 600, -0.10, () => {
    c.font = jpFont(230); c.textAlign = "center"; c.fillStyle = outro ? PAL.mag : PAL.white; if (outro) shadowOn(c, 230);
    c.fillText(D.credits.title, 0, 0); shadowOff(c); noteBox(c, -330, -200, 660, 230);
    c.font = `900 italic 140px ${FONT.en}`; c.fillStyle = PAL.mag; shadowOn(c, 140); c.fillText("Venom", 120, 110); shadowOff(c);
    c.font = jpFont(30, 700); c.fillStyle = outro ? PAL.navy : PAL.white; c.fillText(D.credits.subtitle, 150, 175); c.textAlign = "left";
  });
}

// ------------------------------------------------------------------ frame
function pictureScene(s, t) {
  const cam = camera(s, t), scene = SCENE[s.framing];
  // props float less where the reference camera is still (chorus, credits), more where it travels (verse)
  FLOAT_AMP = s.framing === "keyvisual" ? 0.7 : s.camera === "fast_decel" ? 1.4 : 0.5;
  const moving = s.camera === "fast_decel";
  PARX = moving ? (cam.x - (camera(s, s.g1 - 0.01).x)) * 0.35 : 0; PARY = moving ? cam.y * 0.35 : 0;
  ctx.setTransform(SC, 0, 0, SC, 0, 0);
  if (scene) { ctx.save(); applyCam(ctx, cam); scene(ctx, s, t, cam); ctx.restore(); }
  return cam;
}
function pictureText(s, t, cam) {
  ctx.setTransform(SC, 0, 0, SC, 0, 0);
  if (NO_TEXT) return;
  if (s.method === "title") titleLayer(ctx, s);
  else if (s.method === "credit") creditLayer(ctx, s, t);
  else if (!(s.method === "4" && s.type === "B")) {
    ctx.save(); if (s.camera === "fast_decel" && s.method !== "4") ctx.translate(cam.x * 0.3, cam.y * 0.3);   // small lyric text slides with the picture
    lyricsLayer(ctx, s, t); ctx.restore();
  }
}
const WIPE_IN = 0.5;   // cross ink wipe into a different picture
function render(tReal) {
  const t = Math.floor(tReal * 15 + 1e-6) / 15;
  TEXTBOX.length = 0; EYES = []; CUTS.length = 0;
  const s = shotAt(t), p = SHOTS[s.i - 1];
  ctx.setTransform(SC, 0, 0, SC, 0, 0);
  ctx.fillStyle = PAL.black; ctx.fillRect(0, 0, W0, H0);
  let cam;
  if (s.trans_in === "ink_wipe" && p && p.framing === s.framing) {            // blots spread over the same picture
    cam = pictureScene(s, t); inkWipe(ctx, (t - s.t0) / (s.t1 - s.t0), 31 * s.i, PAL.mag);
  } else if (s.trans_in === "ink_wipe" && p && t - s.t0 < WIPE_IN) {            // the next picture arrives inside the blots
    pictureScene(p, t); EYES = [];
    ctx.save(); ctx.setTransform(SC, 0, 0, SC, 0, 0); ctx.clip(inkWipePath(Math.floor(((t - s.t0) / WIPE_IN) * 15 * WIPE_IN) / (15 * WIPE_IN), 37 * s.i));
    cam = pictureScene(s, t); ctx.restore();
  } else if (s.framing === "black_ink" && p) {                                    // ending: black blots close the last picture
    cam = pictureScene(p, t); inkWipe(ctx, (t - s.t0) / (s.t1 - s.t0), 4343, PAL.black);
  } else cam = pictureScene(s, t);
  pictureText(s, t, cam || { x: 0, y: 0, z: 1 });
  if (s.type !== "D" && (s.trans_in === "flash_magenta" || s.trans_in === "flash_navy") && t - s.t0 < 0.1) {
    ctx.setTransform(SC, 0, 0, SC, 0, 0);
    ctx.fillStyle = s.trans_in === "flash_magenta" ? PAL.mag : PAL.navy; ctx.fillRect(0, 0, W0, H0);
    pictureText(s, t, { x: 0, y: 0, z: 1 });
  }
  ctx.setTransform(SC, 0, 0, SC, 0, 0);
  s._glitch = glitch(ctx, t, s);
  if (s.framing === "grey_blur") bridgeSlices(ctx, t);
  subtitle(ctx, tReal);
  return s;
}
// bridge: magenta horizontal slice glitch (reference E section)
function bridgeSlices(c, t) {
  const f = Math.floor(t * 15 + 1e-6); if (hash(f, 77) > 0.35) return;
  const R = rng(f * 3 + 1);
  for (let k = 0; k < 1 + Math.floor(R() * 3); k++) {
    const y = R() * H0, h = 10 + R() * 40, dx = (R() - 0.5) * 160;
    c.drawImage(cv, 0, y * SC, cv.width, h * SC, dx * SC, y * SC, cv.width, h * SC);
    c.globalAlpha = 0.85; c.fillStyle = PAL.mag; c.fillRect(R() * W0 * 0.7, y, 200 + R() * 500, h * 0.5); c.globalAlpha = 1;
  }
}

// ------------------------------------------------------------------ API
window.init = async function (width = 960, opts = {}) {
  OPTS = opts; if (opts.enFont) EN_FONT = opts.enFont;
  cv = document.getElementById("c"); cv.width = width; cv.height = Math.round((width * 9) / 16); SC = width / W0;
  ctx = cv.getContext("2d", { willReadFrequently: true });
  await loadFonts();
  const names = ["bust", "bust_m", "body"].flatMap((n) => [n, n + "_sil", n + "_mono", n + "_monom", n + "_grey"]).concat(Object.keys(D.meta.props));
  await Promise.all(names.map(loadImg));
  return { fallbacks: fallbackChars(), shots: SHOTS.length };
};
window.needsBlur = function (t) { const s = shotAt(t); return !!OPTS.post && (s.camera !== "static"); };
window.seek = function (t) { const s = render(t); return { shot: s.i, framing: s.framing, glitch: s._glitch }; };
window.glitchTimes = function (a, b) { const out = []; for (let f = Math.ceil(a * 30); f < b * 30; f++) { const t = f / 30, s = shotAt(t); if (glitchCount(t, s)) out.push(t); } return out; };
function glitchCount(t, s) { const rate = (GLITCH_RATE[s.type] || 0) * (GLITCH_SECTION[s.section] ?? 1), f = Math.floor(t * 15 + 1e-6); for (let k = 0; k < 2; k++) { const f0 = f - k; if (hash(f0, 911) <= rate / 15 && k < (hash(f0, 912) < 0.12 ? 2 : 1)) return 1; } return 0; }
// camera speed per shot thirds straight from the engine (px/s at 1080p, translation + zoom at the frame edge)
window.camSpeeds = function (a, b) {
  const out = [];
  for (const sh of SHOTS) {
    if (sh.t1 <= a || sh.t0 >= b || sh.type === "D" || sh.trans_in === "text") continue;
    const g1 = sh.g1, n = Math.max(3, Math.round((g1 - sh.t0) * 15)), v = [];
    for (let i = 0; i < n; i++) {
      const t0 = sh.t0 + i / 15, c0 = camera(sh, t0), c1 = camera(sh, t0 + 1 / 15);
      v.push(Math.hypot(c1.x - c0.x, c1.y - c0.y) * 15 + Math.abs(c1.z - c0.z) * 15 * 960);
    }
    const k = Math.floor(n / 3), m = (x) => +(x.reduce((p, q) => p + q, 0) / x.length).toFixed(1);
    out.push({ t0: sh.t0, framing: sh.framing, camera: sh.camera, thirds: [m(v.slice(0, k)), m(v.slice(k, 2 * k)), m(v.slice(2 * k))] });
  }
  return out;
};
// any canvas-cut prop edge inside the frame? (sampled along each segment, 6 px margin)
window.cutCheck = function (a, b) {
  const bad = [];
  for (let f = Math.ceil(a * 15); f < b * 15; f++) {
    const t = f / 15; render(t);
    for (const [x0, y0, x1, y1, n] of CUTS) for (let k = 0; k <= 20; k++) {
      const x = x0 + (x1 - x0) * k / 20, y = y0 + (y1 - y0) * k / 20;
      if (x > -6 && x < W0 + 6 && y > -6 && y < H0 + 6) { bad.push([+t.toFixed(2), shotAt(t).i, shotAt(t).framing, n]); break; }
    }
  }
  return bad;
};
// lyric check: render with and without the lyric layers; glyph pixels = pixels the text changed.
// contrast = mean |luma(with) - luma(without)| over glyph pixels; eyes = glyph boxes on the eye boxes
let NO_TEXT = false;
window.textCheck = function (t) {
  NO_TEXT = true; render(t); const a = ctx.getImageData(0, 0, cv.width, cv.height).data; NO_TEXT = false;
  render(t); const b = ctx.getImageData(0, 0, cv.width, cv.height).data;
  let n = 0, sum = 0;
  for (let i = 0; i < a.length; i += 4) {
    const la = 0.299 * a[i] + 0.587 * a[i + 1] + 0.114 * a[i + 2], lb = 0.299 * b[i] + 0.587 * b[i + 1] + 0.114 * b[i + 2], d = Math.abs(la - lb);
    if (d > 12) { n++; sum += d; }
  }
  const hit = (p, q) => p[0] < q[0] + q[2] && q[0] < p[0] + p[2] && p[1] < q[1] + q[3] && q[1] < p[1] + p[3];
  return { textPx: n, contrast: n ? sum / n : 0, eyeHits: TEXTBOX.filter((tb) => EYES.some((e) => hit(tb, e))).length, shot: shotAt(t).i };
};
window.probe = function (t) { render(t); return { text: TEXTBOX.slice(), eyes: EYES.slice() }; };
