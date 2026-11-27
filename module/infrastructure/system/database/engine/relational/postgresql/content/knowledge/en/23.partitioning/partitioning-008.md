# Multi-Level Partitioning and Partition-Count Overhead in PostgreSQL

When a PostgreSQL table grows to hundreds of millions or billions of rows, *table partitioning* helps narrow how much data queries read, manage data lifecycles by interval, and isolate maintenance work. For instance, an events table can be partitioned by month so a one-week query reads only one or two partitions instead of the entire history.

Yet operational needs can be more complex: inside each month, the system may also want to split by business region or tenant. This gives us **multi-level partitioning** (or *subpartitioning*).

Example:

```text
events                                  -- RANGE(event_at)
|
+-- events_2026_01                      -- Jan 2026, LIST(region)
|   +-- events_2026_01_north            -- region = NORTH
|   +-- events_2026_01_south            -- region = SOUTH
|   +-- events_2026_01_other            -- remaining regions
|
+-- events_2026_02                      -- Feb 2026, LIST(region)
|   +-- events_2026_02_north
|   +-- events_2026_02_south
|   +-- events_2026_02_other
|
+-- ... subsequent months
```

A query filtering only January events in the NORTH region can undergo **partition pruning** down to a single leaf partition, when predicates and execution plans align. However, every extra split adds child tables, child indexes, metadata, statistics entries, autovacuum work, and sometimes planning or locking overhead.

If you retain 36 months and split each month into 32 groups, you already have:

```text
36 monthly partitions
  x 32 subpartitions/month
  = 1,152 leaf partitions

+ 36 intermediate partitioned nodes
+ 1 root partitioned table
```

If each leaf partition carries four physical indexes, total leaf indexes reach **4,608**, excluding other objects. That is not just "another layer of data organization"; it significantly increases how many relations PostgreSQL must manage.

This lesson explains how to design multi-level partitioning, how PostgreSQL routes rows and prunes partitions, how to measure overhead as partition counts grow, and how to pick a sound partition count grounded in real queries and operations.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish root partitioned tables, intermediate partitions, and leaf partitions.
2. Design a two-level partition tree using `RANGE`, `LIST`, and `HASH`.
3. Write PostgreSQL DDL to create subpartitioning with `PARTITION BY` and `PARTITION OF`.
4. Explain why **partition pruning** depends on query predicates at each level.
5. Distinguish plan-time vs. execution-time pruning and spot the signs in `EXPLAIN`.
6. Calculate partition count growth as the product across levels, not merely root group counts.
7. Analyze partition-count costs for **planning, metadata/catalogs, relation locks, relcache, memory, file handles, indexes, statistics, autovacuum, DDL, and backup/restore**.
8. Explain why full-history queries may gain nothing—or even suffer extra overhead—from over-splitting.
9. Distinguish partition pruning from index scans, partition-wise joins, and partition-wise aggregates.
10. Identify `PRIMARY KEY`, `UNIQUE`, and `FOREIGN KEY` requirements on multi-level partitioned tables.
11. Handle out-of-range rows, default partitions, provisioning new partitions, and partition-key updates.
12. Weigh pros and cons of time-first vs. tenant/region-first level ordering.
13. Plan operations: pre-creation, attach/detach, retention, analyze, vacuum, and index maintenance.
14. Design benchmarks comparing single-level vs. two-level layouts, measuring both query latency and relation maintenance counts.
15. Avoid one-partition-per-customer, per-hour, or per-event designs without proven measurable benefits.

**Scope:** Modern PostgreSQL declarative partitioning. Exact syntax, pruning capabilities, constraint behavior, and maintenance features vary across versions; verify against your target PostgreSQL version and test on a representative workload. Run `DROP TABLE`/`CREATE TABLE` examples strictly in a disposable lab database.

---

## 2. Review of the Three Core Partitioning Methods

PostgreSQL supports three standard declarative partitioning methods.

### 2.1. RANGE — Splitting by Intervals

```sql
CREATE TABLE measurements (
    measured_at TIMESTAMPTZ NOT NULL,
    sensor_id BIGINT NOT NULL,
    value NUMERIC
) PARTITION BY RANGE (measured_at);
```

A monthly partition:

```sql
CREATE TABLE measurements_2026_01
PARTITION OF measurements
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO   ('2026-02-01 00:00:00+00');
```

RANGE bounds follow an **inclusive lower, exclusive upper** (*half-open interval*) model in standard configurations like this.

Suited to aging data, day/month range queries, and interval-based retention drops.

### 2.2. LIST — Splitting by Enumerated Value Sets

```sql
CREATE TABLE regional_data (
    region TEXT NOT NULL,
    payload JSONB
) PARTITION BY LIST (region);

CREATE TABLE regional_data_north
PARTITION OF regional_data FOR VALUES IN ('NORTH');

CREATE TABLE regional_data_south
PARTITION OF regional_data FOR VALUES IN ('SOUTH');
```

Suited to small sets of meaningful discrete groups such as regions, business lines, or markets.

Avoid blindly creating one LIST partition per tenant if tenant counts grow into the thousands or tens of thousands, as partition count itself becomes a heavy cost.

### 2.3. HASH — Splitting by Hash Value

```sql
CREATE TABLE tenant_data (
    tenant_id BIGINT NOT NULL,
    payload JSONB
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_data_h0
PARTITION OF tenant_data
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE tenant_data_h1
PARTITION OF tenant_data
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE tenant_data_h2
PARTITION OF tenant_data
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE tenant_data_h3
PARTITION OF tenant_data
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

HASH is handy for spreading many key values across a fixed chosen number of partitions without needing one partition per tenant.

**Never confuse HASH partitioning with multi-machine PostgreSQL sharding.** All declared partitions remain relations inside the same PostgreSQL database unless a separate distributed architecture is used.

---

## 3. What Is Multi-Level Partitioning?

Multi-level partitioning occurs when a **child partition of a parent table is itself declared as a partitioned table**. Each level can choose a different partitioning method and key matching the data model.

Example:

```text
RANGE(event_at)                -- level 1
   |
   +-- January 2026
   |      |
   |      +-- LIST(region)     -- level 2
   |            |
   |            +-- NORTH      -- leaf partition
   |            +-- SOUTH      -- leaf partition
   |            +-- DEFAULT    -- leaf partition
   |
   +-- February 2026
          |
          +-- LIST(region)
                |
                +-- NORTH
                +-- SOUTH
                +-- DEFAULT
```

A **leaf partition** sits at the end of a branch and stores physical rows in an ordinary heap. The root table and intermediate partitions are **partitioned tables** defining the hierarchy and routing rules.

### 3.1. Every Row Travels a Path from Root to Leaf

For a row:

```text
event_at  = 2026-01-15 09:00:00+00
region    = NORTH
tenant_id = 42
```

PostgreSQL resolves:

1. `event_at` falls in January at the RANGE level.
2. Within January, `region='NORTH'` falls in the NORTH LIST partition.
3. The row is stored in leaf partition `events_2026_01_north`.

Clients still simply execute:

```sql
INSERT INTO partition_levels_lab.events (...);
```

without manually picking leaf names. PostgreSQL routes by declared partition bounds.

### 3.2. Syntax Does Not Require Every Month to Have Identical Subpartitions

In theory, each intermediate partition can define a different subpartition layout. Operationally, however, **keep layouts consistent across periods** when business rules match, avoiding missing-partition bugs, uneven index coverage, and unpredictable maintenance.

### 3.3. When Is Two-Level Partitioning Worth Considering?

Reasonable cases include:

- Massive logs with monthly retention, split further into hash buckets per month to keep individual relation sizes manageable.
- Multi-tenant event tables where queries consistently bound both time and tenant.
- Time drives whole-subtree archival/purging, while the second level isolates operational subsets.
- Core queries and maintenance tasks can consistently touch only a handful of leaf partitions.
- Single-level monthly partitions remain too huge for `VACUUM`, index rebuilds, or localized operations.

Never add a second level merely to make partitions smaller if doing so **fails to improve pruning, maintenance, or concrete access paths**.

---

## 4. Standard Lab: Monthly RANGE, Regional LIST

This lab uses two months with three leaf partitions each. Run all DDL below on a test database.

> **Warning:** `DROP TABLE IF EXISTS ... CASCADE` deletes dependent objects in the lab schema. Run only in a resettable environment—never in production.

### 4.1. Create the Root Partitioned Table

```sql
CREATE SCHEMA IF NOT EXISTS partition_levels_lab;

DROP TABLE IF EXISTS partition_levels_lab.events CASCADE;

CREATE TABLE partition_levels_lab.events (
    event_at TIMESTAMPTZ NOT NULL,
    region TEXT NOT NULL
        CHECK (region IN ('NORTH', 'SOUTH', 'CENTRAL')),
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('VIEW', 'CLICK', 'PURCHASE')),
    amount NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (amount >= 0),
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (event_at, region, event_id)
) PARTITION BY RANGE (event_at);
```

Why does the `PRIMARY KEY` include both `event_at` and `region`?

- Level 1 partitions by `event_at`.
- Level 2 will partition by `region`.
- In standard PostgreSQL declarative partitioning, `UNIQUE`/`PRIMARY KEY` on the hierarchy must include all required partition key columns to ensure uniqueness across the tree along partition boundaries.
- Because there is no general global unique index spanning all leaf partitions, `PRIMARY KEY(event_id)` alone cannot be assumed valid for this tree.

If the application needs `event_id` globally unique independent of date and region, build an extra mechanism—such as a unique registry table or transactional ID-allocation/check architecture—rather than relying on local `UNIQUE(event_id)` per leaf.

### 4.2. Create January Partition and Declare the LIST Level

```sql
CREATE TABLE partition_levels_lab.events_2026_01
PARTITION OF partition_levels_lab.events
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO   ('2026-02-01 00:00:00+00')
PARTITION BY LIST (region);
```

The decisive line is the final clause:

```sql
PARTITION BY LIST (region)
```

It makes `events_2026_01` an **intermediate partition** rather than a leaf storing rows directly.

### 4.3. Three Leaves for January

```sql
CREATE TABLE partition_levels_lab.events_2026_01_north
PARTITION OF partition_levels_lab.events_2026_01
FOR VALUES IN ('NORTH');

CREATE TABLE partition_levels_lab.events_2026_01_south
PARTITION OF partition_levels_lab.events_2026_01
FOR VALUES IN ('SOUTH');

CREATE TABLE partition_levels_lab.events_2026_01_other
PARTITION OF partition_levels_lab.events_2026_01
DEFAULT;
```

Because of `region IN ('NORTH','SOUTH','CENTRAL')` on the root table, each month's `DEFAULT` partition primarily receives `CENTRAL` in lab data. Do not generalize that `DEFAULT` only receives `CENTRAL` on real tables lacking that `CHECK`.

### 4.4. Create February and Its Leaves

```sql
CREATE TABLE partition_levels_lab.events_2026_02
PARTITION OF partition_levels_lab.events
FOR VALUES FROM ('2026-02-01 00:00:00+00')
             TO   ('2026-03-01 00:00:00+00')
PARTITION BY LIST (region);

CREATE TABLE partition_levels_lab.events_2026_02_north
PARTITION OF partition_levels_lab.events_2026_02
FOR VALUES IN ('NORTH');

CREATE TABLE partition_levels_lab.events_2026_02_south
PARTITION OF partition_levels_lab.events_2026_02
FOR VALUES IN ('SOUTH');

CREATE TABLE partition_levels_lab.events_2026_02_other
PARTITION OF partition_levels_lab.events_2026_02
DEFAULT;
```

The tree now contains:

- One root table.
- Two monthly intermediate partitions.
- Six regional leaf partitions.
- **Nine table relations total**, excluding indexes.

### 4.5. Load 15,000 Sample Events

```sql
INSERT INTO partition_levels_lab.events (
    event_at, region, event_id, tenant_id,
    event_type, amount, payload
)
SELECT
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 59) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second',
    CASE (g.n % 3)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'SOUTH'
        ELSE 'CENTRAL'
    END,
    g.n::BIGINT,
    (g.n % 200)::BIGINT + 1,
    CASE (g.n % 5)
        WHEN 0 THEN 'PURCHASE'
        WHEN 1 THEN 'CLICK'
        ELSE 'VIEW'
    END,
    CASE WHEN g.n % 5 = 0
        THEN ROUND((g.n % 10000)::NUMERIC / 100, 2)
        ELSE 0::NUMERIC
    END,
    JSONB_BUILD_OBJECT('source', 'lab', 'n', g.n)
FROM GENERATE_SERIES(1, 15000) AS g(n);

ANALYZE partition_levels_lab.events;
```

Day offsets 0..58 from Jan 1, 2026 span January and February; with no March records, every row routes cleanly into the created tree.

### 4.6. Verify Physical Placement with tableoid

PostgreSQL exposes system column `tableoid` to inspect which physical relation holds each row:

```sql
SELECT
    tableoid::REGCLASS AS leaf_table,
    COUNT(*) AS event_count
FROM partition_levels_lab.events
GROUP BY tableoid
ORDER BY tableoid;
```

Seeing counts across all six leaves confirms routing worked. `leaf_table` may render with or without a schema prefix depending on `search_path` and `REGCLASS` formatting.

### 4.7. Inspect the Tree with pg_partition_tree

```sql
SELECT
    relid::REGCLASS AS relation_name,
    parentrelid::REGCLASS AS parent_relation,
    isleaf,
    level
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
)
ORDER BY level, relid;
```

In our lab tree:

| level | Relation Type | Count |
| ---: | --- | ---: |
| 0 | Root table | 1 |
| 1 | Monthly partitions, further partitioned | 2 |
| 2 | Leaf partitions storing rows | 6 |

Count leaf partitions:

```sql
SELECT
    COUNT(*) FILTER (WHERE isleaf) AS leaf_partitions,
    COUNT(*) FILTER (WHERE NOT isleaf) AS partitioned_nodes,
    MAX(level) AS max_level
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
);
```

Expected: `leaf_partitions=6`, `partitioned_nodes=3`, `max_level=2`.

### 4.8. Create Indexes Through the Parent

```sql
CREATE INDEX idx_events_tenant_time
ON partition_levels_lab.events (tenant_id, event_at);

CREATE INDEX idx_events_event_type_time
ON partition_levels_lab.events (event_type, event_at);
```

Creating an index on a partitioned parent manages a logical **partitioned index** plus matching indexes across partitions. Physical index entries live on leaf partitions; never imagine the parent holding a single B-tree spanning all rows in the tree.

Every parent index multiplies physical indexes by the leaf count. Alongside the primary key, our lab already has numerous leaf indexes—a measurable cost in production.

---

## 5. Two-Level INSERT Routing

When a client inserts into the parent, PostgreSQL chooses the branch using all partition keys.

```sql
INSERT INTO partition_levels_lab.events (
    event_at, region, event_id, tenant_id,
    event_type, amount
)
VALUES (
    TIMESTAMPTZ '2026-01-17 10:30:00+00',
    'NORTH',
    9000001,
    42,
    'CLICK',
    0
)
RETURNING
    tableoid::REGCLASS AS stored_in,
    event_at,
    region,
    event_id;
```

Expected output includes:

```text
stored_in = partition_levels_lab.events_2026_01_north
```

### 5.1. What If No Matching Partition Exists?

Try a March row before March exists:

```sql
INSERT INTO partition_levels_lab.events (
    event_at, region, event_id, tenant_id,
    event_type, amount
)
VALUES (
    TIMESTAMPTZ '2026-03-01 00:00:00+00',
    'NORTH',
    9000002,
    42,
    'VIEW',
    0
);
```

Because the parent lacks a March RANGE partition and a RANGE `DEFAULT`, `INSERT` finds no matching partition and **fails**.

Operational takeaway: PostgreSQL never auto-creates scheduled partitions on `INSERT`.

### 5.2. What If Region Has No Dedicated Leaf?

In our lab, `CENTRAL` routes to each month's `_other` partition. Without a `DEFAULT` at the LIST level and without a `CENTRAL` leaf, inserting `CENTRAL` fails even after the RANGE level matched the month.

To route a row successfully, **every level along the path must have a matching partition**.

### 5.3. Should You INSERT Directly into a Leaf Partition?

Applications should normally insert into the parent so PostgreSQL routes by DDL rules. Writing straight to leaves couples apps to monthly/regional table names and breaks easily when adding periods, changing policies, or reshaping the tree.

Target leaves directly only for controlled operational or data-migration tasks when truly warranted.

---

## 6. Multi-Level Partition Pruning

**Partition pruning** is PostgreSQL skipping partitions unable to hold matching rows based on partition keys and bounds.

The point of two levels is not to force PostgreSQL to open all six leaves and filter via `WHERE`, but to recognize entire branches that can be skipped.

### 6.1. Query Filtering Both Month and Region

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) AS events,
    SUM(amount) AS total_amount
FROM partition_levels_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND region = 'NORTH';
```

With effective pruning, the query examines only January/NORTH. Inside that leaf, the planner chooses `Seq Scan` or `Index Scan` based on row count and cost.

**Pruning picks which relations to visit; indexes determine how rows are found inside those relations.** They complement each other.

### 6.2. Filtering by Month Only

```sql
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00';
```

PostgreSQL skips January, yet must still check **all three February region leaves**, because `WHERE` does not restrict `region`.

### 6.3. Filtering by Region Only

```sql
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE region = 'SOUTH';
```

Without an `event_at` predicate, the query cannot skip any month at level 1. It must inspect the **SOUTH leaf of every month**. With 60 months of retention, that means 60 leaf scans rather than one.

### 6.4. Filtering Only by tenant_id

```sql
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE tenant_id = 42;
```

This lab partitions by `event_at` then `region`, **not `tenant_id`**. Filtering on `tenant_id` alone cannot prune any month or region branches. The local `(tenant_id,event_at)` index helps within each leaf, yet many leaves must still be probed.

### 6.5. Scenario Summary Table

| `WHERE` | Branches Pruned Logically | Leaves Remaining |
| --- | --- | --- |
| Jan AND NORTH | Feb; Jan SOUTH/OTHER | One leaf |
| Feb, no region | Jan | Three leaves |
| NORTH, no time | SOUTH/OTHER across months | One leaf per month |
| `tenant_id=42` | No matching partition keys | Potentially all leaves |
| No filter | None | Entire tree |
| `event_at` across both months, `region IN (NORTH,SOUTH)` | OTHER leaves | Four leaves |

This reflects logical bound elimination; real plans may also apply runtime pruning or version-specific optimizations.

---

## 7. Plan-Time vs. Execution-Time Pruning

Modern PostgreSQL can eliminate partitions at different stages.

### 7.1. Plan-Time Pruning

When predicates supply constants known during planning:

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND region = 'NORTH'
```

the planner can strip out irrelevant partitions right inside the plan.

`EXPLAIN` will show scans only on the surviving leaf.

### 7.2. Execution-Time Pruning

With prepared statements and bound parameters:

```sql
PREPARE count_events (
    TIMESTAMPTZ, TIMESTAMPTZ, TEXT
) AS
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE event_at >= $1
  AND event_at <  $2
  AND region = $3;
```

Run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE count_events(
    TIMESTAMPTZ '2026-01-01 00:00:00+00',
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    'NORTH'
);

DEALLOCATE count_events;
```

Depending on whether PostgreSQL picks a custom or generic plan and version, pruning occurs at plan creation or once the executor receives parameter values. Typical indicators:

- Pruned partitions omitted entirely from the plan.
- `Subplans Removed` in certain plan shapes.
- Subplans listed yet unexecuted (`never executed` or `loops=0`).
- Actual number of partitions scanned.

### 7.3. Do Not Assume Generic Plans Cannot Prune

A generic plan does not know concrete parameter values during planning, yet execution-time pruning eliminates unneeded partitions once parameters are bound.

On the flip side, the planner still did work across the full partition tree when constructing the generic plan. Thus **planning cost** and **actually scanned partitions** are two separate metrics.

### 7.4. Join-Driven Parameter Pruning

In some plans, partition-key predicates depend on values from the outer side of a `Nested Loop`. PostgreSQL can prune inner branches dynamically per iteration rather than scanning the entire tree each time.

Still, not every `JOIN` or filter enables execution-time pruning. Always verify the actual plan rather than guessing.

---

## 8. Expression Predicates Make Pruning Harder

For reliable pruning on `RANGE(event_at)`, express time ranges directly on the partition key column.

### 8.1. Pruning-Friendly Pattern

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
```

### 8.2. Patterns Likely to Lose Pruning/Index Usage

```sql
WHERE (event_at AT TIME ZONE 'UTC')::DATE
      = DATE '2026-01-15'
```

or:

```sql
WHERE DATE_TRUNC(
    'month', event_at AT TIME ZONE 'UTC'
) = TIMESTAMP '2026-01-01 00:00:00'
```

These wrap the column in expressions, and the planner cannot necessarily invert them into raw `event_at` RANGE bounds.

If the goal is Jan 15 UTC:

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-15 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-01-16 00:00:00+00'
```

is clearer and works cleanly with timestamp B-tree indexes.

### 8.3. Business Timezones

"Midnight in Vietnam" differs from UTC midnight. For Jan 15 in `Asia/Ho_Chi_Minh`, write:

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-15 00:00:00+07'
  AND event_at <  TIMESTAMPTZ '2026-01-16 00:00:00+07'
```

In DST-observing timezones, compute **both local day boundaries in the business timezone** rather than blindly adding 24 hours.

Pre-computing boundary instants and comparing against the raw partition key still gives PostgreSQL clean time pruning.

---

## 9. Reverse Hierarchy: HASH/LIST Tenant First, Time RANGE Second

RANGE does not always have to sit at the root. A system can use:

```text
HASH(tenant_id)                      -- level 1
   |
   +-- bucket 0
   |      +-- RANGE(event_at)        -- level 2
   |           +-- Jan
   |           +-- Feb
   |
   +-- bucket 1
          +-- RANGE(event_at)
               +-- Jan
               +-- Feb
```

Separate DDL example:

```sql
CREATE TABLE tenant_events (
    tenant_id BIGINT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    event_id BIGINT NOT NULL,
    payload JSONB NOT NULL
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_events_h0
PARTITION OF tenant_events
FOR VALUES WITH (MODULUS 2, REMAINDER 0)
PARTITION BY RANGE (event_at);

CREATE TABLE tenant_events_h1
PARTITION OF tenant_events
FOR VALUES WITH (MODULUS 2, REMAINDER 1)
PARTITION BY RANGE (event_at);

CREATE TABLE tenant_events_h0_2026_01
PARTITION OF tenant_events_h0
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO   ('2026-02-01 00:00:00+00');

CREATE TABLE tenant_events_h1_2026_01
PARTITION OF tenant_events_h1
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO   ('2026-02-01 00:00:00+00');
```

This illustrates the layout and is not required for the main lab. To insert across multiple months, create matching `RANGE` leaves under every hash bucket.

### 9.1. How Does Level Ordering Matter?

For workloads predominantly filtering both:

```sql
WHERE event_at >= ...
  AND event_at < ...
  AND tenant_id = ...
```

either order can prune down to a small leaf subset.

However, if queries frequently **filter by date only**:

- Time `RANGE` first: prunes whole months cleanly, then inspects subpartitions under the chosen month(s).
- Tenant `HASH` first: must probe every hash bucket to find the date range inside each bucket.

If queries frequently **filter by tenant only**:

- Tenant `HASH` first: prunes straight to one bucket, then inspects monthly leaves within that bucket.
- Time `RANGE` first: must visit every month and locate the tenant bucket under each month.

### 9.2. Choose Based on Workload

Measure:

- Share of queries with a time range.
- Share of queries with `tenant_id`.
- Cross-tenant queries over a single week.
- Single-tenant queries spanning multiple years.
- Monthly retention requirements.
- Desired isolation for `VACUUM`/index rebuilds.
- Cost of creating/dropping monthly partitions.

When monthly retention is a key driver, **putting time `RANGE` at the outer level** offers huge lifecycle convenience: detaching/dropping one monthly node removes the entire period's subtree. The reverse ordering forces operations across every hash bucket when a month expires.

---

## 10. Partition Count Grows as the Product Across Levels

With two uniform levels:

\[
N_{\text{leaf}} = N_{\text{level1}} \times N_{\text{level2}}
\]

With three levels:

\[
N_{\text{leaf}} = N_1 \times N_2 \times N_3
\]

If nodes have uneven child counts, sum the leaf counts across all branches rather than multiplying uniformly.

### 10.1. Scaling Table

| Level 1 | Level 2 | Leaf Count | With 3 Indexes/Leaf |
| --- | --- | ---: | ---: |
| 6 months | 3 regions | 18 | 54 leaf indexes |
| 12 months | 8 hash buckets | 96 | 288 |
| 24 months | 16 hash buckets | 384 | 1,152 |
| 36 months | 32 hash buckets | 1,152 | 3,456 |
| 60 months | 32 hash buckets | 1,920 | 5,760 |
| 36 months | 2,000 LIST tenants | 72,000 | 216,000 |

These figures illustrate object counts only—**not benchmarks or hard PostgreSQL thresholds**. PostgreSQL can handle large partition counts when properly tuned, yet actual cost depends on version, queries, RAM, hardware, index count, and DDL frequency.

### 10.2. Adding a Third Level Can Cause an Explosion

Suppose:

```text
36 months
x 16 tenant hash buckets
x 4 event types
= 2,304 leaf partitions
```

If event type is added solely to separate `VIEW`/`CLICK`/`PURCHASE`, do queries actually filter `event_type` often enough to justify 4x as many leaves?

If not, an index on `event_type` or a partial index creates far fewer objects.

### 10.3. There Is No Magic Rule "Under X Partitions Is Always Fine"

A tree with a few thousand leaves where pruning works well and queries hit one month behaves totally differently from a few hundred leaves where every query scans the whole tree.

Evaluate:

- Total leaves **in the tree**.
- Leaves **surviving pruning** per key query.
- Indexes per leaf.
- Concurrent transactions and statements.
- DDL, vacuum, and analyze frequency.
- Memory, catalog, and lock overhead.
- Planning time versus data-reading execution time.

---

## 11. Cost 1: Query Planning Time

The planner inspects predicates, partition bounds, statistics, and candidate paths. With many partitions, plan construction can burn substantial CPU and memory even when most partitions get pruned.

### 11.1. Planning Time vs. Execution Time

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    COUNT(*),
    SUM(amount)
FROM partition_levels_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND region = 'NORTH';
```

Compare both lines:

```text
Planning Time: ...
Execution Time: ...
```

For highly selective queries with short `Execution Time`, `Planning Time` can dominate total latency if the partition tree is oversized or the query is complex.

### 11.2. Even a One-Leaf Scan Pays Metadata Cost

Effective pruning shrinks executor work, yet does not eliminate planner and cache overhead for managing a massive tree. Never judge solely by heap pages read; always measure planning time too.

### 11.3. High-QPS Short Queries

An API executing thousands of tiny queries per second reading only a few rows can suffer heavy repeated planning and metadata overhead. Prepared statements and plan caching help, yet cannot erase all partition-count cost; generic vs. custom plans introduce their own pruning trade-offs.

### 11.4. Do Not Partition by the Minute Without Measuring

Retaining 30 days at one-minute granularity yields:

```text
30 days × 24 hours × 60 minutes = 43,200 partitions
```

Just the time level is already huge. Subpartitioning into 8 buckets gives:

```text
43,200 × 8 = 345,600 leaves
```

Compare that against daily or monthly partitions with a timestamp index: most queries do not need a new physical table every minute just to filter a few seconds of data.

---

## 12. Cost 2: Metadata, System Catalogs, and Relcache

Every partition is a relation whose metadata PostgreSQL must track across catalogs such as:

- `pg_class`: relations.
- `pg_inherits`: parent–child inheritance/partition links.
- `pg_partitioned_table`: partitioned relation metadata.
- `pg_index` and index catalogs.
- `pg_attribute`, `pg_constraint`, and schema objects.

### 12.1. More Objects, Not Just Smaller Data Chunks

Each leaf carries:

- Heap relation.
- Index relations.
- Statistics entries.
- TOAST relation/index when needed.
- Relcache/catcache entries per backend.
- Locks when referenced by statements or DDL.
- Storage files and forks on disk.

Do not assume 1,000 partitions equals 1,000 filesystem files; each relation, fork, and index creates its own storage files and segments.

### 12.2. Cache Pressure

PostgreSQL backends allocate memory for relation descriptors, metadata, and cached plans. As partition counts grow, relcache/catcache pressure and metadata work can climb noticeably in sessions touching the tree.

This cost is not strictly linear across all queries; it varies with access patterns, pruning, version, and cache state.

### 12.3. Continuous Catalog DDL

Frequent partition creation, attachment, detachment, or drops churn system catalogs. If thousands of tenants create child tables daily, DDL activity itself becomes a major performance factor.

Separate "data `SELECT` cost" from "schema management cost" when evaluating system-wide impact.

---

## 13. Cost 3: Indexes Multiply by Leaf Count

Suppose a tree has 1,152 leaves and the parent defines three logical indexes. PostgreSQL maintains corresponding physical indexes on every leaf:

```text
1,152 leaves
x 3 indexes/leaf
= 3,456 leaf index relations
```

Every one of those indexes:

- Consumes disk space and metadata.
- Must be updated on `INSERT`/`UPDATE`/`DELETE` in its leaf.
- Needs `VACUUM` / index cleanup.
- Needs statistics and occasional `REINDEX`/maintenance.
- Adds objects to attach/detach and backup/restore.

### 13.1. A Parent Index Is Not a Global Physical Index

```sql
CREATE INDEX idx_events_tenant_time
ON partition_levels_lab.events(tenant_id, event_at);
```

This declares an index across the partitioned tree; leaf indexes perform actual lookups per partition.

Never imagine PostgreSQL maintains one global B-tree holding every `tenant_id` across all months to locate a tenant in O(log N) while skipping partitions without `event_at`/`region`.

### 13.2. Querying a Non-Partition-Key Column

For example:

```sql
WHERE event_id = 12345
```

if the only primary key is `(event_at,region,event_id)`, the query lacks time and region to prune, and the key order isn't led by `event_id`.

Adding a local index on `event_id` speeds up each leaf probe, yet the query still has to visit many partitions unless it can resolve the partition keys from the ID.

If querying by `event_id` **without knowing the date** is frequent, consider an `id → partition keys` lookup table, changing the partition key, or organizing data around that access pattern.

### 13.3. Global Uniqueness Does Not Appear Automatically

Even if every leaf has `UNIQUE(event_id)`, duplicate `event_id`s can still live across two different leaves because local indexes never check across leaf boundaries.

This is a correctness risk, not just performance. Tree-wide uniqueness in PostgreSQL declarative partitioning requires including partition keys across all levels.

### 13.4. Can Individual Leaves Have Different Indexes?

Advanced setups sometimes customize indexes on hot vs. cold leaves, yet divergence makes query plans unpredictable and maintenance error-prone. If primary queries follow the same pattern across months, keep index policies consistent unless measurements justify diverging.

---

## 14. Cost 4: Locks and Relations Touched per Transaction

Queries and DDL acquire relation locks on touched objects. On huge trees—especially during DDL, maintenance, or multi-leaf queries—lock counts per transaction climb.

### 14.1. max_locks_per_transaction Is Not a Hard Partition Cap

`max_locks_per_transaction` sizes the shared lock table; it **does not strictly cap a single transaction to N relations** or set a hard "maximum partition count."

However, workloads locking huge numbers of relations concurrently can exhaust shared lock memory. Balance connection/transaction counts, lock modes, DDL concurrency, index counts, and server sizing.

### 14.2. Inspecting Relation Locks

Lab diagnostic query:

```sql
SELECT
    l.pid,
    l.mode,
    l.granted,
    l.relation::REGCLASS AS relation_name
FROM pg_locks AS l
WHERE l.locktype = 'relation'
  AND l.relation IN (
      SELECT relid
      FROM pg_partition_tree(
          'partition_levels_lab.events'::REGCLASS
      )
  )
ORDER BY l.pid, l.relation, l.mode;
```

Output reflects active sessions at that instant, not a fixed constant per query.

### 14.3. Manage DDL Locking Carefully

Creating partitions directly with `CREATE TABLE ... PARTITION OF` can take strong locks on the parent. `ATTACH PARTITION` on a pre-created table uses a different lock profile that often lessens parent disruption, yet still requires locks, validation, and index/constraint handling.

Never run bulk tree changes during peak traffic without testing lock behavior on your exact PostgreSQL version.

---

## 15. Cost 5: Autovacuum, ANALYZE, and Per-Partition Statistics

Each leaf partition stores real rows and needs its own maintenance and statistics.

### 15.1. Leaves Are Maintained Individually

A leaf receiving heavy `UPDATE`/`DELETE` traffic generates dead tuples and needs `VACUUM`. A read-only historical leaf needs less dead-tuple cleanup, yet still needs transaction ID freeze tracking.

Partitioning scopes maintenance locally, though with thousands of leaves the number of relations to track grows rapidly.

### 15.2. Autovacuum Thresholds on Small Partitions

With too many tiny leaves, some may rarely hit autovacuum scale thresholds while hot leaves need frequent vacuuming. Evaluate:

- Write rate per partition.
- Estimated `n_dead_tup`.
- `last_autovacuum` and `last_autoanalyze`.
- Scale factors and base thresholds.
- XID age and freeze policies.
- Autovacuum worker count and cost limits.

Never apply one blind autovacuum setting assuming every leaf sees identical write traffic.

### 15.3. Parent vs. Child ANALYZE Statistics

Depending on version, plan shape, and statistics collection, the planner may need both leaf stats and parent/inherited stats. Notably, autovacuum does not always analyze a rowless partitioned parent automatically the way it analyzes regular tables.

Under heavy data shifts, schedule `ANALYZE` explicitly when needed:

```sql
ANALYZE partition_levels_lab.events;
```

This updates hierarchy statistics used by the planner; never look at `n_live_tup=0` on the parent and conclude the parent needs no statistics.

### 15.4. Inspecting Per-Leaf Statistics

```sql
SELECT
    s.schemaname,
    s.relname,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_vacuum,
    s.last_autovacuum,
    s.last_analyze,
    s.last_autoanalyze
FROM pg_stat_user_tables AS s
WHERE s.schemaname = 'partition_levels_lab'
ORDER BY s.relname;
```

Counters are delayed estimates, not exact live tuple counts. The partitioned parent row differs from leaves because it stores no direct rows.

### 15.5. Many Leaves Are Not Automatically Faster to VACUUM Than One Big Table

Splitting makes individual `VACUUM` runs smaller, yet total overhead for scheduling, starting workers, and scanning thousands of relations and indexes can rise. Compare whole-workload maintenance cost rather than a single leaf's `VACUUM` duration.

---

## 16. Cost 6: Backup, Restore, Replication, and Monitoring

Multi-level partitioning affects the entire system lifecycle, not just SQL execution.

### 16.1. Backup and Restore

With thousands of leaves and indexes:

- Far more schema/catalog objects must be restored.
- Index creation/rebuilding overhead can rise.
- Restores must preserve parent–child trees and constraints accurately.
- Thousands of tiny objects behave differently operationally from a few large ones.

Identical logical data volume does not mean identical backup/restore duration. Never claim a repartitioned layout restores at the exact same speed just because total rows match.

### 16.2. Physical Replication

Physical standbys replay WAL for all relation changes and DDL. Frequent partition/index creation increases WAL and metadata activity proportionally to workload.

### 16.3. Logical Replication

Logical replication has specific rules for publications, partitioned tables, row routing, and replica identity depending on version and configuration. With multi-level trees, verify how publications and subscribers handle row routing, table names, default partitions, replica keys, and DDL synchronization.

Never assume a publication automatically creates new partitions on subscribers in all setups. Primary DDL typically requires matching schema management on subscribers.

### 16.4. Monitoring Cardinality

With 2,000 leaves, monitoring dashboards may need rollups by tree or month instead of rendering thousands of raw rows—while still alerting on individual skewed or hot leaves.

---

## 17. Cost 7: Operational Complexity of DDL

Adding a new month in a two-level tree is no longer a single `CREATE TABLE` if each month contains many subpartitions.

### 17.1. Pre-Creating March Partitions

```sql
CREATE TABLE partition_levels_lab.events_2026_03
PARTITION OF partition_levels_lab.events
FOR VALUES FROM ('2026-03-01 00:00:00+00')
             TO   ('2026-04-01 00:00:00+00')
PARTITION BY LIST (region);

CREATE TABLE partition_levels_lab.events_2026_03_north
PARTITION OF partition_levels_lab.events_2026_03
FOR VALUES IN ('NORTH');

CREATE TABLE partition_levels_lab.events_2026_03_south
PARTITION OF partition_levels_lab.events_2026_03
FOR VALUES IN ('SOUTH');

CREATE TABLE partition_levels_lab.events_2026_03_other
PARTITION OF partition_levels_lab.events_2026_03
DEFAULT;
```

Inherited indexes and constraints must also be verified. With 32 hash leaves per month, the monthly provisioning job must create and validate all 32 leaves.

### 17.2. Never Create Partitions On-Demand During the First INSERT

Running DDL inline on the hot write path when a partition is missing causes:

- Concurrent requests racing to create the same partition.
- DDL lock waits spiking request latency.
- Duplicate `CREATE` collision errors.
- Requiring DDL privileges in runtime API credentials.
- Index/catalog overhead and race conditions on month rollover.

Instead, **pre-create ahead of time** via a controlled background job that tracks progress, alerts on failures, and verifies all leaves exist before data arrives.

### 17.3. Partition-Creation Automation Must Be Idempotent

A monthly creation job should:

1. Determine exact target periods and timezone.
2. Compute exact `FROM`/`TO` bounds.
3. Verify existing partitions and bound correctness.
4. Create missing intermediate nodes and leaves.
5. Verify indexes, constraints, and policies.
6. Log completion and alert if any leaf is missing.
7. Never auto-create unbounded partitions from bad input dates.

Using `IF NOT EXISTS` avoids name-collision errors, yet **never proves an existing object has the right structure or bounds**. Validate catalog metadata directly.

---

## 18. ATTACH PARTITION with Pre-Built Tables

An operational pattern is **creating and preparing tables offline**, then attaching them into the tree when ready—letting you load data and build indexes separately before exposing them under the parent.

Conceptual example at the monthly level:

```sql
-- Structural illustration only; the prepared table must match
-- required schema, constraints, bounds, and indexes.

ALTER TABLE partition_levels_lab.events
ATTACH PARTITION partition_levels_lab.prepared_month
FOR VALUES FROM ('2026-04-01 00:00:00+00')
             TO   ('2026-05-01 00:00:00+00');
```

In our actual two-level tree, `prepared_month` would first be created as a `LIST(region)` partitioned table with matching leaves satisfying parent constraints. The snippet above **cannot run directly in the lab** because `prepared_month` does not exist; it illustrates the attachment step after preparation.

### 18.1. ATTACH May Scan Data for Validation

If the prepared table already holds rows, PostgreSQL must verify every row satisfies partition bounds and constraints. Without a validated constraint proving compliance, `ATTACH` **scans the data** to verify it.

Across many leaves, validation and locks can be substantial. Benchmark on staging at realistic scale.

### 18.2. A DEFAULT Partition Complicates Attaching

If the parent has a `DEFAULT` partition holding rows matching the new month, attaching that month requires checking/validating and moving or resolving those rows first; PostgreSQL will not silently move rows out of `DEFAULT` into the attached partition.

That is why many time-series systems prefer **pre-creating `RANGE` partitions** and handling out-of-range inputs via explicit application/quarantine workflows.

### 18.3. Lock Behavior Varies by Command

`CREATE TABLE ... PARTITION OF` and `ATTACH PARTITION` acquire different locks. Some steps take strong locks on parent or child, and existing `DEFAULT` partitions or populated tables trigger extra scans/locks.

Never treat a tip like "ATTACH never blocks writes" as an absolute guarantee; verify against your PostgreSQL version, tree layout, and concurrency.

---

## 19. DETACH and Retention: The Advantage of Outer RANGE

Suppose a system retains 24 months of data. Purging an expired month row by row:

```sql
DELETE FROM partition_levels_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00';
```

creates massive dead tuples, WAL, and vacuum work when one month holds billions of rows.

When time is the outer root partition key, you can **detach the entire monthly branch**:

```sql
-- Retention illustration only; DO NOT run if data is still needed.
ALTER TABLE partition_levels_lab.events
DETACH PARTITION partition_levels_lab.events_2026_01;
```

Once detached, January is no longer part of the parent, while its subtables and data stay intact per DDL rules for controlled archival or deletion.

### 19.1. Why Is Detaching a Subtree Helpful?

If each month holds 32 hash leaves, detaching that month's intermediate partition handles **the whole 32-leaf subtree** as a single lifecycle unit instead of detaching 32 individual leaves.

### 19.2. Never Run DROP CASCADE Recklessly

Before deleting detached tables permanently, check:

- Retention policy and legal holds.
- Backups / PITR coverage.
- Foreign keys or referencing objects.
- Subscribers and replication.
- Export/archival requirements.
- Audit and historical reporting impact.

Production `DROP`s permanently destroy data within your recovery limits. Never treat detach/drop as harmless cleanup.

### 19.3. DETACH CONCURRENTLY

PostgreSQL provides `DETACH PARTITION CONCURRENTLY` in supported versions, subject to specific limits (e.g., no explicit transaction block, `DEFAULT` partition restrictions, and tree constraints). Do not assume it is always usable or always faster.

For any retention job, verify locking behavior and recovery steps if interrupted.

---

## 20. DEFAULT Partition: Lifesaver for INSERTs or Mask for Missing Partitions?

You can add a `DEFAULT` partition at the `RANGE` level to catch rows outside declared ranges.

Conceptual example:

```sql
CREATE TABLE some_events_default
PARTITION OF some_events DEFAULT;
```

Pros:

- Prevents immediate `INSERT` failures when timestamps fall outside existing partitions.
- Useful as a controlled quarantine zone for late or future data in well-designed pipelines.

Cons:

- Data silently accumulates when partition-creation jobs break.
- Time-series data lands outside expected monthly branches.
- Creating official partitions later requires migrating/validating rows out of `DEFAULT`.
- Queries without tight filters or unable to prune `DEFAULT` pay extra scan cost.
- If a `DEFAULT` partition is itself subpartitioned, routing and maintenance grow complex.

### 20.1. DEFAULT Never Auto-Migrates Data

Adding a new partition never obligates PostgreSQL to automatically reclassify and move existing `DEFAULT` rows into new leaves like an ETL pipeline. You must build a transactional, constraint-safe migration avoiding duplicate or dropped rows.

### 20.2. DEFAULT Per Level

In our lab:

- The root `RANGE` parent has no `DEFAULT`.
- Each month's `LIST(region)` has a `DEFAULT`.

Hence a March row fails even with `region='NORTH'`, whereas a January `region='CENTRAL'` row lands in `_other`.

Always identify **which level** caused a routing error rather than calling everything a generic "missing partition."

---

## 21. Updating Partition Keys Can Move Rows

If an `UPDATE` changes `event_at` from January to February, PostgreSQL relocates the row **from the old leaf to the new leaf** via partition routing.

Lab example:

```sql
BEGIN;

UPDATE partition_levels_lab.events
SET event_at = TIMESTAMPTZ '2026-02-15 12:00:00+00'
WHERE event_id = 9000001
  AND event_at = TIMESTAMPTZ '2026-01-17 10:30:00+00'
  AND region = 'NORTH'
RETURNING tableoid::REGCLASS AS new_leaf, event_at, region;

ROLLBACK;
```

Internally, moving a row across partitions behaves like removing it from the old partition and inserting into the new one, impacting triggers, foreign keys, indexes, WAL, and concurrency.

### 21.1. Updating region Can Also Move Leaves

In `RANGE → LIST`, changing `region='NORTH'` to `'SOUTH'` within the same month also relocates the row to a different leaf.

### 21.2. Avoid Frequently Mutating Partition Keys

Columns like `event_at`, `tenant_id`, and `region` should be stable if chosen as partition keys. Workloads constantly updating partition keys incur far higher routing/movement cost than updating non-key columns.

### 21.3. Concurrency and Row Movement

Concurrent `UPDATE`/`DELETE`s hitting a row being relocated across partitions can trigger serialization/concurrent-modification errors under PostgreSQL rules. Applications need clean transaction boundaries and retry logic—never assume cross-partition movement acts like an in-place update.

---

## 22. PRIMARY KEY, UNIQUE, and Multi-Level Constraints

A core restriction of declarative partitioning is that **tree-wide** uniqueness relies on disjoint partition bounds paired with local indexes.

### 22.1. Why Must Keys Include Partition Keys?

Our lab uses:

```sql
PRIMARY KEY (event_at, region, event_id)
```

In `RANGE(event_at) → LIST(region)`, both partition keys appear in `PRIMARY KEY`, guaranteeing no identical key combination can validly exist in two different leaves.

### 22.2. Keys Containing Only event_id Fail

Writing:

```sql
PRIMARY KEY (event_id)
```

on a tree partitioned by `event_at` and `region` cannot be enforced via local indexes alone when `event_at` and `region` are excluded from the key.

It isn't that `event_id` lacks business uniqueness—it is that physical partitions lack a general global uniqueness index spanning leaves.

### 22.3. Expression Partition Keys

Using expressions instead of plain columns as partition keys restricts declaring `UNIQUE`/`PRIMARY KEY` on the partitioned table. If tree-wide uniqueness is required, store explicit normalized columns as partition keys and check version rules instead of expecting complex expressions to work with parent `UNIQUE` constraints.

### 22.4. Foreign Keys

Modern PostgreSQL supports many foreign-key patterns with partitioned tables, provided you verify:

- Is the referenced key actually a valid unique/primary key?
- Which partition keys are included?
- How do `DETACH`/`DROP` operations affect references?
- What is the DML/constraint maintenance overhead?
- Does your PostgreSQL version support the exact scenario?

A single-column `event_id` reference cannot target a three-column PK without a separate uniqueness mechanism.

---

## 23. Partition-Wise Join: Benefits and Risks

When two large tables are partitioned compatibly on the same keys and bounds, PostgreSQL can perform a **partition-wise join** instead of joining two massive combined datasets.

Conceptual flow:

```text
Table A January  JOIN  Table B January
Table A February JOIN  Table B February
...
Append results
```

### 23.1. Requires Compatible Partitioning

If A is partitioned by `event_at` and B by `tenant_id`, a join cannot pair matching months directly. Key/bound alignment and join predicates determine eligibility.

### 23.2. Two Levels Complicate This Further

With monthly `RANGE` + tenant `HASH`:

- Both tables must match layouts identically to join leaf pairs.
- Plans can expand to hundreds or thousands of join nodes.
- The planner must evaluate many paths and memory budgets.

### 23.3. Configuration

PostgreSQL provides planner flags such as `enable_partitionwise_join`. Enabling it depends on system and version—never assume turning it on automatically speeds things up.

Partition-wise joins inflate plan node counts and planning/execution memory. On oversized trees, planning overhead can easily erase any I/O savings.

---

## 24. Partition-Wise Aggregate: Aggregating Per Branch

Report:

```sql
SELECT
    region,
    COUNT(*) AS events,
    SUM(amount) AS amount
FROM partition_levels_lab.events
GROUP BY region;
```

PostgreSQL supports partition-wise aggregation under eligible conditions, aggregating per partition and combining results when required.

### 24.1. Full vs. Partial Aggregation

- **Full partition-wise aggregate** applies when `GROUP BY` keys guarantee groups cannot span multiple partitions.
- **Partial aggregation** computes intermediate states per partition and finalizes above when groups span partitions.

Exact eligibility depends on aggregate functions, partition keys, query shape, and planner/version.

### 24.2. Example: Regions Spanning Multiple Months

In monthly `RANGE → region LIST`, every region spans multiple months. Computing all-time totals per region requires summing partial regional totals across months—you cannot inspect one `NORTH` leaf and treat it as all-time `NORTH`.

### 24.3. Watch Out for COUNT(DISTINCT)

Not every aggregate decomposes by simply adding child results. Suppose a customer appears in both January and February:

```text
COUNT(DISTINCT customer_id) in January  = 1
COUNT(DISTINCT customer_id) in February = 1

COUNT(DISTINCT customer_id) across both months = 1,
not 2.
```

Partial aggregates must obey each function's exact semantics; never roll up distinct counts with `SUM`.

### 24.4. Do Large Partition Counts Increase Aggregate Memory?

Partition-wise aggregation can spin up many partial aggregate nodes and hash tables, increasing memory demand with partition and group counts. Never enable it globally without measuring planning time, `work_mem`/disk spills, and concurrency.

---

## 25. Queries Without Pruning: The Downside of Over-Splitting

A common query:

```sql
SELECT
    event_type,
    COUNT(*) AS events,
    SUM(amount) AS amount
FROM partition_levels_lab.events
GROUP BY event_type;
```

Neither `event_at` nor `region` appears in `WHERE`. PostgreSQL must read **every populated leaf**, unless a separate summary structure exists.

### 25.1. Full-Tree Scans Are Not Automatically Faster Than One Table

On a single large table, the executor runs one `Seq Scan`/`Parallel Seq Scan`; across many partitions, it builds `Append`/`Parallel Append` over many relations and indexes.

When leaves are tiny, per-partition and multi-node overhead becomes substantial.

### 25.2. Querying by event_id

```sql
WHERE event_id = 12345
```

omits all partition keys. Without an external lookup, PostgreSQL probes many leaves. Finer time splits hurt un-keyed ID lookups if those queries run often.

### 25.3. When Do Indexes Beat More Partition Levels?

If queries mostly run:

```sql
WHERE tenant_id = 42
  AND event_type = 'PURCHASE'
```

across all history, a composite index or summary table beats adding thousands of tenant list partitions.

Weigh selectivity, query frequency, write cost, and pruning potential of existing keys.

---

## 26. Measuring Total Relations and Real Footprint

Useful PostgreSQL catalog functions for inspecting trees:

### 26.1. Leaf Partition Count

```sql
SELECT
    COUNT(*) FILTER (WHERE isleaf) AS leaves,
    COUNT(*) FILTER (WHERE NOT isleaf) AS internal_nodes
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
);
```

### 26.2. Total Leaf Footprint

```sql
SELECT
    PG_SIZE_PRETTY(
        SUM(PG_TOTAL_RELATION_SIZE(relid))::BIGINT
    ) AS all_leaf_size,
    COUNT(*) AS leaf_count
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
)
WHERE isleaf;
```

Because the parent is a partitioned table, it holds no leaf heap rows. Never run `pg_relation_size(parent)` and mistake it for the tree's total size.

### 26.3. Size per Leaf

```sql
SELECT
    relid::REGCLASS AS leaf_name,
    PG_SIZE_PRETTY(PG_TABLE_SIZE(relid)) AS table_size,
    PG_SIZE_PRETTY(PG_INDEXES_SIZE(relid)) AS indexes_size,
    PG_SIZE_PRETTY(PG_TOTAL_RELATION_SIZE(relid))
        AS total_size
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
)
WHERE isleaf
ORDER BY PG_TOTAL_RELATION_SIZE(relid) DESC;
```

### 26.4. Spotting Skewed Distributions

Certain leaves often grow much larger due to:

- A region generating massive traffic.
- A "hot" tenant landing in a shared hash bucket.
- Peak promotional months.
- Backfills or late events piling into `DEFAULT`.
- Unusual bloat or index growth on one leaf.

Counting partitions isn't enough; measure **size and write rate per leaf**.

---

## 27. Auditing Catalogs and Tree Indexes

### 27.1. Inspect Indexes per Leaf

```sql
SELECT
    t.relid::REGCLASS AS leaf_table,
    i.indexrelid::REGCLASS AS index_name
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
) AS t
JOIN pg_index AS i
  ON i.indrelid = t.relid
WHERE t.isleaf
ORDER BY t.relid, i.indexrelid;
```

On trees with many leaves, this quickly reveals how huge total index counts grow.

### 27.2. Count Indexes per Leaf

```sql
SELECT
    t.relid::REGCLASS AS leaf_table,
    COUNT(i.indexrelid) AS index_count
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
) AS t
LEFT JOIN pg_index AS i
  ON i.indrelid = t.relid
WHERE t.isleaf
GROUP BY t.relid
ORDER BY index_count DESC, t.relid;
```

Not every system needs identical indexes on every leaf, yet mismatches can flag a new period missing an index or an old period keeping obsolete indexes.

### 27.3. Monitor Catalog Activity Too

Spikes in DDL, lock waits, or object counts warn of runaway partition creation. Track partition creation health alongside query latency.

---

## 28. Comparing Single-Level vs. Two-Level Experimentally

A valid benchmark compares both layouts under identical data and semantics.

### 28.1. Hypotheses

Design A:

```text
Monthly RANGE
  -> 24 leaf partitions
```

Design B:

```text
Monthly RANGE
  -> 16 tenant HASH buckets per month
  -> 384 leaves
```

Hypotheses:

- One month + one tenant: B reads a smaller leaf, at the cost of more total relations.
- One month, all tenants: A is simpler with one monthly leaf; B reads all 16 leaves for that month.
- One tenant, all months: B reads one bucket per month; A uses tenant indexes per month or scans.
- Full history: B pays higher multi-relation overhead.
- Monthly retention: both can detach a monthly branch when `RANGE` is outer, though B manages more leaves underneath.
- DDL and index count: B creates far more objects.

### 28.2. Keep Comparisons Fair

- Identical row counts and distributions.
- Identical payloads and row widths.
- Equivalent index counts and coverage.
- Identical PostgreSQL version and hardware.
- Identical `work_mem`, parallelism, and fresh statistics.
- Identical write rates and concurrency.
- Warm-up runs and multiple iterations.
- Never benchmark only one query favoring one design.

### 28.3. What to Measure?

| Metric | Why It Matters |
| --- | --- |
| Planning Time | Does the larger tree add planning overhead? |
| Execution Time | Do queries actually run faster? |
| Shared buffers hit/read | Did page accesses actually drop? |
| Temp blocks/disk | Did sorts or hashes spill? |
| Partitions scanned | How effective is pruning? |
| Rows removed by filter | Was input volume reduced meaningfully? |
| Index footprint | Storage cost of leaf indexes |
| Insert throughput | Routing and index write overhead |
| Update/delete throughput | Maintenance and row movement cost |
| Vacuum/analyze cost | Overhead across many leaves |
| DDL time/locks | Impact of provisioning new periods |
| Memory/CPU | Planning and concurrent execution footprint |
| Backup/restore duration | End-of-lifecycle operational impact |

### 28.4. Local Gains Do Not Guarantee Global Wins

If tenant/month queries speed up 10% while 70% of the workload runs all-time rollups and relation counts multiply by 16x, Design B is likely a net loss.

Never evaluate one isolated query instead of the real workload mix.

---

## 29. Prepared Statements and the Plan Cache

JDBC/ORM applications routinely send parameterized SQL:

```sql
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE event_at >= $1
  AND event_at < $2
  AND region = $3;
```

PostgreSQL chooses between custom plans and generic plans depending on context.

### 29.1. Custom Plans

Custom plans see concrete parameter values during planning, leveraging selectivity and exact bounds at the expense of planning on every execution.

### 29.2. Generic Plans

Generic plans save repeated planning cost, yet aren't always ideal when parameters have heavy skew. Execution-time pruning helps, without erasing upfront planning cost or access-path compromises.

### 29.3. Never Force plan_cache_mode Blindly

PostgreSQL exposes `plan_cache_mode` in supported versions to test auto/custom/generic modes. No single setting fits every query.

If one tenant has a billion rows while another has a few hundred, custom plans and statistics matter greatly. Measure P95 latency across both tiny and massive tenants.

---

## 30. Data Skew and Hash Buckets

HASH spreads distinct tenants across buckets, without guaranteeing equal row counts or load per bucket.

### 30.1. Hot Tenants

If one tenant produces 70% of all events, it remains concentrated inside its single bucket. Uniformly hashing **key values** does not balance **per-key traffic**.

Adding buckets isolates a hot tenant from other small tenants, yet never splits one hot tenant across multiple buckets while `tenant_id` remains the partition key.

### 30.2. Resizing Hash Partitions Is Not Free

Growing from 16 to 32 buckets on a populated table is not a quick metadata tweak; it entails creating/attaching partitions, redistributing rows, handling bounds, and preserving availability.

Never pick a hash bucket count thinking "we can easily double it later like a config flag" without a full migration plan.

### 30.3. Per-Tenant LIST Is Even More Complex

With one LIST partition per tenant:

- Onboarding a new tenant requires DDL.
- Offboarding leaves per-tenant lifecycle cleanup.
- Cross-tenant queries touch huge relation counts.
- Catalog and index counts scale linearly with tenants.
- Tiny tenants create thousands of nearly empty tables.

Unless strict operational, legal, or isolation rules mandate it, prefer **HASH buckets** or time partitioning + tenant indexes over per-tenant partitions.

---

## 31. Alternatives to Adding Another Partition Level

Before expanding a tree from 24 to 384 leaves, evaluate simpler options with fewer objects.

### 31.1. Local B-Tree Index

If queries filter by tenant within a month:

```sql
CREATE INDEX idx_events_tenant_time
ON partition_levels_lab.events(tenant_id, event_at);
```

Often delivers fast lookups inside monthly partitions without HASH subpartitions.

### 31.2. BRIN for Time-Correlated Append Data

On large append-only relations correlated physically with time, BRIN keeps indexes tiny while bounding scan ranges:

```sql
CREATE INDEX idx_events_time_brin
ON partition_levels_lab.events
USING BRIN (event_at);
```

BRIN does not replace all B-tree or HASH-subpartition use cases and must be benchmarked, yet is well worth testing on append-heavy logs.

### 31.3. Partial Indexes

If only one event type needs low-latency queries:

```sql
CREATE INDEX idx_events_purchase_time
ON partition_levels_lab.events(event_at)
WHERE event_type = 'PURCHASE';
```

A targeted partial index often beats adding LIST subpartitions for every `event_type` when pruning gains are modest.

### 31.4. Summary Tables / Materialized Views

For dashboards displaying monthly/tenant event counts, adding partitions never makes `COUNT(*)` instantaneous. A summary table or materialized view with clear refresh/delta/idempotency contracts fits recurring rollups much better.

### 31.5. Shorter Retention or Archival

If 90% of queries only touch the last six months, keeping years of history inside the active tree may be needless. Archiving older data shrinks active partition counts and eases catalog, planning, and maintenance load.

---

## 32. Sizing Partition Counts from Volume and Queries

There is no universal "ideal partition size." Answer:

1. How many rows/GB arrive per month?
2. What is the monthly `INSERT`/`UPDATE`/`DELETE` rate?
3. Do queries read one day, one month, or many years?
4. How many tenants/regions exist, and how skewed are they?
5. How many indexes does each leaf require?
6. How large a unit can `VACUUM`, `REINDEX`, and backup retention handle comfortably?
7. How many months must remain online?
8. What planning time and lock/memory overhead does your PostgreSQL version/hardware exhibit?

### 32.1. Quantitative Example

Suppose 24 months at 100 GB/month, queried mainly by month.

Option A: 24 monthly leaves (~100 GB each).

Option B: 24 × 8 hash buckets = 192 leaves (~12.5 GB each **if evenly distributed**).

Option B helps:

- Single-tenant queries narrow to one bucket.
- Per-bucket index maintenance stays smaller.
- Partial isolation of hot/cold workloads.

Yet Option B costs:

- 8x more leaf relations and indexes.
- Whole-month queries must read all 8 buckets.
- DDL, stats, and vacuum manage 8x more objects.
- Higher planning, memory, and locking overhead.

If 95% of queries read all tenants for a month and scan the full 100 GB anyway, splitting into 8 buckets does not reduce data read.

### 32.2. Do Not Pick Partition Counts from Raw File Size Alone

A 100 GB table is not automatically "too big." With good indexes, steady workloads, and fast `VACUUM`/backups, one 100 GB leaf can outperform 100 1-GB leaves.

Base decisions on **latency, throughput, maintenance windows, and metadata cost**—not arbitrary GB per table.

---

## 33. Multi-Level Partition Operations Checklist

Treat automated partition provisioning as maintaining structural invariants.

### 33.1. Before Opening a New Month

- Compute half-open `FROM`/`TO` bounds in the target timezone.
- Confirm no unintended overlaps or gaps.
- Create the monthly intermediate partition.
- Create all required `HASH`/`LIST` subpartitions.
- Verify constraints and indexes on every leaf.
- Confirm filesystem/tablespace free space.
- Verify permissions, RLS, triggers, and replication setup.
- Use idempotent jobs with proper lock coordination.
- Never let hot application requests run DDL on the fly.

### 33.2. During Active Operations

- Monitor `INSERT` routing errors.
- Track row counts per leaf.
- Watch for skew and hot partitions.
- Verify query plans and pruning efficiency.
- Track `Planning Time`.
- Monitor `VACUUM`/`ANALYZE` and XID freeze age.
- Track relation and index sizes.
- Alert if `DEFAULT` accumulates rows.
- Track total partition and DDL growth.
- Monitor replication lag and backup health.

### 33.3. When a Period Expires

- Confirm retention window and archival copies.
- Check FKs, downstream consumers, and audits.
- Schedule `DETACH`/`DROP` with safe lock handling.
- Confirm no active queries still depend on old data.
- Record metadata changes.
- Refresh stats or maintenance after major structural changes.
- Verify reports do not lose required historical data.

---

## 34. Common Design Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Unbounded per-tenant partitions | Explosion of relations, catalogs, and indexes | Use HASH buckets or tenant indexes |
| Per-minute partitioning everywhere | Huge count of tiny partitions | Choose granularity from retention and queries |
| Adding 3 levels assuming "smaller is faster" | Too many nodes, costly planning/maintenance | Add levels only with measured proof |
| Forgetting leaf count multiplies across levels | Underestimates operational cost | Calculate total leaves before DDL |
| Queries omitting partition keys | No pruning; scans many leaves | Add key predicates or rethink indexes/schema |
| Wrapping partition keys in functions in `WHERE` | Loses pruning and sargability | Use half-open raw key ranges |
| Using `BETWEEN ... 23:59:59` for full days | Drops sub-second timestamps | Use `>= start AND < next_day` |
| Using UTC for local business days improperly | Wrong date window | Compute exact bounds in business timezone |
| Confusing pruning with index-only access | Assumes one leaf = O(1) | Measure index/heap scans inside leaf |
| Creating local indexes on only some leaves accidentally | Erratic plans across months | Enforce consistent index policies and audits |
| Thinking parent index is a global index | Unkeyed ID lookups still probe everywhere | Understand local indexes / lookup directories |
| `PK(event_id)` when partitioned on other keys | Cannot enforce cross-leaf uniqueness | Use composite keys or an ID registry |
| Assuming FKs are always trivial | Cost and constraints depend on keys and DDL | Check schema and version support |
| Expecting PostgreSQL to auto-create partitions on `INSERT` | `INSERT` fails at month rollover | Pre-create ahead of time and monitor |
| Adding `DEFAULT` and forgetting to monitor it | Misplaced data piles up; hard attaches | Quarantine, monitor, and migrate |
| Running leaf-creation DDL during peak traffic | Lock waits and latency spikes | Scheduled background jobs with lock control |
| Treating `ATTACH` as free and scanless | Can scan rows and validate constraints | Pre-validate `CHECK`/indexes and test on staging |
| Dropping a subtree without archiving | Permanent data loss | Enforce retention approvals and backups |
| Constantly updating partition keys | Row movement, WAL, and index churn | Pick stable keys |
| Measuring `Execution Time` only | Misses climbing `Planning Time` | Measure both planning and execution |
| Enabling partitionwise join/aggregate blindly | Plan and memory bloat | Benchmark per query |
| Summing `COUNT(DISTINCT)` across leaves | Inflates distinct counts | Compute true global distincts / mergeable states |
| Assuming HASH distributes workload evenly | Hot tenants still skew single buckets | Measure skew and hot keys |
| Thinking scaling hash buckets needs no migration | Hard once data exists | Plan explicit repartitioning migrations |
| Disabling autovacuum due to many leaves | Bloat and wraparound freeze risk | Tune autovacuum to workload |
| Analyzing leaves while forgetting parent stats | Inaccurate planner estimates | Keep tree-level stats fresh |
| Keeping excessive indexes on every leaf | Bloats disk, WAL, backups, and DDL | Audit index usage |
| Trusting one warm-cache benchmark | Misjudges overall workload | Repeat runs and test concurrency |
| Confusing one tenant query with full workload | Wrong layout choice | Weight full query mix |
| Ignoring backup/restore and replication | Operational surprises | Rehearse backup/restore and HA |
| Not alerting on relation-count growth | Silent metadata bloat | Alert on leaf and index counts |

---

## 35. Practice Exercises

### Exercise 1 — Explaining Tree Levels

Sketch a `RANGE(event_at) → LIST(region)` tree with 12 months and 4 regions per month. How many intermediate nodes, leaves, and table relations exist excluding indexes?

### Exercise 2 — Calculating Three-Level Explosion

A system keeps 36 months, 16 tenant hash buckets per month, and 3 event types per bucket. Calculate total leaves and physical indexes if each leaf has four indexes.

### Exercise 3 — Creating Two Levels with DDL

Using the lab schema, create March with `LIST(region)` matching January/February. Why is creating `events_2026_03 PARTITION BY LIST(region)` alone without leaves insufficient for `INSERT`s?

### Exercise 4 — Inspecting tableoid

Insert a January `NORTH` row, a February `SOUTH` row, and a February `CENTRAL` row. Use `tableoid::REGCLASS` to identify each row's leaf partition.

### Exercise 5 — pg_partition_tree

Write a query listing `relid`, `parentrelid`, `isleaf`, and `level`. Count leaves and intermediate nodes before and after adding March.

### Exercise 6 — Pruning Both Levels

Write a January/`NORTH` query and run `EXPLAIN`. Which leaves are eliminated and why?

### Exercise 7 — Time Filter Only

Write a February query with no `region` filter. What can PostgreSQL prune, and why must it still check three region leaves?

### Exercise 8 — Region Filter Only

Write a `SOUTH` query with no time predicate. Why must it inspect `SOUTH` across every month, and why do leaf scans grow with retention months?

### Exercise 9 — Non-Partition-Key Tenant

Write a query filtering only `tenant_id=42` in the lab. Explain why a local tenant index on leaves helps yet cannot prune other leaves on its own.

### Exercise 10 — Half-Open Ranges

Write `WHERE` predicates for Feb 1, 2026 in UTC and in `Asia/Ho_Chi_Minh`. Why is casting `event_at::DATE` unfavorable for pruning?

### Exercise 11 — Prepared Statements

Create a `PREPARE` taking `start`/`end`/`region`. Run `EXPLAIN EXECUTE`. Explain plan-time vs. execution-time pruning clues and why generic plans differ from custom plans.

### Exercise 12 — HASH Before RANGE

Design a two-bucket tenant tree where each bucket holds January and February. Analyze surviving leaf subsets for tenant-only, time-only, and combined queries.

### Exercise 13 — Choosing Level Order

A system runs 90% time-range queries, 10% tenant-only queries, and purges whole months for retention. Pick a level ordering and list assumptions to benchmark.

### Exercise 14 — PK/UNIQUE

Why can't `PRIMARY KEY(event_id)` on a tree partitioned by `event_at` and `region` enforce tree-wide uniqueness easily? Design a valid composite key and explain how to enforce global `event_id` uniqueness if required.

### Exercise 15 — Index Multiplier

With 48 months × 12 hash leaves and 5 indexes per leaf, calculate total leaf indexes and name at least four operational costs.

### Exercise 16 — Global Lookup

An app frequently receives `event_id` without timestamp or region. Why is `WHERE event_id=?` slow on `RANGE→LIST`? Propose solutions.

### Exercise 17 — Planner Overhead

Run `EXPLAIN (ANALYZE, BUFFERS)` and record `Planning Time`/`Execution Time` for a single-leaf query versus a full-tree query. Why doesn't a fast single-leaf scan prove an oversized tree has zero metadata overhead?

### Exercise 18 — Footprint per Leaf

Use `pg_partition_tree` and `pg_total_relation_size` to calculate leaf sizes. Find the largest leaf and discuss skew.

### Exercise 19 — Metadata/Index Counts

Join `pg_index` with `pg_partition_tree` to count indexes per leaf. If a new month has fewer indexes than older months, what causes should you investigate?

### Exercise 20 — Relation Locks

Use `pg_locks` to inspect relation locks during a read or DDL transaction in the lab. Why isn't `max_locks_per_transaction` an exact partition-count limit?

### Exercise 21 — Autovacuum

A current leaf gets millions of updates while historical leaves stay static. Propose how to monitor `n_dead_tup`, `last_autovacuum`, and freeze age per leaf.

### Exercise 22 — Parent Statistics

After loading a large dataset into the tree, run `ANALYZE` on the parent. Why can both tree-wide and per-leaf statistics matter to the query planner?

### Exercise 23 — Missing Partition

Insert a March row before creating the March `RANGE` partition. What error occurs, and why doesn't PostgreSQL auto-create the month?

### Exercise 24 — DEFAULT

Explain the difference between `DEFAULT` at January's `LIST` level versus `DEFAULT` at the root `RANGE` level. What risks arise if `DEFAULT` absorbs lots of misrouted rows?

### Exercise 25 — ATTACH Validation

A populated staging table needs attaching as a new monthly partition. Why might PostgreSQL scan it, and how does a pre-validated bound `CHECK` constraint help?

### Exercise 26 — Retention

Partitioned into 24 months × 8 hash buckets. When purging old months, what is the advantage of outer monthly `RANGE`? What must be checked before `DETACH`/`DROP`?

### Exercise 27 — Updating the Partition Key

Update `event_at` from January to February. Why does this trigger row movement and index/WAL overhead? Observe `RETURNING tableoid::REGCLASS` inside a rolled-back lab transaction.

### Exercise 28 — Partition-Wise Join

Two tables A and B share `(month, tenant bucket)` partitioning. What join and alignment conditions are required for partition-wise join, and what costs rise at 1,000 leaves?

### Exercise 29 — Partition-Wise Aggregate

A report counts rows per tenant across all months. Why must monthly results be combined? If switching `COUNT` to `COUNT(DISTINCT customer_id)`, why is summing monthly counts wrong?

### Exercise 30 — Full Scan Across Thousands of Leaves

An all-time row count has no `WHERE` on the partition key. Why might 48 months × 32 buckets perform worse than 48 monthly leaves? Propose a summary alternative for frequent dashboards.

### Exercise 31 — Hot Tenant

One tenant generates 80% of writes. Does `HASH(tenant_id)` with 32 buckets balance load evenly? Propose how to measure and alternative designs.

### Exercise 32 — DDL Automation

Write pseudocode for a job creating next month's `RANGE→HASH(16 buckets)` subtree, verifying bounds, indexes, idempotency, and alerting on missing partitions.

### Exercise 33 — Indexes vs. Subpartitions

Queries routinely filter `event_at` and `tenant_id`. Compare 24 monthly leaves + tenant B-tree against 24 × 8 hash leaves. Which benchmarks do you need before deciding?

### Exercise 34 — Experiment Plan

Design a workload of four queries: `(time+tenant)`, time only, tenant only, and full history. Measure `Planning Time`, `Execution Time`, `Buffers`, partitions scanned, locks, and index footprint.

### Exercise 35 — Partitioning vs. Other Architectures

A system has tens of thousands of tenants, a few hundred events/day per tenant, monthly retention, and `tenant+time` API queries. Why is per-tenant `LIST` dangerous? Propose a sound tree and pruning monitoring plan.

### Exercise 36 — Backup/Restore Concerns

Scaling from 100 to 5,000 partitions with multiple indexes per leaf impacts backups, restores, `ANALYZE`, replication, and monitoring. Propose pre-migration validation criteria.

### Exercise 37 — Migrating from Single-Level to Multi-Level

An active table has 24 monthly partitions. Plan a minimal-downtime migration to `RANGE(month)→HASH(tenant)`, covering data movement, locks, constraints, dual-write/verification if used, rollback, and validation. Focus on risks rather than production scripts.

### Exercise 38 — Decision Synthesis

A team proposes 60 months × 64 buckets × 5 event types. Calculate leaf count and index count at four indexes per leaf. List questions that must be answered before approving, covering workload, retention, global lookups, planning, disk, vacuum, and DDL locks.

---

## 36. Checklist Before Choosing Partition Counts and Levels

| Question | Required Evidence |
| --- | --- |
| Why partition at all? | Concrete pruning, retention, maintenance, or workload goal |
| What splits the outer level? | Key column, filter patterns, retention unit |
| What splits the inner level? | Query patterns and skew |
| Why add a second level? | Proven gain over single-level leaf indexes |
| How many months stay online? | Retention policy |
| How many subpartitions per month? | Sized to load, not "more is better" |
| What is the total leaf count? | Product across levels or sum across branches |
| What is the total index count? | Indexes per leaf × leaves |
| Do queries filter partition keys in `WHERE`? | Real workload query share |
| Do both levels prune simultaneously? | `EXPLAIN` with realistic parameters |
| Are there queries without time filters? | Global scans and lookups |
| Is global uniqueness required? | PK, `UNIQUE`, event ID rules |
| Are there complex FKs? | Design and retention compatibility |
| Will `UPDATE`s modify partition keys? | Row movement and concurrency |
| Is a `DEFAULT` partition present? | Monitoring and drainage policy |
| Are future partitions pre-created? | Automated ahead of period start |
| Does DDL run during peak traffic? | Lock tests and maintenance windows |
| Will staging tables be attached? | Constraint validation and scan costs |
| Does retention use `DETACH`/`DROP`? | Backups, FKs, archival, audits |
| Is there an extreme hot tenant? | Skew and hash bucket distribution |
| Does `Planning Time` grow? | `EXPLAIN` across representative queries |
| Does `Execution Time` drop? | `EXPLAIN` on realistic workload |
| Are local-only indexes needed? | Per-leaf index usage and disk |
| Is `VACUUM`/`ANALYZE` tuned per leaf? | Stats freshness and XID age |
| Are parent stats maintained? | `ANALYZE` and row estimates |
| Is there lock-memory pressure? | `pg_locks`, concurrency, `max_locks` config |
| Are partition-wise options used? | `enable_partitionwise*` cost trade-offs |
| Does the workload run all-time rollups? | Summary tables / materialized views |
| Are read replicas or logical replication used? | Schema/DDL sync and lag |
| Can backup/restore handle object counts? | Restore rehearsal |
| Tested on production-like data? | Realistic distribution, row width, indexes |
| Benchmarked repeatedly under concurrency? | P95 latency, CPU, I/O, memory |
| Monitored leaf and index counts? | Alerts on runaway growth |
| Plan to resize hash buckets later? | Repartitioning/migration strategy |
| Can granularity be coarser? | Monthly instead of daily/minute if viable |
| Total cost of ownership measured? | Queries + DDL + storage + operations |

## Conclusion

**Multi-level partitioning** lets PostgreSQL combine organizational goals—such as **time `RANGE`** to bound history alongside **regional/tenant `LIST`/`HASH`** to sharpen pruning or isolate maintenance. Yet every added level multiplies leaf partitions, typically by the product of branches at each level.

Key takeaways:

1. **Partition pruning drives the main gain for filtered queries.** Queries must supply compatible predicates on partition keys at each level to skip the maximum number of branches.
2. **Partitioning does not replace indexes.** Pruning selects leaves; indexes or scans access rows inside leaves. Queries omitting partition keys still probe many leaves.
3. **Partition counts carry real overhead.** Each leaf brings metadata, indexes, stats, locks, autovacuum, DDL, planning, and backup/restore work.
4. **There is no universal optimal leaf count.** Measure the mix of pruned vs. unpruned queries, `Planning Time`, `Execution Time`, I/O, memory, and maintenance duration.
5. **Level order reflects business priorities.** Outer time `RANGE` eases monthly retention; outer tenant `HASH` favors tenant-scoped queries without time filters.
6. **Tree-wide `UNIQUE`/`PRIMARY KEY` has strict limits.** Never assume local indexes enforce global uniqueness for keys omitting partition keys.
7. **Operations are part of the design.** Pre-create all subpartitions, govern `DEFAULT`, watch skew, plan `ATTACH`/`DETACH`, and verify indexes and stats.
8. **Never split finer just because you can.** If one large leaf reads fast via indexes and vacuums/backs up cleanly, multiplying leaf counts often hurts more than it helps.
9. **All-history reports may need summaries.** Partition-wise aggregation never turns full-history `COUNT`/`SUM` into constant-time reads.
10. **Benchmarking decides.** Compare single-level vs. multi-level designs on realistic data, parameters, concurrency, retention, and settings before expanding the tree.

A strong PostgreSQL partitioning design is never the one with the most partitions—it is the one with **just enough levels and leaves to shrink data touched while keeping metadata and operational costs sustainable long term**.
