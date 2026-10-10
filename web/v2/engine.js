// v2 engine: scenes from scene_plan.json (section/type only), re-timed to this song's lyrics.
// seek(t) draws everything from t alone. Preview and final share all logic; only resolution/fps/post differ.
"use strict";
const L2 = (i) => lyric(i);
// measured character landmarks in source pixels (2160x3840 art)
const KP = {
  // align: nose line x, eye line y (measured on the source art) - used to join the two half faces
  patient: { eyes: [[815, 855], [975, 835]], eyeBox: [780, 770, 1010, 880], face: [910, 880], align: [885, 845] },
  nurse: { eyes: [[970, 815], [1120, 805]], eyeBox: [930, 765, 1160, 875], face: [1040, 880], align: [1025, 810] },
};
const sease = (k) => 0.5 - 0.5 * Math.cos(Math.PI * clamp(k));

// ---------------------------------------------------------------- shot = layered crop of the art with a slow Ken Burns move
const FULL = { x: 0, y: 0, w: W, h: H };
function cropAt(shot, t, vp = FULL) {
  const u0 = clamp((t - shot.t0) / (shot.t1 - shot.t0));
  const k = shot.ease === "inout" ? u0 * u0 * (3 - 2 * u0) : 1 - Math.pow(1 - u0, 2.6);   // default: fastest at the cut, decelerating
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
  else if (shot.plain) { /* background drawn by the scene */ }
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
  ctx.fillStyle = shot.dark ? "#5e6061" : shot.keyLight ? "#9c9ea0" : "#8a8c8d"; ctx.fillRect(-100, -100, W + 200, H + 200);       // wall_gray token
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
  for (const L0 of shot.layers) {
    const L = typeof L0.alpha === "function" ? { ...L0, alpha: L0.alpha(t) } : L0;
    const C = A2.ch[L.n], ox = L.ox1 !== undefined ? lerp(L.ox || 0, L.ox1, cr.k) : (L.ox || 0), oy = L.oy || 0;
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
    if (L.echo && !MASK) {                                                       // afterimages spreading apart
      const e = L.echo(t);
      for (const sgn of [-1, 1]) if (e > 0) { ctx.globalAlpha = 0.22 * (1 - e); ctx.drawImage(C.mono, sgn * 260 * e, -40 * e); }
    }
    if (sharp > 0) { ctx.globalAlpha = (L.alpha ?? 1) * sharp; ctx.drawImage(C.mono, 0, 0); }
    if (L.dissolve && !MASK) {                                                   // light particles lifting off the figure
      const d = L.dissolve(t);
      if (d > 0) { ctx.save(); ctx.globalCompositeOperation = "screen";
        C.pts.forEach(([x, y], i) => {
          const dl = hash(i * 3 + 1) * 0.55, q = clamp((d - dl) / 0.45); if (q <= 0 || q >= 1) return;
          const qx = x + (hash(i * 5) - 0.5) * 380 * q + Math.sin(q * 6 + i) * 30 * q, qy = y - (260 + hash(i * 7) * 520) * q * q;
          const r = 10 + hash(i * 11) * 22; ctx.globalAlpha = Math.sin(q * Math.PI) * 0.85;
          ctx.drawImage(A2.dot, qx - r, qy - r, r * 2, r * 2);
        });
        ctx.restore(); }
    }
    if (L.color) { ctx.globalAlpha = (L.alpha ?? 1) * L.color(t); ctx.drawImage(C.color, 0, 0); }    // colour returns (final merge)
    if (shot.keyLight) { ctx.globalAlpha = 0.95 * (L.alpha ?? 1); ctx.drawImage(C.rim, 0, 0);       // rim light from behind, upper left
      ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = 0.45 * (L.alpha ?? 1); ctx.drawImage(C.rim, -3, -3); ctx.globalCompositeOperation = "source-over"; }
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
R.giant_type = (ctx, sc, t) => {
  const sh = shotAt(sc, t), cr = drawShot(ctx, sh, t);
  if (sc.pulse !== undefined && t >= sc.pulse) {
    const u = t - sc.pulse, a = Math.exp(-u * 1.6) * (1 - Math.exp(-u * 30)), hx = (1000 - cr.x0) * cr.s, hy = (1500 - cr.y0) * cr.s, r = 260 + 900 * (1 - Math.exp(-u * 2));
    ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = 0.8 * a; ctx.drawImage(A2.dot, hx - r, hy - r, r * 2, r * 2); ctx.restore();
  }
  return { drift: cr.k * 40 };
};
R.blur_focus_pull = R.hud_portrait;
// Two-shot. With sc.split: each figure in its own panel, a dark band with a red thread between them that narrows
// in steps on the lyric hits (each step snaps fast, then settles), until it closes.
const STEP_DUR = 0.8;   // each narrowing step snaps fast, then decelerates over 0.8 s
function stepKeys(keys, t) {
  let v = keys[0][1];
  for (let i = 1; i < keys.length; i++) { const [kt, kv] = keys[i]; if (t < kt) break; const u = clamp((t - kt) / STEP_DUR); v = lerp(v, kv, 1 - Math.pow(1 - u, 3)); }
  return v;
}
R.hud_two_shot = (ctx, sc, t) => {
  if (!sc.split) { const cr = drawShot(ctx, shotAt(sc, t), t); return { drift: cr.k * 40 }; }
  const g = stepKeys(sc.split, t), half = (W - g) / 2, c = clamp(1 - g / sc.split[0][1]);
  const scale = lerp(0.62, 1.12, Math.pow(c, 1.6));              // closer as the band narrows
  const fy = lerp(300, 430, c);                                  // eye line height on screen (same for both)
  const panel = (n, vp, faceTargetX, dir) => {
    const F = KP[n].align, cx = F[0] - (faceTargetX - (vp.x + vp.w / 2)) / scale, cy = F[1] - (fy - H / 2) / scale;
    drawShot(ctx, { t0: sc.t0, t1: sc.t1, layers: [{ n }], c0: [cx, cy, vp.w / scale], c1: [cx, cy, vp.w / scale], r0: 0, r1: 0, keyLight: true, longShadow: true }, t, vp);
  };
  // each face travels toward the seam; at c = 1 both face centres sit exactly on it (one face, two halves)
  panel("patient", { x: 0, y: 0, w: half, h: H }, lerp(half * 0.5, half, c), 1);
  panel("nurse", { x: half + g, y: 0, w: half, h: H }, lerp(half + g + half * 0.5, half + g, c), -1);
  if (g > 0.5) {
    ctx.fillStyle = "#0b0c0f"; ctx.fillRect(half, 0, g, H);
    ctx.fillStyle = "rgba(179,18,43,0.85)"; ctx.fillRect(W / 2 - 1, 0, 2, H);
  } else { ctx.fillStyle = "rgba(236,236,232,0.5)"; ctx.fillRect(W / 2 - 0.5, 0, 1, H); }   // the seam
  return { drift: c * 30 };
};
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
  // crimson smears at the frame edges, boiling like paper (12 fps strip jitter), no zoom
  const fr = Math.floor(t * 12);
  [[1620, 330, 1150, 0, 1], [1800, 880, 860, 1, 0.95], [150, 170, 660, 2, 0.6]].forEach(([x, y, z, i, a], si) => {
    ctx.save(); ctx.globalAlpha = a;
    ctx.translate(x + (hash2(fr, si) - 0.5) * 6, y + (hash2(si, fr) - 0.5) * 6); ctx.rotate((hash2(fr + 3, si) - 0.5) * 0.012);
    const src = A2.smear[i], n = 10, sh = src.height / n;
    for (let k2 = 0; k2 < n; k2++) {
      const off = (hash2(fr * 7 + k2, si) - 0.5) * 9;
      ctx.drawImage(src, 0, k2 * sh, src.width, sh + 1, -z / 2 + off, -z / 2 + k2 * z / n, z, z / n + 1);
    }
    ctx.restore();
  });
  ctx.globalAlpha = 1;
  ctx.save(); roll(ctx, cr); ctx.globalAlpha = 0.9; drawLayers(ctx, shot, cr, t); ctx.restore();
  ctx.save(); ctx.globalCompositeOperation = "multiply"; ctx.fillStyle = "rgba(40,40,44,1)"; ctx.globalAlpha = 0.72; ctx.fillRect(0, 0, W, H); ctx.restore();
  return { drift: k * 30 };
};
R.placeholder = (ctx, sc, t) => { ctx.fillStyle = "#3a3b3c"; ctx.fillRect(0, 0, W, H); return {}; };

// ---- reference-specific backgrounds
function wallBase(ctx, t, k = 0, bright = "#a6a8aa") {   // concrete wall (title/credits/HUD scenes)
  ctx.fillStyle = bright; ctx.fillRect(-100, -100, W + 200, H + 200);
  ctx.save(); ctx.globalCompositeOperation = "overlay"; ctx.globalAlpha = 0.75;
  ctx.drawImage(A2.wall, -180 - 90 * k, -120, 2400 * (1 + 0.04 * k), 1350 * (1 + 0.04 * k)); ctx.restore();
}
function lightBand(ctx, t, x0, a = 0.5) {               // broad diagonal window light across the wall
  const p = x0 + t * 14;
  ctx.save(); ctx.globalCompositeOperation = "soft-light";
  const g = ctx.createLinearGradient(p, 0, p + 900, -520);
  g.addColorStop(0, "rgba(0,0,0,0.55)"); g.addColorStop(0.3, `rgba(255,255,250,${a})`); g.addColorStop(0.62, `rgba(255,255,250,${a})`); g.addColorStop(1, "rgba(0,0,0,0.55)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); ctx.restore();
}
// title card: two shadow silhouettes on the concrete, light sliding over; title box; optional credits / merging shadows
R.title_card_shadow = (ctx, sc, t) => {
  const u = t - sc.t0, k = 1 - Math.pow(1 - clamp(u / (sc.t1 - sc.t0)), 2.2);
  wallBase(ctx, t, k);
  const merge = sc.merge ? sease(clamp(u / 1.1)) : 0, gl0 = 1.45, gone = sc.merge && u > gl0 + 0.2;
  ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate((0.6 - 1.0 * k) * Math.PI / 180); ctx.scale(1 + 0.05 * k, 1 + 0.05 * k); ctx.translate(-W / 2, -H / 2);
  const SX = SHL.getContext("2d"); SX.setTransform(1, 0, 0, 1, 0, 0); SX.clearRect(0, 0, SHL.width, SHL.height); SX.setTransform(PX2, 0, 0, PX2, 0, 0);
  if (!gone) [["patient", 120 + 390 * merge, -0.4], ["nurse", 900 - 390 * merge, 0.4]].forEach(([n, x, sk]) => {
    SX.save(); SX.globalAlpha = n === "nurse" ? 1 - 0.5 * merge : 1; SX.translate(x + 18 * k, 130 - 10 * k); SX.transform(1, 0, sk * 0.15 * (1 - merge), 1, 0, 0);
    SX.drawImage(A2.ch[n].shadowSharp, -540, -260, 1080 * 1.55, 1920 * 1.55); SX.restore();
  });
  ctx.restore(); ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 0.5;
  if (sc.merge && u >= gl0 && u < gl0 + 0.2) {                  // glitch the shadows only
    const fr = Math.floor(t * 30);
    for (let i = 0; i < 14; i++) { const y = hash2(fr, i) * SHL.height, h = (8 + hash2(i, fr) * 50) * PX2, off = (hash2(fr + 5, i) - 0.5) * 220 * PX2;
      ctx.drawImage(SHL, 0, y, SHL.width, h, off, y, SHL.width, h); }
  } else ctx.drawImage(SHL, 0, 0);
  ctx.restore();
  lightBand(ctx, u, -700 + 300 * k, 0.45);
  const ta = sc.titleAt !== undefined ? clamp((t - sc.titleAt) / 0.08) : 0;
  return { drift: k * 40, title: ta, credits: sc.credits ? clamp((t - sc.t0 - 0.6) / 0.6) : 0, creditPos: [1240, 640] };
};
// credits page then white over-exposure with a short pixel glitch (one of the 3-4 glitch uses)
R.white_flash_glitch = (ctx, sc, t) => {
  const u = t - sc.t0; wallBase(ctx, t, u / 3, "#9c9ea0"); lightBand(ctx, u, -400, 0.55);
  return { credits: 1, white: clamp((u - (sc.t1 - sc.t0) + 0.9) / 0.6) * 0.92, glitchAt: sc.t0 + 0.05 };
};
// film strip: dark checker, thin circles, framed panels sliding (two speeds)
R.filmstrip = (ctx, sc, t) => {
  const u = t - sc.t0;
  ctx.fillStyle = "#1b1b1c"; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = "#222224"; for (let y = 0; y < H; y += 36) for (let x = (y / 36) % 2 ? 36 : 0; x < W; x += 72) ctx.fillRect(x, y, 36, 36);
  ctx.strokeStyle = "rgba(220,220,216,0.35)"; ctx.lineWidth = 1.3;
  for (const [r, seed, dash] of [[470, 600, null], [640 + 8 * u, 700, [8, 12]]]) {
    const pts = []; for (let i = 0; i <= 90; i++) { const an = i / 90 * Math.PI * 2 + u * 0.15 * (seed === 600 ? 1 : -1); pts.push([960 + Math.cos(an) * r, 540 + Math.sin(an) * r]); }
    if (dash) ctx.setLineDash(dash); wobblyPath(ctx, pts, t, seed); ctx.setLineDash([]);
    for (let k = 0; k < 24; k++) { const an = k / 24 * Math.PI * 2 + u * 0.15; ctx.beginPath(); ctx.moveTo(960 + Math.cos(an) * 470, 540 + Math.sin(an) * 470); ctx.lineTo(960 + Math.cos(an) * 484, 540 + Math.sin(an) * 484); ctx.stroke(); }
  }
  const rows = [[470, 560, 315, 70, sc.crops], [870, 300, 168, -110, sc.crops2]];
  rows.forEach(([cy, pw, ph, speed, crops], ri) => {
    const step = pw + 70, n = Math.ceil(W / step) + 2, off = ((u * speed) % step + step) % step;
    for (let i = -1; i < n; i++) {
      const x = i * step + off - step, idx = ((i - Math.floor(u * speed / step)) % crops.length + crops.length) % crops.length;
      const c = crops[idx], vp = { x, y: cy - ph / 2, w: pw, h: ph };
      drawShot(ctx, { t0: sc.t0, t1: sc.t1, layers: [{ n: c[0] }], c0: [c[1], c[2], c[3]], c1: [c[1], c[2], c[3] * 0.93], keyLight: true, longShadow: true, r0: 0, r1: 0 }, t, vp);
      ctx.strokeStyle = "rgba(235,235,232,0.8)"; ctx.lineWidth = 1.5; ctx.strokeRect(x + 0.5, cy - ph / 2 + 0.5, pw - 1, ph - 1);
      if (ri === 0) { ctx.fillStyle = "rgba(235,235,232,0.5)"; for (let k = 0; k < 6; k++) ctx.fillRect(x + 8 + k * 9, cy + ph / 2 + 10, 4, 2); }
    }
  });
  return { drift: u * 6 };
};
// rapid 0.12-0.25 s close-up cuts with white flash frames between
R.flash_cut_cluster = (ctx, sc, t) => {
  const u = t - sc.t0, i = Math.min(sc.subs.length - 1, Math.floor(u / sc.sub));
  const c = sc.subs[i], f = u - i * sc.sub;
  drawShot(ctx, { t0: sc.t0 + i * sc.sub, t1: sc.t0 + (i + 1) * sc.sub, layers: [{ n: c[0] }], c0: [c[1], c[2], c[3]], c1: [c[1] + 30, c[2], c[3] * 0.94], keyLight: true, longShadow: true, r0: 0.8, r1: -0.4 }, t);
  return { white: f < 1 / 30 ? 0.85 : 0, drift: 0 };
};
// sunset: thick letterbox, desaturated orange sky with drifting dark clouds, figure against it (accent, once)
R.sunset_letterbox = (ctx, sc, t) => {
  const u = t - sc.t0, k = 1 - Math.pow(1 - clamp(u / (sc.t1 - sc.t0)), 2.2);
  const g = ctx.createLinearGradient(0, 260, 0, 820);
  g.addColorStop(0, "#2b2220"); g.addColorStop(0.42, "#9a4f27"); g.addColorStop(0.55, "#d9722b"); g.addColorStop(0.7, "#7a3a20"); g.addColorStop(1, "#1d1716");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  ctx.save(); ctx.globalAlpha = 0.55;
  for (let i = 0; i < 16; i++) { const x = ((hash(i * 7) * 2400 - u * (12 + hash(i) * 14)) % 2400 + 2400) % 2400 - 240, y = 300 + hash(i * 3) * 420, r = 120 + hash(i * 5) * 260;
    ctx.save(); ctx.translate(x, y); ctx.scale(1, 0.22); ctx.drawImage(A2.dotDark, -r, -r, r * 2, r * 2); ctx.restore(); }
  ctx.restore();
  const sh = sc.shots[0], cr = cropAt(sh, t);
  ctx.save(); roll(ctx, cr); drawLayers(ctx, { ...sh, shadow: false }, cr, t); ctx.restore();
  ctx.save(); ctx.globalCompositeOperation = "multiply"; ctx.fillStyle = "rgba(120,72,50,1)"; ctx.globalAlpha = 0.55; ctx.fillRect(0, 0, W, H); ctx.restore();
  return { bars: 264, drift: k * 20 };
};
R.black_line = () => { return { still: true }; };
// white mirror: one figure upright, the other flipped upside down facing it; framed vertical lyric in the middle
R.mirror_flip = (ctx, sc, t) => {
  const u = t - sc.t0, k = 1 - Math.pow(1 - clamp(u / (sc.t1 - sc.t0)), 2.2);
  ctx.fillStyle = "#f2f1ee"; ctx.fillRect(0, 0, W, H);
  ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate((-1.2 + 2.0 * k) * Math.PI / 180); ctx.translate(-W / 2, -H / 2);
  ctx.globalAlpha = 0.85;
  drawShot(ctx, { t0: sc.t0, t1: sc.t1, layers: [{ n: "nurse" }], c0: [1150, 1350, 2500], c1: [1120, 1320, 2300], shadow: false, plain: true, r0: 0, r1: 0 }, t, { x: -120, y: 0, w: 1150, h: H });
  drawShot(ctx, { t0: sc.t0, t1: sc.t1, layers: [{ n: "patient", flipV: true, mirror: true }], c0: [1120, 2450, 2500], c1: [1150, 2480, 2300], shadow: false, plain: true, r0: 0, r1: 0 }, t, { x: 890, y: 0, w: 1150, h: H });
  ctx.restore();
  ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = "rgba(245,243,236,0.35)"; ctx.fillRect(0, 0, W, H); ctx.restore();
  ctx.strokeStyle = "rgba(40,40,42,0.75)"; ctx.lineWidth = 1.2; ctx.strokeRect(905, 190, 110, 700);
  return { drift: k * 20, hudDark: true };
};
// kinetic cluster: dark strip with one small line, then a grid of panels with glitch blocks and a giant keyword
R.kinetic_cluster = (ctx, sc, t) => {
  const u = t - sc.t0;
  ctx.fillStyle = "#050606"; ctx.fillRect(0, 0, W, H);
  if (u < sc.strip) {
    const vp = { x: 0, y: 340, w: W, h: 400 };
    drawShot(ctx, { t0: sc.t0, t1: sc.t0 + sc.strip, layers: [{ n: "nurse" }], c0: [1060, 870, 1500], c1: [1040, 865, 1400], keyLight: true, r0: 0, r1: 0 }, t, vp);
    ctx.save(); ctx.globalCompositeOperation = "multiply"; ctx.fillStyle = "rgba(70,78,76,1)"; ctx.fillRect(0, 340, W, 400); ctx.restore();
    return { still: true, hud: false };
  }
  const cell = [640, 360], beat = Math.floor((u - sc.strip) / 0.23);
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) {
    const id = (r * 3 + c + beat) % sc.crops.length, cp = sc.crops[id];
    drawShot(ctx, { t0: sc.t0, t1: sc.t1, layers: [{ n: cp[0] }], c0: [cp[1], cp[2], cp[3]], c1: [cp[1] + 40, cp[2], cp[3] * 0.92], keyLight: true, r0: 0, r1: 0 }, t, { x: c * cell[0], y: r * cell[1], w: cell[0], h: cell[1] });
  }
  ctx.strokeStyle = "rgba(10,10,10,1)"; ctx.lineWidth = 6;
  for (let i = 1; i < 3; i++) { ctx.beginPath(); ctx.moveTo(i * 640, 0); ctx.lineTo(i * 640, H); ctx.moveTo(0, i * 360); ctx.lineTo(W, i * 360); ctx.stroke(); }
  return { drift: 0 };
};
// full body, then the exposure climbs to white
R.full_body_whiteout = (ctx, sc, t) => {
  const cr = drawShot(ctx, shotAt(sc, t), t), u = (t - sc.t0) / (sc.t1 - sc.t0);
  return { white: sease(clamp((u - 0.45) / 0.55)) * 0.95, drift: cr.k * 30 };
};
// white, soft: the two figures blurred and overlapping (first hint that they are one)
R.white_soft = (ctx, sc, t) => {
  const u = t - sc.t0, k = 1 - Math.pow(1 - clamp(u / (sc.t1 - sc.t0)), 2.2);
  ctx.fillStyle = "#f4f3f0"; ctx.fillRect(0, 0, W, H);
  const sh = { t0: sc.t0, t1: sc.t1, c0: [1000, 1250, 2600], c1: [990, 1220, 2300], shadow: false, plain: true, focus: "half", r0: 0.5, r1: -0.5,
    layers: [{ n: "nurse", ox: 160 - 140 * k, alpha: 0.32 }, { n: "patient", ox: -160 + 140 * k, alpha: 0.42 }] };
  ctx.save(); ctx.globalAlpha = 0.9; const cr = cropAt(sh, t); roll(ctx, cr); drawLayers(ctx, sh, cr, t); ctx.restore();
  ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = "rgba(246,245,240,0.3)"; ctx.fillRect(0, 0, W, H); ctx.restore();
  return { drift: k * 20, hudDark: true };
};
R.fade_out = () => ({ still: true, hud: false });

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
        { t0: 2.4, t1: 7.3, tin: "bleed", layers: [P()], c0: [1150, 1480, 2560], c1: [1000, 1400, 2260], keyLight: true, dustBack: true, longShadow: true, r0: -0.8, r1: 0.6 },
        // face, eyes visible
        { t0: 7.3, t1: 12.3, tin: "bleed", layers: [P()], c0: [990, 900, 1640], c1: [880, 860, 1400], keyLight: true, dustBack: true, longShadow: true, r0: 0.7, r1: -0.7 },
        // second figure: chest and the clipboard held in both hands
        { t0: 12.3, t1: 17.0, tin: "bleed", layers: [N()], c0: [1160, 1600, 2120], c1: [1300, 1520, 1840], keyLight: true, dustBack: true, longShadow: true, r0: -0.7, r1: 0.7 },
        // second figure: face (whip pan in)
        { t0: 17.0, t1: 20.0, tin: "whip", layers: [N()], c0: [930, 900, 1640], c1: [1100, 860, 1400], keyLight: true, dustBack: true, longShadow: true, r0: -0.6, r1: 0.6 },
      ],
      text: {
        1: { lvl: "A", layout: "vert", x: 1010, y: 345, size: 29, cols: ["僕は最上最愛の"], holdUntil: 2 },
        2: { lvl: "A", layout: "vert", x: 1010 - 29 * 1.3, y: 345, size: 29, gap: 1.3, cols: ["この世界に産み落とされた", "モンスター"] },
        3: { lvl: "A", layout: "vert", x: 1010, y: 345, size: 29, gap: 1.3, cols: ["そこは", "従順傀儡の"] },
        4: { lvl: "A", layout: "vert", x: 560, ink: "dark", y: 345, size: 29, gap: 1.3, cols: ["嫌な時代に", "振り落とされたもんだ"] },
        5: { lvl: "A", layout: "vert", x: 560, ink: "dark", y: 345, size: 29, gap: 1.3, cols: ["赤い糸を", "放ったスパイダー"] },
        6: { lvl: "A", layout: "vert", x: 860, y: 345, size: 29, cols: ["予想通り絡まるハンター"], holdUntil: 7 },
        7: { lvl: "A", layout: "vert", x: 860 - 29 * 1.3, y: 345, size: 29, gap: 1.3, cols: ["どうか", "一生淡々と"] },
        8: { lvl: "A", layout: "vert", x: 560, ink: "dark", y: 345, size: 29, gap: 1.3, cols: ["生きるだけの", "理由をください", "ドクター"] },
      } },
    // ---- title card: shadows on concrete, full frame opens
    { type: "title_card_shadow", t0: 20.0, t1: 34.14, geo: true, tin: "blur", titleAt: snapOnset(23.75, 0.3), lightOverlay: true },
    // ---- verse 2: HUD portrait, crops cut every ~5 s
    { type: "hud_portrait", t0: 34.14, t1: s(13), tin: "cut",
      shots: [
        { t0: 34.14, t1: s(11), layers: [P()], c0: [1060, 1300, 2420], c1: [1000, 1250, 2220] },
        { t0: s(11), t1: s(13), tin: "bleed", layers: [P()], c0: [1010, 930, 1500], c1: [930, 905, 1330] },
      ],
      text: {
        9: { lvl: "A", layout: "vert", x: 1480, y: 250, size: 30, gap: 1.3, cols: ["僕は", "新旧曖昧な"], mirror: { x: 440, y: 300 } },
        10: { lvl: "A", layout: "vert", x: 1480, y: 250, size: 30, gap: 1.3, cols: ["この世界に", "産み落とされた", "モンスター"] },
        11: { lvl: "A", layout: "vert", x: 1500, y: 250, size: 30, gap: 1.3, cols: ["そこは", "一見散漫な"] },
        12: { lvl: "A", layout: "vert", x: 1500, y: 250, size: 30, gap: 1.3, cols: ["手のひらから", "振り落とされたようだ"] },
      } },
    // ---- eye close-up, background blurred, focus pulls in
    { type: "blur_focus_pull", t0: s(13), t1: s(17), tin: "whip",
      shots: [
        { t0: s(13), t1: s(15), layers: [N()], c0: [980, 960, 1700], c1: [1120, 900, 1480], focus: "pull", dof: true },
        { t0: s(15), t1: s(17), tin: "blur", layers: [N()], c0: [1300, 1200, 2000], c1: [1180, 1130, 1760], dof: true },
      ],
      text: {
        13: { lvl: "A", layout: "vert", x: 1560, y: 230, size: 30, gap: 1.3, cols: ["外側に", "放ったスライダー"] },
        14: { lvl: "A", layout: "vert", x: 1560, y: 230, size: 30, gap: 1.3, cols: ["予想通り", "空振るバッター"] },
        15: { lvl: "A", layout: "line", x: 1360, y: 820, size: 30 },
        16: { lvl: "A", layout: "line", x: 1360, y: 820, size: 30 },
      } },
    // ---- pre-chorus: film strip (dark checker)
    { type: "filmstrip", t0: s(17), t1: 61.3, tin: "flash", lightOverlay: false,
      crops: [["patient", 910, 900, 1500], ["nurse", 1040, 900, 1500], ["patient", 1100, 1500, 2200], ["nurse", 1350, 1600, 2000]],
      crops2: [["nurse", 1040, 880, 1300], ["patient", 1600, 760, 1200], ["nurse", 1450, 1600, 1400], ["patient", 910, 880, 1300]],
      text: {
        17: { lvl: "A", layout: "line", x: 960, y: 690, size: 28 },
        18: { lvl: "A", layout: "line", x: 960, y: 690, size: 28 },
        19: { lvl: "A", layout: "line", x: 960, y: 690, size: 28 },
      } },
    { type: "flash_cut_cluster", t0: 61.3, t1: 62.11, tin: "glitch", sub: 0.2, lightOverlay: false,
      subs: [["nurse", 1300, 1500, 1200], ["patient", 910, 870, 900], ["nurse", 1040, 870, 900], ["patient", 1000, 1350, 1400]] },
    // ---- chorus 1: giant type over the figure
    { type: "giant_type", t0: 62.11, t1: s(22), tin: "bleed",
      shots: [
        { t0: 62.11, t1: s(21), layers: [P()], c0: [1010, 1300, 2300], c1: [960, 1240, 2080] },
        { t0: s(21), t1: s(22), tin: "cut", layers: [N()], c0: [1150, 1350, 2300], c1: [1100, 1290, 2060] },
      ],
      text: {
        20: { lvl: "B", x: 0, y: 560, rot: -5, size: 0.3 * H, weight: 300, red: "愛",
              rows: [{ t: "嗚呼", y: 300, scale: 0.55 }, { t: "人類最後に", x: 330, y: 300 }, { t: "愛を持ったって", x: 900, y: 520 }] },
        21: { lvl: "B", x: -40, y: 470, rot: -7, size: 0.32 * H, weight: 300,
              rows: [{ t: "僕に居場所は", y: 300 }, { t: "ないでしょうか", x: 760, y: 540 }] },
      } },
    { type: "hud_portrait", t0: s(22), t1: s(23), tin: "whip",
      shots: [{ t0: s(22), t1: s(23), layers: [P()], c0: [1050, 930, 1560], c1: [960, 900, 1380] }],
      text: { 22: { lvl: "A", layout: "vert", x: 1480, y: 230, size: 30, gap: 1.3, cols: ["心中泣いて", "痛いから", "思い出してよ"], mirror: { x: 430, y: 280 } } } },
    { type: "giant_type", t0: s(23), t1: s(25), tin: "flash",
      shots: [
        { t0: s(23), t1: s(24), layers: [N()], c0: [1080, 1320, 2300], c1: [1020, 1260, 2100] },
        { t0: s(24), t1: s(25), tin: "cut", layers: [P()], c0: [880, 1350, 2300], c1: [960, 1290, 2100] },
      ],
      text: {
        23: { lvl: "B", x: 10, y: 520, rot: -6, size: 0.31 * H, weight: 300, red: "愛",
              rows: [{ t: "人類最後に", y: 300 }, { t: "愛を持ったって", x: 900, y: 560 }] },
        24: { lvl: "B", x: -30, y: 470, rot: -6, size: 0.3 * H, weight: 300,
              rows: [{ t: "それを知る日は", y: 300 }, { t: "ないでしょうなんて", x: 700, y: 560 }] },
      } },
    // ---- accent 1: crimson smear in black space
    { type: "red_burst", t0: s(25), t1: 82.54, tin: "black", accent: 1, lightOverlay: false,
      shots: [{ t0: s(25), t1: 82.54, layers: [P()], c0: [930, 1250, 1900], c1: [930, 1250, 2150], focus: "half", shadow: false }],
      text: { 25: { lvl: "A", layout: "line", x: 960, y: 900, size: 30 } } },
    // ---- credits on the wall, then white over-exposure with a short glitch
    { type: "white_flash_glitch", t0: 82.54, t1: s(26), geo: true, tin: "cut", lightOverlay: true },
    // ---- accent 2: sunset (orange only here)
    { type: "sunset_letterbox", t0: s(26), t1: s(28), tin: "flash", accent: 2, hud: false, lightOverlay: false,
      shots: [{ t0: s(26), t1: s(28), layers: [P()], c0: [1000, 1500, 2700], c1: [980, 1440, 2450], r0: -0.5, r1: 0.5 }],
      text: {
        26: { lvl: "A", layout: "vert", x: 1300, y: 300, size: 28, gap: 1.3, cols: ["有終最後の", "火を灯したって"], red: "火" },
        27: { lvl: "A", layout: "vert", x: 1300, y: 300, size: 28, gap: 1.3, cols: ["心苦しく", "なるでしょうか"] },
      } },
    // ---- quiet: black screen, one small line
    { type: "black_line", t0: s(28), t1: 92.2, tin: "black", hud: false, lightOverlay: false,
      text: { 28: { lvl: "A", layout: "vert", x: 975, y: 330, size: 24, gap: 1.4, cols: ["本当は咲いてみたいってこと", "思い出したんだ"] } } },
    { type: "hud_portrait", t0: 92.2, t1: s(29), tin: "blur",
      shots: [{ t0: 92.2, t1: s(29), layers: [P()], c0: [1080, 1450, 2300], c1: [1010, 1390, 2080] }],
      text: { 28: { lvl: "A", layout: "vert", x: 1480, y: 260, size: 30, gap: 1.3, cols: ["本当は咲いて", "みたいってこと", "思い出したんだ"] } } },
    // ---- emotion flips: white, one figure upside down facing the other
    { type: "mirror_flip", t0: s(29), t1: s(30), tin: "flash", lightOverlay: false,
      text: { 29: { lvl: "A", layout: "vert", x: 975, y: 230, size: 34, gap: 1.35, ink: "dark", cols: ["たどり着いたんだ", "正体と擬態したアイを"] } } },
    // ---- kinetic cluster: one line on a dark strip, then a grid + giant keyword
    { type: "kinetic_cluster", t0: s(30), t1: 101.95, tin: "cut", strip: 0.32, lightOverlay: false, hud: false,
      crops: [["patient", 1050, 1500, 1500], ["nurse", 1400, 1600, 1500], ["patient", 1600, 760, 1300], ["nurse", 1150, 1450, 1500], ["patient", 700, 1700, 1300], ["nurse", 1450, 2000, 1500]],
      text: { 30: (t) => (t - s(30) < 0.32 ? { lvl: "A", layout: "line", x: 960, y: 540, size: 28, instant: true }
        : { lvl: "C", text: "嗚呼", x: 960, y: 560, size: 0.5 * H * (1 + 0.06 * (Math.floor((t - s(30)) / 0.23) % 3)), weight: 200 }) } },
    { type: "giant_type", t0: 101.95, t1: s(31), tin: "flash",
      shots: [{ t0: 101.95, t1: s(31), layers: [P()], c0: [1080, 1420, 2300], c1: [1010, 1360, 2050] }],
      text: { 30: { lvl: "B", x: 10, y: 470, rot: -5, size: 0.3 * H, weight: 300, red: "ア",
        rows: [{ t: "嗚呼", y: 300, scale: 0.5 }, { t: "人類最後に", x: 300, y: 300 }, { t: "アイを持ったって", x: 760, y: 520 }] } } },
    // ---- two-shot: both on the wall, vertical lyrics in the gap
    { type: "hud_two_shot", t0: s(31), t1: s(33), tin: "bleed",
      shots: [
        { t0: s(31), t1: s(32), layers: [P({ ox: -560 }), N({ ox: 640 })], c0: [1080, 1300, 3600], c1: [1080, 1250, 3300] },
        { t0: s(32), t1: s(33), tin: "cut", layers: [P({ ox: -480 }), N({ ox: 560 })], c0: [1080, 1050, 2900], c1: [1080, 1010, 2650] },
      ],
      text: {
        31: { lvl: "A", layout: "vert", x: 990, ink: "dark", y: 260, size: 30, gap: 1.3, cols: ["僕の印は", "ないでしょうか"] },
        32: { lvl: "B", x: 20, y: 560, rot: -6, size: 0.28 * H, weight: 300, rows: [{ t: "きっとふさわしくないけど", y: 300, scale: 0.55 }, { t: "思い出してよ", x: 600, y: 540 }] },
      } },
    // ---- accent 3: crimson smear again (the other figure)
    { type: "red_burst", t0: s(33), t1: s(35), tin: "glitch", accent: 3, lightOverlay: false,
      shots: [{ t0: s(33), t1: s(35), layers: [N()], c0: [1060, 1250, 1900], c1: [1060, 1250, 2150], focus: "half", shadow: false }],
      text: {
        33: { lvl: "A", layout: "line", x: 960, y: 900, size: 30 },
        34: { lvl: "A", layout: "line", x: 960, y: 900, size: 30 },
      } },
    // ---- climax: the two faces close in, giant type
    { type: "giant_type", t0: s(35), t1: s(36), tin: "flash",
      shots: [{ t0: s(35), t1: s(36), layers: [P({ ox: -620, ox1: -300 }), N({ ox: 700, ox1: 380 })], c0: [1080, 1150, 3300], c1: [1080, 1080, 2700] }],
      text: { 35: { lvl: "B", x: 0, y: 600, rot: -6, size: 0.3 * H, weight: 300, rows: [{ t: "やっと", y: 300, scale: 0.6 }, { t: "僕を見つけたんだ", x: 260, y: 300 }, { t: "嗚呼", x: 1300, y: 560 }] } } },
    { type: "full_body_whiteout", t0: s(36), t1: e(36), tin: "cut",
      shots: [{ t0: s(36), t1: e(36), layers: [P()], c0: [1065, 1950, 5600], c1: [1065, 1900, 5000] }],
      text: { 36: { lvl: "A", layout: "vert", x: 1400, ink: "dark", y: 260, size: 30, gap: 1.3, cols: ["こうやって", "アイは終わった"] } } },
    { type: "white_soft", t0: e(36), t1: s(37), geo: true, tin: "blur", lightOverlay: false, hud: false },
    // ---- outro
    { type: "black_line", t0: s(37), t1: s(38), tin: "black", hud: false, lightOverlay: false,
      text: { 37: { lvl: "A", layout: "line", x: 960, y: 540, size: 26 } } },
    { type: "hud_two_shot", t0: s(38), t1: s(40), tin: "bleed",
      split: [[s(38), 260], [s(38) + 1.4, 190], [s(39), 120], [s(39) + 1.6, 50], [s(40) - 0.95, 0]],
      text: {
        38: { lvl: "A", layout: "vert", x: 170, y: 230, size: 30, gap: 1.3, cols: ["この世界に", "産み落とされた", "モンスター"] },
        39: { lvl: "A", layout: "vert", x: 1720, y: 230, size: 30, gap: 1.3, cols: ["僕は人生最大の", "したり顔で"] },
      } },
    // ---- one: the nurse dissolves into the patient, colour returns
    { type: "giant_type", t0: s(40), t1: e(40), tin: "flash",
      pulse: s(40) + 0.05,
      shots: [{ t0: s(40), t1: e(40), layers: [
        P({ color: (t) => 0.55 * sease((t - s(40) - 0.3) / 1.6) })], c0: [1000, 1150, 2350], c1: [960, 1100, 2150] }],
      text: { 40: { lvl: "B", x: 10, y: 640, rot: -5, size: 0.3 * H, weight: 300, rows: [{ t: "今この世界と", y: 300 }, { t: "一つになった。", x: 700, y: 560 }] } } },
    { type: "title_card_shadow", t0: e(40), t1: 142.3, geo: true, tin: "blur", merge: true, titleAt: e(40) + 0.4, credits: true, lightOverlay: true },
    { type: "fade_out", t0: 142.3, t1: 143.4, tin: "black", hud: false },
  ];
  for (const sc of SCENES2) {
    if (sc.lightOverlay === undefined) sc.lightOverlay = true;
    (sc.shots || []).forEach((sh, i) => {
      if (sc.t0 >= 20 && !sh.dustBack && sh.keyLight === undefined) { sh.keyLight = true; sh.longShadow = sh.longShadow ?? true; }
      if (i === 0 && !sh.tin && sc.tin) sh.tin = sc.tin;
    });
  }
  for (const sc of SCENES2) (sc.shots || []).forEach((sh, i) => {
    const d = (i + Math.round(sc.t0)) % 2 ? 1 : -1;
    if (sh.r0 === undefined) sh.r0 = 0.9 * d;
    if (sh.r1 === undefined) sh.r1 = -0.5 * d;
  });
  for (let i = 1; i < SCENES2.length; i++) if (SCENES2[i].type === SCENES2[i - 1].type) throw new Error("adjacent scenes share a type at " + SCENES2[i].t0);
  // every B/C row set must spell the lyric exactly
  for (const sc of SCENES2) for (const [id, sp] of Object.entries(sc.text || {}))
    if (typeof sp !== "function" && sp.lvl === "B" && sp.rows.map((r) => r.t).join("") !== L2(+id).ja) throw new Error(`B rows for ${id} != lyric`);
}
function charT2(i, k) { const c = L2(i).chars; return c[Math.min(k, c.length - 1)]; }
const sceneAt = (t) => SCENES2.find((s) => t >= s.t0 && t < s.t1) || SCENES2[SCENES2.length - 1];

// ---------------------------------------------------------------- frame
let CV2, CX2, PX2 = 1, GRAIN = 0.07, FLICKER = 0.05;
function post(ctx, t) {
  // film grain: ~2 px clumps, new random offset every frame (part of the look in preview and final)
  const fr = Math.floor(t * 30), tile = A2.grain[((fr % A2.grain.length) + A2.grain.length) % A2.grain.length];
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

let IMG, IX, MASK = 0, NOTEXT = false, SHL;
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
  const cam = info.still ? { dx: 0, dy: 0, r: 0, s: 1 } : handheld(t), tr = transitionAt(t);
  const ov = info.still ? 1 : 1.035;
  ctx.save();
  ctx.translate(W / 2 + cam.dx, H / 2 + cam.dy); ctx.rotate(cam.r); ctx.scale(cam.s * ov, cam.s * ov); ctx.translate(-W / 2, -H / 2);  // 3.5 % overscan
  const tri = tr ? 1 - Math.abs(tr.u * 2 - 1) : 0;    // 0 -> 1 at the cut -> 0
  if (!tr || tr.kind === "cut" || tr.kind === "flash" || tr.kind === "black") ctx.drawImage(IMG, 0, 0, W, H);
  else if (tr.kind === "whip") {          // horizontal blur + fast pan, no white; image scaled so no edge shows
    const u = tr.u, k = u < 0.5 ? sease(u * 2) : 1 - sease((u - 0.5) * 2), pan = (u < 0.5 ? -1 : 1) * 200 * k, z = 1 + 0.32 * k;
    ctx.save(); ctx.translate(W / 2 + pan, H / 2); ctx.scale(z, z); ctx.translate(-W / 2, -H / 2); blitBlur(ctx, IMG, 40 + 220 * k, 0); ctx.restore();
  } else if (tr.kind === "blur") {        // focus blur out / in
    ctx.filter = `blur(${(26 * tri * PX2).toFixed(1)}px)`; ctx.drawImage(IMG, 0, 0, W, H); ctx.filter = "none";
  } else if (tr.kind === "glitch") {      // pixel-block slices, < 0.2 s
    ctx.drawImage(IMG, 0, 0, W, H); glitchSlices(ctx, t, tri);
  } else {                                 // light bleed: exposure up + diagonal blur, peak near white, new shot resolves
    const u = tr.u, ang = -30 * Math.PI / 180;
    const blur = u < 3 / 8 ? lerp(40, 120, u / (3 / 8)) : u < 5 / 8 ? 120 : lerp(120, 0, (u - 5 / 8) / (3 / 8));
    blitBlur(ctx, IMG, blur, ang);
  }
  if (info.glitchAt !== undefined && t >= info.glitchAt && t < info.glitchAt + 0.18) glitchSlices(ctx, t, 1);
  ctx.restore();
  INK_DARK = 0;
  if (tr && tr.kind === "bleed") {        // exposure curve: rises to near-white at frames 3-4, falls back on the new shot
    const u = tr.u, ex = u < 3 / 8 ? sease(u / (3 / 8)) * 0.88 : u < 5 / 8 ? 0.94 : (1 - sease((u - 5 / 8) / (3 / 8))) * 0.88;
    INK_DARK = clamp((ex - 0.35) / 0.5);
    ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = `rgba(250,249,244,${ex})`; ctx.fillRect(0, 0, W, H);
    if (u >= 3 / 8 && u < 5 / 8) { ctx.globalAlpha = 0.9; ctx.translate(W / 2, H / 2); ctx.rotate(STRIPE_ANG); ctx.translate(-3000 + (t * 60) % 1500, -1500); ctx.drawImage(A2.stripeTex, 0, 0); }
    ctx.restore();
  }
  if (tr && tr.kind === "flash") { const ex = Math.max(0, 1 - Math.abs(tr.u - 0.5) * 4) * 0.9; INK_DARK = clamp((ex - 0.35) / 0.5); ctx.fillStyle = `rgba(250,249,245,${ex})`; ctx.fillRect(0, 0, W, H); }
  if (tr && tr.kind === "black") { ctx.fillStyle = `rgba(0,0,0,${tri})`; ctx.fillRect(0, 0, W, H); }
  if (info.white) { ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = `rgba(250,249,245,${info.white})`; ctx.fillRect(0, 0, W, H); ctx.restore(); INK_DARK = Math.max(INK_DARK, clamp((info.white - 0.4) / 0.4)); }
  // brightness breathing and light flicker (15 fps steps)
  if (!info.still) {
    const f = 0.02 * Math.sin(2 * Math.PI * 0.3 * t) + FLICKER * (hash(Math.floor(t * 15) + 77) - 0.5) * 2;
    ctx.fillStyle = f > 0 ? `rgba(255,255,255,${f})` : `rgba(0,0,0,${-f})`; ctx.fillRect(0, 0, W, H);
  }
  // lyrics ride the camera at 40 % (parallax), never cut by transitions
  ctx.save(); ctx.translate(cam.dx * 0.4, cam.dy * 0.4);
  if (!NOTEXT) for (const [id, sp] of Object.entries(sc.text || {})) drawLyric(ctx, typeof sp === "function" ? sp(t) : sp, L2(+id), t);
  if (info.credits) drawCredits2(ctx, info.credits, ...(info.creditPos || []));
  if (info.title) drawTitleBox(ctx, info.title, 960, 470);
  ctx.restore();
  ctx.setTransform(PX2, 0, 0, PX2, 0, 0);
  ctx.globalAlpha = sc.vignette ?? 0.8; ctx.drawImage(A2.vignette, 0, 0, W, H); ctx.globalAlpha = 1;
  post(ctx, t);
  if (sc.geo) drawGeo(ctx, t, 1, info.drift || 0, info.hudDark);
  if (sc.hud !== false && info.hud !== false && R[sc.type]) drawHUD2(ctx, t, 1, info.drift || 0, info.hudDark);
  drawBars(ctx, info.bars || 0);
  if (sc.type === "fade_out") { ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H); }
  drawKo(ctx, t);
}
function glitchSlices(ctx, t, amt) {
  const fr = Math.floor(t * 30);
  for (let i = 0; i < 10; i++) {
    const y = hash2(fr, i) * H, h = 10 + hash2(i, fr) * 70, off = (hash2(fr + 7, i) - 0.5) * 180 * amt;
    ctx.drawImage(IMG, 0, y * PX2, IMG.width, h * PX2, off, y, W, h);
    if (i % 3 === 0) { ctx.fillStyle = `rgba(${i % 2 ? 230 : 20},${i % 2 ? 230 : 20},${i % 2 ? 228 : 22},0.55)`; ctx.fillRect(hash2(i, fr + 3) * W, y, 40 + hash2(fr, i + 9) * 260, h * 0.4); }
  }
}
function drawCredits2(ctx, a, x0 = 620, y0 = 330) {
  const rows = [["Music", "ろくろ"], ["Vocal", "暁山瑞希"], ["Movie", "meel"]];
  ctx.save(); ctx.globalAlpha = a * 0.9; ctx.fillStyle = "#ecece8"; ctx.textBaseline = "middle";
  ctx.shadowColor = "rgba(0,0,0,0.5)"; ctx.shadowBlur = 6;
  rows.forEach(([k, v], i) => { const y = y0 + i * 54;
    ctx.font = "300 26px UI"; ctx.fillText(k + "  /", x0, y);
    ctx.font = "300 30px LyricMincho"; ctx.fillText(v, x0 + 140, y); });
  ctx.restore();
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
  IMG = cnv(CV2.width, CV2.height); IX = IMG.getContext("2d"); ACC = cnv(CV2.width, CV2.height); SHL = cnv(CV2.width, CV2.height);
  SUBS = opts.post ? 3 : 1;
  CUTS = [];
  for (const sc of SCENES2) {
    (sc.shots || []).forEach((sh) => { if (sh.tin) CUTS.push({ t: sh.t0, kind: sh.tin }); });
    if (!sc.shots && sc.tin) CUTS.push({ t: sc.t0, kind: sc.tin });
  }
  CUTS.sort((a, b) => a.t - b.t);
  for (let i = 1; i < CUTS.length; i++) if (CUTS[i].t >= 20 && CUTS[i].kind === CUTS[i - 1].kind) throw new Error(`same transition twice in a row at ${CUTS[i].t}: ${CUTS[i].kind}`);
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
window.stillTimes = () => [24, 30, 37, 42, 46, 51, 57, 61.6, 65.5, 69, 72, 76, 79, 81.5, 84, 86.5, 90.5, 94, 98, 101.2, 103, 106, 110, 114, 118, 122.5, 126.5, 129.6, 132, 135, 138.5, 141];
window.faceCheck = (times) => times.map((t) => { const sc = sceneAt(t); const sh = sc.shots && (sc.shots.find((s) => t >= s.t0 && t < s.t1)); return sh ? { t, eyes: eyeRects(sh, t) } : { t, eyes: [] }; });
// Camera probe: screen position of a fixed stage point (shot crop centre at mid-shot) incl. Ken Burns, roll and handheld.
window.camProbe = (t) => {
  const sc = sceneAt(t), sh = sc.shots && shotAt(sc, t); if (!sh || sh.black) return null;
  const cr = cropAt(sh, t), cam = handheld(t);
  const P = [(sh.c0[0] + sh.c1[0]) / 2, (sh.c0[1] + sh.c1[1]) / 2];
  let x = (P[0] - cr.x0) * cr.s, y = (P[1] - cr.y0) * cr.s;                       // Ken Burns
  const cx = W / 2, cy = H / 2, c = Math.cos(cr.rot), s = Math.sin(cr.rot);       // roll
  [x, y] = [cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c];
  const z = cam.s * 1.035, c2 = Math.cos(cam.r), s2 = Math.sin(cam.r);           // handheld
  [x, y] = [cx + cam.dx + z * ((x - cx) * c2 - (y - cy) * s2), cy + cam.dy + z * ((x - cx) * s2 + (y - cy) * c2)];
  return { t, shot: sh.t0, x, y, kbx: (P[0] - cr.x0) * cr.s, kby: (P[1] - cr.y0) * cr.s, scale: cr.s };
};
// Text safety: Japanese glyph pixels inside the eye/face boxes, and contrast under the glyphs.
window.textCheck = (t) => {
  const sc = sceneAt(t), Wd = CV2.width, Hd = CV2.height;
  MASK = 2; composeFrame(t, true); const face = CX2.getImageData(0, 0, Wd, Hd).data; MASK = 0;
  NOTEXT = true; composeFrame(t); NOTEXT = false; const pic = CX2.getImageData(0, 0, Wd, Hd).data;
  // text alone, same camera parallax as composeFrame
  const cam = handheld(t);
  CX2.setTransform(PX2, 0, 0, PX2, 0, 0); CX2.clearRect(0, 0, W, H); CX2.save(); CX2.translate(cam.dx * 0.4, cam.dy * 0.4);
  const saveInk = INK_DARK; INK_DARK = 0;
  for (const [id, sp] of Object.entries(sc.text || {})) drawLyric(CX2, typeof sp === "function" ? sp(t) : sp, L2(+id), t);
  INK_DARK = saveInk; CX2.restore();
  const txt = CX2.getImageData(0, 0, Wd, Hd).data;
  let n = 0, onFace = 0, lum = 0, inkL = 0;
  for (let i = 0; i < txt.length; i += 4) {
    if (txt[i + 3] < 120) continue;
    n++; if (face[i] > 200 && face[i + 1] < 60) onFace++;
    lum += 0.299 * pic[i] + 0.587 * pic[i + 1] + 0.114 * pic[i + 2];
    inkL += 0.299 * txt[i] + 0.587 * txt[i + 1] + 0.114 * txt[i + 2];
  }
  return { t, textPx: n, onFace, picUnderText: n ? Math.round(lum / n) : null, ink: n ? Math.round(inkL / n) : null };
};
