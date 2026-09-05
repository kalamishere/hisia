#!/usr/bin/env node
// radio/stream/capture.js — the video leg. A headless Chrome renders the
// World Sound page in puppet mode; we pull frames off it on our own clock and
// write them through a fifo into one ffmpeg, which muxes them with the radio's
// PCM and tees the result to Twitch, YouTube and/or a local mp4.
//
// Everything here is a lesson from pj-battle's broadcast work, carried over:
//
//   · The headless viewport is PINNED with CDP Emulation.setDeviceMetricsOverride.
//     --window-size / --force-device-scale-factor are quietly ignored in
//     headless=new (measured there: 960x540 flags → a 960x453 viewport that
//     cropped the frame). We also verify the first JPEG really is 1920x1080.
//   · Frames are PULLED (Page.captureScreenshot) on a drift-corrected clock,
//     not pushed by Page.startScreencast. Push delivery arrives in bursts and
//     droughts; pulling gives even spacing and the lowest encode cost.
//   · Sampling runs ~30% faster than the output rate and a drift-corrected CFR
//     pump writes exactly `fps` frames a second into the fifo, newest wins.
//     (pj-battle preferred write-through with -use_wallclock_as_timestamps.
//     Measured here, that flag put the video ~1.8e9 s ahead of the PCM input
//     and ffmpeg read the fifo in dribbles; putting the audio on wallclock too
//     balanced the reads and destroyed the AAC track. One CFR clock in this
//     nearly-idle process is what actually holds 20 fps — see buildArgs and
//     startPumpIfReady for both traps, in full.)
//   · Audio NEVER comes from the browser (--mute-audio). It comes from
//     player.js over /pcm, which is the same feed the page would have played.
//   · This process owns Chrome from the moment it spawns and takes it down on
//     every exit path, including a vanished parent.
//
// Usage: node capture.js '<json opts>'
//   { url, pcmUrl, width, height, fps, vBitrate, legs:["twitch"], recordPath }
// RTMP urls (which carry the stream keys) arrive in the environment as
// HISIA_RTMP_TWITCH / HISIA_RTMP_YOUTUBE and are never printed.
//
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const { spawn, spawnSync } = require("child_process");

const o = JSON.parse(process.argv[2] || "{}");
const URL_ = o.url;
const PCM_URL = o.pcmUrl;
const W = o.width || 1920, H = o.height || 1080;
const FPS = o.fps || 20;
const VBIT = o.vBitrate || 4500;
const QUALITY = Number(process.env.HISIA_JPEG_QUALITY) || 70;
const WARMUP_MS = 25000;

const say = (s) => { try { process.stdout.write(String(s) + "\n"); } catch {} };
const tele = (obj) => say("TELEMETRY " + JSON.stringify(obj));

const CHROME_PATHS = [
  process.env.HISIA_CHROME,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
].filter(Boolean);
function findChrome() {
  for (const p of CHROME_PATHS) { try { fs.accessSync(p, fs.constants.X_OK); return p; } catch {} }
  return null;
}

// JPEG SOFn header → real frame size. The one honest check that the viewport
// override landed; flags alone have lied before.
function jpegSize(buf) {
  let i = 2;
  while (i + 9 < buf.length) {
    if (buf[i] !== 0xff) { i++; continue; }
    const m = buf[i + 1];
    if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
      return { height: buf.readUInt16BE(i + 5), width: buf.readUInt16BE(i + 7) };
    }
    if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) { i += 2; continue; }
    i += 2 + buf.readUInt16BE(i + 2);
  }
  return null;
}

function getJson(port, pathname) {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: "127.0.0.1", port, path: pathname, timeout: 4000 }, (res) => {
      let b = ""; res.on("data", (d) => { b += d; });
      res.on("end", () => { try { resolve(JSON.parse(b)); } catch (e) { reject(e); } });
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("devtools timeout")); });
  });
}

// ── process-wide teardown ────────────────────────────────────────────
let chrome = null, ff = null, fifoPath = null, profileDir = null, dying = false;
let ws = null;                      // CDP socket — module-scope so SIGUSR2 can reach it
let ffFps = null, ffSpeed = null;   // ffmpeg's own -stats numbers
function chromeGoneThenExit(code) {
  try { if (chrome) chrome.kill("SIGKILL"); } catch {}
  try { if (fifoPath) fs.unlinkSync(fifoPath); } catch {}
  try { if (profileDir) fs.rmSync(profileDir, { recursive: true, force: true }); } catch {}
  setTimeout(() => process.exit(code), 150);
}
function die(why, code = 0) {
  if (dying) return;
  dying = true;
  say(`exiting (${why})`);
  try { if (ff) { ff.stdin && ff.stdin.end(); ff.kill("SIGTERM"); } } catch {}
  try { if (chrome) chrome.kill("SIGTERM"); } catch {}
  // ffmpeg finalises the recording on SIGTERM; wait for it before escalating.
  if (ff) ff.on("exit", () => { chromeGoneThenExit(code); });
  setTimeout(() => {
    try { if (chrome) chrome.kill("SIGKILL"); } catch {}
    try { if (ff) ff.kill("SIGKILL"); } catch {}
    try { if (fifoPath) fs.unlinkSync(fifoPath); } catch {}
    try { if (profileDir) fs.rmSync(profileDir, { recursive: true, force: true }); } catch {}
    process.exit(code);
  }, 5000);
  // Hard floor. Both of these timers are deliberately NOT unref'd. Measured
  // on the Space copy: kill the server before the first frame has arrived and
  // ffmpeg has never been spawned, so the ff-exit path above does not exist —
  // with unref'd timers this process then sat there for minutes holding
  // Chrome. A ref'd timer always fires.
  setTimeout(() => {
    try { process.kill(process.pid, "SIGKILL"); } catch {}
    process.exit(code);
  }, 8000);
}
process.on("SIGTERM", () => die("sigterm"));
process.on("SIGINT", () => die("sigint"));
// A page edit never needs Stop → Start: SIGUSR2 reloads the tab over CDP
// without touching ffmpeg or the fifo. One stale frame during the reload is
// fine; the pump just keeps writing whatever `latestFrame` last was.
let reloadMsgId = 900000000;
process.on("SIGUSR2", () => {
  if (!ws || ws.readyState !== 1 /* OPEN */) {
    say("reload: no CDP connection yet, skipped");
    return;
  }
  say("reloading page (SIGUSR2)");
  try {
    ws.send(JSON.stringify({ id: ++reloadMsgId, method: "Page.reload", params: { ignoreCache: false } }));
  } catch (e) { say(`reload failed: ${e.message}`); }
});
process.on("exit", () => {
  try { if (chrome) chrome.kill("SIGKILL"); } catch {}
  try { if (ff) ff.kill("SIGKILL"); } catch {}
  try { if (fifoPath) fs.unlinkSync(fifoPath); } catch {}
});
// parent-death watchdog: a SIGKILLed server must not leave Chrome behind
const parentPid = process.ppid;   // reparenting = orphaned; ppid===1 is wrong in a container where the server is pid 1
const orphanWatch = setInterval(() => { if (process.ppid !== parentPid) die("parent gone"); }, 5000);
if (orphanWatch.unref) orphanWatch.unref();

// ── ffmpeg ───────────────────────────────────────────────────────────
function buildArgs() {
  const args = [
    "-hide_banner", "-loglevel", "warning", "-stats",
    // Video: one JPEG per output slot, written by the CFR pump below at
    // exactly FPS, so the demuxer's own -framerate clock IS real time and both
    // inputs start at zero on the same timeline. The alternative — wallclock
    // timestamps on the video — put it ~1.8e9 s "ahead" of the audio, and
    // ffmpeg then read the fifo in dribbles (measured: the fifo pinned at its
    // cap, ~15 captured frames a second thrown away). Giving the audio
    // wallclock stamps too fixed the reads and destroyed the AAC track: raw
    // PCM arrives in big chunks, so its timestamps stop advancing by sample
    // count and the encoder emitted a fraction of a second.
    "-thread_queue_size", "512",
    "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", String(FPS), "-i", fifoPath,
    // Audio: the radio's own PCM, never the browser's. Its clock is the sample
    // count, which player.js paces against the wallclock — so the two inputs
    // stay together for as long as the broadcast runs.
    "-thread_queue_size", "512",
    "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", PCM_URL,
    "-filter_complex",
    `[0:v]scale=${W}:${H}:force_original_aspect_ratio=decrease,` +
    `pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x0a1020,format=yuv420p,setsar=1[vout]`,   // setsar: a JPEG density tag must never become a non-square pixel aspect on air
    // The audio is mapped straight through: any filter on it (even asetpts)
    // made ffmpeg read the video fifo in dribbles again.
    "-map", "[vout]", "-map", "1:a",
    // Apple's hardware encoder costs a fraction of x264's CPU; software x264 on a
    // loaded laptop ran at 0.92x real time, which the viewer sees as buffering
    // and as audio drifting behind the picture. HISIA_VCODEC=x264 forces software.
    ...(process.platform === "darwin" && process.env.HISIA_VCODEC !== "x264"
      ? ["-c:v", "h264_videotoolbox", "-realtime", "1", "-profile:v", "high"]
      : ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high"]),
    "-b:v", `${VBIT}k`, "-maxrate", `${VBIT}k`, "-bufsize", `${VBIT * 2}k`,
    "-g", String(FPS * 2), "-r", String(FPS), "-fps_mode", "cfr", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
  ];

  const rtmp = [];
  if ((o.legs || []).includes("twitch") && process.env.HISIA_RTMP_TWITCH) rtmp.push(process.env.HISIA_RTMP_TWITCH);
  if ((o.legs || []).includes("youtube") && process.env.HISIA_RTMP_YOUTUBE) rtmp.push(process.env.HISIA_RTMP_YOUTUBE);

  if (!rtmp.length && o.recordPath) {
    args.push("-movflags", "+frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", o.recordPath);
  } else if (rtmp.length === 1 && !o.recordPath) {
    args.push("-f", "flv", rtmp[0]);
  } else {
    // Twitch is leg 0 — the only one allowed to kill the run. Everything
    // after it (YouTube, the local recording) is onfail=ignore.
    const legs = rtmp.map((u, i) => `[f=flv${i ? ":onfail=ignore" : ""}]${u}`);
    if (o.recordPath) legs.push(`[f=mp4:onfail=ignore:movflags=+frag_keyframe+empty_moov+default_base_moof]${o.recordPath}`);
    args.push("-f", "tee", legs.join("|"));
  }
  return args;
}

function startFfmpeg() {
  const args = buildArgs();
  ff = spawn("ffmpeg", args, { stdio: ["ignore", "ignore", "pipe"] });
  let tail = "";
  ff.stderr.on("data", (d) => {
    const s = d.toString();
    tail = (tail + s).slice(-800);
    // -stats writes "frame= … fps= … speed= …x" on a carriage return; keep the
    // last one as telemetry (speed < 1 means the encoder is behind realtime,
    // which shows up upstream as a backed-up fifo and dropped frames).
    const m = /fps=\s*([\d.]+).*?speed=\s*([\d.]+)x/s.exec(s);
    if (m) { ffFps = Number(m[1]); ffSpeed = Number(m[2]); }
    const line = s.trim().split("\n").pop();
    // never let a stream key reach the log: RTMP URLs carry it as the last path segment
    if (line && !/frame=/.test(line)) say(`ffmpeg: ${line.replace(/(rtmps?:\/\/[^\s\/]+\/[^\s\/]+\/)[^\s'"]+/g, "$1<key>")}`);
  });
  ff.on("error", (e) => die(`ffmpeg spawn: ${e.message}`, 1));
  ff.on("close", (code) => die(`ffmpeg exited ${code}: ${tail.trim().split("\n").pop() || ""}`, code ? 1 : 0));
  const names = [
    ...(o.legs || []),
    ...(o.recordPath ? ["file"] : []),
  ];
  say(`ffmpeg up: ${W}x${H}@${FPS} ${VBIT}k x264 veryfast + aac 160k → ${names.join(", ") || "nowhere"}`);
}

// ── Chrome + CDP ─────────────────────────────────────────────────────
async function main() {
  if (!URL_) return die("no url", 1);
  const chromePath = findChrome();
  if (!chromePath) return die("no headless-capable Chrome found (set HISIA_CHROME)", 1);

  fifoPath = path.join(os.tmpdir(), `hisia-fifo-${process.pid}-${Date.now()}`);
  if (spawnSync("mkfifo", [fifoPath]).status !== 0) return die("mkfifo failed", 1);

  profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "hisia-capture-"));
  chrome = spawn(chromePath, [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${profileDir}`,
    `--window-size=${W},${H}`,
    "--no-first-run", "--no-default-browser-check",
    "--mute-audio", "--hide-scrollbars",
    "--disable-extensions", "--disable-background-networking",
    // headless treats the tab as backgroundable and batches frame production;
    // these are the anti-throttle flags that made the pj-battle capture even.
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    URL_,
  ], { stdio: ["ignore", "ignore", "pipe"] });
  chrome.on("error", (e) => die(`chrome spawn: ${e.message}`, 1));
  chrome.on("close", (c) => die(`chrome exited (${c})`, 1));

  const warmup = setTimeout(() => die("no frame within 25s warmup", 1), WARMUP_MS);

  const port = await new Promise((resolve, reject) => {
    let buf = "";
    const to = setTimeout(() => reject(new Error("devtools announce timeout")), 15000);
    chrome.stderr.on("data", (d) => {
      buf += d.toString();
      const m = /DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)\//.exec(buf);
      if (m) { clearTimeout(to); resolve(Number(m[1])); }
    });
  }).catch((e) => { die(`chrome: ${e.message}`, 1); return null; });
  if (!port) return;

  let pageWs = null;
  for (let i = 0; i < 24 && !pageWs; i++) {
    try {
      const list = await getJson(port, "/json/list");
      const pg = list.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (pg) pageWs = pg.webSocketDebuggerUrl;
    } catch {}
    if (!pageWs) await new Promise((r) => setTimeout(r, 250));
  }
  if (!pageWs) return die("no page target on devtools", 1);

  ws = new WebSocket(pageWs);                // node 22 global; no ws dependency
  let msgId = 0;
  const pending = new Map();
  const send = (method, params) => {
    try { ws.send(JSON.stringify({ id: ++msgId, method, params: params || {} })); } catch {}
  };

  await new Promise((resolve, reject) => {
    const to = setTimeout(() => reject(new Error("cdp connect timeout")), 8000);
    ws.addEventListener("open", () => { clearTimeout(to); resolve(); }, { once: true });
    ws.addEventListener("error", () => { clearTimeout(to); reject(new Error("cdp socket error")); }, { once: true });
  }).catch((e) => { die(e.message, 1); return null; });
  if (dying) return;

  ws.addEventListener("close", () => die("cdp socket closed", 1));
  ws.addEventListener("message", (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (m.id && pending.has(m.id)) {
      const cb = pending.get(m.id); pending.delete(m.id);
      cb(m.result, m.error);
    }
  });

  send("Page.enable");
  // PIN the viewport. This — not the flags — is what makes the frame 1920x1080.
  send("Emulation.setDeviceMetricsOverride", {
    width: W, height: H, deviceScaleFactor: 1, mobile: false,
  });

  // ── fifo write-through ─────────────────────────────────────────────
  const sink = fs.createWriteStream(fifoPath);   // open() parks until ffmpeg reads
  let sinkOpen = false;
  let latestFrame = null, lastWritten = null, pump = null, pumpT0 = 0, sent = 0;
  let dupWrites = 0, dropped = 0, maxTick = 0, lastTick = 0, bufMax = 0, writes = 0;
  sink.on("open", () => { sinkOpen = true; startPumpIfReady(); });
  sink.on("error", (e) => die(`fifo: ${e.code || e.message}`, 1));

  // The CFR pump: exactly FPS writes a second, each carrying the newest frame
  // Chrome has produced. It runs in this nearly-idle process (pj-battle's
  // lesson: the same loop inside a busy server arrived 30-500 ms late and every
  // platform showed half-second judder), and it is drift-corrected — "how many
  // frames are due by now" rather than "one per tick", so a late tick is repaid
  // immediately instead of accumulating.
  function startPumpIfReady() {
    if (pump || !sinkOpen || !latestFrame) return;
    pumpT0 = Date.now();
    lastTick = pumpT0;
    pump = setInterval(() => {
      const t = Date.now();
      if (t - lastTick > maxTick) maxTick = t - lastTick;
      lastTick = t;
      if (!latestFrame || !sink.writable) return;
      if (sink.writableLength > bufMax) bufMax = sink.writableLength;
      // Keep the fifo nearly EMPTY, not merely bounded, and REBASE the clock
      // when it is not. A generous cap is a trap: the queue fills during
      // ffmpeg's startup and then stays full for ever, because the pump
      // refills it at exactly the rate ffmpeg drains it — measured as a
      // standing 4 MB, the picture running ~5 s behind the sound. Skipping a
      // slot without rebasing is the other trap: the owed frames come back as
      // a catch-up burst of the SAME frame (measured: 13 of every 20 writes
      // were repeats while fresh frames waited). So when the queue is deep,
      // skip the slot and start counting again from now.
      if (sink.writableLength > 512 * 1024) { dropped++; pumpT0 = t; sent = 0; return; }
      const due = Math.floor(((t - pumpT0) / 1000) * FPS);
      let n = Math.min(3, due - sent);          // cap the catch-up burst
      while (n-- > 0) {
        if (latestFrame === lastWritten) dupWrites++;   // honest "stale frame on air"
        sink.write(latestFrame);
        lastWritten = latestFrame;
        sent++; writes++;
      }
    }, Math.max(8, Math.floor(1000 / FPS / 2)));
  }

  // ── telemetry ──────────────────────────────────────────────────────
  let arrivals = 0, distinct = 0, maxGap = 0, lastArr = 0;
  let bytes = 0;
  let prevLen = -1, prevSig = 0, frameSize = null, checked = false;
  function changed(buf) {
    let sig = 0;
    const step = Math.max(1, buf.length >> 3);
    for (let i = 0; i < buf.length; i += step) sig = (sig * 31 + buf[i]) | 0;
    const c = buf.length !== prevLen || sig !== prevSig;
    prevLen = buf.length; prevSig = sig;
    return c;
  }
  const statTimer = setInterval(() => {
    const kb = arrivals ? Math.round(bytes / arrivals / 1024) : 0;
    tele({
      fps: Math.round((distinct / 15) * 10) / 10,
      arrivalFps: Math.round((arrivals / 15) * 10) / 10,
      maxGap, dropped, dupWrites, size: frameSize, frameKB: kb, ffFps, ffSpeed,
      // what actually reaches the encoder: CFR slots minus repeated content
      freshFps: Math.round(((writes - dupWrites) / 15) * 10) / 10,
      cfrFps: Math.round((writes / 15) * 10) / 10,
    });
    say(`capture: distinct ${(distinct / 15).toFixed(1)}fps, arrivals ${(arrivals / 15).toFixed(1)}fps, ` +
      `maxIFG ${maxGap}ms, dupWrites ${dupWrites}, dropped ${dropped}, ${kb}KB/frame, ` +
      `maxTick ${maxTick}ms, writes ${(writes / 15).toFixed(1)}/s, bufMax ${(bufMax / 1048576).toFixed(1)}MB, ` +
      `ffmpeg ${ffFps}fps speed ${ffSpeed}x`);
    arrivals = 0; distinct = 0; maxGap = 0; bytes = 0; dupWrites = 0; maxTick = 0; writes = 0; bufMax = 0;
  }, 15000);
  if (statTimer.unref) statTimer.unref();

  // ── pull sampling on a drift-corrected clock ───────────────────────
  let inFlight = 0, stopped = false;
  // Sample ~30% faster than the output rate so every output slot has a frame
  // that is at most one sample old, even through a screenshot drought (Chrome
  // stalls to 400-900 ms under other load on this box). Surplus frames are
  // simply overwritten — latest-wins costs nothing, because the pump, not the
  // sampler, decides what goes on air.
  const interval = Math.max(12, 1000 / (FPS * 1.3));
  let lastPulse = 0, lateEma = 0;
  const scheduleNext = () => { if (!stopped) setTimeout(pulse, Math.max(5, interval - lateEma)); };

  function onFrame(buf) {
    const t = Date.now();
    if (lastArr) { const g = t - lastArr; if (g > maxGap) maxGap = g; }
    lastArr = t;
    arrivals++;
    if (changed(buf)) distinct++;
    if (!checked) {
      checked = true;
      const s = jpegSize(buf);
      frameSize = s ? `${s.width}x${s.height}` : "unknown";
      say(`capture: first frame ${frameSize}` + (s && (s.width !== W || s.height !== H)
        ? `  ** WRONG SIZE, expected ${W}x${H} **` : ` (viewport pinned via CDP)`));
      clearTimeout(warmup);
      startFfmpeg();
    }
    bytes += buf.length;
    latestFrame = buf;
    startPumpIfReady();
  }

  function pulse() {
    if (stopped || dying) return;
    const t = Date.now();
    if (lastPulse) lateEma = Math.min(20, Math.max(0, lateEma + ((t - lastPulse) - interval) * 0.25));
    lastPulse = t;
    // Three in flight hides protocol + JPEG-encode latency (measured p95 of a
    // 1080p screenshot ~110ms, well over the 50ms pull interval); with two the
    // pull rate settled at ~19.0/s instead of 20. More than three only queues
    // inside Chrome and makes the frames older, not more numerous.
    if (inFlight >= 3) return scheduleNext();
    inFlight++;
    const id = ++msgId;
    const guard = setTimeout(() => { pending.delete(id); inFlight--; }, interval * 6);
    pending.set(id, (result, error) => {
      clearTimeout(guard);
      inFlight--;
      if (error || !result || !result.data) return;
      try { onFrame(Buffer.from(result.data, "base64")); } catch {}
    });
    try {
      ws.send(JSON.stringify({ id, method: "Page.captureScreenshot", params: {
        format: "jpeg", quality: QUALITY, optimizeForSpeed: true,
      } }));
    } catch { clearTimeout(guard); pending.delete(id); inFlight--; }
    scheduleNext();
  }
  ws.addEventListener("close", () => { stopped = true; });

  say(`capture: pull-sampling ${URL_} at ${W}x${H} q${QUALITY} ${FPS}fps (drift-compensated)`);
  pulse();
}

main().catch((e) => die(`capture: ${e && e.message || e}`, 1));
