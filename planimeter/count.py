"""The counting layer. Union-find over an edge list, then Euler's identity.

For a graph embedded in the plane with V vertices, E edges and C connected
components,

    V - E + F = 1 + C

where F counts *all* faces including the single unbounded one. A triangle has
V = 3, E = 3, F = 2 - one bounded region and the outside - so the number of
enclosed faces is

    faces = F - 1 = E - V + C

which is also the first Betti number of the 1-complex, the number of
independent cycles, and

    chi = V - E = pieces - faces

This is 18th-century arithmetic and it is not where the risk is. Given a
correct edge list this file cannot be wrong, and nothing in it is evidence
that the edge list is correct - that is arrange.py's job, and the counting is
the only part of the pipeline that is linear.

No I/O, no numpy, no float.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, NamedTuple, Sequence, Tuple


class Counts(NamedTuple):
    v: int
    e: int
    pieces: int
    faces: int
    chi: int
    dangles: int


class DSU:
    """Union-find with path halving and union by size. The same structure the
    window search in snap.py uses for Kruskal."""

    __slots__ = ("parent", "size", "n_sets")

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.size = [1] * n
        self.n_sets = n

    def find(self, a: int) -> int:
        p = self.parent
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        self.n_sets -= 1
        return True

    def labels(self) -> List[int]:
        """Component id per element, renumbered 0..k-1 in order of first
        appearance so the result does not depend on union order."""
        seen: Dict[int, int] = {}
        out = []
        for i in range(len(self.parent)):
            r = self.find(i)
            if r not in seen:
                seen[r] = len(seen)
            out.append(seen[r])
        return out


def count(n_vertices: int, edges: Sequence[Tuple[int, int]]) -> Counts:
    """Count a graph given as a vertex count and an edge list of index pairs.

    `edges` must already be deduplicated: a repeated vertex pair inflates E,
    hence faces, by one. arrange.py owns that deduplication, and the lemma that
    makes it exact rather than a heuristic.

    An isolated vertex adds 1 to V and 1 to C, so it leaves faces unchanged -
    the identity is robust to them, though the arrangement never produces any.
    """
    if n_vertices < 0:
        raise ValueError("n_vertices must be non-negative")
    dsu = DSU(n_vertices)
    degree = [0] * n_vertices
    for a, b in edges:
        if not (0 <= a < n_vertices and 0 <= b < n_vertices):
            raise ValueError("edge (%r, %r) outside 0..%d" % (a, b, n_vertices - 1))
        if a == b:
            raise ValueError("self-loop at vertex %d; an edge whose endpoints are one "
                             "vertex is EDGE_COLLAPSED, not a countable edge" % a)
        degree[a] += 1
        degree[b] += 1
        dsu.union(a, b)
    v = n_vertices
    e = len(edges)
    pieces = dsu.n_sets
    faces = e - v + pieces
    return Counts(v=v, e=e, pieces=pieces, faces=faces, chi=v - e,
                  dangles=sum(1 for d in degree if d == 1))


def components(n_vertices: int, edges: Iterable[Tuple[int, int]]) -> List[int]:
    """Component label per vertex. Exposed because snap.py needs the same
    partition over a different edge set."""
    dsu = DSU(n_vertices)
    for a, b in edges:
        dsu.union(a, b)
    return dsu.labels()


# The closed-form table from the specification, checked here against count() and
# against the identity a second time in tests/test_count.py.
def _selfcheck() -> None:
    def sq(o=0):
        return [(o + 0, o + 1), (o + 1, o + 2), (o + 2, o + 3), (o + 3, o + 0)]

    cases = [
        # name, n, edges, (v, e, pieces, faces, chi, dangles)
        ("segment", 2, [(0, 1)], (2, 1, 1, 0, 1, 2)),
        ("triangle", 3, [(0, 1), (1, 2), (2, 0)], (3, 3, 1, 1, 0, 0)),
        ("path tree n=4", 4, [(0, 1), (1, 2), (2, 3)], (4, 3, 1, 0, 1, 2)),
        ("two disjoint squares", 8, sq(0) + sq(4), (8, 8, 2, 2, 0, 0)),
        ("two squares sharing an edge", 6,
         [(0, 1), (1, 2), (2, 3), (3, 0), (1, 4), (4, 5), (5, 2)], (6, 7, 1, 2, -1, 0)),
        ("square + both diagonals + centre", 5,
         sq(0) + [(0, 4), (1, 4), (2, 4), (3, 4)], (5, 8, 1, 4, -3, 0)),
        ("planar K4", 4, [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)], (4, 6, 1, 3, -2, 0)),
        ("T-junction (subdivided)", 6,
         [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 4)], (6, 7, 1, 2, -1, 0)),
    ]
    for name, n, edges, want in cases:
        got = tuple(count(n, edges))
        assert got == want, "%s: got %r want %r" % (name, got, want)
        assert got[3] == got[1] - got[0] + got[2]
        assert got[4] == got[2] - got[3]

    # grid(k): (k+1)^2 vertices, 2k(k+1) edges, k^2 faces, chi = 1 - k^2
    for k in range(2, 13):
        idx = lambda i, j: i * (k + 1) + j                       # noqa: E731
        edges = []
        for i in range(k + 1):
            for j in range(k):
                edges.append((idx(i, j), idx(i, j + 1)))
                edges.append((idx(j, i), idx(j + 1, i)))
        c = count((k + 1) ** 2, edges)
        assert c.v == (k + 1) ** 2 and c.e == 2 * k * (k + 1), c
        assert c.faces == k * k and c.chi == 1 - k * k and c.pieces == 1, c

    # disjoint union is additive
    a = count(3, [(0, 1), (1, 2), (2, 0)])
    b = count(4, [(0, 1), (1, 2), (2, 3), (3, 0)])
    ab = count(7, [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 6), (6, 3)])
    assert (ab.pieces, ab.faces, ab.chi) == (a.pieces + b.pieces, a.faces + b.faces, a.chi + b.chi)

    # a chord inside one component: faces + 1, chi - 1. a bridge between two:
    # pieces - 1, faces unchanged, chi - 1.
    base = count(8, sq(0) + sq(4))
    chord = count(8, sq(0) + sq(4) + [(0, 2)])
    bridge = count(8, sq(0) + sq(4) + [(0, 4)])
    assert (chord.faces, chord.chi) == (base.faces + 1, base.chi - 1)
    assert (bridge.pieces, bridge.faces, bridge.chi) == (base.pieces - 1, base.faces, base.chi - 1)

    print("count.py self-check OK - %d closed-form families, grid k=2..12" % len(cases))


if __name__ == "__main__":
    _selfcheck()
