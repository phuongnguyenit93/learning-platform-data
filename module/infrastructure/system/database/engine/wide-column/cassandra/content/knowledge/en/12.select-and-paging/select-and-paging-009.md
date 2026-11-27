# ALLOW FILTERING and Estimating Data Scanned in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Explain why Apache Cassandra favors queries specifying the **partition key** and **clustering range** rather than arbitrary filtering on regular columns.
2. Understand `ALLOW FILTERING` as accepting an execution path that may read a large amount of data before filtering—**not an indexing mechanism or performance guarantee**.
3. Distinguish three quantities: **partitions inspected**, **candidate rows evaluated**, and **rows returned**.
4. Estimate match rate, fan-out, read amplification, and the effects of `LIMIT`, `PER PARTITION LIMIT`, TTLs, and tombstones.
5. Use `TRACING`, metrics, and load tests for empirical evaluation instead of relying on result row counts.
6. Choose among bounded filtering, query-driven table design, appropriate indexes (such as SAI where supported), and summary tables.
7. Write parameterized queries with the Java Driver, enforce safety bounds, and distinguish CQL errors from load/replica issues.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. The module explores Apache Cassandra's distributed architecture and wide-column model: from partition keys, query-driven table design, and read/write consistency to CQL, replication, compaction, repair, error handling, and Java application integration. The focus here is an operational question: **how much data might Cassandra have already read for a query that returns only a few rows?**

## 1. How Does Cassandra Locate Data Before Filtering?

Consider a table with primary key:

```sql
PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
```

| Component | Role | Impact on `WHERE` |
| --- | --- | --- |
| `tenant_id` and `event_day` | **Composite partition key** | Together identify the partition and token used to locate replicas. |
| `occurred_at` | First clustering column | Selects a point in time or contiguous slice **within the partition**. |
| `event_id` | Second clustering column | Disambiguates rows sharing a timestamp; supports full-key boundaries. |
| `event_type`, `device` | Regular columns | Do not automatically create a lookup path by their values alone. |

Visualize the read path:

```text
Query from application
       |
       v
WHERE: full (tenant_id, event_day)?
       |
       +-- Yes --> compute token --> locate partition/replicas
       |                                  |
       |                                  v
       |                         clustering key/range
       |                                  |
       |                                  v
       |                       candidate rows in partition
       |                                  |
       |                                  v
       |                       check regular column filter
       |                                  |
       |                                  v
       |                             result rows
       |
       +-- No  --> no full-partition read path;
                   may be rejected or require broad scan
                   if query shape and configuration permit
```

The first two read paths are not identical:

- **Key-based read:** `WHERE tenant_id = ... AND event_day = ... AND occurred_at >= ...` directly locates the partition and clustering slice.
- **Read-then-filter:** adding `AND event_type = 'VIEW'` when `event_type` is only a regular column can force Cassandra to inspect each candidate row to test whether it matches.

A well-defined partition can hold a few rows or millions of rows. Thus having the **full partition key** is very helpful, yet **not sufficient** to guarantee that a query filtering on a regular column is cheap.

## 2. What Does ALLOW FILTERING Actually Do?

Consider a standard query:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW';
```

If the table lacks an index or compatible access path for `event_type`, Cassandra normally rejects this statement with a message noting that the query may require filtering data and can only run if filtering is allowed.

Add:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;
```

What `ALLOW FILTERING` means is: **the query author accepts that Cassandra may have to process a dataset larger than the result set in order to evaluate the predicates**.

It does **not** mean:

- Creating a secondary index, Storage-Attached Index (SAI), or a new clustering column.
- Changing the partition key or co-locating partitions sharing a regular column value.
- Guaranteeing cost proportional only to the number of returned rows.
- Guaranteeing execution in every configuration: some `WHERE` shapes are still rejected or blocked by guardrails/policies.
- Turning `LIMIT 1` into a key-based single-row lookup.

**Distinguish errors from design decisions:** "the query runs with `ALLOW FILTERING`" only confirms CQL permitted that read plan; it does **not** prove the query meets your API's p95/p99 latency targets.

## 3. CQL Lab: Three Partitions, Ten Rows

To observe this concretely, build a log table for tenant daily activities.

### 3.1. Creating the Keyspace and Table

```sql
-- Only use SimpleStrategy / RF=1 for single-node lab.
CREATE KEYSPACE IF NOT EXISTS cassandra_filter_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_filter_lab;

CREATE TABLE IF NOT EXISTS events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    device text,
    detail text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);
```

Each `(tenant_id, event_day)` is one partition. Inside a partition, events are ordered by ascending `occurred_at`, then `event_id`. The columns `event_type` and `device` are **not** part of the key.

### 3.2. Loading Data

```sql
-- Tenant A, Nov 20: 5 rows.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000011,
    'LOGIN', 'web', 'Logged in'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000012,
    'VIEW', 'web', 'Viewed order'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000013,
    'VIEW', 'mobile', 'Viewed on mobile'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000014,
    'CLICK', 'mobile', 'Opened details'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000015,
    'LOGOUT', 'web', 'Logged out'
);

-- Tenant A, Nov 21: 3 rows.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-21',
    '2026-11-21 07:00:00+0000',
    00000000-0000-4000-8000-000000000021,
    'LOGIN', 'mobile', 'Logged in day 21'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-21',
    '2026-11-21 08:00:00+0000',
    00000000-0000-4000-8000-000000000022,
    'VIEW', 'mobile', 'Viewed product'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-21',
    '2026-11-21 09:00:00+0000',
    00000000-0000-4000-8000-000000000023,
    'CLICK', 'web', 'Clicked purchase'
);

-- Tenant B, Nov 20: 2 rows.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    22222222-2222-4222-8222-222222222222, '2026-11-20',
    '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000031,
    'LOGIN', 'web', 'Logged in B'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    22222222-2222-4222-8222-222222222222, '2026-11-20',
    '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000032,
    'VIEW', 'mobile', 'Viewed product B'
);
```

Summary of lab data:

| Partition key | Rows | `VIEW` count | `mobile` count |
| --- | ---: | ---: | ---: |
| (Tenant A, 11/20) | 5 | 2 | 2 |
| (Tenant A, 11/21) | 3 | 1 | 2 |
| (Tenant B, 11/20) | 2 | 1 | 1 |
| **Entire lab table** | **10** | **4** | **5** |

These numbers assume a freshly created table containing only the sample data, with no TTLs, deletes, or other writes. Re-running `INSERT` on the same primary key performs an upsert without creating duplicate rows.

## 4. Same Requirement, Three Query Scopes

### 4.1. Key-Based: Reading One Known Partition

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

The result has **5 rows**. The complete `(tenant_id, event_day)` pair routes Cassandra directly to **one partition**. `ALLOW FILTERING` is not needed because there is no predicate filtering on a regular column.

In production, however, five rows can become millions of rows if a tenant logs heavily in one day. Choosing a "one-day" bucket must match traffic volume and partition size limits, not merely the `event_day` column name.

### 4.2. Key-Based Plus Regular-Column Filter Within One Partition

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;
```

Result from sample data: **2 rows** at `09:00` and `10:00`. Yet to determine which two rows match `VIEW`, Cassandra may need to inspect the rows of day 20's partition.

Simplified model without an index:

```text
Partition (Tenant A, 11/20)

08:00 LOGIN  -- no match
09:00 VIEW   -- match
10:00 VIEW   -- match
11:00 CLICK  -- no match
12:00 LOGOUT -- no match

Candidate set: 5 rows
Result set:    2 rows
Match rate:    2 / 5 = 40%
```

Here `5` is the **logical candidate set size** in the lab, not a claim that the storage engine always reads exactly five physical records or five disk blocks. Execution plans, caches, and limits can change actual work; TTLs/tombstones can make items processed **exceed** live row count.

### 4.3. Narrowing with a Clustering Range Before Filtering

```sql
SELECT occurred_at, event_id, event_type, device
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000'
  AND device = 'mobile'
ALLOW FILTERING;
```

Now there is still **one** partition, but the clustering interval `[09:00, 12:00)` covers only **3 candidate rows**:

| UTC Time | `event_type` | `device` | Matches? |
| --- | --- | --- | --- |
| 09:00 | `VIEW` | `web` | No |
| 10:00 | `VIEW` | `mobile` | Yes |
| 11:00 | `CLICK` | `mobile` | Yes |

The result is **2 rows**. The match rate of the narrowed candidate set is `2/3 ≈ 66.7%`.

**Takeaway:** If you must filter on a regular column, always provide the **full partition key** and a **short clustering range** to bound the rows inspected. That is usually better than filtering a regular column across an entire huge partition, though you should still benchmark with realistic data size and distribution.

## 5. Queries Missing Keys: Scanning Many Partitions

### 5.1. Filtering a Regular Column Without a Partition Key

```sql
-- Risky example: no partition-locating key.
-- Only try on a small lab if cluster allows.
SELECT tenant_id, event_day, occurred_at, event_type
FROM events_by_tenant_day
WHERE event_type = 'VIEW'
ALLOW FILTERING;
```

In the sample data, there are **4 `VIEW` rows across 3 partitions**. However, because `event_type` is a regular column and the table has no suitable index, Cassandra cannot infer which partitions contain `VIEW`. If permitted to execute, it may have to scan data across **many token ranges and replicas**.

In production, a table with millions of partitions behaves nothing like a three-partition lab. The query can fail due to guardrails, time out, or inflict severe cluster load before finishing.

### 5.2. Composite Partition Keys Must Be Complete

```sql
-- Cannot locate a full partition:
SELECT event_day, occurred_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111;
```

Because the partition key is **`(tenant_id, event_day)`**, knowing `tenant_id` does not give Cassandra an index listing every day for that tenant. Adding `ALLOW FILTERING` is not a stable fix for an API querying multi-day history.

When specific days are needed, enumerate known buckets with `IN` on the last component of the composite partition key:

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

This query selects **2 candidate partitions** without filtering on a regular column. Adding `AND event_type = 'VIEW' ALLOW FILTERING` may force inspecting rows in **both partitions**. In the lab: `5 + 3 = 8` candidate rows and `2 + 1 = 3` matching `VIEW` rows.

**Note:** `ALLOW FILTERING` is not a license to ignore every CQL rule on composite partition keys or clustering columns. Certain predicate combinations remain rejected depending on version and configuration. In those cases, change the query predicates, add a suitable index, or adjust the table model rather than just appending this keyword.

## 6. Estimating Data Scanned

### 6.1. Per-Partition Candidate Counting Model

Suppose a request specifies a set `K` of `P` **full partition keys**. Inside partition `i`, after clustering range predicates, there are `N_i` logical candidate rows, of which `M_i` match the regular-column filters.

```text
P = full partition-key candidates
N = N_1 + N_2 + ... + N_P  (logical candidate rows)
M = M_1 + M_2 + ... + M_P  (rows matching filter condition)

Match rate = M / N, if N > 0
Candidate-to-result ratio = N / M, if M > 0
```

Examples:

| Query | `P` | `N` | `M` | Match rate |
| --- | ---: | ---: | ---: | ---: |
| Tenant A / day 20, filter `event_type = VIEW` | 1 | 5 | 2 | 40% |
| Tenant A / day 20, window 09–12, filter `device = mobile` | 1 | 3 | 2 | 66.7% |
| Tenant A / days 20–21, filter `event_type = VIEW` | 2 | 8 | 3 | 37.5% |
| Entire lab table, filter `event_type = VIEW` | 3 | 10 | 4 | 40% |

This is a **logical count model for estimation**, not exact execution cost:

- A rare column value makes `M` small, but does **not** shrink `N` when there is no index.
- A huge partition with large `N` can still be slow even if `M = 1`.
- An empty dataset or all-mismatch partition has `M = 0`, yet the engine may still do substantial work to verify it.
- With `LIMIT`, execution can **stop early**, making rows inspected smaller than `N`. Even so, there is no worst-case guarantee on items read.

### 6.2. Accounting for Row Size and Other Costs

A rough initial assessment can combine:

```text
Candidate bytes (rough estimate)
  ≈ total logical candidate rows × average data size to read

Actual read work
  = candidate reads
  + memtable/SSTable lookup and reconciliation
  + tombstone/TTL handling
  + replica/network/coordinator overhead
```

Do not treat the expression above as Cassandra's official internal cost formula. Uneven row sizes, caches, compression, SSTable layouts, indexes, and actual read paths cause physical bytes read to diverge significantly from rough estimates.

### 6.3. Separating Selectivity from Fan-Out

Two independent questions:

1. **Fan-out:** How many partitions, token ranges, and replicas must be involved to locate data?
2. **Match rate:** Within the inspected data, how many rows satisfy the regular-column condition?

For instance, `IN` with 100 days targets 100 candidate partitions for one tenant. If each partition holds 10,000 events, filtering for a rare `event_type` may return a few dozen rows while still processing a massive candidate volume. A good index or an event-type-keyed table changes the access path; merely adding `LIMIT` does not.

## 7. LIMIT, PER PARTITION LIMIT, and Page Size Are Not Indexes

### 7.1. LIMIT 1 May Still Inspect Many Rows

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'LOGOUT'
LIMIT 1
ALLOW FILTERING;
```

In the lab, the sole `LOGOUT` row sits at the **end** of the partition under `occurred_at ASC`: at 12:00. Execution must inspect preceding candidates before finding the matching row; `LIMIT 1` only caps the output at one row, **without creating a direct access path to `event_type = LOGOUT`**.

If hundreds of thousands of non-matching rows precede a single match, fetching **one row** can still be very expensive. If zero rows match, proving the result is empty can also be costly.

### 7.2. PER PARTITION LIMIT Caps Output per Partition

```sql
SELECT event_day, occurred_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 1;
```

This query **does not need `ALLOW FILTERING`** because it uses only the partition key and caps rows returned per partition. It can return two rows—one from day 20 and one from day 21—in each partition's clustering order.

If you add a regular-column filter with `ALLOW FILTERING`, each partition may still have to check many candidates before finding a qualifying row. `PER PARTITION LIMIT 1` does not guarantee Cassandra reads only one physical row or visits only one partition.

### 7.3. Page Size Governs Result Transfer, Not Scan Scope

The Java driver offers `setPageSize(n)` and paging state to retrieve results in chunks, but:

| Mechanism | Purpose | Creates an access path for `event_type`? |
| --- | --- | --- |
| Full partition key in `WHERE` | Locates partition | No, though it narrows scope. |
| Clustering range | Narrows row slice within partition | No, though it narrows scope. |
| `ALLOW FILTERING` | Permits certain read-then-filter plans | **No**. |
| `LIMIT n` | Caps total result rows | **No**. |
| `PER PARTITION LIMIT n` | Caps result rows per partition | **No**. |
| Driver page size | Throttles rows fetched per round trip | **No**. |
| Appropriate index | Can create an access path on the indexed column | **Potentially**, depending on index/version/query. |

Never use page size to "fix" a full-table scan filtering `event_type`. Every page fetch belongs to the same query plan and still performs the work needed to locate matching rows.

## 8. How Do Tombstones, TTLs, Compaction, and Consistency Affect This?

### 8.1. Tombstones and TTLs

In Cassandra, deletes and TTL expirations rely on tombstones. A query may have to read and reconcile many data fragments to determine which rows remain **live**:

```text
10,000 physical row versions / cells (illustrative)
       |
       +-- some deleted or TTL-expired
       +-- some spread across multiple SSTables
       |
       v
2,000 live logical rows in key range
       |
       +-- filter event_type
       v
10 result rows
```

The numbers in the diagram are purely illustrative. The key point is that `M = 10` does **not** tell you how many tombstones, cells, or SSTables had to be processed. When live rows are sparse due to expired data, `LIMIT 10` can still cause slow queries or tombstone warnings.

Compaction reorganizes SSTables and purges obsolete data when safe; repair helps replicas converge. Neither compaction nor repair can be treated as "making `ALLOW FILTERING` cheap" for every query, because the access path itself remains unchanged.

### 8.2. Replication and Consistency

Assume a replication factor of 3 under an appropriate topology strategy. That does **not** mean a query filtering three partitions returns triple the rows: replicas hold copies of the same logical data. However, the number of replicas required to respond, data divergence, and read reconciliation can significantly impact read latency.

- `LOCAL_ONE` typically requires fewer read acknowledgments, but can observe unconverged data.
- `LOCAL_QUORUM` requires more replicas in the local datacenter (depending on RF and cluster state), trading off latency/availability for stronger read guarantees.
- Neither **creates an index on regular columns** nor reduces the number of candidate partitions specified by `WHERE`.

When a filtered query is slow, separate two causes: **an overly broad read path** vs. **replica serving/reconciliation cost**. Choose consistency based on data guarantees, never as a substitute for key design.

## 9. Empirical Measurement Using Tracing and Metrics

### 9.1. Comparing Three Queries in cqlsh

In a **lab environment** on the same dataset, enable tracing:

```sql
TRACING ON;

-- A: key-based read only.
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';

-- B: filter regular column within the exact partition.
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;

-- C: narrow clustering range first before filtering.
SELECT occurred_at, event_id, event_type, device
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000'
  AND device = 'mobile'
ALLOW FILTERING;

TRACING OFF;
```

Inspect partitions/rows read, execution duration, coordinator/replica activity, and read stage details reported by your cluster version. Some trace output shows execution steps without exact disk byte counts; combine tracing with metrics and load testing.

**Never leave tracing enabled continuously across all production queries**: tracing adds overhead. Use it selectively in staging or on controlled requests per operational policy.

### 9.2. Key Metrics to Collect

| Metric | Why it matters |
| --- | --- |
| Per-query p50/p95/p99 latency | Surfaces unpredictable tail latency from skewed data distribution. |
| Partitions accessed and partition sizes | Evaluates fan-out and hot/wide partitions. |
| Tombstones scanned / warnings | Reveals heavy deleted/TTL-expired data being traversed. |
| Read timeouts, `Unavailable`, and retries | Measures overload and request amplification risk. |
| SSTables per read, cache hit rate, compaction backlog | Shows read amplification and storage pressure. |
| Node/coordinator load and replica latency | Distinguishes wide read plans from infrastructure bottlenecks. |
| QPS, `IN` list length, page size, concurrency | Captures actual load pressure from the application. |

Benchmarks should mirror realistic data distributions: large and small tenants, busy daily partitions, low match rates, TTL/tombstone churn, and concurrent traffic. A fast query in a 10-row lab **proves nothing** about production stability.

## 10. Replacing ALLOW FILTERING with a Proper Access Path

### 10.1. Designing a Query-Driven Table

If a screen frequently requests "all `VIEW` events for a tenant on one day, ordered by time," create a dedicated read table:

```sql
CREATE TABLE IF NOT EXISTS events_by_tenant_day_type (
    tenant_id uuid,
    event_day date,
    event_type text,
    occurred_at timestamp,
    event_id uuid,
    device text,
    detail text,
    PRIMARY KEY (
        (tenant_id, event_day, event_type),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);
```

In this table, the triple `(tenant_id, event_day, event_type)` is the **full partition key**. The query:

```sql
SELECT occurred_at, event_id, device
FROM events_by_tenant_day_type
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW';
```

locates the partition by event type **without needing `ALLOW FILTERING`**. Because this is a new table, you must **populate and maintain its data independently**; it does not stay in sync with `events_by_tenant_day` automatically.

Trade-offs:

- More tables and more writes per event.
- Must handle idempotency, retries, updates, and deletes/TTLs across denormalized copies.
- Other queries, such as "all `device = mobile` events," may still need their own read path.
- Avoid oversized partitions if one event type dominates; adjust bucketing accordingly.

Cassandra's strength is **intentional query-driven denormalization**, rather than forcing one generic table to support every ad-hoc filter.

### 10.2. Using Indexes When Appropriate

In Cassandra versions supporting **Storage-Attached Indexes (SAI)** (such as Apache Cassandra 5.0), an index can provide an access path for certain regular-column predicates:

```sql
-- Syntax illustration in an environment supporting SAI.
-- Only create after evaluating version, cardinality, and write cost.
CREATE CUSTOM INDEX IF NOT EXISTS events_type_sai
ON events_by_tenant_day (event_type)
USING 'StorageAttachedIndex';
```

**Do not treat SAI as magic:** performance still depends on selectivity, value distribution, combined predicates, data size, index maintenance, and the work required to materialize matching rows. Supported predicate combinations and syntax must also be verified for your version. An index on `event_type` does not automatically make "query every `VIEW` cluster-wide" cheap at high QPS.

When to consider each option:

| Scenario | Potentially suitable solution | What to measure |
| --- | --- | --- |
| Small partition, infrequent regular-column filter | Bounded `ALLOW FILTERING` | Partition size, p99 latency, tombstones. |
| Very large partition, hot API filtering by `event_type` | Table keyed by `(tenant, day, type)` | Per-partition size, write/sync overhead. |
| Selective query with flexible predicates | SAI where supported by version | Index selectivity, latency, write/read overhead. |
| System-wide counts/aggregations by event type | Summary table / streaming analytics | Freshness, drift, backfill, idempotency. |
| Full-table scans for offline reporting | Controlled batch/analytics tooling | Runtime, concurrency, resource caps. |

### 10.3. Can You Read a Small Slice and Filter in the Application?

This is worth considering when the **input dataset is genuinely small with a strict upper bound**. For example, if a partition has only a few dozen events in an hour, reading a short clustering range and filtering in Java can be easier to reason about than running `ALLOW FILTERING` over a large set.

However, this option **sends unneeded rows over the network**, increasing bandwidth and application memory usage. On large partitions, it is usually inferior to designing a proper access path. Never shift a full-table scan from the server into Java and call it an optimization.

## 11. Java Driver: Enforcing Read Bounds and Binding Parameters

Examples use **Apache Cassandra Java Driver 4.x** and Java 15+ (text blocks). Assume an active `CqlSession session` connected to keyspace `cassandra_filter_lab`.

### 11.1. A Bounded Filtering Case

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

UUID tenantId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

PreparedStatement prepared = session.prepare("""
    SELECT occurred_at, event_id, event_type, device
    FROM events_by_tenant_day
    WHERE tenant_id = ?
      AND event_day = ?
      AND occurred_at >= ?
      AND occurred_at < ?
      AND device = ?
    ALLOW FILTERING
    """);

BoundStatement statement = prepared.bind(
    tenantId,
    day,
    Instant.parse("2026-11-20T09:00:00Z"),
    Instant.parse("2026-11-20T12:00:00Z"),
    "mobile"
).setPageSize(50);

for (Row row : session.execute(statement)) {
    System.out.printf("%s %s %s%n",
        row.getInstant("occurred_at"),
        row.getUuid("event_id"),
        row.getString("event_type")
    );
}
```

With the lab data: `VIEW` at 10:00 and `CLICK` at 11:00. This example **illustrates bounded use of `ALLOW FILTERING`**, not a default recommendation for all endpoints.

### 11.2. API Guardrail Policies

The application should enforce constraints before querying:

1. Authenticate and authorize so `tenant_id` cannot be abused to access another tenant.
2. Require `event_day` or a short, strictly capped list of buckets.
3. Validate both time bounds and cap window length (e.g., only a few hours when business rules allow).
4. Bound concurrency, timeouts, and retries; never auto-retry expensive scan queries indefinitely.
5. Log query shape, candidate partitions, latency, and Cassandra warnings **without exposing sensitive data**.
6. Migrate to a dedicated read table or appropriate index if this filter becomes a hot API or tail latency exceeds SLOs.

Example time-window validation in Java:

```java
import java.time.Duration;
import java.time.Instant;

Instant start = Instant.parse("2026-11-20T09:00:00Z");
Instant end = Instant.parse("2026-11-20T12:00:00Z");
Duration window = Duration.between(start, end);

if (window.isNegative() || window.isZero()
        || window.compareTo(Duration.ofHours(6)) > 0) {
    throw new IllegalArgumentException("Invalid time window");
}
```

The six-hour cap is solely an **example API policy**, not a Cassandra safety threshold. A single tenant can write millions of events in six hours; monitor partition size and measure real performance.

### 11.3. Handling Errors by Category

- **`InvalidQuery` / requires `ALLOW FILTERING`:** a CQL or access-path issue; raising timeouts will not fix it.
- **Timeout / `Unavailable`:** check replicas, consistency, read slice width, fan-out, and load; avoid retry storms.
- **Inconsistent results across reads:** check replication/consistency, TTLs, concurrent writes/deletes, and repair; paging state does not create an immutable snapshot.
- **Response has few rows yet is slow:** inspect filtered-out rows, tombstones, compaction backlog, SSTable reads, and index selectivity (if any).

## 12. Common Misconceptions

| Claim | Why it is wrong or incomplete | How to approach it |
| --- | --- | --- |
| "`ALLOW FILTERING` speeds up queries." | It only permits certain filter execution plans; it never creates an access path. | Bound partition/range or design a table/index. |
| "Once the partition key is known, filtering any column is cheap." | One partition can be huge; regular columns may still force scanning many rows. | Check candidate row counts, bucketing, and latency. |
| "Returning 2 rows means Cassandra only read 2 rows." | It may have inspected 5, 50,000, or many more physical entries. | Measure via tracing/metrics, never infer from response size. |
| "`LIMIT 1` guarantees only one row is checked." | It may scan many non-matching rows before finding one match. | Create a key- or index-backed access path. |
| "`PER PARTITION LIMIT 1` makes the query touch one partition." | Caps rows per partition without reducing partition keys in `WHERE`. | Bound the bucket/`IN` list. |
| "`event_type = 'VIEW'` always finds matches cleanly table-wide." | Without an index or partition key, it causes broad scans or rejection. | Query-driven table / index / analytics. |
| "Adding `ALLOW FILTERING` fixes every `WHERE` error." | Some key combinations remain unsupported or blocked by guardrails. | Check primary key rules and version syntax. |
| "Page size 20 means Cassandra reads only 20 rows." | Page size throttles fetching, not the filtering work needed before emitting rows. | Design proper read bounds. |
| "SAI handles every rare and high-QPS query equally well." | Performance depends on cardinality, selectivity, QPS, and version. | Benchmark and consider dedicated tables. |
| "Increasing timeout fixes slow filtering." | Causes slow requests to pile up and worsens overload. | Shrink scans, measure p99, and control concurrency/retries. |

## 13. Practice Exercises and Answers

### Exercise 1. Counting Candidates vs. Results Within One Partition

**Question:** Tenant A / day 20 has five events. How many rows does `event_type = 'VIEW' ALLOW FILTERING` return? How many logical rows belong to the candidate partition before checking `event_type`?

**Answer:** **2 result rows**, **5 candidate rows** in the lab; match rate `2/5 = 40%`. Five is not an exact guarantee of physical records read.

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;
```

### Exercise 2. Narrowing Scope Before Filtering

**Question:** Find only `device = 'mobile'` events from 09:00 up to before 12:00 on day 20 for tenant A.

**Answer:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000'
  AND device = 'mobile'
ALLOW FILTERING;
```

In the lab: **3 candidate rows in range**, **2 matching rows** at 10:00 and 11:00.

### Exercise 3. Is LIMIT Enough to Prevent a Wide Scan?

**Question:** Why can the following query still be slow even though it fetches only one row?

```sql
SELECT tenant_id, event_day, event_id
FROM events_by_tenant_day
WHERE event_type = 'LOGOUT'
LIMIT 1
ALLOW FILTERING;
```

**Answer:** There is no full partition key and no index on `event_type`. To find a single `LOGOUT` row, Cassandra may have to scan many partitions and rows before encountering a match. `LIMIT 1` only bounds **returned rows**, not **read volume**.

### Exercise 4. Redesigning the Table

**Question:** An API continuously reads all `VIEW` events for a tenant/day in chronological order. Should you fix it with `ALLOW FILTERING` or table design?

**Suggested answer:** For high QPS or large partitions, consider a table `events_by_tenant_day_type` with composite partition key `(tenant_id, event_day, event_type)` and clustering `(occurred_at, event_id)`. Querying for `VIEW` becomes a targeted single-partition read; maintain denormalized data and handle writes/deletes/TTLs. If predicates are flexible and your Cassandra version supports it, evaluate SAI via benchmarking.

### Exercise 5. Multi-Day Fan-Out

**Question:** Tenant A has 30 known daily partitions, averaging 10,000 events/day, with roughly 1% being `VIEW`. Without an index, what are the estimated candidate rows and result rows for a request filtering `VIEW` across all 30 days?

**Answer:**

```text
Partition-key candidates = 30
Logical candidates ≈ 30 × 10000 = 300000
Expected results ≈ 300000 × 1% = 3000 rows
```

This is an **estimate based on averages**, not the exact number of entries read by the storage engine. A `1%` match rate does not allow Cassandra to read only 3,000 rows directly without an access path on `event_type`. Consider finer bucketing, narrower time ranges, a dedicated table, or an index.

### Exercise 6. Distinguishing Query Errors from Operational Failures

**Scenario:** A query missing its partition key fails requiring `ALLOW FILTERING`; after adding the keyword, the API suffers spiking p99 latency and timeouts.

**Suggested answer:** Fixing the syntax only permitted the scan/filter plan—**it did not make performance stable**. Measure fan-out, partition size, tombstones, traces, replica health, and consistency; then narrow scope using keys/clustering or build an appropriate table/index. Blindly retrying and increasing timeouts only worsens cluster load.

## 14. Checklist Before Using ALLOW FILTERING

1. **Keys:** Is the full partition key known? If using `IN`, how many candidate full partition keys exist?
2. **Clustering:** Are you leveraging a clustering key range to minimize candidate rows?
3. **Selectivity:** Estimate `N` candidate rows and `M` matching rows; watch for data skew/hot partitions or frequent `M = 0` scans.
4. **Size:** How large can row counts/bytes per partition, tombstones/TTLs, and SSTable read amplification grow?
5. **Limits:** Are you mistaking `LIMIT`, `PER PARTITION LIMIT`, or driver page size for data-locating capability?
6. **Measurement:** Have you compared tracing, p95/p99 latency, read timeouts, tombstones, and concurrency on production-like data?
7. **Alternatives:** Should you build a query-driven table, use SAI appropriately, pre-aggregate, or keep filtering strictly on a tiny dataset?
8. **Operations:** Are consistency, replication, repair, compaction, retries, and timeouts aligned with read load and data SLAs?
9. **Java app:** Are types bound properly, tenant authorization enforced, bucket/time windows capped, and overload protections in place?

**Remember:** `ALLOW FILTERING` does not index a query; it lets Cassandra **read and inspect more data than it returns**. Evaluate **partition fan-out, candidate rows, tombstones/TTLs, and replica costs** rather than looking only at `LIMIT` or response size. For hot queries, prefer a **query-driven table model** or an index/summary evaluated under realistic load.

## References

- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT and ALLOW FILTERING](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: Primary Key and Clustering Columns](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Documentation — Storage-Attached Indexing](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-overview.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
