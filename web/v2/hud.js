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

function drawHUD2(ctx, t, a, drift) {
  if (a <= 0) return;
  ctx.save();
  ctx.strokeStyle = `rgba(236,236,232,${0.75 * a})`; ctx.fillStyle = `rgba(236,236,232,${0.8 * a})`; ctx.lineWidth = 1.5;
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
  ctx.font = "300 46px UI"; ctx.textBaseline = "alphabetic"; ctx.fillStyle = `rgba(236,236,232,${0.78 * a})`;
  ctx.letterSpacing = "3px"; ctx.fillText("SLOWDOWNER", x0 + 26, 892); ctx.letterSpacing = "0px";
  ctx.font = "300 11px UI"; ctx.fillStyle = `rgba(236,236,232,${0.45 * a})`;
  DUMMY.forEach((s, i) => ctx.fillText(s, x0 + 28, 918 + i * 17));
  ctx.restore();
  // thin crossing lines / arcs over the picture (slow drift with the camera)
  ctx.save(); ctx.strokeStyle = `rgba(240,240,236,${0.5 * a})`; ctx.lineWidth = 1.4;
  const d = drift || 0;
  ctx.beginPath(); ctx.moveTo(-40, 300 + d * 0.6); ctx.bezierCurveTo(500, 160 + d, 1100, 80 + d, 1960, -40 + d * 0.4); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(-40, 1000 - d * 0.3); ctx.bezierCurveTo(700, 820, 1400, 760 - d, 1960, 640 - d * 0.5); ctx.stroke();
  ctx.beginPath(); ctx.arc(1500 + d, 1300, 980, Math.PI * 1.08, Math.PI * 1.62); ctx.stroke();
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
