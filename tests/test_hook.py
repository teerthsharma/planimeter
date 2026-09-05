"""The hook's four contract clauses, and the token budget.

Every test here runs the hook in a cold subprocess, because that is what the
harness does; the in-process shortcuts would not catch an import that only fires
under `-m`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

import pytest

from planimeter import hook
from planimeter.cli import DEMO_SVG
from planimeter.result import REASON

HAS_READER = importlib.util.find_spec("planimeter.read") is not None
needs_reader = pytest.mark.skipif(not HAS_READER, reason="read.py is not in the package yet")

SILENT = [
    ("Write", "a.py"), ("Write", "notes.md"), ("Write", "a.txt"),
    ("Write", "package.json"), ("Edit", "a.PYI"), ("Write", "walls.svg.bak"),
    ("Bash", "walls.svg"), ("Read", "walls.svg"), ("Write", ""),
]


def run(payload, env=None, args=("-m", "planimeter.hook")):
    e = dict(os.environ)
    e.pop("PLANIMETER_HOOK_DEBUG", None)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], input=payload, capture_output=True,
                          text=True, env=e)


def payload(tool, path):
    return json.dumps({"tool_name": tool, "tool_input": {"file_path": path},
                       "session_id": "x", "cwd": "."})


# --------------------------------------------------------------------------
# clause 1: silence is the default, and it costs nothing
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tool,path", SILENT)
def test_hook_is_silent(tool, path, tmp_path):
    p = tmp_path / (path or "x")
    if path:
        p.write_text("nothing here\n")
    r = run(payload(tool, str(p) if path else ""))
    assert r.returncode == 0
    assert r.stdout == "", r.stdout


def test_silent_path_imports_nothing_heavy(tmp_path):
    """The product claim, not its symptom: a .py write must not pay for numpy,
    svgelements or the package itself."""
    p = tmp_path / "a.py"
    p.write_text("x = 1\n")
    probe = (
        "import sys, json;"
        "from planimeter.hook import main;"
        "main();"
        "sys.stderr.write(json.dumps(sorted("
        "  m for m in ('numpy', 'svgelements', 'shapely', 'scipy', 'planimeter.read',"
        "              'planimeter.snap', 'planimeter.arrange', 'planimeter.cli')"
        "  if m in sys.modules)))"
    )
    r = run(payload("Write", str(p)), args=("-c", probe))
    assert r.returncode == 0 and r.stdout == ""
    assert json.loads(r.stderr) == []


def test_suffix_table_agrees_with_the_reader():
    """hook.py duplicates the suffix list rather than importing read.py, so the
    two are checked against each other here instead of drifting apart."""
    if not HAS_READER:
        pytest.skip("read.py is not in the package yet")
    from planimeter import read
    table = getattr(read, "SUFFIXES", None) or getattr(read, "READERS", None)
    if table is None:
        pytest.skip("read.py exposes no suffix table to compare against")
    assert set(hook.SUFFIXES) <= {s.lower() for s in table}


# --------------------------------------------------------------------------
# clause 3: it never raises
# --------------------------------------------------------------------------

def test_hook_never_raises(tmp_path):
    binary = tmp_path / "binary.svg"
    binary.write_bytes(bytes(range(256)) * 40)
    missing = tmp_path / "gone.svg"
    big = tmp_path / "big.svg"
    big.write_text("<svg>" + "<!-- pad -->" * 200000 + "</svg>")
    cases = [
        "", "not json at all", "[]", "null", "{}",
        '{"tool_name":"Write"}',
        '{"tool_name":"Write","tool_input":null}',
        '{"tool_name":"Write","tool_input":{"file_path":null}}',
        payload("Write", str(missing)),
        payload("Write", str(binary)),
        payload("Write", str(big)),
        payload("Write", str(tmp_path)),          # a directory
    ]
    for pl in cases:
        r = run(pl)
        assert r.returncode == 0, (pl[:60], r.stderr[-400:])
        assert r.stdout == "" or "hookSpecificOutput" in r.stdout, pl[:60]


@needs_reader
def test_cli_is_allowed_to_fail_where_the_hook_is_not(tmp_path):
    """The control for the test above: the same missing file through the CLI
    exits 3. Silence is the hook's contract, not the tool's."""
    missing = tmp_path / "gone.svg"
    r = subprocess.run([sys.executable, "-m", "planimeter", str(missing)],
                       capture_output=True, text=True)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)


# --------------------------------------------------------------------------
# clause 4, and the stamp
# --------------------------------------------------------------------------

@needs_reader
def test_hook_never_writes_to_the_geometry_file(tmp_path):
    svg = tmp_path / "demo.svg"
    svg.write_text(DEMO_SVG)
    before = (svg.read_bytes(), svg.stat().st_mtime_ns)
    run(payload("Write", str(svg)), env={"PLANIMETER_CACHE": str(tmp_path / "cache")})
    assert (svg.read_bytes(), svg.stat().st_mtime_ns) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cache", "demo.svg"]


@needs_reader
def test_stamp_and_delta(tmp_path):
    cache = {"PLANIMETER_CACHE": str(tmp_path / "cache")}
    svg = tmp_path / "demo.svg"
    svg.write_text(DEMO_SVG)
    first = run(payload("Write", str(svg)), env=cache)
    assert first.returncode == 0
    ctx = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx == "planimeter demo.svg  pieces 1  faces 4", ctx

    # remove one wall of one cell: the 2x2 grid loses a face
    svg.write_text(DEMO_SVG.replace('<line id="0" x1="0" y1="0" x2="0" y2="10" stroke="black"/>',
                                    ""))
    second = run(payload("Write", str(svg)), env=cache)
    ctx = json.loads(second.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "faces 4 -> 3" in ctx, ctx


@needs_reader
def test_a_fresh_cache_carries_no_delta(tmp_path):
    svg = tmp_path / "demo.svg"
    svg.write_text(DEMO_SVG)
    r = run(payload("Write", str(svg)), env={"PLANIMETER_CACHE": str(tmp_path / "c1")})
    assert "->" not in r.stdout


def test_stamp_token_budget():
    """The line, path excluded, under the published budget. The path's cost is
    reported separately because a long path tokenises differently."""
    class V:
        status, pieces, faces, dangles, rho, grid_source = "CERTIFIED", 1, 4, 2, 10.0, "derived"

    body = hook.line("/very/long/path/to/walls.svg", V(), {}).split("  ", 1)[1]
    assert body == "pieces 1  faces 4  dangles 2"
    assert len(body.split()) <= 6


def test_repeated_refusal_is_stamped_once():
    class R:
        status, reason = "REFUSED", REASON.VERTEX_NEAR_EDGE

    r = R()
    assert hook.line("w.svg", r, {}) is not None
    assert hook.line("w.svg", r, hook.record(r)) is None
    r2 = R()
    r2.reason = REASON.EDGES_CROSS
    assert hook.line("w.svg", r2, hook.record(r)) == "planimeter w.svg  edges cross"


def test_every_refusal_code_has_a_token_or_is_deliberately_silent():
    assert set(hook.TOKEN) | {REASON.BAD_INPUT} == set(REASON.ALL)
    assert REASON.BAD_INPUT not in hook.TOKEN        # the tool never ran; that is not news
    for token in hook.TOKEN.values():
        assert token == token.lower() and len(token.split()) <= 4
        # non-imperative: the imperative lives in the CLI, not in nine tokens
        assert not token.startswith(("move", "split", "pass", "run", "fix", "add", "write"))


def test_module_selfcheck_runs():
    r = subprocess.run([sys.executable, "-m", "planimeter.hook", "--selfcheck"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "self-check OK" in r.stdout, r.stderr[-800:]
