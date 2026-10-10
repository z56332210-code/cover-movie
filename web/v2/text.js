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

// Entrance / exit styles (no bounce). Each lyric line picks one; neighbours never share a style.
const ENTER = ["fade", "rise", "drop", "zoom", "spread", "flicker", "slide"];
const EXIT = ["blur", "up", "spread", "flick"];
function animState(spec, g, i, n, size, t) {
  const en = spec.anim || ENTER[(spec._id * 3) % ENTER.length], ex = spec.exitAnim || EXIT[(spec._id * 5 + 1) % EXIT.length];
  const p = g.a > 0 && g.x < 1 ? clamp(g.p) : clamp(g.p), e = 1 - Math.pow(1 - p, 3), x = g.x, mid = i - (n - 1) / 2;
  const st = { a: p, blur: 0, dx: 0, dy: 0, sc: 1, along: 0 };
  switch (en) {
    case "fade": st.blur = (1 - e) * 12; break;
    case "rise": st.dy = (1 - e) * size * 0.7; st.blur = (1 - e) * 5; break;
    case "drop": st.dy = -(1 - e) * size * 0.9; st.blur = (1 - e) * 9; break;
    case "zoom": st.sc = 1 + 0.45 * (1 - e); st.blur = (1 - e) * 14; break;
    case "spread": st.along = mid * size * 0.55 * (1 - e); st.blur = (1 - e) * 6; break;
    case "flicker": st.a = p >= 1 ? 1 : (hash2(Math.floor(t * 30), i * 7 + spec._id) > 0.45 ? p : p * 0.15); break;
    case "slide": st.dx = -(1 - e) * size * 1.1; st.blur = (1 - e) * 8; break;
  }
  if (x > 0) switch (ex) {
    case "blur": st.a *= 1 - x; st.blur += x * 10; break;
    case "up": st.a *= 1 - x; st.dy -= x * size * 0.6; st.blur += x * 4; break;
    case "spread": st.a *= 1 - x; st.along += mid * size * 0.5 * x; break;
    case "flick": st.a *= hash2(i * 13 + spec._id, Math.floor(t * 30)) > x ? 1 - x * 0.3 : 0; break;
  }
  return st;
}
function glyphAlpha(line, i, t, enterDur = 0.28, spec) {
  // A level: quick sequential fade from the line start (reference); B/C: on the sung time of each character
  const tc = spec && spec.lvl === "A" ? line.start - 0.08 + i * 0.045 : line.chars[Math.min(i, line.chars.length - 1)] - 0.05;
  const end = spec && spec.holdUntil ? L2(spec.holdUntil).end : line.end;
  const a = clamp((t - tc) / enterDur), x = clamp((t - (end - 0.35)) / 0.35);
  return { a: a * (1 - x), blur: (1 - easeOut(a)) * 12 + x * 10, p: a, x };
}
function drawGlyph(ctx, ch, x, y, size, weight, color, a, blur, rot = 0, shade = 0, sc = 1) {
  if (a <= 0.003) return;
  ctx.save(); ctx.translate(x, y); if (rot) ctx.rotate(rot); if (sc !== 1) ctx.scale(sc, sc);
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
        const cc = [...col];
        cc.forEach((ch, k) => {
          const g = glyphAlpha(line, i, t, 0.4, spec), st = animState(spec, g, k, cc.length, size, t); let dx = 0, dy = 0;
          if (SMALL_K.has(ch)) { dx = size * 0.1; dy = -size * 0.1; }
          drawGlyph(ctx, ch, -ci * size * (spec.gap || 1.5) + dx + st.dx, k * size * 1.12 + dy + st.dy + st.along, size, w, colorOf(spec, ch, i), st.a * amul, st.blur, VROT.has(ch) ? Math.PI / 2 : 0, spec.ink === "dark" ? 0 : 0.95, st.sc);
          i++;
        });
      });
    } else {
      ctx.font = `${w} ${size}px LyricMincho`; const track = size * 0.08;
      const widths = chars.map((c) => ctx.measureText(c).width + track), total = widths.reduce((s, v) => s + v, 0);
      let x = spec.align === "left" ? 0 : spec.align === "right" ? -total : -total / 2;
      chars.forEach((ch, i) => { const g = glyphAlpha(line, i, t, 0.4, spec), st = animState(spec, g, i, chars.length, size, t);
        drawGlyph(ctx, ch, x + widths[i] / 2 + st.dx + st.along, st.dy, size, w, colorOf(spec, ch, i), st.a * amul, st.blur, 0, spec.ink === "dark" ? 0 : 0.95, st.sc); x += widths[i]; });
    }
    ctx.restore();
  };
  drawSet(null);
  if (spec.mirror) drawSet(spec.mirror);
}

// Level B: giant thin type, 30-50 % of the frame height, rotated -5..-8 deg, deliberately running off the frame.
// Kanji full size, kana smaller (mixed scale within the line, as in the reference).
function drawB(ctx, spec, line, t) {
  const S = spec.size || 0.4 * H, w = spec.weight || 200, rot = (spec.rot ?? -6) * Math.PI / 180;
  ctx.save(); ctx.translate(spec.x, spec.y); ctx.rotate(rot);
  ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  let i = 0;
  spec.rows.forEach((row) => {
    const cs = [...row.t], sizes = cs.map((ch) => S * (row.scale || 1) * (isKana(ch) ? (SMALL_K.has(ch) ? 0.5 : 0.62) : 1));
    const advs = cs.map((ch, k) => { ctx.font = `${w} ${sizes[k]}px LyricMincho`; return ctx.measureText(ch).width * (row.track || 0.96); });
    const width = advs.reduce((a, b) => a + b, 0);
    // keep the end of the row inside the frame (the start may still run off on purpose)
    const ex = spec.x + ((row.x || 0) + width) * Math.cos(rot) - row.y * Math.sin(rot) * 0, room = W - 70 - spec.x - (row.x || 0) * Math.cos(rot);
    let fit = 1, x0 = row.x || 0;
    if (ex > W - 70) { fit = Math.max(0.72, room / (width * Math.cos(rot))); if (spec.x + (x0 + width * fit) * Math.cos(rot) > W - 70) x0 -= spec.x + (x0 + width * fit) * Math.cos(rot) - (W - 70); }
    let x = x0;
    cs.forEach((ch, k) => {
      const g = glyphAlpha(line, i, t, 0.35), st = animState(spec, g, k, cs.length, sizes[k] * fit, t);
      drawGlyph(ctx, ch, x + st.dx + st.along, row.y + st.dy, sizes[k] * fit, w, colorOf(spec, ch, i), st.a, st.blur * 1.4, 0, 0.85, st.sc);
      x += advs[k] * fit; i++;
    });
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
  chars.forEach((ch, j) => { const g = glyphAlpha(line, base + j, t, 0.3), st = animState(spec, g, j, chars.length, S, t);
    drawGlyph(ctx, ch, x + ws[j] / 2 + st.dx + st.along, st.dy, S, spec.weight || 200, colorOf(spec, ch, base + j), st.a, st.blur * 1.6, 0, 0, st.sc); x += ws[j]; });
  ctx.restore();
}

function drawLyric(ctx, spec, line, t) {
  if (spec && spec._id === undefined) spec._id = line.id;
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
