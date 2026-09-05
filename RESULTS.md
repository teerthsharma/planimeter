# RESULTS

Every number below was produced by a command in this repository on one machine, and
every number sits next to the control it was compared against. Arms that could not be
run are printed as NOT RUN with the reason, never omitted. Three of the seven gates
did not clear and they are reported in the same voice as the ones that did.

**Machine of record.**

```
commit    1e4f006            the last commit that changed code, working tree clean
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
.venv/Scripts/python -m pytest -q         # 474 passed
.venv/Scripts/python bench.py             # the tables below, 57.7 s
```

The footer of that run reads `commit 1e4f006  machine WIN-16QAL06O9GB  python 3.11.9
PYTHONHASHSEED=0  57.7 s`. Sections 1, 2 and 3 are bit-identical across every run on this
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
         4       40       25        0.1        0.2        0.6
         8      144       81        0.3        0.6        2.9
        12      312      169        1.5        1.2       12.4
        16      544      289        7.7        3.6       41.5
        20      840      441       17.3        7.3       95.5
        24     1200      625       41.4       14.8      178.6
        28     1624      841       66.5       22.0      334.2
        32     2112     1089      129.4       43.6      548.2
        36     2664     1369      206.3       65.5      939.0
        40     3280     1681      299.8       85.4     1357.4
        43     3784     1936      412.2      113.4     1774.8
```

```
    fitted log-log exponent 1.82  (kills above 1.3)
    extrapolated to n = 1e5: 698776 ms  (kills above 50 ms)
```

**G3 thresholds: exponent > 1.3, or > 50 ms at n = 1e5. Both blown, by orders of
magnitude. NOT EARNED.**

> **"Usable as a hook on a real floor plan" is withdrawn, not softened.**

The comfortable hook range is under roughly 600 segments: 41 ms at 544, 95 ms at 840,
1.8 s at 3,784. A hard ceiling of `BRUTE_MAX = 2000` vertices refuses `TOO_MANY_VERTICES`
above it rather than stalling a turn.

The cost is the all-pairs vertex-to-edge pass the certificate quantifies over. That pass
is not an implementation detail that a k-d tree removes: the certificate's precondition is
a statement about *every* (vertex, non-incident edge) pair, and a nearest-neighbour
structure answers a different question. Three independent measurements of the exponent
exist — 1.82 over 11 points to k=43 in the run of record, 1.87 over the same 11 points on
an earlier run, and 2.2 over a shorter range during the core build. All three are far
above the gate; the gate result does not depend on which is right.

---

## 6. G7 — hook wall clock, with a floor control

**Command.** `.venv/Scripts/python bench.py` (20 cold subprocesses per row, Windows)

```
    FLOOR bare interpreter, no hook at all        46.7 ms median  [42.6, 55.1]
    silent path (.py write)                       55.7 ms median  [49.4, 67.9]  holds
    CONTROL same hook, suffix check removed      139.9 ms median  [121.9, 153.0]
    geometry path (.svg write)                   148.6 ms median  [130.9, 157.6]  holds
```

**G7 thresholds: 60 ms silent, 250 ms geometry. Both hold on the run of record, and the
silent one does not hold on every run.**

**The floor control is what makes these numbers readable, and it was added after the
threshold was committed.** `python -c pass` costs 46.7 ms on this machine. The silent path
costs **9.0 ms over an interpreter that does nothing** — that is the whole cost of
`planimeter.hook`'s module-scope imports plus the suffix check. The 60 ms gate is therefore
measuring Windows process startup with 13 ms of headroom, not planimeter, and on a machine
whose Python starts slower it will fire for reasons that have nothing to do with this
package.

**This is not hypothetical.** Across five runs of `bench.py` on this machine the silent
path measured 52.5, 63.3, 54.8, 60.5 and 55.7 ms; two of the five exceeded the 60 ms gate
and were printed as `KILLS`. The gate is reported as it stands — the threshold has not been
moved, and no run was discarded for failing it — and the floor row is published beside it
so a reader can see what the number is made of. **On this evidence the silent-path gate is
not a property of the package: it is a coin flip on process startup, and the honest reading
of the row is the 9.0 ms difference, not the pass or fail beside it.**

The suffix check is worth 84.2 ms on every non-geometry write (139.9 against 55.7), which
is the difference between a hook that can be left installed and one that cannot.

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
- **G5 and G6** need `corpus/found/` — roughly 30 real agent-written SVGs with truth
  established by a second method before planimeter is run on them. It holds no SVGs, and
  `corpus/found/README.md` states the collection method and the reporting rule rather than
  inventing rows. `bench.py` reads that emptiness off the filesystem when it prints the
  line above rather than asserting it, so the row retires itself the day files arrive. Until it has files, no claim about real-world refusal rates or about
  whether the certified scale ever changes a real answer is made here. `corpus.found()`
  returns `[]` and a test asserts it says so.
- **G4 was cut, not repaired.** The vision comparison scored perfectly only because it read
  exact coordinate text rather than a render. Re-running it against a raster is a different
  experiment than the one that was reported.
- **The per-session transcript-cost ratio is half-measured.** The stamp's 7 tokens exist;
  the sampled-script denominator does not, because it comes from G1.
- **A clean refusal cliff is NOT EARNED** (§2).
- **"Usable as a hook on a real floor plan" is NOT EARNED** (§5).
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
| planimeter's cost curve (G3) | exponent 1.82 against a 1.3 gate | the gate, committed first |
| planimeter's refusal cliff | no level certifies everything | the shape the design predicted |
| planimeter on two squares a tenth apart | one piece where a reader sees two | the picture |

The last four rows are planimeter's. A table of opponents without them would not be a
benchmark.

---

## 11. Limits

One machine, one operating system, one Python. The jitter stratum is synthetic and its
truth comes from construction recipes, so it measures the arrangement layer and says
nothing about real agent-written files — that is G5 and G6, and they have not run. The
strawman baseline is not the baseline that decides whether there is a product; G1 has not
run. `RHO`, `CAND_MAX` and `FLOOR_ULPS` are three constants this package chose, and while
they are scale-free, printed on every answer and movable by flag, choosing them is still
choosing. The face count is arrangement-theoretic and does not match what a renderer
fills. Refinement stability across `N` and `2N` is evidence, not a theorem. The 22 rows the
oracle control missed were not individually inspected. Benchmark timings are wall clock on
a laptop with other processes running, which is why the G7 rows carry their full range and
the G3 rows are best-of-three.
