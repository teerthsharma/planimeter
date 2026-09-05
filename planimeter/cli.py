"""The command line.

Every printed block comes from `Chi.block()` / `Refused.block()` / `Check.block()`,
so the only strings this file owns are its own help text and the `init` report.
No example block in the repository is hand-typed.

    planimeter FILE [--json] [--grid X] [--rho R] [--flatten N] [--refuse-ok]
    planimeter --demo
    planimeter check FILE [--faces N] [--pieces N] [--chi N] [--json]
    planimeter hook
    planimeter init [--project|--user] [--check] [--yes]

Exit codes are `result.EXIT`: 0 CERTIFIED/HELD, 1 BROKEN, 2 REFUSED, 3 BAD INPUT.
There is deliberately no exit 1 on a plain run - planimeter has no
"computed successfully, proves nothing" state - so 1 means exactly one thing on
both ladders.
"""

from __future__ import annotations

import argparse
import json as _json
import os
import sys

from .result import (
    EXIT, REASON, STATUS, CONVENTION, Chi, Refused, PlanimeterParseError,
)

# A 2x2 grid of unit cells, drawn as 12 separate <line>s so `--demo` exercises
# the exact-duplicate collapse and the counting layer rather than one <path>.
# Truth by construction: V 9, E 12, pieces 1, faces 4, chi -3.
DEMO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
%s
</svg>
""" % "\n".join(
    '  <line id="%s" x1="%g" y1="%g" x2="%g" y2="%g" stroke="black"/>' % (i, a, b, c, d)
    for i, (a, b, c, d) in enumerate(
        [(x, y, x, y + 10) for x in (0, 10, 20) for y in (0, 10)]
        + [(x, y, x + 10, y) for y in (0, 10, 20) for x in (0, 10)]
    )
)

CLAUDE_MD_BLOCK = (
    "## planimeter\n"
    "Before editing a geometry file, state the pieces and enclosed-face counts the edit "
    "should produce; after it, run `planimeter check FILE --faces N --pieces N` and treat "
    "BROKEN as a failed edit.\n"
)


# --------------------------------------------------------------------------
# printing
# --------------------------------------------------------------------------

def emit(result, as_json: bool, stream=None) -> int:
    """Print one verdict and return its exit code."""
    out = stream or sys.stdout
    if as_json:
        out.write(_json.dumps(result.json(), sort_keys=True) + "\n")
    else:
        out.write(result.block() + "\n")
    status = getattr(result, "verdict", None) or getattr(result, "status", STATUS.REFUSED)
    return EXIT.get(status, EXIT[STATUS.REFUSED])


def _bad(msg: str, stream=None) -> int:
    r = Refused(REASON.BAD_INPUT, detail=msg,
                action="the tool never ran; nothing is claimed about this file")
    (stream or sys.stderr).write(r.block() + "\n")
    return EXIT[STATUS.BAD_INPUT]


# --------------------------------------------------------------------------
# parsers
# --------------------------------------------------------------------------

def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="the machine shape on stdout")
    p.add_argument("--grid", type=float, default=None, metavar="X",
                   help="name the snap radius yourself; still checked, still certified")
    p.add_argument("--rho", type=float, default=None, metavar="R",
                   help="minimum window ratio a scale must clear (policy, default 10)")
    p.add_argument("--max-vertices", type=int, default=None, metavar="N",
                   help="raise the vertex ceiling above its default. Cost grows "
                        "about quadratically; RESULTS.md prints the curve")
    p.add_argument("--flatten", type=int, default=16, metavar="N",
                   help="polyline segments per curve; the run is repeated at 2N")


def build_parser(cmd: str = "") -> argparse.ArgumentParser:
    if cmd == "check":
        p = argparse.ArgumentParser(prog="planimeter check",
                                    description="Predict-then-verify: state the integers you "
                                                "expect, get HELD, BROKEN or REFUSED back.")
        p.add_argument("file")
        p.add_argument("--faces", type=int, default=None)
        p.add_argument("--pieces", type=int, default=None)
        p.add_argument("--chi", type=int, default=None)
        _common(p)
        return p
    if cmd == "init":
        p = argparse.ArgumentParser(prog="planimeter init",
                                    description="Install the PostToolUse hook.")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--project", action="store_true", help="./.claude/settings.json (default)")
        g.add_argument("--user", action="store_true", help="~/.claude/settings.json")
        p.add_argument("--check", action="store_true",
                       help="re-read settings.json and run the hook end to end")
        p.add_argument("--yes", "-y", action="store_true", help="write without confirming")
        return p
    p = argparse.ArgumentParser(
        prog="planimeter",
        description="Three integers for a geometry file - pieces, enclosed faces, Euler "
                    "characteristic - and the snap radius that decided them, or a typed refusal.",
        epilog="subcommands: check FILE --faces N | hook | init")
    p.add_argument("file", nargs="?", help="an SVG file, or - for stdin")
    p.add_argument("--demo", action="store_true", help="certify a built-in 2x2 grid")
    p.add_argument("--convention", action="store_true", help="print the convention and exit")
    p.add_argument("--version", action="store_true")
    p.add_argument("--refuse-ok", action="store_true",
                   help="map REFUSED to exit 0 for make / pre-commit / set -e")
    _common(p)
    return p


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def _read_source(path: str):
    if path == "-":
        return sys.stdin.read()
    return path


def cmd_run(a) -> int:
    import planimeter
    if a.demo:
        res = planimeter.chi(DEMO_SVG, grid=a.grid, rho=a.rho, flatten=a.flatten,
                             max_vertices=a.max_vertices)
        res.source = res.source or "--demo (built-in 2x2 grid)"
    else:
        res = planimeter.chi(_read_source(a.file), grid=a.grid, rho=a.rho,
                             flatten=a.flatten, max_vertices=a.max_vertices)
    code = emit(res, a.json)
    return 0 if (a.refuse_ok and code == EXIT[STATUS.REFUSED]) else code


def cmd_check(a) -> int:
    import planimeter
    if a.faces is None and a.pieces is None and a.chi is None:
        return _bad("check needs at least one of --faces, --pieces, --chi")
    c = planimeter.check(_read_source(a.file), faces=a.faces, pieces=a.pieces, chi=a.chi,
                         grid=a.grid, rho=a.rho, flatten=a.flatten,
                         max_vertices=a.max_vertices)
    return emit(c, a.json)


# --------------------------------------------------------------------------
# init - the only command that writes anything, and it prints the diff first
# --------------------------------------------------------------------------

HOOK_ARGS = "-m planimeter.hook"        # the idempotence key, and the cheap entry point
MATCHER = "Write|Edit"


def hook_command() -> str:
    """Absolute interpreter path plus `-m planimeter.hook`.

    Never the bare console script: `planimeter` on PATH silently never fires the
    moment Scripts/ is off PATH or the venv is not active, and a hook that
    silently never fires is worse than no hook.
    """
    return '"%s" %s' % (sys.executable.replace("\\", "/"), HOOK_ARGS)


def settings_path(a) -> str:
    root = os.path.expanduser("~") if getattr(a, "user", False) else os.getcwd()
    return os.path.join(root, ".claude", "settings.json")


def merge_hook(settings: dict) -> dict:
    """Add our entry to hooks.PostToolUse, leaving every other occupant alone."""
    out = _json.loads(_json.dumps(settings))            # never mutate the caller's dict
    hooks = out.setdefault("hooks", {})
    arr = hooks.setdefault("PostToolUse", [])
    if not isinstance(arr, list):
        raise ValueError("hooks.PostToolUse is %s, not a list" % type(arr).__name__)
    entry = {"type": "command", "command": hook_command(), "timeout": 10}
    for group in arr:
        cmds = (group or {}).get("hooks") or []
        for h in cmds:
            if HOOK_ARGS in str((h or {}).get("command", "")):
                h.update(entry)                          # idempotent by substring
                return out
        if (group or {}).get("matcher") == MATCHER:
            cmds.append(entry)
            group["hooks"] = cmds
            return out
    arr.append({"matcher": MATCHER, "hooks": [entry]})
    return out


def _diff(before: str, after: str, name: str) -> str:
    import difflib
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        name, name))


def _confirm(a) -> bool:
    if getattr(a, "yes", False):
        return True
    if not sys.stdin.isatty():
        sys.stdout.write("  not a terminal; nothing written. Re-run with --yes.\n")
        return False
    try:
        answer = input("  write these changes? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        # isatty() is True and stdin is still unreadable - a closed handle under
        # a task runner, or Ctrl-C at the prompt. Declining is the answer; a
        # traceback out of `init` is not.
        sys.stdout.write("\n  no answer read; nothing written. Re-run with --yes.\n")
        return False
    return answer.strip().lower() in ("y", "yes")


def init_check(a) -> int:
    """Re-read settings.json and run the hook end to end, so `is it on?` is never
    a guess."""
    import subprocess
    import tempfile
    p = settings_path(a)
    try:
        with open(p) as fh:
            found = HOOK_ARGS in fh.read()
    except OSError as exc:
        sys.stdout.write("  settings   %s  MISSING (%s)\n" % (p, exc.strerror))
        return EXIT[STATUS.REFUSED]
    sys.stdout.write("  settings   %s  %s\n" % (p, "hook present" if found else "NO HOOK ENTRY"))

    d = tempfile.mkdtemp(prefix="planimeter-check-")
    svg = os.path.join(d, "demo.svg")
    with open(svg, "w") as fh:
        fh.write(DEMO_SVG)
    payload = _json.dumps({"tool_name": "Write", "tool_input": {"file_path": svg}})
    r = subprocess.run([sys.executable, "-m", "planimeter.hook"], input=payload,
                       capture_output=True, text=True)
    stamp = ""
    try:
        stamp = _json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    except Exception:
        pass
    sys.stdout.write("  hook       exit %d  %s\n"
                     % (r.returncode, stamp or "(no stamp - see PLANIMETER_HOOK_DEBUG=1)"))
    ok = found and r.returncode == 0 and stamp
    return EXIT[STATUS.CERTIFIED] if ok else EXIT[STATUS.REFUSED]


def cmd_init(a) -> int:
    if a.check:
        return init_check(a)

    p = settings_path(a)
    try:
        with open(p) as fh:
            before = fh.read()
        settings = _json.loads(before or "{}")
    except FileNotFoundError:
        before, settings = "", {}
    after = _json.dumps(merge_hook(settings), indent=2) + "\n"

    md = os.path.join(os.getcwd(), "CLAUDE.md")
    md_before = ""
    if os.path.exists(md):
        with open(md) as fh:
            md_before = fh.read()
    md_after = md_before if "planimeter check" in md_before else (
        (md_before.rstrip("\n") + "\n\n" if md_before else "") + CLAUDE_MD_BLOCK)

    changes = [(p, before, after), (md, md_before, md_after)]
    changes = [(n, b, c) for n, b, c in changes if b != c]
    if not changes:
        sys.stdout.write("  already installed; nothing to write.\n  %s\n" % hook_command())
        return EXIT[STATUS.CERTIFIED]
    for name, b, c in changes:
        sys.stdout.write(_diff(b, c, name) or "  + %s\n" % name)
    if not _confirm(a):
        return EXIT[STATUS.REFUSED]
    for name, _b, c in changes:
        d = os.path.dirname(name)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(name, "w") as fh:
            fh.write(c)
        sys.stdout.write("  wrote %s\n" % name)
    return EXIT[STATUS.CERTIFIED]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else ""

    if cmd == "hook":                       # documented, but init writes the cheap form
        from . import hook
        return hook.main()
    if cmd in ("check", "init"):
        a = build_parser(cmd).parse_args(argv[1:])
        try:
            return cmd_check(a) if cmd == "check" else cmd_init(a)
        except (OSError, PlanimeterParseError) as exc:
            return _bad(str(exc))

    a = build_parser().parse_args(argv)
    if a.version:
        from . import __version__
        sys.stdout.write("planimeter %s\n" % __version__)
        return 0
    if a.convention:
        sys.stdout.write(CONVENTION + "\n")
        return 0
    if not a.file and not a.demo:
        build_parser().print_help(sys.stderr)
        return _bad("no file given; try `planimeter --demo`")
    try:
        return cmd_run(a)
    except (OSError, PlanimeterParseError) as exc:
        return _bad(str(exc))


def _selfcheck() -> None:
    """Exercises every path that does not need a reader on disk."""
    import io
    assert EXIT[STATUS.CERTIFIED] == 0 and EXIT[STATUS.BROKEN] == 1
    assert EXIT[STATUS.REFUSED] == 2 and EXIT[STATUS.BAD_INPUT] == 3

    buf = io.StringIO()
    c = Chi(v=9, e=12, pieces=1, faces=4, chi=-3, dangles=0,
            t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.0224, source="demo")
    assert emit(c, False, buf) == 0
    assert emit(c, True, buf) == 0
    assert _json.loads(buf.getvalue().splitlines()[-1])["faces"] == 4

    r = Refused(REASON.VERTEX_NEAR_EDGE, detail="1 vertex in the band")
    assert emit(r, False, io.StringIO()) == 2
    assert _bad("nope", io.StringIO()) == 3

    a = build_parser().parse_args(["--demo", "--rho", "3"])
    assert a.demo and a.rho == 3.0 and a.grid is None
    a = build_parser("check").parse_args(["f.svg", "--faces", "5"])
    assert a.file == "f.svg" and a.faces == 5
    assert build_parser("init").parse_args(["--check"]).check
    assert main(["--version"]) == 0
    assert main(["--convention"]) == 0
    assert DEMO_SVG.count("<line") == 12

    # init merges rather than overwrites, and is idempotent by substring
    other = {"hooks": {"PostToolUse": [
        {"matcher": "Write", "hooks": [{"type": "command", "command": "black $FILE"}]}]}}
    once = merge_hook(other)
    assert once["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "black $FILE"
    assert merge_hook(once) == once, "init is not idempotent"
    flat = _json.dumps(once)
    assert flat.count(HOOK_ARGS) == 1
    assert os.path.isfile(sys.executable)
    assert sys.executable.replace("\\", "/") in hook_command()
    # an existing Write|Edit group gains one entry, not a second group
    grouped = merge_hook({"hooks": {"PostToolUse": [{"matcher": MATCHER, "hooks": []}]}})
    assert len(grouped["hooks"]["PostToolUse"]) == 1
    print("cli.py self-check OK")


if __name__ == "__main__":
    # `python -m planimeter.cli` is the self-check; `python -m planimeter` and the
    # console script are the command line.
    _selfcheck()
