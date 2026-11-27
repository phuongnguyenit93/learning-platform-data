# Asynchronous and Synchronous Replication in PostgreSQL

PostgreSQL can maintain one or more standby servers by streaming Write-Ahead Log (WAL) from the primary. The standby receives WAL, writes WAL to storage, and replays records to reproduce data state. This mechanism is called physical streaming replication when the standby receives the cluster's physical WAL stream.

The key difference between **asynchronous replication** and **synchronous replication** lies in when the primary confirms to the client that a transaction has committed. With async replication, the primary does not wait for a standby to acknowledge WAL before returning the commit result. With synchronous replication, the primary may wait for one or more standbys to reach the configured WAL acknowledgement level.

This difference directly affects write latency, continued availability when a standby disconnects, and the amount of data that could be lost during failover. Async generally optimizes latency and continuous write availability; synchronous can provide stronger guarantees for transactions acknowledged by standbys, at the cost of commits slowing down or blocking when too few synchronous standbys remain.

This lesson belongs to the **Physical Replication** chapter of the *Database Engine Relational PostgreSQL* module. We will cover the WAL path, `synchronous_commit` levels, standby selection with `synchronous_standby_names`, primary/standby configuration, monitoring, failover, and designing appropriate RPO/RTO.

> **Principle:** "Synchronous" describes the primary waiting for acknowledgement from a standby before confirming a commit. It does not automatically perform failover, does not replace backups, and does not protect against all simultaneous failures of primary, standby, storage, or network.

## 1. Learning objectives

After this lesson, you will be able to:

1. Describe the primary/standby architecture of physical streaming replication.
2. Explain how WAL is sent, written, and replayed.
3. Distinguish asynchronous and synchronous replication.
4. Understand the primary commit response in each mode.
5. Distinguish `synchronous_commit = off`, `local`, `remote_write`, `on`, and `remote_apply`.
6. Explain the role of `synchronous_standby_names`.
7. Distinguish priority-based `FIRST` and quorum-based `ANY`.
8. Configure `application_name` to identify synchronous standbys.
9. Create a physical replication role, `pg_hba` rule, and base backup.
10. Configure replication slots and understand WAL retention.
11. Monitor the primary using `pg_stat_replication`.
12. Monitor the standby using `pg_stat_wal_receiver` and replay functions.
13. Identify transactions waiting on `SyncRep`.
14. Understand latency, throughput, availability, and RPO trade-offs.
15. Distinguish received, written, flushed, and replayed LSNs.
16. Handle a disconnected synchronous standby.
17. Understand the limits of cascading replication and quorum.
18. Design safe failover, prevent split brain, and avoid promoting the wrong node.
19. Verify read-after-write when using `remote_apply`.
20. Build replication runbooks, labs, and operational checklists.

## 2. Physical streaming replication architecture

PostgreSQL uses WAL to record changes needed to recover the database after a crash. In physical replication, the primary transmits WAL records to the standby. The standby writes the records to WAL files and replays them onto the cluster's data files.

```text
                 Applications
                       |
                       v
                +-------------+
                |   Primary   |
                | transactions|
                +-------------+
                       |
                 WAL generation
                       |
                WAL sender process
                       |
              Streaming replication
                       |
             +---------+----------+
             |                    |
             v                    v
      +-------------+      +-------------+
      | Standby A   |      | Standby B   |
      | WAL receiver|      | WAL receiver|
      +-------------+      +-------------+
             |                    |
        WAL write/flush      WAL write/flush
             |                    |
          Replay                 Replay
             |                    |
       Read-only queries    Read-only queries
```

### 2.1. Primary

The primary accepts write operations, generates WAL records, and manages replication connections. WAL sender processes send WAL to directly connected standbys.

### 2.2. Standby

The standby runs in recovery mode, receives WAL via the WAL receiver, writes WAL to storage, and replays records. With `hot_standby = on`, clients can connect to run read-only queries while the standby continues replaying.

### 2.3. WAL sender and WAL receiver

- WAL sender runs on the primary and sends WAL.
- WAL receiver runs on the standby and receives WAL.
- Startup/receiver/replay processes coordinate to maintain recovery state.

### 2.4. Physical replication replicates at the cluster level

A physical standby reproduces the physical state of the cluster, including all databases in the cluster. It is not a per-table subscription like logical replication.

### 2.5. Same major version

Physical streaming replication generally requires the primary and standby to be compatible at the same PostgreSQL major version and physical format. It is not a standard method for replicating directly between two different major versions; use logical replication or an appropriate major upgrade procedure.

## 3. What stages does WAL pass through?

To understand synchronous replication, distinguish the WAL milestones:

1. **Generated:** primary generates WAL records for a transaction.
2. **Sent:** WAL sender sends records over the connection.
3. **Received:** standby receives records.
4. **Written:** standby writes WAL to the operating system.
5. **Flushed:** standby flushes WAL to storage per system durability semantics.
6. **Replayed:** standby applies WAL records to data files and advances the recovery position.

LSNs such as `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn` reflect these different positions.

### 3.1. LSN

Log Sequence Number (LSN) is a position in the WAL stream. You can compare LSNs to see how well a standby is keeping up.

Example on the primary:

```sql
SELECT pg_current_wal_lsn() AS primary_current_lsn;
```

On the standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
```

### 3.2. Received does not mean durable

The standby may have received bytes over the network without having written them to storage yet. If the standby crashes at that moment, bytes sitting only in memory/network buffers can be lost.

### 3.3. Written is not necessarily flushed

WAL has been written via an OS write call, yet may still reside in the page cache or storage cache before being flushed per durability requests.

### 3.4. Flushed does not mean replay is complete

WAL may already be durable on the standby while the recovery process has not yet applied the records. Read-only queries on the standby may not see that transaction yet.

### 3.5. Replay does not mean every client snapshot sees data immediately

Even after WAL is replayed, a read transaction using an older snapshot may not see the change. `remote_apply` ensures the standby has replayed up to the commit record before the primary returns commit, but the application still needs to open an appropriate read snapshot.

## 4. Asynchronous replication

In asynchronous mode, the primary does not wait for the standby to acknowledge WAL before completing a commit for the client.

Overview flow:

```text
Client             Primary               Standby
  |                   |                     |
  |--- COMMIT ------->|                     |
  |                   |-- write/flush WAL   |
  |<-- COMMIT OK -----|                     |
  |                   |---- send WAL ------>|
  |                   |                     |-- write/flush
  |                   |                     |-- replay
  |                   |                     |
```

### 4.1. Advantages

- Commit latency does not wait for a network round trip to the standby.
- The primary can continue accepting writes when a standby is slow or temporarily disconnected.
- Suitable for systems prioritizing write availability and accepting a data-loss window upon failover.
- Multiple standbys can receive WAL independently without commits waiting for all of them.

### 4.2. Disadvantages

- Standbys can lag behind the primary.
- The primary can report commit success while the standby has not yet received or flushed that WAL.
- If the primary fails abruptly and an un-caught-up standby is promoted, transactions already confirmed to clients may be absent on the new node.
- Read-after-write via a standby can return stale data.

### 4.3. Async does not mean WAL is not flushed on the primary

With `synchronous_commit = on` and no synchronous standby configured, the primary still waits for local WAL flush before returning commit. What is skipped is waiting for acknowledgement from a standby.

### 4.4. Async can still use replication slots

A replication slot can retain WAL so a lagging standby can still receive the needed WAL. Slots protect WAL retention; they do not turn async replication into synchronous replication and do not guarantee commits have reached the standby.

### 4.5. RPO of async

RPO depends on the amount of WAL the standby has not yet received/flushed at failover time and which standby is promoted. Small lag is not a zero-data-loss guarantee. If the business requires near-zero RPO, evaluate synchronous replication or another durability mechanism.

## 5. Synchronous replication

In synchronous replication, the primary waits for acknowledgement from the configured number of standbys before returning commit success to the client, provided the transaction uses a synchronous commit level requiring remote acknowledgement.

Overview flow:

```text
Client             Primary               Sync Standby
  |                   |                       |
  |--- COMMIT ------->|                       |
  |                   |-- write/flush WAL     |
  |                   |---- send WAL -------->|
  |                   |                       |-- receive
  |                   |                       |-- write/flush
  |                   |<--- acknowledgement --|
  |<-- COMMIT OK -----|                       |
```

### 5.1. Conditions for synchronous replication to work

Requires coordination:
- Primary has `synchronous_standby_names` identifying eligible standbys.
- Standby is streaming and has an `application_name` matching the configured name.
- Transaction uses a `synchronous_commit` level requiring remote acknowledgement.
- Standby reaches the corresponding acknowledgement level.

### 5.2. Synchronous does not mean waiting for every standby

You can configure the primary to wait for one standby or a quorum of multiple standbys. The count and selection method are configured via `FIRST` or `ANY`.

### 5.3. Synchronous commit affects response timing

A transaction may have already applied changes on the primary while the client has not yet received the COMMIT response because the primary is waiting for the standby. If the standby fails to respond, the backend can wait.

### 5.4. Synchronous replication does not automatically fail over

PostgreSQL streaming replication does not automatically elect/promote a standby just because the primary dies. An operational procedure or HA manager is needed to detect failure, fence the old primary, and promote the right standby.

### 5.5. Synchronous does not protect every transaction if sessions override it

A transaction can set `synchronous_commit = local` or `off`, bypassing the remote wait. Control role/database/session settings and applications so they do not inadvertently weaken durability policy.

## 6. Comparing asynchronous and synchronous

| Criterion | Asynchronous | Synchronous |
|---|---|---|
| Primary waits for standby before COMMIT response | No | Yes, per commit level and quorum |
| Commit latency | Lower | Can increase with network/storage/replay |
| Primary continues writes when standby disconnects | Typically yes | Can block if quorum is lost |
| Data loss when promoting standby | Can lose WAL not yet on standby | Can avoid losing acknowledged transactions if promoting the right node with suitable durability level |
| Read-after-write on standby | Can lag | `remote_apply` can ensure replay before response |
| Sync standby names configuration | Not required | Required |
| Fault tolerance | Focuses on availability | Trades availability for higher durability/consistency |
| Suitable for | Read replicas, DR with non-zero RPO | Workloads requiring stronger durability |

### 6.1. No single mode fits every workload

Choose based on requirements:
- RPO.
- RTO.
- Write latency budget.
- Network RTT.
- Storage flush latency.
- Number of standbys and failure domains.
- Failover operational capability.
- Tolerance for write outages.

### 6.2. Combining sync and async standbys

One primary can have synchronous standby candidates alongside other async replicas. Synchronous quorum applies only to standbys selected via `synchronous_standby_names`.

### 6.3. Do not look only at replica count

Three standbys sharing the same host/storage failure domain do not improve durability like three replicas in independent failure domains. Placement matters as much as count.

## 7. What does `synchronous_commit` control?

`synchronous_commit` is the setting determining how far the primary waits before confirming a transaction commit. It can be set at system, database, role, session, or transaction scope per PostgreSQL mechanisms.

Common values:

| Value | Primary waits for local WAL flush? | Waits for synchronous standby? | Remote milestone |
|---|---|---|---|
| `off` | Not required before response | No | Does not wait |
| `local` | Yes | No | Local flush only |
| `remote_write` | Yes | Yes | Standby wrote WAL to OS |
| `on` | Yes | Yes | Standby flushed WAL |
| `remote_apply` | Yes | Yes | Standby replayed WAL |

### 7.1. off

A transaction may be reported committed before its WAL record is flushed locally. If the primary OS crashes, some recently confirmed transactions can be lost. PostgreSQL still preserves database consistency via WAL recovery; the risk is losing recent commits within the durability window, not bypassing all consistency rules.

### 7.2. local

The primary waits for local WAL flush but does not wait for a standby. Choose this when you want local durability without remote synchronous waits.

### 7.3. remote_write

The primary waits for the synchronous standby to write WAL to the operating system. It can have lower latency than `on`, though WAL on the standby is not guaranteed to be flushed to durable storage yet. A standby OS crash or power loss can lose newly written but unflushed WAL.

### 7.4. on

The default value. The primary waits for local WAL flush and for the synchronous standby to flush WAL to durable storage per standby/storage stack semantics.

### 7.5. remote_apply

The primary waits for the synchronous standby to replay WAL records. This includes receiving WAL and processing up to the commit record. This value is useful when an application needs to read from a standby right after the primary returns commit, though it can raise latency due to replay queues and standby query conflicts.

### 7.6. No synchronous standby configured

If no synchronous standby is configured/selected, remote levels have no real standby to wait on; local WAL durability still depends on the setting. Thus `synchronous_commit = on` alone does not enable synchronous replication. You must also configure `synchronous_standby_names` and an eligible standby.

### 7.7. Setting for a single transaction

```sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';

UPDATE app.orders
SET status = 'PAID'
WHERE order_id = 1001;

COMMIT;
```

`SET LOCAL` applies only within the current transaction. Choose the right policy before executing transactions.

### 7.8. Setting per role or database

```sql
ALTER ROLE app_runtime
SET synchronous_commit = 'on';

ALTER DATABASE app_db
SET synchronous_commit = 'on';
```

Verify the effective setting inside an application connection:

```sql
SHOW synchronous_commit;
```

### 7.9. Different workloads can choose different levels

For instance, financial transactions may require remote flush, while reproducible jobs might accept local-only durability. Design policies around business semantics and audit overrides; do not let applications lower durability without oversight.

## 8. `synchronous_standby_names`

This setting resides on the primary and specifies which standbys are eligible to participate in synchronous replication.

Example:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

The primary prioritizes `standby_a`. If `standby_a` is unavailable, `standby_b` can be chosen as the synchronous standby via priority rules.

### 8.1. application_name must match

On the standby, `primary_conninfo` can specify:

```conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_a sslmode=verify-full'
```

The name `standby_a` must match the name in `synchronous_standby_names`.

### 8.2. Standby must connect directly and be in an eligible state

The primary selects among directly connected replication connections that meet the criteria. A downstream replica in a cascading chain does not appear as a direct connection to the root primary.

### 8.3. Do not confuse application_name with hostname

`application_name` is a label sent by the client in connection startup options. It can differ from the hostname, server name, or slot name.

### 8.4. List can be changed at runtime

Configuration changes require a reload per the parameter's context. Check `pg_settings`/`pg_file_settings` and `pg_stat_replication` status after reload. Do not assume an edited config file is already active.

## 9. Priority-based selection with FIRST

Syntax:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b, standby_c)'
```

### 9.1. FIRST 1

The primary picks the highest-priority eligible standby in the list. When a higher-priority standby is unavailable, the next standby can be selected.

### 9.2. FIRST 2

```conf
synchronous_standby_names = 'FIRST 2 (standby_a, standby_b, standby_c)'
```

The primary requires the two highest-priority standbys among eligible standbys. This is priority-based synchronous replication with multiple acknowledgements.

### 9.3. Potential synchronous standby

A standby may be a candidate/potential without currently being chosen as an active synchronous standby. Check `sync_state` and `sync_priority` in `pg_stat_replication`.

### 9.4. Advantages

- Easy to specify preferred standbys.
- Can prioritize replicas in the same region or storage class.
- Can use a secondary standby as fallback.

### 9.5. Trade-off

If the highest-priority standby is slow, it sits on the commit path and increases latency. Choose priorities based on topology, latency, and failure domains.

## 10. Quorum-based selection with ANY

Syntax:

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

The primary waits for any two standbys in the list to acknowledge at the configured commit level.

### 10.1. ANY 1

```conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
```

Any single standby in the list can satisfy the acknowledgement. This configuration allows selecting whichever node is fastest/available at runtime.

### 10.2. ANY 2

With three candidates, the primary needs acknowledgements from two nodes. If one node disconnects, the remaining two nodes can still satisfy the quorum. If only one node remains, commits requiring synchronous acknowledgement will wait.

### 10.3. Quorum does not mean every node is in sync

With `ANY 2` of three nodes, the third node can lag and not be part of that transaction's acknowledgement set. During failover, you must know which node actually received/flushed WAL for critical commits.

### 10.4. Choose quorum according to failure domains

If you need to tolerate one node failure while continuing commits, the candidate count and quorum must fit. However, two replicas in the same failure domain can fail together; place nodes in independent failure domains.

### 10.5. FIRST and ANY are not arbitrarily interchangeable

`FIRST` selects by priority order; `ANY` selects by quorum. Choose based on latency requirements, node preference, and fault tolerance.

## 11. At which milestone does the primary confirm synchronous commit?

Remote levels can be understood via WAL positions:

```text
Primary WAL
    |
    | send
    v
Standby receive buffer
    |
    | write
    v
Operating-system write cache
    |
    | flush
    v
Standby durable WAL
    |
    | replay
    v
Standby data files / recovery state
```

- `remote_write`: waits until the write step.
- `on`: waits until the flush step.
- `remote_apply`: waits until the replay step.

### 11.1. Storage semantics still matter

A flush request is only as trustworthy as the operating system, controller, device firmware, and storage service honoring durability semantics. Hardware with unprotected write caches or cloud storage misconfiguration can undermine durability assumptions.

### 11.2. Remote flush and local flush

With `on`, the primary must also ensure local WAL flush. Standby acknowledgement does not replace local WAL durability.

### 11.3. Remote apply for read-after-write

If a transaction commit returns after the standby finishes replaying, a new read transaction on that standby can see the commit, subject to snapshot semantics and routing to the acknowledging standby.

### 11.4. Commit acknowledgement is not application-level validation

Synchronous replication confirms WAL progress. It does not validate business constraints beyond what the transaction executed, does not confirm external side effects, and does not replace application-level idempotency.

## 12. Latency and throughput

Synchronous replication adds an acknowledgement dependency to the commit path. Latency is affected by:
- Network round-trip between primary and standby.
- Standby write/flush latency.
- Standby replay speed if using `remote_apply`.
- Quorum size and node placement.
- Queueing, WAL volume, and concurrent commits.
- Storage jitter, network congestion, and failover events.

### 12.1. A latency example

Suppose a local commit takes 2 ms, network round trip to the standby is 12 ms, and standby flush takes 4 ms. A synchronous commit needs at least the remote acknowledgement wait plus processing overhead; you cannot expect the 2 ms local latency alone.

This is an illustrative example, not a benchmark or an exact additive latency formula, since pipelining, batching, and concurrency affect actual results.

### 12.2. remote_write can reduce wait time

Remote write acknowledgement can be faster than remote flush on some storage stacks. However, durability on the standby is weaker against OS/power failures.

### 12.3. remote_apply typically incurs extra replay delay

If standby replay slows down due to CPU, I/O, or conflicts with read queries, primary commits can wait longer. Use it only when read visibility guarantees justify the cost.

### 12.4. Group commit

PostgreSQL can batch WAL flushes across multiple concurrent transactions. Synchronous replication still requires acknowledgements per policy, though each transaction does not necessarily cause an isolated network flush. Measure with realistic workloads rather than extrapolating from a single transaction.

### 12.5. Connection pools and long transactions

Synchronous replication impacts commit response times for write transactions. Connection pools may hold connections longer when a standby is slow; tune pool sizes, timeouts, and backpressure.

## 13. Availability and commit blocking

Synchronous replication trades some write availability for remote acknowledgement.

### 13.1. Too few synchronous standbys remaining

If `FIRST 1` has no available candidate or `ANY 2` has only one node left, transactions requiring synchronous acknowledgement can wait indefinitely until the situation changes or an operator intervenes.

### 13.2. This is intentional behavior

The primary cannot simultaneously guarantee quorum acknowledgement and ignore the quorum when it stops responding. Automatically continuing to commit would alter the durability contract.

### 13.3. A degradation procedure is needed

Runbooks should define:
- Waiting for the standby to return.
- Restoring network/storage.
- Switching to another standby.
- Reducing quorum per an approved decision.
- Switching specific transactions to local-only when business rules allow.

### 13.4. Do not silently switch to async without notice

Dropping the synchronous requirement means subsequent commits are no longer acknowledged by a standby before the client receives a response. This is an RPO change and must be recorded.

### 13.5. Read-only workloads can still operate

Synchronous commit waits primarily affect transactions committing WAL that requires acknowledgement. Read queries on primary/standby can continue if servers and routing remain healthy; DDL/writes depend on transaction behavior.

## 14. RPO, RTO, and data loss

**RPO (Recovery Point Objective)** is the maximum data loss acceptable to the business. **RTO (Recovery Time Objective)** is the maximum time allowed to restore service.

### 14.1. Async RPO

Async replication can have a non-zero RPO. When the primary fails before WAL reaches the promoted standby, commits already reported successful by the primary but missing on the standby can be lost from the new timeline.

### 14.2. Sync remote flush

If a transaction is confirmed after at least the required number of synchronous standbys have flushed WAL, and failover promotes a standby that acknowledged that transaction, confirmed commits can be preserved under the matching failure model.

### 14.3. Remote write has weaker durability

`remote_write` waits only for WAL to be written to the OS on the standby. If the standby loses OS/power before flushing, that WAL can be lost. Therefore do not treat `remote_write` as having the same durability guarantee as `on`.

### 14.4. Remote apply

`remote_apply` waits for replay and fits when immediate visibility on the standby is needed. Durability-wise, WAL is flushed before replay, while this level adds the apply condition to the commit response.

### 14.5. Never promise zero data loss in all scenarios

Even synchronous replication does not protect against:
- Simultaneous loss of the primary and all standbys holding acknowledged WAL.
- Storage stacks reporting flush success without true persistence.
- Promoting the wrong standby lacking sufficient WAL.
- Split brain or failed fencing.
- Replicated logical/application errors.
- Operators disabling sync policy or session overrides.
- Missing or unrecoverable backups/WAL archives.

## 15. Building a physical standby: prerequisites

Example topology:
- Primary: `db-primary`.
- Standby A: `db-standby-a`.
- Standby B: `db-standby-b`.
- Replication role: `replicator`.

### 15.1. Primary settings

Commonly required parameters:

```conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = '2GB'
```

`wal_keep_size` is a configured minimum amount of retained WAL, not a substitute for monitoring/slots. Choose a value based on WAL generation and expected outage duration.

### 15.2. Replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
```

Provide real credentials via a secret manager/password file; never commit real passwords in scripts.

### 15.3. pg_hba.conf

Example:

```conf
hostssl replication replicator 10.20.0.0/24 scram-sha-256
```

Allow only necessary standby addresses. Enforce TLS and network restrictions per security policy.

### 15.4. Restart or reload?

Some WAL sender/slot settings require a restart when changed; others can be reloaded. Check `pg_settings.context` and the documentation for your exact major version rather than assuming every parameter reloads.

### 15.5. Standby must be created from a valid base backup

A physical standby requires a consistent physical copy of the primary and the WAL needed to begin recovery. Use `pg_basebackup` or a compatible backup solution.

## 16. Creating a standby with pg_basebackup

Example creating a standby with a replication slot:

```bash
pg_basebackup \
  --host=db-primary \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/18/standby-a \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf \
  --create-slot \
  --slot=standby_a_slot
```

Option names have corresponding short forms in certain versions. Read `pg_basebackup --help` for the installed client tools.

### 16.1. write-recovery-conf / -R

This option creates `standby.signal` and writes appropriate connection/slot settings into `postgresql.auto.conf` on the target. In modern PostgreSQL, `standby.signal` marks the cluster to start in standby mode.

### 16.2. Replication slot

`--create-slot --slot=standby_a_slot` asks the primary to create a physical slot for the standby. The primary needs sufficient `max_replication_slots`.

### 16.3. Do not create duplicate slots

If the slot already exists, `--create-slot` cannot create a slot with the same name. You can create the slot manually beforehand and pass `--slot` without `--create-slot`; confirm the slot does not belong to another standby.

### 16.4. Protect credentials

Use a passfile or secret injection appropriate to the OS. Avoid recording passwords in shell history or process listings.

### 16.5. Starting the standby

After base backup, configure `hot_standby`/`primary_conninfo`/slot per policy, ensure port/data directory are right, then start the service. Check logs and `pg_is_in_recovery()`.

## 17. Configuring the standby connection

Example in `postgresql.auto.conf` or an included config:

```conf
primary_conninfo = 'host=db-primary port=5432 user=replicator application_name=standby_a sslmode=verify-full'
primary_slot_name = 'standby_a_slot'
hot_standby = on
```

### 17.1. application_name

Assign a unique, stable name to each standby. The primary uses this name to match `synchronous_standby_names`.

### 17.2. Slot name

The slot name is the identifier governing WAL retention. It does not have to match `application_name`, though matching names makes operations clearer.

### 17.3. Connection string

Needs host, port, user, TLS options, passfile/certificate, and environment-specific connection parameters. Do not hardcode passwords in config when a passfile/secret mechanism can be used.

### 17.4. Checking standby state

On the standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
```

`pg_is_in_recovery()` must return true when the server is in standby/recovery mode.

## 18. Enabling synchronous replication after standby streaming

Do not configure the primary to wait for a standby name before the standby is actually ready if the system is already serving writes.

A safe step-by-step rollout:
1. Create the replication role and `pg_hba` rule.
2. Run base backup and start the standby.
3. Confirm the standby is streaming.
4. Verify `application_name`.
5. Configure `synchronous_standby_names`.
6. Reload primary configuration.
7. Confirm `sync_state` changes to `sync`/`quorum`.
8. Test transaction commit latency and behavior when the standby disconnects.

### 18.1. FIRST 1 example

On the primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

### 18.2. Reload and verify

```sql
SELECT pg_reload_conf();

SHOW synchronous_standby_names;
SHOW synchronous_commit;
```

`pg_reload_conf()` returns whether the reload request was dispatched; still verify the effective settings and logs.

### 18.3. Confirming the standby was selected

```sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
```

For a `FIRST` configuration, the chosen standby will show a matching `sync_state` such as `sync`; other candidates may appear as `potential` or `async` depending on state/configuration.

### 18.4. When no matching standby exists

If synchronous standbys are configured yet no eligible standby matches, transactions requiring remote acknowledgement can wait. Check `application_name`, connection state, `pg_hba`, replication role, and WAL sender capacity.

## 19. FIRST and ANY in practical configurations

### 19.1. One preferred synchronous standby

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

Fits when `standby_a` has preferred latency/failure domain and `standby_b` serves as fallback.

### 19.2. Two synchronous standbys by priority

```conf
synchronous_standby_names = 'FIRST 2 (standby_a, standby_b, standby_c)'
```

Commits require acknowledgements from the two highest-priority standbys selected by priority.

### 19.3. Any one standby

```conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
```

The primary can wait for any one eligible node.

### 19.4. Any two standbys

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

Requires a quorum of two acknowledgements from the list.

### 19.5. Names must be unique

Assign a distinct `application_name` to each standby. If multiple connections share the same name, synchronous standby selection becomes ambiguous and harder to operate.

## 20. Monitoring on the primary

`pg_stat_replication` displays information about directly connected standbys.

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    sync_priority,
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

### 20.1. state

`state` may reflect startup, catchup, streaming, or related states. Under steady replication, `streaming` is expected.

### 20.2. sync_state

Possible values include:
- `async`: asynchronous standby.
- `potential`: candidate that could become synchronous.
- `sync`: synchronous standby selected under priority mode.
- `quorum`: standby participating in quorum mode.

Verify exact values and semantics against your running version.

### 20.3. sync_priority

Indicates priority related to synchronous selection. In quorum mode, do not interpret it as priority ordering like `FIRST`.

### 20.4. LSN gaps

Compare `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn` to measure gaps between send, write, flush, and replay. Use `pg_wal_lsn_diff()` to calculate bytes.

Example:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS send_to_write_bytes,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS write_to_flush_bytes,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS flush_to_replay_bytes
FROM pg_stat_replication
WHERE state = 'streaming';
```

Values can be NULL during certain states/moments; handle NULLs in monitoring.

### 20.5. Lag time fields

`write_lag`, `flush_lag`, and `replay_lag` are time indicators based on recent WAL activity. When workloads are idle or lag is zero, they may be NULL; do not use them alone to forecast catch-up duration.

## 21. Monitoring on the standby

`pg_stat_wal_receiver` displays the current receiver connection:

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

### 21.1. Receiver status

When streaming normally, `status` typically shows the receiver is streaming. If the view returns no rows, the standby has no active WAL receiver connection at query time.

### 21.2. Receive and replay

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

`receive_lsn` and `replay_lsn` differ when the standby has received WAL that it has not yet finished replaying.

### 21.3. Replay timestamp is not a perfect lag metric

If the primary is idle, the last transaction timestamp can look old even when the standby is completely caught up. Compare LSNs and receiver messages alongside primary/standby timestamps.

### 21.4. Standby conflicts

```sql
SELECT *
FROM pg_stat_database_conflicts;
```

This view provides information about query conflicts on a hot standby. Long-running queries can be canceled or delay replay depending on standby conflict settings.

## 22. Identifying transactions waiting on SyncRep

On the primary:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query
FROM pg_stat_activity
WHERE wait_event = 'SyncRep';
```

### 22.1. SyncRep wait

A backend waiting for synchronous replication acknowledgement can display wait event `SyncRep` with the related IPC wait event type.

### 22.2. Investigating the cause

Check:
- `synchronous_standby_names`.
- Transaction/session `synchronous_commit`.
- `pg_stat_replication` and `sync_state`.
- Network latency/loss.
- Standby write/flush/replay progress.
- Standby disk saturation.
- Standby recovery conflicts if using `remote_apply`.
- Replication slots and WAL sender errors.

### 22.3. Do not kill the first waiting transaction you see

The backend may be executing a critical transaction and waiting per durability policy. Identify the application, transaction age, commit stage, and business impact before canceling/terminating.

## 23. Replication slots and WAL retention

A physical replication slot retains WAL needed by a standby that has not yet received it. Slots prevent the primary from recycling WAL segments the standby still requires.

### 23.1. Creating a physical slot

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

Slots can also be created automatically via the corresponding `pg_basebackup` option.

### 23.2. Listing slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status
FROM pg_replication_slots
ORDER BY slot_name;
```

Some columns depend on major version; adjust the query for the target catalog.

### 23.3. A slot does not guarantee the standby is running

An inactive slot still retains WAL. If a standby disconnects for an extended period, `pg_wal` can grow until the filesystem fills up.

### 23.4. max_slot_wal_keep_size

This parameter caps how much WAL replication slots can retain per the PostgreSQL version's policy. When exceeded, the slot can reach `lost` WAL status, requiring intervention or rebuilding the standby.

### 23.5. wal_keep_size

Retains a configured minimum amount of WAL so a standby can catch up after a short outage. It does not guarantee WAL remains available for a long-offline standby.

### 23.6. Slots and synchronous acknowledgement are distinct features

- Slots retain required WAL.
- Synchronous commit determines whether the primary waits for acknowledgement before returning commit.
- A slot does not prove WAL has been flushed on the standby.
- Synchronous replication can use slots, but a slot alone does not make replication synchronous.

## 24. Hot standby and read queries

When `hot_standby = on`, the standby can serve read-only queries while replaying WAL.

### 24.1. Read scaling

Applications can route reporting/read-heavy queries to standbys to offload the primary. Account for read lag in async mode.

### 24.2. Read-after-write

If a transaction just committed on the primary and the application immediately reads from a standby, async mode may return stale data. Options:
- Read again from the primary.
- Wait for the standby to replay up to the transaction's LSN.
- Use `remote_apply` and route to the acknowledging standby.
- Use session consistency/routing policies.

### 24.3. remote_apply does not route the application automatically

The primary waits for the standby to replay, but the application still needs to connect to the right standby and open a fresh snapshot. If a load balancer routes to a different standby that has not replayed yet, stale reads can still occur.

### 24.4. Long-running standby queries

Long queries can conflict with WAL replay when replay must remove row versions or alter catalog state. Settings `max_standby_streaming_delay` and `hot_standby_feedback` govern the trade-off between query availability, replay lag, and primary bloat.

## 25. Synchronous replication and standby conflicts

With `remote_apply`, commit responses wait for standby replay. If standby replay is blocked by read queries or recovery conflicts, primary commits can slow down.

### 25.1. max_standby_streaming_delay

This parameter controls how long the standby can delay applying WAL to let conflicting queries finish before canceling them. Verify exact semantics for your version and workload.

### 25.2. hot_standby_feedback

Feedback helps the primary avoid vacuum cleanup that conflicts with standby queries, at the cost of holding back `xmin` and potentially causing bloat on the primary.

### 25.3. Do not set unbounded delays

If queries are never canceled, replay lag can grow and `remote_apply` commits can stall. Choose delays based on read SLAs and write commit SLAs.

### 25.4. Remote flush may fit better than remote_apply

If the goal is ensuring WAL is flushed on the standby without needing immediate read visibility, `synchronous_commit = on` avoids waiting for replay completion.

## 26. How network and storage affect synchronous replication

The synchronous commit path depends on the network and standby storage.

### 26.1. Network RTT

The primary must send WAL and receive acknowledgements. A standby in a distant region can substantially increase commit latency.

### 26.2. Network loss/jitter

Packet loss, congestion, or reconnects prevent the standby from keeping up. Synchronous transactions can wait until the connection stabilizes and quorum is satisfied.

### 26.3. Standby storage

High flush latency can slow down `on`. Provision storage suited to write latency and WAL workloads; measure `fsync`/flush behavior.

### 26.4. Shared failure domains

A primary and standby sharing a power domain, rack, storage array, or region can fail together. Synchronous acknowledgement does not replace topology design.

### 26.5. TLS

TLS protects confidentiality/integrity of the network connection; it does not guarantee standby storage durability or failover correctness.

## 27. Synchronous replication with multiple standbys

Example topology:

```text
Primary
  |
  +-- standby_a (region A)
  |
  +-- standby_b (region B)
  |
  +-- standby_c (region C)
```

### 27.1. FIRST 1

Selects one preferred standby. Simple, and latency can often be optimized by placing the preferred standby near the primary, though fallback behavior must be tested.

### 27.2. ANY 2

Waits for two of three standbys. Can tolerate one node outage and still commit as long as the remaining two nodes stay up and eligible.

### 27.3. Latency of quorum

Commit latency depends on acknowledgements from enough nodes to form quorum, not necessarily the slowest candidate overall. Still, network/storage conditions or scheduling can put a slower node in the quorum.

### 27.4. Which node to promote?

When the primary is lost, pick a standby that has received/flushed WAL for acknowledged commits. With quorum, not every standby necessarily holds all latest WAL; the failover manager must select the right node based on WAL state and topology.

### 27.5. Quorum size and availability

A larger quorum increases the number of acknowledged WAL copies but reduces commit availability when nodes fail. Design against your failure model, not merely a generic majority formula.

## 28. Cascading replication

In cascading replication, a standby can forward WAL to downstream standbys.

```text
Primary
   |
   +---- Standby A
              |
              +---- Standby A1
              |
              +---- Standby A2
```

### 28.1. Reducing connections on the primary

Cascading can reduce direct WAL sender connections and distribute replication load.

### 28.2. Cumulative downstream lag

WAL traverses multiple hops; downstream replicas can lag further behind than primary-connected standbys.

### 28.3. Synchronous acknowledgement applies to direct standbys

The primary sees only directly connected replication connections. It does not accept direct acknowledgements from A1/A2 through Standby A to count them toward the root primary's synchronous quorum.

### 28.4. Synchronous across tiers

Each tier requires clear sender/receiver relationships and configuration awareness. Do not assume a primary sync ack means the entire cascading tree has flushed or replayed.

## 29. Failover in async replication

When the primary fails, the operator/HA manager evaluates standbys and selects one to promote.

### 29.1. Data loss window

If the promoted standby had not received the primary's latest WAL, commits not yet transmitted can be lost from the new timeline.

### 29.2. Lag is not the only metric

Inspect LSN positions, WAL availability, receiver status, replay progress, and timeline. Timestamp lag can be misleading when workloads are idle.

### 29.3. Promote

A standby can be promoted via `pg_ctl promote` or SQL function `pg_promote()` per runbook. Execute only after confirming the old primary is fenced and the selected node is the right candidate.

### 29.4. Rejoining the old primary

The old primary cannot simply rejoin the new primary's timeline once diverged. Use `pg_rewind` when preconditions are met or rebuild from a base backup. Never start two writable primaries simultaneously.

## 30. Failover in synchronous replication

Synchronous replication helps preserve commits acknowledged by standbys meeting the synchronous policy, yet failover still requires sound decisions.

### 30.1. Promoting the right standby

- With `FIRST 1`, prioritize the active sync node that has WAL flushed up to acknowledged commits.
- With `ANY` quorum, determine which nodes in the quorum received/flushed the commits to preserve.
- Check LSNs and timelines before promotion.
- Avoid promoting a standby outside the acknowledgement set if a better node exists.

### 30.2. Fencing the old primary

If the old primary can still accept writes, split brain can occur. Use fencing/quorum/STONITH/network isolation or the equivalent HA platform mechanism.

### 30.3. Synchronous is not a consensus cluster manager

`synchronous_standby_names` does not elect a primary, fence nodes, manage VIPs/DNS, or guarantee a single writer on its own.

### 30.4. Rejoining and timelines

After promotion, the old node must follow the new timeline via rewind/rebuild. Check WAL availability and `wal_log_hints`/data checksum prerequisites if using `pg_rewind`.

## 31. When a synchronous standby disconnects

Suppose the configuration is:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a)'
```

If `standby_a` disconnects:
- Transactions with `synchronous_commit` requiring remote acknowledgement can wait.
- Transactions using `local` or `off` avoid the remote wait, with weaker durability policy.
- Read queries on the primary can still run.
- Reconnecting the standby can resume commit progress after catching up.

### 31.1. Check first

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

### 31.2. Check the WAL receiver

On the standby, inspect `pg_stat_wal_receiver`, PostgreSQL logs, network, DNS, credentials, `pg_hba`, and slot state.

### 31.3. Do not drop the slot just to free disk right away

The slot may hold WAL needed for the standby to catch up. Dropping it can force reinitializing/reseeding the standby. Evaluate WAL retention and recovery paths first.

### 31.4. Emergency degrade

If the business decides to resume writes without a synchronous standby, an operator can update sync policy per change/incident process. Record the timestamp, scope of transactions lacking remote acknowledgement, and the new RPO.

## 32. Changing synchronous policy safely

A change runbook can include:

1. Confirm reason and approver.
2. Check currently connected/streaming standbys.
3. Determine current `FIRST`/`ANY` quorum.
4. Identify transaction classes eligible for local commit.
5. Modify configuration or per-transaction settings in a controlled manner.
6. Reload if the parameter allows it.
7. Verify effective settings and `sync_state`.
8. Test commits and monitor wait events.
9. Record policy change time and restoration time.
10. Re-verify RPO after the incident.

### 32.1. Reducing quorum

Lowering `ANY 2` to `ANY 1` can unblock commits, while reducing standby acknowledgements. This is a durability change, not harmless tuning.

### 32.2. Switching to async

Removing synchronous standby requirements or using local commit restores write availability. Document that commits after that point lack the same guarantee.

### 32.3. Restoring sync

Once the standby is streaming, caught up, and healthy, restore quorum per config. Confirm `sync_state` before declaring the durability policy restored.

## 33. Synchronous replication and backups

Replication does not replace backups.

### 33.1. Logical errors are replicated

If an application accidentally `DELETE`s rows or a migration drops a table, valid WAL transmits that operation to the standby. Synchronous replication does not preserve pre-change history.

### 33.2. Corruption can be replicated

Certain data corruptions or destructive operations can propagate to replicas. Backups/PITR let you recover to a point before the mistake if WAL archives/retention suffice.

### 33.3. Independent backups

Maintain base backups, WAL archiving, retention, verification, and restore drills. Synchronous replication only improves commit durability per acknowledgement policy.

### 33.4. DR region

A distant sync standby increases latency and shares network/provider risk. You can pair a nearby synchronous standby with an async DR standby in another region; define distinct RPOs for each target.

## 34. Monitoring WAL generation and replication capacity

Metrics to track:
- WAL generation rate on the primary.
- Send/write/flush/replay LSN gaps.
- Standby connection state.
- Sync state/quorum availability.
- WAL sender count/capacity.
- Replication slot WAL retention.
- `pg_wal` filesystem free space.
- Network RTT/loss/throughput.
- Standby write/flush I/O latency.
- Replay lag and standby query conflicts.
- Primary backends waiting on `SyncRep`.
- Failover readiness and last restore drill.

### 34.1. max_wal_senders

Ensure enough WAL sender processes for standbys, base backups, and related replication clients. Too few can block new connections.

### 34.2. max_replication_slots

Ensure enough slots for planned consumers. Unused slots can still retain WAL; monitor inactive slots.

### 34.3. WAL disk capacity

A long-disconnected standby can cause WAL to accumulate. Alert before the filesystem fills; set appropriate slot retention limits and keep a reseed runbook.

### 34.4. Checkpoints and WAL load

Replication does not remove the need for checkpoint tuning. WAL generation, checkpoint frequency, and storage performance affect primary/standby I/O.

## 35. Monitoring replication lag in bytes

Example on the primary:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS replay_lag_bytes,
    pg_wal_lsn_diff(
        sent_lsn,
        write_lsn
    ) AS send_write_gap_bytes,
    pg_wal_lsn_diff(
        write_lsn,
        flush_lsn
    ) AS write_flush_gap_bytes,
    pg_wal_lsn_diff(
        flush_lsn,
        replay_lsn
    ) AS flush_replay_gap_bytes
FROM pg_stat_replication
WHERE state = 'streaming';
```

### 35.1. Byte lag must be paired with WAL rate

100 MB of lag may represent a few seconds or many minutes depending on the WAL generation rate. Track both bytes and WAL generation rate.

### 35.2. LSN positions can be NULL

During startup/catchup/disconnected states, some positions may be NULL. Monitoring must handle NULLs cleanly rather than treating NULL as zero lag.

### 35.3. Lag time and idle workloads

When there are no writes, timestamp-based lag may hold old values or NULL. Never alert from a single field without checking WAL activity.

## 36. Monitoring wait events and transaction latency

Query backends waiting on sync:

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE wait_event = 'SyncRep'
ORDER BY xact_start;
```

### 36.1. Measuring commit latency from the application side

DB views show wait events, yet application metrics are needed to measure end-to-end latency and separate pool waits, query execution, commit waits, and network response.

### 36.2. Correlate with standby flush

When commits slow down, correlate primary waiters with standby `flush_lsn`, storage latency, and network RTT. If using `remote_apply`, also inspect `replay_lsn` and standby conflicts.

### 36.3. Do not just increase timeouts

Raising application timeouts may reduce timeout errors without improving standby durability/latency. Find the real bottleneck.

## 37. Distinguishing replication lag and synchronous wait

An async standby can lag while primary commits remain fast because there is no wait. A sync standby may lag slightly, while primary commits wait only up to the required acknowledgement threshold.

### 37.1. FIRST 1

One standby is selected as `sync`. If another unchosen standby lags, its lag may not affect current commit acknowledgements.

### 37.2. ANY 2

The primary requires two acknowledgements. A third node can lag while commits still complete if the other two nodes qualify.

### 37.3. remote_apply

Replay lag on the synchronous standby directly impacts commit latency when using `remote_apply`.

### 37.4. remote_write/on

With `remote_write` or `on`, the primary waits for write/flush rather than standby replay. Replay can lag while commits are still acknowledged.

## 38. Synchronous replication and transaction isolation

Synchronous commit does not change transaction isolation levels. It controls when the `COMMIT` response returns based on WAL acknowledgement.

### 38.1. Read committed

A new transaction on the standby after a `remote_apply` acknowledgement can see the commit, since a fresh snapshot is taken after replay.

### 38.2. Repeatable read / serializable

A transaction that already opened a snapshot before WAL replay continues seeing its older snapshot. `remote_apply` does not refresh an existing snapshot.

### 38.3. Application routing

If an application uses a read pool, ensure post-commit reads route to the acknowledging standby or primary. Enabling `remote_apply` without a routing/session consistency policy is insufficient.

## 39. Synchronous replication and DDL

DDL is recorded in WAL and physical standbys replay the same changes. Synchronous acknowledgement applies to transactions containing DDL just like other transactions, per `synchronous_commit`.

### 39.1. Extension installation

`CREATE EXTENSION` modifies catalogs/objects and is WAL-replicated. However, the extension shared library must be installed/present on the standby's filesystem; WAL does not transfer binary packages.

### 39.2. Configuration changes

Edits to `postgresql.conf`, `pg_hba.conf`, certificates, preload libraries, or OS packages are not WAL-replicated like database DDL. Manage configuration consistently via automation/config management.

### 39.3. External files

Files outside the data directory or tablespaces are not covered by WAL replication unless handled separately. Provision them on the standby.

## 40. Synchronous replication and replication slots

Physical replication slots are commonly used to ensure WAL not yet received by a standby is not recycled.

### 40.1. Slots do not create synchronous mode

If `synchronous_standby_names` is empty, a standby using a slot is still async.

### 40.2. Synchronous does not require slots in every setup

A standby can stream without a slot, provided sufficient WAL retention via `wal_keep_size`/archive or another mechanism allows catching up after outages. Slots usually make retention easier to manage, with disk growth risk.

### 40.3. Slots and failover

After promotion, manage slots on the new primary and ensure remaining standbys have appropriate slot/connection settings. Do not assume slot state automatically transfers to the new node.

## 41. Checking timelines and recovery state

Standbys replay WAL along a timeline. When a standby is promoted, a new timeline is created. Nodes must follow the right history.

### 41.1. Timeline history

Timeline history files describe branching relationships between timelines. This is essential when a node rejoins after failover.

### 41.2. Promote once

Do not promote multiple standbys independently at the same time without fencing/leader election. Two writable nodes will diverge and cannot merge automatically.

### 41.3. pg_rewind

`pg_rewind` can bring an old primary's data directory onto the new timeline when prerequisites are met, such as data checksums or `wal_log_hints`, `full_page_writes`, and required WAL. Check documentation for your exact version before running.

### 41.4. When rewind is unsuitable

Rebuilding the standby from a base backup is cleaner if there is no common ancestor/required WAL or prerequisites are unmet.

## 42. Tuning primary_conninfo and timeouts

Parameters commonly reviewed:
- `wal_receiver_timeout`
- `wal_sender_timeout`
- `wal_receiver_status_interval`
- `wal_retrieve_retry_interval`
- `primary_conninfo`
- `primary_slot_name`

### 42.1. Timeout too short

Too-short timeouts can reset connections during normal network jitter, causing reconnect loops and synchronous commit waits.

### 42.2. Timeout too long

Too-long timeouts can delay failure detection. HA managers/network monitors may have their own health checks; align timeouts with your failure detection strategy.

### 42.3. SSL verification

Use `sslmode=verify-full` and certificate validation when appropriate. `sslmode=require` encrypts but does not verify hostname/identity to the same level.

## 43. Lab: building a physical async standby

Run on two separate PostgreSQL instances in a lab environment.

### 43.1. Primary configuration

```conf
wal_level = replica
max_wal_senders = 5
max_replication_slots = 5
hot_standby = on
```

### 43.2. Create the replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'lab-secret';
```

Use a lab secret and never reuse production passwords.

### 43.3. pg_hba.conf

```conf
host replication replicator 127.0.0.1/32 scram-sha-256
```

Adjust addresses/SSL according to how the two lab instances connect.

### 43.4. Base backup

```bash
pg_basebackup \
  -h 127.0.0.1 \
  -U replicator \
  -D /path/to/standby_data \
  -X stream \
  -P \
  -R
```

### 43.5. Start standby and verify

On the standby:

```sql
SELECT pg_is_in_recovery();
SELECT * FROM pg_stat_wal_receiver;
```

On the primary:

```sql
SELECT application_name, state, sync_state
FROM pg_stat_replication;
```

If `synchronous_standby_names` is empty, the standby normally shows as `async`.

## 44. Lab: observing async lag

On the primary, create a lab write workload:

```sql
CREATE TABLE IF NOT EXISTS public.replication_lab (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO public.replication_lab (payload)
SELECT repeat('x', 1000)
FROM generate_series(1, 10000);
```

Observe primary/standby LSNs:

```sql
SELECT pg_current_wal_lsn();
```

On the standby:

```sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
```

### 44.1. Generate controlled load

Never intentionally fill disks or kill processes on shared machines. If simulating lag, use bounded workloads in a disposable environment.

### 44.2. Reading LSN gaps

Compare receive/replay to see WAL received but not yet replayed. Increasing load can widen the gap if the standby cannot keep up.

## 45. Lab: enabling FIRST 1 synchronous standby

Ensure the standby has `application_name=standby_a` and is streaming. On the primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a)'
synchronous_commit = on
```

Reload:

```sql
SELECT pg_reload_conf();
```

Check:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority
FROM pg_stat_replication;
```

### 45.1. Test commit

From a primary session:

```sql
BEGIN;
INSERT INTO replication_lab(payload) VALUES ('sync-test');
COMMIT;
```

Observe commit response and standby replay state. Timings depend on lab network/storage.

### 45.2. Reading with remote_apply

Test a separate transaction with `SET LOCAL synchronous_commit='remote_apply'` and compare commit waits. Do not conclude from a single sample; measure multiple times.

## 46. Lab: standby disconnect and commit wait

In the lab only:
1. Confirm the `FIRST 1` standby is `sync`.
2. Open a session on the primary.
3. Stop/terminate the standby service in a controlled lab manner.
4. Run an insert/commit transaction with `synchronous_commit=on`.
5. Observe the session waiting on `SyncRep`.
6. Restart the standby and watch catch-up.
7. Confirm the commit proceeds once the standby responds.

### 46.1. Do not run on production

Simulating disconnects alters availability and can affect live transactions. Use only a disposable lab cluster.

### 46.2. Emergency policy

Try a separate session with `SET synchronous_commit = local` to observe commits not waiting on remote; then reset the setting. This illustrates a durability policy change, not a production recommendation.

## 47. Lab: ANY quorum

Use three standbys with distinct `application_name` values:
- `standby_a`
- `standby_b`
- `standby_c`

Primary config:

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

### 47.1. Observe sync_state

Check `pg_stat_replication`. Participating quorum nodes show `quorum`; other nodes may show `async`/`potential` depending on selection.

### 47.2. Losing one standby

In the lab, stop one node and confirm the remaining two nodes still satisfy quorum when eligible.

### 47.3. Losing two standbys

With only one node left, commits requiring `ANY 2` wait. Confirm via the `pg_stat_activity` wait event.

### 47.4. Do not infer failover solely from quorum

After primary loss, check each node's LSN and pick a candidate holding sufficient acknowledged WAL. Quorum configuration does not automatically promote.

## 48. Lab: verifying read-after-write

From the primary:
1. Insert a row with a unique key.
2. Commit with `synchronous_commit=on`.
3. Immediately read on an async standby and observe the row may not appear yet.
4. With a sync standby and `remote_apply`, commits wait for replay.
5. Open a new read transaction on the exact acknowledging standby and check for the row.

### 48.1. Snapshot semantics

If the read query runs inside a transaction opened before the commit, it may not see the row even if the standby replayed it. Start a fresh transaction/snapshot to test.

### 48.2. Routing semantics

If reading through a load balancer, identify which node actually received the query. Test against a specific standby to separate replay issues from routing.

## 49. Lab: measuring commit latency

Run a workload with many commits in the lab and record:
- Median/p95/p99 commit latency.
- Network RTT.
- Primary WAL flush latency.
- Standby write/flush latency.
- Standby replay delay.
- Wait event duration.
- Standby count/quorum.

Compare:
- Async with empty `synchronous_standby_names`.
- `FIRST 1` + `on`.
- `FIRST 1` + `remote_write`.
- `FIRST 1` + `remote_apply`.
- `ANY 2` if three standbys are available.

### 49.1. Controlled conditions

Keep workload, connection count, data volume, cache warmness, and storage constant. Document each run's configuration.

### 49.2. Do not optimize only for average

Commit tail latency often matters most. Inspect p95/p99 and the number of waiting transactions during network/storage jitter.

## 50. Lab: failover and rejoin in an isolated environment

A failover lab should:
1. Build a primary and at least one standby.
2. Generate writes and record LSNs.
3. Confirm standby catch-up.
4. Stop the primary in a controlled manner.
5. Fence the old primary in the lab.
6. Promote the standby.
7. Confirm `pg_is_in_recovery()` returns false on the new node.
8. Connect a test application.
9. Rejoin the old node via rewind/rebuild.
10. Inspect timeline and WAL.

### 50.1. Async and sync differ in data loss window

Run the same lab with async and sync. In async, if you intentionally promote a lagging node, you can observe missing final commits; in sync remote flush, promoting an acknowledging node preserves those commits within the lab's failure model.

### 50.2. Do not use kill -9 to simulate every failure

Hard kill, power loss, network partition, and storage failure are distinct failure models. Simulate each in a disposable environment and document the conditions.

## 51. Troubleshooting: commits hanging

Symptoms:
- Application commit timeouts.
- Backend `wait_event = SyncRep`.
- Primary still serves read queries while writes wait.
- `pg_stat_replication` lacks an eligible synchronous standby.

Check:
1. `SHOW synchronous_standby_names`.
2. `SHOW synchronous_commit`.
3. `pg_stat_replication`.
4. `pg_stat_activity` for `SyncRep`.
5. Standby logs/receiver status.
6. Network/TLS/`pg_hba`.
7. Disk flush/replay performance.
8. `FIRST`/`ANY` quorum availability.

Do not simply increase `statement_timeout`; commit waits can have separate semantics and timeouts depending on application/connection.

## 52. Troubleshooting: standby does not become sync

Causes:
- `application_name` mismatch.
- Standby not yet in `streaming` state.
- Standby connection rejected.
- Primary config not reloaded.
- A higher-priority `FIRST` standby is active.
- `ANY` quorum selection differs from expectation.
- Multiple connections sharing the same `application_name`.
- WAL sender/slot/connection limits.

Check effective configuration and `sync_state`, not just the config file on disk.

## 53. Troubleshooting: standby lag increasing

Possible causes:
- Network bandwidth/RTT.
- Slow standby disk write/flush.
- Replay CPU/I/O bottleneck.
- Long-running standby queries causing recovery conflicts.
- Large WAL burst.
- Slot/WAL retention or receiver reconnect loop.
- Standby storage nearly full.

Measure receive gap and replay gap separately. If receive keeps up while replay lags, focus on replay. If sent-to-write gap grows, focus on network/receiver/write.

## 54. Troubleshooting: primary WAL disk growing

Check:
- Inactive physical replication slots.
- Disconnected standbys.
- Old `restart_lsn`.
- `max_slot_wal_keep_size`.
- WAL archiving backlog.
- `wal_keep_size`.
- WAL generation rate.
- `pg_wal` filesystem free space.

Never manually delete WAL files inside `pg_wal`. Handle slots/standbys using SQL and proper PostgreSQL procedures.

## 55. Troubleshooting: standby replay is slow

Check:
- `pg_stat_wal_receiver`.
- `pg_last_wal_receive_lsn` and `pg_last_wal_replay_lsn`.
- CPU/storage I/O.
- Active standby queries and conflicts.
- `max_standby_streaming_delay`.
- `hot_standby_feedback`.
- WAL volume/checkpoint activity.

If using `remote_apply`, replay lag can raise commit latency. If using `on`, flush may already be caught up even while replay lags behind.

## 56. Troubleshooting: application reads stale data

Check:
- Whether the read query hit the primary or which standby.
- Whether the standby is streaming.
- Replay LSN compared to commit LSN.
- When the transaction snapshot was opened.
- Whether the load balancer routed to another lagging node.
- Whether the commit used `remote_apply` or only `on`.
- Whether the application has a read-your-writes policy.

Do not just add a fixed sleep after commit; use LSN/session consistency when accuracy is required.

## 57. Troubleshooting: failover may lose acknowledged commits

If using synchronous replication yet commits appear lost after failover:
- Determine the synchronous policy at transaction time.
- Check session/role/database overrides of `synchronous_commit`.
- Identify which standby was actually selected/acknowledged.
- Check `sync_state` and LSN positions.
- Check whether the promoted node was inside the acknowledgement set.
- Verify standby storage durability and the failure sequence.
- Check for split brain/old primary writes.

Synchronous mode cannot protect you if an operator promotes the wrong node or policy was downgraded prior to commit.

## 58. Common misconceptions

### 58.1. "Having two standbys means synchronous"

False. If `synchronous_standby_names` is empty, all standbys can be async.

### 58.2. "synchronous_commit=on automatically enables synchronous replication"

False. It requires a configured and connected synchronous standby to wait for remote acknowledgement. Without a synchronous standby, local flush remains the primary action.

### 58.3. "remote_write is the same as remote_flush"

False. `remote_write` waits only for OS write; `on` waits for the standby to flush WAL.

### 58.4. "remote_apply is just a faster remote_flush"

False. `remote_apply` also waits for the standby to replay WAL, which can be affected by replay backlogs and recovery conflicts.

### 58.5. "Synchronous replication never loses data"

False. It depends on the promoted node, acknowledgement count, flush semantics, storage, fencing, and failure model.

### 58.6. "A replication slot guarantees commits are already on the standby"

False. Slots retain WAL so the standby can receive it; they do not prove WAL has been received/flushed/replayed.

### 58.7. "Standby streaming means everything is replayed"

False. The `streaming` state only means the receiver is streaming; receive/write/flush/replay LSNs can still differ.

### 58.8. "Quorum ANY 2 means all three replicas have the transaction"

False. Only two acknowledgements are needed to satisfy quorum; the remaining replica may lag.

### 58.9. "Sync ack equals automatic failover"

False. You still need an HA manager, fencing, leader election, and routing.

### 58.10. "Reading after commit on any standby always sees the data"

False. Only `remote_apply` against the acknowledging standby supports the replay condition; routing and snapshots still matter.

## 59. Comparing FIRST and ANY

| Criterion | FIRST | ANY |
|---|---|---|
| Standby selection | By priority order | Any up to required count |
| Configuration | `FIRST n (...)` | `ANY n (...)` |
| Latency | Can depend on preferred node | Can use acknowledgements from faster nodes |
| Fallback | Next node when preferred node unavailable | Any eligible candidate |
| Monitoring | `sync`/`potential`/priority | `quorum` state and count |
| Suitable for | Clear preferred standbys | Quorum/failure-domain design |

## 60. Selection guide by requirement

| Requirement | Consideration |
|---|---|
| Low write latency, non-zero RPO accepted | Async |
| Local durability, no standby wait | `synchronous_commit=local` |
| Wait for standby OS write | `remote_write` |
| Wait for standby WAL flush | `on` |
| Require standby replay before commit response | `remote_apply` |
| One preferred standby + fallback | `FIRST 1` |
| Any 2 of 3 replicas | `ANY 2` |
| DR in distant region, low primary latency | Nearby sync primary standby, remote async DR |
| Read-after-write on standby | `remote_apply` + routing/snapshot policy |

All choices should be tested on a realistic topology and compared against business RPO/RTO.

## 61. Design checklist

1. Do primary/standby share the same major version and physical compatibility?
2. Are WAL level and WAL sender capacity properly sized?
3. Does the replication role have least-privilege `REPLICATION`/`LOGIN`?
4. Does `pg_hba` allow only necessary standby hosts?
5. Have TLS/authentication been verified?
6. Is the base backup consistent and does the standby start cleanly?
7. Is `application_name` unique and matching `synchronous_standby_names`?
8. Are replication slots managed and monitored?
9. Is WAL retention sized for outage/reseed strategy?
10. Does `FIRST` or `ANY` fit the failure model?
11. Does quorum size tolerate the desired number of node failures?
12. Are nodes placed in independent failure domains?
13. Does the `synchronous_commit` level match durability/read visibility needs?
14. Are network RTT and standby flush latency within SLA?
15. Is `remote_apply` required or is remote flush sufficient?
16. Has commit wait behavior during standby disconnect been tested?
17. Does emergency async/local policy have approval and auditing?
18. Does the failover manager implement fencing/split-brain prevention?
19. Is promote candidate selection based on LSN/timeline?
20. Does the old primary have a rewind/rebuild runbook?
21. Does read routing ensure read-after-write if needed?
22. Are backups/WAL archives independent from replication?
23. Are alerts set for `SyncRep` waits, lag, slots, and `pg_wal` capacity?
24. Are restore/failover drills executed periodically?

## 62. Daily operations checklist

- Inspect `pg_stat_replication` on the primary.
- Inspect `state` and `sync_state` of each standby.
- Inspect receive/write/flush/replay LSN gaps.
- Inspect `pg_stat_wal_receiver` on standbys.
- Check backends waiting on `SyncRep`.
- Check inactive replication slots and retained WAL.
- Check `PGDATA`/`pg_wal` filesystem capacity.
- Check network RTT/loss.
- Check standby storage latency and replay throughput.
- Check recovery conflicts and standby query cancellations.
- Confirm sync quorum is intact before reporting durability policy healthy.
- Check backup/WAL archiving and restore status.
- Record config/commit policy changes.
- Verify failover readiness on schedule.

## 63. Quick reference table

| Need | Command/setting |
|---|---|
| Enable physical WAL | `wal_level = replica` |
| Select synchronous standbys | `synchronous_standby_names` |
| Wait for local flush + remote flush | `synchronous_commit = on` |
| Wait for remote OS write | `synchronous_commit = remote_write` |
| Wait for remote replay | `synchronous_commit = remote_apply` |
| Wait for local flush only | `synchronous_commit = local` |
| Do not wait for local flush | `synchronous_commit = off` |
| Priority selection | `FIRST 1 (standby_a, standby_b)` |
| Quorum selection | `ANY 2 (standby_a, standby_b, standby_c)` |
| Set standby identity | `application_name=standby_a` |
| Create physical slot | `pg_create_physical_replication_slot()` |
| Base backup | `pg_basebackup -R` |
| View standbys | `pg_stat_replication` |
| View receiver | `pg_stat_wal_receiver` |
| View primary LSN | `pg_current_wal_lsn()` |
| View standby receive | `pg_last_wal_receive_lsn()` |
| View standby replay | `pg_last_wal_replay_lsn()` |
| Compute LSN gap | `pg_wal_lsn_diff()` |
| View SyncRep waiters | `pg_stat_activity WHERE wait_event='SyncRep'` |
| View slots | `pg_replication_slots` |
| Promote standby | `pg_ctl promote` / `pg_promote()` per runbook |
| Check recovery state | `pg_is_in_recovery()` |

## 64. Official reference documentation

- [PostgreSQL 18 — Warm Standby](https://www.postgresql.org/docs/18/warm-standby.html): streaming replication and standby operation.
- [PostgreSQL 18 — Synchronous Replication](https://www.postgresql.org/docs/18/warm-standby.html#SYNCHRONOUS-REPLICATION): synchronous acknowledgement, FIRST/ANY, and commit levels.
- [PostgreSQL 18 — Streaming Replication Protocol](https://www.postgresql.org/docs/18/protocol-replication.html): replication protocol.
- [PostgreSQL 18 — pg_basebackup](https://www.postgresql.org/docs/18/app-pgbasebackup.html): creating base backups/standbys.
- [PostgreSQL 18 — Replication Configuration](https://www.postgresql.org/docs/18/runtime-config-replication.html): WAL sender, slots, synchronous standby settings.
- [PostgreSQL 18 — Replication Statistics](https://www.postgresql.org/docs/18/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW): replication monitoring views.
- [PostgreSQL 18 — WAL Configuration](https://www.postgresql.org/docs/18/runtime-config-wal.html): WAL durability and checkpoint configuration.
- [PostgreSQL 18 — High Availability, Load Balancing, and Replication](https://www.postgresql.org/docs/18/high-availability.html): HA and replication overview.
- [PostgreSQL 18 — pg_rewind](https://www.postgresql.org/docs/18/app-pgrewind.html): rejoining a former primary after timeline divergence.

Some parameters, catalog columns, and tooling options can differ across major versions. Always consult the manual matching your exact source and target version before changing production configuration.

## 65. Summary

Asynchronous and synchronous physical replication both transmit WAL from primary to standby. The difference lies in whether the primary waits for standby acknowledgement before confirming a commit, and whether acknowledgement stops at write, flush, or replay.

1. **Async:** the primary does not wait for the standby. Commit latency is lower and write availability is higher, though promoting a lagging standby can lose transactions already confirmed to clients.
2. **Sync:** the primary waits for the configured number of standbys. It can protect acknowledged commits if failover promotes the right node and storage/fencing satisfy assumptions.
3. **Commit levels:** `remote_write` waits for OS write; `on` waits for remote WAL flush; `remote_apply` waits for replay. `local` waits only for local flush; `off` may return commit before local flush.
4. **Selection:** `FIRST` picks by priority; `ANY` picks any quorum. Quorum size affects both durability and write availability during node failures.
5. **Monitoring:** distinguish sent/write/flush/replay LSNs; inspect `pg_stat_replication`, `pg_stat_wal_receiver`, replication slots, and `SyncRep` wait events.
6. **Availability:** insufficient synchronous quorum can cause commits to wait. Lowering quorum/switching to async changes RPO and requires an incident policy.
7. **Failover:** PostgreSQL does not automatically elect/promote/fence a primary. You must select the right standby, prevent split brain, and manage timelines/rejoin.
8. **Backups:** replication does not replace backups, WAL archiving, PITR, verification, or restore drills.

Good design starts from what the business needs to guarantee: must a commit exist on another node, be durable on separate storage, or be immediately readable on a standby? Choose the acknowledgement level and quorum based on that answer, then validate latency, failure behavior, and failover through controlled tests.
