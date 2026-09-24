"""Cut the QZone pixel critters out of a sheet and give each one a sticker outline.

The sheet is already transparent apart from its own window chrome, so a sprite is
just a connected clump of opaque pixels. Clumps are grouped by hand-drawn boxes
(a fish and its bubbles are one sticker, the watermark is none), then each group
is cropped and traced: the silhouette is dilated by OUTLINE px with a distance
transform run at SS× so the die-cut edge comes out smooth rather than stair-stepped.

The same dilated silhouette is then traced to a vector path, and the art itself
is traced colour by colour — pixel art is flat regions, so this is exact rather
than a fit — giving SVG and PDF that print crisp at any size. Everything inside
the die line is painted opaque (soft edge pixels are flattened onto the border
colour); everything outside it is left transparent, so the shape stays a sticker.

Writes animal-stickers/ (outlined PNG), plain/ (bare cut-outs), @3x/ (retina),
svg/, pdf/, and _proof.pdf — a contact sheet at true print size.
"""

import math, pathlib, numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd
import vectorkit as vk

SRC = pathlib.Path("/Users/lh1783/Desktop/qzone-stick.png")
OUT = pathlib.Path("/Users/lh1783/web-scrape/web/assets/animal-stickers")

OUTLINE = 5              # sticker border, in sheet pixels
COLOR   = (255, 255, 255)
SS      = 6              # supersampling for the distance transform
SCALES  = (1, 3)         # 1x beside the source art, 3x for large display

U         = 10           # vector units per source pixel
MM_PER_PX = 0.5          # printed size of one source pixel — the whole set's scale
SEAM      = 1            # colour regions overlap by this many units, killing hairlines
DP        = 1.2          # die-line simplification tolerance, in units
CUTLINE   = False        # add a magenta CutContour stroke on the die line
CUT_RGB   = (236, 0, 140)

# Stickers whose scattered parts should come off the sheet as one piece: the
# outline is welded into a single closed path instead of one loop per part.
WELD     = {"fish-blue", "fish-small", "sparkles"}
WELD_MAX = 60            # give up past this radius, in sheet pixels
WELD_FAT = 1.3           # past the slimmest bridge that joins, so necks can't tear
PINHOLE  = 40            # interior gaps under this many px² are closed, not cut

# Each sticker's parts must fall wholly inside its box; anything left over is
# reported, so a mis-drawn box fails loudly instead of silently dropping a leg.
GROUPS = [
    ("fish-orange", (30, 105, 175, 205)),   ("fish-purple", (180, 105, 310, 215)),
    ("fish-teal",   (315,  88, 460, 210)),  ("fish-red",    (478,  90, 620, 212)),
    ("fish-blue",   (635,  95, 762, 220)),  ("pig-bowl",    ( 50, 230, 160, 355)),
    ("butterfly",   (175, 245, 300, 350)),  ("laptop",      (305, 245, 400, 335)),
    ("cherries",    (405, 248, 485, 332)),  ("flower",      (510, 242, 625, 365)),
    ("monkey",      (630, 238, 765, 380)),  ("pig-pink",    ( 40, 370, 165, 505)),
    ("chick",       (175, 378, 285, 500)),  ("bubble",      (298, 380, 400, 472)),
    ("dove",        (400, 368, 530, 470)),  ("bunny",       (540, 378, 625, 518)),
    ("sparkles",    (630, 400, 765, 540)),  ("fish-small",  (370, 478, 490, 545)),
]
WATERMARK = (40, 510, 345, 560)   # qzone2000.com — cut away, not a sticker


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def groups(sheet):
    """{name: boolean mask} for every sticker on the sheet."""
    solid = np.asarray(sheet)[..., 3] > 8
    lab, _ = nd.label(solid, np.ones((3, 3)))
    edge = set(lab[0]) | set(lab[-1]) | set(lab[:, 0]) | set(lab[:, -1]) - {0}
    solid &= ~np.isin(lab, list(edge - {0}))         # the window chrome itself
    lab, n = nd.label(solid, np.ones((3, 3)))

    out, orphans = {}, []
    for i, (ys, xs) in enumerate(nd.find_objects(lab), 1):
        box = (xs.start, ys.start, xs.stop, ys.stop)
        inside = lambda b: box[0] >= b[0] and box[1] >= b[1] and box[2] <= b[2] and box[3] <= b[3]
        hit = [name for name, b in GROUPS if inside(b)]
        if len(hit) == 1:
            out.setdefault(hit[0], []).append(i)
        elif not inside(WATERMARK):
            orphans.append((box, hit))
    for box, hit in orphans:
        print(f"  !! clump at {box} belongs to {hit or 'no group'}")
    missing = [name for name, _ in GROUPS if name not in out]
    if missing:
        print(f"  !! empty groups: {missing}")
    return {name: np.isin(lab, ids) for name, ids in out.items()}


def die_mask(alpha, radius, ss, weld=0):
    """The silhouette grown by `radius` px, as a boolean mask at `ss`× resolution.

    With `weld` set, the shape is grown by that much larger radius and then
    shrunk back by the difference instead. Parts further apart than the gap the
    weld can span stay where they were, so the outline still sits `radius` off
    the art in the open and only fattens where it has a neighbour to reach.
    """
    hi = np.repeat(np.repeat(alpha >= 128, ss, 0), ss, 1)
    grown = nd.distance_transform_edt(~hi)
    if weld <= radius:
        return plug(grown <= radius * ss, ss, PINHOLE)
    # a welded sticker comes off the sheet in one piece, so it gets one contour:
    # the gaps the bridges enclose are filled rather than left as islands to cut
    return plug(nd.distance_transform_edt(grown <= weld * ss) > (weld - radius) * ss,
                ss, math.inf)


def plug(mask, ss, limit):
    """Close interior gaps smaller than `limit` px²."""
    gaps, n = nd.label(~mask)
    if n < 2:
        return mask
    small = np.bincount(gaps.ravel()) < limit * ss * ss
    small[[0, *gaps[0], *gaps[-1], *gaps[:, 0], *gaps[:, -1]]] = False
    return mask | small[gaps]


def weld_radius(name, alpha, ss):
    """Smallest weld that pulls one sticker's parts into a single cut path."""
    if name not in WELD:
        return 0
    loose, tight = OUTLINE, 0
    while loose < WELD_MAX and not tight:
        step = round(loose * 1.3) + 1
        if nd.label(die_mask(alpha, OUTLINE, ss, step))[1] == 1:
            tight = step
        else:
            loose = step
    if not tight:
        print(f"  !! {name}: nothing under {WELD_MAX}px welds it into one piece")
        return 0
    for _ in range(4):                       # bisect back down to the slimmest bridge
        mid = (loose + tight) / 2
        if nd.label(die_mask(alpha, OUTLINE, ss, mid))[1] == 1:
            tight = mid
        else:
            loose = mid
    return tight * WELD_FAT


def halo(sprite, mask, ss):
    """The sprite over a COLOR die shape, anti-aliased by downsampling the mask."""
    a = np.asarray(sprite)[..., 3]
    cov = mask.reshape(a.shape[0], ss, a.shape[1], ss).mean(axis=(1, 3))
    ring = Image.fromarray(
        np.dstack([np.full(a.shape + (3,), COLOR, np.uint8),
                   (cov * 255).round().astype(np.uint8)]), "RGBA")
    ring.alpha_composite(sprite)
    return ring


def cut(sheet, mask, scale, pad_px):
    """Crop one sticker out of the sheet at `scale`, with `pad_px` px of room."""
    rgba = np.asarray(sheet).copy()
    rgba[..., 3] = np.where(mask, rgba[..., 3], 0)
    ys, xs = np.nonzero(mask)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1

    sprite = Image.fromarray(rgba[y0:y1, x0:x1], "RGBA")
    if scale > 1:
        sprite = sprite.resize((sprite.width * scale, sprite.height * scale), Image.NEAREST)
    pad = pad_px * scale + 2
    padded = Image.new("RGBA", (sprite.width + pad * 2, sprite.height + pad * 2), (0, 0, 0, 0))
    padded.alpha_composite(sprite, (pad, pad))
    return sprite, padded, (int(x0) - pad, int(y0) - pad)


def trim(sprite, mask, ss, origin, margin=2):
    """Shrink a generously padded sprite and its die mask back onto the die shape."""
    ys, xs = np.nonzero(mask)
    x0, y0 = max(0, xs.min() // ss - margin), max(0, ys.min() // ss - margin)
    x1 = min(sprite.width, xs.max() // ss + 1 + margin)
    y1 = min(sprite.height, ys.max() // ss + 1 + margin)
    return (sprite.crop((x0, y0, x1, y1)), mask[y0 * ss:y1 * ss, x0 * ss:x1 * ss],
            (origin[0] + x0, origin[1] + y0))


def vectorize(sprite, die):
    """(die loops, [(rgb, loops)]) for one padded sprite, in U-per-pixel units.

    The die line is traced off the U× die mask and simplified. The art is traced
    per colour on the source grid — exact, since every pixel is one flat colour —
    then grown by SEAM so neighbouring regions overlap instead of leaving the
    hairline gaps renderers draw between abutting shapes.
    """
    rgba = np.asarray(sprite).astype(np.int16)
    a = rgba[..., 3]
    die_loops = [vk.simplify(lp, DP) for lp in vk.trace(die)]

    # soft edge pixels flatten onto the border colour; anything the die line does
    # not reach is a stray halo pixel and is dropped rather than left floating
    inside = die[U // 2::U, U // 2::U] & (a > 0)
    f = a[..., None] / 255.0
    baked = np.where(inside[..., None], (rgba[..., :3] * f + np.array(COLOR) * (1 - f)), -1)
    baked = baked.round().astype(np.int16)

    flat = baked.reshape(-1, 3)
    colors, index = np.unique(flat[inside.reshape(-1)], axis=0, return_inverse=True)
    art = []
    for i, rgb in enumerate(colors):
        region = np.zeros(flat.shape[0], bool)
        region[np.flatnonzero(inside.reshape(-1))[index == i]] = True
        loops = [vk.grow(vk.scale(lp, U), SEAM) for lp in vk.trace(region.reshape(a.shape))]
        art.append((tuple(int(c) for c in rgb), loops))
    return die_loops, art


HEX = lambda c: "#%02x%02x%02x" % c
STROKE = 0.25 / (MM_PER_PX * vk.PT_PER_MM / U)      # a 0.25pt die line, in units


def svg_sticker(die, art, tag):
    cut = (f'<path fill="none" stroke="{HEX(CUT_RGB)}" stroke-width="{STROKE:.2f}" '
           f'id="CutContour{tag}" d="{vk.svg_d(die)}"/>\n') if CUTLINE else ""
    return (f'<clipPath id="die{tag}"><path d="{vk.svg_d(die)}"/></clipPath>\n'
            f'<path fill="{HEX(COLOR)}" d="{vk.svg_d(die)}"/>\n'
            f'<g clip-path="url(#die{tag})">\n'
            + "".join(f'<path fill="{HEX(c)}" d="{vk.svg_d(l)}"/>\n' for c, l in art)
            + "</g>\n" + cut)


def draw_sticker(pdf, die, art):
    pdf.fill(COLOR, die)
    pdf.clipped(die, lambda: [pdf.fill(c, loops) for c, loops in art])
    if CUTLINE:
        pdf.stroke(CUT_RGB, die, STROKE)


def write_vector(name, sprite, die, art):
    size = (sprite.width * U, sprite.height * U)
    mm = (sprite.width * MM_PER_PX, sprite.height * MM_PER_PX)
    (OUT / "svg" / f"{name}.svg").write_text(vk.svg(svg_sticker(die, art, ""), size, mm, name))

    pdf = vk.Pdf(mm)
    pdf.place((0, 0, *mm), size, lambda: draw_sticker(pdf, die, art))
    pdf.save(OUT / "pdf" / f"{name}.pdf")
    return mm


def write_sheet(placed, px):
    """The whole sheet as one vector page: every sticker where it started, outlined.

    Only the critters go on it. The window chrome and the qzone2000.com mark are
    soft anti-aliased raster — the watermark alone is 1338 colours over 3773
    pixels — so they would vectorise into noise rather than shapes.
    """
    size, mm = (px[0] * U, px[1] * U), (px[0] * MM_PER_PX, px[1] * MM_PER_PX)
    # every white die shape is laid down before any art, so a border can never
    # land on top of a neighbour that happens to sit close
    body = "".join(f'<clipPath id="die{i}"><path d="{vk.svg_d(die)}"/></clipPath>\n'
                   f'<path fill="{HEX(COLOR)}" d="{vk.svg_d(die)}"/>\n'
                   for i, (_, die, _) in enumerate(placed))
    body += "".join(f'<g clip-path="url(#die{i})">\n'
                    + "".join(f'<path fill="{HEX(c)}" d="{vk.svg_d(l)}"/>\n' for c, l in art)
                    + "</g>\n" for i, (_, _, art) in enumerate(placed))
    if CUTLINE:
        body += "".join(f'<path fill="none" stroke="{HEX(CUT_RGB)}" stroke-width="{STROKE:.2f}" '
                        f'id="CutContour{i}" d="{vk.svg_d(die)}"/>\n'
                        for i, (_, die, _) in enumerate(placed))
    (OUT / "sheet.svg").write_text(vk.svg(body, size, mm, "QZone animal stickers"))

    pdf = vk.Pdf(mm)

    def draw():
        for _, die, _ in placed:
            pdf.fill(COLOR, die)
        for _, die, art in placed:
            pdf.clipped(die, lambda die=die, art=art: [pdf.fill(c, l) for c, l in art])
        if CUTLINE:
            for _, die, _ in placed:
                pdf.stroke(CUT_RGB, die, STROKE)

    pdf.place((0, 0, *mm), size, draw)
    pdf.save(OUT / "sheet.pdf")
    return mm


def proof(items, path, cols=5, pad=6):
    """One page, every sticker at its true printed size, named and measured."""
    w = max(mm[0] for _, _, _, mm in items) + pad * 2
    h = max(mm[1] for _, _, _, mm in items) + pad * 2 + 5
    rows = -(-len(items) // cols)
    page = (cols * w, rows * h + 14)
    pdf = vk.Pdf(page, font=True)
    pdf.label(pad, 9, f"QZone animal stickers — {len(items)} pieces, shown at print size "
                      f"({MM_PER_PX}mm per source pixel)", 9, (40, 60, 90))
    for k, (name, die, art, mm) in enumerate(items):
        x, y = (k % cols) * w, (k // cols) * h + 14
        pdf.place((x + (w - mm[0]) / 2, y + pad, *mm), (mm[0] / MM_PER_PX * U, mm[1] / MM_PER_PX * U),
                  lambda die=die, art=art: draw_sticker(pdf, die, art))
        pdf.label(x + pad, y + h - 4, f"{name}  {mm[0]:.0f}×{mm[1]:.0f}mm", 7)
    pdf.save(path)
    return page


def preview(tiles, path, cols=6, cell=(150, 170)):
    sheet = Image.new("RGBA", (cols * cell[0], -(-len(tiles) // cols) * cell[1]), (238, 243, 250, 255))
    draw = ImageDraw.Draw(sheet)
    for k, (name, tile) in enumerate(tiles):
        cx, cy = (k % cols) * cell[0], (k // cols) * cell[1]
        fit = min(1.0, (cell[0] - 16) / tile.width, (cell[1] - 34) / tile.height)
        if fit < 1.0:
            tile = tile.resize((round(tile.width * fit), round(tile.height * fit)), Image.LANCZOS)
        sheet.alpha_composite(tile, (cx + (cell[0] - tile.width) // 2,
                                     cy + (cell[1] - 20 - tile.height) // 2))
        draw.text((cx + 6, cy + cell[1] - 16), f"{name}  {tile.width}×{tile.height}", fill=(60, 85, 120, 255))
    sheet.save(path)


sheet = Image.open(SRC).convert("RGBA")
masks = groups(sheet)
for sub in ("svg", "pdf"):
    (OUT / sub).mkdir(parents=True, exist_ok=True)

tiles, printable, placed, welds = [], [], [], {}
for scale in SCALES:
    dest = OUT if scale == 1 else OUT / f"@{scale}x"
    (dest / "plain").mkdir(parents=True, exist_ok=True)
    for name, _ in GROUPS:
        slack = WELD_MAX if name in WELD else 0
        sprite, padded, origin = cut(sheet, masks[name], scale, OUTLINE + slack)
        alpha, ss = np.asarray(padded)[..., 3], U if scale == 1 else SS
        if scale == 1:
            welds[name] = weld_radius(name, alpha, ss)
        mask = die_mask(alpha, OUTLINE * scale, ss, welds[name] * scale)
        padded, mask, origin = trim(padded, mask, ss, origin)
        sticker = halo(padded, mask, ss)
        sticker.save(dest / f"{name}.png")
        sprite.save(dest / "plain" / f"{name}.png")
        if scale > 1:
            print(f"  @{scale}x {name}.png  {sticker.width}x{sticker.height}")
            continue
        die, art = vectorize(padded, mask)
        mm = write_vector(name, padded, die, art)
        tiles.append((name, sticker))
        printable.append((name, die, art, mm))
        at = lambda loops: [vk.move(lp, origin[0] * U, origin[1] * U) for lp in loops]
        placed.append((name, at(die), [(c, at(l)) for c, l in art]))
        print(f"  {name:<12} {sticker.width}x{sticker.height}px  {mm[0]:.0f}x{mm[1]:.0f}mm  "
              f"{len(art)} colours, {sum(len(l) for _, l in art) + len(die)} paths, "
              f"{plural(nd.label(mask)[1], 'piece')}, {plural(len(die), 'contour')}"
              + (f", welded at {welds[name]:.1f}px" if welds[name] else ""))

preview(tiles, OUT / "_preview.png")
page = proof(printable, OUT / "_proof.pdf")
print(f"  _proof.pdf  {page[0]:.0f}x{page[1]:.0f}mm")
page = write_sheet(placed, sheet.size)
print(f"  sheet.pdf / sheet.svg  {page[0]:.0f}x{page[1]:.0f}mm  ({sheet.size[0]}x{sheet.size[1]} source px)")
print("done ->", OUT)
