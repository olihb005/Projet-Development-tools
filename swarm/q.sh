#!/bin/bash
# The swarm's slice queue and message log, on the bd tracker in the project repository. No model in it.
# Workers PULL their next slice here the moment they finish one, so nobody waits for the manager to hand work out.
#   q.sh add "<title>" "<description>" [priority 0-4, 0 first] [from]   description must hold a line "files: a.py, b.py"; from = who asked (main, chief, v-1 …)
#   q.sh next <worker-name>     claim the first ready slice whose files no in-progress slice holds; prints it, or NONE
#   q.sh done <worker-name> <id> "<commit and one-line result>"
#   q.sh back <worker-name> <id> "<why>"      give a slice back unfinished (it returns to the queue with your note)
#   q.sh list                   ready and in-progress slices
#   q.sh tell <from> <to> "<text>"   message another agent (chief, manager, w-N, v-N, main, all)
#   q.sh doing <name> "<3 to 5 plain words>"   the label under your node on the board (what you are doing, in words anyone understands)
#   q.sh status <name> "<text>" [to]   one line on what you are doing right now (to the manager unless you name someone)
#   q.sh post <name> "<title>" "<text>" [file]   put a notable result on the board (Recent deliverables)
#   q.sh who                    everyone in the swarm: role, agent id, idle time, slice held
#   q.sh join <name> <id> <role> <by>   the launcher records an agent it started
#   q.sh committed <name> <slice> <commit>   record a commit made after a verifier said the slice holds
#   q.sh inbox <name>           read your unread messages (also shown on every next, done, back, toverify, verified)
#   q.sh toverify <verifier>    claim the oldest closed slice not yet verified; prints it, or NONE
#   q.sh verified <verifier> <id> "<holds|partly|does not hold>: what was seen"
. "$(dirname "$0")/lib.sh"                              # loads the swarm's config into SW_* variables
cd "$SW_REPO" || { echo "repo $SW_REPO not found" >&2; exit 1; }
OUT_DIR=$SW_RUN
cmd=$1; shift
# One lock per tracker database, so two swarms on the same repository queue up instead of colliding.
if [ -d "$SW_REPO/.beads" ]; then LOCK="$SW_REPO/.beads/.swarm.lock"; else LOCK="$OUT_DIR/.bd.lock"; fi
SNAP="$OUT_DIR/queue.json"
bd() { flock -w 90 "$LOCK" "$(command -v bd)" "$@"; }   # the tracker takes one process at a time
snapshot() {                                            # one cheap file the board, the watches and "list" read, so they never touch the tracker
  ( flock -w 90 9
    python3 - "$SNAP" <<'PYSNAP'
import json,subprocess,sys,time,os
def q(st):
    try: return json.loads(subprocess.run(["bd","list","--status",st,"--json"],capture_output=True,text=True,timeout=60).stdout or "[]")
    except Exception: return None
out={"t":time.time()}
for st in ("in_progress","open","closed"):
    r=q(st)
    if r is None: sys.exit(0)                           # keep the last good snapshot
    out[st]=[{k:i.get(k) for k in ("id","title","priority","assignee","created_at","closed_at","description")} for i in r]
tmp=sys.argv[1]+".tmp"; json.dump(out,open(tmp,"w")); os.replace(tmp,sys.argv[1])
PYSNAP
  ) 9>"$LOCK"
}
snapget() { python3 - "$SNAP" "$@" <<'PYGET'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: d={"in_progress":[],"open":[],"closed":[]}
what=sys.argv[2]
allv=d["in_progress"]+d["open"]+d["closed"]
if what=="title": print(next((i["title"][:70] for i in allv if i["id"]==sys.argv[3]),""))
elif what=="owner": print(next((i.get("assignee") or "manager" for i in allv if i["id"]==sys.argv[3]),"manager"))
elif what=="list":
    for st in ("in_progress","open"):
        for i in sorted(d[st],key=lambda i:(i.get("priority") if i.get("priority") is not None else 9,i.get("created_at") or "",i["id"])):
            print(st.ljust(11), i["id"], "P%s"%i.get("priority"), (i.get("assignee") or "-").ljust(10), (i["title"] or "")[:90])
elif what=="closed": print(json.dumps(d["closed"]))
elif what=="held":
    for i in d["in_progress"]: print((i.get("assignee") or "?")+"|"+i["id"]+" "+(i["title"] or "")[:70])
PYGET
}
MSG="$OUT_DIR/messages.log"; touch "$MSG"
deliver() {  # print the messages addressed to $1 (or to all) that it has not seen yet, and mark them seen
  local who=$1 pos="$OUT_DIR/.inbox_$1.pos" n seen; [ -z "$who" ] && return
  seen=$(cat "$pos" 2>/dev/null || echo 0); n=$(wc -l < "$MSG")
  if [ "$n" -gt "$seen" ]; then
    grp="-"; case "$who" in w-*) grp="workers";; v-*) grp="verifiers";; esac
    m=$(tail -n +$((seen+1)) "$MSG" | awk -F'|' -v w="$who" -v g="$grp" '($4==w || $4=="all" || $4==g) && $3!=w && $5 !~ /^\[auto\]/ {print "  " $2 " from " $3 ": " $5}')
    [ -n "$m" ] && { echo "=== MESSAGES FOR YOU, $who (direction: act on them now, then answer with q.sh tell) ==="; echo "$m"; echo "==="; }
    echo "$n" > "$pos"
  fi
}
say() { echo "$(date +%s)|$(date +%H:%M)|$1|$2|[auto] $(echo "$3" | tr "\n|" "  " | cut -c1-200)" >> "$MSG"; }   # work events as messages, for the record and the board
owner_of() { snapget owner "$1"; }
title_of() { snapget title "$1"; }
HINT="(mesh: anyone can message anyone. q.sh who lists everyone and what each is on; q.sh tell <your name> <any name or all> \"<text>\" sends; q.sh inbox <your name> reads yours. Check your inbox every few minutes while you work.)"
case "$cmd" in
  add)  # two agents writing at once can make bd answer nothing: try up to three times before giving up
        for try in 1 2 3; do
          d="$2"; [ -n "${4:-}" ] && d="$2
from: $4"                                                # who asked for it: main, chief, a verifier, a worker
          out=$(bd create "$1" -d "$d" -p "${3:-2}" --json 2>/dev/null)
          if printf '%s' "$out" | python3 -c "import json,sys;d=json.load(sys.stdin);print('queued',d['id'],d['title'])" 2>/dev/null; then snapshot; say "${4:-queue}" all "new slice: $1"; exit 0; fi
          sleep $((try * 2))
        done
        echo "NOT QUEUED after three tries: tell the PM the slice text so it is not lost"; exit 1 ;;
  tell) echo "$(date +%s)|$(date +%H:%M)|$1|$2|$(echo "$3" | tr "\n|" "  ")" >> "$MSG"; echo "sent to $2" ;;
  inbox) deliver "$1"; echo "(inbox checked)" ;;
  status) say "$1" "${3:-manager}" "$2"; echo ok ;;
  doing) # q.sh doing <your name> "<three to five plain words on what you are doing now>": the label under your node on the board
         python3 - "$OUT_DIR/taglines.json" "$1" "$2" <<'PYTAG'
import json,sys,time,os
p=sys.argv[1]
try: d=json.load(open(p))
except Exception: d={}
d[sys.argv[2]]={"text":" ".join(sys.argv[3].split()[:6]),"t":time.time()}; json.dump(d,open(p+".tmp","w")); os.replace(p+".tmp",p)
PYTAG
         echo ok ;;   # q.sh status <you> "<what you are doing right now>" [to]: a one-line progress note
  join) say "${4:-main}" "$1" "launched as $3"; # the launcher records each agent it starts: q.sh join <name> <agent id> <role> <launched by>
        R="$OUT_DIR/roster.txt"; touch "$R"; grep -v "^$1|" "$R" > "$R.tmp"; echo "$1|$2|$3|$4|$(date +%H:%M)" >> "$R.tmp"; mv "$R.tmp" "$R"; echo "joined: $1 ($3)" ;;
  who)  # everyone in the swarm: name, role, agent id (for SendMessage), how long since it last did anything, and what it holds
        echo "Mesh: anyone can message anyone. q.sh tell <you> <name> \"<text>\" records it; if the receiver shows IDLE, also SendMessage its id with the same text to wake it."
        SUBD=$SW_SUBAGENTS; now=$(date +%s)
        held=$(snapget held)
        echo "  main       the main session: SendMessage to \"main\" (only the chief presents finished work to it)"
        while IFS='|' read -r n id role by at; do [ -z "$n" ] && continue
          t=$(stat -L -c %Y "$SUBD/agent-$id.jsonl" 2>/dev/null || echo 0); m=$(( (now - t) / 60 )); st="working"; [ "$m" -ge 3 ] && st="IDLE ${m} min"
          h=$(echo "$held" | grep "^$n|" | head -1 | cut -d'|' -f2); printf "  %-9s %-9s id %s  %-12s %s\n" "$n" "$role" "$id" "$st" "${h:+holds $h}"
        done < "$OUT_DIR/roster.txt" ;;
  committed) say "$1" chief "committed $2 as $3 (verified); ready for you to present"; echo "$(date +%H:%M)|$1|$2|$3" >> "$OUT_DIR/commits_verified.log"; echo "recorded: $2 committed as $3 by $1 (verified work only; the chief presents it to main before any push)" ;;
  list) echo "$HINT"; [ -f "$SNAP" ] || snapshot; snapget list ;;
  next) who=$1; deliver "$who"; echo "$HINT"; [ -z "$who" ] && { echo "usage: q.sh next <worker-name>"; exit 2; }
    snapshot
    pick=$(python3 - "$SNAP" <<'EOF'
import json,re,sys
try: d=json.load(open(sys.argv[1]))
except Exception: d={"in_progress":[],"open":[]}
def files(i):
    m=re.search(r"files:\s*(.*)", i.get("description") or "", re.I)
    return {f.strip().split("/")[-1] for f in (m.group(1) if m else "").split(",") if f.strip() and f.strip().lower()!="none"}
held=set()
for i in d["in_progress"]: held |= files(i)
for i in sorted(d["open"],key=lambda i:(i.get("priority") if i.get("priority") is not None else 9,i.get("created_at") or "",i["id"])):
    if i["title"].startswith(("Board is live","TEST","ZZ")): continue
    if files(i) & held: continue
    print(i["id"]); break
EOF
)
    [ -z "$pick" ] && { echo "NONE: no ready slice is free of files held by live slices. Tell the PM you are free and stop."; exit 0; }
    BD_ACTOR="$who" bd update "$pick" --claim >/dev/null 2>&1 || { echo "NONE: could not claim $pick (taken). Run q.sh next again."; exit 0; }
    snapshot; say "$who" manager "took $pick: $(title_of "$pick")"
    bd show "$pick" 2>/dev/null | sed -n '1,60p' ;;
  done) deliver "$1"; BD_ACTOR="$1" bd comment "$2" "$3" >/dev/null 2>&1; BD_ACTOR="$1" bd close "$2" 2>&1 | head -1
        snapshot; say "$1" verifiers "built $2 ($(title_of "$2")): $3"; say "$1" manager "built $2, handing to the verifiers" ;;
  back) say "$1" manager "giving $2 back: $3"; deliver "$1"; BD_ACTOR="$1" bd comment "$2" "given back: $3" >/dev/null 2>&1; BD_ACTOR="$1" bd update "$2" --status open --assignee "" 2>&1 | head -1; snapshot ;;
  snapshot) snapshot; echo "snapshot written" ;;
  post) # q.sh post <your name> "<title>" "<text: the result in a few lines, with numbers>" [path to a vector file or other output]
        python3 - "$OUT_DIR/deliverables.jsonl" "$1" "$2" "$3" "${4:-}" <<'PYPOST'
import json,sys,time
json.dump({"t":time.time(),"hm":time.strftime("%H:%M"),"by":sys.argv[2],"title":sys.argv[3][:140],"text":sys.argv[4][:1500],"path":sys.argv[5]},open(sys.argv[1],"a")); open(sys.argv[1],"a").write("\n")
PYPOST
        say "$1" all "posted a deliverable: $2"; echo "posted to the board's Recent deliverables" ;;
  toverify) who=$1; deliver "$who"; echo "$HINT"; V="$OUT_DIR/verify.log"; touch "$V"   # a verifier claims the oldest closed slice nobody has verified yet
    pick=$(snapget closed | V="$V" python3 -c "
import json,sys,os
seen={l.split()[0] for l in open(os.environ['V']) if l.strip()}
for i in sorted(json.load(sys.stdin),key=lambda i:i.get('closed_at') or ''):
    if i['id'] not in seen and not i['title'].startswith(('ZZ','TEST','Board is live')) and (i.get('closed_at') or '')>='2026-11-22T18:00':
        print(i['id']); break")
    [ -z "$pick" ] && { echo "NONE: nothing closed is waiting for a verifier"; exit 0; }
    ( flock 9; grep -q "^$pick " "$V" && exit 3; echo "$pick $who claimed $(date '+%H:%M')" >> "$V" ) 9>"$V.lock" || { echo "NONE: taken, run again"; exit 0; }
    say "$who" "$(owner_of "$pick")" "checking your slice $pick now"
    bd show "$pick" 2>/dev/null | sed -n '1,70p' ;;
  toverify_count) V="$OUT_DIR/verify.log"; touch "$V"; snapget closed | V="$V" python3 -c "
import json,sys,os
seen={l.split()[0] for l in open(os.environ['V']) if l.strip()}
print(sum(1 for i in json.load(sys.stdin) if i['id'] not in seen and not i['title'].startswith(('ZZ','TEST','Board is live')) and (i.get('closed_at') or '')>='2026-11-22T20:45'))" ;;
  verified) say "$1" "$(owner_of "$2")" "verdict on $2: $3"; say "$1" chief "verdict on $2: $(echo "$3" | cut -c1-60)"; deliver "$1"; echo "$2 $1 verdict $(date '+%H:%M') $3" >> "$OUT_DIR/verify.log"; BD_ACTOR="$1" bd comment "$2" "verifier $1: $3" >/dev/null 2>&1; echo "recorded" ;;
  *) sed -n '2,19p' "$0" ;;
esac
