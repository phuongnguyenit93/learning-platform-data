# LIMIT, PER PARTITION LIMIT, and Scope Boundaries in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish `LIMIT` (capping total result rows) from `PER PARTITION LIMIT` (capping rows taken from **each partition**).
2. Explain **scope boundaries** from three angles: the number of partitions accessed, the number of matching rows inside each partition, and the final number of rows returned.
3. Combine both limit clauses with `WHERE`, clustering order, and `ORDER BY` without confusion over ordering or results.
4. Predict results for CQL examples spanning multiple partitions with varying row counts, including empty or under-filled partitions.
5. Distinguish CQL result limits from **page size** and **paging state** in the Cassandra Java driver.
6. Recognize why `LIMIT 10` does not rescue a wide-scan query, does not guarantee only 10 rows are read from disk, and does not substitute for query-driven table design.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. In Apache Cassandra, a distributed wide-column database, the **partition key** locates where data is stored, **clustering columns** organize row order inside a partition, and **consistency level** governs which replicas are read. Limit clauses only have exact meaning in the context of the data model, partitioning, and Java application query requirements.

## 1. Three Questions to Separate When Reading a Query

Consider the general statement:

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = ?
  AND day_bucket IN (?, ?, ?)
PER PARTITION LIMIT 2
LIMIT 3;
```

To understand this statement, answer three **separate** questions:

| Question | Primary governing part | Meaning |
| --- | --- | --- |
| **Which partitions are selected to read?** | Partition key in `WHERE` | The set of full partition keys, potentially across multiple nodes. |
| **Within each partition, which rows can match?** | Clustering conditions, filters, clustering order | A contiguous slice or row set per key design; the count can be very large. |
| **At most how many rows are returned?** | `PER PARTITION LIMIT` and `LIMIT` | Per-partition cap and total result cap. |

A `SELECT` statement can target 100 partitions yet return only 5 rows. Conversely, querying a single partition can return thousands of rows if that partition is huge. Hence **rows returned is neither partitions accessed nor rows/cells inspected by the storage engine**.

## 2. Syntax and Semantic Rules

Standard syntax structure for the examples:

```sql
SELECT column_name [, column_name ...]
FROM keyspace_name.table_name
[WHERE primary_key_conditions]
[ORDER BY clustering_column [ASC | DESC] [, ...]]
[PER PARTITION LIMIT n]
[LIMIT m];
```

Here `n` and `m` are **positive integers** capping row counts; in real applications, choose small, bounded limits.

- `LIMIT m`: the query returns **at most `m` rows in total**. In a single-partition query, that is the cap on rows returned from that partition.
- `PER PARTITION LIMIT n`: the query returns **at most `n` rows from each partition** it visits. With multiple partitions, total returned rows can still exceed `n`.
- When both appear, **both limits apply simultaneously**: no partition contributes more than `n` rows, and the total result never exceeds `m` rows.
- Without `PER PARTITION LIMIT`, no per-partition cap from this clause is enforced.
- Without `LIMIT`, no total row cap from this clause is enforced; driver/cqlsh page fetching is **not** an implicit `LIMIT` on the overall query.
- Neither clause creates a partition key, an index, or a new sort order.

Syntactically, **`PER PARTITION LIMIT` precedes `LIMIT`**. Other CQL features such as `DISTINCT`, `GROUP BY`, and aggregates have their own rules; examples in this lesson use standard row-level `SELECT` statements so row counts stay consistent and clear.

## 3. Lab Data: One Tenant, Three Daily Partitions

Suppose an application exposes an API to view a tenant's event history for a day or a few specific days. Each `(tenant_id, day_bucket)` pair is **one partition**.

### 3.1. Creating the Keyspace and Table

```sql
-- Single-node lab environment; do not use SimpleStrategy/RF=1
-- as a template for multi-node, multi-datacenter production deployments.
CREATE KEYSPACE IF NOT EXISTS cassandra_limit_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_limit_lab;

CREATE TABLE IF NOT EXISTS events_by_tenant_day (
    tenant_id uuid,
    day_bucket date,
    created_at timestamp,
    event_id uuid,
    event_type text,
    detail text,
    PRIMARY KEY ((tenant_id, day_bucket), created_at, event_id)
) WITH CLUSTERING ORDER BY (created_at DESC, event_id DESC);
```

Key breakdown:

- The `(tenant_id, day_bucket)` pair is the **composite partition key**. Different days for the same tenant live in separate partitions.
- `created_at` and `event_id` are **clustering columns**; by default, rows in each partition are traversed in descending timestamp order, with `event_id` breaking ties.
- `event_type` and `detail` are regular columns and cannot automatically be used as indexes or arbitrary `ORDER BY` targets.

### 3.2. Inserting Sample Data

```sql
-- Tenant A, Nov 20: four rows.
INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Logged in'
);

INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Viewed order list'
);

INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Opened order details'
);

INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Paid'
);

-- Tenant A, Nov 21: two rows.
INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21', '2026-11-21 09:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGIN', 'Logged in day two'
);

INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21', '2026-11-21 15:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'VIEW', 'Viewed report'
);

-- Tenant A, Nov 22: one row.
INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-22', '2026-11-22 16:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGOUT', 'Logged out'
);

-- Tenant B, Nov 20: separate partition.
INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000008,
    'LOGIN', 'Second tenant'
);
```

In a fresh table containing only the `INSERT` statements above, the distribution is:

| Partition key | Row count | `created_at DESC` order |
| --- | ---: | --- |
| Tenant A, Nov 20 | 4 | 11:00, 10:00, 09:00, 08:00 |
| Tenant A, Nov 21 | 2 | 15:00, 09:00 |
| Tenant A, Nov 22 | 1 | 16:00 |
| Tenant B, Nov 20 | 1 | 12:00 |

Querying **tenant A for the three days 20, 21, 22** targets **three partitions holding seven rows in total**. Tenant B's partition is outside this set. The `INSERT` statements use fixed primary keys, so re-running them on the same table performs upserts without creating duplicate rows.

## 4. LIMIT: Capping the Entire Result

### 4.1. Single Partition, Taking N Rows in Clustering Order

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 2;
```

Expected result:

| `created_at` (UTC) | `event_type` |
| --- | --- |
| 11/20 11:00 | `PAY` |
| 11/20 10:00 | `CLICK` |

This query has a clean read path: `WHERE` targets **one partition**, `ORDER BY` matches the clustering order, and `LIMIT 2` keeps at most the first two rows in that order. For "the two newest events in a day," this is the right pattern.

If `LIMIT 2` is changed to `LIMIT 10`, the partition **only has four rows**, so the result still contains four rows. `LIMIT` is an **upper bound**, not a mandate for Cassandra to produce that many rows.

### 4.2. LIMIT Without an Explicit Matching ORDER BY

```sql
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
LIMIT 2;
```

In this table, a single-partition query still traverses in the **default clustering order**, `created_at DESC, event_id DESC`. Still, writing `ORDER BY` explicitly when the API relies on ordering makes the query contract clearer.

Do not write:

```sql
-- Invalid: event_type is a regular column, not a clustering key.
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
ORDER BY event_type ASC
LIMIT 2;
```

`LIMIT` does not make `ORDER BY` on a regular column valid.

### 4.3. Multiple Partitions: LIMIT Still Caps the Whole Result

```sql
SELECT day_bucket, created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
LIMIT 3;
```

The query targets **three partitions**, holding seven rows in the sample data, yet returns at most **three rows total**. Never misread it as "three rows for Nov 20, three for Nov 21, and three for Nov 22."

More importantly, **do not assume from `LIMIT 3` that the result is the three newest events across all three days**. Each partition maintains its own clustering order; an `IN` query touching multiple partitions is not automatically a globally sorted table by `created_at`. If a global top-N is needed, design a separate read and merge strategy.

## 5. PER PARTITION LIMIT: Per-Partition Row Cap

### 5.1. A List of Partitions, Taking Up to Two Rows from Each Partition

```sql
SELECT day_bucket, created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 2;
```

On the sample data:

| Partition | Actual rows | Limit `2` | Max rows returnable |
| --- | ---: | ---: | ---: |
| Tenant A, 11/20 | 4 | 2 | 2 |
| Tenant A, 11/21 | 2 | 2 | 2 |
| Tenant A, 11/22 | 1 | 2 | 1 |
| **Total** | **7** | **Per-partition cap** | **5** |

Within each partition, rows are selected in `DESC` clustering order, so the retained events are:

- Day 20: `PAY 11:00` and `CLICK 10:00`.
- Day 21: `VIEW 15:00` and `LOGIN 09:00`.
- Day 22: `LOGOUT 16:00`.

**The five rows are the combined result after applying the per-partition cap; there is no guarantee they are merged into a global chronological order.**

### 5.2. PER PARTITION LIMIT Does Not Cap the Number of Partitions

Example:

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 1;
```

This query returns at most **one row from each partition**. With three populated partitions, it can return **three rows**, and still inspects all three partition keys. `PER PARTITION LIMIT 1` does **not** mean "query only one partition."

If the `IN` list has 100 days, `PER PARTITION LIMIT 1` can return up to 100 rows while still touching **100 partition-key candidates**. It does not turn a 100-partition fan-out into one.

### 5.3. Single Partition: PER PARTITION LIMIT Acts Like That Partition's Row Cap

```sql
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
PER PARTITION LIMIT 2;
```

In a single-partition query, the result has at most two rows, matching the maximum count of `LIMIT 2` on the same row set and traversal order. The distinct value of `PER PARTITION LIMIT` shows up when a query touches **multiple partitions** or enforces a consistent per-partition bound.

### 5.4. Empty Partitions Do Not Fabricate Rows

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-22', '2026-11-23')
PER PARTITION LIMIT 2;
```

With the sample data, Nov 22 has one row and Nov 23 has none, yielding **only one result row**. Cassandra still looks up the Nov 23 partition key named in the query, but never "pads" rows to reach the limit.

## 6. Combining PER PARTITION LIMIT and LIMIT

Both limits appearing in the same statement:

```sql
SELECT day_bucket, created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 2
LIMIT 3;
```

Here:

1. Each partition contributes **at most two rows**.
2. The entire result set has **at most three rows**.
3. **There is no guarantee of an even split** of three rows across three days, nor is there a guarantee that the result holds the three rows with the highest `created_at` across all days.

For standard row-level `SELECT` queries without aggregate transformations, the **upper bound** can be expressed as:

\[
R_{\max}\ \leq\ \min\left(L,\ \sum_{i=1}^{P}\min(p,\, r_i)\right)
\]

Where:

- `P`: number of queried (candidate) partitions.
- `r_i`: number of rows in partition `i` that actually **match the `WHERE` clause**.
- `p`: `PER PARTITION LIMIT`, if specified.
- `L`: `LIMIT`, if specified.

For tenant A across three days, `r = (4, 2, 1)`, `p = 2`, `L = 3`:

```text
Total fetchable before global limit
    = min(2,4) + min(2,2) + min(2,1)
    = 2 + 2 + 1
    = 5 rows

After LIMIT 3:
    at most min(3,5) = 3 rows.
```

This notation only **explains the row-count bound**; it does not model all internal execution details, does not specify which partition is returned first, and does not apply verbatim to aggregate queries, `GROUP BY`, or special constructs.

| Query on tenant A and three days | Per-partition cap | Global cap | Max rows from sample data |
| --- | --- | --- | ---: |
| Neither limit clause | None | None | 7 |
| `LIMIT 3` | None | 3 | 3 |
| `PER PARTITION LIMIT 2` | 2 | None | 5 |
| `PER PARTITION LIMIT 2 LIMIT 3` | 2 | 3 | 3 |
| `PER PARTITION LIMIT 1 LIMIT 10` | 1 | 10 | 3 |

## 7. "Scope Boundaries" Mean More Than LIMIT: WHERE Governs the Read Region

Fast queries generally come from **narrowing the scope by key** first, and only then capping returned rows.

### 7.1. Bounding the Partition via the Partition Key

```sql
-- One partition precisely identified.
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
LIMIT 2;
```

The full partition key is `(tenant_id, day_bucket)`. Cassandra can therefore route directly to replicas holding **one partition**. `LIMIT 2` then caps the rows returned from that partition.

### 7.2. Bounding a Clustering Range Within the Partition

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at >= '2026-11-20 09:00:00+0000'
  AND created_at <  '2026-11-20 11:00:00+0000'
ORDER BY created_at DESC, event_id DESC
LIMIT 1;
```

This targets **one partition** and a half-open interval `[09:00, 11:00)` on clustering column `created_at`. Two rows match in the sample data (09:00 and 10:00), and the query returns **`CLICK 10:00`** due to descending clustering order and `LIMIT 1`.

Distinguish the three bounding layers:

```text
WHERE tenant_id = A AND day_bucket = 20
    -> one partition

AND created_at >= 09:00 AND created_at < 11:00
    -> slice within the partition: 09:00, 10:00

ORDER BY created_at DESC LIMIT 1
    -> one result row: 10:00
```

Using an appropriate clustering range often bounds read work much better than scanning an entire partition just to return `LIMIT 1`, especially when the request targets a specific time window.

### 7.3. LIMIT Cannot Rescue a Query Missing the Partition Key

```sql
-- Missing day_bucket: incomplete composite partition key.
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
LIMIT 1;

-- event_type is a regular column; no access path under this schema.
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE event_type = 'PAY'
LIMIT 1;
```

These statements **do not become valid key-based queries just by adding `LIMIT 1`**. To support lookups by `event_type` across tenants/days, the application needs a different query-driven table model or an index suited to the Cassandra version and production load.

Even with `ALLOW FILTERING` enabling certain filtered queries, `LIMIT 1` may still have to scan and filter vast numbers of rows or partitions **before finding a single match**. Small output size does not imply small search cost.

### 7.4. LIMIT Does Not Shrink the Number of Partitions in IN

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
LIMIT 1;
```

The key condition still specifies **three candidate partitions**. Depending on execution plan and when the limit is hit, the engine might not read every row from every partition; however, `LIMIT 1` **offers no guarantee** that the query routes to or contacts only one partition. Fan-out assessment must always start from the full key set in `WHERE`.

## 8. Rows Returned Do Not Equal Read Cost

In distributed Cassandra, a `SELECT` incurs several distinct cost dimensions:

| Dimension | Does `LIMIT`/`PER PARTITION LIMIT` change it? | Primary driver |
| --- | --- | --- |
| Partition keys in `WHERE` | **Does not alter the specified key set.** | Partition key, `=`, `IN`, token range. |
| Result rows returned | **Yes**, per global and per-partition caps. | Both limit clauses, existing data, clustering range. |
| Data sent to client | Usually **decreases** with fewer rows. | Selected columns, value sizes, page size. |
| Rows/cells inspected | **No direct cap from `LIMIT`.** | Tombstones, TTLs, filtering, SSTables/memtables, caches. |
| Nodes/replicas contacted | **Cannot be inferred from `LIMIT` alone.** | Token placement, replication, consistency, cluster state. |
| p95/p99 latency | May improve, but **not guaranteed**. | I/O, fan-out, concurrency, compaction/repair, tombstones, timeouts/retries. |

For instance, a partition full of TTL-expired records or tombstones may force Cassandra to scan past many deletion markers just to find **one live row**. In that case `LIMIT 1` certainly does not mean the storage engine inspects only one cell.

Similarly, `PER PARTITION LIMIT 1` over 1,000 partitions reduces returned rows, but fails to bound **candidate partitions**. In online APIs, it is critical to bound **key scope**, **partition size**, **`IN` list length**, and **returned rows/bytes** simultaneously.

## 9. Limits and Paging Are Different Concepts

### 9.1. Comparing LIMIT with Page Size

Consider the query:

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 100;
```

If the Java driver sets page size to `20`:

- `LIMIT 100`: caps the **total number of rows** the query is permitted to return.
- Page size `20`: instructs the driver/server to fetch results in **chunks of a target size**, without capping the entire query at 20 rows.
- In the lab data, Nov 20 only has **four rows**, so total output is four rows even though both `LIMIT` and page size are larger.

Page size can also be subject to execution limits or response byte caps; never treat page size as an absolute payload guarantee. In the Java driver, iterating through the entire `ResultSet` automatically fetches remaining pages.

### 9.2. Paging State for Resuming the Same Query

The Cassandra Java driver supports paging state to resume iterating over results of the **exact same query**. When passing paging state on the next request:

- Keep identical CQL, bind values, ordering clauses, and limit clauses.
- Never mix paging state from one tenant/day query with another tenant/day query.
- Never craft or tamper with paging state contents; if exposed to clients, protect its integrity and bind it to authorization scope.
- Paging does not create an immutable snapshot across reads. Writes, deletes, TTLs, and replica lag can alter observed data.

`PER PARTITION LIMIT` still applies **per partition across the entire query**, not "n rows per page." Therefore, never treat consecutive pages as independent queries that reset per-partition quotas.

### 9.3. CQL Has No SQL-Style OFFSET

Queries like:

```sql
-- Not a CQL-supported pagination syntax:
SELECT created_at, event_id
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
LIMIT 20 OFFSET 40;
```

are not how pagination works in Cassandra. Use **driver paging state**, or design a **keyset cursor** on the clustering key (e.g., `(created_at, event_id)`) when you need business-key pagination within a partition.

### 9.4. LIMIT Does Not Solve Multi-Partition Sorting

`PER PARTITION LIMIT 1` is great for getting **the single newest row per partition** under descending clustering order. However, results across multiple partitions do **not automatically** form "the N newest rows across the tenant." If an API needs top N across multiple day buckets, you can:

1. Pick a finite set of day buckets matching the target time window.
2. Read the newest rows from each bucket with appropriate bounds.
3. Merge using the `(created_at, event_id)` key tuple in the application layer, bounding row counts and concurrency.
4. If this is a hot query path, consider a dedicated read table with more suitable partition/clustering keys.

For continuously arriving data, cursor strategies also need consistent rules when new events land between requests.

## 10. Java Driver Integration: Binding LIMIT and Controlling Results

Examples use Apache Cassandra Java Driver 4.x and Java 15+ (for text blocks). Assume an active `CqlSession session` connected to keyspace `cassandra_limit_lab`.

### 10.1. Capping Results Within One Partition

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

UUID tenantId = UUID.fromString(
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
);
LocalDate day = LocalDate.parse("2026-11-20");

PreparedStatement prepared = session.prepare("""
    SELECT created_at, event_id, event_type
    FROM events_by_tenant_day
    WHERE tenant_id = ?
      AND day_bucket = ?
    ORDER BY created_at DESC, event_id DESC
    LIMIT ?
    """);

int requestedLimit = 2;
int safeLimit = Math.max(1, Math.min(requestedLimit, 100));

BoundStatement bound = prepared.bind(
    tenantId, day, safeLimit
).setPageSize(20);

for (Row row : session.execute(bound)) {
    System.out.printf("%s %s %s%n",
        row.getInstant("created_at"),
        row.getUuid("event_id"),
        row.getString("event_type")
    );
}
```

Here:

- `LIMIT ?` uses an integer bind marker; never concatenate user-supplied numbers into CQL strings.
- `safeLimit` illustrates an **application-enforced bound** from 1 to 100; this is not a Cassandra default limit.
- `setPageSize(20)` sets the driver fetch size; it does not raise the total result cap to 20 when CQL specifies `LIMIT 2`.
- `row.getInstant(...)` and `getUuid(...)` match the declared `timestamp` and `uuid` types.

### 10.2. Per-Partition Limiting Across Three Fixed Days

```java
import java.time.LocalDate;

PreparedStatement perDay = session.prepare("""
    SELECT day_bucket, created_at, event_id, event_type
    FROM events_by_tenant_day
    WHERE tenant_id = ?
      AND day_bucket IN (?, ?, ?)
    PER PARTITION LIMIT 2
    LIMIT 5
    """);

BoundStatement query = perDay.bind(
    tenantId,
    LocalDate.parse("2026-11-20"),
    LocalDate.parse("2026-11-21"),
    LocalDate.parse("2026-11-22")
).setPageSize(3);

for (Row row : session.execute(query)) {
    System.out.printf("%s | %s | %s%n",
        row.getLocalDate("day_bucket"),
        row.getInstant("created_at"),
        row.getString("event_type")
    );
}
```

On the lab table, this query can return **five rows**: two from day 20, two from day 21, and one from day 22; the driver fetches in pages targeting three rows each. Pages **do not map one-to-one to partitions**, and row order across multiple partitions should not be treated as a globally sorted timeline.

In production applications, if the date list varies, bound the number of readable buckets, use parameterized queries suited to list cardinality, and limit fan-out. Reading a small slice across many partitions often fails to stay fast when concurrency and replica coordination grow too high.

### 10.3. Replication, Consistency, and Error Handling

In multi-node clusters, consistency level is configured via driver/session/statement. It governs replica acknowledgments and shapes data freshness, latency, and availability. **`LIMIT` does not change consistency level**, and `PER PARTITION LIMIT` does not lower the replication factor.

When handling errors:

- `InvalidQuery` caused by missing keys, invalid `ORDER BY`, or malformed `LIMIT` is a **design/query error**; increasing timeouts or retrying will not fix it.
- Timeouts/unavailable errors require examining replica health, consistency settings, number of partitions accessed, data size, retry policy, and coordinator load.
- Slow queries despite `LIMIT 1` can stem from tombstones, compaction, repair, cold caches, or filtering many rows before finding a match; use tracing/metrics to diagnose root causes.

## 11. Common Mistakes and Fixes

| Misconception or syntax | Actual issue | How to handle it |
| --- | --- | --- |
| `LIMIT 2` means 2 rows **per day** | Caps total rows across the entire result set. | Use `PER PARTITION LIMIT 2` for per-day caps. |
| `PER PARTITION LIMIT 2` across three partitions means at most 2 rows total | Each partition is capped at 2, so total can reach 6. | Add `LIMIT` if a global cap is needed. |
| `PER PARTITION LIMIT 1` means only 1 partition is read | Can still target every key in the `IN` list. | Bound buckets/partitions in `WHERE` or at the API layer. |
| `LIMIT 10` guarantees at most 10 rows/cells are read on disk | May have to scan tombstones, filter rows, or inspect multiple partitions. | Narrow read scope with keys; monitor tracing and partition size. |
| `LIMIT 10` makes a query missing `day_bucket` valid | Does not supply the full composite partition key. | Specify concrete buckets or design another read table. |
| `PER PARTITION LIMIT 1` fetches the newest event **across the tenant** | Fetches up to one row **per partition**, not a global top one. | Merge under controlled bounds or use an appropriate read table. |
| `ORDER BY event_type` is valid if `LIMIT` is small | `event_type` is not a clustering column. | Design ordering into the primary key or sort small sets in the app. |
| Page size 20 means `SELECT` returns at most 20 rows | Driver can fetch subsequent pages automatically. | Distinguish `LIMIT` from page size and paging state. |
| `PER PARTITION LIMIT 2` re-applies 2 rows on every fetched page | It is a per-partition cap **across the query**, not per page. | Continue the query using the proper paging state. |
| `LIMIT 20 OFFSET 40` paginates like SQL | CQL does not support this offset pattern. | Use driver paging state or an appropriate keyset cursor. |

## 12. Practice Exercises with Answers

### Exercise 1. Two Newest Rows in One Day

**Task:** Fetch at most the two newest events for tenant A on November 20, 2026.

**Answer:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 2;
```

Result: `PAY 11:00`, `CLICK 10:00`.

### Exercise 2. One Event per Day

**Task:** Across the three days Nov 20–22 for tenant A, fetch at most one newest row from each day.

**Answer:**

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 1;
```

With the sample data, this returns three rows: `PAY 11:00` on day 20, `VIEW 15:00` on day 21, and `LOGOUT 16:00` on day 22. No global ordering across the three rows is asserted.

### Exercise 3. Combining Both Limits

**Task:** For the same three days, take at most two events per day and at most three events in the entire response.

**Answer:**

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 2
LIMIT 3;
```

The query returns no more than three rows; no partition can contribute more than two. There is no guarantee that the three rows belong to three distinct days.

### Exercise 4. Reading Within an Hour Window

**Task:** On November 20, pick at most one event from `09:00` up to before `11:00` UTC, newest first.

**Answer:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at >= '2026-11-20 09:00:00+0000'
  AND created_at <  '2026-11-20 11:00:00+0000'
ORDER BY created_at DESC, event_id DESC
LIMIT 1;
```

Result: `CLICK 10:00`. `PAY 11:00` is outside the interval because the upper bound uses `<`.

### Exercise 5. Analyzing Fan-Out and Limits

**Scenario:** An API accepts 100 days for one tenant, one partition per day, and runs `PER PARTITION LIMIT 1 LIMIT 10`. Has it guaranteed reducing candidate partition keys down to 10?

**Answer:** **No.** `WHERE` still specifies 100 candidate partitions. `PER PARTITION LIMIT 1` caps each partition at one contributed row; `LIMIT 10` caps the total output at ten rows. Neither clause changes the list of queried partition keys. You must bound the number of days/buckets at the API layer and evaluate fan-out cost before execution.

## 13. Limit Design Checklist for Cassandra APIs

1. **Partition:** Does `WHERE` provide the full partition key? If using `IN`, how many full partition keys must be located?
2. **Clustering:** When fetching a range, is it constrained on clustering columns in proper key order with clear inclusive/exclusive bounds?
3. **LIMIT semantics:** Is the goal **at most N rows total**, or **at most N rows per partition**? Are both caps needed?
4. **Ordering:** Does `ORDER BY` align with clustering order? Are per-partition newest rows being mistaken for a global top N?
5. **Paging:** Do you distinguish `LIMIT`, `PER PARTITION LIMIT`, driver page size, and paging state? Do paginated requests preserve the exact original predicates?
6. **Performance:** Are buckets and concurrency bounded, oversized partitions avoided, and tombstones, compaction/repair, slow queries, p95/p99 latency, and timeouts monitored?
7. **Java/consistency:** Are parameters bound with matching types, integer limits enforced in the API, consistency matched to replication, and query errors separated from timeout/unavailable errors?

**Remember:** `LIMIT` caps **total returned rows**; `PER PARTITION LIMIT` caps **rows per partition**. To bound **what must be read**, first write `WHERE` clauses compatible with your partition key and clustering columns. Those three mechanisms complement each other in distributed Cassandra query design, but never substitute for one another.

## References

- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT, PER PARTITION LIMIT, LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: PRIMARY KEY, CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
