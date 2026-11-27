# Evidence Collection, Impact Mitigation, and Post-Incident Verification in PostgreSQL

During a PostgreSQL incident, the strongest pressure is usually to restore service as quickly as possible. However, hasty actions such as restarting the server, terminating sessions in bulk, deleting WAL files, or failing over improperly can destroy evidence, prolong downtime, or turn a recoverable incident into permanent data loss.

A reliable incident response workflow requires three sequential activities: **evidence collection**, **impact mitigation**, and **post-incident verification**. Evidence reveals what is happening and guides the right action. Mitigation restores serviceability within RPO/RTO bounds while preventing further data damage. Verification proves that the database, applications, replication, backups, and critical workloads have returned to the desired state.

This lesson belongs to the **Troubleshooting** chapter of the *Database Engine Relational PostgreSQL* module. It covers structuring incident response, recording timelines and initial state, using PostgreSQL catalogs/statistics alongside OS/container telemetry, handling common failure scenarios, controlling risky actions, verifying data and services after mitigation, and converting findings into operational improvements.

> **Principle:** Before altering system state, capture any evidence that action might erase. Choose the smallest mitigation that reduces impact, state clear stop/rollback conditions, and verify with independent metrics and data checks.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish symptoms, impact, root cause, mitigation, and recovery.
2. Structure incident response with severity, owners, timelines, and decision logs.
3. Capture PostgreSQL evidence before restarting, canceling queries, or failing over.
4. Use `pg_stat_activity`, `pg_locks`, `pg_blocking_pids`, and statistics views.
5. Inspect connections, long-running transactions, lock waits, and query activity.
6. Collect WAL, replication, archiver, slot, and vacuum evidence.
7. Correlate database metrics with OS, storage, container, and Kubernetes events.
8. Preserve logs, query samples, configuration, and timestamps without exposing secrets.
9. Select narrowly scoped, reversible mitigations.
10. Handle connection exhaustion, lock contention, and slow queries.
11. Handle disk pressure, WAL growth, replication lag, and autovacuum issues.
12. Handle startup failures, crash recovery, backup failures, and failovers.
13. Know when to halt intervention and switch to recovery/DR procedures.
14. Verify service health, data integrity, replicas, and backups after mitigation.
15. Produce incident reports, root-cause analyses, and follow-up actions.

## 2. Distinguishing Symptom, Impact, Cause, and Recovery

During an incident, these terms are often conflated:

- **Symptom:** what is observed, such as query timeouts, `connection refused`, or replica lag.
- **Impact:** what users or the business actually suffer, such as failed checkouts, stale data, or API p99 breaching SLOs.
- **Cause:** the underlying mechanism producing the symptom, such as a lock queue, storage latency, a connection leak, or a release changing query plans.
- **Mitigation:** an action that reduces immediate impact during the incident, such as throttling traffic, canceling a verified runaway query, or expanding volume capacity.
- **Recovery:** restoring the system to a stable operating posture, including data, replicas, backups, and downstream consumers.

A single symptom can have many causes. For example, a connection timeout can stem from an exhausted pooler, PostgreSQL hitting connection slots, network failure, DNS, or a server undergoing recovery. Never select a mitigation based on one symptom alone.

### 2.1. Classifying by Impact

Assess:
- How many users, tenants, or services are affected?
- Are reads, writes, or both disrupted?
- Are there committed transactions not yet replicated or archived?
- Is there risk of data loss or duplicate processing?
- Is the incident spreading across other databases or regions?
- Are RPO, RTO, or availability SLOs breached?
- Are backup, restore, or failover capabilities impaired?

### 2.2. Distinguishing Service Degradation from Data Integrity Incidents

A database may keep accepting connections while returning wrong results, missing rows, or committing duplicates. Whenever data integrity is in doubt, do not measure availability alone. Preserve transaction IDs, request IDs, keys, and evidence for reconciliation.

### 2.3. Severity Must Reflect Impact

Severity should not be determined solely by 100% CPU or a single red alert. A brief CPU spike might cause zero user impact; a slow query in a critical checkout workflow can lose revenue even at low CPU. Classify severity using SLOs and business impact.

## 3. Overall Incident Response Workflow

Reference workflow:

```text
DETECT
  Alert / report / SLO breach
       |
       v
ASSESS
  Scope, severity, user impact, data risk
       |
       v
PRESERVE EVIDENCE
  Timeline, logs, sessions, locks, WAL,
  replication, storage, config and versions
       |
       v
MITIGATE
  Smallest safe action with an owner
       |
       v
VERIFY
  Database + application + data + replicas
       |
       v
STABILIZE
  Observe through a representative workload window
       |
       v
REVIEW
  Root cause, prevention, runbooks and owners
```

### 3.1. Assign Incident Roles

Depending on organization size, assign roles:
- Incident lead: coordinates, prioritizes, and makes decisions.
- Database operator: gathers evidence and executes database actions.
- Application owner: checks releases, traffic, and request behavior.
- Infrastructure/storage owner: checks hosts, disks, networks, and cloud volumes.
- Communications owner: updates stakeholders on status.

One person may wear multiple hats in smaller incidents, but accountability for each decision must remain explicit.

### 3.2. Maintain a Timeline from the Start

Record timestamps for:
- First alert.
- Start of user impact.
- Most recent deployment or configuration change.
- Appearance of new symptoms.
- Each mitigation executed.
- Database/replica recovery.
- Traffic restoration.
- Incident closure.

Use timestamps with explicit timezones—ideally storing UTC alongside the operator's local display timezone. Synchronize clocks across databases, applications, hosts, and monitoring.

### 3.3. Keep a Decision Log

For every significant action, record:
- Hypothesis being tested.
- Supporting evidence.
- Operator/approver.
- Expected blast radius.
- Observed outcome.
- Rollback criteria or next step.

This prevents multiple operators from applying conflicting changes during the same incident.

## 4. Capturing Evidence Before Changing State

Some evidence disappears when you:
- Restart PostgreSQL, a container, or a host.
- Terminate backend sessions.
- Cancel queries.
- Fail over or promote a standby.
- Reset statistics.
- Rotate or truncate logs.
- Modify configuration.
- Delete or replace a volume.
- Run state-altering maintenance commands.

Therefore, if the system is stable enough, capture an initial snapshot before applying mitigations.

### 4.1. Minimum Evidence

Depending on the incident, record:
- Date, time, timezone, and incident ID.
- PostgreSQL version and image/package digest.
- Database, cluster, node, and role (primary/standby).
- `application_name`, client addresses, and deployment versions.
- Relevant settings from `pg_settings`.
- Active sessions and wait events.
- Blocking and blocked PIDs.
- Long transactions and prepared transactions if any.
- Replication state, slots, and WAL archive status.
- Database/table sizes and filesystem capacity.
- CPU, memory, I/O, network, and container events.
- PostgreSQL and application logs.
- Recent deployments and configuration changes.
- Backup status and latest restore point.

### 4.2. Prefer Read-Only Diagnostics

Catalog and statistics queries are typically the lowest-impact starting point. Even so, they still consume connections and CPU and can expose sensitive data. Run them with an appropriately privileged role, limit output size, and avoid aggressive polling.

### 4.3. Take Multiple Snapshots Over Time

A single snapshot shows only one point in time. During ongoing incidents, sample periodically at reasonable intervals to see whether:
- Waits are growing or shrinking.
- Specific PIDs persist.
- Replication lag keeps rising.
- WAL generation exceeds replay speed.
- Disk usage climbs steadily.
- Mitigations are improving metrics.

Do not hammer the server with heavy queries just to collect more samples.

### 4.4. Do Not Reset Statistics Before Saving a Snapshot

Functions like `pg_stat_reset()` erase counters needed for investigation. Before any reset, export current numbers and record the timestamp. During an incident, keep counters intact for comparison.

## 5. Confirming Database Identity, Version, and Role

Start by verifying the exact server the operator is connected to:

```sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    pg_backend_pid() AS backend_pid,
    version() AS server_version,
    pg_is_in_recovery() AS is_standby;
```

### 5.1. Why Confirm the Endpoint?

Poolers, proxies, DNS, and failover endpoints can route connections to another node. An operator may assume they are inspecting the primary while actually connected to a standby or a different cluster.

### 5.2. Confirm Recovery State

`pg_is_in_recovery()` returns `true` on a standby in recovery. Prior to any write or failover action, verify node role via your HA mechanism rather than relying on hostnames alone.

### 5.3. Collect Relevant Settings

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'shared_buffers',
    'work_mem',
    'maintenance_work_mem',
    'statement_timeout',
    'lock_timeout',
    'idle_in_transaction_session_timeout',
    'shared_preload_libraries',
    'wal_level',
    'max_wal_size',
    'archive_mode',
    'synchronous_commit'
)
ORDER BY name;
```

Available settings depend on PostgreSQL version. Capture only settings relevant to the incident; there is no need to dump every parameter into public chat channels.

### 5.4. Record Configuration Source

`pg_settings.source` identifies where each setting comes from. You can inspect `pg_file_settings` to see file contents and parse errors if your role has privileges. Redact secrets and connection strings before storing or sharing.

## 6. Collecting Session and Query Activity

`pg_stat_activity` is the starting point for viewing server processes and client sessions.

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 1000) AS query_sample
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
```

### 6.1. Understanding `state`

Common states:
- `active`: backend is executing a query.
- `idle`: waiting for the next command.
- `idle in transaction`: transaction is open, but no query is running.
- `idle in transaction (aborted)`: transaction hit an error and awaits rollback/closure.
- `fastpath function call`: backend is executing a fast-path function call.

An `idle` session is not necessarily an error. Prolonged `idle in transaction` sessions can hold locks and snapshots, blocking vacuum.

### 6.2. Understanding `wait_event_type` and `wait_event`

If an active backend shows a wait event, time may be spent waiting on locks, I/O, client, IPC, or another wait category. `active` does not automatically mean running on CPU.

Wait event names and categories can vary by major version. Consult `pg_wait_events` if available and cross-check against your running version.

### 6.3. Do Not Treat Query Text as Complete Evidence

Query text may be truncated by `track_activity_query_size`, contain sensitive literals, or omit prepared statement parameters. Combine query ID, application logs, and trace/request IDs when needed.

### 6.4. Distinguish Query Age from Transaction Age

A query may have just started inside an old open transaction. Transaction age matters because snapshots and locks can be held across multiple statements. Never sort solely by `query_start`.

### 6.5. Application Name

Set `application_name` by service, worker, and version to distinguish traffic sources. If all clients use the same string or leave it blank, tracing connection ownership is much harder.

## 7. Finding Blocking Sessions and Lock Queues

Lock contention can queue up many requests behind a single transaction holding a lock.

### 7.1. Using `pg_blocking_pids`

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocked.state AS blocked_state,
    blocked.wait_event_type,
    blocked.wait_event,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    left(blocker.query, 1000) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
ORDER BY blocked.query_start;
```

### 7.2. Finding the Root Blocker

Blocking chains can span multiple levels. A blocked backend may simultaneously be blocking other backends. Find the session at the head of the chain holding the contended lock rather than acting blindly on the first PID seen in an alert.

### 7.3. Checking Long-Open Transactions

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xid,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 1000) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 7.4. Inspecting Lock Details

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.transactionid,
    a.application_name,
    a.state,
    a.xact_start,
    left(a.query, 500) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
ORDER BY l.granted, l.pid;
```

`relation::regclass` may not resolve to a relation name for every lock type. Transaction, virtual transaction, and object locks populate different fields; preserve `locktype` and all identifiers during analysis.

### 7.5. Checking Queued DDL

A DDL statement waiting for `AccessExclusiveLock` can build a queue behind it. New queries targeting the same relation will queue behind the DDL, spreading user impact rapidly even before the DDL acquires its lock. Record the waiter/blocker chain before canceling the migration.

## 8. Checking Connection Capacity

When applications report connection timeouts, determine whether the pooler or PostgreSQL is out of capacity.

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY connections DESC;
```

Total connections against configured limit:

```sql
SELECT
    count(*) AS current_connections,
    current_setting('max_connections')::integer AS max_connections
FROM pg_stat_activity;
```

### 8.1. Distinguishing Server Slots from Application Pools

Check:
- Application pool queues and pool exhaustion.
- Pooler client and server connection counts.
- PostgreSQL backend count.
- Reserved slots and per-role connection limits.
- Background workers and replication connections.
- Connection churn and reconnect storms.

An application pool can run out of connections while PostgreSQL still has free slots; conversely, PostgreSQL can run out of slots while pools keep trying to open more.

### 8.2. Idle in Transaction

These sessions can hold locks and snapshots and block vacuum cleanup. Capture PID, app, transaction age, and owner before acting.

### 8.3. Do Not Increase `max_connections` Immediately

Increasing `max_connections` raises maximum potential backend resource usage. If the root cause is a connection leak or query queue, raising the limit can push the server into memory pressure and worsen the incident.

### 8.4. Verify Reserved Capacity

Some PostgreSQL versions provide reserved connection settings outside `max_connections`. Verify configuration and privileges for emergency operator access before an incident strikes.

## 9. Collecting WAL, Replication, and Archive Evidence

When replica lag climbs or recovery stalls, pinpoint whether the bottleneck is primary send, network, standby write, or replay.

### 9.1. Primary: `pg_stat_replication`

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

Fields and lag semantics vary by version. Lag columns can become `NULL` when no recent WAL activity occurred; never interpret `NULL` simply as zero lag.

### 9.2. Standby: `pg_stat_wal_receiver`

```sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
```

This view returns no rows if the server is not running a WAL receiver or is in another mode. Correlate timestamps with primary and network metrics.

### 9.3. Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    temporary
FROM pg_replication_slots
ORDER BY slot_name;
```

An inactive slot can retain WAL and fill the filesystem. Never drop a slot just to reclaim disk before confirming its consumer and resync/reseed path. Additional columns like `wal_status` and `safe_wal_size` depend on PostgreSQL version.

### 9.4. Archive Status

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

If archive failures rise, check the archive destination, permissions, credentials, network, and archive command logs. WAL archive backlogs affect both PITR readiness and disk capacity.

### 9.5. Assessing WAL Pressure

Collect:
- WAL directory size.
- `pg_wal_lsn_diff` between relevant LSNs.
- Slot `restart_lsn`.
- Archive success and failures.
- Replica receive/write/flush/replay progress.
- Checkpoint and WAL generation metrics.
- Free disk space.

Never judge replica lag solely from `pg_wal` directory size; retention settings and checkpoint behavior also affect its size.

## 10. Collecting Vacuum, Bloat, and Table Health Evidence

Blocked or lagging autovacuum causes table/index bloat, transaction ID pressure, and disk growth.

### 10.1. Autovacuum Activity

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_stat_progress_vacuum
ORDER BY datname, relation_name;
```

Views and columns vary across PostgreSQL versions; inspect progress views on your running server.

### 10.2. Dead Tuples and Vacuum Timestamps

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

Tuple counts are estimates, not exact counts. Use them to spot trends and target objects for investigation.

### 10.3. Long-Running Snapshots

Transaction age, `backend_xmin`, replication slots, and standby feedback can pin the `xmin` horizon. Identify which consumer pins the horizon before tweaking vacuum settings.

### 10.4. Transaction ID Age

Track database and relation ages to detect wraparound risk early. When anti-wraparound autovacuum warnings appear, follow PostgreSQL's wraparound runbook and never disable autovacuum arbitrarily.

### 10.5. Do Not Run `VACUUM FULL` Reflexively

`VACUUM FULL` acquires exclusive locks, rewrites the entire table, and can consume massive disk space. Mid-incident, it typically increases downtime and impact. Identify root causes, blockers, and schedule proper maintenance first.

## 11. Collecting Query Performance Evidence

When an endpoint slows down, identify the query fingerprint and recent changes.

### 11.1. `pg_stat_statements`

If installed and configured:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    left(query, 1000) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Columns vary with extension version. Counters accumulate since the last reset, so save snapshots and compute deltas across the incident window.

### 11.2. `EXPLAIN ANALYZE` Has Real Side Effects

`EXPLAIN ANALYZE` actually executes the query. `SELECT` queries still consume CPU and I/O; `UPDATE`/`DELETE` statements modify real data. Use a clone/staging instance or pick safe representative queries with strict guardrails in production.

### 11.3. Capture the Plan Before Changing Indexes or Settings

Save the plan, settings, parameters, and statistics context before modifying indexes, `work_mem`, planner knobs, or queries. Afterward, compare plans and real workload impact.

### 11.4. Do Not Force the Planner Globally to Fix One Query

Settings like `enable_seqscan` or `enable_nestloop` are useful for diagnostic sessions, yet changing global configuration to force one plan often regresses other workloads.

### 11.5. Correlate Queries with Application Traces

Use request IDs, trace IDs, `application_name`, query IDs, and timestamps to tie queries to endpoints and releases. Avoid pasting sensitive bind values into incident reports.

## 12. Combining PostgreSQL Evidence with OS and Platform Telemetry

Database statistics show what backends are doing; OS/platform metrics show whether underlying resources can keep up.

### 12.1. CPU and Run Queue

Linux:
```bash
uptime
vmstat 1 5
top -b -n 1
```

High CPU can come from queries, autovacuum, compression, encryption, background workers, or unrelated host processes. Match PIDs, processes, and containers before concluding.

### 12.2. Memory and OOM

```bash
free -h
cat /proc/meminfo
dmesg -T | tail -n 100
```

Containers and Kubernetes pods can have memory limits lower than host RAM. Inspect cgroup memory metrics, `OOMKilled` events, and container limits.

### 12.3. Disk and Inode Pressure

```bash
df -h
df -i
lsblk
du -xhd1 /var/lib/postgresql
```

Running `du` on large data directories generates substantial I/O; scope it tightly and use it judiciously. A full filesystem may differ from the filesystem holding `PGDATA`, `pg_wal`, temp files, or tablespaces.

### 12.4. Storage Latency

```bash
iostat -xz 1 5
```

Watch `await`/latency, queue depth, and utilization per device. Exact metric names vary by OS and tool version.

### 12.5. Network

Check packet loss, retransmits, connection resets, DNS resolution, firewalls/security groups, and throughput between primary, standbys, poolers, and applications. A query waiting on client/network I/O is not a server CPU bottleneck.

### 12.6. Container Logs and Events

Docker:
```bash
docker ps -a
docker inspect <container>
docker logs --since 30m <container>
```

Kubernetes:
```bash
kubectl get pods -o wide
kubectl describe pod <pod>
kubectl logs <pod> --since=30m
kubectl get events --sort-by=.lastTimestamp
```

These commands may output sensitive environment variables, mount paths, labels, or query text. Redact before sharing.

### 12.7. Cloud Storage Events

Check volume throttling, attach/detach events, burst balance/credits where applicable, IOPS caps, and provider maintenance events. Never look solely at database instance CPU.

## 13. Collecting Logs and Preserving Chain of Evidence

Logs often hold the clearest record of event sequencing.

### 13.1. PostgreSQL Logs

Look for:
- `FATAL`, `PANIC`, `ERROR`, `WARNING`.
- Checkpoint warnings and durations.
- Deadlock reports.
- Recovery and startup messages.
- WAL and archive errors.
- Autovacuum cancellations.
- Connection authentication failures.
- Out-of-memory and disk errors.
- Extension and background worker crashes.

### 13.2. Application Logs

Collect SQLSTATE, endpoint, deployment version, retry counts, connection pool metrics, and request IDs. Avoid recording only a vague "database timeout" without knowing which timeout phase expired.

### 13.3. Log Rotation

Record filenames/log streams, timestamp ranges, rotation boundaries, and retention. Copy or export logs without altering files currently open by PostgreSQL.

### 13.4. Evidence Integrity

When an incident requires formal auditability:
- Store read-only copies.
- Record source and collection timestamps.
- Compute checksums for artifacts if policy requires.
- Restrict access controls.
- Document any redactions.
- Never alter original files.

### 13.5. Data Minimization

Query text, parameters, usernames, client IPs, and logs can contain PII, tokens, or secrets. Collect only what is needed, redact per policy, and use approved sharing channels.

## 14. Choosing Mitigations: Reduce Impact First

A good mitigation typically has these traits:
- Targets an identified workload, session, or resource.
- Has a small blast radius.
- Is reversible.
- Preserves data integrity.
- Has metrics to measure effectiveness.
- Has an owner and expiration time.
- Does not destroy critical evidence.

### 14.1. Prefer Traffic Shaping

Reduce impact by:
- Rate-limiting an endpoint or workload.
- Pausing non-critical batch jobs.
- Lowering worker concurrency.
- Capping retry storms.
- Queueing work for later processing.
- Routing reads to replicas if consistency policies allow.

### 14.2. Do Not Pile Load Onto an Incident

Avoid full table scans, full dumps, index builds, or heavy diagnostic polling loops against an overloaded primary unless genuinely needed. Collect evidence selectively and offload heavy inspection to replicas or clones where appropriate.

### 14.3. Apply One Mitigation at a Time

If you simultaneously restart, raise connection limits, tweak planner settings, and kill sessions, you cannot tell which change helped or caused a new regression. Apply changes one step at a time with observation, unless an established emergency procedure dictates otherwise.

### 14.4. Define Rollback Triggers

For example: if p95 does not improve after an observation window, error rates climb, or replication lag exceeds a threshold, halt the change and revert. Define thresholds before executing.

## 15. Canceling Queries and Terminating Backends Safely

PostgreSQL provides functions to request query cancellation or session termination.

### 15.1. Canceling a Query

```sql
SELECT pg_cancel_backend(12345);
```

Requests cancellation of the backend's current query. The session remains open; an aborted transaction may require the client to roll back. The boolean return value indicates only whether the signal was sent, not that all cleanup finished.

### 15.2. Terminating a Session

```sql
SELECT pg_terminate_backend(12345);
```

Terminates the backend session. Active transactions roll back, which can consume time and resources. Locks release once transaction and session cleanup finishes.

### 15.3. Before Canceling or Terminating

Verify:
- Which database and cluster the PID belongs to.
- Which application and owner own it.
- Query details and transaction age.
- Whether the backend is a replication, autovacuum, logical worker, or maintenance process.
- Whether the query is performing business-critical work.
- Whether retries might trigger duplicate side effects.
- Whether you can rate-limit the source instead of killing sessions.

### 15.4. Do Not Bulk-Terminate by State

Bulk-terminating all `idle` or all `active` sessions can disrupt healthy workloads. Act only on verified PIDs with documented justification and an accountable owner.

### 15.5. Do Not Kill OS Processes Directly as a First Resort

Use PostgreSQL's cancellation/termination APIs whenever possible. Killing processes at the OS level bypasses graceful cleanup and can trigger crash recovery. Use OS-level procedures only when PostgreSQL control paths are unresponsive and your runbook authorizes it.

## 16. Handling Connection Exhaustion

Symptoms:
- Applications fail to borrow connections.
- PostgreSQL reports `too many connections`.
- Pool wait times climb.
- `idle in transaction` or `idle` counts spike abnormally.

Workflow:
1. Snapshot connection counts by app, user, and state.
2. Inspect pooler and application pool queues.
3. Identify connection leaks, retry storms, or rollouts spawning oversized pools.
4. Throttle incoming traffic or worker concurrency.
5. Fix pool sizing or connection lifecycle bugs.
6. Terminate only verified orphan/stale sessions with approval.
7. Verify free slots, pool wait times, and request error rates.

### 16.1. Pool Sizing

Sum connections across all replicas and workers. For instance, 20 pods × pool size 30 can open 600 server connections before counting admin, monitoring, and replication.

### 16.2. Idle Sessions Do Not Always Need Killing

Poolers keep idle connections warm for reuse. Evaluate against pool policy, idle age, and capacity. Prefer adjusting pools and traffic at the application layer.

### 16.3. Emergency Access

Maintain an emergency role/process with suitable privileges and reserved connection capacity so operators can still diagnose when applications consume all normal slots. Check version-specific reserved connection settings.

## 17. Handling Lock Contention and Deadlocks

Symptoms:
- Query wait events show `Lock`.
- Multiple requests wait on the same relation or transaction.
- DDL migrations fail to acquire locks.
- Deadlock errors spike.

Workflow:
1. Capture the blocking tree and `pg_locks`.
2. Identify the root blocker, transaction age, and owner.
3. Check recent deployments, migrations, and batch jobs.
4. Throttle traffic piling onto the waiter queue if needed.
5. Contact the owner to commit or roll back the transaction if possible.
6. Cancel the query or terminate the verified session after assessing impact.
7. Confirm lock queues clear and request latency recovers.

### 17.1. Long Transactions

Long-open transactions hold row/table locks and snapshots. An `idle in transaction` blocker usually points to application code or connection pool lifecycle bugs.

### 17.2. Deadlocks

PostgreSQL detects deadlocks automatically and aborts one transaction. Inspect deadlock logs to uncover conflicting lock orders. Long-term fixes are consistent lock ordering, shorter transactions, and bounded retry logic for SQLSTATE `40P01`.

### 17.3. DDL Lock Queues

If DDL is waiting on a strong lock, consider canceling the queued migration before it piles up a long queue behind it. Then resolve the blocker and reschedule with an appropriate `lock_timeout`.

### 17.4. Do Not Run Heavy `VACUUM FULL` or `REINDEX` Mid-Lock Incident

These operations demand strong locks and heavy resources. Gather evidence, stabilize traffic, and schedule separate maintenance windows.

## 18. Handling Slow Queries and CPU Saturation

Symptoms:
- Query latency climbs.
- CPU usage is high.
- Throughput drops.
- Pool queues grow because connections are held longer.

Workflow:
1. Identify query fingerprints and application versions.
2. Capture `pg_stat_activity` and `pg_stat_statements`.
3. Inspect wait events to separate CPU-bound, I/O-bound, and lock-bound queries.
4. Compare query plans against baselines.
5. Inspect statistics, data skew, and index changes.
6. Throttle or pause non-critical workloads.
7. Roll back releases or config changes causing regressions when evidence supports it.
8. Verify latency and resource usage post-mitigation.

### 18.1. Do Not Run `EXPLAIN ANALYZE` Carelessly

Test queries can burn heavy CPU/I/O or mutate data. Run representative queries on clones/staging whenever possible.

### 18.2. Do Not Create Indexes Mid-Incident Without Assessment

Index builds consume heavy I/O and WAL and contend with impacted workloads. If an index is the chosen mitigation, evaluate `CREATE INDEX CONCURRENTLY`, disk headroom, locks, and rollback first.

### 18.3. Query Cancellation

If a verified runaway query causes severe impact, consider canceling that specific query after saving PID/query evidence and checking retry semantics. Never terminate an entire application pool.

### 18.4. `work_mem`

Raising `work_mem` can reduce spills for a specific query, yet memory allocates per operation/worker rather than once per server. Raising it globally mid-incident can spike RAM under high concurrency. If needed, test within controlled session/workload scope.

## 19. Handling Disk Full and Storage Pressure

Disk exhaustion prevents PostgreSQL from writing WAL, temp files, relation updates, or logs.

Workflow:
1. Identify which filesystem/volume is actually full.
2. Check `PGDATA`, `pg_wal`, tablespaces, temp paths, and log mounts.
3. Capture `df`, inode usage, volume metrics, and growth timeline.
4. Identify the cause: WAL retention, archive failures, inactive replication slots, runaway temp files, logs, bloat, or organic growth.
5. Expand volume capacity or provisioned throughput if supported.
6. Clean up logs, backups, or temp artifacts outside database storage per retention and ownership policies.
7. Resolve slot, archive, or transaction blockers using PostgreSQL-supported procedures.
8. Verify writes, checkpoints, archiving, and replicas resume cleanly.

### 19.1. Never Delete WAL Files via Shell

Never run `rm` on files inside `pg_wal`. PostgreSQL needs WAL for crash recovery, replication, and archiving. Manual deletion can prevent the cluster from starting or cause data loss.

### 19.2. Replication Slots Retaining WAL

Inactive slots can pin WAL indefinitely. Verify consumer status and rebuild/reseed options before dropping or recreating slots.

### 19.3. Temp Files

Temp files grow from sort/hash spills or high query concurrency. Identify offending queries/sessions, throttle workloads, or tune queries; never delete temp files actively used by running processes.

### 19.4. Inodes and Quotas

A filesystem can run out of inodes despite free bytes; PVC quotas can differ from apparent capacity. Check bytes, inodes, and provider limits together.

### 19.5. Never Delete Relation Files

Never delete files inside `base/`, `global/`, `pg_tblspc/`, or PostgreSQL-managed directories. Use SQL maintenance procedures and backup/recovery tools.

## 20. Handling WAL Archive Failures and Replication Lag

### 20.1. Archive Failures

Check:
- Archive command exit codes.
- Permissions and credentials.
- Network, DNS, and TLS.
- Destination capacity.
- Object store throttling.
- Duplicate/collision handling.
- Archive timeouts and retry logs.

When archiving stalls, WAL builds up on the primary. Restore the archive path before cleaning anything up.

### 20.2. Replication Lag

Distinguish:
- Send lag: primary has not shipped WAL fast enough.
- Write lag: standby has not written received WAL.
- Flush lag: standby has not flushed WAL to durable storage.
- Replay lag: standby received/flushed WAL yet lags in replaying it.

Use LSNs and timestamps from both nodes, network metrics, and standby storage latency.

### 20.3. Slow Standby Replay

Check standby CPU/I/O, long-running queries, recovery conflicts, `max_standby_streaming_delay`, `hot_standby_feedback`, and query workloads. Never change conflict settings without understanding read availability vs. WAL/bloat trade-offs.

### 20.4. Replication Slot Lag

Check `restart_lsn` and consumer progress. One stalled slot retaining WAL can fill the disk even while other standbys remain completely healthy.

### 20.5. Never Promote a Standby Merely Due to Lag

Promotion is an HA/data-loss decision. Verify whether the primary is still alive, fencing status, replay position, synchronous commit guarantees, and RPO before promoting.

## 21. Handling Autovacuum Falling Behind

Symptoms:
- Growing dead tuples.
- Table and index bloat.
- High transaction ID age.
- Degrading query performance.
- Rising disk usage.

Workflow:
1. Check vacuum progress views and table stats.
2. Find long transactions, prepared transactions, and `xmin` holders.
3. Check replication slots and standby feedback.
4. Identify tables with high write churn or unsuitable vacuum thresholds.
5. Ensure sufficient I/O and maintenance worker capacity.
6. Tune per-table autovacuum settings after assessment.
7. Monitor vacuum progress, dead tuples, and transaction ID age.

### 21.1. Never Disable Autovacuum as a Default Mitigation

Disabling autovacuum accelerates bloat and wraparound risk. If adjustments are needed, apply them narrowly per table/setting with an explicit owner and expiration.

### 21.2. Freeze and Wraparound

Anti-wraparound vacuums take priority even if foreground workloads feel the load. Never reflexively kill them. Check database/table ages and follow PostgreSQL wraparound recovery guidance.

### 21.3. Long-Running Transactions

A single transaction pinning an old snapshot blocks vacuum from cleaning dead tuples. Resolve the owning transaction before blindly adding workers.

## 22. Handling Startup Failures and Crash Recovery

When the server refuses connections:
1. Confirm the exact process, container, node, and endpoint.
2. Capture logs before attempting another restart or recreation.
3. Check volume attachments, read-only filesystems, disk space, and permissions.
4. Check config parse errors, missing libraries/extensions, and port conflicts.
5. Identify startup state: crash recovery, standby recovery, archive recovery, or startup failure.
6. Inspect WAL and control file errors in logs.
7. Preserve the data directory and backups/snapshots.
8. Choose a recovery procedure based on evidence.

### 22.1. Never Delete `postmaster.pid` Arbitrarily

This file holds server process metadata. Deleting it while postmaster is still alive lets a second server attempt to open the same data directory. Before handling a stale PID file, confirm zero processes are touching the cluster and follow your runbook.

### 22.2. Never Run `initdb` on an Existing Data Directory

`initdb` initializes a brand-new cluster. Running it on a path/volume containing data can overwrite or destroy state. Verify `PG_VERSION`, volume identity, and backups before any action.

### 22.3. Never Swap Major Images to Experiment

Major binary versions must match the data directory or use a supported upgrade workflow. If startup fails after an image update, preserve the source volume and revert to the matching compatible binary per rollback plan; never test multiple major binaries against the same data directory.

### 22.4. `PANIC` / Corruption Symptoms

When logs show `PANIC`, checksum errors, or I/O errors, avoid running unverified repair commands. Preserve snapshots/backups, halt writes per incident lead, and transition to corruption/recovery procedures.

## 23. Handling Failovers and Split-Brain Risk

Failover restores availability, yet poor sequencing can create dual primaries or lose acknowledged transactions.

### 23.1. Before Promotion

Confirm:
- Old primary truly cannot continue accepting writes or has been fenced.
- Candidate standby has an appropriate timeline and replay position.
- Replication mode and synchronous commit guarantees.
- Acceptable RPO.
- HA controller state and lease/leader election status.
- Application endpoint routing.

### 23.2. Fencing

Fencing ensures the old primary cannot keep accepting writes after a standby promotes. A network partition can leave the old node alive even when operators cannot reach it. Never treat failing pings as proof a node stopped.

### 23.3. After Promotion

Verify the new primary is writable, application connections route to the right endpoint, the new WAL timeline is active, replicas follow the new primary, and the old primary cannot rejoin automatically as writable.

### 23.4. Rejoining the Old Primary

Use supported rejoin, `pg_rewind`, or rebuild procedures. Never simply start the old primary on its old data directory and let it take writes.

### 23.5. Document Actual RPO Impact

Record LSN/timeline, last known commit/replication positions, and potential data loss. Communicate uncertainty honestly instead of claiming zero data loss without proof.

## 24. Handling Backup and Restore Failures

### 24.1. Backup Job Failures

Collect logs, exit codes, durations, backup type, source node, target storage, WAL/archive state, and free space. Check credentials, networking, permissions, and provider throttling.

### 24.2. A Successful Backup Does Not Guarantee Restorability

Backup completion proves only that the job finished according to the tool. Only a restore test proves artifacts, WAL chains, extension packages, and procedures suffice to recover.

### 24.3. When a Restore Fails

Leave the source backup intact. Check:
- Backup manifests and checksums.
- PostgreSQL major/minor version.
- Tablespaces.
- WAL continuity.
- Extension binaries.
- Encryption keys.
- Credentials.
- Target filesystem capacity and permissions.
- Recovery target timestamp.

### 24.4. Never Overwrite the Source Backup

Restore into a fresh target directory or volume. Keep the source backup immutable under retention rules until restore validation completes.

## 25. Using Timeouts and Cancellation Safely

Timeouts act as guardrails capping resource occupancy, though changing timeouts mid-incident can have side effects.

### 25.1. `lock_timeout`

Caps how long a statement waits for a lock. Use `SET LOCAL lock_timeout` inside transactions or migrations so DDL fails fast if locks are unavailable.

### 25.2. `statement_timeout`

Caps total statement execution time. Setting it too low server-wide can abort legitimate queries or maintenance tasks.

### 25.3. `idle_in_transaction_session_timeout`

Protects against sessions left idle inside open transactions. Evaluate application behavior and transaction boundaries before enabling broadly.

### 25.4. Client-Side Timeouts

Application or pooler timeouts can fire before the server statement timeout. Inspect how server-side queries and transactions behave when clients disconnect. Timeouts alone do not guarantee business operations roll back cleanly as intended.

### 25.5. Timeout Change Procedure

Record previous value, scope, duration, expected behavior, and rollback plan. Prefer session, role, or database scope over global changes during an incident.

## 26. Changing Configuration Mid-Incident

Some settings apply via reload; others require a restart. Some changes can escalate memory or CPU pressure.

Before changing:
1. Record current value and source.
2. Check setting `context` and `pending_restart`.
3. Assess impact across all workloads.
4. Test narrowly scoped changes first if possible.
5. Record the rollback value.
6. Watch metrics immediately after applying.

Never change multiple settings at once. If performance improves, you need to know which exact knob made the difference so you can keep or revert intentionally.

## 27. Mitigating Impact with Application-Level Controls

Database incidents often require coordination at the application layer.

### 27.1. Rate Limiting

Throttle endpoints causing query storms. Preserve capacity for authentication, checkout, or critical workflows.

### 27.2. Circuit Breakers

When the database or a downstream dependency saturates, fail fast or serve controlled fallbacks to avoid piling on load with endless retries.

### 27.3. Backoff and Jitter

Retries need exponential backoff, jitter, and maximum attempt caps. Retrying every SQLSTATE blindly risks duplicate writes or incident amplification.

### 27.4. Deferring Batch Jobs

Pause or reduce concurrency for analytics, imports, backfills, and non-critical scheduled jobs. Record backlogs to drain once the service stabilizes.

### 27.5. Read Routing

Shift read-only workloads to replicas when consistency/freshness rules permit. Never route read-after-write queries to lagging replicas.

### 27.6. Feature Flags

Disable new features generating expensive queries or releases causing regressions. Document flag state and tenant/traffic scope to avoid unintended side effects.

## 28. Immediate Post-Mitigation Verification

After each action, measure the exact metric tied to your hypothesis.

Examples:
- Canceled blocker: did lock wait counts and blocked query ages drop?
- Applied rate limit: did connection/pool queues and latency shrink?
- Expanded volume: did free space rise and can PostgreSQL write?
- Fixed archiving: did `pg_stat_archiver` failures stop rising?
- Restored replication: did replay LSN advance and lag drop?
- Rolled back release: did query plans, latency, and error rates return to baseline?

Never declare success merely because an alert cleared. Alerts can resolve because monitoring reset or upstream traffic stopped arriving.

## 29. Verifying Database Health

Verify:
- PostgreSQL processes run stably.
- Database connections succeed.
- No new startup or recovery errors appear.
- Critical settings and configurations match expectations.
- Active sessions and wait events are normal.
- Lock queues have cleared.
- Long transactions have been resolved.
- Disk space and inodes have headroom.
- WAL and archiving advance normally.
- Autovacuum and checkpoints run cleanly.
- No crash/restart loops occur.

### 29.1. Smoke Query

Run a lightweight query through the application role and production endpoint path, such as:

```sql
SELECT
    current_database(),
    current_user,
    pg_is_in_recovery(),
    now();
```

This is strictly a connectivity smoke test, not a substitute for business transaction validation.

### 29.2. Checking Connection Pools

Check application pool wait times, active/idle counts, acquisition errors, and reconnect rates. A database can be healthy while poolers still hold stale connections.

### 29.3. Checking Wait Events

Some normal wait events are always expected. Compare against baseline and workload; never demand every wait counter be zero.

## 30. Verifying Data Integrity and Business Invariants

If an incident involved write failures, retries, failover, or partial processing, validate the data.

### 30.1. Row Counts and Key Ranges

Compare counts across partitions, time windows, tenants, or business keys. Full-table `COUNT(*)` queries can burden I/O; choose meaningful scopes and use snapshots or replicas where appropriate.

### 30.2. Constraint Validation

Verify critical constraints are validated with zero violating rows. For unique/foreign-key invariants, run thorough queries rather than trusting small samples.

### 30.3. Reconciliation

Reconcile:
- Request and event IDs.
- Orders, payments, and ledger entries.
- Outbox and inbox states.
- Duplicate or missing operations.
- Aggregates or account balances.
- External system acknowledgments.

### 30.4. Idempotency and Retry Outcomes

After retry storms or client timeouts, determine which requests committed on the server even though clients lost responses. Reconcile using idempotency keys and transaction records before replaying anything.

### 30.5. Never Run Repair SQL Without a Dry Run

Before bulk `UPDATE`/`DELETE` repairs:
- `SELECT` the target rows first.
- Save row counts and sample keys.
- Verify mapping and expected values.
- Test on a clone whenever possible.
- Batch modifications with checkpoints.
- Wrap cleanly in transactions.
- Prepare backup, rollback, and reconciliation plans.

## 31. Verifying Replication, Archiving, and Backups

Applications may be serving traffic again while disaster recovery posture remains degraded.

### 31.1. Replication

Verify the primary sees expected standbys in `streaming` state, LSNs advance, lag returns within budget, and no slots pin excessive WAL.

### 31.2. Archiving

Confirm new WAL archives cleanly and can be read back from archive storage. A recent archive success metric alone does not prove the entire WAL chain from the base backup remains unbroken.

### 31.3. Backups

Confirm the latest backup:
- Completed successfully.
- Has a valid manifest/checksum.
- Resides on independent storage.
- Meets retention policy.
- Can restore cleanly under current procedures.

### 31.4. Post-Incident Restore Point

After data repairs or failovers, take a fresh backup and record the new recovery point. Never overwrite pre-incident backups before checking retention and legal requirements.

### 31.5. DR Readiness

If failover or restore occurred, re-establish the DR topology and re-test replication and restores. Never close an incident when only the primary is up while standbys remain detached.

## 32. Verifying Applications and End-to-End Service

Verify outside the database:
- Critical API success and error rates.
- p50/p95/p99 latency.
- Pool acquisition times.
- Business transaction completion.
- Queue backlogs and worker lag.
- Scheduled jobs.
- Cache invalidation and refresh.
- CDC, ETL, and analytics consumers.
- External integrations.

### 32.1. Synthetic Transactions

Run identifiable synthetic test transactions that can be cleaned up or reconciled. Never trigger real external side effects like payments or emails without sandboxes or guards.

### 32.2. Traffic Canaries

Re-open traffic incrementally after severe incidents. Monitor error, latency, and resource budgets before increasing further.

### 32.3. Observe a Representative Window

Observation must span relevant peak traffic, scheduled jobs, or batch cycles. One healthy minute after a restart does not prove an incident is over.

## 33. When to Escalate or Halt Intervention

Escalate to the incident lead, DBA, or DR owner when:
- Signs of data corruption or checksum errors appear.
- It is unclear which primary is authoritative.
- Split-brain risk exists.
- WAL chain or backup integrity is uncertain.
- Storage reports I/O errors.
- Direct operations on data files or control files seem needed.
- Dropping a replication slot or changing a recovery target is proposed.
- Cluster restore, rewind, or reseed is required.
- Bulk repairs could alter large volumes of data.
- RPO or RTO may be breached.

When state is unclear, keep source data intact and gather evidence. Never try random repair commands to see which one runs.

## 34. Incident Handoff and Communication

A good handoff lets the incoming responder grasp current state without restarting the investigation from scratch.

Record:
- Incident summary and severity.
- User and business impact.
- Affected clusters, databases, and nodes.
- Timeline.
- Current primary/standby roles.
- Evidence links and locations.
- Actions already taken.
- Current metrics and state.
- Data integrity concerns.
- Pending decisions.
- Recommended next action.
- Owner and escalation contact.

Clearly distinguish verified facts from hypotheses and unknowns. Avoid calling an incident "fixed" until verification criteria pass.

## 35. Post-Incident Review and Root-Cause Analysis

The goal is reducing the likelihood and impact of recurrence, not assigning blame.

### 35.1. Timeline

Reconstruct from alerts, logs, deploy events, database stats, and operator notes. Use consistent timestamps and mark evidence gaps explicitly.

### 35.2. Root Cause and Contributing Factors

Distinguish:
- Triggering event.
- Technical root cause.
- Contributing conditions.
- Detection gaps.
- Mitigation delays.
- Recovery bottlenecks.

For example, a query regression may be triggered by a release, while contributing factors include missing plan-regression tests, stale statistics, and lacking query-level alerts.

### 35.3. Five Whys Is a Tool, Not the End Goal

Use questioning to uncover system mechanisms and control gaps. Never force a multi-factor incident into a single artificial root cause when multiple conditions interacted.

### 35.4. Blameless Review

Focus on system design, tooling, runbooks, observability, permissions, deployment controls, and capacity planning. Record concrete action items with owners and due dates.

### 35.5. Action Items

Categorize into:
- Prevention: reduce probability of occurrence.
- Detection: catch issues earlier.
- Mitigation: shrink blast radius.
- Recovery: shorten recovery time.
- Evidence: ensure better diagnostics in future incidents.

## 36. Incident Report Template

You can use the following structure:

```markdown
# PostgreSQL Incident Report

## Summary
- Incident ID:
- Severity:
- Start/end time (UTC):
- Affected cluster/database:
- User impact:

## Timeline
- Detection:
- First symptom:
- Mitigations:
- Recovery:
- Verification complete:

## Evidence
- PostgreSQL version/role:
- Relevant logs:
- Sessions/locks:
- Query IDs/plans:
- WAL/replication:
- Storage/OS:
- Recent changes:

## Actions
- Action:
- Owner:
- Reason/evidence:
- Result:
- Rollback:

## Data and recovery
- Integrity checks:
- Replicas:
- WAL archive:
- Backup/restore point:
- RPO/RTO impact:

## Root cause
- Trigger:
- Root cause:
- Contributing factors:
- Detection/recovery gaps:

## Follow-up
- Prevention:
- Detection:
- Mitigation:
- Recovery:
- Owner/due date:
```

Do not include secrets, raw credentials, or unnecessary PII in reports.

## 37. Practice Walkthrough: Connection Storm After Deployment

**Symptom:** APIs begin timing out right after deploying a new release. PostgreSQL connection count climbs rapidly.

**Evidence Collection:**
1. Confirm primary endpoint and version.
2. Query connections grouped by `application_name`, `state`, and user.
3. Pull pool metrics from every application replica.
4. Record deployment timestamp and version.
5. Check long transactions and wait events.
6. Inspect CPU, memory, and database error logs.

**Hypothesis:** Each application pod opened an oversized pool or retry logic triggered a reconnect storm.

**Mitigation:**
1. Rate-limit non-critical endpoints.
2. Reduce worker concurrency or pause batch jobs.
3. Roll back the deployment if evidence ties directly to the release.
4. Terminate only verified orphan/stale sessions if needed.

**Verification:**
- Connection count returns within capacity budget.
- Pool acquisition wait drops.
- API error rates and p95/p99 recover.
- Business writes show no duplicates.
- Worker backlog drains cleanly.

## 38. Practice Walkthrough: DDL Causing a Lock Queue

**Symptom:** Many queries on a table wait on locks; a migration is running or queued.

**Evidence Collection:**
- Blocking tree via `pg_blocking_pids`.
- DDL query and migration owner.
- Blocker transaction age.
- Waiting queries and target relation.
- Recent application release or migration event.

**Mitigation:**
1. Pause additional traffic to the table if needed.
2. Determine whether the DDL is actively executing or waiting.
3. If queued DDL is blocking traffic behind it, consider canceling the DDL per migration runbook.
4. Resolve the blocking transaction with its owner.
5. Retry the migration with a `lock_timeout` during an appropriate window.

**Verification:**
- Lock queue clears.
- Application queries complete normally.
- Migration state is consistent.
- Constraints and indexes are verified.
- No partial migration steps were left incomplete.

## 39. Practice Walkthrough: Replication Lag and WAL Disk Growth

**Symptom:** Primary disk grows rapidly; standby replay lag climbs.

**Evidence Collection:**
- `pg_stat_replication` on primary.
- `pg_stat_wal_receiver` on standby.
- Replication slots and `restart_lsn`.
- `pg_stat_archiver`.
- Disk/IOPS/latency on both nodes.
- WAL generation rate and application write throughput.

**Mitigation:**
1. Pinpoint whether the bottleneck is send, network, write, flush, or replay.
2. Throttle non-critical bulk writes or backfills.
3. Fix the archive destination if failing.
4. Expand volume capacity if needed and supported.
5. Handle inactive slots only after confirming owner and rebuild path.

**Verification:**
- Receive/flush/replay LSNs advance.
- Lag drops within budget.
- WAL retention stabilizes.
- Archiving succeeds again.
- Standby serves workloads within freshness requirements.

## 40. Practice Walkthrough: Volume Nearly Full

**Symptom:** Writes start failing and the primary volume is nearly out of space.

**Evidence Collection:**
- Filesystem and inode usage.
- `PGDATA`, `pg_wal`, tablespaces, and temp paths.
- Replication slots.
- Archive failures.
- Long-running transactions.
- Backup and log growth.

**Mitigation:**
1. Expand the volume if possible.
2. Pause workloads generating heavy WAL.
3. Fix archive failures or consumer lag.
4. Clean up artifacts outside PostgreSQL's data directory per retention policy.
5. Never delete WAL or relation files via shell.

**Verification:**
- Free space has headroom.
- PostgreSQL writes and flushes WAL normally.
- Checkpoints and archiving proceed.
- Replicas catch up.
- A fresh backup completes.

## 41. Evidence Collection Checklist

- [ ] Incident ID, severity, and timeline recorded.
- [ ] Cluster, database, endpoint, and primary/standby role confirmed.
- [ ] PostgreSQL version, image/package, and recent deployments recorded.
- [ ] `pg_stat_activity` snapshot saved.
- [ ] Blocking PIDs and lock details saved.
- [ ] Long transactions and `idle in transaction` sessions identified.
- [ ] Connection counts and pool metrics saved.
- [ ] WAL, replication, slots, and archive state saved.
- [ ] Vacuum progress and transaction ID age checked.
- [ ] Query fingerprints and plans saved when needed.
- [ ] CPU, memory, disk, I/O, network, and platform events correlated.
- [ ] Logs exported with timestamps.
- [ ] Secrets and PII redacted per policy.
- [ ] Statistics left unreset prior to snapshotting.

## 42. Impact Mitigation Checklist

- [ ] Impact and data-loss risk assessed.
- [ ] Incident owner and action owner clearly assigned.
- [ ] Smallest appropriate scoped mitigation selected.
- [ ] Evidence captured prior to state-altering actions.
- [ ] Traffic, retries, and batch concurrency controlled.
- [ ] Cancel/terminate restricted strictly to verified PIDs.
- [ ] No WAL, relation files, or data directories deleted via shell.
- [ ] No failover executed without fencing and RPO evaluation.
- [ ] Config changes have old values and rollback plans documented.
- [ ] Every action has verification metrics and stop conditions.

## 43. Post-Incident Verification Checklist

- [ ] PostgreSQL startup and recovery are stable.
- [ ] Critical connections and queries succeed.
- [ ] Lock queues and long transactions are cleared.
- [ ] Disk, memory, CPU, and I/O have headroom.
- [ ] Query latency and throughput returned to SLOs.
- [ ] Application pools and worker queues are normal.
- [ ] Data integrity and reconciliation checks passed.
- [ ] Primary/standby roles and replication lag are healthy.
- [ ] WAL archiving operates normally.
- [ ] Fresh backup status and restore path verified.
- [ ] DR topology restored if impacted.
- [ ] Observed across a full representative workload window.
- [ ] Incident timeline, decision log, and follow-up items saved.

## 44. Best Practices

- Capture snapshots before restarting, terminating, failing over, or resetting statistics.
- Confirm database identity and primary/standby role before taking action.
- Use `pg_stat_activity`, `pg_locks`, `pg_blocking_pids`, and replication views appropriate to your version.
- Correlate database evidence with OS, storage, container, and application telemetry.
- Record timestamps/timezones, application versions, request IDs, and operator actions.
- Redact secrets/PII and protect evidence artifacts.
- Prefer rate limiting, backpressure, and reversible mitigations.
- Cancel specific queries only after confirming owner and impact; limit session termination.
- Never delete WAL, relation files, or PID files by guesswork.
- Never promote a standby without verifying fencing, timelines, and RPO.
- Verify data integrity, replication, archiving, and backups after service recovers.
- Use post-incident reviews to strengthen detection, mitigation, and recovery.

## 45. Official Reference Documentation

- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html): activity monitoring and statistics views.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): statistics collection and reset behavior.
- [PostgreSQL — System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html): backend cancel/terminate and administrative functions.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock modes and deadlocks.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): WAL, checkpoints, and durability settings.
- [PostgreSQL — Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html): standby and streaming replication.
- [PostgreSQL — Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS): slot retention behavior.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): vacuum, analyze, and transaction ID maintenance.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE codes.
- [PostgreSQL — Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): backups, WAL archives, and recovery.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query-level workload statistics.

Catalog columns, statistics views, and wait events can change across major versions. During production incidents, consult the manual for your exact running version and verify operator role privileges. Diagnostic queries also consume resources; collect only the scope needed.

## 46. Summary

Troubleshooting PostgreSQL does not end when processes come back up or alerts turn green. You must preserve evidence, mitigate impact via controlled actions, and verify that the database, data, applications, replication, and backups have genuinely recovered.

1. **Collect:** confirm identity/role and capture timelines, sessions, locks, WAL, replication, logs, and OS/platform metrics before altering state.
2. **Assess:** separate symptoms from impact and evaluate data-loss risk, severity, and blast radius.
3. **Mitigate:** shed traffic/concurrency, address the exact blocker or resource bottleneck, and record owners and rollback conditions.
4. **Protect data:** never delete WAL/data files, and never trigger failovers or repair commands without understanding recovery state.
5. **Verify:** re-measure service health, business correctness, replicas, archives, backups, and SLOs across a representative workload window.
6. **Improve:** capture incident reports, root causes/contributing factors, and action items with clear owners and deadlines.

An incident is recovered only when the service meets its requirements, data is verified, replication and backup posture return to acceptable bounds, and operations holds evidence supporting those conclusions.
