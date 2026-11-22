# swarm: a reusable agent-team kit for Claude Code

A chief, a manager, workers and verifiers, launched as long-lived Agent-tool agents under one main session, sharing a slice queue
(on the `bd` tracker), a message log, and a self-refreshing HTML board. Generalised from a real project swarm; nothing in it is
project-specific. Everything the scripts need is in one `swarm.json` per swarm, so several swarms can coexist.

## Quick start

```bash
S=~/.claude/tools/swarm/swarm
$S init demo --repo ~/Projects/myrepo            # creates ~/.claude/swarm/demo/ (config, logs, roles/)
cd ~/Projects/myrepo && bd init --prefix demo    # only if init said the repo has no bd database
$EDITOR ~/.claude/swarm/demo/roles/COMMON.md     # fill: What we are building / Rules of this project / Places
$S q demo add "Slice title" "what it does and its done-when
files: a.py, b.py" 1                             # stock 8+ slices
# launch the chief with the Agent tool (see roles/CHIEF.md), then record it:
$S q demo join chief <agent id> chief main
$S board demo --loop 10 &                        # board at ~/.claude/swarm/demo/board.html (xdg-open it)
$S status demo
$S stop demo                                     # stops the board and backup loops of this swarm only
```

## Commands

- `swarm init <name> --repo <path> [--branch B] [--run DIR] [--board HTML] [--subagents DIR]`: creates the run folder
  (default `~/.claude/swarm/<name>/`): `swarm.json`, empty `ledger.md messages.log roster.txt verify.log`, and `roles/` copied from
  `templates/roles/` with paths, name and command lines filled in. Branch defaults to the repo's current branch; the subagents
  directory (where agents' transcript files are, used to tell working from idle) defaults to the most recently active session's.
  It tells you plainly if `bd` is missing or the repo has no bd database; it never creates the database.
- `swarm q <name> <cmd>`: the queue and messages (run bare to list): `add`, `next`, `done`, `back`, `list`, `tell`, `inbox`, `who`,
  `join`, `toverify`, `verified`, `committed`. Runs from inside the repo, which bd needs.
- `swarm board <name> [--loop N] [--until YYYYmmddHHMM]`: draws the board once, or every N seconds.
- `swarm wake <name> <who> [beat=8] [idle=3]`: a no-model watch. Run it as a background command; it exits (and so wakes the agent
  that started it) when an agent is idle with work waiting, or after `beat` minutes.
- `swarm backup <name> <dest> [END]`: rsync loop of the repo folder (minus .git, caches) to `dest` every two minutes, until END
  (default 24 h). The dest's parent folder must exist.
- `swarm status <name>`: roster, queue, who is idle, last messages, verified commits, loop pids.
- `swarm stop <name>`: stops this swarm's board and backup loops by the pid files they wrote; never pattern-kills.

Scripts can also be run directly with `SWARM_CONFIG=<path to swarm.json>`.

## How the board reads

Boxes are agents from the roster in groups (Direction, Management, Workers, Verifiers), plus the queue and the product.
Green: working (transcript touched in the last 2 min). Amber: quiet. Grey dashed: idle, a message wakes it. A yellow link means
those two exchanged messages in the last half hour; a dot travels once along a link when a message is sent; a "woken" flash shows
an agent that has just resumed; a number badge counts recent messages. Click a box for its recent actions and messages. Rings show
5-hour and weekly usage (from `~/.claude/usage_meter.json` if present). Small charts: agents working, slices built, commits,
messages, usage. Lists: queue, built slices, verdicts, commits, ledger, and an acceptance scoreboard if you write
`<run>/acceptance/<x>/scoreboard.md`. "Commits awaiting approval" is `origin/<branch>..HEAD` (all commits since start if the
branch has no upstream). The page refreshes itself every 10 s.

## The commit chain

worker builds (uncommitted) -> `q done` -> verifier `q toverify` and `q verified holds` -> worker commits its files by name and
`q committed` -> chief checks the set and presents it to main with SendMessage -> main approves and pushes. Only main pushes.

## Known limits

- Agents that ended inside a Workflow tool run cannot be woken. This kit uses long-lived Agent-tool agents and SendMessage.
- Each wake re-reads the agent's whole history: keep messages few and complete, and replace a worker after about five slices.
- A running board and a wake watch cost no model usage; the agents do.
- The queue needs `bd` and a bd database in the repo. Closed-slice filtering uses the swarm's start time as a local-time string
  against bd's `closed_at`; if bd stamps UTC and the machine is not on UTC, that cut-off is off by the offset.
- Idle detection reads transcript file times in the subagents directory; a wrong or missing directory shows everyone as idle.
- The board's "verdicts" count only counts verifiers named `v-<n>`; workers `w-<n>` are what the wake watch and roles assume,
  though any name works for the queue.
