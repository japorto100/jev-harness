drop schema public cascade; create schema public;
create table customers (id int primary key, full_name text not null, email text not null, country text, created_at timestamp, notes text);
create table products (id int primary key, name text not null, legacy_sku text, sku text not null, price_cents int not null, active boolean not null);
create table orders (id int primary key, customer_id int, status text not null, currency text not null, created_at timestamp not null, shipped_at timestamp);
create table order_items (id int primary key, order_id int not null, product_id int, sku_ref text, quantity int not null, unit_price text);
create table payments (id int primary key, order_id int not null, amount_cents bigint not null, idempotency_key text not null, created_at timestamp not null, provider text);
create table audit_log (id int primary key, entity text, entity_id int, payload jsonb, created_at timestamp);
