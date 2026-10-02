# Retest of antirez/ds4#1056 at 0231312 on the M4 Max: rules fixed before the run (2026-10-02 ~21:45)

## Arms (built and verified ~21:40, without stopping the daily server)

| Arm | Worktree | Commit | ds4 / ds4-bench / ds4-server sha256 (16) |
|---|---|---|---|
| base | ~/ds4-bench-0aaea5a | 0aaea5a238fb41a35106a551e73c8409dfb751ac | 609637ebd913ef88 / 6ef71fda2de29028 (= published) / c762967736517ebe |
| head | ~/ds4-pr1056-0231312 | 0231312820fb0ba0e8953606976461644511bcab | d28254fd713621b4 / ea8c3d2edb5a3754 / c1417f8c8d34f07f |
| ref | ~/ds4-pr1056-m1tune | 1c126024762dfef74580db0aa906f07f25dce5b7 (local opt-in patch on b96a12b) | built 09-30 |

- **Head is b96a12b plus two commits:** `f32a16a` (research files under `misc/` only; 0 engine files)
  and `0231312`.
- **What 0231312 does:** it widens all "M1 Max" gates to names matching `Apple M[2-4]( |$)`;
  "Apple M4 Max" matches. That covers more than our patch (also SSD and Q4 paths), but for
  resident Q2 the same decode paths are expected to fire.
- **Builds:** plain `make -j8`, 0 warnings, clean worktrees.
- **Head model-free tests:** 10/10 pass, including the new device-policy test (47 names).

## Expected results (written before running)

- **Primary correctness gate:**
  - head vs ref (flag on) and head vs ref (flag off) should be bit-identical (logits, 64-step
    logprobs) and byte-identical (greedy text, MTP off and on) on all 3 prompts. On 09-30, ref off
    was identical to ref on.
  - The head should also be identical to itself on repeat.
  - **Any head-vs-ref difference stops the window before speed tests.**
- **Head vs base, reported but NOT a stop condition.**
  - Expected identical on `rome-short` (29 tokens) and `roma575` (575): a single prefill chunk at
    2048. In slycrel's base-vs-PR runs, short and roma575 were byte-identical.
  - **May differ on `sposi-long` (5,942 tokens, 3 chunks):** base's chunked prefill is
    chunk-dependent, while the PR is chunk-invariant (slycrel, #1056). A difference there is the
    PR's known numerics fix, not the tuning.
  - So the brief's "byte-identical output to the base" can only be claimed where it holds.
- **Speed:** head vs base decode about +7.5% (the 09-30 cross-session estimate). Prefill as in the
  09-30 PR-vs-base sweep: about +1.4% at the stock limit.

## Window steps (`window-retest.sh`)

1. **Quiet check (brief: stop if not quiet).** Before stopping anything: 1-minute load average ≤ 2.5
   and no non-system process ≥ 25% CPU in a 10 s sample. Re-check every 60 s for up to 15 min,
   then abort without touching the server.
2. **Quiet:** pause all scheduled agent jobs (abort unless paused = active and 0 remain active), stop
   the daily server via launchd (wait for its process to exit), quit ChatGPT/Codex if running.
   - A background sampler logs `pmset -g therm` and swap-ins every 10 s for the whole window.
3. **Correctness (~8 min):** arms base, head, head.rep, ref-off, ref-on × 3 prompts × {logits,
   logprobs, text, mtptext}. Same settings as 09-30
   (`--ctx 16384 --prefill-chunk 2048 --temp 0 --nothink`, `DS4_QWEN4_PREFILL_CHUNK=2048`).
4. **Server A/B (~36 min):** daily flags at the current limit (57344). Fixed per-slot prompts.
   - A = base, B = head, C = ref with the flag on.
   - MTP off: A B C C B A. MTP on: A B B A.
   - Validity as before.
5. **Official sweep (~2 h 40 min):** base vs head, `--prefill-chunk 2048`, A B B A A B, 3 each,
   replacement ≤ 2 extra per arm.
   - **Limit:** the sysctl sudo rule is absent, so the sweep runs at 57344 (raised), not the stock
     limit used on 09-30. Labelled; earlier measurements show < 1% speed difference between the
     limits on Qwen. If the owner re-adds the rule before 23:00, the driver uses the stock limit
     automatically.
6. **Restore on every exit path:**
   - daily server back (launchd pid = :8001 listener) and `curl :8001/v1/models` → 200;
   - crons resumed (count = 6);
   - limit 57344; temp KV deleted; ChatGPT reopened if it was quit.

**Hard stop 03:00** (another local session agreed to stay idle 23:00–03:00). Total about 3.5 h, so the expected end is
about 02:30. Replacement runs could reach the hard stop, which restores and leaves a partial,
labelled result.
