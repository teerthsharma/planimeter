"""Real data: SVG files this repository did not write, and what happens to them.

    python realdata.py fetch [--set icons|plans|all]
    python realdata.py run   [--set ...] [--limit N] [--raster-stride N]
                             [--max-vertices N] [--json OUT]

Two sets, both public, both fetched by a pinned recipe rather than curated file
by file, because a corpus somebody picked one file at a time is a corpus
somebody could have picked to win:

  icons  three MIT icon packages from the npm registry, exact versions pinned
         below. 13,681 files of ordinary hand- and tool-drawn SVG: strokes,
         arcs, cubics, transforms. Small and permissively licensed, so 30 of
         them are committed under `corpus/real/sample/` with their upstream
         LICENSE files, and the whole set is one `fetch` away.

  plans  floor plans and site plans from Wikimedia Commons, by fixed search
         terms. This is the tool's own advertised use case, and the licences are
         CC BY-SA and friends, so nothing here is committed - the recipe is, and
         `_meta.json` records the per-file licence next to the download.

Neither set carries a ground truth, and neither is treated as if it did. Two
second methods run on every stride-th answered file instead, both from
`bench.py`: skimage `euler_number` on ink at 4096 px, a different library
reading a different representation, and the round-to-six-decimals snap plus a
union-find that the synthetic benchmark carries as its strawman. Where either
disagrees with the arrangement the disagreement is printed as its own row.
Raster disagreement is the arrangement-faces-versus-rendered-regions seam;
round-6 disagreement is the snap radius changing the integer on a file nobody
here drew. Neither row is a scoreboard.

The refusal rate is the headline this file exists to publish. It is reported per
set, broken out by reason and by kind, and never summed with the synthetic
jitter stratum's rate - those are two different questions with two different
fixes.

Self-check:  python realdata.py --selfcheck
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import pathlib
import statistics
import sys
import tarfile
import time
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REAL = HERE / "corpus" / "real"
SAMPLE = REAL / "sample"
UA = {"User-Agent": "planimeter-realdata/0.1"}

# Pinned. A floating "latest" would make every number here unreproducible.
NPM = [
    ("tabler", "@tabler/icons", "3.46.0", "MIT"),
    ("feather", "feather-icons", "4.29.2", "MIT"),
    ("bootstrap", "bootstrap-icons", "1.13.1", "MIT"),
]
# Commons full-text search, files only, SVG only. Fixed terms, fixed order.
COMMONS_QUERIES = ("floor plan", "site plan", "church plan", "castle plan")
COMMONS_PER_QUERY = 25

# How many files per package go into the committed sample. The choice is a rule
# - sorted names, every kth - so the same pinned versions give the same 30 files.
SAMPLE_PER_SET = 10
# A sprite sheet is a real file and the fetched sets keep theirs; the committed
# sample skips anything above this so the repository does not carry a megabyte
# of one file. `fetch` is how you get the sprites.
SAMPLE_MAX_BYTES = 32_768

RULE = "=" * 78


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------

def _get(url: str, timeout: int = 120, tries: int = 4) -> bytes:
    last = None
    for a in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as exc:                                  # pragma: no cover
            last = exc
            print("  retry %d: %s" % (a, exc))
            time.sleep(3)
    raise SystemExit("unreachable: %s (%s)" % (url, last))


def fetch_icons(out: pathlib.Path) -> None:
    for name, pkg, version, licence in NPM:
        d = out / name
        if d.exists() and any(d.rglob("*.svg")):
            print("  %-10s already present" % name)
            continue
        url = "https://registry.npmjs.org/%s/-/%s-%s.tgz" % (
            pkg, pkg.split("/")[-1], version)
        t = tarfile.open(fileobj=io.BytesIO(_get(url)))
        n = 0
        for m in t.getmembers():
            rel = pathlib.Path(m.name).relative_to("package")
            if m.name.endswith(".svg") or rel.name in ("LICENSE", "LICENSE.md"):
                p = d / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(t.extractfile(m).read())
                n += m.name.endswith(".svg")
        (d / "_meta.json").write_text(json.dumps(
            {"package": pkg, "version": version, "licence": licence,
             "url": url, "files": n}, indent=1), encoding="utf-8")
        print("  %-10s %s %s  %d svg  (%s)" % (name, pkg, version, n, licence))


def _commons(**kw):
    kw.setdefault("format", "json")
    kw.setdefault("action", "query")
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(kw)
    return json.loads(_get(u, timeout=60).decode("utf-8"))


def fetch_plans(out: pathlib.Path) -> None:
    d = out / "commons"
    d.mkdir(parents=True, exist_ok=True)
    titles = []
    for q in COMMONS_QUERIES:
        r = _commons(list="search", srsearch="filetype:drawing " + q,
                     srnamespace=6, srlimit=COMMONS_PER_QUERY)
        titles += [m["title"] for m in r["query"]["search"]
                   if m["title"].lower().endswith(".svg")]
    titles = sorted(set(titles))
    meta = {}
    for i in range(0, len(titles), 10):
        r = _commons(prop="imageinfo", titles="|".join(titles[i:i + 10]),
                     iiprop="url|size|extmetadata")
        for p in r["query"]["pages"].values():
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii:
                continue
            em = ii.get("extmetadata", {})
            meta[p["title"]] = {
                "url": ii["url"], "size": ii.get("size"),
                "licence": em.get("LicenseShortName", {}).get("value"),
            }
        time.sleep(0.5)
    n = 0
    for t, m in sorted(meta.items()):
        p = d / t[5:].replace(" ", "_")
        if not p.exists():
            p.write_bytes(_get(m["url"], timeout=60))
            time.sleep(0.3)
        n += 1
    (d / "_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("  commons   %d files, licences %s"
          % (n, dict(collections.Counter(m["licence"] for m in meta.values()))))
    print("  NOT COMMITTED: share-alike licences and 29 MB. The recipe above is.")


def make_sample() -> None:
    """Refresh `corpus/real/sample/` from a fetched icon set."""
    SAMPLE.mkdir(parents=True, exist_ok=True)
    for name, _pkg, _version, _licence in NPM:
        d = REAL / "icons" / name
        files = [f for f in sorted(d.rglob("*.svg"))
                 if f.stat().st_size <= SAMPLE_MAX_BYTES]
        if not files:
            print("  %s not fetched; run `python realdata.py fetch` first" % name)
            continue
        step = max(1, len(files) // SAMPLE_PER_SET)
        for f in files[::step][:SAMPLE_PER_SET]:
            (SAMPLE / ("%s__%s" % (name, f.name))).write_bytes(f.read_bytes())
        for lic in ("LICENSE", "LICENSE.md"):
            if (d / lic).exists():
                (SAMPLE / ("LICENSE-%s.txt" % name)).write_bytes((d / lic).read_bytes())
        print("  %-10s %d of %d files sampled" % (name, SAMPLE_PER_SET, len(files)))


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def run_set(name: str, root: pathlib.Path, limit=None, raster_stride: int = 4,
            raster_px: int = 4096, max_vertices=None) -> dict:
    import planimeter
    from planimeter.result import Chi, KIND_OF, PlanimeterParseError

    files = sorted(p for p in root.rglob("*.svg"))
    if limit and limit < len(files):
        # every kth file, not the first k: the sets are sorted by package and a
        # prefix would report one package's numbers under three packages' name.
        files = files[::len(files) // limit][:limit]
    if not files:
        print("%s: NOT RUN - nothing under %s (python realdata.py fetch)" % (name, root))
        return {"set": name, "n": 0, "status": "NOT RUN"}

    tally = collections.Counter()
    kinds = collections.Counter()
    secs, rows, unreadable = [], [], []
    for f in files:
        t0 = time.time()
        try:
            r = planimeter.chi(f, max_vertices=max_vertices)
        except (PlanimeterParseError, OSError) as exc:      # typed, still a failure
            tally["UNREADABLE"] += 1
            unreadable.append((f.name, "%s: %s" % (type(exc).__name__, exc)))
            continue
        el = time.time() - t0
        secs.append(el)
        if isinstance(r, Chi):
            tally["CERTIFIED"] += 1
            rows.append({"file": f.name, "verdict": "CERTIFIED", "v": r.v, "e": r.e,
                         "pieces": r.pieces, "faces": r.faces, "chi": r.chi,
                         "radius": r.radius, "secs": el, "path": str(f)})
        else:
            tally[r.reason] += 1
            kinds[KIND_OF.get(r.reason, "input")] += 1
            rows.append({"file": f.name, "verdict": "REFUSED", "reason": r.reason,
                         "kind": KIND_OF.get(r.reason, "input"), "secs": el,
                         "detail": r.detail[:120]})

    n = len(files)
    answered = tally["CERTIFIED"]
    print(RULE)
    print("  %s   %d files   %s   max_vertices %s"
          % (name, n, root, max_vertices if max_vertices else "default"))
    print(RULE)
    print("  answered           %4d  %5.1f%%" % (answered, 100.0 * answered / n))
    print("  refused            %4d  %5.1f%%" % (n - answered,
                                                 100.0 * (n - answered) / n))
    for reason, k in tally.most_common():
        if reason == "CERTIFIED":
            continue
        print("    %-22s %4d  %5.1f%%   %s"
              % (reason, k, 100.0 * k / n, KIND_OF.get(reason, "input")))
    for f, why in unreadable[:5]:
        print("    ! %-40.40s %s" % (f, why[:60]))
    if secs:
        print("  wall clock         median %.0f ms   p95 %.0f ms   max %.1f s"
              % (1000 * statistics.median(secs),
                 1000 * sorted(secs)[min(len(secs) - 1, int(0.95 * len(secs)))],
                 max(secs)))

    control = _raster_control(rows, raster_stride, raster_px)
    return {"set": name, "n": n, "root": str(root), "answered": answered,
            "max_vertices": max_vertices,
            "tally": dict(tally), "kinds": dict(kinds),
            "median_secs": statistics.median(secs) if secs else None,
            "control": control, "rows": rows}


def _raster_control(rows, stride: int, px: int) -> dict:
    """Two controls on the same parse, on every stride-th answered file.

    `skimage.euler_number` on ink at `px`: a different library, a different
    representation, and the same function the synthetic benchmark scores. It
    needs a resolution and planimeter does not, which is why both are printed
    instead of one being called truth.

    `bench.arm_round6`: the round-to-six-decimals snap plus a union-find, run on
    the same segments. Neither is truth either. What the disagreement rate
    measures is how often the choice of snap radius changes the integer on a
    file nobody here drew - which is the question the synthetic jitter stratum
    answers by construction and cannot answer for real input.
    """
    try:
        import bench
        import skimage                                            # noqa: F401
    except Exception as exc:
        print("  raster control     NOT RUN (%s)" % exc)
        return {"status": "NOT RUN", "why": str(exc)}
    from planimeter.read import segments

    certified = [r for r in rows if r["verdict"] == "CERTIFIED"]
    done = agree = r6_agree = 0
    disagree, r6_disagree = [], []
    for row in certified[::stride]:
        seg = segments(row["path"]).seg
        faces = bench._raster(seg, px)
        done += 1
        if faces == row["faces"]:
            agree += 1
        else:
            disagree.append((row["file"], "raster %d vs arrangement %d"
                             % (faces, row["faces"])))
        r6 = bench.arm_round6(seg)
        if r6 == row["faces"]:
            r6_agree += 1
        else:
            r6_disagree.append((row["file"], "round-6 %d vs arrangement %d"
                                % (r6, row["faces"])))
    if not done:
        print("  raster control     NOT RUN (no certified file in the stride)")
        return {"status": "NOT RUN", "checked": 0}
    print("  raster @ %d px    %d of %d certified checked (stride %d): "
          "%d agree, %d disagree"
          % (px, done, len(certified), stride, agree, len(disagree)))
    for f, why in disagree[:6]:
        print("    ~ %-40.40s %s" % (f, why))
    print("  round-6 control    %d of %d certified checked (stride %d): "
          "%d agree, %d disagree" % (done, len(certified), stride,
                                     r6_agree, len(r6_disagree)))
    for f, why in r6_disagree[:6]:
        print("    ~ %-40.40s %s" % (f, why))
    return {"status": "ok", "px": px, "stride": stride, "checked": done,
            "agree": agree, "disagree": len(disagree),
            "sites": [{"file": f, "why": w} for f, w in disagree],
            "round6_agree": r6_agree, "round6_disagree": len(r6_disagree),
            "round6_sites": [{"file": f, "why": w} for f, w in r6_disagree]}


SETS = {"sample": SAMPLE, "icons": REAL / "icons", "plans": REAL / "commons"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["fetch", "run", "sample"])
    ap.add_argument("--set", default="all", help="sample | icons | plans | all")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--raster-stride", type=int, default=4,
                    help="the control runs on every Nth answered file; the "
                         "denominator is printed with the row")
    ap.add_argument("--raster-px", type=int, default=4096)
    ap.add_argument("--max-vertices", type=int, default=None,
                    help="the ceiling every file in the run is given; printed "
                         "with the header, because the refusal rate is a "
                         "statement about a ceiling, not about the set")
    ap.add_argument("--json", default=None, metavar="OUT")
    a = ap.parse_args(argv)

    if a.command == "fetch":
        REAL.mkdir(parents=True, exist_ok=True)
        if a.set in ("all", "icons"):
            fetch_icons(REAL / "icons")
        if a.set in ("all", "plans"):
            fetch_plans(REAL)
        return 0
    if a.command == "sample":
        make_sample()
        return 0

    want = [k for k in ("sample", "icons", "plans") if a.set in ("all", k)] or [a.set]
    out = []
    for k in want:
        out.append(run_set(k, SETS[k], limit=a.limit,
                           raster_stride=a.raster_stride, raster_px=a.raster_px,
                           max_vertices=a.max_vertices))
        print("")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote %s" % a.json)
    return 0


def _selfcheck() -> None:
    assert SAMPLE_PER_SET * len(NPM) == 30
    assert all(v.count(".") == 2 for _, _, v, _ in NPM), "versions are pinned exactly"
    assert set(SETS) == {"sample", "icons", "plans"}
    print("realdata selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        sys.exit(main())
