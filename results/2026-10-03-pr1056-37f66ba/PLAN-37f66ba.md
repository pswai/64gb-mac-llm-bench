# antirez/ds4#1056 at 37f66ba ("restore main arithmetic for resident Qwen prefill"): plan, fixed 2026-10-03 ~18:15

## Arms (built and verified ~18:05; daily server untouched)

| Arm | Worktree | Commit | ds4 / ds4-bench / ds4-server sha256 (16) |
|---|---|---|---|
| new | ~/ds4-pr1056-37f66ba | 37f66ba3c955698c37adb18368773ca1e4cca661 | 927f6f7f2d996734 / dc0b55d02f9db15d / d1ac57d27446b689 |
| base | ~/ds4-bench-0aaea5a | 0aaea5a | 609637ebd913ef88 / 6ef71fda2de29028 / c762967736517ebe |
| prev | ~/ds4-pr1056-0231312 | 0231312 | d28254fd713621b4 / ea8c3d2edb5a3754 / c1417f8c8d34f07f |

- **What changed since `0231312`:** `575369b` (research files under `misc/`, 0 engine files) and
  `37f66ba` (`ds4.c` dispatch: the legacy prefill projection policy is now SSD-only).
- **Build:** 0 warnings, clean worktree.
- **Model-free tests on this M4 Max:** 8/8 pass, including the new
  `test-qwen4-resident-arithmetic` (6.25 MiB synthetic fixture).

## (1) Correctness only (`window-correctness.sh`): needs the owner's go, ~7 min of daily-server downtime

- **Why the server must stop anyway:** the daily server holds ~45–50 GiB of the model in GPU
  memory, and each run loads its own 41.7 GiB copy. Outputs don't depend on a quiet machine;
  memory does.
- **Procedure:** pause crons (count-checked) and stop the daily server; Codex stays open.
  - 4 arms (new, base, prev, new.rep) × 3 prompts (rome-short 29, roma575 575, sposi-long 5,942
    tokens) × {logits, 64-step logprobs (MTP off), greedy text MTP off, greedy text MTP on}
    = 48 runs. Settings as 09-30 / 10-02.
  - **Abort** if system-wide swap-ins pass 1 GiB.
  - Restore: daily server, HTTP 200 check, kv-interval flag check.
- **Estimate:** 48 runs ≈ 5.5 min (60 took 6.5 min on 10-02), plus ~1 min of quieting and
  restore, for **~7 min total**.

**Expected, written before running:**
- **new vs base:** bit-identical logits and logprobs and byte-identical text on all 3 prompts. That's
  Giorgio's claim, based on his M1 Max Q4 fixture.
- **new vs prev:** differs, since `0231312` had the resident prefill policy that `37f66ba` reverts.
- **new vs new.rep:** identical (determinism; the only failure condition).

If new ≠ base, that is reported as-is: it would mean the fix doesn't fully restore main's arithmetic
for Q2 on M4 Max.

## (2) Speed (`window-speed.sh`): tonight 23:00, hard stop 03:00, same rules as 10-02

- **Steps:** quiet check, quiet, then:
  - **server A/B** (daily flags, raised limit, fixed prompts): A = base, B = new, C = prev.
    MTP off A B C C B A; MTP on A B B A.
  - **official sweep**, base vs new: `--prefill-chunk 2048`, A B B A A B, 3 each, replacement ≤ 2
    extra.
- **Limit:** raised (57344), since the sudo rule is absent.
- **The full sweep is kept, not a subset,** so the result stays directly comparable with 10-02.
  Ends ~02:30.
- **What it answers:** whether reverting resident prefill to main's arithmetic gives back the +1.4%
  prefill gain, and whether the ~+7.5% decode gain is unchanged.
