# Schema Evolution

## Implicit Commit DDL and Partial-Failure-Resilient Design

MySQL schema changes are typically deployed using DDL statements such as creating tables, adding columns, changing data types, creating indexes, or adding constraints. Unlike many DML operations, most significant DDL statements cause an implicit commit: any open transaction is committed before the statement runs. Therefore, placing multiple DDL statements inside a transaction and calling `ROLLBACK` cannot restore the schema to its initial state.

In the **DATABASE_MYSQL** module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. These skills help you plan schema changes while keeping data consistent, controlling metadata locks, minimizing disruption, and recovering when a migration step fails.

This lesson explains implicit commits, atomic DDL, and their limits; it then establishes how to organize multi-step migrations to tolerate mid-execution failures. The focus is on state tracking, pre- and post-condition verification for each DDL statement, deploying with the expand-contract pattern, and choosing safe forward-fix approaches when a migration has partially completed.

### 1. DDL and implicit commits

DDL (Data Definition Language) modifies database object definitions. Common statements include:

- CREATE TABLE, ALTER TABLE, DROP TABLE.
- RENAME TABLE, TRUNCATE TABLE.
- CREATE INDEX, DROP INDEX.
- CREATE DATABASE, DROP DATABASE.
- Statements creating or altering views, routines, triggers, and events.

Many DDL statements in MySQL trigger an implicit commit. This has two consequences:

1. If the session has an uncommitted DML transaction open, the DDL commits that transaction before executing.
2. If the DDL succeeds, a subsequent ROLLBACK neither undoes the DDL nor restores the DML that was implicitly committed earlier.

Example:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL;

ROLLBACK;
~~~

Never assume the final ROLLBACK will undo both the UPDATE and the ALTER. The DDL has already committed the preceding transaction; the new schema remains in place if ALTER succeeded. This is why uncommitted business DML work must never be mixed with DDL in the same session.

#### 1.1. Statements that act as transaction boundaries

The table below summarizes several statement groups that commonly cause an implicit commit. The exact list varies by version; check the documentation for your specific version before designing migration tooling.

| Group | Examples | Notes |
|---|---|---|
| Database/table changes | CREATE DATABASE, ALTER DATABASE, DROP DATABASE, CREATE TABLE, ALTER TABLE, DROP TABLE | Typically commits any open transaction before running |
| Structural rename/truncation | RENAME TABLE, TRUNCATE TABLE | Not equivalent to DELETE; ROLLBACK cannot restore truncated data |
| Indexes | CREATE INDEX, DROP INDEX | Alters table structure and may require metadata locks |
| Stored SQL objects | Many CREATE, ALTER, DROP statements for views, routines, triggers, events | Verify the implicit-commit list for your version |
| Privilege management | GRANT, REVOKE, CREATE USER, ALTER USER, DROP USER | Security changes; do not combine with business transactions |
| Transaction/session control | START TRANSACTION, changing autocommit from 0 to 1 | Can terminate an active open transaction |

There is an important exception: CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE do not cause an implicit commit the way their regular-table counterparts do. However, creating/dropping temporary tables is still not undone by ROLLBACK. This exception does not make DDL transactional in general.

#### 1.2. Atomic DDL in MySQL 8.0 is not transactional DDL

MySQL 8.0 introduced atomic DDL for supported operations. For an atomic DDL statement and a compatible storage engine, MySQL coordinates the data dictionary, storage engine, and binary log so the statement completes as an atomic unit, even if the server crashes mid-execution.

Atomic DDL addresses the integrity of **a single supported DDL operation** upon failure or crash. It does not mean:

- ROLLBACK can undo DDL.
- Multiple independent DDL statements can be grouped into a single schema transaction.
- All engines, object types, and DDL operations share the same level of atomicity.
- A multi-step migration automatically reverts to its initial state if the last step fails.

For example, a migration containing ADD COLUMN, backfill UPDATE, and ADD INDEX can still halt after the first two steps have completed. Statement-level atomicity does not turn the whole sequence into an all-or-nothing unit.

MySQL 5.7 lacks a general atomic DDL mechanism like MySQL 8.0. Crash behavior and recoverability depend on the operation, storage engine, and version. When upgrading or deploying the same migration across multiple version series, test each separately.

### 2. Why can a migration complete partially?

A real-world migration often consists of multiple statements and stages:

1. Add a new column or table.
2. Update legacy data.
3. Create indexes or constraints.
4. Deploy application code using the new schema.
5. Drop old columns or tables in a later release.

Suppose a script runs three DDL statements. The first succeeds, the second succeeds, and the third fails due to a duplicate key. At that point, the schema is in an intermediate state. If the client loses connectivity immediately after sending a DDL statement, the outcome is also ambiguous from the orchestrator's perspective: the server may have completed the statement even though the client never received the response.

Common causes:

- DDL is incompatible with existing data, e.g., altering a column to NOT NULL while NULL values exist.
- Adding a unique index when data contains duplicates.
- Running out of temporary space, tablespace, or disk.
- Metadata locks blocked by long-running transactions or open queries.
- Long-running DDL exceeding proxy/client timeouts or canceled by an operator.
- Storage engine, ALTER algorithm, or feature unsupported by the target version.
- Old application code still reading/writing while the schema is changing.
- A backfill step stopping mid-chunk or re-running repeatedly on retry.

Therefore, migrations must be designed as stateful, resumable workflows rather than assuming a SQL file always runs cleanly from start to finish.

### 3. Metadata locks and operational impact

MySQL uses metadata locks (MDL) to protect table and object metadata while queries or DDL access them. DDL typically needs to acquire compatible exclusive locks and may have to wait for active transactions holding metadata locks to finish.

An uncommitted long-running read transaction can force ALTER TABLE to wait. While DDL waits for a lock, new queries targeting the same table may also queue up behind it depending on lock order and type, causing sudden latency spikes in the application.

#### 3.1. Observing waiting locks

On versions with Performance Schema metadata lock instrumentation:

~~~sql
SELECT
  OBJECT_TYPE,
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'appdb'
ORDER BY OBJECT_NAME, LOCK_STATUS;
~~~

You can inspect associated threads and statements via `performance_schema.threads`, `events_statements_current`, or views in the `sys` schema if installed and enabled. Column and view names may vary by version and privileges.

Before running DDL, check for long transactions:

~~~sql
SELECT
  trx_id,
  trx_started,
  trx_state,
  trx_mysql_thread_id,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Do not kill a session simply because it has been running a long time. Identify the owner, statement, impact, and safe termination method before intervening.

#### 3.2. Using timeouts deliberately

`lock_wait_timeout` controls metadata lock wait duration; `innodb_lock_wait_timeout` primarily controls InnoDB row lock wait duration. These two variables are not interchangeable.

You can set a short timeout on the migration session so DDL fails fast if it cannot acquire a metadata lock:

~~~sql
SET SESSION lock_wait_timeout = 15;
ALTER TABLE appdb.orders
  ADD COLUMN source_channel VARCHAR(30) NULL;
~~~

If DDL times out, investigate the blocker and retry during an appropriate window. Do not increase timeouts indefinitely to mask a stuck transaction. For long-running DDL, monitor lock wait time, execution time, disk I/O, temporary space, and replication lag.

### 4. Choosing ALTER algorithms and lock levels

MySQL offers common DDL algorithms:

| Algorithm | General characteristics | Impact to evaluate |
|---|---|---|
| INSTANT | Modifies metadata for supported operations | Usually fast without full data rebuild; still has metadata lock requirements and specific limitations |
| INPLACE | Storage engine applies change without necessarily copying the entire table through a new table | May still rebuild or scan data depending on operation; lock level varies by operation |
| COPY | Creates a table copy, transfers data, then swaps | Can consume significant disk, I/O, and time; concurrent writes are more restricted |

Algorithm and lock availability depend on version, engine, table structure, column/index types, and the exact operation. `INPLACE` does not imply no rebuild; `LOCK=NONE` does not imply zero metadata locking at the start or end.

Once requirements are clear, you can explicitly instruct MySQL to use the desired algorithm and lock:

~~~sql
ALTER TABLE appdb.orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
~~~

If the operation does not support `INSTANT`, the statement fails with an error instead of silently choosing another algorithm. This is useful when you want to avoid unexpected fallbacks. Only use options supported by your target version.

For operations that support online DDL:

~~~sql
ALTER TABLE appdb.orders
  ADD INDEX idx_orders_created_at (created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

This example is valid only if the index type and table structure support that algorithm/lock combination. Otherwise, MySQL returns an error. Even when concurrent DML is permitted, DDL still needs metadata locks in certain phases and can generate significant I/O load.

Before deployment:

- Check version and engine documentation.
- Test on a clone matching production size, data distribution, and workload.
- Run EXPLAIN on queries after the change and measure execution plans.
- Estimate disk space, scan/rebuild duration, and replication lag.
- Set lock timeouts and a deployment schedule.
- Prepare abort, resume, or forward-fix plans based on actual state.

### 5. Designing migrations resumable after failure

A partial-failure-resilient migration must track how far it progressed and inspect database state before retrying. Do not rely solely on whether a script finished running from top to bottom.

#### 5.1. Migration journal

Create a migration tracking table in an administrative schema:

~~~sql
CREATE TABLE IF NOT EXISTS ops.schema_migrations (
  migration_id VARCHAR(150) NOT NULL,
  checksum CHAR(64) NOT NULL,
  state VARCHAR(20) NOT NULL,
  started_at TIMESTAMP(6) NULL,
  completed_at TIMESTAMP(6) NULL,
  last_key BIGINT NULL,
  rows_processed BIGINT NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  PRIMARY KEY (migration_id)
) ENGINE=InnoDB;
~~~

States may include PENDING, RUNNING, FAILED, VERIFYING, and APPLIED. Depending on your tooling, use the framework-managed journal table; do not introduce a competing tracking mechanism if the project already has a standard migration runner.

Field meanings:

- migration_id: unique, ordered identifier.
- checksum: detects whether migration contents changed after execution.
- state: current execution state.
- started_at, completed_at: start and completion timestamps.
- last_key, rows_processed: checkpoint for chunked backfills.
- error_message: last recorded error.

Record RUNNING before executing DDL, then run each step and verify metadata. Transition to APPLIED only when postconditions pass. Because DDL causes implicit commits, updating the journal is not in the same atomic transaction as the DDL; reconcile the journal against the actual schema upon restart.

#### 5.2. Preconditions and postconditions

Each step should define:

- **Precondition:** schema/data required before execution.
- **Action:** a single DDL operation or a clearly scoped DML chunk.
- **Postcondition:** evidence confirming the operation completed.
- **Recovery:** action to take if the postcondition fails or the outcome is ambiguous.

Example before adding a column:

~~~sql
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.columns
WHERE table_schema = 'appdb'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

If the column does not exist, the migration can add it. If it already exists, do not simply skip on name match: verify that type, nullability, default, collation, and semantics match what the migration expects. A column with the same name but a different definition is drift requiring investigation.

After DDL, re-read metadata or SHOW CREATE TABLE to confirm postconditions. If the client times out, reconnect and inspect the schema before deciding to re-run. Never assume a timeout means the server did not execute the command.

#### 5.3. Controlled idempotency

An idempotent step can be re-executed without producing an invalid state. However, `IF NOT EXISTS` does not prove an existing object has the right definition.

Example:

~~~sql
CREATE TABLE IF NOT EXISTS appdb.order_audit (
  audit_id BIGINT NOT NULL AUTO_INCREMENT,
  order_id BIGINT NOT NULL,
  changed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (audit_id),
  KEY idx_order_audit_order_id (order_id)
) ENGINE=InnoDB;
~~~

If the table already exists with different columns or indexes, the statement succeeds without error while the schema remains wrong. Thus, idempotency must include structural and data verification, not merely `IF NOT EXISTS`.

For backfill DML, use conditions safe for repeated execution, such as updating only rows that are still NULL. Whenever possible, store primary-key checkpoints and advance after each committed chunk.

### 6. Expand-contract: changes compatible with multiple application versions

Expand-contract reduces risk when schema and application cannot be deployed atomically together. Changes are divided into a backward-compatible expansion phase, application rollout, and then contraction/removal of legacy structures.

Suppose `orders.customer_name` needs to be replaced by `orders.customer_display_name`.

#### Phase 1 — Expand

Add the new column while keeping the old column:

~~~sql
ALTER TABLE appdb.orders
  ADD COLUMN customer_display_name VARCHAR(200) NULL;
~~~

Deploy application code capable of reading both columns and writing synchronously to the new column. If multiple application versions run concurrently, older versions must still function against the expanded schema.

#### Phase 2 — Backfill

Populate legacy rows in primary-key chunks:

~~~sql
UPDATE appdb.orders
SET customer_display_name = customer_name
WHERE order_id > 0
  AND order_id <= 10000
  AND customer_display_name IS NULL;
~~~

After each chunk, commit and record the checkpoint. Size batches according to load, lock duration, and replication lag; never run one massive UPDATE on a large table. The statement must be safe to re-run if the process stops after commit but before recording the checkpoint.

#### Phase 3 — Verify and switch

Reconcile remaining NULL rows, value mismatches, and business rules. Once the new column is fully populated, deploy code that reads the new column. Monitor errors and keep the old column for the defined rollback window.

#### Phase 4 — Contract

Only after every old application version is retired and no jobs depend on the legacy column, drop the column:

~~~sql
ALTER TABLE appdb.orders
  DROP COLUMN customer_name;
~~~

DROP COLUMN destroys schema information and can permanently lose legacy data. Confirm backups, consumers, reports, stored programs, and ad-hoc queries no longer depend on it before executing.

This pattern applies to renaming columns, changing data types, splitting tables, migrating relationships, and adding constraints. For incompatible changes, API versioning or a controlled transition window is required.

### 7. Fault-tolerant backfills and transaction limits

Backfills are DML, so they can be split into small transactions. Each chunk should have a stable key range, an idempotent condition, and a checkpoint.

Example using an ascending key:

~~~sql
START TRANSACTION;

UPDATE appdb.orders
SET normalized_status = UPPER(status)
WHERE order_id > 100000
  AND order_id <= 110000
  AND normalized_status IS NULL;

COMMIT;
~~~

After committing, update `last_key=110000` in the journal. If the process stops before updating the checkpoint, the chunk can re-run; `normalized_status IS NULL` prevents overwriting already-processed rows. If source data can change concurrently, define precedence rules between the application and the backfill.

Principles:

- Chunk by primary key or a stable indexed key.
- Cap row count and duration per transaction.
- Commit frequently to reduce undo/redo pressure and row lock hold times.
- Monitor replica lag, buffer pool, disk I/O, and query latency.
- Save checkpoints after chunk commits.
- Include ways to detect and handle rows skipped or modified during backfill.
- Apply rate limiting or pause if production load crosses thresholds.

If keys have gaps, do not assume `last_key + 1` always exists. Query for the next batch in key order, record the actual last key processed, and handle the end-of-table case cleanly.

### 8. Multi-step migrations and concurrency coordination

Two migration runners executing at the same time may both observe a "not yet present" state and both execute the DDL. This easily causes duplicate-object errors, lock contention, or inconsistent journal state.

Coordination options include:

- Allowing only one pipeline to run migrations against a schema.
- Using named locks like `GET_LOCK()` if runners connect to the same MySQL instance and follow the same locking protocol.
- Using deployment-system leases/locks when multiple environments or endpoints exist.
- Recording migration IDs and checksums to detect out-of-order runs or altered scripts.

Example using a named lock in a single session:

~~~sql
SELECT GET_LOCK('appdb_schema_migration', 10) AS lock_acquired;
-- Proceed only when the result is 1.

-- Run the migration and verify postconditions.

SELECT RELEASE_LOCK('appdb_schema_migration');
~~~

Named locks are bound to the session and released when the session ends. They do not automatically synchronize runners connected to different MySQL instances, nor do they replace DDL metadata locks. Always handle lock timeouts or dropped connections before applying changes.

### 9. Recovering when a migration fails partway

When a step fails, do not immediately re-run the whole file. Reconstruct the actual state of schema and data first.

Recovery workflow:

1. **Halt further execution.** Prevent pipelines from continuing application deployments or dependent migrations.
2. **Preserve evidence.** Record the MySQL error, migration ID, checksum, timestamp, server version, and executed output.
3. **Read the journal.** Check the last recorded step (RUNNING/FAILED/VERIFYING); do not treat the journal as the sole truth.
4. **Inspect the actual schema.** Use SHOW CREATE TABLE, INFORMATION_SCHEMA.COLUMNS, STATISTICS, TABLE_CONSTRAINTS, and relevant metadata.
5. **Reconcile data.** Check how far backfills progressed, remaining row counts, and business invariants.
6. **Classify state.** Determine whether DDL never ran, completed fully, partially completed per operation/engine behavior, or has an unknown outcome due to disconnect.
7. **Select recovery.** Resume from the missing step, forward-fix via a new migration, or restore if rollback is required and an appropriate plan exists.
8. **Verify after repair.** Re-run postconditions, verify application health, replication, and journal before reopening the pipeline.

#### 9.1. Prefer forward-fix once the schema has expanded

For additive migrations such as adding a nullable column or creating a new table, the safest path is usually to fix the root cause and continue from the current state. For example, if adding a column succeeded but creating an index failed due to disk space, keep the column, free space per runbook, assess load, and create the index after verifying it does not yet exist.

Do not drop a newly added column just to "revert to prior state" if the application or backfill has already started using it. Rolling back the schema can destroy newly written data in that column.

#### 9.2. When rollback or restore is necessary

DDL rollback is typically a new migration with inverse effects, not a transaction ROLLBACK. For instance, you can drop a newly added index if confident no application queries depend on it and dropping it will not cause unexpected performance issues. However, dropping a column that already received new data loses information.

Restoring a backup is a broad data-recovery measure that usually requires downtime or an alternative cutover plan. Before restoring, determine RPO/RTO, transactions written after the backup, and how to bring the system back to a consistent state. Never treat backup restore as a quick undo for an ALTER statement.

### 10. Example migration with journal and postcondition checks

Suppose you need to add `source_channel` to `orders`. A migration runner should execute this logic:

1. Compute the migration file checksum and look up `migration_id` in the journal.
2. If the migration is already APPLIED with a matching checksum, exit successfully.
3. If the same ID has a different checksum, halt and require investigation.
4. Mark RUNNING and record `started_at`.
5. Verify the column does not exist yet or already matches the expected definition.
6. Execute DDL if needed.
7. Re-read metadata and verify type/nullability/default.
8. Mark APPLIED only when postconditions pass; otherwise record FAILED with the error and preserve schema for investigation.

Postcondition query:

~~~sql
SELECT
  COLUMN_NAME,
  COLUMN_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT
FROM information_schema.columns
WHERE table_schema = 'appdb'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

The runner must compare results against the expected definition, not merely check that the query returned one row. If the column exists with the wrong type or nullability, flag drift and halt for an explicit corrective migration.

A subsequent migration can create the index:

~~~sql
SELECT
  INDEX_NAME,
  NON_UNIQUE,
  SEQ_IN_INDEX,
  COLUMN_NAME
FROM information_schema.statistics
WHERE table_schema = 'appdb'
  AND table_name = 'orders'
  AND index_name = 'idx_orders_source_channel';
~~~

If the index does not exist, check data and DDL feasibility before creating it. If it already exists, verify column ordering, uniqueness, and index type match expectations. Never treat a matching index name as proof the index is correct.

### 11. Pre-DDL deployment checklist

- [ ] Identified MySQL version, storage engine, and atomic/online DDL support for the operation.
- [ ] Inspected current schema, NULL/duplicate data, and related constraints.
- [ ] Accounted for DDL implicit commits and not relying on ROLLBACK to undo.
- [ ] Checked for long transactions and metadata lock blockers.
- [ ] Selected appropriate algorithm/lock and tested on production-like data.
- [ ] Estimated disk space, I/O, rebuild time, and replication lag.
- [ ] Configured migration ID, checksum, journal, and postconditions.
- [ ] Designed steps to be safely retryable or recoverable after timeout/disconnect.
- [ ] Confirmed old and new application versions remain compatible during transition.
- [ ] Prepared backups, forward-fix/restore plan, and accountable owner.
- [ ] Verified application, data, and replication after DDL completion.

### 12. Practice exercises

A migration needs to add `customer_display_name` to `orders`, backfill from `customer_name`, create an index, and deploy application code reading the new column. The script completes the first two steps but loses connectivity before creating the index. Upon inspection, the new column exists and contains data for part of the table.

1. Why can ROLLBACK not revert the schema and data to pre-migration state?
2. Which metadata query do you need to verify the column was created with the expected type, nullability, and default?
3. Design a primary-key checkpoint so the backfill can resume after process interruption.
4. How do you detect when an index already exists with the wrong definition?
5. Why can deploying code that reads the new column before backfill finishes cause errors?
6. Describe the expand, backfill, verify, switch, and contract phases.
7. If the client times out after sending ALTER TABLE, how do you determine the command's outcome before retrying?
8. When should you forward-fix, and when is restoring from backup necessary?

### 13. Operational principles

Treat every DDL statement as a commit boundary and every multi-step migration as a workflow that can stop mid-way. Atomic DDL protects certain single operations within supported scope; it does not provide a transaction wrapping an entire schema change. Design preconditions, actions, postconditions, journals, and checkpoints to know the actual state after failure. Use expand-contract so old and new applications operate safely together during transition. When an incident occurs, re-read metadata and data before retrying, forward-fixing, or restoring; never assume re-running a script from the start is safe.
