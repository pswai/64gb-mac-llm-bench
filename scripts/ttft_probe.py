#!/usr/bin/env python3
"""Time process start -> first generated token for one ds4-bench frontier.

Runs `ds4-bench ... --ctx-start N --ctx-max N --gen-tokens 1 --csv /dev/stdout`.
ds4-bench flushes the CSV row right after the first generated token, so the
arrival time of the data row is process start + load + prefill + first token.
Appends one JSON line per run. Not part of the official ds4-bench format.
"""
import argparse, json, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument("--label", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("cmd", nargs=argparse.REMAINDER)
a = ap.parse_args()
cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd

t0 = time.monotonic()
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
header, row, t_row = None, None, None
for line in p.stdout:
    line = line.strip()
    if line.startswith("ctx_tokens"):
        header = line.split(",")
    elif header and line and line[0].isdigit():
        row, t_row = dict(zip(header, line.split(","))), time.monotonic()
rc = p.wait()
t_exit = time.monotonic()

rec = {"label": a.label, "rc": rc, "exit_s": round(t_exit - t0, 3)}
if row:
    prefill_s = int(row["prefill_tokens"]) / float(row["prefill_tps"])
    first_s = float(row["gen_first_ms"]) / 1000.0
    rec.update({
        "start_to_first_token_s": round(t_row - t0, 3),
        "prefill_tokens": int(row["prefill_tokens"]),
        "prefill_s": round(prefill_s, 3),
        "gen_first_ms": float(row["gen_first_ms"]),
        # derived: everything before prefill (load, tokenize, allocate, warm)
        "load_s_derived": round(t_row - t0 - prefill_s - first_s, 3),
    })
with open(a.out, "a") as f:
    f.write(json.dumps(rec) + "\n")
print(json.dumps(rec), file=sys.stderr)
sys.exit(rc)
