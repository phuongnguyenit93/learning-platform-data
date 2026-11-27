# Rotating Out Old Data and Planning Partition Maintenance

Partitioning helps divide a large table into manageable data segments based on partitioning key ranges. For a transaction table stored by date, time-based partitioning lets you move old data out of the active serving table via partition-level operations instead of deleting millions of rows one by one. However, partitioning is only useful when backed by a data lifecycle policy, a schedule for creating future partitions, an archival process, and a clear maintenance plan.

In MySQL, operations such as `EXCHANGE PARTITION`, `DROP PARTITION`, `TRUNCATE PARTITION`, and `REORGANIZE PARTITION` have different impacts on data and partitioning layout. A wrong DDL operation can lose data or cause late-arriving data to land in unexpected partitions. This lesson focuses on planning safe rotation of old data and running scheduled partition maintenance.

## Objectives

After this lesson, you will be able to:

- Design time-based partitions to support retention policies.
- Pre-create future partitions and avoid situations where new data lacks a matching partition.
- Use `EXCHANGE PARTITION` to move a partition's data into an independent table for archiving.
- Distinguish `DROP PARTITION`, `TRUNCATE PARTITION`, and `REORGANIZE PARTITION`.
- Verify data before and after rotation and plan for rollback, backups, and metadata locks.
- Build a recurring maintenance schedule, monitor partitions, and handle late-arriving data.

The examples assume MySQL 8.0, InnoDB, and tables partitioned by `RANGE COLUMNS` on a `DATE` column. Verify support and limitations for your exact deployed MySQL version before applying DDL in production.

## 1. Start from the Data Lifecycle Policy

Before creating partitions, answer these business questions:

- How long must hot data remain available for frequent queries: 30 days, 12 months, or several years?
- Should old data stay online, move to an archive table, be exported to object storage, or be deleted after a legal retention period?
- How late can late-arriving data show up? Are backdated transactions allowed for an already-archived period?
- Do queries primarily filter by date, customer, or transaction ID?
- Who approves data deletion and how is archive completeness proven?

Sample policy:

| Data tier | Storage | Retention duration | Action on expiration |
|---|---|---|---|
| Recent transactions | Main partitioned table | 24 months | Move old partition to archive table |
| Archived transactions | Standalone table or archive storage | Per business/legal requirements | Back up, verify, and purge per separate policy |
| Expired beyond archive | No longer in online table | Per approved retention limit | Drop partition or archive copy after verification |

Partitioning does not decide on its own which data is kept or deleted. It only provides physical boundaries for operating on groups of rows. Retention policies, query filters, and operational schedules must be defined upfront.

## 2. Designing a Time-Partitioned Table

Example sales transactions table:

```sql
CREATE TABLE sales (
    sale_id BIGINT UNSIGNED NOT NULL,
    sold_at DATE NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(16) NOT NULL,
    PRIMARY KEY (sale_id, sold_at),
    KEY ix_sales_customer_date (customer_id, sold_at),
    KEY ix_sales_status_date (status, sold_at)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (sold_at) (
    PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

`RANGE COLUMNS(sold_at)` splits data along date boundaries. `p_before_2026` holds all dates earlier than 2026-01-01; `p2026` holds dates from 2026-01-01 up to before 2027-01-01; `p_future` accepts values from 2027-01-01 onward.

Partition names are merely conventions. With `RANGE`, the first partition has no explicit lower bound; therefore `p_before_2026` can hold very old data if the application permits backfills. Once the first partition is dropped, the next partition becomes the first partition and its range extends downward indefinitely. To prevent overly old rows from slipping into a newer partition, the application must enforce a retention floor prior to insert or retain a dedicated partition for old data.

### Notes on Unique Keys and Foreign Keys

For partitioned tables in MySQL, every unique key, including the primary key, must contain all columns used in the partitioning expression. In the example, `sold_at` is included in primary key `(sale_id, sold_at)`.

InnoDB does not support foreign keys on user-partitioned tables; nor can partitioned tables be referenced by foreign keys from other tables. If the data model requires referential constraints, redesign table boundaries or enforce relationships at the application/transaction layer appropriately.

Indexes on a partitioned table are organized per partition (local indexes). Partition pruning skips irrelevant partitions; in-partition indexes locate rows inside selected partitions. Partitioning does not replace index design and does not automatically make every query faster.

## 3. Planning Future Partitions

Never wait until data for a new day/month arrives only to discover the table lacks a matching partition. Without a matching partition, inserts fail. `p_future` uses `MAXVALUE` as a buffer to prevent that failure, though new rows will keep landing in that single partition until it is split.

### Splitting the MAXVALUE Partition with REORGANIZE

Before 2027 arrives, split `p_future` into a dedicated 2027 partition and a new `p_future`:

```sql
ALTER TABLE sales
REORGANIZE PARTITION p_future INTO (
    PARTITION p2027 VALUES LESS THAN ('2028-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

`REORGANIZE PARTITION` redistributes rows from the old partition according to the new boundaries. If `p_future` already holds significant data, the operation may have to move and rewrite a substantial volume of rows. Creating future partitions ahead of time avoids emergency maintenance pressure.

### ADD PARTITION When No MAXVALUE Exists

If the design has no `MAXVALUE` partition, a new partition can be appended at the end of the range:

```sql
ALTER TABLE sales_no_future
ADD PARTITION (
    PARTITION p2027 VALUES LESS THAN ('2028-01-01')
);
```

You cannot add a partition with a higher bound after a `MAXVALUE` partition using `ADD PARTITION`; you must `REORGANIZE` the `MAXVALUE` partition to carve out the new range. Pick one consistent strategy and document it clearly in the runbook.

### Partition Creation Schedule

An operational schedule typically pre-creates partitions 1–3 periods ahead, depending on partition frequency and change-approval lead times. For example:

| Timing | Task |
|---|---|
| Start of each month | Review existing partitions and upcoming periods |
| 2–4 weeks before new period | Create the partition for the next month/quarter |
| Weekly | Alert if rows have started landing in `p_future` |
| Daily | Monitor failed inserts from missing partitions and late-arriving data |
| Before archival cycle | Verify backups, row counts, date bounds, and retention approval |

If using `p_future`, monitor its row count. When rows regularly land in `p_future`, that signals partition pre-creation is falling behind or boundaries are stale.

## 4. EXCHANGE PARTITION for Archiving Old Data

`ALTER TABLE ... EXCHANGE PARTITION` swaps data between a partition and an unpartitioned table. This is a practical way to pull old data out of an online table without running row-by-row `DELETE`s.

Suppose `p_before_2026` has reached the end of its online window and needs archiving. Create a standalone table with a matching structure:

```sql
CREATE TABLE sales_archive_before_2026 LIKE sales;
ALTER TABLE sales_archive_before_2026 REMOVE PARTITIONING;
```

`CREATE TABLE ... LIKE` creates an empty table matching the source structure; `REMOVE PARTITIONING` turns the archive table into an unpartitioned table. Inspect `SHOW CREATE TABLE` to verify columns, data types, indexes, and table options match. The target archive table must be empty prior to exchange; otherwise its existing rows will be moved into the partition.

Execute the exchange with validation:

```sql
ALTER TABLE sales
EXCHANGE PARTITION p_before_2026
WITH TABLE sales_archive_before_2026
WITH VALIDATION;
```

After the operation:

- `sales_archive_before_2026` contains the rows previously in `p_before_2026`.
- `p_before_2026` still exists, now as an empty partition.
- No other partitions of `sales` have data moved.

`WITH VALIDATION` is the default and instructs MySQL to check whether rows in the unpartitioned table belong to the target partition's range. Validation can take time when the archive table is huge, yet prevents misplaced rows inside partitions. `WITHOUT VALIDATION` skips the check; use it only when an external process proves every row obeys partition boundaries. Putting out-of-range rows into a partition can cause queries relying on partition pruning to miss rows where the application expects them.

### Pre- and Post-Exchange Verification

Before exchange, record row counts and date ranges:

```sql
SELECT COUNT(*) AS row_count,
       MIN(sold_at) AS min_sold_at,
       MAX(sold_at) AS max_sold_at
FROM sales PARTITION (p_before_2026);
```

After exchange, check the archive table:

```sql
SELECT COUNT(*) AS row_count,
       MIN(sold_at) AS min_sold_at,
       MAX(sold_at) AS max_sold_at
FROM sales_archive_before_2026;

SELECT COUNT(*) AS remaining_rows
FROM sales PARTITION (p_before_2026);
```

The archive row count must match the pre-exchange count, and the source partition must be empty. Also reconcile monetary totals, daily counts, or business checksums if audit rules require higher verification guarantees.

### After Exchange: Keep or Drop the Empty Partition?

Two options exist:

- Keep the empty partition if you want to reuse the boundary or perform archival in waves.
- `DROP PARTITION` to remove the old partition definition once the archive is verified.

Example:

```sql
ALTER TABLE sales DROP PARTITION p_before_2026;
```

Drop only after the archive table has been verified, backed up per policy, and approved. When dropping the first partition of a `RANGE` table, the next partition becomes the first partition and its lower range opens downward indefinitely. If overly old rows must be blocked from entering the new first partition, enforce checks in the application or reorganize partitions accordingly.

## 5. How DROP, TRUNCATE, and REORGANIZE Differ

| Operation | Impact on data | Impact on partition definition | When to use |
|---|---|---|---|
| `DROP PARTITION` | Deletes all data inside the dropped partition | Removes the partition from the table | Remove expired retention periods after archiving or deletion approval |
| `TRUNCATE PARTITION` | Deletes all rows inside the partition | Keeps the partition and its boundaries | Empty a partition for reuse |
| `REORGANIZE PARTITION` | Redistributes data across the specified partitions | Changes boundaries/partition count in that region | Split `MAXVALUE`, merge small partitions, or adjust boundaries |
| `EXCHANGE PARTITION` | Swaps data between a partition and an unpartitioned table | Keeps the partition; standalone table receives the data | Archive or batch-load data via a staging table |

Example emptying a partition while keeping its definition:

```sql
ALTER TABLE sales TRUNCATE PARTITION p_future;
```

This deletes data inside `p_future` without dropping the partition. It is a destructive operation; use it only when certain nothing in the partition needs keeping.

Example merging two adjacent partitions:

```sql
ALTER TABLE sales
REORGANIZE PARTITION p2026, p2027 INTO (
    PARTITION p2026_2027 VALUES LESS THAN ('2028-01-01')
);
```

The new boundary must cover the exact combined range of the reorganized partitions. For heavily populated partitions, this can move data and rebuild associated index structures; estimate space, runtime, and I/O load before running.

## 6. Why Not Archive Using Bulk DELETE?

Old data could be deleted via:

```sql
DELETE FROM sales
WHERE sold_at < '2026-01-01';
```

However, across millions or billions of rows, this generates massive undo/redo, inflates binary logs, burdens purge threads, and holds locks for extended durations. Huge transactions can also lag replicas or disrupt concurrent queries.

When retention cutoffs align with partition boundaries, `EXCHANGE PARTITION` followed by `DROP PARTITION` is usually preferable because it operates at the partition unit level. Even so, DDL still needs metadata locks, may wait on active transactions, and can incur I/O depending on the operation. Never treat partition DDL as zero-cost.

If the retention cutoff falls in the middle of a partition, you cannot drop half a partition with `DROP PARTITION`. Options include:

1. Using `REORGANIZE PARTITION` to split old and retained ranges along the new boundary, then archiving/dropping the old half.
2. Deleting in batches by primary key if volume is small or boundaries cannot easily change.
3. Adjusting partition schedules in the next design cycle so boundaries align with retention intervals.

The choice depends on data volume, maintenance windows, retention rules, and rebuild cost.

## 7. Partition Pruning and Queries After Rotation

Partition pruning lets the optimizer read only partitions capable of holding matching rows. Predicates should directly express the range of the partition key:

```sql
SELECT sale_id, customer_id, amount
FROM sales
WHERE sold_at >= '2026-06-01'
  AND sold_at <  '2026-07-01'
  AND customer_id = 42;
```

Avoid wrapping the partition key in functions when an equivalent range can be written:

```sql
-- Harder to prune in many cases:
WHERE YEAR(sold_at) = 2026

-- Write as a clear range:
WHERE sold_at >= '2026-01-01'
  AND sold_at <  '2027-01-01'
```

Inspect selected partitions:

```sql
EXPLAIN PARTITIONS
SELECT sale_id, amount
FROM sales
WHERE sold_at >= '2026-06-01'
  AND sold_at <  '2026-07-01';
```

The `partitions` column in the output shows which partitions are examined. After archiving and dropping an old partition, historical queries must be routed to the archive table or corresponding storage tier. If the application still queries only `sales`, moved data will no longer appear in results.

## 8. Planning and Executing an Archival Cycle

An archival cycle should follow explicit controls:

1. **Define scope:** select the closed partition, verify start/end dates, and confirm retention policy.
2. **Verify schema:** confirm the unpartitioned archive table has compatible structure/indexes and is empty.
3. **Inspect data:** record row counts, min/max dates, amount totals, and business metrics prior to exchange.
4. **Verify recoverability:** confirm the latest backup is valid and archive restore procedures are tested.
5. **Check load and locks:** hunt for long-running transactions, pick a low-traffic window, and budget for metadata locks and validation time.
6. **Exchange:** run `EXCHANGE PARTITION ... WITH VALIDATION`.
7. **Reconcile:** verify row counts and business totals in the archive table, and confirm the source partition is empty.
8. **Back up archive:** create an independent copy per backup and retention policies.
9. **Drop partition:** execute only after archived data is verified and approved.
10. **Log audit trail:** record timestamp, operator, partition name, row count, checksums/control totals, DDL duration, and outcome.

DDL statements such as `ALTER TABLE` trigger implicit commits and cannot be undone via `ROLLBACK` like ordinary DML. Never wrap the exchange/drop workflow in a transaction expecting rollback across all steps. Rely on checkpoints, backups, and explicit recovery procedures.

## 9. Metadata Locks and Maintenance Windows

`ALTER TABLE` commands require metadata locks (MDL). If an active transaction holds a metadata lock on the table, partition operations may wait. Conversely, when DDL is waiting to acquire MDL, incoming queries may queue behind it depending on the situation.

Before the maintenance window:

- Check for long-running transactions and sessions idle in transaction.
- Avoid running archives concurrently with schema migrations or other DDL on the table.
- Configure reasonable lock-wait timeouts and monitor status in `performance_schema`/process list.
- Have an abort plan ready if lock waits drag on; killing running DDL may itself require rollback/cleanup time.
- Notify application owners if operations might increase latency or cause brief interruptions.

Never assume `EXCHANGE PARTITION`, `DROP PARTITION`, or `REORGANIZE PARTITION` are instantaneous. Locking, algorithm, and cost depend on operation type, engine, MySQL version, and table layout. Check MySQL docs for your exact version, test on a data clone, and measure runtime before scheduling in production.

## 10. Monitoring Partitions and Detecting Operational Issues

List existing partitions:

```sql
SELECT PARTITION_NAME,
       PARTITION_METHOD,
       PARTITION_EXPRESSION,
       PARTITION_DESCRIPTION,
       TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'sales'
ORDER BY PARTITION_ORDINAL_POSITION;
```

With InnoDB, `TABLE_ROWS` in `INFORMATION_SCHEMA.PARTITIONS` is an estimate; do not rely on it for exact reconciliation. Use per-partition `COUNT(*)` or pre/post archive snapshots to verify:

```sql
SELECT COUNT(*)
FROM sales PARTITION (p_future);
```

Alerts to track:

| Indicator | Possible meaning | Action |
|---|---|---|
| `p_future` row count grows steadily | Next period's partition not yet created or boundaries stale | Create next period's partition and verify rows land in the right region |
| Inserts fail with no matching partition | No partition covers the incoming partition key value | Create new partition; inspect out-of-range data and job schedule |
| Archive table mismatches pre-exchange count | Issue in exchange or reconciliation workflow | Halt drop step, preserve data, and investigate |
| DDL waits for a long time | Another transaction or query holds MDL | Identify blocker, resolve transaction, and reschedule window if needed |
| Historical queries return no data | Partition was already exchanged/dropped from online table | Route queries to archive or appropriate storage tier |
| Reorganize runs excessively long | Large source partition or many pages moving | Measure beforehand, split work if design allows, and pick off-peak hours |

## 11. Handling Late-Arriving Data

Late-arriving data is one of the biggest operational risks of time-based partitioning. For instance, the pre-2026 partition has already been archived and dropped, yet a transaction dated `sold_at = '2025-12-31'` arrives afterward.

Choose an explicit policy:

- **Reject expired data:** check a retention floor before inserting and route out-of-window records to an exception workflow.
- **Ingest via staging:** write old records into a staging table, validate, then archive directly or exchange into a partition dedicated to late-arriving data.
- **Controlled historical reopen:** create/reorganize a partition to absorb old data, load it, then rerun the archive cycle. This can be costly and requires approval.

Never let old rows silently flow into the first partition just because `INSERT` succeeds without error. Once the first partition is dropped, the next partition's lower range opens downward; old rows can silently land inside a partition named for a newer period. Inspect bounds via `INFORMATION_SCHEMA.PARTITIONS` and enforce a retention floor in the application layer.

## 12. Recurring Operations Checklist

Before each maintenance cycle, confirm:

- [ ] Next period's partition already exists or has a clear creation schedule.
- [ ] The partition being archived is closed with no further active writes per business rules.
- [ ] The unpartitioned archive table has compatible schema and indexes.
- [ ] The target archive table is currently empty.
- [ ] Row counts, min/max partition keys, and reconciliation totals are recorded.
- [ ] The latest backup is valid and restore procedures have been tested.
- [ ] No long-running transactions are likely to block metadata locks.
- [ ] `WITH VALIDATION` is chosen, or strong proof exists if using `WITHOUT VALIDATION`.
- [ ] Post-exchange archive row count matches and the source partition is empty.
- [ ] Partition is dropped only after archive and backup verification.
- [ ] Operation history and approver details are logged.
- [ ] Late-arriving data policies and retention floors remain enforced.

## 13. Practice Lab

On a test MySQL instance, create the `sales` table partitioned by `RANGE COLUMNS(sold_at)` as in section 2 and load sample rows spanning different periods.

1. Run `EXPLAIN PARTITIONS` for a single-month query and identify which partition is selected.
2. Create `sales_archive_before_2026` using `CREATE TABLE ... LIKE`, then `REMOVE PARTITIONING`. Use `SHOW CREATE TABLE` to compare schemas.
3. Record `COUNT(*)`, `MIN(sold_at)`, and `MAX(sold_at)` in `p_before_2026`. Run `EXCHANGE PARTITION ... WITH VALIDATION`.
4. Confirm the archive table holds the exact row count and the source partition is empty. Do not drop the partition in this step.
5. In a separate test run, execute `DROP PARTITION` and observe how the first remaining partition's effective bounds change.
6. Create the 2027 partition by `REORGANIZE`-ing `p_future`. Observe rows redistributed under the new boundaries.
7. Try inserting a row with `sold_at` older than the retention floor. Design an application check to reject or route it to a staging flow.
8. Describe how to recover if the archive table is missing rows after an exchange; explain why `ROLLBACK` alone cannot undo committed DDL.

## Key Takeaways

- Define retention and late-arriving data policies before choosing partition keys and boundaries.
- Create future partitions ahead of time; monitor `p_future` whenever `MAXVALUE` is used.
- `EXCHANGE PARTITION` swaps data with an unpartitioned table; use validation and pre/post reconciliation.
- `DROP PARTITION` deletes both data and partition definition; `TRUNCATE PARTITION` only empties data; `REORGANIZE PARTITION` alters boundaries and can move data.
- Archive or drop partitions only after backups and reconciliation figures are verified.
- Partition DDL requires metadata locks and can generate load; test beforehand, schedule maintenance windows, and prepare recovery plans.
- After dropping the first partition, the next partition's range extends downward; enforce an explicit retention floor or design clear handling for late-arriving data.
