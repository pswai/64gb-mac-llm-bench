#!/usr/bin/env python3
"""Compare flag-off vs flag-on correctness artefacts written by correctness.sh.

For each prompt: max |delta| over every number in the logits / logprobs JSON,
and byte identity of generated text (MTP off and on). Also checks off vs
off.rep (run-to-run determinism) and lists which forced sites logged.
Exit 1 if any off-vs-on difference is found.
"""
import hashlib, json, os, re, sys

d = sys.argv[1]
prompts = ["rome-short", "roma575", "sposi-long"]

def numbers(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool): yield float(x)
    elif isinstance(x, dict):
        for k in sorted(x): yield from numbers(x[k])
    elif isinstance(x, list):
        for v in x: yield from numbers(v)

def maxdiff(a, b):
    try:
        na, nb = list(numbers(json.load(open(a)))), list(numbers(json.load(open(b))))
    except Exception as e:
        return f"unreadable ({e.__class__.__name__})"
    if len(na) != len(nb): return f"length {len(na)} vs {len(nb)}"
    return max((abs(x - y) for x, y in zip(na, nb)), default=0.0), len(na)

def text(p):
    raw = open(p, "rb").read()
    return hashlib.sha256(raw).hexdigest()[:16], len(raw)

bad = 0
for p in prompts:
    print(f"== {p}")
    for kind in ("logits", "logprobs"):
        for a, b in (("off", "on"), ("off", "off.rep"), ("on", "on.rep")):
            r = maxdiff(f"{d}/{p}.{a}.{kind}.json", f"{d}/{p}.{b}.{kind}.json")
            ok = isinstance(r, tuple) and r[0] == 0.0
            if (a, b) == ("off", "on") and not ok: bad += 1
            print(f"  {kind:8} {a:>3} vs {b:<7}: " + (f"max|d|={r[0]:.9g} over {r[1]} values" if isinstance(r, tuple) else r) + ("" if ok else "   <-- DIFFERENT"))
    for kind in ("text", "mtptext"):
        s = {arm: text(f"{d}/{p}.{arm}.{kind}.out") for arm in ("off", "on", "off.rep", "on.rep")}
        same = s["off"] == s["on"]
        if not same: bad += 1
        print(f"  {kind:8} sha off/on/off.rep/on.rep: {' '.join(v[0] for v in s.values())}" + ("" if same else "   <-- DIFFERENT"))
    for arm in ("off", "on"):
        sites = set()
        for f in os.listdir(d):
            if f.startswith(f"{p}.{arm}.") and f.endswith(".err"):
                sites |= set(re.findall(r"DS4_METAL_M1MAX_TUNING applied: (\w+)", open(f"{d}/{f}", errors="replace").read()))
        print(f"  forced sites logged ({arm}): {', '.join(sorted(sites)) or 'none'}")
print("CORRECTNESS: IDENTICAL" if not bad else f"CORRECTNESS: {bad} DIFFERENCE(S) off vs on")
sys.exit(1 if bad else 0)
