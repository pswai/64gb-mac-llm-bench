#!/bin/bash
# Example quiet hook for scripts/run-bench.sh.
# Mirrors the setup used on 2026-09-28: a local LLM server kept alive by a
# launchd agent, plus scheduled agent jobs that would call it. It stops both
# for the benchmark and brings them back afterwards.
#
#   <hook> check   <run-dir>   report what would be done, change nothing
#   <hook> quiet   <run-dir>   pause jobs, stop the server
#   <hook> restore <run-dir>   start the server, verify it, resume jobs (idempotent)
#
# Configure with environment variables (nothing is hard-coded):
#   LAUNCHD_LABEL   e.g. gui/501/com.example.llm-server
#   LAUNCHD_PLIST   e.g. ~/Library/LaunchAgents/com.example.llm-server.plist
#   SERVER_PORT     port the server listens on, e.g. 8001
#   JOB_LIST_CMD    prints active job ids, one per line   (optional)
#   JOB_PAUSE_CMD   pauses one job id, given as the last argument (optional)
#   JOB_RESUME_CMD  resumes one job id                     (optional)
# The 2026-09-28 runs used an AI agent's scheduled-job CLI for the three JOB_* commands.
set -u
cmd=${1:?quiet|restore|check}; run=${2:?run dir}
: "${LAUNCHD_LABEL:?}" "${LAUNCHD_PLIST:?}" "${SERVER_PORT:?}"
state=$run/.hook-paused-jobs

listener() { lsof -tnP -iTCP:"$SERVER_PORT" -sTCP:LISTEN 2>/dev/null | head -1; }
jobs_active() { [ -n "${JOB_LIST_CMD:-}" ] && eval "$JOB_LIST_CMD" 2>/dev/null; }

case $cmd in
check)
    echo "active jobs: $(jobs_active | wc -l | tr -d ' '); server pid on :$SERVER_PORT: $(listener)"
    ;;
quiet)
    if [ -n "${JOB_LIST_CMD:-}" ]; then
        jobs_active > "$state"
        n=$(wc -l < "$state" | tr -d ' ')
        [ "$n" -gt 0 ] || { echo "job list is empty (list failure?); refusing to continue"; exit 1; }
        p=0; while read -r id; do eval "$JOB_PAUSE_CMD $id" >/dev/null 2>&1 && p=$((p+1)); done < "$state"
        left=$(jobs_active | wc -l | tr -d ' ')
        echo "paused $p of $n jobs, $left still active"
        [ "$p" -eq "$n" ] && [ "$left" -eq 0 ] || exit 1
    fi
    if launchctl print "$LAUNCHD_LABEL" >/dev/null 2>&1; then
        spid=$(launchctl print "$LAUNCHD_LABEL" 2>/dev/null | awk '$1=="pid"{print $3; exit}')
        launchctl bootout "$LAUNCHD_LABEL" && echo "server stop requested" && touch "$run/.hook-server-stopped"
        # the port closes before the process exits (it may save caches on shutdown): wait for the pid
        if [ -n "$spid" ]; then
            for _ in $(seq 1 120); do kill -0 "$spid" 2>/dev/null || break; sleep 1; done
            kill -0 "$spid" 2>/dev/null && { echo "server pid $spid still running after 120 s"; exit 1; }
            echo "server pid $spid exited"
        fi
    fi
    for _ in $(seq 1 60); do [ -z "$(listener)" ] && break; sleep 1; done
    [ -z "$(listener)" ] || { echo "server still listening"; exit 1; }
    ;;
restore)
    [ -e "$run/.hook-restored" ] && exit 0; touch "$run/.hook-restored"
    if [ -e "$run/.hook-server-stopped" ]; then
        launchctl bootstrap "gui/$(id -u)" "$LAUNCHD_PLIST"
        for _ in $(seq 1 180); do s=$(listener); [ -n "$s" ] && break; sleep 1; done
        l=$(launchctl print "$LAUNCHD_LABEL" 2>/dev/null | awk '$1=="pid"{print $3; exit}')
        if [ -n "${s:-}" ] && [ "$s" = "$l" ]; then echo "server restored: pid $l on :$SERVER_PORT"
        else echo "SERVER RESTORE CHECK FAILED: launchd pid '$l', listener '${s:-}'"; fi
    fi
    if [ -s "$state" ]; then
        while read -r id; do eval "$JOB_RESUME_CMD $id" >/dev/null 2>&1; done < "$state"
        echo "jobs active now: $(jobs_active | wc -l | tr -d ' ')"
    fi
    ;;
esac
