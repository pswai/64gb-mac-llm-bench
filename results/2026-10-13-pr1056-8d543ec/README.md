# 2026-10-13: antirez/ds4#1056 at `8d543ec` ("Merge antirez/main into qwen-kernel-opt")

**Result (measured):** on this M4 Max with Qwen3.8 Q2 resident, `8d543ec`:
- produces **output identical to `main` `fc80bd6`** (first-token logits, 64-step logprobs, greedy text
  with MTP off and on);
- is **faster than `main`: gen +7.9 to +8.7% (median +8.1%), prefill +1.1 to +1.6% (median +1.4%)**,
  32/32 frontiers separate.

**`DS4_QWEN4_MTP_PREFILL=auto`** (on resident, the same as `off`) vs the default `on`, in the server
with MTP on:
- **text:** identical;
- **prefill:** +8.7..+8.9%;
- **total wall over the 3 requests:** −4.7%.
- **But `on` wins the request with the highest MTP speedup** (short2: `on` +2.4% faster end to end).

## Arms

| Arm | Commit | ds4 / ds4-bench / ds4-server sha256 (16) |
|---|---|---|
| head | `8d543ec` (PR head: `37f66ba` + a merge of `main`'s 9 commits up to `fc80bd6`) | 8e4edecb8ee912f0 / 8d3270e4f36a0c60 / 8bd2f23ebf5292a9 |
| base | `fc80bd6` (`main`, the merge base; head is 40 ahead and 0 behind) | 7de4a40519c1b1f9 / 00f9e37c5744f88c / 547297ba3ce85cfe |

- **Builds:** plain `make -j8`, 0 warnings, clean worktrees.
- **The merge resolved 2 conflicts in `ds4.c`:** TP batched MoE (M5/M6, `tp_world == 2`) and the SSD
  streaming memory admit. Neither path runs resident on this machine (read in code, not traced).
- **Expectations were written before the runs:** [PLAN-8d543ec.md](PLAN-8d543ec.md). The repo copy
  has private names made generic; its content is otherwise unchanged.
- **Limit:** 57344 (raised) throughout, as on 10-03.

## Model-free tests on head (`tests-head/`): 14/15 pass

- **Pass:** the 14 Qwen/Metal targets from the PR thread, including `test-qwen4-resident-arithmetic`
  and `test-metal-device-policy`.
- **Fail: `test-qwen4-moe-mm-compact`,** at `tests/test_qwen4_moe_mm_compact.py:61`. It's a stale
  source scanner: it expects 3 template arguments, and `b96a12b` added `KS`. It's the same failure
  reported on the M1 Max and the M6, it isn't hardware-dependent, and it isn't part of `make test`.

## Correctness (`correctness/`), 2026-10-13 20:01–20:05

**Runs:** 39 (head, base and head.rep × 3 prompts × 4 checks, plus head with `DS4_QWEN4_MTP_PREFILL=auto`
× 3 MTP texts). All rc 0, 0 MiB swap-ins.

| head `8d543ec` vs | first-token logits (MTP off) | 64-step logprobs (MTP off) | greedy text, MTP off / on |
|---|---|---|---|
| base `fc80bd6` | identical (max \|Δ\| 0), 3/3 | identical, 3/3 | byte-identical, 3/3 |
| `37f66ba` (10-03 artefacts) | identical, 3/3 | identical, 3/3 | byte-identical, 3/3 |
| itself (repeat) | identical | identical | identical |

- **Base `fc80bd6` vs 10-03 base `0aaea5a`:** identical on every check, so `main`'s 9 new commits don't
  change resident Qwen output.
- **CLI `--mtp` text** equals plain greedy text for both arms.
- **head `MTP_PREFILL=auto` vs default `on`, `--mtp` text:** byte-identical, 3/3.
  - The setting took effect: single-run CLI prefill was +8.1% (roma575) and +10.0% (sposi-long).
- **Prompts and settings:** as on 2026-09-30 / 10-02 / 10-03.

## Server A/B (`server-ab/`), 20:05–20:41

**Settings:** daily flags, fixed per-slot prompts. A = base, B = head (default `on`),
D = head with `DS4_QWEN4_MTP_PREFILL=auto`.

**Order:** MTP off A B B A; MTP on A B D D B A. 10/10 valid (max 519 swap-in pages ≈ 8 MiB).

Δ vs A unless noted; * = ranges separate (2 startups per arm). Summary: `server-ab/summary.txt`.

| | short1 (3,683 tok) | short2 (3,562 tok) | deep (35,187 tok) |
|---|---:|---:|---:|
| MTP off, decode B | +8.03%* | +7.88%* | +7.92%* |
| MTP off, prefill B | −1.30% | +0.75% | +1.55%* |
| MTP off, request wall B | −5.10%* | −5.56%* | −2.28%* |
| MTP off, text B vs A | identical | identical | identical |
| MTP on, prefill B / D | −6.17%* / +2.19%* | −5.86%* / +2.31%* | −6.79%* / +1.48%* |
| MTP on, decode B / D | +6.40%* / +6.07%* | +14.56%* / +5.70%* | +7.41%* / +5.41%* |
| MTP on, request wall B / D | −2.25%* / −4.65%* | −6.51%* / −4.29%* | +5.68%* / −1.87%* |
| **MTP on, D (`auto`) vs B (`on`)**: prefill / decode / wall | +8.90%* / −0.31%* / **−2.46%*** | +8.68%* / −7.74%* / **+2.38%*** | +8.88%* / −1.86%* / **−7.15%*** |
| MTP on, text D vs B | identical | identical | identical |

**Summed request wall over the 3 requests, MTP on** (medians):
- A 121.83 s, B 124.17 s, D 118.35 s.
- `auto` vs `on` −4.69%*; `auto` vs `main` −2.86%*; `on` vs `main` +1.92%*.

**Reading:**
- Head vs base reproduces 10-03 (MTP-off decode +6.8..+7.9% then, +7.9..+8.0% now; MTP-on B decode
  and wall within 0.3 pt of 10-03, prefill within 0.9 pt).
- With MTP on, `auto` gives back the ~6% prefill that `on` spends preparing predictor history. It
  loses decode wherever MTP is doing a lot of work. On short2 (decode +14.6% under `on`), `auto` loses
  7.7% decode and ends 2.4% slower; on the other two requests it's faster end to end.
- So on this machine `on` can win, on a short-prompt, high-speedup request. That differs from the M1
  Max result in the PR thread, where `auto` never lost. The server doesn't log acceptance, so the
  link to acceptance is inferred from decode speed, not measured.

**MTP-on text vs base:**
- B and D are identical to each other on all 3 requests.
- A differs from them on short1 and deep, and server MTP-on text isn't bit-equal to plain decode in
  either arm (as on 10-03). Not attributed to the PR.

## Official sweep (`sweep/`), 20:41–23:29

**Settings:** `--prefill-chunk 2048`, base vs head, A B B A A B, 3 each. All 6 valid (max 3.7 MiB
swap-ins per run).

| ctx | base prefill / gen | head prefill / gen | Δ prefill | Δ gen |
| ---: | ---: | ---: | ---: | ---: |
| 2048 | 620.6 / 41.28 | 630.6 / 44.54 | +1.62% | +7.90% |
| 16384 | 590.8 / 41.06 | 599.0 / 44.31 | +1.39% | +7.92% |
| 32768 | 583.3 / 40.87 | 591.6 / 44.23 | +1.42% | +8.22% |
| 65536 | 579.7 / 40.57 | 588.7 / 43.81 | +1.55% | +7.99% |

- **Across 32 frontiers:** gen +7.90 to +8.65% (median +8.06%), prefill +1.13 to +1.62% (median
  +1.43%), both separate at 32/32 (`sweep/head-vs-base.txt`).
- **Head vs 10-03 `37f66ba`:** prefill within 0.55%, gen within 1.06% (medians +0.05% / +0.02%).
- **Base vs 10-03 `0aaea5a`:** prefill within 0.46%. Gen is −0.22 to −1.53% (median −0.49%), which is
  past the ~1% the plan expected at some frontiers.
  - The slightly higher head-vs-base gain than 10-03 (+8.06% vs +7.52% median) comes mostly from that
    base gen offset, not from head.

## Window

- **Daily server down 20:01:02–23:30:04** (3 h 29 min).
  - Scheduled jobs: 6 paused (count-checked), 6 restored.
  - Restore check: HTTP 200 with the daily flags; limit 57344.
- **Thermals:** 1,237 samples, 0 thermal or performance warnings.
- **Swap-ins:** 27 MiB system-wide over the whole window.
- **Deviations from the plan:**
  - It ran 19:58–23:30 instead of ~16:00. The owner moved the hard stop from 20:00 to 00:30; the
    20:15 restore target in the plan was replaced by that.
  - Two launch attempts (19:55, 19:57) stopped before anything was quieted: one for the late hour,
    one for a STOP_AT parsing bug, fixed.
  - Codex was left open (on 10-03 it was quit).
  - `run-bench.sh`'s watchdog left an orphaned `sleep` that would have signalled a dead pid at 00:30.
    It was killed by hand after the window.

## Limits

- M4 Max and Q2 resident only. No SSD streaming, no Q4.
- MTP acceptance isn't logged by the server.
- 2 startups per arm in the server A/B; one session per test.
