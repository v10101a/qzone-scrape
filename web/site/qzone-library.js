
const L = window.LIB, $ = s => document.querySelector(s);
let HOT = [0, 0], tab = 'skin', lastFloaty = null, curColor = null, snow = null, layoutIdx = 0;
let curTitlebar = null;   // singular page chrome (one at a time, toggle off)
let editMode = true;   // edit = drag/delete controls visible; view-only = clean preview
let pageZoom = 1;      // the fake browser is zoomed to fit viewports < 1280 (see fitPage)

// what's currently applied per type → drives the market selection checkmark.
// singular types hold one id; pendant holds a Set (multiple instances).
const SEL = { skin: '', color: '', titlebar: '', cursor: '', floaty: '', player: '', pendant: new Set() };
const idOf = it => String(typeof it === 'object' ? it.id : it);
function isSelected(t, id) {
  id = String(id);
  if (t === 'pendant') return SEL.pendant.has(id);
  return String(SEL[t] || '') === id;
}
function refreshSelection() {   // mark currently-rendered cells of the active tab
  document.querySelectorAll('#grid .cell').forEach(c => c.classList.toggle('on', isSelected(tab, c.dataset.id)));
}


const SHARED_HASH = location.hash.startsWith('#s=') ? location.hash.slice(3) : '';

let lang = 'zh'; try { lang = localStorage.getItem('lang') || 'zh'; } catch (e) { }
const T = {
  zh: {
    brand: 'QQ空间博物馆', navArchive: '藏品', navQzone: 'QQ空间', navAbout: '关于', langBtn: 'EN',
    market: '装扮空间', random: '随机', clear: '清空', preview: '预览', edit: '编辑', share: '分享',
    profile: '个人资料', visitors: '最近访客', diary: '最新日志', album: '相册',
    writeDiary: '写日记', upload: '上传照片', albumEmpty: '相册还空着～',
    navHome: '主页', navLog: '日志', navAlbum: '相册', navMusic: '音乐', navBoard: '留言板', navProfile: '个人档',
    qqshowLabel: '我的 QQ 秀', qqshowPh: '粘贴 qqshow2000.com 链接或 id…', searchPh: '按编号或 id 搜索…',
    create: '去 qqshow2000 创建 → ', nick: '我',
    space: n => `${n}的空间`, title: n => `${n}的 QQ 空间`,
    tabs: { skin: '皮肤', color: '配色', titlebar: '标题', pendant: '挂件', floaty: '漂浮', cursor: '鼠标', player: '音乐' }
  },
  en: {
    brand: 'QZone Museum', navArchive: 'Archive', navQzone: 'QZone', navAbout: 'About', langBtn: '中',
    market: 'Decorate', random: 'Random', clear: 'Clear', preview: 'Preview', edit: 'Edit', share: 'Share',
    profile: 'Profile', visitors: 'Recent Visitors', diary: 'Latest Diary', album: 'Album',
    writeDiary: 'Write »', upload: 'Upload »', albumEmpty: 'No photos yet～',
    navHome: 'Home', navLog: 'Diary', navAlbum: 'Album', navMusic: 'Music', navBoard: 'Board', navProfile: 'Profile',
    qqshowLabel: 'My QQ Show', qqshowPh: 'Paste a qqshow2000.com link or id…', searchPh: 'Search by # or id…',
    create: 'Create one on qqshow2000 → ', nick: 'Me',
    space: n => `${n}'s Space`, title: n => `${n}'s QZone`,
    tabs: { skin: 'Skin', color: 'Color', titlebar: 'Banner', pendant: 'Pendant', floaty: 'Floaty', cursor: 'Cursor', player: 'Music' }
  },
};
const TT = () => T[lang];
function applyLang() {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  const t = TT();
  document.querySelectorAll('[data-i18n]').forEach(e => { const v = t[e.dataset.i18n]; if (v != null) e.textContent = v; });
  document.querySelectorAll('[data-i18n-ph]').forEach(e => { const v = t[e.dataset.i18nPh]; if (v != null) e.placeholder = v; });
  const lb = $('#lang'); if (lb) lb.textContent = t.langBtn;
  const eb = $('#editBtn'); if (eb) eb.textContent = editMode ? t.preview : t.edit;
  if (typeof applyTitle === 'function') applyTitle();
  if (typeof renderTabs === 'function') renderTabs();
}

// embedded qqshow2000.com

const QQSHOW_API = 'https://iuthwndljsjdwhzlxopz.supabase.co/rest/v1/shares';
const QQSHOW_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml1dGh3bmRsanNqZHdoemx4b3B6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTg2MTM2MTUsImV4cCI6MjA3NDE4OTYxNX0.q-0qS8L5lpSB-ttj1HK2wfYTu0wM44KuEJ7FhKbz2oQ';
const QQSHOW_FALLBACK = ['he7v7brz', 'tr2u6i0x', 'hjhorfzw', 'hoe50zdr', 's51smak3', 'gqhudbpy', '3k29ta49', 'tzolnf55', 'bpdb6fdl', 'p1fgfg74', 'k9kv6c81', 'kbhdcfxn', 'amsssi0e', 'lubzcs2k', '5y4q1yoj', 'v4vfl3ru', 'tuo8lf89', 'ztjpive9', '0bf088qr', 'x42vgi30'];
const pickFallback = () => QQSHOW_FALLBACK[Math.floor(Math.random() * QQSHOW_FALLBACK.length)];

// accept a full URL, bare id, or empty
function parseQQId(raw) {
  raw = (raw || '').trim();
  if (!raw) return '';
  const m = raw.match(/[?&]id=([^&#\s]+)/);
  if (m) return decodeURIComponent(m[1]);
  return /^[\w-]+$/.test(raw) ? raw : '';   // bare id, else unrecognized
}

async function randomQQId() {
  try {
    const h = { apikey: QQSHOW_KEY, Authorization: 'Bearer ' + QQSHOW_KEY };
    const c = await fetch(QQSHOW_API + '?select=id', { headers: { ...h, Prefer: 'count=exact', Range: '0-0' } });
    const total = parseInt((c.headers.get('content-range') || '').split('/')[1], 10);
    if (!total) throw 0;
    const off = Math.floor(Math.random() * total);
    const r = await fetch(`${QQSHOW_API}?select=id&limit=1&offset=${off}`, { headers: h });
    const rows = await r.json();
    if (rows && rows[0] && rows[0].id) return rows[0].id;
    throw 0;
  } catch (e) { return pickFallback(); }
}

// point the embed at an id 
function showQQShow(id) {
  const card = $('#qqshow'); if (!card) return;
  if (!id) { card.style.display = 'none'; return; }
  const url = `https://qqshow2000.com/?id=${id}`;
  card.style.display = ''; card.href = url; card.querySelector('.qqshow-frame').src = url;
  const input = $('#qqshowInput'); if (input) input.value = id;
}
async function randomizeQQShow() {
  try { localStorage.removeItem('qqshowId'); } catch (e) { }   // un-pin → stays random on refresh
  showQQShow(await randomQQId());
}
(function mountQQShow() {
  let pinned = ''; try { pinned = localStorage.getItem('qqshowId') || ''; } catch (e) { }
  if (SHARED_HASH) { /* a shared space sets the QQ秀 via applyState */ }
  else if (pinned) showQQShow(pinned); else randomizeQQShow();   // pinned id wins, else random per load
  const input = $('#qqshowInput');
  const apply = () => {
    const id = parseQQId(input.value);
    if (!id) { input.focus(); input.select(); return; }
    try { localStorage.setItem('qqshowId', id); } catch (e) { }   // pin it
    showQQShow(id);
  };
  $('#qqshowApply') && ($('#qqshowApply').onclick = apply);
  $('#qqshowRandom') && ($('#qqshowRandom').onclick = randomizeQQShow);
  input && input.addEventListener('keydown', e => { if (e.key === 'Enter') apply(); });
})();

// nick name
let rawName = '我';
function applyTitle() {
  const tt = TT();
  const raw = (rawName || '').trim();
  const nm = (!raw || raw === '我') ? tt.nick : raw;   // untouched default → localized "Me/我"
  const t = $('#pageTitle'); if (t) t.textContent = tt.title(nm);
  const loc = $('#viewerLoc'); if (loc) loc.textContent = tt.space(nm);   // window title-bar breadcrumb
}
function setName(name, persist) {
  rawName = (name || '').trim();
  const pn = $('#profileName'); if (pn && document.activeElement !== pn) pn.textContent = rawName;
  applyTitle();
  if (persist !== false) { try { rawName ? localStorage.setItem('qzName', rawName) : localStorage.removeItem('qzName'); } catch (e) { } }
}
(function mountName() {
  const pn = $('#profileName'); if (!pn) return;
  if (!SHARED_HASH) { try { rawName = localStorage.getItem('qzName') || '我'; } catch (e) { } }
  pn.textContent = rawName; applyTitle();
  pn.contentEditable = editMode;   // editable unless previewing (kept in sync by setEditMode)
  pn.addEventListener('input', () => { rawName = pn.textContent; applyTitle(); try { if (rawName.trim()) localStorage.setItem('qzName', rawName.trim()); } catch (e) { } });
  pn.addEventListener('blur', () => { rawName = pn.textContent.trim(); if (!rawName) { try { localStorage.removeItem('qzName'); } catch (e) { } } applyTitle(); });
  pn.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); pn.blur(); } });
  const caretEnd = el => { const s = window.getSelection(), r = document.createRange(); r.selectNodeContents(el); r.collapse(false); s.removeAllRanges(); s.addRange(r); };
  const editBtn = $('#profileEditBtn'); if (editBtn) editBtn.onclick = () => { pn.focus(); caretEnd(pn); };
})();

const P = {
  skin: { label: '皮肤', kind: 'skin' },
  color: { label: '配色', kind: 'color' },
  titlebar: { label: '标题', kind: 'titlebar', path: id => { const it = L.titlebar.find(x => x.id == id); return `../library/titlebar/${id}.${it ? it.ext : 'gif'}`; } },
  pendant: { label: '挂件', kind: 'pendant', path: id => `../library/pendant/${id}.gif` },
  floaty: { label: '漂浮', kind: 'floaty' },                       // items = {id, n(frames)}
  cursor: { label: '鼠标', kind: 'cursor', path: id => `../library/cursor_anim/${id}.png` },
  player: { label: '音乐', kind: 'player', path: id => `../library/player/${id}.swf` },
};

if ('serviceWorker' in navigator && location.protocol.startsWith('http'))
  navigator.serviceWorker.register('sw.js').catch(() => { });


function renderTabs() {
  const t = TT();
  $('#tabs').innerHTML = Object.entries(P).map(([k, v]) =>
    `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${(t.tabs && t.tabs[k]) || v.label}</button>`).join('');
}
renderTabs();
$('#tabs').onclick = e => {
  const b = e.target.closest('button'); if (!b) return; tab = b.dataset.t;
  document.querySelectorAll('.tabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); render();
};
$('#search').oninput = render;

function render() {
  const items = L[tab] || [], q = $('#search').value.trim();
  const allIds = items.map(idOf);
  const num = new Map(allIds.map((id, i) => [id, i + 1]));   // stable 1-based catalog number
  let ids = allIds;
  if (q) ids = ids.filter(id => id.includes(q) || String(num.get(id)).includes(q));  // by number OR id

  ids = ids.slice().sort((a, b) => (isSelected(tab, b) ? 1 : 0) - (isSelected(tab, a) ? 1 : 0));
  const shown = ids;

  const COLS = {
    skin: 2, color: 4, titlebar: 1, pendant: 6, floaty: 4, cursor: 4, player: 3
  };

  $('#grid').className = 'grid t-' + tab + ' c' + (COLS[tab] || 4);

  const none = tab === 'pendant' ? '' : `<div class="cell cell-none" data-none="1" data-id="" title="无（关闭）"></div>`;
  $('#grid').innerHTML = none + shown.map(id => {
    const n = num.get(id);                    // displayed index
    if (tab === 'color') {
      const c = items.find(x => idOf(x) === id);

      return `<div class="cell swatch" data-id="${id}" title="id ${id}">`
        + `<div class="sw-main" style="background:${c.nav}"></div>`
        + `<div class="sw-strip"><i style="background:${c.tabBg}" title="bg"></i><i style="background:${c.nick}" title="name"></i><i style="background:${c.hover}" title="hover"></i><i style="background:${c.text}" title="text"></i></div>`
        + `<div class="id">${n}</div></div>`;
    }
    if (tab === 'player')
      return `<div class="cell" data-id="${id}" title="id ${id}"><img loading="lazy" src="assets/player_gallery/${id}.png" onerror="this.parentElement.classList.add('swatch');this.parentElement.style.background='linear-gradient(135deg,#2bb673,#0f1620)';this.remove()"><div class="id">${n}</div></div>`;
    let src;
    if (tab === 'skin') src = items.find(x => idOf(x) === id).top;
    else if (tab === 'floaty') src = `../library/floaty/${id}_1.gif`;
    else if (P[tab].thumb) src = P[tab].thumb(id);
    else src = P[tab].path(id);
    return `<div class="cell" data-id="${id}" title="id ${id}"><img loading="lazy" src="${src}"><div class="id">${n}</div></div>`;
  }).join('');
  refreshSelection();   // show checkmarks for whatever is already applied on this tab (incl. 无)
}

$('#grid').addEventListener('click', e => {
  const c = e.target.closest('.cell'); if (!c) return;
  c.dataset.none ? disableType(tab) : apply(tab, c.dataset.id);
});

// turn OFF a singular decoration
function disableType(t) {
  if (t === 'skin') { $('#skinBg').style.background = '#dde6ec'; $('#browserBody').style.background = '#dde6ec'; SEL.skin = ''; }
  else if (t === 'color') { COLOR_VARS.forEach(v => document.documentElement.style.removeProperty(v)); curColor = null; SEL.color = ''; }
  else if (t === 'titlebar') { const ph = $('#pageHeader'); if (ph) { ph.classList.remove('on'); ph.style.backgroundImage = ''; } curTitlebar = null; SEL.titlebar = ''; }
  else if (t === 'cursor') { document.body.classList.remove('custom-cursor'); $('#stageWrap').style.cursor = 'auto'; const f = $('#followCursor'); if (f) f.remove(); HOT = [0, 0]; SEL.cursor = ''; }
  else if (t === 'floaty') { stopSnow(); }                                   // stopSnow clears SEL.floaty
  else if (t === 'player') { $('#pageDeco').querySelectorAll('.player-deco').forEach(x => x.remove()); SEL.player = ''; }
  refreshSelection();
}

function apply(type, id) {
  const k = P[type].kind;
  if (k === 'skin') {
    const it = L.skin.find(x => x.id == id);

    $('#skinBg').style.background = it.bg ? `url("${it.bg}")` : '#dde6ec';
    $('#browserBody').style.background = `url("${it.top}") top center / 100% auto no-repeat`
      + (it.bg ? `, url("${it.bg}") repeat` : ', #dde6ec');
  }
  else if (k === 'color') applyColor(id);
  else if (k === 'titlebar') applyTitlebar(id);   // 页头 banner (singular, toggle)
  else if (k === 'cursor') setFollowerCursor(id);
  else if (k === 'pendant') addDeco(id, { hang: true });                    // 挂件 = individual, multiple
  else if (k === 'floaty') startSnow(L.floaty.find(f => f.id == id));       // 漂浮 = falling snow
  else if (k === 'player') addPlayer(id);                                   // 音乐 = QQ music player skin
  if (k === 'skin') SEL.skin = String(id);
  else if (k === 'color') SEL.color = curColor ? String(curColor) : '';     // toggle-aware
  else if (k === 'titlebar') SEL.titlebar = curTitlebar ? String(curTitlebar) : '';
  else if (k === 'cursor') SEL.cursor = String(id);
  refreshSelection();
}

//  color scheme
const COLOR_VARS = ['--c-tabbg', '--c-tabborder', '--c-tabactive', '--c-hd', '--c-link', '--c-text', '--c-hover', '--c-nick', '--c-hdtext'];

function readableOn(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || ''); if (!m) return '#fff';
  const n = parseInt(m[1], 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#333' : '#fff';
}

function applyColor(id) {
  const c = L.color.find(x => x.id == id), r = document.documentElement.style;
  if (!c) return;   // unknown id (e.g. a shared link to a pruned scheme) → ignore
  if (curColor === id) { COLOR_VARS.forEach(v => r.removeProperty(v)); curColor = null; return; }
  r.setProperty('--c-tabbg', c.tabBg); r.setProperty('--c-tabborder', c.tabBorder);
  r.setProperty('--c-tabactive', c.tabActive); r.setProperty('--c-hd', c.nav);
  r.setProperty('--c-link', c.link); r.setProperty('--c-text', c.text);
  r.setProperty('--c-hover', c.hover);   // accent (link/tab hover) — the only thing some runs vary
  r.setProperty('--c-nick', c.nick);     // nickname accent → the page title (.who)
  // module header (个人资料/留言板…) text: follow the scheme, but auto-contrast vs the header
  // bg (nav) so it's always legible — incl. light-nav schemes where white was invisible
  r.setProperty('--c-hdtext', readableOn(c.nav));
  curColor = id;
}

// type 19:  banner between nav and modules
function applyTitlebar(id) {
  const ph = $('#pageHeader'); if (!ph) return;
  if (curTitlebar == id) { ph.classList.remove('on'); ph.style.backgroundImage = ''; curTitlebar = null; return; }
  ph.style.backgroundImage = `url("${P.titlebar.path(id)}")`;
  ph.classList.add('on'); curTitlebar = id;
}

// type 5: floaties
function startSnow(fl) {
  stopSnow(); lastFloaty = fl; SEL.floaty = String(fl.id);
  const stage = $('#stageDeco'), wrap = $('#browserBody');   // snow bounded to the window
  const W = () => wrap.clientWidth, H = () => wrap.clientHeight;
  const sprites = [];
  for (let i = 0; i < 8; i++) {
    const frame = 1 + Math.floor(Math.random() * fl.n);          // random frame, like itemno_(P+1).gif
    const el = document.createElement('img'); el.className = 'snowflake';
    el.src = `../library/floaty/${fl.id}_${frame}.gif`; el.style.width = '32px'; el.style.height = 'auto';
    stage.appendChild(el);
    sprites.push({
      el, x: Math.random() * W(), y: Math.random() * H(),
      speed: Math.random() * 1.5 + 1, step: Math.random() * 6.28, sway: 0.02 + Math.random() * 0.03
    });
  }
  const tick = () => {
    const w = W(), h = H();
    for (const s of sprites) {
      s.y += s.speed; s.step += s.sway; s.x += Math.cos(s.step) * 1.3;
      if (s.y > h) { s.y = -36; s.x = Math.random() * w; }
      s.el.style.left = s.x + 'px'; s.el.style.top = s.y + 'px';
    }
    snow.raf = requestAnimationFrame(tick);
  };
  snow = { raf: requestAnimationFrame(tick) };
}
function stopSnow() { if (snow) cancelAnimationFrame(snow.raf); document.querySelectorAll('.snowflake').forEach(s => s.remove()); snow = null; SEL.floaty = ''; }

// type 2: pendant: individual, draggable
function addDeco(id, { hang, x, y } = {}) {
  const d = document.createElement('div'); d.className = 'deco pendant-deco'; d.dataset.id = id;

  d.style.left = (x != null ? x : Math.round(Math.random() * 1200)) + 'px';
  d.style.top = (y != null ? y : (hang ? Math.round(Math.random() * 720) : 20 + Math.random() * 300)) + 'px';
  d.innerHTML = `<img src="${P.pendant.path(id)}" style="display:block"><div class="ph"><button class="del" data-x>✕</button></div>`;
  $('#pageDeco').appendChild(d); drag(d);
  SEL.pendant.add(String(id));
  // a pendant can be placed MANY times — only un-select once the LAST copy is removed
  d.querySelector('[data-x]').onclick = () => {
    d.remove();
    const stillOnPage = [...$('#pageDeco').querySelectorAll('.pendant-deco')].some(x => x.dataset.id === String(id));
    if (!stillOnPage) SEL.pendant.delete(String(id));
    refreshSelection();
  };
}

// type 6: QQ Music Player skin
function addPlayer(id) {
  const meta = L.player.find(x => idOf(x) === String(id)) || { w: 210, h: 90 };
  const w = meta.w, h = meta.h;
  // swapping the player KEEPS its current spot (just changes the skin); default = lower-left
  const old = $('#pageDeco').querySelector('.player-deco');
  const bbH = $('#browserBody').clientHeight || 900;
  const left = old ? old.style.left : '12px';
  const top = old ? old.style.top : (bbH - h - 16) + 'px';   // lower-left of the window
  if (old) old.remove();
  const d = document.createElement('div'); d.className = 'deco swfdeco player-deco'; d.dataset.id = id;
  d.style.left = left; d.style.top = top;
  const host = document.createElement('div');


  const surface = document.createElement('div'); surface.className = 'drag-surface';

  const title = document.createElement('div'); title.className = 'mp-title'; title.innerHTML = '<span></span>';
  const ph = document.createElement('div'); ph.className = 'ph';
  ph.innerHTML = `<button class="mbtn" data-music title="设置音乐链接">♫</button><button class="del" data-x>✕</button>`;

  // music-link popover
  const pop = document.createElement('div'); pop.className = 'music-pop';
  pop.innerHTML = `<div class="mp-row"><input class="mp-in" placeholder="link to music"><button class="mp-go">OK</button></div><span class="mp-st"></span><div class="mp-foot"><a class="mp-eg" href="#">▶ test</a><button class="mp-del" title="delete">✕</button></div>`;
  d.appendChild(host); d.appendChild(surface); d.appendChild(title); d.appendChild(ph); d.appendChild(pop); $('#pageDeco').appendChild(d);
  const pl = window.RufflePlayer.newest().createPlayer(); pl.style.width = w + 'px'; pl.style.height = h + 'px'; host.appendChild(pl);
  pl.load({
    url: P.player.path(id), autoplay: 'on', muted: true, unmuteOverlay: 'hidden', wmode: 'transparent',
    // No song list fed to the SWF: it's muted + decorative (real audio = setMusic, real ticker
    // = our .mp-title overlay). Starving its FlashVars leaves its baked-in ticker nothing to
    // scroll — the only lever we have, since we can't reach inside the Flash text field.
    parameters: ''
  }).catch(() => { });
  const popIn = pop.querySelector('.mp-in'), popGo = pop.querySelector('.mp-go'), popSt = pop.querySelector('.mp-st');
  // open → put the cursor in the field and highlight the current link so it's easy to replace
  const openPop = () => { pop.classList.add('open'); popIn.value = musicURL; popIn.focus(); popIn.select(); };
  // show 加载中… → on confirmed playback, flash ✓ then auto-close (clear feedback, no guessing)
  const setSong = () => {
    if (!popIn.value.trim()) return;
    musicStatus(popSt, '加载中…');
    setMusic(popIn.value, popSt, () => setTimeout(() => pop.classList.remove('open'), 900));
  };
  popGo.onclick = setSong;
  popIn.addEventListener('keydown', e => { if (e.key === 'Enter') setSong(); });
  pop.querySelector('.mp-eg').onclick = e => { e.preventDefault(); popIn.value = 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3'; setSong(); };
  pop.querySelector('.mp-del').onclick = () => { stopMusic(); popIn.value = ''; popIn.focus(); musicStatus(popSt, '已删除歌曲'); };
  ph.querySelector('[data-music]').onclick = e => { e.stopPropagation(); pop.classList.contains('open') ? pop.classList.remove('open') : openPop(); };
  // click the gadget (a non-drag tap): if a song is loaded → play/pause; else open the link popover
  surface.addEventListener('click', () => {
    if (surface.__moved) return;
    if (toggleMusic()) return;
    if (editMode) openPop();
  });
  ph.querySelector('[data-x]').onclick = () => { d.remove(); SEL.player = ''; stopMusic(); refreshSelection(); };
  drag(d, surface);   // drag anywhere on the player
  SEL.player = String(id);
  updatePlayerState();
}

// drag `el` by grabbing `handle` (defaults to el itself). A handle is needed for
// Ruffle widgets because the Flash canvas swallows pointer events.
function drag(el, handle) {
  const h = handle || el;
  h.onpointerdown = e => {
    if (!editMode || e.target.tagName === 'BUTTON') return; e.preventDefault();
    h.__moved = false;
    const sx = e.clientX, sy = e.clientY, ox = parseFloat(el.style.left) || 0, oy = parseFloat(el.style.top) || 0;
    h.setPointerCapture(e.pointerId);
    h.onpointermove = m => {
      if (Math.abs(m.clientX - sx) + Math.abs(m.clientY - sy) > 4) h.__moved = true;   // distinguish drag from click
      el.style.left = (ox + (m.clientX - sx) / pageZoom) + 'px'; el.style.top = (oy + (m.clientY - sy) / pageZoom) + 'px';
    };
    h.onpointerup = () => { h.onpointermove = null; };
  };
}

// animated follower cursor
function setFollowerCursor(id) {
  document.body.classList.add('custom-cursor');
  $('#stageWrap').style.cursor = 'none';
  let f = $('#followCursor');
  if (!f) {
    f = document.createElement('img'); f.id = 'followCursor';
    f.style.cssText = 'position:fixed;pointer-events:none;z-index:99999;image-rendering:pixelated;display:none;left:-100px;top:-100px;';
    document.body.appendChild(f);
  }
  f.src = P.cursor.path(id) + '?t=' + id; const hs = window.HOTSPOTS && window.HOTSPOTS[id]; HOT = hs ? hs.hotspot : [0, 0];
}

document.addEventListener('pointermove', e => {
  const f = $('#followCursor'); if (!f) return;
  f.style.left = (e.clientX - HOT[0]) + 'px'; f.style.top = (e.clientY - HOT[1]) + 'px';
  const onChrome = e.target && e.target.closest && e.target.closest('.toolbar, .market');
  f.style.display = onChrome ? 'none' : 'block';
}, true);


function setMarket(open) {
  const m = $('#market');
  if (open) {   // drop from the bar, pinned to the 我的空间 WINDOW's right edge (floating)
    const r = $('#marketToggle').getBoundingClientRect();
    const frame = $('.viewer-frame'); const fr = frame ? frame.getBoundingClientRect() : { right: window.innerWidth - 8 };
    m.style.top = (r.bottom + 6) + 'px';
    m.style.right = Math.max(8, window.innerWidth - fr.right + 8) + 'px';
    m.style.maxHeight = (window.innerHeight - r.bottom - 22) + 'px';
  }
  m.classList.toggle('collapsed', !open);
  $('#marketToggle').classList.toggle('on', open);       // 装扮空间 looks "pressed" while open
}
$('#marketToggle').onclick = () => {
  const open = $('#market').classList.contains('collapsed');
  setMarket(open);
  if (open) setEditMode(true);   // opening the market means you're editing again
};

// view-only
function setEditMode(on) {
  editMode = on;
  document.body.classList.toggle('view-only', !on);
  const pn = $('#profileName'); if (pn) pn.contentEditable = on;   // name editable only while editing
  $('#editBtn').textContent = on ? TT().preview : TT().edit;   // single always-visible toggle
  // (no active/.primary highlight — 编辑 is just a normal action, not a "pressed" state)
  if (on) {
    // editing a shared space = remixing it → drop the "browsing" banner and the shared hash
    const fb = $('#forkBanner'); if (fb) fb.remove();
    if (location.hash) history.replaceState(null, '', location.pathname);
  } else setMarket(false);
}
$('#editBtn').onclick = () => setEditMode(!editMode);
setMarket(false);   // panel starts closed; open it via 装扮空间

function clearAll() {
  stopSnow(); $('#stageDeco').innerHTML = ''; $('#pageDeco').innerHTML = '';
  $('#skinBg').style.background = '#dde6ec'; $('#browserBody').style.background = '#dde6ec';
  COLOR_VARS.forEach(v => document.documentElement.style.removeProperty(v)); curColor = null;
  const ph = $('#pageHeader'); if (ph) { ph.classList.remove('on'); ph.style.backgroundImage = ''; } curTitlebar = null;
  document.body.classList.remove('custom-cursor'); $('#stageWrap').style.cursor = 'auto'; const f = $('#followCursor'); if (f) f.remove();
  stopMusic();
  rizhiList = []; renderRizhi();
  visitors = []; renderVisitors();
  SEL.skin = SEL.color = SEL.titlebar = SEL.cursor = SEL.floaty = SEL.player = '';
  SEL.pendant.clear(); render();
}
$('#clearBtn').onclick = clearAll;
$('#randomBtn').onclick = () => {
  const r = a => a[Math.floor(Math.random() * a.length)];
  $('#pageDeco').innerHTML = ''; SEL.pendant.clear(); SEL.player = '';
  apply('skin', idOf(r(L.skin)));                    // skin only — no auto color scheme (keep it tidy)
  apply('cursor', idOf(r(L.cursor)));                // random cursor too
  for (let i = 0; i < 3; i++) addDeco(idOf(r(L.pendant)), { hang: true });
  startSnow(r(L.floaty));
  genRizhiNew();                                      // roll one 日志 (fresh seed) so the page feels lived-in
  genVisitors();                                      // and a row of recent visitors (fresh seed)
  render();   // re-render so the market shows (pinned + checkmarked) what was just placed
};

// background music by LINK 
// Two backends, both AUDIO-ONLY (no visible video) and both with working play/pause:
//   • direct media file (.mp3 …) → invisible <audio loop>
//   • YouTube link → the YouTube IFrame API in an OFF-SCREEN (not display:none) player;
//     started by a user gesture (the 播放 click) so audio plays with sound, no video shown.
// Other streaming sites (网易云/Spotify…) have no embeddable hidden-audio API → message.
let musicURL = '', musicMode = '', ytPlayer = null, ytReady = false, ytPending = null;
const AUDIO_EXT = /\.(mp3|m4a|ogg|oga|wav|aac|flac|opus)(\?|#|$)/i;
const MUSIC_SITES = /(spotify\.com|bilibili\.com|music\.163\.com|y\.qq\.com|kugou\.com|kuwo\.cn|soundcloud\.com)/i;
function parseMusic(raw) {
  raw = (raw || '').trim(); if (!raw) return null; let m;
  if (AUDIO_EXT.test(raw)) return { type: 'audio', url: raw };
  if (m = raw.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{11})/)) return { type: 'yt', id: m[1], url: raw };
  if (MUSIC_SITES.test(raw)) return { type: 'site', url: raw };
  return { type: 'unknown', url: raw };
}
function musicStatus(el, msg) { if (el) el.textContent = msg || ''; }
function loadYTAPI() {
  if (window.YT && window.YT.Player) { ytReady = true; return; }
  if (!document.getElementById('yt-api')) {
    const s = document.createElement('script'); s.id = 'yt-api'; s.src = 'https://www.youtube.com/iframe_api'; document.head.appendChild(s);
  }
  window.onYouTubeIframeAPIReady = () => { ytReady = true; if (ytPending) { const q = ytPending; ytPending = null; q(); } };
}
function playYouTube(videoId, st, onOk) {
  loadYTAPI();
  let done = false;
  const start = () => {
    let holder = document.getElementById('ytHolder'); if (holder) holder.remove();
    holder = document.createElement('div'); holder.id = 'ytHolder';
    holder.style.cssText = 'position:fixed;left:-9999px;bottom:0;width:200px;height:120px;';   // off-screen, NOT display:none
    document.body.appendChild(holder);
    ytPlayer = new YT.Player('ytHolder', {
      videoId, playerVars: { autoplay: 1, loop: 1, playlist: videoId, controls: 0 },
      events: {
        onReady: e => { e.target.playVideo(); updatePlayerState(); },
        onStateChange: e => { updatePlayerState(); if (e.data === 1 && !done) { done = true; musicStatus(st, '✓ 已加载，播放中'); onOk && onOk(); } },
        onError: () => musicStatus(st, '⚠ 此视频禁止嵌入，换一个')
      }
    });
  };
  if (ytReady) start(); else ytPending = start;
}
// resume after a gesture (shared-load case where autoplay was blocked)
function armPlayOnGesture() {
  const go = () => { const a = $('#bgMusic'); if (a) a.play().catch(() => { }); if (ytPlayer && ytPlayer.playVideo) ytPlayer.playVideo(); };
  document.addEventListener('pointerdown', go, { once: true });
}
function stopMusic() {
  const a = $('#bgMusic'); if (a) a.remove();
  if (ytPlayer && ytPlayer.destroy) { try { ytPlayer.destroy(); } catch (e) { } } ytPlayer = null;
  const h = document.getElementById('ytHolder'); if (h) h.remove();
  musicURL = ''; musicMode = ''; updatePlayerState();
}
// play/pause toggle (clicking the gadget) — works for both audio + YouTube
function toggleMusic() {
  if (musicMode === 'audio') { const a = $('#bgMusic'); if (!a) return false; a.paused ? a.play().catch(() => { }) : a.pause(); updatePlayerState(); return true; }
  if (musicMode === 'yt' && ytPlayer && ytPlayer.getPlayerState) { ytPlayer.getPlayerState() === 1 ? ytPlayer.pauseVideo() : ytPlayer.playVideo(); updatePlayerState(); return true; }
  return false;
}

function fileName(url) {
  try { const u = new URL(url, location.href); return decodeURIComponent((u.pathname.split('/').pop() || '').replace(/\.[a-z0-9]+$/i, '')) || url; }
  catch (e) { return url || ''; }
}

function updatePlayerState() {
  const d = $('#pageDeco .player-deco'); if (!d) return; const tt = d.querySelector('.mp-title span');
  let has = false, name = '';
  if (musicMode === 'audio') { if ($('#bgMusic')) { has = true; name = fileName(musicURL); } }
  else if (musicMode === 'yt' && ytPlayer && ytPlayer.getVideoData) { has = true; const vd = ytPlayer.getVideoData(); name = (vd && vd.title) || 'YouTube'; }
  d.classList.toggle('has-music', has);
  if (tt && tt.textContent !== name) tt.textContent = name;
}

function setMusic(raw, st, onOk) {
  stopMusic();
  const info = parseMusic(raw); if (!info) { musicStatus(st, ''); return; }
  if (info.type === 'site' || info.type === 'unknown') {
    musicStatus(st, info.type === 'site' ? '这个网站做不了后台音乐，试试 YouTube 或 .mp3 直链' : '需 YouTube 链接或 .mp3 / .m4a 直链');
    return;
  }
  musicURL = info.url; musicMode = info.type;
  if (info.type === 'yt') { playYouTube(info.id, st, onOk); armPlayOnGesture(); return; }
  const a = document.createElement('audio'); a.id = 'bgMusic'; a.src = info.url; a.loop = true; a.style.display = 'none';
  a.addEventListener('play', updatePlayerState); a.addEventListener('pause', updatePlayerState);
  // 'playing' fires when it actually starts → the definitive "loaded ✓" signal
  a.addEventListener('playing', () => { musicStatus(st, '✓ 已加载，播放中'); onOk && onOk(); }, { once: true });
  document.body.appendChild(a);
  a.onerror = () => musicStatus(st, '⚠ 放不了，换个音频直链');
  a.play().catch(() => { musicStatus(st, '♪ 点击播放器或页面播放'); armPlayOnGesture(); });
}

// ── random 日志 generator 
// Markov model on shuoshuo_data.js → `lines and GENERATE novel prose that flows but is new each roll. 
const esc = s => (s || '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const MK_ORDER = 3;
let rizhiList = [], MK = null;
// ── seeded RNG so generated content (日志 + 访客) is reproducible from a tiny seed in the
// share link, instead of embedding all the text. mulberry32 = small deterministic PRNG. ──
function mulberry32(a) {
  return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
let RND = Math.random;                                  // swapped to a seeded fn during generation
const newSeed = () => (Math.random() * 0xffffffff) >>> 0;
function withSeed(seed, fn) { const prev = RND; RND = mulberry32(seed >>> 0); try { fn(); } finally { RND = prev; } }
let rzSeed = 0, vsSeed = 0;
const ri = n => Math.floor(RND() * n);
function buildMarkov(order) {
  const lines = (window.SHUOSHUO && window.SHUOSHUO.lines) || [];
  const text = lines.join('。') + '。', map = new Map();
  for (let i = 0; i < text.length - order; i++) {
    const pre = text.slice(i, i + order); let a = map.get(pre); if (!a) map.set(pre, a = []); a.push(text[i + order]);
  }
  return { map, order, starts: lines.filter(l => l.length > order) };
}
// walk the chain from a real line-start until a sentence stop near the target length
function markovPara(maxc) {
  if (!MK) MK = buildMarkov(MK_ORDER);
  const { map, order, starts } = MK; if (!starts.length) return '';
  let out = starts[Math.floor(RND() * starts.length)].slice(0, order);
  while (out.length < maxc) {
    const nx = map.get(out.slice(-order)); if (!nx) break;
    const c = nx[Math.floor(RND() * nx.length)]; out += c;
    if ('。！？'.includes(c) && out.length > maxc * 0.6 && RND() < 0.5) break;
  }
  if (!'。！？…'.includes(out[out.length - 1])) out += '。';
  return sanitize(out);
}
// tidy Markov artifacts: drop stray ascii/symbols, collapse 3+ repeats of a short run
// (kills "谢，谢，谢，…" loops) and runs of repeated punctuation
function sanitize(s) {
  return s.replace(/[*"＂]/g, '')
    .replace(/(.{1,4}?)\1{2,}/g, '$1')
    .replace(/([，。、…！？])\1+/g, '$1');
}
function rzDate() {
  const p = n => String(n).padStart(2, '0');
  const y = 2009 + Math.floor(RND() * 5), mo = 1 + Math.floor(RND() * 12), d = 1 + Math.floor(RND() * 28);
  return `${y}年${p(mo)}月${p(d)}日 ${p(Math.floor(RND() * 24))}时${p(Math.floor(RND() * 60))}分`;
}
// drop repeated sentences (Markov chains loop) — keeps each 日志 from echoing itself
function dedupeSentences(paras) {
  const seen = new Set();
  return paras.map(p => p.split(/(?<=[。！？…])/).filter(s => {
    s = s.trim(); if (!s || seen.has(s)) return false; seen.add(s); return true;
  }).join('')).filter(Boolean);
}
// 日志 = TWO random full posts (markov prose) — fills the wide column. Each = title (40% 《》)
// + paragraphs. Generated under a SEED so the share link reproduces the exact posts.
function genRizhi(nPara, baseLen) {
  const S = window.SHUOSHUO; if (!S || !S.lines || !S.lines.length) return null;
  let t = S.clauses[ri(S.clauses.length)]; if (RND() < 0.4) t = '《' + t + '》';
  const paras = [];
  for (let i = 0; i < nPara; i++) paras.push(markovPara(baseLen + ri(40)));
  return { t, p: dedupeSentences(paras), rd: 12 + ri(90), c: ri(18), d: rzDate() };
}
function genRizhiNew(seed) {
  rzSeed = (seed == null) ? newSeed() : (seed >>> 0);
  withSeed(rzSeed, () => { rizhiList = [genRizhi(3 + ri(2), 115), genRizhi(2, 85)].filter(Boolean); });
  renderRizhi();
}
function renderRizhi() {
  const bd = $('#rizhiBody'); if (!bd) return;
  bd.innerHTML = rizhiList.map(rz =>
    `<div class="rizhi"><div class="rizhi-title">${esc(rz.t)}</div>`
    + (rz.p || []).map(x => `<p class="rizhi-p">${esc(x)}</p>`).join('')
    + `<div class="rizhi-meta">查看全文» 阅读(${rz.rd}) 评论(${rz.c}) 转载 分享<span class="rizhi-date">${esc(rz.d)}</span></div></div>`).join('');
}
$('#rizhiNew') && ($('#rizhiNew').onclick = () => genRizhiNew());
$('#albumUpload') && ($('#albumUpload').onclick = () => toast('相册功能敬请期待～'));

// ── 最近访客 (visitor records) — recovered classic QQ pixel avatars + 非主流 网名 ──
// Avatars = window.AVATARS (Tencent ISUX pixel-retro classic system-avatar set, recovered
// to site/assets/avatars/). Nicknames reuse the short 签名 clauses (read like 非主流 网名).
let visitors = [];
const VISIT_TIME = ['刚刚', '5分钟前', '半小时前', '1小时前', '3小时前', '今天', '昨天', '前天', '3天前', '上周'];
function genVisitors(seed) {
  vsSeed = (seed == null) ? newSeed() : (seed >>> 0);
  const A = window.AVATARS || [], S = window.SHUOSHUO;
  withSeed(vsSeed, () => {
    visitors = [];
    const usedA = new Set(), usedN = new Set();       // distinct avatars + nicks → less 雷同
    let guard = 0;
    while (visitors.length < 2 && A.length && guard++ < 300) {
      const a = A[ri(A.length)];
      const nick = (S && S.clauses) ? S.clauses[ri(S.clauses.length)] : '神秘访客';
      if (usedA.has(a) && usedA.size < A.length) continue;
      if (usedN.has(nick)) continue;
      usedA.add(a); usedN.add(nick);
      visitors.push({ a, n: nick, t: VISIT_TIME[ri(VISIT_TIME.length)] });
    }
  });
  renderVisitors();
}
function renderVisitors() {
  const box = $('#visitorList'); if (!box) return;
  box.innerHTML = visitors.map(v =>
    `<div class="visitor" title="${esc(v.n)} · ${esc(v.t)}来访">`
    + `<img class="visitor-av" src="assets/avatars/${esc(v.a)}" alt="" loading="lazy">`
    + `<div class="visitor-meta"><div class="visitor-nick">${esc(v.n)}</div>`
    + `<div class="visitor-t">${esc(v.t)}来访</div></div></div>`).join('');
}
$('#visitorGen') && ($('#visitorGen').onclick = () => genVisitors());

// share link
function currentQQId() { const i = $('#qqshowInput'); return i ? i.value.trim() : ''; }
function buildShareState() {
  const px = el => Math.round(parseFloat(el.style.left) || 0), py = el => Math.round(parseFloat(el.style.top) || 0);
  const pe = [...document.querySelectorAll('#pageDeco .pendant-deco')].map(d => ({ i: d.dataset.id, x: px(d), y: py(d) }));
  const st = {
    v: 1, n: (rawName || '').trim(), q: currentQQId(),
    sk: SEL.skin || '', co: SEL.color || '', tb: SEL.titlebar || '',
    cu: SEL.cursor || '', fl: SEL.floaty || '', pl: SEL.player || '', mu: musicURL || '', pe, rzs: rzSeed, vss: vsSeed
  };
  // NOTE: 日志 + 访客 are NOT embedded — only their seeds (rzs/vss). They regenerate
  // identically from the seed on load, keeping the link short.
  const player = $('#pageDeco .player-deco'); if (player && st.pl) st.pp = [px(player), py(player)];
  return st;
}
async function applyState(st) {
  setName(st.n, false);   // show the shared name without persisting it as the viewer's own
  if (st.q) showQQShow(st.q);
  clearAll();
  if (st.sk) apply('skin', st.sk);
  if (st.co) apply('color', st.co);
  if (st.tb) apply('titlebar', st.tb);
  if (st.cu) apply('cursor', st.cu);
  if (st.fl) { const fl = L.floaty.find(f => f.id == st.fl); if (fl) startSnow(fl); }
  (st.pe || []).forEach(p => addDeco(p.i, { hang: true, x: p.x, y: p.y }));
  if (st.pl) { addPlayer(st.pl); const pe = $('#pageDeco .player-deco'); if (pe && st.pp) { pe.style.left = st.pp[0] + 'px'; pe.style.top = st.pp[1] + 'px'; } }
  if (st.mu) setMusic(st.mu);
  // regenerate 日志 + 访客 from their seeds (reproduces the sharer's exact content)
  if (st.rzs != null) genRizhiNew(st.rzs); else { rizhiList = []; renderRizhi(); }
  if (st.vss != null) genVisitors(st.vss); else { visitors = []; renderVisitors(); }
  render();   // market reflects the shared space's items (pinned + checkmarked)
}
// base64url over raw bytes (loop, not spread — safe for larger payloads when 说说 lands)
const b64u = {
  enc: u8 => { let s = ''; for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); },
  dec: s => { s = s.replace(/-/g, '+').replace(/_/g, '/'); return Uint8Array.from(atob(s), c => c.charCodeAt(0)); }
};
async function deflate(u8) { const cs = new CompressionStream('deflate'); const w = cs.writable.getWriter(); w.write(u8); w.close(); return new Uint8Array(await new Response(cs.readable).arrayBuffer()); }
async function inflate(u8) { const ds = new DecompressionStream('deflate'); const w = ds.writable.getWriter(); w.write(u8); w.close(); return new Uint8Array(await new Response(ds.readable).arrayBuffer()); }
async function encodeState(obj) {
  const json = new TextEncoder().encode(JSON.stringify(obj));
  if (typeof CompressionStream === 'function') { try { return 'd' + b64u.enc(await deflate(json)); } catch (e) { } }
  return 'r' + b64u.enc(json);   // fallback for browsers without CompressionStream
}
async function decodeState(str) {
  const codec = str[0]; let bytes = b64u.dec(str.slice(1));
  if (codec === 'd') bytes = await inflate(bytes);
  return JSON.parse(new TextDecoder().decode(bytes));
}
function toast(msg) {
  const t = document.createElement('div'); t.id = 'toast'; t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), 2000);
}
$('#shareBtn').onclick = async () => {
  const code = await encodeState(buildShareState());
  history.replaceState(null, '', '#s=' + code);   // reflect in the address bar
  const url = location.href;
  try { await navigator.clipboard.writeText(url); toast('链接已复制 ✓ 发给朋友吧'); }
  catch (e) { toast('链接已生成（见地址栏）'); }
};
// viewing someone else's shared space → a banner to remix it into your own
function showForkBanner() {
  if ($('#forkBanner')) return;
  const b = document.createElement('div'); b.id = 'forkBanner';
  b.innerHTML = `<span>正在浏览分享的空间</span><button id="forkBtn">改成我的 →</button>`;
  document.body.appendChild(b);
  $('#forkBtn').onclick = () => setEditMode(true);   // setEditMode handles banner + hash cleanup
}

render();
(async () => {
  if (SHARED_HASH) {
    try { await applyState(await decodeState(SHARED_HASH)); setEditMode(false); showForkBanner(); return; }
    catch (e) { console.warn('无法解析分享链接', e); randomizeQQShow(); }   // bad link → fall through to a fresh space
  }
  $('#randomBtn').click();                            // pick a skin + a couple decorations to start
})();

// responsive

function fitPage() {
  // zoom the 1280 page to fit the WINDOW WELL (#stageWrap), not the whole viewport
  const host = $('#stageWrap');
  const avail = (host ? host.clientWidth : document.documentElement.clientWidth);
  pageZoom = Math.min(1, avail / 1280);   // match .browser width
  const br = $('.browser'); if (br) br.style.zoom = pageZoom;
}
window.addEventListener('resize', fitPage);
fitPage();

// ── language toggle (EN ⇄ 中), shared with /museum/ via localStorage('lang') ──
$('#lang') && ($('#lang').onclick = () => {
  lang = lang === 'zh' ? 'en' : 'zh';
  try { localStorage.setItem('lang', lang); } catch (e) { }
  applyLang();
});
applyLang();   // paint chrome in the saved language on load
