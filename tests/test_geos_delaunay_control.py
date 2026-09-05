"""The measurement that removed a dependency, kept runnable.

The design called for `shapely.delaunay_triangles(only_edges=True)` plus Kruskal,
on the theorem that the Euclidean MST is a subgraph of the Delaunay triangulation.
The theorem is true; the returned edge set is not always the triangulation. This
file is the measurement that found that out, and it lives here rather than in a
scratch directory because RESULTS.md quotes its numbers and a number whose command
a stranger cannot run is a number on trust.

shapely is a `[test]` extra and a benchmark opponent, never a runtime dependency.
"""

import numpy as np
import pytest

from planimeter.count import DSU
from planimeter.snap import emst
from test_snap import KINDS, _sets

shapely = pytest.importorskip("shapely")


def delaunay_edges(pts):
    """GEOS's Delaunay edge set as index pairs, or None when the coordinates do
    not round-trip to the input points."""
    tri = shapely.delaunay_triangles(shapely.MultiPoint(pts), only_edges=True)
    if tri is None or tri.is_empty:
        return None
    coords = shapely.get_coordinates(tri)
    lookup = {(x + 0.0, y + 0.0): i for i, (x, y) in enumerate(pts)}
    try:
        ids = [lookup[(x + 0.0, y + 0.0)] for x, y in coords]
    except KeyError:
        return None
    return np.array(ids, dtype=np.int64).reshape(-1, 2)


def kruskal(pts, cand, n):
    d = np.hypot(pts[cand[:, 0], 0] - pts[cand[:, 1], 0],
                 pts[cand[:, 0], 1] - pts[cand[:, 1], 1])
    dsu, keep = DSU(n), []
    for k in np.argsort(d, kind="stable"):
        if dsu.union(int(cand[k, 0]), int(cand[k, 1])):
            keep.append(k)
    return cand[np.array(keep, dtype=np.int64)] if dsu.n_sets == 1 else None


def _weight(pts, tree):
    return float(np.hypot(pts[tree[:, 0], 0] - pts[tree[:, 1], 0],
                          pts[tree[:, 0], 1] - pts[tree[:, 1], 1]).sum())


def survey():
    """(bad, total, worst weight excess, per-stratum counts) over 200 seeds x 4
    strata. Runs in well under a second; the whole point is that it is cheap
    enough to keep."""
    bad = tot = 0
    worst = 0.0
    by_kind = {}
    for seed in range(200):
        for kind in KINDS:
            pts = _sets(seed, int(3 + (seed * 7) % 60), kind)
            if len(pts) < 3:
                continue
            cand = delaunay_edges(pts)
            if cand is None:
                continue
            tot += 1
            by_kind.setdefault(kind, [0, 0])[1] += 1
            true_tree = emst(pts)
            have = {tuple(sorted(e)) for e in cand.tolist()}
            if any(tuple(sorted(e)) not in have for e in true_tree.tolist()):
                bad += 1
                by_kind[kind][0] += 1
                d = kruskal(pts, cand, len(pts))
                if d is not None:
                    worst = max(worst, _weight(pts, d) / _weight(pts, true_tree) - 1.0)
    return bad, tot, worst, by_kind


def test_the_geos_delaunay_edge_set_is_not_always_an_emst_supergraph(capsys):
    """One failure is enough to remove the dependency: a spanning tree built on a
    Delaunay edge set that is missing an MST edge is a different merge spectrum,
    and therefore a different snap radius on a file nobody would call unusual.

    The count is asserted loosely - at least one failure, all of them in the
    clustered stratum - because the exact figure is shapely's and moves with
    GEOS. RESULTS.md carries the run of record with its GEOS version, and this
    prints the same shape on any machine.
    """
    bad, tot, worst, by_kind = survey()
    with capsys.disabled():
        print("\n  point sets where the true EMST is NOT a subgraph of "
              "GEOS delaunay_triangles:")
        print("    %d of %d;  worst spanning-tree weight excess %.4f" % (bad, tot, worst))
        for k, (b, t) in sorted(by_kind.items()):
            print("    %-12s %d / %d" % (k, b, t))
        print("    shapely %s GEOS %s" % (shapely.__version__, shapely.geos_version_string))
    assert tot > 500
    assert bad >= 1, "the theorem held on every set here; re-read RESULTS.md section 7"
    assert by_kind["clustered"][0] == bad, by_kind
    assert worst > 0.0


def test_the_exact_prim_that_replaced_it_spans_every_one_of_those_sets():
    """The control for the replacement, on the same point sets: `emst` returns a
    spanning tree of n-1 edges on every stratum, including the one GEOS missed."""
    for seed in range(0, 200, 7):
        for kind in KINDS:
            pts = _sets(seed, int(3 + (seed * 7) % 60), kind)
            if len(pts) < 3:
                continue
            assert emst(pts).shape == (len(pts) - 1, 2), (seed, kind)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-s"]))
