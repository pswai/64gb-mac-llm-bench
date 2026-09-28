#!/usr/bin/env python3
"""Recompute the README headline tables from the result CSVs and compare.

Each README row is identified by (date, GPU-limit text, flags text); the
expected numbers are the per-frontier medians of the listed valid runs at
2K/16K/32K/64K, formatted like summarize.py (prefill 1 dp, gen 2 dp).
Also checks the first-token table. Exit 1 on any mismatch.

  python3 scripts/verify_readme.py
"""
import csv, json, os, re, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "results", "2026-09-28")
FRONTIERS = ["2048", "16384", "32768", "65536"]

ROWS = [  # README row match strings -> valid runs
    (("default (51.84 GiB)", "`--prefill-chunk 2048`"),
     ["2008-default-limit/qwen-chunk2048-r1", "2008-default-limit/qwen-chunk2048-r2", "2008-default-limit/qwen-chunk2048-r3"]),
    (("default (51.84 GiB)", "1 probe run"), ["2008-default-limit/qwen-default-r1"]),
    (("resident", "none (official command)"),
     ["1115-main/qwen-default-r1", "1115-main/qwen-default-r2", "1115-main/qwen-default-r3"]),
    (("resident", "`--prefill-chunk 2048`"), ["1115-main/qwen-chunk2048-r1", "1115-main/qwen-chunk2048-r2"]),
    (("streamed from SSD", "`--ssd-streaming`"),
     ["1115-main/dsf-stream-r1", "1115-main/dsf-stream-r2", "1507-replacement/dsf-stream-r1"]),
]

def medians(runs, key, nd):
    data = [{r["ctx_tokens"]: float(r[key]) for r in csv.DictReader(open(os.path.join(D, x + ".csv")))} for x in runs]
    return [f"{statistics.median(d[f] for d in data):.{nd}f}" for f in FRONTIERS]

readme = open(os.path.join(ROOT, "README.md")).read().splitlines()
bad = 0
for (a, b), runs in ROWS:
    lines = [l for l in readme if l.startswith("| 2026-09-28") and a in l and b in l]
    if len(lines) != 1:
        print(f"FAIL row {a!r}/{b!r}: found {len(lines)} lines"); bad += 1; continue
    cells = [c.strip() for c in lines[0].strip("|").split("|")]
    want_p, want_g = " / ".join(medians(runs, "prefill_tps", 1)), " / ".join(medians(runs, "gen_tps", 2))
    ok = cells[-2] == want_p and cells[-1] == want_g
    bad += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {a} | {b}: prefill {cells[-2]} (want {want_p}); gen {cells[-1]} (want {want_g})")

recs = [json.loads(l) for l in open(os.path.join(D, "1115-main", "ttft.jsonl")) if l.strip()]
for model, key in (("Qwen3.8", "qwen-default"), ("DeepSeek", "dsf-stream")):
    want = [f"{statistics.median(r['start_to_first_token_s'] for r in recs if r['label'].startswith(f'{key}-{k}-')):.1f} s"
            for k in ("cold", "warm")]
    line = [l for l in readme if l.startswith("| 2026-09-28") and model in l and l.rstrip().endswith("s |")]
    ok = len(line) == 1 and [c.strip() for c in line[0].strip("|").split("|")][-2:] == want
    bad += not ok
    print(f"{'ok  ' if ok else 'FAIL'} first token {model}: want cold/warm {want}")
print("ALL OK" if not bad else f"{bad} MISMATCH(ES)")
sys.exit(1 if bad else 0)
