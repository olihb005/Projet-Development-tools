#!/usr/bin/env python3
"""Next-gen fleet board: any number of swarms on one page, drawn by a plain script (no model, standard library only). A fleet is
just a list of swarm.json files; they may sit in different repos and use one tracker or several. Each swarm is a pool sized by its
agent count, packed into balanced rows under one main session; a table gives every swarm's goal, queue load, runway and stage
load; click a pool or a row to open that swarm's full board on the same page. Same skins, layouts, packs and tabs as board_next.py.
usage:
  fleet_next.py [SOURCE ...] [--title T] [--out FILE] [--loop SECONDS] [--until YYYYmmddHHMM] [--as-of auto|EPOCH] [--no-git]
                [--characters neutral|nerd|none|PACK.json] [--skin K] [--layout K] [--tab K]
  fleet_next.py [SOURCE ...] --serve [--port 8897]
SOURCE is any mix of: a swarm.json; a directory (its */swarm.json, swarms/*/swarm.json or own swarm.json); a quoted glob; or a
fleet.json {"title": "...", "swarms": [SOURCE, ...]} whose entries are relative to it. With no SOURCE: every swarm under
$SWARM_ROOT (the kit's root, default ~/.claude/swarm). Sources are read again on every redraw, so new swarms appear by themselves."""
import glob, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_next import arg, collect, page, serve

VALUE_FLAGS = {"--root", "--out", "--loop", "--until", "--as-of", "--port", "--title", "--characters", "--skin", "--layout", "--tab"}
ROOT = os.environ.get("SWARM_ROOT") or os.path.join(os.path.expanduser("~"), ".claude", "swarm")


def sources():
    out, skip = [], False
    for a in sys.argv[1:]:
        if skip: skip = False; continue
        if a in VALUE_FLAGS: skip = True; continue
        if not a.startswith("--"): out.append(a)
    if arg("--root"): out.append(arg("--root"))   # kept for compatibility with earlier calls
    return out or [ROOT]


def expand(src, base="", meta=None):
    """Turn one SOURCE into swarm.json paths (see the usage text)."""
    p = os.path.expanduser(src if os.path.isabs(os.path.expanduser(src)) or not base else os.path.join(base, src))
    if os.path.isdir(p):
        own = os.path.join(p, "swarm.json")
        return [own] if os.path.isfile(own) else sorted(glob.glob(os.path.join(p, "*", "swarm.json")) + glob.glob(os.path.join(p, "swarms", "*", "swarm.json")))
    if os.path.isfile(p):
        try: d = json.load(open(p))
        except Exception: return []
        if isinstance(d, dict) and isinstance(d.get("swarms"), list):        # a fleet.json
            if meta is not None and d.get("title"): meta.setdefault("title", d["title"])
            return [x for s in d["swarms"] for x in expand(s, os.path.dirname(os.path.abspath(p)), meta)]
        return [p] if isinstance(d, dict) and d.get("run") else []
    return sorted(x for x in glob.glob(p) if os.path.isfile(x))


def configs(meta=None):
    seen, out = set(), []
    for s in sources():
        for c in expand(s, meta=meta):
            c = os.path.abspath(c)
            if c not in seen: seen.add(c); out.append(c)
    key = lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", os.path.basename(os.path.dirname(p)))]   # x2 before x10
    return sorted(out, key=key)


def main():
    meta = {}; cfgs = configs(meta)
    if not cfgs: sys.exit("fleet_next.py: no swarm.json found (pass swarm.json files, directories, globs or a fleet.json)")
    git = "--no-git" not in sys.argv; as_of = arg("--as-of"); loop = int(arg("--loop", 0) or 0); until = arg("--until")
    title = arg("--title") or meta.get("title") or "Swarm fleet"
    make = lambda refresh=0: collect(configs(), as_of, git, mode="fleet", refresh=refresh, title=title)
    if "--serve" in sys.argv: serve(make, title, int(arg("--port", 8897))); return
    out = arg("--out") or os.path.join(ROOT, "fleet_next.html")
    while True:
        try:
            html = page(make(loop), title)
            open(out + ".tmp", "w", encoding="utf-8").write(html); os.replace(out + ".tmp", out)
        except Exception as e: sys.stderr.write(f"fleet_next: {e!r}\n")
        if not loop or (until and time.strftime("%Y%m%d%H%M") >= until): break
        time.sleep(loop)
    if not loop: print(out)


if __name__ == "__main__":
    main()
