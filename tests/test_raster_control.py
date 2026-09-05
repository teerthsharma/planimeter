"""THE external control: a different library, a different algorithm, a different
input representation.

`skimage.measure.euler_number` is exact and linear, so there is no speed story
here and none is told. What it needs that planimeter does not is a rasterisation
resolution, and that invented number is what these tests measure: the pair of
resolutions is the argument, not decoration.

The rasteriser under test is `bench._raster`, the same function the published
benchmark arm uses, so these tests control the benchmark row as well.
"""

import functools

import pytest

import bench
import corpus
from planimeter import chi_segments
from planimeter.result import Chi

skimage = pytest.importorskip("skimage")

# Measured, not chosen. Every other family agrees at 4096 px; this one does not,
# and it does not at 512 px either, so it is a property of the representation
# and not of the resolution. K4 drawn with the fourth vertex inside has three
# shallow junctions, and 8-connected Bresenham ink closes a background pocket at
# each of them: 5 holes counted where the arrangement has 3 bounded faces.
RASTER_DISAGREES_AT_4096 = {"planar K4"}


@functools.lru_cache(maxsize=None)
def raster(name, px):
    """One rasterisation per (figure, resolution). At 4096 px the draw pass is
    the expensive half of this file and every test below asks for the same
    pictures."""
    return bench._raster(corpus.FAMILIES[name][0], px)


@pytest.mark.parametrize("name", sorted(corpus.FAMILIES))
def test_the_raster_control_agrees_with_the_arrangement_at_4096_px(name):
    seg, truth = corpus.FAMILIES[name]
    got = raster(name, 4096)
    if name in RASTER_DISAGREES_AT_4096:
        assert got != truth[3], "the named disagreement was fixed; retire the entry"
        return
    assert got == truth[3]


@pytest.mark.parametrize("name", sorted(corpus.FAMILIES))
def test_planimeter_agrees_with_itself_on_the_same_clean_figure(name):
    """The arrangement side of the same comparison, so a raster disagreement is
    readable as a raster disagreement and not as an unspecified difference."""
    seg, truth = corpus.FAMILIES[name]
    r = chi_segments(seg)
    assert isinstance(r, Chi), getattr(r, "reason", r)
    assert (r.pieces, r.faces, r.chi) == (truth[2], truth[3], truth[4])


def test_the_raster_answer_depends_on_the_resolution():
    """The resolution is the invented number one layer down. This is the whole
    argument for the certified window, so it is asserted rather than described:
    at least one figure gets a different integer at 512 px than at 4096 px."""
    moved = [n for n in sorted(corpus.FAMILIES)
             if raster(n, 512)
             != raster(n, 4096)]
    assert moved, "no figure changed with the resolution; the argument would be dead"
    # measured: theta(4) alone, and RESULTS.md carries the count with this test
    assert moved == ["theta(4)"], moved


def test_the_disagreement_is_reported_and_not_summed_away():
    """A count of disagreements, printed. Two figures out of 44 at 512 px, one
    at 4096 px, and the tool that needs no resolution has neither."""
    n512 = sum(raster(n, 512) != corpus.FAMILIES[n][1][3]
               for n in corpus.FAMILIES)
    n4096 = sum(raster(n, 4096) != corpus.FAMILIES[n][1][3]
                for n in corpus.FAMILIES)
    assert (n512, n4096, len(corpus.FAMILIES)) == (2, 1, 44)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
