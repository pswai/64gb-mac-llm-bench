# 2026-09-30: antirez/ds4#1056 (`b96a12b`) vs base `0aaea5a`, Qwen3.8 Flash Next Q2, resident

Same machine as 2026-09-28: Mac Studio M4 Max 64 GB, macOS 26.6.2, internal SSD with 197–199 GiB
free, same Qwen Q2 GGUF (sha256 `b1b93fa6…ccac9`).

- **Arms:**
  - A = `0aaea5a`: the published baseline worktree, `ds4-bench` sha256 `6ef71fda…` (identical to 09-28), `ds4-server` `c7629677…`.
  - B = `b96a12b`: PR head, a fresh detached worktree; `ds4-bench` `2358ab99…`, `ds4-server` `82bbb794…`.
  - Both built with plain `make -j8`, 0 warnings, each run from its own worktree.
- **`0aaea5a` is an ancestor of `b96a12b`**, since the PR merged main at `b1af94b`, so B = A + the PR's changes.
- **Pinned in both arms:** `DS4_QWEN4_PREFILL_CHUNK` = `--prefill-chunk`.
- **Quiet machine:** daily server stopped, 6 scheduled jobs paused (count-verified), desktop chat app quit.
- **Validity:** fixed in advance in the working plan. All runs below passed.

## 1. Official sweep at the macOS default GPU limit (`sweep/`)

- `ds4-bench … --ctx-start 2048 --ctx-max 65536 --step-incr 2048 --gen-tokens 128 --prefill-chunk 2048`.
- Limit set 57344 → 0 (Metal working set 56.00 → **51.84 GiB**) and restored afterwards.
- Order A B B A A B, with 120 s cooldowns. All 6 runs valid: rc 0, 32 rows, system-wide swap-ins ≤ 87 pages (≤ 1.4 MiB).
- Run by the repo's generalized driver (its first measured batch).

Medians, prefill / gen t/s:

| ctx | A `0aaea5a` | B `b96a12b` | Δ prefill | Δ gen |
| ---: | ---: | ---: | ---: | ---: |
| 2048 | 620.4 / 41.41 | 630.1 / 41.59 | +1.57% | +0.43% |
| 16384 | 590.3 / 41.18 | 598.8 / 41.28 | +1.43% | +0.24% |
| 32768 | 584.0 / 40.95 | 590.9 / 41.14 | +1.19% | +0.46% |
| 65536 | 579.6 / 40.66 | 587.5 / 40.92 | +1.35% | +0.64% |

- **All 32 frontiers:** prefill Δ +1.10 to +1.75% (median +1.42%), with the arms' min–max ranges
  separate at 32/32. Gen Δ +0.22 to +0.81% (median +0.50%), separate at 28/32.
- **Reproducibility:** today's A matches the published 2026-09-28 default-limit chunk-2048 medians
  within 0.24% (prefill) and 0.44% (gen) at every frontier.
- Full per-frontier tables: [summary-sweep.md](summary-sweep.md).

## 2. Server A/B on the owner's daily flags (`server-ab/`)

- **Server:** `ds4-server -m Qwen…Q2.gguf --vision mmproj-Q8_0 --metal -c 163840 --prefill-chunk 1024 [--mtp] -n 16384`,
  on a separate port, with a fresh temporary KV dir per startup (deleted afterwards). Run at the
  raised limit (57344 MB), as the daily server runs.
- **Blocks:** MTP off A B B A; MTP on A B C C B A, where C = B with `DS4_QWEN4_MTP_PREFILL=off`.
- **Per startup:** a warmup (excluded), 2 short requests (3,567 / 3,688 prompt tokens, 800
  generated) and 1 deep request (35,193 prompt tokens, 400 generated). Settings: temp 0,
  top_p 1, `ignore_eos`, non-streaming, the no-thinking model alias.
- **Metrics:** the server's own `prefill … avg` / `decoding … avg` lines and client wall time.
- **Validity:** all 10 startups valid (swap-ins ≤ 64 pages).

Medians (4 short / 2 deep requests per arm; ranges in `startups.jsonl`):

| | A | B (PR default) | C (PR, `MTP_PREFILL=off`) |
|---|---:|---:|---:|
| MTP off: prefill short / deep | 509.9 / 525.0 | 519.8 / 532.6 (+1.9% / +1.5%) | n/a |
| MTP off: decode short / deep | 40.04 / 39.76 | 40.12 / 39.92 (+0.2% / +0.4%) | n/a |
| MTP off: wall short / deep | 27.16 s / 77.22 s | 27.01 s / 76.22 s | n/a |
| MTP on: prefill short / deep | 508.4 / 525.0 | 462.1 / 476.2 (−9.1% / −9.3%) | 512.7 / 529.8 (+0.8% / +0.9%) |
| MTP on: decode short / deep | 49.23 / 47.49 | 48.92 / 49.00 (−0.6% / +3.2%) | 48.00 / 46.98 (−2.5% / −1.1%) |
| MTP on: wall short / deep | 23.48 s / 75.57 s | 24.30 s / 82.19 s (+3.5% / +8.8%) | 23.83 s / 75.05 s (+1.5% / −0.7%) |

## Interpretation

These are inferences, labelled as such.
- **With MTP off, the PR is a small, consistent gain on this machine:** +1.2–1.9% prefill and
  +0.2–0.6% decode, in both the official sweep and the server test.
  - slycrel measured +14–17% decode on an M1 Max 64 GB.
  - Several of the PR's decode dispatch choices are enabled only when the device name contains
    "M1 Max". Others are gated to "M3 Ultra" or M5/M6. An M4 Max matches none of them: observed
    in the code, but not traced to specific gains.
- **With MTP on, the PR's default predictor-history preparation costs ~9% prefill** on this Q2
  resident setup (mvdbos: −14%, Q4, M5 Max). Decode didn't recover it here, so requests were
  3.5–8.8% slower.
  - `DS4_QWEN4_MTP_PREFILL=off` removes the prefill cost, and decode was slightly lower than base,
    making it roughly neutral.
  - MTP acceptance isn't logged by the server, so its effect wasn't measured.

## Limits

- **No output-identity check in the server test:** each request carried a unique numeric prefix,
  so outputs are not comparable across arms. The official sweep's generation is greedy but was
  not diffed either.
- Small samples in the server test: 2 deep requests per arm. Resident only; SSD streaming not
  tested (Q2 fits in 64 GB). One machine.

## Attempts that did not measure anything

Logs are in `windows/`:
- **12:13:** aborted during quieting. The driver checked for a leftover server process while the
  daily server was still saving caches on shutdown. Fixed by waiting for the process to exit.
- **12:52:** the official sweep aborted in preflight: the Metal working-set helper wasn't built in
  this repo. Fixed, then the exact command was dry-run before the relaunch.

Both restored the daily server and jobs automatically, and the server A/B was not repeated.
