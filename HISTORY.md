# History

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
