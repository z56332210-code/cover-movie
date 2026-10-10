// v2 assets: thin fonts, concrete wall, desaturated full-resolution characters. Loaded once, cached.
"use strict";
const A2 = {};
function cnv(w, h) { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; }
function img(src) { return new Promise((ok, err) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => err(new Error(src)); i.src = src; }); }

const FONTS2 = [
  ["LyricMincho", "fonts/serif-200.woff2", "200"], ["LyricMincho", "fonts/serif-300.woff2", "300"], ["LyricMincho", "fonts/serif-400.woff2", "400"],
  ["UI", "fonts/inter-300.woff2", "300"], ["Sub", "fonts/pretendard-300.woff2", "300"],
];
async function loadFonts2() {
  for (const [fam, url, w] of FONTS2) { const f = new FontFace(fam, `url(${url})`, { weight: w }); await f.load(); document.fonts.add(f); }
  await document.fonts.ready;
  const x = cnv(8, 8).getContext("2d"), miss = [];
  const probe = (fam, w, s) => { for (const c of new Set(s)) { if (!c.trim()) continue;
    const m = (fb) => { x.font = `${w} 100px ${fam}, ${fb}`; return x.measureText(c).width; };
    if (!(m("monospace") === m("serif") && m("serif") === m("sans-serif"))) miss.push(fam + ":" + c); } };
  const ja = D.lyrics.map((l) => l.ja).join("") + "スロウダウナー作詞・作曲ろくろ暁山瑞希";
  probe("LyricMincho", 200, ja); probe("LyricMincho", 300, ja); probe("UI", 300, "SLOWDOWNER Vocal Movie meel");
  probe("Sub", 300, D.lyrics.map((l) => l.ko).join(""));
  A2.fontFallbacks = miss;
}

async function loadAssets2() {
  await loadFonts2();
  const names = ["patient", "nurse"];
  A2.ch = {};
  for (const n of names) {
    const [mono, blur, shadow, color] = await Promise.all(["mono", "blur", "shadow", "color"].map((k) => img(`img/v2/${n}_${k}.png`)));
    A2.ch[n] = { mono, blur, shadow, color, w: 2160, h: 3840 };
  }
  A2.wall = await img("img/v2/concrete.png");
  A2.wallBlur = await img("img/v2/concrete_blur.png");
  A2.smear = await Promise.all([0, 1, 2].map((k) => img(`img/v2/smear${k}.png`)));
  // grain tiles + vignette + soft dot sprite (dust/bokeh) + eye glow, baked once
  A2.grain = [];
  for (let k = 0; k < 6; k++) {
    const c = cnv(256, 256), g = c.getContext("2d"), d = g.createImageData(256, 256), r = rng(500 + k);
    for (let i = 0; i < d.data.length; i += 4) { const v = 128 + (r() - 0.5) * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
    g.putImageData(d, 0, 0); A2.grain.push(c);
  }
  const v = cnv(W, H), vg = v.getContext("2d"), gr = vg.createRadialGradient(W / 2, H / 2, H * 0.45, W / 2, H / 2, H * 1.0);
  gr.addColorStop(0, "rgba(0,0,0,0)"); gr.addColorStop(1, "rgba(0,0,0,0.42)"); vg.fillStyle = gr; vg.fillRect(0, 0, W, H); A2.vignette = v;
  const dot = (rgba) => { const c = cnv(64, 64), g = c.getContext("2d"), q = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    q.addColorStop(0, rgba(1)); q.addColorStop(0.4, rgba(0.5)); q.addColorStop(1, rgba(0)); g.fillStyle = q; g.fillRect(0, 0, 64, 64); return c; };
  A2.dot = dot((a) => `rgba(235,235,232,${a})`);
  A2.small = cnv(240, 135);
  // blinds shadow: soft dark slats, baked once (drawn rotated and sliding as an overlay)
  const bl = cnv(1400, 1400), bx = bl.getContext("2d"); bx.filter = "blur(18px)"; bx.fillStyle = "rgba(0,0,0,1)";
  for (let y = 40; y < 1400; y += 150) bx.fillRect(-50, y, 1500, 62);
  A2.blinds = bl;
}
