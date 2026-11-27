# Online DDL, DBMS_REDEFINITION, and Lock/Feature Limitations in Oracle Database

Altering table structures in an active production database is challenging because DDL can wait on transactions, acquire metadata locks, or disrupt DML for a window of time. On large tables, seemingly simple operations such as adding columns, changing data types, moving segments, or creating indexes can take long and directly impact workloads.

Oracle provides several ways to reduce downtime:

- **Online DDL:** using the `ONLINE` keyword for Oracle-supported DDL operations, such as creating/rebuilding certain index types or moving certain tables.
- **DBMS_REDEFINITION:** building an interim table with the target structure, syncing changes from the original table, and switching metadata at the final step.
- **DDL_LOCK_TIMEOUT:** controlling how long a DDL statement waits for required locks before failing.
- **Phased rollout design:** adding compatible structures, deploying application changes, backfilling data, switching reads/writes, and cleaning up old structures.

The word "online" does not mean "lock-free" or "never blocks DML." Many operations still need brief metadata locks at the start or end, and carry restrictions by object type, data type, edition, Release Update, and transaction state. DBAs must verify exact operation support, measure execution times, and prepare a fallback path.

This lesson uses Oracle Database 19c as its baseline. It explains locking mechanisms, forms of Online DDL, the `DBMS_REDEFINITION` workflow, feature limitations, monitoring blocking sessions, and planning schema changes with minimal downtime.

## 1. Why Can DDL on Large Tables Cause Disruption?

### 1.1. DDL and DML Have Different Goals

DML modifies row data: `INSERT`, `UPDATE`, `DELETE`, `MERGE`. Oracle uses row locks and table-level DML locks to maintain consistency.

DDL modifies metadata or object structure: `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME`. To modify metadata safely, Oracle requires different lock types, including DDL locks and library cache locks/pins depending on the operation.

A DDL statement may:
- Wait for active transactions touching the object to finish.
- Wait on metadata locks.
- Scan or rewrite a segment.
- Update indexes, constraints, or dependent objects.
- Hold locks long enough to block other sessions.
- Succeed quickly yet trigger invalidations/reparses across subsequent workloads.

### 1.2. DDL Performs Implicit Commits

Many DDL statements perform an implicit commit before and after the operation. Therefore:

~~~sql
UPDATE app.orders
SET    status = 'READY'
WHERE  order_id = 1001;

ALTER TABLE app.orders ADD source_code VARCHAR2(20);

ROLLBACK;
~~~

`ROLLBACK` does not undo the DDL and cannot revert the DML implicitly committed before the DDL. Never bundle DDL and DML into a single transaction expecting to roll back the whole migration.

Each migration step must be designed to be independently resumable, verifiable, or compensatable.

### 1.3. "Online" Does Not Mean "Zero Downtime"

An Online DDL operation allows DML to proceed during most of its execution. Still, it may require:
- Brief locks at start or completion.
- Waiting for older transactions to complete.
- Synchronizing indexes/metadata.
- Extra space to build new segments.
- Substantial CPU and I/O.
- Special conditions for partitions, LOBs, index types, or constraints.

Applications may see elevated latency, lock-waiting sessions, or brief failures during the metadata switchover window.

### 1.4. Defining Acceptable Disruption

Before picking a technique, answer:

1. Must DML continue throughout the change?
2. Can writes be paused for a few seconds during the final step?
3. What is the table's row count, segment size, and DML rate?
4. Is there a stable primary key?
5. Are there triggers, foreign keys, materialized view logs, LOBs, or partitions?
6. Is the application compatible with both old and new schemas concurrently?
7. Is there enough tablespace/FRA capacity for interim segments and redo/undo?
8. Can we roll back or forward-fix if the final step fails?

A change tolerating a few seconds of downtime differs fundamentally in design from one requiring uninterrupted DML throughout.

## 2. Lock Types Related to DDL

### 2.1. Row Locks and TX Enqueues

DML typically locks rows modified by a transaction. A TX enqueue represents a transaction lock. An uncommitted transaction can hold row locks indefinitely and force other transactions to wait.

Example Session A:

~~~sql
UPDATE app.orders
SET    status = 'PROCESSING'
WHERE  order_id = 1001;

-- Not yet COMMITted or ROLLBACKed.
~~~

Session B updating the same row waits on the row lock. This is DML blocking, not an Online DDL bug.

### 2.2. TM Table Locks

DML also acquires table-level locks (TM enqueues) to coordinate object operations and protect integrity. Lock mode depends on the statement type and constraints.

A TM lock does not mean the whole table is exclusively locked. Multiple DML statements can hold row-exclusive table locks concurrently while updating different rows.

### 2.3. DDL Locks

DDL locks protect object definitions while changes execute. A DDL operation needs a lock mode compatible with the operation; if another session holds an incompatible lock, the DDL waits.

Operations using the `ONLINE` keyword still require metadata locks at certain points. Thus, long-running transactions on the table can block DDL startup or completion.

### 2.4. Library Cache Locks/Pins

Oracle caches metadata and cursors in the shared pool/library cache. DDL modifying an object may require invalidation or locks/pins on object metadata. Sessions actively parsing or using the object can delay metadata changes.

When investigating, do not look solely at TX/TM locks. Check wait events, blocking sessions, objects, and actual lock types.

### 2.5. Checking DDL Lock Timeout

`DDL_LOCK_TIMEOUT` specifies how many seconds DDL waits for required DML locks before failing. The default is usually `0`, meaning no waiting if the lock is unavailable immediately.

~~~sql
SHOW PARAMETER ddl_lock_timeout;
~~~

Set the timeout in a migration session:

~~~sql
ALTER SESSION SET DDL_LOCK_TIMEOUT = 60;
~~~

If the lock is not released within the wait window, DDL fails with an error such as `ORA-00054`. The timeout only controls wait duration; it does not force blocking transactions to commit and does not make DDL any safer.

### 2.6. WAIT vs. DDL_LOCK_TIMEOUT

`DDL_LOCK_TIMEOUT` is a session parameter applying to supported DDL. It differs from the `WAIT`/`NOWAIT` clause of explicit locking commands:

~~~sql
LOCK TABLE app.orders IN EXCLUSIVE MODE WAIT 10;
~~~

Do not use `LOCK TABLE` as a substitute for online DDL. That command blocks workloads and is appropriate only when a runbook explicitly calls for locking the table.

## 3. Inspecting Sessions Holding or Waiting on Locks

### 3.1. Viewing Locked Objects

~~~sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.os_user_name,
       lo.locked_mode,
       obj.owner,
       obj.object_name,
       obj.object_type
FROM   v$locked_object lo
JOIN   dba_objects obj
       ON obj.object_id = lo.object_id
ORDER  BY obj.owner, obj.object_name, lo.session_id;
~~~

`LOCKED_MODE` is a numeric lock mode code; consult Oracle Database Reference for meanings. These views require appropriate privileges; in restricted environments, a DBA can run queries on behalf of application users.

### 3.2. Finding Blocking Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       sql_id,
       module,
       program
FROM   v$session
WHERE  blocking_session IS NOT NULL
   OR  event LIKE '%enq:%'
ORDER  BY seconds_in_wait DESC;
~~~

`BLOCKING_SESSION` identifies the session blocking another when Oracle detects the blocker. In RAC, query `GV$SESSION` and include `INST_ID` to distinguish instances.

### 3.3. Viewing Locks by Session

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM   v$lock l
JOIN   v$session s
       ON s.sid = l.sid
WHERE  l.request > 0
   OR  l.block = 1
ORDER  BY l.block DESC, l.request DESC;
~~~

`LMODE` and `REQUEST` show held and requested modes. `ID1`/`ID2` semantics depend on the enqueue type; do not interpret them as object IDs for all lock types.

### 3.4. Viewing DDL Locks

~~~sql
SELECT session_id,
       owner,
       name,
       type,
       mode_held,
       mode_requested
FROM   dba_ddl_locks
ORDER  BY owner, name, session_id;
~~~

`DBA_DDL_LOCKS` displays DDL locks by object and session. Join or correlate with `V$SESSION` to find SQL, module, and wait time.

### 3.5. Identifying Long-Running Transactions

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.sql_id,
       s.event,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM   v$transaction t
JOIN   v$session s
       ON s.taddr = t.addr
ORDER  BY t.start_time;
~~~

Long-lived transactions hold locks and accumulate large undo volumes. Never kill a session reflexively upon spotting a long transaction; identify the owner, business impact, rollback cost, and resolution plan.

### 3.6. Never Handle Blockers Impulsively

Before requesting a commit/rollback or killing a session:
- Identify the application/job owning the session.
- Identify what the transaction is doing.
- Estimate rollback duration and undo volume.
- Check whether the session is running a critical batch job.
- Notify the owner per procedure.
- Kill sessions only with approval and full understanding of impact.

DDL waiting on a lock may simply indicate legitimate active business transactions; forcing lock release can cause worse damage than postponing the DDL.

## 4. Online DDL: Principles and Operation Categories

### 4.1. How It Works at a High Level

For an `ONLINE`-capable operation, Oracle performs most of the work while DML continues. Depending on the operation, Oracle builds or maintains interim structures, logs concurrent changes, and synchronizes before finishing.

Not every `ALTER TABLE ... ONLINE` syntax is valid. The `ONLINE` keyword is only supported in documented syntax positions.

### 4.2. Creating Indexes Online

~~~sql
CREATE INDEX app.ix_orders_status
ON app.orders(status)
ONLINE;
~~~

During the build, applications can continue supported DML. Index creation still consumes CPU, I/O, and TEMP, and may require brief locks during state transitions.

Verify:
- Whether the index type supports `ONLINE`.
- Whether the table has LOBs, partitions, or special attributes.
- Whether the index tablespace has sufficient free space.
- Whether high DML rates could prevent build completion.
- Edition and licensing prerequisites for the feature.

### 4.3. Rebuilding Indexes Online

~~~sql
ALTER INDEX app.ix_orders_status
REBUILD ONLINE;
~~~

Online rebuilds recreate certain index types while letting DML continue. Not every index type is supported; domain indexes, bitmaps, and specialized structures carry restrictions.

Rebuilding into another tablespace:

~~~sql
ALTER INDEX app.ix_orders_status
REBUILD TABLESPACE index_new ONLINE;
~~~

Verify syntax and clause order against the SQL Language Reference for your exact release. Measure duration, new segment size, and I/O impact before running on large tables.

### 4.4. Moving Tables Online

Certain heap tables can be moved online:

~~~sql
ALTER TABLE app.orders
MOVE TABLESPACE data_new
ONLINE;
~~~

Purposes include migrating tablespaces, reorganizing segments, or changing storage attributes. `ONLINE` allows DML during most of a supported move, but does not eliminate metadata locks.

Verify:
- Supported table types and attributes.
- Whether LOB segments must be moved separately.
- Whether indexes stay maintained or require rebuilding.
- Partition/subpartition syntax differences.
- Sufficient space for new segments and temporary space.
- Dependent objects and statistics post-operation.

### 4.5. Adding Columns

~~~sql
ALTER TABLE app.orders
ADD source_system VARCHAR2(30);
~~~

Adding a nullable column without a default is typically a fast metadata operation, yet still requires a DDL lock. Adding a column with a default may leverage metadata-only/fast-add optimizations in Oracle-supported cases.

Never assume all default expressions carry identical cost. Constant defaults, expression defaults, `NOT NULL`, data types, and release versions change how Oracle executes the operation. Test against production-equivalent data and versions.

### 4.6. Phased Constraint Addition

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT ck_orders_amount
CHECK (amount >= 0)
ENABLE NOVALIDATE;
~~~

`ENABLE NOVALIDATE` does not scan and validate all legacy rows the way `ENABLE VALIDATE` does. The constraint is enabled to enforce new DML per constraint semantics; legacy rows may still contain violations.

After cleaning legacy data, validate:

~~~sql
ALTER TABLE app.orders
ENABLE VALIDATE CONSTRAINT ck_orders_amount;
~~~

Validation can scan large data volumes and carry distinct locking/resource needs. Check constraint type behavior, edition/release, and workload before scheduling.

### 4.7. Changing Data Types or Complex Structures

Changes such as altering column types on large tables, changing nullability, changing partitioning, adding computed columns, or type conversions may require scans/rewrites and have online limitations.

If no `ONLINE` syntax exists, or concurrency requirements are not met, evaluate `DBMS_REDEFINITION`. Never slap `ONLINE` onto an unsupported statement assuming Oracle automatically runs it online.

### 4.8. SET UNUSED and DROP UNUSED COLUMNS

You can mark a column unused:

~~~sql
ALTER TABLE app.orders
SET UNUSED (legacy_code);
~~~

This is generally a faster metadata change than physically dropping the column immediately. The column disappears from normal queries, though space is not reclaimed right away.

Reclaim space physically afterward:

~~~sql
ALTER TABLE app.orders
DROP UNUSED COLUMNS;
~~~

`DROP UNUSED COLUMNS` may rewrite blocks and consume substantial resources. It supports batch/checkpoint options in supported cases; consult release-specific syntax and estimate runtime.

## 5. Limitations to Understand Before Using ONLINE

### 5.1. Operation Limitations

The `ONLINE` keyword does not apply uniformly across all DDL. Each operation has its own list of supported objects, types, and options.

For example:
- `CREATE INDEX ONLINE` supports specific index types and conditions.
- `ALTER INDEX REBUILD ONLINE` has restrictions by index type.
- `ALTER TABLE MOVE ONLINE` has restrictions by table type and attributes.
- Constraint changes follow distinct `ENABLE`/`DISABLE`/`VALIDATE` semantics.
- Certain column changes force table rewrites.
- Partition maintenance has operation-specific syntax and limits.

Consult the 19c SQL Language Reference for the exact statement you are using; do not extrapolate from similar statements.

### 5.2. Object Limitations

Inspect carefully if the table contains:
- `LONG` or legacy data types.
- LOBs/SecureFiles.
- IOTs or clustered tables.
- Nested tables/object types.
- Virtual columns or hidden columns.
- Partitions/subpartitions.
- Materialized view logs.
- Complex triggers and foreign keys.
- Domain indexes or bitmap indexes.
- Replication/CDC dependencies.
- VPD/RLS policies or audit policies.

This list highlights areas requiring verification, not an exhaustive ban list. Exact support depends on the operation and release.

### 5.3. Edition and Licensing Limitations

Certain online capabilities and online table redefinition depend on the Oracle Database edition or licensed options. Never infer licensing entitlement simply because syntax runs or a package exists.

Before deploying:
- Check the Oracle Database edition.
- Check the 19c Licensing Information User Manual and your offering.
- Confirm entitlement for Online Index/Online Table Redefinition features.
- Verify BYOL/license-included contracts in cloud environments.
- Document permitted feature scope.

Never substitute `V$OPTION` or a test run for proper licensing verification.

### 5.4. Resource Limitations

Online operations typically require extra space because old and new structures coexist temporarily.

Estimate space for:
- New table/index segments.
- Temporary segments.
- TEMP for sorts/builds.
- UNDO for concurrent DML.
- REDO and archived logs.
- FRA/backup capacity.
- CPU and I/O headroom.

If storage fills mid-operation, DDL can fail or disrupt other workloads.

### 5.5. Impact on the Optimizer and Applications

After DDL:
- Cursors can be invalidated and reparsed.
- Statistics may need gathering or inspection.
- New indexes can change execution plans.
- New columns may not be handled by older application versions.
- New constraints can break previously succeeding DML.
- Triggers/dependent objects may need recompilation or inspection.

"Online" addresses operational continuity during the change, not application compatibility with the new schema.

## 6. What Is DBMS_REDEFINITION?

### 6.1. Purpose

`DBMS_REDEFINITION` lets you restructure a large table while the original table continues serving DML throughout most of the process.

Core workflow:
1. Create an **interim table** with the target structure.
2. Verify the original table is eligible for redefinition.
3. Start redefinition so Oracle copies data and tracks concurrent changes.
4. Copy required dependent objects.
5. Synchronize changes accumulated after the initial copy.
6. Complete via a metadata swap requiring a brief lock.
7. Verify objects and clean up the old/interim table per procedure.

~~~text
Original table ORDERS
      |
      | START_REDEF_TABLE
      v
Copy data + capture concurrent DML changes
      |
      +-----------------------------+
      | DML continues on original   |
      +-----------------------------+
      |
      v
Interim table ORDERS_INT
      |
      | COPY_TABLE_DEPENDENTS
      | SYNC_INTERIM_TABLE
      v
FINISH_REDEF_TABLE
      |
      | metadata lock during switch
      v
New structure active under original table name
~~~

### 6.2. When Is It Appropriate?

`DBMS_REDEFINITION` fits when you need to:
- Reorder or restructure columns.
- Change data types within supported mappings.
- Move a table to a new tablespace.
- Change table organization or partitioning.
- Create a new structure and migrate data from the old table.
- Reduce DML blocking time compared to a long offline operation.

It is not a universal fix for every schema change. Verify eligibility, data types, dependencies, and resources upfront.

### 6.3. Cost of Redefinition

During execution, the following may coexist:
- Original table segment.
- Interim table segment.
- New indexes/LOBs/partitions.
- Redo/undo from copying and concurrent DML.
- Metadata/dependent objects being copied.

Therefore, redefinition demands substantial extra storage and I/O. A large table lacking free space for interim structures may be unsuitable despite strict downtime requirements.

## 7. Preparing Before Redefinition

### 7.1. Choosing CONS_USE_PK or CONS_USE_ROWID

`DBMS_REDEFINITION` supports two primary methods:

- `DBMS_REDEFINITION.CONS_USE_PK`: uses a primary key or qualifying unique key to identify rows.
- `DBMS_REDEFINITION.CONS_USE_ROWID`: uses `ROWID` when the table lacks a suitable key; Oracle uses rowid-based redefinition and may add an internal tracking column during the process.

Prefer a stable primary key when the table has one. The rowid method carries specific limits and requirements; check the package reference and `CAN_REDEF_TABLE` before using it.

### 7.2. Verifying Table Eligibility

Example:

~~~sql
BEGIN
    DBMS_REDEFINITION.CAN_REDEF_TABLE(
        uname        => 'APP',
        tname        => 'ORDERS',
        options_flag => DBMS_REDEFINITION.CONS_USE_PK
    );
END;
/
~~~

This procedure checks whether the table supports the chosen method. If ineligible, it raises an error describing why. Never ignore eligibility errors and guess your way into creating an interim table.

You can check with `CONS_USE_ROWID` if design and package support allow for that object.

### 7.3. Inspecting Current Structure

~~~sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM   all_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
~~~

Inspect constraints:

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated
FROM   all_constraints
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY constraint_type, constraint_name;
~~~

Inspect dependent objects: indexes, triggers, grants, constraints, materialized view logs, policies, synonyms, and dependent applications.

### 7.4. Creating the Interim Table

Suppose we want to add `SOURCE_SYSTEM` and rename `CREATED_AT` to `ORDER_CREATED_AT`:

~~~sql
CREATE TABLE app.orders_int (
    order_id          NUMBER        NOT NULL,
    customer_id       NUMBER        NOT NULL,
    order_created_at  TIMESTAMP(6),
    status            VARCHAR2(30),
    source_system     VARCHAR2(30),
    CONSTRAINT pk_orders_int PRIMARY KEY (order_id)
)
TABLESPACE data_new;
~~~

The interim table must have the target layout compatible with column mapping. Avoid creating duplicate indexes/constraints before understanding which objects `COPY_TABLE_DEPENDENTS` will copy.

Creating the table is DDL with implicit commit. Use a test schema and verify tablespaces/privileges before running in production.

### 7.5. Execution Privileges

The account running redefinition needs privileges on both the original and interim tables, plus `EXECUTE` on `DBMS_REDEFINITION`. Redefining objects across schemas requires administrative privileges per Oracle documentation.

Never grant broad `ANY` or `DBA` privileges just to make an example work. DBAs should grant exact required privileges to the owner/operator and revoke temporary privileges afterward per policy.

## 8. Step-by-Step DBMS_REDEFINITION Workflow

The example below uses schema `APP`, table `ORDERS`, and interim table `ORDERS_INT`. This is an illustrative framework; adapt structures, privileges, tablespaces, and column names to your real database.

### 8.1. Step 1 — CAN_REDEF_TABLE

~~~sql
BEGIN
    DBMS_REDEFINITION.CAN_REDEF_TABLE(
        uname        => 'APP',
        tname        => 'ORDERS',
        options_flag => DBMS_REDEFINITION.CONS_USE_PK
    );
END;
/
~~~

The procedure verifies the table can use the chosen method. Proceed only when error-free and business/resource checks are satisfied.

### 8.2. Step 2 — START_REDEF_TABLE

~~~sql
BEGIN
    DBMS_REDEFINITION.START_REDEF_TABLE(
        uname        => 'APP',
        orig_table   => 'ORDERS',
        int_table    => 'ORDERS_INT',
        col_mapping  =>
            'ORDER_ID ORDER_ID, ' ||
            'CUSTOMER_ID CUSTOMER_ID, ' ||
            'CREATED_AT ORDER_CREATED_AT, ' ||
            'STATUS STATUS, ' ||
            'CAST(NULL AS VARCHAR2(30)) SOURCE_SYSTEM',
        options_flag => DBMS_REDEFINITION.CONS_USE_PK
    );
END;
/
~~~

`col_mapping` describes how columns map from the original table to the interim table. Expressions can rename or transform values where data types and redefinition rules allow.

Check carefully:
- Every target column has a valid mapping expression.
- Data types/precision/scale are compatible.
- `NOT NULL`/default/identity semantics.
- Transformed values do not violate constraints.
- Primary key mapping is consistent.

Never put non-deterministic functions or side-effecting expressions in `col_mapping` without understanding their behavior during copy/sync.

### 8.3. Step 3 — COPY_TABLE_DEPENDENTS

~~~sql
DECLARE
    l_num_errors PLS_INTEGER;
BEGIN
    DBMS_REDEFINITION.COPY_TABLE_DEPENDENTS(
        uname            => 'APP',
        orig_table       => 'ORDERS',
        int_table        => 'ORDERS_INT',
        copy_indexes     => DBMS_REDEFINITION.CONS_ORIG_PARAMS,
        copy_triggers    => TRUE,
        copy_constraints => TRUE,
        copy_privileges  => TRUE,
        ignore_errors    => FALSE,
        num_errors       => l_num_errors,
        copy_statistics  => TRUE,
        copy_mvlog       => FALSE
    );

    DBMS_OUTPUT.PUT_LINE('Dependent object errors: ' || l_num_errors);
END;
/
~~~

The procedure copies specified dependent objects. `copy_indexes` controls index copying; `CONS_ORIG_PARAMS` uses original index parameters per package mechanics.

If errors occur, query `DBA_REDEFINITION_ERRORS` and resolve each object. Never set `ignore_errors => TRUE` just to push forward without knowing which objects were skipped.

Error query example:

~~~sql
SELECT object_owner,
       object_name,
       base_table_owner,
       base_table_name,
       ddl_txt
FROM   dba_redefinition_errors
WHERE  base_table_owner = 'APP'
AND    base_table_name = 'ORDERS';
~~~

### 8.4. Step 4 — SYNC_INTERIM_TABLE

While DML continues on the original table, synchronize accumulated changes:

~~~sql
BEGIN
    DBMS_REDEFINITION.SYNC_INTERIM_TABLE(
        uname      => 'APP',
        orig_table => 'ORDERS',
        int_table  => 'ORDERS_INT'
    );
END;
/
~~~

You can call `SYNC_INTERIM_TABLE` multiple times before finishing to keep the backlog of pending changes small. On high-DML tables, monitor sync durations and change generation rates.

Do not let redefinition linger indefinitely unmonitored; interim tables, redo/undo, and new segments all consume resources.

### 8.5. Step 5 — FINISH_REDEF_TABLE

~~~sql
BEGIN
    DBMS_REDEFINITION.FINISH_REDEF_TABLE(
        uname            => 'APP',
        orig_table       => 'ORDERS',
        int_table        => 'ORDERS_INT',
        dml_lock_timeout => 30
    );
END;
/
~~~

`FINISH_REDEF_TABLE` syncs final deltas and completes the swap. This step requires a brief DML/metadata lock for consistency. `dml_lock_timeout` bounds lock wait time per package semantics.

If the lock cannot be acquired in time, finish fails. Investigate blockers, re-sync if needed, and retry in a suitable window. Do not set an excessively high timeout if the application cannot tolerate prolonged DML stalls.

### 8.6. Step 6 — Post-Finish Verification

Verify structure:

~~~sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM   all_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
~~~

Verify indexes:

~~~sql
SELECT index_name,
       index_type,
       status,
       visibility
FROM   all_indexes
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY index_name;
~~~

Verify constraints:

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated
FROM   all_constraints
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY constraint_name;
~~~

Verify triggers, grants, statistics, invalid objects, row counts, and sample data. Clean up old/interim objects only based on actual verified state after confirming metadata switched cleanly.

### 8.7. Step 7 — Clean Up Interim/Old Object

After finishing, the interim name now refers to the old table due to redefinition's object swap. Verify `DBA_TABLES`, `DBA_OBJECTS`, and package documentation before dropping.

Never blindly run `DROP TABLE APP.ORDERS_INT` immediately after finishing without verifying which object holds that name. Retain necessary backups/reconciliation records and drop only the true old object after verifying application behavior.

## 9. Aborting or Handling Failed Redefinitions

### 9.1. ABORT_REDEF_TABLE

If you need to cancel before finishing:

~~~sql
BEGIN
    DBMS_REDEFINITION.ABORT_REDEF_TABLE(
        uname      => 'APP',
        orig_table => 'ORDERS',
        int_table  => 'ORDERS_INT'
    );
END;
/
~~~

Abort terminates the active redefinition process. The original table remains the live application object; inspect state and clean up remaining interim/dependent objects per documentation.

### 9.2. When COPY_TABLE_DEPENDENTS Fails

- Query `DBA_REDEFINITION_ERRORS`.
- Identify which objects failed to copy.
- Check if objects can be created manually after finish.
- Check whether triggers/constraints/indexes reference old column names.
- Fix and re-run the appropriate step, or abort.
- Never finish while critical dependencies are missing.

### 9.3. When SYNC_INTERIM_TABLE Runs Long

Possible causes:
- High DML rate.
- Throttled redo/undo or I/O.
- Insufficient resources on interim table/indexes.
- Huge transactions on the original table.
- Storage contention from backups or batch jobs.

Monitor sync duration, redo volume, session waits, and blockers. Adjust workloads, run incremental syncs, or schedule finish during low DML periods.

### 9.4. When FINISH_REDEF_TABLE Cannot Acquire the Lock

Identify blockers and long transactions. Never kill sessions reflexively. Options include:
- Waiting for active transactions to finish naturally.
- Asking application owners to close transactions.
- Briefly throttling DML.
- Picking a quieter window.
- Raising `dml_lock_timeout` cautiously if business SLAs allow.
- Re-syncing the interim table before the next finish attempt.

### 9.5. Checking Redefinition State

Views such as `DBA_REDEFINITION_OBJECTS` and `DBA_REDEFINITION_ERRORS` help track objects and errors depending on the release. Inspect available dictionary views with `DESC` and consult Oracle Database Reference. Never rely on a single view to conclude all steps finished cleanly.

## 10. Phased Online Constraint Changes

### 10.1. ENABLE NOVALIDATE

You can add a constraint and enforce it on new DML without validating all legacy rows yet:

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT ck_orders_total
CHECK (total_amount >= 0)
ENABLE NOVALIDATE;
~~~

This splits deployment into two steps:
1. Introduce the constraint to guard new changes.
2. Clean legacy data and validate afterward.

Semantics differ by constraint type; unique/primary keys require specific index/state conditions. Check constraint behavior and documentation before use.

### 10.2. Finding Violating Data Before VALIDATE

~~~sql
SELECT order_id,
       total_amount
FROM   app.orders
WHERE  total_amount < 0;
~~~

Fix data according to business rules—do not just zero out negative values to force validation to pass. Then:

~~~sql
ALTER TABLE app.orders
ENABLE VALIDATE CONSTRAINT ck_orders_total;
~~~

Validation can read the whole table and consume substantial resources. Monitor locks/waits and execute during suitable workloads.

### 10.3. NOVALIDATE Does Not Mean Historical Data Is Valid

An `ENABLE NOVALIDATE` constraint can leave violating rows in place. Queries over historical data may still return violating rows. Document `ENABLED`/`VALIDATED` status in metadata and change records.

~~~sql
SELECT constraint_name,
       status,
       validated
FROM   all_constraints
WHERE  owner = 'APP'
AND    table_name = 'ORDERS';
~~~

## 11. Online Indexes and Index Maintenance

### 11.1. Creating Indexes Online

~~~sql
CREATE INDEX app.ix_orders_created
ON app.orders(created_at)
ONLINE;
~~~

Index builds read table data and write index segments. Concurrent DML is tracked and synchronized via Oracle mechanisms. CPU/I/O overhead remains significant.

### 11.2. Online Rebuilds and Unusable Indexes

~~~sql
ALTER INDEX app.ix_orders_created
REBUILD ONLINE;
~~~

Before rebuilding:
- Check index status.
- Check index type and partitioning.
- Check tablespace/free space.
- Determine whether a constraint relies on the index.
- Estimate execution plan impact and build duration.
- Verify licensing/edition entitlements.

Do not rebuild indexes simply because they are large; examine segment growth, `blevel`, clustering factor, workload, and specific evidence.

### 11.3. Partitioned Indexes

For local vs. global partitioned indexes, syntax and impact differ. Partition maintenance operations can render global indexes `UNUSABLE` unless index maintenance clauses are specified.

Check `DBA_IND_PARTITIONS`, `DBA_IND_SUBPARTITIONS`, `DBA_INDEXES`, and appropriate `UPDATE INDEXES`/`UPDATE GLOBAL INDEXES` syntax for your operation. Do not treat a global index rebuild as a blanket fix for every scenario.

### 11.4. Monitoring Progress

~~~sql
SELECT sid,
       serial#,
       opname,
       target,
       sofar,
       totalwork,
       units,
       elapsed_seconds,
       time_remaining
FROM   v$session_longops
WHERE  totalwork > 0
AND    sofar < totalwork
ORDER  BY elapsed_seconds DESC;
~~~

Not every DDL operation appears in `V$SESSION_LONGOPS`. Combine alert logs, session waits, SQL Monitor if licensed, and wall-clock timing.

## 12. Designing Non-Disruptive Migrations with Expand-and-Contract

### 12.1. Why Are Multiple Steps Needed?

Even when DDL runs online, old and new application versions can coexist during rolling deployments. Renaming a column immediately breaks old versions before every instance upgrades.

Expand-and-contract pattern:
1. **Expand:** add new columns/tables/constraints compatible with old code.
2. **Deploy:** deploy code able to read/write both old and new structures.
3. **Backfill:** copy data to new columns/structures in batches.
4. **Verify:** reconcile data and shift traffic/read paths.
5. **Contract:** stop using old structures and drop/rename them only after a safe window.

### 12.2. Column Rename Example

Suppose `CUSTOMER_NAME` must be renamed to `DISPLAY_NAME`.

Do not simply run:
~~~sql
ALTER TABLE app.customer RENAME COLUMN customer_name TO display_name;
~~~

if old applications still query `CUSTOMER_NAME`.

Compatible workflow:
1. Add `DISPLAY_NAME` nullable or with an appropriate default.
2. Deploy application dual-writing per policy.
3. Backfill `DISPLAY_NAME` in batches.
4. Reconcile data.
5. Switch application reads to `DISPLAY_NAME`.
6. Stop writing `CUSTOMER_NAME`.
7. After a stabilization window, drop/rename the old column in a separate change.

Dual-writing requires handling partial failures, transactions, and concurrency. Temporary triggers can help, though recursion, performance, and business logic must be evaluated.

### 12.3. Batched Backfilling

~~~sql
UPDATE app.customer
SET    display_name = customer_name
WHERE  display_name IS NULL
AND    customer_id BETWEEN :low_id AND :high_id;
~~~

Range chunking bounds transaction/undo size and tracks progress. Choose batch sizes based on redo, undo, locks, replication lag, and workload. Commit per batch per procedure and persist checkpoints for resumability.

### 12.4. Consistency Checks

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM   app.customer
WHERE  NVL(display_name, CHR(0))
   <>  NVL(customer_name, CHR(0));
~~~

Production checks must handle `NULL`s, collations, and exact normalization rules. Never use a sentinel value that might occur in real data; this snippet is purely illustrative.

## 13. Lock Windows and Cutover Strategy

### 13.1. Measure the Lock Window Separately

With `DBMS_REDEFINITION`, copy/sync phases can run long while DML continues. `FINISH_REDEF_TABLE` is the cutover point requiring locks for final synchronization and metadata swap.

Measure:
- Lock acquisition time.
- Final sync time.
- Finish duration.
- Count of queued transactions.
- Application p95/p99 latency.
- Count of blocked sessions.
- Post-cutover validation time.

Do not quote total redefinition runtime as the downtime estimate; measure the DML-blocking phase separately.

### 13.2. Lower DML Rate Before Cutover

Reduce pending sync deltas by:
- Choosing off-peak hours.
- Pausing heavy write batches.
- Coordinating deployments and maintenance.
- Pre-running incremental syncs.
- Asking application owners to throttle concurrency for a few minutes.

Full application shutdown is unnecessary when operations support DML; the goal is keeping the final switchover short and predictable.

### 13.3. Bounding DDL_LOCK_TIMEOUT

Increasing the timeout lets DDL wait longer, yet also:
- DDL sessions hold resources and can form lock queues.
- Other sessions can be affected depending on lock order.
- Maintenance can overrun its planned window.
- Operators struggle to tell when to abort.

Set a bounded timeout with retry rules. Never configure massive timeouts to mask blockers.

### 13.4. Lock Timeouts and Applications

While DDL waits for a lock, applications may continue normally or queue behind it depending on lock types and operations. Monitor:
- Blocking sessions.
- Waiting sessions.
- Connection pool pending threads.
- Request latency.
- Error rates.
- Database wait classes.

If latency breaches thresholds, pause or defer the DDL per runbook.

## 14. Post-DDL Monitoring and Verification

### 14.1. Checking Object Status

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM   dba_objects
WHERE  owner = 'APP'
AND    object_name IN ('ORDERS', 'IX_ORDERS_STATUS')
ORDER  BY object_type, object_name;
~~~

### 14.2. Checking Invalid Objects

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM   dba_objects
WHERE  owner = 'APP'
AND    status <> 'VALID'
ORDER  BY object_type, object_name;
~~~

Some objects turn invalid after dependency changes. Diagnose causes and compile per procedure; avoid blindly recompiling everything without understanding dependencies.

### 14.3. Checking Indexes

~~~sql
SELECT index_name,
       index_type,
       status,
       visibility,
       uniqueness
FROM   dba_indexes
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY index_name;
~~~

For partitioned indexes, also inspect each partition/subpartition status.

### 14.4. Checking Constraints

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       rely
FROM   dba_constraints
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY constraint_name;
~~~

Check `VALIDATED` alongside `STATUS`. `ENABLE NOVALIDATE` differs from `ENABLE VALIDATE`.

### 14.5. Checking Data

Compare:
- Row counts.
- Min/max primary keys.
- Aggregates by partition or business group.
- Null counts.
- Duplicate keys.
- Checksums over business columns.
- Orphan foreign keys.
- Post-conversion values.

For tables under continuous DML, reconciliation must use a consistent point-in-time or proper sync/validation workflow.

### 14.6. Statistics and Execution Plans

After moves/redefinitions, review statistics and plans for critical SQL. Gather statistics if aligned with policy:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
~~~

Avoid arbitrarily gathering stats after every DDL if auto-stats or release workflows already handle it. Check execution plans, buffer gets, elapsed times, and bind distributions.

## 15. Online DDL / DBMS_REDEFINITION Deployment Runbook

### Pre-Run

1. Identify target schema/table and planned changes.
2. Inspect data types, constraints, indexes, triggers, partitions, LOBs, and dependencies.
3. Confirm edition, licensing, and operation support in Oracle 19c.
4. Check long-running transactions/locks and DML rates.
5. Check tablespaces, TEMP, UNDO, REDO, FRA, and backups.
6. Prepare the interim table or reviewed DDL scripts.
7. Run `CAN_REDEF_TABLE` if using `DBMS_REDEFINITION`.
8. Rehearse on comparable data and workload.
9. Measure copy, sync, and cutover durations.
10. Prepare abort/rollback/forward-fix plans and identify approvers.

### During Execution

1. Record change ID, session, module, and start timestamp.
2. Monitor `V$SESSION`, `V$LOCKED_OBJECT`, `DBA_DDL_LOCKS`, and wait events.
3. Monitor CPU, I/O, TEMP, UNDO, REDO, and storage.
4. Monitor job/procedure progress and error views.
5. Run `SYNC_INTERIM_TABLE` as appropriate.
6. Run `FINISH` only when dependent objects and cutover readiness pass.
7. Cap lock timeouts and monitor blockers.
8. Halt/abort if predefined thresholds breach.

### Post-Run

1. Verify table metadata and object names.
2. Verify indexes, constraints, triggers, and grants.
3. Verify row counts and business data.
4. Check invalid objects and sequences.
5. Inspect SQL plans and latency.
6. Clean up old/interim objects only after confirming accuracy.
7. Gather statistics per policy.
8. Archive logs, elapsed times, lock windows, and outcomes in the change record.

## 16. Choosing an Approach by Scenario

| Requirement | Candidate Option | Key Checks |
|---|---|---|
| Create B-tree index on active table | `CREATE INDEX ONLINE` | Index type, edition, space, CPU/I/O |
| Rebuild index during DML | `ALTER INDEX REBUILD ONLINE` | Index/partition support, lock window |
| Move heap table | `ALTER TABLE MOVE ONLINE` | Table/LOB/partition limits, indexes |
| Add compatible column | `ADD COLUMN`, check fast metadata optimization | Default, `NOT NULL`, datatype, DDL lock |
| Add constraint with dirty legacy data | `ENABLE NOVALIDATE` then `VALIDATE` | Constraint type, legacy data, validation cost |
| Complex datatype/partition/column mapping change | `DBMS_REDEFINITION` | Eligibility, interim table, dependencies, space |
| Rename column during rolling deployment | Expand-and-contract | App compatibility and dual-writes |
| Operation lacking `ONLINE` support | Offline DDL in maintenance window or redesign | Downtime, backups, locks, and rollback |

No single online technique fits every DDL change. Select based on operation, object, edition, dependencies, and acceptable disruption.

## 17. Common Errors and Troubleshooting

| Error/Symptom | Possible Cause | Resolution |
|---|---|---|
| `ORA-00054` | Failed to acquire lock within allowed wait | Identify blocker, set `DDL_LOCK_TIMEOUT`, controlled retry |
| `ORA-01450` | Key/index entry exceeds block limit | Review key length, block size, index design |
| `ORA-01408` | Column list already indexed similarly | Inspect existing indexes |
| `ORA-01452` | Creating unique index with duplicate rows | Find duplicates and resolve data |
| `ORA-01502` | Index/partition unusable | Identify cause and rebuild/recover appropriately |
| Redefinition dependency errors | Redefinition prerequisites/dependencies unmet | Read root error and `DBA_REDEFINITION_ERRORS` |
| `FINISH_REDEF_TABLE` stalls | Active transactions/blockers or high DML rate | Find blocker, re-sync, pick lower-traffic cutover |
| Interim table missing objects | `COPY_TABLE_DEPENDENTS` errored/skipped | Check `DBA_REDEFINITION_ERRORS` and create dependencies properly |
| Out of tablespace | Old and new segments coexist | Add space, clean up right objects, re-plan |
| Elevated DML latency | CPU/I/O/redo/undo contention | Lower concurrency, adjust schedule/parallelism |
| SQL plan changes | Statistics/indexes/access paths changed | Compare plans, stats, and SQL workload |

### 17.1. ORA-00054

Inspect blockers before increasing timeouts:

~~~sql
SELECT sid,
       serial#,
       username,
       event,
       blocking_session,
       sql_id,
       module
FROM   v$session
WHERE  blocking_session IS NOT NULL;
~~~

If the transaction belongs to a long batch, coordinate with its owner to finish safely. Never kill sessions before assessing rollback impact.

### 17.2. ORA-01452 When Creating a Unique Index

Find duplicates:

~~~sql
SELECT customer_id,
       COUNT(*) AS row_count
FROM   app.orders
GROUP  BY customer_id
HAVING COUNT(*) > 1;
~~~

Resolve duplicates per business rules before creating the unique index. Never arbitrarily delete duplicate rows.

### 17.3. Redefinition Errors

~~~sql
SELECT *
FROM   dba_redefinition_errors
WHERE  base_table_owner = 'APP'
AND    base_table_name = 'ORDERS';
~~~

Inspect `DDL_TXT` to identify failing dependent objects. Finish only once all mandatory objects are resolved.

## 18. Common Misconceptions

**"ONLINE means zero locks."** False. Operations may still need brief metadata locks at start/finish or wait on transactions.

**"All ALTER TABLE statements support ONLINE."** False. Only specific operations, syntax forms, and object types are supported.

**"DBMS_REDEFINITION requires no extra space."** False. Original and interim structures coexist alongside indexes/LOBs and redo/undo.

**"CAN_REDEF_TABLE succeeding guarantees the whole migration will succeed."** False. It checks eligibility, not space, mappings, dependencies, or workload behavior.

**"COPY_TABLE_DEPENDENTS errors can be ignored."** False. Missing indexes, triggers, constraints, or privileges can break applications post-cutover.

**"FINISH_REDEF_TABLE requires no locks."** False. The final step syncs deltas and swaps metadata, and may wait on DML locks.

**"DDL_LOCK_TIMEOUT makes DDL run online."** False. It merely controls lock wait duration.

**"ENABLE NOVALIDATE means legacy data is already valid."** False. Historical rows have not been validated.

**"Online table moves always preserve every index and dependency."** Never assume; verify indexes, LOBs, and related objects afterward.

**"DDL can be undone with ROLLBACK."** False. Many DDL statements perform implicit commits.

**"If DDL fails, nothing changed."** False. Prior steps or dependent changes may already have committed before failure.

**"Online DDL has no effect on execution plans."** False. Indexes, statistics, metadata, and cursor invalidations can alter plans.

## 19. Hands-On Labs

Perform these in a test schema with reproducible data. Never run create/drop/alter labs in production without change approval.

### Lab 1 — Observing DML Locks

Open two sessions. Session A updates a row without committing; Session B updates the same row. Observe wait events and `blocking_session`.

### Lab 2 — DDL Waiting on a Transaction

Hold an open transaction on a test table, then run `ALTER TABLE` from another session. Observe `ORA-00054` with `DDL_LOCK_TIMEOUT=0` and test with a bounded timeout.

### Lab 3 — Creating an Index Online

Create an index on a test table with `ONLINE` while another session runs DML. Record elapsed time, latency, and index status.

### Lab 4 — Rebuilding an Index Online

Rebuild a test index with `ONLINE`. Monitor `V$SESSION_LONGOPS`, CPU/I/O, and post-completion status.

### Lab 5 — MOVE TABLE ONLINE

Move a test heap table to another tablespace. Verify segments, indexes, LOBs, and row counts.

### Lab 6 — Adding a NOVALIDATE Constraint

Create legacy violating rows, add an `ENABLE NOVALIDATE` constraint. Test violating new DML, then fix legacy rows and run `VALIDATE`.

### Lab 7 — SET UNUSED

Mark a test column `SET UNUSED`. Confirm the column no longer appears in standard metadata; time `DROP UNUSED COLUMNS` separately.

### Lab 8 — CAN_REDEF_TABLE

Create a table with a primary key and run `CAN_REDEF_TABLE` with `CONS_USE_PK`. Document success criteria.

### Lab 9 — Redefinition Column Rename

Create an interim table and use `col_mapping` to map `CREATED_AT` to `ORDER_CREATED_AT`. Verify data after finish.

### Lab 10 — COPY_TABLE_DEPENDENTS

Create indexes, triggers, constraints, and grants on a test table. Run `COPY_TABLE_DEPENDENTS` and inspect `DBA_REDEFINITION_ERRORS`.

### Lab 11 — Incremental Syncing

During redefinition, run DML in another session. Call `SYNC_INTERIM_TABLE` multiple times and observe sync durations.

### Lab 12 — Blocked Finish

Hold a transaction on the original table before finish. Observe finish waiting or timing out; release the lock safely and retry.

### Lab 13 — Aborting Redefinition

Start a test redefinition and run `ABORT_REDEF_TABLE`. Confirm the original table stays usable and inspect interim objects needing cleanup.

### Lab 14 — Designing Expand-and-Contract

Simulate renaming a column for an application running two versions concurrently. Design add, dual-write/backfill, verify, read switch, and old column drop.

## 20. Oracle Reference Documentation

- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_REDEFINITION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_REDEFINITION.html): `CAN_REDEF_TABLE`, `START_REDEF_TABLE`, `COPY_TABLE_DEPENDENTS`, `SYNC_INTERIM_TABLE`, `FINISH_REDEF_TABLE`, and `ABORT_REDEF_TABLE`.
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): table modification variants and syntax restrictions.
- [Oracle Database 19c SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): index creation and the `ONLINE` clause.
- [Oracle Database 19c SQL Language Reference — ALTER INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-INDEX.html): index rebuild and maintenance.
- [Oracle Database 19c Database Reference — DDL_LOCK_TIMEOUT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DDL_LOCK_TIMEOUT.html): DDL lock wait duration.
- [Oracle Database 19c Database Reference — V$LOCKED_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCKED_OBJECT.html): currently held object locks.
- [Oracle Database 19c Database Reference — DBA_DDL_LOCKS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DDL_LOCKS.html): DDL lock metadata.
- [Oracle Database 19c Database Reference — DBA_REDEFINITION_ERRORS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_REDEFINITION_ERRORS.html): errors when copying dependent objects during redefinition.
- [Oracle Database VLDB and Partitioning Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): online table/index maintenance and partition operations.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/): database editions and feature licensing conditions.

Online DDL allows certain structural changes to keep serving DML most of the time, yet remains bounded by operation, object, edition, and resource constraints; metadata steps can still require brief locks. `DBMS_REDEFINITION` handles more complex table restructurings by copying data to an interim table, syncing DML, and performing a controlled cutover. **Verify eligibility, dependencies, licensing, capacity, and blockers upfront; measure the final lock window separately, validate all objects post-cutover, and always maintain an abort or forward-fix plan.**
