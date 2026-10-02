#!/usr/bin/env python3
"""Compare the retest correctness artefacts. Exit 1 only if head differs from ref-on or ref-off
(or from its own repeat) anywhere: the pre-registered stop condition. Head vs base is reported only."""
import hashlib, json, re, os, sys
d = sys.argv[1]; prompts = ["rome-short", "roma575", "sposi-long"]
def nums(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool): yield float(x)
    elif isinstance(x, dict):
        for k in sorted(x): yield from nums(x[k])
    elif isinstance(x, list):
        for v in x: yield from nums(v)
def jd(a, b):
    try: na, nb = list(nums(json.load(open(a)))), list(nums(json.load(open(b))))
    except Exception as e: return None, f"unreadable ({e.__class__.__name__})"
    if len(na) != len(nb): return None, f"length {len(na)} vs {len(nb)}"
    m = max((abs(x - y) for x, y in zip(na, nb)), default=0.0); return m, f"max|d|={m:.9g} over {len(na)}"
def th(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
gate_bad = 0
for p in prompts:
    print(f"== {p}")
    for other in ("ref-on", "ref-off", "head.rep", "base"):
        gate = other != "base"
        res = []
        for kind in ("logits", "logprobs"):
            m, s = jd(f"{d}/{p}.head.{kind}.json", f"{d}/{p}.{other}.{kind}.json")
            ok = m == 0.0; res.append(ok)
            print(f"  head vs {other:8} {kind:8}: {s}{'' if ok else '   <-- DIFFERENT'}")
        for kind in ("text", "mtptext"):
            a, b = th(f"{d}/{p}.head.{kind}.out"), th(f"{d}/{p}.{other}.{kind}.out")
            ok = a == b; res.append(ok)
            print(f"  head vs {other:8} {kind:8}: {a} vs {b}{'' if ok else '   <-- DIFFERENT'}")
        if gate and not all(res): gate_bad += 1
    for arm in ("head", "ref-on", "ref-off", "base"):
        sites = set()
        for f in os.listdir(d):
            if f.startswith(f"{p}.{arm}.") and f.endswith(".err"):
                sites |= set(re.findall(r"DS4_METAL_M1MAX_TUNING applied: (\w+)", open(f"{d}/{f}", errors="replace").read()))
        if sites: print(f"  ref-patch forced sites logged ({arm}): {', '.join(sorted(sites))}")
print("GATE (head vs ref-on/ref-off/head.rep): " + ("IDENTICAL" if not gate_bad else f"{gate_bad} prompt(s) DIFFERENT -> stop before speed tests"))
sys.exit(1 if gate_bad else 0)
