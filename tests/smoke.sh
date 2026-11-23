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
[ $fail = 0 ] && echo "all checks passed" || echo "some checks failed"; exit $fail
