#!/usr/bin/env python3
"""harvest_catalog.py — pull item-ids from 装扮商城 itemlist catalogs.

Fetches `imgcache.qq.com/qzone/mall/static/json/itemlist_<cat>_<page>_v5.json`
(GBK JSONP) for each category, page by page until a 404 / empty page, parses the
top-level item records (Fitem_id + its Ftype_id), and writes a deduped id list.

Nested `suitItems` (in 套装 categories) are ignored — only each record's own
top-level Fitem_id is taken, optionally filtered to a single Ftype_id.

Usage:
    uv run python harvest_catalog.py --cats 12 248 305 11 309 310 311 374 \
        --type 1 --maxpages 6 -o data/catalogs/skin_ids.txt
"""

import argparse
import re
import time
import urllib.request
from pathlib import Path

CDN = "https://imgcache.qq.com/qzone/mall/static/json"
REC = re.compile(r"Fitem_id:'(\d+)'.*?Ftype_id:'(\d+)'", re.S)


def _get(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status != 200:
                return None
            data = r.read()
        if data[:2] == b"\x1f\x8b":          # gzip — the CDN serves these compressed
            import gzip
            data = gzip.decompress(data)
        return data.decode("gbk", "replace")
    except Exception:  # noqa: BLE001
        return None


def fetch_page(cat: int, page: int) -> str | None:
    # v5 is the common version; a few categories only exist as v3
    for ver in ("v5", "v3"):
        txt = _get(f"{CDN}/itemlist_{cat}_{page}_{ver}.json")
        if txt and "Fitem_id" in txt:
            return txt
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cats", nargs="+", type=int, required=True)
    ap.add_argument("--type", type=int, help="keep only this Ftype_id")
    ap.add_argument("--maxpages", type=int, default=60)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--delay", type=float, default=0.2)
    args = ap.parse_args()

    found: dict[int, int] = {}   # id -> type (dedupe, first wins)
    for cat in args.cats:
        got = 0
        for page in range(1, args.maxpages + 1):
            txt = fetch_page(cat, page)
            if not txt or "Fitem_id" not in txt:
                break
            recs = REC.findall(txt)
            if not recs:
                break
            for iid, typ in recs:
                iid, typ = int(iid), int(typ)
                if args.type and typ != args.type:
                    continue
                found.setdefault(iid, typ)
                got += 1
            time.sleep(args.delay)
        print(f"  cat {cat}: scanned, running unique total {len(found)} (this cat +{got})")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(str(i) for i in sorted(found)) + "\n")
    print(f"\n{len(found)} unique ids -> {out}")


if __name__ == "__main__":
    main()
