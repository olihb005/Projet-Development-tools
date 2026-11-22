#!/bin/bash
# The swarm's slice queue, on the bd tracker in the swarm's repo. No model in it. Normally run as: swarm q <name> <command> ...
# Workers PULL their next slice here the moment they finish one, so nobody waits for the manager to hand work out.
#   q.sh add "<title>" "<description>" [priority 0-4, 0 first]   (chief or manager) description must hold a line "files: a.py, b.py"
#   q.sh next <worker-name>     claim the first ready slice whose files no in-progress slice holds; prints it, or NONE
#   q.sh done <worker-name> <id> "<commit and one-line result>"
#   q.sh back <worker-name> <id> "<why>"      give a slice back unfinished (it returns to the queue with your note)
#   q.sh list                   ready and in-progress slices
#   q.sh tell <from> <to> "<text>"   message another agent (chief, manager, w-N, v-N, main, all)
#   q.sh who                    everyone in the swarm: role, agent id, idle time, slice held
#   q.sh join <name> <id> <role> <by>   the launcher records an agent it started
#   q.sh committed <name> <slice> <commit>   record a commit made after a verifier said the slice holds
#   q.sh inbox <name>           read your unread messages (also shown on every next, done, back, toverify, verified)
#   q.sh toverify <verifier>    claim the oldest closed slice not yet verified; prints it, or NONE
#   q.sh verified <verifier> <id> "<holds|partly|does not hold>: what was seen"
. "$(dirname "$(readlink -f "$0")")/lib.sh" || exit 1
SELF="$SW_TOOLS/q.sh"
command -v bd >/dev/null 2>&1 || { echo "bd (the beads tracker) is not installed or not on PATH; the queue needs it. Messages still work only if you run them where bd exists." >&2; }
cd "$SW_REPO" || { echo "repo $SW_REPO not found" >&2; exit 1; }
OUT_DIR=$SW_RUN
SINCE_ISO=$(echo "$SW_STARTED" | sed 's/ /T/' | cut -c1-16)
cmd=$1; shift
MSG="$OUT_DIR/messages.log"; touch "$MSG"
deliver() {  # print the messages addressed to $1 (or to all) that it has not seen yet, and mark them seen
  local who=$1 pos="$OUT_DIR/.inbox_$1.pos" n seen; [ -z "$who" ] && return
  seen=$(cat "$pos" 2>/dev/null || echo 0); n=$(wc -l < "$MSG")
  if [ "$n" -gt "$seen" ]; then
    m=$(tail -n +$((seen+1)) "$MSG" | awk -F'|' -v w="$who" '($4==w || $4=="all") && $3!=w {print "  " $2 " from " $3 ": " $5}')
    [ -n "$m" ] && { echo "=== MESSAGES FOR YOU, $who (direction: act on them now, then answer with q tell) ==="; echo "$m"; echo "==="; }
    echo "$n" > "$pos"
  fi
}
HINT="(mesh: anyone can message anyone. q who lists everyone and what each is on; q tell <your name> <any name or all> \"<text>\" sends; q inbox <your name> reads yours. Check your inbox every few minutes while you work.)"
case "$cmd" in
  add)  # two agents writing at once can make bd answer nothing: try up to three times before giving up
        for try in 1 2 3; do
          out=$(bd create "$1" -d "$2" -p "${3:-2}" --json 2>/dev/null)
          if printf '%s' "$out" | python3 -c "import json,sys;d=json.load(sys.stdin);print('queued',d['id'],d['title'])" 2>/dev/null; then exit 0; fi
          sleep $((try * 2))
        done
        echo "NOT QUEUED after three tries: tell the manager the slice text so it is not lost"; exit 1 ;;
  tell) echo "$(date +%s)|$(date +%H:%M)|$1|$2|$(echo "$3" | tr "\n|" "  ")" >> "$MSG"; echo "sent to $2" ;;
  inbox) deliver "$1"; echo "(inbox checked)" ;;
  join) # the launcher records each agent it starts: q join <name> <agent id> <role> <launched by>
        R="$OUT_DIR/roster.txt"; touch "$R"; grep -v "^$1|" "$R" > "$R.tmp"; echo "$1|$2|$3|$4|$(date +%H:%M)" >> "$R.tmp"; mv "$R.tmp" "$R"; echo "joined: $1 ($3)" ;;
  who)  # everyone in the swarm: name, role, agent id (for SendMessage), how long since it last did anything, and what it holds
        echo "Mesh: anyone can message anyone. q tell <you> <name> \"<text>\" records it; if the receiver shows IDLE, also SendMessage its id with the same text to wake it."
        SUBD=$SW_SUBAGENTS; now=$(date +%s)
        held=$(bd list --status in_progress --json 2>/dev/null | python3 -c "
import json,sys
for i in json.load(sys.stdin): print((i.get('assignee') or '?')+'|'+i['id']+' '+i['title'][:70])" 2>/dev/null)
        echo "  main       the main session: SendMessage to \"main\" (only the chief presents finished work to it)"
        while IFS='|' read -r n id role by at; do [ -z "$n" ] && continue
          t=$(stat -L -c %Y "$SUBD/agent-$id.jsonl" 2>/dev/null || echo 0); m=$(( (now - t) / 60 )); st="working"; [ "$m" -ge 3 ] && st="IDLE ${m} min"; [ "$t" = 0 ] && st="IDLE (no transcript)"
          h=$(echo "$held" | grep "^$n|" | head -1 | cut -d'|' -f2); printf "  %-9s %-9s id %s  %-12s %s\n" "$n" "$role" "$id" "$st" "${h:+holds $h}"
        done < "$OUT_DIR/roster.txt" ;;
  committed) echo "$(date +%H:%M)|$1|$2|$3" >> "$OUT_DIR/commits_verified.log"; echo "recorded: $2 committed as $3 by $1 (verified work only; the chief presents it to main before any push)" ;;
  list) echo "$HINT"; for s in in_progress open; do bd list --status $s --json 2>/dev/null | python3 -c "
import json,sys
for i in sorted(json.load(sys.stdin),key=lambda i:(i.get('priority',9),i.get('created_at') or '',i['id'])):
    print('$s'.ljust(11), i['id'], 'P%s'%i.get('priority'), (i.get('assignee') or '-').ljust(10), i['title'][:90])"; done ;;
  next) who=$1; deliver "$who"; echo "$HINT"; [ -z "$who" ] && { echo "usage: q next <worker-name>"; exit 2; }
    pick=$(python3 - <<'PYEOF'
import json,subprocess,re
def bd(*a):
    try: return json.loads(subprocess.run(["bd",*a,"--json"],capture_output=True,text=True,timeout=30).stdout or "[]")
    except Exception: return []
def files(i):
    m=re.search(r"files:\s*(.*)", i.get("description") or "", re.I)
    return {f.strip().split("/")[-1] for f in (m.group(1) if m else "").split(",") if f.strip() and f.strip().lower()!="none"}
held=set()
for i in bd("list","--status","in_progress"): held |= files(i)
for i in sorted(bd("ready"),key=lambda i:(i.get("priority",9),i.get("created_at") or "",i["id"])):   # same priority: oldest first, the order the chief wrote them (dependency order)
    if i.get("status")=="in_progress" or i["title"].startswith(("Board is live","TEST")): continue
    if files(i) & held: continue
    print(i["id"]); break
PYEOF
)
    [ -z "$pick" ] && { echo "NONE: no ready slice is free of files held by live slices. Tell the manager you are free and stop."; exit 0; }
    BD_ACTOR="$who" bd update "$pick" --claim >/dev/null 2>&1 || { echo "NONE: could not claim $pick (taken). Run q next again."; exit 0; }
    bd show "$pick" 2>/dev/null | sed -n '1,60p' ;;
  done) deliver "$1"; BD_ACTOR="$1" bd comment "$2" "$3" >/dev/null 2>&1; BD_ACTOR="$1" bd close "$2" 2>&1 | head -1 ;;
  back) deliver "$1"; BD_ACTOR="$1" bd comment "$2" "given back: $3" >/dev/null 2>&1; BD_ACTOR="$1" bd update "$2" --status open --assignee "" 2>&1 | head -1 ;;
  toverify) who=$1; deliver "$who"; echo "$HINT"; V="$OUT_DIR/verify.log"; touch "$V"   # a verifier claims the oldest closed slice nobody has verified yet
    pick=$(bd list --status closed --json 2>/dev/null | V="$V" SINCE="$SINCE_ISO" python3 -c "
import json,sys,os
seen={l.split()[0] for l in open(os.environ['V']) if l.strip()}
for i in sorted(json.load(sys.stdin),key=lambda i:i.get('closed_at') or ''):
    if i['id'] not in seen and not i['title'].startswith(('ZZ','TEST','Board is live')) and (i.get('closed_at') or '')>=os.environ['SINCE']:
        print(i['id']); break")
    [ -z "$pick" ] && { echo "NONE: nothing closed is waiting for a verifier"; exit 0; }
    ( flock 9; grep -q "^$pick " "$V" && exit 3; echo "$pick $who claimed $(date '+%H:%M')" >> "$V" ) 9>"$V.lock" || { echo "NONE: taken, run again"; exit 0; }
    bd show "$pick" 2>/dev/null | sed -n '1,70p' ;;
  toverify_count) V="$OUT_DIR/verify.log"; touch "$V"; bd list --status closed --json 2>/dev/null | V="$V" SINCE="$SINCE_ISO" python3 -c "
import json,sys,os
seen={l.split()[0] for l in open(os.environ['V']) if l.strip()}
print(sum(1 for i in json.load(sys.stdin) if i['id'] not in seen and not i['title'].startswith(('ZZ','TEST','Board is live')) and (i.get('closed_at') or '')>=os.environ['SINCE']))" ;;
  verified) deliver "$1"; echo "$2 $1 verdict $(date '+%H:%M') $3" >> "$OUT_DIR/verify.log"; BD_ACTOR="$1" bd comment "$2" "verifier $1: $3" >/dev/null 2>&1; echo "recorded" ;;
  *) sed -n '2,16p' "$SELF" ;;
esac
