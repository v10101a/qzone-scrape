#!/usr/bin/env python3
"""ani2apng.py — convert recovered .ani cursors → animated PNG (APNG).

Chrome can't animate a CSS cursor, but it *does* render APNG in an <img>. So we
turn each Windows animated cursor (RIFF/ACON, frames = embedded .ico/.cur) into a
transparent APNG that the gallery shows as a mouse-following element.

Parses the ANI: 'anih' (frame/step counts + default jiffy rate), the 'icon'
frames, optional 'rate' (per-step durations) and 'seq ' (step→frame order), and
the first frame's hotspot. Writes library/cursor_anim/<id>.png + a hotspots json.

Usage:
    uv run python ani2apng.py            # convert all library/cursor/*.ani
    uv run python ani2apng.py --limit 20
"""

import argparse
import json
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image


def parse_ani(data: bytes):
    """Return (frames[bytes], step_order[int], durations_ms[int], hotspot(x,y))."""
    if data[:4] != b"RIFF" or data[8:12] != b"ACON":
        raise ValueError("not an ACON RIFF")
    pos, n = 12, len(data)
    frames, rates, seq = [], None, None
    nframes = nsteps = 0
    default_rate = 10  # jiffies (1/60s)
    while pos + 8 <= n:
        cid = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8: pos + 8 + size]
        if cid == b"anih":
            (_cb, nframes, nsteps, _w, _h, _bc, _pl, disp, _attr) = struct.unpack_from("<9I", body, 0)
            default_rate = disp or 10
        elif cid == b"rate":
            rates = list(struct.unpack_from(f"<{size // 4}I", body, 0))
        elif cid == b"seq ":
            seq = list(struct.unpack_from(f"<{size // 4}I", body, 0))
        elif cid == b"LIST" and body[:4] == b"fram":
            p2 = 4
            while p2 + 8 <= len(body):
                sid = body[p2:p2 + 4]
                ssz = struct.unpack_from("<I", body, p2 + 4)[0]
                if sid == b"icon":
                    frames.append(body[p2 + 8: p2 + 8 + ssz])
                p2 += 8 + ssz + (ssz & 1)
        pos += 8 + size + (size & 1)

    if not frames:
        raise ValueError("no icon frames")
    nframes = nframes or len(frames)
    nsteps = nsteps or nframes
    order = seq if seq else list(range(nsteps))
    if rates and len(rates) == len(order):
        durs = [max(20, int(r * 1000 / 60)) for r in rates]
    else:
        durs = [max(20, int(default_rate * 1000 / 60))] * len(order)

    # hotspot from the first frame's CUR dir entry (offset 10,12), if present
    hot = (0, 0)
    try:
        f0 = frames[0]
        if f0[2:4] == b"\x02\x00":  # CUR
            hot = struct.unpack_from("<HH", f0, 10)
    except Exception:  # noqa: BLE001
        pass
    return frames, order, durs, hot


def icon_to_rgba(b: bytes) -> Image.Image:
    """Decode an ICO/CUR frame to RGBA, applying the 1-bit AND transparency mask.

    Pillow alone leaves <32bpp cursors opaque (it doesn't apply the AND mask),
    which is why most came out black. We decode the DIB ourselves: palette + XOR
    bitmap for the color, AND mask for alpha. PNG-compressed frames pass through.
    """
    count = struct.unpack_from("<H", b, 4)[0] or 1
    ent = b[6:22]
    size = struct.unpack_from("<I", ent, 8)[0]
    off = struct.unpack_from("<I", ent, 12)[0]
    img = b[off: off + size] if size else b[off:]
    if img[:8] == b"\x89PNG\r\n\x1a\n":               # Vista+ PNG icon: has own alpha
        return Image.open(BytesIO(img)).convert("RGBA")

    hsize, w, h2, _planes, bpp, _comp = struct.unpack_from("<IiiHHI", img, 0)
    h = h2 // 2                                        # DIB stores XOR rows + AND rows
    clr_used = struct.unpack_from("<I", img, 32)[0]
    pal_n = clr_used if clr_used else (1 << bpp if bpp <= 8 else 0)
    pal = []
    poff = hsize
    for i in range(pal_n):
        bb, gg, rr, _a = img[poff + i * 4: poff + i * 4 + 4]
        pal.append((rr, gg, bb))
    xor_off = poff + pal_n * 4
    xrow = ((w * bpp + 31) // 32) * 4                  # 4-byte aligned rows
    arow = ((w + 31) // 32) * 4
    and_off = xor_off + xrow * h

    out = Image.new("RGBA", (w, h))
    px = out.load()
    for y in range(h):
        sr = h - 1 - y                                # bottom-up
        xb, ab = xor_off + sr * xrow, and_off + sr * arow
        for x in range(w):
            transp = (img[ab + (x >> 3)] >> (7 - (x & 7))) & 1
            if bpp == 32:
                bb, gg, rr, a = img[xb + x * 4: xb + x * 4 + 4]
                if transp:
                    a = 0
                elif a == 0:
                    a = 255                            # opaque pixel w/ unset alpha byte
                px[x, y] = (rr, gg, bb, a)
            elif bpp == 24:
                bb, gg, rr = img[xb + x * 3: xb + x * 3 + 3]
                px[x, y] = (rr, gg, bb, 0 if transp else 255)
            else:                                      # 1/4/8 bpp paletted
                if bpp == 8:
                    idx = img[xb + x]
                elif bpp == 4:
                    idx = (img[xb + (x >> 1)] >> 4) if not (x & 1) else (img[xb + (x >> 1)] & 0xF)
                else:  # 1bpp
                    idx = (img[xb + (x >> 3)] >> (7 - (x & 7))) & 1
                rr, gg, bb = pal[idx] if idx < len(pal) else (0, 0, 0)
                px[x, y] = (rr, gg, bb, 0 if transp else 255)
    return out


def convert(path: Path, outdir: Path):
    frames, order, durs, hot = parse_ani(path.read_bytes())
    imgs = [icon_to_rgba(frames[i % len(frames)]) for i in order]
    if not imgs:
        return None
    w = max(i.width for i in imgs)
    h = max(i.height for i in imgs)
    imgs = [im if im.size == (w, h) else _pad(im, w, h) for im in imgs]
    out = outdir / f"{path.stem}.png"
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=durs,
                 loop=0, disposal=1, format="PNG")
    return {"id": path.stem, "w": w, "h": h, "frames": len(imgs),
            "hotspot": list(hot), "png": f"library/cursor_anim/{path.stem}.png"}


def _pad(im, w, h):
    bg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bg.paste(im, (0, 0))
    return bg


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default="library/cursor")
    ap.add_argument("--out", default="library/cursor_anim")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    src = sorted(Path(args.src).glob("*.ani"))
    if args.limit:
        src = src[:args.limit]
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    hotspots, ok, fail = {}, 0, 0
    for p in src:
        try:
            rec = convert(p, outdir)
            if rec:
                hotspots[rec["id"]] = rec
                ok += 1
        except Exception as e:  # noqa: BLE001
            fail += 1
            if fail <= 5:
                print(f"  ! {p.name}: {type(e).__name__} {e}")
    (outdir / "_hotspots.json").write_text(json.dumps(hotspots, ensure_ascii=False))
    print(f"\nConverted {ok} cursor(s) -> {outdir}  (failed {fail})")


if __name__ == "__main__":
    main()
