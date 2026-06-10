/* QZone Decoration Museum — browse / search / filter over window.META (catalog.js). */
'use strict';
const META = (window.META || []);

// ---- i18n -----------------------------------------------------------------
let lang = localStorage.getItem('lang') || 'zh';
const I18N = {
  zh: {
    brand: 'QQ空间博物馆', sub: n => `2005–2009 · 共 ${n} 件藏品`,
    search: '按名称或编号搜索…', all: '全部', color: '色', byDate: '按年代', shuffle: '乱序',
    animOnly: '仅动图', empty: '没有匹配的藏品', langBtn: 'EN',
    f_type: '类型', f_color: '色系', f_year: '年代', f_search: '搜索',
    d_era: '年代', d_color: '色系', d_size: '尺寸', d_price: '原价', d_animated: '动画',
    d_tags: '标签', d_yes: '是', price: p => `${p} <img class="hz" src="assets/huangzuan_plain.png" alt="黄钻">`, viewSrc: '查看原始素材 ↗',
    copyId: '复制编号', copied: '已复制 ✓', untitled: '（无名）',
    nav_archive: '藏品', nav_qzone: 'QQ空间', nav_about: '关于'
  },
  en: {
    brand: 'QZone Museum', sub: n => `2005–2009 · ${n} items`,
    search: 'Search by name or ID…', all: 'All', color: 'Color', byDate: 'By date', shuffle: 'Shuffle',
    animOnly: 'Animated', empty: 'No items match these filters', langBtn: '中',
    f_type: 'Type', f_color: 'Color', f_year: 'Year', f_search: 'Search',
    d_era: 'Era', d_color: 'Color', d_size: 'Size', d_price: 'Price', d_animated: 'Animated',
    d_tags: 'Tags', d_yes: 'Yes', price: p => `${p} <img class="hz" src="assets/huangzuan_plain.png" alt="Yellow Diamond">`, viewSrc: 'View original ↗',
    copyId: 'Copy ID', copied: 'Copied ✓', untitled: '(untitled)',
    nav_archive: 'Archive', nav_qzone: 'QZone', nav_about: 'About'
  },
};
const L = () => I18N[lang];
// null-safe text setter — header bits may be added/removed during restyling
const setTxt = (id, t) => { const e = document.getElementById(id); if (e) e.textContent = t; };

const TYPE_LABEL = { // [zh, en]
  skin: ['皮肤', 'Skins'], pendant: ['挂件', 'Pendants'], floaty: ['漂浮', 'Floaties'],
  cursor: ['鼠标', 'Cursors'], titlebar: ['标题', 'Title bars'], player: ['播放器', 'Music Players'],
  swf: ['Flash', 'Flash'],
};
const TYPE_ORDER = ['skin', 'pendant', 'floaty', 'cursor', 'titlebar', 'player', 'swf'];
const PIXEL_TYPES = new Set(['pendant', 'floaty', 'cursor']); // upscale crisp
const tType = t => (TYPE_LABEL[t] || [t, t])[lang === 'zh' ? 0 : 1];

const HUE = { // bucket -> [swatch, 中文, EN]
  red: ['#d6453d', '红', 'Red'], orange: ['#e08b0f', '橙', 'Orange'], yellow: ['#e6c12f', '黄', 'Yellow'],
  green: ['#5aa84f', '绿', 'Green'], cyan: ['#3fb6b6', '青', 'Cyan'], blue: ['#3d6bab', '蓝', 'Blue'],
  purple: ['#8a5fb0', '紫', 'Purple'], pink: ['#e08bb5', '粉', 'Pink'],
  white: ['#f3f3f3', '白', 'White'], gray: ['#9a9a9a', '灰', 'Gray'], black: ['#2b2b2b', '黑', 'Black'],
};
const HUE_ORDER = ['red', 'orange', 'yellow', 'green', 'cyan', 'blue', 'purple', 'pink', 'white', 'gray', 'black'];
const tHue = h => HUE[h] ? HUE[h][lang === 'zh' ? 1 : 2] : h;

// translation for the finite tag vocab; unknown tags fall back to Chinese
const TAG_EN = {
  '冷色': 'Cool', '暖色': 'Warm', '暧色': 'Warm', '黑白系': 'B&W', '黑白': 'B&W', '彩色': 'Colorful',
  '黑色': 'Black', '白色': 'White', '蓝色': 'Blue', '绿色': 'Green', '紫色': 'Purple', '黄色': 'Yellow',
  '红色': 'Red', '粉色': 'Pink', '半透明': 'Semi-transparent', '不透明': 'Opaque',
  '男生': 'Male', '男性': 'Male', '女生': 'Female', '女性': 'Female', '情侣': 'Couple', '孩童': 'Kids',
  '儿童': 'Kids', '宠物': 'Pets', '男艺人': 'Male star', '女艺人': 'Female star', '人物': 'People',
  '快乐': 'Happy', '高兴': 'Happy', '幸福': 'Blissful', '浪漫': 'Romantic', '伤感': 'Sad', '忧伤': 'Sad',
  '忧郁': 'Melancholy', '寂寞': 'Lonely', '平静': 'Calm', '生气': 'Angry', '奋斗': 'Striving',
  '另类': 'Alternative', '整蛊': 'Prank', '搞笑': 'Funny', '酷炫': 'Cool', '可爱': 'Cute', '简洁': 'Simple',
  '时尚': 'Stylish', '成熟': 'Mature', '古典': 'Classical', '青春': 'Youth', '商务': 'Business',
  'LOMO': 'LOMO', '甜蜜': 'Sweet', '动漫': 'Anime', '卡通': 'Cartoon', '夏': 'Summer', '春': 'Spring',
  '秋': 'Autumn', '冬': 'Winter', '四季': 'Seasons', '动物': 'Animals', '爱情': 'Love', '爱': 'Love',
  '非主流': 'Non-mainstream', '摄影': 'Photography', '梦': 'Dream', '小资': 'Bourgeois', '校园': 'Campus',
  '约定': 'Promise', '圣诞': 'Christmas', '蝴蝶': 'Butterfly', '自然': 'Nature', '风景': 'Scenery',
  '节日': 'Holiday', '星座': 'Zodiac', '明星': 'Star', '影视': 'Film', '游戏': 'Game', '中国风': 'Chinese',
  '友情': 'Friendship', '亲情': 'Family', '汽车': 'Car', '美食': 'Food', '旅游': 'Travel', '运动': 'Sports',
  '配饰': 'Accessories', '建筑': 'Architecture',
};
const tTag = t => lang === 'en' ? (TAG_EN[t] || t) : t;

// ---- state ----------------------------------------------------------------
const state = { type: 'all', hue: null, year: null, q: '', sort: 'date', animOnly: false };
let filtered = [], shown = 0, curItem = null;
const BATCH = 140;
const thumbURL = r => r.thumb ? '../' + r.thumb : '';

const countBy = key => { const m = {}; for (const r of META) { const v = r[key]; if (v) m[v] = (m[v] || 0) + 1; } return m; };
const typeCounts = countBy('type'), yearCounts = countBy('era');
// an item can have several hues — count membership across all of them
const hueCounts = (() => { const m = {}; for (const r of META) for (const h of (r.hues || [])) m[h] = (m[h] || 0) + 1; return m; })();

function chip(label, n, on, onClick) {
  const b = document.createElement('button');
  b.className = 'chip' + (on ? ' on' : '');
  b.innerHTML = label + (n != null ? ` <span class="n">${n}</span>` : '');
  b.onclick = onClick; return b;
}
function buildFacets() {
  const ft = document.getElementById('f-type'); ft.innerHTML = '';
  ft.appendChild(chip(L().all, META.length, state.type === 'all', () => { state.type = 'all'; refresh(); }));
  for (const t of TYPE_ORDER) {
    if (!typeCounts[t]) continue;
    ft.appendChild(chip(tType(t), typeCounts[t], state.type === t, () => { state.type = t; refresh(); }));
  }

  const fh = document.getElementById('f-hue'); fh.innerHTML = '';
  const lbl = document.createElement('span'); lbl.className = 'lbl'; lbl.textContent = L().color; fh.appendChild(lbl);
  for (const h of HUE_ORDER) {
    if (!hueCounts[h]) continue;
    const b = document.createElement('button'); b.className = 'sw' + (state.hue === h ? ' on' : '');
    b.style.background = HUE[h][0]; b.title = `${tHue(h)}  ${hueCounts[h]}`; b.dataset.hue = h;
    b.onclick = () => { state.hue = state.hue === h ? null : h; refresh(); }; fh.appendChild(b);
  }

  const fy = document.getElementById('f-year'); fy.innerHTML = '';
  for (const y of Object.keys(yearCounts).sort())
    fy.appendChild(chip(y, yearCounts[y], state.year === y, () => { state.year = state.year === y ? null : y; refresh(); }));
}

let rndSeed = 1;
function shuffle(arr) {
  let s = rndSeed; const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) { s = (s * 9301 + 49297) % 233280; const j = Math.floor(s / 233280 * (i + 1));[a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
function applyFilters() {
  const q = state.q.trim().toLowerCase();
  let out = META.filter(r => {
    if (state.type !== 'all' && r.type !== state.type) return false;
    if (state.hue && !(r.hues || []).includes(state.hue)) return false;
    if (state.year && r.era !== state.year) return false;
    if (state.animOnly && !r.animated) return false;
    if (q && !((r.name && r.name.toLowerCase().includes(q)) || String(r.id).includes(q))) return false;
    return true;
  });
  if (state.sort === 'rnd') out = shuffle(out);
  else out.sort((a, b) => (a.date || '9999').localeCompare(b.date || '9999') || (+a.id) - (+b.id));
  return out;
}

const grid = document.getElementById('grid');
function cellHTML(r) {
  const c = document.createElement('div');
  c.className = 'cell ' + (PIXEL_TYPES.has(r.type) ? 'cell-pixel' : 'cell-photo');
  c.dataset.idx = r._i;
  const t = thumbURL(r);
  const dots = (r.hues || []).slice(0, 3)
    .map(h => `<span class="dot" style="background:${HUE[h] ? HUE[h][0] : r.color}"></span>`).join('');
  c.innerHTML =
    (dots ? `<span class="dots">${dots}</span>` : '') +
    (r.animated ? `<span class="anim-badge">GIF</span>` : '') +
    (t ? `<img loading="lazy" src="${t}" alt="${r.name || r.id}">` : `<span class="noimg">${r.id}</span>`) +
    `<span class="cap"><span class="id">#${r.id} ${tType(r.type)}</span><span class="nm">${r.name || '—'}</span></span>`;
  return c;
}
function renderBatch() {
  const frag = document.createDocumentFragment();
  const end = Math.min(shown + BATCH, filtered.length);
  for (let i = shown; i < end; i++) frag.appendChild(cellHTML(filtered[i]));
  grid.appendChild(frag); shown = end;
}
function refresh() {
  rndSeed = (rndSeed * 16807) % 2147483647;
  const tchips = document.querySelectorAll('#f-type .chip');
  const types = ['all', ...TYPE_ORDER.filter(t => typeCounts[t])];
  tchips.forEach((c, i) => c.classList.toggle('on', types[i] === state.type));
  document.querySelectorAll('#f-hue .sw').forEach(s => s.classList.toggle('on', s.dataset.hue === state.hue));
  document.querySelectorAll('#f-year .chip').forEach(c => c.classList.toggle('on', c.textContent.trim().startsWith(state.year || '\0')));

  filtered = applyFilters(); grid.innerHTML = ''; shown = 0; renderBatch();
  setTxt('sub', L().sub(filtered.length.toLocaleString()));
  const emptyEl = document.getElementById('empty');
  if (emptyEl) { emptyEl.textContent = L().empty; emptyEl.hidden = filtered.length > 0; }
  buildActiveBar();
}
function buildActiveBar() {
  const bar = document.getElementById('active'); bar.innerHTML = '';
  const add = (label, clear) => {
    const b = document.createElement('button'); b.className = 'tag-x';
    b.innerHTML = label + ' ✕'; b.onclick = clear; bar.appendChild(b);
  };
  if (state.type !== 'all') add(`${L().f_type} <b>${tType(state.type)}</b>`, () => { state.type = 'all'; refresh(); });
  if (state.hue) add(`${L().f_color} <b>${tHue(state.hue)}</b>`, () => { state.hue = null; refresh(); });
  if (state.year) add(`${L().f_year} <b>${state.year}</b>`, () => { state.year = null; refresh(); });
  if (state.animOnly) add(`<b>${L().animOnly}</b>`, () => { state.animOnly = false; document.getElementById('animOnly').checked = false; refresh(); });
  if (state.q) add(`${L().f_search} <b>${state.q}</b>`, () => { state.q = ''; document.getElementById('q').value = ''; refresh(); });
}

// ---- detail ---------------------------------------------------------------
const detail = document.getElementById('detail');
function openDetail(r) {
  curItem = r;
  document.getElementById('d-img').src = thumbURL(r);
  document.getElementById('d-img').alt = r.name || r.id;
  document.getElementById('d-img').className = PIXEL_TYPES.has(r.type) ? 'pixel' : '';
  document.getElementById('d-name').textContent = r.name || L().untitled;
  document.getElementById('d-sub').textContent =
    `#${r.id} · ${tType(r.type)}` + (r.date ? ` · ${r.date.slice(0, 10)}` : '');
  const dl = document.getElementById('d-dl'); dl.innerHTML = '';
  // recessed glass field-card: label on top, value in an inset box
  const row = (k, v, wide) => {
    if (!v) return;
    const f = document.createElement('div'); f.className = 'field' + (wide ? ' wide' : '');
    f.innerHTML = `<span class="fl">${k}</span><span class="fv">${v}</span>`;
    dl.appendChild(f);
  };
  row(L().d_era, r.era);
  if (r.w) row(L().d_size, `${r.w}×${r.h}`);
  if (r.price) row(L().d_price, L().price(r.price));
  if (r.animated) row(L().d_animated, L().d_yes);
  if (r.hues && r.hues.length) row(L().d_color, `<span class="huelist">` + r.hues.map(h =>
    `<span class="huechip"><span class="dot" style="background:${HUE[h] ? HUE[h][0] : r.color}"></span>${tHue(h)}</span>`
  ).join('') + `</span>`, true);
  const tags = [...new Set([].concat(r.themes || [], r.mood || [], r.tone || [], r.audience || [], r.cats || []))].filter(Boolean);
  if (tags.length) row(L().d_tags, `<div class="pills">${tags.map(t => `<span class="pill">${tTag(t)}</span>`).join('')}</div>`, true);
  const src = document.getElementById('d-src'); src.href = r.src || '#'; src.textContent = L().viewSrc;
  const copy = document.getElementById('d-copy'); copy.textContent = L().copyId;
  copy.onclick = () => {
    navigator.clipboard?.writeText(String(r.id)); copy.textContent = L().copied;
    setTimeout(() => copy.textContent = L().copyId, 1200);
  };
  detail.hidden = false; location.hash = 'item-' + r.id;
}
function closeDetail() {
  curItem = null; detail.hidden = true;
  if (location.hash.startsWith('#item-')) history.replaceState(null, '', location.pathname);
}
detail.querySelectorAll('[data-close]').forEach(e => e.onclick = closeDetail);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

// ---- language -------------------------------------------------------------
function applyLang() {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  setTxt('brand', L().brand);
  const qEl = document.getElementById('q'); if (qEl) qEl.placeholder = L().search;
  setTxt('lang', L().langBtn);
  setTxt('animLbl', L().animOnly);
  setTxt('nav-archive', L().nav_archive);
  setTxt('nav-qzone', L().nav_qzone);
  setTxt('nav-about', L().nav_about);
  document.querySelectorAll('.sort button[data-sort]').forEach(b => {
    b.textContent = b.dataset.sort === 'date' ? L().byDate : L().shuffle;
  });
  buildFacets();
  refresh();
  if (curItem) openDetail(curItem);
}

// ---- wire up --------------------------------------------------------------
META.forEach((r, i) => r._i = i);
grid.addEventListener('click', e => { const c = e.target.closest('.cell'); if (c) openDetail(META[+c.dataset.idx]); });
let qTimer;
document.getElementById('q').addEventListener('input', e => {
  clearTimeout(qTimer); qTimer = setTimeout(() => { state.q = e.target.value; refresh(); }, 150);
});
document.getElementById('random').onclick = () => { if (filtered.length) openDetail(filtered[Math.floor(Math.random() * filtered.length)]); };
document.getElementById('lang').onclick = () => { lang = lang === 'zh' ? 'en' : 'zh'; localStorage.setItem('lang', lang); applyLang(); };
document.querySelectorAll('.sort button[data-sort]').forEach(b => {
  b.onclick = () => {
    state.sort = b.dataset.sort;
    document.querySelectorAll('.sort button[data-sort]').forEach(x => x.classList.toggle('on', x === b)); refresh();
  };
});
document.getElementById('animOnly').onchange = e => { state.animOnly = e.target.checked; refresh(); };
new IntersectionObserver(es => { if (es[0].isIntersecting && shown < filtered.length) renderBatch(); },
  { rootMargin: '700px' }).observe(document.getElementById('sentinel'));

applyLang();
if (location.hash.startsWith('#item-')) {
  const id = location.hash.slice(6); const r = META.find(x => String(x.id) === id); if (r) openDetail(r);
}
