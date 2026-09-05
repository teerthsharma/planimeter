"""Closed form only. No float, no I/O, no planimeter arithmetic on either side.

Truth in this file is written out as the construction recipe's formula, derived
on paper. `count.py` computes the same integers a different way (union-find over
an edge list); agreement is the test.
"""

import pytest

from planimeter.count import DSU, Counts, components, count


def sq(o=0):
    return [(o + 0, o + 1), (o + 1, o + 2), (o + 2, o + 3), (o + 3, o + 0)]


KNOWN = [
    ("segment", 2, [(0, 1)], (2, 1, 1, 0, 1, 2)),
    ("triangle", 3, [(0, 1), (1, 2), (2, 0)], (3, 3, 1, 1, 0, 0)),
    ("path tree n=4", 4, [(0, 1), (1, 2), (2, 3)], (4, 3, 1, 0, 1, 2)),
    ("star tree n=5", 5, [(0, 1), (0, 2), (0, 3), (0, 4)], (5, 4, 1, 0, 1, 4)),
    ("two disjoint squares", 8, sq(0) + sq(4), (8, 8, 2, 2, 0, 0)),
    ("two squares sharing an edge", 6,
     [(0, 1), (1, 2), (2, 3), (3, 0), (1, 4), (4, 5), (5, 2)], (6, 7, 1, 2, -1, 0)),
    ("square + both diagonals + centre", 5,
     sq(0) + [(0, 4), (1, 4), (2, 4), (3, 4)], (5, 8, 1, 4, -3, 0)),
    ("planar K4", 4, [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)], (4, 6, 1, 3, -2, 0)),
    ("nested unconnected squares", 8, sq(0) + sq(4), (8, 8, 2, 2, 0, 0)),
    ("T-junction subdivided", 6,
     [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 4)], (6, 7, 1, 2, -1, 0)),
]


@pytest.mark.parametrize("name,n,edges,want", KNOWN, ids=[k[0] for k in KNOWN])
def test_known_answers(name, n, edges, want):
    assert tuple(count(n, edges)) == want


def test_grid_family():
    """k = 2..12: V = (k+1)^2, E = 2k(k+1), faces = k^2, chi = 1 - k^2."""
    for k in range(2, 13):
        edges = []
        for i in range(k + 1):
            for j in range(k):
                edges.append((i * (k + 1) + j, i * (k + 1) + j + 1))
                edges.append((j * (k + 1) + i, (j + 1) * (k + 1) + i))
        c = count((k + 1) ** 2, edges)
        assert (c.v, c.e, c.pieces, c.faces, c.chi) == \
               ((k + 1) ** 2, 2 * k * (k + 1), 1, k * k, 1 - k * k)


def test_theta_and_chain_and_comb_and_ladder():
    for k in range(2, 7):
        # theta(k): two poles joined by k internally disjoint 2-segment paths
        edges = [(0, 2 + i) for i in range(k)] + [(2 + i, 1) for i in range(k)]
        c = count(2 + k, edges)
        assert (c.v, c.e, c.faces, c.chi) == (2 + k, 2 * k, k - 1, 2 - k)
        # chain(k) squares sharing walls
        n = 2 * (k + 1)
        edges = ([(2 * i, 2 * i + 2) for i in range(k)] +
                 [(2 * i + 1, 2 * i + 3) for i in range(k)] +
                 [(2 * i, 2 * i + 1) for i in range(k + 1)])
        c = count(n, edges)
        assert (c.v, c.e, c.faces, c.chi) == (n, 3 * k + 1, k, 1 - k)
        # comb(k): a spine subdivided at k interior points, one tooth at each
        n = 2 * k + 2
        edges = [(i, i + 1) for i in range(k + 1)] + [(1 + i, k + 2 + i) for i in range(k)]
        c = count(n, edges)
        assert (c.v, c.e, c.faces, c.chi, c.pieces) == (n, 2 * k + 1, 0, 1, 1)
        assert c.dangles == k + 2


def test_disjoint_union_is_additive():
    a = count(3, [(0, 1), (1, 2), (2, 0)])
    b = count(4, sq(0))
    ab = count(7, [(0, 1), (1, 2), (2, 0)] + sq(3))
    assert ab.pieces == a.pieces + b.pieces
    assert ab.faces == a.faces + b.faces
    assert ab.chi == a.chi + b.chi


def test_chord_and_bridge():
    """A chord inside one component: faces + 1, chi - 1. A bridge between two:
    pieces - 1, faces unchanged, chi - 1. This is predict-then-verify in closed
    form, at the graph level."""
    base = count(8, sq(0) + sq(4))
    chord = count(8, sq(0) + sq(4) + [(0, 2)])
    bridge = count(8, sq(0) + sq(4) + [(0, 4)])
    assert (chord.pieces, chord.faces, chord.chi) == (base.pieces, base.faces + 1, base.chi - 1)
    assert (bridge.pieces, bridge.faces, bridge.chi) == (base.pieces - 1, base.faces, base.chi - 1)


def test_isolated_vertices_leave_faces_alone():
    """An isolated vertex adds 1 to V and 1 to C, so the identity absorbs it."""
    a = count(3, [(0, 1), (1, 2), (2, 0)])
    b = count(6, [(0, 1), (1, 2), (2, 0)])
    assert b.faces == a.faces and b.chi == a.chi + 3 and b.pieces == a.pieces + 3


def test_identity_holds_on_every_known_row():
    for _, n, edges, _ in KNOWN:
        c = count(n, edges)
        assert c.faces == c.e - c.v + c.pieces
        assert c.chi == c.v - c.e == c.pieces - c.faces


def test_dangles_counts_degree_one_vertices():
    assert count(2, [(0, 1)]).dangles == 2
    assert count(4, sq(0)).dangles == 0
    assert count(5, sq(0) + [(0, 4)]).dangles == 1


def test_self_loop_and_out_of_range_are_errors_not_answers():
    with pytest.raises(ValueError):
        count(3, [(1, 1)])
    with pytest.raises(ValueError):
        count(3, [(0, 7)])
    with pytest.raises(ValueError):
        count(-1, [])


def test_dsu_labels_do_not_depend_on_union_order():
    a = DSU(6)
    for x, y in [(0, 1), (1, 2), (3, 4)]:
        a.union(x, y)
    b = DSU(6)
    for x, y in [(3, 4), (1, 2), (0, 1)]:
        b.union(x, y)
    assert a.labels() == b.labels() == [0, 0, 0, 1, 1, 2]
    assert components(6, [(0, 1), (1, 2), (3, 4)]) == a.labels()


def test_empty_graph():
    assert tuple(count(0, [])) == (0, 0, 0, 0, 0, 0)
    assert isinstance(count(0, []), Counts)
