# History

## 2026-10-03/04: #1056 at `37f66ba` (resident prefill back to main's arithmetic)

- **Correctness (18:41, ~5 min of server downtime):** identical to base `0aaea5a` on all 3 prompts;
  the 10-02 drift is gone.
- **Speed (23:00–02:25, all runs valid):** gen +6.2 to +8.7%, prefill +1.0 to +2.0% vs base
  (32/32 separate), the same as `0231312`. With MTP on, ~6–7% prefill cost remains.

## 2026-10-02/03: #1056 retest at `0231312` (M2–M4 tuning by device name)

- **No env var or patch, one session, all runs valid:** head vs base gen +6.3 to +8.9%, prefill +1.1
  to +2.0% (sweep, raised limit). Server: MTP off decode +6.8 to +8.1%; with MTP on, still ~7%
  prefill cost from the MTP prompt preparation.
- **Correctness:** head = 09-30 opt-in patch (bit/byte-identical). Head vs base differs on all 3
  prompts, from non-tuning PR changes; my pre-run expectation of single-chunk parity was wrong.

## 2026-09-30 (evening): #1056's M1 Max-gated paths on the M4 Max

- An opt-in local patch (`DS4_METAL_M1MAX_TUNING=1`, 7 gates) was tested on the same binary, off vs on.
- **Correctness gate passed:** logits, logprobs and text identical on 3 prompts, MTP off and on.
- **Speed:** decode +6.8 to +7.5% (sweep), +5.3 to +7.2% (server); prefill unchanged.
- One flag-on sweep run was excluded by the swap rule and replaced; that changed the run order
  (noted in the results).
- **Harness fix:** the server A/B now uses fixed per-slot prompts, so outputs compare across arms.

## 2026-09-30: antirez/ds4#1056 measured before merge (`b96a12b` vs `0aaea5a`)

- **Official sweep** at the macOS default limit, 3 + 3 runs, all valid: the PR is +1.1–1.75% prefill
  and +0.2–0.8% gen at every frontier. The base arm reproduced the 09-28 lead row within 0.24% / 0.44%.
- **Daily-server A/B:** a small gain with MTP off; with MTP on, the PR's default predictor
  preparation costs ~9% prefill, and requests are 3.5–8.8% slower. `DS4_QWEN4_MTP_PREFILL=off` is
  roughly neutral.
- **First measured batch with the generalized driver.** New optional per-config hooks
  (`config_ds4_dir`, `config_expect_commit`, `config_env`) allow A/B between two checkouts. The
  example quiet hook now waits for the server process to exit, not just its port; that race aborted
  the first attempt.

## 2026-09-28: first measurements (ds4 `0aaea5a`, Mac Studio M4 Max 64 GB)

- **11:15–15:05, main batch** at a raised GPU limit (56.00 GiB): Qwen3.8 Flash Next Q2 with the
  official command (3 of 3 valid) and with `--prefill-chunk 2048`; DeepSeek V4 Flash Q2 with
  `--ssd-streaming`; the cold/warm first-token probe.
- **15:07–15:51, replacement batch:** one rep each for the two configurations that had lost runs
  to the swap rule. DeepSeek recovered to 3 valid runs; Qwen chunk 2048 stayed at 2 of 4.
- **20:08–21:59, default-limit sweep:** macOS default GPU limit (51.84 GiB measured). Qwen chunk
  2048 3 of 3 valid, plus one probe of the unmodified command, which completed without swapping.
  This measurement contradicted an earlier inference that the unmodified command fits "only
  because of the raised limit"; that claim was withdrawn.
- **Upstream:** submitted as [antirez/ds4#1142](https://github.com/antirez/ds4/pull/1142), with a
  follow-up comment carrying the default-limit numbers.
- **Repository created** from those results. The driver was generalized; see the
  "published driver vs the ones that ran" section in METHODOLOGY.md.
