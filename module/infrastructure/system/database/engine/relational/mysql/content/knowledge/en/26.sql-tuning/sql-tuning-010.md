# Avoiding N+1, Repeated Queries, and Excessive Network Round-Trips

An endpoint may return only a few dozen orders yet send hundreds of SQL statements to MySQL. A common cause is the application loading a list of parent records in one query, then executing another query per record to fetch related data. This pattern is called the **N+1 query problem**: one initial query plus N repeated queries.

N+1 does more than inflate query count. Each database call incurs request serialization, network latency, parse/execute overhead, result fetching, and application deserialization. Under concurrent traffic, repeated small queries hold connection pool slots longer, increase server load, and extend transaction lifetimes. Remedies typically involve `JOIN`, batch loading with `IN`, aggregate queries, scoped caching, or batched writes.

## Objectives

After this lesson, you will be able to:

- Recognize N+1 and repeated query patterns in ORMs or service layers.
- Choose between `JOIN`, batch loading, and aggregate queries based on data shape.
- Avoid pagination bugs when joining one-to-many relationships.
- Reduce round-trips for both multi-record reads and writes.
- Use appropriately sized batches, prepared statements, and matching indexes.
- Measure query count, rows examined, payload size, and request latency.
- Preserve consistency when replacing a single large query with multiple batched queries.

The examples assume MySQL 8.0, InnoDB, and applications using prepared statements. Parameter binding method names vary across drivers and ORMs.

## 1. What Is the N+1 Query Problem?

Suppose the system has two tables:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    KEY ix_orders_customer_created
        (customer_id, created_at, order_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    KEY ix_order_items_order (order_id)
) ENGINE = InnoDB;
```

The application needs to display the 50 most recent orders along with each order's line items. A naive implementation:

```sql
-- Query 1: fetch 50 orders.
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;

-- For each order_id, the application runs:
SELECT item_id, product_id, quantity, unit_price
FROM order_items
WHERE order_id = ?;
```

With 50 orders, the application sends 51 queries total: one parent query and 50 child queries. If each child query takes an average of 3 ms round-trip time, sequential waiting alone takes roughly 150 ms, before counting SQL execution and data transfer. As N grows, overhead scales nearly linearly.

ORM code often hides this pattern behind lazy loading:

```text
orders = queryOrders(customerId, limit=50)  // 1 query
for order in orders:
    order.items                         // 1 query per order
```

Notably, simply accessing `order.items` looks innocent yet triggers a new database query. N+1 also occurs when iterating over customers to load addresses, products to load categories, or individual records to count related events.

## 2. Why Are Many Round-Trips Expensive?

Every database query has multiple cost components:

1. The application prepares the statement and parameters.
2. The request travels through driver, socket, and network to MySQL.
3. The server parses/executes or reuses a prepared statement, accessing index/data pages.
4. Results are sent back to the client and decoded by the driver.
5. The application hydrates objects and continues processing.

Many repeated small queries multiply all of these steps. Even when each `SELECT` reads a single row and runs quickly, total latency climbs due to network waiting and per-call fixed overhead.

N+1 can also cause:

- **Prolonged connection pool occupancy:** requests hold connections while waiting for sequential queries.
- **Higher server load:** repeated executions, lookups, Performance Schema instrumentation, and result serialization.
- **Unpredictable consistency:** separate queries may observe data at different points in time depending on transaction isolation.
- **Longer transactions:** if all queries share one transaction, that transaction holds snapshots or locks longer.
- **Redundant payloads:** the application may fetch the same related object multiple times.

Simply minimizing query count is not always better. One massive SQL statement returning millions of rows can cost more than a few small batched queries. The goal is reducing round-trips while keeping rows read, bytes returned, and processing cost under control.

## 3. Approach 1: Use JOIN to Fetch Related Data

With a one-order-to-many-items relationship, data can be fetched in a single statement:

```sql
SELECT o.order_id,
       o.created_at,
       o.status,
       o.total_amount,
       i.item_id,
       i.product_id,
       i.quantity,
       i.unit_price
FROM orders AS o
LEFT JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.customer_id = 42
ORDER BY o.created_at DESC,
         o.order_id DESC,
         i.item_id;
```

The application receives a single result set. Order columns repeat on every line-item row, so the mapping layer groups rows by `order_id` to reconstruct the parent object and child list.

Index `ix_orders_customer_created` supports filtering and sorting orders by customer; `ix_order_items_order` supports looking up line items by `order_id`. Verify the plan with `EXPLAIN` on near-production data.

### When Does JOIN Fit?

- Related data is needed immediately in the same screen or report.
- Post-join row count stays bounded and manageable.
- Relationships and join conditions are clear with supporting indexes.
- You want a single `SELECT` reading from one consistent snapshot.

### Watch Out for Parent Row Duplication

In a one-to-many relationship, each order appears once per `order_items` row. If an order has 5 items, its `total_amount` column also appears 5 times. Summing after a join can accidentally double-count parent values.

The following example easily produces wrong results:

```sql
SELECT o.customer_id,
       SUM(o.total_amount) AS customer_total
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

Each order is repeated by its line-item count, multiplying `SUM(o.total_amount)`. If you only need order totals, query `orders` directly. If you need aggregates at both levels, aggregate each table first before joining or run separate queries.

## 4. Avoid Pagination Bugs in One-to-Many JOINs

Never put `LIMIT 50` directly on a joined result when the intent is fetching 50 orders. `LIMIT` caps 50 post-join rows, not 50 orders. One order with many items can consume most of the limit and omit other orders.

Paginate the parent set first, then join details:

```sql
WITH page_orders AS (
    SELECT order_id, customer_id, created_at, status, total_amount
    FROM orders
    WHERE customer_id = 42
    ORDER BY created_at DESC, order_id DESC
    LIMIT 50
)
SELECT p.order_id,
       p.created_at,
       p.status,
       p.total_amount,
       i.item_id,
       i.product_id,
       i.quantity,
       i.unit_price
FROM page_orders AS p
LEFT JOIN order_items AS i
  ON i.order_id = p.order_id
ORDER BY p.created_at DESC,
         p.order_id DESC,
         i.item_id;
```

The `page_orders` CTE selects exactly 50 orders before joining. Afterward, all line items for those 50 orders are returned. Note that the final row count can exceed 50; the application should enforce reasonable item bounds or batch if a single order can hold huge item counts.

Pagination ordering needs a unique tie-breaker column at the end of `ORDER BY`—here `order_id`—to prevent unstable ordering when multiple orders share the same `created_at`.

## 5. Approach 2: Batch Loading with IN

Another option is running one query for the parent list and one query fetching all children for those parents:

```sql
-- Query 1: fetch a page of orders.
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 50;

-- Query 2: fetch line items for all orders on the page.
SELECT order_id, item_id, product_id, quantity, unit_price
FROM order_items
WHERE order_id IN (?, ?, ?, ...)
ORDER BY order_id, item_id;
```

The application collects the 50 `order_id` values, builds placeholders, and binds each value via a prepared statement. It then groups items by `order_id` in memory. Total queries remain two regardless of whether the page contains 5 or 50 orders.

### Why Is IN Usually Better Than N+1?

`IN` lets a single statement look up rows belonging to multiple keys. With an index on `order_items(order_id)`, MySQL can probe the corresponding index ranges. The driver sends one request and receives items for many orders in one round-trip.

Never interpolate ID values directly into SQL strings. Generate `?` placeholders matching the ID count and bind parameters to avoid SQL injection and escaping bugs. Many ORMs offer `select-in loading`, `prefetch_related`, `include`, or similar batch loader features.

### Split Into Chunks When the List Is Too Large

Do not build an unbounded `IN` list. Huge batches produce long SQL text, higher parse cost, excessive placeholders, and oversized single-shot responses. Split into measured chunks, such as 200–1000 keys depending on row width, latency, driver, and server load.

```text
orderIds = [ ... 5000 IDs ... ]
for each chunk of 500 IDs:
    query order_items WHERE order_id IN (chunk)
    append/group results
```

A chunk size of 500 is just a starting point for benchmarking, not a fixed MySQL limit. Measure p95 latency, payload size, row count, and application processing time.

When batching tens or hundreds of thousands of keys, consider loading keys into a temporary or staging table and joining:

```sql
CREATE TEMPORARY TABLE requested_orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

INSERT INTO requested_orders (order_id)
VALUES (1001), (1002), (1003);

SELECT i.order_id, i.item_id, i.product_id, i.quantity
FROM requested_orders AS r
JOIN order_items AS i
  ON i.order_id = r.order_id
ORDER BY i.order_id, i.item_id;
```

Temporary tables are session-scoped, so creating, populating, and joining must run on the same connection. With connection pools, ensure temporary tables are dropped before returning connections to the pool, or use unique names and safe cleanup routines.

## 6. Approach 3: Aggregate Multiple Records in One Query

N+1 patterns often run per-parent subqueries solely to count or sum child rows. Instead of running `COUNT(*)` N times, group once:

```sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_spent,
       MAX(created_at) AS latest_order_at
FROM orders
WHERE customer_id IN (?, ?, ?, ...)
GROUP BY customer_id;
```

If you need item counts per order:

```sql
SELECT order_id,
       COUNT(*) AS item_count,
       SUM(quantity) AS total_quantity
FROM order_items
WHERE order_id IN (?, ?, ?, ...)
GROUP BY order_id;
```

Results have at most one row per grouping key. The application maps results onto parent objects; if a key has no result row, assign an appropriate default such as 0.

Avoid mechanically using correlated subqueries to fix N+1. The optimizer can transform some subqueries, yet you must verify `EXPLAIN` and actual row counts. An explicit `GROUP BY` query usually makes aggregation intent clear to both readers and the optimizer.

## 7. Approach 4: Batch Multi-Row Writes and Updates

N+1 does not happen only on reads. Applications sometimes execute one `INSERT` per row:

```sql
INSERT INTO order_items
    (item_id, order_id, product_id, quantity, unit_price)
VALUES (1, 7001, 10, 2, 15.00);

INSERT INTO order_items
    (item_id, order_id, product_id, quantity, unit_price)
VALUES (2, 7001, 11, 1, 25.00);
```

For multiple rows, use multi-row inserts:

```sql
INSERT INTO order_items
    (item_id, order_id, product_id, quantity, unit_price)
VALUES
    (?, ?, ?, ?, ?),
    (?, ?, ?, ?, ?),
    (?, ?, ?, ?, ?);
```

Batch inserts reduce round-trips and execution overhead. Chunk batches if payloads are large or transactions hold too many locks. Ensure duplicate-key errors and affected row counts follow business rules.

To update multiple rows with differing values, use a staging table and join:

```sql
CREATE TEMPORARY TABLE inventory_changes (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    quantity_delta INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory_changes (product_id, quantity_delta)
VALUES (10, -2), (11, 5), (12, -1);

UPDATE inventory AS i
JOIN inventory_changes AS c
  ON c.product_id = i.product_id
SET i.available = i.available + c.quantity_delta;
```

If non-negative inventory must be enforced, add the proper guard condition and check affected row counts; never run batch updates while bypassing data invariants. Staging and update statements must run within an appropriate transaction on the same connection.

## 8. DataLoader and Per-Request Caching

In GraphQL or service layers, multiple resolvers may request the same kind of data. The **DataLoader pattern** collects keys requested during an execution tick into one batch, queries once, and distributes results back to each resolver.

Conceptual flow:

```text
Resolver A requests items(order 1) ---+
Resolver B requests items(order 2) ---+--> Batch loader
Resolver C requests items(order 3) ---+         |
                                                v
                                    SELECT ... WHERE order_id IN (...)
                                                |
                                                v
                                  Map results by order_id
                                                |
                     +--------------------------+------------------+
                     v                          v                  v
                  Resolver A                Resolver B          Resolver C
```

DataLoader typically includes a per-request cache so if multiple resolvers request the same key, data is loaded only once. Per-request caches are short-lived and easier to reason about than global caches. Long-lived caches require explicit invalidation, TTLs, and stale-data handling.

Caching does not replace batch loading across distinct keys. Also avoid caching sensitive or fast-changing data without clear access control and freshness guarantees.

## 9. Consistency When Splitting One Query Into Multiple Batches

A single `SELECT` join reads data within one statement snapshot. When replaced by two or more batched queries, data can change between reads.

For example, the first query fetches the order list; before the second query fetches `order_items`, another transaction inserts or deletes an item. The assembled result in the application may reflect two different points in time.

If business logic demands a consistent snapshot, run the read queries inside a single InnoDB transaction at `REPEATABLE READ`:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;

SELECT order_id, item_id, product_id, quantity, unit_price
FROM order_items
WHERE order_id IN (?, ?, ?, ...)
ORDER BY order_id, item_id;

COMMIT;
```

Both ordinary `SELECT` statements share the same read view. Keep the transaction short; never wait for user input or make external HTTP calls while holding the transaction open. If business logic does not require a unified snapshot, accept near-real-time consistency and avoid long transactions.

Under `READ COMMITTED`, each consistent read takes a fresh snapshot, so two statements in the same transaction can see different commits. Choose isolation levels based on business requirements, not merely to lower query counts.

`SET SESSION TRANSACTION ISOLATION LEVEL` alters the current connection's setting. When using connection pools and changing isolation per request, restore the standard setting before returning the connection to the pool or manage isolation centrally in pool configuration.

## 10. Choosing JOIN, Batch, or Aggregation?

| Scenario | Usually suitable strategy | Notes |
|---|---|---|
| One-to-one or many-to-one relation | `JOIN` | Avoid re-fetching the same related record |
| One parent page with many child rows | Batch `IN` or join after parent pagination | Bound child row count and payload |
| Counts/sums across multiple parent keys | `GROUP BY` with `IN` or join | Avoid double-counting from one-to-many joins |
| Inserting many identically structured rows | Multi-row `INSERT` | Chunk batches and handle per-batch errors |
| Updating multiple keys with distinct values | Staging table + `UPDATE JOIN` | Protect invariants and transactions |
| Multiple resolvers requesting the same data type | DataLoader/batch loader | Scope cache to the request |
| Very large input key list | Temporary/staging table + join | Same session and explicit cleanup |

No single strategy fits every case. `JOIN` minimizes round-trips but can repeat parent columns; `IN` batching maps objects cleanly yet requires more than one statement; aggregation shrinks payloads but omits per-row details.

## 11. Measuring N+1 and Repeated Queries

### Measure at the Application Layer

Attach query counts to each request or business transaction. Record:

- Number of SQL statements executed.
- Query digest or fingerprint and repetition count.
- Total time and p50/p95/p99.
- Rows returned, estimated rows examined, and payload size.
- Endpoint, resolver, or service issuing the queries.

If an endpoint returns 50 orders yet executes 51 SQL statements matching the same `WHERE order_id = ?` pattern, that is the classic signature of N+1. Per-request query counts pinpoint issues far better than server-wide totals.

### Inspect Statement Statistics in Performance Schema

MySQL aggregates statements by digest in `performance_schema.events_statements_summary_by_digest`:

```sql
SELECT DIGEST_TEXT,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
       SUM_ROWS_SENT,
       SUM_ROWS_EXAMINED
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

`COUNT_STAR` shows execution count for the digest; `SUM_TIMER_WAIT` is total time in picoseconds. A digest with huge execution count and low average time is a strong N+1 candidate. Cross-reference `SUM_ROWS_SENT`, `SUM_ROWS_EXAMINED`, and application traces to identify the originating endpoint.

Digest statistics are server/schema-wide aggregates and do not directly identify the exact request that triggered them. Performance Schema may have limited history size and instrument settings; check permissions and configuration before drawing conclusions.

### Run EXPLAIN on Batched Queries

After eliminating N+1, inspect the new SQL statements:

```sql
EXPLAIN
SELECT order_id, item_id, product_id, quantity, unit_price
FROM order_items
WHERE order_id IN (1001, 1002, 1003)
ORDER BY order_id, item_id;
```

Confirm that the index on `order_id` is considered, estimated rows are reasonable, and no excessive out-of-range scanning occurs. When actual runtime metrics are needed, run `EXPLAIN ANALYZE` in an appropriate environment; remember it executes the query.

## 12. Mistakes When Optimizing N+1

| Mistake | Consequence | Fix |
|---|---|---|
| Replacing N+1 with an unbounded JOIN | Result can multiply rows and create huge payloads | Paginate parent first, bound scope, and map relations cleanly |
| Putting LIMIT on a one-to-many join | Missing parent records or truncated items | Limit parent inside CTE/subquery before joining |
| Using `SELECT *` on every table | Returns unneeded columns | Select only columns actually displayed or processed |
| Building an oversized `IN` list | Long SQL, heavy parsing, huge payload | Chunk batches or use a staging table |
| Concatenating IDs directly into SQL | SQL injection risk and formatting bugs | Use prepared statements and bound parameters |
| Global cache without invalidation | Stale data or cross-user/tenant leaks | Use per-request caching or clear invalidation policies |
| Skipping transactions when snapshot is needed | Parent/child data may come from different timestamps | Use proper transaction/isolation and keep it short |
| Watching query count alone | One giant query can still be very slow | Measure rows, bytes, latency, and CPU/I/O |

## 13. Workflow for Fixing an N+1 Endpoint

1. Trace a representative request and count SQL statements.
2. Group queries by digest; look for repeated patterns differing only by key parameter.
3. Identify data relationships: one-to-one, many-to-one, one-to-many, or aggregated.
4. Pick `JOIN`, `IN` batching, `GROUP BY`, or DataLoader based on output shape.
5. If paginated, limit the parent set before joining one-to-many child data.
6. Check indexes and `EXPLAIN` for the new queries.
7. Compare query count, rows examined, rows sent, payload, and p95 latency before/after.
8. Verify transaction/isolation if multiple batches must share one snapshot.
9. Test with near-production page sizes and distributions, including parents with very many children.
10. Monitor post-deployment to confirm query counts drop without shifting bottlenecks elsewhere.

## 14. Practice Exercises

Using the `orders` and `order_items` tables from section 1:

1. Write a loop simulating loading 50 orders and then loading items per `order_id`. Count SQL statements and measure total round-trip time.
2. Rewrite using `LEFT JOIN`. Reconstruct per-order item lists by `order_id` and explain why order columns repeat.
3. Rewrite using two batched queries: one for orders, one for items with `IN`. Compare query count and bytes returned.
4. Test placing `LIMIT 50` directly on the one-to-many join and compare against a CTE paginating orders before joining.
5. Write a `GROUP BY order_id` query computing `item_count` and `total_quantity` for all orders on a page.
6. Pass 1,000 `order_id` values into a batch. Compare one large `IN` list against smaller chunks and a temporary table.
7. Run batched reads inside a `REPEATABLE READ` transaction, then test `READ COMMITTED` while another session updates items between the two reads. Observe snapshot differences.
8. Query `events_statements_summary_by_digest`, find digests with high `COUNT_STAR`, and match them against application request traces.

## Key Takeaways

- N+1 is one parent query plus one repeated query per parent record.
- `JOIN`, `IN` batching, `GROUP BY`, and DataLoader reduce round-trips tailored to each relationship shape.
- For one-to-many relationships, paginate parents before joining and avoid double-counting parent values.
- Chunk batches at measured sizes; use prepared statements and staging tables for large key lists.
- Multiple batched queries can observe different snapshots; use transactions/isolation when business logic requires consistency.
- Measure per-request query counts alongside latency, rows examined, rows sent, and payload size; never tune by query count alone.
