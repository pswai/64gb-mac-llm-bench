# 2026-09-28: Mac Studio M4 Max 64 GB, ds4 `0aaea5a`

## Environment (sanitized from the local capture)

| | |
|---|---|
| Machine | Mac Studio `Mac16,9`, Apple M4 Max, 64 GB (68,719,476,736 bytes), 16 KiB pages |
| OS | macOS 26.6.2 (25G83), Darwin 25.6.0, arm64 |
| GPU memory limit | batches 1115 and 1507: `iogpu.wired_limit_mb=57344` (Metal working set 56.00 GiB). Batch 2008: `0` = default (Metal working set **51.84 GiB**, 55,662,788,608 bytes) |
| Storage | internal APPLE SSD AP1024Z (1 TB); 124–125 GiB free in the main batches, 245 GiB in 2008 |
| Power | on mains, `lowpowermode 0`; `pmset -g therm` recorded no thermal or performance warning in any sample |
| Engine | antirez/ds4 `0aaea5a238fb41a35106a551e73c8409dfb751ac`, `make ds4-bench`, 0 warnings; `ds4-bench` sha256 `6ef71fda2de29028a9f387ebb5fd52f177d191336aeb9e28620211fd8fc3662e` |
| Qwen3.8 Flash Next Q2 | `Qwen3.8-Flash-Next-Q2.gguf`, 147,207,127,040 bytes, sha256 `b1b93fa69aca5f187b0fb813aca8f3ec1beb5cf8cf0bd38cf041b93e0b6ccac9` (HF `antirez/qwen3.8-flash-next-gguf`) |
| DeepSeek V4 Flash Q2 | `DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix-0731.gguf`, 86,720,111,488 bytes, sha256 `ca22ae2f838e14077c22bc1c1417b71b45b5e5a3687bd96c2ac6e17fdb6261c0` (HF `antirez/deepseek-v4-gguf`) |

The checksums were verified at 11:22. Batches 1507 and 2008 skipped the check; the files were
read-only in between.

## Command

From the ds4 checkout: `./ds4-bench -m MODEL --prompt-file speed-bench/promessi_sposi.txt --ctx-start 2048 --ctx-max 65536 --step-incr 2048 --gen-tokens 128 [FLAGS]`, under `/usr/bin/time -l`.

| Config | Model | FLAGS | ds4's plan (from its startup report) |
|---|---|---|---|
| `qwen-default` | Qwen Q2 | none | chunk 8192; KV 2.09 + buffers 8.24 + model 41.72 = **52.05 GiB** |
| `qwen-chunk2048` | Qwen Q2 | `--prefill-chunk 2048` | KV 2.09 + buffers 2.31 + model 41.72 = **46.11 GiB** |
| `dsf-stream` | DeepSeek Q2 | `--ssd-streaming` | resident 8.20 + expert cache 35.42 + prefill reserve 3.38 + KV 0.86 + buffers 0.50 = **48.36 GiB** |

## Batches and runs

| Batch (dir) | GPU limit | Runs |
|---|---|---|
| `1115-main` | 56.00 GiB | qwen-default r1–r3; qwen-chunk2048 r1–r3; dsf-stream r1–r3; first-token probe |
| `1507-replacement` | 56.00 GiB | qwen-chunk2048 r1, dsf-stream r1 (replacements, see `REPLACEMENT-NOTE.txt`) |
| `2008-default-limit` | 51.84 GiB | qwen-chunk2048 r1–r3; qwen-default r1 (probe), see `DEFAULT-LIMIT-PLAN.txt` |

**Excluded by the swap rule** (> 100 MiB of system-wide swap-ins; `ds4-bench` itself had 0 swaps in each):
- `1115-main/qwen-chunk2048-r3` (137 MiB);
- `1115-main/dsf-stream-r3` (403 MiB);
- `1507-replacement/qwen-chunk2048-r1` (168 MiB).

Their numbers match the valid runs. The files are kept here.

Full per-frontier tables, with every run side by side: [summary-raised-limit.md](summary-raised-limit.md)
(batches 1115 and 1507 merged) and [summary-default-limit.md](summary-default-limit.md).

## Observations

These are measured; the causes are unexplained where marked.
- **Qwen** is flat from 2K to 64K. Across the 288 frontier points of the 9 valid Qwen runs:
  - prefill: 571–622 t/s;
  - generation: 40.1–41.6 t/s, except two points: 35.7 t/s at 2K in the day's first run
    (1115 qwen-default r1) and 38.6 t/s at 12K (2008 qwen-chunk2048 r1).

  The lowest prefill point, 571 t/s, is also in 2008 qwen-chunk2048 r1 (at 59K). Chunk size and
  GPU limit change the per-frontier medians by ≤ 1%.
- **DeepSeek streamed:**
  - Generation is steady at 13–16 t/s.
  - Prefill has a median of ~135 t/s but intermittent drops in every run. The deepest was ~48 t/s
    at 57K–63K in 1115 r1, and it wasn't reproduced in an order-matched run. Unexplained.
  - Disk reads peaked at ~6.1 GB/s.
  - In excluded 1115 r3, about two-thirds of 403 MiB of system-wide swap-ins came 3–6 minutes
    into the run.
- **Default GPU limit:** the unmodified Qwen command, planned at 0.21 GiB over the limit,
  completed its one probe run with 10 MiB of system-wide swap-ins and 0 swaps for the process.
  Why a plan over the working-set figure didn't swap is unexplained; the plan may overstate
  actual GPU residency.
- **First token** (1115 batch, 2,048-token prompt, 3 pairs; median, with min–max):

  | Model | Cold, after purge | Warm |
  |---|---:|---:|
  | Qwen | 23.7 s (23.6–24.6) | 3.7 s (3.7–3.7) |
  | DeepSeek, streamed | 18.2 s (18.0–19.1) | 13.8 s (13.6–14.0) |

  Derived load time is 20.3 s for Qwen cold, 4.6 s for DeepSeek cold, and 0.3 s warm for both.
- **Qwen snapshots** exceed ds4-bench's 1 GiB limit from 30,720 onward (`kvcache_bytes=0`), so
  prefix replay is used. It sits outside the timed windows.

## Files per batch

- `<config>-r<N>.csv`: unmodified ds4-bench output.
- `<config>-r<N>.stderr`: ds4's startup report and `time -l`.
- `<config>-r<N>.samples.csv`: 5-second samples.
- `runs.tsv`: one line per run, with columns id, rc, wall s, rows, swap-in pages, end time.
- `driver.log`: redacted.
- `representative-*.csv`: the run chosen by the representative-run rule.
- `ttft.jsonl` and `ttft.stderr`: the first-token probe (1115 only).
- `charts/`: CSVs identical to the representative runs, plus SVGs from upstream's
  `speed-bench/plot_speed.py`.
