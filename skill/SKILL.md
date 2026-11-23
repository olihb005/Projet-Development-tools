---
name: swarm
description: Set up and run a multi-agent swarm (chief, manager, workers, verifiers) with a shared slice queue, message log and live board, using the kit in ~/.claude/tools/swarm. Use when the user says "swarm", "agent team", "chief and manager", "run workers with verifiers", "board for the agents", or wants several long-lived agents building in parallel with verified commits.
---

# swarm

The kit is `~/.claude/tools/swarm/` (README.md there). `S=~/.claude/tools/swarm/swarm`. You are the main session:
you launch the chief, audit, approve and push. You do not build.

## Set up

1. `$S init <name> --repo <repo path> [--branch B] [--board <html path>]`. Read what it prints. If it says bd is missing, tell the
   user plainly. If the repo has no bd database, run `cd <repo> && bd init --prefix <prefix>` only after the user agrees, and
   check `.beads` is gitignored if the repo is shared.
2. Open `~/.claude/swarm/<name>/roles/COMMON.md` and fill exactly three sections from the user's direction, in their words with
   dates: **What we are building**, **Rules of this project**, **Places**. Leave the general part alone. Do not launch before
   these are filled; ask the user for what is missing.
3. Stock the queue: eight or more small slices (15 to 20 min), dependency order, each ending `files: a.py, b.py` and a done-when:
   `$S q <name> add "<title>" "<what; done-when\nfiles: ...>" <priority 0-4>`. Check with `$S q <name> list`.
4. Launch the chief with the Agent tool (general-purpose, model sonnet or opus for hard work, run in background): "You are the
   chief of the <name> swarm. Read ~/.claude/swarm/<name>/roles/COMMON.md, CHIEF.md and MANAGER.md and follow them. The main
   session's name for SendMessage is main." Record it: `$S q <name> join chief <agent id> chief main`. If the subagents dir was
   guessed wrong (board shows everyone idle), find the right one and edit `subagents` in swarm.json.
5. Start the board: run `$S board <name> --loop 10` as a background Bash command, then open the file named in swarm.json
   (`xdg-open <board>`). Optionally `$S backup <name> <dest>` in the background.
   Prefer the next-generation board when it is installed (`$S board <name> --next --loop 10`, or `--serve` for a live local page): five
   skins, five layouts, agents with names and a plain line on what each is doing, plain-English logs, and the queue's load with its
   runway (ready slices divided by workers). With several swarms, even in different repos, run `$S fleet` (every swarm under the swarm
   root) or `$S fleet a/swarm.json b/swarm.json --serve` for one page showing them all, with the ones that need attention first.
   `$S stop` does not stop a `--next` loop or server: end it with Ctrl-C or by its process id, and bind nothing but 127.0.0.1.

## Audit (every few minutes while it runs)

`$S status <name>` shows roster, queue, who is IDLE, last messages and verified commits. Check: anyone idle while slices are
ready (the manager should wake them; if not, `$S q <name> tell main <who> "<text>"` and SendMessage its id); queue depth under
three ready (tell the chief); verdicts in `verify.log` that are "partly" or "does not hold" with no fix queued; commits awaiting
approval (`git -C <repo> log origin/<branch>..HEAD`); anything not matching the user's rules; a queue whose runway is under one round, or a swarm flagged stalled or empty on the fleet page. Fix deviations yourself or by
message, do not wait to be asked. Keep your own messages few: each wake re-reads that agent's history.

## Approve and push

Only the chief presents finished work, as one SendMessage to main. Read the commits (`git log`, `git show --stat`), run the
project's checks yourself, and check no secrets or `.claude/` are in them. Approve by replying to the chief. Push only the user's
branch, never main or master, never force, and only where the global rules allow it for that repo; in a teammate's repo ask the
user first. Send back by message with what failed.

## Shut down

1. Tell the chief to wrap up: finish or give back held slices, present what is verified. 2. `$S stop <name>` (board and backup loops only). 3. Leave a relaunch note in
`~/.claude/swarm/<name>/ledger.md` (date from `date`): what is built and committed, what is queued (`$S q <name> list`), open
faults, the roster with agent ids (they cannot be reused after the session ends), and the command to relaunch: `swarm init` is
not needed again; launch a new chief with the same prompt and `join` it. Report to the user what was done, what is left, and what
is awaiting their approval.
