#!/usr/bin/env python3
"""Jev Harness Lab: a read-only dashboard over the harness runs (live or finished).

  python3 app/server.py [port]      default 8918
Reads results/runs/<run>/{stdout.log,decisions.jsonl} and results/runs/*.json written by harness/run.py.
"""
import glob, json, os, re, statistics, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
RES = os.path.join(ROOT, "results", "runs")
TOOLS = os.path.join(ROOT, "results")


SECRET = re.compile(r"npg_[A-Za-z0-9]+|postgres(?:ql)?://\S+|(?<=\"password\":\")[^\"]+|(?<=password=)\S+")


def scrub(obj):
    """Never show a password or a connection string, even from an old log."""
    if isinstance(obj, str):
        obj = SECRET.sub("<redacted>", obj)
        obj = re.sub(r"/Users/[^/\s\"']+", "~", obj)  # home paths stay off screen
        return re.sub(r"(~/(?:Downloads|Desktop|Documents)/)[^/\n\"']+", r"\1…", obj)
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    return obj


def read_json(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default


def runs():
    out = []
    for d in sorted(glob.glob(os.path.join(RES, "jh-*"))):
        if not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        rel = os.path.relpath(d, RES)
        r = read_json(os.path.join(os.path.dirname(d), name + ".json"))
        parts = name.split("-")  # jh-<config>-<task>-r<rep>
        out.append({"id": rel, "name": name, "config": parts[1], "task": parts[2], "rep": parts[3],
                    "status": (r or {}).get("status", "running"), "score": (r or {}).get("score"),
                    "mtime": os.path.getmtime(os.path.join(d, "stdout.log")) if os.path.exists(os.path.join(d, "stdout.log")) else 0})
    return sorted(out, key=lambda x: -x["mtime"])


def run_detail(rel):
    d = os.path.join(RES, rel)
    if not os.path.realpath(d).startswith(os.path.realpath(RES)):
        return {}
    name = os.path.basename(d)
    decisions = []
    if os.path.exists(os.path.join(d, "decisions.jsonl")):
        for line in open(os.path.join(d, "decisions.jsonl")):
            try:
                decisions.append(json.loads(line))
            except ValueError:
                pass
    events, pending = [], {}
    usage = {"requests": 0, "input": 0, "output": 0, "cost": 0.0, "models": {}}
    if os.path.exists(os.path.join(d, "stdout.log")):
        for line in open(os.path.join(d, "stdout.log"), errors="replace"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            m = e.get("message", {})
            if e.get("type") == "message_end" and m.get("role") == "assistant":
                us = m.get("usage", {})
                usage["requests"] += 1
                usage["input"] += us.get("input", 0) + us.get("cacheRead", 0)
                usage["output"] += us.get("output", 0)
                usage["cost"] += (us.get("cost") or {}).get("total", 0) or 0
                usage["models"][m.get("model", "?")] = usage["models"].get(m.get("model", "?"), 0) + 1
                for c in m.get("content", []):
                    if c.get("type") == "text" and c.get("text", "").strip():
                        events.append({"kind": "text", "text": c["text"][:3000]})
                    elif c.get("type") == "toolCall":
                        ev = {"kind": "tool", "id": c.get("id"), "tool": c.get("name"), "args": c.get("arguments", {}), "result": None, "blocked": False}
                        pending[c.get("id")] = ev; events.append(ev)
                if m.get("stopReason") == "error":
                    events.append({"kind": "error", "text": str(m.get("errorMessage"))[:400]})
            elif e.get("type") == "message_end" and m.get("role") == "toolResult":
                ev = pending.get(m.get("toolCallId"))
                if ev is not None:
                    txt = "".join(c.get("text", "") for c in m.get("content", []))
                    ev["result"] = txt[:1500]
                    ev["blocked"] = txt.startswith("JEV GATE")
            elif e.get("type") == "message_end" and m.get("role") == "user":
                txt = "".join(c.get("text", "") for c in m.get("content", []) if isinstance(c, dict))
                if txt.startswith("VERIFIER"):
                    events.append({"kind": "verifier_msg", "text": txt})
    usage["cost"] = round(usage["cost"], 4)
    result = read_json(os.path.join(os.path.dirname(d), name + ".json"))
    prompt = open(os.path.join(d, "PROMPT.md")).read() if os.path.exists(os.path.join(d, "PROMPT.md")) else ""
    return {"id": rel, "name": name, "decisions": decisions, "events": events, "usage": usage, "result": result, "prompt": prompt}


def summary():
    rows = {}
    for p in glob.glob(os.path.join(RES, "jh-*.json")):
        r = read_json(p)
        if not r or r.get("status") != "completed":
            continue
        k = (r["config"], r["task"])
        rows.setdefault(k, []).append(r)
    out = []
    for (cfg, task), rs in sorted(rows.items()):
        out.append({"config": cfg, "task": task, "n": len(rs),
                    "score": round(statistics.mean(x["score"] for x in rs), 1),
                    "scores": [x["score"] for x in rs],
                    "input_tokens": round(statistics.mean(x["usage"]["input"] for x in rs)),
                    "llm_cost": round(statistics.mean(x["usage"]["cost"] for x in rs), 4),
                    "jev_calls": round(statistics.mean(x["jev"]["calls"] for x in rs), 1),
                    "jev_ms": round(statistics.mean(x["jev"]["ms"] for x in rs)),
                    "jev_cost": round(statistics.mean(x["jev"].get("cost_usd", 0) for x in rs), 5),
                    "wall_s": round(statistics.mean(x["wall_s"] for x in rs), 1),
                    "bash_sql": sum(x["jev"]["bash_sql"] for x in rs),
                    "prod_ok": all(x["production_untouched"] for x in rs),
                    "models": sorted({m for x in rs for m in x["usage"]["models"]})})
    return out


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=APP, **k)

    def log_message(self, *a):
        pass

    def send_json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); p = unquote(u.path)
        if p == "/api/runs": return self.send_json(runs())
        if p.startswith("/api/run/"): return self.send_json(scrub(run_detail(p[len("/api/run/"):])))
        if p == "/api/summary": return self.send_json(summary())
        if p == "/api/probes": return self.send_json(read_json(os.path.join(TOOLS, "probes.json"), {}))
        if p == "/api/neon": return self.send_json(read_json(os.path.join(TOOLS, "neon_features.json"), {}))
        if p == "/api/waf": return self.send_json(read_json(os.path.join(TOOLS, "waf_probe.json"), {}))
        return super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8918
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
