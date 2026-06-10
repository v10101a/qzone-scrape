// Render each recovered music-player SWF (fed a song list via FlashVars) to a PNG
// thumbnail so the 音乐 tab shows real player-skin previews. Self-contained server.
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { join, extname, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url)), ROOT = resolve(HERE, "..");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
  ".wasm": "application/wasm", ".swf": "application/x-shockwave-flash", ".png": "image/png",
  ".gif": "image/gif", ".jpg": "image/jpeg", ".css": "text/css" };

function serve() {
  return new Promise((res) => {
    const s = createServer(async (rq, rp) => {
      try { const u = decodeURIComponent(rq.url.split("?")[0]); const buf = await readFile(join(ROOT, u));
        rp.writeHead(200, { "Content-Type": MIME[extname(u)] || "application/octet-stream" }); rp.end(buf); }
      catch { rp.writeHead(404); rp.end(); }
    });
    s.listen(0, "127.0.0.1", () => res(s));
  });
}

const ids = readFileSync(join(ROOT, "data/catalogs/player_ids.txt"), "utf8").trim().split("\n");
const out = join(ROOT, "demo/player_gallery"); await mkdir(out, { recursive: true });
const srv = await serve(); const port = srv.address().port;
const b = await chromium.launch(); let ok = 0;
for (let i = 0; i < ids.length; i++) {
  const id = ids[i]; const p = await b.newPage({ viewport: { width: 400, height: 320 } });
  try {
    await p.goto(`http://127.0.0.1:${port}/demo/bundle/playerframe.html?swf=/library/player/${id}.swf`,
      { waitUntil: "domcontentloaded", timeout: 20000 });
    await p.waitForTimeout(4500);
    const el = await p.$("#rp");
    if (el) { await el.screenshot({ path: join(out, id + ".png"), omitBackground: true }); ok++; }
  } catch { /* skip */ }
  await p.close();
  if (i % 30 === 0) console.log(`${i}/${ids.length}`);
}
await b.close(); srv.close();
console.log("rendered", ok, "player previews ->", out);
