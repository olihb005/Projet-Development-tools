#!/usr/bin/env python3
"""Swarm board, drawn by a plain script (no model). The swarm as a graph in groups: direction, management, workers, verifiers,
with the queue and the product between them. Nodes come from the roster, so the picture changes whenever agents are added or
retired. A link lights up between any two agents that have exchanged messages; a dot travels once when a message is sent; a
node that has just been woken flashes once. Click a node to see what that agent is doing.
usage: SWARM_CONFIG=<swarm.json> board.py [--loop SECONDS] [--until YYYYmmddHHMM]     (normally: swarm board <name> [--loop N])"""
import glob, html, json, math, os, re, shlex, subprocess, sys, time
_cp = os.environ.get("SWARM_CONFIG") or (sys.argv[sys.argv.index("--config") + 1] if "--config" in sys.argv else "")
if not _cp or not os.path.isfile(_cp): sys.exit("board.py: set SWARM_CONFIG to the swarm.json path")
_c = json.load(open(_cp)); os.environ["SWARM_CONFIG"] = _cp
CFG = {"title": _c["name"] + " swarm", "run": _c["run"], "repo": _c["repo"], "branch": _c.get("branch") or "",
       "q": os.path.join(os.path.dirname(os.path.abspath(__file__)), "q.sh"), "sub": _c.get("subagents") or "",
       "out": _c["board"], "since": (_c.get("started") or "1970-01-01 00:00").replace("T", " ")[:16]}
RUN, WT, Q, SUB, OUT = CFG["run"], CFG["repo"], CFG["q"], CFG["sub"], CFG["out"]
E = html.escape
COL = {"live": "#35d07f", "slow": "#f0b23a", "idle": "#6c8089", "hub": "#7fb3c2"}
WORD = {"live": "working now", "slow": "quiet for a few minutes", "idle": "idle: turn ended, a message wakes it", "hub": ""}
def sh(c, t=40):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t).stdout
    except Exception: return ""
def actions(p, n=7):
    try:
        with open(p, "rb") as f:
            f.seek(max(0, os.path.getsize(p) - 60000)); tail = f.read().decode("utf-8", "ignore")
        h = re.findall(r'"(?:description|command|file_path)":\s*"((?:[^"\\]|\\.){4,170})', tail)
        return [x.encode().decode("unicode_escape", "ignore").replace("\n", " ")[:170] for x in h[-n:]]
    except Exception: return []
def build():
    now = time.time()
    try: u = json.load(open(os.path.expanduser("~/.claude/usage_meter.json")))
    except Exception: u = {}
    five, seven = u.get("five_hour") or 0, u.get("seven_day") or 0
    rs = u.get("five_hour_resets_at"); rs = time.strftime("%H:%M", time.localtime(rs)) if isinstance(rs, (int, float)) else "?"
    roster = []
    try:
        for ln in open(RUN + "/roster.txt"):
            f = ln.strip().split("|")
            if len(f) >= 3: roster.append({"name": f[0], "id": f[1], "role": f[2], "by": f[3] if len(f) > 3 else "", "at": f[4] if len(f) > 4 else ""})
    except Exception: pass
    ql = [l for l in sh(Q + " list").splitlines() if l.startswith(("in_progress", "open"))]
    prog = [l for l in ql if l.startswith("in_progress")]; ready = [l for l in ql if l.startswith("open") and "Board is live" not in l]
    since_iso = CFG["since"].replace(" ", "T")
    try: cl = sorted([i for i in json.loads(sh(f"cd {shlex.quote(WT)} && bd list --status closed --json", 30)) if (i.get("closed_at") or "") >= since_iso and not i["title"].startswith(("ZZ", "TEST"))], key=lambda i: i.get("closed_at") or "", reverse=True)
    except Exception: cl = []
    ver = open(RUN + "/verify.log").read().splitlines() if os.path.isfile(RUN + "/verify.log") else []
    verd = [v for v in ver if " verdict " in v and len(v.split()) > 3 and v.split()[1].startswith("v-") and v.split()[3] >= CFG["since"][11:]]
    G = f"git -C {shlex.quote(WT)}"; BR = CFG["branch"]
    ncom = len(sh(f"{G} log --since='{CFG['since']}' --format=%h").split())
    up = None
    for r in ((f"origin/{BR}", "@{u}") if BR else ()):
        if sh(f"{G} rev-parse --verify -q {shlex.quote(r)}").strip(): up = r; break
    unpushed = sh(f"{G} log {shlex.quote(up)}..HEAD --format='%h %s'").splitlines() if up else sh(f"{G} log --since='{CFG['since']}' --format='%h %s'").splitlines()
    commits = sh(f"{G} log -12 --format='%cd  %h  %s' --date=format:%H:%M --since='{CFG['since']}'").splitlines()
    ledger = open(RUN + "/ledger.md").read().splitlines()[-8:] if os.path.isfile(RUN + "/ledger.md") else []
    msgs = []
    try:
        for ln in open(RUN + "/messages.log"):
            f = ln.rstrip("\n").split("|", 4)
            if len(f) == 5: msgs.append((float(f[0]), f[1], f[2], f[3], f[4]))
    except Exception: pass
    try: mem = json.load(open(RUN + "/board_history.json"))
    except Exception: mem = {}
    if isinstance(mem, list): mem = {"hist": mem}
    hist = [h for h in mem.get("hist", []) if now - h["t"] < 6 * 3600]; prev = mem.get("state", {}); woke = mem.get("woke", {})
    # ---- nodes, in groups
    agents = []
    for r in roster:
        p = f"{SUB}/agent-{r['id']}.jsonl"; mt = os.path.getmtime(p) if os.path.isfile(p) else None
        m = (now - mt) / 60 if mt else 999; s = "live" if m < 2 else "slow" if m < 5 else "idle"
        if prev.get(r["name"]) in ("idle", "slow") and s == "live": woke[r["name"]] = now
        sl = next((re.sub(r"^in_progress\s+", "", l) for l in prog if re.search(rf"\s{re.escape(r['name'])}\s", l)), "")
        agents.append(dict(r, state=s, mt=mt, slice=sl, acts=actions(p)))
    state_now = {a["name"]: a["state"] for a in agents}
    groups = [("Direction", [a for a in agents if a["role"] == "chief"], 150), ("Management", [a for a in agents if a["role"] == "manager"], 150),
              ("Workers", [a for a in agents if a["role"] == "worker"], 890), ("Verifiers", [a for a in agents if a["role"] == "verifier"], 890)]
    pos = {"main": (150, 60), "queue": (520, 190), "product": (520, 360)}; H = 520; g = []; panels = []
    def col(items, x, y0, y1):
        n = max(len(items), 1)
        for i, a in enumerate(items): pos[a["name"]] = (x, y0 + (y1 - y0) * (i + 0.5) / n)
    col(groups[0][1], 150, 130, 230); col(groups[1][1], 150, 300, 420)
    nw, nv = len(groups[2][1]), len(groups[3][1]); split = 60 + (H - 90) * (nw + 0.6) / max(nw + nv + 1.2, 1)
    col(groups[2][1], 930, 70, split - 10); col(groups[3][1], 930, split + 30, H - 20)
    panels = [("Direction", 30, 20, 240, 230), ("Management", 30, 270, 240, 170), (f"Workers ({nw})", 780, 20, 300, split - 20), (f"Verifiers ({nv})", 780, split + 10, 300, H - split - 20), ("Work", 400, 110, 240, 330)]
    g.append(f"<svg viewBox='0 0 1110 {H}' class='flow'>")
    for t, x, y, w, h in panels:
        g.append(f"<rect x='{x}' y='{y}' width='{w}' height='{h:.0f}' rx='14' fill='#101f26' stroke='#20333b'/><text x='{x+12}' y='{y+18:.0f}' class='gl'>{E(t.upper())}</text>")
    names = ["main"] + [a["name"] for a in agents]
    def curve(a, b):
        (x1, y1), (x2, y2) = pos[a], pos[b]; mx, my = (x1 + x2) / 2, (y1 + y2) / 2; dx, dy = x2 - x1, y2 - y1; L = math.hypot(dx, dy) or 1
        k = 0.18 if abs(dx) < 40 else 0.06; return f"M{x1:.0f},{y1:.0f} Q{mx - dy * k:.0f},{my + dx * k:.0f} {x2:.0f},{y2:.0f}"
    pair = {}
    for t, hm, frm, to, txt in [m for m in msgs if now - m[0] < 1800]:
        for tg in ([x for x in names if x != frm] if to == "all" else [to]):
            if frm in pos and tg in pos: pair[tuple(sorted((frm, tg)))] = pair.get(tuple(sorted((frm, tg))), 0) + (0.2 if to == "all" else 1)
    for (a, b), c in pair.items():
        if c >= 1: g.append(f"<path d='{curve(a, b)}' fill='none' stroke='#ffd166' stroke-opacity='.5' stroke-width='{min(1 + c * .7, 5):.1f}'/>")
    for l in prog:
        w = re.search(r"\s(\S+-\d+)\s", l)
        if w and w.group(1) in pos: g.append(f"<path d='{curve('queue', w.group(1))}' fill='none' stroke='#35d07f' stroke-opacity='.75' stroke-width='1.6' stroke-dasharray='5 4'/>")
    k = 0
    for t, hm, frm, to, txt in [m for m in msgs if now - m[0] < 14][-10:]:
        for tg in ([x for x in names if x != frm] if to == "all" else [to]):
            if frm in pos and tg in pos:
                b = (k % 8) * 0.25; k += 1
                g.append(f"<circle r='6' fill='#ffd166' opacity='0'><animateMotion dur='2.2s' begin='{b:.2f}s' repeatCount='1' fill='freeze' path='{curve(frm, tg)}'/><animate attributeName='opacity' values='0;1;1;0' dur='2.2s' begin='{b:.2f}s' repeatCount='1' fill='freeze'/></circle>")
    INFO = {}; cnt = {}
    for t, hm, frm, to, txt in [m for m in msgs if now - m[0] < 900]:
        cnt[frm] = cnt.get(frm, 0) + 1
        if to != "all": cnt[to] = cnt.get(to, 0) + 1
    def box(key, title, state, sub, w=200, h=50, flash=False):
        x, y = pos[key]; c = COL[state]
        fl = f"<rect x='{x-w/2-4:.0f}' y='{y-h/2-4:.0f}' width='{w+8}' height='{h+8}' rx='14' fill='none' stroke='#35d07f' stroke-width='3'><animate attributeName='opacity' values='1;0' dur='2.5s' repeatCount='1' fill='freeze'/></rect><text x='{x+w/2-8:.0f}' y='{y-h/2-6:.0f}' text-anchor='end' style='fill:#35d07f;font-size:11px;font-weight:700'>woken</text>" if flash else ""
        b = f"<g><circle cx='{x+w/2-4:.0f}' cy='{y-h/2+2:.0f}' r='10' fill='#ffd166'/><text x='{x+w/2-4:.0f}' y='{y-h/2+6:.0f}' text-anchor='middle' style='font-size:10.5px;font-weight:700;fill:#0e1a20'>{cnt[key]}</text></g>" if cnt.get(key) else ""
        return (f"<g class='node' data-n='{E(key)}'>{fl}<rect x='{x-w/2:.0f}' y='{y-h/2:.0f}' width='{w}' height='{h}' rx='11' fill='#16242b' stroke='{c}' stroke-width='2' {'stroke-dasharray=\"4 3\"' if state == 'idle' else ''}/>"
                f"<circle cx='{x-w/2+15:.0f}' cy='{y-8:.0f}' r='5' fill='{c}'/><text x='{x-w/2+27:.0f}' y='{y-3:.0f}' class='t'>{E(title)}</text><text x='{x-w/2+13:.0f}' y='{y+16:.0f}' class='s'>{E(sub[:30])}</text>{b}</g>")
    g.append(box("main", "Main session", "hub", "orchestrates, approves pushes"))
    INFO["main"] = {"title": "Main session", "state": "orchestrates; only it pushes, after the chief presents", "acts": [l[:170] for l in ledger if " main" in l[:12]][-5:], "msgs": [f"{hm}  {frm} -> {to}:  {txt}" for t, hm, frm, to, txt in msgs if "main" in (frm, to)][-8:], "slice": ""}
    for a in agents:
        nm = a["name"]; title = {"chief": "Chief of staff", "manager": "Manager"}.get(a["role"], a["role"].capitalize() + " " + nm)
        sub = re.sub(r"^\S+\s+\S+\s+\S+\s+", "", a["slice"]) if a["slice"] else WORD[a["state"]]
        g.append(box(nm, title, a["state"], sub, flash=(now - woke.get(nm, 0) < 25)))
        INFO[nm] = {"title": title, "state": WORD[a["state"]] + (f" · launched by {a['by']} at {a['at']}" if a["by"] else ""), "ago": int((now - a["mt"]) / 60) if a["mt"] else None, "slice": a["slice"], "acts": a["acts"],
                    "msgs": [f"{hm}  {frm} -> {to}:  {txt}" for t, hm, frm, to, txt in msgs if nm in (frm, to) or to == "all"][-8:]}
    g.append(box("queue", "The queue", "live" if prog else "hub", f"{len(prog)} in work · {len(ready)} ready · {len(cl)} built", 210, 56))
    g.append(box("product", "The product", "live" if unpushed else "hub", f"{ncom} commits · {len(unpushed)} awaiting approval", 210, 56))
    g.append(f"<text x='520' y='275' text-anchor='middle' class='s'>build → verify → commit</text><text x='520' y='292' text-anchor='middle' class='s'>chief presents → main approves → push</text>")
    INFO["queue"] = {"title": "The queue", "state": f"{len(prog)} in work, {len(ready)} ready, {len(cl)} built since start", "acts": [l[12:160] for l in prog] + ["next: " + l[12:150] for l in ready[:6]], "msgs": [], "slice": "workers pull the oldest slice of the highest priority whose files nobody holds"}
    INFO["product"] = {"title": "The product", "state": f"{ncom} commits since start; {len(unpushed)} verified and waiting for the chief to present and main to approve", "acts": (["awaiting approval: " + x for x in unpushed[:6]] + commits[:6]), "msgs": [v[:170] for v in verd[-6:]], "slice": ""}
    g.append("</svg>"); flow = "".join(g)
    hist.append({"t": now, "ready": len(ready), "work": len(prog), "closed": len(cl), "com": ncom, "u": five, "msg": len(msgs), "agents": len(agents), "live": sum(1 for a in agents if a["state"] == "live")})
    json.dump({"hist": hist, "state": state_now, "woke": {k: v for k, v in woke.items() if now - v < 600}}, open(RUN + "/board_history.json", "w"))
    def spark(key, c, w=260, h=76):
        v = [x.get(key, 0) for x in hist]; t = [x["t"] for x in hist]
        if len(v) < 2: return "<small>collecting…</small>"
        mx = max(max(v), 1); t0, t1 = t[0], max(t[-1], t[0] + 1); pts = [(8 + (w - 16) * (a - t0) / (t1 - t0), h - 18 - (h - 34) * b / mx) for a, b in zip(t, v)]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        return (f"<svg viewBox='0 0 {w} {h}'><polygon points='8,{h-18} {line} {pts[-1][0]:.1f},{h-18}' fill='{c}' opacity='0.18'/><polyline points='{line}' fill='none' stroke='{c}' stroke-width='2.2'/>"
                f"<text x='8' y='{h-4}' class='s'>{time.strftime('%H:%M', time.localtime(t0))}</text><text x='{w-8}' y='{h-4}' class='s' text-anchor='end'>now</text><text x='{w-8}' y='14' class='s' text-anchor='end'>{v[-1]}</text></svg>")
    C = 2 * math.pi * 34
    ring = lambda p, c: f"<svg viewBox='0 0 90 90' width='84'><circle cx='45' cy='45' r='34' fill='none' stroke='#22343c' stroke-width='9'/><circle cx='45' cy='45' r='34' fill='none' stroke='{c}' stroke-width='9' stroke-linecap='round' stroke-dasharray='{C*min(p,100)/100:.0f} {C:.0f}' transform='rotate(-90 45 45)'/><text x='45' y='51' text-anchor='middle' class='big2'>{p:.0f}%</text></svg>"
    pre = lambda ls: "<pre>" + E("\n".join(x[:185] for x in ls) or "none yet") + "</pre>"
    acc = sorted(glob.glob(RUN + "/acceptance/*/scoreboard.md"), key=os.path.getmtime)
    feed = [f"{hm}  {frm} -> {to}:  {txt}" for t, hm, frm, to, txt in msgs[-12:]]
    live = sum(1 for a in agents if a["state"] == "live")
    page = f"""<!doctype html><meta charset='utf-8'><meta http-equiv='refresh' content='10'><title>{E(CFG['title'])} board</title>
<style>body{{font:15px/1.4 system-ui,sans-serif;margin:0;background:#0e1a20;color:#dfe8ea}}.wrap{{max-width:1280px;margin:0 auto;padding:22px}}
h1{{font-size:24px;margin:0}}h2{{font-size:13px;margin:22px 0 8px;color:#7fb3c2;text-transform:uppercase;letter-spacing:1.2px}}
small,.s{{color:#8aa0a8;font-size:12px;fill:#8aa0a8}}.t{{fill:#e9f1f2;font-size:14px;font-weight:600}}.gl{{fill:#5f7a84;font-size:10.5px;letter-spacing:1.4px;font-weight:700}}.big2{{fill:#fff;font-size:17px;font-weight:700}}
.flow{{width:100%;background:#0c171c;border:1px solid #22343c;border-radius:14px}}.row{{display:flex;gap:14px;flex-wrap:wrap}}.card{{background:#13232a;border:1px solid #22343c;border-radius:12px;padding:12px 14px;flex:1;min-width:200px}}
.k{{background:#13232a;border:1px solid #22343c;border-radius:12px;padding:10px 16px}}.k b{{font-size:22px;color:#fff}}
.node{{cursor:pointer}}.node:hover rect{{fill:#1c313a}}.node.sel rect{{stroke-width:4}}#panel ul{{margin:6px 0 0 18px;padding:0;font-size:12.5px;color:#c9d6d9}}#panel li{{margin-bottom:3px}}#panel p{{margin:8px 0}}
pre{{background:#13232a;border:1px solid #22343c;border-radius:10px;padding:10px;white-space:pre-wrap;font-size:12.5px;margin:0;color:#c9d6d9}}details{{margin-top:10px}}summary{{cursor:pointer;color:#7fb3c2}}</style>
<div class='wrap'><div class='row' style='align-items:center'><div style='flex:3'><h1>{E(CFG['title'])}</h1><small>one tree under the main session, talking as a mesh · drawn {time.strftime('%H:%M:%S')} by a plain script, every 10 seconds · green: working · amber: quiet a few minutes · grey dashed: idle until a message wakes it · yellow links have carried messages in the last half hour · a dot travels once when a message is sent · click a box for detail</small></div>
<div style='text-align:center'>{ring(five,'#35d07f' if five<70 else '#f0b23a' if five<90 else '#e2574c')}<br><small>5-hour window<br>resets {rs}</small></div><div style='text-align:center'>{ring(seven,'#7fb3c2' if seven<80 else '#e2574c')}<br><small>week<br>weekly usage</small></div></div>
<h2>Now</h2><div class='row'><div class='k'><b>{len(agents)}</b> agents</div><div class='k'><b>{live}</b> working</div><div class='k'><b>{len(agents)-live}</b> idle or quiet</div><div class='k'><b>{len(prog)}</b> slices in work</div><div class='k'><b>{len(ready)}</b> ready</div><div class='k'><b>{len(verd)}</b> verdicts</div><div class='k'><b>{len(unpushed)}</b> commits awaiting approval</div></div>
<h2>The swarm, live</h2>{flow}
<div id='panel' class='card' style='margin-top:12px'><small>Click any box to see what that agent is doing.</small></div>
<script>const INFO={json.dumps(INFO)};const esc=x=>String(x).replace(/</g,'&lt;');
function show(k){{const d=INFO[k];if(!d)return;const li=a=>(a&&a.length?'<ul>'+a.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'<small>nothing yet</small>');
document.getElementById('panel').innerHTML='<b style="font-size:17px">'+esc(d.title||k)+'</b> &nbsp; <small>'+esc(d.state||'')+(d.ago!=null?' · last action '+(d.ago<1?'just now':d.ago+' min ago'):'')+'</small>'+(d.slice?'<p><b>On:</b> '+esc(d.slice)+'</p>':'')+'<div class="row"><div style="flex:1"><small>RECENT ACTIONS (newest last)</small>'+li(d.acts)+'</div><div style="flex:1"><small>MESSAGES TO AND FROM</small>'+li(d.msgs)+'</div></div>';
try{{localStorage.setItem('sel',k)}}catch(e){{}};document.querySelectorAll('.node').forEach(n=>n.classList.toggle('sel',n.dataset.n===k));}}
document.querySelectorAll('.node').forEach(n=>n.addEventListener('click',()=>show(n.dataset.n)));try{{const k=localStorage.getItem('sel');if(k&&INFO[k])show(k)}}catch(e){{}}</script>
<h2>Messages (newest last)</h2>{pre(feed)}
<h2>Since the swarm started</h2><div class='row'><div class='card'><small>agents working</small>{spark('live','#35d07f')}</div><div class='card'><small>slices built</small>{spark('closed','#5b7f8c')}</div><div class='card'><small>commits</small>{spark('com','#7fb3c2')}</div><div class='card'><small>messages sent</small>{spark('msg','#ffd166')}</div><div class='card'><small>usage, % of window</small>{spark('u','#f0b23a')}</div></div>
<h2>Acceptance scoreboard (run/acceptance/*/scoreboard.md, if you keep one)</h2>{pre([open(acc[-1]).read()[:3500]] if acc else ["none yet"])}
<details><summary>In work ({len(prog)}) and next in the queue</summary>{pre(prog + ready[:8])}</details><details><summary>Built since start ({len(cl)})</summary>{pre([i['id'] + '  ' + (i.get('closed_at') or '')[11:16] + '  ' + i['title'] for i in cl[:24]])}</details>
<details><summary>Verifier verdicts ({len(verd)})</summary>{pre(verd[-14:])}</details><details><summary>Commits since start ({ncom})</summary>{pre(commits)}</details><details><summary>Ledger, newest last</summary>{pre(ledger)}</details></div>"""
    open(OUT + ".tmp", "w").write(page); os.replace(OUT + ".tmp", OUT)
if __name__ == "__main__":
    loop = int(sys.argv[sys.argv.index("--loop") + 1]) if "--loop" in sys.argv else 0
    until = sys.argv[sys.argv.index("--until") + 1] if "--until" in sys.argv else None
    while True:
        try: build()
        except Exception as e: sys.stderr.write(f"board: {e!r}\n")
        if not loop or (until and time.strftime("%Y%m%d%H%M") >= until): break
        time.sleep(loop)
