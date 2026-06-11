import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 880 } });
const errs = [];
p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));
await p.goto('http://localhost:8777/qqshow/museum/', { waitUntil: 'networkidle' });
await p.waitForTimeout(1500);

const total = await p.evaluate(() => (window.QQSHOW || []).length);
const cells = await p.$$eval('.cell', els => els.length);
const kinds = await p.$$eval('#f-kind .chip', els => els.map(e => e.textContent.trim()));
// did the composited/single layer GIFs actually load pixels?
const imgStats = await p.$$eval('.cell img', imgs => {
  const f = imgs.slice(0, 30);
  return { total: imgs.length, loaded: f.filter(i => i.complete && i.naturalWidth > 0).length, sample: f.length };
});
await p.screenshot({ path: '/tmp/qqshow_landing.png', fullPage: false });

// open the first multi-layer "look" to test the compositor + layer strip
const lookIdx = await p.evaluate(() => (window.QQSHOW || []).findIndex(r => r.kind === 'look'));
if (lookIdx >= 0) {
  await p.evaluate(i => document.querySelectorAll('.cell')[0] && null, lookIdx);
}
await p.click('.cell .badge.look').catch(() => p.click('.cell'));
await p.waitForTimeout(600);
const detailOpen = await p.isVisible('#detail .detail-card');
const dName = await p.textContent('#d-name');
const stageImgs = await p.$$eval('#d-stage img', imgs => ({
  n: imgs.length, loaded: imgs.filter(i => i.complete && i.naturalWidth > 0).length
}));
const layerStrip = await p.$$eval('#d-layers .layer', els => els.length);
await p.screenshot({ path: '/tmp/qqshow_detail.png', fullPage: false });
await p.keyboard.press('Escape');

// filter: click the 造型 (Looks) kind tab if present
await p.click('#f-kind .chip:nth-child(2)').catch(() => { });
await p.waitForTimeout(300);
const afterKind = await p.$$eval('.cell', els => els.length);

// search by an id
await p.fill('#q', '1');
await p.waitForTimeout(400);
const afterSearch = await p.$$eval('.cell', els => els.length);
await p.screenshot({ path: '/tmp/qqshow_filtered.png' });

console.log(JSON.stringify({ total, cells, kinds, imgStats, detailOpen, dName, stageImgs, layerStrip, afterKind, afterSearch, errs }, null, 2));
await b.close();
