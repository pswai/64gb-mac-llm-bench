#!/bin/bash
# Correctness for the 0231312 retest (see PLAN-RETEST.md). Arms:
#   base = 0aaea5a, head = 0231312 (+ head.rep), ref-off / ref-on = 1c12602 with DS4_METAL_M1MAX_TUNING unset / =1
# Per arm and prompt: --dump-logits, 64-step --dump-logprobs (MTP off), greedy text -n 128 (MTP off) and with --mtp.
set -u
M=$HOME/Dev/ds4/gguf/Qwen3.8-Flash-Next-Q2.gguf
D=$(cd "$(dirname "$0")" && pwd)
OUT=${1:?out dir}; mkdir -p "$OUT"
dir_of() { case $1 in base) echo $HOME/Dev/ds4-bench-0aaea5a ;; head*) echo $HOME/Dev/ds4-pr1056-0231312 ;; ref-*) echo $HOME/Dev/ds4-pr1056-m1tune ;; esac; }
COMMON="-m $M --metal --ctx 16384 --prefill-chunk 2048 --temp 0 --nothink"
run() {  # arm prompt kind extra...
    local arm=$1 p=$2 kind=$3; shift 3
    local env=(DS4_QWEN4_PREFILL_CHUNK=2048); [ "$arm" = ref-on ] && env+=(DS4_METAL_M1MAX_TUNING=1)
    ( cd "$(dir_of "$arm")" && exec env "${env[@]}" ./ds4 $COMMON --prompt-file "$D/prompts/$p.txt" "$@" ) \
        > "$OUT/$p.$arm.$kind.out" 2> "$OUT/$p.$arm.$kind.err"
    echo "$(date '+%T') $p $arm $kind rc=$?" >> "$OUT/runs.log"
}
for p in rome-short roma575 sposi-long; do
    for arm in head base ref-on ref-off head.rep; do
        run "$arm" "$p" logits -n 1 --dump-logits "$OUT/$p.$arm.logits.json"
        run "$arm" "$p" logprobs -n 64 --dump-logprobs "$OUT/$p.$arm.logprobs.json"
        run "$arm" "$p" text -n 128
        run "$arm" "$p" mtptext -n 128 --mtp
    done
done
python3 "$D/compare-retest.py" "$OUT"
