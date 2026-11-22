# swarm

Run a software project with a team of Claude Code agents that check each other's work.

One main session directs a **chief**, a **manager**, a pool of **workers** and a couple of **verifiers**. Workers pull small
slices from a shared queue, verifiers run each one on real input, and only work that holds is committed. You watch it on a
live board and approve what gets pushed.

The kit is shell and Python with no model calls of its own: a queue, a message log, an idle watch, a backup loop, role files
the agents read, and the board.

```
                 ┌──────────────── you approve, main pushes ◄───────────────┐
                 ▼                                                          │
main session ─► queue ─► chief ─► manager ─► workers ─► verifiers ─► verified commits
                 ▲                                                          │
                 └─────────── faults and what is left go back ◄─────────────┘
```

## Why it is built this way

These came from running it on a real product, mostly by getting them wrong first.

- **Verified before committed, approved before pushed.** A worker commits its own files only after a verifier says "holds".
  The chief is the only agent that presents finished work, and only the main session pushes.
- **Workers pull; nobody hands work out.** A slice names the files it touches, and the queue never gives two workers the same
  file. A worker that finishes takes the next slice at once.
- **Any agent can message any other.** The manager is not a switchboard. A message plus a wake brings an idle agent back.
- **Nobody sits idle with work waiting.** The chief and manager arm a watch before ending a turn; it wakes them when an agent
  has gone quiet while slices are ready.
- **Slices are kinds of fault, not single cases.** "Done" means the scoreboard moved on every case the fault affects and no
  case went backwards, checked on at least one input the builder never ran.
- **The system has to work without an agent in the loop.** A result that needed an agent to run a script by hand is not a
  result.

## Install

You need [Claude Code](https://claude.com/claude-code), `git`, `python3`, `flock`, `rsync` and the
[beads](https://github.com/steveyegge/beads) tracker (`npm i -g @beads/bd`).

```bash
git clone https://github.com/olihb005/Projet-Development-tools
cd Projet-Development-tools
./install.sh          # copies the kit to ~/.claude/tools/swarm and the skill to ~/.claude/skills/swarm
./tests/smoke.sh      # optional: runs one slice through the whole queue with no agents
```

## Start a swarm

```bash
S=~/.claude/tools/swarm/swarm
cd ~/code/my-project && bd init --prefix mp            # once per repository
$S init my-swarm --repo ~/code/my-project              # writes the role files and the run folder
$EDITOR ~/.claude/swarm/my-swarm/roles/COMMON.md       # say what you are building, your rules, where things live
$S q my-swarm add "Login form validates email" "Reject malformed addresses with a plain message. Done when the form test passes and a verifier has tried five bad addresses.
files: web/login.js, web/login.test.js" 1
$S board my-swarm --live --port 8899 &                 # http://127.0.0.1:8899/
```

Then, in a Claude Code session in that project, ask it to **"run the my-swarm swarm"**. The installed skill launches the
chief, which launches the manager, which sizes and launches the pool.

## Commands

| Command | What it does |
|---|---|
| `swarm init <name> --repo <path>` | Create a swarm: config, run folder, role files |
| `swarm q <name> add "<title>" "<what, done-when, files: …>" [0-4]` | Queue a slice (0 is most urgent) |
| `swarm q <name> next <worker>` / `done` / `back` | Take a slice, hand it in, or give it back with a note |
| `swarm q <name> toverify <verifier>` / `verified <verifier> <id> "<holds\|partly\|does not hold>: …"` | Check a built slice |
| `swarm q <name> committed <worker> <id> <commit>` | Record a commit made after a "holds" |
| `swarm q <name> tell <from> <to\|workers\|verifiers\|all> "<text>"` / `inbox <name>` | Message any agent |
| `swarm q <name> doing <name> "<a few words>"` / `post <name> "<headline>" "<text>" [file]` | Label a node; post a result |
| `swarm q <name> who` / `list` | Who is on what; what is queued |
| `swarm wake <name> <chief\|manager> [beat] [idle]` | Exit when someone is idle with work waiting, or on a heartbeat |
| `swarm backup <name> <dest>` | Copy the working tree aside every two minutes |
| `swarm board <name> --live [--port P]` | The live board |
| `swarm status <name>` / `swarm stop <name>` | Summary; stop the board and backup loops |

## Sizing

| Size | Agents | Use it for |
|---|---|---|
| Small | chief, 2 workers, 1 verifier (the chief manages) | One feature, a few hours |
| Medium | chief, manager, 4 workers, 2 verifiers | A product area with independent parts |
| Large | chief, manager, 6 workers, 3 verifiers | Many independent files and a machine that can take it |

Past about six workers the limit is usually the machine and the number of files that can be worked on independently, not the
agents. Cap heavy runs (builds, long tests) at two at a time across the swarm; the role files tell agents how to take turns.

## Several swarms at once

Each swarm has its own name, run folder, role files and board port, so you can run more than one, on one account or several.

- **Different repositories:** nothing to do. `swarm init` each one and give each board its own `--port`.
- **The same repository:** give each swarm its own git worktree and branch, and pass that worktree as `--repo`. The queue lock
  is per tracker database, so swarms sharing a tracker wait for each other rather than collide; give each its own `bd` prefix
  or label if you want the queues kept apart.
- **Different Claude accounts:** a swarm belongs to the session that launched it. Start each in its own terminal, and pass
  `--subagents ~/.claude/projects/<project>/<session id>/subagents` to `swarm init` so the board watches the right agents.
  Usage limits are per account; agree a stop line for each and have the chief close out before it.

## Layout

```
swarm/                 the kit, installed to ~/.claude/tools/swarm
  swarm                the command
  q.sh                 queue and messages, on bd, behind one lock, with a cached snapshot the board reads
  wake.sh  backup.sh   idle watch; working-tree backup
  board_live.py  board_page.html    live board (server-sent events, no page reloads)
  board.py             a static HTML board, for when you cannot run a server
  templates/roles/     COMMON, CHIEF, MANAGER, WORKER, VERIFIER
skill/SKILL.md         the Claude Code skill
tests/smoke.sh         one slice through the queue, no agents
```

## Limits

- Agents are Claude Code background agents. One that has ended can be woken by message; one whose session has closed cannot.
- Claude Code's permission checks may refuse an agent's `git commit`. Decide beforehand whether agents may commit in your
  repository, or have the main session make the commits the chief presents.
- The board's work animation and click-through detail were built during one project and have had little testing elsewhere.
- Linux and macOS. `flock` is not installed on macOS by default (`brew install flock`).

## Licence

MIT.
