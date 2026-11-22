#!/bin/bash
# Shared by q.sh, wake.sh, backup.sh: loads swarm.json (path in $SWARM_CONFIG) into SW_* variables.
: "${SWARM_CONFIG:?SWARM_CONFIG must point at the swarm.json of the swarm (use: swarm q <name> ...)}"
[ -f "$SWARM_CONFIG" ] || { echo "no such config: $SWARM_CONFIG" >&2; exit 1; }
_sw_vars=$(python3 -c 'import json,sys,shlex
c=json.load(open(sys.argv[1]))
for k,v in c.items(): print("SW_%s=%s" % (k.upper(), shlex.quote(str(v))))' "$SWARM_CONFIG") || exit 1
eval "$_sw_vars"
SW_TOOLS=${SW_TOOLS:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
export SWARM_CONFIG
