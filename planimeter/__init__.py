"""planimeter - three integers for a geometry file, and the scale that decided them.

    import planimeter
    c = planimeter.chi("walls.svg")     # Chi, or Refused. Never raises for geometry reasons.
    c.pieces, c.faces, c.chi            # 1, 5, -4
    c.t_below, c.t_above, c.radius      # the certified window, printed with the answer

`import planimeter` touches nothing but this docstring: names resolve lazily
through PEP 562, so the hook can decide a file is not geometry before numpy
or the reader is ever loaded.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "chi", "chi_segments", "segments", "check",
    "Chi", "Refused", "Check", "REASON", "KIND", "STATUS", "EXIT",
    "CONVENTION", "PlanimeterParseError", "__version__",
]

_LAZY = {
    "Chi": "result", "Refused": "result", "Check": "result", "REASON": "result",
    "KIND": "result", "STATUS": "result", "EXIT": "result", "CONVENTION": "result",
    "PlanimeterParseError": "result", "digest": "result",
    "chi_segments": "arrange", "arrange": "arrange",
    "segments": "read", "Segments": "read",
    "snap": "snap", "count": "count", "result": "result", "read": "read",
}


def __getattr__(name):
    mod = _LAZY.get(name)
    if mod is None:
        raise AttributeError("module 'planimeter' has no attribute %r" % name)
    import importlib
    m = importlib.import_module("." + mod, __name__)
    value = m if name == mod else getattr(m, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(__all__) | set(_LAZY))


def chi(source, *, grid=None, rho=None, flatten=16):
    """The verdict for a geometry file, a PathLike, or SVG text.

    Raises only OSError / PlanimeterParseError; every geometry outcome is a
    value, not an exception. `chi()` is literally `chi_segments(segments(...))`.
    """
    from .arrange import chi_segments
    from .read import segments as _segments
    seg = _segments(source, flatten=flatten)
    return chi_segments(seg, grid=grid, rho=rho, flatten=flatten)


def check(source, *, faces=None, pieces=None, chi=None, **kw):
    """Predict-then-verify: state the integers you expect, get HELD, BROKEN or
    REFUSED back. Three states, because "the tool could not answer" must not be
    readable as "your prediction was wrong"."""
    from .result import Check, Chi as _Chi, STATUS
    claimed = {k: v for k, v in
               (("faces", faces), ("pieces", pieces), ("chi", chi)) if v is not None}
    if not claimed:
        raise ValueError("check() needs at least one of faces=, pieces=, chi=")
    result = globals()["chi"](source, **kw) if not isinstance(source, _Chi) else source
    if not isinstance(result, _Chi):
        return Check(STATUS.REFUSED, claimed, None, result, source=getattr(result, "source", ""))
    actual = {"faces": result.faces, "pieces": result.pieces, "chi": result.chi}
    held = all(actual[k] == v for k, v in claimed.items())
    return Check(STATUS.HELD if held else STATUS.BROKEN, claimed, actual, result,
                 source=result.source)
