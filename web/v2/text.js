// Japanese typography, three levels (scene_plan tokens.text_levels). Thin mincho only.
// Characters appear one by one on their sung time: fade + blur -> sharp. Exit: blur + fade. No bounce.
"use strict";
const RED = "rgba(179,18,43,A)";
let INK_DARK = 0;   // 0..1: lyrics darken while the picture flashes to white, so they never disappear in a transition
Object.defineProperty(globalThis, "INK_W", { get: () => { const v = Math.round(233 - (233 - 38) * INK_DARK); return `rgba(${v},${v},${v - 2},A)`; } });
const isKana = (c) => /[぀-ヿ]/.test(c);
const SMALL_K = new Set([..."ぁぃぅぇぉっゃゅょァィゥェォッャュョ"]);
const VROT = new Set(["ー", "〜", "…"]);
let POST = true;

function glyphAlpha(line, i, t, enterDur = 0.28, spec) {
  // A level: quick sequential fade from the line start (reference); B/C: on the sung time of each character
  const tc = spec && spec.lvl === "A" ? line.start - 0.08 + i * 0.045 : line.chars[Math.min(i, line.chars.length - 1)] - 0.05;
  const end = spec && spec.holdUntil ? L2(spec.holdUntil).end : line.end;
  const a = clamp((t - tc) / enterDur), x = clamp((t - (end - 0.35)) / 0.35);
  return { a: a * (1 - x), blur: (1 - easeOut(a)) * 12 + x * 10 };
}
function drawGlyph(ctx, ch, x, y, size, weight, color, a, blur, rot = 0, shade = 0) {
  if (a <= 0.003) return;
  ctx.save(); ctx.translate(x, y); if (rot) ctx.rotate(rot);
  if (shade) { ctx.shadowColor = `rgba(0,0,0,${(shade * a).toFixed(3)})`; ctx.shadowBlur = Math.max(6, size * 0.06); }
  ctx.font = `${weight} ${size}px LyricMincho`;
  if (POST && blur > 0.4) ctx.filter = `blur(${(blur * size / 120).toFixed(1)}px)`;
  ctx.fillStyle = color.replace("A", a.toFixed(3)); ctx.fillText(ch, 0, 0);
  ctx.restore();
}
const INK_D = "rgba(34,34,36,A)";   // dark ink for lyrics placed on the bright backdrop
const colorOf = (spec, ch, idx) => (spec.red && (spec.red === ch || spec.red === idx) ? RED : spec.ink === "dark" ? INK_D : INK_W);

// Level A: small lyric; vertical columns or a single horizontal line. Optional mirrored copy (reference).
function drawA(ctx, spec, line, t) {
  const size = spec.size || 40, w = spec.weight || 400, chars = [...line.ja];
  const drawSet = (mirror) => {
    ctx.save(); ctx.translate(mirror ? mirror.x : spec.x, mirror ? mirror.y : spec.y);
    if (mirror) ctx.scale(-1, 1);
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const amul = mirror ? 0.55 : 1;
    if (spec.layout === "vert") {
      const cols = spec.cols || [line.ja]; let i = 0;
      cols.forEach((col, ci) => {
        [...col].forEach((ch, k) => {
          const g = glyphAlpha(line, i, t, 0.4, spec); let dx = 0, dy = 0;
          if (SMALL_K.has(ch)) { dx = size * 0.1; dy = -size * 0.1; }
          drawGlyph(ctx, ch, -ci * size * (spec.gap || 1.5) + dx, k * size * 1.12 + dy, size, w, colorOf(spec, ch, i), g.a * amul, g.blur, VROT.has(ch) ? Math.PI / 2 : 0, spec.ink === "dark" ? 0 : 0.95);
          i++;
        });
      });
    } else {
      ctx.font = `${w} ${size}px LyricMincho`; const track = size * 0.08;
      const widths = chars.map((c) => ctx.measureText(c).width + track), total = widths.reduce((s, v) => s + v, 0);
      let x = spec.align === "left" ? 0 : spec.align === "right" ? -total : -total / 2;
      chars.forEach((ch, i) => { const g = glyphAlpha(line, i, t, 0.4, spec); drawGlyph(ctx, ch, x + widths[i] / 2, 0, size, w, colorOf(spec, ch, i), g.a * amul, g.blur, 0, spec.ink === "dark" ? 0 : 0.95); x += widths[i]; });
    }
    ctx.restore();
  };
  drawSet(null);
  if (spec.mirror) drawSet(spec.mirror);
}

// Level B: giant thin type, 30-50 % of the frame height, rotated -5..-8 deg, deliberately running off the frame.
// Kanji full size, kana smaller (mixed scale within the line, as in the reference).
function drawB(ctx, spec, line, t) {
  const S = spec.size || 0.4 * H, w = spec.weight || 200;
  ctx.save(); ctx.translate(spec.x, spec.y); ctx.rotate((spec.rot ?? -6) * Math.PI / 180);
  ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  let i = 0;
  spec.rows.forEach((row) => {
    let x = row.x || 0;
    for (const ch of row.t) {
      const s = S * (row.scale || 1) * (isKana(ch) ? (SMALL_K.has(ch) ? 0.5 : 0.62) : 1);
      ctx.font = `${w} ${s}px LyricMincho`; const adv = ctx.measureText(ch).width;
      const g = glyphAlpha(line, i, t, 0.35);
      drawGlyph(ctx, ch, x, row.y, s, w, colorOf(spec, ch, i), g.a, g.blur * 1.4, 0, 0.85);
      x += adv * (row.track || 0.96); i++;
    }
  });
  ctx.restore();
}

// Level C: one keyword at half the frame height (鳴呼, 愛 ...). One character may be red.
function drawC(ctx, spec, line, t) {
  const S = spec.size || 0.5 * H, k = spec.text;
  const start = line.ja.indexOf(k), base = Math.max(0, start);
  ctx.save(); ctx.translate(spec.x, spec.y); ctx.rotate((spec.rot || 0) * Math.PI / 180);
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.font = `${spec.weight || 200} ${S}px LyricMincho`;
  const chars = [...k], ws = chars.map((c) => ctx.measureText(c).width), tot = ws.reduce((a, b) => a + b, 0);
  let x = -tot / 2;
  chars.forEach((ch, j) => { const g = glyphAlpha(line, base + j, t, 0.3); drawGlyph(ctx, ch, x + ws[j] / 2, 0, S, spec.weight || 200, colorOf(spec, ch, base + j), g.a, g.blur * 1.6); x += ws[j]; });
  ctx.restore();
}

function drawLyric(ctx, spec, line, t) {
  if (!spec || t < line.start - 0.3 || t > (spec.holdUntil ? L2(spec.holdUntil).end : line.end)) return;
  if (spec.lvl === "B") drawB(ctx, spec, line, t);
  else if (spec.lvl === "C") drawC(ctx, spec, line, t);
  else drawA(ctx, spec, line, t);
}

// Korean subtitle: bottom centre, small and thin, plain fade. Never part of the design.
function drawKo(ctx, t) {
  const l = D.lyrics.find((x) => t >= x.start && t <= x.end); if (!l) return;
  const a = Math.min(clamp((t - l.start) / 0.15), clamp((l.end - t) / 0.15)); if (a <= 0) return;
  ctx.save(); ctx.font = "300 30px Sub"; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
  ctx.shadowColor = `rgba(0,0,0,${0.85 * a})`; ctx.shadowBlur = 8;                          // soft shadow only
  ctx.fillStyle = `rgba(240,240,238,${a})`; ctx.fillText(l.ko, W / 2, 987); ctx.fillText(l.ko, W / 2, 987);
  ctx.restore();
}
