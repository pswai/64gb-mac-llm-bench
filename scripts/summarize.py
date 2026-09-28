#!/usr/bin/env python3
"""Summarize a run directory from run-bench.sh.

Per config: per-frontier median and min-max over valid reps for prefill t/s,
generation t/s (all 128 tokens, the column upstream plots) and steady t/s.
Also writes, per config, the one unmodified ds4-bench CSV whose mean gen_tps
is the median of the valid reps (candidate for an upstream PR), and the
cold/warm first-token table from ttft.jsonl.

  python3 scripts/summarize.py results/2026-09-28/1115-main results/2026-09-28/1507-replacement > summary.md

Several run directories may be given (e.g. a replacement batch). Runs are
labelled <batch>:rN where batch is the directory name's first dash-separated
part; every valid run from every batch is included. The representative CSVs
are written to the first directory.
"""
import csv, json, os, shutil, statistics, sys

SWAP_INVALID_PAGES = 100 * 1024 // 16   # 100 MiB of 16 KiB pages, same rule as the driver

dirs = sys.argv[1:]
d = dirs[0]
runs = []
for dd in dirs:
    tag = os.path.basename(dd.rstrip("/")).split("-")[0]   # e.g. "1115" from "1115-main"
    with open(os.path.join(dd, "runs.tsv")) as f:
        for line in f:
            rid, rc, wall, rows, swapin, t = line.rstrip("\n").split("\t")
            cfg, rep = rid.rsplit("-r", 1)
            valid = rc == "0" and rows == "32" and int(swapin) <= SWAP_INVALID_PAGES
            runs.append(dict(id=f"{tag}:{rid}", path=os.path.join(dd, rid + ".csv"), cfg=cfg,
                             rep=f"{tag}:r{rep}", rc=int(rc), wall=int(wall), rows=int(rows),
                             swapin_pages=int(swapin), end=t, valid=valid))

def load(r):
    with open(r["path"]) as f:
        return list(csv.DictReader(f))

def fmt(xs, nd=1):
    if not xs:
        return "—"
    m = statistics.median(xs)
    return f"{m:.{nd}f} ({min(xs):.{nd}f}–{max(xs):.{nd}f})" if len(xs) > 1 else f"{m:.{nd}f}"

print(f"# Summary of {os.path.basename(d.rstrip('/'))}\n")
print("## Runs\n")
print("| run | rc | wall s | rows | swap-in MiB | valid |")
print("|---|---:|---:|---:|---:|---|")
for r in runs:
    print(f"| {r['id']} | {r['rc']} | {r['wall']} | {r['rows']} | {r['swapin_pages']*16/1024:.1f} | {'yes' if r['valid'] else 'NO'} |")

for cfg in dict.fromkeys(r["cfg"] for r in runs):
    good = [r for r in runs if r["cfg"] == cfg and r["valid"]]
    if not good:
        continue
    data = {r["rep"]: load(r) for r in good}
    paths = {r["rep"]: r["path"] for r in good}
    reps = sorted(data)
    print(f"\n## {cfg}: {len(reps)} valid reps ({', '.join(reps)}); median (min–max)\n")
    print("| ctx | prefill t/s | gen t/s | gen steady t/s | first-token ms | " +
          " | ".join(f"{x} prefill / gen" for x in reps) + " |")
    print("|---:|---:|---:|---:|---:|" + "---:|" * len(reps))
    for i, row in enumerate(data[reps[0]]):
        col = lambda k: [float(data[x][i][k]) for x in reps]
        per = " | ".join(f"{float(data[x][i]['prefill_tps']):.1f} / {float(data[x][i]['gen_tps']):.2f}" for x in reps)
        print(f"| {row['ctx_tokens']} | {fmt(col('prefill_tps'))} | {fmt(col('gen_tps'), 2)} | "
              f"{fmt(col('gen_steady_tps'), 2)} | {fmt(col('gen_first_ms'), 0)} | {per} |")
    # Representative = valid run closest to the per-frontier medians of prefill
    # and generation (sum of squared relative deviations). Rule adopted after a
    # first rule (median of mean gen t/s) picked the dsf-stream run with a
    # one-off prefill drop; see README.
    n = len(data[reps[0]])
    med = {k: [statistics.median(float(data[x][i][k]) for x in reps) for i in range(n)]
           for k in ("prefill_tps", "gen_tps")}
    dist = {x: sum((float(data[x][i][k]) / med[k][i] - 1) ** 2
                   for i in range(n) for k in ("prefill_tps", "gen_tps")) for x in reps}
    pick = min(reps, key=lambda x: dist[x])
    shutil.copyfile(paths[pick], os.path.join(d, f"representative-{cfg}.csv"))
    print(f"\nRepresentative unmodified run (closest to per-frontier medians): {pick} -> "
          f"representative-{cfg}.csv; distances " + ", ".join(f"{x} {dist[x]:.4f}" for x in reps))

tt = os.path.join(d, "ttft.jsonl")
if os.path.exists(tt):
    recs = [json.loads(l) for l in open(tt) if l.strip()]
    print("\n## Process start → first token (2,048-token prompt; NOT the official format)\n")
    print("| model | cache | n | start→first token s | derived load s | prefill s | first-token ms |")
    print("|---|---|---:|---:|---:|---:|---:|")
    groups = {}
    for r in recs:
        if r.get("rc") != 0 or "start_to_first_token_s" not in r:
            continue
        cfg, kind, _ = r["label"].rsplit("-", 2)
        groups.setdefault((cfg, kind), []).append(r)
    for (cfg, kind), rs in sorted(groups.items()):
        g = lambda k: [x[k] for x in rs]
        print(f"| {cfg} | {kind} | {len(rs)} | {fmt(g('start_to_first_token_s'), 1)} | "
              f"{fmt(g('load_s_derived'), 1)} | {fmt(g('prefill_s'), 1)} | {fmt(g('gen_first_ms'), 0)} |")
    bad = [r["label"] for r in recs if r.get("rc") != 0 or "start_to_first_token_s" not in r]
    if bad:
        print(f"\nFailed probes: {', '.join(bad)}")
