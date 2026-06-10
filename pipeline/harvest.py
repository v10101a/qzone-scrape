#!/usr/bin/env python3
"""CDX harvester — build a manifest of archived assets from the Wayback Machine.

Queries the Wayback CDX API for each target, paginates through every result
block, dedupes to one row per unique URL (keeping the best snapshot), and
writes a JSONL manifest. No third-party deps.

Examples:
    python3 harvest.py qzone                       # all QZone targets, SWF only
    python3 harvest.py qqshow --mime all           # every mimetype
    python3 harvest.py 4399-sda --status 200       # one target, only 200s
    python3 harvest.py all -o data/manifest.jsonl

The manifest is append-safe and deduped on load by the downloader, so re-running
a harvest to pick up new snapshots is cheap.
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import targets as T

CDX = "http://web.archive.org/cdx/search/cdx"
UA = "qzone-museum-harvester/0.1 (preservation; contact via project)"

# Rows pulled per CDX request when paginating via resumeKey.
PAGE_LIMIT = 25000

# Mimetype filter presets. CDX `filter=mimetype:<re>` treats the value as a
# regex directly — do NOT prefix with `~` (that matches a literal tilde and
# silently returns zero rows).
MIME_PRESETS = {
    "swf": "application/x-shockwave-flash",
    "image": "image/.*",
    "audio": "(audio|application/ogg).*",
    "media": "(application/x-shockwave-flash|image/.*|audio/.*)",
    "all": None,
}

# Fields we pull back from CDX, in order.
FL = ["original", "timestamp", "statuscode", "mimetype", "digest", "length"]


def _get(url: str, retries: int = 5, timeout: int = 90) -> str:
    """GET with exponential backoff on transient failures."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 — network is broad by nature
            last = e
            wait = min(2 ** attempt, 30)
            print(f"    ! {type(e).__name__}: {e} — retry in {wait}s "
                  f"({attempt + 1}/{retries})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"GET failed after {retries} tries: {url}") from last


def _cdx_params(target: T.Target, mime: str, status: str | None) -> list[tuple]:
    # output=text + resumeKey paginates correctly for ALL match types
    # (the page/showNumPages API silently returns empty for matchType=prefix).
    p = [
        ("url", target.url),
        ("matchType", target.match),
        ("output", "text"),
        ("fl", ",".join(FL)),
        ("collapse", "urlkey"),     # dedupe per window; full dedupe done on load
        ("limit", str(PAGE_LIMIT)),
        ("showResumeKey", "true"),
    ]
    mime_filter = MIME_PRESETS[mime]
    if mime_filter:
        p.append(("filter", f"mimetype:{mime_filter}"))
    if status:
        p.append(("filter", f"statuscode:{status}"))
    for f in target.filters:
        p.append(("filter", f))
    return p


def _parse_text_page(txt: str):
    """Parse a text CDX response. Returns (rows, resume_key_or_None).

    With showResumeKey=true the body ends with a blank line then the resume
    key on its own line (absent on the final page).
    """
    lines = txt.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    resume = None
    if len(lines) >= 2 and lines[-2] == "":
        resume = lines[-1]
        lines = lines[:-2]
    rows = []
    for line in lines:
        if not line:
            continue
        parts = line.split(" ", len(FL) - 1)
        rows.append(dict(zip(FL, parts)))
    return rows, resume


def harvest_target(target: T.Target, mime: str, status: str | None,
                   delay: float):
    base = _cdx_params(target, mime, status)
    print(f"  {target.name}: [{target.match} {target.url}]")
    out, resume, window = [], None, 0
    while True:
        params = list(base)
        if resume:
            params.append(("resumeKey", resume))
        txt = _get(f"{CDX}?{urllib.parse.urlencode(params)}")
        rows, resume = _parse_text_page(txt)
        for r in rows:
            r["_target"] = target.name
        out.extend(rows)
        window += 1
        print(f"    window {window}: +{len(rows)} (running total {len(out)})")
        if not resume:
            break
        time.sleep(delay)
    return out


def write_manifest(records: list[dict], path: Path):
    """Append records; dedupe whole file by original URL keeping best snapshot.

    'Best' = a 200 beats a non-200; otherwise the most recent timestamp wins.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                existing[rec["original"]] = rec

    def better(a: dict, b: dict) -> dict:
        a200 = a.get("statuscode") == "200"
        b200 = b.get("statuscode") == "200"
        if a200 != b200:
            return a if a200 else b
        return a if a.get("timestamp", "") >= b.get("timestamp", "") else b

    added = 0
    for rec in records:
        url = rec["original"]
        if url in existing:
            existing[url] = better(existing[url], rec)
        else:
            existing[url] = rec
            added += 1

    with path.open("w") as f:
        for rec in sorted(existing.values(), key=lambda r: r["original"]):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return added, len(existing)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("group", help="target group (qzone|qqshow|4399|all) or a single target name")
    ap.add_argument("--mime", choices=list(MIME_PRESETS), default="swf",
                    help="mimetype filter preset (default: swf)")
    ap.add_argument("--status", default="200",
                    help="statuscode filter, e.g. 200 (default), or '' to disable")
    ap.add_argument("-o", "--out", default="data/manifest.jsonl",
                    help="manifest path (default: data/manifest.jsonl)")
    ap.add_argument("--delay", type=float, default=0.5,
                    help="seconds between CDX page requests (default: 0.5)")
    args = ap.parse_args()

    status = args.status or None
    targets = T.resolve(args.group)
    print(f"Harvesting {len(targets)} target(s) | mime={args.mime} "
          f"status={status or 'any'}")

    all_records = []
    for t in targets:
        try:
            all_records.extend(harvest_target(t, args.mime, status, args.delay))
        except Exception as e:  # noqa: BLE001
            print(f"  !! {t.name} failed: {e}", file=sys.stderr)

    added, total = write_manifest(all_records, Path(args.out))
    print(f"\nDone. {len(all_records)} rows fetched | "
          f"+{added} new | {total} unique URLs in {args.out}")


if __name__ == "__main__":
    main()
