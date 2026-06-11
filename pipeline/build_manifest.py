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
LIB = Path("web/library")

OUT_JSON = Path("data/catalog.json")
OUT_JS = Path("web/catalog.js")           # baked window.META for the museum (file://-safe)
PLAYER_THUMBS = Path("web/site/assets/player_gallery")
SWF_THUMBS = Path("data/screenshots")
SITE_INDEX = Path("web/site/library_index.js")  # atelier's already-curated good-skin allowlist


def good_skins():
    """The 939 non-blank skin ids the atelier already curated (pixel-variance filter)."""
    if not SITE_INDEX.exists():
        return None
    import re
    t = SITE_INDEX.read_text()
    m = re.search(r'"skin":\[(.*?)\](?=,"|\})', t, re.S)
    if not m:
        return None
    return set(re.findall(r'"id":"?(\d+)', m.group(1)))

# Tencent's tag/category vocab → facet buckets
TONE = {"冷色", "暖色", "黑白系", "黑白", "彩色", "黑色", "白色", "蓝色", "绿色",
        "紫色", "黄色", "红色", "粉色", "半透明", "不透明"}
AUDIENCE = {"男生", "女生", "男性", "女性", "情侣", "孩童", "宠物", "儿童",
            "男艺人", "女艺人", "人物"}
MOOD = {"快乐", "幸福", "浪漫", "伤感", "忧伤", "忧郁", "寂寞", "平静", "高兴",
        "生气", "奋斗", "另类", "整蛊", "搞笑", "酷炫", "可爱", "简洁", "时尚",
        "成熟", "古典", "青春", "商务", "忧郁"}
# Tencent's explicit 色系 words → our hue buckets (human-curated, trusted)
COLOR_TAG = {"红色": "red", "橙色": "orange", "黄色": "yellow", "绿色": "green",
             "青色": "cyan", "蓝色": "blue", "紫色": "purple", "粉色": "pink",
             "黑色": "black", "白色": "white"}

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


def thumb_path(typ, iid):
    """Web-root-relative URL of a browser-displayable thumbnail, or ''. Files live under web/."""
    if typ == "skin":
        for ext in ("jpg", "gif", "png"):
            if (LIB / "skin" / f"{iid}_top.{ext}").exists():
                return f"library/skin/{iid}_top.{ext}"
        for ext in ("jpg", "gif", "png"):
            if (LIB / "skin" / f"{iid}_bg.{ext}").exists():
                return f"library/skin/{iid}_bg.{ext}"
    elif typ == "pendant":
        if (LIB / "pendant" / f"{iid}.gif").exists():
            return f"library/pendant/{iid}.gif"
    elif typ == "floaty":
        if (LIB / "floaty" / f"{iid}_1.gif").exists():
            return f"library/floaty/{iid}_1.gif"
    elif typ == "cursor":
        if (LIB / "cursor_anim" / f"{iid}.png").exists():
            return f"library/cursor_anim/{iid}.png"
    elif typ == "titlebar":
        for ext in ("png", "gif", "jpg"):
            if (LIB / "titlebar" / f"{iid}.{ext}").exists():
                return f"library/titlebar/{iid}.{ext}"
    elif typ == "player":
        if (PLAYER_THUMBS / f"{iid}.png").exists():
            return f"site/assets/player_gallery/{iid}.png"
    elif typ == "swf":
        hits = list(SWF_THUMBS.glob(f"*_{iid}.swf.png"))
        if hits:
            return str(hits[0])
    return ""


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
    keep_skins = good_skins()
    out = []
    stats = Counter()
    have_meta = Counter()
    dropped_blank = 0

    for typ, idset in ids.items():
        for iid in sorted(idset, key=lambda x: int(x) if x.isdigit() else 0):
            if typ == "skin" and keep_skins is not None and iid not in keep_skins:
                dropped_blank += 1
                continue
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

            # HUES = pixel chromatic hues ∪ Tencent's explicit color tags.
            # white/gray/black is a LAST resort (only if nothing else found) — fixes
            # the "everything is white" inaccuracy.
            hues = list(c.get("hues", []))
            for src in (tags, cats):
                for tok in src:
                    h = COLOR_TAG.get(tok)
                    if h and h not in hues:
                        hues.append(h)
            if not hues and c.get("neutral"):
                hues = [c["neutral"]]

            rec = {
                "id": iid,
                "type": typ,
                "name": m.get("Fitem_name", ""),
                "date": date,
                "era": era,
                "price": m.get("Fprice", ""),
                "ext": m.get("Fdesc", ""),
                "color": c.get("color", ""),
                "hue": hues[0] if hues else "",
                "hues": hues,
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
                "thumb": thumb_path(typ, iid),
            }
            out.append(rec)
            stats[typ] += 1
            if m:
                have_meta[typ] += 1

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False))
    OUT_JS.write_text("window.META=" + json.dumps(out, ensure_ascii=False) + ";")

    print(f"dropped {dropped_blank} blank/placeholder skins (not in atelier allowlist)")
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
