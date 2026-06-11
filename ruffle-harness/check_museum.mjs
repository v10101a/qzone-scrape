import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage();
const errs = [];
p.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
p.on('pageerror', e => errs.push('PAGEERROR: '+e.message));
await p.goto('http://localhost:8731/', { waitUntil:'networkidle' });
await p.waitForTimeout(1200);

const cellCount = () => p.$$eval('.cell', els => els.length);
const cells = await cellCount();
await p.screenshot({ path:'/tmp/museum_landing.png', fullPage:false });
const firstCap = await p.$eval('.cell .cap .nm', e=>e.textContent).catch(()=>'?');
// did first few thumbnails actually load pixels?
const imgStats = await p.$$eval('.cell img', imgs => {
  const first = imgs.slice(0,12);
  return { total:imgs.length, loaded:first.filter(i=>i.complete && i.naturalWidth>0).length, sample:first.length };
});
// open a detail by clicking the first cell
await p.click('.cell');
await p.waitForTimeout(400);
const detailOpen = await p.isVisible('#detail .detail-card');
const dName = await p.textContent('#d-name');
const dImgOk = await p.$eval('#d-img', i=>i.complete && i.naturalWidth>0).catch(()=>false);
await p.screenshot({ path:'/tmp/museum_grid.png', fullPage:false });
await p.keyboard.press('Escape');

// test a filter: click blue swatch + a type
await p.click('#f-type .chip:nth-child(2)'); // first real type
await p.waitForTimeout(300);
const afterType = await cellCount();

// test search
await p.fill('#q', '爱');
await p.waitForTimeout(400);
const afterSearch = await cellCount();
await p.screenshot({ path:'/tmp/museum_filtered.png' });

console.log(JSON.stringify({ cells, imgStats, detailOpen, dName, dImgOk, afterType, afterSearch, errs }, null, 2));
await b.close();
