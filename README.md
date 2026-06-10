# QZone / QQShow preservation harvester

Tooling to scrape archived Flash + asset files for a **QQ空间装扮 museum** (and
sister 4399 / QQShow archives), in the spirit of the Winamp Skin Museum / Webamp.

## Project layout

```
pipeline/    harvesting + processing scripts (stdlib-only, resumable)
data/        manifests, catalogs, downloaded asset working set
library/     the curated asset archive served by the site (skins, players, cursors, …)
site/        the museum web app  →  open site/index.html
qq-player-poc/  separate effort: a Webamp-style JS reimplementation of the QQ player
archive/     dev screenshots + old prototypes, kept out of the way
```

Run the museum: serve the repo and open `site/index.html` (e.g. VS Code Live
Server, or `python3 -m http.server` then visit `/site/`). HTTP is required (the
service worker that mirrors Tencent CDN deps only runs over http).

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

## Notes

- **Live-first is a feature.** Tencent/4399 rarely purge old CDN files, so most assets come straight from origin at full fidelity. `--wayback-only` forces the archive path if origin is gone or you want the historical byte-exact version.
- **`valid_swf:BAD`** in the log = the bytes weren't a real SWF (often an HTML
  error page saved with a `.swf` name). Filter these out before processing.
- **Be polite.** Defaults are 4 workers + small delays. Wayback throttles hard; don't crank `--workers` high or you'll get rate-limited (429).
- **Login-walled content is unreachable.** Personal QZone profile pages were
  behind login → never crawled. We recover the *asset library*, not assembled
  personal pages.

## Status

Built: harvesting + download pipeline, SWF triage (`pipeline/analyze.py`), the
Ruffle render harness (`ruffle-harness/`), and the museum frontend (`site/` —
grid + search + live dress-up preview).

In progress: `qq-player-poc/` — a Webamp-style JS reimplementation of the QQ
music player that still renders the original Flash skins (see its README).
