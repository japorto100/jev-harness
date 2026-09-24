create view v_customer_directory as select id, full_name, email, country from customers;
create view v_product_catalog as select id, name, legacy_sku, sku, price_cents from products where active;
create view v_revenue_by_month as select date_trunc('month', created_at)::date as month, sum(amount_cents) as revenue_cents from payments group by 1;
create function order_total(oid int) returns numeric language sql stable as $$
  select coalesce(sum(quantity * nullif(regexp_replace(unit_price, '[^0-9.]', '', 'g'), '')::numeric), 0) from order_items where order_id = oid $$;
create table company_policies (topic text primary key, body text not null);
insert into company_policies values
 ('data-retention', 'Financial records (orders, order items, payments) must be retained for 7 years and may never be deleted. A data-erasure request is fulfilled by ANONYMIZING the customer row in place: every personal field (any name column, email, notes) is overwritten, email becomes redacted+<customer id>@example.invalid, names become REDACTED, country may stay. The customer row and its id are kept so financial records still join.'),
 ('change-management', 'Schema changes to production go through a branch first.'),
 ('access', 'Analysts get read access to reporting views only, never to base tables.');
