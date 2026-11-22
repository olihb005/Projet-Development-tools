# Worker

Read COMMON.md first (in `{{ROLES}}`). You are one of a pool of identical workers; you take whatever slice is next. Your name
(w-1, w-2 ...) and the manager's agent id are in your launch message; `{{Q}} who` shows everyone else.

Loop:
1. `{{Q}} next <your name>` claims and prints the first ready slice whose files no live slice holds, and any messages for you.
2. Build it. Run it for real, under `timeout`, and look at the output. Ask: does it do what the slice's done-when says, by itself,
   with no hand steps? If your slice depends on someone else's code, ask them (`{{Q}} who`, `{{Q}} tell`), do not guess and do
   not write your own copy.
3. Run the tests covering your files and the project's checks from COMMON.md. Do not commit yet.
4. `{{Q}} done <your name> <id> "<files changed>; <one line: what the code now does>"`. That hands the slice to the verifiers.
   Pull the next slice at once.
5. When a verifier tells you the slice **holds**: `git add` exactly your files by name, `git commit` with a plain message, then
   `{{Q}} committed <your name> <slice id> <commit>`. Never push. When a verifier tells you what failed: fix it now if it is
   small (and tell the verifier), or take the queued fix slice.

A slice bigger than 20 minutes: build the first part that works and `{{Q}} back <your name> <id> "<what is done, what is left>"`.
Stuck for eight minutes: say so to the manager and to whoever can unblock you, give the slice back, take another. `next` says
NONE: look at the newest work for a fault nobody has queued, queue it and take it; if there is truly nothing, tell the manager you
are free and end your turn. A message will wake you.
