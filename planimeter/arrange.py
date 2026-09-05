"""The arrangement layer: from segments and a candidate scale to a graph, or a refusal.

The order is fixed and no step ever creates a coordinate:

    exact dedup -> EMST -> candidate windows -> cluster
      -> subdivide at *existing* vertices only -> dedup edges
      -> check no remaining intersection -> count

planimeter never computes an intersection point. Split-then-snap can create
crossings and snap-then-split needs a second snap with no fixpoint argument;
both problems disappear when the answer to "these two segments cross at a point
your file does not contain" is a refusal rather than a new coordinate.

Three preconditions decide whether a candidate window survives:

  P1  every edge survives - no input segment has both endpoints in one cluster
  P2  robustness - every (vertex, non-incident edge) pair is at distance exactly
      0, in which case the edge is subdivided there, or at least t_above.
      Anything strictly between refuses.
  P3  plane embedding - after subdivision and edge dedup, no two segments
      intersect except at a shared vertex.

P2 is the check the whole tool turns on. A vertex in the interior of another
segment is not a proper crossing, so a planarity test alone passes it and the
count comes out wrong: a square with a crosswall through two edge midpoints
reads as two pieces and one face against a truth of one and two. Subdividing at
exactly-incident vertices fixes that, and refusing the ambiguous band is what
keeps a near-miss from being silently read as a hit.

Two lemmas make float64 enough:

  Margin. P2 and P3 put every non-degenerate configuration at least t_above
  from degeneracy, and precondition 5 requires t_above > 64 * 2^-52 * M. A
  float64 evaluation of these predicates on coordinates bounded by M has
  absolute error a small multiple of 2^-52 * M, so its sign is correct with
  t_above of slack. The genuinely degenerate case, a vertex exactly on an edge,
  is decided by an exact comparison to 0.0. No rational arithmetic is used and
  none is needed.

  Dedup is exact. Under P3 and straight segments, two distinct edges joining
  the same vertex pair are the same segment, so collapsing them is an identity.
  Without it a duplicated wall inflates E, hence faces, by one.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import snap as _snap
from .count import count
from .result import PRINT_CAP, REASON, Chi, PlanimeterParseError, Refused, digest
from .snap import (CAND_MAX, RHO, Window, candidates, dedup_exact, margin,
                   window_from_grid)

# budget: exact pairs this file will compute - (vertex, segment) for the
# spectrum and the robustness check, (edge, edge) for the embedding check.
# Every pass here is exact all-pairs, blocked to bound memory. There is no
# spatial index and no candidate set, so there is no query tolerance to tune;
# the price is a ceiling, and the ceiling is published rather than hidden.
#
# ponytail: O(n*m) with a refusal above the cap. Upgrade path is a sweep line,
# and the refusal is what a floor plan too large for this pass gets today.
VE_BUDGET = 16_000_000


def pair_budget(max_vertices=None) -> int:
    """The pair ceiling that goes with a vertex ceiling.

    The two budgets are one quadratic budget stated twice - VE_BUDGET is
    exactly 4 x BRUTE_MAX squared - so one flag moves both and a raised
    vertex ceiling cannot be silently undone by the pair ceiling three
    passes later.
    """
    return VE_BUDGET if max_vertices is None else 4 * int(max_vertices) ** 2

# A refusal from one candidate window either ends the run or moves to the next
# window, and which one is not a detail:
#
#   EDGE_COLLAPSED and MARGIN_TOO_SMALL say this *window* is wrong for this
#   drawing - it swallows a real segment, or it sits inside float64 noise - so
#   the next window is tried.
#
#   VERTEX_NEAR_EDGE and EDGES_CROSS say this *drawing* is ambiguous or unnoded.
#   Trying a finer window would find one where the near miss reads as a clean
#   miss, and returning that is choosing the reading that happens to certify.
#   The refusal is the answer.
FALL_THROUGH = frozenset({REASON.EDGE_COLLAPSED, REASON.MARGIN_TOO_SMALL})


class _Bare:
    """Stand-in for a reader record when a bare array is handed in."""


def _sites(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    return rows[:PRINT_CAP], max(0, len(rows) - PRINT_CAP)


def _block_distances(pts, A, B, E, block_ends):
    """(d, t) for every (segment in this block, vertex) pair.

    Exactly 0.0 on the clean case: a wall from (0,0) to (10,0) with a crosswall
    end at (5,0) projects to t = 0.5 and back to (5,0) with no rounding at all.
    Incident pairs are marked with a NaN distance - they are 0 by construction,
    not evidence.
    """
    ab = B - A
    den = np.einsum("ij,ij->i", ab, ab)[:, None]
    safe = np.where(den > 0.0, den, 1.0)
    ap = pts[None, :, :] - A[:, None, :]
    t = np.clip(np.where(den > 0.0, np.einsum("kni,ki->kn", ap, ab) / safe, 0.0), 0.0, 1.0)
    c = A[:, None, :] + t[:, :, None] * ab[:, None, :]
    d = np.hypot(pts[None, :, 0] - c[:, :, 0], pts[None, :, 1] - c[:, :, 1])
    if block_ends:
        k = np.arange(len(A))
        d[k, E[:, 0]] = np.nan
        d[k, E[:, 1]] = np.nan
    return d, t


def near_incidences(pts: np.ndarray, ends: np.ndarray, t_above: float, block: int = 256):
    """Every non-incident (edge, vertex) pair closer than t_above, exactly.

    Returns (edge index, vertex index, distance, parameter along the edge). No
    spatial index: the same exact pass that built the spectrum answers this, and
    an index that returns candidate sets would only add a tolerance to tune.
    """
    a, b = pts[ends[:, 0]], pts[ends[:, 1]]
    ei, vi, dd, tt = [], [], [], []
    for s in range(0, len(ends), block):
        E = ends[s:s + block]
        d, t = _block_distances(pts, a[s:s + block], b[s:s + block], E, True)
        hit = np.nonzero(d < t_above)          # NaN compares false, so incident pairs drop
        ei.append(hit[0] + s)
        vi.append(hit[1])
        dd.append(d[hit])
        tt.append(t[hit])
    cat = lambda xs: np.concatenate(xs) if xs else np.zeros(0)     # noqa: E731
    return (cat(ei).astype(np.int64), cat(vi).astype(np.int64), cat(dd), cat(tt))


def _cross2(u, v):
    """The 2D cross product, written out. numpy's `cross` deprecated the
    2-vector form, and an orientation predicate is one multiply-subtract."""
    return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]


def crossings(pts: np.ndarray, ends: np.ndarray, block: int = 256):
    """Pairs of edges that cross at a point no vertex occupies.

    Only the strict sign test is needed. Precondition P2 has already put every
    non-incident vertex at distance exactly 0 - in which case the edge was
    subdivided there and the pair now shares a vertex - or at least t_above from
    every edge, so no endpoint lies on another edge and no two distinct edges
    overlap collinearly. What is left is a proper crossing, and by the margin
    lemma its four orientation signs are correct in float64.
    """
    a, b = pts[ends[:, 0]], pts[ends[:, 1]]
    out = []
    ba = b - a
    for s in range(0, len(ends), block):
        A, B = a[s:s + block], b[s:s + block]
        BA = (B - A)[:, None, :]
        d1 = _cross2(ba, A[:, None, :] - a[None, :, :])           # (k, m)
        d2 = _cross2(ba, B[:, None, :] - a[None, :, :])
        d3 = _cross2(BA, a[None, :, :] - A[:, None, :])
        d4 = _cross2(BA, b[None, :, :] - A[:, None, :])
        cross = ((d1 > 0) != (d2 > 0)) & ((d3 > 0) != (d4 > 0))
        i, j = np.nonzero(cross)
        i = i + s
        keep = i < j
        i, j = i[keep], j[keep]
        if len(i):
            shares = ((ends[i, 0] == ends[j, 0]) | (ends[i, 0] == ends[j, 1]) |
                      (ends[i, 1] == ends[j, 0]) | (ends[i, 1] == ends[j, 1]))
            out.append(np.stack([i[~shares], j[~shares]], axis=1))
    return np.concatenate(out) if out else np.zeros((0, 2), dtype=np.int64)


def crossing_point(pts, ends, i, j):
    """Where two crossing edges meet. Informational only: this coordinate is
    never inserted into the arrangement, which is why the refusal says to split
    both segments rather than doing it here."""
    p, r = pts[ends[i, 0]], pts[ends[i, 1]] - pts[ends[i, 0]]
    q, s = pts[ends[j, 0]], pts[ends[j, 1]] - pts[ends[j, 0]]
    den = float(_cross2(r, s))
    if den == 0.0:                                        # pragma: no cover
        return None
    u = float(_cross2(q - p, s)) / den
    return [float(p[0] + u * r[0]), float(p[1] + u * r[1])]


def vertex_edge_spectrum(pts: np.ndarray, ends: np.ndarray, block: int = 256,
                         budget: Optional[int] = None) -> np.ndarray:
    """Every non-incident vertex-to-segment distance, on the file's own points,
    before any clustering.

    These distances *propose* the window as well as verify it. A gap search over
    vertex pairs alone is blind to the separation that decides the face count -
    a wall whose end misses a floor by 2.2e-6 leaves no small vertex-pair
    separation behind - and it also invents one that is not there, because the
    smallest vertex-pair separation in a triangle is its shortest side.

    Nothing here consults the certificate, so there is no cycle between the
    tolerance and the thing the tolerance decides.
    """
    n, m = len(pts), len(ends)
    cap = VE_BUDGET if budget is None else int(budget)
    if n * m > cap:
        raise MemoryError("%d vertices x %d segments is above the %d pair budget"
                          % (n, m, cap))
    # ponytail: exact all-pairs, blocked to bound memory. The ceiling is
    # published rather than hidden; the upgrade path is a sweep line, and the
    # refusal above is what a floor plan too large for this pass gets today.
    a, b = pts[ends[:, 0]], pts[ends[:, 1]]
    out = []
    for s in range(0, m, block):
        d, _ = _block_distances(pts, a[s:s + block], b[s:s + block], ends[s:s + block], True)
        out.append(d[~np.isnan(d)])
    return np.concatenate(out) if out else np.zeros(0)


def _as_segments(obj) -> Tuple[np.ndarray, List[str], Dict[str, int], str, str, Tuple[int, int]]:
    """Accept a raw (m, 2, 2) array or a reader's Segments record.

    The reader contract, so read.py and this file can be written apart: an
    object carrying `.seg` (or `.segments` / `.array`) as an (m, 2, 2) float64
    array, plus optional `.ids`, `.skipped`, `.source`, `.source_format` and
    `.flatten`.
    """
    if isinstance(obj, np.ndarray) or isinstance(obj, (list, tuple)):
        arr, obj = obj, _Bare()          # a bare array carries no reader metadata
    else:
        arr = None
        for name in ("seg", "segments", "array"):
            arr = getattr(obj, name, None)
            if arr is not None:
                break
        if arr is None:
            arr = obj
    try:
        seg = np.asarray(arr, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise PlanimeterParseError(
            "segments must be numeric and convertible to float64: %s" % exc)
    if seg.size == 0:
        seg = seg.reshape(0, 2, 2)
    if seg.ndim != 3 or seg.shape[1:] != (2, 2):
        raise PlanimeterParseError(
            "segments must have shape (m, 2, 2); got %r" % (seg.shape,))
    if not np.all(np.isfinite(seg)):
        n_bad = int(np.count_nonzero(~np.isfinite(seg)))
        raise PlanimeterParseError(
            "segments contain %d non-finite value(s) (NaN or Inf) across their "
            "coordinates; every x and y must be a finite float" % n_bad)
    ids = list(getattr(obj, "ids", None) or ["seg#%d" % i for i in range(len(seg))])
    if len(ids) != len(seg):
        ids = ["seg#%d" % i for i in range(len(seg))]
    skipped = dict(getattr(obj, "skipped", None) or {})
    source = str(getattr(obj, "source", "") or "")
    fmt = str(getattr(obj, "source_format", "") or "segments")
    flat = tuple(getattr(obj, "flatten", (16, 32)))
    if len(flat) != 2:
        flat = (int(flat[0]), int(flat[0]) * 2)
    return seg, ids, skipped, source, fmt, (int(flat[0]), int(flat[1]))


def chi_segments(seg, *, grid: Optional[float] = None, rho: Optional[float] = None,
                 cand_max: int = CAND_MAX, flatten: Any = None,
                 ids: Optional[Sequence[str]] = None, source: str = "",
                 max_vertices: Optional[int] = None):
    """The verdict for a segment set. Returns Chi or Refused; never raises for a
    geometry reason.

    This is the entry point every test and the benchmark use, so no test is
    coupled to a file format and the claim "given a correct segment set the
    integers are exact" is testable with no parser in the room.
    """
    with np.errstate(invalid="ignore", over="ignore", divide="ignore"):
        return _chi_segments(seg, grid=grid, rho=rho, cand_max=cand_max, flatten=flatten,
                             ids=ids, source=source, max_vertices=max_vertices)


def _chi_segments(seg, *, grid, rho, cand_max, flatten, ids, source, max_vertices):
    # `_as_segments` has already refused non-finite input; a coordinate near
    # float64's own range can still overflow to +/-inf inside an intermediate
    # squared-length or cross product below (a segment near 1e308, say). That
    # is arithmetic noise, not new information - a downstream refusal
    # (MARGIN_TOO_SMALL or EDGE_COLLAPSED) already says the drawing's scale is
    # unusable - so `chi_segments` silences it above rather than letting a
    # RuntimeWarning print on every such run.
    arr, auto_ids, skipped, src, fmt, flat = _as_segments(seg)
    if ids is not None:
        ids = list(ids)
        auto_ids = ids if len(ids) == len(arr) else auto_ids
    if source:
        src = source
    if flatten is not None:
        flat = (int(flatten), int(flatten) * 2) if np.isscalar(flatten) else tuple(flatten)
    rho = RHO if rho is None else float(rho)
    budget = pair_budget(max_vertices)

    if len(arr) == 0:
        return Refused(REASON.NO_GEOMETRY,
                       detail="parsed %s, zero straight segments" % (src or "input"),
                       look_at=[{"element": k, "count": v} for k, v in sorted(skipped.items())],
                       action="this file has no line work planimeter can read",
                       source=src)

    pts, flat_idx = dedup_exact(arr.reshape(-1, 2))
    ends = flat_idx.reshape(len(arr), 2)

    try:
        _snap.check_vertex_cap(len(pts), max_vertices)
        ve = vertex_edge_spectrum(pts, ends, budget=budget)
        cands = ([window_from_grid(pts, float(grid), rho=rho, extra=ve,
                                   max_vertices=max_vertices)] if grid is not None
                 else candidates(pts, rho=rho, cand_max=cand_max, extra=ve,
                                 max_vertices=max_vertices))
    except MemoryError as exc:
        return Refused(REASON.TOO_MANY_VERTICES,
                       detail="%d distinct endpoints, %d segments; %s" % (len(pts), len(arr), exc),
                       look_at=[{"element": "vertices", "count": len(pts)}],
                       action="raise --max-vertices (cost grows about quadratically; see RESULTS.md), or split the file",
                       source=src)
    if cands and isinstance(cands[0], Refused):
        cands[0].source = src
        return cands[0]
    if not cands:
        r = _snap._no_scale(pts, rho, ve, max_vertices=max_vertices)
        r.source = src
        return r

    tried: List[Refused] = []
    for w in cands:
        out = _try_window(pts, ends, auto_ids, w, rho, flat, skipped, src, fmt,
                          len(cands), budget)
        if isinstance(out, Chi):
            return out
        w.rejected = out.reason
        tried.append(out)
        if out.reason not in FALL_THROUGH:
            out.source = src
            return out
    # Every candidate window was wrong for this drawing. The first one's own
    # refusal is returned rather than a blanket NO_STABLE_SCALE, because it
    # names the element to re-observe and NO_STABLE_SCALE does not.
    first = tried[0]
    first.detail += " (all %d candidate windows failed: %s)" % (
        len(cands), ", ".join(w.rejected for w in cands))
    first.source = src
    return first


def _try_window(pts, ends, ids, w: Window, rho, flat, skipped, src, fmt, n_cands,
                budget: int = VE_BUDGET):
    n_seg = len(ends)
    labels = np.asarray(w.labels, dtype=np.int64)
    R = pts[np.asarray(w.reps, dtype=np.int64)]

    # ---- precondition 5: the float64 margin ------------------------------
    mrg = margin(pts)
    if not (w.t_above > mrg):
        return Refused(REASON.MARGIN_TOO_SMALL,
                       detail="t_above %g is not above 64 ulps of the drawing's magnitude (%g); "
                              "the drawing's scale swamps its own detail" % (w.t_above, mrg),
                       look_at=[{"xy": [float(w.t_above), float(mrg)], "failed": "margin"}],
                       action="rescale the drawing, or split it into files", source=src)

    # ---- P1: every edge survives -----------------------------------------
    ea, eb = labels[ends[:, 0]], labels[ends[:, 1]]
    dead = np.nonzero(ea == eb)[0]
    if len(dead):
        rows = [{"element": ids[k], "xy": [float(pts[ends[k, 0], 0]), float(pts[ends[k, 0], 1])],
                 "length": float(np.hypot(*(pts[ends[k, 1]] - pts[ends[k, 0]])))}
                for k in dead]
        sites, more = _sites(rows)
        return Refused(REASON.EDGE_COLLAPSED,
                       detail="%d segment(s) have both endpoints inside one cluster at radius %g"
                              % (len(dead), w.radius),
                       look_at=sites, n_more=more,
                       action="lengthen this segment, or pass --grid below its length", source=src)

    # ---- edge list at this scale, deduplicated ---------------------------
    pairs = np.stack([np.minimum(ea, eb), np.maximum(ea, eb)], axis=1)
    uniq, first_seg = {}, []
    for k in range(n_seg):
        key = (int(pairs[k, 0]), int(pairs[k, 1]))
        if key not in uniq:
            uniq[key] = len(first_seg)
            first_seg.append(k)
    edges = np.array(list(uniq.keys()), dtype=np.int64).reshape(-1, 2)
    n_dup = n_seg - len(edges)
    owner = [ids[k] for k in first_seg]

    # ---- P2: robustness. Every (vertex, non-incident edge) pair is at 0 or
    #      at least t_above; distance 0 subdivides, the band refuses. -------
    if len(R) * len(edges) > budget:
        return Refused(REASON.TOO_MANY_PAIRS,
                       detail="%d vertices x %d edges is above the %d pair budget"
                              % (len(R), len(edges), budget),
                       look_at=[{"element": "pairs", "count": len(R) * len(edges)}],
                       action="split the file, or raise --max-vertices", source=src)
    ei, vi, d, t = near_incidences(R, edges, w.t_above)

    band = np.nonzero(d > 0.0)[0]
    if len(band):
        rows = [{"xy": [float(R[vi[k], 0]), float(R[vi[k], 1])],
                 "element": _vertex_owner(vi[k], ends, labels, ids),
                 "edge": owner[ei[k]], "d": float(d[k])} for k in band]
        rows.sort(key=lambda r: r["d"])
        sites, more = _sites(rows)
        return Refused(REASON.VERTEX_NEAR_EDGE,
                       detail="%d vertex%s inside the ambiguous band (0, %g)"
                              % (len(band), " sits" if len(band) == 1 else "es sit",
                                 w.t_above),
                       look_at=sites, n_more=more,
                       action="move this end onto the wall, or away from it by more than %g"
                              % w.t_above,
                       source=src)

    # ---- subdivide at exactly-incident vertices. No coordinate is created:
    #      the point already exists in the file. -------------------------
    on = np.nonzero(d == 0.0)[0]
    splits: Dict[int, List[Tuple[float, int]]] = {}
    for k in on:
        splits.setdefault(int(ei[k]), []).append((float(t[k]), int(vi[k])))
    n_subdivided = len(splits)

    final: Dict[Tuple[int, int], str] = {}
    for e in range(len(edges)):
        chain = [int(edges[e, 0])]
        for _, v in sorted(splits.get(e, [])):
            chain.append(v)
        chain.append(int(edges[e, 1]))
        for a, b in zip(chain, chain[1:]):
            final.setdefault((min(a, b), max(a, b)), owner[e])
    n_dup += sum(len(splits.get(e, [])) + 1 for e in range(len(edges))) - len(final)
    fedges = np.array(list(final.keys()), dtype=np.int64).reshape(-1, 2)
    fowner = list(final.values())

    # ---- P3: plane embedding ---------------------------------------------
    if len(fedges) ** 2 > budget:
        return Refused(REASON.TOO_MANY_PAIRS,
                       detail="%d edges squared is above the %d pair budget"
                              % (len(fedges), budget),
                       look_at=[{"element": "pairs", "count": len(fedges) ** 2}],
                       action="split the file, or raise --max-vertices", source=src)
    bad = crossings(R, fedges)
    if len(bad):
        rows = [{"element": fowner[i], "other": fowner[j],
                 "xy": crossing_point(R, fedges, i, j)} for i, j in bad]
        sites, more = _sites(rows)
        return Refused(REASON.EDGES_CROSS,
                       detail="%d segment pair%s still intersect at a point the file does not "
                              "contain" % (len(bad), "" if len(bad) == 1 else "s"),
                       look_at=sites, n_more=more,
                       action="split both segments at that point and re-run", source=src)

    # ---- count -------------------------------------------------------------
    c = count(len(R), [(int(x), int(y)) for x, y in fedges])
    return Chi(v=c.v, e=c.e, pieces=c.pieces, faces=c.faces, chi=c.chi, dangles=c.dangles,
               t_below=w.t_below, t_above=w.t_above, ratio=w.ratio, radius=w.radius,
               grid_source=w.source, rho=float(rho), n_subdivided=n_subdivided,
               n_dup_edges=n_dup, n_merged=w.n_merged, diam_max=w.diam_max,
               n_candidates=n_cands, flatten=tuple(flat), source_format=fmt,
               elements_skipped=dict(skipped),
               digest=digest(R.tolist(), [(int(x), int(y)) for x, y in fedges],
                             w.t_below, w.t_above, rho, flat),
               source=src)


def _vertex_owner(cluster: int, ends, labels, ids) -> str:
    """Which input element contributed this vertex. A refusal names the file's
    own elements, never an index into an array the user has never seen."""
    for k in range(len(ends)):
        if labels[ends[k, 0]] == cluster or labels[ends[k, 1]] == cluster:
            return ids[k]
    return "vertex#%d" % cluster       # pragma: no cover


# ---------------------------------------------------------------------------

def _seg(*pairs) -> np.ndarray:
    return np.array(pairs, dtype=np.float64).reshape(-1, 2, 2)


def _square(x=0.0, y=0.0, s=10.0):
    return _seg([[x, y], [x + s, y]], [[x + s, y], [x + s, y + s]],
                [[x + s, y + s], [x, y + s]], [[x, y + s], [x, y]])


def _selfcheck() -> None:
    # 1. the T-junction, the case a planarity test alone gets wrong. A square
    #    with a crosswall between two edge midpoints: truth 1 piece, 2 faces.
    tj = np.concatenate([_square(), _seg([[5.0, 0.0], [5.0, 10.0]])])
    c = chi_segments(tj)
    assert isinstance(c, Chi), c
    assert (c.pieces, c.faces, c.chi) == (1, 2, -1), c
    assert (c.v, c.e, c.n_subdivided) == (6, 7, 2), c

    # 2. collinear overlap: subdivision then dedup, no bigon with no interior.
    ov = _seg([[0.0, 0.0], [10.0, 0.0]], [[3.0, 0.0], [7.0, 0.0]])
    c = chi_segments(ov)
    assert (c.v, c.e, c.pieces, c.faces, c.chi) == (4, 3, 1, 0, 1), c

    # 3. an exactly duplicated segment is one edge, not two.
    dup = _seg([[0.0, 0.0], [10.0, 0.0]], [[0.0, 0.0], [10.0, 0.0]])
    c = chi_segments(dup)
    assert (c.v, c.e, c.faces, c.n_dup_edges) == (2, 1, 0, 1), c

    # 4. two disjoint squares: 2 pieces, 2 faces, chi 0.
    c = chi_segments(np.concatenate([_square(), _square(100.0, 0.0)]))
    assert (c.pieces, c.faces, c.chi) == (2, 2, 0), c

    # 5. a raw pentagram crosses at five points the file does not contain.
    import math
    P = [[math.cos(math.radians(90 + 72 * i)), math.sin(math.radians(90 + 72 * i))]
         for i in range(5)]
    star = _seg(*[[P[i], P[(i + 2) % 5]] for i in range(5)])
    r = chi_segments(star)
    assert isinstance(r, Refused) and r.reason == REASON.EDGES_CROSS, r
    assert len(r.look_at) == 5, r

    # 6. a wall whose end misses the floor by 2.2e-6 refuses instead of being
    #    read as a hit or as a miss - the case a vertex-pair gap search cannot
    #    see, because the face count turns on vertex-to-EDGE incidence.
    near = np.concatenate([_square(), _seg([[5.0, 2.2e-06], [5.0, 10.0]])])
    r = chi_segments(near)
    assert isinstance(r, Refused) and r.reason == REASON.VERTEX_NEAR_EDGE, r
    assert abs(r.look_at[0]["d"] - 2.2e-06) < 1e-15, r.look_at

    # 7. a jittered square still counts: the un-merged reading is rejected by
    #    P2, the merged reading passes, and nothing was invented to get there.
    jit = _square()
    jit[0, 0] += [1e-05, -1e-05]
    jit[3, 1] += [-1e-05, 1e-05]
    c = chi_segments(jit)
    assert isinstance(c, Chi) and (c.pieces, c.faces) == (1, 1), c
    assert c.n_merged == 1 and c.n_candidates >= 2, c

    # 8. a refusal is falsy and will not become an integer.
    assert not chi_segments(star)
    assert chi_segments(np.zeros((0, 2, 2)))                is not None
    assert chi_segments(np.zeros((0, 2, 2))).reason == REASON.NO_GEOMETRY

    # 9. grid(k) end to end from segments, k = 2..8.
    for k in range(2, 9):
        segs = []
        for i in range(k + 1):
            for j in range(k):
                segs.append([[float(i), float(j)], [float(i), float(j + 1)]])
                segs.append([[float(j), float(i)], [float(j + 1), float(i)]])
        c = chi_segments(np.array(segs, dtype=np.float64))
        assert isinstance(c, Chi), (k, c)
        assert (c.v, c.e, c.faces, c.chi) == ((k + 1) ** 2, 2 * k * (k + 1), k * k, 1 - k * k), (k, c)

    print("arrange.py self-check OK - T-junction, overlap, duplicate, pentagram, "
          "near-miss band, jitter, grid k=2..8")


if __name__ == "__main__":
    _selfcheck()
