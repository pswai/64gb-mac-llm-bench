# 2026-10-03/04: antirez/ds4#1056 at `37f66ba` ("restore main arithmetic for resident Qwen prefill")

**Result (measured):** on this M4 Max with Qwen3.8 Q2 resident, `37f66ba`:
- produces **output identical to base `0aaea5a`** (first-token logits, 64-step logprobs, greedy
  text);
- keeps the full speedup: **gen +6.2 to +8.7% (median +7.5%), prefill +1.0 to +2.0% (median +1.3%)**,
  32/32 frontiers separate.
- The head-vs-base drift reported for `0231312` (2026-10-02) is gone.

## Arms

| Arm | Commit | ds4 / ds4-bench / ds4-server sha256 (16) |
|---|---|---|
| new | `37f66ba` (`0231312` + `575369b` research files only + `37f66ba`, a `ds4.c` dispatch scope change) | 927f6f7f2d996734 / dc0b55d02f9db15d / d1ac57d27446b689 |
| base | `0aaea5a` | 609637ebd913ef88 / 6ef71fda2de29028 / c762967736517ebe |
| prev | `0231312` | d28254fd713621b4 / ea8c3d2edb5a3754 / c1417f8c8d34f07f |

- Builds: plain `make -j8`, 0 warnings.
- Model-free tests on this M4 Max: 8/8 pass, including the new `test-qwen4-resident-arithmetic`.
- Expectations were written before the runs: [PLAN-37f66ba.md](PLAN-37f66ba.md).
- Limit 57344 (raised) throughout.

## Correctness (`correctness/`), 2026-10-03 18:41–18:46

- **Downtime:** the daily server was stopped for ~5 min (crons count-checked). Two model copies
  don't fit in 64 GB.
- **Runs:** 48 (new, base, prev, new.rep × 3 prompts × 4 checks), all rc 0, 0 MiB swap-ins.
- **Settings:** as on 2026-09-30 and 10-02.

| new vs | first-token logits (MTP off) | 64-step logprobs (MTP off) | greedy text, MTP off / on |
|---|---|---|---|
| base `0aaea5a` | identical (max \|Δ\| 0), 3/3 | identical, 3/3 | byte-identical, 3/3 |
| prev `0231312` | max \|Δ\| 0.295 / 0.618 / 0.953 | differ | differ on roma575 and sposi-long |
| itself (repeat) | identical | identical | identical |

- **Prompts:** rome-short (29 tokens), roma575 (575), sposi-long (5,942, 3 chunks).
- The new-vs-prev differences equal the 10-02 head-vs-base numbers: `37f66ba` reverted exactly that
  drift.

## Speed window, 2026-10-03 23:00 – 10-04 02:25

All runs valid. Thermals sampled every 10 s (1,214 samples, no warnings); highest system-wide
swap-ins in a run were 1,256 pages ≈ 20 MiB.

**Official sweep** (`sweep/`): `--prefill-chunk 2048`, base vs new, A B B A A B, 3 each:

| ctx | base prefill / gen | new prefill / gen | Δ prefill | Δ gen |
| ---: | ---: | ---: | ---: | ---: |
| 2048 | 621.7 / 41.49 | 634.1 / 44.96 | +1.99% | +8.36% |
| 16384 | 590.0 / 41.15 | 599.0 / 44.23 | +1.52% | +7.48% |
| 32768 | 583.7 / 41.07 | 591.1 / 44.24 | +1.27% | +7.72% |
| 65536 | 580.8 / 40.72 | 587.3 / 43.73 | +1.11% | +7.39% |

- **Across 32 frontiers:** gen +6.21 to +8.69% (median +7.52%), prefill +1.04 to +1.99% (median
  +1.32%), both separate at 32/32.
- **Same as `0231312` on 10-02** (+7.45% / +1.40%), so restoring main's resident prefill arithmetic
  cost nothing measurable here.
- **Base reproducibility vs 10-02:** within 0.35% (prefill) and 1.05% (gen) at every frontier.

**Server A/B** (`server-ab/`): daily flags, fixed per-slot prompts. A = base, B = new, C = prev.
MTP off A B C C B A; MTP on A B B A. 10/10 valid. Δ vs A; * = ranges separate:

| | short 1 (3,683 tok) | short 2 (3,562 tok) | deep (35,187 tok) |
|---|---:|---:|---:|
| MTP off, decode B (C) | +7.86%* (+7.27%*) | +6.76%* (+7.12%*) | +7.13%* (+7.60%*) |
| MTP off, prefill B | −0.20% | +0.55% | +1.93%* |
| MTP off, request wall B | −5.47%* | −5.08%* | −2.65%* |
| MTP off, text B vs A | identical | identical | identical |
| MTP on, decode B | +6.48%* | +14.54%* | +7.18%* |
| MTP on, prefill B | −7.04%* | −6.13%* | −6.80%* |
| MTP on, request wall B | −2.05%* | −6.38%* | +5.73%* |

**About MTP-on text in the server.** A and B differ on 2 of 3 MTP-on requests. Base itself gives
different text with MTP on vs off on the same 2 prompts. That's deterministic across startups, and
the same on 10-02. So server-side MTP verification isn't bit-equivalent to plain decode even on
`0aaea5a`, and these cross-arm MTP-on differences aren't attributed to the PR (an inference, not
traced). In the CLI correctness runs, MTP on equals MTP off for every arm.

## Limits

M4 Max and Q2 resident only. MTP acceptance isn't logged by the server. One session per test.
