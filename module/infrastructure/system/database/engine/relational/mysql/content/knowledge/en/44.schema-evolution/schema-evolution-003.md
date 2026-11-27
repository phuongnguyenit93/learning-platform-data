# Schema Drift, Migration Ordering, and Concurrent Deployment Locking

A MySQL schema evolves across the application lifecycle: adding tables, adding columns, creating indexes, altering data types, or removing legacy structures. When multiple environments, development branches, or services modify the database, the actual structure can diverge from what the source code and migrations expect. This phenomenon is called **schema drift**. If migrations run out of order or concurrently, the application can fail even when each individual migration was tested.

This lesson focuses on three closely related problems: detecting and handling schema drift, managing migration ordering, and locking so that only one schema deployment process executes changes at a time. Within the `DATABASE_MYSQL` module, this content connects table design, DDL, transactions, metadata locks, and deployment operations.

After this lesson, you will be able to:

- Distinguish schema drift from a valid unapplied migration.
- Compare the actual schema against a canonical schema and identify discrepancies.
- Manage ordered migrations, checksums, and execution history.
- Understand the impact of implicit commits and metadata locks in MySQL DDL.
- Prevent multiple pipelines or application instances from running migrations concurrently.
- Deploy compatible changes using the expand-contract pattern.
- Handle migrations that fail partway through and establish post-deployment verification procedures.

## 1. What is schema drift?

Schema drift occurs when the running database structure differs from the structure declared in migrations, schema manifests, or the project's canonical data model. Discrepancies can originate from many places:

- A column is added manually in production without a corresponding migration in the repository.
- A migration has run on staging but not yet on production.
- One branch alters a column type while another branch adds an index based on the old definition.
- A hotfix changes a default, nullability, or collation without updating migrations.
- A table or index is manually dropped during incident mitigation.
- Two environments run different migration versions even though both are labeled staging.

Not every difference is an error. One environment may intentionally contain extra tables for testing or differ in resource configuration. What matters is classifying discrepancies: which structures belong to the application contract, which belong to environment-specific configuration, and which are out-of-band changes.

### 1.1. What can drift affect?

| Discrepancy type | Example | Potential consequence |
|---|---|---|
| Missing structure | Missing `customer_status` column | New application fails when querying the column |
| Extra structure | Production has a hotfix-created table | Subsequent migrations may hit object-already-exists errors |
| Different data type | `VARCHAR(100)` in one environment, `VARCHAR(255)` in another | Different storage, indexing, or validation behavior |
| Different null/default | One environment allows `NULL`, another requires `NOT NULL` | Inserts may succeed in one place and fail in another |
| Different index/constraint | Missing unique index or foreign key | Slow queries or duplicate/orphaned data |
| Different charset/collation | `utf8mb4_0900_ai_ci` vs. another collation | Different string comparisons, sorting, and uniqueness |
| Divergent migration history | History table marks version as run, but actual schema is incomplete | Deployment tool skips required steps or next migration fails |

Schema drift can linger silently long before causing failures. For instance, a missing index does not break the application immediately, yet causes queries to slow down as data grows. A missing unique constraint can allow duplicate records that the application discovers weeks later.

## 2. Establishing a single source of truth for the schema

A project must clearly define which source describes the desired schema. Typically, this is the set of versioned migrations stored in the repository. Some systems also generate a schema manifest or canonical DDL from a schema management tool.

Key principles:

1. **Every schema change must have a reviewed migration.** Direct changes on shared environments should be reserved for emergencies and captured as migrations immediately afterward.
2. **Applied migrations are immutable.** Do not modify the contents of an old migration once it has run on any shared environment. Create a new migration for further changes.
3. **Each migration has a unique identifier and clear ordering.** Sequential numbers or timestamps paired with descriptive names can be used.
4. **Execution history must be stored in the database.** The tool needs to know which migrations ran, which checksums were applied, and their outcomes.
5. **Do not equate migration history with schema state.** The history table shows what the tool recorded; inspecting the actual schema remains essential.

Example migration filenames:

```text
202611190900_add_customer_status.sql
202611190930_create_customer_status_index.sql
202611191000_backfill_customer_status.sql
202611191100_enforce_customer_status_not_null.sql
```

Timestamps are just one example. If multiple branches can create migrations simultaneously, the team needs a numbering convention or sufficiently granular timestamps and must resolve conflicts during merges. Never allow two migrations with different contents to share the same version.

## 3. Detecting schema drift

Detecting drift requires comparing the actual structure against the canonical structure. Compare at the structured metadata level rather than merely diffing `SHOW CREATE TABLE` text, because output formatting can vary by MySQL version, display order, or default attributes.

### 3.1. Inventorying tables and engines

Run in each environment:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_COLLATION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

InnoDB's `TABLE_ROWS` is usually an estimate, not an exact row count. Use this query for structural inventory and spotting engine/collation differences; do not use `TABLE_ROWS` as exact data reconciliation proof.

### 3.2. Comparing columns

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Export results from each environment and compare against the reviewed manifest. Pay attention to `COLUMN_TYPE`, nullability, defaults, `EXTRA` (such as auto_increment or generated columns), charset, and collation. For expression defaults, check how the server represents the expression so formatting differences are not mistaken for true drift.

### 3.3. Comparing indexes and keys

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

Check column order within composite indexes, unique/non-unique flags, and index types. Two indexes with the same column set but different column ordering are not equivalent for all queries.

Check foreign keys:

```sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
```

Separately inspect `CHECK_CONSTRAINTS`, `TABLE_CONSTRAINTS`, triggers, views, and routines if they are part of the application's schema contract.

### 3.4. Normalizing comparison output

A comparison tool should:

- Obtain the canonical schema from reviewed migrations or manifests.
- Gather actual metadata from `INFORMATION_SCHEMA` and `SHOW CREATE` when detailed verification is needed.
- Normalize default values, schema names, data types, and version-dependent attributes.
- Ignore environment-specific attributes explicitly allowed to differ.
- Output diffs showing object type, expected value, actual value, and impact severity.

Never automatically execute `ALTER TABLE` for every difference a tool detects. A diff may require a decision from the data owner, especially when changes involve dropping columns, narrowing data types, or adding constraints over existing data.

## 4. Migration history and checksums

A migration history table typically stores version, checksum, and execution timestamp. Simple example:

```sql
CREATE TABLE schema_migrations (
    version VARCHAR(100) NOT NULL,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    execution_ms BIGINT UNSIGNED NULL,
    applied_by VARCHAR(128) NULL,
    PRIMARY KEY (version)
) ENGINE=InnoDB;
```

Tools such as Flyway, Liquibase, or custom migration frameworks may use different schemas and column names. Let the tool own its history table; do not alter tool-managed table structures without following its documentation.

Checksums detect when a migration file has been altered after running. When a tool reports a checksum mismatch, treat it as a signal to investigate. Never update the checksum in the history table to mask file edits.

A migration workflow may execute as follows:

1. Read the migration list in order.
2. Match executed versions against existing files.
3. Verify checksums of applied migrations.
4. Check preconditions before new migrations.
5. Execute one migration in strict order.
6. Verify DDL results and record history according to the tool's mechanism.
7. Proceed to the next migration only after the previous step succeeds.

If a migration fails partway through, do not assume MySQL rolled back all changes. Inspect the actual schema, logs, history table, and connection state before deciding to fix or re-run.

## 5. Migration ordering and dependencies between changes

Migrations must run in an order where every intermediate state is safe. For example, if the application needs to read a new column, that column must exist before deploying the application version that uses it. If an index must be created before enabling a new query, verify the index is ready before shifting traffic.

A migration may depend on:

- Tables or columns created in an earlier migration.
- Data backfilled before adding `NOT NULL` or constraints.
- Indexes created before a new query receives heavy load.
- An application version having stopped reading/writing an old column before dropping it.
- Another service having deployed compatibility with a shared schema.

Do not rely on accidental filesystem ordering. The migration tool must sort explicitly by version and reject version conflicts or checksum mismatches.

### 5.1. Avoiding conflicting parallel migrations across branches

Suppose branch A adds `customer_status`, while branch B creates an index on `customer_status`. If branch B's migration runs before the column-creation migration, `CREATE INDEX` will fail. When merging, resolve dependencies and version ordering before deployment.

Useful conventions:

- Every migration has a globally unique version across the repository.
- Never rebase or edit applied migrations on shared environments.
- Dependent migrations must declare or clearly reflect dependencies in version ordering.
- CI creates a clean database and runs all migrations in order to catch missing dependencies.
- CI also tests upgrading from a production-like schema, because building from an empty database does not catch all drift.

## 6. MySQL DDL, implicit commits, and rollback limits

MySQL handles many DDL statements such as `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, and `CREATE INDEX` with an implicit commit. This means you cannot treat a sequence of DDL statements like an ordinary InnoDB transaction and expect `ROLLBACK` to restore all structures.

For example:

```sql
START TRANSACTION;

ALTER TABLE customers
    ADD COLUMN customer_status VARCHAR(20) NULL;

ROLLBACK;
```

Do not expect `ROLLBACK` to remove the newly added column. DDL may have implicitly committed before or after the operation depending on statement and version. MySQL 8.0 supports atomic DDL for many supported operations, giving DDL server-level crash atomicity; **atomic DDL does not mean DDL participates in an application transaction or can be undone with `ROLLBACK`**.

Therefore:

- Break changes into small, verifiable steps.
- Have explicit corrective migrations instead of relying on transaction rollback.
- Back up and test on realistic data scales before major changes.
- Verify schema state after every critical DDL statement.
- Plan how to handle cases where DDL completes but migration history was not recorded.

If a DDL statement errors, some operations may not have altered the schema, yet in multi-DDL migrations earlier statements may have already completed. Always inspect the actual state before re-running the whole file.

## 7. Metadata locks and DDL wait times

MySQL uses metadata locks (MDL) to protect table and schema object metadata. Queries currently using a table or open uncommitted transactions can hold metadata locks, forcing DDL requiring incompatible locks to wait. Conversely, waiting DDL can queue up subsequent queries behind it, causing unexpected stalls.

For example, one session opens a transaction, reads `orders`, and leaves the transaction idle. Another session runs `ALTER TABLE orders ...`. The DDL must wait for the first transaction to end in order to acquire the required metadata lock.

Inspect metadata locks via Performance Schema:

```sql
SELECT
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    th.PROCESSLIST_ID,
    th.PROCESSLIST_USER,
    th.PROCESSLIST_TIME,
    th.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
    ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = DATABASE()
ORDER BY ml.OBJECT_NAME, ml.LOCK_STATUS;
```

`LOCK_STATUS` shows whether a lock is `GRANTED` or `PENDING`. Inspect both sessions holding locks and sessions waiting. Access to Performance Schema and available columns depend on configuration and version.

You can also inspect:

```sql
SHOW FULL PROCESSLIST;
```

Do not terminate a session merely because it is long-running. Identify the application, transaction, and impact before killing it. In production, establish procedures for long-lived idle transactions and cap metadata lock wait times.

### 7.1. Reducing risk when running ALTER TABLE

Before major DDL:

- Identify tables with long-running transactions or slow queries.
- Check disk space, I/O, replica lag, and application load.
- Verify which DDL algorithm is usable on the current version.
- Set an appropriate `lock_wait_timeout` for the migration session so it does not wait indefinitely.
- Run inside a deployment window with an abort plan if thresholds are exceeded.
- Monitor metadata locks, processlist, and replication status during execution.

Example setting a timeout for the migration session:

```sql
SET SESSION lock_wait_timeout = 15;
```

15 seconds is only an example. If it times out, the DDL fails cleanly because it could not acquire the metadata lock; resolve the blocker and retry per runbook. Never set unbounded timeouts while production queries are piling up in the queue.

## 8. Online DDL: ALGORITHM and LOCK

InnoDB supports multiple DDL algorithms. Depending on operation, version, table structure, and index types, MySQL may use `INSTANT`, `INPLACE`, or `COPY`; allowed lock levels also vary.

Illustrative example:

```sql
ALTER TABLE customers
    ADD COLUMN customer_note VARCHAR(200) NULL,
    ALGORITHM=INSTANT;
```

`ALGORITHM=INSTANT` can modify metadata without rebuilding the entire table for supported operations. Not every column addition, column position, table type, or version supports instant execution. If an unsupported algorithm is requested, the statement fails rather than silently falling back to another algorithm.

Another example:

```sql
ALTER TABLE orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

`LOCK=NONE` permits concurrent DML under supported operations and conditions. It does not mean zero metadata locking across every phase, zero I/O, or zero performance impact. Building an index still reads data, consumes CPU/I/O, and can generate significant load.

Before specifying `ALGORITHM` or `LOCK`, check the MySQL documentation for your exact version and operation. Test on a realistic data clone. If you want to guarantee DDL does not silently fall back to a heavy table copy, explicitly specify the desired algorithm/lock so MySQL errors out if it cannot comply rather than assuming it runs online.

## 9. Concurrent migration deployment locking

In CI/CD environments, two pipelines may detect unapplied migrations simultaneously and both attempt to apply them. One pipeline might create a table while the other tries to create the same table, or the second migration might run before the first finishes.

The system needs a locking mechanism so only one migration runner holds execution rights at a time on a given database/topology. Options include:

- The migration tool's built-in locking mechanism.
- MySQL advisory locks via `GET_LOCK()`.
- An application-implemented lock coordination table, if designed properly.
- An external distributed lock service in architectures with multiple database endpoints.

Prefer the locking mechanism officially supported by your migration tool. Do not bolt on a parallel lock mechanism if the tool already provides locking, as two mechanisms can create operational deadlocks or confusion over lock ownership.

### 9.1. Using MySQL advisory locks

MySQL provides `GET_LOCK(name, timeout)` for a session to request a named lock. Illustrative example:

```sql
SELECT GET_LOCK('shop-schema-migration', 30) AS lock_acquired;
```

Typical return values:

- `1`: the session acquired the lock.
- `0`: timed out waiting without acquiring the lock.
- `NULL`: an error occurred while executing the request.

Run migrations only after successfully acquiring the lock. After completion or error, release the lock on the same session:

```sql
SELECT RELEASE_LOCK('shop-schema-migration') AS lock_released;
```

Advisory locks are bound to the connection. If the connection closes, the lock is released. Therefore, the migration runner must maintain a stable connection from lock acquisition until migration completion. If a runner acquires the lock on one connection and runs DDL on another connection, the lock does not protect the execution region as intended.

Named locks only coordinate processes connecting to the same MySQL server using the same lock name. They do not automatically lock pipelines running against another server or an isolated environment. Lock names should represent the scope requiring serialization, such as a database/schema or shared topology.

### 9.2. Coordination pattern in a migration runner

Pseudocode:

```text
connection = openMigrationConnection()

try:
    result = connection.query(
        "SELECT GET_LOCK('shop-schema-migration', 30)"
    )

    if result != 1:
        fail("Failed to acquire migration lock")

    verifyMigrationHistoryAndChecksums(connection)

    for migration in pendingMigrationsInVersionOrder:
        verifyPreconditions(connection, migration)
        executeMigration(connection, migration)
        verifyPostconditions(connection, migration)
        recordMigrationHistory(connection, migration)
finally:
    connection.query(
        "SELECT RELEASE_LOCK('shop-schema-migration')"
    )
    connection.close()
```

This is a logical flow, not production-ready code for a specific framework. Handle connection drops before lock release, failures partway through DDL statements, and cases where migration history has not yet been recorded. If the connection drops, MySQL releases that session's advisory lock; the next runner must inspect the actual schema before proceeding.

### 9.3. Why row locking in the migration history table may not suffice

Some systems try to lock a row in the history table using `SELECT ... FOR UPDATE`. This only protects within a transaction. Many MySQL DDL statements cause an implicit commit, so the transaction can end and release row locks before the full migration sequence completes.

If using a lock table, understand clearly how the tool maintains the lock across migrations and how it recovers when a process dies. Never assume a transaction wrapping DDL will hold locks from start to finish.

## 10. Expand-contract: deploying schemas without breaking the application

When multiple application versions run side by side during rolling deployments, the schema must remain compatible with both old and new versions during the transition. The expand-contract pattern splits breaking changes into small steps.

Suppose `customers.name` needs to become `customers.display_name`:

### Phase 1: Expand

Add the new column while keeping the old column:

```sql
ALTER TABLE customers
    ADD COLUMN display_name VARCHAR(150) NULL;
```

The old application version continues reading/writing `name`; the new version can begin understanding `display_name`.

### Phase 2: Dual write or data synchronization

Deploy code that writes compatible values to both columns during transition, or run a batched backfill job to populate `display_name` from `name`. Designate a primary source of truth and avoid divergence between the two columns under concurrent updates.

Example primary-key batched backfill:

```sql
UPDATE customers
SET display_name = name
WHERE customer_id > 0
  AND customer_id <= 10000
  AND display_name IS NULL;
```

Continue in small key ranges, measure load, and verify updated row counts. Do not run a full-table `UPDATE` on a large table without evaluating locks, undo, redo, replication lag, and storage capacity.

### Phase 3: Switch reads

Deploy application code reading `display_name`, monitor errors, and reconcile data between both columns. Preserve rollback capability to the previous application version for a defined window.

### Phase 4: Contract

Once all application instances have stopped using `name`, backfill jobs are complete, and no legacy consumers remain, create a migration dropping the old column:

```sql
ALTER TABLE customers
    DROP COLUMN name;
```

This is a breaking operation. Confirm no queries, jobs, reports, or services still depend on the column before running. On large tables, evaluate DDL algorithms and operational impact.

Expand-contract applies to renaming columns, changing data types, restructuring tables, or migrating keys. Dual-writing is not strictly mandatory in every scenario; views, triggers, or other backfill workflows may be used, provided the source of truth and consistency guarantees are clearly evaluated.

## 11. Handling migrations that fail partway through

Because DDL triggers implicit commits, a multi-statement migration can partially complete. For instance, a migration succeeds in adding a column, then fails creating an index. The history table may not yet record the version while the schema has already changed.

When a failure occurs:

1. Halt other migration runners via the locking mechanism.
2. Record the error, executed DDL statements, connection ID, timestamp, and server logs.
3. Inspect the actual schema via `INFORMATION_SCHEMA` and `SHOW CREATE TABLE`.
4. Compare migration history and checksums.
5. Determine state: unchanged, partially changed, or completed without history recorded.
6. Create a corrective migration or use a tool-supported repair procedure.
7. Mark a migration as applied only after verifying all postconditions.

Do not blindly re-run the migration. `CREATE TABLE` or `ADD COLUMN` may fail because the object already exists; using `IF NOT EXISTS` is not always sufficient since the object might exist with the wrong definition.

If production must be patched via hotfix, record the exact DDL and data changes made, then create a migration so other environments can reach the same state. Never edit an already-applied migration file to pretend the hotfix was always part of history.

## 12. CI/CD workflow for migrations

A schema deployment pipeline should separate validation, execution, and verification:

1. **Validate:** check syntax, unique versions, checksums, and migration naming rules.
2. **Clean build:** create a fresh database and run all migrations in order.
3. **Upgrade test:** build a schema from a production-like version, then run new migrations.
4. **Drift check:** compare the actual schema against the expected manifest in the target environment.
5. **Review:** evaluate DDL, algorithms, duration, metadata locks, disk space, and replication impact.
6. **Serialize:** acquire the migration lock before validating and executing migrations.
7. **Apply:** execute migrations in order and store history/checksums.
8. **Verify:** check schema, indexes, constraints, backfilled data, and application health.
9. **Release:** deploy compatible application versions following expand-contract ordering.
10. **Observe:** monitor query errors, metadata locks, replication lag, and post-deploy performance.

In multi-database or sharded environments, define lock scope per database and rollout order. Do not let a migration run on one shard while another shard stays on the old schema if the application assumes uniform schema versions across all shards.

## 13. Common incidents and how to investigate

| Symptom | Likely cause | Investigation steps |
|---|---|---|
| Migration reports column already exists | Drift from hotfix or partially executed migration | Inspect `INFORMATION_SCHEMA.COLUMNS`, history, and checksums |
| Index creation migration fails | Wrong ordering, index already exists, or DDL limits | Inspect `INFORMATION_SCHEMA.STATISTICS` and table definition |
| Migration waits for a very long time | Metadata lock held by a long transaction or query | Inspect `performance_schema.metadata_locks` and processlist |
| Two pipelines run migrations simultaneously | Missing lock or lock does not cover the right scope | Inspect migration runner, connections, and named locks |
| Checksum mismatch | Migration file was edited after being applied | Compare repository, history, and release workflow |
| Old application fails after schema deploy | Breaking DDL applied too early | Check rollout ordering and apply expand-contract |
| Migration history lacks version but DDL exists | DDL implicit commit; runner died before recording history | Verify postconditions, then run controlled repair |
| Replica lag spikes after DDL/backfill | Heavy DDL or large updates creating replication load | Monitor applier, binlog volume, batch size, and backfill rate |

During investigation, capture before/after schema diffs, migration files and checksums, runner logs, processlist, metadata locks, and replication state. Never delete history rows or drop objects just to make the next run "clean" without knowing the data impact.

## 14. Pre-deployment schema checklist

- [ ] Migration has a unique version and verified checksum.
- [ ] Migration has already run in earlier environments in the exact same order.
- [ ] Target environment schema drift has been classified and resolved.
- [ ] DDL is compatible with the current MySQL version and engine.
- [ ] `ALGORITHM`, `LOCK`, metadata locks, and estimated runtime have been evaluated.
- [ ] Migration lock is in place to prevent concurrent runners.
- [ ] Old and new applications remain compatible during rolling deployment.
- [ ] Backfills are batched and resumable after errors.
- [ ] Backup/restore plan and partial-DDL recovery steps are ready.
- [ ] Postconditions exist to verify schema and data after migration.
- [ ] Monitoring covers replication lag, application errors, and performance.

## 15. Practice scenario

An e-commerce application has three environments: development, staging, and production. Production received a hotfix adding a `delivery_note` column directly. The corresponding migration was never committed to the repository. Another branch adds an index on `delivery_note`, and two pipelines are about to run migrations simultaneously.

Practice in a lab environment:

1. Create three databases representing the three environments with diverging schemas.
2. Manually add `delivery_note` to the simulated production database to create drift.
3. Use `INFORMATION_SCHEMA.COLUMNS` to compare the three environments and document discrepancies.
4. Write a normalizing migration so all environments end up with the same column definition.
5. Create an index migration versioned after the column-creation migration.
6. Simulate two migration runners executing concurrently and observe errors without locking.
7. Use `GET_LOCK()` to serialize the runners; verify the second runner waits or times out.
8. Open a transaction reading a table, then attempt DDL from another session; inspect metadata locks and processlist.
9. Test expand-contract to rename a column while old and new applications continue working during transition.
10. Simulate a migration that succeeds in adding a column but fails creating an index; inspect schema and history, then write a repair migration.

**Self-assessment questions:**

- How does schema drift differ from a new unapplied migration?
- Why should you not edit a migration that has already run on a shared environment?
- Why is the migration history table insufficient to prove the actual schema is correct?
- How does MySQL DDL implicit commit affect rollbacks and mid-migration failure recovery?
- How can a metadata lock cause both a DDL statement and subsequent queries to stall?
- How is `GET_LOCK()` bound to a connection and why must the runner keep the same connection?
- Why may locking a row in a transaction fail to protect an entire DDL sequence?
- How does expand-contract make rolling deployments safe?

## Conclusion

Safe schema management requires a single source of truth, ordered and immutable migrations, drift detection, and deployment locking to prevent multiple runners from modifying the database at once. In MySQL, implicit commits and metadata locks mean DDL must be planned, monitored, and verified explicitly. Roll out changes in compatible steps, verify the actual schema after every change, and maintain clear repair procedures when migrations fail partway through.
