# DDL in Transactions and Command Exceptions in PostgreSQL

PostgreSQL supports transactional DDL for most schema modification operations. This means a group of commands such as regular `CREATE TABLE`, `ALTER TABLE`, `CREATE VIEW`, or `DROP INDEX` can run inside a transaction; if the transaction rolls back, the corresponding catalog changes are undone as well. This is a major advantage when deploying migrations: schema and data can be modified together as a consistent unit.

However, **not every administrative or DDL command can run inside a transaction block**. Some commands interact with the database cluster, filesystem, server configuration, or replication slots outside the current transaction. Commands such as `CREATE DATABASE`, `CREATE TABLESPACE`, `ALTER SYSTEM`, `VACUUM`, and the `CREATE INDEX CONCURRENTLY` variants have special rules. If a migration framework automatically wraps the entire script in `BEGIN`/`COMMIT`, these commands will fail.

In addition, two kinds of exceptions must be distinguished:

- **Commands prohibited inside a transaction block:** PostgreSQL rejects them immediately upon detecting an open transaction block.
- **Commands allowed inside a transaction that can fail:** an SQL error puts the transaction into an aborted state. To continue, you must `ROLLBACK` the entire transaction or `ROLLBACK TO SAVEPOINT` created beforehand.

A safe migration must know which commands can be grouped atomically, which must run standalone, how to handle errors, and how to verify state after a long or concurrent operation fails.

~~~text
                  Schema migration
                         |
              +----------+-----------+
              |                      |
              v                      v
       Transactional DDL       Non-transactional
       BEGIN / COMMIT          command / operation
              |                      |
       +------+-------+         +----+------+
       |              |         |           |
       v              v         v           v
    Success          Error    Run outside   External
       |              |       transaction   side effects
       v              v         |           |
     COMMIT      ROLLBACK /     v           v
                 SAVEPOINT   Verify state, cleanup,
                             retry or continue
~~~

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Schema Migrations** chapter, covering the topic **"DDL in Transactions and Command Exceptions"**. The content explains transactional DDL, savepoints, the transaction-aborted state, the list of commands with exceptions, concurrent index operations, PL/pgSQL exception blocks, transaction control in procedures, and how to organize production migrations.

---

## 1. Learning Objectives

After this lesson, you can:

1. Explain transactional DDL in PostgreSQL.
2. Distinguish between a transaction block, an implicit transaction, and autocommit.
3. Execute `CREATE`/`ALTER`/`DROP` on schema objects inside a transaction.
4. Roll back DDL when a migration fails.
5. Use `SAVEPOINT` and `ROLLBACK TO SAVEPOINT` to recover part of a transaction.
6. Explain why an SQL error transitions a transaction into the aborted state.
7. Identify commands that are prohibited inside a transaction block.
8. Distinguish between regular `CREATE INDEX` and `CREATE INDEX CONCURRENTLY`.
9. Understand failure modes and invalid indexes after a concurrent index build.
10. Know the limitations of `DROP INDEX CONCURRENTLY` and `REINDEX CONCURRENTLY`.
11. Handle `VACUUM`, `CREATE DATABASE`, `TABLESPACE`, and `ALTER SYSTEM` in migrations.
12. Understand exceptions related to `CREATE`/`DROP SUBSCRIPTION` and replication slots.
13. Recognize version-specific changes with `ALTER TYPE ADD VALUE`.
14. Use PL/pgSQL `EXCEPTION` blocks and understand subtransaction semantics.
15. Collect `SQLSTATE`, message, detail, hint, and constraint information.
16. Distinguish between functions, procedures, and `DO` blocks regarding transaction control.
17. Design atomic and non-atomic migrations.
18. Configure migration tools so special commands are not wrapped in a transaction.
19. Manage locks, timeouts, and transaction duration during DDL.
20. Inspect catalog state after migrations and after failures.
21. Build rollback, retry, and recovery procedures.
22. Practice transactional DDL, savepoints, concurrent indexes, and exception handling in labs.

**Scope:** Modern PostgreSQL. The list of commands and certain limitations may vary across major versions. Always check the documentation for your target server, especially for replication commands, enum changes, concurrent index operations, and migration frameworks. Examples use a lab database; do not run destructive operations or long-running DDL on production without a plan.

---

## 2. Transaction Blocks and Autocommit

A transaction defines the boundary within which database changes are committed or rolled back.

### 2.1. Explicit transaction

An explicit transaction begins with `BEGIN` or `START TRANSACTION` and ends with `COMMIT` or `ROLLBACK`.

~~~sql
BEGIN;

CREATE TABLE public.customer_note (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.customer_note
    ADD CONSTRAINT customer_note_note_not_empty
    CHECK (length(note) > 0);

COMMIT;
~~~

If all commands succeed, the transaction commits all changes. If an error occurs and the transaction rolls back, the table and constraint created inside the transaction will no longer exist.

### 2.2. Autocommit

In `psql`, autocommit is enabled by default. Each statement outside a transaction block executes in its own implicit transaction.

~~~sql
CREATE TABLE public.audit_event (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name TEXT NOT NULL
);

ALTER TABLE public.audit_event
    ADD COLUMN created_at TIMESTAMPTZ DEFAULT now();
~~~

The two statements above normally commit independently. If the second statement fails, the first statement has already committed.

### 2.3. Implicit transaction and explicit transaction

- Implicit transaction: the client sends a statement when no transaction block is open; PostgreSQL automatically manages begin/commit for that statement.
- Explicit transaction: the client opens a transaction and groups multiple statements into a single unit.
- Transaction block: the state in which the server is inside a client-controlled transaction.

A command prohibited inside a transaction block can still run if sent standalone with autocommit enabled.

### 2.4. Clients may wrap transactions automatically

Migration tools, ORMs, or application drivers may automatically issue `BEGIN` before running SQL. Therefore, a command that works in `psql` autocommit mode can fail when invoked from a migration framework.

### 2.5. Checking state from the client

In `psql`, you can check the autocommit setting:

~~~text
\echo :AUTOCOMMIT
~~~

You can toggle it with:

~~~text
\set AUTOCOMMIT on
~~~

Autocommit is a `psql` client behavior, not a server GUC shared across all connections.

---

## 3. What is Transactional DDL?

Transactional DDL is the ability to perform schema changes inside a transaction and roll back those changes if the transaction does not commit.

### 3.1. DDL statements that typically support transactions

Most of the following commands can run inside a transaction block:

- `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`.
- `CREATE VIEW`, `ALTER VIEW`, `DROP VIEW`.
- `CREATE SEQUENCE`, `ALTER SEQUENCE`, `DROP SEQUENCE`.
- `CREATE SCHEMA`, `ALTER SCHEMA`, `DROP SCHEMA`.
- `CREATE TYPE`, `ALTER TYPE`, `DROP TYPE`, with some version/operation-specific caveats.
- `CREATE FUNCTION`, `ALTER FUNCTION`, `DROP FUNCTION`.
- `CREATE TRIGGER`, `ALTER TRIGGER`, `DROP TRIGGER`.
- Regular `CREATE INDEX` and `DROP INDEX`.
- `CREATE EXTENSION`, `ALTER EXTENSION UPDATE`, `DROP EXTENSION` under conditions supported by the extension.
- `CREATE`/`ALTER`/`DROP` for many types of constraints and policies.

This list does not mean every option or extension script is safe in a transaction. An extension update script might invoke a command prohibited in a transaction block.

### 3.2. Example: rolling back CREATE TABLE

~~~sql
BEGIN;

CREATE TABLE public.rollback_demo (
    id INTEGER PRIMARY KEY,
    description TEXT
);

INSERT INTO public.rollback_demo(id, description)
VALUES (1, 'temporary schema change');

ROLLBACK;
~~~

After `ROLLBACK`, the newly created table and row no longer exist.

### 3.3. Example: rolling back ALTER TABLE

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN migration_marker BOOLEAN DEFAULT false;

ROLLBACK;
~~~

The new column created inside the transaction is rolled back.

### 3.4. Example: rolling back DROP TABLE

~~~sql
BEGIN;

DROP TABLE public.old_reporting_table;

-- Realized the migration is missing a step.
ROLLBACK;
~~~

Because `DROP TABLE` has not committed, rolling back restores the catalog state and the table remains intact.

### 3.5. DDL and catalog visibility

Uncommitted catalog changes are not visible as published schema changes to other transactions. Upon commit, other sessions observe the new schema according to transaction visibility and locking rules.

### 3.6. Transactional DDL does not eliminate locks

DDL must still acquire the required locks. For example, `ALTER TABLE` often requires a strong lock, which is held until the end of the transaction. A long-running migration transaction can block application queries or force other DDL to wait.

### 3.7. Atomicity is bounded to the database transaction

Side effects outside the transaction—such as HTTP requests, custom file writes from external processes, or changes in remote systems—do not automatically roll back with a PostgreSQL transaction. Sequence operations like `nextval` also do not roll back in the usual way.

Never assume every side effect triggered while running DDL is undone.

---

## 4. Why is Transactional DDL Useful?

### 4.1. Schema and data changes can stay consistent

A migration can add a column, backfill a small dataset, create a constraint, and update the migration ledger within the same transaction. If one step fails, the entire group of changes can roll back.

### 4.2. Avoids half-applied schemas

If `ALTER TABLE` succeeds but the next step fails, a transactional migration can roll back `ALTER TABLE` instead of leaving the new schema missing a constraint or function.

### 4.3. Controlled deployments

The migration runner can mark a migration complete only after `COMMIT` succeeds. This keeps schema state and migration history consistent.

### 4.4. Easy testing and recovery

In staging, you can run a migration, inspect the result, and roll back to verify behavior. However, this does not replace backups or rehearsals on production-equivalent data.

### 4.5. Not every migration should be one giant transaction

A long-running DDL transaction holds locks, snapshots, and resources. Backfilling billions of rows, concurrent index builds, or vacuuming usually require separate workflows, batching, or standalone execution.

---

## 5. SQL Errors and the Aborted Transaction State

When a statement inside an explicit transaction fails, PostgreSQL normally marks the transaction as aborted. Subsequent statements will not execute successfully until a rollback occurs.

### 5.1. Example: unique violation

~~~sql
BEGIN;

CREATE TABLE public.unique_demo (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE
);

INSERT INTO public.unique_demo VALUES
    (1, 'a@example.test');

INSERT INTO public.unique_demo VALUES
    (2, 'a@example.test');

-- The second statement triggers unique_violation.
SELECT count(*) FROM public.unique_demo;
~~~

After the error, the final `SELECT` returns an error because the transaction is in the aborted state. You need `ROLLBACK` or `ROLLBACK TO SAVEPOINT`.

### 5.2. SQLSTATE

PostgreSQL attaches an `SQLSTATE` code to errors. Examples:

| SQLSTATE | Condition | Meaning |
| --- | --- | --- |
| 23505 | unique_violation | Duplicate unique key |
| 23503 | foreign_key_violation | Foreign key violation |
| 23514 | check_violation | CHECK violation |
| 42P07 | duplicate_table | Relation with the same name already exists |
| 42701 | duplicate_column | Column already exists |
| 25001 | active_sql_transaction | Command cannot run inside a transaction block |
| 40001 | serialization_failure | Serialization conflict |
| 40P01 | deadlock_detected | Deadlock |
| 55P03 | lock_not_available | Could not acquire lock |
| 57014 | query_canceled | Query canceled/timed out in many scenarios |

Specific `SQLSTATE` classes/codes and messages should be obtained from the server, not inferred solely from text.

### 5.3. Recovering the transaction

~~~sql
ROLLBACK;
~~~

`ROLLBACK` ends the aborted transaction and undoes all uncommitted changes.

### 5.4. Why can't execution continue?

PostgreSQL must preserve transaction consistency. After an error, it cannot simply skip the failed statement and commit subsequent statements as though the transaction had no issues.

### 5.5. Client behavior

Some clients automatically roll back on exception; others leave the transaction in the aborted state until the application explicitly calls rollback. Application code must always clean up transactions on error paths.

---

## 6. SAVEPOINT and ROLLBACK TO SAVEPOINT

A savepoint creates a recovery point inside a transaction. If a statement after the savepoint fails, you can roll back the portion after the savepoint while keeping earlier changes.

### 6.1. Example

~~~sql
BEGIN;

CREATE TABLE public.savepoint_demo (
    id INTEGER PRIMARY KEY,
    value TEXT
);

SAVEPOINT before_optional_change;

ALTER TABLE public.savepoint_demo
    ADD COLUMN status TEXT;

-- Suppose the following step fails:
INSERT INTO public.savepoint_demo(id, value, status)
VALUES (1, 'one', 'active');

-- If recovery is needed:
ROLLBACK TO SAVEPOINT before_optional_change;

-- CREATE TABLE remains in the transaction.
-- ALTER TABLE and INSERT after the savepoint are undone.

COMMIT;
~~~

### 6.2. Savepoints do not commit transactions

`ROLLBACK TO SAVEPOINT` only undoes changes made after the savepoint. The outer transaction remains open and still requires `COMMIT` or `ROLLBACK`.

### 6.3. RELEASE SAVEPOINT

~~~sql
RELEASE SAVEPOINT before_optional_change;
~~~

`RELEASE` removes the savepoint marker. It does not commit the transaction.

### 6.4. Nested savepoints

You can create multiple savepoints for layered recovery. When rolling back to a savepoint, any savepoints created after it are destroyed.

### 6.5. Savepoints and locks

Rolling back to a savepoint can release some locks acquired after the savepoint, according to PostgreSQL semantics. Locks acquired before the savepoint generally remain until the end of the transaction.

### 6.6. When to use savepoints?

- A migration has an optional step.
- Attempting DDL that might fail while wanting to keep earlier setup.
- Controlled error handling in administrative scripts.
- Batch operations requiring partial rollback.

Do not use savepoints to mask failed migrations or commit an undefined schema state.

---

## 7. Commands Prohibited Inside a Transaction Block

Certain commands must run standalone because they affect resources or state outside a normal transaction.

### 7.1. Summary table

| Command / group | Inside transaction block? | Reason / notes |
| --- | --- | --- |
| CREATE DATABASE | No | Creates a database at the cluster level |
| DROP DATABASE | No | Drops a database at the cluster level |
| CREATE TABLESPACE | No | Creates a tablespace and filesystem directory |
| DROP TABLESPACE | No | Drops a tablespace |
| ALTER SYSTEM | No | Writes to the server configuration file |
| VACUUM | No | Performs maintenance with its own transaction semantics |
| CREATE INDEX CONCURRENTLY | No | Builds an index across multiple transactions/phases |
| DROP INDEX CONCURRENTLY | No | Drops an index using a concurrent workflow |
| REINDEX CONCURRENTLY | No | Rebuilds an index across multiple phases |
| CREATE SUBSCRIPTION with connect=true | No | Can create a replication slot on a remote publisher |
| DROP SUBSCRIPTION when dropping remote slot | No | Has side effects on a replication slot |

These are important common cases, not an exhaustive list for every PostgreSQL release and extension. For replication commands, verify specific options and versions.

### 7.2. CREATE DATABASE

~~~sql
CREATE DATABASE app_reporting;
~~~

Run standalone, not wrapped in `BEGIN`/`COMMIT`.

If you need to create a database and then run schema migrations:
1. Create the database in a separate step.
2. Connect to the new database.
3. Run schema DDL inside an appropriate transaction.

### 7.3. DROP DATABASE

~~~sql
DROP DATABASE app_reporting;
~~~

Also runs outside a transaction block. Check active connections, ownership, and destructive impact before dropping.

### 7.4. CREATE TABLESPACE

~~~sql
CREATE TABLESPACE fast_space
    LOCATION '/srv/postgresql/tablespaces/fast_space';
~~~

Creating a tablespace depends on filesystem paths and permissions. The directory must meet PostgreSQL's requirements and usually must exist before running the command.

### 7.5. DROP TABLESPACE

~~~sql
DROP TABLESPACE fast_space;
~~~

The tablespace must be empty per PostgreSQL rules. Check for objects still using the tablespace before dropping it.

### 7.6. ALTER SYSTEM

~~~sql
ALTER SYSTEM SET work_mem = '16MB';
~~~

`ALTER SYSTEM` writes configuration to `postgresql.auto.conf`. It is not a schema change rolled back with a transaction. Afterward, a reload or restart is required depending on the parameter context.

### 7.7. VACUUM

~~~sql
VACUUM (ANALYZE) public.orders;
~~~

`VACUUM` cannot run inside a transaction block. `VACUUM FULL` shares the same transaction block restriction and has its own lock/space requirements. Standalone `ANALYZE` can run inside a transaction; do not confuse `ANALYZE` with `VACUUM ANALYZE`.

### 7.8. Why must they be separated?

If a migration runner wraps a script in `BEGIN`, the server may return `SQLSTATE 25001`. Move the command to a non-transactional migration or a separate deployment step—do not try to nest it inside a transaction using a savepoint.

---

## 8. CREATE INDEX and CREATE INDEX CONCURRENTLY

This is a classic example of the difference between regular transactional DDL and commands with exceptions.

### 8.1. Regular CREATE INDEX

~~~sql
BEGIN;

CREATE INDEX orders_created_at_idx
    ON public.orders (created_at);

COMMIT;
~~~

Regular `CREATE INDEX` can run inside a transaction. If the transaction rolls back, index creation rolls back as well.

### 8.2. Lock behavior

Regular `CREATE INDEX` typically takes a lock that blocks DML writes to the table during the build. It can force `INSERT`/`UPDATE`/`DELETE` statements to wait. On large tables, the lock duration can impact availability.

### 8.3. CREATE INDEX CONCURRENTLY

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON public.orders (created_at);
~~~

This command allows reads and writes to continue during most of the build, but requires multiple phases, scans, and waits. It cannot run inside a transaction block.

### 8.4. Why can't it be inside a single transaction?

A concurrent build requires multiple transactions/phases to coordinate with active transactions and ensure the index is valid once complete. Therefore, the server rejects it when the client is inside an explicit transaction block.

### 8.5. Limitations

- Cannot run inside a transaction block.
- Cannot run multiple concurrent index builds on the same table simultaneously.
- May have to wait on older transactions/snapshots.
- Consumes I/O and CPU during the build.
- A unique index build can detect duplicate values and fail.
- If it fails, it can leave behind an invalid index.

### 8.6. Invalid indexes after failure

Inspect the index catalog:

~~~sql
SELECT
    ns.nspname AS schema_name,
    idx.relname AS index_name,
    tbl.relname AS table_name,
    i.indisready,
    i.indisvalid,
    i.indislive
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_catalog.pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = idx.relnamespace
WHERE NOT i.indisvalid
ORDER BY ns.nspname, idx.relname;
~~~

`indisvalid=false` means the planner does not consider the index valid for normal query usage. `indisready` indicates whether the index is being maintained by writes; inspect both flags and the actual state.

### 8.7. Cleaning up an invalid index

After verifying the exact index and the root cause of the failure, you can drop it concurrently:

~~~sql
DROP INDEX CONCURRENTLY public.orders_created_at_idx;
~~~

This command also cannot run inside a transaction block. After cleanup, fix the cause and retry.

### 8.8. IF NOT EXISTS does not fix an invalid index

If an index with the same name already exists but is invalid, `CREATE INDEX CONCURRENTLY IF NOT EXISTS` may simply emit a notice that the relation already exists and skip creation. You must inspect the catalog, drop the invalid index appropriately, and then recreate it.

### 8.9. Unique indexes and constraints

`CREATE UNIQUE INDEX CONCURRENTLY` can detect duplicates during the build. If you need a `UNIQUE` constraint, look into building a unique index first and then attaching the constraint according to version capabilities. Do not assume every constraint can be created concurrently directly.

---

## 9. DROP INDEX CONCURRENTLY and REINDEX CONCURRENTLY

### 9.1. Regular DROP INDEX

~~~sql
BEGIN;

DROP INDEX public.orders_old_idx;

ROLLBACK;
~~~

Regular `DROP INDEX` can run inside a transaction. Rolling back undoes the drop.

### 9.2. DROP INDEX CONCURRENTLY

~~~sql
DROP INDEX CONCURRENTLY public.orders_old_idx;
~~~

Cannot run inside a transaction block. It reduces blocking against concurrent activity using a multi-phase procedure.

### 9.3. Limitations to remember

`DROP INDEX CONCURRENTLY`:
- Drops only one index per command.
- Does not support `CASCADE`.
- Cannot be used to drop an index backing a constraint.
- Has specific relation/index limitations depending on version.

If an index belongs to a constraint, handle the constraint through the proper DDL path instead of trying to drop the index directly.

### 9.4. Regular REINDEX

~~~sql
REINDEX INDEX public.orders_created_at_idx;
~~~

Regular `REINDEX` can be used inside a transaction block under supported conditions, but can significantly block reads/writes depending on the object and operation.

### 9.5. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_created_at_idx;
~~~

Cannot run inside a transaction block. It builds a replacement index across multiple phases to reduce blocking, at the cost of additional time, I/O, and storage.

### 9.6. Choosing a method

| Method | Transaction block | Blocking | Cost |
| --- | --- | --- | --- |
| CREATE INDEX | Yes | Can block writes during build | Typically fewer phases |
| CREATE INDEX CONCURRENTLY | No | Allows DML for most of the process | Multiple phases, waits, and I/O |
| DROP INDEX | Yes | May require a strong lock | Shorter catalog operation |
| DROP INDEX CONCURRENTLY | No | Reduces blocking with concurrent sessions | Multiple phases |
| REINDEX | Per operation/version | Can block activity | Rebuilds index |
| REINDEX CONCURRENTLY | No | Reduces blocking | Requires more time/storage |

Always check the PostgreSQL version and object type before choosing.

---

## 10. CREATE DATABASE, TABLESPACE, and ALTER SYSTEM in Migrations

These commands belong to cluster/host configuration rather than a single database's schema transaction.

### 10.1. Separate provisioning from schema migrations

A deployment workflow can be split into:
1. Provision database/tablespace.
2. Configure server settings.
3. Connect to the database.
4. Run transactional schema migrations.
5. Run non-transactional operations.
6. Verify application and operational state.

### 10.2. Database creation

~~~sql
CREATE DATABASE appdb
    OWNER app_owner
    ENCODING 'UTF8';
~~~

The command must run from another database, not inside a transaction block. Locale and template settings must also be decided before creation.

### 10.3. Tablespace provisioning

~~~sql
CREATE TABLESPACE archive_space
    OWNER dba_role
    LOCATION '/srv/postgresql/archive_space';
~~~

The filesystem path and OS ownership must be ready. Backup/restore and failover hosts need matching storage mappings.

### 10.4. ALTER SYSTEM

~~~sql
ALTER SYSTEM SET shared_buffers = '4GB';
SELECT pg_reload_conf();
~~~

`shared_buffers` requires a restart to take effect; a reload is not enough. `pg_settings.pending_restart` helps confirm this. `ALTER SYSTEM` cannot run inside a transaction block and does not roll back with schema migrations.

### 10.5. Manage configuration as infrastructure

In production, many organizations manage parameters via configuration management, container environments, or managed-service parameter groups. Migration SQL should not silently alter server-wide configuration without an owner and change record.

---

## 11. VACUUM and ANALYZE

### 11.1. VACUUM

~~~sql
VACUUM public.orders;
~~~

`VACUUM` cannot run inside a transaction block. It performs maintenance to process dead tuples, the visibility map, and related tasks.

### 11.2. VACUUM ANALYZE

~~~sql
VACUUM (ANALYZE) public.orders;
~~~

Also cannot run inside a transaction block because it includes `VACUUM`.

### 11.3. Standalone ANALYZE

~~~sql
ANALYZE public.orders;
~~~

`ANALYZE` can run inside a transaction block. It collects planner statistics; it does not perform all the cleanup work of `VACUUM`.

### 11.4. VACUUM FULL

~~~sql
VACUUM FULL public.orders;
~~~

`VACUUM FULL` rewrites the table and requires a strong lock plus extra storage. It cannot run inside a transaction block. Evaluate downtime, disk space, and bloat before using it.

### 11.5. Autovacuum

Autovacuum is a background process coordinated by PostgreSQL. It is not a migration DDL command and has its own lifecycle. Do not try to call `VACUUM` inside a migration transaction to replace autovacuum.

---

## 12. Subscriptions and Replication Slots: Exceptions with External Side Effects

Logical replication includes commands that require care because they interact with publishers and replication slots.

### 12.1. CREATE SUBSCRIPTION

Example:

~~~sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=publisher.example.test dbname=appdb user=repl_user'
PUBLICATION orders_pub;
~~~

With the default `connect=true`, `CREATE SUBSCRIPTION` connects to the publisher and creates a replication slot as configured. Because of this side effect on a remote server, the command cannot execute inside a transaction block.

### 12.2. connect=false

Some workflows create a subscription with `connect=false` to avoid connecting and creating the slot immediately during the command. In that case, you must manage the slot and subsequent synchronization steps manually according to the documentation. Do not treat this as a way to bypass replication setup requirements.

### 12.3. DROP SUBSCRIPTION

If a subscription needs to drop its remote replication slot, `DROP SUBSCRIPTION` may not run inside a transaction block due to the remote side effect. Check slot state and version-specific instructions.

### 12.4. Unreachable slot

If the publisher is unreachable or the slot was handled separately, follow documentation to detach the subscription from the slot before dropping the local subscription. Do not delete a slot on the publisher without confirming consumer state.

### 12.5. External state does not roll back with local transactions

Remote replication slot creation/deletion cannot be treated like a normal local catalog change. Rehearsals must check both the subscriber and the publisher.

---

## 13. ALTER TYPE ADD VALUE and Version Differences

Enum types are an example of DDL whose rules changed across major versions.

### 13.1. Adding an enum value

~~~sql
ALTER TYPE order_status
    ADD VALUE 'awaiting_review';
~~~

### 13.2. PostgreSQL 11 and older

In older versions, `ALTER TYPE ... ADD VALUE` could not run inside a transaction block. Migrations had to isolate the command as a standalone step.

### 13.3. PostgreSQL 12 and newer

These versions allow adding an enum value inside a transaction block. However, the new value cannot be used until the transaction containing `ALTER TYPE` commits.

Example:

~~~sql
BEGIN;

ALTER TYPE order_status
    ADD VALUE 'awaiting_review';

-- Do not use the newly added value in the same transaction.
COMMIT;

INSERT INTO public.orders(status)
VALUES ('awaiting_review');
~~~

### 13.4. Why separate steps?

If a migration adds an enum value and immediately inserts or casts to that value before `COMMIT`, the server can reject it because the enum value has not been committed yet.

### 13.5. Enum label ordering

`ADD VALUE` can specify `BEFORE`/`AFTER` an existing label. Enum ordering affects comparison/sort semantics; check application assumptions and migration order.

### 13.6. Do not remove enum labels directly

If you need to remove or rename a label, you usually must create a new type and migrate dependencies/data. This is a multi-step migration, not a simple string rename.

---

## 14. Commands with Exceptions Do Not Mean DDL is Non-Transactional

Distinguish between:
- DDL that modifies catalogs and can roll back.
- Commands prohibited inside a transaction block.
- Commands that can run but cause external side effects.
- Commands requiring multiple transactions/phases.
- Commands whose behavior changes across versions.

### 14.1. Example: CREATE INDEX

Regular `CREATE INDEX` is transactional; `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block.

### 14.2. Example: VACUUM

`VACUUM` is not schema DDL, yet it frequently appears in migration/maintenance scripts and cannot run inside a transaction block.

### 14.3. Example: ALTER SYSTEM

`ALTER SYSTEM` is a configuration management command, not a database schema change. It writes a config file and does not participate in transaction rollback.

### 14.4. Example: CREATE SUBSCRIPTION

It alters local catalogs and can create a replication slot on a remote publisher. That external effect imposes transaction restrictions.

### 14.5. Classify by specific command

You cannot infer from a DDL command's name alone whether it can run inside a transaction. Check the documentation and test on the exact target major version.

---

## 15. PL/pgSQL EXCEPTION Blocks and Subtransactions

PL/pgSQL allows handling errors inside a block using `EXCEPTION`. A block with `EXCEPTION` executes with subtransaction semantics.

### 15.1. Basic structure

~~~sql
DO $$
BEGIN
    INSERT INTO public.audit_event(event_name)
    VALUES ('migration_started');

EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate event ignored';
END;
$$;
~~~

A `DO` block is an anonymous code block. The example above illustrates a handler; the table must exist before running.

### 15.2. Subtransaction behavior

When an error occurs inside a block with `EXCEPTION`:
- Database changes made inside that block are rolled back.
- Control transfers to the matching handler.
- Changes made prior to entering the block remain in the outer transaction.
- After the handler finishes, the outer block can continue.

### 15.3. Example: partial rollback

~~~sql
DO $$
BEGIN
    INSERT INTO public.audit_event(event_name)
    VALUES ('before_inner_block');

    BEGIN
        INSERT INTO public.audit_event(event_name)
        VALUES ('duplicate_event');

        INSERT INTO public.audit_event(event_name)
        VALUES ('duplicate_event');

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'Inner block rolled back';
    END;

    INSERT INTO public.audit_event(event_name)
    VALUES ('after_inner_block');
END;
$$;
~~~

To demonstrate `unique_violation`, `event_name` needs a unique constraint. When the error occurs, the first insert inside the inner block is also rolled back with the subtransaction.

### 15.4. PL/pgSQL variables

PL/pgSQL variable values are not rolled back like database changes. Handlers can inspect variables at the point the exception was raised.

### 15.5. Exception blocks have overhead

Subtransactions incur management overhead. Avoid wrapping every statement in `EXCEPTION` just to check conditions that can be handled with `INSERT ... ON CONFLICT` or metadata checks.

### 15.6. Do not catch overly broadly

`WHEN OTHERS` can hide severe schema errors if the handler merely emits a `NOTICE` and continues. Only catch conditions that the code knows how to recover from.

---

## 16. Catching Errors by Condition and SQLSTATE

### 16.1. Common conditions

~~~sql
DO $$
BEGIN
    -- Perform an operation that may fail.
    PERFORM 1 / 0;

EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Cannot divide by zero';

    WHEN OTHERS THEN
        RAISE;
END;
$$;
~~~

`RAISE;` inside a handler re-throws the current error so the outer caller can handle it.

### 16.2. Common condition names

| Condition | SQLSTATE | Meaning |
| --- | --- | --- |
| unique_violation | 23505 | Unique constraint |
| foreign_key_violation | 23503 | Foreign key |
| check_violation | 23514 | CHECK constraint |
| not_null_violation | 23502 | NOT NULL |
| serialization_failure | 40001 | Serialization conflict |
| deadlock_detected | 40P01 | Deadlock |
| lock_not_available | 55P03 | Lock unavailable |
| query_canceled | 57014 | Query canceled |
| insufficient_privilege | 42501 | Insufficient privilege |
| undefined_table | 42P01 | Table does not exist |

### 16.3. SQLSTATE is a more stable interface than message text

Applications/handlers should classify errors by `SQLSTATE` or condition name. Message text can vary by locale, version, or error detail.

### 16.4. Exceptions to WHEN OTHERS

In PL/pgSQL, `WHEN OTHERS` does not catch every condition. Query cancellation and assertion failures are excluded under PL/pgSQL semantics. Do not rely on `OTHERS` to swallow all errors.

### 16.5. RAISE NOTICE does not replace error handling

`NOTICE` only emits a message. If a handler ignores an error and continues, you must be certain the database state has been recovered and business logic permits continuing.

---

## 17. GET STACKED DIAGNOSTICS

Handlers can read detailed information about the exception that just occurred.

~~~sql
DO $$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_detail TEXT;
    v_hint TEXT;
    v_context TEXT;
BEGIN
    INSERT INTO public.unique_demo(id, email)
    VALUES (3, 'a@example.test');

EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail = PG_EXCEPTION_DETAIL,
            v_hint = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE NOTICE 'SQLSTATE=% MESSAGE=% DETAIL=% HINT=% CONTEXT=%',
            v_state, v_message, v_detail, v_hint, v_context;

        RAISE;
END;
$$;
~~~

### 17.1. Diagnostics fields

You can retrieve:
- `RETURNED_SQLSTATE`.
- `MESSAGE_TEXT`.
- `PG_EXCEPTION_DETAIL`.
- `PG_EXCEPTION_HINT`.
- `PG_EXCEPTION_CONTEXT`.
- `SCHEMA_NAME`.
- `TABLE_NAME`.
- `COLUMN_NAME`.
- `CONSTRAINT_NAME`.
- `DATATYPE_NAME`.

Availability and meaning of specific fields depend on the exception and version.

### 17.2. Do not log secrets

Exception details/context may contain sensitive data or query parameters. Mask them per policy before sending to centralized logs.

### 17.3. Re-RAISE after logging diagnostics

If the error is not safely handled, `RAISE;` preserves failure semantics and allows the caller or migration runner to roll back the transaction.

---

## 18. ON CONFLICT Instead of Exceptions for Upserts

Some errors can be handled using SQL semantics rather than raising exceptions.

### 18.1. No need to catch unique_violation for simple upserts

~~~sql
INSERT INTO public.feature_flag(flag_name, enabled)
VALUES ('new_checkout', true)
ON CONFLICT (flag_name)
DO UPDATE SET enabled = EXCLUDED.enabled;
~~~

### 18.2. DO NOTHING

~~~sql
INSERT INTO public.feature_flag(flag_name, enabled)
VALUES ('new_checkout', true)
ON CONFLICT (flag_name) DO NOTHING;
~~~

### 18.3. Benefits

- Clearer code intent.
- Avoids using exceptions as routine control flow.
- Can reduce subtransaction overhead.
- Handles concurrency according to PostgreSQL unique constraint semantics.

### 18.4. Does not replace all exceptions

Foreign key violations, check violations, permissions, serialization failures, and other errors still require proper handling. `ON CONFLICT` only handles supported conflict targets.

---

## 19. Functions, Procedures, and DO Blocks: Transaction Control

Not all PL/pgSQL code is allowed to `COMMIT` or `ROLLBACK`.

### 19.1. Function

A function is invoked within an SQL statement and runs in the statement/caller's transaction. A function cannot `COMMIT` or `ROLLBACK` the transaction itself.

~~~sql
CREATE OR REPLACE FUNCTION public.do_work()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.audit_event(event_name)
    VALUES ('function_called');

    -- Cannot COMMIT transaction here.
END;
$$;
~~~

### 19.2. Procedure

A procedure is invoked with `CALL` and can perform transaction control under conditions permitted by PostgreSQL.

~~~sql
CREATE OR REPLACE PROCEDURE public.batch_marker()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.audit_event(event_name)
    VALUES ('batch_marker');

    COMMIT;
END;
$$;
~~~

This example illustrates transaction control in a procedure. `CALL` must be executed under permitted conditions, typically at the top level and not inside an explicit transaction block opened by the caller.

### 19.3. CALL inside a transaction block

~~~sql
BEGIN;
CALL public.batch_marker();
COMMIT;
~~~

If the procedure attempts to `COMMIT` when `CALL` is running inside an explicit transaction block, PostgreSQL will reject the transaction control.

### 19.4. DO block

`DO` can use transaction control when called at the top level without an enclosing outer transaction block preventing it. If `DO` runs inside a transaction block, `COMMIT`/`ROLLBACK` inside `DO` is not permitted.

### 19.5. Exception blocks restrict transaction control

Transaction control cannot be executed while inside a PL/pgSQL block that has an `EXCEPTION` handler because that block uses a subtransaction.

### 19.6. CALL stack

Transaction control in procedures also depends on how `CALL`/`DO` blocks are nested. An intermediate invocation via another SQL command can invalidate the required top-level condition.

### 19.7. COMMIT AND CHAIN

Procedures can use `COMMIT AND CHAIN` in supported versions to end the current transaction and start a new one with chained characteristics according to PostgreSQL semantics.

### 19.8. Use transaction control in procedures intentionally

For example, batch processing can commit each group to avoid giant transactions. In return, the entire procedure is no longer atomic as a single transaction. You must design for restartability and idempotency.

---

## 20. DDL in PL/pgSQL and Dynamic SQL

### 20.1. Static DDL in functions

Regular DDL can be executed inside a function if the command is allowed in the current transaction and violates no other restriction. The function still cannot end the transaction itself.

### 20.2. Dynamic SQL

~~~sql
DO $$
BEGIN
    EXECUTE
        'ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS source_tag TEXT';
END;
$$;
~~~

`EXECUTE` allows constructing commands dynamically. It does not bypass transaction restrictions: if a command is prohibited inside a transaction block, executing it via `EXECUTE` will still fail.

### 20.3. Identifier quoting

When building dynamic DDL, use `format` with `%I` for identifiers and `%L` for literals.

~~~sql
DO $$
DECLARE
    v_table_name TEXT := 'orders';
BEGIN
    EXECUTE format(
        'ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS migration_note TEXT',
        v_table_name
    );
END;
$$;
~~~

Never concatenate raw user input into SQL commands.

### 20.4. Dynamic commands and permissions

`SECURITY DEFINER` functions must control `search_path`, ownership, schema qualification, and identifier quoting. Dynamic DDL can open privilege escalation vectors if untrusted input is used.

### 20.5. Non-transactional commands cannot be legalized via EXECUTE

You cannot call `CREATE INDEX CONCURRENTLY`, `VACUUM`, or `ALTER SYSTEM` inside a function/`DO` running in a transaction block and expect it to run standalone.

---

## 21. Atomic and Non-Atomic Migrations

### 21.1. Atomic migration

A migration runs inside a single transaction and is only marked applied after `COMMIT`.

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN source_system TEXT;

CREATE INDEX orders_source_system_idx
    ON public.orders(source_system);

INSERT INTO public.schema_migration_log(version, applied_at)
VALUES ('2026_11_add_source_system', clock_timestamp());

COMMIT;
~~~

If any step fails, both the schema changes and the migration ledger update roll back.

### 21.2. Non-atomic migration

A migration containing commands prohibited in a transaction block must be configured as non-transactional or split into independent steps.

Example:

~~~sql
CREATE INDEX CONCURRENTLY orders_customer_id_idx
    ON public.orders(customer_id);
~~~

The migration runner must not wrap this command in `BEGIN`/`COMMIT`.

### 21.3. Do not mix both styles thoughtlessly

A script containing `CREATE INDEX CONCURRENTLY` alongside multiple transactional `ALTER TABLE` statements will fail if the tool wraps the entire script. Separate the command into its own migration and explicitly set its transaction mode.

### 21.4. Migration ledger

For non-atomic migrations, define when the ledger is updated:
- Mark complete only after the command succeeds and post-checks pass.
- If the command fails and leaves an invalid object, record a failed/pending status per your migration tool.
- Recovery scripts must know how to check whether the object exists, is valid, or is in a half-finished state.

### 21.5. Idempotency

Non-atomic migrations may need to be re-run. Design clear preconditions/postconditions, catalog checks, and cleanup. `IF NOT EXISTS` does not guarantee an existing object is in a valid state.

### 21.6. Expand/contract

For zero-downtime application deployments:
1. Expand the schema in a backward-compatible way.
2. Deploy the application reading/writing the new schema.
3. Backfill data in batches.
4. Validate.
5. Switch reads/writes.
6. Contract the old schema in a separate release.

Concurrent indexes and non-transactional steps typically belong in separate phases.

---

## 22. DDL Locks and Transaction Duration

Transactional DDL may be safe regarding atomicity, but it can still impact availability due to locks.

### 22.1. ALTER TABLE

Many `ALTER TABLE` forms require an `ACCESS EXCLUSIVE` lock. Some operations take lighter locks or can be performed in phases. Check the specific command and version.

### 22.2. Locks held until transaction end

If `ALTER TABLE` acquires a lock and the transaction then runs a long backfill, the lock can be held for the entire remaining duration.

### 22.3. lock_timeout

You can set timeouts before DDL:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '5min';

ALTER TABLE public.orders
    ADD COLUMN source_tag TEXT;

COMMIT;
~~~

If the lock cannot be acquired within 3 seconds, the statement fails. The transaction must then be rolled back or handled via a savepoint.

### 22.4. SET LOCAL

`SET LOCAL` applies only to the current transaction and expires when the transaction ends. It is well suited for bounding a migration session.

### 22.5. Long-running transactions

A long DDL transaction can:
- Hold locks.
- Hold snapshots.
- Block other deployments/queries.
- Delay autovacuum cleanup.
- Increase dead tuples and bloat.
- Increase recovery/rollback duration.

### 22.6. Observe blockers

Use `pg_stat_activity`, `pg_blocking_pids`, and `pg_locks` to see what the migration is waiting on or blocking.

---

## 23. Multi-Phase Constraint Migrations

PostgreSQL supports several ways to add constraints with reduced impact on large tables.

### 23.1. ADD CONSTRAINT NOT VALID

~~~sql
ALTER TABLE public.orders
    ADD CONSTRAINT orders_amount_nonnegative
    CHECK (amount >= 0)
    NOT VALID;
~~~

The constraint is added without fully scanning/validating existing data upfront. New writes must still satisfy the constraint per command semantics.

### 23.2. VALIDATE CONSTRAINT

~~~sql
ALTER TABLE public.orders
    VALIDATE CONSTRAINT orders_amount_nonnegative;
~~~

Validation runs separately, typically allowing better concurrency than adding an immediately validated constraint, though it still requires lock and resource planning.

### 23.3. Foreign keys

Foreign keys also support `NOT VALID` followed by `VALIDATE CONSTRAINT` in appropriate scenarios. This reduces the time strong locks are held when adding constraints to large tables.

### 23.4. Choosing transaction boundaries

`ADD CONSTRAINT` and `VALIDATE CONSTRAINT` can run inside transactions per command semantics, but separating them into distinct migration phases helps control duration and lock impact.

### 23.5. Post-check

Inspect `pg_constraint.convalidated` and the constraint definition after the migration.

---

## 24. Backfills and Batch Transactions

Large data backfills should not always sit inside a single transaction.

### 24.1. Why batch?

- Limits WAL bursts.
- Reduces time holding locks/snapshots.
- Enables pause/resume.
- Reduces rollback cost.
- Allows throttling according to application load.

### 24.2. Batch pattern

~~~sql
WITH batch AS (
    SELECT id
    FROM public.orders
    WHERE source_tag IS NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE public.orders AS o
SET source_tag = 'legacy'
FROM batch
WHERE o.id = batch.id;
~~~

The application/job runs this statement repeatedly in small transactions until no rows remain to process.

### 24.3. Idempotency

The `WHERE source_tag IS NULL` predicate allows re-running without overwriting already backfilled rows. In practice, you may also need a checkpoint/progress table.

### 24.4. Transaction control

Each batch commits separately. If a batch fails, roll back that batch and retry per policy; earlier batches remain committed.

### 24.5. Procedures can commit per batch

A procedure can control transactions under appropriate `CALL` conditions. Avoid `EXCEPTION` blocks wrapping the portion where you want to `COMMIT`, and test restart semantics.

---

## 25. psql and Migration Runners

### 25.1. psql ON_ERROR_STOP

~~~text
\set ON_ERROR_STOP on
~~~

When a command fails, `psql` stops the script as configured. With explicit transactions, the client must ensure the transaction is rolled back and the exit status is handled.

### 25.2. psql single-transaction

~~~bash
psql --single-transaction --file migration.sql appdb
~~~

This `psql` option wraps the script in a single transaction. It is unsuitable if the file contains commands prohibited in a transaction block such as `CREATE INDEX CONCURRENTLY` or `VACUUM`.

### 25.3. Autocommit

With autocommit enabled, non-transactional commands can run standalone. However, migration runners often manage their own transactions, so you must read your tool's configuration.

### 25.4. Migration frameworks

Many frameworks support:
- Transaction per migration.
- Transaction per statement.
- Non-transactional migration markers.
- Explicit transaction control.
- Retry or resume.
- Migration history tables.

Use the framework's built-in mechanisms rather than inserting `BEGIN`/`COMMIT` arbitrarily.

### 25.5. Separate migration files

Create separate files for concurrent indexes, vacuum, or cluster-level operations. Clearly document that the file must not run inside a transaction.

### 25.6. Script fails midway

Record:
- Exit code.
- Last successful command.
- Transaction state.
- Object state in catalogs.
- External side effects already executed.
- Whether safe retry is possible or cleanup is required.

---

## 26. Distinguishing DDL Rollback from Sequences and External Side Effects

Transactional DDL does not mean every change produced by a script is reverted.

### 26.1. Sequence values

`nextval` does not roll back with normal transactions. If a script consumes a sequence value and then rolls back, the consumed value may be skipped.

~~~sql
BEGIN;

SELECT nextval('public.order_id_seq');

ROLLBACK;
~~~

The sequence can still advance even though the transaction rolls back.

### 26.2. External calls

A function or extension might send requests to external systems, write files, or cause side effects outside PostgreSQL transactions. Rolling back the local database cannot undo those side effects.

### 26.3. Notifications

`NOTIFY` is delivered to listeners according to transaction commit semantics; notifications from rolled-back transactions are not emitted as committed notifications.

### 26.4. Advisory locks

Session-level advisory locks are not automatically released when a transaction rolls back; transaction-level advisory locks follow the transaction lifecycle. Distinguish between them when migration scripts use advisory locks.

### 26.5. Temporary objects

Temporary tables/objects follow `ON COMMIT` behavior and session lifecycles. Rolling back a transaction can undo object creation, whereas committed temp objects persist until session end.

### 26.6. Practical takeaway

When designing migrations, categorize side effects into two groups:
- PostgreSQL transactional state.
- External/non-transactional state.

Every external side effect needs its own retry or compensation plan.

---

## 27. Error Handling in Migration Scripts

### 27.1. Atomic transaction

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN source_system TEXT;

CREATE INDEX orders_source_system_idx
    ON public.orders(source_system);

COMMIT;
~~~

If `CREATE INDEX` fails, the transaction aborts and `ALTER TABLE` does not commit either.

### 27.2. Savepoint around an optional step

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN source_system TEXT;

SAVEPOINT optional_index;

CREATE INDEX orders_source_system_idx
    ON public.orders(source_system);

-- If CREATE INDEX fails:
-- ROLLBACK TO SAVEPOINT optional_index;

COMMIT;
~~~

In a real script, the client or PL block must catch the error and execute `ROLLBACK TO SAVEPOINT`. A plain SQL script does not automatically skip forward after an error once the transaction is aborted.

### 27.3. Do not swallow errors and mark the migration successful

If a handler catches an error while the migration ledger still records success, the system will believe the schema is complete even though an object is missing.

### 27.4. Preconditions and postconditions

Before migrating:
- Check whether objects exist.
- Check version/state.
- Check dependencies.
- Check lock availability.

After migrating:
- Check schema definitions.
- Check index validity.
- Check constraint validation.
- Check application queries.
- Check the migration ledger.

### 27.5. Recovery scripts

Write dedicated scripts to handle partial states of non-atomic migrations. Scripts must distinguish absent, valid, invalid, ready-but-invalid, and incorrectly defined objects.

---

## 28. Version-Specific and Extension-Specific Exceptions

### 28.1. ALTER TYPE ADD VALUE

As discussed, PostgreSQL 12+ allows adding enum labels inside a transaction, but the new label cannot be used until commit. Older versions have different restrictions.

### 28.2. CREATE/DROP SUBSCRIPTION

Options related to `connect` and replication slots affect transaction restrictions. Check documentation for your exact target major version and publisher state.

### 28.3. Extension scripts

`CREATE EXTENSION` or `ALTER EXTENSION UPDATE` can run inside a transaction, but the extension's script may contain commands that do not support transactions. Extension vendors should document specific procedures.

### 28.4. Concurrent operations

Commands containing the `CONCURRENTLY` keyword usually have transaction restrictions or special semantics. Do not assume all commands with `CONCURRENTLY` behave identically; verify each command.

### 28.5. New PostgreSQL releases

Major releases may add commands/options or change transaction support. A compatibility matrix should document command behavior across source and target versions.

---

## 29. Checking Transaction State and Command Behavior

### 29.1. Viewing transaction state in the client

`psql` shows different prompts when a transaction is open or aborted. Prompts help visually identify state, though automation should check exit statuses and server errors.

### 29.2. SQLSTATE for command restrictions

A command prohibited inside a transaction block typically returns `SQLSTATE 25001` (`active_sql_transaction`). Log the full message to identify the specific command.

### 29.3. Checking transaction ID/current state

PostgreSQL does not expose a single simple SQL boolean that completely replaces client transaction state across all contexts. Rely on client driver transaction APIs, `psql` prompts, and server error diagnostics.

### 29.4. Inspecting DDL objects

Use `pg_class`, `pg_index`, `pg_constraint`, `pg_extension`, and related catalogs to confirm the outcome of changes.

### 29.5. Do not rely solely on command exit messages

A concurrent command can fail after several phases and leave behind an object needing cleanup. Always check catalog postconditions.

---

## 30. Workflow for Designing Migrations with DDL

### Step 1: Classify every command

Label commands as transactional, non-transactional, version-specific, or having external side effects.

### Step 2: Define transaction boundaries

Group DDL requiring atomicity into small transactions. Separate concurrent indexes, `VACUUM`, database/tablespace provisioning, and `ALTER SYSTEM`.

### Step 3: Evaluate lock behavior

Review lock levels, table sizes, traffic, transaction duration, and blocker risks.

### Step 4: Set appropriate timeouts

Use `lock_timeout` and `statement_timeout` in the migration session. Define a retry policy.

### Step 5: Design failure recovery

For transactional steps, roll back the full transaction or to a savepoint. For non-transactional steps, inspect partial state and clean up/retry.

### Step 6: Manage the migration ledger

Record migration success only after postconditions pass. Maintain clear pending/failed states for non-atomic steps.

### Step 7: Rehearsal

Run on a clone with dataset, extension, and tool versions matching production. Measure duration, locks, WAL, I/O, and application impact.

### Step 8: Cutover

Execute in dependency order, verify each checkpoint, and preserve a rollback path.

### Step 9: Verify

Check schema, indexes, constraints, application compatibility, background jobs, and monitoring.

### Step 10: Record

Archive command outputs, version, start/end times, migration ID, operator, and recovery notes.

---

## 31. Runbook: Error 25001 from a Command Prohibited in a Transaction

### Step 1: Identify the command

Read the `SQLSTATE` and message. Confirm whether the command must run outside a transaction block.

### Step 2: Identify what opened the transaction

Check:
- `BEGIN` inside the SQL file.
- `psql --single-transaction`.
- Migration framework transaction-per-migration mode.
- ORM/session transaction.
- Procedure/`DO` caller context.

### Step 3: Split the migration

Move the command into a separate non-transactional file/step. Ensure the runner does not automatically wrap a transaction.

### Step 4: Check state before retrying

For concurrent indexes, check if the index exists and inspect `indisvalid`/`indisready`. For subscriptions, inspect the local subscription and remote slot. For databases/tablespaces, check whether the object exists.

### Step 5: Run the command standalone

Use an autocommit connection or the appropriate migration mode. Do not run it inside a function/`DO` block currently in a transaction.

### Step 6: Post-check

Verify the command completed and external side effects are accurate. Only then mark the migration applied.

---

## 32. Runbook: Concurrent Index Build Failed

### Step 1: Record the error

Save `SQLSTATE`, message, query, table/index name, and timestamp.

### Step 2: Inspect index flags

~~~sql
SELECT
    c.oid::regclass AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indexrelid
WHERE c.oid = to_regclass('public.orders_customer_id_idx');
~~~

### Step 3: Identify the cause

- Duplicate values (if unique index).
- Deadlock or lock timeout.
- Long-running transactions/snapshots.
- Storage full or I/O error.
- Cancel signal or statement timeout.
- Concurrent DDL conflict.

### Step 4: Check write maintenance state

If `indisready=true` while `indisvalid=false`, the index may still be maintained by writes even though the planner cannot use it as a valid index. Assess the overhead and clean up.

### Step 5: Cleanup

After confirming the exact index and verifying no constraint depends on it, run `DROP INDEX CONCURRENTLY` outside a transaction block.

### Step 6: Fix root cause and retry

Do not blindly retry before addressing the underlying cause.

### Step 7: Verify

Confirm `indisvalid=true`, correct index definition, and expected query plan/application behavior.

---

## 33. Runbook: Migration Transaction Aborted

### Step 1: Stop further statements

Stop sending DDL/DML to the aborted transaction.

### Step 2: Capture the first error

Record `SQLSTATE`, message, detail, hint, constraint/table, and the offending statement.

### Step 3: Check for savepoints

If the script had a savepoint before the command, `ROLLBACK TO SAVEPOINT` as appropriate. Otherwise, roll back the entire transaction.

### Step 4: Confirm state

Verify the transaction has ended or returned to the savepoint. Do not assume the client rolled back automatically.

### Step 5: Inspect the catalog

Verify objects prior to the transaction or after the savepoint are intact and no partial state exists outside the transaction.

### Step 6: Fix the migration

Fix the root cause and re-test on staging. Never edit production catalogs directly just to make a migration runner "green" without a recovery plan.

---

## 34. Lab 1: Transactional DDL and Rollback

This lab uses a development database.

### 34.1. Create an object inside a transaction

~~~sql
BEGIN;

CREATE TABLE public.ddl_tx_lab (
    id INTEGER PRIMARY KEY,
    value TEXT
);

INSERT INTO public.ddl_tx_lab VALUES (1, 'created in transaction');

SELECT to_regclass('public.ddl_tx_lab');

ROLLBACK;
~~~

### 34.2. Verify rollback

~~~sql
SELECT to_regclass('public.ddl_tx_lab');
~~~

The result is `NULL` if the table did not exist before the lab.

### 34.3. Test ALTER TABLE rollback

~~~sql
BEGIN;

CREATE TABLE public.ddl_alter_lab (id INTEGER PRIMARY KEY);

ALTER TABLE public.ddl_alter_lab ADD COLUMN note TEXT;

ROLLBACK;
~~~

### 34.4. Conclusion

Standard DDL participates in transactions and rolls back alongside other changes.

---

## 35. Lab 2: Savepoints and the Transaction-Aborted State

### 35.1. Create the table

~~~sql
CREATE TABLE public.savepoint_lab (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE
);
~~~

### 35.2. Create a savepoint

~~~sql
BEGIN;

INSERT INTO public.savepoint_lab VALUES (1, 'A');

SAVEPOINT before_duplicate;

INSERT INTO public.savepoint_lab VALUES (2, 'A');
~~~

The second statement violates the unique constraint.

### 35.3. Rollback to savepoint

~~~sql
ROLLBACK TO SAVEPOINT before_duplicate;

INSERT INTO public.savepoint_lab VALUES (2, 'B');

COMMIT;
~~~

### 35.4. Check the result

~~~sql
TABLE public.savepoint_lab;
~~~

The first row remains; the failed duplicate row was rolled back; row B was inserted after recovery.

### 35.5. Conclusion

Savepoints allow recovering the portion of a transaction after a chosen marker without rolling back the entire transaction.

---

## 36. Lab 3: Distinguishing CREATE INDEX and CREATE INDEX CONCURRENTLY

### 36.1. Generate lab data

~~~sql
CREATE TABLE public.index_tx_lab (
    id BIGINT PRIMARY KEY,
    category INTEGER NOT NULL,
    payload TEXT
);

INSERT INTO public.index_tx_lab(id, category, payload)
SELECT g, g % 100, repeat('x', 100)
FROM generate_series(1, 200000) AS g;
~~~

### 36.2. Create a regular index inside a transaction

~~~sql
BEGIN;

CREATE INDEX index_tx_lab_category_idx
    ON public.index_tx_lab(category);

ROLLBACK;
~~~

### 36.3. Verify the index does not exist

~~~sql
SELECT to_regclass('public.index_tx_lab_category_idx');
~~~

### 36.4. Create a concurrent index standalone

~~~sql
CREATE INDEX CONCURRENTLY index_tx_lab_category_idx
    ON public.index_tx_lab(category);
~~~

Run outside `BEGIN`/`COMMIT`.

### 36.5. Check validity

~~~sql
SELECT
    c.oid::regclass AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indexrelid
WHERE c.oid = to_regclass('public.index_tx_lab_category_idx');
~~~

### 36.6. Conclusion

Both commands create the same type of index, yet their transaction restrictions and concurrency behaviors differ.

---

## 37. Lab 4: Observing CREATE INDEX CONCURRENTLY Failure and Cleanup

Perform this lab only on a test table. Do not intentionally induce errors on production.

### 37.1. Create duplicate data

~~~sql
CREATE TABLE public.concurrent_failure_lab (
    id INTEGER,
    value TEXT
);

INSERT INTO public.concurrent_failure_lab VALUES
    (1, 'one'),
    (1, 'duplicate'),
    (2, 'two');
~~~

### 37.2. Attempt a unique concurrent index

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY concurrent_failure_lab_id_uq
    ON public.concurrent_failure_lab(id);
~~~

The command fails due to duplicate values and can leave behind an invalid index.

### 37.3. Inspect the catalog

~~~sql
SELECT
    c.oid::regclass AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indexrelid
WHERE c.oid = to_regclass(
    'public.concurrent_failure_lab_id_uq'
);
~~~

### 37.4. Remove duplicates

~~~DELETE FROM public.concurrent_failure_lab
WHERE ctid NOT IN (
    SELECT min(ctid)
    FROM public.concurrent_failure_lab
    GROUP BY id
);
~~~

### 37.5. Drop the invalid index

~~~DROP INDEX CONCURRENTLY public.concurrent_failure_lab_id_uq;
~~~

### 37.6. Recreate and verify

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY concurrent_failure_lab_id_uq
    ON public.concurrent_failure_lab(id);
~~~

Verify `indisvalid=true`. This lab demonstrates why catalog post-checks are needed after failures.

---

## 38. Lab 5: PL/pgSQL EXCEPTION and Diagnostics

### 38.1. Prepare the table

~~~sql
CREATE TABLE public.exception_lab (
    id INTEGER PRIMARY KEY,
    value TEXT UNIQUE
);
~~~

### 38.2. Create the handler

~~~sql
DO $$
DECLARE
    v_state TEXT;
    v_message TEXT;
BEGIN
    INSERT INTO public.exception_lab VALUES (1, 'first');

    BEGIN
        INSERT INTO public.exception_lab VALUES (2, 'first');

    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS
                v_state = RETURNED_SQLSTATE,
                v_message = MESSAGE_TEXT;

            RAISE NOTICE 'Caught %, %', v_state, v_message;
    END;

    INSERT INTO public.exception_lab VALUES (3, 'third');
END;
$$;
~~~

### 38.3. Check rows

~~~sql
TABLE public.exception_lab;
~~~

The duplicate row in the inner block is not inserted; the outer block continues.

### 38.4. Try re-RAISE

Replace the handler with `RAISE;` to observe the error propagating to the caller and the entire `DO` statement failing.

### 38.5. Conclusion

An `EXCEPTION` block creates a subtransaction, rolls back database changes inside the failing block, and allows outer code to continue if the handler handles it properly.

---

## 39. Practice Exercises

### Exercise 1 — Transactional DDL

Explain transactional DDL and list at least five DDL commands that can normally roll back.

### Exercise 2 — Autocommit

Distinguish between `psql` autocommit and explicit `BEGIN`/`COMMIT`.

### Exercise 3 — Atomic migration

Write a migration that creates a table, adds a constraint, and records the migration ledger in a single transaction.

### Exercise 4 — Transaction aborted

An `INSERT` triggers `unique_violation` inside an explicit transaction. Why does a subsequent `SELECT` also error?

### Exercise 5 — Savepoint

Write a script that creates a savepoint, triggers a constraint error, rolls back to the savepoint, and continues.

### Exercise 6 — SQLSTATE

Look up the `SQLSTATE` codes for unique violation, foreign key, deadlock, serialization failure, and active transaction restriction.

### Exercise 7 — Non-transactional commands

List commands prohibited inside a transaction block and group them by cluster, filesystem, maintenance, and concurrent index.

### Exercise 8 — CREATE DATABASE

Design a deployment that creates a database and then runs schema migrations. Why are two steps required?

### Exercise 9 — TABLESPACE

List filesystem prerequisites and risks when creating/dropping a tablespace.

### Exercise 10 — ALTER SYSTEM

Explain why `ALTER SYSTEM` does not roll back with DDL and why `shared_buffers` requires a restart.

### Exercise 11 — VACUUM

Compare `VACUUM`, `VACUUM ANALYZE`, and `ANALYZE` regarding transaction restrictions.

### Exercise 12 — CREATE INDEX

Compare `CREATE INDEX` and `CREATE INDEX CONCURRENTLY` regarding locks and transaction support.

### Exercise 13 — Concurrent index failure

A `CREATE UNIQUE INDEX CONCURRENTLY` fails due to duplicate data. Write a query to inspect `indisvalid`/`indisready` and a cleanup plan.

### Exercise 14 — IF NOT EXISTS

Why does `CREATE INDEX CONCURRENTLY IF NOT EXISTS` not automatically recover an invalid index of the same name?

### Exercise 15 — DROP INDEX CONCURRENTLY

List the limitations of `DROP INDEX CONCURRENTLY` and how to handle an index backing a constraint.

### Exercise 16 — REINDEX

Compare `REINDEX` and `REINDEX CONCURRENTLY`. Explain when to choose each method.

### Exercise 17 — Subscription

Why does `CREATE SUBSCRIPTION` with `connect=true` have a transaction restriction? Which external side effects must be checked?

### Exercise 18 — Enum versions

Compare `ALTER TYPE ADD VALUE` on PostgreSQL 11 vs. PostgreSQL 12 and newer.

### Exercise 19 — Enum visibility

On PostgreSQL 12+, why cannot a new enum label be used before the transaction containing `ALTER TYPE` commits?

### Exercise 20 — PL/pgSQL exception

Explain why a block with `EXCEPTION` creates a subtransaction.

### Exercise 21 — Variables

When an exception occurs in a PL/pgSQL block, do database changes and PL/pgSQL variables roll back the same way?

### Exercise 22 — WHEN OTHERS

List conditions not caught by `WHEN OTHERS` and the risks of swallowing all errors.

### Exercise 23 — Diagnostics

Write a handler using `GET STACKED DIAGNOSTICS` to retrieve `SQLSTATE`, message, detail, and constraint name.

### Exercise 24 — ON CONFLICT

When should `ON CONFLICT` be used instead of catching `unique_violation`?

### Exercise 25 — Function vs procedure

Distinguish transaction control in functions, procedures, and `DO` blocks.

### Exercise 26 — Exception and COMMIT

Why cannot a procedure `COMMIT` while inside an `EXCEPTION` block?

### Exercise 27 — Dynamic SQL

Write dynamic DDL using `format %I`. Why does `EXECUTE` not bypass transaction restrictions?

### Exercise 28 — Migration runner

A framework automatically wraps every migration in `BEGIN`/`COMMIT`. How do you organize a migration that contains `CREATE INDEX CONCURRENTLY`?

### Exercise 29 — psql -1

Why is `psql --single-transaction` unsuitable for scripts containing `VACUUM` or `CREATE INDEX CONCURRENTLY`?

### Exercise 30 — Lock timeout

Write a migration using `SET LOCAL lock_timeout` and `statement_timeout`. Explain how to handle a lock timeout when it occurs.

### Exercise 31 — NOT VALID constraints

Design a two-phase `ADD CONSTRAINT NOT VALID` and `VALIDATE CONSTRAINT` workflow for a large table.

### Exercise 32 — Batch backfill

Write a batch update pattern using `FOR UPDATE SKIP LOCKED` and explain the benefits of small transactions.

### Exercise 33 — Sequence rollback

Why can `nextval` advance even when a transaction rolls back?

### Exercise 34 — External side effects

A migration calls an external service and then rolls back. Why does the remote side effect not disappear automatically?

### Exercise 35 — Migration ledger

Design migration states for a non-atomic concurrent index build that can fail midway.

### Exercise 36 — Invalid index recovery

Write a runbook from failure message to catalog inspection, duplicate cleanup, dropping the invalid index, and retrying.

### Exercise 37 — Subscription recovery

A subscription was created locally, but the publisher slot state is unexpected. Explain how to investigate before dropping/recreating.

### Exercise 38 — DDL blocking

An `ALTER TABLE` has been waiting on a lock for 2 minutes. Which sessions/transactions should you inspect, and how should `lock_timeout` be configured?

### Exercise 39 — Rehearsal

Design a staging rehearsal for a migration combining transactional `ALTER TABLE`, `CREATE INDEX CONCURRENTLY`, `VACUUM`, and an extension update.

### Exercise 40 — End-to-end migration

A release needs to add an enum label, create a concurrent unique index, backfill millions of rows, add a `CHECK` constraint, run `VACUUM`, and update the migration ledger. Split it into phases, transaction boundaries, validations, retry/cleanup steps, and a rollback plan. Note the differences if the source server is PostgreSQL 11 vs. PostgreSQL 12+.

---

## 40. Pre-Migration Checklist

| Item | Question to answer |
| --- | --- |
| PostgreSQL version | What are the source and target major versions? |
| Command classification | Is the command transactional or prohibited in a transaction block? |
| Version-specific behavior | Does behavior vary across versions? |
| Migration runner | Does the tool automatically issue `BEGIN`/`COMMIT`? |
| Autocommit | Is the client in autocommit or single-transaction mode? |
| Transaction scope | Which group of DDL needs to be atomic? |
| Savepoints | Are recovery points needed before optional steps? |
| Error handling | Which `SQLSTATE`/conditions are handled? |
| Non-transactional step | Has it been separated into its own file/runner mode? |
| Concurrent index | Are validity checks and cleanup in place? |
| Replication side effects | Have slot and remote publisher states been checked? |
| ALTER SYSTEM | Are config ownership and restart plans clear? |
| VACUUM | Is it running outside a transaction block? |
| CREATE DATABASE | Is it running separately at cluster scope? |
| TABLESPACE | Are filesystem paths, ownership, and backup mappings ready? |
| Lock behavior | What are the expected lock levels and blockers? |
| Timeouts | Are `lock_timeout`/`statement_timeout` appropriate? |
| Backfill | Is it batched and idempotent? |
| DDL duration | Have table size and maintenance window been accounted for? |
| Data validation | Are postconditions verifiable? |
| Migration ledger | Is success recorded only after post-checks? |
| Retry | Can it be re-run safely? |
| Cleanup | How are partial/invalid objects handled? |
| External effects | Is there a compensation/reconciliation plan? |
| Backup | Are the restore point and rollback path ready? |
| Rehearsal | Was it run with equivalent dataset and tool versions? |
| Monitoring | Are lock waits, WAL, I/O, and latency monitored? |
| Owner | Is an owner assigned for each phase? |
| Audit | Are commands, timestamps, outputs, and operator recorded? |

## Conclusion

Transactional DDL enables PostgreSQL to change schemas atomically: a single transaction can create, modify, or drop multiple objects and commit or roll back together. However, certain commands such as `CREATE`/`DROP DATABASE`, `TABLESPACE`, `ALTER SYSTEM`, `VACUUM`, and concurrent index operations must run outside a transaction block. Replication operations carry side effects on remote slots, and some DDL rules depend on the major version.

Key principles to remember:

1. **Most regular DDL is transactional.** Group related schema changes into small transactions to preserve atomicity.
2. **SQL errors abort the transaction.** After an error, you must `ROLLBACK` or `ROLLBACK TO SAVEPOINT` before continuing.
3. **Savepoints only create recovery points.** They do not commit the outer transaction.
4. **Not all commands run inside a transaction block.** Separate `CREATE`/`DROP DATABASE`, `TABLESPACE`, `ALTER SYSTEM`, `VACUUM`, and concurrent index operations.
5. **CREATE INDEX CONCURRENTLY is not atomic like regular DDL.** It spans multiple phases and can leave an invalid index after failure.
6. **IF NOT EXISTS does not guarantee an existing object is valid.** Verify catalog postconditions.
7. **Replication commands have external side effects.** Check publisher slots and subscription state before retrying or dropping.
8. **Enum DDL has version differences.** PostgreSQL 12+ allows `ADD VALUE` inside a transaction, but the new value is only usable after commit.
9. **EXCEPTION blocks use subtransactions.** Database changes inside the failing block roll back, while the outer block can continue.
10. **Functions and procedures have different transaction permissions.** Transaction control in procedures/`DO` blocks depends on call context and cannot run inside an exception subtransaction.
11. **The migration runner determines the actual transaction boundary.** Inspect framework behavior, `psql` flags, and autocommit settings.
12. **DDL can hold locks until COMMIT.** Keep transactions short, set timeouts, and monitor blockers.
13. **Large backfills should be batched.** Design for idempotency, progress tracking, and retries.
14. **External side effects require separate recovery.** PostgreSQL rollback does not undo remote calls or all sequence effects.
15. **Post-checks are mandatory for non-atomic steps.** Verify index validity, constraints, subscriptions, schemas, and the migration ledger before marking success.

A safe migration starts with classifying every command, defining transaction boundaries, anticipating locks and failure modes, and designing ways to verify or recover state. When you clearly know which commands are atomic and which have exceptions, you can roll out schema changes under control without letting a migration runner accidentally turn a special operation into a production outage.
