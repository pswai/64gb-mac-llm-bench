# antirez/ds4#1056 at 8d543ec ("Merge antirez/main into qwen-kernel-opt"): plan, fixed 2026-10-13 ~15:45

Written before any model run. Brief: the owner's bench brief (not in this repo).
Promise being kept (our 10-11 PR comment): output identity vs `main`, the same speed sweep, and
`DS4_QWEN4_MTP_PREFILL` `on` vs `auto`, all on this M4 Max 64 GB with Qwen3.8 Q2 resident.

## Arms (built and verified 15:1x; daily server untouched)

| Arm | Worktree | Commit | ds4 / ds4-bench / ds4-server sha256 (16) |
|---|---|---|---|
| head | ~/Dev/ds4-pr1056-8d543ec | 8d543ecc95605e8062aaedd75261f22d557e580d | 8e4edecb8ee912f0 / 8d3270e4f36a0c60 / 8bd2f23ebf5292a9 |
| base | ~/Dev/ds4-bench-fc80bd6 | fc80bd695da76ee14bcb86820bf900a5cdfda806 (`main`) | 7de4a40519c1b1f9 / 00f9e37c5744f88c / 547297ba3ce85cfe |

- **SHAs (verified 10-13 with `git fetch`):** `main` is still `fc80bd6`, and it is the merge base. Head is
  40 ahead and 0 behind, so head *is* the merge result.
- **What is new since our last-tested head `37f66ba`:** only the merge of `main`'s 9 commits
  (`0aaea5a..fc80bd6`: CUDA tensor parallelism, Spark/DSpark, ROCm tests, score API, a server change).
  The PR's own Qwen/Metal code is unchanged.
- **The merge had 2 hand-resolved conflicts in `ds4.c`** (git's auto-merge reports CONFLICT; the
  resolution differs from it by 58 lines):
  - `tp_batched_moe` now uses `ds4_gpu_device_is_m5_or_m6_apple_silicon()` inside main's new
    `tp_batched_backend` block;
  - the PR's `qwen4_ssd` memory admit is kept ahead of main's streaming cache configuration.
  - Neither runs here: the first needs `tp_world == 2`, and the second only fires with
    `--ssd-streaming`. Resident takes main's `else` branch. Read in code, not traced at runtime.
- **Build:** plain `make -j8` (`-O3 -ffast-math -mcpu=native`), Apple clang 21.0.0, 0 warnings, clean
  worktrees. Logs are in `build-*.log`.
- **Machine:** Apple M4 Max, `iogpu.wired_limit_mb` 57344 (raised, as on 10-03).
  - The sudo sysctl rule is present again (it was absent on 10-03). This window **does not change the
    limit**; everything runs at 57344 so the sweep stays comparable with 10-03.

## Model-free tests on head (done, 15:1x, daily server up): 14/15 pass

- **Pass (14):**
  - `test-qwen4-memory`, `test-qwen4-kernels`, `test-qwen4-q2`, `test-qwen4-hc-math`,
    `test-qwen4-ssd-experts`, `test-qwen4-resident-arithmetic`;
  - `test-metal-q8-reduction`, `test-metal-q8-gemv-reference`, `test-metal-qwen4-moe-half`,
    `test-metal-qwen4-hc`, `test-metal-qwen4-moe-mid`, `test-metal-qwen4-moe-down`,
    `test-metal-ssd-reuse`;
  - `test-metal-device-policy` ("Qwen M1 Max/M2-M4 and M5/M6 boundaries passed").
- **Fail (1): `test-qwen4-moe-mm-compact`, rc 2,** at `tests/test_qwen4_moe_mm_compact.py:61`
  (`AssertionError: kernel void kernel_qwen4_moe_mm_mid(`).
  - It is the same failure slycrel reported on 10-10 on the M1 Max and the M6.
  - It's a **stale source scanner**: it still expects 3 template arguments, while `b96a12b` added a
    fourth (`KS`). It reads `.metal` source text, so it isn't hardware-dependent.
  - It's not in `make test`. **Not a blocker;** one line in the draft.
- Logs are in `tests-head/`.

## Window: one back-to-back downtime, owner-approved; restore by 20:15

`window-8d543ec.sh`, hard stop `STOP_AT=20:00`, so the daily server answers 200 well before 20:15.

1. Preflight: disk ≥ 100 GiB, both arms at their SHA and ds4 hash, worktrees clean, limit 57344.
2. Quiet check: load1 ≤ 2.5 and no process ≥ 25% CPU, up to 10 min, else abort with nothing stopped.
3. Wait until the daily server has been idle for 30 s (max 10 min).
4. Hook: pause the scheduled jobs (count-checked) and stop the daily server (launchd); wait for its process to exit.
5. **Stop and wait for the owner's KV cleanup "go"** (I touch `GO` when it replies; abort after 15 min).
6. Start the sampler (thermals and swap-ins every 10 s) and the abort monitor. Then (1) correctness,
   (2) server A/B, (3) sweep.
7. Restore on every exit path, exactly once: test servers killed, hook restore (server and crons),
   then the FINAL line with HTTP code, kv-interval flag, cron count and free disk.

**Codex/ChatGPT:** left open unless the owner says to quit it (`QUIT_CODEX=1`, as on 10-03). If left
open, that's a deviation from 10-03, and the per-run validity rules below catch interference.

**Estimate**, from 10-03's timings:

| Step | Time |
|---|---|
| quiet check + idle wait + stop | 2–12 min |
| correctness (39 runs) | ~5 min |
| server A/B (10 startups × ~3.6 min) | ~36 min |
| sweep, 6 runs × 28.2 min | ~2 h 50 min |
| **total downtime** | **~3 h 35 min** |

Starting by 16:05, the server is back by ~19:45. **The reps rule is fixed now**, at sweep start: if
the full A B B A A B (6 × 29 min) fits before 19:55, REPS = 3. If only A B B A fits, REPS = 2.
Otherwise the sweep is skipped. Replacement runs happen only if whole runs still fit (max 2).

## (1) Correctness (CLI, `correctness-8d543ec.sh`)

**Settings, identical to 09-30 / 10-02 / 10-03:** `--metal --ctx 16384 --prefill-chunk 2048 --temp 0
--nothink`, `DS4_QWEN4_PREFILL_CHUNK=2048`, and the same 3 prompts (sha256-verified copies of 10-03's):
- rome-short (29 tokens);
- roma575 (575);
- sposi-long (5,942).

**Arms:**
- head, base and head.rep: × {first-token logits, 64-step logprobs (MTP off), greedy text 128 MTP off,
  greedy text 128 `--mtp`};
- head.auto: `DS4_QWEN4_MTP_PREFILL=auto`, `--mtp` text only.
- `DS4_QWEN4_MTP_PREFILL` is explicitly unset for all other arms (default `on`). The variable is inert
  without `--mtp` (`qwen4_mtp_prefill_resolve` returns 0).

**Also compared against saved 10-03 artefacts** (same prompts and flags): head vs `37f66ba`, base vs `0aaea5a`.

**Expected, written before running:**
- **head vs base `fc80bd6`:** bit-identical logits and logprobs and byte-identical text (MTP off and
  on), 3/3. Reasons:
  - `37f66ba` was identical to `0aaea5a` on 10-03;
  - the merge adds the same 9 main commits to both sides;
  - slycrel reports byte-identical resident output vs `fc80bd6` on the M1 Max.
- **head vs 10-03 `37f66ba`, and base vs 10-03 `0aaea5a`:** identical. `main`'s 9 commits are
  CUDA/Spark/DSpark/server; none is in the resident Qwen Metal path, as far as I've read.
  - If base differs from `0aaea5a`, then `main` itself moved Qwen output. That gets reported, and it
    isn't a PR finding.
- **CLI `--mtp` text vs plain text:** identical for both arms (true for every arm on 10-03).
- **head `auto` vs `on`, MTP text:** **identical** on 3/3.
  - Reasoning (inference): the docs say target prefill caches and logits are unchanged and only the
    predictor's history differs. Target verification decides every emitted token, and CLI MTP matched
    plain decode on 10-03.
  - If they differ, the CLI MTP path is not exactly target-greedy under different drafts. That would be
    a finding to report, not a run failure.
- **head vs head.rep:** identical. This is the **only gate**; if it fails, everything else is
  reported as nondeterministic.
- **Abort rule:** system-wide swap-ins past 2 GiB since the quiet point, or any `pmset -g therm` warning.

## (2) Server A/B (`server_ab.py`, unchanged from 10-03)

**Daily flags:** `-c 163840 --prefill-chunk 1024 --vision`, a fresh temporary KV dir per startup,
`--fixed-prefix` prompts (same text per slot in every startup).

**Each startup:** 1 excluded warmup, then short1 (~3.7K tokens, 800 generated), short2 (~3.6K, 800) and
deep (~35K, 400).

**Arms:**
- A = base;
- B = head (default, MTP prefill `on`);
- D = head with `DS4_QWEN4_MTP_PREFILL=auto`. Resident `auto` resolves exactly like `off` (read in
  code).

**Blocks:**
- MTP off: A B B A (4 startups; 10-03's C = `0231312` is dropped);
- MTP on: A B D D B A (6 startups).

**Validity, as on 10-03:**
- a startup is valid if all 3 requests return 200 with completion tokens = requested, prefill and
  decode are parsed from the server log, and swap-ins ≤ 100 MiB;
- an invalid startup is re-run once at the end of its block;
- medians, and "separate" = the per-arm ranges don't overlap.

**Expected, written before running:**
- **MTP off, B vs A:** decode +6.8..+8% (10-03: +6.8..+7.9%), prefill −0.5..+2%, wall −2..−6%, text
  identical on all 3 requests.
- **MTP on, B vs A:** prefill −6..−7% (the preparation cost), decode +6..+15%. Wall: shorts faster,
  deep (35K) ~+5% slower (10-03: −2.0 / −6.4 / +5.7%).
- **MTP on, D (`auto`) vs B (`on`):**
  - prefill **+6..+8%**, back to about MTP-off level;
  - decode **lower than B**, a few percent (slycrel M1 Max: −3.8%) and still above A;
  - **wall: D ≤ B on all 3 requests**, with the biggest gain on deep (35K prompt): D ≈ A or better
    there, where B was +5.7% slower than A.
  - If D loses to B on the short requests, that contradicts slycrel's "no ratio where `on` wins" for
    this machine/quant, and it gets reported as-is.
- **MTP on, text:** server MTP text can differ from plain decode even on base (10-03, deterministic),
  so D-vs-B or A-vs-B text differences in this block **are reported, not attributed**.
- **Limitation:** the server doesn't log MTP acceptance, so acceptance isn't compared. If head's
  server log prints it, it gets extracted after the run.

## (3) Official sweep (`run-bench.sh`, `bench-8d543ec.conf`)

**Settings:** `ds4-bench --prefill-chunk 2048`, `DS4_QWEN4_PREFILL_CHUNK=2048`, ctx 2048..65536 (32
frontiers), base vs head, A B B A A B, at the raised limit 57344 (as 10-03).
- `ds4-bench` has no `--mtp`, so the sweep can't see `DS4_QWEN4_MTP_PREFILL`. The `on`/`auto` speed
  question is answered by the server A/B.

**Validity, as 10-03:** a run is valid if rc 0, all 32 rows are present and system-wide
swap-ins ≤ 100 MiB per run (driver default), with a 120 s cooldown between runs. The representative
run is the median.

**Expected, written before running:**
- **Gen:** +6.2..+8.7%, median ~+7.5%, 32/32 separate.
- **Prefill:** +1.0..+2.0%, median ~+1.3%, 32/32 separate.
- **Why:** head's resident Qwen Metal code equals `37f66ba`'s, and base's equals `0aaea5a`'s, as far as
  read.
- **Base reproducibility vs 10-03 `0aaea5a`:** within ~1% at every frontier. If not, that's either
  `main`'s changes or a daytime machine state, and it gets reported.

## Not done / limits
- No `37f66ba` arm (optional in the brief): head differs from it only by main's merge, and it's
  checked against 10-03's saved artefacts instead.
- No SSD streaming, no Q4, no other machine. Everything is M4 Max, Q2, resident.
- Daytime window (16:00–20:00) rather than 23:00, so the machine may be less idle. The quiet check
  and the validity rules apply as before.
