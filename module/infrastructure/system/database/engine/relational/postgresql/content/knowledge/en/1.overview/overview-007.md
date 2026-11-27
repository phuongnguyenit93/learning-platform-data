# Distinguishing Transaction Processing and Data Analytics in PostgreSQL

## 1. Two Different Needs on the Same Data System

An e-commerce system typically fields two kinds of questions:

- **"A customer just placed an order—is there enough stock to sell? Did payment and inventory deduction succeed?"** This is a **transaction processing** need.
- **"By what percentage did monthly revenue grow? Which customer segment generated the most revenue this quarter?"** This is a **data analytics** need.

Both use SQL and relational data, yet their **query shapes, target response times, rows scanned, update patterns, and system architecture** differ sharply. A database can run smoothly at 1,000 order placements per second while struggling if several reports simultaneously scan hundreds of millions of transactions on that very same server.

The two workload classes are commonly called:

- **OLTP (Online Transaction Processing):** processes online business transactions, typically accessing few rows, performing many writes, and demanding correctness and fast responses.
- **OLAP (Online Analytical Processing):** analyzes large datasets, typically reading and aggregating many rows with extensive `JOIN`s, `GROUP BY`s, statistics, and time-series comparisons.

PostgreSQL is a general-purpose relational DBMS capable of serving **both OLTP and many types of analytics**, yet that **does not mean both workloads should always share the same infrastructure, schema, or optimization policies**.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish OLTP and OLAP queries from business requirements.
2. Differentiate requirements around latency, throughput, consistency, and data freshness.
3. Design initial schemas and indexes suited to each query class.
4. Write PostgreSQL SQL demonstrating transaction processing and analytics.
5. Understand the roles of MVCC, transactions, WAL, read replicas, and materialized views.
6. Decide when to run analytics directly on PostgreSQL versus offloading workloads to an analytical system.

**Scope:** examples use modern PostgreSQL with standard tables and PostgreSQL-standard SQL. The goal is architectural understanding and hands-on practice; performance figures in the text are illustrative, not measured benchmarks.

---

## 2. What Is OLTP?

**OLTP** focuses on recording and updating business state while many users or services operate concurrently.

An order placement transaction might consist of:

1. Verifying the customer and product.
2. Checking available stock.
3. Deducting inventory quantity.
4. Creating the order.
5. Creating order line items.
6. `COMMIT` if all steps requiring atomicity succeed; `ROLLBACK` on error.

If inventory deduction commits while order creation fails without a rollback, data no longer reflects reality. Thus, **atomicity** and **data integrity** are central requirements.

### 2.1. Common Characteristics of OLTP

- Accesses **one or a few rows** via primary keys, unique keys, or selective indexes.
- Involves many short `INSERT`, `UPDATE`, `DELETE`, and `SELECT` statements.
- Many transactions run **concurrently**, sometimes updating the same item or account.
- Expected response time is very low—for example, a few to tens of milliseconds for simple DB operations under suitable conditions.
- Uses `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `CHECK` constraints, and transactions to prevent invalid data states.
- Typically uses a **normalized** design to minimize duplication and maintain a single source of truth per entity.

Example of an order lookup query:

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE order_id = 1001;
~~~

If `order_id` is the primary key, PostgreSQL can locate that row using an index rather than scanning the entire table. The result normally contains just one row.

### 2.2. A Transaction Does Not Mean "One SQL Statement"

A transaction can span multiple SQL statements that must succeed together:

~~~sql
BEGIN;

-- Conditional inventory check/deduction.
-- Insert order header.
-- Insert order line items.

COMMIT;
~~~

The key principle is **business-aligned transaction boundaries**. Overly long transactions hold locks, increase contention, and retain old MVCC row versions longer than necessary.

---

## 3. What Is OLAP?

**OLAP** answers questions about trends, aggregations, and decision-making:

- Revenue by day/month/quarter.
- Cancellation rate by sales channel.
- Returning customers within 30 days.
- Top products by revenue and growth rate.
- Sales comparisons across regions/customer segments.
- Average order value, shares, cumulative totals, and rankings.

An analytical query might read millions of rows to return **just 12 monthly revenue rows**.

~~~sql
SELECT
    date_trunc('month', ordered_at)::date AS month,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY date_trunc('month', ordered_at)::date
ORDER BY month;
~~~

This snippet illustrates the idea; when `ordered_at` is `timestamptz` and reporting expects months in local time, specify the **business time zone** explicitly rather than implicitly relying on the session time zone. The lesson shows how below.

### 3.1. Common Characteristics of OLAP

- Reads **many rows** and **many columns** for aggregation.
- Frequently uses `JOIN`, `GROUP BY`, `HAVING`, `ORDER BY`, CTEs, and window functions.
- A single query can consume substantial CPU, I/O, and RAM even when returning very few rows.
- Concurrency may be lower than OLTP, yet **each query is far heavier**.
- Data may come from a snapshot, precomputed summary table, or ingestion pipeline.
- Sometimes minutes or hours of staleness are acceptable; in other cases, near real-time freshness is required.

OLAP is not always "strictly read-only." Analytical systems still ingest data, clean records, compute summary tables, and update storage structures. The difference lies in **purpose and workload shape**, not a rule that OLAP never writes.

---

## 4. High-Level Comparison of OLTP and OLAP

| Criterion | OLTP | OLAP |
|---|---|---|
| Purpose | Execute and record business transactions | Aggregate, explore, and support decision-making |
| Unit of operation | One customer/order/account or a few related rows | Many customers/orders, entire reporting periods |
| Common SQL | `INSERT`, `UPDATE`, `DELETE`, key-based `SELECT` | `SELECT` with `JOIN`, `GROUP BY`, window functions |
| Read volume | Usually small and selective | Usually large, may scan many partitions |
| Concurrency | Many short operations | Few to moderate heavy queries, platform-dependent |
| Key metrics | p95/p99 latency, TPS, error rate, lock waits | Report runtime, rows/bytes scanned, CPU/I/O, data freshness |
| Data organization | Usually normalized, prioritizing write correctness | May use star schemas, summary tables, or analytics-oriented models |
| Indexes | Primary keys, foreign keys, selective predicates | Filter keys, time ranges, `JOIN` keys; sometimes BRIN/partitioning |
| Data currency | Usually requires current state | Can be periodic, snapshot-based, or within agreed lag |
| Impact of errors | Lost orders, wrong inventory, wrong balances | Wrong reports, slow dashboards, decisions based on stale data |
| Costs to control | Lock contention, commits, connections, WAL writes | Large scans, sorts/hashes, memory, temp files, I/O contention |
| Design patterns | Transactions and constraints | Pipelines, historical data, pre-aggregations, partitioning |

**Not a rigid binary split:** an API might execute simple summary queries, and a data pipeline still uses transactions. Classify **each specific workload**, rather than merely labeling an entire system "OLTP" or "OLAP."

## 5. Why Can PostgreSQL Serve Both?

PostgreSQL stores relational data in row-oriented tables and provides powerful SQL, ACID transactions, indexes, a query optimizer, and parallel execution mechanisms suited to many query patterns.

### 5.1. Key Mechanisms for OLTP

**Transactions and ACID:**

- **Atomicity:** all changes in a transaction commit or roll back per transaction semantics.
- **Consistency:** data integrity rules hold when applications and constraints are designed properly.
- **Isolation:** concurrent transactions are coordinated per the chosen isolation level.
- **Durability:** committed transactions persist per storage/WAL durability settings.

**MVCC (Multi-Version Concurrency Control):** PostgreSQL lets transactions read row versions matching their snapshot without blocking every reader with exclusive row locks. This enables higher read/write concurrency than simple read/write lock models.

**Write-Ahead Log (WAL):** changes are logged for durability and recovery. WAL also powers physical streaming replication and other change-capture mechanisms. WAL **does not replace independent backups**.

**Indexes:** B-trees on primary keys, unique keys, and commonly filtered columns make fetching small row sets fast.

### 5.2. Key Mechanisms for OLAP

- `JOIN`, aggregate functions, grouping sets, window functions, and CTEs support rich analytical queries.
- The optimizer chooses `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, `Hash Join`, `Merge Join`, `Nested Loop`, or other appropriate operators.
- **Parallel query** plans can distribute scans and aggregations across multiple workers when beneficial.
- **Declarative partitioning** organizes large tables by month/year and enables skipping partitions outside query filters.
- **BRIN indexes** save space on huge tables whose values correlate with physical storage order (such as monotonically increasing timestamps).
- **Materialized views** store precomputed query results so reports read faster as of the latest refresh.

However, PostgreSQL in standard row-oriented table storage **does not automatically become a specialized columnar data warehouse**. Workloads scanning massive volumes may fit better on a dedicated OLAP engine or a separated architecture.

## 6. Building a Sample Sales Dataset

To observe both query classes, use a dedicated practice schema. The DDL below is PostgreSQL syntax, not MySQL syntax.

### 6.1. Create the Schema and Tables

~~~sql
CREATE SCHEMA IF NOT EXISTS learning_shop;

CREATE TABLE learning_shop.customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    segment TEXT NOT NULL
        CHECK (segment IN ('VIP', 'STANDARD'))
);

CREATE TABLE learning_shop.products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE learning_shop.orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES learning_shop.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);

CREATE TABLE learning_shop.order_items (
    order_item_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES learning_shop.orders(order_id),
    product_id BIGINT NOT NULL
        REFERENCES learning_shop.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);
~~~

Monetary columns use `NUMERIC` rather than floating-point numbers to represent two-decimal amounts accurately.

This schema is **normalized by entity**: customers, products, orders, and order items live in separate tables linked by foreign keys. `unit_price` in `order_items` is the **price at purchase time**, distinct from the current list price in `products.unit_price`. Preserving price snapshots is a sound business decision for order history.

> This is a lab model, not a complete e-commerce design: production systems also handle payments, refunds, addresses, taxes, shipping, and total reconciliation rules.

### 6.2. Load Sample Data

~~~sql
INSERT INTO learning_shop.customers
    (customer_id, email, customer_name, segment)
VALUES
    (1, 'an@example.com', 'An', 'VIP'),
    (2, 'binh@example.com', 'Binh', 'STANDARD'),
    (3, 'chi@example.com', 'Chi', 'VIP');

INSERT INTO learning_shop.products
    (product_id, sku, product_name, unit_price, stock_qty)
VALUES
    (11, 'KB-01', 'Keyboard', 350000.00, 50),
    (12, 'MS-01', 'Mouse',    150000.00, 80),
    (13, 'MN-01', 'Monitor', 2200000.00, 20);

INSERT INTO learning_shop.orders
    (order_id, customer_id, ordered_at, status, total_amount)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-01-05 10:00:00+07', 'PAID',     500000.00),
    (1002, 2, TIMESTAMPTZ '2026-01-05 15:00:00+07', 'PAID',    2200000.00),
    (1003, 1, TIMESTAMPTZ '2026-01-08 16:00:00+07', 'PAID',     300000.00),
    (1004, 3, TIMESTAMPTZ '2026-01-10 09:00:00+07', 'CANCELED', 350000.00),
    (1005, 2, TIMESTAMPTZ '2026-02-01 11:00:00+07', 'PAID',     350000.00),
    (1006, 3, TIMESTAMPTZ '2026-02-04 11:00:00+07', 'PENDING',  150000.00);

INSERT INTO learning_shop.order_items
    (order_item_id, order_id, product_id, quantity, unit_price)
VALUES
    (2001, 1001, 11, 1,  350000.00),
    (2002, 1001, 12, 1,  150000.00),
    (2003, 1002, 13, 1, 2200000.00),
    (2004, 1003, 12, 2,  150000.00),
    (2005, 1004, 11, 1,  350000.00),
    (2006, 1005, 11, 1,  350000.00),
    (2007, 1006, 12, 1,  150000.00);
~~~

The `orders` table has six orders: four `PAID`, one `CANCELED`, and one `PENDING`. Illustrative revenue computed from `orders.total_amount` **only for `status = 'PAID'`**:

| Period (Vietnam Time) | PAID Orders | Revenue |
|---|---:|---:|
| Jan 2026 | 3 | 3,000,000 |
| Feb 2026 | 1 | 350,000 |
| Total | 4 | 3,350,000 |

These figures are expected values from **the SQL data above**, not real revenue. Because the dataset has only a few rows, PostgreSQL may choose `Seq Scan` instead of indexes on most queries; never draw performance conclusions from a tiny lab dataset.

## 7. OLTP Examples: Reading and Updating Individual Transactions

### 7.1. Look Up One Order by Primary Key

~~~sql
SELECT
    o.order_id,
    o.status,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 1001;
~~~

This query needs only one order and its matching customer. PostgreSQL can look up `orders` via its primary key, then look up the customer via `customers`' primary key.

If a listing page shows a customer's 20 most recent orders, a composite index can help:

~~~sql
CREATE INDEX idx_orders_customer_time
ON learning_shop.orders (customer_id, ordered_at DESC, order_id DESC);

SELECT order_id, ordered_at, status, total_amount
FROM learning_shop.orders
WHERE customer_id = 1
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
~~~

Putting `customer_id` first supports the equality filter; the next two key parts support reading in newest-first order with `order_id` breaking ties. Still, PostgreSQL may choose another scan plan when the table is small.

### 7.2. Atomic Inventory Updates

When multiple buyers purchase the same product, an unlocked read-then-write flow fails:

~~~text
Request A: SELECT stock_qty → 1
Request B: SELECT stock_qty → 1
Request A: decides to deduct 1
Request B: decides to deduct 1
~~~

If the application computes against stale reads and writes back without concurrency control, inventory becomes wrong or a request is mishandled.

Use a **conditional `UPDATE`**:

~~~sql
UPDATE learning_shop.products
SET stock_qty = stock_qty - 2
WHERE product_id = 12
  AND stock_qty >= 2
RETURNING product_id, stock_qty, unit_price;
~~~

If this returns **one row**, it deducted two units and returned the updated stock and price. If it returns **zero rows**, either the product does not exist or stock is insufficient. This is a controlled single write independent of how long ago the application read inventory.

For a complete order placement, stock deduction and order creation must share a transaction:

~~~sql
BEGIN;

UPDATE learning_shop.products
SET stock_qty = stock_qty - 2
WHERE product_id = 12
  AND stock_qty >= 2
RETURNING unit_price;

-- The application MUST verify RETURNING returned exactly one row.
-- If 0 rows: ROLLBACK immediately, do not create the order.

INSERT INTO learning_shop.orders
    (order_id, customer_id, status, total_amount)
VALUES
    (1007, 1, 'PAID', 300000.00);

INSERT INTO learning_shop.order_items
    (order_item_id, order_id, product_id, quantity, unit_price)
VALUES
    (2008, 1007, 12, 2, 150000.00);

COMMIT;
~~~

This example hardcodes IDs and prices for readability; **run it only once** on lab data. In production applications, let the database generate `IDENTITY` values, capture IDs with `INSERT ... RETURNING`, compute totals from verified data inside the transaction, and **abort without committing if any step fails**. Real checkout flows also involve payment gateway integration, idempotency, and appropriate business states; never assume a single database transaction covers an entire cross-system workflow.

### 7.3. Why Are Transactions Central to OLTP?

If `UPDATE products` succeeds but `INSERT order_items` fails a foreign key check, the application needs `ROLLBACK` so both inventory and orders return to a valid state. If each statement committed independently, a single rollback at the end could not undo earlier commits.

OLTP code paths generally must address:

- Checking business conditions at write time.
- Short, explicit transaction boundaries.
- Handling deadlocks, serialization failures, and connection drops.
- Bounded retries and **idempotency** for requests that might be retried.
- Least-privilege write access and database constraints.

## 8. OLAP Examples: Reading and Aggregating Many Transactions

### 8.1. Monthly Revenue

PostgreSQL stores `TIMESTAMPTZ` as an absolute point in time with time zone awareness. If a report groups days or months in **Asia/Ho_Chi_Minh**, convert to local time before grouping:

~~~sql
SELECT
    date_trunc(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM learning_shop.orders
WHERE status = 'PAID'
GROUP BY 1
ORDER BY 1;
~~~

Expected output prior to running the sample order insert in Section 7.2:

| month_start | paid_orders | revenue |
|---|---:|---:|
| 2026-01-01 | 3 | 3000000.00 |
| 2026-02-01 | 1 | 350000.00 |

Unlike single-order lookups, this query evaluates **all `PAID` orders** in the dataset and groups them by month.

> If you already ran Section 7.2 and inserted order 1007 at the current timestamp, report totals will change. Maintain the same **baseline data state** when comparing lab outputs.

### 8.2. Daily Aggregation with a Time Range Filter

~~~sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS order_day,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM learning_shop.orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+07'
GROUP BY 1
ORDER BY 1;
~~~

Expected output from the original dataset:

| order_day | paid_orders | revenue |
|---|---:|---:|
| 2026-01-05 | 2 | 2700000.00 |
| 2026-01-08 | 1 | 300000.00 |

The filter uses a **half-open interval** (inclusive start, exclusive end) directly on the raw `ordered_at` column, avoiding missing end-of-day timestamps while remaining eligible for a B-tree index on the timestamp column.

### 8.3. Top Customers by Revenue

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    c.segment,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS total_revenue
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name, c.segment
ORDER BY total_revenue DESC, c.customer_id
LIMIT 10;
~~~

How this differs from OLTP:

- Must join many orders with customers.
- Must compute `SUM` across rows.
- Can only determine the highest `total_revenue` after aggregating.
- `LIMIT 10` caps returned rows, **not** the number of orders read (it does not scan only 10 orders).

With the sample data, **Binh** totals 2,550,000 and **An** totals 800,000; customer Chi has no `PAID` orders and is excluded by this `INNER JOIN`. To keep all customers including non-buyers, switch to `LEFT JOIN` and move the order status filter into the `ON` clause appropriately.

### 8.4. Cumulative Analysis with Window Functions

~~~sql
WITH daily_revenue AS (
    SELECT
        (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS order_day,
        SUM(total_amount) AS revenue
    FROM learning_shop.orders
    WHERE status = 'PAID'
    GROUP BY 1
)
SELECT
    order_day,
    revenue,
    SUM(revenue) OVER (
        ORDER BY order_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM daily_revenue
ORDER BY order_day;
~~~

The first CTE computes daily revenue. The window function accumulates a running total from the start of the series through each day. This is an analytical pattern—it updates no individual order, instead turning many event rows into **metrics** for decision-making.

### 8.5. Order Share by Status

~~~sql
SELECT
    status,
    COUNT(*) AS order_count,
    ROUND(
        100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
        2
    ) AS percentage
FROM learning_shop.orders
GROUP BY status
ORDER BY order_count DESC, status;
~~~

This combines `GROUP BY` and `SUM(COUNT(*)) OVER ()` to calculate shares of total orders. It is handy for dashboards, though you must still verify the **denominator** matches business semantics: all orders ever, orders in a month, or only valid orders?

## 9. Data Normalization and Dimensional Modeling

### 9.1. Why Does OLTP Typically Use Normalized Schemas?

The `orders` table stores `customer_id` rather than copying all customer details into every order. If a customer's name changes, the app updates a single `customers` record.

This approach helps:

- Reduce unnecessary duplication.
- Enforce foreign keys.
- Avoid insert/update/delete anomalies.
- Keep one clear source of truth per entity.

However, reporting may require joining multiple tables and processing large historical volumes.

### 9.2. Why Does Analytics Often Use Facts and Dimensions?

An analytical model can organize data as:

~~~text
                  dim_customer
                        |
+----------+      +--------------+      +------------+
| dim_date | ---- | fact_sales   | ---- | dim_product|
+----------+      +--------------+      +------------+
                        |
                   dim_channel
~~~

- **Fact table** (`fact_sales`): quantitative events such as quantity, revenue, discount, and tax; each row has a well-defined *grain*.
- **Dimension tables** (`dim_customer`, `dim_product`, `dim_date`): descriptive attributes for grouping, filtering, and slicing data along multiple axes.

For example, one fact row might represent **one paid order line item**, rather than one whole order. When the grain is line item, order counts must use `COUNT(DISTINCT order_id)` or an order-grain model to avoid counting each line item as a separate order.

A star schema makes many analytical queries easier to understand and optimize, yet is **not mandatory for running OLAP on PostgreSQL**. At modest scale, querying the OLTP schema directly may be completely sufficient.

### 9.3. History Is a Separate Requirement

Suppose a customer belongs to the `VIP` segment today, whereas last month they were `STANDARD`. Should last month's report show their **current** segment or their **segment at purchase time**?

Joining historical orders directly to the current `customers.segment` row causes historical reports to shift retroactively whenever a customer is upgraded. Analytical warehouses often need **dimension history** (e.g., Slowly Changing Dimension Type 2) or attributes captured at event time.

This is a key distinction: **current transactional state alone is not guaranteed to reconstruct every historical reporting dimension**. Define "as-of" rules from business requirements.

## 10. Indexing for OLTP and OLAP Workloads in PostgreSQL

### 10.1. B-Tree Indexes for Selective Access

B-trees excel at primary keys, equality lookups, range scans, and certain ordered sorts.

Example fetching a customer's newest orders:

~~~sql
CREATE INDEX idx_orders_customer_ordered
ON learning_shop.orders
    (customer_id, ordered_at DESC, order_id DESC);
~~~

For a report frequently filtering `PAID` orders by date range:

~~~sql
CREATE INDEX idx_orders_paid_time
ON learning_shop.orders (ordered_at)
WHERE status = 'PAID';
~~~

This is a **partial index**: it stores only rows matching `status = 'PAID'`. It can be smaller than a full-status index when only a subset of orders are paid. The optimizer uses it only when query predicates **imply** the partial index's predicate; with prepared statements and generic plans, do not assume arbitrary status parameters automatically match.

Keep in mind:

- Indexes speed up reads while forcing `INSERT/UPDATE/DELETE` to maintain extra structures.
- If a table is small or a report reads most rows, `Seq Scan` can be faster.
- Partial indexes require matching predicates; not every query on `ordered_at` can use them.
- Keep indexes backed by **measured critical queries**, rather than adding indexes on gut feeling.

### 10.2. BRIN for Very Large, Time-Correlated Tables

For huge append-heavy event tables where `event_time` increases roughly in physical storage order, **BRIN** stores summary ranges for groups of blocks. These indexes are far smaller than B-trees and can skip out-of-range block groups:

~~~sql
-- Illustrative on a large-scale event table if present.
CREATE INDEX idx_event_time_brin
ON event_logs USING BRIN (event_time);
~~~

BRIN **does not pinpoint individual rows** like a B-tree. If timestamps are scattered randomly across blocks, effectiveness drops sharply. Do not pick BRIN merely because a column is a timestamp; evaluate physical correlation, table scale, and query filters.

### 10.3. `GIN` Is Not an Index for Every Aggregate

PostgreSQL provides `GIN` indexes, which are effective for full-text search, arrays, or JSONB operators where supported. Yet a `SUM(total_amount) GROUP BY month` report does not speed up simply by putting a GIN index on `total_amount`. Always choose index types based on **the operators used**.

### 10.4. Partitioning for Large Historical Tables

Suppose `orders` holds hundreds of millions of rows and reports typically filter a date window. You can evaluate **declarative partitioning** by time to manage monthly slices and enable partition pruning:

~~~sql
CREATE TABLE report_events (
    event_id BIGINT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB
) PARTITION BY RANGE (event_time);

CREATE TABLE report_events_2026_01
PARTITION OF report_events
FOR VALUES FROM ('2026-01-01 00:00:00+00')
           TO   ('2026-02-01 00:00:00+00');

CREATE TABLE report_events_2026_02
PARTITION OF report_events
FOR VALUES FROM ('2026-02-01 00:00:00+00')
           TO   ('2026-03-01 00:00:00+00');
~~~

This example partitions on **explicit UTC boundaries**. If reporting slices months in Vietnam local time, design partition bounds accordingly rather than assuming UTC months match local months.

Partitioning helps skip irrelevant partitions when filters align and simplifies archiving or dropping old data. However:

- Not every query benefits.
- Too many partitions increase planning and administrative overhead.
- Unique constraints and primary keys on partitioned tables carry rules tied to partition keys.
- Partitioning **does not replace proper indexes and data modeling**.

## 11. MVCC, Consistency, and Data Freshness

### 11.1. Read Snapshots in PostgreSQL

Under the default `READ COMMITTED` isolation level, each read statement sees a snapshot of changes committed as of the start of that statement. Two `SELECT`s in the same transaction can see different states if another transaction commits in between.

Under `REPEATABLE READ`, statements share a transaction snapshot per PostgreSQL semantics; the snapshot is normally taken at the first statement needing one—do not assume `BEGIN` trivially freezes all data beforehand. PostgreSQL's `REPEATABLE READ` provides snapshot isolation that is stronger in several respects than the SQL standard's minimum requirement.

Under `SERIALIZABLE`, PostgreSQL uses **Serializable Snapshot Isolation (SSI)** to detect schedules that could violate serializability; a transaction may abort with a **serialization failure**, so applications must safely retry **the entire transaction**.

### 11.2. Reporting Queries and Writers Still Contend for Resources

MVCC lets normal `SELECT` queries avoid waiting on per-row write locks to read consistent versions. Yet long analytical queries still exert real pressure:

- Scanning large volumes consumes CPU and storage bandwidth.
- Competing for memory with hashes, sorts, and concurrent queries.
- Spilling temporary files to disk if `work_mem` or execution strategies cannot hold intermediate data in memory.
- Long-lived transactions/snapshots can block `VACUUM` from reclaiming obsolete versions, increasing bloat and I/O pressure.
- Interactions with table/metadata locks when DDL runs, even without acquiring row write locks.

Therefore, the claim "PostgreSQL has MVCC, so running heavy reports on the primary won't affect order placement" is **false**.

### 11.3. Consistent Does Not Mean Up-to-Date

A report can be **consistent** as of a 10:00 snapshot yet **stale** compared to 10:05 transactions. Conversely, a dashboard issuing separate queries against live data can assemble panels reflecting **different points in time**.

When designing reports, clarify:

- What maximum data lag is acceptable?
- Must all charts on a dashboard share the **exact same snapshot**?
- Does a user who just placed an order need to see it immediately?
- Is the output for financial auditing/closing or approximate trend monitoring?
- Is change history or point-in-time replay needed?

These answers determine whether to use a read replica, materialized view, or separate analytical system.

## 12. Why Can Heavy Reports Slow Down OLTP?

Suppose the PostgreSQL primary handles order checkouts while also running:

~~~sql
SELECT
    c.segment,
    date_trunc('month', o.ordered_at) AS report_month,
    SUM(o.total_amount)
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.segment, date_trunc('month', o.ordered_at);
~~~

On a tiny table, the cost is negligible. Across hundreds of millions of rows, the exact same query can consume massive resources.

### 12.1. CPU and I/O Contention

If a report scans most of a table, hot OLTP pages can be evicted from shared buffers and disk read I/O spikes. Checkout requests that only probe a few primary keys slow down waiting on CPU and I/O, even without row-lock waits.

### 12.2. Sorts and Hash Aggregates Consume Memory

Plans with `Sort`, `HashAggregate`, and `Hash Join` require working memory. When insufficient, PostgreSQL spills temp files to disk. Setting `work_mem` recklessly high globally is also dangerous because one query can have multiple memory-using nodes and many queries run concurrently.

### 12.3. Long Reports and `VACUUM`

A transaction holding an old snapshot forces PostgreSQL to retain obsolete row versions, delaying cleanup and causing tables and indexes to bloat. On write-heavy systems, this carries a major cost.

### 12.4. Impact on Service-Level Objectives

OLTP typically targets percentiles like **p95/p99**; a heavy hourly report can visibly degrade requests hitting at the same time. Looking solely at **mean latency** hides these spikes.

The fix is not simply "increase connection pool size." A larger pool lets even more heavy reports contend for resources simultaneously.

## 13. Deployment Patterns for OLTP and OLAP in the PostgreSQL Ecosystem

### 13.1. Option 1 — Analytics Directly on the Primary

~~~text
Transactional app ──┐
                    ├── PostgreSQL primary ─── Transaction tables
Dashboard/report ───┘
~~~

**Pros:** simple, no cross-system sync needed, reports query committed state as of each query's snapshot.

**Cons:** heavy reports compete for resources with writes; hard to isolate CPU/I/O budgets; long read transactions carry operational side effects.

Fits when data and load are still small, reports are relatively light or infrequent, and impact has been measured and accepted.

### 13.2. Option 2 — Read Replica for Reporting

~~~text
                        WAL/streaming replication
Application ──► Primary ─────────────────────────► Read replica
                   │                                    │
                   └── Business writes                  └── Report SELECTs
~~~

A PostgreSQL **physical standby** can receive WAL and serve read queries in hot standby mode when configured appropriately, offloading part of the read load from the primary.

Keep in mind:

- **Replicas can lag** behind the primary, especially with asynchronous replication.
- Immediately after placing an order on the primary, a user reading a replica **may not yet see** the new order.
- Long queries on a standby can conflict with WAL replay and be canceled per policy; settings that suppress conflicts can instead increase bloat on the primary.
- Replicas still store tables in row format and do not magically become columnar warehouses.
- The primary must still generate and ship WAL; replication lag and failover readiness require monitoring.

Thus, replicas fit lag-tolerant dashboards or throttled reporting queries. Flows requiring **strict read-after-write** must read from the primary or wait for the replica to reach the needed WAL position.

### 13.3. Option 3 — Materialized Views or Summary Tables

PostgreSQL supports **materialized views**, which store query outputs and update only when refreshed.

~~~sql
CREATE MATERIALIZED VIEW learning_shop.monthly_paid_revenue AS
SELECT
    date_trunc(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM learning_shop.orders
WHERE status = 'PAID'
GROUP BY 1;

SELECT *
FROM learning_shop.monthly_paid_revenue
ORDER BY month_start;
~~~

After `orders` changes, the materialized view **does not update automatically**:

~~~sql
REFRESH MATERIALIZED VIEW learning_shop.monthly_paid_revenue;
~~~

You need a refresh schedule or explicit refresh workflow aligned with acceptable staleness.

To use concurrent refresh:

~~~sql
CREATE UNIQUE INDEX ux_monthly_paid_revenue_month
ON learning_shop.monthly_paid_revenue (month_start);

REFRESH MATERIALIZED VIEW CONCURRENTLY
    learning_shop.monthly_paid_revenue;
~~~

`CONCURRENTLY` avoids blocking concurrent `SELECT`s on the materialized view during refresh, subject to strict conditions: the materialized view must **already be populated**, and it must have a **valid unique index on ordinary columns covering all rows (not an expression or partial index)**. You cannot arbitrarily apply `CONCURRENTLY` to every view. Refreshing still consumes CPU/I/O, and **core PostgreSQL does not automatically perform row-level incremental refreshes** just because a view is materialized.

**When worth using:** fixed-grouping reports run repeatedly where scheduled freshness is acceptable. Unsuitable for highly ad-hoc queries or instant reflection of every commit unless backed by additional architecture.

### 13.4. Option 4 — Offload to a Dedicated Analytical System

~~~mermaid
flowchart LR
    A["Application"] --> B["PostgreSQL OLTP Primary"]
    B --> C["CDC / ETL / Batch"]
    C --> D["Data Warehouse / OLAP Engine"]
    D --> E["Dashboards & Analytics"]
~~~

You can use batch **ETL/ELT** or **CDC (Change Data Capture)** from PostgreSQL changes to move data to a dedicated analytics store.

Potential benefits:

- Isolates analytical resource usage from the primary.
- Organizes fact/dimension schemas or columnar storage tailored for analytical queries.
- Retains historical snapshots and cleans data across multiple sources.
- Scales reporting independently from transactional traffic.

Trade-offs:

- Pipelines require monitoring, failure recovery, and reconciliation.
- Introduces data propagation latency.
- Must handle deletes, updates, duplicate events, and out-of-order events.
- Increases storage and operational costs.
- Requires governance over PII and access permissions on replicated data.

**No single architecture is universally best.** For a small shop, one PostgreSQL instance may suffice. For a large platform with dashboards scanning data continuously, isolating workloads matters far more than piling extra indexes onto the primary.

## 14. Comparing Consistency Requirements Between OLTP and Analytics

| Question | Preferred Handling Approach |
|---|---|
| Can stock be deducted for a new order? | Atomic conditional check/update inside a transaction |
| Has a newly paid order's total committed? | Read transaction state from an authoritative source |
| Can last month's revenue report lag by 30 minutes? | If acceptable, use a materialized view or pipeline |
| After writing, must the user immediately see their change? | Avoid lagging replicas or enforce read consistency |
| Must all charts on a dashboard use the exact same cut-off? | Use a shared snapshot or versioned report dataset |
| Does an audit report need exact historical reproduction? | Persist historical events/versions and closing rules |
| Are ad-hoc full-history scans slowing down checkouts? | Cap resources, tune queries, and consider offloading analytics |

While OLTP usually demands maximum freshness, **OLAP can also demand strict numerical accuracy**; the difference is that analytical systems can tolerate an **explicitly published lag** while guaranteeing accurate totals, groupings, and history as of the cut-off point.

## 15. Comparing Query Plans in PostgreSQL

PostgreSQL provides key tools to inspect and measure execution paths:

~~~sql
EXPLAIN
SELECT order_id, customer_id, status
FROM learning_shop.orders
WHERE order_id = 1001;
~~~

For an analytical query:

~~~sql
EXPLAIN
SELECT
    c.segment,
    SUM(o.total_amount) AS revenue
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.segment;
~~~

Common plan nodes:

| Node | Meaning |
|---|---|
| `Seq Scan` | Sequential scan across much or all of a table |
| `Index Scan` | Probes index keys, then fetches table rows as needed |
| `Index Only Scan` | Satisfies columns from the index when eligible; visibility checks may still visit the heap |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Collects row locations via index, then reads heap pages in batches |
| `Nested Loop` | Iterates one input and looks up matching rows in the other |
| `Hash Join` | Builds a hash table to join datasets |
| `Merge Join` | Joins pre-sorted inputs |
| `HashAggregate` / `GroupAggregate` | Computes grouped aggregations |
| `Sort` | Sorts rows |
| `Gather` / `Gather Merge` | Collects results from parallel workers |

`EXPLAIN` shows the **estimated plan**. To observe actual row counts and runtime:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.segment,
    SUM(o.total_amount) AS revenue
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.segment;
~~~

**Warning:** `EXPLAIN ANALYZE` actually executes the SQL statement. Here it is a `SELECT`; if run on `UPDATE/DELETE/INSERT`, data modifications occur. When testing DML with `EXPLAIN ANALYZE` in a lab, wrap it in a transaction with rollback and still account for side effects that cannot be rolled back.

### 15.1. Do Not Judge Cost by Result Row Count

An OLAP query can return **12 rows** after scanning 500 million rows. Conversely, an OLTP query might return **100 rows** in a couple of milliseconds via an index. Rows **returned** differ vastly from rows **processed**.

### 15.2. Why Does the Same SQL Choose Different Plans?

The optimizer depends on:

- Table row counts and value distribution statistics.
- Available indexes.
- Filter predicates and selectivity.
- Estimated I/O and CPU costs.
- Memory settings, parallelism, and PostgreSQL version.
- Cache warmth and environment configuration.

Tiny lab tables naturally favor `Seq Scan`. **Never treat `SET enable_seqscan = off` as a production optimization technique.** That lever is only for controlled diagnostic investigation—it does not fix why an index was not chosen naturally.

### 15.3. How to Measure in Real Systems

Track the same query with representative parameters, comparing:

- p50/p95/p99 latency and execution frequency.
- Plan shape, estimated vs. actual rows, and `BUFFERS`.
- CPU/I/O usage and temporary file spills.
- Lock waits and long-running transaction counts.
- Replica or pipeline lag if using copies.
- `INSERT/UPDATE` overhead after adding indexes.

You can use `pg_stat_statements` if the extension and configuration are enabled in your environment; never assume it is always installed or accessible via a single `SELECT`.

## 16. Anti-Patterns to Avoid

### 16.1. Running Unbounded Full-Scan Reports on the Primary

Analytical queries themselves are valid, yet running them unthrottled alongside checkouts causes resource contention. Cap concurrency, schedule runs, tune queries, or offload to replicas/warehouses.

### 16.2. Trying to Force Every Query to Use an Index

A report reading 80% of a table is often best served by `Seq Scan`, whereas a single-order lookup needs an index once the table grows. Optimize **overall execution cost**, not "zero sequential scans."

### 16.3. Adding Too Many Indexes to Heavy-Write Tables

Every index adds write overhead and disk usage. Adding 10 indexes for 10 rarely run reports can slow down millions of daily OLTP writes. Look for shared indexes, pre-aggregations, or workload separation.

### 16.4. Confusing a Transaction Snapshot with Real-Time Data

A snapshot query is consistent yet excludes commits occurring after the snapshot began. Replica or materialized view data carries additional lag policies.

### 16.5. Confusing Replication with Backups

Replicas propagate erroneous updates and deletions too. WAL/replication supports synchronization and failover recovery, yet you still need backups, restore drills, and PITR plans aligned with RPO requirements.

### 16.6. Multiplying Rows When Aggregating Orders and Line Items

For instance, joining `orders` with `order_items` and computing `SUM(orders.total_amount)` **double-counts order totals** whenever an order has multiple line items. Respect grain and pick the right metric: aggregate order totals at the order grain, and product revenue using `quantity * unit_price` at the line-item grain.

### 16.7. Failing to Pin Reporting Time Zones

`timestamptz` stores an absolute instant; "February 1st revenue" must specify a time zone. Grouping by the default session time zone causes the same data to shift across days if connection settings change.

### 16.8. Keeping Reporting Transactions Open Too Long

Long snapshots block `VACUUM` from reclaiming dead tuples and worsen bloat. Distinguish legitimate long queries from forgotten `"idle in transaction"` sessions.

### 16.9. Leaving Data Freshness Undefined

Dashboards backed by async replicas or materialized views display older numbers. If the product needs near real-time metrics, define target lag, monitoring, and fallback behavior explicitly.

### 16.10. Assuming a Star Schema Guarantees Correct Data

Facts/dimensions, ETL, and summary tables speed up queries, yet incomplete or duplicated pipeline ingestion still corrupts reports. Implement reconciliation, deduplication keys, update/delete handling, and historical tracking.

## 17. System Evolution Scenario: From Small Shop to Large Platform

### Stage A — Small Shop

- One PostgreSQL instance storing customers, orders, line items, and products.
- OLTP uses primary keys, foreign keys, transactions, and selective indexes.
- Monthly reports run infrequently on a small dataset.
- Monitor query durations; no separate ETL or warehouse needed yet.

**Rationale:** keep operations simple; premature distributed architecture rarely pays off before real scale demands it.

### Stage B — Growing Data and Dashboards

- Tune SQL and indexes for common filters.
- Evaluate summary tables or materialized views for recurring metrics.
- Limit runtime and frequency of heavy reports on the primary.
- Add a read replica if dashboards tolerate lag.
- Monitor OLTP p95/p99, CPU/I/O, `VACUUM`, and replication lag.

**Rationale:** relieve workload contention without rebuilding the entire architecture.

### Stage C — Multi-Source Analytics and Deep History

- Keep the PostgreSQL primary focused on transactional workloads.
- Offload ingestion via CDC/ETL/batch to an analytical layer.
- Design fact/dimension models with explicit grain and historical tracking.
- Enforce data quality, reconciliation, and access controls.
- Define freshness SLAs, late/duplicate event handling, and pipeline recovery.

**Rationale:** analytics becomes its own data product with distinct scale, history, and operational requirements.

## 18. Practice Exercises

Use the `learning_shop` schema from Section 6. Each exercise asks you to explain why a query leans OLTP or OLAP, not merely write valid SQL.

### Exercise 1 — Classify Workloads

Classify the following operations and name at least one metric to optimize:

1. Fetch the order with `order_id = 1001`.
2. Deduct stock for product 12 and create a new order.
3. Compute monthly revenue over the past three years.
4. List the top 20 highest-spending customers.
5. Check whether an email already exists before registration.
6. Populate a daily revenue summary table for repeated dashboard queries.

### Exercise 2 — Write a Conditional Transaction

Write an `UPDATE` deducting 3 units of product 11 **only if sufficient stock exists**, returning the remaining stock. Explain how to handle zero rows returned by `RETURNING`.

### Exercise 3 — Daily Revenue

Write a query selecting only `PAID` orders in January 2026 in **Vietnam time**, grouped by day, returning total order count and total revenue. Explain why a half-open interval is used on `ordered_at`.

### Exercise 4 — Top Customers

Write a `JOIN` between customers and orders to compute `PAID` revenue per customer. Why can `SUM(o.total_amount)` become inflated if you also join `order_items`?

### Exercise 5 — Choose Indexes

Compare two predicates:

~~~sql
-- Case A: look up one customer and sort newest orders first.
WHERE customer_id = 1
ORDER BY ordered_at DESC
LIMIT 20

-- Case B: compute PAID revenue across an entire year.
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
~~~

Propose candidate indexes for A and B. List reasons why B might still choose `Seq Scan` on a large table if most orders are `PAID`.

### Exercise 6 — Data Freshness Problem

A user just created an order on the primary. The application reads `orders` from a read replica and does not see it yet. Does this necessarily mean the database lost data? Name two ways to satisfy read-after-write.

### Exercise 7 — Materialized Views

Create a monthly revenue materialized view from `orders`. If a new `PAID` order is inserted afterward, why hasn't `SELECT` on the view changed? What requirements must be met to refresh concurrently?

### Exercise 8 — Measure the Plan

Run `EXPLAIN (ANALYZE, BUFFERS)` on a query summing revenue by status. Note:

- `Seq Scan` or `Index Scan`?
- Which aggregate node was used?
- `actual rows` and actual runtime?
- Were buffers read from cache or disk?
- What can you conclude on the tiny lab dataset, and what **cannot be concluded** for production?

### Exercise 9 — Choose an Architecture

A shop has 10 million orders; the checkout API needs very low p99 latency, while reporting dashboards tolerate 15-minute lag and run heavy multi-minute queries. Would you pick a single primary, primary + replica, or a pipeline to an OLAP engine? State what to measure before deciding.

## 19. Suggested Solutions

### Exercise 1

1. Key-based order lookup: **OLTP**, optimize lookup speed and latency.
2. Stock deduction and order creation: **OLTP**, optimize correctness, lock contention, and commit success rate.
3. Three-year monthly totals: **OLAP**, focus on scan volume, aggregations, and report runtime.
4. Top customers: **OLAP**, focus on JOIN/grouping/sorting cost.
5. Email check: **OLTP**; enforce uniqueness with a **database unique constraint**, rather than relying solely on `SELECT` and assuming no race conditions.
6. Summary table creation: **analytics preparation pipeline**; it writes data, yet its purpose is supporting OLAP.

### Exercise 2

~~~sql
UPDATE learning_shop.products
SET stock_qty = stock_qty - 3
WHERE product_id = 11
  AND stock_qty >= 3
RETURNING product_id, stock_qty;
~~~

If no row is returned, the application reports not found or insufficient stock per business rules; in a multi-step transaction, roll back when the condition fails.

### Exercise 3

~~~sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS order_day,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM learning_shop.orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+07'
GROUP BY 1
ORDER BY 1;
~~~

A half-open interval captures every instant within the month regardless of sub-second precision.

### Exercise 4

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        SUM(o.total_amount) FILTER (WHERE o.status = 'PAID'),
        0
    ) AS paid_revenue
FROM learning_shop.customers AS c
LEFT JOIN learning_shop.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY paid_revenue DESC, c.customer_id;
~~~

This preserves customers with no orders and returns 0. If `order_items` is joined directly as well, an order with two items duplicates `orders.total_amount` in the JOIN output; aggregate at the matching grain or pre-aggregate child tables before joining.

### Exercise 5

Case A can use `(customer_id, ordered_at DESC, order_id DESC)`. Case B can test a partial index `(ordered_at) WHERE status = 'PAID'`, yet if the query must read a very large fraction of the table to sum revenue, `Seq Scan` may still be cheaper. Never decide without inspecting `EXPLAIN` and real data.

### Exercise 6

An async replica may simply be **lagging**, not losing data. Read from the primary right after writes, or implement WAL-position-aware consistency waiting for the replica to catch up, with appropriate timeouts and fallbacks.

### Exercise 7

A materialized view reflects only the state as of its last populate/refresh. `REFRESH MATERIALIZED VIEW` updates it; `CONCURRENTLY` requires an already-populated view and a valid unique index on ordinary columns covering every row.

### Exercise 8

There is no single fixed plan or runtime across all PostgreSQL setups. Tiny lab datasets naturally pick `Seq Scan`; this **does not prove** B-trees are useless on multi-million-row tables. Always benchmark on representative data.

### Exercise 9

With heavy analytics and strict OLTP p99 SLAs, prioritize **separating analytical read resources**. If dashboards mainly run PostgreSQL-compatible queries and tolerate lag, a replica or summary tables can serve as a first step. If reports are complex, multi-source, scan deep history, or require dimensional models, a pipeline to a dedicated OLAP engine fits better. Before finalizing, measure workload, CPU/I/O, lag, and operational cost.

## 20. Conclusion

**OLTP** focuses on **small, concurrent, accurate state changes**: key lookups, conditional updates, transactions, and constraints. **OLAP** focuses on understanding **the big picture across many transactions**: large scans, JOINs, GROUP BYs, window functions, and historical time-series analysis.

PostgreSQL is versatile enough to support both across many scales, yet differing workload shapes call for deliberate choices in **schemas, indexes, transactions, data freshness, and deployment architecture**. Heavy OLAP queries can still degrade OLTP even though MVCC minimizes row-level read–write blocking.

When starting a new problem, ask yourself: **"Am I mutating the state of a business transaction, or analyzing many events to derive metrics?"** From that answer, choose your read/write paths, transaction boundaries, indexes, aggregation strategy, and execution host. Sound decisions rest not on mechanical OLTP/OLAP labels, but on **correctness, latency, scale, freshness, and real operational cost**.
