"""The input layer: an SVG file becomes an (m, 2, 2) float64 array and nothing else.

Three rules hold everywhere in this file.

  1. No coordinate is invented. Straight segments are copied out of the file
     verbatim; curves are the one exception and they are handled by the
     refinement rule below, not by a tolerance.
  2. Nothing here decides anything. `segments()` reports what it read and what
     it skipped; whether that is enough geometry to answer is `arrange`'s call
     (`NO_GEOMETRY` is raised there, from the skipped report built here).
  3. The reader never writes. Files are opened read-only, on every path.

**Curves.** A curve has no vertex set, so flattening has to choose one, and the
number of pieces is exactly the kind of invented number this package exists to
refuse. The cycle is broken by never letting the flattening consult the
certificate: a curve flattens at a fixed `N` and again at `2N`, the whole
pipeline runs twice, and identical verdicts with identical integers is what
`CERTIFIED` means for a file with curves. Disagreement is `CURVE_UNSTABLE`.
That is evidence, not a theorem - two nearly tangent curves can gain or lose an
intersection at every positive tolerance and still agree at `N` and `2N` - and
`stable()` says so in one line rather than defending it.

A file with no curves pays none of this: `has_curves` is False and the second
pass never runs.

Self-check:  python -m planimeter.read
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .result import KIND, REASON, Chi, PlanimeterParseError, Refused

# The suffixes this reader claims. `hook.py` must NOT import this - it decides a
# file is not geometry before importing anything - so the table is duplicated
# there by design and `test_hook_suffixes_match_the_reader` is what keeps the
# two honest.
SUFFIXES = (".svg",)

# Default curve refinement. The pair (N, 2N) is stamped into every verdict and
# into the digest, because two files that differ only in N are two different
# arrangements and must not collide.
FLATTEN = 16

# Container and metadata tags: present in the tree, never geometry, never
# counted as skipped. Anything outside this set that carries no segments is
# reported by tag, so `NO_GEOMETRY` on a file that visibly has geometry names
# what it could not use instead of reading as a bug.
_CONTAINERS = frozenset({
    "svg", "g", "defs", "symbol", "clippath", "mask", "marker", "pattern",
    "title", "desc", "style", "metadata", "switch", "a", "view", "script",
    "lineargradient", "radialgradient", "stop", "filter", "font", "fontface",
    "animate", "animatetransform", "animatemotion", "set", "use",
})


@dataclass
class Segments:
    """What a file contained, and what it did not.

    Duck-typed by `arrange._as_segments`: `.seg` plus optional `.ids`,
    `.skipped`, `.source`, `.source_format`, `.flatten`.
    """

    seg: np.ndarray                                   # (m, 2, 2) float64
    ids: List[str] = field(default_factory=list)      # "path#wall-7", one per segment
    skipped: Dict[str, int] = field(default_factory=dict)
    source: str = ""
    source_format: str = "svg"
    flatten: Tuple[int, int] = (FLATTEN, 2 * FLATTEN)
    n_curves: int = 0
    n_degenerate: int = 0                             # zero-length, dropped exactly
    n_elements: int = 0

    @property
    def has_curves(self) -> bool:
        return self.n_curves > 0

    def __len__(self) -> int:
        return len(self.seg)

    def __array__(self, dtype=None):
        return self.seg if dtype is None else self.seg.astype(dtype)

    def __repr__(self) -> str:
        return ("Segments(%d segments, %d elements, %d curves, flatten %d/%d, %s)"
                % (len(self.seg), self.n_elements, self.n_curves,
                   self.flatten[0], self.flatten[1], self.source or "(text)"))


def _text_and_name(source: Any) -> Tuple[str, str]:
    """Return the SVG text and the name to print. OSError propagates: a missing
    file is the caller's problem, not a verdict."""
    if hasattr(source, "read"):
        data = source.read()
        return (data.decode("utf-8", "replace") if isinstance(data, bytes) else data,
                str(getattr(source, "name", "<stream>")))
    if isinstance(source, bytes):
        source = source.decode("utf-8", "replace")
    if isinstance(source, os.PathLike):
        source = os.fspath(source)
    if not isinstance(source, str):
        raise PlanimeterParseError(
            "source must be a path, PathLike, SVG text or a file object; got %s"
            % type(source).__name__)
    head = source[:512].lstrip().lower()
    if head.startswith("<") and ("<svg" in source[:4096].lower() or head.startswith("<?xml")):
        return source, "<text>"
    with open(source, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read(), str(source)


def _element_id(elem, tag: str, seen: Dict[str, int]) -> str:
    ident = getattr(elem, "id", None)
    if not ident:
        seen[tag] = seen.get(tag, 0) + 1
        ident = str(seen[tag] - 1)
    return "%s#%s" % (tag, ident)


def segments(source: Any, *, flatten: int = FLATTEN) -> Segments:
    """Read an SVG path, PathLike, file object or SVG text into segments.

    Raises `OSError` (the file is not there) or `PlanimeterParseError` (it is
    not SVG). Every geometry outcome is a value, not an exception.
    """
    n = int(flatten)
    if n < 1:
        raise ValueError("flatten must be >= 1; got %r" % (flatten,))
    text, name = _text_and_name(source)
    try:
        import io

        from svgelements import (SVG, Close, Line, Move, Shape)
        from svgelements import Path as SvgPath
    except ImportError as exc:                                   # pragma: no cover
        raise PlanimeterParseError("svgelements is required to read SVG: %s" % exc)

    n_empty_paths = 0
    try:
        tree = SVG.parse(io.StringIO(text), reify=True)
        elements = list(tree.elements())
    except PlanimeterParseError:                                 # pragma: no cover
        raise
    except Exception as exc:
        # Measured on real files, not anticipated: 2 of 96 Wikimedia Commons
        # floor plans carry an Inkscape <path> with no `d`, and svgelements
        # raises TypeError inside its own parser on it. An element with no `d`
        # has no geometry by the SVG grammar, so dropping it invents nothing -
        # but it is reported as `path-without-d`, never dropped silently.
        text2, n_empty_paths = _drop_empty_paths(text)
        if not n_empty_paths:
            raise PlanimeterParseError("%s: %s: %s" % (name, type(exc).__name__, exc))
        try:
            tree = SVG.parse(io.StringIO(text2), reify=True)
            elements = list(tree.elements())
        except Exception as exc2:
            raise PlanimeterParseError("%s: %s: %s" % (name, type(exc2).__name__, exc2))

    out: List[List[List[float]]] = []
    ids: List[str] = []
    skipped: Dict[str, int] = {}
    if n_empty_paths:
        skipped["path-without-d"] = n_empty_paths
    counter: Dict[str, int] = {}
    closes: List[int] = []
    n_curves = n_degenerate = n_elements = 0

    for elem in elements:
        tag = str((getattr(elem, "values", None) or {}).get("tag", "")).lower()
        if tag in _CONTAINERS:
            continue
        n_elements += 1
        if not isinstance(elem, Shape):
            skipped[tag or type(elem).__name__.lower()] = \
                skipped.get(tag or type(elem).__name__.lower(), 0) + 1
            continue
        ident = _element_id(elem, tag or "shape", counter)
        try:
            pieces = list(SvgPath(elem))
        except Exception as exc:
            raise PlanimeterParseError("%s: %s: %s" % (ident, type(exc).__name__, exc))
        before = len(out)
        for piece in pieces:
            if isinstance(piece, Move):
                continue
            a, b = getattr(piece, "start", None), getattr(piece, "end", None)
            if a is None or b is None:
                continue
            if isinstance(piece, (Line, Close)):
                pts = [(float(a.x), float(a.y)), (float(b.x), float(b.y))]
            else:
                n_curves += 1
                pts = [(float(piece.point(i / n).x), float(piece.point(i / n).y))
                       for i in range(n + 1)]
                # The endpoints come from the curve, not from the sampler, so a
                # shared endpoint between two curves stays bitwise shared.
                pts[0] = (float(a.x), float(a.y))
                pts[-1] = (float(b.x), float(b.y))
            for p, q in zip(pts, pts[1:]):
                if p == q:                      # exact, not a tolerance
                    n_degenerate += 1
                    continue
                if isinstance(piece, Close):
                    closes.append(len(out))
                out.append([[p[0], p[1]], [q[0], q[1]]])
                ids.append(ident)
        if len(out) == before:
            skipped[tag or "shape"] = skipped.get(tag or "shape", 0) + 1

    seg = (np.asarray(out, dtype=np.float64) if out
           else np.zeros((0, 2, 2), dtype=np.float64))
    seg, ids, dropped = _drop_spurious_closures(seg, ids, closes)
    n_degenerate += dropped
    return Segments(seg=seg, ids=ids, skipped=skipped, source=name,
                    source_format="svg", flatten=(n, 2 * n), n_curves=n_curves,
                    n_degenerate=n_degenerate, n_elements=n_elements)


def _drop_empty_paths(text: str) -> Tuple[str, int]:
    """Strip `<path>` elements carrying no `d`, and say how many.

    Only ever called after `svgelements` has already failed on the file. No
    coordinate is added, moved or rounded: the elements removed have no
    coordinates at all.
    """
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return text, 0
    n = 0
    for parent in root.iter():
        for child in list(parent):
            if child.tag.split("}")[-1] == "path" and not (child.get("d") or "").strip():
                parent.remove(child)
                n += 1
    if not n:
        return text, 0
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="unicode"), n


def _drop_spurious_closures(seg: np.ndarray, ids: List[str],
                            closes: Sequence[int]) -> Tuple[np.ndarray, List[str], int]:
    """Drop a `Z` whose two ends are the same point below the representability floor.

    `Z` closes a subpath back to its start, so on a shape that already returns
    there - a circle, an ellipse, a closed path - the closing edge has length
    zero by the SVG grammar. `svgelements` reconstructs a circle from four arcs
    and its endpoint misses the start by about 1e-15 at radius 5, so the closure
    arrives as a real edge a thousand times shorter than anything else in the
    file. Emitting it poisons the spectrum and refuses every circle.

    The cut is the package's own representability floor - `FLOOR_ULPS` ulps of
    the drawing's magnitude, the same `delta` that anchors the merge spectrum -
    and not a new tolerance: below it two coordinates are not distinguishable
    from float64 noise at this drawing's scale, which is already this package's
    stated position. A rectangle's `Z` is its fourth side and is orders of
    magnitude above the floor, so it survives; nothing but a numerically
    zero-length closure is ever dropped.
    """
    if not len(closes) or not len(seg):
        return seg, ids, 0
    from .snap import floor_delta

    delta = floor_delta(seg.reshape(-1, 2))
    idx = np.asarray(closes, dtype=np.intp)
    d = np.hypot(*(seg[idx, 1] - seg[idx, 0]).T)
    doomed = idx[d < delta]
    if not len(doomed):
        return seg, ids, 0
    keep = np.ones(len(seg), dtype=bool)
    keep[doomed] = False
    return seg[keep], [i for i, k in zip(ids, keep) if k], int(len(doomed))


def _shape(verdict) -> Tuple:
    """What "the same verdict" means across two flattenings. V and E are not in
    it: a finer flattening has more of both by construction, and comparing them
    would make every curve unstable."""
    if isinstance(verdict, Chi):
        return (verdict.status, verdict.pieces, verdict.faces, verdict.chi)
    return (verdict.status, verdict.reason)


def stable(coarse, fine, seg: Optional[Segments] = None):
    """Refinement stability: `coarse` if the two flattenings agree, else
    `CURVE_UNSTABLE`.

    Evidence, not a theorem. Agreement at `N` and `2N` does not prove the
    flattened polyline has the topology of the curve; it proves the answer did
    not move when the only invented number in the pipeline was doubled.
    """
    if _shape(coarse) == _shape(fine):
        return coarse
    flat = tuple(getattr(seg, "flatten", (FLATTEN, 2 * FLATTEN)))
    # Measured on real files, not anticipated: on 5 of 96 Wikimedia Commons
    # plans the N pass produced a verdict and the 2N pass - which has about
    # twice the vertices by construction - hit the vertex ceiling instead.
    # The two passes did not disagree about the drawing; the second one never
    # ran. Calling that CURVE_UNSTABLE sends an agent to re-observe a curve
    # over a machine that ran out of room, so the budget refusal is what is
    # returned, with its own kind, and the N pass verdict is carried in the
    # detail.
    if getattr(fine, "kind", "") == KIND.BUDGET:
        return Refused(
            fine.reason,
            detail="flattening at %d gave %s; at %d the stability pass did not fit: %s"
                   % (flat[0], _say(coarse), flat[1], fine.detail),
            look_at=list(fine.look_at),
            action="raise --max-vertices past the 2N pass, or replace the curve "
                   "with a polyline",
            source=getattr(seg, "source", "") or getattr(coarse, "source", ""),
        )
    src = getattr(seg, "source", "") or getattr(coarse, "source", "")
    ids = list(getattr(seg, "ids", ()) or ())
    curves = sorted({i for i in ids})[:4]
    return Refused(
        REASON.CURVE_UNSTABLE,
        detail="flattening at %d and at %d gave %s and %s"
               % (flat[0], flat[1], _say(coarse), _say(fine)),
        look_at=[{"element": c} for c in curves],
        action="pass --flatten %d, or replace the curve with a polyline" % (4 * flat[0]),
        source=src,
    )


def _say(verdict) -> str:
    if isinstance(verdict, Chi):
        return "pieces %d faces %d" % (verdict.pieces, verdict.faces)
    return "REFUSED %s" % verdict.reason


def bad_input(source: Any, exc: BaseException) -> Refused:
    """The tool never ran. Exit 3, `kind` is `input`, and it is deliberately not
    a geometry verdict: an agent that re-observes the drawing because the path
    was misspelled has burnt a turn on the wrong thing."""
    return Refused(
        REASON.BAD_INPUT,
        detail="%s: %s" % (type(exc).__name__, exc),
        kind=KIND.INPUT,
        action="check the path and that the file is SVG",
        source=str(source),
    )


def _selfcheck() -> None:
    text = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <line id="floor" x1="0" y1="0" x2="10" y2="0"/>
      <rect x="0" y="0" width="10" height="10"/>
      <g transform="translate(100,0)"><line x1="0" y1="0" x2="1" y2="0"/></g>
      <line x1="5" y1="5" x2="5" y2="5"/>
      <text x="1" y="1">not geometry</text>
    </svg>"""
    s = segments(text)
    assert s.seg.shape == (6, 2, 2), s.seg.shape       # 1 line + 4 rect sides + 1 in g
    assert s.n_degenerate == 1, s.n_degenerate          # the zero-length line, dropped
    # a shape that carried no usable segment is reported, not silently absent
    assert s.skipped == {"text": 1, "line": 1}, s.skipped
    assert s.ids[0] == "line#floor", s.ids[0]
    assert not s.has_curves
    assert np.allclose(s.seg[-1], [[100.0, 0.0], [101.0, 0.0]]), "transform not applied"

    circle = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="0" cy="0" r="5"/></svg>'
    c16, c32 = segments(circle, flatten=16), segments(circle, flatten=32)
    assert c16.has_curves and len(c16.seg) == 64 and len(c32.seg) == 128, len(c16.seg)
    assert c16.flatten == (16, 32)

    empty = segments('<svg xmlns="http://www.w3.org/2000/svg"><text x="0" y="0">a</text></svg>')
    assert len(empty) == 0 and empty.skipped == {"text": 1}

    for bad in ("not xml at all", 42):
        try:
            segments(bad)
        except (PlanimeterParseError, OSError):
            pass
        else:
            raise AssertionError("accepted %r" % (bad,))

    a = Chi(v=4, e=4, pieces=1, faces=1, chi=0, dangles=0,
            t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.02)
    b = Chi(v=8, e=8, pieces=1, faces=1, chi=0, dangles=0,
            t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.02)
    assert stable(a, b, c16) is a, "a finer flattening must not be called unstable"
    d = Refused(REASON.EDGES_CROSS, detail="x")
    r = stable(a, d, c16)
    assert r.reason == REASON.CURVE_UNSTABLE and not r
    assert bad_input("nope.svg", OSError("no such file")).kind == KIND.INPUT
    print(repr(s))
    print(r.block())
    print("read.py self-check OK")


if __name__ == "__main__":
    _selfcheck()
