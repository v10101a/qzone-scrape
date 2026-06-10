# QQ空间装扮 Museum — Process & Architecture

A working notebook for how this project scrapes, analyzes, and revives early
Chinese-internet Flash — QZone **装扮** (decorations), **花藤** (the flower-vine garden game), the **music player**, and 4399 games — and turns them into a browsable museum + embeddable widgets, in the spirit of Webamp / the Winamp Skin Museum.

---

## 1. The core idea (the "Webamp way")

Webamp's insight was that a Winamp `.wsz` skin is *inert data* — bitmaps + a
config — so one reimplemented player can render thousands of skins. Flash is
harder: a `.swf` fuses **code + assets** into one binary. That forces a fork in strategy, and the whole project is organized around deciding which fork each artifact takes:

| Path | What it is | Best for | Cost |
|------|-----------|----------|------|
| **A — Emulate** | Run the original `.swf` in **Ruffle** (WASM Flash player) | The games museum *at scale*; any self-contained AS1/2 widget | Low — drop it in |
| **B — Reimplement** | Decompile, keep assets as data, rebuild the logic in JS/Canvas, stub the dead backend | The 3–4 hero embeddable widgets; anything **networked** | High per item |

The decision is driven by two facts we extract per file (see §4, `analyze.py`):
**ActionScript version** (Ruffle is great at AS1/2, partial at AS3) and
**networked-or-not** (a widget that phoned home to a now-dead Tencent server
can't just be emulated — its backend is gone).

```
                     ┌─────────────┐
   for each .swf ──► │ analyze.py  │
                     └──────┬──────┘
            ┌───────────────┼────────────────┐
       AS1/2 &           AS3                networked
     self-contained    (any)             (dead backend)
            │             │                    │
       Path A         render-check         Path B
      (Ruffle)        (ruffle-harness) ──► if blank/fail ─► Path B
```

---

## 2. Pipeline at a glance

Five stages, each resumable, each writing a JSONL artifact the next stage reads:

```
 targets.py ─► harvest.py ─► download.py ─► analyze.py ─► ruffle-harness ─► museum
   (what)       (CDX index)    (bytes)      (triage)      (does it play?)   (present)
                    │              │            │              │
              manifest.jsonl  assets/ +    analysis.jsonl  ruffle.jsonl +
                              fetched.jsonl                 screenshots/
```

1. **Harvest** — query the Wayback **CDX API** for every archived asset URL on
   the target CDNs → a deduped manifest (URL + best snapshot timestamp).
2. **Download** — fetch each asset **live-CDN-first** (Tencent rarely purges old
   files), falling back to Wayback raw bytes. Validates SWF magic bytes.
3. **Analyze** — parse each SWF's structure (no Java needed) → AS version,
   networked flag, embedded URLs, asset/tag histogram.
4. **Render-check** — play each SWF in headless Ruffle, capture screenshot +
   console errors + blank-canvas detection → a per-file verdict.
5. **Museum** *(next)* — grid + search + "embed this" snippet generator.

---

## 3. Directory structure

```
web-scrape/
├── pyproject.toml          # uv project; core pipeline is stdlib-only
├── .python-version         # pinned 3.11
├── targets.py              # declarative CDX harvest targets (qzone/qqshow/4399)
├── harvest.py              # CDX → manifest.jsonl  (resumeKey pagination)
├── download.py             # manifest → assets/    (live-first, retry+backoff)
├── analyze.py              # assets → analysis.jsonl  (pure-stdlib SWF parser)
├── ruffle-harness/         # Node + Playwright + self-hosted Ruffle
│   ├── package.json
│   ├── player.html         # minimal Ruffle host page
│   └── render.mjs          # headless render → data/ruffle.jsonl + screenshots
├── README.md               # usage
├── DESIGN.md               # this file
└── data/                   # gitignored — large + regenerable
    ├── manifest.jsonl      # one row/URL: original, timestamp, status, mime, digest, _target
    ├── assets/<host>/<path>...   # downloaded files
    ├── fetched.jsonl       # download log: source(live|wayback|cached|failed), sha256, valid_swf
    ├── analysis.jsonl      # per-SWF: as_version, classification, urls, tags, ruffle_confidence
    ├── ruffle.jsonl        # per-SWF: verdict(ok|blank|errors|failed), errors, screenshot
    └── screenshots/        # one PNG per rendered SWF (human review)
```

---

## 4. Key design decisions (and the bugs that shaped them)

**CDX pagination uses `resumeKey`, not `page`.** The obvious `page=`/`showNumPages` pagination *silently returns empty* for `matchType=prefix` (only works for `domain`/`host`), and `showNumPages` returns junk under `output=json`. The `resumeKey` scheme (`output=text` + `showResumeKey=true`) works for every match type. This was a real, silent foot-gun — worth remembering if you extend it.

**Live-CDN-first download.** Tencent/4399 are lazy about deleting old CDN files, so most assets come straight from origin at full fidelity (no Wayback HTML rewriting). When origin 404s, we fall back to Wayback's `…/<ts>id_/<url>` form — the `id_` modifier returns the *original bytes* with no archive wrapper, which is essential for binary SWFs. `--wayback-only` forces the historical version.

**Retry + backoff on the Wayback fallback.** Wayback throttles hard: 4 concurrent workers hammering it after live-404s caused connection resets (`URLError`) and a ~75% spurious failure rate. The fix: per-fetch exponential backoff (1/2/4/8s), retry on timeouts/429/5xx, and raise immediately on 404 (skip to fallback). Keep `--workers` low (3–4) for Wayback-heavy runs.

**Analyzer needs no Java.** Instead of requiring JPEXS/FFDec (which needs a JDK, not installed here), `analyze.py` parses the SWF format directly: decompress (FWS/CWS/ZWS), read the header (version, stage size, frame rate/count), then walk the tag stream. AS3 = presence of `DoABC`/`SymbolClass` tags; AS1/2 = `DoAction`/ `DoInitAction`. "Networked" = embedded `http(s)` URLs / Tencent CGI hosts found in the decompressed body. FFDec stays optional, only for deep asset *extraction*.

> ⚠️ The networked heuristic is deliberately broad (any URL ⇒ networked). Many
> 装扮 items embed a harmless click-through or asset URL but are functionally
> self-contained. Treat "networked" as "needs a human look," not "definitely
> server-dependent." Refining this (CGI/data-load URLs only) is a TODO.

**Render verdict is honest, not magic.** The Ruffle harness combines three
signals: did Ruffle's `load()` resolve, did it emit AS3 "unimplemented"/panic
console errors, and is the canvas non-blank (pixel-variance sample). Verdicts:
`ok` / `errors` / `blank` / `failed`. A screenshot is always saved for eyeballing
— the automated verdict narrows what a human reviews, it doesn't replace them.

---

## 5. What's scrapable (verified live, 2026-06)

| Source | State |
|--------|-------|
| `qzonestyle.gtimg.cn/qzone/space_item/boss_pic/` | ✅ The 装扮 item store — ~hundreds of per-item SWFs |
| `qzone.qq.com/item/orig/…` | ⚠️ Mostly gone from live CDN; recoverable via Wayback |
| `qzone.qq.com` (domain) | ✅ Thousands of SWFs (old `player.swf`, `top.swf`, widgets) |
| `imgcache.qq.com/ac/qqshow/…enginer_v_*.swf` | ✅ QQShow dress-up engine (v3–v8) |
| `sda.4399.com/4399swf/upload_swf/` | ✅ Huge — tens of thousands of game SWFs |
| `huateng.qzone.qq.com` (花藤's host) | ❌ **Not archived** (login-walled). 花藤 is the hard one. |
| Personal QZone profile pages | ❌ Login-gated → never crawled. We recover the *asset library*, not assembled pages. |

---

## 6. Don't reinvent — reuse map

| Area | Status | Action |
|------|--------|--------|
| **QQShow (QQ秀)** | Done well by **qqshow2000** (Kay Zeng) — React+Supabase, IA-sourced PNG/GIF assets composited in-browser | Reuse assets / collaborate. Their `uploadNewAssets.js` ingest is a reference pattern. |
| **QZone 装扮 / 花藤 / player** | **Open territory** — only personal-data exporters exist; 花藤 shut down Oct 2022 | This is our net-new contribution. |
| **4399 / games** | Flashpoint Archive curates 4399 (uncatalogued); `keuin/4399-flash-games` SWF dump | Reuse + Ruffle; harvest only gaps. |
| **闪客 / Flash animation** | `rwv/flash-archive-project` — hosted SWF CDN `flash-swf.zczc.cz/{sha256}.swf` + JSON metadata | Pull directly. |

**Tools:** JPEXS **FFDec** (decompile/extract, needs a JDK) · **Ruffle** (playback).
No Tencent-specific tooling exists — our normalization pipeline is the new part.

---

## 7. Environment

- **Python** via **uv** (`uv 0.8.x`), pinned to 3.11 in a project `.venv`. The
  core pipeline has *zero* runtime deps (stdlib only) — `uv sync` just gives a
  clean, reproducible env; `ruff` is the only (dev) dependency. Run anything with
  `uv run python <script>.py`.
- **Node** (v22) for the Ruffle harness: `cd ruffle-harness && npm run setup`
  (installs `@ruffle-rs/ruffle` + Playwright Chromium).
- **Java/FFDec**: not installed; not required for the current pipeline. Install a
  JDK only when you want deep SWF asset extraction (Path B reimplementation).

---

## 8. Open problems / roadmap

- **花藤** — its client assets aren't on Wayback (login-walled host). Need to
  find an app-bundle SWF elsewhere, or reconstruct from screenshots/video. This is the hardest single target and a flagship Path-B candidate.
- **Music player** — the UI SWF is recoverable, but audio streamed from now-dead, copyright-locked QQ Music URLs. Reimplement the *player UI* as data; supply your own audio. Don't rehost copyrighted tracks.
- **Networked-classification refinement** — narrow the heuristic to data/CGI loads (see §4 warning).
- **`--mime media` harvest** — many 装扮 items are PNG/GIF, not SWF. A full
  museum wants images + audio, not just Flash.
- **Museum frontend** — grid + tag/search + per-item Ruffle embed + "copy embed snippet" generator.
- **Provenance/legal** — this is non-commercial preservation (Webamp/Flashpoint posture). Keep it non-commercial, honor takedowns, never rehost music.
