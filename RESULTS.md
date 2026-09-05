# RESULTS

Every number below was produced by a command in this repository on one machine, and
every number sits next to the control it was compared against. Arms that could not be
run are printed as NOT RUN with the reason, never omitted. Three of the seven gates
did not clear and they are reported in the same voice as the ones that did.

**Machine of record.**

```
commit    5713012            the last commit that changed code, working tree clean
machine   WIN-16QAL06O9GB    Windows 11, python 3.11.9
runtime   numpy 2.4.6   svgelements 1.9.6
opponents shapely 2.1.2 / GEOS 3.13.1   scikit-image 0.26.0   networkx 3.6.1   tiktoken 0.14.0
```

The opponents are all in the `[test]` extra; none of them is a runtime dependency.
`bench.py` prints whatever `HEAD` is when it runs, so the hash it stamps on its footer is
the commit that produced the numbers and not the commit that records them — the
documentation commit that follows moves `HEAD` without moving a number.

```
python -m venv .venv
.venv/Scripts/pip install -e ".[test]"
.venv/Scripts/python -m pytest -q         # 500 passed at 6d63c43
.venv/Scripts/python bench.py             # sections 1-8, 61.3 s
.venv/Scripts/python realdata.py fetch    # 61 MB, not committed; section 11
.venv/Scripts/python realdata.py run      # section 11
```

The suite was 479 at `4730829`, the commit that recorded section 11, and is **500 at `6d63c43`**.
The difference is `2db2d8c`, which added ten crash-path tests that collect as twenty-one under
parametrisation. No test was removed and no number in sections 1 through 11 moved.

Sections 1 through 10 are `bench.py`; section 11 is `realdata.py` and runs on files this
repository did not write. `bench.py` is the run of record for the first ten and stamps its
own commit; section 11 stamps the commit it was run at in its own header.

The footer of that run reads `commit 5713012  machine WIN-16QAL06O9GB  python 3.11.9
PYTHONHASHSEED=0  61.3 s`. Sections 1, 2 and 3 are bit-identical across every run on this
machine; sections 5 and 6 are wall clock and carry their own spread.

---

## 1. G2 — wrong integers on the jitter stratum

**Question.** On files where near-coincident vertices decide the answer, how often does
each tool return an integer that is silently wrong?

**Stratum.** 44 figure families x 6 levels of `sigma/g` in `1e-7 .. 1e-2` x 2 seeds =
528 draws. Truth comes from each family's construction recipe, derived on paper; a test
(`test_corpus_has_no_shared_arithmetic`) parses `corpus.py`'s AST and asserts it imports
nothing from `planimeter.count`, `.snap` or `.arrange`, so the corpus cannot borrow the
package's arithmetic. `sigma` is a fraction of each figure's own feature gap, so the
same level asks the same question of a 10-unit square and a 12x12 grid.

**Command.** `.venv/Scripts/python bench.py`

```
    planimeter                                    0 wrong   495 exact    33 refused  / 528
    round-to-6-decimals dict snap  STRAWMAN     350 wrong   178 exact     0 refused  / 528
                                              first wrong: T-junction  sigma/g 1e-07  seed 0  truth 2  got 1
    networkx b1 after a round-6 snap            350 wrong   178 exact     0 refused  / 528
                                              first wrong: T-junction  sigma/g 1e-07  seed 0  truth 2  got 1
    shapely polygonize_full(unary_union)        336 wrong   192 exact     0 refused  / 528
                                              first wrong: T-junction  sigma/g 1e-07  seed 0  truth 2  got 0
    shapely set_precision(1e-6) + the above     299 wrong   229 exact     0 refused  / 528
                                              first wrong: T-junction  sigma/g 1e-06  seed 0  truth 2  got 1
    skimage.euler_number @  512 px                2 wrong    64 exact     0 refused  / 66  (stride 8)
                                              first wrong: planar K4  sigma/g 1e-05  seed 0  truth 3  got 5
    skimage.euler_number @ 4096 px                7 wrong    59 exact     0 refused  / 66  (stride 8)
                                              first wrong: chain(2)  sigma/g 0.001  seed 0  truth 2  got 0
    CONTROL refuse-on-anything                    0 wrong     0 exact   528 refused  / 528
    CONTROL polygonize @ planimeter's radius     22 wrong   473 exact    33 refused  / 528
                                              first wrong: chain(3)  sigma/g 0.001  seed 1  truth 3  got 0
```

**G2 threshold: any nonzero wrong count blocks the release. Measured 0. HOLDS.**

### What each row is, and what it is not

- **The strawman row is labelled STRAWMAN in the benchmark's own output** because it is.
  A hand-written round-to-six-decimals snap is the comparison the prototype used, and it
  is not the baseline the headline may be quoted against. See §9.
- **`networkx`** computes `E - V + C` on the same snapped graph and gets the same 350.
  That is the point: the counting layer is not the contribution, and an opponent that
  reimplements `count.py` exactly says so louder than a paragraph.
- **`polygonize_full` reports dangles and names the unclosed edges.** The claim that it
  offers no diagnostic is false and was cut before the first line of code. What it does
  not report is which identification produced the count.
- **The two raster rows are reported as a pair and the pair is the argument.** They ran
  on every 8th draw (stride 8, 66 of 528) because a 4096-px rasterisation of 528 figures
  is the slowest arm in the file. `euler_number` is exact and linear, so there is no
  speed story here and none is told; what it needs and planimeter does not is a
  resolution, and the answer moves with it. The 4096-px arm is **worse** than the 512-px
  arm, 7 wrong against 2.
- **`refuse-on-anything` is the control that makes the accuracy row readable.** A tool
  that refuses everything scores zero wrong. planimeter's 0 is only worth reading beside
  its 495 exact.

### The oracle control, which was built to kill the counter and did not

**CONTROL polygonize @ planimeter's radius: 22 wrong / 528.** `shapely.set_precision`
handed planimeter's own certified snap radius, then `unary_union` then `polygonize_full`.
If this had scored zero, the entire contribution would have been the scale and the
refusal, and the counter would contribute nothing. It scored 22, so the counting layer
earns its place — and the 22 are `chain(k)` and similar figures where the shared-edge
structure survives snapping but not GEOS's noding.

This was the sharpest control in the design and it came back in the tool's favour. It is
one machine and one stratum.

---

## 2. Refusals by jitter level, and the cliff that is not there

**Command.** `.venv/Scripts/python bench.py`

```
    sigma/g       wrong    exact  refused
    1e-07             0       82        6
    1e-06             0       84        4
    1e-05             0       84        4
    0.0001            0       78       10
    0.001             0       85        3
    0.01              0       82        6
```

There is **no level at which everything certifies**, including the smallest. Refusals sit
between 3 and 10 of 88 at every level and do not order monotonically with the jitter. The
cliff shape the design asked for — certify-everything, then refuse-everything, with no
wrong integer in between — **is NOT EARNED**, and the test the design named for it was
never written, because there is nothing to pin. What is flat at zero across all six levels
is the wrong count, and that is the claim the tests pin
(`test_zero_wrong_or_refuse`, `test_there_is_no_jitter_level_at_which_everything_certifies`).

**The schedule's ceiling is measured, not chosen.** Extending the sweep one step to
`sigma/g = 5e-2` (44 families x 3 seeds = 132 draws) gives **4 wrong, 47 exact and 81
refused**, because a triangle whose corners sit a twentieth of its own size apart is
honestly three disjoint segments. `corpus.RATIOS` therefore stops at `1e-2`, and
`test_a_figure_jittered_past_its_own_feature_gap_is_a_different_figure` asserts that 5e-2
is outside the schedule *because it is measurably outside*, not by preference.

**Command.** The row above is one sweep past the published schedule, so it is not in
`bench.py`; this reproduces it in about a minute.

```
.venv/Scripts/python -c "import corpus; from planimeter import chi_segments; from planimeter.result import Chi; w=e=r=0
for d in corpus.jitter_stratum(ratios=(5e-2,), seeds=3):
    c = chi_segments(d['seg'])
    if not isinstance(c, Chi): r += 1
    elif (c.pieces, c.faces) == (d['truth'][2], d['truth'][3]): e += 1
    else: w += 1
print('wrong', w, 'exact', e, 'refused', r)"

wrong 4 exact 47 refused 81
```

---

## 3. RHO sensitivity — the one free constant

`RHO = 10` is the minimum window ratio a candidate must have. It is a policy, not a
theorem, and it is printed on every answer.

**Command.** `.venv/Scripts/python bench.py`

```
    rho         wrong    exact  refused   of which
    3               0      495       33
    10              0      495       33
    100             3      444       81 3 merged nothing
      T-junction                   sigma/g 0.01     truth 2  certified 0  merged 0
      chain(2)                     sigma/g 0.01     truth 2  certified 0  merged 0
      triangle                     sigma/g 0.01     truth 1  certified 0  merged 0
```

**Raising `rho` does not make the tool stricter.** It removes the genuine merge window —
whose ratio is bounded by the drawing — and leaves the merge-nothing window, whose ratio
is drawing-scale over machine epsilon for arithmetic reasons alone. The three wrong rows
at `rho = 100` are that window certifying the *file*: a jittered triangle read as three
disjoint segments. That reading is inside the stated convention and outside what a reader
would say.

**Zero-wrong is a claim about `rho <= 10`, and this table is why.** `bench.py` prints that
paragraph under the table on every run so the caveat cannot be separated from the number.

---

## 4. The independent control — a different library, a different representation

`skimage.measure.euler_number` on a rasterised stroke image. Different library, different
algorithm, different input representation, and it needs a number planimeter does not.

**Command.** `.venv/Scripts/python -m pytest tests/test_raster_control.py -q` — 90 passed.

| resolution | figures disagreeing with the arrangement | of |
|---|---|---|
| 512 px | 2 | 44 |
| 4096 px | 1 | 44 |
| planimeter | 0 | 44 |

- At 4096 px the single disagreement is **planar K4**, and it disagrees at 512 px too, so
  it is a property of the representation and not of the resolution: K4 drawn with the
  fourth vertex inside has three shallow junctions, and 8-connected Bresenham ink closes a
  background pocket at each. The raster counts 5 holes where the arrangement has 3 bounded
  faces.
- At 512 px **theta(4)** additionally disagrees, and it agrees again at 4096 px.
  `test_the_raster_answer_depends_on_the_resolution` asserts that at least one figure moves
  between the two resolutions, and pins the list to `["theta(4)"]`. If that assertion ever
  becomes false, the argument for the certified window loses its cleanest evidence, and the
  test failing is how that gets noticed.

---

## 5. G3 — cost, and it loses

**Question.** Does the certificate scale to a real floor plan?

**Command.** `.venv/Scripts/python bench.py` (grid(k) end to end, best of 3)

```
         k     segs    verts   spectrum     window      total
         4       40       25        0.1        0.2        0.7
         8      144       81        0.4        0.6        2.9
        12      312      169        2.2        1.4       14.6
        16      544      289        7.9        3.7       43.3
        20      840      441       19.8        7.8       97.2
        24     1200      625       37.8       12.5      208.5
        28     1624      841       74.4       29.5      375.5
        32     2112     1089      126.3       39.7      631.7
        36     2664     1369      201.9       65.2      994.1
        40     3280     1681      289.5       97.7     1411.2
        43     3784     1936      400.3      139.4     1880.1
```

```
    fitted log-log exponent 1.83  (kills above 1.3)
    extrapolated to n = 1e5: 740531 ms  (kills above 50 ms)
```

**G3 thresholds: exponent > 1.3, or > 50 ms at n = 1e5. Both blown, by orders of
magnitude. NOT EARNED.**

> **"Usable as a hook on a real floor plan" is withdrawn, not softened.**

The comfortable hook range is under roughly 600 segments: 43 ms at 544, 97 ms at 840,
1.9 s at 3,784. A hard ceiling of `BRUTE_MAX = 2000` vertices refuses `TOO_MANY_VERTICES`
above it rather than stalling a turn.

The cost is the all-pairs vertex-to-edge pass the certificate quantifies over. That pass
is not an implementation detail that a k-d tree removes: the certificate's precondition is
a statement about *every* (vertex, non-incident edge) pair, and a nearest-neighbour
structure answers a different question. The exponent has been measured five times on
this machine — 1.825 over 11 points to k=43 in the run of record (`1.83` in the table
above is `bench.py`'s two-decimal format for the same number), then 1.84 and 1.88 over
the same 11 points on repeat runs, 1.87 on an earlier run, and 2.2 over a shorter range
during the core build. All five are far above the gate; the gate result does not depend
on which is right.

---

## 6. G7 — hook wall clock, with a floor control

**Command.** `.venv/Scripts/python bench.py` (20 cold subprocesses per row, Windows)

```
    FLOOR bare interpreter, no hook at all        52.4 ms median  [48.0, 70.8]
    silent path (.py write)                       56.4 ms median  [46.7, 62.9]  holds
    CONTROL same hook, suffix check removed      154.0 ms median  [138.9, 163.4]
    geometry path (.svg write)                   158.6 ms median  [145.0, 168.7]  holds
```

**G7 thresholds: 60 ms silent, 250 ms geometry. Both hold on the run of record, and the
silent one does not hold on every run.**

**The floor control is what makes these numbers readable, and it was added after the
threshold was committed.** `python -c pass` costs 52.4 ms on this machine, and the silent
path costs **4.0 ms more** — that is the whole cost of `planimeter.hook`'s module-scope
imports plus the suffix check. The 60 ms gate is therefore measuring Windows process
startup with 8 ms of headroom, not planimeter, and on a machine whose Python starts slower
it will fire for reasons that have nothing to do with this package.

**That difference is itself two noisy medians subtracted, and it is reported as a range,
not as a number.** Across the seven runs that recorded the floor row it measured 9.0, 2.0,
2.4, 4.7, 14.6, 4.0 and 4.0 ms — median 4.0, spread 2.0 to 14.6, on medians whose own
ranges overlap almost completely. **Any single-run figure for this difference, including
the 4.0 ms in the run of record, is not a property of the package**; what the seven runs
support is *under about 15 ms*, and that is the claim.

**Nor is the gate itself stable.** Across eleven runs of `bench.py` on this machine the
silent path measured 52.5, 63.3, 54.8, 60.5, 55.7, 53.4, 56.9, 59.0, 70.3, 57.7 and
56.4 ms; three of the eleven exceeded the 60 ms gate and were printed as `KILLS`. The gate
is reported as it stands — the threshold has not been moved, and no run was discarded for
failing it — and the floor row is published beside it so a reader can see what the number
is made of. **On this evidence the silent-path gate is not a property of the package
either: it is a coin flip on process startup.**

The suffix check is worth 97.6 ms on every non-geometry write in the run of record (154.0
against 56.4), and 84 to 105 ms across the seven runs. That is the difference between a
hook that can be left installed and one that cannot, and unlike the 4.0 ms it is far larger
than the spread it is measured against.

**The stamp.**

```
planimeter demo.svg  pieces 1  faces 4
```

7 `cl100k_base` tokens for the body, 5 more for the path prefix.

---

## 7. Correctness measurements inside the package

Each of these was made against an independent implementation, not against planimeter.

| measurement | result | control |
|---|---|---|
| Exact EMST (vectorised Prim) | agreement to 1e-12 relative on 500 point sets across general / collinear / duplicate-heavy / near-degenerate strata | a scalar Prim written longhand (`test_emst_matches_bruteforce`) |
| The certified window's partition | identical on 200 point sets | an explicit all-pairs single-linkage cut (`test_snap_matches_all_pairs_single_linkage`) |
| Window invariance | the partition is constant across `[t_below, t_above)` and the minimum inter-cluster distance is exactly `t_above` | Kruskal's cut property, checked numerically (`test_window_invariance`, `test_minimum_inter_cluster_distance_is_exactly_t_above`) |
| 44 closed-form families, clean stratum | 44/44 exact, `n_merged == 0` on every one | each recipe's `faces` re-derived independently as `E - V + C` in the test file (`test_every_recipe_agrees_with_euler`) |
| SVG round trip | 44/44 families survive corpus → SVG text → reader → the same integers, bitwise | `test_every_clean_family_survives_the_round_trip_through_svg` |
| Scaling by `2^k` | bit-identical certificate | a theorem in binary floating point, stated separately from the empirical claim |
| Rigid motion | identical integers or REFUSED, never a different integer | empirical, and labelled empirical in the test name |
| Predict-then-verify closed form | a loop edit moves `faces` by exactly 1 and `chi` by exactly -1 | `test_a_loop_edit_moves_faces_by_exactly_one`, the `4 -> 5` claim in its arrangement version |
| The corpus is reproducible | the same draws under `PYTHONHASHSEED=0` and `PYTHONHASHSEED=12345`, compared bitwise | two subprocesses (`test_the_jitter_stratum_is_the_same_draws_in_every_interpreter`) |
| No GEOS on the counting path | neither `shapely` nor `scipy` appears in `sys.modules` after a certified count | a subprocess assertion (`test_no_geos_in_the_certified_core`) |
| planimeter never writes | every mtime and digest unchanged across the whole corpus through CLI and hook | `test_never_writes_to_the_input`, `test_hook_never_writes_to_the_geometry_file` |

### The dependency the design specified and the measurement removed

The design called for `shapely.delaunay_triangles(only_edges=True)` plus Kruskal, on the
theorem that the Euclidean MST is a subgraph of the Delaunay triangulation.

**Command.** `.venv/Scripts/python -m pytest tests/test_geos_delaunay_control.py -q -s` — 2 passed.

```
  point sets where the true EMST is NOT a subgraph of GEOS delaunay_triangles:
    1 of 793;  worst spanning-tree weight excess 0.2566
    clustered    1 / 200
    collinear    0 / 200
    duplicated   0 / 193
    general      0 / 200
    shapely 2.1.2 GEOS 3.13.1
```

The test asserts the shape — at least one failure, every one of them clustered — and not
the exact count, because the count is GEOS's and moves with its version. The figures above
are this machine's, at the GEOS in the block at the top of this file. The second test in
that file is the control for the replacement: the exact vectorised Prim returns an `n-1`
edge spanning tree on every one of the same strata.

One failure in 793, entirely inside the **clustered** stratum — which is exactly the
stratum this tool exists for. The returned edge set omitted a true MST edge, giving a
spanning tree 25.7% heavier and therefore a different merge spectrum. Replaced with an
exact vectorised `O(n^2)` Prim. shapely and GEOS left the hard dependencies with it, and
the `STRtree` queries went too. `numpy` and `svgelements` are the only runtime
dependencies, and "no GEOS-invented tolerance" is now literally true rather than
rhetorically true.

### Two reader findings, measured

- **svgelements rebuilds a circle from four arcs and closes it 1.2e-15 short of the start
  at radius 5**, so `Z` arrives as a real edge a thousand times shorter than anything else
  in the file. Emitted verbatim it poisons the merge spectrum and every circle refuses. A
  `Z` whose two ends are closer than the package's own representability floor
  (`FLOOR_ULPS` ulps of the drawing's magnitude, the constant that already anchors the
  spectrum) is dropped and counted in `n_degenerate`. This is not a new tolerance and it is
  deliberately scoped to `Z`: a rectangle's `Z` is its fourth side, orders of magnitude
  above the floor, and survives (`test_a_rectangles_closepath_is_its_fourth_side_and_survives`,
  `test_a_circles_closepath_is_numerically_zero_and_is_dropped`).
- **The corpus writes no `viewBox`, and that is load-bearing.** A `viewBox` is a viewport
  transform; the reader honours it and translates every coordinate by the box origin. On
  the noded pentagram that rigid motion moved a vertex into the ambiguous band and turned
  CERTIFIED into `VERTEX_NEAR_EDGE`. Emitting a `viewBox` would have made the corpus measure
  the writer. `to_svg(viewbox=True)` keeps the behaviour reachable and
  `test_a_viewbox_is_a_transform_and_the_reader_honours_it` pins that the integers survive
  it on `grid(3)`. This is a concrete instance of why rigid-motion invariance is empirical
  and not a theorem.

---

## 8. The contested row — a clean file where the reading is arguable

Two 10-unit squares **1.00 apart** certify as **one piece** (`n_merged 2`). The same two
squares **1.01 apart** certify as **two** (`n_merged 0`).

**Command.** `.venv/Scripts/python -m pytest tests/test_corpus.py -k gap_a_tenth -q`

The boundary is exactly `gap = feature / RHO`. The file has only two lengths, so the widest
window is `(gap, 10)` with ratio 10; merge-nothing is offered last; the merging reading
wins. This fires **with no jitter at all**, on two squares a tenth of their own size apart.
It is inside the letter of the convention — the design declines to claim uniqueness of the
scale — and outside what any reader looking at the picture would say.

It is recorded in `corpus.CONTESTED`, pinned by
`test_a_gap_a_tenth_of_the_feature_size_is_read_as_noise_and_merged`, and it sits here next
to the accuracy row rather than in a footnote.

---

## 9. NOT EARNED and NOT RUN

`bench.py` prints this list on every run rather than skipping the arms silently.

```
    G1 agent samples                               baselines/agent_samples/ does not exist
    G5 found-corpus refusal histogram              corpus/found/ holds no SVGs (see corpus/found/README.md)
    G6 certified scale vs round-6 on real files    corpus/found/ holds no SVGs (see corpus/found/README.md)
    G4 vision comparison                           CUT: it read coordinate text, not a render
```

- **G1, and it is the load-bearing gate.** The accuracy headline compares against a
  hand-written round-6 script. The baseline that matters is the code an agent actually
  writes unprompted on a first attempt, sampled at least twenty times with the whole
  distribution published. `baselines/agent_samples/` is empty, so **the strawman row in §1
  is not the baseline the headline may be quoted against**, and the benchmark says so in
  its own output. If the sampled median clears roughly 20 of 24 on this stratum, the
  accuracy headline is dead and what remains is the printed scale and the hook slot. That
  outcome would be published, not hidden.
- **G5 and G6 are half answered, by §11, and the half that is missing is the one that was
  specified.** `corpus/found/` still holds no SVGs — its specification is thirty real
  *agent-written* files with truth established by a second method *before* planimeter runs,
  and `bench.py` still reads that emptiness off the filesystem rather than asserting it.
  What §11 supplies instead is 13,777 real files nobody here drew, from npm and Wikimedia
  Commons, with **no truth at all**: a refusal histogram by reason code (G5's deliverable,
  on the wrong corpus) and a measurement of how often the certified radius and a fixed
  round-6 radius disagree on real input, 7 of 30, with a third method siding with the
  certified one 7 times out of 7 (G6's question, answered without an answer key). **Neither
  becomes an accuracy number**, and the agent-written corpus is still uncollected.
- **G4 was cut, not repaired.** The vision comparison scored perfectly only because it read
  exact coordinate text rather than a render. Re-running it against a raster is a different
  experiment than the one that was reported.
- **The per-session transcript-cost ratio is half-measured.** The stamp's 7 tokens exist;
  the sampled-script denominator does not, because it comes from G1.
- **A clean refusal cliff is NOT EARNED** (§2).
- **"Usable as a hook on a real floor plan" is NOT EARNED** (§5), and §11 puts a number on
  it: **0 of 96** Wikimedia Commons floor plans certify at the default ceiling, 1 of 96 at
  `--max-vertices 6000`, and the median plan carries three times the default ceiling's worth
  of vertices. On 13,681 icon files the same default answers 79.4%.
- **Uniqueness of the certified scale is not established.** At most `CAND_MAX = 4` windows
  are tried, widest ratio first, first pass wins. A second window might also have passed
  with a different answer.

---

## 10. Every arm that lost, collected

| arm | lost by | against |
|---|---|---|
| round-to-6-decimals dict snap | 350 wrong / 528 | truth by construction |
| networkx `E - V + C` after that snap | 350 wrong / 528 | truth by construction |
| shapely `polygonize_full(unary_union)` | 336 wrong / 528 | truth by construction |
| shapely `set_precision(1e-6)` + the above | 299 wrong / 528 | truth by construction |
| skimage `euler_number` @ 4096 px | 7 wrong / 66 | truth by construction |
| skimage `euler_number` @ 512 px | 2 wrong / 66 | truth by construction |
| polygonize @ planimeter's own radius (oracle) | 22 wrong / 528 | truth by construction |
| GEOS `delaunay_triangles` as an EMST supergraph | 1 of 793 point sets | exact all-pairs Prim |
| planimeter at `rho = 100` | 3 wrong / 528 | truth by construction |
| planimeter's cost curve (G3) | exponent 1.825 against a 1.3 gate | the gate, committed first |
| planimeter's refusal cliff | no level certifies everything | the shape the design predicted |
| planimeter on two squares a tenth apart | one piece where a reader sees two | the picture |
| round-6 snap on 30 real icon files | 7 of 30 integers moved | `skimage.euler_number` @ 4096 px, which sided with the arrangement 7 of 7 |
| planimeter on 96 Commons floor plans | 0 answered at the default ceiling, 1 at `--max-vertices 6000` | its own advertised use case |
| planimeter on 13,681 real icon files | 2,819 refused, 20.6% | the same files, answered 10,862 times |
| the guard-ordering change, at the default ceiling | no effect outside the machine's own drift | a repeat of its own faster arm |

The last eight rows are planimeter's. A table of opponents without them would not be a
benchmark.

---

## 11. Real input — files this repository did not write

**Question.** Sections 1 through 8 all score against truth this repository constructed. What
happens to files nobody here drew, how often does the tool refuse them, and for what?

**Code of record.** Commit `4a7a3dc`, same machine as the header, `svgelements 1.9.6`,
`scikit-image 0.26.0`. The commit that records this section adds documentation, one
corrected source comment and one reader test, and moves no number.

**Corpus, and where its provenance comes from.** Both sets are fetched by a pinned recipe in
`realdata.py` rather than curated file by file: a corpus somebody picked one file at a time
is a corpus somebody could have picked to win. **Neither set carries a ground truth, and
neither is treated as if it did** — where a number below is called agreement it is agreement
between two methods, not a score against an answer key.

| set | provenance | files | in the repository |
|---|---|---|---|
| `sample` | every kth of the icon set by sorted name, under 32 KB | 30 | **yes**, `corpus/real/sample/` with the three upstream `LICENSE` files |
| `icons` | `@tabler/icons 3.46.0`, `feather-icons 4.29.2`, `bootstrap-icons 1.13.1` from the npm registry, MIT | 13,681 | no — 32 MB. `python realdata.py fetch --set icons` |
| `plans` | Wikimedia Commons full-text search, `filetype:drawing`, four fixed terms × 25 | 96 | no — 29 MB and share-alike licences. `python realdata.py fetch --set plans`, and `_meta.json` records the per-file licence |

### The committed sample, and the two controls

```
python realdata.py run --set sample --raster-stride 1
```

```
  sample   30 files                                     max_vertices default
  answered             30  100.0%
  refused               0    0.0%
  wall clock         median 48 ms   p95 190 ms   max 0.3 s
  raster @ 4096 px    30 of 30 certified checked (stride 1): 29 agree, 1 disagree
    ~ bootstrap__send-arrow-down.svg           raster 6 vs arrangement 4
  round-6 control    30 of 30 certified checked (stride 1): 23 agree, 7 disagree
```

Both controls come from `bench.py` and neither is truth. `skimage.euler_number` on ink at
4096 px is a different library reading a different representation; the round-to-six-decimals
snap plus a union-find is the arm §1 labels `STRAWMAN`.

**The seven round-6 disagreements are the row that matters, and they get checked a third
way.** On every one of the seven the raster sides with the arrangement:

| file | planimeter | round-6 | raster @ 4096 px |
|---|---|---|---|
| `feather__clipboard.svg` | 2 | 1 | **2** |
| `feather__database.svg` | 3 | 2 | **3** |
| `feather__layout.svg` | 3 | 1 | **3** |
| `tabler__currency-afghani.svg` | 2 | 1 | **2** |
| `tabler__quote-open.svg` | 3 | 1 | **3** |
| `tabler__rotate-3d.svg` | 4 | 3 | **4** |
| `tabler__tags-chevron-down.svg` | 3 | 2 | **3** |

On real files the strawman's fixed radius moves the integer on **7 of 30**, and the
independent method agrees with the certified radius every time it is asked. §1 measured that
same effect against constructed truth; this is the first time it has been measured on files
this repository did not write. The one raster disagreement runs the other way —
`bootstrap__send-arrow-down.svg`, raster 6 against arrangement 4, round-6 also 4 — and it is
the arrangement-faces-versus-rendered-regions seam the convention already names, not a
counting error.

### 13,681 icon files

```
python realdata.py run --set icons --raster-stride 500
```

```
  icons   13681 files                                   max_vertices default
  answered           10862   79.4%
  refused             2819   20.6%
    EDGES_CROSS            1715   12.5%   geometry
    VERTEX_NEAR_EDGE        759    5.5%   geometry
    CURVE_UNSTABLE          311    2.3%   geometry
    TOO_MANY_VERTICES        33    0.2%   budget
    NO_GEOMETRY               1    0.0%   geometry
  wall clock         median 37 ms   p95 224 ms   max 30.5 s
  raster @ 4096 px    22 of 10862 certified checked (stride 500): 20 agree, 2 disagree
    ~ wheat.svg                                raster 12 vs arrangement 3
    ~ whirl.svg                                raster 6 vs arrangement 2
  round-6 control    22 of 10862 certified checked (stride 500): 20 agree, 2 disagree
    ~ error-404-off.svg                        round-6 1 vs arrangement 2
    ~ heart-rate-monitor.svg                   round-6 2 vs arrangement 3
```

**Four files in five get an integer.** The refusals are almost entirely geometric.
`EDGES_CROSS` at 12.5% is line work that crosses at a point the file does not contain, which
is what an icon drawn as overlapping strokes looks like from inside an arrangement. The
budget refuses **0.2%**: the vertex ceiling is not what stops this set. The two raster
disagreements are both stroke-thickness cases at 4096 px, the same seam as above, and the
control's denominator is 22 because it runs on every 500th answered file, not on all 10,862.

### 96 Wikimedia Commons floor plans — the advertised use case, and it does not clear

```
python realdata.py run --set plans --raster-stride 1
python realdata.py run --set plans --max-vertices 6000 --raster-stride 1
```

| | default ceiling (2,000) | `--max-vertices 6000` |
|---|---|---|
| answered | **0 of 96, 0.0%** | **1 of 96, 1.0%** |
| `TOO_MANY_VERTICES` (budget) | 88, 91.7% | 57, 59.4% |
| `VERTEX_NEAR_EDGE` (geometry) | 4, 4.2% | 22, 22.9% |
| `EDGES_CROSS` (geometry) | 4, 4.2% | 12, 12.5% |
| `CURVE_UNSTABLE` (geometry) | 0 | 3, 3.1% |
| `NO_STABLE_SCALE` (geometry) | 0 | 1, 1.0% |
| wall clock | median 468 ms, p95 6,668 ms, max 19.0 s | median 1,989 ms, p95 9,693 ms, max 15.5 s |

**Raising the ceiling does not buy answers on this set, it buys coordinates.** Nearly every
file the higher ceiling admits arrives at a *geometry* refusal instead of a budget one: the
budget bucket falls from 88 to 57, and of those 31 files, **30** became `VERTEX_NEAR_EDGE`,
`EDGES_CROSS`, `CURVE_UNSTABLE` or `NO_STABLE_SCALE` and **1** became an answer. Pushed further on a subsample the trend holds —
four of the nine files with `6,000 < n ≤ 10,000`, at `--max-vertices 25000`, where the budget
cannot bind:

```
Zimnyaya_Vishnya_floor_4_plan-cs.svg           n=  6085    34.3s  VERTEX_NEAR_EDGE
Mariahilf_Church_plan.svg                      n=  6398    18.9s  EDGE_COLLAPSED
Camber_Castle_plan_with_stages,_labelled.svg   n=  6788    35.5s  VERTEX_NEAR_EDGE
Plan_of_Castle_Garden_in_Český_Krumlov.svg     n=  8726    68.5s  VERTEX_NEAR_EDGE
```

Zero of four. **A published floor plan is drawn, not built**: a wall ends near a wall rather
than on it, and two walls cross where the file records no vertex. Those are the two
conditions the convention says are refused, so the refusal is the design working — and **the
answer rate on this corpus is the design's price, printed here rather than left to be
discovered.** The bands are in the file's own units and they are narrow: 19 vertices inside
`(0, 1.78e-3)` on one Beylerbeyi Palace plan, 190 inside `(0, 1.21e-4)` on the BNF site plan,
23 inside `(0, 4.25e-7)` on `Plan_abbaye_corvey.svg`. These are near misses, not draughting
at a visible scale.

**The one file that certifies.** `Akori_church_plan.svg`, at `--max-vertices 3000`:
`pieces 13, faces 13, chi 0`, radius `7.03e-08`, window `[4.945e-10, 9.998e-06)`, ratio
20,218. Both controls agree with it. It has 1,295 vertices — under the default ceiling all
along — and was refused before this commit because the `2N` stability pass crossed the
ceiling and that budget refusal was reported as `CURVE_UNSTABLE`.

### Why the ceiling binds: cost measured on real geometry

The plans are far larger than the synthetic stratum. Distinct endpoints per file, at the
0/10/25/50/75/90/100th percentile: **105 / 1,169 / 2,273 / 6,398 / 22,044 / 69,042 /
359,723.** The median plan is three times the default ceiling and the largest is 180 times
it. Wall clock for the two quadratic passes, on the real files themselves:

| file | vertices | segments | `emst` | vertex-edge spectrum |
|---|---|---|---|---|
| `Floor_plans_of_Buda_Castle_he.svg` | 105 | 106 | 0.00 s | 0.00 s |
| `Pinxton_Castle_schematic_plan.svg` | 1,108 | 1,292 | 0.02 s | 0.07 s |
| `Cathedral_schematic_plan_pt_vectorial.svg` | 2,273 | 2,188 | 0.05 s | 0.26 s |
| `Kaaba-plan_bn.svg` | 4,835 | 4,751 | 0.17 s | 1.16 s |
| `Camber_Castle_plan,_labelled.svg` | 6,776 | 6,758 | 0.42 s | 3.16 s |
| `Nijo_Castle_plan.svg` | 11,506 | 11,497 | 1.32 s | 8.52 s |
| `Plan_du_site_Richelieu-Louvois…svg` | 22,261 | 22,352 | 4.50 s | 40.01 s |

The spectrum, not the spanning tree, is what costs: it is the `(vertex, edge)` quantifier the
certificate is defined over, and §5's exponent is the same finding on constructed grids. A
file with curves pays it twice, at `N` and again at about `2N` vertices, so the **effective
ceiling for a curved file is roughly half the flag's value** — which is exactly how
`Akori_church_plan.svg` was lost.

### The guard ordering, and the arm of it that lost

`check_vertex_cap` moved in front of the vertex-edge pass. At the default ceiling **this buys
nothing that can be distinguished from the machine**, and the arms are printed rather than
the claim:

```
A guard first                  median  361 ms   p95 4740 ms   max 12.2 s   total  96.6 s
B spectrum first               median  449 ms   p95 4654 ms   max 16.1 s   total 111.8 s
A guard first, repeated        median  443 ms   p95 5563 ms   max 15.4 s   total 122.0 s
A and B verdicts identical on all 96 files: True
```

The repeat of arm A is slower than arm B, so the drift is larger than the difference the
change would claim; at the default ceiling the pair budget was already capping the wasted
pass. The ordering earns its four lines only where the ceiling is raised — same file, same
three arms, at `--max-vertices 20000`, where 4.97e8 pairs sit under the implied 1.6e9 pair
budget:

```
A guard first             0.7 s   TOO_MANY_VERTICES
B spectrum first         41.1 s   TOO_MANY_VERTICES
A repeated                0.8 s   TOO_MANY_VERTICES
```

### The relabel, measured against the function it replaced

Same process, the same 96 plans, the pre-commit `read.stable` restored as a second arm:

```
committed              TOO_MANY_VERTICES 88, VERTEX_NEAR_EDGE 4, EDGES_CROSS 4
pre-commit stable()    TOO_MANY_VERTICES 77, CURVE_UNSTABLE 11, VERTEX_NEAR_EDGE 4, EDGES_CROSS 4
```

Eleven files were told *the curve is ambiguous, go re-observe it* when what happened is that
the machine ran out of room on a pass carrying twice the vertices. The eight geometry
refusals are untouched, which is what the control is for.

### What the reader met, and what it dropped

`0 of 96` plans were unreadable. **One** — `Plan_abbaye_corvey.svg` — parses only after a
`<path>` carrying no `d` is dropped: `svgelements 1.9.6` raises
`TypeError: object of type NoneType has no len()` inside its own parser on it. Such an
element has no geometry by the SVG grammar, so dropping it invents nothing, and it is counted
as `path-without-d` on the verdict rather than dropped silently. What else was skipped across
the 96, by tag: `image` 13,160 in 4 files, `tspan` 1,758 in 55, `text` 1,409 in 61, and RDF /
Inkscape metadata in roughly 60 files each. Every one of those is on the `skipped` record of
the verdict that reports it.

### What real input did **not** answer

- **No file here has a ground truth.** `corpus/found/` is still empty and G5's specification —
  thirty real files with truth established by a second method *before* planimeter runs — is
  still unmet. What is measured above is a refusal histogram and two method-agreement rates,
  and neither of those becomes an accuracy number.
- **None of these files was written by an agent.** They were drawn by people with Inkscape and
  emitted by icon build tools. G1, and the agent-written half of G5, have not moved.
- **The `sample` set is 30 files, committed for reproducibility rather than for power.** Its
  100% answer rate is the icon set's 79.4% restricted to small files, and it should be read
  that way.
- **Refusal rates are per corpus and per ceiling, and they do not compose.** The 20.6% on
  icons, the 99.0% on plans at `--max-vertices 6000` and the 5–10 of 88 per jitter level in §2
  are three different questions. None of them is *the* refusal rate.

---

## 12. Limits

One machine, one operating system, one Python. The jitter stratum is synthetic and its
truth comes from construction recipes, so it measures the arrangement layer and says
nothing about real agent-written files. §11 measures real files, and none of them has a
ground truth or was written by an agent, so it reports refusal rates and method agreement
and never an accuracy — G5's specified corpus and G1 have still not run. §11's `icons` and
`plans` sets are 61 MB and are not committed; the fetch recipe is pinned by exact version
and by fixed search terms, but Wikimedia Commons search results can move, so the `plans`
set is reproducible in method and not guaranteed identical in membership. The
strawman baseline is not the baseline that decides whether there is a product; G1 has not
run. `RHO`, `CAND_MAX` and `FLOOR_ULPS` are three constants this package chose, and while
they are scale-free, printed on every answer and movable by flag, choosing them is still
choosing. The face count is arrangement-theoretic and does not match what a renderer
fills. Refinement stability across `N` and `2N` is evidence, not a theorem. The 22 rows the
oracle control missed were not individually inspected. Benchmark timings are wall clock on
a laptop with other processes running, which is why the G7 rows carry their full range and
the G3 rows are best-of-three.
