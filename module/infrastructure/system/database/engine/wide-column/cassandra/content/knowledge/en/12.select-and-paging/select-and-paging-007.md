# DISTINCT, GROUP BY, and CQL Constraints to Check

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish `SELECT DISTINCT` from `GROUP BY` in Apache Cassandra and explain why neither operates like arbitrary grouping or sorting in relational SQL.
2. Write valid `DISTINCT` queries for **partition keys** and **static columns**, while recognizing invalid `DISTINCT` queries on clustering or regular columns.
3. Use `GROUP BY` along a **primary key prefix**, combined with `COUNT(*)`, `SUM`, `MIN`, `MAX`, or `AVG` when the query scope is bounded.
4. Distinguish aggregated values from non-grouped columns that happen to be selected, avoiding treating a representative column value as a property of the whole group.
5. Check CQL constraints around `WHERE`, `ORDER BY`, `LIMIT`, `HAVING`, and partition read scope before putting analytics into an API.
6. Decide when a pre-maintained summary table is needed instead of running live analytical queries over transactional data in a distributed cluster.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Because Apache Cassandra is a distributed wide-column database, **data partitioning**, **clustering order**, **replication**, **consistency**, and query-driven table design directly determine both the correctness and the cost of grouping operations. The CQL and Java examples below cover both syntax and identifying which queries are genuinely suitable for production applications.

## 1. DISTINCT and GROUP BY Answer Two Different Questions

In a Cassandra table with primary key:

```sql
PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
```

distinguish:

- **`DISTINCT`:** "Which **partitions** exist?" Cassandra restricts the `DISTINCT` selector list to partition key columns and static columns; it is not a general deduplication operator on any column.
- **`GROUP BY`:** "For the selected rows, how many rows or what total amount belongs to **each primary-key-prefix group**?" CQL only supports grouping shapes compatible with key structure, rather than arbitrary expressions or columns.
- **Aggregate without `GROUP BY`:** "Across the matching rows, what is the aggregate?" For example, `COUNT(*)` over **one known partition**.

| Desired query | Suitable CQL tool | Key constraint |
| --- | --- | --- |
| List the months that have partitions for a store | `SELECT DISTINCT store_id, month_bucket` | Selects partition key; read scope still depends on `WHERE`. |
| Count orders in a month | `COUNT(*)` | Must read the rows in the set being counted. |
| Count orders per day within a month | `GROUP BY` on a key prefix including `order_day` | Clustering key must follow primary key order. |
| List distinct `PAID`/`CREATED` statuses | Cannot run `DISTINCT status` directly on the example table | `status` is a regular column; consider another read/summary table. |
| Total revenue by status cluster-wide | No arbitrary `GROUP BY status` on the example table | Requires an aggregation pipeline or query-specific table. |

Difference from relational SQL: even though both questions mathematically involve "deduplication" and "grouping," **CQL does not provide arbitrary sort/hash aggregation over any data column** across the cluster.

## 2. CQL Lab: Table with Composite Partition Key and Static Column

Suppose an e-commerce application needs to query orders for **one store in one month**. Within each monthly partition, order day is the leading clustering column; `order_id` disambiguates orders on the same day.

### 2.1. Creating the Keyspace and Table

```sql
-- RF=1 and SimpleStrategy are for a single-node lab environment only.
CREATE KEYSPACE IF NOT EXISTS cql_group_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cql_group_lab;

CREATE TABLE IF NOT EXISTS orders_by_store_month (
    store_id uuid,
    month_bucket text,
    order_day date,
    order_id uuid,
    store_name text static,
    status text,
    amount_cents bigint,
    PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
) WITH CLUSTERING ORDER BY (order_day ASC, order_id ASC);
```

Column roles:

| Column | Role | Note |
| --- | --- | --- |
| `store_id`, `month_bucket` | **Composite partition key** | Whole pair is hashed to select the partition and replicas. |
| `order_day`, `order_id` | **Clustering columns** | Identify and order rows within each partition. |
| `store_name` | **Static column** | Partition-level value shared by all rows in that partition. |
| `status`, `amount_cents` | **Regular columns** | Row-level values; cannot be freely used in `DISTINCT`/`GROUP BY`. |

Because `store_name` is a static column, changing a store's name does not automatically synchronize across all monthly partitions. Partitions storing static values may need updating per product requirements, and analytics jobs must account for consistency and multi-table/multi-partition writes.

### 2.2. Loading Deterministic Sample Data

```sql
-- Store A, November: three orders on the 20th.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20',
    00000000-0000-4000-8000-000000000001, 'PAID', 10000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20',
    00000000-0000-4000-8000-000000000002, 'PAID', 15000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20',
    00000000-0000-4000-8000-000000000003, 'CREATED', 30000
);

-- Store A, November: two orders on the 21st.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21',
    00000000-0000-4000-8000-000000000004, 'PAID', 20000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21',
    00000000-0000-4000-8000-000000000005, 'SHIPPED', 40000
);

-- Store A, December: one order on the 1st.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12', '2026-12-01',
    00000000-0000-4000-8000-000000000006, 'PAID', 60000
);

-- Store B, November: one order on the 20th.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11', '2026-11-20',
    00000000-0000-4000-8000-000000000007, 'CREATED', 80000
);

-- Update static column at the partition level; no clustering key required.
UPDATE orders_by_store_month SET store_name = 'Store A'
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

UPDATE orders_by_store_month SET store_name = 'Store A'
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-12';

UPDATE orders_by_store_month SET store_name = 'Store B'
WHERE store_id = 22222222-2222-4222-8222-222222222222
  AND month_bucket = '2026-11';
```

The sample dataset has **three populated partitions** and **seven rows** in total:

| Partition key | Clustering groups by day | Rows | Sum of `amount_cents` |
| --- | --- | ---: | ---: |
| (A, `2026-11`) | 11/20: 3, 11/21: 2 | 5 | 115,000 |
| (A, `2026-12`) | 12/01: 1 | 1 | 60,000 |
| (B, `2026-11`) | 11/20: 1 | 1 | 80,000 |

With fixed keys in the example, re-running `INSERT` performs an **upsert** on the same primary key without adding duplicate rows. If the table already holds prior data outside these sample rows, the totals above will differ.

## 3. DISTINCT: Selecting Partition-Level Columns Only

### 3.1. Listing Known Monthly Partitions for Store A

```sql
SELECT DISTINCT store_id, month_bucket
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12');
```

With the sample data, this returns **two rows**:

| `store_id` | `month_bucket` |
| --- | --- |
| A | `2026-11` |
| A | `2026-12` |

Each row represents a **full partition key**, not an individual order. Partition A/11 has five orders yet contributes only **one `DISTINCT` row**.

Do not interpret this query as "get the two most recent months" unless you have explicit month-lookup and ordering mechanisms. `IN` simply names two known months; `DISTINCT` does not sort partitions chronologically.

### 3.2. Selecting a Static Column Alongside the Partition Key

```sql
SELECT DISTINCT store_id, month_bucket, store_name
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12');
```

`store_name` is a static column, so it is permitted in the `DISTINCT` selector list. The output remains **two rows for the two partitions**, each carrying the partition-level store name.

If no static value was written for a partition, it may appear as `null`. `DISTINCT` does not synchronize static values across partitions of the same store.

### 3.3. DISTINCT Cannot Be Used Arbitrarily on Clustering or Regular Columns

The following queries are **invalid** under `DISTINCT` rules for the lab table:

```sql
-- Invalid: status is a regular column.
SELECT DISTINCT status
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

-- Invalid: order_day is a clustering column, not part of the partition key.
SELECT DISTINCT order_day
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

-- Invalid: mixes valid DISTINCT columns with a regular column.
SELECT DISTINCT store_id, month_bucket, status
FROM orders_by_store_month;
```

To find the set of days with orders, you can use `GROUP BY` on the clustering key as shown next **within a known partition**. To find distinct `PAID`/`CREATED`/`SHIPPED` statuses across many orders, choose a fitting storage/read pattern; do not assume Cassandra provides `SELECT DISTINCT status` like a relational SQL analytics engine.

### 3.4. DISTINCT Does Not Make Full-Table Scans Cheap

```sql
-- For observation in a small lab; avoid arbitrary use in large production clusters.
SELECT DISTINCT store_id, month_bucket
FROM orders_by_store_month;
```

This query may scan **many partitions across many nodes**. Even though the output row count is smaller than the order count, the engine still needs to read enough data to identify every existing partition. Adding `LIMIT 10` only caps output; it does not provide a partition key to route the query to a small known scope.

In production systems, if an API frequently needs the list of active months for each store, consider a dedicated index/lookup table tracking months with orders, or query known monthly buckets within a bounded window.

## 4. GROUP BY: Grouping by a Primary Key Prefix

### 4.1. Core Rules

In the table:

```sql
PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
```

the key hierarchy is:

```text
store_id, month_bucket   |   order_day   |   order_id
<-- partition key ---->  |  clustering  | clustering

safe prefix for GROUP BY:
  (store_id, month_bucket)
  (store_id, month_bucket, order_day)
  (store_id, month_bucket, order_day, order_id)
```

Standard CQL `GROUP BY` only groups by **primary key columns in key order**, taking columns fixed by equality in `WHERE` into account. When running `GROUP BY` over multiple partitions, include the **full partition key** in the grouping key and bound partitions via `WHERE`. Some Cassandra versions also support specialized expressions like `floor()` to bucket timestamps on compatible clustering columns; that does not mean `GROUP BY` works arbitrarily on any expression or regular column.

Unlike relational SQL, `GROUP BY status` does not become valid just because `status` appears in `SELECT` or has low cardinality.

### 4.2. Counting Orders by Day Within One Monthly Partition

```sql
SELECT store_id,
       month_bucket,
       order_day,
       count(*) AS order_count,
       sum(amount_cents) AS gross_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
```

**Results computed from sample data:**

| `month_bucket` | `order_day` | `order_count` | `gross_cents` |
| --- | --- | ---: | ---: |
| `2026-11` | 2026-11-20 | 3 | 55,000 |
| `2026-11` | 2026-11-21 | 2 | 60,000 |

`store_id` and `month_bucket` remain constant in this query because `WHERE` pins a single partition. Cassandra can stream rows in their defined clustering order and group along the key prefix `(store_id, month_bucket, order_day)`.

Sum breakdown:

```text
2026-11-20:
  count = 3
  sum   = 10000 + 15000 + 30000 = 55000

2026-11-21:
  count = 2
  sum   = 20000 + 40000 = 60000

Entire November partition:
  count = 5
  sum   = 115000
```

This `GROUP BY` is valid because `WHERE` locates the partition and the grouping key relies purely on a **clustering key prefix**.

### 4.3. GROUP BY on the Partition Key When Reading Multiple Months

```sql
SELECT store_id,
       month_bucket,
       count(*) AS order_count,
       sum(amount_cents) AS gross_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12')
GROUP BY store_id, month_bucket;
```

With the sample data, this yields two groups:

| Partition/group | `order_count` | `gross_cents` |
| --- | ---: | ---: |
| (A, `2026-11`) | 5 | 115,000 |
| (A, `2026-12`) | 1 | 60,000 |

Thus `GROUP BY store_id, month_bucket` can emit **one aggregate result per partition**. It differs from `SELECT DISTINCT store_id, month_bucket` because `GROUP BY` also **reads the rows and computes aggregates**.

`IN` on the last component of the composite partition key generates **two candidate partition keys**. If the list spans 100 months/buckets, multi-partition read cost must be evaluated separately; `GROUP BY` does not turn those partitions into a contiguous range on the token ring.

### 4.4. Aggregating a Single Partition Without GROUP BY

If the question is simply "how many orders and what total revenue did store A have in November?", write it concisely:

```sql
SELECT count(*) AS order_count,
       sum(amount_cents) AS gross_cents,
       min(amount_cents) AS min_cents,
       max(amount_cents) AS max_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

With the sample data: `order_count = 5`, `gross_cents = 115000`, `min_cents = 10000`, `max_cents = 40000`. Because this targets **one row set identified by the partition key**, no `GROUP BY` is needed to split it into groups.

Avoid running full-table `COUNT(*)` regularly for dashboards under the assumption that returning a single cell makes the query cheap. Cassandra still has to process every row/partition in the counted set.

## 5. GROUP BY Constraints That Cause Queries to Be Rejected

### 5.1. Cannot GROUP BY Arbitrary Regular Columns

```sql
-- Invalid: status is not part of the primary key.
SELECT status, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY status;
```

In the current data model, orders with status `PAID` are not stored contiguously by `status`. If you need order counts by status at scale with low latency, consider a **summary table keyed by `(store, month, status)`** or a dedicated write/aggregation pipeline.

### 5.2. Cannot Skip Preceding Clustering Columns

```sql
-- Invalid: skips order_day and tries to GROUP BY order_id.
SELECT order_id, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_id;
```

`order_id` follows `order_day` in the clustering key. Grouping by `order_id` while skipping `order_day` violates the **primary key prefix** rule. You also cannot reorder grouping columns arbitrarily to force Cassandra to behave like an SQL engine.

### 5.3. No Relational SQL-Style HAVING

```sql
-- Invalid: CQL does not support HAVING in SELECT like relational SQL.
SELECT order_day, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day
HAVING count(*) > 2;
```

When the group set is **small and bounded**, the application can fetch the valid groups and filter `order_count > 2` in memory. If this is a hot condition over millions of groups or needs accurate aggregate-based pagination, **pre-compute and maintain summary data** in your write path or streaming pipeline.

### 5.4. Cannot ORDER BY Arbitrary Aggregate Values

```sql
-- Invalid: ORDER BY cannot sort by an aggregate alias.
SELECT order_day, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day
ORDER BY order_count DESC;
```

Cassandra's `ORDER BY` relies on **clustering columns** and schema-supported directions, not sorting temporary groups by `count(*)`. If an API needs "the 10 days with the most orders," design a top-N/summary table or fetch a bounded set of groups and sort in the application.

## 6. Non-Grouped Columns in SELECT: Misleading Representative Values

CQL permits certain aggregate queries to select columns not present in the grouping key. A non-grouped column value may be taken from the **first row of the group** encountered during traversal; it does **not** represent every row in the group.

```sql
-- Caution: status is not a grouping key.
SELECT order_day,
       status,
       count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
```

The danger is that readers might assume this query "counts orders by day and status." In reality, `GROUP BY` only groups by `store_id`, `month_bucket`, and `order_day`. On Nov 20, the rows have statuses `PAID`, `PAID`, `CREATED`: a single `status` shown next to `order_count = 3` does **not** mean all three orders share that status.

Therefore:

- Project only **grouping key columns** and **aggregates** when designing analytical responses.
- If counts by `status` are required, organize data by status or build an explicit aggregation pipeline.
- Avoid combining `SELECT *` with aggregates and drawing business conclusions from the regular columns returned.

Even if an example happens to return the expected value due to small test data or current clustering order, that coincidence never turns a representative cell into a **group-wide attribute**.

## 7. Aggregate Functions and Behavior with Missing Data

Common functions include:

| Function | Meaning | Notes |
| --- | --- | --- |
| `count(*)` | Counts matching rows | May scan many rows; not a pre-maintained counter for arbitrary queries. |
| `count(amount_cents)` | Counts non-null values in the column | Differs from `count(*)` when some rows lack that column. |
| `sum(amount_cents)` | Sums numeric values | Watch return type and overflow risk. |
| `avg(amount_cents)` | Average of numeric values | Watch type and precision for monetary values. |
| `min(amount_cents)`, `max(amount_cents)` | Minimum / maximum value | Does not return the full row associated with min/max. |

Example computing an average with controlled precision:

```sql
SELECT count(*) AS order_count,
       sum(amount_cents) AS total_cents,
       avg(CAST(amount_cents AS decimal)) AS avg_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

For the five values `10000, 15000, 30000, 20000, 40000`, the average is `23000` cents. Casting to `decimal` before averaging clarifies the desired result type. For currency, store amounts in the smallest integer unit and use an appropriate precision type in the application.

**Note:** Function return types depend on CQL function signatures and Cassandra version. Do not assume every aggregate applies to every data type, or that decimal arithmetic preserves precision if inputs were already truncated by integer division.

### Missing Data, TTL, and Deletions

If a row has no `amount_cents`, `count(*)` still counts the row while `count(amount_cents)` ignores null/missing values. If a cell expires via TTL or is deleted, observed counts at read time can change as replicas converge.

In distributed Cassandra, read consistency level (e.g., `LOCAL_ONE` vs. `LOCAL_QUORUM` under appropriate replication) controls **which replicas must respond**. It does not turn `COUNT(*)` into a cluster-wide transactional metric with snapshot isolation across separate queries.

## 8. Constraints on WHERE, LIMIT, and Read Scope

### 8.1. Partition Key Determines Fan-Out

Two queries can return similar summary row counts while having completely different read scopes:

```sql
-- Narrow scope: one specific partition.
SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

-- Wide scope: no partition key supplied.
SELECT store_id, month_bucket, count(*) AS order_count
FROM orders_by_store_month
GROUP BY store_id, month_bucket;
```

The second statement merely illustrates **table-wide scope** in a tiny lab. Even though the sample data returns just three groups across three partitions, in production it could read vast numbers of partitions across many nodes. If an API always queries **one store**, put the full partition key/bucket into `WHERE` and design the schema around the required read scope.

### 8.2. LIMIT Does Not Automatically Make Aggregates Cheap

```sql
SELECT store_id,
       month_bucket,
       order_day,
       count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day
LIMIT 1;
```

`LIMIT 1` caps the number of **grouped result rows** returned; it does not mean Cassandra reads only **one order row** to compute `COUNT(*)`. To return an accurate count for the emitted group, Cassandra must examine the rows belonging to that group per aggregate semantics.

In queries combining `GROUP BY`, `PER PARTITION LIMIT`, and `LIMIT`, never equate **capping output groups/result rows** with **capping raw rows read to compute aggregates**. Verify behavior on your cluster version and workload, especially when selecting top-N over an aggregate.

### 8.3. GROUP BY Does Not Replace Valid Clustering Conditions

```sql
-- Valid: scopes to one partition and one day by clustering column.
SELECT order_day, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND order_day = '2026-11-20'
GROUP BY store_id, month_bucket, order_day;
```

Conversely, adding `GROUP BY` to a query with `WHERE status = 'PAID'` does not turn `status` into a key or index. `ALLOW FILTERING`, if permitted for certain queries, only allows Cassandra to filter wider row sets—it creates neither a cheap read path nor arbitrary grouping capability.

## 9. DISTINCT, GROUP BY, and Query-Driven Table Design

A long-lived Cassandra system should define **which metrics truly need live updates**, query frequency, and latency budgets. Three practical options exist:

| Need | Approach | When it fits |
| --- | --- | --- |
| Count total orders for one store in a small month | `COUNT(*)` with full partition key | Partition row count is bounded and stats QPS is low. |
| Group by day within a small month | `GROUP BY` on `order_day` key prefix | Compatible clustering order, single bounded partition. |
| Continuous stats by status or cluster-wide | Pre-maintained summary table or ETL/streaming pipeline | Multi-partition, multi-group queries requiring low p95/p99 latency. |
| List active months for a store | Bucket catalog table or `DISTINCT` on known partition set | Avoids full-table scans when month history grows large. |

Example table storing pre-aggregated daily metrics:

```sql
CREATE TABLE IF NOT EXISTS daily_order_summary_by_store_month (
    store_id uuid,
    month_bucket text,
    order_day date,
    order_count bigint,
    gross_cents bigint,
    PRIMARY KEY ((store_id, month_bucket), order_day)
) WITH CLUSTERING ORDER BY (order_day ASC);
```

The application/pipeline can update metrics via its own workflow, then read:

```sql
SELECT order_day, order_count, gross_cents
FROM daily_order_summary_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

This pattern moves aggregation cost off the API read path; in exchange, order writes and summary updates may occur **asynchronously**. Design for duplicate events, order cancellations/deletes, retries, idempotency, backfills, drift reconciliation, and acceptable freshness. Never treat a CQL `BATCH` or counter column as a universal default for every multi-partition synchronization need.

For high-accuracy real-time analytics across many partitions, consider dedicated aggregation architectures outside direct CQL queries alongside appropriate consistency policies.

## 10. Java Integration: Reading Groups with a Prepared Statement

Example using Cassandra Java Driver 4.x, Java 15+ for text blocks, and assuming an active `CqlSession session` connected to keyspace `cql_group_lab`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

UUID storeId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);

PreparedStatement prepared = session.prepare("""
    SELECT order_day,
           count(*) AS order_count,
           sum(amount_cents) AS gross_cents
    FROM orders_by_store_month
    WHERE store_id = ?
      AND month_bucket = ?
    GROUP BY store_id, month_bucket, order_day
    """);

BoundStatement statement = prepared.bind(
    storeId, "2026-11"
).setPageSize(50);

for (Row group : session.execute(statement)) {
    LocalDate day = group.getLocalDate("order_day");
    long count = group.getLong("order_count");
    long sumCents = group.getLong("gross_cents");
    System.out.printf("%s: count=%d, cents=%d%n",
        day, count, sumCents);
}
```

With the sample data, the loop processes **two groups**: day 20 (3, 55,000) and day 21 (2, 60,000). Notes:

- The bind marker for `store_id` (`uuid`) takes `UUID`; `month_bucket` (`text`) takes `String`.
- `count(*)` and `sum(amount_cents)` over `bigint` in this example are read via `getLong`. If you change aggregate types, adjust the CQL types and Java getters accordingly.
- `setPageSize(50)` is the driver's **fetch size**, not a limit on how many rows Cassandra must read to compute groups. To cap returned groups, use `LIMIT` properly.
- In a distributed cluster, reading at different consistency levels can observe different states if replicas have not converged. Never combine results from different points in time and call it a transactional snapshot.

If an API needs multiple months, consider querying each month using its full partition key, bounding concurrency, and deciding whether to merge results in the application tier. Avoid running full-table `GROUP BY` on every user-facing request.

## 11. Checklist of CQL Constraints to Verify

| Check question | Invalid example or risk | How to address |
| --- | --- | --- |
| What columns does `DISTINCT` select? | `SELECT DISTINCT status` | Use partition key/static columns only; for unique statuses, design another read path. |
| Which key does `GROUP BY` rely on? | `GROUP BY status` | Use a valid primary-key prefix or maintain a status summary table. |
| Are any leading clustering columns skipped? | `GROUP BY store_id, month_bucket, order_id` | Include `order_day` in proper position if grouping by full key, or redesign the query model. |
| How many partitions does `WHERE` target? | Full-table `GROUP BY` | Put the full partition key in `WHERE`; choose suitable bucketing. |
| Are groups filtered with `HAVING`? | `HAVING count(*) > 2` | CQL lacks standard `HAVING`; filter small group sets in the app or use summaries. |
| Are results sorted by an aggregate? | `ORDER BY order_count DESC` | Cassandra `ORDER BY` relies on clustering order, not aggregate aliases. |
| Are non-grouped columns selected? | `SELECT status, count(*) GROUP BY ...` | `status` only represents one row, not the group; omit it or aggregate explicitly. |
| Is `LIMIT` properly understood? | `COUNT(*) ... LIMIT 1` assumed to read one raw row | Caps output rows, not the underlying aggregate work. |
| Is global order needed across partitions? | `GROUP BY` with a very long `IN` | Cap fan-out and design a merge strategy or summary table. |
| Is dynamic data accounted for? | TTLs/deletes/concurrent writes and temporary inconsistency | Define consistency, acceptable freshness, and reconciliation. |

## 12. Practice Exercises with Answers

### Exercise 1. DISTINCT Populated Months

**Task:** List the monthly partitions `2026-11` and `2026-12` that have data for store A, along with the static name.

**Answer:**

```sql
SELECT DISTINCT store_id, month_bucket, store_name
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12');
```

With the sample data, this returns **two result rows**, each representing a monthly partition rather than an individual order.

### Exercise 2. Counting Orders per Day Within a Month

**Task:** For store A in November, how many orders and what total `amount_cents` occurred on each day?

**Answer:**

```sql
SELECT order_day,
       count(*) AS order_count,
       sum(amount_cents) AS gross_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
```

Nov 20: **3 orders, 55,000 cents**. Nov 21: **2 orders, 60,000 cents**.

### Exercise 3. Analyzing an Invalid Query

```sql
SELECT status, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY status;
```

**Answer:** `status` is a regular column, not part of the primary key. Cassandra does not support arbitrary `GROUP BY` on this column. You can create a status-keyed summary table or group in the application layer if the dataset is strictly bounded to a very small size and requirements allow it.

### Exercise 4. Does LIMIT Make GROUP BY Read Only One Order?

```sql
SELECT order_day, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day
LIMIT 1;
```

**Answer:** No. `LIMIT 1` caps **one group row in the result**, without guaranteeing only one order row is read to compute `count(*)` for that group.

### Exercise 5. Requirement for Top 10 Statuses by Order Count

**Task:** A dashboard wants "the 10 statuses with the most orders system-wide, updated continuously," while the table only has `status` as a regular column.

**Suggested answer:** `GROUP BY status ORDER BY count(*) DESC` is not a supported CQL query on this table. You need a controlled aggregation path (summary table, stream processor, or analytical store), clear update rules when order statuses change, and a freshness SLA. Scanning the whole table on every request will not yield predictable performance.

## 13. Takeaways When Designing Analytical Queries

Before using `DISTINCT` or `GROUP BY`, ask yourself:

1. **Partition scope:** Does `WHERE` supply the full partition key or a finite partition list? Can fan-out be estimated?
2. **`DISTINCT` eligibility:** Do the selected columns belong strictly to the partition key and static columns? Are you confusing it with "distinct values of a regular column"?
3. **`GROUP BY` eligibility:** Is the grouping list a valid primary key prefix in exact order, consistent with columns fixed in `WHERE`?
4. **Aggregate semantics:** Did you select a non-grouped column and misread it as representing the whole group? Are `SUM`/`AVG` types, nulls/TTLs, and currency units handled properly?
5. **Query limits:** Does `LIMIT` only cap result rows, or is the read dataset actually bounded? Is pre-aggregation needed due to high QPS or large partition sizes?
6. **Distributed operations:** How do replication/consistency, retries, tombstones, compaction, and repair impact cost and observed results?
7. **Java application:** Are return types, bind markers, paging, and per-request scope controlled and measured?

The central point is that **`DISTINCT` operates at the partition-key/static-value level, while `GROUP BY` follows the primary key structure**. If analytics primarily depend on regular columns or require low-latency cluster-wide grouping/sorting, organize dedicated data structures for those queries rather than expecting CQL to behave like a relational SQL analytics engine.

## References

- [Apache Cassandra — CQL Data Manipulation: SELECT, DISTINCT, and GROUP BY](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra — CQL Data Definition: primary key, clustering, and static columns](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra — CQL Functions: aggregate, COUNT, SUM, AVG](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html)
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
