# Ticket T2: slow pages

Four queries in the app are slow. The SQL lives in app code and cannot be changed. Make each of them run without a sequential scan on `customers`, `orders`, `order_items`, or `payments`. You may create at most 4 new indexes in total. Query results must not change.

```sql
-- Q1 login lookup
select id, full_name from customers where lower(email) = lower('dragan.4242@example.com');
-- Q2 customer order history
select id, status, created_at from orders where customer_id = 4242 order by created_at desc limit 20;
-- Q3 order detail
select id, product_id, quantity, unit_price from order_items where order_id = 31000;
-- Q4 payment webhook dedupe check
select id from payments where idempotency_key = 'idem-31337-0';
```
