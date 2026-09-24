#!/usr/bin/env python3
"""Measure the Neon features the sponsor brief asks for, in a separate test project it creates
(so the benchmark project keeps its branch allowance). Needs NEON_API_KEY and NEON_ORG_ID. Writes results/neon_features.json.

  provisioning   create a project -> first successful query (s)
  branching      create a branch of a seeded database -> first query (s), n=5
  reset          break the branch (DROP COLUMN), restore it from its parent, verify (s), n=5
  scale_to_zero  suspend the compute, then time the first query that wakes it (cold start), n=3
  autoscaling    the compute's autoscaling range, and vCPUs seen by neon_utils.num_cpus() under load
"""
import json, os, statistics, subprocess, threading, time
import requests

API = "https://console.neon.tech/api/v2"
H = {"Authorization": f"Bearer {os.environ['NEON_API_KEY']}", "Content-Type": "application/json", "Accept": "application/json"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "results", "neon_features.json")
NAME = "jev-harness-neon-features"
ORG = os.environ["NEON_ORG_ID"]  # Neon console: Settings -> Organization


def api(method, path, **kw):
    for _ in range(30):
        r = requests.request(method, API + path, headers=H, timeout=60, **kw)
        if r.status_code == 423:  # project locked by a running operation
            time.sleep(1); continue
        r.raise_for_status()
        return r.json() if r.text else {}
    raise RuntimeError(f"{path}: still locked")


def psql(url, sql, timeout=120):
    p = subprocess.run(["psql", url, "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr[-300:])
    return p.stdout.strip()


def wait_ops(pid):
    for _ in range(120):
        ops = api("GET", f"/projects/{pid}/operations?limit=20").get("operations", [])
        if all(o["status"] in ("finished", "skipped", "cancelled") for o in ops):
            return
        time.sleep(0.5)


def conn(pid, branch_id):
    return api("GET", f"/projects/{pid}/connection_uri?branch_id={branch_id}&database_name=neondb&role_name=neondb_owner")["uri"]


def until_query(url, deadline=120):
    t0 = time.time()
    while time.time() - t0 < deadline:
        try:
            psql(url, "select 1", timeout=30); return round(time.time() - t0, 2)
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("never answered")


def main():
    res = {"date": time.strftime("%Y-%m-%d %H:%M %Z")}
    # 1. provisioning
    existing = [p for p in api("GET", "/projects?limit=100&org_id=" + ORG)["projects"] if p["name"] == NAME]
    if existing:
        pid = existing[0]["id"]; res["provisioning"] = json.load(open(OUT)).get("provisioning") if os.path.exists(OUT) else None
        prod = api("GET", f"/projects/{pid}/branches")["branches"]; main_b = [b for b in prod if b.get("default")][0]["id"]
        url = conn(pid, main_b)
    else:
        t0 = time.time()
        made = api("POST", "/projects", json={"project": {"name": NAME, "pg_version": 17, "org_id": ORG}})
        t_api = round(time.time() - t0, 2)
        pid = made["project"]["id"]; main_b = made["branch"]["id"]; url = made["connection_uris"][0]["connection_uri"]
        t_query = until_query(url)
        res["provisioning"] = {"api_s": t_api, "first_query_after_api_s": t_query, "total_s": round(t_api + t_query, 2), "project_id": pid}
    print("provisioning", res["provisioning"])
    # seed a small table
    psql(url, "create table if not exists products (id int primary key, name text, legacy_sku text); "
              "insert into products select g, 'p'||g, 'LG-'||g from generate_series(1,100000) g on conflict do nothing;")
    wait_ops(pid)

    # 2 + 3. branching and reset
    br, rs = [], []
    for i in range(5):
        t0 = time.time()
        b = api("POST", f"/projects/{pid}/branches", json={"branch": {"name": f"agent-run-{i}"}, "endpoints": [{"type": "read_write"}]})
        t_api = round(time.time() - t0, 2)
        bid = b["branch"]["id"]; burl = b["connection_uris"][0]["connection_uri"]
        t_q = until_query(burl)
        br.append({"api_s": t_api, "first_query_after_api_s": t_q, "total_s": round(t_api + t_q, 2)})
        psql(burl, "alter table products drop column legacy_sku;")
        assert psql(burl, "select count(*) from information_schema.columns where table_name='products' and column_name='legacy_sku'") == "0"
        wait_ops(pid)
        t0 = time.time()
        api("POST", f"/projects/{pid}/branches/{bid}/restore", json={"source_branch_id": main_b})
        t_api = round(time.time() - t0, 2)
        t_q = until_query(burl)
        back = psql(burl, "select count(*) from information_schema.columns where table_name='products' and column_name='legacy_sku'") == "1"
        rows = psql(burl, "select count(legacy_sku) from products")
        rs.append({"api_s": t_api, "first_query_after_api_s": t_q, "total_s": round(t_api + t_q, 2), "column_back": back, "rows_with_legacy_sku": int(rows)})
        wait_ops(pid)
        for x in api("GET", f"/projects/{pid}/branches")["branches"]:  # restore keeps a backup branch; clean both
            if x["id"] == bid or x.get("parent_id") == bid or x["name"].startswith(f"agent-run-{i}"):
                pass
        api("DELETE", f"/projects/{pid}/branches/{bid}")
        wait_ops(pid)
        for x in api("GET", f"/projects/{pid}/branches")["branches"]:
            if not x.get("default") and x["name"] != "main":
                try:
                    api("DELETE", f"/projects/{pid}/branches/{x['id']}"); wait_ops(pid)
                except Exception:
                    pass
        print("branch", br[-1], "reset", rs[-1])
    res["branching"] = {"runs": br, "p50_total_s": statistics.median(x["total_s"] for x in br)}
    res["reset"] = {"runs": rs, "p50_total_s": statistics.median(x["total_s"] for x in rs)}

    # 4. scale to zero
    ep = api("GET", f"/projects/{pid}/endpoints")["endpoints"]
    ep = [e for e in ep if e["branch_id"] == main_b][0]
    res["endpoint_settings"] = {k: ep.get(k) for k in ("autoscaling_limit_min_cu", "autoscaling_limit_max_cu", "suspend_timeout_seconds", "current_state")}
    cold = []
    for i in range(3):
        api("POST", f"/projects/{pid}/endpoints/{ep['id']}/suspend")
        for _ in range(120):
            st = api("GET", f"/projects/{pid}/endpoints/{ep['id']}")["endpoint"]["current_state"]
            if st == "idle":
                break
            time.sleep(0.5)
        time.sleep(2)
        t0 = time.time(); psql(url, "select count(*) from products", timeout=60)
        cold.append(round(time.time() - t0, 2))
        t0 = time.time(); psql(url, "select count(*) from products"); warm = round(time.time() - t0, 2)
        print("cold start", cold[-1], "warm", warm)
    res["scale_to_zero"] = {"cold_query_s": cold, "p50_cold_s": statistics.median(cold), "warm_query_s": warm,
                            "note": "compute suspended through the API, then the first query wakes it"}

    # 5. autoscaling
    try:
        api("PATCH", f"/projects/{pid}/endpoints/{ep['id']}", json={"endpoint": {"autoscaling_limit_min_cu": 0.25, "autoscaling_limit_max_cu": 2}})
        wait_ops(pid)
    except Exception as e:
        res["autoscaling_patch_error"] = str(e)[:200]
    ep2 = api("GET", f"/projects/{pid}/endpoints/{ep['id']}")["endpoint"]
    samples = []
    try:
        psql(url, "create extension if not exists neon_utils;")
        stop = threading.Event()
        def load():
            while not stop.is_set():
                try:
                    psql(url, "select sum(sqrt(a*b)) from generate_series(1,3000) a, generate_series(1,3000) b", timeout=120)
                except Exception:
                    pass
        threads = [threading.Thread(target=load) for _ in range(4)]
        t0 = time.time(); samples.append((0.0, float(psql(url, "select num_cpus()"))))
        for t in threads: t.start()
        while time.time() - t0 < 90:
            time.sleep(3)
            samples.append((round(time.time() - t0, 1), float(psql(url, "select num_cpus()"))))
        stop.set()
        for t in threads: t.join()
        res["autoscaling"] = {"range_cu": [ep2.get("autoscaling_limit_min_cu"), ep2.get("autoscaling_limit_max_cu")], "num_cpus_samples": samples,
                              "min_vcpu": min(s[1] for s in samples), "max_vcpu": max(s[1] for s in samples)}
    except Exception as e:
        res["autoscaling"] = {"range_cu": [ep2.get("autoscaling_limit_min_cu"), ep2.get("autoscaling_limit_max_cu")], "error": str(e)[:300], "num_cpus_samples": samples}
    print("autoscaling", res["autoscaling"])
    res["project_id"] = pid
    json.dump(res, open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main()
