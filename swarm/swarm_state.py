#!/usr/bin/env python3
"""Read one swarm's run folder into a plain dict for the next-gen board. Read-only, no model, no tracker call: it reads the files
the kit already writes (swarm.json, roster.txt, queue.json snapshot, messages.log, verify.log, commits_verified.log, ledger.md,
acceptance/*/scoreboard.md, deliverables.jsonl, taglines.json) plus agent transcript mtimes and a few cheap `git log` calls.
as_of: the moment the board is drawn for (default now). Agent state is judged against it, so a recorded run can be replayed."""
import calendar, glob, hashlib, json, os, re, subprocess, time

LIVE_MIN, SLOW_MIN = 2.0, 5.0          # transcript touched < 2 min ago: working; < 5 min: quiet; else idle (same as board.py)
SKIP = ("Board is live", "TEST", "ZZ")


def _sh(args, t=10):
    try: return subprocess.run(args, capture_output=True, text=True, timeout=t).stdout
    except Exception: return ""


def _lines(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f: return f.read().splitlines()
    except Exception: return []


def _json(p, default):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return default


def clean_title(title):
    """A slice title as a person would say it: drop codes and numbering at the front ("Slice 4: ", "M2 ", "S-041 ")."""
    t = (title or "").strip()
    for _ in range(3):
        t2 = re.sub(r"^\s*(?:(?:slice|task|step|item)\s*#?\d+[a-z]?|[A-Z]{1,3}-?\d+[a-z]?(?:-\d+)?)\s*[:.)\-–]?\s+", "", t, flags=re.I)
        if t2 == t: break
        t = t2
    return t or (title or "")


def tagline(title):
    t = re.split(r"[:(;]| - ", clean_title(title))[0].strip()
    w = t.split(); return " ".join(w[:5]) + ("…" if len(w) > 5 else "")


def load_pack(spec=None):
    """A character pack: a name in packs/ (neutral, nerd), a path to a JSON file, or none. Default: neutral."""
    spec = spec or os.environ.get("SWARM_CHARACTERS") or "neutral"
    if spec == "none": return {"pack": "", "roles": {}}
    p = spec if spec.endswith(".json") or os.sep in spec else os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs", spec + ".json")
    return _json(p, {"pack": "", "roles": {}})


def assign_characters(agents, pack, swarm=""):
    """Each agent gets a character from its role's list, picked by a hash of swarm and agent name (stable across redraws); a clash inside
    the swarm moves to the next free one. Agents are taken in name order so the result does not depend on roster order."""
    roles, used = pack.get("roles") or {}, set()
    for a in sorted(agents, key=lambda a: a["name"]):
        pool = roles.get(a["role"]) or roles.get("other") or []
        if not pool: a["char"] = None; continue
        i0 = int(hashlib.md5((swarm + "/" + a["name"]).encode()).hexdigest(), 16) % len(pool)
        for k in range(len(pool)):
            c = pool[(i0 + k) % len(pool)]
            if c["name"] not in used or k == len(pool) - 1: break
        used.add(c["name"]); a["char"] = {"name": c["name"], "short": c.get("short") or c["name"], "aside": c.get("aside") or c.get("quote") or "", "from": c.get("from", "")}


def role_word(name, role):
    if name == "main": return "Main"
    if name == "queue": return "The queue"
    if name in ("all", "workers", "verifiers"): return {"all": "everyone", "workers": "the workers", "verifiers": "the verifiers"}[name]
    return {"chief": "The chief", "manager": "The manager", "worker": f"Worker {name}", "verifier": f"Verifier {name}",
            "researcher": f"Researcher {name}"}.get(role, name)


def humanize(m, roles, titles, idre):
    """Rewrite a message in plain English with slice titles instead of tracker ids. Keeps the original as m['raw'].
    Returns (text, kind) where kind drives the pulse on the board."""
    t, who = m["text"], role_word(m["from"], roles.get(m["from"], ""))
    q = lambda i: "‘" + clean_title(titles.get(i, i))[:70] + "’"
    sub = lambda x: idre.sub(lambda g: q(g.group(0)), x) if idre else x
    r = lambda pat: re.match(pat, t, re.S)
    if not m["auto"]: return sub(t), "msg"
    if (g := r(r"took (\S+?):")): return f"{who} picked up {q(g[1])}", "took"
    if (g := r(r"built (\S+?) \(.*?\):\s*(.*)")): return f"{who} finished {q(g[1])} and sent it for checking" + (f": {sub(g[2])}" if g[2] else ""), "built"
    if (g := r(r"built (\S+?),")): return f"{who} handed {q(g[1])} to the verifiers", "built"
    if (g := r(r"checking your slice (\S+)")): return f"{who} is checking {q(g[1])}", "checking"
    if (g := r(r"verdict on (\S+?):\s*(.*)")):
        v = g[2].strip(); low = v.lower()
        if low.startswith(("does not hold", "fail")): return f"{who} failed {q(g[1])}: {sub(v)}", "back"
        if low.startswith("partly"): return f"{who} sent {q(g[1])} back, it partly holds: {sub(v[6:].lstrip(':, '))}", "back"
        return f"{who} passed {q(g[1])}: {sub(re.sub(r'^holds\W*', '', v))}", "pass"
    if (g := r(r"committed (\S+) as \S+")): return f"{who} committed {q(g[1])}", "committed"
    if (g := r(r"new slice:\s*(.*)")): return f"New slice queued: ‘{clean_title(g[1].strip())[:70]}’", "new"
    if (g := r(r"launched as (\S+)")): return f"{role_word(m['to'], g[1])} joined the swarm as {g[1]}", "join"
    if (g := r(r"giving (\S+) back:\s*(.*)")): return f"{who} gave {q(g[1])} back: {sub(g[2])}", "back"
    if (g := r(r"posted a deliverable:\s*(.*)")): return f"{who} posted ‘{g[1].strip()}’", "post"
    return f"{who}: {sub(t)}", "status"


def actions(p, n=8):
    """The last few things an agent did, from the tail of its transcript (descriptions, commands, file paths)."""
    try:
        with open(p, "rb") as f:
            f.seek(max(0, os.path.getsize(p) - 60000)); tail = f.read().decode("utf-8", "ignore")
        h = re.findall(r'"(?:description|command|file_path)":\s*"((?:[^"\\]|\\.){2,170})', tail)
        return [x.encode().decode("unicode_escape", "ignore").replace("\n", " ")[:170] for x in h[-n:]]
    except Exception: return []


def auto_as_of(cfg_path):
    """For replaying a recorded or generated run: the latest moment anything was written in it."""
    c = _json(cfg_path, {}); run = c.get("run", ""); ts = []
    q = _json(os.path.join(run, "queue.json"), {})
    if isinstance(q.get("t"), (int, float)): ts.append(q["t"])
    for ln in _lines(os.path.join(run, "messages.log"))[-1:]:
        try: ts.append(float(ln.split("|", 1)[0]))
        except Exception: pass
    sub = c.get("subagents") or ""
    for p in glob.glob(os.path.join(sub, "agent-*.jsonl")):
        try: ts.append(os.path.getmtime(p))
        except Exception: pass
    return max(ts) if ts else time.time()


def read_swarm(cfg_path, as_of=None, git=True, pack=None):
    now = as_of or time.time()
    c = _json(cfg_path, {}); name = c.get("name") or os.path.basename(os.path.dirname(cfg_path))
    run, repo, sub = c.get("run") or os.path.dirname(cfg_path), c.get("repo") or "", c.get("subagents") or ""
    started = (c.get("started") or "1970-01-01 00:00").replace("T", " ")[:16]
    started_epoch = c.get("started_epoch") or 0
    # ---- queue snapshot (written by q.sh on every add/next/done/back)
    snap = _json(os.path.join(run, "queue.json"), {})
    for k in ("in_progress", "open", "closed"): snap.setdefault(k, [])
    keep = lambda i: not (i.get("title") or "").startswith(SKIP)
    key = lambda i: (i.get("priority") if i.get("priority") is not None else 9, i.get("created_at") or "", i.get("id") or "")
    mk = lambda i: {"id": i.get("id"), "p": i.get("priority"), "who": i.get("assignee") or "", "title": clean_title(i.get("title"))[:120],
                    "tag": tagline(i.get("title")), "from": (re.search(r"^from:\s*(\S+)", i.get("description") or "", re.M) or [None, ""])[1]}
    prog = [mk(i) for i in sorted(filter(keep, snap["in_progress"]), key=key)]
    ready = [mk(i) for i in sorted(filter(keep, snap["open"]), key=key)]
    closed = sorted(filter(keep, snap["closed"]), key=lambda i: i.get("closed_at") or "")
    titles = {i.get("id"): (i.get("title") or "") for k in ("in_progress", "open", "closed") for i in snap[k]}
    owner = {i.get("id"): (i.get("assignee") or "") for k in ("in_progress", "open", "closed") for i in snap[k]}
    # ---- verification and commits
    claimed, verdict, verd = {}, {}, []
    for v in _lines(os.path.join(run, "verify.log")):
        f = v.split()
        if len(f) > 3 and f[2] == "claimed": claimed[f[0]] = (f[1], f[3])
        m = re.match(r"(\S+) (\S+) verdict (\d\d:\d\d) (.*)", v)
        if m:
            txt = m.group(4); low = txt.lower()
            kind = "not" if low.startswith(("does not hold", "fails", "fail")) else "partly" if low.startswith("partly") else "holds"
            verdict[m.group(1)] = kind
            verd.append({"id": m.group(1), "by": m.group(2), "hm": m.group(3), "v": kind, "text": txt[:200], "tag": tagline(titles.get(m.group(1), "")), "who": owner.get(m.group(1), "")})
    committed = {}
    for ln in _lines(os.path.join(run, "commits_verified.log")):
        f = ln.split("|")
        if len(f) >= 4: committed[f[2]] = {"hm": f[0], "by": f[1], "h": f[3]}
    cids = [i.get("id") for i in closed]
    awaiting = [i for i in cids if i not in claimed and i not in verdict]
    checking = [{"id": i, "v": claimed[i][0], "w": owner.get(i, ""), "tag": tagline(titles.get(i, ""))} for i in claimed if i not in verdict]
    holds_uncommitted = [i for i, k in verdict.items() if k == "holds" and i not in committed]
    back = [i for i, k in verdict.items() if k != "holds"]
    # ---- git (cheap, read-only)
    ncom, unp, commits = 0, [], []
    if git and repo and os.path.isdir(repo):
        G = ["git", "-C", repo]
        ncom = len(_sh(G + ["log", f"--since={started}", "--format=%h"]).split())
        up = c.get("branch") and _sh(G + ["rev-parse", "--verify", "-q", f"origin/{c['branch']}"]).strip()
        unp = _sh(G + ["log", f"origin/{c['branch']}..HEAD" if up else f"--since={started}", "--format=%h"]).split()
        for l in _sh(G + ["log", "-20", "--format=%cd%x09%h%x09%s", "--date=format:%H:%M", f"--since={started}"]).splitlines():
            p = l.split("\t")
            if len(p) == 3: commits.append({"hm": p[0], "h": p[1], "s": p[2][:120], "wait": p[1] in unp})
    # ---- messages
    msgs = []
    for i, ln in enumerate(_lines(os.path.join(run, "messages.log"))):
        f = ln.split("|", 4)
        if len(f) == 5:
            try: t = float(f[0])
            except Exception: continue
            if t > now + 1: continue
            msgs.append({"i": i, "t": t, "hm": f[1], "from": f[2], "to": f[3], "text": f[4].replace("[auto] ", "").strip()[:300], "auto": f[4].startswith("[auto]")})
    # ---- agents
    tags = _json(os.path.join(run, "taglines.json"), {}); agents = []
    for ln in _lines(os.path.join(run, "roster.txt")):
        f = ln.strip().split("|")
        if len(f) < 3: continue
        nm, aid, role = f[0], f[1], f[2]
        p = os.path.join(sub, f"agent-{aid}.jsonl"); mt = os.path.getmtime(p) if os.path.isfile(p) else None
        m = (now - mt) / 60 if mt else 999
        st = "live" if m < LIVE_MIN else "slow" if m < SLOW_MIN else "idle"
        sl = next((x for x in prog if x["who"] == nm), None)
        chk = next((x for x in checking if x["v"] == nm), None)
        own = tags.get(nm) or {}
        # what it is doing, in plain words: its own label (q.sh doing) first, then the slice it holds or checks, then its state
        tag = own.get("text") if own and now - own.get("t", 0) < 1500 else ("Building " + sl["tag"]) if sl else ("Checking " + chk["tag"]) if chk else \
            "Idle, waiting for a message" if st == "idle" else "Quiet for a few minutes" if st == "slow" else \
            {"chief": "Steering the swarm", "manager": "Running the queue", "worker": "Between slices", "verifier": "Looking for work to check"}.get(role, "Working")
        agents.append({"name": nm, "id": aid, "role": role, "by": f[3] if len(f) > 3 else "", "at": f[4] if len(f) > 4 else "",
                       "state": st, "ago": int(m) if mt else None, "slice": sl, "check": chk, "tag": tag, "acts": actions(p) if mt else []})
    assign_characters(agents, pack if pack is not None else load_pack(), name)
    roles = {a["name"]: a["role"] for a in agents}; disp = {a["name"]: (a["char"] or {}).get("short") or a["name"] for a in agents}
    disp.update(main="Main", queue="Queue", all="everyone", workers="workers", verifiers="verifiers")
    ids = sorted((i for i in titles if i), key=len, reverse=True)
    idre = re.compile("|".join(re.escape(i) for i in ids)) if ids else None
    for m in msgs:
        m["raw"] = m["text"]; m["text"], m["kind"] = humanize(m, roles, titles, idre)
        m["fn"], m["tn"] = disp.get(m["from"], m["from"]), disp.get(m["to"], m["to"])
    for v in verd: v["title"] = clean_title(titles.get(v["id"], ""))[:90]
    nw = sum(1 for a in agents if a["role"] == "worker"); live = sum(1 for a in agents if a["state"] == "live")
    # ---- goal (acceptance scoreboard, newest)
    acc = sorted(glob.glob(os.path.join(run, "acceptance", "*", "scoreboard.md")), key=os.path.getmtime)
    goal = {"text": "", "lines": [], "done": None, "total": None, "file": ""}
    if acc:
        L = [l.strip() for l in _lines(acc[-1]) if l.strip()][:14]
        g0 = next((re.sub(r"^(#+\s*|goal:\s*)", "", l, flags=re.I) for l in L if re.match(r"^(#|goal:)", l, re.I)), L[0] if L else "")
        m = next((re.search(r"(\d+)\s+of\s+(\d+)", l) for l in L if re.search(r"(\d+)\s+of\s+(\d+)", l)), None)
        goal = {"text": g0[:140], "lines": [l for l in L if not l.lower().startswith("goal:")][:10], "done": int(m.group(1)) if m else None,
                "total": int(m.group(2)) if m else None, "file": os.path.relpath(acc[-1], run)}
    total = len(closed) + len(prog) + len(ready)
    if goal["done"] is None: goal.update(done=len([i for i in verdict.values() if i == "holds"]), total=total or None, derived=True)
    # ---- queue load, runway and warnings
    runway = len(ready) / max(nw, 1)
    if not ready and not prog and total: warn = {"level": "done", "text": "queue empty: every slice built"}
    elif not total: warn = {"level": "warn", "text": "no slices yet: stock the queue"}
    elif ready and not live and not any(a["state"] == "slow" for a in agents): warn = {"level": "bad", "text": "stalled: work waiting, nobody working"}
    elif not ready: warn = {"level": "bad", "text": "empty: workers run dry after this round, restock"}
    elif len(ready) < max(2, nw): warn = {"level": "warn", "text": f"low: under one round left, restock"}
    else: warn = {"level": "ok", "text": f"{runway:.1f} rounds of work for {nw} worker{'s' if nw != 1 else ''}"}
    status = "finished" if warn["level"] == "done" else "stalled" if warn["text"].startswith("stalled") else "busy" if live else "quiet"
    # ---- time series from real timestamps (no history file needed)
    def iso_epoch(s):   # bd stamps UTC with a Z; without one, treat it as local time
        try:
            tt = time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
            return calendar.timegm(tt) if s.endswith("Z") else time.mktime(tt)
        except Exception: return None
    day = started[:10]
    def hm_epoch(hm):
        try: return time.mktime(time.strptime(day + " " + hm, "%Y-%m-%d %H:%M"))
        except Exception: return None
    built_t = sorted(x for x in (iso_epoch(i.get("closed_at") or "") for i in closed) if x)
    holds_t = sorted(x for x in (hm_epoch(v["hm"]) for v in verd if v["v"] == "holds") if x)
    msg_t = [m["t"] for m in msgs]
    deliv = [json.loads(l) for l in _lines(os.path.join(run, "deliverables.jsonl")) if l.strip().startswith("{")][-8:][::-1]
    return {"name": name, "cfg": cfg_path, "started": started, "started_epoch": started_epoch, "as_of": now,
            "goal": goal, "agents": agents, "workers": nw, "live": live,
            "q": {"ready": ready[:60], "nready": len(ready), "prog": prog, "nprog": len(prog), "nbuilt": len(closed), "total": total},
            "stages": {"ready": len(ready), "building": len(prog), "awaiting": len(awaiting), "checking": len(checking),
                       "holds": len(holds_uncommitted), "committed": len(committed), "back": len(back)},
            "checking": checking, "verd": verd[-40:][::-1], "nverd": len(verd), "nholds": sum(1 for v in verd if v["v"] == "holds"),
            "committed": [{"id": k, "tag": tagline(titles.get(k, "")), "title": clean_title(titles.get(k, ""))[:90], **v} for k, v in list(committed.items())[-30:]],
            "git": {"n": ncom, "unpushed": len(unp), "commits": commits},
            "msgs": msgs[-400:], "nmsgs": len(msgs), "ledger": _lines(os.path.join(run, "ledger.md"))[-10:], "deliv": deliv,
            "runway": round(runway, 2), "warn": warn, "status": status,
            "series": {"built": built_t, "holds": holds_t, "msgs": msg_t[-400:]}}


def usage():
    u = _json(os.path.expanduser("~/.claude/usage_meter.json"), {})
    rs = u.get("five_hour_resets_at")
    return {"five": u.get("five_hour"), "seven": u.get("seven_day"), "reset": time.strftime("%H:%M", time.localtime(rs)) if isinstance(rs, (int, float)) else ""}
