#!/bin/bash
# Auto-wake for the manager and the chief. No model in it. Arm it as a BACKGROUND command before you end a turn; when it exits you
# are woken with the line it printed. It exits on the first of:
#   IDLE       an agent in the roster has done nothing for IDLE_MIN minutes while there is work it could take
#   HEARTBEAT  BEAT_MIN minutes have passed
# usage (normally): swarm wake <name> <who> [BEAT_MIN=8] [IDLE_MIN=3]      direct: SWARM_CONFIG=... wake.sh <who> [BEAT] [IDLE]
. "$(dirname "$(readlink -f "$0")")/lib.sh" || exit 1
WHO=${1:-agent}; BEAT=${2:-8}; IDLE_MIN=${3:-3}
OUT=$SW_RUN; Q=$SW_TOOLS/q.sh; SUB=$SW_SUBAGENTS
trap 'echo "wake $WHO: watch ended by signal"; exit 0' TERM INT
start=$(date +%s)
while :; do
  now=$(date +%s); ran=$(( (now - start) / 60 ))
  if [ $(( now - start )) -ge 60 ]; then
    L=$($Q list 2>/dev/null); ready=$(echo "$L" | grep -c "^open"); names=""
    while IFS='|' read -r n id role by at; do
      [ "$role" = "worker" ] || [ "$role" = "verifier" ] || continue
      t=$(stat -L -c %Y "$SUB/agent-$id.jsonl" 2>/dev/null || echo 0); m=$(( (now - t) / 60 ))
      if [ "$m" -ge "$IDLE_MIN" ]; then
        if [ "$role" = "worker" ] && { [ "$ready" -gt 1 ] || echo "$L" | grep -q "^in_progress.* $n "; }; then names="$names $n($id, idle ${m} min)"; fi
        if [ "$role" = "verifier" ] && [ "$($Q toverify_count 2>/dev/null || echo 0)" -gt 0 ]; then names="$names $n($id, idle ${m} min)"; fi
      fi
    done < "$OUT/roster.txt"
    [ -n "$names" ] && { echo "wake $WHO $(date '+%H:%M'): IDLE with work waiting:$names. Wake each now: q tell $WHO <name> \"<what to do>\" and SendMessage its id with the same text."; exit 0; }
  fi
  [ "$ran" -ge "$BEAT" ] && { echo "wake $WHO $(date '+%H:%M'): HEARTBEAT ${ran} min: read your inbox, look at the newest work, guide whoever needs it."; exit 0; }
  sleep 20 & wait $!
done
