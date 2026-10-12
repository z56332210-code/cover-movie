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
function splatter(c, cx, cy, r, seed, n = 18, alpha = 0.45) {
  const R = rng(seed); c.save(); c.fillStyle = PAL.mag;
  for (let i = 0; i < n; i++) {
    const a = R() * 6.283, d = Math.sqrt(R()) * r, rr = 10 + R() * r * 0.16;
    c.globalAlpha = alpha * (0.35 + R() * 0.65);
    c.fill(blobPath(cx + Math.cos(a) * d, cy + Math.sin(a) * d, rr, seed * 7 + i, 10, 0.18));
  }
  c.globalAlpha = 0.9;
  for (let i = 0; i < n * 3; i++) {
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
function drawImg(c, name, cx, cy, s, rot = 0, alpha = 1) {
  const im = IMG[name]; if (!im) return;
  c.save(); c.globalAlpha = alpha; c.translate(cx, cy); if (rot) c.rotate(rot);
  c.drawImage(im, (-im.width * s) / 2, (-im.height * s) / 2, im.width * s, im.height * s); c.restore();
}

// ------------------------------------------------------------------ camera
function camera(s, t) {
  const g = Math.max(0.001, s.g1 - s.g0), tau = t - s.g0, u = clamp(tau / g);
  const dec = 1 - Math.exp(-tau / 0.55);                    // fast right after the cut, then settles (ref: ~180 -> 50 -> 15 px/s)
  switch (s.camera) {
    case "fast_decel": { const R = rng(s.gid * 13 + 5), dir = R() < 0.5 ? -1 : 1; return { z: lerp(1.10, 1.0, dec) + 0.01 * u, x: dir * lerp(110, 0, dec), y: lerp(-30, 0, dec) }; }
    case "slow_push": return { z: 1.0 + 0.05 * u, x: 0, y: 0 };
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
  key:   { img: "bust_m", cx: 960, top: 70, h: 1450 },    // key visual silhouette
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
  wide: [["bg1_ribbon", 430, 330, 0.40, -0.50], ["bg3_scissors", 1010, 760, 0.46, -0.55], ["bg2_traffic_light", 1560, 330, 0.40, 0.42]],
  key:  [["bg1_ribbon", 380, 300, 0.44, -0.55], ["bg3_scissors", 980, 820, 0.52, -0.50], ["bg2_traffic_light", 1600, 300, 0.44, 0.45]],
  manga:[["bg3_scissors", 1500, 640, 0.48, 0.65]],
};
const FG_PROPS = {
  wide: [["fg3_brush_long", 190, 150, 0.46, -0.9], ["fg2_lipstick_long", 1800, 600, 0.50, 0.9], ["fg5_foundation", 1640, 960, 0.52, -0.2],
         ["fg1_lipstick_short", 300, 960, 0.60, 0.7], ["fg4_brush_short", 90, 640, 0.50, 0.3]],
  key:  [["fg3_brush_long", 150, 130, 0.52, -0.9], ["fg2_lipstick_long", 1830, 640, 0.56, 0.9], ["fg5_foundation", 1680, 980, 0.58, -0.2],
         ["fg1_lipstick_short", 280, 990, 0.66, 0.7], ["fg4_brush_short", 70, 620, 0.55, 0.3]],
};
function drawProps(c, list, filter) {
  if (filter) c.filter = filter;
  list.forEach(([n, x, y, s, r]) => drawImg(c, n, x, y, s, r));
  if (filter) c.filter = "none";
}

// ------------------------------------------------------------------ text
const jpFont = (px, w = 900) => `${w} ${px}px ${w === 900 ? FONT.jp : FONT.jp7}`;
const isLatin = (s) => /^[\x20-\x7e]+$/.test(s);
function shadowOn(c, px) { c.shadowColor = PAL.navy; c.shadowOffsetX = px * 0.025 * SC; c.shadowOffsetY = px * 0.02 * SC; c.shadowBlur = 0; }
function shadowOff(c) { c.shadowColor = "transparent"; c.shadowOffsetX = c.shadowOffsetY = 0; }
function slanted(c, x, y, rot, fn) { c.save(); c.translate(x, y); c.rotate(rot); c.transform(1, 0, -0.22, 1, 0, 0); fn(); c.restore(); }
const visibleLine = (id, t) => { const l = LYR[id]; return l && t >= l.start - 0.02 && t < l.end; };
const TEXTBOX = [];   // screen-space boxes of drawn lyric text (for the eye-overlap check)
function noteBox(c, x, y, w, h) { const m = c.getTransform(); const pts = [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].map(([a, b]) => [m.a * a + m.c * b + m.e, m.b * a + m.d * b + m.f]); const xs = pts.map((p) => p[0] / SC), ys = pts.map((p) => p[1] / SC); TEXTBOX.push([Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)]); }

// method 1: navy box + white text
function textBox(c, str, x, y, px = 30) {
  c.font = jpFont(px, 700); const lines = splitTwo(str), lw = Math.max(...lines.map((l) => c.measureText(l).width));
  const pad = px * 0.55, lh = px * 1.45, w = lw + pad * 2, h = lines.length * lh + pad * 1.2;
  c.fillStyle = PAL.navy; c.fillRect(x, y, w, h); noteBox(c, x, y, w, h);
  c.fillStyle = PAL.white; c.textBaseline = "middle";
  lines.forEach((l, i) => fillSpaced(c, l, x + pad, y + pad * 0.6 + lh * (i + 0.5), px * 0.12));
}
function fillSpaced(c, s, x, y, sp) { for (const ch of s) { c.fillText(ch, x, y); x += c.measureText(ch).width + sp; } }
function splitTwo(s) {
  s = s.replace(/[（）]/g, (m) => m);
  if (s.length <= 12) return [s];
  const brk = s.search(/[」だなはでもの]/g); const cut = brk > 4 && brk < s.length - 3 ? brk + 1 : Math.ceil(s.length / 2);
  return [s.slice(0, cut), s.slice(cut)];
}
// 1b: small white horizontal; 2b: small white vertical; 2: vertical on navy/black bar
function textSmall(c, str, x, y, px = 30, color = PAL.white) {
  c.font = jpFont(px, 700); c.fillStyle = color; c.textBaseline = "middle";
  splitTwo(str).forEach((l, i) => { fillSpaced(c, l, x, y + i * px * 1.6, px * 0.18); noteBox(c, x, y - px / 2 + i * px * 1.6, c.measureText(l).width * 1.2, px); });
}
function textVertical(c, str, x, y, px = 30, bar = null, color = PAL.white) {
  c.font = jpFont(px, 700); const step = px * 1.12, chars = [...str.replace(/\s/g, "")];
  if (bar) { c.fillStyle = bar; c.fillRect(x - px * 0.75, y - px * 0.9, px * 1.5, step * chars.length + px * 0.8); }
  noteBox(c, x - px * 0.75, y - px * 0.9, px * 1.5, step * chars.length + px * 0.8);
  c.fillStyle = color; c.textAlign = "center"; c.textBaseline = "middle";
  chars.forEach((ch, i) => { const rot = /[ーー～（）「」]/.test(ch); c.save(); c.translate(x, y + i * step); if (rot) c.rotate(Math.PI / 2); c.fillText(ch, 0, 0); c.restore(); });
  c.textAlign = "left";
}
// 3: diagonal band along a prop; words revealed as sung
function textBand(c, id, t, x, y, rot, px = 30) {
  const l = LYR[id]; c.save(); c.translate(x, y); c.rotate(rot); c.font = jpFont(px, 700);
  const n = [...l.ja].filter((ch, i) => l.chars[i] <= t + 0.05).length, shown = [...l.ja].slice(0, Math.max(1, n)).join("");
  const w = c.measureText(l.ja).width + l.ja.length * px * 0.2 + px * 1.4;
  c.fillStyle = PAL.navy; c.fillRect(-px * 0.7, -px * 0.85, w, px * 1.7); noteBox(c, -px * 0.7, -px * 0.85, w, px * 1.7);
  c.fillStyle = PAL.white; c.textBaseline = "middle"; fillSpaced(c, shown, 0, 0, px * 0.2); c.restore();
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
      const col = wd.echo ? PAL.navy : PAL.mag;
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
const GLITCH_RATE = { C: 1.65, A: 0.17, B: 0.04, D: 0, E: 0 };      // events per second, from the reference measurement
const GLITCH_COLS = ["#7CFF5A", "#E9FF4A", "#46E8FF", "#FF5AC8", "#FFFFFF", "#15183C"];
function glitch(c, t, s) {
  const rate = GLITCH_RATE[s.type] || 0, f = Math.floor(t * 30); let drawn = 0;
  for (let k = 0; k < 4; k++) {
    const f0 = f - k; if (hash(f0, 911) > rate / 30) continue;
    const len = 1 + Math.floor(hash(f0, 912) * 3); if (k >= len) continue;
    const R = rng(f0 * 7 + 3), nb = 1 + Math.floor(R() * 3);
    for (let b = 0; b < nb; b++) {
      let x = R() * W0 * 0.9, y = R() * H0, w = 60 + R() * 220, h = 4 + R() * 12;
      for (let x1 = x; x1 < x + w;) { const sw = 6 + R() * 40; c.fillStyle = GLITCH_COLS[Math.floor(R() * GLITCH_COLS.length)]; c.fillRect(x1, y, sw, h); x1 += sw; }
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
  halftone(c, inkX + 120, inkY - 80, inkR * 1.8, 17, PAL.mag);
  inkCluster(c, inkX, inkY, inkR, seed + 3);
}
const SCENE = {
  keyvisual(c, s, t, cam) {
    bgA(c, s, t, 101, 960, 600, 360);
    drawProps(c, BG_PROPS.key);
    pills(c, s.pills, 77, t - s.g0, { x: 0, y: 380, w: W0, h: 700 });
    drawChar(c, cam, "key", "_sil");
    drawProps(c, FG_PROPS.key);
  },
  char_wide(c, s, t, cam) {
    bgA(c, s, t, 202, 980, 560, 400);
    drawProps(c, BG_PROPS.wide);
    pills(c, s.pills, 55 + s.gid, t - s.g0);
    drawChar(c, cam, "bust");
    drawProps(c, FG_PROPS.wide);
  },
  char_manga(c, s, t, cam) {
    c.fillStyle = PAL.white; c.fillRect(-200, -200, W0 + 400, H0 + 400);
    halftone(c, 960, 540, 1500, 15, "#000", (x, y) => 0.55 * clamp(1 - Math.abs((x - y * 0.6) - 500) / 700) + 0.35 * clamp((x - 1300) / 600));
    drawProps(c, BG_PROPS.manga, "grayscale(1) contrast(1.8)");
    giantRowsB(c, s.lines.find((id) => D.typo[String(id)]) || s.lines[0], t, 300 + s.gid);
    drawChar(c, cam, "bust", "_mono");
  },
};

// ------------------------------------------------------------------ lyric layer per shot (screen space, after the camera)
function lyricsLayer(c, s, t) {
  for (const id of s.lines) {
    if (!visibleLine(id, t)) continue;
    const l = LYR[id];
    switch (s.method) {
      case "1": textBox(c, l.ja, 1320, 300); break;
      case "1b": textSmall(c, l.ja, 120, 640); break;
      case "2": textVertical(c, l.ja, 1700, 140, 34, PAL.navy); break;
      case "2b": textVertical(c, l.ja, 1700, 160, 30); break;
      case "3": textBand(c, id, t, 300, 760, -0.42); break;
      case "4": if (s.type === "A") giantA(c, id, t, 500 + s.gid); break;
      case "5": textVertical(c, l.ja, 960, 300, 30); break;
      case "6": textMagenta(c, l.ja, 140, 820, 150, -0.2); break;
      default: textSmall(c, l.ja, 760, 540, 26);
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
function titleLayer(c) {
  slanted(c, 960, 600, -0.10, () => {
    c.font = jpFont(230); c.textAlign = "center"; c.fillStyle = PAL.white; c.fillText(D.credits.title, 0, 0); noteBox(c, -330, -200, 660, 230);
    c.font = `900 italic 140px ${FONT.en}`; c.fillStyle = PAL.mag; shadowOn(c, 140); c.fillText("Venom", 120, 110); shadowOff(c);
    c.font = jpFont(30, 700); c.fillStyle = PAL.white; c.fillText(D.credits.subtitle, 150, 175); c.textAlign = "left";
  });
}

// ------------------------------------------------------------------ frame
function render(t) {
  TEXTBOX.length = 0; EYES = [];
  const s = shotAt(t), cam = camera(s, t);
  ctx.setTransform(SC, 0, 0, SC, 0, 0);
  ctx.fillStyle = PAL.black; ctx.fillRect(0, 0, W0, H0);
  const scene = SCENE[s.framing];
  if (scene) { ctx.save(); applyCam(ctx, cam); scene(ctx, s, t, cam); ctx.restore(); }
  if (s.method === "title") titleLayer(ctx);
  else if (s.method === "credit") creditLayer(ctx, s, t);
  else if (!(s.method === "4" && s.type === "B")) lyricsLayer(ctx, s, t);
  s._glitch = glitch(ctx, t, s);
  subtitle(ctx, t);
  return s;
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
window.seek = function (t) { const s = render(t); return { shot: s.i, framing: s.framing, glitch: s._glitch }; };
window.glitchTimes = function (a, b) { const out = []; for (let f = Math.ceil(a * 30); f < b * 30; f++) { const t = f / 30, s = shotAt(t); if (glitchCount(t, s)) out.push(t); } return out; };
function glitchCount(t, s) { const rate = GLITCH_RATE[s.type] || 0, f = Math.floor(t * 30); for (let k = 0; k < 4; k++) { const f0 = f - k; if (hash(f0, 911) <= rate / 30 && k < 1 + Math.floor(hash(f0, 912) * 3)) return 1; } return 0; }
window.probe = function (t) { render(t); return { text: TEXTBOX.slice(), eyes: EYES.slice() }; };
