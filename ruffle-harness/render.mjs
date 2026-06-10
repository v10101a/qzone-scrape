// render.mjs — headless Ruffle render check for scraped SWFs.
//
// For each .swf it: loads it in Ruffle inside headless Chromium, waits for
// playback, captures (1) whether Ruffle loaded it, (2) console errors/panics
// Ruffle emitted (the AS3 "unimplemented" signal), (3) a screenshot, and
// (4) a blank-canvas check. Writes a verdict per file to data/ruffle.jsonl.
//
// Verdicts:  ok | blank | errors | failed
//
// Setup once:  cd ruffle-harness && npm run setup
// Run:         node render.mjs [globDir] [--limit N] [--wait MS]
//   node render.mjs ../data/assets --limit 30
//
// Paths are resolved relative to the REPO ROOT (one level up from here).

import { createServer } from "node:http";
import { readFile, readdir, mkdir, writeFile, appendFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { extname, join, relative, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");

const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
  ".wasm": "application/wasm", ".swf": "application/x-shockwave-flash",
  ".json": "application/json", ".css": "text/css",
};

// --- tiny static file server rooted at the repo (so Ruffle can fetch wasm
//     chunks from node_modules AND the harness can fetch SWFs under data/) ---
function serve() {
  return new Promise((res) => {
    const srv = createServer(async (req, rep) => {
      try {
        const url = decodeURIComponent(req.url.split("?")[0]);
        const path = join(ROOT, url);
        const buf = await readFile(path);
        rep.writeHead(200, {
          "Content-Type": MIME[extname(path)] || "application/octet-stream",
          // wasm needs these for some Ruffle builds
          "Cross-Origin-Opener-Policy": "same-origin",
          "Cross-Origin-Embedder-Policy": "require-corp",
        });
        rep.end(buf);
      } catch {
        rep.writeHead(404);
        rep.end("nope");
      }
    });
    srv.listen(0, "127.0.0.1", () => res(srv));
  });
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (extname(p).toLowerCase() === ".swf") yield p;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const dirArg = args.find((a) => !a.startsWith("--")) || "data/assets";
  const limit = Number((args.find((a) => a.startsWith("--limit")) || "").split("=")[1]
    || args[args.indexOf("--limit") + 1]) || Infinity;
  const wait = Number((args.find((a) => a.startsWith("--wait")) || "").split("=")[1]
    || args[args.indexOf("--wait") + 1]) || 4000;

  const scanDir = resolve(ROOT, dirArg);
  if (!existsSync(scanDir)) throw new Error(`No such dir: ${scanDir}`);

  const swfs = [];
  for await (const p of walk(scanDir)) {
    swfs.push(p);
    if (swfs.length >= limit) break;
  }
  if (!swfs.length) throw new Error(`No .swf under ${scanDir}`);

  const shotDir = join(ROOT, "data", "screenshots");
  await mkdir(shotDir, { recursive: true });
  const outPath = join(ROOT, "data", "ruffle.jsonl");

  const srv = await serve();
  const port = srv.address().port;
  const browser = await chromium.launch();
  const tally = { ok: 0, blank: 0, errors: 0, failed: 0 };

  console.log(`Rendering ${swfs.length} SWF(s) via Ruffle on :${port}\n`);
  for (let i = 0; i < swfs.length; i++) {
    const swf = swfs[i];
    const rel = relative(ROOT, swf);
    const page = await browser.newPage();
    const logs = [];
    page.on("console", (m) => {
      const t = m.text();
      if (/error|panic|unimplement|unsupported|unknown/i.test(t)) logs.push(t);
    });
    page.on("pageerror", (e) => logs.push("pageerror: " + e.message));

    let state = {}, blank = true;
    try {
      await page.goto(
        `http://127.0.0.1:${port}/ruffle-harness/player.html?swf=/${encodeURIComponent(rel)}`,
        { waitUntil: "load", timeout: 20000 }
      );
      await page.waitForTimeout(wait);
      state = await page.evaluate(() => window.__ruffleState);
    } catch (e) {
      logs.push("harness: " + e.message);
    }

    // Screenshot the Ruffle element (tight crop) — this is GROUND TRUTH. Reading
    // the WebGL canvas in-page returns an empty buffer, so we blank-check the
    // composited screenshot instead by re-loading it as a plain image.
    // transparent-PNG screenshot of just the 挂件 (omitBackground) → alpha = art
    const shot = join(shotDir, `${String(i).padStart(4, "0")}_${rel.replace(/[\/\\]/g, "_")}.png`);
    let shotBuf = null, opaqueFrac = 0;
    try {
      const el = await page.$("#rp");
      shotBuf = el
        ? await el.screenshot({ path: shot, omitBackground: true })
        : await page.screenshot({ path: shot, omitBackground: true });
    } catch { /* ignore */ }

    if (shotBuf) {
      try {
        opaqueFrac = await page.evaluate(async (b64) => {
          const blob = await (await fetch("data:image/png;base64," + b64)).blob();
          const bmp = await createImageBitmap(blob);
          const W = 96, H = 96, c = new OffscreenCanvas(W, H), ctx = c.getContext("2d");
          ctx.drawImage(bmp, 0, 0, W, H);
          const d = ctx.getImageData(0, 0, W, H).data;
          let op = 0;
          for (let k = 3; k < d.length; k += 4) if (d[k] > 16) op++;
          return op / (W * H); // fraction of non-transparent pixels
        }, shotBuf.toString("base64"));
      } catch (e) { logs.push("alphacheck: " + e.message); }
    }
    blank = opaqueFrac < 0.004; // <0.4% opaque => nothing drew
    await page.close();

    // verdict by what actually DREW (opaque-pixel fraction), not console noise
    let verdict;
    if (state.error || logs.some((l) => /panic/i.test(l))) verdict = "failed";
    else if (blank) verdict = "empty";   // transparent/param-driven, nothing shown
    else verdict = "content";            // real visible 挂件 art
    tally[verdict] = (tally[verdict] || 0) + 1;

    const rec = { path: rel, verdict, opaqueFrac: Math.round(opaqueFrac * 1000) / 1000,
      loaded: !!state.loaded, ready: !!state.ready,
      errors: logs.slice(0, 8), screenshot: relative(ROOT, shot) };
    await appendFile(outPath, JSON.stringify(rec) + "\n");
    const mark = { content: "✓", empty: "▢", failed: "✗" }[verdict] || "?";
    console.log(`  [${i + 1}/${swfs.length}] ${mark} ${verdict.padEnd(7)} ${rel}`);
  }

  await browser.close();
  srv.close();
  console.log("\nSummary: " + Object.entries(tally).map(([k, v]) => `${k}=${v}`).join(" | "));
  console.log(`Screenshots -> data/screenshots/   verdicts -> data/ruffle.jsonl`);
}

main().catch((e) => { console.error(e); process.exit(1); });
