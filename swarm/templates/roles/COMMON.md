# {{NAME}} swarm: what every agent follows

Created {{STARTED}}. Repo `{{REPO}}`, branch `{{BRANCH}}`. Run folder `{{RUN}}`. Roles live in `{{ROLES}}`.

The three sections marked FILL IN are written by the user or the main session before any agent is launched. Everything else is
the general method and stays as it is.

## What we are building

<!-- FILL IN (main session, from the user's direction): 3 to 8 lines. What the finished thing is, who it is for, what "done" means,
and the one test that decides whether a slice counts. Quote the user's own words where they gave them, with the date. -->

_not filled in yet_

## Rules of this project

<!-- FILL IN: the rules of this product that every slice must obey: formats, forbidden shortcuts, data that is read-only, tests that
must still pass, limits of the machine. Short bullets, each checkable. -->

_not filled in yet_

## Places

<!-- FILL IN: where things are. Code areas, test folders, the interpreter to use, data folders, scratch folder, the state file. -->

- Repo: `{{REPO}}`, branch `{{BRANCH}}`.
- Results and run records: `{{RUN}}`.

## How the swarm runs

One tree under the main session, and a mesh for talking. Main launches the chief. The chief launches the manager. The manager
launches and wakes the workers and verifiers, as many as the queue and the machine justify, and adds or retires them as that
changes. Everyone is long-lived: you work, and when you have nothing to do you end your turn and cost nothing; a message wakes
you with your history intact.

- **Nobody sits idle while there is work.** Before ending a turn ask: is there a slice I can take, a result I can check, a fault I
  have seen, a neighbour I can unblock? Only when the answer is no do you stop. The manager wakes anyone idle the moment there is
  work for them.
- **The queue** is `{{Q}}` (run it bare for its commands; it runs on the `bd` tracker inside the repo). A slice is 15 to 20 minutes
  and its description ends with a line `files: a.py, b.py`; two live slices never share a file. A slice names its done-when.
- **Messages: a mesh, not a chain.** `{{Q}} who` lists everyone: name, role, agent id, whether working or idle, what each holds.
  To message anyone: `{{Q}} tell <your name> <name> "<text>"` (this is the record, and it shows on the board), and if the receiver is
  idle also send the same text with the SendMessage tool to its agent id (ToolSearch "select:SendMessage"), which wakes it. Talk
  sideways as much as up and down: a worker asks the worker whose code it depends on for the exact name and arguments; a verifier
  tells the worker whose slice it checked exactly what failed, with the path, and that worker answers; two workers about to touch
  the same thing settle who does it. Read `{{Q}} inbox <your name>` every few minutes while you work and answer in one line. Each
  wake re-reads the receiver's whole history, so send few messages and make each complete.
- **Commit chain.** A worker builds and leaves its files uncommitted. A verifier checks the slice. On "holds", the worker commits
  exactly its files by name with a plain message and records it with `{{Q}} committed <name> <slice> <commit>`. Nobody pushes except
  the main session. The chief collects the verified commits, checks them, and presents them to main; main approves and pushes.
  Never push to the main branch of a shared repo, never force.
- **Only the chief presents finished work to the main session** (SendMessage to "main"). Everyone else reports to the manager or
  the chief.
- **The ledger** is `{{RUN}}/ledger.md`: one dated line for the record, with the time from `date`.
- **Nothing falls through.** A fault you see goes to its owner by message and into the queue with the path that shows it. A slice
  you cannot finish goes back with what is left. Leftovers are queued, never only written down.
- **Time labels come from the `date` command**, never from memory.

## Keeping the board and the machine honest

- **Say what you are on.** `{{Q}} doing <your name> "<three to five plain words>"` whenever your task changes. It is the label
  under your node on the board, so write it for someone who has not read the queue.
- **Post results as headlines.** `{{Q}} post <your name> "<one plain sentence with its number>" "<what it means, what is still
  wrong>" [file]`. No slice ids, file names or working jargon. Bad news is posted the same way.
- **Heavy runs take turns.** At most two heavy runs (a long test run, a build, a big import) across the whole swarm at once.
  Before one: `{{Q}} status <your name> "heavy: <what>"`; wait if two are announced and not finished; afterwards
  `{{Q}} status <your name> "done: <what>"`. Always under `nice` and `timeout`.
- **Commit messages are for strangers.** A subject of 72 characters or fewer that says what changed, a blank line, then why.
