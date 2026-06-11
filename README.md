# QZone preservation harvester

Tooling to scrape archived Flash + asset files for a **QQ空间装扮 museum**, in the spirit of the Winamp Skin Museum / Webamp.

Live at [qzone2000.com](https://qzone2000.com) — the museum at `/`, the
dress-up-your-own-QZone app at `/site/`.

## Project layout

```
pipeline/    harvesting + processing scripts (stdlib-only, resumable)
data/        manifests, catalogs, downloaded asset working set
web/         everything that gets deployed — this directory is the web root
  index.html   the museum (web archive that displays assets)
  site/        the make-your-own-QZone app
  library/     the curated asset archive both pages serve
qq-player-poc/  a Webamp-style JS reimplementation of the QQ player (WIP)
```

The museum and `site/` are two web surfaces over one dataset. Serve the web
root (`python3 -m http.server -d web`) and visit `/` or `/site/` (http required).

## The catalog (`data/catalog.json` → baked into `web/catalog.js`)

One normalized record per item — the single source of truth the museum reads:
`id, type, name (中文), date, era, price, color (#hex), hue, animated, w/h,
tone/audience/mood/themes (from Tencent's Fitem_tag + categories), cats, src
(live CDN url), thumb`. Rebuilt by three pipeline steps:

```bash
python3 pipeline/harvest_catalog_full.py   # mall itemlist JSON → data/catalogs/catalog_meta.jsonl
                                           #   (full records: name, upload date, tags) for the types we hold
python3 pipeline/extract_colors.py         # Pillow → dominant hex + hue bucket + animated flag, per asset
python3 pipeline/build_manifest.py         # join disk assets + metadata + colors → catalog.json + web/catalog.js
```

Coverage of the 5,992 on-disk items: **98% real names, 95% colors, ~100%
thumbnails**, spanning 2005–2009. Tencent's theme/mood tags are dense on ~2009
items, sparse on 2005–2007 (which still carry name + date + color).

## Harvesting pipeline

Two stages, stdlib-only (no `pip install` needed), both resumable:

1. **`pipeline/harvest.py`** — query the Wayback CDX API → a deduped JSONL
   **manifest** of every archived asset URL + its best snapshot timestamp.
2. **`pipeline/download.py`** — fetch each asset, **live CDN first** (often still
   up), falling back to Wayback raw bytes (`id_/` = no HTML rewriting). Validates
   SWF magic bytes, content-addresses, skips already-downloaded files.

```bash
# 1. Build a manifest of QZone SWFs (themes/装扮, players, widgets)
python3 pipeline/harvest.py qzone --mime swf

# 2. Smoke-test the downloader on the first 20 before committing to the full run
python3 pipeline/download.py --limit 20

# 3. Full download
python3 pipeline/download.py
```

## Targets

Defined in `targets.py`. Groups: `qzone`, `qqshow`, `4399`, `all`. You can also
pass a single target name (e.g. `qzonestyle`, `4399-sda`).

```bash
python3 pipeline/harvest.py qqshow --mime all   # QQShow engine + every mimetype
python3 pipeline/harvest.py 4399-sda            # just the big 4399 game CDN
python3 pipeline/harvest.py all --mime media    # SWF + image + audio, everything
```

## Mime presets (`--mime`)

| preset  | matches                                   |
|---------|-------------------------------------------|
| `swf`   | Flash only (default)                      |
| `image` | all images                                |
| `audio` | audio + ogg                               |
| `media` | swf + image + audio (good for a museum)   |
| `all`   | no mime filter                            |

## Output layout

```
data/
  manifest.jsonl    # one row per unique URL: original, timestamp, status, mime, digest, length, _target
  assets/<host>/<path>...   # downloaded files, query-string variants get __q<hash> suffix
  fetched.jsonl     # download log: source (live|wayback|cached|failed), sha256, bytes, valid_swf
```