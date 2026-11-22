# Project development tools: running a project with a Claude Code swarm

A way to run a software project with several long-lived Claude Code agents under one main session: a **chief** who holds the
goal and keeps the queue right, a **manager** who runs the pool, generic **workers** who build one slice at a time, and
**verifiers** who check each slice on real input before it is committed. Nothing here calls a model; these are the scripts,
role files and board the agents and you share.

## How it works

```
main session ──► queue ──► chief ──► manager ──► workers ──► verifiers ──► product
     ▲                                                                        │
     └──────────── verified commits to approve ◄──────────────────────────────┤
                   what is left goes back into the queue ◄────────────────────┘
```

- **Queue of slices** on the `bd` (beads) tracker. A slice is one small piece of work with a "done when" and a `files:` line, so
  two workers never hold the same file.
- **Mesh messaging.** Any agent can message any other (`q.sh tell`), and a message plus `SendMessage` wakes an idle agent.
- **Verified before committed, approved before pushed.** A worker commits its own files only after a verifier says "holds". Only
  the chief presents finished commits to the main session, and only the main session pushes.
- **Nobody idle.** `wake.sh` is armed by the chief and manager before they end a turn; it wakes them when an agent sits idle with
  work waiting, or on a heartbeat.
- **A board** you can leave open: who is working, what each holds, messages as they are sent, verdicts, commits to approve.

## What is here

| Path | What it is |
|---|---|
| `tools/swarm/swarm` | One command: `init`, `q`, `board`, `wake`, `backup`, `status`, `stop` |
| `tools/swarm/q.sh` | The queue and the messages: add, next, done, back, tell, inbox, who, join, toverify, verified, committed |
| `tools/swarm/wake.sh` | Anti-idle watch for the chief and manager |
| `tools/swarm/backup.sh` | Plain copy of the working tree every few minutes, so uncommitted work survives |
| `tools/swarm/board.py` | Self-refreshing static HTML board |
| `tools/swarm/templates/roles/` | `COMMON.md`, `CHIEF.md`, `MANAGER.md`, `WORKER.md`, `VERIFIER.md`: what each agent reads first |
| `skills/swarm/SKILL.md` | A Claude Code skill so "set up a swarm" does the right thing |
| `board/` | The live board (server-sent events, no reload): `board_live.py` and `board_page.html` |

## Install

Needs Claude Code, `git`, `python3`, `flock`, and the `bd` tracker (`npm i -g @beads/bd`).

```bash
git clone https://github.com/olihb005/Projet-Development-tools
mkdir -p ~/.claude/tools ~/.claude/skills
cp -r Projet-Development-tools/tools/swarm ~/.claude/tools/swarm
cp -r Projet-Development-tools/skills/swarm ~/.claude/skills/swarm
```

Then, in a Claude Code session in your project: "set up a swarm for <goal>". The skill runs `swarm init`, writes the role files
for your project, and launches the chief. See `tools/swarm/README.md` for each command.

## The live board

```bash
SWARM_RUN=<run folder> SWARM_REPO=<your checkout> SWARM_TITLE="My swarm" \
SWARM_SUBAGENTS=~/.claude/projects/<project>/<session id>/subagents \
python3 board/board_live.py --port 8899        # then open http://127.0.0.1:8899/
```

It reads `queue.json`, `messages.log`, `roster.txt`, `verify.log` and `deliverables.jsonl` from the run folder.

## Rules that made it work

1. The system must produce its results without an agent in the loop; an agent-run script is not a result.
2. Judge by the real output against a known answer, on more than one input, one of which the builder never ran.
3. Slices are kinds of fault, not single cases; done means the scoreboard moves on every case affected and none goes back.
4. Cap heavy runs to what the machine holds (two at a time on a 12-core laptop), announced on the channel.
5. Keep your own working folder (`.claude/`) and any client data out of the repository.

## Known gaps

- The live board in `board/` was written against a later version of `q.sh` than the one in `tools/swarm/`. Three things that
  later version does are not yet in the kit: every tracker call behind a lock with a cached `queue.json` snapshot; the `status`,
  `doing` and `post` commands (node labels and headline cards); and work events written to the message log. Until they are
  ported the live board shows agents, messages and commits, but its queue panel and headlines stay empty.
- The board's work-pulse animation and hover tracing have not been tested against a running swarm.
