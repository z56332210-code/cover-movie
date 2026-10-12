#!/usr/bin/env node
// Still frames from web/venom/index.html.
//   node tools/stills_venom.mjs --times 56.3,35.6 [--w 1920] [--en en-bodoni] [--out out/stills]
import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web/venom");
const argv = process.argv.slice(2), opt = (n, d) => { const i = argv.indexOf("--" + n); return i >= 0 ? argv[i + 1] : d; }, flag = (n) => argv.includes("--" + n);
// threshold from the reference: its weakest lyric (small white text on lavender, 0:18.6) measures 24.5 luma above its
// surroundings (local-median method); ours is checked as text-layer minus no-text render, the same quantity
const CONTRAST_MIN = 25;
const width = +opt("w", 1920), times = opt("times", "5").split(",").map(Number), out = path.resolve(ROOT, opt("out", "out/stills")), en = opt("en", "en-playfair");
fs.mkdirSync(out, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".png": "image/png", ".woff2": "font/woff2", ".json": "application/json" };
const srv = http.createServer((req, res) => {
  const f = path.join(WEB, path.normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)));
  if (!f.startsWith(WEB)) return res.writeHead(403).end();
  fs.readFile(f, (e, b) => (e ? res.writeHead(404).end() : res.writeHead(200, { "content-type": types[path.extname(f)] || "application/octet-stream" }).end(b)));
});
await new Promise((ok) => srv.listen(0, "127.0.0.1", ok));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width, height: Math.round((width * 9) / 16) } });
page.on("pageerror", (e) => console.error("pageerror:", e.message));
page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") console.error("page:", m.text()); });
await page.goto(`http://127.0.0.1:${srv.address().port}/index.html`);
const info = await page.evaluate(([w, en]) => window.init(w, { enFont: en }), [width, en]);
if (info.fallbacks.length) console.error("FONT FALLBACK:", info.fallbacks.join(""));
if (opt("glitch")) { const [a, b] = opt("glitch").split("-").map(Number); console.log("glitch frames:", JSON.stringify(await page.evaluate(([a, b]) => window.glitchTimes(a, b), [a, b]))); }
if (opt("camspeed")) { const [a, b] = opt("camspeed").split("-").map(Number); for (const r of await page.evaluate(([a, b]) => window.camSpeeds(a, b), [a, b])) console.log("cam", JSON.stringify(r)); }
if (opt("eyecheck")) {
  const L = JSON.parse(fs.readFileSync(path.join(ROOT, "data/lyrics_timed.json"), "utf8")); const [a, b] = opt("eyecheck").split("-").map(Number); let bad = 0, n = 0;
  for (const l of L.filter((l) => l.start >= a && l.start < b)) for (const f of [0.35, 0.7, 0.95]) {
    const t = l.start + (l.end - l.start) * f, pr = await page.evaluate((t) => window.probe(t), t); n++;
    const hit = (p, q) => p[0] < q[0] + q[2] && q[0] < p[0] + p[2] && p[1] < q[1] + q[3] && q[1] < p[1] + p[3];
    const h = pr.text.filter((tb) => pr.eyes.some((e) => hit(tb, e))).length; if (h) { bad++; console.log("EYE HIT line", l.id, t.toFixed(2)); }
    if (!pr.text.length) console.log("NO TEXT line", l.id, "at", t.toFixed(2));
  }
  console.log(`eye check: ${n} probes, ${bad} with glyphs on the eyes`);
}
if (opt("cutcheck")) {
  const [a, b] = opt("cutcheck").split("-").map(Number), bad = await page.evaluate(([a, b]) => window.cutCheck(a, b), [a, b]);
  const by = {}; for (const [t, i, fr, n] of bad) { const k = `shot ${i} ${fr} ${n}`; (by[k] = by[k] || []).push(t); }
  for (const [k, ts] of Object.entries(by)) console.log("CUT VISIBLE", k, ts.length, "frames", ts[0], "-", ts[ts.length - 1]);
  console.log(`cut check ${a}-${b}: ${bad.length} frames with a visible canvas cut`);
}
if (flag("textcheck")) {
  const L = await page.evaluate(() => window.DATA.lyrics); const rows = []; let bad = 0;
  for (const l of L) for (const f of [0.35, 0.7, 0.95]) {
    const t = l.start + (l.end - l.start) * f, r = await page.evaluate((t) => window.textCheck(t), t);
    const problem = r.eyeHits > 0 ? "EYES" : r.textPx < 40 ? "NO TEXT" : r.contrast < CONTRAST_MIN ? "LOW CONTRAST" : "";
    if (problem) bad++;
    rows.push(`${l.id}\t${t.toFixed(2)}\tshot ${r.shot}\ttextPx ${r.textPx}\tcontrast ${r.contrast.toFixed(0)}\t${problem}`);
  }
  fs.writeFileSync(path.join(out, "textcheck.tsv"), rows.join("\n") + "\n");
  console.log(rows.filter((r) => /EYES|NO TEXT|LOW/.test(r)).join("\n"));
  console.log(`text check: ${L.length} lines x 3 = ${rows.length} probes, ${bad} problems (contrast threshold ${CONTRAST_MIN})`);
}
for (const t of times) {
  const t0 = Date.now();
  const pr = await page.evaluate((t) => window.probe(t), t);
  const hit = (a, b) => a[0] < b[0] + b[2] && b[0] < a[0] + a[2] && a[1] < b[1] + b[3] && b[1] < a[1] + a[3];
  const eyeHits = pr.text.filter((tb) => pr.eyes.some((e) => hit(tb, e))).length;
  const r = await page.evaluate((t) => window.seek(t), t); r.eyeHits = eyeHits; r.textBoxes = pr.text.length;
  const b64 = await page.evaluate(() => document.getElementById("c").toDataURL("image/png").split(",")[1]);
  const f = path.join(out, `t${t.toFixed(2)}_${en}.png`); fs.writeFileSync(f, Buffer.from(b64, "base64"));
  console.log(f, JSON.stringify(r), Date.now() - t0, "ms");
}
await browser.close(); srv.close();
