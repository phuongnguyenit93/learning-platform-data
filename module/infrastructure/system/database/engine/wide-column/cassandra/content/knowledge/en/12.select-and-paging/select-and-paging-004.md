# IN, Composite Keys, and Partition Fan-Out in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Explain why `IN` represents a set of **discrete** values rather than a range scan, and distinguish among partitions accessed, rows returned, and replicas contacted.
2. Analyze how Cassandra locates partitions with a **composite partition key**, especially when `IN` is applied to the last partition key component.
3. Count or estimate the number of **full partition keys** produced by a query or batch of queries.
4. Distinguish `IN` on the **partition key** from `IN` on the **final clustering column**: two queries can have identical list lengths yet very different distributed costs.
5. Use `LIMIT` and `PER PARTITION LIMIT` properly, and recognize ordering and pagination issues when reading across multiple partitions.
6. Choose bucketing strategies, bound `IN` lists, and implement queries in the Java driver suited to real-world traffic.

This lesson is part of the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. In Apache Cassandra's wide-column model, read efficiency depends directly on the **partition key**, query-driven table design, and distributed cluster topology. `IN` is convenient for a known list of partitions, but each additional value can generate extra read work and replica communication. Read/write consistency levels, replication, compaction, repair, and Java application error handling all shape actual latency.

## 1. Review: Primary Key, Composite Partition Key, and Clustering Columns

Consider the primary key:

```sql
PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)
```

Each component has a distinct role:

| Component | Role | Consequence |
| --- | --- | --- |
| `tenant_id` + `day_bucket` | **Composite partition key** (two combined values) | Together they are hashed into a token to find the replicas holding the partition. |
| `created_at` | First clustering column | Orders orders chronologically within the partition. |
| `order_id` | Second clustering column | Disambiguates orders sharing the same `created_at`. |
| All four columns | **Full primary key** | Uniquely identifies at most one row in the table. |

Do not confuse these two schemas:

```sql
-- A. EACH (tenant_id, day_bucket) IS ONE PARTITION.
PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)

-- B. EACH tenant_id IS ONE PARTITION.
-- day_bucket is the first clustering column.
PRIMARY KEY (tenant_id, day_bucket, created_at, order_id)
```

In schema **A**, different days for the same tenant are distinct partitions. In schema **B**, all days for the same tenant belong to **a single partition** and are sorted by `day_bucket`. Therefore, multi-day queries have different costs and `WHERE` rules despite identical column names.

For schema **A**, visualize it as:

```text
tenant_id = A
   |
   +-- (A, 2026-11-20) --> token P20 --> replicas owning partition P20
   |
   +-- (A, 2026-11-21) --> token P21 --> replicas owning partition P21
   |
   +-- (A, 2026-11-22) --> token P22 --> replicas owning partition P22

Each partition holds rows ordered by (created_at, order_id).
P20, P21, P22 are not necessarily on the same node or adjacent on the token ring.
```

The token is computed from the **entire** partition key; fixing `tenant_id` does not create a contiguous storage region by `day_bucket`. That is the starting point for understanding `IN`.

## 2. Creating Sample Data Runnable in cqlsh

Consider a multi-tenant application storing orders in daily buckets to bound each partition's size. Each day typically holds multiple orders per tenant.

```sql
-- Only use replication_factor = 1 in a single-node lab.
CREATE KEYSPACE IF NOT EXISTS cassandra_in_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_in_lab;

CREATE TABLE IF NOT EXISTS orders_by_tenant_day (
    tenant_id uuid,
    day_bucket date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount_cents bigint,
    PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000011, 'CREATED', 129900
);

INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000012, 'PAID', 259900
);

INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21', '2026-11-21 10:15:00+0000',
    00000000-0000-4000-8000-000000000013, 'PAID', 49900
);

INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-22', '2026-11-22 13:00:00+0000',
    00000000-0000-4000-8000-000000000014, 'SHIPPED', 80000
);

-- Second tenant: does not share partitions with the first tenant.
INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000015, 'CREATED', 99000
);
```

**Data layout after loading:**

| Partition key | Rows in sample data | `order_id` values (suffix) |
| --- | ---: | --- |
| Tenant A, Nov 20 | 2 | `...0011`, `...0012` |
| Tenant A, Nov 21 | 1 | `...0013` |
| Tenant A, Nov 22 | 1 | `...0014` |
| Tenant B, Nov 20 | 1 | `...0015` |

There are **four populated partitions**, containing **five rows** in total. We will use these numbers to distinguish *partitions queried*, *non-empty partitions*, and *rows returned*. `INSERT` on the same full primary key is an upsert; re-running the script does not duplicate rows.

## 3. What Does IN in WHERE Mean?

`x IN (v1, v2, v3)` specifies a set of candidate values, logically similar to `x = v1 OR x = v2 OR x = v3`. However, CQL **does not support arbitrary `OR` expressions**, and where `IN` is permitted depends on the primary key structure and Cassandra version.

Example on the **last component of a composite partition key**:

```sql
SELECT day_bucket, created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21');
```

This query evaluates **two full partition keys**:

```text
P1 = (tenant A, 2026-11-20)
P2 = (tenant A, 2026-11-21)

           +--> P1: 2 rows
Coordinator|
           +--> P2: 1 row

Total: 2 partitions, 3 rows returned from the sample data.
```

Points to keep in mind:

- `IN` enumerates **specific values**; it does not represent a continuous interval from the smallest to largest date.
- For tenant A and the list above, **two separate partitions** are targeted even though both belong to the same tenant.
- If one of the days has no data, that partition key is still a **candidate to look up**, even though the result contains zero rows for that day.
- The number of elements in `IN` is **not** the row count; each partition can hold 0, 1, or thousands of rows.
- Multi-partition results provide **no global chronological ordering guarantee across days/timestamps** merely because each partition has its own clustering order.

When you only need a single day, querying with `=` expresses intent more clearly:

```sql
SELECT created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20';
```

This touches **one partition**, not two. In the sample data, that partition has two rows.

## 4. IN Rules on Composite Keys

### 4.1. IN on the Last Component of the Partition Key

Per CQL documentation, the commonly supported position is the **last column of the partition key**, with all preceding components constrained by equality.

For:

```sql
PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)
```

the following query fits:

```sql
SELECT day_bucket, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22');
```

Since `tenant_id` is fixed, each `day_bucket` value completes a full partition key.

Do not swap the roles of the two components:

```sql
-- Invalid under the IN rules for this composite partition key:
-- IN is not on the last column of the partition key.
SELECT order_id
FROM orders_by_tenant_day
WHERE tenant_id IN (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
)
AND day_bucket = '2026-11-20';
```

To fetch multiple tenants for the same day under this schema, the application can send **one query per tenant with the full partition key** or use a separate read table if this is a primary access pattern. An API may need to look up multiple independent keys; not every set of keys can be expressed in **one valid CQL `IN` query**.

### 4.2. If the Partition Key Has Only One Column

Suppose a separate table is defined as:

```sql
CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id uuid PRIMARY KEY,
    display_name text,
    default_locale text
);
```

In this table, `tenant_id` is both the first and the **sole final component** of the partition key. Therefore:

```sql
SELECT tenant_id, display_name, default_locale
FROM tenant_settings
WHERE tenant_id IN (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
);
```

is a valid query targeting **two settings partitions**; if both exist, it returns at most two rows because the table has no clustering columns. Being able to use `IN` on `tenant_id` in this table **does not mean** you can use it the same way on the leading `tenant_id` component of the composite partition key in the orders table.

### 4.3. Three-Component Composite Key: Must Fix the Prefix

Imagine another table with:

```sql
PRIMARY KEY ((tenant_id, region_id, day_bucket), created_at, order_id)
```

A query for one tenant, one region, and multiple days looks like:

```sql
-- Illustrates the key rules for a hypothetical table.
SELECT created_at, order_id
FROM orders_by_tenant_region_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND region_id = 'north'
  AND day_bucket IN ('2026-11-20', '2026-11-21');
```

This yields **two composite partition keys**:

1. `(tenant A, north, 2026-11-20)`
2. `(tenant A, north, 2026-11-21)`

The `tenant_id = ...` and `region_id = ...` conditions fix the prefix; `IN` sits on the final component `day_bucket`. Never assume Cassandra can infer all regions or all days if a partition key component is omitted. The table name `orders_by_tenant_region_day` is purely illustrative of the key structure; no DDL for it is run in this lab.

## 5. IN on a Clustering Column: Value Count Does Not Equal Partition Count

`IN` is also supported on the **final column of the entire primary key** when preceding columns are properly constrained.

In the lab table:

```sql
PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)
```

`order_id` is the final column of the primary key. Let's query two orders sharing `created_at`:

```sql
SELECT day_bucket, created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at = '2026-11-20 09:00:00+0000'
  AND order_id IN (
      00000000-0000-4000-8000-000000000011,
      00000000-0000-4000-8000-000000000012
  );
```

This statement also has **two elements in `IN`**, yet it reads **only one partition** because the `(tenant_id, day_bucket)` pair is fixed. Here `IN` selects two clustering key values **within the partition**, matching up to two rows. Compare:

| Query | `IN` elements | Partitions targeted | Rows in sample data |
| --- | ---: | ---: | ---: |
| `day_bucket IN (20, 21)`, fixed tenant A | 2 | 2 | 3 |
| `order_id IN (11, 12)`, fixed tenant A / day 20 / `created_at` | 2 | 1 | 2 |
| `day_bucket = 20`, fixed tenant A, no `IN` | — | 1 | 2 |

**Position takeaway:** to determine partition count, look at the **full partition key** first, then examine the elements inside `IN`. Counting commas in an `IN` list without checking which column it constrains leads to wrong estimates.

Do not use `IN` arbitrarily on the leading clustering column of a multi-column primary key:

```sql
-- Invalid under standard IN rules for this schema:
-- created_at is not the last column of the full primary key.
SELECT order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at IN (
      '2026-11-20 09:00:00+0000',
      '2026-11-20 10:00:00+0000'
  );
```

When you need to list **complete clustering key tuples**, CQL also supports `(created_at, order_id) IN ((t1, id1), (t2, id2))` for clustering tuples. This still selects rows **within one partition** once the partition key is fixed; it does not multiply partitions.

## 6. Counting Partitions Targeted: Formula and Limits

Given the query:

```sql
WHERE tenant_id = :tenant
  AND day_bucket IN (:day1, :day2, :day3)
```

let `K` be the set of **full partition key** values represented by the statement. Then:

```text
Partition-key candidate count = |K|

tenant_id = A, day_bucket IN (D1, D2, D3)
K = {(A,D1), (A,D2), (A,D3)}
|K| = 3 (assuming three distinct days)
```

Assuming the days are valid and distinct, **three candidate keys** correspond to three partitions to locate. If a partition contains no data yet, the query still looks up that key, returning zero rows for that partition.

### 6.1. Quantitative Examples

| Scenario | Candidate partition keys |
| --- | ---: |
| One tenant and one day with `=` | 1 |
| One tenant and three days in `IN` | 3 |
| One tenant and 30 distinct days in `IN` | 30 |
| 4 tenants, each querying 7 days in separate requests | Up to 28 distinct keys **across the batch** |
| One tenant, one day, 10 `order_id` values in clustering `IN` | 1 |
| One tenant, three days in `IN`, only two days populated | 3 candidate keys; 2 non-empty partitions |

In row four, `4 × 7 = 28` is an **application-level** count when issuing four separate requests of seven distinct days each; it **does not imply** you can write one CQL query with two `IN` lists on a composite partition key.

Across multiple queries `Q1, Q2, ...`, you can track two distinct metrics:

- **Per-request partition lookups:** sum the partition-key candidates of each request, even if the same key is queried repeatedly.
- **Unique partitions across the batch:** count the union of full key sets `|K1 ∪ K2 ∪ ...|`; duplicate keys are counted only once here.

These are two different metrics. For example, two requests both querying tenant A / day 20 produce **two partition lookups** while referring to **only one unique partition** by identity.

### 6.2. Partitions ≠ Rows ≠ Nodes ≠ Replicas

You cannot deduce the exact number of network messages or SSTables read solely from the number of keys in `IN`:

| Metric | Example | Depends on |
| --- | --- | --- |
| **Partition candidates** | 3 keys `(A, D1..D3)` | The query's list of full partition keys. |
| **Rows returned** | 0, 3, or thousands of rows | Rows per partition, clustering predicates, tombstones, `LIMIT`. |
| **Nodes involved** | One or more nodes | Token placement, topology, replication, and routing. |
| **Replicas contacted** | Can vary per request | Read consistency level, replica health, speculative retry, read repair/reconciliation. |
| **Actual I/O** | Few or many SSTables/cells | Caches, memtables, SSTable layout, compaction, tombstones. |

For example, a replication factor of `RF=3` **does not mean** every three-key `IN` query sends exactly nine replica requests. The actual replicas contacted depend on consistency level (e.g., `LOCAL_ONE` vs. `LOCAL_QUORUM`), availability, driver/coordinator settings, and read-repair behavior. Still, increasing partition candidates generally increases coordination overhead.

### 6.3. Estimating Fan-Out Before Sending Queries

In a Java service, you can compute this upfront:

```text
request: tenant=A, days=[20, 21, 22]
distinct days = 3
candidate partition keys = 3

request: tenant=A, days=[20, 20, 21]
distinct days after normalization = 2
candidate partition keys = 2

request batch: 5 tenants x 14 dates
up to 70 distinct full partition keys across the batch
```

Always **deduplicate values on the client**, enforce caps on day/tenant counts, and reject or throttle overly broad requests according to product rules. Normalizing inputs makes key estimates predictable; do not assume the server will optimally handle arbitrary duplicate lists.

## 7. IN vs. Range Queries: When to Use Each

In `orders_by_tenant_day`, `day_bucket` is part of the partition key, so:

```sql
-- Valid: enumerates specific days.
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22');

-- Not a valid range query on this table's partition key.
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket >= '2026-11-20'
  AND day_bucket < '2026-11-23';
```

Date ranges do not follow the physical order of partitions hashed from the key pair. `IN` fits when the application knows and bounds a **specific set of buckets**, not because it turns a partition key into a range-indexed column.

Conversely, `created_at` is the first clustering column. Inside a single partition, querying by time range is a direct read pattern:

```sql
SELECT created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at >= '2026-11-20 08:00:00+0000'
  AND created_at < '2026-11-20 10:00:00+0000';
```

Results for this pattern come from **one partition**, because the full partition key is fixed. The two rows sharing the `09:00` timestamp remain distinguished by `order_id`.

Choose bucket granularity based on workload: buckets that are too small force history queries across many partitions; buckets that are too large create hot partitions and heavy read/compaction/repair costs. There is no single "daily" bucket optimal for every system—base it on write density, row size, retention, and critical query paths.

## 8. LIMIT, PER PARTITION LIMIT, and Pagination Issues

The two limits below have different scopes:

```sql
-- At most 2 rows for the entire CQL result.
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
LIMIT 2;

-- At most 1 row from each queried partition.
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 1;
```

On the sample data:

- The `LIMIT 2` query returns **no more than two rows total**, with no guarantee they are the "newest orders across all three days" without an explicit global merge/ordering strategy.
- The `PER PARTITION LIMIT 1` query allows at most **one row per day**, so across three populated partitions it can return three rows (one per partition).
- You can combine `PER PARTITION LIMIT 1 LIMIT 2`: **both limits** apply together, yielding at most two rows in total.

**Design warning:** Cassandra's `ORDER BY` is based on clustering columns and is not equivalent to a global `ORDER BY created_at DESC` across all tenants and days. When fetching "the 20 newest orders for a tenant" across multiple buckets, define the merge logic, allowed partition scan budget, and cursor/aggregation strategy explicitly. Do not assume `IN` + `LIMIT 20` solves cross-partition sorting.

The Java driver has **page size** and **paging state**, which differ from both `LIMIT` and `PER PARTITION LIMIT`:

- **Page size** controls how much data is fetched per round trip for the same query, not how many partitions an `IN` clause touches.
- **Paging state** resumes a specific query with the same parameters; it does not provide global ordering or an immutable snapshot across reads.
- There is no SQL-style `OFFSET` to skip N rows efficiently. If the business requires deep history and stable pagination, design the cursor and storage model from the start.

## 9. How Many IN Values Are Too Many?

There is no universal "safe `IN` list length for all clusters." Impact depends on individual partition sizes, replica count, token placement across nodes, consistency level, caches, SSTable/tombstone counts, and concurrent request volume.

Compare these cases:

| Scenario | Usage note |
| --- | --- |
| Tenant A views orders for 2–3 selected days | A short `IN` list can be simple and predictable. |
| Tenant A requests 90 days, one partition per day | Fan-out of 90 partitions; measure latency and consider breaking into controlled batches. |
| API accepts thousands of days unbounded | High risk of fan-out, large payloads, timeouts, coordinator pressure, and cluster overload. |
| Two `order_id` values within one specific partition | `IN` on the final clustering column targets only one partition; distributed cost differs from two days. |
| Queries always need every day of an entire month | Consider an additional monthly-bucket or summary table depending on data density and load. |

**Operational design guidelines:**

1. Cap `IN` list length at the API boundary using a limit validated by benchmarking.
2. Deduplicate dates, validate tenant/date bounds, and reject invalid input before querying.
3. Bound concurrency if the application splits a date list into multiple `=` queries; never fire hundreds of parallel queries unchecked.
4. Measure p95/p99 latency, coordinator read latency, timeouts, retries, and read amplification via tracing/metrics; inspect partition sizes, tombstones, and compaction activity.
5. Choose replication and consistency according to freshness/availability SLAs; `IN` does not alter those trade-offs.

Both a massive `IN` query and hundreds of concurrent `=` queries can overload a cluster. Decisions should rely on empirical performance evidence and concurrency control, not merely CQL statement count.

## 10. Java Driver: Controlled Partition-List Queries

Assume `CqlSession session` is connected to keyspace `cassandra_in_lab`; the examples below use Java Driver 4.x and Java 15+ for text blocks.

### 10.1. Fixed Two-Day List

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

UUID tenantId = UUID.fromString("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");

PreparedStatement prepared = session.prepare("""
    SELECT day_bucket, created_at, order_id, status
    FROM orders_by_tenant_day
    WHERE tenant_id = ?
      AND day_bucket IN (?, ?)
    """);

BoundStatement bound = prepared.bind(
    tenantId,
    LocalDate.parse("2026-11-20"),
    LocalDate.parse("2026-11-21")
).setPageSize(100);

ResultSet resultSet = session.execute(bound);
for (Row row : resultSet) {
    System.out.printf("%s | %s | %s%n",
        row.getLocalDate("day_bucket"),
        row.getUuid("order_id"),
        row.getString("status"));
}
```

Here, `IN (?, ?)` has two bind markers for the two dates. The driver maps CQL `uuid` to `UUID` and CQL `date` to `LocalDate`. `setPageSize(100)` tunes page fetching; it **does not replace** `LIMIT` and does not restrict the query to a single partition.

The placeholder count must match the element count. When the number of days varies per request, the application can prepare statements for bounded sizes, bind a list parameter for `IN` if supported by the driver/CQL version in use, or split into individual `=` queries. Never concatenate user input directly into CQL as a literal value list.

### 10.2. Computing Fan-Out Ahead of Time and Validating Input

```java
import java.time.LocalDate;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

List<LocalDate> requestedDays = List.of(
    LocalDate.parse("2026-11-20"),
    LocalDate.parse("2026-11-20"),
    LocalDate.parse("2026-11-21")
);

Set<LocalDate> uniqueDays = new LinkedHashSet<>(requestedDays);
int candidatePartitions = uniqueDays.size(); // 2 for a fixed tenant

if (uniqueDays.isEmpty() || candidatePartitions > 14) {
    throw new IllegalArgumentException("Invalid date range");
}

// Next: build a parameterized query matching uniqueDays
// or issue point-partition reads with bounded concurrency.
```

The limit `14` here is strictly an **example API policy**, not a hard limit of Apache Cassandra. For a fixed tenant, `uniqueDays.size()` equals the number of **candidate** full partition keys; in multi-tenant execution, count unique `(tenant_id, day_bucket)` pairs.

**Do not assume each Java driver page corresponds to one partition.** Multi-partition queries can span multiple pages; record mapping should retain `day_bucket` and key fields to associate rows with the right tenant/day. If a global ranking by `created_at` is required, define an explicit merge strategy and data bounds.

## 11. Common Mistakes

| Misconception | Key truth to remember | How to handle it |
| --- | --- | --- |
| `IN (D1,D2,D3)` reads one partition because `tenant_id` is known | Composite partition key consists of **tenant and day**; each day forms a distinct full key. | Count the `(tenant_id, day_bucket)` pairs. |
| An `IN` list with 3 values always returns 3 rows | Each partition holds a varying number of rows and may be empty. | Distinguish candidate keys from returned rows. |
| `IN` on `order_id` behaves like `IN` on `day_bucket` | `order_id` is the last clustering column; `day_bucket` is part of the partition key. | Check where `IN` sits in the schema. |
| `tenant_id IN (...) AND day_bucket = D` works just like `day_bucket IN (...)` | `tenant_id` is not the final component of the composite partition key. | Issue per-tenant queries or create another query table. |
| `day_bucket >= D1 AND day_bucket < D2` is a range scan within a tenant | `day_bucket` is part of the partition key; partitions are distributed by token. | Enumerate finite buckets or redesign the schema. |
| `LIMIT 10` means at most 10 partitions are contacted | `LIMIT` caps **result rows**, without shrinking the `IN` candidate key set. | Bound the key list and buckets at request time. |
| `PER PARTITION LIMIT 1` means one row total | It caps **each partition**; multiple partitions can return multiple rows. | Combine with `LIMIT` if a total cap is needed. |
| `RF=3` means querying 10 partitions always sends 30 read requests | Contacted replicas also depend on consistency level and query execution mechanics. | Monitor driver/coordinator metrics instead of assuming fixed request counts. |
| `IN` provides global clustering order | Clustering order applies within each individual partition. | Design merge/cursor logic or a dedicated table for the required order. |
| Adding `ALLOW FILTERING` fixes missing partition key queries | Can force expensive data scans with unpredictable latency. | Redesign the access path; avoid cluster-wide filtering on hot APIs. |

## 12. Practice Exercises with Answers

### Exercise 1: Counting Partitions for IN on a Composite Key

Given `PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)`, one fixed tenant, and the date list `[20, 21, 22]` of November 2026, how many partitions does the query target?

**Answer:** **3 candidate partitions**, corresponding to `(tenant A, 20)`, `(tenant A, 21)`, and `(tenant A, 22)`. The row count can exceed three. CQL:

```sql
SELECT day_bucket, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22');
```

With the sample data, this returns **4 rows** from **3 partitions**, not three rows.

### Exercise 2: IN on a Clustering Column

For tenant A on Nov 20, fetch the two orders at `09:00` with IDs ending in `...0011` and `...0012`. How many partitions are targeted?

**Answer:** One partition, two rows:

```sql
SELECT created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at = '2026-11-20 09:00:00+0000'
  AND order_id IN (
      00000000-0000-4000-8000-000000000011,
      00000000-0000-4000-8000-000000000012
  );
```

### Exercise 3: Choosing LIMIT vs. PER PARTITION LIMIT

Retrieve at most **one order from each day** across three known days for tenant A.

**Answer:**

```sql
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 1;
```

The query returns at most **three rows** across the three known partitions. Do not replace `PER PARTITION LIMIT 1` with `LIMIT 1` if you want up to one row **for each day**.

### Exercise 4: Fan-Out Across Multiple Tenants

An audit job reads **5 tenants**, each with **7 distinct days**, issuing one `IN` query of seven days per tenant. How many distinct full partition keys can be involved?

**Answer:** `5 × 7 = 35` distinct full partition keys, assuming all five tenants are distinct; this is an aggregate total across **multiple requests**, not a single `WHERE tenant_id IN (...) AND day_bucket IN (...)` query. Populated partitions, rows returned, and replicas contacted must be measured separately.

### Exercise 5: Critiquing a Flawed "Optimization"

Proposal: "Change `day_bucket IN (D1, ..., D100)` to the same `IN` query plus `LIMIT 10`, so Cassandra reads at most 10 partitions."

**Answer:** Incorrect. `LIMIT` caps the number of **result rows**, not the 100 candidate partition keys. To reduce fan-out, shrink the bucket list queried, split requests into bounded batches, or redesign a table tailored to frequent cross-day queries.

## 13. Checklist Before Using IN in an API

1. **Read the primary key accurately:** identify which components belong to the partition key and which to clustering; never guess from column names.
2. **Check `IN` placement:** is `IN` on the last partition key column or the final column of the full primary key under supported syntax? Are preceding components properly constrained?
3. **Estimate fan-out:** after input normalization, how many full partition-key candidates exist? How many across all concurrent requests?
4. **Control volume:** do you reject overly long lists, oversized partitions, excessive page sizes, or excessive concurrency?
5. **Understand output:** what do `LIMIT` and `PER PARTITION LIMIT` mean here? Does the client expect global ordering when rows span multiple partitions?
6. **Distributed behavior:** how do replication, consistency, replica state, compaction/repair, tombstones, and retries affect latency? Have p95/p99 latencies been measured?
7. **Java integration:** are `UUID`/`LocalDate` bound with proper types, paging state managed safely, and timeouts tuned to query size?

Core takeaway: **count the full partition keys** a query actually targets. `IN` on the last component of a composite partition key can trigger **multiple partition reads**; `IN` on the final clustering key generally stays **within one partition**. That distinction matters far more than the raw element count in an `IN` list when writing CQL for distributed Cassandra systems.

## References

- [Apache Cassandra Documentation — Data Manipulation: WHERE, IN, ORDER BY, and LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Definition: Primary Key and Clustering Columns](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — CQL Single File Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
