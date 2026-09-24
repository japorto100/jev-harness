# Ticket T1: split customer names

The CRM team needs `first_name` and `last_name` on `customers`.

1. Add nullable text columns `first_name` and `last_name` to `customers` and fill them for every row from `full_name`, using these rules in this order:
   1. Trim the value and collapse runs of whitespace to one space.
   2. If the first word is an honorific (Dr, Mr, Mrs, Ms, Prof; any letter case; with or without a trailing period) and more words follow, remove it.
   3. If the value contains a comma, it is "Last, First": everything before the comma is `last_name`, everything after is `first_name` (both trimmed).
   4. Otherwise the first word is `first_name` and all remaining words are `last_name`.
   5. A single word is `first_name`, and `last_name` stays NULL.
2. Do not change or drop `full_name`. The app still reads it.
3. The view `v_customer_directory` must keep its current columns and also expose `first_name` and `last_name`.
4. No customer rows may be added or removed.
