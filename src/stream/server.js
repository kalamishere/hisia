#!/usr/bin/env node
// radio/stream/server.js — the local control plane for the hisia.live /
// World Sound stream. One process holds the radio (player.js) and hands out:
//
//   GET  /radio/index.html   the page itself (served from ../ so its relative
//                            library.json / audio/ fetches resolve)
//   GET  /now.json           what is playing, when it started, what is next
//   POST /skip               crossfade to the next track now
//   POST /reload             reload the capture tab in place (no Stop/Start)
//   POST /broadcast          {action:"start"|"stop", targets:[...]}
//   GET  /status.json        live, legs, distinct fps, dropped, uptime, now
//   GET  /pcm                the raw 48k/stereo/s16le radio feed (ffmpeg's
//                            audio input, and the tap used to verify gapless)
//   GET  /stream/console     the operator page
//
// Stream keys live ONLY in radio/stream/.env. They are read here, passed to
// the capture child through its environment, and never logged, never returned
// by /status.json, never written to the log ring.
//
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn } = require("child_process");
const { Player } = require("./player");

const HERE = __dirname;
const RADIO_DIR = path.resolve(HERE, "..");
const PORT = Number(process.env.PORT) || 4700;
const START_AT = Date.now();

// ── log ring (the console shows the last 20 lines) ───────────────────
const LOG = [];
function log(msg) {
  const line = `${new Date().toISOString().slice(11, 19)} ${msg}`;
  LOG.push(line);
  if (LOG.length > 200) LOG.shift();
  console.log(line);
}

// ── .env (no dependency; keys never leave this object) ───────────────
function readEnv() {
  const out = {};
  try {
    for (const raw of fs.readFileSync(path.join(HERE, ".env"), "utf8").split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const i = line.indexOf("=");
      if (i < 0) continue;
      out[line.slice(0, i).trim()] = line.slice(i + 1).trim().replace(/^["']|["']$/g, "");
    }
  } catch { /* no .env — file-only broadcasts still work */ }
  return out;
}

// ── the radio ────────────────────────────────────────────────────────
const player = new Player({
  libraryPath: path.join(RADIO_DIR, "library.json"),
  audioRoot: RADIO_DIR,
  log,
});

// ── broadcast state ──────────────────────────────────────────────────
// Generation guard, straight from pj-battle's BROADCAST_RELIABILITY_REVIEW:
// every start() mints a generation and stop() invalidates it, so a child's
// late exit handler can never null out the generation that replaced it (that
// is what used to orphan ffmpeg and Chrome).
let gen = 0;
let cap = null;          // { proc, gen, targets, startedAt }
let telemetry = { fps: null, maxGap: null, dropped: 0, frames: 0, size: null };

// Everything the process has ever spawned, so the exit handler can reap a
// child even after broadcastStop() has already cleared `cap`. Without this a
// server killed early (before broadcastStop runs, or mid-teardown) could exit
// leaving capture.js — and its Chrome — behind. Ported from hisia-stream.
const spawned = new Set();

function broadcastStart(targets) {
  if (cap) return { ok: false, reason: "already-live" };
  const env = readEnv();
  const legs = [];
  const childEnv = { ...process.env };
  let recordPath = null;

  for (const t of targets) {
    if (t === "twitch") {
      if (!env.TWITCH_STREAM_KEY) return { ok: false, reason: "no TWITCH_STREAM_KEY in radio/stream/.env" };
      childEnv.HISIA_RTMP_TWITCH = `rtmp://live.twitch.tv/app/${env.TWITCH_STREAM_KEY}`;
      legs.push("twitch");
    } else if (t === "youtube") {
      if (!env.YOUTUBE_STREAM_KEY) return { ok: false, reason: "no YOUTUBE_STREAM_KEY in radio/stream/.env" };
      const ingest = env.YOUTUBE_INGEST || "rtmp://a.rtmp.youtube.com/live2";
      childEnv.HISIA_RTMP_YOUTUBE = `${ingest.replace(/\/$/, "")}/${env.YOUTUBE_STREAM_KEY}`;
      legs.push("youtube");
    } else if (t === "file") {
      legs.push("file");
    } else {
      return { ok: false, reason: `unknown target ${t}` };
    }
  }
  if (!legs.length) return { ok: false, reason: "no targets" };
  if (legs.includes("file") || process.env.RECORD === "1") {
    const dir = path.join(os.homedir(), "Movies", "hisia");
    fs.mkdirSync(dir, { recursive: true });
    recordPath = path.join(dir, `hisia-${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}.mp4`);
    if (!legs.includes("file")) legs.push("file");
  }

  const myGen = ++gen;
  telemetry = { fps: null, maxGap: null, dropped: 0, frames: 0, size: null };
  const opts = {
    url: `http://127.0.0.1:${PORT}/radio/index.html?stream=1`,
    pcmUrl: `http://127.0.0.1:${PORT}/pcm`,
    width: Number(process.env.HISIA_W) || 1280, height: Number(process.env.HISIA_H) || 720,
    fps: Number(process.env.HISIA_FPS) || 20, vBitrate: Number(process.env.HISIA_VBIT) || 3000,
    legs: legs.filter((l) => l !== "file"),
    recordPath,
  };
  let proc;
  try {
    proc = spawn(process.execPath, [path.join(HERE, "capture.js"), JSON.stringify(opts)],
      { env: childEnv, stdio: ["ignore", "pipe", "pipe"] });
  } catch (e) {
    return { ok: false, reason: `spawn: ${e.message}` };
  }
  spawned.add(proc);
  proc.on("exit", () => spawned.delete(proc));
  cap = { proc, gen: myGen, targets: legs, startedAt: Date.now(), recordPath };

  let buf = "";
  const onLine = (line) => {
    if (!line) return;
    if (line.startsWith("TELEMETRY ")) {
      try { Object.assign(telemetry, JSON.parse(line.slice(10))); } catch {}
      return;
    }
    log(`capture: ${line}`);
  };
  const feed = (d) => {
    buf += d.toString();
    let i;
    while ((i = buf.indexOf("\n")) >= 0) { onLine(buf.slice(0, i).trim()); buf = buf.slice(i + 1); }
  };
  proc.stdout.on("data", feed);
  proc.stderr.on("data", (d) => log(`capture!: ${d.toString().trim().split("\n").slice(-1)[0]}`));
  proc.on("exit", (code) => {
    if (!cap || cap.gen !== myGen) { log(`stale capture exit (gen ${myGen}) ignored`); return; }
    log(`broadcast ended (capture exit ${code})`);
    cap = null;
  });

  log(`broadcast starting → ${legs.join(", ")}${recordPath ? ` (${recordPath})` : ""}`);
  return { ok: true, targets: legs, recordPath };
}

function broadcastStop() {
  if (!cap) return { ok: false, reason: "not-live" };
  gen++;                       // invalidate first — every pending handler no-ops
  const { proc } = cap;
  cap = null;
  try { proc.kill("SIGTERM"); } catch {}
  // capture.js needs a moment to let ffmpeg finalise a recording
  const killer = setTimeout(() => { try { proc.kill("SIGKILL"); } catch {} }, 8000);
  if (killer.unref) killer.unref();
  proc.on("exit", () => clearTimeout(killer));
  log("broadcast stopped");
  return { ok: true };
}

function status() {
  return {
    live: !!cap,
    legs: cap ? cap.targets : [],
    recording: !!(cap && cap.recordPath),
    broadcastUptimeS: cap ? Math.round((Date.now() - cap.startedAt) / 1000) : 0,
    serverUptimeS: Math.round((Date.now() - START_AT) / 1000),
    capture: {
      distinctFps: telemetry.fps,
      maxInterFrameGapMs: telemetry.maxGap,
      dropped: telemetry.dropped,
      frameSize: telemetry.size,
      freshFps: telemetry.freshFps,
      cfrFps: telemetry.cfrFps,
      frameKB: telemetry.frameKB,
      encoderSpeed: telemetry.ffSpeed,
    },
    player: player.stats(),
    now: player.now(),
  };
}

// ── static files (../ = the radio dir; also mounted at /radio/) ───────
const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".mp3": "audio/mpeg", ".wav": "audio/wav", ".png": "image/png",
  ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".ico": "image/x-icon",
};
function serveFile(res, file) {
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404); return res.end("not found"); }
    res.writeHead(200, {
      "Content-Type": MIME[path.extname(file).toLowerCase()] || "application/octet-stream",
      "Content-Length": st.size,
      "Cache-Control": "no-store",
    });
    fs.createReadStream(file).pipe(res);
  });
}
function safeJoin(root, rel) {
  const p = path.resolve(root, "." + path.posix.normalize("/" + rel));
  return p.startsWith(root) ? p : null;
}

function json(res, obj, code = 200) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(body);
}
function readBody(req) {
  return new Promise((resolve) => {
    let b = "";
    req.on("data", (d) => { b += d; if (b.length > 1e5) req.destroy(); });
    req.on("end", () => { try { resolve(JSON.parse(b || "{}")); } catch { resolve({}); } });
  });
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const p = u.pathname;

  if (p === "/now.json") return json(res, player.now() || { track: null });
  if (p === "/status.json") return json(res, status());

  if (p === "/skip") {
    if (req.method !== "POST") return json(res, { ok: false, reason: "POST only" }, 405);
    player.skip();
    log("skip");
    return json(res, { ok: true });
  }

  // reload the capture tab in place — a page edit never needs Stop → Start
  if (p === "/reload") {
    if (req.method !== "POST") return json(res, { ok: false, reason: "POST only" }, 405);
    if (!cap) return json(res, { ok: false, reason: "not-live" });
    try { cap.proc.kill("SIGUSR2"); } catch (e) { return json(res, { ok: false, reason: e.message }); }
    log("reload requested");
    return json(res, { ok: true });
  }

  if (p === "/broadcast") {
    if (req.method !== "POST") return json(res, { ok: false, reason: "POST only" }, 405);
    const body = await readBody(req);
    const action = String(body.action || "");
    if (action === "start") {
      const targets = Array.isArray(body.targets) && body.targets.length ? body.targets : ["twitch"];
      return json(res, broadcastStart(targets.map(String)));
    }
    if (action === "stop") return json(res, broadcastStop());
    return json(res, { ok: false, reason: "action must be start or stop" }, 400);
  }

  // the never-ending radio feed
  if (p === "/pcm") {
    res.writeHead(200, { "Content-Type": "audio/L16", "Cache-Control": "no-store" });
    player.attach(res);
    log(`pcm tap attached (${player.sinks.size} total)`);
    req.on("close", () => log(`pcm tap closed (${player.sinks.size} left)`));
    return;
  }

  if (p === "/log.json") return json(res, { lines: LOG.slice(-20) });

  if (p === "/stream/console" || p === "/stream/console.html" || p === "/console") {
    return serveFile(res, path.join(HERE, "console.html"));
  }

  // /radio/... and / both resolve inside the radio dir
  let rel = p;
  if (rel === "/") rel = "/index.html";
  if (rel.startsWith("/radio/")) rel = rel.slice("/radio".length);
  const file = safeJoin(RADIO_DIR, rel);
  if (!file) { res.writeHead(400); return res.end("bad path"); }
  // never serve the .env, whatever the path games
  if (path.basename(file) === ".env") { res.writeHead(403); return res.end("no"); }
  return serveFile(res, file);
});

process.on("SIGINT", () => { broadcastStop(); player.stop(); process.exit(0); });
process.on("SIGTERM", () => { broadcastStop(); player.stop(); process.exit(0); });
process.on("exit", () => {
  for (const p of spawned) { try { p.kill("SIGKILL"); } catch {} }
});

player.load();
player.start().then(() => {
  server.listen(PORT, "127.0.0.1", () => {
    log(`World Sound stream server on http://127.0.0.1:${PORT}`);
    log(`  page    http://127.0.0.1:${PORT}/radio/index.html`);
    log(`  console http://127.0.0.1:${PORT}/stream/console`);
  });
}).catch((e) => {
  console.error(`player failed to start: ${e.message}`);
  process.exit(1);
});
