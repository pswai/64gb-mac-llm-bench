#!/usr/bin/env python3
"""Summarize server_ab.py startups.jsonl: per block/arm/slot medians and ranges of prefill, decode and
request wall; deltas vs a reference arm; '*' = per-arm ranges don't overlap (separate). Text identity per slot.
  python3 summarize_server_ab.py RUN_DIR/server-ab [PAIRS]   PAIRS like 'B:A,D:A,D:B' (default)"""
import json, statistics as st, sys
d = sys.argv[1]; pairs = [p.split(":") for p in (sys.argv[2] if len(sys.argv) > 2 else "B:A,D:A,D:B").split(",")]
recs = [json.loads(l) for l in open(f"{d}/startups.jsonl") if l.strip()]
valid = [r for r in recs if r["valid"]]
print(f"startups: {len(recs)}, valid {len(valid)}; max swap-in pages {max(r['swapin_pages'] for r in recs)}")
slots = ["short1", "short2", "deep"]
def vals(block, arm, slot, key):
    return [q[key] for r in valid if r["block"] == block and r["arm"] == arm for q in r["requests"] if q["slot"] == slot]
for block in dict.fromkeys(r["block"] for r in valid):
    arms = sorted({r["arm"] for r in valid if r["block"] == block})
    counts = ", ".join(f"{a}={sum(r['arm'] == a and r['block'] == block for r in valid)}" for a in arms)
    print(f"\n## {block}  (startups {counts})")
    for slot in slots:
        pt = sorted(set(vals(block, arms[0], slot, "prompt_tokens")))
        print(f"  {slot} (prompt tokens {pt}):")
        for key, lab in (("prefill_avg", "prefill t/s"), ("decode_avg", "decode t/s"), ("wall_s", "wall s")):
            line = "    " + f"{lab:12}" + "  ".join(
                f"{a} {st.median(vals(block, a, slot, key)):.2f} [{min(vals(block, a, slot, key)):.2f}-{max(vals(block, a, slot, key)):.2f}]"
                for a in arms)
            for x, y in pairs:
                if x in arms and y in arms:
                    vx, vy = vals(block, x, slot, key), vals(block, y, slot, key)
                    dlt = (st.median(vx) / st.median(vy) - 1) * 100
                    sep = max(vx) < min(vy) or min(vx) > max(vy)
                    line += f" | {x} vs {y} {dlt:+.2f}%{'*' if sep else ''}"
            print(line)
        texts = {a: sorted(set(vals(block, a, slot, "text_sha256"))) for a in arms}
        print("    text: " + "  ".join(f"{a}={'/'.join(t)}" for a, t in texts.items()))
