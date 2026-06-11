# QZone preservation harvester

Tooling to scrape archived Flash + asset files + archive for QZone decoration assets

[link to preview](https://v10101a.github.io/qzone-scrape/museum/)

## Harvesting pipeline

1. **`pipeline/harvest.py`** — query the Wayback CDX API → a deduped JSONL
   **manifest** of every archived asset URL + its best snapshot timestamp.
2. **`pipeline/download.py`** — fetch each asset, **live CDN first** (often still
   up), falling back to Wayback raw bytes (`id_/` = no HTML rewriting). Validates
   SWF magic bytes, content-addresses, skips already-downloaded files.

## Targets

Defined in `targets.py`. Groups: `qzone`, `qqshow`, `4399`, `all` or single target name (e.g. `qzonestyle`, `4399-sda`).
