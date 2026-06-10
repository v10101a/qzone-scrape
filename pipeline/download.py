#!/usr/bin/env python3
"""Downloader — fetch assets listed in a manifest, live-CDN-first.

For each manifest entry:
  1. Try the ORIGINAL url on the live CDN (Tencent/4399 are lazy about
     deleting old files — this is often still up and is the highest fidelity).
  2. On failure, fall back to the Wayback raw bytes:
       https://web.archive.org/web/<timestamp>id_/<original>
     The `id_` modifier returns the original file with NO Wayback HTML/JS
     rewriting — essential for binary SWFs.

Saved under data/assets/<host>/<path>; URLs with query strings get a short
hash suffix so variants don't collide. Resumable: existing files are skipped.
Results (source, sha256, bytes, swf-validity) are written to data/fetched.jsonl.

Examples:
    python3 download.py                              # download everything
    python3 download.py --manifest data/manifest.jsonl --workers 4
    python3 download.py --only qzonestyle            # only this _target
    python3 download.py --wayback-only               # skip live CDN attempt
    python3 download.py --limit 20                   # smoke-test first 20
"""

import argparse
import hashlib
import json
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) qzone-museum/0.1")
SWF_MAGIC = (b"FWS", b"CWS", b"ZWS")  # uncompressed / zlib / lzma

_print_lock = threading.Lock()


def log(msg: str):
    with _print_lock:
        print(msg, flush=True)


def local_path(root: Path, original: str) -> Path:
    """Map an original URL to a human-browsable local path."""
    u = urllib.parse.urlsplit(original)
    host = u.netloc.split(":")[0] or "_nohost"
    path = u.path.lstrip("/") or "index"
    if path.endswith("/"):
        path += "index"
    p = Path(path)
    if u.query:
        h = hashlib.sha1(u.query.encode()).hexdigest()[:8]
        p = p.with_name(f"{p.stem}__q{h}{p.suffix}")
    # Sanitize each path segment for the filesystem.
    safe = [seg.replace("..", "__") for seg in (host, *p.parts)]
    return root.joinpath(*safe)


class NotFound(Exception):
    """Permanent 404 — don't retry, fall through to the next source."""


def _fetch(url: str, timeout: int = 60, retries: int = 4) -> bytes:
    """GET with backoff. Retries transient failures (throttling, timeouts,
    429/5xx); raises NotFound immediately on 404 so callers skip to fallback."""
    import urllib.error
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if not data:
                raise RuntimeError("empty body")
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFound() from e
            last = e  # 429 / 5xx -> retry
        except Exception as e:  # noqa: BLE001 — URLError, timeouts, resets
            last = e
        time.sleep(min(2 ** attempt, 20))  # 1s, 2s, 4s, 8s
    raise last if last else RuntimeError("fetch failed")


def wayback_raw_url(original: str, timestamp: str) -> str:
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def fetch_one(rec: dict, root: Path, wayback_only: bool, delay: float) -> dict:
    original = rec["original"]
    dest = local_path(root, original)
    result = {"original": original, "dest": str(dest)}

    if dest.exists() and dest.stat().st_size > 0:
        result["source"] = "cached"
        return result

    data, source, err = None, None, None

    if not wayback_only:
        try:
            data = _fetch(original)
            source = "live"
        except Exception as e:  # noqa: BLE001
            err = f"live:{type(e).__name__}"

    if data is None:
        ts = rec.get("timestamp")
        if ts:
            try:
                data = _fetch(wayback_raw_url(original, ts))
                source = "wayback"
            except Exception as e:  # noqa: BLE001
                err = f"{err + '; ' if err else ''}wayback:{type(e).__name__}"

    if data is None:
        result["source"] = "failed"
        result["error"] = err
        time.sleep(delay)
        return result

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    result["source"] = source
    result["bytes"] = len(data)
    result["sha256"] = hashlib.sha256(data).hexdigest()
    if original.lower().split("?")[0].endswith(".swf"):
        result["valid_swf"] = data[:3] in SWF_MAGIC
    time.sleep(delay)
    return result


def load_manifest(path: Path, only: str | None, limit: int | None) -> list[dict]:
    recs = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if only and rec.get("_target") != only:
            continue
        recs.append(rec)
    if limit:
        recs = recs[:limit]
    return recs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="data/manifest.jsonl")
    ap.add_argument("--assets", default="data/assets", help="output root dir")
    ap.add_argument("--results", default="data/fetched.jsonl")
    ap.add_argument("--only", help="only download entries with this _target")
    ap.add_argument("--limit", type=int, help="cap number of entries (smoke test)")
    ap.add_argument("--workers", type=int, default=4,
                    help="concurrent downloads (default: 4 — be polite)")
    ap.add_argument("--delay", type=float, default=0.3,
                    help="per-task sleep after each fetch (default: 0.3s)")
    ap.add_argument("--wayback-only", action="store_true",
                    help="skip the live-CDN attempt, go straight to Wayback")
    args = ap.parse_args()

    manifest = Path(args.manifest)
    if not manifest.exists():
        raise SystemExit(f"No manifest at {manifest}. Run harvest.py first.")

    root = Path(args.assets)
    recs = load_manifest(manifest, args.only, args.limit)
    log(f"Downloading {len(recs)} asset(s) -> {root} "
        f"| workers={args.workers} | wayback_only={args.wayback_only}")

    results, counts = [], {}
    results_path = Path(args.results)
    results_path.parent.mkdir(parents=True, exist_ok=True)

    with results_path.open("a") as rf, \
            ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, r, root, args.wayback_only, args.delay): r
                for r in recs}
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            results.append(res)
            rf.write(json.dumps(res, ensure_ascii=False) + "\n")
            rf.flush()
            src = res.get("source", "?")
            counts[src] = counts.get(src, 0) + 1
            mark = {"live": "↓", "wayback": "⟲", "cached": "=",
                    "failed": "✗"}.get(src, "?")
            extra = ""
            if src in ("live", "wayback"):
                extra = f" {res['bytes']}B"
                if "valid_swf" in res:
                    extra += " swf:ok" if res["valid_swf"] else " swf:BAD"
            if src == "failed":
                extra = f" ({res.get('error')})"
            log(f"  [{i}/{len(recs)}] {mark} {res['original']}{extra}")

    log("\nSummary: " + " | ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    bad = [r for r in results if r.get("valid_swf") is False]
    if bad:
        log(f"⚠ {len(bad)} file(s) downloaded but failed SWF magic-byte check "
            f"(may be HTML error pages saved as .swf).")


if __name__ == "__main__":
    main()
