#!/bin/bash
# Correctness gate for DS4_METAL_M1MAX_TUNING=1 on the M4 Max (run inside a quiet window).
# Same binary, flag off vs on, three fixed prompts (no nonces):
#   first-token full logits (--dump-logits), 64 greedy decode steps of top-20
#   logprobs (--dump-logprobs, exercises the decode-path gates), and greedy text
#   with MTP off and on (-n 128). Exit 0 only if everything is bit-identical.
set -u
X=$HOME/Dev/ds4-pr1056-m1tune
M=$HOME/Dev/ds4/gguf/Qwen3.8-Flash-Next-Q2.gguf
D=$(cd "$(dirname "$0")" && pwd)
OUT=${1:?out dir}; mkdir -p "$OUT"
COMMON="-m $M --metal --ctx 16384 --prefill-chunk 2048 --temp 0 --nothink"
run() {  # arm prompt kind extra...
    local arm=$1 p=$2 kind=$3; shift 3
    local env=(DS4_QWEN4_PREFILL_CHUNK=2048); case $arm in on*) env+=(DS4_METAL_M1MAX_TUNING=1) ;; esac
    ( cd "$X" && exec env "${env[@]}" ./ds4 $COMMON --prompt-file "$D/prompts/$p.txt" "$@" ) \
        > "$OUT/$p.$arm.$kind.out" 2> "$OUT/$p.$arm.$kind.err"
    echo "$(date '+%T') $p $arm $kind rc=$?" >> "$OUT/runs.log"
}
for p in rome-short roma575 sposi-long; do
    for arm in off on on off; do   # ABBA; the second pass of each arm checks run-to-run determinism
        tag=$arm; [ -e "$OUT/$p.$arm.logits.json" ] && tag=$arm.rep
        run "$tag" "$p" logits -n 1 --dump-logits "$OUT/$p.$tag.logits.json"
        run "$tag" "$p" logprobs -n 64 --dump-logprobs "$OUT/$p.$tag.logprobs.json"
        run "$tag" "$p" text -n 128
        run "$tag" "$p" mtptext -n 128 --mtp
    done
done
python3 "$D/compare.py" "$OUT"
