#!/usr/bin/env node
// Deterministic frame renderer for web/index.html.
//
//   node tools/render.mjs                          # final: 1920x1080 30fps, all sections -> out/final/slowdowner.mp4
//   node tools/render.mjs --preview                # 960x540 15fps preview of everything
//   node tools/render.mjs --preview --sections chorus1,C   # re-render only changed sections, then re-concat
//   node tools/render.mjs --preview --range 64.2-69.2      # short clip with its audio
//   node tools/render.mjs --preview --stills       # one still per section
//   node tools/render.mjs --bench chorus2          # time 10 final-quality frames of a section, print ETA
//
// Resumable: finished chunks are recorded in <out>/manifest.json and skipped on the next run.
// Progress goes to <out>/render.log.
import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web");
const AUDIO = path.join(ROOT, "assets/audio/song.mp3");
const DATA = JSON.parse(fs.readFileSync(path.join(ROOT, "data/sections.json"), "utf8"));
const DURATION = 143.333875;

// ---------------------------------------------------------------- args
const argv = process.argv.slice(2);
const flag = (n) => argv.includes("--" + n);
const opt = (n, d) => { const i = argv.indexOf("--" + n); return i >= 0 ? argv[i + 1] : d; };
const preview = !flag("final");            // preview is the default; --final = 1920x1080 30fps, all post effects
const width = +opt("w", preview ? 960 : 1920);
const fps = +opt("fps", preview ? 15 : 30);
const outDir = path.resolve(ROOT, opt("out", preview ? "out/preview" : "out/final"));
const workers = +opt("workers", Math.max(1, os.cpus().length - 1));
const jpegQ = +opt("q", preview ? 0.85 : 0.95);
const crf = +opt("crf", preview ? 23 : 15);
const x264preset = opt("preset", preview ? "veryfast" : "medium");
fs.mkdirSync(outDir, { recursive: true });

const logFile = path.join(outDir, "render.log");
const log = (...a) => { const s = `[${new Date().toISOString()}] ${a.join(" ")}`; console.log(s); fs.appendFileSync(logFile, s + "\n"); };

// ---------------------------------------------------------------- static server (canvas must stay untainted)
function serve() {
  const types = { ".html": "text/html", ".js": "text/javascript", ".png": "image/png", ".woff2": "font/woff2", ".mp3": "audio/mpeg", ".json": "application/json" };
  const srv = http.createServer((req, res) => {
    const u = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const f = u === "/song.mp3" ? AUDIO : path.join(WEB, path.normalize(u === "/" ? "/index.html" : u));
    if (!f.startsWith(WEB) && f !== AUDIO) { res.writeHead(403).end(); return; }
    fs.readFile(f, (err, buf) => {
      if (err) { res.writeHead(404).end(); return; }
      res.writeHead(200, { "content-type": types[path.extname(f)] || "application/octet-stream" }).end(buf);
    });
  });
  return new Promise((ok) => srv.listen(0, "127.0.0.1", () => ok(srv)));
}

async function openPage(browser, port) {
  const page = await browser.newPage({ viewport: { width, height: Math.round(width * 9 / 16) }, deviceScaleFactor: 1 });
  page.on("console", (m) => { if (m.type() === "warning" || m.type() === "error") log("page:", m.text()); });
  page.on("pageerror", (e) => log("pageerror:", e.message));
  await page.goto(`http://127.0.0.1:${port}/index.html`);
  const info = await page.evaluate(([w, post]) => window.init(w, { post }), [width, !preview]);
  if (info.fallbacks.length) throw new Error("font fallback for: " + info.fallbacks.join(" "));
  return page;
}
const grab = (page, t, blur, type = "image/jpeg") =>
  page.evaluate(([t, blur, type, q]) => { window.seek(t, { blur }); return document.getElementById("c").toDataURL(type, q).split(",")[1]; }, [t, blur, type, jpegQ])
    .then((b64) => Buffer.from(b64, "base64"));

function ffmpeg(args) {
  const p = spawn("ffmpeg", ["-hide_banner", "-loglevel", process.env.FFLOG || "error", "-y", ...args], { stdio: ["pipe", "inherit", "inherit"] });
  p.done = new Promise((ok, err) => p.on("close", (c) => (c === 0 ? ok() : err(new Error("ffmpeg exit " + c)))));
  return p;
}
const encodeArgs = (out) => ["-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
  "-c:v", "libx264", "-preset", x264preset, "-crf", String(crf), "-pix_fmt", "yuv420p", "-r", String(fps),
  "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-g", String(fps * 2), out];

// ---------------------------------------------------------------- chunks = sections
function chunks(only) {
  const total = Math.ceil(DURATION * fps);
  const list = DATA.map((s, i) => ({ name: `${String(i).padStart(2, "0")}_${s.name}`, sec: s.name,
    f0: Math.round(s.start * fps), f1: i === DATA.length - 1 ? total : Math.round(DATA[i + 1].start * fps) }));
  list[0].f0 = 0;
  return only ? list.filter((c) => only.includes(c.sec)) : list;
}
const settingsKey = JSON.stringify({ width, fps, jpegQ, crf, x264preset });
function manifest() { try { return JSON.parse(fs.readFileSync(path.join(outDir, "manifest.json"), "utf8")); } catch { return {}; } }
function markDone(c) {
  const m = manifest(); m[c.name] = { f0: c.f0, f1: c.f1, settings: settingsKey, at: new Date().toISOString() };
  fs.writeFileSync(path.join(outDir, "manifest.json.tmp"), JSON.stringify(m, null, 1));
  fs.renameSync(path.join(outDir, "manifest.json.tmp"), path.join(outDir, "manifest.json"));
}

async function renderChunk(page, c) {
  const out = path.join(outDir, "chunks", c.name + ".mp4"), part = out.replace(/\.mp4$/, ".part.mp4");
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const ff = ffmpeg(encodeArgs(part));
  const n = c.f1 - c.f0, t0 = Date.now();
  for (let f = c.f0; f < c.f1; f++) {
    const t = f / fps;
    const blur = (await page.evaluate((t) => window.needsBlur(t), t)) ? 0.5 / fps : 0;
    const buf = await grab(page, t, blur);
    if (!ff.stdin.write(buf)) await new Promise((ok) => ff.stdin.once("drain", ok));
    const k = f - c.f0 + 1;
    if (k % (fps * 2) === 0 || k === n) {
      const ms = (Date.now() - t0) / k;
      log(`${c.name} ${k}/${n} frames  ${ms.toFixed(0)} ms/frame  chunk ETA ${((n - k) * ms / 1000).toFixed(0)} s`);
    }
  }
  ff.stdin.end(); await ff.done;
  fs.renameSync(part, out);
  markDone(c);
}

async function runChunks(list, force = false) {
  const m = manifest();
  const todo = force ? list : list.filter((c) => !(m[c.name] && m[c.name].settings === settingsKey && fs.existsSync(path.join(outDir, "chunks", c.name + ".mp4"))));
  log(`render ${width}px ${fps}fps: ${list.length} chunks, ${list.length - todo.length} already done, ${todo.length} to render, ${workers} workers`);
  const srv = await serve(), port = srv.address().port, t0 = Date.now();
  const queue = [...todo].sort((a, b) => (b.f1 - b.f0) - (a.f1 - a.f0)); // longest first
  await Promise.all(Array.from({ length: Math.min(workers, queue.length) }, async () => {
    const browser = await chromium.launch({ args: ["--disable-gpu", "--force-color-profile=srgb", "--font-render-hinting=none", "--disable-lcd-text"] });
    const page = await openPage(browser, port);
    while (queue.length) { const c = queue.shift(); log(`start ${c.name} (${c.f1 - c.f0} frames)`); await renderChunk(page, c); log(`done  ${c.name}`); }
    await browser.close();
  }));
  srv.close();
  log(`chunks finished in ${((Date.now() - t0) / 60000).toFixed(1)} min`);
}

async function concatAndMux() {
  const all = chunks();
  const listFile = path.join(outDir, "concat.txt");
  for (const c of all) if (!fs.existsSync(path.join(outDir, "chunks", c.name + ".mp4"))) { log(`missing chunk ${c.name}, not muxing yet`); return; }
  fs.writeFileSync(listFile, all.map((c) => `file 'chunks/${c.name}.mp4'`).join("\n") + "\n");
  const video = path.join(outDir, "video_only.mp4"), final = path.join(outDir, preview ? "preview.mp4" : "slowdowner.mp4");
  await ffmpeg(["-f", "concat", "-safe", "0", "-i", listFile, "-c", "copy", video]).done;
  await ffmpeg(["-i", video, "-i", AUDIO, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
    "-movflags", "+faststart", final]).done;
  log(`wrote ${final}`);
}

// ---------------------------------------------------------------- modes
async function stills() {
  const srv = await serve(); const browser = await chromium.launch({ args: ["--disable-gpu", "--force-color-profile=srgb"] });
  const page = await openPage(browser, srv.address().port);
  const times = opt("times") ? opt("times").split(",").map(Number) : null;
  const picks = times || (await page.evaluate(() => window.stillTimes()));
  fs.mkdirSync(path.join(outDir, "stills"), { recursive: true });
  for (const [i, t] of picks.entries()) {
    const buf = await grab(page, t, 0, "image/png");
    const f = path.join(outDir, "stills", `${String(i).padStart(2, "0")}_${t.toFixed(2)}.png`); fs.writeFileSync(f, buf); log("still", f);
  }
  await browser.close(); srv.close();
}
async function rangeClip(spec) {
  const [a, b] = spec.split("-").map(Number);
  const srv = await serve(); const browser = await chromium.launch({ args: ["--disable-gpu", "--force-color-profile=srgb"] });
  const page = await openPage(browser, srv.address().port);
  const name = `clip_${a}-${b}`, vid = path.join(outDir, name + "_v.mp4"), out = path.join(outDir, name + ".mp4");
  const ff = ffmpeg(encodeArgs(vid)); const t0 = Date.now();
  const f0 = Math.round(a * fps), f1 = Math.round(b * fps);
  for (let f = f0; f < f1; f++) {
    const t = f / fps, blur = (await page.evaluate((t) => window.needsBlur(t), t)) ? 0.5 / fps : 0;
    if (!ff.stdin.write(await grab(page, t, blur))) await new Promise((ok) => ff.stdin.once("drain", ok));
  }
  ff.stdin.end(); await ff.done; await browser.close(); srv.close();
  await ffmpeg(["-i", vid, "-ss", String(f0 / fps), "-t", String((f1 - f0) / fps), "-i", AUDIO, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]).done;
  fs.unlinkSync(vid);
  log(`wrote ${out} (${((Date.now() - t0) / (f1 - f0)).toFixed(0)} ms/frame)`);
}
async function bench(secName) {
  const c = chunks([secName])[0];
  const srv = await serve(); const browser = await chromium.launch({ args: ["--disable-gpu", "--force-color-profile=srgb", "--font-render-hinting=none"] });
  const page = await openPage(browser, srv.address().port);
  await grab(page, c.f0 / fps, 0); // warm-up
  const N = 10, step = Math.max(1, Math.floor((c.f1 - c.f0) / N)); let ms = 0;
  for (let i = 0; i < N; i++) {
    const t = (c.f0 + i * step) / fps, blur = (await page.evaluate((t) => window.needsBlur(t), t)) ? 0.5 / fps : 0;
    const s = performance.now(); await grab(page, t, blur); ms += performance.now() - s;
  }
  await browser.close(); srv.close();
  const per = ms / N, total = Math.ceil(DURATION * fps);
  const encodeOverhead = 1.15; // x264 runs alongside the browsers
  const est = total * per * encodeOverhead / Math.min(workers, chunks().length) / 1000;
  log(`bench ${secName} @ ${width}px: ${per.toFixed(1)} ms/frame (render+encode to JPEG), ${total} frames, ${workers} workers -> ~${(est / 60).toFixed(1)} min total`);
}

async function check() {
  const srv = await serve(); const browser = await chromium.launch({ args: ["--disable-gpu"] });
  const page = await openPage(browser, srv.address().port);
  const bad = await page.evaluate(() => window.checkText());
  await browser.close(); srv.close();
  log(bad.length ? "LAYOUT PROBLEMS " + JSON.stringify(bad) : "layout check OK: no Japanese text in the subtitle band or outside safe margins; no font fallbacks");
  return bad;
}

async function luma(times) {
  const srv = await serve(); const browser = await chromium.launch({ args: ["--disable-gpu"] });
  const page = await openPage(browser, srv.address().port);
  const out = [];
  for (const t of times) out.push(await page.evaluate((t) => window.lumaStats(t), t));
  await browser.close(); srv.close();
  for (const r of out) log(`luma t=${r.t}: figure ${r.figure}  face ${r.face}  wall ${r.wall}`);
  return out;
}

async function camspeed() {
  const srv = await serve(); const browser = await chromium.launch({ args: ["--disable-gpu"] });
  const page = await openPage(browser, srv.address().port);
  const pts = await page.evaluate(() => { const o = []; for (let f = 0; f < 600; f++) o.push(window.camProbe(f / 30)); return o; });
  await browser.close(); srv.close();
  const shots = [...new Set(pts.filter(Boolean).map((p) => p.shot))];
  for (const s0 of shots) {
    const p = pts.filter((q) => q && q.shot === s0), v = [], kb = [];
    for (let i = 1; i < p.length; i++) { v.push(Math.hypot(p[i].x - p[i - 1].x, p[i].y - p[i - 1].y)); kb.push(Math.hypot(p[i].kbx - p[i - 1].kbx, p[i].kby - p[i - 1].kby) + Math.abs(p[i].scale - p[i - 1].scale) * 1500); }
    const n = Math.floor(v.length / 3), m = (a) => (a.reduce((x, y) => x + y, 0) / a.length).toFixed(2);
    log(`shot @${s0}s  total camera px/frame: ${m(v.slice(0, n))} > ${m(v.slice(n, 2 * n))} > ${m(v.slice(2 * n))}   Ken Burns only: ${m(kb.slice(0, n))} > ${m(kb.slice(n, 2 * n))} > ${m(kb.slice(2 * n))}`);
  }
}

const run = async () => {
  if (flag("camspeed")) return camspeed();
  if (opt("luma")) return luma(opt("luma").split(",").map(Number));
  if (flag("check")) return check();
  if (flag("stills")) return stills();
  if (opt("range")) return rangeClip(opt("range"));
  if (opt("bench")) return bench(opt("bench"));
  const only = opt("sections") ? opt("sections").split(",") : null;
  await runChunks(chunks(only), !!only); // named sections are always re-rendered
  await concatAndMux();
};
run().catch((e) => { log("ERROR", e.stack || e.message); process.exit(1); });
