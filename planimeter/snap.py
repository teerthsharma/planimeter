"""The snap layer: which vertices are the same vertex, and what certifies it.

THE FILE A REVIEWER OPENS FIRST.

The rule is single-linkage clustering over a Euclidean minimum spanning tree,
cut inside the widest representable gap in the merge-height spectrum. That is
about ten lines over a triangulation, and the README says so: the guarantee is
a policy - refuse rather than guess - not a barrier.

What makes the cut checkable rather than chosen:

  Gower & Ross (1969). For a finite point set P, let G_r be the graph on P with
  an edge whenever d(p, q) <= r, and pi(r) its component partition. pi(r)
  changes exactly at the edge weights of a Euclidean MST of P. So the entire
  spectrum of interesting radii is n-1 numbers, obtained once.

  Theorem (window invariance). If w_i < w_{i+1} are consecutive sorted EMST
  weights then pi(r) is constant for every r in [w_i, w_{i+1}), and for that
  partition the minimum distance between two distinct clusters is exactly
  w_{i+1} by Kruskal's cut property.

That is the whole certificate on the snap side: the identification does not
move anywhere in a window at least RHO wide. It is strictly weaker than "the
identification is right", and it is the strongest statement available without
knowing what the file was supposed to draw. Separation is not checked because
by the cut property it cannot fail, and a predicate that cannot fail is not
evidence.

The tree itself is all-pairs Prim, O(n^2) and exact. Delaunay plus Kruskal was
tried and dropped - see `emst` - because on the near-degenerate point sets a
jittered drawing produces, GEOS's triangulation does not contain the true EMST,
and a spectrum from a wrong tree certifies a scale the drawing does not have.

Two things the spectrum is not, and both were errors this file had:

  It is not vertex separations alone. The face count turns on vertex-to-EDGE
  incidence, so a gap search over vertex pairs is blind to a wall that misses a
  floor by 2.2e-6 and invents a band where none exists - the shortest side of a
  triangle is its smallest vertex separation, so the apex, 8.66 from its own
  base, reads as ambiguous and an ordinary triangle refuses. arrange.py hands
  those distances in as `extra`; they propose the window as well as verify it.

  Merge-nothing is not the widest gap. The window between the representability
  floor and the smallest real separation has an astronomical ratio for
  arithmetic reasons alone, so ranking it by ratio makes "every jittered
  endpoint is its own vertex" the preferred reading of every file. It is
  offered last, as the fallback for a drawing with no near-coincidences.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .count import DSU
from .result import REASON, Refused

# ---------------------------------------------------------------------------
# Policy constants. Every one is a number this package chose, printed on every
# answer and movable by flag. None of them is a theorem.
# ---------------------------------------------------------------------------

RHO = 10.0        # policy: the minimum t_above/t_below ratio a window may have
CAND_MAX = 4      # policy: how many windows are tried, widest ratio first
FLOOR_ULPS = 4096  # policy: the representability floor, in ulps of the drawing's magnitude
CLUSTER_MAX = 16  # policy: largest cluster of endpoints treated as one vertex
BRUTE_MAX = 2000  # budget: vertex ceiling for the exact O(n^2) spanning tree
MARGIN_ULPS = 64  # from the margin lemma, not policy: float64 predicate signs are correct above this

EPS = 2.0 ** -52  # float64 unit roundoff


@dataclass
class Window:
    """A certified scale, plus the partition it induces.

    `t_below` and `t_above` are consecutive merge heights; the partition is the
    connected-component partition of the distance graph at every radius in
    [t_below, t_above). `radius` is the geometric mean of the two, the point in
    the window furthest from either edge in log scale.
    """

    t_below: float
    t_above: float
    ratio: float
    radius: float
    labels: List[int]          # cluster id per input point
    reps: List[int]            # index of each cluster's representative point
    n_clusters: int
    n_merged: int
    diam_max: float
    source: str = "derived"    # "derived" | "user"
    rejected: Optional[str] = None   # set by the caller when a precondition failed

    def json(self) -> Dict[str, Any]:
        return {"t_below": self.t_below, "t_above": self.t_above, "ratio": self.ratio,
                "radius": self.radius, "n_clusters": self.n_clusters,
                "n_merged": self.n_merged, "diam_max": self.diam_max,
                "grid_source": self.source}


# ---------------------------------------------------------------------------
# Exact deduplication. This is an identification, not a tolerance: two points
# written at the same coordinates are the same point, and no gap search runs
# before it. Without this a clean all-exact file has no cluster structure at
# all and the gap search reaches into the drawing's own length distribution.
# ---------------------------------------------------------------------------

def dedup_exact(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Collapse bitwise-equal coordinates. Returns (unique points, index map)."""
    pts = np.ascontiguousarray(np.asarray(points, dtype=np.float64).reshape(-1, 2))
    seen: Dict[Tuple[float, float], int] = {}
    idx = np.empty(len(pts), dtype=np.int64)
    keep: List[int] = []
    for i, (x, y) in enumerate(pts):
        # +0.0 normalises -0.0, which is the same point written two ways.
        key = (x + 0.0, y + 0.0)
        j = seen.get(key)
        if j is None:
            j = seen[key] = len(keep)
            keep.append(i)
        idx[i] = j
    return pts[keep], idx


# ---------------------------------------------------------------------------
# The Euclidean minimum spanning tree, exactly.
# ---------------------------------------------------------------------------

def emst(pts: np.ndarray) -> np.ndarray:
    """Exact Euclidean MST edges as an (n-1, 2) index array.

    All-pairs Prim, vectorised: O(n^2) in time and O(n) in memory, and exact by
    construction. Above BRUTE_MAX it refuses.

    The obvious optimisation is Delaunay plus Kruskal, since the EMST is a
    subgraph of *a* Delaunay triangulation. It was tried and dropped: on
    near-degenerate point sets - which is what a jittered drawing is -
    `shapely.delaunay_triangles(..., only_edges=True)` under shapely 2.1.2 /
    GEOS returns an edge set that does not contain the true EMST, and Kruskal
    over it returns a heavier tree with different merge heights. The measurement
    is in RESULTS.md. A spectrum computed from a wrong tree is a certificate
    about a scale the drawing does not have, so the exact O(n^2) pass stays
    until an exact O(n log n) one is verified against it.

    # ponytail: O(n^2), same order as the vertex-edge pass this file feeds, and
    # the published ceiling is BRUTE_MAX. Upgrade path is a verified Delaunay
    # (Qhull, not GEOS) with the all-pairs tree kept as the test control.
    """
    n = len(pts)
    if n <= 1:
        return np.zeros((0, 2), dtype=np.int64)
    if n == 2:
        return np.array([[0, 1]], dtype=np.int64)
    if n > BRUTE_MAX:
        raise MemoryError("%d distinct vertices is above BRUTE_MAX = %d" % (n, BRUTE_MAX))

    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(n, dtype=bool)
    best = np.full(n, np.inf)
    src = np.zeros(n, dtype=np.int64)
    best[0] = 0.0
    out = np.empty((n - 1, 2), dtype=np.int64)
    for k in range(n):
        u = int(np.argmin(np.where(inside, np.inf, best)))
        inside[u] = True
        if k:
            out[k - 1] = (src[u], u)
        d = np.hypot(x - x[u], y - y[u])
        upd = (~inside) & (d < best)
        best[upd] = d[upd]
        src[upd] = u
    return out


def merge_heights(pts: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """The single-linkage merge spectrum: sorted EMST weights, and the edges
    that carry them, in the same order."""
    tree = emst(pts)
    if not len(tree):
        return np.zeros(0), tree
    w = np.hypot(pts[tree[:, 0], 0] - pts[tree[:, 1], 0],
                 pts[tree[:, 0], 1] - pts[tree[:, 1], 1])
    order = np.argsort(w, kind="stable")
    return w[order], tree[order]


def floor_delta(pts: np.ndarray) -> float:
    """The representability floor: separations below it are not distinguishable
    from float64 noise at the drawing's own magnitude."""
    m = float(np.max(np.abs(pts))) if len(pts) else 0.0
    if m == 0.0:
        m = 1.0     # a single point at the origin; the floor is then absolute
    return FLOOR_ULPS * EPS * m


def margin(pts: np.ndarray) -> float:
    """The float64 margin from the lemma: above this, every incidence sign the
    pipeline computes in float64 is correct, so no rational arithmetic is used
    and none is needed."""
    m = float(np.max(np.abs(pts))) if len(pts) else 0.0
    return MARGIN_ULPS * EPS * (m if m else 1.0)


# ---------------------------------------------------------------------------
# Candidate windows.
# ---------------------------------------------------------------------------

def _build(pts: np.ndarray, weights: np.ndarray, tree: np.ndarray,
           t_below: float, t_above: float, source: str = "derived") -> Optional[Window]:
    dsu = DSU(len(pts))
    for k, w in enumerate(weights):
        if w <= t_below:
            dsu.union(int(tree[k, 0]), int(tree[k, 1]))
    labels = dsu.labels()
    n_clusters = dsu.n_sets
    members: List[List[int]] = [[] for _ in range(n_clusters)]
    for i, lab in enumerate(labels):
        members[lab].append(i)
    diam = 0.0
    for grp in members:
        if len(grp) > CLUSTER_MAX:
            return None     # policy: a cluster this wide is not one vertex
        if len(grp) > 1:
            q = pts[grp]
            dd = np.hypot(q[:, None, 0] - q[None, :, 0], q[:, None, 1] - q[None, :, 1])
            diam = max(diam, float(dd.max()))
    reps = [min(grp, key=lambda i: (pts[i, 0], pts[i, 1])) for grp in members]
    return Window(t_below=float(t_below), t_above=float(t_above),
                  ratio=float(t_above / t_below), radius=math.sqrt(t_below * t_above),
                  labels=labels, reps=reps, n_clusters=n_clusters,
                  n_merged=len(pts) - n_clusters, diam_max=diam, source=source)


def spectrum(pts: np.ndarray, extra: Optional[np.ndarray] = None):
    """(spectrum, weights, tree). The spectrum is the representability floor
    followed by every separation above it that could decide the answer: the
    single-linkage merge heights, and - when the caller supplies them - the
    vertex-to-non-incident-edge distances.

    Heights at or below the floor are not separations, they are noise, and they
    merge unconditionally.

    The vertex-edge distances matter here, not only at verification time. A gap
    search over vertex *pairs* alone is blind to the separation that actually
    decides the face count: a wall whose end misses a floor by 2.2e-6 has no
    small vertex-pair separation at all, so the widest gap lands at the drawing
    scale and the near miss is read as a clean miss. Including them costs one
    brute-force pass and turns the near miss into a named refusal.

    It also fixes the opposite error. With vertex pairs alone the smallest
    separation in a triangle is its shortest side, so the apex - 8.66 from its
    own base with sides of 10 - reads as sitting inside the ambiguous band, and
    an ordinary triangle refuses.
    """
    weights, tree = merge_heights(pts)
    delta = floor_delta(pts)
    vals = [weights[weights > delta]]
    if extra is not None and len(extra):
        extra = np.asarray(extra, dtype=np.float64)
        vals.append(extra[extra > delta])
    s = np.unique(np.concatenate([[delta]] + vals))
    return s, weights, tree


def candidates(pts: np.ndarray, rho: float = RHO, cand_max: int = CAND_MAX,
               extra: Optional[np.ndarray] = None) -> List[Window]:
    """Windows with ratio >= rho: genuine gaps first, widest ratio first, and
    the merge-nothing reading last.

    The merge-nothing reading - the window between the representability floor
    and the smallest real separation - is not ranked by ratio with the others.
    Its ratio is astronomical for arithmetic reasons (the floor is 4096 ulps of
    the drawing's magnitude, so the ratio is whatever the drawing's scale
    divided by machine epsilon happens to be), and ranking it first would make
    "every jittered endpoint is its own vertex" the preferred reading of every
    file. It is the fallback, not the favourite.

    Uniqueness is not claimed: a window further down the list might also have
    passed the downstream checks with a different answer.
    """
    s, weights, tree = spectrum(pts, extra)
    if len(s) < 2:
        return []
    lo, hi = s[:-1], s[1:]
    ratio = hi / lo
    ok = np.nonzero(ratio[1:] >= rho)[0] + 1            # genuine gaps only
    order = list(ok[np.argsort(-ratio[ok], kind="stable")])
    if ratio[0] >= rho:
        order.append(0)                                  # merge nothing, last
    out: List[Window] = []
    for k in order:
        w = _build(pts, weights, tree, float(lo[k]), float(hi[k]))
        if w is not None:
            out.append(w)
            if len(out) == cand_max:
                break
    return out


def window(pts: np.ndarray, *, rho: float = RHO, extra: Optional[np.ndarray] = None):
    """The widest certified window for a point set, or NO_STABLE_SCALE.

    Exposed on its own because the README's honest seam says this rule is about
    ten lines over an MST, and the test that proves it agrees with all-pairs
    single linkage needs to reach it. This function does not apply the
    arrangement preconditions - arrange.py owns those, and owns the selection
    loop that walks these candidates.
    """
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    cands = candidates(pts, rho=rho, cand_max=1, extra=extra)
    if cands:
        return cands[0]
    return _no_scale(pts, rho, extra)


def _no_scale(pts: np.ndarray, rho: float, extra=None) -> Refused:
    s, _, _ = spectrum(pts, extra)
    sites = []
    if len(s) >= 2:
        r = s[1:] / s[:-1]
        for k in np.argsort(-r)[:3]:
            sites.append({"xy": [float(s[k]), float(s[k + 1])], "ratio": float(r[k]),
                          "failed": "ratio below rho" if r[k] < rho else "cluster above CLUSTER_MAX"})
    return Refused(
        REASON.NO_STABLE_SCALE,
        detail=("no gap in the %d merge heights has ratio >= %g; the three widest are listed "
                "as [t_below, t_above]" % (max(len(s) - 1, 0), rho)),
        look_at=sites,
        action="write coincident vertices at identical coordinates, or pass --grid X "
               "to name the scale yourself",
    )


def window_from_grid(pts: np.ndarray, radius: float, *, rho: float = RHO,
                     extra: Optional[np.ndarray] = None):
    """The window a user-supplied radius lands in.

    Provenance and verification are orthogonal: a supplied radius that lands
    inside a window with ratio >= rho and passes the arrangement preconditions
    is exactly as verified as a derived one, and grid_source says which it was.
    """
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    s, weights, tree = spectrum(pts, extra)
    if radius < s[0]:
        return Refused(
            REASON.NO_STABLE_SCALE,
            detail="--grid %g is below the representability floor %g for this drawing"
                   % (radius, s[0]),
            look_at=[{"xy": [float(radius), float(s[0])], "failed": "below floor"}],
            action="pass a larger --grid, or rescale the drawing")
    if radius >= s[-1]:
        return Refused(
            REASON.NO_STABLE_SCALE,
            detail="--grid %g is at or above every separation in the drawing (%g); every "
                   "vertex would be one vertex" % (radius, s[-1]),
            look_at=[{"xy": [float(radius), float(s[-1])], "failed": "above every separation"}],
            action="pass a smaller --grid")
    k = int(np.searchsorted(s, radius, side="right") - 1)
    lo, hi = float(s[k]), float(s[k + 1])
    if hi / lo < rho:
        return Refused(
            REASON.NO_STABLE_SCALE,
            detail="--grid %g lands in [%g, %g), ratio %.4g, below rho = %g"
                   % (radius, lo, hi, hi / lo, rho),
            look_at=[{"xy": [lo, hi], "ratio": hi / lo, "failed": "ratio below rho"}],
            action="pass --grid inside a wider gap, or lower --rho and say so")
    w = _build(pts, weights, tree, lo, hi, source="user")
    if w is None:
        return Refused(
            REASON.NO_STABLE_SCALE,
            detail="--grid %g merges more than CLUSTER_MAX = %d endpoints into one vertex"
                   % (radius, CLUSTER_MAX),
            look_at=[{"xy": [lo, hi], "failed": "cluster above CLUSTER_MAX"}],
            action="pass a smaller --grid")
    w.radius = float(radius)
    return w


# ---------------------------------------------------------------------------

def _selfcheck() -> None:
    rng = np.random.default_rng(7)

    # 1. the EMST is the EMST: the vectorised tree against a scalar Kruskal over
    #    every pair, by the sorted weight multiset (ties make the edge set
    #    ambiguous; the spectrum is not).
    def kruskal_all_pairs(p):
        n = len(p)
        pairs = sorted((math.hypot(*(p[i] - p[j])), i, j)
                       for i in range(n) for j in range(i + 1, n))
        dsu, out = DSU(n), []
        for w_, i, j in pairs:
            if dsu.union(i, j):
                out.append(w_)
        return out

    for trial in range(60):
        n = int(rng.integers(3, 60))
        p = rng.normal(size=(n, 2)) * 10.0
        if trial % 5 == 0:                       # collinear sets are common, not exotic
            p[:, 1] = 0.0
        if trial % 7 == 0:                       # near-degenerate: what jitter looks like
            p = np.repeat(p[: max(n // 4, 1)], 4, axis=0) + rng.normal(size=(4 * max(n // 4, 1), 2)) * 1e-6
        p = dedup_exact(p)[0]
        if len(p) < 3:
            continue
        a = np.sort(np.hypot(*(p[emst(p)[:, 0]] - p[emst(p)[:, 1]]).T))
        b = np.sort(kruskal_all_pairs(p))
        assert np.allclose(a, b, rtol=0, atol=1e-12 * max(1.0, float(a.max()))), \
            "EMST disagrees with all-pairs at n=%d" % len(p)

    # 2. window invariance: the partition is constant across the whole window.
    p = np.array([[0.0, 0.0], [1e-5, 0.0], [1.0, 0.0], [1.0 + 1e-5, 1e-5],
                  [0.0, 1.0], [2.0, 2.0]])
    w = window(p)
    assert isinstance(w, Window) and w.ratio >= RHO, w
    for frac in (0.0, 0.001, 0.5, 0.999):
        r = w.t_below + frac * (w.t_above - w.t_below)
        dsu = DSU(len(p))
        for i in range(len(p)):
            for j in range(i + 1, len(p)):
                if math.hypot(*(p[i] - p[j])) <= r:
                    dsu.union(i, j)
        assert dsu.labels() == w.labels, "partition moved inside the window at r=%g" % r

    # 3. Kruskal's cut property: the minimum inter-cluster distance is exactly
    #    t_above, which is why separation is not a checkable predicate.
    best = min(math.hypot(*(p[i] - p[j]))
               for i in range(len(p)) for j in range(i + 1, len(p))
               if w.labels[i] != w.labels[j])
    assert abs(best - w.t_above) <= 1e-12 * max(1.0, w.t_above), (best, w.t_above)

    # 4. exact duplicates collapse before any gap search, and a clean file with
    #    no near-coincidence merges nothing.
    clean = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]])
    u, idx = dedup_exact(clean)
    assert len(u) == 4 and idx.tolist() == [0, 1, 2, 3, 0]
    wc = window(u)
    assert isinstance(wc, Window) and wc.n_merged == 0, wc

    # 5. "merge nothing" is always one of the candidate readings - the window
    #    between the representability floor and the smallest real separation -
    #    and on a clean drawing it is the widest, so a clean grid certifies with
    #    nothing merged rather than reaching into its own length distribution.
    grid = np.array([[float(i), float(j)] for i in range(6) for j in range(6)])
    wg = window(grid)
    assert isinstance(wg, Window) and wg.n_merged == 0 and wg.t_below == floor_delta(grid), wg

    # 5b. a jittered figure offers both readings. The genuine gap - the one
    #     between the jitter and the drawing - is tried first; merge-nothing is
    #     the fallback, not the favourite, or every jittered file would read as
    #     a pile of distinct endpoints.
    jit = np.array([[0.0, 0.0], [1e-4, 1e-4], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cs = candidates(jit)
    assert len(cs) >= 2 and cs[0].n_merged == 1 and cs[-1].n_merged == 0, cs
    assert cs[-1].t_below == floor_delta(jit), cs[-1]

    # 5c. no window survives when the drawing's magnitude swamps its own detail:
    #     the smallest separation is inside rho of the representability floor.
    huge = 1e8 + np.array([[0.0, 0.0], [1e-4, 0.0], [2e-4, 0.0], [3e-4, 0.0]])
    r = window(huge)
    assert isinstance(r, Refused) and r.reason == REASON.NO_STABLE_SCALE, r

    # 6. a supplied radius is verified the same way, and one outside every gap
    #    refuses instead of merging the drawing into a point.
    wu = window_from_grid(u, 1.0)
    assert isinstance(wu, Window) and wu.source == "user" and wu.n_merged == 0
    assert isinstance(window_from_grid(u, 1e9), Refused)

    print("snap.py self-check OK - EMST 60 sets, window invariance, cut property, "
          "floor %g ulps, rho %g" % (FLOOR_ULPS, RHO))


if __name__ == "__main__":
    _selfcheck()
