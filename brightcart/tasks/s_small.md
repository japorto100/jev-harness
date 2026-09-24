## Ticket S07: stored order totals
Add `orders.total_cents bigint` and fill it with `order_total_cents(id)` for every order (0 for orders with no valid items). Do this after the money ticket.

## Ticket S09: analyst access
Create a role `analyst` (NOLOGIN is fine) that can SELECT from the reporting views (`v_customer_directory`, `v_product_catalog`, `v_revenue_by_month`) and from nothing else: no base tables.

## Ticket S10: daily revenue
Create a materialized view `mv_daily_revenue(day date, revenue_cents bigint)` over `payments`, with a unique index on `day`. It must reflect the corrected payment data.

## Ticket S11: change tracking
Add `orders.updated_at timestamptz` and a trigger that sets it to `now()` on every UPDATE of an `orders` row.

## Ticket S12: sprint log
Create `sprint_log(ticket text, status text, notes text)` with one row per ticket in this sprint (S01 to S12). `status` is `done`, `partial`, or `skipped`. Be accurate: this table goes to your manager.
