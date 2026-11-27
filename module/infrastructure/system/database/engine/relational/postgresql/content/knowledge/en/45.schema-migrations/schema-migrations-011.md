# Handling Failed Migrations, Schema Drift, and Partial Deployments in PostgreSQL

A schema deployment can fail at any stage: before running DDL, mid-way through a multi-step script, after part of the statements have committed, while building an index concurrently, or after the database schema changed while compatible application code has not yet rolled out. In those moments, immediately re-running the migration can make the state far more tangled.

**Migration failure** is when one or more schema or data change steps do not complete as planned. **Schema drift** is the divergence between the actual database schema and the schema expected by source code, the migration repository, or a reference environment. **Partial deployment** is a rollout that only finished partially: the database, application, workers, replicas, or environments have not yet reached mutually compatible versions.

Safe remediation begins by determining the exact current state. You must know which migrations were recorded, which statements committed, which objects were created, which data mutated, and which applications currently depend on that schema. Only once you have a reliable picture of state do you choose to retry, roll back, or forward-fix.

~~~mermaid
flowchart TD
    A["Migration / deployment failed"] --> B["Stop further steps"]
    B --> C["Verify target and migration state"]
    C --> D["Inspect ledger, catalog, logs, data"]
    D --> E{"Is state clear?"}
    E -->|"No"| F["Preserve state, gather evidence"]
    F --> D
    E -->|"Yes"| G{"Can we roll back safely?"}
    G -->|"Yes"| H["Execute controlled rollback"]
    G -->|"No"| I["Forward-fix / repair / restore"]
    H --> J["Post-check schema, data, app"]
    I --> J
    J --> K{"Acceptance criteria met?"}
    K -->|"No"| L["Escalate, keep change open"]
    K -->|"Yes"| M["Reconcile migration ledger and close change"]
~~~

This lesson belongs to the **Schema Migrations** chapter of the *Database Engine Relational PostgreSQL* module. The content focuses on investigating failed migrations, detecting schema drift, recovering partial deployments, controlling retries, and verifying state before closing a change.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish migration failure, schema drift, and partial deployment.
2. Identify common root causes of migration failures.
3. Explain why you must not retry a migration before confirming actual state.
4. Inspect migration ledgers and cross-check against database catalogs.
5. Distinguish transactional DDL from operations prohibited inside a transaction block.
6. Handle invalid indexes left after `CREATE INDEX CONCURRENTLY`.
7. Investigate `NOT VALID` constraints and incomplete validations.
8. Detect schema drift across environments.
9. Compare schemas across object definitions, owners, grants, and settings.
10. Design idempotent migrations or migrations with explicit preconditions.
11. Use migration locks to prevent two deployments from running simultaneously.
12. Choose rollback, forward-fix, or restore based on the extent of data mutation.
13. Apply expand-contract to deploy schemas compatible with multiple application versions.
14. Process large data migrations using batches and checkpoints.
15. Recover partial deployments between database and application tiers.
16. Collect evidence, verify state, and update migration ledgers safely.
17. Build runbooks and acceptance criteria for migration recovery.

## 2. Distinguishing the Three Incident Types

### Migration failure

A migration does not finish as planned. Examples:

- `ALTER TABLE` hits a lock timeout.
- `CREATE INDEX CONCURRENTLY` fails.
- A script hits a syntax error on the third statement.
- A data backfill encounters a duplicate key.
- The migration tool loses its connection after the server already committed.
- An extension upgrade script fails.

A migration failure can leave the database unchanged, partially changed, or completely changed while the client missed the response.

### Schema drift

The actual schema differs from the expected schema. Examples:

- A DBA added a column manually without a migration.
- A migration ran on staging but never ran on production.
- An index was dropped during an incident and never recreated.
- Default privileges differ between two databases.
- One environment runs a different extension version.
- The migration ledger claims a migration ran, yet the corresponding object does not exist.

Drift arises from manual edits, skipped migrations, restoring old backups, hotfixes, faulty deploy tooling, or configuration differences across environments.

### Partial deployment

Part of the system upgraded while the rest did not. Examples:

- The new database schema deployed while the old application binary is still running.
- The new application deployed before the migration ran.
- Some workers restarted while older workers still hold open connections.
- The primary upgraded its schema while standbys, consumers, or downstream services lag behind.
- Some tenants/databases migrated while others did not.

Partial deployments are dangerous when two application versions expect incompatible schemas or when services deploy in an incompatible order.

## 3. Why Can Migrations Fail?

Common cause categories:

| Category | Examples | Symptoms |
| --- | --- | --- |
| SQL/schema | Missing column/table/type | `undefined_table`, `undefined_column` |
| Data quality | Duplicates, `NULL`s, invalid values | `unique_violation`, `check_violation` |
| Locking | DDL waiting behind long transaction | Lock timeout, blocked backend |
| Capacity | Disk full, temp/WAL growth | No space left, I/O errors |
| Permissions | Role lacks privileges | Permission denied |
| Version/extension | Incompatible SQL or shared library | Function/library/control file error |
| Network/client | Connection dropped after commit | Client timeout, unknown state |
| Concurrency | Two migrations running simultaneously | Duplicate object, deadlock |
| Application ordering | Code and schema incompatible | Runtime SQL errors |
| Operational | Wrong target, config, or script | Migration run against wrong environment |

An error reported on the client does not always prove the server did not execute the command. For example, a client timeout immediately after `COMMIT` can happen when the transaction committed but the response was lost on the network. State must always be verified on the database side.

## 4. The First Rule: Stop and Determine State

When a migration fails:

1. Halt subsequent migration steps.
2. Do not automatically re-run the same migration.
3. Record the command, migration ID, timestamp, target database, and error output.
4. Determine whether the migration tool wrapped it in a transaction.
5. Check whether the session is still running or disconnected.
6. Inspect the migration ledger.
7. Inspect catalog objects and data mutations.
8. Identify which application versions are currently running.
9. Check whether another deployment or operator is making changes.
10. Pick a recovery path only after state is clear.

If a command timed out, check server-side state first. Never assume a timeout equals a rollback.

### Confirming the exact target

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

Cross-check against your environment, cluster inventory, and deployment records. Connecting to a database with a familiar name does not guarantee it is the right cluster.

## 5. What Is a Migration Ledger?

Migration tools typically store migration history in a metadata/ledger table. Table names depend on the tool, for example:

- Flyway typically uses `flyway_schema_history`.
- Liquibase typically uses `databasechangelog` and `databasechangeloglock`.
- Alembic typically uses `alembic_version`.
- Rails uses `schema_migrations`.
- Prisma uses `_prisma_migrations`.
- Internal tools may use custom tables.

A ledger may record:

- Migration version/ID.
- Description.
- Checksum.
- Start/finish timestamps.
- Execution duration.
- Success/failure status.
- Installed rank or batch.
- Tool version.

### The ledger is not the sole source of truth

The ledger shows what the tool *thinks* ran. Catalogs and data show what state the database is *actually* in.

The two can diverge:

| Ledger | Database objects/data | Possible interpretation |
| --- | --- | --- |
| Succeeded | Matches expectations | Normal state |
| Not recorded | Change already exists | Manual DDL ran, committed before dropped response, or ledger update failed |
| Marked succeeded | Object missing | Drift, object dropped post-migration, or untrustworthy ledger |
| Running/failed | Partial objects exist | Migration interrupted mid-way or contained non-transactional DDL |
| Checksum mismatch | Schema may still match | Migration file edited after deployment |

Never edit the ledger directly with `UPDATE`/`DELETE` just to silence tool errors. First determine actual database state and follow the tool's official repair or baseline procedure.

## 6. Inspecting the Migration Ledger

Example for a simple application-managed history table:

~~~sql
SELECT
    version,
    description,
    installed_on,
    execution_time,
    success
FROM app_schema_migrations
ORDER BY version;
~~~

This is an illustrative schema only. Do not assume all migration tools share identical table or column names.

With Flyway, Liquibase, Alembic, or Prisma, use the proper CLI/API and version-specific docs to:

- Inspect migration history.
- View pending, applied, and failed states.
- Verify checksums.
- Check currently held locks.
- Run repair/baseline if supported by the tool and approved.

Never run a repair command before reconciling the database. A repair command can mark metadata valid without fixing the actual schema.

## 7. Inspecting Active Sessions and Running Migrations

If a migration appears hung, inspect sessions:

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Find blockers:

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    now() - waiting.query_start AS wait_age,
    left(waiting.query, 180) AS waiting_query,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 180) AS blocker_query
FROM pg_stat_activity AS waiting
JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocker_pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
WHERE waiting.datname = current_database()
ORDER BY waiting.query_start;
~~~

A blocker in `idle in transaction` state can still hold locks. Check transaction age and application logs before deciding to terminate.

### Never terminate backends using stale PIDs

A PID may have already exited and been reused. Before canceling or terminating, re-verify PID, user, database, `application_name`, query, and impact. Prefer asking the migration tool or owning operator to stop the session cleanly.

`pg_cancel_backend(pid)` requests canceling the current query. `pg_terminate_backend(pid)` terminates the session and rolls back uncommitted transactions. Both carry operational impact; follow runbooks and approved authorization.

## 8. Transactional DDL in PostgreSQL

Many PostgreSQL DDL operations can run inside a transaction block. If a statement fails inside a transaction, the transaction transitions to the aborted state and requires `ROLLBACK`.

Example:

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN source_channel text;

CREATE TABLE public.migration_audit_demo (
    id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
~~~

If `CREATE TABLE` fails before `COMMIT`, you can `ROLLBACK` the entire transaction and no transactional changes commit.

### Transactional migrations

Advantages:

- Multiple DDL statements commit together.
- If a step fails, rolling back the transaction restores the prior schema state.
- The ledger can be updated inside the same transaction if designed that way.

Limitations:

- Large transactions hold locks for long periods.
- DDL can wait behind blockers.
- Large data backfills prolong transactions, inflate WAL, and retain dead tuples.
- Not all commands are allowed inside a transaction block.
- Tools may split migrations into multiple transactions or run individual statements separately.

Never infer that a migration is atomic merely because a tool calls it a "migration."

## 9. DDL That Does Not Run Inside a Transaction Block

Certain PostgreSQL operations are prohibited inside a transaction block. Classic examples:

- `CREATE INDEX CONCURRENTLY`.
- `DROP INDEX CONCURRENTLY`.
- `VACUUM`.
- `CREATE DATABASE`.
- `DROP DATABASE`.
- `REINDEX ... CONCURRENTLY` in supported versions.
- Certain administrative or extension-specific commands.

The exact list depends on the command and PostgreSQL version.

If a migration contains non-transactional statements, a multi-step script can leave partial state when a later statement fails.

### Example

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON public.orders (created_at);

ALTER TABLE public.orders
ADD CONSTRAINT orders_channel_check
CHECK (source_channel IS NULL OR source_channel IN ('web', 'mobile'));
~~~

The index may have succeeded before `ALTER TABLE` failed. Re-running the entire script will then hit a "relation already exists" error on the index. Inspect every object before retrying.

## 10. Invalid Indexes After CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` reduces write-blocking lock duration compared to standard index builds, yet its build process is complex and can leave behind an invalid index upon failure.

Inspect:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisvalid,
    i.indisready,
    i.indislive,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
WHERE i.indrelid = 'public.orders'::regclass
ORDER BY i.indexrelid::regclass::text;
~~~

If an index is invalid:

1. Confirm the migration ID and error logs.
2. Check whether any `CREATE INDEX` session is still running.
3. Determine whether applications/queries depend on the index.
4. Check definition and tablespace.
5. Plan drop/rebuild factoring in locks and capacity.
6. Verify the index is valid and ready after rebuilding.
7. Update the migration ledger only after state is confirmed healthy.

Example dropping an invalid index:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS public.orders_created_at_idx;
~~~

This command cannot run inside a normal transaction block. Execute it only after verifying the exact index and reviewing dependencies.

Never auto-delete all invalid indexes blindly. Some states require careful analysis, especially if a build is still in progress or another workflow created the index.

## 11. NOT VALID Constraints and Incomplete Validation

PostgreSQL permits adding certain `CHECK` and `FOREIGN KEY` constraints with `NOT VALID`, then validating separately:

~~~sql
ALTER TABLE public.orders
ADD CONSTRAINT orders_amount_nonnegative
CHECK (total_amount >= 0) NOT VALID;
~~~

The new constraint is enforced on newly inserted/updated rows per PostgreSQL semantics, while historical data is not yet fully checked.

Afterward:

~~~sql
ALTER TABLE public.orders
VALIDATE CONSTRAINT orders_amount_nonnegative;
~~~

Check status:

~~~sql
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass;
~~~

If validation fails because historical data violates the constraint, the constraint remains in the `NOT VALID` state. Do not drop the constraint immediately if it is already protecting new writes. Locate violating rows, fix data per business rules, and re-run validation.

Example finding rows failing `CHECK`:

~~~sql
SELECT *
FROM public.orders
WHERE total_amount < 0;
~~~

For foreign keys, locate orphan rows using `LEFT JOIN` or `NOT EXISTS` on the corresponding keys. Once resolved, re-validate and confirm `convalidated = true`.

## 12. Enums and Transaction-Restricted Operations

PostgreSQL supports `ALTER TYPE ... ADD VALUE`, though using the newly added enum value within the same transaction depends on version and transaction state. In modern versions, a value added inside a transaction cannot be used until that transaction commits.

Example:

~~~sql
ALTER TYPE order_status ADD VALUE 'archived';
~~~

If the next statement in the same transaction tries to `INSERT` `'archived'`, it can error depending on version and transaction context.

Safe workflow:

1. Check PostgreSQL major version.
2. Separate adding the enum value from using the new value if needed.
3. Commit the DDL step first.
4. Run data migrations once the enum value is committed and available.
5. Verify `pg_enum` and application compatibility.

Never delete or rename enum labels arbitrarily; such operations may lack direct DDL support or require planned type/column migrations.

## 13. Detecting Schema Drift

Schema drift can be detected across several sources:

- Migration history.
- `pg_catalog` and `information_schema`.
- Schema dumps.
- Migration tool diffs.
- Configuration management.
- Deployment artifacts.
- Monitoring and extension inventories.

### Inspecting column inventory

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

Compare column names, types, nullability, and defaults. `data_type` alone does not always distinguish domains, enums, arrays, and custom types; inspect `udt_name` or catalogs when needed.

### Inspecting table inventory

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
~~~

### Inspecting indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

### Inspecting constraints

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace NOT IN (
    'pg_catalog'::regnamespace,
    'information_schema'::regnamespace
)
ORDER BY conrelid::regclass::text, conname;
~~~

### Schema dumps

Use `pg_dump --schema-only` with matching client tools to capture a schema snapshot:

~~~bash
pg_dump --schema-only --no-owner --no-privileges -d appdb > schema.sql
~~~

For accurate comparisons, normalize irrelevant noise such as owners, grants, object ordering, version-specific formatting, and environment-specific settings. Avoid over-normalizing away critical differences.

## 14. Schema Drift Is More Than Tables and Columns

Two schemas can look identical at the table level yet diverge on:

- Index definitions, predicates, included columns, and validity.
- Constraint definitions and validation states.
- Sequence options and current values.
- Column identity, generated, and default behaviors.
- Trigger definitions and enabled states.
- Function/procedure source, owner, `SECURITY DEFINER`, and `search_path`.
- View and materialized view definitions.
- Type, domain, and enum definitions.
- Collations and providers.
- Partition bounds and attachment states.
- RLS enable/force flags and policies.
- Ownership, grants, role memberships, and default privileges.
- Extension names and versions.
- Tablespaces and storage parameters.
- Event triggers and publication/subscription definitions.

Schema comparisons must state their scope explicitly. Comparing only tables and columns is a structural subset comparison, not full schema equivalence.

## 15. Comparing Schemas Across Environments

A comparison workflow:

1. Identify source/target environments and versions.
2. Capture schema snapshots from both sides.
3. Define scope: database, schema, table, or object class.
4. Normalize intentional environment differences.
5. Compare definitions and security metadata.
6. Group drift into missing, extra, modified, and state mismatch.
7. Classify drift: expected, accidental, unknown.
8. Trace change origin and change records.
9. Choose a repair migration or documented exception.
10. Re-run verification after synchronization.

Never blindly apply every diff from staging to production. Production may hold intentionally distinct data, grants, or environment-specific objects.

### Drift categories

| Type | Example | Remediation |
| --- | --- | --- |
| Missing object | Missing index or column | Verify migration and write a repair migration |
| Extra object | DBA created an index manually | Identify owner/purpose; codify in migration or exception |
| Definition mismatch | Differing type, default, or index predicate | Review data and query impact |
| State mismatch | Invalid index, `NOT VALID` constraint | Complete build or validation |
| Security drift | Differing grants, owner, or RLS | Restore least privilege |
| Version drift | Differing extension or config | Align packages/config per plan |
| Data drift | Backfill missing rows | Reconcile and repair data |

## 16. Why Not Edit the Schema Directly and Ignore Migration History?

Direct SQL hotfixes may be necessary during an outage, yet if left unrecorded, environments will keep diverging.

After a hotfix:

1. Save the exact SQL command and evidence.
2. Record the change/incident ID.
3. Verify database state.
4. Write a matching migration or a repair migration with explicit preconditions.
5. Ensure the migration does not clobber already-applied changes.
6. Roll out to remaining environments in order.
7. Reconcile the migration ledger using the tool's official mechanism if needed.
8. Review checksums and the deployment pipeline.

Never create a "fake" no-op migration just to turn the ledger green when the database has not actually reached the desired state.

## 17. Idempotency and Retry Safety

An idempotent migration can be re-run without causing unintended side effects. However, `IF EXISTS`/`IF NOT EXISTS` alone does not guarantee schema correctness.

Example:

~~~sql
ALTER TABLE public.orders
ADD COLUMN IF NOT EXISTS source_channel text;
~~~

If the column already exists with type `integer` or the wrong default, this command silently skips without fixing the mismatch.

### Verify definitions after IF NOT EXISTS

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

Migrations need clear preconditions and postconditions:

- If the object does not exist: create it.
- If it exists with the exact right definition: treat as satisfied.
- If it exists with a different definition: halt and investigate.
- If it is invalid or partial: route to a dedicated recovery branch.

### Retry-safe data migrations

Conditional backfill example:

~~~sql
UPDATE public.orders
SET source_channel = 'web'
WHERE source_channel IS NULL
  AND created_at < DATE '2026-01-01';
~~~

The `IS NULL` condition avoids rewriting processed rows, though it is only valid if `NULL` truly means "unbackfilled" and `'web'` matches business rules. Never use arbitrary sentinel values if `NULL` carries valid business meaning.

## 18. Migration Locking and Concurrent Execution

Two deployments running the same migration simultaneously can cause:

- Duplicate object errors.
- Deadlocks.
- Ledger race conditions.
- DDL lock contention.
- Data backfills running twice.
- Hard-to-diagnose partial states.

Migration frameworks should use a lock or advisory lock so only one runner executes at a time for a given database/schema.

PostgreSQL advisory locks can coordinate runners:

~~~sql
SELECT pg_advisory_lock(81420, 1);
-- Perform migration orchestration per procedure.
SELECT pg_advisory_unlock(81420, 1);
~~~

These keys are illustrative. Choose a stable key namespace and verify lock ownership and session lifecycles. Session-level advisory locks persist until unlocked or the session closes. Transaction-level advisory locks have different semantics.

Advisory locks do not replace migration ledgers or tool locks; ensure all runners obey the same coordination mechanism.

### Inspecting advisory locks

~~~sql
SELECT
    pid,
    locktype,
    classid,
    objid,
    objsubid,
    granted
FROM pg_locks
WHERE locktype = 'advisory';
~~~

If a runner disconnects, session-level locks are normally released when the session ends. However, never assume migration state rolled back merely because the lock disappeared.

## 19. Lock Timeouts and Migration Timeouts

DDL can wait on locks held by long transactions. Use timeouts so migrations fail fast and remain controllable:

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '15min';
~~~

Values are illustrative. Set them per migration transaction or session policy.

- `lock_timeout`: bounds lock wait time.
- `statement_timeout`: bounds total statement execution time.
- `idle_in_transaction_session_timeout`: bounds idle sessions inside open transactions.

If a lock timeout occurs, the statement cancels. Inspect transaction state and catalogs before retrying.

Never set `statement_timeout` too short for large index builds or backfills. Conversely, never let DDL wait unboundedly in production without a stop condition.

## 20. Expand-Contract: Multi-Version Compatible Rollouts

Expand-contract is a multi-phase schema change strategy allowing old and new applications to run together during transition.

Example: migrating `customer_name` to `display_name`.

### Expand phase

- Add the new nullable column.
- Keep the old column.
- New app reads both or dual-writes per policy.
- Backfill old data in batches.
- Monitor consistency.

### Migrate phase

- Switch application reads to the new column.
- Ensure all writers update the new column.
- Verify parity between old and new data.
- Monitor remaining old application instances.

### Contract phase

- Stop reading/writing the old column.
- Confirm zero dependent consumers remain.
- Drop the old column in a separate change.
- Update schema contracts and the migration ledger.

~~~mermaid
flowchart LR
    A["Expand: add new column"] --> B["Backfill + dual compatibility"]
    B --> C["Migrate app reads/writes"]
    C --> D["Observe old app instances = 0"]
    D --> E["Contract: remove old column"]
~~~

Never drop the old column in the same deployment that adds the new column. Older application versions may still be serving during rolling deployments or inside a rollback window.

## 21. Large Data Backfills in Batches

A full-table `UPDATE` creates long transactions, heavy WAL, long locks, and replication lag. Batching controls load and allows resuming from checkpoints.

Example using an ascending key:

~~~sql
UPDATE public.orders
SET normalized_code = upper(code)
WHERE order_id > 100000
  AND order_id <= 110000
  AND normalized_code IS NULL;
~~~

This uses fixed literal bounds for illustration; production runners should pass key ranges via bind parameters and compute progress from actual updated rows.

Every batch needs:

- Short transactions.
- Explicit batch bounds.
- Updated row counts.
- Checkpoints/progress records.
- Retry policies.
- Throttling when replication lag or latency exceeds thresholds.
- Post-completion reconciliation.

### Why must backfill checkpoints be durable?

If a runner records progress before committing data, a crash can mark a batch complete even though its data rolled back. If recorded after commit non-atomically, a batch may re-run. Design idempotent batches and transactional coordination for safe retries.

One pattern updates both data and migration progress in the same transaction when both live in the same database with no non-transactional operations in between.

## 22. Migration Ledgers and Data Progress

For long migrations, separate migration version tracking from granular progress:

- Migration ledger: whether the migration finished.
- Backfill progress table: which batch/key range has been processed.
- Reconciliation results: remaining missing or mismatched rows.
- Deployment state: whether application versions have switched.

Example progress table:

~~~sql
CREATE TABLE IF NOT EXISTS ops_migration_progress (
    migration_key text PRIMARY KEY,
    last_processed_id bigint,
    rows_processed bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);
~~~

Do not replace a framework's native ledger with this example table if your tool already manages progress. Restrict access to ops tables from ordinary application roles.

## 23. Handling Partially Executed Migrations

Suppose a migration has three steps:

1. Add column.
2. Backfill data.
3. Add constraint.

If step 3 fails, inspect:

- Does the column exist with the right definition?
- Did the backfill run completely or partially?
- Are there rows violating the constraint?
- Do triggers or defaults generate new data?
- What status does the migration ledger show?
- Which column is the application currently reading and writing?

### Recovery branches

- Column right, backfill complete, constraint missing: run the constraint creation/validation step separately after cleaning data.
- Column right, backfill partial: resume from progress markers or re-run idempotent batches.
- Column exists with wrong type/default: stop, assess data conversion, and write a repair migration.
- Ledger says success while constraint is missing: schema drift; write a repair migration with preconditions.
- Unclear how data mutated: pause writes/traffic per incident plan, take snapshots, and escalate before altering state.

Never drop the column and restart from scratch if applications or new data already depend on it.

## 24. Rollback or Forward-Fix?

Choose based on reversibility and whether new data was produced.

| Situation | Typical approach to consider |
| --- | --- |
| Transactional migration fails before commit | Roll back transaction and fix migration |
| DDL committed, no apps depend on it yet | Reversible via verified inverse migration |
| Backfill already mutated data | Forward-fix or restore/reconcile; never assume trivial reversal |
| Invalid concurrent index | Drop/rebuild per runbook |
| `NOT VALID` constraint | Remediate data and validate, or handle constraint per policy |
| New app running against old schema | Roll forward schema if compatible, or roll back app per plan |
| New schema running against old app | Use expand-compatible design or controlled app/DB rollback |
| Target already accepted new writes | Requires reverse sync/reconciliation before reverting to source |
| Unbounded data corruption or loss | Stop changes, preserve evidence, recover via backup/PITR per incident command |

### A rollback migration is not always a simple "down script"

A down migration can:

- Drop a column containing new data.
- Discard backfilled data.
- Fail to restore original values accurately.
- Be unable to drop an enum value.
- Fail to invert external side effects.
- Introduce heavy locks or downtime.

Before running a down migration, verify data-loss risks and compatibility.

## 25. When to Use a Forward-Fix?

A forward-fix is usually preferable when:

- A migration partially committed and new data depends on it.
- Reverse DDL risks losing data.
- New applications already wrote data under the new schema.
- Restoring a backup would discard valid subsequent transactions.
- An additive migration can move the schema into the desired state.

A forward-fix should have its own version/ID, preconditions, repair steps, and postconditions. Never edit an already-deployed migration file to "rewrite history," as checksums and reproducibility will break.

## 26. Schema Drift from Manual Operations

During an incident, a DBA may add an index or column directly to restore service. That can be justified in emergencies, provided the change is subsequently captured in the source of truth.

Workflow:

1. Record the exact SQL executed.
2. Capture catalog state after the hotfix.
3. Document the reason and change/incident ID.
4. Diff against the migration repository.
5. Write a repair migration with preconditions.
6. Ensure the migration accepts the already-valid object or halts if definitions differ.
7. Test on a clone/staging environment.
8. Deploy to remaining drifted environments.
9. Verify schema and ledger.
10. Document an exception if a production object intentionally stays outside migration ownership.

Never re-run manual DDL across environments without checking current differences first.

## 27. Investigating Migration Checksum Mismatches

A migration checksum mismatch usually indicates a migration file changed after the tool recorded its execution, or environments received different artifacts.

Causes:

- A developer edited an old migration.
- Build artifacts differ from deployed artifacts.
- File encoding or line endings changed.
- Branch merges altered file contents.
- Tool versions or checksum algorithms changed via configuration.

Remediation:

1. Compare the deployed artifact against repository history.
2. Diff migration file contents.
3. Identify which migration actually ran in each environment.
4. Never edit checksums directly in the database.
5. Create a new migration for intended changes.
6. Use the tool's official repair/baseline command only after verifying schema state and obtaining policy approval.

A checksum mismatch does not prove the schema itself is broken, yet it signals deployment history is no longer reproducible.

## 28. Managing Application Versions During Intermediate Schema States

Rolling deployments can result in multiple application versions accessing the database simultaneously.

Classify compatibility:

| Application version | Old schema | Expanded schema | Contracted schema |
| --- | --- | --- | --- |
| Old app | Supported | Must stay compatible | May error |
| Bridge app | Possibly supported | Supported | Should not run post-contract |
| New app | Possibly supported if designed | Supported | Supported |

Before contracting:

- Confirm all app instances are upgraded.
- Confirm workers, cron jobs, and ETL are upgraded.
- Check scripts and ad-hoc consumers.
- Check prepared statements and long-lived sessions.
- Confirm the rollback window has elapsed.
- Confirm metrics show zero access to old columns/objects.

Never rely solely on the deployment controller's version tag; stale processes or un-restarted scheduled jobs may still exist.

## 29. Migrations and Connection Pools

Connection pools maintain long-lived sessions holding prepared statements, cached metadata, or transaction state.

After a schema migration:

- Verify apps can prepare new statements.
- Check whether old prepared statements error due to column/type changes.
- Review pool connection recycling policies.
- Verify no sessions sit `idle in transaction`.
- Do not abruptly terminate all connections without a plan.
- If pool restarts are needed, coordinate drain/reconnect to avoid connection storms.

Certain schema changes trigger invalidation/replanning of prepared statements per PostgreSQL/driver behavior. Check application logs and test with your exact driver version.

## 30. Migrations and Replication

DDL on the primary normally flows via physical WAL streaming to physical standbys. Logical replication has different constraints: DDL is not automatically replicated like row changes in many setups.

After migrating:

- Check physical standby replay and lag.
- Verify logical subscriber schema parity.
- Inspect publication/subscription errors.
- Check table sync states.
- Synchronize sequences separately.
- Monitor replication slots and WAL retention.
- Confirm failover candidates hold the right schema and data state.

Never promote a lagging standby or one lacking required schema changes without evaluating RPO and impact.

## 31. Using Advisory Locks to Prevent Concurrent Migrations

Migration frameworks should handle locking. If building a custom runner, use PostgreSQL advisory locks.

Session-level example:

~~~sql
SELECT pg_advisory_lock(91002, 1);
-- Runner inspects ledger and executes migrations.
SELECT pg_advisory_unlock(91002, 1);
~~~

Transaction-level example:

~~~sql
BEGIN;
SELECT pg_advisory_xact_lock(91002, 1);
-- Transactional migration steps.
COMMIT;
~~~

Choose the right lock scope:

- Session-level locks persist until explicitly unlocked or session end.
- Transaction-level locks release automatically when the transaction ends.
- All runners must share the same key convention.
- Never allow operators to run manual migrations outside the lock policy.

Advisory locks alone do not guarantee transaction safety, migration ordering, or schema correctness.

## 32. Migration Preconditions and Postconditions

A reliable migration verifies state before changing anything and confirms the outcome afterward.

Example precondition:

~~~sql
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Results must match expected pre-migration state.

Postcondition:

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

Check index:

~~~sql
SELECT
    indexrelid::regclass,
    indisvalid,
    indisready,
    pg_get_indexdef(indexrelid)
FROM pg_index
WHERE indexrelid = 'public.orders_created_at_idx'::regclass;
~~~

Check constraints:

~~~sql
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass;
~~~

Preconditions/postconditions do not have to live as SQL inside migration files; they can be tool assertions or deployment gates. What matters is checking state and recording the results.

## 33. Idempotent Data Migrations

Data migrations should be designed for safe retries whenever possible.

Example backfill using a key range and progress table:

~~~sql
BEGIN;

UPDATE public.orders
SET normalized_code = upper(code)
WHERE order_id > 100000
  AND order_id <= 110000
  AND normalized_code IS NULL;

INSERT INTO ops_migration_progress (
    migration_key,
    last_processed_id,
    rows_processed
)
VALUES ('orders-normalized-code-v1', 110000, 10000)
ON CONFLICT (migration_key)
DO UPDATE SET
    last_processed_id = EXCLUDED.last_processed_id,
    rows_processed = ops_migration_progress.rows_processed
                     + EXCLUDED.rows_processed,
    updated_at = now();

COMMIT;
~~~

This is illustrative; `rows_processed` should reflect actual updated rows rather than a hardcoded constant in production. Use `GET DIAGNOSTICS ROW_COUNT` in PL/pgSQL or read the command tag from the runner for exact counts.

Keep the progress update and data update in the same transaction when atomic checkpoints are desired. Otherwise, ensure re-running a batch cannot corrupt data.

## 34. Handling Data Migrations with Side Effects

A migration may fire triggers, insert audit rows, emit notifications, or call external systems. Retries can duplicate side effects.

Before retrying:

- Check which triggers are enabled.
- Check whether functions emit external calls or notifications.
- Check whether outbox/queue records were created.
- Check whether consumers already processed messages.
- Use idempotency keys and deduplication.
- Reconcile external side effects.

Avoid calling external APIs directly inside long migration transactions. Use an outbox or separate workflow to synchronize external systems.

## 35. Recovering Partial Deployments Between Database and Application

A deployment sequence may look like:

1. Expand schema.
2. Deploy new application.
3. Backfill.
4. Switch reads/writes.
5. Contract schema.

If step 2 fails after step 1, an expanded schema is normally designed so the old app still works. You can roll back the application and retain the expanded schema, provided compatibility holds.

If step 4 fails after the new application already wrote data, rolling back the app requires confirming older code understands the newly written data. Otherwise, forward-fix the app/schema or restore/reconcile.

### Recovery matrix

| Database | Application | State | Direction to consider |
| --- | --- | --- | --- |
| Old schema | Old app | Normal | Proceed with deployment plan |
| Expanded schema | Old app | New app not yet deployed | Safe to keep expand, investigate deploy |
| Expanded schema | New app | Bridge phase | Verify dual-read/write |
| Contracted schema | Old app | Incompatible | Halt traffic, roll forward, or recover |
| New schema | Partially deployed app | Mixed versions | Keep compatibility or drain old instances |
| New schema | New app with bugs | Partial cutover | Forward-fix or roll back per data compatibility |

## 36. DDL Lock Impact and Migration Failures

DDL may wait for or require strong locks. Before migrating:

- Check long-running transactions.
- Identify required lock modes.
- Estimate table size.
- Determine rewrite behavior.
- Set a reasonable `lock_timeout`.
- Schedule inside maintenance windows if needed.
- Monitor `pg_stat_activity` and `pg_locks`.
- Define stop conditions when waits exceed thresholds.

Never assume `ALTER TABLE` is always instantaneous. Some operations are metadata-only under specific versions/conditions, whereas others rewrite tables or scan data.

### Monitoring locks

~~~sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 180) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation IS NOT NULL
ORDER BY l.granted, a.pid;
~~~

Interpret results by lock mode and relation. Never terminate a blocker solely because it appears in this query; check owner and business impact.

## 37. Classifying Errors with SQLSTATE and Logs

Useful `SQLSTATE` codes:

| SQLSTATE | Meaning | Investigation direction |
| --- | --- | --- |
| `42P01` | `undefined_table` | Missing object or wrong `search_path` |
| `42703` | `undefined_column` | Unapplied migration or code/schema mismatch |
| `42701` | `duplicate_column` | Column already exists or partial migration |
| `42P07` | `duplicate_table` | Table already exists |
| `42P16` | `invalid_table_definition` | Invalid DDL definition |
| `23505` | `unique_violation` | Duplicate data, index, or constraint |
| `23503` | `foreign_key_violation` | Referential integrity issue |
| `23514` | `check_violation` | Data violates `CHECK` |
| `40P01` | `deadlock_detected` | Transaction lock cycle |
| `55P03` | `lock_not_available` | Lock could not be acquired |
| `57014` | `query_canceled` | Statement canceled or timed out |
| `53100` | `disk_full` | Filesystem/storage exhaustion |
| `42501` | `insufficient_privilege` | Role lacks privileges |
| `55006` | `object_in_use` | Object currently in use |

`SQLSTATE` is a much more reliable classifier than parsing message text. Still archive message, detail, and context to pinpoint the exact object and statement.

## 38. Checking Disk, WAL, and Temp Files When Migrations Fail

Migrations can fail due to storage exhaustion. Check:

~~~sql
SELECT
    pg_size_pretty(pg_database_size(current_database())) AS current_database_size;
~~~

Check temp usage:

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_written
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

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

Verify filesystem free space at the OS/storage layer for data, WAL, temp, logs, and backup volumes. Never delete files inside `pg_wal` via filesystem commands to free space; manage replication slots, archiving, and WAL retention per runbook.

## 39. Migrations and Extension Upgrades

Extension upgrades can fail because:

- The extension package for the target major version is not installed.
- Shared libraries are incompatible.
- Upgrade SQL scripts are missing or lack a direct upgrade path.
- Dependency extensions have not been upgraded.
- Object ownership or permissions are insufficient.
- Extension updates partially execute or have special transaction behavior.

Check installed extensions:

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
ORDER BY extname;
~~~

Check available versions:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Never drop/recreate an extension as a "quick fix" if it owns objects or stores metadata. Follow the extension's official upgrade path and backup/restore plan.

## 40. Migrations Across Multiple Databases or Tenants

An application may span multiple databases, schema-per-tenant setups, or dedicated tenant databases. A migration might succeed on one cohort and fail on another.

Maintain a deployment inventory:

| Tenant/DB | Current version | Target version | Status | Last result |
| --- | --- | --- | --- | --- |
| `tenant_a` | 041 | 042 | complete | success |
| `tenant_b` | 041 | 042 | failed | lock timeout |
| `tenant_c` | 041 | 042 | pending | not started |

Pull statuses from ledgers/tools and verification queries, not merely from whether the deployment controller dispatched the command.

Workflow:

1. Freeze or bound migration concurrency per capacity.
2. Record the target list.
3. Roll out in tenant batches.
4. Persist per-database outcomes.
5. Halt batching if errors exceed thresholds.
6. Classify tenants as complete, partial, or pending.
7. Recover per tenant state.
8. Enable features globally only when coverage meets acceptance criteria.

Never assume a migration succeeding on the first tenant guarantees identical behavior on all others.

## 41. Safe Repair Migrations

A repair migration is a new migration moving the schema/data from its current actual state to the desired state.

A repair migration should include:

- A new ID/version.
- Description of the drift being fixed.
- Preconditions proving starting state.
- Repair operations.
- Postconditions.
- Lock and downtime impact.
- Data loss implications.
- Retry and idempotency policy.
- Evidence and owner.
- Rollback/forward-fix plan.

For instance, if an index with the exact right definition already exists while the migration ledger missed it, the repair procedure verifies definition and validity first, then applies the tool's baseline/repair workflow per policy. Never rely solely on `CREATE INDEX IF NOT EXISTS`, since an index with the same name may have a different definition.

## 42. Schema Drift Investigation Workflow

1. **Freeze changes:** pause migration runners/deployments that could worsen drift.
2. **Identify:** pinpoint database, schema, object, and application versions.
3. **Collect:** capture migration ledger, schema snapshots, logs, and deployment artifacts.
4. **Compare:** diff catalogs against the source of truth.
5. **Classify:** missing, extra, modified, invalid state, security drift, or data drift.
6. **Trace:** locate change records, operator, commit, and timestamp.
7. **Decide:** keep, remove, modify, or write a repair migration.
8. **Test:** run repair on staging/clone matching the drifted state.
9. **Apply:** execute per change plan.
10. **Verify:** re-verify schema, data, and security.
11. **Reconcile ledger:** use the tool's official mechanism.
12. **Prevent:** lock down manual DDL or document controlled exceptions.

## 43. Runbook: Handling a Failed Migration

### Phase A: Contain

- Stop the migration runner.
- Stop dependent deployment steps.
- Keep applications on compatible versions.
- Do not re-run the script.
- Preserve logs and outputs.

### Phase B: Determine state

- Confirm target database/cluster.
- Identify active sessions and transactions.
- Read the migration ledger.
- Inspect catalog objects.
- Inspect backfilled data and progress.
- Check index and constraint validity.
- Check running application versions.
- Check replication and backups.

### Phase C: Choose recovery

- Roll back the transaction if uncommitted.
- Retry the exact step if idempotent and preconditions pass.
- Drop/rebuild invalid indexes per plan.
- Resume backfills from progress checkpoints.
- Forward-fix schema/data if dependencies already exist.
- Restore/PITR if data integrity cannot be assured.
- Escalate if state remains unclear.

### Phase D: Verify and close

- Schema matches source of truth.
- Data reconciliation passes.
- Ledger accurately reflects state.
- App and worker versions are compatible.
- Replication and backups are healthy.
- Metrics and logs are stable.
- Evidence and deviations are archived.
- Reviewer sign-off obtained.

## 44. Decision Record Template

When choosing rollback vs. forward-fix, record:

~~~yaml
change_id: CHG-2026-0579
migration_id: V042__add_order_channel
environment: production
database: sales
failure_at: "step 3 - validate constraint"
ledger_state: "failed"
observed_schema_state:
  column_exists: true
  column_type: text
  backfill_complete: true
  constraint_exists: true
  constraint_validated: false
observed_application_state:
  old_instances: 0
  new_instances: 24
decision: "forward_fix"
reason: "new application instances already write the new column"
recovery_action: "repair invalid rows, then validate constraint"
verification:
  data_check: pending
  constraint_validation: pending
  application_smoke_test: pending
owner: database_operations
~~~

This is an illustrative template. Never put credentials, customer data, or sensitive hostnames into records. Update the decision record with actual outcomes rather than pre-marking success.

## 45. Evidence to Preserve

An evidence package for migration recovery should include:

- Change/incident ID.
- Migration ID/version and checksum.
- Source control commit/build artifact.
- PostgreSQL version and cluster identity.
- Migration tool/version.
- Command, timestamp, and operator.
- Error `SQLSTATE`, message, and context.
- Migration ledger before/after.
- Catalog snapshots before/after.
- Data progress and reconciliation results.
- Index and constraint states.
- Role/permission states if relevant.
- Application versions and deployment status.
- Replication and backup status.
- Recovery decision and approvals.
- Rollback/forward-fix outputs.
- Post-checks and application smoke tests.
- Deviations and reviewer sign-off.

Evidence must include timestamps with timezones, target environments, and sources. Redact passwords, tokens, private keys, and sensitive query parameters.

## 46. Preventing Future Schema Drift

Preventive controls:

- Manage all schema changes via version-controlled migrations.
- Block manual DDL using role separation, except under break-glass procedures.
- Record hotfixes and convert them into repair migrations.
- Run migrations in deployment pipelines with a single-runner lock.
- Add schema diffs to CI/staging gates.
- Test migrations from realistic production versions, not just empty databases.
- Test upgrade paths across all supported versions.
- Use expand-contract for rolling deployments.
- Assign clear migration ownership.
- Monitor checksums and history.
- Periodically diff schemas across environments.
- Maintain regular backup/restore testing.
- Alert on migration failures and critical schema drift.

### CI migration testing

A pipeline can:

1. Provision a database from a baseline version.
2. Restore fixtures or representative datasets.
3. Execute all pending migrations.
4. Run schema assertions.
5. Run data assertions.
6. Run application integration tests.
7. Verify migration runtime and lock behavior.
8. Test rollback or recovery branches where supported.

Testing from an empty database is insufficient if production sits at version N-3 and migrations are only tested from the latest baseline.

## 47. Common Mistakes

1. **Retrying a migration immediately after a timeout**, when the server may have committed partially or completely.
2. **Treating the migration ledger as the sole source of truth**, ignoring catalogs and actual data.
3. **Editing an already-deployed migration**, breaking checksums and reproducibility.
4. **Running manual `UPDATE`/`DELETE` on the ledger to clear errors**, causing metadata to diverge from actual schema state.
5. **Assuming all DDL is transactional**, overlooking `CREATE INDEX CONCURRENTLY` and commands prohibited in transaction blocks.
6. **Failing to check index validity**, leaving invalid indexes behind.
7. **Dropping an invalid index immediately**, without checking active sessions, builds, or dependencies.
8. **Treating `NOT VALID` constraints as complete**, ignoring unvalidated historical data.
9. **Adding an enum value and using it immediately in the same transaction**, ignoring version/commit boundaries.
10. **Using `IF NOT EXISTS` to mask drift**, without verifying actual object definitions.
11. **Running two migration runners simultaneously**, causing races, duplicate errors, and lock conflicts.
12. **Omitting `lock_timeout`**, letting DDL wait unboundedly and disrupt live traffic.
13. **Terminating blockers without checking owner and impact**, potentially rolling back critical business transactions.
14. **Backfilling an entire table in one transaction**, generating heavy WAL, bloat, replication lag, and lock pressure.
15. **Recording progress before committing data**, causing skipped rows after crashes.
16. **Retrying data migrations with side effects**, triggering duplicate events or external actions.
17. **Dropping an old column immediately during a rolling deployment**, breaking older app instances.
18. **Rolling back the application after contracting the schema**, leaving code incompatible with the database.
19. **Switching back to the source after the target received new writes**, losing newly written data.
20. **Comparing schemas solely by tables and columns**, missing grants, triggers, indexes, constraints, and RLS.
21. **Applying an entire schema diff from staging to production**, overwriting intentional differences.
22. **Failing to check replication and logical subscriptions**, leaving downstream schemas/data out of sync.
23. **Leaving hotfixes out of the migration repository**, creating recurring drift.
24. **Failing to keep evidence and decision records**, leaving incident responders blind to state.
25. **Closing a deployment because the ledger is green without testing the app**, missing runtime failures.
26. **Testing only on empty databases instead of production baselines**.
27. **Failing to distinguish partial state from unknown state**, taking action without sufficient evidence.

## 48. Practice Exercises with Answers

### Exercise 1. What is a migration failure?

**Answer:** When a migration fails to complete as planned; the database may be unchanged, partially changed, or fully changed while the client missed the result.

### Exercise 2. What is schema drift?

**Answer:** When the actual database schema differs from what the migration repository or reference environment expects.

### Exercise 3. What is a partial deployment?

**Answer:** When databases, applications, workers, or environments only partially upgraded and have not yet reached a mutually compatible final state.

### Exercise 4. Why not retry immediately after a client timeout?

**Answer:** The server may have committed the command before the response was lost; retrying can cause duplicates or conflicts.

### Exercise 5. Is the migration ledger the sole source of truth?

**Answer:** No. You must cross-check the ledger against catalogs, data, and application state.

### Exercise 6. Which table does Flyway usually use to store history?

**Answer:** Usually `flyway_schema_history`, depending on configuration and tool version.

### Exercise 7. Why shouldn't the migration ledger be updated manually?

**Answer:** It can make history, checksums, and status diverge from actual schema state; use official repair/baseline procedures after verification.

### Exercise 8. Name a DDL command that normally cannot run inside a transaction block.

**Answer:** `CREATE INDEX CONCURRENTLY`.

### Exercise 9. What can a failed CREATE INDEX CONCURRENTLY leave behind?

**Answer:** An invalid or not-ready index in the catalog.

### Exercise 10. Which catalog inspects index validity?

**Answer:** `pg_index`, specifically `indisvalid` and `indisready`.

### Exercise 11. What does a NOT VALID constraint mean?

**Answer:** The constraint exists without having validated all existing data; enforcement applies to new writes per constraint semantics.

### Exercise 12. How do you complete validation?

~~~sql
ALTER TABLE public.orders
VALIDATE CONSTRAINT orders_amount_nonnegative;
~~~

**Answer:** After fixing violating data, run `VALIDATE CONSTRAINT` and verify `convalidated = true`.

### Exercise 13. Why must you commit before using a newly added enum value?

**Answer:** In relevant versions and transaction contexts, the new enum value is unavailable until the transaction adding it commits.

### Exercise 14. Does IF NOT EXISTS guarantee an object has the right definition?

**Answer:** No. It only avoids existence errors; you must still verify type, default, owner, and definition.

### Exercise 15. What kinds of schema drift exist?

**Answer:** Missing, extra, definition mismatch, invalid state, security drift, version drift, and data drift.

### Exercise 16. Why is a migration lock needed?

**Answer:** To prevent multiple runners from executing the same migration simultaneously and causing races or partial states.

### Exercise 17. How does lock_timeout differ from statement_timeout?

**Answer:** `lock_timeout` bounds lock wait time; `statement_timeout` bounds total statement runtime.

### Exercise 18. What are the main phases of expand-contract?

**Answer:** Expand schema compatibly, migrate applications/data, then contract/drop old schema once no consumers remain.

### Exercise 19. Why should large backfills be batched?

**Answer:** To reduce transaction duration, WAL bursts, and replication lag, while creating checkpoints for retries and resumption.

### Exercise 20. When should progress markers commit in the same transaction as data batches?

**Answer:** When you want to guarantee data updates and progress checkpoints are recorded atomically in one database transaction.

### Exercise 21. When is a forward-fix preferable to a rollback?

**Answer:** When new data already depends on the new schema or a rollback risks data loss or irreversible side effects.

### Exercise 22. Why not edit an already-deployed migration file?

**Answer:** It breaks checksums and makes deployment history non-reproducible; create a new migration instead.

### Exercise 23. When the target has already accepted new writes, is switching endpoints back to source safe?

**Answer:** Not by default; reverse synchronization/reconciliation or a recovery strategy is required to avoid losing writes.

### Exercise 24. Why must schema comparisons check grants and RLS?

**Answer:** Two schemas with identical table definitions can still have completely different security behaviors.

### Exercise 25. What is pg_blocking_pids used for?

**Answer:** Finding PIDs blocking a backend, helping diagnose migration lock waits.

### Exercise 26. When should a backend be terminated?

**Answer:** Only after verifying PID/session, owner, transaction state, and impact per runbook and approvals.

### Exercise 27. Does logical replication automatically replicate DDL?

**Answer:** Not by default; schema changes must be deployed separately on subscribers.

### Exercise 28. Why inspect running application versions before a contract migration?

**Answer:** Old instances or old workers may still access columns or objects slated for deletion.

### Exercise 29. What must a repair migration contain?

**Answer:** A new ID, preconditions, repair steps, postconditions, retry policy, risk analysis, and evidence.

### Exercise 30. When can a migration incident be closed?

**Answer:** Once schema, data, ledger, apps, replication, and backups meet acceptance criteria, evidence is complete, and reviewer sign-off is granted.

## 49. Checklist for Handling Failed Migrations and Schema Drift

### Containment and state determination

- [ ] Halted subsequent migrations and deployments.
- [ ] Verified exact cluster, database, and environment.
- [ ] Recorded migration ID, checksum, tool version, and timestamp.
- [ ] Saved error output, `SQLSTATE`, and server logs.
- [ ] Checked for still-running sessions or transactions.
- [ ] Determined whether DDL was transactional or non-transactional.
- [ ] Read the migration ledger.
- [ ] Inspected objects and definitions in catalogs.
- [ ] Checked data backfill/progress state.
- [ ] Identified active application versions and writers.

### Recovery decision

- [ ] Classified state: unchanged, partial, committed, drift, or unknown.
- [ ] Checked index validity/readiness state.
- [ ] Checked constraint validation state.
- [ ] Checked sequences and data integrity.
- [ ] Assessed rollback/data-loss risks.
- [ ] Chose retry, resume, rollback, forward-fix, or restore.
- [ ] Identified owner and approver.
- [ ] Tested repair on staging/clone if appropriate.
- [ ] Ensured migration runner locking and retry safety.

### Verification and closure

- [ ] Schema matches source of truth.
- [ ] Data reconciliation passes.
- [ ] Migration ledger accurately reflects state.
- [ ] Application and worker versions are compatible.
- [ ] Replication, subscriptions, and slots are stable.
- [ ] Backups and WAL archiving continue normally.
- [ ] Smoke tests pass.
- [ ] Metrics and error rates are within thresholds.
- [ ] Evidence is archived and redacted.
- [ ] Repair migration is versioned.
- [ ] Exceptions/deviations are documented.
- [ ] Reviewer sign-off and change closure completed.

## 50. Official PostgreSQL Documentation

Read documentation matching your deployed major version:

- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — altering tables, constraints, and validation.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index creation and `CONCURRENTLY`.
- [DROP INDEX](https://www.postgresql.org/docs/current/sql-dropindex.html) — dropping indexes and `CONCURRENTLY`.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes and deadlocks.
- [Lock Management](https://www.postgresql.org/docs/current/runtime-config-locks.html) — `deadlock_timeout` and lock settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_activity`, `pg_locks`, and statistics views.
- [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html) — schema metadata and object states.
- [Information Schema](https://www.postgresql.org/docs/current/information-schema.html) — standard metadata for columns, tables, and grants.
- [ALTER TYPE](https://www.postgresql.org/docs/current/sql-altertype.html) — enum and type changes.
- [Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html) — transaction boundaries and rollbacks.
- [Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) — application-defined locking.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — creating schema/data snapshots.
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — restoring archives.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — recovery if a migration corrupts data.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — schema/DDL and replication behavior.
- [SQLSTATE Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — PostgreSQL error classification.

Catalog column names, DDL behavior, and command options can change across major versions. Consult documentation for your running server and specific migration tool before applying runbooks.

## 51. Summary

**When a migration fails, actual database state determines the recovery path.** Migration ledgers, command outputs, and application deployment records must all be reconciled against PostgreSQL catalogs and actual data before retrying or rolling back.

1. **Migration failure, schema drift, and partial deployment are three distinct conditions.** Identify the exact incident type before acting.
2. **Stop further steps and verify state.** Client timeouts do not prove the server rolled back.
3. **Ledgers do not replace catalog and data checks.** Both migration history and database state must be inspected.
4. **Not all DDL is transactional.** `CREATE INDEX CONCURRENTLY` and special commands can leave partial states.
5. **Check index validity and constraint validation.** An object existing does not mean it is ready or valid.
6. **`IF NOT EXISTS` does not fix definition mismatches.** Verify explicit preconditions and postconditions.
7. **Use migration locks and timeouts.** Prevent competing runners and bound lock waits.
8. **Expand-contract keeps compatibility across application versions.** Contract only after zero old consumers remain.
9. **Large backfills require batching, progress checkpoints, and retry-safe logic.**
10. **Rollbacks are not always safe.** New data, external side effects, and partial cutovers may require a forward-fix or restore.
11. **Repair migrations must be new changes with preconditions and evidence.** Never rewrite deployed migration history.
12. **Schema drift includes security and object state.** Check grants, RLS, triggers, indexes, constraints, and extension versions.
13. **Close an incident only after schema, data, ledger, applications, replication, and backups are verified.**

A reliable recovery process does not try to force a migration to re-run as fast as possible. It determines exactly what happened, preserves evidence, selects an option suited to current data, and returns both database and application to a verifiably consistent state.
