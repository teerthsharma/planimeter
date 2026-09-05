"""Regenerates every file in assets/ from real input and a live run.

    python realdata.py fetch --set plans      # two of the five need this first
    python assets.py                          # the five assets, then the PNG
    python assets.py --check                  # the face walk against closed forms

The icon in `control.svg` is committed under `corpus/real/sample/`; the two
Wikimedia Commons floor plans are not, and arrive by the pinned recipe above.

Nothing here is transcribed. Each picture parses a committed or downloaded file,
runs planimeter on it, and draws what came back; the integers in the corner are
the integers the run returned, and the script raises rather than draw geometry
that does not reproduce them.

The face polygons are the one thing planimeter itself does not hand back.
`faces` is E - V + C, an identity over the arrangement rather than a traversal,
so a picture that wants to shade the regions has to walk them. The walk here is
the ordinary half-edge rotation, and `arrangement()` checks that it recovers the
run's own `pieces` and `faces` before a single polygon is drawn.

PALETTE - six values, one meaning each, identical in every asset:

    #0d1117  ground     GitHub's own dark canvas, so nothing glares
    #e6edf3  ink        the drawing exactly as the file contains it
    #3fb950  certified  an answer, and every region that answer covers
    #f85149  site       the coordinate the answer turns on
    #d29922  budget     this machine ran out of room; not a fact about the drawing
    #8b949e  muted      labels, provenance, and another method's reading

Sizes are chosen for GitHub's ~890 px content column: an asset 1600 px wide
displays at 0.56x, so no type here is set below 26 px.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
COMMONS = os.path.join(HERE, "corpus", "real", "commons")
SAMPLE = os.path.join(HERE, "corpus", "real", "sample")

GROUND, INK, CERT, SITE, BUDGET, MUTED = (
    "#0d1117", "#e6edf3", "#3fb950", "#f85149", "#d29922", "#8b949e")
PANEL, GRID = "#161b22", "#30363d"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SANS = "system-ui,-apple-system,Segoe UI,Helvetica,Arial,sans-serif"


# ---------------------------------------------------------------------------
# svg primitives
# ---------------------------------------------------------------------------
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def T(x, y, s, size=28, fill=INK, anchor="start", family=SANS, weight="400", halo=False):
    # halo: a ground-coloured outline painted under the glyphs, for the two
    # labels that have to sit on top of a rule.
    h = (' stroke="%s" stroke-width="7" paint-order="stroke" '
         'stroke-linejoin="round"' % GROUND) if halo else ""
    return ('<text x="%.1f" y="%.1f" font-size="%g" fill="%s" text-anchor="%s" '
            'font-family="%s" font-weight="%s"%s>%s</text>'
            % (x, y, size, fill, anchor, family, weight, h, esc(s)))


def RECT(x, y, w, h, fill="none", stroke="none", sw=2, rx=0, op=None):
    o = ' fill-opacity="%s"' % op if op is not None else ""
    return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="%s" '
            'stroke-width="%g" rx="%g"%s/>' % (x, y, w, h, fill, stroke, sw, rx, o))


def LINE(x1, y1, x2, y2, c=INK, w=2, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%g" '
            'stroke-linecap="round"%s/>' % (x1, y1, x2, y2, c, w, d))


def CIRC(x, y, r, fill="none", stroke=SITE, sw=3):
    return ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="%s" stroke-width="%g"/>'
            % (x, y, r, fill, stroke, sw))


def write(name, body, w, h):
    p = os.path.join(OUT, name)
    doc = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" '
           'height="%d">\n<rect width="%d" height="%d" fill="%s"/>\n%s\n</svg>\n'
           % (w, h, w, h, w, h, GROUND, "\n".join(body)))
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    print("  %-20s %6.1f kB  %dx%d" % (name, os.path.getsize(p) / 1000.0, w, h))
    return p


def eng(x, sig=3):
    return ("%." + str(sig) + "g") % x


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------
def arrangement(path, max_vertices=None):
    """(verdict, points, edges, bounded face cycles) for a file that certifies.

    Clustering and subdivision are re-derived at the run's own certified radius,
    then checked against the run: same V, E, pieces, faces, or raise.
    """
    import planimeter
    from planimeter.arrange import near_incidences, pair_budget, vertex_edge_spectrum
    from planimeter.count import count
    from planimeter.read import segments
    from planimeter.snap import dedup_exact, window_from_grid

    c = planimeter.chi(path, max_vertices=max_vertices)
    if getattr(c, "status", "") != "CERTIFIED":
        raise SystemExit("%s did not certify: %s" % (path, getattr(c, "reason", "?")))
    seg = segments(path).seg
    pts, flat = dedup_exact(seg.reshape(-1, 2))
    ends = flat.reshape(len(seg), 2)
    ve = vertex_edge_spectrum(pts, ends, budget=pair_budget(max_vertices))
    w = window_from_grid(pts, c.radius, extra=ve, max_vertices=max_vertices)
    lab = np.asarray(w.labels)
    P = pts[np.asarray(w.reps)]

    coarse = {}
    for k in range(len(ends)):
        a, b = int(lab[ends[k, 0]]), int(lab[ends[k, 1]])
        coarse.setdefault((min(a, b), max(a, b)), k)
    ce = np.array(list(coarse.keys()), dtype=np.int64).reshape(-1, 2)
    ei, vi, d, t = near_incidences(P, ce, w.t_above)
    splits = {}
    for k in np.nonzero(d == 0.0)[0]:
        splits.setdefault(int(ei[k]), []).append((float(t[k]), int(vi[k])))
    edges = set()
    for e in range(len(ce)):
        chain = ([int(ce[e, 0])] + [v for _, v in sorted(splits.get(e, []))]
                 + [int(ce[e, 1])])
        for a, b in zip(chain, chain[1:]):
            edges.add((min(a, b), max(a, b)))
    edges = sorted(edges)

    got = count(len(P), edges)
    if (got.v, got.e, got.pieces, got.faces) != (c.v, c.e, c.pieces, c.faces):
        raise SystemExit("rebuilt arrangement %r does not match the run (%d,%d,%d,%d)"
                         % (tuple(got), c.v, c.e, c.pieces, c.faces))
    cyc = bounded_faces(P, edges)
    if len(cyc) != c.faces:
        raise SystemExit("face walk found %d bounded cycles, the run says %d faces"
                         % (len(cyc), c.faces))
    return c, P, edges, cyc


def bounded_faces(P, edges):
    """The bounded faces of a planar straight-line graph, as vertex cycles.

    Half-edge rotation: arriving at v from u, leave by the neighbour one step
    clockwise from u. Under that rule a bounded face comes out with positive
    shoelace area in these (y-down) coordinates and an unbounded one negative,
    which `_selfcheck` pins against the square and the T-junction.
    """
    P = np.asarray(P, dtype=np.float64)
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    rank = {}
    for u, ns in adj.items():
        ns.sort(key=lambda v: math.atan2(P[v][1] - P[u][1], P[v][0] - P[u][0]))
        rank[u] = {v: i for i, v in enumerate(ns)}
    seen, out = set(), []
    for a, b in edges:
        for he in ((a, b), (b, a)):
            if he in seen:
                continue
            walk, cur = [], he
            while cur not in seen:
                seen.add(cur)
                walk.append(cur[0])
                u, v = cur
                ns = adj[v]
                cur = (v, ns[(rank[v][u] - 1) % len(ns)])
            p = P[walk]
            if np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]) > 0:
                out.append(walk)
    return out


def round6_graph(seg, nd=6):
    """What a round-to-six-decimals snap sees: its vertices and its edges.

    Same keying as `bench._round6_graph`, which is the arm RESULTS.md reports;
    returned with coordinates so the reading can be drawn rather than asserted.
    """
    key, edges = {}, set()
    for a, b in seg:
        ids = []
        for p in (a, b):
            k = (round(float(p[0]), nd), round(float(p[1]), nd))
            ids.append(key.setdefault(k, len(key)))
        if ids[0] != ids[1]:
            edges.add((min(ids), max(ids)))
    P = np.array(sorted(key, key=key.get), dtype=np.float64)
    return P, sorted(edges)


def fit(P, box):
    """A uniform scale placing a point cloud's bbox centred inside box."""
    x0, y0, w, h = box
    P = np.asarray(P, dtype=np.float64)
    lo, hi = P.min(0), P.max(0)
    span = np.maximum(hi - lo, 1e-12)
    s = min(w / span[0], h / span[1])
    ox = x0 + (w - span[0] * s) / 2.0 - lo[0] * s
    oy = y0 + (h - span[1] * s) / 2.0 - lo[1] * s
    return (lambda p: (float(p[0]) * s + ox, float(p[1]) * s + oy)), s


def poly(P, cyc, f, fill, op=0.18):
    d = "".join(("M%.1f %.1f" if i == 0 else "L%.1f %.1f") % f(P[v])
                for i, v in enumerate(cyc)) + "Z"
    return '<path d="%s" fill="%s" fill-opacity="%g"/>' % (d, fill, op)


def wires(P, edges, f, colour=INK, w=2.0):
    d = "".join("M%.1f %.1fL%.1f %.1f" % (f(P[a]) + f(P[b])) for a, b in edges)
    return ('<path d="%s" fill="none" stroke="%s" stroke-width="%g" '
            'stroke-linecap="round"/>' % (d, colour, w))


# ---------------------------------------------------------------------------
# 1. hero - the product doing its job on a real floor plan
# ---------------------------------------------------------------------------
def hero(W=1600, H=900):
    from planimeter.read import segments
    src = os.path.join(COMMONS, "Akori_church_plan.svg")
    c, P, edges, cyc = arrangement(src, max_vertices=3000)
    n_curves = segments(src).n_curves
    f, _ = fit(P, (72, 182, 856, 610))

    g = [T(64, 76, "planimeter", 46, INK, family=MONO, weight="700"),
         T(378, 76, "three integers for a geometry file, and the radius that decided them",
           28, MUTED),
         LINE(64, 112, W - 64, 112, GRID, 2)]
    g += [poly(P, k, f, CERT, 0.20) for k in cyc]
    g.append(wires(P, edges, f, INK, 2.0))
    g.append(T(72, 158, "Akori_church_plan.svg", 27, MUTED, family=MONO))
    g.append(T(928, 158, "%d segments, %d curves flattened" % (len(segments(src).seg), n_curves),
               27, MUTED, anchor="end", family=MONO))

    x = 1000
    g.append(RECT(x, 152, 536, 66, PANEL, CERT, 2, 6))
    g.append(T(x + 26, 196, "CERTIFIED", 34, CERT, family=MONO, weight="700"))
    rows = [(c.pieces, "pieces", "connected components"),
            (c.faces, "faces", "bounded regions enclosed"),
            (c.chi, "chi", "pieces minus faces")]
    y = 260
    for n, name, gloss in rows:
        g.append(T(x + 148, y + 88, str(n), 112, CERT, anchor="end", family=MONO, weight="700"))
        g.append(T(x + 176, y + 58, name, 42, INK, family=MONO))
        g.append(T(x + 176, y + 94, gloss, 26, MUTED))
        y += 134
    g.append(LINE(x, 690, W - 64, 690, GRID, 2))
    g.append(T(x, 734, "radius  %s" % eng(c.radius), 28, INK, family=MONO))
    g.append(T(x, 772, "window  [%s, %s)" % (eng(c.t_below, 4), eng(c.t_above, 4)),
               28, INK, family=MONO))
    g.append(T(x, 810, "ratio   %s and empty" % format(round(c.ratio), ","),
               28, MUTED, family=MONO))
    g.append(T(64, 862, "$", 30, MUTED, family=MONO))
    g.append(T(94, 862, "planimeter Akori_church_plan.svg --max-vertices 3000",
               30, INK, family=MONO))
    write("hero.svg", g, W, H)
    return c, P, edges, cyc


# ---------------------------------------------------------------------------
# 2. control - the tool right where the obvious method is wrong
# ---------------------------------------------------------------------------
def control(W=1600, H=900):
    import bench
    from planimeter.read import segments
    src = os.path.join(SAMPLE, "feather__layout.svg")
    c, P, edges, cyc = arrangement(src)
    seg = segments(src).seg
    P6, e6 = round6_graph(seg)
    cyc6 = bounded_faces(P6, e6)
    if len(cyc6) != bench.arm_round6(seg):
        raise SystemExit("round-6 face walk %d, bench.arm_round6 %d"
                         % (len(cyc6), bench.arm_round6(seg)))

    g = [T(64, 76, "the same 70 segments, counted two ways", 40, INK, weight="600"),
         T(64, 120, "feather__layout.svg, one of the 30 icons committed to corpus/",
           28, MUTED, family=MONO),
         LINE(64, 152, W - 64, 152, GRID, 2)]

    boxes = ((110, 212, 560, 400), (870, 212, 560, 400))
    fl, _ = fit(P, boxes[0])
    fr, _ = fit(P6, boxes[1])
    deg = {}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    junc = [v for v, d in deg.items() if d >= 3]

    # the regions abut here, so a uniform wash reads as one shape. Number them.
    def label_faces(pts, cycles, f, colour):
        out = []
        for i, k in enumerate(sorted(cycles, key=lambda k: -len(k)), 1):
            cx, cy = np.asarray([f(pts[v]) for v in k]).mean(0)
            out.append(T(cx, cy + 20, str(i), 58, colour, anchor="middle",
                         family=MONO, weight="700"))
        return out

    g += [poly(P, k, fl, CERT, 0.22) for k in cyc]
    g.append(wires(P, edges, fl, INK, 5.0))
    g += [CIRC(*(fl(P[v]) + (14, "none", CERT, 4))) for v in junc]
    g += label_faces(P, cyc, fl, CERT)

    g += [poly(P6, k, fr, MUTED, 0.16) for k in cyc6]
    g.append(wires(P6, e6, fr, INK, 5.0))
    g += [CIRC(*(fr(P[v]) + (14, GROUND, SITE, 4))) for v in junc]
    g += label_faces(P6, cyc6, fr, MUTED)

    panels = ((110, "planimeter", c.faces, CERT,
               "4 junctions subdivided,  E 70 -> %d" % c.e),
              (870, "a round-6 snap and a union-find", len(cyc6), MUTED,
               "4 junctions missed,  E 70"))
    for x0, who, n, colour, note in panels:
        g.append(T(x0, 202, who, 30, colour, family=MONO, weight="600"))
        g.append(T(x0, 668, note, 27, CERT if colour == CERT else SITE, family=MONO))
        g.append(T(x0 + 560, 742, str(n), 118, colour, anchor="end", family=MONO,
                   weight="700"))
        g.append(T(x0, 712, "bounded", 32, INK, family=MONO))
        g.append(T(x0, 748, "regions", 32, INK, family=MONO))
    g.append(T(W / 2, 380, "vs", 36, MUTED, anchor="middle", family=MONO))
    g.append(LINE(64, 796, W - 64, 796, GRID, 2))
    g.append(T(64, 842, "raster control at 4096 px, same file:  %d" % c.faces,
               27, MUTED, family=MONO))
    g.append(T(64, 878, "7 of the 30 sample files disagree; the raster sides with "
               "planimeter on all 7", 27, MUTED, family=MONO))
    write("control.svg", g, W, H)


# ---------------------------------------------------------------------------
# 3. refusal - the tool declining, and naming the coordinate
# ---------------------------------------------------------------------------
def refuse(W=1600, H=880):
    import planimeter
    from planimeter.read import segments
    src = os.path.join(COMMONS, "Floor_plans_of_Buda_Castle_he.svg")
    r = planimeter.chi(src)
    if getattr(r, "status", "") != "REFUSED" or r.reason != "VERTEX_NEAR_EDGE":
        raise SystemExit("%s no longer refuses VERTEX_NEAR_EDGE: %r" % (src, r))
    site = r.look_at[0]
    band = float(r.detail.split(", ")[-1].rstrip(")"))
    seg = segments(src).seg
    pts = seg.reshape(-1, 2)
    f, _ = fit(pts, (72, 196, 630, 380))

    g = [T(64, 76, "when it cannot answer, it says which coordinate to go and look at",
           40, INK, weight="600"),
         T(64, 120, "Floor_plans_of_Buda_Castle_he.svg, %d segments" % len(seg),
           28, MUTED, family=MONO),
         LINE(64, 152, W - 64, 152, GRID, 2)]
    g.append(wires(pts, [(2 * i, 2 * i + 1) for i in range(len(seg))], f, INK, 3.0))
    sx, sy = f(site["xy"])
    zx, zy = 800, 268
    g.append(LINE(sx, sy, zx, zy, SITE, 2, dash="6 8"))
    g.append(CIRC(sx, sy, 26, "none", SITE, 4))

    # the gap, drawn at a size a reader can see: 7e-15 of a 700-unit drawing is
    # nothing any renderer can show, which is the whole point.
    g.append(CIRC(zx, zy, 96, GROUND, SITE, 3))
    g.append(LINE(zx - 74, zy + 30, zx + 74, zy + 30, INK, 7))
    g.append(LINE(zx - 8, zy - 58, zx - 8, zy + 20, INK, 7))
    g.append(LINE(zx - 44, zy + 20, zx + 34, zy + 20, SITE, 3, dash="4 5"))
    g.append(T(zx, zy + 138, "d = %s" % eng(site["d"], 2), 30, SITE, anchor="middle",
               family=MONO, weight="600"))

    x = 920
    g.append(RECT(x, 186, W - 64 - x, 78, PANEL, SITE, 2, 6))
    g.append(T(x + 26, 238, "REFUSED", 40, SITE, family=MONO, weight="700"))
    g.append(T(x + 232, 238, r.reason, 32, SITE, family=MONO))
    lines = [("look at", "(%g, %g)" % tuple(site["xy"])),
             ("element", site["element"]),
             ("on edge", site["edge"]),
             ("distance", eng(site["d"], 2)),
             ("band", "(0, %s)" % eng(band, 3)),
             ("action", "move this end onto the wall,"),
             ("", "or away from it by more than"),
             ("", eng(band, 3))]
    y = 318
    for k, v in lines:
        if k:
            g.append(T(x, y, k, 28, MUTED, family=MONO))
        g.append(T(x + 172, y, v, 28, INK, family=MONO))
        y += 42
    g.append(T(72, 668, "not zero, so it cannot subdivide the wall. not outside the band, "
               "so it cannot be a separate", 28, MUTED))
    g.append(T(72, 706, "vertex either. no snap radius makes this drawing unambiguous, "
               "so there is no integer to give.", 28, MUTED))

    # the honest limit, in the two colours that mean different things
    bx, by, bw = 72, 800, W - 136
    g.append(LINE(64, 744, W - 64, 744, GRID, 2))
    g.append(T(bx, 784, "96 Wikimedia Commons floor plans at the default ceiling, "
               "0 answered", 27, MUTED, family=MONO))
    xo = bx
    for n, colour, label, side in ((88, BUDGET, "88 out of room on this machine", "start"),
                                   (8, SITE, "8 go and look", "end")):
        w = bw * n / 96.0
        g.append(RECT(xo, by, w - 6, 32, colour, "none", 0, 4, 0.85))
        g.append(T(xo + 2 if side == "start" else xo + w - 6, by + 62, label, 26,
                   colour, anchor=side, family=MONO))
        xo += w
    write("refuse.svg", g, W, H)


# ---------------------------------------------------------------------------
# 4. mechanism - where the radius comes from
# ---------------------------------------------------------------------------
def mechanism(W=1600, H=760):
    import planimeter
    from planimeter.arrange import pair_budget, vertex_edge_spectrum
    from planimeter.read import segments
    from planimeter.snap import dedup_exact, spectrum

    src = os.path.join(COMMONS, "Akori_church_plan.svg")
    c = planimeter.chi(src, max_vertices=3000)
    seg = segments(src).seg
    pts, flat = dedup_exact(seg.reshape(-1, 2))
    ends = flat.reshape(len(seg), 2)
    ve = vertex_edge_spectrum(pts, ends, budget=pair_budget(3000))
    s, _, _ = spectrum(pts, ve, max_vertices=3000)

    x0, x1, ax = 130, W - 130, 470
    lo, hi = float(s[0]) * 0.4, float(s[-1]) * 2.5
    lg = lambda v: x0 + (x1 - x0) * (math.log10(v) - math.log10(lo)) / (
        math.log10(hi) - math.log10(lo))

    g = [T(64, 76, "every separation in the drawing, and the empty band between them",
           40, INK, weight="600"),
         T(64, 120, "Akori_church_plan.svg, %s separations over %d decades"
           % (format(len(s), ","), round(math.log10(s[-1] / s[0]))),
           28, MUTED, family=MONO),
         LINE(64, 152, W - 64, 152, GRID, 2)]

    wl, wr = lg(c.t_below), lg(c.t_above)
    g.append(RECT(wl, 236, wr - wl, ax - 236, CERT, "none", 0, 0, 0.13))
    g.append(LINE(wl, 236, wl, ax, CERT, 3))
    g.append(LINE(wr, 236, wr, ax, CERT, 3))

    # 855k separations over 1,340 px, so bin to the pixel and let bar height
    # carry how many landed there. One element per separation is a 95 MB file in
    # which every tick is drawn on top of another tick.
    col = np.clip(np.floor((np.log10(s) - math.log10(lo)) * (x1 - x0)
                           / (math.log10(hi) - math.log10(lo))).astype(np.int64),
                  0, x1 - x0 - 1)
    n = np.bincount(col, minlength=x1 - x0).astype(np.float64)
    hgt = 14 + 186 * np.log1p(n) / math.log1p(n.max())
    for i in np.nonzero(n)[0]:
        g.append(LINE(x0 + i, ax, x0 + i, ax - hgt[i], INK, 1.6))
    g.append(LINE(x0, ax, x1, ax, GRID, 3))

    dec = range(int(math.ceil(math.log10(lo))), int(math.floor(math.log10(hi))) + 1)
    for d in dec:
        xd = lg(10.0 ** d)
        g.append(LINE(xd, ax, xd, ax + 12, GRID, 2))
        if d % 2 == 0:
            g.append(T(xd, ax + 46, "1e%d" % d, 26, MUTED, anchor="middle", family=MONO))

    rx = lg(c.radius)
    g.append(LINE(rx, 200, rx, ax, CERT, 3, dash="8 8"))
    g.append(T(rx, 186, "radius %s" % eng(c.radius), 30, CERT, anchor="middle",
               family=MONO, weight="700"))
    g.append(T(wl + 16, 300, eng(c.t_below, 4), 28, INK, family=MONO))
    g.append(T(wr - 16, 300, eng(c.t_above, 4), 28, INK, anchor="end", family=MONO))
    g.append(T((wl + wr) / 2, 356, "%s x wide" % format(round(c.ratio), ","), 30, CERT,
               anchor="middle", family=MONO, weight="700", halo=True))
    g.append(T((wl + wr) / 2, 396, "and empty", 30, CERT, anchor="middle", family=MONO,
               halo=True))
    g.append(T(x0, 224, "float64 floor", 27, MUTED, family=MONO))
    g.append(T(x1, 224, "the drawing itself", 27, MUTED, anchor="end", family=MONO))

    g.append(LINE(64, 588, W - 64, 588, GRID, 2))
    g.append(T(64, 634, "each bar is a distance the answer could turn on: a gap between two "
               "endpoints, or an endpoint's distance", 28, MUTED))
    g.append(T(64, 672, "to a wall it does not touch. the widest empty band between two of "
               "them is the certified window, and", 28, MUTED))
    g.append(T(64, 710, "every snap radius inside it gives the same %d, %d, %d."
               % (c.pieces, c.faces, c.chi), 28, INK))
    write("mechanism.svg", g, W, H)


# ---------------------------------------------------------------------------
# 5. social preview - 1280x640, the same plan and the same integers
# ---------------------------------------------------------------------------
def social(cached, W=1280, H=640):
    c, P, edges, cyc = cached
    f, _ = fit(P, (64, 150, 600, 420))
    g = [T(60, 84, "planimeter", 46, INK, family=MONO, weight="700"),
         LINE(60, 110, W - 60, 110, GRID, 2)]
    g += [poly(P, k, f, CERT, 0.20) for k in cyc]
    g.append(wires(P, edges, f, INK, 1.8))
    x = 748
    g.append(T(x, 190, "three integers for a", 34, MUTED))
    g.append(T(x, 232, "geometry file, and the", 34, MUTED))
    g.append(T(x, 274, "radius that decided them", 34, MUTED))
    y = 330
    for n, name in ((c.pieces, "pieces"), (c.faces, "faces"), (c.chi, "chi")):
        g.append(T(x + 90, y + 60, str(n), 76, CERT, anchor="end", family=MONO, weight="700"))
        g.append(T(x + 116, y + 60, name, 40, INK, family=MONO))
        y += 84
    g.append(T(x, 604, "radius %s, window ratio %s" % (eng(c.radius), format(round(c.ratio), ",")),
               26, MUTED, family=MONO))
    g.append(T(60, 604, "Akori_church_plan.svg", 26, MUTED, family=MONO))
    return write("social-preview.svg", g, W, H)


EDGES = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")


def rasterise(svg, W=1280, H=640):
    """GitHub's social preview slot takes a raster, so one asset ships twice."""
    exe = next((p for p in EDGES if os.path.exists(p)), None)
    if exe is None:
        print("  social-preview.png   SKIPPED (no Edge found; any renderer will do)")
        return
    png = os.path.join(OUT, "social-preview.png")
    tmp = os.path.join(HERE, ".donotcommit", "shot")
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--window-size=%d,%d" % (W, H),
                    "--screenshot=" + png, "--user-data-dir=" + tmp,
                    "file:///" + svg.replace("\\", "/")],
                   check=True, capture_output=True)
    print("  %-20s %6.1f kB  %dx%d" % ("social-preview.png",
                                       os.path.getsize(png) / 1000.0, W, H))


# ---------------------------------------------------------------------------
def _selfcheck():
    """The face walk against three closed forms count.py already pins."""
    sq = np.array([[0., 0.], [10., 0.], [10., 10.], [0., 10.]])
    assert len(bounded_faces(sq, [(0, 1), (1, 2), (2, 3), (0, 3)])) == 1
    tj = np.array([[0., 0.], [10., 0.], [10., 10.], [0., 10.], [5., 0.], [5., 10.]])
    assert len(bounded_faces(tj, [(0, 4), (1, 4), (1, 2), (2, 5), (3, 5), (0, 3),
                                  (4, 5)])) == 2
    tree = np.array([[0., 0.], [10., 0.], [20., 0.], [10., 10.]])
    assert len(bounded_faces(tree, [(0, 1), (1, 2), (1, 3)])) == 0
    two = np.array([[0., 0.], [4., 0.], [4., 4.], [0., 4.],
                    [10., 0.], [14., 0.], [14., 4.], [10., 4.]])
    assert len(bounded_faces(two, [(0, 1), (1, 2), (2, 3), (0, 3),
                                   (4, 5), (5, 6), (6, 7), (4, 7)])) == 2
    print("face walk OK - square 1, T-junction 2, tree 0, two squares 2")


def main():
    if "--check" in sys.argv:
        return _selfcheck()
    _selfcheck()
    sys.path.insert(0, HERE)
    os.makedirs(OUT, exist_ok=True)
    for f in ("Akori_church_plan.svg", "Floor_plans_of_Buda_Castle_he.svg"):
        if not os.path.exists(os.path.join(COMMONS, f)):
            raise SystemExit("%s is not here yet; run `python realdata.py fetch "
                             "--set plans` first" % f)
    print("assets/")
    cached = hero()
    control()
    refuse()
    mechanism()
    rasterise(social(cached))


if __name__ == "__main__":
    main()
