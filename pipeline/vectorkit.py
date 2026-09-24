"""Pixel masks to vector loops, and vector loops to SVG and PDF.

No potrace, no shapely: everything here is a pixel grid, so a region boundary is
traced by crack-following — collect every edge that has the region on one side
and empty on the other, orient them all the same way round, stitch them into
closed loops. It is exact (no curve fitting to go wrong), it is integer, and
holes fall out of it with the opposite winding, so nonzero fill punches them for
free. Smooth shapes are traced from a supersampled mask and then simplified.

The PDF writer is the minimum that a print shop can open: one page, transparent
background, flate-compressed content, no transparency beyond the page group.
"""

import zlib

# right, down, left, up — clockwise on screen, where y grows downward
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
PT_PER_MM = 72 / 25.4


def trace(mask):
    """Closed integer loops around every blob in `mask`, in cell units.

    Edges run with the filled side on their right, so outer loops come out
    clockwise and holes counter-clockwise. At a diagonal pinch the walk takes
    the sharpest clockwise turn, which keeps the two blobs as separate loops.
    """
    import numpy as np
    m = np.pad(mask, 1)
    stride = m.shape[1] + 1
    ys, xs = np.nonzero(m)

    heads = {}
    sides = ((~m[ys - 1, xs], xs, ys, xs + 1, ys, 0),          # north edge, going right
             (~m[ys, xs + 1], xs + 1, ys, xs + 1, ys + 1, 1),  # east, going down
             (~m[ys + 1, xs], xs + 1, ys + 1, xs, ys + 1, 2),  # south, going left
             (~m[ys, xs - 1], xs, ys + 1, xs, ys, 3))          # west, going up
    for sel, ax, ay, bx, by, d in sides:
        a = (ay[sel] * stride + ax[sel]).tolist()
        b = (by[sel] * stride + bx[sel]).tolist()
        for u, v in zip(a, b):
            heads.setdefault(u, []).append([v, d, False])

    loops = []
    for start, edges in heads.items():
        for first in edges:
            if first[2]:
                continue
            first[2] = True
            loop, node, d = [start], first[0], first[1]
            while node != start:
                loop.append(node)
                step = None
                for want in ((d + 1) % 4, d, (d + 3) % 4, (d + 2) % 4):
                    step = next((e for e in heads[node] if not e[2] and e[1] == want), None)
                    if step:
                        break
                step[2] = True
                node, d = step[0], step[1]
            loops.append([(v % stride - 1, v // stride - 1) for v in loop])
    return [corners(lp) for lp in loops]


def corners(loop):
    """Drop the vertices that only sit mid-edge."""
    out = []
    n = len(loop)
    for i, (x, y) in enumerate(loop):
        ax, ay = loop[i - 1]
        bx, by = loop[(i + 1) % n]
        if (x - ax) * (by - y) != (y - ay) * (bx - x):
            out.append((x, y))
    return out


def scale(loop, k):
    return [(x * k, y * k) for x, y in loop]


def move(loop, dx, dy):
    return [(x + dx, y + dy) for x, y in loop]


def grow(loop, k):
    """Push a rectilinear loop `k` units outward along its own normals.

    Each edge slides out by its outward normal (the left of its direction, the
    empty side); perpendicular neighbours then meet at vertex + both normals.
    Safe while every feature is at least 2k wide, which one source pixel is.
    """
    out, n = [], len(loop)
    for i, (x, y) in enumerate(loop):
        px, py = loop[i - 1]
        nx, ny = loop[(i + 1) % n]
        ia, ib = normal(x - px, y - py), normal(nx - x, ny - y)
        out.append((x + k * (ia[0] + ib[0]), y + k * (ia[1] + ib[1])))
    return out


def normal(dx, dy):
    """Outward normal of an edge heading (dx, dy) with its region on the right."""
    return (0, -1) if dx > 0 else (0, 1) if dx < 0 else (1, 0) if dy > 0 else (-1, 0)


def simplify(loop, eps):
    """Douglas-Peucker on a closed loop, anchored on its two farthest-apart corners."""
    if len(loop) < 4:
        return loop
    far = max(range(len(loop)), key=lambda i: loop[i][0] ** 2 + loop[i][1] ** 2)
    loop = loop[far:] + loop[:far]
    half = len(loop) // 2
    keep = _dp(loop[:half + 1], eps)[:-1] + _dp(loop[half:] + loop[:1], eps)[:-1]
    return [(round(x), round(y)) for x, y in keep]


def _dp(pts, eps):
    if len(pts) < 3:
        return list(pts)
    (ax, ay), (bx, by) = pts[0], pts[-1]
    dx, dy = bx - ax, by - ay
    span = (dx * dx + dy * dy) ** .5 or 1.0
    worst, at = 0.0, 0
    for i, (x, y) in enumerate(pts[1:-1], 1):
        off = abs(dy * (x - ax) - dx * (y - ay)) / span
        if off > worst:
            worst, at = off, i
    if worst <= eps:
        return [pts[0], pts[-1]]
    return _dp(pts[:at + 1], eps)[:-1] + _dp(pts[at:], eps)


def svg_d(loops):
    out = []
    for lp in loops:
        x, y = lp[0]
        out.append(f"M{x} {y}")
        for nx, ny in lp[1:]:
            dx, dy = nx - x, ny - y
            out.append(f"h{dx}" if dy == 0 else f"v{dy}" if dx == 0 else f"l{dx} {dy}")
            x, y = nx, ny
        out.append("z")
    return "".join(out)


def pdf_d(loops):
    out = []
    for lp in loops:
        out.append(f"{lp[0][0]} {lp[0][1]} m")
        out += [f"{x} {y} l" for x, y in lp[1:]]
        out.append("h")
    return " ".join(out)


def svg(body, size, mm, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{mm[0]:.3f}mm" '
            f'height="{mm[1]:.3f}mm" viewBox="0 0 {size[0]} {size[1]}">\n'
            f"<title>{title}</title>\n{body}</svg>\n")


class Pdf:
    """A one-page vector PDF with a transparent background.

    The page is addressed in mm from its top-left; `place` maps a unit-space
    drawing into an mm box, so the same loops serve a single sticker and a
    proof sheet.
    """

    def __init__(self, mm, font=False):
        self.pt = (mm[0] * PT_PER_MM, mm[1] * PT_PER_MM)
        self.ops, self.font = [], font

    def place(self, box, size, draw):
        x, y, w, h = box
        self.ops.append("q %.6f 0 0 %.6f %.4f %.4f cm" % (
            w * PT_PER_MM / size[0], -h * PT_PER_MM / size[1],
            x * PT_PER_MM, self.pt[1] - y * PT_PER_MM))
        draw()
        self.ops.append("Q")

    def fill(self, rgb, loops):
        self.ops.append("%.4f %.4f %.4f rg %s f" % (*[c / 255 for c in rgb], pdf_d(loops)))

    def stroke(self, rgb, loops, width):
        self.ops.append("%.4f %.4f %.4f RG %.4f w %s S" % (*[c / 255 for c in rgb], width, pdf_d(loops)))

    def clipped(self, loops, draw):
        self.ops.append("q " + pdf_d(loops) + " W n")
        draw()
        self.ops.append("Q")

    def label(self, x, y, text, pt=8, rgb=(90, 110, 140)):
        esc = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        self.ops.append("BT %.4f %.4f %.4f rg /F1 %g Tf %.3f %.3f Td (%s) Tj ET" % (
            *[c / 255 for c in rgb], pt, x * PT_PER_MM, self.pt[1] - y * PT_PER_MM, esc))

    def save(self, path):
        stream = zlib.compress("\n".join(self.ops).encode("latin-1", "replace"))
        res = "/Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >> >>" if self.font else ""
        objs = ["<< /Type /Catalog /Pages 2 0 R >>",
                "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.pt[0]:.4f} {self.pt[1]:.4f}] "
                f"/Group << /S /Transparency /CS /DeviceRGB >> /Resources << {res} >> /Contents 4 0 R >>",
                f"<< /Length {len(stream)} /Filter /FlateDecode >>\nstream\n@\nendstream"]
        out, offsets = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"), []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            head, _, tail = body.partition("@")
            out += f"{i} 0 obj\n{head}".encode() + (stream + tail.encode() if tail else b"")
            out += b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        path.write_bytes(bytes(out))
