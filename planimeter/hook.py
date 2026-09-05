"""The PostToolUse hook. One short line on every geometric write: 7 cl100k_base
tokens of body and 5 more for a short path, measured by bench.py.

Module scope imports `json`, `sys` and `os` and NOTHING else, and the suffix
check runs before any package import, so a write to a `.py` file costs one
interpreter start and no numpy. Its own `__main__` means
`python -m planimeter.hook` never touches `cli`.

Four contract clauses:

1. Silence is the default. Not Write/Edit, or a suffix outside the reader
   table -> exit 0, zero bytes, nothing imported.
2. Bounded work or refuse. Above the vertex ceiling it stamps a budget token
   rather than stalling the turn.
3. It never raises. Any unexpected exception -> exit 0, empty stdout;
   diagnostics to stderr only under PLANIMETER_HOOK_DEBUG=1. A hook that can
   break a session is a hook that gets uninstalled on day two.
4. It never writes to the geometry file, on any path. That is what makes a
   write-triggered hook installable at all, and it is why healing the geometry
   will never be a feature.
"""

import json
import os
import sys

# The reader table, duplicated here as three literals rather than imported:
# importing read.py to learn which suffixes it handles would defeat clause 1.
# read.py's own suffix table is the authority and test_hook checks they agree.
SUFFIXES = (".svg",)

TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# One non-imperative token per refusal reason. No coordinates, no imperative and
# no next action - those live in the CLI, and a one-line budget spent inviting
# a question this line cannot answer is not a feature. BAD_INPUT stamps nothing:
# a half-written file mid-edit is the common case and is not news.
TOKEN = {
    "NO_STABLE_SCALE": "no certified scale",
    "VERTEX_NEAR_EDGE": "vertex near edge",
    "EDGES_CROSS": "edges cross",
    "EDGE_COLLAPSED": "edge collapsed",
    "CURVE_UNSTABLE": "curve unstable",
    "MARGIN_TOO_SMALL": "margin too small",
    "NO_GEOMETRY": "no line work",
    "TOO_MANY_PAIRS": "too large to certify",
    "TOO_MANY_VERTICES": "too large to certify",
}


def is_geometry(path):
    """Clause 1's gate. Pure string work: no stat, no open, no import."""
    return bool(path) and os.path.splitext(str(path))[1].lower() in SUFFIXES


def cache_path(path):
    """Per-user cache directory, keyed by a hash of the absolute path.

    Nothing is ever written inside the user's repository, so `.gitignore` is
    irrelevant and `planimeter never writes to a geometry file` stays literally
    true. A fresh clone's first write therefore carries no delta.
    """
    import hashlib
    root = (os.environ.get("PLANIMETER_CACHE")
            or os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_CACHE_HOME")
            or os.path.join(os.path.expanduser("~"), ".cache"))
    key = hashlib.sha1(os.path.abspath(path).encode("utf-8", "replace")).hexdigest()[:16]
    return os.path.join(root, "planimeter", key + ".json")


def load_previous(path):
    try:
        with open(cache_path(path), "r") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_current(path, record):
    try:
        p = cache_path(path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            json.dump(record, fh)
    except Exception:
        pass                                    # the delta is a nicety, not the product


def line(path, verdict, previous):
    """The stamp, or None for silence. `verdict` is a Chi or a Refused."""
    name = os.path.basename(path)
    status = getattr(verdict, "status", "")
    if status != "CERTIFIED":
        reason = getattr(verdict, "reason", "")
        if reason == previous.get("reason"):
            return None                         # thirty identical lines train an agent to ignore
        token = TOKEN.get(reason)
        return None if token is None else "planimeter %s  %s" % (name, token)

    # The delta prints only across two certificates of the same object: same
    # status, same rho, same grid_source. A delta across two different windows
    # would describe two different objects.
    same = (previous.get("status") == "CERTIFIED"
            and previous.get("rho") == verdict.rho
            and previous.get("grid_source") == verdict.grid_source)
    was = previous.get("faces")
    faces = ("%d -> %d" % (was, verdict.faces)
             if same and isinstance(was, int) and was != verdict.faces
             else "%d" % verdict.faces)
    out = "planimeter %s  pieces %d  faces %s" % (name, verdict.pieces, faces)
    if verdict.dangles:                          # an integer the user cannot act on, omitted at 0
        out += "  dangles %d" % verdict.dangles
    return out


def record(verdict):
    if getattr(verdict, "status", "") == "CERTIFIED":
        return {"status": "CERTIFIED", "faces": verdict.faces, "pieces": verdict.pieces,
                "rho": verdict.rho, "grid_source": verdict.grid_source}
    return {"status": "REFUSED", "reason": getattr(verdict, "reason", "")}


def stamp(path):
    """Read the file, count, and return the stamp or None. Never writes to it."""
    import planimeter
    verdict = planimeter.chi(path)
    prev = load_previous(path)
    out = line(path, verdict, prev)
    save_current(path, record(verdict))
    return out


def main(argv=None, force=False):
    """stdin carries the PostToolUse payload; stdout carries one line or nothing.

    `force` skips the suffix gate. It exists for one reason: the G7 control is
    this same hook with the suffix check removed, and a benchmark that measures a
    different program than the one it ships is not a control.
    """
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        if not force and payload.get("tool_name") not in TOOLS:
            return 0
        tool_input = payload.get("tool_input") or {}
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        if not force and not is_geometry(path):
            return 0                              # clause 1: nothing imported, nothing printed
        if not path or not os.path.isfile(path):
            return 0
        out = stamp(path)
        if out:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": out}}) + "\n")
    except BaseException:                         # clause 3, and SystemExit is included on purpose
        if os.environ.get("PLANIMETER_HOOK_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
    return 0


def _selfcheck():
    class V(object):
        status, pieces, faces, dangles, rho, grid_source = "CERTIFIED", 1, 4, 0, 10.0, "derived"

    class R(object):
        status, reason = "REFUSED", "VERTEX_NEAR_EDGE"

    assert is_geometry("a/b/walls.svg") and is_geometry("WALLS.SVG")
    assert not is_geometry("x.py") and not is_geometry("x.svg.bak") and not is_geometry("")

    v = V()
    assert line("w.svg", v, {}) == "planimeter w.svg  pieces 1  faces 4"
    prev = record(v)
    v.faces = 5
    assert line("w.svg", v, prev) == "planimeter w.svg  pieces 1  faces 4 -> 5"
    v.dangles = 2
    assert line("w.svg", v, {}).endswith("faces 5  dangles 2")
    v.grid_source = "user"                     # a different window is a different object
    assert line("w.svg", v, prev) == "planimeter w.svg  pieces 1  faces 5  dangles 2"

    r = R()
    assert line("w.svg", r, {}) == "planimeter w.svg  vertex near edge"
    assert line("w.svg", r, record(r)) is None      # same reason twice: silence
    r.reason = "BAD_INPUT"
    assert line("w.svg", r, {}) is None
    assert set(TOKEN) | {"BAD_INPUT"} == set(__import__(
        "planimeter.result", fromlist=["REASON"]).REASON.ALL)

    # the stamp's token budget, path excluded
    body = line("w.svg", V(), {}).split("  ", 1)[1]
    assert len(body.split()) <= 6, body

    # clause 1 end to end, in this process: a .py write imports nothing of ours
    import io
    for payload in ('{"tool_name":"Write","tool_input":{"file_path":"x.py"}}',
                    '{"tool_name":"Bash","tool_input":{"command":"ls"}}',
                    'not json at all', ''):
        sys.stdin, out = io.StringIO(payload), io.StringIO()
        real, sys.stdout = sys.stdout, out
        try:
            assert main() == 0 and out.getvalue() == ""
        finally:
            sys.stdout, sys.stdin = real, sys.__stdin__
    print("hook.py self-check OK")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        sys.exit(main())
