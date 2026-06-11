"""Harvest targets for the QZone / QQShow preservation project.

Each target describes a query against the Wayback CDX API. `url` + `match`
map directly to the CDX `url=` and `matchType=` params:

  - match="domain"  -> the host and ALL its subdomains
  - match="host"    -> exactly this host
  - match="prefix"  -> every URL beginning with this path
  - match="exact"   -> this one URL

Notes on what lives where (from live CDX probing, 2026-06):
  - qzonestyle.gtimg.cn  : main QZone "style" CDN — themes/装扮, widgets, players
  - imgcache.qq.com      : QQShow (QQ秀) dress-up engine + avatar assets
  - qzs.qq.com / qzonestyle... : newer QZone static hosts
  - sda/sxiao.4399.com   : 4399 Flash game SWFs (kept here for cross-project use)

Add/trim freely. Keep groups small so a failed harvest is cheap to retry.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Target:
    name: str                 # short slug, used in filenames/logs
    url: str                  # CDX url= value
    match: str = "domain"     # domain | host | prefix | exact
    note: str = ""
    # Extra CDX field filters, e.g. ["statuscode:200"]. Mime filter is added
    # separately by the harvester so you can switch SWF-only vs. all-assets.
    filters: tuple = field(default_factory=tuple)


# --- QZone 装扮 / widgets -------------------------------------------------
QZONE = [
    Target("qzonestyle", "qzonestyle.gtimg.cn", "domain",
           "Primary QZone style CDN: themes/装扮, music player, widgets"),
    Target("qzs", "qzs.qq.com", "domain",
           "Newer QZone static host"),
    Target("qzonestyle-qzone", "qzonestyle.gtimg.cn/qzone", "prefix",
           "QZone-specific subtree (decorations, app widgets)"),
    Target("qzonestyle-aoi", "qzonestyle.gtimg.cn/aoi", "prefix",
           "AOI subtree — observed to hold standalone .swf widgets"),
    # --- the actual 装扮 item library (confirmed via CDX, 2026-06) ---
    Target("qzonestyle-space-item", "qzonestyle.gtimg.cn/qzone/space_item", "prefix",
           "QZone 装扮 item store: per-item .swf (boss_pic/<pkg>/<id>.swf)"),
    Target("qzone-item", "qzone.qq.com/item", "prefix",
           "Legacy 装扮 items by numeric id (item/orig/0/<id>.swf)"),
    Target("qzone-web", "qzone.qq.com/web", "prefix",
           "Early QZone chrome: player.swf, top.swf, ad/register widgets"),
    Target("qzone-orig", "qzonestyle.gtimg.cn/qzone/space_item/orig", "prefix",
           "REAL 装扮 item library: 挂件(swf), skins(_bg/_top), frame folders(css+png), cursors(.ani)"),
    Target("qzone-qq", "qzone.qq.com", "domain",
           "Whole qzone.qq.com — LARGE (~thousands of SWFs); use for deep sweeps"),
]

# --- QQShow (QQ秀) dress-up ----------------------------------------------
# The per-item ARTWORK (the layered avatar GIFs) lives on its OWN host,
# qqshow-item.qq.com, NOT under imgcache. URL shape (verified 2026-06 via CDX):
#   qqshow-item.qq.com/<id>/<layer>/<frame>/[cache.gif]
#   - <id>    : item id (often zero-padded to 8 digits, e.g. 00013419)
#   - <layer> : body slot / z-order (00 = the catalog thumbnail; 2,7,8,9,11,
#               13,14,18,23,24… = the placed artwork's slot in the older scheme)
#   - <frame> : pose/frame, almost always 00
# ~4,300 image URLs / ~3,600 distinct items are archived (≈2005-2007). The live
# host 404s old ids, so these recover via Wayback id_. The look CATALOG (which
# items combine into an avatar + their z-order) is the live excellib JS — see
# qqshow/pipeline/catalog.py.
QQSHOW = [
    Target("qqshow-item", "qqshow-item.qq.com", "domain",
           "QQShow per-item artwork: <id>/<layer>/00/[cache.gif] layered GIFs"),
    Target("qqshow-engine", "imgcache.qq.com/ac/qqshow", "prefix",
           "QQShow dress-up engine (enginer_v_*.swf) + client assets"),
    Target("qqshow-club", "imgcache.qq.com/ac/club", "prefix",
           "QQ club / vip tool widgets"),
]

# --- 4399 games (sister project) -----------------------------------------
GAMES_4399 = [
    Target("4399-sda", "sda.4399.com", "domain",
           "4399 game SWF CDN (huge; ~tens of thousands of titles)"),
    Target("4399-sxiao", "sxiao.4399.com", "domain",
           "4399 secondary game SWF CDN"),
]


GROUPS = {
    "qzone": QZONE,
    "qqshow": QQSHOW,
    "4399": GAMES_4399,
    "all": QZONE + QQSHOW + GAMES_4399,
}


def resolve(group_or_name: str):
    """Return a list of Targets for a group name or a single target name."""
    if group_or_name in GROUPS:
        return GROUPS[group_or_name]
    for t in GROUPS["all"]:
        if t.name == group_or_name:
            return [t]
    raise SystemExit(
        f"Unknown target/group: {group_or_name!r}. "
        f"Groups: {', '.join(GROUPS)}. "
        f"Targets: {', '.join(t.name for t in GROUPS['all'])}"
    )
