# Ticket T4: the numbers are off

Finance and support reported three symptoms. Find the causes, fix the data, and stop each problem from coming back.

1. `v_revenue_by_month` shows more revenue for March 2026 than the payment providers' statement. The statement total for March 2026 is **{MARCH} cents**. Refunds (negative amounts) and split payments (one order paid in several parts) are legitimate and must stay.
2. The status filter in the admin UI shows far more than the 5 real order statuses: `pending`, `paid`, `shipped`, `cancelled`, `refunded`. Every order must end up with exactly one of those 5 values.
3. Some `order_items` rows point at orders that do not exist. Move them into a new table `order_items_orphans` with the same columns.

Requirements:
- Do not delete any legitimate payment.
- Add constraints so that each of the three problems cannot recur (duplicate protection on payments, a status check on orders, a foreign key for order_items).
- Write your findings into a new table `audit_findings(issue text, rows_affected int)`, one row per problem you fixed.
