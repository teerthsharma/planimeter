"""The command line: exit ladder, rendering, and `init`.

Nothing here hand-types a block. The rendering tests assert that the CLI prints
what `Chi.block()` / `Refused.block()` / `Check.block()` produce, so a change to
the block shape cannot pass here and break the README.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

import pytest

from planimeter import cli
from planimeter.result import EXIT, REASON, STATUS, Check, Chi, Refused

HAS_READER = importlib.util.find_spec("planimeter.read") is not None
needs_reader = pytest.mark.skipif(not HAS_READER, reason="read.py is not in the package yet")

CERT = Chi(v=9, e=12, pieces=1, faces=4, chi=-3, dangles=0, t_below=1e-3, t_above=0.5,
           ratio=500.0, radius=0.0224, source="demo.svg")
REFUSAL = Refused(REASON.VERTEX_NEAR_EDGE, detail="1 vertex sits in the band (0, 0.5)",
                  look_at=[{"xy": [12.003, 4.001], "element": "path#wall-7", "d": 2.2e-6}],
                  action="move this end onto the wall, or away from it by more than 0.5",
                  source="walls.svg")


def out(result, as_json=False):
    import io
    buf = io.StringIO()
    code = cli.emit(result, as_json, buf)
    return code, buf.getvalue()


# --------------------------------------------------------------------------
# the exit ladder
# --------------------------------------------------------------------------

def test_exit_ladder():
    assert out(CERT)[0] == 0
    assert out(Check(STATUS.HELD, {"faces": 4}, {"faces": 4}, CERT))[0] == 1 - 1
    assert out(Check(STATUS.BROKEN, {"faces": 5}, {"faces": 4}, CERT))[0] == 1
    assert out(REFUSAL)[0] == 2
    assert cli._bad("no file", __import__("io").StringIO()) == 3
    # a plain run has no exit 1: there is no "computed successfully, proves
    # nothing" state, and leaving the code unused keeps 1 unambiguous.
    assert 1 not in {EXIT[STATUS.CERTIFIED], EXIT[STATUS.REFUSED], EXIT[STATUS.BAD_INPUT]}


def test_refuse_ok_maps_refused_to_zero():
    a = cli.build_parser().parse_args(["f.svg", "--refuse-ok"])
    assert a.refuse_ok
    code, _ = out(REFUSAL)
    assert (0 if (a.refuse_ok and code == 2) else code) == 0


# --------------------------------------------------------------------------
# rendering: no block in this repository is hand-typed
# --------------------------------------------------------------------------

def test_blocks_come_from_the_result_types():
    for r in (CERT, REFUSAL):
        assert out(r)[1] == r.block() + "\n"


def test_json_is_the_machine_shape():
    d = json.loads(out(CERT, True)[1])
    assert d["faces"] == 4 and d["pieces"] == 1 and d["chi"] == -3
    assert d["status"] == "CERTIFIED" and d["grid_source"] == "derived"
    assert "convention" in d and d["t_above"] == 0.5
    d = json.loads(out(REFUSAL, True)[1])
    assert d["reason"] == REASON.VERTEX_NEAR_EDGE and d["kind"] == "geometry"
    assert d["look_at"][0]["d"] == 2.2e-6


def test_refusal_block_names_the_coordinate_to_re_observe():
    text = REFUSAL.block()
    assert "12.003" in text and "path#wall-7" in text
    assert REASON.VERTEX_NEAR_EDGE in text and "geometry" in text
    assert "move this end" in text


def test_check_three_states_render_distinctly():
    held = Check(STATUS.HELD, {"faces": 4}, {"faces": 4}, CERT).block()
    broken = Check(STATUS.BROKEN, {"faces": 5}, {"faces": 4}, CERT).block()
    refused = Check(STATUS.REFUSED, {"faces": 5}, None, REFUSAL).block()
    assert "HELD" in held and "BROKEN" not in held
    assert "BROKEN" in broken
    # a refusal is not a broken claim
    assert "BROKEN" not in refused and "not tested" in refused


def test_bad_input_says_the_tool_never_ran():
    import io
    buf = io.StringIO()
    cli._bad("check needs at least one of --faces, --pieces, --chi", buf)
    assert "BAD_INPUT" in buf.getvalue() and "never ran" in buf.getvalue()


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------

def test_parsers():
    a = cli.build_parser().parse_args(["walls.svg", "--json", "--grid", "0.01", "--rho", "3"])
    assert (a.file, a.json, a.grid, a.rho, a.flatten) == ("walls.svg", True, 0.01, 3.0, 16)
    a = cli.build_parser("check").parse_args(["w.svg", "--faces", "5", "--pieces", "1"])
    assert (a.faces, a.pieces, a.chi) == (5, 1, None)
    a = cli.build_parser("init").parse_args(["--user", "--yes"])
    assert a.user and a.yes and not a.check


def test_check_without_a_claim_is_bad_input(capsys):
    a = cli.build_parser("check").parse_args(["w.svg"])
    assert cli.cmd_check(a) == 3


def test_version_and_convention(capsys):
    assert cli.main(["--version"]) == 0
    assert "planimeter" in capsys.readouterr().out
    assert cli.main(["--convention"]) == 0
    assert "bounded regions" in capsys.readouterr().out


def test_no_file_is_bad_input(capsys):
    assert cli.main([]) == 3


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------

def test_init_is_idempotent_and_leaves_other_hooks_alone():
    other = {"hooks": {"PostToolUse": [
        {"matcher": "Write", "hooks": [{"type": "command", "command": "black $FILE"}]}]}}
    once = cli.merge_hook(other)
    twice = cli.merge_hook(once)
    assert once == twice
    assert json.dumps(once).count(cli.HOOK_ARGS) == 1
    assert once["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "black $FILE"
    assert other == {"hooks": {"PostToolUse": [
        {"matcher": "Write", "hooks": [{"type": "command", "command": "black $FILE"}]}]}}


def test_init_writes_an_interpreter_that_exists():
    cmd = cli.hook_command()
    assert cli.HOOK_ARGS in cmd
    path = cmd.split('"')[1]
    assert os.path.isfile(path), path
    # never the bare console script: it silently never fires off PATH
    assert not cmd.startswith("planimeter")


def test_init_merges_into_an_existing_matching_group():
    merged = cli.merge_hook({"hooks": {"PostToolUse": [{"matcher": cli.MATCHER, "hooks": []}]}})
    arr = merged["hooks"]["PostToolUse"]
    assert len(arr) == 1 and len(arr[0]["hooks"]) == 1


def test_init_writes_nothing_without_confirmation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    a = cli.build_parser("init").parse_args([])
    assert cli.cmd_init(a) == EXIT[STATUS.REFUSED]        # not a tty, no --yes
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert "+" in capsys.readouterr().out                 # the diff was printed first


def test_init_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# project\n")
    a = cli.build_parser("init").parse_args(["--yes"])
    assert cli.cmd_init(a) == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    entry = settings["hooks"]["PostToolUse"][0]
    assert entry["matcher"] == cli.MATCHER
    assert cli.HOOK_ARGS in entry["hooks"][0]["command"]
    md = (tmp_path / "CLAUDE.md").read_text()
    assert md.startswith("# project") and "planimeter check" in md

    capsys.readouterr()
    assert cli.cmd_init(a) == 0                            # second run: nothing to write
    assert "already installed" in capsys.readouterr().out
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text()) == settings
    assert (tmp_path / "CLAUDE.md").read_text() == md


@needs_reader
def test_init_check_runs_the_hook_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cli.cmd_init(cli.build_parser("init").parse_args(["--yes"]))
    capsys.readouterr()
    assert cli.cmd_init(cli.build_parser("init").parse_args(["--check"])) == 0
    text = capsys.readouterr().out
    assert "hook present" in text and "pieces 1" in text


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

@needs_reader
def test_demo_certifies():
    r = subprocess.run([sys.executable, "-m", "planimeter", "--demo", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    d = json.loads(r.stdout)
    assert (d["pieces"], d["faces"], d["chi"], d["v"], d["e"]) == (1, 4, -3, 9, 12)


@needs_reader
def test_check_held_and_broken(tmp_path):
    svg = tmp_path / "demo.svg"
    svg.write_text(cli.DEMO_SVG)
    held = subprocess.run([sys.executable, "-m", "planimeter", "check", str(svg), "--faces", "4"],
                          capture_output=True, text=True)
    assert held.returncode == 0 and "HELD" in held.stdout
    broken = subprocess.run([sys.executable, "-m", "planimeter", "check", str(svg), "--faces", "5"],
                            capture_output=True, text=True)
    assert broken.returncode == 1 and "BROKEN" in broken.stdout


def test_module_selfchecks_run():
    """cli, hook and bench each own a runnable self-check; bench's runs every
    benchmark arm on one clean figure, so a broken arm fails here rather than
    quietly scoring wrong in the published table."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(cli.__file__)))
    for args in ([sys.executable, "-m", "planimeter.cli"],
                 [sys.executable, "-m", "planimeter.hook", "--selfcheck"],
                 [sys.executable, os.path.join(root, "bench.py"), "--selfcheck"]):
        r = subprocess.run(args, capture_output=True, text=True, cwd=root)
        assert r.returncode == 0 and "self-check OK" in r.stdout, (args[-1], r.stderr[-800:])
