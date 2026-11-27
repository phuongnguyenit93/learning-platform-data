# Setting Up a Replica, Observing Lag, and Testing Role Switching

A MySQL replica is only useful when initialized cleanly from a consistent dataset, receiving continuous binary logs, and applying transactions in order. When an outage occurs, promoting a replica to primary also demands determining which node received sufficient data, fencing the old primary from further writes, and updating application endpoints. Skipping any of these steps risks losing acknowledged transactions, creating two primaries accepting writes simultaneously, or causing remaining replicas to diverge.

This lab belongs to the **DATABASE_MYSQL** module, **Integrated Practice** chapter. You will build a GTID-based source–replica topology, inspect replication threads and lag, simulate replica lag, execute a planned switchover, rehearse a controlled failover, and rejoin the old node into the topology. The goal is understanding both MySQL commands and the evidence required before every role-change step.

## 1. Objectives and Lab Topology

After completing this lab, learners should be able to:

1. Configure a source with binary logging and GTIDs.
2. Create a least-privilege replication account.
3. Initialize a replica from a consistent snapshot.
4. Configure GTID auto-positioning and start replication.
5. Verify data, I/O and applier thread states, and GTID sets.
6. Measure lag using multiple signals instead of relying on a single metric.
7. Simulate slow replicas or stopped appliers and recover cleanly.
8. Swap primary/replica roles in a planned switchover.
9. Execute a failover with proper fencing and evaluate RPO/RTO.
10. Rejoin the former primary into the topology without causing split-brain.

Sample topology:

~~~text
                    Application
                         |
                  DB endpoint / proxy
                         |
                         v
                mysql-source (A)
                server_id = 101
                GTID + binlog
                         |
                 asynchronous GTID
                  replication
                         |
                         v
                mysql-replica (B)
                server_id = 102
                read_only
                super_read_only
~~~

In this lab, A initially acts as source and B as replica. After switching roles, B becomes the new primary and A is reconfigured as a replica of B.

### Environment requirements

- Two MySQL servers on the same major version, ideally identical minor/patch versions in the lab.
- MySQL 8.0.23+ or MySQL 8.4 to use current `SOURCE`/`REPLICA` syntax.
- Stable hostnames/IPs and bidirectional TCP connectivity per topology.
- Synchronized clocks across hosts via NTP/chrony.
- A unique `server_id` on each server.
- Sufficient disk space for the data directory, binary logs, and relay logs.
- Administrative accounts to configure replication and `read_only` modes.
- A test environment where services can be stopped or networks blocked to simulate failures.

Commands in this lesson use **source** and **replica** terminology. Older MySQL versions still use `MASTER`/`SLAVE` commands and status columns, such as `START SLAVE` and `SHOW SLAVE STATUS`. Check documentation for your exact server version before running.

Never test failovers, `STOP REPLICA`, `RESET REPLICA`, or `read_only` changes on production without an approved runbook, fencing, and a recovery plan.

## 2. Configuring the Source

On host A, configure options in the MySQL config file, typically under `[mysqld]`:

~~~ini
[mysqld]
server_id=101
log_bin=mysql-bin
binlog_format=ROW
gtid_mode=ON
enforce_gtid_consistency=ON
log_replica_updates=ON
binlog_expire_logs_seconds=604800
~~~

Meaning:

| Parameter | Purpose |
|---|---|
| `server_id` | Unique server identifier inside the replication topology |
| `log_bin` | Enables binary logging to record changes |
| `binlog_format=ROW` | Writes row events, suited for replication and CDC |
| `gtid_mode=ON` | Assigns GTIDs to transactions written to the binlog |
| `enforce_gtid_consistency=ON` | Blocks statements incompatible with GTIDs |
| `log_replica_updates=ON` | Logs transactions applied from upstream into this node's own binlog; required for intermediate/cascading topologies and certain promotions |
| `binlog_expire_logs_seconds` | Binlog retention duration; must exceed replica catch-up and recovery windows |

Restart MySQL if parameter changes require a restart. Then verify:

~~~sql
SELECT
  @@server_id,
  @@log_bin,
  @@binlog_format,
  @@gtid_mode,
  @@enforce_gtid_consistency,
  @@log_replica_updates;

SELECT @@GLOBAL.gtid_executed;
~~~

Never choose binlog retention solely based on current disk capacity. Factor in maximum outage duration, peak binlog generation rate, and how long replicas/CDC take to catch up. If binlogs purge before a replica reads them, the replica may need to be rebuilt from scratch.

## 3. Creating the Replication Account

On source A, create a user restricted to the replica's IP address:

~~~sql
CREATE USER 'repl_user'@'10.20.0.12'
  IDENTIFIED BY 'REPLACE_WITH_SECRET'
  REQUIRE SSL;

GRANT REPLICATION SLAVE ON *.*
  TO 'repl_user'@'10.20.0.12';
~~~

Adjust host IP, password, and TLS policy to match your environment. Store credentials in a secret manager or secured configuration; never commit passwords to source control or print credentials into logs.

Verify grants:

~~~sql
SHOW GRANTS FOR 'repl_user'@'10.20.0.12';
~~~

A replication account needs replication privileges only—not `SELECT`/`INSERT`/`UPDATE` across all application tables just to read binary logs. Restrict hosts, enforce TLS, and rotate secrets per security policy.

In modern MySQL, the privilege name remains `REPLICATION SLAVE` even though administrative terminology shifted to source/replica.

## 4. Preparing the Replica

On host B, configure:

~~~ini
[mysqld]
server_id=102
relay_log=relay-bin
log_bin=mysql-bin
binlog_format=ROW
gtid_mode=ON
enforce_gtid_consistency=ON
log_replica_updates=ON
read_only=ON
super_read_only=ON
~~~

Enabling binary logs and `log_replica_updates` on the replica prepares it for promotion to source or cascading replication. Leaf replicas that will never be promoted may have different requirements; in this lab we enable them in preparation for role switching.

`read_only` blocks writes from ordinary client accounts. `super_read_only` goes further, blocking direct writes even from users holding `SUPER` privileges, while still letting the replication applier apply upstream transactions. High-privilege admin accounts must still be controlled; these flags are not a replacement for SQL privilege boundaries.

Start MySQL on B, verify `server_id` differs from A, and confirm GTID variables are enabled. Ensure firewall rules permit TCP connections from B to A on the MySQL port and A does not block required traffic.

## 5. Initializing Replica Data from a Consistent Snapshot

A replica must start from a dataset aligned with the GTID/binlog coordinate from which it will consume subsequent changes. You cannot install an empty MySQL server and simply run `START REPLICA`; missing or mismatched starting data causes replication failures or silent divergence.

### Snapshot approach for a small lab

For small datasets, you can use `mysqldump` from the source:

~~~bash
mysqldump \
  --host=SOURCE_HOST \
  --user=BACKUP_USER \
  --single-transaction \
  --source-data=2 \
  --set-gtid-purged=ON \
  --routines \
  --events \
  --triggers \
  --databases appdb \
  --result-file=appdb-seed.sql
~~~

This command targets modern MySQL 8.0. `--single-transaction` takes a consistent snapshot for InnoDB tables; it does not guarantee consistent snapshots for non-transactional tables. Avoid running DDL during the dump. `--source-data=2` writes binlog coordinate metadata as comments; the GTID set is handled via `--set-gtid-purged=ON`.

If the dump emits `GTID_PURGED`, the target must be prepared appropriately—typically a clean instance or one whose GTID state has been verified. Never import this dump onto a server with an incompatible existing GTID history without reconciling first. For large databases, prefer physical backups, the MySQL Clone Plugin, or dedicated hot-backup tools to shorten seeding time.

Transfer the dump file to B over a secure channel and verify its checksum:

~~~bash
sha256sum appdb-seed.sql
~~~

Import onto the replica:

~~~bash
mysql --host=REPLICA_HOST --user=ADMIN_USER \
  < appdb-seed.sql
~~~

After importing, verify databases, tables, representative row counts, and the GTID set. Never proceed to configure replication if snapshot or GTID state is unclear.

### Why must snapshot and GTID match?

Suppose the snapshot captures data up to transaction T. The replica must receive every transaction after T. If the snapshot is older than T while the replica skips GTIDs already assumed included, data will go missing. Conversely, if the snapshot already contains transactions that the replica re-applies due to mismatched file/position coordinates, duplicate keys or data corruption will occur.

GTID auto-positioning lets both servers exchange executed GTID sets to locate missing transactions. It cannot fix an inconsistent initial snapshot.

## 6. Configuring GTID Auto-Position and Starting Replication

On B, configure the replication source:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = '10.20.0.11',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'REPLACE_WITH_SECRET',
  SOURCE_AUTO_POSITION = 1,
  SOURCE_SSL = 1;

START REPLICA;
~~~

In this lab, credentials are placeholders. In production, use proper secret management and TLS verification with CA/hostname checks per your MySQL version. Never pass passwords directly in scripts that could end up in shell history or logs.

`SOURCE_AUTO_POSITION=1` instructs MySQL to use GTIDs instead of manual binlog files and positions. Both servers must have compatible GTID settings and the replica must hold the proper initial GTID set. If using a custom CA certificate, configure `SOURCE_SSL_CA` and related TLS verification options per version docs.

Inspect status:

~~~sql
SHOW REPLICA STATUS\G
~~~

Expected state:

- `Replica_IO_Running = Yes`.
- `Replica_SQL_Running = Yes`.
- `Last_IO_Error` is empty.
- `Last_SQL_Error` is empty.
- `Source_Host` points to A.
- `Retrieved_Gtid_Set` grows as new transactions occur on the source.
- `Executed_Gtid_Set` catches up to `Retrieved_Gtid_Set`.

Column names may vary across MySQL versions. If replication stops, never look only at `Seconds_Behind_Source`; inspect `Last_IO_Error`, `Last_SQL_Error`, and individual thread states.

## 7. Verifying Replicated Data

On source A, create a dedicated probe table:

~~~sql
CREATE DATABASE IF NOT EXISTS replication_lab;

CREATE TABLE replication_lab.replication_probe (
    probe_id BIGINT NOT NULL PRIMARY KEY,
    payload VARCHAR(100) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

INSERT INTO replication_lab.replication_probe
    (probe_id, payload)
VALUES
    (1, 'first transaction'),
    (2, 'second transaction');
~~~

On replica B, verify:

~~~sql
SELECT *
FROM replication_lab.replication_probe
ORDER BY probe_id;
~~~

Run additional `INSERT`, `UPDATE`, and `DELETE` statements on the source and confirm results on the replica. Never insert test probe rows into real business tables.

### Verifying with GTIDs

On the source:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

On the replica:

~~~sql
SELECT
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;
~~~

The replica's GTID set must include the transactions applied from the source. Complex topologies do not always have identical GTID strings; a replica might hold local transactions if misconfigured or repurposed. In a single-source lab topology, avoid direct writes on the replica so GTID sets stay clean and comparable.

### Waiting for a specific GTID to apply

After writing on the source, capture the GTID set to wait for. On the replica, run:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'SOURCE_UUID:TRANSACTION_INTERVAL',
  10
);
~~~

Substitute the real GTID set retrieved from the source. Returning `0` means the replica executed the requested GTID set within the timeout; `1` indicates timeout; `NULL` indicates an error. This provides deterministic read-after-write verification for a specific transaction rather than sleeping an arbitrary number of seconds.

## 8. Observing Replication Lag

Replication lag is the delay between when a transaction commits on the source and when that transaction becomes readable on the replica. Lag can build during binlog network transfer, relay log queueing, or transaction application.

### Checking overall status

~~~sql
SHOW REPLICA STATUS\G
~~~

Key fields to watch:

| Field | Meaning |
|---|---|
| `Replica_IO_Running` | Whether the receiver thread is actively fetching binlogs |
| `Replica_SQL_Running` | Whether the applier thread is applying transactions |
| `Seconds_Behind_Source` | Estimated lag based on event timestamps |
| `Last_IO_Error` | Error reading binlogs from the source |
| `Last_SQL_Error` | Error applying relay logs |
| `Retrieved_Gtid_Set` | GTIDs received so far |
| `Executed_Gtid_Set` | GTIDs executed so far |
| `Relay_Log_Space` | Disk space consumed by relay logs |
| `Source_Server_Id` | Server ID of the current source |

`Seconds_Behind_Source` is useful yet imperfect. It can return `NULL` when threads stop or status is indeterminate; clock skew across hosts also distorts it. One huge transaction can spike lag abruptly even while the receiver thread runs normally.

### Inspecting receiver and applier in Performance Schema

On the replica:

~~~sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_QUEUED_TRANSACTION,
  RECEIVED_TRANSACTION_SET
FROM performance_schema.replication_connection_status;
~~~

Inspect applier workers:

~~~sql
SELECT
  CHANNEL_NAME,
  WORKER_ID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_APPLIED_TRANSACTION,
  APPLYING_TRANSACTION
FROM performance_schema.replication_applier_status_by_worker;
~~~

Columns may vary by MySQL version. Run `DESCRIBE performance_schema.replication_connection_status` and `DESCRIBE performance_schema.replication_applier_status_by_worker` to confirm exact schemas on your running server.

### Measuring lag with a heartbeat

`Seconds_Behind_Source` may not fully capture user-visible staleness. Maintain a heartbeat row on the source:

~~~sql
CREATE TABLE replication_lab.replication_heartbeat (
    heartbeat_id TINYINT NOT NULL PRIMARY KEY,
    source_time_utc DATETIME(6) NOT NULL
) ENGINE=InnoDB;

INSERT INTO replication_lab.replication_heartbeat
    (heartbeat_id, source_time_utc)
VALUES
    (1, UTC_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE
    source_time_utc = UTC_TIMESTAMP(6);
~~~

A periodic job on the source updates this row every second or few seconds. On the replica:

~~~sql
SELECT
  TIMESTAMPDIFF(
    MICROSECOND,
    source_time_utc,
    UTC_TIMESTAMP(6)
  ) / 1000000 AS observed_lag_seconds
FROM replication_lab.replication_heartbeat
WHERE heartbeat_id = 1;
~~~

Heartbeats must be updated and committed regularly. Synchronize clocks between source and replica; otherwise wall-clock measurements can appear negative or inaccurate. A heartbeat measures observed lag of that periodic update stream—it does not prove every earlier transaction has applied if huge transactions or parallel workers are running out of order.

### Tracking GTID gaps

You can diff source and replica GTID sets to see which transactions the replica still lacks. In a single-source topology, use `GTID_SUBSET` and `GTID_SUBTRACT`:

~~~sql
SELECT
  GTID_SUBSET(
    'REPLICA_EXECUTED_GTID_SET',
    'SOURCE_EXECUTED_GTID_SET'
  ) AS replica_is_subset,
  GTID_SUBTRACT(
    'SOURCE_EXECUTED_GTID_SET',
    'REPLICA_EXECUTED_GTID_SET'
  ) AS missing_from_replica;
~~~

Substitute the two captured GTID sets. If the replica is a subset of the source and the difference is empty after waiting, the replica has caught up to that transaction set. In multi-source topologies or with local transactions, analyze GTIDs per UUID rather than relying on one global comparison.

## 9. Simulating Replica Lag and Recovering

Perform this section only in the lab.

### Stopping the applier thread

On replica B:

~~~sql
STOP REPLICA SQL_THREAD;
~~~

On source A, generate several test transactions:

~~~sql
INSERT INTO replication_lab.replication_probe
    (probe_id, payload)
VALUES
    (100, 'lag test 100'),
    (101, 'lag test 101'),
    (102, 'lag test 102');
~~~

On B, observe:

- Receiver thread keeps running and fetching binlogs.
- Applier thread is stopped.
- `Retrieved_Gtid_Set` grows while `Executed_Gtid_Set` stays stalled.
- The new probe rows are not yet visible on B.
- Relay log size increases.

Resume the applier:

~~~sql
START REPLICA SQL_THREAD;
~~~

Wait for GTIDs to apply, then verify data. If the relay log hits a SQL error, inspect `Last_SQL_Error` and worker status before intervening. Never use `SQL_SLAVE_SKIP_COUNTER` or blindly skip transactions in a GTID topology; skipping a transaction can cause permanent data divergence.

### Distinguishing receiver lag from applier lag

- Receiver stopped: replica cannot fetch binlogs from source; check DNS, network, credentials, TLS, source health, and binlog retention.
- Receiver running, applier stopped: relay logs arrive yet fail to apply; inspect SQL errors, duplicate keys, schema drift, and workers.
- Both running yet lag climbs: heavy write rate, huge transactions, slow I/O, or insufficient applier capacity.
- Lag drops to 0 yet app reads stale data: check read routing, caches, transaction snapshots, and active endpoints.

Do not blindly raise applier worker counts without identifying the bottleneck. Multi-threaded appliers can boost throughput for parallelizable workloads, yet also increase resource contention and face commit-order/dependency constraints.

## 10. Preparing for Role Switching: Planned Switchover

A planned switchover is a scheduled primary transition where the old source remains healthy so writes can pause cleanly while the replica catches up. The objective is zero loss of committed transactions.

### Pre-switchover checklist

- B has both receiver and applier threads running cleanly.
- Zero `Last_IO_Error` or `Last_SQL_Error`.
- B has applied up to the target GTID set.
- Zero open business write transactions remain on A.
- The application can pause writes or enter maintenance mode.
- Endpoint/proxy/DNS cutover to B is planned.
- Operators have verified fencing and rollback procedures.
- Backups/restores and admin access are verified.

### Planned switchover sequence

**Step 1 — Stop new writes**

Put the application into maintenance/read-only mode or pause writers. Drain in-flight requests and wait for open transactions to finish. Never merely flip `read_only` and assume every active transaction has already completed.

**Step 2 — Capture final GTID set on the source**

On A, after stopping writes and draining transactions:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

Save this GTID set as the switchover coordinate.

**Step 3 — Wait for the replica to apply all GTIDs**

On B:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'GTID_SET_CAPTURED_FROM_SOURCE',
  60
);
~~~

Proceed only when the return value is `0`. On timeout, keep the app paused for writes, diagnose the lag, and resolve before proceeding. Never promote a replica without knowing which transactions remain unapplied.

**Step 4 — Fence the old source**

On A, enable read-only mode:

~~~sql
SET GLOBAL super_read_only = ON;
SET GLOBAL read_only = ON;
~~~

Simultaneously block applications and other writers from reaching A via proxies, firewalls, or orchestration. Fencing must block every write path, including background jobs and privileged accounts. `read_only`/`super_read_only` are an extra guardrail, not a replacement for infrastructure fencing.

**Step 5 — Stop replication on B and promote**

On B:

~~~sql
STOP REPLICA;
RESET REPLICA ALL;
SET GLOBAL super_read_only = OFF;
SET GLOBAL read_only = OFF;
~~~

`RESET REPLICA ALL` clears the replica's source connection config and relay log metadata; never run it until confirming B caught up and committing to promotion. Never run `RESET MASTER` or `RESET BINARY LOGS AND GTIDS` during switchover; those commands wipe binlog/GTID history needed downstream.

**Step 6 — Verify B accepts writes**

Insert a new probe transaction on B, verifying data and GTID advancement. Confirm privileges, read-only flags, and active endpoint routing.

**Step 7 — Switch application endpoints**

Update proxies, service discovery, or DNS per system architecture. Refresh connection pools so applications do not hold onto stale connections pointing at A. Re-enable writes only after confirming B alone receives write traffic.

## 11. Rehearsing Failover During a Source Outage

Unplanned failover is harder than switchover because the source may be unreachable and you cannot verify whether the final transactions reached the replica.

### Risk of split-brain

Split-brain occurs when both A and B act as primary and accept writes simultaneously. Under a network partition, clients on opposite sides can write to separate nodes. When connectivity heals, GTID sets diverge; MySQL cannot automatically merge two divergent write histories into one valid state.

Fencing is mandatory before enabling writes on the candidate:

- Power off or isolate the old source at the infrastructure layer.
- Revoke write routing to the old source.
- Stop `mysqld` or isolate networking wherever possible.
- Confirm all writers, schedulers, and background jobs can no longer write to the old node.

If you cannot prove the old source is fenced, do not open writes on the promoted replica.

### Choosing a candidate

When multiple replicas exist:

1. Collect `Retrieved_Gtid_Set` and `Executed_Gtid_Set` from each replica.
2. Identify the node that applied the greatest subset of recoverable transactions.
3. Check applier errors, active transactions, and relay logs.
4. Estimate transactions acknowledged to clients on the source that may not have replicated and could be lost.
5. Pick the candidate using RPO policy and GTID evidence—never solely by `Seconds_Behind_Source`.

If the old source is permanently lost while an asynchronous replica lacked recent transactions, failover incurs RPO > 0. Document potential data loss scope and execute business reconciliation post-recovery.

### Controlled failover sequence

1. Declare the incident and lock topology changes so a single operator/orchestrator coordinates.
2. Fence the old source at the infrastructure layer independent of MySQL if needed.
3. Confirm the candidate has zero applier errors and holds the best GTID set.
4. If received relay logs remain unapplied, evaluate applying them cleanly before promotion.
5. Stop replication and clear upstream config once promotion is decided.
6. Disable `read_only`/`super_read_only` on the candidate.
7. Verify data integrity, GTID state, and write capability.
8. Switch application endpoints and recycle connection pools.
9. Monitor error rates, latency, duplicates, and missing transactions.
10. Keep the old source fenced until a rebuild/rejoin plan runs.

Never auto-select a replica simply because it responds to ping or reports `Seconds_Behind_Source = 0`. That metric does not prove the node holds all transactions committed before the outage.

## 12. Rejoining the Former Source into the Topology

After a failover, A must never simply restart and resume taking writes. It may contain local transactions missing from B or a diverged GTID set.

Safe rejoin workflow:

1. Keep A fenced and read-only.
2. Collect GTID sets from both A and B.
3. Check whether A contains errant/divergent transactions.
4. If the two nodes diverged, never attempt to blindly auto-merge data.
5. Prefer rebuilding A from a fresh backup/snapshot of B, then configure A as a replica.
6. If rejoining via existing GTIDs, evaluate errant transactions, data diffs, and recovery safety upfront.
7. Once A replicates from B, verify GTID sets, row counts/checksums, and thread health.
8. Add A back to read pools only after consistency passes; never enable writes on it.

Never run `RESET MASTER` or wipe GTID history as a generic fix. Doing so destroys historical evidence and makes locating missing data harder.

Once A is rebuilt from a consistent snapshot of B, configure A as a replica pointing to the new primary:

~~~sql
-- Run on A after seeding data and verifying GTIDs.
SET GLOBAL super_read_only = ON;
SET GLOBAL read_only = ON;

CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = '10.20.0.12',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'REPLACE_WITH_SECRET',
  SOURCE_AUTO_POSITION = 1,
  SOURCE_SSL = 1;

START REPLICA;
~~~

Update endpoints, credentials, and TLS options to match your environment. Never run these commands on A while it still holds unresolved diverged data; enabling GTID auto-positioning does not erase errant transactions or repair differing rows.

## 13. Testing Roles and Consistency

In the lab, create a transaction verification table:

~~~sql
CREATE TABLE replication_lab.role_switch_test (
    request_id CHAR(36) NOT NULL PRIMARY KEY,
    note VARCHAR(100) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
~~~

Before switchover:

1. Write several request IDs on A.
2. Wait for B to apply them via GTID.
3. Compare row counts and request IDs across both nodes.
4. Execute the planned switchover.
5. Write new request IDs on B.
6. Once A is reconfigured as a replica of B, confirm A receives the new request IDs.

Unplanned failover drill:

- Stop A in the lab after writing several transactions.
- Intentionally introduce lag so B lacks part of the transactions.
- Run the candidate evaluation workflow and record potentially lost transactions.
- Fence A before promoting B.
- After B accepts writes, never restart A as an independent primary.
- Rebuild or rejoin A from B and reconcile data.

Results to record:

| Item | What to Observe |
|---|---|
| Receiver/applier | Threads running or stopped, last errors |
| GTID | Retrieved, executed, and missing sets |
| Lag | `Seconds_Behind_Source`, heartbeat, and backlog |
| Data consistency | Row counts, request IDs, and checksums |
| Role | Which node permits writes |
| Endpoint | Which node applications are connected to |
| Recovery | Whether the former node was rebuilt/rejoined or remains fenced |

## 14. RPO, RTO, and Choosing a Replication Mode

Two metrics evaluate failover quality:

- **RPO (Recovery Point Objective):** maximum tolerable data loss measured in time or transaction window.
- **RTO (Recovery Time Objective):** maximum tolerable duration to restore service.

Asynchronous replication can incur RPO > 0 because the source acknowledges commits before replicas receive and apply them. Semi-synchronous replication can shrink the data-loss window under specific conditions, yet does not guarantee zero data loss across every failure mode or configuration. Review ACK semantics, timeouts, async fallback rules, and replica-disconnect behavior for your exact version.

Group Replication/InnoDB Cluster or external HA orchestrators provide integrated membership, quorum, and automated failover, yet still require fencing design, network partition handling, client routing, and chaos testing. A manual source–replica pair does not become high-availability merely because `START REPLICA` works.

### Overview comparison table

| Model | Characteristics | Risks / Considerations |
|---|---|---|
| Asynchronous replication | Source commits independently of replicas | Recent transactions may be lost if source dies |
| Semisynchronous replication | Source waits for at least one replica ACK per policy | ACK does not mean replica applied the tx; timeouts/fallback impact RPO |
| Group Replication / InnoDB Cluster | Built-in membership, quorum, and failover | Higher complexity; requires proper node count/quorum and stable networking |
| External orchestrator | Manages topology and promotions by policy | Requires fencing, privileges, and failure-mode testing |

Never claim zero RPO without proving it across configuration, failure models, and live chaos tests. Measure RPO/RTO during drills rather than leaving them as numbers in design docs.

## 15. Operational and Alerting Checklist

### Before putting a replica into service

- [ ] Source has binary logging and GTID properly configured.
- [ ] Every node has a unique `server_id`.
- [ ] Initial snapshot is consistent and GTID state is verified.
- [ ] Replication user holds least privileges over a secured connection.
- [ ] Both receiver and applier threads are running.
- [ ] `Last_IO_Error` and `Last_SQL_Error` are empty.
- [ ] Sample rows, counts, or checksums are reconciled.
- [ ] `read_only` and `super_read_only` are enabled on the replica.
- [ ] Binlog retention covers expected outages and catch-up windows.

### Continuous monitoring

- [ ] Receiver/applier thread state.
- [ ] `Seconds_Behind_Source` and heartbeat lag.
- [ ] Retrieved/Executed GTID sets and transaction gaps.
- [ ] Relay log space and free disk capacity.
- [ ] `Last_IO_Error` / `Last_SQL_Error`.
- [ ] Binlog generation rate and retention margin.
- [ ] CPU, I/O, network, and applier throughput.
- [ ] Replica read error rate and report freshness.

### Before switching roles

- [ ] Maintenance plan and writer draining ready.
- [ ] Final source GTID set captured.
- [ ] Candidate applied up to the required GTID set.
- [ ] Old source fenced across every write path.
- [ ] Only one candidate promoted.
- [ ] Endpoint and connection pool refresh plan ready.
- [ ] Post-switchover data reconciliation planned.
- [ ] Rebuild/rejoin plan prepared for the old node.

## 16. Common Issues and Troubleshooting

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| `Replica_IO_Running = No` | Network, DNS, credentials, TLS, or source down | Inspect `Last_IO_Error`, TCP connectivity, grants, and certificates |
| `Replica_SQL_Running = No` | Applier SQL error, schema drift, or duplicate key | Inspect `Last_SQL_Error`, worker status, and affected rows |
| `Seconds_Behind_Source = NULL` | Thread stopped or insufficient timing info | Check receiver/applier states and Performance Schema |
| Continuously climbing lag | Huge transactions, heavy write rate, slow I/O, or undersized applier | Check relay logs, workers, CPU/I/O, and workload |
| GTID gap not shrinking | Replica not receiving or not applying transactions | Check Retrieved/Executed sets, thread states, and binlog retention |
| Replica missing rows after seed | Inconsistent snapshot or wrong GTID/coordinate | Verify dump source, `GTID_PURGED`, and data scope |
| Duplicate key on replica | Direct writes hit replica or seed data drifted | Halt automation, diff GTIDs and rows; never skip blindly |
| Old source accepts writes post-failover | Missing fencing or stale open endpoint | Isolate old source immediately, stop writers, and assess divergence |

When the applier halts on a data error, never delete rows or skip events just to make the thread run again. Find the root cause, assess impacted transactions, and execute a reconciled data fix.

## 17. Final Practice Scenarios

Execute sequentially and archive evidence:

**Scenario A — Build replication**

1. Configure A and B with distinct `server_id`s, GTIDs, and binary logging.
2. Create the replication user.
3. Seed B from a consistent snapshot.
4. Configure `SOURCE_AUTO_POSITION` and run `START REPLICA`.
5. Verify both threads, GTIDs, and probe data.

**Scenario B — Induce and recover from lag**

1. Stop `SQL_THREAD` on B.
2. Write several transactions on A.
3. Observe `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, and relay logs.
4. Run the heartbeat query to measure observed lag.
5. Start `SQL_THREAD` and wait for GTIDs to catch up.
6. Verify final data consistency.

**Scenario C — Planned switchover**

1. Pause writes and drain transactions on A.
2. Capture the final GTID set.
3. Wait for B to apply all GTIDs.
4. Fence A.
5. Promote B and switch endpoints.
6. Write new probe rows on B.
7. Reconfigure A as a replica of B.
8. Verify A receives the new transactions.

**Scenario D — Unplanned failover**

1. Write several transactions while intentionally making B lag.
2. Stop A in the lab.
3. Inspect GTIDs and estimate potentially lost data.
4. Fence A before opening writes on B.
5. Promote B per RPO decision.
6. Reconcile data and record the missing transaction window.
7. Rebuild/rejoin A from B.

### Completion criteria

- Replication runs steadily with zero I/O or applier errors.
- You can explain the difference between retrieved and executed transactions.
- You can prove a replica caught up to a specific GTID set.
- You can measure lag and explain the limitations of `Seconds_Behind_Source`.
- You can switch roles without ever letting two nodes accept writes concurrently.
- You can rejoin the former node without arbitrarily wiping GTID history.
- You can document observed RPO/RTO for each scenario.

## References

- [MySQL Reference Manual — Replication](https://dev.mysql.com/doc/refman/8.4/en/replication.html)
- [MySQL Reference Manual — GTID Concepts](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-concepts.html)
- [MySQL Reference Manual — GTID Auto-Positioning](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-auto-positioning.html)
- [MySQL Reference Manual — SHOW REPLICA STATUS](https://dev.mysql.com/doc/refman/8.4/en/show-replica-status.html)
- [MySQL Reference Manual — WAIT_FOR_EXECUTED_GTID_SET](https://dev.mysql.com/doc/refman/8.4/en/gtid-functions.html)
- [MySQL Reference Manual — Replication Performance Schema Tables](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-replication-tables.html)
- [MySQL Reference Manual — Semisynchronous Replication](https://dev.mysql.com/doc/refman/8.4/en/replication-semisync.html)

## Conclusion

Setting up a replica is a discipline of consistent snapshots, GTIDs, binary logs, and transaction application; switching roles adds verifying final state, fencing, and application routing. Observe receiver threads, applier threads, GTID gaps, heartbeats, and errors rather than relying on `Seconds_Behind_Source` alone. Planned switchovers require stopping writes and waiting for the replica to apply the final GTIDs before promoting. Unplanned failovers must fence the old source before opening writes on the candidate and accept RPO grounded in evidence. Finally, only rejoin the former source as a replica after reconciling GTIDs and data—typically by rebuilding from the new primary.
