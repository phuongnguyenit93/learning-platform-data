# ADD, DROP, TRUNCATE, REORGANIZE, and COALESCE PARTITION

Partitioning divides a table's data into multiple partitions managed by MySQL. When a table is partitioned appropriately for its data domain and workload, operators can add new data ranges, drop expired ranges, empty a partition, split/merge boundaries, or change the partition count of HASH/KEY tables. These operations are typically performed with `ALTER TABLE` and can directly affect data, lock duration, disk space, replication, and recoverability.

The five operations to distinguish are `ADD PARTITION`, `DROP PARTITION`, `TRUNCATE PARTITION`, `REORGANIZE PARTITION`, and `COALESCE PARTITION`. They are not interchangeable: `DROP` removes both the partition definition and its data; `TRUNCATE` keeps the partition while deleting its data; `REORGANIZE` redistributes data across RANGE/LIST partitions; `COALESCE` reduces the number of HASH/KEY partitions and redistributes data. Choosing the wrong statement can destroy data or trigger an unexpected large rebuild/flush.

This lesson belongs to the `DATABASE_MYSQL` module, where you master table design, data types, keys, SQL queries, indexes, transactions, concurrency control, execution plan reading, query optimization, and relational database operations. The goal is to manage partition lifecycles safely, understand method-specific limits, and verify outcomes via metadata and real data.

After this lesson, you will be able to:

- Choose the right partition management operation for RANGE, LIST, HASH, or KEY.
- Add new partitions with `ADD PARTITION` when boundary conditions allow.
- Remove partitions and their data with `DROP PARTITION`.
- Empty data while preserving the partition definition with `TRUNCATE PARTITION`.
- Split or merge RANGE/LIST partitions with `REORGANIZE PARTITION`.
- Reduce the number of HASH/KEY partitions with `COALESCE PARTITION`.
- Understand the impact of `MAXVALUE`, unique keys, and foreign key restrictions.
- Verify partition metadata, row counts, and query pruning.
- Design maintenance workflows with controls for data, DDL, locks, backups, and replication.

## 1. Choosing Operations by Partitioning Method

Each operation has a distinct scope of support. The table below is a practical guide for user-defined partitioning in MySQL:

| Operation | RANGE / LIST | HASH / KEY | Primary effect |
| --- | --- | --- | --- |
| `ADD PARTITION` | Yes | Yes | RANGE/LIST: add a new range or value list; HASH/KEY: increase partition count by the specified number |
| `DROP PARTITION` | Yes | No; use `COALESCE` to reduce partition count | Deletes the partition and all data inside it |
| `TRUNCATE PARTITION` | Yes | Yes | Deletes data inside the partition while keeping the partition definition |
| `REORGANIZE PARTITION` | Yes | No | Splits/merges or changes boundaries/value groups while redistributing data |
| `COALESCE PARTITION` | No | Yes | Reduces the number of HASH/KEY partitions and redistributes data |

For HASH/KEY, use `ADD PARTITION PARTITIONS n` to add `n` partitions; use `COALESCE PARTITION n` to remove `n` partitions. This syntax differs from RANGE/LIST, where `ADD PARTITION` declares new partition definitions. Never use `REORGANIZE PARTITION` on HASH/KEY. Increasing or decreasing HASH/KEY partitions can redistribute data and generate heavy I/O; efficiency exceptions may exist for LINEAR HASH/KEY.

## 2. Inspecting a Partitioned Table Before Maintenance

Before running DDL, verify the partitioning method, partitioning expression, and current boundaries.

```sql
SHOW CREATE TABLE event_log;
```

`SHOW CREATE TABLE` is the authoritative source for viewing the full partition definition, including:

- `PARTITION BY RANGE`, `LIST`, `HASH`, or `KEY`.
- The expression/columns used for partitioning.
- The name of each partition.
- `VALUES LESS THAN` or `VALUES IN`.
- `MAXVALUE` if present.
- The partition count for HASH/KEY.

Metadata can also be queried via `INFORMATION_SCHEMA.PARTITIONS`:

```sql
SELECT
    PARTITION_ORDINAL_POSITION,
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'event_log'
ORDER BY PARTITION_ORDINAL_POSITION;
```

With InnoDB, `TABLE_ROWS` is an estimate rather than an exact row count. When you need exact row counts before and after an operation, run `COUNT(*)` over an appropriate range or query a specific partition:

```sql
SELECT COUNT(*) AS rows_in_partition
FROM event_log PARTITION (p2026_11);
```

`PARTITION (...)` inside `SELECT` is explicit partition selection. It is useful for verification or targeted queries, but does not replace automatic optimizer partition pruning.

## 3. Creating the RANGE COLUMNS Table Used in Examples

Example daily log table:

```sql
DROP TABLE IF EXISTS event_log;

CREATE TABLE event_log (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    tenant_id INT UNSIGNED NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (event_id, event_date),
    KEY idx_event_date_tenant (event_date, tenant_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p_before_2026_10 VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026_10 VALUES LESS THAN ('2026-11-01'),
    PARTITION p2026_11 VALUES LESS THAN ('2026-12-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

With `RANGE COLUMNS(event_date)`, partitions are ordered by strictly increasing boundaries:

- `p_before_2026_10` holds dates before 2026-10-01.
- `p2026_10` holds dates from 2026-10-01 up to before 2026-11-01.
- `p2026_11` holds dates from 2026-11-01 up to before 2026-12-01.
- `pmax` holds all remaining values from 2026-12-01 onward.

Insert test data:

```sql
INSERT INTO event_log
    (event_id, event_date, tenant_id, event_type, payload)
VALUES
(1, '2026-10-15', 10, 'LOGIN', JSON_OBJECT('user', 'an')),
(2, '2026-11-05', 10, 'ORDER', JSON_OBJECT('order_id', 9001)),
(3, '2026-11-20', 20, 'PAYMENT', JSON_OBJECT('amount', 125.50)),
(4, '2026-12-03', 10, 'LOGOUT', JSON_OBJECT('user', 'an'));
```

This is the initial fixture state. The subsequent DDL examples are standalone maintenance scenarios, not a single migration script meant to be executed sequentially from start to finish. Before each operation, verify that the named partitions still exist with the expected boundaries; to restore the initial fixture, re-run this entire section.

`pmax` is a catch-all partition for values without a dedicated partition yet. It prevents errors when future data arrives, yet once `MAXVALUE` exists you cannot simply `ADD PARTITION` after it. To create a new monthly partition before `pmax`, you must `REORGANIZE` partition `pmax` to split out part of its value range.

### 3.1. Notes on Unique Keys and Foreign Keys

For a partitioned table, every column used in the partitioning expression must appear in every unique key of the table, including the primary key. In the example, `event_date` is inside primary key `(event_id, event_date)`. Adding a standalone `UNIQUE(event_id)` would be rejected by MySQL because that unique key omits the partitioning column.

This has a design implication: `PRIMARY KEY(event_id, event_date)` only enforces uniqueness of the pair, not table-wide uniqueness of `event_id` alone. If business rules require globally unique IDs, consider generating collision-free IDs at the application layer or maintaining an unpartitioned registry table with a unique key on `event_id`.

InnoDB with user-defined partitioning does not support foreign key constraints on partitioned tables; nor can partitioned tables be referenced by foreign keys in the usual way. If business logic depends on FKs, re-evaluate the data model before partitioning. Never drop constraints without replacing them with an equivalent integrity safeguard.

## 4. ADD PARTITION — Adding New Partitions

`ADD PARTITION` has different syntax depending on the partitioning method: RANGE/LIST declares new partitions with boundaries or value sets; HASH/KEY specifies the number of partitions to add.

### 4.1. ADD for RANGE When No MAXVALUE Exists

For a RANGE table without a `MAXVALUE` partition, you can add a partition at the end of the current range. The example below creates a small lab table and adds the next month's partition:

```sql
CREATE TABLE event_log_without_max (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    PRIMARY KEY (event_id, event_date)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p_before_2026_12 VALUES LESS THAN ('2026-12-01'),
    PARTITION p2026_12 VALUES LESS THAN ('2027-01-01')
);

ALTER TABLE event_log_without_max
ADD PARTITION (
    PARTITION p2027_01 VALUES LESS THAN ('2027-02-01')
);
```

Key conditions:

- The table must be partitioned by RANGE.
- The new partition must validly extend the end of the partition list.
- The new RANGE bound must be strictly greater than the current highest bound.
- You cannot add a partition after a `MAXVALUE` partition.
- Partition names must not collide with existing names.

The example above uses the illustrative table `event_log_without_max`; the `event_log` table in section 3 already has `pmax`, so that exact ADD statement cannot be applied to it.

### 4.2. ADD for LIST

With LIST partitioning, a new partition receives values not yet assigned to any existing partition:

```sql
CREATE TABLE regional_events (
    event_id BIGINT UNSIGNED NOT NULL,
    region_id INT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    PRIMARY KEY (event_id, region_id)
) ENGINE = InnoDB
PARTITION BY LIST COLUMNS (region_id) (
    PARTITION p_north VALUES IN (1, 2),
    PARTITION p_south VALUES IN (3, 4)
);

ALTER TABLE regional_events
ADD PARTITION (
    PARTITION p_central VALUES IN (5, 6)
);
```

Do not repeat values already belonging to another partition. Every valid value must map to exactly one partition; if no matching partition exists, `INSERT` fails.

### 4.3. ADD for HASH/KEY

For HASH or KEY tables, `ADD PARTITION PARTITIONS n` increases the total partition count by `n`. No individual partition names or boundaries are declared:

```sql
DROP TABLE IF EXISTS session_hash_add;

CREATE TABLE session_hash_add (
    session_id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    PRIMARY KEY (session_id, customer_id)
) ENGINE = InnoDB
PARTITION BY HASH (customer_id)
PARTITIONS 8;

ALTER TABLE session_hash_add
ADD PARTITION PARTITIONS 2;
```

If the table currently has 8 partitions, the statement above increases the total to 10. The number `2` is the number of partitions added, not the target total partition count.

Unlike RANGE/LIST, increasing the HASH/KEY partition count changes the mapping of many rows. For standard HASH/KEY, MySQL must redistribute data across partitions; LINEAR HASH/LINEAR KEY can reduce data movement. Measure temporary space, I/O, DDL duration, metadata locks, and replication lag before applying on large tables.

### 4.4. When MAXVALUE Already Exists

Suppose `pmax` currently holds all dates from 2026-12-01 onward. To create a December 2026 partition, split `pmax` into the December partition and a new `pmax`:

```sql
ALTER TABLE event_log
REORGANIZE PARTITION pmax INTO (
    PARTITION p2026_12 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

December rows already sitting in `pmax` are redistributed into `p2026_12`; rows from 2027-01-01 onward remain in `pmax`. This is a `REORGANIZE`, not an `ADD`, because it splits a range already covered by the `MAXVALUE` partition.

## 5. DROP PARTITION — Deleting a Partition and Its Data

`DROP PARTITION` deletes the partition definition along with all data stored inside that partition. It does not move data into another partition.

Example:

```sql
ALTER TABLE event_log
DROP PARTITION p2026_10;
```

After this operation:

- Partition `p2026_10` no longer exists.
- Rows in that partition spanning 2026-10-01 up to before 2026-11-01 are removed from the table.
- The remaining partitions still exist.
- Data in `p2026_11` and `pmax` is not deleted by this statement.

`DROP PARTITION` applies to RANGE/LIST. For HASH/KEY, use `COALESCE PARTITION` if the goal is to reduce the partition count.

### 5.1. DROP vs. DELETE

| Criterion | `DELETE FROM ... WHERE ...` | `ALTER TABLE ... DROP PARTITION` |
| --- | --- | --- |
| Scope | Rows matching the predicate | All data in the specified partition |
| Partition definition | Preserved | Partition is removed |
| Predicate | Can filter by row conditions | Selects only by partition name |
| Typical goal | Delete a specific business subset of rows | Permanently remove an expired data range |
| Rollback capability | Transactional DML; can roll back before commit | DDL with implicit commit; cannot use ROLLBACK to restore a dropped partition |

Before dropping:

1. Confirm the exact schema, table, and partition name.
2. Count or inspect the data range to be removed.
3. Archive/export data if historical retention is required.
4. Verify backups and recovery capability.
5. Check whether queries, reports, or replication depend on that data range.
6. Run during an appropriate maintenance window and verify after DDL.

Do not use `DROP PARTITION` just to shrink a table if the data is still subject to retention or audit requirements.

## 6. TRUNCATE PARTITION — Deleting Data While Keeping the Partition

`TRUNCATE PARTITION` empties one or more specified partitions while preserving their partition definitions. It is a way to clear a data region for reuse without altering partition boundaries.

Example:

```sql
ALTER TABLE event_log
TRUNCATE PARTITION p2026_11;
```

Partition `p2026_11` still exists with the same November 2026 boundaries, but all data inside it is deleted.

Multiple partitions can be truncated at once:

```sql
ALTER TABLE event_log
TRUNCATE PARTITION p2026_10, p2026_11;
```

The example above is only valid if those partitions still exist. Do not run it after they have been dropped.

In this lesson's running examples, `p2026_10` was dropped in section 5. To test this multi-partition TRUNCATE statement, restore the fixture from section 3 first or omit `p2026_10` from the list.

### 6.1. TRUNCATE vs. DROP

| Operation | Partition definition | Data inside | Can future INSERTs use that range? |
| --- | --- | --- | --- |
| `DROP PARTITION p` | Deleted | Deleted | Not under the old partition; a matching partition must be defined first |
| `TRUNCATE PARTITION p` | Preserved | Deleted | Yes, the partition continues accepting data in its range |

### 6.2. TRUNCATE PARTITION vs. Predicate DELETE

`DELETE` removes matching rows one by one and incurs undo, redo, trigger, and row-level work proportional to row count. `TRUNCATE PARTITION` is a partition-level DDL operation, not a conditional DELETE; it triggers an implicit commit and truncated data cannot be rolled back with a regular `ROLLBACK`.

Before truncating, be certain the partition contains only data permitted to be deleted. If you only want to delete a subset of rows inside a partition, use `DELETE` with an appropriate predicate instead of truncating the entire partition.

## 7. REORGANIZE PARTITION — Splitting or Merging RANGE/LIST Partitions

`REORGANIZE PARTITION` changes how data is divided among one or more RANGE/LIST partitions. Existing rows in the specified partitions are redistributed according to the new definitions.

Common use cases:

- Splitting one large partition into multiple smaller partitions.
- Merging several partitions into one larger partition.
- Splitting `MAXVALUE` to carve out a partition for a new interval.
- Changing value groups in LIST partitioning.

### 7.1. Splitting a RANGE Partition

Suppose `p2026_11` currently covers 2026-11-01 up to before 2026-12-01. To split it into two half-months:

```sql
ALTER TABLE event_log
REORGANIZE PARTITION p2026_11 INTO (
    PARTITION p2026_11a VALUES LESS THAN ('2026-11-16'),
    PARTITION p2026_11b VALUES LESS THAN ('2026-12-01')
);
```

The new boundaries must cover the exact range previously represented by the old partition:

- `p2026_11a`: from 2026-11-01 up to before 2026-11-16.
- `p2026_11b`: from 2026-11-16 up to before 2026-12-01.

Existing rows in `p2026_11` are distributed across the two new partitions by `event_date`. No rows are lost as long as the new definitions match the old range.

### 7.2. Merging RANGE Partitions

If two adjacent partitions have compatible boundaries, they can be merged:

```sql
ALTER TABLE event_log
REORGANIZE PARTITION p2026_11a, p2026_11b INTO (
    PARTITION p2026_11 VALUES LESS THAN ('2026-12-01')
);
```

After the operation, data from both partitions is merged into the new partition `p2026_11`. The total covered value range must match the prior range; never leave gaps or overlapping boundaries.

### 7.3. Splitting MAXVALUE

The example in section 4.4 is an important form of REORGANIZE: splitting `pmax` into a specific monthly partition and a new `pmax`. When managing monthly tables, this is the standard way to create new partitions when keeping a catch-all partition.

If `pmax` already contains future data, MySQL must redistribute those rows into the new partition. Evaluate data movement volume and DDL duration before running.

### 7.4. REORGANIZE LIST

For LIST partitioning, the values of the old partitions must be fully redistributed into the new partitions. For example:

```sql
ALTER TABLE regional_events
REORGANIZE PARTITION p_north INTO (
    PARTITION p_north_1 VALUES IN (1),
    PARTITION p_north_2 VALUES IN (2)
);
```

The old partition contained values 1 and 2; the new definition splits that value set into two partitions. Do not omit any value and do not assign the same value to multiple partitions.

### 7.5. Key Conditions for REORGANIZE

- Only supported for RANGE/LIST partitioning.
- The new definitions must cover the exact value domain of the reorganized old partitions.
- New partition names must be valid and unique.
- Existing data must be distributable under the new definitions.
- For RANGE with `MAXVALUE`, ensure the new last partition still handles all remaining values.
- Evaluate data movement volume, DDL duration, metadata locks, and I/O.

Never treat REORGANIZE as a metadata-only rename. Whenever boundaries change, MySQL may have to read and rewrite rows to redistribute them.

## 8. COALESCE PARTITION — Reducing HASH/KEY Partition Count

`COALESCE PARTITION` applies to tables partitioned by HASH or KEY. It reduces the number of partitions and redistributes data across the remaining partitions.

Create a lab HASH table:

```sql
DROP TABLE IF EXISTS session_hash;

CREATE TABLE session_hash (
    session_id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (session_id, customer_id),
    KEY idx_session_hash_customer (customer_id)
) ENGINE = InnoDB
PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

Reduce from 8 partitions down to 6:

```sql
ALTER TABLE session_hash COALESCE PARTITION 2;
```

The parameter `2` is the number of partitions to remove from the total partition count; InnoDB redistributes data according to the remaining HASH/KEY definition. Specific partition names are not chosen in `COALESCE`.

### 8.1. COALESCE vs. DROP PARTITION

- `DROP PARTITION` removes a named partition and all data inside it; used with RANGE/LIST.
- `COALESCE PARTITION n` reduces the HASH/KEY partition count and redistributes rows; it does not arbitrarily delete a subset of data.

With HASH/KEY, reducing the partition count does not lose data. Rows remain in the table, while their partition placement is recomputed for the new partition count.

### 8.2. Increasing HASH/KEY Partition Count

To increase the existing partition count, use `ADD PARTITION PARTITIONS n`:

```sql
ALTER TABLE session_hash
ADD PARTITION PARTITIONS 4;
```

For example, a table with 8 partitions will have 12 partitions after this statement. This is the way to add partitions while keeping the current partitioning method/expression. With non-linear HASH/KEY, the operation may copy/redistribute data across partitions; with LINEAR HASH/KEY, data movement cost can be lower.

Only use `ALTER TABLE ... PARTITION BY HASH/KEY (...) PARTITIONS n` when you need to change the partitioning expression or method, not as the routine way to merely change partition count. Changing the partitioning scheme can rebuild the table structure and copy data; check supported `ALGORITHM`/`LOCK` options, test in staging, and plan a maintenance window.

## 9. Impact of Partition Maintenance on DDL and Transactions

All partition management commands above are `ALTER TABLE` operations. DDL in MySQL follows implicit commit rules; never place a DROP/TRUNCATE/REORGANIZE PARTITION statement inside a DML transaction expecting `ROLLBACK` to undo everything.

Unsafe example regarding rollback expectations:

This is an independent scenario illustrating implicit commit. Restore the fixture from section 3 before running so row `event_id = 2` still exists in `p2026_11`.

```sql
START TRANSACTION;

UPDATE event_log
SET event_type = 'ARCHIVED'
WHERE event_id = 2 AND event_date = '2026-11-05';

ALTER TABLE event_log
TRUNCATE PARTITION p2026_11;

ROLLBACK;
```

DDL commits the open transaction before executing; the trailing `ROLLBACK` does not restore truncated rows or undo DML changes already committed by the implicit commit.

MySQL 8.0 provides atomic DDL for many InnoDB DDL operations, meaning the DDL statement itself is guaranteed to either complete or recover consistently on server crash under supported conditions. Atomic DDL does not mean DDL participates in a user's DML transaction or can be rolled back after the statement succeeds.

### 9.1. Metadata Locks and Maintenance Windows

DDL requires a metadata lock to alter table definitions. An active transaction touching the table can hold a metadata lock longer than expected and block `ALTER TABLE`. Conversely, a waiting DDL statement can queue subsequent statements behind metadata lock waits.

Before running partition maintenance on large tables:

- Check open transactions and their runtime.
- Monitor metadata locks/waits if the table has heavy traffic.
- Assess whether the DDL requires moving or rebuilding data.
- Verify which `ALGORITHM` and `LOCK` options are supported for the specific operation, version, and engine.
- Set appropriate timeouts/monitoring and have a cancellation plan if the DDL waits too long.

Do not assume every partition operation is `INSTANT`, `INPLACE`, or `LOCK=NONE`. Online capability depends on operation type, MySQL version, engine, table definition, and active restrictions. Test on a staging copy of realistic scale.

## 10. Verifying Partitions After Operations

After DDL, re-verify the definition:

```sql
SHOW CREATE TABLE event_log;
```

Check metadata:

```sql
SELECT
    PARTITION_ORDINAL_POSITION,
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'event_log'
ORDER BY PARTITION_ORDINAL_POSITION;
```

Verify row counts per partition:

```sql
SELECT 'p2026_11' AS partition_name, COUNT(*) AS row_count
FROM event_log PARTITION (p2026_11)
UNION ALL
SELECT 'p2026_12', COUNT(*)
FROM event_log PARTITION (p2026_12)
UNION ALL
SELECT 'pmax', COUNT(*)
FROM event_log PARTITION (pmax);
```

Only query partitions that exist under the current definition. `COUNT(*)` gives exact row counts at the query snapshot, though it can be expensive if partitions are large.

### 10.1. Verifying Boundaries with Sample Data

For date-based RANGE partitions, check dates immediately before, exactly at, and immediately after boundaries:

```sql
SELECT event_id, event_date
FROM event_log
WHERE event_date IN (
    '2026-11-15',
    '2026-11-16',
    '2026-11-30',
    '2026-12-01'
)
ORDER BY event_date, event_id;
```

With `VALUES LESS THAN`, a value equal to the boundary belongs to the next partition. For instance, `VALUES LESS THAN ('2026-12-01')` excludes 2026-12-01.

## 11. Partition Pruning After Partition Changes

Partition maintenance must preserve accurate boundaries so the optimizer eliminates irrelevant partitions when queries supply compatible predicates (*partition pruning*).

Example:

```sql
EXPLAIN PARTITIONS
SELECT event_id, event_date, event_type
FROM event_log
WHERE event_date >= '2026-11-01'
  AND event_date < '2026-12-01';
```

Inspect the `partitions` column in `EXPLAIN` to see which partitions are accessed. On MySQL 8.x, `EXPLAIN` output format may vary; use a version-appropriate `EXPLAIN` form if `EXPLAIN PARTITIONS` is unsupported in a given environment.

Predicates should align with the partitioning expression. Avoid wrapping the partition column in unnecessary functions or conversions if doing so prevents pruning. For instance, half-open time intervals (`>= start`, `< next day`) are clearer and less error-prone at boundaries than applying `DATE_FORMAT()` to the column.

After `REORGANIZE` or `ADD`/`DROP`, re-run representative queries to confirm pruning still behaves properly and does not accidentally scan `pmax` alongside unnecessary partitions.

## 12. Monthly Partition Maintenance Workflow

A standard operational workflow for a monthly log table:

1. Before the new month, identify the monthly partition to create and its exact boundary.
2. Inspect `SHOW CREATE TABLE` and `INFORMATION_SCHEMA.PARTITIONS`.
3. If `pmax` exists, use `REORGANIZE pmax` to carve out the new month and retain `pmax`.
4. Verify that incoming future data maps into the new partition.
5. When retention expires, archive/back up the old partition before dropping.
6. Use `DROP PARTITION` to remove both data and definition, or `TRUNCATE PARTITION` to retain an empty partition.
7. Check row counts, boundaries, query pruning, replication lag, and storage after the operation.

Example creating the January 2027 partition when `pmax` exists:

```sql
ALTER TABLE event_log
REORGANIZE PARTITION pmax INTO (
    PARTITION p2027_01 VALUES LESS THAN ('2027-02-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Example dropping October 2026 after archiving and confirming retention:

This is a standalone retention operation. If you already ran `DROP PARTITION p2026_10` in section 5, restore the fixture or skip this example.

```sql
ALTER TABLE event_log
DROP PARTITION p2026_10;
```

Both operations must be scheduled around boundaries and retention policies. Never run `DROP` before archived data is verified readable and recoverable.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using ADD after a `MAXVALUE` partition | DDL fails because no range can follow MAXVALUE | REORGANIZE the MAXVALUE partition to split out the new range |
| Using DROP just to empty a partition | Partition definition is also lost | Use TRUNCATE PARTITION |
| Using TRUNCATE when intending to remove a partition | Empty partition remains defined | Use DROP PARTITION to remove both definition and data |
| Running DROP/TRUNCATE without archiving | Loss of data still required for retention | Verify retention, backups, and exports first |
| REORGANIZE fails to cover the exact old range | DDL rejected or unintended boundaries | Recalculate contiguous value sets/ranges for full coverage |
| Using REORGANIZE on HASH/KEY | Wrong partitioning method | Use ADD PARTITION PARTITIONS n to increase or COALESCE PARTITION n to decrease |
| Using COALESCE on RANGE/LIST | Wrong partitioning method | Use DROP/REORGANIZE depending on goal |
| Using DROP PARTITION on HASH/KEY | Unsupported unlike RANGE/LIST | Use COALESCE PARTITION |
| Thinking COALESCE deletes data | Misunderstanding partition reduction | COALESCE redistributes data across the remaining partitions |
| Forgetting unique keys must include the partition key | Cannot create desired unique/primary keys | Redesign keys or use a registry table |
| Assuming partitioned InnoDB still supports FKs | Schema fails to build or design is invalid | Verify FK limits before choosing partitioning |
| Thinking partition DDL can roll back | Dropped/truncated data is not restored by ROLLBACK | Keep DDL separate from business transactions and prepare backups |
| Assuming DDL is always online and lock-free | Workload stalls or migration blocks on metadata locks | Check ALGORITHM/LOCK and test in staging |
| Not verifying partition pruning after changes | Queries scan more partitions than expected | Use EXPLAIN and predicates aligned with the partition key |

## 14. Practice Exercises

1. Create `event_log` from section 3. Run `SHOW CREATE TABLE` and query `INFORMATION_SCHEMA.PARTITIONS` to record boundaries.
2. Create a RANGE table without `MAXVALUE`, add a new partition using `ADD PARTITION`; try adding a boundary lower than the last boundary and explain the error.
3. Create a LIST table. Add a partition for unassigned values; try adding a value that already exists and observe the error.
4. Run `DROP PARTITION` on a lab partition containing data. Verify both the partition definition and its data are gone.
5. Run `TRUNCATE PARTITION` on another partition. Verify the partition still exists while its row count is 0.
6. Split a monthly partition using `REORGANIZE PARTITION`. Check rows on both sides of the boundary, especially dates equal to the boundary.
7. Merge the split partitions back together. Compare total row counts before and after.
8. Create a HASH table with 8 partitions, then run `COALESCE PARTITION 2`. Verify the remaining partition count and unchanged total row count.
9. Increase HASH partitions with `ADD PARTITION PARTITIONS n`, then decrease with `COALESCE PARTITION n`; compare partition counts, total rows, and redistribution impact.
10. Run `EXPLAIN PARTITIONS` for a date-range query before and after reorganizing.
11. Observe metadata locks in a lab environment while one session holds an open transaction touching the table and another runs `ALTER PARTITION`.
12. Write a monthly maintenance runbook covering archiving, creating new partitions, dropping expired partitions, and checking row counts, pruning, and replication lag.

## 15. Checklist Before Running Partition Maintenance

- [ ] Confirmed exact schema, table, partitioning method, and current definition.
- [ ] Clarified whether the goal is adding a range, deleting data, emptying, splitting/merging, or reducing partition count.
- [ ] Selected the right command for RANGE/LIST/HASH/KEY.
- [ ] Checked `MAXVALUE` and current boundaries.
- [ ] Verified new partition names do not collide and ranges neither overlap nor leave gaps.
- [ ] Verified the rule requiring partitioning columns in every unique key.
- [ ] Verified foreign key restrictions on InnoDB partitioned tables.
- [ ] Counted/assessed affected data and archived/backed up if needed.
- [ ] Assessed data movement volume, disk space, and I/O.
- [ ] Checked long-running transactions, metadata locks, and maintenance window.
- [ ] Verified compatible ALGORITHM/LOCK for the version and operation.
- [ ] Prepared a plan to monitor replication lag and workload after DDL.
- [ ] Re-checked SHOW CREATE TABLE, partition metadata, row counts, and pruning afterward.
- [ ] Not relying on ROLLBACK to revert completed DDL.

## 16. Completion Criteria

You have completed this lesson when you can clearly distinguish `ADD`, `DROP`, `TRUNCATE`, `REORGANIZE`, and `COALESCE PARTITION`; choose the right operation for RANGE/LIST/HASH/KEY; explain how to handle `MAXVALUE`; split and merge partitions without losing value ranges; understand DDL implicit commits and metadata locks; and verify partition definitions, row counts, and pruning after maintenance.

## References

- [MySQL 8.4 Reference Manual — Management of RANGE and LIST Partitions](https://dev.mysql.com/doc/refman/8.4/en/partitioning-management-range-list.html)
- [MySQL 8.4 Reference Manual — Management of HASH and KEY Partitions](https://dev.mysql.com/doc/refman/8.4/en/partitioning-management-hash-key.html)
- [MySQL 8.4 Reference Manual — Partitioning Limitations](https://dev.mysql.com/doc/refman/8.4/en/partitioning-limitations.html)
- [MySQL 8.4 Reference Manual — INFORMATION_SCHEMA PARTITIONS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-partitions-table.html)
- [MySQL 8.4 Reference Manual — ALTER TABLE Partition Operations](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html)
