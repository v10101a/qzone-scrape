#!/usr/bin/env python3
"""recover_items.py — recover 装扮 items by id from the mall catalogs.

Given a category's item-id list (from data/catalogs/, harvested out of the live
装扮商城 catalog `itemlist_<catid>_<page>_v5.json`), fetch each item's real asset
straight from Tencent's still-live CDN using the deterministic rule
`bucket = id % 16` → `orig/<bucket>/<id><suffix>`.

These item types are SELF-CONTAINED files (no Flash deps) — exactly what we want:
    cursor  (type 4) -> orig/<b>/<id>.ani      (RIFF animated cursor)
    pendant (type 2) -> orig/<b>/<id>.gif      (often animated GIF)
    floaty  (type 5) -> orig/<b>/<id>_2.gif

Saved to library/<type>/<id>.<ext> with a provenance manifest. Resumable.

Usage:
    uv run python recover_items.py cursor
    uv run python recover_items.py pendant --limit 200 --workers 6
    uv run python recover_items.py floaty
"""

import argparse
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

CDN = "https://qzonestyle.gtimg.cn/qzone/space_item/orig"
# Accept header that excludes webp so the CDN serves ORIGINAL gif/png (and keeps
# animated GIFs animated instead of flattening to webp).
HEADERS = {
    "User-Agent": "Mozilla/5.0 qzone-museum/0.1",
    "Accept": "image/gif,image/png,image/jpeg,application/octet-stream,*/*;q=0.3",
}

TYPES = {
    # type: (id-list filename, url-suffix builder, saved extension)
    "cursor":  ("FINAL_cursor_type4_ids.txt",  lambda i: f"{i}.ani",   "ani"),
    "pendant": ("FINAL_pendant_type2_ids.txt", lambda i: f"{i}.gif",   "gif"),
    "floaty":  ("FINAL_floaty_type5_ids.txt",  lambda i: f"{i}_2.gif", "gif"),
    # skin/floaty are special-cased in recover_one; url/ext unused for those
    "skin":    ("skin_ids.txt", None, None),
    "player":  ("player_ids.txt", lambda i: f"{i}.swf", "swf"),   # 音乐播放器 (type 6, flash)
}

_lock = threading.Lock()


def log(m):
    with _lock:
        print(m, flush=True)


def read_ids(path: Path):
    ids = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.isdigit():
            ids.append(int(line))
    return ids


def fetch(url: str, retries=3, timeout=30) -> bytes | None:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            return data if data else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None          # item genuinely absent — don't retry
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 ** attempt)
    return None


def recover_skin(item_id: int, outdir: Path):
    """A skin is a pair: <id>_top (masthead) + <id>_bg (tile). Try ext variants."""
    bucket = item_id % 16
    got = {}
    for part in ("top", "bg"):
        for ext in ("jpg", "gif", "png"):
            dest = outdir / f"{item_id}_{part}.{ext}"
            if dest.exists() and dest.stat().st_size > 0:
                got[part] = dest.name
                break
            data = fetch(f"{CDN}/{bucket}/{item_id}_{part}.{ext}")
            if data:
                dest.write_bytes(data)
                got[part] = dest.name
                break
    if "top" not in got:                       # no masthead => not a usable skin
        return {"id": item_id, "status": "miss"}
    return {"id": item_id, "status": "ok",
            "top": got.get("top"), "bg": got.get("bg")}


def recover_floaty(item_id: int, outdir: Path):
    """Floaty (type 5) has consecutive frames <id>_1.gif … <id>_N.gif. The snow
    engine assigns each sprite a random frame, so recover all of them."""
    bucket = item_id % 16
    frames = []
    for n in range(1, 13):
        dest = outdir / f"{item_id}_{n}.gif"
        if dest.exists() and dest.stat().st_size > 0:
            frames.append(n); continue
        data = fetch(f"{CDN}/{bucket}/{item_id}_{n}.gif")
        if not data:
            break                              # frames are consecutive
        dest.write_bytes(data); frames.append(n)
    if not frames:
        return {"id": item_id, "status": "miss"}
    return {"id": item_id, "status": "ok", "frames": frames,
            "animated": True}


def recover_one(item_type: str, item_id: int, outdir: Path):
    if item_type == "skin":
        return recover_skin(item_id, outdir)
    if item_type == "floaty":
        return recover_floaty(item_id, outdir)
    suffix_fn, ext = TYPES[item_type][1], TYPES[item_type][2]
    bucket = item_id % 16
    url = f"{CDN}/{bucket}/{suffix_fn(item_id)}"
    dest = outdir / f"{item_id}.{ext}"
    if dest.exists() and dest.stat().st_size > 0:
        return {"id": item_id, "status": "cached", "dest": str(dest)}
    data = fetch(url)
    if not data:
        return {"id": item_id, "status": "miss", "url": url}
    dest.write_bytes(data)
    return {
        "id": item_id, "status": "ok", "url": url, "dest": str(dest),
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()[:16],
        # GIF89a animation marker — quick heuristic for "is it moving"
        "animated": (ext == "gif" and data[:6] == b"GIF89a"
                     and data.count(b"\x21\xf9\x04") > 1),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("type", choices=list(TYPES))
    ap.add_argument("--catalogs", default="data/catalogs")
    ap.add_argument("--out", default="library")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    idfile = Path(args.catalogs) / TYPES[args.type][0]
    ids = read_ids(idfile)
    if args.limit:
        ids = ids[:args.limit]
    outdir = Path(args.out) / args.type
    outdir.mkdir(parents=True, exist_ok=True)
    log(f"Recovering {len(ids)} {args.type} item(s) -> {outdir}")

    results, counts, animated = [], {}, 0
    manifest = (outdir / "_manifest.jsonl").open("a")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(recover_one, args.type, i, outdir): i for i in ids}
        for n, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            if r.get("animated"):
                animated += 1
            if r["status"] in ("ok", "cached"):
                manifest.write(json.dumps(r, ensure_ascii=False) + "\n")
            if n % 100 == 0 or n == len(ids):
                log(f"  {n}/{len(ids)}  " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            time.sleep(0.03)
    manifest.close()
    got = counts.get("ok", 0) + counts.get("cached", 0)
    log(f"\nDone. recovered={got}  missing={counts.get('miss',0)}  "
        f"animated_gifs={animated}  -> {outdir}")


if __name__ == "__main__":
    main()
