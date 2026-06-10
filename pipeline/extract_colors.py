#!/usr/bin/env python3
"""extract_colors.py — dominant color + hue bucket + animated flag per asset.

Walks the on-disk library and, for every image-backed item, computes:
    color    : a representative hex (#rrggbb) for the visual swatch strip
    hue      : a coarse bucket  (red/orange/yellow/green/cyan/blue/purple/pink
               or neutral black/white/gray/brown) for faceted filtering
    animated : bool (GIF/APNG with >1 frame; floaty are inherently animated)
    w, h     : pixel dims

Method: thumbnail to 48px, keep opaque pixels, build an HSV histogram over the
*chromatic* pixels (decent saturation+value); the dominant hue bin wins. If too
few chromatic pixels, classify as a neutral by average lightness. The swatch hex
is the average of the pixels in the winning bin (vivid, not muddy).

Output: data/catalogs/colors.json  -> { "<type>:<id>": {color,hue,animated,w,h} }

Usage:  uv run python extract_colors.py
"""

import colorsys
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

LIB = Path("library")
OUT = Path("data/catalogs/colors.json")

# (type, dir, how to find the representative file for an id)
def skin_file(d, iid):
    for ext in ("jpg", "gif", "png"):
        p = d / f"{iid}_top.{ext}"
        if p.exists():
            return p
    for ext in ("jpg", "gif", "png"):
        p = d / f"{iid}_bg.{ext}"
        if p.exists():
            return p
    return None


HUE_BINS = [
    (345, 360, "red"), (0, 15, "red"), (15, 40, "orange"), (40, 65, "yellow"),
    (65, 160, "green"), (160, 195, "cyan"), (195, 250, "blue"),
    (250, 290, "purple"), (290, 345, "pink"),
]


def hue_name(h_deg):
    for lo, hi, name in HUE_BINS:
        if lo <= h_deg < hi:
            return name
    return "red"


def analyze(path: Path, force_anim=False):
    try:
        im = Image.open(path)
        w, h = im.size
        animated = force_anim or getattr(im, "n_frames", 1) > 1
        im = im.convert("RGBA")
        im.thumbnail((48, 48))
        px = list(im.getdata())
    except Exception:  # noqa: BLE001
        return None

    # Lower the saturation bar so pastels/light-but-colorful items count as a
    # real hue instead of falling into "white". white/gray/black is a LAST resort
    # (only when an item has essentially no chromatic pixels).
    chroma = defaultdict(list)   # hue_name -> [(r,g,b), ...]
    neutral = []                 # value of low-sat opaque pixels
    for r, g, b, a in px:
        if a < 160:
            continue
        hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if ss >= 0.14 and 0.12 <= vv <= 0.98:
            chroma[hue_name(hh * 360)].append((r, g, b))
        else:
            neutral.append(vv)

    total_op = sum(len(v) for v in chroma.values()) + len(neutral)
    if total_op == 0:
        return {"color": "#000000", "hues": [], "neutral": "black",
                "animated": animated, "w": w, "h": h}

    chroma_count = sum(len(v) for v in chroma.values())
    hues, color = [], ""
    if chroma_count >= 0.06 * total_op and chroma:
        # every hue bin holding >=18% of the chromatic pixels is a "present" color
        ranked = sorted(chroma.items(), key=lambda kv: len(kv[1]), reverse=True)
        for name, pts in ranked:
            if len(pts) >= 0.18 * chroma_count and len(hues) < 3:
                hues.append(name)
        if not hues:
            hues = [ranked[0][0]]
        top = dict(chroma)[hues[0]]
        avg = tuple(round(sum(c[i] for c in top) / len(top)) for i in range(3))
        color = "#%02x%02x%02x" % avg

    # neutral classification (used as fallback when no chromatic hue)
    v = sum(neutral) / len(neutral) if neutral else 0
    neutral_name = "black" if v < 0.25 else "white" if v > 0.80 else "gray"
    if not color:
        g = round(v * 255)
        color = "#%02x%02x%02x" % (g, g, g)
    return {"color": color, "hues": hues, "neutral": neutral_name,
            "animated": animated, "w": w, "h": h}


def main():
    out = {}
    counts = defaultdict(int)

    def add(typ, iid, path, force_anim=False):
        res = analyze(path, force_anim)
        if res:
            out[f"{typ}:{iid}"] = res
            counts[typ] += 1

    # skin: _top banner (fallback _bg)
    d = LIB / "skin"
    seen = set()
    for p in d.glob("*_top.*"):
        seen.add(p.name.split("_")[0])
    for p in d.glob("*_bg.*"):
        seen.add(p.name.split("_")[0])
    for iid in seen:
        f = skin_file(d, iid)
        if f:
            add("skin", iid, f)

    # pendant: <id>.gif
    for p in (LIB / "pendant").glob("*.gif"):
        add("pendant", p.stem, p, force_anim=True)

    # floaty: first frame <id>_1.gif (inherently animated set)
    d = LIB / "floaty"
    fids = sorted({p.name.split("_")[0] for p in d.glob("*_*.gif")})
    for iid in fids:
        f = d / f"{iid}_1.gif"
        if f.exists():
            add("floaty", iid, f, force_anim=True)

    # cursor: APNG render in cursor_anim/<id>.png
    for p in (LIB / "cursor_anim").glob("*.png"):
        add("cursor", p.stem, p)

    # titlebar: <id>.<ext>
    for p in (LIB / "titlebar").iterdir():
        if p.suffix.lower() in (".gif", ".png", ".jpg"):
            add("titlebar", p.stem, p, force_anim=(p.suffix.lower() == ".gif"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print("colors extracted:", dict(counts), "total", len(out), "->", OUT)


if __name__ == "__main__":
    main()
