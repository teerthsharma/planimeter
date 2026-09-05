"""Verdict types shared by every surface. Standard library only.

Nothing here imports numpy, so `planimeter.hook` and the JSON round-trip cost
nothing beyond the interpreter. Everything else imports this,
and this imports nothing of ours, so no cycle exists.
"""

from __future__ import annotations

import hashlib
import json as _json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

__version__ = "0.1.0"

RULE = "=" * 78
THIN = "-" * 78

# The convention. Printed on every verdict, carried on every JSON payload.
CONVENTION = (
    "The drawing is a finite set of straight segments in the plane. Vertices within the "
    "certified snap radius of each other are one vertex; a vertex lying exactly on another "
    "segment subdivides it; all other points are distinct; no other identification is made. "
    "The three integers describe that graph and its embedding: pieces is the number of "
    "connected components, faces is the number of bounded regions the edges enclose, and "
    "chi = pieces - faces. Nothing is claimed about stroke width, fill rule, z-order, "
    "curvature, units, or how any renderer draws this file."
)


class REASON:
    """The ten refusal codes. Every one is produced by a committed input file."""

    NO_STABLE_SCALE = "NO_STABLE_SCALE"
    VERTEX_NEAR_EDGE = "VERTEX_NEAR_EDGE"
    EDGES_CROSS = "EDGES_CROSS"
    EDGE_COLLAPSED = "EDGE_COLLAPSED"
    CURVE_UNSTABLE = "CURVE_UNSTABLE"
    MARGIN_TOO_SMALL = "MARGIN_TOO_SMALL"
    NO_GEOMETRY = "NO_GEOMETRY"
    TOO_MANY_PAIRS = "TOO_MANY_PAIRS"
    TOO_MANY_VERTICES = "TOO_MANY_VERTICES"
    BAD_INPUT = "BAD_INPUT"

    ALL = (
        NO_STABLE_SCALE, VERTEX_NEAR_EDGE, EDGES_CROSS, EDGE_COLLAPSED, CURVE_UNSTABLE,
        MARGIN_TOO_SMALL, NO_GEOMETRY, TOO_MANY_PAIRS, TOO_MANY_VERTICES, BAD_INPUT,
    )


class KIND:
    GEOMETRY = "geometry"   # go re-observe the drawing
    BUDGET = "budget"       # this machine ran out of room
    INPUT = "input"         # the tool never ran


# Which kind each reason carries. An agent consuming JSON must be able to tell
# "re-observe the drawing" from "this machine ran out of room".
KIND_OF = {
    REASON.NO_STABLE_SCALE: KIND.GEOMETRY,
    REASON.VERTEX_NEAR_EDGE: KIND.GEOMETRY,
    REASON.EDGES_CROSS: KIND.GEOMETRY,
    REASON.EDGE_COLLAPSED: KIND.GEOMETRY,
    REASON.CURVE_UNSTABLE: KIND.GEOMETRY,
    REASON.MARGIN_TOO_SMALL: KIND.GEOMETRY,
    REASON.NO_GEOMETRY: KIND.GEOMETRY,
    REASON.TOO_MANY_PAIRS: KIND.BUDGET,
    REASON.TOO_MANY_VERTICES: KIND.BUDGET,
    REASON.BAD_INPUT: KIND.INPUT,
}


class STATUS:
    CERTIFIED = "CERTIFIED"
    REFUSED = "REFUSED"
    HELD = "HELD"
    BROKEN = "BROKEN"
    BAD_INPUT = "BAD INPUT"


EXIT = {
    STATUS.CERTIFIED: 0,
    STATUS.HELD: 0,
    STATUS.BROKEN: 1,
    STATUS.REFUSED: 2,
    STATUS.BAD_INPUT: 3,
}

# Phrases that must never appear in a verdict or in package source outside this
# list. The test that enforces it excludes this tuple by line, and its scope is
# stated where it lives: a word list is a guard, not a proof.
BANNED = (
    "watertight", "manifold", "well-formed", "well formed", "valid geometry",
    "healed", "repaired", "cleaned",
    "confidence", "probability", "percentage",
    "approximately", "roughly",
)

# Site lists are printed up to this many entries; the rest are counted in n_more.
PRINT_CAP = 8


class PlanimeterParseError(Exception):
    """The file could not be read. Exit 3. Not a verdict - the tool never ran."""


def digest(reps: Sequence[Sequence[float]],
           edges: Sequence[Tuple[int, int]],
           t_below: float, t_above: float, rho: float,
           flatten: Sequence[int], version: str = __version__) -> str:
    """SHA-1 over the sorted cluster representatives, the sorted edge list, the
    window endpoints, rho, the flatten pair and the package version.

    It identifies an arrangement under one package version: two stamps collide
    iff the arrangements match. It is a hash of public data under a public
    algorithm and is not tamper-evident.
    """
    # Edge indices are renumbered by the sorted representative order, so two runs
    # that produce the same arrangement in a different internal order collide.
    pts = [(float(x), float(y)) for x, y in reps]
    rank = {i: r for r, i in enumerate(sorted(range(len(pts)), key=lambda i: pts[i]))}
    h = hashlib.sha1()
    payload = {
        "reps": sorted([x, y] for x, y in pts),
        "edges": sorted(tuple(sorted((rank[int(a)], rank[int(b)]))) for a, b in edges),
        "t_below": float(t_below),
        "t_above": float(t_above),
        "rho": float(rho),
        "flatten": [int(n) for n in flatten],
        "version": version,
    }
    h.update(_json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return h.hexdigest()


def _num(x: float) -> str:
    if x == 0.0:
        return "0"
    a = abs(x)
    return ("%.6g" % x) if 1e-4 <= a < 1e7 else ("%.4g" % x)


@dataclass
class Chi:
    """A certified count. `faces` is the number of bounded regions; `chi` is
    derived from it by the identity below, not measured a second way."""

    v: int
    e: int
    pieces: int
    faces: int
    chi: int
    dangles: int
    t_below: float
    t_above: float
    ratio: float
    radius: float
    grid_source: str = "derived"        # "derived" | "user"
    rho: float = 10.0
    n_subdivided: int = 0
    n_dup_edges: int = 0
    n_merged: int = 0
    diam_max: float = 0.0
    n_candidates: int = 1
    flatten: Tuple[int, int] = (16, 32)
    source_format: str = "segments"
    elements_skipped: Dict[str, int] = field(default_factory=dict)
    digest: str = ""
    source: str = ""
    version: str = __version__
    status: str = STATUS.CERTIFIED

    def __post_init__(self) -> None:
        # faces = E - V + pieces is the identity, not a second path to it, so on
        # the computed path this cannot fail and is not called a control
        # (finding 9). It earns its keep on the JSON round-trip, where the four
        # fields arrive independently. ValueError, never assert: -O strips assert.
        if self.faces != self.e - self.v + self.pieces:
            raise ValueError(
                "faces %d != e - v + pieces = %d - %d + %d"
                % (self.faces, self.e, self.v, self.pieces)
            )
        if self.chi != self.pieces - self.faces:
            raise ValueError(
                "chi %d != pieces - faces = %d - %d"
                % (self.chi, self.pieces, self.faces)
            )

    def __bool__(self) -> bool:
        return True

    def __int__(self) -> int:
        return self.faces

    def json(self) -> Dict[str, Any]:
        d = asdict(self)
        d["flatten"] = list(self.flatten)
        d["convention"] = CONVENTION
        return d

    @classmethod
    def from_json(cls, d: Dict[str, Any]) -> "Chi":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if "flatten" in d:
            d["flatten"] = tuple(d["flatten"])
        return cls(**d)

    def block(self) -> str:
        name = self.source or "(segments)"
        L = [RULE, "  planimeter  %s" % name, RULE]
        L.append("  pieces  %14d" % self.pieces)
        L.append("  faces   %14d" % self.faces)
        L.append("  chi     %14d      chi = pieces - faces = V - E" % self.chi)
        if self.dangles:
            L.append("  dangles %14d      degree-1 vertices" % self.dangles)
        L.append(THIN)
        L.append("  vertices %13d      edges %12d" % (self.v, self.e))
        L.append("  subdivided %11d      dup edges %8d" % (self.n_subdivided, self.n_dup_edges))
        L.append("  merged %15d      max cluster diam %s" % (self.n_merged, _num(self.diam_max)))
        L.append("  snap window   [%s, %s)   ratio %s   radius %s   %s"
                 % (_num(self.t_below), _num(self.t_above), _num(self.ratio),
                    _num(self.radius), self.grid_source))
        L.append("  rho %s   flatten %d/%d   candidates tried %d"
                 % (_num(self.rho), self.flatten[0], self.flatten[1], self.n_candidates))
        if self.elements_skipped:
            L.append("  skipped  " + ", ".join("%s %d" % kv for kv in sorted(self.elements_skipped.items())))
        L.append("  digest  %s" % self.digest[:16])
        L.append(RULE)
        return "\n".join(L)


@dataclass
class Refused:
    """One named condition could not be established.

    A refusal is a statement about the evidence, not about the geometry. It is
    falsy and it will not convert to an integer, so `if faces(f):` cannot read
    it as an answer.
    """

    reason: str
    detail: str = ""
    look_at: List[Dict[str, Any]] = field(default_factory=list)
    n_more: int = 0
    action: str = ""
    kind: str = ""
    source: str = ""
    version: str = __version__
    status: str = STATUS.REFUSED

    def __post_init__(self) -> None:
        if not self.kind:
            self.kind = KIND_OF.get(self.reason, KIND.GEOMETRY)

    def __bool__(self) -> bool:
        return False

    def __int__(self) -> int:
        raise TypeError("planimeter refused: %s - %s" % (self.reason, self.detail))

    def json(self) -> Dict[str, Any]:
        d = asdict(self)
        d["convention"] = CONVENTION
        return d

    @classmethod
    def from_json(cls, d: Dict[str, Any]) -> "Refused":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d)

    def block(self) -> str:
        name = self.source or "(segments)"
        L = [RULE, "  planimeter  %-52s REFUSED" % name[:52], RULE]
        L.append("  reason   %s   (%s)" % (self.reason, self.kind))
        if self.detail:
            L.append("  detail   %s" % self.detail)
        for i, site in enumerate(self.look_at[:PRINT_CAP]):
            L.append("  %s %s" % ("look at " if i == 0 else "        ", _site(site)))
        if self.n_more:
            L.append("           ... %d more" % self.n_more)
        if self.action:
            L.append("  action   %s" % self.action)
        L.append(RULE)
        return "\n".join(L)


_SITE_ORDER = ("element", "edge", "other", "d", "length", "ratio", "failed")


def _site(site: Dict[str, Any]) -> str:
    parts = []
    xy = site.get("xy")
    if xy is not None:
        parts.append("(%s, %s)" % (_num(xy[0]), _num(xy[1])))
    for k in _SITE_ORDER:
        if site.get(k) is not None:
            v = site[k]
            parts.append("%s=%s" % (k, _num(v) if isinstance(v, float) else v))
    for k in sorted(site):
        if k not in _SITE_ORDER and k != "xy":
            parts.append("%s=%s" % (k, site[k]))
    return "  ".join(parts)


@dataclass
class Check:
    """Predict-then-verify. Three states, because "the tool could not answer"
    must not be readable as "your prediction was wrong"."""

    verdict: str                       # HELD | BROKEN | REFUSED
    claimed: Dict[str, int]
    actual: Optional[Dict[str, int]]
    result: Any                        # Chi | Refused
    source: str = ""
    version: str = __version__

    def __bool__(self) -> bool:
        return self.verdict == STATUS.HELD

    def json(self) -> Dict[str, Any]:
        return {
            "status": self.verdict, "claimed": self.claimed, "actual": self.actual,
            "result": self.result.json(), "source": self.source, "version": self.version,
        }

    def block(self) -> str:
        L = [self.result.block()]
        if self.verdict == STATUS.REFUSED:
            L.append("  CLAIM   not tested - planimeter refused. Your prediction stands untested.")
        else:
            for k, want in sorted(self.claimed.items()):
                got = (self.actual or {}).get(k)
                L.append("  CLAIM   %-8s stated %-6d  measured %-6s  %s"
                         % (k, want, got, "HELD" if got == want else "BROKEN"))
        return "\n".join(L)


def verdict_from_json(d: Dict[str, Any]):
    return Refused.from_json(d) if d.get("status") == STATUS.REFUSED else Chi.from_json(d)


def _selfcheck() -> None:
    c = Chi(v=9, e=12, pieces=1, faces=4, chi=-3, dangles=0,
            t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.0224)
    assert c.faces == 4 and int(c) == 4 and bool(c)
    assert Chi.from_json(c.json()) == c
    try:
        Chi(v=9, e=12, pieces=1, faces=5, chi=-4, dangles=0,
            t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.0224)
        raise AssertionError("bad faces accepted")
    except ValueError:
        pass
    r = Refused(REASON.VERTEX_NEAR_EDGE, detail="1 vertex in the band",
                look_at=[{"xy": [1.0, 2.0], "d": 2.2e-06}], action="move it")
    assert bool(r) is False and r.kind == KIND.GEOMETRY
    try:
        int(r)
        raise AssertionError("refusal converted to int")
    except TypeError as exc:
        assert REASON.VERTEX_NEAR_EDGE in str(exc)
    assert Refused.from_json(r.json()) == r
    assert set(KIND_OF) == set(REASON.ALL)
    d1 = digest([[0.0, 0.0], [1.0, 0.0]], [(0, 1)], 1e-3, 0.5, 10.0, (16, 32))
    d2 = digest([[1.0, 0.0], [0.0, 0.0]], [(1, 0)], 1e-3, 0.5, 10.0, (16, 32))
    assert d1 == d2, "digest is not order-independent"
    assert d1 != digest([[0.0, 0.0], [1.0, 0.0]], [(0, 1)], 1e-3, 0.6, 10.0, (16, 32))
    for text in (c.block(), r.block()):
        low = text.lower()
        assert not any(b in low for b in BANNED), text
    print(c.block())
    print(r.block())
    print("result.py self-check OK")


if __name__ == "__main__":
    _selfcheck()
