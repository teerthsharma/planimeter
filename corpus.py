"""The corpus: figures whose answer is known before any code runs.

Not inside the package. Users never install this; `bench.py` and the tests
import it, and it is the only place a "truth" value is allowed to come from.

Every family here is emitted from a recipe whose `(V, E, pieces, faces, chi)`
was derived on paper. Nothing in this file imports `planimeter.count`,
`planimeter.snap` or `planimeter.arrange` - `test_corpus_has_no_shared_arithmetic`
parses this file's AST and asserts it - so a figure and the tool that counts it
have no arithmetic in common and a benchmark cannot score the package against
itself.

Three strata:

  clean    exact round coordinates, exact coincidences. The normal case for
           model-written geometry. Expected: CERTIFIED, nothing merged.
           Anything else here is a bug, not a refusal.
  jitter   the same figures with the same truth and worse coordinates: every
           *shared* vertex split by sigma, with sigma set as a fraction of the
           figure's own feature gap g, so `sigma/g` means the same thing across
           families of different sizes. The only stratum where the snap decides
           the answer, and the only one an accuracy headline may quote.
  found    real agent-written SVGs, truth by a second method, dated. Not
           synthesised here and not synthesisable: see `found()`.

Self-check:  python corpus.py
"""

from __future__ import annotations

import json
import math
import pathlib
import zlib
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

# (segments, (V, E, pieces, faces, chi))
Figure = Tuple[np.ndarray, Tuple[int, int, int, int, int]]

HERE = pathlib.Path(__file__).resolve().parent
FOUND = HERE / "corpus" / "found"

# sigma/g levels for the jitter stratum. The ceiling is measured, not chosen:
# at sigma/g = 1e-2 the whole stratum is still exact-or-refused, and at 5e-2 six
# draws of 108 come back with a different integer - a square whose corners are
# half a unit apart at side 10 is honestly four disjoint segments, and the file
# says so. That is inside the convention and outside this schedule, and
# `test_a_figure_jittered_past_its_own_feature_gap_is_a_different_figure` pins
# the boundary rather than letting a reader find it as a wrong answer.
RATIOS: Tuple[float, ...] = (1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2)
SEEDS = 10


# --------------------------------------------------------------------------
# construction helpers
# --------------------------------------------------------------------------

def S(*pairs) -> np.ndarray:
    return np.array(pairs, dtype=np.float64).reshape(-1, 2, 2)


def square(x: float = 0.0, y: float = 0.0, s: float = 10.0) -> np.ndarray:
    return S([[x, y], [x + s, y]], [[x + s, y], [x + s, y + s]],
             [[x + s, y + s], [x, y + s]], [[x, y + s], [x, y]])


def grid(k: int, h: float = 1.0) -> np.ndarray:
    """k x k cells of unit squares, emitted one cell edge at a time."""
    segs = []
    for i in range(k + 1):
        for j in range(k):
            segs.append([[i * h, j * h], [i * h, (j + 1) * h]])
            segs.append([[j * h, i * h], [(j + 1) * h, i * h]])
    return np.array(segs, dtype=np.float64)


def theta(k: int) -> np.ndarray:
    """Two poles joined by k internally disjoint two-segment paths."""
    segs = []
    for i in range(k):
        y = (i - (k - 1) / 2.0) * 4.0
        segs += [[[0.0, 0.0], [5.0, y]], [[5.0, y], [10.0, 0.0]]]
    return np.array(segs, dtype=np.float64)


def chain(k: int) -> np.ndarray:
    segs = [[[i * 10.0, 0.0], [i * 10.0 + 10.0, 0.0]] for i in range(k)]
    segs += [[[i * 10.0, 10.0], [i * 10.0 + 10.0, 10.0]] for i in range(k)]
    segs += [[[i * 10.0, 0.0], [i * 10.0, 10.0]] for i in range(k + 1)]
    return np.array(segs, dtype=np.float64)


def comb(k: int) -> np.ndarray:
    """k teeth meeting the interior of a spine. A tree: no face, k+2 leaves."""
    segs = [[[0.0, 0.0], [10.0 * (k + 1), 0.0]]]
    segs += [[[10.0 * (i + 1), 0.0], [10.0 * (i + 1), 10.0]] for i in range(k)]
    return np.array(segs, dtype=np.float64)


def ladder(k: int) -> np.ndarray:
    """k rungs meeting the interiors of two rails."""
    top = 10.0 * (k + 1)
    segs = [[[0.0, 0.0], [0.0, top]], [[10.0, 0.0], [10.0, top]]]
    segs += [[[0.0, 10.0 * (i + 1)], [10.0, 10.0 * (i + 1)]] for i in range(k)]
    return np.array(segs, dtype=np.float64)


def tree(n: int) -> np.ndarray:
    """A path of n vertices: n-1 edges, no cycle, two leaves."""
    return np.array([[[i * 10.0, 0.0], [(i + 1) * 10.0, 0.0]] for i in range(n - 1)],
                    dtype=np.float64)


def _star_points(r: float = 10.0) -> List[List[float]]:
    return [[r * math.cos(math.radians(90 + 72 * i)),
             r * math.sin(math.radians(90 + 72 * i))] for i in range(5)]


def pentagram_raw() -> np.ndarray:
    """Five chords crossing at five points the file does not contain. A refusal,
    not a family: planimeter never invents an intersection."""
    P = _star_points()
    return S(*[[P[i], P[(i + 2) % 5]] for i in range(5)])


def pentagram_noded() -> np.ndarray:
    """The same star with the five crossings written into the file.

    Each crossing is computed once and shared bitwise by both chords that meet
    there, so the coincidence is exact and no snap is needed to see it.
    """
    P = _star_points()
    chords = [(P[i], P[(i + 2) % 5]) for i in range(5)]
    cross: Dict[Tuple[int, int], Tuple[float, float]] = {}
    for i in range(5):
        for j in range(i + 1, 5):
            hit = _intersect(chords[i], chords[j])
            if hit is not None:
                cross[(i, j)] = hit
    out: List[List[List[float]]] = []
    for i, (a, b) in enumerate(chords):
        cuts = [cross[k] for k in cross if i in k]
        a = (float(a[0]), float(a[1]))
        b = (float(b[0]), float(b[1]))
        cuts.sort(key=lambda p: (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2)
        run = [a] + cuts + [b]
        out += [[list(p), list(q)] for p, q in zip(run, run[1:])]
    return np.array(out, dtype=np.float64)


def _intersect(u, v) -> Optional[Tuple[float, float]]:
    """The crossing of two open segments, or None. Used only to *write* a noded
    figure, never to count one."""
    (x1, y1), (x2, y2) = u
    (x3, y3), (x4, y4) = v
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if d == 0.0:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    s = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if not (1e-9 < t < 1 - 1e-9 and 1e-9 < s < 1 - 1e-9):
        return None
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


# --------------------------------------------------------------------------
# the closed-form families
# --------------------------------------------------------------------------

def _families() -> Dict[str, Figure]:
    f: Dict[str, Figure] = {}
    f["segment"] = (S([[0, 0], [10, 0]]), (2, 1, 1, 0, 1))
    f["triangle"] = (S([[0, 0], [10, 0]], [[10, 0], [5, 8.66]], [[5, 8.66], [0, 0]]),
                     (3, 3, 1, 1, 0))
    f["square"] = (square(), (4, 4, 1, 1, 0))
    f["two disjoint squares"] = (np.concatenate([square(), square(100.0, 0.0)]),
                                 (8, 8, 2, 2, 0))
    f["two squares sharing an edge"] = (
        np.concatenate([square(), S([[10, 0], [20, 0]], [[20, 0], [20, 10]],
                                    [[20, 10], [10, 10]])]), (6, 7, 1, 2, -1))
    f["square + diagonals + centre"] = (
        np.concatenate([square(), S([[0, 0], [5, 5]], [[5, 5], [10, 10]],
                                    [[10, 0], [5, 5]], [[5, 5], [0, 10]])]),
        (5, 8, 1, 4, -3))
    f["planar K4"] = (S([[0, 0], [10, 0]], [[10, 0], [5, 8.66]], [[5, 8.66], [0, 0]],
                        [[0, 0], [5, 2.887]], [[10, 0], [5, 2.887]],
                        [[5, 8.66], [5, 2.887]]), (4, 6, 1, 3, -2))
    f["nested unconnected squares"] = (
        np.concatenate([square(0, 0, 30.0), square(10, 10, 10.0)]), (8, 8, 2, 2, 0))
    # The four families every input design lacked, and where the two worst
    # errors lived: a vertex in another segment's interior, and exact overlap.
    f["T-junction"] = (np.concatenate([square(), S([[5, 0], [5, 10]])]), (6, 7, 1, 2, -1))
    f["H"] = (S([[0, 0], [0, 20]], [[10, 0], [10, 20]], [[0, 10], [10, 10]]),
              (6, 5, 1, 0, 1))
    f["collinear overlap"] = (S([[0, 0], [10, 0]], [[3, 0], [7, 0]]), (4, 3, 1, 0, 1))
    f["exact duplicate segment"] = (S([[0, 0], [10, 0]], [[0, 0], [10, 0]]), (2, 1, 1, 0, 1))
    f["pentagram noded"] = (pentagram_noded(), (10, 15, 1, 6, -5))
    for n in (2, 3, 5, 8):
        f["tree(%d)" % n] = (tree(n), (n, n - 1, 1, 0, 1))
    for k in range(2, 13):
        f["grid(%d)" % k] = (grid(k), ((k + 1) ** 2, 2 * k * (k + 1), 1, k * k, 1 - k * k))
    for k in (2, 3, 4, 5):
        f["theta(%d)" % k] = (theta(k), (2 + k, 2 * k, 1, k - 1, 2 - k))
        f["chain(%d)" % k] = (chain(k), (2 * (k + 1), 3 * k + 1, 1, k, 1 - k))
        f["comb(%d)" % k] = (comb(k), (2 * k + 2, 2 * k + 1, 1, 0, 1))
        # chi = V - E = (2k+4) - (3k+2) = 2 - k. The specification table prints
        # 3 - k, which its own V and E columns contradict; the arithmetic wins.
        f["ladder(%d)" % k] = (ladder(k), (2 * k + 4, 3 * k + 2, 1, k - 1, 2 - k))
    return f


FAMILIES: Dict[str, Figure] = _families()


def disjoint_union(a: str, b: str) -> Figure:
    """A + B translated clear of A. Every quantity adds; that is the closed form
    the additivity test scores against."""
    sa, ta = FAMILIES[a]
    sb, tb = FAMILIES[b]
    dx = float(sa.reshape(-1, 2)[:, 0].max() - sb.reshape(-1, 2)[:, 0].min()) + 100.0
    shifted = sb + np.array([dx, 0.0])
    return (np.concatenate([sa, shifted]), tuple(x + y for x, y in zip(ta, tb)))


# --------------------------------------------------------------------------
# figures whose truth is a refusal
# --------------------------------------------------------------------------

def near_touching_squares(gap: float = 2.2e-6) -> np.ndarray:
    """Two 10-unit squares whose facing walls miss by `gap`. Truth as a drawing
    is `pieces 2, faces 2`; truth under the certified identification is not.

    This is the figure where the rule and the reader disagree, and the
    disagreement is not a bug in either. The only two lengths in the file are
    `gap` and 10, so the widest window is `(gap, 10)`; when `10/gap >= RHO` the
    rule reads the gap as noise, merges the two facing corners and answers
    `pieces 1, faces 2` with `n_merged = 2` printed. Measured boundary, RHO = 10:

        gap 0.99  ->  pieces 1, merged 2        gap 1.01  ->  pieces 2, merged 0

    So two squares a tenth of their own size apart fuse, and two squares a ninth
    apart do not, and the constant that decided it is on the verdict. Nothing
    here is hidden by a refusal: uniqueness of the certified scale is not
    claimed, and this is what not claiming it costs.
    """
    return np.concatenate([square(0.0, 0.0, 10.0), square(10.0 + gap, 0.0, 10.0)])


def wall_missing_the_floor(gap: float = 2.2e-6) -> np.ndarray:
    """A crosswall inside a room whose lower end misses the floor by `gap`.

    Its upper end sits exactly on the ceiling, so the file contains no small
    vertex-pair separation anywhere: a certificate quantified over vertex pairs
    alone puts the window at drawing scale and closes the gap silently, and
    `faces` is off by one. Snapped, the crosswall divides the room and `faces`
    is 2; left apart it is a dangle and `faces` is 1. Nothing in the file says
    which, which is why this figure refuses.
    """
    return np.concatenate([square(), S([[5.0, gap], [5.0, 10.0]])])


def curve_unstable_svg(radius: float = 5.0, flatten: int = 16) -> str:
    """A circle and a radial stub whose far end lands between the polygon
    inscribed at N and the one inscribed at 2N.

    At N the stub end sits `radius*(1 - cos(pi/(4N)))` outside a chord and the
    ambiguous band refuses; at 2N the same point is inside and the file counts.
    Two verdicts from one file and one invented number: `CURVE_UNSTABLE`.
    """
    half = math.radians(90.0 / flatten / 2.0)          # half a chord of one arc
    r_in = radius * math.cos(half)                     # the N-polygon's inradius
    r = 0.5 * (r_in + radius * math.cos(half / 2.0))   # between N and 2N
    x, y = r * math.cos(half), r * math.sin(half)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-6 -6 12 12">\n'
            '  <circle id="dial" cx="0" cy="0" r="%.17g"/>\n'
            '  <line id="hand" x1="0" y1="0" x2="%.17g" y2="%.17g"/>\n'
            '</svg>\n' % (radius, x, y))


# name -> (segments, the reason this file is expected to refuse)
REFUSALS: Dict[str, Tuple[np.ndarray, str]] = {
    "pentagram raw": (pentagram_raw(), "EDGES_CROSS"),
    "two segments crossing": (S([[0, 0], [10, 10]], [[0, 10], [10, 0]]), "EDGES_CROSS"),
    "wall missing the floor": (wall_missing_the_floor(), "VERTEX_NEAR_EDGE"),
}

# name -> (segments, the certified reading, the reading a reader expects).
# Figures where the two differ. They are not refusals and they are not bugs;
# they are what "the certificate is about what was checked, not about what was
# meant" costs, and they are listed rather than left for a user to hit.
CONTESTED: Dict[str, Tuple[np.ndarray, Tuple[int, int], Tuple[int, int]]] = {
    # (pieces, faces) certified            (pieces, faces) as drawn
    "squares 1.0 apart": (near_touching_squares(1.0), (1, 2), (2, 2)),
    "squares 2.2e-6 apart": (near_touching_squares(2.2e-6), (1, 2), (2, 2)),
}


# --------------------------------------------------------------------------
# the feature gap, and the jitter stratum
# --------------------------------------------------------------------------

def feature_gap(seg: np.ndarray) -> float:
    """The smallest positive distance the figure resolves: over distinct vertex
    pairs *and* over vertex-to-non-incident-segment pairs.

    Both sets matter and the second is the one that is easy to forget. A
    triangle's apex is 8.66 from its own base while its sides are 10, so a gap
    read off vertex pairs alone is not the gap the figure actually has; and a
    wall that misses a floor leaves no small vertex-pair separation at all.

    Exact zeros are excluded: a T-junction's incidence is a coincidence the
    figure declares, not a gap it resolves.
    """
    P = np.unique(seg.reshape(-1, 2), axis=0)
    if len(P) < 2:
        return float("inf")
    d = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1])
    d[np.triu_indices(len(P))] = np.inf
    best = float(d.min())
    for a, b in seg:
        ab = b - a
        L2 = float(ab @ ab)
        if L2 == 0.0:
            continue
        t = np.clip(((P - a) @ ab) / L2, 0.0, 1.0)
        foot = a + t[:, None] * ab
        dd = np.hypot(P[:, 0] - foot[:, 0], P[:, 1] - foot[:, 1])
        incident = (np.all(P == a, axis=1) | np.all(P == b, axis=1))
        dd = dd[~incident]
        dd = dd[dd > 0.0]
        if len(dd):
            best = min(best, float(dd.min()))
    return best


def jitter(seg: np.ndarray, sigma: float, rng) -> np.ndarray:
    """Re-emit a figure with the same truth and worse coordinates: every vertex
    shared by two or more segment ends is split by a displacement of size sigma.

    Exact incidences - a crosswall end sitting on a wall's interior - are left
    exact, so a T-junction stays a T-junction and the only contested question is
    vertex identity. Perturbing every coordinate instead would change the figure
    and destroy the truth this stratum is measured against.
    """
    out = seg.copy()
    ends = out.reshape(-1, 2)
    seen: Dict[Tuple[float, float], List[int]] = {}
    for i, (x, y) in enumerate(ends):
        seen.setdefault((float(x), float(y)), []).append(i)
    for group in seen.values():
        if len(group) < 2:
            continue
        for i in group:
            a = rng.uniform(0.0, 2.0 * math.pi)
            ends[i] += sigma * np.array([math.cos(a), math.sin(a)])
    return out


def jitter_stratum(names: Optional[Sequence[str]] = None,
                   ratios: Sequence[float] = RATIOS,
                   seeds: int = SEEDS) -> Iterator[Dict[str, object]]:
    """Every family x every sigma/g level x every seed, truth by construction.

    sigma is set as a fraction of the figure's own feature gap, so `sigma/g` is
    the same question asked of a 10-unit square and a 12x12 unit grid; a fixed
    sigma would be a different question per family and the levels would not be
    comparable across the table.
    """
    for name in (names if names is not None else sorted(FAMILIES)):
        seg, truth = FAMILIES[name]
        g = feature_gap(seg)
        if not math.isfinite(g):
            continue
        for ratio in ratios:
            for seed in range(seeds):
                # zlib.crc32 of a formatted string, never hash(): str hashing is
                # salted per interpreter, so hash() made the stratum a different
                # set of draws in every process and no wrong row was reproducible.
                key = ("%s|%.17g|%d" % (name, ratio, seed)).encode()
                rng = np.random.default_rng(zlib.crc32(key))
                yield {"family": name, "ratio": float(ratio), "seed": seed,
                       "gap": g, "sigma": ratio * g, "truth": truth,
                       "seg": jitter(seg, ratio * g, rng)}


# --------------------------------------------------------------------------
# the edit generator: predict-then-verify with a closed form
# --------------------------------------------------------------------------

def edits(seg: np.ndarray, truth: Tuple[int, int, int, int, int]
          ) -> Iterator[Tuple[str, np.ndarray, Tuple[int, int, int, int, int], str]]:
    """Edits whose effect on the five integers is known before the edit is made.

    Each one attaches in the empty half-plane to the right of the figure's
    rightmost vertex, so the prediction does not depend on the figure's shape.
    That is the claim no vision check and no area check can express: *this edit
    should take faces from 4 to 5*, checked by an integer.
    """
    v, e, c, faces, chi = truth
    P = seg.reshape(-1, 2)
    x0, y0 = float(P[:, 0].min()), float(P[:, 1].min())
    x1, y1 = float(P[:, 0].max()), float(P[:, 1].max())
    s = 0.25 * max(math.hypot(x1 - x0, y1 - y0), 1.0)
    k = int(np.lexsort((P[:, 1], P[:, 0]))[-1])         # rightmost, then topmost
    vx, vy = float(P[k, 0]), float(P[k, 1])
    w = (vx + s, vy)                                    # clear of every vertex

    stub = S([[vx, vy], list(w)])
    yield ("pendant", np.concatenate([seg, stub]), (v + 1, e + 1, c, faces, chi),
           "a dangling edge changes nothing but V, E and the dangle count")

    box = S([list(w), [w[0] + s, w[1]]], [[w[0] + s, w[1]], [w[0] + s, w[1] + s]],
            [[w[0] + s, w[1] + s], [w[0], w[1] + s]], [[w[0], w[1] + s], list(w)])
    yield ("loop", np.concatenate([seg, stub, box]),
           (v + 4, e + 5, c, faces + 1, chi - 1),
           "one more enclosed face: faces %d -> %d" % (faces, faces + 1))

    dx = (x1 - x0) + 2.0 * s + max(x1 - x0, 1.0)
    yield ("copy", np.concatenate([seg, seg + np.array([dx, 0.0])]),
           (2 * v, 2 * e, 2 * c, 2 * faces, 2 * chi),
           "every quantity doubles")


# --------------------------------------------------------------------------
# SVG emission - the only place the corpus becomes a file
# --------------------------------------------------------------------------

def to_svg(seg: np.ndarray, ids: Optional[Sequence[str]] = None,
           kind: str = "line", stroke: float = 0.05, viewbox: bool = False) -> str:
    """The figure as SVG text, at full float64 precision and, by default, with
    no viewBox.

    `%.17g` is not decoration: rounding here would manufacture exactly the
    near-coincidences the jitter stratum is supposed to control, and the corpus
    would be measuring the writer instead of the reader.

    The viewBox is off for the same reason. A viewBox is a viewport transform,
    and a reader that honours it - this one does - translates every coordinate
    by the box origin, which is a rigid motion of the drawing and therefore a
    different float64 point set. `viewbox=True` exists so that behaviour can be
    tested deliberately; it is not what a figure with known truth should carry.
    """
    P = seg.reshape(-1, 2)
    x0, y0 = float(P[:, 0].min()), float(P[:, 1].min())
    x1, y1 = float(P[:, 0].max()), float(P[:, 1].max())
    pad = 0.05 * max(x1 - x0, y1 - y0, 1.0)
    head = '<svg xmlns="http://www.w3.org/2000/svg">'
    if viewbox:
        head = ('<svg xmlns="http://www.w3.org/2000/svg" '
                'viewBox="%.17g %.17g %.17g %.17g">'
                % (x0 - pad, y0 - pad, (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad))
    body = []
    for i, ((ax, ay), (bx, by)) in enumerate(seg):
        ident = ids[i] if ids is not None and i < len(ids) else "s%d" % i
        if kind == "path":
            body.append('  <path id="%s" fill="none" stroke="black" stroke-width="%g" '
                        'd="M %.17g %.17g L %.17g %.17g"/>' % (ident, stroke, ax, ay, bx, by))
        else:
            body.append('  <line id="%s" stroke="black" stroke-width="%g" '
                        'x1="%.17g" y1="%.17g" x2="%.17g" y2="%.17g"/>'
                        % (ident, stroke, ax, ay, bx, by))
    return "\n".join([head] + body + ["</svg>", ""])


def write_svg(path, seg: np.ndarray, **kw) -> pathlib.Path:
    p = pathlib.Path(path)
    p.write_text(to_svg(seg, **kw), encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# the found corpus
# --------------------------------------------------------------------------

def found() -> List[Dict[str, object]]:
    """Real agent-written SVGs from `corpus/found/`, with truth from `truth.json`.

    Returns `[]` when the directory is empty, and that is the honest state: a
    found corpus cannot be synthesised - a figure this file writes is a figure
    this file already knows the answer to - so it is collected, dated and
    committed, or the rates that depend on it stay NOT EARNED. Nothing here
    fabricates a row to make a table look full.
    """
    truth_file = FOUND / "truth.json"
    truth = json.loads(truth_file.read_text(encoding="utf-8")) if truth_file.exists() else {}
    out: List[Dict[str, object]] = []
    for svg in sorted(FOUND.glob("*.svg")) if FOUND.exists() else []:
        rec = dict(truth.get(svg.name, {}))
        rec["path"] = svg
        rec["name"] = svg.name
        out.append(rec)
    return out


# --------------------------------------------------------------------------

def _selfcheck() -> None:
    """Truth is checked against a second formula here, never against planimeter."""
    for name, (seg, truth) in FAMILIES.items():
        v, e, c, faces, chi = truth
        assert faces == e - v + c, (name, truth)
        assert chi == v - e == c - faces, (name, truth)
        assert seg.ndim == 3 and seg.shape[1:] == (2, 2), (name, seg.shape)
        assert np.isfinite(seg).all(), name
    assert FAMILIES["grid(2)"][1] == (9, 12, 1, 4, -3)
    assert FAMILIES["pentagram noded"][0].shape == (15, 2, 2)

    seg, truth = disjoint_union("square", "triangle")
    assert truth == (7, 7, 2, 2, 0), truth

    tri = FAMILIES["triangle"][0]
    g = feature_gap(tri)
    assert abs(g - 8.66) < 1e-9, g          # apex to base, not the 10-unit sides
    assert abs(feature_gap(FAMILIES["square"][0]) - 10.0) < 1e-12
    assert abs(feature_gap(near_touching_squares()) - 2.2e-6) < 1e-14
    assert abs(feature_gap(wall_missing_the_floor()) - 2.2e-6) < 1e-14

    rng = np.random.default_rng(0)
    j = jitter(FAMILIES["square"][0], 1e-4, rng)
    assert j.shape == FAMILIES["square"][0].shape
    assert 0 < float(np.abs(j - FAMILIES["square"][0]).max()) <= 1e-4 + 1e-18
    assert feature_gap(j) < 1e-3, "jitter must create the near-coincidence it promises"

    n = sum(1 for _ in jitter_stratum(names=["square"], seeds=3))
    assert n == len(RATIOS) * 3, n
    assert max(RATIOS) <= 1e-2, "the measured ceiling of the exact-or-refuse stratum"
    assert set(CONTESTED) and all(a != b for _, a, b in CONTESTED.values())

    for name, new_seg, new_truth, _why in edits(*FAMILIES["square"]):
        v, e, c, faces, chi = new_truth
        assert faces == e - v + c and chi == v - e, (name, new_truth)
    names = [n for n, _, _, _ in edits(*FAMILIES["square"])]
    assert names == ["pendant", "loop", "copy"], names

    text = to_svg(FAMILIES["T-junction"][0])
    assert text.count("<line") == 5 and "viewBox" not in text
    assert "viewBox" in to_svg(FAMILIES["square"][0], viewbox=True)
    assert "<circle" in curve_unstable_svg()
    assert found() == [] or all("path" in r for r in found())
    print("families %d   refusals %d   jitter draws %d   found %d"
          % (len(FAMILIES), len(REFUSALS),
             len(FAMILIES) * len(RATIOS) * SEEDS, len(found())))
    print("corpus.py self-check OK")


if __name__ == "__main__":
    _selfcheck()
