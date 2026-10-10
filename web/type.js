// Japanese kinetic typography. A line design (lines.js) is laid out once (static metrics),
// then every frame computes each glyph's state from t only.
"use strict";

const ROTATE_IN_VERT = new Set(["ー", "〜", "～", "…", "（", "）", "「", "」"]);
const SMALL_KANA = new Set([..."ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ"]);
const VERT_PUNCT = new Set(["、", "。"]);

function fontStr(seg, size) {
  return seg.font === "dela" ? `400 ${size}px Dela` : `${seg.weight || 400} ${size}px Mincho`;
}

// ---- layout (cached per design; depends only on font metrics)
const _layoutCache = new Map();
function layoutLine(design, ctx) {
  if (_layoutCache.has(design)) return _layoutCache.get(design);
  const glyphs = []; // {ch, x, y, size, seg, rot, idx}
  let idx = 0;
  if (design.layout === "vert") {
    // columns right -> left, each column is a list of segments
    let colX = 0;
    design.cols.forEach((col, ci) => {
      const segs = Array.isArray(col) ? col : [{ t: col }];
      const colSize = Math.max(...segs.map((s) => s.size || design.size));
      let y = 0;
      for (const seg of segs) {
        const size = seg.size || design.size, tr = (seg.tracking ?? design.tracking ?? 0.06) * size;
        ctx.font = fontStr({ ...design, ...seg }, size);
        // latin runs are rotated as a whole
        if (/^[\x20-\x7e]+$/.test(seg.t)) {
          const w = ctx.measureText(seg.t).width;
          glyphs.push({ ch: seg.t, x: colX, y: y + w / 2, size, seg: { ...design, ...seg }, rot: Math.PI / 2, idx, run: seg.t.length });
          idx += seg.t.length; y += w + tr; continue;
        }
        for (const ch of seg.t) {
          let dx = 0, dy = 0, rot = 0;
          if (ROTATE_IN_VERT.has(ch)) rot = Math.PI / 2;
          if (SMALL_KANA.has(ch)) { dx = size * 0.1; dy = -size * 0.1; }
          if (VERT_PUNCT.has(ch)) { dx = size * 0.55; dy = -size * 0.55; }
          glyphs.push({ ch, x: colX + dx, y: y + size / 2 + dy, size, seg: { ...design, ...seg }, rot, idx: idx++ });
          y += size + tr;
        }
      }
      colX -= colSize * (1 + (design.colGap ?? 0.35));
    });
    // anchor: (x, y) is the top of the first (rightmost) column
  } else {
    let y = 0;
    const rows = design.rows.map((row) => (Array.isArray(row) ? row : [{ t: row }]));
    rows.forEach((row) => {
      const rowSize = Math.max(...row.map((s) => s.size || design.size));
      let x = 0; const rowGlyphs = [];
      for (const seg of row) {
        const size = seg.size || design.size, tr = (seg.tracking ?? design.tracking ?? 0.02) * size;
        ctx.font = fontStr({ ...design, ...seg }, size);
        for (const ch of seg.t) {
          const w = ctx.measureText(ch).width;
          rowGlyphs.push({ ch, x: x + w / 2, y: y + rowSize * 0.8, size, seg: { ...design, ...seg }, rot: 0, idx: idx++, w });
          x += w + tr;
        }
        x += (seg.gap || 0) * size;
      }
      const align = design.align || "center";
      const shift = align === "center" ? -x / 2 : align === "right" ? -x : 0;
      for (const g of rowGlyphs) { g.x += shift; glyphs.push(g); }
      y += rowSize * (design.lineHeight || 1.16);
    });
    const totalH = y;
    for (const g of glyphs) g.y -= totalH / 2; // (x, y) is the visual centre of the block
  }
  const text = glyphs.map((g) => g.ch).join("");
  if (text.replace(/\s/g, "") !== design.ja.replace(/\s/g, "")) throw new Error(`design ${design.id} text "${text}" != lyric "${design.ja}"`);
  _layoutCache.set(design, glyphs);
  return glyphs;
}

// ---- per-glyph animation state
function glyphState(g, design, line, t, i, n) {
  const lead = design.lead ?? 0.08;
  let tc;
  if (design.reveal === "all") tc = line.start - lead;
  else if (design.reveal === "stagger") tc = line.start - lead + i * (design.stagger ?? 0.035);
  else tc = line.chars[Math.min(g.idx, line.chars.length - 1)] - lead; // sung-synced
  const enter = design.enter || "fade", exit = design.exit || "fade";
  const ew = design.springW || 16, ez = design.springZ || 0.78;
  const p = spring(t - tc, ew, ez);
  const s = { a: clamp((t - tc) / 0.1), dx: 0, dy: 0, sc: 1, rot: 0 };
  const h = hash2(design.id, g.idx);
  switch (enter) {
    case "fade": s.dy = (1 - p) * g.size * 0.25; break;
    case "rise": s.dy = (1 - p) * g.size * 0.9; s.a = clamp((t - tc) / 0.25); break;
    case "pop": s.sc = 1 + (1 - p) * 0.55; break;
    case "stamp": s.sc = 1 + (1 - spring(t - tc, 24, 0.7)) * 1.4; s.a = clamp((t - tc) / 0.05); break;
    case "drop": s.dy = -(1 - p) * g.size * 2.2; break;
    case "slide": s.dx = -(1 - p) * g.size * 2.5 * (design.dir || 1); break;
    case "jitter": s.dx = (1 - p) * (h - 0.5) * g.size * 1.6; s.dy = (1 - p) * (hash(g.idx * 7 + design.id) - 0.5) * g.size * 1.6; s.rot = (1 - p) * (h - 0.5) * 0.8; break;
    case "type": s.a = t >= tc ? 1 : 0; break;
  }
  if (design.scatter) { // permanent disorder (散漫)
    s.dx += (h - 0.5) * design.scatter * g.size; s.dy += (hash(g.idx + 991) - 0.5) * design.scatter * g.size; s.rot += (h - 0.5) * design.scatter * 0.5;
  }
  if (design.shake) { // jitter locked to the 16th grid (steps, not smooth noise)
    const step = Math.floor(t * D.bpm / 60 * 4);
    s.dx += (hash2(step, g.idx) - 0.5) * design.shake * g.size; s.dy += (hash2(g.idx, step) - 0.5) * design.shake * g.size;
  }
  // exit: finish exactly at line.end so the next line never overlaps
  const xd = design.exitDur ?? 0.22, te = line.end - xd, q = clamp((t - te) / xd);
  if (q > 0) {
    switch (exit) {
      case "fade": s.a *= 1 - q; s.dy -= q * g.size * 0.15; break;
      case "blow": s.a *= 1 - q; s.sc *= 1 + q * 0.35; break;
      case "cut": s.a *= t < line.end ? 1 : 0; break;
      case "slideout": s.dx += easeIn(q) * 1400 * (design.dir || 1); s.a *= 1 - clamp((q - 0.6) / 0.4); break;
      case "glitch": { const fr = Math.floor(t * 30); s.dx += (hash2(fr, g.idx) - 0.5) * 80 * q; s.a *= hash2(g.idx, fr) > q ? 1 : 0; break; }
      case "fall": s.dy += easeIn(q) * 300 * (0.6 + h); s.rot += q * (h - 0.5); s.a *= 1 - q; break;
    }
  }
  if (t > line.end) s.a = 0;
  return s;
}

function resolveColor(name, pal, alpha = 1) {
  if (!name || name === "fg") return rgb(pal.fg, alpha);
  if (name === "bg") return rgb(pal.bg, alpha);
  return rgb(ACCENT[name], alpha);
}

// Draw one designed lyric line. env = {pal, alphaMul}
function drawLine(ctx, design, line, t, pal) {
  if (t < line.start - 0.6 || t > line.end) return;
  const glyphs = layoutLine(design, ctx);
  const blk = design.block || {};
  // block-level motion (rotation swing, drift) as springs from the line start
  const bp = spring(t - line.start + (design.lead ?? 0.08), blk.w || 9, blk.z || 0.8);
  const rot = ((design.rot || 0) + (blk.rotFrom || 0) * (1 - bp)) * Math.PI / 180;
  const drift = (t - line.start) * (design.drift || 0);
  ctx.save();
  ctx.translate(design.x + drift, design.y);
  ctx.rotate(rot);
  if (design.skew) ctx.transform(1, 0, Math.tan(design.skew * Math.PI / 180), 1, 0, 0);
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const n = glyphs.length;
  glyphs.forEach((g, i) => {
    const s = glyphState(g, design, line, t, i, n);
    if (s.a <= 0.002) return;
    const seg = g.seg;
    ctx.save();
    ctx.translate(g.x + s.dx, g.y + s.dy - (design.layout === "vert" ? 0 : g.size * 0.3));
    if (g.rot || s.rot) ctx.rotate(g.rot + s.rot);
    if (s.sc !== 1) ctx.scale(s.sc, s.sc);
    ctx.font = fontStr(seg, g.size);
    const a = s.a * (seg.alpha ?? 1);
    if (seg.outline) {
      ctx.lineWidth = Math.max(1.5, g.size * 0.02); ctx.strokeStyle = resolveColor(seg.color, pal, a); ctx.strokeText(g.ch, 0, 0);
    } else {
      if (seg.halo !== false && design.halo !== false) { // thin contrasting edge keeps text readable over the art
        ctx.lineWidth = Math.max(2, g.size * 0.07); ctx.lineJoin = "round";
        ctx.strokeStyle = resolveColor(seg.haloColor || "bg", pal, a * 0.85); ctx.strokeText(g.ch, 0, 0);
      }
      ctx.fillStyle = resolveColor(seg.color, pal, a); ctx.fillText(g.ch, 0, 0);
    }
    ctx.restore();
  });
  ctx.restore();
}

// Big translucent text behind everything (ghost layer).
function drawGhost(ctx, gh, line, t, pal) {
  const a0 = line.start - 0.1, a1 = line.end;
  if (t < a0 || t > a1) return;
  const k = spring(t - a0, 7, 0.9);
  const a = (gh.alpha ?? 0.1) * Math.min(clamp(k * 1.2), clamp((a1 - t) / 0.3));
  ctx.save();
  ctx.translate(gh.x + (t - a0) * (gh.drift || 0), gh.y);
  ctx.rotate((gh.rot || 0) * Math.PI / 180);
  const sc = 1.08 - 0.08 * k; ctx.scale(sc, sc);
  ctx.font = gh.font === "dela" ? `400 ${gh.size}px Dela` : `${gh.weight || 800} ${gh.size}px Mincho`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const lines = gh.vert ? [...gh.t] : [gh.t];
  lines.forEach((s, i) => {
    const y = gh.vert ? (i - (lines.length - 1) / 2) * gh.size * 1.02 : 0;
    if (gh.outline) { ctx.lineWidth = 2.5; ctx.strokeStyle = resolveColor(gh.color, pal, a); ctx.strokeText(s, 0, y); }
    else { ctx.fillStyle = resolveColor(gh.color, pal, a); ctx.fillText(s, 0, y); }
  });
  if (gh.echo) for (let e = 1; e <= gh.echo; e++) { // repeated after-images (九十九回)
    const ea = a * (1 - e / (gh.echo + 1)) * 0.8, off = e * (gh.echoStep || 40) * clamp((t - a0) / 1.2);
    ctx.fillStyle = resolveColor(gh.color, pal, ea); ctx.fillText(lines[0], off, off * 0.35); ctx.fillText(lines[0], -off, -off * 0.35);
  }
  ctx.restore();
}

// Small sub-lyric fragments around the main text.
function drawSubs(ctx, subs, line, t, pal) {
  for (const [k, sb] of subs.entries()) {
    const ts = line.start + (sb.delay || 0.1 * k);
    const a = (sb.alpha ?? 0.45) * clamp((t - ts) / 0.2) * clamp((line.end - t) / 0.2);
    if (a <= 0) continue;
    ctx.save(); ctx.translate(sb.x, sb.y + (1 - spring(t - ts, 12, 0.85)) * 14); ctx.rotate((sb.rot || 0) * Math.PI / 180);
    ctx.font = `${sb.weight || 400} ${sb.size || 26}px Mincho`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = resolveColor(sb.color, pal, a);
    if (sb.vert) [...sb.t].forEach((c, i) => ctx.fillText(c, 0, i * (sb.size || 26) * 1.05)); else ctx.fillText(sb.t, 0, 0);
    ctx.restore();
  }
}

// ---- Korean subtitle band: one fixed style, plain fade, never transformed.
const SUB = { y: 985, size: 44, maxW: 1560, fade: 0.15 };
function wrapKo(ctx, s) {
  if (ctx.measureText(s).width <= SUB.maxW) return [s];
  const mid = s.length / 2; let best = -1;
  for (let i = 0; i < s.length; i++) if (s[i] === " " && (best < 0 || Math.abs(i - mid) < Math.abs(best - mid))) best = i;
  return best < 0 ? [s] : [s.slice(0, best), s.slice(best + 1)];
}
function drawSubtitle(ctx, t) {
  const l = D.lyrics.find((x) => t >= x.start && t <= x.end);
  if (!l) return;
  const a = Math.min(clamp((t - l.start) / SUB.fade), clamp((l.end - t) / SUB.fade));
  if (a <= 0) return;
  ctx.save();
  ctx.font = `600 ${SUB.size}px Pretendard`; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
  const rows = wrapKo(ctx, l.ko);
  rows.forEach((r, i) => {
    const y = SUB.y - (rows.length - 1 - i) * SUB.size * 1.25;
    ctx.lineJoin = "round"; ctx.lineWidth = 6; ctx.strokeStyle = `rgba(10,10,12,${0.78 * a})`; ctx.strokeText(r, W / 2, y);
    ctx.fillStyle = `rgba(255,255,255,${a})`; ctx.fillText(r, W / 2, y);
  });
  ctx.restore();
}
