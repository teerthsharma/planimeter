"""The gates, one command. `python bench.py [--full] [--json out.json]`

Every threshold below is a named constant in this file, so the thresholds are in
git history before the numbers are. Arms this machine cannot run are PRINTED AS
NOT RUN with the reason, never skipped silently: a benchmark that quietly drops
the arm that would have lost is not a benchmark.

    G1  is the baseline a strawman?   >= 20 unprompted first-attempt agent
        scripts against the closed-form corpus, whole distribution published.
        KILL: if the MEDIAN sample clears G1_MEDIAN_KILL of the jitter stratum,
        the accuracy headline is dead and what remains is the printed scale and
        the hook slot. Publish that outcome; do not hide it.
    G2  zero wrong on the jitter stratum. KILL: any nonzero value.
    G3  cost. KILL: fitted log-log exponent > G3_EXPONENT_KILL, or > G3_MS_KILL
        ms at n = 1e5. Either one and "usable as a hook on a real floor plan"
        is labelled NOT EARNED, not softened.
    G5  what fraction of ~30 real agent-written SVGs get an integer.
    G6  does the certified scale ever change the answer against a round-6 snap
        on those files? KILL: a zero here ends the accuracy story on real files.
    G7  hook wall clock. KILL: > G7_SILENT_MS silent, > G7_GEOMETRY_MS geometry.
    G4  vision comparison: CUT, not fixed. It scored perfectly only because
        it read exact coordinate text rather than a render.

The corpus contract this file consumes, so the corpus owner has a target: a
module named `corpus` (repo root) or `tests.figures`, carrying
`FAMILIES: {name: (segments (m,2,2), (V, E, pieces, faces, chi))}` and either
`jitter_stratum(ratios=, seeds=)` yielding dicts with `family`, `ratio`, `seed`,
`truth` and `seg`, or the older `split_shared_vertices(seg, sigma, rng)`. The
jitter levels come from the corpus's own `RATIOS` when it publishes them, because
the schedule is the corpus owner's to define and not the benchmark's. G1, G5 and
G6 additionally need `baselines/agent_samples/` and `corpus/found/`, and print
NOT RUN until they exist.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import zlib

import numpy as np

# ---- thresholds, committed before any number exists ------------------------
G1_MEDIAN_KILL = 20 / 24      # median sampled agent script clearing this kills the headline
G2_WRONG_KILL = 0             # a count, not a rate
G3_EXPONENT_KILL = 1.3
G3_MS_KILL = 50.0             # at n = 1e5
G7_SILENT_MS = 60.0
G7_GEOMETRY_MS = 250.0

RULE = "=" * 78
THIN = "-" * 78
JITTER_LEVELS = (1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 5e-2)   # sigma / g, if the corpus names none
RHO_SWEEP = (3.0, 10.0, 100.0)
NOT_RUN = []                  # every arm this machine could not run, printed at the end


def not_run(what, why):
    NOT_RUN.append((what, why))
    return None


# --------------------------------------------------------------------------
# the corpus
# --------------------------------------------------------------------------

def load_corpus():
    """`corpus` at the repo root if it exists, else the core's `tests/figures.py`,
    which carries the same two names and is slated to be collapsed into it."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, os.path.join(here, "tests")):
        if d not in sys.path:
            sys.path.insert(0, d)
    for name in ("corpus", "figures"):
        try:
            mod = __import__(name)
        except Exception:
            continue
        if hasattr(mod, "FAMILIES") and (hasattr(mod, "jitter_stratum")
                                         or hasattr(mod, "split_shared_vertices")):
            return mod, name
    return None, ""


def levels_of(mod):
    """The corpus's own sigma/g schedule when it publishes one. A benchmark that
    imposes its own levels on someone else's corpus is measuring a stratum the
    truth was not constructed for."""
    return tuple(getattr(mod, "RATIOS", None) or JITTER_LEVELS)


def draws(mod, seeds, levels):
    """(name, sigma_over_g, seed, segments, truth_faces, truth_pieces)."""
    if hasattr(mod, "jitter_stratum"):
        for d in mod.jitter_stratum(ratios=tuple(levels), seeds=seeds):
            yield (d["family"], d["ratio"], d["seed"], d["seg"],
                   d["truth"][3], d["truth"][2])
        return
    for name, (seg, truth) in sorted(mod.FAMILIES.items()):
        for lvl in levels:
            for s in range(seeds):
                # zlib.crc32, not hash(): PYTHONHASHSEED randomises str hashing per
                # process, and a benchmark whose draws move between runs is not one.
                rng = np.random.default_rng(zlib.crc32(("%s|%g|%d" % (name, lvl, s)).encode()))
                yield (name, lvl, s, mod.split_shared_vertices(seg, lvl * 10.0, rng),
                       truth[3], truth[2])


# --------------------------------------------------------------------------
# the arms. Each returns the enclosed-face count, or None for "no answer".
# --------------------------------------------------------------------------

def _round6_graph(seg, nd=6):
    key, edges = {}, []
    for a, b in seg:
        ids = []
        for p in (a, b):
            k = (round(float(p[0]), nd), round(float(p[1]), nd))
            ids.append(key.setdefault(k, len(key)))
        edges.append(tuple(ids))
    return len(key), edges


def arm_round6(seg):
    """The strawman, named as one: a hand-written round-to-six-decimals snap and
    a union-find. This is the arm the prototype's 5-of-6 headline beat, and G1
    exists because a competent agent does not write it."""
    n, edges = _round6_graph(seg)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    uniq = set()
    for a, b in edges:
        if a != b:
            uniq.add((min(a, b), max(a, b)))
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    c = len({find(i) for i in range(n)})
    return len(uniq) - n + c


def arm_networkx(seg):
    """The honest zero-effort opponent for the integer: three lines of networkx
    after the same round-6 snap. It reimplements count.py exactly."""
    import networkx as nx
    n, edges = _round6_graph(seg)
    g = nx.Graph()
    g.add_nodes_from(range(n))
    g.add_edges_from((a, b) for a, b in edges if a != b)
    return g.number_of_edges() - g.number_of_nodes() + nx.number_connected_components(g)


def _polygonize(seg, grid=None):
    from shapely import set_precision
    from shapely.geometry import MultiLineString
    from shapely.ops import polygonize_full, unary_union
    ml = MultiLineString([[tuple(a), tuple(b)] for a, b in seg])
    if grid:
        ml = set_precision(ml, float(grid))
    polys, cuts, dangles, invalid = polygonize_full(unary_union(ml))
    return len(polys.geoms)


def arm_polygonize(seg):
    """shapely / GEOS on noded input. It also reports dangles, cuts and invalid
    rings - the claim that it offers no diagnostic is false and is cut."""
    return _polygonize(seg)


def arm_set_precision(seg):
    """GEOS's own snap, taking the grid size you invent. The honest opponent for
    the snap layer."""
    return _polygonize(seg, 1e-6)


def _raster(seg, px):
    from skimage.draw import line as dline
    from skimage.measure import euler_number, label
    p = seg.reshape(-1, 2)
    lo, hi = p.min(0), p.max(0)
    span = float(max((hi - lo).max(), 1e-12))
    q = np.rint((seg - lo) * ((px - 6) / span)).astype(int) + 3
    ink = np.zeros((px, px), bool)
    for a, b in q:
        rr, cc = dline(int(a[1]), int(a[0]), int(b[1]), int(b[0]))
        ink[rr, cc] = True
    return int(label(ink, connectivity=2).max()) - int(euler_number(ink, connectivity=2))


def arm_euler512(seg):
    return _raster(seg, 512)


def arm_euler4096(seg):
    return _raster(seg, 4096)


def arm_refuse_all(seg):
    """CONTROL. A tool that refuses everything scores zero wrong. Any accuracy
    row that does not sit beside this one is unreadable."""
    return None


def arm_oracle(seg):
    """CONTROL, and the sharpest one in the benchmark: polygonize handed
    planimeter's own certified radius. If this also scores zero wrong then the
    counter contributes nothing and the whole contribution is the scale and the
    refusal."""
    import planimeter
    c = planimeter.chi_segments(seg)
    if not c:
        return None
    return _polygonize(seg, c.radius)


def arm_planimeter(seg):
    import planimeter
    c = planimeter.chi_segments(seg)
    return c.faces if c else None


ARMS = [
    ("planimeter", arm_planimeter, None),
    ("round-to-6-decimals dict snap  STRAWMAN", arm_round6, None),
    ("networkx b1 after a round-6 snap", arm_networkx, "networkx"),
    ("shapely polygonize_full(unary_union)", arm_polygonize, "shapely"),
    ("shapely set_precision(1e-6) + the above", arm_set_precision, "shapely"),
    ("skimage.euler_number @  512 px", arm_euler512, "skimage"),
    ("skimage.euler_number @ 4096 px", arm_euler4096, "skimage"),
    ("CONTROL refuse-on-anything", arm_refuse_all, None),
    ("CONTROL polygonize @ planimeter's radius", arm_oracle, "shapely"),
]

RASTER_ARMS = {"skimage.euler_number @  512 px", "skimage.euler_number @ 4096 px"}


def available(dep):
    if dep is None:
        return True
    try:
        __import__(dep)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# G2 / the headline table
# --------------------------------------------------------------------------

def headline(mod, name, seeds, raster_stride):
    levels = levels_of(mod)
    rows, all_draws = [], list(draws(mod, seeds, levels))
    n_fam = len(mod.FAMILIES)
    print(RULE)
    print("  wrong integers on the jitter stratum")
    print("  %d figure families x %d jitter levels x %d seeds = %d draws, truth by construction"
          % (n_fam, len(levels), seeds, len(all_draws)))
    print("  corpus module: %s" % name)
    print(RULE)
    for label_, fn, dep in ARMS:
        if not available(dep):
            not_run(label_, "%s is not installed" % dep)
            print("    %-42s NOT RUN  (%s missing)" % (label_, dep))
            continue
        stride = raster_stride if label_ in RASTER_ARMS else 1
        wrong = exact = refused = 0
        worst = None
        t0 = time.perf_counter()
        for i, (fam, lvl, seed, seg, truth, _pieces) in enumerate(all_draws):
            if i % stride:
                continue
            try:
                got = fn(seg)
            except Exception:
                got = None
            if got is None:
                refused += 1
            elif int(got) == truth:
                exact += 1
            else:
                wrong += 1
                if worst is None:
                    worst = (fam, lvl, seed, truth, int(got))
        dt = time.perf_counter() - t0
        n = wrong + exact + refused
        rows.append({"arm": label_, "wrong": wrong, "exact": exact, "refused": refused,
                     "n": n, "seconds": round(dt, 2),
                     "first_wrong": worst})
        note = "" if stride == 1 else "  (stride %d)" % stride
        print("    %-42s %4d wrong %5d exact %5d refused  / %d%s"
              % (label_, wrong, exact, refused, n, note))
        if worst:
            print("      %sfirst wrong: %s  sigma/g %g  seed %d  truth %d  got %d"
                  % (" " * 40, worst[0], worst[1], worst[2], worst[3], worst[4]))
    print(THIN)
    p = [r for r in rows if r["arm"] == "planimeter"]
    if p:
        verdict = "HOLDS" if p[0]["wrong"] <= G2_WRONG_KILL else "BLOCKS THE RELEASE"
        print("  G2  planimeter wrong = %d  (threshold %d)  %s"
              % (p[0]["wrong"], G2_WRONG_KILL, verdict))
    print("  G1  agent-sample rows NOT RUN: baselines/agent_samples/ is empty. The strawman")
    print("      row above is NOT the baseline the headline may be quoted against.")
    print(RULE)
    return rows


def by_level(mod, seeds):
    """The cliff, or the absence of one. Direction and zero-wrong per level."""
    print("  refusal and wrong counts by jitter level")
    print(THIN)
    print("    %-10s %8s %8s %8s" % ("sigma/g", "wrong", "exact", "refused"))
    out = []
    for lvl in levels_of(mod):
        w = e = r = 0
        for _n, _l, _s, seg, truth, _p in draws(mod, seeds, (lvl,)):
            got = arm_planimeter(seg)
            if got is None:
                r += 1
            elif got == truth:
                e += 1
            else:
                w += 1
        out.append({"level": lvl, "wrong": w, "exact": e, "refused": r})
        print("    %-10g %8d %8d %8d" % (lvl, w, e, r))
    print(THIN)
    return out


def rho_sensitivity(mod, seeds):
    """RHO is the one free constant in a tool whose pitch is that it invents
    none. Isolate its contribution rather than defending it."""
    import planimeter
    print("  RHO sensitivity")
    print(THIN)
    print("    %-8s %8s %8s %8s %10s" % ("rho", "wrong", "exact", "refused", "of which"))
    out = []
    for rho in RHO_SWEEP:
        w = e = r = merge_nothing = 0
        worst = []
        for name, lvl, _s, seg, truth, _p in draws(mod, seeds, levels_of(mod)):
            c = planimeter.chi_segments(seg, rho=rho)
            if not c:
                r += 1
            elif c.faces == truth:
                e += 1
            else:
                w += 1
                merge_nothing += (c.n_merged == 0)
                worst.append((name, lvl, truth, c.faces, c.n_merged))
        out.append({"rho": rho, "wrong": w, "exact": e, "refused": r,
                    "wrong_from_merge_nothing": merge_nothing, "wrong_rows": worst[:8]})
        print("    %-8g %8d %8d %8d %10s"
              % (rho, w, e, r, "%d merged nothing" % merge_nothing if w else ""))
        for row in worst[:4]:
            print("      %-28s sigma/g %-8g truth %d  certified %d  merged %d" % row)
    print(THIN)
    print("    Raising rho does not make the tool stricter. It removes the genuine merge")
    print("    window - whose ratio is bounded by the drawing - and leaves the merge-nothing")
    print("    window, whose ratio is drawing-scale over machine epsilon for arithmetic")
    print("    reasons alone. The wrong rows above are that window certifying the FILE, in")
    print("    which a triangle whose corners sit 0.1 apart on a 10-unit figure is honestly")
    print("    three disjoint segments. Zero-wrong is therefore a claim about rho <= 10.")
    print(THIN)
    return out


# --------------------------------------------------------------------------
# G3 cost
# --------------------------------------------------------------------------

def _grid(k, h=1.0):
    segs = []
    for i in range(k + 1):
        for j in range(k):
            segs.append([[i * h, j * h], [i * h, (j + 1) * h]])
            segs.append([[j * h, i * h], [(j + 1) * h, i * h]])
    return np.array(segs, dtype=np.float64)


def _ms(fn, repeat=3):
    best = float("inf")
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        best = min(best, (time.perf_counter() - t) * 1e3)
    return best


def cost(ks):
    from planimeter import arrange, snap
    import planimeter
    print(RULE)
    print("  G3  cost, grid(k): ms per stage, best of 3")
    print(RULE)
    print("    %6s %8s %8s %10s %10s %10s" % ("k", "segs", "verts", "spectrum", "window", "total"))
    rows = []
    for k in ks:
        seg = _grid(k)
        pts, flat = snap.dedup_exact(seg.reshape(-1, 2))
        ends = flat.reshape(len(seg), 2)
        try:
            t_spec = _ms(lambda: arrange.vertex_edge_spectrum(pts, ends))
            ve = arrange.vertex_edge_spectrum(pts, ends)
            t_win = _ms(lambda: snap.candidates(pts, extra=ve))
            t_tot = _ms(lambda: planimeter.chi_segments(seg))
        except MemoryError:
            print("    %6d %8d %8d   MemoryError - the ceiling, published" % (k, len(seg), len(pts)))
            break
        rows.append({"k": k, "segments": len(seg), "vertices": len(pts),
                     "spectrum_ms": round(t_spec, 2), "window_ms": round(t_win, 2),
                     "total_ms": round(t_tot, 2)})
        print("    %6d %8d %8d %10.1f %10.1f %10.1f"
              % (k, len(seg), len(pts), t_spec, t_win, t_tot))
    print(THIN)
    if len(rows) >= 2:
        xs = [math.log(r["segments"]) for r in rows]
        ys = [math.log(r["total_ms"]) for r in rows]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs)
        expo = num / den if den else float("nan")
        at1e5 = rows[-1]["total_ms"] * (1e5 / rows[-1]["segments"]) ** expo
        kill = expo > G3_EXPONENT_KILL or at1e5 > G3_MS_KILL
        print("    fitted log-log exponent %.2f  (kills above %.1f)" % (expo, G3_EXPONENT_KILL))
        print("    extrapolated to n = 1e5: %.0f ms  (kills above %.0f ms)" % (at1e5, G3_MS_KILL))
        print("    G3  %s" % ("NOT EARNED: 'usable as a hook on a real floor plan' is withdrawn."
                              if kill else "holds"))
        print("        The comfortable hook range is the top row that stays under ~100 ms.")
        return {"rows": rows, "exponent": round(expo, 3), "ms_at_1e5": round(at1e5, 1),
                "not_earned": bool(kill)}
    return {"rows": rows}


# --------------------------------------------------------------------------
# G7 hook wall clock
# --------------------------------------------------------------------------

def _run(args, payload, n):
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        subprocess.run(args, input=payload, capture_output=True, text=True)
        ts.append((time.perf_counter() - t) * 1e3)
    return statistics.median(ts), min(ts), max(ts)


def hook_latency(tmp, n=20):
    print(RULE)
    print("  G7  hook wall clock, %s, %d cold subprocesses each" % (platform.system(), n))
    print(RULE)
    py = sys.executable
    notgeo = os.path.join(tmp, "x.py")
    open(notgeo, "w").write("# not geometry\n")
    svg = os.path.join(tmp, "demo.svg")
    from planimeter.cli import DEMO_SVG
    open(svg, "w").write(DEMO_SVG)

    def payload(p):
        return json.dumps({"tool_name": "Write", "tool_input": {"file_path": p}})

    out = {}
    rows = [
        ("FLOOR bare interpreter, no hook at all", [py, "-c", "pass"], "", None),
        ("silent path (.py write)", [py, "-m", "planimeter.hook"], payload(notgeo),
         G7_SILENT_MS),
        ("CONTROL same hook, suffix check removed",
         [py, "-c", "from planimeter.hook import main; main(force=True)"], payload(notgeo), None),
        ("geometry path (.svg write)", [py, "-m", "planimeter.hook"], payload(svg),
         G7_GEOMETRY_MS),
    ]
    for label_, args, pl, kill in rows:
        med, lo, hi = _run(args, pl, n)
        flag = "" if kill is None else ("  KILLS (> %.0f)" % kill if med > kill else "  holds")
        print("    %-42s %7.1f ms median  [%.1f, %.1f]%s" % (label_, med, lo, hi, flag))
        out[label_] = {"median_ms": round(med, 1), "min_ms": round(lo, 1),
                       "max_ms": round(hi, 1), "kill_ms": kill}
    r = subprocess.run([py, "-m", "planimeter.hook"], input=payload(svg),
                       capture_output=True, text=True)
    stamp = ""
    try:
        stamp = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    except Exception:
        pass
    print(THIN)
    floor = out["FLOOR bare interpreter, no hook at all"]["median_ms"]
    silent = out["silent path (.py write)"]["median_ms"]
    print("    The silent path costs %.1f ms over an interpreter that does nothing"
          % (silent - floor))
    print("    (%.1f ms floor on this machine). G7_SILENT_MS was committed at %.0f ms"
          % (floor, G7_SILENT_MS))
    print("    WITHOUT that control, so on a machine whose Python starts in %.0f ms the"
          % floor)
    print("    gate measures Windows and not planimeter. The gate result above stands as")
    print("    written; this line says what it is made of, and does not move it.")
    print(THIN)
    print("    the stamp itself: %s" % (stamp or "(none - the reader is not installed yet)"))
    out["stamp"] = stamp
    out["stamp_tokens"] = stamp_cost(stamp)
    return out


def stamp_cost(stamp):
    """Tokens for the stamp with the path excluded, because a long path
    tokenises differently and its cost is reported on its own."""
    if not stamp:
        return not_run("stamp token budget", "no stamp: the reader is not installed")
    body = stamp.split("  ", 1)[1] if "  " in stamp else stamp
    path = stamp[:len(stamp) - len(body)]
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        n_body, n_path, name = len(enc.encode(body)), len(enc.encode(path)), "cl100k_base"
    except Exception:
        not_run("tokens under a named encoding", "tiktoken is not installed")
        n_body, n_path, name = len(body.split()), len(path.split()), "whitespace words"
    print("    stamp body %d %s, prefix and path %d more" % (n_body, name, n_path))
    print("    G1's per-session comparison (stamp x writes vs one sampled script) NOT RUN:")
    print("      baselines/agent_samples/ is empty, so there is nothing to compare against.")
    return {"encoding": name, "body": n_body, "path": n_path}


# --------------------------------------------------------------------------

def pin_hash_seed():
    """Re-exec once under PYTHONHASHSEED=0.

    A corpus that seeds its generator from `hash((name, ratio, seed))` draws a
    different stratum in every interpreter, because str hashing is salted per
    process. Without this the table cannot be reproduced and a wrong row cannot
    be investigated: the draw that produced it no longer exists. Pinning the
    salt is the smallest fix that does not reach into someone else's file.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    env = dict(os.environ, PYTHONHASHSEED="0")
    raise SystemExit(subprocess.call([sys.executable, os.path.abspath(__file__)]
                                     + sys.argv[1:], env=env))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--full", action="store_true", help="10 seeds per level instead of 2")
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--raster-stride", type=int, default=8,
                    help="rasterised arms are scored on every Nth draw; the denominator "
                         "is printed with the row")
    ap.add_argument("--max-k", type=int, default=43,
                    help="largest grid(k) in the cost curve; 43 is the BRUTE_MAX ceiling")
    ap.add_argument("--json", default=None, metavar="OUT")
    a = ap.parse_args(argv)
    pin_hash_seed()
    seeds = a.seeds if a.seeds is not None else (10 if a.full else 2)

    t0 = time.perf_counter()
    out = {"machine": platform.node(), "python": platform.python_version(),
           "platform": platform.platform(), "numpy": np.__version__,
           "commit": commit(), "seeds": seeds, "PYTHONHASHSEED": "0"}
    mod, name = load_corpus()
    if mod is None:
        not_run("the whole headline table", "no corpus module: see this file's docstring")
        print(RULE)
        print("  headline table NOT RUN: no `corpus` module and no `tests.figures`.")
        print(RULE)
    else:
        out["headline"] = headline(mod, name, seeds, a.raster_stride)
        out["by_level"] = by_level(mod, seeds)
        out["rho"] = rho_sensitivity(mod, seeds)

    ks = [k for k in (4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 43) if k <= a.max_k]
    out["G3"] = cost(ks)

    import tempfile
    tmp = tempfile.mkdtemp(prefix="planimeter-bench-")
    out["G7"] = hook_latency(tmp)

    print(RULE)
    print("  NOT RUN, and why")
    for what, why in NOT_RUN + [
            ("G1 agent samples", "baselines/agent_samples/ does not exist"),
            ("G5 found-corpus refusal histogram", "corpus/found/ does not exist"),
            ("G6 certified scale vs round-6 on real files", "corpus/found/ does not exist"),
            ("G4 vision comparison", "CUT: it read coordinate text, not a render")]:
        print("    %-46s %s" % (what, why))
    print(RULE)
    print("  commit %s  machine %s  python %s  PYTHONHASHSEED=0  %.1f s"
          % (out["commit"], out["machine"], out["python"], time.perf_counter() - t0))
    print(RULE)

    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=str)
        print("  wrote %s" % a.json)
    return 0


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, cwd=os.path.dirname(os.path.abspath(__file__))
                              ).stdout.strip() or "(none)"
    except Exception:
        return "(none)"


def _selfcheck():
    """Every arm on one clean figure where the answer is not in doubt, so a
    broken arm fails here rather than silently scoring wrong in the table."""
    seg = _grid(3)
    truth = 9
    for label_, fn, dep in ARMS:
        if not available(dep) or fn is arm_refuse_all:
            continue
        got = fn(seg)
        assert got == truth, "%s gave %r, not %d on grid(3)" % (label_, got, truth)
    assert arm_refuse_all(seg) is None
    assert len(_grid(3)) == 24 and len(_grid(2)) == 12
    mod, name = load_corpus()
    assert mod is not None, "no corpus module"
    d = list(draws(mod, 1, (1e-6,)))
    assert 0 < len(d) <= len(mod.FAMILIES)
    assert d[0][3].shape[1:] == (2, 2)
    print("bench.py self-check OK (corpus: %s, %d families)" % (name, len(mod.FAMILIES)))


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        sys.exit(main())
