# 2026-09-30 (evening): #1056's M1 Max-gated paths forced on for the M4 Max

**Question:** antirez/ds4#1056 (`b96a12b`) enables several resident Q2 dispatch choices only when the
GPU name contains "M1 Max" ("Leave other devices… until their parallelism tradeoff is measured").
Are they correct and faster on an M4 Max?

**Answer (measured):** yes on this machine.
- **Correctness:** first-token logits, 64 decode steps of logprobs and greedy text are all
  **bit-/byte-identical**.
- **Speed:** decode **+6.8 to +7.5%** in the official sweep (all 32 frontiers separate), +5.3 to +7.2% in
  a daily-server A/B; prefill unchanged.

## Build

- **Worktree:** local branch `exp/m1max-tuning-optin`, commit `1c12602` on `b96a12b`. Never pushed; the
  diff is [m1max-tuning-optin.diff](m1max-tuning-optin.diff) (ds4_metal.m, +35/−7).
- **Opt-in:** `DS4_METAL_M1MAX_TUNING=1` widens 7 gates. Unset = identical dispatch to the PR on
  non-M1 devices.
  - Decode: `q8_nr4_proj`, `iq2_nr2_mid`, `q2k_down_reuse`, `hc_mix_reuse`.
  - MTP stage: `q8_mtp_rows`.
  - Prefill: `hc_down_tile` (9–128-token batches), `hc_norm_reuse` (48–256).
  - Untouched: the other 9 M1 Max checks (SSD streaming, Q4/MXFP4, test hooks) and M3 Ultra / M5 / M6.
- **Logging:** each forced site logs once (`DS4_METAL_M1MAX_TUNING applied: <site>`).
  `DS4_METAL_M1MAX_TUNING_MASK` selects sites (not used here).
- **Build:** plain `make -j8`, 0 warnings.
- **Kernel suites:** 9 of the PR's kernel suites pass on this GPU (Q8 GEMV reference, Q8 reduction,
  HC, HC math, MoE mid, MoE down, Q2, Qwen kernels, prefill reuse). They call kernels directly: they
  show the M1-tuned kernels are exact here, not that dispatch selects them.
- **Arms:** the same binary with the variable off vs on, from the same worktree. The same machine and
  model as the other 2026-09 entries.

## 1. Correctness gate: ran first, set to stop the window on any difference (`correctness/`)

- **Prompts:** `rome-short` (29 tokens), `roma575` (Giorgio's prompt from the #1056 thread, sha256
  `5da9ad53…` matches his), and `sposi-long` (first 20,500 characters of `promessi_sposi.txt`,
  5,942 tokens).
- **Settings:** `./ds4 --ctx 16384 --prefill-chunk 2048 --temp 0 --nothink`, with
  `DS4_QWEN4_PREFILL_CHUNK=2048`.
- **Order:** off, on, on, off per prompt; the repeats check determinism.

| Check | off vs on | each arm vs its repeat |
|---|---|---|
| `--dump-logits` (248,328–248,330 values), MTP off | max \|Δ\| = 0, 3/3 prompts | identical |
| `--dump-logprobs`, 64 steps (10,739–11,004 values), MTP off | max \|Δ\| = 0 | identical |
| Greedy text `-n 128`, MTP off | byte-identical | identical |
| Greedy text `-n 128 --mtp` | byte-identical (and equal to MTP off) | identical |

- **Logit files:** the dumps (36 MB) aren't kept. `logits-sha256.txt` lists their hashes: one hash
  per prompt, shared by all four runs.
- **Runs:** all 48 exited 0.
- **Paths fired:** `hc_down_tile` on the 29-token prompt only; `q8_nr4_proj`, `iq2_nr2_mid`,
  `q2k_down_reuse`, `hc_mix_reuse` and `q8_mtp_rows` on all prompts; `hc_norm_reuse` never (no
  prefill batch fell in 48–256 tokens). None with the flag off.

## 2. Server A/B on the daily-driver flags (`server-ab/`)

- **Setup:** as in `2026-09-30-pr1056` (raised limit, `-c 163840 --prefill-chunk 1024 --vision …`),
  with A = flag off and B = flag on. MTP off A B B A; MTP on A B B A.
- **Prompts are fixed per slot** (`--fixed-prefix`; a server restart clears caches), so text is
  comparable: **byte-identical between A and B, and across startups, for every request.**
- **Validity:** all 8 startups valid (swap-ins ≤ 216 pages).
- **Paths fired (B):** the four decode paths, plus `q8_mtp_rows` in the MTP-on startups. No prefill
  path.

Medians over 2 startups per arm (Δ = B vs A; * = min–max ranges separate):

| | MTP off prefill | decode | wall | MTP on prefill | decode | wall |
|---|---:|---:|---:|---:|---:|---:|
| short 1 (3,683 tok, 800 gen) | 526.19 → 517.31 (−1.69%*) | 40.14 → 42.99 (+7.11%*) | 27.06 → 25.79 s (−4.71%*) | 465.08 → 473.22 (+1.75%*) | 48.00 → 50.59 (+5.41%*) | 24.66 → 23.66 s (−4.04%*) |
| short 2 (3,562 tok, 800 gen) | 524.92 → 519.20 (−1.09%) | 40.12 → 43.00 (+7.18%*) | 26.88 → 25.58 s (−4.86%*) | 465.35 → 477.07 (+2.52%*) | 59.55 → 62.86 (+5.54%*) | 21.20 → 20.31 s (−4.23%*) |
| deep (35,187 tok, 400 gen) | 532.70 → 531.99 (−0.13%*) | 39.90 → 42.73 (+7.09%*) | 76.26 → 75.62 s (−0.84%*) | 477.27 → 488.10 (+2.27%*) | 48.77 → 51.38 (+5.33%*) | 82.04 → 79.99 s (−2.50%*) |

The MTP-off prefill dip on the short prompts is **unexplained**. No widened prefill path fired, and the
sweep shows prefill unchanged.

## 3. Official sweep at the default GPU limit (`sweep/`)

- `--prefill-chunk 2048`, limit 57344 → 0 (51.84 GiB) and restored. Flag off (`exp-off`) vs on
  (`exp-on`), planned A B B A A B.
- **Validity:** `exp-on-r2` exceeded the 100 MiB system-wide swap-in rule (6,772 pages ≈ 106 MiB;
  ds4-bench 0 swaps). It is kept but excluded, and was replaced by `exp-on-r4` and `exp-on-r5`.
  - The replacement changed the order: flag-on's valid runs were the 2nd, 6th and 7th of 7 runs.
  - Wall time per run was constant within each arm: 1,547 s on, 1,554 s off.
  - The excluded run's gen gain (+6.6 to +7.9%) matches the valid runs.

Medians, prefill / gen t/s:

| ctx | flag off | flag on | Δ prefill | Δ gen |
| ---: | ---: | ---: | ---: | ---: |
| 2048 | 628.8 / 41.63 | 629.4 / 44.54 | +0.09% | +6.99% |
| 16384 | 598.1 / 41.28 | 598.2 / 44.27 | +0.01% | +7.24% |
| 32768 | 590.0 / 41.18 | 590.6 / 44.10 | +0.10% | +7.09% |
| 65536 | 587.7 / 40.91 | 587.7 / 43.79 | +0.01% | +7.04% |

- **Across all 32 frontiers:** gen **+6.76 to +7.46%** (median +7.05%), ranges separate at 32/32.
  Prefill −0.13 to +0.14% (median +0.02%), separate at 5/32.
- **Cross-check with the afternoon batch:** the flag-off arm matches the PR arm of
  `2026-09-30-pr1056` (628.8 / 41.63 vs 630.1 / 41.59 at 2K; same dispatch, different build).
- **Relative to `0aaea5a` across sessions:** gen +7.5 to +7.7% at 2K–64K. Different sessions, so
  approximate.

## Limits

- **Thermals:** `pmset -g therm` was sampled every ~5 s in the sweep runs, with no warnings; the server A/B harness doesn't sample thermals. Fans were not pinned.

- The +7% here is short of slycrel's +9.3 to +17.0% M1 Max decode gain for the whole PR. Whether these paths benefit the M1 Max more, or other PR changes account for the rest, is unexplained.
- One machine, one M4 variant (M4 Max). The two prefill-only paths never fired, so they're
  unmeasured. MTP acceptance isn't logged by the server.
- The patch is an experiment harness (logging, mask), not a merge-ready change.
