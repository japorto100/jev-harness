"""Small Neon REST API client: just what the harness needs. Reads NEON_API_KEY and NEON_PROJECT_ID from the environment."""
import os, time
import requests

API = "https://console.neon.tech/api/v2"


class Neon:
    def __init__(self, project=None, key=None):
        self.project = project or os.environ["NEON_PROJECT_ID"]
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {key or os.environ['NEON_API_KEY']}", "Accept": "application/json"})

    def api(self, method, path, **kw):
        for _ in range(60):
            r = self.s.request(method, f"{API}/projects/{self.project}{path}", timeout=60, **kw)
            if r.status_code == 423:  # the project is busy with another operation
                time.sleep(1); continue
            r.raise_for_status()
            return r.json() if r.text else {}
        raise RuntimeError(f"{path}: project stayed locked")

    def wait(self):
        for _ in range(240):
            ops = self.api("GET", "/operations?limit=20").get("operations", [])
            if all(o["status"] in ("finished", "skipped", "cancelled") for o in ops):
                return
            time.sleep(0.5)

    def branches(self):
        return self.api("GET", "/branches")["branches"]

    def default_branch(self):
        return next(b for b in self.branches() if b.get("default"))

    def endpoint_of(self, branch_id):
        return next((e for e in self.api("GET", "/endpoints")["endpoints"] if e["branch_id"] == branch_id), None)

    def create_branch(self, name, parent_id):
        b = self.api("POST", "/branches", json={"branch": {"name": name, "parent_id": parent_id}, "endpoints": [{"type": "read_write"}]})
        self.wait()
        return b["branch"]["id"]

    def rotate_password(self, branch_id, role="neondb_owner"):
        """Branch roles start with the parent's password. Resetting it on the child gives the run its own credential."""
        self.api("POST", f"/branches/{branch_id}/roles/{role}/reset_password")
        self.wait()

    def connection_uri(self, branch_id, role="neondb_owner", database="neondb"):
        return self.api("GET", f"/connection_uri?branch_id={branch_id}&database_name={database}&role_name={role}")["uri"]

    def children(self, branch_id):
        return [b["id"] for b in self.branches() if b.get("parent_id") == branch_id]

    def delete_branch(self, branch_id):
        for child in self.children(branch_id):
            self.delete_branch(child)
        try:
            self.api("DELETE", f"/branches/{branch_id}")
            self.wait()
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 404:
                raise
