"""The snap layer against independent implementations, not against itself.

The two load-bearing controls here are an explicit all-pairs single-linkage cut
and a scalar Prim, both written out longhand in this file. They are slow and
obviously right; the vectorised versions in snap.py have to agree with them.
"""

import math

import numpy as np

import pytest

from planimeter.result import REASON, PlanimeterParseError, Refused
from planimeter.snap import (CLUSTER_MAX, FLOOR_ULPS, Window, candidates,
                             dedup_exact, emst, floor_delta, margin,
                             merge_heights, spectrum, window, window_from_grid)


# --- controls, written out longhand -----------------------------------------

def all_pairs_single_linkage(pts, r):
    """The definition: components of the graph joining every pair within r.

    `np.hypot`, not `math.hypot`: the two disagree by an ulp on some pairs, and
    r is often exactly one of those distances, so a scalar control would report
    a partition difference that is a difference between two square roots. The
    control here is the algorithm - all pairs against a spanning tree - not the
    distance function.
    """
    n = len(pts)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            if float(np.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])) <= r:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[rb] = ra
    seen, out = {}, []
    for i in range(n):
        r0 = find(i)
        out.append(seen.setdefault(r0, len(seen)))
    return out


def brute_mst_weights(pts):
    """Prim over all pairs. O(n^2), no triangulation anywhere near it."""
    n = len(pts)
    inside = [False] * n
    best = [float("inf")] * n
    best[0] = 0.0
    out = []
    for _ in range(n):
        u = min((b, i) for i, b in enumerate(best) if not inside[i])[1]
        inside[u] = True
        if best[u] > 0.0:
            out.append(best[u])
        for v in range(n):
            if not inside[v]:
                d = math.hypot(pts[u][0] - pts[v][0], pts[u][1] - pts[v][1])
                if d < best[v]:
                    best[v] = d
    return sorted(out)


def _sets(seed, n, kind):
    rng = np.random.default_rng(seed)
    p = rng.normal(size=(n, 2)) * 10.0
    if kind == "collinear":
        p[:, 1] = 0.0
    elif kind == "clustered":
        base = p[: max(n // 4, 1)]
        p = np.resize(base, (n, 2)) + rng.normal(size=(n, 2)) * 1e-6
    elif kind == "duplicated":
        p[n // 2:] = p[: n - n // 2]
    return dedup_exact(p)[0]


KINDS = ["general", "collinear", "clustered", "duplicated"]


# --- the tests ---------------------------------------------------------------

def test_emst_matches_bruteforce():
    """500 point sets, including collinear, duplicate-heavy and near-degenerate
    ones, against a scalar Prim written out longhand."""
    n_checked = 0
    for seed in range(125):
        for kind in KINDS:
            pts = _sets(seed, int(3 + (seed * 7) % 60), kind)
            if len(pts) < 2:
                continue
            fast = np.sort(np.hypot(pts[emst(pts)[:, 0], 0] - pts[emst(pts)[:, 1], 0],
                                    pts[emst(pts)[:, 0], 1] - pts[emst(pts)[:, 1], 1]))
            slow = brute_mst_weights(pts.tolist())
            assert len(fast) == len(slow) == len(pts) - 1
            assert np.allclose(fast, slow, rtol=0, atol=1e-12 * max(1.0, float(np.max(fast))))
            n_checked += 1
    assert n_checked >= 400


def test_snap_matches_all_pairs_single_linkage():
    """The honest seam, made checkable: the EMST window rule is single-linkage
    clustering, and here it is against the definition on 200 point sets."""
    n_checked = 0
    for seed in range(50):
        for kind in KINDS:
            pts = _sets(1000 + seed, int(4 + (seed * 5) % 40), kind)
            if len(pts) < 3:
                continue
            w = window(pts)
            if isinstance(w, Refused):
                continue
            assert w.labels == all_pairs_single_linkage(pts.tolist(), w.t_below)
            n_checked += 1
    assert n_checked >= 100


def test_window_invariance():
    """The partition is constant across the whole window, which is the whole
    claim the certificate makes about the snap."""
    pts = np.array([[0.0, 0.0], [1e-5, 0.0], [1.0, 0.0], [1.0 + 1e-5, 1e-5],
                    [0.0, 1.0], [2.0, 2.0]])
    for w in candidates(pts):
        for frac in (0.0, 1e-6, 0.25, 0.5, 0.999999):
            r = w.t_below + frac * (w.t_above - w.t_below)
            assert all_pairs_single_linkage(pts.tolist(), r) == w.labels


def test_minimum_inter_cluster_distance_is_exactly_t_above():
    """Kruskal's cut property. This is why separation is reported as a theorem
    and not checked as a predicate: as a predicate it cannot fail."""
    rng = np.random.default_rng(3)
    for _ in range(30):
        pts = dedup_exact(rng.normal(size=(25, 2)))[0]
        for w in candidates(pts):
            if w.n_clusters < 2:
                continue
            best = min(float(np.hypot(*(pts[i] - pts[j])))
                       for i in range(len(pts)) for j in range(i + 1, len(pts))
                       if w.labels[i] != w.labels[j])
            assert abs(best - w.t_above) <= 1e-9 * max(1.0, w.t_above)


def test_exact_duplicates_collapse_before_any_gap_search():
    pts = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 0.0], [-0.0, 0.0], [10.0, 0.0]])
    u, idx = dedup_exact(pts)
    assert len(u) == 2
    assert idx.tolist() == [0, 1, 0, 0, 1]


def test_clean_drawing_merges_nothing():
    """The case the plain widest-gap rule got wrong: with no near-coincidence
    there is nothing to snap, and the rule must not reach into the drawing's own
    length distribution to find something."""
    for pts in (np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]),
                np.array([[float(i), float(j)] for i in range(6) for j in range(6)])):
        w = window(pts)
        assert isinstance(w, Window)
        assert w.n_merged == 0
        assert w.t_below == floor_delta(pts)


def test_merge_nothing_is_offered_last_not_first():
    """Ranked by ratio, the floor window always wins - for arithmetic reasons,
    not geometric ones - and every jittered file would read as a pile of
    distinct endpoints."""
    jit = np.array([[0.0, 0.0], [1e-4, 1e-4], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cs = candidates(jit)
    assert len(cs) >= 2
    assert cs[0].n_merged == 1
    assert cs[-1].n_merged == 0 and cs[-1].t_below == floor_delta(jit)


def test_no_stable_scale_refuses_rather_than_choosing():
    """A drawing whose magnitude swamps its own detail: every separation is
    inside rho of the representability floor."""
    pts = 1e8 + np.array([[0.0, 0.0], [1e-4, 0.0], [2e-4, 0.0], [3e-4, 0.0]])
    r = window(pts)
    assert isinstance(r, Refused) and r.reason == REASON.NO_STABLE_SCALE
    assert r.action and r.look_at


def test_cluster_cap_is_a_policy_and_it_bites():
    """A window that would fold more than CLUSTER_MAX endpoints into one vertex
    is not offered. Stated as a policy, not sold as a theorem."""
    tight = np.concatenate([np.array([[i * 1e-9, 0.0] for i in range(CLUSTER_MAX + 4)]),
                            np.array([[1.0, 0.0], [2.0, 0.0]])])
    for w in candidates(tight):
        sizes = np.bincount(np.asarray(w.labels))
        assert sizes.max() <= CLUSTER_MAX


def test_user_grid_is_verified_the_same_way():
    """Provenance and verification are orthogonal: a supplied radius inside a
    wide enough window is as verified as a derived one, and says which it was."""
    pts = np.array([[0.0, 0.0], [1e-4, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    w = window_from_grid(pts, 1e-2)
    assert isinstance(w, Window) and w.source == "user" and w.n_merged == 1
    assert isinstance(window_from_grid(pts, 1e9), Refused)
    assert isinstance(window_from_grid(pts, 1e-300), Refused)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_grid_is_this_packages_own_typed_error(bad):
    """NaN compares False against both the floor and the ceiling check below,
    falling through to an unguarded `s[k + 1]` and raising a bare IndexError
    three frames inside `window_from_grid` - reachable directly from the
    command line as `--grid nan`. Inf and -Inf happened to be caught by the
    two comparisons that follow, but are refused up front too rather than
    trusted to keep landing on the right side of them."""
    pts = np.array([[0.0, 0.0], [1e-4, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    with pytest.raises(PlanimeterParseError, match="finite"):
        window_from_grid(pts, bad)


def test_rho_is_printed_and_movable():
    pts = np.array([[0.0, 0.0], [1.0, 0.0], [4.0, 0.0], [10.0, 0.0]])
    assert all(w.ratio >= 10.0 for w in candidates(pts, rho=10.0))
    assert all(w.ratio >= 3.0 for w in candidates(pts, rho=3.0))
    assert len(candidates(pts, rho=3.0)) >= len(candidates(pts, rho=10.0))


def test_floor_and_margin_scale_with_the_drawing():
    pts = np.array([[0.0, 0.0], [1.0, 1.0]])
    assert floor_delta(pts) == FLOOR_ULPS * 2.0 ** -52 * 1.0
    assert margin(pts) == 64 * 2.0 ** -52 * 1.0
    assert floor_delta(pts * 1024.0) == floor_delta(pts) * 1024.0


def test_extra_distances_enter_the_spectrum():
    """Vertex-to-edge distances propose the window, not only verify it."""
    pts = np.array([[0.0, 0.0], [10.0, 0.0], [5.0, 8.66]])
    s_plain, _, _ = spectrum(pts)
    s_ve, _, _ = spectrum(pts, np.array([8.66, 8.66, 8.66]))
    assert 8.66 not in s_plain
    assert 8.66 in s_ve and s_ve[1] == 8.66


def test_merge_heights_are_the_sorted_emst_weights():
    rng = np.random.default_rng(11)
    pts = dedup_exact(rng.normal(size=(40, 2)))[0]
    w, tree = merge_heights(pts)
    assert list(w) == sorted(w)
    assert len(w) == len(pts) - 1
    assert np.allclose(w, brute_mst_weights(pts.tolist()))


def test_window_json_is_serialisable():
    pts = np.array([[0.0, 0.0], [1e-5, 0.0], [1.0, 0.0]])
    import json
    json.dumps(window(pts).json())
