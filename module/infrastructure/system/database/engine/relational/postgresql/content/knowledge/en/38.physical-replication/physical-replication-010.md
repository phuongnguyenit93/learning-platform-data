# Write Lag, Flush Lag, Replay Lag, and Measuring Latency in PostgreSQL

## 1. Why measure replication lag across multiple stages?

In PostgreSQL physical streaming replication, the primary sends WAL to the standby. The standby receives WAL, writes WAL to storage, durably flushes WAL, and then replays records to update data pages and transaction state. These steps run continuously, yet they do not necessarily finish at the exact same instant.

A dashboard showing only "replication lag = 10 seconds" is usually insufficient to pinpoint root causes. A standby may be slow due to the network, storage write speed, flush latency, replay workload, recovery conflicts, or because the primary generates WAL faster than the standby processes it.

PostgreSQL exposes LSN positions and time metrics to observe each stage:

- **Write lag:** delay until the standby reports having written WAL.
- **Flush lag:** delay until the standby reports having flushed WAL.
- **Replay lag:** delay until the standby reports having replayed WAL.
- **LSN/byte lag:** WAL positional distance between stages.
- **Rate/backlog trend:** WAL generation rate, replay rate, and whether the backlog is growing or shrinking.

```text
PRIMARY
  WAL generated
       |
       v
  sent_lsn
       |
       | network / sender queue
       v
STANDBY
  write_lsn       <- WAL written
       |
       | storage flush
       v
  flush_lsn       <- WAL flushed
       |
       | recovery / replay
       v
  replay_lsn      <- WAL applied
       |
       v
  Data pages / visible state
```

**No single lag number explains everything.** Read write, flush, and replay alongside LSN backlogs, connection status, workload, and sync mode.

### Learning objectives

After this lesson, you will be able to:

1. Describe the WAL path from primary to standby.
2. Distinguish sent, write, flush, and replay LSNs.
3. Explain the meaning of `write_lag`, `flush_lag`, and `replay_lag`.
4. Distinguish time lag from byte lag and replication backlogs.
5. Measure each queue using `pg_wal_lsn_diff`.
6. Measure WAL generation rate and replay rate over time.
7. Estimate catch-up time when a standby can drain its backlog.
8. Read `pg_stat_replication`, `pg_stat_wal_receiver`, and `pg_stat_activity`.
9. Distinguish replication lag from archive lag and replication slot retention.
10. Understand synchronous replication and `synchronous_commit`.
11. Recognize intentional replay delays and recovery conflicts.
12. Build dashboards, alerts, and lag investigation runbooks.
13. Measure lag with transaction markers when business-level proof is needed.
14. Avoid misinterpreting NULL values or stale timestamps when the system is idle.

---

## 2. Stages of physical streaming replication

A WAL record is created on the primary before it can be sent to the standby. The WAL sender transmits data over the replication connection. The WAL receiver on the standby receives data and writes it to WAL storage. Then the recovery process replays WAL to update database state.

| Stage | Commonly observed position | Meaning |
|---|---|---|
| WAL generation | `pg_current_wal_lsn()` on primary | WAL written up to the current position |
| WAL sent | `sent_lsn` | Last WAL position sent over the connection |
| WAL written | `write_lsn` | Position the standby reported writing WAL to |
| WAL flushed | `flush_lsn` | Position the standby reported flushing WAL to |
| WAL replayed | `replay_lsn` | Position the standby has replayed WAL to |

These LSNs form a positional chain for analyzing backlogs. Column names and certain observation details can vary by PostgreSQL major version; inspect views on your actual server.

### 2.1. Sent does not mean written

The primary may have sent a WAL span without the standby confirming it wrote to file yet. The distance between `sent_lsn` and `write_lsn` suggests data is still in transit/receiver buffers or awaiting write acknowledgement.

### 2.2. Written does not mean flushed

WAL may be written to the filesystem without being confirmed durably flushed. The distance between `write_lsn` and `flush_lsn` reflects the portion waiting for flush.

### 2.3. Flushed does not mean replayed

WAL may be durable on the standby while recovery has not applied all of it yet. The distance between `flush_lsn` and `replay_lsn` is the backlog at the replay stage.

### 2.4. Replay does not mean every query sees the same instant

Standby queries read a consistent snapshot taken when their transaction begins. An already-running query does not automatically shift its snapshot to newly replayed data after starting.

## 3. What is an LSN?

LSN (Log Sequence Number) is a position in the WAL stream. PostgreSQL typically displays LSNs in the format:

```text
0/16B6C50
```

An LSN is not a timestamp, transaction ID, or row ID. You can use `pg_wal_lsn_diff` to compute the byte distance between two WAL positions.

Example:

```sql
SELECT pg_wal_lsn_diff('0/2000100', '0/2000000') AS bytes_between;
```

The result is the byte distance between the two LSNs.

### 3.1. Compare LSNs within the same WAL history

LSNs are meaningful only within the same cluster/WAL history. After promotion, timelines can change. Never subtract LSNs from two independent clusters as if they belonged to one continuous sequence.

### 3.2. Growing LSN does not equal growing row count

WAL also records index changes, page images, catalog updates, full-page writes, and internal operations. WAL volume does not equal business data bytes.

### 3.3. LSN diff is byte backlog, not time

100 MB of lag may correspond to a few seconds on fast storage or many minutes on a slow standby. Converting to time requires measuring throughput and the WAL generation rate.

## 4. What is write lag?

`write_lag` in `pg_stat_replication` represents the elapsed time from when the primary recently flushed WAL until the primary received notification that the standby wrote the corresponding WAL.

It answers: **How quickly does WAL reach the standby and get written?**

High `write_lag` can involve:
- Network latency or packet loss.
- Standby receiver/OS scheduling.
- Storage write queues.
- CPU pressure.
- WAL sender/receiver congestion.
- Standby overloaded by other workloads.

### 4.1. Write lag is not network latency alone

This metric covers the path from primary to standby plus the standby's write/acknowledgement processing. Do not conclude the network is slow from `write_lag` alone.

### 4.2. Low write lag yet high flush lag

This suggests the standby writes WAL promptly yet flushes slowly to storage. Inspect disk latency, `fsync`, storage queues, and write-cache guarantees.

### 4.3. Low write lag yet high replay lag

WAL is transmitted and written relatively fast, yet the standby cannot replay fast enough. Investigate replay throughput, query workloads, and recovery conflicts.

## 5. What is flush lag?

`flush_lag` represents the elapsed time from when the primary recently flushed WAL until the primary received notification that the standby flushed the corresponding WAL.

Flush is the key milestone for WAL durability on the standby. With synchronous replication and `synchronous_commit = on`, commits wait for standby WAL flush per PostgreSQL semantics.

High `flush_lag` can result from:
- High storage latency.
- Slow `fsync`.
- Slow WAL receiver flushes.
- Disk contention from queries/backups/checkpoints.
- Filesystem or cloud volume throttling.
- Growing I/O queues.

### 5.1. Flush lag is not exact data-loss duration

It is a timing indicator for recent WAL milestones, not a direct measure of the last transaction lost if the primary dies. Actual RPO requires verifying acknowledged transactions and the promoted standby.

### 5.2. High flush lag in synchronous replication

If transactions wait on standby flushes, application commit latency rises. Check `synchronous_commit`, `synchronous_standby_names`, `sync_state`, and wait events.

### 5.3. Low flush lag does not prove replay caught up

The standby may have durably flushed WAL while replay still has a backlog. Check `replay_lsn` and `replay_lag` separately.

## 6. What is replay lag?

`replay_lag` represents the elapsed time from when the primary recently flushed WAL until the primary received notification that the standby replayed the corresponding WAL.

Replay is the recovery step applying WAL to update database state on the standby. It can be slow even when both network and flush perform well.

Common causes:
- WAL generation rate exceeds replay capacity.
- Slow storage reads/writes.
- Insufficient CPU.
- Competing query workloads on the standby.
- Recovery conflicts with long-running read queries.
- Intentionally configured `recovery_min_apply_delay`.
- Checkpoint/recovery I/O.
- A large batch transaction or index build generating heavy WAL.

### 6.1. Replay lag is not exact queue duration

It reflects how long recent WAL changes took to be confirmed replayed. Do not interpret it as "the standby needs exactly 30 seconds to catch up."

### 6.2. Idle standbys may report NULL replay lag

When there is no new WAL, there are no recent transaction samples to compute lag intervals. NULL does not automatically mean the standby is broken.

### 6.3. Old replay timestamps may simply mean an idle primary

`pg_last_xact_replay_timestamp()` is the timestamp of the last transaction replayed during recovery. If the primary executes no new transactions, this timestamp stays unchanged even when the standby is completely caught up.

## 7. Time lag fields in pg_stat_replication

On the primary:

```sql
SELECT
    application_name,
    state,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
```

Fields:
- `write_lag`: time until WAL write acknowledgement.
- `flush_lag`: time until WAL flush acknowledgement.
- `replay_lag`: time until WAL replay acknowledgement.
- `reply_time`: timestamp when the primary received the most recent standby reply.

### 7.1. Measured on the primary

`pg_stat_replication` is a primary-side view, where each row represents a WAL sender connection to a standby. Returning zero rows when queried on a standby is normal.

### 7.2. NULL is not zero

If a lag field is NULL, never silently replace it with 0 during interpretation. Record "no sample/no value" and inspect `state`, LSN positions, `reply_time`, and workload.

### 7.3. Lag fields are not ETAs

PostgreSQL describes these time lag fields as how long recent transactions took to synchronize. They do not predict how long a standby will take to catch up if the primary stops writing.

### 7.4. Never use a single field as the sole health check

A standby can report `state = streaming` while its replay backlog grows. Conversely, time lag can be NULL during idle periods while the standby is completely healthy.

## 8. Measuring byte lag using LSNs on the primary

Combined query:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        sent_lsn
    ) AS not_yet_sent_bytes,
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
    ) AS flushed_not_replayed_bytes,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS total_replay_backlog_bytes
FROM pg_stat_replication
ORDER BY application_name;
```

### 8.1. How to read it

- `not_yet_sent_bytes`: WAL written on primary not yet sent on the connection.
- `sent_not_written_bytes`: WAL sent not yet confirmed written by the standby.
- `written_not_flushed_bytes`: WAL written not yet confirmed flushed.
- `flushed_not_replayed_bytes`: WAL flushed not yet confirmed replayed.
- `total_replay_backlog_bytes`: distance from primary's current WAL to the standby's replay position.

These are LSN distances at observation time, not exact byte sizes of internal buffers or file queues.

### 8.2. Snapshot caveat

Stats and LSN positions can update at slightly different instants. Values may shift slightly across samples; examine trends rather than concluding from a single snapshot.

### 8.3. Do not mechanically sum every queue

The intervals are sequential segments of the same WAL span. `total_replay_backlog_bytes` already encompasses all stages prior to replay. Never add it on top of its component queues.

## 9. Measuring LSN positions on the standby

On the standby, you can check:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS last_receive_lsn,
    pg_last_wal_replay_lsn() AS last_replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_transaction_time;
```

- `pg_last_wal_receive_lsn()` reports the last WAL position received and synced to disk per function semantics.
- `pg_last_wal_replay_lsn()` reports the last WAL position replayed.
- `pg_last_xact_replay_timestamp()` reports the timestamp of the last transaction replayed during recovery.

### 9.1. Receive and replay differ

If receive LSN advances rapidly while replay LSN stalls, the standby is receiving WAL yet recovery cannot keep up or is blocked.

### 9.2. Sample concurrently with the primary

To calculate end-to-end byte lag, compare the primary's current LSN with the standby's replay LSN within the same sampling window while recording timestamps and server identities.

### 9.3. pg_is_in_recovery()

This function tells whether the server is in recovery/standby mode. After promotion, it returns `false`; dashboards must recognize role changes instead of applying standby formulas to a primary.

## 10. pg_stat_replication: key view on the primary

This view exposes WAL sender/standby status:

```sql
SELECT
    pid,
    usename,
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
    replay_lag,
    reply_time
FROM pg_stat_replication;
```

### 10.1. Connection-identifying columns

- `pid`: WAL sender process ID.
- `application_name`: standby/client-declared name.
- `client_addr`: client IP address if applicable.
- `state`: replication state.
- `sync_state`: current synchronous/asynchronous role.

### 10.2. Multiple standbys require inspecting every row

A single primary can stream to multiple standbys. One healthy standby does not mean all standbys are healthy. Track every `application_name` and `client_addr`.

### 10.3. Streaming state

`state = 'streaming'` means the connection is streaming WAL. It does not by itself prove low lag, fast replay, or compliance with synchronous policy.

### 10.4. Stats privileges

Some columns may be hidden if the role lacks full stats visibility. Use an appropriate monitoring role such as `pg_monitor` per security policy.

## 11. pg_stat_wal_receiver: view on the standby

On the standby, `pg_stat_wal_receiver` shows WAL receiver status.

Example:

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

Specific columns can vary by version. Verify the view on your actual server before standardizing long-term monitoring queries.

### 11.1. status

During normal streaming, `status` usually shows `streaming`. Zero rows can mean the standby is not currently using a streaming connection or is in another recovery state.

### 11.2. last_msg_receipt_time

Timestamp when the standby last received a message from the sender. If unusually stale while the primary has write traffic, inspect network, sender, receiver, and connection health.

### 11.3. latest_end_lsn

Latest WAL end position reported by the sender to the receiver. This is a useful signal, though still compare it with receive/replay positions and the primary's current LSN.

### 11.4. Do not confuse receiver with replay process

The WAL receiver receives data; the recovery process replays data. A streaming receiver does not guarantee replay is advancing.

## 12. Distinguishing standby lag from archive lag

Streaming replication and WAL archiving are two separate paths.

| Signal | View/tool | Data path |
|---|---|---|
| Streaming replication lag | `pg_stat_replication` | Primary → standby |
| WAL receive/replay | `pg_stat_wal_receiver`, recovery functions | Receiver/recovery on standby |
| Archive success/failure | `pg_stat_archiver` | Primary → archive repository |
| Archive freshness | Archive inventory/logs | WAL segments → backup storage |
| Slot retention | `pg_replication_slots` | WAL retained for consumer |

### 12.1. Standby can stay caught up while archiving fails

Streaming WAL continues reaching the standby even when `archive_command` fails. The PITR archive chain can break even while failover standbys look healthy.

### 12.2. Archiving can be healthy while a standby lags

WAL archiving may save segments quickly while a standby's network, receiver, or replay lags behind.

### 12.3. Track the two goals separately

- Standby lag: read/failover readiness.
- Archive lag: PITR/backup recoverability.

Never merge both metrics into a single replication status.

## 13. Distinguishing lag from replication slot retention

A replication slot retains WAL needed by a consumer. It can cause `pg_wal` to grow, yet does not directly tell how slowly the standby is replaying.

Inspect:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    xmin,
    catalog_xmin
FROM pg_replication_slots
ORDER BY slot_name;
```

### 13.1. restart_lsn

Oldest WAL position the slot may still need. The slot retains WAL from this position so the consumer can resume.

### 13.2. Inactive slots

An inactive slot still retains WAL. Verify owner/consumer before dropping or invalidating.

### 13.3. Estimating WAL retention distance

```sql
SELECT
    slot_name,
    active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS retained_wal_distance_bytes
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
```

This is an LSN distance, not exact filesystem disk usage. WAL segments are managed/recycled on segment boundaries and may also be pinned for other reasons.

### 13.4. Do not reflexively drop slots to fix lag

Dropping a slot can prevent a standby/CDC consumer from resuming from its previous position. Assess resync and recovery impacts first.

## 14. Time lag and byte lag answer different questions

| Metric | Question answered | Limitation |
|---|---|---|
| `write_lag` | How delayed were recent WAL write acknowledgements? | Not a catch-up ETA |
| `flush_lag` | How delayed were recent WAL flush acknowledgements? | Not directly actual RPO |
| `replay_lag` | How delayed were recent WAL replay acknowledgements? | Not time remaining |
| LSN byte gap | How many WAL bytes behind the primary is the standby? | Does not show throughput |
| Backlog growth rate | Is lag growing or shrinking? | Requires multiple samples |
| Replay throughput | How fast is the standby applying WAL? | Varies with workload and window |
| Marker gap | Which commit markers are missing? | Represents only tested cadence/path |

### 14.1. When to prioritize byte lag?

When you need to know how much WAL remains queued, size storage/network capacity, or forecast replay work.

### 14.2. When to prioritize time lag?

When monitoring recent commit latency or business objectives defined in seconds.

### 14.3. When are transaction markers needed?

When you need evidence close to actual acknowledged data loss, especially during failover drills or RPO validation.

## 15. Measuring queues per stage

A query can compute each stage distance:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS sent_to_write_bytes,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS write_to_flush_bytes,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS flush_to_replay_bytes
FROM pg_stat_replication;
```

### 15.1. Large sent-to-write gap

Investigate:
- Network throughput/latency.
- Receiver CPU.
- Standby scheduling.
- WAL receiver process state.
- Network retransmits/packet loss.

### 15.2. Large write-to-flush gap

Investigate:
- Storage latency.
- `fsync` latency.
- IOPS/throughput throttling.
- Disk queue depth.
- Filesystem/cache behavior.

### 15.3. Large flush-to-replay gap

Investigate:
- Replay process CPU/I/O.
- Recovery conflicts.
- Query load on the standby.
- `recovery_min_apply_delay`.
- Batch transactions or WAL bursts.

### 15.4. Do not look only at the largest queue

A large queue can be a symptom of an upstream bottleneck. Check stage rates and trends before diagnosing the bottleneck.

## 16. Measuring WAL generation rate

On the primary, sample LSN at two timestamps:

```sql
SELECT
    clock_timestamp() AS sampled_at,
    pg_current_wal_lsn() AS current_lsn;
```

Store samples externally or in monitoring. Given two samples:

```text
WAL generation rate
  = diff(current_lsn_2, current_lsn_1)
    / elapsed_seconds
```

Units are bytes/second when `pg_wal_lsn_diff` returns bytes.

### 16.1. Workloads vary over time

A system may generate 2 MB/s off-peak and 100 MB/s during batch windows. Long-term averages can hide peaks requiring capacity.

### 16.2. WAL generation is not data growth

WAL includes index/page changes, full-page images, catalog operations, and internal overhead. WAL rate does not equal newly inserted business data.

### 16.3. Measure across suitable windows

Use multiple windows: short windows to catch bursts, longer windows for trends and capacity baselines.

## 17. Measuring replay rate

On the primary, sample `replay_lsn` from `pg_stat_replication` periodically; or on the standby sample `pg_last_wal_replay_lsn()`.

```text
Replay rate
  = diff(replay_lsn_2, replay_lsn_1)
    / elapsed_seconds
```

### 17.1. Measure replay rate on the same timeline

After promotion/timeline changes, do not connect samples from two different WAL histories without handling the timeline transition.

### 17.2. Replay rate equals 0

The standby may be receiving no new WAL, idle, paused, or stalled in recovery. Cross-check receiver status, primary write activity, and logs.

### 17.3. Unsteady replay rate

Large transactions, index builds, or checkpoints can cause replay throughput to fluctuate. Use rolling windows and multiple samples.

## 18. Is the backlog growing or shrinking?

Suppose:
- WAL generation rate = 20 MB/s.
- Replay rate = 25 MB/s.
- Replay backlog = 1,000 MB.

If both rates hold steady, the backlog shrinks by roughly 5 MB/s.

If:
- WAL generation rate = 30 MB/s.
- Replay rate = 25 MB/s.

The backlog grows by roughly 5 MB/s. The standby cannot catch up while the primary continues generating WAL faster than replay speed.

### 18.1. Net catch-up rate

```text
net catch-up rate = replay rate - WAL generation rate
```

If positive, the backlog can shrink. If zero or negative, the standby will not close the backlog under the current workload.

### 18.2. Estimating ETA

```text
estimated catch-up time
  = backlog bytes / net catch-up rate
```

Use only when net catch-up rate is positive and workload is fairly steady. This is an estimate, not a guarantee.

### 18.3. Example

Backlog 900 MB, replay 60 MB/s, WAL generation 30 MB/s:

- Net catch-up rate = 30 MB/s.
- Approximate ETA = 900 / 30 = 30 seconds.

If replay rate drops to 25 MB/s while generation stays 30 MB/s, ETA is meaningless because the backlog is growing.

### 18.4. Never forecast from one sample

Calculate rates across multiple intervals and observe rolling averages. A brief spike can skew ETA wildly.

## 19. Measuring on the standby with pg_stat_wal_receiver

Sample query:

```sql
SELECT
    status,
    received_tli,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    now() - last_msg_receipt_time AS message_age
FROM pg_stat_wal_receiver;
```

### 19.1. Message age

If the primary has WAL activity yet `last_msg_receipt_time` is stale, check connection, network, and receiver. If the primary is idle, interpret message age alongside heartbeat/status behavior.

### 19.2. Received timeline

`received_tli` shows which timeline the receiver is processing. During failover, inspect timeline history and primary connections to confirm the standby follows the right branch.

### 19.3. Combine with replay position

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS receive_to_replay_bytes;
```

This query applies only when positions are populated and the server is in recovery. If NULL, check receiver state and server role.

## 20. Reading wait events to locate bottlenecks

`pg_stat_activity` reports wait events for backends, including WAL sender/receiver and related processes.

Example:

```sql
SELECT
    pid,
    backend_type,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - backend_start AS backend_age
FROM pg_stat_activity
WHERE backend_type ILIKE '%wal%'
   OR application_name ILIKE '%standby%';
```

Wait event names vary by version. You may see the WAL sender waiting for new data or socket/network I/O, or the receiver waiting for WAL. Never diagnose from wait event names alone; correlate with LSNs/rates and OS metrics.

### 20.1. Network bottlenecks

Inspect interface throughput, retransmits, packet loss, RTT, firewall/NAT idle timeouts, and connection resets.

### 20.2. Storage bottlenecks

Inspect read/write/`fsync` latency, IOPS, throughput limits, queue depth, disk saturation, and cloud volume throttling.

### 20.3. CPU bottlenecks

Replay and checksum/decompression consume CPU. Compare CPU utilization, run queues, per-process CPU usage, and replay rate.

## 21. Synchronous replication and the meaning of lag

Synchronous replication can cause commits on the primary to wait for standbys to acknowledge WAL at the configured level.

Key components:
- `synchronous_standby_names`: identifies participating synchronous standbys.
- `synchronous_commit`: acknowledgement level transactions wait for.
- `sync_state`: synchronous state of each standby.

### 21.1. synchronous_commit = local

Commits wait for local WAL flush per semantics, without waiting for remote standbys.

### 21.2. synchronous_commit = remote_write

Commits wait for the standby to confirm WAL was written to the OS; this does not mean durable storage flush.

### 21.3. synchronous_commit = on

With synchronous replication, commits wait for the standby to durably flush WAL per PostgreSQL semantics.

### 21.4. synchronous_commit = remote_apply

Commits wait for the standby to replay WAL, useful when applications must read fresh data immediately on the standby after commit, at the cost of potentially higher latency.

### 21.5. synchronous_standby_names

If no eligible synchronous standby is available, commit behavior is affected per configuration. Verify live state rather than reading the config file alone.

## 22. Reading sync_state and sync_priority

Query:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY sync_priority, application_name;
```

Common states in `sync_state` include:
- `async`: standby is asynchronous.
- `potential`: standby eligible to become synchronous per config/availability.
- `sync`: currently selected synchronous standby.
- `quorum`: standby participating in quorum synchronous replication.

Exact names/states depend on configuration and PostgreSQL version.

### 22.1. Quorum synchronous

With quorum configured, transactions need only enough standbys to acknowledge. Do not assume every standby in the list must flush before commit.

### 22.2. One sync standby does not mean all replicas are sync

Inspect each row and determine which standbys are actually chosen to satisfy commit durability.

### 22.3. Promotion policy

After failover, the promoted node must satisfy promised durability guarantees. An async standby does not become zero-data-loss merely because it remained connected.

## 23. Intentional replay delay

A standby can be configured to delay replay via `recovery_min_apply_delay`. This is useful for certain protections against accidental deletions, yet creates intentional replay lag.

### 23.1. Intentional delay vs unintended backlog

If the configured delay is 10 minutes, replay lag should not trigger normal catch-up alerts when policy calls for that delay. Dashboards must know each standby's role/purpose.

### 23.2. Receive can still stay close to the primary

A delayed standby can receive and flush WAL quickly while waiting before replaying. In that case receive/flush positions stay near the primary while replay position trails by the delay.

### 23.3. Delayed standbys do not replace backups

If primary and archive suffer the same failure or a standby is promoted prematurely, delay does not replace backups/WAL retention.

## 24. Recovery conflicts on the standby

A standby serves read-only queries while replaying WAL. Some replay operations can conflict with running queries.

Related parameters:
- `max_standby_streaming_delay`.
- `max_standby_archive_delay`.
- `hot_standby_feedback`.

### 24.1. max_standby_streaming_delay

Controls how long the standby can delay replay due to query conflicts when receiving WAL via streaming replication. Larger values help read queries finish while increasing replay lag.

### 24.2. Canceled queries

When replay must proceed and conflicts exceed wait limits, PostgreSQL cancels standby queries. Check logs and `pg_stat_database_conflicts`.

### 24.3. hot_standby_feedback

Sends `xmin` feedback to reduce some query cancellations from vacuum conflicts, at the cost of holding dead tuples longer on the primary and increasing bloat.

### 24.4. Balancing read workloads and replay freshness

A standby serving long analytics may require a different policy from a failover standby. Do not apply one setting blindly to every replica.

## 25. WAL sender/receiver timeouts and connections

Commonly involved settings:
- `wal_sender_timeout`.
- `wal_receiver_timeout`.
- `wal_receiver_status_interval`.
- `max_wal_senders`.
- `primary_conninfo`.

### 25.1. Timeout too low

Normal network jitter or brief storage pauses can repeatedly close connections. Tune timeouts against real network behavior.

### 25.2. Timeout too high

Connection failures take longer to detect, impacting failover RTO and alert responsiveness.

### 25.3. Receiver status interval

The standby sends periodic status updates. Changing this interval affects how often the primary receives acknowledgements/feedback; it does not directly speed up replay.

### 25.4. Checking connectivity and authentication

Inspect logs on both sides, SSL/certificates, `pg_hba`, DNS, firewalls, ports, passwords/roles, and replication slots.

## 26. WAL retention and lag

A lagging standby needs older WAL segments. The primary must retain enough WAL for the standby to continue.

Related mechanisms:
- Physical replication slots.
- `wal_keep_size`.
- `max_slot_wal_keep_size` on supported versions.
- WAL archives.
- `max_wal_size` and checkpoint/recycle behavior.

### 26.1. Replication slots

Slots retain WAL from `restart_lsn` needed by a consumer. They help standbys reconnect after brief outages yet can grow disk usage.

### 26.2. wal_keep_size

Retains a minimum amount of WAL for standbys without slots per configuration. It does not replace long-term archiving and does not guarantee infinite retention.

### 26.3. max_slot_wal_keep_size

Caps WAL retained by slots on supported versions. Once exceeded, the slot can become unusable and the standby/consumer must reinitialize or resync.

### 26.4. max_wal_size is not a hard quota

Never assume `pg_wal` is capped at `max_wal_size`. Slot retention, archive failures, and checkpoint behavior can push the WAL directory larger.

## 27. Measuring WAL retained distance per slot

Query:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS distance_from_current_bytes
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY distance_from_current_bytes DESC;
```

### 27.1. Not exact filesystem usage

LSN distance ignores segment rounding, WAL files pinned by other slots, or other internal retention reasons. Use it to rank slots with large retention distances.

### 27.2. Inactive slots need an owner

Identify the consumer, standby, or backup job owning the slot. Never drop a slot merely because `active = false`.

### 27.3. Alert on growth rate and disk headroom

A slot retaining 2 GB may be normal in a large cluster; adding 2 GB per minute on a disk with 5 GB free is critical. Track both trend and capacity.

## 28. Measuring replication lag with transaction markers

When you must know which business commits exist on a standby, insert periodic markers:

```sql
CREATE SCHEMA IF NOT EXISTS replication_test;

CREATE TABLE replication_test.marker (
    sequence_no bigint PRIMARY KEY,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

A test agent writes a marker, commits, and records the acknowledgement in an external witness after receiving `COMMIT` success.

On primary/standby:

```sql
SELECT
    max(sequence_no) AS latest_marker,
    max(committed_at) AS latest_marker_time
FROM replication_test.marker;
```

Compare the latest sequence across both nodes and the witness ledger.

### 28.1. Marker cadence

One marker per second gives finer resolution than one per minute, while creating more writes/WAL. Pick a cadence aligned with your RPO target and overhead.

### 28.2. Witness must be independent

If the witness lives in the same database or failure domain, it cannot prove whether acknowledged data was lost.

### 28.3. Record witness after commit

Never record a marker in the witness before the database confirms `COMMIT`. Otherwise measurements can count uncommitted transactions.

### 28.4. Markers are not a full correctness test

Markers measure the replication path. They do not prove every table, index, sequence, and business invariant synchronized properly.

## 29. Measuring time using pg_last_xact_replay_timestamp

On the standby:

```sql
SELECT
    pg_last_xact_replay_timestamp() AS last_replayed_xact,
    clock_timestamp()
      - pg_last_xact_replay_timestamp() AS age_since_last_replayed_xact;
```

This is the age of the last replayed transaction, not necessarily how long the standby is lagging.

### 29.1. Primary has no writes

Without new transactions, the timestamp grows older even when the standby is caught up, causing false alerts.

### 29.2. Primary has continuous writes

Under steady write traffic, this timestamp helps check replay freshness, though still compare it with primary commit/marker times and LSN positions.

### 29.3. Clocks must be synchronized

When comparing timestamps across different hosts, synchronize clocks. Use UTC and record clock sources/offsets when measuring RPO.

## 30. Measuring lag per standby

Never collapse multiple standbys into a single number. Example dashboard query:

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
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS replay_backlog_bytes,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
```

### 30.1. Failover standbys

Prioritize replay freshness, flush durability, connectivity, and promotion readiness.

### 30.2. Reporting standbys

Higher replay lag may be acceptable if query workloads are isolated and business freshness targets permit it.

### 30.3. Delayed standbys

Alerts must account for configured apply delays. Never compare them directly against failover standbys.

### 30.4. Quorum standbys

Identify which nodes participate in quorum and which are async only. Dashboards should distinguish durability roles.

## 31. Building a useful lag dashboard

A dashboard can include panels for:

1. WAL generation rate on the primary.
2. Sent/write/flush/replay LSN positions per standby.
3. Byte gaps for each queue.
4. `write_lag`, `flush_lag`, `replay_lag`.
5. `reply_time` age and connection state.
6. `pg_stat_wal_receiver` status/last message.
7. Replay rate and backlog slope.
8. Replication slot retained distance.
9. WAL directory disk usage.
10. Archive success/failure and archive freshness.
11. Standby query latency/conflicts.
12. Synchronous standby state.

### 31.1. Labels must be stable

Use cluster, primary, standby/`application_name`, region, role, and timeline. Do not rely solely on PID since PIDs change across restarts.

### 31.2. Distinguish NULL from 0

NULL lag means no sample/value exists in that context. 0 means a measured lag of zero. Dashboards should not silently convert NULL to 0 without noting it.

### 31.3. Include time-series panels

A single snapshot cannot show whether a backlog is growing or shrinking. Use time series to see slopes and correlations with workload.

## 32. Designing goal-oriented alerts

Never use one global threshold for every standby. Illustrative policy example:

| Alert | Sample trigger | Meaning |
|---|---|---|
| Connection down | State not `streaming` beyond threshold | WAL is not streaming continuously |
| Send backlog | `current_lsn - sent_lsn` rising continuously | Sender/network path |
| Write lag | `sent_lsn - write_lsn` rising | Receiver/write path |
| Flush lag | `write_lsn - flush_lsn` rising | Storage flush path |
| Replay lag | `flush_lsn - replay_lsn` rising | Recovery/apply path |
| Backlog growth | Generation rate > replay rate sustained | Standby is not catching up |
| Slot retention | Retained WAL nearing disk budget | Risk of `pg_wal` filling up |
| Archive failure | Failed count delta rising | PITR archive risk |
| Sync degradation | Synchronous standby no longer eligible | Commit durability/latency risk |

### 32.1. Use duration/persistence

A brief spike of a few seconds can be normal. Alert after thresholds persist for an appropriate duration, except for critical events like extended connection loss or nearly full disks.

### 32.2. Tie alerts to failure scenarios

30 seconds of lag may be fine for a reporting replica yet unacceptable for a failover tier requiring a 5-second RPO.

### 32.3. Separate warning and critical

Use warning for deteriorating trends; critical when RPO budgets, disk headroom, or failover readiness are about to be breached.

## 33. Runbook: standby replay lag increasing

1. Identify which standby and its workload/role.
2. Check `pg_stat_replication.state`, `sync_state`, `reply_time`.
3. Measure sent/write/flush/replay LSN gaps.
4. On the standby, inspect `pg_stat_wal_receiver`.
5. Compute WAL generation rate and replay rate over multiple samples.
6. Check recovery conflicts and `pg_stat_database_conflicts`.
7. Check CPU, storage latency, IOPS, and network.
8. Check `recovery_min_apply_delay`.
9. Check query/reporting workloads on the standby.
10. Inspect primary/standby logs.
11. Determine whether lag is shrinking, steady, or growing.
12. If the standby no longer has sufficient WAL, evaluate reinitializing/resyncing.
13. Update RPO/failover readiness status if the standby cannot be safely promoted.

### 33.1. Do not restart the standby immediately

Restarting may not fix the bottleneck and interrupts receiver/replay progress. Gather evidence first.

### 33.2. Do not promote a heavily lagging standby just because the primary is down

Assess last received/flushed/replayed WAL and acknowledged transaction evidence. Business owners must understand actual data loss if that node is chosen.

### 33.3. If replay is intentionally delayed

Confirm the policy and target delay. Another standby may need to be chosen for failover.

## 34. Runbook: high write/flush lag

### High write lag

- Check network RTT, packet loss, retransmits.
- Check sender/receiver CPU.
- Check connection resets.
- Check throughput and receiver scheduling.
- Check WAL bursts from batch workloads.

### High flush lag

- Check disk latency and `fsync`.
- Check IOPS/throughput throttling.
- Check volume queue depth.
- Check backup/checkpoint contention.
- Compare standbys on different storage classes.

### 34.1. Compare multiple standbys

If only one standby flushes slowly, the issue likely lies in that host/storage. If all standbys slow down together, inspect the primary sender/network or a shared WAL burst.

### 34.2. Do not add replay workers to fix flush

Replay workers do not fix storage flush bottlenecks. Target the action to the queue that is actually growing.

## 35. Runbook: interrupted replication connection

Check:
- Whether `pg_stat_replication` shows a row.
- Whether `pg_stat_wal_receiver` shows `streaming`.
- Primary/standby logs.
- DNS, routing, firewalls, TLS/certificates.
- Replication user/password and `pg_hba.conf`.
- WAL sender capacity.
- Replication slot validity.
- Whether the standby still has needed WAL or must fetch from the archive.

### 35.1. Slot invalidated

If the slot became unusable because WAL was recycled/capped by retention limits, the standby may need a new base backup or resync procedure. Never create a new slot and assume the gap vanished.

### 35.2. Archive fallback

If the standby has `restore_command` configured, it can retrieve WAL from the archive during recovery per workflow. Verify archive continuity.

### 35.3. Restored connection does not mean caught up

Once streaming reconnects, monitor the replay backlog and catch-up rate until targets are met.

## 36. Replay conflicts and reporting workloads

A standby serving long queries can conflict with WAL replay. `pg_stat_database_conflicts` tracks conflict counts per database.

Example:

```sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
```

Counters are cumulative since stats reset. Track deltas over time rather than absolute totals alone.

### 36.1. max_standby_streaming_delay

Larger values give queries more time while delaying replay longer. Choose according to the standby's freshness SLO.

### 36.2. hot_standby_feedback

Reduces query cancellations from vacuum conflicts, yet retains dead tuples longer on the primary and increases bloat. Monitor bloat/cleanup horizons.

### 36.3. Isolate standbys by workload

If long reporting queries cause lag on a failover standby, consider a dedicated replica or workload limits.

## 37. Impact of large transactions and WAL bursts

A large transaction can generate massive WAL, causing:
- Sender queues to grow.
- Network throughput to saturate.
- Standby flushes to slow down.
- Replay backlogs to build.
- Prolonged catch-up after the transaction finishes.

Other burst sources:
- Bulk loads.
- `CREATE INDEX`.
- Batch `UPDATE`/`DELETE`.
- Partition maintenance.
- Full-page images after checkpoints.
- Certain DDL operations.

### 37.1. Do not look only at average WAL rate

Track peak rates and burst durations. A system may fit within averages yet still choke during batch windows.

### 37.2. Batch operations when appropriate

Some batch updates can be split into smaller transactions to reduce peak pressure and lock duration, weighing transaction semantics and overhead.

### 37.3. Schedule backups and batches

Backups read heavily from storage while batches generate WAL; running them together can slow both primary and standby. Schedule based on measured capacity.

## 38. Targeted tuning

| Bottleneck | Investigation/tuning direction |
|---|---|
| Network | Throughput, RTT, packet loss, NIC, routing |
| WAL sender | CPU, sender count, socket waits, WAL bursts |
| Standby write | Receiver CPU, filesystem writes, storage |
| Standby flush | `fsync` latency, disk IOPS/throughput |
| Replay | CPU, read/write I/O, conflicts, apply delay |
| Query contention | Workload isolation, `max_standby` delays, feedback |
| Retention | Slots, `wal_keep_size`, archive, disk capacity |
| Connection churn | Timeouts, network, authentication, monitoring |

### 38.1. Do not change all settings at once

Change one hypothesis-driven group, measure before/after, and keep a rollback path. Changing many settings together hides which adjustment actually helped.

### 38.2. max_wal_senders

Ensure enough sender capacity for standby/backup clients. Raising it unnecessarily does not speed up the network or replay.

### 38.3. wal_compression

This parameter compresses full-page images inside WAL records where applicable; it is not compression of the entire streaming connection. Check version details and CPU trade-offs.

### 38.4. Do not tune from a single snapshot

Capture baselines across peak hours, batch windows, and idle periods. Verify changes do not degrade commit latency or storage.

## 39. Replication lag and synchronous commit latency

With synchronous replication, applications feel lag directly through `COMMIT` duration.

Monitor:
- Transaction commit latency.
- `synchronous_commit`.
- `synchronous_standby_names`.
- `sync_state`.
- `write_lag`/`flush_lag`/`replay_lag`.
- Network RTT and standby storage latency.

### 39.1. remote_write

Reduces latency compared to waiting for durable flush, though durability guarantees differ from `on`.

### 39.2. on

Waits for standby WAL flush. Common choice when synchronous durability to the standby is required.

### 39.3. remote_apply

Waits for standby replay. Useful for read-after-write on standbys while making commits depend on replay throughput.

### 39.4. Never lower synchronous_commit merely to mask lag

Weakening durability lowers commit latency while changing RPO/failure guarantees. Require business/architecture review and testing.

## 40. Replication lag and read-after-write consistency

Applications reading from a standby may miss a transaction just committed on the primary if the standby has not yet replayed the corresponding WAL.

Design patterns:
- Route transaction-sensitive reads to the primary.
- Wait for the standby to replay up to the transaction's LSN token before reading.
- Use `synchronous_commit = remote_apply` when requirements/costs justify it.
- Pin sessions to the primary during read-after-write windows.
- Use consistency tokens in the application layer.

### 40.1. Wait for LSN

Applications can fetch the post-commit LSN from the primary and wait for the standby to replay up to that position via an appropriate mechanism such as `pg_wait_for_replay_lsn` on supported versions.

Example on the standby:

```sql
SELECT pg_last_wal_replay_lsn();
```

Compare against the target LSN received from the primary. Wait function names/availability depend on version; check documentation.

### 40.2. Never rely on fixed sleeps

`pg_sleep(1)` does not guarantee replay reached the target. Waiting on an LSN/consistency token is far more reliable.

### 40.3. Read scaling has trade-offs

Reading from standbys offloads the primary yet can return stale data. Encode freshness requirements into routing policies.

## 41. Monitoring freshness for idle standbys

If the primary generates no WAL, time lag fields may be NULL and `pg_last_xact_replay_timestamp()` may look old. Distinguish idle from disconnected.

You can use:
- WAL sender connection state.
- `reply_time`.
- `pg_stat_wal_receiver.last_msg_receipt_time`.
- Controlled primary heartbeat/marker transactions.
- Network health.
- Slot/receiver state.

### 41.1. Heartbeat markers

Small periodic transactions produce freshness signals, yet generate WAL and must be accounted for in workload planning.

### 41.2. Do not run heartbeats overly frequently

Pick a cadence that meets freshness goals without creating unnecessary writes.

### 41.3. Connection state must still be checked

If there is no WAL activity yet the receiver connection dropped, the system is still degraded even though byte lag is not growing.

## 42. Multi-standby topologies

In a multi-standby system:
- One node may be synchronous.
- One node may be async in another region.
- One node may be delayed.
- One node serves reporting.
- One node is a cascading standby.

Dashboards must clearly record each node's role/purpose and WAL source.

### 42.1. Cascading replication

A standby can forward WAL to downstream standbys. Lag on downstream nodes includes upstream receive/replay plus downstream send/receive/replay.

### 42.2. Do not compare all LSNs as if on one hop

Document topology and timelines. Identify where each node receives WAL from.

### 42.3. Failover paths

If standby A is upstream of standby B, promoting A affects B. Runbooks must specify how to reparent/reconfigure downstream nodes.

## 43. Updating RPO/RTO from lag metrics

Lag metrics support operations but do not replace measuring actual RPO/RTO.

To update:
1. Define the failure scenario.
2. Record primary current LSN and standby sent/write/flush/replay positions.
3. Record `sync_state` and `synchronous_commit`.
4. Record acknowledged transaction markers.
5. Execute the failover drill per policy.
6. Compare the last marker on the old primary with the promoted standby.
7. Calculate actual RPO.
8. Measure time from incident start until the application is write-ready.
9. Calculate actual RTO.
10. Update runbooks and target feasibility.

### 43.1. Pre-incident lag is not actual loss

A standby with 10 MB of replay lag may have flushed enough WAL to avoid losing acknowledged commits if promotion/recovery uses the right WAL. Conversely, small time lag does not prove every transaction was durable.

### 43.2. Specify the failure model

Primary process crash, host loss, storage loss, and region loss have different durability assumptions.

### 43.3. Evidence must include timeline

Record timeline IDs, LSNs, marker sequences, and timestamps to reconstruct results accurately.

## 44. Common mistakes when measuring replication lag

### Mistake 1 — Collapsing write, flush, and replay into one number

Loses the ability to isolate the bottleneck.

### Mistake 2 — Treating write_lag as network latency

The metric also includes the standby write/acknowledgement path.

### Mistake 3 — Treating flush_lag as actual RPO

Actual RPO must compare acknowledged commits against recovered data.

### Mistake 4 — Treating replay_lag as catch-up ETA

It reflects recent WAL delay, not remaining catch-up time.

### Mistake 5 — Treating NULL as zero lag

NULL can mean no samples or no recent WAL activity.

### Mistake 6 — Treating an old replay timestamp as a broken standby

The primary may simply be idle.

### Mistake 7 — Treating byte lag as time lag

Converting requires WAL generation and replay rates.

### Mistake 8 — Treating state = streaming as healthy

A streaming connection can still have a large backlog.

### Mistake 9 — Assuming standby WAL receipt means replay finished

Receiver and recovery are two distinct processes/stages.

### Mistake 10 — Equating archive lag with streaming lag

They are two separate paths.

### Mistake 11 — Treating slot retained distance as exact disk usage

It is only an LSN distance estimate.

### Mistake 12 — Dropping inactive slots without checking owners

Can force consumers to resync from scratch.

### Mistake 13 — Raising max_wal_size to fix replay lag

This parameter does not accelerate replay.

### Mistake 14 — Raising max_wal_senders to fix the network

Sender slots do not add network bandwidth.

### Mistake 15 — Raising max_standby_streaming_delay without checking freshness

Queries get canceled less often while replay lag increases.

### Mistake 16 — Enabling hot_standby_feedback without watching primary bloat

Can retain dead tuples longer on the primary.

### Mistake 17 — Measuring only one standby

Standbys differ in role, storage, and network.

### Mistake 18 — Omitting timeline

After promotion, LSN comparisons can lose valid context.

### Mistake 19 — Taking only one snapshot

Cannot tell whether the backlog is growing or shrinking.

### Mistake 20 — Not verifying transaction markers

Lacks business-level proof comparing confirmed data against recovered data.

## 45. Practice exercises with answers

### Exercise 1. What is write lag?

**Answer:** Elapsed time from recent primary WAL flush until the primary receives acknowledgement that the standby wrote that WAL.

### Exercise 2. What is flush lag?

**Answer:** Elapsed time until the primary receives acknowledgement that the standby flushed the corresponding WAL.

### Exercise 3. What is replay lag?

**Answer:** Elapsed time until the primary receives acknowledgement that the standby replayed the corresponding WAL.

### Exercise 4. Does high write lag prove a slow network?

**Answer:** No. Inspect network, receiver, CPU, and standby write path together.

### Exercise 5. What do low write lag and high flush lag suggest?

**Answer:** WAL is written quickly yet storage flushing is slow; inspect disk/`fsync` latency.

### Exercise 6. What do low flush lag and high replay lag suggest?

**Answer:** WAL is flushed yet recovery cannot replay fast enough; inspect replay throughput/conflicts.

### Exercise 7. How does sent LSN differ from replay LSN?

**Answer:** Sent is the WAL position transmitted; replay is the WAL position applied by the standby.

### Exercise 8. Is an LSN a timestamp?

**Answer:** No. An LSN is a position in the WAL stream.

### Exercise 9. Which function computes byte distance between two LSNs?

**Answer:** `pg_wal_lsn_diff`.

### Exercise 10. Where is pg_stat_replication queried?

**Answer:** On the primary/WAL sender server; each row typically represents one connected standby.

### Exercise 11. Where is pg_stat_wal_receiver queried?

**Answer:** On a standby receiving WAL via streaming replication.

### Exercise 12. Does state = streaming prove replay has zero lag?

**Answer:** No. Inspect LSN positions, replay backlogs, and rates.

### Exercise 13. What does NULL replay_lag mean?

**Answer:** There may be no recent WAL sample to compute it; it does not automatically mean zero or failure.

### Exercise 14. Why can pg_last_xact_replay_timestamp() appear old?

**Answer:** The primary has no new transactions; the timestamp does not advance while idle.

### Exercise 15. Does byte lag convert directly to seconds?

**Answer:** No. You need WAL generation and replay rates.

### Exercise 16. What is the WAL generation rate formula?

**Answer:** Current LSN difference between two samples divided by elapsed seconds.

### Exercise 17. What is the replay rate formula?

**Answer:** Replay LSN difference between two samples divided by elapsed seconds.

### Exercise 18. Replay rate 40 MB/s, WAL generation 25 MB/s; what is the net catch-up rate?

**Answer:** 15 MB/s, assuming rates hold steady.

### Exercise 19. Backlog 600 MB, net catch-up 20 MB/s; what is the approximate ETA?

**Answer:** 30 seconds, as an estimate under steady conditions.

### Exercise 20. If replay rate is lower than generation rate, will the standby catch up?

**Answer:** Not under those conditions; the backlog will grow.

### Exercise 21. Is write_lag an ETA?

**Answer:** No. It reflects acknowledgement delay for recent WAL.

### Exercise 22. Is flush_lag actual RPO?

**Answer:** No. Actual RPO requires comparing acknowledged commits against recovered data.

### Exercise 23. Are archive lag and streaming lag the same?

**Answer:** No. One path saves WAL to an archive; the other streams WAL to standbys.

### Exercise 24. Can an inactive slot retain WAL?

**Answer:** Yes. A slot can hold `restart_lsn`/`xmin` and grow retained resources.

### Exercise 25. What is restart_lsn used for?

**Answer:** Indicates the oldest WAL position a replication slot may still need.

### Exercise 26. Is the LSN distance to restart_lsn exact disk usage?

**Answer:** No. It is a WAL distance and ignores segment boundaries and other retention factors.

### Exercise 27. What does synchronous_commit = on wait for?

**Answer:** With synchronous replication, waits for the standby to durably flush WAL per PostgreSQL semantics.

### Exercise 28. Is remote_write equivalent to durable flush?

**Answer:** No. It waits for the standby to write WAL to the OS, not durable storage flush.

### Exercise 29. How does remote_apply differ from on?

**Answer:** `remote_apply` waits for the standby to replay WAL, whereas `on` waits for WAL flush.

### Exercise 30. What does sync_state show?

**Answer:** Whether the standby is `async`, `potential`, `sync`, or `quorum` per configuration/version.

### Exercise 31. What can recovery_min_apply_delay cause?

**Answer:** Intentional replay lag on a standby.

### Exercise 32. Why can reporting queries slow down replay?

**Answer:** Recovery conflicts can force replay to wait or cancel queries depending on configuration.

### Exercise 33. What is the trade-off of hot_standby_feedback?

**Answer:** Can reduce query cancellations while holding dead tuples longer on the primary.

### Exercise 34. Is max_wal_size a hard limit on pg_wal?

**Answer:** No. Slot retention/archive failures can push WAL usage above it.

### Exercise 35. Why shouldn't you raise max_wal_senders to fix replay lag?

**Answer:** Sender count does not make the recovery process replay faster.

### Exercise 36. What does pg_stat_database_conflicts report?

**Answer:** Counters of recovery conflicts on a standby; inspect deltas over time.

### Exercise 37. When a standby receives WAL fast yet replay stalls, what should you check?

**Answer:** Replay process, conflicts, apply delay, CPU/I/O, and query workloads.

### Exercise 38. When the sent-to-write gap grows, what should you check?

**Answer:** Network, receiver, CPU, and write path.

### Exercise 39. When the write-to-flush gap grows, what should you check?

**Answer:** Storage latency, `fsync`, IOPS, and disk queues.

### Exercise 40. When the flush-to-replay gap grows, what should you check?

**Answer:** Replay throughput, recovery conflicts, apply delay, and standby workload.

### Exercise 41. Why monitor each standby individually?

**Answer:** Each node has different roles, storage, network, and sync policies.

### Exercise 42. Can a standby be streaming yet unsuitable to promote?

**Answer:** Yes. It might lag heavily or lack required acknowledged commits.

### Exercise 43. How do you measure acknowledged data loss in a failover drill?

**Answer:** Use transaction markers recorded in an external witness after `COMMIT` and compare against markers on the promoted standby.

### Exercise 44. Why must the marker witness be independent?

**Answer:** So it does not fail inside the database's failure domain.

### Exercise 45. What is the impact of overly frequent heartbeat markers?

**Answer:** Generates extra writes/WAL and can alter workload characteristics.

### Exercise 46. Why record timeline when comparing LSNs?

**Answer:** Promotion starts a new WAL history branch; you must know which timeline an LSN belongs to.

### Exercise 47. Is one lag measurement enough to establish a trend?

**Answer:** No. Multiple samples over time are needed to compute backlog slopes and rates.

### Exercise 48. Replay lag rises during batch hours then drops afterward; how should you handle it?

**Answer:** Measure peak WAL rate, replay capacity, and catch-up time; adjust batch sizing or standby capacity if freshness targets are breached.

### Exercise 49. Can RPO/RTO be inferred solely from lag fields?

**Answer:** No. Failover/PITR drills and measuring actual acknowledged transactions plus service-ready time are required.

### Exercise 50. What should a good replication lag dashboard include?

**Answer:** LSN positions, byte gaps, time lags, generation/replay rates, connection state, receiver status, slot retention, archive health, and role/timeline.

## 46. Replication lag investigation checklist

| Stage | Question |
|---|---|
| Identification | Which primary and standby are being measured? |
| Identification | Is the standby for failover, reporting, delayed, or quorum? |
| Connection | Is `state` `streaming`? |
| Connection | Are `reply_time` and receiver last message recent? |
| Sender | Is `current_lsn - sent_lsn` growing? |
| Receiver/write | Is `sent_lsn - write_lsn` growing? |
| Flush | Is `write_lsn - flush_lsn` growing? |
| Replay | Is `flush_lsn - replay_lsn` growing? |
| Time | Are `write_lag`/`flush_lag`/`replay_lag` NULL or populated? |
| Trend | Is the backlog growing, steady, or shrinking? |
| Rate | How does WAL generation rate compare to replay rate? |
| Storage | Are IOPS, `fsync` latency, or throughput saturated? |
| Network | What are RTT, packet loss, retransmits, and throughput? |
| Replay | Are there recovery conflicts or apply delays? |
| Retention | How much LSN distance is retained by slots? |
| Archive | Are there WAL archive failures/gaps? |
| Durability | Which standbys are actually synchronous? |
| Application | Are commit latency or read freshness impacted? |
| Recovery | Does the standby have enough WAL and is it safe to promote? |
| Post-action | Is lag trending down and meeting SLOs? |
| Evidence | Are LSNs, timelines, markers, and timestamps saved? |

## 47. Official PostgreSQL documentation

- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_replication`, `pg_stat_wal_receiver`, activity, and replication statistics.
- [Warm Standby / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — physical streaming replication and standby behavior.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — `synchronous_commit` and acknowledgement levels.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — sender, receiver, slots, and replication settings.
- [Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET) — recovery delay/settings.
- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html) — read-only standby, conflicts, and feedback.
- [System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html) — LSN/recovery functions.
- [pg_stat_replication](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW) — sender/standby positions and lag fields.
- [pg_stat_wal_receiver](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-WAL-RECEIVER-VIEW) — receiver status and LSN positions.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — retained WAL and slot status.
- [pg_stat_database_conflicts](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-DATABASE-CONFLICTS-VIEW) — recovery conflict counters.

View columns, wait events, and replication settings can vary across PostgreSQL major versions. Before deploying queries to production monitoring, check `server_version`, `pg_settings`, view definitions, and documentation matching your running version.

## 48. Summary: measure each stage accurately, find the true bottleneck

```text
Primary WAL generation
        |
        v
   sent_lsn
        |
        v
   write_lsn       -> write path
        |
        v
   flush_lsn       -> durable storage path
        |
        v
   replay_lsn      -> recovery/apply path
        |
        v
   Standby visible state

Time lag: write_lag / flush_lag / replay_lag
Byte lag:  LSN differences
Trend:     WAL generation rate vs replay rate
Proof:     transaction markers + failover drill
```

Principles to remember:

1. **Write, flush, and replay are three distinct milestones.** Read each metric to locate where a queue is building.
2. **LSN gaps measure WAL distance in bytes.** They do not convert directly into time.
3. **Time lag fields describe recent WAL delay.** They are neither catch-up ETAs nor actual RPO.
4. **NULL does not mean zero.** When the primary is idle, lag time fields may lack fresh samples.
5. **The receiver receives WAL; recovery replays WAL.** The two processes can advance at different speeds.
6. **WAL generation rate must be compared against replay rate.** Backlogs shrink only when replay throughput exceeds incoming WAL rate.
7. **Archive lag, streaming lag, and slot retention are three separate concerns.** Dashboards must track them separately.
8. **Synchronous commit alters durability and commit latency.** Understand `remote_write`, `on`, and `remote_apply` before tuning.
9. **Recovery conflicts and apply delays can intentionally slow replay.** Account for standby role before alerting.
10. **Never promote solely because a standby is streaming.** Verify LSN, timeline, acknowledged commits, and fencing.
11. **Transaction markers provide better business-level evidence than a single lag field.** Use an external witness in drills.
12. **Track trends and keep evidence.** One snapshot cannot tell whether a standby is catching up.

**One sentence to remember:** *Replication lag is only diagnosed accurately when you know whether WAL is queued at sending, writing, flushing, or replaying; measure LSNs, rates, and transaction evidence together before concluding whether a standby is fresh enough for reads or failover.*
