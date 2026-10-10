// Load fonts/images once and build every static cache (textures, silhouettes, blurred layers, sprites).
"use strict";
const ASSETS = {};

function canvas(w, h) { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; }
function loadImage(src) {
  return new Promise((ok, err) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => err(new Error("image " + src)); i.src = src; });
}

const FONTS = [
  ["Mincho", "fonts/mincho-400.woff2", "400"], ["Mincho", "fonts/mincho-700.woff2", "700"],
  ["Mincho", "fonts/mincho-800.woff2", "800"], ["Dela", "fonts/dela.woff2", "400"],
  ["Pretendard", "fonts/pretendard-600.woff2", "600"],
];

async function loadFonts() {
  for (const [fam, url, weight] of FONTS) {
    const f = new FontFace(fam, `url(${url})`, { weight });
    await f.load(); document.fonts.add(f);
  }
  await document.fonts.ready;
  // Fallback check: every lyric glyph must render with our font, not a system fallback.
  const ctx = canvas(10, 10).getContext("2d");
  const missing = [];
  const probe = (fam, weight, chars) => {
    for (const c of new Set(chars)) {
      if (!c.trim()) continue;
      ctx.font = `${weight} 100px ${fam}, monospace`; const a = ctx.measureText(c).width;
      ctx.font = `${weight} 100px ${fam}, serif`; const b = ctx.measureText(c).width;
      ctx.font = `${weight} 100px ${fam}, sans-serif`; const d = ctx.measureText(c).width;
      if (!(a === b && b === d)) missing.push(fam + ":" + c);
    }
  };
  const ja = D.lyrics.map((l) => l.ja).join("") + "スロウダウナー作詞・作曲ろくろ暁山瑞希SLOWDOWNERVocalMoviemeel";
  probe("Mincho", 400, ja); probe("Mincho", 800, ja); probe("Dela", 400, ja);
  probe("Pretendard", 600, D.lyrics.map((l) => l.ko).join(""));
  ASSETS.fontFallbacks = missing;
  if (missing.length) console.warn("FONT FALLBACK", missing.join(" "));
}

function bake(img, fn) { const c = canvas(img.width, img.height); const x = c.getContext("2d"); fn(x, c); return c; }
function silhouette(img, color) {
  return bake(img, (x) => { x.drawImage(img, 0, 0); x.globalCompositeOperation = "source-in"; x.fillStyle = color; x.fillRect(0, 0, img.width, img.height); });
}
function blurred(img, px) { // one-time cache; never a per-frame filter
  const s = 0.5, c = canvas(Math.ceil(img.width * s), Math.ceil(img.height * s)), x = c.getContext("2d");
  x.filter = `blur(${px * s}px)`; x.drawImage(img, 0, 0, c.width, c.height); return c;
}

function paperTexture(seed, w = 1920, h = 1080) {
  const c = canvas(w, h), x = c.getContext("2d"), r = rng(seed);
  x.fillStyle = "#808080"; x.fillRect(0, 0, w, h);
  for (let i = 0; i < 260; i++) { // soft blotches (concrete / paper)
    const px = r() * w, py = r() * h, rad = 40 + r() * 260, v = r() < 0.5 ? 0 : 255;
    const g = x.createRadialGradient(px, py, 0, px, py, rad);
    g.addColorStop(0, `rgba(${v},${v},${v},${0.03 + r() * 0.05})`); g.addColorStop(1, `rgba(${v},${v},${v},0)`);
    x.fillStyle = g; x.fillRect(px - rad, py - rad, rad * 2, rad * 2);
  }
  x.strokeStyle = "rgba(40,40,40,0.10)"; // hairline cracks
  for (let i = 0; i < 18; i++) {
    let px = r() * w, py = r() * h; x.lineWidth = 0.6 + r(); x.beginPath(); x.moveTo(px, py);
    for (let j = 0; j < 12; j++) { px += (r() - 0.5) * 70; py += (r() - 0.5) * 70; x.lineTo(px, py); } x.stroke();
  }
  const d = x.getImageData(0, 0, w, h), a = d.data; // fine grain baked in
  for (let i = 0; i < a.length; i += 4) { const n = (r() - 0.5) * 26; a[i] += n; a[i + 1] += n; a[i + 2] += n; }
  x.putImageData(d, 0, 0);
  return c;
}
function grainTiles(n = 6, size = 256) {
  const out = [];
  for (let k = 0; k < n; k++) {
    const c = canvas(size, size), x = c.getContext("2d"), d = x.createImageData(size, size), r = rng(1000 + k);
    for (let i = 0; i < d.data.length; i += 4) { const v = r() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
    x.putImageData(d, 0, 0); out.push(c);
  }
  return out;
}
function vignette() {
  const c = canvas(W, H), x = c.getContext("2d");
  const g = x.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 1.05);
  g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(0,0,0,0.55)");
  x.fillStyle = g; x.fillRect(0, 0, W, H); return c;
}
function windowLight() { // slanted window beam with soft edges, baked once
  const c = canvas(W, H), x = c.getContext("2d");
  x.filter = "blur(28px)"; x.fillStyle = "rgba(255,255,255,0.9)";
  for (const [ox, w] of [[0, 260], [330, 220], [620, 160]]) {
    x.beginPath(); x.moveTo(500 + ox, -60); x.lineTo(500 + ox + w, -60); x.lineTo(80 + ox + w, H + 60); x.lineTo(80 + ox, H + 60); x.fill();
  }
  return c;
}
function glowSprite(color, size = 256) { // fake glow: pre-rendered radial falloff
  const c = canvas(size, size), x = c.getContext("2d"), g = x.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, rgb(color, 0.9)); g.addColorStop(0.25, rgb(color, 0.45)); g.addColorStop(1, rgb(color, 0));
  x.fillStyle = g; x.fillRect(0, 0, size, size); return c;
}
function streakSprite() { // horizontal light streak
  const c = canvas(1024, 64), x = c.getContext("2d"), g = x.createLinearGradient(0, 0, 1024, 0);
  g.addColorStop(0, "rgba(255,255,255,0)"); g.addColorStop(0.5, "rgba(255,255,255,0.95)"); g.addColorStop(1, "rgba(255,255,255,0)");
  const v = x.createLinearGradient(0, 0, 0, 64); v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(0.5, "rgba(0,0,0,1)"); v.addColorStop(1, "rgba(0,0,0,0)");
  x.fillStyle = g; x.fillRect(0, 0, 1024, 64); x.globalCompositeOperation = "destination-in"; x.fillStyle = v; x.fillRect(0, 0, 1024, 64);
  return c;
}

async function loadAssets() {
  await loadFonts();
  const names = ["patient", "nurse"];
  ASSETS.char = {};
  for (const n of names) {
    const [body, bodyGray, face, faceGray] = await Promise.all([
      loadImage(`img/${n}_body.png`), loadImage(`img/${n}_body_gray.png`), loadImage(`img/${n}_face.png`), loadImage(`img/${n}_face_gray.png`)]);
    ASSETS.char[n] = {
      body, bodyGray, face, faceGray, meta: D.chars[n],
      silDark: silhouette(bodyGray, "#1a1b1e"), silLight: silhouette(bodyGray, "#ffffff"),
      blurGray: blurred(bodyGray, 22),
    };
  }
  ASSETS.paper = paperTexture(7);
  ASSETS.grain = grainTiles();
  ASSETS.vignette = vignette();
  ASSETS.window = windowLight();
  ASSETS.glow = { orange: glowSprite(ACCENT.orange), white: glowSprite(ACCENT.white), red: glowSprite(ACCENT.red) };
  ASSETS.streak = streakSprite();
  // small-canvas scratch buffers reused every frame (contents fully overwritten before use, so no carried state)
  ASSETS.small = canvas(240, 135);
  ASSETS.layer = canvas(W, H);
  ASSETS.prev = canvas(W, H);
}
