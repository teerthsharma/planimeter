# corpus/found — real agent-written SVGs

**Empty. Every number that depends on this directory is NOT EARNED.**

This is the stratum that decides whether planimeter is worth installing, and it
is the one stratum that cannot be synthesised. A figure `corpus.py` writes is a
figure `corpus.py` already knows the answer to; the question here is what an
agent actually emits when nobody is watching, and that has to be collected.

## What goes in here

Roughly thirty `.svg` files written by agents in ordinary sessions, unedited —
no reformatting, no coordinate rounding, no removal of `<text>`.

## How truth is established

By a second method, **before** planimeter is run on the file: rasterise at
4096 px with 1-px strokes and label the connected components of the complement.
Record it in `truth.json` as

```json
{"floorplan-03.svg": {"pieces": 1, "faces": 7, "method": "raster 4096 px",
                      "date": "YYYY-MM-DD", "by": "..."}}
```

Where the raster and the arrangement disagree, **the disagreement is the
interesting row**: it is the arrangement-faces-versus-rendered-regions seam, and
publishing the count of disagreements is worth more than a clean hand-annotated
table nobody can check.

## How the rates are reported

Never as a bare percentage. Thirty files with single-source truth carry the rule
of three, broken out by refusal reason, and never summed across reader gaps and
mathematical refusals — those are two different failures with two different
fixes. The synthetic refusal rate is a property of the jitter schedule and must
never be read as this one.
