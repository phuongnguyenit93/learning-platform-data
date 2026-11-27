# Adding Indexes CONCURRENTLY Outside a Migration Transaction in PostgreSQL

Indexes are essential for query performance, yet adding an index to a table actively serving application traffic can acquire locks and disrupt writes if built with the standard approach. PostgreSQL provides CREATE INDEX CONCURRENTLY to build an index while INSERT, UPDATE, and DELETE operations continue on the table.

There is one critical requirement: **CREATE INDEX CONCURRENTLY cannot run inside a transaction block**. Many migration frameworks wrap each migration in a transaction by default so DDL changes succeed or roll back atomically. Consequently, a migration creating an index concurrently must be configured to run outside a transaction using the mechanism supported by the framework.

This changes how schema deployments behave. Once the transaction wrapper is removed, the migration is no longer atomic like ordinary DDL migrations. An index build can run long, be canceled, or fail and leave behind an invalid index. The migration runner must explicitly manage state, logs, retries, and cleanup.

This lesson explains lock behavior and the phases of a concurrent index build, how to write non-transactional migrations across common frameworks, how to monitor progress and index validity, how to handle failures, how to build unique indexes, and how to deploy safely in production.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the differences between CREATE INDEX and CREATE INDEX CONCURRENTLY.
2. Understand why a concurrent index build allows DML to continue.
3. Explain why the command cannot run inside a transaction block.
4. Identify whether a migration framework uses a transaction wrapper by default.
5. Configure a migration to run outside a transaction per framework and version.
6. Separate index-creation migrations from transactional DDL.
7. Monitor progress using pg_stat_progress_create_index.
8. Verify index readiness, validity, and definition.
9. Handle invalid indexes after migration failures.
10. Build unique indexes concurrently and handle duplicate data.
11. Understand limitations with partitioned tables and constraint attachment.
12. Design lock_timeout, statement_timeout, retries, and concurrency controls.
13. Roll out schema changes using an expand-and-contract strategy.
14. Build runbooks, verification steps, and 80 hands-on exercises.

## 2. Why Is CREATE INDEX CONCURRENTLY Needed?

A standard CREATE INDEX builds the index by scanning the table. During this process, PostgreSQL acquires a lock that prevents concurrent writes on the table. Ordinary reads can still proceed, but INSERT, UPDATE, and DELETE operations may be blocked until the build completes.

On small tables, build time may be brief. On large tables serving OLTP traffic, an index build can take many minutes or longer. When DML is blocked, request latency rises, connection pools saturate, and subsequent transactions queue up behind it.

CREATE INDEX CONCURRENTLY allows writes to continue during most of the build. In exchange, PostgreSQL must execute multiple phases, perform multiple scans and transaction waits, and consume more wall-clock time, I/O, and WAL.

### 2.1. Comparing Both Approaches

| Aspect | CREATE INDEX | CREATE INDEX CONCURRENTLY |
| --- | --- | --- |
| DML during build | Blocked by index build lock | Can continue |
| Ordinary reads | Can continue | Can continue |
| Table scans | One main scan | Two main scans plus validation phases |
| Duration | Usually shorter | Usually longer |
| Locks | Stronger, blocks writes | Lighter on DML, still has locks and waits |
| Transaction block | Can run inside a transaction | Cannot run inside a transaction block |
| Failure | Transaction usually rolls back index creation | Can leave behind an invalid index |
| Best suited for | Low-traffic tables or maintenance windows | Production tables that must keep accepting writes |

### 2.2. "Concurrent" Does Not Mean Lock-Free

CREATE INDEX CONCURRENTLY still acquires locks on the table and must wait for certain transactions and snapshots. It reduces blocking for ordinary DML, but does not eliminate all forms of lock contention.

### 2.3. Trade-Offs

A concurrent build typically:
- Runs longer due to two scans and validation steps.
- Can wait on long-running transactions.
- Generates additional I/O and WAL alongside existing workload traffic.
- Increases CPU and storage load.
- Can leave behind an invalid index on failure.

### 2.4. When Should You Use It?

Consider CONCURRENTLY when the table is serving live traffic and blocking writes during the build is unacceptable. For small tables, staging environments, or maintenance windows where writes can stop, a standard build can be simpler and faster.

## 3. Lock Behavior

CREATE INDEX CONCURRENTLY uses locks that allow normal reads and writes to continue, yet still conflict with certain DDL and maintenance operations.

### 3.1. DML Keeps Running

INSERT, UPDATE, and DELETE can continue during a concurrent build. PostgreSQL must ensure changes occurring while the index is being constructed are fully reflected before marking the index valid.

### 3.2. Other DDL Can Be Blocked

Operations that alter table or index structure can conflict with the concurrent build's lock. Do not run multiple schema migrations on the same table simultaneously.

### 3.3. One Concurrent Build per Table at a Time

PostgreSQL only allows one CREATE INDEX CONCURRENTLY to run on a given table at a time. Schedule index builds on the same table sequentially.

### 3.4. Long Transactions Can Prolong the Build

A concurrent build must wait for transactions that could observe an older table/index state or hold snapshots incompatible with validating the index. An idle-in-transaction session or long-running query can extend these wait phases.

### 3.5. Lock Timeout

You can set lock_timeout so the migration does not wait too long for a lock:

~~~sql
SET lock_timeout = '5s';
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

This value is only an example. A short lock timeout prevents unbounded waits, though it can cause the migration to fail if competing DDL or maintenance is active on the table. The runner must log the error and retry per policy.

### 3.6. Lock Timeout Is Not Statement Timeout

lock_timeout limits wait time per lock acquisition attempt. statement_timeout limits total statement duration. An index build can take minutes or hours; do not apply a short statement_timeout suited for application requests.

### 3.7. Monitoring Blockers

During the build, check pg_stat_activity, pg_blocking_pids, and pg_locks if a wait phase drags on. Identify the blocker before considering canceling or terminating; never kill transactions arbitrarily.

## 4. Why Can't CREATE INDEX CONCURRENTLY Run Inside a Transaction Block?

PostgreSQL must commit intermediate states of a concurrent index build and wait for other transactions at specific points. If the entire command sits inside a single transaction block, the server cannot execute that lifecycle as required.

Invalid example:

~~~sql
BEGIN;

CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);

COMMIT;
~~~

PostgreSQL returns an error stating that CREATE INDEX CONCURRENTLY cannot run inside a transaction block.

### 4.1. Where Can a Transaction Block Come From?

It is not only an explicit BEGIN written by the migration author. A transaction wrapper can be added by:
- The migration framework.
- A test harness.
- A database client or deployment runner.
- A stored procedure, DO block, or script wrapper.
- A previously opened transaction on a pooled connection.

### 4.2. Autocommit

A standalone statement run in psql with default autocommit is not inside an explicit transaction block:

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

Do not wrap the statement in BEGIN/COMMIT.

### 4.3. Separating Migrations

If the migration framework is transactional by default, create a separate migration marked non-transactional. Do not simply drop CREATE INDEX CONCURRENTLY into the middle of a migration file that the framework still wraps in a transaction.

### 4.4. Cannot Be Fixed With SAVEPOINT

SAVEPOINT still lives inside a transaction block. It does not bypass this restriction.

### 4.5. Do Not Use a DO Block

Placing CREATE INDEX CONCURRENTLY inside a DO block or function does not make it run outside a transaction. Use a migration runner or connection that executes the statement directly.

## 5. Separating Non-Transactional Migrations

A schema change may require multiple operations, but those operations do not have to live in the same migration.

For example:
1. A transactional migration creates the required table or column.
2. A non-transactional migration creates the index concurrently.
3. A transactional migration adds a constraint or updates metadata once the index is valid.
4. A subsequent migration updates application behavior.

### 5.1. Why Separate Them?

- The framework can toggle transactions at the migration level.
- If the index build fails, other changes are not left half-applied inside the same file.
- Retries and cleanup have a clear scope.
- Deployment logs are easier to read.
- Index builds can run during lower-traffic windows.

### 5.2. Do Not Mix in Transactional DDL

A non-transactional migration executes each statement independently. If a file contains multiple DDLs and a statement midway fails, earlier statements may have already committed. Keep non-transactional migrations short, focused on one index or an independently manageable set of indexes.

### 5.3. Migration State

Frameworks usually record the migration version after the migration completes. Without an enclosing transaction, understand exactly when the migration record is written and how the framework handles failures. Never assume index creation and migration metadata commit atomically together.

### 5.4. One Index per Migration?

This is the safest option, easiest to retry, and clearest to track state. You can group multiple indexes if they are independent and the runner has solid logging/cleanup, provided you account for partial completion.

## 6. Direct SQL Examples

A migration file containing a single statement:

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

With psql:

~~~bash
psql "service=appdb" \
  -v ON_ERROR_STOP=1 \
  -c "CREATE INDEX CONCURRENTLY orders_created_at_idx ON app.orders (created_at);"
~~~

### 6.1. Do Not Pass BEGIN

Do not use a script like:

~~~sql
BEGIN;
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
COMMIT;
~~~

### 6.2. Session Settings

You can set session-level settings before the command if the runner keeps the same connection:

~~~sql
SET application_name = 'migration_create_orders_index';
SET lock_timeout = '5s';
SET statement_timeout = '0';

CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

The SET statements run in individual autocommit transactions when the client has autocommit enabled. If the framework wraps the entire migration in a transaction, these SETs will not solve the problem.

### 6.3. Statement Timeout

statement_timeout=0 disables the session execution time limit in the example above. Use this only if the job runner enforces external timeouts/monitoring and has a runbook to stop the job. A finite timeout comfortably above expected duration can also be appropriate.

### 6.4. psql ON_ERROR_STOP

When running via script, enable ON_ERROR_STOP so psql returns an error if a statement fails. The scheduler must capture the exit code and preserve logs.

## 7. Migration Framework: Rails

Active Record migrations run inside a transaction by default if the adapter/database supports transactional DDL. The PostgreSQL adapter supports transactional DDL, so CREATE INDEX CONCURRENTLY requires disabling the migration transaction for that migration.

~~~ruby
class AddCreatedAtIndexToOrders < ActiveRecord::Migration[7.1]
  disable_ddl_transaction!

  def change
    add_index :orders, :created_at, algorithm: :concurrently
  end
end
~~~

### 7.1. disable_ddl_transaction!

Declared at the migration class level. This is not a SQL command; it is a Rails migration framework directive.

### 7.2. algorithm: :concurrently

The Rails adapter translates the index creation request into SQL matching PostgreSQL's concurrent index build.

### 7.3. Do Not Use Transaction Callbacks

Because the migration has no enclosing transaction, callbacks or other operations inside it are not atomically protected. Keep the migration simple and avoid mixing unrelated changes.

### 7.4. Version Compatibility

Migration class version syntax and adapter behavior depend on your Rails version. Check the Rails documentation/source for the version your project uses before applying.

### 7.5. Revert

A migration using change/add_index lets Rails infer how to revert it, but verify the generated SQL and actual behavior. Dropping an index concurrently must also run outside a transaction.

## 8. Migration Framework: Liquibase

Liquibase allows declaring a changeset to run outside a transaction using runInTransaction=false.

XML example:

~~~xml
<changeSet id="2026-11-add-orders-created-index"
           author="database-team"
           runInTransaction="false">
    <sql>
        CREATE INDEX CONCURRENTLY orders_created_at_idx
        ON app.orders (created_at)
    </sql>
</changeSet>
~~~

### 8.1. A Dedicated Changeset

Place CREATE INDEX CONCURRENTLY in its own changeset and do not mix in other transactional statements.

### 8.2. Failure State

Because the changeset does not run inside a transaction, a failure across multiple statements can leave the database partially applied. Keep the changeset to a single critical statement and inspect DATABASECHANGELOG after a failure.

### 8.3. Rollback

Declare an explicit rollback if required by the framework. If rollback uses DROP INDEX CONCURRENTLY, the rollback changeset must also execute outside a transaction block.

### 8.4. runInTransaction=false Is Not a Guarantee Across Every Tool Wrapper

Verify your Liquibase version, executor, and database extension behavior. Check logs to confirm the framework does not open an outer transaction around the changeset.

## 9. Migration Framework: Flyway

Flyway manages transactions according to migration/database support and allows configuring executeInTransaction on supported versions and configurations.

One way to configure this is setting the non-transactional property per migration using the per-migration configuration mechanism of your Flyway version:

~~~properties
executeInTransaction=false
~~~

### 9.1. Verify Syntax by Version

How per-script configuration is specified and config filenames depend on Flyway version/edition. Check the documentation for your installed version. If the framework lacks per-migration transaction overrides in your setup, use a separate controlled migration runner/command.

### 9.2. A Migration That Only Creates the Index

Example migration SQL:

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

Do not include BEGIN/COMMIT.

### 9.3. Migration History

When a statement fails, inspect schema history and the index catalog. Do not simply re-run migrate immediately; an invalid index may remain with the same name.

### 9.4. Undo

If using Flyway undo migrations, ensure the undo script's transaction configuration is also appropriate when using DROP INDEX CONCURRENTLY. Verify edition/version behavior.

## 10. Migration Framework: Django

Django migrations run inside a transaction by default on PostgreSQL. A migration containing CREATE INDEX CONCURRENTLY must disable the atomic wrapper for that migration.

~~~python
from django.db import migrations

class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("orders", "0042_previous_migration"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX CONCURRENTLY orders_created_at_idx
                ON app_orders (created_at)
            """,
            reverse_sql="""
                DROP INDEX CONCURRENTLY IF EXISTS orders_created_at_idx
            """,
        ),
    ]
~~~

### 10.1. atomic = False

Declared on the migration class. Operations are no longer wrapped in a single migration-level transaction.

### 10.2. Reverse SQL

DROP INDEX CONCURRENTLY also cannot run inside a transaction block. The reverse operation must execute under the same non-atomic setting.

### 10.3. Schema Qualification

Table and index names in examples must match actual schemas/tables and the Django database search path. Use schema-qualified names when needed.

### 10.4. State vs. Database Operation

If the migration only uses RunSQL, ensure Django's migration state reflects the desired indexes and constraints. Use SeparateDatabaseAndState or the appropriate operation if the framework model state needs the corresponding index.

## 11. Migration Framework: Alembic/SQLAlchemy

Alembic usually runs migrations inside a transaction. You can use autocommit_block to execute commands requiring autocommit mode.

~~~python
from alembic import op

def upgrade():
    with op.get_context().autocommit_block():
        op.execute("""
            CREATE INDEX CONCURRENTLY orders_created_at_idx
            ON app.orders (created_at)
        """)

def downgrade():
    with op.get_context().autocommit_block():
        op.execute("""
            DROP INDEX CONCURRENTLY IF EXISTS app.orders_created_at_idx
        """)
~~~

### 11.1. autocommit_block

Alembic's autocommit block can commit any open transaction before entering the block. Earlier operations in the same migration may have already committed separately. Therefore, placing concurrent index builds in standalone migrations is easier to control.

### 11.2. SQLAlchemy Connection

Ensure the connection truly operates with autocommit isolation behavior inside the block. Do not open an outer transaction wrapper externally.

### 11.3. Downgrade

Downgrade also requires an autocommit block for DROP INDEX CONCURRENTLY. Verify the exact object name and schema.

### 11.4. Version Compatibility

APIs and behavior depend on Alembic/SQLAlchemy versions. Check project documentation and test on a database clone.

## 12. Other Frameworks or Custom Migration Runners

If your framework lacks a non-transactional directive:
- Create a separate deployment step.
- Open a dedicated autocommit connection.
- Issue CREATE INDEX CONCURRENTLY directly.
- Wait for the command to finish.
- Verify the index is valid.
- Only then mark the migration step complete.

### 12.1. Do Not Use a Default Transactional Connection Pool

Some application libraries open transactions automatically or keep connections inside a transaction scope. Use a dedicated connection and verify transaction state.

### 12.2. Checking Transaction State

Within the session, you can check:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    application_name
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
~~~

A NULL xact_start signals the session has no open transaction at the moment of observation; combine this with runner behavior and server logs.

### 12.3. Runner Contract

The runner should support:
- Non-transactional migration metadata.
- Configurable timeouts.
- Logging stdout/stderr.
- Clear exit statuses.
- No blind retries.
- Concurrency locking across deployment instances.
- Index validity checks before marking complete.

## 13. Monitoring Progress With pg_stat_progress_create_index

PostgreSQL provides pg_stat_progress_create_index to observe running index builds.

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    lockers_total,
    lockers_done,
    current_locker_pid,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index
ORDER BY pid;
~~~

Columns can vary across PostgreSQL major versions. Use SELECT * or inspect the catalog view definition on your specific version before building fixed dashboards.

### 13.1. Common Phases

A concurrent index build can pass through phases such as:
- initializing.
- waiting for writers before build.
- building index.
- waiting for writers before validation.
- index validation: scanning index.
- index validation: sorting tuples.
- index validation: scanning table.
- waiting for old snapshots.

Exact phase names depend on version and index type.

### 13.2. blocks_done and blocks_total

Indicates block scan progress during the corresponding phase. Not every phase has a meaningful progress denominator.

### 13.3. tuples_done and tuples_total

Can show tuple processing progress during certain phases. Do not interpret a single pair of counters as overall job percentage across phase transitions.

### 13.4. lockers_total and lockers_done

Shows the number of lockers/transactions to wait on per phase. If the job stalls in a waiting phase, inspect current_locker_pid and the associated transaction.

### 13.5. No Rows Returned

If the view returns no rows, either no index build is running, the command has finished, or visibility permissions are insufficient. Never assume the job succeeded simply because the view is empty; check pg_index.

## 14. Understanding Concurrent Build Phases

A concurrent build adds extra steps so DML can keep running while the index is constructed.

### 14.1. Initializing

PostgreSQL prepares catalog/index build state and determines required conditions.

### 14.2. Waiting for Writers Before Build

Waits for relevant active writing transactions to finish so the scan begins from a consistent state.

### 14.3. Building Index

PostgreSQL scans the table and creates index entries for existing data. DML can still proceed; concurrent modifications are tracked by the concurrent build mechanism.

### 14.4. Waiting for Writers Before Validation

Waits for transactions that could affect the validation phase to finish.

### 14.5. Index Validation

PostgreSQL checks index contents against the table and reconciles entries modified during the build. This is why an extra scan and validation occur.

### 14.6. Waiting for Old Snapshots

PostgreSQL may have to wait until older snapshots are no longer in use before marking the index valid. Long-running transactions can prolong this phase.

### 14.7. Jobs Can Run Long Even at 100% Blocks

Some phases are wait phases or catalog transitions. Reaching 100% on blocks_done/blocks_total does not mean the entire command has completed.

## 15. Inspecting the Index After Build

pg_index stores metadata about index state.

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive,
    i.indisunique,
    i.indisprimary
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE idx.relname = 'orders_created_at_idx';
~~~

### 15.1. indisready

Indicates whether the index is ready to be maintained by INSERT/UPDATE/DELETE operations.

### 15.2. indisvalid

Indicates whether the planner can use the index as a valid index. After a successful build, the index must have indisvalid=true.

### 15.3. indislive

Indicates whether the index is live in its lifecycle. An index currently being dropped may show a different state.

### 15.4. Verifying the Definition

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND indexname = 'orders_created_at_idx';
~~~

Do not check only the index name. Verify columns, expressions, predicate, access method, uniqueness, and included columns match what the migration intended.

### 15.5. A Valid Index Does Not Prove Queries Use It

The planner may still choose a sequential scan if the table is small or a query reads many rows. Verify EXPLAIN plans and real workloads.

## 16. Handling Invalid Indexes After Failure

CREATE INDEX CONCURRENTLY can fail due to duplicate keys, cancellation, deadlock/lock timeout, server restart, disk exhaustion, or I/O errors. When this happens, PostgreSQL can leave behind an invalid index.

### 16.1. Finding Invalid Indexes

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive,
    i.indisunique
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
ORDER BY 1, 2, 3;
~~~

### 16.2. Invalid Indexes Still Consume Storage

An invalid index can persist and occupy disk space. If indisready=true, PostgreSQL may continue maintaining the index during DML even though the planner does not use it.

### 16.3. Unique Invalid Indexes Require Extra Care

With CREATE UNIQUE INDEX CONCURRENTLY, uniqueness checks can begin before the index is marked valid. If the build fails during a late phase, the invalid index may continue enforcing uniqueness. Inspect indisready, indisvalid, and the original error before dropping.

### 16.4. Do Not Retry Blindly

If the migration re-runs with the same index name, the command may report that the relation already exists. Check whether that index is valid/invalid, whether its definition matches, and the state of migration history.

### 16.5. Cleanup

If you decide to remove the invalid index, you can use:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS app.orders_created_at_idx;
~~~

DROP INDEX CONCURRENTLY also cannot run inside a transaction block. It has its own restrictions, including disallowing CASCADE and not being able to drop an index backing a constraint in the standard way.

### 16.6. After Cleanup

- Confirm the index no longer appears in pg_class/pg_indexes.
- Verify migration state.
- Identify the root cause of the failure.
- Fix duplicate data or capacity/lock issues.
- Re-run the migration in a non-transactional session.
- Verify the index is valid.

## 17. Concurrent Unique Indexes

Unique indexes are often needed to enforce business keys. You can build a unique index concurrently to minimize write blocking.

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY users_email_key_idx
    ON app.users (email);
~~~

### 17.1. Duplicate Data

If the table already contains duplicate values for the unique key, the build will fail. Before running, check:

~~~sql
SELECT
    email,
    count(*) AS occurrences
FROM app.users
GROUP BY email
HAVING count(*) > 1
ORDER BY occurrences DESC
LIMIT 100;
~~~

Adjust this query for composite keys, expressions, collation, NULL semantics, and partial predicates matching the index definition.

### 17.2. Race Conditions

Pre-checking duplicates does not guarantee the build will succeed. Application writes continue during the concurrent build; the unique index checks changes throughout its lifecycle and can error if a duplicate appears.

### 17.3. Uniqueness Enforcement Timing

During a concurrent unique build, PostgreSQL begins enforcing uniqueness against other transactions before the index is marked valid. Thus, the application can receive unique violations while the migration is still in the build/validation phase.

### 17.4. NULL Semantics

Unique indexes permit multiple NULL values by default per standard SQL semantics. PostgreSQL provides the NULLS NOT DISTINCT option in supported versions to treat NULLs as equal for uniqueness. Verify your version and business requirements.

### 17.5. Composite Unique Indexes

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY orders_tenant_external_id_idx
    ON app.orders (tenant_id, external_id);
~~~

Uniqueness applies across the combination of columns. Duplicate pre-checks must group by the same column list.

## 18. Creating a Constraint From a Unique Index

Some schema changes require a unique constraint in the catalog, not just a unique index. You can build the unique index concurrently first and then attach a constraint via ALTER TABLE ... ADD CONSTRAINT ... USING INDEX.

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY users_email_key_idx
    ON app.users (email);

ALTER TABLE app.users
    ADD CONSTRAINT users_email_key
    UNIQUE USING INDEX users_email_key_idx;
~~~

### 18.1. Two Steps With Different Transaction Behavior

CREATE UNIQUE INDEX CONCURRENTLY runs outside a transaction block. ALTER TABLE ADD CONSTRAINT USING INDEX can run in a separate transactional migration according to appropriate lock behavior and framework rules.

### 18.2. Lock During Attach

ALTER TABLE still needs a lock to update catalog/constraint state. Duration is usually much shorter than building the index, yet it can wait on locks. Set lock_timeout and watch blockers.

### 18.3. Index Requirements

The index must qualify for constraint backing—for example, a suitable unique B-tree index, not a partial index or expression index where constraints disallow them. Consult the documentation for your version and constraint type.

### 18.4. Index/Constraint Naming

PostgreSQL may rename the index to match the constraint name when attaching if the names differ. Pick clear names and verify after DDL.

### 18.5. Primary Keys

To create a primary key from an index, the index must also meet NOT NULL requirements on key columns and primary key rules. If columns are not yet NOT NULL, design a separate migration to avoid unexpected scans or locks.

## 19. Partial Indexes and Expression Indexes

Concurrent builds support many of the same index definitions as standard index creation, though semantics and query patterns should be considered.

### 19.1. Partial Index

~~~sql
CREATE INDEX CONCURRENTLY orders_open_created_idx
    ON app.orders (created_at)
    WHERE status = 'open';
~~~

The index only contains rows matching the predicate. The planner must be able to prove the query predicate is compatible to use the index.

### 19.2. Expression Index

~~~sql
CREATE INDEX CONCURRENTLY users_lower_email_idx
    ON app.users (lower(email));
~~~

Application queries should use the matching expression, such as WHERE lower(email) = lower($1).

### 19.3. Unique Partial Index

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY active_users_email_idx
    ON app.users (email)
    WHERE deleted_at IS NULL;
~~~

Uniqueness enforcement applies only to rows matching the predicate.

### 19.4. Included Columns

~~~sql
CREATE INDEX CONCURRENTLY orders_customer_created_idx
    ON app.orders (customer_id, created_at)
    INCLUDE (status, total_amount);
~~~

INCLUDE can enable index-only scans for certain workloads, but increases index size and write costs. Benchmark before adding many included columns.

### 19.5. Collation and Operator Class

Index behavior depends on data type, collation, and operator class. Use a definition compatible with your query operators and locale semantics.

## 20. Partitioned Tables

Concurrent index creation on a partitioned parent has limitations depending on PostgreSQL major version. In many versions, CREATE INDEX CONCURRENTLY directly on a partitioned table is not supported.

A common strategy is:
1. Create the index concurrently on each leaf partition.
2. Verify child indexes are valid and have matching definitions.
3. Create the partitioned index on the parent using the appropriate attach operation.
4. Verify the parent/child index hierarchy.

### 20.1. Leaf Partition Example

~~~sql
CREATE INDEX CONCURRENTLY orders_2026_10_customer_idx
    ON app.orders_2026_10 (customer_id);
~~~

### 20.2. Creating the Parent Index

~~~sql
CREATE INDEX orders_customer_idx
    ON ONLY app.orders (customer_id);
~~~

ONLY creates a partitioned parent index without building on partitions automatically. Then attach child indexes:

~~~sql
ALTER INDEX app.orders_customer_idx
    ATTACH PARTITION app.orders_2026_10_customer_idx;
~~~

Once all required partitions have matching indexes attached, the parent index can become valid per PostgreSQL semantics.

### 20.3. Names and Definitions

Child indexes must be compatible with the parent index definition: key columns, expressions, operator classes, collations, sort options, and predicates as required. Check before attaching.

### 20.4. Multi-Level Partitioning

If subpartitioning exists, plan for each leaf index and hierarchy level. Do not verify only a single parent-child level.

### 20.5. New Partitions After Migration

New partitions need matching indexes. Partition-provisioning automation must create/attach indexes before a partition receives significant workload.

### 20.6. Version Caveat

Support for direct concurrent builds on partitioned tables and related utilities can vary by major version. Read the documentation for your exact server version before choosing a strategy.

## 21. IF NOT EXISTS and Idempotency

You can write:

~~~sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_created_at_idx
    ON app.orders (created_at);
~~~

However, IF NOT EXISTS only suppresses an error when a relation with the same name already exists. It does not verify that the existing index has the same definition.

### 21.1. Wrong index with same name

If an index shares the name but has different columns, predicate, or uniqueness, the command silently skips and the migration appears to succeed. Application queries remain unoptimized or uniqueness remains unenforced.

### 21.2. Verify Definition

Use pg_get_indexdef:

~~~sql
SELECT
    c.oid::regclass AS index_name,
    pg_get_indexdef(c.oid) AS definition,
    i.indisready,
    i.indisvalid
FROM pg_class AS c
JOIN pg_index AS i ON i.indexrelid = c.oid
WHERE c.oid = 'app.orders_created_at_idx'::regclass;
~~~

If the object does not exist, casting to regclass errors; use to_regclass to query safely:

~~~sql
SELECT to_regclass('app.orders_created_at_idx');
~~~

### 21.3. Migration Idempotency

Idempotency must include:
- Checking migration history.
- Checking index existence.
- Checking definition.
- Checking validity and readiness.
- Cleaning up invalid leftovers.
- Marking complete only after verification.

### 21.4. Do Not Use IF NOT EXISTS to Mask Failures

If a prior build failed and left an invalid index, IF NOT EXISTS can cause the migration runner to skip over it. Always inspect pg_index.

## 22. Lock and Statement Timeouts for Migrations

Choose timeouts based on operational goals rather than using one fixed value for every index.

### 22.1. lock_timeout

Prevents the migration from waiting too long on lock acquisition. If it times out, the job fails fast so it can retry in another window.

### 22.2. statement_timeout

Concurrent builds on large tables can run long. Too short a timeout cancels the build mid-flight and can leave an invalid index. Choose a value based on measured build duration, or manage timeouts in the job runner.

### 22.3. idle_in_transaction_session_timeout

The migration runner should never leave a session idle in transaction. Although concurrent builds must run outside transactions, a buggy wrapper could leave a transaction/session open holding locks or snapshots. Monitor runner connections.

### 22.4. application_name

Set an identifiable application_name, such as schema-migration:create-orders-index, for visibility in pg_stat_activity and logs.

### 22.5. Cancel Behavior

If a command is canceled, inspect pg_index afterward. Never assume cancellation cleaned up all catalog or file artifacts.

## 23. Monitoring Blockers and Long-Running Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### 23.1. Idle in Transaction

An idle-in-transaction session can hold an old snapshot and cause a concurrent index build to stall in the waiting for old snapshots phase.

### 23.2. Blocking PID

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    blocking.pid AS blocking_pid,
    blocking.application_name,
    blocking.state,
    blocking.xact_start,
    left(blocking.query, 500) AS blocking_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocking_pid)
JOIN pg_stat_activity AS blocking
  ON blocking.pid = p.blocking_pid;
~~~

This query identifies lock blockers at the moment captured; a concurrent build can wait on snapshots or transactions without showing up as a simple lock wait. Combine with the phase in pg_stat_progress_create_index.

### 23.3. Never Terminate Blockers Arbitrarily

Terminating a session can roll back an application transaction and trigger a retry storm. Identify the owner/business impact, then request commit/rollback or act per incident policy.

## 24. WAL, Disk, and I/O During Concurrent Builds

CREATE INDEX CONCURRENTLY reads the table multiple times, writes index pages, and generates WAL. Since DML continues concurrently, peak I/O can be higher than an index build during a quiet maintenance window.

### 24.1. Disk Headroom

Account for the new index size, temporary sort files, WAL, archive backlog, and replication retention. Do not run when volumes are near capacity.

### 24.2. WAL Generation

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
~~~

Take snapshots before and after to compute the wal_bytes delta. pg_stat_wal exists since PostgreSQL 14; check your version.

### 24.3. Replication Lag

Concurrent index builds can generate WAL that slows down standbys and CDC consumers. Monitor pg_stat_replication, replication slots, and archiving.

### 24.4. Temporary Files

Index builds may require sort/temp storage depending on access method and settings. Monitor temp_bytes, temp_files, and filesystem usage.

### 24.5. I/O Scheduling

Do not stack multiple concurrent index builds, full backups, and bulk loads on the same storage without benchmarking. Only run one build per table; builds across multiple tables can still contend for I/O.

## 25. Migration Ordering in Expand-and-Contract

When adding an index to support new queries, deploy in a safe order.

### 25.1. Expand

1. Review query patterns and index definition.
2. Create the index concurrently via a non-transactional migration.
3. Verify the index is valid.
4. Verify query plans and latency.

### 25.2. Deploy Application

Deploy code using the new queries after the index is ready if performance relies on that index. For unique indexes, the application must be ready to handle unique violations as soon as enforcement begins.

### 25.3. Contract

If an old index is no longer needed:
1. Verify the new index is being used.
2. Observe across a full workload cycle.
3. Check constraints and dependencies.
4. Drop the old index using DROP INDEX CONCURRENTLY in a dedicated non-transactional migration.

### 25.4. Avoid Simultaneous Deployment

If application deployment and the index build run in parallel, new queries may execute before the index is valid. Enforce deployment dependencies or feature flags.

### 25.5. Indexes Are Not Contract Logic

Indexes alter performance and uniqueness behavior, but do not replace application validation, data migrations, or business constraints on their own.

## 26. Creating Concurrent Indexes for Foreign Key Lookups

PostgreSQL does not automatically create an index on referencing columns when declaring a foreign key. Joins, deletes, or updates on the referenced table may benefit from an index on the foreign-key columns.

~~~sql
CREATE INDEX CONCURRENTLY orders_customer_id_idx
    ON app.orders (customer_id);
~~~

### 26.1. Not Every Foreign Key Needs an Index

Evaluate query patterns, table size, parent deletes/updates, and write overhead. Extra indexes increase storage and DML cost.

### 26.2. Composite Foreign Keys

Create the index with column order aligned to predicates and joins. Evaluate both foreign-key column order and query access patterns.

### 26.3. Unique Constraints

Foreign key referenced columns require a suitable unique or primary key; an index on referencing columns only speeds lookups/joins and does not create a constraint.

## 27. Concurrent Index Builds in Production

Before running:
- Confirm table size and expected build duration.
- Check for active transactions and long snapshots.
- Verify no other concurrent build is running on the same table.
- Check disk, WAL, and replication headroom.
- Verify framework non-transactional configuration.
- Define timeouts and cancel policy.
- Notify owners and establish the maintenance window.
- Confirm logs and monitoring are active.

While running:
- Monitor pg_stat_progress_create_index.
- Monitor pg_stat_activity, blockers, and wait events.
- Monitor disk, I/O, WAL, and replication lag.
- Do not start competing DDL on the same table.
- Do not mark the migration complete before the command finishes.

After running:
- Verify pg_index indisready/indisvalid.
- Verify pg_get_indexdef.
- Verify migration history.
- Verify query plans and application behavior.
- Monitor storage and replication post-build.
- Record results in the change record.

## 28. Failure Modes and Remediation

| Failure | Symptom | Remediation |
| --- | --- | --- |
| Transaction block | Server reports command cannot run inside a transaction | Disable wrapper, run separately |
| Lock timeout | Lock acquisition timeout | Find blocker, retry in controlled manner |
| Statement timeout/cancel | Client/server reports cancellation | Inspect invalid index and build state |
| Duplicate key | Unique index build fails | Locate and resolve duplicate rows |
| Disk full | No space left / I/O errors | Pause heavy load, safely expand/free storage |
| Server restart | Connection lost, job interrupted | Check index state and migration history |
| Invalid index leftover | indisvalid=false | Assess readiness/uniqueness, clean up or repair |
| Same-name index | Relation already exists or IF NOT EXISTS skipped | Compare definition and validity |
| Long snapshot wait | Progress phase waiting for old snapshots | Locate old transaction and handle per policy |
| Replica lag | Standby/CDC lag rises | Throttle concurrent load, address consumer/storage |

### 28.1. Migration Runner Times Out While Server Command Keeps Running?

A client timeout or connection drop does not always prove the backend stopped immediately. Check pg_stat_progress_create_index and pg_stat_activity before retrying.

### 28.2. Job Completes but Migration Record Is Missing

The command may have succeeded while the runner lost connection before writing history. Verify index definition/validity, then reconcile migration state per framework rules. Never re-run blindly.

### 28.3. Migration Record Complete While Index Is Invalid

Treat this as a deployment incident. Determine whether the framework wrote the record before completion, inspect index state, and assess application impact.

## 29. Runbook: Creating an Index Concurrently

1. Review index definition, columns, predicate, access method, and expected benefit.
2. Check for duplicate data if creating a unique index.
3. Verify no other concurrent build is active on the same table.
4. Check for long-running transactions and idle-in-transaction sessions.
5. Verify free disk, WAL/archiving, temp storage, and replication lag.
6. Create a separate non-transactional migration.
7. Configure appropriate lock_timeout and job timeout.
8. Run CREATE INDEX CONCURRENTLY.
9. Monitor progress phases.
10. Wait for completion and verify exit status.
11. Verify indisready=true and indisvalid=true.
12. Verify pg_get_indexdef matches expectations.
13. Run EXPLAIN and query smoke tests.
14. Update migration history/change record.
15. Monitor query latency, WAL, and replica lag.

## 30. Runbook: Migration Fails Leaving an Invalid Index

1. Do not retry immediately.
2. Confirm whether the backend is still running or has terminated.
3. Read migration logs and PostgreSQL logs.
4. Inspect pg_index flags.
5. Inspect index definition and size.
6. For unique indexes, assess active uniqueness enforcement.
7. Find duplicate rows if the error involves uniqueness.
8. Determine whether migration history was recorded.
9. Choose DROP INDEX CONCURRENTLY on the invalid index or a supported repair path.
10. Confirm cleanup completed.
11. Fix the root cause.
12. Re-run the non-transactional migration.
13. Verify the index is valid and application behavior is healthy.

## 31. Runbook: Blocked Migration

1. Identify the PID and phase in pg_stat_progress_create_index.
2. Check current_locker_pid if populated.
3. Inspect pg_stat_activity and transaction ages.
4. Identify the blocker owner/application.
5. Check for competing DDL or maintenance jobs.
6. Assess the impact of canceling the migration vs. the blocker.
7. Request the blocker to finish its transaction if appropriate.
8. Use cancel/terminate only per incident policy.
9. Check index state after the build stops.
10. Adjust schedule/timeouts and retry.

## 32. Testing Migrations on Staging

A good rehearsal mirrors production in:
- PostgreSQL major version.
- Table size and row distribution.
- Index definitions and collations.
- Concurrent write rate.
- Long-running transactions.
- Storage IOPS/throughput.
- Replication/CDC topology.
- Migration framework version and config.
- Deployment orchestration.

### 32.1. Measuring Duration

Record per-phase durations where visible, total duration, wait time, scan time, and verification time.

### 32.2. Measuring Application Impact

Compare p50/p95/p99 latency, error rate, connection pool wait, and throughput before, during, and after the build.

### 32.3. Measuring Storage Impact

Monitor IOPS, throughput, free disk, WAL bytes/sec, temp files, and replica lag.

### 32.4. Failure Rehearsal

Test cancellation, lock timeouts, or runner interruptions in staging to practice invalid-index cleanup and migration history reconciliation.

## 33. Common Anti-Patterns

| Anti-pattern | Consequence | Correct approach |
| --- | --- | --- |
| Putting CREATE INDEX CONCURRENTLY in a migration transaction | Rejected by PostgreSQL | Mark migration non-transactional |
| Disabling transactions for a multi-DDL file | Can leave partial state applied | One short migration for the index |
| Using IF NOT EXISTS and skipping validation | Can retain wrong or invalid index | Verify definition and indisvalid |
| Retrying immediately after timeout | Can collide with running build or invalid index | Inspect backend and catalog first |
| Running multiple concurrent builds on the same table | PostgreSQL disallows concurrent builds on the same table | Serialize them |
| Assuming concurrent means lock-free | DDL/transactions can still block | Monitor locks and snapshots |
| Too-short statement timeout | Build canceled, invalid index left behind | Use an appropriate runtime budget |
| Skipping duplicate check before unique build | Migration can fail | Pre-check and clean duplicates |
| Assuming pre-check guarantees uniqueness | Concurrent DML can still insert duplicates | Let unique build enforce and handle races |
| Dropping invalid unique index without assessment | Can drop active uniqueness enforcement | Check phase/readiness and business risk |
| Ignoring migration history | Database and migration metadata drift | Reconcile against catalog |
| Unsupported concurrent build on partitioned parent | Migration fails | Build leaf indexes and attach to parent per version |
| Dropping index backing a constraint | DDL blocked or unintended constraint change | Drop constraint per plan |
| Ignoring WAL/disk | Volume fills mid-build | Enforce capacity gates |
| Ignoring replica lag | Consumers/standbys fall behind | Monitor WAL and slots |
| Running index build alongside major backup | Storage contention | Schedule and budget I/O |
| Deploying queries before index is valid | Poor query plans/latency | Enforce schema-to-app deploy dependencies |
| Not testing rollback | Rollback migration fails due to transaction wrapper | Test DROP INDEX CONCURRENTLY outside transaction |

## 34. PostgreSQL Hands-On Exercises

Perform on a lab/staging or database clone. Do not build large indexes or cancel migrations in production purely for practice.

1. **Baseline:** create a moderately large table and record baseline DML throughput.
2. **Regular build:** run CREATE INDEX in the lab while writes pause.
3. **Concurrent build:** run CREATE INDEX CONCURRENTLY on the same dataset.
4. **Compare:** compare duration and DML availability.
5. **Transaction error:** test CREATE INDEX CONCURRENTLY inside BEGIN/COMMIT and read the error.
6. **Autocommit:** run the same command in psql autocommit mode.
7. **Progress:** open pg_stat_progress_create_index in another session.
8. **Phases:** observe the phases of a concurrent build.
9. **Lock:** create a long transaction and see whether the build must wait.
10. **Blocker:** use pg_blocking_pids to find the blocker during a lock wait.
11. **Old snapshot:** create a long-lived snapshot transaction and observe the waiting phase.
12. **Lock timeout:** set a short lock_timeout in the lab and observe the failure.
13. **Statement timeout:** set a timeout short enough to cancel a test build.
14. **Invalid index:** inspect the invalid index left behind after failure.
15. **Readiness:** compare indisready and indisvalid.
16. **Definition:** inspect pg_get_indexdef after build.
17. **IF NOT EXISTS:** create an index with the same name but different definition and observe behavior.
18. **Idempotency:** write a preflight check verifying existence, definition, and validity.
19. **Rails:** create a migration using disable_ddl_transaction!.
20. **Rails adapter:** verify algorithm: :concurrently produces the right SQL.
21. **Liquibase:** write a changeset with runInTransaction=false.
22. **Liquibase failure:** simulate an error and inspect DATABASECHANGELOG.
23. **Flyway:** configure executeInTransaction=false for your Flyway version.
24. **Flyway history:** simulate command success with runner connection loss and reconcile history.
25. **Django:** create an atomic=False migration with RunSQL.
26. **Django reverse:** write reverse_sql using DROP INDEX CONCURRENTLY.
27. **Alembic:** use autocommit_block for CREATE INDEX CONCURRENTLY.
28. **Alembic downgrade:** use autocommit_block for DROP INDEX CONCURRENTLY.
29. **Custom runner:** write a psql script that does not open a transaction.
30. **Exit status:** configure ON_ERROR_STOP and verify the scheduler exit code.
31. **Unique index:** create a unique index concurrently on a column with no duplicates.
32. **Duplicate check:** create duplicate rows and write a pre-check query.
33. **Concurrent race:** attempt inserting a duplicate during a unique build in the lab.
34. **Unique failure:** observe the invalid unique index after failure.
35. **Unique readiness:** check whether the index still enforces uniqueness when indisvalid=false and indisready=true.
36. **Composite unique:** create a unique index across two columns.
37. **NULL semantics:** test a default unique index with multiple NULLs.
38. **NULLS NOT DISTINCT:** test on a supported version and compare.
39. **Partial index:** create a partial index concurrently.
40. **Expression index:** create an index on lower(email).
41. **Included columns:** create a covering index with INCLUDE.
42. **Foreign key lookup:** add an index concurrently on referencing columns.
43. **Constraint attach:** create a unique index concurrently and run ADD CONSTRAINT USING INDEX.
44. **Attach lock:** measure locks during constraint attachment.
45. **Primary key:** study the conditions for turning an index into a primary key.
46. **Partition leaf:** create an index concurrently on a leaf partition.
47. **Parent index:** create a partitioned index on ONLY the parent in the lab.
48. **Attach partition:** attach a child index to the parent index.
49. **Partition version:** verify capabilities of your running major version.
50. **Multiple builds:** attempt two concurrent builds on the same table and observe behavior.
51. **Different tables:** benchmark concurrent builds across two separate tables.
52. **WAL:** measure the wal_bytes delta during an index build.
53. **Temp:** monitor temp_files/temp_bytes during a build.
54. **Disk:** measure filesystem free bytes before, during, and after a build.
55. **Replication:** monitor pg_stat_replication during a concurrent build.
56. **Slot retention:** check whether replication slots retain extra WAL during a build.
57. **I/O:** use pg_stat_io or host metrics to measure I/O.
58. **Application latency:** benchmark p95/p99 while a build runs.
59. **Index plan:** EXPLAIN a query before and after the index becomes valid.
60. **Query use:** verify the planner can use the index after the build.
61. **Cancel:** cancel a build from another session in the lab.
62. **Runner timeout:** simulate a client timeout and check whether the server command is still running.
63. **Cleanup:** run DROP INDEX CONCURRENTLY on an invalid index.
64. **Drop transaction:** attempt DROP INDEX CONCURRENTLY inside a transaction and read the error.
65. **Constraint dependency:** attempt to drop an index backing a constraint and observe the restriction.
66. **Lock timeout retry:** write a retry policy with backoff.
67. **Advisory lock:** prevent two deployment instances from running the migration simultaneously.
68. **Migration history:** design reconciliation when the index is valid but the migration record is missing.
69. **Non-transactional batch:** intentionally put two statements, make the second fail, and analyze partial state.
70. **Single-index migration:** split two concurrent index builds into separate migrations.
71. **Expand-contract:** deploy an index before an application query change.
72. **Drop old index:** write a non-transactional migration using DROP INDEX CONCURRENTLY.
73. **Capacity gate:** block the build when free disk falls below reserve.
74. **Timeout policy:** select lock_timeout/statement_timeout based on staging measurements.
75. **Long transaction runbook:** simulate reporting sessions that prolong a concurrent build.
76. **Failure runbook:** write an invalid-index handling procedure.
77. **Staging rehearsal:** run the migration at production-like table size.
78. **Framework audit:** verify your framework has no unexpected transaction wrapper.
79. **Verification:** automate checks for index definition, indisready, indisvalid, and migration history.
80. **Capstone design:** design a production index deployment workflow using a non-transactional migration covering preflight, framework config, concurrency control, progress monitoring, WAL/disk gates, failure cleanup, post-build verification, and application rollout.

## 35. Deployment Checklist

### Before Migration

- [ ] Confirm exact table, schema, and index definition.
- [ ] Review query plans and rationale for the index.
- [ ] Check for duplicate data if the index is unique.
- [ ] Check for long-running transactions and DDL blockers.
- [ ] Verify table size, disk headroom, WAL, and temp capacity.
- [ ] Check replication and archive health.
- [ ] Verify PostgreSQL major version and partition limitations.
- [ ] Create a dedicated migration for the concurrent index build.
- [ ] Configure the framework to run outside a transaction.
- [ ] Set timeouts and retry/stop policies.
- [ ] Complete staging rehearsal and assign an owner.

### During Migration

- [ ] Runner opens no transaction block.
- [ ] Only one concurrent build runs per table at a time.
- [ ] application_name identifies the migration.
- [ ] Monitor pg_stat_progress_create_index.
- [ ] Monitor blockers, I/O, WAL, disk, and replication lag.
- [ ] Do not mark migration complete before command finishes.
- [ ] Capture logs and exit status.

### After Migration

- [ ] indisready=true.
- [ ] indisvalid=true.
- [ ] Definition matches requirements.
- [ ] Migration history is synchronized.
- [ ] Query plans and application smoke tests pass.
- [ ] Replication, archiving, and disk are stable.
- [ ] Invalid leftovers are cleaned up.
- [ ] Change record captures outcome and duration.

### On Failure

- [ ] Confirm backend has stopped.
- [ ] Inspect index catalog state.
- [ ] Check uniqueness enforcement if unique index.
- [ ] Do not retry blindly.
- [ ] Clean up outside a transaction if needed.
- [ ] Resolve the root cause.
- [ ] Reconcile migration metadata.
- [ ] Re-run and verify from the start.

## 36. Summary

CREATE INDEX CONCURRENTLY is an essential tool for evolving schemas on production tables actively receiving writes. It minimizes DML blocking, but requires the migration runner to respect transaction boundaries and follow structured failure handling.

~~~text
PREPARE
  definition / duplicates / capacity / blockers
       |
       v
NON-TRANSACTIONAL MIGRATION
  CREATE INDEX CONCURRENTLY
       |
       v
MONITOR
  progress phases / waits / WAL / disk / replicas
       |
       v
VERIFY
  indisready = true
  indisvalid = true
  definition matches
       |
       v
DEPLOY DEPENDENT APPLICATION CHANGE
       |
       v
RECORD AND MONITOR
~~~

Core principles:

- **CREATE INDEX CONCURRENTLY cannot run inside a transaction block.** Disable transaction wrappers at the migration/framework level and run the statement directly.
- **Isolate concurrent index builds into their own migrations.** Once non-transactional, statements no longer roll back atomically together.
- **Concurrent does not mean lock-free.** Long transactions, old snapshots, and competing DDL can still prolong or block the build.
- **Monitor progress phases.** pg_stat_progress_create_index distinguishes scan work from wait phases.
- **Verify indisready and indisvalid.** Index name or migration history alone does not prove an index is usable.
- **Invalid indexes require deliberate handling.** For unique indexes, assess active uniqueness enforcement before dropping.
- **IF NOT EXISTS does not verify definitions.** Inspect pg_get_indexdef and catalog state before treating a migration as complete.
- **Unique indexes can encounter duplicates while writes continue.** Pre-checks help, but do not eliminate race conditions.
- **Partitioned tables require version-aware planning.** You may need to build indexes concurrently on each leaf and attach them to the parent.
- **Account for disk, WAL, and replication impact.** Builds can run long, saturate I/O, and lag consumers.
- **Rollbacks must also be non-transactional when using DROP INDEX CONCURRENTLY.** Test both upgrade and downgrade paths.
- **Migration history must be reconciled after failures.** A client timeout does not prove the backend stopped or the index was removed.

A sound workflow introduces indexes into production while preserving DML availability, enforcing transaction boundaries, catching failures early, and marking migrations complete only after the index is verified valid.
