// HUD layer, modelled on the reference: thin frame, top tick ruler, side sparkles, bottom-left title with dummy text,
// bottom-right stacked lines, corner crosses, and thin lines/arcs crossing the picture. 1-2 px, white, 40-80 % opacity.
"use strict";
const BAR = 54;                         // permanent thin letterbox (reference frames are ~5 % top/bottom)
const FR = { x0: 50, y0: BAR + 26, x1: W - 50, y1: H - BAR - 26 };
const DUMMY = [
  "I am the most beloved monster born into this world",
  "That place was shaken off by obedient puppets in a disgusting era",
  "The spider that threw a red thread, the hunter who got tangled as expected",
  "Please give me a reason to live calmly for the rest of my life, doctor",
  "I'm a monster born into this vague new and old world",
];

function sparkle(ctx, x, y, r) { // thin 4-point star
  ctx.beginPath(); ctx.moveTo(x, y - r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.quadraticCurveTo(x, y, x, y + r);
  ctx.quadraticCurveTo(x, y, x - r, y); ctx.quadraticCurveTo(x, y, x, y - r); ctx.fill();
}

function drawHUD2(ctx, t, a, drift, dark) {
  if (a <= 0) return;
  const C = dark ? "40,40,42" : "236,236,232";
  ctx.save();
  ctx.strokeStyle = `rgba(${C},${0.75 * a})`; ctx.fillStyle = `rgba(${C},${0.8 * a})`; ctx.lineWidth = 1.5;
  const { x0, y0, x1, y1 } = FR;
  // frame: top line broken by the ruler, sides, bottom centre line
  ctx.beginPath();
  ctx.moveTo(x0, y0); ctx.lineTo(680, y0); ctx.moveTo(1240, y0); ctx.lineTo(x1, y0);
  ctx.moveTo(x0, y0); ctx.lineTo(x0, y1); ctx.moveTo(x1, y0); ctx.lineTo(x1, y1);
  ctx.moveTo(560, y1); ctx.lineTo(1360, y1);
  ctx.stroke();
  // top ruler ticks
  for (let i = 0; i <= 56; i++) { const x = 700 + i * 9.6; ctx.fillRect(x, y0 - 9, 1.2, i % 8 === 0 ? 20 : 12); }
  // side sparkles (3 stacked, both sides)
  for (const x of [x0 - 1, x1 + 1]) for (let k = 0; k < 3; k++) sparkle(ctx, x, 480 + k * 56, 9);
  // corner crosses
  ctx.lineWidth = 1.3;
  for (const [x, y] of [[x0 + 22, y0 + 22], [x1 - 22, y0 + 22], [x0 + 22, y1 - 22], [x1 - 22, y1 - 22]]) {
    ctx.beginPath(); ctx.moveTo(x - 8, y); ctx.lineTo(x + 8, y); ctx.moveTo(x, y - 8); ctx.lineTo(x, y + 8); ctx.stroke();
  }
  // bottom-right stacked thin lines
  ctx.lineWidth = 1.2;
  [[1570, 900], [1620, 922], [1500, 944], [1470, 966]].forEach(([xs, y]) => { ctx.beginPath(); ctx.moveTo(xs, y); ctx.lineTo(x1 - 30, y); ctx.stroke(); });
  // bottom-left title + unreadable dummy block
  ctx.font = "300 46px UI"; ctx.textBaseline = "alphabetic"; ctx.fillStyle = `rgba(${C},${0.78 * a})`;
  ctx.letterSpacing = "3px"; ctx.fillText("SLOWDOWNER", x0 + 26, 892); ctx.letterSpacing = "0px";
  ctx.font = "300 11px UI"; ctx.fillStyle = `rgba(${C},${0.45 * a})`;
  DUMMY.forEach((s, i) => ctx.fillText(s, x0 + 28, 918 + i * 17));
  ctx.restore();
}
// Geometric layer over the picture: thin lines and circles that boil like drawn-on paper (12 fps jitter)
// and slowly rotate. Used only in quiet sections (interludes, title/credits cards).
function boil(t, k, amp = 1.6) { const f = Math.floor(t * 12); return (hash2(f, k) - 0.5) * 2 * amp; }
function wobblyPath(ctx, pts, t, seed) {
  ctx.beginPath();
  pts.forEach(([x, y], i) => { const nx = x + boil(t, seed + i * 2), ny = y + boil(t, seed + i * 2 + 1); i ? ctx.lineTo(nx, ny) : ctx.moveTo(nx, ny); });
  ctx.stroke();
}
function sampleBezier(p0, p1, p2, p3, n = 24) {
  const o = []; for (let i = 0; i <= n; i++) { const u = i / n, v = 1 - u;
    o.push([v * v * v * p0[0] + 3 * v * v * u * p1[0] + 3 * v * u * u * p2[0] + u * u * u * p3[0], v * v * v * p0[1] + 3 * v * v * u * p1[1] + 3 * v * u * u * p2[1] + u * u * u * p3[1]]); }
  return o;
}
function drawGeo(ctx, t, a, drift, dark) {
  if (a <= 0) return;
  const C = dark ? "40,40,42" : "240,240,236", d = drift || 0;
  ctx.save(); ctx.strokeStyle = `rgba(${C},${0.5 * a})`; ctx.fillStyle = `rgba(${C},${0.55 * a})`; ctx.lineWidth = 1.4; ctx.lineJoin = "round";
  wobblyPath(ctx, sampleBezier([-40, 300 + d * 0.6], [500, 160 + d], [1100, 80 + d], [1960, -40 + d * 0.4]), t, 100);
  wobblyPath(ctx, sampleBezier([-40, 1000 - d * 0.3], [700, 820], [1400, 760 - d], [1960, 640 - d * 0.5]), t, 200);
  // rotating circles: a large arc with tick marks and a small dashed ring
  const rot = t * 0.12;
  const ring = (cx, cy, r, a0, a1, seed, ticks) => {
    const pts = []; for (let i = 0; i <= 64; i++) { const an = a0 + (a1 - a0) * i / 64 + rot; pts.push([cx + Math.cos(an) * r, cy + Math.sin(an) * r]); }
    wobblyPath(ctx, pts, t, seed);
    for (let k = 0; k < ticks; k++) { const an = rot * 1.6 + k * Math.PI * 2 / ticks; const x = cx + Math.cos(an) * r, y = cy + Math.sin(an) * r;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(cx + Math.cos(an) * (r + 12), cy + Math.sin(an) * (r + 12)); ctx.stroke(); }
  };
  ring(1500 + d, 1300, 980, Math.PI * 1.08, Math.PI * 1.62, 300, 0);
  ctx.setLineDash([6, 10]); ring(380, 300, 210, 0, Math.PI * 2, 400, 0); ctx.setLineDash([]);
  ring(380, 300, 250, 0, Math.PI * 1.3, 500, 12);
  ctx.restore();
}

function drawBars(ctx, extra = 0) { // permanent thin letterbox, thicker in the intro
  const b = BAR + extra; ctx.fillStyle = "#050505"; ctx.fillRect(0, 0, W, b); ctx.fillRect(0, H - b, W, b);
}

// Title card: black box + white text (censor-bar look)
function drawTitleBox(ctx, a, cx = 960, cy = 520) {
  if (a <= 0) return;
  ctx.save(); ctx.globalAlpha = a;
  ctx.font = "300 40px LyricMincho"; const w = ctx.measureText("スロウダウナー").width + 56;
  ctx.fillStyle = "#0b0b0c"; ctx.fillRect(cx - w / 2, cy - 30, w, 60);
  ctx.fillStyle = "#e9e9e6"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("スロウダウナー", cx, cy + 2);
  ctx.restore();
}
