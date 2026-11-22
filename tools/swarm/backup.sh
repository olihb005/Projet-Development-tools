#!/bin/bash
# Plain backup, no git and no model: every two minutes rsyncs the swarm's repo folder (without .git, caches, venvs, node_modules)
# to a destination folder, so unverified, uncommitted work survives if the working folder is re-made. Commits are made only after
# a verifier's "holds"; pushes only by the main session after the chief presents them.
# usage (normally): swarm backup <name> <dest> [END=YYYYmmddHHMM]     direct: SWARM_CONFIG=... backup.sh <dest> [END]
. "$(dirname "$(readlink -f "$0")")/lib.sh" || exit 1
DST=${1:?usage: backup.sh <dest folder> [END=YYYYmmddHHMM]}
END=${2:-$(date -d '+24 hours' +%Y%m%d%H%M)}; trap 'exit 0' TERM INT
command -v rsync >/dev/null || { echo "rsync not installed" >&2; exit 1; }
while [ "$(date +%Y%m%d%H%M)" -lt "$END" ]; do
  # the destination's parent must already exist (an unmounted drive is skipped, not recreated)
  if [ -d "$SW_REPO" ] && [ -d "$(dirname "$DST")" ]; then
    mkdir -p "$DST" && rsync -a --delete --exclude '.git' --exclude '__pycache__' --exclude '.venv' --exclude 'node_modules' --exclude '*.pyc' "$SW_REPO/" "$DST/" 2>/dev/null && date '+%Y-%m-%d %H:%M:%S' > "$DST/LAST_BACKUP.txt"
  fi
  sleep 120 & wait $!   # background sleep so a TERM is handled at once
done
