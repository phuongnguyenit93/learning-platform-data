# Testing Migrations Against Prior-Version Schemas and Data

A database migration changes structure or data to transition a database from its current application/schema version to a new version. A migration may add or alter columns, create indexes, modify constraints, transform data, update extensions, or drop legacy structures. These changes are often straightforward on an empty database, yet can fail or cause outages when executed on production data accumulated over years—containing NULLs, duplicates, unexpected values, complex relationships, open transactions, and concurrent workloads.

Migration testing must start from a **realistic prior-version schema and dataset**, then execute the exact migration chain that production will run. The goal is to prove the database can transition from the old state to the new state, data is preserved or transformed accurately, the application remains compatible throughout the transition, and performance/availability stay within acceptable bounds. Testing migrations only on a freshly created database cannot uncover bugs dependent on data shape, historical values, table sizes, indexes, constraints, or transaction history.

This lesson belongs to the **Testing** chapter of the **Database Engine Relational PostgreSQL** module. It presents how to build a test baseline from prior-version schemas/data, prepare representative datasets, run migration rehearsals, verify schema and data invariants, measure locks/performance, test rollback/recovery, and integrate migration tests into CI/CD.

## 1. Learning Objectives

After this lesson, you can:

- Explain why migrations must be tested against prior-version schemas and data.
- Distinguish schema baselines, data snapshots, and migration targets.
- Create test clones safely from backups or snapshots.
- Prepare representative datasets including NULLs, duplicates, skew, boundary values, and historical records.
- Detect schema drift across environments.
- Execute the entire migration chain in the exact production order.
- Test DDL, data backfills, constraints, indexes, and extension changes.
- Verify before/after data using counts, checksums, and business invariants.
- Measure lock duration, query impact, WAL, disk growth, and replication lag.
- Verify compatibility across application versions during expand-and-contract.
- Build rollback, restore, and forward-fix strategies.
- Automate migration rehearsals in CI/CD and archive evidence.

## 2. Why Must Migrations Run Against Prior-Version Data?

Migrations are designed to transform an existing state. Assumptions that hold on an empty database can break on an older database.

### 2.1. Historical data

Production data contains records created by multiple past application versions, business rules, and legacy formats. A column may hold values that current code no longer produces yet the migration must still handle.

### 2.2. NULLs and missing data

A migration adding `NOT NULL` or converting values can fail because older rows contain `NULL`. New test fixtures often contain only valid rows matching the current model.

### 2.3. Duplicates and uniqueness

Creating a unique index/constraint can fail if historical data contains duplicates. Such duplicates may stem from old bugs, imports, or concurrency races.

### 2.4. Scale and distribution

A migration that finishes quickly on a few hundred rows can lock tables or generate massive WAL on hundreds of millions of rows. Data skew also affects query plans and backfill duration.

### 2.5. Dependencies and live workloads

Foreign keys, views, triggers, functions, prepared statements, and open transactions can affect migrations. Testing against a prior-version database reproduces real dependencies far more faithfully.

## 3. States to Test

A migration test can model the database as a reproducible sequence of states.

~~~text
Prior application + schema + data (N)
                  |
                  v
          Pre-migration checks
                  |
                  v
          Migration sequence
                  |
                  v
       Target schema + transformed data (N+1)
                  |
                  v
      Validation + application smoke tests
                  |
                  v
       Performance / recovery acceptance
~~~

### 3.1. Source state

The source state is the prior-version schema/data matching production immediately before the migration. Record the PostgreSQL major/minor version, application release, and current migration version.

### 3.2. Intermediate states

If a migration involves multiple steps or deployment phases, capture state after each major step. This helps pinpoint the exact failing step.

### 3.3. Target state

The target state includes the new schema version, transformed data, valid indexes/constraints, privileges, and related objects.

### 3.4. Runtime state

A migration may complete its DDL while the application still fails due to query behavior, defaults, permissions, or background jobs. Test runtime behavior after the transition.

### 3.5. Recovery state

Define recoverable states when a migration fails: transaction rollback, migration-specific compensation, snapshot restore, or forward fix.

## 4. Prior-Version Schema Baseline

The baseline must describe the actual schema before running migrations.

### 4.1. DDL inventory

Capture `CREATE TABLE` definitions, indexes, constraints, sequences, views, materialized views, functions, triggers, types, schemas, and grants.

### 4.2. Migration version markers

If the application uses a migration history table, record the current version, applied timestamps, and checksums. Never manually edit the history table just to make a test pass.

### 4.3. Object ownership

Record owners, grants, default privileges, and required role memberships. A migration running under a different role can fail even when the schema looks identical.

### 4.4. Extension inventory

Record extension names/versions and dependencies. The target environment needs matching packages/shared libraries before running migrations that depend on them.

### 4.5. Schema diff baseline

Compare the test snapshot's DDL against the source-controlled schema in the repository. If drift exists, document it before running migrations so old bugs are not confused with new ones.

## 5. Prior-Version Data Baseline

The data baseline must be rich enough to reproduce the conditions migrations will encounter.

### 5.1. Table row counts

Record exact counts or estimates for key tables, broken down by schema/table and partition. Counts serve as a baseline for post-backfill reconciliation.

### 5.2. Distribution profiles

Record NULL fractions, distinct values, min/max, most common values, date ranges, and distributions across tenant/status/type.

### 5.3. Referential relationships

Record counts of rows with/without parents, orphan candidates, and many-to-many relationships. Foreign key migrations can fail if historical rows violate them.

### 5.4. Data quality anomalies

Capture duplicates, malformed strings, invalid enum values, out-of-range numbers, invalid timestamps, and legacy sentinel values.

### 5.5. Sensitive data handling

Production snapshots may contain personal/customer/financial data. Apply policy-compliant sanitization or synthetic replacement while preserving necessary distribution structure and controlling access.

## 6. Choosing a Source for the Test Database

There are several ways to construct a source database for migration rehearsals.

### 6.1. Logical backups

`pg_dump`/`pg_restore` creates a logical clone. This fits when portability and selective schemas/tables are needed, though dump/restore times can be long and physical layout differs from production.

### 6.2. Physical backups

Base backups or storage snapshots create a physical copy of the cluster following PostgreSQL-aware procedures. Ensure consistency, WAL requirements, and PostgreSQL major version compatibility.

### 6.3. Storage snapshots

Volume snapshots can be fast, provided the database is snapshotted in a consistent/crash-recovery-aware manner with sufficient WAL for recovery.

### 6.4. Sanitized clones

You can restore a production backup and mask/tokenize sensitive fields in an isolated environment. Verify that sanitization does not break uniqueness, relationships, or distributions needed for migration testing.

### 6.5. Synthetic data

Synthetic data is valuable when production snapshots cannot be used. It must generate equivalent volume, skew, historical edge cases, and referential patterns; a handful of sample rows does not represent a production migration.

## 7. Production-Like Test Environment

Migration behavior depends on PostgreSQL version, configuration, hardware, storage, and workload.

### 7.1. PostgreSQL version

Use the same major/minor release or explicitly document differences. DDL syntax, catalog behavior, locking, and extension compatibility can change across versions.

### 7.2. Configuration

Compare `max_connections`, `work_mem`, `maintenance_work_mem`, `shared_buffers`, autovacuum, WAL, checkpoint, and relevant timeout settings.

### 7.3. Hardware/storage

CPU, RAM, disk throughput/latency, and filesystem affect migration duration. A small VM can test correctness but should not be used to predict production duration.

### 7.4. Extensions and collations

Install the required extension versions, locales/collations, and OS libraries. Where differences exist, clearly note which tests are non-representative.

### 7.5. Networking and topology

If migrations involve replication, FDWs, logical subscribers, or remote services, build a matching topology and test network/authentication behavior.

## 8. Representative Datasets and Edge Cases

A useful dataset must include both normal data and rare cases capable of breaking migrations.

| Data category | Examples to include | Migration risk |
|---|---|---|
| NULL | Optional fields, missing dates | NOT NULL, casts |
| Duplicates | Same natural key | UNIQUE constraint/index |
| Boundary | Min/max, empty strings, zero | Type/range conversion |
| Historical | Old enum/status values | CASE mapping |
| Skew | One tenant dominates | Backfill performance |
| Large values | Long text, large JSON | Memory/WAL/TOAST |
| Orphans | Missing parent candidates | Foreign keys |
| Time data | DST/time zone boundaries | Timestamp conversion |
| Unicode | Accents, combining chars | Collation/encoding |
| Soft deleted | Archived/inactive rows | Filtered backfill |

### 8.1. NULL distributions

Include both `NULL` and non-`NULL` rows in columns whose nullability or default will change.

### 8.2. Duplicate keys

Intentionally include duplicate natural keys to test deduplication steps before adding unique constraints.

### 8.3. Legacy values

Keep old status/type codes that the new application no longer creates. Migrations must map, preserve, or reject them according to explicit business rules.

### 8.4. Large objects and TOAST

Include records with large text/JSON/binary values to test table rewrites, copying, and WAL volume.

### 8.5. Boundary dates and numbers

Test leap days, timezone offsets, negative/zero/maximum values, decimal precision, and out-of-domain values.

## 9. Snapshot Consistency and Repeatability

A test yields meaningful comparisons only when the source state is well-defined and recreatable.

### 9.1. Snapshot identifier

Record the backup ID, timestamp, database identifier, source release, and migration version. For physical backups, save appropriate timeline/LSN metadata.

### 9.2. Quiesce or consistent snapshots

Use a snapshot method that guarantees consistent data and schema. If the application continues writing, use a backup mechanism that guarantees snapshot consistency.

### 9.3. Immutable source artifacts

Keep the original backup/snapshot read-only or protected. Create a separate working clone for each rehearsal.

### 9.4. Repeat tests

Run migrations from the exact same source snapshot to compare duration, output, and transformed data. Whenever inputs differ between runs, explicitly note the differences.

### 9.5. No hidden manual edits

All seeds, sanitization, and setup changes must be scripted and version-controlled. Document any manual actions that cannot be automated.

## 10. Pre-Migration Schema Checks

Before running migrations, confirm the clone truly matches the source version the migration expects.

### 10.1. Migration history

Read the migration history table and verify the latest applied version. Check migration checksums if supported by the framework.

### 10.2. Required objects

Verify that tables, columns, indexes, constraints, functions, and extensions referenced by the migration exist.

### 10.3. Unexpected objects

Look for manual objects or drift outside source control. A pre-existing colliding index name or column can make a migration fail.

### 10.4. Ownership and privileges

Run preflight checks under the exact deployment role. Verify `CREATE`/`ALTER` privileges, schema ownership, and permissions on sequences/functions.

### 10.5. Baseline query behavior

Save `EXPLAIN` plans and runtimes of relevant queries before the migration. After migration, you may need to separate schema correctness from plan/performance changes.

## 11. Classifying Migrations

Each migration carries a different risk profile. Classification guides test case selection and recovery strategies.

### 11.1. Additive DDL

Adding tables, nullable columns, indexes, or functions is usually less destructive, yet can still lock catalogs/tables and impact writes.

### 11.2. Destructive DDL

Dropping/renaming columns, dropping tables, narrowing data types, and removing constraints can break application compatibility or lose data.

### 11.3. Data migrations

Backfills, normalization, record splitting/merging, unit conversions, and code remapping require business invariants alongside partial-progress handling strategies.

### 11.4. Constraint migrations

Adding `NOT NULL`, `CHECK`, `UNIQUE`, or foreign keys requires validating existing rows and understanding lock/validation behavior.

### 11.5. Operational migrations

Extension updates, collation rebuilds, partition reorganization, and role/privilege changes have environment-specific prerequisites.

## 12. Expand-and-Contract Migrations

Expand-and-contract allows old and new schemas to coexist during deployment.

~~~text
Old schema + old app
        |
        v
Expand: add compatible new objects
        |
        v
App supports old + new schema
        |
        v
Backfill and validate
        |
        v
Switch reads/writes to new shape
        |
        v
Contract: remove old objects later
~~~

### 12.1. Expand

Add new columns/tables/indexes in a way that does not break old application code. Avoid dropping or renaming immediately in the first step.

### 12.2. Compatibility release

Deploy application code capable of reading/writing both schema shapes or performing controlled dual-writes.

### 12.3. Backfill

Convert historical rows in batches, checkpoint progress, and monitor locks/WAL/replication.

### 12.4. Cutover

Once new data is validated, switch read/write paths to the new structure. Monitor mismatches during an observation window.

### 12.5. Contract

Drop legacy columns/tables only after no application instances/jobs use them and the rollback window has closed.

## 13. Migration Frameworks and Version Ordering

Use a migration framework with explicit history/versioning so production and tests execute the exact same sequence.

### 13.1. Versioned migrations

Each migration has a unique identifier/version and runs in deterministic order. Avoid editing the contents of a migration already applied in production.

### 13.2. Migration history table

Frameworks typically record migration version, checksum, execution time, and status. This serves as evidence of which scripts ran.

### 13.3. Repeatable migrations

Some frameworks support repeatable scripts that re-run when their checksum changes. Use these only for objects designed to be idempotent and understand the framework's semantics.

### 13.4. Transaction modes

Check whether the framework runs each migration in its own transaction, one large transaction, or autocommit. Commands like `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block.

### 13.5. Production command parity

Use the exact same binary/tool version, configuration, environment variables, role, and command flags as deployment. Running SQL manually outside the production workflow can miss orchestration bugs.

## 14. Running Migrations End-to-End on a Clone

Rehearsals must execute the exact migration chain from source version to target version.

### 14.1. Restore source clone

Restore the prior-version snapshot/schema/data into an isolated database. Verify the application release and migration marker.

### 14.2. Run preflight checks

Verify disk headroom, locks, active transactions, required extensions, schema drift, and privileges.

### 14.3. Run the migration runner

Execute the exact command, role, connection settings, and sequence as production. Capture stdout/stderr, exit codes, and server logs.

### 14.4. Do not skip older migrations

If production will migrate from version N to N+5, test the full chain starting at N. Testing only the final migration against a hand-built schema can miss assumptions from intermediate steps.

### 14.5. Record every phase

Log start/end times, migration identifiers, affected relations, rows processed, lock waits, and outcomes. On failure, preserve the clone and logs for investigation.

## 15. Transaction Boundaries and Atomicity

A migration may contain multiple DDL/data statements. Transaction boundaries determine rollback behavior.

### 15.1. Transactional migrations

If an entire migration runs inside one transaction, an error can roll back that transaction's changes. This does not guarantee external side effects outside the database are also rolled back.

### 15.2. Non-transactional commands

Certain commands cannot run inside a transaction block, such as `CREATE INDEX CONCURRENTLY` and `VACUUM`. The framework must support separate non-transactional migrations.

### 15.3. Long transaction costs

Large migration transactions can hold locks/snapshots for a long time, blocking autovacuum, increasing bloat, and retaining WAL/resources.

### 15.4. Partial progress

If a backfill runs in batches where each batch commits independently, a failure can leave partially converted data. Migrations need checkpoint/resume semantics.

### 15.5. External side effects

Migrations that call external services, send messages, or modify files are not automatically rolled back by PostgreSQL. Preferably separate side effects into workflows with idempotency/outbox patterns.

## 16. DDL Lock Testing

DDL can wait a long time for locks even when the command only updates metadata.

### 16.1. Lock modes

Identify the lock mode each command requires and determine which queries/transactions can block it. `ALTER TABLE` often requires strong locks at certain steps.

### 16.2. Lock timeout

Use `lock_timeout` so migrations fail fast if a lock cannot be acquired within budget.

~~~sql
SET lock_timeout = '3s';
ALTER TABLE public.orders ADD COLUMN source_code text;
~~~

### 16.3. Statement timeout

Set `statement_timeout` appropriate to the operation. A large table-rewriting migration needs a different deadline than metadata-only DDL.

### 16.4. Blocker tests

In staging, deliberately open a transaction holding a lock and run the migration to observe waiting, timeouts, cancellation, and recovery.

### 16.5. Queueing impact

A DDL statement waiting for `ACCESS EXCLUSIVE` can queue subsequent requests behind it. Measure impact on latency, not solely command execution time.

## 17. Index Migrations

Index creation/rebuilds must be tested on tables of production-like size and distribution.

### 17.1. CREATE INDEX

Standard index builds can block writes to the table for the duration of the build. Measure lock duration and resource consumption.

### 17.2. CREATE INDEX CONCURRENTLY

Concurrent builds allow DML to continue through most of the build, though they involve multiple phases, waits, and cannot run inside a transaction block.

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
~~~

### 17.3. Invalid indexes after failure

If a concurrent build fails, inspect `pg_index.indisvalid`/`indisready`. Never assume an index's mere existence means the planner can use it.

### 17.4. Unique indexes

Unique index builds can fail if duplicates exist. Run duplicate detection on prior-version data before deploying.

### 17.5. Disk/WAL headroom

Index builds require storage for the new index, temporary files, and WAL. Test peak disk usage and replication/archive retention.

## 18. Constraint Migrations

New constraints must hold across all historical data, not just newly inserted rows.

### 18.1. NOT NULL

Before adding `NOT NULL`, count `NULL`s and determine how to backfill/default them. Test concurrent writes so new rows do not introduce `NULL`s during the migration.

### 18.2. CHECK

Find rows violating the condition before validating the constraint. PostgreSQL supports `NOT VALID` for certain constraints followed by a separate `VALIDATE` step to reduce impact.

### 18.3. FOREIGN KEY

Check for orphan rows and remote/local relationship assumptions. `NOT VALID` followed by `VALIDATE CONSTRAINT` can phase the rollout.

### 18.4. UNIQUE

Find duplicates using the exact collation/operator semantics and business key. Resolve duplicates deterministically before creating the constraint.

### 18.5. Constraint validation

Measure validation duration on large tables, lock behavior, and impact on reads/writes. Inspect the catalog to confirm the constraint is marked validated.

## 19. Data Type Conversions

`ALTER COLUMN TYPE` can rewrite the table or require casting data; risk depends on source/target types and PostgreSQL version.

### 19.1. Cast validity

Test-run the cast across all historical values or samples containing boundary cases. Identify unconvertible rows before production.

### 19.2. Precision loss

Narrowing numeric scale/precision, truncating timestamps, or shortening strings can lose information.

### 19.3. Timezone semantics

Distinguish `timestamp without time zone` from `timestamptz`; verify timezone assumptions for historical values before converting.

### 19.4. Collation/encoding

Text conversions can affect comparisons, sorting, indexes, and uniqueness. Test Unicode, case/accent behavior, and collation versions.

### 19.5. Rewrite duration

If a type change rewrites the table, measure disk headroom, WAL, lock duration, replication lag, and recovery time on a realistically sized clone.

## 20. Batched Data Backfills

Backfills on large tables should report clear progress, bound transaction size, and support resumption.

### 20.1. Stable key ranges

Partition by primary key ranges or deterministic partitions so each batch processes a non-overlapping set of rows without gaps.

### 20.2. Idempotent updates

Update only unconverted rows or use deterministic transformations so re-running never corrupts results.

~~~sql
UPDATE public.orders
SET normalized_status =
    CASE legacy_status
        WHEN 'A' THEN 'active'
        WHEN 'C' THEN 'cancelled'
        ELSE 'unknown'
    END
WHERE normalized_status IS NULL
  AND order_id >= 1
  AND order_id < 10001;
~~~

### 20.3. Commit per batch

Commit each batch separately to bound lock duration, rollback cost, and WAL bursts. Persist the last processed key/checkpoint.

### 20.4. Throttling

Limit batch size/concurrency and pause between batches if CPU, I/O, replication lag, or foreground latency exceeds thresholds.

### 20.5. Concurrent application writes

During backfill, the application may continue modifying rows. Use dual-writes, triggers, version columns, or freeze windows as designed; never let a backfill overwrite newer updates.

## 21. Testing Idempotency and Resumability

Large data migrations often must run in batches or retry after transient failures.

### 21.1. Idempotency

Re-running a batch must not create duplicates or unexpectedly transform values a second time. Design `WHERE` predicates/unique keys to target only unprocessed rows.

### 21.2. Checkpoints

Record batch identifier, key range, rows attempted/updated, and commit status. Checkpoints must reflect transactions that actually committed.

### 21.3. Resuming after failure

Stop the migration midway, restart the runner, and verify it resumes safely. Never skip a batch with an unknown outcome.

### 21.4. Concurrent inserts

Insert new rows during the backfill to verify they receive the new schema/defaults/dual-writes and are not missed.

### 21.5. Concurrent updates/deletes

Modify or delete rows inside the active batch window. Verify the migration neither overwrites newer data nor resurrects deleted rows.

## 22. Dual-Writes and Temporary Data Synchronization

When an application must support both old and new schemas simultaneously, dual-writes can maintain both representations during the transition.

### 22.1. Dual-writes

The application writes to both old and new columns/tables. All code paths, workers, imports, and admin tools must follow the exact same contract.

### 22.2. Partial failures

If writing to the old structure succeeds while writing to the new structure fails, data diverges. Use a shared transaction whenever both reside in the same database and transaction boundary.

### 22.3. Backfill races

Backfills can run concurrently with dual-writes. Define update ordering, compare versions/timestamps, or use conditional updates so newer values are not overwritten.

### 22.4. Reconciliation

Periodically compare old/new representations, detect missing/mismatched rows, and repair them using deterministic rules.

### 22.5. Ending dual-writes

Stop dual-writes only after the backfill completes, mismatches are zero or accounted for, and all application instances have switched to the new schema.

## 23. Post-Migration Data Verification

Data validation must measure both quantities and business meaning.

### 23.1. Row counts

Compare before/after counts by table, partition, and logical group. If a migration splits/merges rows, use the expected transformation formula instead of requiring identical counts.

### 23.2. Aggregate checks

Compare total amounts, quantities, balances, min/max, counts by status/tenant/date, and key business aggregates.

### 23.3. Key coverage

Cross-check primary keys or stable business keys to detect missing or duplicate records.

### 23.4. Checksums

You can compute deterministic checksums across normalized column sets or key ranges. Normalize `NULL`s, timezones, numeric formatting, and ordering before hashing.

### 23.5. Business invariants

Verify business rules such as allocation sums matching totals, order lines matching order totals, non-negative balances if required by policy, and valid state transitions.

## 24. Before-and-After Data Reconciliation

A meaningful comparison requires knowing which data must stay unchanged and which data is allowed to transform.

### 24.1. Preserve set

List columns/records that must remain exact, such as identifiers, audit timestamps, or external references.

### 24.2. Transform set

For columns changing format/unit/status, define the old-to-new mapping and test all historical values.

### 24.3. Derived set

For recomputed columns, specify the formula, rounding, timezone, and null semantics.

### 24.4. Deleted/merged set

If the migration removes duplicates or merges records, store source-key-to-target-key mappings and reasons for auditing.

### 24.5. Exception set

Unconvertible rows should be quarantined/reported with an owner and remediation plan. Never silently drop bad data.

## 25. Checking Referential Integrity

Migrations can alter keys, split tables, or add foreign keys.

### 25.1. Orphan detection

Before adding a foreign key, find child rows lacking a matching parent.

~~~sql
SELECT c.parent_id, count(*)
FROM public.child_records AS c
LEFT JOIN public.parents AS p
  ON p.id = c.parent_id
WHERE c.parent_id IS NOT NULL
  AND p.id IS NULL
GROUP BY c.parent_id
ORDER BY count(*) DESC;
~~~

### 25.2. Key remapping

If primary keys change, build an `old_id -> new_id` mapping and verify every referencing table updated properly.

### 25.3. Cascading effects

Verify `ON DELETE`/`ON UPDATE` behavior. A migration can introduce new cascade paths and alter the blast radius of application deletes.

### 25.4. Deferred constraints

If using `DEFERRABLE` constraints, test both transaction-level deferred validation and commit-time failures.

### 25.5. Catalog validation

Inspect `pg_constraint`, `convalidated`, `condeferrable`, and related metadata after migration.

## 26. Checking Sequences and Generated Identifiers

Data migrations can copy rows with explicit IDs while the sequence keeps its old value.

### 26.1. Sequence state

Compare sequence `last_value`/`is_called` against `MAX(primary_key)` on the table. Never let `nextval` produce duplicate keys after cutover.

### 26.2. setval

Update the sequence via an appropriate procedure after imports/backfills:

~~~sql
SELECT setval(
    pg_get_serial_sequence('public.orders', 'order_id'),
    COALESCE((SELECT max(order_id) FROM public.orders), 1),
    EXISTS (SELECT 1 FROM public.orders)
);
~~~

Adjust this example to match the actual sequence/identity and table state.

### 26.3. Identity columns

Verify `GENERATED ALWAYS`/`BY DEFAULT` semantics and explicit value imports. Migrations must preserve the behavior expected by the application.

### 26.4. Concurrent inserts

Freeze or coordinate writers when synchronizing sequences to avoid racing with `nextval`. Perform this during a controlled cutover step.

### 26.5. Multi-table sequences

Inventory all sequences/identity columns, including standalone sequences without clear default dependencies or sequences shared by multiple tables.

## 27. Checking Indexes and Query Plans After Migration

A new schema can alter query plans even when data remains correct.

### 27.1. Index definitions

Compare index columns, expressions, predicates, operator classes, collations, and `INCLUDE` columns against the target schema.

### 27.2. Index validity

Verify `indisvalid` and `indisready` after concurrent builds. Invalid indexes do not serve production queries.

### 27.3. Planner statistics

Run `ANALYZE` after bulk backfills/data transformations so the planner sees the updated distribution.

### 27.4. Query plan baselines

Compare `EXPLAIN` plans of critical queries before and after, paying attention to join order, row estimates, scans, sorts/hashes, and buffers.

### 27.5. Runtime acceptance

Benchmark p50/p95/p99, throughput, and resource usage on a representative dataset. A plan shape change alone does not prove a regression.

## 28. Views, Functions, Triggers, and Stored Procedures

Schema migrations often affect objects that depend on tables and columns.

### 28.1. View dependencies

Find views/materialized views referencing renamed/dropped columns. `CREATE OR REPLACE VIEW` must preserve output contracts if the application depends on them.

### 28.2. Function signatures

Changing function argument/return types can break callers, grants, and dependent objects. Check overloaded functions and `search_path`.

### 28.3. Trigger behavior

Adding or modifying triggers can cause dual-writes or backfills to trigger unintended side effects. Test ordering, recursion, and transition behavior.

### 28.4. Materialized views

Determine refresh strategies and rebuild times. A migration can leave materialized views stale or unqueryable.

### 28.5. Dependency graphs

Use catalogs/dependency inspection and staging deployments to uncover objects not managed by migration scripts.

## 29. Privileges, Roles, and Row-Level Security

Migrations can change owners, grants, policies, or security semantics.

### 29.1. Role inventory

Compare roles, memberships, ownership, and attributes such as `LOGIN`, `BYPASSRLS`, and `CREATEDB`/`SUPERUSER` against policy.

### 29.2. Grants

Check table/schema/sequence/function privileges before and after. Newly created tables may not receive expected default privileges if owned by a different role.

### 29.3. Row-level security

Test policies under each application role and tenant dataset. Migrations modifying columns/functions referenced in policies can make users see too few or too many rows.

### 29.4. SECURITY DEFINER

Verify ownership and pinned `search_path` for security-definer functions. Schema changes can introduce object-shadowing risks.

### 29.5. Negative tests

Attempt unauthorized access to confirm the migration did not inadvertently widen permissions. Test both positive and negative paths with realistic roles.

## 30. Extension and Collation Changes in Migrations

Migrations may add/upgrade extensions or alter text semantics.

### 30.1. Extension prerequisites

Install matching packages/shared libraries for the PostgreSQL version on the test environment before running `CREATE`/`ALTER EXTENSION`.

### 30.2. Extension update scripts

Test `ALTER EXTENSION UPDATE` from prior versions on a clone containing real extension data/config tables.

### 30.3. Collation versions

If OS/ICU/libc versions change, check for collation version mismatches and index rebuild requirements.

### 30.4. Type/operator behavior

Extension types, operators, and casts can alter behavior or planner semantics. Test application queries and indexes that rely on them.

### 30.5. Restore compatibility

Test `pg_dump`/restore or physical recovery with the extension packages and versions required by the migration target.

## 31. Partitioned Tables and Migrations

Partitioned tables have DDL/data behaviors different from single tables.

### 31.1. Parent/child schemas

Ensure columns, types, constraints, and indexes are applied appropriately across the parent and existing partitions.

### 31.2. New partitions

If a migration creates new partitions, test partition bounds, default partitions, and insert routing.

### 31.3. Attach/detach

`ATTACH PARTITION` can scan/validate constraints and acquire locks. Test with large tables and concurrent writes.

### 31.4. Partition indexes

Confirm partitioned indexes and child indexes are valid and complete across all partitions.

### 31.5. Historical partitions

Do not test only the current partition. Historical partitions may hold schema/data anomalies or very different distributions.

## 32. Large Objects, JSON, and Specialized Data

Certain types/objects behave distinctively during migrations.

### 32.1. JSON/JSONB

Check malformed legacy JSON, key casing, numeric/string distinctions, missing keys, and transformation cost.

### 32.2. Arrays and composites

Test empty arrays, `NULL` arrays, nested values, composite types, and type casts.

### 32.3. Large objects

If using PostgreSQL large objects, check `lo` metadata, ownership/privileges, and referential integrity. `pg_dump` options must include required objects.

### 32.4. TOAST

Large text/JSON/`BYTEA` values can sharply increase table rewrites, storage, and WAL. Use realistically sized records in rehearsals.

### 32.5. Full-text/geospatial types

Extension-backed types/indexes require compatible packages/versions and dedicated migration tests for operators, casts, and index rebuilds.

## 33. Compatibility Between Application Versions

Schema migrations may happen while multiple application instances run different releases.

### 33.1. Old application on expanded schema

Confirm the old app continues running when new columns/tables are added. Defaults, triggers, and `NOT NULL` changes must not break older code.

### 33.2. New application on old schema

If required by the rollout, confirm the new app can operate before migration finishes or uses feature flags to avoid accessing non-existent objects.

### 33.3. Mixed-version periods

Run old and new application instances concurrently against the expanded schema and test read/write consistency.

### 33.4. Worker compatibility

Background workers, scheduled jobs, ETL pipelines, admin tools, and scripts may deploy more slowly than web applications. Include them in the compatibility matrix.

### 33.5. Contract gates

Contract the old schema only when no clients/transactions/jobs still use it and telemetry confirms legacy access has dropped to zero over an observation period.

## 34. Testing Migrations Under Concurrent Load

A migration may pass on an idle database yet cause an outage while production traffic continues running.

### 34.1. Representative concurrency

Run production-like read/write transactions during the migration, including short requests, long transactions, and batch jobs.

### 34.2. Lock contention

Monitor `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids` to see what the migration waits on and which sessions the migration blocks.

### 34.3. Query latency

Measure p50/p95/p99 and error rates of critical endpoints during the migration, not just how long the migration command itself runs.

### 34.4. Connection pool behavior

Test pool exhaustion, waiting clients, reconnect behavior, and application retries when DDL or remote operations introduce delays.

### 34.5. Deadlocks and serialization errors

Generate concurrent transactions that can touch the same rows/constraints to verify deadlock, serialization failure, and application retry behavior.

## 35. Testing WAL, Disk, and Replication Impact

Data migrations and index builds can generate heavy WAL, increasing storage consumption and replica lag.

### 35.1. WAL generation

Record `wal_bytes`/LSN progression before, during, and after the migration. Large backfills can push WAL generation far above baseline.

### 35.2. Disk headroom

Monitor data directory, `pg_wal`, temporary files, index growth, and free filesystem space. Estimate peak usage rather than only final table size.

### 35.3. Replication lag

Monitor write/flush/replay lag and slot-retained WAL. Migrations can slow standbys or retain WAL for extended periods.

### 35.4. Archive throughput

If using WAL archiving/PITR, check archive queues and destination capacity during migration. Never let archive backlogs exceed your recovery budget.

### 35.5. Checkpoint pressure

Bulk writes/index builds can spike checkpoint activity and I/O. Record checkpoint frequency, write times, and storage latency.

## 36. Testing Autovacuum and Bloat After Migration

Large updates/deletes generate dead tuples and can cause table/index bloat.

### 36.1. Dead tuples

Monitor `n_dead_tup`, vacuum history, and table sizes before and after backfills.

### 36.2. Long snapshots

Long-running transactions can block vacuum from reclaiming dead tuples. Test transaction durations and idle-in-transaction behavior.

### 36.3. Autovacuum catch-up

Verify autovacuum can process tables after migration without overly competing with foreground workloads.

### 36.4. Analyze after backfill

Run `ANALYZE` after data distribution changes and check planner estimates and critical query plans.

### 36.5. Post-migration maintenance

Factor required post-migration vacuum/analyze/reindex time into the change window or stabilization plan.

## 37. Testing Migration Performance and Duration

Timings on a clone help estimate the production window if the environment is comparable.

### 37.1. Baseline duration

Measure every migration step, including lock acquisition, execution, validation, and cleanup—not just total command wall time.

### 37.2. Scaling behavior

Run across datasets of multiple sizes to understand how cost scales with row count/table size. Some operations rewrite entire tables while others depend on indexes/locks.

### 37.3. Resource profiles

Record CPU, memory, disk IOPS/latency, network, WAL, temp files, and replication lag.

### 37.4. Concurrency profiles

Compare duration on an idle database versus under a representative workload. Use the results to calculate an impact budget.

### 37.5. Window estimates

Sum step durations across sequence, dependencies, retry/rollback buffers, and validation. Use percentiles from multiple rehearsals rather than a single run.

## 38. Testing Failure Injection

Deliberately make migrations fail in test environments to understand recovery behavior.

### 38.1. SQL error mid-migration

Inject a failing statement on a clone or construct fixtures that cause constraint validation to fail. Verify transaction rollback/partial progress behaves as expected.

### 38.2. Connection loss

Drop the client connection during a long migration and inspect server transaction state, migration history, and retry safety.

### 38.3. Disk pressure

In an isolated environment, constrain disk space to observe index build/backfill behavior and verify monitoring/stop conditions trigger.

### 38.4. Lock timeout

Introduce a controlled blocker and verify the migration fails fast, logs sufficient context, and does not create long request queues.

### 38.5. Worker/application crashes

Kill the migration runner or worker mid-batch to verify checkpoints, idempotency, and resume paths.

## 39. Rollback Strategies

Rollbacks must be designed around the change type and data written after cutover.

### 39.1. Transaction rollback

For a migration inside an uncommitted transaction, `ROLLBACK` can undo transactional DDL/data changes.

### 39.2. Compensating migrations

Once a migration commits, a separate reverse migration may be needed. Reverse migrations must preserve new data written after cutover.

### 39.3. Forward fixes

In many cases, fixing a bug with a forward migration is safer than rolling back a schema/data state that has already received new writes.

### 39.4. Restore/PITR

If a change is destructive or causes irreversible data corruption, restore/PITR may be required. Account for RPO, RTO, and reconciliation of writes after the recovery point.

### 39.5. Rollback boundaries

Document the point of no simple return—for example, once the application writes data in a new format or a contract migration drops legacy columns.

## 40. Testing Restore and Recovery

Migration tests should prove the recovery plan actually works, not merely that backup files exist.

### 40.1. Pre-migration backups

Take a backup/restore point before destructive migrations per policy. Record the backup identifier and WAL coverage.

### 40.2. Restoring an isolated clone

Restore into an isolated environment, verify the source schema/data, and re-run migrations from the start.

### 40.3. PITR targets

If rolling back to a point in time might be needed, rehearse PITR to right before migration/cutover and verify database consistency.

### 40.4. Data after restore

Define how transactions committed after the backup/recovery point will be reconciled: event replay, queue reprocessing, or manual business reconciliation.

### 40.5. Recovery timing

Measure restore duration, WAL replay, application validation, and traffic restoration. RTO must include all of these steps.

## 41. Do Not Confuse Migration Rollback with Application Rollback

Application code and database schemas have distinct lifecycles.

### 41.1. Code rollback

Rolling application code back to an older version is safe only if the new schema remains compatible with the old code.

### 41.2. Schema rollback

Rolling back a schema can drop columns/data written by the new code. Inspect post-cutover write patterns carefully.

### 41.3. Backward compatibility

The expand phase usually preserves the old schema long enough for safe application rollbacks. The contract phase usually closes the simple rollback path.

### 41.4. Data format compatibility

If new code writes enum/status/JSON formats that old code cannot parse, rolling back the application can still fail even if the schema stays intact.

### 41.5. Rollback rehearsals

Practice both application rollback and schema/data recovery on a clone containing post-cutover writes to prove the procedure.

## 42. Migration Tests in CI

CI should test the migration chain on a database initialized from a prior-version schema.

### 42.1. Build the source-version database

Start a PostgreSQL service/container on the target version and apply the prior schema/migration history or restore a fixture snapshot.

### 42.2. Seed representative data

Load fixtures containing `NULL`s, duplicates, historical values, boundary cases, and references. Keep seeds deterministic.

### 42.3. Apply pending migrations

Run the migration runner from the current source version to the target using the exact deployment command.

### 42.4. Assert schema/data

Run SQL assertions for columns/types/constraints/indexes, row counts, mappings, invariants, and migration history.

### 42.5. Test matrix

Run across supported PostgreSQL major versions, extension versions, and relevant application versions. Do not test only a single version if the product supports multiple versions.

## 43. Migration Tests in Staging

Staging needs scale and topology closer to production than CI provides.

### 43.1. Restore a recent sanitized snapshot

Use a snapshot recent and large enough to be meaningful. Record its source timestamp and sanitization version.

### 43.2. Rehearse the production command

Use the exact release artifact, credential model, runner, flags, and environment variables.

### 43.3. Load testing

Run representative traffic during the migration, including peak/steady workloads and relevant scheduled jobs.

### 43.4. Observe the full topology

Monitor primary/standby, logical subscribers, archiving, poolers, application services, and monitoring.

### 43.5. Sign-off evidence

Archive durations, impact metrics, validation outputs, unresolved risks, stop conditions, and approvals per the change process.

## 44. Production Rehearsals and Canaries

Before full production cutover, migrations can be tested on a canary database or a single tenant/subset if architecture permits.

### 44.1. Canary scope

Choose a subset with a representative data shape but a small blast radius. Avoid picking only tiny, trivial-to-migrate tenants.

### 44.2. Compare behavior

Compare schemas, data invariants, query latency, and application errors between the canary and baseline.

### 44.3. Gradual rollout

Shift traffic incrementally, monitor mismatches/errors/latency, and halt traffic increases if thresholds are breached.

### 44.4. Full cutover gate

Proceed to full cutover only when canary validation passes and the migration sequence has been verified for the remaining data.

### 44.5. Limits of canaries

If a migration involves global uniqueness, cross-tenant references, or shared tables, a single-tenant canary may not be representative. Full-database clone testing remains necessary.

## 45. Observability During Migrations

A migration needs telemetry covering both command progress and service impact.

### 45.1. Migration runner logs

Log migration ID, start/end times, duration, step, affected rows, error codes, and retry counts.

### 45.2. Database activity

Monitor active sessions, wait events, locks, blockers, long transactions, and idle-in-transaction sessions.

### 45.3. Resource metrics

Monitor CPU, memory, disk latency/IOPS, free space, WAL, checkpoints, and temp files.

### 45.4. Application metrics

Request rate, error rate, p95/p99, connection pool waits, queue depth, and retries.

### 45.5. Replication/recovery metrics

Monitor replay lag, slot-retained WAL, archive backlog, and backup status. Alert thresholds must be defined prior to migration.

## 46. Organizing the Migration Test Suite

A test suite should be layered so CI runs fast while staging tests deeply.

### 46.1. Unit-level transformation tests

Test transformation functions/SQL expressions on small edge cases—fast to run and easy to debug.

### 46.2. Schema migration integration tests

Initialize a prior-version schema, seed fixtures, and execute the migration chain on real PostgreSQL. Test syntax/catalog behavior that mocks cannot represent.

### 46.3. Data reconciliation tests

Run counts, key coverage, checksums, and business invariants on sufficiently large datasets.

### 46.4. Performance tests

Measure durations, locks, resource usage, and query latency on a representative clone. Run in staging/nightly rather than on every commit if expensive.

### 46.5. Recovery tests

Test resumption, transaction rollbacks, forward fixes, restore/PITR, and application rollbacks based on risk level.

## 47. Post-Migration SQL Assertions

Assertions should fail loudly when schemas or data miss the target.

### 47.1. Checking columns

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

### 47.2. Checking constraints

~~~sql
SELECT
    conname,
    contype,
    convalidated,
    condeferrable
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
ORDER BY conname;
~~~

### 47.3. Checking indexes

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready,
    indisunique
FROM pg_index
WHERE indrelid = 'public.orders'::regclass
ORDER BY indexrelid::regclass::text;
~~~

### 47.4. Checking migration markers

Read version/checksum from the framework's migration history table. Assert that the target version applied exactly once.

### 47.5. Assertions must check expected values

Do not merely print query results to logs. The test runner must compare against expected outcomes and exit non-zero when an invariant fails.

## 48. Data Validation Queries

Examples of queries checking data after a migration.

### 48.1. Remaining NULLs

~~~sql
SELECT count(*) AS missing_status
FROM public.orders
WHERE normalized_status IS NULL;
~~~

### 48.2. Unexpected values

~~~sql
SELECT normalized_status, count(*)
FROM public.orders
GROUP BY normalized_status
ORDER BY count(*) DESC;
~~~

### 48.3. Duplicate business keys

~~~sql
SELECT external_order_id, count(*)
FROM public.orders
GROUP BY external_order_id
HAVING count(*) > 1;
~~~

### 48.4. Aggregate reconciliation

~~~sql
SELECT
    count(*) AS rows_total,
    count(DISTINCT order_id) AS unique_orders,
    sum(total_amount) AS amount_total,
    min(created_at) AS first_order,
    max(created_at) AS last_order
FROM public.orders;
~~~

### 48.5. Cross-table invariants

~~~sql
SELECT o.order_id
FROM public.orders AS o
LEFT JOIN public.customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Adapt queries to business rules and expected transformations. If a migration legitimately merges/deletes rows, build expected reconciliation formulas rather than mechanically applying old invariants.

## 49. Test Artifacts and Migration Rehearsal Reports

Reports must allow others to reproduce the test and understand release decisions.

### 49.1. Source identity

Record source backup/snapshot ID, database name, PostgreSQL version, application release, and migration version.

### 49.2. Environment identity

Record CPU/RAM/storage, PostgreSQL configuration, extensions, collations, and network topology.

### 49.3. Migration evidence

Archive runner logs, SQL output, start/end timestamps, rows processed, lock waits, failures, and retries.

### 49.4. Validation evidence

Archive schema diffs, row counts, checksums, business invariants, constraint/index validity, and application smoke test results.

### 49.5. Performance evidence

Archive per-step durations, p95/p99, CPU/I/O, WAL, peak disk, replication lag, and relevant query plans.

## 50. Acceptance Criteria and Release Gates

Acceptance criteria must be defined prior to rehearsal.

### 50.1. Correctness gate

Migration chain completes; schema/objects match target; data transformations and business invariants pass.

### 50.2. Compatibility gate

Old/new application compatibility satisfies the rollout plan; privileges, triggers, jobs, and integrations work.

### 50.3. Performance gate

Migration duration, lock time, query latency, resource usage, disk headroom, and replication lag stay within budget.

### 50.4. Recovery gate

Backup/restore, rollback/forward fix, resume behavior, and operational ownership have been demonstrated.

### 50.5. Decision

Pass/fail must be evidence-based. Any exceptions require documented risk, owner, mitigation, and approval prior to production.

## 51. Rehearsal Runbook from a Prior-Version Database

A sample rehearsal procedure can follow this sequence.

1. Select a source snapshot matching the current application/schema version.
2. Restore the snapshot into an isolated PostgreSQL environment.
3. Apply version-controlled sanitization/supplementary seed scripts.
4. Confirm schema, extensions, roles, and migration markers match the source state.
5. Capture baseline counts, invariants, query plans, and resource metrics.
6. Run preflight checks: disk, locks, connections, replication, and permissions.
7. Execute the migration runner with the exact production artifact/flags/role.
8. Record timings, logs, rows processed, locks, WAL, and failures.
9. Run schema/data/business assertions.
10. Run application smoke tests and mixed-version compatibility tests.
11. Run load/performance/replication checks.
12. Exercise recovery paths matched to the migration's risk.
13. Archive artifacts and evaluate against acceptance thresholds.
14. Update runbooks or migration scripts if issues occur; re-run from a clean source snapshot.

## 52. Example: Adding a NOT NULL Column to a Large Table

Suppose the `orders` table in the source version has millions of rows and a new `normalized_status` column must always hold a value.

### 52.1. Source inspection

Count rows, `NULL` distribution of `legacy_status`, rare status values, and insert/update rates. Define the mapping for every legacy value.

### 52.2. Expand

Add nullable `normalized_status`. Check DDL lock duration and old application compatibility.

### 52.3. Backfill

Update by small key ranges using a `CASE` mapping. Commit each batch and record checkpoints.

### 52.4. Dual-write

Deploy application code writing both `legacy_status` and `normalized_status`; test concurrent writes so no mismatches arise.

### 52.5. Validate and contract

Verify zero remaining `NULL`s/unmapped values outside policy, add `CHECK`/`NOT NULL` using an appropriate strategy, switch reads to the new column, and drop the legacy column in a subsequent release.

## 53. Example: Creating a Unique Constraint After Data Normalization

### 53.1. Define the business key

Clarify normalization rules: trimming, case folding, Unicode normalization, and collation. The unique key must match exact business semantics.

### 53.2. Detect duplicates

Write an expression query matching the normalization rule to group duplicate candidates. Save a mapping of rows requiring merge/resolution.

### 53.3. Resolve conflicts

Select canonical records per business rules, repoint references, and keep an audit trail. Never delete duplicates arbitrarily.

### 53.4. Build the unique index

Once data is clean, build the unique index within the lock/downtime budget; consider `CREATE UNIQUE INDEX CONCURRENTLY` and handle invalid indexes if a build fails.

### 53.5. Validate

Verify the index is valid/unique, confirm duplicate inserts are rejected, and test application behavior under concurrent key creation/updates.

## 54. Example: Changing Column Type and Normalizing Timezones

### 54.1. Profile source values

Inspect min/max, `NULL`s, malformed strings, timezone offsets, and records near DST boundaries.

### 54.2. Dry-run conversions

Run conversion expressions on a clone, log unconvertible rows, and compare sample values against expected business times.

### 54.3. Expand representation

If needed, add a new column with the target type instead of performing an immediate rewrite/destructive change. Backfill and dual-write during the compatibility window.

### 54.4. Reconcile

Compare normalized timestamps in UTC/expected timezone and check reports/date partitions.

### 54.5. Cutover

Switch the application to read the new column, monitor errors, and drop the legacy representation only once the rollback window closes.

## 55. Common Migration Testing Mistakes

1. Testing only on an empty database or a few seed rows.
2. Using a manually built new schema instead of restoring a prior-version schema.
3. Skipping the migration chain and running only the latest script.
4. Testing on a different PostgreSQL major version from production without documenting differences.
5. Failing to install required extensions/collations before rehearsal.
6. Over-sanitizing datasets and erasing important skew, duplicates, or `NULL`s.
7. Comparing only row counts without verifying business invariants.
8. Ignoring sequence state after importing explicit identifiers.
9. Adding `NOT NULL`/`UNIQUE`/`FK` without profiling historical violations.
10. Creating an index on a small table and extrapolating production lock/duration.
11. Running a backfill in one giant transaction without checkpoints.
12. Failing to test backfills alongside concurrent application writes.
13. Assuming a migration is rollback-safe simply because DDL is inside a transaction.
14. Ignoring external side effects of triggers/functions/jobs.
15. Overlooking old-version application instances/workers.
16. Failing to measure WAL, peak disk, and replication lag.
17. Failing to test failed concurrent index builds or invalid index cleanup.
18. Failing to test restore/PITR from pre-migration state.
19. Editing a migration already applied in production instead of creating a new migration.
20. Failing to save the source snapshot ID and logs to reproduce results.
21. Failing to set acceptance/stop thresholds before rehearsal.
22. Monitoring only the migration command while ignoring application latency/error rates.
23. Relying on a small canary lacking cross-tenant/global constraints as sufficient proof.
24. Marking a migration passed despite quarantined rows lacking an owner.
25. Running contract migrations while legacy clients remain active.

## 56. Practice Exercises

### Exercise 1 — Prior-version baseline

Why must testing start from a prior-version schema and data?

**Answer:** Because migrations transform an existing state; historical values, constraints, table sizes, and dependencies can cause migrations to fail.

### Exercise 2 — Schema baseline

Name four kinds of objects to inventory besides tables.

**Hint:** Indexes, constraints, sequences, views, functions, triggers, types, grants, extensions.

### Exercise 3 — Data baseline

Why are row counts alone insufficient to describe a dataset?

**Answer:** They do not describe `NULL`s, duplicates, skew, ranges, historical values, or relationships.

### Exercise 4 — Snapshots

Why is recording the snapshot identifier necessary?

**Answer:** To recreate the exact same source state and compare across rehearsal runs.

### Exercise 5 — Sanitization

How can sanitizing production data harm migration testing?

**Answer:** It can break uniqueness, referential links, skew, and edge cases that the migration must handle.

### Exercise 6 — Expand-and-contract

Why not drop the old column in the very first release?

**Hint:** Old application instances/workers need a compatibility period and a rollback window.

### Exercise 7 — Migration history

Should you edit the migration history table to skip a failed migration?

**Answer:** No; determine the exact state and fix via controlled migration/recovery.

### Exercise 8 — Transaction boundaries

Can `CREATE INDEX CONCURRENTLY` run inside a transaction block?

**Answer:** No; the migration framework must support non-transactional steps.

### Exercise 9 — Lock timeout

What does `lock_timeout` help control?

**Answer:** Limits lock acquisition wait time so a migration fails fast instead of waiting indefinitely.

### Exercise 10 — Unique constraints

What must be checked before creating a unique index?

**Answer:** Duplicate candidates under the exact business key/normalization/collation rules.

### Exercise 11 — NOT NULL

What must be done before setting `NOT NULL` on an existing column?

**Hint:** Profile `NULL`s, backfill/default, control concurrent writes, and validate.

### Exercise 12 — Foreign keys

Why search for orphan rows before adding an FK?

**Answer:** Historical child rows may reference non-existent parents.

### Exercise 13 — Backfills

Why split a backfill into batches?

**Answer:** Reduces lock duration, rollback cost, and WAL bursts, and enables resuming/throttling.

### Exercise 14 — Idempotency

What does an idempotent batch mean?

**Answer:** Retrying the same batch neither corrupts results nor creates duplicate side effects.

### Exercise 15 — Concurrent writes

Can a backfill overwrite newer application updates?

**Answer:** Yes, unless an appropriate conditional/versioning/dual-write strategy is used.

### Exercise 16 — Sequence state

What must be checked after importing explicit IDs?

**Answer:** The sequence/identity next value must exceed all used values to prevent duplicate keys.

### Exercise 17 — Checksums

Why do checksums require normalizing data?

**Answer:** `NULL`s, timezones, numeric formatting, and row ordering can produce different hashes for equivalent data.

### Exercise 18 — Query plans

Why compare `EXPLAIN` after a migration?

**Answer:** Schema/index/data changes can cause the planner to pick different plans and impact performance.

### Exercise 19 — Application compatibility

What does mixed-version testing verify?

**Answer:** Old and new application instances and workers can operate together during the expanded schema window.

### Exercise 20 — RLS

Why test migrations under multiple application roles?

**Answer:** Grants and row-level security can cause each role to see or modify different sets of rows.

### Exercise 21 — WAL

How can a large backfill affect replication?

**Answer:** Increases WAL generation, replay lag, slot retention, and archive backlog.

### Exercise 22 — Failure injection

Why deliberately trigger SQL errors/lock timeouts in a clone?

**Answer:** To prove rollback, partial progress, logging, and recovery behavior.

### Exercise 23 — Rollback boundaries

What can make an application rollback unsafe?

**Answer:** New code has written data formats that old code cannot parse, or a contract migration has dropped legacy objects.

### Exercise 24 — PITR

Why rehearse restore/PITR?

**Answer:** Having a backup file does not prove restoration finishes within RTO or yields intact data.

### Exercise 25 — CI vs. staging

How do the roles of CI and staging differ?

**Answer:** CI quickly tests correctness/migration chains; staging tests scale, topology, concurrency, and operational impact.

### Exercise 26 — Canaries

What can a single-tenant canary miss?

**Answer:** Global uniqueness, cross-tenant references, shared tables, and different data distributions.

### Exercise 27 — Acceptance criteria

When is a rehearsal considered passed?

**Hint:** Correctness, compatibility, performance, recovery, and evidence all meet established thresholds.

### Exercise 28 — Migration duration

Why is a single rehearsal insufficient to estimate a window?

**Answer:** Runtime varies with cache, load, storage, data distribution, and background tasks.

### Exercise 29 — Source snapshots

If schema drift already exists before the migration, how should it be handled?

**Answer:** Document/reconcile the drift and establish a valid source state before evaluating the migration.

### Exercise 30 — Forward fixes

When can a forward fix be safer than a rollback?

**Answer:** When new writes already use the new schema/format or when rolling back risks losing data.

## 57. Source Database Preparation Checklist

- [ ] Application release, PostgreSQL version, and migration markers identified?
- [ ] Source snapshot/backup has verified consistency and explicit identifier?
- [ ] Schema DDL, indexes, constraints, sequences, and functions/triggers inventoried?
- [ ] Extensions, collations, roles, grants, and ownership recorded?
- [ ] Row counts and data distribution profiles saved?
- [ ] Fixtures include `NULL`s, duplicates, legacy values, boundary values, and orphan candidates?
- [ ] Sensitive data sanitized per policy while preserving relationships/skew?
- [ ] Original snapshot protected and working clone created separately?
- [ ] Source state restoration verified before running migrations?

## 58. Migration Rehearsal Execution Checklist

- [ ] Exact production migration runner/version/flags/role used?
- [ ] Full migration chain run from source version?
- [ ] Preflight disk, locks, sessions, extensions, and privileges passed?
- [ ] Appropriate DDL `lock_timeout`/`statement_timeout` configured?
- [ ] Non-transactional commands handled properly?
- [ ] Backfills include batching/checkpoints/idempotency/throttling?
- [ ] Concurrent application writes/workers simulated?
- [ ] Start/end duration, rows, locks, WAL, and errors recorded?
- [ ] Failure/resume paths tested on a clone?
- [ ] Source clone/logs preserved on failure?

## 59. Post-Migration Validation Checklist

- [ ] Target schema and migration history accurate?
- [ ] Columns/types/defaults/nullability verified?
- [ ] Constraints validated and indexes valid/ready?
- [ ] Row counts/key coverage/checksums match expected transformations?
- [ ] Business aggregates/invariants pass?
- [ ] Sequences/identity values safe?
- [ ] Views/functions/triggers/extensions/partitions working?
- [ ] Grants/RLS/security negative tests pass?
- [ ] Application smoke tests and mixed-version compatibility pass?
- [ ] Critical query plans/latency pass?
- [ ] WAL/disk/autovacuum/replication/archiving stable?

## 60. Release and Recovery Gate Checklist

- [ ] Migration duration fits within approved window?
- [ ] Lock impact/error rate/latency within budget?
- [ ] Backup/PITR restore test and RTO/RPO evidence available?
- [ ] Rollback boundaries and forward-fix strategies clear?
- [ ] Canary/full rollout gates and stop conditions defined?
- [ ] Owners/on-call/escalation contacts confirmed?
- [ ] Artifacts, source snapshot ID, logs, and validation reports archived?
- [ ] Exceptions have risk owners/mitigations/approvals?
- [ ] Legacy apps/workers no longer depend on objects before contract phase?

## 61. Quick Reference Table

| Component | Purpose |
|---|---|
| Prior-version schema | Source structure prior to migration |
| Data snapshot | Consistent source rows for reproduction |
| Schema baseline | DDL/objects/privileges inventory |
| Data profile | NULLs/skew/ranges/duplicates/relationships |
| Migration history | Applied versions/checksums |
| Expand-and-contract | Phased compatible schema transition |
| DDL lock | Locks affecting concurrent sessions |
| lock_timeout | Limit on lock wait duration |
| statement_timeout | Limit on statement duration |
| CREATE INDEX CONCURRENTLY | Index creation minimizing DML blocking |
| NOT VALID | Add certain constraints before validating |
| VALIDATE CONSTRAINT | Check historical rows against constraint |
| Backfill | Transform existing data |
| Checkpoint | Record committed batch progress |
| Idempotency | Retries cause no drift or corruption |
| Dual-write | Write old/new representations concurrently |
| Reconciliation | Compare and repair mismatches |
| Sequence state | Next identifier after import/backfill |
| pg_stat_activity | Session/query state |
| pg_locks | Lock state |
| pg_stat_replication | Replication progress |
| WAL | Write-ahead log generation/retention |
| PITR | Point-in-time recovery |
| Canary | Trial rollout/migration on a small scope |
| Acceptance criteria | Predefined pass/fail conditions |

## 62. Conclusion

**Migrations must be tested on a consistent copy of the prior-version schema and data, executing the exact migration chain as production.** An empty database does not represent accumulated historical values, `NULL`s, duplicates, skew, relationships, table sizes, extensions, and object dependencies. Source snapshots must carry clear identities, remain protected, and be restorable so every rehearsal begins from the exact same state.

A thorough rehearsal verifies DDL locks, constraints/indexes, data backfills, sequences, dependent objects, privileges/RLS, and compatibility across application versions. Data validation must cover row/key coverage, normalized checksums, and business invariants; performance validation must measure lock waits, query latency, CPU/I/O, WAL, peak disk, autovacuum, and replication lag. Backfills require batching, checkpoints, idempotency, and handling of concurrent writes.

Rollback is not always straightforward once a migration commits or the application writes data in a new format. Test transaction rollbacks, compensating/forward migrations, application rollbacks, and restore/PITR according to risk. CI verifies correctness on prior-version fixtures; staging rehearsals confirm scale, topology, concurrency, and recovery; production proceeds only once acceptance criteria, stop conditions, and owners are clear.

Testing principle: **restore the exact old state, run the exact migration chain, prove new data preserves business meaning, measure impact under load, and rehearse recovery before touching production.**
