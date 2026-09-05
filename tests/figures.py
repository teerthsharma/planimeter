"""Closed-form figure families for the certified core's tests.

Truth comes from the construction recipe, derived on paper, never from
planimeter. Nothing here imports planimeter.count, .snap or .arrange.

The jitter re-emitter splits every *shared* vertex by sigma rather than
perturbing every coordinate: that is the only stratum where vertex identity is
contested, and it keeps exact incidences exact so a T-junction stays a
T-junction.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np

# (name) -> (segments, (V, E, pieces, faces, chi))
Figure = Tuple[np.ndarray, Tuple[int, int, int, int, int]]


def S(*pairs) -> np.ndarray:
    return np.array(pairs, dtype=np.float64).reshape(-1, 2, 2)


def square(x=0.0, y=0.0, s=10.0) -> np.ndarray:
    return S([[x, y], [x + s, y]], [[x + s, y], [x + s, y + s]],
             [[x + s, y + s], [x, y + s]], [[x, y + s], [x, y]])


def grid(k: int, h: float = 1.0) -> np.ndarray:
    segs = []
    for i in range(k + 1):
        for j in range(k):
            segs.append([[i * h, j * h], [i * h, (j + 1) * h]])
            segs.append([[j * h, i * h], [(j + 1) * h, i * h]])
    return np.array(segs, dtype=np.float64)


def theta(k: int) -> np.ndarray:
    """Two poles joined by k internally disjoint 2-segment paths."""
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
    """k teeth meeting the interior of a spine. A tree."""
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
    """A path of n vertices; n-1 edges, no cycle, two leaves."""
    return np.array([[[i * 10.0, 0.0], [(i + 1) * 10.0, 0.0]] for i in range(n - 1)],
                    dtype=np.float64)


def pentagram() -> np.ndarray:
    P = [[math.cos(math.radians(90 + 72 * i)), math.sin(math.radians(90 + 72 * i))]
         for i in range(5)]
    return S(*[[P[i], P[(i + 2) % 5]] for i in range(5)])


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
                        [[0, 0], [5, 2.887]], [[10, 0], [5, 2.887]], [[5, 8.66], [5, 2.887]]),
                      (4, 6, 1, 3, -2))
    f["nested unconnected squares"] = (np.concatenate([square(0, 0, 30.0), square(10, 10, 10.0)]),
                                       (8, 8, 2, 2, 0))
    f["T-junction"] = (np.concatenate([square(), S([[5, 0], [5, 10]])]), (6, 7, 1, 2, -1))
    f["H"] = (S([[0, 0], [0, 20]], [[10, 0], [10, 20]], [[0, 10], [10, 10]]), (6, 5, 1, 0, 1))
    f["collinear overlap"] = (S([[0, 0], [10, 0]], [[3, 0], [7, 0]]), (4, 3, 1, 0, 1))
    f["exact duplicate segment"] = (S([[0, 0], [10, 0]], [[0, 0], [10, 0]]), (2, 1, 1, 0, 1))
    for n in (2, 3, 5, 8):
        f["tree(%d)" % n] = (tree(n), (n, n - 1, 1, 0, 1))
    for k in range(2, 13):
        f["grid(%d)" % k] = (grid(k), ((k + 1) ** 2, 2 * k * (k + 1), 1, k * k, 1 - k * k))
    for k in (2, 3, 4, 5):
        f["theta(%d)" % k] = (theta(k), (2 + k, 2 * k, 1, k - 1, 2 - k))
        f["chain(%d)" % k] = (chain(k), (2 * (k + 1), 3 * k + 1, 1, k, 1 - k))
        f["comb(%d)" % k] = (comb(k), (2 * k + 2, 2 * k + 1, 1, 0, 1))
        # chi = V - E = (2k+4) - (3k+2) = 2 - k. The specification table prints 3 - k,
        # which its own V and E columns contradict; the arithmetic wins.
        f["ladder(%d)" % k] = (ladder(k), (2 * k + 4, 3 * k + 2, 1, k - 1, 2 - k))
    return f


FAMILIES: Dict[str, Figure] = _families()

# Figures whose truth is a refusal, not an integer: the raw star crosses at five
# points the file does not contain.
REFUSAL_FIGURES = {"pentagram raw": pentagram()}


def split_shared_vertices(seg: np.ndarray, sigma: float, rng) -> np.ndarray:
    """Re-emit a figure with the same truth and worse coordinates: every vertex
    shared by two or more segment ends is split by a displacement of size sigma.

    Exact incidences - a crosswall end sitting on a wall's interior - are left
    exact, so a T-junction stays a T-junction and the only contested question is
    vertex identity.
    """
    out = seg.copy()
    ends = out.reshape(-1, 2)
    seen: Dict[Tuple[float, float], List[int]] = {}
    for i, (x, y) in enumerate(ends):
        seen.setdefault((x + 0.0, y + 0.0), []).append(i)
    for _, group in seen.items():
        if len(group) < 2:
            continue
        for i in group:
            a = rng.uniform(0.0, 2.0 * math.pi)
            ends[i] += sigma * np.array([math.cos(a), math.sin(a)])
    return out
