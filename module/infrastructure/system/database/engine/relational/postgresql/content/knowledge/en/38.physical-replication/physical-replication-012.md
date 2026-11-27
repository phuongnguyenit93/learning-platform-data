# Checking disconnects, WAL catch-up, and standby reinitialization in PostgreSQL

Physical streaming replication enables a PostgreSQL standby to receive WAL from the primary and replay changes to maintain a physical copy of the cluster. When the connection is interrupted, the standby can resume from its received WAL position if the segments are still retained on the primary or available in the WAL archive. If required WAL has already been recycled, or the standby is on a different timeline, simply reconnecting is not enough: you must evaluate fetching WAL from the archive, using `pg_rewind` when two branches have diverged, or rebuilding the standby with a new base backup.

Troubleshooting must answer three questions in order:

1. **Is the connection working?** Does the primary have a WAL sender, does the standby have a WAL receiver, and are authentication and networking clear?
2. **Which WAL is the standby missing and where is that WAL?** Distinguish sent, written, flushed, and replayed WAL; check primary retention, replication slots, and archives.
3. **Is the standby still on the same WAL history?** If on the same timeline and sufficient WAL remains, it can catch up. If WAL is missing or timelines diverged, choose the appropriate recovery path.

```text
Primary
  |  WAL sender
  |---------------------------> Standby
                                WAL receiver
                                    |
                                    v
                              pg_wal on standby
                                    |
                                    v
                              Startup / redo
                                    |
                                    v
                              Replay into data pages

Connection lost:
  1. Diagnose network, auth, processes, and configuration
  2. Locate missing WAL on primary or in archive
  3. If same timeline and enough WAL: reconnect + catch-up
  4. If divergence: pg_rewind (when eligible)
  5. If WAL missing or rewind unsuitable: new base backup
```

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Physical Replication** chapter, covering **"Checking disconnects, WAL catch-up, and standby reinitialization"**. Topics include replication diagnostics, reading LSNs, handling retention, reconnecting, catch-up, distinguishing WAL gaps from timeline divergence, reinitializing a standby, verification, and operational runbooks.

---

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain the roles of the WAL sender and WAL receiver in physical streaming replication.
2. Recognize streaming, catchup, and disconnected states.
3. Inspect replication from the primary using `pg_stat_replication`.
4. Inspect the WAL receiver from the standby using `pg_stat_wal_receiver`.
5. Distinguish sent, write, flush, and replay LSNs.
6. Measure missing WAL distance using `pg_wal_lsn_diff` when two positions share history.
7. Distinguish network lag, receive lag, and replay lag.
8. Identify when a standby has received WAL without yet replaying it.
9. Investigate DNS, routing, firewall, TLS, `pg_hba.conf`, and replication credential errors.
10. Check `primary_conninfo`, replication role, `max_wal_senders`, and replication slots.
11. Explain `wal_keep_size` and its limitations.
12. Understand how replication slots retain WAL and the risk of disk exhaustion.
13. Recognize when a slot has lost the ability to catch up due to WAL recycling.
14. Use WAL archiving and `restore_command` to supply missing segments.
15. Understand timeout and retry parameters related to WAL streaming.
16. Determine whether a standby is still on the same timeline as the primary.
17. Distinguish reconnect/catch-up from timeline rewind.
18. State the preconditions and limitations of `pg_rewind`.
19. Reinitialize a standby using `pg_basebackup` following a safe procedure.
20. Configure replication slots and connections after rebuilding.
21. Monitor catch-up progress until replay stabilizes.
22. Verify consistency at the data and application levels.
23. Design retention, capacity alerts, and backups to reduce reinitialization risk.
24. Build runbooks for offline standbys, WAL gaps, divergence, and rebuilds.

**Scope:** Modern PostgreSQL, particularly PostgreSQL 12 and later. Column names in some system views and capabilities of parameters/tools can vary by major version. Commands that affect a data directory or server role should only be run per runbook on the right node.

---

## 2. How does physical streaming replication work?

In physical replication, the primary sends a WAL stream to the standby. The standby saves received WAL into its WAL area, and the startup process replays records to update data pages.

### 2.1. On the primary

- Write transactions generate WAL records.
- WAL is written and flushed per durability policy.
- WAL sender processes send WAL to connected standbys.
- Replication slots, `wal_keep_size`, and archive policies can affect how long WAL remains available.

### 2.2. On the standby

- The WAL receiver connects to the primary via the replication protocol.
- The WAL receiver receives and writes WAL into `pg_wal`.
- The startup process replays WAL onto data pages.
- The standby can serve read-only queries if `hot_standby` is enabled.

### 2.3. Receiving WAL differs from replaying WAL

A standby may have received and flushed a WAL segment without yet having replayed to the end of that segment. In that case, WAL already resides on the standby, yet the corresponding changes are not necessarily visible to queries.

### 2.4. A physical standby does not re-run SQL

The standby replays WAL records at the storage/internal operation level. It does not re-execute the original `UPDATE` or `INSERT` statements from the application.

### 2.5. One primary can have multiple standbys

A primary can stream WAL to multiple standbys directly. A standby can also act as upstream for another standby in cascading replication.

### 2.6. Streaming replication does not replace backups

An accidental `DELETE` or logical error is replicated to the standby. Base backups and WAL archives are still needed to recover to a point before the mistake.

---

## 3. Components to check when disconnected

When a standby stops keeping up, the issue can span multiple layers:

| Component | Role | Symptoms when failing |
| --- | --- | --- |
| Primary PostgreSQL | Generates and serves WAL | Server down, no WAL sender spawned |
| WAL sender | Sends WAL to standby | No replication session |
| Network | Transmits WAL stream | Timeouts, resets, packet loss |
| DNS/routing | Locates and routes to primary | Host resolution failure, wrong route |
| Firewall/security group | Permits TCP connections | Connection refused/timeout |
| TLS | Protects connections | Certificate/hostname/CA errors |
| `pg_hba.conf` | Authenticates replication connections | No `pg_hba.conf` entry, authentication failed |
| Replication role | Permits replication login | Permission denied |
| WAL receiver | Receives stream on standby | No receiver or receiver reconnecting repeatedly |
| Replication slot | Retains WAL needed by consumer | WAL retained, disk growing or slot invalid |
| WAL archive | Supplies older segments | Restore command failure, missing segment |
| Standby storage | Writes WAL and data pages | Slow I/O, disk full, read-only filesystem |
| Startup/replay | Applies WAL | Receive advances while replay lags |
| Timeline history | Selects the right WAL branch | Standby fails to follow branch after promotion |

Do not conclude replication is broken from a single lag metric. Read status on both primary and standby along with logs from both sides.

---

## 4. Quick status checks on the primary

### 4.1. List connected standbys

On the primary:

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
    reply_time
FROM pg_catalog.pg_stat_replication;
```

This view shows standbys connected directly to the current primary. It does not automatically list standbys sitting behind a cascading standby.

### 4.2. Meaning of state

Common states include:

- `startup`: standby is establishing the replication connection.
- `catchup`: standby is catching up on WAL before entering streaming state.
- `streaming`: WAL is being sent continuously.
- `backup`: connection is serving a backup operation.
- `stopping`: WAL sender is shutting down.

States and their exact set of values can vary by version. Consult the documentation for your cluster's major version.

### 4.3. No rows in pg_stat_replication

No rows usually means the primary has no active direct standby connection at query time. That alone does not prove the standby's data directory is corrupted.

Check further:

- Is the standby running?
- Is the WAL receiver attempting to reconnect?
- Does `primary_conninfo` have the right host/port/user?
- Are network and TLS reachable?
- Does the replication role have `LOGIN`/`REPLICATION`?
- Does `pg_hba.conf` have an appropriate rule?
- Does the primary have enough `max_wal_senders`?
- Do logs show authentication, timeout, or missing WAL errors?

### 4.4. Inspect WAL sender processes

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

### 4.5. Count replication connections

```sql
SELECT count(*) AS active_standby_connections
FROM pg_catalog.pg_stat_replication;
```

Compare against the expected number of standbys. With a cascading topology, inspect each corresponding upstream.

---

## 5. Status checks on the standby

### 5.1. Is the server in recovery?

```sql
SELECT pg_is_in_recovery();
```

- `true`: server is in recovery, typically a standby or archive recovery.
- `false`: server is no longer in recovery and may be operating as a primary.

Never promote a server simply because the WAL receiver lost its connection. A lost connection is not proof that the primary is dead.

### 5.2. Check the WAL receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

This view provides receiver status, sender host/port, slot name, LSNs, and message receipt times depending on version. On a streaming standby, one row normally appears.

If no row appears, the receiver may not have started, has stopped, or cannot establish a connection. Read logs and configuration.

### 5.3. Check receive/replay LSN

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

- `receive_lsn`: last WAL position received and synced to storage via streaming.
- `replay_lsn`: last WAL position replayed.
- `last_replay_time`: timestamp of the last replayed transaction.

These functions may return NULL when no suitable WAL has been received/replayed in the current recovery session.

### 5.4. Receive LSN advances while replay LSN stalls

The standby is receiving WAL, yet startup/replay is not keeping up. Investigate:

- Standby CPU and I/O.
- Disk latency and free space.
- Recovery conflicts from read queries.
- Whether replay is paused.
- Whether `recovery_min_apply_delay` is intentionally configured.
- PostgreSQL logs for page/WAL errors.

### 5.5. Both receive and replay LSNs stall

The receiver may have lost its connection, the primary may not be generating new WAL, the network may have failed, or the receiver may be waiting on archive/retry. Cross-check primary LSN and WAL receiver status.

### 5.6. An old replay timestamp alone does not prove failure

If the primary has no new transactions, `last_replay_time` can stay old even though the standby is completely in sync. Evaluate using LSNs and workload activity together.

---

## 6. Distinguishing sent, write, flush, and replay

On the primary, the LSNs in `pg_stat_replication` represent distinct stages:

| Field | Meaning |
| --- | --- |
| `sent_lsn` | WAL position primary has sent to standby |
| `write_lsn` | WAL position standby reports written |
| `flush_lsn` | WAL position standby reports flushed to storage |
| `replay_lsn` | WAL position standby has replayed |

Flow:

```text
Primary WAL position
        |
        v
     sent_lsn
        |
        v
     write_lsn
        |
        v
     flush_lsn
        |
        v
     replay_lsn
```

### 6.1. Sent lag

If primary current LSN advances faster than `sent_lsn`, the WAL sender/network path has not finished transmitting data.

### 6.2. Write lag

If `sent_lsn` advances while `write_lsn` lags, the standby may be receiving/writing slowly or the network has issues.

### 6.3. Flush lag

If `write_lsn` advances while `flush_lsn` lags, standby storage flush may be the bottleneck.

### 6.4. Replay lag

If `flush_lsn` advances while `replay_lsn` lags, the standby has saved WAL yet has not finished applying it.

### 6.5. Never infer root cause from a single gap

LSN gaps locate which stage is slow. Combine logs, OS metrics, query load, and disk latency to pinpoint the root cause.

---

## 7. Measuring missing WAL bytes

On the primary, compare current WAL LSN against standby positions:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        sent_lsn
    ) AS unsent_bytes,
    pg_wal_lsn_diff(
        sent_lsn,
        write_lsn
    ) AS sent_not_written_bytes,
    pg_wal_lsn_diff(
        write_lsn,
        flush_lsn
    ) AS written_not_flushed_bytes,
    pg_wal_lsn_diff(
        flush_lsn,
        replay_lsn
    ) AS flushed_not_replayed_bytes
FROM pg_catalog.pg_stat_replication;
```

These subtractions are valid only when the LSNs belong to the same cluster and compatible WAL history. After failover or timeline divergence, never subtract LSNs across two branches as if they formed a single continuous stream.

### 7.1. Measure total distance to replay

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind_replay
FROM pg_catalog.pg_stat_replication;
```

### 7.2. LSN distance is bytes, not seconds

If the primary generates 100 MB of WAL per minute, a 500 MB backlog means something very different than on a workload generating 1 MB per minute. Estimating catch-up time requires measuring WAL generation rate and replay throughput.

### 7.3. LSN does not replace timeline ID

Record TLI alongside LSN. After promotion, a similar LSN can belong to a different WAL branch.

---

## 8. Lag columns and interpretation limits

`pg_stat_replication` can provide `write_lag`, `flush_lag`, and `replay_lag` on modern versions.

```sql
SELECT
    application_name,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_catalog.pg_stat_replication;
```

### 8.1. Lag is recent response delay

Lag fields estimate the time from when a WAL record was flushed on the primary until the standby reported receiving/flushing/replaying that position. They reflect recent transactions and are not a full prediction of backlog catch-up time.

### 8.2. Can be NULL when idle

If the primary has no recent WAL activity, lag fields may be NULL. NULL does not automatically mean the standby has failed.

### 8.3. Do not sum lag fields as an independent number

Write, flush, and replay lag have overlapping relationships and distinct semantics. Use LSN gaps for current backlog size, and lag time to gauge recent delay.

### 8.4. Monitoring needs both bytes and time

Monitor:
- WAL bytes behind.
- Receive/replay LSN movement.
- Last message receipt.
- Last replayed transaction timestamp.
- WAL generation rate.
- Standby disk/CPU.
- Connection state and logs.

---

## 9. Diagnosing network and connection errors

### 9.1. Check host and port

From the standby, verify DNS, routing, and TCP connectivity to the primary port (commonly 5432 by default). Use approved network tools in your environment, such as `Test-NetConnection` on Windows or `nc`/`psql` on Linux.

### 9.2. Check what the primary is listening on

```sql
SHOW listen_addresses;
SHOW port;
```

The primary must listen on an interface reachable by the standby. Changing some settings requires a restart.

### 9.3. Check firewall and security groups

Allow TCP connections from the standby address to the primary. Avoid exposing the replication port to the entire Internet; restrict by subnet/host and network policy.

### 9.4. Check DNS and addresses

If `primary_conninfo` uses a hostname, confirm the standby resolves the current IP address. After failover, DNS/proxy endpoints must point to the new primary.

### 9.5. Check TLS

If using SSL/TLS, verify the CA, certificate, hostname, and `sslmode`. `verify-full` validates both chain and hostname; a certificate mismatch can break connections after an endpoint swap.

### 9.6. Check connection limits

Compare `max_wal_senders` against standbys, backup streams, and replication clients needing connections. If WAL sender slots are exhausted, new standbys may fail to connect.

### 9.7. Check timeouts and network stability

Firewall idle timeouts, NAT, packet loss, or connection tracking can drop long-lived streams. Inspect `wal_sender_timeout`, `wal_receiver_timeout`, TCP keepalives, and network logs. Do not lower timeouts too aggressively just to detect failures faster if the network normally has high latency.

---

## 10. Replication authentication

### 10.1. Replication role

The replication user needs `LOGIN` and `REPLICATION` privileges, or equivalent permissions under role/managed service policy.

Example creating a role in a lab:

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-a-secret';
```

Never use illustrative passwords in production. Manage credentials via a secret store or appropriate passfile.

### 10.2. pg_hba.conf

An example rule restricting replication from the standby subnet:

```conf
hostssl replication replicator 10.20.30.0/24 scram-sha-256
```

Authentication syntax must match your PostgreSQL version and policy. After editing, reload configuration and inspect logs.

### 10.3. Verify pg_hba_file_rules

```sql
SELECT *
FROM pg_catalog.pg_hba_file_rules;
```

This view helps detect parse errors and confirm rules were loaded. It does not replace testing actual connections from the standby.

### 10.4. Check role privileges

```sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication
FROM pg_catalog.pg_roles
WHERE rolname = 'replicator';
```

### 10.5. Never write passwords into logs/chat

Never paste passwords or connection strings containing secrets into public tickets. Use a passfile with restricted OS file permissions.

---

## 11. Checking primary_conninfo on the standby

The standby uses `primary_conninfo` to know how to connect upstream.

Example configuration:

```conf
primary_conninfo = 'host=db-primary.example.internal port=5432 user=replicator application_name=standby_a sslmode=verify-full'
```

### 11.1. Fields to check

- `host`: DNS name/IP of the current primary.
- `port`: PostgreSQL port.
- `user`: replication role.
- `application_name`: name displayed on the primary.
- `sslmode` and certificate settings if using TLS.
- `passfile`: credential location if needed.

### 11.2. Do not hard-code secrets

Avoid placing passwords in broadly readable config files. Use a passfile/secret manager and protect files with filesystem permissions.

### 11.3. Configuration can live in multiple places

`primary_conninfo` can come from `postgresql.conf`, included configs, or `postgresql.auto.conf` written by tools like `pg_basebackup -R`. Inspect the effective source:

```sql
SELECT
    name,
    setting,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'primary_conninfo',
    'primary_slot_name',
    'restore_command',
    'recovery_target_timeline'
);
```

On some versions, `sourcefile`/`sourceline` may be NULL depending on privileges or configuration source.

### 11.4. After failover

If the primary changes host/port, the standby must connect to the new primary. Update the connection via your HA endpoint or designed automation; do not merely swap the hostname while ignoring timeline divergence.

---

## 12. Checking WAL sender and replication capacity

### 12.1. max_wal_senders

Limits concurrent WAL sender processes. Account for direct standbys, backup streams, and consumers needing replication connections.

```sql
SHOW max_wal_senders;
```

### 12.2. max_replication_slots

Limits replication slots. Each standby with its own slot must be counted in the capacity plan.

```sql
SHOW max_replication_slots;
```

### 12.3. max_connections

Replication connections are not ordinary application SQL connections; verify WAL sender capacity and service/managed platform limits separately.

### 12.4. Logs when capacity is exhausted

Logs may report inability to spawn WAL senders or no remaining slots. Raising limits requires evaluating process/memory overhead and often requires a restart for certain parameters.

### 12.5. Do not confuse capacity exhaustion with lost WAL

If the primary cannot allocate a WAL sender, the standby can reconnect once capacity is restored. That differs from a WAL segment already having been recycled.

---

## 13. How do replication slots retain WAL?

A replication slot records the position a consumer still needs. With a physical slot, the primary retains WAL segments required by the standby from `restart_lsn` onward.

### 13.1. List slots

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

Use `SELECT *` when exploring schemas to avoid errors from differing columns across major versions. In long-term monitoring, explicitly select columns present on the deployed version.

### 13.2. Key fields

- `slot_name`: slot name.
- `slot_type`: `physical` or `logical`.
- `active`: whether a consumer is currently using the slot.
- `restart_lsn`: earliest WAL the consumer may still need.
- `confirmed_flush_lsn`: typically meaningful for logical slots.
- `wal_status`/`safe_wal_size`: retention status on supported versions.

### 13.3. Inactive slots

If a standby loses its connection, its physical slot becomes inactive while continuing to retain WAL. This helps the standby catch up when it returns, as long as storage suffices and retention policies do not invalidate the slot.

### 13.4. Slots can retain WAL for a long time

A standby offline for days can make `pg_wal` grow dramatically if the slot retains all required WAL.

### 13.5. max_slot_wal_keep_size

This parameter caps the amount of WAL retained for replication slots on supported versions. When exceeded, needed segments can be recycled and the slot is no longer usable to catch up.

### 13.6. Never set unlimited blindly

Unlimited retention protects slots from losing WAL, yet can fill the filesystem. Choose a limit based on disk capacity, peak WAL generation, and tolerated standby offline time.

### 13.7. Never drop a slot solely to shrink disk usage

Dropping a slot can strip the standby of required WAL. Before dropping, verify owner, consumer, backup/recovery dependencies, and reinitialization plan.

---

## 14. wal_keep_size and retention limits

`wal_keep_size` instructs the primary to keep at least a specified amount of recent WAL so standbys have a chance to reconnect after brief interruptions.

```sql
SHOW wal_keep_size;
```

### 14.1. Not a long-term retention guarantee

If a standby stays offline longer than the retained WAL, the primary can recycle old segments. When the standby returns, WAL will be missing.

### 14.2. Does not replace replication slots

`wal_keep_size` does not track exact consumer positions like a replication slot. It is a minimum WAL cushion, not a guarantee every standby retains enough history.

### 14.3. Does not replace an archive

A WAL archive stores segments outside `pg_wal` to support longer recovery and PITR. `wal_keep_size` is not an archive repository.

### 14.4. Size based on WAL generation rate

Rough estimate:

```text
Required WAL retention
  ≈ WAL generation rate × tolerated standby offline time
    + headroom for workload bursts
```

This is only a sizing estimate. Measure peak WAL rate, real outage durations, and other consumers.

### 14.5. Do not rely on max_wal_size to protect standbys

`max_wal_size` is a checkpoint pressure target, not a hard cap or commitment to hold WAL for standbys.

---

## 15. WAL archiving as a catch-up source

When a standby can no longer find a segment in the primary's `pg_wal`, an archive can supply older segments.

### 15.1. On the primary

Configure archive mode and an appropriate archive command/library:

```conf
archive_mode = on
archive_command = 'archive-helper %p %f'
```

`archive-helper` is a placeholder. The command must return success only after the file is durably stored per the archive system's contract.

### 15.2. On the standby

Configure `restore_command` to retrieve WAL segments from the archive:

```conf
restore_command = 'restore-helper %f %p'
```

`restore-helper` is a placeholder for a script/tool that reads the archive and writes the file to the requested path.

### 15.3. Combining archive and streaming

During standby recovery, PostgreSQL can obtain WAL from both the archive and streaming replication. When streaming is interrupted, it can retry archive/reconnect within its recovery loop. Exact retry order and log messages depend on version/configuration.

### 15.4. The archive must contain a continuous segment chain

An archive holding many files that is missing the exact needed segment still cannot help the standby catch up.

### 15.5. History files must also be present

After promotion, standbys may need timeline history files to follow the new branch.

### 15.6. Archive integrity

Use checksums/manifests, immutable storage, and monitoring. Never report archive success before data is durably stored.

---

## 16. Diagnosing WAL missing messages

A common log message reads like:

```text
requested WAL segment ... has already been removed
```

This usually indicates the standby requested a WAL segment that the current primary no longer supplies from `pg_wal`.

### 16.1. Check the slot

- Does the standby configure `primary_slot_name`?
- Does the slot exist on the primary?
- Is the slot active/inactive?
- Does `restart_lsn` still cover the needed segment?
- Was the slot invalidated due to a retention limit?

### 16.2. Check the archive

- Does the segment exist in the archive?
- Does `restore_command` return the right file?
- Does the archive have the right timeline prefix?
- Was the file corrupted or deleted by retention?

### 16.3. Check the timeline

- Was the current primary promoted from a standby?
- Is the standby still following an old timeline?
- Does the history file exist?
- Is `recovery_target_timeline` appropriate?

### 16.4. Decision

- Same timeline, WAL still in archive: let the standby continue recovery/catch-up.
- Same timeline, WAL missing on primary yet archive is complete: supply the archive and verify `restore_command`.
- Same timeline, WAL lost on both primary and archive: rebuild the standby from a base backup.
- Timelines diverged: evaluate `pg_rewind`; if preconditions fail, take a new base backup.

### 16.5. Never copy an arbitrary segment into pg_wal

WAL must belong to the exact system identifier, timeline, segment sequence, and checksum. Copying a wrong file can break recovery or cause further corruption.

---

## 17. Checking timelines before catch-up

After failover, a standby may still point to the old primary or an old timeline.

### 17.1. Signs of divergence

- The new primary was promoted and has a higher timeline ID.
- The standby reports a WAL segment does not exist on the current timeline.
- Logs mention timeline history or timeline switches.
- The standby may need WAL from the new branch starting at the fork point.

### 17.2. Inspect history files

Read the timeline history file in the archive or `pg_wal` to identify the parent timeline and fork LSN. Never edit the file.

### 17.3. recovery_target_timeline

In standby configuration, `recovery_target_timeline = 'latest'` normally allows following the newest timeline found. Verify version, archive, and history files before relying on this setting.

### 17.4. Same timeline and different timeline are two distinct cases

Losing a connection does not itself cause timeline divergence. If the standby merely lagged on the same branch and enough WAL remains, reconnecting suffices. If one branch was promoted and the other took independent writes, rewind or rebuild is required.

### 17.5. Similar LSNs do not prove shared history

Record both TLI and LSN when comparing two nodes. Never conclude a standby is caught up solely because LSN numbers look close.

---

## 18. Reconnecting and catching up when sufficient WAL remains

This is the easiest case to resolve: the standby lost network connectivity for a period while the primary still retains needed WAL segments, or an archive supplies complete segments.

### 18.1. Restore network/authentication

Fix DNS, firewalls, TLS, `pg_hba.conf`, credentials, or connection endpoints.

### 18.2. Verify primary_conninfo

Ensure the standby connects to the right current primary with the right `application_name`/slot name.

### 18.3. Check the receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

When streaming works, the receiver normally reports `streaming` status and advancing LSNs.

### 18.4. Check the primary

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
```

### 18.5. Track LSN progression

Take multiple snapshots over time. If sent/write/flush/replay LSNs advance steadily, the standby is catching up.

### 18.6. Compare backlog and throughput

Measure bytes behind over multiple intervals. If replay throughput exceeds the WAL generation rate, the backlog decreases. If the primary generates WAL faster than the standby replays it, lag may continue to grow even though the receiver is connected.

### 18.7. Do not take a base backup if WAL remains continuous

If the standby is on the same timeline and has all required WAL, PostgreSQL automatically replays what is missing. Rebuilding in that situation wastes bandwidth and I/O unnecessarily.

---

## 19. Why does a standby receive WAL yet replay slowly?

Receive lag and replay lag require different remedies.

### 19.1. Storage latency

The WAL receiver may receive bytes yet flush slowly due to disk latency, throughput, or filesystem pressure.

### 19.2. Replay CPU

WAL replay requires CPU to process records and update pages/indexes. Busy standby CPU can slow replay.

### 19.3. Read query conflicts

Read-only queries on a hot standby can conflict with WAL replay, such as a query holding a snapshot needed for cleanup. PostgreSQL may delay replay or cancel the query depending on standby delay settings.

### 19.4. max_standby_streaming_delay

This parameter controls how long a standby may delay replay to wait for conflicting queries before canceling them. Increasing it can protect reporting queries while increasing replay lag.

### 19.5. hot_standby_feedback

This can send feedback so the primary avoids vacuuming row versions needed by standby queries, though it can cause bloat on the primary. It is not a general way to increase replay throughput.

### 19.6. recovery_min_apply_delay

If configured non-zero, the standby intentionally delays applying WAL. This may be a delayed-standby design to guard against certain logical errors; do not treat that lag as a network fault.

### 19.7. Replay paused

Check:

```sql
SELECT pg_is_wal_replay_paused();
```

If paused, verify the reason before resuming:

```sql
SELECT pg_wal_replay_resume();
```

Do not resume mechanically if the pause is part of a PITR/DR procedure awaiting verification.

---

## 20. Timeout and retry settings

Several parameters affect connection detection and recovery:

| Setting | Role | Notes |
| --- | --- | --- |
| `wal_sender_timeout` | Primary detects a silent WAL sender connection | Too low can disconnect high-latency networks |
| `wal_receiver_timeout` | Standby detects no messages from upstream | Evaluate alongside network timeouts |
| `wal_retrieve_retry_interval` | Retry interval when WAL cannot be obtained during recovery | Affects retry cadence |
| `wal_receiver_status_interval` | Interval at which standby sends status updates | Affects how frequently primary receives progress |
| `tcp_keepalives_idle` | Idle time before TCP keepalive | OS-dependent |
| `tcp_keepalives_interval` | Interval between probes | OS-dependent |
| `tcp_keepalives_count` | Number of probes before connection is considered dead | OS-dependent |

Inspect PostgreSQL settings:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'wal_sender_timeout',
    'wal_receiver_timeout',
    'wal_retrieve_retry_interval',
    'wal_receiver_status_interval',
    'primary_conninfo',
    'primary_slot_name',
    'wal_keep_size',
    'max_slot_wal_keep_size'
)
ORDER BY name;
```

Some OS keepalive settings do not appear in full inside PostgreSQL on every platform. Do not tune timeouts merely to mask network faults; determine latency, idle timeout, and failure detection requirements.

---

## 21. When is pg_rewind needed?

`pg_rewind` fits when target and source once belonged to the same cluster yet diverged after a common point, commonly because an old primary and a new primary both generated WAL on different timelines.

### 21.1. Reconnecting does not resolve divergence

If the target wrote its own WAL after the fork point, it cannot simply receive the source's WAL and continue as though no separate branch existed.

### 21.2. pg_rewind identifies the common point

The tool locates the common timeline history/fork point, identifies blocks modified on the source, and updates the target to follow the source.

### 21.3. Common use cases

- An old primary returning after failover.
- A standby promoted by mistake that needs to return to the authoritative branch.
- A promoted PITR cluster that needs to rejoin another topology.

### 21.4. Do not use pg_rewind for every WAL gap

If a standby merely missed WAL due to extended downtime while staying on the same timeline, an archive or a new base backup is appropriate depending on WAL availability. `pg_rewind` is for divergence, not a general tool to reload missing WAL.

---

## 22. Preconditions for pg_rewind

Before running it, confirm all conditions appropriate for your PostgreSQL version:

1. Source and target share the same system identifier/cluster ancestry prior to the fork point.
2. Target PostgreSQL has been shut down cleanly.
3. Data checksums were enabled when the cluster ran `initdb`, or `wal_log_hints` was enabled on the target before divergence occurred.
4. `full_page_writes` is enabled as required by `pg_rewind`.
5. Required WAL from the fork point is available in target `pg_wal` or retrievable from the archive.
6. Access to the source exists via the chosen method.
7. Sufficient disk space and OS permissions exist on the target.
8. A snapshot/backup of the target exists if data must be preserved for investigation.
9. The `pg_rewind` tool matches the cluster's major version.

### 22.1. Data checksums

You can check status with an appropriate tool such as `pg_controldata`. Checksums must be enabled at cluster creation or through a PostgreSQL-supported conversion procedure.

### 22.2. wal_log_hints

If data checksums are off, `wal_log_hints` can satisfy the requirement to detect hint-bit changes for rewind, provided it was enabled before the tracked changes occurred. Enabling it after divergence cannot recreate missing WAL.

### 22.3. full_page_writes

Must be enabled to ensure WAL contains the page images required for rewind/recovery as specified by the tool.

### 22.4. Target must be shut down cleanly

Never run `pg_rewind` against the data directory of a running server. Stop the target cleanly and confirm no processes still use the directory.

### 22.5. WAL from the fork point

If required WAL is no longer in target `pg_wal`, you can use the `restore-target-wal` option to fetch from the archive if `restore_command` is configured properly. Without that WAL, rewind may not be possible.

---

## 23. Running pg_rewind

Example using a source server:

```bash
pg_rewind \
  --target-pgdata=/data/old-standby \
  --source-server="host=new-primary port=5432 dbname=postgres user=rewind_user"
```

Replace paths, connection strings, users, and privileges with values from your actual environment.

### 23.1. Source server

The source is the authoritative cluster the target needs to follow. The source server normally must be running and the connecting user needs appropriate permissions for `pg_rewind` to read data/control information.

### 23.2. Target data directory

The target is the cleanly stopped data directory to be rewound. Verify the exact path before running because the tool modifies target contents.

### 23.3. Fetching WAL from the archive

If a WAL archive is needed and the target already has `restore_command`:

```bash
pg_rewind \
  --target-pgdata=/data/old-standby \
  --source-server="host=new-primary port=5432 dbname=postgres user=rewind_user" \
  --restore-target-wal
```

Options and syntax must be verified against the `pg_rewind` binary for your major version.

### 23.4. Writing standby configuration after rewind

On supported versions, `--write-recovery-conf` (or `-R`) can create the needed recovery/standby configuration, including the signal file and connection settings. Review generated files before starting.

### 23.5. Completing rewind does not mean the standby has caught up

After rewind, the target may need crash recovery/WAL replay before streaming resumes. Monitor logs and receiver/replay LSNs.

### 23.6. If pg_rewind fails

Do not retry repeatedly without understanding the error. Preserve logs, check preconditions, WAL availability, system identifier, permissions, and target state. If rewind is impossible, create a new standby from a base backup.

---

## 24. Reinitializing a standby with pg_basebackup

When required WAL is gone, timeline divergence cannot be rewound, or the data directory is corrupted, the clean path is creating a new standby from a base backup of the authoritative primary.

### 24.1. When should you rebuild?

- Required WAL segments are missing on both the primary and the archive.
- The replication slot was invalidated and insufficient WAL remains.
- Target and source do not meet `pg_rewind` preconditions.
- The target data directory is corrupted or untrustworthy.
- You want to replace an old standby with a fresh clone.
- Rewind failed and there is no way to supply missing WAL.

### 24.2. Preparing before backup

1. Confirm the right authoritative primary.
2. Confirm the target standby is stopped.
3. Preserve/snapshot the old data directory if needed for investigation.
4. Choose a new or empty destination data directory.
5. Check the replication role and `pg_hba.conf`.
6. Check disk space, network throughput, and tablespace paths.
7. Choose the replication slot and WAL streaming method.
8. Check backup retention and archive policy.

### 24.3. Create a replication role if missing

Lab example:

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-a-secret';
```

In production, use secret management and do not put passwords into logs.

### 24.4. pg_hba.conf rule

```conf
hostssl replication replicator 10.20.30.0/24 scram-sha-256
```

This rule is only an example. Adjust subnet, auth method, and TLS to match security policy.

### 24.5. Primary configuration

Settings commonly inspected:

```conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
hot_standby = on
```

Values are illustrative, not universal recommendations for every cluster. `wal_level` must fit the topology; some parameters require a restart.

### 24.6. Basic base backup

Example:

```bash
pg_basebackup \
  -h new-primary \
  -p 5432 \
  -U replicator \
  -D /data/standby-new \
  -R \
  -X stream \
  -P
```

`-R` writes the configuration needed to continue as a standby on supported versions. `-X stream` streams WAL during the backup. `-P` displays progress.

### 24.7. Using a replication slot

If the slot already exists and is dedicated to the standby:

```bash
pg_basebackup \
  -h new-primary \
  -p 5432 \
  -U replicator \
  -D /data/standby-new \
  -R \
  -X stream \
  -S standby_a_slot \
  -P
```

If creating a new slot via `pg_basebackup` on a supported version:

```bash
pg_basebackup \
  -h new-primary \
  -p 5432 \
  -U replicator \
  -D /data/standby-new \
  -R \
  -X stream \
  -C \
  -S standby_a_slot \
  -P
```

Do not use `-C` if a slot with the same name already exists. By design, only one consumer should own that slot.

### 24.8. Why use -X stream?

WAL is streamed in parallel during the base backup, giving the backup the WAL needed to form a consistent copy. Account for WAL sender connections and bandwidth for this operation.

### 24.9. Target data directory must meet conditions

The destination normally must be empty or prepared per tool procedure. Never let `pg_basebackup` overwrite the data directory of a running instance. Verify tablespace mappings and file ownership.

### 24.10. Major version

A physical base backup must match the cluster's major version and platform/format. Never use `pg_basebackup` to perform a major version upgrade; use a supported upgrade workflow.

---

## 25. Configuring the standby after pg_basebackup

Once the base backup completes, inspect the generated configuration.

### 25.1. standby.signal

On PostgreSQL 12 and later, standby mode is normally enabled via `standby.signal`. `pg_basebackup -R` can create this file.

### 25.2. primary_conninfo

Check endpoint, replication user, `application_name`, TLS, and passfile. Do not leave the standby pointing at an old primary.

### 25.3. primary_slot_name

If using a physical replication slot, configure the standby to use the exact slot created/reserved for it.

### 25.4. restore_command

If the archive serves as a fallback source for WAL catch-up, configure `restore_command` properly and test archive access permissions.

### 25.5. recovery_target_timeline

For a standby that must follow a new timeline after failover, verify `recovery_target_timeline` is appropriate; `latest` is commonly chosen to follow the newest branch, provided complete archive/history files exist.

### 25.6. Inspect postgresql.auto.conf

`pg_basebackup -R` can write configuration into `postgresql.auto.conf`. Review precedence among the main file, included files, and `auto.conf` before editing.

### 25.7. Protect credentials

Use a passfile or secret store. Set restrictive filesystem permissions so only PostgreSQL's OS account can read them.

---

## 26. Starting the standby and verifying streaming begins

### 26.1. Start the instance

Use your service manager or `pg_ctl` according to deployment. Check logs immediately after starting.

### 26.2. Check recovery state

```sql
SELECT pg_is_in_recovery();
```

Expected: `true`.

### 26.3. Check the WAL receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

Once the receiver connects, verify sender host, status, slot name, and LSN fields match expectations.

### 26.4. Check the primary

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
```

Confirm the new standby appears with the expected `application_name`.

### 26.5. Check logs

Look for messages indicating streaming started, WAL received, catch-up, and connection errors. If the receiver reconnects repeatedly, determine the root cause rather than restarting the instance over and over.

---

## 27. Monitoring catch-up after reconnect/rebuild

A newly reconnected standby may need to replay a large volume of WAL.

### 27.1. Take periodic snapshots

On the primary:

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind
FROM pg_catalog.pg_stat_replication;
```

### 27.2. Track backlog reduction rate

Take multiple timestamped snapshots. If `bytes_behind` decreases, the standby is catching up. If it increases, the primary is generating WAL faster than the standby processes it or a bottleneck exists.

### 27.3. Separate receive from replay

If write/flush LSN is close to sent LSN while replay LSN trails far behind, focus on replay/storage/query conflicts. If sent LSN trails current LSN, focus on the WAL sender/network.

### 27.4. Do not demand zero lag under continuous load

In a continuously writing system, a standby may always have a small delay. Stability criteria should rest on SLO/RPO and trend rather than requiring zero on every snapshot.

### 27.5. Confirm replay is not paused

```sql
SELECT pg_is_wal_replay_paused();
```

### 27.6. Interpret last replay time carefully

If the primary creates no transactions, the replay timestamp may stay unchanged. Evaluate alongside LSN movement and WAL generation.

---

## 28. Handling disk pressure while a standby is offline

### 28.1. Why does pg_wal grow?

- A physical slot retains WAL for an offline standby.
- `archive_command` is failing.
- Another logical slot is retaining WAL.
- Workload is generating WAL rapidly.
- A standby/consumer is not advancing `restart_lsn`.
- Multiple backup/replication consumers concurrently request WAL.

### 28.2. Check disk capacity

Use OS monitoring to inspect the filesystem hosting `pg_wal`, growth rate, and free space. PostgreSQL does not provide a single simple hard cap guaranteeing this directory cannot exceed a threshold.

### 28.3. Check slot retention

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

Compare `restart_lsn`, `active`, and retention fields available on your version.

### 28.4. Check the archiver

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

A steadily rising failed count signals the need to check archive destination, permissions, networking, and command logs.

### 28.5. Never delete WAL manually

Never remove files inside `pg_wal` to free disk space. Doing so can make the primary unable to crash-recover or strip standbys/backups of required WAL.

### 28.6. Remediate by root cause

- Expand storage capacity if urgent.
- Restore the archive destination.
- Identify the consumer holding the slot and the expected catch-up time.
- If a slot is no longer needed, follow the runbook after verifying owner/dependencies.
- Rebuild the standby if WAL has been lost.
- Throttle workload if WAL generation exceeds storage capacity.

---

## 29. Invalidated replication slots

If a slot needs WAL older than retention permits and segments have already been recycled, the standby cannot use that slot to catch up.

### 29.1. Symptoms

Depending on version, `pg_replication_slots` may show `wal_status` as no longer usable or an equivalent status. Logs may indicate the requested WAL segment has already been removed.

### 29.2. A slot cannot recreate lost history

Creating a new slot does not restore deleted WAL segments. A new slot only retains WAL from its current position onward.

### 29.3. Evaluate the archive

If the archive holds complete WAL from the position the standby needs, the standby can recover via archive and then resume streaming.

### 29.4. If the archive is also missing segments

Take a new base backup. Never try to feed a standby a discontinuous WAL stream.

### 29.5. Create a slot for the rebuilt standby

When rebuilding, create a new slot or reuse an existing verified slot. Set retention limits and capacity alerts to prevent recurrence.

---

## 30. Choosing among reconnect, archive, pg_rewind, and base backup

| Situation | Usually appropriate action | Key condition |
| --- | --- | --- |
| Brief network interruption, WAL remains on primary | Reconnect/streaming catch-up | Same timeline, enough WAL remains |
| WAL recycled on primary yet archive is complete | Archive recovery then streaming | `restore_command` and archive continuity |
| Standby offline longer, slot retained WAL | Reconnect and catch-up | Slot still valid, sufficient disk |
| Slot lost WAL yet archive is complete | Restore WAL from archive | Right timeline and continuous segments |
| WAL missing on both primary and archive, same timeline | New base backup | Healthy source primary |
| Standby on old branch after promotion | `pg_rewind` or base backup | Timeline divergence |
| `pg_rewind` preconditions unmet | New base backup | Same source cluster, permissions, and capacity |
| Data directory corrupted | Reinitialize from backup | Reliable base backup |
| Two primaries both writing | Fence, preserve data, pick authoritative branch, then rewind/rebuild | HA incident procedure |

### 30.1. Reconnect is first choice when sharing history

If sufficient WAL remains, let PostgreSQL reconnect and replay automatically. Never rebuild merely because the receiver lost its connection once.

### 30.2. Archives rescue WAL that has left pg_wal

An archive helps only when segments still exist and are continuous. It cannot recreate missing segments.

### 30.3. pg_rewind is for divergence

Rewind does not replace a base backup for ordinary WAL gaps or data directory corruption.

### 30.4. Base backup recreates a physical copy

When current WAL history cannot continue, a new base backup establishes a consistent starting point.

---

## 31. Reference replication configuration for a lab

The following examples illustrate key components only; adapt them for real environments.

### 31.1. Primary

```conf
listen_addresses = '*'
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = '1GB'
archive_mode = on
archive_command = 'archive-helper %p %f'
```

Do not use `listen_addresses='*'` without appropriate network controls. `wal_keep_size` is a sizing example, not a universal value.

### 31.2. Replication role and pg_hba

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-a-secret';
```

```conf
hostssl replication replicator 10.20.30.0/24 scram-sha-256
```

### 31.3. Standby

```conf
primary_conninfo = 'host=db-primary port=5432 user=replicator application_name=standby_a sslmode=verify-full'
primary_slot_name = 'standby_a_slot'
restore_command = 'restore-helper %f %p'
recovery_target_timeline = 'latest'
```

Standby mode on PostgreSQL 12+ requires `standby.signal`. `pg_basebackup -R` can create the signal file and required recovery settings.

### 31.4. Slot

Create a physical replication slot on the primary:

```sql
SELECT *
FROM pg_catalog.pg_create_physical_replication_slot('standby_a_slot');
```

Check whether a slot already exists before creating it. Do not create duplicate slots for the same role.

### 31.5. Settings with restart requirements

Parameters such as `wal_level`, `max_wal_senders`, and `max_replication_slots` usually require a restart when changed. Check `pg_settings.context` and `pending_restart`.

---

## 32. Lab 1: checking replication health

The lab requires one primary and one standby in an isolated environment.

### 32.1. On the primary

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
```

Record the state.

### 32.2. On the standby

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 32.3. Generate a small workload

On the primary:

```sql
CREATE TABLE IF NOT EXISTS public.replication_lab (
    id BIGINT PRIMARY KEY,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO public.replication_lab(id, message)
VALUES (1, 'replication-check')
ON CONFLICT (id) DO UPDATE
SET message = EXCLUDED.message,
    created_at = clock_timestamp();
```

### 32.4. Verify on the standby

Wait for replay and query the row. The standby should reflect the change once WAL is applied.

### 32.5. Compute bytes behind

On the primary:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_behind
FROM pg_catalog.pg_stat_replication;
```

### 32.6. Observe multiple times

Repeat the snapshot after a few seconds. Note whether `bytes_behind` grows or shrinks with the workload.

---

## 33. Lab 2: simulating a brief disconnect

Perform only in a lab; never cut production networking.

### 33.1. Record baseline

Save sent/write/flush/replay LSNs and slot state before disconnecting.

### 33.2. Pause network or standby

Use a lab mechanism to disconnect the standby briefly. Do not delete the data directory and do not delete WAL.

### 33.3. Observe the primary

Confirm the row disappears from `pg_stat_replication` and the slot's active state changes.

### 33.4. Observe the standby

Check logs for disconnect/retry messages. The WAL receiver may disappear from the view while disconnected.

### 33.5. Restore networking

Allow the standby to reconnect to the same primary on the same timeline.

### 33.6. Verify catch-up

Check receiver state, primary replication row, and LSN movement. The standby should replay the missing WAL.

### 33.7. Conclusion

If WAL was still retained, no base backup is needed. Record the maximum offline duration tolerated by the current configuration.

---

## 34. Lab 3: testing replication slot retention

Use only a lab cluster with suitable disk capacity.

### 34.1. Create a physical slot

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_lab_slot');
```

### 34.2. Inspect the slot

```sql
SELECT *
FROM pg_replication_slots
WHERE slot_name = 'standby_lab_slot';
```

### 34.3. Disconnect the standby and generate WAL

In the lab, stop/pause the standby and generate a write workload on the primary. Do not create a workload larger than disk capacity allows.

### 34.4. Monitor retained WAL

Check `restart_lsn` and WAL disk usage. While the slot is inactive, the primary continues holding segments needed by the slot.

### 34.5. Reconnect

Restore the standby and watch the receiver catch up while WAL segments remain intact.

### 34.6. Clean up the lab

Drop the slot only after confirming the standby no longer uses it and the lab is finished:

```sql
SELECT pg_drop_replication_slot('standby_lab_slot');
```

Never run this command on a production slot serving a standby.

---

## 35. Lab 4: archive-assisted catch-up

The lab requires WAL archiving properly configured on the primary and `restore_command` on the standby.

### 35.1. Verify the archive

```sql
SELECT *
FROM pg_stat_archiver;
```

### 35.2. Generate WAL

```sql
INSERT INTO public.replication_lab(id, message)
VALUES (2, 'archive-catchup')
ON CONFLICT (id) DO UPDATE
SET message = EXCLUDED.message;
```

### 35.3. Switch WAL in the lab

```sql
SELECT pg_switch_wal();
```

Use this command only in an appropriate lab/maintenance scenario; do not force continuous switches in production.

### 35.4. Check archive files

Verify the WAL segment has its full filename, right timeline, and expected checksum/size in the archive destination.

### 35.5. Test restore_command

On the standby, confirm the command can retrieve a file by requested name and return the right exit status when a file does not exist.

### 35.6. Test recovery

Run the test with an isolated lab standby and observe logs showing WAL fetched from archive/streaming. Never delete production WAL to force archive recovery.

---

## 36. Lab 5: rebuilding a standby with pg_basebackup

This exercise creates a new standby in an isolated environment. Never overwrite a running node's data directory.

### 36.1. Verify the primary

On the primary, verify role and replication capacity. Check the replication user and `pg_hba`.

### 36.2. Create a slot

```sql
SELECT pg_create_physical_replication_slot('standby_rebuild_slot');
```

If the slot already exists, verify ownership/state instead of recreating it.

### 36.3. Take a base backup

```bash
pg_basebackup \
  -h db-primary \
  -U replicator \
  -D /data/standby-rebuilt \
  -R \
  -X stream \
  -S standby_rebuild_slot \
  -P
```

### 36.4. Inspect generated files

Verify the data directory has the PostgreSQL directory structure, `standby.signal`, and matching connection/slot config. Check tablespaces if present.

### 36.5. Start the standby

Start using the lab service manager/`pg_ctl`. Read logs and check `pg_is_in_recovery()`.

### 36.6. Verify receiver and primary

Query `pg_stat_wal_receiver` on the standby and `pg_stat_replication` on the primary.

### 36.7. Verify data

Query `replication_lab` on the standby after replay. Compare selected business rows/checksums.

### 36.8. Wrap up

Record backup duration, transferred bytes, catch-up time, and slot state. Clean up the lab per your procedure.

---

## 37. Lab 6: pg_rewind after timeline divergence

This lab requires two data directories sharing ancestry and a controlled promotion scenario. Never execute on production.

### 37.1. Prepare before divergence

Enable data checksums at `initdb` or enable `wal_log_hints` beforehand. Ensure `full_page_writes` is enabled. Configure archiving to keep WAL.

### 37.2. Create the standby

Use `pg_basebackup` to create the standby and confirm streaming.

### 37.3. Promote in the lab

Fence the old primary in the lab and promote the standby. Generate some new WAL on the new primary.

### 37.4. Old primary

Keep the old primary's data directory to illustrate divergence. Do not allow that node to receive additional writes.

### 37.5. Shut down the target cleanly

Stop the old primary with a clean shutdown and verify no processes still use the data directory.

### 37.6. Run pg_rewind

Point `source-server` to the new primary and `target-pgdata` to the old data directory. Use `restore-target-wal` if WAL from the archive is needed.

### 37.7. Configure as standby

Use `write-recovery-conf` if supported by your version, or configure connection/signal files per runbook.

### 37.8. Start and verify

Check `pg_is_in_recovery()`, WAL receiver, timeline, and replay LSN. Verify post-promotion data appears on the rejoined standby.

### 37.9. If preconditions are unmet

Record the exact error, preserve the data directory, and rebuild the standby from a base backup. Never edit WAL or control files manually.

---

## 38. Common misconceptions

| Misconception | Reality |
| --- | --- |
| No `pg_stat_replication` row means the standby is broken | It only indicates no direct connection exists at query time |
| Receiver connected means the standby is caught up | A receive/replay backlog may still remain |
| Receive LSN equals replay LSN means everything is fine | Must compare against primary and timeline while checking workload |
| `write_lag` is the total catch-up time | It reflects recent lag, not a backlog forecast |
| Old `last_replay_timestamp` means standby failure | The primary may simply have no new transactions |
| `wal_keep_size` retains WAL indefinitely | It is only a minimum retention amount |
| `max_wal_size` is a hard disk cap | No; slots/archives can retain additional WAL |
| An inactive slot can be dropped immediately | The slot may be holding WAL needed by a standby |
| Creating a new slot recovers lost WAL | Slots do not recreate old segments |
| Archive enabled means the standby always catches up | Requires WAL continuity and working `restore_command` |
| Network loss always requires `pg_basebackup` | If enough WAL remains, reconnecting suffices |
| Every WAL gap uses `pg_rewind` | Rewind is for timeline divergence |
| `pg_rewind` replaces base backups in all cases | It has preconditions and needs WAL from the fork point |
| `pg_rewind` runs while the target is active | The target must be shut down as required |
| `wal_log_hints` can be enabled after an incident to rewind | It must be enabled prior to divergence |
| Synchronous replication eliminates all data loss | Requires proper standby, quorum, fencing, and failover policy |
| Promoting a standby makes the old primary follow it automatically | The old primary needs rewind or rebuild |
| Changing `primary_conninfo` alone suffices after failover | Timeline divergence may still exist |
| Copying WAL files manually is always safe | Requires exact system identifier, TLI, sequence, and integrity |
| Restarting the receiver repeatedly fixes all errors | Must diagnose network, auth, retention, or replay root cause |
| Rebuilding a standby does not impact the primary | It can generate heavy network, disk, and WAL load |
| Base backups from another major version always work | Physical format must match the major version |
| Slow WAL replay is always caused by networking | Can stem from storage, CPU, conflicts, or apply delay |
| Increasing `max_standby_streaming_delay` is always good | Can increase replay lag |
| `hot_standby_feedback` solves all replay lag | Can cause primary bloat |
| Two nodes with close LSNs share the same branch | Must verify timeline |
| `pg_stat_replication` shows the entire cascading tree | Shows directly connected standbys only |
| Dropping a slot is the standard way to shrink disk | Can strip standbys of needed WAL |
| Delete files in `pg_wal` to free disk space | Can break recovery |
| Promotion is a config-only change | It ends recovery and creates a new WAL branch |
| Archive history files are unnecessary | Required to follow timeline ancestry |
| Standby replay paused means a network error | May be an intentional pause or recovery target |
| A successful backup guarantees a successful rebuild | Requires restore tests and data verification |

---

## 39. Runbook: standby disconnected

A production runbook should follow a verifiable sequence.

### 39.1. Record observations

- Incident timestamp.
- Primary/standby hostnames and cluster identifier.
- Timeline ID if known.
- Latest primary LSN.
- Latest receive/replay LSN on the standby.
- Replication slot and archive state.
- PostgreSQL logs on both nodes.

### 39.2. Determine scope

Verify whether the primary is still serving the application, whether other standbys are connected, and whether the issue is isolated to one network segment.

### 39.3. Inspect receiver/sender

- Standby: `pg_stat_wal_receiver`.
- Primary: `pg_stat_replication`.
- Logs: authentication, timeouts, missing WAL, timeline mismatch.

### 39.4. Check network/auth

DNS, routes, TCP ports, firewalls, TLS, `pg_hba`, replication role, and connection string.

### 39.5. Check WAL retention

Slots, `restart_lsn`, `max_slot_wal_keep_size`, `wal_keep_size`, archive continuity, and disk usage.

### 39.6. Choose recovery path

- Same timeline, sufficient WAL: reconnect.
- WAL in archive: restore via archive.
- Diverged timeline, rewind preconditions met: `pg_rewind`.
- WAL missing or rewind unsuitable: `pg_basebackup`.

### 39.7. Monitor catch-up

Measure sent/write/flush/replay LSNs, bytes behind, WAL rate, disk latency, and receiver state.

### 39.8. Verify

Check sample rows, business metrics, application smoke tests, and replication stability.

### 39.9. Close incident

Document root cause, outage duration, any data loss, recovery method, backup references, and follow-up changes.

---

## 40. Designing monitoring and alerting

A production replication setup should alert on critical states and trends.

### 40.1. Connection state

Alert when an expected standby is absent from `pg_stat_replication` beyond an allowed threshold.

### 40.2. Receiver health

Alert when `pg_stat_wal_receiver` has no row or last message receipt is stale while the primary is generating WAL.

### 40.3. WAL backlog

Track bytes behind across sent/write/flush/replay LSNs. Set thresholds per workload/SLO rather than one fixed threshold for all clusters.

### 40.4. Catch-up rate

Measure backlog reduction rate. If the backlog does not shrink under normal load, the standby is not catching up.

### 40.5. Slot retention

Alert on retained WAL bytes, inactive slot duration, `wal_status`, and `safe_wal_size` when supported by the version.

### 40.6. Disk capacity

Alert on free space, growth rate, and estimated time to full for `pg_wal` and archive filesystems.

### 40.7. Archive health

Monitor `pg_stat_archiver`, archive failures, last archived time, and continuity checks.

### 40.8. Timeline events

Record promotions, new TLIs, new history files, and rejoin operations. Alert if a standby remains on an old timeline too long after failover.

### 40.9. Replay conflicts

Monitor recovery conflicts, canceled standby queries, and apply delay if read workloads run on the standby.

### 40.10. Do not alert solely on replay timestamp

When the primary is idle, the timestamp may stay unchanged. Combine LSNs, workload activity, and receiver messages.

---

## 41. Sizing retention and catch-up capacity

### 41.1. Estimate WAL generation

Compute `wal_bytes` delta in `pg_stat_wal` over an interval:

```sql
SELECT
    wal_bytes,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

Take snapshots over time to calculate bytes/second or bytes/minute. Counters can reset, so check `stats_reset`.

### 41.2. Estimate offline window

Determine how long a standby may stay disconnected during maintenance/incident scenarios.

### 41.3. Estimate WAL to retain

Peak WAL rate × outage window + headroom. Add other consumers and retention requirements.

### 41.4. Catch-up throughput

The standby must replay faster than the WAL generation rate over a window for the backlog to shrink. Otherwise, scale resources, throttle load, or accept a rebuild.

### 41.5. Disk headroom

Slot retention can hold WAL beyond `max_wal_size`. Disk sizing must account for peak WAL, archive backlog, slot backlog, and incident response time.

### 41.6. Capacity is part of RPO/RTO

If WAL is recycled before a standby returns, recovery time rises sharply because a base backup must be taken. Retention policy directly impacts RTO.

---

## 42. Security and operational permissions

### 42.1. Least-privilege replication user

Use a dedicated role with `LOGIN`/`REPLICATION`, not superuser for routine streaming replication.

### 42.2. Network allowlist

Restrict replication connections by subnet/host, TLS, and firewall rules.

### 42.3. Secret handling

Never write passwords into logs, committed scripts, or tickets. Use a passfile/secret store and rotation.

### 42.4. Data directory permissions

Only the PostgreSQL OS account and authorized admin tools should hold needed permissions. Never allow multiple users to write into the data directory.

### 42.5. pg_rewind/base backup permissions

These tools can read/write substantial data. Only authorized operators should run them, and target paths/sources must be verified before execution.

### 42.6. Archive security

WAL archives contain enough data to reconstruct changes. Protect read access, encryption at rest, retention, and immutable copies.

---

## 43. Practice exercises

### Exercise 1 — Replication architecture

Diagram the WAL flow from primary to standby, explaining the roles of WAL sender, WAL receiver, and startup process.

### Exercise 2 — Sent/write/flush/replay

Distinguish the four LSNs in `pg_stat_replication` and explain how to identify the slow stage.

### Exercise 3 — Receiver status

Write a query to inspect `pg_stat_wal_receiver` and explain why the view may contain zero rows.

### Exercise 4 — Receive vs replay

A standby's receive LSN advances while its replay LSN stalls. List the causes to investigate.

### Exercise 5 — LSN distance

Use `pg_wal_lsn_diff` to compute bytes behind. Why must you confirm the same timeline?

### Exercise 6 — Lag time

Explain `write_lag`/`flush_lag`/`replay_lag` and why they can be NULL when idle.

### Exercise 7 — Network

Build a checklist for DNS, routing, firewalls, ports, and TLS when the receiver cannot connect.

### Exercise 8 — Authentication

Write a replication role and suitable `pg_hba` rule. Explain `REPLICATION` privilege and SCRAM/TLS.

### Exercise 9 — primary_conninfo

List required fields and explain how to protect credentials.

### Exercise 10 — WAL sender capacity

Why must `max_wal_senders` account for standbys and backup streams?

### Exercise 11 — Replication slot

Explain `restart_lsn` and why an inactive slot can cause `pg_wal` to grow.

### Exercise 12 — wal_keep_size

Why does `wal_keep_size` not guarantee unlimited WAL for a standby?

### Exercise 13 — max_slot_wal_keep_size

Describe the trade-off between unlimited WAL retention and bounded retention.

### Exercise 14 — Archive catch-up

Design a `restore_command` to fetch WAL from an archive and state the conditions for archive success.

### Exercise 15 — Missing WAL

Standby logs report `requested WAL segment has already been removed`. Order the investigation across slot, archive, timeline, and disk.

### Exercise 16 — Reconnect

A standby loses connection for 10 minutes while WAL remains intact. Describe the reconnect procedure and catch-up checks.

### Exercise 17 — Replay bottleneck

Flush LSN is close to sent LSN yet replay LSN lags. Propose investigations across CPU, disk, query conflicts, and replay pause.

### Exercise 18 — Replay delay

A standby configures `recovery_min_apply_delay`. Why is an old last replay timestamp not necessarily a fault?

### Exercise 19 — Timeline divergence

A new primary was promoted yet a standby still follows an old timeline. Why might changing `primary_conninfo` alone be insufficient?

### Exercise 20 — pg_rewind

Explain the purpose of `pg_rewind` and why it applies only to two branches sharing common ancestry.

### Exercise 21 — Rewind prerequisites

List requirements covering clean shutdown, checksums/`wal_log_hints`, `full_page_writes`, and WAL from the fork point.

### Exercise 22 — Rewind command

Write a `pg_rewind` example using `source-server` and `target-pgdata`. State the risks around the target path.

### Exercise 23 — Rewind archive

When is `restore-target-wal` used? What conditions must hold on the target?

### Exercise 24 — Base backup

Write a `pg_basebackup` command using `-R`, `-X stream`, and a replication slot. Explain `-C` and `-S`.

### Exercise 25 — Rebuild decision

Provide selection criteria between `pg_rewind` and `pg_basebackup` across four scenarios: WAL gap, divergence, corruption, and missing archive.

### Exercise 26 — Rejoin verification

After rebuilding, write queries confirming `pg_is_in_recovery`, receiver, primary replication state, and replay progress.

### Exercise 27 — Slot invalidation

A slot lost required WAL. Why will creating a new slot not restore old segments?

### Exercise 28 — Disk pressure

The `pg_wal` filesystem has 5% free space remaining. Write a runbook handling archive backlog, slot retention, and workload spikes.

### Exercise 29 — Monitoring

Design a dashboard covering connection status, receive/replay LSN, bytes behind, slot retention, archive failures, and disk time-to-full.

### Exercise 30 — Catch-up throughput

WAL generation is 20 MB/s and standby replay is 15 MB/s. How will the backlog change? Propose investigation and mitigation steps.

### Exercise 31 — Synchronous replication

A synchronous standby loses connectivity. How can commit behavior change depending on `synchronous_commit` and quorum configuration?

### Exercise 32 — Failover

A primary stops responding yet may merely be experiencing a network partition. Why must fencing happen before promotion?

### Exercise 33 — Cascading replication

A cascading standby loses its upstream. Identify the nodes and WAL paths to inspect.

### Exercise 34 — Archive retention

Design retention for a primary generating 100 GB WAL/day where a standby may go offline for 8 hours. What headroom and consumers must be included?

### Exercise 35 — Base backup load

A `pg_basebackup` increases primary latency. Propose ways to throttle/schedule backups and measure impact.

### Exercise 36 — Restore drill

Design a test creating a new standby from a base backup, catching up via WAL archive, and verifying application data.

### Exercise 37 — Version compatibility

A `pg_replication_slots` query referencing `safe_wal_size` fails on older PostgreSQL. Build an approach to discover the schema and write a compatible query.

### Exercise 38 — Logs

Identify groups of log messages that distinguish network timeouts, authentication failures, missing WAL, and timeline mismatches.

### Exercise 39 — Security

Design a replication user, TLS, `pg_hba` allowlist, passfile, and data directory permissions.

### Exercise 40 — End-to-end operations

A system has one primary, three standbys across two regions, a 7-day WAL archive, one logical consumer, and a 1-minute RPO. Design slot policy, WAL retention, catch-up, rewind/rebuild, alerting, failover fencing, and restore drills. Analyze trade-offs across RPO/RTO, disk, network, and latency.

---

## 44. Disconnect and standby reinitialization operational checklist

| Item | What to confirm |
| --- | --- |
| Primary running? | Health, logs, `pg_is_in_recovery` |
| Standby in recovery? | `pg_is_in_recovery` |
| WAL sender connection present? | `pg_stat_replication` |
| WAL receiver has a row? | `pg_stat_wal_receiver` |
| State is streaming/catchup? | Replication state |
| Host/port correct? | `primary_conninfo` |
| DNS/routing working? | Network diagnostics |
| Firewall allows traffic? | TCP allowlist |
| TLS valid? | CA/hostname/certificate |
| `pg_hba` rule correct? | `pg_hba_file_rules` |
| Replication role valid? | `LOGIN`/`REPLICATION` |
| Enough WAL sender capacity? | `max_wal_senders` |
| Slot exists? | `pg_replication_slots` |
| Slot active/inactive? | `active` |
| `restart_lsn` still needed? | Retention analysis |
| Slot invalidated? | `wal_status`/version fields |
| `wal_keep_size` adequate? | Offline window |
| `max_slot_wal_keep_size` appropriate? | Disk vs retention |
| Archive mode active? | `pg_stat_archiver` |
| WAL archive continuous? | Manifest/checksum |
| `restore_command` works? | Test fetch |
| Timeline matches? | TLI + history files |
| `recovery_target_timeline` appropriate? | `latest`/`current`/specific |
| Receive LSN advancing? | `pg_last_wal_receive_lsn` |
| Replay LSN advancing? | `pg_last_wal_replay_lsn` |
| Replay paused? | `pg_is_wal_replay_paused` |
| Disk/CPU sufficient? | OS metrics |
| Read query conflicts? | Standby conflict stats/logs |
| WAL generation rate? | `pg_stat_wal` delta |
| Backlog shrinking? | Time-series LSN gap |
| Can reconnect/catch up? | Sufficient WAL remains |
| `pg_rewind` needed? | Timeline divergence + prerequisites |
| Target cleanly shut down? | `pg_rewind` precondition |
| Checksums or `wal_log_hints`? | Enabled prior to divergence |
| `full_page_writes` enabled? | Rewind requirement |
| WAL from fork point available? | Local/archive |
| Snapshot taken before rewind? | Recovery safety |
| If rewind fails, base backup available? | Rebuild plan |
| Target data directory safe? | Empty/right target |
| `pg_basebackup` `-R`/`-X`/`-S` appropriate? | Backup plan |
| New slot managed? | Ownership/retention |
| Standby signal/config correct? | `standby.signal`/conninfo |
| Rebuild matches major version? | Compatibility |
| Rejoin complete? | Receiver/replay state |
| Application data accurate? | Smoke tests |
| Archive/slot disk headroom left? | Capacity alerts |
| Incident root cause documented? | Logs/timeline/LSN |

## Conclusion

Handling a disconnected standby in PostgreSQL requires clearly distinguishing connectivity errors, WAL retention, and timeline divergence. When the standby remains on the same history and sufficient WAL exists, restoring the connection so it can catch up automatically is enough. When WAL has left `pg_wal` yet the archive remains continuous, `restore_command` can supply missing segments. When the standby has moved onto a different branch, `pg_rewind` can bring it back to the authoritative branch if all preconditions are satisfied. If required WAL is gone, the data directory is corrupted, or rewind is unsuitable, rebuild the standby from a base backup.

Key principles to remember:

1. **Check both ends of replication.** `pg_stat_replication` on the primary and `pg_stat_wal_receiver` on the standby show connection status from both sides.
2. **Distinguish sent, write, flush, and replay.** They pinpoint whether WAL lags in sending, writing, flushing, or applying.
3. **Use LSNs to measure backlog alongside timeline.** LSN distance is in bytes; never treat LSNs from two diverged branches as one stream.
4. **Lag time is not catch-up ETA.** Measure bytes behind, WAL generation rate, and replay throughput over time.
5. **Replication slots retain WAL while consuming disk.** An inactive slot can cause `pg_wal` to grow; set limits and alerts.
6. **`wal_keep_size` does not replace an archive or slot.** It merely keeps a minimum WAL cushion for reconnects.
7. **Archives must be continuous and match the timeline.** A single missing segment or history file can block recovery.
8. **Reconnect when sufficient WAL remains.** Do not rebuild a standby just because of a network disconnect.
9. **`pg_rewind` is for timeline divergence.** Check clean shutdown, checksums or `wal_log_hints`, `full_page_writes`, and WAL from the fork point.
10. **`pg_basebackup` creates a fresh physical copy.** Use it when WAL is gone, the target is damaged, or rewind preconditions fail.
11. **Rebuilds must be verified.** Check receiver, replay LSN, timeline, slot, sample data, and application behavior.
12. **Never delete WAL manually.** Manage archives, slots, capacity, and rebuilds per runbook.
13. **Fence before promoting.** Losing connectivity does not prove the primary is dead; prevent split brain.
14. **Restore drills prove recoverability.** Test archive catch-up, rewind, and base backups in an isolated environment.

A healthy standby is not merely one whose connection state reads `streaming`. It must receive the right WAL, advance flush and replay, follow the right timeline, maintain sufficient WAL retention for expected outages, and have a tested reinitialization plan when it cannot catch up to current history.
