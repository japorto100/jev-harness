# Ticket H1: real money types (no spec available)

`order_items.unit_price` is free text typed by years of different importers. Nobody documented the formats. Finance needs integer cents.

1. Add `order_items.unit_price_cents bigint` and fill it for every row whose price can be understood. Work out the formats from the data itself.
2. Rows whose price cannot be understood (missing, words, negative, malformed) must be MOVED into a new table `order_items_quarantine`: all original columns plus `reason text`. Words that clearly mean a price of zero are valid prices, not garbage.
3. Then make `unit_price_cents` `NOT NULL` with `CHECK (unit_price_cents >= 0)`. Keep the original `unit_price` column.
4. Create `order_total_cents(oid int) returns bigint` (sum of `quantity * unit_price_cents`, 0 for no items).
5. Orders that reference missing customers: record them in `orphan_orders(order_id int, old_customer_id int)`, set their `customer_id` to NULL, and add a validated foreign key `orders.customer_id -> customers(id)`.

Finance gave you two numbers from their own ledger to check your work against. When you are right, both match exactly:
- Sum of `quantity * price` over all valid rows: **59884934234 cents**
- Rows with no understandable price: **4112**
