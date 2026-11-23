#!/usr/bin/env python3
"""Next-gen swarm board for one swarm, drawn by a plain script (no model, standard library only). It reads only the files the kit
writes (see swarm_state.py) and is additive: board.py and board_live.py are unchanged and still work.
Skins live in board_skins.css + board_skins.json, character packs in packs/*.json (neutral by default); all are plain data files.
Skin, layout and node tab are chosen on the page and kept in the browser and the URL hash (#skin=tidepool&layout=subway&tab=strip).
usage:
  SWARM_CONFIG=<swarm.json> board_next.py [--out FILE] [--loop SECONDS] [--until YYYYmmddHHMM] [--as-of auto|EPOCH] [--no-git]
                                          [--characters neutral|nerd|none|PACK.json] [--skin K] [--layout K] [--tab K]
  SWARM_CONFIG=<swarm.json> board_next.py --serve [--port 8898]        live page on 127.0.0.1: polls every 2.5 s, never reloads
--out defaults to <board path from swarm.json>_next.html. --as-of auto judges working/idle against the last write in the run
folder instead of now (for replaying a recorded run)."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarm_state as ss

HERE = os.path.dirname(os.path.abspath(__file__))


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else default


def page(data, title):
    """One self-contained HTML file: the template with the skins and the data inlined (works from file:// and over http)."""
    rd = lambda f: open(os.path.join(HERE, f), encoding="utf-8").read()
    safe = lambda obj: json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")   # never close the script tag
    ref = f"<meta http-equiv='refresh' content='{data['refresh']}'>" if data.get("refresh") else ""
    return (rd("board_next_page.html").replace("__TITLE__", title.replace("<", "")).replace("__REFRESH__", ref)
            .replace("/*__SKINS_CSS__*/", rd("board_skins.css").replace("</", "<\\/"))
            .replace("/*__SKINS__*/null", safe(json.loads(rd("board_skins.json")))).replace("/*__DATA__*/null", safe(data)))


def resolve_as_of(spec, cfg):
    if spec in (None, "", "now"): return None, ""
    if spec == "auto":
        t = ss.auto_as_of(cfg); return t, "replayed as of " + time.strftime("%H:%M:%S", time.localtime(t))
    return float(spec), "as of " + time.strftime("%H:%M:%S", time.localtime(float(spec)))


def collect(cfgs, as_of_spec, git=True, mode="swarm", refresh=0, live=False, title=""):
    swarms, notes = [], set(); pack = ss.load_pack(arg("--characters"))
    ss.reset_fleet()
    for c in cfgs:
        t, note = resolve_as_of(as_of_spec, c)
        if note: notes.add("replayed as of each swarm's last write" if as_of_spec == "auto" and len(cfgs) > 1 else note)
        try: swarms.append(ss.read_swarm(c, t, git=git, pack=pack))
        except Exception as e: sys.stderr.write(f"board_next: skipped {c}: {e!r}\n")
    defaults = {k: arg("--" + k) for k in ("skin", "layout", "tab") if arg("--" + k)}
    return {"mode": mode, "title": title, "swarms": swarms, "usage": ss.usage(), "made": time.time(), "refresh": refresh, "live": live,
            "pack": pack.get("pack", ""), "defaults": defaults, "as_of_note": "; ".join(sorted(notes))}


def serve(make_state, title, port):
    """A small local server: / is the page, /state.json the data (rebuilt at most every 2 s). Read-only, bound to 127.0.0.1."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    cache = {"t": 0, "d": None}; lock = threading.Lock()
    def state():
        with lock:
            if time.time() - cache["t"] > 2 or cache["d"] is None: cache["d"] = make_state(); cache["t"] = time.time()
            return cache["d"]
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            if self.path.startswith("/state.json"): body, ct = json.dumps(dict(state(), live=True)).encode(), "application/json"
            elif self.path in ("/", "/index.html") or self.path.startswith(("/?", "/#")): body, ct = page(dict(state(), live=True), title).encode(), "text/html; charset=utf-8"
            else: self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    srv = ThreadingHTTPServer(("127.0.0.1", port), H); srv.daemon_threads = True
    print(f"board at http://127.0.0.1:{port}/", flush=True)
    until = arg("--until")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    while not (until and time.strftime("%Y%m%d%H%M") >= until): time.sleep(5)


def main():
    cfg = os.environ.get("SWARM_CONFIG") or arg("--config")
    if not cfg or not os.path.isfile(cfg): sys.exit("board_next.py: set SWARM_CONFIG to the swarm.json path")
    c = json.load(open(cfg)); name = c.get("name", "swarm")
    out = arg("--out") or (os.path.splitext(c["board"])[0] + "_next.html" if c.get("board") else os.path.join(os.path.dirname(os.path.abspath(cfg)), "board_next.html"))
    git = "--no-git" not in sys.argv; as_of = arg("--as-of"); loop = int(arg("--loop", 0) or 0); until = arg("--until")
    if "--serve" in sys.argv:
        serve(lambda: collect([cfg], as_of, git, title=f"{name} swarm"), f"{name} swarm", int(arg("--port", 8898))); return
    while True:
        try:
            html = page(collect([cfg], as_of, git, refresh=loop, title=f"{name} swarm"), f"{name} swarm")
            open(out + ".tmp", "w", encoding="utf-8").write(html); os.replace(out + ".tmp", out)
        except Exception as e: sys.stderr.write(f"board_next: {e!r}\n")
        if not loop or (until and time.strftime("%Y%m%d%H%M") >= until): break
        time.sleep(loop)
    if not loop: print(out)


if __name__ == "__main__":
    main()
