# EXCHANGE PARTITION and Data Validation During Swap

`ALTER TABLE ... EXCHANGE PARTITION` allows swapping data between a partition of a partitioned table and a regular (nonpartitioned) table with a compatible structure. This operation is commonly used to load prepared data into a partition or move a partition out into a staging/archive table for further processing.

The key point is that this is a **swap**, not an append operation: data currently in the partition moves to the regular table, while data currently in the regular table moves into the partition. If one side is empty, it receives the other side's data. With `WITH VALIDATION`, MySQL checks whether rows in the regular table belong to the target partition's value range before swapping.

In the `DATABASE_MYSQL` module, this technique is useful for periodic data loading, partition archiving, and ETL pipelines. However, you must verify table structure compatibility, partition bounds, unique keys, staging data, metadata locks, and the consequences of skipping validation. This lesson focuses on MySQL 8.0 and InnoDB.

## Objectives

After this lesson, you will be able to:

- Explain the bidirectional swap semantics of `EXCHANGE PARTITION`.
- Create a RANGE-partitioned table and a compatible unpartitioned staging table.
- Understand why partition columns must appear in every unique key of the partitioned table.
- Verify schema, storage engine, indexes, and partition bounds before exchanging.
- Use `WITH VALIDATION` to confirm staging data belongs to the target partition.
- Understand the risks of `WITHOUT VALIDATION` and out-of-range rows ending up in the wrong partition.
- Verify row counts and data after swapping.
- Use exchange to ingest data or move a partition out to staging/archive.
- Recognize implicit commit, metadata locks, and operational constraints.

## 1. What Does EXCHANGE PARTITION Do?

General syntax:

```sql
ALTER TABLE partitioned_table
EXCHANGE PARTITION partition_name
WITH TABLE nonpartitioned_table
[WITH VALIDATION | WITHOUT VALIDATION];
```

Two objects participate:

- `partitioned_table`: the partitioned table; the command names one specific partition.
- `nonpartitioned_table`: a regular unpartitioned table used to receive or supply data.

After a successful exchange:

- Rows previously in the target partition move into the regular table.
- Rows previously in the regular table move into the target partition.
- Both the partition definition and table definitions remain intact; only the data is swapped between the two objects.

Therefore, if the target partition holds 1 million rows and staging holds 100 thousand rows, after exchange the partition holds 100 thousand rows while staging receives the old 1 million rows. MySQL does not append the 100 thousand rows onto the existing 1 million rows.

### 1.1. Two Primary Use Cases

**Loading data into a partition:** prepare data in a staging table, validate it, then exchange staging into the corresponding partition. If the partition was empty, staging becomes empty afterward.

**Moving a partition out:** prepare an empty staging table and exchange the partition into it. The partition becomes empty while the staging table holds the partition's data for export, archiving, or downstream processing.

### 1.2. Exchange Is Not INSERT SELECT

`INSERT INTO partitioned_table SELECT ... FROM staging` copies each row and executes row-by-row inserts into the target table. `EXCHANGE PARTITION` swaps the data segments of the two objects via metadata/storage-engine operations, avoiding row-by-row re-insertion.

That does not mean exchange is completely free: validation may have to scan staging data; the DDL requires metadata locks; and the system still needs resources for metadata, indexes, and subsequent operations.

## 2. Creating a Date-Partitioned Table

Example table storing daily sales events. The table uses `RANGE COLUMNS(event_date)` with monthly partitions:

```sql
CREATE TABLE sales_event (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    event_note VARCHAR(200) NULL,
    PRIMARY KEY (event_id, event_date),
    KEY idx_sales_tenant_date (tenant_id, event_date)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p202601 VALUES LESS THAN ('2026-02-01'),
    PARTITION p202602 VALUES LESS THAN ('2026-03-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Partition domains:

| Partition | `event_date` value domain |
|---|---|
| `p202601` | Less than `2026-02-01` and greater than/equal to the preceding partition's lower bound |
| `p202602` | From `2026-02-01` up to before `2026-03-01` |
| `pmax` | From `2026-03-01` onward |

Because the example omits a partition before `p202601`, the first partition accepts all dates earlier than `2026-02-01`. In production systems, explicitly define all retention periods and rules for late-arriving data.

### 2.1. Partition Columns Must Appear in Every Unique Key

MySQL requires every column used in the partitioning expression to be part of every unique key on the partitioned table, including the primary key. That is why the primary key in the example is `(event_id, event_date)`, not just `(event_id)`.

Attempting to declare `PRIMARY KEY (event_id)` while partitioning by `event_date` is rejected by MySQL. This has a business consequence: the primary key no longer guarantees `event_id` is globally unique across the table if the same ID can appear on two different dates. The application must ensure suitable identifiers or use a different key design.

You cannot add `UNIQUE KEY uq_event_id (event_id)` unless `event_date` is included in that unique key. If global ID uniqueness is required, redesign the identity and partitioning model to satisfy both constraints.

## 3. Creating an Unpartitioned Staging Table

The staging table must be a regular table without partitions. Column and index structures must be compatible with the partitioned table. To avoid accidentally copying partitioning clauses when creating one table from another, the example declares staging explicitly:

```sql
CREATE TABLE sales_event_stage (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    event_note VARCHAR(200) NULL,
    PRIMARY KEY (event_id, event_date),
    KEY idx_sales_tenant_date (tenant_id, event_date)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

`sales_event_stage` has no `PARTITION BY` clause, so it is unpartitioned. Both tables share identical:

- Column count, column names, column order, and data types.
- `NULL`/`NOT NULL` attributes, precision, and related column properties.
- Primary key and required secondary indexes.
- InnoDB storage engine.

In operations, compare `SHOW CREATE TABLE` for both tables prior to exchange. Whenever schema changes occur on the main table, update the staging creation workflow so definitions never drift.

### 3.1. Structural Requirements to Remember

- The target table must be a regular, unpartitioned table.
- Both sides must have compatible structures meeting MySQL's exchange requirements.
- Both sides must use the same storage engine; this example uses InnoDB.
- No foreign key constraints may exist on participating tables; InnoDB partitioned tables do not support foreign keys.
- The named partition must exist in the partitioned table.
- The staging table cannot be a temporary table.

Do not assume having the same column count is sufficient. Differences in order, data types, attributes, or indexes can cause exchange to fail or violate structural requirements. Use the same DDL source/schema versioning to create both the main table and staging.

## 4. Loading Data into Staging

Suppose January 2026 data needs to be loaded into `p202601`. Load the data into the staging table first:

```sql
INSERT INTO sales_event_stage
    (event_id, event_date, tenant_id, amount, event_note)
VALUES
    (1001, '2026-01-05', 10, 125.00, 'Web order'),
    (1002, '2026-01-12', 10,  80.00, 'Mobile order'),
    (1003, '2026-01-29', 20, 210.00, 'Partner order');
```

Staging can be populated via `INSERT`, bulk load, or ETL. This stage should complete before the exchange to minimize metadata lock hold time on the partitioned table.

### 4.1. Checking Data Domain Before Exchange

Partition `p202601` accepts any `event_date` earlier than `2026-02-01` in the example. Check staging:

```sql
SELECT COUNT(*) AS out_of_range_rows
FROM sales_event_stage
WHERE event_date >= '2026-02-01';
```

Since `event_date` is `NOT NULL` and the first partition has no lower bound, this query checks the upper bound of `p202601`. In systems with an explicit lower bound, check both ends:

```sql
SELECT COUNT(*) AS out_of_range_rows
FROM sales_event_stage
WHERE event_date <  '2026-01-01'
   OR event_date >= '2026-02-01';
```

The result must be 0 before exchanging. With `RANGE COLUMNS`, `VALUES LESS THAN` is an exclusive upper bound: `2026-02-01` does not belong to `p202601`.

### 4.2. Business Rule Checks on Data

In addition to partition bounds, check other rules:

```sql
SELECT COUNT(*) AS invalid_amount_rows
FROM sales_event_stage
WHERE amount < 0;

SELECT COUNT(*) AS missing_tenant_rows
FROM sales_event_stage
WHERE tenant_id IS NULL;

SELECT COUNT(*) AS duplicate_event_keys
FROM (
    SELECT event_id, event_date
    FROM sales_event_stage
    GROUP BY event_id, event_date
    HAVING COUNT(*) > 1
) AS duplicates;
```

The primary key already prevents duplicate `(event_id, event_date)` in staging, though extra checks are helpful in ETL pipelines and source reconciliation. Business validations should match the real schema; do not assume every system forbids negative amounts.

### 4.3. Comparing Schema and Engine

```sql
SHOW CREATE TABLE sales_event\G
SHOW CREATE TABLE sales_event_stage\G

SELECT TABLE_NAME, ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('sales_event', 'sales_event_stage');
```

Confirm `sales_event` has a partition definition, `sales_event_stage` has no partition definition, and both use InnoDB. Check full column/index definitions before running exchange DDL.

## 5. EXCHANGE PARTITION WITH VALIDATION

Once staging is loaded and verified, execute:

```sql
ALTER TABLE sales_event
EXCHANGE PARTITION p202601
WITH TABLE sales_event_stage
WITH VALIDATION;
```

`WITH VALIDATION` instructs MySQL to verify that all rows in the staging table belong to the target partition. This is the default mode when `WITHOUT VALIDATION` is omitted; spell it out explicitly in operational scripts so the validation intent is clear during review.

If staging contains a row dated `2026-02-01`, exchanging into `p202601` fails because that row lies outside the partition's domain. Fix the data or select the right partition before retrying.

### 5.1. Outcome After Exchange

If `p202601` was initially empty:

- `sales_event` partition `p202601` receives the three staging rows.
- `sales_event_stage` becomes empty.
- Other partitions are untouched.

Verify:

```sql
SELECT COUNT(*) AS rows_in_partition
FROM sales_event PARTITION (p202601);

SELECT COUNT(*) AS rows_left_in_stage
FROM sales_event_stage;

SELECT event_id, event_date, tenant_id, amount
FROM sales_event PARTITION (p202601)
ORDER BY event_date, event_id;
```

Expected output is 3 rows in `p202601` and 0 rows in staging.

### 5.2. When the Partition Already Contains Data

Suppose the partition already holds 1,000 rows and staging holds 100 rows. After exchange, the partition has the 100 staging rows, while the staging table receives the partition's previous 1,000 rows. There is no automatic append.

If the goal is adding new data into a partition while retaining existing data, build staging with the complete replacement dataset, or use `INSERT`/ETL with an appropriate strategy. Never exchange a delta-only staging table against a populated partition expecting the two sets to merge.

## 6. WITHOUT VALIDATION and the Risk of Misplaced Partition Data

Validation can be bypassed:

```sql
ALTER TABLE sales_event
EXCHANGE PARTITION p202601
WITH TABLE sales_event_stage
WITHOUT VALIDATION;
```

`WITHOUT VALIDATION` lets MySQL skip checking whether every staging row belongs to the target partition. It can shorten exchange duration for massive datasets, but is safe only when an external process has already proven the data matches the partition bounds.

### 6.1. What Happens If Out-of-Range Rows Are Present?

If staging contains `event_date = '2026-02-10'` yet is exchanged into `p202601`, that row physically resides inside a partition whose bounds do not cover it. The optimizer relies on partition bounds for pruning; a query searching for `2026-02-10` may read only `p202602` and skip `p202601`, returning incomplete results.

This is a data correctness risk, not merely a performance issue. `WITHOUT VALIDATION` does not safely turn a partition into a container for arbitrary values.

### 6.2. When Should WITHOUT VALIDATION Be Considered?

Consider it only when:

- The ETL pipeline has already validated every row against the exact same partitioning expression and bounds.
- Staging data is locked/frozen throughout both validation and exchange.
- Row counts, min/max partition keys, and appropriate checksums are reconciled.
- An immediate remediation procedure exists if post-checks detect misplaced data.
- It has been tested on the exact production MySQL version and schema.

If these conditions cannot be proven, use `WITH VALIDATION`. Never skip validation just to shave a few seconds off DDL at the expense of query correctness.

### 6.3. Checking Bounds with MIN/MAX

For the January 2026 partition:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(event_date) AS min_event_date,
    MAX(event_date) AS max_event_date
FROM sales_event_stage;
```

`MIN`/`MAX` offers a quick sanity check, but does not replace checking every row when data types or partitioning expressions are complex. With `RANGE COLUMNS(event_date)` and a `DATE NOT NULL` column, the out-of-range filter shown earlier is a direct check. For multi-column or expression-based partition keys, replicate the exact partitioning logic during validation.

## 7. EXCHANGE for Archiving a Partition

Swapping also works in the outward direction. Create an empty regular table with matching schema/indexes, such as `sales_event_archive_stage`:

```sql
CREATE TABLE sales_event_archive_stage (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    event_note VARCHAR(200) NULL,
    PRIMARY KEY (event_id, event_date),
    KEY idx_sales_tenant_date (tenant_id, event_date)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Confirm the archive staging table is empty, then exchange:

```sql
SELECT COUNT(*) AS archive_stage_rows
FROM sales_event_archive_stage;

ALTER TABLE sales_event
EXCHANGE PARTITION p202601
WITH TABLE sales_event_archive_stage
WITH VALIDATION;
```

After exchange:

- `sales_event_archive_stage` holds the rows previously in `p202601`.
- `p202601` becomes empty.
- The archive staging table remains a regular table that can be exported, backed up, moved, or renamed per archival policies.

Never truncate or drop the archive staging table before exporting and reconciling data. If archive staging was not empty beforehand, its rows will be placed into the partition while the partition's rows move to staging; it is still a two-way swap.

## 8. Pre- and Post-Exchange Verification

A safe workflow does not stop when DDL returns success. Reconcile across multiple layers.

### 8.1. Inspecting Partition Definitions

```sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'sales_event'
ORDER BY PARTITION_ORDINAL_POSITION;
```

`TABLE_ROWS` in InnoDB is an estimate; do not use it for exact reconciliation. Use `COUNT(*)` on the partition or targeted data queries when exact numbers are required.

### 8.2. Pre/Post Row Counts

Before exchange, record:

```sql
SELECT COUNT(*) AS stage_count
FROM sales_event_stage;

SELECT COUNT(*) AS partition_count_before
FROM sales_event PARTITION (p202601);
```

After exchange, record both again. If the partition started empty, expect `partition_count_after = stage_count_before` and `stage_count_after = 0`.

If the partition held prior data, the two counts swap sides. For full reconciliation, record counts, min/max, amount totals, or business checksums before running the operation.

### 8.3. Post-Exchange Data Checks

```sql
SELECT COUNT(*) AS rows_outside_expected_range
FROM sales_event PARTITION (p202601)
WHERE event_date >= '2026-02-01';
```

The result must be 0. You can also check daily distribution:

```sql
SELECT event_date, COUNT(*) AS row_count, SUM(amount) AS daily_amount
FROM sales_event PARTITION (p202601)
GROUP BY event_date
ORDER BY event_date;
```

Reconcile against the ETL batch manifest or source totals. Do not check only total row count: data could have the right count while holding wrong tenants, wrong dates, or wrong business amounts.

### 8.4. Verifying Partition Pruning

```sql
EXPLAIN
SELECT event_id, event_date, amount
FROM sales_event
WHERE event_date >= '2026-01-01'
  AND event_date <  '2026-02-01';
```

In the output, inspect the `partitions` column to confirm MySQL only needs to read the matching partition such as `p202601`. If rows sit in the wrong partition due to an unvalidated exchange, pruning may skip them.

## 9. Conditions and Limitations to Check

| Condition | Why it matters |
|---|---|
| Source table is partitioned, staging is unpartitioned | Exchange only swaps one partition with a regular table |
| Exact partition name | Wrong name or missing partition causes DDL to fail |
| Compatible columns and column order | MySQL requires matching row structures on both sides |
| Compatible indexes | B-trees and index definitions must align for exchange |
| Same storage engine | Avoids swapping between engines with different layouts/semantics |
| No foreign key constraints | Partitioned InnoDB tables do not support foreign keys |
| Staging is not a temporary table | Temporary tables cannot participate in exchange |
| Unique keys include partition columns | Mandatory under MySQL partitioning rules |
| Data lies within partition bounds | Validation checks this; bad data breaks pruning correctness if validation is skipped |
| Staging is frozen | Prevents data changes between validation and exchange |

Before deploying, check the requirements of your exact MySQL version. Partitioning restrictions, column types, and DDL rules can differ across releases.

## 10. Metadata Locks, Implicit Commit, and Operations

`EXCHANGE PARTITION` is executed via `ALTER TABLE`, so treat it as a DDL operation. DDL may require metadata locks on both the partitioned table and the staging table; if another transaction is actively using either table, the operation may wait. Conversely, a DDL waiting on a metadata lock can queue incoming queries behind it.

Before running in production:

- Check long-running transactions and active metadata locks.
- Run the exchange during an appropriate load window.
- Ensure no other writer modifies staging during validation/exchange.
- Monitor lock wait times, replication lag, and DDL errors.
- Prepare a remediation plan if validation fails or staging contains invalid rows.

### 10.1. Do Not Expect Transactional Rollback of DDL

`ALTER TABLE` statements trigger an implicit commit under MySQL rules. Never wrap `EXCHANGE PARTITION` in a transaction expecting `ROLLBACK` to reverse the swap like an ordinary InnoDB `UPDATE`.

Treat exchange as a separate DDL boundary. Atomic DDL in MySQL 8.0 with InnoDB guarantees atomicity of supported DDL operations during crashes, but does not turn DDL into something freely rollbackable inside an application transaction. Test on the exact MySQL version and prepare a data recovery plan.

### 10.2. Validation and Lock Duration

`WITH VALIDATION` scans staging data to ensure rows belong to the target partition. With very large staging tables, this step can lengthen the operation. Load data, verify bounds, and reconcile ahead of time to catch errors early; MySQL validation remains the final safety net during exchange.

If using `WITHOUT VALIDATION`, external checks must be trustworthy and staging data must remain unmodified between external validation and the exchange. A single `MIN/MAX` check is not sufficient for every partitioning model, especially with multi-column partitioning expressions.

## 11. Standard Partition Ingestion Workflow

An ETL pipeline can be structured as follows:

1. Identify the target partition and exact bounds from schema/metadata.
2. Create or truncate staging per approved data policies; verify staging is empty before loading if targeting an empty partition.
3. Load the batch into staging.
4. Verify schema, engine, indexes, and unpartitioned status of staging.
5. Check for out-of-bounds rows, duplicate keys, NULLs, and business rule violations.
6. Freeze staging so other writers cannot alter data.
7. Record batch row counts, min/max, control sums, or checksums.
8. Run `ALTER TABLE ... EXCHANGE PARTITION ... WITH VALIDATION`.
9. Recount the partition and staging; reconcile against the manifest.
10. Verify partition pruning with a representative query.
11. Log exchange results and clean up staging according to policy.
12. Monitor metadata locks, replication, and performance post-deployment.

If exchange fails, data remains safely in staging for investigation. Never truncate staging or reload over it before identifying the root cause.

## 12. Standard Partition Archival Workflow

To move an old partition out:

1. Confirm the period is closed and no late-arriving events still need ingestion.
2. Verify partition bounds and data inside the partition.
3. Create an unpartitioned archive staging table with matching structure/indexes.
4. Confirm archive staging is empty.
5. Record row counts and reconciliation totals in the partition.
6. Exchange the partition with staging using `WITH VALIDATION`.
7. Reconcile row counts and metrics in archive staging.
8. Export/back up/move archive staging per archival procedures.
9. Truncate/drop staging only after the archive is verified and retention policy permits.
10. If reusing the emptied partition, update the ingestion pipeline for the next cycle.

EXCHANGE does not delete old data on its own, nor does it compress or back up archived data. It solely transfers data between a partition and a regular table.

## 13. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Exchange reports incompatible schema | Mismatched columns, types, order, or indexes | Compare `SHOW CREATE TABLE`; create staging from the same schema version |
| Staging rejected as partitioned | Target table also has partitions | Use a regular table without `PARTITION BY` |
| Validation fails | Rows lie outside target partition bounds | Query for out-of-range rows, fix data, or pick the right partition |
| Unexpected row count in partition after exchange | Exchange is a swap; old partition data moved to staging | Record counts on both sides and remember bidirectional swap semantics |
| Queries fail to find some rows | Data was exchanged with WITHOUT VALIDATION and sits in the wrong partition | Check partition keys/bounds and re-exchange via a validated workflow |
| DDL waits for a long time | Metadata locks or validation over large staging | Inspect transactions/MDL, shrink staging, pick a better window |
| ROLLBACK does not undo exchange | ALTER TABLE causes implicit commit | Build a DDL procedure and reverse-exchange plan if recovery is needed |
| Cannot create unique key | Unique key lacks partition columns | Include partition columns in all unique keys or redesign partitioning |
| Archive stage still holds old data | Stage was not empty prior to exchange | Reconcile and empty staging per policy before swapping |
| Staging data changed after validation | Another writer still writes to staging | Freeze/lock write permissions during preflight and exchange |

## 14. Practice Lab

Practice in a dedicated lab schema with `sales_event` and `sales_event_stage`:

1. Create `sales_event` partitioned monthly by `RANGE COLUMNS(event_date)`.
2. Try declaring `PRIMARY KEY(event_id)` and observe the partition-column-in-unique-key rule; fix it to `(event_id, event_date)`.
3. Create an unpartitioned staging table with identical columns, column order, data types, primary key, secondary indexes, and InnoDB engine.
4. Use `SHOW CREATE TABLE` to compare both definitions and verify only the main table has a partition clause.
5. Load January 2026 data into staging; check counts, min/max, and out-of-bounds rows.
6. Try adding a row dated `2026-02-01`; run exchange with `WITH VALIDATION` and observe the error.
7. Delete or move the out-of-range row, re-run exchange; verify the partition receives the data and staging becomes empty if the partition started empty.
8. Load data into staging while the partition already contains data; exchange and verify the two datasets are swapped, not appended.
9. Create an empty archive staging table and exchange the partition out; verify the partition is empty and staging holds the old data.
10. In an isolated lab, test `WITHOUT VALIDATION` with out-of-bounds rows; observe the partition pruning correctness risk and restore the clean state.
11. Use `INFORMATION_SCHEMA.PARTITIONS` to inspect partition metadata and `EXPLAIN` to confirm pruning for date queries.
12. Hold an open read transaction on the table in another session while running exchange; observe the metadata lock wait and commit/end the transaction to let DDL proceed.
13. Build a manifest with row counts, min/max dates, amount totals, and checksums; reconcile before and after exchange.
14. Write an operational runbook for partition loading and archiving covering preflight, exchange, verification, error handling, and staging cleanup criteria.

You have completed this lesson when you can explain exchange as a two-way swap, verify staging data belongs within target partition bounds, and reconcile post-exchange data using both metadata and business queries.

## 15. Principles to Remember

- `EXCHANGE PARTITION` swaps data between one partition and one regular table; it does not append.
- After exchange, the partition holds staging's previous data and staging holds the partition's previous data.
- Use `WITH VALIDATION` so MySQL verifies staging data belongs to the target partition; this is the default when `WITHOUT VALIDATION` is omitted.
- `WITHOUT VALIDATION` skips bounds checks and can place rows in the wrong partition, causing partition pruning to return incomplete results.
- The staging table must be unpartitioned with compatible structure and indexes; both sides must use the same storage engine.
- InnoDB partitioned tables do not support foreign keys; do not design exchange with tables carrying foreign key constraints.
- Every column in the partitioning expression must appear in every unique key, including the primary key.
- Verify bounds, schema, engine, indexes, row counts, and business rules before exchange.
- Use `INFORMATION_SCHEMA.PARTITIONS`, `SHOW CREATE TABLE`, `COUNT(*)`, `MIN/MAX`, and `EXPLAIN` to verify.
- Exchange is DDL (`ALTER TABLE`), triggers implicit commit, and may require metadata locks.
- Validation time can scale with staging row count; prepare data ahead of time to shorten operation duration.
- When archiving a partition, staging must be empty if the goal is receiving the entire partition's data.
- Never truncate/drop staging before archived data is reconciled and safely stored.
- Always test on the exact MySQL version and prepare a recovery runbook before production execution.
