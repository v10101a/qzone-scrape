#!/usr/bin/env python3
"""build_manifest.py — fuse on-disk assets + catalog metadata + colors into ONE manifest.

This is the single source of truth the museum (and, later, the atelier) reads. For
every item we actually have an asset for, it emits a normalized record:

    { id, type, name, date, era, price,
      color, hue, animated, w, h,        # from extract_colors.py
      tone, audience, mood, themes,      # parsed from Tencent's Fitem_tag + categories
      tags, cats,                        # raw Tencent tag tokens / category 中文名s
      ext, src }                         # asset ext + live-CDN source url

Inputs:
    data/catalogs/colors.json        (type:id -> color/hue/animated/w/h)
    data/catalogs/catalog_meta.jsonl (id -> Fitem_name/Fupload_time/Fitem_tag/...)
    data/catalogs/cat_names.json     (catid -> 中文名)

Outputs:
    data/catalog.json    canonical
    demo/catalog.js      window.META baked for file:// use

Usage:  uv run python build_manifest.py
"""

import json
from collections import Counter
from pathlib import Path

COLORS = Path("data/catalogs/colors.json")
META = Path("data/catalogs/catalog_meta.jsonl")
CATNAMES = Path("data/catalogs/cat_names.json")
LIB = Path("library")

OUT_JSON = Path("data/catalog.json")
OUT_JS = Path("demo/catalog.js")

# Tencent's tag/category vocab → facet buckets
TONE = {"冷色", "暖色", "黑白系", "黑白", "彩色", "黑色", "白色", "蓝色", "绿色",
        "紫色", "黄色", "红色", "粉色", "半透明", "不透明"}
AUDIENCE = {"男生", "女生", "男性", "女性", "情侣", "孩童", "宠物", "儿童",
            "男艺人", "女艺人", "人物"}
MOOD = {"快乐", "幸福", "浪漫", "伤感", "忧伤", "忧郁", "寂寞", "平静", "高兴",
        "生气", "奋斗", "另类", "整蛊", "搞笑", "酷炫", "可爱", "简洁", "时尚",
        "成熟", "古典", "青春", "商务", "忧郁"}

# bucket id -> our museum type (mirrors the library/ dir layout)
TYPE_DIRS = ["skin", "pendant", "floaty", "cursor", "titlebar", "player"]

CDN = "https://qzonestyle.gtimg.cn/qzone/space_item/orig"


def src_url(typ, iid, ext):
    b = int(iid) % 16
    if typ == "skin":
        return f"{CDN}/{b}/{iid}_top.{ext or 'jpg'}"
    if typ == "cursor":
        return f"{CDN}/{b}/{iid}.ani"
    if typ in ("pendant", "player", "swf"):
        suf = "swf" if typ in ("player", "swf") else (ext or "gif")
        return f"{CDN}/{b}/{iid}.{suf}"
    if typ == "floaty":
        return f"{CDN}/{b}/{iid}_2.{ext or 'gif'}"
    if typ == "titlebar":
        return f"{CDN}/{b}/{iid}.{ext or 'gif'}"
    return f"{CDN}/{b}/{iid}"


def disk_ids():
    """type -> set(id) for everything we actually have an asset for."""
    ids = {t: set() for t in TYPE_DIRS + ["swf"]}
    for p in (LIB / "skin").glob("*_top.*"):
        ids["skin"].add(p.name.split("_")[0])
    for p in (LIB / "skin").glob("*_bg.*"):
        ids["skin"].add(p.name.split("_")[0])
    for p in (LIB / "pendant").glob("*.gif"):
        ids["pendant"].add(p.stem)
    for p in (LIB / "floaty").glob("*_*.gif"):
        ids["floaty"].add(p.name.split("_")[0])
    for p in (LIB / "cursor").glob("*.ani"):
        ids["cursor"].add(p.stem)
    for p in (LIB / "titlebar").iterdir():
        if p.suffix.lower() in (".gif", ".png", ".jpg"):
            ids["titlebar"].add(p.stem)
    for p in (LIB / "player").glob("*.swf"):
        ids["player"].add(p.stem)
    for p in (LIB / "swf").glob("*.swf"):
        ids["swf"].add(p.stem)
    return ids


def main():
    colors = json.loads(COLORS.read_text()) if COLORS.exists() else {}
    catnames = json.loads(CATNAMES.read_text()) if CATNAMES.exists() else {}
    meta = {}
    if META.exists():
        for line in META.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                meta[r["Fitem_id"]] = r

    ids = disk_ids()
    out = []
    stats = Counter()
    have_meta = Counter()

    for typ, idset in ids.items():
        for iid in sorted(idset, key=lambda x: int(x) if x.isdigit() else 0):
            m = meta.get(iid, {})
            c = colors.get(f"{typ}:{iid}", {})
            tags = [t for t in (m.get("Fitem_tag") or "").split() if t]
            cats = [catnames.get(str(cid), str(cid)) for cid in m.get("cats", [])]
            date = m.get("Fupload_time", "") or ""
            era = date[:4] if date[:4].isdigit() else ""

            tone = [t for t in tags if t in TONE]
            audience = [t for t in tags if t in AUDIENCE]
            mood = [t for t in tags if t in MOOD]
            themes = [t for t in tags if t not in TONE and t not in AUDIENCE and t not in MOOD]
            # enrich themes/tone/audience from category names too
            for cn in cats:
                if cn in TONE and cn not in tone:
                    tone.append(cn)
                elif cn in AUDIENCE and cn not in audience:
                    audience.append(cn)
                elif cn in MOOD and cn not in mood:
                    mood.append(cn)

            rec = {
                "id": iid,
                "type": typ,
                "name": m.get("Fitem_name", ""),
                "date": date,
                "era": era,
                "price": m.get("Fprice", ""),
                "ext": m.get("Fdesc", ""),
                "color": c.get("color", ""),
                "hue": c.get("hue", ""),
                "animated": c.get("animated", False),
                "w": c.get("w", 0),
                "h": c.get("h", 0),
                "tone": tone,
                "audience": audience,
                "mood": mood,
                "themes": themes,
                "tags": tags,
                "cats": cats,
                "src": src_url(typ, iid, m.get("Fdesc", "")),
            }
            out.append(rec)
            stats[typ] += 1
            if m:
                have_meta[typ] += 1

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False))
    OUT_JS.write_text("window.META=" + json.dumps(out, ensure_ascii=False) + ";")

    print("items per type:", dict(stats))
    print("with catalog metadata:", dict(have_meta))
    total = sum(stats.values())
    named = sum(1 for r in out if r["name"])
    colored = sum(1 for r in out if r["color"])
    print(f"total {total} | named {named} ({100*named//max(total,1)}%) | "
          f"colored {colored} ({100*colored//max(total,1)}%)")
    print("->", OUT_JSON, "and", OUT_JS)


if __name__ == "__main__":
    main()
