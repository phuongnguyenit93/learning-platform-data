# Data Type Changes, Backfilling, and Impact Control in PostgreSQL

Changing a column's data type may look like a single `ALTER TABLE` command, yet in production it can affect millions of rows, indexes, constraints, running applications, replication, and recovery times. A conversion can hold a strong lock for a long time, rewrite the entire table, generate heavy WAL, or render older application versions incompatible.

For large databases and high-uptime systems, schema migrations should be treated as a multi-phase workflow. The standard pattern is **expand – migrate – contract**: expand the schema so old and new application versions can run concurrently, migrate data in controllable batches, switch traffic to the new structure, and only remove the old structure once no dependent consumers remain.

This lesson explains how to safely change data types, design shadow columns, implement dual writes, run batched backfills, control locks/I/O/WAL, verify results, and plan rollbacks. Examples use PostgreSQL SQL and should be tuned to your major version, table size, and actual workload.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Assess the impact of `ALTER COLUMN TYPE` before deployment.
2. Distinguish metadata-only changes from table rewrites and index rebuilds.
3. Choose between direct conversion and expand–migrate–contract.
4. Design shadow columns and compatibility across multiple application versions.
5. Write idempotent backfills, chunk into batches, and control concurrency.
6. Handle dual writes, retries, race conditions, and data changing during backfill.
7. Monitor lock waits, transaction age, WAL, replication lag, and disk headroom.
8. Use `NOT VALID`/`VALIDATE CONSTRAINT` and concurrent index builds when appropriate.
9. Verify completeness, correctness, and application behavior before cutover.
10. Establish rollback/roll-forward plans and migration stop conditions.
11. Roll out migrations using canaries, maintenance windows, and phased rollouts.
12. Record progress, metrics, ownership, and post-change outcomes.

## 2. Why Are Data Type Changes Risky?

### 2.1. Impact Extends Beyond the Column

A column may be used by:

- Application queries, ORM models, and prepared statements;
- Views, materialized views, functions, triggers, and generated columns;
- Indexes, unique constraints, primary keys, and foreign keys;
- Check constraints, partition keys, and partition bounds;
- Logical replication publications and subscriptions;
- ETL, CDC, reporting, BI, and downstream services;
- Stored procedures, jobs, exports, and API contracts.

Changing a type can alter cast resolution, operator selection, index usability, sort semantics, precision, timezone handling, or serialized values.

### 2.2. Lock Duration

Many forms of `ALTER TABLE` require an `ACCESS EXCLUSIVE` lock. This lock conflicts with nearly all operations on the relation. If the command must rewrite a large table, the lock may be held for most of the rewrite, blocking reads and writes.

Even when the DDL executes quickly after acquiring the lock, it can wait a long time to acquire it. A DDL waiting for `ACCESS EXCLUSIVE` can cause new queries to queue behind it depending on the lock queue, triggering a cascading outage.

### 2.3. Table Rewrites

If a conversion is not binary-coercible or PostgreSQL must alter the physical representation, `ALTER COLUMN TYPE` can rewrite the table. Rewrites read/write data, require extra temporary disk space, generate WAL, and impact cache and I/O.

Certain type changes can avoid rewrites under specific PostgreSQL rules and versions, such as increasing a `varchar` length limit in some cases. Never assume every "same-data" change is metadata-only; check the documentation and test on a copy of comparable size.

### 2.4. Indexes and Constraints

Indexes depending on the column may need rebuilding or be affected by type, operator class, or collation changes. Unique, check, and foreign key constraints may require re-validation or undergo semantic changes. Index rebuilds also consume disk, I/O, and WAL.

### 2.5. WAL and Replication

Large rewrites or backfills can generate WAL faster than standbys or archives can process it. Consequences include:

- Increased replication lag;
- Replication slots retaining WAL and bloating `pg_wal`;
- WAL archive backlogs;
- Longer backup/restore windows;
- DR replicas failing to meet RPO;
- Disk exhaustion impacting the entire cluster.

### 2.6. Application Impact

Older applications may send values that no longer cast, expect legacy formats, or read the column mid-conversion. ORMs may cache schema metadata. Prepared statements may need refreshing when types or result metadata change.

### 2.7. Rollbacks Are Not Free

After backfilling or writing data in the new type, rolling back can lose information if the reverse conversion is not lossless. For example, `numeric` to `integer` loses fractional digits; `timestamp with time zone` to `timestamp without time zone` can lose timezone context. Design rollback before starting.

## 3. Evaluating the Type Conversion

### 3.1. Define Source and Target Semantics

First document:

- Current type and target type;
- Nullability;
- Default expression;
- Allowed value range;
- Precision and scale;
- Collation and encoding;
- Timezone semantics;
- Sort and equality semantics;
- Application/API representation;
- Constraint and index dependencies.

"Converting data without errors" is not enough; business meaning must be preserved.

### 3.2. Inspect Data Before Conversion

Example converting text to integer:

~~~sql
SELECT
    count(*) AS total_rows,
    count(*) FILTER (WHERE value_text IS NULL) AS null_rows,
    count(*) FILTER (
        WHERE value_text IS NOT NULL
          AND value_text !~ '^[+-]?[0-9]+$'
    ) AS non_integer_rows
FROM public.imported_values;
~~~

Check range before casting:

~~~sql
SELECT
    min(value_text::numeric) AS min_value,
    max(value_text::numeric) AS max_value
FROM public.imported_values
WHERE value_text ~ '^[+-]?[0-9]+$';
~~~

Only cast inside validation queries after ensuring the data is valid; do not write a query that could fail casting on an unsafely filtered row.

### 3.3. Direct ALTER COLUMN TYPE

When the table is small, downtime/locks are acceptable, and conversion has been thoroughly tested, you can use:

~~~sql
ALTER TABLE public.orders
ALTER COLUMN external_id TYPE bigint
USING external_id::bigint;
~~~

`USING` defines the expression converting each value. PostgreSQL may cast automatically when an assignment/implicit cast exists, but an explicit expression clarifies intent and handles custom conversions.

### 3.4. Conversions Can Fail

If any value fails to cast, the statement fails and the transaction rolls back. Inspect and clean data before the migration; if special values require mapping, express the mapping explicitly in the expression or a staging migration.

~~~sql
ALTER TABLE public.customer_codes
ALTER COLUMN code TYPE bigint
USING CASE
    WHEN code ~ '^[0-9]+$' THEN code::bigint
    ELSE NULL
END;
~~~

This example is only suitable when the business accepts mapping invalid values to NULL and the column allows NULL. Never silently turn invalid data into NULL if that loses information.

### 3.5. Default Expressions

An old default may not convert automatically to the new type. You may need to drop the default first, change the type, and then set a new default:

~~~sql
ALTER TABLE public.orders
ALTER COLUMN external_id DROP DEFAULT;

ALTER TABLE public.orders
ALTER COLUMN external_id TYPE bigint
USING external_id::bigint;

ALTER TABLE public.orders
ALTER COLUMN external_id SET DEFAULT 0;
~~~

Execute within a single transaction when appropriate and when locks/rewrites fit within budget. Do not use an example default like `0` if it has no business meaning.

### 3.6. Nullability and Constraints

If conversion produces NULL, a NOT NULL column will fail the migration. Define null handling beforehand. For large tables, you can add a `NOT VALID` check constraint, backfill/clean data, validate the constraint, and then set NOT NULL according to the appropriate workflow and version.

### 3.7. Numeric Precision and Scale

Converting `numeric(p,s)` to a lower scale can round values; converting to integer may require explicit rounding or truncation. Check maximums, minimums, decimal places, and business rounding rules.

### 3.8. Timestamp Semantics

`timestamp without time zone` is just a wall-clock timestamp; `timestamptz` stores an instant and displays it according to session timezone. Converting between them requires defining the source timezone. Never blind-cast if historical values were recorded across multiple timezones or an unknown timezone.

### 3.9. Text, Varchar, and Collation

Increasing a varchar length limit differs fundamentally from changing collation or encoding semantics. Collation changes can affect sort/equality behavior and indexes; inspect collation versions and plan index rebuilds per documentation.

### 3.10. JSON and JSONB

`json` preserves the input text representation; `jsonb` parses and stores a normalized binary format, supporting different indexing and operators. Converting to jsonb can fail on invalid JSON, consume CPU, and require redesigned indexes. Verify duplicate keys, numeric precision, and application assumptions.

### 3.11. Enums and Domains

Adding enum values has transaction and version-dependent restrictions in PostgreSQL. Changing an enum to text or a domain requires reviewing constraints, defaults, and application serialization. Avoid enums if value lifecycles change frequently and migration coordination is difficult.

### 3.12. Dependency Inventory

Before running DDL, check indexes, constraints, views, functions, triggers, foreign keys, and partition dependencies. Use catalog queries, schema migration tooling, and source-code search. Do not rely on a single catalog query to find all dynamic dependencies.

## 4. Deciding Between Direct Conversion and Staged Migration

### 4.1. When Direct ALTER Is Appropriate

Direct conversion may be appropriate when:

- The table is small or the maintenance window is long enough;
- Lock impact is acceptable;
- The conversion is simple, deterministic, and lossless;
- Sufficient disk/WAL headroom exists;
- Replicas and archives can keep up;
- Applications can be stopped or deployed synchronously;
- Restore/rollback plans have been tested.

### 4.2. When Staged Migration Is Necessary

Use expand–migrate–contract when:

- The table is large;
- High uptime is required and long locks cannot be tolerated;
- Applications use rolling deployments across multiple versions;
- The new type requires mapping or backfilling;
- Historical data is inconsistent;
- Multiple services or consumers read or write the same column;
- Verification is needed before shifting traffic.

### 4.3. Expand–Migrate–Contract

Deployment flow:

1. Expand: add new columns, constraints, or indexes in a backward-compatible way;
2. Deploy bridge app: support both old and new schemas;
3. Migrate: backfill in batches and synchronize new writes;
4. Validate: verify parity, completeness, and constraints;
5. Cutover: switch reads/writes to the new column;
6. Observe: maintain a rollback window and monitor;
7. Contract: remove the old column once all consumers have migrated.

### 4.4. Expand Phase

Add new structures compatibly with existing code. Typically add a nullable shadow column, new indexes, or unvalidated constraints. Do not drop or rename the old column during this phase.

### 4.5. Migrate Phase

Deploy application code capable of reading/writing the new schema according to policy. Backfill historical data in batches; synchronize incoming writes occurring during backfill. Monitor progress and verify.

### 4.6. Cutover Phase

Switch reads to the new column first, then switch writes in a controlled step. Use feature flags or canaries to limit blast radius. Monitor errors, latency, and data parity.

### 4.7. Contract Phase

After all application versions, jobs, reports, CDC consumers, and integrations no longer use the old column, drop the legacy column, indexes, and constraints. Contraction is hard to roll back; execute only after an adequate observation period.

### 4.8. Compatibility Matrix

| Application version | Old schema | Expanded schema | Post-contract schema |
| --- | --- | --- | --- |
| Old app | Supported | Must keep working | No longer deployed |
| Bridge app | Not necessarily | Compatible reads/writes | Must be upgraded before contract |
| New app | Not necessarily | Reads/writes new column, fallback per policy | Supported |

Build this table before rollout to determine deployment order and when old structures can safely be removed.

### 4.9. Rollback and Roll-Forward

Before cutover, you can roll back the new app/schema if the old column remains authoritative and synchronized. After cutover, if writes only target the new column, rolling back to the old app may be unsafe. Maintain dual-write or reverse synchronization during the rollback window, or choose a roll-forward fix instead of reverting data.

## 5. Shadow Columns and Dual Writes

### 5.1. What Is a Shadow Column?

A shadow column is a new column added alongside the old column to hold the same data in the new type or representation. For instance, if `customer_code` is currently text and the system wants to move to bigint:

~~~sql
ALTER TABLE public.customers
ADD COLUMN customer_code_v2 bigint;
~~~

Adding a nullable column without a default is usually a fast metadata change, yet still requires a brief lock to update the catalog. The lock may still wait on other transactions; use `lock_timeout` and controlled retries.

### 5.2. Naming and Lifecycle Management

Column names should reflect purpose; do not let a `_v2` suffix live permanently. Track migration state in code, config, or a migration tracking table; document which column is authoritative in each phase.

### 5.3. Choosing the Source of Truth

Before backfilling, define which column is authoritative:

- Phase A: old column is source of truth; new column is synced from old;
- Phase B: both are written in the same transaction; reads still use the old column;
- Phase C: cutover reads to the new column; keep the old column synced during the rollback window;
- Phase D: new column is source of truth; stop writing to the old column;
- Phase E: contract and drop the old column.

Never allow the application, triggers, and backfill jobs to assume different sources of truth.

### 5.4. Application-Level Dual Writes

The bridge application can write both columns in the same transaction:

~~~sql
INSERT INTO public.customers (customer_code, customer_code_v2)
VALUES ('12345', 12345);

UPDATE public.customers
SET customer_code = '67890',
    customer_code_v2 = 67890
WHERE id = 42;
~~~

If conversion can fail, the application must validate beforehand and handle errors per business rules. Two writes inside the same database transaction ensure atomicity; writing to two separate systems or databases requires an outbox, CDC, or dedicated coordination.

### 5.5. Dual Writes Can Introduce Divergence

If the app runs two separate statements and the first succeeds while the second fails, the columns can diverge unless wrapped in the same transaction. If retries are not idempotent, stale values can overwrite newer data.

Prefer a single statement/transaction containing both values, or use a synchronization trigger. Emit mismatch metrics and alert whenever divergence appears.

### 5.6. Triggers as a Compatibility Bridge

A trigger can synchronize writes from older app versions that only know about the old column. For example, during the phase where the old column is authoritative:

~~~sql
CREATE OR REPLACE FUNCTION public.sync_customer_code_v2()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.customer_code IS NOT NULL THEN
            NEW.customer_code_v2 := NEW.customer_code::bigint;
        END IF;
    ELSIF NEW.customer_code IS DISTINCT FROM OLD.customer_code THEN
        NEW.customer_code_v2 := NEW.customer_code::bigint;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER customers_sync_code_v2
BEFORE INSERT OR UPDATE OF customer_code
ON public.customers
FOR EACH ROW
EXECUTE FUNCTION public.sync_customer_code_v2();
~~~

This trigger demonstrates the old-to-new direction. Adjust INSERT behavior if the application may submit only the new column, and validate invalid input before casting. Avoid ambiguous bidirectional triggers when both columns might change in the same statement.

### 5.7. Triggers and Dual Writes Coexisting

If the bridge app writes both columns while the trigger still treats the old column as authoritative, the trigger may overwrite `v2` from converting the old column. This is safe only if the conversion is deterministic and both values are guaranteed equal. Define explicit conflict rules, check parity, and test the trigger alongside every app version.

### 5.8. Reversing Sync Direction After Cutover

During the rollback window, you can flip the trigger so the new column becomes authoritative and updates the old column from the new column. Deploy trigger changes in a controlled rollout; verify old apps are drained or the old column remains accurately updated before allowing rollback.

### 5.9. Avoiding Trigger Recursion and Hidden Side Effects

Triggers execute within the write transaction and can increase latency and WAL. Prevent triggers from re-invoking themselves, performing redundant writes, or triggering recursion through other triggers. Check ordering, `WHEN` clauses, and behavior during bulk loads and replication.

### 5.10. Logical Replication and CDC

Shadow columns and triggers can interact with publication column lists, replica identity, subscriber schemas, and CDC consumers. Verify schema compatibility on both ends; logical replication does not automatically transform types to match your desired mapping.

## 6. Batched Data Backfills

### 6.1. What Is a Backfill?

A backfill populates the new column from existing data or another source after the schema has been expanded. For large tables, split it into small transactions to minimize lock duration, WAL bursts, rollback cost, and replication lag.

### 6.2. Prerequisites

Before running:

- A stable primary key or deterministic row identifier;
- A clear source of truth and conversion expression;
- New writes already synchronized;
- Supporting indexes to locate unbackfilled rows if needed;
- Batch size and rate limits;
- Metrics and stop conditions;
- A crash-resume mechanism.

### 6.3. Idempotent Backfills

Filtering with `WHERE new_column IS NULL` ensures each batch only processes rows still lacking the new value. If the job restarts after a failure, completed rows are skipped.

### 6.4. Batching by Primary Key

Example using primary key `id`:

~~~sql
WITH batch AS (
    SELECT id
    FROM public.customers
    WHERE customer_code_v2 IS NULL
      AND customer_code IS NOT NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE public.customers AS c
SET customer_code_v2 = c.customer_code::bigint
FROM batch
WHERE c.id = batch.id
  AND c.customer_code_v2 IS NULL
RETURNING c.id;
~~~

Each execution is one batch; commit the transaction before running the next batch. `SKIP LOCKED` lets multiple workers avoid waiting on the same rows, though it can skip locked rows; run subsequent passes to process any remaining rows.

### 6.5. Why Avoid OFFSET?

Large `OFFSET` values force PostgreSQL to walk past many rows before reaching the next batch, causing cost to grow steadily. Use keyset pagination (`id > last_id`) or `WHERE new_column IS NULL` backed by an appropriate index.

### 6.6. Keyset Pagination

A single worker can maintain a logical cursor:

~~~sql
WITH batch AS (
    SELECT id
    FROM public.customers
    WHERE id > :last_id
      AND customer_code_v2 IS NULL
    ORDER BY id
    LIMIT 1000
)
UPDATE public.customers AS c
SET customer_code_v2 = c.customer_code::bigint
FROM batch
WHERE c.id = batch.id
  AND c.customer_code_v2 IS NULL
RETURNING c.id;
~~~

`:last_id` is a client/job-runner placeholder, not native SQL server bind variable syntax. Advance the cursor only after the batch commits successfully. If rows are skipped due to concurrent changes, run a final reconciliation pass.

### 6.7. Batching by ctid

When no primary key exists, you can use `ctid` within a single short statement:

~~~sql
WITH batch AS (
    SELECT ctid
    FROM public.legacy_records
    WHERE new_value IS NULL
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE public.legacy_records AS t
SET new_value = convert_value(t.old_value)
FROM batch
WHERE t.ctid = batch.ctid;
~~~

`ctid` is only stable for the current row version; UPDATEs, VACUUM FULL, or rewrites can change it. Never persist `ctid` as a long-term checkpoint. For large tables, establish a stable key for reliable resume and parallelization.

### 6.8. Choosing Batch Size

Small batches reduce transaction duration and WAL bursts, but increase round trips and overhead. Large batches increase throughput, yet can trigger lock contention, replica lag, autovacuum pressure, and long rollbacks. Start small, measure latency/lag, and tune gradually.

### 6.9. Pausing Between Batches

The job runner can pause briefly between batches or rate-limit by rows/second or WAL bytes. Use adaptive throttling: slow down when replication lag, disk latency, or application p95 exceeds thresholds; ramp back up when the system stabilizes.

### 6.10. Do Not Hold One Transaction Across the Entire Backfill

Commit every batch independently. A long-running transaction holds snapshots open, prevents vacuum from reclaiming dead tuples, holds locks, and increases rollback cost. Never open one transaction and update millions of rows across loops.

### 6.11. Concurrent Writes During Backfill

If the application continues updating the source column, triggers or dual-write must ensure the shadow column receives new values. The backfill must only fill missing rows and never overwrite newer values with stale values read from an older snapshot.

### 6.12. Race Conditions

Row locking inside the batch combined with `new_column IS NULL` reduces overwrite races. Still, source-of-truth logic and triggers must be sound. Test concurrent updates/deletes, deadlock retries, and multiple concurrent backfill workers.

### 6.13. Unconvertible Rows

Isolate failing rows into an exception set or report. Do not retry the same failing batch indefinitely. Log the primary key, reason code, and remediation; fix data with business approval before rerunning.

### 6.14. Progress Tracking

Log per batch:

- Run ID and worker ID;
- First and last keys;
- Rows scanned/updated/skipped/failed;
- Duration;
- WAL and replication lag;
- Current throughput;
- Timestamp and error details.

Counting remaining rows across the full table can be expensive; do not run full-table `count(*)` every few seconds. Sample less frequently or track progress via partition/key ranges and checkpoints.

### 6.15. Parallel Workers

You can run multiple workers with `FOR UPDATE SKIP LOCKED`, but bound total concurrency. Adding workers does not guarantee linear throughput gains; it can induce random I/O, lock waits, WAL saturation, and contention.

### 6.16. Partition-by-Partition Backfill

For partitioned tables, process leaf partitions one by one in priority order. This limits blast radius, isolates per-partition timing, and lets you pause between partitions. Verify parent/child schema consistency and partition attach behavior.

## 7. Controlling Locks and Production Impact

### 7.1. Understand Locks Before Running DDL

PostgreSQL holds table locks until the end of the transaction. A DDL command may wait on existing locks; once queued, new statements can also be delayed by the lock queue. Even a fast DDL can cause queueing if it waits long to acquire its lock.

### 7.2. Preflight Lock Inspection

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS xact_age,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 250) AS query
FROM pg_locks AS l
JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE l.relation = 'public.customers'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
~~~

This query focuses on a specific relation; locks can also involve transaction IDs, virtual transactions, databases, or other objects. Use `pg_blocking_pids()` to find direct blockers.

### 7.3. lock_timeout

Set `lock_timeout` so DDL fails fast if it cannot acquire the lock within budget:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE public.customers
ADD COLUMN customer_code_v2 bigint;
COMMIT;
~~~

On timeout, the transaction errors out and must be rolled back/closed before retrying. Retry with backoff during a maintenance window rather than looping continuously and building a lock queue.

### 7.4. statement_timeout

`statement_timeout` limits total statement execution time, unlike `lock_timeout` (which only limits lock wait time). Choose timeouts based on expected duration, table size, and rollback cost. Canceling a large rewrite mid-flight can take time to roll back and generate extra load.

### 7.5. DDL Lock Queues

If DDL is waiting on a lock, identify the lock-holding transaction, its age, application owner, and query. An `idle in transaction` session can hold locks even without an active query. Never terminate a blocker automatically without understanding the business impact.

### 7.6. Lock Timeout Does Not Eliminate All Impact

Once the lock is acquired, the operation can still create I/O, WAL, and cache pressure. `lock_timeout` only bounds the lock wait step; it does not limit rewrite duration or resource consumption.

### 7.7. Prefer Metadata-Only DDL

Prefer fast changes like adding a nullable column without a default when possible. Even so, metadata changes still require brief catalog/relation locks and can wait behind long transactions. Use a short lock timeout to avoid unbounded waits.

### 7.8. Defaults When Adding Columns

Modern PostgreSQL versions can add a column with a constant immutable default without rewriting every row in many cases (since PostgreSQL 11). However, volatile defaults or special cases can require rewrites. Check your version and test; never assume this applies to every default.

### 7.9. Direct Type Changes

Before a direct type change, test on staging using a copy with comparable data volume, indexes, constraints, and workload. Measure lock duration, rewrite duration, WAL generated, peak disk, and replica catch-up time.

### 7.10. Avoid Multiple Concurrent DDLs

DDLs on the same relation conflict on locks; DDLs on different relations still compete for catalog locks, I/O, and WAL. Serialize high-impact schema migrations and designate a migration coordinator.

## 8. Constraints and Indexes in Staged Migrations

### 8.1. Add CHECK NOT VALID

You can add a check constraint without scanning/validating all existing data upfront:

~~~sql
ALTER TABLE public.customers
ADD CONSTRAINT customers_code_v2_not_null
CHECK (customer_code_v2 IS NOT NULL) NOT VALID;
~~~

The constraint is enforced on newly inserted or updated rows after creation, while existing data remains unverified. Backfill existing rows, then validate.

### 8.2. Validate Constraint

~~~sql
ALTER TABLE public.customers
VALIDATE CONSTRAINT customers_code_v2_not_null;
~~~

Validation scans existing data using a weaker lock than stronger DDL operations; it still consumes I/O and requires workload monitoring. If validation fails, locate and fix violating rows before retrying.

### 8.3. Setting NOT NULL

Once data is complete and the check constraint is validated, you can set `NOT NULL`:

~~~sql
ALTER TABLE public.customers
ALTER COLUMN customer_code_v2 SET NOT NULL;
~~~

PostgreSQL can use the validated check constraint to skip re-scanning in supported versions and conditions, though the command still requires a brief strong lock to update the catalog. Verify version behavior and set a lock timeout.

### 8.4. Foreign Key NOT VALID

~~~sql
ALTER TABLE public.order_items
ADD CONSTRAINT order_items_customer_v2_fk
FOREIGN KEY (customer_id_v2)
REFERENCES public.customers(customer_code_v2)
NOT VALID;

ALTER TABLE public.order_items
VALIDATE CONSTRAINT order_items_customer_v2_fk;
~~~

The referenced key must have an appropriate unique or primary key. Use this pattern to separate adding the constraint from the validation scan while monitoring locks and I/O.

### 8.5. Concurrent Unique Index

Create a unique index on the shadow column:

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY customers_code_v2_uidx
ON public.customers (customer_code_v2);
~~~

A concurrent unique index build still checks uniqueness during the build and can fail if duplicates exist. Resolve duplicates first and verify index validity afterward.

### 8.6. Attaching a Unique Constraint

Once the unique index is valid and meets requirements, attach it as a constraint:

~~~sql
ALTER TABLE public.customers
ADD CONSTRAINT customers_code_v2_key
UNIQUE USING INDEX customers_code_v2_uidx;
~~~

Attaching requires a lock; set `lock_timeout`, run within a window, and verify naming, ownership, and index compatibility.

### 8.7. Index for Backfilling

If the backfill selects rows by `id` range, the primary key already has an index. If selecting `WHERE new_column IS NULL`, a partial index can help:

~~~sql
CREATE INDEX CONCURRENTLY customers_v2_missing_idx
ON public.customers (id)
WHERE customer_code_v2 IS NULL;
~~~

A partial index adds write and space overhead during the migration. After backfilling, drop this index concurrently if it is no longer needed.

### 8.8. Foreign Keys and Type Compatibility

When changing the type of a referenced key, update both parent and child columns in a compatible sequence. PostgreSQL requires matching types/operators for foreign keys; never cut over one side while the other side remains incompatible.

### 8.9. Partitioned Indexes

For partitioned tables, index creation and attachment have version-specific restrictions and procedures. You can build indexes concurrently on each partition and attach them to a partitioned index per PostgreSQL guidelines. Verify all partitions have their corresponding indexes before cutover.

## 9. Validation and Data Parity

### 9.1. Checking Missing Rows

~~~sql
SELECT count(*) AS missing_rows
FROM public.customers
WHERE customer_code IS NOT NULL
  AND customer_code_v2 IS NULL;
~~~

A full-table count query can be expensive. Run in an appropriate window, or use partition/range summaries and checkpoints for frequent monitoring.

### 9.2. Checking Mismatches

~~~sql
SELECT
    count(*) AS compared_rows,
    count(*) FILTER (
        WHERE customer_code_v2 IS DISTINCT FROM customer_code::bigint
    ) AS mismatch_rows
FROM public.customers
WHERE customer_code IS NOT NULL;
~~~

Run this only when all source values are castable. For complex mappings, use the exact same deterministic conversion function for both backfill and validation to avoid diverging definitions.

### 9.3. Null Parity

~~~sql
SELECT
    count(*) FILTER (
        WHERE customer_code IS NULL AND customer_code_v2 IS NOT NULL
    ) AS unexpected_new_values,
    count(*) FILTER (
        WHERE customer_code IS NOT NULL AND customer_code_v2 IS NULL
    ) AS missing_new_values
FROM public.customers;
~~~

Null semantics must align with the business contract. Sometimes the new column allows null even if the old one did not, or vice versa; document the rule explicitly.

### 9.4. Range and Domain Validation

Check min/max, invalid values, duplicates, allowed ranges, and conversion loss. For decimals, timezones, and JSON, validate semantic equivalence rather than raw text representation.

### 9.5. Sample Validation

Sample across key ranges, recent rows, and hot partitions to verify conversion. Sampling catches bugs early, but does not replace full validation before contraction.

### 9.6. Constraint Validation

Verify constraints are validated, indexes are `indisvalid`/`indisready`, and foreign key/unique semantics hold. Log validation outcomes alongside the migration run ID.

### 9.7. Application Validation

Run smoke and integration tests on bridge/new versions:

- New inserts;
- Updates to source column;
- Updates to target column;
- Null values;
- Boundary values;
- Timeout retries;
- Concurrent updates;
- Read paths and serialization;
- Reports, ETL, and CDC consumers.

### 9.8. Query Plan Validation

After creating new indexes or changing types, compare `EXPLAIN (ANALYZE, BUFFERS)` on representative queries in staging or canary. Type/operator changes can alter planner choices; do not merely check that an index exists.

### 9.9. Count Parity Is Not Enough

Two columns can have identical non-NULL row counts while holding different values. Combine mismatch counts, ranges, checksums/hashes by key range, constraints, and business invariants.

### 9.10. Validation Snapshots

Run validation inside an appropriate transaction/snapshot to avoid counting shifting state across multiple queries. On actively written tables, maintain parity with triggers or dual writes, then re-run validation until mismatches reach zero or fall within policy.

## 10. Cutover and Contraction

### 10.1. Read Cutover

Switch reads to the new column first, optionally via feature flags or canaries. Keep writes synchronized and compare outputs between old and new paths during an observation period.

### 10.2. Write Cutover

Once the read path is stable, promote the new column as the source of truth. Verify all writers have deployed the bridge/new version: APIs, batch jobs, admin scripts, ETL, triggers, and integrations.

### 10.3. Shadow Reads

You can perform shadow reads: query both old and new logic, compare results, and return responses solely from the authoritative path. Ensure shadow queries do not push load over budget.

### 10.4. Canary Rollout

Shift a small fraction of traffic or a subset of tenants first. Monitor mismatches, errors, latency, lock waits, replica lag, and support tickets. Increase traffic only when acceptance criteria are met.

### 10.5. Rollback Window

During this window:

- Keep the old column;
- Maintain reverse sync if older app rollback is required;
- Record parity metrics;
- Keep old indexes and constraints;
- Verify restore points/backups;
- Document the exit criteria for the rollback window.

### 10.6. Contract Checklist

Before dropping the old column:

- No app versions read or write the old column;
- No jobs, reports, or CDC consumers depend on it;
- Read/write metrics show zero usage for an adequate duration;
- Data parity/validation is complete;
- Backup/restore paths are verified;
- Owner/business sign-off obtained;
- Drop operation has a lock timeout and rollback/recovery plan.

### 10.7. Dropping the Old Column

~~~sql
ALTER TABLE public.customers
DROP COLUMN customer_code;
~~~

Dropping a column usually updates metadata without immediately reclaiming all file space; reclaiming physical space may require separate rewrite/maintenance. It still requires a brief strong lock and can wait on transactions. Execute it in a dedicated contract migration once all dependencies are gone.

### 10.8. Renaming Is Not a Safe Standalone Cutover Step

Renaming old/new columns can break running code immediately. In rolling deployments, column names are the database's API contract. Only rename once all consumers are compatible and deployment order is controlled.

## 11. Monitoring Migration Impact

### 11.1. Pre-Migration Baseline

Record at minimum:

- Query latency p50/p95/p99 and error rates;
- Transaction throughput and connection count;
- CPU, memory, and disk IOPS/latency/throughput;
- Table/index sizes and free disk;
- WAL generation rate;
- Replication send/write/flush/replay lag;
- Archive success/failure and retained WAL;
- Long-running transactions and lock waits;
- Backup age and restore readiness.

Without a baseline, it is hard to separate migration impact from normal workload fluctuations.

### 11.2. Monitoring Lock Waits

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE array_length(pg_blocking_pids(pid), 1) > 0
ORDER BY query_start;
~~~

### 11.3. Monitoring Replication Lag

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Combine lag time with LSN distance, WAL generation, and workload. Lag columns may be NULL or imprecise when no new WAL arrives; never treat a single column as an absolute RPO guarantee.

### 11.4. Monitoring WAL Archiving

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

Large migrations can trigger WAL bursts. If archive failures rise or disk headroom drops quickly, throttle the backfill rate or pause the job.

### 11.5. Monitoring Replication Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
~~~

`wal_status`/`safe_wal_size` depend on major version. Check available columns before running on older servers. Never drop a slot to free disk without understanding the consumer and the consequence of having to reinitialize standbys or CDC.

### 11.6. Monitoring Backfill Throughput

Measure rows updated per batch, bytes/WAL over time, and batch duration. If throughput degrades over time, check index scan costs, dead tuples, I/O, lock waits, and autovacuum.

### 11.7. Monitoring Disk

Rewrites/backfills can increase table, index, WAL, and temp usage. Pull filesystem free space from OS/cloud monitoring; PostgreSQL relation size functions cannot replace volume metrics.

### 11.8. Monitoring Autovacuum

Backfill UPDATEs create dead tuples. Monitor `pg_stat_progress_vacuum`, `pg_stat_user_tables.n_dead_tup`, autovacuum logs, and transaction age. Do not disable autovacuum during a migration without a clear control plan.

### 11.9. Monitoring Query Plans

Backfills can compete with application queries; new indexes or type changes can alter query plans. Compare representative `EXPLAIN (ANALYZE, BUFFERS)` and query latency before and after in staging/canary.

### 11.10. Stop Conditions

Predefine pause/abort criteria:

- Application p95/p99 exceeds error budget;
- Lock waits impact critical transactions;
- Replication lag exceeds RPO budget;
- WAL archive backlog grows continuously;
- Free disk falls below reserve;
- Sustained CPU/I/O saturation;
- Mismatches or conversion errors exceed policy;
- Backfill stalls or causes repeated deadlocks.

### 11.11. Adaptive Throttling

A backfill does not need to run at maximum speed. Adjust batch size, sleep intervals, and worker count based on metrics. For example, if lag climbs, lower batch frequency; if latency is stable and lag is low, scale up gently within tested bounds.

## 12. Migration State and Automation

### 12.1. Persisting Migration State

A coordination table can record:

~~~sql
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.schema_migration_progress (
    migration_key text PRIMARY KEY,
    phase text NOT NULL,
    last_processed_id bigint,
    rows_processed bigint NOT NULL DEFAULT 0,
    rows_failed bigint NOT NULL DEFAULT 0,
    started_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

Save a checkpoint after every committed batch. With multiple workers, use separate job/range tables or atomic claims to prevent workers from overwriting a shared checkpoint.

### 12.2. Job Runner Pseudocode

~~~text
while migration is not paused:
    check stop conditions
    begin a short transaction
    claim one key range or batch
    update only rows that still need backfill
    record rows updated
    commit
    persist checkpoint
    sample replication lag, latency and disk headroom
    adjust batch size or sleep
    if no rows were found:
        run a reconciliation pass
        stop only when validation says complete
~~~

This illustrates coordination logic, not a complete script. Handle transaction errors, deadlock retries, process restarts, checkpoint consistency, and secrets in real implementations.

### 12.3. Atomic Checkpoints

If checkpoints live in the same database, update the progress row in the same transaction as the batch update to avoid marking progress before data commits. If checkpoints live in an external queue/store, design for at-least-once execution and keep batches idempotent.

### 12.4. Advisory Locks for a Migration

A session-level advisory lock can prevent two orchestrators from running the same migration simultaneously:

~~~sql
SELECT pg_try_advisory_lock(573001::bigint);
~~~

If the lock cannot be acquired, the runner should exit or wait per policy. Keep the same session connection for the duration of the job and release the lock when finished. Advisory locks do not stop another user from running DDL directly.

### 12.5. Retrying Deadlocks

Batch transactions can deadlock with application writes. Retry deadlocked transactions using exponential backoff/jitter, bounded attempts, and metrics. Keep batches short and enforce consistent row/key ordering to minimize deadlocks.

### 12.6. Resuming After a Crash

When the runner restarts:

1. Read the migration phase/checkpoint;
2. Identify the last committed batch;
3. Inspect schema/trigger/index state;
4. Re-run idempotent batches;
5. Reconcile any missing rows;
6. Continue validation.

Never assume a process exit means the database transaction rolled back if the client disconnected during COMMIT.

### 12.7. Dry Runs

A dry run should check counts, conversion failures, dependency inventory, estimated rows/bytes, lock requirements, and plans. It does not execute writes; do not treat a dry run as proof of exact runtime.

### 12.8. Canary Batches

Start with a small range or single partition, verify conversion, parity, latency, and WAL impact, and only then expand. Record canary metrics to size batches for the remainder.

## 13. Rollback, Recovery, and Failure Handling

### 13.1. Rollback Classification by Phase

| Phase | Rollback option | Risk |
| --- | --- | --- |
| Expand | Drop new structure if no consumers exist | DDL locks and dependencies |
| Bridge deploy | Roll back application while schema stays compatible | App rollback may reintroduce dual-write behavior |
| Backfill | Pause/resume; keep shadow data or delete deliberately | Avoid reversing batch-by-batch unnecessarily |
| Validation | Fix data and re-run | Must preserve source of truth |
| Read cutover | Switch reads back to old column if parity/sync holds | Old column may become stale |
| Write cutover | Reverse sync or roll forward | New data may not reverse-convert losslessly |
| Contract | Restore from backup/PITR or rebuild column | Dropped columns are hard to roll back quickly |

### 13.2. Direct ALTER Rollback

PostgreSQL DDL is usually transactional: if `ALTER COLUMN TYPE` fails inside a transaction, uncommitted changes roll back. However, once committed, reversing it is a new migration that may rewrite the table again; it is not a free undo.

### 13.3. Backfill Rollback

With a shadow column, you can retain the new data and pause the migration. Only drop the shadow column if needed after investigation or retry. If the conversion discarded data, lost precision or context cannot be recovered simply by casting back.

### 13.4. Dual-Write Mismatches

If mismatches occur:

1. Pause cutover/backfill;
2. Identify the authoritative column;
3. Categorize divergent rows and root causes;
4. Inspect triggers, app versions, and retry races;
5. Fix synchronization logic;
6. Reconcile data;
7. Re-run validation before proceeding.

Never blindly copy one column over the other across all rows without verifying which side holds the true value.

### 13.5. Backfill Causing Replication Lag

Lower worker count/batch size or pause. Address bottlenecks on the standby, network, storage, or archive, wait for lag to drop, and resume. If a slot retaining WAL threatens disk exhaustion, prioritize protecting primary disk while preserving WAL needed for recovery.

### 13.6. Disk Pressure

Pause write-heavy migrations before volumes run out of space. Identify whether growth is in heap, indexes, WAL, temp, or backups. Expand volumes or shift maintenance plans; never delete files inside the data directory or `pg_wal` via filesystem commands.

### 13.7. Lock Queues and Outages

If a DDL waiter causes a queue:

- Identify the DDL PID and blockers;
- Cancel the DDL waiter if needed to clear the queue;
- Handle the lock-holding transaction per incident policy;
- Confirm application requests recover;
- Reschedule with a short lock timeout and preflight checks.

### 13.8. Conversion Errors

Log the primary key and invalid value in an access-controlled error report. Fix the source per business rules or create an approved mapping table. Reprocess failed rows and verify no data was lost or corrupted.

### 13.9. Application Incompatibility

If the new app version fails, toggle the feature flag back to the old path while sync remains active. If the schema has already contracted, you may need a roll-forward fix or restore; never assume deploying the old app will work against the contracted schema.

### 13.10. When to Choose Roll-Forward

Once the new column is authoritative and reverse mapping is lossy, a roll-forward fix is usually safer than rolling back data. Keep the old column until business sign-off and the rollback window ends.

## 14. End-to-End Example: Text ID to Bigint

Scenario: the `customers` table has 80 million rows. The `customer_code` column is currently text holding numeric strings; the application wants bigint to avoid casts and standardize the API. The system must continue accepting writes throughout the migration.

### 14.1. Preflight

Count invalid values:

~~~sql
SELECT
    count(*) AS total_rows,
    count(*) FILTER (WHERE customer_code IS NULL) AS null_rows,
    count(*) FILTER (
        WHERE customer_code IS NOT NULL
          AND customer_code !~ '^[0-9]+$'
    ) AS invalid_rows
FROM public.customers;
~~~

Check range and confirm all values fit in bigint. Inspect dependencies, indexes, constraints, views, CDC, application versions, and query plans. Record disk, WAL, and replication baselines.

### 14.2. Expand Schema

~~~sql
SET lock_timeout = '2s';

ALTER TABLE public.customers
ADD COLUMN customer_code_v2 bigint;
~~~

This command needs a brief catalog/relation lock. If it fails to acquire the lock within budget, retry after identifying blockers.

### 14.3. Deploy Compatibility Bridge

Deploy an application version that reads the old column and writes both old and new values in the same transaction. Install an old-to-new trigger for legacy writers not yet upgraded. During this phase, the old column remains the source of truth.

### 14.4. Batched Backfill

Start with 1,000–5,000 rows per batch, tuning based on latency and lag:

~~~sql
WITH batch AS (
    SELECT id
    FROM public.customers
    WHERE customer_code_v2 IS NULL
      AND customer_code IS NOT NULL
    ORDER BY id
    LIMIT 2000
    FOR UPDATE SKIP LOCKED
)
UPDATE public.customers AS c
SET customer_code_v2 = c.customer_code::bigint
FROM batch
WHERE c.id = batch.id
  AND c.customer_code_v2 IS NULL;
~~~

Commit each batch. The job runner records checkpoints/updated row counts, sleeps between batches, and pauses on stop conditions. Run a reconciliation pass for any skipped rows.

### 14.5. Validate Completeness and Parity

~~~sql
SELECT count(*) AS missing_rows
FROM public.customers
WHERE customer_code IS NOT NULL
  AND customer_code_v2 IS NULL;

SELECT count(*) AS mismatches
FROM public.customers
WHERE customer_code IS NOT NULL
  AND customer_code_v2 IS DISTINCT FROM customer_code::bigint;
~~~

Also verify null semantics, min/max values, duplicates, and business constraints.

### 14.6. Create New Index/Constraint

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY customers_code_v2_uidx
ON public.customers (customer_code_v2);
~~~

If a unique constraint is needed, attach the valid index using `UNIQUE USING INDEX`. Monitor progress, locks, disk, and WAL. If the unique build fails due to duplicates, resolve duplicates per business rules first.

### 14.7. Cut Over Reads

Deploy code reading `customer_code_v2` for canary tenants or a small traffic slice. Shadow-compare old and new results while monitoring latency, errors, and data parity. Expand traffic as acceptance criteria are met.

### 14.8. Cut Over Writes

Promote bigint as the source of truth. During the rollback window, keep reverse sync to text if legacy apps must remain runnable. Confirm no old writers remain and all downstream consumers have transitioned.

### 14.9. Contract

Once old-column usage stays at zero through the observation period and business sign-off is obtained:

- Drop old triggers;
- Drop old indexes/constraints after verifying dependencies;
- Drop the legacy text column in a dedicated migration;
- Remove compatibility code;
- Update schema docs, ORMs, and CDC contracts.

### 14.10. Post-Check

Measure query plans, p95/p99, table/index sizes, WAL/archiving, replication lag, dead tuples, and backup duration. Log actual migration duration, rows/sec, error count, and lessons learned.

## 15. Example: Integer to Bigint

### 15.1. Direct Conversion

For small tables or within a maintenance window:

~~~sql
ALTER TABLE public.invoice_items
ALTER COLUMN legacy_id TYPE bigint
USING legacy_id::bigint;
~~~

Assess table rewrite, lock, and index impact per version. Do not assume this is metadata-only merely because all integer values fit within bigint's range.

### 15.2. Staged Conversion

For large tables, add `legacy_id_bigint`, synchronize writes, backfill by primary key, create indexes concurrently, validate constraints, cut over the application, and contract. This takes more time and storage, but avoids holding long locks.

### 15.3. Sequences and Identity

If the column is serial or identity, inspect the sequence type, ownership, default expression, current value, and application assumptions. Changing only the column type does not guarantee the sequence is properly adjusted for the new range.

## 16. Example: Text Timestamp to Timestamptz

### 16.1. Identify Source Timezone

If text strings include offsets, they can be parsed into instants. If text strings lack a timezone, you must know the business/source timezone before casting.

~~~sql
SELECT
    raw_timestamp,
    raw_timestamp::timestamptz
FROM public.event_import
WHERE raw_timestamp IS NOT NULL
LIMIT 20;
~~~

Display output depends on session timezone; keep in mind that instant semantics differ from local wall-clock time.

### 16.2. Shadow Column

~~~sql
ALTER TABLE public.event_import
ADD COLUMN occurred_at_v2 timestamptz;
~~~

Backfill using a verified conversion expression and isolate invalid strings into an error set. If inputs lack timezones, attach the explicit business timezone in the expression rather than relying implicitly on session settings.

### 16.3. Validation

Compare by instant/epoch and check boundary values around daylight-saving transitions if the source contains local times. Verify API serialization, reporting timezones, and partition bounds.

## 17. Example: JSON to JSONB

### 17.1. Check JSON Validity

If the column is already type `json`, values are valid per the JSON parser. If it is text, determine how to detect invalid input before converting. You can use a staging table or a controlled try-cast function; never cast unverified data directly.

### 17.2. Conversion

For small tables:

~~~sql
ALTER TABLE public.audit_events
ALTER COLUMN payload TYPE jsonb
USING payload::jsonb;
~~~

For large tables, use a jsonb shadow column and backfill in batches. After cutover, re-evaluate GIN/expression indexes and query operators.

### 17.3. Semantic Differences

`jsonb` normalizes representation and does not preserve whitespace or key order from the input text; duplicate object keys are not retained as independent entries. If consumers rely on byte-for-byte raw payloads, store raw text separately.

## 18. Type Changes in Partitioned Tables

### 18.1. Parent and Partitions

Schemas of a partitioned parent and its partitions must remain compatible. Some DDL on a parent can touch all partitions and hold locks across many relations. Check partition count, size skew, and maintenance duration before running.

### 18.2. Rolling Partition Migration

For time-series data, you can migrate partition by partition or in groups, provided parent schema compatibility is maintained. Attaching/detaching partitions and partition bounds may require matching constraints and indexes.

### 18.3. New Partitions Created During Backfill

Ensure partition-creation jobs create both old and new columns, triggers, constraints, and indexes matching the current phase. Otherwise, rows in newly created partitions may miss dual writes or backfilling.

### 18.4. Retention and Archival

Old partitions nearing retention expiration may not need backfilling if business and legal policies allow scheduled archival or dropping. Document scope explicitly so required data is not skipped.

## 19. Operational Runbook for a Major Schema Migration

### 19.1. Before Deployment

1. Author the migration design: source/target types, conversion rules, and source of truth.
2. Inventory dependencies: applications, jobs, views, functions, triggers, indexes, constraints, and CDC.
3. Audit data: invalid values, nulls, ranges, duplicates, and edge cases.
4. Test on staging with production-scale data volume.
5. Measure lock duration, rewrite/backfill throughput, WAL, peak disk, and replica catch-up.
6. Define the maintenance window, on-call, owner, and business approver.
7. Capture baselines and configure dashboards/alerts.
8. Define stop conditions, rollback/roll-forward plans, and recovery steps.

### 19.2. Expand

- Verify current schema and migration version;
- Set a short lock timeout;
- Add required shadow columns/constraints/indexes;
- Confirm catalogs and old apps still operate;
- Record the migration phase.

### 19.3. Deploy Bridge

- Roll out the bridge app via rolling deployment;
- Verify dual-write/trigger behavior;
- Test writes from APIs, batch jobs, admin tools, and integrations;
- Monitor parity mismatches and errors;
- Do not switch reads until backfilling is complete enough.

### 19.4. Backfill

- Start with a canary range or partition;
- Measure rows/sec, WAL rate, replication lag, and p95;
- Tune batch size and interval;
- Commit every batch;
- Persist atomic checkpoints;
- Pause if stop conditions trigger;
- Run a reconciliation pass.

### 19.5. Validate

- Missing rows equal zero or align with exception policy;
- Mismatches equal zero;
- Range/domain/null/unique/FK checks pass;
- Indexes are valid/ready;
- Application smoke tests and query plans pass;
- CDC/ETL/reporting consumers verified.

### 19.6. Cutover

- Switch canary reads;
- Run shadow comparisons;
- Expand traffic;
- Switch writes / source of truth;
- Keep reverse sync if rollback is needed;
- Monitor errors, latency, parity, and support incidents.

### 19.7. Contract

- Wait for the rollback window to close;
- Verify zero remaining legacy consumers;
- Obtain business sign-off;
- Drop old triggers/indexes/constraints/columns in small isolated steps;
- Monitor locks and query queues;
- Update code, docs, dashboards, and runbooks.

### 19.8. Post-Migration

Save a migration report including actual duration, rows converted, mismatch/error counts, WAL generated, peak disk, replica lag, before/after query latency, and follow-up actions. Never mark complete solely because the final DDL executed.

## 20. Hands-On Exercises: Data Type Changes and Backfilling

Perform exercises in a lab/staging environment. Do not run type rewrites, large backfills, locks, or destructive DDL in production just for practice. For version-dependent behavior, check the corresponding documentation.

### Exercise 1 — Evaluating a Type Change

A text column storing customer codes must be converted to bigint. List all information needed before writing the migration.

### Exercise 2 — Data Audit

Write a query counting NULLs, invalid numeric strings, and values exceeding the bigint range before casting.

### Exercise 3 — Direct ALTER

Write an ALTER COLUMN TYPE statement using USING to convert text to bigint. List reasons the statement could fail.

### Exercise 4 — Rewrite Risk

Explain the difference between a metadata-only change and a table rewrite. List the resources to measure before changing a column type on a large table.

### Exercise 5 — Locks

Explain why an ALTER TABLE requiring ACCESS EXCLUSIVE can cause an outage even while the DDL is still waiting for the lock.

### Exercise 6 — lock_timeout

Write a transaction adding a nullable column with SET LOCAL lock_timeout. Explain how to retry after a lock timeout.

### Exercise 7 — Default Expressions

An old default cannot cast to the new type. Write the sequence of DROP DEFAULT, ALTER TYPE, and SET DEFAULT.

### Exercise 8 — Numeric Precision

Convert numeric(18,4) to numeric(12,2). Describe how to detect values that overflow or lose precision and define a rounding rule.

### Exercise 9 — Timestamps

A text column holds local timestamps without offsets. Why must you know the source timezone before converting to timestamptz?

### Exercise 10 — JSONB

Compare json and jsonb regarding representation, duplicate keys, and indexing. When should raw text be preserved?

### Exercise 11 — Expand-Contract

Diagram the expand, bridge, backfill, validate, cutover, and contract phases for a large column.

### Exercise 12 — Compatibility Matrix

Build a compatibility table for old app, bridge app, and new app across three schema states.

### Exercise 13 — Shadow Column

Write an ALTER TABLE adding a shadow bigint column for an existing text column.

### Exercise 14 — Dual Write

Write an INSERT/UPDATE updating both old and new columns in the same transaction. Explain what can fail if split into two transactions.

### Exercise 15 — Trigger Bridge

Write an old-to-new trigger for INSERT and UPDATE. Explain source of truth and how invalid values should be handled.

### Exercise 16 — Backfill Batch

Write a CTE using primary key, LIMIT, and `FOR UPDATE SKIP LOCKED` to update 1,000 unbackfilled rows.

### Exercise 17 — Idempotency

Why does `WHERE new_column IS NULL` allow a backfill to resume safely? State its limitation if the source column changes concurrently.

### Exercise 18 — OFFSET vs. Keyset

Compare `OFFSET` pagination with keyset pagination when backfilling hundreds of millions of rows.

### Exercise 19 — ctid

Explain why `ctid` works for a single batch statement, yet should not be used as a long-term checkpoint.

### Exercise 20 — Batch Sizing

A 5,000-row batch takes 20 seconds and replica lag rises. Recommend adjustments to batch size, delay, and concurrency.

### Exercise 21 — Concurrent Updates

During backfill, the application updates the source column. Design a trigger/dual-write setup so the shadow column never goes stale.

### Exercise 22 — Validation

Write queries counting missing rows and mismatches between a text source and a bigint shadow column. Why is count parity insufficient?

### Exercise 23 — NOT VALID

Write ADD CHECK NOT VALID, VALIDATE CONSTRAINT, and SET NOT NULL for a shadow column. Explain lock and scan impacts.

### Exercise 24 — Unique Index

Write `CREATE UNIQUE INDEX CONCURRENTLY` on a shadow column and describe how to attach it as a unique constraint.

### Exercise 25 — Replication Monitoring

Write a query inspecting sent/write/flush/replay LSN and propose stop conditions when migration lag threatens the RPO budget.

### Exercise 26 — WAL Capacity

A backfill generates 200 GB of WAL while an offline standby holds a slot. Describe how to investigate and protect primary disk.

### Exercise 27 — Rollback

Analyze rollback feasibility across expand, backfill, read cutover, write cutover, and contract phases. Which phase is hardest to roll back?

### Exercise 28 — Partition Migration

Design a type-change plan for a partitioned table with 60 partitions. Explain how to handle new partitions created during migration.

### Exercise 29 — Application Cutover

Design a canary rollout and shadow reads for the new column. Define metrics and acceptance criteria before ramping traffic.

### Exercise 30 — Capstone: Zero-Downtime Migration

An `orders` table has 120 million rows. Its `customer_ref` column is varchar and must become bigint; the system sustains 8,000 writes/second, has 2 synchronous standbys, one async DR replica, a CDC consumer, and multiple application versions running rolling deploys. The RPO target for an AZ failure is 0 with a 5-minute RTO.

**Requirements:**

1. Assess conversion validity, ranges, nulls, duplicates, and dependencies.
2. Compare direct ALTER against expand–migrate–contract.
3. Design the shadow column, source-of-truth phases, and dual-write/trigger.
4. Write an idempotent batched backfill with checkpoint/resume.
5. Choose batch size/concurrency and adaptive throttling metrics.
6. Design constraints/indexes and pre-cutover validation.
7. Define lock timeout, statement timeout, stop conditions, and maintenance windows.
8. Monitor WAL, replication, CDC lag, disk, and application latency.
9. Write read/write cutover, rollback window, and contract checklists.
10. Design failure handling for invalid rows, deadlocks, disk pressure, and mismatches.
11. Create a test matrix covering old/bridge/new app versions.
12. Write a migration report and acceptance criteria for business sign-off.

**Success criteria:** the migration can pause/resume, never overwrites newer data with stale backfill values, stays within RPO/latency/disk budgets, validates parity, and provides rollback/roll-forward plans per phase.

## 21. Frequently Asked Questions

### 21.1. Can a type be changed directly on a large table?

Technically yes, but it usually requires a strong lock and may rewrite the entire table. Assess table size, dependencies, conversion, WAL, disk headroom, and downtime first. For high-uptime systems, staged migrations are usually easier to control.

### 21.2. Does ALTER COLUMN TYPE always rewrite the table?

No. Some conversions are binary-coercible or metadata-only depending on types and version; others require a rewrite. Verify the documentation and test on a production-equivalent copy.

### 21.3. Can ALTER TABLE cause an outage before the command even runs?

Yes. A DDL waiting on a strong lock can build a lock queue and block other queries. Use short lock timeouts, preflight checks, and backoff retries.

### 21.4. Is adding a nullable column safe?

Usually a fast metadata change if no default forces a rewrite, though it still needs a brief lock and can wait behind long transactions. Use a lock timeout and verify version behavior.

### 21.5. Should defaults be used when adding columns to large tables?

Modern PostgreSQL versions optimize certain constant immutable defaults, whereas volatile expressions or older versions can rewrite the table. Check your version and test beforehand.

### 21.6. Why is a shadow column needed?

It lets old and new columns coexist during rollout, allowing batched backfills and controlled traffic cutover. This avoids holding long rewrite locks on large tables.

### 21.7. Should dual writes live in the application or in a trigger?

Application dual writes are clean once all writers are upgraded; triggers maintain compatibility for legacy writers. Both can be combined during a phase, provided source-of-truth/conflict rules are defined and all write paths are tested.

### 21.8. Do dual writes guarantee the two columns match?

Only when writes happen in the same transaction or are atomically synchronized, the conversion is deterministic, and retries cannot overwrite newer data. Parity metrics and reconciliation are still required.

### 21.9. Should a backfill run in a single transaction?

Not for large tables. Split into batches and commit separately to bound locks, snapshots, WAL bursts, and rollback costs.

### 21.10. What is the right batch size?

There is no universal number. Start small, measure batch duration, throughput, latency, WAL, and replication lag, then tune against stop conditions.

### 21.11. Can FOR UPDATE SKIP LOCKED miss rows?

It can skip rows currently locked during that pass. Run a reconciliation pass and only declare completion once validation confirms zero rows remain unbackfilled.

### 21.12. Is OFFSET suitable for large backfills?

Usually not. Large OFFSETs force the database to traverse many rows before each batch. Use keyset pagination on a stable key or query missing rows directly.

### 21.13. Can ctid be used as a checkpoint?

It should not be. ctid can change whenever a row is updated or rewritten. Only use ctid within a single short batch statement; use a primary key or range for durable checkpoints.

### 21.14. Can a backfill overwrite concurrent updates?

It can if locking and source-of-truth checks are incorrect. Use row locking, update only missing rows, maintain dual-write/triggers, and test race conditions.

### 21.15. How do you know when a backfill is complete?

Do not rely solely on a cursor or processed row count. Run reconciliation, missing/mismatch checks, domain/range validation, and verify new writes stay synchronized.

### 21.16. Does NOT VALID mean the constraint is not enforced?

No. Existing data is unvalidated, yet the constraint is still enforced for new and modified rows per constraint semantics. Run VALIDATE CONSTRAINT to check existing data.

### 21.17. Does VALIDATE CONSTRAINT block writes?

It takes a weaker lock than strong DDL and allows many DML operations to continue, though it still scans data and uses I/O. Monitor workload and version-specific lock behavior.

### 21.18. Does CREATE INDEX CONCURRENTLY require extra disk?

Yes. The new index is built before replacing/attaching; space is needed for old/new indexes, WAL, and temporary work. Builds can also fail if duplicates appear.

### 21.19. Why inspect sequences when changing integer to bigint?

Serial/identity columns use separate sequences. Verify sequence type, ownership, defaults, and current value; changing column type alone does not guarantee sequence capacity matches.

### 21.20. Should you change the parent type first and partitions later?

Not arbitrarily. A partitioned parent and its partitions must stay compatible; parent DDL can touch many relations. Plan by version, partition count, and attach/detach requirements.

### 21.21. Does backfilling affect autovacuum?

Yes. UPDATEs create dead tuples and WAL; autovacuum may need to run more aggressively. Do not disable autovacuum by default; monitor dead tuples, freeze age, and worker capacity.

### 21.22. What if backfilling increases replication lag?

Pause or reduce batch size/concurrency, find the bottleneck (network, standby I/O, replay, archive), and resume once metrics stabilize. Never promote or drop a slot just to hide lag.

### 21.23. Can you roll back after cutover?

Only while the old column stays synced and reverse conversion is lossless. Once the new column is authoritative or conversion discarded information, rolling forward may be safer than rolling back.

### 21.24. When is it safe to drop the old column?

Once all app versions, jobs, reports, CDC consumers, and integrations have migrated; parity/validation passes; old-column usage has been zero long enough; the rollback window has closed; and the business owner signs off.

### 21.25. Do schema migrations need a dedicated backup?

Have an appropriate backup/PITR recovery point before major migrations, though backups do not replace validation or rollback plans. Verify WAL archiving and restore paths; an untested backup does not prove you can meet RTO.

## 22. Official PostgreSQL Documentation

Consult documentation matching your running major version, as lock behavior, DDL optimizations, catalog columns, and feature support can vary:

- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): changing types, adding/dropping columns, constraints, and locks.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock modes and conflict behavior.
- [Concurrency Control](https://www.postgresql.org/docs/current/mvcc.html): MVCC and transaction snapshots.
- [Data Type Conversion](https://www.postgresql.org/docs/current/typeconv.html): cast resolution and type conversion.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): concurrent index creation.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): rebuilding indexes.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): tracking index builds and VACUUM.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, UNIQUE, and foreign keys.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): autovacuum and cleanup after UPDATE/backfills.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): activity, locks, and replication statistics.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): WAL senders, slots, and replication settings.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): publications, subscriptions, and schema compatibility.
- [pg_cron](https://github.com/citusdata/pg_cron): scheduler extension; check compatible releases.
- [pg_repack](https://github.com/reorg/pg_repack): table/index reorganization tool; check version, requirements, and operational limits.

## 23. Summary

Safe data type changes are a problem of compatibility, data integrity, locking, resources, and rollout discipline. For small tables, direct `ALTER COLUMN TYPE` can fit if the conversion is verified and the lock window is acceptable. For large tables or rolling-deploy applications, expand–migrate–contract lets old and new schemas coexist across backfilling and cutover.

| Component | Role |
| --- | --- |
| Type assessment | Define semantics, range, precision, timezone, and conversion errors |
| Expand | Add compatible shadow column/index/constraint |
| Dual write/trigger | Synchronize writes during transition |
| Batched backfill | Populate data in short, resumable transactions |
| Validation | Prove completeness, parity, and constraints |
| Cutover | Shift reads/writes to the new type via canary |
| Rollback window | Preserve safe reversion or roll-forward capability |
| Contract | Remove legacy structures once zero consumers remain |
| Monitoring | Control locks, latency, WAL, replication, and disk |

Never run a massive rewrite simply because the DDL statement is short. Test on production-scale data, chunk backfills into idempotent batches, keep incoming writes synchronized, watch WAL/replication/disk, and validate data before cutover. Once contraction completes, rollbacks become dramatically harder.

**A good migration can pause, resume, validate, and account for the source of truth at every phase.** That enables evolving schemas while preserving data accuracy and limiting impact on live user traffic.
