# N+1 Queries and Fetching Too Many Rows from the Application in PostgreSQL

An application can be slow even when **every individual SQL statement runs very fast**. Two commonly overlooked causes are:

1. **N+1 queries:** the application fetches a list with one query, and then executes an extra query for **each element** of that list.
2. **Overfetching:** the application asks PostgreSQL to return **too many rows, too many columns, or too much nested data**, and only then filters or truncates it in Java.

For example, a page displaying 50 orders and the ordering customer's name:

```text
SELECT 50 orders                    -> 1 query
for each order:
    SELECT customer WHERE id = ...  -> 50 queries
                                      ----------
                                      51 queries for a single page
```

An alternative using `JOIN` retrieves all needed data in **one round trip**:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 50;
```

However, cramming everything into a single `JOIN` is no silver bullet. If each order has 10 line items, joining orders with line items turns 50 orders into **500 result rows**, repeating order and customer fields on every row. Joining another one-to-many relation can **cross-multiply** rows unexpectedly.

Likewise, a statement like:

```sql
SELECT * FROM orders;
```

may be only **one query**, yet if the table holds millions of orders with wide `JSONB`/`TEXT` columns, the data transferred from PostgreSQL to the application is massive. Calling `.stream().limit(20)` on the loaded list afterward does nothing to reduce what the database already sent.

**Proper optimization reduces both round-trip count and the amount of data read, transferred, mapped, and retained in the application**, while preserving business correctness and consistency.

## 1. Learning Objectives

After this lesson, you will be able to:

- Spot N+1 queries across Java loops, ORM lazy loading, serializers, and SQL logs.
- Distinguish **query count**, **round trips**, **rows returned**, **row width**, **bytes transferred**, and execution time.
- Replace N+1 patterns using **JOINs**, **batch fetching**, `IN`/`ANY`, aggregated queries, or **projections**.
- Choose distinct strategies for **many-to-one**, **one-to-many**, and multi-collection relationships.
- Avoid `JOIN` side effects: duplicate parent rows, broken pagination, Cartesian multiplication, and inflated aggregates.
- Limit data inside PostgreSQL via `WHERE`, `ORDER BY`, `LIMIT`, keyset pagination, and narrow projections.
- Understand JDBC `fetchSize`, cursors, and streaming, and why batch fetching **differs** from capping total rows.
- Measure using `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements`, app logs, tracing, and row/byte counters.
- Design indexes supporting consolidated queries rather than tuning only individual N+1 lookups.
- Write regression tests guarding against N+1 queries and overfetching.

## 2. Two Problem Classes: Too Many Queries vs Too Much Data

| Aspect | N+1 Queries | Overfetching |
| --- | --- | --- |
| Symptom | One request emits many identical SQLs differing only in bind values | One or a few SQLs return more rows, columns, or bytes than the screen needs |
| Example | 1 query for 100 orders + 100 queries for customers | Fetching 100,000 orders and displaying only 20 |
| Dominant cost | Network round trips, parse/bind/execute, pool pressure, server overhead | I/O, CPU, memory, network transfer, decoding, object mapping, GC |
| Can both occur together? | Yes | Yes |
| Common fixes | JOIN, batch fetch, selective eager fetch, DataLoader | Projection, `WHERE`/`LIMIT`, pagination, streaming, fetching only needed relations |
| Risk when fixing | One-to-many JOINs multiply rows; memory rises | Wrong limits drop data or break pagination stability |
| Measurement | Queries per request, repeated SQL templates, round-trip time | Rows/bytes per request, heap/JVM memory, result set size, latency |

**One query is not automatically better than two queries.** Two queries fetching 20 orders and 80 line items can beat one `JOIN` emitting 20 × 80 rows across two independent collections. The goal is **total cost and correctness**, not minimizing query count at any price.

### 2.1. Total-Cost Thinking

A conceptual breakdown:

```text
Request latency ≈
    connection pool wait time
  + total round-trip / driver overhead
  + SQL planning / execution
  + transfer + result set decoding
  + object mapping / serialization
  + business processing
  + other wait times
```

Do not treat this as an exact additive formula when queries overlap or run concurrently. It shows why queries that look fast in `psql` can still make an application slow.

## 3. Why Do N+1 Queries Happen?

Suppose an order listing screen displays the customer's name:

```sql
SELECT order_id, customer_id, ordered_at, total_amount
FROM orders
ORDER BY ordered_at DESC
LIMIT 50;
```

After receiving 50 orders, the code executes:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id = 17;
```

and the same statement 49 more times.

This is the **1 + N** pattern:

```text
1: fetch N orders (parent entities)
N: fetch each order's customer
=> 1 + N database queries without caching or batching
```

### 3.1. N+1 Does Not Always Mean Literally N+1 Queries

If those 50 orders belong to only 5 customers, an ORM's first-level cache may cut customer loads from 50 down to 5 under favorable conditions. If cached beforehand, even fewer; if every order has a distinct customer, roughly 50 queries.

Thus N+1 is an **access pattern whose query count scales with list size**, not a promise that every run emits literally N+1 statements.

### 3.2. The Root Cause Often Sits at Repository / Service / Serializer Boundaries

Code may look clean:

```java
List<Order> orders = orderRepository.findRecent(50);
for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

If `getCustomer()` triggers ORM lazy loading for an uninitialized association, that loop emits many `SELECT`s—even though **no SQL appears inside the `for` loop**.

Similarly:

- A mapper converting entities to DTOs calls `getItems()`.
- Jackson serialization walks lazy associations while building JSON.
- A template engine accesses `order.customer.name`.
- A GraphQL resolver queries a data source per parent object.
- A service calls a repository to count orders for each customer.

**Inspect the actual SQL emitted per request**, never infer query count from Java syntax alone.

## 4. The Round-Trip Effect: Why Many Tiny Queries Still Cost a Lot

Suppose looking up one customer by ID takes only **0.3 ms on the server**. Across 100 customer lookups, before counting anything else, you already pay 100 rounds of parse/bind/execute and result framing.

If the application and database communicate across a network with measurable round-trip latency, 100 sequential queries can add far more latency than PostgreSQL's total CPU time.

Illustrative **hypothetical calculation to show scale**, not a benchmark:

```text
One request needs 50 sequential customer lookups
Assume each round trip takes ~4 ms
=> 50 round trips alone can approach 200 ms

If consolidated into one batch query:
=> 1 round trip for 50 customers
=> index access and data transfer costs still remain
```

### 4.1. Increasing Connection Pool Size Does Not Fix N+1

Adding connections can raise concurrent request capacity up to a point, yet:

- Every request still emits excessive queries.
- Database concurrency, lock contention, and cache pressure rise.
- An oversized pool lets more queries fight for CPU and I/O.
- Sequential queries inside **the same request** do not automatically parallelize just because the pool is bigger.

First **eliminate redundant queries** and cap data fetched; size the pool afterward for real throughput.

### 4.2. Co-Located N+1 Still Carries Overhead

Even when app and PostgreSQL share a host and network latency is tiny, the server still receives, parses/plans/binds/executes, and returns each SQL statement. Pool checkouts, driver work, mapping, and context switches still add up.

## 5. PostgreSQL Lab Environment

We use schema `app_fetch_lab` with customers, orders, and order items. Run these examples only in a **test database** where creating tables and loading demo data is allowed.

### 5.1. Create Schema

```sql
CREATE SCHEMA IF NOT EXISTS app_fetch_lab;
```

### 5.2. `customers` Table

```sql
CREATE TABLE app_fetch_lab.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region_code TEXT NOT NULL,
    email TEXT NOT NULL
);
```

### 5.3. `orders` Table

```sql
CREATE TABLE app_fetch_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES app_fetch_lab.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    note TEXT,
    extra_data JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

### 5.4. `order_items` Table

```sql
CREATE TABLE app_fetch_lab.order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES app_fetch_lab.orders(order_id),
    product_code TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);
```

### 5.5. Load 1,000 Customers

```sql
INSERT INTO app_fetch_lab.customers
    (customer_id, customer_name, region_code, email)
SELECT
    g.n,
    'Customer ' || g.n,
    CASE WHEN g.n % 3 = 0 THEN 'N'
         WHEN g.n % 3 = 1 THEN 'C'
         ELSE 'S'
    END,
    'customer' || g.n || '@example.test'
FROM generate_series(1, 1000) AS g(n);
```

### 5.6. Load 50,000 Orders

```sql
INSERT INTO app_fetch_lab.orders
    (customer_id, ordered_at, status, total_amount, note, extra_data)
SELECT
    (g.n % 1000) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
      + make_interval(mins => g.n),
    CASE WHEN g.n % 10 < 7 THEN 'PAID'
         WHEN g.n % 10 < 9 THEN 'PENDING'
         ELSE 'CANCELLED'
    END,
    (100 + g.n % 5000)::numeric(12, 2),
    repeat('Example note; ', 16),
    jsonb_build_object(
        'source', CASE WHEN g.n % 2 = 0 THEN 'web' ELSE 'app' END,
        'debugText', repeat('metadata-', 24)
    )
FROM generate_series(1, 50000) AS g(n);
```

### 5.7. Load Three Items per Order

On a newly created table, `order_id` runs sequentially from 1 to 50,000. Insert by selecting existing IDs rather than assuming identity values across repeated runs:

```sql
INSERT INTO app_fetch_lab.order_items
    (order_id, product_code, quantity, unit_price)
SELECT
    o.order_id,
    'SKU-' || x.item_no,
    x.item_no,
    (15 * x.item_no)::numeric(12, 2)
FROM app_fetch_lab.orders AS o
CROSS JOIN generate_series(1, 3) AS x(item_no);
```

If run once on a fresh schema: **50,000 orders × 3 items = 150,000 items**.

### 5.8. Indexes for the Lab

```sql
CREATE INDEX idx_app_orders_recent
ON app_fetch_lab.orders
    (ordered_at DESC, order_id DESC);

CREATE INDEX idx_app_orders_customer_recent
ON app_fetch_lab.orders
    (customer_id, ordered_at DESC, order_id DESC);

CREATE INDEX idx_app_items_order
ON app_fetch_lab.order_items (order_id);

ANALYZE app_fetch_lab.customers;
ANALYZE app_fetch_lab.orders;
ANALYZE app_fetch_lab.order_items;
```

PostgreSQL **does not automatically create an index on child foreign-key columns** merely from FK declarations. Therefore `order_items(order_id)` is created explicitly so multi-order item lookups have an index path.

### 5.9. Verify Data

```sql
SELECT
    (SELECT count(*) FROM app_fetch_lab.customers)
        AS customer_count,
    (SELECT count(*) FROM app_fetch_lab.orders)
        AS order_count,
    (SELECT count(*) FROM app_fetch_lab.order_items)
        AS item_count;
```

Expected on initial empty-schema load: 1,000 / 50,000 / 150,000.

## 6. Seeing N+1 Clearly in SQL: 1 + 20 Queries

A page displays the 20 newest orders:

```sql
SELECT order_id, customer_id, ordered_at, total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Suppose Java loops over the rows and for each `customer_id` executes:

```sql
SELECT customer_id, customer_name
FROM app_fetch_lab.customers
WHERE customer_id = 781;
```

repeating that customer `SELECT` for every ID.

### 6.1. Total SQL Count

```text
N = orders returned on the page = 20
1 query for orders
20 queries for customers (if every lookup hits the DB)
=> 21 queries/request
```

Change the page size to 100 orders:

```text
1 list query + 100 customer queries
=> 101 queries/request
```

As page size grows, query count scales linearly with N. Under hundreds of requests, load climbs rapidly even though a single PK `SELECT` is cheap.

### 6.2. Multi-Level N+1

An endpoint can even execute:

```text
1 query for 20 orders
20 queries for customers
20 queries for items
20 queries counting payments
=> 61 queries/request
```

N+1 **compounds across relations**. One level deeper—such as fetching product details per item—makes query count scale with item count rather than order count.

## 7. Fix A: `JOIN` for Many-to-One Relationships

Because each order references exactly one customer, joining `customers` fetches customer names in the same query:

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM app_fetch_lab.orders AS o
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

In the lab schema, FK `orders.customer_id` is `NOT NULL` and references `customers` PK, so every valid order has **exactly one** customer. The `JOIN` **never multiplies order rows**.

### 7.1. Why Does `JOIN` Solve N+1 Here?

- One SQL statement sent to PostgreSQL.
- The database executes the join via `Nested Loop`, `Hash Join`, `Merge Join`, or another valid plan.
- The application receives needed display columns directly instead of calling the customer repository 20 times.
- One round trip for the primary result set.

**This does not mean PostgreSQL reads only one physical row**; it still scans/probes indexes and pages across both tables. The gain comes from letting one globally optimizable query handle the join and cutting round trips.

### 7.2. `EXPLAIN` on the `JOIN`

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM app_fetch_lab.orders AS o
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

You may see `Nested Loop` with PK lookups on `customers`, or `Hash Join` depending on stats and cost. **Do not demand one specific join algorithm** to consider the fix valid.

### 7.3. `LEFT JOIN` When the Relationship Is Optional

If an order might lack a customer in another data model, use `LEFT JOIN` to **keep orders without customers**:

```sql
SELECT o.order_id, c.customer_name
FROM app_fetch_lab.orders AS o
LEFT JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id;
```

Do not swap `JOIN` for `LEFT JOIN` merely because it feels “safer” while ignoring semantics: check FKs, `NOT NULL`, and business rules.

## 8. Fix B: Batch Fetching via `ANY(array)`

It isn't always convenient to rewrite every repository into a single `JOIN`, especially across modular boundaries or independent caching layers.

Instead of querying customers one by one:

1. Fetch the 20 orders.
2. Collect **distinct `customer_id`s**.
3. Send **one query** for all matching customers.
4. Build a `customerId -> CustomerDTO` map in Java.
5. Stitch them together in memory.

Example SQL fetching customers by list:

```sql
SELECT
    customer_id,
    customer_name
FROM app_fetch_lab.customers
WHERE customer_id IN (781, 782, 783, 784);
```

Or with a PostgreSQL array:

```sql
SELECT
    customer_id,
    customer_name
FROM app_fetch_lab.customers
WHERE customer_id = ANY(ARRAY[781, 782, 783, 784]::integer[]);
```

### 8.1. Query Count

```text
Before: 1 orders query + 20 customer queries = 21 queries
After:  1 orders query +  1 customer query   =  2 queries
```

Query count stays independent of order count as long as the ID list fits in a reasonable batch.

### 8.2. `ANY(array)` in JDBC

With the PostgreSQL JDBC driver, you can bind a SQL array:

```java
List<Integer> customerIds = List.of(781, 782, 783, 784);

String sql = """
    SELECT customer_id, customer_name
    FROM app_fetch_lab.customers
    WHERE customer_id = ANY(?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql);
     java.sql.Array ids = connection.createArrayOf(
         "integer", customerIds.toArray())) {
    ps.setArray(1, ids);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Put customer into Map<Integer, CustomerDto>.
        }
    }
}
```

This illustrates the driver API. In real code, `java.sql.Array` manages resources via `free()` in `finally` rather than assuming `AutoCloseable` support across every JDK/driver:

```java
java.sql.Array ids =
    connection.createArrayOf("integer", customerIds.toArray());
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setArray(1, ids);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read row data.
        }
    }
} finally {
    ids.free();
}
```

**Note:** when the ID list is empty, skip the query and return an empty map; never generate invalid `IN ()` SQL. For huge ID lists, chunk into batches or use a suited loading pattern instead of blindly passing gigantic arrays.

### 8.3. Batching Does Not Eliminate All Costs

A `SELECT ... ANY(...)` over 50,000 IDs still incurs substantial planning time, CPU, memory, and I/O. If the app already fetched too many orders, batch-fetching customers **does not cure the initial overfetch**.

Right order of operations: **bound the parent orders first**, then batch-fetch related data.

## 9. Batch Fetching in Java: DTO Mapping Example

Suppose the repository already fetched orders containing `customerId`:

```java
record OrderRow(
    long orderId,
    int customerId,
    java.math.BigDecimal totalAmount
) {}

record CustomerRow(int customerId, String customerName) {}

record OrderSummary(
    long orderId,
    String customerName,
    java.math.BigDecimal totalAmount
) {}

List<OrderRow> orders = findRecentOrders(connection, 20);

List<Integer> ids = orders.stream()
    .map(OrderRow::customerId)
    .distinct()
    .toList();

Map<Integer, CustomerRow> customersById =
    findCustomersByIds(connection, ids);

List<OrderSummary> summaries = orders.stream()
    .map(order -> {
        CustomerRow customer = customersById.get(order.customerId());
        if (customer == null) {
            throw new IllegalStateException(
                "Missing customer " + order.customerId()
            );
        }
        return new OrderSummary(
            order.orderId(),
            customer.customerName(),
            order.totalAmount()
        );
    })
    .toList();
```

This is a **structural Java example**, assuming `findRecentOrders` and `findCustomersByIds` use parameterized SQL and proper JDBC/transaction handling. Key points:

- Calling `distinct()` avoids requesting duplicate customer IDs.
- Looking up in a Java `Map` emits zero extra SQL.
- Missing customers follow business invariants instead of silently showing wrong names.
- Output preserves `orders` ordering rather than relying on `IN`/`ANY` return order.

### 9.1. Preserving the Input ID List's Order

`WHERE id = ANY(...)` **does not guarantee output ordered like the input array**. Usually mapping by key in Java is best.

If SQL itself must preserve input array order, use `unnest(... WITH ORDINALITY)` and `JOIN`:

```sql
WITH requested AS (
    SELECT id, ord
    FROM unnest(ARRAY[784, 781, 783]::integer[])
         WITH ORDINALITY AS u(id, ord)
)
SELECT
    c.customer_id,
    c.customer_name
FROM requested AS r
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = r.id
ORDER BY r.ord;
```

This preserves order when SQL ordering is required, though unnecessary when Java stitches by map.

## 10. N+1 in One-to-Many Relationships: Selecting Items per Order

On an order listing screen:

```text
1 SELECT fetching 20 orders
20 SELECTs fetching order_items WHERE order_id = ?
```

A typical item query:

```sql
SELECT order_item_id, product_code, quantity, unit_price
FROM app_fetch_lab.order_items
WHERE order_id = 49999
ORDER BY order_item_id;
```

With 20 orders of 3 items each, N+1 runs 21 queries for just **20 orders + 60 items**. Two strategies usually work well.

### 10.1. One `JOIN` Across the Relationship

```sql
SELECT
    o.order_id,
    o.ordered_at,
    i.order_item_id,
    i.product_code,
    i.quantity
FROM app_fetch_lab.orders AS o
LEFT JOIN app_fetch_lab.order_items AS i
  ON i.order_id = o.order_id
WHERE o.order_id IN (49996, 49997, 49998, 49999, 50000)
ORDER BY o.order_id, i.order_item_id;
```

With 3 items per order, this `JOIN` returns **15 rows** for 5 orders. Java must **group by `order_id`** to rebuild parent–children objects.

### 10.2. Two Queries: Parent Page First, Then Batch Children

Query 1:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Given the returned IDs, query 2:

```sql
SELECT
    order_id,
    order_item_id,
    product_code,
    quantity,
    unit_price
FROM app_fetch_lab.order_items
WHERE order_id = ANY(ARRAY[49981,49982,49983,49984,49985]::bigint[])
ORDER BY order_id, order_item_id;
```

In real code, the array holds **all order IDs from the fetched page**, not hardcoded examples.

Build:

```text
Map<Long, List<OrderItemDto>>
    orderId -> all items for that order
```

Then attach each order's list. If an order has no items, attach an **empty list** per business rules rather than treating the order as missing.

### 10.3. Why Two Queries Often Beat One `JOIN`

- **Paginate parents accurately** first.
- Avoid repeating every parent column across every child row.
- Keep narrow projections on both parent and child entities.
- Simplify loading multiple child collections cleanly.
- Make it easy to bound/monitor child rows per page.

Fixing N+1 does not require forcing everything into a single SQL statement.

## 11. The Trap of One-to-Many `JOIN` Followed by `LIMIT`

A dangerous SQL statement:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    i.order_item_id
FROM app_fetch_lab.orders AS o
LEFT JOIN app_fetch_lab.order_items AS i
  ON i.order_id = o.order_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

In the lab, each order has three items. This returns **20 joined rows**, not **20 orders**—covering roughly seven orders, with the seventh order missing some of its items.

**`LIMIT` caps post-JOIN rows**, without understanding “20 parent orders.”

### 11.1. Correct: Paginate Parents First, Then `JOIN`

```sql
WITH page AS (
    SELECT
        order_id,
        ordered_at,
        total_amount
    FROM app_fetch_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 20
)
SELECT
    p.order_id,
    p.ordered_at,
    p.total_amount,
    i.order_item_id,
    i.product_code,
    i.quantity
FROM page AS p
LEFT JOIN app_fetch_lab.order_items AS i
  ON i.order_id = p.order_id
ORDER BY p.ordered_at DESC, p.order_id DESC, i.order_item_id;
```

Here:

1. The `page` CTE selects **20 `order_id`s** first.
2. Items are joined only for those 20 orders.
3. Output exceeds 20 rows, yet contains every item of the exact 20 orders.

**Still:** cap child rows if a single order can hold hundreds of thousands of items, and verify pagination/snapshot rules match business requirements.

### 11.2. Parent Count vs Result Row Count

```text
20 orders × 3 items/order
=> 20 parent entities, yet 60 joined rows
```

An ORM may deduplicate parent entities when assembling the object graph, yet SQL still transfers all 60 joined rows. Never mistake an API returning 20 objects as proof PostgreSQL sent only 20 rows.

## 12. The Multi-Collection `JOIN` Trap: Cartesian Multiplication

Suppose each order has:

- 3 items.
- 4 shipments.
- 5 payment attempts.

Joining **three independent one-to-many collections**:

```text
1 order × 3 items × 4 shipments × 5 payments
=> up to 60 rows for a single order
```

Across 20 orders, output balloons up to 1,200 rows, repeating every item, shipment, and payment across combinations. This leads to:

- Massive duplicate data transferred.
- Memory spikes and heavy object mapping.
- ORM Cartesian product warnings or multiple-bag fetch errors.
- Inflated `SUM`s if aggregated post-join without respecting grain.

### 12.1. Recommended Fix

Select the **parent page first**, then:

1. Batch-load items for those order IDs.
2. Batch-load shipments.
3. Batch-load payments.
4. Stitch by `order_id`.

Total queries: **1 + 3 = 4 SQLs**, with zero Cartesian multiplication across collections.

### 12.2. Be Careful with `DISTINCT`

`DISTINCT` removes **identical projected rows**, yet cannot undo distinct combinations of item/shipment/payment columns and adds `Sort`/`HashAggregate` overhead. Never use `DISTINCT` to paper over a broken join model.

## 13. Aggregating Child Rows Inside PostgreSQL

When an API truly wants orders with nested items, PostgreSQL JSON aggregation returns **one SQL row per order**.

Example scoped to the 20 selected orders:

```sql
WITH page AS (
    SELECT
        order_id,
        ordered_at,
        total_amount
    FROM app_fetch_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 20
)
SELECT
    p.order_id,
    p.ordered_at,
    p.total_amount,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'itemId', i.order_item_id,
                'sku', i.product_code,
                'quantity', i.quantity
            )
            ORDER BY i.order_item_id
        ) FILTER (WHERE i.order_item_id IS NOT NULL),
        '[]'::jsonb
    ) AS items
FROM page AS p
LEFT JOIN app_fetch_lab.order_items AS i
  ON i.order_id = p.order_id
GROUP BY p.order_id, p.ordered_at, p.total_amount
ORDER BY p.ordered_at DESC, p.order_id DESC;
```

Key details:

- The CTE bounds the parent page first.
- `LEFT JOIN` keeps orders without items.
- `FILTER (WHERE i.order_item_id IS NOT NULL)` prevents emitting a `null` item element from outer-join padding.
- `COALESCE(..., '[]'::jsonb)` returns an empty array when an order has zero items.
- `ORDER BY` inside the aggregate orders items; the outer `ORDER BY` orders parent orders.

### 13.1. Is JSON Aggregation Free?

No. PostgreSQL still executes the join/aggregation, builds JSON, allocates memory, and transfers potentially large JSON payloads. This fits APIs returning nested JSON with reasonably bounded children. If an order can have huge item lists, paginate or expose a dedicated endpoint.

### 13.2. Avoid Inflating Totals When Joining Multiple Relations

When joining both items and payments, `SUM(i.quantity * i.unit_price)` multiplies by payment row count. A sound pattern is **aggregating each child relation by `order_id` first**, then joining the aggregated results by `order_id`.

Example:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS subtotal
    FROM app_fetch_lab.order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    t.subtotal
FROM app_fetch_lab.orders AS o
JOIN item_totals AS t
  ON t.order_id = o.order_id
WHERE o.order_id = 50000;
```

At scale, bound parent IDs first so you do not aggregate every item in the entire database.

## 14. `LATERAL`: One Round Trip, Yet Potentially N Inner Executions

PostgreSQL supports `LATERAL` so a subquery can reference columns from a preceding outer relation.

Example fetching the **first two items** of each order on the page:

```sql
WITH page AS (
    SELECT order_id, ordered_at
    FROM app_fetch_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 20
)
SELECT
    p.order_id,
    p.ordered_at,
    i.order_item_id,
    i.product_code
FROM page AS p
LEFT JOIN LATERAL (
    SELECT order_item_id, product_code
    FROM app_fetch_lab.order_items AS oi
    WHERE oi.order_id = p.order_id
    ORDER BY oi.order_item_id
    LIMIT 2
) AS i ON TRUE
ORDER BY p.ordered_at DESC, p.order_id DESC, i.order_item_id;
```

### 14.1. Does `LATERAL` Eliminate All N+1 Work?

Not necessarily. It is **one SQL round trip from the app**, yet the plan may use `Nested Loop` and execute the inner subquery **once per parent**. With a matching index retrieving 2 rows each time, it can be super fast.

Conversely, if each inner probe scans a huge table, repeating it N times is expensive even though the app sent only 1 query.

**Always inspect `EXPLAIN (ANALYZE, BUFFERS)` and `loops` on inner nodes.** Cutting network round trips does not turn server-side work into a single pass.

### 14.2. When Does `LATERAL` Fit Well?

- Fetching top-K child rows **per parent**.
- Inner query backed by `(order_id, order_item_id)` or a suited index.
- Parent list is already tightly bounded.
- Per-parent `LIMIT` semantics are needed rather than a global `LIMIT`.

## 15. JPA/Hibernate ORMs: Lazy Loading and N+1

A typical Java mapping:

```java
@Entity
class OrderEntity {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order")
    private List<OrderItemEntity> items;
}
```

This is an **illustrative mapping snippet**, omitting table/column names, getters/setters, and annotations needed to match the lab schema. Real projects must define exact mappings.

If a service loads a list of orders and then touches `order.getCustomer().getName()` or `order.getItems().size()`, the ORM emits queries for each uninitialized entity or collection.

### 15.1. Lazy Does Not Mean Broken

Lazy loading avoids fetching relations **when they are not needed**. It causes N+1 when code accesses an association across **a list of entities** without a suited batch or join strategy.

Never “fix” N+1 by switching **every association to `EAGER`**. That triggers overfetching on endpoints that don't need those relations and produces hard-to-control SQL.

### 15.2. `JOIN FETCH` for Many-to-One Relationships

In JPA/Hibernate with proper entity mappings:

```java
List<OrderEntity> orders = entityManager
    .createQuery("""
        select o
        from OrderEntity o
        join fetch o.customer
        order by o.orderedAt desc, o.id desc
        """, OrderEntity.class)
    .setMaxResults(20)
    .getResultList();
```

Because `o.customer` is many-to-one, `join fetch` does not **multiply parent rows** the way a collection join does. Still verify mappings, filters, authorization, and actual generated SQL.

### 15.3. Collection `JOIN FETCH` with Pagination Is Hazardous

Example:

```java
entityManager.createQuery("""
    select o
    from OrderEntity o
    left join fetch o.items
    order by o.orderedAt desc
    """, OrderEntity.class)
    .setMaxResults(20)
    .getResultList();
```

With a one-to-many collection, one parent spans multiple joined rows. ORMs/frameworks may warn, paginate in memory, or behave unexpectedly to avoid truncating collections—causing **massive overfetching even when the API returns 20 orders**.

**More reliable design:** paginate parent IDs first, then batch-load items for those IDs; or use native SQL selecting the parent page before joining as in section 11.

### 15.4. Entity Graphs and Fetch Profiles

JPA entity graphs / fetch plans let an endpoint specify which associations to load without altering global entity defaults. However, they **do not guarantee query count = 1**; always inspect the provider's generated SQL.

### 15.5. Batch Fetching

Hibernate offers batch fetching (e.g., configuring batch size for lazy associations). When entities await association initialization, the ORM loads a batch of IDs in one query instead of one query per ID.

Do not assume bumping `batch_size` solves everything:

- Associations must be accessed within an active session.
- Larger batch sizes produce `WHERE id IN (...)` queries with many elements.
- Memory usage and bound ID counts increase.
- Unused columns/entities may still be loaded.
- Exact behavior depends on provider, version, fetch plan, and mapping.

**Measure actual query counts** after changing configuration.

## 16. DTO Projections: Fetch Only the Columns the API Needs

A listing screen typically needs:

```text
orderId, orderedAt, totalAmount, customerName
```

It does not need:

```text
order.note, order.extra_data, customer.email,
all line items, or entity tracking metadata
```

Narrow query:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM app_fetch_lab.orders AS o
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

In JPA, use a DTO constructor projection:

```java
List<OrderSummaryDto> result = entityManager
    .createQuery("""
        select new com.example.dto.OrderSummaryDto(
            o.id,
            o.orderedAt,
            o.totalAmount,
            c.name
        )
        from OrderEntity o
        join o.customer c
        order by o.orderedAt desc, o.id desc
        """, OrderSummaryDto.class)
    .setMaxResults(20)
    .getResultList();
```

This JPQL assumes matching DTO constructors and field names; it cannot compile verbatim without defining those classes.

### 16.1. Benefits of DTO Projections

- PostgreSQL can avoid reading/detoasting unused wide columns.
- Less data transferred over the wire.
- Fewer object allocations and no persistence-context dirty-checking overhead.
- JSON serializers cannot accidentally trigger lazy loading.
- Clearer API contracts and lower risk of leaking sensitive columns.

Note that projections do not automatically produce an `Index Only Scan`; that depends on indexes and MVCC/visibility map state.

## 17. Overfetching: `SELECT *` and Wide Columns

In the lab, `orders` includes `note` and `extra_data`. A list view needs only order ID, timestamp, and total amount.

**Poor fit for a list view:**

```sql
SELECT *
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC
LIMIT 20;
```

**Better:**

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Even with the exact same row count, `SELECT *` can:

- Pull extra `TEXT`/`JSONB` fields.
- Increase output row width.
- Force reading/detoasting out-of-line TOAST values.
- Bloat network payloads.
- Increase `ResultSet`/DTO memory and JSON response size.

### 17.1. Reading `width` in `EXPLAIN`

```sql
EXPLAIN
SELECT *
FROM app_fetch_lab.orders
WHERE customer_id = 42;

EXPLAIN
SELECT order_id, total_amount
FROM app_fetch_lab.orders
WHERE customer_id = 42;
```

Inspect `width=...` on output nodes. `width` is the **estimated average row width in bytes**, not total network bytes and not guaranteed to match final JSON size.

### 17.2. `SELECT *` Also Couples Code to Schema Changes

Adding a column to a table causes `SELECT *` queries to silently pull extra data, and positional column mappers can break. Explicit projections improve both performance and contract stability.

## 18. Overfetching: Fetching Everything and Slicing in Java

Anti-pattern:

```java
List<Order> allOrders = orderRepository.findAll();

List<Order> page = allOrders.stream()
    .sorted(comparing(Order::getOrderedAt).reversed())
    .limit(20)
    .toList();
```

If `findAll()` loads 50,000 rows:

- PostgreSQL processed and sent 50,000 rows.
- JDBC/ORM decoded and allocated 50,000 objects.
- Java finally kept 20 rows.
- Calling `.limit(20)` in a Java stream **does nothing to shrink what the database sent**.

**Architecturally sound:**

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

### 18.1. Push Filter Predicates to the Database Too

Wrong:

```java
List<Order> all = orderRepository.findAll();
List<Order> paid = all.stream()
    .filter(o -> o.getStatus() == OrderStatus.PAID)
    .toList();
```

Better:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

PostgreSQL can use statistics, indexes, and optimizer rules to filter early and minimize returned rows.

### 18.2. Don't Force Everything Into SQL Blindly

Some business logic cannot be expressed cleanly in SQL or relies on external services. Even then, **narrow candidate rows in PostgreSQL first** before running the remaining logic in Java.

The key is separating **filters that safely cut data early** while preserving exact business meaning.

## 19. Database Pagination: `LIMIT` and `OFFSET`

Traditional pagination:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20 OFFSET 0;
```

Next page:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20 OFFSET 20;
```

PostgreSQL returns at most 20 rows per query, not the entire table.

### 19.1. Why Does `ORDER BY` Need a Stable Tie-Breaker?

With only:

```sql
ORDER BY ordered_at DESC
```

two orders sharing a timestamp lack a deterministic relative order. Adding unique `order_id DESC` establishes a total order for pagination.

Never rely on physical heap scan order; without `ORDER BY`, output order is never guaranteed.

### 19.2. Deep `OFFSET` Remains Expensive

```sql
SELECT order_id, ordered_at
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
OFFSET 40000
LIMIT 20;
```

The executor typically still traverses qualifying rows to skip 40,000 positions before emitting 20. An ordered index helps, yet deep-page cost still scales with offset.

### 19.3. Concurrent Inserts Shift Pages

If a user reads page 1 and a new order is inserted before page 2 is requested, `OFFSET` can duplicate or skip rows across pages depending on data and snapshot timing.

When users need stable traversal of a changing feed, consider keyset pagination or an appropriate snapshot/export design.

## 20. Keyset Pagination: Resume from the Last Key

First page:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

The app keeps the key pair of the **last row on the page**:

```text
last_ordered_at = 2026-02-01T12:00:00Z
last_order_id   = 45678
```

Next page:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
WHERE (ordered_at, order_id)
    < (TIMESTAMPTZ '2026-02-01 12:00:00+00', 45678)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

With two `NOT NULL` columns both sorted `DESC`, tuple comparison `(ordered_at, order_id) < (...)` fetches rows **following** that last key pair.

### 20.1. Accompanying Index

```sql
CREATE INDEX idx_app_orders_keyset
ON app_fetch_lab.orders (ordered_at DESC, order_id DESC);
```

The lab already has an equivalent `idx_app_orders_recent`; **do not create duplicate indexes in production** just to mirror a lesson snippet. PostgreSQL uses the existing one.

### 20.2. With Filters

Per-customer example:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
WHERE customer_id = 42
  AND (ordered_at, order_id)
      < (TIMESTAMPTZ '2026-02-01 12:00:00+00', 45678)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

The lab's `(customer_id, ordered_at DESC, order_id DESC)` index directly supports this access path.

**Note:** the timestamp/ID above are illustrative. Real code must take cursor keys from the previous page—never hardcode arbitrary markers outside the dataset and assume no more data exists.

### 20.3. Keyset Does Not Freeze a Cross-Request Snapshot

If older rows are deleted or sort keys mutate while paging, results can still change. Keyset avoids offset drift from newly inserted head items, yet does not provide an immutable snapshot across multiple HTTP requests.

## 21. Count Queries: Do You Need `COUNT(*)` on Every Page?

A paginated API often runs:

```sql
SELECT COUNT(*)
FROM app_fetch_lab.orders
WHERE status = 'PAID';
```

alongside the 20-row page query.

These are **two queries serving different purposes**, not N+1. Still, on huge tables `COUNT(*)` must verify MVCC visibility and scan indexes or heap; PostgreSQL cannot return exact snapshot counts in O(1) from table metadata.

### 21.1. When the UI Doesn't Need Total Pages

Fetch `pageSize + 1` rows:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM app_fetch_lab.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 21;
```

When displaying 20 rows, presence of a 21st row tells you a next page exists in that query's snapshot, avoiding an expensive `COUNT(*)`.

### 21.2. When Exact `COUNT` Is Required

If business requirements demand an exact total at a consistent snapshot, compute it or design an explicit counting strategy. Never substitute catalog estimates without documenting semantics clearly.

## 22. JDBC `fetchSize`: Batch Size Hint, Not Total Row Limit

JDBC supports:

```java
preparedStatement.setFetchSize(500);
```

This is a **hint to the driver on how many rows to fetch per round trip**, not equivalent to:

```sql
LIMIT 500
```

If a query matches 2 million rows:

- `LIMIT 500` makes PostgreSQL return at most 500 rows.
- `fetchSize=500` lets the driver stream rows **in batches** instead of buffering everything upfront, yet the application still reads all 2 million rows if it iterates the entire `ResultSet`.

### 22.1. Cursor-Based Fetching in PostgreSQL JDBC

With PgJDBC properly configured, to fetch in batches via a cursor you generally need:

- `autoCommit=false` on the connection.
- A statement compatible with the driver's cursor fetch mode.
- Positive `setFetchSize(n)`.
- Iterating the `ResultSet` while the transaction stays active.

Example:

```java
boolean previousAutoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement("""
        SELECT order_id, ordered_at, total_amount
        FROM app_fetch_lab.orders
        WHERE status = ?
        ORDER BY order_id
        """)) {
    ps.setString(1, "PAID");
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            // Process sequentially; do not collect everything into a huge List.
        }
    }
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(previousAutoCommit);
}
```

This assumes an existing `connection` inside a method handling `SQLException`. Inside managed pools or transaction managers, never toggle `autoCommit` in violation of the framework's contract.

### 22.2. Holding Cursors/Transactions Too Long Is Also Risky

Streaming a `ResultSet` across an hour-long transaction can:

- Tie up a pooled connection and exhaust the pool.
- Hold snapshots open, blocking `VACUUM` pruning.
- Create hard-to-handle backpressure.
- Leave queries hanging when clients read slowly.

For massive exports, consider **keyset-batched** background exports writing incrementally to files/streams outside long-running transactions when requirements allow.

### 22.3. `fetchSize` Does Not Fix `SELECT *`

If a query selects 100 columns when the UI uses 3, batched fetching still reads and sends all 100 columns on every row. Combine **projections** with **batching/pagination**.

## 23. How Streaming and App Limits Differ from SQL Limits

An API may stream rows:

```text
PostgreSQL -> JDBC fetch batches -> app writes HTTP stream incrementally
```

This avoids holding all rows in Java heap simultaneously, yet:

- Does not reduce total rows processed if all rows are read.
- Does not reduce total network traffic between DB and app.
- Can hold the DB connection open throughout streaming.
- Slow or disconnected clients require proper cancellation and cleanup.

**Streaming controls memory footprint**, while `WHERE`, projections, pagination, and business filters control **how much data actually needs to be fetched**.

### 23.1. Paginated APIs Instead of Returning Hundreds of Thousands of Rows per Request

For user-facing endpoints, generally:

- Enforce a max `page_size`.
- Use keyset pagination for deep pages.
- Return only required fields.
- Provide dedicated async export/download endpoints for large datasets.
- Enforce quotas, deadlines, and cancellation.

Never let clients pass `limit=1000000000` unchecked merely because SQL supports `LIMIT`.

## 24. `EXISTS` Instead of Loading a Collection Just to Check Presence

Anti-pattern:

```java
List<OrderItem> items = itemRepository.findByOrderId(orderId);
boolean hasItems = !items.isEmpty();
```

If you only need to know whether an item exists:

```sql
SELECT EXISTS (
    SELECT 1
    FROM app_fetch_lab.order_items
    WHERE order_id = 50000
) AS has_items;
```

PostgreSQL can stop as soon as it finds one qualifying row instead of returning all items.

### 24.1. Use `COUNT` When You Need the Exact Count, Not Just Existence

```sql
SELECT COUNT(*) AS item_count
FROM app_fetch_lab.order_items
WHERE order_id = 50000;
```

`COUNT` returns exact snapshot counts by scanning matching rows/index entries. When a boolean is all business logic needs, `EXISTS` fits better.

### 24.2. Avoid N+1 `COUNT`s

Wrong:

```text
1 SELECT for 20 orders
20 SELECT COUNT(*) WHERE order_id = ?
```

Better: aggregate counts for the selected IDs in one batch:

```sql
SELECT
    order_id,
    COUNT(*) AS item_count
FROM app_fetch_lab.order_items
WHERE order_id = ANY(ARRAY[49998,49999,50000]::bigint[])
GROUP BY order_id;
```

An order with zero items **will not appear in `GROUP BY` output**. When merging in Java, default missing order IDs to count 0.

## 25. Replacing N+1 Aggregates with `GROUP BY` or Well-Scoped Correlated Queries

Suppose a dashboard shows 20 customers with their order counts and totals:

**Wrong pattern:**

```text
SELECT 20 customers
for each customer:
    SELECT COUNT(*), SUM(total_amount)
    FROM orders WHERE customer_id = ?
```

**Single aggregated query:**

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_amount
FROM app_fetch_lab.customers AS c
LEFT JOIN app_fetch_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id BETWEEN 1 AND 20
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Note `COUNT(o.order_id)` instead of `COUNT(*)` with `LEFT JOIN`, because a customer with no orders still emits **one NULL-padded row**, making `COUNT(*)` wrongly return 1.

### 25.1. Avoid Aggregating the Entire Table When Only 20 Customers Are Needed

A query aggregating 50,000 orders for all customers before filtering down to 20 customers does wasteful work. When target customer IDs are known, filter early.

### 25.2. Is a Correlated Subquery N+1?

```sql
SELECT
    c.customer_id,
    (SELECT COUNT(*)
     FROM app_fetch_lab.orders AS o
     WHERE o.customer_id = c.customer_id) AS order_count
FROM app_fetch_lab.customers AS c
WHERE c.customer_id BETWEEN 1 AND 20;
```

This is **one SQL statement**, not 21 network round trips. Still, PostgreSQL may run the subquery multiple times (*SubPlan loops*) depending on the plan. With an index on `customer_id` and few parents it can be fine; with many parents it can get slow.

**Distinguish application-level N+1 from server-side repeated loops.** Inspect `EXPLAIN ANALYZE`, `loops`, and `Buffers` to pick the best query shape.

## 26. Choosing Indexes After Fixing N+1

When an app consolidates 20 queries:

```sql
SELECT * FROM app_fetch_lab.order_items WHERE order_id = ?;
```

into one batch query:

```sql
SELECT order_id, product_code, quantity
FROM app_fetch_lab.order_items
WHERE order_id = ANY(?);
```

an index:

```sql
CREATE INDEX idx_example_items_order
ON app_fetch_lab.order_items(order_id);
```

can be valuable. The lab already has `idx_app_items_order`, so **do not create another index on the same key**.

### 26.1. Indexes for `ORDER BY` and `LIMIT`

A page query:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

aligns with:

```sql
ON app_fetch_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
```

already created in the lab, enabling fast early-stop paging instead of shipping the whole list to Java to sort and slice.

### 26.2. `INCLUDE` / Covering Indexes When Genuinely Helpful

If the screen always fetches `total_amount` alongside the page keys, consider testing:

```sql
CREATE INDEX idx_example_orders_cover
ON app_fetch_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (total_amount);
```

This is a **benchmark suggestion**, not mandatory. Wider indexes consume more space and write effort, and `Index Only Scan` depends on the visibility map. Never stack redundant overlapping indexes without measuring impact.

### 26.3. Consolidated Queries May Need Different Indexes Than Old Queries

A consolidated `JOIN`/`GROUP BY`/batch query has different access patterns from many single-PK lookups. After fixing N+1, **inspect the new SQL's plan** and tune indexes for the new workload instead of assuming old indexes remain optimal.

## 27. `EXPLAIN (ANALYZE, BUFFERS)`: Measuring Individual Queries Is Not Enough for N+1

Measuring one SQL statement:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    customer_name
FROM app_fetch_lab.customers
WHERE customer_id = 781;
```

may show an `Index Scan` taking a fraction of a millisecond. That **does not disprove N+1**, because:

- The application executes that `SELECT` dozens of times per request.
- `EXPLAIN` measures one server execution, excluding repeated network round trips and object mapping.
- Request latency also includes pool checkouts, driver overhead, and serialization.

### 27.1. Measure the Consolidated Query

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM app_fetch_lab.orders AS o
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

Inspect:

- `Seq Scan`, `Index Scan`, `Nested Loop`, or `Hash Join`.
- Estimated `rows` vs `actual rows`.
- `loops` on inner scans.
- `Buffers: shared hit/read`.
- `Execution Time`.

**The consolidated SQL's row count may exceed one individual child query's rows**, while total application latency still drops sharply thanks to fewer round trips.

### 27.2. Check `width` and `Rows Removed`

For overfetching, inspect:

- Estimated `width` per row.
- `actual rows` across nodes.
- `Rows Removed by Filter`.
- `Sort Method` / memory / temp disk if sorting large inputs.

If only 20 rows are needed while the plan processes tens of thousands of rows, see whether filters/limits can push down or indexes can enable early stopping.

### 27.3. `EXPLAIN ANALYZE` Has Overhead

It executes the query and collects timing. Run heavy queries in an appropriate environment. Never blast thousands of `EXPLAIN ANALYZE` calls on production; combine system statistics with sampled tracing.

## 28. `pg_stat_statements`: Spotting Frequently Executed SQL

The `pg_stat_statements` extension aggregates execution metrics across normalized SQL statements.

When properly configured by an admin, inspect:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 20;
```

These view and column names match modern PostgreSQL versions with the extension enabled. If the extension is not enabled/permitted, the query will fail; never edit `shared_preload_libraries` or restart production just for a lab.

### 28.1. What Footprint Does N+1 Leave?

A normalized query:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id = $1
```

often exhibits:

- Very high `calls` relative to HTTP request volume.
- Low `mean_exec_time`.
- Significant `total_exec_time` due to call volume.

This is a **signal**, not standalone proof of N+1—the same PK lookup might legitimately run across many independent requests and users.

### 28.2. Why Doesn't `pg_stat_statements` Know About “One HTTP Request”?

The view aggregates by normalized statement/database/role; it **does not track** `requestId`, user journeys, or which Java loop fired the queries.

To prove N+1, combine it with:

- JDBC/ORM instrumentation.
- Distributed trace spans or request correlation IDs.
- Query count per request.
- SQL templates plus safely redacted bind metadata.
- Endpoint name and primary result list size `N`.

### 28.3. Read Total Runtime and Calls Together

A query with a 0.2 ms mean called 1 million times can dominate workload cost despite fast individual runs. Conversely, a 500 ms query run once a day may matter less than a hot endpoint.

Prioritize by **total load and latency SLOs**, not simply “slowest single query.”

## 29. App Tracing and SQL Logging: Catching Real N+1s

Observability should capture:

```text
HTTP GET /orders?pageSize=20   request_id=abc
  db.query SELECT orders...      1 time
  db.query SELECT customer...   20 times
  mapper/serialization...
```

From there:

1. Count SQL statements per request.
2. Group by SQL template rather than treating distinct IDs as different queries.
3. Compare query count against page size.
4. Attribute queries to controller, service, lazy association, mapper, or serializer.
5. Track latency, row counts, and payload bytes.

### 29.1. Log Bind Parameters Safely

Never log plaintext sensitive parameters (tokens, personal emails, payment cards, customer payloads) just to debug N+1. Instead log:

- SQL fingerprint/template.
- Parameter types.
- Batch ID count.
- Query duration.
- Request correlation ID.
- Row counts and byte estimates.

### 29.2. Sampling and Overhead

Logging every SQL statement with full stack traces in production creates log volume overhead and data risk. Use sampled tracing or time-boxed debug modes compliant with security policies.

### 29.3. Hibernate Statistics

With ORMs, enable session/repository statistics or SQL counters in test/profiling to track:

- Query execution count.
- Entity/collection fetch count.
- Lazy loading triggers.
- Query cache hits/misses if used.

Do not confuse **entity fetch count** with **SQL statement count**: one query can hydrate many entities, and batch fetching changes that ratio.

## 30. Measuring Data Volume: Rows, Columns, and Bytes

Apps should measure more than SQL duration. An endpoint returning 20 items while the DB ships 50,000 rows pays heavy network and GC costs.

### 30.1. Metrics to Distinguish

| Metric | Meaning |
| --- | --- |
| Queries/request | SQL statements emitted |
| Round trips/request | Client–DB network interactions; can differ from queries due to protocol/batching |
| Rows returned from DB | Rows delivered to the driver, including joined rows later collapsed |
| Selected columns | Values actually returned by SQL |
| Estimated row width | Plan's byte/row estimate |
| Network bytes | Actual protocol/payload bytes transferred |
| Application objects allocated | Objects instantiated by mappers |
| API response bytes | HTTP bytes sent to the client |
| Heap allocation / GC | Java memory cost |

### 30.2. Never Use API JSON Size as the Sole Proxy

An ORM can load 50,000 orders and serialize JSON for 20 orders—tiny HTTP response, huge 50,000-row DB payload.

Likewise, an ORM can deduplicate 600 joined rows into 20 parent objects—20 parents in JSON, yet JDBC still read 600 rows.

### 30.3. Rough Data Transfer Estimate

Hypothetical illustration:

```text
100,000 rows × 500 bytes/row ≈ 50 MB raw data
20 rows × 80 bytes/row       ≈ 1.6 KB raw data
```

This rough ratio excludes wire framing, text/binary encoding, null bitmaps, compression, TLS, and object overhead. Actual driver/network bytes vary, yet the ratio explains why overfetching hurts.

## 31. Avoid Selecting Many Rows to Compute in Java When SQL Can Do It

Suppose an app needs only total revenue for `PAID` orders:

**No need to load all orders into Java:**

```sql
SELECT
    COUNT(*) AS paid_orders,
    COALESCE(SUM(total_amount), 0) AS revenue
FROM app_fetch_lab.orders
WHERE status = 'PAID';
```

The database returns **one row** instead of tens of thousands. Still, PostgreSQL must scan/index to compute the sum; shrinking transfer does not reduce server work to zero.

### 31.1. Aggregating by Customer

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM app_fetch_lab.orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY revenue DESC, customer_id
LIMIT 10;
```

Output is at most 10 rows, though computing it may still aggregate many orders. This trades **application-side overfetch for server-side aggregation**; choose indexes and aggregation strategies matching the workload.

### 31.2. Do Not Optimize Away Business Rules

If taxes must be computed via an external service or custom Java logic, you cannot move everything into plain SQL `SUM`. Still filter time ranges, customers, and statuses and select only needed columns before pulling rows out of the DB.

## 32. Database Filtering and Data Access Control

Never load all tenants and filter in Java:

```java
List<Order> all = repository.findAll();
List<Order> tenantOrders = all.stream()
    .filter(o -> o.getTenantId().equals(currentTenant))
    .toList();
```

Beyond massive overfetching, this pulls other tenants' data into app memory, creating security and logging exposure.

Better design:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM tenant_orders
WHERE tenant_id = $1
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

This illustrates a multi-tenant schema not created in the lab.

### 32.1. Indexes Do Not Replace Authorization

Adding `tenant_id` to an index speeds up queries, not security. Enforce authentication, authorization, Row-Level Security where appropriate, and consistent tenant predicates.

### 32.2. Even with `LIMIT ?`, Validate Inputs

Even when SQL uses `LIMIT ?`, never allow clients to request gigantic limits. Validate min/max page sizes against the API contract.

## 33. Memory, GC, and ORM Persistence Context

When an ORM loads hundreds of thousands of entities:

- Every entity carries object header/field overhead.
- Proxies, collection wrappers, and dirty-checking snapshots accumulate.
- The persistence context pins references to all loaded entities for the session.
- Garbage collection works harder, increasing pause times.

Projections and pagination keep memory footprints dramatically smaller than full entity graphs.

### 33.1. When You Genuinely Must Process Huge Volumes

A batch job may have to process an entire dataset. In that case:

1. Chunk by primary key or stable timestamp keyset.
2. Cap columns and rows per batch.
3. Commit/clear the persistence context per framework guidelines.
4. Use idempotency and checkpoints for crash recovery.
5. Avoid holding transactions or DB connections open too long.

Never call `findAll()` and hold millions of entities in memory just because “the job processes everything.”

### 33.2. Cursors and ORM Streams Have Limits Too

An ORM stream may use a `ResultSet` cursor or another mechanism—verify provider behavior. Even with streaming, calling `.collect(toList())` accumulates the entire dataset in memory.

## 34. N+1 in GraphQL and Resolvers

A GraphQL query:

```graphql
query {
  orders(first: 20) {
    id
    customer {
      name
    }
  }
}
```

may invoke the `customer` resolver 20 times. If each invocation queries PostgreSQL, you get N+1.

### 34.1. DataLoader / Batching

Instead of loading customers individually:

```text
load(781)
load(782)
load(783)
...
```

a batch loader collects IDs within the request:

```sql
SELECT customer_id, customer_name
FROM app_fetch_lab.customers
WHERE customer_id = ANY(?);
```

and maps results back in the exact order of requested keys.

### 34.2. Keep Cache Scope Properly Isolated

DataLoader caches should be scoped per **request/user/security context**. Never build a global cross-tenant cache lacking authorization checks and invalidation.

### 34.3. Can GraphQL Still Overfetch?

Yes. Even if the GraphQL client requests only `customer.name`, a backend resolver might still call `findAll()` or `SELECT *` and load full associations. Client field selection **does not automatically make the database read only those fields**; resolvers must use matching projections and fetch plans.

## 35. Caching: Reducing N+1 or Hiding It?

Caching customers by ID can keep some lookups off the DB:

```text
request: 20 orders
lookup customer #1 -> cache hit
lookup customer #2 -> cache miss -> SQL
...
```

Yet on cold caches, N+1 reappears. Never treat “p95 looks fine while cache is warm” as proof of an efficient data-access design.

### 35.1. Caching Risks

- Stale cache invalidation when a customer renames.
- Memory consumption and eviction churn.
- Cache stampedes on simultaneous misses.
- Stale reads when strong consistency is required.
- Tenant/permission scoping in cache keys.

Caching is useful when justified, **not a substitute for reducing round trips in data access**.

### 35.2. Query Caching Does Not Merge Relationships

ORM query caches, entity caches, and JDBC statement caches are distinct mechanisms. A cached prepared statement does not turn 20 `EXECUTE` calls into a single batch query.

## 36. Batch Size: Sizing to Data and Practical Limits

Suppose you need customers for 10,000 orders. You shouldn't necessarily pass 10,000 IDs at once if:

- Parameter/array payloads grow huge.
- Planning time and memory spike.
- Result rows are wide.
- Connection/transaction timeouts are tight.
- The app prefers smaller incremental batches.

Splitting IDs into chunks like 200–1,000 often works well, though **there is no universal magic number**.

### 36.1. Don't Issue 10,000 Single-ID Queries

Batching pattern:

```text
uniqueCustomerIds = distinct(ids)
for each chunk of B IDs:
    SELECT ... WHERE id = ANY(chunk)
merge results into map
```

Query count is roughly `ceil(U/B)` where `U` is unique ID count, plus the orders query.

### 36.2. Do Not Grow Batch Size Indefinitely

Giant batches cause high time-to-first-byte, memory spikes, and timeout risks. If an endpoint only displays 20 orders, **not loading 10,000 orders upfront** matters far more than tuning batch fetch for 10,000 customers.

## 37. Consistency When Splitting One `JOIN` into Two Queries

A single `JOIN` runs within **one statement snapshot** under MVCC. Splitting into:

1. `SELECT` order page.
2. `SELECT` customers/items by IDs.

means two statements under `READ COMMITTED` can see **different committed states** if a concurrent transaction commits in between.

### 37.1. Example State Change Between Queries

```text
T1: SELECT orders (returns customer_id=42)
T2: UPDATE customer_name of #42; COMMIT
T1: SELECT customers WHERE id=42 (sees new name)
```

This is not automatically a bug; many UIs accept reading the latest committed state per statement. Financial reports or snapshot exports may require stronger consistency.

### 37.2. Choosing a Strategy

- **Single `JOIN` statement:** all joined tables share that statement's snapshot.
- **`REPEATABLE READ` transaction:** shares one snapshot across multiple `SELECT`s in the same short transaction, weighing PostgreSQL trade-offs.
- **Read model / denormalization:** for ultra-stable, high-traffic endpoints, maintain materialized projections updated per workflow.

Never hold a read transaction open for tens of minutes just to avoid a minor customer-name mismatch; long transactions hurt `VACUUM` and resources.

### 37.3. Authorization Between Both Steps

Parent IDs retrieved in step 1 must belong to the caller's authorized scope. Child batch queries in step 2 must also ensure they never leak out-of-scope parent data, especially if IDs can arrive from clients.

## 38. Query Timeouts and Cancellation

An N+1 endpoint must not be “fixed” by raising timeouts indefinitely. Still, bounding statements limits blast radius:

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';

SELECT order_id, total_amount
FROM app_fetch_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC
LIMIT 20;

COMMIT;
```

`5s` here is illustrative; pick thresholds matching your SLAs and workload.

### 38.1. Per-Query Timeout Differs from Request Timeout

If an app fires 100 queries each finishing under 5 seconds, the total request can still take minutes. `statement_timeout` bounds each PostgreSQL statement, **not the cumulative budget of all queries in a request**.

Combine request-level timeouts, cancellation, and query-count metrics.

### 38.2. Do Not Keep Querying After Client Cancellation

Applications should close `ResultSet`/`Statement` handles, cancel active work, and release connections when the HTTP client disconnects. Never let a canceled export keep streaming millions of rows pointlessly.

## 39. When Is One Larger Query Better Than Multiple Small Queries?

**Usually better** when:

- The relationship is many-to-one.
- Output is a small page with a narrow projection.
- Join cardinality is tightly bounded.
- SQL can filter and sort early.
- Indexes and statistics support it.

**Often worse** when:

- Joining multiple one-to-many collections triggers huge row combinations.
- One side carries wide `TEXT`/`JSONB` fields repeated across joined rows.
- A monolithic query forces sorting/aggregating huge intermediate datasets.
- Each collection needs independent pagination or top-K slicing.
- Different data domains enforce separate security/snapshot boundaries.

A **2–4 batch-query** strategy over a bounded parent page is often the pragmatic sweet spot.

### 39.1. Don't Count Queries While Ignoring Bytes

Compare two options:

```text
Option A:
  1 SQL
  200,000 joined rows
  parent fields repeated extensively

Option B:
  3 SQLs
  100 parent rows
  300 item rows
  150 shipment rows
```

Option B can easily outperform Option A despite having 3× as many SQL statements. Measure end-to-end instead of optimizing blindly for `query count = 1`.

## 40. Step-by-Step Workflow to Fix N+1 on an Endpoint

Practical workflow:

1. **Reproduce the exact request** with realistic page size and data.
2. **Record query count**, SQL templates, and total request latency.
3. **Spot repeated queries by ID** (customers, items, statuses, counts, etc.).
4. **Trace the trigger**: controller, service, lazy association, mapper, or serializer.
5. **Define what the screen actually needs**: how many parents/children and which columns.
6. **Limit the parent page in SQL**, never loading the whole table.
7. **Pick the relation-fetching strategy**: `JOIN` for many-to-one; batch fetching or paged CTE + `JOIN` for one-to-many.
8. **Verify cardinality**: 1:1, N:1, or 1:N, and whether multiple collections exist.
9. **Avoid `JOIN`s that break pagination or inflate aggregates**.
10. **Use DTO projections** and drop unneeded columns/payloads.
11. **Measure the consolidated query** with `EXPLAIN (ANALYZE, BUFFERS)` and row counts.
12. **Evaluate indexes** for the new `WHERE`/`JOIN`/`ORDER BY` patterns.
13. **Re-measure app latency**, query count, rows/bytes, memory/GC, and throughput.
14. **Verify correctness**: sort order, parents without children, totals, tenant isolation, snapshots.
15. **Add regression tests** so N+1 cannot silently return.

## 41. Testing Against N+1 Regressions

A test checking only HTTP 200 and JSON payload is insufficient—the endpoint could pass while issuing 101 SQL statements per page.

### 41.1. Query-Count Test Pattern

```text
Arrange:
  seed 50 orders with matching customers and items
  reset request-scoped query counter

Act:
  call GET /orders?limit=20

Assert:
  response has exact 20 orders with accurate customer names/items
  SQL statement count does not scale linearly with page size
```

You don't have to assert strictly **1 query**. If the design uses 1 parent page + 1 batch items + 1 batch customers, asserting **<= 3 queries** is a sound contract.

### 41.2. Test Multiple Page Sizes

Run the same endpoint with `N = 1, 10, 20, 50`:

| N | N+1 Pattern | 2-Query Batch Pattern |
| ---: | ---: | ---: |
| 1 | 2 | 2 |
| 10 | 11 | 2 |
| 20 | 21 | 2 |
| 50 | 51 | 2 |

This table is idealized assuming each parent triggers one DB lookup and batching fits in one query. ORM caches, distinct customer counts, multiple collections, or chunked batch sizes alter exact numbers—test with representative data.

### 41.3. Overfetch Tests

Beyond query count:

- Verify queries fetch the expected page size (aside from bounded `JOIN` rows).
- Ensure no `SELECT *` when endpoints need only a few columns.
- Ensure collections aren't loaded just for `COUNT`/`EXISTS`.
- Seed wide item data and multi-child parents to test row multiplication.
- Test memory and runtime on larger datasets.

### 41.4. Ensure Caches Don't Mask N+1 in Tests

An ORM session holding warm entities can let an N+1 test pass artificially. Set up data cleanly, clear the persistence context, or isolate caches so you observe cold-cache DB queries.

## 42. Benchmarking an N+1 Fix Properly

**Before fix:**

```text
Request: GET /orders?limit=50
SQL:     1 order query + 50 customer queries
Rows:    50 orders + 50 customer rows
Mapping: 50 orders + 50 customers
```

**After fix with `JOIN`:**

```text
Request: GET /orders?limit=50
SQL:     1 join query
Rows:    50 joined rows (many-to-one)
Mapping: 50 DTOs
```

Expected result is fewer round trips, yet **measure**:

- P50/P95/P99 request latency.
- SQL count per request.
- DB execution time, CPU, and buffers.
- Rows and bytes returned from DB.
- Connection pool wait time.
- JVM allocations and GC.
- Concurrent load and throughput.

### 42.1. Benchmark in a Representative Environment

A 50,000-order lab explains mechanics, yet does not prove production latency under:

- Hundreds of millions of records.
- Skewed customer distributions.
- Orders with thousands of items.
- Cross-AZ/region network latency.
- Pool saturation and CPU/I/O contention.
- Different `VACUUM`, bloat, and statistics states.

Measure in a representative staging/profiling environment and roll out with monitoring.

### 42.2. Check Regression Risks Too

When changing fetch strategies:

- Are any orders missing?
- Are orders or items duplicated?
- Did `JOIN` fan-out inflate monetary totals?
- Did isolation semantics weaken or shift?
- Could another tenant's data leak?
- Could one giant query overload the database?

Faster runtime with wrong data is never a successful optimization.

## 43. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Each SQL takes 0.5 ms so it can't be N+1 | Hundreds of round trips and mappings still add major latency |
| N+1 only happens with SQL inside a `for` loop | Lazy ORMs, mappers, serializers, and GraphQL resolvers trigger it too |
| Making every association `EAGER` cures N+1 | Causes overfetching and hard-to-control SQL |
| Joining all collections into one query is always fast | Multiplies rows and breaks pagination |
| `LEFT JOIN ... LIMIT 20` means 20 parent rows | `LIMIT` caps joined result rows |
| `DISTINCT` fixes any Cartesian join | May fail to deduplicate meaningfully and adds heavy sorting |
| Batch fetching needs no parent limit | Huge ID batches are still overfetching |
| `WHERE id IN (...)` returns rows in input ID order | Without `ORDER BY`, output order is never guaranteed |
| `fetchSize=500` caps SQL output at 500 rows | `fetchSize` is a batch hint, not `LIMIT` |
| Streaming `ResultSet` means DB sends less data | Iterating to the end still transfers every row |
| Using `SELECT *` and dropping fields in the serializer is fine | Wide columns were already read and sent by DB |
| `.limit(20)` in Java Stream makes DB read less | Java limit runs after DB already sent all rows |
| Low query count guarantees high performance | One `JOIN` can emit millions of rows |
| Small HTTP JSON means small DB payload | ORM may load massive rows before trimming |
| `COUNT(*)` is O(1) metadata in PostgreSQL | Exact counts incur MVCC visibility/scan cost |
| `EXISTS` and `COUNT(*)` are identical for boolean checks | `EXISTS` can stop at the first match |
| One consolidated query has no repeated inner work | Correlated subqueries / `LATERAL` can still loop N times |
| Child FK columns are indexed automatically | PostgreSQL does not auto-index referencing FK columns |
| Warm-cache speed proves no N+1 | Cold caches expose the problem again |
| `pg_stat_statements` directly identifies N+1 requests | Requires request tracing and per-request query counts |
| One `JOIN` and two batch queries share the same snapshot | Separate statements under `READ COMMITTED` see different commits |
| Keyset gives an eternal immutable snapshot | It does not stop concurrent deletes or updates |
| Raising pool size or timeout fixes N+1 | Can overload DB without cutting redundant queries |
| Improving `EXPLAIN` for one query finishes the job | Measure full request latency, DB bytes, rows, and mapping |

## 44. PostgreSQL and Java Practice Exercises

SQL exercises use schema `app_fetch_lab`. For Java/JPA exercises, write pseudocode or use a practice project with matching drivers and entity mappings.

1. **Concept:** explain N+1 in an endpoint returning 50 orders with customer names, stating the idealized SQL count.
2. **Counting queries:** if a page has 30 orders and each triggers 1 customer `SELECT`, count total queries; if each also triggers an item `SELECT`, how does the total grow?
3. **Lab data:** create `customers`, `orders`, and `order_items` and populate them per the script.
4. **Many-to-one N+1:** write the `SELECT` for 20 orders plus the per-ID customer `SELECT`; identify which step loops in Java.
5. **`JOIN`:** write one SQL fetching 20 orders with `customer_name` without N extra queries.
6. **Cardinality:** why does a many-to-one `JOIN` not multiply order rows when FKs are valid and `customer_id` is unique?
7. **`EXPLAIN`:** inspect the `JOIN` with `EXPLAIN (ANALYZE, BUFFERS)`; note `Index Scan`/`Hash Join`/`Nested Loop` and `loops`.
8. **Batch IDs:** use `WHERE customer_id = ANY(ARRAY[...]::integer[])` to fetch multiple customers at once.
9. **Distinct IDs:** why deduplicate customer IDs before batch fetching?
10. **Ordering:** why does `IN`/`ANY` without `ORDER BY` not guarantee input ID ordering?
11. **DTO map:** write Java pseudocode using `Map<Integer,CustomerDto>` to stitch orders and customers.
12. **One-to-many:** write the N+1 pattern for fetching items of 20 orders, then replace it with a batched `SELECT` by order IDs.
13. **`LIMIT` after `JOIN`:** run a `JOIN` of `orders`/`order_items` with `LIMIT 20`. Why aren't 20 orders guaranteed?
14. **Parent page CTE:** select 20 orders in a CTE first and then join items; compare parent count vs joined row count.
15. **Missing children:** ensure an order with zero items still appears in results with an empty item list.
16. **`JOIN` fan-out:** if one order has 3 items, 4 shipments, and 5 payments, how many rows can a 3-way `JOIN` emit?
17. **Multiple collections:** propose a 1 parent page + 3 batch-query strategy and explain why it can beat a single `JOIN`.
18. **JSON aggregation:** use `jsonb_agg + FILTER + COALESCE` to pack items of 20 orders into one JSON column per order.
19. **`LATERAL`:** write a query fetching top 2 items per order, inspect `loops` on the inner node, and explain why one SQL can still repeat work.
20. **Aggregated counts:** replace 20 per-order `SELECT COUNT(*)` queries with one `GROUP BY order_id` over page IDs.
21. **`COUNT(*) LEFT JOIN`:** why can `COUNT(*)` return 1 for a customer with no orders? Fix with `COUNT(o.order_id)`.
22. **`EXISTS`:** write a query checking whether order 50000 has items without loading the collection.
23. **Projection:** compare `SELECT *` against `SELECT order_id, ordered_at, total_amount` and inspect `width` in `EXPLAIN`.
24. **TOAST:** why can selecting unused wide `note`/`extra_data` columns bloat data transfer?
25. **DB filtering:** replace Java `findAll().filter(PAID)` with SQL `WHERE status='PAID'`.
26. **Pagination:** write `LIMIT 20 OFFSET 20` with a two-column `ORDER BY`; explain the tie-breaker's role.
27. **Deep offset:** measure `OFFSET 40000 LIMIT 20` and compare against page 1.
28. **Keyset:** write the next-page query using `(ordered_at,order_id)<(cursorTime,cursorId)`.
29. **Index:** explain how `(customer_id,ordered_at DESC,order_id DESC)` accelerates a single customer's order list.
30. **Total count:** when the UI only needs “is there a next page?”, use `LIMIT pageSize+1` and explain the trade-offs.
31. **Fetch size:** distinguish JDBC `setFetchSize(500)` from SQL `LIMIT 500`.
32. **PgJDBC streaming:** sketch batched `ResultSet` fetching with `autoCommit=false` and proper transaction cleanup.
33. **GC:** why can loading 100,000 ORM entities create heavy heap/GC pressure even if the final JSON response is small?
34. **Lazy loading:** identify where `order.getCustomer().getName()` can trigger unintended SQL.
35. **`EAGER`:** why is switching all associations to eager not a universal fix?
36. **`JOIN FETCH`:** explain the difference between fetch-joining many-to-one vs a paginated one-to-many collection.
37. **DTO:** write a JPQL constructor projection for `OrderSummaryDto`.
38. **Batch size:** with 2,300 distinct IDs and batch size 500, estimate how many batch queries run.
39. **GraphQL:** use a DataLoader to merge 20 customer resolver calls into one batch query; why must loader caches be request-scoped?
40. **Cold cache:** write a test verifying query count does not grow linearly when the ORM cache is cold.
41. **`pg_stat_statements`:** locate a query with high `calls` and low `mean_exec_time`; why isn't that conclusive proof of N+1?
42. **Tracing:** propose safe fields (`request_id`, query template, duration, `row_count`) without logging sensitive values.
43. **Rows vs API objects:** explain why an ORM returning 20 `Order` objects may have read 60 joined rows.
44. **Consistency:** how can two batch queries under `READ COMMITTED` see two different snapshots?
45. **Timeout:** why doesn't `statement_timeout = '5s'` guarantee a 100-SQL request finishes under 5 seconds?
46. **Regression test:** test `N=1,10,20,50` and tabulate query counts before vs after batch fetching.
47. **Benchmark:** measure before/after P95 latency, SQL count, rows/bytes, `BUFFERS`, pool wait, and JVM allocations.
48. **Multi-tenant security:** explain why loading all tenants and filtering in Java is wrong; propose `WHERE tenant_id` plus proper authorization.
49. **Fix aggregate endpoint:** return Top 10 customers by revenue; replace loading all orders with `GROUP BY + ORDER BY + LIMIT`.
50. **Full design:** architect `GET /orders?limit=20` returning `customerName`, `itemCount`, and the first three items; choose queries, keys/columns, paging strategy, and explicit child caps.

## 45. Endpoint PostgreSQL Access Review Checklist

Before approving a PR adding an endpoint or modifying ORM mappings, ask:

1. How many **SQL statements** does the endpoint emit for `N = 1, 20, 100`?
2. Are any query templates repeating per parent ID?
3. Do mappers or serializers trigger lazy loading?
4. Can many-to-one associations use `JOIN`?
5. Are one-to-many associations batch-fetched by parent IDs?
6. Are collection `JOIN FETCH` + pagination causing memory paging or overfetching?
7. Are multiple collections joined together causing row multiplication?
8. Does the parent query apply an explicit `LIMIT` inside PostgreSQL?
9. Does `ORDER BY` have a unique tie-breaker?
10. Should deep pages use keyset instead of `OFFSET`?
11. Are `SELECT *` or full entities loaded when only a few fields are needed?
12. Are full collections loaded just for `COUNT`/`EXISTS`?
13. Are wide `TEXT`/`JSONB` columns actually needed in the response?
14. Are JDBC `fetchSize`/streaming confused with row limits?
15. Are cursors and transactions held open too long?
16. Do indexes support the consolidated query's `WHERE`/`JOIN`/`ORDER BY`?
17. Does `EXPLAIN (ANALYZE, BUFFERS)` show unexpected `loops`, rows, or temp I/O?
18. Are **rows and bytes** from the database measured rather than only JSON response size?
19. Are cross-query snapshot discrepancies acceptable if split across statements?
20. Are tenant/authorization scopes enforced during batch fetches?
21. Are there regression tests with cold caches and distinct parents?
22. Were latency, throughput, and memory re-measured on representative data?

## 46. Summary

These two performance bugs can appear independently or together:

```text
N+1 QUERIES
  1 query fetching parent list
  N queries fetching related data per parent
  -> excessive round trips, overhead, and pool pressure

Fix:
  JOIN for many-to-one
  batch-fetch IDs for one-to-many
  group aggregates / EXISTS when only counts or booleans are needed
  monitor actual per-request query counts

OVERFETCHING
  SELECT * / findAll()
  filter + sort + limit in Java
  joining multiple collections causing row multiplication
  -> rising network bytes, mapping cost, heap memory, and GC

Fix:
  WHERE, ORDER BY, LIMIT, keyset inside PostgreSQL
  DTO projections selecting only needed columns
  paginate parents before joining children
  batch/stream fetches for genuinely large processing
  measure rows/width/bytes, not only SQL count
```

Core principles:

- **N+1 is an application–database interaction problem**, invisible in a single isolated `EXPLAIN` plan. A tiny query called hundreds of times per request still makes endpoints slow.
- **Fixing N+1 does not mean forcing every endpoint into one SQL statement.** A clean `JOIN` fits many-to-one; two or a few batch queries often beat multi-collection one-to-many joins.
- **Paginate parents before joining children.** `LIMIT` after a `JOIN` caps joined rows, not displayed parent entities.
- **Prevent overfetching in SQL:** select only needed columns, fetch only needed rows, filter/sort early in PostgreSQL, and choose suitable pagination.
- **JDBC `fetchSize`/streaming are not `LIMIT`.** They control how rows are buffered and consumed in the app, without reducing total rows processed when reading to completion.
- **Use `EXPLAIN` for individual SQLs and tracing/`pg_stat_statements` for workload frequency and total cost.** Track queries/request, total rows, network bytes, server buffers, JVM memory, and P95/P99 latency.
- **Never trade correctness for speed:** avoid duplicate rows, wrong `COUNT`/`SUM`s, missing items, unstable pages, tenant leaks, and unacceptable snapshot drift.
- **Add N+1 and overfetch tests on representative data** so regressions cannot slip back in via mapper, ORM association, or serializer edits.

In short, a well-designed query **fetches only the necessary data, in a bounded number of round trips, with controlled row/column scope and relationship cardinality**. Combining clean SQL design, disciplined Java data access, and real measurement lets PostgreSQL serve endpoints faster without drowning in redundant queries or excess data.
