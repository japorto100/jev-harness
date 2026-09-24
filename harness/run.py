#!/usr/bin/env python3
"""Run Pi + the Jev harness extension on one Brightcart ticket, on its own Neon branch, then score it.

Usage: python3 harness/run.py <config> <task> <rep> [--keep] [--timeout 1500]
Needs (in the environment or .env): NEON_API_KEY, NEON_PROJECT_ID, TYPESAFE_API_KEY, GEMINI_API_KEY.
Writes results/runs/<run>.json and results/runs/<run>/{PROMPT.md,stdout.log,decisions.jsonl,REPORT.md}.

Safety: each run gets its own branch with its own role password; the agent's shell runs under an OS sandbox
(no access to /Users or /home) in a temp working directory with an empty HOME and no API keys; the extension
blocks the Neon control plane, the neon CLI and production ids in code. Production is fingerprinted before and after.
"""
import argparse, json, os, shutil, signal, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness.neon import Neon  # noqa: E402
from brightcart import prompts  # noqa: E402

EXT = os.path.join(ROOT, "extension", "jev-harness.ts")
OUT = os.path.join(ROOT, "results", "runs")
# Outside the user's home: the agent's sandboxed shell can't read or write anything under /Users or /home.
WORK = os.environ.get("JEV_WORKDIR") or os.path.join(tempfile.gettempdir(), "jev-harness", "runs")
SECRETS_DIR = os.path.expanduser("~/.jev-harness/secrets")
FAST = os.environ.get("JEV_FAST_MODEL", "gemini-3.5-flash-lite")
POWER = os.environ.get("JEV_POWER_MODEL", "gemini-3.8-flash")
KEYS = {"NEON_API_KEY", "TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FIRECRAWL_API_KEY"}

# config -> (model the run starts on, extension settings)
CONFIGS = {
    "base":     (POWER, {}),
    "fast":     (FAST,  {}),
    "router":   (POWER, {"JEV_ROUTER": "1"}),
    "context":  (POWER, {"JEV_CONTEXT": "jev"}),
    "fullrb":   (POWER, {"JEV_CONTEXT": "full"}),
    "gate":     (POWER, {"JEV_GATE": "policy"}),
    "gatebash": (POWER, {"JEV_GATE": "policy", "JEV_GATE_BASH": "1"}),
    "blunt":    (POWER, {"JEV_GATE": "blunt"}),
    "automode": (POWER, {"JEV_GATE": "automode"}),
    "verifier": (POWER, {"JEV_VERIFIER": "1"}),
    "fastver":  (FAST,  {"JEV_VERIFIER": "1"}),
    "all":      (POWER, {"JEV_ROUTER": "1", "JEV_CONTEXT": "jev", "JEV_GATE": "policy", "JEV_GATE_BASH": "1", "JEV_VERIFIER": "1"}),
}


def load_dotenv():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def pi_usage(stdout_path):
    u = {"errors": [], "requests": 0, "input": 0, "output": 0, "cache_read": 0, "cost": 0.0, "tool_calls": {}, "models": {}}
    final = ""
    for line in open(stdout_path, errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get("message", {})
        if d.get("type") == "message_end" and m.get("role") == "assistant":
            us = m.get("usage", {})
            if m.get("stopReason") == "error":
                u["errors"].append(str(m.get("errorMessage"))[:200])
            u["requests"] += 1
            u["input"] += us.get("input", 0) + us.get("cacheRead", 0)
            u["output"] += us.get("output", 0)
            u["cache_read"] += us.get("cacheRead", 0)
            u["cost"] += (us.get("cost") or {}).get("total", 0) or 0
            u["models"][m.get("model", "?")] = u["models"].get(m.get("model", "?"), 0) + 1
            text = "".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")
            final = text if text.strip() else final
            for c in m.get("content", []):
                if c.get("type") == "toolCall":
                    u["tool_calls"][c.get("name", "?")] = u["tool_calls"].get(c.get("name", "?"), 0) + 1
    u["cost"] = round(u["cost"], 4)
    return u, final


def jev_summary(log_path):
    s = {"calls": 0, "ms": 0, "in_tokens": 0, "gate": {}, "hard_rule": 0, "bash_sql": 0, "checkpoints": 0, "router": None, "context": None, "verifier": []}
    if not os.path.exists(log_path):
        return s
    for line in open(log_path):
        d = json.loads(line)
        k = d["kind"]
        if "jev_ms" in d:
            s["calls"] += 1; s["ms"] += d["jev_ms"]; s["in_tokens"] += d.get("jev_in_tokens", 0)
        if k == "gate":
            s["gate"][d["verdict"]] = s["gate"].get(d["verdict"], 0) + 1
            s["checkpoints"] += 1 if (d.get("checkpoint") or {}).get("id") else 0
        elif k == "hard_rule":
            s["hard_rule"] += 1
        elif k == "bash_sql":
            s["bash_sql"] += 1
        elif k == "router":
            s["router"] = {x: d.get(x) for x in ("pick", "tier", "why", "confidence", "complexity")}
        elif k == "context":
            s["context"] = {"chosen": d.get("chosen"), "jev_ms": d.get("jev_ms")}
        elif k == "verifier":
            s["verifier"].append({x: d.get(x) for x in ("attempt", "quality", "grounded", "retry")})
    s["cost_usd"] = round(s["in_tokens"] * 0.042 / 1e6, 5)  # $0.042 per million input tokens, output free
    return s


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("config", choices=CONFIGS); ap.add_argument("task", choices=prompts.TASKS); ap.add_argument("rep")
    ap.add_argument("--keep", action="store_true", help="keep the run branch for inspection")
    ap.add_argument("--timeout", type=int, default=1500)
    a = ap.parse_args()
    name = f"jh-{a.config}-{a.task}-r{a.rep}"
    model, extra = CONFIGS[a.config]
    neon = Neon()
    prod = neon.default_branch()
    prod_ep = neon.endpoint_of(prod["id"])
    prod_url = neon.connection_uri(prod["id"])

    resdir = os.path.join(OUT, name); shutil.rmtree(resdir, ignore_errors=True); os.makedirs(resdir)
    work = os.path.join(WORK, name); shutil.rmtree(work, ignore_errors=True); os.makedirs(os.path.join(work, ".home"))
    os.makedirs(os.path.join(work, ".pi"), exist_ok=True)
    json.dump({"retry": {"enabled": True, "maxRetries": 6, "baseDelayMs": 4000}}, open(os.path.join(work, ".pi", "settings.json"), "w"))

    fp_before = prompts.fingerprint(prod_url)
    for b in neon.branches():  # a stale branch from an earlier attempt
        if b["name"] == name:
            neon.delete_branch(b["id"])
    t0 = time.time(); bid = neon.create_branch(name, prod["id"]); branch_s = round(time.time() - t0, 2)
    neon.rotate_password(bid)  # the run's credential must not work on production
    burl = neon.connection_uri(bid)
    t0 = time.time(); subprocess.run(["psql", burl, "-X", "-Atc", "select 1"], capture_output=True); first_query_s = round(time.time() - t0, 2)

    text = prompts.prompt(a.task, name)
    open(os.path.join(resdir, "PROMPT.md"), "w").write(text)
    log_path = os.path.join(resdir, "decisions.jsonl")
    os.makedirs(SECRETS_DIR, mode=0o700, exist_ok=True)
    secrets = os.path.join(SECRETS_DIR, name + ".json")
    with os.fdopen(os.open(secrets, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump({"TYPESAFE_API_KEY": os.environ["TYPESAFE_API_KEY"], "NEON_API_KEY": os.environ["NEON_API_KEY"]}, f)
    env = {k: v for k, v in os.environ.items() if k not in KEYS}
    env.update(HOME=os.path.join(work, ".home"), BRANCH_URL=burl, NEON_PROJECT=neon.project, NEON_BRANCH_ID=bid, JEV_RUN=name,
               JEV_LOG=log_path, JEV_SECRETS=secrets, JEV_PROTECTED=",".join(filter(None, [prod["id"], (prod_ep or {}).get("id")])),
               JEV_FAST_MODEL=FAST, JEV_POWER_MODEL=POWER, **extra)
    cmd = ["pi", "-p", "--mode", "json", "--no-session", "-e", EXT, "--provider", "google", "--model", model, text]

    t1 = time.time(); status = "completed"
    with open(os.path.join(resdir, "stdout.log"), "w") as so, open(os.path.join(resdir, "stderr.log"), "w") as se:
        proc = subprocess.Popen(cmd, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=so, stderr=se, start_new_session=True)
        def kill(*_):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        signal.signal(signal.SIGTERM, lambda *x: (kill(), sys.exit(143)))
        try:
            rc = proc.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            kill(); rc, status = -1, "timeout"
        finally:
            kill()  # the whole process group: an orphaned agent must never outlive its branch
            if os.path.exists(secrets):
                os.remove(secrets)
    wall = round(time.time() - t1, 1)

    checkpoints = len(neon.children(bid))
    fp_after = prompts.fingerprint(prod_url)
    sc = subprocess.run([sys.executable, os.path.join(ROOT, "brightcart", "score.py"), a.task, burl, prod_url], capture_output=True, text=True)
    sc = json.loads(sc.stdout or '{"score": 0, "error": "scorer failed"}')
    usage, final = pi_usage(os.path.join(resdir, "stdout.log"))
    if usage["errors"] and status == "completed":
        status = "error"  # an LLM API error ended the run: not a valid sample
    open(os.path.join(resdir, "REPORT.md"), "w").write(final)
    result = {"run": name, "config": a.config, "task": a.task, "rep": a.rep, "status": status, "exit_code": rc, "wall_s": wall,
              "branch_create_s": branch_s, "first_query_s": first_query_s, "score": sc.get("score", 0), "checks": sc.get("checks", []),
              "false_done_claims": sc.get("false_done_claims"), "production_untouched": fp_before == fp_after,
              "checkpoint_branches": checkpoints, "usage": usage, "jev": jev_summary(log_path), "start_model": model}
    json.dump(result, open(os.path.join(OUT, name + ".json"), "w"), indent=1)
    if not a.keep:
        neon.delete_branch(bid)
    j = result["jev"]
    print(f"{name}: score {result['score']} {status} {wall}s req={usage['requests']} in={usage['input']} models={usage['models']} "
          f"jev_calls={j['calls']} gate={j['gate']} hard_rule={j['hard_rule']} bash_sql={j['bash_sql']} prod_ok={result['production_untouched']}")


if __name__ == "__main__":
    main()
