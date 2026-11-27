# Join Order, Access Path, and Join Algorithm Selection

When executing a multi-table join query, MySQL must make three related but distinct decisions: **join order** determines which table is processed first; **access path** determines how rows are read from each table; and **join algorithm** determines how row sets are combined. Writing `customers JOIN orders JOIN order_items` does not mean MySQL always reads the tables in that exact textual order.

MySQL uses a cost-based optimizer to estimate row counts, condition selectivity, index/table read costs, and table-joining costs. For the same SQL statement, plans can change when data, statistics, indexes, or versions change. Therefore, read `EXPLAIN` and verify with `EXPLAIN ANALYZE` instead of guessing the plan from table order in the query text.

In the `DATABASE_MYSQL` module, understanding these three decisions explains why a `JOIN` that is fast on small data becomes slow as data grows, why the optimizer picks the wrong driving table, and when index lookups or hash joins fit. This lesson focuses on MySQL 8.0 and later with InnoDB.

## Objectives

After this lesson, you will be able to:

- Distinguish join order, access path, and join algorithm.
- Explain how the optimizer estimates costs and picks a join order.
- Read table ordering in tabular, JSON, and TREE `EXPLAIN` formats.
- Distinguish table scans, index lookups, range scans, and covering accesses within a `JOIN`.
- Explain nested-loop join, index nested-loop join, batched key access, and hash join.
- Design indexes for the outer and inner sides of a nested-loop join.
- Diagnose why the optimizer chooses a suboptimal join order.
- Improve statistics with `ANALYZE TABLE` and histograms where appropriate.
- Use `EXPLAIN ANALYZE` to compare estimated row counts with actual row counts.
- Understand the limitations of forcing join order and the effects of outer joins.

## 1. Three Decisions During JOIN Execution

Suppose a query joins customers with orders:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42;
```

The optimizer must answer three questions:

1. **Join order:** read `customers` first then look up `orders`, or read `orders` first then look up `customers`?
2. **Access path:** read a table via table scan, index range scan, `ref` lookup, `eq_ref` lookup, or another access path?
3. **Join algorithm:** loop over outer rows and probe inner rows, batch keys for batched inner lookups, or build a hash table and probe?

These three decisions do not substitute for each other. For example, the optimizer may pick `customers` as the first table, use an index range scan on `tenant_id`, and then run a nested loop with index lookups on `orders.customer_id`. Another plan might read `orders` via an index filtering status/date, then look up `customers` by primary key.

## 2. Practice Dataset

Subsequent examples use four tables: customers, orders, order items, and products. Create the tables in a dedicated lab schema:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    customer_status VARCHAR(20) NOT NULL,
    external_customer_code VARCHAR(30) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customers_tenant (tenant_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_status_time
        (customer_id, status, created_at),
    KEY idx_orders_status_time
        (status, created_at, order_id, customer_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(160) NOT NULL,
    category_id BIGINT UNSIGNED NOT NULL,
    is_active TINYINT(1) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_products_category (category_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_order (order_id),
    KEY idx_order_items_product (product_id, order_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

The indexes on `orders` illustrate two potentially useful access directions: starting from customer and looking up orders, or starting from status/time and looking up customers. This does not mean every system should keep both indexes; they are created to compare plans and write overhead in the lab. InnoDB secondary indexes automatically include the primary key if it is not already in the declared key columns, so index `(tenant_id)` can supply `customer_id` for the join without duplicating it in the definition.

Load a sufficiently large dataset with varied distributions across tenants, statuses, and order creation dates. A few sample rows are insufficient to evaluate the optimizer because table scans are typically cheaper on tiny tables.

## 3. Join Order: Which Table Is Read First?

Join order is the sequence in which the optimizer brings tables into the join plan. For inner joins, the optimizer generally has freedom to reorder tables because the join can be transformed while preserving logical results. The order in `FROM` is query syntax, not a mandatory execution directive.

### 3.1. Starting from a Strongly Filtered Table

If `tenant_id = 42` selects only a small fraction of customers, starting from `customers` can make sense:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01 00:00:00'
  AND o.created_at <  '2026-02-01 00:00:00';
```

The plan can read tenant 42's customers via `idx_customers_tenant`, then for each customer look up matching orders via `idx_orders_customer_status_time`. This direction works well if the tenant has few customers or relatively few corresponding orders.

### 3.2. Starting from the Table with More Selective Predicates

If very few `PAID` orders exist in the time range, starting from `orders` can be cheaper:

```sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= '2026-01-01 00:00:00'
  AND o.created_at <  '2026-02-01 00:00:00'
  AND c.tenant_id = 42;
```

The optimizer can scan the `idx_orders_status_time` index range first, then look up each customer by primary key. The tenant filter is checked when retrieving each customer. This direction fits when status/time filters narrow down orders drastically before the join.

### 3.3. Join Order Depends on Data Distribution

Suppose `tenant_id = 42` selects 100 customers while status/date selects 2 million orders system-wide; starting with customers requires less work. If the tenant has 500,000 customers while status/date selects only 300 orders, starting with orders can be better.

Do not compare only raw table row counts. Estimate rows remaining after each condition and lookup counts at subsequent steps. A huge table can still be a good driving table if an index filters it down to a tiny subset.

## 4. Access Path: How Rows Are Read from Each Table

An access path describes how MySQL retrieves rows from a table in a `JOIN` plan. Common access types in tabular `EXPLAIN`:

| `type` | General Meaning | Typical Scenario |
|---|---|---|
| `system` | Table has exactly one row | System table / single-row derived result |
| `const` | At most one row matched via full unique/primary key and constants | Lookup by full unique key with fixed values |
| `eq_ref` | For each preceding row combination, at most one row looked up via full unique index/primary key | Joining `orders.customer_id` to `customers.customer_id` |
| `ref` | Lookup one or more rows via non-unique index or matching unique prefix | Finding orders by `customer_id` |
| `range` | Reading an index interval | Filtering by timestamp, ID, or value interval |
| `index` | Scanning the entire index | Can help if index is small/covering, though still a full index scan |
| `ALL` | Scanning the entire table | Small table, missing suitable index, or low-selectivity filter |

These labels are access types, not `JOIN` algorithms. For instance, a nested-loop plan may use `range` on the first table and `ref` on the inner table. Nor does `type=index` equate to a covering index; covering access is typically indicated by `Extra: Using index`.

### 4.1. eq_ref and ref in Joins

With primary key `customers.customer_id`, each `orders.customer_id` can match at most one customer row:

```sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id;
```

If the optimizer uses `customers`'s primary key, the `customers` table can show access type `eq_ref`. If looking up orders via the non-unique `orders.customer_id` index, the access type is typically `ref` because one customer can have multiple orders.

### 4.2. A Table Scan Is Not Always Wrong

If a table has only a few dozen rows, or the condition returns most of the table, sequential reading can be cheaper than traversing an index and looking up many rows in the clustered index. `ALL` does not automatically prove a query has a bug; inspect actual row counts, returned rows, query frequency, and latency.

### 4.3. JOIN Conditions Must Have Compatible Data Types

For an indexed join to work effectively, both join columns should have compatible data types, including width and signed/unsigned for numeric types, and character set/collation for string types. Casting or wrapping an indexed column in a function can make the condition non-sargable:

```sql
-- Good: both columns share BIGINT UNSIGNED type
ON o.customer_id = c.customer_id

-- Review carefully: casting on an indexed column
ON CAST(o.customer_id AS CHAR) = c.external_customer_code
```

If you must join keys of different types, prefer normalizing the schema or converting the value on the parameter/appropriate side so index usage on the critical column is preserved.

## 5. Nested-Loop Join

A nested-loop join (NLJ) iterates over an outer row set; for each outer row, it searches for matching rows in an inner set. Conceptually, for two tables:

```text
for each row in outer input:
    find matching rows in inner input
    emit joined rows
```

If the outer side has `M` rows and each inner search scans `N` rows, cost approaches `M × N`. If the inner side has a suitable index and each lookup reads only a few rows, cost drops dramatically.

### 5.1. Index Nested-Loop Join

This is common and efficient when the outer table is narrowed down and the inner table has an index on the join column:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42;
```

With `idx_customers_tenant(tenant_id)` (whose secondary entries carry `customer_id`) and `idx_orders_customer_status_time(customer_id, status, created_at)` (whose entries carry `order_id`), MySQL can:

1. Range-scan customers for `tenant_id = 42`.
2. For each `customer_id`, look up the matching index range in `orders`.
3. Read matching order rows and return results.

If the outer side yields 200 customers and each averages 20 matching orders, inner lookups occur roughly 200 times and result rows total about 4,000. If the outer side grows to millions of rows, the same repeated lookup pattern can become expensive.

### 5.2. When Does Nested Loop Fit?

- Outer input is small after filtering.
- Inner side has an index matching the join condition.
- Lookups typically return one or a few rows (`eq_ref`, `ref`).
- Results need early stopping with `LIMIT` and a compatible access ordering is required.

Nested loop can perform poorly when the outer side is huge, the inner side requires repeated scans, or index lookups incur heavy random I/O.

## 6. Batched Key Access (BKA) and Multi-Range Read

Batched Key Access is a nested-loop variant that collects join key values from multiple outer rows into a batch and performs inner lookups in batches. Multi-Range Read (MRR) can sort/group reads into a more storage-friendly order to reduce random I/O.

BKA still relies on an index on the inner table; it does not replace indexes. The main difference is batching lookups instead of issuing each lookup individually.

In MySQL, BKA is controlled via optimizer switches and is typically disabled by default. You can test it in a lab session:

```sql
SELECT @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'mrr=on,batched_key_access=on';

EXPLAIN FORMAT=TREE
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42;
```

Whether BKA is chosen also depends on query structure, indexes, the optimizer, and MySQL version. If the plan does not change, it does not mean the `SET` failed; current conditions may not qualify or estimated costs may not favor BKA. Compare `EXPLAIN ANALYZE` before and after on identical data and workload. Do not enable BKA system-wide based on a single lab query.

## 7. Hash Join

Hash join builds a hash table from one input (the build side), then reads the other input (the probe side) and looks up matching keys. For equi-joins, this algorithm can be efficient when no suitable join index exists or when large row volumes make repeated nested-loop lookups too costly.

Conceptual model:

```text
build hash table from one input using join key
for each row in the other input:
    calculate hash(join key)
    find candidate matches in hash table
    verify join condition
    emit matching rows
```

Hash join does not require an inner index lookup for equi-join conditions, though it still reads both inputs and allocates memory for the hash table. For large datasets, memory consumption and temporary disk I/O can be significant.

### 7.1. Hash Join in MySQL 8.0

MySQL 8.0.18 introduced hash join. Starting in MySQL 8.0.20, hash join replaced the legacy block nested-loop algorithm in applicable cases; therefore, documentation or plans from older versions may display `Using join buffer (Block Nested Loop)` whereas newer versions display `Hash join`.

In `EXPLAIN FORMAT=TREE`, eligible plans can show an `Inner hash join` node or the corresponding hash join operator. Exact display depends on version and `JOIN` type.

### 7.2. Build Side and Probe Side

In principle, the smaller input is usually the better candidate for the build side because the hash table requires less memory. The optimizer chooses based on cardinality and cost estimates; do not assume the table written on the left is always the build side.

### 7.3. When Does Hash Join Fit?

- Both inputs read a relatively large number of rows.
- The join condition is an equality comparison eligible for hash join.
- No efficient inner-side index lookup exists, or repeated lookups are too expensive.
- Memory and temporary I/O capacity suffice to handle the hash table.

If one input has only a few remaining rows and the other has a strong unique/index lookup, nested loop typically holds the advantage. Hash join also cannot fix scanning excessive data caused by missing filters or bad statistics.

## 8. Comparing Join Algorithms

| Algorithm | How It Works | Typically Fits When | Watchouts |
|---|---|---|---|
| Nested loop | For each outer row, find inner rows | Outer is small and inner has a good access path | Large outer can trigger massive lookups |
| Index nested loop | Nested loop using an inner index | Join key is indexed and lookups return few rows | Depends on selectivity and lookup locality |
| Batched Key Access | Batch outer keys then probe inner in batches; can pair with MRR | Many index lookups where batching reduces I/O | Depends on optimizer switches, workload, and version |
| Hash join | Build hash table, probe the other input | Large equi-join where index lookups are unsuitable | Consumes memory; may spill to temp I/O |
| Block Nested Loop (legacy) | Buffer blocks of outer rows in join buffer and scan inner | Plans on older versions | From MySQL 8.0.20, hash join replaces BNL in applicable cases |

There is no single best algorithm for every `JOIN`. The choice depends on post-filter input sizes, indexes, data distribution, join order, memory limits, and I/O costs.

## 9. Reading Join Plans with EXPLAIN

### 9.1. Tabular EXPLAIN

```sql
EXPLAIN
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

In traditional output, each row generally describes a table or query block. For simple joins, row order in the output usually reflects table access order in the plan. Columns to watch:

- `table`: table or alias accessed.
- `type`: access type such as `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`.
- `possible_keys`: indexes considered by the optimizer.
- `key`: chosen index.
- `key_len`: length of the key prefix used in the access path.
- `ref`: value/column compared against the key.
- `rows`: estimated rows to read.
- `filtered`: estimated percentage of rows remaining after filter conditions.
- `Extra`: additional notes such as `Using where`, `Using index`, `Using join buffer`.

For complex joins, derived tables, subqueries, or nested query blocks, do not rely solely on row order; use JSON or TREE to understand the full structure.

### 9.2. EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

JSON presents deeper details on `nested_loop`, `table`, `access_type`, `rows_examined_per_scan`, `rows_produced_per_join`, `attached_condition`, and cost estimates. This format is helpful when determining where conditions are applied and how row counts grow at each join step.

### 9.3. EXPLAIN FORMAT=TREE

```sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

TREE displays execution structure as a tree, making it easy to spot:

- `Nested loop inner join`: outer input and inner lookup.
- `Index lookup`: lookup through an index.
- `Index range scan`: reading an index range.
- `Table scan`: scanning a table.
- `Hash join`: build/probe hash join.
- `Filter`: filter condition applied at a node.

Read from the leaf nodes up to parent nodes to see where data enters, at which step it is filtered, and how it is joined.

## 10. EXPLAIN ANALYZE: Checking Estimates Against Actuals

Regular `EXPLAIN` primarily shows pre-execution estimates. `EXPLAIN ANALYZE` runs the query and adds actual row counts, loop counts, and timings per iterator. MySQL has supported this command since 8.0.18.

```sql
EXPLAIN ANALYZE
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01 00:00:00'
  AND o.created_at <  '2026-02-01 00:00:00';
```

Compare:

- Estimated rows vs. actual rows at each iterator.
- Loop counts on inner lookups.
- Per-iterator time and total time.
- Which node reads many rows yet emits very few.
- Which node takes the most time and whether it stems from sorting, hashing, or temp I/O.

`EXPLAIN ANALYZE` actually executes the `SELECT`. Do not run it casually on heavy queries or in production without evaluating scope and impact.

## 11. How Statistics and Cardinality Affect Join Order

The optimizer does not know query results ahead of time; it relies on statistics to estimate row counts and selectivity. When statistics are wrong or data is heavily skewed, the optimizer may choose the wrong driving table or underestimate loop counts.

### 11.1. Updating Table Statistics

```sql
ANALYZE TABLE customers, orders, order_items, products;
```

This tells MySQL to update key distribution statistics for the tables. After loading large datasets, deleting many rows, or significantly altering distributions, fresh statistics help the optimizer choose better plans.

`ANALYZE TABLE` does not create indexes and does not alter business data. It can consume resources and has locking/concurrency behavior depending on engine and version; run it according to appropriate operational procedures.

### 11.2. Histograms for Skewed Columns

If a column has a skewed distribution without a suitable index, a histogram can improve selectivity estimates for filter conditions:

```sql
ANALYZE TABLE customers
UPDATE HISTOGRAM ON customer_status WITH 32 BUCKETS;
```

Inspect histograms:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'customers'
  AND COLUMN_NAME = 'customer_status';
```

Drop histograms when needed:

```sql
ANALYZE TABLE customers
DROP HISTOGRAM ON customer_status;
```

Histograms do not create access paths and do not replace indexes. They improve predicate estimation; single-column histograms also do not perfectly capture multi-column correlations such as `(tenant_id, customer_status)`.

You can inspect a query affected by the histogram:

```sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE customer_status = 'ACTIVE';
```

### 11.3. Skew and Column Correlation

Suppose 90% of customers are `ACTIVE`, yet that ratio differs widely across tenants. If the optimizer lacks accurate distribution or correlation info between `tenant_id` and `customer_status`, post-filter row counts can be misestimated.

Inspect the actual distribution in the lab:

```sql
SELECT customer_status, COUNT(*) AS customer_count
FROM customers
GROUP BY customer_status
ORDER BY customer_count DESC;

SELECT tenant_id, customer_status, COUNT(*) AS customer_count
FROM customers
GROUP BY tenant_id, customer_status
ORDER BY customer_count DESC;
```

If estimates diverge, consider `ANALYZE TABLE`, histograms for eligible skewed predicates, composite indexes aligned with queries, and refreshing stats after data changes. Do not create histograms or indexes solely to force a specific plan without measuring.

## 12. Designing Indexes for Both Join Directions

For a query filtering tenant on customers and then fetching their orders:

```sql
WHERE c.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= ...
```

On the customer side, `idx_customers_tenant(tenant_id)` supports tenant filtering; InnoDB automatically carries primary key `customer_id` in secondary entries to supply the join key. On the order side, `idx_orders_customer_status_time(customer_id, status, created_at)` supports looking up orders per customer, status, and date interval; primary key `order_id` is also carried along.

If queries commonly start from orders with a highly selective status/date, index `(status, created_at, order_id, customer_id)` can support the order range scan first and supply `customer_id` for customer lookups. The two indexes represent two different access patterns.

### 12.1. Indexing Only the Join Column Is Not Always Enough

An index solely on `orders.customer_id` supports lookups by customer, but if a customer has tens of thousands of orders and the query only wants `PAID` orders from one week, a composite index cuts down rows read:

```sql
KEY idx_orders_customer_status_time
    (customer_id, status, created_at)
```

Conversely, if starting from system-wide status/time, the right column order may be:

```sql
KEY idx_orders_status_time
    (status, created_at, order_id, customer_id)
```

Do not create both merely because they could support both directions. Evaluate query frequency, selectivity, storage footprint, and write cost; extra indexes add overhead to every `INSERT`/`UPDATE`/`DELETE`.

### 12.2. Multi-Table Joins

With `customers -> orders -> order_items -> products`, the optimizer can join in multiple valid orders. One direction filters customers, fetches orders, retrieves order items, and looks up products. Another filters products by category, finds matching order items, and walks back up to orders and customers.

Indexes on each join edge may differ:

- `customers`: `idx_customers_tenant(tenant_id)`; secondary entries carry `customer_id`.
- `orders(customer_id, status, created_at)` for orders by customer.
- `order_items`: `idx_order_items_order(order_id)`; secondary entries carry `order_item_id`.
- `products`: `idx_products_category(category_id)`; secondary entries carry `product_id`.

If a query filters category very tightly, starting from `products` may make sense. If tenant and time filters are tighter, starting from `customers` or `orders` may be better. Decide based on post-filter row counts, not the order tables appear in SQL.

## 13. INNER JOIN and OUTER JOIN Impact on Reordering

With `INNER JOIN`, the optimizer generally has broad freedom to reorder tables when transformations preserve results. `LEFT JOIN` has row-preserving semantics for the left side; reordering can alter results and is therefore constrained by outer-join relationships.

Example:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
WHERE c.tenant_id = 42;
```

Placing `o.status = 'PAID'` inside `ON` retains customers who have no `PAID` orders; their `o` columns become `NULL`.

If you move that condition into `WHERE`:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

Rows without orders have `o.status IS NULL` and are eliminated by `WHERE`. The query then behaves effectively like an inner join with respect to this condition. Never move conditions between `ON` and `WHERE` just hoping to change the plan; preserve result semantics first.

## 14. Forcing Join Order and Optimizer Hints

MySQL normally chooses join order by cost. When you have measured and proven that the optimizer consistently chooses the wrong order, you can test `STRAIGHT_JOIN` in the lab:

```sql
SELECT STRAIGHT_JOIN
    c.customer_id,
    o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.tenant_id = 42
  AND o.status = 'PAID';
```

`STRAIGHT_JOIN` instructs MySQL to read tables in the order they appear in the `FROM` clause. It can validate hypotheses about join order, yet it can also lock the optimizer into a bad plan when data distributions evolve.

MySQL 8.0 also offers optimizer hints for join order such as `JOIN_ORDER`, `JOIN_PREFIX`, `JOIN_SUFFIX`, and `JOIN_FIXED_ORDER` in supported versions. Hint syntax must match the right query block and version; verify against the documentation for your exact MySQL version before use.

Prioritize fixing root causes:

- Refresh statistics.
- Add or adjust indexes aligned with the workload.
- Make join conditions sargable with compatible data types.
- Reduce row counts early with semantically accurate predicates.
- Avoid locking join order if data distributions change frequently.

## 15. Signs of a Problematic Join Plan

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Large table read first despite broad filter | Bad estimate or missing suitable index | Compare estimated vs. actual rows; inspect stats and histograms |
| Inner table shows `ALL` and very high loops | Missing index on join/filter or poor optimizer access path | Check inner index, loop counts, and join condition |
| `rows` estimate diverges far from actual | Stale stats, skew, or column correlation | Run `ANALYZE TABLE`, check histograms, inspect true distributions |
| Hash join consumes excessive time/memory | Two large inputs or huge build side | Narrow valid inputs, improve filters/indexes, and re-measure |
| Nested loop performs millions of lookups | Outer input too large or bad join order | Check outer cardinality, inner index, and alternative join direction |
| `Using temporary` or large sort | `GROUP BY`/`ORDER BY` not supported by access path | Check indexes, join order, and intermediate row volume |
| Query slows down after data growth | Plan suited small data, now selectivity shifted | Run `EXPLAIN ANALYZE` on production-like data |
| `LEFT JOIN` drops unmatched rows | Right-side predicate placed in `WHERE` | Review semantics and `ON`/`WHERE` placement |

## 16. Workflow for Optimizing a JOIN Query

1. State the required business result; confirm whether inner/outer joins must preserve unmatched rows.
2. Identify the strongest filter conditions and estimate rows remaining after each condition.
3. Verify data types and collations on join columns; eliminate unnecessary casts/functions on indexed columns.
4. List existing indexes on each table and identify feasible access paths.
5. Run `EXPLAIN FORMAT=TREE` and `EXPLAIN FORMAT=JSON` to read join order, access paths, and join algorithms.
6. Run `EXPLAIN ANALYZE` in lab/staging to compare estimates against actuals.
7. If estimates are off, refresh statistics and evaluate histograms for skewed predicates.
8. Design composite indexes aligned with the real join direction; avoid adding indexes based on single columns in isolation.
9. Compare nested loop/index lookup, BKA, or hash join if eligible and suited to the workload.
10. Measure latency, rows read, loops, I/O, and write overhead after adding indexes.
11. Use `STRAIGHT_JOIN`/optimizer hints only with clear evidence and a post-rollout monitoring plan.
12. Re-verify as data and distributions evolve; a good plan today is not guaranteed forever.

## 17. Practice Exercises

Perform these in a separate lab database using the four tables from Section 2 and a sufficiently large dataset:

1. Write a `JOIN` between `customers` and `orders` on `customer_id`, filtering one tenant; read table order in `EXPLAIN`.
2. Add `status` and a `created_at` range; compare index `(customer_id, status, created_at)` against `(status, created_at, customer_id)`.
3. Create a distribution where one tenant has very few customers; measure a plan starting from `customers`.
4. Create a distribution where a status/date selects very few orders; measure a plan starting from `orders`.
5. Use `EXPLAIN FORMAT=TREE` to identify nested loops and index lookups.
6. Observe access type `eq_ref` when looking up customers by primary key and `ref` when finding multiple orders per customer.
7. Test a query lacking an inner index in a separate lab schema; observe scan iterations and runtime.
8. Test BKA via session `optimizer_switch`; compare actual time rather than just algorithm names.
9. Construct a large equi-join without a suitable join index to observe hash join on MySQL 8.0.18+.
10. Vary row counts and data distributions; compare build/probe inputs and actual rows of the hash join.
11. Run `ANALYZE TABLE`, create a histogram on `customers.customer_status`, and compare estimates before and after.
12. Write a `LEFT JOIN` with a right-table predicate in `ON`, then move it to `WHERE`; explain which rows disappear.
13. Use `STRAIGHT_JOIN` to force order in the lab, compare against the optimizer's automatic plan, and remove the hint after measuring.
14. Optimize a three- or four-table `JOIN`; submit the query, proposed indexes, `EXPLAIN TREE`, `EXPLAIN ANALYZE`, and trade-off explanation.

You have completed this lesson when you can explain why the optimizer chooses a table as the driving input, distinguish access types from join algorithms, and use actual metrics to decide index or join-order changes.

## 18. Key Principles to Remember

- Join order, access path, and join algorithm are three distinct decisions.
- Table order written in `FROM` is not automatically MySQL's inner-join execution order.
- The optimizer chooses join order using cardinality, selectivity, and cost estimates.
- `eq_ref`, `ref`, `range`, `index`, and `ALL` are access types, not `JOIN` algorithms.
- Nested loop works well when the outer side is small and the inner side has a good index lookup.
- Index nested loop probes an inner index per outer row; an oversized outer input triggers excessive lookups.
- BKA batches lookups and can pair with MRR; measure before enabling.
- Hash join builds a hash table and probes the other input; suited for large equi-joins when index lookups are unfavorable.
- MySQL 8.0.18 introduced hash join; starting in 8.0.20 hash join replaces legacy BNL in applicable cases.
- Indexes should support both filters and join columns aligned with real access patterns.
- Bad statistics or skewed data can cause the optimizer to pick the wrong join order.
- `ANALYZE TABLE` updates statistics; histograms improve predicate estimates but do not create indexes.
- `EXPLAIN FORMAT=TREE` reveals execution structure; `EXPLAIN ANALYZE` supplies actual rows and timings.
- `LEFT JOIN` preserves left-side rows; placing predicates in `ON` vs. `WHERE` can alter results.
- Force join order only with evidence; fix statistics, indexes, and predicates first.
