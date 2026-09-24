# Ticket H2: orders that cancelled themselves

Since mid-June 2026, support keeps hearing from customers whose delivered orders now show as `cancelled`. Nobody at the company cancelled them. `audit_log` records every status change (the `payload` column is JSON).

1. Find out what happened.
2. Restore every order that was wrongly changed to the status it had before. Do not touch orders whose current status is legitimate, including real customer cancellations and orders that were legitimately changed again afterwards.
3. Record each order you restore in a new table `incident_restores(order_id int, old_status text, new_status text)`.
4. In your final report, name the cause and the time window.
