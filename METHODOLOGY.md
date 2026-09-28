# Methodology

The rules here were fixed before each batch of runs. Where a rule changed after I had seen
data, this document says so.

## Instrument

- **Engine:** DwarfStar (ds4), [antirez/ds4](https://github.com/antirez/ds4), built with plain
  `make ds4-bench` from a clean checkout at the recorded commit. The checkout is a separate
  detached worktree, never a working branch.
- **Benchmark:** upstream's `ds4-bench` with the documented sweep, unchanged:
  `--prompt-file speed-bench/promessi_sposi.txt --ctx-start 2048 --ctx-max 65536 --step-incr 2048 --gen-tokens 128`.
  - Each of the 32 rows measures the newest 2,048-token prefill interval, then a 128-token greedy,
    non-EOS generation probe.
  - Beyond a 1 GiB session snapshot (~30K context for Qwen3.8 Q2), `ds4-bench` restores by
    replaying the prefix instead. The replay happens outside the timed windows (checked in
    `ds4_bench.c`); it adds wall time, not error.
  - ds4 compiles its Metal shaders from `metal/*.metal` at runtime, so the benchmark runs with the
    checkout as its working directory.
- **Models:** downloaded with upstream's `./download_model.sh`. Each is checked against the
  Hugging Face LFS sha256 before the first batch that uses it (see `scripts/bench.conf.example`).

## Quiet machine

A benchmark counts only when nothing else is using the GPU or competing for memory.
- **Stopped for the window:** the local LLM server (kept alive by launchd) and every scheduled
  agent job that could call it. The pause is verified: the driver or hook aborts unless the
  number of paused jobs equals the number that were active and none remain active.
- **Restored on every exit path** (finish, error, Ctrl-C, hard stop), exactly once. A restored
  server must be the process launchd started and the one listening on its port.
- **GPU memory limit** (default-limit sweep only): set before the runs and restored *before* the
  server restarts. Both the sysctl value and Metal's `recommendedMaxWorkingSetSize` (the
  effective limit, printed by `scripts/wsz.m`) are logged before and after.
- **What was still running on 2026-09-28**, from process snapshots taken at the start of each run.
  The raw snapshots are not published; see below.
  - Two Claude Code CLI sessions: one supervising the runs, one idle. 0.1–13% CPU at snapshot time,
    ≤ 550 MB RSS.
  - An idle agent gateway process: ≤ 2.6% CPU, ≤ 264 MB.
  - macOS services: locationd, PerfPowerServices, searchpartyd, contactsd, the Wi-Fi driver
    extension, logd and similar, each ≤ 3% CPU.
  - A desktop chat/coding app was quit for the main batch. It wasn't running in the default-limit
    sweep.
- **Load and state:** load average ~1.3–1.6 at the start. Time Machine had no destination. The Mac
  Studio was on mains power, in normal power mode.

## Order, repeats, cooldown

- Three rounds in alternating configuration order (forward, reversed, forward), with a 120 s
  cooldown after every run.
- **Hard stop:** a watchdog ends the window at a set time and triggers the restore.

## Sampling

Every ~5 s during a run, the driver records:
- raw `vm_stat` fields (free, active, inactive, wired, compressor, swap-ins, swap-outs,
  pageouts);
- disk MB/s (`iostat disk0`);
- swap usage;
- whether `pmset -g therm` reports any thermal or performance warning.

There is no "free %" column. On Apple Silicon, Metal allocations move between "wired" and
"inactive" from second to second even when idle (observed ~43 GiB flipping), so that split can't
be trusted. `/usr/bin/time -l` wraps each run, giving the process's own swaps and page faults.
Not recorded: GPU power, temperature and clocks (`powermetrics` needs root; not used).

## Validity rule (fixed before the first run)

A run is valid only if:
1. `ds4-bench` exits 0;
2. all 32 rows are present;
3. system-wide swap-ins during the run are **≤ 100 MiB**.

The rule is system-wide on purpose: it catches a machine that pages at all. In every excluded run
so far, `ds4-bench` itself had 0 swaps, so the swap-ins came from other processes being paged
back in. Excluded runs stay in `results/` and are listed in each date's README.

## Replacement rule

- **Main batch, 2026-09-28:** no replacements were planned. After it, one replacement per affected
  configuration was set in writing *before* the replacement batch
  ([results/2026-09-28/REPLACEMENT-NOTE.txt](results/2026-09-28/REPLACEMENT-NOTE.txt)): all valid
  runs from both batches are reported, and nothing is retried further.
- **From the default-limit sweep on:** built into the driver. While a configuration has fewer
  than 3 valid runs, add a rep, at most 2 extra.

## Probe runs

A probe is a single run under a riskier setting, reported as one observation and never as a
median. It is killed as soon as system-wide swap-ins pass 1 GiB, to avoid heavy swap writes to
a soldered SSD. On 2026-09-28 that was the unmodified command at the default GPU limit. It
completed, and the guard never triggered.

## Representative run

Charts and any single-CSV submission use one unmodified run per configuration: the valid run
closest to the per-frontier medians of prefill and generation (smallest sum of squared relative
deviations).
**Adopted after seeing data:** the first rule, the median of mean generation t/s, picked the
DeepSeek run with the deepest prefill drop, which would have misrepresented prefill. The change
applies to all configurations.

## First-token probe (not part of the official format)

`scripts/ttft_probe.py` starts a fresh `ds4-bench` on a 2,048-token prompt (the first 16,000
bytes of the same text) with one frontier and one generated token, and times process start →
the CSV row. "Cold" follows `sudo purge`; "warm" is an immediate repeat. Load time is *derived*
as total − prefill − first token.

## What is not comparable

- **Resident vs SSD-streamed:** the same model in a different mode measures capacity, not the
  chip.
- **Other chips and memory sizes:** upstream's 128 GB M5 Max and DGX Spark rows, and other 64 GB
  Macs such as the M1 Max in antirez/ds4#1068.
- **`ds4-bench` vs `ds4-server`:** the server with `--mtp` speculative decoding, prefix caching
  and real prompts behaves differently. `ds4-bench` does not accept `--mtp`.
- **Different engine commits:** always compare at the same commit or say that you didn't.

## What was excluded from this repository, and why

This repo publishes results, not the machine's private state. The raw material stays with the
owner.
| Excluded | Why | Replaced by |
|---|---|---|
| Per-run process snapshots (`*.ps`) | full command lines include home paths and app names | the process summary above |
| Per-run command files (`*.cmd`) | absolute home paths | the exact command in this file and in each date's README |
| Environment captures (`env*.txt`) | hostname, home paths, full process lists | the sanitized environment in each date's README |
| Paused-job lists and job IDs | IDs of the owner's private scheduled jobs | `<cron-id>` in driver logs |
| Download and nohup logs | home paths, download progress only | nothing |
| The as-run driver copies | hard-coded home paths and private service names | the generalized `scripts/run-bench.sh` (differences below) |

Driver logs are published with job IDs replaced by `<cron-id>` and watchdog PIDs removed.

## The published driver vs the ones that ran

The 2026-09-28 data came from two revisions of an owner-specific driver. `scripts/run-bench.sh`
is the same logic, with the machine-specific parts moved out:
- Paths, models and expected checksums: in a config file (`bench.conf.example`).
- Server and job quieting: in a hook (`scripts/examples/quiet-launchd-server-and-crons.sh`),
  called as `quiet`, `restore` or `check`.
- Environment capture no longer records the hostname or launchd listings. `.cmd` files record the
  model's file name instead of its path.
- `RESTORE_LIMIT` must be given explicitly, and the first-token probe configs are selectable
  (`TTFT_CONFIGS`).

Unchanged: the sweep, sampler, validity rule, order, cooldowns and swap-guarded probe.

The main and replacement batches (11:15, 15:07) ran an earlier revision that had no built-in
replacement loop, probe option, GPU-limit option or job-count check. The replacement batch was
started by hand under the rule written above. The default-limit batch (20:08) ran the revision
this script generalizes. **The generalized script has been dry-run tested, not yet used for a
full measured batch.** The next dated entry in HISTORY.md will say when it is.
