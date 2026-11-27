# Recovering Large Tables, Verifying Constraints, and Reconciling Business Metrics

Recovering a large table in MySQL requires more than simply reloading an SQL file. A table may hold millions or billions of rows, have foreign keys to other tables, unique indexes, CHECK constraints, triggers, and data that continues changing elsewhere in the system. A recovery is only considered successful once the data is completely loaded, structures and relationships are preserved, business metrics match the chosen recovery checkpoint, and the application can safely resume operation.

This lesson belongs to mastering MySQL from table design, data types, keys, queries, indexes, and transactions to backup, recovery, and handling operational issues. The focus is the workflow for recovering a large table, checking constraints, and reconciling data from a business perspective before returning the table to serve the application.

## 1. Defining the Exact Recovery Objective

Before running commands, clarify which table needs recovery, the target data checkpoint, and the impact on the application. Several scenarios exist:

| Scenario | Goal | Typical Approach |
|---|---|---|
| A table was accidentally dropped | Restore the table as of right before the drop | Restore backup to a temp environment, apply binary logs up to right before the drop, then extract the table |
| Certain rows were wrongly updated or deleted | Recover the affected rows | Recover to an appropriate point in time, identify primary keys of rows to retrieve, and reconcile before updating |
| Table suffered data corruption after deployment | Restore the valid data state | Use a backup or authoritative source, checking changes that occurred since the backup timestamp |
| Need to move a table to another server | Migrate schema and data to target | Export table, load into a staging table, verify compatibility, and only then cut over the application |
| Need to recover a very large table | Bring data back with controlled disruption | Recover in staging, load in batches or bounded parallelism, reconcile in parts, and plan cutover |

Three facts must be clearly established:

- **Recovery point:** at what exact time must the data be accurate? The latest backup may not suffice if the incident happened afterward.
- **Recovery scope:** must the whole table, a time window, or a subset of rows identified by keys be recovered?
- **Write boundary:** while recovering, is the application still allowed to write to the table, or must writes pause to avoid losing new changes?

Never start loading data before knowing where the backup came from, whether it is consistent, and which binary logs are available to bring the data to the needed checkpoint. If a trustworthy data source or recovery point has not yet been determined, preserve the current state and gather information first.

## 2. Preparing the Environment and Recovery Source

### 2.1. Preserving Evidence and Current Data

When a table issue is discovered, restrict operations that could overwrite more data. Record the discovery time, the account that performed the change if known, the related statement or deployment session, and the affected application scope. If possible, capture the current state with a separate backup or export before making repairs.

Never directly overwrite the troubled table merely because a backup was found. The live table may still contain valid transactions committed after the backup timestamp. Keeping a copy for investigation and comparison reduces the risk of losing those changes.

### 2.2. Choosing the Data Source

The recovery source usually falls into one of these types:

- **Logical backup:** data exported as SQL statements or a logical format. Allows single-table recovery and easy movement between compatible servers, though export and load times can be long for very large tables.
- **Physical backup:** copies of MySQL or InnoDB data files. Usually faster to recover a large instance as a whole, though this does not mean a single table can be plucked directly. Typically you restore the instance onto a temporary host and then extract the table.
- **Binary logs:** record data-change events after the backup checkpoint. Events up to a specific time or position can be applied to perform point-in-time recovery (PITR).
- **Business data sources:** exports from upstream systems, data warehouses, or reconciliation records. These can assist in validating figures, provided completeness, timestamps, and transformation rules are verified.

For PITR, you need a baseline backup and continuous binary logs from the position recorded in the backup metadata up to the target time. If a log segment is missing, never assume remaining logs suffice to reconstruct the exact state.

### 2.3. Compatibility Checks

Before recovering into staging, verify at least:

- MySQL version and the table's storage engine.
- Character set, collation, data types, `DECIMAL` precision, and time zones used by the application.
- Primary key structure, unique indexes, foreign keys, CHECK constraints, generated columns, and partitions.
- Triggers, views, or application jobs depending on the table.
- Plugins, tablespace encryption, TLS settings, or source-specific features if applicable.

Cross-check the table definition with:

~~~sql
SHOW CREATE TABLE app_db.orders;
~~~

Do not compare only column names and counts. Differences in **UNSIGNED**, **NULL**, default values, collations, index column order, or generated column expressions can alter how data is interpreted or break application behavior.

### 2.4. Resource Estimation

For large tables, backup file size does not equal the space required during recovery. Account for:

- Space for the staging copy, the live copy, and post-cutover retention copies.
- Space for secondary indexes, temporary files, redo logs, undo logs, and binary logs generated during loading.
- Disk I/O, network throughput, and concurrent load threads.
- Buffer pool capacity and impact on other workloads.
- Replication lag if the recovery host is a replication source or target.

Benchmark on representative data or an equivalent environment. A fast load on a tiny test machine does not predict recovery duration for a production table.

## 3. Recovering the Table into a Staging Environment

Staging is where data is verified before replacing the table serving the application. You can use a dedicated MySQL instance or a properly isolated temporary schema. This environment should match the target's version, configuration, and structure.

### 3.1. Exporting a Single Table with `mysqldump`

If the source is a live MySQL instance and the table uses InnoDB, you can take an isolated logical dump:

~~~bash
mysqldump --single-transaction --quick --hex-blob app_db orders > orders.sql
~~~

Meaning of options:

- **--single-transaction** establishes a consistent snapshot for transactional tables such as InnoDB without locking the entire table for the duration of the dump.
- **--quick** reads and writes rows one at a time rather than buffering the whole result set in client memory.
- **--hex-blob** represents binary data in a safe format for export and import.

**--single-transaction** does not guarantee a consistent snapshot for tables using non-transactional engines such as MyISAM. During the dump, also avoid DDL operations such as ALTER, DROP, or RENAME on the exported table because they can fail the dump or break consistency. If multiple related tables must be dumped, account for snapshot mechanics so all tables share the same data checkpoint.

For very large tables, the dump file can take substantial disk space and time. Check destination disk space, monitor progress, and protect backup files according to your system's data policy.

### 3.2. Restoring the Dump into a Temporary Schema

Create the staging schema with the appropriate charset and collation:

~~~sql
CREATE DATABASE restore_stage
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

The collation name above is an example for MySQL 8.0; use the actual charset and collation from the source system. Load the dump into the temporary schema:

~~~bash
mysql --host=restore-db --user=restore_operator --password restore_stage < orders.sql
~~~

Passing **--password** without a value prompts interactively for the password, avoiding writing secrets directly into command history. The recovery account should hold only necessary privileges in staging.

After loading, confirm the table exists with the right structure:

~~~sql
SHOW TABLES FROM restore_stage LIKE 'orders';
SHOW CREATE TABLE restore_stage.orders;
~~~

If the source is a physical backup, the workflow is typically restoring the backup onto a temporary instance per the backup tool's guide, starting and checking that instance, and then using a logical dump to extract the needed table. Never arbitrarily copy a `.ibd` file into a live data directory expecting MySQL to adopt the table automatically; InnoDB has metadata, dictionary entries, tablespaces, and compatibility requirements that must be handled properly.

### 3.3. Point-in-Time Recovery with Binary Logs

When a table was wrongly altered after the backup timestamp, PITR may be required. General workflow:

1. Restore the baseline backup onto a temporary instance.
2. Read backup metadata to identify the starting binary log file/position or GTID.
3. Apply continuous binary logs up to right before the erroneous transaction or to an approved recovery checkpoint.
4. Verify data on the temporary instance, and only then extract the table.

Illustrative example applying logs with a start position and stop datetime:

~~~bash
mysqlbinlog \
  --start-position=12345 \
  --stop-datetime="2026-11-19 10:30:00" \
  binlog.000123 binlog.000124 \
  | mysql --host=restore-db --user=restore_operator --password
~~~

File names, positions, and timestamps in the example are placeholders. Substitute actual backup metadata and verified checkpoints. The start position must match the backup state; the stop point must precede the corrupting transaction if the goal is recovering the state before that transaction. Whenever possible, use recorded file/position or GTID to pinpoint the exact boundary; timestamps should only be used once you understand time zones and exact event timestamps in the logs.

Never apply binary logs directly onto production merely to test a recovery point. Binary logs may contain changes across many tables and schemas; apply them on a temporary instance, verify the result, and then extract the scope needing recovery.

## 4. Controlled Loading of Large Data

A single import command may suit moderate tables, whereas large tables usually require managing throughput, memory, transactions, and resumability on errors.

### 4.1. Batch Loading by Primary Key

If data is exported as row sets or files by key range, chunk along a stable primary key. For example, using **orders.id**:

~~~sql
SELECT *
FROM restore_stage.orders
WHERE id >= 1 AND id < 100001
ORDER BY id;
~~~

The next batch uses `[100001, 200001)` and so on. Boundaries do not overlap and leave no gaps. Primary-key range chunking is usually far easier to resume than `LIMIT offset, count` pagination, because large offsets force the server to read and discard many rows.

When batch-loading into a staging table, specify an explicit column list:

~~~sql
INSERT INTO app_db.orders_restore
  (id, customer_id, status, total_amount, created_at)
SELECT
  id, customer_id, status, total_amount, created_at
FROM restore_stage.orders
WHERE id >= 1 AND id < 100001
ORDER BY id;
~~~

An explicit column list avoids dependence on column ordering and clarifies handling of generated or default-value columns. The example assumes both tables have compatible structures and the target table already exists. Confirm data types, charsets, collations, and conversion rules before running.

### 4.2. Choosing Transaction Size

Do not default to loading the entire table in one giant transaction. Oversized transactions generate huge undo logs, hold row locks too long, lengthen rollbacks, and pressure redo logs or replication. Tiny transactions increase commit overhead and can lower throughput.

Pick batch sizes based on commit latency, I/O, log volume, and system load. After each batch:

1. Confirm the statement succeeded and the expected row count was processed.
2. Record the completed key range in a progress log.
3. Check batch row counts or sums.
4. Mark the batch complete only after the transaction commits.

If the process is interrupted, use the progress log to resume from the incomplete range. Never blindly rerun a batch that might already have committed. **INSERT IGNORE** or **ON DUPLICATE KEY UPDATE** can mask key conflicts or overwrite data unintentionally; use them only when the recovery policy explicitly defines how each case is handled.

### 4.3. Organizing Indexes and Constraints

Indexes speed up queries and enforce uniqueness, but maintaining numerous secondary indexes while loading millions of rows increases write overhead. For staging tables, you may consider building certain secondary indexes after loading data if validation procedures and integrity requirements permit. However:

- Primary keys and unique constraints guard uniqueness; never skip conflicts simply for speed.
- If adding a unique index post-load, check for duplicates first and resolve duplicates per business rules.
- Never drop foreign keys or CHECK constraints on production tables to speed up recovery without an equivalent verification mechanism.
- Post-load index creation also consumes I/O, CPU, and temp space; benchmark and plan accordingly.

After loading large volumes, refresh optimizer statistics:

~~~sql
ANALYZE TABLE app_db.orders_restore;
~~~

This updates statistics for query plan selection; it does not prove the data is business-correct.

### 4.4. Monitoring Operational Impact

During loading, monitor:

- Write throughput, commit latency, and per-batch processing time.
- CPU, IOPS, disk throughput, and remaining free space.
- Redo/undo log sizes, binary log growth, and temp file usage.
- Connection counts, lock waits, deadlocks, and long-running transactions.
- Replication lag if replicas receive changes from the recovery host.

Cap concurrent loader threads. Increasing concurrency too aggressively causes threads to contend on I/O and indexes, lengthening total runtime. If production degrades, throttle load speed or shift work onto a dedicated instance instead of piling on load.

## 5. Checking Structure and Constraints

Constraint verification must happen before cutover. A table with the right row count can still be broken if it lacks indexes, contains orphaned foreign keys, or violates business domain rules.

### 5.1. Structural Comparison

Compare `SHOW CREATE TABLE` across the authoritative source, staging, and target tables. Verify:

- Column list, order, data types, lengths, and `UNSIGNED` attributes.
- `NULL`, `DEFAULT`, `AUTO_INCREMENT`, and generated columns.
- Primary key, unique indexes, secondary indexes, and column order inside each index.
- Foreign keys, `ON DELETE`, and `ON UPDATE` actions.
- CHECK constraints, partitions, engine, charset, and collation.
- Triggers attached to the table and dependent objects.

If the table was recovered from a different MySQL version, verify feature syntax and enforcement. For example, CHECK constraints are enforced by MySQL starting in 8.0.16; earlier versions may accept the syntax without enforcing the condition as expected. Also check whether constraints are declared `ENFORCED`.

### 5.2. Checking Primary Keys and Unique Keys

Primary keys must be unique and non-NULL. If the staging table already defines a primary key, duplicate keys during loading normally fail the statement or transaction. If data was loaded into a temporary table without unique indexes, verify uniqueness before creating indexes:

~~~sql
SELECT id, COUNT(*) AS duplicate_count
FROM app_db.orders_restore
GROUP BY id
HAVING COUNT(*) > 1
LIMIT 20;
~~~

Check a unique business key, such as **order_number**:

~~~sql
SELECT order_number, COUNT(*) AS duplicate_count
FROM app_db.orders_restore
GROUP BY order_number
HAVING COUNT(*) > 1
LIMIT 20;
~~~

For composite unique keys, group by all columns in the key. Never arbitrarily delete one of the duplicate rows; determine which row is valid according to the authoritative source and business rules.

### 5.3. Checking Foreign Keys

Suppose **orders.customer_id** references **customers.id**. Find orphaned rows using an anti-join:

~~~sql
SELECT COUNT(*) AS orphan_count
FROM app_db.orders_restore AS o
LEFT JOIN app_db.customers AS c
  ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

The expected result is **orphan_count = 0**, unless business logic permits a documented special reference case. Run checks for every foreign key and confirm the parent table is checked at the same data checkpoint as the child table.

Recovery order is normally parent tables first, child tables second. Loading in another order can trigger foreign key errors. MySQL does not support deferring foreign key checks until transaction commit like some other DBMSs.

**SET FOREIGN_KEY_CHECKS = 0** can be used inside a controlled load workflow, but understand a crucial limitation: when re-enabling **FOREIGN_KEY_CHECKS = 1**, MySQL does not automatically scan and re-verify rows loaded while checks were disabled. Therefore, re-enabling it does not prove the data has no orphans. If used, you must run independent foreign-key validation queries before cutover. Avoid altering the variable at global scope for routine data loads.

### 5.4. Checking CHECK Constraints and Domain Rules

CHECK constraints can express rules such as non-negative quantities or end dates not earlier than start dates. Example:

~~~sql
ALTER TABLE app_db.orders_restore
  ADD CONSTRAINT chk_orders_total_nonnegative
  CHECK (total_amount >= 0);
~~~

Add the constraint only if it matches business rules and the MySQL version enforces it. Before adding, find violating rows:

~~~sql
SELECT COUNT(*) AS invalid_amount_count
FROM app_db.orders_restore
WHERE total_amount < 0;
~~~

Conditions can evaluate to `UNKNOWN` when expressions contain `NULL`; therefore, a CHECK constraint does not replace a `NOT NULL` requirement. For instance, if `total_amount` must always have a value, check for both nulls and negative numbers, or declare the column `NOT NULL` per design.

## 6. Reconciling Business Metrics

Business reconciliation answers the question: does the recovered data produce the exact results the system and users expect? Checking structures and constraints is necessary but not sufficient. A table can pass every key check yet still miss an entire day of data, hold wrong order statuses, or have skewed monetary totals.

### 6.1. Comparing Row Counts and Key Ranges

Check row counts along with minimum and maximum key values:

~~~sql
SELECT
  COUNT(*) AS row_count,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM app_db.orders_restore;
~~~

Compare against the backup source or metrics captured at the same checkpoint. `COUNT(*)` on InnoDB can require scanning substantial data and take time on huge tables. The estimate in `information_schema.TABLES.TABLE_ROWS` is not an exact count; use it only for planning estimates.

To locate missing ranges, split data by primary key intervals and compare per-interval row counts between source and staging. This isolates discrepancies without processing the whole table in one giant aggregate query.

### 6.2. Comparing Totals and Counts by Status

Suppose the orders table has `status`, `total_amount`, and `created_at`. An aggregate report could be:

~~~sql
SELECT
  DATE(created_at) AS order_date,
  status,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_amount
FROM app_db.orders_restore
WHERE created_at >= '2026-11-01'
  AND created_at <  '2026-11-20'
GROUP BY DATE(created_at), status
ORDER BY order_date, status;
~~~

Compare daily and status-grouped results against the trusted source or closed business reports at the matching timestamp. Use `DECIMAL` for monetary values and compare at exact specified precision; never cast to `FLOAT` for financial reconciliation because binary floating-point rounding introduces discrepancies.

### 6.3. Checking Nulls, Value Ranges, and Timestamps

The following queries help surface anomalous data:

~~~sql
SELECT
  SUM(customer_id IS NULL) AS missing_customer,
  SUM(total_amount IS NULL) AS missing_total,
  SUM(total_amount < 0) AS negative_total,
  MIN(created_at) AS first_order,
  MAX(created_at) AS last_order
FROM app_db.orders_restore;
~~~

Exact expectations depend on business logic. An order might lack `customer_id` in certain intake flows; some statuses might have a zero total. Never conclude data is corrupt based solely on a non-zero or `NULL` count without understanding the domain rules.

### 6.4. Cross-Checking with Related Tables or Upstream Systems

If every paid order must have a corresponding payment record, check for orders lacking payments:

~~~sql
SELECT COUNT(*) AS orders_without_payment
FROM app_db.orders_restore AS o
LEFT JOIN app_db.payments AS p
  ON p.order_id = o.id
WHERE o.status = 'PAID'
  AND p.order_id IS NULL;
~~~

This is an example check; a system might permit delayed payment recording or split payments across multiple transactions. Adapt the query to the real data model, such as aggregating multiple payments per order or excluding unsettled states.

For critical data like balances, revenue, or inventory, also reconcile against ledgers, payment processors, or independent business sources. Pin down exact timestamps, time zones, included statuses, and refund/cancellation rules. Two reports using different time cutoffs or filters can disagree even when the table was recovered accurately.

### 6.5. Batch-by-Batch Verification

For extremely large tables, partition reconciliation by key ranges or time intervals:

~~~sql
SELECT
  COUNT(*) AS row_count,
  SUM(total_amount) AS total_amount,
  MIN(created_at) AS first_created_at,
  MAX(created_at) AS last_created_at
FROM app_db.orders_restore
WHERE id >= 100001
  AND id < 200001;
~~~

Record each batch's key boundaries, row count, and monetary total. When a batch differs, investigate only that interval. You can supplement with per-batch digests if the system has a stable checksum tool; checksums are only a supporting signal and require agreeing on columns, row ordering, data types, and normalization rules before comparing.

### 6.6. Comparing at the Same Data Checkpoint

A common reconciliation mistake is comparing staging as of backup time against live production continuing to receive transactions. Both sides will legitimately differ. Pick one of these approaches:

- Pause writes during verification and cutover.
- Bring staging and source to the exact same checkpoint using binary logs or a verified sync mechanism.
- Record a clear watermark, such as the highest primary key or last processed transaction timestamp, and compare the identical scope.

If the application has multiple writers or asynchronous processing, account for events still sitting in queues. A simple watermark on `MAX(id)` may be insufficient if IDs are allocated prior to transaction commit or across independent write sources.

## 7. Promoting the Verified Table into Service

Cut over only after data and structures pass all required checks. The cutover plan must clearly state write-pause duration, how transactions occurring after the backup checkpoint are handled, and how to revert to the old table if post-cutover checks fail.

### 7.1. Finalizing Trailing Changes

If the application kept writing while staging was recovered, staging may miss recent transactions. Three common handling methods exist:

1. **Maintenance window:** stop the application or switch it to read-only, record the final watermark, bring staging to that exact point, and cut over.
2. **Delta replay:** capture and apply changes since the snapshot in an ordered workflow ensuring no missed or duplicate transactions.
3. **Dual-write or change capture:** use only when the system already has a sync mechanism designed, monitored, and tested for recovery scenarios.

Never improvise a temporary change-capture mechanism mid-incident without establishing transaction ordering, write conflicts, and missed-data detection.

### 7.2. Choosing the Cutover Method

For simple tables, you can consider swapping table names in a single multi-table `RENAME TABLE` operation:

~~~sql
RENAME TABLE
  app_db.orders TO app_db.orders_before_restore,
  app_db.orders_restore TO app_db.orders;
~~~

This is only an illustrative example of one cutover option. Before using it, test on an equivalent version and schema, especially if the table has incoming foreign keys from other tables, triggers, views, partitions, or dependent objects. Renaming can affect metadata and application dependencies. Never assume every system can swap tables with a one-liner like this without adjustments.

If safe renaming is not possible, batch-load data into the target table inside a maintenance window, or design a dedicated cutover tailored to data relationships. DDL statements like `ALTER TABLE` and `RENAME TABLE` cause implicit commits; never rely on `ROLLBACK` to undo a DDL cutover.

### 7.3. Immediate Post-Cutover Checks

After cutover:

- Confirm the application connects to the right schema and new table.
- Run representative read queries and controlled write probes if permitted by workflow.
- Monitor application errors, constraint violations, and MySQL logs.
- Watch latency, lock waits, deadlocks, CPU, I/O, and replication lag.
- Compare key business metrics against approved staging results.
- Retain the old table or snapshot for the agreed retention period for investigation or rollback.

Never drop the old table right after a single test query succeeds. Clean up only after the data owner signs off on results and the required monitoring window has elapsed.

## 8. Common Recovery Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Import stops with duplicate key | Duplicate keys in data or target table already partially populated | Identify committed batches, locate duplicate keys, and resolve per business rules |
| Import reports foreign key error | Parent table not yet restored, missing referenced ID, or schema mismatch | Restore parent tables first, run anti-joins, and compare key column types |
| Orphans still present after re-enabling `FOREIGN_KEY_CHECKS` | MySQL does not re-validate rows loaded while checks were off | Run verification queries for every relationship before cutover |
| Very slow data loading | Saturated I/O, too many secondary indexes, oversized transactions, or excessive threads | Benchmark batches, lower concurrency, tune transaction size, and check resources |
| Disk space growing rapidly | Staging files, indexes, redo/undo, binlogs, or temp files expanding | Forecast space upfront, monitor free space, and pause cleanly if nearing exhaustion |
| Monetary sum matches yet order count differs | Offsetting errors or mismatched filters/statuses | Compare counts, sums, status groupings, and time windows together |
| Staging data differs from production | Two sides sit at different checkpoints or unsynced transactions remain | Pin a watermark or align both sides to the same checkpoint |
| Application errors after cutover | Missing indexes, triggers, privileges, views, or schema differences | Diff schemas and dependencies, inspect app/MySQL logs, and trigger rollback plan |

## 9. Sample Practice Workflow

Suppose a retail system's `orders` table has hundreds of millions of rows. It contains `id`, `customer_id`, `status`, `total_amount`, and `created_at`; `customer_id` references `customers.id`. A deployment mistake wiped part of the data on November 18. The goal is recovering data accurately up to right before the erroneous action.

Execute the following workflow:

1. Record the timestamp of the erroneous action and locate the corresponding transaction or event in audit logs/binlogs.
2. Select the most recent baseline backup prior to the error, verifying metadata and binary log continuity.
3. Restore the backup onto a temporary instance compatible with production.
4. Apply binary logs up to right before the erroneous action; verify the stop checkpoint and data at that moment.
5. Export the `orders` table alone from the temporary instance and load it into `restore_stage`.
6. Cross-check structure, primary key, unique keys, foreign keys, CHECK constraints, and triggers.
7. Reconcile row counts by ID ranges, monetary totals by date/status, min/max timestamps, and order counts by status.
8. Run an anti-join to check for orphaned `customer_id` values; cross-check paid order counts against payments or business sources.
9. Finalize the strategy to preserve transactions committed since the snapshot: maintenance window, delta replay, or existing change capture.
10. Cut over per the tested plan, monitor the application, and remove the old table only after data-owner sign-off.

Results to document include backup source, PITR position/GTID and timestamp, table structure, batch row counts, reconciliation metrics, constraint violation counts, cutover timestamp, and sign-off owner. This makes future recoveries repeatable and auditable.

## 10. Pre-Confirmation Recovery Checklist

- [ ] Identified exact table, data scope, and recovery point.
- [ ] Verified origin, metadata, and continuity of backup and binary logs.
- [ ] Preserved current state for investigation or rollback.
- [ ] Staging matches in version, engine, charset, collation, and schema structure.
- [ ] All data loaded; committed batches recorded.
- [ ] Primary key and unique keys have no unexpected conflicts.
- [ ] Foreign keys have zero orphans; CHECK constraints and domain rules hold.
- [ ] Row counts, key ranges, business aggregates, and timestamps match authoritative source.
- [ ] Staging and comparison dataset align on the same checkpoint or watermark.
- [ ] Post-snapshot transactions handled.
- [ ] Cutover and rollback plans tested against table dependencies.
- [ ] Application and operational metrics verified post-cutover.

## 11. Self-Check Questions

1. Why should a large table be recovered into staging before replacing the production table?
2. What does `mysqldump --single-transaction` guarantee, and what does it not guarantee?
3. Why does recovering a single table from a physical backup usually require restoring a temporary instance first?
4. When performing PITR, what information from backup metadata is needed to choose the exact starting point for applying binary logs?
5. Why is disabling `FOREIGN_KEY_CHECKS` and turning it back on insufficient to prove a table has no orphaned rows?
6. For an orders table, which metrics besides `COUNT(*)` should be reconciled?
7. Why must staging and production be compared at the exact same timestamp or watermark?
8. Which dependencies must be checked before using `RENAME TABLE` for cutover?

A trustworthy recovery must prove three things: the data came from a verified source and point in time, relational constraints were actually validated, and critical business metrics match the reference source. Only once that evidence is in hand should the table return to serving the application.
