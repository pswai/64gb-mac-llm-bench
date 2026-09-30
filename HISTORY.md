# History

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
