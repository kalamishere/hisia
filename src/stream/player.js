// radio/stream/player.js — the playlist brain and the audio engine of the
// hisia.live / World Sound stream.
//
// It is the SAME rule as radio/index.html: follow the sun into evening.
// Cities are scored by how far their local clock sits from 20:00, ties inside
// a half hour are broken at random, the last three regions stand aside, one
// track per pick, and a region never repeats a track until its pool is spent.
// The page and the stream therefore behave identically; the page in puppet
// mode just displays what this file decided.
//
// Audio: every track is decoded once by ffmpeg to 48 kHz stereo s16le, held in
// memory (~23 MB per 2-minute track, two at a time), and mixed into ONE
// never-ending PCM stream on a drift-corrected wallclock. Between tracks the
// mixer runs a 2 s equal-power crossfade — the same curve the page uses in Web
// Audio — so the stream is gapless by construction, not by luck.
//
// The PCM goes to any number of attached sinks (ffmpeg's stdin, an HTTP tap on
// /pcm, a file for analysis). Sinks come and go; the clock never stops, so a
// broadcast can start and stop without the radio missing a beat.
//
"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { EventEmitter } = require("events");

const SR = 48000;
const CH = 2;
const BYTES_PER_FRAME = CH * 2;          // s16le stereo
const BLOCK_MS = 20;
const BLOCK_FRAMES = (SR * BLOCK_MS) / 1000;   // 960
const XFADE_S = 2.0;                     // track-to-track crossfade
const SKIP_XFADE_S = 0.5;                // a skip cuts faster, still not a click
const LOOKAHEAD_MS = 500;                // stay this far ahead of the wallclock
const EVENING = 20.0;                    // the target local hour
const RUN = 1;                           // tracks per region before the sun moves on
const HOLD = 4;                          // regions held out of the next pick
const EVENING_WINDOW_H = 3.5;            // any city this close to evening is fair game

// ── equal-power curves, computed once ────────────────────────────────
function xfadeGains(len) {
  const up = new Float32Array(len), down = new Float32Array(len);
  for (let i = 0; i < len; i++) {
    const x = len === 1 ? 1 : i / (len - 1);
    up[i] = Math.sin((x * Math.PI) / 2);
    down[i] = Math.cos((x * Math.PI) / 2);
  }
  return { up, down };
}

// ── local-time helpers (identical maths to the page) ─────────────────
const fmtCache = {};
function tzParts(tz, d) {
  const f = fmtCache[tz] || (fmtCache[tz] = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false,
  }));
  let h = 0, m = 0;
  for (const p of f.formatToParts(d)) {
    if (p.type === "hour") h = parseInt(p.value, 10) % 24;
    if (p.type === "minute") m = parseInt(p.value, 10);
  }
  return { h, m };
}
function localHour(tz, d) { const p = tzParts(tz, d || new Date()); return p.h + p.m / 60; }
function eveningness(tz, d) {
  const h = localHour(tz, d), diff = Math.abs(h - EVENING);
  return Math.min(diff, 24 - diff);
}
function shuffle(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// ── ffmpeg decode: any mp3 → raw 48k stereo s16le in memory ──────────
function decode(file) {
  return new Promise((resolve, reject) => {
    const p = spawn("ffmpeg", [
      "-hide_banner", "-loglevel", "error",
      "-i", file,
      "-f", "s16le", "-acodec", "pcm_s16le", "-ar", String(SR), "-ac", String(CH),
      "pipe:1",
    ], { stdio: ["ignore", "pipe", "pipe"] });
    const chunks = [];
    let err = "";
    p.stdout.on("data", (d) => chunks.push(d));
    p.stderr.on("data", (d) => { err = (err + d).slice(-400); });
    p.on("error", reject);
    p.on("close", (code) => {
      if (code !== 0) return reject(new Error(`decode ${path.basename(file)}: ${err.trim() || code}`));
      resolve(Buffer.concat(chunks));
    });
  });
}

class Player extends EventEmitter {
  // libraryPath: absolute path to radio/library.json
  constructor({ libraryPath, audioRoot, log = () => {} }) {
    super();
    this.libraryPath = libraryPath;
    this.audioRoot = audioRoot || path.dirname(libraryPath);
    this.log = log;

    this.lib = null;
    this.regions = {};
    this.poolByRegion = {};
    this.playedByRegion = {};
    this.queue = [];
    this.recent = [];

    this.sinks = new Set();
    this.cur = null;        // {track, pcm, pos}
    this.nxt = null;        // {track, pcm, pos} — decoded ahead
    this.xf = null;         // {gains, i, len}
    this.skipWanted = false;
    this.loadingNext = false;

    this.nowTrack = null;
    this.nowStartedAt = 0;
    this.nowDurationS = 0;
    this.emittedFrames = 0;
    this.startedAtMs = 0;
    this.underruns = 0;     // blocks emitted as silence because nothing was ready
    this.timer = null;
  }

  // ── library ────────────────────────────────────────────────────────
  load() {
    const data = JSON.parse(fs.readFileSync(this.libraryPath, "utf8"));
    this.lib = data;
    this.regions = data.regions || {};
    this.poolByRegion = {};
    this.playedByRegion = {};
    for (const t of data.tracks || []) {
      if (!this.regions[t.region]) continue;
      (this.poolByRegion[t.region] = this.poolByRegion[t.region] || []).push(t);
      this.playedByRegion[t.region] = this.playedByRegion[t.region] || [];
    }
    const n = Object.values(this.poolByRegion).reduce((a, p) => a + p.length, 0);
    this.log(`player: library ${n} tracks across ${Object.keys(this.poolByRegion).length} regions`);
    return this;
  }

  // closest to evening wins; half-hour ties are random; the last three
  // regions stand aside so the rotation keeps moving.
  pickRegion() {
    const all = Object.keys(this.poolByRegion).filter((k) => this.poolByRegion[k].length);
    if (!all.length) return null;
    const hold = Math.min(this.recent.length, Math.max(0, all.length - 1), HOLD);
    const skip = this.recent.slice(this.recent.length - hold);
    let cands = all.filter((k) => skip.indexOf(k) === -1);
    if (!cands.length) cands = all;
    // any city within the evening window, at random — strict "closest" looped
    // four cities for half an hour; this spreads an hour across ten
    const d = new Date(), score = {}, jitter = {};
    for (const k of cands) {
      score[k] = eveningness(this.regions[k].tz, d);
      jitter[k] = Math.random();
    }
    let near = cands.filter((k) => score[k] <= EVENING_WINDOW_H);
    // a thin side of the clock leaves too few cities in the window; take the six nearest instead
    if (near.length < 6) near = cands.slice().sort((a, b) => score[a] - score[b]).slice(0, 6);
    if (near.length) {
      // weighted toward the sunset (~19:30): the city with the sun on the horizon
      // plays about three times as often as one two hours into the night
      const w = near.map((k) => {
        let dd = Math.abs(localHour(this.regions[k].tz, d) - 19.5); dd = Math.min(dd, 24 - dd);
        return 1 / (0.5 + dd);
      });
      let pick = Math.random() * w.reduce((a, b) => a + b, 0);
      for (let i = 0; i < near.length; i++) { pick -= w[i]; if (pick <= 0) return near[i]; }
      return near[near.length - 1];
    }
    cands.sort((a, b) => (score[a] - score[b]) || (jitter[a] - jitter[b]));
    return cands[0];
  }

  refill() {
    let guard = 0;
    while (this.queue.length < 3 && guard++ < 40) {
      const iso = this.pickRegion();
      if (!iso) break;
      const pool = this.poolByRegion[iso], played = this.playedByRegion[iso];
      let fresh = pool.filter((t) => played.indexOf(t.id) === -1);
      if (!fresh.length) { played.length = 0; fresh = pool.slice(); }
      shuffle(fresh);
      for (const t of fresh.slice(0, Math.min(RUN, fresh.length))) {
        played.push(t.id);
        this.queue.push(t);
      }
      this.recent.push(iso);
      if (this.recent.length > HOLD) this.recent.shift();
    }
  }

  fileFor(track) {
    return path.resolve(this.audioRoot, track.file);
  }

  async takeNext() {
    if (!this.queue.length) this.refill();
    const track = this.queue.shift();
    if (!track) return null;
    try {
      const pcm = await decode(this.fileFor(track));
      return { track, pcm, pos: 0 };
    } catch (e) {
      this.log(`player: ${e.message} — skipping`);
      return null;
    }
  }

  async ensureNext() {
    if (this.nxt || this.loadingNext) return;
    this.loadingNext = true;
    try {
      let slot = null, tries = 0;
      while (!slot && tries++ < 5) slot = await this.takeNext();
      this.nxt = slot;
    } finally {
      this.loadingNext = false;
    }
  }

  // ── the mixer ──────────────────────────────────────────────────────
  async start() {
    if (this.timer) return this;
    if (!this.lib) this.load();
    this.refill();
    this.cur = null;
    let tries = 0;
    while (!this.cur && tries++ < 5) this.cur = await this.takeNext();
    if (!this.cur) throw new Error("player: no playable track in the library");
    this.promote(this.cur.track, 0);
    this.ensureNext();

    this.startedAtMs = Date.now();
    this.emittedFrames = 0;
    // 5 ms tick, drift-corrected: we emit whatever the wallclock says is due
    // (plus LOOKAHEAD_MS), so a late timer is repaid immediately and the
    // long-run rate is exactly 48 kHz. No second clock, no accumulating skew.
    this.timer = setInterval(() => this.tick(), 5);
    this.log("player: on air");
    return this;
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  promote(track, offsetFrames) {
    this.nowTrack = track;
    this.nowStartedAt = Date.now() - Math.round((offsetFrames / SR) * 1000);
    this.log(`player: ▶ ${track.id} ${track.artist} — ${track.title} (${track.seed_mode || track.seed_source || "?"} @ ${track.vibe})`);
    this.emit("track", this.now());
  }

  tick() {
    const dueMs = (Date.now() - this.startedAtMs) + LOOKAHEAD_MS;
    const dueFrames = Math.floor((dueMs / 1000) * SR);
    let budget = 40;   // never emit more than 0.8 s in one tick
    while (this.emittedFrames + BLOCK_FRAMES <= dueFrames && budget-- > 0) {
      this.emit_block();
    }
  }

  emit_block() {
    const out = Buffer.alloc(BLOCK_FRAMES * BYTES_PER_FRAME);
    let wroteAudio = false;

    for (let f = 0; f < BLOCK_FRAMES; f++) {
      // start a crossfade when the tail is near, or when a skip is asked for
      if (!this.xf && this.cur) {
        const left = (this.cur.pcm.length / BYTES_PER_FRAME) - this.cur.pos;
        const wantSkip = this.skipWanted;
        const wantTail = left <= XFADE_S * SR;
        if ((wantSkip || wantTail) && this.nxt) {
          const secs = wantSkip ? SKIP_XFADE_S : XFADE_S;
          const len = Math.min(Math.round(secs * SR), Math.max(1, left),
            this.nxt.pcm.length / BYTES_PER_FRAME);
          this.xf = { ...xfadeGains(len), i: 0, len };
          this.skipWanted = false;
          this.promote(this.nxt.track, 0);
        } else if (wantSkip && !this.nxt) {
          // next isn't decoded yet; hold the skip until it is
        }
      }

      let l = 0, r = 0;
      if (this.cur && this.cur.pos * BYTES_PER_FRAME + 3 < this.cur.pcm.length) {
        const o = this.cur.pos * BYTES_PER_FRAME;
        const g = this.xf ? this.xf.down[Math.min(this.xf.i, this.xf.len - 1)] : 1;
        l += this.cur.pcm.readInt16LE(o) * g;
        r += this.cur.pcm.readInt16LE(o + 2) * g;
        this.cur.pos++;
        wroteAudio = true;
      }
      if (this.xf && this.nxt && this.nxt.pos * BYTES_PER_FRAME + 3 < this.nxt.pcm.length) {
        const o = this.nxt.pos * BYTES_PER_FRAME;
        const g = this.xf.up[Math.min(this.xf.i, this.xf.len - 1)];
        l += this.nxt.pcm.readInt16LE(o) * g;
        r += this.nxt.pcm.readInt16LE(o + 2) * g;
        this.nxt.pos++;
        wroteAudio = true;
      }

      if (this.xf) {
        this.xf.i++;
        if (this.xf.i >= this.xf.len) {
          // the incoming track becomes the current one; decode the one after
          this.cur = this.nxt;
          this.nxt = null;
          this.xf = null;
          if (this.cur) this.nowDurationS = this.cur.pcm.length / BYTES_PER_FRAME / SR;
          this.ensureNext();
        }
      } else if (this.cur && this.cur.pos * BYTES_PER_FRAME >= this.cur.pcm.length) {
        // ran off the end without a next ready (decode was slow): go silent
        // rather than click, and pick up as soon as the decode lands.
        this.cur = null;
        this.ensureNext();
      }

      const o = f * BYTES_PER_FRAME;
      out.writeInt16LE(Math.max(-32768, Math.min(32767, l | 0)), o);
      out.writeInt16LE(Math.max(-32768, Math.min(32767, r | 0)), o + 2);
    }

    if (!wroteAudio) {
      this.underruns++;
      // nothing playing: try to install whatever finished decoding
      if (!this.cur && this.nxt) {
        this.cur = this.nxt; this.nxt = null;
        this.promote(this.cur.track, 0);
        this.nowDurationS = this.cur.pcm.length / BYTES_PER_FRAME / SR;
        this.ensureNext();
      }
    }

    this.emittedFrames += BLOCK_FRAMES;
    for (const s of this.sinks) {
      if (!s.writable || s.destroyed) { this.sinks.delete(s); continue; }
      // a stuck reader must never stall the radio: drop instead of buffering
      if (s.writableLength > 4 * 1024 * 1024) continue;
      try { s.write(out); } catch { this.sinks.delete(s); }
    }
  }

  // ── public surface ─────────────────────────────────────────────────
  attach(stream) {
    this.sinks.add(stream);
    const drop = () => this.sinks.delete(stream);
    stream.on("close", drop);
    stream.on("error", drop);
    return () => drop();
  }

  skip() {
    if (!this.nxt) { this.ensureNext(); }
    this.skipWanted = true;
    return true;
  }

  now() {
    const t = this.nowTrack;
    if (!t) return null;
    const region = this.regions[t.region] || null;
    const nextT = this.nxt ? this.nxt.track : (this.queue[0] || null);
    const durationS = this.cur && this.cur.track === t
      ? this.cur.pcm.length / BYTES_PER_FRAME / SR
      : (this.nxt && this.nxt.track === t
        ? this.nxt.pcm.length / BYTES_PER_FRAME / SR
        : (t.duration_s || 0));
    return {
      track: t,
      region: t.region,
      city: region ? region.city : null,
      startedAt: this.nowStartedAt,
      durationS: Math.round(durationS * 100) / 100,
      elapsedS: Math.round((Date.now() - this.nowStartedAt) / 10) / 100,
      next: nextT ? {
        track: nextT,
        region: nextT.region,
        city: (this.regions[nextT.region] || {}).city || null,
      } : null,
      serverTime: Date.now(),
    };
  }

  stats() {
    return {
      sinks: this.sinks.size,
      emittedS: Math.round(this.emittedFrames / SR),
      underrunBlocks: this.underruns,
      queued: this.queue.length,
      nextDecoded: !!this.nxt,
    };
  }
}

module.exports = { Player, SR, CH, BLOCK_FRAMES, XFADE_S, decode, eveningness, localHour };
