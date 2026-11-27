# Flyway, Liquibase, and PostgreSQL Migration Testing Workflows

Schema changes are a routine part of application development: adding tables, changing data types, creating indexes, adding constraints, transforming data, and dropping old structures. If these changes are run manually across environments, source code and databases easily drift out of version sync. One server might already have a column while another lacks it; a migration might run twice; or a new application version might deploy before the schema is ready.

Flyway and Liquibase manage database changes using versioned migrations, execution history, and change detection mechanisms. Flyway typically organizes SQL migrations by file name and version; Liquibase organizes changes into changesets within XML, YAML, JSON, or SQL changelogs. Both integrate into CI/CD pipelines to test migrations against PostgreSQL before deployment.

Migration tools do not replace schema design, lock impact analysis, or rollback planning. A migration that passes on an empty database can still fail when upgrading large production datasets. A sound workflow tests both fresh installation and upgrade paths from currently running versions, measures runtime/locks, verifies data, and rolls out in steps compatible with applications.

~~~text
       Developer changes schema / application
                       |
                       v
             Migration source files
                 /           \
                v             v
             Flyway        Liquibase
                \             /
                 \           /
                  v         v
              CI migration validation
                       |
              +--------+---------+
              |                  |
              v                  v
         Fresh database    Upgrade fixture
              |                  |
              +--------+---------+
                       |
                       v
               Schema/data tests
                       |
                       v
                Review & approval
                       |
                       v
                Deployment runner
                       |
                       v
               PostgreSQL target
                       |
             History / lock tables
                       |
                       v
              Observe and verify
~~~

This lesson belongs to the **Schema Migrations** chapter of the *Database Engine Relational PostgreSQL* module, focusing on Flyway, Liquibase, and repeatable, controlled, production-safe migration testing workflows.

## 1. Learning Objectives

After this lesson, you can:

1. Explain why schema changes should be managed as migration files.
2. Distinguish between Flyway versioned and repeatable migrations.
3. Understand Flyway naming conventions and execution ordering.
4. Explain schema history, checksums, `validate`, `info`, and `repair`.
5. Distinguish Liquibase changelogs, changesets, `id`, `author`, and `path`.
6. Understand `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK`.
7. Author PostgreSQL SQL migrations using both tools.
8. Choose between SQL-first and declarative changelog formats.
9. Control migration ordering and object dependencies.
10. Handle migrations already executed in shared environments.
11. Design appropriate rollbacks or forward fixes.
12. Understand DDL transaction behavior and PostgreSQL exceptions.
13. Manage index creation, constraints, enums, and partition changes.
14. Use expand-contract to deploy schemas compatible with multiple app versions.
15. Backfill large datasets in batches.
16. Control `lock_timeout`, `statement_timeout`, and lock impacts.
17. Test migrations on both fresh databases and populated historical databases.
18. Verify schemas, data invariants, indexes, permissions, and query behavior.
19. Integrate migration validation into CI/CD.
20. Deploy migrations with a single serialized runner and observe outcomes.
21. Protect credentials and migration execution privileges.
22. Troubleshoot failures, migration drift, and cross-environment discrepancies.
23. Build review, release, rollback, and incident response procedures.

## 2. Why Is Migration Management Needed?

The database schema is part of the deployed application. If code changes without the schema evolving properly, applications error on reads/writes or produce inconsistent data.

### 2.1. Change history

Migration files document how the database evolved over time. A new developer can build a schema from scratch by applying all migrations in sequence.

### 2.2. Repeatability

The same migration suite can run across local, test, staging, and production environments. This eliminates discrepancies caused by manual operations.

### 2.3. Applied state tracking

Flyway and Liquibase store history of executed changes. The runner knows which changes are pending and avoids re-applying completed changesets per tool mechanics.

### 2.4. Integrity verification

Checksums detect whether a migration file changed after execution. Validation catches drift between artifacts and database history.

### 2.5. Pre-deployment review

Migration SQL goes through code review, enabling inspection of locks, data rewrites, index builds, privileges, and application release compatibility.

### 2.6. No tool automatically guarantees safe migrations

A syntactically valid `ALTER TABLE` statement can still wait long on locks, rewrite a massive table, or break older applications. Tools manage ordering and history; humans must still assess impact.

## 3. Flyway vs. Liquibase: Comparing Approaches

| Criterion | Flyway | Liquibase |
| --- | --- | --- |
| Unit of change | Migration file | Changeset |
| Definition format | SQL or Java migrations; repeatable SQL common | XML, YAML, JSON, formatted SQL, and extensions |
| Versioning | `V...` migration names | Changelog order and changeset identity |
| History | `flyway_schema_history` | `DATABASECHANGELOG` |
| Lock coordination | Flyway locking/history mechanism | `DATABASECHANGELOGLOCK` |
| Checksum | Stores checksum of applied migrations | Stores checksum of changesets |
| Rollback | Can use undo migrations in supported configs/editions; forward fix is common | Supports rollback blocks or built-in rollback for change types |
| Best suited for | Simple, clear SQL-first workflows | Changelogs describing diverse change types and preconditions |
| PostgreSQL-specific SQL | Direct SQL migrations | SQL changesets or external SQL files |

### 3.1. Flyway

Flyway typically uses versioned files following `V1__description.sql`, `V2__description.sql`. The tool records version, description, checksum, and status in the schema history table.

### 3.2. Liquibase

Liquibase uses changelogs to declare changesets. Each changeset has an `id`, `author`, and file/path identifier. You can use raw SQL or structured change types.

### 3.3. Do not run both tools on the same schema without design

If Flyway and Liquibase both manage one schema without clear ownership boundaries, history and ordering can diverge. Pick one migration authority per database/schema or define strictly independent boundaries.

### 3.4. SQL-first

PostgreSQL has many engine-specific features. SQL-first lets you use full PostgreSQL syntax and review the exact statements that will execute.

### 3.5. Declarative changelogs

Liquibase change types help express intent and support multiple database engines. However, abstractions may not capture PostgreSQL-specific behavior fully; use raw SQL when exact control is needed.

### 3.6. Base the choice on team workflow

Consider team familiarity, SQL review practices, multi-database needs, rollback requirements, deployment integration, and long-term changeset maintenance.

## 4. General Principles for Writing Migrations

A migration is a deployed artifact. Once a migration has run on a shared environment, treat its content as immutable.

### 4.1. One migration, one clear purpose

Each file/changeset should perform one meaningful, reviewable change. Avoid bundling unrelated changes that make failures harder to diagnose.

### 4.2. Deterministic ordering

Use explicit versions or changelog order. Never rely on undefined filesystem ordering.

### 4.3. Never edit an already-run migration

If V12 already ran in staging or production, do not edit V12 to alter logic. Create a new migration V13 to adjust state.

### 4.4. Migrations must be reviewable

SQL should be readable, making impact on data volume, locks, constraints, defaults, indexes, and application versions clear.

### 4.5. Idempotency is not the sole goal

A versioned migration normally runs once. Do not wrap every statement in `IF NOT EXISTS` to hide drift. If an object unexpectedly exists, stop and investigate why.

### 4.6. Fail fast

Use `psql` `ON_ERROR_STOP` in scripts, transactions where appropriate, and preconditions to prevent continuing after errors.

### 4.7. Never embed secrets

Never store passwords, API tokens, private keys, or production credentials inside migration source files.

### 4.8. Data migrations must be bounded

Large table backfills must use batching, progress tracking, resumability, and lock/replication throttling.

## 5. Flyway: Project Structure

A simple project can be organized as:

~~~text
project/
  src/
    main/
      resources/
        db/
          migration/
            V1__create_customer.sql
            V2__create_orders.sql
            V3__add_order_status.sql
            R__customer_summary_view.sql
  flyway.conf
~~~

### 5.1. Migration locations

Flyway scans configured locations for migration files. In Java applications, `db/migration` on the classpath is standard; CLI usage can point to filesystem locations.

### 5.2. Versioned migrations

Files `V1`, `V2`, `V3`... execute in version order. Versions can be multi-part, such as `V2.1` or `V2026.11.14.1`, depending on project convention.

### 5.3. Description

The portion after the double underscore describes intent. Keep names short, clear, and consistent.

### 5.4. Repeatable migrations

Files starting with `R__` are typically used for objects replaceable when definitions change, such as views or functions. Flyway runs repeatable migrations whenever their checksum changes, after pending versioned migrations, in repeatable ordering.

### 5.5. Java migrations

Java migrations can be used when logic is awkward to express in SQL. However, SQL is generally easier to audit and review for PostgreSQL schema changes.

### 5.6. Naming consistency

Do not arbitrarily rename versions or descriptions after a migration has run. Keep conventions uniform across modules and teams.

## 6. Flyway: Writing Versioned Migrations

Example creating the `customer` table:

~~~sql
-- V1__create_customer.sql
CREATE TABLE app.customer (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX customer_email_uq
    ON app.customer (email);
~~~

### 6.1. Schema must exist first

If schema `app` does not exist yet, create it in a prior migration or use a managed bootstrap schema. Never assume a schema exists in every environment.

### 6.2. Naming

File names must strictly match Flyway's configured pattern. A naming mistake can cause Flyway to ignore the migration.

### 6.3. SQL ordering

Create schemas before tables, tables before dependent indexes/constraints, and functions before triggers calling them.

### 6.4. Transactions

Flyway normally runs SQL migrations in transactions if supported by the database and migration. Certain PostgreSQL commands cannot run inside a transaction block; configure migration execution appropriately.

### 6.5. Subsequent changes

To add a column later, create `V2__add_customer_phone.sql`. Never go back and edit V1 after it has run.

~~~sql
-- V2__add_customer_phone.sql
ALTER TABLE app.customer
    ADD COLUMN phone_number text;
~~~

## 7. Flyway: Schema History, Checksums, and Common Commands

Flyway stores history in `flyway_schema_history` in the configured schema.

### 7.1. Schema history

This table records version, description, type, script, checksum, `installed_by`, `installed_on`, `execution_time`, `success`, and related fields.

### 7.2. migrate

~~~bash
flyway migrate
~~~

Applies pending versioned migrations and repeatable migrations needing updates.

### 7.3. info

~~~bash
flyway info
~~~

Displays applied, pending, and failed/resolved migrations and related state.

### 7.4. validate

~~~bash
flyway validate
~~~

Compares current migration files against stored history, including checksums and metadata per configuration. `validate` does not prove runtime schema or data are completely accurate.

### 7.5. repair

~~~bash
flyway repair
~~~

`repair` adjusts history metadata per Flyway rules, such as removing failed migration entries or realigning checksums. It does not fix schemas or re-run failed SQL. Use only after confirming exact database state and root cause.

### 7.6. baseline

`baseline` marks an existing database as a starting point for Flyway to manage subsequent migrations. Use when adopting Flyway on an existing schema; do not treat baselining as a full schema audit.

### 7.7. clean

`clean` drops objects in configured managed schemas. It is destructive to data and schemas; never enable or run it on production. Restrict it strictly to disposable test databases.

### 7.8. undo

Some Flyway versions/editions support undo migrations. Check licensing/version and write undo scripts if required by workflow. Never assume every SQL migration automatically rolls back.

## 8. Flyway: Repeatable Migrations

Repeatable migrations are useful for definitions replaced wholesale when source changes.

### 8.1. Views

~~~sql
-- R__customer_summary_view.sql
CREATE OR REPLACE VIEW app.customer_summary AS
SELECT
    c.customer_id,
    c.email,
    count(o.order_id) AS order_count
FROM app.customer AS c
LEFT JOIN app.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.email;
~~~

### 8.2. Functions

~~~sql
-- R__normalize_email.sql
CREATE OR REPLACE FUNCTION app.normalize_email(value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT lower(btrim(value));
$$;
~~~

### 8.3. When to use

Repeatable migrations suit views, functions, procedures, or reference data scripts designed to re-run whenever their checksum changes.

### 8.4. Do not use for arbitrary data backfills

A repeatable migration re-runs whenever content changes. If a script runs non-idempotent large `UPDATE`s or causes side effects, it can unintentionally repeat changes.

### 8.5. Versioned vs. repeatable?

Use versioned migrations for one-time ordered historical changes. Use repeatable migrations for object definitions re-applied in full when source changes.

## 9. Flyway: Configuration and Environments

Configuration can come from files, command-line flags, environment variables, or application integrations.

### 9.1. Example configuration

~~~properties
flyway.url=jdbc:postgresql://localhost:5432/appdb
flyway.user=migration_runner
flyway.locations=filesystem:./sql/migrations
flyway.schemas=app
flyway.defaultSchema=app
flyway.validateOnMigrate=true
~~~

Property prefix syntax can vary across Flyway CLI, Maven/Gradle plugins, and API versions. Check documentation for your installed version.

### 9.2. Separate credentials

Never commit `flyway.password` to source control. Inject via a secret store or protected CI variables.

### 9.3. Per-environment config

URL, username, schemas, and connection settings vary by environment; migration source files should stay identical.

### 9.4. Placeholders

Flyway supports configurable placeholders. Use them for controlled identifiers/config—never to inject secrets into SQL history or logs.

### 9.5. Schema history table

Specify the history schema/table explicitly so multiple applications do not accidentally share one history table.

### 9.6. Migration runners

In production, designate a single deployment job/runner as migration owner. Avoid letting every application replica auto-migrate on startup without a verified locking/coordination strategy.

## 10. Liquibase: Changelogs and Changesets

Liquibase describes database changes in a changelog. A changelog can include child files organized by module or release.

### 10.1. Changeset identity

A changeset is identified by `id`, `author`, and changelog path. Never reuse an identity for a different change.

### 10.2. XML example

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="001-create-customer" author="platform">
        <sql>
            CREATE TABLE app.customer (
                customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                email text NOT NULL,
                display_name text NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            );
        </sql>
    </changeSet>
</databaseChangeLog>
~~~

In real projects, use the `schemaLocation`/version recommended by your pinned Liquibase release rather than relying on an unpinned `"latest"` reference.

### 10.3. YAML example

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-phone
      author: platform
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: phone_number
                  type: varchar(40)
~~~

### 10.4. Formatted SQL

Liquibase also supports formatted SQL changelogs using header and changeset comment markers. This keeps PostgreSQL SQL close to native form.

### 10.5. Includes

A root changelog can include changelogs by module or release. Keep include ordering explicit and avoid accidentally including the same changeset multiple times.

### 10.6. One changeset, one purpose

Scope changesets so failures and rollbacks remain easy to reason about. Avoid giant changesets packing dozens of unrelated operations.

## 11. Liquibase: DATABASECHANGELOG and Locks

Liquibase stores metadata in dedicated management tables.

### 11.1. DATABASECHANGELOG

This table records executed changesets, including `id`, `author`, `filename`, execution order/date, checksum, description, contexts/labels, and deployment metadata depending on version.

### 11.2. DATABASECHANGELOGLOCK

This lock table ensures only one Liquibase process holds permission to execute the changeset sequence at a time for a given database.

### 11.3. Lock waits

If another deployment is running, a new process may wait on the lock. Investigate the process owner before clearing the lock.

### 11.4. Clear checksums

Liquibase provides `clearCheckSums` to force recomputing checksums. Never use it to mask unauthorized edits to already-run changesets. Determine why checksums differ and follow change-management policy.

### 11.5. Lock cleanup

Never delete lock rows or manually set `LOCKED=0` before confirming the prior process has actually terminated. Releasing a lock prematurely can allow two runners to execute concurrently.

### 11.6. History is not a schema diff

`DATABASECHANGELOG` shows which changesets ran. It does not prove a DBA or external tool has not altered the schema outside Liquibase.

## 12. Liquibase: Operational Commands

### 12.1. validate

~~~bash
liquibase validate
~~~

Checks changelog structure and metadata/validation rules. Does not substitute for running migrations against real PostgreSQL.

### 12.2. status

~~~bash
liquibase status
~~~

Shows unapplied changesets based on current database and changelog configuration.

### 12.3. update

~~~bash
liquibase update
~~~

Applies pending changesets.

### 12.4. updateSQL

~~~bash
liquibase updateSQL
~~~

Generates the SQL Liquibase plans to run without executing changes. Review the SQL output and execute it on PostgreSQL staging to confirm behavior.

### 12.5. rollback

Liquibase supports rollback by tag, count, or date depending on version and configuration. Rollback works only when changesets define rollback logic or use change types with built-in rollback support.

### 12.6. rollbackSQL

Generates planned rollback SQL for review before executing an actual rollback.

### 12.7. diff

Some workflows use `diff`/`diff-changelog` to compare schemas across databases. Diff tools cannot infer business intent and can produce SQL needing manual review.

### 12.8. Tagging

You can tag a database at release boundaries to support milestone-based rollback. Tags do not replace backups or restore testing.

## 13. Liquibase: Preconditions, Contexts, and Labels

These metadata controls govern where and under what conditions changesets execute.

### 13.1. Preconditions

Preconditions check database state before running a changeset, such as whether a schema/table/column exists or whether the database engine/version matches.

~~~xml
<changeSet id="003-add-status" author="platform">
    <preConditions onFail="HALT">
        <tableExists schemaName="app" tableName="orders"/>
        <not>
            <columnExists schemaName="app" tableName="orders" columnName="status"/>
        </not>
    </preConditions>
    <addColumn schemaName="app" tableName="orders">
        <column name="status" type="text"/>
    </addColumn>
</changeSet>
~~~

### 13.2. onFail

Options like `HALT`, `WARN`, `MARK_RAN`, or `CONTINUE` carry distinct semantics. Use `HALT` when unexpected state must abort deployment. Use `MARK_RAN` only after proving the database is in an equivalent state and policy permits it.

### 13.3. Contexts

Contexts categorize changesets for different environments or purposes. Never use contexts to skip schema structures required in production.

### 13.4. Labels

Labels filter changesets by release, component, or team. Keep label policies clear so required changesets are never accidentally omitted.

### 13.5. dbms

You can restrict a changeset to a specific database engine. Useful when sharing a changelog across multiple engines with differing SQL dialects.

### 13.6. Preconditions do not replace tests

A `tableExists` precondition only confirms a table exists; it does not prove its structure, data, and semantics are right.

## 14. Liquibase Rollback and Limitations

Rollback capability is useful, yet not every change has a safe inverse operation.

### 14.1. Explicit rollback

For instance, a changeset creating an index can define a rollback dropping that index:

~~~xml
<changeSet id="004-customer-created-index" author="platform">
    <sql>
        CREATE INDEX customer_created_at_idx
        ON app.customer (created_at);
    </sql>
    <rollback>
        <sql>
            DROP INDEX IF EXISTS app.customer_created_at_idx;
        </sql>
    </rollback>
</changeSet>
~~~

### 14.2. Data loss

Rolling back `DROP COLUMN` cannot recover lost values without a backup or separate data copy. Destructive DDL rollbacks are rarely symmetric.

### 14.3. Data transformations

If a changeset transforms data, rolling back requires preserving old values or defining a provably lossless reverse transform. Never assume type conversions automatically reverse without data loss.

### 14.4. SQL changesets

Raw SQL changesets generally require explicit rollback blocks. Inspect generated rollback SQL before trusting the rollback command.

### 14.5. Forward fixes

In production, creating a new corrective migration is usually safer and more auditable than altering history or attempting to invert a migration that already caused side effects.

### 14.6. Rollback plan vs. restore plan

Rolling back application/schema differs from restoring a database backup. Once new data has been written, restoring a backup loses writes made after the backup. Design recovery around RPO and RTO.

## 15. PostgreSQL DDL and Transaction Behavior

PostgreSQL supports transactional DDL for many operations: if a transaction rolls back, schema changes within that transaction normally roll back too. However, certain commands cannot run inside a transaction block, and some operations have special locking or side effects.

### 15.1. Transactional DDL

Example:

~~~sql
BEGIN;

ALTER TABLE app.customer
    ADD COLUMN preferred_name text;

CREATE INDEX customer_preferred_name_idx
    ON app.customer (preferred_name);

COMMIT;
~~~

If the transaction fails before `COMMIT`, both changes roll back together.

### 15.2. CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block:

~~~sql
CREATE INDEX CONCURRENTLY customer_email_idx
ON app.customer (email);
~~~

The migration runner must allow this statement to execute outside a transaction. Exact configuration differs across Flyway/Liquibase versions and integrations; check documentation and test in CI.

### 15.3. REINDEX CONCURRENTLY

Forms of `REINDEX CONCURRENTLY` also cannot run inside a transaction block. Confirm syntax and restrictions for your PostgreSQL version.

### 15.4. VACUUM

`VACUUM` cannot run inside an ordinary transaction block. Never bundle `VACUUM` inside a changeset/migration that the runner automatically wraps in a transaction.

### 15.5. CREATE DATABASE

`CREATE DATABASE` cannot run inside a transaction block. Typically database provisioning is separated from schema migrations.

### 15.6. ALTER SYSTEM

`ALTER SYSTEM` modifies server configuration and is not a standard schema migration. Manage it separately through infrastructure/configuration management.

### 15.7. Enum changes

`ALTER TYPE ... ADD VALUE` has version-dependent transaction rules in PostgreSQL; on versions allowing execution inside a transaction, the new enum value cannot be used until that transaction commits. Separate adding the value from data migrations using that value into distinct steps.

### 15.8. Transaction policy

Do not disable transactions for an entire migration just because one statement lacks transaction support. Split non-transactional operations into dedicated migrations and keep transactions enabled for other changes where appropriate.

## 16. Lock Impact and Safe Migrations

DDL can require strong table locks. A fast statement on a small dev table can wait very long in production if a long transaction is active.

### 16.1. Lock acquisition

`ALTER TABLE` normally requires a relatively strong lock; exact lock levels depend on the operation. When the lock is unavailable, the command waits and can queue subsequent queries.

### 16.2. lock_timeout

Set a bound on lock wait time so migrations fail fast instead of waiting indefinitely:

~~~sql
SET lock_timeout = '3s';
SET statement_timeout = '15min';

ALTER TABLE app.orders
    ADD COLUMN source_code text;

RESET lock_timeout;
RESET statement_timeout;
~~~

If the runner wraps migrations in a transaction automatically, place `SET`/`RESET` deliberately within the same transaction. Use `SET LOCAL` when running inside a transaction.

### 16.3. statement_timeout

`statement_timeout` bounds total statement runtime, including lock wait time. Choose values fitting the operation and deployment window.

### 16.4. Long transactions

A long-open transaction can hold locks or snapshots and block DDL. Before migrating, inspect `pg_stat_activity`, transaction ages, and prepared transactions.

### 16.5. Lock queues

DDL waiting on a lock can cause incoming queries to queue behind it depending on lock conflicts. Abort the migration if widespread blocking appears.

### 16.6. NOWAIT

Some operations support `NOWAIT` or `lock_timeout` to fail fast. Use them when you want the migration to probe for a lock in a short window and retry later.

### 16.7. Online index builds

`CREATE INDEX CONCURRENTLY` minimizes write blocking compared to regular builds, yet takes longer, consumes more I/O, and can fail leaving an invalid index requiring cleanup.

### 16.8. Review lock levels

Read PostgreSQL documentation for your specific operation and version. Never infer lock modes from the `ALTER TABLE` name alone.

## 17. Expand-Contract Deployments

Expand-contract enables schemas and multiple application versions to operate concurrently during rollout.

### 17.1. Expand

Add new structures backward-compatibly—for example, adding a nullable column or new table—without removing old columns yet.

### 17.2. Deploy compatible application

Deploy code capable of reading/writing the new structure while continuing to work alongside application instances still running the old version.

### 17.3. Backfill

Populate new structures from existing data in batches, monitoring progress and consistency.

### 17.4. Switch reads

After backfilling and validation finish, switch application reads to the new column/table.

### 17.5. Stop old writes

Wait until all old app instances are replaced and no jobs or consumers still write to old structures.

### 17.6. Contract

In a separate release, drop old columns, tables, and indexes once confirmed zero code or reports depend on them.

### 17.7. Why split releases?

If adding and dropping occur in the same deploy, older application instances can error mid-rollout. Expand-contract creates a compatibility window for safe rolling deployments.

### 17.8. Example: renaming a column

Never rename a column immediately while old apps still use the old name. Add a new column, dual-write cleanly or use a temporary trigger, backfill, switch reads, stop old writes, and finally drop the old column.

## 18. Large Data Backfills

Backfills can run for hours and generate WAL, bloat, replication lag, or lock contention.

### 18.1. Batching

Use primary key ranges or keyset pagination rather than one massive full-table `UPDATE`.

~~~sql
UPDATE app.customer
SET normalized_email = lower(btrim(email))
WHERE customer_id > 100000
  AND customer_id <= 110000
  AND normalized_email IS NULL;
~~~

Iterate across batches with separate commits, recording the last processed key and updated row counts.

### 18.2. Resumability

Backfills should maintain checkpoints or `WHERE` predicates allowing re-execution without re-updating already processed rows.

### 18.3. Throttling

Tune batch size, pause intervals, and concurrency based on replication lag, WAL generation, CPU, I/O, and application latency.

### 18.4. Idempotent updates

Use predicates selecting only unprocessed rows. Ensure transformation logic is safe if re-applied.

### 18.5. Concurrent writes

If the application continues writing during backfilling, use dual-writes or a catch-up mechanism so new rows are not missed. Expand-contract requires clear write ownership.

### 18.6. Do not run massive backfills inside schema migrations

Separate schema DDL from large data backfill jobs. This keeps deployments shorter and easier to observe and control.

### 18.7. Validation

Count remaining `NULL` rows, verify transformation samples, and run aggregate checks before switching reads.

## 19. Safely Adding Constraints on Large Tables

Certain PostgreSQL operations allow separating enforcement from validation.

### 19.1. CHECK NOT VALID

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT orders_amount_nonnegative
CHECK (amount >= 0) NOT VALID;
~~~

The new constraint applies to newly inserted/updated rows per PostgreSQL semantics, while existing data is not yet scanned for verification.

### 19.2. Validate separately

~~~sql
ALTER TABLE app.orders
VALIDATE CONSTRAINT orders_amount_nonnegative;
~~~

Validation takes a lighter lock than direct validated constraint creation, though it still consumes I/O and should be scheduled carefully.

### 19.3. Foreign keys NOT VALID

You can add a foreign key `NOT VALID` and run `VALIDATE CONSTRAINT` after cleaning existing data. Test actual lock behavior and dependencies.

### 19.4. Unique constraints

A common strategy is building a unique index concurrently, verifying index validity, and attaching it as a constraint via `USING INDEX`. Check PostgreSQL version rules and transaction boundaries.

### 19.5. Clean data first

If historical data violates the constraint, locate and remediate rows before validation. Never use `NOT VALID` to ignore violations permanently.

## 20. Index Migrations on PostgreSQL

Index creation strongly impacts availability and I/O.

### 20.1. Standard CREATE INDEX

~~~sql
CREATE INDEX orders_created_at_idx
ON app.orders (created_at);
~~~

This operation can block writes during the build depending on lock mode. Better suited for small tables or controlled maintenance windows.

### 20.2. CREATE INDEX CONCURRENTLY

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON app.orders (created_at);
~~~

Allows `INSERT`/`UPDATE`/`DELETE` to continue during most of the build, at the cost of multiple scans and extra overhead.

### 20.3. Outside transaction blocks

Isolate concurrent commands from migration transactions. Configure Flyway/Liquibase per version to execute those changesets outside transactions when needed.

### 20.4. Failed concurrent indexes

If a concurrent build fails, it can leave an invalid index behind. Inspect `pg_index.indisvalid`/`indisready` and clean up deliberately before retrying.

### 20.5. IF NOT EXISTS does not guarantee the right index

An existing index with the same name but a different definition can prevent a migration from reaching the intended state. Compare `pg_get_indexdef` and catalog metadata.

### 20.6. Index size and disk

Account for temporary/final sizes and monitor free disk space. Concurrent builds require extra storage while existing indexes remain in place.

## 21. Data Types, Enums, and Object Dependencies

### 21.1. Enums

Adding enum values is a schema change requiring coordination with application releases. Never let an application emit a new enum label before all database instances carry the updated type.

### 21.2. Domains and composite types

Create types before functions or tables referencing them. Modifying types can ripple across wide dependency graphs.

### 21.3. Functions and procedures

Function/procedure definitions should use explicit migrations or repeatable definitions. Verify `search_path` and ownership.

### 21.4. Views and materialized views

Views depend on tables and columns. When schemas change, update views compatibly. Materialized views may need refreshes whose runtime must be budgeted into rollouts.

### 21.5. Triggers

Create functions before triggers. When triggers mutate data, evaluate side effects, recursion, replication behavior, and lock impacts.

### 21.6. Extensions

Install extension OS packages on the server before running `CREATE EXTENSION`/`ALTER EXTENSION UPDATE`. Shared libraries must exist on every host that can run the database.

### 21.7. Ownership and grants

Schema migrations must preserve proper ownership and grants. The runner can execute as an owner role or via `SET ROLE`; avoid leaving production objects owned by ephemeral or non-existent roles.

## 22. Flyway and Liquibase in CI

CI should execute migrations against a temporary PostgreSQL database, not just parse SQL statically.

### 22.1. Fresh database tests

Create an empty database matching the target major version and extension dependencies, then execute all migrations.

### 22.2. Upgrade-path tests

Provision a database at a schema/data state close to production, load representative fixtures, and run pending migrations. This is critical because migrations passing on empty databases can fail on populated data.

### 22.3. PostgreSQL version parity

Match the production target major version. For cross-major upgrades, test both source and target versions in matching pairs.

### 22.4. Extension parity

Install matching extension versions, locales/collations, and required server settings.

### 22.5. Validate migration artifacts

Run `flyway validate` or `liquibase validate` to check metadata/changelogs. Then run `migrate`/`update` against real PostgreSQL to catch SQL and runtime issues.

### 22.6. SQL preview

Use `liquibase updateSQL` or your tool's dry-run/preview feature to review planned SQL. Previews do not replace execution tests.

### 22.7. Schema assertions

Verify columns, types, nullability, indexes, constraints, defaults, functions, triggers, grants, and ownership.

### 22.8. Data assertions

Verify row counts, aggregates, absence of duplicates, absence of orphans, and business invariants.

### 22.9. App compatibility

Run application integration tests against the migrated schema and, when possible, test rolling compatibility between old and new app versions.

### 22.10. Artifact immutability

CI/CD must deploy the exact migration artifact reviewed and built. Never synthesize different migration contents per environment outside controlled placeholders/configs.

## 23. Example End-to-End CI Workflow

~~~text
Pull request
    |
    v
Static review / lint SQL
    |
    v
Start PostgreSQL test service
    |
    v
Install required extensions
    |
    +-------------------------+
    |                         |
    v                         v
Fresh DB test            Upgrade fixture
    |                         |
    v                         v
Flyway migrate /         Restore prior schema
Liquibase update         and representative data
    |                         |
    v                         v
Schema + data tests      Apply pending migrations
    |                         |
    +------------+------------+
                 |
                 v
          Application tests
                 |
                 v
          Review SQL/lock plan
                 |
                 v
             Approve
                 |
                 v
          Staging migration
                 |
                 v
          Production runner
~~~

### 23.1. Pull request gate

Do not merge a migration if either the fresh install or upgrade-path test fails.

### 23.2. Parallel tests

Each CI job needs its own isolated database or schema. Never let two test runners mutate the same database simultaneously.

### 23.3. Test data

Fixtures should cover edge cases: `NULL`s, duplicates, large tables, long text, timezones, boundary dates, and existing constraints.

### 23.4. Performance tests

For major migrations, measure runtime, lock duration, WAL, disk growth, and replication lag on staging using near-production data volumes.

### 23.5. Approval gates

Production migrations require SQL review and deployment windows aligned with risk. Never auto-apply destructive migrations merely because CI passed.

## 24. Testing Migrations on PostgreSQL

A thorough test suite spans multiple layers.

### 24.1. Syntax and parsing

Verify file naming, changelog schemas, SQL syntax, and tool validation.

### 24.2. Execution

Run migrations on real PostgreSQL to verify permissions, transaction behavior, and server-specific features.

### 24.3. Repeatability

Create a fresh database and run all migrations. Run `validate`/`status` afterward to confirm consistent history.

### 24.4. Upgrade paths

Upgrade from every supported baseline version. If production spans multiple baseline versions, test each critical upgrade path.

### 24.5. Data correctness

Verify transformation results with SQL assertions. Do not check only the migration exit code.

### 24.6. Rollback and forward fixes

If using rollback scripts, test rollback SQL on a disposable database. If using forward fixes, verify recovery migrations can run cleanly after partial failures.

### 24.7. Lock behavior

Use a second session holding transactions/locks to test how the migration reacts to `lock_timeout`. Measure lock wait and blocking impact.

### 24.8. Concurrency

Test concurrent application reads and writes while the migration runs if rollout design requires online compatibility.

### 24.9. Failure injection

In a lab, inject controlled mid-migration errors to verify transaction rollbacks, history state, and recovery procedures. Never do this intentionally on production.

### 24.10. Restore tests

Backups and restores are part of migration risk management. Test restore capability whenever migrations include destructive operations.

## 25. Post-Migration Schema and Data Verification

### 25.1. Catalog inspection

Use `information_schema` and PostgreSQL catalogs to verify schema state.

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
ORDER BY table_name, ordinal_position;
~~~

### 25.2. Index definitions

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'app'
ORDER BY tablename, indexname;
~~~

### 25.3. Constraints

~~~sql
SELECT
    conrelid::regclass AS relation,
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'app'::regnamespace
ORDER BY relation::text, conname;
~~~

### 25.4. Invalid indexes

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready
FROM pg_index
WHERE NOT indisvalid OR NOT indisready;
~~~

### 25.5. Data invariants

Example checking that no `normalized_email` remains `NULL` after backfilling:

~~~sql
SELECT count(*)
FROM app.customer
WHERE normalized_email IS NULL;
~~~

### 25.6. Duplicate detection

~~~sql
SELECT email, count(*)
FROM app.customer
GROUP BY email
HAVING count(*) > 1;
~~~

### 25.7. Referential integrity

Check for orphan rows or constraint validation state. An existing `NOT VALID` constraint does not prove historical data complies.

### 25.8. Permissions

Confirm the application role holds necessary privileges without excessive permissions after migration.

## 26. Migration History and Schema Drift

History tables are an important record, yet not sole proof of schema state.

### 26.1. Drift

Schema drift occurs when databases are altered outside migration tools, or different migrations execute across environments.

### 26.2. Manual hotfixes

If a DBA applies an emergency hotfix directly in production, document it and capture the equivalent change in migration source. Otherwise, staging and fresh databases will fail to reproduce production.

### 26.3. Flyway checksum mismatches

A checksum mismatch usually means a migration file changed after application or a different artifact was used. Determine what actually ran and write a corrective migration rather than editing checksums arbitrarily.

### 26.4. Liquibase checksum mismatches

Changeset checksum mismatches also require investigation. Never run `clearCheckSums` to legitimize unreviewed edits.

### 26.5. Existing baselines

When bringing an existing database under management, compare the live schema against the baseline artifact. Baselining marks a starting milestone; it does not synchronize objects automatically.

### 26.6. Drift detection

Run schema diffs or catalog snapshots in CI or periodically. Review every discrepancy before writing corrective migrations.

## 27. Executing Migrations in Production

Production migrations require a runner with explicit authority and accountability.

### 27.1. Single runner

Use a deployment job or release task that runs migrations once. Never let every application pod run migrations concurrently on boot unless orchestration is explicitly designed and verified for it.

### 27.2. Locking

Flyway/Liquibase include coordination locks to prevent concurrent runs. Even so, enforce pipeline-level serialization so multiple releases do not race.

### 27.3. Credentials

Migration roles normally need broader DDL privileges than application runtime roles. Separate the two credentials and withhold DDL privileges from runtime apps.

### 27.4. Deployment ordering

For expand-contract:
1. Deploy expand migration.
2. Deploy compatible app version.
3. Backfill.
4. Switch reads/writes.
5. Deploy contract migration in a later release.

### 27.5. Time windows

Run migrations with lock or I/O impact inside appropriate windows. Online migrations still require notification and monitoring.

### 27.6. Observe

Monitor the migration process, PostgreSQL logs, `pg_stat_activity`, `pg_locks`, disk, WAL, replication lag, and application latency.

### 27.7. Stop conditions

Pause or abort per runbook if lock waits exceed thresholds, disk headroom drops low, replication lag spikes, or application errors exceed budgets.

### 27.8. Completion

Mark a release successful only after tool history, schema assertions, application smoke tests, and monitoring all pass.

## 28. Security and Separation of Duties

### 28.1. Migration role

Create a dedicated role for the deployment runner. Privileges can include ownership/DDL within managed schemas, but should not be superuser by default.

### 28.2. Runtime role

The application runtime receives only necessary DML/`EXECUTE` grants. Never allow applications to create or drop schemas during routine operations.

### 28.3. Secret management

Inject credentials at runtime and rotate per policy. Never embed passwords in changelogs, SQL comments, CI artifacts, or command logs.

### 28.4. Approvals

Destructive DDL such as `DROP TABLE`/`COLUMN`, heavy data rewrites, or truncates require appropriate review and approval.

### 28.5. Auditing

Record who ran the migration, release ID, commit SHA, target database, timestamp, migration versions, and outcome.

### 28.6. Least privilege

If a migration needs elevated privileges, use a scoped temporary role or controlled elevated job, then revoke unneeded privileges afterward.

## 29. Common Anti-Patterns

### 29.1. Editing already-run migrations

Breaks checksums and causes environments to diverge. Create a new migration instead.

### 29.2. Running undocumented manual DDL

Creates schema drift. Record hotfixes in migration history through reviewed processes.

### 29.3. Putting huge backfills inside short migrations

Holds transactions/locks too long, spikes WAL, and hinders tracking. Isolate into separate data jobs.

### 29.4. Dropping immediately in the same release

Older application instances may still query the column or table. Use expand-contract.

### 29.5. Using IF NOT EXISTS to hide drift

The object may exist with the wrong definition. Validate state and fail if expectations are unmet.

### 29.6. Relying on automatic rollbacks

Not every DDL or data change has an inverse. Plan forward fixes, backups/restores, and data preservation.

### 29.7. Running multiple concurrent migration runners

Creates lock contention and unpredictable release ordering. Serialize deployments.

### 29.8. Testing only on empty databases

Misses issues with existing data, duplicates, `NULL`s, long locks, and table rewrites. Test upgrade fixtures.

### 29.9. Skipping review of generated SQL

Liquibase abstractions can generate unexpected SQL. Review `updateSQL` and execute on PostgreSQL staging.

### 29.10. Failing to measure locks

Even a "small" migration can wait on an `ACCESS EXCLUSIVE` lock. Measure locks and set `lock_timeout`.

## 30. Troubleshooting

### Issue 1. Flyway cannot find migrations

Check `locations`, filename patterns, classpath/filesystem paths, and artifact read permissions.

### Issue 2. Flyway validate checksum mismatch

Compare current files against deployed artifacts, history rows, and commit SHAs. Never repair checksums before understanding the drift.

### Issue 3. Flyway migration failed

Inspect errors and transaction behavior. Determine whether DDL rolled back completely or a non-transactional operation partially ran before running repair/retry.

### Issue 4. Flyway repair misused

`repair` only fixes history metadata per tool semantics; it does not repair schemas or data. Verify actual database state first.

### Issue 5. Liquibase changeset checksum changed

Determine where the changeset was applied and whether content changed. Create a new changeset if changes are needed.

### Issue 6. Liquibase lock not released

Confirm the prior runner stopped and no active process remains. Clear the lock only via official procedures after verification.

### Issue 7. Liquibase updateSQL differs from expectations

Review DBMS/version, changelog parameters, contexts/labels, and generated SQL. Run on PostgreSQL staging.

### Issue 8. CREATE INDEX CONCURRENTLY reports transaction block error

Isolate into a non-transactional migration and configure the runner appropriately. Do not drop `CONCURRENTLY` just to silence the error if production needs continuous writes.

### Issue 9. ALTER TABLE waiting on lock

Inspect `pg_stat_activity`/`pg_locks`, locate blockers, use `lock_timeout`, and retry in an appropriate window.

### Issue 10. Migration running long

Determine whether it is waiting on locks, scanning/rewriting a table, building an index, backfilling, or I/O bound. Do not blindly raise timeouts.

### Issue 11. Unique constraint failed

Find duplicate values, clean data first, build a unique index online if appropriate, and then attach the constraint.

### Issue 12. NOT NULL failed

Find `NULL` rows, backfill in batches, and validate before setting `NOT NULL`.

### Issue 13. Subscriber/replica lag spiked after DDL/backfill

Monitor WAL volume, index builds, backfill rate, and downstream capacity. Throttle the job.

### Issue 14. Old app version broke after migration

The schema change was not backward-compatible. Use expand-contract and app/schema rollback plans.

### Issue 15. Fresh install passes, upgrade fails

Existing fixtures have different data shapes or drift. Add upgrade-path tests from production baseline versions.

### Issue 16. Rollback lost data

DDL/data rollback was not invertible. Stop writes, restore/reconcile from backup, or apply a forward fix per incident plan.

### Issue 17. Role lacks privileges

Check object ownership and required grants; grant scoped schema/table privileges or run under the proper migration owner.

### Issue 18. Extension does not exist

Install OS packages/shared libraries before running `CREATE EXTENSION` or extension upgrades.

### Issue 19. Differing search_path

Use schema-qualified object names in migrations so objects are never created in the wrong schema.

### Issue 20. Migration ran twice

Inspect history/lock tables, deployment concurrency, and app auto-migration behavior. Serialize runners and recover state per tool rules.

## 31. Complete Migration Testing Workflow

~~~text
1. Author migration
       |
       v
2. Review SQL / changelog
       |
       v
3. Validate tool metadata
       |
       v
4. Fresh PostgreSQL database test
       |
       v
5. Upgrade from prior schema fixture
       |
       v
6. Assert schema and data
       |
       v
7. Test app compatibility
       |
       v
8. Measure locks / runtime / WAL
       |
       v
9. Stage deployment
       |
       v
10. Production migration runner
       |
       v
11. Smoke tests and monitoring
       |
       v
12. Record release evidence
~~~

### 31.1. Source review

Review migration files, naming, ordering, DDL semantics, privileges, data transformations, and rollback/forward-fix plans.

### 31.2. Tool validation

Run `flyway validate` or `liquibase validate` to check metadata/changelogs. Verify pinned tool version and configuration.

### 31.3. Fresh install

Create an empty DB, install extensions, and run all migrations. Confirm the final schema.

### 31.4. Upgrade fixtures

Restore schema/data from the prior release and run pending migrations. Include edge-case data and object dependencies.

### 31.5. Assertions

Verify catalogs, row counts, aggregates, constraints, indexes, permissions, and application tests.

### 31.6. Operational tests

Measure lock waits, execution duration, WAL, disk, and replication lag. Confirm migration runners do not execute concurrently.

### 31.7. Production release

Use the tested artifact, a single runner, a planned maintenance/rollout window, and clear stop conditions.

### 31.8. Evidence

Archive migration versions, commit SHA, execution times, logs, validation outputs, and approval records.

## 32. Example Flyway Workflow

An SQL-first workflow:

~~~text
db/migration/
  V1__create_schema.sql
  V2__create_customer.sql
  V3__add_customer_phone.sql
  V4__add_order_status.sql
  R__customer_summary_view.sql
~~~

### 32.1. V1

~~~sql
CREATE SCHEMA IF NOT EXISTS app;
~~~

### 32.2. V2

~~~sql
CREATE TABLE app.customer (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

### 32.3. V3

~~~sql
ALTER TABLE app.customer
ADD COLUMN phone_number text;
~~~

### 32.4. V4

~~~sql
ALTER TABLE app.orders
ADD COLUMN status text;
~~~

### 32.5. Repeatable view

~~~sql
CREATE OR REPLACE VIEW app.customer_summary AS
SELECT customer_id, email
FROM app.customer;
~~~

### 32.6. CI

~~~bash
flyway validate
flyway info
flyway migrate
flyway validate
~~~

Run in a disposable test database. Production runners use the exact same reviewed artifact/config with target credentials and deployment gates.

## 33. Example Liquibase Workflow

A root changelog can include changesets by release:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/001-create-schema.yaml
  - include:
      file: db/changelog/002-create-customer.yaml
  - include:
      file: db/changelog/003-add-customer-phone.yaml
~~~

### 33.1. Changeset

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: platform
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: customer_id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: text
                  constraints:
                    nullable: false
~~~

### 33.2. PostgreSQL-specific SQL

For engine-specific syntax or features, use `sql`/`sqlFile` changesets for exact statement control.

### 33.3. Preview

~~~bash
liquibase validate
liquibase status
liquibase updateSQL
~~~

Review SQL output before running `update` on PostgreSQL.

### 33.4. Apply test

~~~bash
liquibase update
liquibase status
~~~

### 33.5. Rollback review

~~~bash
liquibase rollbackSQL <tag-or-count>
~~~

Command syntax/arguments depend on Liquibase version. Verify rollback blocks and generated SQL on a test database.

## 34. Tool Selection Comparison Table

| Scenario | Considerations |
| --- | --- |
| SQL-first, PostgreSQL-only team | Flyway or Liquibase formatted SQL |
| Rich changeset metadata needed | Liquibase |
| Repeatable view/function scripts | Flyway repeatable migrations or equivalent Liquibase changesets |
| PostgreSQL-specific SQL needed | Both can execute raw SQL |
| Declarative rollback needed | Liquibase rollback blocks or Flyway undo where supported |
| Multiple database engines | Liquibase abstractions help, though generated SQL must be reviewed |
| Simple CI, versioned SQL | Flyway is often easier to organize |
| Schema drift across environments | Both need validate/history plus schema inspection |
| Huge data backfills | Separate job independent of migration tool |
| Online index creation | Both require proper non-transactional configuration |

## 35. Practice Exercises

Perform exercises on a dedicated PostgreSQL test database. Never run `clean`, drop schemas, or test destructive rollbacks in production.

### Exercise 1. Migrations

Why should schema changes be stored as migration files?

### Exercise 2. Flyway

What is the basic naming convention for Flyway versioned migrations?

### Exercise 3. Repeatable

Which kinds of database objects suit repeatable migrations?

### Exercise 4. Checksums

What issue do checksums help detect?

### Exercise 5. History

Which table does Flyway use by default to store migration history?

### Exercise 6. Validate

What does `flyway validate` do, and what does it not prove?

### Exercise 7. Repair

Why is `flyway repair` not a schema-fixing command?

### Exercise 8. Baseline

When is `baseline` used?

### Exercise 9. Clean

Why should `flyway clean` never run on production?

### Exercise 10. Liquibase

Which fields identify a changeset?

### Exercise 11. DATABASECHANGELOG

What information does this table store?

### Exercise 12. DATABASECHANGELOGLOCK

What role does this lock table serve?

### Exercise 13. Preconditions

What are preconditions used for?

### Exercise 14. Contexts

How do contexts and labels affect changeset selection?

### Exercise 15. Rollbacks

Why cannot every changeset roll back automatically and safely?

### Exercise 16. Transactional DDL

What does it mean that PostgreSQL supports transactional DDL?

### Exercise 17. Concurrent indexes

Why does `CREATE INDEX CONCURRENTLY` require a non-transactional migration?

### Exercise 18. VACUUM

Can `VACUUM` run inside a regular transaction block?

### Exercise 19. Lock timeout

Write SQL setting `lock_timeout` to 3 seconds.

### Exercise 20. Statement timeout

How does `statement_timeout` differ from `lock_timeout`?

### Exercise 21. Expand-contract

List the phases of an expand-contract deployment.

### Exercise 22. Renaming columns

Why should you avoid renaming or dropping a column immediately in the first release?

### Exercise 23. Backfills

Why should large backfills be split into batches?

### Exercise 24. Resumability

What properties does a resumable backfill need?

### Exercise 25. NOT VALID

Which two steps does `CHECK NOT VALID` separate?

### Exercise 26. Index failures

After `CREATE INDEX CONCURRENTLY` fails, what must be checked?

### Exercise 27. Fresh tests

What kinds of errors do fresh database tests catch?

### Exercise 28. Upgrade tests

Why must we test upgrading from older schema/data versions?

### Exercise 29. Data assertions

Name four types of data invariants that can be verified.

### Exercise 30. Migration runners

Why should production normally use a single serialized migration runner?

### Exercise 31. Schema drift

When does schema drift happen?

### Exercise 32. Manual hotfixes

What must a DBA do after a direct production hotfix to keep migration history consistent?

### Exercise 33. Role separation

Why separate the migration role from the application runtime role?

### Exercise 34. Search path

Why should object names be schema-qualified?

### Exercise 35. Liquibase preview

Which command generates planned SQL without executing changesets?

### Exercise 36. Flyway repeatable

When does a repeatable migration re-run?

### Exercise 37. Enums

Why must adding an enum value and using it be separated into appropriate steps/commits?

### Exercise 38. Rollback boundaries

When is a forward fix usually preferable to a rollback?

### Exercise 39. Production monitoring

Name five signals to monitor while a migration runs.

### Exercise 40. Workflow

Propose a CI/CD pipeline for testing and deploying PostgreSQL migrations.

## 36. Reference Solutions

### Exercises 1–9. Flyway

Migration files enable versioning, code review, schema reconstruction, and consistent execution. Flyway versioned files typically follow `V1__description.sql`. Repeatable migrations fit view/function/procedure definitions re-run when contents change. Checksums detect edits to migration files after application. The default history table is `flyway_schema_history`. `validate` compares artifacts against history metadata, though it does not prove all runtime objects/data are valid. `repair` fixes history metadata per tool semantics rather than running SQL to fix the schema. `baseline` marks the starting point for managing an existing database. `clean` destroys configured schemas/objects and must never run in production.

### Exercises 10–15. Liquibase

Changeset identity consists of `id`, `author`, and changelog path. `DATABASECHANGELOG` stores executed changesets and metadata/checksums. `DATABASECHANGELOGLOCK` coordinates so only one process updates at a time. Preconditions inspect database state before running a changeset. Contexts/labels filter changesets by environment, component, or release. Rollbacks may not invert data loss, external side effects, or raw SQL lacking rollback definitions.

### Exercises 16–20. PostgreSQL transactions and locks

Transactional DDL allows rolling back multiple schema changes within one transaction. `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block and requires an appropriate non-transactional execution mode. `VACUUM` cannot run inside an ordinary transaction block.

~~~sql
SET lock_timeout = '3s';
~~~

`lock_timeout` bounds lock wait time; `statement_timeout` bounds total statement runtime.

### Exercises 21–26. Deployment and backfilling

Expand-contract consists of expanding the schema, deploying compatible apps, backfilling, switching reads/writes, stopping old usage, and contracting/dropping old objects. Immediate renames/drops break older running app instances. Batch backfilling reduces transaction duration and lock/WAL bursts while enabling throttling. Resumability requires checkpoints or predicates selecting only unprocessed rows. `NOT VALID` separates constraint creation from validating existing data. After a concurrent index failure, inspect `pg_index.indisvalid`/`indisready` and clean up invalid indexes safely.

### Exercises 27–34. Testing and governance

Fresh tests catch migration chains unable to build a schema from scratch. Upgrade tests catch legacy data issues, duplicates, `NULL`s, and dependencies. Data invariants include counts, sums, uniqueness, referential integrity, non-`NULL` checks, and domain rules. A single runner enforces serialization and auditing. Schema drift comes from unrecorded out-of-band changes or mismatched artifacts. Hotfixes must be captured via corrective migrations. Role separation prevents runtime apps from holding broad DDL privileges. Schema qualification prevents `search_path` from placing objects in the wrong schema.

### Exercises 35–40. Pipeline and operations

`liquibase updateSQL` generates SQL previews. Flyway repeatable migrations re-run whenever their checksum changes. New enum values can only be used after the transaction adding them commits per PostgreSQL semantics. Forward fixes are preferable when rollbacks cannot invert data transformations or side effects. Monitor migration duration, lock waits, active blockers, CPU/I/O, WAL/replication lag, disk, and application errors.

Pipeline: review SQL/changelog; validate tool metadata; run fresh database test; run upgrade fixture test; assert schema/data; test app compatibility; measure locks/runtime/WAL; deploy staging; approve; run a single production migration runner; smoke test and monitor; archive evidence and release ID.

## 37. Quick Reference Table

| Need | Flyway | Liquibase / PostgreSQL |
| --- | --- | --- |
| Versioned change | `V1__name.sql` | Changeset `id`/`author` |
| Repeatable definition | `R__name.sql` | Appropriately configured changelog changeset |
| History | `flyway_schema_history` | `DATABASECHANGELOG` |
| Migration lock | Flyway coordination | `DATABASECHANGELOGLOCK` |
| Pending changes | `info` | `status` |
| Metadata validation | `validate` | `validate` |
| Apply changes | `migrate` | `update` |
| SQL preview | Version-specific preview mechanism | `updateSQL` |
| Repair metadata | `repair` | `clearCheckSums` only per policy |
| Baseline existing DB | `baseline` | Changelog baseline/tag/mark-ran workflow |
| Rollback | Undo if supported; forward fix common | Rollback blocks/commands |
| Non-transactional SQL | Per-migration transaction config | `runInTransaction=false` |
| Online PostgreSQL index | `CREATE INDEX CONCURRENTLY` | Raw SQL changeset outside transaction |
| Lock safety | `lock_timeout` in SQL | `lock_timeout` in SQL |
| Schema inspection | Catalog / `pg_dump` | Catalog / diff |
| Data backfill | Separate job | Separate job |
| CI validation | Fresh + upgrade tests | `validate` + `updateSQL` + execution tests |

## 38. Migration Testing and Deployment Checklist

1. Every migration has a clear purpose and owner.
2. Versions and changeset identities are never reused.
3. Files already applied in shared environments are never edited.
4. Schema-qualified names are used consistently.
5. Dependencies across schemas, tables, types, functions, and triggers are mapped.
6. PostgreSQL version and extension compatibility are verified.
7. Transaction behavior of every statement is verified.
8. Non-transactional operations are isolated separately.
9. `CREATE INDEX CONCURRENTLY` does not run inside a transaction block.
10. Lock impact and `lock_timeout` are evaluated.
11. `statement_timeout` fits the operation.
12. Large table rewrites/backfills are separated and estimated.
13. DDL is compatible with app versions during rolling deployments.
14. Expand-contract is used whenever a compatibility window is needed.
15. Backfills include batching, checkpoints, throttling, and validation.
16. Constraints are validated according to plan.
17. Fresh database tests pass.
18. Upgrade-path tests from historical schema/data pass.
19. Schema assertions pass.
20. Data invariants pass.
21. Indexes, constraints, permissions, and ownership are verified.
22. Application integration tests pass.
23. Liquibase generated SQL or Flyway artifacts are reviewed.
24. Checksum and history states are valid.
25. No unexplained schema drift exists.
26. A single serialized production migration runner is used.
27. Migration credentials are protected and separated from runtime roles.
28. Backup/restore and recovery options are verified.
29. Stop conditions and rollback/forward-fix plans are documented.
30. Locks, blockers, runtime, CPU, I/O, WAL, and disk are monitored.
31. Replication lag is monitored if standbys exist.
32. Post-migration smoke tests pass.
33. Release ID, commit SHA, and history state are archived.
34. Destructive contract changes run only once old application usage is zero.
35. Cleanup/retirement of artifacts happens only after migration stabilizes.

## 39. Summary

Flyway and Liquibase provide mechanisms for tracking schema change history, checksums, execution order, and coordinating migration runners. Flyway typically organizes SQL files into versioned and repeatable migrations; Liquibase organizes changelogs into changesets with `id`/`author`, preconditions, contexts/labels, and rollback metadata. Both can execute PostgreSQL-specific SQL when needed.

Tools cannot automatically decide whether DDL is safe for production. PostgreSQL offers transactional DDL for many operations, yet commands such as `CREATE INDEX CONCURRENTLY`, `VACUUM`, and `CREATE DATABASE` cannot run in normal transaction blocks. `ALTER TABLE` can wait on locks or trigger heavy table changes. Use `lock_timeout`, `statement_timeout`, online index strategies, `NOT VALID`/`VALIDATE CONSTRAINT`, and staging benchmarks to mitigate risk.

For rolling-deployment applications, expand-contract keeps schemas compatible across versions: expand the schema, deploy new code, backfill, switch reads/writes, and only then remove old structures. Large backfills need batching, checkpoints, and throttling. Migration testing must cover both fresh databases and upgrades from historical schemas/data, followed by verifying catalogs, data invariants, permissions, application behavior, and lock impact.

In production, serialize the migration runner, protect credentials, review generated SQL, and monitor blockers, WAL, replication lag, disk, and application errors. Once a migration has run, create a new migration to fix issues rather than rewriting history. When rollbacks cannot restore data or side effects, rely on prepared forward fixes and recovery plans. A pipeline built on repeatable testing and release evidence makes schema evolution a controllable part of the application lifecycle.
