#!/usr/bin/env python3
"""analyze.py — triage downloaded SWFs with ZERO external dependencies.

Parses each SWF's structure directly (header + tag stream) to answer the two
questions that decide how a widget gets revived:

  1. Is it AS3 or AS1/2?  -> drives Ruffle confidence (Ruffle nails AS1/2;
     AS3 support is partial, so AS3 files need a render check).
  2. Is it self-contained or networked?  -> scans for embedded http(s) URLs and
     Tencent CGI hosts. Networked widgets (花藤 farm state, music player audio)
     have dead backends and need a stub or client-side reimplementation.

Also reports: SWF version, compression, stage size, frame count/rate, and a tag
histogram (how many images / sounds / sprites / scripts).

Output: one JSON record per file to data/analysis.jsonl, plus a printed summary.

FFDec (JPEXS) is NOT required for this triage. It's only needed later for actual
asset *extraction* (--ffdec flag, if `ffdec`/`java -jar ffdec.jar` is available).

Usage:
    uv run python analyze.py                      # analyze data/assets/**.swf
    uv run python analyze.py --assets data/assets --out data/analysis.jsonl
    uv run python analyze.py path/to/one.swf      # a single file
"""

import argparse
import json
import re
import struct
import sys
import zlib
from pathlib import Path

# --- SWF tag codes we care about -----------------------------------------
TAG_NAMES = {
    0: "End", 1: "ShowFrame", 6: "DefineBits", 9: "SetBackgroundColor",
    12: "DoAction", 14: "DefineSound", 18: "SoundStreamHead",
    19: "SoundStreamBlock", 20: "DefineBitsLossless", 21: "DefineBitsJPEG2",
    35: "DefineBitsJPEG3", 36: "DefineBitsLossless2", 39: "DefineSprite",
    56: "ExportAssets", 59: "DoInitAction", 60: "DefineVideoStream",
    72: "DoABC", 76: "SymbolClass", 82: "DoABC2", 87: "DefineBinaryData",
    90: "DefineBitsJPEG4",
}
AS12_TAGS = {12, 59}                       # DoAction / DoInitAction
AS3_TAGS = {72, 82, 76}                    # DoABC / DoABC2 / SymbolClass
IMAGE_TAGS = {6, 20, 21, 35, 36, 90}
SOUND_TAGS = {14, 18, 19}

URL_RE = re.compile(rb"https?://[A-Za-z0-9._~:/?#%@!$&'()*+,;=\-]+")
# Tencent backend hostnames that imply a (now-dead) server dependency.
TENCENT_HOSTS = ("qzone.qq.com", "qzonestyle", "gtimg", "qq.com", "tencent",
                 "qpic", "qlogo", "cgi-bin", "qzs.qq")


def decompress_swf(raw: bytes) -> tuple[str, int, bytes] | None:
    """Return (compression, version, decompressed_body_after_8byte_header).

    Body is everything after the 8-byte file header, decompressed. None if the
    bytes aren't a recognizable SWF.
    """
    if len(raw) < 8:
        return None
    sig, version = raw[:3], raw[3]
    if sig == b"FWS":
        return ("none", version, raw[8:])
    if sig == b"CWS":
        try:
            return ("zlib", version, zlib.decompress(raw[8:]))
        except zlib.error:
            return None
    if sig == b"ZWS":
        # LZMA SWF: 4 bytes compressed-len, 5 bytes lzma props, then stream.
        try:
            import lzma
            props = raw[12:17]
            stream = raw[17:]
            filt = [{"id": lzma.FILTER_LZMA1,
                     "dict_size": struct.unpack("<I", props[1:5])[0]}]
            dec = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=filt)
            return ("lzma", version, dec.decompress(stream))
        except Exception:  # noqa: BLE001 — best effort; rare format
            return None
    return None


def _skip_rect(body: bytes) -> int:
    """Return byte offset in `body` just past the leading RECT (stage size)."""
    nbits = body[0] >> 3
    total_bits = 5 + nbits * 4
    return (total_bits + 7) // 8


def _read_rect(body: bytes) -> tuple[int, int, int]:
    """Parse the RECT -> (end_offset, width_px, height_px). Twips -> px /20."""
    nbits = body[0] >> 3
    total_bits = 5 + nbits * 4
    nbytes = (total_bits + 7) // 8
    val = int.from_bytes(body[:nbytes], "big")
    fields, pos = [], total_bits
    for _ in range(4):
        pos -= nbits
        fields.append((val >> pos) & ((1 << nbits) - 1))
    _, xmax, _, ymax = fields
    return nbytes, xmax // 20, ymax // 20


def iter_tags(body: bytes, start: int):
    """Yield (tag_code, length) for each tag, skipping over tag bodies."""
    i = start
    n = len(body)
    while i + 2 <= n:
        rh = struct.unpack_from("<H", body, i)[0]
        i += 2
        code = rh >> 6
        length = rh & 0x3F
        if length == 0x3F:
            if i + 4 > n:
                break
            length = struct.unpack_from("<I", body, i)[0]
            i += 4
        yield code, length
        if code == 0:  # End
            break
        i += length


def analyze_swf(path: Path) -> dict:
    raw = path.read_bytes()
    rec = {"path": str(path), "size": len(raw)}
    parsed = decompress_swf(raw)
    if not parsed:
        rec["ok"] = False
        rec["error"] = "not a valid SWF (bad magic / decompress failed)"
        return rec
    compression, version, body = parsed
    rec.update(ok=True, compression=compression, swf_version=version)

    try:
        rect_len, w, h = _read_rect(body)
        rec["stage"] = [w, h]
        rate = struct.unpack_from("<H", body, rect_len)[0] / 256.0
        frames = struct.unpack_from("<H", body, rect_len + 2)[0]
        rec["frame_rate"] = round(rate, 2)
        rec["frame_count"] = frames
        tag_start = rect_len + 4
    except Exception:  # noqa: BLE001
        tag_start = _skip_rect(body) + 4

    hist: dict[str, int] = {}
    images = sounds = 0
    has_as12 = has_as3 = False
    for code, _ in iter_tags(body, tag_start):
        name = TAG_NAMES.get(code, f"tag{code}")
        hist[name] = hist.get(name, 0) + 1
        if code in IMAGE_TAGS:
            images += 1
        if code in SOUND_TAGS:
            sounds += 1
        if code in AS12_TAGS:
            has_as12 = True
        if code in AS3_TAGS:
            has_as3 = True

    rec["images"] = images
    rec["sounds"] = sounds
    rec["tags"] = hist

    if has_as3:
        rec["as_version"] = "AS3"
        rec["ruffle_confidence"] = "check"   # partial AS3 support -> verify render
    elif has_as12:
        rec["as_version"] = "AS1/2"
        rec["ruffle_confidence"] = "good"
    else:
        rec["as_version"] = "none"
        rec["ruffle_confidence"] = "good"    # pure animation/asset, very safe

    urls = sorted({u.decode("latin-1") for u in URL_RE.findall(body)})
    rec["urls"] = urls
    networked = any(any(h in u for h in TENCENT_HOSTS) for u in urls) or bool(urls)
    rec["classification"] = "networked" if networked else "self_contained"
    return rec


def iter_swf_paths(target: Path):
    if target.is_file():
        yield target
    else:
        yield from sorted(target.rglob("*.swf"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", default="data/assets",
                    help="dir to scan recursively, or a single .swf (default: data/assets)")
    ap.add_argument("-o", "--out", default="data/analysis.jsonl")
    args = ap.parse_args()

    target = Path(args.target)
    paths = list(iter_swf_paths(target))
    if not paths:
        raise SystemExit(f"No .swf files under {target}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    recs = []
    with out.open("w") as f:
        for p in paths:
            rec = analyze_swf(p)
            recs.append(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    ok = [r for r in recs if r.get("ok")]
    bad = [r for r in recs if not r.get("ok")]
    by_as = _tally(ok, "as_version")
    by_class = _tally(ok, "classification")
    by_ruffle = _tally(ok, "ruffle_confidence")

    print(f"Analyzed {len(recs)} SWF(s) | ok={len(ok)} bad={len(bad)} -> {out}\n")
    print("ActionScript:   " + _fmt(by_as))
    print("Networking:     " + _fmt(by_class))
    print("Ruffle outlook: " + _fmt(by_ruffle))
    if bad:
        print(f"\n⚠ {len(bad)} unparseable (likely HTML error pages saved as .swf):")
        for r in bad[:5]:
            print(f"    {r['path']}")


def _tally(recs, key):
    out = {}
    for r in recs:
        out[r.get(key)] = out.get(r.get(key), 0) + 1
    return out


def _fmt(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(d.items(), key=lambda x: -x[1]))


if __name__ == "__main__":
    main()
