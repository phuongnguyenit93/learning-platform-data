# Versioned Migrations and Change History Management in PostgreSQL

## 1. Why version database migrations?

An application changes over time: adding tables, changing data types, creating indexes, adding constraints, splitting columns, backfilling data, or dropping old structures. Those changes need to be deployed consistently across development, test, staging, and production environments.

If every deployment requires remembering to run a manual list of SQL statements, the system can easily drift out of sync. One environment might already have a column added while another does not; a script might be run twice; operators may not know which changes have been applied; and a rollback might not restore the data.

**Versioned migration** solves this problem by storing each database change as a migration with a clear identifier and order. The migration tool reads the applied history, identifies missing migrations, verifies integrity, and executes them in order.

Change history management needs to answer:
- Which migrations have run on this database?
- In what order, when, and by whom were they run?
- Which file/script was applied?
- Was the script content modified after deployment?
- Did the migration succeed or fail?
- Does the actual database schema still match the history?
- Can we recover or continue deploying safely?

```text
Source control
   |
   +-- V001__create_customers.sql
   +-- V002__add_customer_status.sql
   +-- V003__create_orders.sql
   |
   v
Migration runner
   |
   +-- Read migration files
   +-- Compare version/checksum with history
   +-- Serialize concurrent runners
   +-- Execute pending migrations
   +-- Record successful changes
   |
   v
PostgreSQL database
   |
   +-- Application schema
   +-- Migration history table
```

Migration versioning turns schema changes into a reviewable, testable, auditable, and reproducible part of the software development process.

### Learning Objectives

After this lesson, you can:

1. Explain versioned migrations and migration history.
2. Design migration naming, numbering, and ordering schemes.
3. Distinguish between versioned migrations, repeatable migrations, and baselines.
4. Understand checksums, immutability, and validation.
5. Design a migration history table and know when to use a dedicated tool.
6. Ensure a migration runs only once across multiple deployment runners.
7. Manage transactional and non-transactional migrations.
8. Understand locks, table rewrites, and DDL-induced downtime.
9. Design expand-contract patterns for zero-downtime deployments.
10. Backfill data in batches and resume safely after errors.
11. Test migrations in CI/CD and across multiple environments.
12. Handle schema drift, failed migrations, and repair.
13. Plan for rollback, roll-forward, and recovery.
14. Manage roles, ownership, privileges, and secrets.
15. Build auditing, monitoring, runbooks, and checklists for migrations.

---

## 2. What is a Migration?

A migration is an intentional change to a database schema or data, stored as a script or change set that can be re-executed across environments.

Examples of migrations:
- Creating the customers table.
- Adding the status column.
- Creating an index for a frequent query.
- Adding a foreign key.
- Moving data from an old column to a new column.
- Splitting a large table into two tables.
- Creating a view or materialized view.
- Modifying access permissions.
- Dropping an old column after the application has switched to the new column.

### 2.1. Schema migration

Changes to database structure: tables, columns, indexes, constraints, types, functions, triggers, views, schemas, and permissions.

### 2.2. Data migration

Changes or transformations to existing data, such as normalizing phone numbers, backfilling new values, or moving records to another structure.

### 2.3. Migrations can combine schema and data

For example, adding a new column, backfilling from an old column, and then creating a constraint. However, you should consider splitting them into multiple steps to limit locks, transaction duration, and risk.

### 2.4. A migration is a managed artifact

Scripts should live in source control, be reviewed, tested, versioned, and have an owner. Making changes directly in production without recording them in migration source creates schema drift.

## 3. What is Migration History?

Migration history is metadata recording which migrations have been applied to a database.

A history record typically includes:
- Version or change ID.
- Description.
- File/script name or changelog.
- Content checksum.
- Executing user or tool.
- Execution timestamp.
- Execution duration.
- Success/failure status or execution type.
- Migration tool version.

Tools can use a dedicated table in an administrative schema, such as a flyway/liquibase schema or a schema defined by the organization.

### 3.1. History answers deployment state

The runner compares migrations in the source repository against the history table to determine what work needs to be done.

### 3.2. History is not a copy of the schema

The history table only records which scripts the tool applied. It does not prove that a DBA has not modified a table manually or that a script created the exact expected structure.

### 3.3. History is critical operational data

Do not arbitrarily delete, modify, or truncate the history table. Doing so can cause the runner to re-run migrations or believe a migration has not been applied.

### 3.4. Each database has its own history

Development, staging, and production typically share the same migration source but have different histories due to deployment progress. Do not copy the history table between environments to "make them match".

## 4. Numbering and Naming Migrations

A clear naming convention helps both humans and tools read the execution order.

Example:

```text
V001__create_customers.sql
V002__add_customer_status.sql
V003__create_orders.sql
V004__add_orders_customer_index.sql
V005__backfill_customer_status.sql
```

Another convention uses timestamps:

```text
V2026111401__create_customers.sql
V2026111402__add_customer_status.sql
V2026111501__create_orders.sql
```

### 4.1. Versions must be unique

Do not allow two scripts to share the same version. If two branches create the same version, resolve the collision before merging or deploying.

### 4.2. Do not sort versions as arbitrary text

If a tool compares versions by numeric components, 1.10 is ordered after 1.9. If you write a custom runner and compare text lexicographically, the order can be wrong. Use a proper version parser.

### 4.3. Choose one convention and keep it stable

You can use an increasing sequence, timestamp, or semantic components. Avoid mixing multiple styles without clear rules.

### 4.4. Descriptions should be concise and express intent

A name like `add_customer_status` is clearer than `update_db_2`. Do not include secrets or sensitive information in file names.

### 4.5. The file name is part of the identity

When a tool stores the script name in history, renaming the file after deployment can cause validation to fail or hinder auditing. Keep names stable.

## 5. Versioned Migrations and Repeatable Migrations

Two common migration categories in tools like Flyway:

| Type | Characteristics | Examples |
|---|---|---|
| Versioned | Has a unique version, runs once in order | Create table, add column, alter constraint |
| Repeatable | No sequential version, re-runs when checksum changes | Recreate view/function/procedure |

### 5.1. Versioned migration

Once applied to a shared environment, treat the file as immutable. Subsequent changes are recorded in a new migration version.

### 5.2. Repeatable migration

Suitable for objects that can be recreated from a new definition, such as certain views or functions. Scripts must be designed to be idempotent or use an appropriate replace mechanism.

### 5.3. Do not use repeatable migrations to hide data migrations

A data backfill script should not re-run automatically just because its checksum changed. Use a versioned migration or a job with explicit checkpoints and idempotency.

### 5.4. Tools use different terminology

Liquibase uses changelog and changeset; Flyway uses versioned/repeatable migrations. Understand the semantics of the tool in use; do not apply one tool's terminology directly to another.

## 6. Migrations Must Be Immutable After Being Applied

A core principle: **do not modify a versioned migration that has already run on a shared environment**.

Example:
- V001 already created the `customers` table on staging.
- Later, you discover the `email` column is missing.
- Do not edit V001 to add `email`.
- Create `V006__add_customer_email.sql`.

### 6.1. Why is editing old files dangerous?

A fresh development environment may run the modified file, while production already ran the old content. Both databases record V001, yet their actual schemas differ.

### 6.2. Checksums detect modifications

Tools can store a checksum upon application. When the current file differs from the content that ran, validation reports a checksum mismatch.

### 6.3. Do not "fix checksum" to ignore the root cause

Repair/checksum updates should only be performed under a procedure that inspects both the schema and history. Updating a checksum does not automatically fix the schema.

### 6.4. New migrations correct old outcomes

Create a subsequent migration to supplement or correct the schema. Keep history intact for auditing and environment reproducibility.

## 7. Checksums and Validation

A checksum is a fingerprint computed from the migration file content. Tools can use checksums to detect whether a file was modified after deployment.

A validation process typically checks:
- Applied migrations still exist in source.
- Version/description/file identity matches.
- Current checksum matches the stored checksum.
- There are no duplicate versions or out-of-order migrations.
- There are no unexpected failed or pending states.

### 7.1. A checksum is not a security signature

Checksums detect unintended content changes, but they do not prove the file author is trustworthy or that the content is safe.

### 7.2. Checksums depend on tool/version

Line-ending normalization, encoding, or the checksum algorithm may depend on the tool. Do not compute a checksum differently from the tool and write it directly into history.

### 7.3. Source control is still essential

Checksums do not replace Git reviews, branch protection, code ownership, and release artifacts.

### 7.4. Validation must run before deployment

Run validation on staging/production before migrating to detect checksum drift and history inconsistencies before changing the schema.

## 8. Designing a Migration History Table

Migration tools usually manage their own history tables. If building a custom runner for learning purposes, you can envision a minimal ledger:

```sql
CREATE SCHEMA IF NOT EXISTS migration_admin;

CREATE TABLE migration_admin.schema_history (
    version          text PRIMARY KEY,
    description      text NOT NULL,
    script_name      text NOT NULL,
    checksum         text NOT NULL,
    installed_by     text NOT NULL,
    installed_at     timestamptz NOT NULL DEFAULT now(),
    execution_ms     bigint,
    success          boolean NOT NULL
);
```

This is an illustrative example of the data fields, not a direct replacement schema for Flyway or Liquibase.

### 8.1. Version as unique key

A primary key on `version` prevents the same migration from being recorded twice.

### 8.2. Checksum and script name

Helps link history to a specific artifact in the repository or release.

### 8.3. installed_by and installed_at

Useful for auditing and incident timelines. In automated environments, `installed_by` should be a clear service identity.

### 8.4. Execution time

Helps identify abnormally slow migrations and plan maintenance windows.

### 8.5. A success flag is not enough for a production runner

A real-world runner also needs lock/concurrency control, execution state, error handling, transaction boundaries, tool version, and repair semantics. Prefer a proven migration framework rather than implementing a half-baked custom system.

## 9. Flyway Schema History and Liquibase Changelog

Two popular tools manage history differently.

### 9.1. Flyway

Flyway typically uses a schema history table to record version, description, type, script, checksum, installed_by, installed_on, execution_time, and success. The table name is configurable.

Core concepts:
- Versioned migrations.
- Repeatable migrations.
- Validate.
- Migrate.
- Info.
- Repair.
- Baseline.

### 9.2. Liquibase

Liquibase stores changeset history in `DATABASECHANGELOG` and uses `DATABASECHANGELOGLOCK` to coordinate changelog execution.

A changeset is typically identified by `id`, `author`, and `file path`; checksums detect content changes according to Liquibase semantics.

### 9.3. Do not mix history tables

Do not let Flyway and Liquibase manage the same schema with two history systems without a clear migration architecture. The two runners may not understand each other's state.

### 9.4. Choose a tool based on team workflow

Consider SQL-first vs. declarative changelogs, rollback support, multi-database support, CI integration, license/edition, observability, and operational expertise.

## 10. Versioned SQL Migrations

An example of three migrations:

`V001__create_customers.sql`

```sql
CREATE TABLE public.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

`V002__add_customer_status.sql`

```sql
ALTER TABLE public.customers
ADD COLUMN status text;
```

`V003__create_customer_status_index.sql`

```sql
CREATE INDEX idx_customers_status
ON public.customers (status);
```

### 10.1. Each migration has a clear, reviewable purpose

A migration does not have to contain only a single SQL statement, but its scope should be small enough to understand, test, and recover.

### 10.2. Ordered dependencies

V003 depends on the `customers` table and `status` column created by V001/V002. Version order reflects dependency order.

### 10.3. Do not reuse existing versions

Once V003 has been deployed, the next change must be V004 or later according to the repository convention.

### 10.4. Schema qualification

Use explicit schema qualification or a controlled `search_path` configuration so migrations do not create objects in the wrong schema.

## 11. Transactional Migrations in PostgreSQL

PostgreSQL supports transactional DDL for many schema operations. If the migration tool runs a migration inside a transaction, the DDL and the history record can commit together.

Example:

```sql
BEGIN;

CREATE TABLE public.audit_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.audit_events
ADD COLUMN source text;

COMMIT;
```

If a statement fails before `COMMIT`, the transaction can roll back all DDL changes within that transaction.

### 11.1. Atomicity

When the migration and history update share a transaction, the database avoids ending up in a state where the script committed but history was not recorded (or vice versa), provided the tool actually uses the same transaction and the operations support transactional execution.

### 11.2. DDL is not always transactional

Certain commands cannot run inside a transaction block, such as `CREATE INDEX CONCURRENTLY`, `VACUUM`, `CREATE DATABASE`, and some other administrative operations. Verify each command and version.

### 11.3. Tools have their own transaction policies

Some tools allow disabling transactions for a migration or marking a changeset as non-transactional. Do not assume every script is automatically wrapped in a single transaction.

### 11.4. Large transactions have trade-offs

A long-running migration transaction can hold locks, snapshots, and WAL for a long time, causing replication lag or vacuum pressure. Split migrations into phases when appropriate.

## 12. Non-Transactional Migrations

Some PostgreSQL commands must run outside a transaction block. A common example is:

```sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
```

Do not run this statement inside a regular `BEGIN`/`COMMIT` block.

### 12.1. Isolate into a separate migration

Place non-transactional operations in their own migration file and configure the tool appropriately. Do not place additional transactional DDL in the same file if the runner cannot establish safe boundaries.

### 12.2. Failure can leave an intermediate state

A failed `CREATE INDEX CONCURRENTLY` can leave an invalid index behind. Migration history may record a failure; check the catalog and clean up or retry according to the runbook.

### 12.3. History updates are no longer atomic with DDL

When an operation is non-transactional, the runner must handle the case where DDL succeeds but the process crashes before history is recorded. This is one reason to rely on a proven framework and repair procedure.

### 12.4. Do not re-run blindly

Before retrying, verify whether the object exists, its valid/ready status, and how far the script progressed.

## 13. Migration Locks and Multiple Deploy Runners

Two CI jobs or two application instances might detect pending migrations at the same time. If they run concurrently, they can conflict or execute DDL twice.

A migration runner needs serialization:
- Only one runner executes migrations at a time.
- A second runner must wait or abort with a clear message.
- The lock must be held for the appropriate execution scope.
- The lock must be released when the runner finishes or crashes, according to the database/tool mechanism.

### 13.1. Liquibase lock table

Liquibase uses `DATABASECHANGELOGLOCK` to mark that a changelog is currently executing and prevent other runners from running in parallel.

### 13.2. Advisory locks

A custom runner can use PostgreSQL advisory locks. If a migration runs across multiple transactions, you must understand session-level locks and connection identity.

```sql
SELECT pg_advisory_lock(8421, 1);

-- Execute the serialized migration sequence
-- using the same database session.

SELECT pg_advisory_unlock(8421, 1);
```

This example only illustrates the mechanism. In production, use a dedicated key namespace, keep the same connection, and ensure proper unlock and connection cleanup.

### 13.3. Transaction-scoped advisory locks

If the entire migration and history update run inside a single transaction, `pg_advisory_xact_lock` can hold the lock until the transaction ends. It is not suitable if operations need to commit midway while keeping serialization.

### 13.4. Connection poolers

Session-level advisory locks require the same PostgreSQL session. Transaction pooling can switch backend connections between transactions; do not use session locks through a pooler in an unsupported manner.

## 14. Migration Idempotency

An idempotent operation can be executed multiple times while still leaving the system in the same final state, or without causing harm when re-run.

However, not every migration should be written to re-run repeatedly on its own.

### 14.1. Versioned migrations run once

Versioned migrations are governed by history; the runner does not re-run them once they succeed. Immutability and history are the primary safeguards.

### 14.2. IF NOT EXISTS does not solve schema drift

`CREATE TABLE IF NOT EXISTS` can skip an existing object whose structure differs from what is expected. Command success does not prove the schema is correct.

### 14.3. Data backfills should be resumable

A large backfill can use batches and a predicate identifying unprocessed records, allowing resumption after an interruption.

### 14.4. Repeatable scripts need clear semantics

View/function replacements can be re-run, but dependencies, grants, ownership, and side effects must be clearly defined.

## 15. Expand-Contract Migrations

Expand-contract enables changing schemas while multiple versions of an application are running simultaneously.

For example, suppose you want to rename the column `full_name` to `display_name`.

```text
Phase 1: EXPAND
  Add display_name
  Keep full_name
  Deploy app compatible with both

Phase 2: MIGRATE
  Backfill display_name in batches
  Dual-write or synchronize during transition
  Validate values

Phase 3: SWITCH
  Read from display_name
  Stop writing full_name
  Wait until old app versions are gone

Phase 4: CONTRACT
  Drop full_name in a later release
```

### 15.1. Expand

Add the new structure in a way that remains compatible with the old code. For example, adding a nullable column or a new table.

### 15.2. Migrate data

Backfill existing data in batches. If the application is still writing during the backfill, use dual-write, a temporary trigger, or a change-capture strategy so updates are not missed.

### 15.3. Switch

Deploy the application reading/writing the new structure. Monitor correctness and retain the ability to revert for a period of time.

### 15.4. Contract

Drop the old column/table only after no application version, job, or consumer still uses it.

### 15.5. Do not combine all four phases into one deployment

If you add, backfill, switch, and drop in a single large migration, rolling deployments can cause older application versions to fail mid-rollout.

## 16. Safely Adding Columns and NOT NULL Constraints

A seemingly simple change may require heavy locks or table rewrites depending on version, default value, and table size.

### 16.1. Expand first with a nullable column

```sql
ALTER TABLE public.customers
ADD COLUMN status text;
```

Older application versions can still operate if they do not depend on the new column.

### 16.2. Backfill in batches

Update rows where `status` is `NULL` in batches and commit frequently. Avoid a single transaction updating hundreds of millions of rows if unnecessary.

### 16.3. Add a NOT VALID constraint

```sql
ALTER TABLE public.customers
ADD CONSTRAINT customers_status_not_null_check
CHECK (status IS NOT NULL) NOT VALID;
```

`NOT VALID` allows the constraint to be enforced for new changes without scanning all existing rows immediately; verify semantics by constraint type and version.

### 16.4. Validate the constraint

```sql
ALTER TABLE public.customers
VALIDATE CONSTRAINT customers_status_not_null_check;
```

Once existing data is valid, you can perform the `SET NOT NULL` step according to your plan and version-specific locking behavior, then drop the redundant check constraint if appropriate.

### 16.5. Defaults and table rewrites

The behavior of `ADD COLUMN DEFAULT` varies by PostgreSQL version and default expression type. Read the documentation for your target version and measure lock/rewrite risk on a comparable table.

## 17. Safely Creating Indexes on Large Tables

A standard `CREATE INDEX` can block writes during the build depending on the command's lock mode. For tables serving live traffic, consider `CREATE INDEX CONCURRENTLY`.

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON public.orders (customer_id, created_at DESC);
```

### 17.1. Do not run inside a transaction block

`CREATE INDEX CONCURRENTLY` cannot run inside a regular transaction block. The migration runner must support non-transactional migrations.

### 17.2. Concurrent does not mean resource-free

The build still consumes CPU, I/O, and WAL, and can be prolonged by active transactions or old snapshots. Monitor the progress view and production load.

### 17.3. Check index validity

```sql
SELECT
    c.relname AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_index AS i
JOIN pg_class AS c
  ON c.oid = i.indexrelid
WHERE c.relname = 'idx_orders_customer_created';
```

### 17.4. Failed builds

If an invalid index remains, investigate and drop/rebuild it according to the runbook. Never just change the history status to pretend the migration succeeded.

## 18. Foreign Keys and Constraints on Large Tables

You can add certain constraints in a `NOT VALID` state and validate them separately to reduce the duration of strong locks.

Example:

```sql
ALTER TABLE public.orders
ADD CONSTRAINT orders_customer_fk
FOREIGN KEY (customer_id)
REFERENCES public.customers(customer_id)
NOT VALID;

ALTER TABLE public.orders
VALIDATE CONSTRAINT orders_customer_fk;
```

### 18.1. NOT VALID does not skip checking new data

The constraint is still enforced for new and updated rows according to PostgreSQL semantics; the `VALIDATE` step checks existing data.

### 18.2. Check for orphan rows first

You can query for foreign keys without a matching parent to anticipate validation failures.

### 18.3. Lock behavior

`ADD CONSTRAINT` and `VALIDATE` take different lock modes. Read the command documentation and test on the corresponding version and table size.

### 18.4. Constraint naming

Use stable names that are easy to search in logs, catalogs, and migration history.

## 19. Backfilling Data in Batches

A large data migration should be chunked to limit lock duration, WAL bursts, replication lag, and rollback cost.

Example using an ascending key to update in batches:

```sql
UPDATE public.customers
SET status = 'ACTIVE'
WHERE customer_id > 0
  AND customer_id <= 10000
  AND status IS NULL;
```

Then loop through subsequent key ranges, committing each batch.

### 19.1. Idempotent predicates

The `status IS NULL` condition allows re-running a batch without overwriting already-processed rows.

### 19.2. Keyset over OFFSET

For large tables, key ranges/keyset pagination are much more stable than large `OFFSET` values. Choose an indexed key with deterministic ordering.

### 19.3. Checkpoints

Record batch progress or derive it from remaining data. If a job crashes, it can resume without starting over from the beginning.

### 19.4. Concurrency with application writes

If the application still updates rows during a backfill, design precedence and conflict policies. Do not let the backfill overwrite newer values.

### 19.5. WAL and replication

Oversized batches can cause WAL bursts, replica lag, and archive growth. Tune batch size and concurrency based on metrics.

## 20. Migrations and Lock Behavior

DDL may require `AccessExclusiveLock` or other lock modes. A migration waiting for a lock can create a lock queue: incoming queries queued behind it may also be blocked depending on the situation.

### 20.1. Lock acquisition is part of downtime

Even a very fast `ALTER TABLE` can wait a long time if another transaction holds a lock. The wait time can far exceed the DDL execution time itself.

### 20.2. lock_timeout

You can set a short `lock_timeout` for migrations to fail fast if the lock cannot be acquired within the maintenance budget.

```sql
SET lock_timeout = '2s';
SET statement_timeout = '15min';
```

These are examples; choose values based on the operation and the tool's transaction model.

### 20.3. Long-running transactions

Look for sessions with an old `xact_start` before migrating. An `idle in transaction` session can hold locks/snapshots and block DDL.

### 20.4. NOWAIT

Some DDL or lock operations support `NOWAIT` or provide ways to inspect locks beforehand. Use this when you want a migration to fail immediately instead of forming a lock queue.

### 20.5. Do not terminate blockers reflexively

Identify the owner, transaction, and business impact before canceling or terminating a session. A fast-failing migration is usually safer than killing an unknown transaction.

## 21. Search Path, Schemas, and Object Ownership

Migrations must create objects in the right schema and with the right owner.

### 21.1. Schema qualification

Use `public.table` or the target schema explicitly when scripts may run in environments with varying `search_path` settings.

### 21.2. search_path

If the tool uses a dedicated migration role, check the role/session `search_path` and avoid schema shadowing.

### 21.3. Object owner

Objects created by the migration role belong to that role unless ownership is transferred. Choose an appropriate owner role so the application does not need superuser privileges.

### 21.4. Grants

Create grants/default privileges intentionally. Migrations adding new tables, sequences, or functions may require grants for the application to function.

### 21.5. SECURITY DEFINER functions

If a migration creates `SECURITY DEFINER` functions, set a safe `search_path`, use a trusted owner, and revoke `EXECUTE`/public grants when necessary.

## 22. Roles and Migration Execution Privileges

Separate these roles:
- Application runtime role: least privilege needed for business operations.
- Migration role: required DDL privileges within managed schemas.
- DBA/owner role: cluster administration and special operations.
- Read-only/reporting roles: read access per policy.

### 22.1. Do not run the application as superuser

The runtime application does not need privileges to alter schemas. Separating credentials reduces blast radius.

### 22.2. Grant the migration role appropriate privileges

The migration role needs to create/alter objects in target schemas and may need ownership. Grant privileges by scope, not superuser by default.

### 22.3. Credential management

Fetch secrets from a secret manager or CI secret store. Do not commit passwords into migration config or the repository.

### 22.4. Audit identity

History records and deployment logs should indicate which service identity or operator ran the migration.

## 23. Baseline for Existing Databases

When introducing a migration tool to a database that was created manually or has been running for a long time, you cannot run all historical migrations from scratch by default.

A baseline records that the current database is already at a specific version/schema state, so the tool starts managing from that milestone onward.

### 23.1. Inspect the schema before baselining

Compare objects, constraints, indexes, extensions, owners, and data assumptions against the schema corresponding to the chosen version.

### 23.2. Baseline does not create the schema

Baseline usually only records a history milestone. It does not execute all prior migrations to construct objects.

### 23.3. Choose the exact baseline version

If you pick the wrong version, the runner might skip necessary migrations or attempt to run old migrations on an existing schema.

### 23.4. Keep evidence

Store the schema snapshot/diff, object counts, database identity, baseline version, and approval. Baselining is a decision with long-term impact.

## 24. Fresh Migrations for Empty Environments

A good migration repository must be able to build a new database from scratch in sequence.

### 24.1. Empty database test

Create a clean database, run all migrations, and verify the application schema.

### 24.2. Seed/reference data

Distinguish required reference data (lookup/status codes) from production data. Seed scripts should be idempotent and have an owner.

### 24.3. Bootstrap roles/schemas

Create roles, schemas, extensions, and grants using an appropriate bootstrap process. Some cluster-level objects do not belong in regular database migrations.

### 24.4. Reproducibility

The same migration artifact and tool version must produce an equivalent schema across all supported environments.

## 25. CI/CD for Database Migrations

A typical pipeline:

```text
Pull request
    |
    v
Static review / lint
    |
    v
Create ephemeral PostgreSQL database
    |
    v
Run all migrations from empty state
    |
    v
Run application tests
    |
    v
Validate migration history/checksums
    |
    v
Build immutable release artifact
    |
    v
Deploy to staging
    |
    v
Backup + approval/change window
    |
    v
Run production migration once
    |
    v
Deploy compatible application
    |
    v
Monitor and verify
```

### 25.1. Test the full migration chain

Do not only test the latest migration on a database with a roughly similar schema. Test from an empty database to catch missing dependencies.

### 25.2. Test the upgrade path from a production-like state

Restore a representative snapshot/schema/data and run pending migrations. A script might succeed on an empty database yet time out on a large production table.

### 25.3. Test application compatibility

For rolling deployments, test both the old application version and the new application version during expand-contract phases.

### 25.4. Immutable release artifacts

Deploy the exact same tested migration artifact. Do not rebuild different scripts between staging and production.

### 25.5. Separate the migration runner from every application replica

Avoid having each web instance run migrations on startup. Use a serialized, audited deployment job or runner.

## 26. Promotion Across Development, Test, Staging, and Production

The exact same migration file should be promoted across environments in the same order.

### 26.1. Development

Allow rapid experimentation, but once a migration has been shared with others, keep the file stable and create a new version for modifications.

### 26.2. Test/CI

Run the full chain, schema validation, integration tests, and appropriate performance tests.

### 26.3. Staging

Use configuration and data volumes close to production. Measure locks, duration, WAL, replication lag, and downtime.

### 26.4. Production

Use the tested artifact, backup/restore evidence, change window, migration lock, and rollback/forward plan.

### 26.5. Do not customize scripts per environment

Use controlled configuration/variables for environment-specific values. Schema migrations should have consistent behavior; avoid files with the same version but different contents.

## 27. Migration History Across Multiple Environments

Each database has its own history table. A migration might be:
- Already executed in development.
- Already executed in the CI database.
- Already executed in staging.
- Not yet executed in production.

### 27.1. Do not copy history tables to synchronize

History must reflect the migrations that actually ran on that specific database. Copying rows between environments can mask schema mismatches.

### 27.2. Compare pending migrations

Before deploying, review the list of pending migrations and the current version. Verify the exact list about to execute.

### 27.3. Same artifact

Ensure migration checksums and file contents are identical across environments. Avoid branch-specific script drift.

### 27.4. Environment-specific data

Schema migrations should remain consistent; data seeds or tenant-specific setups should be managed separately under proper controls.

## 28. What is Schema Drift?

Schema drift occurs when the actual database schema differs from the state described by migration history and source code.

Causes:
- A DBA modifies production directly.
- A migration is run manually outside the tool.
- Tool history is altered or deleted.
- An already-applied script is modified.
- An environment misses a migration.
- An extension or provider automatically creates objects.
- Restoring from an old backup leaves history and artifacts out of sync.

### 28.1. History does not detect all drift

Checksums can detect modified migration files. They do not automatically detect every manual change made directly to catalogs.

### 28.2. Schema diff

Use schema comparison/introspection to compare actual objects against the expected schema. Review the diff before making fixes.

### 28.3. Do not automatically drop unknown objects

A drift tool might suggest `DROP` or `ALTER`. Verify dependencies, data, and ownership before applying.

### 28.4. Capture drift as a new migration

After verifying that a manual change is valid, bring it under source control with an appropriate migration or reconcile the schema following your process.

## 29. Failed Migrations and Recovery

When a migration fails, first determine:
- Was it transactional or non-transactional?
- How much of the script executed?
- Was the history record written?
- Which objects were created or altered?
- Are there open locks or transactions?
- Which version/schema state is the application currently expecting?

### 29.1. Transactional failure

If the tool ran the entire script in a single transaction and rolled back cleanly, DDL changes inside the transaction were rolled back. Inspect history and catalogs before retrying.

### 29.2. Non-transactional failure

Part of the operation may have completed. For example, an invalid index may remain. Inspect the catalog and clean up intermediate states.

### 29.3. Do not edit history with ad-hoc SQL

Use the tool's validate/repair or recovery procedure after understanding the actual state. Manual history edits can cause the runner to skip incomplete migrations.

### 29.4. Roll-forward is often safer

With production data, creating a subsequent corrective migration is usually safer than attempting to roll back a migration that already caused side effects or data transformations.

## 30. Rollback and Roll-Forward

Database rollback is rarely as simple as reverting a Git commit.

### 30.1. DDL rollback

Some DDL can be rolled back within a transaction. However, once committed and the application has written data under the new schema, reversing it can lose data or no longer be feasible.

### 30.2. Data migration rollback

If a transformation is lossy—such as merging two columns into one—you cannot always reconstruct the original data. Back up data or keep source columns during the transition.

### 30.3. Compensating migration

Create a new migration to return the schema to a compatible state, rather than altering or deleting applied history.

### 30.4. Roll-forward

Fixing issues with a new migration and deploying forward keeps history linear. Evaluate business impact and recovery points first.

### 30.5. Migration down scripts

Some tools support rollback/undo scripts, but they must be tested and checked for data loss. Never assume a down migration is always safe or reversible.

## 31. Migrations and Backup/PITR

Before high-risk migrations:
- Verify the most recent base backup.
- Verify continuous WAL archiving.
- Verify the restore procedure.
- Take a snapshot/backup per policy.
- Record the recovery point and owner.
- Rehearse restores for changes with a large blast radius.

### 31.1. Backups do not replace migration history

A backup restores the database state at a point in time. Migration history shows which changes were applied. Keep both artifacts and backup metadata.

### 31.2. Restoring pulls history backward

If you restore an older backup, the history table also reverts to its state at the time of the backup. Ensure the application version and migration artifacts are compatible with the restored schema.

### 31.3. PITR after a migration

If you need to revert to before a migration, restore the cluster to a point prior to the change using your PITR procedure. You cannot simply delete a history row.

### 31.4. Test recovery

An untested backup does not prove that a migration has a viable recovery path.

## 32. Migrations and Zero-Downtime Deployment

Databases and applications are often deployed separately. Rolling deployments can run old and new application versions simultaneously.

Expand-contract helps maintain compatibility:
1. Expand the schema.
2. Deploy code capable of reading/writing both old and new schemas.
3. Backfill data.
4. Switch traffic/code to the new structure.
5. Verify no old consumers remain.
6. Contract the schema in a later release.

### 32.1. Backward compatibility

The first migration must not drop or rename columns that the old application still uses.

### 32.2. Forward compatibility

The new application must not require the new schema before the expand migration has completed.

### 32.3. Deploy ordering

A common sequence: expand migration → deploy compatible application → backfill → switch application → contract migration after old versions are gone.

### 32.4. Workers and background jobs

Do not forget scheduled jobs, consumers, and long-lived workers. An old worker may still read a column slated for removal.

## 33. Migrations for Functions, Views, and Triggers

Database code also needs versioning:
- Functions/procedures.
- Views/materialized views.
- Triggers.
- Types/domains.
- Operators.
- Policies.
- Grants/default privileges.

### 33.1. CREATE OR REPLACE

May suit functions/views when signatures and semantics allow. Some changes to return types, dependencies, or object kinds require `DROP`/`CREATE` or separate migrations.

### 33.2. Dependencies

Changing a function signature can affect views, triggers, generated columns, or application calls. Inventory dependencies before modifying.

### 33.3. Grants and ownership

`CREATE OR REPLACE` may preserve certain ownership/privilege states, but you should not assume all permissions are preserved as intended. Verify grants after migrating.

### 33.4. Materialized views

Refreshing data can take time and acquire locks. `REFRESH MATERIALIZED VIEW CONCURRENTLY` has specific prerequisites and cannot run inside a regular transaction block.

## 34. Migrations for Enums and Data Types

PostgreSQL has type changes that require careful planning:
- `ALTER TYPE ADD VALUE`.
- Domain constraints.
- Composite types.
- Enum labels.
- Column type conversion.
- Collation changes.

### 34.1. Enum value addition

`ALTER TYPE ... ADD VALUE` has transactional behavior that depends on PostgreSQL version; in modern versions it can run inside a transaction, though the new value cannot be used before the transaction commits in some contexts. Check docs for your exact version.

### 34.2. Enum removal/rename

Removing an enum value has no simple equivalent to `ADD VALUE`. Typically you need to create a new type, migrate columns/data, update dependencies, and drop the old type.

### 34.3. Type conversion

`ALTER COLUMN TYPE` can rewrite the table and hold significant locks. Evaluate `USING` expressions, indexes, constraints, WAL, and disk space.

### 34.4. Large table strategy

For large tables, consider a new column + batch backfill + dual-write + switch + drop the old column.

## 35. Migrations for Partitioned Tables

Partitioned tables introduce additional dependencies:
- Parent partitioned table.
- Child partitions.
- Partition bounds.
- Indexes/constraints on parent and children.
- Default partition.
- Attach/detach workflows.

### 35.1. Create partitions before data arrives

If the application writes by time range, maintain a partition creation schedule and monitor the default partition.

### 35.2. Attach partition

May require validation/locks and matching constraint conditions. Pre-create matching check constraints to reduce scans in certain workflows.

### 35.3. Index consistency

Ensure partitioned indexes and child indexes correspond properly. Verify valid status after migration.

### 35.4. Detach/drop partition

This is a high-impact data change. Confirm retention policy, backups, and consumer dependencies beforehand.

## 36. Migrations with Logical Replication and CDC

DDL and migration history are not automatically replicated like row data.

### 36.1. Schemas must be deployed on subscribers

If the publisher adds a column before the subscriber schema is compatible, apply behavior depends on column mapping and publication settings. Plan DDL on both sides.

### 36.2. Can the migration history table be replicated?

It may be possible depending on publication/table selection, but replicating history should not be used to coordinate migration runners. Each database/cluster needs clear state and ownership.

### 36.3. CDC consumers

Schema changes can affect downstream schemas, event contracts, and deserialization. Coordinate database and event schema versioning.

### 36.4. Ordering

Ensure consumers know the new schema before events containing new fields arrive. Use compatibility rollouts and a schema registry/pipeline contract when available.

## 37. Migration Scripts and Data Safety

A migration can cause data loss if:
- `DROP COLUMN` runs before code stops reading it.
- `ALTER TYPE` truncates or casts data incorrectly.
- `UPDATE` lacks a `WHERE` clause.
- `DELETE` has an incorrect filter.
- Backfill overwrites concurrent updates.
- Rebuilding an object loses grants/ownership.
- Dropping/recreating a table loses dependent objects.

### 37.1. Review destructive statements

`DROP`, `TRUNCATE`, `DELETE`, type conversions, and table rewrites require thorough review, a backup/recovery plan, and explicit impact analysis.

### 37.2. Dry run/plan

Some changes allow estimating affected rows or locks beforehand. Use `SELECT` previews and test transactions on staging.

### 37.3. Row counts and invariants

Before and after migrating, check row counts, null counts, uniqueness, foreign-key coverage, and business aggregates.

### 37.4. Data retention

Do not delete old data before confirming retention, legal, and business requirements as well as downstream consumers.

## 38. Naming, Repository Structure, and Ownership

Repository example:

```text
db/
  migrations/
    V001__create_customers.sql
    V002__add_customer_status.sql
    V003__create_orders.sql
    V004__create_orders_customer_index.sql
    R__customer_reporting_views.sql
  callbacks/
  seed/
  tests/
  README.md
```

### 38.1. Ownership

Each migration should have an author/team or appropriate `CODEOWNERS`. The database platform team can review migrations that impact locks or availability.

### 38.2. Do not store migrations in temporary directories

Migrations must reside in versioned release artifacts/source control and be deployed consistently.

### 38.3. SQL review

Review the plan, locks, table size, index builds, data transformations, privileges, and rollback/forward paths.

### 38.4. Naming convention

Keep version, separator, description, and encoding rules consistent.

## 39. Observability for Migration Execution

Record:
- Migration version/script.
- Start/end timestamps.
- Duration.
- Runner identity.
- Database/cluster identity.
- Success/failure.
- Checksum.
- Lock wait.
- Rows affected or backfill progress.
- WAL/replication lag.
- Error message/SQLSTATE.
- Deployment/change ID.

### 39.1. Migration duration

Compare actual duration against rehearsal timings. Alert when exceeding the maintenance budget.

### 39.2. Lock wait

Measure lock wait time and the number of blocked sessions. A short DDL that waits long for a lock can still cause an incident.

### 39.3. Backfill progress

Log batches completed, rows remaining, throughput, and checkpoints. Do not just log a single "job running" line.

### 39.4. Replica lag and WAL

Monitor WAL generation, archive retention, and standby replay lag during large data migrations.

## 40. Monitoring and Alerting

Alerts can include:
- Migration runner failure.
- Checksum validation mismatch.
- Version collision or history inconsistency.
- Migration lock waiting too long.
- DDL blockers exceeding threshold.
- Migration duration exceeding budget.
- Sharp spike in replica lag during backfill.
- WAL filesystem nearing capacity.
- Invalid index after a failed concurrent build.
- Increased application errors/latency after a migration.

### 40.1. Alert by impact

A failed migration on a staging database differs from critical production. Base severity on environment and business impact.

### 40.2. Do not alert solely because a migration is running

Migrations can be long by design. Alert when exceeding expected duration, lock budget, or resource thresholds.

### 40.3. Link runbooks

Alerts should include the migration version, runner, database, logs, and next steps.

### 40.4. Stop conditions

Define thresholds to pause, roll back, or throttle traffic before running a large migration.

## 41. Repair and History Reconciliation

Migration tools provide a repair command to handle metadata after exceptional situations. Repair is not a "fix database schema" command.

### 41.1. Validate before repairing

Inspect history, checksums, scripts, and the actual schema. Determine which migrations ran completely, partially, or not at all.

### 41.2. Repair only fixes metadata per tool semantics

For example, it may update checksums, remove failed records, or reconcile history. Exact behavior depends on the tool and version.

### 41.3. Do not use repair to hide drift

If the schema is missing a column, repairing history will not create that column. Create a corrective migration or restore according to plan.

### 41.4. Audit repairs

Record who ran it, why, before/after history, and schema evidence. Repairs in production require change control.

## 42. Migrations and Disaster Recovery

When restoring a backup, migration history reverts to the backup timestamp. The source repository may contain migrations newer than the restored state.

### 42.1. Reconcile before migrating forward

Identify the database version in history after restore, the target application version, and the pending migrations.

### 42.2. PITR target

If restoring to a point before a migration, history must also reflect that state. Do not manually delete history rows just to force the runner.

### 42.3. Recovery environment

Use the same tested migration artifacts and tool version. Avoid deploying a new branch onto a restored database without checking compatibility.

### 42.4. Disaster recovery exercise

Rehearse restore, migration catch-up, and application startup. Measure time to service recovery.

## 43. Security in the Migration Pipeline

Migration scripts hold DDL privileges and can read/write large amounts of data. Secure the pipeline:
- Secrets in a secret manager/CI variables.
- Never commit credentials.
- Dedicated runner identity.
- Restricted network access.
- Least privilege.
- Signed/immutable artifacts when needed.
- Branch protection and mandatory reviews.
- Audit deployment approvals.
- Redact sensitive data from logs.
- Review extension/function security.

### 43.1. SQL injection in migration tooling

Never concatenate untrusted input into dynamic SQL. Use proper parameterization and identifier quoting in procedural code.

### 43.2. Migration files are executable code

Review SQL like production code. A script can `DROP` data or grant overly broad privileges.

### 43.3. Production approvals

High-risk changes require an owner and approval per policy. Automation should not self-escalate privileges.

### 43.4. Secrets rotation

If a migration needs an external credential, use a secret reference and limit its lifetime.

## 44. Runbook: Deploying Migrations for a Release

1. Finalize migration files and version uniqueness.
2. Review SQL, dependencies, locks, and destructive operations.
3. Run lint/static checks.
4. Spin up a clean database and run the full chain.
5. Test upgrading from a production-like schema.
6. Run application integration tests.
7. Rehearse duration/locks/WAL with representative data volume.
8. Validate migration checksums/history.
9. Build an immutable artifact.
10. Deploy to staging and verify.
11. Verify backup/restore readiness.
12. Open the change window and confirm the owner.
13. Run a single serialized migration runner.
14. Monitor progress, logs, locks, replica lag, and application metrics.
15. Verify history, schema, and business invariants.
16. Deploy/enable compatible application behavior.
17. Record change evidence and close the release.

## 45. Runbook: Migration Failed Midway

1. Stop automatic runner retries until the state is understood.
2. Record the migration version, checksum, tool version, and error.
3. Determine whether it was transactional or non-transactional.
4. Check active backends/sessions and locks.
5. Inspect the history table and execution status.
6. Inspect the actual catalog/object state.
7. Check how far data rows were backfilled.
8. Determine if the application version depends on an intermediate schema.
9. Choose rollback, cleanup, or a corrective migration.
10. Use tool repair only after schema and history are reconciled.
11. Test recovery on a clone/copy.
12. Proceed per runbook and verify invariants.

### 45.1. Do not delete history records before knowing DDL state

If DDL succeeded while history is missing, the runner may re-run and fail or corrupt the schema.

### 45.2. Do not edit an already-run versioned file

Create a new corrective migration if changes are needed.

### 45.3. Preserve evidence

Save logs, `SQLSTATE`, backend PID, locks, object states, and history snapshots.

## 46. Runbook: Checking for Schema Drift

1. Retrieve the expected migration list from the release artifact.
2. Run validate/checksum checks.
3. Read migration history on each environment.
4. Compare object inventory/catalogs.
5. Identify missing, extra, or differently defined objects.
6. Identify manual changes, extension/provider changes, or missed migrations.
7. Assess data and dependency impact.
8. Write a corrective migration or reconcile via tool.
9. Test on staging/snapshot.
10. Deploy and re-verify history and schema.

### 46.1. Do not automatically drop unknown objects

A table might belong to an extension, provider, or another application. Identify the owner first.

### 46.2. Drift is not just columns

It includes indexes, constraints, triggers, functions, policies, owners, grants, extensions, and collations.

### 46.3. Compare across environments

Staging and production having the same history but different schemas can indicate drift. Compare both history and actual catalogs.

## 47. Common Mistakes

- Editing a versioned migration that has already run.
- Using duplicate versions across two branches.
- Comparing versions as text in the wrong order.
- Running migrations concurrently from multiple application replicas.
- Running non-transactional DDL inside a transaction block.
- Retrying a failed migration without checking object state.
- Using `IF NOT EXISTS` to mask schema mismatches.
- Recording history before DDL has actually completed.
- Modifying/deleting the history table with ad-hoc SQL.
- Treating checksums as proof against schema drift.
- Backfilling an entire table in one massive transaction.
- Adding `NOT NULL` or foreign keys on large tables without rehearsal.
- Creating standard indexes during peak hours without evaluating locks.
- Forgetting sequence, data, or CDC dependencies.
- Dropping a column before old apps/workers stop using it.
- Deploying a new app before the expand migration.
- Failing to check grants/ownership after creating objects.
- Failing to test the migration chain from an empty database.
- Copying history from staging to production.
- Lacking backup/restore tests or a forward recovery plan.

## 48. Practice Exercises with Answers

### Exercise 1. What is a versioned migration?

**Answer:** A script/change set with a unique version, executed in order and recorded in migration history.

### Exercise 2. What is migration history used for?

**Answer:** Recording applied migrations, versions, checksums, timestamps, executing user/tool, and execution outcomes.

### Exercise 3. Does the history table prove the actual schema has not drifted?

**Answer:** No. It records tool history; schema diffs/catalog inspection are needed to detect manual changes.

### Exercise 4. Why must migration versions be unique?

**Answer:** So the runner can determine order and avoid two scripts sharing the same identity.

### Exercise 5. Why shouldn't V001 be edited after production has run it?

**Answer:** Environments can record the same version while having executed different contents.

### Exercise 6. What is the purpose of a checksum?

**Answer:** Detecting whether a migration file has changed compared to the content recorded when it was applied.

### Exercise 7. Is a checksum a security signature?

**Answer:** No. It is a fingerprint/validation mechanism, not proof of author identity or safe content.

### Exercise 8. What are repeatable migrations suitable for?

**Answer:** Objects that can be recreated from a new definition, such as certain views/functions; not suitable for arbitrary data backfills.

### Exercise 9. Are Flyway versioned migrations and Liquibase changesets completely identical?

**Answer:** No. Both manage change history, but their identity, ordering, and execution semantics differ.

### Exercise 10. Which table does Liquibase use to lock the changelog?

**Answer:** `DATABASECHANGELOGLOCK`.

### Exercise 11. Why does a migration runner need a lock?

**Answer:** To prevent two deployment runners from applying migrations concurrently and creating race conditions.

### Exercise 12. Does PostgreSQL support transactional DDL?

**Answer:** Yes for many DDL commands, though not every command can run inside a transaction block.

### Exercise 13. Can CREATE INDEX CONCURRENTLY run inside a regular BEGIN/COMMIT block?

**Answer:** No. It must run outside a transaction block.

### Exercise 14. What might remain if CREATE INDEX CONCURRENTLY fails?

**Answer:** An invalid/not-ready index may remain; check the catalog before retrying.

### Exercise 15. How do transactional migrations help?

**Answer:** They can commit DDL and history updates atomically within the same transaction if all operations support transactions.

### Exercise 16. Why are non-transactional migrations harder to recover?

**Answer:** DDL may have partially completed before the runner records history or the process crashes.

### Exercise 17. What is pg_advisory_lock?

**Answer:** PostgreSQL's application-defined locking mechanism, which can serialize migration runners if used with the same session/key.

### Exercise 18. How long does pg_advisory_xact_lock hold a lock?

**Answer:** Until the transaction ends.

### Exercise 19. Why are session advisory locks problematic with transaction pooling?

**Answer:** The backend session can change between transactions; session locks are tied to a specific session.

### Exercise 20. Does IF NOT EXISTS guarantee an object has the right schema?

**Answer:** No. It only skips creation if an object with the same name exists; the definition can differ.

### Exercise 21. What phases make up expand-contract?

**Answer:** Expand schema, migrate/backfill, switch application, contract/drop old structure.

### Exercise 22. Why not drop an old column immediately when adding a new column?

**Answer:** Old application versions and workers may still use the old column during a rolling deployment.

### Exercise 23. What are the benefits of batched backfills?

**Answer:** Limits transaction duration, locks, and WAL bursts, and allows resuming after an interruption.

### Exercise 24. Why must backfills handle concurrent writes?

**Answer:** If the application updates the same rows, a backfill could overwrite newer data or miss changes.

### Exercise 25. What does a NOT VALID constraint do?

**Answer:** Allows adding a constraint without scanning all existing rows upfront; existing data is validated in a separate step.

### Exercise 26. What is VALIDATE CONSTRAINT used for?

**Answer:** Checking that existing data satisfies the constraint.

### Exercise 27. Does CREATE INDEX CONCURRENTLY have zero impact on workload?

**Answer:** No. It still consumes CPU, I/O, and WAL and can wait on transactions/snapshots.

### Exercise 28. What does lock_timeout limit?

**Answer:** How long a statement waits to acquire a lock before failing with an error.

### Exercise 29. Why can a short DDL migration still block traffic for a long time?

**Answer:** It may wait for a lock held by another transaction; the wait time can exceed the DDL execution time.

### Exercise 30. Should the migration role be a superuser?

**Answer:** Not by default. Grant only the necessary DDL privileges within the schema scope following least privilege.

### Exercise 31. Does baselining automatically create the schema for an old database?

**Answer:** No. It records a history milestone; you must verify the current schema matches that milestone.

### Exercise 32. Why test migrations from an empty database?

**Answer:** To detect missing dependencies or migration chains unable to recreate a fresh schema.

### Exercise 33. Why test on production-like data?

**Answer:** To measure locks, duration, rewrites, WAL, and data validation under realistic volume and skew.

### Exercise 34. Should you copy the history table from staging to production?

**Answer:** No. History must reflect the migrations that actually ran on that specific database.

### Exercise 35. What is schema drift?

**Answer:** When the actual schema differs from the state described by migration source and history.

### Exercise 36. Does checksum validation detect all schema drift?

**Answer:** No. It primarily detects modified migration files; catalog/schema diffs are needed for actual schema drift.

### Exercise 37. When a migration fails, what is the first step?

**Answer:** Determine transactional state, object/data changes, history state, and locks before retrying.

### Exercise 38. Does the repair command fix the schema automatically?

**Answer:** No. It adjusts migration metadata according to tool semantics; the schema requires a separate corrective migration or recovery.

### Exercise 39. Is rolling back a migration always safe?

**Answer:** No. Data transformations may be lossy and the application may already have written data under the new schema.

### Exercise 40. What is roll-forward?

**Answer:** Creating a new migration to fix the current state while keeping applied history intact.

### Exercise 41. Do backups/PITR replace migration history?

**Answer:** No. Backups store database state; history describes which changes were executed.

### Exercise 42. After PITR, what state can the history table be in?

**Answer:** It reverts to its state at the recovery target, which may be older than the current source migration repository.

### Exercise 43. How should migrations and rolling application deployments be coordinated?

**Answer:** Expand the schema first, deploy compatible code, backfill/switch, then contract after old consumers are gone.

### Exercise 44. Why check grants after CREATE TABLE?

**Answer:** The new object may belong to the migration role, and the application runtime role will not automatically have access.

### Exercise 45. Are sequences automatically synchronized like rows by logical replication?

**Answer:** No. A separate procedure is needed to synchronize sequence state during migration/cutover.

### Exercise 46. Why should migrations have an owner and audit trail?

**Answer:** To know who is accountable, when it ran, what changes were applied, and to support incident investigations.

### Exercise 47. Does a migration lock replace source control review?

**Answer:** No. Locking only serializes execution; review is still needed to verify correctness and risk.

### Exercise 48. When is a dedicated migration runner needed instead of each app replica running migrations?

**Answer:** In most production deployments, a dedicated runner controls order, privileges, locking, auditing, and rollout.

### Exercise 49. When can a migration history record be deleted?

**Answer:** Never arbitrarily. Only under a verified repair/recovery procedure of the tool and owner.

### Exercise 50. What does a reliable migration process require?

**Answer:** Immutable versioning, checksum validation, serialized runner, transaction policy, backup/recovery, CI tests, schema drift detection, auditing, and post-deploy verification.

## 49. Versioned Migration Management Checklist

| Phase | Question |
|---|---|
| Design | Does the migration have a clear purpose and unique version? |
| Source | Is the file in source control and immutable after deployment? |
| Naming | Are version ordering and file naming stable? |
| History | Is the history table/tool managed properly? |
| Checksum | Does validation detect unintended modifications? |
| Locking | Does only one runner execute at a time? |
| Transaction | Is the script transactional or non-transactional? |
| DDL | Have locks, rewrites, and index builds been evaluated? |
| Data | Does the backfill have batching, checkpoints, and a concurrency policy? |
| Compatibility | Can old and new application versions operate together? |
| Permissions | Does the migration role follow least privilege? |
| CI | Does the full chain run from a clean database? |
| Staging | Was it tested on production-like data volume and schema? |
| Backup | Are backup/PITR and restore tests ready? |
| Deploy | Is the exact same artifact used across environments? |
| Failure | Is there a runbook to inspect partial state and repair? |
| Drift | Is there schema diff/catalog reconciliation? |
| Audit | Are runner, version, checksum, time, and outcome recorded? |
| Recovery | Are rollback/roll-forward and data-loss risks clear? |
| Verify | Have history, schema, and business invariants been confirmed? |

## 50. Official References

- [PostgreSQL: ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — locks, constraints, column changes, and validation.
- [PostgreSQL: CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — regular and concurrent index builds.
- [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes and behavior.
- [PostgreSQL: Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) — session/transaction advisory locks.
- [PostgreSQL: SET](https://www.postgresql.org/docs/current/sql-set.html) — session and transaction-local settings.
- [PostgreSQL: NOT VALID Constraints](https://www.postgresql.org/docs/current/sql-altertable.html) — adding and validating constraints.
- [PostgreSQL: System Catalogs](https://www.postgresql.org/docs/current/catalogs.html) — inspecting schema objects and metadata.
- [PostgreSQL: Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — sessions, locks, replication, and database activity.
- [Flyway Documentation](https://documentation.red-gate.com/flyway) — versioned/repeatable migrations, schema history, validate, and repair.
- [Liquibase Documentation](https://docs.liquibase.com/) — changelogs, changesets, `DATABASECHANGELOG`, and `DATABASECHANGELOGLOCK`.

Commands, locking behavior, and tool features may vary across PostgreSQL major versions and migration-tool versions. Check the documentation for your exact version, test on staging, and confirm transaction support for every DDL statement before production deployment.

## 51. Summary: Migrations as Reproducible History

```text
Migration files in source control
             |
             v
Unique versions + immutable content
             |
             v
Validate checksum and history
             |
             v
Acquire migration lock
             |
             v
Run transactional / non-transactional steps
             |
             v
Record execution outcome
             |
             v
Verify schema + data + application
             |
             v
Audit, monitor and recover if needed
```

Key principles to remember:

1. **Every change has a clear version and purpose.** Versions determine order and prevent duplicate execution.
2. **Applied migrations must be immutable.** Subsequent modifications are recorded under a new version.
3. **The history table is a ledger, not proof against schema drift.** Combine checksum validation with schema diffs.
4. **Only one runner executes at a time.** Use migration tool locks or an explicitly designed serialization mechanism.
5. **Distinguish transactional and non-transactional DDL.** `CREATE INDEX CONCURRENTLY` needs separate boundaries and a recovery plan.
6. **Account for locks and table size.** Fast DDL can still wait a long time for locks.
7. **Use expand-contract for rolling deployments.** Keep old and new application versions compatible during the transition.
8. **Backfill in batches with checkpoints.** Control WAL, replication lag, and concurrent writes.
9. **Baselining must be based on a verified schema.** It marks a milestone; it does not reconstruct an old database.
10. **Do not edit or delete history to hide errors.** Investigate the actual state, then use tool repair or a corrective migration.
11. **Backups, PITR, and restore tests are part of the migration plan.** Schema rollback cannot always reverse data changes.
12. **CI must test both clean databases and upgrade paths.** Staging rehearsals help predict locks, duration, and performance.
13. **Migration roles follow least privilege.** The runtime application does not need DDL or superuser privileges.
14. **Verify after deployment.** Check history, catalogs, constraints, indexes, data invariants, and business flows.

**One sentence to remember:** *Version every change, keep executed migrations immutable, record reliable history, and verify the actual schema; that is the foundation for consistently upgrading a database across all environments.*
