#!/usr/bin/env python3
"""Head vs base per frontier from run-bench.sh output: medians over valid runs, delta, 'separate' when
the arms' min-max ranges don't overlap. Optional REF_DIR: base reproducibility vs an earlier base.
  python3 compare_sweep.py SWEEP_DIR [REF_SWEEP_DIR]"""
import csv, glob, os, statistics as st, sys
def runs(d, cfg):
    ok = {l.split("\t")[0] for l in open(f"{d}/runs.tsv") if l.split("\t")[1] == "0" and l.split("\t")[3] == "32"
          and int(l.split("\t")[4]) * 16 / 1024 <= 100}
    out = []
    for f in sorted(glob.glob(f"{d}/{cfg}-r*.csv")):
        if os.path.basename(f)[:-4] in ok:
            out.append({int(r["ctx_tokens"]): r for r in csv.DictReader(open(f))})
    return out
def table(d, cfg):
    rs = runs(d, cfg); ctxs = sorted(rs[0])
    return len(rs), {c: {k: [float(r[c][k]) for r in rs] for k in ("prefill_tps", "gen_tps")} for c in ctxs}
d = sys.argv[1]
nb, base = table(d, "base-chunk2048"); nh, head = table(d, "head-chunk2048")
print(f"valid runs: base {nb}, head {nh}")
summ = {}
for k in ("gen_tps", "prefill_tps"):
    ds, sep = [], 0
    for c in base:
        b, h = base[c][k], head[c][k]
        ds.append((st.median(h) / st.median(b) - 1) * 100)
        sep += max(b) < min(h) or min(b) > max(h)
    summ[k] = (min(ds), max(ds), st.median(ds), sep, len(ds))
    print(f"{k}: {min(ds):+.2f}..{max(ds):+.2f}% (median {st.median(ds):+.2f}%), separate {sep}/{len(ds)}")
print("\n| ctx | base prefill / gen | head prefill / gen | Δ prefill | Δ gen |\n| ---: | ---: | ---: | ---: | ---: |")
for c in (2048, 16384, 32768, 65536):
    bp, bg, hp, hg = (st.median(x[c][k]) for x in (base, head) for k in ("prefill_tps", "gen_tps"))
    print(f"| {c} | {bp:.1f} / {bg:.2f} | {hp:.1f} / {hg:.2f} | {(hp/bp-1)*100:+.2f}% | {(hg/bg-1)*100:+.2f}% |")
if len(sys.argv) > 2:
    _, ref = table(sys.argv[2], "base-chunk2048"); _, refh = table(sys.argv[2], "head-chunk2048")
    for lab, cur, old in (("base vs earlier base", base, ref), ("head vs earlier head", head, refh)):
        for k in ("prefill_tps", "gen_tps"):
            ds = [(st.median(cur[c][k]) / st.median(old[c][k]) - 1) * 100 for c in cur]
            print(f"{lab} {k}: {min(ds):+.2f}..{max(ds):+.2f}% (median {st.median(ds):+.2f}%, max |d| {max(abs(x) for x in ds):.2f}%)")
