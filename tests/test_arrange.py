"""The arrangement, end to end from segments, against the closed-form table.

`chi_segments` is the entry point, so no test here is coupled to a file format
and the claim "given a correct segment set the integers are exact" is testable
with no parser in the room.
"""

import json
import math
import pathlib

import numpy as np
import pytest

from figures import FAMILIES, REFUSAL_FIGURES, S, split_shared_vertices, square
from planimeter.arrange import chi_segments, vertex_edge_spectrum
from planimeter.result import BANNED, REASON, Chi, PlanimeterParseError, Refused

NAMES = sorted(FAMILIES)
FEATURE_GAP = 10.0                       # every family's smallest deliberate feature
JITTER_LEVELS = (1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3)   # sigma / g
SEEDS = 10


@pytest.mark.parametrize("name", NAMES)
def test_closed_form_families(name):
    seg, want = FAMILIES[name]
    c = chi_segments(seg)
    assert isinstance(c, Chi), "%s refused: %r" % (name, c)
    assert (c.v, c.e, c.pieces, c.faces, c.chi) == want


@pytest.mark.parametrize("name", NAMES)
def test_clean_stratum_never_merges(name):
    """Exact, round coordinates and exact coincidences are the normal case for
    model-written geometry. Anything merged here is a bug, not a refusal."""
    c = chi_segments(FAMILIES[name][0])
    assert isinstance(c, Chi) and c.n_merged == 0 and c.diam_max == 0.0


def test_t_junction_certifies():
    """A vertex in the interior of another segment is not a proper crossing, so
    a planarity test alone passes it and the count comes out wrong. The input
    has 5 segments; subdivision at the two existing vertices makes 7 edges."""
    seg = np.concatenate([square(), S([[5, 0], [5, 10]])])
    c = chi_segments(seg)
    assert (c.pieces, c.faces, c.chi) == (1, 2, -1)
    assert (c.v, c.e, c.n_subdivided) == (6, 7, 2)


def test_overlap_and_duplicate():
    ov = chi_segments(S([[0, 0], [10, 0]], [[3, 0], [7, 0]]))
    assert (ov.v, ov.e, ov.faces, ov.chi) == (4, 3, 0, 1)
    dup = chi_segments(S([[0, 0], [10, 0]], [[0, 0], [10, 0]]))
    assert (dup.v, dup.e, dup.faces, dup.n_dup_edges) == (2, 1, 0, 1)


def test_near_touching_refuses_and_names_the_coordinate():
    """A wall whose end misses a floor by 2.2e-6 leaves no small vertex-pair
    separation behind, so a gap search over vertex pairs alone cannot see it."""
    seg = np.concatenate([square(), S([[5.0, 2.2e-06], [5.0, 10.0]])])
    r = chi_segments(seg)
    assert isinstance(r, Refused) and r.reason == REASON.VERTEX_NEAR_EDGE
    assert r.kind == "geometry"
    site = r.look_at[0]
    assert abs(site["d"] - 2.2e-06) < 1e-15
    assert abs(site["xy"][0] - 5.0) < 1e-9
    assert site["element"] and site["edge"] and r.action


def test_crossing_refuses_rather_than_inventing_the_point():
    r = chi_segments(REFUSAL_FIGURES["pentagram raw"])
    assert isinstance(r, Refused) and r.reason == REASON.EDGES_CROSS
    assert len(r.look_at) == 5
    assert "split both segments" in r.action


def test_zero_wrong_or_refuse():
    """THE LOAD-BEARING TEST. Every family, six jitter levels, ten seeds: the
    answer is exactly the closed-form integer or it is a typed refusal. One
    silent wrong integer fails the suite."""
    rng = np.random.default_rng(20260905)
    wrong, exact, refused = [], 0, 0
    for sigma_over_g in JITTER_LEVELS:
        for name in NAMES:
            seg, want = FAMILIES[name]
            for _ in range(SEEDS):
                jit = split_shared_vertices(seg, sigma_over_g * FEATURE_GAP, rng)
                c = chi_segments(jit)
                if isinstance(c, Refused):
                    refused += 1
                elif (c.v, c.e, c.pieces, c.faces, c.chi) == want:
                    exact += 1
                else:
                    wrong.append((name, sigma_over_g, (c.pieces, c.faces, c.chi), want[2:]))
    assert exact + refused + len(wrong) == len(JITTER_LEVELS) * len(NAMES) * SEEDS
    assert not wrong, wrong[:5]


def test_refusals_grow_with_the_jitter():
    """Not a clean cliff - the re-emitter can push a split corner near an edge at
    any level - but the direction is pinned, and no level produces a wrong
    integer, which is the claim that matters."""
    rng = np.random.default_rng(7)

    def refusal_rate(sigma_over_g):
        n = bad = 0
        for name in NAMES:
            seg, want = FAMILIES[name]
            for _ in range(4):
                c = chi_segments(split_shared_vertices(seg, sigma_over_g * FEATURE_GAP, rng))
                n += 1
                if isinstance(c, Refused):
                    bad += 1
                else:
                    assert (c.v, c.e, c.pieces, c.faces, c.chi) == want, name
        return bad / n

    assert refusal_rate(1e-2) > refusal_rate(1e-8)


def test_subdivision_invariance():
    """Inserting a midpoint vertex leaves the integers alone, or refuses. Not
    "always identical": a new vertex changes the spectrum and may move the
    window, and pretending otherwise would be a claim this cannot make."""
    for name in NAMES:
        seg, want = FAMILIES[name]
        a, b = seg[0][0], seg[0][1]
        mid = (a + b) / 2.0
        split = np.concatenate([np.array([[a, mid], [mid, b]]), seg[1:]])
        c = chi_segments(split)
        if isinstance(c, Chi):
            assert (c.pieces, c.faces, c.chi) == want[2:], name


def test_power_of_two_scaling_is_exact():
    """Multiplying every coordinate by 2^k is exact in binary floating point, so
    the certificate is bit-identical apart from the window endpoints, which
    scale by the same factor."""
    for name in NAMES[:12]:
        seg, want = FAMILIES[name]
        a = chi_segments(seg)
        b = chi_segments(seg * 1024.0)
        assert isinstance(a, Chi) and isinstance(b, Chi), name
        assert (a.v, a.e, a.pieces, a.faces, a.chi) == (b.v, b.e, b.pieces, b.faces, b.chi)
        assert b.t_above == a.t_above * 1024.0
        assert b.t_below == a.t_below * 1024.0


def test_rigid_motion_invariance_is_empirical_and_labelled_so():
    """Rotation and arbitrary scaling: identical integers or REFUSED, never a
    different integer. Empirical, over published seeds - a rotation is not exact
    in float64 and no theorem is claimed."""
    rng = np.random.default_rng(99)
    checked = 0
    for name in NAMES:
        seg, want = FAMILIES[name]
        for _ in range(3):
            th = rng.uniform(0, 2 * math.pi)
            s = float(rng.uniform(0.3, 3.0))
            R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]]) * s
            c = chi_segments(seg @ R.T)
            if isinstance(c, Chi):
                assert (c.pieces, c.faces, c.chi) == want[2:], (name, th, s)
                checked += 1
    assert checked > 50


def test_disjoint_union_is_additive():
    a_seg, a = FAMILIES["square"]
    b_seg, b = FAMILIES["T-junction"]
    both = chi_segments(np.concatenate([a_seg, b_seg + np.array([1000.0, 0.0])]))
    assert both.pieces == a[2] + b[2]
    assert both.faces == a[3] + b[3]
    assert both.chi == a[4] + b[4]


def test_chord_and_bridge_in_the_arrangement():
    """The graph-level identity, re-run where the edge has to survive the
    arrangement: a chord adds a face, a bridge joins two pieces."""
    base = chi_segments(np.concatenate([square(), square(100.0, 0.0)]))
    bridge = chi_segments(np.concatenate([square(), square(100.0, 0.0),
                                          S([[10, 0], [100, 0]])]))
    assert (bridge.pieces, bridge.faces, bridge.chi) == (base.pieces - 1, base.faces,
                                                         base.chi - 1)
    chord = chi_segments(np.concatenate([square(), S([[0, 0], [10, 10]])]))
    assert (chord.pieces, chord.faces, chord.chi) == (1, 2, -1)


def test_refused_is_falsy_and_will_not_become_an_integer():
    r = chi_segments(REFUSAL_FIGURES["pentagram raw"])
    assert bool(r) is False
    with pytest.raises(TypeError) as exc:
        int(r)
    assert REASON.EDGES_CROSS in str(exc.value)


def test_no_geometry_names_what_was_skipped():
    r = chi_segments(np.zeros((0, 2, 2)))
    assert isinstance(r, Refused) and r.reason == REASON.NO_GEOMETRY
    assert r.kind == "geometry"


@pytest.mark.parametrize("bad,match", [
    (np.zeros((5, 2)), "shape"),                        # missing the endpoint axis
    (np.zeros((5, 4)), "shape"),                        # 4 numbers, not 2 points
    (np.zeros((5, 2, 3)), "shape"),                     # 3 numbers per point, not 2
    ([["a", "b"], ["c", "d"]], "float64"),              # wrong dtype: not numeric at all
    ({"not": "a segment array"}, "float64"),            # not array-like at all
])
def test_a_malformed_segment_array_is_this_packages_own_typed_error(bad, match):
    """A caller of the array API - not the CLI, which only ever hands `chi_segments`
    a reader's own validated Segments - can pass anything. The wrong shape or a
    non-numeric dtype must come back as `PlanimeterParseError`, never a bare
    numpy `ValueError` two frames down inside `np.asarray`."""
    with pytest.raises(PlanimeterParseError, match=match):
        chi_segments(bad)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_coordinates_are_refused_by_type_not_by_warning(bad_value):
    """NaN/Inf used to reach the vertex-edge distance math unfiltered, printing a
    numpy RuntimeWarning and returning a confusing NO_STABLE_SCALE ("0
    separations"). It must instead be this package's own typed, actionable
    error, and it must not print anything to warn about."""
    import warnings
    seg = np.array([[[0.0, 0.0], [bad_value, 1.0]]])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(PlanimeterParseError, match="finite"):
            chi_segments(seg)
    assert not caught, "non-finite input must not raise a numpy warning: %r" % caught


def test_edge_collapsed_is_reachable_and_falls_through():
    """A user radius above a real segment's length swallows it. The refusal
    names the element and its length."""
    seg = np.concatenate([square(), S([[5.0, 5.0], [5.0001, 5.0]])])
    r = chi_segments(seg, grid=0.01)
    assert isinstance(r, Refused) and r.reason == REASON.EDGE_COLLAPSED
    assert r.look_at[0]["element"] and r.look_at[0]["length"] < 0.01


def test_margin_too_small_is_reachable():
    seg = S([[1e17, 0.0], [1e17 + 1.0, 0.0]], [[1e17 + 2.0, 0.0], [1e17 + 3.0, 0.0]])
    r = chi_segments(seg)
    assert isinstance(r, Refused)
    assert r.reason in (REASON.MARGIN_TOO_SMALL, REASON.NO_STABLE_SCALE)


def test_a_finite_but_extreme_coordinate_refuses_quietly():
    """1e308 squared overflows float64 inside an intermediate squared-length,
    so a legitimately finite coordinate near the top of float64's range used to
    print a numpy RuntimeWarning on its way to a refusal. The refusal is fine -
    this drawing's own scale is unusable - the warning was noise from computing
    it, and chi_segments now silences that noise rather than passing it through
    to the caller's stderr."""
    import warnings
    seg = S([[0.0, 0.0], [1e308, 1e308]], [[0.0, 0.0], [10.0, 0.0]])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        r = chi_segments(seg)
    assert isinstance(r, Refused)
    assert not caught, "an extreme-but-finite coordinate must not warn: %r" % caught


def test_too_many_vertices_is_a_budget_refusal_not_a_geometry_one():
    from planimeter import arrange
    old = arrange.VE_BUDGET
    arrange.VE_BUDGET = 4
    try:
        r = chi_segments(square())
        assert isinstance(r, Refused) and r.reason == REASON.TOO_MANY_VERTICES
        assert r.kind == "budget"
    finally:
        arrange.VE_BUDGET = old


def test_the_vertex_ceiling_is_a_default_a_caller_can_spend_past():
    """grid(46) is 2,209 vertices: above BRUTE_MAX, so the default refuses. The
    truth it must produce once the ceiling is raised is closed-form (k*k faces,
    one piece), so this is not planimeter scored against planimeter."""
    from corpus import grid
    seg = grid(46)
    r = chi_segments(seg)
    assert isinstance(r, Refused) and r.reason == REASON.TOO_MANY_VERTICES
    assert r.kind == "budget"
    assert "--max-vertices" in r.action           # the flag named exists
    ok = chi_segments(seg, max_vertices=3000)
    assert isinstance(ok, Chi), getattr(ok, "detail", ok)
    assert (ok.pieces, ok.faces, ok.chi) == (1, 46 * 46, 1 - 46 * 46)


def test_one_flag_moves_both_ceilings():
    """The pair budget is the vertex ceiling squared, times four. A raised vertex
    ceiling that left the pair budget at 16,000,000 would refuse TOO_MANY_PAIRS
    three passes later, which is the same ceiling wearing a different name."""
    from planimeter.arrange import VE_BUDGET, pair_budget
    from planimeter.snap import BRUTE_MAX
    assert pair_budget(None) == VE_BUDGET == 4 * BRUTE_MAX ** 2
    assert pair_budget(3000) == 36_000_000


def test_the_vertex_ceiling_is_checked_before_the_quadratic_pass():
    """The cheap guard runs first: a set above the ceiling must not pay for the
    vertex-edge spectrum before being refused. Measured by making that pass
    raise if it is ever entered."""
    from planimeter import arrange
    from corpus import grid
    real = arrange.vertex_edge_spectrum

    def boom(*a, **kw):
        raise AssertionError("the quadratic pass ran on a file above the ceiling")

    arrange.vertex_edge_spectrum = boom
    try:
        r = chi_segments(grid(46))
    finally:
        arrange.vertex_edge_spectrum = real
    assert isinstance(r, Refused) and r.reason == REASON.TOO_MANY_VERTICES


def test_user_grid_keeps_the_certificate_and_says_who_chose_it():
    seg = np.concatenate([square(), S([[0, 0], [10, 10]])])
    a = chi_segments(seg)
    b = chi_segments(seg, grid=1e-6)
    assert a.grid_source == "derived" and b.grid_source == "user"
    assert (a.pieces, a.faces) == (b.pieces, b.faces)


def test_vertex_edge_spectrum_excludes_incident_pairs():
    seg = S([[0, 0], [10, 0]], [[0, 5], [10, 5]])
    pts = np.array([[0., 0.], [10., 0.], [0., 5.], [10., 5.]])
    ends = np.array([[0, 1], [2, 3]])
    d = vertex_edge_spectrum(pts, ends)
    assert len(d) == 4                       # 2 segments x 4 vertices - 4 incident
    assert np.allclose(np.sort(d), [5.0, 5.0, 5.0, 5.0])


def test_digest_identifies_the_arrangement():
    seg, _ = FAMILIES["T-junction"]
    a = chi_segments(seg)
    b = chi_segments(seg[::-1])              # same arrangement, segments reordered
    c = chi_segments(FAMILIES["square"][0])
    assert a.digest == b.digest
    assert a.digest != c.digest
    assert len(a.digest) == 40


def test_json_round_trip_rebuilds_the_verdict():
    c = chi_segments(FAMILIES["grid(3)"][0])
    d = json.loads(json.dumps(c.json()))
    assert Chi.from_json(d) == c
    r = chi_segments(REFUSAL_FIGURES["pentagram raw"])
    assert Refused.from_json(json.loads(json.dumps(r.json()))) == r


def test_json_round_trip_catches_a_broken_identity():
    """The one place the identity is not a tautology: the four fields arrive
    independently, so a hand-edited payload is rejected rather than trusted."""
    d = chi_segments(FAMILIES["square"][0]).json()
    d["faces"] += 1
    with pytest.raises(ValueError):
        Chi.from_json(d)


def test_no_banned_phrase_in_source_or_verdict():
    """Source grep, scoped and stated: a word list is a guard, not a proof. The
    package never says a drawing is closed, sound, or fixed, and never reports
    an area or a length of the drawing."""
    root = pathlib.Path(__file__).resolve().parent.parent / "planimeter"
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for phrase in BANNED:
            if path.name == "result.py" and phrase in _banned_literal_lines(path):
                continue
            assert phrase not in text, "%s in %s" % (phrase, path.name)
    for name in NAMES[:8]:
        block = chi_segments(FAMILIES[name][0]).block().lower()
        assert not any(p in block for p in BANNED)
    r = chi_segments(REFUSAL_FIGURES["pentagram raw"]).block().lower()
    assert not any(p in r for p in BANNED)


def _banned_literal_lines(path):
    text = path.read_text(encoding="utf-8")
    start = text.index("BANNED = (")
    return text[start:text.index(")", start)].lower()


def test_never_writes_to_the_input():
    """The guarantee that makes a write-triggered hook installable gets a test,
    not a sentence."""
    seg = FAMILIES["T-junction"][0]
    before = seg.copy()
    chi_segments(seg)
    assert np.array_equal(seg, before)
    root = pathlib.Path(__file__).resolve().parent.parent / "planimeter"
    stamps = {p: p.stat().st_mtime_ns for p in root.glob("*.py")}
    for name in NAMES[:5]:
        chi_segments(FAMILIES[name][0])
    assert {p: p.stat().st_mtime_ns for p in root.glob("*.py")} == stamps


def _in_subprocess(lines):
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-c", "\n".join(lines)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_no_geos_in_the_certified_core():
    """The one thing GEOS was wanted for - an exact Euclidean MST through the
    Delaunay triangulation - was measured and does not hold on near-degenerate
    point sets, which is exactly what a jittered drawing is. Nothing on the
    counting path imports it now, and this is a test of that claim rather than a
    comment about it."""
    assert _in_subprocess([
        "import sys, numpy as np, planimeter",
        "from planimeter.arrange import chi_segments",
        "seg = np.array([[[0,0],[10,0]],[[10,0],[10,10]],[[10,10],[0,10]],"
        "[[0,10],[0,0]],[[5,0],[5,10]]], dtype=float)",
        "c = chi_segments(seg)",
        "assert (c.pieces, c.faces) == (1, 2), c",
        "bad = [m for m in ('shapely', 'scipy') if m in sys.modules]",
        "assert not bad, bad",
        "print('clean')",
    ]) == "clean"


def test_import_planimeter_costs_nothing():
    """PEP 562: naming the package must not drag numpy in, because the hook has
    to decide a file is not geometry before anything is loaded."""
    assert _in_subprocess([
        "import sys, planimeter",
        "assert planimeter.__version__",
        "bad = [m for m in ('numpy', 'planimeter.snap', 'planimeter.arrange')"
        " if m in sys.modules]",
        "assert not bad, bad",
        "print('lazy')",
    ]) == "lazy"
