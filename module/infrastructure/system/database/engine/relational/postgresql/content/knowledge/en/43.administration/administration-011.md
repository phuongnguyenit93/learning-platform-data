# Building Runbooks and Post-Operation Verification Evidence in PostgreSQL

PostgreSQL administration does not end when a SQL command returns success. After operations such as changing configuration, creating roles, running migrations, restoring backups, vacuuming large tables, or switching primaries, operators must prove the system reached the intended state and related services remain healthy.

A **runbook** is an operational document guiding a procedure in clear sequential order. It specifies starting preconditions, owners, commands to execute, evidence to preserve, success criteria, stop conditions, rollback plans, and communication procedures.

**Post-operation evidence** consists of verifiable artifacts—such as SQL output, system catalogs, server logs, monitoring snapshots, backup metadata, checksums, application health checks, and change records. Evidence must be tied to the exact environment, timestamp, target object, and operator.

A solid runbook lets different engineers execute the same procedure consistently, reduces reliance on personal memory, and shortens investigation time when outcomes diverge from expectations.

~~~mermaid
flowchart TD
    A["Change request / incident"] --> B["Runbook and scope"]
    B --> C["Pre-check: initial state"]
    C --> D{"Conditions met?"}
    D -->|"No"| X["Halt / escalation"]
    D -->|"Yes"| E["Execute step by step"]
    E --> F["Collect evidence"]
    F --> G{"Post-check passed?"}
    G -->|"No"| H["Rollback / recovery"]
    H --> I["Post-rollback check"]
    G -->|"Yes"| J["Verify and close change"]
    I --> K["Log incident / handoff"]
    J --> L["Archive evidence and update runbook"]
~~~

This lesson belongs to the **Administration** chapter of the **Database Engine Relational PostgreSQL** module. It covers how to design runbooks, assign responsibilities, enforce change control, preserve evidence, verify outcomes, handle rollbacks, manage escalation, and walk through common PostgreSQL operational scenarios.

## 1. Learning Objectives

After this lesson, you can:

1. Explain what a runbook is and why it is essential in PostgreSQL administration.
2. Distinguish between runbooks, checklists, SOPs, change records, and incident reports.
3. Define scope, objectives, and risks for an operation.
4. Write preconditions, execution steps, decision gates, and postconditions.
5. Assign executors, approvers, and verifiers.
6. Capture pre-operation state as a baseline.
7. Select appropriate evidence from SQL, catalogs, logs, metrics, and the OS.
8. Verify completeness, integrity, and traceability of evidence.
9. Build rollback and recovery plans with explicit triggers.
10. Design runbooks for backups, restores, migrations, roles, vacuuming, configuration, and failover.
11. Validate databases and applications post-operation.
12. Record outcomes, deviations, and final decisions.
13. Version-control runbooks and rehearse them periodically.
14. Avoid operational failures caused by unguarded commands or incomplete evidence.

## 2. Runbooks, Checklists, and Change Records

Operational documents are interrelated yet serve distinct purposes.

| Document | Purpose | Example |
| --- | --- | --- |
| Runbook | End-to-end procedural guide | Primary switchover, backup restore |
| Checklist | Confirms required conditions or steps completed | Pre-migration backup verification |
| SOP | Organization-wide standard operating procedure | Role and privilege management policy |
| Change record | Tracks a specific change, timing, and approvals | Production PostgreSQL upgrade |
| Incident report | Records an incident, impact, root cause, and fix | Primary connection loss |
| Evidence package | Collection of artifacts proving state and results | SQL output, logs, metrics, checksums |

A runbook describes how to execute a class of work. A change record tracks one specific execution. An evidence package preserves the proof from that specific run.

A runbook can be reused many times, whereas evidence must belong to a single run with an explicit timestamp and environment.

## 3. Runbook Design Principles

A runbook must satisfy these principles:

**Executable:** Every step states who performs it, where, with what privileges, and using which exact command.

**Verifiable:** Every critical step includes an expected result and an evidence source.

**Stop-gated:** When preconditions fail, results diverge from expectations, or risks cross thresholds, the runbook states clearly where to stop.

**Recoverable:** Defines concrete rollback, forward-fix, or restore/recovery steps—never vague phrases like "roll back if it fails".

**Scoped:** Lists affected databases, clusters, schemas, tables, roles, hosts, environments, and objects.

**Version-aware:** Notes PostgreSQL major version, OS, extensions, and tool versions whenever differences affect commands.

**Handover-ready:** Another engineer can read it and continue execution without relying on the author's memory.

**Security-controlled:** Never stores passwords, tokens, private keys, or connection strings containing secrets inside runbooks or evidence.

## 4. Standard Runbook Structure

A practical runbook template should include:

1. Metadata and purpose.
2. Scope and affected systems.
3. Triggers and priority.
4. Roles and responsibilities.
5. Preconditions.
6. Risks and expected impact.
7. Backup/restore readiness.
8. Execution steps.
9. Expected results and evidence.
10. Decision gates.
11. Rollback/recovery.
12. Post-operation verification.
13. Communication and escalation.
14. Closure criteria.
15. Revision history.

### Metadata Example

~~~yaml
runbook_id: RB-DB-014
title: PostgreSQL schema migration
owner: Database Operations
service: orders-db
environment: production
postgres_major_version: "16"
risk_level: high
estimated_duration: "30 minutes"
last_reviewed: "2026-10-01"
review_interval: "6 months"
approver_role: change_manager
operator_role: database_operator
verifier_role: application_owner
~~~

Metadata is illustrative. Never place real hostnames/IPs, credentials, or confidential data in broadly shared documents.

## 5. Defining Scope and Objectives

Before writing commands, answer:

- Which cluster and database are affected?
- Primary or standby?
- Which schemas, tables, indexes, or roles?
- Which applications and services depend on them?
- Does the operation require downtime?
- Does the change alter data or access privileges?
- Can the operation be safely re-run?
- What is the rollback scope?

Example vague objective:

> Optimize the orders table.

Verifiable objective:

> Create an index concurrently on `orders(created_at, status)` in database `sales` without holding long write locks; confirm the index is valid, usable by query plans where appropriate, and causes no error-rate spike or replication lag above threshold during a 15-minute observation window.

The more concrete the objective, the clearer the required evidence and exit criteria.

## 6. Triggers and Starting Conditions

A runbook must state clearly when it applies.

Examples:

- Change is approved.
- Latest backup succeeded and restore testing meets policy.
- Replication lag is within thresholds.
- No conflicting maintenance is underway.
- Disk has sufficient headroom.
- Operator and verifier are available.
- Application owner confirmed the maintenance window.
- Rollback/recovery path is prepared.

For incident runbooks, triggers may be specific alerts such as connection failures, disk pressure, replication failures, or database unavailability.

Never use a routine maintenance runbook for an incident with indeterminate data state unless the procedure explicitly covers that scenario.

## 7. Roles and Responsibilities

Common roles:

| Role | Responsibility |
| --- | --- |
| Requester | States the business need and intended impact |
| Change owner | Accountable for overall change execution |
| Operator | Executes commands per the runbook |
| Approver | Reviews and approves changes per policy |
| Verifier | Independently verifies outcomes |
| Application owner | Confirms application behavior |
| Incident commander | Coordinates response during incidents |
| Security/Compliance | Reviews privileges, auditing, and sensitive data |

For high-risk operations, separate the executor and the verifier. The person running commands should never self-certify success solely because commands exited 0.

Runbooks should name roles rather than individual people so documents do not quickly go stale. Individual execution change records capture the specific people involved.

## 8. Preconditions: Pre-Operation Checks

Pre-checks verify the environment is safe enough to begin.

Common check categories:

### Database Identity and Version

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    version() AS server_version;
~~~

Combine with inventory/cluster managers to confirm whether the node is primary or standby. Never rely on hostname alone if an endpoint can route to multiple nodes.

### Roles and Privileges

~~~sql
SELECT
    rolname,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolcanlogin
FROM pg_roles
WHERE rolname = current_user;
~~~

You do not need to dump all role attributes into every evidence package. Record only privileges relevant to the operation.

### Database Size and Disk

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
~~~

Filesystem capacity must be verified at the OS/storage layer; SQL database sizes exclude WAL, archives, logs, and backup volumes.

### Active Sessions and Transactions

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;
~~~

Check for long-running transactions, `idle in transaction` sessions, lock waits, and maintenance jobs before any task needing exclusive locks or restarts.

### Replication State

On the primary:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

On a standby:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
~~~

Run only queries matching the cluster topology. A standalone database having no standbys is valid; record the topology instead of treating zero rows as an error.

## 9. Pre-Operation Baselines

A baseline is the reference state used for post-change comparison.

Depending on the task, a baseline can include:

- Database/cluster identity and PostgreSQL version.
- Current primary/standby role.
- Database, table, and index sizes.
- Active sessions and long transactions.
- Replication lag.
- Free disk space.
- CPU, memory, and I/O utilization.
- Query latency and transaction throughput.
- Error rates.
- Checkpoint and WAL counters.
- Backup status and restore points.
- Application health checks.

### Capturing Comparable Baselines

PostgreSQL counters generally accumulate since the last stats reset or server start. For valid comparisons, save the timestamp, `stats_reset`, and value at time `t1`; sample again at `t2` and compute the delta.

Never compare two counters if stats reset between samples. Never take a single post-operation snapshot and try to infer the prior state.

## 10. Every Execution Step Must Have an Expected Result

A step reading merely "run ALTER TABLE" is insufficient.

Good template:

| Field | Content |
| --- | --- |
| Step | 04 |
| Actor | Database operator |
| Target | `sales.public.orders` |
| Action | Add nullable column |
| Command | `ALTER TABLE ... ADD COLUMN ...` |
| Expected result | Command succeeds; column exists with expected type and default |
| Evidence | SQL output and catalog query |
| Stop condition | Lock wait exceeds threshold or session is blocked |
| Recovery | Evaluate DDL state; run forward-fix or rollback as feasible |

Each major step should pair a command with a verification query. If a command is non-idempotent, explicitly forbid re-running it until current state is verified.

## 11. What Is Evidence?

Evidence is verifiable data proving a specific assertion.

Examples:

| Evidence | What It Proves |
| --- | --- |
| SQL command output | The command returned a result |
| Catalog query | Object or configuration exists with expected properties |
| Server logs | PostgreSQL recorded events or errors |
| Monitoring snapshot | Metrics over a time window |
| Backup metadata | Backup tool recorded backup completion |
| Restore test output | Backup proved recoverable in testing |
| Checksums / row counts | Specific data properties were reconciled |
| Application smoke test | Application successfully executes business flows |
| Change record | Who acted, when, and under what approval |
| Reviewer sign-off | Responsible reviewer verified the outcome |

A lone screenshot is usually insufficient when lacking timestamps, environment context, commands run, and data sources.

## 12. Evidence Must Carry Context

Every key piece of evidence should include metadata:

- Runbook ID and version.
- Change or incident ID.
- Environment.
- Cluster and database.
- Host/node or endpoint.
- PostgreSQL version.
- Timestamp and timezone.
- Operator.
- Step number.
- Command/query or dashboard panel.
- Expected result.
- Actual result.
- Evidence file or reference.
- Redaction status.

Example:

~~~yaml
evidence_id: EV-2026-1042-07
runbook_id: RB-DB-014
runbook_version: "2.1"
change_id: CHG-2026-1042
environment: production
database: sales
postgres_version: "16.4"
step: "07"
captured_at: "2026-11-14T08:30:00Z"
operator: db_operator_1
source: "psql query output"
purpose: "Verify new index validity"
result: pass
artifact: "CHG-2026-1042/07-index-validity.txt"
~~~

Never record secrets, full connection URIs containing passwords, or sensitive query parameters in metadata.

## 13. Traceable and Tamper-Evident Evidence

An evidence package needs:

- Consistent filenames.
- Timestamps and timezones.
- Linking change or incident IDs.
- Explicit evidence sources.
- Controlled read access.
- Retention policies.
- Protection against silent overwrites.
- Checksums or immutable storage when strict auditing applies.
- Redaction notes whenever data was masked.

Generate SHA-256 checksums in your storage environment:

~~~bash
sha256sum evidence-file.txt
~~~

On Windows:

~~~powershell
Get-FileHash .\evidence-file.txt -Algorithm SHA256
~~~

Checksums detect file modifications after the hash was generated; they do not prove original contents were accurate. Protect both the checksum manifest and the underlying evidence source.

## 14. Execution Evidence vs. Outcome Evidence

**Execution evidence** proves a step ran:

- `psql` command output.
- Deployment logs.
- Migration tool logs.
- Operator action records.

**Outcome evidence** proves the post-operation state meets requirements:

- Catalog confirms columns, indexes, or roles exist.
- Backup restore test succeeded.
- Replication state stabilized.
- Query plans and latency meet criteria.
- Application smoke tests passed.
- Disk and connection metrics remain within thresholds.

A server returning `ALTER TABLE` only proves the server accepted the DDL. It does not prove application compatibility, absence of query regressions, or healthy replication catch-up.

## 15. Decision Gates and Stop Conditions

Runbooks must define conditions telling operators when to proceed, halt, or escalate.

Examples:

| Condition | Decision |
| --- | --- |
| Backup incomplete | Halt before destructive data operations |
| Primary cannot be positively identified | Halt and verify topology |
| Free disk below safety threshold | Halt or expand storage per plan |
| Replication lag exceeds threshold | Halt migration/failover per policy |
| Lock wait exceeds maximum duration | Abort step and identify blocker |
| DDL output differs from expectations | Do not execute subsequent steps |
| Post-check fails | Trigger rollback/recovery decision |
| Application smoke test fails | Keep change open/incomplete and escalate |

Service owners must define thresholds based on SLAs, RPO/RTO, and capacity. Never invent one universal number for every cluster.

## 16. Rollback, Recovery, and Forward-Fix

Not every change can be undone with an inverse SQL statement.

### Rollback

Restores the system to its pre-change state when reversal is safe and no new data dependencies were created.

Examples:

- Restoring an old configuration value.
- Revoking newly granted privileges.
- Dropping a newly created index if unneeded.
- Routing endpoints back to the old node after confirming it is safe.

### Recovery

Restoring from backups, WAL archives, or replicas when simple rollback is insufficient.

Examples:

- Database restore.
- PITR to a recovery target.
- Rebuilding a standby.
- Recreating objects from migrations or backups.

### Forward-Fix

Fixing current state via a follow-up change when rollback is risky or infeasible.

Examples:

- Repairing a partially applied migration.
- Adding a compatible index or constraint to complete a schema.
- Re-granting privileges accidentally revoked.
- Running reconciliation for transformed data.

### Required Elements of a Rollback Plan

1. Trigger conditions.
2. Authorized decision-maker.
3. Exact commands or steps.
4. Impact and downtime.
5. Data loss implications.
6. Backup or recovery point.
7. Post-rollback verification.
8. Rollback stop conditions.
9. Escalation path if rollback fails.

Never write "restore from backup if it fails" without specifying which backup, where it resides, how long restore takes, and what data loss is acceptable.

## 17. Why DDL Rollbacks Require Extra Caution

Some DDL commands are syntactically reversible yet cannot restore lost data.

Examples:

- `DROP COLUMN` followed by `ADD COLUMN` with the same name does not restore old values.
- `DROP TABLE` followed by a new `CREATE TABLE` does not restore rows, indexes, grants, or triggers.
- `ALTER TYPE` can lose precision or data when casting.
- `DELETE`/`TRUNCATE` cannot simply be undone after committing.
- Partially applied migrations can leave intermediate states.

Before migrating, determine transactionality of every DDL step, lock impacts, data transformations, and data recovery paths.

## 18. Post-Checks: Layered Verification

Post-checks should span multiple layers.

### Layer 1: Object State

- Object exists.
- Schema, name, and type match.
- Owner and grants match.
- Indexes are valid and ready.
- Constraints are in the expected state.
- Effective configuration values match.

### Layer 2: Data State

- Row counts or aggregates match.
- Key uniqueness and referential integrity hold.
- Nullability and range checks pass.
- Sampled data transformations verified.
- Source-to-target reconciliation passes for migrations or restores.

### Layer 3: Database Health

- PostgreSQL process and SQL health.
- Connection counts.
- Long transactions and lock waits.
- Replication lag.
- WAL and archive health.
- Free disk space.
- Error logs.
- Checkpoint and vacuum activity.

### Layer 4: Application Health

- Connections succeed.
- Read paths succeed.
- Write paths succeed where applicable.
- Business smoke tests pass.
- Error rates and latency within bounds.
- Background jobs and queues operating.
- External integrations healthy.

### Layer 5: Operational Readiness

- Monitoring and alerting active.
- Backup schedules continuing normally.
- HA topology stable.
- Runbooks and evidence updated.
- On-call team informed the change occurred.

## 19. Evidence After Configuration Changes

Example parameter change:

~~~sql
ALTER SYSTEM SET work_mem = '32MB';
SELECT pg_reload_conf();
~~~

Checking effective value:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name = 'work_mem';
~~~

Evidence should include:

- Prior value.
- Requested value.
- Associated config file/source.
- Reload result.
- Effective value after reload.
- `pending_restart` status.
- Before/after workload metrics.
- Error logs.
- Operator and change ID.

Do not assume `pg_reload_conf()` returning true means every setting took effect. Some parameters require a restart or are overridden at session, role, or database level.

## 20. Evidence After Role and Privilege Changes

Example creating an application role:

~~~sql
CREATE ROLE orders_reader
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;
~~~

Granting schema read privileges:

~~~sql
GRANT CONNECT ON DATABASE sales TO orders_reader;
GRANT USAGE ON SCHEMA reporting TO orders_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO orders_reader;
~~~

Verifying role attributes:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole
FROM pg_roles
WHERE rolname = 'orders_reader';
~~~

Verifying relation privileges:

~~~sql
SELECT
    has_database_privilege('orders_reader', 'sales', 'CONNECT') AS can_connect,
    has_schema_privilege('orders_reader', 'reporting', 'USAGE') AS can_use_schema,
    has_table_privilege('orders_reader', 'reporting.daily_orders', 'SELECT') AS can_select;
~~~

Required evidence:

- Role attributes.
- Database, schema, and table privileges.
- Default privileges if the role must read future objects.
- Connection test using the new role.
- Permitted `SELECT` test.
- Denied DML test if the role is read-only.
- Membership and inherited privilege checks.

Never store passwords in evidence. If test credentials are used, fetch via a secret manager and delete/rotate per policy afterward.

## 21. Evidence After Schema Migrations

Example migration adding a column:

~~~sql
ALTER TABLE public.orders
ADD COLUMN source_channel text;
~~~

Verifying catalog:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

If the migration creates an index:

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON public.orders (created_at);
~~~

Verify:

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready,
    indisunique
FROM pg_index
WHERE indexrelid = 'public.orders_created_at_idx'::regclass;
~~~

Additional evidence:

- Migration tool version and migration ID.
- Start/end timestamps.
- SQL output and logs.
- Catalog state.
- Lock waits and replication lag during execution.
- Query plans on representative queries.
- Application smoke tests.
- Rollback/forward-fix results if applicable.

With `CREATE INDEX CONCURRENTLY`, an index can exist yet remain invalid if the operation failed. Never check only the index name; inspect `indisvalid` and resolve invalid indexes per runbook.

## 22. Evidence After Backups

A backup command exiting with code 0 is insufficient to prove recoverability.

Evidence should include:

- Backup ID.
- Backup tool and version.
- Cluster and database identity.
- Backup start and end times.
- Backup type and mode.
- Backup size.
- WAL range and required WAL metadata.
- Exit status.
- Backup manifest.
- Checksum/validation results where supported.
- Storage location and retention.
- Encryption status.
- Restore test results.

For `pg_basebackup`, inspect outputs, manifests, and validation results per version. For dedicated backup tools, preserve tool-generated metadata.

### Backup Consistency

Physical backups need sufficient WAL to bring the cluster to a consistent state. With continuous archiving, check archive success and WAL continuity.

Do not equate a backup file existing with a restorable backup. Restore tests provide far stronger recoverability proof.

## 23. Evidence After Restores and PITR

Restores are high-risk because they can replace existing data.

Before restoring:

- Verify source backup and checksum/manifest.
- Identify target cluster and database.
- Confirm target is not live production receiving writes without explicit approval.
- Specify recovery target and timezone.
- Identify expected data loss window.
- Record pre-operation target state.
- Secure approvals and a rollback path.

After restoring:

- PostgreSQL starts and recovery completes.
- Database and object inventories match.
- Data counts and aggregates match.
- Required extensions and roles exist.
- Application smoke tests pass.
- WAL archiving and backup schedules are configured.
- Access controls are verified.
- Recovery timeline and target are recorded.

Evidence includes backup ID, restore logs, recovery target, timeline, server logs, SQL checks, and application tests.

## 24. Evidence After VACUUM and Maintenance

Monitoring vacuum progress:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
~~~

After completion, inspect table statistics:

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

Post-checks may include:

- Vacuum command/log completion.
- Before/after table and index sizes.
- Dead tuple estimates.
- Long transaction horizons.
- Query latency.
- Disk I/O.
- Replication lag.
- Lock impact.

Do not treat `n_dead_tup` as an exact absolute count; it is a statistical estimate. Standard `VACUUM` does not usually return file space to the OS immediately; `VACUUM FULL` behaves differently and requires dedicated lock and access planning.

## 25. Evidence After Failover or Switchover

After switching primary, prove both role and topology.

Checking the new node:

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_current_wal_lsn() AS current_lsn;
~~~

The new primary must report `in_recovery = false`.

Checking standbys:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Evidence should include:

- Incident or change ID.
- Reason for failover or switchover.
- Old and new primary nodes.
- Timeline and promotion timestamp.
- Selected candidate LSN.
- Fencing confirmation.
- `pg_is_in_recovery()` on the new primary.
- Replication state of remaining standbys.
- Endpoint/routing updates.
- Application reconnect and smoke tests.
- WAL archiving and backup state.
- Plan to rejoin the old node.

A newly writable node does not prove full HA recovery. Verify standbys follow the new primary and backups/monitoring continue operating.

## 26. Evidence After Network and Authentication Changes

When modifying `pg_hba.conf`, TLS, or connection settings:

- Record before/after config versions.
- Record file paths and change ID.
- Verify syntax and reload results.
- Inspect `pg_hba_file_rules`.
- Test permitted connections.
- Test rejected connections.
- Inspect authentication logs.
- Verify certificate expirations and TLS parameters.
- Verify application reconnects.

Example:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

Never save private keys or passwords in evidence. Connection tests should record user, database, client context, and outcome—not credentials.

## 27. Post-Restart Verification

After restarting PostgreSQL:

- Confirm the service is active.
- Check server version and role.
- Inspect logs from the latest startup.
- Verify recovery vs. primary state.
- Check listeners and connections.
- Check preloaded extensions if configured.
- Check effective configuration.
- Check replication.
- Check backups and WAL archiving.
- Run application smoke tests.

Example checking startup time and role:

~~~sql
SELECT
    pg_postmaster_start_time() AS postmaster_started_at,
    pg_is_in_recovery() AS in_recovery,
    current_database() AS database_name,
    current_user AS database_user;
~~~

A service manager reporting an active process only confirms the OS process started. PostgreSQL may still be recovering, not yet accepting traffic, or unreachable by applications.

## 28. Evidence from Logs

Logs provide historical evidence of events that occurred.

Sources:

- PostgreSQL server logs.
- OS/service manager logs.
- HA manager logs.
- Backup tool logs.
- Migration tool logs.
- Application logs.
- Proxy/load balancer logs.
- Cloud storage/control plane logs.

When saving log excerpts:

- Preserve timestamps and timezones.
- Preserve PID, session, and application context.
- Preserve SQLSTATEs and severity.
- Include enough surrounding lines for context.
- Redact secrets and PII.
- Record the query or filter used to extract them.
- Never save a single isolated ERROR line stripped of context.

Never replace raw evidence with a hand-written summary by the operator.

## 29. Evidence from Metrics

Metrics prove stability over time rather than at a single instant.

Examples:

- Connection counts.
- Query latency p50/p95/p99.
- TPS / transaction rates.
- Error rates.
- CPU and memory.
- Disk IOPS, throughput, and latency.
- WAL generation.
- Checkpoint durations.
- Replication lag.
- Deadlocks and lock waits.
- Temporary files.
- Autovacuum progress.

For high-risk changes, save snapshots before, during, and after the operation. Define observation windows and acceptance thresholds beforehand.

For example, if policy requires query p95 not to exceed baseline by more than 10% over 15 minutes, the runbook must specify which dashboard or query provides the data and how the baseline is computed.

## 30. Post-Migration Data Verification

Row counts are a first step but insufficient when data is transformed.

Compare aggregates:

~~~sql
SELECT
    count(*) AS row_count,
    min(created_at) AS min_created_at,
    max(created_at) AS max_created_at,
    sum(total_amount) AS total_amount
FROM public.orders;
~~~

Check for duplicate keys:

~~~sql
SELECT
    order_id,
    count(*) AS duplicate_count
FROM public.orders
GROUP BY order_id
HAVING count(*) > 1;
~~~

Check NULLs and ranges:

~~~sql
SELECT
    count(*) FILTER (WHERE order_id IS NULL) AS null_order_ids,
    count(*) FILTER (WHERE total_amount < 0) AS negative_amounts
FROM public.orders;
~~~

When comparing two systems, ensure you use the same snapshot or a consistent watermark. If data keeps changing while counts run, differences may simply reflect timing skew.

For massive datasets, full-table checksums can be expensive. Pick key ranges, partitions, samples, or suitable reconciliation tools, and document the verification coverage explicitly.

## 31. Evidence and Audit Trails

An audit trail records who did what, when, on which object, and under whose authorization.

An audit record should include:

- Change or incident ID.
- Operator identity.
- Approver identity.
- Start and end timestamps.
- Host, cluster, and database.
- Command or action.
- Result and exit code.
- Evidence reference.
- Exceptions or deviations.
- Rollback or recovery actions.
- Reviewer sign-off.

PostgreSQL logs do not fully replace organizational audit trails. Database logs may miss external actions such as DNS updates, firewall edits, secret manager changes, or cloud volume operations.

Combine database logs with infrastructure audit logs and change management records.

## 32. Managing Secrets and Sensitive Data in Evidence

Never include in runbooks or evidence:

- Passwords.
- API tokens.
- Private keys.
- Full connection strings containing passwords.
- Unnecessary customer PII.
- Sensitive query parameters.
- Backup encryption keys.

Use placeholders such as:

~~~text
host=<db-endpoint> dbname=<database> user=<service-role>
~~~

Real credentials belong in a secret manager or approved auth mechanism. When evidence must prove authentication succeeded, record the outcome, role, database, timestamp, and auth method—never the secret.

Redaction must preserve enough detail for troubleshooting. Do not strip timestamps, SQLSTATEs, or object names when they are non-sensitive and necessary.

## 33. Runbook Versioning and Ownership

Every runbook needs:

- A stable ID.
- A version number.
- An owning team.
- Creation and review dates.
- Last tested date.
- Supported PostgreSQL versions.
- Change history.
- Links to dashboards and tooling.
- Reviewer and approver.

Whenever PostgreSQL major versions, backup tools, HA managers, storage platforms, or authentication methods change, review the affected runbooks.

### Runbook Drift

Runbook drift happens when documentation no longer matches the live system:

- Hostnames or endpoints changed.
- Settings changed while docs stayed stale.
- Scripts were deleted or had flags changed.
- Tool versions differ.
- Roles or permissions changed.
- Dashboards moved.
- Recovery procedures no longer work.

Conduct periodic tabletop exercises or staging rehearsals to catch drift.

## 34. Testing Runbooks

Do not wait for a real incident to test a runbook.

Testing methods:

**Tabletop exercise:** Operations team walks through every step on paper, simulating decisions and escalations.

**Staging rehearsal:** Executes the procedure in staging with representative data sizes and workloads within safe bounds.

**Restore drill:** Restores a backup and measures actual RTO and RPO.

**Failover drill:** Tests primary switchover, fencing, routing, and node rejoin.

**Permission test:** Uses the real execution role to confirm the runbook has sufficient—and not excessive—privileges.

**Evidence review:** Someone uninvolved in execution inspects the evidence package to confirm they can independently verify the outcome.

Each test must log outcomes, durations, errors, unclear steps, and resulting doc updates.

## 35. Complete Runbook Example: Creating an Index Concurrently

### Objective

Create an index on a large table while minimizing write lock duration compared to standard index creation.

### Scope

- Database: `sales`.
- Table: `public.orders`.
- Index: `orders_created_at_idx`.
- Column: `created_at`.
- Environment: staging or production per change approval.

### Preconditions

- Target query requiring the index is identified.
- Checked whether a similar index already exists.
- Sufficient disk headroom exists for the index build.
- Replication lag and disk pressure are within bounds.
- No concurrent migration is running on the same table.
- Baseline query plan captured.
- Rollback plan ready.

Check existing indexes:

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready
FROM pg_index
WHERE indrelid = 'public.orders'::regclass;
~~~

### Execution

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON public.orders (created_at);
~~~

`CREATE INDEX CONCURRENTLY` cannot run inside a normal transaction block. Migration tooling must support non-transactional migrations.

### Post-Check

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready
FROM pg_index
WHERE indexrelid = 'public.orders_created_at_idx'::regclass;
~~~

Expected: one row, index valid and ready.

Inspect query plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE created_at >= now() - interval '7 days';
~~~

The query plan does not have to use the index in every case; the planner chooses based on selectivity and cost. Test representative query workloads and latency.

### Rollback

If the index is unneeded or causes excessive write overhead:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS public.orders_created_at_idx;
~~~

`DROP INDEX CONCURRENTLY` also cannot run inside a normal transaction block. Confirm the index disappeared and queries/applications continue working.

### Evidence

- Before/after index inventory.
- Command output.
- `indisvalid`/`indisready`.
- Build duration and logs.
- Disk usage.
- Replication lag.
- Query plans and latency.
- Application error rates.

## 36. Sample Runbook: Changing PostgreSQL Configuration

### Preconditions

- Identify parameter and context.
- Save current value.
- Identify config source and overrides.
- Assess memory, disk, and durability impact.
- Determine reload vs. restart.
- Identify rollback value.
- Secure a maintenance window if a restart is needed.

### Baseline

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name = 'max_connections';
~~~

### Execution

Example persistent change:

~~~sql
ALTER SYSTEM SET max_connections = '300';
~~~

This parameter requires a restart because its context is `postmaster`. Never call `pg_reload_conf()` and assume it took effect.

### Restart and Verify

After restarting via the service manager per runbook:

~~~sql
SHOW max_connections;

SELECT
    pg_postmaster_start_time(),
    pg_is_in_recovery();
~~~

Verify:

- PostgreSQL is active.
- Effective parameter value matches.
- `pending_restart` is cleared for that parameter.
- Connection capacity is sufficient.
- Application health passes.
- Logs show no startup or config errors.

### Rollback

Restore the old value via `ALTER SYSTEM` or configuration management, then restart if needed. Document where the old value came from and who approved it.

## 37. Sample Runbook: Creating a Role and Granting Privileges

### Preconditions

- Approved access request exists.
- Exact database, schema, and tables specified.
- Login vs. no-login defined.
- Role memberships defined.
- Default privileges for future objects defined.
- Least privilege applied.

### Execution

~~~sql
CREATE ROLE reporting_reader
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;

GRANT CONNECT ON DATABASE sales TO reporting_reader;
GRANT USAGE ON SCHEMA reporting TO reporting_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO reporting_reader;
~~~

### Post-Check

- Role attributes match.
- Memberships match.
- Database/schema/table grants match.
- Login test passes.
- `SELECT` succeeds.
- `INSERT`/`UPDATE`/`DELETE` are denied if the role is read-only.
- Default privileges match if required.

### Rollback

Revoke granted privileges. Drop the role only after verifying no object ownership, memberships, or dependencies remain. If the role created objects, transfer ownership or clean them up first.

## 38. Sample Runbook: Backup and Restore Testing

### Backup

1. Identify cluster/database and backup type.
2. Check destination capacity.
3. Check WAL archive health.
4. Run backup with the approved tool.
5. Record backup ID, start/end times, size, and tool exit status.
6. Validate manifest and checksums.
7. Verify retention and encryption.
8. Register the backup in the inventory.

### Restore Test

1. Select a specific backup ID.
2. Select an isolated target.
3. Specify recovery target.
4. Restore using the tool.
5. Wait for PostgreSQL recovery to finish.
6. Verify database and object inventories.
7. Run data checks and application smoke tests.
8. Measure restore duration and recovery point.
9. Tear down the test environment per policy after saving evidence.

### Evidence

- Backup metadata.
- WAL coverage.
- Restore logs.
- Recovery target and timeline.
- SQL checks.
- Application test results.
- Actual RTO/RPO.
- Reviewer sign-off.

## 39. Sample Runbook: Data Migration

### Preconditions

- Source and target identified.
- Mapping and schema reviewed.
- Data volume and duration estimated.
- Cutover and watermark strategy defined.
- Backup and rollback paths verified.
- Dual-write or write-freeze policy defined.
- Reconciliation queries prepared.

### Execution

- Capture source baseline.
- Run initial copy.
- Sync incremental changes.
- Pause/drain writes if required.
- Record final watermark/LSN.
- Apply final data delta.
- Switch applications.
- Open writes on target.
- Retain source through retention/rollback window.

### Post-Check

- Row counts by partition or key range.
- Aggregate totals.
- Missing or duplicate keys.
- Nullability and range constraints.
- Referential integrity.
- Query and application smoke tests.
- Error rates and latency.
- Replication/CDC lag if applicable.

### Rollback

Rollback feasibility depends on whether the target already accepted new writes. If the target accepted new writes, switching back to the source can lose data; reverse sync or reconciliation is needed. The runbook must state this condition before cutover.

## 40. Sample Runbook: Failover and Switchover

### Preconditions

- HA manager health and quorum.
- Candidate standby state.
- Replication LSN and lag.
- RPO policy.
- Fencing mechanism.
- Endpoint and routing paths.
- Backup and WAL archive state.
- Operator and incident commander.

### Execution

1. Detect and confirm primary failure or maintenance event.
2. Confirm quorum and authority to proceed.
3. Fence the old primary.
4. Select candidate based on WAL/LSN and health.
5. Promote exactly one standby.
6. Verify `pg_is_in_recovery() = false`.
7. Switch endpoints.
8. Confirm application reconnects and writes succeed.
9. Check replication slots, WAL archiving, and backups.
10. Rejoin the old node via rewind or rebuild as conditions dictate.

### Post-Check Evidence

- Failure timeline.
- Fencing confirmation.
- Candidate LSN.
- Promotion logs.
- Primary role query.
- Endpoint updates.
- Application smoke tests.
- Replication state.
- Timeline and backup status.
- Actual RTO and estimated/actual data loss.

Never consider failover complete simply because the new node is writable. Topology, applications, and backups must all be verified.

## 41. Runbooks for Re-Runnable Operations

Some commands can be safely re-run; others cannot.

| Operation Type | Re-Runnability | How to Control |
| --- | --- | --- |
| `SELECT` verification | Usually safe | Re-run as needed |
| `CREATE TABLE IF NOT EXISTS` | Conditional | Still must verify schema compatibility |
| `CREATE INDEX` | Not always safe | Check index state before retrying |
| `CREATE INDEX CONCURRENTLY` | May leave invalid index on fail | Check catalog and clean up invalid indexes |
| `ALTER SYSTEM SET` | Overwrites setting | Verify source and effective value |
| `INSERT` migration data | Risk of duplicates | Use idempotency keys, upserts, or checkpoints |
| `DROP TABLE` | Destructive | Require explicit approval and recovery path |
| `RESTORE` | Can overwrite target | Verify target and backup ID explicitly |
| `PROMOTE` standby | Advances timeline/role | Never repeat across multiple candidates |

Every runbook must classify commands as idempotent, conditionally idempotent, or destructive. When a command times out, never blindly re-run before confirming how far the server got.

## 42. Controlling Manual Operations

In production, commands should be saved alongside the change record. Run `psql` with `ON_ERROR_STOP` for scripts:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d sales -f migration.sql
~~~

This tells `psql` to halt on SQL errors inside the script. However, it does not roll back earlier committed commands, especially when the script includes statements outside transaction blocks.

Always:

- Review scripts beforehand.
- Test on staging.
- Confirm database and host.
- Use least-privilege roles.
- Save command output.
- Never paste secrets into shell history.
- Never use wrapper scripts that hide targets or ignore errors.
- Check state after timeouts or disconnects.

## 43. Managing Evidence Packages

An example directory layout:

~~~text
CHG-2026-1042/
  00-change-record.md
  01-prechecks/
    database-identity.txt
    replication-state.txt
    disk-capacity.txt
    baseline-metrics.json
  02-execution/
    command-output.txt
    migration-tool.log
    operator-actions.csv
  03-postchecks/
    catalog-verification.txt
    data-reconciliation.txt
    application-smoke-test.txt
    monitoring-snapshot.json
  04-recovery/
    rollback-decision.md
    rollback-output.txt
  05-closure/
    reviewer-signoff.md
    checksums.txt
~~~

This layout is illustrative. Use an organization-approved storage/records repository with access control and retention. Never leave evidence sitting in a temporary directory on the database host and forget to archive it.

## 44. Evidence Matrix

An evidence matrix shows reviewers how each goal is proven.

| Objective | Pre-Evidence | Execution Evidence | Post-Evidence |
| --- | --- | --- | --- |
| Add column | Schema snapshot | DDL output | `information_schema.columns` |
| Create index | Index inventory/query plan | `CREATE INDEX` output | `pg_index` validity + plan |
| Grant role | Role/grant snapshot | `GRANT` output | Privilege checks + login test |
| Restore | Backup ID/manifest | Restore logs | SQL/data/application checks |
| Failover | Topology/LSN/health | Fence/promote logs | Role/routing/replication checks |
| Config change | `pg_settings`/config source | `ALTER SYSTEM`/reload/restart logs | Effective setting + health metrics |
| Vacuum | Table stats/size | `VACUUM` logs/progress | Dead tuple estimates, latency, I/O |

If an objective lacks post-evidence, the runbook cannot yet prove success.

## 45. Closure Criteria

Never close a change simply because every command finished running.

Closure criteria can include:

- All required steps completed.
- No steps left in unknown state.
- Post-checks passed.
- Application owner confirmed.
- Monitoring shows no regressions past thresholds.
- Replication, backups, and HA in desired state.
- No pending rollbacks.
- Deviations recorded and approved.
- Evidence package archived.
- Reviewer sign-off completed.
- Runbook/documentation updated if procedures changed.

If only partial goals succeeded, record partial status or accepted risk per policy; never mark complete while ignoring exceptions.

## 46. Incident Handoff and Escalation

When a runbook halts due to an error:

1. Record the exact last completed step.
2. Record the failing step and its command/output.
3. Record timestamp, timezone, environment, and target.
4. Record the database's current state.
5. Record application impact.
6. Record decisions already made.
7. List which steps have not yet run.
8. Attach redacted evidence and logs.
9. Identify the receiving person or team.
10. Keep the system in a defined safe state.

Never send a bare "migration failed" message. The incoming responder needs to know whether retrying is safe, whether DDL committed, whether partial objects remain, and how far data changed.

## 47. Common Mistakes

1. **Runbooks listing only commands**, lacking preconditions, expected results, or verification.
2. **Omitting explicit database/host/role**, risking execution in the wrong environment.
3. **Using one generic runbook across all PostgreSQL major versions**, ignoring syntax and catalog changes.
4. **Skipping baselines**, making before/after comparisons impossible.
5. **Treating exit code 0 as the sole proof**, ignoring actual state.
6. **Confusing execution evidence with outcome evidence**, leading to premature change closure.
7. **Omitting stop conditions**, causing operators to push forward after safety preconditions fail.
8. **Writing vague rollbacks**, omitting data loss, targets, and recovery time.
9. **Assuming all DDL is rollbackable**, forgetting auto-committed DDL or lost data.
10. **Re-running timed-out commands without checking state**, creating duplicate objects or data.
11. **Skipping `CREATE INDEX CONCURRENTLY` verification**, leaving invalid indexes behind.
12. **Relying on row counts alone to validate migrations**, missing key gaps, duplicates, or aggregate mismatches.
13. **Skipping application tests**, checking only database objects.
14. **Ignoring replication after DDL, restores, or failovers**, leaving standbys lagging or broken.
15. **Saving passwords or connection URIs in evidence**, leaking credentials.
16. **Saving contextless screenshots without timestamps**, untraceable to sources.
17. **Discarding raw outputs and logs**, keeping only operator-written summaries.
18. **Lacking retention and access policies**, causing evidence loss or unauthorized exposure.
19. **Not versioning runbooks**, letting docs drift from reality.
20. **Never rehearsing restores or failovers**, leaving RTO and recovery steps untested on paper.
21. **Not separating operator and verifier on high-risk actions**, lacking independent checks.
22. **Omitting deviations and exceptions**, leaving reviewers unaware of procedural changes.
23. **Closing changes before the observation window finishes**, missing delayed regressions.
24. **Failing to hand off exact state when halting**, causing the next responder to run the wrong step.

## 48. Practice Exercises with Answers

### Exercise 1. What is a runbook?

**Answer:** A document guiding an operational procedure from starting preconditions through verification and closure.

### Exercise 2. How does a runbook differ from a checklist?

**Answer:** A runbook explains how to execute steps and handle branches; a checklist confirms items are completed.

### Exercise 3. What is post-operation evidence used for?

**Answer:** Proving verifiable state and outcomes tied to the exact environment and execution run.

### Exercise 4. Why are pre-checks needed?

**Answer:** To confirm target, health, privileges, backups, capacity, and safety conditions before making changes.

### Exercise 5. What is a baseline?

**Answer:** A pre-operation state snapshot used to compare against post-operation outcomes.

### Exercise 6. Is exit code 0 enough to prove success?

**Answer:** No. You must check catalogs, data, database health, and application behavior.

### Exercise 7. How does execution evidence differ from outcome evidence?

**Answer:** Execution evidence proves a command ran; outcome evidence proves the intended state was reached.

### Exercise 8. Does a runbook need stop conditions?

**Answer:** Yes. Operators must know when to halt or escalate if preconditions or expected results fail.

### Exercise 9. Why can't every DDL change be rolled back?

**Answer:** Some DDL commits independently, destroys data, or cannot restore prior values with an inverse statement alone.

### Exercise 10. Evidence to verify a new column?

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders';
~~~

**Answer:** The catalog confirms column name, data type, and nullability.

### Exercise 11. What verifies index validity?

**Answer:** `pg_index`, specifically `indisvalid` and `indisready`.

### Exercise 12. Why does CREATE INDEX CONCURRENTLY need a dedicated post-check?

**Answer:** The index may still exist in an invalid state if the build failed.

### Exercise 13. What evidence does a read-only role need?

**Answer:** Role attributes, grants, and tests showing `SELECT` succeeds while DML is denied.

### Exercise 14. Does a completed backup guarantee it is restorable?

**Answer:** No. Backup metadata validation and restore testing are required.

### Exercise 15. What should post-restore evidence include?

**Answer:** Backup ID, restore logs, recovery target, catalog/data checks, and application smoke tests.

### Exercise 16. Why record the PostgreSQL version?

**Answer:** Syntax, catalog views, settings, and behavior can differ across major versions.

### Exercise 17. Does an evidence record need a timestamp and timezone?

**Answer:** Yes, to correlate cleanly with logs, metrics, and external systems.

### Exercise 18. Does a checksum prove contents are accurate?

**Answer:** No. It only detects whether the file changed after the checksum was generated.

### Exercise 19. When should operator and verifier be separated?

**Answer:** Especially for high-risk or production-impacting operations to ensure independent verification.

### Exercise 20. When should you not retry a command?

**Answer:** When you do not know how far the previous command got, or when the operation is non-idempotent or destructive.

### Exercise 21. Which layers should post-checks inspect?

**Answer:** Object, data, database health, application health, and operational readiness.

### Exercise 22. Why are application smoke tests important?

**Answer:** Valid database objects do not guarantee the application can connect and execute business workflows.

### Exercise 23. Why document deviations?

**Answer:** Reviewers and handoff recipients need to know where actual execution diverged from the runbook and why.

### Exercise 24. When a migration already received target writes, is rolling back to source always safe?

**Answer:** No. Reverse sync/reconciliation or explicit acceptance of data loss is required.

### Exercise 25. Does an evidence package need retention and access control?

**Answer:** Yes, because logs and evidence can contain operational details and sensitive data.

### Exercise 26. What is runbook drift?

**Answer:** When a runbook no longer matches the real system, tools, endpoints, permissions, or configuration.

### Exercise 27. What is a tabletop exercise used for?

**Answer:** Simulating procedures and decisions without executing real changes against the database.

### Exercise 28. Why not store screenshots alone?

**Answer:** Screenshots often lack sources, timestamps, raw outputs, and search/reconciliation capability.

### Exercise 29. What should closure criteria include?

**Answer:** Passed post-checks, stable applications/monitoring, archived evidence, resolved exceptions, and reviewer sign-off.

### Exercise 30. What should a failed-runbook handoff record?

**Answer:** Completed steps, commands/outputs, current state, impact, remaining steps, evidence, and next owner.

## 49. Runbook Authoring and Execution Checklist

### Before the Operation

- [ ] Runbook ID, version, and owner are clear.
- [ ] Change or incident ID exists.
- [ ] Objective and scope are specific.
- [ ] Correct environment, cluster, database, and host verified.
- [ ] PostgreSQL major version confirmed.
- [ ] Operator, approver, and verifier assigned.
- [ ] Preconditions and stop conditions defined.
- [ ] Backup/recovery readiness confirmed.
- [ ] Database, application, and OS baselines saved.
- [ ] Risks, downtime, and RPO/RTO assessed.
- [ ] Commands and scripts reviewed/tested.
- [ ] Rollback or forward-fix plan is actionable.

### During the Operation

- [ ] Executed in exact order.
- [ ] Timestamps and operators logged for major steps.
- [ ] Command outputs and tool logs saved.
- [ ] Expected results verified before proceeding.
- [ ] Locks, connections, disk, WAL, and replication monitored.
- [ ] Halted if stop conditions triggered.
- [ ] All deviations/exceptions documented.
- [ ] Zero secrets stored in evidence.
- [ ] Never retried commands with unknown state.

### After the Operation

- [ ] Catalog and object states verified.
- [ ] Data checks and reconciliation passed.
- [ ] Database health verified.
- [ ] Application smoke tests passed.
- [ ] Replication, backups, and monitoring remain operational.
- [ ] Metrics stayed within observation-window thresholds.
- [ ] No pending rollbacks or recoveries remain.
- [ ] Evidence includes timestamps, context, and sources.
- [ ] Evidence archived in proper repository with access controls.
- [ ] Reviewer sign-off completed.
- [ ] Change/incident record closed with accurate status.
- [ ] Runbook updated if drift was discovered.

## 50. Official PostgreSQL Documentation

Consult documentation matching your deployed major version:

- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — system views for verifying sessions, databases, I/O, and replication.
- [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html) — catalog metadata for database objects and states.
- [Information Schema](https://www.postgresql.org/docs/current/information-schema.html) — SQL-standard metadata for tables, columns, and privileges.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — managing roles and privileges.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — database, schema, and table privileges.
- [ALTER SYSTEM](https://www.postgresql.org/docs/current/sql-altersystem.html) — persistent configuration changes.
- [Configuration Settings](https://www.postgresql.org/docs/current/config-setting.html) — reload, restart, and setting contexts.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backup and restore methods.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — WAL archiving and point-in-time recovery.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — creating physical base backups.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index creation and `CONCURRENTLY`.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — vacuuming and options.
- [pg_stat_progress](https://www.postgresql.org/docs/current/progress-reporting.html) — tracking progress of long-running operations.
- [Logging Configuration](https://www.postgresql.org/docs/current/runtime-config-logging.html) — server logs and log context.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — inspecting query plans and execution behavior.

`/current/` URLs point to the latest PostgreSQL documentation. Catalog columns, statistics views, DDL behavior, and backup tooling can vary by major version; cross-check documentation matching your actual version and tools before running production runbooks.

## 51. Summary

**Runbooks describe how to execute; evidence proves state and results; post-checks confirm the service remains healthy after changes.** These three elements must be designed together for every critical administrative operation.

1. **Runbooks must specify scope, triggers, roles, preconditions, execution steps, and stop conditions.**
2. **Pre-operation baselines make it possible to see what the change actually affected.**
3. **Every major step needs an expected result and an evidence source.**
4. **A zero exit code proves only that the command returned success.** Catalog, data, and application checks prove the outcome.
5. **Rollbacks require concrete triggers, commands, and recovery points.** Never assume every DDL or data change is reversible.
6. **Evidence requires context:** change ID, environment, database, version, timestamp, operator, and source.
7. **Protect secrets and PII in logs and evidence.** Use access controls, redaction, retention, and checksums where appropriate.
8. **Post-checks must span object, data, database, application, and operational readiness.**
9. **Backups require restore testing.** File existence alone does not prove recoverability.
10. **Migrations require reconciliation and consistent watermarks.** Row counts alone are insufficient.
11. **Failovers require verifying fencing, roles, routing, replication, and backups.**
12. **Runbooks must be versioned and rehearsed.** Untested runbooks often fail during real incidents.
13. **Close changes only once evidence is complete, exceptions are logged, and accountable reviewers sign off.**

A reliable PostgreSQL administrative procedure never stops when the command finishes. It leaves behind clear evidence enabling anyone to verify what happened, the system's exact state, and why it is safe to keep operating.
