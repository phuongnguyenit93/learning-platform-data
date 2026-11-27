# Partitioning Goals and Unsuitable Use Cases in PostgreSQL

When a PostgreSQL table grows from a few hundred thousand to hundreds of millions or billions of rows, **partitioning** often comes to mind immediately. However, partitioning is neither a "speed up every query" button nor a mandatory requirement whenever a table becomes large. A properly partitioned table can allow queries to read only a subset of data, delete old data quickly via partition management operations, and narrow the scope of maintenance. Conversely, partitioning on the wrong key or splitting too finely can force the planner to process thousands of child relations, require every INSERT to be routed, force UPDATE operations to move rows between partitions, and make queries without predicates on the partition key more complex.

For example, consider two reports querying an events table containing three years of data:

```sql
-- Report for October 2026 only:
SELECT COUNT(*)
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';

-- All-time report:
SELECT COUNT(*)
FROM events;
```

If `events` is partitioned by month on `occurred_at`, PostgreSQL can **prune** most partitions for the first query, yet still has to inspect data across all eligible partitions for the second query. If the application primarily looks up rows by `event_id` without knowing the date, monthly partitioning might not help that query and could even force it to search across multiple child indexes.

Therefore, before writing `CREATE TABLE ... PARTITION BY ...`, the right question is:

> **What do we want to optimize, and can the workload eliminate a large fraction of partitions in most critical operations?**

This lesson covers the true goals of partitioning, how to choose among RANGE/LIST/HASH, suitable and unsuitable scenarios, trade-offs regarding indexes, primary keys, uniqueness, JOINs, INSERT/UPDATE/DELETE, VACUUM, replication, and planning, followed by a decision-making process with examples and exercises.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between a logical partitioned table and the physical data of its partitions.
2. State the valid goals of partitioning: **partition pruning**, **data lifecycle** management, scoped maintenance, and certain forms of parallelization/workload organization.
3. Distinguish between **RANGE**, **LIST**, and **HASH partitioning** in PostgreSQL.
4. Read partition design diagrams by time, tenant, and hash key.
5. Explain why partitioning does not replace B-tree/BRIN/GIN indexes, statistics, or SQL optimization.
6. Understand when queries without a partition key lead to scanning many partitions.
7. Identify the costs of having many partitions: planning, metadata, file descriptors, index/constraint maintenance, and operational complexity.
8. Recognize the limitations of **PRIMARY KEY/UNIQUE** on a partitioned table and the consequences for foreign keys, upserts, and business identifiers.
9. Analyze UPDATE operations that modify the partition key and the risks of moving rows to another partition.
10. Design schedules for pre-creating future partitions, attach/detach operations, archiving/deleting old data, and controlled default partitions.
11. Evaluate alternatives: appropriate indexes, BRIN, query rewriting, archiving, batching, retention jobs, materialized views, or sharding when truly needed.
12. Use `EXPLAIN` and real metrics to decide whether to partition or not.

## 2. What Is Partitioning in PostgreSQL?

**Declarative partitioning** lets you declare a parent table (*partitioned table*) whose data is stored in **partitions that are separate physical tables** according to partition key rules. Applications can run queries against the parent table as a single logical table.

```text
                         orders  (logical parent table)
                                  |
                    PARTITION BY RANGE (created_at)
                                  |
                 +----------------+----------------+
                 |                |                |
                 v                v                v
           orders_2026_09   orders_2026_10   orders_2026_11
           [Sep 01-Oct 01)  [Oct 01-Nov 01)  [Nov 01-Dec 01)
                 |                |                |
              September        October          November
                data             data             data
```

Rows are routed into a partition based on the partition key value. The partitioned parent table **is not a heap storing all rows like a regular table**. It holds the definition and partitioning structure, while the partitions are where the data is stored.

### 2.1. One Logical Table, Many Physical Relations

When reading:

```sql
SELECT *
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

PostgreSQL can read only the October partition if the partition bounds and predicate align. This is **partition pruning**.

When reading:

```sql
SELECT * FROM orders;
```

the query must inspect data in **every relevant partition** to return the complete result; there is no logical basis to skip unfiltered months.

### 2.2. Partitioning Is Not Sharding by Default

A standard partitioned table inside a single PostgreSQL instance:

- Remains in the same DBMS, the same logical cluster, and the same server resource boundaries.
- Has multiple physical heaps/indexes per partition.
- Does not automatically distribute data across multiple independent PostgreSQL servers.
- Does not automatically provide linear write throughput scaling across machines.

**Sharding** is an architecture for distributing data/load across different nodes, requiring its own routing, consistency, transaction, and operational plan. Splitting a table into 12 monthly partitions **does not** give you 12 database servers.

### 2.3. Partitioning Does Not Shrink Data Size on Its Own

If a table has 100 million rows and is split into 12 partitions, the total row count is still 100 million. Child indexes, metadata, and physical files may make total storage **larger or different** from the original table depending on the design. Partitioning primarily lets PostgreSQL **avoid inspecting irrelevant parts**, and allows administrative operations on an isolated part when appropriate.

## 3. Three Declarative Strategies: RANGE, LIST, and HASH

PostgreSQL supports three common forms of declarative partitioning:

| Type | Routing Rule | Typical Workload | Cautions |
| --- | --- | --- | --- |
| **RANGE** | Value ranges with lower and upper bounds. | Logs, daily/monthly events, time-series data, numeric ranges. | Upper bound is typically **exclusive**; future partitions must be created ahead of time. |
| **LIST** | An explicitly enumerated set of values. | Region, business category, stable tenant groups. | Excessive cardinality and frequent changes create too many partitions. |
| **HASH** | Hash function distributing by modulus/remainder. | Evenly distributing data by tenant/customer ID across a fixed number of partitions. | Time-range queries usually cannot prune by hash ID; changing the bucket count is harder. |

### 3.1. RANGE by Month

```sql
CREATE TABLE range_orders (
    order_id bigint NOT NULL,
    created_at timestamptz NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY RANGE (created_at);

CREATE TABLE range_orders_2026_10
PARTITION OF range_orders
FOR VALUES FROM ('2026-10-01 00:00+00')
TO              ('2026-11-01 00:00+00');
```

Values from **Oct 01 00:00 UTC up to before Nov 01 00:00 UTC** go into the October partition. Choose boundaries consistently with respect to timezone.

### 3.2. LIST by Region

```sql
CREATE TABLE region_orders (
    order_id bigint NOT NULL,
    region text NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY LIST (region);

CREATE TABLE region_orders_north
PARTITION OF region_orders
FOR VALUES IN ('north');

CREATE TABLE region_orders_south
PARTITION OF region_orders
FOR VALUES IN ('south');
```

The query `WHERE region='north'` can touch only the north partition if the condition is pruning-compatible.

### 3.3. HASH by customer_id

```sql
CREATE TABLE hash_orders (
    order_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY HASH (customer_id);

CREATE TABLE hash_orders_p0
PARTITION OF hash_orders
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE hash_orders_p1
PARTITION OF hash_orders
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE hash_orders_p2
PARTITION OF hash_orders
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE hash_orders_p3
PARTITION OF hash_orders
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

An equality predicate on `customer_id` allows PostgreSQL to target the corresponding hash partition. However, it cannot deduce that a range `created_at >= ...` maps to a single hash bucket, because the hash is determined by `customer_id`.

### 3.4. Subpartitioning

A partition can itself be a partitioned table, for example:

```text
orders PARTITION BY RANGE (created_at)
  |
  +-- 2026_10 PARTITION BY HASH (tenant_id)
  |      +-- bucket 0
  |      +-- bucket 1
  |      +-- bucket 2
  |      +-- bucket 3
  |
  +-- 2026_11 PARTITION BY HASH (tenant_id)
         +-- bucket 0
         +-- bucket 1
         +-- bucket 2
         +-- bucket 3
```

This can help certain workloads that filter by both time and tenant. However, the number of physical relations grows by the **product of the branches**, bringing greater management, planning, and maintenance complexity. Do not use subpartitioning merely on the assumption that "finer splitting is always faster."

## 4. First Valid Goal: Partition Pruning

**Partition pruning** is the elimination of partitions proven unable to contain rows matching a query.

For example, on a time-range partitioned table:

```sql
SELECT COUNT(*)
FROM range_orders
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

If there are 36 monthly partitions, the planner/executor can read only the October partition instead of inspecting all three years of data.

### 4.1. Pruning Is Not an Index Scan

Two distinct layers must be distinguished:

```text
WHERE created_at falls in October
                |
                v
     Partition pruning
  skips all non-October partitions
                |
                v
   Scan the October partition:
      - Seq Scan?
      - Index Scan?
      - Bitmap Heap Scan?
      - Index Only Scan?
```

Partition pruning **selects which child tables need to be examined**. After that, the planner still has to choose how to access data **inside** each remaining partition. If October holds 30 million rows and a query fetches a single order by `order_id`, an index on `order_id` within the partition can still be critical.

### 4.2. Strong Benefits When Queries Filter Close to the Partition Key

For a table partitioned by `created_at`:

```sql
WHERE created_at >= :start_time
  AND created_at < :end_time
```

is a pattern much more likely to leverage partition bounds than a query filtering only by:

```sql
WHERE customer_id = :customer_id
```

If `customer_id` is not the partition key, every monthly partition **could** contain orders for that customer. Time-based pruning cannot eliminate partitions based solely on a `customer_id` predicate.

### 4.3. Conditions Incompatible with the Partition Key

For example:

```sql
WHERE date_trunc('month', created_at)
    = TIMESTAMPTZ '2026-10-01 00:00+00'
```

If the table is RANGE-partitioned directly on `created_at`, wrapping the column in an expression may prevent PostgreSQL from deriving which partition range to read, depending on the partition key definition, data types, and version.

When the semantics call for a UTC month, expressing it as a half-open interval is usually clearer:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
```

Do not arbitrarily replace a business-timezone condition with UTC if the product defines months in a local timezone; define the exact boundaries first.

### 4.4. Pruning Depends on the Predicate, Not the Partition Count

A table split into 120 partitions where queries always filter a single month can work reasonably well. Conversely, a table split into only four partitions where every query scans all four may yield no meaningful pruning benefit. **The number of partitions alone does not tell you whether queries will run faster.**

## 5. Second Valid Goal: Lifecycle Management and Old Data Deletion

This is often the **most tangible operational benefit** of time-based partitioning.

Suppose logs are retained for 12 months. With a regular table, deleting 50 million old rows:

```sql
DELETE FROM logs
WHERE occurred_at < TIMESTAMPTZ '2025-11-01 00:00+00';
```

can generate heavy MVCC churn, WAL volume, dead tuples, vacuum work, index maintenance, locks, and I/O pressure. With a partition containing only expired data, you can use partition management operations to remove the **entire chunk of data** without deleting rows one by one.

### 5.1. Dropping an Old Partition

```sql
-- Illustrative pattern: only when logs_2025_10 is truly an old partition
-- and its data is eligible for deletion under policy:
-- DROP TABLE logs_2025_10;
```

Dropping a partition is a DDL operation rather than row-by-row tuple deletion, and **is not free in terms of locks or WAL metadata**. Mechanically, however, it generally avoids the massive row-by-row processing of `DELETE`.

### 5.2. DETACH for Archival Before Deletion

A retention workflow can look like this:

```text
Expired partition
   |
   +-- verify retention/legal hold/backup
   |
   +-- DETACH partition from parent table
   |
   +-- archive/export if needed
   |
   +-- DROP detached table when eligible
```

`DETACH PARTITION` turns the partition into a standalone relation. Detaching it **does not automatically delete the data**; this makes it convenient for archiving.

### 5.3. Prerequisites for Safe DROP

Never drop a partition based solely on its table name:

- Has the time range expired according to policy?
- Are there orders, invoices, or records that must be retained for regulatory reasons?
- Is there late-arriving data or are records updated retroactively?
- Is there a verified backup/archival copy?
- Are there downstream CDC, ETL, reports, foreign keys, or dependent views?
- Can it be rolled back or restored?

Partitioning helps **enforce retention**, but it cannot decide the retention policy on its own.

### 5.4. Data Deletion Not Aligned with Partition Boundaries

If policy requires "retain exactly a rolling 90 days," while partitions are **monthly**, on November 15 the August partition may contain both expired data and data still within the 90-day window.

You cannot DROP the entire August partition and still preserve the exact 90-day cutoff. You must choose an appropriate granularity (daily/weekly/monthly), combine `DELETE` for the boundary edge, or revise the retention definition with approval.

### 5.5. Why Is This Different from VACUUM?

`DELETE` marks rows as no longer visible under MVCC, and only afterward does `VACUUM` reclaim row versions when safe. Dropping an intact partition is a DDL operation that removes the relation altogether, without needing to delete rows individually via MVCC. Consequently, retention aligned with partition boundaries is often much more predictable at very large data volumes.

## 6. Third Valid Goal: Scoped Maintenance and Administration

When a large table is split into partitions along proper boundaries:

- You can `ANALYZE` a new partition after a large ingest.
- You can `VACUUM` partitions with heavy `UPDATE`/`DELETE` activity.
- You can handle index/bloat maintenance on a single partition as planned.
- You can move or archive old partitions per policy.
- You can evaluate statistics of "hot" partitions separately from "cold" ones.
- You can schedule maintenance within a specific time or tenant scope.

### 6.1. Distinguishing Hot and Cold Data

For example, in an orders system:

```text
2026-11: continuously updated  -> hot partition
2026-10: moderately updated    -> warm partition
2024-01: nearly immutable      -> cold partition
```

This distinction helps decide:

- Where autovacuum/vacuum and `ANALYZE` should focus.
- Which indexes are needed for historical queries.
- When a partition can be archived.
- Storage and maintenance resource allocation.

However, **partitioning does not automatically make old partitions read-only**. Enforcing immutability requires appropriate permissions, business logic, and governance controls.

### 6.2. Per-Partition Indexes

PostgreSQL lets you create an index on the parent table to manage corresponding definitions across partitions. Each partition has its **own physical index**; do not assume a single global B-tree spans all rows across all partitions like on an unpartitioned table.

This keeps individual index sizes smaller when pruning works well, but introduces per-partition multiplication overhead.

### 6.3. Parent and Child Statistics

Each partition can have a different data distribution, making last month's statistics differ from older months. The planner may use partition statistics and parent statistics depending on the query type. Some situations require proactively running `ANALYZE` on the parent, especially after major changes in child partitions.

Do not assume autoanalyze always keeps all inherited/partitioned parent statistics sufficiently up to date simply because child tables are actively receiving writes.

### 6.4. Scoped Maintenance Does Not Mean Zero Locks

Operations such as CREATE/ATTACH/DETACH/DROP partition, REINDEX, or structural ALTERs can still acquire locks on the parent/children and impact concurrent access. A good design helps **limit the data scope**, but does not eliminate the need for operational coordination.

## 7. Lab: Monthly Partitioned Events Table

This section demonstrates **partitioning goals** without relying on any external database. All commands are strictly for a practice database; never run them against real user tables. The examples use modern PostgreSQL declarative partitioning.

### 7.1. Create the Schema and Parent Table

```sql
CREATE SCHEMA IF NOT EXISTS partition_goal_lab;

CREATE TABLE partition_goal_lab.events (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    tenant_id integer NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (occurred_at, event_id)
) PARTITION BY RANGE (occurred_at);
```

Pay close attention to `PRIMARY KEY (occurred_at,event_id)` instead of `PRIMARY KEY (event_id)`: for a time-partitioned table and the corresponding PostgreSQL rules, a unique/primary key constraint on the parent must include the relevant partition key columns so uniqueness can be guaranteed without a conventional global index spanning child tables. Section 16 explains this in detail.

### 7.2. Create Three Partitions

```sql
CREATE TABLE partition_goal_lab.events_2026_09
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2026-09-01 00:00+00')
TO              ('2026-10-01 00:00+00');

CREATE TABLE partition_goal_lab.events_2026_10
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2026-10-01 00:00+00')
TO              ('2026-11-01 00:00+00');

CREATE TABLE partition_goal_lab.events_2026_11
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2026-11-01 00:00+00')
TO              ('2026-12-01 00:00+00');
```

The partitions have contiguous, non-overlapping bounds. Because `timestamptz` with explicit UTC offsets is used, the definitions do not depend on the session's timezone display settings at query time.

### 7.3. Load 18,000 Events Through the Parent Table

```sql
INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type, payload
)
SELECT
    g::bigint,
    CASE
        WHEN g <= 6000 THEN
            TIMESTAMPTZ '2026-09-01 00:00+00'
        WHEN g <= 12000 THEN
            TIMESTAMPTZ '2026-10-01 00:00+00'
        ELSE
            TIMESTAMPTZ '2026-11-01 00:00+00'
    END
    + (((g - 1) % 28) * INTERVAL '1 day')
    + (((g - 1) % 1440) * INTERVAL '1 minute'),
    1 + (g % 10),
    CASE (g % 4)
        WHEN 0 THEN 'view'
        WHEN 1 THEN 'purchase'
        WHEN 2 THEN 'click'
        ELSE 'refund'
    END,
    jsonb_build_object('source', 'lab', 'sequence', g)
FROM generate_series(1, 18000) AS series(g);
```

This experiment should only be run **once on an empty table**. Re-running it will cause duplicate primary key errors. The data is synthetically generated; do not extrapolate execution times to infer production throughput.

### 7.4. Verify Which Partition Each Event Belongs To

`tableoid` is a system column showing the OID of the physical relation containing the row. Cast with `::regclass` to display the table name:

```sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS event_count,
    MIN(occurred_at) AS first_event,
    MAX(occurred_at) AS last_event
FROM partition_goal_lab.events
GROUP BY tableoid
ORDER BY tableoid::regclass::text;
```

With the intact lab dataset, there are three partitions and each contains **6,000 rows**. `tableoid` lets you observe actual routing, though by itself it does not prove pruning for an arbitrary query.

### 7.5. Query a Single Month

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

Observe:

- Does the plan access `events_2026_10`?
- Are `events_2026_09` and `events_2026_11` eliminated?
- Does the planner use a Seq Scan or an index inside the remaining partition?
- Are total buffers and timing proportional to the subset size?

Because the query targets exactly one month, PostgreSQL can determine that partitions outside October are irrelevant. On a small dataset, a **Seq Scan on the October partition alone is normal**: pruning and index scans are not the same concept.

### 7.6. Query Without the Partition Key

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE tenant_id = 3;
```

`tenant_id` is not the partition key of this RANGE table on `occurred_at`. Every month can contain tenant 3, so PostgreSQL generally must examine multiple partitions. If `tenant_id` is an important filter, an appropriate child index can help, but it does not remove the need to probe monthly partitions that could still hold matching rows.

### 7.7. Index on the Parent, Physical Indexes on Children

```sql
CREATE INDEX idx_events_tenant_time
ON partition_goal_lab.events (tenant_id, occurred_at DESC);

ANALYZE partition_goal_lab.events;
```

In modern declarative partitioning versions, creating an index on the parent table manages corresponding indexes across existing partitions. The key `(tenant_id,occurred_at)` can speed up lookups within each partition, but it does not cause `WHERE tenant_id=3` to prune time-based RANGE partitions.

Try again:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at
FROM partition_goal_lab.events
WHERE tenant_id = 3
  AND occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
ORDER BY occurred_at DESC
LIMIT 20;
```

The query has both a condition enabling partition pruning and a filter/ORDER BY supporting index usage within the partition. The planner may still pick a different access path if the data is small or cost estimates differ.

### 7.8. Query Across All History

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM partition_goal_lab.events;
```

No constraint allows skipping any specific month, so the plan may scan all three partitions and aggregate the result. This clearly illustrates that **partitioning is not an automatic accelerator for full-table scans**.

### 7.9. Data Outside Defined Ranges

Try an INSERT intentionally falling outside all three months:

```sql
-- Run separately only when your client allows observing the error:
INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type
)
VALUES (
    20001,
    TIMESTAMPTZ '2026-12-05 12:00+00',
    1,
    'view'
);
```

Without a default partition and without a child covering December, PostgreSQL will report **no partition found for row**. If the statement runs inside an explicit transaction block, the SQL error places the transaction into an aborted state until properly rolled back.

This is not an index error: partition routing requires a destination partition to accept the new value.

### 7.10. Create the Future Partition and Retry the Insert

```sql
CREATE TABLE partition_goal_lab.events_2026_12
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2026-12-01 00:00+00')
TO              ('2027-01-01 00:00+00');

INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type
)
VALUES (
    20001,
    TIMESTAMPTZ '2026-12-05 12:00+00',
    1,
    'view'
);
```

Once the previous test error is rolled back and the session is ready for SQL execution, the subsequent INSERT succeeds. The lab now has **18,001 rows**: the original 18,000 rows plus one new row. That will change the full-table COUNT result if you re-run the `EXPLAIN ANALYZE` queries.

### 7.11. Testing a Default Partition

Instead of letting new INSERTs fail, you can declare a default child:

```sql
CREATE TABLE partition_goal_lab.events_other
PARTITION OF partition_goal_lab.events
DEFAULT;
```

A default partition catches rows that do not match any declared partition. It is useful as a safety net for late/out-of-range data, but:

- It can mask failures in the scheduler that creates future partitions.
- It can accumulate "misplaced" data, making pruning and maintenance unpredictable.
- When attaching/creating a new partition, PostgreSQL may have to scan the default partition to ensure it contains no rows belonging to the new range, depending on constraints and workflow.
- `DEFAULT` must never be treated as the permanent destination for all new data.

In the lab, December already has its own partition, so the INSERT in 7.10 does not go into default. To test default, pick a timestamp **outside** all existing bounds, and never run such tests on production.

### 7.12. Listing Partitions

Several ways to inspect partitions:

```sql
SELECT
    parent.relname AS parent_name,
    child.relname AS partition_name,
    pg_get_expr(child.relpartbound, child.oid) AS partition_bound
FROM pg_inherits AS inh
JOIN pg_class AS parent ON parent.oid = inh.inhparent
JOIN pg_class AS child ON child.oid = inh.inhrelid
JOIN pg_namespace AS n ON n.oid = parent.relnamespace
WHERE n.nspname = 'partition_goal_lab'
  AND parent.relname = 'events'
ORDER BY child.relname;
```

In `psql`, you can use metacommands such as `\d+ partition_goal_lab.events` to inspect the structure and partitions. `\d+` is a `psql` client command, not SQL sent directly to the server.

## 8. Planning-Time vs. Execution-Time Pruning

A query with deterministic literals:

```sql
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

typically gives the planner enough information to eliminate partitions at plan time. However, applications often use parameterized prepared statements:

```sql
PREPARE events_by_time(timestamptz, timestamptz) AS
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= $1
  AND occurred_at <  $2;
```

PostgreSQL can prune at **planning time** or **execution time**, depending on capabilities and plan context. Therefore:

- Do not conclude "prepared statements cannot prune."
- Neither assume every parameterized predicate always prunes at planning time.
- Measure on your target major version with actual custom/generic plans.

### 8.1. Testing a Generic Plan in the Lab

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE events_by_time(
    TIMESTAMPTZ '2026-10-01 00:00+00',
    TIMESTAMPTZ '2026-11-01 00:00+00'
);

ROLLBACK;

DEALLOCATE events_by_time;
```

`plan_cache_mode` is a setting available on supported PostgreSQL major versions (since PostgreSQL 12). Depending on the plan shape and version, `EXPLAIN` may show `Subplans Removed`, unexecuted nodes, or only the remaining nodes. Interpret the output according to the specific mechanism rather than relying on a single fixed string.

### 8.2. Pruning Is Not Partition-Wise JOIN

Eliminating partitions based on a `WHERE` clause differs from executing JOIN/aggregate per partition. PostgreSQL provides *partition-wise join* and *partition-wise aggregate* capabilities under suitable conditions, with overhead that increases as the partition count grows.

Do not assume that partitioning two tables by the same month will cause every JOIN to automatically run one-to-one across partitions. You must check the partition schemes, join conditions, planner settings, bound compatibility, and actual `EXPLAIN` output.

## 9. When Partitioning Is Genuinely Worth Considering

### 9.1. Time-Growing Data with Clear Retention

Examples:

- Access logs retained for 90 days.
- Audit events retained for 12 months by policy.
- Telemetry/metrics retained per day.
- Clickstream queried primarily over time windows.

Favorable traits:

1. Most queries restrict the time window fairly tightly.
2. New rows land in the current/future partition.
3. Old data becomes rarely modified.
4. Deletion/archival rules align with partition boundaries.

The **biggest benefit** may lie in retention/maintenance, not necessarily `SELECT` latency.

### 9.2. Very Large Tables Queried by a Fixed Category

For instance, a regional system with 4–8 regions:

```sql
WHERE region = 'south'
```

If queries routinely filter by region and data/maintenance are truly independent per region, LIST partitioning can be helpful.

However, if the system has only 100,000 rows, an index `(region,...)` may be simpler and fast enough. Do not choose LIST just because `region` has few distinct values.

### 9.3. Selective Multi-Tenant Workloads

Partitioning by tenant ID or a hash of tenant ID can narrow access scope in some systems:

```sql
WHERE tenant_id = ?
```

However, evaluate:

- How many tenants are there?
- How skewed is the row count per tenant?
- Is there an oversized tenant generating most of the data?
- Do queries always know the tenant?
- Are cross-tenant uniqueness and foreign keys required?
- Are system-wide queries or cross-tenant reports needed?

One partition **per tenant** can suit a small, relatively stable number of tenants requiring isolated operations; with tens of thousands of small tenants, this strategy usually causes an explosion of relations and indexes.

### 9.4. Separating Hot/Cold Maintenance

Systems where recent partitions are frequently updated while history is nearly immutable can optimize vacuum/analyze schedules, indexes, and archival by data region. Still, verify the real workload before assuming older partitions have truly gone cold.

## 10. Unsuitable Case 1: Table Not Large Enough or Lacking a Specific Problem

A 200,000-row table with proper indexes and acceptable latency should not be partitioned just because "the table keeps growing." PostgreSQL B-trees perform very well at large scale when schema, indexes, and queries are well designed.

### 10.1. Distinguish Size from Symptoms

Better questions than "how many GB is the table?":

- Which specific query is slow, and how many rows match it?
- Is the planner doing a seq scan when an index is needed?
- Is an index matching `WHERE` and `ORDER BY` missing?
- Are there large sorts, inaccurate join estimates, or N+1 queries?
- Does old data need scheduled bulk `DELETE`s?
- Is VACUUM/autovacuum lagging due to long transactions or write rate?
- Are disk/RAM/network and concurrency the actual bottleneck?

If the main problem is a lookup by `order_id` returning a single row, creating a unique index on `order_id` on a regular table can solve it directly without partitioning.

### 10.2. Why Can Partitioning Slow Down Small Tables?

When a table occupies only a few data pages, a seq scan can be very cheap. After splitting into dozens of child tables, the planner must inspect partition metadata, build plan nodes, open the relevant relations, and coordinate multiple branches. This overhead can outweigh the savings from reading fewer pages.

There is no universal threshold such as "mandatory partitioning at 10 million rows" or "never partition under 1 GB" applicable to every workload. Benchmark before and after on representative data.

### 10.3. When Might You Still Partition a Modestly Sized Table?

If retention requirements are strict and mandate dropping an entire month every period, partitioning can offer **operational** value before query latency ever degrades. In that case, the decision is driven by policy and growth projections, not current size alone.

## 11. Unsuitable Case 2: Queries Do Not Filter by the Partition Key

Suppose a table is RANGE-partitioned by `created_at`, yet the hottest query is:

```sql
SELECT *
FROM partition_goal_lab.events
WHERE event_id = 12345;
```

`event_id` does not indicate which time partition holds the row. With 36 months, PostgreSQL may have to search across many child indexes or scan across many partitions.

### 11.1. What About Indexing event_id?

You can create:

```sql
CREATE INDEX idx_events_id
ON partition_goal_lab.events (event_id);
```

However, on a standard declarative partitioned table, this index consists of local child indexes. It **is not a single global B-tree** locating an `event_id` across all partitions without knowing the month.

PostgreSQL can use child indexes to search quickly within each partition, but it must inspect all partitions that could contain `event_id`. As the partition count grows large, the overhead of probing many indexes can become significant.

### 11.2. Queries Without Time Filters Requiring Full History

For example:

```sql
SELECT tenant_id, COUNT(*)
FROM partition_goal_lab.events
GROUP BY tenant_id;
```

The query must aggregate data across the entire history; partitioning cannot skip months simply because rows are grouped by tenant. Partition-wise aggregation or parallel scans may help if eligible, but there is no guarantee it outperforms an unpartitioned table with equivalent structure and resources.

### 11.3. Querying by customer_id When Partitioned by status

If screens always search for a specific customer without knowing `status`, LIST partitioning by `status` can also force every query to check many partitions. Choosing a partition key misaligned with access patterns is a common cause of **many partitions with poor pruning**.

### 11.4. Alternatives

Before partitioning:

1. Create an `(event_id)` index or a composite index tailored to the hot query on a regular table.
2. Check whether the API/query can retain the date to enable pruning if the business flow naturally knows the date.
3. If global lookup by ID is required, consider a reliable metadata/directory model mapping ID→partition, though that introduces additional architecture with its own consistency and transactional responsibilities.
4. When time cannot be derived from the ID, do not expect time-based partitioning to shorten ID-based lookups by itself.

## 12. Unsuitable Case 3: Too Many Tiny Partitions

A 100-million-row log table split into:

```text
12 monthly partitions
365 daily partitions
8,760 hourly partitions
525,600 per-minute partitions in one year
```

Having many small partitions can sharply increase:

- The number of relation/index entries in system catalogs.
- Query planning time and plan-node management cost.
- Metadata/relcache and associated memory usage.
- The number of files/file descriptors potentially opened.
- Autovacuum/analyze activity across many child relations.
- DDL cost for creating/attaching/detaching/indexing.
- Complexity of migrations, backups, monitoring, and alerting.

### 12.1. Partition Granularity Must Match Query Patterns and Retention

If 95% of queries read one week of data and retention drops monthly, daily or monthly partitions may both be worth evaluating depending on daily volume and maintenance windows.

If queries read a whole year, splitting by minute almost certainly creates excessive metadata/planning overhead without useful pruning.

### 12.2. There Is No Universal "Maximum" Partition Count

PostgreSQL continuously improves pruning, planning, and partition management across major versions. Still, that does not produce a universal rule like "1,000 partitions is always safe" or "above 200 is definitely slow." Practical limits depend on:

- Size and complexity of each partition.
- How many partitions queries actually have to examine.
- Query frequency and prepared plans.
- Number of indexes/constraints per child.
- DDL concurrency and metadata cache.
- Hardware and configuration.

Benchmark on your actual system and PostgreSQL version.

### 12.3. Subpartitioning Can Multiply Partition Counts Exponentially

For example: 36 months × 128 hash buckets = **4,608 leaf partitions**, excluding parent nodes and indexes. If each leaf has 3 indexes, the number of physical index relations grows dramatically.

Multi-level splitting needs a benefit strong enough to justify that cost; never assume it is inherently "better than single-level partitioning."

## 13. Unsuitable Case 4: Frequently Changing Partition Key

A good partition key is typically **immutable** over the record's lifecycle, such as event creation timestamp or an immutable tenant ID by design. Conversely, an order's `status` often changes:

```text
pending -> paid -> shipped -> completed
```

### 13.1. LIST by status Causes Row Movement

If:

```sql
CREATE TABLE status_orders (
    order_id bigint NOT NULL,
    status text NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY LIST (status);
```

gives each status its own partition, then when `UPDATE ... SET status='paid'` changes the partition key, PostgreSQL may have to **move the row from the old partition to the new partition** under cross-partition row movement semantics.

This is not like updating a non-key column within the same heap. Row movement can increase index work, WAL volume, trigger/constraint overhead, and contention with other transactions.

### 13.2. Moving Rows Between Partitions Is Not Free

In execution terms, PostgreSQL can represent row movement similarly to a **DELETE from the source partition and an INSERT into the destination partition**, with the corresponding concurrency and consistency rules. This impacts:

- Indexes across both partitions.
- Foreign keys, triggers, and table policies.
- Locking and serialization behavior.
- Replication/CDC interpretation depending on configuration.

Do not pick LIST partitioning on `status` **merely because status is a frequent filter** if status changes continually and other queries gain nothing.

### 13.3. Risk of Missing Destination Partition

If a new status `'returned'` appears before a matching partition or default partition exists, an `UPDATE` changing the partition key can fail because the row cannot be routed.

### 13.4. Alternative Options

An index on `status`, a partial index for `pending` rows, or a composite `(tenant_id,status,created_at)` index can serve `SELECT`s without forcing physical row movement on every status change. Measure actual write costs first.

## 14. Unsuitable Case 5: Expecting Global Uniqueness on a Key Without the Partition Key

This is a **crucial** design limitation of PostgreSQL declarative partitioning.

Suppose a table is defined as:

```sql
CREATE TABLE partition_goal_lab.events (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    ...
) PARTITION BY RANGE (occurred_at);
```

The application wants `event_id` to be globally unique regardless of month. However, in standard PostgreSQL partitioning, **any unique/primary key constraint declared on the partitioned parent must include all partition key columns**. When the partition key uses expressions/functions, additional restrictions apply to declaring unique/primary keys on the parent.

### 14.1. Why?

Partitions have separate physical indexes. If uniqueness were checked only on `event_id` inside each child, two records with the same `event_id` in different months could coexist because each child only enforces uniqueness over its own rows.

Partition boundaries must be part of the unique key so that two rows with the same unique key cannot reside in two different partitions.

### 14.2. Viable Primary Key by Month

In the lab:

```sql
PRIMARY KEY (occurred_at, event_id)
```

This guarantees uniqueness of the **pair** `(occurred_at,event_id)`, which does not mean `event_id` is globally unique on its own.

Test this inside a transaction so the dataset stays clean:

```sql
BEGIN;

INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type
)
VALUES
    (90001, TIMESTAMPTZ '2026-10-05 00:00+00', 1, 'view'),
    (90001, TIMESTAMPTZ '2026-11-05 00:00+00', 1, 'view');

SELECT event_id, occurred_at, tableoid::regclass
FROM partition_goal_lab.events
WHERE event_id = 90001
ORDER BY occurred_at;

ROLLBACK;
```

Two rows with the same `event_id` and different `occurred_at` **do not violate PRIMARY KEY(occurred_at,event_id)**. The final `ROLLBACK` restores the lab data to its initial state.

### 14.3. Do Not Declare PK(event_id) on a Time-Partitioned Parent

```sql
-- INVALID example for a parent partitioned by occurred_at:
-- ALTER TABLE partition_goal_lab.events
-- ADD CONSTRAINT events_event_id_unique UNIQUE (event_id);
```

PostgreSQL cannot enforce global uniqueness using local indexes on a partitioned table in that manner.

### 14.4. Workarounds and Their Trade-offs

- **Use a composite key (occurred_at,event_id)** in the schema and all reference paths if business semantics allow.
- **Change the partition key** to a column included in the required uniqueness constraint if it fits the workload.
- **Maintain a separate identity/registry table** with a unique `event_id` on an unpartitioned table, managing consistency alongside inserts into the partitioned table.
- **Generate globally unique IDs at the application layer** (e.g., identifiers with sufficient entropy) so collision probability is negligible, though **that is not equivalent to a database-enforced global UNIQUE constraint**.
- If strict `unique(event_id)` enforcement is mandatory and lookups frequently use `event_id`, consider **not partitioning the table by time**.

Do not attempt to simulate global uniqueness by running a `SELECT` check before `INSERT` across concurrent transactions; that introduces race conditions without proper synchronization and constraints.

## 15. Foreign Keys and Referential Key Design

The unique key restriction directly affects foreign keys:

> If a partitioned parent table only has `PRIMARY KEY (occurred_at,event_id)`, a child table cannot reference `event_id` alone as though it had a global unique constraint.

### 15.1. Composite Foreign Key Example

```sql
CREATE TABLE partition_goal_lab.event_notes (
    note_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_occurred_at timestamptz NOT NULL,
    event_id bigint NOT NULL,
    note_text text NOT NULL,
    FOREIGN KEY (event_occurred_at, event_id)
        REFERENCES partition_goal_lab.events
            (occurred_at, event_id)
);
```

Example inserting a note:

```sql
INSERT INTO partition_goal_lab.event_notes (
    event_occurred_at, event_id, note_text
)
SELECT
    occurred_at, event_id, 'Verified event'
FROM partition_goal_lab.events
WHERE event_id = 100
LIMIT 1;
```

In the lab, `event_id` 100 is unique due to how the data was generated. `LIMIT 1` is only for simplicity in the example, **not** an enforcement of `event_id` uniqueness in the schema.

### 15.2. Query APIs Must Carry the Full Key

If a public API accepts only:

```text
GET /events/100
```

while the database only enforces uniqueness on `(occurred_at,event_id)`, the application must decide whether `event_id` is truly a system-wide ID. Storing the timestamp in notes/foreign keys and looking up `event_id` across partitions represents an **API and data-model design change**, not just a DDL statement.

### 15.3. Foreign Keys Are Supported in PostgreSQL, but Not Free

Modern PostgreSQL major versions support foreign keys involving partitioned tables under the appropriate rules and syntax. Still, referential constraints can complicate `DROP/DETACH` of old partitions, bulk loads, and migrations.

Do not assume a 10-billion-row events table can drop a partition without considering referencing note/order/customer rows. Plan for dependent data before deleting or detaching.

### 15.4. Unsuitable Scenario

If many child tables currently have foreign keys to `orders(order_id)` and the application does not have the order creation date everywhere, migrating `orders` to daily RANGE partitioning can carry massive migration cost.

The retention benefit must be weighed against rewriting the entire referential model. Sometimes an unpartitioned table paired with another archival strategy is the lower-risk option.

## 16. UPSERT, UNIQUE, and Operations Changing the Partition Key

PostgreSQL supports `INSERT ... ON CONFLICT` when a matching unique arbiter exists, but on partitioned tables you must understand the partition scheme and unique key.

### 16.1. ON CONFLICT on a Composite Key

With the data inserted in Section 7, row `event_id=100` has `occurred_at` on Sep 16 at 01:39 UTC. Use that exact pair to observe the conflict target on the composite key:

```sql
BEGIN;

INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type
)
VALUES (
    100,
    TIMESTAMPTZ '2026-09-16 01:39+00',
    1,
    'purchase'
)
ON CONFLICT (occurred_at, event_id)
DO UPDATE SET
    event_type = EXCLUDED.event_type;

-- Test only; do not persist changes to the original record.
ROLLBACK;
```

The command updates the existing record by composite key, and `ROLLBACK` restores the lab data. If you change `occurred_at` to a different timestamp, the key pair differs and `INSERT` will create **a new row with a duplicate event_id**, which remains valid under the composite PK. Therefore, **never rely on this composite key to assume a standalone event_id has global idempotency**.

### 16.2. The Conflict Target Must Match the Unique Key

`ON CONFLICT (event_id)` cannot rely on `PRIMARY KEY (occurred_at,event_id)` to detect global `event_id` conflicts. The arbiter must match an applicable unique index/constraint.

### 16.3. DO UPDATE Is Not a Free-Form Cross-Partition Mover

PostgreSQL has restrictions on `ON CONFLICT DO UPDATE` on partitioned tables when updating a conflicting row's partition key would require moving the row to a different partition. Do not assume every UPSERT can both resolve a conflict and relocate a row into a new partition.

If business logic frequently alters creation date, tenant, or partition key inside an UPSERT, that is a strong sign the partition key may be ill-suited.

## 17. Unsuitable Case 6: Heavily Skewed Data and Queries

Consider a system with 100 tenants:

```text
Tenant 1:    85% of total data and 90% of write traffic
Tenant 2:     5% of total data
Tenants 3-100: remaining 10%
```

If you LIST-partition one child per tenant, tenant 1's partition remains an enormous, very "hot" table. Partitioning does not split tenant 1's load on its own.

### 17.1. Does Hash Partitioning Solve All Skew?

HASH on `tenant_id` distributes **tenant IDs** across buckets; every row for a given tenant is still routed by the same hash key to the same bucket in that hash design. If one tenant generates 85% of the data, the bucket holding that tenant remains huge.

Hash partitioning does not hash each row independently to spread one massive tenant across every bucket. That is the difference between hashing **tenant_id** versus hashing **event_id**.

### 17.2. Is Switching the Key to event_id Worth It?

If you HASH on `event_id` to spread a huge tenant's rows evenly, queries like `WHERE tenant_id=?` cannot prune effectively by `event_id`. You reduce physical row-ID skew at the expense of losing tenant-based pruning.

**Partitioning must solve a specific workload problem**; it cannot simultaneously eliminate every form of skew, optimize every query, and remove every hotspot by default.

### 17.3. Analyze Along Three Dimensions

For multi-tenant workloads, evaluate:

1. **Data skew:** rows/bytes per tenant.
2. **Read skew:** which tenants/queries generate most reads.
3. **Write skew:** which tenants/tables generate most `UPDATE`/`INSERT`s.

Appropriate solutions might include subpartitioning for large tenants, dedicated tables, workload isolation, or sharding—each carrying its own transaction, query, and operational trade-offs.

## 18. Unsuitable Case 7: Cross-Partition JOIN, GROUP BY, or ORDER BY

Partitioning helps most when irrelevant partitions are eliminated. For a system-wide query:

```sql
SELECT
    tenant_id,
    COUNT(*) AS event_count
FROM partition_goal_lab.events
GROUP BY tenant_id
ORDER BY event_count DESC
LIMIT 10;
```

PostgreSQL still has to inspect data across many partitions to compute total events per tenant over the full history.

### 18.1. Global Time ORDER BY

```sql
SELECT event_id, occurred_at
FROM partition_goal_lab.events
ORDER BY occurred_at DESC
LIMIT 20;
```

The planner may choose strategies like Append/Merge Append and scan appropriate indexes depending on the data. Some cases benefit from time ranges, but **do not assume monthly partitioning guarantees the planner reads only the latest month** when the query has no filter.

For example, the newest partition might be empty, timestamps could have unusual distributions, a default partition could hold outlier data, and the planner must prove eligibility before skipping other branches. Inspect `EXPLAIN` and actual rows/buffers.

### 18.2. JOIN Between Tables Partitioned on Different Keys

Suppose `orders` is partitioned by time and `customers` by region:

```text
orders PARTITION BY RANGE(created_at)
customers PARTITION BY LIST(region)
```

A JOIN `orders.customer_id = customers.customer_id` does not naturally align child-to-child. PostgreSQL may have to plan a JOIN across multiple partition scans and materialization/hash structures.

Avoid choosing mismatched partition schemes for tables that are constantly joined without evaluating the query plan impact.

### 18.3. Partition-Wise Join/Aggregate Is Not Automatic

PostgreSQL supports partition-wise join/aggregate under suitable conditions and corresponding planner settings. For instance:

```sql
SHOW enable_partitionwise_join;
SHOW enable_partitionwise_aggregate;
```

Check the default values and exact behavior on the running major version/server. Enabling partition-wise options can increase **planning time/memory** proportionally to the number of partitions, and they are only chosen when the query, partition bounds, keys, and costing match.

### 18.4. Alternatives for All-Time Reports

If the application regularly displays total orders per tenant across five years, consider:

- Appropriate indexes or parallel scans on a regular table.
- Materialized views or periodic rollups if slight staleness is acceptable.
- Summary tables maintained transactionally or via an outbox.
- A dedicated analytics system for heavy aggregations.

Monthly partitioning may still be great for retention, but it does not magically turn an all-time aggregation into a single-partition query.

## 19. Unsuitable Case 8: Seeking Higher Write Throughput Without Changing System Limits

A single PostgreSQL server has:

- Finite disk IOPS.
- Finite CPU.
- WAL writer and checkpoint I/O sharing the same infrastructure.
- Lock/contention and connection pool limits.

Splitting a table into 64 hash partitions does not multiply write throughput by 64x. All partitions still operate within the same cluster/instance unless a distributed architecture is used.

### 19.1. Partitioning Can Relieve Certain Bottlenecks

In specific scenarios, separating indexes and heaps per partition can:

- Limit the working index size touched when the partition key is known.
- Isolate vacuum/maintenance work.
- Alter contention patterns or cache locality.
- Enable parallelization of eligible queries/maintenance.

However, **these benefits are workload-dependent**, not a guarantee of linear write scaling.

### 19.2. INSERT Routing Has Its Own Overhead

Every `INSERT` into the parent table must determine the target partition and satisfy its constraints/triggers. With too many partitions, this routing itself adds noticeable overhead.

Bulk loads can route through the parent or load in a controlled manner directly into the appropriate partition, provided partition constraints, security, and procedures are respected. Never bypass the parent purely for speed if doing so inadvertently skips validation or operational contracts.

### 19.3. When Multiple Machines Are Truly Needed

If the bottleneck exceeds a single instance's CPU/I/O/storage capacity, evaluate:

- Vertical scaling / better hardware.
- Connection pooling and query optimization.
- Read replicas for read-heavy workloads.
- Sharding / distributed databases when data and write load must span multiple nodes.
- OLAP or streaming systems for analytics.

Declarative partitioning can be one component of a larger architecture, but **it does not implement those layers by itself**.

## 20. Unsuitable Case 9: Retention Does Not Align with Partition Bounds

Some systems require deletion **by business entity**, not by time:

```text
Delete all data for customer A
Keep customer B's data indefinitely
Retain data under legal hold
Delete individual accounts upon request
```

If RANGE-partitioned by month, customer A's data may appear in **every single month**. Deleting customer A still requires row-level `DELETE`/logical deletion across many partitions.

### 20.1. Not Every Deletion Policy Allows Dropping a Partition

Dropping a monthly partition deletes **every customer's** data in that month. If policy permits deleting only customer A, you cannot drop the whole partition without destroying other customers' data.

### 20.2. Would Partitioning by Tenant Solve It?

If tenant A has a dedicated partition and policy genuinely requires deleting the **entire tenant**, LIST partitioning per tenant can help. Yet that raises the partition count and becomes impractical when tenant counts are very large.

Choose based on the **actual unit of deletion/archival**, not on a marketing claim that partitioning always lets you DROP old data.

### 20.3. Soft Deletes and Legal Holds

If records carry legal holds, soft-delete flags, or retention exceptions, time-based partitioning cannot know which individual rows must be kept. A separate business model and data governance workflow are required. Never drop a partition—even if most rows have expired—while it still holds rows that must be preserved.

## 21. Unsuitable Case 10: Automation Is Not Ready

For time-based tables, partitions must exist **before new rows arrive**. A system relying on manual monthly partition creation is prone to failing right at the start of a new month.

### 21.1. Minimum Operational Readiness

- Pre-create future partitions ahead of schedule with sufficient buffer.
- Alert if the next partition does not yet exist.
- Ensure proper indexes, constraints, and permissions on new partitions.
- Run `ANALYZE` after bulk loads when needed.
- Monitor for late-arriving data or invalid timestamps.
- Track default partition growth if one is used.
- Schedule attach/detach/archive/drop aligned with retention.
- Control locks, backups, dependencies, and DDL rollback procedures.

If an organization cannot maintain these practices, partitioning can **reduce reliability** rather than improve it.

### 21.2. The Problem with a Neglected DEFAULT Partition

For example:

```text
November partition exists
December partition was not created
DEFAULT absorbs all December data

By mid-December:
  DEFAULT holds 50 million rows
  many queries touch DEFAULT
  ATTACHING December partition requires validating/moving data
```

By default, declaring a bounded partition does not automatically "cleanly migrate rows out of DEFAULT into the new monthly child." You need a proper migration/validation workflow, which can take time and hold locks.

### 21.3. Late-Arriving Data

An event arriving on November 15 with `occurred_at` on September 30 still needs the September partition if event time is the partition key. If September was already dropped due to retention, the `INSERT` will fail or land in `DEFAULT`.

The design must choose between **event time** and **ingestion time** as the partition key:

- Event time fits historical reporting by when events occurred.
- Ingestion time fits certain operational workflows based on arrival time.
- The two can diverge widely; picking the wrong one affects pruning, routing, and retention.

## 22. When Should Indexes Be Preferred Over Partitioning?

Most typical ORM/API queries are selective lookups:

```sql
SELECT order_id, status, amount
FROM orders
WHERE tenant_id = 15
  AND customer_id = 9001
ORDER BY created_at DESC
LIMIT 20;
```

On an unpartitioned table, a B-tree such as:

```sql
CREATE INDEX idx_orders_tenant_customer_time
ON orders (
    tenant_id,
    customer_id,
    created_at DESC
);
```

can solve the problem directly. Monthly partitioning will not speed up finding a customer if the query does not specify a date range.

### 22.1. B-Tree for Equality and Top-N

Composite B-trees usually fit well for:

- `WHERE tenant_id=? AND customer_id=?`.
- `WHERE order_id=?` when global uniqueness/lookup is needed.
- `ORDER BY created_at DESC LIMIT ?` with matching key ordering.
- Keyset pagination on ordered keys.

### 22.2. Partial Index for a Rare Status

```sql
-- Example on an unpartitioned orders table:
CREATE INDEX idx_orders_pending_by_tenant
ON orders (tenant_id, created_at DESC)
WHERE status = 'pending';
```

If hot queries only fetch pending orders, a small partial index can outperform LIST partitioning on a frequently changing status. Of course, it still incurs index maintenance cost when `status` changes.

### 22.3. BRIN for Physically Correlated Append-Only Data

A very large event table inserted chronologically can benefit from **BRIN**:

```sql
-- Example on a regular events table:
CREATE INDEX idx_events_brin_time
ON events USING BRIN (occurred_at);
```

BRIN indexes are typically tiny, summarizing block ranges, and suit physically correlated columns. However, they return candidate page ranges that must be rechecked and do not directly provide sorted output like a B-tree.

**BRIN and partitioning can work together**; they are not mutually exclusive. Still, if the only goal is time filtering without fast partition drops, trying BRIN on a regular table can be a simpler first step.

### 22.4. Query Optimization Before Structural Migration

Do not partition a table just to mask poorly written SQL:

```sql
SELECT *
FROM orders
ORDER BY created_at DESC
OFFSET 1000000 LIMIT 20;
```

The bottleneck may be deep `OFFSET` pagination rather than a lack of partitions. Keyset pagination with an appropriate index often addresses the root issue cleanly.

## 23. Alternatives to Partitioning

| Primary Need | Option to Check First or Alongside | When Partitioning Is Worth Considering |
| --- | --- | --- |
| Single-row lookup by ID | Unique B-tree/index on the exact key. | When retention/maintenance is also a goal and IDs can be routed. |
| Tenant + time queries | Composite index, pruning logic in SQL. | When time-series volume is huge and queries usually bound day/month. |
| Time-range scans on append table | BRIN/B-tree on timestamp. | When bulk DROP/archival on clean bounds or scan bounding is needed. |
| Per-customer deletion on request | Indexed DELETE, retention workflow, soft-delete policies. | When data separates cleanly by deletion unit and partition count stays reasonable. |
| All-time aggregations | Materialized view, summary table, OLAP. | Can aid maintenance, does not replace pre-aggregation. |
| Table bloat from long transactions | Identify snapshot/XID holders, vacuum, fix transaction boundaries. | Partitioning does not fix the root MVCC blocker. |
| Write throughput exceeding one host | Reduce contention/I/O, scale up, sharding/distributed strategy. | Partitioning can organize data, not distribute load across multiple servers. |
| Queries filtering frequently updated status | Partial/composite index. | LIST on status causes row movement; choose only with compelling justification. |
| Old data needing monthly archival | Controlled archival/retention job. | One of the strongest cases for partitioning. |

### 23.1. Why Can Options Be Combined?

A sound example:

```text
Monthly RANGE partitioning
  +-- local B-tree (tenant_id, occurred_at)
  +-- BRIN or other index for hot queries if appropriate
  +-- scheduled ANALYZE after ingest
  +-- DROP/DETACH after verified retention
```

Partitioning **manages data scope**; indexes **manage access within that scope**; statistics **help the planner pick plans**; application/retention workflows **manage business lifecycles**.

### 23.2. Do Not Optimize One Piece While Ignoring Total Cost

A design might speed up last month's query while slowing down cross-tenant queries, increasing `INSERT` overhead, and complicating migrations. The final decision must weigh overall SLAs, storage, operational risk, and retention necessity.

## 24. Partitioning and MVCC/VACUUM: Not a Universal Cure for Bloat

A table often bloats due to heavy `UPDATE`/`DELETE` activity or because long-running transactions prevent `VACUUM` from reclaiming dead versions. Monthly partitioning can:

- Confine the region of active updates.
- Allow targeted vacuuming on high-write partitions.
- Allow dropping expired old partitions instead of bulk `DELETE`s.

However, it **does not change MVCC rules**: if an old snapshot still needs tuple versions in an active partition, `VACUUM` cannot remove them merely because the table is partitioned.

### 24.1. Long Transactions Still Block Cleanup

```text
Session A: BEGIN REPEATABLE READ
           SELECT from October partition
           holds snapshot open for a long time

Session B: UPDATE many October rows, COMMIT

Autovacuum on October:
           must still respect Session A's snapshot
```

Partitioning does not "override" old snapshot visibility. If the root cause is `idle in transaction` holding back the horizon, fix transaction lifecycles, timeouts, and monitoring.

### 24.2. Dropping a Partition Is Not Always Non-Blocking

`DROP` is a DDL command subject to locks and dependencies. An active transaction reading a partition can force `ALTER`/`DROP` to wait depending on the operation and version.

Never deploy partitioning to production assuming retention `DROP`s can run anytime with zero user impact.

### 24.3. Partitioning and Anti-Wraparound

Partitions still carry transaction IDs requiring `VACUUM`/freezing. Never disable autovacuum globally assuming monthly partition drops will resolve all transaction ID wraparound concerns.

## 25. Choosing a Partition Key: Decision Matrix

Choosing a partition key is a **data architecture** decision, not merely SQL syntax.

### 25.1. RANGE on Time

Pros:

- Fits event/ingestion data naturally.
- Time-filtered queries prune easily.
- Monthly/daily retention can be simplified.
- Old partitions can be archived per lifecycle.

Cons:

- Lookups by ID without time must inspect many partitions.
- Global uniqueness on a standalone ID is hard to enforce on a time-partitioned parent.
- Late arrivals require old partitions or special handling.
- Granularity must balance retention accuracy against partition count.

### 25.2. LIST by Tenant/Region

Pros:

- Prunes when queries always include tenant/region.
- Individual tenants/regions can be maintained independently.
- Easy to reason about if value cardinality is low and stable.

Cons:

- One partition per tenant causes child-table explosion as tenants grow.
- Large tenants can become hotspots.
- Cross-tenant queries still inspect many partitions.
- Adding a new tenant requires preparing bounds/partitions or a default.

### 25.3. HASH by Identifier Key

Pros:

- Can distribute key values fairly evenly if the hash key is well distributed.
- Partition count can be chosen in a controlled way.
- Equality on the hash key routes directly to a bucket.

Cons:

- Does not support pruning by a time range unrelated to the hash key.
- Rebalancing/changing bucket count is not a simple parameter change; requires planning data/bound redistribution.
- Heavy skew on a single key value still concentrates in one bucket.
- Time-based retention requires `DELETE` across all buckets unless subpartitioned.

### 25.4. Need Both Time and Tenant?

If common queries look like:

```sql
WHERE tenant_id = ?
  AND occurred_at >= ?
  AND occurred_at < ?
```

and the dataset is enormous, consider:

- RANGE partitioning by time, with a local B-tree `(tenant_id,occurred_at)` inside each child.
- HASH partitioning by tenant, with a timestamp index inside each child.
- RANGE+HASH subpartitioning only once the benefit is proven substantial.

Do not automatically subpartition just because queries filter on two columns. A composite index inside each partition typically meets most needs with far less overhead.

### 25.5. Multi-Column Partition Keys Are Not Always "Two-Dimensional"

`PARTITION BY RANGE (tenant_id,occurred_at)` orders multi-column range keys lexicographically under PostgreSQL comparison semantics; it **does not automatically create a tenant × month grid** with two independent dimensions as intuitive as subpartitioning.

If the goal is hash buckets per tenant within each month, declare a proper hierarchy rather than treating a two-column range key as equivalent.

## 26. Choosing Partition Size: Day, Week, Month, or Year?

Granularity determines partition count, pruning precision, and retention accuracy.

### 26.1. Guidelines by Granularity

| Granularity | Strengths | Risks |
| --- | --- | --- |
| **Year** | Few partitions, simple administration. | Each child grows huge; single-week queries scan an entire year's child; monthly retention is difficult. |
| **Month** | Balanced choice for many time-series datasets. | Monthly data can still grow very large; rolling 90-day retention does not align cleanly. |
| **Week** | Smaller chunks than months, suits weekly retention. | More partitions; requires consistent ISO/UTC/business week boundaries. |
| **Day** | Very narrow pruning, daily DROP. | Many child tables/indexes, frequent DDL automation needed. |
| **Hour** | Suits certain massive telemetry workloads with hourly windows. | Metadata and maintenance overhead can be prohibitive without strong justification. |

This list is not ordered "smaller is better." The decision depends on rows/bytes per partition, query frequency, retention span, and maintenance capacity.

### 26.2. A Simple Child-Count Model

Suppose:

- Retention: 3 years.
- Monthly partitions: 36 children.
- Daily partitions: roughly 1,095 children.
- Hourly partitions: roughly 26,280 children.

If each partition has three indexes and separate metadata, physical object counts climb rapidly. Still, this arithmetic only predicts **object counts**, not exact planning time or IOPS. Benchmark against your workload.

### 26.3. Sizing Around the Hot Partition

One month containing 500 million rows may be too large for vacuum/index maintenance and retention windows, making weekly or daily better. Conversely, 100 rows per day retained for 10 years makes daily partitioning uneconomical.

### 26.4. Do Not Change Granularity Without Planning the Migration

Switching from monthly to daily is not just editing a `PARTITION BY` parameter. It usually entails building a new partition tree, moving/attaching data to match new bounds, managing indexes/constraints/locks, and coordinating with applications.

## 27. Partition Lifecycle Management

A solid partitioning plan should describe the full lifecycle:

```text
Design bounds
     |
     v
Pre-create future partitions
     |
     v
Ingest data + routing
     |
     v
ANALYZE/VACUUM and index maintenance
     |
     v
Partition becomes rarely modified
     |
     v
Verify retention / legal hold / downstream
     |
     v
DETACH / ARCHIVE / DROP per runbook
```

### 27.1. Pre-Creating Partitions Ahead of Time

Monthly schedule example:

```sql
-- Run only if the partition does not already exist:
CREATE TABLE partition_goal_lab.events_2027_01
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2027-01-01 00:00+00')
TO              ('2027-02-01 00:00+00');
```

If a `DEFAULT` partition exists and holds January rows, creating/attaching the January partition requires checking data inside `DEFAULT` and may require extracting/moving rows first.

Operationally, create partitions **ahead** of the new period and monitor bounds proactively rather than waiting for the first `INSERT` to fail.

### 27.2. Attaching Partitions with Historical Data

A common migration pattern:

1. Create a standalone table with matching structure.
2. Load data belonging to the target range.
3. Create matching indexes and an appropriate `CHECK` constraint per your strategy.
4. Verify no rows fall outside the bounds.
5. Run `ALTER TABLE parent ATTACH PARTITION ... FOR VALUES ...`.

If PostgreSQL cannot prove all rows satisfy the partition constraint, `ATTACH` may have to **scan the table to validate** it and hold appropriate locks.

### 27.3. DETACH PARTITION

Illustrative SQL pattern—**do not execute on the lab partition if still using it for exercises**:

```sql
-- ALTER TABLE partition_goal_lab.events
-- DETACH PARTITION partition_goal_lab.events_2026_09;
```

Once detached, `events_2026_09` still exists as an independent table. Queries against the parent no longer see data in the detached table.

### 27.4. DETACH PARTITION CONCURRENTLY

In PostgreSQL major versions supporting it, `DETACH PARTITION ... CONCURRENTLY` can reduce certain blocking compared to normal detach, but:

- It cannot run inside an explicit transaction block.
- It has version/configuration restrictions, e.g., involving a `DEFAULT` partition.
- It still runs across multiple phases and may wait on transactions.
- If interrupted, it may require resuming/recovering according to PostgreSQL's procedure.

Never assume "CONCURRENTLY" means zero locks, zero waiting, or zero user impact.

### 27.5. DROP Partition

Pattern:

```sql
-- Only after verifying retention and dependencies:
-- DROP TABLE partition_goal_lab.events_2026_09;
```

This is destructive data loss without another backup/archive. Distinguish between **knowing how to write the SQL** and **being authorized to execute destructive operations in production**.

### 27.6. Do Not Reflexively Use DROP CASCADE

If a partition has dependent objects, `DROP ... CASCADE` can drop unintended objects. Inspect dependencies and handle them deliberately. Never tack on `CASCADE` just to "make DDL succeed" without knowing what will be removed.

## 28. Inspecting the Partition Tree and Sizes

### 28.1. pg_partition_tree

On PostgreSQL major versions providing `pg_partition_tree`:

```sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree(
    'partition_goal_lab.events'::regclass
)
ORDER BY level, relid::regclass::text;
```

This function returns the tree structure (parents and children) for the specified partitioned table, which is especially useful for inspecting subpartitioning.

### 28.2. Size of Each Leaf Partition

```sql
SELECT
    relid::regclass AS partition_name,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS index_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_partition_tree(
    'partition_goal_lab.events'::regclass
)
WHERE isleaf
ORDER BY pg_total_relation_size(relid) DESC;
```

Physical relation size does not directly equal row count or live data size. Physical indexes, TOAST, and dead/free space all affect total size. Avoid choosing granularity from a single size number without examining queries and maintenance.

### 28.3. Row Estimates and ANALYZE Timestamps

```sql
SELECT
    s.relid::regclass AS partition_name,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_analyze,
    s.last_autoanalyze,
    s.last_vacuum,
    s.last_autovacuum
FROM pg_stat_all_tables AS s
WHERE s.relid IN (
    SELECT relid
    FROM pg_partition_tree(
        'partition_goal_lab.events'::regclass
    )
)
ORDER BY s.relid::regclass::text;
```

`n_live_tup`/`n_dead_tup` are statistical estimates, not exact point-in-time counts. If exact row counts are needed in the lab, run `COUNT(*)` on the data.

### 28.4. Verifying Pruning with EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

Check which partition scan nodes appear, which nodes never executed, and how many buffers and milliseconds were consumed. Do not judge performance solely by **cost**.

### 28.5. Partition Pruning Configuration

```sql
SHOW enable_partition_pruning;
```

Keep the appropriate setting enabled in production. To test the difference, use `SET LOCAL` inside a lab transaction for `EXPLAIN` to isolate the change:

```sql
BEGIN;
SET LOCAL enable_partition_pruning = off;

EXPLAIN
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';

ROLLBACK;
```

This is purely to compare plans; **turning off pruning is not a recommended optimization**. If a plan fails to prune, investigate predicates, parameter bindings, and partition bounds.

## 29. Operations Must Measure Both Planning Time and Execution Time

With many partitions, a query may execute very quickly once planned yet **take too long to plan**. Another query may have short planning time but long execution time from scanning many partitions.

### 29.1. EXPLAIN Metrics

```sql
EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
SELECT event_id, occurred_at
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
ORDER BY occurred_at DESC
LIMIT 20;
```

Inspect:

| Metric | Question |
| --- | --- |
| Planning Time | How much does the partition tree increase planning overhead? |
| Execution Time | After pruning/indexes, how long does the query actually run? |
| Rows, Actual Rows, Loops | Do row estimates diverge from reality? |
| Buffers Shared Hit/Read | How many pages were read from cache vs. disk? |
| Append / Merge Append | Are multiple child nodes being combined? |
| Subplans Removed / unexecuted nodes | How is pruning behaving at each applicable stage? |
| Sort / Incremental Sort | Does index/partition order avoid an extra sort? |

### 29.2. Benchmark Multiple Query Patterns

Benchmark at least:

1. Single-day/month queries with explicit predicates.
2. Multi-month queries.
3. ID lookups without timestamps.
4. Tenant queries spanning full history.
5. Aggregations or JOINs across many months.
6. Bulk inserts and UPDATEs with and without partition key changes.
7. Retention/maintenance DDL operations.

Never use the result of **a single** recent-month query to conclude partitioning benefits the entire system.

### 29.3. Checking Locks During DDL

In a test environment, you can inspect:

```sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    l.locktype,
    l.mode,
    l.granted,
    a.query
FROM pg_stat_activity AS a
JOIN pg_locks AS l ON l.pid = a.pid
WHERE a.datname = current_database()
ORDER BY a.pid, l.granted, l.mode;
```

This is a broad query that may return many rows and SQL text containing sensitive data. In production, enforce proper permissions, narrow the scope, and avoid pasting raw queries containing secrets into tickets. The goal is to spot `ALTER`/`ATTACH`/`DETACH` statements waiting on locks, not to blindly terminate backends.

### 29.4. Test Data Differs from Production

Partitioning often reveals its true costs only with large datasets, diverse query mixes, and high concurrency. Testing 18,000 rows across 3 partitions **only proves the mechanism**, not that a 1,000-partition production design will perform well.

## 30. Decision Matrix: To Partition or Not?

This table is a guide for architectural discussion, **not a quantitative PostgreSQL scoring system**.

| Criterion | Signals Favoring Partitioning | Signals for Caution or Not Partitioning |
| --- | --- | --- |
| **Data volume** | Very large, steadily growing dataset where each range needs separate management. | Small table, fast queries with standard indexes. |
| **Query patterns** | Most hot queries include predicates aligned with the partition key. | Hot queries routinely lack the partition key and must probe every child. |
| **Retention** | Bulk deletion/archival of whole months/days/tenants. | Per-customer/row deletions or legal holds misaligned with bounds. |
| **Partition key** | Immutable, known at INSERT and in SELECT. | Changes frequently, or late/out-of-range values are hard to manage. |
| **Partition count** | Reasonable relative to partition size and measured overhead. | Thousands or tens of thousands of tiny children with poor pruning. |
| **Uniqueness** | PK/UNIQUE can semantically include the partition key. | Strict global UNIQUE required on an ID excluding the partition key. |
| **Foreign keys** | Referencing model accepts composite keys and partition lifecycles. | Hundreds of existing FKs reference a single ID, making migration too costly. |
| **Read/write skew** | Partitions can be accessed/maintained independently and genuinely narrow scope. | One partition still dominates writes/reads. |
| **Operations** | Automated pre-creation, monitoring, archival, and recovery exist. | Manual partition creation with no clear owner or workflow. |
| **Measurement** | Benchmarks prove SLA/total-cost improvement. | Plans have not been measured, or you are masking unrelated issues like locks/stale stats. |

### 30.1. Simple Decision Flow

```text
                   What problem does the table have?
                               |
              +----------------+----------------+
              |                                 |
         Slow queries                 Hard retention/maintenance
              |                                 |
              v                                 v
      Are index/query designs          Can it be split by a
       already appropriate?           stable key/range?
           /       \                       /       \
          No       Yes                    No       Yes
          |         |                     |         |
          v         v                     v         v
    Optimize SQL/  Filter on           Consider   Evaluate
    indexes first  partition key?      archival/  partitioning
                   /        \          DELETE     by lifecycle
                  No        Yes         jobs      & costs
                  |          |
                  v          v
            Partitioning   Measure pruning
            may add little and planning/DDL
            value/be costly    overhead
```

### 30.2. Three Questions to Answer Before CREATE TABLE

1. **How much data can be skipped?** Which real queries provide predicates enabling pruning?
2. **Which lifecycle operation is simplified?** Can whole partitions be dropped/detached cleanly per policy?
3. **Which trade-offs are acceptable?** Unique keys, FKs, UPDATEs, INSERTs, operational complexity, and rollback strategy?

If all three answers are vague, it is too early to start a partitioned-table migration.

## 31. Case Study A: Access Logs Retained for 90 Days

**Context:**

- 200 million events/day.
- Operational queries mostly read the last 1–24 hours.
- Policy retains 90 days, then deletes daily.
- `occurred_at` is nearly immutable.
- Log IDs do not need to act as global unique keys referenced by other business tables.

### 31.1. Candidate Design

Daily **RANGE** partitioning is a strong candidate:

```text
access_logs
    +-- 2026_11_13
    +-- 2026_11_14
    +-- 2026_11_15
    +-- ... ~90 days of retention
```

### 31.2. Why It Fits

- Queries from 08:00 to 09:00 can prune most other days.
- Old daily data can be detached/archived/dropped after retention.
- The partition key is immutable.
- Each day holds huge volume, not just a handful of rows.
- Active partition count stays bounded.

### 31.3. Additional Design Requirements

- Handling logs arriving 2–7 days late.
- Timezone and UTC day boundaries.
- Indexes/BRIN inside partitions.
- 90-day storage footprint and I/O/WAL load.
- Automated pre-creation of future partitions.
- Retention/legal hold verification workflow.
- Planning cost for queries scanning all 90 days.

### 31.4. Conclusion

Here partitioning yields **two simultaneous benefits**: pruning and retention. Even so, benchmark against the actual workload and never assume dropping partitions is lock-free.

## 32. Case Study B: Users Table Queried by user_id

**Context:**

- 10 million users; profiles are updated.
- 99% of requests are `WHERE user_id=?`.
- Multiple tables (`orders`, `profiles`, `sessions`) reference `user_id`.
- No policy to drop entire time ranges.
- Global uniqueness on `user_id` is required.

### 32.1. Strong First Choice

A regular table with:

```sql
PRIMARY KEY (user_id)
```

and suitable indexes/queries is usually the right starting point. RANGE partitioning on `created_at` would force `user_id` lookups without a month to inspect many partitions, while global uniqueness on `user_id` without the partition key runs into declarative partitioning constraints.

### 32.2. When to Consider HASH?

Only if you have proven major write/read contention or key-based maintenance issues on the users table should you evaluate HASH on `user_id`. Even then, account for uniqueness, foreign keys, partition counts, and the difficulty of changing modulus.

Adding HASH partitions does not create multi-machine sharding.

### 32.3. Conclusion

For global ID lookups, **proper indexing and a simple schema** usually beat time-based partitioning adopted merely because the table is large.

## 33. Case Study C: Orders with Constantly Changing Status

**Context:**

```text
pending -> paid -> shipped -> returned
```

- Operational screens heavily query `pending` orders.
- Most orders change `status` multiple times.
- APIs look up by `order_id` and `tenant_id`.
- Retention is based on order creation date, not status.

### 33.1. Tempting but Harmful Option

LIST partitioning by `status` so pending queries read a single partition.

**Issues:** every status transition triggers row movement; many flows lack the partition key when looking up by ID; missing partitions for new statuses cause errors; date-based retention can no longer drop partitions cleanly.

### 33.2. Balanced Alternative

Prefer indexes:

```sql
-- Example on a regular orders table:
CREATE INDEX idx_orders_pending
ON orders (tenant_id, created_at DESC)
WHERE status = 'pending';
```

If you later partition by `created_at` because retention truly matters, you can maintain partial/composite indexes per partition and accept the associated overhead.

### 33.3. Conclusion

A frequently filtered column **does not automatically make a good partition key**, especially when it is mutable.

## 34. Case Study D: SaaS with 50,000 Tenants

**Context:**

- 50,000 tenants.
- 90% of tenants have few rows.
- A handful of tenants generate most of the traffic.
- Queries mostly filter by `tenant_id`.
- No requirement to detach/drop individual tenants daily.

### 34.1. Why Is LIST Per Tenant Risky?

Creating 50,000 child tables and matching indexes introduces huge metadata/catalog/planning/operational complexity while most children are tiny. A massive tenant remains a hotspot regardless.

### 34.2. HASH Partitioning by Tenant?

HASH with a benchmarked bucket count caps physical partition counts and aligns with tenant equality filters. Still, cross-tenant queries touch all buckets, and a huge tenant lands entirely inside a single bucket.

### 34.3. Alternatives

- Composite index `(tenant_id, key)` on a regular table.
- HASH partitions when workload size and goals are clear.
- Isolating oversized tenants via a separate operational strategy if permitted.
- Sharding when resources genuinely need to scale across servers.

### 34.4. Conclusion

There is no single right answer. Evaluate data skew, read/write mix, and real cost measurements instead of choosing based solely on tenant count.

## 35. Case Study E: Legal Per-Customer Deletion Requests

**Context:**

- Interactions table retained for two years.
- Users have the right to request deletion of their personal data.
- Legal hold exceptions exist.
- Queries usually filter by customer, sometimes by time.

### 35.1. What Does Monthly RANGE Solve?

It can help archive monthly history and prune time-bounded queries. Yet "delete customer A across two years" still requires finding and deleting A's rows across many partitions.

### 35.2. Does LIST Per Customer Fit?

With millions of customers, LIST per customer makes the partition count operationally unviable in most systems. Nor does it handle partial legal holds on specific records.

### 35.3. Alternative Direction

Customer indexes, verified deletion workflows, a retention/legal-hold data model, accurate archival, and observability. Partitioning can support monthly lifecycle management, but it does not replace subject-level deletion.

### 35.4. Conclusion

When the **partitioning unit and deletion unit do not match**, the partition-DROP advantage does not apply to that requirement.

## 36. Migrating an Active Table to a Partitioned Table

Suppose `orders` in production is currently a regular table and needs to become daily RANGE partitioned. This is a migration project—not merely running an imaginary `ALTER TABLE orders PARTITION BY RANGE(created_at)` in place.

### 36.1. Architectural Steps

A high-level plan:

1. **Audit** queries, indexes, constraints, FKs, triggers, permissions, RLS, and replication.
2. **Design the new parent**, partition key, bounds, granularity, and unique/PK model.
3. **Create partitions and indexes** matching the target schema.
4. **Backfill historical data** in controlled chunks.
5. **Sync ongoing writes** between source and target during transition via an evaluated mechanism.
6. **Validate completeness** via counts, checksums/business reconciliation, and constraints.
7. **Cut over** the application with a planned lock/downtime window.
8. **Monitor** latency, routing errors, autovacuum/`ANALYZE`, and replication post-cutover.
9. **Keep a rollback plan** to revert to the old model if errors arise.
10. **Clean up legacy structures** only after full verification and once the rollback window has passed.

You cannot guarantee a "zero-downtime" migration merely by adopting partitioning; feasibility depends on data volume, constraints, PostgreSQL version, and surrounding systems.

### 36.2. Constraints to Plan Up Front

- An existing `PK(id)` may not be valid on a `RANGE(created_at)` parent.
- Existing FKs pointing to `id` must be addressed if uniqueness changes.
- Application ORMs may assume a single `id` column is the unique primary key.
- Legacy queries may omit the partition key and lose pruning benefits.
- Batch jobs updating `created_at` or `tenant_id` may trigger row movement.
- Sequences/identities and defaults must be migrated accurately.
- Triggers, RLS policies, and direct permissions on child tables must be reviewed.
- Replication/CDC pipelines may depend on table names, replica identity, and event semantics.

### 36.3. Out-of-Bounds Data

Before migrating:

```sql
SELECT
    MIN(created_at),
    MAX(created_at),
    COUNT(*) FILTER (WHERE created_at IS NULL)
FROM orders;
```

If `created_at` is the partition key, you must handle `NULL`s or out-of-schedule values. RANGE partitions generally do not accept `NULL` unless a matching `DEFAULT` partition exists. Under declarative partitioning, rows matching no bound cause `INSERT`/`ATTACH` to fail unless handled explicitly.

### 36.4. Validation and Sample Mismatches

Checking `COUNT(*)` alone may be insufficient: two tables can have identical row counts yet mismatched rows. Reconcile by tenant/month, keys, data checksums, and business invariants. Do not treat checksums alone as a substitute for FKs or uniqueness if the new schema altered semantics.

### 36.5. Permissions and RLS

Because partitions are distinct physical relations, verify access privileges both through the parent and directly on children, along with policies and maintenance/ETL jobs. Never assume direct operations on a child partition behave identically to parent access with respect to permissions and RLS.

### 36.6. Transactions and DDL

Creation, indexing, attaching, and cutover steps have different lock levels and transaction rules. Some `CONCURRENTLY` options cannot run inside explicit transactions. Plan specifically for your major version rather than dumping all SQL into a single transactional script hoping every option is compatible.

## 37. Common Misconceptions and Design Pitfalls

### Misconception 1. "Large tables must always be partitioned"

No. Table size is an input, but the decision must rest on query patterns, indexes, retention, maintenance cost, and measurements.

### Misconception 2. "Partitioning always speeds up every SELECT"

No. Queries lacking the partition key may inspect many children; single-ID lookups can be simpler on a regular table with a global ID index.

### Misconception 3. "Partition pruning and Index Scan are the same thing"

No. Pruning selects partitions; an index scan chooses how to locate rows inside a remaining relation. You can prune effectively yet still use a Seq Scan on the child.

### Misconception 4. "Splitting finer is always faster"

No. Many tiny partitions increase planning time, metadata/index counts, and operational complexity.

### Misconception 5. "Time partitioning lets WHERE event_id=? know the month automatically"

No, unless the application supplies the time condition or uses another routing mechanism. A standalone event ID does not inherently imply a bound.

### Misconception 6. "An index on the parent is a single global index"

Not in standard declarative partitioning: a parent index manages physical indexes per partition, not a unified cross-partition index enforcing arbitrary global uniqueness outside the partition key.

### Misconception 7. "PRIMARY KEY(event_id) works fine even when partitioned by created_at"

PostgreSQL requires unique/primary-key constraints on a partitioned parent to include the appropriate partition key columns. Never copy an old PK blindly without redesigning.

### Misconception 8. "PRIMARY KEY(created_at,event_id) means event_id itself is unique"

No. Only the pair is enforced. The same `event_id` with a different `created_at` is valid under that constraint.

### Misconception 9. "One partition per tenant is always the best multi-tenant design"

No. With tens of thousands of small tenants, metadata/DDL/planning overhead becomes heavy, and one giant tenant remains a hotspot.

### Misconception 10. "HASH by tenant automatically spreads a large tenant across buckets"

No. Every row sharing the same `tenant_id` produces the same hash key and routes to the same bucket under that HASH design.

### Misconception 11. "LIST by status is great because WHERE status=... is common"

Not necessarily. Frequently changing statuses cause row movement across partitions and complicate retention and ID lookups.

### Misconception 12. "Having a DEFAULT partition eliminates the need to pre-create future partitions"

No. `DEFAULT` can silently absorb data meant for periodic partitions and make later attaches/maintenance expensive.

### Misconception 13. "Dropping a partition only deletes expired rows"

No. It removes the entire relation, so bounds must match retention, legal holds, and dependencies. Dropping the wrong month can destroy data that had to be kept.

### Misconception 14. "Rolling 90-day retention can safely DROP an entire monthly partition anytime"

Not accurately. A monthly partition may span both sides of the 90-day cutoff. Choose an appropriate granularity/policy or handle boundary edges.

### Misconception 15. "DETACH and DROP have the same effect"

No. `DETACH` unlinks the relation from the parent while preserving data in a standalone table. `DROP` deletes both the relation and its data.

### Misconception 16. "CONCURRENTLY means never waiting on locks"

No. Concurrent DDL reduces blocking under specific rules, yet still has wait phases, transaction restrictions, and interruption risks.

### Misconception 17. "Partitioning eliminates bloat caused by long transactions"

No. `VACUUM` on each partition still obeys the MVCC visibility horizon. Long-lived snapshots still block cleanup in the affected partitions.

### Misconception 18. "Indexes are no longer needed once partitioned"

No. A single monthly partition can contain tens of millions of rows; tenant or order ID lookups still require suitable access paths.

### Misconception 19. "With indexes, you never need partitioning even when retention is painful"

Indexes speed up finding rows, but they do not replace bulk `DROP`/archival over large ranges. The two features solve different problems.

### Misconception 20. "HASH partitions multiply write throughput by the bucket count"

No. On a single PostgreSQL instance, overall I/O, WAL, CPU, and contention remain bounded by the server; only specific workloads benefit.

### Misconception 21. "Two tables partitioned by the same month always get partition-wise JOINs"

Not automatically. It depends on join keys, schemes, bounds, planner settings, costs, and PostgreSQL version.

### Misconception 22. "Changing the partition key is just a normal UPDATE"

Not quite. It can force cross-partition row movement, impacting constraints, triggers, indexes, and WAL, and can fail if no target child exists.

### Misconception 23. "Once partitions are created, autoanalyze handles all child and parent stats automatically"

Not guaranteed. Monitor both per-partition and parent/inherited statistics in your specific PostgreSQL environment.

### Misconception 24. "Deleting a customer becomes fast thanks to monthly partitioning"

Unlikely. If a customer has data across all months, rows must still be processed across many partitions; dropping a month would wipe out other customers' data.

### Misconception 25. "Converting a regular table to partitioned is a single ALTER command"

No. It usually requires building a new structure, backfilling, syncing writes, adapting PK/FK/indexes, and executing a planned cutover.

### Misconception 26. "Partitioning automatically gives you read replicas or sharding"

No. Standard declarative partitioning stays within one cluster/instance; multi-node distribution is a separate architecture.

### Misconception 27. "In EXPLAIN, only Execution Time matters"

No. With many partitions, inspect `Planning Time`, pruning, child node counts, actual rows, loops, buffers, and concurrent workload behavior.

### Misconception 28. "Without literals, prepared statements cannot prune"

Not always true. PostgreSQL supports execution-time pruning in suitable cases. Inspect generic/custom plans and version behavior.

### Misconception 29. "Multi-column RANGE is equivalent to two-dimensional subpartitioning"

No. Multi-column range keys have lexicographical ordering semantics rather than a two-tier grid; build a partition tree if both dimensions genuinely need branching.

### Misconception 30. "The parent table holds the full heap so it still scans one big file"

No. A declarative partitioned parent is a logical/metadata relation; physical rows live in partitions. The planner can prune irrelevant children.

### Misconception 31. "Dropping a partition affects nothing else"

No. Foreign keys, views, replication, privileges, active transactions, and dependencies can all be impacted. Follow a runbook before `DETACH`/`DROP`.

### Misconception 32. "Every partition must have the exact same set of indexes"

Not necessarily. Queries on hot versus cold partitions can differ and index maintenance has a cost. However, when using indexes defined on the parent, understand how they map to child indexes if you diverge.

### Misconception 33. "Enable partition-wise join to speed up all JOINs"

No. Enabling partition-wise options can raise planning time and memory and brings no benefit if data or partition schemes do not align.

### Misconception 34. "Fast results on 18,000 rows prove the production strategy"

No. A small lab illustrates mechanics only; benchmark with realistic partition counts, row volumes, index sizes, concurrency, and query mixes.

## 38. Practice Exercises

The following exercises use the concepts and schema `partition_goal_lab`. Exercises involving destructive actions such as `DETACH`/`DROP` require **analysis or writing commented SQL**, never executing them outside a dedicated lab database without backups. For `EXPLAIN`, exact plans depend on version and cost, so focus on what indicators to observe rather than expecting a single fixed node.

### Exercise 1. Definitions

Distinguish a logical partitioned table from physical child partitions. Does a monthly RANGE parent table store all rows in its own heap?

### Exercise 2. Three Partition Types

Given three scenarios: time-based logs, stable geographic regions, and `customer_id` lookups across a fixed set of buckets. Match them to RANGE/LIST/HASH and explain your choices.

### Exercise 3. RANGE Bounds

With a partition from `2026-10-01 00:00 UTC` to `2026-11-01 00:00 UTC`, does the exact value `2026-11-01 00:00 UTC` belong to the October partition?

### Exercise 4. Time-Based Pruning

Write a query counting events from the start of October up to before the start of November and predict which partition(s) will be examined.

### Exercise 5. Missing Partition Key

Why might `WHERE tenant_id=3` on a table partitioned by `occurred_at` still access multiple months?

### Exercise 6. Partition Pruning vs. Indexes

A query reads only the October partition but uses a Seq Scan. Can you conclude pruning failed?

### Exercise 7. Missing Future Partition

What happens when inserting a December event into a parent that only has September–November children and no `DEFAULT`?

### Exercise 8. DEFAULT

What are the benefits and risks of a `DEFAULT` partition? Why should you monitor its row count and data age?

### Exercise 9. Inspecting Physical Relations

Write a query using `tableoid::regclass` to count rows per child partition.

### Exercise 10. Adding an Index

For `WHERE tenant_id=? AND occurred_at >= ? AND occurred_at < ? ORDER BY occurred_at DESC`, propose a suitable index on the parent and explain whether it aids pruning or intra-partition scanning.

### Exercise 11. Primary Key

Why can `PRIMARY KEY(event_id)` not be declared on a parent RANGE-partitioned by `occurred_at`? What does `PRIMARY KEY(occurred_at,event_id)` enforce?

### Exercise 12. Two Rows with the Same event_id

If two rows share `event_id=999` with `occurred_at` in different months, does `PRIMARY KEY(occurred_at,event_id)` forbid them?

### Exercise 13. Foreign Key

A notes table must reference events on a parent with a two-column primary key. Which columns must it store to reference a row directly via that key?

### Exercise 14. Orders Changing Status

Analyze why LIST partitioning by `status` can be a poor fit for an orders system regularly transitioning `pending→paid→shipped`.

### Exercise 15. Tenant Skew

Tenant A accounts for 90% of rows. Does HASH on `tenant_id` with 16 buckets spread Tenant A's rows evenly across 16 partitions?

### Exercise 16. Child Counts

For a three-year retention period, compare approximate partition counts for monthly, daily, and hourly splits. Which is always fastest?

### Exercise 17. 90-Day Retention

On November 14, can a policy requiring "delete right after 90 days" safely `DROP` the entire August partition? What must be checked?

### Exercise 18. DETACH and DROP

Compare the impact of `DETACH PARTITION` versus `DROP TABLE partition` on the underlying data and queries via the parent.

### Exercise 19. MVCC Considerations

An old `REPEATABLE READ` transaction holds a snapshot during updates on the October partition. Can autovacuum reclaim all old tuple versions simply because the table is partitioned?

### Exercise 20. All-Time Aggregation

Why must `SELECT tenant_id,COUNT(*) ... GROUP BY tenant_id` still read across many partitions? Name an alternative if a dashboard tolerates slight staleness.

### Exercise 21. Partition-Wise JOIN

Are two tables with different partition schemes guaranteed to join child-to-child? What factors must be checked?

### Exercise 22. Inspecting the Partition Tree

Write a query reading `pg_partition_tree` to list relation, parent, leaf flag, and level.

### Exercise 23. Size per Partition

Write a query displaying `pg_total_relation_size` for each leaf partition in the lab schema.

### Exercise 24. Reading EXPLAIN

A query filtering only October shows `Planning Time=120 ms` and `Execution Time=4 ms`. What should you investigate if the partition count grows sharply?

### Exercise 25. Indexes vs. Partitioning

A 5-million-row users table mostly runs `WHERE user_id=?` and has a primary key on `user_id`. Should you migrate immediately to RANGE partitioning by `created_at` to optimize this lookup?

### Exercise 26. Partitioning Is Not Sharding

Explain why 64 hash partitions on a single PostgreSQL instance do not equal 64 machines or 64x write throughput.

### Exercise 27. Prepared Statements and Pruning

With `WHERE occurred_at >= $1 AND occurred_at < $2`, at which stages can PostgreSQL prune? How can you test with a generic plan?

### Exercise 28. Appropriate Granularity

A log table gets 100 rows/day and is kept for 10 years. Is per-minute partitioning reasonable? Name at least three costs to consider.

### Exercise 29. Late-Arriving Events

The September partition was dropped per retention, yet a new event arrives with `occurred_at` in September. Which handling policies should be defined in advance?

### Exercise 30. Migration

An `orders` table has `PK(order_id)` and many FKs referencing `order_id`, and needs RANGE partitioning by `created_at`. Name the top three obstacles and a high-level migration sequence.

### Exercise 31. Partition Key Selection Process

A system queries by both `tenant_id` and `occurred_at`, with monthly retention. Compare time RANGE + local composite index against tenant HASH; should you jump straight to subpartitioning?

### Exercise 32. Case Study Analysis

A system handles 300 million events/day, retains 60 days, runs 95% of queries over the last 24 hours, and has a nearly immutable `event_time`. Is partitioning worth considering? By which criteria?

## 39. Suggested Solutions

### Answer 1. Parent Table and Partitions

The partitioned parent represents the logical table and partitioning definition, while child partitions store the physical heap rows. Do not picture the parent as storing a duplicate heap copy of all child rows.

### Answer 2. RANGE/LIST/HASH

| Scenario | Candidate Type | Reason |
| --- | --- | --- |
| Monthly/daily logs | Time RANGE | Easy time pruning and whole-interval retention. |
| Stable regional groups | LIST | Region queries can prune other groups. |
| Lookups by `customer_id` across finite buckets | HASH(customer_id) | Equality on ID can route to a single bucket. |

Do not assume these choices are mandatory for every table; an index on a regular table may already suffice.

### Answer 3. RANGE Bounds

No. `FROM ... TO ...` has an **inclusive lower bound and exclusive upper bound** in standard PostgreSQL RANGE declarations. The exact value `2026-11-01 00:00 UTC` belongs to the next partition if one exists.

### Answer 4. October Pruning

```sql
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

PostgreSQL has enough information to prune partitions outside October when bounds match; the remaining query may still use a Seq Scan or Index Scan on the October partition depending on cost.

### Answer 5. Tenant Is Not the Partition Key

The partition key is `occurred_at`. Because tenant 3 can have events in any month, `tenant_id=3` alone does not prove any time partition is empty for that query. A child index on tenant helps within partitions, but does not prune months.

### Answer 6. Seq Scan on a Child

No. Pruning may have already selected the exact right partition, and a Seq Scan on that partition is simply the cheapest plan. Check the child nodes in `EXPLAIN` rather than judging by the presence of Seq Scan.

### Answer 7. Missing Partition

`INSERT` finds no matching destination partition and raises an SQL error if there is no `DEFAULT`. Inside an explicit transaction, you must roll back or handle recovery before issuing further SQL statements.

### Answer 8. DEFAULT

`DEFAULT` catches out-of-range rows, but can hide failures to create new partitions, accumulate large amounts of data, and require validation/data movement when attaching later partitions. Monitor its row count, unexpected bounds, and partition creation schedules.

### Answer 9. tableoid

```sql
SELECT
    tableoid::regclass AS partition_name,
    COUNT(*) AS row_count
FROM partition_goal_lab.events
GROUP BY tableoid
ORDER BY tableoid::regclass::text;
```

`tableoid` reveals the physical relation; in the initial lab there are three partitions with 6,000 rows each before December is added.

### Answer 10. Index

```sql
CREATE INDEX idx_exercise_tenant_occurred
ON partition_goal_lab.events
    (tenant_id, occurred_at DESC);
```

This is a candidate index for tenant equality, time range, and time sorting. **Partition pruning** comes from the `occurred_at` predicate and parent bounds; the index accelerates searching inside the remaining selected partitions.

### Answer 11. Primary Key

Unique/PK constraints on a partitioned parent must include the partition key columns per PostgreSQL rules, because local indexes cannot enforce `event_id` uniqueness across all months. `PRIMARY KEY(occurred_at,event_id)` protects the pair, not `event_id` alone.

### Answer 12. Duplicate event_id Across Different Timestamps

It does not forbid them, as long as the two `(occurred_at,event_id)` pairs differ. If the business requires `event_id` to be globally unique, the current schema does not enforce it.

### Answer 13. Foreign Key

The child table must store both `event_occurred_at` and `event_id` and declare a composite foreign key referencing `(occurred_at,event_id)` on the parent:

```sql
FOREIGN KEY (event_occurred_at, event_id)
REFERENCES partition_goal_lab.events (occurred_at, event_id)
```

### Answer 14. Mutable Status

Each status change can move the row across LIST partitions, increasing write/index work and requiring destination partitions to exist. Partial/composite indexes on a regular table can serve `pending` `SELECT`s without partition-key row movement.

### Answer 15. Hash and Skew

No. If the hash key is solely `tenant_id`, all rows for Tenant A share the same key value and route to the same hash bucket by design. Tenant A can still make one bucket very hot.

### Answer 16. Child Counts

Over three years:

- Monthly: ~36 partitions.
- Daily: ~1,095 partitions.
- Hourly: ~26,280 partitions.

None is universally fastest; measure pruning ratio, rows/partition, planning overhead, indexes, and retention needs.

### Answer 17. Rolling Retention

Not by default. The August partition holds both early- and late-August data; some rows may still fall inside 90 days depending on the exact calculation cutoff. Check exact thresholds, timezone, legal holds, granularity, and edge-handling policies.

### Answer 18. DETACH vs. DROP

`DETACH` unlinks the partition from the parent while leaving the standalone table and its data intact; `DROP TABLE` deletes the relation and its data. Both are DDL operations with locks and dependencies to manage.

### Answer 19. MVCC

No. `VACUUM` still cannot remove old tuple versions needed by an active snapshot, even though the table is split into child partitions.

### Answer 20. All-Time Aggregation

There is no partition-key condition allowing other months to be skipped; the planner must process data across eligible partitions to compute the totals. A materialized view or summary table updated on a schedule/stream can serve dashboards quickly if staleness is acceptable and sync is managed.

### Answer 21. Partition-Wise JOIN

Not guaranteed. You must inspect partition keys, bounds, schemes, JOIN conditions, planner settings, costs, and PostgreSQL major version. Two tables split on different keys do not automatically align into matching partition pairs.

### Answer 22. Partition Tree

```sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree(
    'partition_goal_lab.events'::regclass
)
ORDER BY level, relid::regclass::text;
```

### Answer 23. Size per Child

```sql
SELECT
    relid::regclass AS leaf_name,
    pg_size_pretty(
        pg_total_relation_size(relid)
    ) AS total_size
FROM pg_partition_tree(
    'partition_goal_lab.events'::regclass
)
WHERE isleaf
ORDER BY pg_total_relation_size(relid) DESC;
```

### Answer 24. Planning Time

Planning Time is already many times larger than Execution Time. Investigate the partition count, planned node count, planning vs. execution pruning, generic vs. custom plans, query frequency, memory, and impact as child count grows. Do not try to tune index scans when execution is already fast.

### Answer 25. Users Table

Do not RANGE-partition by `created_at` just to optimize `user_id` lookups. A primary key/index on `user_id` fetches the row directly; partitioning by creation date introduces query routing and uniqueness/FK issues.

### Answer 26. Hash Is Not Sharding

Partitions remain inside the same PostgreSQL instance/cluster; splitting physical relations does not multiply CPU/disk/WAL writer capacity into 64 servers. A workload may benefit from data layout, but total capacity stays bound by the single system.

### Answer 27. Prepared Statement Pruning

It can happen at planning time when values are known or at execution time for parameters in supported plans. To test a generic plan:

```sql
PREPARE exercise_by_time(timestamptz, timestamptz) AS
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= $1
  AND occurred_at <  $2;

BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE exercise_by_time(
    TIMESTAMPTZ '2026-10-01 00:00+00',
    TIMESTAMPTZ '2026-11-01 00:00+00'
);

ROLLBACK;
DEALLOCATE exercise_by_time;
```

Observe `Subplans Removed` or unexecuted nodes depending on PostgreSQL major version and actual plan.

### Answer 28. Per-Minute Partitioning

Unreasonable in almost any design at 100 rows/day over 10 years. The huge partition count inflates metadata and indexes, complicates planning and DDL/backups/monitoring, and queries without per-minute filters gain nothing. Consider an unpartitioned table, or monthly/yearly partitions if retention truly demands it.

### Answer 29. Late-Arriving Events

You must decide:

- Accept or reject late data?
- Keep old partitions for a grace period?
- Use event time or ingestion time?
- Maintain a `DEFAULT`/quarantine table or separate backfill flow?
- Restore from archive or treat as already purged?
- Do retention/legal-hold rules permit storing late old events?

Never let routing errors silently turn into data loss.

### Answer 30. Migration with PK/FK

Three obstacles:

1. `PK(order_id)` cannot be declared on a parent partitioned by `created_at` because it lacks the partition key.
2. Numerous FKs referencing `order_id` alone require a new key/relationship model or an alternative approach.
3. API queries by `order_id` without `created_at` may have to search across partitions.

Sequence: audit → design PK/partition bounds → create table/children/indexes → backfill → sync writes → validate → controlled cutover → monitor and keep a rollback plan.

### Answer 31. Tenant + Time

Time RANGE fits monthly retention, while a local composite `(tenant_id,occurred_at)` index serves tenant queries within the month. Tenant HASH fits tenant equality, but cannot drop whole months cleanly without another time structure. Subpartitioning can support both, yet adds children and overhead; adopt it only after benchmarking against real row counts and query patterns.

### Answer 32. Huge Events with Short Retention

Strongly worth considering daily RANGE partitioning or another matching granularity, because:

- Daily data volume is massive.
- Most queries target recent windows.
- The partition key is nearly immutable.
- The 60-day retention policy aligns with a daily lifecycle.
- Hot/cold states and daily `DETACH`/`DROP` can be managed cleanly.

You still must calculate bytes/day, indexes, I/O/WAL, timezone, late events, replication, DDL locks, and operational ownership. Never promise specific read/write throughput gains without measuring.

## 40. Pre-Partitioning Decision Checklist

1. **Goal:** Do you need pruning, retention, maintenance, or are you trying to fix an unrelated bottleneck?
2. **Query evidence:** Do you have 10–20 hot queries with parameter distributions and real latency measurements?
3. **Partition key:** Do queries filter on that exact key frequently and explicitly?
4. **Routing:** Do `INSERT`s know the key and always have a matching child?
5. **Stability:** Will `UPDATE`s mutate the key and trigger frequent row movement?
6. **Bounds:** Are RANGE boundaries and timezones clearly defined?
7. **Retention:** Do deletion/archival policies align cleanly with whole partitions?
8. **Late data:** How will late-arriving events or skewed timestamps be handled?
9. **Child count:** How many partitions will exist after one year, three years, and full retention?
10. **Index design:** Are suitable indexes defined inside the remaining partitions?
11. **Uniqueness:** Can PK/UNIQUE semantically include the partition key?
12. **FKs:** Do referencing tables accept composite keys and partition lifecycles?
13. **UPSERT:** Do conflict targets match the constraint, and will they update the partition key?
14. **Skew:** Are tenant/time buckets reasonably balanced, or does one child dominate?
15. **Cross-partition queries:** Do full-history aggregations/JOINs/sorts dominate the workload?
16. **Planning cost:** Have you measured `Planning Time` at a representative child count?
17. **Concurrency:** Have you benchmarked concurrent `SELECT`/`INSERT`/`UPDATE`?
18. **Statistics:** Have parent/child `ANALYZE` and partition pruning been verified?
19. **Vacuum:** Have you distinguished MVCC blockers from partition-count issues?
20. **Automation:** Are future partition creation jobs and default-growth alerts in place?
21. **Archival:** Are backups, legal holds, and recovery procedures verified before `DROP`?
22. **Permissions/RLS:** Is access controlled on both parent and children if needed?
23. **Replication/CDC:** Do downstream consumers handle attach/detach/drop cleanly?
24. **Migration:** Are backfill, dual-write/CDC sync, cutover, and rollback plans ready?
25. **Alternatives:** Have composite B-trees, BRIN, partial indexes, query rewrites, or summary tables been tested?
26. **SLA:** Do post-change metrics prove the benefits outweigh operational costs?

## 41. Summary

**Partitioning is a data organization and storage lifecycle strategy, not a default speed boost.** It excels when a workload has two traits: **queries consistently filter by the partition key** and/or **data can be managed or deleted in whole partition chunks**.

Key takeaways:

- **RANGE** suits time-series data and retention; **LIST** suits stable value sets; **HASH** suits equality keys and bucketed distribution with a clear purpose.
- **Partition pruning** eliminates children that cannot contain results. It does not replace B-tree/BRIN indexes, statistics, or intra-child query tuning.
- **A large table alone does not mandate partitioning.** An unpartitioned table with proper indexes can be simpler, faster, and easier to maintain.
- **Queries lacking the partition key** may inspect many partitions; too many children inflate planning and metadata overhead.
- **Mutable partition keys** can force `UPDATE`s to move rows between partitions, raising cost and risk.
- **Unique/PK and FKs** must be carefully redesigned if you need global identifiers while partitioning on a different column.
- **Retention is only simple when the deletion unit matches partition bounds.** Dropping a partition is unsafe if rows must be preserved, held legally, or referenced.
- **A default partition is a fallback**, not a substitute for timely child creation and monitoring late/out-of-range data.
- **Partitioning does not cure bloat from old snapshots, fix bad queries, or turn a single instance into a sharded cluster.**
- **Measure pruning, Planning Time, Execution Time, buffers, and write/DDL overhead** across a representative query mix before migrating.
- **Operations are part of the design:** future partition creation, `ANALYZE`, index management, attach/detach, backup/archival, lock monitoring, and rollback plans all need clear ownership.

Final design principle:

> **Do not partition simply because a table is large. Partition when you can state precisely which data will be skipped during queries, which data will be managed independently, and why those gains outweigh the overhead of multiple relations.**

Without clear evidence supporting at least one of those goals, starting with index/query optimization and real workload measurement is usually the safer choice.
