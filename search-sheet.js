/* search-sheet.js: prompt search shared by search.html and the radio page.
   One file: the index loader, the ranking, the chips and the result card (window.HisiaSearch),
   and, on the radio page only, the sheet that rises over the sky (opened by #btnSearch or "/").
   The sheet never owns audio: "Play on the radio" calls window.hisiaRadio.play(file), the
   radio's own player with its usual crossfade. search-index.json is fetched once, on first use. */
(function () {
  'use strict';
  var HS = window.HisiaSearch = {};

  // ---------- ranking (place > genre > prompt > mood; prefix match both ways at 4+ letters) ----------
  var SYN = { melancholic: 'emotional ballad moody dark tender soft', melancholy: 'emotional ballad moody dark tender soft', sad: 'emotional ballad moody dark tender',
    wistful: 'emotional ballad moody tender', chill: 'relaxing meditative mellow laid soft', calm: 'relaxing meditative mellow soft',
    mellow: 'mellow relaxing laid soft', party: 'energetic upbeat club dance festive', hype: 'energetic upbeat', sunny: 'summer sunny bright happy',
    romance: 'romantic love', night: 'night nocturnal dark late', dreamy: 'dreamy ethereal atmospheric pads' };
  function norm(s) { return (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function words(s) { return norm(s).split(/[^a-z0-9]+/).filter(Boolean); }
  function same(a, b) {
    if (a === b) return true;
    if (a.length < 4 || b.length < 4) return false;
    if (a.indexOf(b) === 0 || b.indexOf(a) === 0) return true;
    var n = 0, m = Math.min(a.length, b.length); while (n < m && a[n] === b[n]) n++;
    return n >= 6 && n >= m - 2;
  }
  function hit(qw, list) { for (var i = 0; i < list.length; i++) if (same(qw, list[i])) return true; return false; }
  function synHit(qw, list) { return (SYN[qw] || '').split(' ').some(function (a) { return a && hit(a, list); }); }
  function score(g, qws) {
    var total = 0, matched = 0;
    qws.forEach(function (w) {
      var s = hit(w, g._place) ? 8 : hit(w, g._genre) ? 4 : hit(w, g._prompt) ? 2 : hit(w, g._feel) ? 1 : (synHit(w, g._prompt) || synHit(w, g._feel)) ? 1 : 0;
      if (s) { matched++; total += s; }
    });
    if (!matched) return 0;
    return total + (matched === qws.length && qws.length > 1 ? 10 : 0);
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function mark(text, qws) {
    if (!qws.length) return esc(text);
    return esc(text).replace(/[A-Za-zÀ-ɏ0-9-]+/g, function (w) {
      var n = norm(w);
      return qws.some(function (qw) { return same(n, qw) || (SYN[qw] || '').split(' ').some(function (a) { return a && same(n, a); }); }) ? '<mark>' + w + '</mark>' : w;
    });
  }
  function excerpt(p) { return p.length <= 160 ? p : p.slice(0, 150).replace(/\s+\S*$/, '') + '…'; }

  // ---------- chips: tempo band, key, texture and feel words mined from the prompt text ----------
  var FACETS = [['tempo', function (g) { return g.o ? [g.o] : []; }], ['key', function (g) { return g.m ? [g.m] : []; }],
    ['texture', function (g) { return g.x; }], ['feel', function (g) { return g.e; }]];
  function chipKey(f, v) { return f + ':' + v; }
  function facetOf(g, key) {
    var i = key.indexOf(':'), f = key.slice(0, i), v = key.slice(i + 1);
    for (var j = 0; j < FACETS.length; j++) if (FACETS[j][0] === f) return FACETS[j][1](g).indexOf(v) >= 0;
    return false;
  }
  function chipSets(idx) {
    return FACETS.map(function (F) {
      var c = {}; idx.forEach(function (g) { F[1](g).forEach(function (v) { c[v] = (c[v] || 0) + 1; }); });
      var vals = Object.keys(c).filter(function (v) { return c[v] >= 2 && (F[0] === 'tempo' || F[0] === 'key' || c[v] <= idx.length * 0.5); })
        .sort(function (a, b) { return F[0] === 'tempo' ? ['slow', 'mid', 'fast'].indexOf(a) - ['slow', 'mid', 'fast'].indexOf(b) : c[b] - c[a]; });
      return [F[0], vals.slice(0, F[0] === 'texture' ? 12 : 10), c];
    });
  }
  function chipBtn(key, label, n, on) {
    return '<button class="chip" type="button" data-chip="' + esc(key) + '" aria-pressed="' + (on ? 'true' : 'false') + '">' + esc(label) + (n ? '<span class="n">' + n + '</span>' : '') + '</button>';
  }
  // returns {row, grid}: one scrolling row in thumb reach, and the full grid that opens from it
  function chipsHTML(sets, ON, open) {
    var row = [];
    Object.keys(ON).forEach(function (k) { row.push(chipBtn(k, k.split(':')[1], 0, true)); });
    sets.forEach(function (S) { S[1].slice(0, 3 + (S[0] === 'texture' ? 1 : 0)).forEach(function (v) { var k = chipKey(S[0], v); if (!ON[k]) row.push(chipBtn(k, v, 0, false)); }); });
    row.push('<button class="chip more" type="button" data-more="1">' + (open ? 'fewer' : 'more sounds') + '</button>');
    return { row: row.join(''), grid: sets.map(function (S) {
      return '<span class="k">' + S[0] + '</span>' + S[1].map(function (v) { var k = chipKey(S[0], v); return chipBtn(k, v, S[2][v], !!ON[k]); }).join('');
    }).join('') };
  }

  // ---------- the card (one component for search.html and the sheet) ----------
  // o.play: label of the Play button; o.file: file the radio is playing now (highlights its take)
  function cardHTML(g, qws, i, o) {
    o = o || {};
    var takes = g.t.map(function (t) {
      return '<li data-file="' + esc(t[0]) + '" data-title="' + esc(t[1]) + '" data-artist="' + esc(t[2]) + '"' + (o.file === t[0] ? ' class="playing"' : '') + '><b>' + esc(t[1]) + '</b> · ' + esc(t[2]) + '</li>';
    }).join('');
    var where = g.c + (g.n && g.n !== g.c ? ', ' + g.n : '');
    return '<section class="card" id="' + esc(o.idPrefix || '') + esc(g.id) + '" data-city="' + esc(where) + '" data-i="' + i + '">'
      + '<h2 class="city">' + mark(g.c, qws) + (g.n && g.n !== g.c ? '<i>' + mark(g.n, qws) + '</i>' : '') + '</h2>'
      + '<div class="meta">' + (g.g ? '<span class="g">' + mark(g.g, qws) + '</span>' : '') + (g.b ? '<span>' + g.b + ' BPM</span>' : '')
      + (g.m ? '<span>' + esc(g.m) + '</span>' : '') + (g.wl ? '<span>week of ' + esc(g.wl) + '</span>' : '') + '</div>'
      + '<p class="prompt">' + mark(excerpt(g.p), qws) + '</p>'
      + '<div class="acts"><button class="btn cue" type="button" aria-pressed="false">' + esc(o.play || 'Play') + '</button>'
      + '<button class="btn copy" type="button">Copy prompt</button>'
      + (g.p.length > 160 ? '<button class="btn ghost more" type="button">Full prompt</button>' : '') + '</div>'
      + '<ul>' + takes + '</ul></section>';
  }
  function copyText(g) { return g.p + '\n— published prompt, ' + g.c + (g.wl ? ', chart week of ' + g.wl : '') + '. via hisia.live/search.html#' + g.id + ', CC BY 4.0'; }
  // handles the buttons every card has (Copy, Full prompt); returns true when it took the click
  function cardButton(b, g, text) {
    if (b.classList.contains('more')) { b.closest('section.card').querySelector('.prompt').innerHTML = mark(g.p, words(text)); b.remove(); return true; }
    if (b.classList.contains('copy')) {
      var done = function () { b.textContent = 'Copied'; b.classList.add('done'); setTimeout(function () { b.textContent = 'Copy prompt'; b.classList.remove('done'); }, 1600); };
      if (navigator.clipboard) navigator.clipboard.writeText(copyText(g)).then(done, function () { b.textContent = 'Copy failed'; });
      return true;
    }
    return false;
  }
  function rank(idx, text, ON) {
    var qws = words(text), keys = Object.keys(ON || {});
    var shown = idx.filter(function (g) { return keys.every(function (k) { return facetOf(g, k); }); });
    if (qws.length) {
      shown = shown.map(function (g) { return [score(g, qws), g]; }).filter(function (x) { return x[0] > 0; })
        .sort(function (a, b) { return b[0] - a[0] || (a[1].w < b[1].w ? 1 : a[1].w > b[1].w ? -1 : 0); })
        .map(function (x) { return x[1]; });
    }
    return { shown: shown, qws: qws, keys: keys, takes: shown.reduce(function (n, g) { return n + g.t.length; }, 0) };
  }
  function countText(r) {
    return r.shown.length ? (r.qws.length || r.keys.length ? '' : 'Newest first · ') + r.shown.length + (r.shown.length === 1 ? ' prompt, ' : ' prompts, ') + r.takes + ' tracks' : '';
  }

  var cache = {};
  function load(url) {
    if (cache[url]) return cache[url];
    return cache[url] = fetch(url).then(function (r) { return r.json(); }).then(function (d) {
      var idx = d.prompts;
      idx.forEach(function (g) {
        g._place = words(g.c + ' ' + g.n + ' ' + g.r); g._genre = words(g.g);
        g._prompt = words(g.p); g._feel = words(g.f + ' ' + g.m + ' ' + g.x.join(' ') + ' ' + g.e.join(' '));
      });
      return idx;
    });
  }

  HS.words = words; HS.mark = mark; HS.esc = esc; HS.load = load; HS.rank = rank; HS.countText = countText;
  HS.chipSets = chipSets; HS.chipsHTML = chipsHTML; HS.cardHTML = cardHTML; HS.cardButton = cardButton;

  // ---------- the sheet (radio page only) ----------
  var opener = document.getElementById('btnSearch');
  if (!opener) return;   // search.html: core only

  var CSS = '\
#hsRoot{position:fixed;inset:0;z-index:60;font-family:var(--text,Inter,system-ui,sans-serif);font-weight:300;font-size:15px;line-height:1.5;color:#ece9dc}\
#hsRoot[hidden]{display:none}\
#hsRoot *{box-sizing:border-box}\
.hs-scrim{position:absolute;inset:0;background:rgba(6,8,18,.55)}\
.hs-bar{position:absolute;top:max(14px,env(safe-area-inset-top));left:14px;right:14px;max-width:40rem;margin:0 auto;z-index:2;display:flex;align-items:center;gap:10px;border:1px solid rgba(236,233,220,.35);border-radius:999px;padding:4px 6px 4px 14px;background:rgba(10,16,32,.94)}\
.hs-bar svg{width:15px;height:15px;stroke:rgba(236,233,220,.5);fill:none;stroke-width:1.8;flex:none}\
.hs-bar input{flex:1;min-width:0;border:0;background:none;color:#fff;font:inherit;font-size:16px;outline:none;padding:7px 0}\
.hs-bar input::placeholder{color:rgba(236,233,220,.5)}\
.hs-x{appearance:none;border:0;background:none;color:rgba(236,233,220,.8);font-size:24px;line-height:1;width:40px;height:40px;border-radius:50%;cursor:pointer}\
.hs-sheet{position:absolute;left:0;right:0;bottom:0;top:calc(max(14px,env(safe-area-inset-top)) + 58px);max-width:40rem;margin:0 auto;z-index:1;display:flex;flex-direction:column;background:rgba(10,16,32,.95);border-top:1px solid rgba(236,233,220,.2);border-radius:22px 22px 0 0;transform:translateY(40px);opacity:0;transition:transform .28s ease,opacity .28s ease}\
#hsRoot.in .hs-sheet{transform:none;opacity:1}\
.hs-handle{width:38px;height:4px;border-radius:2px;background:rgba(236,233,220,.3);margin:9px auto 4px;flex:none}\
.hs-body{flex:1;overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;padding:6px 18px 24px}\
.hs-feel{display:flex;gap:6px;overflow-x:auto;padding:4px 0 2px;scrollbar-width:none}\
.hs-feel::-webkit-scrollbar{display:none}\
.hs-grid{display:none;flex-wrap:wrap;gap:6px;padding:4px 0}\
.hs-grid.open{display:flex}\
.hs-grid .k{width:100%;font-size:10.5px;letter-spacing:.22em;text-transform:uppercase;color:rgba(236,233,220,.5);margin:6px 0 0}\
#hsRoot .chip{appearance:none;font:inherit;font-size:12.5px;color:rgba(236,233,220,.78);border:1px solid rgba(236,233,220,.28);background:rgba(6,8,18,.3);border-radius:999px;padding:6px 12px;cursor:pointer;white-space:nowrap;flex:none}\
#hsRoot .chip[aria-pressed="true"]{background:#f0a53a;border-color:#f0a53a;color:#0a1020;font-weight:500}\
#hsRoot .chip .n{opacity:.55;margin-left:4px;font-size:11px}\
#hsRoot .chip.more{border-style:dashed}\
.hs-count{font-size:12px;color:rgba(236,233,220,.5);margin:8px 0 0;min-height:1.2em}\
#hsRoot .card{border-top:1px solid rgba(236,233,220,.16);padding:13px 0 10px;margin-top:6px}\
#hsRoot .card.now{border-left:2px solid #f0a53a;padding-left:10px;margin-left:-12px}\
#hsRoot .card .city{font-family:var(--display,"Instrument Serif",Georgia,serif);font-weight:400;font-size:22px;line-height:1.1;margin:0;color:#ece9dc}\
#hsRoot .card .city i{font-style:italic;color:rgba(236,233,220,.72);font-size:.8em;margin-left:.35em}\
#hsRoot .card .meta{font-size:11.5px;color:rgba(236,233,220,.5);letter-spacing:.06em;margin:3px 0 6px;display:flex;flex-wrap:wrap;gap:4px 10px}\
#hsRoot .card .meta .g{color:rgba(236,233,220,.72);letter-spacing:.02em}\
#hsRoot .card .prompt{margin:0 0 8px;font-size:13.5px;line-height:1.5;color:rgba(236,233,220,.72)}\
#hsRoot mark{background:rgba(240,165,58,.28);color:#ece9dc;padding:0 .1em;border-radius:2px}\
#hsRoot .acts{display:flex;gap:8px;margin:0 0 6px;flex-wrap:wrap}\
#hsRoot .btn{appearance:none;font-family:inherit;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#ece9dc;background:rgba(236,233,220,.08);border:1px solid rgba(236,233,220,.26);border-radius:999px;padding:10px 14px;cursor:pointer;white-space:nowrap}\
#hsRoot .btn.cue{background:#f0a53a;border-color:#f0a53a;color:#0a1020;font-weight:500}\
#hsRoot .btn.cue::before{content:"\\25B6";font-size:9px;margin-right:7px}\
#hsRoot .btn.done{background:#f0a53a;border-color:#f0a53a;color:#0a1020}\
#hsRoot .btn.ghost{background:none;color:rgba(236,233,220,.72)}\
#hsRoot .card ul{list-style:none;margin:0;padding:0;font-size:12.5px;color:rgba(236,233,220,.5)}\
#hsRoot .card li{padding:6px 0;cursor:pointer}\
#hsRoot .card li b{font-weight:400;color:rgba(236,233,220,.72);font-family:var(--display,"Instrument Serif",Georgia,serif);font-size:1.08em}\
#hsRoot .card li.playing,#hsRoot .card li.playing b{color:#f0a53a}\
.hs-more{display:block;margin:10px 0 0}\
.hs-full{display:block;margin-top:14px;font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;color:rgba(236,233,220,.6);text-underline-offset:3px}\
.hs-empty{color:rgba(236,233,220,.72);margin:12px 0}\
.hs-nowbar{flex:none;display:flex;align-items:center;gap:10px;padding:10px 18px calc(10px + env(safe-area-inset-bottom));background:rgba(10,16,32,.98);border-top:1px solid rgba(236,233,220,.22);font-size:12.5px}\
.hs-pp{appearance:none;flex:none;width:40px;height:40px;border-radius:50%;border:1px solid rgba(236,233,220,.4);background:none;color:#ece9dc;display:grid;place-items:center;cursor:pointer}\
.hs-pp svg{width:14px;height:14px;fill:currentColor}\
.hs-t{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\
.hs-t small{display:block;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:rgba(236,233,220,.5)}\
.hs-t b{font-weight:500}\
@media(prefers-reduced-motion:reduce){.hs-sheet{transition:none}}';

  var root, input, feel, grid, count, results, full, nowbar, bodyEl, IDX = null, SETS = [], ON = {}, shown = [], LIMIT = 30, limit = LIMIT;
  var isOpen = false, pushed = false, loading = false, t = null, lastFocus = null;
  var PAUSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>';
  var PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>';

  function build() {
    var st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    root = document.createElement('div'); root.id = 'hsRoot'; root.hidden = true;
    root.innerHTML = '<div class="hs-scrim"></div>'
      + '<div class="hs-bar" role="search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>'
      + '<input type="search" enterkeyhint="search" placeholder="a place, a genre, a sound" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Search prompts">'
      + '<button class="hs-x" type="button" aria-label="Close search">&times;</button></div>'
      + '<div class="hs-sheet" role="dialog" aria-label="Prompt search"><div class="hs-handle"></div>'
      + '<div class="hs-body"><div class="hs-feel"></div><div class="hs-grid"></div><p class="hs-count" aria-live="polite"></p><div class="hs-results"></div>'
      + '<a class="hs-full" href="search.html">Open full search &#8599;</a></div>'
      + '<div class="hs-nowbar"><button class="hs-pp" type="button" aria-label="Play or pause the radio"></button><span class="hs-t"></span></div></div>';
    document.body.appendChild(root);
    input = root.querySelector('input'); feel = root.querySelector('.hs-feel'); grid = root.querySelector('.hs-grid');
    count = root.querySelector('.hs-count'); results = root.querySelector('.hs-results'); full = root.querySelector('.hs-full');
    nowbar = root.querySelector('.hs-nowbar'); bodyEl = root.querySelector('.hs-body');

    root.querySelector('.hs-scrim').addEventListener('click', function () { close(); });
    root.querySelector('.hs-x').addEventListener('click', function () { close(); });
    input.addEventListener('input', function () { clearTimeout(t); t = setTimeout(function () { limit = LIMIT; writeHash(false); render(); }, 150); });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { clearTimeout(t); limit = LIMIT; render(); input.blur(); } });
    root.addEventListener('click', onClick);
    nowbar.querySelector('.hs-pp').addEventListener('click', function () { if (window.hisiaRadio) window.hisiaRadio.toggle(); });
    // the radio swipes left for "next track" on document touchend; a swipe inside the sheet is not that
    ['touchstart', 'touchend'].forEach(function (ev) { root.addEventListener(ev, function (e) { e.stopPropagation(); }, { passive: true }); });
    // swipe down closes when the list is at the top
    var sy = 0, sx = 0, st0 = 0;
    root.addEventListener('touchstart', function (e) { var p = e.changedTouches[0]; sy = p.clientY; sx = p.clientX; st0 = Date.now(); }, { passive: true });
    root.addEventListener('touchend', function (e) {
      var p = e.changedTouches[0], dy = p.clientY - sy, dx = p.clientX - sx;
      if (dy > 80 && Math.abs(dx) < dy / 2 && Date.now() - st0 < 800 && bodyEl.scrollTop <= 0 && !e.target.closest('.hs-feel')) close();
    }, { passive: true });
    window.addEventListener('hisia:track', paintNow);
  }

  function onClick(e) {
    var b = e.target.closest('button'), li = e.target.closest('li[data-file]');
    if (b && b.dataset.more) { grid.classList.toggle('open'); paintChips(); return; }
    if (b && b.dataset.chip) { var k = b.dataset.chip; if (ON[k]) delete ON[k]; else ON[k] = true; limit = LIMIT; writeHash(false); render(); return; }
    if (b && b.classList.contains('hs-showmore')) { limit += LIMIT; render(true); return; }
    var sec = e.target.closest('section.card'); if (!sec) return;
    var g = shown[+sec.dataset.i];
    if (b && g && HS.cardButton(b, g, input.value)) return;
    if (b && b.classList.contains('cue')) { playFile(g.t[0][0]); return; }
    if (li) playFile(li.dataset.file);
  }

  function playFile(file) {
    if (window.hisiaRadio) window.hisiaRadio.play(file);   // the radio's own track-start path, usual crossfade
  }

  function paintChips() {
    if (!SETS.length) { feel.innerHTML = ''; grid.innerHTML = ''; return; }
    var c = HS.chipsHTML(SETS, ON, grid.classList.contains('open'));
    feel.innerHTML = c.row; grid.innerHTML = c.grid;
  }

  function render(keepScroll) {
    if (!IDX) return;
    var r = HS.rank(IDX, input.value.trim(), ON); shown = r.shown;
    var np = window.hisiaRadio && window.hisiaRadio.now(), file = np && np.file;
    count.textContent = HS.countText(r);
    var cards = shown.slice(0, limit).map(function (g, i) { return HS.cardHTML(g, r.qws, i, { play: 'Play on the radio', file: file, idPrefix: 'hs-' }); }).join('');
    if (shown.length > limit) cards += '<button class="btn ghost hs-more hs-showmore" type="button">Show ' + Math.min(LIMIT, shown.length - limit) + ' more</button>';
    results.innerHTML = shown.length ? cards : '<p class="hs-empty">Nothing matches that. Try fewer words, or one of the chips.</p>';
    if (!shown.length) grid.classList.add('open');
    paintChips(); paintFull(); paintNow();
    if (!keepScroll) bodyEl.scrollTop = 0;
  }

  function paintFull() {
    var sp = new URLSearchParams(), v = input.value.trim(), keys = Object.keys(ON);
    if (v) sp.set('q', v); if (keys.length) sp.set('feel', keys.join(' '));
    full.href = 'search.html' + (sp.toString() ? '?' + sp.toString() : '');
  }

  function paintNow() {
    if (!root) return;
    var np = window.hisiaRadio && window.hisiaRadio.now();
    var line = nowbar.querySelector('.hs-t');
    if (!np || !np.title) { line.innerHTML = '<small>radio</small>nothing playing yet'; }
    else line.innerHTML = '<small>radio, ' + (np.paused ? 'paused' : 'playing') + '</small><b>' + HS.esc(np.city) + '</b> \u00b7 \u201c' + HS.esc(np.title) + '\u201d \u00b7 ' + HS.esc(np.artist);
    nowbar.querySelector('.hs-pp').innerHTML = np && !np.paused ? PAUSE : PLAY;
    var file = np && np.file;
    Array.prototype.forEach.call(results.querySelectorAll('li[data-file]'), function (li) { li.classList.toggle('playing', li.dataset.file === file); });
    Array.prototype.forEach.call(results.querySelectorAll('section.card'), function (sec) {
      var on = !!sec.querySelector('li.playing'); sec.classList.toggle('now', on);
      var cue = sec.querySelector('.btn.cue'); if (cue) cue.textContent = on ? 'Playing on the radio' : 'Play on the radio';
    });
  }

  // ---------- hash state: #q=lagos+brass&feel=texture:brass ----------
  function hashParams() { return new URLSearchParams(location.hash.replace(/^#/, '')); }
  function writeHash(push) {
    var sp = new URLSearchParams(), v = input.value.trim(), keys = Object.keys(ON);
    sp.set('q', v); if (keys.length) sp.set('feel', keys.join(' '));
    var url = location.pathname + location.search + '#' + sp.toString().replace(/%20/g, '+');
    if (push) { history.pushState({ hs: 1 }, '', url); pushed = true; } else history.replaceState(history.state, '', url);
  }
  function readHash() {
    var sp = hashParams(); input.value = sp.get('q') || ''; ON = {};
    (sp.get('feel') || '').split(' ').filter(Boolean).forEach(function (k) { ON[k] = true; });
  }

  function open(fromHash) {
    if (!root) build();
    if (isOpen) return;
    isOpen = true; lastFocus = document.activeElement;
    if (fromHash) readHash();
    root.hidden = false; void root.offsetWidth; root.classList.add('in');
    if (!fromHash) writeHash(true);
    paintNow();
    if (!IDX && !loading) {   // first open only: no cost to the radio if nobody searches
      loading = true; count.textContent = 'Loading prompts\u2026';
      HS.load('search-index.json').then(function (idx) { IDX = idx; SETS = HS.chipSets(idx); loading = false; render(); },
        function () { loading = false; count.textContent = 'The prompt list did not load. Try again in a moment.'; });
    } else render();
    setTimeout(function () { try { input.focus({ preventScroll: true }); } catch (e) {} }, 60);
  }

  function close(fromHash) {
    if (!isOpen) return;
    isOpen = false; root.classList.remove('in'); root.hidden = true;
    if (!fromHash) {
      if (pushed) { pushed = false; history.back(); }   // the hashchange it fires finds the sheet already closed
      else history.replaceState(null, '', location.pathname + location.search);
    } else pushed = false;
    input.blur();
    try { if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true }); } catch (e) {}
  }

  window.addEventListener('hashchange', function () {
    var has = hashParams().has('q');
    if (has && !isOpen) open(true);
    else if (!has && isOpen) close(true);
  });
  window.addEventListener('popstate', function () { if (isOpen && !hashParams().has('q')) close(true); });
  opener.addEventListener('click', function () { open(false); });
  document.addEventListener('keydown', function (e) {
    if (isOpen && e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (e.key === '/' && !isOpen && !e.metaKey && !e.ctrlKey && !e.altKey && !/input|textarea|select/i.test((e.target || {}).tagName || '')) { e.preventDefault(); open(false); }
  });
  if (hashParams().has('q')) open(true);
})();
