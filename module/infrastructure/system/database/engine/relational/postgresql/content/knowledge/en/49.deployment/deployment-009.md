# Integrating Migrations, Monitoring, and Post-Deployment Checks into PostgreSQL Workflows

An application release can succeed at the binary layer yet still fail at the database: migrations did not run, schemas changed only partially, indexes remain invalid, backfills are incomplete, permissions are wrong, or new queries spike system load. Conversely, migrations may complete while applications, workers, scheduled jobs, or subscribers are still running old versions incompatible with the new schema.

Therefore, migrations must be managed as part of the release lifecycle. Pipelines must know which migrations will run, on which cluster, from which schema version to which target version, what locks or maintenance windows are needed, what stop criteria apply, and what must be proven after deployment. Monitoring provides operational signals; post-deployment verification provides evidence that both the database and applications reached the intended state.

This lesson presents how to integrate migrations, monitoring, and post-deployment checks into PostgreSQL deployment workflows, from preflight through release closure. The goal is repeatable deployments, early fault detection, bounded blast radius, and controlled recovery.

~~~mermaid
flowchart TD
    A["Build release artifact"] --> B["Preflight: version, backup, capacity, locks"]
    B --> C{"Preflight passed?"}
    C -->|"No"| X["Stop release / resolve blocker"]
    C -->|"Yes"| D["Acquire migration lock"]
    D --> E["Run expand-compatible migrations"]
    E --> F{"Migration succeeded?"}
    F -->|"No"| R["Contain + recovery decision"]
    F -->|"Yes"| G["Deploy application / workers"]
    G --> H["Canary + monitor"]
    H --> I{"Health and data checks passed?"}
    I -->|"No"| R
    I -->|"Yes"| J["Backfill / validate / reconcile"]
    J --> K["Post-deploy acceptance checks"]
    K --> L{"All criteria passed?"}
    L -->|"No"| R
    L -->|"Yes"| M["Release sign-off and close"]
~~~

This lesson belongs to the **Deployment** chapter, **Database Engine Relational PostgreSQL** module.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why database migrations belong in the release lifecycle.
2. Design a migration pipeline with preflight, lock, execution, and verification gates.
3. Identify schema baselines, target versions, and migration artifacts.
4. Assess backups, restore readiness, capacity, and lock risks prior to deployment.
5. Distinguish transactional DDL from operations that cannot run inside transaction blocks.
6. Integrate a migration runner into CI/CD without unintended parallel execution.
7. Implement expand-contract to support rolling deployments.
8. Manage backfills, validation, and long-running operations.
9. Build monitoring for the database, migration runner, and application.
10. Define appropriate SLIs/SLOs and release thresholds.
11. Write post-deployment checks for schemas, data, permissions, replication, and application behavior.
12. Distinguish application rollback, schema rollback, and forward-fix.
13. Collect evidence and maintain an audit trail for changes.
14. Design canaries, staged rollouts, and stop conditions.
15. Create runbooks for migration failures, lag, query regressions, and data mismatches.
16. Automate repeatable checks while keeping remediation under change control.
17. Close releases only after acceptance criteria are verified.

## 2. Why Migrations Must Belong to the Release Process

Migrations alter the contract applications rely on. These changes can affect:

- Table structures, columns, types, and constraints.
- Indexes and query plans.
- Roles, ownership, grants, and RLS policies.
- Triggers, functions, views, and extensions.
- Data representation and backfill state.
- Replication, CDC, and downstream consumers.
- Locking, WAL generation, disk usage, and latency.

If migrations run outside the pipeline, release artifacts and database states can drift out of sync. One environment might run new code against an old schema; another might have the new schema without deployed code. During an incident, teams struggle to know which commands ran, who ran them, which artifact was used, and which state is authoritative.

The release process needs a versioned source of truth for:

- Application artifacts.
- Migration artifacts/checksums.
- Source schema version.
- Target schema version.
- Deployment target.
- Migration execution results.
- Post-deployment verification results.

Never treat a log line saying "migration command exited 0" as sufficient proof that a release succeeded.

## 3. Release Lifecycle for Database Changes

A release with migrations should include these phases:

| Phase | Goal | Artifacts to Record |
| --- | --- | --- |
| Plan | Define scope and compatibility | Change plan, migration list |
| Build | Package code and migrations | Immutable artifact, checksum |
| Preflight | Verify target/capacity/backups | Preflight report |
| Migrate | Run schema/data changes | Migration logs, ledger |
| Deploy | Roll out app/worker versions | Deployment versions |
| Observe | Monitor behavior and load | Metrics, logs, traces |
| Verify | Validate schema/data/business | Post-deploy report |
| Close | Record acceptance/sign-off | Change closure evidence |

Steps can be organized into an automated pipeline or multi-stage gated approvals. Regardless, ordering and dependencies must be explicit. For example, never run a contract migration dropping an old column before all application instances and workers have stopped using that column.

## 4. Source of Truth and Schema Versions

Every environment must know its current schema and target schema.

Migration frameworks typically maintain a metadata table, such as Flyway, Liquibase, Alembic, Rails, or internal tooling. Table names and semantics differ, so pipelines should invoke the framework's official CLI/API.

A schema version record may contain:

- Migration version or ID.
- Description.
- Checksum.
- Installed timestamp.
- Execution duration.
- Success/failure state.
- Tool version.
- Release/build identifier if supported by the framework.

Inspect the history table per your framework. Illustrative example using an application-managed table:

~~~sql
SELECT
    version,
    description,
    checksum,
    installed_on,
    execution_time,
    success
FROM app_schema_migrations
ORDER BY version;
~~~

Do not assume this example table exists in every project.

### Source Schema and Target Schema

Before deployment, the pipeline should determine:

- Current schema version.
- Pending migration IDs.
- Target version.
- Migration order.
- Approved checksums.
- Whether any migration was modified after deployment.
- Whether any migration was skipped/failed/repaired.

Never mark a migration as applied automatically just to turn the pipeline green. The ledger must reflect actual database state.

## 5. Immutable Migration Artifacts

Deployed migration files should be treated as immutable. Editing contents after an environment has executed them breaks checksums and reproducibility.

Rules:

1. New migrations get new IDs/versions.
2. Artifacts are built once and promoted across environments.
3. Checksums are stored alongside build metadata.
4. Never generate environment-specific migration variations.
5. Never edit old migrations to fix already-deployed bugs.
6. If repairs are needed, create a new migration or use the official repair mechanism after verifying state.

The exact same artifact should run in staging and production. Environment settings are injected separately, while migration contents remain stable.

## 6. Designing Pipelines with Clear Gates

Example stages:

~~~yaml
pipeline:
  stages:
    - validate_artifact
    - preflight
    - migrate_expand
    - deploy_application
    - canary_observation
    - backfill
    - validate_constraints
    - post_deploy_checks
    - release_signoff
~~~

This is a conceptual layout; actual syntax depends on your CI/CD platform.

Every stage needs:

- Clear inputs.
- A clear owner.
- Timeouts.
- A retry policy.
- Success criteria.
- Failure behavior.
- Evidence outputs.

Never automatically retry a migration command simply because a job timed out. First verify transactions, the migration ledger, and object state to know whether the command already committed.

## 7. Preflight: Confirming the Right Target

One of the most dangerous mistakes is running migrations against the wrong database or cluster.

Preflight should verify:

- Environment name.
- Cluster/system identifier.
- Database name.
- Server address/port.
- Primary vs. standby status.
- PostgreSQL major version.
- Current schema version.
- Application service/tenant scope.
- Release ID and artifact checksum.

SQL context:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    version() AS server_version,
    pg_is_in_recovery() AS is_standby,
    pg_postmaster_start_time() AS server_started_at;
~~~

The cluster system identifier can be obtained via `pg_controldata` on an authorized host or provider metadata. Never rely solely on database name, as multiple clusters often share names.

The pipeline must halt if the target does not match the allowlist or environment metadata.

## 8. Preflight: Verifying Version and Configuration

Check version:

~~~sql
SHOW server_version;
SHOW server_version_num;
~~~

Check migration-relevant settings:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'lock_timeout',
    'statement_timeout',
    'maintenance_work_mem',
    'max_wal_size',
    'wal_level',
    'max_replication_slots',
    'max_wal_senders'
)
ORDER BY name;
~~~

Migrations can depend on extensions, collations, encodings, timezones, locales, or major-version features. Record all factors affecting behavior.

Never implicitly change server settings inside the same release. Settings requiring restarts must have a separate change plan or explicit stage.

## 9. Preflight: Backup and Restore Readiness

Before high-risk migrations, verify:

- Most recent backup.
- Backup completion status.
- WAL archive health.
- PITR coverage.
- Target restore point.
- RPO/RTO.
- Most recent restore test.
- Recovery owner.

An existing backup does not guarantee recoverability. Know the backup tool, encryption keys, archive locations, and restore procedures.

Check WAL archiving:

~~~sql
SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

This view may not reflect the full backup system of a managed provider. Cross-check provider backup metrics and external backup tooling.

### Backup Decisions by Migration Type

| Migration | Typical Preparation Level |
| --- | --- |
| Metadata-only nullable column add | Standard backup policy and rollback/forward-fix |
| Adding constraints or large indexes | Capacity, lock impact, backup readiness |
| Table rewrite / type conversion | Restore/PITR plan, disk headroom, maintenance window |
| Destructive data migration | Verified backup, restore drill, explicit approval |
| Major version/cluster migration | Full migration and rollback plan, compatibility testing |

Do not apply one backup rule to every change. Evaluate blast radius and reversibility.

## 10. Preflight: Capacity and Workload

Before running heavy DDL or backfills, check:

- Database/table/index sizes.
- Free disk space on data/WAL/temp/backup volumes.
- WAL generation rate.
- Replication lag and slot retention.
- Long-running transactions.
- Lock blockers.
- Active sessions.
- CPU, memory, and storage latency.
- Autovacuum progress.
- Connection pool utilization.

Example relation sizes:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS table_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 30;
~~~

Check long-running transactions:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 180) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Never automatically terminate sessions solely because a transaction is old. Identify its owner and business impact first.

## 11. Migration Locks: Only One Runner at a Time

Two deployments running migrations concurrently can cause duplicate objects, deadlocks, ledger race conditions, or partial states. Use the migration framework's lock or a unified orchestration lock.

Advisory locks can be used in custom runners:

~~~sql
SELECT pg_advisory_lock(62501, 1);
-- Check ledger, run migrations, and record results.
SELECT pg_advisory_unlock(62501, 1);
~~~

Keys are illustrative. All runners must follow the same convention. Session-level advisory locks persist until unlocked or the session ends; transaction-level locks release when the transaction ends.

A lock does not replace the ledger or state verification. If a process crashes, determine how far migrations committed before proceeding.

### Pipeline Lock Policy

- Scope locks by database/schema/project.
- Assign an owner and timeout.
- Log acquire/release timestamps.
- Disallow other jobs from bypassing the lock.
- Handle stale sessions via runbooks.
- Always release locks upon completion or session close.
- Alert if locks are held too long.

## 12. Lock Timeouts and Statement Timeouts

Set timeouts so DDL never waits indefinitely:

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '20min';
~~~

Choose values based on the operation and workload. Never apply the exact same timeout to a metadata-only column add, `CREATE INDEX CONCURRENTLY`, and a billion-row backfill.

- `lock_timeout` bounds lock wait time.
- `statement_timeout` bounds statement execution time.
- `idle_in_transaction_session_timeout` bounds idle sessions inside transactions.

If a statement times out, the transaction enters an aborted state. The migration runner must roll back or close the transaction properly, then inspect state before retrying.

## 13. Transactional and Non-Transactional Migrations

Many PostgreSQL DDL statements can run inside a transaction. If a step fails before `COMMIT`, rollback undoes all transactional changes.

Some commands cannot run inside a normal transaction block, such as:

- `CREATE INDEX CONCURRENTLY`.
- `DROP INDEX CONCURRENTLY`.
- `VACUUM`.
- `CREATE DATABASE`.
- `DROP DATABASE`.

Having multiple statements in one migration file does not automatically make all statements atomic. Frameworks may split migrations into multiple transactions or run non-transactional statements separately.

The pipeline must know which migrations are:

- Transactional.
- Non-transactional.
- Potentially long-running.
- Heavy-locking.
- Table-rewriting.
- Carrying external side effects.
- Safely retryable.

## 14. Classifying Migrations by Risk

A taxonomy helps pipelines select appropriate gates:

| Group | Examples | Primary Risks |
| --- | --- | --- |
| Metadata change | Add nullable column | Lock acquisition, compatibility |
| Index build | `CREATE INDEX CONCURRENTLY` | I/O, invalid indexes, duration |
| Constraint | `CHECK`/`FK` validation | Scans, locks, legacy data violations |
| Data backfill | Batched `UPDATE` | WAL, bloat, replication lag |
| Type/table rewrite | `ALTER TYPE`, rewrite | Disk space, locks, downtime |
| Security | `GRANT`, RLS, owner | Access regressions |
| Destructive | `DROP`/`DELETE` | Data loss, irreversible changes |
| Extension | `ALTER EXTENSION UPDATE` | Binary/script/version compatibility |
| Partition | Attach/detach/reorganize | Locks, routing, data movement |

Risk scores can factor in table size, lock mode, data loss potential, reversibility, estimated runtime, replication impact, and consumer count.

Do not let developers self-select "low risk" without rule/metadata backing.

## 15. Expand-Contract in Release Pipelines

Expand-contract enables schemas and applications to transition across multiple releases.

Example: renaming column `customer_name` to `display_name`.

**Release A — Expand:**
- Add nullable `display_name`.
- Keep `customer_name`.
- Deploy bridge application capable of compatible reads/writes.
- Start batched backfill.

**Release B — Migrate:**
- Confirm backfill completion.
- Switch application reads to `display_name`.
- Optionally dual-write briefly.
- Monitor apps/workers still reading `customer_name`.

**Release C — Contract:**
- Stop reading/writing `customer_name`.
- Confirm zero old consumers remain.
- Drop `customer_name` in a separate migration.

~~~mermaid
flowchart LR
    A["Release A: expand schema"] --> B["App bridge + backfill"]
    B --> C["Release B: switch reads/writes"]
    C --> D["Observe old consumers = 0"]
    D --> E["Release C: contract old schema"]
~~~

Never add a new column and drop the old column in the same deployment if rolling deployments or rollback windows exist.

## 16. Migration Files and Preconditions/Postconditions

Migrations should state expected inputs and expected outcomes.

Example precondition: verify the column does not exist yet or already has the expected definition.

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Corresponding postcondition:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Pipelines can use framework assertions or custom verification scripts. If an object already exists with a different definition, stop rather than treating `IF NOT EXISTS` as success.

Preconditions/postconditions should appear in change metadata so reviewers know what the migration alters and what evidence confirms success.

## 17. Integrating Migrations into CI

CI must validate migrations before promoting artifacts:

1. Validate SQL syntax and migration naming/ordering.
2. Verify migrations do not alter already-deployed history.
3. Build a database from supported baselines.
4. Restore representative fixtures if needed.
5. Run all pending migrations.
6. Verify schema assertions.
7. Verify data invariants.
8. Run application integration tests.
9. Test rollback/recovery paths where supported.
10. Record runtime, logs, and checksums.

Testing solely from an empty database is insufficient. Production may sit at version N-3 with different data distributions. Test upgrade paths from all supported baselines.

### CI Cannot Prove Production Impact

CI validates logic and compatibility in a controlled environment. It cannot fully simulate production table sizes, concurrent transactions, I/O latency, lock contention, or replication topologies. Those require staging/load rehearsals and production rollout gates.

## 18. Integrating Migrations into CD

A typical CD flow:

1. Verify immutable artifact.
2. Resolve target database.
3. Acquire deployment/migration lock.
4. Run preflight.
5. Run expand migrations.
6. Verify migration ledger and schema.
7. Deploy application.
8. Deploy workers/schedulers.
9. Canary.
10. Monitor health.
11. Run backfill/validation.
12. Run post-deployment checks.
13. Release sign-off.
14. Contract migration in a later release once eligible.

For small, backward-compatible migrations, some steps can be combined. For large or destructive migrations, separate stages with appropriate approvals.

## 19. Do Not Run Migrations Inside Every Application Instance

If every pod/process runs migrations on startup, rolling deployments can spawn competing migration runners.

A better pattern:

- A dedicated migration job.
- Executed beforehand or at a defined pipeline stage.
- Protected by a migration lock.
- Emits output to the deployment system.
- App instances only verify schema compatibility at startup.

If a framework forces apps to self-migrate, verify the framework provides locking and tested concurrency behavior. Never assume startup migrations are safe simply because apps can restart repeatedly.

## 20. Backfills in Deployment Pipelines

Large backfills should usually be decoupled from DDL migrations:

- Expand schema first.
- Deploy compatible application.
- Run batched backfill.
- Persist progress durably.
- Data reconciliation confirms completeness.
- Constraint validation happens afterward.
- Contract happens in a subsequent release.

Each batch should have short transactions, explicit key ranges, row counts, checkpoints, and throttling.

Example:

~~~sql
UPDATE public.orders
SET normalized_code = upper(code)
WHERE order_id > 100000
  AND order_id <= 110000
  AND normalized_code IS NULL;
~~~

Fixed ranges here are illustrative. Production runners must pick ranges by key/index, measure actual rows, and persist progress.

If progress markers and data updates share the same transaction, a crash before commit rolls back both. If separate, idempotency is required for safe restarts.

## 21. Tracking Migration Progress

Migration runners should emit structured logs and metrics:

- `migration_id`.
- `release_id`.
- Target database/cluster.
- Start/end timestamps.
- Current step.
- Duration.
- Rows processed.
- Rows/sec.
- Last key/checkpoint.
- Lock wait duration.
- Retry count.
- Error `SQLSTATE`.
- Success/failure.
- Checksum.

Example JSON log:

~~~json
{
  "event": "migration_step_completed",
  "release_id": "release-2026.11.14.3",
  "migration_id": "V042__add_order_channel",
  "database": "sales",
  "step": "backfill_batch",
  "rows_processed": 10000,
  "last_key": 110000,
  "duration_ms": 842,
  "result": "success"
}
~~~

Never log raw customer values, secrets, or full payloads. Use IDs and aggregate counts.

## 22. Monitoring the Database During Releases

Monitoring should cover four layers:

**Availability:** connection success, server up, failover, connection pool exhaustion.

**Performance:** query latency, throughput, CPU, memory, I/O latency, locks, temp files.

**Storage/maintenance:** free disk, WAL growth, checkpoints, autovacuum, dead tuples, relation growth.

**Correctness/replication:** migration state, constraint validity, replication lag, slot retention, data reconciliation.

A dashboard showing only CPU and database uptime is insufficient to verify a safe release.

## 23. SLIs/SLOs for Releases

Select SLIs reflecting user and database behavior:

| SLI | Measurement Example | Used To |
| --- | --- | --- |
| Availability | Successful requests / total requests | Confirm service usability |
| Latency | p50/p95/p99 query/API latency | Detect regressions |
| Error rate | Failed requests / total | Detect runtime errors |
| DB saturation | CPU, connections, I/O queue | Detect resource pressure |
| Lock impact | Lock wait duration/count | Detect DDL contention |
| Replication lag | Replay/apply delay | Assess downstream freshness |
| CDC lag | Source LSN to sink applied time | Assess event freshness |
| Migration duration | Start-to-finish time | Assess capacity/plan accuracy |
| Data correctness | Reconciliation mismatches | Detect missing/corrupt data |

SLO thresholds must be grounded in baselines and business requirements. Never copy a generic latency number across all databases.

### Baselines and Comparison Windows

Compare:

- Pre-release.
- During migration.
- Canary window.
- Post-rollout.
- Same hour/day workload if seasonality exists.

Use consistent metric definitions and aggregation windows. A brief p95 spike from a batch job differs from a sustained post-release regression.

## 24. Monitoring Query Latency and Workload

Use `pg_stat_statements` to track normalized query workloads if the extension is configured.

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Compare snapshots/deltas rather than inspecting raw cumulative counters alone. Track `stats_reset` and server restarts to avoid miscalculating deltas.

When query regressions appear, run `EXPLAIN (ANALYZE, BUFFERS)` on representative workloads. `ANALYZE` executes the query; never run it casually on write statements or very heavy queries in production.

## 25. Monitoring Locks and Blocking

During migrations, lock waits can impact application traffic.

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    now() - waiting.query_start AS wait_age,
    left(waiting.query, 160) AS waiting_query,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 160) AS blocker_query
FROM pg_stat_activity AS waiting
JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocker_pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
WHERE waiting.datname = current_database()
ORDER BY waiting.query_start;
~~~

Alerts can trigger on wait age, blocked session count, and application latency. Base thresholds on baselines.

Never automatically terminate blockers without knowing the owner and impact. Stopping the migration runner or canceling its statement per runbook can be safer than killing business transactions.

## 26. Monitoring Replication and WAL

For physical replication:

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

For logical slots:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Monitor:

- Inactive slots.
- Stalled `restart_lsn`.
- Retained WAL exceeding capacity.
- Standby replay lag.
- Logical subscriber errors.
- WAL archive failures.

Schema migrations can surge WAL heavily, especially rewrites/backfills. Put replication/WAL metrics on the release dashboard.

## 27. Monitoring Autovacuum and Table Health

Large data migrations generate dead tuples and increase autovacuum load.

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Track vacuum progress:

~~~sql
SELECT *
FROM pg_stat_progress_vacuum;
~~~

Counters may be estimates and can reset. Use trends, relation sizes, and vacuum logs to assess health.

Never run `VACUUM FULL` automatically just because dead tuple estimates rise. `VACUUM FULL` rewrites the table under a strong lock; consider standard `VACUUM`, autovacuum tuning, or a planned table rewrite based on evidence.

## 28. Canaries and Staged Rollouts

For large systems, roll out in waves:

- One canary database/tenant.
- One application instance.
- One partition/consumer group.
- A percentage of traffic.
- One region/cluster.

Canaries must check both schema and behavior:

- Migration succeeded.
- App reads/writes properly.
- Error rate has not risen.
- Latency stays within bounds.
- No abnormal lock waits.
- Data invariants hold.
- Replication/CDC lag remains stable.
- No old worker version violates compatibility.

If the canary fails, halt rollout at the current stage. Do not propagate failures across all tenants.

## 29. Post-Deployment Verification: Schema

After migrations, verify actual schema state:

- Migration ledger reached target version.
- No unexpected failed/pending migrations remain.
- Columns/types/defaults/nullability match.
- Indexes exist and are valid.
- Constraints exist and are validated.
- Triggers/functions/views match target versions.
- Extensions match target versions.
- Ownership/grants/RLS are correct.
- Sequences/identity states are valid.

### Checking Invalid Indexes

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisvalid,
    i.indisready,
    i.indislive
FROM pg_index AS i
JOIN pg_class AS c
    ON c.oid = i.indexrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND (NOT i.indisvalid OR NOT i.indisready)
ORDER BY i.indexrelid::regclass::text;
~~~

Zero rows is a good signal for the query's scope, but still verify the specific indexes touched by the release.

### Checking Unvalidated Constraints

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE NOT convalidated
ORDER BY conrelid::regclass::text, conname;
~~~

Some constraints may intentionally remain `NOT VALID` during an expand phase. Compare against expected release state rather than demanding every cluster constraint be validated if managed exceptions exist.

## 30. Post-Deployment Verification: Data

A valid schema does not prove data is valid.

Check:

- Backfill completion.
- NULL/duplicate counts.
- Foreign key orphans.
- Check constraint violations.
- Aggregate totals.
- Sequence positions.
- Row counts by key ranges.
- Old/new column consistency during expand-contract.
- CDC/outbox completeness.
- Data retention/partition coverage.

Example checking un-backfilled rows:

~~~sql
SELECT count(*) AS remaining_rows
FROM public.orders
WHERE normalized_code IS NULL
  AND code IS NOT NULL;
~~~

Example checking duplicate business keys:

~~~sql
SELECT
    external_reference,
    count(*) AS duplicate_count
FROM public.orders
WHERE external_reference IS NOT NULL
GROUP BY external_reference
HAVING count(*) > 1
ORDER BY duplicate_count DESC;
~~~

Example comparing two columns during transition:

~~~sql
SELECT count(*) AS mismatched_rows
FROM public.customers
WHERE display_name IS DISTINCT FROM customer_name;
~~~

Adjust these queries to business rules. `NULL`s may be valid; never mutate data merely to drive mismatch counts to zero without understanding semantics.

## 31. Post-Deployment Verification: Permissions and Security

Migrations can unintentionally alter ownership, grants, default privileges, or RLS.

Verify:

- Application roles have exact required read/write permissions.
- Roles hold no excessive permissions.
- Schema/table owners are right.
- Default privileges apply to future objects.
- RLS is properly enabled/forced.
- Policies have accurate predicates.
- `SECURITY DEFINER` functions have safe owners and `search_path`.
- Connector/replication roles stay within scope.

Example viewing grants:

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
ORDER BY grantee, table_name, privilege_type;
~~~

`information_schema` may only show grants visible to the current role. For full audits, inspect system catalogs with an appropriately privileged role.

Do not merely verify app queries succeed; confirm app roles were not accidentally granted `SUPERUSER`, `BYPASSRLS`, or unnecessary DDL rights.

## 32. Post-Deployment Verification: Application Compatibility

Verify every process accessing the database:

- Web/API instances.
- Background workers.
- Cron/scheduled jobs.
- ETL/ELT jobs.
- Admin scripts.
- CDC connectors.
- Reporting/BI clients.
- Read replicas/subscribers.
- Long-running sessions and connection pools.

Track the actual running version of each instance, not just deployment controller state. Old workers may still be alive accessing contracted columns.

Smoke tests should verify critical business behaviors, not just health endpoints.

## 33. Post-Deployment Verification: Query Plans

Schema migrations can cause the optimizer to pick different plans due to changed indexes, statistics, or data distributions.

Inspect critical queries:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

This is an illustrative query; substitute representative queries and parameter values. `EXPLAIN ANALYZE` executes the statement and incurs load; avoid using it with DML without controlling side effects.

Inspect:

- Appropriateness of index scans vs. sequential scans.
- Estimated rows vs. actual rows.
- Shared/local/temp blocks.
- Sort/hash spills.
- Nested loop behavior.
- Execution time.
- Planning time.
- Lock/wait behavior.

If statistics are stale after bulk changes, schedule `ANALYZE`:

~~~sql
ANALYZE public.orders;
~~~

Do not run database-wide `ANALYZE` casually during peak hours on large databases without resource planning.

## 34. Post-Deployment Verification: Replication and CDC

If the database has replicas or CDC:

- Physical standby replay lag is within bounds.
- Logical subscriptions show no apply errors.
- Subscriber schemas are deployed.
- Replication slots are active and advancing.
- Retained WAL stays within budget.
- Connector source LSNs advance.
- Broker lag is not growing continuously.
- Consumer sink commits succeed.
- Outbox events are relayed.
- Reconciliation detects no gaps.

DDL does not automatically propagate to all logical subscribers or downstream sinks. Post-deploy checks must verify schema parity and data parity across the actual topology.

## 35. Post-Deployment Verification: Sequences and Identity

After imports, restores, or bulk loads with explicit IDs, sequences may trail the max key and cause duplicate key errors on subsequent `INSERT`s.

Check sequence ownership and state. For a specific sequence:

~~~sql
SELECT
    pg_get_serial_sequence('public.orders', 'order_id') AS sequence_name;
~~~

Once the sequence and policy are identified, compare against the max key. Never blindly run a generic `setval` script across all sequences without checking increments, cycling, caching, and concurrent writes.

Sequences are independent objects; native logical replication does not sync sequence states alongside row changes by default. During cutovers, sequence syncing must be an explicit step.

## 36. Health Checks: Readiness, Liveness, and Startup

Application health endpoints serve distinct roles:

- **Liveness:** process is alive; should not depend on transient downstream outages.
- **Readiness:** instance can serve traffic with required dependencies and schema compatibility.
- **Startup:** process finished initialization.

Readiness checks can verify database connectivity and schema compatibility versions. Never run migrations inside readiness probes.

Schema compatibility checks must be lightweight, bounded by timeouts, and read a stable metadata source. If schemas are incompatible, the instance refuses traffic and the pipeline catches deployment ordering errors.

## 37. Release Thresholds and Stop Conditions

Each release needs predefined thresholds:

- API/database error rates.
- p95/p99 latency.
- Connection pool saturation.
- Lock wait duration.
- Deadlocks.
- WAL growth.
- Replication/CDC lag.
- Free disk space.
- Migration runtime.
- Backfill progress.
- Data mismatch counts.
- Failed smoke tests.

Conceptual policy example:

~~~yaml
release_gates:
  migration:
    status: success
    unexpected_pending: 0
  application:
    error_rate_delta: within_baseline
    p95_latency_delta: within_baseline
  database:
    lock_waits: below_threshold
    disk_free: above_reserve
    replication_lag: within_slo
  data:
    reconciliation_mismatches: 0
~~~

This structure is illustrative, not a default threshold set. Choose metrics and bounds according to SLOs, baselines, and business risk.

## 38. Application Rollback, Schema Rollback, and Forward-Fix

These three actions are distinct:

**Application rollback:** reverting binaries/configs to the prior version. Safe only if the current schema remains compatible with old code.

**Schema rollback:** running down migrations or restoring schema/data. Can cause data loss, heavy locks, or fail to reverse side effects.

**Forward-fix:** creating a new migration/application change to move the system from its current state to a valid state.

| Situation | Option to Consider |
| --- | --- |
| Expand migration succeeded, app deploy failed | Roll back app; keep expanded schema if old app is compatible |
| New app failed while schema is compatible | Roll back app or forward-fix |
| Data backfill already created new data | Forward-fix/reconcile is usually safer than down migrations |
| `CREATE INDEX CONCURRENTLY` left invalid index | Clean up/rebuild index per runbook and retry step |
| Contract dropped column | Old app may fail; requires restore/forward recovery |
| Data corruption/loss | Incident recovery, backup/PITR, and reconciliation |
| Target already accepted new writes | Evaluate reverse sync before cutting back to source |

Never assume every migration has a safe down script. Down migrations must be tested and evaluated for data loss before release.

## 39. When to Halt a Rollout

Halt a rollout when:

- Migration failed or ledger state is ambiguous.
- Schema postconditions fail.
- Index invalid/constraint state diverges from expectations.
- Data reconciliation mismatches exceed policy.
- Application error rate/latency breaches thresholds.
- Lock waits impact traffic.
- Disk/WAL capacity falls below reserve.
- Replication/CDC lag exceeds recovery budgets.
- Old workers violate the schema contract.
- No backup/restore path exists for a high-risk change.

Halting a rollout does not automatically mean immediate rollback. Keep the system in a compatible state, gather evidence, and pick a recovery path based on commit/data state.

## 40. Incident Workflow When a Migration Fails

### Contain

- Stop the migration runner and subsequent deployment stages.
- Keep apps on a compatible version.
- Do not retry immediately.
- Preserve logs, artifacts, and timestamps.
- Determine whether traffic/data writes are continuing.

### Determine State

- Confirm target cluster/database.
- Inspect active sessions and transactions.
- Read the migration ledger.
- Inspect catalog objects.
- Inspect data changes/backfills.
- Check index validity and constraints.
- Check replication slots/WAL.
- Identify running app/worker versions.

### Recover

- Roll back uncommitted transactions if applicable.
- Resume batches if progress/idempotency guarantees hold.
- Rebuild invalid indexes if diagnosed appropriately.
- Validate constraints after fixing offending data.
- Forward-fix if dependencies exist.
- Restore/PITR if integrity cannot be assured.
- Reconcile source/sink before reopening traffic.

### Verify

- Schema and ledger align.
- Data invariants hold.
- App/worker compatibility holds.
- Replication/CDC healthy.
- Metrics returned within bounds.
- Evidence and reviewer sign-off complete.

## 41. Change Records and Audit Trails

A change record should include:

~~~yaml
change_id: CHG-2026-0625
release_id: release-2026.11.14.4
environment: production
database: sales
source_schema_version: "041"
target_schema_version: "042"
migration_artifact: "db-migrations-2026.11.14.4"
artifact_checksum: "sha256:example"
execution:
  started_at: "2026-11-14T09:00:00Z"
  finished_at: "2026-11-14T09:03:21Z"
  result: "success"
post_deploy:
  schema_checks: "passed"
  data_checks: "passed"
  application_smoke: "passed"
  replication: "passed"
decision: "release_accepted"
owner: "database_operations"
reviewer: "release_manager"
~~~

This is an example; timestamps, IDs, and checksums must come from real systems. Never record secrets or customer data.

Audit trails must answer:

- Who authored/approved the migration?
- Which artifact was deployed?
- Into which environment?
- When did it start/finish?
- Were there any retries/repairs?
- What were the verification outcomes?
- Who decided on rollback/forward-fix?
- Where is the evidence stored?

## 42. Post-Deployment Runbook

### Phase A: Migration

- Confirm exact target.
- Acquire lock.
- Record current/target schema versions.
- Run migration.
- Save outputs/checksums.
- Verify ledger.
- Verify postconditions.

### Phase B: Application Rollout

- Deploy bridge/compatible app version.
- Deploy workers and scheduled jobs.
- Canary traffic.
- Check errors/latency.
- Check schema compatibility.
- Expand rollout in waves.

### Phase C: Data and Database Health

- Monitor backfill progress.
- Validate constraints.
- Run `ANALYZE` if needed.
- Verify index validity.
- Verify data invariants.
- Check replication/CDC.
- Check disk/WAL/autovacuum.

### Phase D: Acceptance

- Smoke tests.
- Business reconciliation.
- SLO thresholds.
- Security/permissions.
- Evidence.
- Reviewer sign-off.
- Schedule contract stage only once eligible.

## 43. Automating Post-Deployment Checks

Create a verification job running read-only queries:

- Current database/cluster identity.
- Current schema version.
- Expected columns/types.
- Expected indexes and validity.
- Expected constraints and validation.
- Extension versions.
- Role/grant assertions.
- Data count/aggregate checks.
- Replication slot state.
- Application smoke endpoints.
- CDC lag and event freshness.

Output structured JSON for pipeline parsing:

~~~json
{
  "release_id": "release-2026.11.14.4",
  "database": "sales",
  "schema_version": "042",
  "checks": [
    {
      "name": "migration_version",
      "status": "passed"
    },
    {
      "name": "orders_index_valid",
      "status": "passed"
    },
    {
      "name": "backfill_complete",
      "status": "passed",
      "remaining_rows": 0
    },
    {
      "name": "replication_lag",
      "status": "passed"
    }
  ],
  "overall": "passed"
}
~~~

Real outputs should include timestamps, tool versions, target identities, and evidence references. Never return a bare boolean without explaining which checks failed.

## 44. Post-Deploy Checks Must Not Overload Production

Verification queries can also slow production. Design carefully:

- Use catalog lookups for schema assertions.
- Use indexed predicates for data checks.
- Chunk large reconciliations.
- Bound statement timeouts.
- Schedule heavy aggregate scans in suitable windows.
- Avoid running multiple full-table scans concurrently.
- Cache short-lived check results where appropriate.
- Separate fast smoke checks from long deep audits.

If deep data validation is needed, run an async job with progress tracking and an owner. A release can sit in a "deployed, validation pending" state if policy permits, but must not be marked fully accepted before deep checks pass.

## 45. Observability and Correlation

Attach to all release-related logs/metrics/events:

- `release_id`.
- `change_id`.
- `migration_id`.
- `environment`.
- Database/cluster identity.
- Service/version.
- Tenant/wave if applicable.
- Trace/correlation ID.

This links migration runner logs to application errors, database waits, connector lag, and incident records.

Never send raw SQL parameters containing PII into tracing. Use `queryid`/normalized queries and sampled metadata.

## 46. Release Metrics and Dashboard Layout

A release dashboard should include these groups:

| Group | Metrics |
| --- | --- |
| Release progress | Stage, migration ID, duration, current version |
| Database health | Availability, CPU, memory, connections |
| Query behavior | p95/p99, error rate, top query deltas |
| Locking | Waiters, blocker age, deadlocks |
| Storage | Disk free, WAL rate, temp bytes |
| Maintenance | Autovacuum, dead tuples, analyze age |
| Replication | Replay lag, slot retained WAL |
| CDC | Source LSN, broker lag, sink applied time |
| Correctness | Schema assertions, reconciliation mismatches |
| Application | Error rate, request latency, worker health |

Use dashboards to inform decisions, not replace runbooks. Alerts need owners, severities, and actions.

## 47. Preventing Drift Across Environments

Every environment must run the exact same migration artifact in the exact same order. Enforce:

- No manual schema edits outside break-glass.
- Hotfixes must be converted into migrations.
- Compare schema snapshots within scope.
- Check extension versions.
- Manage grants/default privileges.
- Record exceptions with owners/expirations.
- Use the same build artifact.
- Test supported baseline versions.
- Never skip failed migrations.
- Reconcile prior to promotion.

Production may carry intentional differences such as tablespaces, replica topologies, or grants. Schema diffs should distinguish expected vs. accidental differences rather than blindly syncing everything.

## 48. Making Staging Resemble Production

Staging should resemble production in aspects affecting migrations:

- PostgreSQL major/minor versions.
- Extensions and versions.
- Collations/encodings.
- Realistic table/index sizes or scaling models.
- Data distributions/skew.
- Replication topologies.
- Parameter settings.
- Roles/grants.
- Connection pool behavior.
- Concurrent workloads.

If staging is vastly smaller than production, migration durations and locking behavior can differ completely. Rehearse with representative datasets or estimate using measured production metadata.

## 49. Release Cadence and Maintenance Windows

Not every migration requires a maintenance window. Decide based on:

- Lock mode.
- Table rewrites.
- Estimated runtime.
- Application compatibility.
- Replication/CDC impact.
- Data-loss risk.
- Recovery complexity.
- Business traffic patterns.

Online DDL can still trigger lock-acquisition waits or I/O pressure. Maintenance windows do not eliminate risk; they merely pick lower-impact times.

## 50. Managing Multi-Tenant/Multi-Database Releases

If an application spans multiple databases/tenants, rollouts need target-by-target tracking:

| Tenant | Current | Target | Migration State | Verification |
| --- | --- | --- | --- | --- |
| `tenant_a` | 041 | 042 | complete | passed |
| `tenant_b` | 041 | 042 | failed | pending |
| `tenant_c` | 041 | 042 | pending | not started |

Workflow:

1. Build target list from deployment inventory.
2. Choose appropriate concurrency.
3. Run canary tenant.
4. Halt if failures exceed policy.
5. Persist state per tenant.
6. Resume only pending/failed tenants after verification.
7. Do not re-run completed tenants unless recovery plans require it.
8. Enable features once coverage meets threshold.

One successful tenant does not prove the entire fleet succeeded.

## 51. Deployment Anti-Patterns

1. Running migrations on every application startup without locking.
2. Running migrations and deploying code in parallel when new code needs the new schema immediately.
3. Editing old migrations after they were deployed.
4. Timing out and auto-retrying without checking commit state.
5. Manually marking the ledger as applied.
6. Bundling destructive DDL with application rollouts lacking a compatibility phase.
7. Backfilling an entire table inside one long transaction.
8. Running `CREATE INDEX CONCURRENTLY` inside a transaction block.
9. Failing to check for invalid indexes after index builds.
10. Ignoring replication lag/WAL during data migrations.
11. Testing on tiny staging datasets and extrapolating production runtime.
12. Treating a green health endpoint as release acceptance.
13. Checking schemas while ignoring business data.
14. Checking the database while ignoring workers/cron/CDC consumers.
15. Dropping a column as soon as the new app partially rolls out.
16. Rolling back a database after the target accepted new writes without reverse-sync.
17. Running `VACUUM FULL` automatically when bloat rises.
18. Failing to retain migration logs/checksums/release IDs.
19. Running deep verification scans concurrently with peak traffic.
20. Closing changes before reconciliation or restore readiness passes.

## 52. Practice Exercises with Answers

### Exercise 1. Why must migrations belong to the release lifecycle?

**Answer:** Because schemas and applications form a contract; teams must know the artifact, target version, rollout order, and post-deploy state.

### Exercise 2. What does an immutable migration artifact mean?

**Answer:** Once built and deployed, artifact contents are never edited; subsequent changes are introduced via new migrations.

### Exercise 3. What must preflight verify first?

**Answer:** Correct environment, cluster/database identity, current schema version, and target artifact.

### Exercise 4. Why are backups insufficient without restore tests?

**Answer:** Backup file existence does not prove restore procedures, keys, WAL chains, and application recovery work.

### Exercise 5. Why should only one migration runner operate at a time?

**Answer:** To prevent duplicate DDL, race conditions, deadlocks, and ledger inconsistencies.

### Exercise 6. How does `lock_timeout` differ from `statement_timeout`?

**Answer:** `lock_timeout` bounds lock wait duration; `statement_timeout` bounds total statement execution duration.

### Exercise 7. Name one DDL statement that does not run in a standard transaction block.

**Answer:** `CREATE INDEX CONCURRENTLY`.

### Exercise 8. What is the benefit of expand-contract?

**Answer:** Allows old and new apps to coexist during rolling deployments via phased compatible schemas.

### Exercise 9. Why not drop the old column immediately when adding a new column?

**Answer:** Old instances, workers, or scheduled jobs may still read/write the old column.

### Exercise 10. Why should backfills run in batches?

**Answer:** Reduces transaction duration, WAL bursts, and lock pressure while providing checkpoints to resume.

### Exercise 11. What metadata should a migration runner log?

**Answer:** Release ID, migration ID, target, checksum, timestamps, duration, progress, retries, and result.

### Exercise 12. Which SLIs help detect query regressions?

**Answer:** Query/API p95/p99 latency, error rate, and workload statistics compared against baselines.

### Exercise 13. Why is monitoring CPU alone insufficient?

**Answer:** Migrations can cause lock waits, WAL growth, disk pressure, replication lag, or data errors while CPU remains low.

### Exercise 14. What is `pg_stat_replication` used to monitor?

**Answer:** Physical replication sender state and LSN/lag fields for connected standbys.

### Exercise 15. What does `pg_replication_slots` help detect?

**Answer:** Inactive slots, `restart_lsn`, `confirmed_flush_lsn`, and WAL retention status.

### Exercise 16. What should post-deploy schema checks verify?

**Answer:** Ledger, columns/types/defaults, index validity, constraints, extensions, owners/grants, and RLS.

### Exercise 17. Why are data checks needed in addition to schema checks?

**Answer:** A valid schema does not prove backfill completeness, data integrity, or business invariants hold.

### Exercise 18. Why check application workers after deployment?

**Answer:** Old workers may keep accessing altered schemas even after web/API instances are upgraded.

### Exercise 19. What impact does `EXPLAIN ANALYZE` have?

**Answer:** It executes the query; choose representative queries and control side effects and load.

### Exercise 20. When can an application rollback be safe?

**Answer:** When the current schema remains compatible with old code and new data does not break old code.

### Exercise 21. When is forward-fix usually better than a down migration?

**Answer:** When new data already depends on the new schema or rollback risks data loss/side effects.

### Exercise 22. Why is a green health endpoint insufficient to close a release?

**Answer:** It does not fully verify schemas, data reconciliation, replication, permissions, or business behavior.

### Exercise 23. What is a release gate?

**Answer:** A mandatory condition that must pass before a pipeline advances to the next stage.

### Exercise 24. Why use canaries?

**Answer:** To bound blast radius and observe behavior on a subset of traffic/tenants before wide rollout.

### Exercise 25. When should a rollout be halted?

**Answer:** When migration state is unclear, postconditions fail, SLOs breach, disk/WAL runs low, replication lags heavily, or apps are incompatible.

### Exercise 26. Why not retry a migration solely because a CI job timed out?

**Answer:** The server may have committed; verify transaction, ledger, and catalog state before retrying.

### Exercise 27. What should release evidence include?

**Answer:** Artifact/checksum, target identity, migration logs, ledger state, app versions, post-check results, and sign-off.

### Exercise 28. Why use the exact same artifact between staging and production?

**Answer:** So rehearsal results apply to the exact migration contents being deployed.

### Exercise 29. How should multi-tenant releases be tracked?

**Answer:** Store current/target versions, migration states, and verification results per tenant/database.

### Exercise 30. When may a change be closed?

**Answer:** When migration, application, data, security, replication, monitoring, and acceptance criteria all pass, evidence is complete, and reviewers sign off.

## 53. Checklist for Integrating Migrations into Release Processes

### Plan and Build

- [ ] Migration has a new ID/version.
- [ ] Artifact is immutable and checksum is recorded.
- [ ] Current/target schema versions are clear.
- [ ] Migration risk and reversibility are classified.
- [ ] App/worker compatibility is assessed.
- [ ] Expand-contract is used where needed.
- [ ] Upgrade paths from supported baselines are tested.
- [ ] Change owner/reviewer is assigned.

### Preflight

- [ ] Correct cluster/database/environment.
- [ ] PostgreSQL/extension versions compatible.
- [ ] Backup and PITR readiness confirmed.
- [ ] Disk/WAL/temp capacity sufficient.
- [ ] Long-running transactions/blockers checked.
- [ ] Replication/CDC healthy.
- [ ] Maintenance window/stop conditions clear.
- [ ] Migration lock policy ready.

### Execute

- [ ] Only one migration runner.
- [ ] Appropriate timeouts set.
- [ ] Transactional/non-transactional behavior known.
- [ ] Migration logs include release/migration IDs.
- [ ] Backfills use batches/checkpoints.
- [ ] No retries before verifying state.
- [ ] Ledger checked after execution.
- [ ] Lock released.

### Observe and Verify

- [ ] Canary/rollout stage passed.
- [ ] Error rate/latency within thresholds.
- [ ] Lock waits/deadlocks normal.
- [ ] Disk/WAL/replication lag within budget.
- [ ] Indexes valid.
- [ ] Constraints in expected validation state.
- [ ] Backfill/reconciliation passed.
- [ ] Permissions/RLS accurate.
- [ ] Apps/workers/scheduled jobs compatible.
- [ ] Critical query plans show no regressions.
- [ ] CDC/downstream consumers healthy.
- [ ] Smoke tests and business checks passed.

### Close

- [ ] Release artifact/checksum archived.
- [ ] Migration ledger at target.
- [ ] Post-deploy report saved.
- [ ] Exceptions have owners/expirations.
- [ ] Rollback/forward-fix decisions recorded.
- [ ] Reviewer sign-off.
- [ ] Contract migration scheduled separately if legacy schema remains.
- [ ] Change closed per policy.

## 54. Official PostgreSQL References

Consult documentation for the exact major version deployed:

- [SQL Commands](https://www.postgresql.org/docs/current/sql-commands.html) — reference for DDL commands and transaction behavior.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — altering tables, constraints, and validation.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — creating indexes and `CONCURRENTLY`.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes and advisory locks.
- [Lock Management](https://www.postgresql.org/docs/current/runtime-config-locks.html) — lock timeout and deadlock settings.
- [Statement Behavior](https://www.postgresql.org/docs/current/runtime-config-client.html) — `statement_timeout` and session settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — activity, replication, I/O, and progress views.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query workload statistics.
- [pg_stat_io](https://www.postgresql.org/docs/current/monitoring-stats.html) — I/O statistics by backend/context.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — backups, WAL archives, and point-in-time recovery.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — creating physical base backups.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html) — verifying backup manifests.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publications, subscriptions, and schema considerations.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — WAL senders, slots, and replication parameters.
- [Statistics Configuration](https://www.postgresql.org/docs/current/runtime-config-statistics.html) — statistics collection settings.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — `VACUUM`, `ANALYZE`, and autovacuum.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — query plans and `ANALYZE` behavior.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — role attributes.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — ownership and access control.

`/current/` documentation may describe a newer version than your running server. Verify documentation for your exact major version, migration framework, and CI/CD platform before placing commands into production pipelines.

## 55. Summary

**Migrations, monitoring, and post-deployment verification must form one gated, evidence-backed chain within the same release lifecycle.** Migrations change schemas; application rollouts change consumer behavior; monitoring reveals how the system behaves; post-deployment checks confirm both the database and business state reached expectations.

1. **Package migrations with release artifacts.** Keep migrations immutable and record checksums.
2. **Preflight the exact target and schema version.** Verify cluster identity, backups, capacity, locks, and replication.
3. **Allow only one migration runner at a time.** Enforce locks and controlled timeouts.
4. **Classify DDL and data changes by risk.** Transactional behavior, lock impact, WAL, and reversibility determine rollout strategy.
5. **Use expand-contract for rolling deployments.** Drop old schema elements only once zero consumers depend on them.
6. **Decouple long backfills from DDL when appropriate.** Use batches, checkpoints, and reconciliation.
7. **Monitor database and application together.** Latency, errors, locks, disk, WAL, replication, and CDC all impact releases.
8. **Canaries and staged rollouts bound blast radius.** Halt when health or correctness breaches thresholds.
9. **Post-deployment checks must verify schemas, data, permissions, applications, and replication.**
10. **Application rollback is not schema rollback.** Evaluate compatibility and new writes before picking recovery paths.
11. **Forward-fix often fits best once data depends on the new schema.** Down migrations can cause data loss.
12. **Preserve release evidence and audit trails.** Artifacts, ledgers, metrics, checks, and sign-off must be linkable.
13. **Close changes only when acceptance criteria pass.** A green health endpoint alone does not prove a valid release.

A solid deployment workflow lets teams know upfront what will change, observe what is happening, and prove the final state. PostgreSQL migrations then become a controlled release step rather than ad-hoc SQL operations that are hard to trace and recover.
