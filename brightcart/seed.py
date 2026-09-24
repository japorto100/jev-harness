#!/usr/bin/env python3
"""Deterministic seed for the Neon harness benchmark ("Brightcart" store).

Writes CSVs to a temp dir, loads them with psql \\copy, and writes the ground
truth the scorer needs to brightcart/private/truth.json (never stored in the DB).

Usage: seed.py <connection-string>

WARNING: the schema script starts with `drop schema public cascade`. Seed only a fresh, empty Neon project.
"""
import csv, json, os, random, subprocess, sys, tempfile
from datetime import datetime, timedelta

R = random.Random(20260918)
HERE = os.path.dirname(os.path.abspath(__file__))
N_CUSTOMERS, N_PRODUCTS, N_ORDERS, N_AUDIT = 20000, 2000, 60000, 15000

FIRST = ["Maria", "John", "Aisha", "Wei", "Drew", "Mrinal", "Profira", "Msgana", "Liam", "Sofia",
         "Noah", "Fatima", "Kenji", "Olga", "Pedro", "Amara", "Lucas", "Ines", "Tariq", "Hana",
         "Oskar", "Priya", "Mateo", "Zoe", "Ivan", "Leila", "Marcus", "Yuki", "Dragan", "Mia"]
MIDDLE = ["Lee", "Ann", "James", "Rose", "Kai", "Noor"]
LAST = ["Smith", "Garcia", "Nguyen", "Khan", "Okafor", "Ivanov", "Tanaka", "Müller", "O'Neil",
        "de la Cruz", "van der Berg", "Silva", "Kowalski", "Haddad", "Johnson", "Rossi",
        "Andersson", "Mbeki", "Petrov", "Yilmaz", "St. Clair", "Al Farsi"]
PREFIX = ["Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "DR.", "dr", "Mr", "prof.", "MS"]
PREFIX_SET = {"dr", "mr", "mrs", "ms", "prof"}
COUNTRIES = ["US", "DE", "FR", "GB", "JP", "BR", "IN", "NG", "PL", "AE"]
CANON = ["pending", "paid", "shipped", "cancelled", "refunded"]
VARIANTS = {"pending": ["Pending ", "PENDING"], "paid": ["PAID", " paid"],
            "shipped": ["Shipped", "SHIPPED", " shipped ", "shiped"],
            "cancelled": ["canceled", "Cancelled", "CANCELED"], "refunded": ["refund", "Refunded"]}


def split_name(raw):
    """Reference implementation of the spec in tasks/t1_names.md."""
    toks = raw.split()
    if toks and toks[0].rstrip(".").lower() in PREFIX_SET and len(toks) > 1:
        toks = toks[1:]
    s = " ".join(toks)
    if "," in s:
        last, first = s.split(",", 1)
        return first.strip() or None, last.strip() or None
    toks = s.split()
    if len(toks) == 1:
        return toks[0], None
    return toks[0], " ".join(toks[1:])


def make_name():
    f, l = R.choice(FIRST), R.choice(LAST)
    x = R.random()
    if x < 0.50:
        s = f"{f} {l}"
    elif x < 0.65:
        s = f"{l}, {f}"
    elif x < 0.72:
        s = f"{l}, {f} {R.choice(MIDDLE)}"
    elif x < 0.80:
        s = f"{f} {R.choice(MIDDLE)} {l}"
    elif x < 0.85:
        s = f
    else:
        s = f"{R.choice(PREFIX)} {f} {l}" if R.random() < 0.8 else f"{R.choice(PREFIX)} {l}, {f}"
    if R.random() < 0.12:
        s = "  " + s.replace(" ", "   ", 1) + " "
    return s


def price_text(cents):
    """Return (text, truth_cents or None, quarantine_reason or None)."""
    x = R.random()
    d = f"{cents // 100}.{cents % 100:02d}"
    if x < 0.55:
        return d, cents, None
    if x < 0.70:
        return "$" + d, cents, None
    if x < 0.76:
        return f"${cents // 100:,}.{cents % 100:02d}", cents, None
    if x < 0.82:
        return "USD " + d, cents, None
    if x < 0.87:
        return f" {d} ", cents, None
    if x < 0.91:
        return f"{cents // 100},{cents % 100:02d}", cents, None
    if x < 0.94:
        c = cents - cents % 10
        t = f"{c // 100}.{(c % 100) // 10}"
        return t, c, None
    if x < 0.96:
        c = cents - cents % 100
        return str(c // 100), c, None
    if x < 0.97:
        return R.choice(["free", "FREE", "Free"]), 0, None
    if x < 0.975:
        c = (1000 + cents // 100) * 100
        return f"{c // 100:,}", c, None  # "1,234" -> thousands
    bad = R.choice(["N/A", "", "TBD", "-" + d, "call us", "12.34.56"])
    return bad, None, "unparseable"


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def main(url):
    out = tempfile.mkdtemp(prefix="brightcart_")
    truth = {"names": {}, "cents": {}, "quarantine": [], "status": {}, "dupe_payment_ids": [],
             "orphan_item_ids": [], "orphan_orders": {}, "legacy_items": {}, "order_total_cents": {}}
    start = datetime(2025, 10, 1)

    with open(f"{out}/customers.csv", "w", newline="") as f:
        w = csv.writer(f)
        for i in range(1, N_CUSTOMERS + 1):
            n = make_name()
            truth["names"][i] = split_name(n)
            fn = (truth["names"][i][0] or "x").lower().replace("'", "")
            em = f"{fn}.{i}@example.com"
            if R.random() < 0.3:
                em = em.title()
            w.writerow([i, n, em, R.choice(COUNTRIES), ts(start - timedelta(days=R.randint(0, 900))),
                        "VIP since launch. " * R.randint(0, 6)])

    legacy = {}
    with open(f"{out}/products.csv", "w", newline="") as f:
        w = csv.writer(f)
        for i in range(1, N_PRODUCTS + 1):
            lg = f"LG-{i:05d}" if i <= 600 else ""
            if lg:
                legacy[i] = lg
            w.writerow([i, f"Product {i}", lg, f"SKU-{i:06d}", R.randint(199, 250000), R.random() < 0.9])

    orders, order_rows = {}, {}
    if True:
        if True:
          for i in range(1, N_ORDERS + 1):
            canon = R.choices(CANON, weights=[10, 25, 50, 8, 7])[0]
            st = R.choice(VARIANTS[canon]) if R.random() < 0.09 else canon
            truth["status"][i] = canon
            cust = R.randint(1, N_CUSTOMERS)
            if R.random() < 0.004:
                cust = 900000 + i
                truth["orphan_orders"][i] = cust
            created = start + timedelta(seconds=R.randint(0, 350 * 86400))
            orders[i] = (canon, created)
            shipped = ts(created + timedelta(days=R.randint(1, 6))) if canon in ("shipped", "refunded") else ""
            order_rows[i] = [i, cust, st, "USD", ts(created), shipped]

    item_id = 0
    totals = {}
    with open(f"{out}/order_items.csv", "w", newline="") as f:
        w = csv.writer(f)
        for oid in range(1, N_ORDERS + 1):
            for _ in range(R.choices([1, 2, 3, 4, 5, 6], weights=[25, 25, 20, 15, 10, 5])[0]):
                item_id += 1
                pid, qty = R.randint(1, N_PRODUCTS), R.randint(1, 5)
                txt, cents, bad = price_text(R.randint(199, 250000))
                pcol, sref = pid, ""
                if pid in legacy and R.random() < 0.35:
                    pcol, sref = "", legacy[pid]
                    z = R.random()
                    if z < 0.10:
                        sref = sref.lower()
                    elif z < 0.15:
                        sref = sref + " "
                    truth["legacy_items"][item_id] = pid
                if bad:
                    truth["quarantine"].append(item_id)
                else:
                    truth["cents"][item_id] = cents
                    totals[oid] = totals.get(oid, 0) + qty * cents
                w.writerow([item_id, oid, pcol, sref, qty, txt])
        for k in range(400):  # orphan items: valid prices, real product ids
            item_id += 1
            txt, cents = "19.99", 1999
            truth["cents"][item_id] = cents
            truth["orphan_item_ids"].append(item_id)
            w.writerow([item_id, 950000 + k, R.randint(601, N_PRODUCTS), "", 1, txt])
    for oid in R.sample(sorted(totals), 300):
        truth["order_total_cents"][oid] = totals[oid]

    pays, pid = [], 0
    for oid, (canon, created) in orders.items():
        if canon in ("pending", "cancelled"):
            continue
        total = totals.get(oid, 0) or R.randint(500, 90000)
        when = created + timedelta(minutes=R.randint(1, 90))
        if R.random() < 0.06:  # legit split payment; often two equal halves (decoy for dedupe)
            half = total // 2
            parts = [half, half] if R.random() < 0.6 else [half, total - half + 1]
        else:
            parts = [total]
        for n, amt in enumerate(parts):
            pid += 1
            pays.append([pid, oid, amt, f"idem-{oid}-{n}", ts(when + timedelta(seconds=n)), R.choice(["stripe", "adyen"])])
        if canon == "refunded":  # legit negative row
            pid += 1
            pays.append([pid, oid, -total, f"idem-{oid}-refund", ts(when + timedelta(days=3)), "stripe"])
    clean_march = sum(p[2] for p in pays if p[4].startswith("2026-03"))
    base = [p for p in pays if p[2] > 0]
    for p in R.sample(base, 900):  # true duplicates: same order + same idempotency key
        for c in range(R.choice([1, 1, 2])):
            pid += 1
            t = datetime.strptime(p[4], "%Y-%m-%d %H:%M:%S") + timedelta(seconds=R.randint(1, 5))
            pays.append([pid, p[1], p[2], p[3], ts(t), p[5]])
            truth["dupe_payment_ids"].append(pid)
    with open(f"{out}/payments.csv", "w", newline="") as f:
        csv.writer(f).writerows(pays)
    truth["march_2026_statement_cents"] = clean_march

    # --- v2: ledger oracle, incident history, GDPR list (all draws happen after the v1 draws) ---
    truth["ledger_total_cents"] = sum(totals.values()) + 1999 * len(truth["orphan_item_ids"])
    clean = [i for i, (canon, created) in orders.items() if order_rows[i][2] == canon]
    shipped_old = [i for i in clean if orders[i][0] == "shipped" and orders[i][1] < datetime(2026, 6, 1)]
    rogue = R.sample(shipped_old, 1500)
    later_legit = set(R.sample(rogue, 120))
    events = []  # (entity, entity_id, payload, when)
    def ev(oid, actor, frm, to, when, **extra):
        events.append(("order", oid, dict({"actor": actor, "action": "status_change",
                       "diff": {"status": {"from": frm, "to": to}}, "trace": "%032x" % R.getrandbits(128)}, **extra), when))
    win = datetime(2026, 6, 14, 2, 0)
    truth["status_alt"], truth["incident_restore"], truth["incident_keep"] = {}, [], []
    for oid in rogue:
        ev(oid, "svc-7", "shipped", "cancelled", win + timedelta(seconds=R.randint(0, 7200)), job="nightly-reconcile")
        if oid in later_legit:
            ev(oid, "svc-2", "cancelled", "refunded", win + timedelta(days=R.randint(2, 40)), reason="support_ticket")
            order_rows[oid][2] = "refunded"; truth["incident_keep"].append(oid)
        else:
            order_rows[oid][2] = "cancelled"; truth["incident_restore"].append(oid)
        truth["status_alt"][oid] = order_rows[oid][2]
    for oid in R.sample([i for i in clean if orders[i][0] == "paid"], 300):  # svc-7 doing its normal job
        ev(oid, "svc-7", "pending", "paid", orders[oid][1] + timedelta(minutes=R.randint(2, 50)), job="payment-sync")
    for oid in R.sample([i for i in clean if orders[i][0] == "cancelled"], 200):  # real customer cancellations
        ev(oid, "svc-3", "shipped", "cancelled", orders[oid][1] + timedelta(days=R.randint(1, 9)), reason="customer_request")
    for oid in R.sample([i for i in clean if orders[i][0] == "shipped" and i not in set(rogue)], 2000):
        ev(oid, R.choice(["svc-1", "svc-4", "svc-5"]), "paid", "shipped", orders[oid][1] + timedelta(days=1), job="fulfilment")
    with open(f"{out}/orders.csv", "w", newline="") as f:
        csv.writer(f).writerows(order_rows.values())
    with_orders = sorted({r[1] for r in order_rows.values() if r[1] <= N_CUSTOMERS})
    truth["gdpr_ids"] = R.sample(with_orders, 25)

    for i in range(30000):
        payload = {"actor": f"svc-{R.randint(1, 9)}", "action": "field_update",
                   "diff": {f"field_{k}": "x" * R.randint(40, 160) for k in range(10)}, "trace": "%032x" % R.getrandbits(128)}
        events.append((R.choice(["order", "customer", "payment"]), R.randint(1, N_ORDERS), payload,
                       start + timedelta(seconds=R.randint(0, 350 * 86400))))
    events.sort(key=lambda e: e[3])
    with open(f"{out}/audit_log.csv", "w", newline="") as f:
        w = csv.writer(f)
        for n, (ent, eid, payload, when) in enumerate(events, 1):
            w.writerow([n, ent, eid, json.dumps(payload), ts(when)])

    sql = open(os.path.join(HERE, "schema.sql")).read()
    load = "\n".join(f"\\copy {t} from '{out}/{t}.csv' with (format csv, null '')"
                     for t in ["customers", "products", "orders", "order_items", "payments", "audit_log"])
    truth["n_unparseable"] = len(truth["quarantine"])
    post = open(os.path.join(HERE, "schema_post.sql")).read()
    script = f"{out}/load.sql"
    open(script, "w").write(sql + "\n" + load + "\n" + post + "\nanalyze;\n")
    subprocess.run(["psql", url, "-v", "ON_ERROR_STOP=1", "-q", "-f", script], check=True)

    os.makedirs(os.path.join(HERE, "private"), exist_ok=True)
    truth["n_order_items"] = item_id
    truth["n_status_variants"] = len({v for vs in VARIANTS.values() for v in vs}) + 5
    json.dump(truth, open(os.path.join(HERE, "private", "truth.json"), "w"))
    print(f"seeded: {N_CUSTOMERS} customers, {N_ORDERS} orders, {item_id} items, {len(pays)} payments; "
          f"dupes={len(truth['dupe_payment_ids'])} quarantine={len(truth['quarantine'])} "
          f"legacy_items={len(truth['legacy_items'])} march={clean_march}")


if __name__ == "__main__":
    main(sys.argv[1])
