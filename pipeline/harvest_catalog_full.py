#!/usr/bin/env python3
"""harvest_catalog_full.py — recover the FULL 装扮商城 catalog metadata.

The original harvest_catalog.py kept only (Fitem_id, Ftype_id) and threw the rest
away. But Tencent's itemlist JSON (still live on imgcache.qq.com) carries the whole
record per item:

    Fitem_id, Fitem_name (中文名), Fupload_time (exact date), Fitem_tag (色系+主题+性别),
    Ftype_id, Fdesc (asset ext), Fprice / Fvip_price, Fitem_remark (套装 piece list)

This sweeps every category in data/catalogs/category_map.txt, page by page, parses
the full record for each item, and merges into a master id->record map. It ALSO
records which categories each id appeared in (category names ARE a curated taxonomy:
themes 爱情/动漫/四季/校园, colors 黑/白/蓝/绿..., moods 高兴/忧伤/寂寞, audience 男性/女性/情侣).

Output:
    data/catalogs/catalog_meta.jsonl   — one JSON record per unique item id
    data/catalogs/cat_names.json       — {catid: 中文名} from the map file

Usage:
    uv run python harvest_catalog_full.py                  # sweep all cats
    uv run python harvest_catalog_full.py --maxpages 60    # server caps at 60 anyway
"""

import argparse
import gzip
import json
import re
import time
import urllib.request
from pathlib import Path

CDN = "https://imgcache.qq.com/qzone/mall/static/json"
CATMAP = Path("data/catalogs/category_map.txt")
OUT_META = Path("data/catalogs/catalog_meta.jsonl")
OUT_CATNAMES = Path("data/catalogs/cat_names.json")

# split the data:[ ... ] body into individual {...} records
REC_SPLIT = re.compile(r"\},\s*\{")
# every field is  Fkey:'value'  — values rarely contain a single quote
FIELD = re.compile(r"F(\w+):'((?:[^']|'(?![,}\s]))*)'")


def _get(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            if r.status != 200:
                return None
            data = r.read()
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        return data.decode("gbk", "replace")
    except Exception:  # noqa: BLE001
        return None


def fetch_page(cat: int, page: int) -> str | None:
    for ver in ("v5", "v3"):
        txt = _get(f"{CDN}/itemlist_{cat}_{page}_{ver}.json")
        if txt and "Fitem_id" in txt:
            return txt
    return None


def parse_records(txt: str) -> list[dict]:
    body = txt[txt.find("data:[") :]
    out = []
    for chunk in REC_SPLIT.split(body):
        fields = {f"F{k}": v for k, v in FIELD.findall(chunk)}
        if "Fitem_id" in fields:
            out.append(fields)
    return out


def load_catmap() -> list[dict]:
    """Parse category_map.txt rows: catid name totalpage pmallid hastype ..."""
    rows = []
    for line in CATMAP.read_text().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            cid, name, total = int(parts[0]), parts[1], int(parts[2])
        except ValueError:
            continue
        pmallid = parts[3] if len(parts) > 3 else ""
        hastype = [t for t in (parts[4].split("|") if len(parts) > 4 else []) if t]
        rows.append({"cid": cid, "name": name, "total": total,
                     "pmallid": pmallid, "hastype": hastype})
    return rows


KEEP = ("Fitem_id", "Fitem_name", "Ftype_id", "Fupload_time", "Fdesc",
        "Fitem_tag", "Fprice", "Fvip_price", "Fitem_remark")


def sweep_cat(cat: dict, maxpages: int, delay: float):
    """Page through one category until empty; return (cid, [records])."""
    recs = []
    pages = min(maxpages, max(cat["total"], 1))
    for page in range(1, pages + 1):
        txt = fetch_page(cat["cid"], page)
        if not txt:
            break
        rs = parse_records(txt)
        if not rs:
            break
        recs.extend(rs)
        time.sleep(delay)
    return cat["cid"], recs


def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ap = argparse.ArgumentParser()
    ap.add_argument("--maxpages", type=int, default=60)
    ap.add_argument("--delay", type=float, default=0.15)
    ap.add_argument("--workers", type=int, default=8)
    # types we hold assets for: 1 skin, 2 pendant, 3/19 titlebar/banner,
    # 4 cursor, 5 floaty, 6 player (13 nav, 14 intro, 16 frame optional)
    ap.add_argument("--types", nargs="+", default=["1", "2", "3", "4", "5", "6", "19"])
    ap.add_argument("--include-suits", action="store_true",
                    help="also sweep 套装 bundle categories (pmallid 280)")
    args = ap.parse_args()

    rows = load_catmap()
    cat_names = {str(r["cid"]): r["name"] for r in rows}
    OUT_CATNAMES.parent.mkdir(parents=True, exist_ok=True)
    OUT_CATNAMES.write_text(json.dumps(cat_names, ensure_ascii=False, indent=0))

    # pick only categories that contain a type we have assets for
    want = set(args.types)
    todo = []
    for r in rows:
        if not args.include_suits and r["pmallid"] == "280":
            continue
        if r["hastype"] and want.intersection(r["hastype"]):
            todo.append(r)
    print(f"sweeping {len(todo)} categories for types {sorted(want)} "
          f"with {args.workers} workers")

    meta: dict[str, dict] = {}
    cats_of: dict[str, set] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(sweep_cat, c, args.maxpages, args.delay): c for c in todo}
        for fut in as_completed(futs):
            cid, recs = fut.result()
            for rec in recs:
                iid = rec["Fitem_id"]
                slim = {k: rec.get(k, "") for k in KEEP}
                if iid not in meta:
                    meta[iid] = slim
                else:
                    for k, v in slim.items():
                        if v and not meta[iid].get(k):
                            meta[iid][k] = v
                cats_of.setdefault(iid, set()).add(cid)
            done += 1
            c = futs[fut]
            print(f"  [{done:>3}/{len(todo)}] cat {cid:>4} {c['name']:<10} "
                  f"+{len(recs):<5} unique total {len(meta)}")

    with OUT_META.open("w") as f:
        for iid, rec in sorted(meta.items(), key=lambda kv: int(kv[0])):
            rec = dict(rec)
            rec["cats"] = sorted(cats_of.get(iid, []))
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n{len(meta)} unique items -> {OUT_META}")
    print(f"cat names -> {OUT_CATNAMES}")


if __name__ == "__main__":
    main()
