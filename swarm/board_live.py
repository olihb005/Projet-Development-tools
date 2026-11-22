#!/usr/bin/env python3
"""Live swarm board: a small local server, no model. The page never reloads: messages are pushed the moment they are written,
who is working is checked every two seconds, the rest every eight. It reads the queue snapshot, never the tracker itself.
usage: board_live.py [--port 8899] [--until YYYYmmddHHMM]"""
import csv, glob, io, json, os, re, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
RUN = os.environ["SWARM_RUN"]   # the run folder: queue.json, messages.log, roster.txt, verify.log
WT = os.environ.get("SWARM_REPO", os.getcwd())   # the git checkout the agents work in
Q = os.environ.get("SWARM_Q", os.path.join(os.path.dirname(os.path.abspath(__file__)), "q.sh"))
SUB = os.environ.get("SWARM_SUBAGENTS", "")   # ~/.claude/projects/<project>/<session id>/subagents
SINCE = os.environ.get("SWARM_SINCE", time.strftime("%Y-%m-%d 00:00")); TITLE = os.environ.get("SWARM_TITLE", "Swarm")
ALLOW = (RUN,)
S = {"slow": {}, "ver": 0}; HIST = []
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
def roster():
    out = []
    try:
        for ln in open(RUN + "/roster.txt"):
            f = ln.strip().split("|")
            if len(f) >= 3: out.append({"name": f[0], "id": f[1], "role": f[2], "by": f[3] if len(f) > 3 else "", "at": f[4] if len(f) > 4 else ""})
    except Exception: pass
    return out
def pulse():
    now = time.time(); out = {}
    for r in roster():
        p = f"{SUB}/agent-{r['id']}.jsonl"; mt = os.path.getmtime(p) if os.path.isfile(p) else 0
        m = (now - mt) / 60 if mt else 999; out[r["name"]] = {"state": "live" if m < 1.5 else "slow" if m < 5 else "idle", "ago": int(m) if mt else None}
    return out
def messages(since_line=0):
    out = []
    try:
        for i, ln in enumerate(open(RUN + "/messages.log")):
            if i < since_line: continue
            f = ln.rstrip("\n").split("|", 4)
            if len(f) == 5: out.append({"i": i, "t": float(f[0]), "hm": f[1], "from": f[2], "to": f[3], "text": f[4].replace("[auto] ", ""), "auto": f[4].startswith("[auto]")})
    except Exception: pass
    return out
def tagline(title):
    """A three to five word, plain label for a slice: drop the code at the front, keep the words before the first colon or bracket."""
    t = re.sub(r"^\s*[A-Z]{1,3}\d*[a-z]?(-\d+)?\s+", "", title or ""); t = re.split(r"[:(;]| - ", t)[0].strip()
    w = t.split(); return " ".join(w[:5]) + ("…" if len(w) > 5 else "")
def _fmap():
    try: return json.load(open(RUN + "/features.json"))
    except Exception: return {}
def feat(title):
    """The feature a slice belongs to: a code with a number at the front of its title ("M2 ...", "U8 ..."), or a keyword from
    features.json. Codes that share a label there are one feature."""
    names = _fmap(); code = ""
    m = re.match(r"\s*([A-Z]{1,3})\d+[a-z]?(-\d+)?\s", title or "")
    if m: code = m.group(1)
    else:
        low = (title or "").lower()
        code = next((c for word, c in (names.get("_keywords") or {}).items() if word in low), "")
    label = names.get(code)
    return next((k for k, v in names.items() if v == label), code) if label else code
def origin(desc):
    m = re.search(r"^from:\s*(\S+)", desc or "", re.M); return m.group(1) if m else ""
def features(titles):
    names = _fmap(); return {f: names.get(f, f) for f in sorted({feat(t) for t in titles} - {""})}
def tags():
    try: return json.load(open(RUN + "/taglines.json"))
    except Exception: return {}
def scoreboard():
    acc = sorted(glob.glob(RUN + "/acceptance/*/scoreboard.csv"), key=os.path.getmtime); rows = []
    if not acc: return {"when": "", "rows": []}
    try:
        for r in csv.DictReader(open(acc[-1])):
            def j(x):
                try: return json.loads(x) if x else {}
                except Exception: return {}
            e, x = j(r.get("edits")), j(r.get("export")); num = lambda v: int(float(v)) if str(v).replace(".", "").isdigit() else None
            rows.append({"sheet": r.get("sheet"), "file": (r.get("file") or "")[:40], "state": r.get("state"), "homes": num(r.get("homes")), "printed": num(r.get("printed")),
                         "gardens": num(r.get("gardens_linked")), "bays": num(r.get("bays_linked")), "seconds": float(r["seconds"]) if (r.get("seconds") or "").replace(".", "").isdigit() else None,
                         "made": e.get("made"), "failed": e.get("failed"), "edits": (e.get("made") or 0) + (e.get("failed") or 0) + (e.get("not_available") or 0), "export": bool(x.get("file")) if x else None, "said": (r.get("said") or "")[:160]})
    except Exception: pass
    return {"when": os.path.basename(os.path.dirname(acc[-1])).replace("_", " "), "rows": rows}
def slow_loop():
    while True:
        try:
            try: u = json.load(open(os.path.expanduser("~/.claude/usage_meter.json")))
            except Exception: u = {}
            if S["ver"] and int(time.time()) % 40 < 9: sh(Q + " snapshot", 100)   # never on the first pass: the page must fill at once
            try: snap = json.load(open(RUN + "/queue.json"))
            except Exception: snap = {"in_progress": [], "open": [], "closed": []}
            key = lambda i: (i.get("priority") if i.get("priority") is not None else 9, i.get("created_at") or "", i["id"])
            mk = lambda i: {"id": i["id"], "p": i.get("priority"), "who": i.get("assignee") or "", "title": (i.get("title") or "")[:110], "tag": tagline(i.get("title")), "feat": feat(i.get("title")), "origin": origin(i.get("description"))}
            prog = [mk(i) for i in sorted(snap["in_progress"], key=key)]
            ready = [mk(i) for i in sorted(snap["open"], key=key) if "Board is live" not in (i.get("title") or "")]
            cl = sorted([i for i in snap["closed"] if (i.get("closed_at") or "") >= SINCE.replace(" ", "T") and not (i.get("title") or "").startswith(("ZZ", "TEST"))], key=lambda i: i.get("closed_at") or "", reverse=True)
            ver = open(RUN + "/verify.log").read().splitlines() if os.path.isfile(RUN + "/verify.log") else []
            verd = []
            for v in ver:
                m = re.match(r"(\S+) (v-\d+) verdict (\d\d:\d\d) (holds|partly|does not hold)\W*(.*)", v)
                if m and m.group(3) >= SINCE[11:]: verd.append({"id": m.group(1), "by": m.group(2), "hm": m.group(3), "v": m.group(4), "text": m.group(5)[:200]})
            seen = {v.split()[0] for v in ver if v.strip()}
            ag = []; tg = tags(); titles = {i["id"]: (i.get("title") or "") for k in ("in_progress", "open", "closed") for i in snap[k]}
            checking = {}
            for v in ver:
                f = v.split()
                if len(f) > 2 and f[2] == "claimed": checking[f[1]] = f[0]
                elif len(f) > 2 and f[2] == "verdict" and checking.get(f[1]) == f[0]: checking.pop(f[1], None)
            owner = {i["id"]: (i.get("assignee") or "") for k in ("in_progress", "open", "closed") for i in snap[k]}
            nowhm = time.strftime("%H:%M"); mins = lambda hm: int(hm[:2]) * 60 + int(hm[3:5])
            passes = sorted({(v["by"], owner.get(v["id"], "")) for v in verd if v["v"] == "holds" and 0 <= mins(nowhm) - mins(v["hm"]) <= 12})
            for r in roster():
                sl = next((p for p in prog if p["who"] == r["name"]), None); own = tg.get(r["name"]) or {}
                tag = own.get("text") if own and time.time() - own.get("t", 0) < 1500 else (tagline(sl["title"]) if sl else ("checking: " + tagline(titles.get(checking[r["name"]], "")) if r["name"] in checking else ""))
                ag.append(dict(r, slice=(sl["id"] + "  " + sl["title"]) if sl else "", tag=tag, acts=actions(f"{SUB}/agent-{r['id']}.jsonl")))
            pu0 = pulse(); nmsg = sum(1 for _ in open(RUN + "/messages.log")) if os.path.isfile(RUN + "/messages.log") else 0
            HIST.append({"t": time.time(), "live": sum(1 for p in pu0.values() if p["state"] == "live"), "work": len(prog), "ready": len(ready), "built": len(cl), "u": u.get("five_hour") or 0, "w": u.get("seven_day") or 0, "holds": sum(1 for v in verd if v["v"] == "holds")}); del HIST[:-900]
            deliv = []
            try:
                for ln in open(RUN + "/deliverables.jsonl"):
                    try: deliv.append(json.loads(ln))
                    except Exception: pass
            except Exception: pass
            commits = [dict(zip(("hm", "h", "s"), l.split("\t"))) for l in sh(f"git -C {WT} log -40 --format='%cd%x09%h%x09%s' --date=format:%H:%M --since='{SINCE}'").splitlines() if l.count("\t") == 2]
            unp = set(sh(f"git -C {WT} log @{{upstream}}..HEAD --format=%h").split())
            for c in commits: c["wait"] = c["h"] in unp
            for v in verd: v["title"] = titles.get(v["id"], ""); v["tag"] = tagline(v["title"]); v["feat"] = feat(v["title"])
            rs = u.get("five_hour_resets_at")
            S["slow"] = {"title": TITLE, "since": SINCE[11:16], "usage": {"five": u.get("five_hour") or 0, "seven": u.get("seven_day") or 0, "reset": time.strftime("%H:%M", time.localtime(rs)) if isinstance(rs, (int, float)) else "?"},
                         "agents": ag, "prog": prog, "ready": ready[:80], "nready": len(ready), "built": [{"id": i["id"], "hm": (i.get("closed_at") or "")[11:16], "title": (i.get("title") or "")[:100], "who": i.get("assignee") or ""} for i in cl[:14]], "nbuilt": len(cl),
                         "verd": verd[-60:][::-1], "nverd": len(verd), "holds": sum(1 for v in verd if v["v"] == "holds"), "awaiting": len([i for i in cl if i["id"] not in seen]),
                         "commits": commits, "ncom": len(sh(f"git -C {WT} log --since='{SINCE}' --format=%h").split()), "nunp": len(unp),
                         "ledger": (open(RUN + "/ledger.md").read().splitlines()[-8:] if os.path.isfile(RUN + "/ledger.md") else []),
                         "features": features(titles.values()), "score": scoreboard(), "hist": HIST[-360:], "checks": [{"v": v, "id": i, "w": owner.get(i, "")} for v, i in checking.items()], "passes": [{"v": a, "w": b} for a, b in passes], "deliv": deliv[-12:][::-1]}
            S["ver"] += 1
        except Exception as e: sys.stderr.write(f"slow: {e!r}\n")
        time.sleep(3)
PAGE = r"""<!doctype html><meta charset='utf-8'><title>__TITLE__</title>
<style>
:root{--bg:#0d181d;--card:#13232a;--line:#22363f;--ink:#e6eef0;--mute:#8aa0a8;--teal:#7fb3c2;--green:#35d07f;--amber:#f0b23a;--red:#e2574c;--yel:#ffd166;--blue:#7fd3ff}
*{box-sizing:border-box}body{font:14.5px/1.45 system-ui,sans-serif;margin:0;background:radial-gradient(1200px 700px at 15% 0%,#14303a 0%,var(--bg) 55%) fixed;color:var(--ink)}
.wrap{max-width:1360px;margin:0 auto;padding:22px 26px 60px}header{display:flex;align-items:center;gap:22px;margin-bottom:14px}h1{font-size:26px;margin:0;letter-spacing:-.2px}
h2{font-size:12px;margin:0 0 10px;color:var(--teal);text-transform:uppercase;letter-spacing:1.6px;font-weight:700}h2 small{font-weight:400;letter-spacing:0;text-transform:none}
small,.s{color:var(--mute);font-size:12px;fill:var(--mute)}.t{fill:#e9f1f2;font-size:14px;font-weight:600}.gl{fill:#5f7a84;font-size:10.5px;letter-spacing:1.4px;font-weight:700}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 18px}.grid{display:grid;gap:16px;margin-top:16px}.g2{grid-template-columns:1.55fr 1fr}.g3{grid-template-columns:1fr 1fr 1fr}.g6{grid-template-columns:repeat(6,1fr)}
@media(max-width:1100px){.g2,.g3{grid-template-columns:1fr}.g6{grid-template-columns:repeat(3,1fr)}}
.kpis{display:grid;grid-template-columns:repeat(8,1fr);gap:10px}.k{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:10px 14px}.k b{display:block;font-size:24px;color:#fff;line-height:1.1}.k span{color:var(--mute);font-size:12px}
.flow{width:100%;display:block;background:#0c171c;border:1px solid var(--line);border-radius:26px;margin-top:16px}
.fl{animation:flow 1.5s linear infinite}@keyframes flow{from{stroke-dashoffset:18}to{stroke-dashoffset:0}}
.node{cursor:pointer}.node:hover rect{fill:#1c313a}.node.sel rect{stroke-width:3.5}.ping{animation:ping .9s ease-out 1}@keyframes ping{0%{filter:drop-shadow(0 0 12px var(--yel))}100%{filter:none}}.woke{animation:woke 2.4s ease-out 1}@keyframes woke{0%{filter:drop-shadow(0 0 18px var(--green))}100%{filter:none}}
#panel{margin-top:12px;display:none}#panel.on{display:block}#panel ul{margin:6px 0 0 18px;padding:0;font-size:12.5px;color:#c9d6d9}#panel .cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}
#feed{height:430px;overflow:auto;display:flex;flex-direction:column;gap:6px;padding-right:4px}.m{background:#0f1d23;border:1px solid #1d3038;border-radius:12px;padding:7px 10px;font-size:13px}.m.a{background:transparent;border-color:transparent;color:var(--mute);padding:2px 10px;font-size:12px}
.m.new{animation:fl 1.8s ease-out 1}@keyframes fl{0%{box-shadow:0 0 0 2px var(--yel)}100%{box-shadow:none}}.chip{display:inline-block;border-radius:999px;padding:1px 9px;font-size:11.5px;font-weight:700;background:#213841;color:#cfe3e8;margin-right:4px}
.chip.c{background:#3a2f12;color:var(--yel)}.chip.mg{background:#10343a;color:#8fe0ee}.chip.w{background:#143524;color:#8ee8b8}.chip.v{background:#2c2440;color:#cdb6ff}.chip.mn{background:#1f3a48;color:#bfe3f0}
.hm{color:var(--mute);font-size:11.5px;margin-right:6px}.dcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}.d{background:#0f1d23;border:1px solid #1d3038;border-radius:16px;padding:14px;display:flex;flex-direction:column;gap:8px}
.d .big{font-size:30px;font-weight:800;color:#fff;line-height:1}.d .big small{font-size:14px;color:var(--mute);font-weight:500}.bar{height:8px;border-radius:99px;background:#1c2f37;overflow:hidden}.bar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--green),#3fb8d8)}
.d p{margin:0;font-size:12.5px;color:#b9c9cd;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.d img{width:100%;border-radius:10px;background:#fff;max-height:210px;object-fit:contain}.d a{color:var(--teal);font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:7px 8px;border-bottom:1px solid #1b2e36;text-align:left;vertical-align:middle}th{color:var(--mute);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.8px}
.pill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:11.5px;font-weight:700}.ok{background:#12372a;color:#7ee2ad}.pa{background:#3a3014;color:#f3c96a}.no{background:#3a1c1a;color:#f29a92}.wt{background:#1f3a48;color:#bfe3f0}
.row1{display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-bottom:1px solid #1b2e36;font-size:13px}.row1:last-child{border:0}.id{font:11.5px ui-monospace,monospace;color:var(--mute);min-width:52px}
#live{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--red);margin-right:6px}details summary{cursor:pointer;color:var(--teal);font-size:12.5px}pre{white-space:pre-wrap;font-size:12px;color:#b9c9cd;margin:8px 0 0}
</style>
<div class='wrap'><header><div style='flex:1'><h1>__TITLE__</h1><small><span id='live'></span><span id='conn'>connecting…</span> · green working · amber quiet a few minutes · grey dashed idle until a message wakes it · solid lines carry work, dotted lines are messages · click a node</small></div><div id='rings' style='display:flex;gap:18px'></div></header>
<div id='kpi' class='kpis'></div><svg id='g' viewBox='0 0 1240 600' class='flow'></svg><div id='panel' class='card'></div>
<div class='grid g2'><div class='card'><h2>Recent deliverables <small>· results the swarm has posted, newest first</small></h2><div id='deliv' class='dcards'></div></div>
<div class='card'><h2>Messages, live <small id='rate'></small></h2><div id='c_mpm'></div><div id='feed'></div></div></div>
<div class='grid g2'><div class='card'><h2>The product by itself <small id='scw'></small></h2><div id='score'></div></div><div class='card'><h2>Who is talking <small>· messages sent in the last 30 minutes</small></h2><div id='c_who'></div></div></div>
<div class='grid g6' id='charts'></div>
<div class='grid g3'><div class='card'><h2>In work and next</h2><div id='work'></div></div><div class='card'><h2>Verdicts</h2><div id='verd'></div></div><div class='card'><h2>Commits this evening</h2><div id='coms'></div></div></div>
<div class='card' style='margin-top:16px'><details><summary>Ledger, newest last</summary><pre id='ledger'></pre></details></div></div>
<script>
const esc=x=>String(x==null?'':x).replace(/&/g,'&amp;').replace(/</g,'&lt;');let ST={},PU={},POS={},MSG=[],sel=localStorage.getItem('sel'),prevState={};const $=id=>document.getElementById(id);
const COL={live:'#35d07f',slow:'#f0b23a',idle:'#6c8089',hub:'#7fb3c2'},WORD={live:'working now',slow:'quiet for a few minutes',idle:'idle: a message wakes it',hub:''};
const chip=n=>`<span class='chip ${n=='chief'?'c':n=='manager'?'mg':n=='main'?'mn':/^w-/.test(n)||n=='workers'?'w':/^v-/.test(n)||n=='verifiers'?'v':''}'>${esc(n)}</span>`;
function layout(){const a=ST.agents||[];POS={queue:[115,330],product:[1125,330],main:[620,46]};const col=(items,x,y0,y1)=>items.forEach((n,i)=>POS[n.name]=[x,y0+(y1-y0)*(i+.5)/Math.max(items.length,1)]);
 col(a.filter(x=>x.role=='chief'),380,150,250);col(a.filter(x=>x.role=='manager'),380,400,520);const w=a.filter(x=>x.role=='worker'),v=a.filter(x=>x.role=='verifier');const clus=(items,cx,cy,dx,y0,y1)=>{const n=items.length,st=(y1-y0)/Math.max(n,1);items.forEach((it,i)=>{POS[it.name]=[cx+(n>1?(i%2?dx:-dx):0),y0+st*(i+.5)];});};clus(w,640,340,22,128,560);clus(v,912,340,14,190,490);return {w,v};}
function curve(a,b){const [x1,y1]=POS[a],[x2,y2]=POS[b],dx=x2-x1,dy=y2-y1;if(Math.abs(dx)<60){const k=70*(dy>0?1:-1);return [x1,y1,x1-k,y1+dy*.25,x2-k,y2-dy*.25,x2,y2];}if(a=='main'||b=='main')return [x1,y1,x1,y1+dy*.6,x2,y2-dy*.6,x2,y2];return [x1,y1,x1+dx*.5,y1,x2-dx*.5,y2,x2,y2];}
const pd=p=>`M${p[0]},${p[1]} C${p[2]},${p[3]} ${p[4]},${p[5]} ${p[6]},${p[7]}`;
function targets(m){const a=(ST.agents||[]).map(x=>x.name);if(m.to=='all')return ['main',...a].filter(n=>n!=m.from);if(m.to=='verifiers')return a.filter(n=>n.startsWith('v-'));if(m.to=='workers')return a.filter(n=>n.startsWith('w-'));return [m.to];}
function box(key,title,state,sub,w,h){const [x,y]=POS[key],c=COL[state];return `<g class='node${sel==key?' sel':''}' data-n='${key}' id='n_${key}' style='filter:drop-shadow(0 0 ${state=='live'?9:3}px ${c}55)'><rect x='${x-w/2}' y='${y-h/2}' width='${w}' height='${h}' rx='${h/2}' fill='url(#ng)' stroke='${c}' stroke-width='1.8' ${state=='idle'?"stroke-dasharray='4 4' stroke-opacity='.7'":''}/><circle cx='${x-w/2+20}' cy='${y}' r='6' fill='${c}'/><text x='${x-w/2+34}' y='${y-3}' class='t'>${esc(title)}</text><text x='${x-w/2+34}' y='${y+14}' class='s'>${esc((sub||'').slice(0,Math.floor((w-44)/6.2)))}</text></g>`;}
function draw(){if(!ST.agents)return;const {w,v}=layout(),H=600,g=[`<defs><linearGradient id='ng' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#1d323b'/><stop offset='1' stop-color='#12222a'/></linearGradient><linearGradient id='dg' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#35d07f' stop-opacity='.95'/><stop offset='1' stop-color='#3fb8d8' stop-opacity='.95'/></linearGradient><radialGradient id='bg1' cx='.2' cy='.3' r='.7'><stop offset='0' stop-color='#17323c'/><stop offset='1' stop-color='#0c171c' stop-opacity='0'/></radialGradient></defs><rect width='1240' height='${H}' fill='url(#bg1)'/>`];
 const lab=(t,x,y)=>g.push(`<text x='${x}' y='${y}' text-anchor='middle' class='gl'>${t}</text>`);lab('DIRECTION',380,118);lab('WORKERS · '+w.length,640,100);lab('VERIFIERS · '+v.length,912,160);
 const seg=(d,wd,label,lx,ly)=>g.push(`<path d='${d}' fill='none' stroke='url(#dg)' stroke-width='${wd}' stroke-linecap='round' stroke-opacity='.85'/><path class='fl' d='${d}' fill='none' stroke='#f2fff8' stroke-opacity='.75' stroke-width='${Math.max(1.5,wd*.4)}' stroke-linecap='round' stroke-dasharray='1 17'/>`+(label?`<text x='${lx}' y='${ly}' text-anchor='middle' class='s' style='fill:#9fe3c3'>${label}</text>`:''));
 const edge=(a,b,wd,label)=>{if(!POS[a]||!POS[b])return;const p=curve(a,b),mx=(p[0]+3*p[2]+3*p[4]+p[6])/8,my=(p[1]+3*p[3]+3*p[5]+p[7])/8;seg(pd(p),wd,label,mx,my-8);};
 const ch=(ST.agents||[]).find(x=>x.role=='chief'),mg=(ST.agents||[]).find(x=>x.role=='manager'),nw=(ST.prog||[]).length,M=POS.main,names=new Set((ST.agents||[]).map(x=>x.name));
 // the graph, node to node: main directs the queue and the chief; the queue feeds the chief; the chief the manager; the manager each worker that holds a slice;
 // a worker's built slice goes to the verifier checking it; a verifier that has passed work feeds the product; the product goes up to main for approval and its review returns to the queue
 seg(`M${M[0]-100},${M[1]} C300,${M[1]} 115,140 115,${POS.queue[1]-32}`,2.4,'direction and new slices',250,40);
 if(ch)edge('main','chief',2.4);
 seg(`M${POS.product[0]},${POS.product[1]-32} C${POS.product[0]},140 940,${M[1]} ${M[0]+100},${M[1]}`,Math.min(2.4+(ST.nunp||0)*1.1,9),(ST.nunp||0)+' checked changes to approve',990,40);
 if(ch)edge('queue','chief',Math.min(3+ST.nready*.1,8),ST.nready+' ready');
 if(ch&&mg)edge('chief','manager',3.2);
 (ST.prog||[]).forEach(p=>{if(mg&&names.has(p.who))edge('manager',p.who,2.6);});
 (ST.checks||[]).forEach(c=>{if(names.has(c.w)&&names.has(c.v))edge(c.w,c.v,2.8,'checking');});
 (ST.passes||[]).forEach(c=>{if(names.has(c.v))edge(c.v,'product',2.8);});
 if((ST.awaiting||0)>0)g.push(`<text x='780' y='588' text-anchor='middle' class='s' style='fill:#9fe3c3'>${ST.awaiting} built, waiting for a verifier</text>`);
 seg(`M1125,${POS.product[1]+32} C1125,596 900,596 620,596 C340,596 115,596 115,${POS.queue[1]+32}`,2.8,'review, faults and what is left go back into the queue',430,588);
 const now=Date.now()/1000,pair={};MSG.filter(m=>now-m.t<1800&&m.to!='all').forEach(m=>targets(m).forEach(t=>{if(POS[m.from]&&POS[t]){const k=[m.from,t].sort().join('|');pair[k]=(pair[k]||0)+1;}}));
 Object.entries(pair).forEach(([k,c])=>{const [a,b]=k.split('|');g.push(`<path d='${pd(curve(a,b))}' fill='none' stroke='#ffd166' stroke-opacity='${Math.min(.28+c*.04,.8)}' stroke-width='${Math.min(1.4+c*.12,3.2)}' stroke-dasharray='1.5 7' stroke-linecap='round'/>`);});
 g.push(box('main','Main session','hub','directs, approves, pushes',200,48));
 (ST.agents||[]).forEach(a=>{const st=(PU[a.name]||{}).state||'idle';const title={chief:'Chief of staff',manager:'Manager'}[a.role]||(a.role[0].toUpperCase()+a.role.slice(1)+' '+a.name);const sub=a.slice?a.slice.replace(/^\S+\s+/,''):WORD[st];const small=a.role=='worker'||a.role=='verifier';g.push(box(a.name,small?a.name:title,st,a.tag||(st=='idle'?'idle: a message wakes it':st=='slow'?'quiet a few minutes':(small?'between slices':'working now')),small?222:210,small?46:52));});
 g.push(box('queue','The queue',nw?'live':'hub',`${nw} in work · ${ST.nready} ready`,190,62));g.push(box('product','The product',(ST.nunp||0)?'live':'hub',`${ST.ncom} commits · ${ST.nunp||0} to approve`,190,62));
 g.push(`<text x='115' y='${POS.queue[1]+56}' text-anchor='middle' class='s'>slices to build</text><text x='1125' y='${POS.product[1]+56}' text-anchor='middle' class='s'>verified and committed</text><g id='fly'></g>`);
 $('g').innerHTML=g.join('');document.querySelectorAll('.node').forEach(n=>n.onclick=()=>show(n.dataset.n));
 Object.entries(PU).forEach(([n,p])=>{if(prevState[n]&&prevState[n]!='live'&&p.state=='live'){const e=$('n_'+n);e&&e.classList.add('woke');}prevState[n]=p.state;});
 const live=Object.values(PU).filter(p=>p.state=='live').length,na=(ST.agents||[]).length,k=(n,t)=>`<div class='k'><b>${n}</b><span>${t}</span></div>`;
 $('kpi').innerHTML=k(na,'agents')+k(live,'working now')+k(na-live,'idle or quiet')+k(nw,'slices in work')+k(ST.nready,'ready')+k(ST.nbuilt,'built this evening')+k(ST.holds+' / '+ST.nverd,'hold / verdicts')+k(ST.nunp||0,'commits to approve');
 const C=2*Math.PI*30,ring=(p,c,l)=>`<div style='text-align:center'><svg viewBox='0 0 80 80' width='72'><circle cx='40' cy='40' r='30' fill='none' stroke='#22343c' stroke-width='8'/><circle cx='40' cy='40' r='30' fill='none' stroke='${c}' stroke-width='8' stroke-linecap='round' stroke-dasharray='${C*Math.min(p,100)/100} ${C}' transform='rotate(-90 40 40)'/><text x='40' y='46' text-anchor='middle' style='fill:#fff;font-size:16px;font-weight:700'>${Math.round(p)}%</text></svg><br><small>${l}</small></div>`;
 const u=ST.usage||{};$('rings').innerHTML=ring(u.five||0,(u.five||0)<70?'#35d07f':(u.five||0)<90?'#f0b23a':'#e2574c','5-hour window · resets '+u.reset)+ring(u.seven||0,(u.seven||0)<80?'#7fb3c2':'#e2574c','week · stop line 90%');
 rest();if(sel)show(sel,true);}
function rest(){const pill=v=>`<span class='pill ${v=='holds'?'ok':v=='partly'?'pa':'no'}'>${v}</span>`;
 $('work').innerHTML=(ST.prog||[]).map(p=>`<div class='row1'>${chip(p.who||'?')}<div><span class='id'>${esc(p.id)}</span> ${esc(p.title)}</div></div>`).join('')+(ST.ready||[]).slice(0,6).map(p=>`<div class='row1' style='opacity:.65'><span class='pill wt'>P${p.p}</span><div><span class='id'>${esc(p.id)}</span> ${esc(p.title)}</div></div>`).join('')||'<small>nothing yet</small>';
 $('verd').innerHTML=(ST.verd||[]).map(v=>`<div class='row1'>${pill(v.v)}<div><span class='hm'>${v.hm}</span>${chip(v.by)}<span class='id'>${esc(v.id)}</span><br><small>${esc(v.text)}</small></div></div>`).join('')||'<small>no verdicts yet</small>';
 $('coms').innerHTML=(ST.commits||[]).map(c=>`<div class='row1'><span class='pill ${c.wait?'pa':'ok'}'>${c.wait?'to approve':'pushed'}</span><div><span class='hm'>${c.hm}</span><span class='id'>${esc(c.h)}</span><br>${esc(c.s.slice(0,120))}</div></div>`).join('')||'<small>none yet</small>';
 $('ledger').textContent=(ST.ledger||[]).join('\n');
 const sc=ST.score||{rows:[]};$('scw').textContent=sc.when?'· acceptance run of '+sc.when+', no agent in it':'· no acceptance run yet';
 $('score').innerHTML=sc.rows.length?`<table><tr><th>Sheet</th><th style='width:34%'>Homes found of printed</th><th>Gardens</th><th>Bays</th><th>Edits made</th><th>Export</th><th>Seconds (goal 90)</th></tr>`+sc.rows.map(r=>{const pc=r.printed?Math.min(100,100*r.homes/r.printed):0,ok=r.state=='done';return `<tr><td><b>${esc(r.sheet)}</b><br><small>${esc(r.file)}</small></td><td>${ok?`<b style='font-size:17px'>${r.homes??'–'}</b> <small>of ${r.printed??'?'}</small><div class='bar' style='margin-top:4px'><i style='width:${pc}%;${pc<99.5?'background:linear-gradient(90deg,#f0b23a,#e2905c)':''}'></i></div>`:`<span class='pill no'>${esc(r.state)}</span><br><small>${esc(r.said)}</small>`}</td><td>${r.gardens??'–'}</td><td>${r.bays??'–'}</td><td>${r.edits?`<span class='pill ${r.failed?'pa':'ok'}'>${r.made} of ${r.edits}</span>`:'–'}</td><td>${r.export==null?'–':`<span class='pill ${r.export?'ok':'no'}'>${r.export?'written':'failed'}</span>`}</td><td>${r.seconds!=null?`${r.seconds.toFixed(0)} s<div class='bar' style='margin-top:4px'><i style='width:${Math.min(100,r.seconds/1.8)}%;${r.seconds>90?'background:#e2905c':''}'></i></div>`:'–'}</td></tr>`;}).join('')+'</table>':'<small>The acceptance run has not produced a scoreboard yet.</small>';
 $('deliv').innerHTML=(ST.deliv||[]).map(d=>{const u=d.path?'/file?p='+encodeURIComponent(d.path):'',ext=(d.path||'').split('.').pop().toLowerCase(),m=(d.title+' '+d.text).match(/(\d+)\s+of\s+(\d+)/),n=!m&&(d.title+' '+d.text).match(/(\d+(?:\.\d+)?)\s?(s|%|homes|tests|edits|commits|slices)\b/);
  return `<div class='d'><div><span class='hm'>${esc(d.hm)}</span>${chip(d.by)}</div><b>${esc(d.title)}</b>${m?`<div class='big'>${m[1]} <small>of ${m[2]}</small></div><div class='bar'><i style='width:${Math.min(100,100*m[1]/m[2])}%'></i></div>`:n?`<div class='big'>${n[1]} <small>${n[2]}</small></div>`:''}${u&&['svg','png','jpg'].includes(ext)?`<a href='${u}' target='_blank'><img src='${u}'></a>`:''}<p>${esc(d.text)}</p>${u?`<a href='${u}' target='_blank'>open ${esc(d.path.split('/').slice(-2).join('/'))}</a>`:''}</div>`;}).join('')||'<small>Nothing posted yet.</small>';
 charts();}
function line(v,t,c,h){const w=220;if(!v||v.length<2)return '<small>collecting…</small>';const mx=Math.max(...v,1),t0=t[0],t1=Math.max(t[t.length-1],t0+1),P=v.map((b,i)=>[4+(w-8)*(t[i]-t0)/(t1-t0),h-6-(h-24)*b/mx]),L=P.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ');return `<svg viewBox='0 0 ${w} ${h}' width='100%'><polygon points='4,${h-6} ${L} ${P[P.length-1][0]},${h-6}' fill='${c}' opacity='.16'/><polyline points='${L}' fill='none' stroke='${c}' stroke-width='2.2' stroke-linejoin='round'/><circle cx='${P[P.length-1][0]}' cy='${P[P.length-1][1]}' r='3.5' fill='${c}'/></svg>`;}
function charts(){const Hh=ST.hist||[],t=Hh.map(x=>x.t),card=(l,k,c,suf)=>`<div class='card' style='padding:12px 14px'><small>${l}</small><div style='font-size:22px;font-weight:800;color:#fff'>${Hh.length?Hh[Hh.length-1][k]:'–'}${suf||''}</div>${line(Hh.map(x=>x[k]),t,c,56)}</div>`;
 $('charts').innerHTML=card('Agents working','live','#35d07f')+card('Slices in work','work','#3fb8d8')+card('Slices built','built','#7fb3c2')+card('Verdicts that hold','holds','#8ee8b8')+card('5-hour window used','u','#e2905c','%')+card('Week used','w','#c98bd8','%');
 const now=Date.now()/1000,B=Array(30).fill(0),A=Array(30).fill(0);MSG.forEach(m=>{const k=29-Math.floor((now-m.t)/60);if(k>=0&&k<30)(m.auto?A:B)[k]++;});const mx=Math.max(...B.map((b,i)=>b+A[i]),1);
 $('c_mpm').innerHTML=`<svg viewBox='0 0 300 62' width='100%' style='margin-bottom:8px'>`+B.map((b,i)=>{const hb=44*b/mx,ha=44*A[i]/mx,x=3+i*9.9;return `<rect x='${x}' y='${48-ha}' width='7.6' height='${ha}' rx='2' fill='#7fd3ff'/><rect x='${x}' y='${48-ha-hb}' width='7.6' height='${hb}' rx='2' fill='#ffd166'/>`;}).join('')+`<text x='3' y='60' class='s'>30 min ago</text><text x='297' y='60' class='s' text-anchor='end'>now</text></svg>`;
 const by={};MSG.filter(m=>now-m.t<1800).forEach(m=>{by[m.from]=by[m.from]||[0,0];by[m.from][m.auto?1:0]++;});const E2=Object.entries(by).sort((a,b)=>(b[1][0]+b[1][1])-(a[1][0]+a[1][1])).slice(0,10),m2=Math.max(...E2.map(e=>e[1][0]+e[1][1]),1);
 $('c_who').innerHTML=`<svg viewBox='0 0 420 ${E2.length*24+6}' width='100%'>`+E2.map((e,i)=>{const a=260*e[1][0]/m2,b=260*e[1][1]/m2;return `<text x='70' y='${i*24+17}' text-anchor='end' style='fill:#cfe3e8;font-size:12.5px'>${esc(e[0])}</text><rect x='80' y='${i*24+6}' width='${a}' height='14' rx='7' fill='#ffd166'/><rect x='${80+a}' y='${i*24+6}' width='${b}' height='14' rx='7' fill='#7fd3ff'/><text x='${88+a+b}' y='${i*24+17}' class='s'>${e[1][0]+e[1][1]}</text>`;}).join('')+`</svg><small>yellow: written by the agent · blue: its work events</small>`;}
function show(k,quiet){sel=k;localStorage.setItem('sel',k);const a=(ST.agents||[]).find(x=>x.name==k),p=PU[k]||{},li=x=>(x&&x.length?'<ul>'+x.map(y=>'<li>'+esc(y)+'</li>').join('')+'</ul>':'<small>nothing yet</small>');
 const mm=MSG.filter(m=>m.from==k||targets(m).includes(k)).slice(-10).map(m=>`${m.hm}  ${m.from} → ${m.to}:  ${m.text}`);let title=k,state='',slice='',acts=[];
 if(a){title={chief:'Chief of staff',manager:'Manager'}[a.role]||a.role+' '+a.name;state=WORD[p.state||'idle']+(p.ago!=null?' · last action '+(p.ago<1?'just now':p.ago+' min ago'):'')+' · launched by '+a.by+' at '+a.at;slice=a.slice;acts=a.acts;}
 else if(k=='queue'){title='The queue';acts=(ST.prog||[]).map(x=>x.who+': '+x.id+' '+x.title).concat((ST.ready||[]).map(x=>'next: '+x.id+' '+x.title));}else if(k=='product'){title='The product';acts=(ST.commits||[]).map(c=>(c.wait?'to approve: ':'pushed: ')+c.h+' '+c.s);}else if(k=='main'){title='Main session';state='directs the swarm; only it pushes, after the chief presents';}
 $('panel').className='card on';$('panel').innerHTML=`<b style='font-size:17px'>${esc(title)}</b> &nbsp; <small>${esc(state)}</small>${slice?'<p style="margin:8px 0"><b>On:</b> '+esc(slice)+'</p>':''}<div class='cols'><div><small>RECENT ACTIONS (newest last)</small>${li(acts)}</div><div><small>MESSAGES TO AND FROM</small>${li(mm)}</div></div>`;
 if(!quiet)document.querySelectorAll('.node').forEach(n=>n.classList.toggle('sel',n.dataset.n===k));}
function fly(m){targets(m).forEach((t,i)=>{if(!POS[m.from]||!POS[t])return;const p=curve(m.from,t),c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('r',m.auto?4.5:6.5);c.setAttribute('fill',m.auto?'#7fd3ff':'#ffd166');c.style.filter='drop-shadow(0 0 6px '+(m.auto?'#7fd3ff':'#ffd166')+')';const f=$('fly');if(!f)return;f.appendChild(c);const t0=performance.now()+i*60,D=1000;
 (function step(now){let u=(now-t0)/D;if(u<0){requestAnimationFrame(step);return;}if(u>=1){c.remove();const e=$('n_'+t);if(e){e.classList.remove('ping');void e.getBBox();e.classList.add('ping');}return;}u=u*u*(3-2*u);const a=1-u,x=a*a*a*p[0]+3*a*a*u*p[2]+3*a*u*u*p[4]+u*u*u*p[6],y=a*a*a*p[1]+3*a*a*u*p[3]+3*a*u*u*p[5]+u*u*u*p[7];c.setAttribute('cx',x);c.setAttribute('cy',y);requestAnimationFrame(step);})(performance.now());});}
function feedAdd(m,isNew){const f=$('feed'),d=document.createElement('div');d.className='m'+(m.auto?' a':'')+(isNew?' new':'');d.innerHTML=`<span class='hm'>${m.hm}</span>${chip(m.from)}→ ${chip(m.to)}${esc(m.text)}`;f.prepend(d);while(f.children.length>160)f.lastChild.remove();}
function rate(){const now=Date.now()/1000,n=MSG.filter(m=>now-m.t<60).length,n5=MSG.filter(m=>now-m.t<300).length;$('rate').textContent=`· ${n} in the last minute · ${n5} in the last five`;if(ST.agents)charts();}
const es=new EventSource('/events');es.onopen=()=>{$('live').style.background='#35d07f';$('conn').textContent='live';};es.onerror=()=>{$('live').style.background='#e2574c';$('conn').textContent='disconnected, retrying';};
es.addEventListener('init',e=>{const d=JSON.parse(e.data);ST=d.slow;PU=d.pulse;MSG=d.msgs;$('feed').innerHTML='';MSG.slice(-90).forEach(m=>feedAdd(m,false));draw();rate();});
es.addEventListener('slow',e=>{ST=JSON.parse(e.data);draw();});es.addEventListener('pulse',e=>{PU=JSON.parse(e.data);draw();});
es.addEventListener('msg',e=>{const m=JSON.parse(e.data);MSG.push(m);feedAdd(m,true);fly(m);rate();});setInterval(rate,5000);
</script>"""
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/events"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.end_headers()
            def send(ev, data): self.wfile.write(f"event: {ev}\ndata: {json.dumps(data)}\n\n".encode()); self.wfile.flush()
            try:
                msgs = messages(); n = (msgs[-1]["i"] + 1) if msgs else 0; pu = pulse(); ver = S["ver"]; send("init", {"slow": S["slow"], "pulse": pu, "msgs": msgs[-1500:]}); k = 0
                while True:
                    time.sleep(0.4); k += 1
                    for m in messages(n): send("msg", m); n = m["i"] + 1
                    if k % 5 == 0:
                        p2 = pulse()
                        if p2 != pu: pu = p2; send("pulse", pu)
                    if S["ver"] != ver: ver = S["ver"]; send("slow", S["slow"])
                    if k % 40 == 0: self.wfile.write(b": keep\n\n"); self.wfile.flush()
            except Exception: return
        elif self.path.startswith("/file?p="):
            from urllib.parse import unquote
            fp = os.path.realpath(unquote(self.path[8:]))
            if not any(fp.startswith(os.path.realpath(a) + "/") for a in ALLOW) or not os.path.isfile(fp): self.send_response(404); self.end_headers(); return
            ct = {".svg": "image/svg+xml", ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json"}.get(os.path.splitext(fp)[1].lower(), "text/plain; charset=utf-8")
            b = open(fp, "rb").read(); self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            pf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "board_page.html"); b = (open(pf).read() if os.path.isfile(pf) else PAGE).replace("__TITLE__", TITLE).encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8899
    until = sys.argv[sys.argv.index("--until") + 1] if "--until" in sys.argv else None
    threading.Thread(target=slow_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), H); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    while not (until and time.strftime("%Y%m%d%H%M") >= until): time.sleep(20)
