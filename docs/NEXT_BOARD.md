# Swarm board, next version

A next-gen board for the swarm kit, built on the current board (`board.py`, `board_live.py` and the `board_page.html` it serves)
It is additive: the original board scripts are unchanged and still work.

## Files

| File | Role |
|---|---|
| `swarm_state.py` | Reads one run folder into a dict. Read-only, standard library, no model, no tracker call |
| `board_next.py` | One swarm: a static file (`--out`, `--loop N`) or a live local server (`--serve`) |
| `fleet_next.py` | Any number of swarms on one page; same outputs |
| `board_next_page.html` | The page template: one JS app that draws a swarm or a fleet |
| `board_skins.css`, `board_skins.json` | The five skins, as data. The JSON also holds the default skin, layout and tab |
| `packs/neutral.json` (default), `packs/nerd.json` | Character packs, as data |

## How to run

```bash
K=<folder holding these files>          # after the merge: ~/.claude/tools/swarm
SWARM_CONFIG=<run>/swarm.json $K/board_next.py                       # writes <board>_next.html beside the kit's board
SWARM_CONFIG=<run>/swarm.json $K/board_next.py --loop 10             # redrawn every 10 s (page refreshes itself)
SWARM_CONFIG=<run>/swarm.json $K/board_next.py --serve --port 8898   # live on 127.0.0.1, never reloads
$K/fleet_next.py                                                     # every swarm under $SWARM_ROOT (default ~/.claude/swarm)
$K/fleet_next.py fleet.json --serve                                  # or any mix of swarm.json files, dirs, globs, fleet.json
```

**Options**

| Option | What it does |
|---|---|
| `--characters neutral\|nerd\|none\|PACK.json` (or `SWARM_CHARACTERS`) | Character pack. `neutral` is the default |
| `--skin`, `--layout`, `--tab` | Change the page default for this run. The kit default comes from `board_skins.json` |
| `--no-git` | Skip the three cheap `git log` calls per swarm |
| `--as-of auto` | Judge working and idle against the last write in the run folder; for replaying a recorded or fake run |
| `--title` (fleet only) | Page title |

**A fleet is a list of swarm.json files.** The arguments can be swarm.json files, directories (their `*/swarm.json`,
`swarms/*/swarm.json` or own `swarm.json`), quoted globs, or a `fleet.json`:

```json
{"title": "...", "swarms": ["../a/swarm.json", "/runs/b", "/runs/*/swarm.json"]}
```

Entries in a `fleet.json` are relative to the file. Sources are re-read on every redraw, so new swarms appear by themselves. They
may live in different repos and use one tracker or several.

**On the page**, skin, layout and node tab are chosen with buttons and kept in the browser and the URL hash:
`#skin=tidepool&layout=subway&tab=strip`. Adding `&node=0|w-3` opens that node's tab; on a fleet page `&swarm=<name>` opens that
swarm.

## What changed from the current board

**Data**
- It reads only the kit's own files:
  - `swarm.json`, `roster.txt`
  - `queue.json` (the snapshot `q.sh` writes)
  - `messages.log`, `verify.log`, `commits_verified.log`, `ledger.md`
  - `acceptance/*/scoreboard.md`, `deliverables.jsonl`, `taglines.json`
  - agent transcript mtimes and tails
  - `git log`
- It never calls `bd` and writes nothing into the run folder. `board.py` calls `bd` and writes `board_history.json`.
- Charts come from real timestamps (`closed_at`, verdict times, message times), so they are right from the first draw.

**Names and words**
- **Names.** Every agent gets a display name from a character pack, picked by a hash of swarm and agent name, so it keeps its name
  between redraws and differs across swarms. Clashes inside a swarm move to the next free name.
  - The default pack is neutral call-signs (Wren, Harbour, Gauge…).
  - `packs/nerd.json` is optional: Hitchhiker's Guide, Archer, Bond, Star Trek, Discworld, Tolkien. The chief draws from M,
    Deep Thought, Picard and others; managers from Moneypenny, Ford Prefect and others; verifiers from Marvin, Q, Spock and others.
- **Roles stay visible.** The real role (Chief, Manager, Worker w-3, Verifier v-1) stays on every tile as a small subtitle, and
  inside the node.
- **The tile line says what the agent is doing, in plain words.** It is the agent's own `q.sh doing` label, else
  "Building ‹slice›", "Checking ‹slice›", "Idle, waiting for a message" and so on.
- **References are only dotted about.** A pack's `aside` line shows on hover and on idle tiles, never as a line on every tile.
- **Crew section.** A grid of these tiles under the graph; click one to open its tab.
- **Plain-English logs.** Every feed, tab and table reads as sentences with slice titles, and tracker ids and commit hashes appear
  only on hover:
  - "Worker w-1 picked up ‘Parse CSV bank export’"
  - "Verifier v-2 passed ‘…’: …"
  - "Worker w-1 committed ‘…’"
  - "New slice queued: ‘…’"

  Numbering at the front of a title ("Slice 4: ", "M2 ", "S-041 ") is dropped. Chips name the character and keep the role id beside it.

**Load and flow**
- **Load by stage**, as a band under the graph: ready, building, built and waiting for a check, being checked, passed and to commit,
  committed, sent back. The fleet shows its total, plus a small band per swarm.
- **Queue load per swarm**: built, in work and ready as one bar, plus runway (ready ÷ workers, in rounds) and a plain warning: low,
  restock; empty, workers run dry; stalled, work waiting and nobody working; queue empty, every slice built; no slices yet. The
  queue node holds its ready slices as dots (red P0, amber P1) and its ring takes the warning colour.
- **Goal** from the newest acceptance scoreboard, with the first "X of Y" drawn as a progress bar.
- **Animation** (kept from `board_x.py`):
  - Slices in work ride from the queue to their worker as small squares, and working nodes glow.
  - Work lines are coloured by how much waits on them, and active ones carry a moving dash.
  - A work event sends a pulse along its real path: picked up, built, checking, passed (to the product), failed (round the red loop
    back to the queue), committed (to main), new slice (chief to queue).
  - Messages fly along dotted chords.
- **Node tabs.** Side drawer (default) or timeline strip, for agents, the queue, the product and main.

**Any size, any fleet**
- Spacing and node size follow the worker count, from 1 to 10 and more.
- In a fleet, each swarm is a pool sized by its agent count. Pools are packed into balanced rows (at most four to a row), and in
  the twin-loop layout every second pool in a row is mirrored so neighbouring products face each other. 
- The fleet page also has a table (goal, agents, queue load and runway, stages, last word), a merged message feed, and "Who needs
  a hand", worst first. Click a pool or a row to open that swarm's full board on the same page.

**Five skins** (Ink & Wash, Tidepool, Copperplate, Interchange, Orrery) **and five layouts** (twin loop, hub and spoke, subway,
orbit, circuit). Any layout can wear any skin. Each skin is a CSS variable set plus one SVG touch:

| Skin | SVG touch | Nodes |
|---|---|---|
| Ink & Wash | Watercolour wash | Circles |
| Tidepool | Pools of light and glow | Circles |
| Copperplate | Grid board | Chips with pins |
| Interchange | Cased lines | Stations |
| Orrery | Star field and orbit rings | Circles |

**Not carried over from the current live page**: the project-specific scoreboard table and the deliverable cards (the file is
read but not drawn), hover path tracing, and the slice-path view.

## Known gaps

- **Small fleet pools have no labels.** Their names appear on hover and in the tab. Main's lines to the lower pools show only in
  the gaps between pools.
- **Lines cross in places.** Hub and Orbit cross lines by nature, . Worker labels sit over the
  build lines in twin loop and subway, readable only because of the text halo.
- **Static pages replay rather than stream.** A static page replays the events since the last redraw. `--serve` is live, but it
  re-renders the view when the data changes, and feed scroll positions reset then.
- **Group messages draw nothing on the graph.** Messages to `all`, `workers` or `verifiers` are in the feed but get no chord or
  pulse.
- **Thresholds are judgement calls.** Load colour: ready ÷ workers under 1.2 is "little", under 2.5 "some", otherwise "a lot".
  "To approve" is `git log origin/<branch>..HEAD`, or every commit since the start when there is no upstream.
- **Message rewriting** follows the exact wording `q.sh` writes today; a reworded `q.sh` line falls back to "‹role›: ‹text›", with
  ids still replaced by titles.
- **Fake data is thin.** Every fake agent has one transcript line, so "recent actions" is short, and the fake swarms were written
  within minutes, so the charts are short. This needs a look on a real swarm.
- **Browsers.** Tested only in headless Chrome at 1400 px. Not tested in Firefox or Safari, or at phone width.


## Defaults

In `board_skins.json`: skin Ink & Wash, layout twin loop, node tab side drawer, neutral character pack. Warnings use full vermilion because that skin's weakness is that a stall does not stand out. Change the defaults in the file or with `--skin`, `--layout`, `--tab`, `--characters`.

## Notes

- Python is standard library only and the page loads nothing from the network.
- The live server binds 127.0.0.1 and serves only `/` and `/state.json`; all run text is HTML-escaped.
- Tested in headless Chrome at 1400 px; not in Firefox or Safari or at phone width.
