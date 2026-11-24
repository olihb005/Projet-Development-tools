#!/bin/bash
# End-to-end check of the queue with no agents: one slice goes from queued to built to verified to committed.
# Needs git, python3, flock and bd. Works in a throwaway folder and leaves nothing behind.
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd); SW="$HERE/swarm/swarm"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export SWARM_ROOT="$T/swarms"; fail=0
ok() { if eval "$2" >/dev/null 2>&1; then echo "ok    $1"; else echo "FAIL  $1"; fail=1; fi; }
mkdir -p "$T/repo" && cd "$T/repo" && git init -q && git commit -q --allow-empty -m init
bd init --prefix sm </dev/null >/dev/null 2>&1 || { echo "bd init failed: is bd installed?"; exit 2; }
"$SW" init demo --repo "$T/repo" --subagents "$T/none" >/dev/null || exit 2
q() { "$SW" q demo "$@"; }
ok "a slice is queued"            'q add "First slice" "Do the thing. files: a.py" 1 | grep -q queued'
ok "the list shows it"            'q list | grep -q "First slice"'
ID=$(q next w-1 | grep -oE "sm-[a-z0-9]+" | head -1)
ok "a worker takes it"            '[ -n "$ID" ]'
ok "nothing else is ready"        'q next w-2 | grep -q NONE'
ok "the worker hands it in"       'q done w-1 "$ID" "built"'
ok "a verifier claims it"         'q toverify v-1 | grep -q "$ID"'
ok "the verdict is recorded"      'q verified v-1 "$ID" "holds: ran it" && grep -q "holds" "$SWARM_ROOT/demo/verify.log"'
ok "the commit is recorded"       'q committed w-1 "$ID" abc1234 && grep -q abc1234 "$SWARM_ROOT/demo/commits_verified.log"'
ok "a message reaches its inbox"  'q tell w-1 v-1 "thanks" && q inbox v-1 | grep -q thanks'
ok "a headline is posted"         'q post w-1 "1 of 1 slices verified" "smoke" && grep -q "1 of 1" "$SWARM_ROOT/demo/deliverables.jsonl"'
ok "the snapshot is written"      'python3 -c "import json;json.load(open(\"$SWARM_ROOT/demo/queue.json\"))"'
ok "toverify respects the swarm start time" 'q add "Second" "x. files: b.py" 1 >/dev/null; ID2=$(q next w-1 | grep -oE "sm-[a-z0-9]+" | head -1); q done w-1 "$ID2" built >/dev/null; q toverify v-1 | grep -q "$ID2"'
ok "the next-gen board draws"       '"$SW" board demo --next --no-git && grep -q "Worker" "$SWARM_ROOT/demo/board.html_next.html" || ls "$SWARM_ROOT/demo"/*_next.html'
ok "the fleet page draws"           '"$SW" fleet "$SWARM_ROOT" --no-git --out "$T/fleet.html" && [ -s "$T/fleet.html" ]'
ok "show names and quotes are unique" 'python3 -c "import sys;sys.path.insert(0,\"$HERE/swarm\");import swarm_state as s;s.reset_fleet();p=s.load_pack(\"shows\");a=[{\"name\":\"w-%d\"%i,\"role\":\"worker\"} for i in range(8)];s.assign_characters(a,p,\"x\");assert len({x[\"char\"][\"name\"] for x in a})==8 and len({x[\"char\"][\"aside\"] for x in a})==8"'
R="$SWARM_ROOT/demo"
ok "a researcher joins the roster"  'q join r-1 abc123 researcher manager | grep -q "joined: r-1" && grep -q "^r-1|abc123|researcher|" "$R/roster.txt"'
ok "a second chief joins"           'q join chief-2 def456 chief main | grep -q joined'
printf '%s\n' '{"id":"g1","title":"First goal","priority":0}' '{"id":"g2","title":"Second goal","status":"done"}' > "$R/goals.jsonl"
ST="import sys,json;sys.path.insert(0,\"$HERE/swarm\");import swarm_state as s;d=s.read_swarm(\"$R/swarm.json\",git=False,pack=s.load_pack(\"shows\"));Q=d[\"stageq\"]"
ok "the state reader sees the researcher and both chiefs" 'python3 -c "$ST;r=[a[\"role\"] for a in d[\"agents\"]];assert \"researcher\" in r and \"chief-2\" in [a[\"name\"] for a in d[\"agents\"] if a[\"role\"]==\"chief\"]"'
ok "goals waiting to be broken down: open goals only" 'python3 -c "$ST;assert Q[\"goals\"][\"show\"] and Q[\"goals\"][\"n\"]==1 and Q[\"goals\"][\"label\"]==\"goals waiting to be broken down\""'
ok "the five stage queues have their names" 'python3 -c "$ST;assert [Q[k][\"label\"] for k in (\"goals\",\"build\",\"review\",\"clear\",\"merge\")]==[\"goals waiting to be broken down\",\"tasks waiting to be built\",\"built work waiting for review\",\"reviewed work waiting to be cleared\",\"cleared work waiting to merge\"]"'
ok "built work waits for review, cleared work waits to merge" 'python3 -c "$ST;assert Q[\"review\"][\"n\"]==1 and Q[\"merge\"][\"n\"]==1 and Q[\"clear\"][\"n\"]==0 and d[\"done\"][\"n\"]==1"'
ok "no goals file: the goals queue is hidden" 'rm "$R/goals.jsonl"; python3 -c "$ST;assert not Q[\"goals\"][\"show\"]"'
ok "the board draws researchers and the stage queues" '"$SW" board demo --next --no-git --characters shows >/dev/null; f=$(ls "$R"/*_next.html "$R"/board_next.html 2>/dev/null | head -1); grep -q "researcher" "$f" && grep -q "cleared work waiting to merge" "$f"'
[ $fail = 0 ] && echo "all checks passed" || echo "some checks failed"; exit $fail
