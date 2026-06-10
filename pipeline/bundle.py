#!/usr/bin/env python3
"""bundle.py — make SWFs self-contained by mirroring their external deps.

Reads a SWF analysis jsonl (paths + external `urls`), keeps only fetchable
Tencent-CDN dependencies (*.qq.com / *.gtimg.cn — for our 挂件 these are the
shared font SWFs), and downloads each into demo/bundle/mirror/<host>/<path>,
preserving the original URL structure.

A service worker (demo/bundle/sw.js) then serves these mirrored files in place of
the live/远程 originals, so Ruffle runs each SWF with ZERO live Tencent dependency
— the Flashpoint "replay archived deps at their original URLs" model, but as a
static, browser-native bundle hostable anywhere.

XMP-namespace URLs (adobe.com / w3.org / purl.org / ns.adobe.com) are skipped —
they're XML namespace identifiers in Flash metadata, not fetchable resources.

Usage:
    uv run python bundle.py                       # mirror deps from data/orig_analysis.jsonl
    uv run python bundle.py --analysis data/orig_analysis.jsonl
"""

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 qzone-museum/0.1"
CDX = "http://web.archive.org/cdx/search/cdx"
SKIP_HOSTS = ("adobe.com", "ns.adobe.com", "www.w3.org", "purl.org")


def is_dep(url: str) -> bool:
    try:
        h = urllib.parse.urlsplit(url).netloc.lower()
    except ValueError:
        return False
    if any(s in url for s in SKIP_HOSTS):
        return False
    return h.endswith(".qq.com") or h.endswith(".gtimg.cn")


def collect_deps(analysis: Path) -> set[str]:
    deps = set()
    for line in analysis.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        for u in rec.get("urls", []):
            u = u.split("#")[0]
            if is_dep(u):
                deps.add(u)
    return deps


def _get(url: str, timeout=30) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = r.read()
        return d or None
    except Exception:  # noqa: BLE001
        return None


def wayback_latest(url: str) -> bytes | None:
    """Fallback: newest archived copy of the URL via CDX -> id_ replay."""
    q = (f"{CDX}?url={urllib.parse.quote(url, safe='')}"
         f"&filter=statuscode:200&output=text&fl=timestamp&limit=-1")
    txt = _get(q)
    if not txt:
        return None
    ts = txt.decode().strip().splitlines()
    if not ts:
        return None
    return _get(f"https://web.archive.org/web/{ts[-1]}id_/{url}")


def mirror_path(root: Path, url: str) -> Path:
    u = urllib.parse.urlsplit(url)
    host = u.netloc.split(":")[0]
    path = u.path.lstrip("/")
    return root / host / path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", default="data/orig_analysis.jsonl")
    ap.add_argument("--out", default="demo/bundle/mirror")
    ap.add_argument("--deps-json", default="demo/bundle/deps.json")
    args = ap.parse_args()

    deps = sorted(collect_deps(Path(args.analysis)))
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    print(f"{len(deps)} unique external dependency URL(s) to mirror\n")

    records = []
    for i, url in enumerate(deps, 1):
        dest = mirror_path(root, url)
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  [{i}/{len(deps)}] = {url}")
            records.append({"url": url, "status": "cached", "local": str(dest)})
            continue
        data = _get(url)
        src = "live"
        if not data:
            data = wayback_latest(url)
            src = "wayback"
        if not data:
            print(f"  [{i}/{len(deps)}] ✗ {url}")
            records.append({"url": url, "status": "failed"})
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f"  [{i}/{len(deps)}] ↓ {src} {len(data)}B {url}")
        records.append({"url": url, "status": src, "local": str(dest),
                        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()[:16]})
        time.sleep(0.1)

    Path(args.deps_json).write_text(json.dumps(records, indent=2, ensure_ascii=False))
    ok = sum(1 for r in records if r["status"] in ("live", "wayback", "cached"))
    print(f"\nMirrored {ok}/{len(deps)} deps -> {root}\nManifest -> {args.deps_json}")


if __name__ == "__main__":
    main()
