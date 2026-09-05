"""The reader: what came out of the file, and what did not.

No test here scores planimeter against planimeter. The reader's answers are
checked against the SVG grammar (a `<rect>` has four sides, a `<g transform>`
moves what it contains) and against `corpus.py`, whose truth was derived on
paper.
"""

from __future__ import annotations

import hashlib
import os

import numpy as np
import pytest

import corpus
import planimeter
from planimeter.arrange import chi_segments
from planimeter.read import (FLATTEN, SUFFIXES, Segments, bad_input, segments,
                             stable)
from planimeter.result import KIND, REASON, Chi, PlanimeterParseError, Refused

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">\n'
       '  <line id="floor" x1="0" y1="0" x2="10" y2="0"/>\n'
       '  <rect x="20" y="20" width="10" height="10"/>\n'
       '  <polyline points="0,50 10,50 10,60"/>\n'
       '  <polygon points="60,0 70,0 70,10"/>\n'
       '  <g transform="translate(200,5)"><line x1="0" y1="0" x2="1" y2="0"/></g>\n'
       '  <text x="1" y="1">not geometry</text>\n'
       '</svg>')


def test_every_shape_gives_the_number_of_sides_the_grammar_says():
    s = segments(SVG)
    # 1 line + 4 rect sides + 2 polyline + 3 polygon (Z is the third side) + 1 in g
    assert len(s) == 11, s.seg
    assert s.source_format == "svg"
    assert s.n_curves == 0 and not s.has_curves


def test_a_group_transform_moves_what_it_contains():
    s = segments(SVG)
    assert np.allclose(s.seg[-1], [[200.0, 5.0], [201.0, 5.0]])


def test_ids_name_the_element_a_refusal_will_have_to_point_at():
    s = segments(SVG)
    assert s.ids[0] == "line#floor"
    assert all("#" in i for i in s.ids)
    assert {i.split("#")[0] for i in s.ids} == {"line", "rect", "polyline", "polygon"}
    assert len(s.ids) == len(s.seg)


def test_text_is_reported_not_silently_dropped():
    s = segments(SVG)
    assert s.skipped == {"text": 1}


def test_a_shape_that_carried_no_segment_is_named_by_its_tag():
    s = segments('<svg xmlns="http://www.w3.org/2000/svg">'
                 '<line x1="5" y1="5" x2="5" y2="5"/></svg>')
    assert len(s) == 0 and s.n_degenerate == 1 and s.skipped == {"line": 1}


def test_a_path_with_no_d_is_dropped_and_counted_rather_than_killing_the_read():
    """svgelements 1.9.6 raises TypeError inside its own parser on a <path>
    carrying no `d`. Found on Plan_abbaye_corvey.svg, 1 of 96 Wikimedia Commons
    plans. Such an element has no geometry by the SVG grammar, so dropping it
    invents nothing - but it is counted, and the fallback only runs after a
    parse has already failed, so a file svgelements can read is never rewritten."""
    text = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<line x1="0" y1="0" x2="5" y2="0"/><path id="empty"/></svg>')
    s = segments(text)
    assert len(s) == 1                       # the line survived
    assert s.skipped["path-without-d"] == 1  # and the drop is on the record


def test_no_geometry_names_what_was_skipped():
    s = segments('<svg xmlns="http://www.w3.org/2000/svg">'
                 '<text x="0" y="0">a</text><text x="0" y="9">b</text></svg>')
    r = chi_segments(s)
    assert isinstance(r, Refused) and r.reason == REASON.NO_GEOMETRY
    assert r.look_at == [{"element": "text", "count": 2}]


def test_a_rectangles_closepath_is_its_fourth_side_and_survives():
    s = segments('<svg xmlns="http://www.w3.org/2000/svg">'
                 '<rect x="0" y="0" width="10" height="10"/></svg>')
    assert len(s) == 4 and s.n_degenerate == 0
    r = chi_segments(s)
    assert (r.pieces, r.faces, r.chi) == (1, 1, 0)


def test_a_circles_closepath_is_numerically_zero_and_is_dropped():
    """svgelements rebuilds a circle from four arcs and misses the start by about
    1e-15 at radius 5. Emitting that closure would put a segment a thousand times
    shorter than anything else in the file into the spectrum and refuse every
    circle; the representability floor - the package's own delta, not a new
    tolerance - is what drops it."""
    s = segments('<svg xmlns="http://www.w3.org/2000/svg"><circle cx="0" cy="0" r="5"/></svg>')
    assert len(s) == 4 * FLATTEN and s.n_degenerate == 1
    r = chi_segments(s)
    assert (r.pieces, r.faces) == (1, 1)


@pytest.mark.parametrize("n", [4, 16, 32])
def test_a_curve_flattens_into_exactly_n_pieces(n):
    s = segments('<svg xmlns="http://www.w3.org/2000/svg">'
                 '<path d="M 0 0 C 10 10 20 10 30 0"/></svg>', flatten=n)
    assert len(s) == n and s.n_curves == 1 and s.has_curves
    assert s.flatten == (n, 2 * n)


def test_the_flatten_pair_is_stamped_and_a_finer_read_is_not_called_unstable():
    circle = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="0" cy="0" r="5"/></svg>'
    v = planimeter.chi(circle)
    assert isinstance(v, Chi) and (v.pieces, v.faces, v.chi) == (1, 1, 0)
    assert v.flatten == (FLATTEN, 2 * FLATTEN)


def test_curve_unstable_is_reachable_from_a_committed_file():
    """One file, one invented number, two answers. At N the stub end sits outside
    a chord and lands in the ambiguous band; at 2N the same point is inside."""
    text = corpus.curve_unstable_svg(flatten=FLATTEN)
    coarse = chi_segments(segments(text, flatten=FLATTEN), flatten=FLATTEN)
    fine = chi_segments(segments(text, flatten=2 * FLATTEN), flatten=FLATTEN)
    assert isinstance(coarse, Refused) and isinstance(fine, Chi)
    v = planimeter.chi(text)
    assert isinstance(v, Refused) and v.reason == REASON.CURVE_UNSTABLE
    assert v.kind == KIND.GEOMETRY and "circle#dial" in str(v.look_at)
    assert "16" in v.detail and "32" in v.detail


def test_stable_compares_the_integers_and_not_v_and_e():
    """A finer flattening has more vertices and more edges by construction. A
    comparison that included them would call every curve unstable."""
    coarse = Chi(v=4, e=4, pieces=1, faces=1, chi=0, dangles=0,
                 t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.02)
    fine = Chi(v=64, e=64, pieces=1, faces=1, chi=0, dangles=0,
               t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.02)
    assert stable(coarse, fine) is coarse
    other = Chi(v=64, e=65, pieces=1, faces=2, chi=-1, dangles=0,
                t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.02)
    assert stable(coarse, other).reason == REASON.CURVE_UNSTABLE
    # two refusals for the same reason are the same verdict, not an instability
    r = Refused(REASON.EDGES_CROSS, detail="x")
    assert stable(r, Refused(REASON.EDGES_CROSS, detail="y")) is r
    assert stable(r, Refused(REASON.VERTEX_NEAR_EDGE)).reason == REASON.CURVE_UNSTABLE


def test_a_budget_refusal_at_2n_is_not_reported_as_an_unstable_curve():
    """The 2N pass has about twice the vertices by construction, so it can hit
    the vertex ceiling while the N pass produced a verdict. The two passes did
    not disagree about the drawing - the second never ran - and an agent told
    CURVE_UNSTABLE would go re-observe a curve over a machine that ran out of
    room. Found on 5 of 96 Wikimedia Commons plans, not anticipated."""
    coarse = Chi(v=9, e=12, pieces=1, faces=4, chi=-3, dangles=0,
                 t_below=1e-3, t_above=0.5, ratio=500.0, radius=0.0224)
    fine = Refused(REASON.TOO_MANY_VERTICES, detail="4100 distinct endpoints",
                   look_at=[{"element": "vertices", "count": 4100}])
    out = stable(coarse, fine)
    assert isinstance(out, Refused)
    assert out.reason == REASON.TOO_MANY_VERTICES and out.kind == KIND.BUDGET
    assert "4100" in out.detail and "faces 4" in out.detail
    # a genuine disagreement is still CURVE_UNSTABLE
    other = Refused(REASON.VERTEX_NEAR_EDGE, detail="1 vertex in the band")
    assert stable(coarse, other).reason == REASON.CURVE_UNSTABLE


def test_a_file_with_no_curves_is_read_once():
    """The second pass is what makes curves affordable to be honest about; a
    floor plan of straight walls must not pay for it."""
    calls = []
    real = planimeter.read.segments

    def counting(source, **kw):
        calls.append(kw.get("flatten"))
        return real(source, **kw)

    planimeter.read.segments = counting
    try:
        planimeter.chi(corpus.to_svg(corpus.FAMILIES["square"][0]))
    finally:
        planimeter.read.segments = real
    assert calls == [16], calls


@pytest.mark.parametrize("name", sorted(corpus.FAMILIES))
def test_every_clean_family_survives_the_round_trip_through_svg(name):
    """corpus -> SVG text -> reader -> the same integers the recipe predicted.
    This is the only test that joins the reader to a truth value."""
    seg, (v, e, c, faces, chi) = corpus.FAMILIES[name]
    r = chi_segments(segments(corpus.to_svg(seg)))
    assert isinstance(r, Chi), getattr(r, "reason", r)
    assert (r.v, r.e, r.pieces, r.faces, r.chi) == (v, e, c, faces, chi)
    assert r.n_merged == 0, "a clean file must not need a snap"


@pytest.mark.parametrize("kind", ["line", "path"])
def test_line_elements_and_path_elements_read_the_same(kind):
    seg = corpus.FAMILIES["T-junction"][0]
    r = chi_segments(segments(corpus.to_svg(seg, kind=kind)))
    assert (r.pieces, r.faces, r.n_subdivided) == (1, 2, 2)


def test_a_path_and_the_same_file_on_disk_agree(tmp_path):
    text = corpus.to_svg(corpus.FAMILIES["grid(3)"][0])
    p = tmp_path / "walls.svg"
    p.write_text(text, encoding="utf-8")
    from_text, from_path = planimeter.chi(text), planimeter.chi(p)
    assert from_text.digest == from_path.digest
    assert from_path.source == str(p) and from_text.source == "<text>"
    with open(p, "r", encoding="utf-8") as fh:
        assert np.array_equal(segments(fh).seg, segments(text).seg)


def test_reading_never_writes(tmp_path):
    p = tmp_path / "walls.svg"
    p.write_text(corpus.to_svg(corpus.FAMILIES["chain(3)"][0]), encoding="utf-8")
    before = (p.stat().st_mtime_ns, hashlib.sha1(p.read_bytes()).hexdigest())
    os.chmod(p, 0o444)
    try:
        planimeter.chi(p)
        planimeter.chi(p, flatten=8)
        segments(p)
    finally:
        os.chmod(p, 0o644)
    assert (p.stat().st_mtime_ns, hashlib.sha1(p.read_bytes()).hexdigest()) == before


@pytest.mark.parametrize("bad,exc", [
    ("<svg><line x1='0'", PlanimeterParseError),        # markup, and broken
    ("<?xml version='1.0'?><nope", PlanimeterParseError),
    (42, PlanimeterParseError),                          # not a source at all
    (None, PlanimeterParseError),
    ("no/such/file/anywhere.svg", OSError),              # a path, and not there
    ("this is not xml at all", OSError),                 # read as a path, correctly
])
def test_bad_input_raises_and_is_never_a_geometry_verdict(bad, exc):
    """Both exits are 3 and neither is a verdict: the tool never ran. OSError is
    not softened into a parse error, because "the path is wrong" and "the file is
    not SVG" send an agent to two different places."""
    with pytest.raises(exc):
        segments(bad)


def test_bad_input_becomes_a_refusal_the_cli_can_print():
    r = bad_input("nope.svg", OSError("no such file"))
    assert r.reason == REASON.BAD_INPUT and r.kind == KIND.INPUT
    assert not r and "nope.svg" in r.source
    with pytest.raises(TypeError):
        int(r)


def test_flatten_must_be_a_real_refinement():
    with pytest.raises(ValueError):
        segments(SVG, flatten=0)


def test_the_reader_record_duck_types_into_the_arrangement():
    """The contract arrange._as_segments reads: .seg plus optional .ids,
    .skipped, .source, .source_format, .flatten."""
    s = segments(SVG)
    assert isinstance(s, Segments) and isinstance(s.seg, np.ndarray)
    assert s.seg.dtype == np.float64 and s.seg.shape[1:] == (2, 2)
    assert np.asarray(s).shape == s.seg.shape
    bare = chi_segments(s.seg)
    rich = chi_segments(s)
    assert (bare.pieces, bare.faces) == (rich.pieces, rich.faces)
    assert rich.source_format == "svg" and bare.source_format == "segments"


def test_the_suffix_table_is_what_the_reader_actually_accepts():
    assert SUFFIXES == (".svg",)


def test_a_viewbox_is_a_transform_and_the_reader_honours_it():
    """A viewBox translates every coordinate by the box origin. The integers are
    the same figure's; the float64 point set is not, which is why the corpus
    writes no viewBox and why rigid-motion invariance is an empirical claim in
    this package rather than a theorem."""
    seg = corpus.FAMILIES["grid(3)"][0]
    plain = segments(corpus.to_svg(seg))
    boxed = segments(corpus.to_svg(seg, viewbox=True))
    assert not np.array_equal(plain.seg, boxed.seg)
    a, b = chi_segments(plain), chi_segments(boxed)
    assert (a.pieces, a.faces, a.chi) == (b.pieces, b.faces, b.chi)


def test_reading_is_deterministic():
    a, b = segments(SVG), segments(SVG)
    assert np.array_equal(a.seg, b.seg) and a.ids == b.ids
