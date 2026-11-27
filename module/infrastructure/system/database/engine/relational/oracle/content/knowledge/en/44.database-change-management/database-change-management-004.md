# DDL Implicit Commit and Designing Partial-Failure-Tolerant Migrations in Oracle

In Oracle Database, DDL (Data Definition Language) statements such as `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME`, and many object definition operations exhibit implicit commit behavior. Oracle commits the current transaction before executing a valid DDL statement, and then commits the DDL itself if it succeeds. Consequently, DDL cannot be grouped with preceding DML statements into a single transaction to roll everything back with `ROLLBACK`.

This behavior directly impacts how schema changes are deployed. A migration consisting of five DDL statements and three backfill steps is not an atomic transaction. If the fourth step fails or the deployment process stops midway, the database may already be left in a partially applied state. Simply re-running the entire script can fail with "object already exists" errors, already-added constraints, partially backfilled data, or an application already using the new schema for some steps.

Safe migration design must assume that failures can occur after any step. Every step must have an observable state, be verifiable before re-running, maintain durable checkpoints, and have clear resume/recovery actions. Schema changes should generally follow the expand-contract model: expand the schema in a backward-compatible way first, transition application code and data in phases, and only remove old structures in a later release.

This lesson belongs to the **Change and Upgrade** topic of *Database Engine Relational Oracle*. It focuses on:

- Implicit commit rules before and after DDL.
- Why `ROLLBACK` does not undo DDL or DML committed prior to DDL.
- The difference between single-DDL atomicity and whole-migration atomicity.
- Designing multi-step migrations tolerant of partial failures.
- Expand-contract, backward compatibility, and schema/application deployment ordering.
- Migration history, checkpoints, idempotency, and safe retries.
- Batched backfills, validation, and cutover.
- DDL locks, online DDL, `DDL_LOCK_TIMEOUT`, and workload impact.
- Rollback vs. roll-forward/compensating migrations.
- A hands-on lab simulating a mid-migration failure and resuming from a checkpoint.

## 1. What Is DDL and Why Does Implicit Commit Matter?

DDL alters database structure or metadata. Common examples:

| Category | Examples |
| --- | --- |
| Object creation | `CREATE TABLE`, `CREATE INDEX`, `CREATE VIEW`, `CREATE SEQUENCE` |
| Object modification | `ALTER TABLE`, `ALTER INDEX`, `ALTER VIEW` |
| Drop/rename | `DROP TABLE`, `DROP INDEX`, `RENAME` |
| Structural data removal | `TRUNCATE TABLE` |
| Privilege management | `GRANT`, `REVOKE` |
| Other metadata | `COMMENT ON`, `CREATE OR REPLACE PROCEDURE/PACKAGE` |

These statements modify dictionary metadata and typically require database-wide coordination/locks. Oracle does not allow applications to wrap a sequence of DDL statements in a user-managed transaction and roll the entire sequence back like DML.

### Implicit Commit Rules

For valid DDL executed by Oracle, Oracle performs an implicit `COMMIT` before running the DDL and a `COMMIT` after the DDL succeeds. This has two consequences:

1. Uncommitted DML prior to the DDL is committed before the DDL begins.
2. If the DDL succeeds, the metadata change is committed; a subsequent `ROLLBACK` does not undo the DDL.

If the DDL fails after Oracle has already performed the pre-DDL commit, the preceding DML remains committed. No automatic rollback restores the database to the state prior to invoking the DDL.

### Example: ROLLBACK Does Not Undo DDL

~~~sql
CREATE TABLE migration_demo (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

INSERT INTO migration_demo(id, note)
VALUES (1, 'created before alter');

ALTER TABLE migration_demo ADD created_at DATE;

ROLLBACK;
~~~

After `ALTER TABLE`, the preceding DML transaction was implicitly committed. `ROLLBACK` does not drop the table, does not remove the `CREATED_AT` column, and does not undo the `INSERT` committed before the DDL.

You can verify:

~~~sql
SELECT * FROM migration_demo;

SELECT column_name, data_type
FROM user_tab_columns
WHERE table_name = 'MIGRATION_DEMO'
ORDER BY column_id;
~~~

### A Failed DDL Can Still Commit Preceding DML

Example:

~~~sql
INSERT INTO migration_demo(id, note)
VALUES (2, 'this row may be committed before DDL');

ALTER TABLE migration_demo ADD id NUMBER;
~~~

`ALTER TABLE` fails because column `ID` already exists. The DML before the valid DDL was committed before Oracle processed the `ALTER` statement. A subsequent `ROLLBACK` cannot restore the initial transaction state.

Key takeaway: never write scripts assuming that if a DDL statement raises an error, all preceding statements will automatically roll back.

## 2. Distinguishing Atomic DDL from Atomic Migrations

A single DDL statement is generally protected by Oracle's internal transaction mechanism so metadata is not left half-written if the operation fails. However, that does not confer atomicity on a multi-statement sequence of DDL/DML assembled by an operator.

Example migration:

1. Create a new table.
2. Add a column to an existing table.
3. Create an index.
4. Backfill data.
5. Add a constraint.
6. Deploy new code.
7. Drop the old column.

If step 5 fails, steps 1–4 may already be committed and present. If step 6 deploys successfully but step 7 fails, the application may be running new code while the old schema still exists. This is a partial migration state, not necessarily database corruption.

### Single DDL vs. Multi-Step Migration Sequence

| Attribute | Single DDL | Full Multi-Step Migration |
| --- | --- | --- |
| User transaction rollback | No | Cannot roll back the entire sequence |
| Can stop between steps | Not applicable | Yes |
| Can be partially applied | Failed DDL is usually handled internally | Yes, across already-committed steps |
| Needs checkpoint | Usually unnecessary for one statement | Needed |
| Needs idempotency/retry | May be needed if client loses response | Essential |
| Rollback | Usually compensating DDL or restore | Requires phase-by-phase planning |

### A Timeout Does Not Prove DDL Did Not Run

A client can lose connection or time out after the server executed the DDL but before the client received the response. Upon reconnecting, never assume the statement did not run and blindly re-execute it. Query the data dictionary to determine whether the object/column/index/constraint already exists before deciding how to proceed.

## 3. Classifying Changes Before Designing a Migration

Before writing scripts, classify each step:

| Change Type | Examples | Primary Risks |
| --- | --- | --- |
| Additive DDL | Add nullable column, create new table | Metadata locks, application compatibility |
| Index DDL | Create index, rebuild index | CPU/I/O, locks, space, index status |
| Constraint DDL | Add FK/UNIQUE/CHECK/NOT NULL | Validating historical data, locks, data errors |
| Destructive DDL | `DROP` column/table, `TRUNCATE` | Loss of ability to read/recover old structure |
| Data migration | `UPDATE`/`INSERT`/`MERGE` backfill | Undo/redo, locks, restartability |
| Application cutover | Switch code to read/write new column | Application version compatibility |
| Cleanup | Drop old column, old index, old table | Difficult rollback once old code is gone |

### Evaluating Each Step

For every step, answer:

- What are the preconditions before running?
- Which query confirms the success state?
- If the client disconnects after issuing the command, how do we know it took effect?
- Is re-running safe?
- How long might it hold locks or affect the workload?
- Is extra space needed for data, indexes, TEMP, UNDO, or REDO?
- Can it be rolled back with compensating DDL, or only rolled forward?
- Can old and new application versions operate concurrently during transition?

## 4. Partial-Failure-Tolerant Migrations: Core Principles

### Principle 1: Break Migrations into Small Steps

A massive migration containing dozens of changes is hard to investigate and recover. Break it into meaningful steps, each with preconditions, actions, postconditions, and a checkpoint.

### Principle 2: State Must Be Durable

Store the migration version, step name, status, start/end timestamps, and script checksum in a migration history table. This state tells operators how far execution progressed after a process crash.

### Principle 3: Inspect Actual Schema Before Retrying

Do not rely solely on runner state. DDL may have succeeded while the runner crashed before updating history. Retries must compare the data dictionary against the expected state.

### Principle 4: Idempotent or Explicit Preconditions

An idempotent step can be re-run without causing unintended extra changes. When idempotency is not possible, scripts must detect an already-applied state and stop with a clear message.

### Principle 5: Backward Compatibility During Transition

The new schema must let old code keep running until all application instances are upgraded. Never drop or rename an old column in the exact same release where new code is first deployed.

### Principle 6: Prefer Roll-Forward

Because committed DDL cannot be transactionally rolled back, many migrations are safer to fix via a follow-up forward migration. Structural rollback should only be executed when clear compensating DDL exists and data has not been lost or irreversibly transformed.

### Principle 7: Measure and Bound Impact

Test DDL duration, locks, redo/undo, index builds, validation scans, and workload impact. Choose a maintenance window or online operations supported by your version and edition.

## 5. Designing the Migration History Table

A history table records where a migration started, completed, or stopped. This table does not make DDL transactional; it provides durable checkpoints for runner recovery.

### Example Structure

~~~sql
CREATE TABLE schema_migrations (
    migration_id       VARCHAR2(100) PRIMARY KEY,
    checksum           VARCHAR2(128) NOT NULL,
    status             VARCHAR2(20) NOT NULL,
    current_step       VARCHAR2(100),
    started_at         TIMESTAMP WITH TIME ZONE,
    updated_at         TIMESTAMP WITH TIME ZONE,
    completed_at       TIMESTAMP WITH TIME ZONE,
    executed_by        VARCHAR2(128),
    error_code         NUMBER,
    error_message      VARCHAR2(2000),
    CONSTRAINT ck_schema_migrations_status
        CHECK (status IN (
            'STARTED',
            'RUNNING',
            'FAILED',
            'VALIDATED',
            'COMPLETED'
        ))
);
~~~

Names and columns can be adapted to your migration framework. The `CHECK` constraint enforces valid statuses; updating the history table is DML and can commit in its own transaction.

### Usage Rules

- One `migration_id` represents one logical migration/version.
- `checksum` detects if a script file was altered after running in another environment.
- `current_step` indicates the latest recorded step.
- `STARTED`/`RUNNING` distinguishes an in-progress migration from a completed one.
- `FAILED` captures `error_code`/`error_message` and the failing step for investigation.
- `COMPLETED` is written only after postconditions and validations pass.

### Never Edit Old Scripts After Running in an Environment

If script version V12 has already run in test/staging/production, do not edit V12 and re-run it with a new checksum. Create migration V13 for subsequent changes. This keeps deployment history consistent across environments.

### Checkpoints Do Not Replace Schema Inspection

If migration history says step `CREATE_INDEX` completed, yet the index was later dropped manually, the runner must not skip verification. Conversely, if the index was already created while history still shows `RUNNING` due to a client crash, the runner should detect the matching object definition and mark the step complete.

## 6. Preventing Concurrent Migration Execution

Two concurrent deployments can both see an object does not exist and run `CREATE`, or run two backfills over the same dataset. This causes race conditions, `ORA-00955`, lock contention, or unexpected data updates.

### Why SELECT FOR UPDATE Is Not Enough

An intuitive idea is to lock a migration lock row with `SELECT FOR UPDATE` while running scripts. However, DDL performs an implicit `COMMIT`, releasing the current transaction's row lock before the DDL executes. A second session can then acquire the row lock and start migrating while the first session is still running.

Never use a transaction row lock in the same session as a mutex across a sequence of DDL statements.

### Use Locks in the Deployment Orchestrator

When running migrations via CI/CD or a deployment service, prefer the orchestrator's concurrency locking:

- One migration mutex per database/schema.
- Only one job can run migrations at a time.
- The lock is held from preflight until migration completion or job cancellation.
- If a job dies, the orchestrator releases the lock via its lease/heartbeat mechanism.

### Using DBMS_LOCK When an In-Database Mutex Is Needed

`DBMS_LOCK` can create an application lock that is not released on commit when `REQUEST` uses `release_on_commit => FALSE`. The migration account needs appropriate execute privileges.

Conceptual example:

~~~sql
DECLARE
    l_handle VARCHAR2(128);
    l_result PLS_INTEGER;
BEGIN
    DBMS_LOCK.ALLOCATE_UNIQUE(
        lockname => 'APP_SCHEMA_MIGRATION',
        lockhandle => l_handle
    );

    l_result := DBMS_LOCK.REQUEST(
        lockhandle => l_handle,
        lockmode => DBMS_LOCK.X_MODE,
        timeout => 0,
        release_on_commit => FALSE
    );

    IF l_result NOT IN (0, 4) THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Another schema migration is running; DBMS_LOCK result=' || l_result
        );
    END IF;
END;
/
~~~

A result of `0` indicates the lock was acquired successfully; `4` can indicate the session already owns the lock. Verify return-code semantics against your Oracle version and usage.

Important note: `DBMS_LOCK.ALLOCATE_UNIQUE` can commit the current transaction. Call it before beginning business/migration work requiring a transaction, or allocate/register the handle beforehand during setup. After the migration, call `DBMS_LOCK.RELEASE` in a finally/cleanup path. If the process dies, Oracle releases the session lock when the session terminates.

Release example:

~~~sql
DECLARE
    l_result PLS_INTEGER;
BEGIN
    l_result := DBMS_LOCK.RELEASE(:lock_handle);
END;
/
~~~

This illustrative release snippet requires the actual handle returned by the acquire step. Do not run it standalone with an uninitialized bind variable.

### The Lock Must Span the Entire Lifecycle

Hold the lock across preflight, DDL, backfill, validation, and cutover. Locking only while writing migration history and releasing before DDL still leaves a race condition. With `DBMS_LOCK`, keep the same session throughout and do not use `release_on_commit => TRUE`.

## 7. Writing Idempotent DDL and Inspecting Object State

Idempotency means re-running a completed step produces no incorrect changes or unexpected errors. Oracle lacks a uniform `IF NOT EXISTS` clause for all DDL types across all releases, so many migrations use PL/SQL to query the dictionary before executing dynamic SQL.

### Create Table If Not Exists

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_tables
    WHERE table_name = 'APP_EVENT';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            CREATE TABLE app_event (
                event_id NUMBER PRIMARY KEY,
                event_type VARCHAR2(50) NOT NULL,
                created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
            )
        ]';
    ELSE
        -- Object already exists: verify structure before marking the step complete.
        SELECT COUNT(*)
        INTO l_count
        FROM user_tab_columns
        WHERE table_name = 'APP_EVENT'
          AND column_name IN ('EVENT_ID', 'EVENT_TYPE', 'CREATED_AT');

        IF l_count <> 3 THEN
            RAISE_APPLICATION_ERROR(
                -20002,
                'APP_EVENT exists with an unexpected structure'
            );
        END IF;
    END IF;
END;
/
~~~

Checking whether a table name exists is only the first step. If an object with the same name has a different owner, type, or definition, do not treat the migration as succeeded. Verify all required columns, data types, nullability, constraints, and defaults.

### Add Column If Not Exists

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_tab_columns
    WHERE table_name = 'CUSTOMERS'
      AND column_name = 'NORMALIZED_EMAIL';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE
            'ALTER TABLE customers ADD (normalized_email VARCHAR2(320))';
    ELSE
        SELECT COUNT(*)
        INTO l_count
        FROM user_tab_columns
        WHERE table_name = 'CUSTOMERS'
          AND column_name = 'NORMALIZED_EMAIL'
          AND data_type = 'VARCHAR2'
          AND data_length >= 320;

        IF l_count = 0 THEN
            RAISE_APPLICATION_ERROR(
                -20003,
                'NORMALIZED_EMAIL exists with an incompatible definition'
            );
        END IF;
    END IF;
END;
/
~~~

`USER_TAB_COLUMNS.DATA_LENGTH` reports bytes or character semantics depending on the column definition; for `VARCHAR2`, also check `CHAR_USED`/`CHAR_LENGTH` when needed. The example merely illustrates verifying data type and length.

### Add Constraint with Checks

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_constraints
    WHERE table_name = 'ORDERS'
      AND constraint_name = 'CK_ORDERS_AMOUNT';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            ALTER TABLE orders
            ADD CONSTRAINT ck_orders_amount
            CHECK (order_amount >= 0)
            ENABLE NOVALIDATE
        ]';
    ELSE
        SELECT COUNT(*)
        INTO l_count
        FROM user_constraints
        WHERE table_name = 'ORDERS'
          AND constraint_name = 'CK_ORDERS_AMOUNT'
          AND constraint_type = 'C';

        IF l_count = 0 THEN
            RAISE_APPLICATION_ERROR(
                -20004,
                'CK_ORDERS_AMOUNT exists but is not the expected constraint type'
            );
        END IF;
    END IF;
END;
/
~~~

An existing constraint name alone does not prove its condition is right. When the object already exists, inspect `SEARCH_CONDITION`, `STATUS`, `VALIDATED`, and involved columns before skipping creation.

### Create Index If Not Exists

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_indexes
    WHERE index_name = 'IX_ORDERS_CUSTOMER_CREATED';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            CREATE INDEX ix_orders_customer_created
            ON orders(customer_id, created_at)
        ]';
    ELSE
        SELECT COUNT(*)
        INTO l_count
        FROM user_ind_columns
        WHERE index_name = 'IX_ORDERS_CUSTOMER_CREATED';

        IF l_count <> 2 THEN
            RAISE_APPLICATION_ERROR(
                -20005,
                'Index exists with unexpected column definition'
            );
        END IF;
    END IF;
END;
/
~~~

In production, verify column order, `ASC`/`DESC`, uniqueness, partitioning, visibility, status, and tablespace; matching column counts alone is not enough to confirm index equivalence.

### Never Catch and Ignore All Exceptions

Dangerous pattern:

~~~sql
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE app_event (event_id NUMBER)';
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
/
~~~

This snippet hides syntax errors, insufficient quota, missing privileges, full tablespaces, and object conflicts. If you need to handle `ORA-00955`, catch only the expected error and verify the existing object is actually compatible; re-raise all other errors.

### Race Between Check and Create

A dictionary check followed by `CREATE` can still race if two runners execute concurrently. Idempotent checks do not replace a migration mutex. Use a single runner/lock while still guarding against out-of-band objects.

## 8. Expand-Contract Strategy

Expand-contract is an approach to deploying schema changes across multiple releases so old and new application versions can run concurrently during transition. Changes are divided into three phases:

1. **Expand:** add new structures while old code continues working.
2. **Migrate/cut over:** deploy compatible code, read/write new data, backfill, and shift traffic.
3. **Contract:** drop old structures only after all old code/consumers have stopped using them.

### Example: Renaming EMAIL to NORMALIZED_EMAIL

Do not rename or drop `EMAIL` right when deploying new code. An old application instance might still query `EMAIL` during a rolling deployment.

~~~text
Release A: schema has EMAIL
    |
    v
Release B: ADD NORMALIZED_EMAIL (nullable)
    |
    v
Release C: application dual-writes EMAIL + NORMALIZED_EMAIL
    |
    v
Backfill historical data in batches
    |
    v
Validate data and constraints
    |
    v
Release D: application reads NORMALIZED_EMAIL
    |
    v
Release E: stop writing EMAIL, observe no old consumers remain
    |
    v
Release F: DROP EMAIL in a separate migration
~~~

### Phase 1: Expand Schema

~~~sql
ALTER TABLE customers
ADD (normalized_email VARCHAR2(320));
~~~

A nullable new column allows old code to continue inserting without knowing about it. If defaults or `NOT NULL` are involved, evaluate their impact on existing data, DML, locks, and Oracle version before adding.

### Phase 2: Deploy Compatible Code

During rolling deployment, new code can dual-write:

~~~sql
INSERT INTO customers (
    customer_id, email, normalized_email
)
VALUES (
    :customer_id, :email, LOWER(:email)
);
~~~

For `UPDATE`, all write paths must maintain both columns. If multiple application versions, batch jobs, or integration clients write to the table, update all of them or use a controlled temporary synchronization mechanism. Triggers can aid transition but increase complexity and require evaluating recursion, ordering, and performance.

### Phase 3: Backfill Historical Data

Backfill updates only rows that do not yet have the new value:

~~~sql
UPDATE customers
SET normalized_email = LOWER(email)
WHERE normalized_email IS NULL
  AND email IS NOT NULL;

COMMIT;
~~~

For large tables, run in batches to limit undo/redo, lock duration, and per-transaction time. Never run an unmeasured full-table `UPDATE` during peak hours.

### Phase 4: Validate and Switch Reads

~~~sql
SELECT COUNT(*) AS missing_normalized_email
FROM customers
WHERE email IS NOT NULL
  AND normalized_email IS NULL;

SELECT COUNT(*) AS mismatched_email
FROM customers
WHERE email IS NOT NULL
  AND normalized_email <> LOWER(email);
~~~

Validation checks must handle `NULL`s according to business semantics. Once validation passes, deploy code reading the new column; keep the old column for an observation window so you can still roll back to the previous code.

### Phase 5: Contract

Only after confirming every application instance, report, ETL job, database link consumer, and batch job has stopped using `EMAIL` should you drop it:

~~~sql
ALTER TABLE customers DROP COLUMN email;
~~~

This is destructive DDL. Before running it, ensure appropriate backups/archives, confirm dependencies, and accept that old code is no longer compatible. Execute it in a separate migration/release so there is observation time after cutover.

## 9. Batched Backfills and Checkpoints

Data backfilling can take longer than DDL. Batching keeps each transaction short, limits the undo needed for any single rollback, and enables resuming after process failure.

### Batching by Primary Key

If the table has a monotonically increasing numeric key, chunk by key ranges:

~~~sql
UPDATE customers
SET normalized_email = LOWER(email)
WHERE customer_id >= :range_start
  AND customer_id < :range_end
  AND normalized_email IS NULL
  AND email IS NOT NULL;

COMMIT;
~~~

The runner records completed ranges in a migration progress table after DML commits. If the process dies, re-run only unfinished ranges; the `NORMALIZED_EMAIL IS NULL` condition prevents overwriting values already updated by new code.

### Batching by ROWID

For tables without a suitable key, you can select a batch of `ROWID`s:

~~~sql
UPDATE customers
SET normalized_email = LOWER(email)
WHERE ROWID IN (
    SELECT rid
    FROM (
        SELECT ROWID AS rid
        FROM customers
        WHERE normalized_email IS NULL
          AND email IS NOT NULL
          AND ROWNUM <= 1000
    )
);

COMMIT;
~~~

Repeat until `SQL%ROWCOUNT` equals `0`. Under concurrent workloads, adjust batch selection strategies to avoid multiple workers picking the same rows. `ROWID` applies only to current physical row locations; never persist `ROWID` as a durable key across table moves or redefinitions.

### Illustrative PL/SQL Loop

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    LOOP
        UPDATE customers
        SET normalized_email = LOWER(email)
        WHERE ROWID IN (
            SELECT rid
            FROM (
                SELECT ROWID AS rid
                FROM customers
                WHERE normalized_email IS NULL
                  AND email IS NOT NULL
                  AND ROWNUM <= 1000
            )
        );

        l_rows := SQL%ROWCOUNT;
        COMMIT;

        EXIT WHEN l_rows = 0;
    END LOOP;
END;
/
~~~

This snippet demonstrates a simple batched loop. Production code needs sleep/throttling, instrumentation, checkpoints, exception handling, and time/redo bounds. Every `COMMIT` persists the previous batch; an exception in a later batch does not roll back already-committed batches.

### Per-Batch Checkpoints

You can store:

- Migration ID and step.
- Batch key range or chunk ID.
- Rows updated count.
- Start/end timestamps.
- Status (`RUNNING`/`COMPLETED`/`FAILED`).
- Error code/message on failure.

Write the checkpoint after the batch data commits. If the checkpoint commits before the data commits, the runner could mark a batch complete even though the data is not persisted. Commit order must therefore be deliberate.

### Handling Concurrent Writes

During backfilling, the application may continue inserting/updating rows. Use predicates that only update rows lacking the new value, dual-writes, or another sync mechanism to avoid overwriting newer data. After backfilling, re-run validation to catch rows created or updated during the migration window.

### Monitoring Resources

Monitor elapsed time, rows/sec, redo size, undo usage, buffer gets, physical I/O, blocking sessions, archive destination/FRA, and application latency. Pause or throttle batches if workload metrics exceed agreed thresholds.

## 10. Adding Constraints Without Immediate Full Validation

On large tables, adding a constraint and validating all existing rows can be slow and lock-heavy. Oracle supports `ENABLE NOVALIDATE` and `ENABLE VALIDATE` states for many constraint types.

### ENABLE NOVALIDATE

Example adding a `CHECK` constraint:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_amount
CHECK (order_amount >= 0)
ENABLE NOVALIDATE;
~~~

`ENABLE NOVALIDATE` does not scan or certify all historical data as valid, yet enables the constraint to enforce new DML according to the constraint type's semantics. Thus, historical rows may still contain violations while new changes are checked.

### Finding Violating Old Rows Before Validation

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM orders
WHERE order_amount < 0;
~~~

If violations exist, fix the data in a separate checkpointed DML migration. Do not attempt `ENABLE VALIDATE` until the data satisfies the constraint.

### ENABLE VALIDATE

~~~sql
ALTER TABLE orders
ENABLE VALIDATE CONSTRAINT ck_orders_amount;
~~~

This verifies existing data obeys the constraint and transitions the constraint to the validated state. It may require data scans, resources, and locks; evaluate workload, table size, and release behavior.

### Inspecting Constraint State

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       rely
FROM user_constraints
WHERE table_name = 'ORDERS'
ORDER BY constraint_name;
~~~

`STATUS=ENABLED` does not mean `VALIDATED=VALIDATED`. With `NOVALIDATE`, a constraint can enforce new DML while historical data remains unvalidated.

### Foreign Keys

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id)
ENABLE NOVALIDATE;
~~~

Before validating, check for orphan rows:

~~~sql
SELECT COUNT(*) AS orphan_rows
FROM order_items i
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.order_id = i.order_id
);
~~~

An index on the child table's foreign key column is generally beneficial for DML and locking behavior, though it is not created automatically when adding a foreign key. Evaluate workload and create appropriate indexes.

### NOT NULL

To convert a nullable column to `NOT NULL`, first backfill and verify:

~~~sql
SELECT COUNT(*) AS null_rows
FROM customers
WHERE normalized_email IS NULL;
~~~

Once zero `NULL`s remain and all writers maintain the value, execute:

~~~sql
ALTER TABLE customers
MODIFY (normalized_email NOT NULL);
~~~

Changing nullability may require validation/locks and fails if any `NULL`s remain. Execute it in a separate migration after dual-write and validation have stabilized.

## 11. Creating Indexes and Online DDL

Creating indexes on large tables consumes CPU, I/O, temporary space, and redo. When supported by your version/edition/configuration, `ONLINE` lets DML continue during part of the build, though start/finish phases still require locks and extra resources.

### Standard Index Creation

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders(customer_id, created_at);
~~~

### ONLINE Index Creation

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders(customer_id, created_at)
ONLINE;
~~~

`ONLINE` does not mean zero locks, zero redo, or negligible impact. Oracle may require locks at the start and end phases, tracks concurrent DML changes, and consumes additional resources. Verify availability, datatype/partitioning limits, and licensing entitlements for your release.

### Inspecting Index Status

~~~sql
SELECT index_name,
       table_name,
       status,
       visibility,
       uniqueness,
       logging,
       degree
FROM user_indexes
WHERE table_name = 'ORDERS'
ORDER BY index_name;
~~~

For partitioned indexes, also check `USER_IND_PARTITIONS` and `USER_IND_SUBPARTITIONS`. An `INVALID`/`UNUSABLE` index may not be used by the optimizer as expected; identify the cause and rebuild per procedure.

### Invisible Indexes for Testing

In supported releases, you can create an `INVISIBLE` index to test impact without letting the optimizer use it by default:

~~~sql
CREATE INDEX ix_orders_customer_test
ON orders(customer_id)
INVISIBLE;
~~~

Test sessions can enable `optimizer_use_invisible_indexes` to evaluate execution plans. Invisible indexes are still maintained by DML and consume storage; they are not a way to avoid index maintenance overhead. Confirm release support.

### Rebuilding Indexes

~~~sql
ALTER INDEX ix_orders_customer_created REBUILD ONLINE;
~~~

`REBUILD` is DDL and performs an implicit commit. `ONLINE` has specific prerequisites; evaluate temporary storage, redo, locks, and DML impact. If a rebuild fails, check `USER_INDEXES`/partition status before retrying.

## 12. DDL Locks and Availability Impact

DDL requires dictionary/metadata locks to ensure object structure does not change between parse and execution. A DDL statement may wait behind a DML transaction holding a lock or fail if it cannot acquire the lock within the allowed time.

### DDL_LOCK_TIMEOUT

The `DDL_LOCK_TIMEOUT` parameter specifies how long a session waits for a DDL lock before returning an error when unavailable. It can be set per session:

~~~sql
ALTER SESSION SET ddl_lock_timeout = 60;
~~~

`60` is an illustrative 60-second timeout. Setting a timeout does not resolve blockers; it merely adjusts wait duration. Choose the timeout based on the maintenance window and acceptable deployment wait time.

### ORA-00054

`ORA-00054` generally indicates "resource busy" when DDL cannot acquire the required lock. Inspect sessions holding locks, transaction durations, and workload; avoid tight retry loops with excessive timeouts that prolong deployment queues.

### Inspecting Locks and Sessions

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       s.sql_id,
       s.event,
       s.seconds_in_wait,
       s.blocking_session
FROM v$session s
WHERE s.username IS NOT NULL
ORDER BY s.seconds_in_wait DESC;
~~~

~~~sql
SELECT lo.session_id AS sid,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
~~~

These views help investigate session/object locks; DDL locks and library cache locks may also require `V$LOCK`, `V$ACCESS`, or diagnostic views depending on the wait type.

### Online DDL Can Still Wait on Locks

Even `ONLINE` operations require metadata coordination. If another session holds a long transaction on the object, the DDL can block during the start or completion phase. Monitor session waits and set an appropriate `DDL_LOCK_TIMEOUT`.

### Avoid Running DDL Inside Application Transactions

Never execute `ALTER TABLE` or `CREATE INDEX` in the middle of an open business transaction. The DDL will commit that transaction beforehand, potentially stripping the application's ability to roll back unfinished business changes.

## 13. Migration Runners and Error Handling

A migration runner must handle SQL errors, process interruptions, connection loss, and cases where DDL executed on the server before the response reached the client.

### SQL*Plus/SQLcl Error Handling

A script can use:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

-- Migration steps...
~~~

`WHENEVER SQLERROR` makes the runner exit on SQL errors. `ROLLBACK` only undoes the currently uncommitted DML transaction; it does not undo implicitly committed DDL or DML committed prior to DDL.

### Every Step Needs Preconditions and Postconditions

Example step `ADD_COLUMN`:

- Precondition: table `CUSTOMERS` exists, `NORMALIZED_EMAIL` does not exist yet or already matches the intended definition.
- Action: `ALTER TABLE ADD COLUMN` if needed.
- Postcondition: `USER_TAB_COLUMNS` shows the column with the right datatype/nullability/default.
- Recovery: if the postcondition holds even though the runner timed out, mark the step complete; if an incompatible object exists, stop for manual intervention.

### FAILED Status Does Not Always Mean Rollback

If a migration fails after adding a column and completing a partial backfill, rolling everything back may be impossible or dangerous. Record `FAILED`, preserve state, identify completed steps, and decide whether to resume or run a compensating migration.

### Never Blindly Retry DDL

After a network or client timeout error:

1. Reconnect to the database.
2. Check migration history.
3. Inspect the data dictionary and object states.
4. Verify whether the DDL took effect.
5. If properly applied, record the checkpoint.
6. If not yet applied, re-run the idempotent step.
7. If the object exists with the wrong definition, halt and create a remediation migration.

### Error Logs

Log `SQLCODE`, `SQLERRM`, migration ID, step, session/module, timestamp, and necessary stack/trace details. Never log credentials, sensitive bind data, or full customer records in error messages.

## 14. Schema and Application Deployment Order

Rolling deployments allow multiple application versions to access the database simultaneously. The schema must stay compatible with every version running during the transition window.

### Compatibility Matrix

| Schema State | Old Application | New Application |
| --- | --- | --- |
| Before expand | Yes | May not run yet |
| After expand, before cutover | Yes | Yes, if new code supports old/new schema |
| During dual-write/backfill | Yes, if old column is maintained | Yes |
| After switching reads to new column | May still run if old column is maintained | Yes |
| After contract/dropping old column | No | Yes |

Therefore, run contract only after all old instances, batch jobs, reports, ETL pipelines, integrations, and consumers have been upgraded or decommissioned.

### Recommended Release Sequence

1. **Release expand schema:** add only backward-compatible structures.
2. **Release compatible application:** new code can read/write both old and new states.
3. **Backfill:** populate legacy rows in checkpointed batches.
4. **Validation:** verify completeness and constraints.
5. **Read cutover:** switch code to read from the new structure.
6. **Stop old writes:** confirm no legacy writers remain.
7. **Observation window:** monitor errors, data drift, performance, and dependencies.
8. **Contract release:** drop/rename/clean up old structures in a separate migration.

### Do Not Rename or Drop in the Initial Deployment

`ALTER TABLE RENAME COLUMN` or `DROP COLUMN` can immediately break old code, views, procedures, triggers, reports, and integrations. Use expand-contract to preserve a compatibility window.

### Changing Data Types

When an incompatible datatype change is needed, consider adding a new column with the target datatype, dual-writing, backfilling with conversion/error handling, validating, switching reads/writes, and dropping the old column later. Never `ALTER COLUMN` directly when there is risk of data loss, rounding, truncation, or conversion errors.

### Edition-Based Redefinition

For applications requiring low-downtime upgrades of PL/SQL and database objects, Oracle Edition-Based Redefinition (EBR) helps maintain multiple editions and switch sessions cleanly to the new edition. EBR does not make DDL transactional; it is a deployment technique for versioned objects requiring editioning views, cross-edition triggers, and editionable objects. Verify edition/feature support and suitability before adopting it.

## 15. Rollback, Roll-Forward, and Compensating Migrations

Because DDL auto-commits, a single `ROLLBACK` cannot restore the entire schema to its pre-migration state. Distinguish among three recovery strategies.

### Structural Rollback

Structural rollback runs inverse or compensating DDL:

- `ADD COLUMN` can be reversed with `DROP COLUMN` if the column holds no data worth keeping and has no dependencies.
- `CREATE INDEX` can be reversed with `DROP INDEX` if the application does not rely on it.
- `ADD CONSTRAINT` can be reversed with `DROP CONSTRAINT` if business rules allow.
- `DROP COLUMN`/`TABLE` generally cannot be rolled back without a backup or data copy.

Rollback DDL is also DDL and performs implicit commits. Every rollback step must have its own preconditions and postconditions.

### Roll-Forward

Roll-forward creates a new migration to move schema/data from the current state to the desired state. This is usually the safer option once some steps have already been applied and new data has been written.

For example, if a new column was added but the index build failed, fix the root cause and create the index in the next migration or resume the step; there is no need to drop the column just to return to square one.

### Compensating Migration

A compensating migration applies a business-level change to offset the effect of an already-committed step. For instance, if data was migrated to a new table with a buggy mapping, author a migration correcting the mapping from the source data or business rules—DDL `ROLLBACK` cannot undo it.

### When to Restore from Backup?

Restore or point-in-time recovery is a database-level measure when schema/data is severely corrupted and no safe forward fix exists. It risks losing transactions after the recovery point, affects the entire database, and requires a coordinated outage. Never restore an entire database to undo a small migration when a compensating migration can fix it.

### Deciding Between Rollback and Roll-Forward

| Scenario | Typically Appropriate Action |
| --- | --- |
| `ADD COLUMN` succeeded, `CREATE INDEX` failed | Check state, then retry index creation |
| Backfill partially completed | Resume using checkpoints/idempotent predicates |
| `NOVALIDATE` constraint created, validation failed | Fix violating data, then re-validate |
| New code has bugs, expand schema is compatible | Roll back application, keep expand schema |
| Reads switched to new column, data is wrong | Halt cutover, reconcile, and roll forward data fix |
| Old column already dropped and old data needed | Restore from backup/archive or source data; no simple rollback |
| Migration created object with wrong definition | Halt deployment, assess dependencies, run controlled remediation |

## 16. Example Multi-Step Migration with Checkpoints

The example below illustrates breaking a migration into durable steps. Adapt schema, table names, and privileges to your actual environment.

### Step 0: Record Migration Start

~~~sql
INSERT INTO schema_migrations (
    migration_id,
    checksum,
    status,
    current_step,
    started_at,
    updated_at,
    executed_by
)
VALUES (
    'V2026_015_ADD_NORMALIZED_EMAIL',
    'sha256:example-checksum',
    'STARTED',
    'INIT',
    SYSTIMESTAMP,
    SYSTIMESTAMP,
    SYS_CONTEXT('USERENV', 'SESSION_USER')
);

COMMIT;
~~~

If `migration_id` already exists, the runner must inspect `status`/`checksum` and determine how to resume; never insert duplicates or arbitrarily reset state.

### Step 1: Add Column

~~~sql
ALTER TABLE customers
ADD (normalized_email VARCHAR2(320));
~~~

Then verify:

~~~sql
SELECT column_name, data_type, data_length, nullable
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
  AND column_name = 'NORMALIZED_EMAIL';
~~~

Record checkpoint after postcondition passes:

~~~sql
UPDATE schema_migrations
SET status = 'RUNNING',
    current_step = 'COLUMN_ADDED',
    updated_at = SYSTIMESTAMP
WHERE migration_id = 'V2026_015_ADD_NORMALIZED_EMAIL';

COMMIT;
~~~

If the process dies after `ALTER TABLE` but before `UPDATE` history, the next run inspects the dictionary, sees the column matches the expected definition, and writes the checkpoint without re-running `ADD`.

### Step 2: Batched Backfill

Run batch updates with predicate `NORMALIZED_EMAIL IS NULL`. Commit data per batch; write the corresponding range checkpoint only after commit. If the process dies between commits, the batch can re-run safely without overwriting existing values due to the idempotent predicate.

### Step 3: Create Index

~~~sql
CREATE INDEX ix_customers_normalized_email
ON customers(normalized_email);
~~~

Verify index definition/status via `USER_INDEXES` and `USER_IND_COLUMNS`. If the runner loses connection after `CREATE`, inspect metadata before retrying.

### Step 4: Validate

~~~sql
SELECT COUNT(*) AS rows_missing_value
FROM customers
WHERE email IS NOT NULL
  AND normalized_email IS NULL;
~~~

Mark `VALIDATED` only when the query result and all business rules pass. On mismatch, keep `RUNNING`/`FAILED` with the step name—do not mark `COMPLETED`.

### Step 5: Complete

~~~sql
UPDATE schema_migrations
SET status = 'COMPLETED',
    current_step = 'VALIDATED',
    updated_at = SYSTIMESTAMP,
    completed_at = SYSTIMESTAMP,
    error_code = NULL,
    error_message = NULL
WHERE migration_id = 'V2026_015_ADD_NORMALIZED_EMAIL';

COMMIT;
~~~

The migration is only complete once schema, data, and application cutover within the release scope are confirmed.

## 17. Checking Dependencies Before Contract

Before dropping or renaming a column or table, search for dependencies both inside and outside the database.

### USER_DEPENDENCIES

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE referenced_name = 'CUSTOMERS'
ORDER BY type, name;
~~~

### USER_OBJECTS

~~~sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name IN ('CUSTOMERS', 'CUSTOMER_REPORT_V')
ORDER BY object_type, object_name;
~~~

### DBMS_METADATA

~~~sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'CUSTOMERS', USER)
FROM dual;
~~~

`DBMS_METADATA` helps archive current DDL for review or structural restoration if needed. Output may include tablespace/storage attributes and vary by release; verify execute privileges and metadata filters.

### External Dependencies

The data dictionary does not know every consumer. Also check:

- Source code and ORM mappings.
- Report/BI definitions.
- ETL jobs, schedulers, and batch scripts.
- Database links and remote consumers.
- Materialized views/replication.
- Dynamic SQL and runtime-generated SQL.
- Monitoring, auditing, and integration platforms.

Never proceed with contract solely because `USER_DEPENDENCIES` returns no rows.

## 18. DDL in PL/SQL and Dynamic SQL

Putting DDL inside an anonymous block or stored procedure does not remove implicit commits. Oracle generally requires dynamic SQL to execute DDL from PL/SQL:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'ALTER TABLE customers ADD (source_system VARCHAR2(30))';
END;
/
~~~

`ALTER TABLE` still performs an implicit commit per DDL rules. If the block ran DML before `EXECUTE IMMEDIATE`, that DML may have committed before the DDL. An exception handler calling `ROLLBACK` does not undo the DDL or the previously committed DML.

### Dangerous Example

~~~sql
BEGIN
    UPDATE accounts
    SET migration_flag = 'Y'
    WHERE migration_flag IS NULL;

    EXECUTE IMMEDIATE
        'ALTER TABLE accounts ADD (new_code VARCHAR2(20))';

    RAISE_APPLICATION_ERROR(-20010, 'simulate later failure');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

The `UPDATE` can be implicitly committed before `ALTER TABLE`. `ALTER TABLE` also commits upon success. The subsequent error cannot roll back those two committed changes. That is why DML migrations and DDL should be separated into explicit steps rather than assuming an exception handler wraps everything atomically.

### Stored Procedures and CREATE OR REPLACE

`CREATE OR REPLACE PROCEDURE`/`PACKAGE`/`VIEW` is DDL. It alters object definitions and can invalidate dependent objects/cursors requiring recompilation. When deploying PL/SQL:

- Record source version/checksum.
- Check `USER_OBJECTS.STATUS` after compilation.
- Inspect `USER_ERRORS`.
- Verify required grants/dependencies.
- Never assume a compile error automatically rolls back earlier DDL in the release.

~~~sql
SELECT name, type, line, position, text
FROM user_errors
ORDER BY name, sequence;
~~~

## 19. Pre-Migration Checklist

### Scope and Plan

- Identify migration ID, checksum, and target database/schema.
- Determine the overlap window where old and new application releases coexist.
- List DDL, DML, backfill, and cleanup steps in order.
- Define preconditions/postconditions for every step.
- Flag destructive steps requiring separate approval.
- Define resume points and remediation paths if any step fails.

### Database Readiness

- Verify database role/open mode and container/service.
- Verify free space for data, indexes, TEMP, UNDO, and archive/FRA.
- Check for invalid objects, blocking sessions, and long-running transactions.
- Verify object dependencies and schema privileges.
- Review statistics, partitioning, and data volumes.
- Confirm backup/recovery readiness for destructive changes.

### Application Readiness

- Does old code continue working after expand?
- Does new code work both before and after backfill?
- Do all writers dual-write or stay compatible?
- Have retries/idempotency been tested?
- Do connection pools/session states need resetting?
- Have reporting/ETL/integration consumers been inventoried?

### Execution Readiness

- Is the migration mutex active?
- Can the script resume after process/network failure?
- Does error handling halt cleanly on SQL errors?
- Are `DDL_LOCK_TIMEOUT` and maintenance windows appropriate?
- Are logs/checkpoints persisted durably?
- Do operators know how to inspect actual schema state?

## 20. Post-Migration Checklist

After the runner reports completion, verify the database directly instead of trusting exit codes alone.

### Schema

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name IN ('CUSTOMERS', 'SCHEMA_MIGRATIONS');

SELECT column_name, data_type, data_length, nullable
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
ORDER BY column_id;

SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'CUSTOMERS'
ORDER BY constraint_name;

SELECT index_name, status, visibility
FROM user_indexes
WHERE table_name = 'CUSTOMERS'
ORDER BY index_name;
~~~

### Data Validation

- Before/after row counts matching business criteria.
- Zero remaining unbackfilled rows.
- No unexpected duplicate keys.
- No orphan foreign keys.
- Nullability, range, and check conditions satisfied.
- Aggregate totals/checksums match by group.
- Data written by the application during backfill was not missed.

### Object Compilation and Runtime

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE status <> 'VALID'
ORDER BY object_type, object_name;

SELECT name, type, line, position, text
FROM user_errors
ORDER BY name, sequence;
~~~

Check application smoke tests, query plans, latency, error rates, blocking, redo/undo, invalid objects, and job schedules.

### Migration History

~~~sql
SELECT migration_id,
       checksum,
       status,
       current_step,
       started_at,
       updated_at,
       completed_at,
       error_code,
       error_message
FROM schema_migrations
ORDER BY started_at DESC;
~~~

Reconcile `COMPLETED` status against actual postconditions. If history and schema disagree, halt further rollouts and investigate.

## 21. Common Migration Errors

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `ORA-00955 name is already used by an existing object` | DDL already ran previously or an object with the same name exists | Inspect object type/definition; mark step complete if matching, else remediate. |
| `ORA-01430 column being added already exists` | `ADD COLUMN` already ran or column was created out-of-band | Inspect datatype/default/nullability and dependencies before resuming. |
| `ORA-02264 name already used by an existing constraint` | Constraint name already exists | Inspect `USER_CONSTRAINTS` and definition; do not blindly rename. |
| `ORA-02298 cannot validate constraint` | Historical rows violate the constraint | Find offending rows, fix via checkpointed DML migration, then re-validate. |
| `ORA-02291 parent key not found` | DML inserts child row without parent | Check mapping/load order and parent data. |
| `ORA-02292 child record found` | Deleting parent while child rows remain | Confirm cascade/business rules and process in order. |
| `ORA-00054 resource busy` | DDL could not acquire lock | Identify blocker, pick suitable window, tune `DDL_LOCK_TIMEOUT`. |
| `ORA-04021 timeout waiting for object lock` | Library cache/object lock is held | Identify session/DDL holding the object; avoid aggressive retry storms. |
| `ORA-01652 unable to extend temp segment` | Insufficient TEMP for sort/index/validation | Check TEMP capacity, index/validation plan, and batch size. |
| `ORA-01653 unable to extend table` | Insufficient tablespace/datafile space | Check free space, autoextend, and storage capacity. |
| `ORA-01555 snapshot too old` during backfill/query | UNDO retention/volume and transaction duration | Batch work, shorten query duration, review UNDO sizing/retention. |
| `ORA-01442 column already NOT NULL` | Re-running migration on column already in target state | Check metadata; mark step complete if accurate. |
| `ORA-01451 cannot modify to NULL` | Nullability change conflicts with current state/constraints | Inspect data, constraints, and column state. |
| `ORA-01031 insufficient privileges` | Migration account lacks DDL/object privileges | Grant exact privileges via admin workflow; avoid `SYSDBA` for apps. |
| `ORA-00942 table or view does not exist` | Wrong owner/current schema or missing dependency | Check schema qualification, synonyms, grants, and migration order. |
| `ORA-04063 object has errors` | View/package/procedure invalid after dependency change | Inspect `USER_ERRORS`, fix source, and compile in order. |
| Client timeout after DDL | Server may have executed DDL while response was lost | Check data dictionary before retrying. |
| History `RUNNING` while schema already changed | Process crashed between DDL and checkpoint | Verify postconditions and write checkpoint if object matches. |
| History `COMPLETED` while object is missing | Object modified/dropped out-of-band | Halt further deployments, investigate drift, and remediate. |

## 22. Hands-On Lab: Resumable Migration After Failure

This lab uses a learning schema. The goal is to simulate a multi-step migration, intentionally stop after DDL commits, and resume using state inspection. Never run this on a shared schema.

### Step 1: Create Table and Initial Data

~~~sql
CREATE TABLE lab_customer (
    customer_id NUMBER PRIMARY KEY,
    email VARCHAR2(320),
    created_at DATE DEFAULT SYSDATE NOT NULL
);

INSERT INTO lab_customer(customer_id, email)
SELECT level,
       'user' || level || '@example.test'
FROM dual
CONNECT BY level <= 10000;

COMMIT;
~~~

### Step 2: Create Migration History

~~~sql
CREATE TABLE lab_migration_history (
    migration_id VARCHAR2(100) PRIMARY KEY,
    status VARCHAR2(20) NOT NULL,
    current_step VARCHAR2(100),
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP
);

INSERT INTO lab_migration_history(
    migration_id, status, current_step
)
VALUES (
    'LAB_001_NORMALIZED_EMAIL', 'STARTED', 'INIT'
);

COMMIT;
~~~

### Step 3: Add New Column

~~~sql
ALTER TABLE lab_customer
ADD (normalized_email VARCHAR2(320));
~~~

Verify the column:

~~~sql
SELECT column_name, data_type, data_length, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_CUSTOMER'
  AND column_name = 'NORMALIZED_EMAIL';
~~~

### Step 4: Simulate Runner Crash Before Checkpoint

Do not update `LAB_MIGRATION_HISTORY`. Suppose the client lost connection right after `ALTER TABLE`, so the runner does not know the DDL succeeded.

Upon reconnecting, inspect:

~~~sql
SELECT COUNT(*)
FROM user_tab_columns
WHERE table_name = 'LAB_CUSTOMER'
  AND column_name = 'NORMALIZED_EMAIL';
~~~

Since the column exists with the expected definition, do not run `ADD COLUMN` again. Update the checkpoint:

~~~sql
UPDATE lab_migration_history
SET status = 'RUNNING',
    current_step = 'COLUMN_ADDED',
    updated_at = SYSTIMESTAMP
WHERE migration_id = 'LAB_001_NORMALIZED_EMAIL';

COMMIT;
~~~

### Step 5: Batched Backfill

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    LOOP
        UPDATE lab_customer
        SET normalized_email = LOWER(email)
        WHERE normalized_email IS NULL
          AND email IS NOT NULL
          AND ROWID IN (
              SELECT rid
              FROM (
                  SELECT ROWID AS rid
                  FROM lab_customer
                  WHERE normalized_email IS NULL
                    AND email IS NOT NULL
                    AND ROWNUM <= 1000
              )
          );

        l_rows := SQL%ROWCOUNT;
        COMMIT;
        EXIT WHEN l_rows = 0;
    END LOOP;
END;
/
~~~

If the process stops between batches, re-run the block. Rows that already have `NORMALIZED_EMAIL` will not be updated again.

### Step 6: Verify Data

~~~sql
SELECT COUNT(*) AS missing_rows
FROM lab_customer
WHERE email IS NOT NULL
  AND normalized_email IS NULL;

SELECT COUNT(*) AS mismatch_rows
FROM lab_customer
WHERE email IS NOT NULL
  AND normalized_email <> LOWER(email);
~~~

Both queries should return `0` for the lab data.

### Step 7: Idempotent Index Creation

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM user_indexes
    WHERE index_name = 'IX_LAB_CUSTOMER_NORMALIZED';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE
            'CREATE INDEX ix_lab_customer_normalized ON lab_customer(normalized_email)';
    END IF;
END;
/
~~~

Then query `USER_INDEXES` and `USER_IND_COLUMNS` to confirm the index targets the right table and column.

### Step 8: Mark Complete

~~~sql
UPDATE lab_migration_history
SET status = 'COMPLETED',
    current_step = 'VALIDATED',
    updated_at = SYSTIMESTAMP
WHERE migration_id = 'LAB_001_NORMALIZED_EMAIL';

COMMIT;
~~~

### Step 9: Clean Up Lab

~~~sql
DROP TABLE lab_migration_history PURGE;
DROP TABLE lab_customer PURGE;
~~~

Run only after saving results and confirming these are lab objects.

## 23. Self-Check Questions

1. **What is DDL implicit commit?** Oracle commits the current transaction before valid DDL and commits the DDL upon success.
2. **Does `ROLLBACK` undo `ALTER TABLE`?** No.
3. **If DDL fails, could preceding DML have committed?** Yes, due to the implicit commit before DDL execution.
4. **Does atomic DDL mean atomic migration?** No; a sequence of DDL/DML steps can fail between already-committed steps.
5. **What is an idempotent migration?** Re-running it causes no erroneous changes and recognizes already-applied states.
6. **Why inspect the data dictionary after a timeout?** DDL may have succeeded on the server even if the client never received the response.
7. **What is migration history used for?** Recording versions, checksums, steps, and statuses for resuming and auditing.
8. **Why are checksums important?** They detect when an already-applied script was modified across environments.
9. **What are the main phases of expand-contract?** Expand, migrate/cutover, and contract.
10. **Why not drop the old column immediately when deploying new code?** Old application instances or other consumers may still depend on it.
11. **What are the benefits of batched backfilling?** It bounds undo/redo, limits lock duration, and enables resumability.
12. **When should a batch checkpoint be written?** After the batch data has been durably committed.
13. **Why can't `SELECT FOR UPDATE` hold a migration lock across DDL?** Implicit commits release transaction row locks.
14. **How does `DBMS_LOCK` `release_on_commit=FALSE` help?** It retains the application lock across implicit commits within the same session.
15. **What is the caveat with `DBMS_LOCK.ALLOCATE_UNIQUE`?** It can commit the current transaction, so call it before work requiring transactionality.
16. **What does `ENABLE NOVALIDATE` mean?** Enforces the constraint on new DML without validating all historical data yet.
17. **What does `ENABLE VALIDATE` do?** Verifies all existing data obeys the constraint.
18. **Is `ONLINE` DDL completely lock-free?** No; metadata lock phases and extra resource usage still occur.
19. **What does `DDL_LOCK_TIMEOUT` control?** How long a session waits for a DDL lock.
20. **If migration history shows `FAILED` after adding a column succeeded, what do you do?** Inspect the column definition, write the checkpoint if valid, and continue from the next step.
21. **What is roll-forward?** Running a new migration to move from the current state to the desired state.
22. **When is a compensating migration needed?** When a change already committed and a business-level offset is needed to fix its impact.
23. **Can `ROLLBACK` undo `DROP TABLE`?** No; backup/recovery or a data copy is required.
24. **Why inventory dependencies before contract?** External consumers may not appear in database dictionary dependencies.
25. **What must be checked after a migration?** Schema, data, constraints, indexes, invalid objects, application workload, and migration history.

Oracle's implicit commit behavior prevents DDL from being bundled into a single migration transaction that can roll back completely. Therefore, migrations must be designed to tolerate failures after any step: split into small steps, record history/checkpoints, use a migration mutex that survives commits, inspect the data dictionary before retrying, backfill idempotently in batches, and maintain backward compatibility with expand-contract. Online DDL reduces some disruption but still requires evaluating locks and resources. When failures occur, determine the true schema state, then resume, roll forward, or run a compensating migration; reserve restore solely for database-level recovery. Migration completion must be confirmed by schema, data, application behavior, and checkpoints—not merely by the runner's exit code.
