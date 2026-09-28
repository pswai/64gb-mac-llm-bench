#!/bin/bash
# 64 GB Mac LLM benchmark driver for DwarfStar (ds4) `ds4-bench`.
#
# Runs the official ds4-bench context sweep once per configuration and repeat,
# with a memory/disk sampler, a swap-in validity rule, alternating order,
# cooldowns, a hard stop, optional GPU wired-limit change, an optional
# swap-guarded probe run and an optional cold/warm first-token probe.
# Machine-specific things (model paths, expected checksums, how to quiet the
# machine) live in a config file and in hook scripts, not here.
#
#   cp scripts/bench.conf.example bench.conf    # edit paths
#   BENCH_CONF=bench.conf DRY_RUN=1 scripts/run-bench.sh      # preflight only
#   BENCH_CONF=bench.conf STOP_AT=06:00 nohup scripts/run-bench.sh >/dev/null 2>&1 &
#
# See METHODOLOGY.md for the rules this script implements.
set -u

S=$(cd "$(dirname "$0")" && pwd)                 # scripts/ directory
BENCH_CONF=${BENCH_CONF:-$S/bench.conf}
[ -f "$BENCH_CONF" ] || { echo "config not found: $BENCH_CONF (copy scripts/bench.conf.example)"; exit 2; }
# shellcheck source=/dev/null
. "$BENCH_CONF"                                  # must set DS4_DIR, CONFIGS and the config_* functions

: "${DS4_DIR:?set DS4_DIR in the config}"
EXPECT_COMMIT=${EXPECT_COMMIT:-}                 # full hash; empty = record only
OUT_DIR=${OUT_DIR:-$(cd "$S/.." && pwd)/results/local}
QUIET_HOOK=${QUIET_HOOK:-}                       # executable: "<hook> quiet <run-dir>" / "<hook> restore <run-dir>"
MIN_FREE_GIB=${MIN_FREE_GIB:-100}

REPS=${REPS:-3}
COOLDOWN=${COOLDOWN:-120}
STOP_AT=${STOP_AT:-06:00}
RUN_TTFT=${RUN_TTFT:-0}
TTFT_CONFIGS=${TTFT_CONFIGS:-$CONFIGS}
TTFT_PAIRS=${TTFT_PAIRS:-3}
SKIP_SHA=${SKIP_SHA:-0}
DRY_RUN=${DRY_RUN:-0}
WIRED_LIMIT=${WIRED_LIMIT:-}                     # e.g. 0 = macOS default; empty = leave alone
RESTORE_LIMIT=${RESTORE_LIMIT:-}                 # value to restore on exit (required with WIRED_LIMIT)
PROBE_CONFIG=${PROBE_CONFIG:-}                   # one extra run at the end, killed past PROBE_ABORT_MIB swap-ins
PROBE_ABORT_MIB=${PROBE_ABORT_MIB:-1024}
MIN_VALID=${MIN_VALID:-3}                        # replacement rule: extra reps until MIN_VALID valid
MAX_EXTRA=${MAX_EXTRA:-2}                        # ...but at most MAX_EXTRA extra reps per config
SWAP_INVALID_MIB=${SWAP_INVALID_MIB:-100}        # validity rule: system-wide swap-ins per run
WSZ=${WSZ:-$S/wsz}                               # build: see scripts/wsz.m

CTX_START=2048 CTX_MAX=65536 STEP=2048 GEN=128   # the documented upstream sweep
OFFICIAL="--prompt-file speed-bench/promessi_sposi.txt --ctx-start $CTX_START --ctx-max $CTX_MAX --step-incr $STEP --gen-tokens $GEN"
EXPECTED_ROWS=$(( (CTX_MAX - CTX_START) / STEP + 1 ))

RUN=$OUT_DIR/$(date +%Y%m%d-%H%M)${RUN_TAG:+-$RUN_TAG}
mkdir -p "$RUN"
log() { echo "$(date '+%F %T') $*" | tee -a "$RUN/driver.log"; }

page_kib=$(( $(sysctl -n hw.pagesize) / 1024 ))
SWAP_INVALID_PAGES=$(( SWAP_INVALID_MIB * 1024 / page_kib ))
vm_counter() { vm_stat | awk -v k="$1" -F: '$1==k {gsub(/[ .]/,"",$2); print $2}'; }
# Raw vm_stat fields in pages. On Apple Silicon, Metal memory moves between
# "wired" and "inactive" from second to second even when idle, so no free% is
# derived; system-wide swap-ins are the validity signal.
vm_fields() {
    vm_stat | awk -F: '{gsub(/[ .]/,"",$2)}
        $1=="Pages free"{f=$2} $1=="Pages active"{a=$2} $1=="Pages inactive"{i=$2}
        $1=="Pages wired down"{w=$2} $1=="Pages occupied by compressor"{c=$2}
        $1=="Swapins"{si=$2} $1=="Swapouts"{so=$2} $1=="Pageouts"{po=$2}
        END{printf "%s,%s,%s,%s,%s,%s,%s,%s", f,a,i,w,c,si,so,po}'
}

# ---------------------------------------------------------------- preflight
preflight() {
    local free; free=$(df -g "$OUT_DIR" | awk 'NR==2{print $4}')
    log "free disk ${free} GiB"
    [ "$free" -ge "$MIN_FREE_GIB" ] || { log "ABORT: under $MIN_FREE_GIB GiB free"; return 1; }
    local head; head=$(git -C "$DS4_DIR" rev-parse HEAD 2>/dev/null)
    [ -n "$head" ] || { log "ABORT: $DS4_DIR is not a ds4 git checkout"; return 1; }
    if [ -n "$EXPECT_COMMIT" ] && [ "$head" != "$EXPECT_COMMIT" ]; then log "ABORT: ds4 at $head, expected $EXPECT_COMMIT"; return 1; fi
    [ -z "$(git -C "$DS4_DIR" status --porcelain)" ] || { log "ABORT: ds4 checkout has local changes"; return 1; }
    [ -x "$DS4_DIR/ds4-bench" ] || { log "ABORT: ds4-bench not built (make ds4-bench)"; return 1; }
    local c m want
    for c in $CONFIGS $PROBE_CONFIG; do
        [ "$(config_flags "$c")" != UNKNOWN ] || { log "ABORT: unknown config $c"; return 1; }
        m=$(config_model "$c"); want=$(model_expect "$m" | awk '{print $1}')
        [ -f "$m" ] || { log "ABORT: model missing: $m"; return 1; }
        if [ -n "$want" ] && [ "$(stat -f %z "$m")" != "$want" ]; then log "ABORT: $m is not $want bytes"; return 1; fi
    done
    if pgrep -x ds4-bench >/dev/null; then log "ABORT: another ds4-bench is running"; return 1; fi
    if [ -n "$WIRED_LIMIT" ]; then
        [ -n "$RESTORE_LIMIT" ] || { log "ABORT: WIRED_LIMIT set without RESTORE_LIMIT"; return 1; }
        sudo -n -l /usr/sbin/sysctl "iogpu.wired_limit_mb=$WIRED_LIMIT" >/dev/null 2>&1 &&
        sudo -n -l /usr/sbin/sysctl "iogpu.wired_limit_mb=$RESTORE_LIMIT" >/dev/null 2>&1 ||
            { log "ABORT: no passwordless sudo for sysctl iogpu.wired_limit_mb=$WIRED_LIMIT/$RESTORE_LIMIT"; return 1; }
        [ -x "$WSZ" ] || { log "ABORT: $WSZ missing (see scripts/wsz.m)"; return 1; }
    fi
    [ -n "$QUIET_HOOK" ] || log "WARNING: no QUIET_HOOK; stop other GPU and memory-heavy work yourself"
    return 0
}

capture_env() {   # stays local; review before publishing (it lists running processes)
    {
        echo "# captured $(date '+%F %T %Z')"
        sw_vers; uname -srm
        sysctl hw.model machdep.cpu.brand_string hw.memsize hw.pagesize iogpu.wired_limit_mb iogpu.wired_lwm_mb vm.swapusage
        [ -x "$WSZ" ] && "$WSZ"
        echo "## ds4"; git -C "$DS4_DIR" log -1 --format='%H %cd %s'; git -C "$DS4_DIR" status --porcelain | wc -l
        shasum -a 256 "$DS4_DIR/ds4-bench" | awk '{print $1"  ds4-bench"}'
        echo "## models"; for c in $CONFIGS $PROBE_CONFIG; do m=$(config_model "$c"); echo "$(stat -f %z "$m") $(basename "$m")"; done | sort -u
        echo "## disk"; df -h "$OUT_DIR" | tail -1 | awk '{print "free", $4}'; diskutil info / | grep -E "Media Name|Solid State|Protocol"
        echo "## power/thermal"; pmset -g | grep -E "lowpowermode|powermode"; pmset -g therm
        echo "## load"; uptime | sed 's/.*load/load/'; vm_stat
        ps -Ao pid,pcpu,rss,comm -r | head -15
    } > "$RUN/env.txt" 2>&1
}

verify_sha() {
    [ "$SKIP_SHA" = 1 ] && { log "sha256 check skipped"; return 0; }
    local c m want got
    for m in $(for c in $CONFIGS $PROBE_CONFIG; do config_model "$c"; done | sort -u); do
        want=$(model_expect "$m" | awk '{print $2}')
        got=$(shasum -a 256 "$m" | awk '{print $1}')
        echo "$got  $(basename "$m")" >> "$RUN/gguf-sha256.txt"
        if [ -n "$want" ] && [ "$got" != "$want" ]; then log "ABORT: sha256 mismatch $(basename "$m") ($got)"; return 1; fi
        log "sha256 ${want:+ok }$got $(basename "$m")"
    done
}

# ---------------------------------------------------------------- quiet / restore
RESTORED=; CHILD=; SAMPLER=; WD_PID=; LIMIT_CHANGED=; HOOK_QUIETED=

quiet() {
    if [ -n "$QUIET_HOOK" ]; then
        HOOK_QUIETED=1   # restore runs the hook's restore even after a partial quiet
        "$QUIET_HOOK" quiet "$RUN" 2>&1 | while IFS= read -r l; do log "hook: $l"; done
        [ "${PIPESTATUS[0]}" -eq 0 ] || { log "ABORT: quiet hook failed"; return 1; }
    fi
    if pgrep -x ds4-server >/dev/null || pgrep -x ds4 >/dev/null; then log "ABORT: a ds4 process is still running"; return 1; fi
    if [ -n "$WIRED_LIMIT" ]; then
        log "wired limit before: $(sysctl -n iogpu.wired_limit_mb) MiB; $("$WSZ")"
        sudo -n /usr/sbin/sysctl "iogpu.wired_limit_mb=$WIRED_LIMIT" >/dev/null && LIMIT_CHANGED=1
        [ "$(sysctl -n iogpu.wired_limit_mb)" = "$WIRED_LIMIT" ] || { log "ABORT: sysctl did not take"; return 1; }
        log "wired limit after: $(sysctl -n iogpu.wired_limit_mb) MiB; $("$WSZ")"
    fi
    sleep 20   # let unified memory settle after other models unload
    log "quiet: vm free,active,inactive,wired,compressor,swapins,swapouts,pageouts = $(vm_fields)"
}

restore() {
    [ -n "$RESTORED" ] && return; RESTORED=1
    trap - EXIT INT TERM
    [ -n "$WD_PID" ] && kill "$WD_PID" 2>/dev/null
    if [ -n "$CHILD" ]; then kill -TERM "$CHILD" 2>/dev/null; sleep 5; kill -KILL "$CHILD" 2>/dev/null; fi
    pkill -TERM -x ds4-bench 2>/dev/null
    [ -n "$SAMPLER" ] && kill "$SAMPLER" 2>/dev/null
    if [ -n "$LIMIT_CHANGED" ]; then   # before the hook, so any server it restarts sees the normal limit
        sudo -n /usr/sbin/sysctl "iogpu.wired_limit_mb=$RESTORE_LIMIT" >/dev/null
        if [ "$(sysctl -n iogpu.wired_limit_mb)" = "$RESTORE_LIMIT" ]; then log "LIMIT RESTORED: $(sysctl -n iogpu.wired_limit_mb) MiB; $("$WSZ")"
        else log "LIMIT RESTORE FAILED: now $(sysctl -n iogpu.wired_limit_mb); run: sudo sysctl iogpu.wired_limit_mb=$RESTORE_LIMIT"; fi
    fi
    if [ -n "$HOOK_QUIETED" ]; then
        "$QUIET_HOOK" restore "$RUN" 2>&1 | while IFS= read -r l; do log "hook: $l"; done
    fi
    log "disk after: $(df -h "$OUT_DIR" | awk 'NR==2{print $4" free"}')"
}

# ---------------------------------------------------------------- sampler
start_sampler() {
    local out=$1
    (
        echo "time,free_pg,active_pg,inactive_pg,wired_pg,compressor_pg,swapins,swapouts,pageouts,disk_MBps,swap_used,therm_warn"
        while :; do
            local vf mb su tw
            vf=$(vm_fields)
            mb=$(iostat -d -c 2 -w 1 disk0 2>/dev/null | tail -1 | awk '{print $3}')
            su=$(sysctl -n vm.swapusage | awk '{print $6}')
            tw=$(pmset -g therm 2>/dev/null | grep -v -c "No .* has been recorded")
            echo "$(date +%T),$vf,$mb,$su,$tw"
            sleep 4
        done
    ) > "$out" 2>/dev/null &
    SAMPLER=$!
}
stop_sampler() { [ -n "$SAMPLER" ] && kill "$SAMPLER" 2>/dev/null; wait "$SAMPLER" 2>/dev/null; SAMPLER=; }

# ---------------------------------------------------------------- runs
SKIP_CONFIGS=""
run_one() {
    local cfg=$1 rep=$2 id="$1-r$2" model flags t0 t1 rc si0 si1 dsi
    case " $SKIP_CONFIGS " in *" $cfg "*) log "skip $id (earlier rep swapped)"; return ;; esac
    model=$(config_model "$cfg"); flags=$(config_flags "$cfg")
    ps -Ao pid,pcpu,rss,comm -r | head -10 > "$RUN/$id.ps"   # local only; do not publish raw
    echo "./ds4-bench -m $(basename "$model") $flags $OFFICIAL" > "$RUN/$id.cmd"
    si0=$(vm_counter Swapins)
    start_sampler "$RUN/$id.samples.csv"
    log "start $id: ds4-bench -m $(basename "$model") $flags"
    t0=$(date +%s)
    ( cd "$DS4_DIR" && exec /usr/bin/time -l ./ds4-bench -m "$model" $flags $OFFICIAL --csv "$RUN/$id.csv" ) 2> "$RUN/$id.stderr" &
    CHILD=$!
    if [ -n "${ABORT_PAGES:-}" ]; then
        while kill -0 "$CHILD" 2>/dev/null; do
            if [ $(( $(vm_counter Swapins) - si0 )) -gt "$ABORT_PAGES" ]; then
                log "PROBE ABORT $id: swap-ins passed ${PROBE_ABORT_MIB} MiB; killing"
                kill -TERM "$CHILD"; sleep 5; kill -KILL "$CHILD" 2>/dev/null; break
            fi
            sleep 2 & wait $!
        done
    fi
    wait "$CHILD"; rc=$?; CHILD=
    t1=$(date +%s)
    stop_sampler
    si1=$(vm_counter Swapins); dsi=$(( si1 - si0 ))
    local rows; rows=$(( $(wc -l < "$RUN/$id.csv" 2>/dev/null || echo 1) - 1 ))
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$id" "$rc" "$(( t1 - t0 ))" "$rows" "$dsi" "$(date +%T)" >> "$RUN/runs.tsv"
    log "end $id: rc=$rc wall=$(( t1 - t0 ))s rows=$rows swapin_pages=$dsi"
    if [ "$dsi" -gt "$SWAP_INVALID_PAGES" ]; then
        log "INVALID $id: swap-ins ${dsi} pages; skipping remaining reps of $cfg"
        SKIP_CONFIGS="$SKIP_CONFIGS $cfg"
    fi
}

cooldown() { log "cooldown ${COOLDOWN}s"; sleep "$COOLDOWN" & wait $!; }

run_ttft() {
    local cfg model flags p kind purge_ok=0
    sudo -n -l /usr/sbin/purge >/dev/null 2>&1 && purge_ok=1
    log "ttft: purge available: $purge_ok (cold runs skipped if 0)"
    head -c 16000 "$DS4_DIR/speed-bench/promessi_sposi.txt" > "$RUN/ttft-prompt.txt"
    for cfg in $TTFT_CONFIGS; do
        model=$(config_model "$cfg"); flags=$(config_flags "$cfg")
        for p in $(seq 1 "$TTFT_PAIRS"); do
            for kind in cold warm; do
                if [ "$kind" = cold ]; then
                    [ "$purge_ok" = 1 ] || continue
                    sudo -n /usr/sbin/purge; sleep 5
                fi
                ( cd "$DS4_DIR" && exec python3 "$S/ttft_probe.py" --label "$cfg-$kind-p$p" \
                    --out "$RUN/ttft.jsonl" -- ./ds4-bench -m "$model" $flags \
                    --prompt-file "$RUN/ttft-prompt.txt" --ctx-start 2048 --ctx-max 2048 --gen-tokens 1 \
                    --csv /dev/stdout ) 2>> "$RUN/ttft.stderr" &
                CHILD=$!; wait "$CHILD"; CHILD=
                log "ttft $cfg $kind p$p: $(tail -1 "$RUN/ttft.jsonl" 2>/dev/null)"
                sleep 20 & wait $!
            done
        done
    done
}

# ---------------------------------------------------------------- main
preflight || exit 1
capture_env
if [ "$DRY_RUN" = 1 ]; then
    [ -n "$QUIET_HOOK" ] && "$QUIET_HOOK" check "$RUN" 2>&1 | while IFS= read -r l; do log "hook check: $l"; done
    log "DRY RUN: preflight ok; ds4 $(git -C "$DS4_DIR" rev-parse --short HEAD); configs: $CONFIGS${PROBE_CONFIG:+ + probe $PROBE_CONFIG}; reps $REPS; stop at $STOP_AT"
    exit 0
fi

trap 'restore' EXIT
trap 'log "signal: stopping"; restore; exit 130' INT TERM

stop_epoch=$(date -j -f "%H:%M" "$STOP_AT" +%s); now=$(date +%s)
[ "$stop_epoch" -le "$now" ] && stop_epoch=$(( stop_epoch + 86400 ))
( sleep $(( stop_epoch - now )); kill -TERM $$ ) & WD_PID=$!
log "hard stop at $(date -r "$stop_epoch" '+%F %T')"

quiet || exit 1
capture_env; mv "$RUN/env.txt" "$RUN/env-quiet.txt"
verify_sha || exit 1

order=($CONFIGS)
for rep in $(seq 1 "$REPS"); do
    if [ $(( rep % 2 )) -eq 0 ]; then seq_=$(printf '%s\n' "${order[@]}" | tail -r); else seq_=$(printf '%s\n' "${order[@]}"); fi
    for cfg in $seq_; do run_one "$cfg" "$rep"; cooldown; done
done
valid_count() { awk -F'\t' -v c="$1" -v lim="$SWAP_INVALID_PAGES" -v rows="$EXPECTED_ROWS" 'index($1, c"-r")==1 && $2==0 && $4==rows && $5<=lim' "$RUN/runs.tsv" 2>/dev/null | wc -l | tr -d ' '; }
for cfg in $CONFIGS; do
    extra=0; rep=$REPS
    while [ "$(valid_count "$cfg")" -lt "$MIN_VALID" ] && [ "$extra" -lt "$MAX_EXTRA" ]; do
        extra=$((extra+1)); rep=$((rep+1)); SKIP_CONFIGS=""
        log "replacement rep $rep for $cfg (valid so far $(valid_count "$cfg"))"
        run_one "$cfg" "$rep"; cooldown
    done
done
if [ -n "$PROBE_CONFIG" ]; then
    ABORT_PAGES=$(( PROBE_ABORT_MIB * 1024 / page_kib )); SKIP_CONFIGS=""
    log "probe: $PROBE_CONFIG x1, abort past $PROBE_ABORT_MIB MiB swap-ins"
    run_one "$PROBE_CONFIG" 1
    ABORT_PAGES=
fi
[ "$RUN_TTFT" = 1 ] && run_ttft
log "all runs done"
restore
