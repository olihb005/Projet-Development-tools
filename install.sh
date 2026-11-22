#!/bin/bash
# Copies the kit into your Claude Code folder. Run again to update; the previous copy is kept beside it.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); DEST="${CLAUDE_HOME:-$HOME/.claude}"
for need in git python3 flock rsync; do command -v "$need" >/dev/null || { echo "missing: $need"; exit 1; }; done
command -v bd >/dev/null || echo "note: bd (the beads tracker) is not installed; the queue needs it: npm i -g @beads/bd"
mkdir -p "$DEST/tools" "$DEST/skills/swarm"
if [ -d "$DEST/tools/swarm" ]; then old="$DEST/tools/swarm.previous"; rm -rf "$old"; mv "$DEST/tools/swarm" "$old"; echo "kept your previous copy at $old"; fi
cp -r "$HERE/swarm" "$DEST/tools/swarm"; cp "$HERE/skill/SKILL.md" "$DEST/skills/swarm/SKILL.md"
chmod +x "$DEST/tools/swarm/swarm" "$DEST/tools/swarm/"*.sh
echo "installed to $DEST/tools/swarm"; echo "try: $DEST/tools/swarm/swarm --help"
