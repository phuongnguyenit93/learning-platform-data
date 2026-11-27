# Performing Compatible Migrations While the Application Remains Live

Migrating a database while the application continues serving users is the process of evolving schemas and data while multiple application versions coexist. During a rolling deployment, some Pods still run the old version while others already run the new version; background workers, cron jobs, consumers, or other services may also continue accessing the database. Therefore, a schema change is safe only when every active application version can operate against the database state throughout the entire transition.

PostgreSQL supports transactional DDL for many operations, yet that does not mean every migration is non-disruptive. A statement may require heavy locks, queue behind long-running transactions, or trigger heavy I/O. Large backfills can contend for resources with production queries. Compatible migrations require coordinating schema changes, application releases, data migrations, verification, and legacy cleanup across multiple stages.

The standard deployment pattern is **expand and contract**: expand the schema so old and new versions operate side by side, migrate applications and data incrementally, and remove the old structure only after confirming zero dependencies remain.

## 1. Why Can a Direct Migration Cause Application Downtime?

Suppose an application currently reads and writes the column `customers.full_name`. A new release wants to rename the column to `display_name`.

If a migration executes:

~~~sql
ALTER TABLE customers RENAME COLUMN full_name TO display_name;
~~~

every application instance still querying `full_name` fails immediately after the rename. During a rolling deployment, older Pods are still running, so errors erupt mid-rollout. Rolling back the application binary will not fix it either if the schema only exposes the new column.

Changes that commonly trigger similar failures:

- Dropping or renaming a column, table, index, enum value, or function still used by older code.
- Changing a column data type such that existing queries or data become invalid.
- Adding a `NOT NULL` column without providing a value for existing rows or older application writers.
- Adding a constraint immediately while existing rows violate the condition.
- Building an index in a way that holds locks too long on a busy table.
- Migrating data inside one massive transaction, holding row locks too long or generating WAL faster than storage/replication can absorb.
- Deploying new application code before required schema changes are in place.

A safe migration must account for **the schema before and after migration**, **coexisting application versions**, **open transactions**, **background jobs**, and **rollback capability**.

## 2. Backward Compatibility and Forward Compatibility

These two concepts describe the two directions of compatibility:

- **Backward compatibility:** the new schema continues supporting the old application. For example, adding a new nullable column generally does not break older code as long as existing columns remain intact.
- **Forward compatibility:** the new application can run against an older schema during a rollout phase. This helps when application releases ship ahead of or alongside schema migrations, though it is not always strictly required.

During a rolling deployment, the top priority is ensuring every running application version stays compatible with the database schema at that moment.

| Application | Old Schema | Expanded Schema | Contracted Schema |
|---|---|---|---|
| Old version | Works | Must continue working | Typically incompatible |
| Transition (bridge) version | Only if designed to tolerate old schema | Works | May become incompatible |
| New version | Only if designed to tolerate old schema | Works | Works |

This table shows why contracting must be delayed. Once the old column is dropped, the old application can no longer run against that schema. If you need binary rollback capability, the schema must preserve the old structure throughout the entire rollback window.

## 3. The Expand and Contract Pattern

A change is split into two major phases:

**Expand:** add new structures without breaking existing code. This may involve adding nullable columns, new tables, new indexes, unvalidated constraints, or parallel APIs. The old application continues functioning undisturbed.

**Contract:** only after the new application relies on the new structure, all old instances are retired, data is verified, and the rollback window closes, stop writing to and then drop the old structure.

Overall flow:

~~~mermaid
flowchart TD
    A[Old schema + old application] --> B[Expand: add new structures]
    B --> C[Deploy bridge application]
    C --> D[Backfill and synchronize data]
    D --> E[Verify new data]
    E --> F[Switch application reads to new structure]
    F --> G[Retire dependencies on old structure]
    G --> H[Contract: drop old structure in a later release]
~~~

Every step must leave the system in an operable state. If deployment halts mid-way, the system must still serve traffic using the current schema and running application versions. Never bundle expand, backfill, read switch, and contract into a single migration.

### Practical Rules

- Add first, drop later.
- Read from the old structure first, then switch reads to the new structure.
- Start dual-writing or synchronization before backfilling.
- Backfill in small resumable batches.
- Verify data integrity before switching read paths.
- Maintain rollback capability for an agreed rollback window.
- Contract only when every application, worker, report, and operational script has stopped using the old structure.

## 4. End-to-End Example: Migrating `full_name` to `display_name`

Suppose the current table is:

~~~sql
CREATE TABLE customers (
    id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name   text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
~~~

The old application reads and writes `full_name`. The new requirement wants to use `display_name`. Because both represent the same semantic value, we can migrate across the following stages.

### Stage 1: Expand the Schema

Add the new column as nullable:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name text;
~~~

This is an additive change, so old code continues accessing `full_name`. Adding a column still acquires a metadata lock on the table; while normally instant, it can queue behind long-running transactions holding locks. Choose an appropriate maintenance window and set `lock_timeout` so the migration does not wait indefinitely.

~~~sql
SET lock_timeout = '2s';

ALTER TABLE customers
ADD COLUMN display_name text;

RESET lock_timeout;
~~~

The snippet above illustrates a single migration session. If the command fails due to timeout inside a transaction block, the transaction enters an aborted state and must roll back before running further statements. Your migration runner should manage error states explicitly.

### Stage 2: Keep New Writes Synchronized

During rolling deployment, older Pods only write `full_name`. If the backfill already processed a row and an old Pod subsequently updates that row, `display_name` would become stale. Every legacy write must update the new column during the transition.

You can use a temporary trigger to keep the new column synchronized with the old column:

~~~sql
CREATE FUNCTION sync_customer_display_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.display_name := NEW.full_name;
    RETURN NEW;
END;
$$;

CREATE TRIGGER customers_sync_display_name
BEFORE INSERT OR UPDATE OF full_name
ON customers
FOR EACH ROW
EXECUTE FUNCTION sync_customer_display_name();
~~~

This example fits cases where both columns share the exact same semantics and the old column remains the source of truth during transition. The trigger keeps inserts and updates from old application instances populating `display_name`.

A bridge application version may write both `full_name` and `display_name` in the same transaction, while the trigger in this example still treats `full_name` as canonical. Do not use this one-way trigger pattern if the two columns follow different transformation rules or if the new version writes solely to the new column. For complex transitions, design bidirectional sync with explicit conflict rules or switch the write authority via a dedicated protocol.

Triggers run as production logic and add overhead to every write. Monitor trigger errors, latency, and deadlocks; document which migration owns the trigger and the criteria for removing it.

### Stage 3: Backfill Legacy Rows in Batches

Rows existing before the trigger was created will have `NULL` in `display_name`. Never update an entire large table in one long transaction. Split into batches, commit each batch, and design the job to resume cleanly after interruption.

Example batch of up to 1,000 rows:

~~~sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE display_name IS NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET display_name = c.full_name
FROM batch
WHERE c.id = batch.id
RETURNING c.id;
~~~

Run this statement repeatedly in separate transactions until no rows remain. `SKIP LOCKED` lets the worker skip rows currently locked by other transactions; consequently, an empty batch result does not guarantee the entire table is finished if concurrent transactions are still holding rows. Run a final verification sweep after active transactions settle.

Backfills should be:

- **Idempotent:** re-running does not corrupt already-migrated rows.
- **Checkpointed:** tracks progress or filters remaining rows cleanly to resume.
- **Rate-limited:** batch size, inter-batch sleep, and worker concurrency respect production headroom.
- **Interruptible:** stopping the job leaves neither massive transactions nor unrecoverable half-states.
- **Observable:** logs updated row counts, throughput, errors, WAL generation, replica lag, and query durations.

Never increase batch size merely to finish faster. Backfills amplify WAL volume, replication lag, I/O, cache churn, and autovacuum contention. Start with small batches and tune based on observed metrics.

### Stage 4: Verify Data Completeness and Parity

After backfilling, compare both columns:

~~~sql
SELECT
    count(*) FILTER (WHERE display_name IS NULL) AS missing_count,
    count(*) FILTER (
        WHERE display_name IS DISTINCT FROM full_name
    ) AS mismatch_count
FROM customers;
~~~

Assuming `full_name` is always populated and both columns must match, both counts must be 0. If data is normalized or transformed under a mapping rule, compare against the transformed expression rather than raw equality.

Inspect sample mismatched rows if any appear:

~~~sql
SELECT id, full_name, display_name
FROM customers
WHERE display_name IS DISTINCT FROM full_name
ORDER BY id
LIMIT 100;
~~~

Do not switch the application to read the new column merely because the backfill job exited cleanly. Verify parity, audit every write path, and resolve any rows skipped due to locks or conversion errors.

### Stage 5: Switch Application Reads to the New Column

Deploy the next application version reading `display_name`. Throughout the rollback window, keep writing both old and new columns—or keep verified synchronization active—so older binaries can still function if rolled back.

A new read query:

~~~sql
SELECT id, display_name
FROM customers
WHERE id = $1;
~~~

During rollout, monitor:

- Query errors from missing columns or permission mismatches.
- `NULL` counts and column mismatches.
- Request success rates, latency, and business errors.
- Pod counts running old vs. new versions.
- Workers, cron jobs, consumers, or scripts still reading/writing the old column.
- Trigger logs and update frequency on the old column.

Never rely solely on a Pod deployment check as proof that all clients upgraded. Scheduled jobs or external services may live outside the main Deployment.

### Stage 6: Contract in a Separate Release

Only when no code references `full_name`, new data is verified, the rollback window has closed, and data owners sign off should you drop the trigger and old column.

~~~sql
DROP TRIGGER customers_sync_display_name ON customers;
DROP FUNCTION sync_customer_display_name();

ALTER TABLE customers
DROP COLUMN full_name;
~~~

This is a breaking change. Never run it in the same rolling deployment while older application instances remain alive. Nor should it run before auditing views, functions, reports, ETL jobs, ad-hoc queries, and admin tools that may depend on the old column.

After contracting, rolling back to the old binary is typically no longer viable. Reverting requires a forward-fix or a dedicated schema/data restore plan; never assume you can simply redeploy the previous container image.

## 5. Changing Data Types or Data Rules

Changing a column's data type often requires more steps than renaming a column. Suppose you want to migrate text column `amount_text` to `amount numeric(12,2)`. Direct casting can fail on malformed values and lock or rewrite the table for a long time.

Safe conversion pattern:

1. Add a new column with the target data type, initially nullable.
2. Deploy compatible code writing values under standardized formatting rules.
3. Backfill legacy values to the new type in batches.
4. Capture and resolve values that fail conversion.
5. Verify row counts, aggregate totals, and discrepancies.
6. Switch reads to the new column.
7. Maintain compatible writes throughout the rollback window.
8. Drop the old column in a later release.

Before casting, locate malformed rows:

~~~sql
SELECT id, amount_text
FROM invoices
WHERE amount_text IS NOT NULL
  AND amount_text !~ '^[0-9]+([.][0-9]{1,2})?$'
ORDER BY id
LIMIT 100;
~~~

The regex above is only an example for simple decimal strings; it does not cover negative signs, thousand separators, locales, or scientific notation. Parsing rules must match actual production data formats.

Never run an unguarded bulk cast inside a migration where a single malformed row aborts the entire table migration. Classify anomalies, decide how to repair or quarantine exceptions, and track processed row counts.

## 6. Adding Constraints Without Long Application Blocking

Adding a constraint immediately can require scanning all existing rows and acquiring locks that disrupt traffic. PostgreSQL provides staged enforcement mechanisms.

For example, adding a `NOT NULL` check on `display_name` without scanning existing rows immediately:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT customers_display_name_not_null
CHECK (display_name IS NOT NULL)
NOT VALID;
~~~

A `NOT VALID` constraint does not validate pre-existing rows yet, while still enforcing the rule for all new inserts and updates. After backfilling and verifying data, validate separately:

~~~sql
ALTER TABLE customers
VALIDATE CONSTRAINT customers_display_name_not_null;
~~~

Afterward, if your PostgreSQL version and constraint state allow, you can set the formal `NOT NULL` column attribute:

~~~sql
ALTER TABLE customers
ALTER COLUMN display_name SET NOT NULL;
~~~

A validated `CHECK` constraint can allow PostgreSQL to skip a full table scan when setting `NOT NULL` on versions supporting that optimization. Even so, the command still acquires metadata locks; test on your exact version and data size. Once `NOT NULL` is set, the temporary `CHECK` constraint can be dropped if no longer needed:

~~~sql
ALTER TABLE customers
DROP CONSTRAINT customers_display_name_not_null;
~~~

`NOT VALID` does not apply identically to every constraint type. Foreign keys, unique constraints, and check constraints have different capabilities and rollout sequences. Use syntax verified for your constraint type and PostgreSQL version.

### Staged Foreign Keys

You can add a foreign key as `NOT VALID`, then validate existing rows with `VALIDATE CONSTRAINT`:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT order_items_product_fk
FOREIGN KEY (product_id)
REFERENCES products(id)
NOT VALID;

ALTER TABLE order_items
VALIDATE CONSTRAINT order_items_product_fk;
~~~

While unvalidated, the constraint is still enforced for new writes per PostgreSQL semantics. Before adding it, check existing data for orphaned rows and define cleanup handling.

## 7. Building Indexes on Busy Tables

Standard index creation can block writes on the table for the duration of the build. PostgreSQL supports:

~~~sql
CREATE INDEX CONCURRENTLY idx_customers_display_name
ON customers(display_name);
~~~

`CONCURRENTLY` allows `INSERT`, `UPDATE`, and `DELETE` operations to proceed during most of the build, though the build takes longer and waits on active transactions across multiple phases. This command **cannot execute inside a transaction block**. Your migration tool must support marking this migration as non-transactional.

If concurrent index creation fails, PostgreSQL may leave behind an invalid index. Check its status:

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisready,
    indisvalid
FROM pg_index
WHERE indexrelid = 'idx_customers_display_name'::regclass;
~~~

If the index is invalid, handle it per runbook—typically dropping it with `DROP INDEX CONCURRENTLY` before rebuilding:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS idx_customers_display_name;
~~~

`DROP INDEX CONCURRENTLY` also cannot run inside a transaction block. Never drop an old index still relied upon by queries before the new index is valid and execution plans are verified.

After creating the index, inspect `EXPLAIN (ANALYZE, BUFFERS)` on representative queries in an appropriate environment. An index existing does not guarantee the planner picks it or that performance improves. On large tables, index builds consume CPU, I/O, and temp disk space; monitor system load.

## 8. Controlling Locks and DDL Execution Time

DDL acquires locks on relations. An `ALTER TABLE` may queue behind a long-running transaction accessing the table. While DDL waits for an exclusive lock, subsequent incoming queries also queue behind the waiting DDL—causing a major traffic pile-up even before the schema change executes.

Use `lock_timeout` so DDL fails fast if it cannot acquire the lock within the allowed window:

~~~sql
SET lock_timeout = '2s';
ALTER TABLE customers ADD COLUMN display_name text;
RESET lock_timeout;
~~~

Short timeouts prevent migrations from hanging indefinitely during peak traffic. When a timeout occurs, log the failure and retry cleanly; never crank timeouts up indefinitely just to force a migration through. A separate `statement_timeout` can bound total statement runtime, tuned appropriately for longer operations like `VALIDATE CONSTRAINT` or index builds.

Before running migrations, inspect long-running transactions and sessions holding locks:

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
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Inspect locks on the target table:

~~~sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    l.mode,
    l.granted,
    a.xact_start,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation = 'customers'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
~~~

Never blindly terminate long-running sessions. A transaction may belong to a legitimate batch job or require coordination with its owner. Identify the application, statement, and impact before intervening.

## 9. Backfilling Large Data While Production Continues Writing

Backfilling reads and updates legacy rows into the new format. It is often the most resource-intensive phase of an online migration.

### Why Avoid Backfilling an Entire Table in One Transaction?

A massive transaction can:

- Hold row locks for long durations, blocking application transactions.
- Generate massive WAL volume, spiking replication lag and archive pressure.
- Pin old tuple versions, preventing vacuum from reclaiming space.
- Take a very long time to roll back if interrupted.
- Increase table bloat and I/O contention.
- Cause replicas or backups to fall behind.

Partition the work by primary key or a stable cursor, commit per batch, and throttle throughput. On tables with monotonically increasing keys, jobs can persist a `last_id` checkpoint. Even then, perform a final sweep to catch any rows skipped or inserted mid-run.

### Monitoring and Throttling Load

Metrics to watch:

- Processed rows, remaining rows, and rows-per-second rate.
- Per-batch duration and retry counts.
- CPU, IOPS, disk latency, and free disk space.
- WAL generation rate, archive backlog, and `pg_wal` disk usage.
- Replication lag across every standby.
- Lock waits, deadlocks, autovacuum activity, and bloat.
- Application error rates during the backfill window.

If replica lag or production latency breaches thresholds, shrink batch sizes, reduce worker concurrency, or pause the backfill. The job must resume cleanly without restarting from scratch.

### Avoiding Overwriting Newer Data

Backfills run concurrently with live application traffic. Update conditions must never overwrite fresher values just written by the application. For example, predicate on `display_name IS NULL` when a trigger or bridge writer already populates new rows. If transformation logic must touch all rows, use a version/timestamp column or compare-and-set rule to distinguish stale from fresh data.

Do not run multiple backfill workers over the same key range without explicit partitioning or `SKIP LOCKED`. Parallel workers can boost throughput, yet also amplify lock contention, WAL volume, and storage load.

## 10. Dual-Writes, Triggers, and Switching Data Sources

Dual-writing means the application writes both old and new structures during a transition phase. This eases rollbacks, yet introduces risk if one write fails or transformation logic diverges.

When both columns reside in the same PostgreSQL table and update inside the same statement or transaction, the database guarantees both changes commit or roll back atomically. When writing across two distinct systems or databases, atomicity is not automatic; use an outbox, CDC, or resilient synchronization pipeline.

Common options:

| Sync Mechanism | Best Suited When | Risks to Manage |
|---|---|---|
| Application dual-write | You can ship a bridge release and control all writers | Every service/job must share identical rules; partial failures must be handled |
| Database trigger | Legacy writers cannot upgrade simultaneously | Hidden DB logic, write overhead, recursion, and precedence if both columns change |
| One-shot backfill then switch | No legacy writers remain or data is static during cutover | Concurrent writes risk missing or overwriting fresh values |
| CDC / replication pipeline | Moving large datasets continuously across systems | Lag, ordering, duplicates, schema evolution, and error handling |

Never dual-write indefinitely. Define the canonical source of truth for each phase, conflict resolution rules, and explicit exit criteria. If business rules allow the two columns to diverge intentionally, simple equality checks cannot verify parity.

## 11. Managing Migrations When Multiple App Instances Start Up

Never run migrations from application startup hooks if multiple Pods can boot simultaneously. Two migration processes can read the same version and attempt overlapping DDL, or one Pod may migrate while another Pod runs against a half-applied schema.

A safer model:

1. A dedicated pipeline stage or Kubernetes Job executes migrations.
2. The migration runner acquires a lock so only one runner executes at a time.
3. The runner inspects the current version and applies only pending migrations.
4. Each migration carries a clear version ID, checksum, and execution status.
5. Only after migrations succeed does the pipeline roll out application instances.
6. The migration job has dedicated logging, timeouts, retry policies, and scoped database privileges.

You can use a session-level advisory lock to serialize runners:

~~~sql
SELECT pg_advisory_lock(652001, 1);

-- Migration runner executes migrations in order.
-- Keep this same connection for the entire duration the lock is held.

SELECT pg_advisory_unlock(652001, 1);
~~~

Session advisory locks must be acquired and released on the exact same connection. If the connection drops, PostgreSQL automatically releases session-level advisory locks. Standard migration tools usually include tested locking mechanisms; prefer those battle-tested locks over rolling custom locks without recovery procedures.

A migration history table should record at least version, execution timestamp, status, and content checksum. If an already-applied migration file is modified, handle checksum mismatches explicitly; never silently re-run historical migrations.

## 12. Transaction Boundaries and Non-Transactional Migrations

Many PostgreSQL DDL statements run inside transactions, allowing automatic rollback on failure. However, certain commands cannot run inside a transaction block—most notably `CREATE INDEX CONCURRENTLY` and `DROP INDEX CONCURRENTLY`. Several other maintenance commands carry similar restrictions.

Do not wrap an entire migration release inside one giant transaction if it includes non-transactional commands or heavy backfills. Split migrations by purpose and rollback semantics:

- Short, compatible DDL: small transaction.
- Concurrent index: separate non-transactional migration.
- Backfill: batched, checkpointed job.
- Validation: separate observable step.
- Contract: breaking migration executed later in its own release.

Already-committed migrations do not automatically revert if a subsequent step fails. Prepare forward-fixes, compensating migrations, or restores tailored to each change type.

## 13. Rolling Deployment and Release Sequencing

A typical release sequence:

| Stage | Database | Application | Gate to Proceed |
|---|---|---|---|
| 0. Baseline | Old schema only | All old version | Backup and baseline verified |
| 1. Expand | Add new columns/tables/indexes, keep old structure | Still old version | New schema tested with old app |
| 2. Bridge | Sync old/new, backfill | Rolling deploy bridge version | All writers covered |
| 3. Switch reads | Both structures coexist | New version reads new structure | Parity and metrics verified |
| 4. Retire old writes | Stop legacy dependencies, keep structure | New version, rollback window closed | Zero legacy readers/writers left |
| 5. Contract | Drop old triggers/columns/indexes | Version using only new schema | Approvals and recovery plan ready |

The critical invariant is expanding the schema before deploying code that requires the new schema. During an application rollback, the expanded schema must remain compatible with the old binary. Contracting occurs only after rolling back to the old binary is no longer needed.

### Auditing Every Writer and Reader

Before contracting, search for all dependencies:

- API services and workers.
- CronJobs, scheduled tasks, and queue consumers.
- BI reports, ETL pipelines, data warehouses, and CDC streams.
- Views, materialized views, functions, procedures, triggers, and rules.
- Admin scripts, notebooks, and ad-hoc queries.
- Third-party integrations sharing the database.
- Backup/restore tooling, upcoming migrations, and runbooks.

A column absent from the primary service repository may still power a nightly report or external job.

## 14. Rollback and Forward-Fix

Application rollback and database rollback are separate operations. In compatible migrations, the goal is enabling binary rollbacks while the schema retains both old and new structures.

**Before switching reads:** you can roll back the bridge version to the old version if the expanded schema still supports old code and triggers/dual-writes remain active.

**After switching reads, before contracting:** you can roll back to the bridge version or old version provided old data remained fully synchronized and all dependencies are intact.

**After contracting:** the old binary may no longer run. Recovery typically requires a forward-fix, restoring schema/data from backup, or a dedicated recovery migration. Never assume simply renaming a column back safely restores all data written post-cutover.

For irreversible data mutations, capture snapshots or audit trails beforehand. Still, avoid cloning huge tables solely for false peace of mind if doing so overloads production; align backup and restore strategies with dataset scale.

Every release should document rollback boundaries: which steps support binary rollback, which require a forward-fix, which require restore, and who holds authority to decide.

## 15. Migrations in Multi-Application Environments

A shared database may be accessed by multiple independent services, each on its own release cadence. Schema changes must be coordinated as cross-consumer contracts.

Track table and column ownership and maintain a consumer inventory. If one service wants to drop a column potentially read by another service, establish deprecation notices, telemetry, or direct owner sign-off. Never rely solely on searching the main service's repository.

Version and communicate database contract changes just like API changes. An internal schema registry or catalog can document producers, consumers, owners, and deprecation dates.

When multiple teams run migrations, establish ordering conventions and avoid two independent migrations altering the same table concurrently. Migration locks prevent overlapping execution, not logical conflicts between two competing plans.

## 16. Pre-Production Migration Testing

Testing must cover the transition window when schema and application versions are temporarily mixed.

A comprehensive test suite covers:

- **Schema compatibility:** old app works against expanded schema; bridge version works; new version works prior to contract.
- **Rolling deployment:** simulate old Pods and new Pods querying the database simultaneously.
- **Concurrent writes:** update rows while backfill runs.
- **Backfill restart:** interrupt mid-run and resume, ensuring zero lost or duplicated updates.
- **Lock behavior:** run migration alongside long transactions and verify `lock_timeout` triggers cleanly.
- **Index builds:** verify `CREATE INDEX CONCURRENTLY` runs outside transactions and test handling invalid indexes.
- **Constraint validation:** test both compliant and violating rows.
- **Rollback:** test binary rollback at every stage prior to contract.
- **Failure injection:** simulate dropped connections, killed jobs, temp space exhaustion, or replica lag.
- **Data verification:** compare row counts, `NULL`s, mismatches, aggregates, and business invariants.

Test on data clones matching production scale and skew. A staging table with a few hundred rows reveals nothing about lock wait behavior, WAL spikes, and I/O on a table with hundreds of millions of rows.

## 17. Observability During Live Migrations

Even online migrations can degrade performance. Monitor both database and application telemetry.

**PostgreSQL:**

- `pg_stat_activity`: active queries, transaction age, wait events.
- `pg_locks`: granted vs. waiting locks.
- `pg_stat_progress_create_index`: index build progress.
- `pg_stat_user_tables`: update rates, dead tuples, and vacuum runs.
- `pg_stat_replication`: sent/write/flush/replay LSN lag.
- `pg_stat_archiver`: archive backlog and failures.

Example inspecting index build progress:

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
~~~

**Application and Infrastructure:**

- Error rates, p95/p99 latency, and request timeouts.
- Connection pool saturation and connection resets.
- CPU, memory, I/O latency, and disk utilization.
- Worker queue depth and consumer lag.
- Replication lag, WAL archive delay, and backup health.
- Backfill progress, failure counts, and batch durations.

Define pause or throttle thresholds before starting. For instance, if replication lag crosses a threshold or production latency spikes, backfill workers should automatically slow down or pause. Assign an active operator with a tested kill switch.

## 18. Common Anti-Patterns

**Renaming or dropping columns in the same release as new code.** Old Pods may still be running, and binary rollbacks will break. Add new structures first, transition gradually, and drop later.

**Adding `NOT NULL` immediately on a large table before backfilling.** Legacy rows may violate it, and validation can cause heavy scans or locks. Add nullable columns, backfill, validate, and then enforce constraints.

**Backfilling an entire table in one transaction.** Long transactions pin resources, flood WAL, and make rollbacks slow. Batch, commit incrementally, and checkpoint progress.

**Dual-writing without defining a canonical source.** Values can drift apart. Define source precedence, conflict handling, and dual-write exit criteria.

**Running migrations from every Pod.** Concurrent instances may collide on DDL. Use a single locked migration runner with a history table.

**Running `CREATE INDEX CONCURRENTLY` inside a transaction block.** PostgreSQL rejects it. Place it in a separate non-transactional migration.

**Using huge `lock_timeout` values.** Waiting DDL queues incoming traffic behind it and amplifies outages. Keep timeouts tight, inspect long transactions, and retry cleanly.

**Contracting immediately after rollout finishes.** Workers, cron jobs, or older clients may still lag behind, and the rollback window has not closed. Audit every dependency before dropping.

**Equating DDL success with data correctness.** Successful DDL does not prove backfills completed or transformations were accurate. Verify data using invariants and business metrics.

## 19. Sample Runbook for an Online Migration

A runbook can be structured as follows:

**Before Starting**

1. Record current schema version, running app versions, and dependent consumers.
2. Confirm latest backup and verified restore readiness.
3. Dry-run the migration on a production-sized dataset copy.
4. Measure lock impact, DDL duration, WAL volume, replication lag, and rollback plan.
5. Confirm owner, observation window, abort thresholds, and contract approver.

**During Expand**

1. Execute additive DDL with an explicit `lock_timeout`.
2. Verify new columns, indexes, and constraints exist.
3. Rolling-deploy the bridge application version.
4. Confirm old and bridge versions run cleanly together.
5. Enable triggers or dual-writes as designed.

**During Data Migration**

1. Run batched backfills with checkpoints.
2. Monitor WAL, replica lag, locks, latency, and app errors.
3. Pause or throttle if thresholds are exceeded.
4. Run a final sweep for any skipped rows.
5. Verify row counts, `NULL`s, mismatches, and invariants.

**During Switch**

1. Deploy the release reading the new structure.
2. Keep the old column synchronized during the rollback window.
3. Monitor query errors, data drift, and legacy consumers.
4. Confirm all Pods, workers, cron jobs, and batch jobs upgraded.

**Before Contract**

1. Confirm zero traffic or reads/writes remain on the old structure.
2. Confirm the rollback window has closed and owner approval is granted.
3. Capture a backup/snapshot per policy.
4. Remove triggers or dual-writes in an appropriate release.
5. Drop old structures in a dedicated migration with `lock_timeout`.
6. Verify application health, query plans, metrics, and data post-contract.

## 20. Pre-Completion Migration Checklist

- [ ] Schema expansion does not break older application versions.
- [ ] Migration runner enforces single execution with history tracking and checksums.
- [ ] DDL is broken into small steps with explicit `lock_timeout` and proper transaction boundaries.
- [ ] Large indexes use concurrent builds with invalid-index cleanup procedures.
- [ ] Backfills are batched, checkpointed, retryable, and rate-limited.
- [ ] Old and new writers synchronize data around one clear canonical source.
- [ ] Data parity is verified via row counts, `NULL` checks, mismatch queries, and invariants.
- [ ] New version reads the new structure stably in production.
- [ ] Workers, cron jobs, consumers, reports, and external services have been audited.
- [ ] Binary rollback was tested while the schema remained compatible.
- [ ] The rollback window closed prior to contracting.
- [ ] Legacy structures are dropped only after data owner sign-off.
- [ ] Monitoring dashboards and runbooks are updated.

Compatible migrations are an intentional sequence of coordinated releases. When the schema expands first, data is synchronized and verified, applications transition version by version, and legacy structures are retired last, PostgreSQL can continue serving live traffic throughout nearly the entire change. Success is proven by application compatibility, data accuracy, and safe operability whenever a step must pause or roll back.
