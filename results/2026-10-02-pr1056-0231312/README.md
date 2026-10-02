# 2026-10-02/03: antirez/ds4#1056 at `0231312` (M2–M4 tuning by device name) vs base `0aaea5a`

**Result (measured, one session, no env var or patch):** the PR head enables the M1 Max-tuned
decode paths on this M4 Max by device name. Compared with the base:
- **Official sweep:** generation **+6.3 to +8.9%** (median +7.45%) and prefill +1.1 to +2.0%
  (median +1.4%), with ranges separate at 32/32 frontiers.
- **Correctness:** output is identical to our opt-in patch from 2026-09-30 (`1c12602`, flag on or
  off).
- **Not identical to the base:** head-vs-base outputs differ. That's a pre-existing difference
  between the PR and its base, not the tuning (see Correctness).

## Arms

Each arm was built in its own clean worktree with plain `make -j8` and 0 warnings; sha256 prefixes
are logged in `window.log`.

| Arm | Commit | Notes |
|---|---|---|
| base | `0aaea5a` | same `ds4-bench` binary as all earlier entries (`6ef71fda…`) |
| head | `0231312` | = `b96a12b` + `f32a16a` (research files under `misc/` only) + `0231312` ("extend Qwen M1 Max tuning to M2, M3 and M4"; "Apple M4 Max" matches `Apple M[2-4]( \|$)`) |
| ref | `1c12602` | our 2026-09-30 opt-in patch on `b96a12b`; `DS4_METAL_M1MAX_TUNING` off or on |

- Head model-free tests: 10/10 pass, including the new 47-name device-policy test.
- Rules and expected results were written before the run (`PLAN-RETEST.md`).
- Machine: as before, with `iogpu.wired_limit_mb=57344` (raised; it survived a reboot via a boot
  daemon) for the whole window. The 2026-09-30 sweeps ran at the stock limit; today's base arm
  matches 09-30's base within ~0.3% at 2K (620.1 / 41.51 vs 620.4 / 41.41).
- Window 23:00–02:31 SGT:
  - quiet check passed (load 1.60);
  - all scheduled jobs paused (count-verified) and the daily server stopped;
  - `pmset -g therm` and swap-ins sampled every 10 s across the whole window (1,250 samples, no
    thermal warnings).

## Correctness (`correctness/`): settings as on 2026-09-30, 60 runs, all rc 0

- **Gate, fixed in advance:** head vs ref-on, ref-off and its own repeat. **Identical:** first-token
  logits and 64-step logprobs (MTP off) bit-identical, and greedy text (MTP off and on)
  byte-identical, on all 3 prompts. So the new device gate is output-neutral here, as the opt-in
  patch was.
- **Head vs base (reported, not a gate). Different on all 3 prompts:**

| Prompt | First-token logits, max \|Δ\| | Greedy text (MTP off / on) |
|---|---:|---|
| rome-short (29 tokens, 1 chunk) | 0.295 | identical |
| roma575 (575 tokens, 1 chunk) | 0.618 | different |
| sposi-long (5,942 tokens, 3 chunks) | 0.953 | different |

- **Not caused by the M2–M4 tuning:** ref-off (no tuning, `b96a12b` dispatch) equals the head. It
  comes from the PR's other changes since `0aaea5a`.
- **My pre-run expectation was wrong:** I expected the two single-chunk prompts to match the base,
  following slycrel's single-pass parity at `04c0867` / `11811b9`. Which later commit changed it, or
  whether our CLI setup differs from his, is **not determined**; a bisect would settle it.

## Server A/B (`server-ab/`): daily flags, raised limit, fixed per-slot prompts

- **Arms:** A = base, B = head, C = ref with the flag on. Blocks: MTP off A B C C B A; MTP on
  A B B A.
- **Validity:** 10/10 startups valid.
- **Prompts:** 3,683 / 3,562 / 35,187 tokens.
- **Text:** B and C are byte-identical on every request; A differs (see Correctness).

Medians; Δ vs A; * = ranges separate:

| | short 1 | short 2 | deep |
|---|---:|---:|---:|
| MTP off, decode B (C) | +8.06%* (+7.48%*) | +6.82%* (+7.02%*) | +7.56%* (+7.72%*) |
| MTP off, prefill B | −0.14% | +0.69% | +1.81%* |
| MTP off, request wall B | −5.74%* | −5.17%* | −2.59%* |
| MTP on, decode B | +7.70%* | +14.74%* | +8.66%* |
| MTP on, prefill B | −7.17%* | −6.79%* | −7.55%* |
| MTP on, request wall B | −2.75%* | −6.23%* | **+6.36%*** |

With MTP on, the PR's default predictor preparation still costs ~7% prefill
(`DS4_QWEN4_MTP_PREFILL`, default on). On the 35K prompt that outweighs the decode gain, and the
request is slower end to end.

## Official sweep (`sweep/`): `--prefill-chunk 2048`, raised limit, base vs head, A B B A A B

All 6 runs valid. Highest system-wide swap-ins: 4,035 pages ≈ 63 MiB; ds4-bench 0 swaps.

| ctx | base prefill / gen | head prefill / gen | Δ prefill | Δ gen |
| ---: | ---: | ---: | ---: | ---: |
| 2048 | 620.1 / 41.51 | 632.5 / 44.66 | +2.00% | +7.59% |
| 16384 | 591.3 / 41.14 | 598.7 / 44.16 | +1.26% | +7.34% |
| 32768 | 583.7 / 41.06 | 591.6 / 44.05 | +1.36% | +7.28% |
| 65536 | 579.3 / 41.14 | 587.3 / 43.77 | +1.38% | +6.39% |

**Across all 32 frontiers:** gen +6.32 to +8.86% (median +7.45%) and prefill +1.13 to +2.00% (median
+1.40%), both separate at 32/32.

## Limits

- One machine and one chip (M4 Max), Qwen Q2 resident. Not covered: M2/M3, other M4 variants, SSD
  streaming, Q4.
- Correctness compares outputs, not quality.
- The head-vs-base output difference is unexplained.
