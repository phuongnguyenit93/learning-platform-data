# COUNT, Aggregate Functions, and Actual Read Cost in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish the semantics of `COUNT(*)`, `COUNT(1)`, and `COUNT(column)`, especially when a column has missing values.
2. Use basic aggregate functions `MIN`, `MAX`, `SUM`, `AVG`, and `CAST`, understanding data types, precision, and overflow risks.
3. Write aggregate queries with bounded scope using **partition keys**, **clustering columns**, and time ranges inside a single partition.
4. Explain why `SELECT COUNT(*) FROM table` can be very slow or time out on distributed Cassandra, even though the result is a single number.
5. Understand the limits of `LIMIT`, `PER PARTITION LIMIT`, paging, and `GROUP BY` when combined with aggregates.
6. Choose among **direct counting**, **maintained summary tables**, **counters**, and **aggregation pipelines** based on latency, accuracy, and freshness requirements.
7. Read aggregate results from the Java Driver while knowing how to measure and handle errors when counting spans many partitions, tombstones, or replicas.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. In Apache Cassandra, data is distributed by partition key and ordered by clustering columns within each partition. Therefore, **a tiny single-cell result does not imply a cheap query**: to compute that cell, the system may have to scan vast numbers of rows across multiple replicas. This also underpins safe Java API design, consistency selection, and understanding the impact of compaction, repair, TTL, and real-world failure modes.

## 1. What Is COUNT Actually Counting in CQL?

Suppose a table holds order rows, with a few orders lacking a final price yet:

| Function | Meaning | Important note |
| --- | --- | --- |
| `COUNT(*)` | Number of **live rows** matching the query | Not total physical cells, SSTable records, or tombstones. |
| `COUNT(1)` | Equivalent form of `COUNT(*)` in CQL | Not noticeably faster just because `1` is written. |
| `COUNT(amount_cents)` | Matching rows with a **non-null value** in `amount_cents` | Can be smaller than `COUNT(*)`. |
| `COUNT(status)` | Non-null `status` values in the matching row set | Not the count of **distinct statuses**. |

Do not conflate:

- **Row count:** how many primary keys still have valid data to return.
- **Partition count:** how many full partition keys must be located/read.
- **Non-null value count:** how many rows have a specific column present.
- **Distinct value count:** how many unique values exist; `COUNT(column)` does not automatically perform `DISTINCT`.
- **Physical versions inspected:** depends on memtables, SSTables, TTLs, tombstones, compaction, and replica state—not directly reflected by the `COUNT` output.

For example, a partition with 5 rows where only 4 rows have `amount_cents` yields `COUNT(*) = 5`, `COUNT(amount_cents) = 4`. Every count is evaluated over the **matching row set** at the time and consistency level of that read.

## 2. Lab Table: Orders by Store and Month

An application wants to display order counts, total revenue, and min/max values for **one store in one month**. We design the table around that query:

```sql
-- Single-node lab only.
CREATE KEYSPACE IF NOT EXISTS cassandra_aggregate_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_aggregate_lab;

CREATE TABLE IF NOT EXISTS orders_by_store_month (
    store_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount_cents bigint,
    PRIMARY KEY ((store_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at ASC, order_id ASC);
```

### 2.1. Why Choose This Key?

| Component | Type | Role |
| --- | --- | --- |
| `(store_id, month_bucket)` | **Composite partition key** | Each store/month is a partition; Cassandra computes the token from both values. |
| `created_at` | First clustering column | Enables time-range selection **within one partition**. |
| `order_id` | Second clustering column | Disambiguates orders sharing a timestamp; completes the primary key. |
| `status`, `amount_cents` | Regular columns | Store status and price; no dedicated lookup path on these columns in the lab schema. |

The `ASC` order here serves chronological scan examples. It does **not** place partitions of the same store adjacent to each other by month: `month_bucket` is part of the partition key, not a clustering column.

### 2.2. Inserting Eight Sample Rows

```sql
-- Store A, November: three rows on the 20th.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'PAID', 10000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'CREATED', 15000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000003,
    'PAID', 30000
);

-- Store A, November: two rows on the 21st.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21 10:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAID', 20000
);

-- Cancelled order without amount_cents: column intentionally omitted on INSERT.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21 11:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'CANCELLED'
);

-- Store A, December: two rows in a different partition.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12', '2026-12-01 08:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'PAID', 50000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12', '2026-12-01 09:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'REFUNDED', 70000
);

-- Store B, November: third partition.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11', '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000008,
    'PAID', 80000
);
```

**Data summary for the newly created table:**

| Partition | Live rows | Rows with `amount_cents` | Total amount (cents) |
| --- | ---: | ---: | ---: |
| Store A / `2026-11` | 5 | 4 | 75,000 |
| Store A / `2026-12` | 2 | 2 | 120,000 |
| Store B / `2026-11` | 1 | 1 | 80,000 |
| **Entire lab table** | **8** | **7** | **275,000** |

The numeric results below assume **only these eight sample rows**, with no TTL expirations, deletes, or edits from other requests. Because fixed primary keys are declared, re-running the same `INSERT` statements performs upserts without creating duplicate rows. Also note: `month_bucket` is a business-month string convention; a production system must keep it consistent with time zones and `created_at`.

## 3. COUNT(*) Within Exactly One Partition

### 3.1. Counting Orders for One Store in One Month

```sql
SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

**Result:** `order_count = 5`.

The coordinator uses the `(store_id, month_bucket)` pair to locate the partition and responsible replicas. After finding the partition, however, Cassandra must still **process the necessary rows to count them**, rather than reading the number 5 from a pre-maintained transactional table counter.

Compared to a full-table count, this query has a **well-defined partition scope**. Still, if a single partition contains millions of rows or many tombstones, `COUNT(*)` within one partition can still be expensive.

```sql
-- COUNT(1) is an equivalent form for counting rows.
SELECT count(1) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Do not pick `COUNT(1)` expecting it to be faster than `COUNT(*)`: both must evaluate the matching row set.

### 3.2. COUNT(column) Skips Rows Missing That Column's Value

```sql
SELECT count(*) AS total_orders,
       count(amount_cents) AS priced_orders,
       count(status) AS orders_with_status
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

| Result | Value | Why |
| --- | ---: | --- |
| `total_orders` | 5 | Five order primary keys exist in the partition. |
| `priced_orders` | 4 | The `CANCELLED` order has no `amount_cents` value present. |
| `orders_with_status` | 5 | All five rows have `status`. |

CQL does not allow inferring "`COUNT(status) = number of distinct statuses`." Across the five rows, `PAID` appears three times, yet `COUNT(status)` is still **5**, not the number of distinct values. If the product needs "order count by status," that is **grouping by status**, not counting non-null values in a column.

### 3.3. Querying One Row by Full Key

```sql
SELECT count(*) AS matched_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at = '2026-11-20 09:00:00+0000'
  AND order_id = 00000000-0000-4000-8000-000000000002;
```

This is a **full primary-key lookup**, so `matched_count` is at most one. However, if the API already has the full key and only needs an existence check, it can read a single key column:

```sql
SELECT order_id
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at = '2026-11-20 09:00:00+0000'
  AND order_id = 00000000-0000-4000-8000-000000000002;
```

If no row exists, the result is empty; if it exists, `order_id` is returned. This expresses the **existence check** intent clearly without invoking an unnecessary aggregate; in a distributed system, consistency level still governs what data the request observes.

## 4. COUNT Within a Clustering Range

In the lab table, `created_at` is the first clustering column. Once the full partition key is fixed, you can count within a time window.

### 4.1. Half-Open Interval [start, end)

```sql
SELECT count(*) AS morning_orders
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at >= '2026-11-20 09:00:00+0000'
  AND created_at <  '2026-11-20 10:00:00+0000';
```

**Result:** `morning_orders = 2`, from the two orders at 09:00 and 09:30. The 08:00 order is outside the range, as are the Nov 21 orders.

Two filtering layers:

```text
Partition key:
  (store A, month 2026-11)
       |
       +-- created_at in ASC order
           11/20 08:00  -- outside range
           11/20 09:00  -- counted
           11/20 09:30  -- counted
           11/21 10:00  -- outside range
           11/21 11:00  -- outside range

COUNT(*) = 2
```

Using `>=` on the lower bound and `<` on the upper bound avoids double-counting rows landing right on the boundary between adjacent windows. If grouping by local calendar day, compute start and end instants using business time-zone rules rather than equating local dates with UTC.

### 4.2. Clustering Ranges Do Not Turn Regular Columns into Indexes

The following query is not supported along the standard key path of the lab schema:

```sql
-- status is not a partition key, clustering column, or index.
SELECT count(*) AS paid_orders
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND status = 'PAID';
```

Even within a single partition, Cassandra **does not maintain a contiguous clustering slice by `status`** for this condition. Adding `ALLOW FILTERING` or a suitable index may let some queries run, but it does not make counting O(1).

To count `PAID` orders frequently, consider:

- A **status-oriented read table** with matching partition/clustering keys.
- A **summary table** keyed by `(store_id, month_bucket, status)` maintained by the data pipeline.
- An index suited to your Cassandra version (such as SAI) **when selectivity and read load genuinely warrant it**; always benchmark aggregate cost.

Never add `ALLOW FILTERING` just to make a `COUNT` example run while ignoring row-scan risks.

## 5. COUNT Across Multiple Partitions and Full Tables

### 5.1. Two Known Months for the Same Store

```sql
SELECT count(*) AS order_count,
       count(amount_cents) AS priced_orders
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12');
```

With the sample data, `order_count = 7`, `priced_orders = 6`. This aggregates over rows belonging to **two full partitions**:

```text
(store A, 2026-11) -> 5 orders, 4 priced orders
(store A, 2026-12) -> 2 orders, 2 priced orders
                     ----------------------------
Total                     7             6
```

`IN` on `month_bucket` (the last component of the composite partition key) lists candidate partitions. A longer list widens the read and coordination scope even though the aggregate still returns **only one row**.

### 5.2. Full-Table COUNT: An Anti-Pattern in Production

```sql
-- Illustrative only in a small lab keyspace; never run arbitrarily
-- on a production table with many partitions.
SELECT count(*) AS total_orders
FROM orders_by_store_month;
```

On the sample data, the result is **8**. In a real cluster, however, omitting `WHERE` leaves no specific partition key to target. Cassandra may have to scan **the entire token range/all partitions of the table**, contacting multiple nodes and processing huge volumes of data.

On a large table:

- The coordinator must orchestrate work across many partitions and replicas.
- Counting **live** rows cannot simply be inferred from file sizes, SSTable counts, or rough estimates.
- TTLs and tombstones increase the work required to verify live rows.
- The query can time out before finishing, even though it only asks for **a single `bigint` value**.
- Separate reads at different times do not automatically yield a table-wide transactional snapshot.

A single numeric result reflects **output size**, not the **input size** Cassandra had to process.

## 6. Aggregate Functions SUM, AVG, MIN, MAX

### 6.1. Basic Aggregates

```sql
SELECT count(*) AS order_count,
       count(amount_cents) AS priced_count,
       sum(amount_cents) AS total_cents,
       min(amount_cents) AS min_cents,
       max(amount_cents) AS max_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

| Result column | Value in lab |
| --- | ---: |
| `order_count` | 5 |
| `priced_count` | 4 |
| `total_cents` | 75,000 |
| `min_cents` | 10,000 |
| `max_cents` | 30,000 |

`MIN(amount_cents)` and `MAX(amount_cents)` return the minimum/maximum **value**, not the entire order row carrying that value. If you need the `order_id` of the highest-value order, use a tailored table/query path or fetch and compare over a bounded set; do not select `order_id` alongside `MAX` and assume it is necessarily the ID of the max row.

### 6.2. AVG on Integer Types Can Truncate Fractional Parts

`amount_cents` is `bigint`. `SUM`/`AVG` aggregates depend on input types; for integer types, consider **overflow** and **rounding/truncation** risks. For monetary values, a clean approach is casting inputs to a decimal type before computing:

```sql
SELECT avg(CAST(amount_cents AS decimal)) AS avg_cents_decimal,
       sum(CAST(amount_cents AS varint)) AS total_cents_wide
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Since only four rows have prices, their average is:

```text
(10000 + 15000 + 30000 + 20000) / 4 = 18750 cents
```

Do not divide by `COUNT(*) = 5` when the business rule defines the average over **priced orders**. If the product defines unpriced orders as 0, that is a different **business data rule** that should be represented explicitly during writes or aggregation rather than assuming `null` equals zero.

Casting to `varint` before `SUM` chooses an integer type with a wider range than `bigint`, provided the application reads the matching return type. Supported functions and casts vary by function signature and Cassandra version; test against your actual Cassandra version.

### 6.3. Aggregates Do Not Automatically Reflect Final Accounting Metrics

The example above sums `amount_cents` across `PAID`, `CREATED`, and `REFUNDED` orders because there is no status filter. The figure `75,000` is the sum of existing `amount_cents` in the **queried partition**—it is **not automatically paid revenue or net revenue**.

To compute "paid revenue" or "net revenue after refunds," define:

1. Which statuses qualify and how status transitions affect totals.
2. Which fields represent charges, refunds, or adjustments.
3. How to structure data or summary tables to compute those metrics without scanning regular columns broadly.

Cassandra provides aggregate primitives, not built-in awareness of your application's accounting rules.

## 7. GROUP BY When You Want One Metric per Day

In the lab table, the full primary key is:

```sql
PRIMARY KEY ((store_id, month_bucket), created_at, order_id)
```

We can **group by the partition key or a clustering key prefix**, but cannot freely run `GROUP BY status` as in an analytical SQL tool.

Grouping by **day** from a timestamp requires a suitable data model. In the current schema, `created_at` is a full timestamp, not `order_day`; each distinct timestamp is a distinct clustering value. Therefore:

```sql
-- Valid by primary-key prefix, but groups by EXACT timestamp,
-- not automatically by day.
SELECT created_at, count(*) AS orders_at_timestamp
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, created_at;
```

With the sample data, all timestamps are distinct, yielding **five groups** of one row each—not a daily report of "Nov 20: 3 orders, Nov 21: 2 orders."

If daily reporting is a primary query path, a tailored read table can make `order_day` the first clustering column:

```sql
CREATE TABLE IF NOT EXISTS orders_by_store_month_day (
    store_id uuid,
    month_bucket text,
    order_day date,
    order_id uuid,
    amount_cents bigint,
    PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
) WITH CLUSTERING ORDER BY (order_day ASC, order_id ASC);
```

When the application **writes to this second table** for the same business events, it can query:

```sql
-- Illustrative query on the second table; load data first.
SELECT order_day,
       count(*) AS orders_per_day,
       sum(amount_cents) AS amount_per_day
FROM orders_by_store_month_day
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
```

The benefit is that the day is now a **clustering column eligible for primary-key-prefix grouping**. In return, the denormalized table must be inserted, updated, and deleted consistently per business policy. The lesson is not "create a new table whenever `GROUP BY` is mentioned," but rather **your data model must match the questions you need to answer**.

If you only need daily stats for a small dataset already fetched into Java, the application can also aggregate over a bounded partition in memory. That still transfers/reads multiple rows to the client and must account for payload limits, latency, and concurrent writes.

## 8. Do LIMIT, PER PARTITION LIMIT, and Paging Make COUNT Faster?

### 8.1. LIMIT 1 Does Not Make COUNT(*) Inspect Only One Row

```sql
SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 1;
```

In modern Cassandra, `COUNT(*)` is not turned into "count at most one row" simply by adding `LIMIT 1`. The aggregate returns **one result row**, and capping output does not bypass the work of **processing matching rows to compute the number 5**. On the lab data, `order_count` is still **5**.

Contrast this with:

```sql
SELECT order_id, created_at
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 1;
```

The second query does not aggregate across the partition; it asks for at most **one data row** in clustering order. That is a huge difference in both intent and potential cost.

**Version note:** Very old Cassandra 2.1 docs once interpreted `LIMIT` on `COUNT` differently. Starting with Cassandra 2.2 and modern releases, never rely on a `COUNT(*) ... LIMIT N` trick expecting it to "count at most N rows." Verify behavior on your cluster version if any logic depends on this detail.

### 8.2. PER PARTITION LIMIT Does Not Replace Summary Tables Either

`PER PARTITION LIMIT n` caps the number of **result rows per partition** in CQL syntax, primarily useful for row-level `SELECT` queries. When combined with aggregates or `GROUP BY`, distinguish **source rows processed**, **groups formed**, and **result rows emitted**; never assume `PER PARTITION LIMIT 1` creates an O(1) counter per partition.

If your goal is **counting all orders per month**, `PER PARTITION LIMIT 1` is not a way to produce a precomputed total per month. Design key-scoped aggregates, narrow ranges, or read from a summary table.

### 8.3. Page Size Only Throttles Fetching, Not Aggregate Scope

The Java driver has page size and paging state—two concepts distinct from `LIMIT`:

| Mechanism | Primary effect | Does it make a full-table COUNT cheap? |
| --- | --- | --- |
| `WHERE` full partition key | Targets the partition to read | **Can narrow scope**, though matching rows still must be inspected. |
| Clustering range conditions | Bounds the row slice inside a partition | **Can shrink the counted set.** |
| `LIMIT` | Caps returned result rows | **Does not eliminate aggregate computation cost.** |
| `PER PARTITION LIMIT` | Caps result rows per partition | **Not an index or precomputed counter.** |
| Driver page size | Throttles fetching across pages | **Does not shrink the scope of the count.** |
| Driver paging state | Resumes the exact same query | **Does not create a snapshot or precomputed aggregate.** |

If an API needs to paginate an order list, fetch `pageSize + 1` rows or use paging state to detect whether a next page exists per API policy; avoid running an extra full-table `COUNT(*)` on **every request just to render a total page count**.

## 9. Actual Read Cost: From Partition to SSTable

### 9.1. A Simple Estimation Model

Compare the following scopes:

| Query pattern | Partition-key candidates | Matching rows in lab | Note |
| --- | ---: | ---: | --- |
| Store A, `2026-11`, no clustering range | 1 | 5 | Counts one partition, not a full-table read. |
| Store A, `2026-11`, `created_at` in `[09:00,10:00)` on day 20 | 1 | 2 | Counts a small slice of one partition. |
| Store A, `month_bucket IN ('2026-11','2026-12')` | 2 | 7 | Aggregates across two partitions. |
| `SELECT COUNT(*) FROM orders_by_store_month` | All partitions in the table | 8 | Broad scan; suitable only for tiny labs. |

The numbers above count **matching rows and candidate partitions in the sample data**—they do not measure exact network messages or disk blocks read.

Conceptually:

```text
API / Java driver
       |
       v
Coordinator
       |
       +--> locate partition via partition key token
       |
       +--> contact replicas per consistency / topology
                 |
                 +--> memtable and SSTables
                 +--> handle tombstones / TTL / reconciliation
                 +--> live rows matching WHERE
                                   |
                                   v
                                COUNT / SUM / AVG ...
                                   |
                                   v
                              one / few result rows
```

**Reading multiple replicas does not multiply the count by the replication factor.** Three replicas storing copies of the same logical data do not cause `COUNT(*)` to triple the order count. Replication and consistency affect execution mechanics and visible data, not the logical row-counting semantics of the table.

### 9.2. Factors That Make Queries Slow Despite Small Output

| Factor | Observable impact |
| --- | --- |
| **Many partitions** | Fan-out and coordination across many tokens/nodes; coordinator pressure. |
| **Oversized partition** | Even a single-partition `COUNT(*)` must scan many rows inside it. |
| **Tombstones, TTLs** | Expired/deleted cells must be traversed to count only live rows. |
| **Many SSTables and lagging compaction** | Higher read amplification; one logical row may require merging fragments across files. |
| **Out-of-sync replicas / pending repair** | Higher reconciliation overhead and differing results across consistency levels. |
| **Higher consistency level** | May wait on more replicas; trades off freshness, availability, and latency. |
| **Concurrent reads and retries** | Amplifies coordinator/replica load; unbounded retries risk retry storms. |

A **qualitative estimation formula** (not a formal cost model):

```text
Read cost of COUNT
  ~ work to locate/read selected partitions
  + work to scan inspected rows/cells
  + handling expired data, tombstones, and reconciliation
  + network, replica, and coordination overhead

Output row count is usually tiny (1 or number of groups).
```

### 9.3. Tracing and Metrics to Monitor

In a small lab, you can enable tracing in `cqlsh` to observe a query's execution path:

```sql
TRACING ON;

SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

TRACING OFF;
```

In production, enable tracing **selectively** per operational policy to avoid adding overhead. Key signals to monitor:

- Read latency p50/p95/p99 per query/endpoint, timeouts, and `Unavailable` errors.
- Partitions read, partition sizes, and partition skew.
- Tombstone warnings, queries scanning excessive tombstones, and read amplification.
- SSTable/memtable counts, compaction throughput, repair duration, and replica health.
- Coordinator load, concurrency, speculative execution, retry counts, and consistency levels.

Never try to "optimize" `COUNT` simply by raising timeouts: longer timeouts mask symptoms while the cluster keeps doing overly wide reads or remains overloaded.

## 10. Java Driver: Reading Typed Aggregates and Bounding Scope

Examples with **Apache Cassandra Java Driver 4.x** and Java 15+ (text blocks). Assume an active `CqlSession session` connected to keyspace `cassandra_aggregate_lab`.

### 10.1. Counting and Summing Within One Partition

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

UUID storeId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);

PreparedStatement prepared = session.prepare("""
    SELECT count(*) AS order_count,
           count(amount_cents) AS priced_count,
           sum(amount_cents) AS total_cents
    FROM orders_by_store_month
    WHERE store_id = ?
      AND month_bucket = ?
    """);

BoundStatement statement = prepared.bind(storeId, "2026-11");
Row row = session.execute(statement).one();
if (row != null) {
    long totalOrders = row.getLong("order_count");
    long pricedOrders = row.getLong("priced_count");
    long totalCents = row.getLong("total_cents");
    System.out.printf("%d orders, %d priced, %d cents%n",
        totalOrders, pricedOrders, totalCents);
}
```

With the sample data, this prints `5 orders, 4 priced, 75000 cents`. CQL `COUNT` returns a numeric counter type (typically `bigint`); `SUM(amount_cents)` on `bigint` input can be read with `getLong` under current signatures. If you change `CAST` or column types, update the Java getters accordingly.

**Important:** `setPageSize(...)` on an aggregate statement does not make Cassandra count only one page of the partition. Page size governs result transmission, not turning a large-set count into a metadata read.

### 10.2. Binding a Time Range to Count Only Needed Data

```java
import java.time.Instant;

PreparedStatement byWindow = session.prepare("""
    SELECT count(*) AS matching_orders
    FROM orders_by_store_month
    WHERE store_id = ?
      AND month_bucket = ?
      AND created_at >= ?
      AND created_at < ?
    """);

BoundStatement window = byWindow.bind(
    storeId,
    "2026-11",
    Instant.parse("2026-11-20T09:00:00Z"),
    Instant.parse("2026-11-20T10:00:00Z")
);

Row one = session.execute(window).one();
long matchingOrders = one == null
    ? 0L
    : one.getLong("matching_orders");
System.out.println(matchingOrders); // 2 in sample data
```

In a production API, `store_id` must come from an authenticated/authorized context, not just an unvalidated client URL parameter. `month_bucket` must be validated against business conventions; never let clients pass thousands of months to trigger unbounded scans.

### 10.3. Latency, Consistency, and Errors

- **Timeouts / unavailable:** evaluate read scope, partition count, consistency, replica health, and cluster resources; tune retries around idempotency and load rather than retrying indefinitely.
- **`InvalidQuery`:** usually caused by unsupported key conditions, filters, or ordering; raising timeouts will not fix it.
- **Discrepancies across reads:** may stem from concurrent writes/deletes/TTLs between requests or unconverged replicas. Define freshness requirements before choosing `LOCAL_ONE`, `LOCAL_QUORUM`, or another level.
- **Overload protection:** bound concurrency, set sensible request timeouts, and track p95/p99 latency. If a dashboard polls the exact same count continuously, consider a summary table or a cache with a suitable TTL.

## 11. When Should You Avoid Direct COUNT?

### 11.1. Comparing Strategies

| Requirement | Suitable approach | Trade-off |
| --- | --- | --- |
| Count a few hundred rows in a known partition at low QPS | Direct `COUNT(*)` with full partition key | Simple; cost grows with data processed. |
| Count within a narrow clustering window | `COUNT(*)` with two time bounds | Bounds scope, though rows in the window are still read. |
| Dashboard needing system-wide order counts every second | Summary table / stream aggregator | Cheap reads; must maintain totals and handle replays/edits/deletes. |
| Large reports across many partitions | Batch analytics/ETL/warehouse | Fits heavy aggregation; incurs update lag and pipeline overhead. |
| Simple increment/decrement event counting | Counter column if semantics fit | Requires special care for retries, idempotency, drift, and reconciliation. |
| Checking if an order exists by full primary key | Single-key-column point lookup | Reports existence without unnecessary aggregate work. |

### 11.2. Summary Tables Read Faster Than Historical COUNT

If the product frequently needs order counts and total revenue by **store/month**, design a summary table:

```sql
CREATE TABLE IF NOT EXISTS monthly_order_summary (
    store_id uuid,
    month_bucket text,
    order_count bigint,
    priced_count bigint,
    total_cents varint,
    updated_at timestamp,
    PRIMARY KEY (store_id, month_bucket)
);
```

Once a pipeline maintains these values accurately, reading the metrics is a single point lookup:

```sql
SELECT order_count, priced_count, total_cents, updated_at
FROM monthly_order_summary
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

`CREATE TABLE` only defines the schema; it **does not populate or update summaries automatically** from the orders table. The application needs event-driven updates for order creation, cancellation, refunds, deletions, and backfills. `total_cents` may need to handle value adjustments, not just blind additions on every write.

A design pattern worth considering:

```text
Order event (with unique event_id)
    |
    v
Pipeline validates + deduplicates events (idempotent)
    |
    +--> write orders_by_store_month
    |
    +--> update monthly_order_summary
                |
                v
       API reads 1 summary row

Periodically reconcile summary against source data by bucket.
```

Writes across multiple partitions/tables are not automatically atomic like a cross-table SQL transaction. Define how to recover when one write succeeds and the other fails, using idempotency keys, bounded retries, and reconciliation jobs.

### 11.3. Be Careful with Counter Columns

Cassandra has a `counter` type suitable for certain increment/decrement patterns. However:

- Never treat `counter` as an automatic `COUNT(*)` of another table; the application must perform the updates.
- Counter increments are **not naturally idempotent**: if a request executes and is then retried, it risks double-counting unless handled carefully in application logic.
- Counter tables have different schema and write restrictions than regular tables; do not mix arbitrary regular columns with counters in the same way.
- For events that can change status, cancel, or replay, you need compensating updates and reconciliation rather than simply incrementing on every seen event.

Therefore, choose **`counter`** only when the event model and accuracy tolerances genuinely fit; otherwise, a summary table updated from an idempotent event stream or an analytical store may be easier to operate.

## 12. Common Mistakes

| Statement / query | Issue | How to handle it |
| --- | --- | --- |
| `SELECT COUNT(*) FROM orders_by_store_month` returns 1 number so it's cheap | May scan the entire table/cluster. | Always scope with `WHERE`, bucketing, or summary tables. |
| `COUNT(1)` reads metadata faster than `COUNT(*)` | Both count matching rows the same way. | Pick the clearer syntax; do not treat `COUNT(1)` as a special optimization. |
| `COUNT(amount_cents) = COUNT(*)` always | Column values may be missing/null or TTL-expired. | Distinguish row count from non-null value count. |
| `COUNT(status)` gives the number of distinct statuses | It counts **non-null `status` values**, not distinct ones. | Design a grouping/summary path if per-status counts are needed. |
| `COUNT(*) ... LIMIT 1` processes only one raw row | `LIMIT` caps aggregate output, not turning it into an O(1) counter. | Bound scope in `WHERE` or use a summary table. |
| `WHERE status = 'PAID'` will be auto-optimized by `COUNT` | `status` is an unindexed regular column in the lab schema. | Change table model, add an appropriate index, or use an aggregation pipeline. |
| `SUM` always stays exact with `bigint` | Can overflow; `AVG` can round/truncate fractional parts. | `CAST` inputs and verify data types. |
| `MIN(amount)` plus `order_id` returns the smallest order's ID | Non-aggregated columns may come from the first row, not the min row. | Separate "min value" from "row holding min value." |
| Arbitrary `GROUP BY` on any column like SQL | CQL enforces primary-key grouping rules. | Build query-driven tables or aggregate externally. |
| Driver page size 50 makes `COUNT` inspect only 50 orders | Page size only controls result fetching. | Bound scope by keys; do not confuse paging with aggregate cost. |
| With `RF=3`, `COUNT` must be multiplied by three | Replicas store copies of the same logical rows. | Never multiply by RF; choose business-appropriate consistency. |
| `COUNT` returns "the absolute ground truth at all times" | Concurrent writes, TTLs, and unconverged replicas can change counts. | Define freshness SLAs, reconciliation, and consistency levels. |

## 13. Exercises with Answers

### Exercise 1. Counting Priced vs. Unpriced Orders

**Question:** In store A's `2026-11` partition, how many total rows exist, how many have `amount_cents`, and what is the difference?

**CQL Answer:**

```sql
SELECT count(*) AS total_orders,
       count(amount_cents) AS priced_orders
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Results: `5` and `4`; a difference of **1** row without `amount_cents`.

### Exercise 2. Total Amount for One Day

**Question:** Compute the total `amount_cents` for Nov 20, store A only, without reading Nov 21.

**Answer:**

```sql
SELECT count(*) AS orders_on_day,
       sum(amount_cents) AS total_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at >= '2026-11-20 00:00:00+0000'
  AND created_at <  '2026-11-21 00:00:00+0000';
```

Result: **3 orders**, **55,000 cents**. This is a UTC timestamp range, not implicitly the buyer's local calendar day.

### Exercise 3. Why Can Full-Table COUNT(*) Time Out?

**Question:** A table holds 200 million orders across many nodes. A dashboard executes `SELECT COUNT(*) FROM orders_by_store_month;` on every page load, even though the output is a single number. Name at least three risk factors.

**Suggested answer:** No partition key in `WHERE` forces inspecting data across many partitions/tokens; live rows must be resolved past TTLs/tombstones and potentially across multiple SSTables; multi-replica/coordinator work combined with concurrent traffic drives up latency or causes timeouts. The fix is a summary/counter/pipeline tailored to semantics and reconciliation—not merely raising timeouts.

### Exercise 4. Does LIMIT 1 Alter Counting?

```sql
SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 1;
```

**Answer:** On modern Cassandra, `order_count` is still **5**. `LIMIT 1` does not mean only one row is processed to compute the aggregate. If you only want to inspect **one order**, use `SELECT order_id ... LIMIT 1` instead of counting.

### Exercise 5. Distinguishing Numeric Output from Business Meaning

**Question:** For store A / Nov, `SUM(amount_cents)` is `75,000`. Can we immediately label this "paid revenue"?

**Answer:** **No.** The row set includes `CREATED` and `CANCELLED` statuses; `SUM(amount_cents)` does not filter by status. You need explicit business rules and a schema/query/summary reflecting only qualifying statuses.

### Exercise 6. AVG and Missing Values

**Question:** In store A's November partition, there are five orders but only four price values. What is the average `amount_cents` of the priced rows?

**Answer:** `(10000+15000+30000+20000)/4 = 18750` cents. CQL:

```sql
SELECT avg(CAST(amount_cents AS decimal)) AS avg_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Do not use five as the denominator when the metric is defined as the average of **non-null values**.

## 14. Checklist Before Putting COUNT into Production

1. **Problem:** Do you need to count live rows, non-null columns, by status, by day, or a custom business KPI?
2. **Scope:** Does the query include the full partition key? Can a clustering range narrow it? If using `IN`, how many candidate partitions exist?
3. **Size:** How many rows and tombstones live in each partition? Is counting cost acceptable at p95/p99 and peak concurrency?
4. **Syntax:** `COUNT(*)` vs. `COUNT(column)`, and what types do `SUM`/`AVG` use? Is `CAST` needed to prevent truncation/overflow? Does `GROUP BY` match the primary key?
5. **Limits:** Do you understand that `LIMIT` and driver paging do not make aggregates cheap?
6. **Distribution:** How do replication, consistency, compaction/repair, and retries impact latency and result freshness?
7. **Redesign:** If dashboards poll continuously or need cluster-wide totals, do you have a summary/pipeline/counter with proper idempotency, reconciliation, and backfill?
8. **Java:** Are types bound properly, getters matched to aggregate types, timeouts/concurrency bounded, and full-table scans kept off hot request paths?

**Core takeaway:** `COUNT(*)` in Cassandra is **not an instant metadata lookup of total row count**. It aggregates over the rows that must be read and evaluated per `WHERE`, data state, and consistency. Use **partition keys and clustering ranges** to minimize cost whenever possible; for large or frequent metrics, prefer a **summary/query model** tailored to your product requirements.

## References

- [Apache Cassandra Documentation — Functions: COUNT, MIN, MAX, SUM, AVG](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html)
- [Apache Cassandra Documentation — CQL Data Manipulation: WHERE, GROUP BY, LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: PRIMARY KEY and CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
