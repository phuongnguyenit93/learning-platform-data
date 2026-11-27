# Finalizing an Operations Handbook with Diagrams, Metrics, and Recovery Evidence

This lab belongs to the **DATABASE_MYSQL** module. The module's goal is mastering MySQL from table design, data types, keys, and SQL queries through indexing, transactions, and concurrency control—while practicing reading execution plans, optimizing queries, managing privileges, backups, and relational database operations.

In this lesson, we synthesize those skills into a **MySQL operations handbook** ready for service handovers, on-call shifts, incident response, and recovery drills. A useful handbook must answer concrete questions: what components make up the system, who is accountable, which metrics to watch, which signals trigger alerts, which inspection commands are safe, when to escalate, and how to prove data was accurately recovered.

A handbook is not a loose collection of commands. Each procedure must state its objective, preconditions, required privileges, execution steps, expected outcomes, stop/rollback rules, and required evidence. Alert thresholds must be calibrated against system baselines; examples in this lesson serve as a template rather than universal defaults for every workload.

## 1. Required Deliverables

After completing this lab, the operations team has a minimum documentation pack consisting of:

1. Architecture and data flow diagrams.
2. Inventory of instances, environments, versions, and node roles.
3. Catalog of metrics, dashboards, alerts, and interpretation guidance.
4. Periodic health check procedures.
5. Runbooks for common incidents.
6. Backup, binary log retention, and recovery procedures.
7. Restore drill plan with RPO/RTO measurements.
8. Evidence checklist proving backups and restores are usable.
9. Privilege matrix, accountable owners, and escalation contacts.
10. Handover checklist and handbook review cadence.

A record stating only "backup job succeeded" is insufficient. You need evidence covering timestamp, source instance, GTID or binlog coordinates, checksum, restore outcome, recovery duration, and post-restore data validation.

## 2. Defining Service Scope

Before writing runbooks, clearly specify which service the handbook covers. Avoid vague names like "main database" when the organization operates multiple clusters or regions.

Service metadata template:

| Field | What to Record |
|---|---|
| Service name | Database service name per internal catalog |
| Business owner | Business/product owning team |
| Technical owner | Team accountable for MySQL |
| On-call | Primary on-call rotation and escalation tier |
| Environment | Development, staging, production |
| Database product | MySQL Community/Enterprise or verified compatible service |
| Version | Server, Connector/J, and backup tool versions |
| Topology | Standalone, source/replica, Group Replication, or managed cluster |
| Data classification | Data sensitivity tier and protection requirements |
| Criticality | Criticality tier and operating hours |
| RPO | Maximum acceptable data loss |
| RTO | Maximum acceptable time to restore service |
| Change window | Permitted maintenance/deployment windows |
| Backup owner | Person/team operating backups and restores |

Never fill in guesses. If RPO, RTO, versions, or owners are unknown, mark them "unconfirmed" and assign an owner and due date.

### 2.1. Agreeing on business RPO and RTO

- **RPO (Recovery Point Objective):** the maximum period of data loss acceptable to the business during an incident.
- **RTO (Recovery Time Objective):** the maximum elapsed time from service disruption until service is restored to an agreed baseline.

For example, a 5-minute RPO means that in designed and tested scenarios, the recovery point must be no older than 5 minutes before the incident. A 60-minute RTO means the target is restoring service within 60 minutes.

RPO/RTO must be approved based on business impact, not chosen merely because a backup tool happens to advertise them. If the system has not yet proven it can meet those targets, document the gap and remediation plan.

## 3. Architecture and Data Flow Diagrams

Diagrams must show on-call engineers where applications connect, which nodes handle traffic, and how backups leave the system.

Example source/replica topology:

~~~mermaid
flowchart LR
    APP[Application] --> POOL[Connection pool]
    POOL --> PROXY[Proxy or write endpoint]
    PROXY --> SRC[(MySQL source)]
    SRC --> BINLOG[Binary log]
    BINLOG --> R1[(Read replica 1)]
    BINLOG --> R2[(Read replica 2)]
    SRC --> BKP[Backup pipeline]
    BINLOG --> ARCHIVE[Binary log archive]
    BKP --> VAULT[(Isolated backup vault)]
    ARCHIVE --> VAULT
    SRC --> EXP[Exporter / Performance Schema]
    R1 --> EXP
    R2 --> EXP
    EXP --> PROM[Prometheus / Monitoring]
    PROM --> DASH[Dashboards and alerts]
~~~

The diagram above is a sample. If the system uses Group Replication, InnoDB Cluster, a managed database, or multi-source replication, draw the actual topology. Never depict a replica as a backup: replication copies mutations, so accidental deletes or corrupted data replicate straight to replicas.

### 3.1. Documenting read and write flows

The handbook must state:

- Current write endpoint.
- Read endpoints and query routing rules.
- Proxy/load balancer components if present.
- Which node is authorized to accept writes.
- How the application behaves when replicas lag.
- How endpoints switch during failover.
- How the former source is prevented from accepting writes after promoting a new primary.

Never let an application pick an arbitrary node from an IP list without single-writer enforcement. During failover, fencing or an equivalent safeguard is mandatory to prevent split-brain.

### 3.2. Dependency and trust boundary diagrams

Include components outside MySQL:

- DNS, proxies, load balancers, and firewalls.
- Secret managers and TLS certificates.
- Backup schedulers, object storage buckets, and encryption keys.
- Monitoring, log collectors, and alert managers.
- Authentication systems, IAM, and jump hosts.
- Application services, queue consumers, ETL pipelines, and BI tools.

Annotate permitted connection paths, service accounts used, and where data leaves the database network zone. Never put passwords, tokens, private keys, or secret-bearing connection strings inside diagrams or documents.

## 4. Instance Inventory and Standard Configuration

Every instance needs an inventory record. Never lump everything into one generic list where source, replica, staging, and decommissioned nodes cannot be distinguished.

| Field | Example Format |
|---|---|
| Instance ID | `mysql-prod-a` |
| Environment | production |
| Role | source / replica / recovery target |
| Host / endpoint | Internal DNS without secrets |
| Port | 3306 if default |
| Server version | Output of `VERSION()` |
| `server_id` | Unique numeric ID within the topology |
| `server_uuid` | UUID from `@@server_uuid` |
| Storage engine | InnoDB |
| GTID mode | ON/OFF |
| Binary logging | ON/OFF |
| Replication channel | Channel name if applicable |
| Data directory | Verified filesystem path |
| Backup policy | Schedule, backup type, retention |
| Monitoring target | Target label in monitoring system |

Collect baseline info on each instance:

~~~sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@hostname AS hostname,
    @@port AS port,
    @@server_id AS server_id,
    @@server_uuid AS server_uuid,
    @@datadir AS data_directory,
    @@log_bin AS log_bin,
    @@gtid_mode AS gtid_mode,
    @@default_storage_engine AS default_engine;
~~~

Inspect critical configuration variables:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'wait_timeout',
    'interactive_timeout',
    'innodb_buffer_pool_size',
    'innodb_redo_log_capacity',
    'slow_query_log',
    'long_query_time',
    'binlog_expire_logs_seconds',
    'read_only',
    'super_read_only',
    'time_zone',
    'sql_mode'
);
~~~

Some variables do not exist in older MySQL versions or carry different names. The handbook must record the reference version and matching inspection commands; never assume one sample config fits every release.

## 5. Designing the Metrics System

Metrics must answer six operational questions:

1. Is the service available?
2. Are queries slow or failing?
3. Are resources approaching saturation?
4. Are transactions and locks degrading throughput?
5. Are replicas keeping up with the source?
6. Are backups and recovery capabilities still trustworthy?

Group metrics by domain:

| Category | Operational Question | Examples |
|---|---|---|
| Availability | Are instances and endpoints reachable? | Connection probes, uptime, replication state |
| Traffic | Is load rising or falling? | QPS, transactions/s, connections |
| Latency | Are queries slow? | p50/p95/p99 latency, slow query count |
| Errors | Are operations failing? | Connection errors, deadlocks, SQL errors |
| Saturation | Are resources running out? | CPU, memory, disk, IOPS, connection usage |
| InnoDB | Is the storage engine bottlenecked? | Buffer pool, row locks, redo log waits |
| Replication | Is data keeping up? | GTID gap, applier errors, lag |
| Backup/recovery | Can we recover? | Backup age, duration, checksums, restore drills |

### 5.1. Availability and connections

Track:

- Connection probes against the write endpoint.
- Read probes against replicas if replicas serve read queries.
- Uptime and restart count.
- `Threads_connected`.
- `Threads_running`.
- `Max_used_connections`.
- `Connections` and `Aborted_connects`.
- Connection errors broken down by cause.
- Application connection pool utilization, pending waits, and timeouts.

Fetch status:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects'
);
~~~

High `Threads_connected` does not always indicate an outage; connection pools legitimately keep idle connections open. Rising `Threads_running` paired with high CPU, rising latency, and queued connection acquisitions is a real signal to investigate.

Never raise `max_connections` merely to silence an alert. Every connection consumes memory and overhead; limits must be engineered alongside pool sizes, concurrency, and memory budgets.

### 5.2. Traffic and latency

Track statements and transactions over time:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Questions',
    'Queries',
    'Com_select',
    'Com_insert',
    'Com_update',
    'Com_delete',
    'Slow_queries'
);
~~~

Most status counters accumulate since server startup or counter reset. Compute rates by dividing the delta between two scrapes by the interval. After a server restart, counters reset to low values; monitoring must handle counter resets properly.

QPS alone does not reflect performance. A workload with low QPS where each query scans millions of rows can still saturate the server. Pair QPS with latency, rows examined, lock waits, and query digests.

If the application exposes per-endpoint metrics, track p50/p95/p99 latency and error rates at the application tier. MySQL status counters do not measure end-to-end request latency on their own.

### 5.3. Slow queries and query digests

Enable the slow query log according to a tested policy:

~~~sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'log_queries_not_using_indexes';
~~~

Never blindly enable logging for every query not using an index in production; it can produce massive logs and many false positives. Pick thresholds from baselines and actual workloads.

Performance Schema summarizes statements by digest:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_TIMER_WAIT,
    AVG_TIMER_WAIT,
    MAX_TIMER_WAIT,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

`TIMER_WAIT` fields are typically recorded in picoseconds in Performance Schema. Convert units explicitly when presenting metrics. Digest tables are size-bounded and reset on server restart or Performance Schema truncation.

When investigating a query digest:

1. Capture the sample SQL and target schema.
2. Check execution count, total wait time, mean, and max wait time.
3. Compare rows examined against rows sent.
4. Run `EXPLAIN` on a representative query.
5. Run `EXPLAIN ANALYZE` when supported and safe to execute.
6. Check indexes, cardinality, statistics, and data skew.
7. Validate changes with before/after benchmarks.

Never run `EXPLAIN ANALYZE` on a write statement or heavy query in production without understanding its execution impact.

### 5.4. InnoDB buffer pool and storage

Monitor these counters:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_row_lock_waits',
    'Innodb_row_lock_time',
    'Innodb_row_lock_current_waits',
    'Innodb_log_waits'
);
~~~

Interpret metrics together:

- Buffer pool read requests: logical page read requests into the buffer pool.
- Buffer pool reads: physical page reads from storage.
- Pages dirty: modified pages not yet flushed to disk.
- Row lock waits/time: signs of transactions waiting on locks.
- Deadlocks: count of detected deadlocks.
- Log waits: cases where transactions waited for redo log writes/flushes.

To inspect InnoDB deadlock counters when the corresponding metrics are enabled:

~~~sql
SELECT NAME, COUNT, STATUS
FROM information_schema.innodb_metrics
WHERE NAME IN ('lock_deadlocks', 'lock_timeouts');
~~~

If those metrics are disabled or unavailable in your version, check the `LATEST DETECTED DEADLOCK` section of `SHOW ENGINE INNODB STATUS` and your monitoring system. Never assume every MySQL version exposes the exact same status variables.

Buffer pool hit ratio is helpful for trend tracking, yet should never serve as a lone fixed pass/fail threshold. Large scan workloads, cold warm-ups, and measurement formulas skew the ratio. Correlate it with I/O latency, buffer pool size, working set size, and query plans.

Alongside MySQL metrics, monitor the OS and storage layer:

- CPU utilization, load average, and CPU steal on VMs.
- RAM, swap usage, and OOM events.
- Free disk space per filesystem.
- Read/write IOPS, throughput, and latency.
- Filesystem inode usage if bounded by platform limits.
- Size of data, redo, undo, relay logs, and binary logs.
- Backup volume size and growth rate.

Free disk space is time-sensitive. Alert on both percentage free and growth rate (time-to-full) so operators have enough lead time before disks fill up.

### 5.5. Locks, transactions, and undo history

When queries slow down abnormally, inspect open transactions and locks:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Check InnoDB status:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Look for warning signs:

- Long-running open transactions.
- Climbing lock waits.
- Repeated deadlocks.
- Transactions modifying huge numbers of rows.
- Continuously growing undo history / history list length.
- Redo log or page flushing bottlenecks.

A long-running `REPEATABLE READ` read transaction holds open a read view and blocks purge from reclaiming old undo versions. Never kill a session solely because it is old; first identify its owner, statement, modified rows, and rollback impact.

### 5.6. Replication and GTID

For asynchronous replication, track:

- Receiver and applier thread states.
- `Last_IO_Error` and `Last_SQL_Error`.
- `Retrieved_Gtid_Set` and `Executed_Gtid_Set`.
- Missing GTID gaps.
- Active applier workers and worker errors.
- Relay log disk usage.
- Platform lag metrics and commit/apply timestamps.

MySQL 8.0.22 and later:

~~~sql
SHOW REPLICA STATUS\G
~~~

Older versions use `SHOW SLAVE STATUS`. Never rely on `Seconds_Behind_Source` as the sole source of truth. It can return `NULL` when threads stop or status is uncertain, and may not accurately reflect application-observed staleness.

For GTIDs, inspect:

~~~sql
SELECT
    @@GLOBAL.gtid_executed AS executed_gtids,
    @@GLOBAL.gtid_purged AS purged_gtids,
    @@GLOBAL.server_uuid AS server_uuid;
~~~

To confirm a replica has applied up to a target GTID set:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
    'UUID:1-1000',
    30
) AS wait_result;
~~~

Replace `UUID:1-1000` with the actual GTID set. Returning `0` means the requested set executed; `1` means timeout. Run this only after clearly identifying the synchronization point to verify.

For Group Replication, monitor member state:

~~~sql
SELECT
    MEMBER_ID,
    MEMBER_HOST,
    MEMBER_PORT,
    MEMBER_STATE,
    MEMBER_ROLE
FROM performance_schema.replication_group_members;
~~~

Members must report states consistent with their cluster roles. Never promote or bootstrap a group based solely on lag metrics; follow verified cluster and quorum procedures.

## 6. Building Operational Dashboards

Dashboards should provide one overview screen plus focused drill-down screens. Never cram every metric onto a single chart.

### 6.1. Overview dashboard

| Panel | Displays | How to Read |
|---|---|---|
| Service availability | Endpoint probes, instance status | Spot dropped connections or down nodes |
| Request latency | Application p50/p95/p99 | Observe actual user experience |
| Query throughput | QPS, transactions/s | Distinguish traffic spikes from drops |
| Error rate | SQL errors, timeouts, connection errors | Spot sudden error surges |
| Connection usage | `Threads_connected`, pool utilization | Spot connection exhaustion risk |
| CPU and memory | CPU, RAM, swap | Spot compute saturation |
| Disk and I/O | Free space, IOPS, latency | Spot storage bottlenecks |
| Replication | Thread state, GTID gap, apply lag | Assess read scaling and failover readiness |
| Backup freshness | Timestamp of latest successful backup | Verify backup currency |
| Restore drill | Latest restore test and duration | Verify proven recoverability |

### 6.2. Performance dashboard

Include:

- Top query digests by total time.
- Top digests by mean and max time.
- Rows examined vs. rows sent.
- Slow query count.
- `Threads_running`.
- Lock waits and deadlock rate.
- Buffer pool physical reads.
- Disk read/write latency.
- Redo log waits.
- Disk-backed temporary tables.

Align all charts to the same time range for correlation. For example, latency rising alongside `Threads_running` and disk latency points to resource saturation; latency rising while CPU stays low points toward lock waits, network issues, or external dependencies.

### 6.3. Data protection dashboard

Mandatory for critical databases:

- Latest successful backup per instance/database.
- Backup age and backup duration.
- Backup size and abnormal size swings.
- Checksum/manifest verification status.
- Binary log archive freshness and retention.
- Free space in the backup vault.
- Latest restore drill date.
- Restore and binlog replay duration.
- Row count, checksum, and business invariant verification results.
- Measured RPO/RTO from the latest drill.

A green backup job does not prove restores work. The dashboard must surface restore tests as an independent health signal.

## 7. Creating Actionable Alerts

Every alert requires:

- Name and severity level.
- Trigger condition and sustained duration.
- Business impact.
- Linked runbook.
- Receiving team and escalation path.
- How to confirm resolution.
- Alert closure criteria.

Sample alert catalog:

| Alert | Reference Condition | First Action |
|---|---|---|
| MySQL endpoint unavailable | Probes fail continuously over defined window | Check instance, network, proxy, and error log |
| Connection saturation | Pool/connection usage stays near limit | Inspect pool waits, `Threads_running`, and connection-holding queries |
| Slow query regression | p95 or total query time exceeds baseline | Identify new digests or plan changes |
| Disk pressure | Projected time-to-full drops below safety threshold | Check data growth, binlogs, relay logs, and backup staging |
| Replica applier stopped | Applier stopped or `Last_SQL_Error` non-empty | Capture status/errors before intervening |
| Replica lag | Lag exceeds business threshold for sustained window | Check source load, network, applier workers, and queries |
| Backup stale | No verified backup within target window | Check scheduler, credentials, storage, and logs |
| Restore drill overdue | Drill overdue per policy schedule | Schedule restore test and archive evidence |
| Deadlock increase | Deadlock rate exceeds baseline | Collect deadlock details, queries, and transaction order |

Vague conditions like "near limit" or "exceeds baseline" must become concrete numbers after observation. Never copy-paste generic 80% CPU, 90% disk, or fixed lag thresholds across every system. Alerts should factor in sustained duration and rate of change to suppress noise.

### 7.1. Example trend-based alert logic

For disk space, never alert solely on percentage used. If growth accelerates sharply, a volume with 30% free space can still fill before the next shift. Combine:

- Free bytes.
- Hourly/daily data growth rate.
- Binary log generation rate.
- Size of in-progress backups.
- Spare headroom required during restores.

For replication, alerting on a stopped applier or a continuously widening GTID gap is usually more reliable than reacting to a single `Seconds_Behind_Source` sample.

## 8. Periodic Health Check Procedure

Run health checks using a read-only account whenever possible. Never execute test writes against production solely to verify connectivity.

### 8.1. Checking connectivity and version

~~~sql
SELECT NOW(6) AS server_time,
       VERSION() AS version,
       @@hostname AS hostname,
       @@server_id AS server_id,
       @@server_uuid AS server_uuid,
       @@read_only AS read_only,
       @@super_read_only AS super_read_only;
~~~

Confirm the endpoint and node role match inventory. Verify `read_only`/`super_read_only` per topology: write sources permit writes; read replicas are typically write-protected.

### 8.2. Checking errors and resources

- Review error logs for the check window.
- Check connection usage and `Threads_running`.
- Check free disk space, I/O latency, and CPU.
- Check deadlocks, lock waits, and long-running transactions.
- Check slow queries and top digests.
- Check buffer pool health and redo log waits.

A health check must record more than "OK." Log timestamp, node, version, findings, any anomalous metrics, and the operator.

### 8.3. Checking replication

On replicas, verify:

- Receiver/applier threads are in expected running states.
- Zero new I/O or SQL errors.
- Executed GTIDs are advancing.
- Zero unexpected errant GTIDs.
- Lag stays within business limits.
- Relay logs are not growing unbounded.

Never repair replication before saving initial status. If a thread halted, capture error messages and GTID sets before restarting it.

### 8.4. Checking backups

Verify the newest backup:

- Exited with a success code.
- Has a recorded manifest and checksum.
- Size falls within expected bounds.
- GTID/binlog coordinates are recorded.
- Uploaded/replicated to the backup vault.
- Not prematurely pruned by retention rules.
- Latest restore test remains within the approved cadence.

## 9. Runbook: Cannot Connect to MySQL

**Symptoms:** application timeouts or connection refused errors.

**Objective:** isolate whether the fault lies in the application, network, proxy, or `mysqld`.

1. Scope the impact: one app, one endpoint, or all clients.
2. Check DNS, routing, firewalls, TLS certificates, and proxy health.
3. Check the MySQL service/process and error log via administrative channels.
4. If authorized, verify the instance is listening on the expected port and interface.
5. Inspect connection pools: active, idle, pending, timeouts, and connection leaks.
6. Check `Aborted_connects`, connection errors, and `Threads_connected`.
7. Never restart immediately before collecting error logs, process states, and resource metrics.
8. If the instance crashed or stopped, determine root cause before restarting.
9. Once the endpoint recovers, run a read-only health check and application smoke test.
10. Document start/end timestamps, root cause, and evidence.

Supporting queries:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects'
);

SHOW VARIABLES LIKE 'max_connections';
~~~

On connection saturation, inspect pool sizes across every application instance. Increasing `max_connections` raises memory pressure and never cures connection leaks or stalled queries.

## 10. Runbook: Slow Queries or Latency Spikes

**Symptoms:** rising p95/p99 latency, request timeouts, falling throughput.

1. Pinpoint onset time and affected request paths.
2. Compare application latency against database query latency.
3. Inspect CPU, disk I/O, `Threads_running`, connection pool waits, and lock waits.
4. Pull top query digests by total time and execution count.
5. Diff digests against the baseline prior to the latest deployment.
6. Run `EXPLAIN` on representative queries.
7. Check indexes, statistics, rows examined, sorts/temp tables, and data skew.
8. Check long-running transactions, lock waits, and deadlocks.
9. Apply fixes only after validating a test and rollback plan.
10. Re-measure p95/p99 latency, throughput, and resources afterward.

Query to inspect digests:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    AVG_TIMER_WAIT,
    MAX_TIMER_WAIT,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 10;
~~~

When verifying execution plans, archive the sample SQL, `EXPLAIN` output, schema/indexes, and table statistics. A plan that looks fast on staging may degrade in production if cardinality and data skew differ.

## 11. Runbook: Disk Nearly Full

**Symptoms:** filesystem alerts, failing writes, or MySQL unable to allocate temp/redo/binlog files.

1. Identify which mount is filling: `datadir`, `tmpdir`, relay logs, binlogs, or backup staging.
2. Record free bytes, growth rate, and which process is writing.
3. Inspect sizes of data files, binary logs, relay logs, general/slow/error logs, and temp files.
4. Check whether a stuck backup is writing into `datadir` by mistake.
5. Check whether a halted replica applier is accumulating relay logs.
6. Verify retention policy and which replicas/backups still need older binary logs.
7. Expand storage or free space strictly via approved procedures.
8. Never manually delete InnoDB, redo, undo, relay log, or binary log files managed by MySQL.
9. If purging binary logs, use proper MySQL commands after confirming no replica or backup still needs them.
10. Afterward, confirm disk growth stabilized and close alerts.

Checking binary logs:

~~~sql
SHOW BINARY LOGS;
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'log_bin_basename';
~~~

Never run `PURGE BINARY LOGS` blindly just to free disk space without checking replica lag and PITR requirements. Binary logs may be the only path to recover up to an incident.

## 12. Runbook: Replica Lag or Stopped Applier

**Symptoms:** read queries return stale data, replica status shows errors, or GTID gap widens.

1. Confirm the exact node and replication channel under inspection.
2. Save `SHOW REPLICA STATUS` output before changing anything.
3. Inspect receiver/applier threads and the latest error messages.
4. Compare `GTID_EXECUTED` between source and replica.
5. Verify the source still retains binary logs the replica needs.
6. Inspect CPU, I/O, network, locks, and queries executing on the replica.
7. Check for large DDLs or giant transactions blocking the applier.
8. Never skip a failing transaction just to flip the thread back to `Yes`.
9. If the source already purged required logs, plan to rebuild the replica from a backup with intact GTID state.
10. Wait for the target GTID and verify data before returning the replica to read pools.

For MySQL 8.0.22 and later:

~~~sql
SHOW REPLICA STATUS\G
~~~

Checking GTIDs:

~~~sql
SELECT @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;
~~~

If a replica lags behind SLA, temporarily remove it from read routing per application policy. Never switch source/replica roles while the authoritative writer is uncertain.

## 13. Runbook: Deadlocks and Lock Waits

**Symptoms:** transactions failing with error `1213` or `1205`, rising retry rates.

1. Capture error codes, SQL templates, and request IDs.
2. Inspect deadlock details inside `SHOW ENGINE INNODB STATUS`.
3. Identify involved transactions and locked index records.
4. Trace table/row access ordering across competing flows.
5. Locate queries lacking indexes that lock overly broad row ranges.
6. Shorten transaction duration and move external calls outside transactions.
7. Standardize multi-row update ordering across all code paths.
8. For deadlocks, retry the entire transaction with bounded attempts and jitter if idempotent.
9. For lock wait timeouts, locate blocking transactions before tuning timeout settings.
10. Monitor deadlock rates and latency after deploying fixes.

Never retry only the final failing statement of an aborted transaction. On deadlock, InnoDB rolls back the victim transaction; the application must replay the entire unit of work in a fresh transaction when appropriate.

## 14. Designing the Backup Policy

Backups must be engineered around RPO/RTO targets and dataset size.

### 14.1. Backup types

| Type | Characteristics | When Suitable |
|---|---|---|
| Logical backup | Exports schema and data as SQL/dumps | Data migration, object-level recovery, small/medium databases |
| Physical backup | Copies page/data files via supported tooling | Large datasets requiring faster restores |
| Snapshot | Storage/volume snapshot with consistency guarantees | Platforms supporting consistent snapshots |
| Binary log archive | Stores incremental changes post-backup | Point-in-time recovery |
| Replica-based backup | Offloads backup I/O from the primary | When tooling and topology guarantee consistency |

A replica is never an independent backup. Accidental deletions on the source replicate immediately. Maintain isolated backups with separate retention and access controls.

### 14.2. Scheduling and retention

Policy elements to define around RPO/RTO:

- Full backups: cadence balanced against dataset size and restore time.
- Incremental backups: if supported by tooling and tested end-to-end.
- Binary log archiving: continuous or short-interval per RPO.
- Offsite/immutable copies: stored outside the database's failure domain.
- Retention: long enough for recovery, audit, and compliance needs.
- Restore drills: scheduled periodically and after major tool/version upgrades.

Retention must account for detection delay. If an accidental deletion goes unnoticed for days, retained backups must extend far enough back prior to the error, paired with binary logs advancing up to right before the bad operation.

### 14.3. Logical backups with `mysqldump`

Example for an InnoDB schema:

~~~bash
mysqldump --single-transaction \
  --routines --triggers --events \
  --hex-blob \
  --databases shop > shop.sql
~~~

`--single-transaction` produces a consistent snapshot for transactional tables like InnoDB. Consistency is not guaranteed if concurrent DDL modifies table structures or if non-transactional tables exist. Control DDL during dumps and document backup limitations.

Additional flags depend on GTIDs, versions, and restore targets. If GTID metadata is required, check `--set-gtid-purged` and organizational standards. Do not blindly enable GTID flags on every dump, as restoring onto another instance can alter GTID state unexpectedly.

For larger backups, evaluate MySQL Shell dump utilities or physical backup tools compatible with your server version. Pick tools supporting consistency, GTID metadata, compression, encryption, and verified restores.

### 14.4. Physical backups

Physical backups suit large datasets where restore speed is critical. Use a tool supported for your exact MySQL version, storage engine, and platform—such as MySQL Enterprise Backup or Percona XtraBackup per their compatibility matrices.

The handbook must document:

- Tool and server versions.
- Tested backup, prepare, and copy-back commands.
- Required locking or flush steps.
- Redo/undo and metadata handling.
- Procedure to restore into a clean data directory.
- Filesystem ownership and permission requirements.
- Verification steps before allowing `mysqld` to accept traffic.

Never copy files from a live running MySQL `datadir` using plain filesystem commands and treat them as a consistent physical backup.

## 15. Protecting and Verifying Backups

Every backup should produce a manifest containing:

| Field | Contents |
|---|---|
| Backup ID | Unique identifier |
| Source instance | Host/instance and role |
| Server version | MySQL version |
| Tool version | Backup tool version |
| Start/end time | UTC timestamps |
| Backup type | Logical/physical/snapshot |
| Databases | Included database scope |
| GTID state | `GTID_EXECUTED` and `GTID_PURGED` if applicable |
| Binlog coordinate | File/position or GTID info |
| Size | Byte size |
| Checksum | SHA-256 or policy checksum |
| Encryption | Encryption status and key reference |
| Storage location | Internal URI/path without credentials |
| Exit status | Tool return code |
| Restore test | Whether this backup passed a restore test |

Verify checksums after upload and prior to restore. A checksum proves the file was not corrupted since creation; it does not prove the SQL is valid or the database can boot cleanly.

Linux SHA-256 example:

~~~bash
sha256sum shop.sql
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\shop.sql
~~~

Encrypt backups both in transit and at rest. Separate backup read/delete permissions from application and day-to-day MySQL accounts. Enforce immutable retention or deletion locks per policy to mitigate ransomware and human error.

Never store passwords, private keys, or secret values inside manifests. Store only references to your secret manager.

## 16. Evidence of a Successful Backup

A backup is considered complete only when full procedural evidence exists:

1. Job exited with a success code.
2. Logs contain zero unhandled errors.
3. Backup files/objects exist with reasonable sizes.
4. Manifest was persisted.
5. Checksum was computed and verified post-transfer.
6. GTID/binlog metadata was captured for PITR.
7. Backup resides in the vault with proper retention and encryption.
8. Monitoring updated with the latest backup status.
9. Backup is eligible for scheduled restore drills.

Evidence must capture UTC timestamps, backup ID, source instance, tool version, byte size, and checksum. Never rely solely on screenshots; prefer machine-readable logs and auditable metadata.

## 17. Runbook: Restoring a Full Backup

Restores must target a designated host/instance isolated from production traffic until verification finishes.

### 17.1. Preparation

1. Open an incident/change record and identify the approver.
2. Locate the backup ID and manifest.
3. Verify checksums and encryption key access.
4. Confirm MySQL version compatibility with the backup.
5. Provision a target with enough capacity for data, redo, temp, and binary logs.
6. Isolate the target from production applications and replication.
7. Record current `server_uuid`/`server_id` if the target holds existing data to preserve.
8. Clarify whether the restore is a standalone recovery, source replacement, or new replica seed.

Never overwrite a live traffic-serving instance before establishing a cutover plan and backing up its current state.

### 17.2. Restoring a logical dump

When the dump already contains `CREATE DATABASE`:

~~~bash
mysql < shop.sql
~~~

If the dump omits database creation, specify the target database in the command or dump. Inspect charsets, collations, users/grants, routines, triggers, events, and `DEFINER` clauses. A logical data dump may exclude server configs, system accounts, or config files.

After restoring, verify:

~~~sql
SHOW DATABASES;
SHOW TABLE STATUS FROM shop;
SHOW CREATE TABLE shop.orders\G
~~~

### 17.3. Restoring a physical backup

Follow the documentation for your exact backup tool version:

1. Stop `mysqld` on the target.
2. Prepare an empty data directory with proper filesystem permissions.
3. Run the prepare/apply-log step if required by the tool.
4. Run copy-back/restore per tool instructions.
5. Set file ownership and permissions.
6. Verify server config, `datadir`, and port.
7. Verify server identity and replication settings before opening networking.
8. Start `mysqld` in isolated mode.
9. Inspect error logs, InnoDB crash recovery messages, and data integrity.
10. Rejoin the target to the topology only after full verification completes.

Never mix steps from two different backup tools. Prepare and copy-back procedures must match the exact tool version that created the backup.

## 18. Point-in-Time Recovery (PITR)

PITR restores from a full backup and applies binary logs up to a target timestamp or transaction.

~~~mermaid
flowchart LR
    A[Full backup at T0] --> B[Restore to recovery target]
    B --> C[Read binlogs after T0]
    C --> D[Replay transactions in order]
    D --> E[Stop before bad action at T1]
    E --> F[Verify data and application]
    F --> G[Approve cutover]
~~~

### 18.1. PITR preconditions

- Consistent, restorable full backup.
- Complete binary logs from backup point to recovery point.
- Accurate binlog coordinates or GTID metadata.
- Continuous ordered binlog files with zero gaps.
- Compatible `mysqlbinlog` utility.
- Explicitly defined stop point using a consistent timezone.
- Plan for open transactions or excluding the corrupting action.

If binary logs were purged or an archive is missing a file, continuous replay across that gap is impossible. That is why archive continuity must be verified continuously—not just the newest file.

### 18.2. Determining the stop point

You can target:

- UTC timestamp immediately prior to the corrupting action.
- Verified binary log file and position.
- Identified GTID/transaction boundary.

Align on clean transaction boundaries to avoid stopping mid-transaction. When using timestamps, convert and verify timezones explicitly; never use ambiguous local times without offsets across DST boundaries.

Illustrative example using locally downloaded binlog files:

~~~bash
mysqlbinlog \
  --start-position=12345 \
  --stop-datetime="2026-11-19 09:55:00" \
  mysql-bin.000123 mysql-bin.000124 \
  | mysql --host=recovery-db.example.net
~~~

Filenames, positions, and timestamps above are placeholders. Adjust them to match backup metadata, actual files, timezone, and the approved stop point. Never test directly against the production source. Inspect decoded binlog contents before replaying onto an isolated target.

When using GTIDs, identify transactions to include or exclude and follow the PITR procedure for your version/tool. Never manually alter `gtid_purged` merely to force history to look aligned.

### 18.3. Recovering after an accidental delete

A common sequence:

1. Pause or restrict writers to prevent further changes if business rules allow.
2. Pinpoint the accidental delete transaction from audit logs, app logs, and binlogs.
3. Select the latest full backup prior to the deletion.
4. Restore onto an isolated recovery instance.
5. Replay binlogs up to immediately before the corrupting transaction.
6. Verify rows to restore and related foreign-key records.
7. Export and diff the data to reintroduce into production.
8. Apply controlled fixes after taking a fresh pre-merge backup.
9. Verify foreign keys, unique keys, monetary totals, and business states.
10. Re-open traffic per plan and monitor closely.

You do not always need to replace all of production with the recovery instance. When only a subset of rows was deleted, extract from the recovery instance and run a controlled merge—handling IDs, foreign keys, post-incident rows, and unique conflicts.

## 19. Measuring and Proving RPO/RTO

After every restore drill, record:

| Milestone | UTC Timestamp |
|---|---|
| Incident/drill start | T0 |
| Backup selected | Backup timestamp |
| Restore started | T1 |
| Full backup restore completed | T2 |
| Binlog replay started/finished | T3/T4 |
| Data validation completed | T5 |
| Application smoke test passed | T6 |
| Recovery sign-off | T7 |

Calculate:

- **Measured RTO:** elapsed time from the approved start milestone until the service meets recovery acceptance criteria.
- **Measured RPO:** gap between the newest recoverable data timestamp and the incident/data-loss point.

Never measure RTO solely by how long the restore command ran. Include detection, decision-making, provisioning, restore, replay, validation, and cutover if those fall under your organization's RTO definition.

Sample drill report:

| Metric | Target | Measured Result | Verdict |
|---|---:|---:|---|
| RPO | 5 minutes | Fill after drill | Pass/Fail |
| RTO | 60 minutes | Fill after drill | Pass/Fail |
| Full restore | Per plan | Record duration | Pass/Fail |
| Binlog continuity | Zero gaps | Yes/No | Pass/Fail |
| Data validation | Zero material discrepancies | Yes/No | Pass/Fail |
| App smoke test | All mandatory steps pass | Yes/No | Pass/Fail |

Never mark Pass without measurements and archived evidence. If targets fail, record the gap, root cause, owner, and next drill date.

## 20. Recovery Evidence Package

A drill counts as proven only when all evidence categories below are collected:

### 20.1. Backup provenance evidence

- Backup ID and manifest.
- Source instance, server version, and backup tool version.
- Backup UTC timestamp.
- `GTID_EXECUTED`/`GTID_PURGED` or binlog file/position.
- Byte size and checksum.
- Job logs and exit code.
- Vault location, encryption status, and retention.

### 20.2. Restore evidence

- Recovery target and network isolation setup.
- Restore start and finish timestamps.
- Restore tool logs.
- MySQL startup output and error log.
- Server version and InnoDB recovery status.
- Post-restore GTID/binlog position.
- Data directory size and key tables.

### 20.3. Data validation evidence

Verify row counts on critical tables:

~~~sql
SELECT 'customers' AS table_name, COUNT(*) AS row_count
FROM shop.customers
UNION ALL
SELECT 'orders', COUNT(*)
FROM shop.orders
UNION ALL
SELECT 'order_items', COUNT(*)
FROM shop.order_items;
~~~

Row counts are only a coarse sanity check. Two tables with equal row counts can still hold corrupted values. Supplement with chunked checksums, key comparisons, or an approved consistency-check tool.

Verify zero orphaned relationships:

~~~sql
SELECT COUNT(*) AS orphan_order_items
FROM shop.order_items AS oi
LEFT JOIN shop.orders AS o
    ON o.order_id = oi.order_id
WHERE o.order_id IS NULL;
~~~

Reconcile order header totals against line items per business rules. Example:

~~~sql
SELECT o.order_id, o.order_number
FROM shop.orders AS o
LEFT JOIN shop.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.subtotal,
    o.discount_amount,
    o.shipping_fee,
    o.total_amount
HAVING
    o.subtotal <> COALESCE(SUM(oi.quantity * oi.unit_price), 0.00)
    OR o.discount_amount <> COALESCE(SUM(oi.discount_amount), 0.00)
    OR o.total_amount <>
       COALESCE(SUM(oi.line_total), 0.00) + o.shipping_fee;
~~~

Adapt queries to match your actual schema, fees, and taxes. A validation check is only meaningful if it faithfully expresses real business invariants.

### 20.4. Application verification evidence

- Application connects to the intended recovery/cutover endpoint.
- Read/write smoke tests pass.
- Execute a controlled test transaction if permitted.
- Verify user grants, stored routines, triggers, events, and `DEFINER`s.
- Verify charsets, collations, SQL mode, and timezones.
- Confirm background jobs/queues do not trigger unwanted side effects in test environments.
- If replicas exist, verify replication health after reconfiguration.

Never include personal data or secrets in screenshots or reports. Use test IDs and masked data.

## 21. Failover and Returning to Normal Operations

Failover promotes another node to writer; it is a topology change carrying split-brain risk. The handbook must specify who holds approval authority and which orchestration tools are used.

Before promoting:

1. Check whether the old source is still accepting writes.
2. Fence the old source or guarantee it can no longer receive writes.
3. Select the replica with the most complete applied GTID set.
4. Confirm no critical unapplied transactions sit in relay logs.
5. Verify `server_uuid`/`server_id` and node health.
6. Execute promotion via tested procedure.
7. Redirect the write endpoint via proxy/DNS/service discovery.
8. Re-point remaining replicas to the new source.
9. Verify application health and new transactions.
10. Archive pre/post GTID sets and cutover timestamps.

Never promote solely because one replica shows lower lag on a single status read. Verify GTIDs and confirm the old source is fenced. If the authoritative node cannot be determined, halt ad-hoc changes and escalate via the incident commander.

After failover, never rush to reattach the old primary as a replica. First verify whether its data and GTIDs allow a safe rejoin or require rebuilding from a fresh backup/clone.

## 22. Access Control and Operational Safety

The handbook should define privileges by role:

| Role | Typical Privileges | Restrictions |
|---|---|---|
| Application user | `SELECT`/`INSERT`/`UPDATE`/`DELETE` on required schemas | No admin privileges, never grant `SUPER` |
| Read-only analyst | `SELECT` on permitted schemas/views | No writes, scoped away from restricted data |
| Backup agent | Privileges required by backup tooling | Separate from application accounts |
| Monitoring agent | Status/Performance Schema reads needed by exporters | Zero data-write privileges |
| DBA operator | Operational tasks per runbook | Individual named accounts, audited with approvals |
| Emergency admin | Break-glass highest privileges during incidents | Vaulted, time-bound, post-incident audited |

Core principles:

- Least privilege: grant only what the role needs.
- Individual named accounts for administration; avoid shared logins.
- Keep secrets in a secret manager and rotate on schedule.
- Require TLS for network connections.
- Audit all privilege and configuration changes.
- Never paste passwords into tickets, chats, or runbooks.
- Use read-only queries during investigation.
- Clearly flag commands that mutate data, restart services, fail over, purge logs, or reset state.

Commands such as `KILL`, `SET GLOBAL`, `ALTER USER`, `PURGE BINARY LOGS`, `RESET REPLICA`, and DDL statements must be classified by risk level, required privileges, and approval gates.

## 23. Incident Severity and Escalation Matrix

| Severity | Examples | Response |
|---|---|---|
| SEV-1 | Writer unavailable, active data loss, suspected split-brain | Page incident commander, on-call DBA, and business owner immediately |
| SEV-2 | All replicas down, disk nearly full, no recent valid backups | On-call DBA urgent response, notify owner, assess RPO exposure |
| SEV-3 | Slow queries hurting subset of traffic, rising lag still within bounds | Database team investigates per runbook |
| SEV-4 | Trend alerts, capacity warnings, or upcoming overdue restore drill | Create tracked task with owner and due date |

Each organization must populate target response SLAs, paging channels, and backup contacts. Never place personal phone numbers or sensitive details in widely readable docs; reference controlled internal directories.

## 24. Recurring Operations Schedule

Reference cadence:

| Cadence | Tasks | Evidence |
|---|---|---|
| Every shift | Check availability, alerts, replication, backup freshness | Health check log |
| Daily | Check backups, binlog archiving, disk trends, new errors | Dashboard snapshot/logs |
| Weekly | Review slow queries, deadlocks, connection pools, capacity | Performance review |
| Monthly | Audit users/grants, retention, capacity forecast, alert noise | Access/capacity report |
| Quarterly | Restore drill and RPO/RTO measurement | Restore evidence pack |
| Post-upgrade | Regression tests, backup/restore test, replication validation | Change validation |
| Post-failover | Rebuild/rejoin replicas, audit GTIDs and data integrity | Failover report |

Actual cadence must match service criticality and policy. A payment ledger requires more frequent drills than a low-criticality reporting database.

## 25. Incident Record Template

Every incident needs a structured record:

| Field | Contents |
|---|---|
| Incident ID | Incident ticket/ID |
| Severity | SEV-1/2/3/4 |
| Start/end UTC | Start and resolution timestamps |
| Affected service | Service name and environment |
| Symptoms | Observable symptoms |
| Business impact | Affected users/transactions |
| Detection | Alert, user report, or health check |
| Timeline | Key milestones and actions |
| Evidence | Logs, metrics, queries, GTIDs, backup IDs |
| Root cause | Verified cause or working hypothesis |
| Resolution | Remediation actions taken |
| Data integrity | How data consistency was verified |
| RPO/RTO | Measured results if data recovery occurred |
| Follow-up | Action items, owners, and due dates |

Separate verified facts from hypotheses. Never write "MySQL failed" as a root cause without concrete evidence.

## 26. Practice Lab: Completing a Handbook for a Sample Service

Suppose a system runs one MySQL source, two replicas, a Spring Boot application, and daily backups with binary log archiving. Complete each step sequentially:

### Step 1 — Inventory and topology

- Document server version, `server_id`, and `server_uuid` for all three nodes.
- Diagram read/write endpoints and replication flows.
- Map network boundaries, proxies, and backup storage.
- Define the authoritative writer and fencing mechanism.

### Step 2 — Select metrics

Include at minimum:

- Availability probes.
- Application p95/p99 latency.
- QPS and transaction rate.
- Connection usage and pool waits.
- CPU, memory, free disk space, and I/O latency.
- Slow query digests and rows examined.
- Deadlocks and lock waits.
- Replica thread states, GTID gaps, and lag.
- Backup age, checksums, and restore drill age.

Document units, data source, scrape interval, instance labels, and owner for each metric.

### Step 3 — Build dashboards and alerts

- Create an overview dashboard.
- Create a performance dashboard.
- Create a replication dashboard.
- Create a backup/recovery dashboard.
- Link a runbook to every alert.
- Fire a synthetic alert in staging to verify paging channels.

### Step 4 — Write runbooks

Complete procedures for at least:

- Cannot connect to MySQL.
- Connection pool exhaustion.
- Query latency spike.
- Disk nearly full.
- Rising deadlocks/lock waits.
- Replica lag or stopped applier.
- Backup failure.
- Full backup restore.
- PITR after accidental delete.
- Failover and replica rejoin.

Every runbook needs diagnostic commands, expected outputs, required privileges, escalation paths, and abort conditions.

### Step 5 — Rehearse restore

- Select a backup and verify its manifest/checksum.
- Restore onto an isolated target.
- Replay binary logs to the chosen stop point.
- Run row counts, checksums, and business invariants.
- Run application smoke tests.
- Measure RPO/RTO.
- Archive evidence and document any gaps against targets.

### Step 6 — Review and handover

- Review with DBAs and business owners.
- Verify all URLs, hosts, and accounts work within intended scopes.
- Verify runbooks contain zero secrets.
- Assign owners to every open item.
- Set the next review date and handbook version.

## 27. Pre-Closure Incident Checklist

- [ ] Service and nodes returned to expected healthy state.
- [ ] Authoritative writer confirmed.
- [ ] Zero former sources still accepting accidental writes.
- [ ] Replicas caught up to target GTIDs.
- [ ] Zero unresolved I/O, SQL, or applier errors.
- [ ] Critical data reconciled.
- [ ] Post-incident backup completed and verified.
- [ ] Dashboards and alerts returned to green.
- [ ] Application smoke tests passed.
- [ ] RPO/RTO measured if data recovery was executed.
- [ ] Timeline, logs, metrics, and decisions archived.
- [ ] Follow-up items assigned owners and due dates.

## 28. Operations Handbook Completion Checklist

- [ ] Service owner, technical owner, and on-call rotation defined.
- [ ] MySQL, Connector/J, and backup tool versions documented.
- [ ] Instance inventory populated with `server_id`/`server_uuid`.
- [ ] Architecture and read/write flow diagrams included.
- [ ] Backup, binlog archive, and recovery target diagrams included.
- [ ] Business-approved RPO/RTO documented.
- [ ] Metric catalog and units defined.
- [ ] Availability, performance, replication, and backup dashboards built.
- [ ] Alerts linked to runbooks and escalation paths.
- [ ] Read-only health check documented.
- [ ] Runbooks ready for connectivity, slow queries, disk, locks, and replication.
- [ ] Backup retention and binary log retention policies documented.
- [ ] Backup manifests, checksums, and encryption enforced.
- [ ] Logical/physical restore procedures documented.
- [ ] PITR procedure includes clear stop points and timezone handling.
- [ ] Restore drill executed with data validation evidence.
- [ ] Measured RPO/RTO recorded.
- [ ] Failover, fencing, and rejoin procedures documented.
- [ ] Privilege matrix and secret handling rules defined.
- [ ] Operational cadence and review schedule established.
- [ ] Incident record template included.
- [ ] Unresolved gaps assigned owners and due dates.

## 29. Self-Check

1. Why can a replica never replace an independent backup?
2. Which endpoints and data flows must a MySQL operational architecture diagram depict?
3. How does `Threads_connected` differ from `Threads_running`?
4. Why doesn't higher QPS always imply a faster or healthier system?
5. Which metrics should be combined when investigating slow queries?
6. Why shouldn't `Seconds_Behind_Source` be the sole source of truth for replication lag?
7. Is a valid backup checksum enough to prove the backup is restorable? Why or why not?
8. How do RPO and RTO differ, and from which milestones should they be measured?
9. Which metadata and files does PITR require to replay cleanly from a full backup?
10. Why must the old source be fenced before promoting a replica?
11. What evidence proves restored data satisfies business rules?
12. Design the dashboard and top three alerts for a MySQL service with a 5-minute RPO and 60-minute RTO.

A complete operations handbook connects architecture, metrics, actions, and evidence. On-call engineers must know which node is the writer, which signals reveal saturation, which commands are safe to run, when to escalate, and how recovery has been proven. Only when backups are test-restored, data is reconciled, and RPO/RTO are measured can a team trust that recovery procedures meet service commitments.
