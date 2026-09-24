// kiosk flow on top of qzone-library.js: everything that touches the 空间 (apply, addDeco,
// startSnow, setFollowerCursor, addPlayer, clearAll, render, setMarket, setEditMode, the share
// state…) is the site's own; this file only places the window and runs idle/done/reset.
(() => {
  'use strict';
  const META = window.META || [];
  const Q = new URLSearchParams(location.search);
  const IDLE_MS = (+Q.get('idle') || 120) * 1000;   // ?idle=<seconds> for testing
  const SHARE_BASE = Q.get('share') || 'https://qzone2000.com/site/';   // where the postcard QR points
  const NAME = Q.get('name') || 'viola';
  const TICK_MS = 500, WANDER = true, MAX_PENDANTS = 3;
  const ROLL = ['skin', 'pendant', 'color', 'floaty', 'titlebar', 'cursor', 'player'];   // one type per tick, interlaced
  const PIXEL = new Set(['pendant', 'floaty', 'cursor']);
  let mode = 'idle', idleT = null, attractT = null, tickN = 0, lastMouse = 0;
  const rnd = n => Math.floor(Math.random() * n), pickOf = a => a[rnd(a.length)];
  const shuffled = a => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = rnd(i + 1);[a[i], a[j]] = [a[j], a[i]]; } return a; };

  // players re-roll every few seconds in idle — no Ruffle splash logo between loads
  window.RufflePlayer = window.RufflePlayer || {};
  window.RufflePlayer.config = Object.assign({}, window.RufflePlayer.config, { splashScreen: false });

  // English chrome everywhere, incl. the archive iframe (shares localStorage 'lang')
  try { localStorage.setItem('lang', 'en'); } catch (e) { }
  T.en.preview = 'Done ✓';
  lang = 'en'; applyLang();
  setName(NAME, false);

  // ---- window placement: the locked 1280×900 page + its title bar, fitted into a box per mode ----
  function place() {
    const vw = innerWidth, vh = innerHeight, bar = $('.viewer-bar').offsetHeight || 48;
    let bw = vw - 48, bh = vh - 48, x = 24, y = 24;
    if (mode === 'idle') { bw = vw * .6; bh = vh * .66; x = (vw - bw) / 2; y = vh * .12; }
    const z = Math.min(bw / 1280, (bh - bar) / 900), w = 1280 * z + 2, h = 900 * z + bar + 2;
    const vf = $('.viewer-frame');
    vf.style.left = (x + (bw - w) / 2) + 'px'; vf.style.top = (y + (bh - h) / 2) + 'px';
    vf.style.width = w + 'px'; vf.style.height = h + 'px';
    $('.browser').style.zoom = z; pageZoom = z; fitQQShow(z);
    $('#stageWrap').scrollLeft = 0; $('#stageWrap').scrollTop = 0;
    if (!$('#market').classList.contains('collapsed')) setMarket(true);   // re-pin the dropdown
  }
  function setMode(m) { mode = m; document.body.dataset.mode = m; place(); }
  window.addEventListener('resize', place);   // registered after the site's fitPage, so this wins

  // ---- idle: museum wall behind the window, page re-rolled with the site's 随机 ----
  function buildWall() {
    const wall = $('#wall'); wall.innerHTML = '';
    const cols = Math.max(4, Math.round(innerWidth / 150));
    const cellW = (innerWidth - 24) / cols - 12, per = Math.ceil(innerHeight / (cellW + 12)) + 2;
    const pool = shuffled(META.filter(r => r.thumb));
    let k = 0;
    for (let c = 0; c < cols; c++) {
      const col = document.createElement('div'); col.className = 'wall-col' + (c % 2 ? ' rev' : '');
      col.style.setProperty('--dur', (80 + rnd(50)) + 's');
      col.style.animationDelay = -rnd(60) + 's';
      let html = '';
      for (let i = 0; i < per; i++) { const r = pool[k++ % pool.length]; html += `<div class="wcell${PIXEL.has(r.type) ? ' px' : ''}"><img loading="lazy" src="../${r.thumb}" alt=""></div>`; }
      col.innerHTML = html + html;   // duplicated → the -50% loop is seamless
      wall.appendChild(col);
    }
  }
  function roll(type) {
    const items = L[type]; if (!items || !items.length) return;
    const id = idOf(pickOf(items));
    if (type === 'skin') {   // preload, so the page never flashes gray between skins
      const it = L.skin.find(s => idOf(s) === id), img = new Image();
      img.onload = () => { if (mode === 'idle') apply('skin', id); };
      img.src = it.top; return;
    }
    if (type === 'pendant') {   // addDeco stacks, so retire the oldest beyond the cap
      const ps = $('#pageDeco').querySelectorAll('.pendant-deco');
      if (ps.length >= MAX_PENDANTS) ps[0].remove();
      SEL.pendant.clear(); $('#pageDeco').querySelectorAll('.pendant-deco').forEach(x => SEL.pendant.add(x.dataset.id));
    }
    if ((type === 'color' && SEL.color === id) || (type === 'titlebar' && SEL.titlebar === id)) return;   // apply() would toggle it off
    apply(type, id);
  }
  function attractTick() {
    roll(ROLL[tickN % ROLL.length]);
    if (tickN % 16 === 7) randomizeQQShow();
    if (tickN % 16 === 15) { genRizhiNew(); genVisitors(); }
    tickN++;
  }
  // idle only: the follower cursor drifts over the page until someone moves the mouse
  document.addEventListener('pointermove', e => { if (e.pointerType === 'mouse') lastMouse = performance.now(); }, { capture: true, passive: true });
  const wd = { x: 0, y: 0, tx: 0, ty: 0 };
  function wander(now) {
    const f = $('#followCursor');
    if (WANDER && mode === 'idle' && f && now - lastMouse > 4000) {
      const r = $('#stageWrap').getBoundingClientRect();
      if (!wd.x) { wd.x = r.left + r.width / 2; wd.y = r.top + r.height / 2; }
      if (Math.hypot(wd.tx - wd.x, wd.ty - wd.y) < 4) { wd.tx = r.left + r.width * (.1 + Math.random() * .8); wd.ty = r.top + r.height * (.1 + Math.random() * .8); }
      wd.x += (wd.tx - wd.x) * .01; wd.y += (wd.ty - wd.y) * .01;
      f.style.left = (wd.x - HOT[0]) + 'px'; f.style.top = (wd.y - HOT[1]) + 'px'; f.style.display = 'block';
    }
    requestAnimationFrame(wander);
  }
  requestAnimationFrame(wander);

  // ---- decorate: the site's market open on the window; Done ✓ = the site's preview toggle ----
  function decorate() {
    setEditMode(true); setMode('decorate');
    tab = 'skin'; $('#search').value = ''; renderTabs(); render(); $('#grid').scrollTop = 0;
    setMarket(true);
  }
  function start() { clearInterval(attractT); decorate(); bump(); }
  $('#attract').onclick = start;
  document.addEventListener('keydown', () => { if (mode === 'idle') start(); });
  $('#editBtn').addEventListener('click', () => setMode(editMode ? 'decorate' : 'done'));   // after the site's toggle
  $('#again').onclick = decorate;

  // ---- postcard: the page's skin + its decorations on a card, QR of the site's share link ----
  function qrTint() {   // the page's 配色 header color (else the skin's color), darkened until it scans
    let c = (document.documentElement.style.getPropertyValue('--c-hd') || '').trim();
    if (!c && SEL.skin) { const r = META.find(x => x.type === 'skin' && String(x.id) === SEL.skin); c = r && r.color; }
    const m = /^#?([0-9a-f]{6})$/i.exec(c || ''); if (!m) return '#1257c4';
    let [r, g, b] = [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
    while (.299 * r + .587 * g + .114 * b > 110) { r *= .85; g *= .85; b *= .85; }
    return '#' + [r, g, b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  }
  async function openPostcard() {
    const url = SHARE_BASE + '#s=' + await encodeState(buildShareState());
    $('#pc-title').textContent = $('#pageTitle').textContent;
    const body = $('#pc-body'), it = SEL.skin && L.skin.find(s => idOf(s) === SEL.skin);
    body.style.background = it ? `url("${it.top}") top center / 100% auto no-repeat, url("${it.bg}") repeat` : '#dde6ec';
    document.body.classList.add('postcard-open');
    // composed, not copied: QR in the middle, pendants hanging from the top, floaties + cursor at the sides
    const SLOTS = ['left:5%;top:3%', 'right:5%;top:3%', 'left:19%;top:2%', 'right:19%;top:2%', 'left:33%;top:1%', 'right:33%;top:1%'];
    let html = '';
    document.querySelectorAll('#pageDeco .pendant-deco').forEach((d, i) => {
      const img = d.querySelector('img');
      html += `<img src="${img.src}" style="${SLOTS[i % SLOTS.length]};width:${Math.min(120, (img.naturalWidth || img.width) * .8)}px" alt="">`;
    });
    document.querySelectorAll('#stageDeco .snowflake').forEach((s, i) => {
      html += `<img src="${s.src}" style="${i % 2 ? 'right' : 'left'}:${3 + rnd(17)}%;top:${8 + rnd(78)}%;width:28px" alt="">`;
    });
    if (SEL.player) { const m = L.player.find(x => idOf(x) === SEL.player) || { w: 210, h: 90 }; html += `<img src="assets/player_gallery/${SEL.player}.png" style="left:3%;bottom:7%;width:${m.w * .7}px;height:${m.h * .7}px" alt="">`; }
    if (SEL.cursor) html += `<img src="../library/cursor_anim/${SEL.cursor}.png" style="left:calc(50% + 120px);top:56%" alt="">`;
    $('#pc-deco').innerHTML = html;
    if (window.QRCode) QRCode.toCanvas($('#pc-qr'), url, { width: 200, margin: 1, color: { dark: qrTint(), light: '#ffffff' } });
  }
  $('#postcardBtn').onclick = openPostcard;
  $('#pc-close').onclick = () => document.body.classList.remove('postcard-open');

  // ---- archive: the museum as is; the QZone tab is the landing page here, so it's hidden ----
  $('#browse').onclick = () => {
    setMode('archive');
    const f = document.createElement('iframe'); f.src = '../';
    f.addEventListener('load', () => {   // fires again on every in-frame navigation (about.html…)
      try {
        const d = f.contentDocument; hookInput(d);
        const s = d.createElement('style'); s.textContent = '#nav-qzone,.about-go a[href="site/"]{display:none}'; d.head.appendChild(s);
      } catch (e) { }
    });
    $('#archive').prepend(f);
  };
  function closeArchive() { const f = $('#archive iframe'); if (f) f.remove(); }
  $('#back').onclick = goIdle;   // leaving the collection = the next visitor's turn

  // ---- idle + the 2-minute reset ----
  function goIdle() {
    clearTimeout(idleT); clearInterval(attractT); closeArchive();
    document.body.classList.remove('postcard-open');
    try { localStorage.removeItem('qzName'); } catch (e) { }   // a visitor's typed name doesn't carry over
    setName(NAME, false);
    setEditMode(false);   // clean window, market collapsed
    buildWall(); setMode('idle');
    $('#randomBtn').click(); randomizeQQShow();
    tickN = 0; attractT = setInterval(attractTick, TICK_MS);
  }
  function bump() { if (mode === 'idle') return; clearTimeout(idleT); idleT = setTimeout(goIdle, IDLE_MS); }
  function hookInput(doc) {
    ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'].forEach(ev => doc.addEventListener(ev, bump, { capture: true, passive: true }));
  }
  hookInput(document);

  if ('serviceWorker' in navigator && location.protocol.startsWith('http')) navigator.serviceWorker.register('../tiat/sw.js').catch(() => { });
  goIdle();
})();
