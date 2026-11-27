# ATTACH, DETACH, and Data Lifecycle Management in PostgreSQL

A logging, transaction, IoT event, or access-record system can grow by millions of rows every month. Recent data is queried frequently, older data only needs to be looked up during audits, and expired data must be archived or deleted according to policy. If all of it lives in one giant table, deleting rows one by one with `DELETE` can take a long time, generate substantial WAL, and leave behind dead row versions that require `VACUUM` cleanup.

**Declarative partitioning** lets PostgreSQL organize a logical table into multiple child tables (*partitions*) by time range, list of values, or hash function. When partitioning by month, a system can:

1. Pre-create a table for the new month.
2. **`ATTACH PARTITION`** to attach an existing table into the partition tree, even when that table already contains valid data.
3. Continue querying through the **parent table** as a single unified logical table.
4. When an old month reaches the end of its online serving lifecycle, **`DETACH PARTITION`** to separate it into a standalone table.
5. Back up/export the old data, verify it, and only then **`DROP TABLE`** if policy permits.

Conceptual view:

```text
               events (partitioned parent)
                         |
           +-------------+-------------+
           |             |             |
     events_2026_01  events_2026_02  events_2026_03
      [Jan rows]      [Feb rows]      [Mar rows]
           |                             ^
           | DETACH                      | ATTACH
           v                             |
   standalone table              staging_march
    / archive candidate          (existing table)
           |
      Export + verify
           |
   Retain / DROP later
```

The `ATTACH` and `DETACH` operations **change the relationship between the parent table and child table**; they are not by default commands that copy or delete all rows. Because of this, cycle-based data management can be much more efficient than moving or deleting individual records. However, safety depends on **partition bounds, data constraints, DDL locks, the default partition, indexes, foreign keys, transactions, and archival procedures**.

This lesson belongs to the **Partitioning** chapter of the *Database Engine Relational PostgreSQL* module. It provides self-contained SQL labs, operational diagrams, failure scenarios, production deployment notes, and exercises with answers.

**Objectives:**

- Understand how PostgreSQL routes `INSERT` statements and eliminates irrelevant partitions during queries (*partition pruning*).
- Create a time-based `RANGE` partitioned table and verify `FROM ... TO ...` bounds.
- `ATTACH` a regular table that already has data, using a validated `CHECK` constraint to reduce the risk of a full-table scan.
- Handle the impact of a **default partition** and data falling inside the range being attached.
- Distinguish regular `DETACH PARTITION` from `DETACH PARTITION CONCURRENTLY`, including `FINALIZE` when a concurrent operation is interrupted.
- Build a **hot → warm → archive → delete** workflow with row-count reconciliation, backups, retention, and legal hold.
- Understand the impact on locks, indexes, primary keys/unique constraints, FKs, transactions, logical replication, and monitoring.

> **Safety:** All hands-on DDL/DML commands use a dedicated schema `partition_lifecycle_lab` in a test database. Do not run `DROP`, `DETACH`, or modify retention on production tables without proper authorization and a runbook. Do not run `DETACH ... CONCURRENTLY` inside `BEGIN ... COMMIT`; it has its own transaction restrictions.

---

## 1. Partitioned Tables and Physical Partitions

### 1.1. The Parent Table Is a Logical Relation

Suppose a logical table `events` contains an `event_time` column. We can split it by month:

```text
events
  event_time  < 2026-02-01 --> events_2026_01
  event_time  < 2026-03-01 --> events_2026_02
  event_time  < 2026-04-01 --> events_2026_03
```

With PostgreSQL declarative partitioning, the parent table defines the structure and partitioning method. The partitions are **separate relations with actual data storage**; a partitioned parent table normally holds no heap rows of its own.

### 1.2. Main Partitioning Methods

| Method | Typical Syntax | Use Case |
|---|---|---|
| `RANGE` | `PARTITION BY RANGE (event_time)` | Monthly/daily time-series data, bounded numeric ranges |
| `LIST` | `PARTITION BY LIST (region)` | Finite sets of statuses, regions, or categories |
| `HASH` | `PARTITION BY HASH (tenant_id)` | Distributing keys by modulo/remainder |

Time-based lifecycle management pairs especially well with **`RANGE`**, because it is common to archive or drop an entire month or day at once.

### 1.3. RANGE Intervals Are Half-Open

A partition:

```sql
FOR VALUES FROM ('2026-01-01 00:00:00+00')
           TO ('2026-02-01 00:00:00+00')
```

is **inclusive of the lower bound** and **exclusive of the upper bound**:

```text
2026-01-01 00:00:00+00    accepted
2026-01-31 23:59:59+00    accepted
2026-02-01 00:00:00+00    does not belong to Jan
```

Fractional seconds are also handled accurately under half-open bounds. Do not express a month using `BETWEEN ... 23:59:59`, because it can miss timestamps with microseconds.

### 1.4. Partition Pruning Is Different from an Index Scan

PostgreSQL can **skip partitions** that cannot contain rows matching the predicate:

```sql
SELECT COUNT(*)
FROM events
WHERE event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-03-01 00:00+00';
```

This is **partition pruning**. After selecting the February partition, PostgreSQL may still perform a **Seq Scan** or an **Index Scan** inside that partition. A Seq Scan on a small partition **does not mean pruning failed**.

---

## 2. Monthly Hands-On Dataset

### 2.1. Check the Database

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Create a dedicated schema. If a schema with the same name already exists and holds data from another session, switch to a different practice database instead of dropping objects outside your scope.

### 2.2. Create the Parent Partitioned Table

```sql
CREATE SCHEMA partition_lifecycle_lab;

CREATE TABLE partition_lifecycle_lab.events (
    event_id BIGINT NOT NULL,
    tenant_id INTEGER NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_time, event_id)
) PARTITION BY RANGE (event_time);
```

Key points to understand:

- `event_time` is the **partition key**.
- `PRIMARY KEY (event_time, event_id)` includes the partition key to satisfy the uniqueness requirement on a partitioned parent.
- PostgreSQL routes `INSERT INTO ...events` statements to the appropriate partition.
- The parent stores no regular data heap; the partitions are where rows live.

**Why not declare `PRIMARY KEY (event_id)` on the parent?** PostgreSQL does not have a single global B-tree spanning all RANGE partitions to directly enforce uniqueness of `event_id` when the partition key is `event_time`. A `PRIMARY KEY`/`UNIQUE` constraint on a partitioned parent must include all partition key columns under the applicable rules. The key `(event_time,event_id)` does not prevent two rows in two different months from having the same `event_id` with different `event_time` values.

### 2.3. Create the January Partition

```sql
CREATE TABLE partition_lifecycle_lab.events_2026_01
PARTITION OF partition_lifecycle_lab.events
FOR VALUES FROM ('2026-01-01 00:00:00+00')
           TO ('2026-02-01 00:00:00+00');
```

### 2.4. Create the February Partition

```sql
CREATE TABLE partition_lifecycle_lab.events_2026_02
PARTITION OF partition_lifecycle_lab.events
FOR VALUES FROM ('2026-02-01 00:00:00+00')
           TO ('2026-03-01 00:00:00+00');
```

Do not create the March partition yet; we will create **a standalone table with preloaded data** and then practice `ATTACH`ing it.

### 2.5. Create an Index via the Parent

```sql
CREATE INDEX events_tenant_time_idx
ON partition_lifecycle_lab.events
    (tenant_id, event_time DESC);
```

Defining an index on the partitioned parent creates a **partitioned index**, with corresponding physical indexes on the child partitions. Do not mistake this for a single global B-tree holding every entry across all partitions.

### 2.6. Insert Data via the Parent

```sql
INSERT INTO partition_lifecycle_lab.events
    (event_id, tenant_id, event_time, event_type, payload)
VALUES
    (1001, 10, '2026-01-15 08:00:00+00',
     'login', '{"source":"web"}'),
    (1002, 20, '2026-01-31 23:59:59+00',
     'purchase', '{"total":100}'),
    (2001, 10, '2026-02-01 00:00:00+00',
     'login', '{"source":"mobile"}'),
    (2002, 10, '2026-02-18 12:30:00+00',
     'logout', '{}');
```

There is no need to insert directly into partition names. PostgreSQL automatically selects `events_2026_01` or `events_2026_02` based on `event_time`.

### 2.7. Verify Routing

```sql
SELECT
    tableoid::regclass AS physical_partition,
    event_id,
    event_time,
    event_type
FROM partition_lifecycle_lab.events
ORDER BY event_time;
```

`tableoid` is a system column indicating the physical relation containing the returned tuple. When querying through the parent, it is useful for observing which partition actually holds each row.

Expected output:

| event_id | Partition | Timestamp |
|---:|---|---|
| 1001 | `events_2026_01` | 2026-01-15 |
| 1002 | `events_2026_01` | 2026-01-31 |
| 2001 | `events_2026_02` | 2026-02-01 |
| 2002 | `events_2026_02` | 2026-02-18 |

The full name rendered by `tableoid::regclass` may or may not be schema-qualified depending on `search_path`; do not compare its display string rigidly.

### 2.8. What Happens If You INSERT into a Month Without a Partition

```sql
-- At this point there is no March or DEFAULT partition yet:
-- INSERT INTO partition_lifecycle_lab.events
--     (event_id, tenant_id, event_time, event_type)
-- VALUES (3001, 10, '2026-03-03 00:00+00', 'login');
```

The command above will fail with:

```text
ERROR: no partition of relation "events" found for row
```

This is expected behavior: PostgreSQL has no valid partition to hold the row. **Applications must not rely on partitions being created automatically simply by inserting into a new month.** You must schedule partition creation/attachment before data arrives, or have a deliberately designed default partition.

---

## 3. When Is ATTACH PARTITION Used?

`ATTACH PARTITION` attaches an **already existing** table to a partitioned parent table with a declared bound range.

### 3.1. Main Syntax

```sql
ALTER TABLE parent_table
ATTACH PARTITION existing_table
FOR VALUES FROM (lower_bound)
           TO (upper_bound);
```

Example for March:

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_03
FOR VALUES FROM ('2026-03-01 00:00:00+00')
           TO ('2026-04-01 00:00:00+00');
```

At the time this command is executed, `events_2026_03` must **already exist**, match the parent's structure, and contain only data within the permitted range. We will create that table in the next section.

### 3.2. How Does It Differ from CREATE TABLE ... PARTITION OF?

| Operation | Scenario |
|---|---|
| `CREATE TABLE child PARTITION OF parent ...` | Creates a new partition directly inside the tree |
| `CREATE TABLE child (...); ALTER TABLE parent ATTACH PARTITION child ...` | Creates a standalone table first, loads/validates data, and attaches it later |
| `ALTER TABLE parent DETACH PARTITION child` | Separates an existing partition into a standalone table |

The `ATTACH` approach is especially useful when data is **bulk-loaded** into a staging table, when constraints/indexes are prepared beforehand, or when **bringing existing historical data** into a partition tree.

### 3.3. ATTACH Is Not COPY

If a standalone table holds one million rows, `ATTACH` does not by default copy each row into another child table. It turns **the existing table itself** into a partition through the required checks and metadata updates.

However, PostgreSQL may have to **scan the table** to prove all rows fall within bounds, or build/match the necessary indexes and constraints. Therefore, never assume "ATTACH is metadata-only in every situation."

---

## 4. Creating a March Staging Table and Attaching Preloaded Data

### 4.1. Create a Standalone Table Matching the Parent Structure

```sql
CREATE TABLE partition_lifecycle_lab.events_2026_03
(
    LIKE partition_lifecycle_lab.events
      INCLUDING DEFAULTS
      INCLUDING CONSTRAINTS
      INCLUDING INDEXES
);
```

This creates a **regular table** with matching columns, defaults, CHECK constraints, and indexes/PK copied according to the `LIKE` options. `LIKE` does not mean the new table automatically becomes a partition or inherits all external dependencies, privileges, triggers, or FKs identically to the parent. In production deployments, deliberately verify structure, constraints, and indexes.

### 4.2. Load March Data into the Staging Table

```sql
INSERT INTO partition_lifecycle_lab.events_2026_03
    (event_id, tenant_id, event_time, event_type, payload)
VALUES
    (3001, 10, '2026-03-02 09:00:00+00',
     'login', '{"source":"web"}'),
    (3002, 20, '2026-03-15 18:00:00+00',
     'purchase', '{"total":250}'),
    (3003, 10, '2026-03-31 23:59:59+00',
     'logout', '{}');
```

At this point, these rows **exist only in the standalone table**. Queries through `partition_lifecycle_lab.events` do not see them yet.

### 4.3. Check Data Bounds Before ATTACH

```sql
SELECT
    COUNT(*) AS total_rows,
    MIN(event_time) AS min_time,
    MAX(event_time) AS max_time
FROM partition_lifecycle_lab.events_2026_03;

SELECT COUNT(*) AS out_of_range_rows
FROM partition_lifecycle_lab.events_2026_03
WHERE NOT (
    event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
    AND event_time <
        TIMESTAMPTZ '2026-04-01 00:00:00+00'
);
```

Because `event_time` is `NOT NULL`, the `NOT (...)` check in this example does not skip rows with NULL timestamps. The result for `out_of_range_rows` must be **0**.

This is a useful application/business check, but **it does not substitute** for a constraint validated by PostgreSQL.

### 4.4. Create a CHECK Constraint Matching the Exact Bounds

```sql
ALTER TABLE partition_lifecycle_lab.events_2026_03
ADD CONSTRAINT events_2026_03_bounds_chk
CHECK (
    event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
    AND event_time < TIMESTAMPTZ '2026-04-01 00:00:00+00'
);
```

A **validated** `CHECK` constraint that proves the partition bounds lets PostgreSQL skip rescanning the entire table to verify data during `ATTACH`. This is critical for large staging tables.

Do not simply run a `SELECT ... WHERE` check and assume the database can trust that result. PostgreSQL relies on enforced constraints and its verification rules.

### 4.5. For Large Tables: NOT VALID Followed by VALIDATE

You can prepare the constraint in a separate phase:

```sql
-- Alternative pattern for ADD CHECK in Section 4.4;
-- do not run both patterns with the same constraint name on one table.
--
-- ALTER TABLE partition_lifecycle_lab.events_2026_03
-- ADD CONSTRAINT events_2026_03_bounds_chk
-- CHECK (
--   event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
--   AND event_time < TIMESTAMPTZ '2026-04-01 00:00:00+00'
-- ) NOT VALID;
--
-- ALTER TABLE partition_lifecycle_lab.events_2026_03
-- VALIDATE CONSTRAINT events_2026_03_bounds_chk;
```

`NOT VALID` lets you separate declaring the constraint from the validation scan of existing rows according to PostgreSQL's rules. **You must complete `VALIDATE CONSTRAINT` successfully before relying on the constraint to skip the scan during ATTACH.** A CHECK that is still `NOT VALID` does not prove existing rows are valid.

### 4.6. Prepare Matching Indexes

The parent currently has the index:

```sql
ON events (tenant_id, event_time DESC)
```

We can pre-create an equivalent index on staging:

```sql
CREATE INDEX events_2026_03_tenant_time_idx
ON partition_lifecycle_lab.events_2026_03
    (tenant_id, event_time DESC);
```

During attach, PostgreSQL can **attach an existing compatible index** to the parent's partitioned index, rather than building the corresponding index inside the DDL window. If a required index is missing, the DBMS may build it on the new partition according to its rules.

Indexes and constraints are not just about performance: if the parent has a `PRIMARY KEY`/`UNIQUE` constraint, the partition must satisfy the corresponding requirements. Preparing structures on staging reduces the work needed at ATTACH time.

### 4.7. Execute ATTACH

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_03
FOR VALUES FROM ('2026-03-01 00:00:00+00')
           TO ('2026-04-01 00:00:00+00');
```

Once this succeeds, `events_2026_03` becomes a partition of `events`. The table retains its March data; there is no need to re-INSERT the rows.

### 4.8. Confirm the Parent Sees the New Data

```sql
SELECT
    tableoid::regclass AS physical_partition,
    event_id,
    event_time,
    event_type
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
ORDER BY event_time;
```

Expected output includes IDs `3001`, `3002`, and `3003`, all located in `events_2026_03`.

### 4.9. Reasons ATTACH Can Fail

| Scenario | Cause |
|---|---|
| April rows exist in the March table | Data violates the bounds being attached |
| March bounds overlap an existing partition | Sibling RANGE partitions at the same level cannot overlap |
| Missing/different columns or incompatible structure | Attached table must match the parent's definition |
| A required index/constraint cannot be guaranteed | DDL cannot complete validly |
| Default partition contains rows belonging to March | Those rows would become invalid in default after ATTACH |
| Lock could not be acquired within timeout | Another transaction is using the object |
| Insufficient privileges / invalid object dependencies | PostgreSQL cannot perform the schema change |

Do not automatically retry every DDL error: **bound conflicts or invalid data must be fixed**—they are not transient contention errors.

---

## 5. Why Is a CHECK Constraint Before ATTACH Important?

Suppose the staging table contains **50 million rows**. PostgreSQL must guarantee:

```text
ALL event_time >= 2026-03-01 00:00 UTC
AND
ALL event_time <  2026-04-01 00:00 UTC
```

Without suitable constraint proof, the database may have to **scan the entire staging table** to verify it.

### 5.1. A Full Scan Does Not Turn ATTACH into COPY

A validation scan can read a great deal of data and hold required locks, yet it still does not mean PostgreSQL copies every row from the staging table into another child table. It is a **validation scan**.

### 5.2. A Validated CHECK Is Durable Proof

```sql
ALTER TABLE partition_lifecycle_lab.events_2026_03
ADD CONSTRAINT events_2026_03_bounds_chk
CHECK (
  event_time >= TIMESTAMPTZ '2026-03-01 00:00+00'
  AND event_time < TIMESTAMPTZ '2026-04-01 00:00+00'
);
```

This constraint not only proves existing rows are valid, it also **prevents subsequently written rows from violating** the bounds under PostgreSQL's check rules.

### 5.3. The Proof Must Be Tight Enough

A CHECK like:

```sql
-- Too broad, does not prove all rows belong to March:
-- CHECK (event_time >= TIMESTAMPTZ '2026-01-01 00:00+00')
```

does not prove the table only holds March rows. It still permits April/May rows, so it cannot substitute for a CHECK matching the exact bounds.

### 5.4. CHECK Limitations with NULL

In SQL, `CHECK` treats both `TRUE` **and `UNKNOWN` as non-violating**. Therefore, if the partition key is nullable, a CHECK consisting only of range comparisons might not prove every row falls within the range because of NULLs.

In our example, `event_time NOT NULL` is declared; non-nullability combined with the range condition makes the proof unambiguous. Do not casually drop `NOT NULL` when adapting this pattern to production.

### 5.5. Other Checks Do Not Replace CHECK for ATTACH

A `SELECT` before ATTACH, an operational runbook note, or an application-layer promise **is not treated by PostgreSQL as enforced proof** across all rows of the table. Let the database enforce the constraint if you want to rely on it for validation.

---

## 6. Locking Behavior of ATTACH PARTITION

ATTACH is DDL and affects concurrent sessions. "Metadata-only change" **does not mean lock-free**.

### 6.1. Key Lock Levels to Remember

With modern declarative partitioning:

- `ATTACH PARTITION` requires a **`SHARE UPDATE EXCLUSIVE` lock on the parent table**.
- The table being attached requires a stronger lock, typically **`ACCESS EXCLUSIVE`**, during the operation.
- If there is a **default partition** that must be checked to ensure it contains no rows belonging to the new bounds, PostgreSQL may scan the default partition and hold **`ACCESS EXCLUSIVE`** on the relevant relation during verification.
- If the attached table or default partition is itself a partitioned subtree, verification may recurse down to leaf partitions.

Exact lock details, wait durations, and edge-case impacts depend on the PostgreSQL version and specific DDL; consult the documentation for your server version when deploying.

### 6.2. Why Pre-Stage the Table First?

Move expensive work ahead of the attach window:

1. Load data into the standalone table.
2. Verify bounds.
3. Validate CHECK.
4. Create matching indexes.
5. Run `ANALYZE` if needed.
6. Only then run `ATTACH`.

The goal is to **minimize the work performed while holding locks on the parent and participating objects**.

### 6.3. Bound Lock Wait Time

Inside a dedicated DDL transaction in the lab:

```sql
-- Example showing SET LOCAL; do not re-run if the table is already attached:
-- BEGIN;
-- SET LOCAL lock_timeout = '5s';
-- ALTER TABLE partition_lifecycle_lab.events
-- ATTACH PARTITION partition_lifecycle_lab.events_2026_03
-- FOR VALUES FROM ('2026-03-01 00:00+00')
--            TO ('2026-04-01 00:00+00');
-- COMMIT;
```

`lock_timeout` ensures the operation **fails in a controlled manner if waiting too long for a lock**, rather than hanging indefinitely during deployment. When an error occurs in a transaction, roll back and reassess conditions before retrying.

### 6.4. ATTACH Has No CONCURRENTLY Option Like DETACH

PostgreSQL provides `DETACH PARTITION CONCURRENTLY` syntax to reduce locking on the parent in supported scenarios, but there is no equivalent `ATTACH PARTITION CONCURRENTLY` where you can just add the keyword `CONCURRENTLY`.

To optimize online ATTACH, use **staging + validated CHECK + pre-built indexes + lock/timeout management**.

---

## 7. Default Partition: Benefits and the Cost of Flexibility

A **default partition** catches rows that do not match any declared partition bounds.

### 7.1. Creating a Default Partition

After finishing the `DETACH CONCURRENTLY` scenarios in Section 10, you can try:

```sql
-- In the lab, run this AFTER the detach concurrently section,
-- because a default partition restricts DETACH ... CONCURRENTLY.
CREATE TABLE partition_lifecycle_lab.events_default
PARTITION OF partition_lifecycle_lab.events
DEFAULT;
```

When a default partition exists, an `INSERT` for a month without a specific partition goes into the default table instead of raising a "no partition found" error.

### 7.2. Why Can Default Make ATTACH Harder?

Suppose a default partition already exists and currently holds April events. Later, you want to run:

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_04
FOR VALUES FROM ('2026-04-01 00:00+00')
           TO ('2026-05-01 00:00+00');
```

When adding the April partition, April rows **are no longer permitted to live in the default partition**. PostgreSQL must prove the default **contains no rows** falling into the new bounds. If any exist, attach will **fail** until that data is moved consistently.

### 7.3. Scan and Lock Impact on Default

Without a suitable CHECK excluding the new bounds, PostgreSQL may have to scan the default partition during attach. With a huge default partition, this greatly increases DDL duration and lock hold time.

A validated CHECK on the default proving:

```text
event_time < lower_bound
OR
event_time >= upper_bound
```

can avoid the verification scan for the new bounds, **if it holds for all existing rows and is tight enough under PostgreSQL's rules**.

### 7.4. You Cannot Just Copy and Attach While Default Still Holds the Originals

A broken workflow looks like:

```text
1. COPY April rows from default into staging April.
2. ATTACH April immediately.
3. Leave the April rows sitting inside default.
```

During attach, default still holds April rows, making it invalid. Moreover, concurrent writers may keep inserting April rows into default while the move is underway.

**The workflow must handle consistency properly**: define a write/lock window, move the exact rows from default to the target table, delete the original rows, and prevent races with writers before and through attach. On large systems, design a proper migration with transactions, locks, and backfill rather than copying unguarded SQL snippets.

### 7.5. DEFAULT Does Not Replace a Partition Creation Schedule

A default reduces the risk of INSERT failures when a partition is missing, but it can:

- Grow into a large table that is hard to prune.
- Force extra validation when attaching new partitions.
- Prevent `DETACH PARTITION CONCURRENTLY`.
- Mask operational failures where teams forget to create partitions on time.

One option is **no default partition**, pre-creating partitions several periods ahead and alerting on routing errors. Another option is a controlled default with regular inspection and migration procedures. Choose based on SLA and operational capability.

---

## 8. DETACH PARTITION: Removing Data from the Parent

`DETACH PARTITION` severs the partition relationship between the child table and the parent, keeping that table as a **standalone table**.

### 8.1. Basic Syntax

```sql
ALTER TABLE parent_table
DETACH PARTITION partition_table;
```

For example, once January no longer needs to be in the online query set:

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_01;
```

### 8.2. What Happens After DETACH?

Before:

```text
events parent
  events_2026_01   <- visible to SELECTs through parent
  events_2026_02
  events_2026_03
```

After:

```text
events parent
  events_2026_02
  events_2026_03

events_2026_01     <- standalone table still exists
```

January rows **no longer appear in queries through the parent**, yet they remain intact inside `events_2026_01`.

### 8.3. Verify with SQL

```sql
SELECT COUNT(*) AS visible_from_parent
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-01 00:00+00';
```

After detaching January (with no other partitions or default containing January rows), the result is **0**.

However:

```sql
SELECT COUNT(*) AS rows_in_detached_table
FROM partition_lifecycle_lab.events_2026_01;
```

will count **2 rows** from the demo dataset.

### 8.4. DETACH Does Not Automatically Free Disk Space

This is a critical misconception in retention management:

```text
DETACH:
  parent no longer sees old rows
  standalone table still occupies storage

DROP TABLE detached_table:
  removes the table object and its data
  disk space can be reclaimed according to PostgreSQL rules
```

If the goal is **archival**, detach is a state transition step. If the goal is **retention deletion**, you must still execute the table drop after meeting policy and safety checks.

### 8.5. Impact on Application Queries and INSERTs

After detaching:

- Queries through the parent only see partitions **still attached**.
- Direct queries against the standalone table can still see old data if the role has privileges.
- If the application tries to INSERT a January event into the parent without a matching partition or default, the INSERT fails.
- If a default partition exists, that January event may be routed to default, breaking the assumption that "January data is completely off online storage."

You must define a policy for **late-arriving events** before detaching any period.

---

## 9. Locking Behavior of Regular DETACH

`DETACH PARTITION` without `CONCURRENTLY` typically requires a strong lock on the parent—specifically **`ACCESS EXCLUSIVE`**—and can block other operations while altering the tree structure.

### 9.1. Why Is This Dangerous on High-Traffic Tables?

`ACCESS EXCLUSIVE` conflicts with all other lock modes, including normal reads on the parent. Even if the DDL work itself is fast, **waiting for the lock** or holding it can build up a queue of blocked requests.

Actual detach duration depends on:

- Long-running transactions touching the table/partition.
- Other locks held on the parent.
- Number of dependent relations needing updates.
- FKs/triggers/indexes/concurrent DDL.
- Server load and PostgreSQL version.

### 9.2. Transactions Can Wrap Regular DETACH

```sql
-- Illustrative pattern if you want a lock deadline.
-- Do not re-run after January is already detached.
--
-- BEGIN;
-- SET LOCAL lock_timeout = '5s';
-- ALTER TABLE partition_lifecycle_lab.events
-- DETACH PARTITION partition_lifecycle_lab.events_2026_01;
-- COMMIT;
```

In regular mode, placing DETACH inside a valid DDL transaction can help coordinate it with other metadata changes. However, **keeping a transaction open long after the DDL** extends lock hold duration. Keep transactions short and controlled.

### 9.3. When Should Regular DETACH Be Used?

- Maintenance windows where strong locks are acceptable.
- Small systems with low transaction concurrency.
- Environments unsuitable for or not supporting CONCURRENTLY.
- When a default partition exists (due to CONCURRENTLY limitations).
- When DDL must be coordinated deliberately within a single transaction.

Do not default to regular DETACH on a high-traffic table just because the statement is short.

---

## 10. DETACH PARTITION CONCURRENTLY

Modern PostgreSQL versions support **`DETACH PARTITION CONCURRENTLY`** to lower the lock level on the parent and avoid blocking normal traffic for long periods while other transactions are using the partition tree.

### 10.1. Syntax

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_02
CONCURRENTLY;
```

In the lab, after detaching January, February is still attached and **we have not created a default partition yet**, so we can use February to test concurrent detach.

### 10.2. How Does It Differ from Regular DETACH?

Overview:

```text
Regular DETACH:
  strong lock on parent
  modifies partition relationship
  completes in a single DDL transaction

DETACH CONCURRENTLY:
  reduces lock required on parent
  executes across multiple phases / internal transactions
  may wait for existing transactions still using the parent
  has a "pending detach" state between phases
```

`DETACH CONCURRENTLY` typically acquires a **`SHARE UPDATE EXCLUSIVE`** lock on the parent instead of `ACCESS EXCLUSIVE`, though this does not mean there are zero locks, zero waits, or zero performance impacts.

### 10.3. DO NOT Run Inside an Explicit Transaction Block

Do not do this:

```sql
-- INVALID:
-- BEGIN;
-- ALTER TABLE partition_lifecycle_lab.events
-- DETACH PARTITION partition_lifecycle_lab.events_2026_02
-- CONCURRENTLY;
-- COMMIT;
```

`CONCURRENTLY` relies on PostgreSQL's own multi-transaction execution mechanism and cannot run inside an explicit `BEGIN ... COMMIT` block. Watch out especially for **migration frameworks** that automatically wrap every migration file in a transaction.

### 10.4. NOT Supported When the Parent Has a DEFAULT Partition

A key limitation to remember: **`DETACH PARTITION CONCURRENTLY` cannot be used if the parent has a default partition**.

This is why the lab creates the default partition **after** practicing concurrent detach. In production systems with a default partition, plan an appropriate strategy rather than simply adding `CONCURRENTLY` and expecting the DDL to succeed.

### 10.5. Two Phases and Pending Detach

In concurrent mode, PostgreSQL performs the work across **two transactions**. Roughly:

1. The first phase marks the partition as being detached according to the protocol and commits.
2. It waits for older transactions still referencing the parent within the required scope.
3. The next phase finalizes the detach.

If interrupted in between, the partition can remain in a **pending detach** state, not yet a fully clean standalone table that you can manipulate arbitrarily.

### 10.6. Recovering an Interrupted Operation with FINALIZE

Once you confirm a partition is in pending detach because an earlier concurrent detach was interrupted, you can run:

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_02
FINALIZE;
```

**Run this only when a matching pending detach actually exists**—not as an automatic command run every time. If the concurrent detach already succeeded, February is no longer a partition of the parent, so FINALIZE makes no sense.

### 10.7. No Multiple Concurrent Pending Detaches at Once

PostgreSQL restricts overlapping incomplete concurrent detaches. If one partition is still pending, you must **finalize/recover** that state properly before proceeding with related partition changes.

Do not let multiple independent retention jobs run `DETACH CONCURRENTLY` on the same parent without coordination.

### 10.8. When Should CONCURRENTLY Be Used?

- The parent has steady read/write traffic.
- There is no default partition.
- The migration runner permits DDL **outside a transaction**.
- You can wait on and monitor transactions still using the table.
- A runbook exists to handle pending detach/`FINALIZE` on interruption.

Do not treat it as a shortcut to skip FK, backup, or retention checks.

---

## 11. Inspecting the Partition Tree and DETACH State

### 11.1. pg_partition_tree

Modern PostgreSQL provides:

```sql
SELECT *
FROM pg_partition_tree(
    'partition_lifecycle_lab.events'::regclass
);
```

This function returns root, child, and level relationships, letting you inspect which partitions **remain in the tree**.

### 11.2. pg_inherits and Pending Detach Status

```sql
SELECT
    child_ns.nspname AS child_schema,
    child.relname AS child_name,
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_name,
    inh.inhdetachpending
FROM pg_inherits AS inh
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
WHERE inh.inhparent =
    'partition_lifecycle_lab.events'::regclass
ORDER BY child.relname;
```

`inhdetachpending` exists in versions supporting concurrent detach. On older PostgreSQL versions without this column, consult the catalog documentation for that version; do not assume the query above is portable to all versions.

A **`TRUE`** value indicates the inheritance/partition relationship is in a pending detach state that needs diagnosis before proceeding.

### 11.3. Inspect Bounds from the Catalog

```sql
SELECT
    child.relname AS partition_name,
    pg_get_expr(child.relpartbound, child.oid)
        AS partition_bound
FROM pg_class AS child
JOIN pg_inherits AS inh
    ON inh.inhrelid = child.oid
WHERE inh.inhparent =
    'partition_lifecycle_lab.events'::regclass
ORDER BY child.relname;
```

This checks the **bounds actually enforced by the database**, instead of trusting a table name like `events_2026_03` to prove it contains March data.

### 11.4. Using tableoid to See Which Partition Holds Rows

```sql
SELECT
    tableoid::regclass AS leaf_table,
    COUNT(*) AS rows_count
FROM partition_lifecycle_lab.events
GROUP BY tableoid
ORDER BY tableoid::regclass::text;
```

This query reports row counts visible through the parent grouped by physical relation. Empty partitions do not appear in `GROUP BY tableoid`; to see empty partitions as well, query the system catalog.

### 11.5. Inspect Indexes Associated with Partitions

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'partition_lifecycle_lab'
ORDER BY tablename, indexname;
```

Do not assume that DETACH deletes all indexes on the old table. The standalone table retains its own indexes/constraints for queries and storage; verify how indexes remain linked or named in the catalog after DDL.

---

## 12. Verifying Partition Pruning with EXPLAIN

### 12.1. Querying a Single Month

Before detaching an active partition in the example, try:

```sql
EXPLAIN
SELECT event_id, tenant_id, event_time
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-04-01 00:00:00+00';
```

If March is attached and no default partition needs scanning, the plan should read only `events_2026_03`.

### 12.2. A Seq Scan on the Right Partition Can Still Be Good

Sample plan:

```text
Seq Scan on events_2026_03
  Filter: (event_time >= ... AND event_time < ...)
```

When March has only 3 rows in the lab, scanning it sequentially is the cheapest choice. **Partition pruning already succeeded** because Jan/Feb partitions were eliminated from the plan even though no B-tree scan was used.

### 12.3. Query Without the Partition Key

```sql
EXPLAIN
SELECT event_id
FROM partition_lifecycle_lab.events
WHERE tenant_id = 10;
```

The predicate `tenant_id` is not the partition key in a `RANGE(event_time)` design. The planner may need to inspect multiple partitions; the `(tenant_id,event_time)` index on each partition can still speed up access within each partition.

### 12.4. Do Not Transform the Partition Key Unnecessarily

```sql
-- Not preferred if you want timestamp range pruning:
-- WHERE event_time::date = DATE '2026-03-15'
```

Casting `TIMESTAMPTZ` to `DATE` is also timezone-dependent and can hinder deriving RANGE bounds. For a UTC day:

```sql
WHERE event_time >= TIMESTAMPTZ '2026-03-15 00:00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-03-16 00:00:00+00'
```

For a business day in another timezone, convert **the two local midnight boundaries** into their corresponding instants and bind typed values.

### 12.5. Runtime Partition Pruning

With prepared statements and certain plan structures, PostgreSQL can prune partitions at **execution time** based on parameter values:

```sql
PREPARE events_by_window(TIMESTAMPTZ, TIMESTAMPTZ) AS
SELECT event_id, event_time
FROM partition_lifecycle_lab.events
WHERE event_time >= $1
  AND event_time < $2;

EXPLAIN EXECUTE events_by_window(
    TIMESTAMPTZ '2026-03-01 00:00+00',
    TIMESTAMPTZ '2026-04-01 00:00+00'
);

DEALLOCATE events_by_window;
```

Do not assume "a generic plan always scans every partition." PostgreSQL supports planning-time and execution-time pruning depending on plan type, parameters, and version. Check `EXPLAIN` for eliminated branches, `Subplans Removed`, or `never executed` where applicable.

---

## 13. Indexes, PRIMARY KEY, and UNIQUE Across ATTACH/DETACH

### 13.1. Each Partition Has Its Own Storage and Indexes

An index declared on the parent governs corresponding indexes on each partition; in this style of declarative partitioning, there is no single global B-tree covering every partition.

Therefore, before attaching a large staging table, check:

- Indexes needed for queries on the new partition.
- Indexes/constraints matching the parent.
- Validity of existing indexes.
- Cost of creating indexes during attach if missing.

### 13.2. Primary Keys Must Include the Partition Key

For our parent:

```sql
PRIMARY KEY (event_time, event_id)
```

PostgreSQL can enforce uniqueness on this composite key through how data is partitioned and constrained across partitions.

However:

```text
event_id=123, event_time=2026-01-10
event_id=123, event_time=2026-02-10
```

are distinct composite keys and are not prevented by the composite PK. If business rules require **`event_id` to be globally unique across the entire system**, you need an additional ID-allocation/enforcement strategy (such as an ID generator service, a dedicated identity lookup table, or redesigning the key model) while accounting for partitioned table uniqueness rules.

### 13.3. Rules for UNIQUE/PRIMARY KEY

On a partitioned parent, a valid unique or primary-key constraint must include all partition key columns under PostgreSQL's rules; expression partition keys also have restrictions when declaring uniqueness on the parent.

Do not mechanically apply regular-table unique syntax to a partitioned parent without verifying the partition scheme.

### 13.4. Indexes After DETACH

When detaching a partition:

- The child table becomes a standalone table.
- Physical indexes on the table still remain, now belonging to the standalone table itself.
- Metadata links with the parent's partitioned indexes/constraints are updated according to DDL rules.
- Re-check `pg_indexes` and `pg_constraint`, especially if archiving independently or attaching to another parent.

Do not assume detaching automatically drops all indexes to save disk space.

---

## 14. Foreign Keys, Triggers, and Lifecycle Dependencies

### 14.1. A Partition Is Not Business-Isolated

A partition may participate in various relationships:

- Foreign keys pointing to other tables.
- Foreign keys from other tables referencing the parent/partition (depending on version capabilities).
- Audit/business triggers.
- Views and materialized views.
- ETL/CDC/logical replication jobs.
- Access privileges, policies, schemas, and storage configurations.

Before running DETACH or DROP, identify **what still references that period's data**.

### 14.2. DROP Can Be Blocked by FKs or Dependencies

`DROP TABLE` will not always succeed if dependent objects exist. **Do not use `CASCADE` just "to make it work"** without reading the full list of affected objects: `CASCADE` can silently drop critical constraints or other objects.

### 14.3. Triggers Can Affect Other Tables

An `INSERT`/`UPDATE` on a parent/partition may fire triggers depending on configuration and version. During attach/detach, evaluate explicitly how triggers are inherited, cloned, or depended upon.

A standalone archive table may no longer be subject to the same routing or policies as when it was a partition. Never assume "it was detached, so all triggers and authorization still behave 100% identically."

### 14.4. Do Not Turn Archived Data into a Privilege Leak

After DETACH, an application might still access the standalone table if granted privileges. However, authorization rules relying on the parent or RLS policies may no longer apply as you expect.

When detaching sensitive data:

1. Review ownership, grants, and RLS on the standalone table.
2. Define which roles are permitted to read the archive.
3. Check encryption/masking and backup policies.
4. Do not simply rename the table and consider the data protected.

---

## 15. Lifecycle Management: Hot, Warm, Archive, Delete

A retention policy can be structured as follows:

| Stage | Example Data Age | Storage Location | Access |
|---|---|---|---|
| **Hot** | 0–30 days | Attached partition, full indexes | Online application |
| **Warm** | 31–90 days | Attached partition, workload-tuned indexes | Reporting/reconciliation |
| **Archive** | 91 days–2 years | Detached table or external storage | Restricted/on-demand |
| **Delete** | Past retention | Drop table/corresponding copies per policy | No longer accessible |

These are **examples**, not mandatory numbers. Financial, healthcare, legal, or personal data systems may have different retention windows, legal holds, and deletion obligations.

### 15.1. Create Partitions Before the Month Starts

For monthly data:

```text
Day 20 of month N:
    prepare partition N+1

Day 01 of month N+1:
    writers already have a valid partition

After month N-3 closes:
    check late events / reconcile
    DETACH partition N-3

After archive is verified:
    DROP standalone table if retention permits
```

Do not wait until INSERTs fail due to a missing partition before creating the next month.

### 15.2. A Partition May Not Align with "Current Month" in Every Timezone

If the partition key is `TIMESTAMPTZ` and bounds are written in UTC, the system's January is **UTC January**. Users in timezone +07 may treat late-evening UTC instants on the last day of the month as the first day of the next local month.

Define clearly:

- Is retention measured in UTC, local calendar date, or business transaction date?
- Where are bounds computed?
- Do client/server timestamps carry timezones?
- Must DST shifts in other markets be handled?

Do not casually treat `event_time::date` under an arbitrary session timezone as the basis for partition retention.

### 15.3. Late-Arriving Events

An event occurring in January that arrives at the server in April may still carry a January `event_time`. If the January partition is already detached:

- Without default or January partition: INSERT into parent fails.
- With default: rows go into default, diluting clean retention.
- If the app overwrites `event_time=received_at` to avoid errors, business facts become corrupted.

Solutions depend on your domain contract:

- Allow a **grace period** before detaching.
- Use dedicated late-event staging and reconciliation.
- Write directly to archive storage via a controlled pipeline.
- Reject overly stale late events with a clear error.

Do not use `ATTACH`/`DETACH` as a substitute for a late-data handling policy.

### 15.4. Legal Hold

If a period is placed under hold due to an investigation or legal obligation, the system **must not automatically DROP** that partition simply because a cron date arrived. Separate determining **time expiration** from **authorization to delete**.

### 15.5. Do Not Forget Backups and Replicas

A detached partition is still protected data if retention requires keeping it. Before dropping:

- Verify the archive has a valid copy.
- Verify backups can be restored.
- Check access permissions, anonymization, and encryption.
- Check replication/CDC status.
- Drop the original only under an approved workflow.

---

## 16. Exporting a Detached Partition

Once `events_2026_01` is standalone, you can export its data as needed.

### 16.1. COPY to Client

In `psql`, for example:

```sql
COPY (
    SELECT event_id, tenant_id, event_time,
           event_type, payload
    FROM partition_lifecycle_lab.events_2026_01
    ORDER BY event_time, event_id
)
TO STDOUT
WITH (FORMAT CSV, HEADER TRUE);
```

This prints CSV to client output. To write a local file from `psql`, you can use the `\copy` meta-command with an **operator-chosen file path** and protected file permissions.

### 16.2. Why Is COPY Not Considered a Full Backup?

A CSV export may omit essential components:

- DDL, indexes, and constraints.
- Ownership, grants, and RLS.
- Triggers and dependencies.
- Types, collations, and other table settings.
- Sequences and related structures.
- Cross-table consistency if exported without a coordinated snapshot.

If you need a recoverable copy as a PostgreSQL table, use an appropriate backup/restore strategy (`pg_dump`, physical backups, etc.) per operational guidelines. CSV works well for data exchange or analytics, not as a drop-in backup replacement.

### 16.3. Reconciling Row Counts

Before export:

```sql
SELECT COUNT(*) AS source_rows
FROM partition_lifecycle_lab.events_2026_01;
```

After export, reconcile:

- Row count.
- Checksums/hashes or sample checks if you have a reliable verification strategy.
- Min/max `event_time` and `event_id`.
- Data schema/version.
- Archive location, permissions, and bucket retention settings.

Matching `COUNT(*)` alone does not prove identical contents, but it is a baseline check.

### 16.4. Detaching Storage Does Not Mean Moving to Cold Storage

If the detached table remains in the same database and tablespace, disk space is still consumed. You may need to:

- Export to object storage.
- Copy/restore into an archive database.
- Move tablespaces when appropriate and governed by a runbook.
- Load into a data warehouse/lake for reporting needs.

Choose based on retrieval patterns, RPO/RTO, cost, and data governance obligations.

---

## 17. Dropping Old Partitions and Batch Deletion

### 17.1. Dropping an Entire Partition Is Usually Cheaper Than Row-by-Row DELETE

Once detached and verified safe to remove:

```sql
-- Run only when you truly want to destroy January data in the lab:
-- DROP TABLE partition_lifecycle_lab.events_2026_01;
```

For retention policies removing **an entire month**, dropping a partition table avoids per-row DELETE overhead and dead-tuple cleanup. Still, DDL carries locks/dependencies and impacts catalogs, backups, replication, and applications.

### 17.2. Can You DROP an Attached Partition Directly?

You can `DROP TABLE` an attached partition directly, subject to PostgreSQL's rules and locks, removing both the partition and its data. However, if you want to:

- Export/archive first,
- Move to another store,
- Inspect the old month's contents, or
- Enforce a waiting window before deletion,

then **detaching first** cleanly separates removing online visibility from final destruction.

### 17.3. DELETE WHERE Date Still Differs from Dropping a Partition

```sql
DELETE FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-01 00:00+00';
```

`DELETE` is row-level DML. It can:

- Write WAL for every row.
- Fire row-level triggers and FK checks.
- Generate dead tuples needing VACUUM.
- Hold locks and cause contention.
- Run for a very long time at large scale.

When the objective is removing **an entire partition**, `DETACH/DROP` is usually worth considering, though **trigger/FK semantics and business guarantees differ**. Do not replace row-level DELETE with DROP if the application relies on delete triggers to clean up other resources.

### 17.4. TRUNCATE Also Has Limits

`TRUNCATE` is fast on many regular tables, but has specific lock, FK, transaction, and parent/partition scoping rules. Do not run `TRUNCATE parent` thinking it "only clears January": it can affect multiple partitions unexpectedly.

If you need to clear an attached or detached partition, target **the exact child table** and verify dependencies. For typical lifecycles, archive then detach/drop is easier to audit.

### 17.5. DROP Does Not Guarantee Data Disappears from All Copies Immediately

After DROP:

- Older backups still hold the data according to backup retention.
- Replicas/CDC pipelines have lag and sync rules.
- Object storage exports retain independent copies.
- Logs, audits, or application caches may still contain information.

Regulatory deletion requirements ("right to erasure" / retention purging) must account for the lifecycle of every copy, not just SQL on the primary.

---

## 18. Monitoring Partition Size and Distribution

### 18.1. Size per Partition

```sql
SELECT
    c.oid::regclass AS relation_name,
    pg_size_pretty(
        pg_total_relation_size(c.oid)
    ) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'partition_lifecycle_lab'
  AND c.relkind = 'r'
ORDER BY pg_total_relation_size(c.oid) DESC;
```

`pg_total_relation_size` includes associated storage components such as the table heap, indexes, and TOAST per the function's definition. Standalone objects after detach still appear in the schema until dropped.

### 18.2. Statistics per Partition

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'partition_lifecycle_lab'
ORDER BY relname;
```

`n_live_tup` and `n_dead_tup` are **estimates** from statistics, not exact row counts at the moment of the SELECT. Live/dead counts shift with workload and stats collection lag.

### 18.3. Check Open Transactions

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Long-running transactions can force DDL to wait on locks or stall phases of `DETACH CONCURRENTLY`. Visibility into other sessions depends on monitoring role privileges.

### 18.4. Check Blocking PIDs

```sql
SELECT
    pid,
    application_name,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

Observe this while an operation is actively blocked. Once the blocking session finishes, the list turns empty; do not conclude that earlier DDL never experienced blocking.

---

## 19. Operational Runbook: ATTACH for a New Period

**Scenario:** On March 20, prepare the April partition.

### Phase A — Design Before the DDL Window

1. Choose UTC/local bounds matching business rules: `[2026-04-01, 2026-05-01)`.
2. Verify the current tree has no overlapping partition.
3. Check whether a default partition exists and whether it holds April data.
4. Estimate row count, indexes, and storage size.
5. Confirm April schema/constraints/indexes match the parent.
6. Plan handling for late events and write access into the new period.

### Phase B — Prepare the Standalone Table

```sql
-- Illustrative example: create only if no April partition exists yet.
CREATE TABLE partition_lifecycle_lab.events_2026_04
(
    LIKE partition_lifecycle_lab.events
      INCLUDING DEFAULTS
      INCLUDING CONSTRAINTS
      INCLUDING INDEXES
);

ALTER TABLE partition_lifecycle_lab.events_2026_04
ADD CONSTRAINT events_2026_04_bounds_chk
CHECK (
    event_time >= TIMESTAMPTZ '2026-04-01 00:00+00'
    AND event_time < TIMESTAMPTZ '2026-05-01 00:00+00'
);
```

On large tables, ensure the CHECK is validated. If staging is still receiving writes, follow a proper protocol to freeze/drain writers before ATTACH.

### Phase C — ATTACH

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_04
FOR VALUES FROM ('2026-04-01 00:00+00')
           TO ('2026-05-01 00:00+00');
```

In production, deploy with a lock timeout, maintenance policy, monitoring, and rollback plan. If default contains April rows, **the command can fail** until that data is handled.

### Phase D — Post-Check

```sql
SELECT *
FROM pg_partition_tree(
    'partition_lifecycle_lab.events'::regclass
);

EXPLAIN
SELECT event_id
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-04-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-05-01 00:00+00';
```

Application-level post-checks should also include controlled test INSERTs, routing verification, "no partition" error metrics, and access policies. These lab checks do not alter production data directly.

---

## 20. Operational Runbook: DETACH and Archive an Old Period

**Scenario:** January has passed its online access window.

### Phase A — Confirm Authorization to Detach

- Has the cutoff for January events passed?
- Has accounting/business reconciliation closed?
- Are there pending late-arriving events to handle?
- Do online queries or reports still need January?
- Are there FKs/dependencies from other tables?
- Is there a legal hold or audit requirement?
- Is a backup/restore plan in place for the data?

### Phase B — Choose the Right Concurrency Mode

For a low-traffic parent or inside a maintenance window:

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_01;
```

For a high-traffic parent **without a default partition** on a supported version:

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_01
CONCURRENTLY;
```

**Choose one of the two**—do not run both consecutively on the same partition. For instance, in the lab, once January was detached in Section 8, it is no longer attached; the second command there is purely syntax reference.

### Phase C — Verify Results

```sql
SELECT COUNT(*) AS parent_january_rows
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-01 00:00+00';

SELECT COUNT(*) AS detached_rows
FROM partition_lifecycle_lab.events_2026_01;
```

If the parent has no remaining partition or default holding January rows, the parent count is 0 while the standalone table retains the old rows.

### Phase D — Archive and Verify

1. Record row count and min/max timestamps.
2. Export or back up in the appropriate format.
3. Verify integrity and restore capability.
4. Register storage location, retention period, access rights, and owner.
5. Monitor replicas/CDC and downstream consumers.

### Phase E — Drop Once Eligible

```sql
-- Only after retention has elapsed and deletion is approved:
-- DROP TABLE partition_lifecycle_lab.events_2026_01;
```

**Core point:** DETACH and DROP are **two separate operational decisions**. Never combine both blindly into a single automated step while skipping archival and verification time.

---

## 21. Automating the Lifecycle Schedule

A system with hundreds of partitions needs a scheduled workflow rather than manual operations keyed off dates in SQL filenames.

### 21.1. Example Monthly Schedule

```text
Daily:
  - check for missing partitions over the next 60 days
  - check row count in default (if present)
  - alert on unprepared partitions

Monthly, before period rollover:
  - create/ATTACH next month's partition
  - verify routing and indexes

Monthly, after old period closes:
  - check retention/legal hold
  - DETACH (with appropriate concurrency)
  - export/archive
  - checksum/restore test
  - DROP once approved
```

This schedule is illustrative; actual cadence depends on data volume and business policy.

### 21.2. Schedulers Must Not Build SQL from Untrusted Input

DDL contains **relation names** and **bounds**; identifiers cannot be bound as query parameters like values in a SELECT. When an application builds partition names from dates or tenant IDs:

- Validate date ranges and valid identifier formats.
- Use proper identifier quoting when generating dynamic SQL.
- Never concatenate user-supplied strings directly into table names or SQL.
- Run with the minimum required DDL privileges.
- Use a coordination lock so two schedulers never create/attach the same period simultaneously.

### 21.3. Operational Idempotency

A partition creation job may be retried after a timeout or crash. Before acting, it should reconcile against **actual catalog state**:

```text
Does April partition already exist?
    |
    +-- Yes: are bounds/DDL/indexes correct?
    |       |
    |       +-- Yes -> treat preparation step as done
    |       +-- No  -> raise conflict, do not overwrite
    |
    +-- No: create staging/attach per runbook
```

Never use `DROP ... CASCADE; CREATE ...` as a "quick retry" on a partition that might already hold live data.

### 21.4. Single DDL Coordinator

Multiple concurrent workers can:

- Race to create the same partition.
- Collide on parent locks.
- Run detach during an attach.
- Leave behind an unhandled pending detach.
- Execute DROP before an export job confirms completion.

Use a single coordinator or durable job state machine distinguishing **PREPARED → ATTACHED → DETACHED → ARCHIVED → VERIFIED → DELETED** along with error and retry branches.

### 21.5. Do Not Assume Every Step Rolls Back Like a Single Transaction

Some DDL can run inside a transaction, whereas `DETACH ... CONCURRENTLY` cannot run inside an explicit transaction block and spans multiple phases. Exporting to external storage also cannot be rolled back by PostgreSQL.

Therefore, the workflow must include:

- State checkpoints.
- Post-verification steps.
- Idempotent retries where safe.
- Recovery procedures on mid-flight interruption.

This is the hallmark of a **lifecycle management workflow**, not just a single SQL statement.

---

## 22. Common Operational Mistakes

### 22.1. Attaching with Wrong Bounds

If you name a table `events_2026_04` with bounds:

```sql
FOR VALUES FROM ('2026-04-01') TO ('2026-06-01')
```

the table spans **two months**, even though its name says April. PostgreSQL obeys DDL bounds, not calendar assumptions inferred from table names.

### 22.2. Timezone Mismatch

A script computes months in local timezone but writes misaligned UTC bounds. Rows near midnight may land in a different partition than business reports expect. Verify boundaries with explicit timezone-aware timestamps.

### 22.3. Forgetting the Next Month

No partition and no default → INSERT fails. Having a default → rows pile up in default, making subsequent attach harder.

### 22.4. Trusting Table Names Instead of the Catalog

A table named `events_2026_01` might be standalone after DETACH or attached with different bounds. Authoritative state comes from `pg_partition_tree`, `pg_inherits`, and `pg_get_expr(relpartbound, ...)`.

### 22.5. Running DETACH CONCURRENTLY Inside a Migration Transaction

A framework wrapping migrations in `BEGIN` makes the command invalid. Use non-transactional migration execution or choose regular DETACH with lock planning.

### 22.6. Using CONCURRENTLY When a Default Partition Exists

PostgreSQL does not support that combination. Do not ignore the error and assume the partition was detached.

### 22.7. Ignoring Pending Detach

If CONCURRENTLY is interrupted, a partition may remain pending. Inspect the catalog and run `FINALIZE` appropriately before subsequent operations.

### 22.8. Checking Only Counts After DETACH

`COUNT(*)` between parent and standalone verifies visibility, not checksums, indexes/constraints, backups, or archive access controls.

### 22.9. Assuming Disk Drops Right After DETACH

The standalone table still exists and consumes storage. Reclaiming space from old data requires dropping or moving it per policy.

### 22.10. Dropping Without Checking Legal Hold

Dropping an entire month can violate retention obligations. Use a separate retention-hold state and approval gate before any irreversible step.

---

## 23. Comparing ATTACH/DETACH with DELETE, VACUUM, and DROP

| Operation | Changes Parent Row Set? | Original Data Still Kept? | Purpose |
|---|---|---|---|
| `ATTACH PARTITION` | Parent begins seeing rows of attached table | Yes, now as a partition | Bring table into tree |
| `DETACH PARTITION` | Parent stops seeing rows of detached partition | **Yes**, in standalone table | Remove from online queries / prep archive |
| `DELETE WHERE ...` | Deletes matching rows transactionally | Committed rows removed, dead tuples need VACUUM | Selective row deletion |
| `TRUNCATE` | Removes rows on target table per command scope | Not an archive mechanism | Fast bulk table clearing, strong lock |
| `DROP TABLE partition` | Partition and data removed from database | **Table no longer exists** | Drop entire period when authorized |
| `VACUUM` | Does not logically change live rows | Not partition removal | Reclaim/reuse eligible tuple storage |

Do not swap these commands mechanically. `DELETE` has different row-level triggers, FK behavior, and MVCC effects than `DROP`. `VACUUM` is not a retention decision. `ATTACH` and `DETACH` manage **membership**, not security or archival policies.

---

## 24. Advanced Scenario: Multi-Level Partitioning

PostgreSQL supports **subpartitioning**, such as RANGE by month followed by HASH by tenant:

```text
events parent, RANGE(event_time)
   |
   +-- events_2026_03, HASH(tenant_id)
          |
          +-- events_2026_03_h0
          +-- events_2026_03_h1
          +-- events_2026_03_h2
          +-- events_2026_03_h3
```

### 24.1. Attaching a Subtree

An attached table can itself be a partitioned table with child partitions. When PostgreSQL must verify data falls within bounds, scanning and locking can **traverse down to leaf partitions** unless sufficient CHECK constraints prove the bounds.

### 24.2. Detaching an Entire Month

If the parent partitions by month at the top level, detaching the monthly partition detaches **the entire subtree** from the parent, making structured archival of the whole period convenient.

However:

- Direct queries on the subtree can still read data.
- Leaf tables, indexes, and constraints still exist in the database.
- Multiple relations must be sized and backed up.
- FKs, dependencies, and locking become more complex.

### 24.3. Do Not Over-Partition Thinking "Smaller Is Always Faster"

Every partition adds catalog metadata, indexes, and planning/DDL work. Too many partitions can increase:

- Planning time.
- Number of files/relations to manage.
- Autovacuum and statistics overhead.
- DDL and backup costs.
- Operational and permissions complexity.

Choose monthly/daily/hourly granularity based on **data volume, query patterns, retention granularity, and management cost**, not the slogan "smaller partitions are always better."

---

## 25. Practice Exercises with Answers

### Exercise 1 — Does RANGE Include the Upper Bound?

Partition:

```sql
FOR VALUES FROM ('2026-03-01 00:00+00')
           TO ('2026-04-01 00:00+00')
```

**Question:** Does a row at exactly `2026-04-01 00:00+00` belong to the March partition?

**Answer:** No. `FROM` is inclusive, `TO` is exclusive. That row belongs to April if a matching partition exists.

### Exercise 2 — Role of ATTACH

**Question:** Does attaching a 5-million-row table copy 5 million rows into a new relation by default?

**Answer:** No. It attaches the existing table as a partition. However, it may scan to validate data, reconcile/create indexes, and hold locks.

### Exercise 3 — Distinguish CREATE PARTITION OF and ATTACH

**Answer:** `CREATE TABLE ... PARTITION OF` creates a new empty partition directly; `ATTACH PARTITION` attaches an **existing table** with valid structure and rows into the parent.

### Exercise 4 — Write ATTACH for April

**Answer:**

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_04
FOR VALUES FROM ('2026-04-01 00:00+00')
           TO ('2026-05-01 00:00+00');
```

Run only when the April table already exists, matches the schema, and has no overlapping bounds.

### Exercise 5 — How CHECK Helps Skip Scans

**Question:** Why prepare a validated CHECK on staging before ATTACH?

**Answer:** So PostgreSQL has proof that all staging rows lie within the partition bounds, allowing it to skip scanning the whole staging table during attach and reducing lock hold time.

### Exercise 6 — Insufficiently Tight CHECK

March staging has `CHECK (event_time >= '2026-01-01')`. Is that enough to prove March bounds?

**Answer:** No, because the CHECK still permits February/April rows. You need a validated constraint covering both the lower and upper bounds of March.

### Exercise 7 — NOT VALID

**Question:** Is a newly added CHECK with `NOT VALID` accepted as proof that existing rows are valid?

**Answer:** Not yet. `VALIDATE CONSTRAINT` must complete successfully before it can be relied upon to skip the validation scan.

### Exercise 8 — ATTACH When Default Contains April Rows

Default holds April rows and you attach the April partition. What happens?

**Answer:** PostgreSQL must verify default holds no rows in the new bounds. If it still does, attach fails. You must move the data consistently and prevent races with concurrent writers.

### Exercise 9 — ATTACH Locking

**Answer:** ATTACH requires `SHARE UPDATE EXCLUSIVE` on the parent and can acquire `ACCESS EXCLUSIVE` on the table being attached/default during verification, so prepare CHECKs/indexes ahead of time and monitor DDL.

### Exercise 10 — DETACH Does Not Delete Data

**Question:** After `DETACH PARTITION events_2026_01`, will SELECT through parent see January? Does the January table still exist?

**Answer:** The parent no longer sees rows from that partition; `events_2026_01` still exists as a standalone table and can be queried directly.

### Exercise 11 — Disk After DETACH

**Answer:** Disk usage does not decrease automatically just from detaching. The standalone table still stores data/indexes; archive and drop per policy to reclaim storage.

### Exercise 12 — DETACH CONCURRENTLY Inside BEGIN

```sql
BEGIN;
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_02
CONCURRENTLY;
COMMIT;
```

**Answer:** Invalid. `DETACH ... CONCURRENTLY` cannot run inside an explicit transaction block.

### Exercise 13 — DEFAULT and CONCURRENTLY

The parent has a default partition. Can `DETACH ... CONCURRENTLY` be used?

**Answer:** No, under current PostgreSQL restrictions. Choose a different workflow or redesign the default strategy.

### Exercise 14 — Pending Detach

**Question:** A concurrent detach operation was interrupted between its two phases. What should you do?

**Answer:** Inspect pending detach status in the catalog, identify the incomplete operation, and run `ALTER TABLE ... DETACH PARTITION ... FINALIZE` when appropriate—do not blindly start a fresh detach.

### Exercise 15 — Why Partition Pruning Is Not an Index Scan

The plan shows only `Seq Scan on events_2026_03`, without January or February.

**Answer:** PostgreSQL already pruned the irrelevant partitions. A Seq Scan inside a small March partition can still be optimal.

### Exercise 16 — Pruning-Friendly Query

**Requirement:** Find March rows in UTC.

```sql
SELECT event_id
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-03-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-04-01 00:00+00';
```

### Exercise 17 — Parent Primary Key

**Question:** Why does the `RANGE(event_time)` parent use PK `(event_time,event_id)` instead of PK on `event_id` alone?

**Answer:** UNIQUE/PK rules on a partitioned parent require including the partition key, because there is no general global unique index across all partitions. A composite PK does not prevent duplicate `event_id` values across different months.

### Exercise 18 — DELETE vs DROP

**Question:** Does deleting 10 million January rows with `DELETE` have the same consequences as dropping a January partition?

**Answer:** No. DELETE is row-by-row DML with different triggers, FKs, WAL, and MVCC behavior. DROP removes the entire relation and data, requiring retention, permissions, and dependency verification.

### Exercise 19 — Late Events

A January event arrives in April after January is detached and the parent has no default partition.

**Answer:** Inserting with a January `event_time` finds no valid partition and fails. You need a grace period, staging/archive pipeline, or late-event rejection policy; never rewrite original business timestamps silently.

### Exercise 20 — Exports Do Not Replace Backups

**Question:** Does CSV `COPY` of a detached table preserve PKs, indexes, triggers, and permissions?

**Answer:** Not completely. CSV preserves exported row values; for a table-level recoverable copy in PostgreSQL, use proper backups/DDL and restore testing.

### Exercise 21 — Managing Legal Hold

January has passed its retention period but is under legal hold.

**Answer:** Do not drop automatically. Separate deletion eligibility/approval from date-based scheduling.

### Exercise 22 — Identifying Partitions in the Catalog

**Requirement:** State how to check actual bounds.

**Answer:** Join `pg_inherits` with `pg_class` and inspect `pg_get_expr(child.relpartbound, child.oid)`; do not rely on table names alone to prove bounds.

### Exercise 23 — ATTACH CONCURRENTLY

**Question:** Is there an `ALTER TABLE ... ATTACH PARTITION ... CONCURRENTLY` syntax like DETACH?

**Answer:** No. To minimize ATTACH disruption, prepare staging, validated CHECK constraints, indexes, default-partition checks, and lock timeouts.

### Exercise 24 — Repeatable Workflow

**Question:** The scheduler retries after a timeout, but April is already attached. Should it `DROP April` and recreate it to be safe?

**Answer:** No. Inspect the catalog, bounds, indexes, and state. If already valid, treat the step as complete; if conflicting, alert and investigate. Never destroy live data with DROP just to force idempotency.

### Exercise 25 — Retention Stages

**Requirement:** Draw the lifecycle sequence.

**Answer:**

```text
PREPARED
    -> ATTACHED / ONLINE
    -> CLOSED / VERIFIED
    -> DETACHED
    -> EXPORTED / ARCHIVED
    -> RESTORE-TESTED
    -> DELETED (once retention expires and no legal hold applies)
```

### Exercise 26 — Distinguishing DROP and Archival

**Question:** Does a detached partition sitting in the same tablespace and database count as "archived to cold storage"?

**Answer:** Not by default. It is still a standalone table stored in the database; cold storage typically requires exporting/moving it along with distinct access policies.

---

## 26. Pre-Production Checklist for ATTACH/DETACH

### Partition Design

1. **Partition key and bounds:** Accurate, non-overlapping, half-open upper bounds.
2. **Timezone:** Explicit UTC or clearly converted local boundaries.
3. **Partition granularity:** Daily/monthly/hourly balancing query pruning and management overhead.
4. **Primary key/unique:** Includes partition key per PostgreSQL rules; global uniqueness addressed.
5. **Indexes/constraints:** Consistent with parent, suited for queries and write throughput.

### ATTACH

6. **Staging table:** Exact columns, types, `NOT NULL`, `DEFAULT`, and required structure.
7. **Staging data:** Entirely within bounds with outlier checks passed.
8. **Validated CHECK:** Tight enough to prove bounds and skip the attach validation scan where possible.
9. **Pre-built indexes:** Avoid building huge indexes under DDL locks.
10. **Default partition:** Contains no rows in the new bounds, or rows migrated consistently.
11. **Locks/timeouts:** Understand how parent/child/default may be locked.
12. **Pruning and routing:** Verify queries and test INSERTs after attach.

### DETACH

13. **Old period closed:** No active normal writers or unresolved late events.
14. **Regular vs CONCURRENTLY:** Account for lock, transaction, and default-partition restrictions.
15. **Never wrap CONCURRENTLY in BEGIN:** Migration runner must support non-transactional execution.
16. **Pending detach:** Have a catalog inspection and `FINALIZE` recovery runbook.
17. **Foreign keys/dependencies:** Identify impact on the standalone table.
18. **Permissions/RLS:** Prevent archived data from leaking outside authorized roles.

### Archive / Delete

19. **Row counts and boundaries:** Reconcile before/after; verify samples/hashes where needed.
20. **Backup/export:** Valid format, restore-tested, with an archival manifest.
21. **Retention/legal hold:** Drop only when both policy and approval permit.
22. **DROP vs DETACH:** Remember DETACH keeps disk storage; only DROP removes the relation.
23. **Replicas/CDC:** Understand how schema/data changes replicate and affect consumers.
24. **Resource monitoring:** Watch DDL locks, waits, WAL, disk, and autovacuum.

### Automation

25. **Idempotent scheduler:** Never create duplicates or blindly drop on retry.
26. **Single DDL coordinator:** Prevent competing attach/detach runs on the same parent.
27. **Deadlines and alerts:** Next month's partition ready well before rollover.
28. **Recovery workflow:** If attach/detach/export is interrupted, verify state and resume safely.

---

## 27. Summary

**`ATTACH PARTITION` integrates an existing table into the partition tree; `DETACH PARTITION` converts an attached partition back into a standalone table.** Together they allow lifecycle management without moving or deleting rows individually in appropriate workloads.

Remember the core principles:

- **RANGE partitions use half-open intervals**: `FROM` is inclusive, `TO` is exclusive. Bounds must align with the business timezone.
- **ATTACH may scan the entire staging table and default partition**. Create/validate tight `CHECK` constraints and pre-build indexes to minimize work inside the DDL window.
- **ATTACH acquires locks**, even though rows are not copied into a new table.
- **Regular DETACH takes a strong lock on the parent**; `DETACH ... CONCURRENTLY` lowers lock strength but **cannot run inside a transaction block** and **cannot be used when a default partition exists**.
- **CONCURRENTLY can leave a pending detach if interrupted**; inspect state and use `FINALIZE` when appropriate.
- **DETACH does not delete data or free storage**. The old table remains intact, making archival/backup/verification and DROP distinct steps.
- **Pruning does not mean an Index Scan**. A Seq Scan targeting only the needed partition can be completely optimal.
- **Do not treat partitioning as a replacement for UNIQUE/FK/RLS/backups**. Design invariants, access controls, and dependencies across the entire lifecycle.
- **Retention requires business workflows**: handling late events, legal holds, replicas/CDC, restore testing, and deletion approvals.

**Final question for every data period:** "Has the new partition been prepared with validated bounds? Is the old partition truly cleared to leave online storage and eligible for deletion? And if the operation fails mid-way, what state are the catalog and data in, and how can we recover safely?"

### Official PostgreSQL Documentation

- [Table Partitioning — Declarative Partitioning, Partition Maintenance](https://www.postgresql.org/docs/current/ddl-partitioning.html).
- [ALTER TABLE — ATTACH PARTITION, DETACH PARTITION, CONCURRENTLY, FINALIZE](https://www.postgresql.org/docs/current/sql-altertable.html).
- [CREATE TABLE — PARTITION OF, FOR VALUES, DEFAULT](https://www.postgresql.org/docs/current/sql-createtable.html).
- [Partition Pruning and the Planner](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING).
- [Indexes on Partitioned Tables](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE-MAINTENANCE).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Catalog pg_inherits](https://www.postgresql.org/docs/current/catalog-pg-inherits.html).
- [Partition Information Functions](https://www.postgresql.org/docs/current/functions-admin.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [COPY](https://www.postgresql.org/docs/current/sql-copy.html), [DROP TABLE](https://www.postgresql.org/docs/current/sql-droptable.html).
