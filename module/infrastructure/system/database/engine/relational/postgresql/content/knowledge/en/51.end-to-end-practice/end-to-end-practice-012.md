# Setting Up Primary, Standby, and Role Transition Drills in PostgreSQL

PostgreSQL can maintain one or more standby servers receiving WAL from a primary to serve read-only workloads, improve resilience, and minimize downtime when the main node fails. However, having a standby does not automatically equal high availability. An HA system must prove that the standby receives all WAL, replays it properly, can be promoted, applications shift connections safely, and the old node cannot continue accepting writes after failover.

This practice establishes physical streaming replication between a primary and a standby, configures monitoring, and rehearses two procedures:

- **Planned switchover:** transitioning roles while the primary is healthy, coordinating a clean write pause, waiting for the standby to catch up, and promoting.
- **Emergency failover:** cutting over to a standby when the primary becomes unavailable; requires identifying an adequately up-to-date node, fencing the old primary, and measuring/accepting potential data loss under asynchronous replication.

The single most important goal during a role transition is ensuring only one primary is ever allowed to accept writes. Promoting a standby before isolating the old primary can create a split-brain: two nodes independently accepting transactions whose WAL histories can no longer be reconciled into a single history. Changing DNS or connection strings alone is not fencing.

~~~mermaid
flowchart TD
    A["Primary serving writes"] --> B["WAL streaming"]
    B --> C["Standby receives and replays WAL"]
    C --> D{"Transition type"}
    D -->|"Planned switchover"| E["Quiesce writes and drain"]
    D -->|"Emergency failover"| F["Fence old primary"]
    E --> G["Verify standby caught up"]
    F --> H["Select standby with latest WAL"]
    G --> I["Promote standby"]
    H --> I
    I --> J["Switch endpoints and connection pools"]
    J --> K["Verify writes, replication, and application"]
    K --> L["Rebuild/rejoin old node as standby"]
~~~

This lesson is part of the **End-to-End Practice** chapter in the **Database Engine Relational PostgreSQL** module.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain primary, physical standby, WAL sender, WAL receiver, and replay.
2. Distinguish streaming replication from WAL archiving.
3. Prepare a primary for physical replication.
4. Create a replication role and configure `pg_hba.conf` securely.
5. Bootstrap a standby using `pg_basebackup`.
6. Configure `standby.signal`, `primary_conninfo`, and replication slots.
7. Verify WAL receive/replay progress and replication lag.
8. Understand synchronous vs. asynchronous replication, RPO, and RTO.
9. Monitor replication slots, WAL retention, and disk capacity.
10. Execute a planned switchover.
11. Execute an emergency failover with fencing.
12. Promote a standby and verify the new node acts as primary.
13. Cut over application endpoints and recycle connection pools.
14. Rejoin the old primary using `pg_rewind` or a fresh base backup.
15. Verify replication topology post-transition.
16. Rehearse failures without inducing split-brain.
17. Gather evidence and evaluate actual RPO/RTO.

## 2. Architecture and Terminology

In physical streaming replication:

- **Primary:** node accepting application write transactions and generating WAL.
- **Standby:** node receiving WAL, writing it to local storage, and replaying it to update data pages.
- **WAL sender:** process on the primary streaming WAL to standbys.
- **WAL receiver:** process on the standby receiving WAL.
- **Startup/recovery process:** replays WAL and keeps the standby in recovery mode.
- **Replication slot:** retains WAL segments required by a consumer.
- **WAL archive:** durable store holding WAL segments for recovery or catching up when streaming is interrupted.
- **Promotion:** ending recovery and turning a standby into a writable primary.
- **Fencing:** guaranteeing the old node can no longer operate as a primary.

~~~mermaid
flowchart LR
    A["Application writes"] --> P["Primary"]
    P --> W["WAL"]
    W --> S["WAL sender"]
    S --> R["WAL receiver"]
    R --> D["Standby WAL"]
    D --> H["Replay / recovery"]
    H --> Q["Hot standby reads"]
~~~

Physical replication ships WAL at the cluster level, not just rows belonging to a publication. A standby is a physical replica of the cluster and requires binary/data compatibility per PostgreSQL version, architecture, and upgrade rules.

## 3. Streaming Replication vs. WAL Archiving

Both mechanisms are typically combined:

**Streaming replication** maintains a continuous connection between primary and standby. WAL streams nearly in real time, keeping replication lag low when the network and nodes are healthy.

**WAL archiving** copies completed WAL segments to an archive store. A standby can fetch segments from the archive to catch up when WAL segments are no longer on the primary, or to recover from a base backup.

| Criterion | Streaming | WAL Archive |
|---|---|---|
| Transport | Persistent replication connection | Archive command / archive service |
| Latency | Typically low | Depends on segment switches and archive pipeline |
| Purpose | Near-real-time standby | Recovery, catch-up, PITR |
| Dependencies | Network, WAL sender/receiver | Archive storage and `restore_command` |
| On interruption | Reconnects if WAL remains on primary | Can fetch archived segments |
| Monitoring | Receiver state, LSN lag | Archive success/failure, archive freshness |

WAL archiving does not replace streaming monitoring. Streaming does not replace backups or archive retention.

## 4. Defining Topology and Failure Domains

Before setup, document:

- Primary hostname/IP and data directory.
- Standby hostname/IP and data directory.
- PostgreSQL major/minor version.
- OS/architecture and storage layout.
- Network routing, firewalls, and TLS policy.
- Replication mode: async or sync.
- WAL archive destination.
- Replication slot ownership.
- Application endpoint / VIP / proxy.
- HA manager if used.
- Backup/PITR policy.
- Target RPO/RTO.
- Personnel authorized to promote/fence.

Primary and standby should reside in independent failure domains as required: separate physical hosts, storage fault domains, or availability zones. Two VMs on the same hypervisor or two disks on the same storage array can fail together in a single incident.

Do not place a synchronous standby so far away that network round-trip latency violates commit latency SLOs if synchronous mode is enabled.

## 5. Checking Version and Identity on Both Nodes

On each node, verify the PostgreSQL version:

~~~sql
SELECT
    version(),
    current_setting('server_version_num') AS server_version_num,
    pg_is_in_recovery() AS is_standby,
    pg_postmaster_start_time();
~~~

Check binaries:

~~~bash
postgres --version
pg_basebackup --version
pg_ctl --version
~~~

Primary and physical standby require compatible versions/formats per PostgreSQL rules. Never run `pg_basebackup` from an incompatible major version or arbitrarily copy a live running data directory with filesystem copy tools.

Record the system identifier via `pg_controldata` on each cluster. A primary and its physical standby belong to the same cluster lineage; a base backup from the primary produces a standby sharing that system identifier.

## 6. Configuring the Primary for Physical Replication

Common parameters:

~~~conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = 2GB
max_slot_wal_keep_size = 20GB
hot_standby = on
archive_mode = on
archive_command = 'test ! -f /archive/%f && cp %p /archive/%f'
~~~

These settings illustrate the components rather than a copy-paste production config. Archive paths, capacity, permissions, and upload mechanisms must suit your environment. The sample `archive_command` uses a local filesystem and must be replaced with a reliable archive service in production.

Parameter meanings:

- `wal_level = replica`: emits sufficient WAL for physical replication.
- `max_wal_senders`: maximum concurrent WAL sender connections.
- `max_replication_slots`: maximum allowed replication slots.
- `wal_keep_size`: minimum WAL retained by config; does not replace slots or archiving.
- `max_slot_wal_keep_size`: upper bound on WAL retained by replication slots on supported versions.
- `hot_standby`: permits read-only queries while the standby replays WAL.
- `archive_mode`/`archive_command`: copies completed WAL segments to archive storage.

Some settings require a server restart. Inspect `context` before editing:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'hot_standby',
    'archive_mode'
)
ORDER BY name;
~~~

Do not set `max_slot_wal_keep_size` too low without understanding slot invalidation; slots can be invalidated if needed WAL gets recycled. Nor should you leave it unlimited without capacity alerting.

## 7. Creating the Replication Role

On the primary, create a dedicated replication role:

~~~sql
CREATE ROLE replicator
    WITH LOGIN
    REPLICATION
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT;
~~~

Set the password via a secret manager or secure credential workflow. Never commit passwords into source control, shell history, or logs.

Verify the role:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication,
    rolsuper
FROM pg_roles
WHERE rolname = 'replicator';
~~~

The `REPLICATION` attribute permits replication protocol connections. Restrict source IPs in `pg_hba.conf`, enforce TLS per policy, and rotate credentials regularly.

## 8. Configuring `pg_hba.conf`

On the primary, allow the standby host to open replication connections:

~~~conf
hostssl replication replicator 10.20.30.12/32 scram-sha-256
~~~

Replace the example IP with your standby's IP/CIDR. If your environment does not use TLS, evaluate security policy before using a `host` rule; prefer `hostssl` with certificate verification wherever feasible.

Reload configuration:

~~~sql
SELECT pg_reload_conf();
~~~

Check for parse errors:

~~~sql
SELECT *
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
~~~

`pg_hba.conf` rules evaluate top-to-bottom. A broader rule higher up can shadow a more specific rule below. Also verify network firewalls and security groups.

## 9. Verifying WAL Archiving

On the primary:

~~~sql
SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Watch for:

- Rising `failed_count`.
- `last_archived_time` lagging far behind WAL generation.
- Archive destination running out of space.
- `archive_command` returning errors.
- WAL segments piling up in `pg_wal`.

If `archive_command` fails repeatedly, PostgreSQL retries and retains unarchived WAL on the primary, causing disk usage to climb rapidly. Configure alerts and a runbook.

An archive pipeline is trustworthy only when monitored for existence, integrity, retention, access control, and verified via restore tests. Never manually delete WAL archives without checking PITR and standby dependencies.

## 10. Creating a Replication Slot for the Standby

A physical replication slot instructs the primary to retain WAL needed by a standby if it disconnects temporarily.

Create a slot:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
~~~

Inspect slots:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
WHERE slot_type = 'physical';
~~~

Some columns exist only on newer PostgreSQL versions. If a column is missing, inspect `pg_replication_slots` on your deployed version.

Every slot must have an explicit owner. Do not leave unused spare slots lying around, as inactive slots still pin WAL. If a standby is configured to use a slot, the slot name must match.

You can let `pg_basebackup` create the slot using its options, but do not create the slot manually and also pass flags instructing the tool to create the same slot.

## 11. Bootstrapping the Standby with `pg_basebackup`

The standby needs a consistent base backup from the primary. `pg_basebackup` uses the replication protocol to copy data files and stream WAL during the backup.

Example:

~~~bash
pg_basebackup \
  --host=primary.example.internal \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/17/standby \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf \
  --create-slot \
  --slot=standby_a
~~~

Flags and syntax vary slightly across client versions. Run `pg_basebackup --help` and check documentation for your major version.

Before running:

- Target data directory must be empty or safely prepared.
- OS user ownership on the data directory must match PostgreSQL's service user.
- Disk capacity suffices for the base backup plus incoming WAL.
- Network and `pg_hba.conf` permit replication connections.
- Role has `REPLICATION` privilege.
- Slot capacity and slot name are verified.
- Backup source is the primary of the right cluster.

Never run `pg_basebackup` into a data directory currently used by a live PostgreSQL server.

## 12. `standby.signal` and Recovery Configuration

In modern PostgreSQL, the `standby.signal` file tells the server to start in standby mode. Passing `--write-recovery-conf` to `pg_basebackup` creates `standby.signal` and writes connection settings into configuration.

Example:

~~~conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_a sslmode=verify-full'
primary_slot_name = 'standby_a'
recovery_target_timeline = 'latest'
restore_command = 'cp /archive/%f %p'
~~~

Certificates, passwords, and archive paths must be secured properly. Avoid storing plaintext passwords in world-readable files.

- `primary_conninfo`: connection string to the upstream primary.
- `application_name`: standby name reported on the primary.
- `primary_slot_name`: physical replication slot name.
- `recovery_target_timeline = latest`: follows the newest recoverable timeline.
- `restore_command`: fetches archived WAL segments when needed.

Older PostgreSQL versions placed recovery settings in `recovery.conf`; never mix legacy and modern syntax. Verify against your major version's docs.

## 13. Starting and Verifying the Standby

Start PostgreSQL via your environment's service manager or `pg_ctl`. On the standby, verify:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

Expected results:

- `is_standby = true`.
- Receive/replay LSN advances as the primary generates WAL.
- Standby rejects ordinary write transactions.
- WAL receiver status is `streaming`.

Inspect the WAL receiver:

~~~sql
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
~~~

Columns vary across versions. If no row appears, the receiver may not be connected yet, may have disconnected, or the standby may currently be reading WAL from the archive.

## 14. Verifying from the Primary

On the primary:

~~~sql
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
~~~

Expect the standby to appear with:

- Correct `application_name`.
- `state = streaming`.
- `sync_state` reflecting async/sync/quorum policy.
- LSNs advancing with workload activity.

Never treat a single `state = streaming` snapshot as sufficient. Observe multiple samples and verify LSNs actually advance.

## 15. Testing Replication with a Smoke Transaction

On the primary, create a dedicated smoke-test table if permissions and the change window allow:

~~~sql
CREATE TABLE IF NOT EXISTS public.replication_smoke_test (
    id bigint PRIMARY KEY,
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.replication_smoke_test (id, message)
VALUES (1, 'replication-check')
ON CONFLICT (id) DO UPDATE
SET message = EXCLUDED.message,
    created_at = now();
~~~

On the standby, read:

~~~sql
SELECT *
FROM public.replication_smoke_test
WHERE id = 1;
~~~

A hot standby allows read-only queries. If the row has not appeared, check receive/replay LSN, replication connectivity, recovery conflicts, and WAL logs. Never attempt `INSERT`/`UPDATE` on the standby.

Clean up test rows from the primary per policy afterward. Record the commit timestamp and when the row became visible on the standby to gauge apply delay.

## 16. Is Physical Replication Asynchronous or Synchronous?

By default, physical streaming replication is asynchronous unless `synchronous_standby_names` is configured.

**Asynchronous replication:** the primary does not wait for standbys to flush or replay WAL before acknowledging a commit. Commit latency is lower, yet the primary may lose recently committed transactions if failing over to a standby that has not received that WAL.

**Synchronous replication:** commits wait for one or more standbys to acknowledge WAL according to `synchronous_commit` and `synchronous_standby_names`. Durability improves, while commit latency and availability become coupled to standby and network health.

| Criterion | Asynchronous | Synchronous |
|---|---|---|
| Commit latency | Usually lower | Adds network and standby wait |
| RPO on sudden primary loss | Can be > 0 | Can approach 0 for commits acknowledged per policy |
| Standby dependency | Lower | Higher |
| Availability if standby drops | Primary keeps committing | Writes may block depending on config |
| Complexity | Lower | Requires quorum/failover design |

Synchronous replication does not automatically guarantee zero data loss across every topology or failure mode. You must understand required ack counts, failure domains, and how your failover manager picks the winning node.

## 17. Configuring Synchronous Replication

Example prioritizing one synchronous standby:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

Example quorum: wait for any one listed standby:

~~~conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

Names in `synchronous_standby_names` must match the `application_name` sent by each standby in `primary_conninfo`.

`synchronous_commit` levels:

- `off`: skips waiting for local WAL flush per commit; PostgreSQL stays crash-consistent, though recent commits can be lost on OS/server crash.
- `local`: waits for local WAL flush, not standby acks.
- `remote_write`: waits for the synchronous standby to write WAL to its OS, not necessarily flushed durably to storage.
- `on`: waits for remote WAL flush on synchronous standbys per policy.
- `remote_apply`: waits for the standby to replay the transaction—useful when read-after-write consistency on standbys is required, at higher latency cost.

`on` is the common choice for synchronous durability. Pick `remote_apply` only when applications genuinely require standby replay before commit returns.

### Checking Sync Status

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

`sync_state` reports `async`, `potential`, `sync`, or `quorum` depending on configuration and version.

## 18. RPO and RTO

**RPO (Recovery Point Objective):** maximum tolerable data loss during recovery from an outage.

**RTO (Recovery Time Objective):** maximum acceptable time to restore service to an operational state.

Under async replication, RPO depends on how much WAL the primary acknowledged to clients that standbys had not yet received or flushed before the crash.

Under synchronous replication, commits acknowledged after standbys satisfy the configured ack policy drastically shrink RPO. Still, examine:
- How many standbys are synchronous.
- Which `synchronous_commit` level is active.
- Whether failover guarantees picking an acknowledged standby.
- Whether standbys and storage inhabit independent failure domains.
- Whether split-brain is possible.

RTO encompasses detection, fencing, promotion, endpoint cutover, connection pool recovery, and validation. Promoting the database is only one piece of RTO.
## 19. Monitoring Replication Lag

Measure lag from multiple angles:

- Primary `sent_lsn`.
- Standby write/flush/replay LSNs.
- Slot `restart_lsn` and `confirmed_flush_lsn`.
- Time since last message.
- Retained WAL bytes.
- Application read freshness.

On the primary:

~~~sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_behind_replay,
    pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS bytes_behind_flush
FROM pg_stat_replication;
~~~

On the standby:

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS received_not_replayed_bytes;
~~~

Take LSN measurements roughly together and track which node you query. Bytes behind measures WAL position distance, not directly seconds of lag.

`pg_last_xact_replay_timestamp()` can appear stale whenever the primary receives no writes; do not mistake an idle workload for replication lag. Combine LSNs, last message timestamps, and a synthetic heartbeat workload.

## 20. Monitoring Replication Slots and WAL Capacity

On the primary:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NULL THEN NULL
        ELSE pg_size_pretty(
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
        )
    END AS wal_distance
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Monitor free disk space on filesystems hosting `pg_wal` and WAL archives. LSN distance is an indicator rather than exact file bytes due to segment retention, checkpoints, and other consumers.

Alerts to configure:

- Standby disconnected.
- Replay lag above threshold.
- Slot inactive for too long.
- WAL distance growing steadily.
- Low `safe_wal_size` or invalidated slot.
- Archive failures.
- Free disk space below safety reserve.
- Replication authentication errors.

Never drop inactive slots automatically. Verify the slot owner and recovery path first.

## 21. How Switchover Differs from Failover

**Switchover** is a planned role transition. The primary is healthy, writes can be paused gracefully, standbys catch up and replay WAL to a target point, and leadership transfers without losing drained transactions.

**Failover** is an emergency role transition when the primary can no longer serve or must be isolated. You may not know exactly which commits the primary acknowledged that standbys never received. Async replication can lose recent data.

| Criterion | Switchover | Failover |
|---|---|---|
| Old primary | Accessible and healthy | May be unreachable or crashed |
| Writes | Can be quiesced/drained | May terminate abruptly |
| WAL catch-up | Can wait for target LSN | Picks standby with newest WAL |
| RPO | Can achieve 0 if drained cleanly | Depends on sync/async mode and received WAL |
| Fencing | Still required before opening writes on new node | Mandatory prior to promotion |
| Goal | Maintenance / planned rotation | Service restoration |

Never label an unplanned promotion "switchover" when the primary was not fenced and writes were not drained.

## 22. Prerequisites Before Running a Drill

A drill requires:

- An approved staging environment or dedicated drill cluster.
- Verified backups and PITR readiness.
- Healthy primary and standby.
- Replication lag within bounds.
- Operational WAL archiving.
- Switchable application endpoints.
- Tested fencing mechanisms.
- A synthetic test workload and verification markers.
- Abort conditions and rollback/recovery paths.
- Recorded target RPO/RTO.

Never simulate failover by killing a production primary without formal change/incident authorization and an approved HA procedure.

## 23. Planned Switchover: Overview

A safe switchover follows:

1. Verify primary and standby health.
2. Confirm the standby is an eligible candidate.
3. Stop new application writes.
4. Drain active transactions and background writers per plan.
5. Record the target LSN on the primary.
6. Wait for the standby to replay through the target LSN.
7. Fence/stop the old primary.
8. Promote the standby.
9. Verify the new node has exited recovery mode.
10. Switch application endpoints.
11. Resume writes in a controlled manner.
12. Rebuild/rejoin the old node as a standby.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant P as Old Primary
    participant S as Standby
    App->>P: Stop new writes
    App->>P: Drain active transactions
    P->>P: Record target LSN
    P->>S: Continue WAL streaming
    S->>S: Replay through target LSN
    P->>P: Fence / stop
    S->>S: Promote
    App->>S: Connect to new primary
    App->>S: Smoke write and verify
    P->>S: Rejoin old primary as standby
~~~

## 24. Switchover: Checking Standby Candidacy

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

On the standby:

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
~~~

Confirm:

- Standby is streaming stably.
- Replay is not inadvertently paused.
- No severe recovery conflicts exist.
- Sufficient disk space remains.
- Standby is not overloaded by read traffic.
- Archive/WAL availability supports recovery.
- Chosen node is an HA-policy-approved candidate.

If multiple standbys exist, select candidates by flush/replay position and failure-domain policy—not simply whichever hostname is easiest to type.

## 25. Switchover: Quiescing and Draining Writes

Stop writes across every producer:

- Web/API services.
- Background workers.
- Scheduled jobs.
- ETL/CDC control writes.
- Admin scripts.
- Batch jobs.
- Any other services hitting the database directly.

Use maintenance mode, traffic gates, or application write pauses. Then wait for in-flight transactions to finish or handle them per runbook.

Check active transactions:

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
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Never terminate every session blindly. A long transaction could be critical work; identify its owner and drain properly.

## 26. Switchover: Recording Target LSN and Waiting for Replay

Once writes are stopped and transactions drained, capture the target LSN on the primary:

~~~sql
SELECT pg_current_wal_lsn() AS switchover_target_lsn;
~~~

Record that value. On the standby, inspect replay LSN:

~~~sql
SELECT
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_wal_receive_lsn() AS receive_lsn;
~~~

Proceed only once replay LSN meets or exceeds the target LSN:

~~~sql
SELECT
    pg_last_wal_replay_lsn() >= '0/50000A0'::pg_lsn
        AS standby_replayed_target;
~~~

Replace the example LSN with the exact LSN captured above. If the standby has not reached the target, wait for streaming/replay or investigate; never promote early when aiming for a zero-loss planned switchover.

A final commit may still need WAL flush/replay while recovery catches up. Confirm stable state before proceeding.

## 27. Switchover: Stopping the Old Primary and Promoting

Once the standby has replayed through the target, shut down the old primary cleanly:

~~~bash
pg_ctl -D /path/to/old-primary-data stop -m fast
~~~

Or use your platform's service manager. Confirm the old node has stopped and is fenced from application writes.

Next, promote the standby:

~~~sql
SELECT pg_promote(wait => true, wait_seconds => 60);
~~~

Alternatively:

~~~bash
pg_ctl -D /path/to/standby-data promote
~~~

Use only one appropriate promotion method. If an HA manager such as Patroni or repmgr manages the cluster, follow the manager's workflow; never promote manually behind its state machine's back.

Verify on the new node:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_current_wal_lsn() AS current_lsn,
    pg_postmaster_start_time();
~~~

Expect `is_standby = false`. The new node is now a PostgreSQL primary, though full traffic should remain gated until endpoints, roles, archiving, and replication are verified.

## 28. Emergency Failover: Node Selection Principles

When the primary goes down:

1. Determine whether the primary is truly down or merely network-partitioned.
2. Fence the old primary via infrastructure controls.
3. Inventory all surviving standbys.
4. Choose the standby with the newest verifiable WAL receive/flush/replay position.
5. Assess potential data loss based on replication mode.
6. Log the decision maker and timestamp.
7. Promote strictly one candidate.
8. Cut over application endpoints.
9. Rebuild replication topology.

Never promote a standby merely because it is reachable while the old primary might still accept writes on another network segment.

### Fencing Mechanisms Include

- Powering off the node via hypervisor or cloud API.
- STONITH via cluster manager.
- Network/storage isolation preventing the old node from accepting writes.
- Stopping PostgreSQL and disabling service auto-restart.
- Revoking routes/VIPs/credentials per HA design.

Fencing must be verified at the infrastructure layer. Updating DNS or load balancer backends alone does not stop existing clients from writing directly to the old primary.

## 29. Failover: Assessing Potential Data Loss

Under asynchronous replication, the primary may have returned `COMMIT` to clients for WAL that never reached the chosen standby.

Gather:

- Last confirmed application commit from audit trails if available.
- Primary's last known LSN/metrics.
- Standby receive/flush/replay LSNs.
- Last heartbeat/event watermark.
- Pre-outage replication lag.
- Downstream broker/CDC offsets if relevant.

You cannot determine exact data loss solely from `pg_last_xact_replay_timestamp()` during idle periods or clock skew. Rely on LSN metrics and application-level commit markers.

If the old primary is unreachable, its exact final LSN may be unknown. Record actual RPO honestly as an estimate or unknown rather than inventing a number.

## 30. Failover: Fence First, Then Promote

After confirming the old primary is fenced, run on the chosen standby candidate:

~~~sql
SELECT pg_promote(wait => true, wait_seconds => 60);
~~~

Verify:

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_current_wal_lsn(),
    pg_postmaster_start_time();
~~~

Expect `pg_is_in_recovery() = false`.

Check PostgreSQL logs to confirm promotion and timeline switch completed. Never run `pg_promote` on multiple standbys concurrently. Exactly one candidate may become primary.

## 31. Timelines After Promotion

Each time a standby is promoted, PostgreSQL creates a new timeline. Timeline history files describe where the new WAL branch diverged.

Inspect timeline and WAL state with:

~~~bash
pg_controldata /path/to/new-primary-data
~~~

And inspect WAL files/history using version-appropriate tools.

Remaining standbys must follow the new timeline. With `recovery_target_timeline = 'latest'`, standbys can follow the new timeline provided required WAL history and segments are accessible.

Timelines are part of PostgreSQL's WAL recovery model; never manually delete timeline history files or WAL segments.

## 32. Switching Application Endpoints

Once the new node is promoted and verified:

- Update VIP / load balancer / service discovery / DNS per your HA architecture.
- Point connection pools to the new endpoint.
- Close or recycle existing pooled connections.
- Restore write traffic via canary ramp-up.
- Verify transaction commits.
- Verify background workers and scheduled jobs.
- Verify read routing if read replicas exist.

DNS TTLs can cause clients to cache old IPs. Connection pools may hold sockets open longer than DNS TTLs. Explicit pool recycling or proxy-level failover may be necessary.

Never check only a single application instance. Verify all services, scripts, and integrations reach the new endpoint.

## 33. Smoke Testing After Promotion

After opening limited traffic, run controlled checks:

~~~sql
SELECT
    current_database(),
    current_user,
    pg_is_in_recovery(),
    pg_current_wal_lsn();
~~~

Execute a small transaction with a unique marker:

~~~sql
CREATE TABLE IF NOT EXISTS public.ha_drill_marker (
    drill_id text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    note text NOT NULL
);

INSERT INTO public.ha_drill_marker (drill_id, note)
VALUES ('drill-2026-11-14-a', 'post-promotion-write-check')
ON CONFLICT (drill_id) DO UPDATE
SET created_at = now(),
    note = EXCLUDED.note;
~~~

Confirm the marker reads back cleanly and application roles hold proper permissions. Use table/marker names suited to the drill environment; avoid creating ad-hoc test objects in production without approval.

Verify:
- Application connection success.
- Read/write paths.
- Error rates and latency.
- Transaction commits.
- Sequence/identity behavior.
- Roles and grants.
- Background jobs.
- Replication and archiving.
- CDC/downstream health.

## 34. Rebuilding Replication Topology After Failover

After promotion, the new node is primary. Surviving standbys may need repointing to the new upstream. The old primary may have diverged and cannot simply be restarted as a standby.

Steps:

1. Identify which nodes will serve as standbys.
2. Fence the old primary if not already done.
3. Determine whether the old node can be rewound or requires a fresh base backup.
4. Create/recreate physical replication slots on the new primary.
5. Configure `primary_conninfo` pointing to the new primary.
6. Configure `primary_slot_name` if slots are used.
7. Ensure `standby.signal` exists.
8. Start the standby.
9. Verify WAL receiver and replay.
10. Monitor lag and archiving.

Never start the old node as a writable primary. It may carry a diverged timeline.

## 35. Using `pg_rewind` to Rejoin the Old Primary

`pg_rewind` can synchronize a diverged data directory back onto the new source's timeline history when prerequisites are met. It is not a merge of two primary write histories.

Key prerequisites typically include:

- Target cluster was shut down cleanly.
- Source and target share a common ancestor timeline.
- Target had `data_checksums` or `wal_log_hints` enabled prior to divergence.
- `full_page_writes` is enabled.
- Required WAL from the divergence point onward remains in `pg_wal` or is fetchable from the archive as configured.
- Compatible PostgreSQL binaries.

Verify prerequisites against your version's documentation before running.

Conceptual command example:

~~~bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/17/old-primary \
  --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user" \
  --write-recovery-conf
~~~

Options and required role privileges depend on version. The source connection requires appropriate read privileges; never put plaintext passwords in shell history.

After `pg_rewind`, inspect recovery configuration, `primary_conninfo`, slot settings, file permissions, and `standby.signal`. If `pg_rewind` prerequisites are unmet or WAL is missing, rebuilding with `pg_basebackup` is safer and easier to verify.

## 36. When Must You Rebuild with `pg_basebackup`?

Take a fresh base backup when:

- No suitable common timeline history exists.
- Target lacked `wal_log_hints` or data checksums before divergence.
- Required WAL segments were lost.
- Target data directory could not shut down cleanly.
- `pg_rewind` fails with unrecoverable errors.
- Data directory integrity is uncertain or corrupted.
- You need a simple, verifiable clean recovery.

Do not repeatedly re-run `pg_rewind` tweaking flags to bypass prerequisites. If the tool cannot prove the target/source relationship, rebuild from the new primary.

## 37. Replication Slots After Promotion

Replication slots are cluster-scoped and must be audited after failover. Do not assume all physical or logical slots automatically survive and work identically post-promotion across every PostgreSQL version and topology.

Inventory slots on the new primary:

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

Recreate slots for standbys/consumers per owner and runbook. For logical CDC, check failover slot support and synchronized standby slots if supported by your PostgreSQL version and connector. If a slot cannot resume, connectors may require a snapshot, rebootstrap, or reconciliation.

Never drop logical slots still in use by consumers. Confirm owner, retention, and WAL capacity before cleanup.

## 38. Synchronous Replication and Failover Behavior

Synchronous configuration affects both durability and availability.

If config requires one synchronous standby and that standby disconnects, commits may hang until another synchronous standby connects or policy changes. Write workloads can block.

Before a drill, verify:

- `synchronous_standby_names`.
- `synchronous_commit` at database, role, and session levels.
- Standby `application_name`.
- `FIRST` vs. `ANY` quorum semantics.
- Count of eligible standbys.
- Behavior when one or all synchronous standbys go offline.
- Whether the failover manager strictly promotes an acknowledged standby.

Never lower `synchronous_commit` "to get the system moving again" without understanding the altered RPO and logging the change. Durability policy changes require owner approval.

## 39. Cascading Replication

A standby can serve as upstream to another standby (cascading replication). This reduces WAL sender load on the primary or ships replication across distant sites.

Risks:

- Lag accumulates across multiple hops.
- Upstream standby failure cuts off downstream WAL streams.
- Promotion must track timeline and ancestry carefully.
- Monitoring must measure every hop.
- Upstream slot/WAL retention requires adequate disk capacity.

Never select a cascading node as a failover candidate based solely on reachability. Verify it has received/replayed sufficient WAL and sits on a valid timeline.

## 40. Using an HA Manager vs. Manual Operations

In production, teams generally rely on an HA manager with state management—such as Patroni, repmgr, Pacemaker/Corosync, or a managed database failover service—depending on platform.

An HA manager coordinates:

- Leader election.
- Health checks.
- Fencing.
- Promotion.
- Endpoint/VIP updates.
- Rejoin/rebuild.
- Replication configuration.
- Failover history.

Tools vary in semantics and prerequisites. Study your tool's runbook and establish a single source of authority.

Never mix manual `pg_promote` commands with a running HA manager outside the manager's workflow. Doing so can produce dual leaders or split state.

## 41. Split-Brain: Causes and Consequences

Split-brain occurs when two nodes both act as primary and accept independent writes.

Common causes:

- Network partition isolates the old primary from standbys while it still serves some clients.
- Promoting a standby before fencing the old primary.
- Two HA managers simultaneously controlling the cluster.
- VIP/DNS updates leave direct client connections hitting the old primary.
- Fencing failed or went unverified.
- An operator manually promotes multiple nodes.

Consequences:

- Two WAL timelines diverge.
- Writes cannot be merged automatically.
- Data loss or business state conflicts.
- Difficult to determine the canonical truth.
- Recovery may require picking one branch and manually reconciling writes from the other.

Mitigations:
- Single leader authority.
- Reliable fencing / STONITH.
- Proper quorum/lease policies.
- Endpoint enforcement and blocking direct node access.
- Strict promotion authorization.
- Clear runbooks and regular drills.

DNS or application configuration merely steers clients; it never replaces fencing.

## 42. Rehearsing Planned Switchover in Staging

A drill checklist:

### Preparation

- Verify primary and standby health.
- Record baseline LSNs and replication lag.
- Confirm backup/restore readiness.
- Enable application write pause.
- Record start timestamp.
- Verify endpoint cutover procedure.
- Prepare test transaction markers.

### Execution

1. Stop new writes.
2. Drain in-flight transactions.
3. Record target LSN on primary.
4. Wait for standby to replay target LSN.
5. Stop/fence old primary.
6. Promote standby.
7. Cut over endpoints.
8. Open canary writes.
9. Verify markers and application health.
10. Rejoin old primary as standby.

### Outcomes

Record:
- Detection/preparation duration.
- Drain duration.
- Promotion duration.
- Endpoint cutover duration.
- Time to first successful write.
- Actual RPO.
- Actual RTO.
- Replication lag after rejoin.
- Issues and follow-up actions.

## 43. Rehearsing Unplanned Failover in Staging

Failover drills simulate controlled node failures—such as stopping the PostgreSQL service or isolating a host/network in a test environment.

Never rely solely on `kill -9` to simulate every failure; it tests only one crash class. Separate drills may be needed for host loss, network partitions, storage failures, and availability-zone outages.

Procedure:

1. Start a write workload with markers/sequences.
2. Record replication lag and last acknowledged commit.
3. Simulate primary outage.
4. Execute fencing.
5. Select the most up-to-date standby.
6. Record WAL/replay position.
7. Promote one node.
8. Cut over endpoints.
9. Verify application health.
10. Reconcile markers and transactions.
11. Rebuild the old primary.
12. Restore full topology.
13. Calculate actual RPO/RTO.

If the primary dies abruptly in async mode, some commits may not have reached the standby. Never mark a drill "zero-loss" unless proven by commit markers.

## 44. Verifying Data Consistency After Failover

Verification checks should include:

- Primary/standby role state.
- Database identity and timeline.
- Critical row counts and aggregates.
- Last committed business marker.
- Sequence/identity values.
- Constraints and index validity.
- Replication catch-up.
- Application read/write tests.
- CDC event completeness.
- Downstream reconciliation.

Example business watermark check:

~~~sql
SELECT
    max(event_sequence) AS latest_sequence,
    count(*) AS event_count
FROM public.integration_events;
~~~

Reconcile against producer/consumer watermarks. Matching aggregate counts alone do not prove every row matches; for critical data, compare key ranges, chunks, or checksums.

## 45. Backups and PITR Before and After Role Transitions

A physical standby is not an independent backup. If data is accidentally deleted on the primary, that deletion replays onto the standby.

Maintain:
- Base backups.
- Continuous WAL archiving.
- Restore tests.
- Appropriate retention.
- Offsite/independent storage.
- Encryption key management.
- PITR runbooks.
- Snapshots of config/package inventory.
- Plans for writes occurring post-cutover.

Pre-transition backups provide a recovery baseline, yet if the new primary already accepted writes, rolling back to an old backup loses those writes unless a reverse sync/replay strategy exists.

Post-promotion, verify `archive_command` or the archive service on the new primary. If archive destinations or timeline handling break, the PITR chain breaks.

WAL archives must retain timeline history files. Never prune segments purely by filename or age while ignoring archive retention policy.

## 46. Security and Access Control for Replication

Replication opens cluster-wide data access. Protect:

- Dedicated replication role.
- TLS/mTLS per policy.
- Source restrictions in `pg_hba.conf`.
- Network ACLs / security groups.
- Secret manager and credential rotation.
- OS file permissions.
- Archive encryption and access controls.
- Auditing of connection attempts.
- HA manager credentials.
- Fencing API permissions.

Never grant superuser to a replication role without verified technical justification. Separate operator privileges authorized to promote from application runtime roles.

## 47. HA Monitoring Dashboard

A dashboard should cover:

| Group | Metrics |
|---|---|
| Role | Current primary, standby state, timeline |
| Connectivity | WAL receiver status, sender count, connection errors |
| Progress | Sent/write/flush/replay LSN |
| Lag | Bytes behind, time since last message, replay delay |
| Slots | Active state, `restart_lsn`, retained WAL, `safe_wal_size` |
| Archive | Archived/failed counts, last archived time |
| Storage | Data/WAL/archive free space |
| Workload | Connections, latency, errors, transactions/sec |
| Recovery | Last backup, restore tests, PITR coverage |
| HA manager | Leader, quorum, fencing, failover events |
| Application | Endpoint, pool errors, successful writes |
| Drill | Last switchover/failover, achieved RPO/RTO |

Every alert needs an owner and runbook action. For example: standby disconnected -> check network/receiver; retained WAL climbing -> inspect slots; replay lag climbing -> check I/O and recovery conflicts.

## 48. Stop Conditions During Drills

Halt the drill or abort promotion when:

- True primary state cannot be determined.
- Fencing is unverified.
- Multiple candidates exist and the newest WAL node cannot be identified.
- Standby lacks required WAL, slots, or archives.
- Disk/WAL capacity is insufficient.
- Backup/PITR is unavailable for a risky drill.
- HA manager state is ambiguous.
- Endpoints could still route writes to the old primary.
- Data consistency checks fail.
- The coordinator cannot bound RPO/data loss risk.

During a real production incident, you may have to choose the least harmful path to restore service; when doing so, explicitly document unknowns and a data reconciliation plan rather than pretending criteria were met.

## 49. Runbook: Primary Unreachable, Status Unknown

This is a dangerous scenario because a network partition can hide the primary from standbys while clients still write to it.

1. Check health from multiple independent network paths.
2. Inspect host/cloud control plane status.
3. Check application connections hitting the old primary.
4. Inspect HA manager quorum/lease state.
5. Fence the old primary.
6. Confirm fencing completion.
7. Select candidate and promote.
8. Block direct connections to the old node.
9. Open the new endpoint only after verification.
10. Keep the old node isolated until ready to rejoin.

Never treat a single failed ping as proof that a node is powered off.

## 50. Runbook: Standby Falling Behind

1. Inspect `pg_stat_wal_receiver`.
2. Check network connectivity and authentication.
3. Inspect `pg_stat_replication` on the primary.
4. Compare standby receive vs. replay LSN.
5. Check recovery conflicts and long-running standby queries.
6. Check replication slot `active` status and `restart_lsn`.
7. Inspect WAL archive health and `restore_command`.
8. Check disk/I/O saturation on both nodes.
9. Verify required WAL segments still exist.
10. If required WAL is lost, rebuild the standby with a fresh base backup per plan.

Never delete replication slots or `pg_wal` files manually to "fix" lag.

## 51. Runbook: Old Primary Rejoin Failed

1. Keep the old primary fenced.
2. Confirm the target cluster shut down cleanly.
3. Verify source/target timeline histories.
4. Check `data_checksums` or `wal_log_hints` prerequisite.
5. Check `full_page_writes`.
6. Confirm WAL from the divergence point onward is available.
7. Run `pg_rewind` per version documentation.
8. If prerequisites are missing, skip rewind and take a fresh base backup.
9. Verify `standby.signal`, `primary_conninfo`, and slot settings.
10. Start and verify `pg_stat_wal_receiver`.
11. Monitor replay lag.
12. Open read traffic only after recovery state stabilizes.

Never start an old primary in writable mode "just to check if any data is left."

## 52. Checklist: Before, During, and After Switchover

### Before

- [ ] Confirm primary/standby identities.
- [ ] Verify version and configuration compatibility.
- [ ] Standby streaming/replay healthy.
- [ ] Replication lag within bounds.
- [ ] WAL archive and slots healthy.
- [ ] Backup/PITR readiness verified.
- [ ] Application endpoint cutover plan ready.
- [ ] Fencing plan verified.
- [ ] Target RPO/RTO defined.
- [ ] Owner and incident commander assigned.

### During

- [ ] Stop new writes.
- [ ] Drain transactions (planned).
- [ ] Record target LSN.
- [ ] Wait for replay through target.
- [ ] Fence old primary.
- [ ] Promote strictly one standby.
- [ ] Verify `pg_is_in_recovery() = false`.
- [ ] Cut over endpoints.
- [ ] Open canary traffic.
- [ ] Record timeline and timestamps.

### After

- [ ] Application read/write smoke tests pass.
- [ ] Data markers and reconciliation verified.
- [ ] Roles, grants, and sequences verified.
- [ ] WAL archiving operational on new primary.
- [ ] Standby slots and receivers healthy.
- [ ] Old primary rewound or rebuilt.
- [ ] Replication lag within bounds.
- [ ] CDC/downstream consumers healthy.
- [ ] Backup/PITR verified.
- [ ] Actual RPO/RTO recorded.
- [ ] Evidence and sign-off completed.

## 53. Common Mistakes

1. **Promoting a standby before fencing the old primary**, causing split-brain.
2. **Treating DNS/VIP updates as fencing**, leaving the old primary open to direct writes.
3. **Picking a standby solely by hostname or reachability**, ignoring replay LSN.
4. **Assuming async replication provides zero data loss**, ignoring unshipped WAL.
5. **Enabling synchronous replication without accounting for commit blocking**, causing outages when a standby/network drops.
6. **Mismatching `application_name` and `synchronous_standby_names`**, preventing standbys from qualifying as sync.
7. **Forgetting abandoned replication slots**, filling up `pg_wal`.
8. **Setting `max_slot_wal_keep_size` too low**, invalidating slots before consumers catch up.
9. **Relying on `wal_keep_size` instead of slots/archiving**, failing to guarantee WAL retention.
10. **Running `pg_basebackup` into an active data directory**, corrupting the node.
11. **Ignoring `pg_basebackup` version/flag differences**, causing syntax or behavior errors.
12. **Missing `standby.signal` or `primary_conninfo`**, booting as an isolated primary or failing to connect upstream.
13. **Storing plaintext passwords in configs or logs**, exposing replication credentials.
14. **Reading `last_xact_replay_timestamp` during idle periods**, falsely reporting lag.
15. **Confusing LSN byte distance with lag seconds**, misreading units.
16. **Promoting multiple standbys**, creating competing primary candidates.
17. **Mixing manual promotion with Patroni/repmgr**, desynchronizing the HA state manager.
18. **Restarting the old primary post-failover as writable**, creating diverged writes.
19. **Running `pg_rewind` without prerequisites**, failing recovery.
20. **Delaying base-backup rebuild when rewind is ineligible**, prolonging degraded redundancy.
21. **Failing to recreate slots on the new primary**, stalling standbys or CDC.
22. **Failing to preserve archive timeline history**, breaking PITR chains.
23. **Updating endpoints while forgetting connection pools or workers**, leaving clients writing to the old node.
24. **Skipping sequence checks post-cutover**, hitting duplicate key errors.
25. **Skipping data reconciliation after async failover**, missing lost commits.
26. **Treating a physical standby as a backup**, unable to recover from logical deletions.
27. **Never testing network partitions**, testing only clean service stops.
28. **Never recording actual RPO/RTO**, leaving HA compliance unproven.

## 54. Practice Exercises with Answers

### Exercise 1. How do primary and standby differ?

**Answer:** The primary accepts writes and generates WAL; the standby receives/replays WAL and serves read-only queries when hot standby is enabled.

### Exercise 2. What does physical streaming replication transmit?

**Answer:** Cluster-wide physical WAL, not merely rows scoped to a logical publication.

### Exercise 3. What `wal_level` is required for physical replication?

**Answer:** `replica` is typically sufficient; `logical` also supports physical replication.

### Exercise 4. What attributes does a replication role need?

**Answer:** `LOGIN` and `REPLICATION`, alongside minimal required grants and network rules.

### Exercise 5. What does a `hostssl` rule in `pg_hba.conf` enforce?

**Answer:** Permits only SSL-encrypted connections matching the specified address, user, and database or replication target.

### Exercise 6. What is `pg_basebackup` used for?

**Answer:** Taking a consistent base backup from the primary to bootstrap a standby or create a physical backup.

### Exercise 7. What does the `-R` option of `pg_basebackup` do?

**Answer:** Creates `standby.signal` and writes recovery connection settings per version behavior.

### Exercise 8. What does `standby.signal` signify?

**Answer:** Directs modern PostgreSQL to start the data directory in standby/recovery mode.

### Exercise 9. What does a replication slot retain?

**Answer:** WAL segments required by a consumer and its replication progress state.

### Exercise 10. What does `pg_stat_replication` show?

**Answer:** WAL sender and connected standby states along with LSN and lag metrics on the primary.

### Exercise 11. What does `pg_stat_wal_receiver` show?

**Answer:** WAL receiver status and upstream connection details on the standby.

### Exercise 12. What does `pg_is_in_recovery()` returning `false` mean?

**Answer:** The node is no longer in recovery/standby mode and is acting as a writable PostgreSQL primary.

### Exercise 13. Can async replication lose data on failover?

**Answer:** Yes; the primary may have acknowledged commits not yet received or flushed by the standby.

### Exercise 14. What does synchronous replication improve?

**Answer:** Waits for standby WAL acknowledgment per commit policy, reducing the risk of losing acknowledged commits.

### Exercise 15. How does `synchronous_commit = remote_apply` differ from `on`?

**Answer:** `remote_apply` waits until the standby replays the transaction; `on` waits for remote WAL flush per synchronous replication semantics.

### Exercise 16. What is RPO?

**Answer:** The Recovery Point Objective—maximum tolerable data loss upon recovery.

### Exercise 17. What is RTO?

**Answer:** The Recovery Time Objective—maximum tolerable duration to restore service.

### Exercise 18. How does switchover differ from failover?

**Answer:** Switchover is planned and drains writes gracefully; failover is an emergency cutover when the primary becomes unavailable.

### Exercise 19. Why record a target LSN during switchover?

**Answer:** To prove the standby has replayed all required WAL prior to promotion.

### Exercise 20. Why is fencing mandatory during failover?

**Answer:** So the old primary cannot continue accepting writes and induce split-brain.

### Exercise 21. What is `pg_promote` used for?

**Answer:** Promoting a standby into a writable primary.

### Exercise 22. Does promotion create a new timeline?

**Answer:** Yes; PostgreSQL increments to a new timeline to record the new WAL branch.

### Exercise 23. Why recycle connection pools after endpoint cutover?

**Answer:** Existing pooled connections may stay connected to the old node despite DNS/VIP updates.

### Exercise 24. When is `pg_rewind` used?

**Answer:** To synchronize a diverged target cluster back onto the new source's timeline when common history and prerequisites exist.

### Exercise 25. What key prerequisites does `pg_rewind` require?

**Answer:** Clean shutdown of the target, common timeline history, `data_checksums` or `wal_log_hints` enabled prior to divergence, `full_page_writes`, and required WAL.

### Exercise 26. When should you use `pg_basebackup` instead of `pg_rewind`?

**Answer:** When prerequisites are missing, required WAL is gone, timelines do not match, or the target state is untrusted.

### Exercise 27. Does a physical standby replace backups?

**Answer:** No; logical errors such as accidental `DELETE`s replicate directly to the standby.

### Exercise 28. Why verify archiving after promotion?

**Answer:** The new primary must continue generating and archiving WAL to preserve PITR chains and downstream recovery.

### Exercise 29. What is split-brain?

**Answer:** Two nodes simultaneously acting as primary and accepting independent writes.

### Exercise 30. What outcomes must an HA drill record?

**Answer:** Actual RPO/RTO, timeline, replication lag, promotion duration, endpoint recovery, data verification checks, and discovered issues.

## 55. Official PostgreSQL Documentation

Consult documentation matching your deployed major version:

- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html) — streaming replication, standbys, and archive recovery.
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION) — primary/standby setup.
- [Log-Shipping Standby Servers](https://www.postgresql.org/docs/current/warm-standby.html#STANDBY-SERVER-OPERATION) — recovery and standby behavior.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — bootstrapping a physical standby.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html) — rejoining a diverged cluster.
- [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html) — starting, stopping, and promoting servers.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — WAL senders, slots, and synchronous standby settings.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — WAL behavior and durability.
- [Replication Monitoring](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_replication`, `pg_stat_wal_receiver`, and slots.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — `REPLICATION` role attribute.
- [pg_hba.conf](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html) — client authentication rules.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backups, WAL archives, and recovery.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — synchronous commit semantics.
- [Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — `recovery_target_timeline` and related settings.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html) — cluster identity and checkpoint metadata.

`/current/` URLs reflect the latest documentation. `pg_basebackup`/`pg_rewind` flags, failover slot support, view columns, configuration parameters, and HA manager behavior vary across PostgreSQL major versions and platforms. Always check docs for your exact version and HA manager before executing production failovers.

## 56. Summary

**Primary/standby forms true HA only when replication is monitored, promotion enforces fencing, and applications cut over safely.** Streaming replication keeps standbys close to the primary; WAL archives support catch-up and PITR; switchover and failover require distinct workflows.

1. **Bootstrap standbys from a consistent base backup.** Configure roles, HBA rules, WAL senders, slots, and standby recovery settings.
2. **Verify receive and replay progress.** Use `pg_stat_replication`, `pg_stat_wal_receiver`, and LSN metrics.
3. **Choose sync/async based on RPO/RTO.** Synchronous mode reduces risk of losing acknowledged commits while adding latency and availability coupling.
4. **Monitor slots, archives, and disk space.** Disconnected standbys or abandoned slots can fill `pg_wal` rapidly.
5. **Switchover drains writes and waits for target LSN.** It provides a controlled, graceful transition.
6. **Failover requires fencing before promotion.** Never open writes on a new node while the old primary can still accept writes.
7. **Promote strictly one candidate.** Verify `pg_is_in_recovery()` and timeline post-promotion.
8. **Switch endpoints and recycle connection pools.** Verify web services, workers, scheduled jobs, and integrations.
9. **Rejoin the old primary with `pg_rewind` when eligible.** Otherwise, rebuild cleanly with `pg_basebackup`.
10. **Audit slots and archiving on the new primary.** Recreate/reconfigure consumers per ownership and recovery policy.
11. **Physical standbys never replace backups/PITR.** Maintain restore tests and independent backups.
12. **Drill regularly and record actual RPO/RTO.** Observed drill measurements prove whether your HA design meets targets.

A successful HA drill means more than merely promoting a standby. It must prove two primaries never accept writes simultaneously, applications resume within RTO, data stays within committed RPO, and replication topology rebuilds cleanly afterward.
