#!/usr/bin/env python3
"""Resumable batch of harness runs. Finished runs are skipped; runs that die on a model API 429 wait and retry.

Usage: python3 harness/batch.py [--plan ladder,trap,verifier] [--reps 3] [--workers 2]
Neon's free plan allows 10 branches per project. Each run uses 1 branch plus up to 2 checkpoints, so keep workers <= 3.
"""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "runs")
PLANS = {
    "ladder": [(c, t) for c in ("base", "router", "context", "gate", "all") for t in ("t5", "h2", "h3")],
    "trap": [(c, "t5") for c in ("gatebash", "fullrb", "fast", "blunt")],
    "verifier": [("fastver", "hs"), ("fast", "hs")],
}


def status(name):
    p = os.path.join(OUT, name + ".json")
    return json.load(open(p)) if os.path.exists(p) else {}


def once(cfg, task, rep):
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run.py"), cfg, task, str(rep), "--timeout", "1800" if task == "hs" else "1200"],
                       capture_output=True, text=True, cwd=ROOT)
    line = (p.stdout.strip().splitlines() or ["?"])[-1]
    msg = f"{time.strftime('%H:%M:%S')} {line} ({round(time.time() - t0)}s)" + (f" ERR {p.stderr[-300:]}" if p.returncode else "")
    with open(os.path.join(OUT, "batch.log"), "a") as f:
        f.write(msg + "\n")
    return msg


def run(job):
    cfg, task, rep = job
    name = f"jh-{cfg}-{task}-r{rep}"
    if status(name).get("status") == "completed":
        return f"skip {name}"
    for attempt in range(4):
        msg = once(cfg, task, rep)
        r = status(name)
        if r.get("status") != "error" or not any("429" in e for e in r.get("usage", {}).get("errors", [])):
            return msg
        time.sleep(60 * (attempt + 1))  # per-minute model quota: wait, then rerun on a fresh branch
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="ladder,trap,verifier"); ap.add_argument("--reps", type=int, default=3); ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    jobs = [(c, t, rep) for rep in range(1, a.reps + 1) for pl in a.plan.split(",") for c, t in PLANS[pl]
            if not (pl == "verifier" and rep > 2)]  # rep-major: a partial batch still covers every cell
    with ThreadPoolExecutor(a.workers) as ex:
        for m in ex.map(run, jobs):
            print(m, flush=True)


if __name__ == "__main__":
    main()
