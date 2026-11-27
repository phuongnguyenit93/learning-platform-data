# Restricted Operating Modes and Maintenance Windows

A production PostgreSQL system needs a way to keep serving traffic while operators maintain the database, operating system, storage, or application. Some changes require only a configuration reload; others require a restart; some operations require blocking writes, terminating sessions, or pausing all application traffic. Without advance preparation, an administrative operation can cause lock waits, connection storms, replication lag, transaction failures, or longer downtime than planned.

A **restricted operating mode** is a state where the system permits only a defined subset of operations—such as read-only access, operator-only access, write suspension, or health-check-only traffic. A **maintenance window** is a scheduled period for performing changes that affect availability, performance, or data safety. The two concepts are related yet distinct: the maintenance window is the schedule and coordination workflow; the restricted mode is the technical state enforced during that period.

PostgreSQL offers several primitives supporting restricted operations, including read-only transactions, `default_transaction_read_only`, server-level `default_transaction_read_only`, `pg_hba.conf`, role privileges, connection limits, hot standby read-only behavior, session termination, and controlled restarts. However, no single setting creates a complete maintenance mode. Applications may still write over open connections, background workers may keep running, scheduled jobs may start new transactions, and proxies may retain stale endpoints. Therefore, maintenance must be coordinated across database, application, network, and orchestration layers.

This lesson belongs to the **Administration** chapter of the **Database Engine Relational PostgreSQL** module. It explains how to choose an appropriate restricted mode, schedule and execute maintenance windows, preserve consistency, minimize downtime, control access, validate recovery, and rehearse procedures.

## 1. Learning Objectives

After this lesson, you can:

- Distinguish between a maintenance window, restricted mode, read-only mode, and full outage.
- Select a restricted mode based on the type of administrative action.
- Understand read-only transactions, `default_transaction_read_only`, and role privileges.
- Control admission for applications, connections, and background jobs.
- Drain traffic and sessions before risky changes.
- Distinguish reload, restart, switchover, and failover.
- Plan DDL, index maintenance, vacuum, backups, and upgrades.
- Protect replication, WAL archiving, and recovery paths during maintenance.
- Define preconditions, stop conditions, rollbacks, and validation.
- Coordinate maintenance across application, DBA, infrastructure, and business teams.
- Measure downtime, maintenance duration, RPO/RTO, and user impact.
- Build runbooks, communications, checklists, and practice labs.

## 2. What Is a Maintenance Window?

A maintenance window is an approved time period for executing administrative activities that may affect service.

### 2.1. Planned Maintenance

Foreknown changes such as minor version updates, OS patches, storage migrations, schema migrations, certificate rotations, or configuration changes requiring restarts.

### 2.2. Emergency Maintenance

Changes required urgently due to security vulnerabilities, disk exhaustion, corruption risks, or production defects. There may not be time for full advance notice, yet decision records and stop conditions are still mandatory.

### 2.3. A Maintenance Window Does Not Equal Downtime

Certain tasks can run online, such as concurrent index builds, analyze, certain schema changes, or rolling maintenance on HA clusters. The window can serve as a risk-control interval rather than a service outage.

### 2.4. Scope and Ownership

Every window must specify affected systems, databases, nodes, applications, regions, owners, dependencies, and permitted actions.

### 2.5. Entry and Exit Criteria

Entry criteria confirm the system is healthy enough to begin. Exit criteria confirm the database, replication, applications, and monitoring have returned to an acceptable state.

## 3. Restricted Operating Modes

A restricted mode limits one or more categories of activity for a targeted period.

| Mode | Primary Behavior | Use Cases |
|---|---|---|
| Read-only | Allows reads, rejects writes per transaction policy | Reporting, cutovers, data protection |
| Application maintenance | App rejects requests or allows only maintenance endpoints | Schema and data migrations |
| Restricted access | Only approved operators, roles, or networks may connect | Emergency repairs |
| Drained | Accepts no new requests, waits for in-flight requests to finish | Switchovers and restarts |
| Quiesced writes | Stops writers and jobs, keeps reads if safe | Backups, cutovers, and DDL |
| Offline | Serves no clients | Restarts, upgrades, and restores |

### 3.1. Choose the Narrowest Appropriate Restriction

If only one batch job needs to stop, you do not need to take the entire database offline. Narrowing scope limits business impact.

### 3.2. Every Mode Needs an Owner

One designated person or controller must own enabling and disabling the restricted mode, logging timestamps, and verifying outcomes.

### 3.3. Every Mode Needs an Expiration

A forgotten maintenance mode can leave a service unavailable far longer than planned. Set expirations/alerts and post-window verification procedures.

### 3.4. Distinguish Access Restriction from Data Protection

Blocking application connections does not stop operator roles or lingering background processes. Data protection requires privileges, transaction controls, and backups.

### 3.5. There Is No Single Universal Maintenance-Mode Switch in PostgreSQL

PostgreSQL provides individual primitives; applications, proxies, and orchestrators typically supply admission and draining behaviors. Runbooks must coordinate them together.

## 4. Read-Only Transactions

PostgreSQL supports read-only transactions that forbid most write operations inside that transaction.

~~~sql
BEGIN READ ONLY;

SELECT count(*)
FROM public.orders;

COMMIT;
~~~

### 4.1. SET TRANSACTION READ ONLY

You can set the mode for the current transaction immediately after `BEGIN`, before running other statements.

~~~sql
BEGIN;
SET TRANSACTION READ ONLY;
SELECT now();
COMMIT;
~~~

### 4.2. Read-Only Is Not a Cluster-Wide Read-Only Snapshot

The transaction enforces read-only semantics under PostgreSQL rules. It does not block other sessions from writing to the primary.

### 4.3. Restricted Operations

A read-only transaction rejects normal write operations and many commands with side effects. Certain administrative commands or temporary objects follow specific rules; check version-specific documentation for exact commands.

### 4.4. Read Consistency

Read-only transactions still follow the snapshot isolation semantics of their transaction isolation level. `READ COMMITTED` sees a fresh snapshot per statement; `REPEATABLE READ` holds a consistent snapshot across the transaction.

### 4.5. Do Not Use Read-Only as Your Only Security Boundary

A client can open another transaction or connect with another role. Use role privileges and connection policies to enforce access control.

## 5. default_transaction_read_only

This setting establishes the default transaction mode for new sessions or transactions that do not specify another mode.

~~~sql
SHOW default_transaction_read_only;

SET default_transaction_read_only = on;
~~~

### 5.1. Session-Level Setting

`SET` changes the setting for the current session. Useful for testing or dedicated connection pools.

### 5.2. Role and Database Defaults

`ALTER ROLE` or `ALTER DATABASE ... SET` configures defaults for sessions matching that role or database. This works well for reporting users.

~~~sql
ALTER ROLE reporting_user
SET default_transaction_read_only = on;
~~~

### 5.3. Server-Level Default

`postgresql.conf` can set `default_transaction_read_only` server-wide. Changes can normally be reloaded; verify context in `pg_settings` and your version.

### 5.4. Not an Absolute Write Lock

Superusers and certain privileged contexts can override the setting or perform special operations. Role privileges remain an essential enforcement layer.

### 5.5. Verifying Effectiveness

Connect as the actual application role, run `SHOW default_transaction_read_only`, and attempt a write inside a test transaction. Never verify using an admin account alone.

## 6. Role Privileges and Read-Only Users

Database privileges provide a more durable enforcement layer than relying on client conventions alone.

### 6.1. Creating a Read-Only Role

~~~sql
CREATE ROLE reporting_reader
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE
NOINHERIT;
~~~

Design role memberships to match actual privileges and environment policies.

### 6.2. Granting CONNECT and Schema Usage

~~~sql
GRANT CONNECT ON DATABASE appdb TO reporting_reader;
GRANT USAGE ON SCHEMA reporting TO reporting_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting
TO reporting_reader;
~~~

### 6.3. Default Privileges

So future tables grant appropriate read access, configure default privileges under the role that creates objects:

~~~sql
ALTER DEFAULT PRIVILEGES
IN SCHEMA reporting
GRANT SELECT ON TABLES TO reporting_reader;
~~~

Default privileges are bound to the object-creating role; configure them for each relevant owner.

### 6.4. Revoking Write Privileges

Do not grant `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`REFERENCES`/`TRIGGER` or sequence privileges unless required. Inspect inherited role memberships and `PUBLIC` grants.

### 6.5. Roles Do Not Replace Network Controls

A role only protects database authorization. Combine it with `pg_hba.conf`, TLS, network allowlists, and secret management.

## 7. Read-Only Standbys vs. Primary Read-Only

A hot standby in recovery inherently permits only read-only queries. This behavior differs from setting `default_transaction_read_only` on a running primary.

### 7.1. Hot Standbys

A standby can serve `SELECT` queries when `hot_standby` is enabled and recovery allows queries. Ordinary writes are rejected.

### 7.2. Primary Read-Only Policy

The primary remains a writable node by role, yet can be configured and coordinated so applications execute only reads. Explicit enforcement is needed at both database and application layers.

### 7.3. Promotion Changes Behavior

When a standby is promoted, it becomes primary and is no longer automatically read-only under recovery semantics. Maintaining read-only requires an explicit policy.

### 7.4. Recovery Conflicts

Read queries on a standby can conflict with WAL replay. Long maintenance or read-only workloads require reviewing `max_standby_*` delays and `hot_standby_feedback` trade-offs.

### 7.5. Replica Lag

Read-only does not mean up-to-the-instant data. Before cutover or validation, inspect replay progress and consistency requirements.

## 8. Application Maintenance Mode

The application layer is usually the best place to reject writes with user-friendly messages and stop jobs from initiating new transactions.

### 8.1. Admission Control

An API gateway or service can return a maintenance response to new requests while keeping health checks and operator endpoints active.

### 8.2. Read-Only Application Mode

The application can permit GET/query endpoints while rejecting state-changing commands. Verify secondary endpoints, GraphQL mutations, admin tools, and internal APIs too.

### 8.3. Background Workers

Pause queue consumers, schedulers, cron jobs, ETL pipelines, event handlers, and retry workers. An API in read-only mode while workers keep writing can break a maintenance plan.

### 8.4. Idempotency and Queue Retention

Keep jobs queued rather than dropping them. Ensure post-window retries are idempotent and capable of draining backlogs safely.

### 8.5. User Communication

Return retryable maintenance status codes showing the expected window and guidance. Prevent clients from retrying aggressively and causing a traffic storm.

## 9. Draining Traffic and Sessions

Draining means stopping new work while allowing in-flight work to finish under control.

### 9.1. Stop Admission First

Put gateways/services into maintenance mode or remove nodes from load balancers before altering the database.

### 9.2. Drain In-Flight Requests

Wait for active requests to finish within a deadline. Requests exceeding the deadline must be canceled or return retryable errors per policy.

### 9.3. Stop Writers and Workers

Pause writers, scheduled tasks, consumers, and integration jobs. Check for service accounts that write directly to the database.

### 9.4. Drain Connection Pools

Poolers and applications should stop opening new connections to the node undergoing maintenance and close or recycle connections per plan. Idle connections can still retain session state.

### 9.5. Confirm No Writers Remain

Check `pg_stat_activity`, application metrics, and logs. Some maintenance commands require other sessions to finish or locks to clear.


## 10. Database and Role Connection Limits

PostgreSQL can limit connections by database and by role. This is an admission control tool, not a replacement for draining existing sessions.

### 10.1. CONNECTION LIMIT per Role

~~~sql
ALTER ROLE app_writer CONNECTION LIMIT 0;
~~~

A connection limit of 0 blocks new connections for that role under limit enforcement; already-connected sessions are not disconnected.

### 10.2. CONNECTION LIMIT per Database

~~~sql
ALTER DATABASE appdb CONNECTION LIMIT 20;
~~~

The limit applies to new database connections and does not restrict superuser connections in the same way as ordinary roles. Check version-specific behavior.

### 10.3. ALLOW_CONNECTIONS

~~~sql
ALTER DATABASE appdb WITH ALLOW_CONNECTIONS false;
~~~

This setting blocks new connections to the database. It does not terminate existing sessions.

### 10.4. Checking Remaining Sessions

~~~sql
SELECT pid, usename, application_name, state
FROM pg_stat_activity
WHERE datname = 'appdb';
~~~

Identify sessions to keep (operators/monitoring) and sessions to drain or terminate.

### 10.5. Re-Enabling Connections

~~~sql
ALTER DATABASE appdb WITH ALLOW_CONNECTIONS true;
~~~

Re-open connections only after schema, config, data validation, and application readiness succeed.

## 11. pg_hba.conf for Restricted Access

`pg_hba.conf` governs client authentication and connection admission by address, database, user, and authentication method.

### 11.1. Rule Order

PostgreSQL uses the first matching rule. A `reject` rule placed after a broad allow rule may never take effect.

### 11.2. Operator-Network-Only Access

During maintenance, you can restrict database connections using targeted rules for operator/bastion subnets while rejecting client application networks.

### 11.3. Reloading HBA

After editing the file, reload configuration to read the updated rules:

~~~sql
SELECT pg_reload_conf();
~~~

### 11.4. HBA Does Not Terminate Existing Sessions

Connections authenticated before the rule change can keep operating. Drain or terminate sessions per plan.

### 11.5. Validating Rules

Inspect `pg_hba_file_rules` on supporting versions to catch parse errors and verify rule order. Keep a tested operator access path so you do not lock yourself out of the database.

## 12. Combining Restricted Modes Across Layers

A reliable maintenance mode requires enforcement across multiple layers.

~~~text
Client traffic
     |
     v
API / Gateway admission
     |
     +---- reject new writes
     |
     v
Application workers / schedulers
     |
     +---- pause consumers and jobs
     |
     v
Connection pool / proxy
     |
     +---- drain or block new sessions
     |
     v
PostgreSQL
     |
     +---- role privileges / read-only / connection policy
~~~

### 12.1. Gateway

Block new requests or allow only read endpoints and maintenance pages. Keep health checks working so orchestrators do not mistake maintenance for an outage.

### 12.2. Application

Reject write commands across all code paths, including admin APIs and internal service calls.

### 12.3. Workers

Pause scheduled jobs and consumers; record offsets and checkpoints so resuming loses no events.

### 12.4. Database

Apply role privileges, read-only transactions, connection controls, and HBA rules scoped to the task.

### 12.5. Infrastructure

Drain load balancers, adjust routing, and restrict network paths if maintenance requires node restarts or upgrades.

## 13. Stopping Writes While Keeping Reads

Some maintenance tasks must prevent data changes while still letting users view existing data.

### 13.1. Read-Only Application Mode

The application switches to read-only banners and API behavior. Write requests are rejected with actionable/retryable responses per contract.

### 13.2. Read-Only Role Separation

Application reads use a reader role; the writer role is disabled or withheld during the window. Separate pools so operators retain access.

### 13.3. Database Default Read-Only

`default_transaction_read_only` can be applied to application roles or databases as defense-in-depth, though privileged users can override the setting.

### 13.4. Existing Transactions

Open write transactions can still commit after the mode changes unless drained. Identify and conclude in-flight writers before cutover.

### 13.5. Validating Read Paths

Test critical queries, views, functions, and replicas. Some functions trigger side effects or call external services even when invoked by a `SELECT`.

## 14. Maintenance with Applications Completely Offline

Certain operations require the database to have zero client traffic.

### 14.1. Stop Application Admission

Put gateways into maintenance mode and stop writer services and background jobs.

### 14.2. Stop Connection Poolers

Drain PgBouncer/proxy pools or route targets away from the node. Retain a controlled management path.

### 14.3. Terminate Remaining Sessions

After confirming no critical transactions remain, remaining client backends can be terminated scoped by database or application.

~~~sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'appdb'
  AND pid <> pg_backend_pid()
  AND usename = 'app_writer';
~~~

This action has side effects: terminated sessions roll back their transactions. Inspect owners and query age before running it.

### 14.4. Keep an Operator Path

Preserve superuser/break-glass access over a tested local socket or bastion. Never cut off every administrative path simultaneously.

### 14.5. Confirm Quiescence

Inspect active sessions, transactions, prepared transactions, replication workers, and background jobs. Even without app sessions, the database may still run autovacuum or the checkpointer.

## 15. Prepared Transactions and Long-Running Transactions

Draining is incomplete if lingering transaction state can interfere with maintenance.

### 15.1. Long Transactions

Long transactions can hold locks, pin snapshots, and block vacuum cleanup. Check `xact_start`, `backend_xmin`, and query age.

### 15.2. Idle in Transaction

Sessions in `idle in transaction` keep transactions open even without running SQL. Identify the application bug and owner before terminating.

### 15.3. Prepared Transactions

Two-phase commit can leave prepared transactions behind if a client or coordinator disconnects. Inspect `pg_prepared_xacts` and commit/roll back only per the transaction coordinator and business decision.

### 15.4. Replication Slots and Logical Consumers

Logical replication slots and decoding consumers can retain WAL even after application traffic stops. Inspect slot activity and retained WAL.

### 15.5. Maintenance Preflight

Before DDL, restarts, or upgrades, check locks, prepared transactions, replication slots, long snapshots, and active backups.


## 16. Reload or Restart?

Not every PostgreSQL configuration change requires a restart. `pg_settings.context` and major-version documentation specify how each parameter applies.

### 16.1. Reloadable Settings

Settings with context `sighup` take effect after a configuration reload.

~~~sql
SELECT pg_reload_conf();
~~~

### 16.2. Restart-Required Settings

Settings with context `postmaster` require a server restart to take effect—for example, memory and process settings like `shared_buffers` and `max_connections`.

### 16.3. Checking Context

~~~sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'max_connections',
    'work_mem',
    'log_min_duration_statement'
);
~~~

### 16.4. pending_restart

If `pending_restart` is true, the setting has been changed yet is not active until a restart occurs. Never declare maintenance complete before restarting and verifying.

### 16.5. Avoid Unnecessary Restarts

Restarts drop sessions and generate recovery and reconnect load. Use reloads whenever supported, while verifying actual application behavior.

## 17. PostgreSQL Shutdown Modes

PostgreSQL supports different shutdown modes via server control utilities.

### 17.1. Smart Shutdown

Smart shutdown waits for all clients to disconnect before stopping. If sessions stay open, shutdown can wait indefinitely.

### 17.2. Fast Shutdown

Fast shutdown disconnects clients, aborts active transactions, and performs a clean server shutdown. This is the typical choice for controlled restarts.

### 17.3. Immediate Shutdown

Immediate shutdown stops abruptly without a clean shutdown; the next startup requires crash recovery. Use only for exceptional cases with full awareness of recovery impact.

### 17.4. pg_ctl

`pg_ctl` provides stop, restart, and status commands. Pick the mode matching your runbook and service manager; avoid mixing conflicting control paths concurrently.

### 17.5. Verify Stopped State

Verify process/service state, sockets/ports, logs, and control-plane status. A stop command returning success must still be cross-checked against actual state.

## 18. Planned Restarts and Connection Storms

After a restart, thousands of clients may try to reconnect simultaneously, creating a sudden load spike.

### 18.1. Stagger Application Startup

Start application instances in batches or with jitter to spread out connection attempts.

### 18.2. Pooler Warm-Up

Start or refresh connection pools within capacity limits. Check authentication, DNS, and TLS handshake capacity.

### 18.3. Background Jobs

Do not resume all queues and schedulers the instant the database process starts. Wait until the database and downstream dependencies stabilize.

### 18.4. Recovery Duration

Crash recovery, WAL replay, and startup checks can take significant time. Base readiness checks on SQL and application probes rather than process existence alone.

### 18.5. Throttled Traffic Restoration

Open traffic incrementally while monitoring CPU, connections, locks, WAL, and p95/p99 latency. You can keep restricted mode active longer for validation.


## 19. DDL in Maintenance Windows

DDL can acquire strong locks and queue production queries. Assess lock modes, table sizes, transaction durations, and version behavior before deploying.

### 19.1. ALTER TABLE

Many `ALTER TABLE` operations require an `ACCESS EXCLUSIVE` lock for at least one phase. Locks may be granted instantly if uncontested, or queue behind an older transaction.

### 19.2. Lock Timeout

Set `lock_timeout` so DDL fails fast instead of waiting indefinitely and queuing other requests behind it:

~~~sql
SET lock_timeout = '5s';
ALTER TABLE public.orders ADD COLUMN source_code text;
~~~

If it times out, investigate blockers and retry in an appropriate window. Do not raise the timeout merely to force DDL through.

### 19.3. Statement Timeout

`statement_timeout` bounds statement runtime. Pick values suited to the operation; large migrations may need dedicated deadlines and monitoring.

### 19.4. Transactional DDL

Many PostgreSQL DDL statements can run inside transactions, but commands such as `CREATE INDEX CONCURRENTLY` and `VACUUM` cannot run inside a transaction block. Verify command-specific rules.

### 19.5. Migration Compatibility

Deploy applications compatible with both old and new schemas following expand-and-contract. Never drop or rename columns while older application instances still query the old schema.

## 20. Creating Indexes Online

Standard `CREATE INDEX` blocks writes to the table during the build. `CREATE INDEX CONCURRENTLY` avoids blocking writes across most of the build, though it takes longer and involves multiple phases.

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
~~~

### 20.1. Concurrent Builds

Concurrent builds allow `INSERT`/`UPDATE`/`DELETE` to continue during most of the operation. They still take locks and can wait on old transactions or snapshots.

### 20.2. Cannot Run Inside a Transaction Block

`CREATE INDEX CONCURRENTLY` cannot run inside a `BEGIN`/`COMMIT` transaction block. Migration tools must execute the statement standalone.

### 20.3. Failed Index Builds

If a build fails, it can leave an invalid index behind. Inspect `pg_index.indisvalid`/`indisready` and drop/retry per runbook.

### 20.4. Resource Impact

Index builds scan tables, sort data, write index pages, and emit WAL. Monitor I/O, CPU, temp files, replication lag, and free disk space.

### 20.5. Post-Build Verification

Confirm the index is valid, usable by the planner, and improves query performance. New indexes add write amplification and storage overhead.

## 21. REINDEX and Index Maintenance

Index rebuilds can resolve corruption or bloat or change storage layout, yet generate load and require disk headroom.

### 21.1. Standard REINDEX

`REINDEX` can take strong locks affecting reads and writes on the relation depending on object type. Schedule a window and inspect blockers.

### 21.2. REINDEX CONCURRENTLY

Concurrent reindexing lowers blocking for ordinary DML on supporting versions, yet executes in phases, consumes extra disk, and waits on locks/snapshots. Cannot run inside a transaction block.

### 21.3. Disk Headroom

During the build, old and new indexes coexist. Budget extra temporary files, WAL, and replica/archive retention headroom.

### 21.4. Unique Indexes

Unique index builds can detect duplicate rows and fail. Resolve duplicates per business rules before running.

### 21.5. Validate Workload Impact

Compare query plans, latency, and write throughput after rebuilding; never declare success solely from a zero exit code.

## 22. VACUUM, VACUUM FULL, and ANALYZE

Maintenance commands vary widely in locking, I/O, and transaction-context requirements.

### 22.1. Standard VACUUM

`VACUUM` reclaims space for internal reuse, updates visibility information, and helps prevent transaction ID wraparound. It allows normal reads and writes to proceed while consuming I/O.

### 22.2. VACUUM FULL

`VACUUM FULL` rewrites the table and requires an `ACCESS EXCLUSIVE` lock. It can return disk space to the filesystem, yet causes table downtime/blocking; requires ample temporary disk and a window.

### 22.3. ANALYZE

`ANALYZE` refreshes planner statistics. It usually requires no table downtime, though it incurs I/O/CPU cost and can alter query plans.

### 22.4. Do Not Use VACUUM FULL as Routine Maintenance

Check dead tuples, long transactions, autovacuum, and bloat evidence first. Standard `VACUUM` does not normally shrink OS file size, yet makes space reusable inside the relation.

### 22.5. VACUUM Cannot Run Inside a Transaction Block

Run `VACUUM`/`ANALYZE` per command rules and scheduling. `VACUUM FULL` imposes much heavier lock demands.

## 23. Online Schema Migration

Phased migrations minimize how long a database must enter restricted or offline modes.

### 23.1. Expand

Add new columns, tables, or indexes in a manner compatible with the current application. Choose defaults and nullability mindful of PostgreSQL version and DDL lock behavior.

### 23.2. Deploy Compatible Application

Deploy code capable of reading and writing both old and new schemas. Dual-writes require idempotency and consistency checks.

### 23.3. Backfill in Batches

Backfill data in small batches, committing frequently and checkpointing progress. Monitor WAL, replica lag, dead tuples, and foreground latency.

### 23.4. Switch Reads and Writes

After backfill and validation pass, switch applications to the new schema. Preserve a rollback path for an observation window.

### 23.5. Contract Later

Once old code is gone and data is verified, drop legacy columns/objects in a separate migration with lock timeouts and a rollback plan.

## 24. Backups During Maintenance Windows

Backups can run online, yet still require scheduling and resource controls.

### 24.1. Physical Base Backups

Physical backups read large volumes of data files and can add network and disk load. Monitor replication, WAL retention, and backup progress.

### 24.2. Logical Dumps

`pg_dump` takes a consistent snapshot and reads tables and indexes. On large databases, it can run long and impact cache and I/O; choose parallelism carefully.

### 24.3. WAL Archiving

Verify `archive_command`/archiver health before and after maintenance. Continuous WAL retention is essential for PITR.

### 24.4. Back Up Before Risky Changes

Before destructive migrations or upgrades, verify the latest backup, WAL coverage, and restore procedure. A "completed" backup is insufficient without restore evidence.

### 24.5. Restore Testing

Test restores into an isolated environment and validate database/application consistency. Never perform restore tests by overwriting production.

## 25. Minor and Major Version Upgrades

PostgreSQL upgrades involve different downtime profiles and procedures.

### 25.1. Minor Updates

Minor updates preserve data directory compatibility within the same major series, yet still require a restart and checking release notes, extensions, and provider requirements.

### 25.2. Major Upgrades with pg_upgrade

`pg_upgrade` converts the data directory to a new major version via a compatibility workflow. Requires preflight checks, backups, target extension binaries, disk headroom, and an upgrade window.

### 25.3. Major Upgrades with Logical Replication

Logical replication can synchronize source and target and cut over with shorter downtime, yet requires careful planning for schemas, sequences, large objects, DDL, and write freezes.

### 25.4. Extension Compatibility

Verify extension versions, shared libraries, SQL upgrade scripts, and compatibility with the target PostgreSQL version.

### 25.5. Cutover Validation

Before opening writes on the target, verify row counts/checksums/business invariants, sequences, roles, grants, jobs, replication/backups, and application smoke tests.

## 26. Maintenance on HA Clusters

HA reduces downtime, yet per-node maintenance must preserve quorum, replication, and capacity.

### 26.1. Standby-First Maintenance

Some updates can be applied to standbys first, followed by a switchover and updating the former primary. Always verify version compatibility and upgrade rules.

### 26.2. Rolling Maintenance

Maintain one node at a time only if cluster topology and replication mode support it. Ensure sufficient standbys, quorum, and failover protection remain at every step.

### 26.3. Planned Switchover

Drain writes, wait for the candidate to catch up, verify timeline and LSN, promote the new primary, and fence/demote the old primary via the HA manager.

### 26.4. Failover Protection Gaps

While a node restarts or rebuilds, the cluster may run with a primary and zero healthy standbys. Flag degraded protection and reduce risky workload.

### 26.5. Restoring Redundancy

After maintenance, confirm standbys have rejoined and caught up, archiving/backups operate, and the HA manager reports healthy topology before closing the window.


## 27. Planning a Maintenance Window

A solid maintenance plan documents operation order, expected duration, dependencies, and stop decisions.

### 27.1. Scope

Explicitly list affected clusters, databases, tables, application services, regions, endpoints, replicas, backup systems, and external integrations.

### 27.2. Impact Classification

Classify each step: online, degraded performance, read-only, partial outage, or full outage. Communicate concrete impacts instead of writing only "maintenance".

### 27.3. Timeline

Set milestones for preflight, admission stop, draining, backups/checkpoints, changes, validation, traffic restoration, and closeout. Include buffers for rollback and recovery.

### 27.4. Owners and Approvals

Assign a change owner, DBA, application owner, infrastructure owner, incident commander/on-call, and business approver whenever data loss or extended downtime risks exist.

### 27.5. Dependencies

Confirm access credentials, storage capacity, backup targets, DNS/proxy controls, certificates, monitoring, vendor support, and approvers.

## 28. Pre-Window Preflight Checklist

Preflight catches unmet prerequisites before placing the system into restricted mode.

### 28.1. Health

Check database availability, error rates, replication state, free disk, CPU/memory headroom, backup/archiver health, and HA manager status.

### 28.2. Data Safety

Confirm valid backups, WAL coverage, restore evidence, and transaction/LSN baselines. For destructive migrations, record rollback or restore points.

### 28.3. Locks and Sessions

Check for long transactions, `idle in transaction` sessions, prepared transactions, blockers, active jobs, and replication consumers.

### 28.4. Capacity

Budget temporary disk for index rebuilds/upgrades, memory/CPU for backfills, WAL growth, and replica catch-up. Do not start if headroom is insufficient.

### 28.5. Change Readiness

Verify scripts, checksums/artifact versions, approvals, rollback steps, runbook links, and staging test outcomes.

## 29. Runbook: Starting a Maintenance Window

Exact ordering varies by task, though a standard skeleton applies.

1. Declare window start and confirm owners/on-call are present.
2. Capture baseline: metrics, node roles, LSN/timeline, connections, slots, backup/archive state.
3. Notify applications/gateways and enable maintenance or read-only mode if needed.
4. Stop or pause scheduled jobs, queue consumers, and writers.
5. Drain in-flight requests and connection pools.
6. Inspect remaining sessions/transactions; terminate per policy if needed.
7. Confirm the database is in the intended restricted/quiesced state.
8. Execute approved actions while logging outputs and timestamps.
9. Validate database, replication, backups, application, and business behavior.
10. Resume jobs and traffic incrementally, monitor SLOs, and close the window.

### 29.1. Never Skip the Baseline

Without capturing pre-change state, distinguishing new regressions from pre-existing issues becomes difficult.

### 29.2. Freeze Point

Record the exact timestamp when applications stopped writing. Use it to reconcile events and transactions after maintenance.

### 29.3. One Coordinating Change Owner

Prevent multiple operators from running overlapping commands on the same cluster without shared awareness of state.

### 29.4. Checkpoint Each Step

Record completion and preconditions for every step. If you must abort, you know exactly where the system stands.

### 29.5. Communication Cadence

Send status updates at defined intervals, especially if durations shift or rollback triggers.

## 30. Stop Conditions and Abort Criteria

Maintenance must define clear abort criteria before starting.

### 30.1. Data Safety Failures

Unreadable backups, WAL gaps, unexpected writes, or indeterminate replication state mandate halting before any destructive action.

### 30.2. Lock Waits Exceeding Deadlines

If DDL cannot acquire locks within `lock_timeout` or blockers cannot be cleared safely, cancel and reschedule.

### 30.3. Capacity Thresholds

Halt when disk headroom, memory, replication lag, or WAL retention crosses approved limits.

### 30.4. Unexpected Application Impact

If error rates, latency, or queue backlogs breach abort criteria, halt subsequent steps and evaluate rollback.

### 30.5. Ambiguous State

If it is unclear whether a command succeeded, check database, catalogs, and control planes before retrying. Never re-run destructive commands merely because a client timed out.

## 31. Rollback and Recovery Plans

Rollbacks must be tailored to each change type; not every database operation has a trivial undo.

### 31.1. Configuration Rollback

Save old configs, change one setting at a time, and prepare restoration commands and approvals. Check reload vs. restart requirements.

### 31.2. Schema Rollback

Destructive DDL may be irreversible once data is dropped or transformed. Prefer expand-and-contract plus backups/restore points for risky migrations.

### 31.3. Index Rollback

Newly created indexes can be dropped if problematic, considering locks and query dependencies. Concurrent drops may suit large indexes depending on version.

### 31.4. Upgrade Rollback

Major version upgrades generally cannot be undone simply by starting old binaries on an upgraded data directory. Prepare old-cluster snapshots/backups or separate rollback topologies.

### 31.5. PITR Instead of Undo

If changes committed and propagated, restore/PITR may be the recovery path. Account for restore time, data loss past the recovery point, and write reconciliation.

## 32. Post-Maintenance Validation

Maintenance is complete only once the system satisfies service-readiness exit criteria.

### 32.1. Database Readiness

Verify connections, intended read/write behavior, logs, catalog state, schema versions, and critical queries.

### 32.2. Replication Readiness

Verify senders/receivers, replay lag, slots, WAL archiving, and timelines. On HA clusters, confirm standbys are healthy.

### 32.3. Application Readiness

Run smoke tests against real endpoints: logins, reads, safe writes, transaction commits, queue publish/consume, and external integrations.

### 32.4. Business Validation

Verify key row counts, aggregates, business invariants, pending jobs, and event backlogs. Re-open full writes only when business state is sound.

### 32.5. Restoring Normal Mode

Re-enable connections, roles, gateway admission, workers, and scheduled jobs in order. Clear maintenance flags and confirm monitoring shows normal traffic.

## 33. Monitoring During Maintenance Windows

During the window, dashboards should focus on both operation progress and service impact.

### 33.1. Database Activity

Active sessions, locks, transaction age, query latency, deadlocks, and errors.

### 33.2. Resource Pressure

CPU, memory/swap, disk latency/IOPS/throughput, temporary files, and free space.

### 33.3. WAL and Replication

WAL generation, archive backlog, slot retained bytes, sender/receiver lag, and replay progress.

### 33.4. Application Impact

Request rate, error rate, p95/p99 latency, pool waits, queue depth, and retries.

### 33.5. Maintenance Progress

Index build progress, vacuum progress, backup progress, upgrade phases, and remaining estimates if tools expose them. Never extrapolate an exact ETA from a single sample.

## 34. Storage and Filesystem Maintenance

Storage operations often need coordination with PostgreSQL because data files, WAL, and temporary files behave differently.

### 34.1. Disk Expansion

Expand volumes/filesystems per provider procedures, verify the filesystem sees the added space, and confirm mounts and ownership remain intact.

### 34.2. Disk Migration

Use PostgreSQL-aware procedures to relocate data or WAL directories. Stop, copy, sync, permissions, and startup checks must be controlled; never copy an active data directory haphazardly.

### 34.3. WAL Directory

If WAL resides on its own volume, verify the mount before starting PostgreSQL. A missing mount can cause the server to write onto the root filesystem or fail to start.

### 34.4. Disk Full

Full disks halt WAL writes, checkpoints, temporary files, or logs. Keep emergency headroom and runbooks for slots, archiving, and temporary files.

### 34.5. Capacity Alerts

Alert on free bytes, usage percentage, growth rate, and time-to-full. Percentages alone can mislead on huge or tiny volumes.

## 35. Certificate and Credential Maintenance

Credential rotation is security maintenance that can break replication or application connections if mismanaged.

### 35.1. Rotation Overlap

Where policy allows, deploy new credentials/certificates alongside old ones, verify clients reconnect, then revoke the old ones.

### 35.2. TLS Certificates

Check SANs/hostnames, CA chains, expirations, permissions, and trust stores across applications, poolers, and replication clients.

### 35.3. Replication Connections

Rotate replication user secrets across all subscribers and standbys and verify sender/receiver reconnects before revoking old credentials.

### 35.4. Database Role Rotation

Never change the password on a shared role without inventorying all clients first. Prefer dedicated per-service roles and secret references.

### 35.5. Auditing

Record actors, timestamps, secret versions, and connection validations; never record secret values in logs or tickets.

## 36. Backups and Maintenance Scheduling

Backup schedules should avoid colliding with heavy I/O operations without compromising backup coverage.

### 36.1. Base Backup Windows

Pick low-traffic hours when backups read substantial data. Measure actual throughput and impact on cache and replication.

### 36.2. WAL Archive Continuity

Never pause the archive pipeline without understanding retention and recovery consequences. Maintain buffering and alerts when the archive backend undergoes maintenance.

### 36.3. Backup Catalog Consistency

Record backup ID, source node, timeline, start/stop LSN, WAL coverage, and retention metadata.

### 36.4. Restore Test Windows

Allocate dedicated schedules for restore drills on isolated infrastructure. Measure RTO and verify application data.

### 36.5. Backups After Upgrades

After major upgrades or schema migrations, take fresh backups per policy and verify the WAL archive chain on the new topology.


## 37. Maintenance Communication and Coordination

Clear communication helps application teams prepare retries, queue handling, and user notices.

### 37.1. Advance Notice

Include service/database scope, start/end times, timezone, expected impact, read/write availability, endpoints, and support contacts.

### 37.2. Reminders

Send reminders ahead of the window and confirm owners completed preflight checks. Re-notify immediately if timing shifts.

### 37.3. Live Status

During the window, update statuses: scheduled, admission closed, draining, executing, validating, restoring traffic, or extended/aborted.

### 37.4. Extension Notices

If an operation exceeds estimates, share the reason, current impact, risk, and revised ETA. Never promise an ETA without evidence.

### 37.5. Completion Notices

Confirm service restoration, removal of restricted modes, passed validations, and any remaining limitations.

## 38. Maintenance Calendars and Conflict Management

Multiple teams may schedule changes on the same cluster; visibility into one shared calendar is essential.

### 38.1. Shared Calendar

Track maintenance windows across database, application, network, storage, identity, and cloud platforms. Avoid overlapping business peaks and major events.

### 38.2. Change Freezes

Enforce freezes before peak seasons or financial close. Emergency security fixes require an explicit exception path.

### 38.3. Dependency Order

For example, certificate rotation must update trust stores before rotating server certs; schema expansion must precede application deploys; database upgrades must follow planned extension/application compatibility steps.

### 38.4. Concurrent Maintenance

Avoid running backups, index rebuilds, storage migrations, and major batches concurrently when they compete for I/O without prior benchmarking.

### 38.5. Post-Window Reviews

Compare actual durations and impacts against estimates, updating future maintenance estimates and sequences.

## 39. Restricted Modes by Use Case

Select modes based on the operation and what must be protected.

| Use Case | Suggested Mode | Primary Controls |
|---|---|---|
| Read-only reporting period | Read-only role/transaction | `SELECT` grants, default read-only |
| Schema migration requiring no writes | App write freeze + drain | Pause writers/jobs, validate sessions |
| Database restart | Full drain/offline | Stop clients, fast shutdown, readiness |
| Emergency data repair | Restricted access | Operator-only path, backup, audit |
| HA switchover | Writer drain/quiesce | Catch-up, fence/demote, route |
| Certificate rotation | Restricted admin change | Overlap certs, reconnect tests |
| Concurrent index creation | Normal service with monitoring | Lock waits, I/O, replication |
| Major upgrade | Offline or logical cutover | Backup, compatibility, validation |

### 39.1. Read-Only Windows

Use when reads can continue while writes must stop. Verify all write paths, including background jobs and privileged users.

### 39.2. Operator-Only Windows

Use when only DBAs or infra engineers need access. HBA/network allowlists and database connection restrictions must preserve the management path.

### 39.3. Full Offline Windows

Use for restarts, restores, or storage operations incompatible with live access. Factor draining and recovery checks into window duration.

### 39.4. Online Maintenance

Some commands run while the service stays online, yet require monitoring and abort criteria. Concurrent does not mean zero impact.

### 39.5. Degraded Service Windows

Some read endpoints can stay open while writer paths stop. Communicate freshness, consistency expectations, and endpoint behavior clearly.

## 40. Scheduled Jobs and Maintenance Coordination

Automated jobs can start unexpectedly right in the middle of DBA maintenance.

### 40.1. Inventory Schedulers

Document cron, `pg_cron`, Kubernetes CronJobs, Airflow, ETL orchestrators, application schedulers, and vendor jobs.

### 40.2. Pause and Resume

Pause before the freeze point, save job state/offsets, and resume in sequence after validation. Do not delete schedules just to pause them temporarily.

### 40.3. Retry Behavior

Jobs failing during a window may retry all at once when the database reopens, creating a spike. Add jitter, backoff, and concurrency caps.

### 40.4. Long-Running Jobs

Decide which jobs may finish, which must be canceled, and how to resume them. Save checkpoints to avoid restarting entire batches from scratch.

### 40.5. Job Ownership

Every job needs an owner, contact, expected runtime, write scope, and recovery procedure. Without an owner, deciding whether to terminate is risky.

## 41. Maintenance with Logical and Physical Replication

Maintenance on one node can impact replication and failover readiness.

### 41.1. Before Maintaining a Publisher

Inspect sender connections, slots, synchronous standbys, archive status, and WAL retention. Ensure downstream consumers retain valid WAL paths.

### 41.2. Maintaining a Standby

Drain read traffic from the standby, stop/restart/rebuild per runbook, and verify receiver/replay progress once back online.

### 41.3. Logical Subscriptions

If subscriptions or apply workers must pause, monitor logical slots on the publisher and retained WAL. Never drop slots without a resync plan.

### 41.4. Failover During Maintenance

Avoid combining maintenance with a planned failover unless rehearsed as the explicit objective. If the primary fails mid-window, switch to the incident runbook.

### 41.5. Restoring Redundancy

Confirm all standbys and subscriptions have caught up, slots are valid, and the backup/archive chain is intact before closing.

## 42. Maintenance and Data Corrections

Direct data fixes carry distinct side effects unlike schema or config changes.

### 42.1. Scope Target Rows

Run `SELECT` previews showing primary keys, counts, and expected values before `UPDATE`/`DELETE`. Save result sets or backups as needed.

### 42.2. Transaction Sizing

Split large corrections into checkpointed batches to minimize lock duration, WAL bursts, and rollback overhead.

### 42.3. Idempotency

Scripts must include conditions or progress markers so re-running is safe. Avoid repeating full-table updates without knowing which rows already finished.

### 42.4. Business Approval

Modifying balances, orders, payments, entitlements, or audit records requires owner approval. DBAs validate execution mechanics and evidence.

### 42.5. Post-Correction Validation

Compare affected row counts, aggregates, and business invariants. Check downstream events, replicas, and caches if they do not sync automatically.

## 43. Security and Maintenance Access

Maintenance windows often expand access; controls must remain explicit.

### 43.1. Least Privilege

Use task-specific roles: read-only inspection, schema migration, backups, replication administration, and break-glass superuser. Never use a single shared superuser for everything.

### 43.2. Time-Bound Access

Grant elevated access temporarily for the window and revoke afterward. Verify memberships, default privileges, and rotated credentials.

### 43.3. Bastion and Network Controls

Require bastion/VPN access with MFA and auditing for operators. Never open PostgreSQL ports broadly to the internet for convenience.

### 43.4. Audit Logging

Log DDL, role grants, connection changes, config updates, and privileged actions. Protect query text and parameters per privacy policy.

### 43.5. Separation of Duties

For high-risk actions, separate proposer, approver, and executor roles. This reduces human error and strengthens traceability.


## 44. Example: Maintenance Window for Schema Migration

A migration adding columns, backfilling data, and switching application paths can proceed in phases.

### 44.1. Before the Window

Take a backup/restore point, check replication lag, deploy code compatible with both old and new schemas, and rehearse the migration in staging with representative volume.

### 44.2. Expand Schema

Add nullable columns or new structures under DDL lock policies. Use a short `lock_timeout` and abort if locks are not acquired promptly.

### 44.3. Backfill

Pause or throttle batches, update in small key ranges, commit per batch, and monitor WAL, replica lag, and latency.

### 44.4. Cutover

Enable the new application path after validation counts and checksums pass. Retain old columns/logic through a rollback window.

### 44.5. Contract Later

Drop legacy objects in a separate maintenance window once no old application versions remain. Never bundle destructive cleanup into the initial deployment.

## 45. Example: Maintenance Window for Restart / Configuration Change

### 45.1. Identify Parameter Requirements

Use `pg_settings.context` to distinguish reload vs. restart. Check parameter values and `pending_restart`.

### 45.2. Preflight

Confirm backups, HA candidates, replication catch-up, disk/CPU headroom, and connection drain plans.

### 45.3. Drain

Enable app maintenance, pause jobs, drain poolers, and confirm no critical transactions remain.

### 45.4. Apply and Restart

Apply configs via configuration management; reload or restart via the service manager per runbook. Avoid editing multiple uncoordinated sources of truth.

### 45.5. Validate and Restore

Check `SHOW` settings, logs, SQL readiness, replication, and app smoke tests; restore traffic incrementally and verify protection recovered.

## 46. Example: Emergency Maintenance When Disk Nears Full

### 46.1. Assess Root Cause

Inspect filesystems, `pg_wal`, replication slots, archive backlogs, temp files, logs, and relation growth. Never delete WAL files using filesystem commands.

### 46.2. Safely Shed Load

Temporarily pause batches, backups, or writers by business priority. Preserve WAL/backup protection and identify slots or consumers causing retention.

### 46.3. Expand Storage If Needed

Use provider-supported volume expansion and filesystem resize procedures. Verify actual free space afterward.

### 46.4. Handle Slots and Archiving

Only drop/advance slots or purge retention once you understand subscriber and recovery consequences. Losing needed WAL can force standbys or consumers to reseed.

### 46.5. Restore Normal Operations

Verify WAL generation, archiving, and replication catch up, disk forecasts stabilize, backups run, and alerts clear with evidence.

## 47. Practice Exercises

### Exercise 1 — Concepts

What is a maintenance window?

**Answer:** A scheduled and coordinated period for executing operational changes that may affect service.

### Exercise 2 — Restricted Mode

Must a restricted mode always take the entire database offline?

**Answer:** No; it may enforce read-only, operator-only, or write-paused modes instead.

### Exercise 3 — Read-Only Transactions

Which command starts a read-only transaction?

**Answer:** `BEGIN READ ONLY`.

### Exercise 4 — Defaults

Does `default_transaction_read_only` block all privileged writes?

**Answer:** No; it only sets default transaction behavior and must pair with privileges and access controls.

### Exercise 5 — Role Grants

Why should reporting roles have write privileges omitted?

**Hint:** Enforce read-only at the authorization layer rather than relying on application code alone.

### Exercise 6 — ALLOW_CONNECTIONS

Does `ALTER DATABASE ... ALLOW_CONNECTIONS false` disconnect open sessions?

**Answer:** No; it blocks new connections, while existing sessions must be drained or terminated separately.

### Exercise 7 — HBA

Do `pg_hba.conf` changes affect already-open sessions immediately?

**Answer:** No; reloading applies to new connection attempts and does not terminate already-authenticated sessions.

### Exercise 8 — Application Mode

Why must queue consumers and schedulers also be paused?

**Hint:** They can keep writing even when the API switches to read-only.

### Exercise 9 — Draining

What does draining mean?

**Answer:** Stopping new work admission and waiting for or canceling in-flight work by a deadline.

### Exercise 10 — Long Transactions

Why is `idle in transaction` dangerous during maintenance?

**Answer:** It can hold locks and snapshots while blocking vacuum cleanup.

### Exercise 11 — Prepared Transactions

Should all prepared transactions be rolled back automatically before maintenance?

**Answer:** No; you must confirm with the coordinator and business outcome first.

### Exercise 12 — Reload vs. Restart

Which setting indicates whether a config change requires a restart?

**Answer:** `pg_settings.context`, alongside `pending_restart` to check current status.

### Exercise 13 — Shutdown

What is the behavior of fast shutdown?

**Answer:** Disconnects clients, aborts active transactions, and performs a clean server shutdown.

### Exercise 14 — Immediate Shutdown

Why does immediate shutdown carry risk?

**Answer:** The next startup requires crash recovery.

### Exercise 15 — Connection Storms

How do you mitigate reconnect bursts after a restart?

**Hint:** Stagger startup, jitter, pool warm-up, and throttled traffic restoration.

### Exercise 16 — CREATE INDEX CONCURRENTLY

Can it run inside a transaction block?

**Answer:** No.

### Exercise 17 — Failed Concurrent Index

What must you check?

**Hint:** Index validity/readiness, plus dropping/retrying per runbook if the build left an invalid index.

### Exercise 18 — VACUUM FULL

What is the key difference compared to standard `VACUUM`?

**Answer:** Rewrites the relation, requires an `ACCESS EXCLUSIVE` lock, and can cause table downtime.

### Exercise 19 — Lock Timeout

What does `lock_timeout` help with?

**Answer:** Bounds how long DDL waits for a lock so it does not hang indefinitely.

### Exercise 20 — Expand-and-Contract

Why add the new schema first and drop the old schema later?

**Hint:** Lets compatible application versions coexist and minimizes downtime.


### Exercise 21 — Backups

Is a completed backup alone enough to prove recoverability?

**Answer:** No; WAL coverage and restore tests are required.

### Exercise 22 — Major Upgrades

Why can't you always start the old binary after `pg_upgrade`?

**Answer:** Major upgrades convert data directories/catalogs; separate rollback artifacts/backups are needed.

### Exercise 23 — HA Rolling Maintenance

Why maintain standby and quorum capacity during rolling maintenance?

**Answer:** So the cluster retains failover protection and coordination quorum.

### Exercise 24 — Logical Slots

Why shouldn't you drop a slot just to free disk during maintenance?

**Answer:** Consumers can lose needed WAL and be forced to resync.

### Exercise 25 — Stop Conditions

List two conditions that must halt maintenance.

**Hint:** Unsafe backups/WAL, insufficient disk headroom, unexpected writes, lock wait past deadline, or excessive replication lag.

### Exercise 26 — Rollback

Is every DDL change easy to roll back?

**Answer:** No; destructive data changes may require restore or PITR.

### Exercise 27 — Read-Only Standbys

Does a read-only standby guarantee the newest data?

**Answer:** No; check replay lag and freshness.

### Exercise 28 — User Communication

What should a maintenance notice include?

**Hint:** Scope, timezone, impact, read/write availability, endpoints, and support contact.

### Exercise 29 — Emergency Disk

Can you delete WAL files directly in `pg_wal` to free space?

**Answer:** No; use PostgreSQL-aware slot, archive, and storage procedures.

### Exercise 30 — Completion

When is a maintenance window considered complete?

**Answer:** Database, replication, backups, application/business validations, and monitoring all pass exit criteria, and restricted modes have been cleanly lifted.

## 48. Pre-Maintenance Checklist

- [ ] Scope, impact, timezone, and window approved?
- [ ] Owners, on-call, and escalation contacts confirmed?
- [ ] Backup/WAL coverage and restore evidence available?
- [ ] Database, HA, replication, archive, and disk health verified?
- [ ] Long transactions, prepared transactions, slots, and blockers checked?
- [ ] Capacity sufficient for index rebuilds, upgrades, or backfills?
- [ ] Maintenance and drain plans ready for applications, gateways, poolers, and jobs?
- [ ] Config/DDL scripts and version compatibility tested?
- [ ] Rollback, stop conditions, and validation steps documented?
- [ ] Operator and break-glass access tested?
- [ ] Notices and reminders sent?

## 49. During- and Post-Maintenance Checklists

### During the Window

- [ ] Baseline and freeze point recorded?
- [ ] Application admission and writes controlled?
- [ ] Workers, schedulers, and consumers paused?
- [ ] Connections and transactions drained?
- [ ] Each step has outputs, timestamps, and checkpoints logged?
- [ ] CPU, memory, disk, WAL, replication, and app SLOs monitored?
- [ ] Stop conditions enforced if triggered?

### After the Window

- [ ] Database settings, schemas, and indexes verified?
- [ ] SQL readiness and critical queries passing?
- [ ] Replication, slots, and WAL archiving healthy?
- [ ] New backup or backup chain verified per policy?
- [ ] Application smoke tests and business invariants passing?
- [ ] Queues and jobs resumed in order?
- [ ] Read-only and connection restrictions lifted properly?
- [ ] Traffic restored incrementally and p95/p99 latency stable?
- [ ] Completion notice and change record updated?
- [ ] Follow-up items assigned owners and deadlines?

## 50. Quick Reference Table

| Component | Role |
|---|---|
| Maintenance window | Coordinated timeframe for changes |
| Restricted mode | Limits permitted operations |
| `BEGIN READ ONLY` | Read-only transaction |
| `default_transaction_read_only` | Default mode for transactions |
| Role privileges | Read/write enforcement |
| `ALLOW_CONNECTIONS` | Allow/block new connections to a database |
| `CONNECTION LIMIT` | Connection cap |
| `pg_hba.conf` | Client authentication and admission rules |
| Drain | Stop new admission and finish in-flight work |
| `pg_stat_activity` | Sessions and transaction states |
| `pg_prepared_xacts` | Prepared transactions |
| `pg_reload_conf` | Reload configuration |
| `pg_settings.context` | Setting application context |
| `pending_restart` | Setting awaiting server restart |
| Smart shutdown | Waits for clients to disconnect |
| Fast shutdown | Disconnects clients and shuts down cleanly |
| Immediate shutdown | Stops immediately; requires crash recovery |
| `CREATE INDEX CONCURRENTLY` | Index build with reduced DML blocking |
| `REINDEX CONCURRENTLY` | Reduced-blocking index rebuild by version |
| `VACUUM` | Cleanup, space reuse, visibility maintenance |
| `VACUUM FULL` | Table rewrite with strong lock |
| `lock_timeout` | Lock wait limit |
| `statement_timeout` | Execution duration limit |
| Expand-and-contract | Multi-step compatible schema migration |
| `pg_upgrade` | Major version upgrade tool |
| WAL archive | Recovery chain |
| Exit criteria | Conditions to finish maintenance |
| Stop condition | Conditions requiring halt/abort |

## 51. Conclusion

**Safe maintenance coordinates scheduling, admission control, restricted modes, database operations, and validation.** Read-only transactions, `default_transaction_read_only`, role privileges, connection limits, `ALLOW_CONNECTIONS`, and `pg_hba.conf` are database-layer controls; application gateways, connection poolers, background jobs, and network controls determine whether the system truly stops receiving writes. Existing connections and transactions do not vanish when changing settings or reloading HBA, making draining and session inspection mandatory in many windows.

Not all maintenance requires downtime. Concurrent index operations, certain DDL, analyze, and backups can run online with monitoring and abort criteria. Operations such as `VACUUM FULL`, restarts, storage migrations, or major upgrades may require restricted or offline modes. Understand lock behavior, transaction-block restrictions, resource impacts, WAL/replication retention, and rollback limits before acting.

Every maintenance window requires preflight checks, owners, a timeline, a freeze point, stop conditions, rollback/recovery plans, live monitoring, and exit criteria. Afterward, verify the database, replication, archive/backups, application smoke tests, and business invariants; restore traffic and workers incrementally before lifting restricted modes. Record actual durations, impacts, and follow-ups to improve the next window.

Operational principle: **restrict only the operations that must pause, drain every write source, keep a safe administrative access path, execute changes with checkpoints, and reopen service only after validation evidence passes.**
