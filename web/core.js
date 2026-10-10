// Pure helpers. Nothing here keeps state between frames: every value is a function of t.
"use strict";
const W = 1920, H = 1080;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, k) => a + (b - a) * k;
const smooth = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };
const easeOut = (x) => 1 - Math.pow(1 - clamp(x), 3);
const easeIn = (x) => Math.pow(clamp(x), 2);

// Closed-form step response of a damped spring (0 -> 1). zeta < 1 gives a small overshoot.
function spring(dt, omega = 14, zeta = 0.8) {
  if (dt <= 0) return 0;
  if (zeta >= 1) return 1 - Math.exp(-omega * dt) * (1 + omega * dt);
  const wd = omega * Math.sqrt(1 - zeta * zeta);
  return 1 - Math.exp(-zeta * omega * dt) * (Math.cos(wd * dt) + (zeta * omega / wd) * Math.sin(wd * dt));
}

// A value that is retargeted at several times = sum of one spring per change.
// keys: [[t, value, {w, z, cut}], ...] sorted by t.
function track(v0, keys) {
  const k = keys.map(([t, v, o]) => ({ t, v, w: (o && o.w) || 10, z: (o && o.z) || 0.85, cut: !!(o && o.cut) }));
  return (t) => {
    let out = v0, prev = v0;
    for (const e of k) {
      if (t < e.t) break;
      out += (e.v - prev) * (e.cut ? 1 : spring(t - e.t, e.w, e.z));
      prev = e.v;
    }
    return out;
  };
}

// Quick attack, exponential decay impulse (camera pops, flashes).
const impulse = (dt, decay = 9, attack = 60) => dt < 0 ? 0 : (1 - Math.exp(-dt * attack)) * Math.exp(-dt * decay);

// Deterministic hash noise.
function hash(n) {
  n = (n ^ 61) ^ (n >>> 16); n = Math.imul(n, 9); n ^= n >>> 4; n = Math.imul(n, 0x27d4eb2d); n ^= n >>> 15;
  return (n >>> 0) / 4294967296;
}
const hash2 = (a, b) => hash(Math.imul(a, 73856093) ^ Math.imul(b + 1, 19349663));
function rng(seed) { // mulberry32, only used at load time to build caches
  return () => { seed |= 0; seed = seed + 0x6d2b79f5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}

// Window envelope: 0 outside [a, b], ramps in/out.
const env = (t, a, b, fin = 0.15, fout = 0.15) => t < a || t > b ? 0 : Math.min(clamp((t - a) / fin), clamp((b - t) / fout));

// ---- music data lookups
const D = window.DATA;
const FPS_DATA = D.fps;
const energyAt = (t) => D.energy[clamp(Math.floor(t * FPS_DATA), 0, D.energy.length - 1)];
const onsetAt = (t) => D.onsetCurve[clamp(Math.floor(t * FPS_DATA), 0, D.onsetCurve.length - 1)];
// Snap a designed accent to the nearest measured onset (never to a theoretical beat).
function snapOnset(t, win = 0.15, minS = 0.2) {
  let best = t, bd = win;
  for (const [ot, s] of D.onsets) if (s >= minS && Math.abs(ot - t) < bd) { bd = Math.abs(ot - t); best = ot; }
  return best;
}
const onsetsIn = (a, b, minS) => D.onsets.filter(([t, s]) => t >= a && t < b && s >= minS).map(([t, s]) => ({ t, s }));
const section = (name) => D.sections.find((s) => s.name === name);
const lyric = (id) => D.lyrics.find((l) => l.id === id);

// ---- colors
function hex(c) { const n = parseInt(c.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
const rgb = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
const mixc = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
const ACCENT = { red: hex("#C8102E"), cyan: hex("#8FD3D8"), orange: hex("#E8772E"), white: hex("#F4F2EE"), black: hex("#0B0C0F") };
