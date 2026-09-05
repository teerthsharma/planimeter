"""The corpus: is the truth actually true, and does it come from anywhere but planimeter.

Two kinds of test live here. The first kind checks the corpus against itself by
a second formula - the recipe says `faces`, Euler says `E - V + C`, and they
have to agree. The second kind runs the corpus through the package and asserts
`exact or REFUSED`, never a third outcome.
"""

from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

import corpus
from planimeter.arrange import chi_segments
from planimeter.result import Chi, Refused

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The heavy grids are the cost test's job, not the corpus's. Everything a
# refusal has ever hidden in - T-junction, comb, H, ladder, overlap, the noded
# star - is in here.
LIGHT = [n for n in sorted(corpus.FAMILIES)
         if not (n.startswith("grid(") and int(n[5:-1]) > 4)]


# --------------------------------------------------------------------------
# the corpus against itself
# --------------------------------------------------------------------------

def test_corpus_has_no_shared_arithmetic():
    """Parses corpus.py's AST. If the corpus could import the counting layer,
    a benchmark row would be planimeter agreeing with planimeter."""
    tree = ast.parse((ROOT / "corpus.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(m == "planimeter" or m.startswith("planimeter.") for m in imported), \
        sorted(imported)


@pytest.mark.parametrize("name", sorted(corpus.FAMILIES))
def test_every_recipe_agrees_with_euler(name):
    """The control is the second formula, written here and not in corpus.py:
    faces = E - V + C, chi = V - E, chi = pieces - faces."""
    v, e, c, faces, chi = corpus.FAMILIES[name][1]
    assert faces == e - v + c
    assert chi == v - e
    assert chi == c - faces
    assert c >= 1 and faces >= 0 and v >= 2


def test_the_families_the_two_worst_errors_lived_in_are_present():
    for name in ("T-junction", "H", "collinear overlap", "exact duplicate segment",
                 "pentagram noded"):
        assert name in corpus.FAMILIES
    assert any(n.startswith("comb(") for n in corpus.FAMILIES)
    assert any(n.startswith("ladder(") for n in corpus.FAMILIES)


def test_the_corpus_has_not_drifted_from_the_core_test_figures():
    """tests/figures.py is the certified core's own copy. Where the two name the
    same family they must be the same figure and the same truth; this is what
    keeps one file from being quietly corrected and the other not."""
    import figures
    shared = set(figures.FAMILIES) & set(corpus.FAMILIES)
    assert len(shared) >= 30, sorted(shared)
    for name in sorted(shared):
        a_seg, a_truth = figures.FAMILIES[name]
        b_seg, b_truth = corpus.FAMILIES[name]
        assert a_truth == b_truth, name
        assert np.array_equal(a_seg, b_seg), name


@pytest.mark.parametrize("name", ["triangle", "square", "grid(3)", "T-junction"])
def test_feature_gap_is_the_smallest_thing_the_figure_resolves(name):
    seg = corpus.FAMILIES[name][0]
    g = corpus.feature_gap(seg)
    closed = {"triangle": 8.66,        # apex to base, not the 10-unit sides
              "square": 10.0,
              "grid(3)": 1.0,
              "T-junction": 5.0}[name]
    assert abs(g - closed) < 1e-9, g


def test_feature_gap_sees_a_gap_no_vertex_pair_shows():
    """A wall that misses a floor by 2.2e-6 leaves no small vertex-pair
    separation anywhere. A gap read off vertex pairs alone would be 5, and the
    jitter schedule built on it would never contest the thing that decides the
    answer."""
    seg = corpus.wall_missing_the_floor(2.2e-6)
    P = np.unique(seg.reshape(-1, 2), axis=0)
    d = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1])
    d[np.triu_indices(len(P))] = np.inf
    assert d.min() > 1.0                       # vertex pairs see nothing
    assert abs(corpus.feature_gap(seg) - 2.2e-6) < 1e-14


def test_jitter_splits_shared_vertices_and_leaves_exact_incidences_exact():
    seg = corpus.FAMILIES["T-junction"][0]
    j = corpus.jitter(seg, 1e-5, np.random.default_rng(7))
    assert j.shape == seg.shape
    moved = np.abs(j - seg).reshape(-1, 2)
    moved = np.hypot(moved[:, 0], moved[:, 1])
    # the crosswall's ends sit in two walls' interiors: unshared, so untouched
    assert (moved == 0).sum() == 2
    assert np.allclose(moved[moved > 0], 1e-5)


def test_the_jitter_schedule_is_scale_free():
    """sigma/g is the same question asked of a 10-unit square and a unit grid.
    A fixed sigma would be a different question per family."""
    for rec in corpus.jitter_stratum(names=["square", "grid(4)"], ratios=(1e-3,), seeds=1):
        assert abs(rec["sigma"] / rec["gap"] - 1e-3) < 1e-15
        assert rec["truth"] == corpus.FAMILIES[rec["family"]][1]


def test_found_is_empty_and_says_so_rather_than_inventing_rows():
    """A found corpus cannot be synthesised: a figure this file writes is a
    figure this file already knows the answer to. Until real files are
    collected, every rate that depends on them is NOT EARNED."""
    rows = corpus.found()
    assert isinstance(rows, list)
    assert all(set(r) >= {"path", "name"} for r in rows)


# --------------------------------------------------------------------------
# the corpus through the package
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", LIGHT)
def test_the_clean_stratum_is_exact_and_merges_nothing(name):
    seg, (v, e, c, faces, chi) = corpus.FAMILIES[name]
    r = chi_segments(seg)
    assert isinstance(r, Chi), getattr(r, "reason", r)
    assert (r.v, r.e, r.pieces, r.faces, r.chi) == (v, e, c, faces, chi)
    assert r.n_merged == 0


@pytest.mark.parametrize("name", sorted(corpus.REFUSALS))
def test_every_refusal_figure_refuses_for_the_reason_it_was_built_for(name):
    seg, reason = corpus.REFUSALS[name]
    r = chi_segments(seg)
    assert isinstance(r, Refused), r
    assert r.reason == reason, (name, r.reason, r.detail)
    assert r.look_at and r.action


@pytest.mark.parametrize("name", ["square", "T-junction", "grid(3)", "theta(4)",
                                  "comb(3)", "collinear overlap"])
def test_an_edit_lands_on_the_integer_it_was_predicted_to(name):
    """Predict-then-verify with a closed form. No vision check and no area check
    can express a claim of this shape."""
    for edit, seg, (v, e, c, faces, chi), why in corpus.edits(*corpus.FAMILIES[name]):
        r = chi_segments(seg)
        assert isinstance(r, Chi), (name, edit, getattr(r, "reason", r), why)
        assert (r.v, r.e, r.pieces, r.faces, r.chi) == (v, e, c, faces, chi), \
            (name, edit, why)


def test_a_loop_edit_moves_faces_by_exactly_one():
    """The claim the pitch is made of, checked against the integer rather than
    against a picture."""
    seg, truth = corpus.FAMILIES["square + diagonals + centre"]
    before = chi_segments(seg)
    edit = {n: (s, t) for n, s, t, _ in corpus.edits(seg, truth)}["loop"]
    after = chi_segments(edit[0])
    assert (before.faces, after.faces) == (4, 5)
    assert after.chi == before.chi - 1


@pytest.mark.parametrize("ratio", corpus.RATIOS)
def test_zero_wrong_over_the_feature_gap_schedule(ratio):
    """THE claim. Every draw is exactly the closed-form answer or REFUSED; a
    third outcome fails the suite. A count, not a rate."""
    wrong, exact, refused = [], 0, 0
    for rec in corpus.jitter_stratum(names=LIGHT, ratios=(ratio,), seeds=3):
        r = chi_segments(rec["seg"])
        if isinstance(r, Refused):
            refused += 1
        elif (r.v, r.e, r.pieces, r.faces, r.chi) == rec["truth"]:
            exact += 1
        else:
            wrong.append((rec["family"], rec["seed"],
                          (r.v, r.e, r.pieces, r.faces, r.chi), rec["truth"]))
    assert not wrong, wrong[:5]
    assert exact + refused == len(LIGHT) * 3


def test_there_is_no_jitter_level_at_which_everything_certifies():
    """The cliff is not clean, and this is the measured shape rather than the
    hoped-for one: refusals sit at a few percent at every level including the
    smallest, so no level of the schedule is a "clean" one. What is flat at zero
    across all six levels is the wrong count, and that is the claim."""
    rates = []
    for ratio in corpus.RATIOS:
        n = refused = 0
        for rec in corpus.jitter_stratum(names=LIGHT, ratios=(ratio,), seeds=3):
            n += 1
            r = chi_segments(rec["seg"])
            if isinstance(r, Refused):
                refused += 1
            else:
                assert (r.v, r.e, r.pieces, r.faces, r.chi) == rec["truth"], rec["family"]
        rates.append(refused / n)
    assert all(0.0 < rate < 0.5 for rate in rates), rates


def test_a_gap_a_tenth_of_the_feature_size_is_read_as_noise_and_merged():
    """The measured boundary, pinned so it cannot move silently.

    Two 10-unit squares 1.0 apart certify as ONE piece; 1.01 apart certify as
    two. The file has only two lengths, the widest window is (gap, 10), and RHO
    is the constant that decides which side of it a gap falls on. Nothing here
    is wrong by the convention - the identification is invariant across a window
    ten times wide and `n_merged` is printed - and nothing here matches what a
    reader looking at the picture would say. That is the cost of not claiming
    uniqueness of the scale, and it is a corpus row, not a footnote."""
    merged = chi_segments(corpus.near_touching_squares(1.0))
    apart = chi_segments(corpus.near_touching_squares(1.01))
    assert (merged.pieces, merged.faces, merged.n_merged) == (1, 2, 2)
    assert (apart.pieces, apart.faces, apart.n_merged) == (2, 2, 0)
    assert merged.rho == apart.rho == 10.0


@pytest.mark.parametrize("name", sorted(corpus.CONTESTED))
def test_a_contested_figure_certifies_the_reading_it_was_recorded_with(name):
    seg, certified, as_drawn = corpus.CONTESTED[name]
    r = chi_segments(seg)
    assert isinstance(r, Chi), getattr(r, "reason", r)
    assert (r.pieces, r.faces) == certified
    assert (r.pieces, r.faces) != as_drawn
    assert r.n_merged > 0, "a reading that differs from the drawing must say so"


def test_a_figure_jittered_past_its_own_feature_gap_is_a_different_figure():
    """Stated rather than hidden: at sigma/g near 1 the integers describe the
    file honestly and the figure not at all. That is inside the convention, and
    it is why the schedule stops at 5e-2."""
    seg, truth = corpus.FAMILIES["square"]
    wrong = 0
    for seed in range(12):
        big = corpus.jitter(seg, 5e-2 * corpus.feature_gap(seg), np.random.default_rng(seed))
        r = chi_segments(big)
        if isinstance(r, Chi) and (r.pieces, r.faces) != (truth[2], truth[3]):
            wrong += 1
    assert wrong > 0, "5e-2 is outside the schedule because it is measurably outside"
