#!/usr/bin/env python3
"""Server A/B for antirez/ds4#1056 on the owner's daily ds4-server flags.

Per startup: one excluded warmup, then 2 short requests (~3.5K prompt tokens,
800 generated) and 1 deep request (~32K prompt tokens, 400 generated). Every
prompt starts with a unique nonce so nothing hits the prefix cache. Metrics
come from the server's own log lines (prefill avg, decoding avg) plus request
wall time and usage counts. The machine must already be quiet (the window
script does that); this script only ever talks to its own port.

  python3 server_ab.py --out RUN_DIR --base DIR --pr DIR --model GGUF --mmproj GGUF --text FILE
"""
import argparse, hashlib, json, os, re, shutil, signal, subprocess, sys, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--base", required=True)
ap.add_argument("--pr", required=True)
ap.add_argument("--model", required=True)
ap.add_argument("--mmproj", required=True)
ap.add_argument("--text", required=True, help="source text, e.g. speed-bench/promessi_sposi.txt")
ap.add_argument("--port", type=int, default=8099)
ap.add_argument("--kv-root", required=True, help="parent for fresh per-startup KV dirs (deleted after)")
ap.add_argument("--cooldown", type=int, default=60)
ap.add_argument("--short-chars", type=int, default=12500)   # calibrated at warmup; see log
ap.add_argument("--deep-chars", type=int, default=118000)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
TEXT = open(a.text, encoding="utf-8-sig").read()
SWAP_INVALID_PAGES = 100 * 1024 // 16
BASE_ENV = {"DS4_QWEN4_PREFILL_CHUNK": "1024"}
ARMS = {"A": (a.base, {}), "B": (a.pr, {}), "C": (a.pr, {"DS4_QWEN4_MTP_PREFILL": "off"})}
BLOCKS = [("mtp-off", ["A", "B", "B", "A"], False), ("mtp-on", ["A", "B", "C", "C", "B", "A"], True)]
# Fixed text slices per request slot, identical for every arm and startup; only the
# fixed-length numeric nonce at the start differs (digits tokenize one per digit).
N, D = a.short_chars, a.deep_chars
SLICES = {"warmup": TEXT[0:N], "short1": TEXT[N:2 * N], "short2": TEXT[2 * N:3 * N], "deep": TEXT[3 * N:3 * N + D]}
REQUESTS = [("short", "short1", 800), ("short", "short2", 800), ("deep", "deep", 400)]
nonce = [0]

def log(msg):
    line = f"{time.strftime('%F %T')} {msg}"
    print(line, flush=True)
    open(os.path.join(a.out, "server_ab.log"), "a").write(line + "\n")

def swapins():
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    return int(re.search(r"Swapins:\s+(\d+)", out).group(1))

def prompt(slot):
    nonce[0] += 1
    return f"Sessione {nonce[0]:06d}.\n\n{SLICES[slot]}\n\nContinua il racconto."

def post(body, timeout=1800):
    req = urllib.request.Request(f"http://127.0.0.1:{a.port}/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
        return r.status, data, time.monotonic() - t0

def parse_log(path, start_pos):
    with open(path, errors="replace") as f:
        f.seek(start_pos)
        lines = [l for l in f if "snippet" not in l]
    pre = [(int(m.group(1)), int(m.group(2)), float(m.group(3))) for l in lines
           for m in [re.search(r"prefill chunk (\d+)/(\d+) .*avg=([\d.]+) t/s", l)] if m]
    dec = [float(m.group(1)) for l in lines for m in [re.search(r"decoding .*avg=([\d.]+) t/s", l)] if m]
    fin = [float(m.group(1)) for l in lines for m in [re.search(r"finish=\w+ ([\d.]+)s", l)] if m]
    return {"prefill_avg": max(pre)[2] if pre else None, "prefill_lines": len(pre),
            "decode_avg": dec[-1] if dec else None, "server_total_s": fin[-1] if fin else None}

def one_startup(block, idx, arm, mtp, attempt):
    tag = f"{block}-{idx:02d}-{arm}{'-retry' if attempt else ''}"
    wdir, extra = ARMS[arm]
    env = dict(os.environ, **BASE_ENV, **extra)
    kv = os.path.join(a.kv_root, tag)
    shutil.rmtree(kv, ignore_errors=True); os.makedirs(kv)
    slog = os.path.join(a.out, f"{tag}.server.log")
    cmd = ["./ds4-server", "-m", a.model, "--vision", a.mmproj, "--metal", "-c", "163840",
           "--prefill-chunk", "1024"] + (["--mtp"] if mtp else []) + [
           "--kv-disk-dir", kv, "--kv-disk-space-mb", "16384", "-n", "16384",
           "--host", "127.0.0.1", "--port", str(a.port)]
    si0 = swapins()
    rec = {"tag": tag, "block": block, "arm": arm, "mtp": mtp, "attempt": attempt, "cwd": os.path.basename(wdir),
           "env": {**BASE_ENV, **extra}, "requests": [], "valid": False}
    proc = subprocess.Popen(cmd, cwd=wdir, env=env, stdout=open(slog, "w"), stderr=subprocess.STDOUT)
    t_start = time.monotonic()
    try:
        for _ in range(300):
            if proc.poll() is not None: raise RuntimeError(f"server exited rc={proc.returncode}")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{a.port}/v1/models", timeout=2); break
            except Exception: time.sleep(1)
        else: raise RuntimeError("server not ready in 300 s")
        rec["ready_s"] = round(time.monotonic() - t_start, 1)
        # warmup (excluded)
        post({"model": "qwen3.8-flash-next-chat", "messages": [{"role": "user", "content": prompt("warmup")}],
              "max_tokens": 800, "temperature": 0, "top_p": 1, "ignore_eos": True})
        for kind, slot, ntok in REQUESTS:
            pos = os.path.getsize(slog)
            st, data, wall = post({"model": "qwen3.8-flash-next-chat",
                                   "messages": [{"role": "user", "content": prompt(slot)}],
                                   "max_tokens": ntok, "temperature": 0, "top_p": 1, "ignore_eos": True})
            time.sleep(0.5)
            u = data.get("usage", {})
            txt = data["choices"][0]["message"].get("content") or ""
            r = {"kind": kind, "slot": slot, "status": st, "wall_s": round(wall, 3), "prompt_tokens": u.get("prompt_tokens"),
                 "completion_tokens": u.get("completion_tokens"), "requested": ntok,
                 "text_sha256": hashlib.sha256(txt.encode()).hexdigest()[:16], **parse_log(slog, pos)}
            rec["requests"].append(r)
            log(f"  {tag} {kind}: prompt {r['prompt_tokens']} gen {r['completion_tokens']} "
                f"prefill {r['prefill_avg']} decode {r['decode_avg']} wall {r['wall_s']}s")
    except Exception as e:
        rec["error"] = repr(e); log(f"  {tag} ERROR {e!r}")
    finally:
        proc.send_signal(signal.SIGTERM)
        try: proc.wait(timeout=60)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        shutil.rmtree(kv, ignore_errors=True)
    rec["swapin_pages"] = swapins() - si0
    ok_reqs = len(rec["requests"]) == len(REQUESTS) and all(
        r["status"] == 200 and r["completion_tokens"] == r["requested"] and r["prefill_avg"] and r["decode_avg"]
        for r in rec["requests"])
    rec["valid"] = "error" not in rec and ok_reqs and rec["swapin_pages"] <= SWAP_INVALID_PAGES
    json.dump(rec, open(os.path.join(a.out, "startups.jsonl"), "a")); open(os.path.join(a.out, "startups.jsonl"), "a").write("\n")
    log(f"{tag}: valid={rec['valid']} swapin_pages={rec['swapin_pages']} ready={rec.get('ready_s')}s")
    return rec["valid"]

for block, order, mtp in BLOCKS:
    log(f"block {block}: order {' '.join(order)}")
    failed = []
    for i, arm in enumerate(order, 1):
        if not one_startup(block, i, arm, mtp, 0): failed.append((i, arm))
        time.sleep(a.cooldown)
    fails_per_arm = {}
    for i, arm in failed:   # rule: an invalid startup is re-run once at the end of its block
        ok = one_startup(block, i, arm, mtp, 1)
        time.sleep(a.cooldown)
        if not ok:
            fails_per_arm[arm] = fails_per_arm.get(arm, 0) + 1
            log(f"{block}: {arm} startup {i} failed twice; reported as failed")
log("server A/B done")
