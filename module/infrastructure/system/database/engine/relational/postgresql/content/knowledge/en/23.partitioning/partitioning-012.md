# Evaluating Query Plans, Locks, and Maintenance on Partitioned Tables in PostgreSQL

## 1. Why Can a Partitioned Table Still Be Slow or Blocked?

Imagine a transactions table holding hundreds of millions of rows, partitioned by month. A report only needs February data, yet the query plan still touches multiple child tables. Creating next month's partition forces active writes to wait. An older partition receiving zero new writes keeps growing in disk usage or lacks fresh statistics. A `DROP TABLE` intended to purge historical data ends up blocked behind a long-running read transaction.

All of these happen because **partitioning does not automatically replace query tuning, lock management, and maintenance**.

Three questions must be answered when operating partitioned tables in PostgreSQL:

1. **Query plan:** Is the planner actually pruning away irrelevant partitions? Within each remaining partition, what scan, join, aggregate, and index paths are chosen?
2. **Locks:** Which parent and partition relations can a `SELECT`, `INSERT`, DDL statement, or `ATTACH`/`DETACH` operation lock? Who is blocking whom?
3. **Maintenance:** How are statistics, `VACUUM`, indexes, storage size, and data retention managed at both the parent and per-partition levels?

Mental model to remember:

```text
                    sales (partitioned parent)
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
     sales_2026_01     sales_2026_02     sales_2026_03 ...
       Jan rows          Feb rows          Mar rows
          |                 |                 |
       local index       local index       local index
          |                 |                 |
       VACUUM /          VACUUM /          VACUUM /
       ANALYZE            ANALYZE            ANALYZE
          \                 |                 /
           +----------------+----------------+
                            |
                 Parent query / DDL / locks
```

A `SELECT * FROM sales` accesses the **logical partitioned table**. Actual rows reside in **leaf partitions**, not in the partitioned parent's heap.

> **Key takeaway:** partition pruning avoids reading irrelevant partitions, yet does not guarantee each surviving partition gets a good plan; partition management DDL can require heavy locks; and `VACUUM`/`ANALYZE`/index work must be monitored at the right level.

## 2. Learning Objectives

After completing this lesson, you will be able to:

1. Inspect parent table structure, partition bounds, child partitions, and local indexes.
2. Explain the difference between **partition pruning** and an **index scan**.
3. Read `Append`, `Merge Append`, and `Parallel Append` alongside per-partition scan nodes.
4. Distinguish pruning at **planning time**, **initialization time**, and **execution time**.
5. Understand the impact of literal constants, bind parameters, and generic prepared plans.
6. Recognize `WHERE` predicates that prevent expected pruning.
7. Understand the limits and trade-offs of partitionwise joins and aggregates.
8. Evaluate indexes on the partitioned parent and on each leaf partition.
9. Explain lock impacts of `SELECT`/`INSERT`/`UPDATE` and partition DDL operations.
10. Diagnose lock-waiting sessions using `pg_locks`, `pg_stat_activity`, and `pg_blocking_pids`.
11. Plan safer `ATTACH PARTITION`, `DETACH PARTITION`, and `DROP` operations.
12. Understand the limitations of `CREATE INDEX CONCURRENTLY` on partitioned tables.
13. Distinguish parent vs. child statistics, and configure `ANALYZE` and autovacuum appropriately.
14. Track bloat, dead tuples, index usage, and disk size per partition.
15. Design partition-based retention/archival workflows with rollback paths and late-data controls.
16. Verify real improvements with `EXPLAIN` and empirical metrics rather than assuming partitioning is always faster.

## 3. How Does Declarative Partitioning Work?

PostgreSQL supports declarative partitioning via:

- `PARTITION BY RANGE`: splits by contiguous value intervals, such as months.
- `PARTITION BY LIST`: splits by explicit lists of values, such as regions or categories.
- `PARTITION BY HASH`: splits by a hash of the partition key.

Example:

```sql
CREATE TABLE sales (
    sold_on date NOT NULL,
    sale_id bigint NOT NULL,
    amount numeric(12,2) NOT NULL
) PARTITION BY RANGE (sold_on);
```

Create child tables:

```sql
CREATE TABLE sales_2026_01 PARTITION OF sales
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE sales_2026_02 PARTITION OF sales
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

With `RANGE`, the `FROM` bound is **inclusive** and the `TO` bound is **exclusive**:

```text
sales_2026_01: [2026-01-01, 2026-02-01)
sales_2026_02: [2026-02-01, 2026-03-01)
```

### 3.1. A Parent Table Differs from a Regular Table

A parent declared with `PARTITION BY` is a logical relation governing partitioning. When inserting through the parent, PostgreSQL routes rows to the child matching the partition key.

Because the parent has no heap storing partitioned rows, calling:

```sql
SELECT pg_relation_size('schema.sales'::regclass);
```

**does not return the total data size** across all partitions. To measure total storage, you must sum across leaf relations along with their indexes and TOAST tables.

### 3.2. Each Partition Is a Real Table

Every leaf partition has its own:

- Heap pages.
- Attached indexes.
- Statistics and `VACUUM` state.
- Catalog metadata and lock relations.
- Data and TOAST storage where applicable.

Consequently, maintenance cannot treat `sales` as a single monolithic table on a dashboard.

### 3.3. Partitioning Is Not Sharding

All partitions in this lesson reside in one PostgreSQL database managed by a single cluster. They do not automatically distribute data across separate servers like sharding.

Placing partitions onto separate tablespaces likewise does not turn partitioning into a distributed cluster coordinator.

## 4. Setting Up a Monthly Lab Environment

Run exercises in a **test database**. Bulk data generation, index builds, and DDL consume real resources; never run them directly on production.

### 4.1. Create the Schema

```sql
CREATE SCHEMA IF NOT EXISTS part_eval_lab;
```

### 4.2. Create the Parent Table with a Valid Primary Key

```sql
CREATE TABLE part_eval_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY,
    sold_on date NOT NULL,
    tenant_id integer NOT NULL,
    status text NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0),
    note text NOT NULL,
    PRIMARY KEY (sold_on, sale_id)
) PARTITION BY RANGE (sold_on);
```

**Why is the PRIMARY KEY `(sold_on, sale_id)`?**

PostgreSQL lacks a conventional global unique index spanning every partition as a single heap index. Any `PRIMARY KEY` or `UNIQUE` constraint declared on a partitioned table must include all partition key columns under PostgreSQL's supported rules so uniqueness can be enforced locally per partition index.

Here, `sold_on` is the partition key, making `PRIMARY KEY (sold_on, sale_id)` valid.

`sale_id` comes from an identity sequence, yet **do not treat a sequence alone as enforcing global uniqueness** across all write paths or migrations. If business rules require a globally unique ID independent of date, design an explicit enforcement mechanism rather than assuming you can declare `UNIQUE (sale_id)` on a parent `RANGE`-partitioned by `sold_on`.

### 4.3. Create Four Partitions

```sql
CREATE TABLE part_eval_lab.sales_2026_01
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE part_eval_lab.sales_2026_02
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE part_eval_lab.sales_2026_03
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE part_eval_lab.sales_2026_04
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
```

Add a `DEFAULT` partition to study out-of-range rows:

```sql
CREATE TABLE part_eval_lab.sales_default
PARTITION OF part_eval_lab.sales DEFAULT;
```

Never declare overlapping bounds. `DEFAULT` catches rows falling outside all explicit partitions.

### 4.4. Generate 120,000 Rows Through the Parent

```sql
INSERT INTO part_eval_lab.sales (
    sold_on, tenant_id, status, amount, note
)
SELECT
    DATE '2026-01-01' + ((g - 1) % 120),
    CASE
        WHEN g % 5 IN (0, 1, 2, 3) THEN 1
        ELSE 2 + ((g / 5) % 400)
    END,
    CASE
        WHEN g % 17 = 0 THEN 'CANCELLED'
        WHEN g % 7  = 0 THEN 'PENDING'
        ELSE 'PAID'
    END,
    ((g * 31) % 100000)::numeric / 100,
    repeat('sale-note-', 8) || g::text
FROM generate_series(1, 120000) AS s(g);
```

Temporal distribution:

- `2026-01-01` through `2026-04-30` spans exactly **120 days** across the first four months of 2026.
- Each day receives 1,000 generated rows.
- Tenant 1 accounts for roughly 80% of rows.
- Remaining tenants divide the remaining share.

This dataset lets us evaluate both **date/month partition pruning** and the effect of **per-tenant selectivity** inside each partition.

### 4.5. Gather Statistics

```sql
ANALYZE part_eval_lab.sales;
```

Rows were inserted through the parent, yet physically reside in leaves. After `ANALYZE`, `EXPLAIN` can use accurate statistics.

### 4.6. Inspect Rows per Partition

```sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS rows_in_partition,
    MIN(sold_on) AS first_date,
    MAX(sold_on) AS last_date
FROM part_eval_lab.sales
GROUP BY tableoid
ORDER BY physical_partition;
```

You should see rows across all four monthly partitions, with zero rows in `sales_default` from this load.

`tableoid` returns the OID of the **physical table** holding each tuple, making `tableoid::regclass` useful for observing row routing. Never use `tableoid` as a business primary key.

## 5. Inspecting the Partition Tree and Bounds

Before interpreting `EXPLAIN`, verify which partitions actually exist in the schema.

### 5.1. `pg_partition_tree`

```sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
)
ORDER BY level, relation_name;
```

On versions supporting `pg_partition_tree`, output lists the parent (level 0) and all descendants:

- `relid`: relation OID.
- `parentrelid`: immediate parent node, NULL at the root.
- `isleaf`: true if the node is not further partitioned.
- `level`: depth in the tree.

### 5.2. Query Bounds from the Catalog

```sql
SELECT
    i.inhrelid::regclass AS child_partition,
    pg_get_expr(
        child.relpartbound,
        child.oid
    ) AS partition_bound
FROM pg_inherits AS i
JOIN pg_class AS child
  ON child.oid = i.inhrelid
WHERE i.inhparent = 'part_eval_lab.sales'::regclass
ORDER BY child.relname;
```

`pg_inherits` records inheritance/partition parent-child links. For declarative partitions, `relpartbound` stores the enforced partition boundaries.

### 5.3. Inspecting in psql

In `psql`, the command:

```text
\d+ part_eval_lab.sales
```

displays the partition key, list of partitions, and indexes depending on version. This is a `psql` client meta-command, **not SQL** you can send over JDBC.

### 5.4. Common Bug: A New Partition Is Not Actually Attached

A table named `sales_2026_05` **does not become a partition** just by matching a naming convention. It must be created via `PARTITION OF` or attached via `ALTER TABLE ... ATTACH PARTITION`.

If `pg_partition_tree` omits that node, queries through the parent will never read a standalone table with a matching name.

## 6. Query Plans: Reading `Append` First

Multi-partition queries typically appear with an `Append` node or equivalent structure.

Example:

```sql
EXPLAIN
SELECT sale_id, sold_on, tenant_id, amount
FROM part_eval_lab.sales;
```

Illustrative plan shape:

```text
Append
  -> Seq Scan on sales_2026_01
  -> Seq Scan on sales_2026_02
  -> Seq Scan on sales_2026_03
  -> Seq Scan on sales_2026_04
  -> Seq Scan on sales_default
```

This is an **illustrative shape**, not mandatory output. PostgreSQL may pick `Parallel Append`, reorder nodes, or pick another plan shape depending on query, stats, and version.

### 6.1. What Does `Append` Mean?

`Append` concatenates result streams from multiple child plans. Each child subplan can be:

- `Seq Scan`.
- `Index Scan`.
- `Bitmap Heap Scan`.
- A deeper subplan or join.

It does not mean "all partition data has been merged into a single heap."

### 6.2. `Append` Guarantees No Ordering

Without `ORDER BY`, PostgreSQL makes no promise to return rows ordered by month, partition creation order, or primary key.

When ordering is required:

```sql
SELECT sale_id, sold_on, amount
FROM part_eval_lab.sales
ORDER BY sold_on, sale_id;
```

the planner must enforce that sort order explicitly via a `Sort` or an ordered scan path.

### 6.3. `Merge Append`

When child paths already produce compatible sort orders, PostgreSQL can choose `Merge Append` to merge pre-sorted streams:

```text
Merge Append
  Sort Key: sold_on, sale_id
  -> Index Scan on sales_2026_01 ...
  -> Index Scan on sales_2026_02 ...
  -> Index Scan on sales_2026_03 ...
  -> Index Scan on sales_2026_04 ...
```

`Merge Append` can avoid a separate global `Sort`, though merging many streams still carries overhead. Not every `ORDER BY` query selects it.

### 6.4. `Parallel Append`

In a parallel plan, workers can execute child subplans concurrently under `Parallel Append`:

```text
Gather
  -> Parallel Append
       -> Parallel Seq Scan on sales_2026_01
       -> Parallel Seq Scan on sales_2026_02
       -> ...
```

Net benefit depends on partition sizes, worker count, I/O, and coordination overhead. Across many tiny partitions, worker coordination can outweigh gains.

### 6.5. Never Judge a Plan Solely by Node Count

An `Append` spanning 12 tiny children can finish rapidly. A plan touching a single partition that `Seq Scan`s a billion rows can still crawl.

Compare **actual rows, buffers, execution time, surviving partition count after pruning, and the scan path inside each leaf**.

## 7. Partition Pruning: Eliminating Unneeded Partitions

**Partition pruning** lets PostgreSQL rule out partitions **incapable of containing matching rows** based on declared bounds.

### 7.1. Querying Only February

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_on, tenant_id, amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

With `RANGE` partitioning on `sold_on`, the predicate aligns cleanly with `sales_2026_02` bounds.

The planner eliminates January, March, April, and default right at planning time. An illustrative plan reduces to:

```text
Seq Scan on sales_2026_02
  Filter: (
      sold_on >= '2026-02-01'::date
      AND sold_on < '2026-03-01'::date
  )
```

Depending on optimizer version, the plan may retain a single-child `Append` wrapper or collapse straight to a direct child scan. **Both represent successful pruning.**

### 7.2. Two-Month Predicate

```sql
EXPLAIN
SELECT sale_id, sold_on
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-04-01';
```

This needs only February and March partitions.

### 7.3. Query Without the Partition Key

```sql
EXPLAIN
SELECT sale_id, sold_on, tenant_id
FROM part_eval_lab.sales
WHERE tenant_id = 1;
```

Even though `tenant_id = 1` is heavily queried, it **does not enable pruning date partitions**. PostgreSQL must check every partition, picking local scans or indexes per child independently.

**Partition pruning relies on partition key bounds, not merely having a `WHERE` clause.**

### 7.4. Pruning Is Not Index Usage

Even after pruning eliminates three partitions for February, PostgreSQL still needs to read inside `sales_2026_02`.

Within that partition it may pick:

- `Seq Scan`.
- `Index Scan` on a local index.
- `Bitmap Heap Scan`.

Even with zero indexes on `sold_on`, pruning **still works** because it operates purely on catalog partition bounds.

### 7.5. There Is No Rule That "One Partition Is Always Fast"

If February holds 500 million rows, scanning that single partition is still expensive. If a query looks up one small tenant inside February, a local index `(tenant_id, sold_on)` matters far more than trimming 12 partitions down to 1.

## 8. Writing Pruning-Friendly Predicates

Help PostgreSQL infer partition ranges by writing predicates directly on the raw partition key whenever possible.

### 8.1. Prefer Half-Open Intervals `[start, end)`

```sql
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
```

Advantages:

- Aligns identically with `RANGE` partition bounds.
- Eliminates guessing the last day of each month.
- Extends naturally to sub-second timestamps.
- Works cleanly with bind parameters for `start` and `end`.

### 8.2. Functions Wrapping the Key Column Can Block Pruning

Example:

```sql
WHERE date_trunc(
    'month',
    sold_on::timestamp
) = timestamp '2026-02-01 00:00:00'
```

Logically, for calendar dates this targets February. Yet the planner often cannot invert the expression back into tight `sold_on` range constraints matching partition bounds.

A cleaner form:

```sql
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
```

### 8.3. Be Careful Wrapping Columns in Casts or String Expressions

```sql
WHERE sold_on::text LIKE '2026-02%'
```

is not equivalent in optimization potential to direct range predicates. It complicates types/operators and blocks both clean pruning and B-tree index usage.

### 8.4. With `TIMESTAMP` / `TIMESTAMPTZ`

When the partition key is `timestamptz`, align explicitly with the domain timezone and monthly boundaries.

Example UTC window:

```sql
WHERE created_at >= timestamptz '2026-02-01 00:00:00+00'
  AND created_at <  timestamptz '2026-03-01 00:00:00+00'
```

Never use `BETWEEN ... 23:59:59` to denote "through end of day" on timestamps, as fractional seconds get missed.

### 8.5. Complex `OR` and Optional Filter Patterns

A predicate like:

```sql
WHERE (
    $1 IS NULL
    OR sold_on >= $1
)
```

prevents a generic plan from pruning tightly to fixed bounds, since the plan must remain valid when `$1` is `NULL`.

If an endpoint supports both "unfiltered" and "date-bounded" modes, consider separate query shapes with explicit bind parameters.

## 9. Plan-Time Pruning: Bounds Known During Planning

When queries contain constants:

```sql
SELECT *
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-03-01'
  AND sold_on <  DATE '2026-04-01';
```

the planner already has enough facts to eliminate non-March partitions during planning.

### 9.1. Pruned Partitions May Not Appear in `EXPLAIN`

Because nodes are discarded before the final plan is built, `EXPLAIN` usually **omits pruned partition names completely**.

To confirm pruning occurred, compare:

- Full partition count from `pg_partition_tree`.
- Partition names printed in `EXPLAIN`.
- Actual buffers read/hit.

### 9.2. What Overhead Does Early Pruning Save?

It can reduce:

- Relations included in access path search.
- Child subplans executed.
- Heap and index pages touched.
- Lock acquisition and executor setup work in some plans.

Not all catalog and planner overhead disappears—especially with thousands of partitions and complex queries.

### 9.3. Pruning Cannot Skip `DEFAULT` Under Ambiguous Predicates

Whenever predicates leave partition key ranges open, the `DEFAULT` partition remains a valid candidate.

When using `DEFAULT`, monitor whether it holds unexpected data; any query omitting the date filter must touch `DEFAULT` alongside every month.

## 10. Execution-Time Pruning with Prepared Statements

Applications routinely parameterize date bounds:

```sql
SELECT sale_id, sold_on, tenant_id
FROM part_eval_lab.sales
WHERE sold_on >= $1
  AND sold_on < $2;
```

A generic prepared plan lacks concrete values for `$1` and `$2` at planning time. PostgreSQL supports **execution-time partition pruning** in eligible plans.

### 10.1. Create a Prepared Statement in the Lab

```sql
PREPARE sales_in_range(date, date) AS
SELECT sale_id, sold_on, tenant_id, amount
FROM part_eval_lab.sales
WHERE sold_on >= $1
  AND sold_on < $2;
```

### 10.2. Force a Generic Plan to Observe Behavior

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE sales_in_range(
    DATE '2026-02-01',
    DATE '2026-03-01'
);

ROLLBACK;
```

The generic plan shows an `Append` over candidate children, while the executor skips unneeded ones using runtime parameter values.

Look for output lines such as:

```text
Append
  Subplans Removed: 4
  -> Seq Scan on sales_2026_02 ...
```

The `4` is illustrative if four partitions were removed at executor initialization. Actual plans vary by version and tree structure.

### 10.3. What Does `Subplans Removed` Mean?

When pruning executes **at executor initialization time**, `EXPLAIN` reports `Subplans Removed`. Eliminated subplans never run.

Never treat the mere presence of `Append` as proof pruning failed when irrelevant subplans were cleanly removed.

### 10.4. Per-Row Re-Pruning During Execution

Inside a `Nested Loop` or parameterized subquery where the partition key varies per outer row, PostgreSQL can re-prune partitions dynamically during execution.

`EXPLAIN ANALYZE` then shows partitions with:

- Varying `loops` counts.
- `(never executed)` annotations.
- Specific partitions scanned in some outer iterations and skipped in others.

Do not look solely at `Subplans Removed` to diagnose all pruning; pruning at different execution phases shows up differently in `EXPLAIN`.

### 10.5. Test a Custom Plan

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE sales_in_range(
    DATE '2026-02-01',
    DATE '2026-03-01'
);

ROLLBACK;
```

A custom plan plugs concrete parameter values straight into planning, pruning partitions earlier.

### 10.6. Clean Up the Prepared Statement

```sql
DEALLOCATE sales_in_range;
```

### 10.7. Never Assume Generic Plans Always Scan Every Partition

A widespread myth claims:

> "Prepared SQL using `$1` definitely scans every partition."

That is false on PostgreSQL versions supporting execution-time partition pruning with suitable predicates. Generic plans still skip irrelevant subplans.

However, execution-time pruning has boundaries, and planning/lock behavior can differ from plan-time pruning. **Measure on your real version and queries.**

## 11. `enable_partition_pruning` and Constraint Exclusion

PostgreSQL exposes:

```sql
SHOW enable_partition_pruning;
SHOW constraint_exclusion;
```

### 11.1. Partition Pruning Is Its Own Mechanism

`enable_partition_pruning` controls whether planner and executor apply declarative partition pruning.

Observe the difference in the lab:

```sql
BEGIN;

SET LOCAL enable_partition_pruning = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';

ROLLBACK;
```

Compare against default settings:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

With pruning disabled, all child plans appear. Even then, local indexes or other bounds may still influence how individual children execute.

### 11.2. Constraint Exclusion Differs from Partition Pruning

Constraint exclusion inspects general `CHECK` constraints to prove tables cannot match query predicates in specific scenarios. It is related, yet **not synonymous** with declarative partition pruning.

In modern declarative partitioning, bound-based partition pruning is the primary engine. Do not blindly toggle `constraint_exclusion` expecting it to cure slow partitioned queries.

### 11.3. Disabling Planner Flags Is Strictly for Lab Testing

`SET LOCAL enable_partition_pruning = off` helps illustrate the mechanism; never leave it off in production.

If a query already prunes cleanly yet remains slow, inspect the scan/index inside surviving partitions, join/aggregation costs, and data skew.

## 12. Parent Indexes vs. Physical Local Indexes

A partitioned table holds a **partitioned index definition** on the parent, backed by real physical child indexes on each partition.

### 12.1. Create an Index via the Parent

```sql
CREATE INDEX sales_tenant_date_idx
ON part_eval_lab.sales (tenant_id, sold_on);
```

PostgreSQL propagates index management down the hierarchy, creating or attaching matching local indexes across existing partitions.

Conceptually:

```text
sales_tenant_date_idx (partitioned parent index)
            |
     +------+------+------+
     |      |      |      |
    Jan    Feb    Mar    Apr  (local B-tree indexes)
```

There is no single physical B-tree holding entries across all months.

### 12.2. Using an Index After Pruning

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_on, amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
  AND tenant_id = 321;
```

This query benefits twice:

1. Pruning keeps only the February partition.
2. Within February, PostgreSQL can use the local B-tree on `(tenant_id, sold_on)` when cost-effective.

Illustrative plan:

```text
Index Scan using sales_2026_02_tenant_id_sold_on_idx
  on sales_2026_02
  Index Cond: (
      tenant_id = 321
      AND sold_on >= '2026-02-01'::date
      AND sold_on < '2026-03-01'::date
  )
```

Exact child index names may vary. Focus on **the access path inside the surviving partition**.

### 12.3. A Partition May Still Use `Seq Scan` Even When Indexed

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_on, tenant_id, amount, note
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
  AND tenant_id = 1;
```

Tenant 1 accounts for roughly 80% of rows. A `Seq Scan` over February beats chasing 80% of heap tuples through an index. **That is not a pruning failure.**

### 12.4. Index-Only Scans and the Visibility Map

When a local index covers all queried columns, PostgreSQL considers `Index Only Scan`. Whether heap fetches are actually skipped depends on **each partition's own MVCC visibility map**.

Quiet historical partitions often yield higher heap-fetch avoidance than active partitions receiving heavy `INSERT`/`UPDATE` traffic.

### 12.5. Do Not Index Every Column Across Every Partition

Extra indexes multiply:

- Storage per child partition.
- Write amplification and WAL volume.
- DDL time whenever new partitions are added.
- `REINDEX` and `VACUUM` overhead.
- Catalog entries and planner overhead.

Add indexes strictly from observed query patterns.

## 13. Creating Indexes on a Live Partitioned System

Running:

```sql
CREATE INDEX index_name
ON part_eval_lab.sales (tenant_id, status);
```

must build indexes across multiple partitions, consuming I/O and taking locks per version behavior. It is not a non-blocking operation.

### 13.1. `CREATE INDEX CONCURRENTLY` Restriction on Parents

On supported declarative partitioning releases, you cannot simply run:

```sql
-- Not supported as a guaranteed single online command:
CREATE INDEX CONCURRENTLY ix
ON part_eval_lab.sales (tenant_id);
```

expecting PostgreSQL to concurrently build every child index automatically from the parent. **Direct `CREATE INDEX CONCURRENTLY` on a partitioned parent is unsupported** in those versions.

Check documentation for your exact PostgreSQL release when writing runbooks.

### 13.2. Building Per-Partition Concurrently and Attaching

The supported online workflow in compatible versions:

1. Create **partitioned index metadata** on the parent using `ON ONLY`; the parent index starts marked invalid until all child indexes are attached.
2. Build each child index individually using `CREATE INDEX CONCURRENTLY` outside any explicit transaction block.
3. Attach each child index with `ALTER INDEX ... ATTACH PARTITION` matching the parent index definition.
4. Once every child partition has a valid attached index, PostgreSQL automatically marks the parent index valid.

Illustrative example for **a brand-new index** (do not run if an identical index already exists):

```sql
-- 1. Metadata index on parent:
CREATE INDEX sales_tenant_status_parent_idx
ON ONLY part_eval_lab.sales (tenant_id, status);

-- 2. Build one child index concurrently:
-- CREATE INDEX CONCURRENTLY must run outside BEGIN/COMMIT.
CREATE INDEX CONCURRENTLY sales_2026_01_tenant_status_idx
ON part_eval_lab.sales_2026_01 (tenant_id, status);

-- 3. Attach child index to parent index:
ALTER INDEX part_eval_lab.sales_tenant_status_parent_idx
ATTACH PARTITION
part_eval_lab.sales_2026_01_tenant_status_idx;

-- 4. Repeat for all remaining partitions, including DEFAULT.
```

**Note:** the snippet above only attaches **one partition**; the parent index remains invalid until every required child index is attached. When compatible child indexes already exist, verify exact definition reuse and compatibility rules.

### 13.3. Never Wrap This Workflow in a Single Transaction

`CREATE INDEX CONCURRENTLY` must run outside explicit transaction blocks. Migration runners that unconditionally wrap every script in `BEGIN`/`COMMIT` will fail.

Structure migrations to separate transactional and non-transactional steps, track checkpoints, handle retries, clean up `INVALID` leftovers, and monitor progress.

### 13.4. Plan for Future Partitions Too

Once a parent index is valid, newly created partitions automatically inherit matching child indexes via standard DDL. Ensure deployment pipelines verify future partitions receive **every required index**, not just existing historical ones.

## 14. Locks on Parents and Children: What Gets Locked?

PostgreSQL manages locks at relation, transaction, and tuple levels. With partitioning, operations can involve both **parent** and **child relations**.

### 14.1. Reading One Partition

```sql
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

A regular `SELECT` acquires `ACCESS SHARE` locks on the relations actually accessed. Which child relations are locked depends on plan shape and when pruning occurs.

**Never assume a parent `SELECT` always locks every partition or always locks strictly one partition.** Pruning stage (plan-time vs. init-time vs. per-loop), plan structure, and server version all affect locking.

### 14.2. Writing to One Partition

```sql
INSERT INTO part_eval_lab.sales (
    sold_on, tenant_id, status, amount, note
) VALUES (
    DATE '2026-02-15', 50, 'PAID', 100.00, 'lab'
);
```

PostgreSQL routes the row to February, acquiring appropriate write locks on the relevant relations (parent and target leaf under PostgreSQL's lock rules).

Never assume that because a write targets only one child, parent DDL cannot contend with writers.

### 14.3. Updating the Partition Key Can Move Rows

```sql
BEGIN;

UPDATE part_eval_lab.sales
SET sold_on = DATE '2026-03-01'
WHERE sold_on = DATE '2026-02-15'
  AND tenant_id = 50;

ROLLBACK;
```

When an `UPDATE` alters the partition key so the row maps to a different partition, PostgreSQL executes cross-partition **row movement**, logically deleting from the source leaf and inserting into the destination leaf.

Consequences:

- Acquires locks on both source and destination partitions.
- Interacts with foreign keys, triggers, and constraints.
- Can trigger concurrent update conflicts or serialization errors under concurrency.
- Never run unmeasured mass partition-key updates as a routine reorganization tactic.

The example wraps the update in `BEGIN`/`ROLLBACK` to preserve lab data; broad `WHERE` clauses can match many rows, so keep tests out of production.

### 14.4. Partition-Level Locking Does Not Eliminate All Contention

Even though January and February have separate heaps, DDL on the parent still acquires parent locks, and maintenance targeting February still contends with queries touching February.

Partitioning isolates many operations, **without guaranteeing total workload independence**.

## 15. Two-Session Experiment: Locking a Single Partition

Goal: observe lock waits **strictly in the lab**. Open two or three independent sessions and check their PIDs:

```sql
SELECT pg_backend_pid();
```

### 15.1. Session A Locks February

```sql
BEGIN;

LOCK TABLE part_eval_lab.sales_2026_02
IN ACCESS EXCLUSIVE MODE;

-- Leave transaction open to observe lock behavior.
```

`ACCESS EXCLUSIVE` conflicts with every lock mode, including `ACCESS SHARE` taken by ordinary `SELECT`s on that relation.

### 15.2. Session B Attempts to Read February

```sql
BEGIN;

SET LOCAL lock_timeout = '3s';

SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

Because Session B needs an incompatible lock on `sales_2026_02`, it blocks and aborts upon hitting `lock_timeout`.

### 15.3. Session C Inspects Waiters

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST, a.pid;
```

To inspect exact relation locks:

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted,
    l.waitstart
FROM pg_locks AS l
WHERE l.locktype = 'relation'
  AND l.relation IN (
      SELECT relid
      FROM pg_partition_tree(
          'part_eval_lab.sales'::regclass
      )
  )
ORDER BY l.pid NULLS LAST, l.granted, relation_name;
```

### 15.4. Session A Releases the Lock

```sql
ROLLBACK;
```

If Session B timed out into an aborted transaction state, clear it as well:

```sql
ROLLBACK;
```

### 15.5. Test Querying January Independently

While Session A holds the lock on February, run a January query in another session with clear literals enabling **plan-time pruning of February**:

```sql
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-01-01'
  AND sold_on <  DATE '2026-02-01';
```

Depending on plan and version, it **can avoid locking February** and proceed unblocked. However, locks on the parent or late execution-time pruning can change behavior.

**Never rely blindly on "separate partitions never block one another." Inspect `pg_locks` directly.**

## 16. `ATTACH PARTITION`: Attaching Partitions Can Scan and Lock

Alongside `CREATE TABLE ... PARTITION OF`, PostgreSQL provides:

```sql
ALTER TABLE part_eval_lab.sales
ATTACH PARTITION part_eval_lab.sales_2026_05
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

The table being attached must **already exist**, share compatible structure/constraints, and contain only valid rows. The command above is syntax-only unless you created `sales_2026_05` first.

### 16.1. Why Is ATTACH Not Purely Metadata-Only?

When attaching an existing table, PostgreSQL must prove all existing rows satisfy the new bounds. Without valid constraint proof, it **scans the attached table** to verify every row.

If a `DEFAULT` partition exists, PostgreSQL must also verify `DEFAULT` holds **zero rows** falling in the new bounds, potentially scanning and locking `DEFAULT`.

### 16.2. Lock Modes to Evaluate

On PostgreSQL versions supporting declarative partitioning:

- `ALTER TABLE ... ATTACH PARTITION` generally needs only **`SHARE UPDATE EXCLUSIVE` on the parent** (far less blocking than `ACCESS EXCLUSIVE`).
- The table being attached typically requires **`ACCESS EXCLUSIVE`**.
- `DEFAULT` may be locked and scanned to verify it holds no overlapping rows.

Exact lock modes depend on PostgreSQL version, schema constraints, and `DEFAULT` state; verify against your target version when building production runbooks.

### 16.3. A Validated `CHECK` Constraint Avoids Full Validation Scans

When the standalone table carries a **validated `CHECK` constraint** proving all rows satisfy the new bounds, PostgreSQL skips the validation scan during attach.

Conceptual example for May:

```sql
ALTER TABLE part_eval_lab.sales_2026_05
ADD CONSTRAINT sales_2026_05_bounds_check
CHECK (
    sold_on >= DATE '2026-05-01'
    AND sold_on < DATE '2026-06-01'
);
```

Run this **after** creating `sales_2026_05` with matching schema. For large populated staging tables, adding/validating the `CHECK` also scans and locks, so finish validation **ahead of the attach window**.

### 16.4. A `DEFAULT` Partition Complicates Attach

If `sales_default` already holds May rows, attaching a May partition fails because `DEFAULT` violates the new disjointness invariant.

You must:

1. Inspect `DEFAULT` rows matching the new month's bounds.
2. Move matching rows cleanly into the staging table / target partition.
3. Verify constraints and active writers.
4. Coordinate ingestion so new May rows do not keep entering `DEFAULT` mid-migration.
5. Attach only once bounds, `DEFAULT` cleanliness, and lock windows are satisfied.

Never delete rows from `DEFAULT` just to unblock `ATTACH` unless retention allows discarding them.

### 16.5. Pre-Create Partitions Before Data Arrives

In monthly tables, pre-create future partitions **ahead** of rollover to prevent:

- `INSERT`s failing with "no partition found."
- Rows spilling into `DEFAULT` and requiring cleanup migrations.
- Running emergency DDL under peak production traffic.

Maintain a pre-creation schedule paired with alerts whenever the upcoming period's partition is missing.

## 17. Direct Creation vs. Standalone `ATTACH`: Two Distinct Workflows

### 17.1. Directly Creating an Empty Partition

When you just need next month's empty table with no external preload:

```sql
CREATE TABLE part_eval_lab.sales_2026_05
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

This modifies the parent partition hierarchy directly and takes a strong parent lock per `CREATE TABLE ... PARTITION OF` rules, so schedule during an appropriate window.

**Note:** if `DEFAULT` already holds May rows, direct creation also collides until overlapping data/constraints are resolved.

### 17.2. Staging a Standalone Table Followed by `ATTACH`

Alternative workflow:

```text
Create standalone table with matching schema
    |
Bulk-load data (if needed)
    |
Build indexes and CHECK constraints
    |
VALIDATE data and bounds
    |
ALTER TABLE parent ATTACH PARTITION standalone
    |
Verify tree, data, and indexes
```

This keeps expensive loading, indexing, and validation off the live tree so the final `ATTACH` lock window stays short.

### 17.3. Never Run Both Workflows for the Same Table Name

Once you run:

```sql
CREATE TABLE part_eval_lab.sales_2026_05
PARTITION OF part_eval_lab.sales ...;
```

that table **is already a partition**—you cannot attach it again as a standalone table.

Conversely, `ATTACH PARTITION` requires an existing unattached table ready to join that parent.

### 17.4. Production DDL Demands Real Lock Awareness

Optimizing `ATTACH` means more than skipping validation scans:

- Bound lock wait times.
- Minimize lock hold duration.
- Protect concurrent `INSERT` and `SELECT` traffic.
- Verify indexes, constraints, and foreign keys.
- Never assume every partition attach succeeds unconditionally under heavy concurrency.

## 18. `DETACH PARTITION` and `DETACH ... CONCURRENTLY`

Detaching removes a partition from the parent tree while keeping the child **intact as a standalone table**.

Example:

```sql
ALTER TABLE part_eval_lab.sales
DETACH PARTITION part_eval_lab.sales_2026_01;
```

After detaching:

- Queries through the parent no longer return rows from that detached table.
- `sales_2026_01` can still be queried directly.
- Its indexes and stored rows remain untouched until dropped or moved.

### 18.1. Regular `DETACH` Takes Heavy Locks

Non-concurrent `ALTER TABLE ... DETACH PARTITION` requires strong locks on the parent and blocks concurrent traffic. Measure contention carefully on busy systems.

### 18.2. `DETACH CONCURRENTLY`

Supported PostgreSQL versions allow:

```sql
ALTER TABLE part_eval_lab.sales
DETACH PARTITION part_eval_lab.sales_2026_01
CONCURRENTLY;
```

This reduces blocking using a multi-phase detach taking a weaker parent lock than regular `DETACH`.

**Critical limitations:**

- Cannot run `DETACH ... CONCURRENTLY` inside an explicit transaction block.
- Has hierarchy restrictions, notably **when a `DEFAULT` partition exists**.
- Still waits for older transactions referencing the tree to finish.
- If interrupted mid-way, leaves a **pending detach** state requiring version-specific recovery such as `FINALIZE`.

Never assume adding `CONCURRENTLY` makes detaching instant or lock-free.

### 18.3. Our Lab Currently Has a `DEFAULT` Partition

Because our lab created `sales_default`, **do not blindly run the `DETACH CONCURRENTLY` snippet directly on it**. Check your PostgreSQL version's rules and test concurrent detach on a separate lab hierarchy without `DEFAULT`.

### 18.4. `DETACH` Is Not `DROP`

- **`DETACH`**: removes parent-child membership, preserving the physical table and data.
- **`DROP TABLE child`**: permanently destroys the table and its data.
- **`TRUNCATE child`**: empties rows while preserving the table shell.
- **`DROP TABLE parent`**: destroys the entire parent and dependent hierarchy—never use it to clean a single month.

Keeping these distinct drives proper archival and retention engineering.

## 19. Partition Retention: Retiring Old Months Without Row-by-Row `DELETE`

For monthly logs, rather than running:

```sql
DELETE FROM part_eval_lab.sales
WHERE sold_on < DATE '2026-02-01';
```

on massive tables, evaluate **detaching/dropping old partitions** on an approved retention schedule.

### 19.1. Why Can `DELETE` Be So Expensive?

Deleting millions of rows causes:

- Massive WAL generation.
- Millions of dead tuples.
- Heavy `VACUUM` workload.
- Index bloat and maintenance cost.
- Long transaction locks and contention.
- Replication lag and I/O spikes.

### 19.2. Partition-Level Retention Workflow

Typical pipeline:

```text
Identify month eligible for retirement
    |
Verify cutoff date, timezone, and compliance retention rules
    |
Check late-arriving writes and external dependencies
    |
Back up or export to archive storage if required
    |
DETACH PARTITION (if keeping standalone intermediate stage)
    |
Confirm parent queries no longer surface old rows
    |
DROP standalone table once approved
    |
Verify stats, monitoring, disk space, and replication
```

### 19.3. `DETACH` Does Not Immediately Reclaim Storage

Once detached, the table and its indexes still occupy disk. Space is reclaimed only after executing an approved purge or moving data off the instance.

To reduce database disk usage, follow up with a controlled `DROP TABLE` **only after** meeting backup and compliance requirements.

### 19.4. Dropping a Partition Is Destructive

```sql
-- ILLUSTRATIVE ONLY; do not run blindly on production:
DROP TABLE part_eval_lab.sales_2026_01;
```

This destroys the partition, its indexes, and dependent objects per `DROP` rules. Never run in production without approvals, checkpoints, verified backups, and dependency checks.

### 19.5. Late-Arriving Data

If January was dropped yet an API inserts `sold_on = '2026-01-15'` later:

- With `DEFAULT` present and unguarded, the row lands quietly in `DEFAULT`.
- Without a matching partition or `DEFAULT`, the `INSERT` fails.
- Retrying ETL pipelines may spin indefinitely.

Retention therefore requires an explicit **late-data policy**: reject, quarantine, route to archive pipelines, or reopen under controlled processes.

### 19.6. Replication, Backups, and Downstream Dependencies

`DROP`/`DETACH` DDL impacts downstream systems, replicas, backups, and analytics. Verify:

- Streaming and logical replication behavior.
- Backup and PITR windows.
- Foreign keys and view dependencies.
- Data lake/export pipelines.
- Historical reporting tools.
- Compliance holds and retention mandates.

Having monthly partitions alone does not make auto-dropping old months safe.

## 20. Locking During Partition Maintenance: Planning Timeouts

Maintenance DDL can block behind active queries—and queue up incoming `SELECT`s/`INSERT`s behind itself.

### 20.1. Set Timeouts Inside Transactional DDL

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

-- Illustrative transactional DDL in lab:
-- ALTER TABLE ... ATTACH PARTITION ...;

ROLLBACK;
```

`lock_timeout` caps how long DDL waits for locks; `statement_timeout` caps overall command duration.

If DDL cannot acquire locks within budget, **abort cleanly and retry with backoff** instead of stalling production traffic indefinitely.

### 20.2. For `CONCURRENTLY` Commands Outside Transactions

Commands like `CREATE INDEX CONCURRENTLY` and `DETACH PARTITION CONCURRENTLY` cannot execute inside explicit transaction blocks.

To bound timeouts, configure `lock_timeout`/`statement_timeout` at the **session/driver/role** scope and reset them afterward.

Never execute `SET LOCAL` outside a transaction expecting it to carry over into a subsequent autocommit `CONCURRENTLY` command.

### 20.3. Watch Out for `idle in transaction` Sessions

A client that opens a transaction, reads or writes, and forgets to commit/rollback holds locks and snapshots open indefinitely, blocking partition DDL.

Inspect with:

```sql
SELECT
    pid,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Never terminate a backend purely because `xact_age` looks large; identify the user, application, held locks, and business impact first.

## 21. Identifying Who Is Blocking Partition DDL

### 21.1. Query Waiters and Blockers

```sql
SELECT
    w.pid AS waiting_pid,
    w.application_name AS waiting_app,
    w.state AS waiting_state,
    w.wait_event_type,
    w.wait_event,
    w.query AS waiting_query,
    b.pid AS blocking_pid,
    b.application_name AS blocking_app,
    b.state AS blocking_state,
    b.xact_start AS blocking_xact_start,
    b.query AS blocking_last_query
FROM pg_stat_activity AS w
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(w.pid)) AS p(blocking_pid)
LEFT JOIN pg_stat_activity AS b
  ON b.pid = p.blocking_pid
WHERE w.datname = current_database()
ORDER BY w.pid, b.pid;
```

`pg_blocking_pids` reports the exact backends blocking a waiter inside the lock manager, including lock-queue dependencies. Never try inferring root blockers manually from two isolated `pg_locks` rows.

### 21.2. Query Relation Locks Across Parent and Leaves

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted,
    l.waitstart,
    a.application_name,
    a.state,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.locktype = 'relation'
  AND l.database = (
      SELECT oid
      FROM pg_database
      WHERE datname = current_database()
  )
  AND l.relation IN (
      SELECT relid
      FROM pg_partition_tree(
          'part_eval_lab.sales'::regclass
      )
  )
ORDER BY l.granted, l.waitstart NULLS LAST, relation_name;
```

Check:

- `relation_name`: parent or specific leaf partition.
- `mode`: requested or held lock mode.
- `granted`: `true` if held, `false` if waiting.
- `waitstart`: timestamp wait started.
- `application_name`, `state`: owning client context.

### 21.3. Look Beyond Relation Locks Alone

An `UPDATE` can wait on a `transactionid` lock held by another session modifying the same tuple. `pg_locks` does not expose every row lock continuously like explicit `tuple` entries.

When writes stall, correlate:

- `pg_blocking_pids`.
- `pg_stat_activity`.
- Relation and `transactionid` lock views.
- Recent DDL history and transaction age.

### 21.4. Never Mass-Cancel or Terminate Sessions

When DDL blocks, do **not** reflexively run:

```sql
-- DO NOT run in production:
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'active';
```

That kills legitimate transactions indiscriminately and triggers retry storms. Prefer bounding DDL with `lock_timeout`, coordinating with session owners, or terminating only verified runaway backends with proper authorization.

## 22. How Index Builds and `VACUUM` Interact with DDL

Maintenance commands carry distinct lock profiles:

| Operation | Operational Impact |
| --- | --- |
| Regular `SELECT` | Takes read locks; conflicts with strong DDL locks |
| `INSERT`/`UPDATE`/`DELETE` | Takes write locks on parent/leaves; contends with maintenance/DDL |
| Regular `CREATE INDEX` | Blocks concurrent writes and holds locks throughout build |
| `CREATE INDEX CONCURRENTLY` on leaf | Minimizes write blocking, yet involves multiple wait phases and limits |
| Regular `VACUUM` | Reclaims dead tuples with low-impact lock modes suitable for live traffic |
| `VACUUM FULL` | Rewrites entire relation under exclusive lock; heavily disruptive |
| `ATTACH PARTITION` | May scan/validate and lock parent, child, and `DEFAULT` |
| `DETACH PARTITION` | Strong locks in regular mode; `CONCURRENTLY` has strict restrictions |
| `DROP TABLE` partition | Destroys relation and data permanently |

Good maintenance plans minimize **lock wait queues and live workload disruption**, not just raw command runtime.

### 22.1. Why Can `CREATE INDEX CONCURRENTLY` Still Block or Stall?

`CONCURRENTLY` does not mean "zero locks," "zero I/O," or "zero waiting." It executes multiple scan phases synchronized against active snapshots and can take a long time.

### 22.2. Why Is `VACUUM FULL` Riskier Than Regular `VACUUM`?

`VACUUM FULL` rewrites the table to compact OS file size while holding an `ACCESS EXCLUSIVE` lock. Never schedule it reflexively on active partitions.

### 22.3. Maintenance Windows Still Matter with Partitioning

A huge leaf partition still needs serious maintenance resources. Even if other partitions serve unaffected reads, parent DDL or queries hitting that leaf can still feel the impact.

Classify **hot active partitions** separately from **quiet historical partitions** to tailor maintenance schedules.

## 23. Per-Partition `VACUUM`

MVCC creates tuple versions. `UPDATE` and `DELETE` leave behind dead tuples requiring `VACUUM` cleanup once no older snapshot needs them.

### 23.1. Inspect Per-Partition Tuple Stats

```sql
SELECT
    relid::regclass AS partition_name,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'part_eval_lab'
  AND relname LIKE 'sales_2026_%'
ORDER BY relname;
```

`n_live_tup` and `n_dead_tup` are statistical estimates/counters, not exact snapshot row counts.

### 23.2. Vacuum a Leaf with High Dead Tuples

```sql
VACUUM (ANALYZE) part_eval_lab.sales_2026_02;
```

This targets only the February leaf; never assume it cleans sibling partitions.

**Never run `VACUUM` inside an explicit transaction block.**

### 23.3. Primary Effects of Regular `VACUUM`

Regular `VACUUM`:

- Marks dead-tuple space reusable inside the relation per MVCC rules.
- Updates the visibility map and free space map.
- Enables `Index Only Scan`s to skip heap fetches on all-visible pages.
- Advances `relfrozenxid` to prevent transaction ID wraparound.
- Cleans up index entries pointing to dead heap tuples.

It generally does not return file blocks immediately to the OS. When evaluating bloat, distinguish **reusable free space inside relation pages** from **physical file size on disk**.

### 23.4. Old Partitions Still Need Freeze Policies

Quiet historical partitions generate few dead tuples, yet still age toward transaction ID wraparound and require timely freezing.

Never disable autovacuum across historical partitions "because the data never changes" without a verified freeze/vacuum strategy.

### 23.5. Long Transactions Block `VACUUM` Cleanup

An old open transaction or replication slot with an active `xmin` prevents `VACUUM` from reclaiming dead tuples newer than that horizon—even on unrelated tables.

When `n_dead_tup` climbs persistently, check transaction ages, replication slots, and snapshots before merely tweaking autovacuum scale factors.

## 24. `ANALYZE`: Both Parent and Child Statistics Matter

Partitioned tables carry two levels of planner estimates:

1. **Per-partition statistics** used to pick scans/joins inside each leaf.
2. **Parent/inheritance statistics** used when planning queries spanning multiple partitions.

### 24.1. `ANALYZE` the Parent

```sql
ANALYZE part_eval_lab.sales;
```

On supported PostgreSQL releases, this collects hierarchical parent summary stats alongside leaf partition statistics.

### 24.2. Autovacuum and Partitioned Parents

A key operational detail: partitioned parent tables **store zero heap tuples directly**, so autovacuum/autoanalyze do not trigger automatically on a parent the same way they do on normal heap tables. Heavy writes inside children **do not automatically trigger auto-`ANALYZE` on the parent**.

Therefore, after major data shifts across partitions, schedule explicit **periodic/post-load `ANALYZE` on the parent** rather than assuming stats refresh automatically.

Leaf partitions still receive normal autovacuum and autoanalyze based on their own heap changes.

### 24.3. Check `last_analyze` and `last_autoanalyze`

```sql
SELECT
    relid::regclass AS relation_name,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname = 'part_eval_lab'
  AND relname LIKE 'sales%'
ORDER BY relname;
```

These columns track counter timestamps—they do not prove stats accurately model correlated multi-column predicates.

### 24.4. When Should You Re-Run `ANALYZE`?

- After bulk-loading a new partition.
- After migrating rows out of `DEFAULT` into a new partition.
- After major tenant or status distribution shifts.
- After attaching/detaching partitions in the hierarchy.
- Whenever `EXPLAIN` shows severe estimated vs. actual row mismatches.
- After sudden volume spikes inside a leaf.

### 24.5. Do Not Run Full-Tree `ANALYZE` After Every Small `INSERT`

`ANALYZE` consumes sampling I/O, CPU, and catalog work. Trigger it after bulk batches, during off-peak windows, or on volume thresholds—just frequently enough to keep plans accurate.

## 25. Measuring Plan Changes After Adding a Partition

### 25.1. Capture Baseline Before Changes

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

Record:

- Child nodes and partition names.
- Estimated vs. actual rows.
- Shared buffer hits/reads.
- Planning Time and Execution Time.
- Query parameters.
- PostgreSQL version and active indexes.

### 25.2. Apply the Change in the Lab

For example, add May (assuming `DEFAULT` holds no May rows):

```sql
CREATE TABLE part_eval_lab.sales_2026_05
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

### 25.3. Refresh Stats as Needed

```sql
ANALYZE part_eval_lab.sales;
```

### 25.4. Re-Run the February Query

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

With proper pruning, adding May does not cause February queries to touch May.

### 25.5. Watch for Planning Overhead Growth

At thousands of partitions, catalog lookup and planner path-enumeration overhead can grow even when execution pruning eliminates nearly all children.

Always measure **Planning Time separately from Execution Time** rather than looking solely at total warm-cache latency.

## 26. When Do Too Many Partitions Hurt Performance?

Switching from **monthly** to **daily** partitions multiplies partition count by roughly 30× over the same retention window.

Consequences include:

- Far more catalog objects.
- Far more local index structures.
- Higher planning overhead.
- Complex maintenance scheduling.
- More metadata and locking work during DDL.
- Inefficient handling of tiny partitions.
- Heavier backup, monitoring, and permission management.

### 26.1. There Is No Fixed Universal Cutoff

There is no rule saying "100 partitions is great, 101 is fatal."

The right partition count depends on:

- Data volume per partition.
- Fraction of queries filtering on the partition key.
- Retention window length.
- Index count per table.
- Pruning efficiency.
- PostgreSQL version.
- Memory and concurrency levels.
- Attach/detach/reindex frequency.

### 26.2. Align Granularity with Queries and Retention

If most queries filter 3-day windows, monthly partitioning combined with a date index inside each monthly partition often works wonderfully.

If daily volume is huge and retention runs daily, daily partitions make sense.

If overall volume is modest, daily partitioning just creates thousands of tiny tables unnecessarily.

### 26.3. More Partitions Do Not Replace Indexes

A query filtering a specific tenant inside January still benefits from a local index after pruning down to January. Partition granularity and index design solve distinct problems.

## 27. `enable_partitionwise_join`: Joining Partition Pairs Locally

When two tables share compatible partitioning schemes and join conditions include the partition keys under supported rules, PostgreSQL can perform a **partitionwise join**.

### 27.1. Concept

```text
sales (Jan, Feb, Mar)       sale_tags (Jan, Feb, Mar)
       |                            |
       +-- Jan sales  JOIN Jan tags-+
       +-- Feb sales  JOIN Feb tags-+
       +-- Mar sales  JOIN Mar tags-+
                 |
               Append
```

Instead of joining two giant combined sets globally, matching monthly pairs join independently.

### 27.2. Companion Table with Identical Partitioning

In the lab:

```sql
CREATE TABLE part_eval_lab.sale_tags (
    sale_id bigint NOT NULL,
    sold_on date NOT NULL,
    tag text NOT NULL
) PARTITION BY RANGE (sold_on);

CREATE TABLE part_eval_lab.sale_tags_2026_01
PARTITION OF part_eval_lab.sale_tags
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE part_eval_lab.sale_tags_2026_02
PARTITION OF part_eval_lab.sale_tags
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE part_eval_lab.sale_tags_2026_03
PARTITION OF part_eval_lab.sale_tags
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE part_eval_lab.sale_tags_2026_04
PARTITION OF part_eval_lab.sale_tags
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
```

Populate sample tags:

```sql
INSERT INTO part_eval_lab.sale_tags (
    sale_id, sold_on, tag
)
SELECT
    sale_id, sold_on, 'reviewed'
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-01-01'
  AND sold_on <  DATE '2026-05-01'
  AND sale_id % 100 = 0;

ANALYZE part_eval_lab.sale_tags;
```

### 27.3. Compare Plans

```sql
BEGIN;

SET LOCAL enable_partitionwise_join = on;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    s.sold_on,
    COUNT(*) AS tagged_sales
FROM part_eval_lab.sales AS s
JOIN part_eval_lab.sale_tags AS t
  ON t.sold_on = s.sold_on
 AND t.sale_id = s.sale_id
WHERE s.sold_on >= DATE '2026-02-01'
  AND s.sold_on <  DATE '2026-04-01'
GROUP BY s.sold_on;

ROLLBACK;
```

The join condition includes equality on `sold_on`, the partition key of both tables.

### 27.4. Why Might Partitionwise Join Not Be Chosen?

The planner compares costs and partition compatibility strictly. If `sale_tags` is tiny, a single global hash join can still be cheaper.

`enable_partitionwise_join = on` **allows the planner to consider it**, never forcing it unconditionally.

### 27.5. Memory Warning

Partitionwise joins generate separate join/hash/sort nodes per partition pair, multiplying memory footprints across many partitions.

Never enable the flag globally just because "partitionwise" sounds faster.

## 28. `enable_partitionwise_aggregate`: Per-Partition Aggregation

Eligible queries can aggregate data independently per partition before combining results.

### 28.1. Daily Aggregation Query

```sql
BEGIN;

SET LOCAL enable_partitionwise_aggregate = on;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    sold_on,
    COUNT(*) AS sales_count,
    SUM(amount) AS total_amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-01-01'
  AND sold_on <  DATE '2026-05-01'
GROUP BY sold_on;

ROLLBACK;
```

Because `sold_on` is both the partition key and the `GROUP BY` key, groups cannot span multiple monthly partitions.

### 28.2. Partial/Final Aggregation

Depending on compatibility and cost, the planner may pick:

- Full aggregate per child followed by `Append`.
- Partial aggregate per child followed by `Append` and Finalize aggregate.
- A single aggregate above `Append`.
- A parallel aggregation strategy.

### 28.3. Not Every Grouping Completes Partition-Locally

`GROUP BY tenant_id` allows the same tenant to appear in multiple months. Partial per-partition aggregates still require a final aggregation step to combine each tenant across months.

Never assume "GROUP BY on a partitioned table always isolates every group inside a single partition."

### 28.4. More Aggregate Nodes Mean Higher Overhead

Creating many hash/sort aggregate states across numerous partitions increases memory usage and planning cost. Benchmark carefully—especially when partition counts are high.

## 29. Measuring Storage Accurately

### 29.1. Mistake: Measuring Only the Parent

```sql
SELECT pg_size_pretty(
    pg_total_relation_size(
        'part_eval_lab.sales'::regclass
    )
);
```

This **never reflects total child storage**, because the partitioned parent holds no heap rows for its leaves.

### 29.2. Measure Each Leaf Individually

```sql
SELECT
    p.relid::regclass AS partition_name,
    pg_size_pretty(
        pg_relation_size(p.relid)
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size(p.relid)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size(p.relid)
    ) AS total_size
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
) AS p
WHERE p.isleaf
ORDER BY p.relid::regclass::text;
```

`pg_total_relation_size` on each leaf covers heap, indexes, and TOAST storage.

### 29.3. Total Across the Tree

```sql
SELECT
    pg_size_pretty(
        SUM(pg_total_relation_size(p.relid))
    ) AS total_leaf_storage
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
) AS p
WHERE p.isleaf;
```

This sums all **currently attached leaves** at query time.

### 29.4. `DETACH` Shrinks Parent Tree Totals Without Freeing Disk

Once January is detached, `pg_partition_tree('...sales')` omits it, so tree storage totals drop—yet the standalone January table still occupies disk until dropped or moved.

Never cite "tree storage dropped" as proof disk space was freed.

### 29.5. Account for Tablespaces, Replicas, and Storage Layers

Relation sizes inside PostgreSQL exclude total disk consumed by backups, WAL archives, replicas, and filesystem snapshots. Evaluate real storage impact across every infrastructure layer.

## 30. Tracking Scans, Index Usage, and Dead Tuples per Partition

### 30.1. `Seq Scan` and `Index Scan` Counters

```sql
SELECT
    relid::regclass AS relation_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'part_eval_lab'
  AND relname LIKE 'sales%'
ORDER BY relname;
```

Meaning:

- `seq_scan`: number of sequential scans recorded.
- `seq_tup_read`: tuples read via sequential scans.
- `idx_scan`: number of index scans initiated.
- `idx_tup_fetch`: heap tuples fetched by index scans.
- `n_live_tup` / `n_dead_tup`: estimated live and dead tuples.

### 30.2. High Index-Scan Ratio Is Not the Only KPI

If January reporting reads 80% of that month's rows, sequential scans are entirely appropriate. A high `seq_scan` count alone does not prove an index is missing.

Examine slow queries and `EXPLAIN`. Repeatedly calling an `Index Scan` inside a huge nested loop can easily be slower than scanning cleanly.

### 30.3. Index Usage

```sql
SELECT
    relid::regclass AS table_name,
    indexrelid::regclass AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'part_eval_lab'
ORDER BY relid::regclass::text, indexrelid::regclass::text;
```

Zero or low `idx_scan` **does not automatically prove an index is unused**: it may enforce a unique constraint or support rare yet critical end-of-month audits.

### 30.4. I/O Statistics

```sql
SELECT
    relid::regclass AS relation_name,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_tables
WHERE schemaname = 'part_eval_lab'
  AND relname LIKE 'sales%'
ORDER BY relname;
```

These cumulative counters span the stats tracking interval; record baselines and timestamps when comparing, never mistaking them for single-query metrics.

### 30.5. Stats Lag and Access Privileges

Stats views are cumulative estimates rather than instant transactional metrics. They can lag, reset, or be restricted by role grants. Correlate trends with `EXPLAIN` and external telemetry.

## 31. Monitoring Active `VACUUM` Operations

`pg_stat_progress_vacuum` tracks running vacuums on supported versions:

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum
WHERE datname = current_database()
ORDER BY pid;
```

A `VACUUM` running on February displays February's leaf `relid`, not a shared parent heap.

### 31.1. Do Not Confuse Vacuum Progress with Reclaimed OS Disk Space

Progress tracks scan/cleanup completion, not filesystem shrinkage.

### 31.2. Separate Index Build Progress

During index creation, inspect `pg_stat_progress_create_index` on supported versions. Remember `CONCURRENTLY` adds extra synchronization phases and snapshot waits.

### 31.3. Autovacuum Across Numerous Partitions

Hot active partitions receiving constant updates may need tighter autovacuum/autoanalyze thresholds than quiet historical partitions. Per-relation `reloptions` allow tuning, though avoid tuning hundreds of tables inconsistently without automation.

## 32. Customizing Autovacuum for Hot Partitions

PostgreSQL allows per-relation autovacuum settings.

Illustrative example for February:

```sql
ALTER TABLE part_eval_lab.sales_2026_02
SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02
);
```

These values are **illustrative only**, not universal tuning defaults.

### 32.1. Why Separate Hot vs. Cold Partitions?

An active partition taking heavy `INSERT`/`UPDATE` traffic builds dead tuples quickly and needs frequent stat refreshes.

A closed historical partition sees minimal churn, yet still needs wraparound freeze maintenance per cluster age policies.

### 32.2. Inspect Per-Child Settings

```sql
SELECT
    oid::regclass AS relation_name,
    reloptions
FROM pg_class
WHERE oid IN (
    SELECT relid
    FROM pg_partition_tree(
        'part_eval_lab.sales'::regclass
    )
)
ORDER BY oid::regclass::text;
```

### 32.3. Never Disable Autovacuum Blindly

Turning off autovacuum on partitions "to save CPU" invites dead-tuple bloat, stale statistics, and transaction ID wraparound emergencies.

To reduce load safely, tune vacuum cost limits, schedules, or worker counts deliberately while monitoring every partition.

### 32.4. Parent `ANALYZE` Still Requires Attention

Tuning child autovacuum does not guarantee fresh parent inheritance statistics. Schedule periodic parent `ANALYZE` after major hierarchy shifts.

## 33. Bloat, `REINDEX`, and Why Smaller Partitions Don't Eliminate MVCC Overhead

### 33.1. Bloat Occurs Inside Individual Leaves

A partition receiving heavy updates/deletes develops heap and index bloat locally. Partitioning bounds the blast radius per relation—it does not suspend MVCC mechanics.

### 33.2. Index Maintenance

When bloat degrades scans or indexes require repair, evaluate `REINDEX` on specific **child indexes** using lock/concurrent options supported by your version.

Illustrative example:

```sql
-- Illustrative only; verify real index name and PostgreSQL version:
REINDEX INDEX CONCURRENTLY
part_eval_lab.some_child_index;
```

Do not execute on the non-existent placeholder `some_child_index`. `REINDEX ... CONCURRENTLY` has version-specific limits and cannot run inside an explicit transaction block.

### 33.3. Never Blindly Reindex All Partitions on a Cron

Reindexing fresh, unbloated indexes just wastes I/O, generates extra WAL, and causes lock contention.

Only reindex when backed by:

- Measurable bloat or degradation evidence.
- Index size and build duration estimates.
- Lock, concurrency, and rollback planning.
- Monitoring for replication lag and free disk headroom.

### 33.4. `VACUUM FULL` Is Not a Monthly Cleanup Routine

`VACUUM FULL` rewrites the relation with extra scratch disk space and an exclusive lock. Never confuse it with retiring an expired historical partition via `DETACH`/`DROP`.

## 34. Multi-Partition Queries and Cardinality Misestimation

Partitioning adds estimation layers for the planner:

- How many partitions remain relevant.
- Row counts per partition.
- Predicate selectivity per child.
- Overall data skew.
- Placement of joins, aggregates, and sorts.

### 34.1. Hot Tenant Without a Date Filter

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE tenant_id = 1;
```

Lacking a `sold_on` predicate, the planner must inspect every partition.

### 34.2. Selective Tenant Within February

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_on, tenant_id, amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
  AND tenant_id = 321;
```

Prunes down to February and leverages the local index cleanly.

### 34.3. Inter-Partition Skew

Tenant 1 may represent 90% of one month and only 10% of another. Parent-level aggregate stats alone cannot capture per-partition skew.

Inspect estimated vs. actual rows on individual child nodes rather than glancing solely at the top `Append`.

### 34.4. Prepared Statements and Generic Plans

A parameterized query:

```sql
WHERE sold_on >= $1
  AND sold_on < $2
  AND tenant_id = $3
```

can prune months at execution time, yet generic plans still pick fixed inner scan paths without seeing skewed `$3` values.

Runtime partition pruning **does not solve parameter-skewed index selectivity** inside surviving partitions.

### 34.5. Fresh Stats Do Not Force Index Usage

`ANALYZE` gives the planner accurate selectivity estimates; when a query reads most of a partition, `Seq Scan` legitimately beats `Index Scan`.

## 35. Reading `EXPLAIN` on Partitioned Tables: Key Fields

Use:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, VERBOSE)
SELECT
    sold_on,
    tenant_id,
    COUNT(*) AS sale_count,
    SUM(amount) AS total_amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-04-01'
GROUP BY sold_on, tenant_id;
```

### 35.1. Checklist of Plan Elements

| Element | Meaning |
| --- | --- |
| `Append` / `Merge Append` | Combines child result streams |
| `Parallel Append` | Schedules child plans across parallel workers |
| Partition names | Which child relations actually appear in the plan |
| `Subplans Removed` | Initialization-time pruning count when reported |
| `(never executed)` | Child node skipped during measured execution |
| `loops` | Execution iterations; key for per-loop pruning in joins |
| `Seq Scan` / `Index Scan` / `Bitmap Heap Scan` | Access path inside each surviving leaf |
| `Index Cond` / `Filter` | Index-pushed predicates vs. post-fetch tuple filters |
| `rows` / `actual rows` | Estimated vs. actual row counts |
| `Buffers: shared hit/read` | Page access counts per instrumentation |
| `Planning Time` | Planner cost—watch carefully at high partition counts |
| `Execution Time` | Server-side execution time inside `EXPLAIN` |
| `Settings` | Non-default planner parameters active |

### 35.2. `EXPLAIN ANALYZE` Executes the Statement

For `SELECT`, it executes the query while discarding final client row transmission.

For `INSERT`/`UPDATE`/`DELETE`, `EXPLAIN ANALYZE` **modifies data** inside the transaction.

To test DML plans safely in the lab:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE part_eval_lab.sales
SET status = 'PAID'
WHERE sold_on = DATE '2026-02-01'
  AND tenant_id = 321;

ROLLBACK;
```

Rollback reverts data changes, yet still executes I/O, WAL writes, and potential lock waits. Never treat `BEGIN...ROLLBACK` as a license to probe dangerous DML on production.

### 35.3. Buffers and Warm vs. Cold Cache

`shared hit` counts pages found in PostgreSQL shared buffers; `shared read` counts pages read from the OS (which may still be OS page-cache hits rather than physical disk seeks).

Repeat runs to separate cold-cache variance from warm-cache performance, documenting test conditions.

### 35.4. Planning Time Can Become the Bottleneck

At huge partition counts, execution after pruning can take milliseconds while `Planning Time` stretches far longer.

Evaluate **both planning and execution time**—especially for high-frequency OLTP queries.

## 36. Operational Runbook: Adding Next Month's Partition

Template runbook to adapt to your server version and platform:

### Before Month Rollover

1. **Verify exact date/month boundaries** and domain timezone.
2. Inspect the live tree with `pg_partition_tree`.
3. Check whether `DEFAULT` holds rows falling in the upcoming range.
4. Prepare child table, indexes, and constraints per chosen workflow.
5. Confirm actual DDL lock behavior on your PostgreSQL version.
6. Schedule during low traffic; set appropriate `lock_timeout`.
7. Prepare failure/rollback handling if `ATTACH`/`CREATE` aborts.
8. For non-transactional workflows, prepare checkpoints and cleanup steps.

### During Execution

```text
Confirm partition does not already exist
      |
      v
Check DEFAULT and late-arriving data overlap
      |
      v
CREATE PARTITION or ATTACH (pick one workflow)
      |
      v
Verify bounds, indexes, and constraints
      |
      v
Run ANALYZE as needed
      |
      v
Test INSERT/SELECT routing and EXPLAIN on new bounds
```

### Post-Execution

- Confirm writes route to the new child.
- Verify no lingering lock waits.
- Verify local indexes exist and are valid.
- Confirm monitoring and backups discover the new partition.
- Ensure retention jobs cannot accidentally drop the newly added future partition.
- Clear or update "missing next month" alerts.

## 37. Operational Runbook: Retiring an Old Partition

### Before Cleanup

1. Confirm business and legal retention cutoff.
2. Verify exact partition bounds in catalog—never trust table names alone.
3. Confirm no active writers still emit rows for that period.
4. Confirm alignment with late-arriving data policy.
5. Audit foreign keys, views, routines, and downstream consumers.
6. Verify backups, archives, and replication states.
7. Decide between `DETACH`, `DROP`, or read-only archival.
8. Inspect long transactions for DDL lock risk.
9. Configure `lock_timeout` and escalation/rollback steps.

### During Cleanup

If retaining a temporary standalone stage:

```text
DETACH -> confirm parent queries no longer see old rows
       -> export, reconcile, and archive if required
       -> DROP standalone table once approved
```

If dropping an attached leaf directly where authorized, account explicitly for parent locks and irreversible deletion.

### Post-Cleanup

- Parent queries omit the removed partition.
- Total attached leaf storage drops as expected.
- Actual filesystem/disk usage verified separately.
- Zero leftover pending detaches or `INVALID` indexes.
- No unexpected late `INSERT`s spilling into `DEFAULT`.
- Broad historical reports remain compliant with policy.

## 38. Decision Matrix: Matching Symptoms to Investigations

| Symptom | Do Not Rushedly | Investigate Instead |
| --- | --- | --- |
| February query still scans 12 partitions | Add random indexes | Inspect partition key predicate and pruning stage |
| Query reads only Feb yet runs slowly | Split into smaller partitions | Check scan/index/join inside Feb |
| Generic prepared plan lists many child nodes | Assume full-table scan | Check `Subplans Removed`, `loops`, and actual buffers |
| `WHERE date_trunc(...)` fails to prune | Disable `Seq Scan` | Rewrite as direct range bounds on partition key |
| Parent has index yet child scans slowly | Immediately build another index | Inspect child index health, stats, and selectivity |
| `ATTACH` takes too long | Kill every session | Check validation scan, `DEFAULT`, and lock graph |
| `DETACH` blocks behind old transactions | Terminate all backends | Inspect detach mode, long transactions, concurrent limits |
| `DEFAULT` holds new month's rows | Truncate/delete `DEFAULT` | Migrate/reconcile rows and add/validate bounds |
| Parent stats are stale | Reindex everything | Run `ANALYZE` on parent and leaves appropriately |
| Hot partition has high dead tuples | Run `VACUUM FULL` immediately | Inspect autovacuum tuning, long snapshots, regular `VACUUM` |
| Historical partition bloats on disk | Row-by-row `DELETE` | Check bloat vs. approved partition detach/drop retention |
| High partition count inflates `Planning Time` | Inflate `shared_buffers` blindly | Review partition granularity, joins, and index counts |
| Multi-partition join is slow | Flip all planner flags globally | Benchmark partitionwise join/aggregate and `work_mem` |
| Parent `CREATE INDEX` blocks writes | Abandon indexing | Use version-supported concurrent leaf-build + attach workflow |
| Old data reappears after retention | Drop extra tables blindly | Inspect `DEFAULT` and late-arriving ingestion paths |
| `pg_total_relation_size(parent)` looks tiny | Assume table is empty | Sum `pg_total_relation_size` across all leaves |
| DDL timeouts repeat frequently | Raise `lock_timeout` endlessly | Diagnose blocking sessions and adjust maintenance windows |

## 39. Practice Exercises with Answers

Use the `part_eval_lab` schema already built. Run destructive DDL, detach, drop, or heavy lock experiments **strictly on a lab copy**, never in production.

### Exercise 1. Does the parent store heap rows for all partitions?

**Answer:** No. A declarative partitioned parent is a logical relation; actual tuples live in leaf partitions. Measure total size across leaves.

### Exercise 2. List all partitions

```sql
SELECT relid::regclass, isleaf, level
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
);
```

**Answer:** Returns the parent at level 0 plus leaves Jan–Apr and `DEFAULT` (before any hierarchy edits).

### Exercise 3. Inspect February's exact bounds

```sql
SELECT pg_get_expr(c.relpartbound, c.oid)
FROM pg_class AS c
WHERE c.oid = 'part_eval_lab.sales_2026_02'::regclass;
```

**Answer:** Range from `2026-02-01` (inclusive) to `2026-03-01` (exclusive).

### Exercise 4. Why doesn't a February `SELECT` need to scan January?

**Answer:** Because the predicate on `sold_on` matches partition bounds, letting planner/executor prune January purely from partition metadata—even without an index on `sold_on`.

### Exercise 5. Write a pruning-friendly March query

```sql
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-03-01'
  AND sold_on <  DATE '2026-04-01';
```

**Answer:** Half-open date range matching March's exact bounds.

### Exercise 6. Why can `date_trunc('month',sold_on::timestamp)` degrade pruning?

**Answer:** Transforming the partition key column via casts/functions often prevents the optimizer from inverting the expression into direct `sold_on` range constraints.

### Exercise 7. Does seeing `Append` guarantee all partitions are scanned?

**Answer:** No. `Append` may wrap only surviving children after plan-time pruning, or the executor may remove unnecessary subplans at runtime.

### Exercise 8. What does `Subplans Removed` indicate?

**Answer:** The count of child subplans eliminated during initialization-time partition pruning when reported by `EXPLAIN`.

### Exercise 9. Why can a generic prepared plan still prune?

**Answer:** Supported PostgreSQL versions perform execution-time partition pruning, using runtime bind parameter values to skip irrelevant subplans.

### Exercise 10. Why is `(never executed)` in `EXPLAIN` important?

**Answer:** It confirms a node was skipped during the measured execution—often due to runtime pruning or conditional plan control. Inspect loops and parent nodes together.

### Exercise 11. How do pruning and `Index Scan` differ?

**Answer:** Pruning eliminates **entire relations/partitions** using bounds; `Index Scan` finds matching tuples **inside a surviving relation** using an index.

### Exercise 12. Can the same February query pick different scans for tenant 1 vs. tenant 321?

**Answer:** Yes. Because tenant 1 dominates rows, `Seq Scan` wins on cost; tenant 321 is selective, so a local `Index Scan` wins.

### Exercise 13. What does `Merge Append` accomplish?

**Answer:** Merges pre-sorted streams from child plans into globally ordered output, potentially avoiding an explicit top-level `Sort`.

### Exercise 14. Is `Parallel Append` always faster than `Append`?

**Answer:** No. Worker startup, `Gather` overhead, partition sizes, and I/O contention can make parallel plans slower across small partitions.

### Exercise 15. Why must the parent `PRIMARY KEY` include the partition key?

**Answer:** Without a global unique index across partitions, PostgreSQL enforces uniqueness via local partition indexes; including the partition key guarantees potentially colliding keys always map to the same partition.

### Exercise 16. Does a parent index store all child entries in one single B-tree?

**Answer:** No. The partitioned index defines the logical hierarchy; physical B-tree structures live locally on each child partition.

### Exercise 17. Can you run `CREATE INDEX CONCURRENTLY` directly on a partitioned parent?

**Answer:** Direct `CREATE INDEX CONCURRENTLY` on the partitioned parent is unsupported in those releases. Use the supported workflow: create an `ON ONLY` parent metadata index, build child indexes concurrently, and attach each child index.

### Exercise 18. Can `CREATE INDEX CONCURRENTLY` run inside `BEGIN ... COMMIT`?

**Answer:** No. It must run outside explicit transaction blocks.

### Exercise 19. Why can `ATTACH` scan the child table?

**Answer:** PostgreSQL must verify all existing rows satisfy the partition bounds unless a validated constraint proves compliance.

### Exercise 20. How does a pre-validated `CHECK` help before `ATTACH`?

**Answer:** It proves every row falls within bounds, reducing or eliminating the attach validation scan where supported.

### Exercise 21. How does `DEFAULT` impact attaching a new month?

**Answer:** If `DEFAULT` holds rows matching the new month, they must be migrated out first; PostgreSQL must also lock/validate `DEFAULT` prior to attaching.

### Exercise 22. Are `CREATE TABLE ... PARTITION OF` and `ATTACH` identical?

**Answer:** No. The former creates a brand-new child directly in the hierarchy; the latter integrates an existing compatible table with distinct prep, validation, and lock profiles.

### Exercise 23. Does data survive `DETACH`?

**Answer:** Yes. The detached table remains an intact standalone table holding its rows and indexes until archived or dropped.

### Exercise 24. Can `DETACH CONCURRENTLY` always run when `DEFAULT` exists?

**Answer:** No. Current PostgreSQL versions restrict `DETACH CONCURRENTLY` when a default partition exists; verify release docs and test carefully.

### Exercise 25. Why can partition retention beat deleting millions of rows?

**Answer:** Detaching/dropping an expired partition avoids per-row `DELETE` WAL, dead tuples, and `VACUUM` churn, while introducing DDL locks and requiring backup/retention controls.

### Exercise 26. What happens if a January row arrives after January is dropped?

**Answer:** If `DEFAULT` exists unguarded, it lands in `DEFAULT`; otherwise `INSERT` fails with no partition found. Define an explicit late-arriving data policy.

### Exercise 27. Why can updating the partition key be expensive?

**Answer:** Changing a row's target partition forces cross-partition tuple movement, updating both source and destination heaps, indexes, constraints, and locks.

### Exercise 28. Does an `ACCESS EXCLUSIVE` lock on February block `SELECT` on February?

**Answer:** Yes, whenever the `SELECT` needs an incompatible `ACCESS SHARE` lock on February while the holding transaction remains open.

### Exercise 29. Does locking February guarantee every January `SELECT` runs unblocked?

**Answer:** No. Queries cleanly pruning February at plan time can avoid it, yet parent locks or late pruning can still interact.

### Exercise 30. Find blocking PIDs

```sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
```

**Answer:** Inspecting the `blockers` array maps the wait graph. Check state, client app, and SQL before intervening.

### Exercise 31. Why does `pg_locks.granted = false` matter?

**Answer:** It flags ungranted waiting lock requests; combine with `locktype`, `mode`, `relation`, and `waitstart` to pinpoint contention.

### Exercise 32. Does vacuuming one leaf vacuum the entire hierarchy?

**Answer:** No. `VACUUM (ANALYZE) part_eval_lab.sales_2026_02` targets only February.

### Exercise 33. Is `n_dead_tup` an exact dead-row count?

**Answer:** No. It is a statistical estimate, not an exact MVCC tuple count.

### Exercise 34. Why does the parent need periodic manual `ANALYZE`?

**Answer:** The parent stores no heap rows directly, so child churn does not automatically trigger parent auto-`ANALYZE`. Schedule parent `ANALYZE` after major hierarchy shifts.

### Exercise 35. Why do quiet historical partitions still need freeze policies?

**Answer:** Even without writes, transaction ID ages continue advancing and require periodic freezing to prevent wraparound.

### Exercise 36. Is `pg_total_relation_size(parent)` the total size of all partitions?

**Answer:** No. Sum `pg_total_relation_size(relid)` across leaf relations returned by `pg_partition_tree`.

### Exercise 37. Why doesn't disk usage drop after `DETACH` shrinks tree totals?

**Answer:** Detaching removes the child from `pg_partition_tree` sums, while the standalone table's heap and index files remain on disk.

### Exercise 38. Does `enable_partitionwise_join=on` force partitionwise joins everywhere?

**Answer:** No. It enables the planner to consider them based on compatibility and cost, never forcing them unconditionally.

### Exercise 39. Can `GROUP BY tenant_id` always aggregate per month without a final merge?

**Answer:** No whenever the same tenant spans multiple months. A final aggregation stage must combine partial per-partition aggregates.

### Exercise 40. Why evaluate `work_mem` when enabling partitionwise join/aggregate?

**Answer:** Splitting joins/aggregates across many partitions creates multiple parallel hash/sort memory allocations, raising total memory pressure. Benchmark under concurrency.

### Exercise 41. If `EXPLAIN` shows only February yet remains slow, what do you check?

**Answer:** Check February's scan path, estimated vs. actual rows, local indexes, selectivity, buffers, join loops, sorts/aggregates, and skew—never split partitions further just for pruning when pruning already hit one leaf.

### Exercise 42. Why can `Planning Time` jump after splitting 12 partitions into 365?

**Answer:** Catalog lookups, relation handles, indexes, and access path combinations scale up with partition count—raising planning time even when execution pruning works cleanly.

### Exercise 43. Outline an ATTACH runbook for a new month

**Answer:** Verify bounds, `DEFAULT`, schema/indexes; prepare/validate `CHECK`; assess lock modes, DDL windows, and timeouts; attach; `ANALYZE`; verify tree, routing, plans, and alerts.

### Exercise 44. Outline a retention runbook

**Answer:** Verify cutoff, approvals, backups; check late writes, dependencies, replicas; detach/archive/drop cleanly; enforce lock timeouts; verify data visibility, disk space, and monitoring afterward.

### Exercise 45. Write a partitioning performance evaluation report

**Suggested answer:** Document SQL text, bind parameters, partition key/bounds, partition counts before/after pruning, per-child scan paths, estimated/actual rows, buffers, planning vs. execution time, lock waits, stats freshness, and maintenance overhead. Conclude improvement only from representative workload measurements.

## 40. Partitioning Health Audit Checklist

| Question | Action |
| --- | --- |
| Does the partition key match core query filters? | Compare `WHERE` patterns against partition bounds |
| Are any future partitions missing? | Check `pg_partition_tree` and pre-creation schedule |
| Does `DEFAULT` hold unexpected rows? | Audit row counts and date spread |
| Are partition key predicates pruning-friendly? | Prefer half-open ranges |
| Do casts/functions block pruning? | Rewrite onto raw key predicates where appropriate |
| Do parameterized queries use generic plans? | Inspect runtime pruning via `EXPLAIN EXECUTE` |
| How many partitions are actually scanned? | Check plan nodes, `loops`, and buffers |
| Are `Subplans Removed` lines reported? | Distinguish initialization-time pruning |
| Are `(never executed)` nodes present? | Verify per-loop runtime pruning |
| Are there too many partitions? | Measure `Planning Time` and catalog overhead |
| Is a post-pruning partition still huge? | Tune local indexes and scan paths |
| Does the index hierarchy match workload? | Audit parent vs. child index definitions |
| Are any child indexes missing or `INVALID`? | Inspect catalog and index build status |
| Need online concurrent index builds? | Build per leaf concurrently and attach per version workflow |
| Does `ATTACH` scan the staging table? | Pre-stage and validate bound `CHECK`s first |
| Does `DEFAULT` block `ATTACH`? | Check overlapping rows, locks, and validation scans |
| Does `CREATE PARTITION` take heavy locks? | Schedule in appropriate windows |
| Can `DETACH CONCURRENTLY` be used? | Verify version, `DEFAULT` presence, and transaction limits |
| Is DDL blocked behind long transactions? | Check `pg_blocking_pids` and `pg_stat_activity` |
| Are lock timeouts configured safely? | Never let DDL hang indefinitely |
| Is retention cutoff clearly approved? | Align with domain and compliance policies |
| Are late-arriving writes handled? | Reject, quarantine, or reconcile safely |
| Checked backups, replicas, and dependencies? | Verify all downstream impacts before `DROP` |
| Are parent statistics fresh? | Run periodic `ANALYZE` on parent |
| Are child statistics accurate? | Check `last_analyze` and estimated vs. actual rows |
| Does child autovacuum keep up with `UPDATE`s? | Monitor `n_dead_tup` and `last_autovacuum` |
| Do historical partitions have freeze coverage? | Track relation transaction age |
| Is any partition heavily bloated? | Measure storage vs. `VACUUM` history |
| Should a child index be reindexed? | Base on bloat evidence and lock impact |
| Did storage totals sum across all leaves? | Use `pg_partition_tree` + relation size functions |
| Disk still full after `DETACH`? | Remember standalone detached tables stay on disk |
| Using partitionwise join/aggregate? | Benchmark plans and `work_mem` |
| Queries running many-to-many joins? | Watch `loops` and row estimates |
| Monitoring per leaf partition? | Query `pg_stat_*` / `pg_statio_*` |
| Tracking live `VACUUM` progress? | Check `pg_stat_progress_vacuum` |
| Benchmarked after DDL changes? | Run `EXPLAIN (ANALYZE, BUFFERS)` |
| Rollback plan ready for migrations? | Define checkpoints, cleanup, and alerts |
| Measured concurrency and p95/p99? | Never rely on a single isolated `EXPLAIN` |
| Clear owner for partition runbooks? | Assign alerts, audits, and approvals |

## 41. Summary

Partitioning organizes large datasets and streamlines operational lifecycles, provided you manage **query plans, locks, and maintenance** together.

Key principles:

1. **The partitioned parent is a logical relation**, while leaf partitions store actual heaps, indexes, and tuples.
2. **Partition pruning** eliminates irrelevant partitions via bounds; it is **distinct from an `Index Scan`** inside a partition.
3. `Append` / `Merge Append` / `Parallel Append` are standard plan structures and do not imply every child was actually scanned.
4. **Plan-time pruning** removes children before plan completion; **execution-time pruning** uses bind parameters inside the executor.
5. **Generic prepared plans** can still runtime-prune; inspect `Subplans Removed`, `loops`, and `(never executed)` instead of guessing from `Append`.
6. Write **half-open range predicates directly on the partition key** so the planner derives bounds cleanly without missing sub-second timestamps.
7. Local indexes remain vital for selective queries inside surviving leaves. Parent indexes form an **index hierarchy**, not one giant global B-tree.
8. `CREATE INDEX CONCURRENTLY` is unsupported directly on partitioned parents in relevant releases; use concurrent leaf builds followed by `ALTER INDEX ... ATTACH PARTITION`.
9. **DDL is never lock-free**: `CREATE PARTITION`, `ATTACH`, `DETACH`, and `DROP` acquire significant locks or stall behind long transactions.
10. **`ATTACH`** may scan both the staging table and `DEFAULT` to prove bounds; pre-validated `CHECK` constraints skip validation scans when tight enough.
11. **`DETACH` is not `DROP`**: data stays intact in a standalone table. `DETACH CONCURRENTLY` carries strict restrictions and is never instantaneous.
12. **Partition retention** avoids massive row-level `DELETE`s, yet still demands coordination across backups, late data, foreign keys, replication, and approvals.
13. **`VACUUM`, `ANALYZE`, and index maintenance** operate per leaf, while parents still need periodic `ANALYZE` for up-to-date hierarchy statistics.
14. **Quiet old partitions still need freeze maintenance** for MVCC wraparound safety, while hot partitions need tighter autovacuum/autoanalyze thresholds.
15. `pg_total_relation_size(parent)` is not total storage; sum `pg_total_relation_size` across **leaf partitions**.
16. `pg_locks`, `pg_stat_activity`, and `pg_blocking_pids` pinpoint blocking sessions without resorting to reckless mass termination.
17. **Partitionwise joins and aggregates** cut redundant work in aligned queries, at the cost of extra plan nodes and memory usage on deep trees.
18. **Measure both `Planning Time` and `Execution Time`**, plus buffers, row estimates, and lock waits, to prove partitioning actually helps.

Reference queries to keep handy:

```sql
-- 1. Actual partition tree:
SELECT relid::regclass, isleaf, level
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
);

-- 2. February pruning check:
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';

-- 3. Inspect DDL/lock waits:
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();

-- 4. Refresh parent statistics:
ANALYZE part_eval_lab.sales;

-- 5. Measure total attached tree storage:
SELECT pg_size_pretty(
    SUM(pg_total_relation_size(relid))
)
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
)
WHERE isleaf;
```

**Core rule:** whenever a partitioned system feels slow or blocked, ask **"which partitions are actually being read, what locks are held on the parent or specific leaves, and what state are each partition's stats and maintenance in?"** Answering with `EXPLAIN`, lock graphs, and per-leaf statistics beats assuming monthly partitioning automatically makes everything fast.
