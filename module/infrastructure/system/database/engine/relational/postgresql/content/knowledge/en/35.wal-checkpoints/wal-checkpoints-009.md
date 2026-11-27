# Rapid WAL Growth, Frequent Checkpoints, and I/O Impact

PostgreSQL writes the **Write-Ahead Log (WAL)** before changes on data pages are considered durable. WAL enables crash recovery, replication, and point-in-time recovery. The **checkpoint** mechanism periodically syncs required dirty buffers down to data files and records an appropriate starting point for crash recovery.

When write workloads increase, WAL can be generated very quickly. If PostgreSQL has to checkpoint too frequently, the checkpointer generates extra bursts of data page writes, drives up I/O, competes with queries, and can trigger many full-page images in WAL. If WAL is retained too long because archiving or a replication slot lags, the `pg_wal` directory can grow even while checkpoints continue running. These two phenomena are related yet distinct: **WAL generation** is the rate of creating logs; **WAL retention** is the amount of log not yet eligible for recycling.

This lesson explains how WAL and checkpoints interact, why frequent checkpoints hurt performance, how to read metrics, and how to tune safely. The goal is not to minimize WAL at all costs. WAL is the foundation of durability and recovery; the goal is to generate only the WAL the workload needs, checkpoint at an appropriate cadence, keep I/O steady, and ensure WAL is archived, replicated, and recycled on time.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain WAL and the write-ahead principle.
2. Distinguish WAL generation, WAL flush, WAL write, WAL archiving, and WAL retention.
3. Describe checkpoints, dirty buffers, redo points, and crash recovery.
4. Distinguish timed checkpoints from requested checkpoints.
5. Explain the roles of `max_wal_size`, `min_wal_size`, `checkpoint_timeout`, and `checkpoint_completion_target`.
6. Understand full-page images (FPIs), `full_page_writes`, and their impact on WAL volume.
7. Distinguish the checkpointer, background writer, and backend writes.
8. Read metrics from `pg_stat_wal`, checkpoint statistics, `pg_stat_archiver`, and replication slots.
9. Monitor WAL generation rate, checkpoint frequency, checkpoint write/sync times, and storage latency.
10. Separate checkpoint pressure from WAL retention caused by archive/replication backlogs.
11. Tune checkpoint/WAL settings based on measurements and recovery objectives.
12. Handle rapid WAL growth, frequent checkpoints, slow archiving, replica lag, or nearly full disks.

> **PostgreSQL version note:** Checkpoint statistics views changed in PostgreSQL 17. This lesson separates examples by version: PostgreSQL 16 and earlier vs. PostgreSQL 17 and later. Always check view schemas and settings on your actual major version before relying on static dashboards or SQL queries.

## 2. What Is WAL?

The **Write-Ahead Log** is a stream of records describing the changes PostgreSQL needs to recover the database. Whenever a transaction modifies a row, index, or page metadata, PostgreSQL writes corresponding WAL records.

The write-ahead principle:

```text
1. Write WAL describing the change.
2. Ensure required WAL is durably flushed per durability semantics.
3. Data pages may then be written to data files.
```

WAL lets PostgreSQL avoid syncing every data page at transaction commit. Instead, transaction commits only wait for WAL flush; data pages are written out gradually by background processes and the checkpointer.

### Why Not Write Only Data Files?

If the server crashes mid-write of a page, a data page can end up half-written or holding partial changes. WAL supplies enough history to replay required changes after a crash, within the limits of recovery configuration.

### What Does WAL Contain?

WAL records can describe:

- Heap tuple changes.
- Index page changes.
- Page initialization and metadata changes.
- Transaction commit/abort records.
- Full-page images when torn-page protection is needed.
- Other system changes required for recovery and replication.

One SQL statement does not map one-to-one to a single WAL record. A statement can emit many records, and one record can involve multiple internal operations.

## 3. WAL and Transaction COMMIT

A transaction modifying data:

```text
BEGIN
  UPDATE rows
  INSERT index entries
  DELETE old versions
COMMIT
  ↓
WAL records already generated
  ↓
WAL flushed per synchronous_commit / durability policy
  ↓
COMMIT confirmed to client
  ↓
Data pages can be written out later
```

Under the common default configuration, `synchronous_commit=on` makes commits wait for local WAL flush on the primary. If synchronous replication is configured, waiting can also depend on replica acknowledgement and `synchronous_standby_names`.

### WAL Flush Is Not a Checkpoint

This distinction is essential:

- **WAL flush:** ensures the required portion of WAL is durably written per the transaction's policy.
- **Checkpoint:** syncs required data pages and establishes a new recovery point.

A transaction can already be durably committed even though its data pages have not yet been written to data files; crash recovery uses WAL to complete them.

## 4. WAL Generation, Write, Flush, and Archiving

Common terms:

| Concept | Meaning |
|---|---|
| WAL generation | Rate at which PostgreSQL creates WAL records |
| WAL write | WAL bytes transferred from buffers to OS/files |
| WAL flush | WAL flushed to durable storage per server semantics |
| WAL archive | WAL segments copied to an archive destination |
| WAL replay | Standby/recovery reading and applying WAL |
| WAL retention | Old WAL not yet eligible for recycling/deletion because archiving, replication, or recovery still needs it |

### An Example

The primary generates 200 GB of WAL per hour. The archive destination accepts only 100 GB per hour. As the backlog grows, WAL segments remain pinned in `pg_wal`; disk usage rises even though checkpoints keep running.

### Do Not Confuse WAL Archiving with WAL Flushing

Transaction commits do not wait for `archive_command` to copy segments unless custom external tooling enforces that. Archiving retains WAL for backup/PITR independently of normal commit flushes.

## 5. WAL Segments and the pg_wal Directory

WAL is stored in **segment files** inside the `pg_wal` directory. The default segment size is commonly 16 MB, though it can be chosen at cluster initialization.

Segments are named using timeline/log/segment identifiers. PostgreSQL can:

- Create new segments as needed.
- Recycle old segments by renaming them for reuse.
- Delete segments no longer needed.
- Retain segments due to archiving, replication slots, or `wal_keep_size`.

### Why Does the File Count in pg_wal Not Depend Only on WAL Generation?

`pg_wal` disk usage depends on all of:

- WAL creation rate.
- Checkpoints and recycling policies.
- `min_wal_size` / `max_wal_size`.
- Archive backlogs.
- Replication slots and `restart_lsn`.
- `wal_keep_size`.
- Recovery/standby requirements.

`max_wal_size` is a soft target to schedule checkpoints, **not a hard quota guaranteeing pg_wal will never exceed that size**.

## 6. What Is a Checkpoint?

A checkpoint is a milestone in the WAL/recovery process where PostgreSQL ensures required data pages prior to the checkpoint have been written to data files. The checkpoint record stores metadata needed for crash recovery, including the appropriate redo point.

Conceptually:

```text
Dirty buffers in shared_buffers
       ↓
Checkpointer writes required data pages
       ↓
Flush/sync data files per checkpoint protocol
       ↓
Write checkpoint record and update control metadata
       ↓
Crash recovery can start from the new redo point
```

### Why Are Checkpoints Needed?

If recovery relied solely on WAL from database creation, crash recovery would have to replay huge volumes of WAL. Checkpoints create fresh recovery starting points, bounding how much WAL normal crash recovery must replay.

A checkpoint does not mean all WAL prior to the checkpoint can be deleted right away. Archiving, replication slots, standbys, and backup/PITR may still need older WAL segments.

## 7. What Are Dirty Buffers?

PostgreSQL caches data pages in `shared_buffers`. When a page is modified, that page becomes a **dirty buffer** until written back out to data files.

Example:

1. UPDATE a row on a heap page.
2. PostgreSQL modifies the page in shared buffers and emits WAL.
3. The transaction commits after WAL flushes.
4. The heap page can remain dirty in shared buffers.
5. Checkpointer, background writer, or a backend writes the page to storage.

### Why Not Flush Data Pages on Every COMMIT?

One page can be updated many times by many transactions. Writing data pages on every commit would cause heavy random writes and high latency. WAL lets PostgreSQL coalesce data page writes and flush them via buffer management and checkpoint scheduling.

### WAL-Before-Data

Before a data page is durably written, its corresponding WAL must be flushed through the required position. This protects redo capability if the data page write is torn.

## 8. Timed Checkpoints vs. Requested Checkpoints

PostgreSQL initiates checkpoints for two main categories of reasons:

**Timed checkpoint:** the `checkpoint_timeout` interval elapsed.

**Requested checkpoint:** WAL generated since the previous checkpoint exceeded the threshold derived from `max_wal_size`, or an explicit manual/administrative checkpoint was requested.

### Why Do Requested Checkpoints Matter?

If a workload generates WAL rapidly, `max_wal_size` may be hit before `checkpoint_timeout`. PostgreSQL must checkpoint earlier than scheduled. If this repeats, checkpoint frequency climbs, data write I/O intensifies, and FPIs can surge.

### Not All Requested Checkpoints Come from WAL Rate

Manual `CHECKPOINT` commands and certain administrative/recovery operations also trigger requested checkpoints. When analyzing metrics, correlate logs and system activity to confirm the cause.

## 9. max_wal_size and min_wal_size

`max_wal_size` controls how much WAL is allowed to accumulate before PostgreSQL requests an early checkpoint. It is a **soft limit**:

- WAL generation spikes can push past the target before a checkpoint completes.
- Archives or replication slots can pin segments against recycling.
- `wal_keep_size` can retain extra WAL for standbys.
- Certain recovery/backup scenarios retain WAL longer.

`min_wal_size` is the minimum WAL volume PostgreSQL tries to retain/recycle to avoid continually creating and deleting segment files as workloads fluctuate.

### Viewing Settings

```sql
SHOW min_wal_size;
SHOW max_wal_size;
```

Illustrative configuration example:

```text
min_wal_size = 2GB
max_wal_size = 16GB
```

These values are not recommendations for every server. Size them according to WAL generation rate, disk headroom, checkpoint duration, recovery time objective, and archive/replication requirements.

## 10. checkpoint_timeout

`checkpoint_timeout` is the maximum time interval between automatic time-based checkpoints.

```sql
SHOW checkpoint_timeout;
```

If `checkpoint_timeout` is short:

- Timed checkpoints happen more frequently.
- Data pages are written more frequently.
- Recovery generally has less WAL to replay from the latest checkpoint.

If `checkpoint_timeout` is long:

- Timed checkpoint frequency drops.
- More WAL may need to be retained and replayed during crash recovery.
- Dirty buffers can accumulate longer before checkpointing.
- Requested checkpoints can still happen early if `max_wal_size` is hit.

### Raising checkpoint_timeout Alone Is Not Always Enough

If `max_wal_size` is too small for the WAL generation rate, requested checkpoints will still happen frequently. Inspect both checkpoint reasons and WAL generation.

## 11. checkpoint_completion_target

`checkpoint_completion_target` controls the fraction of the checkpoint interval over which data page writes are spread, rather than dumping writes in a short burst.

For example, 0.9 means PostgreSQL tries to pace checkpoint writes across most of the allowed checkpoint interval according to its scheduling algorithm.

```sql
SHOW checkpoint_completion_target;
```

### Impact

- Higher targets spread checkpoint writes more evenly.
- Reduces the chance of a short, intense write burst.
- Smooths I/O load during checkpoints.
- Checkpoints must still finish; if storage cannot keep up, checkpoints can overrun the schedule.

### Not an Absolute Throttle

`checkpoint_completion_target` does not throttle all database writes. Backends, the background writer, the WAL writer, and other processes can still generate I/O outside checkpoint scheduling.

## 12. Full-Page Images (FPI)

With `full_page_writes=on`, PostgreSQL writes a **full-page image** of a page into WAL on the first modification to that page after a checkpoint. This protects against torn-page writes: if a page is only partially written during a crash, recovery restores the full page image before replaying subsequent WAL records.

### Example

After a checkpoint:

1. Page P has not been modified yet.
2. The first transaction modifies P.
3. PostgreSQL logs an FPI of P into WAL.
4. Subsequent changes to P in the same cycle can log smaller delta WAL records until the next checkpoint resets the state.

### Why Can Frequent Checkpoints Inflate WAL Even Further?

Frequent checkpoints cause the "first modification after checkpoint" window to recur much more often. On workloads touching many pages, FPI volume can climb dramatically. Thus overly frequent checkpoints can drive up both data-page write I/O and WAL generation.

## 13. full_page_writes and wal_compression

Check:

```sql
SHOW full_page_writes;
SHOW wal_compression;
SHOW wal_level;
```

### full_page_writes

Normally keep this enabled to protect against torn-page writes. Turning it off can cut WAL volume in some workloads, yet increases corruption risk after a crash or storage failure. Never disable it just to reduce disk I/O.

### wal_compression

`wal_compression` compresses full-page images inside WAL, reducing bytes written when FPIs are large. In return, the server spends extra CPU compressing and decompressing. Effectiveness depends on data/page patterns and algorithms supported by your version.

### WAL Level

`wal_level` determines how much WAL information is logged for standbys, replication, and logical decoding. `logical` can log more info than `replica` to support logical decoding; never lower `wal_level` if your replication, CDC, or backup architecture requires the current level.

## 14. Why Can FPIs Cause Write Amplification?

Suppose a workload modifies 100,000 heap pages during each checkpoint cycle. With `full_page_writes` enabled, the first modification to each page after a checkpoint emits a full-page image. At an 8 KB page size, theoretical raw FPI volume can reach hundreds of MB per cycle before compression and other WAL records.

### Contributing Factors

- Number of distinct pages touched after a checkpoint.
- Checkpoint frequency.
- Page size and tuple/page layout.
- `full_page_writes` and `wal_compression`.
- Workload update pattern: hot pages vs. widely scattered touches.
- Operations like index builds, bulk loads, and page initializations.

A workload updating a small hot set of pages repeatedly produces a very different FPI profile than a workload randomly touching millions of pages, even with the exact same number of updated rows.

### Viewing FPI Counts

The `pg_stat_wal` view exposes `wal_fpi` on supported PostgreSQL versions:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

`wal_fpi` counts full-page images written to WAL; compute deltas over time to understand trends.

## 15. Checkpointer, Background Writer, and Backend Writes

Three processes write dirty data buffers:

**Checkpointer:** writes dirty buffers as part of the checkpoint process to establish recovery points.

**Background writer (bgwriter):** proactively writes some dirty buffers to maintain a pool of clean buffers, reducing how often backends must write pages themselves when allocating buffers.

**Backend processes:** query/transaction backends may have to write dirty buffers themselves when they need a free buffer and bgwriter has not prepared one in time.

### Different Goals

| Process | Goal |
|---|---|
| Checkpointer | Complete checkpoints, sync pages required for recovery |
| Background writer | Maintain clean buffer pool, smooth buffer allocations |
| Backend | Execute queries/updates; occasionally forced to write a buffer to proceed |

Do not confuse the background writer with the checkpointer. Tuning bgwriter up does not replace checkpoints, and checkpoints are not simply "bgwriter running harder."

## 16. How Do Checkpoints Generate I/O?

A checkpoint can:

1. Identify dirty buffers needing writes.
2. Pace write requests per checkpoint scheduling.
3. Write data pages out to data files.
4. Sync required files per the checkpoint protocol.
5. Finalize checkpoint metadata and the WAL checkpoint record.

### Two Timing Components

Checkpoint statistics typically report:

- **write time:** time the checkpointer spent writing buffers.
- **sync time:** time spent syncing files to storage.

High write time indicates the checkpointer is writing many pages or storage write throughput is low. High sync time points to fsync or storage flush latency issues.

### Why Do Checkpoint Spikes Slow Down Queries?

Checkpoint writes share storage bandwidth with foreground queries, WAL writes, autovacuum, index builds, and replication/backup reads. When device queues lengthen or IOPS/throughput saturates, query reads and writes suffer higher latency even when SQL plans have not changed.

## 17. checkpoint_completion_target and I/O Smoothing

Illustrative example:

```text
checkpoint interval ~ 5 minutes

target 0.5:
  tries to spread most writes across ~2.5 minutes

target 0.9:
  tries to spread writes across ~4.5 minutes
```

This is a conceptual visualization, not an exact timer promise. Checkpoint scheduling adapts based on buffer/dirty-page counts, prior timings, and workload.

### If Target Is Too Low

Writes concentrate tightly, producing larger bursts and spiking storage latency over a short window.

### If Target Is Too High

The checkpointer spreads work across nearly the entire checkpoint interval. If the next checkpoint arrives early or storage lacks throughput, checkpoint loads can overlap and create pressure. PostgreSQL prevents checkpoint writes from stretching indefinitely without limit.

A common default in modern PostgreSQL versions is 0.9; always check `SHOW` rather than relying on memory.

## 18. checkpoint_timeout and max_wal_size Working Together

These two settings define two distinct boundaries:

- `checkpoint_timeout` triggers checkpoints based on elapsed time.
- `max_wal_size` creates requested-checkpoint pressure when accumulated WAL exceeds the target.

Example:

```text
checkpoint_timeout = 5 min
max_wal_size = 1 GB
WAL generation = 500 MB/min

The WAL threshold may be hit after ~2 minutes,
before the 5-minute timed checkpoint arrives.
```

This simplified example ignores overhead and WAL recycling nuances. It illustrates why raising `checkpoint_timeout` has no effect if the WAL threshold keeps triggering early.

### How to Reason About Them

First measure WAL bytes/second and checkpoint counts. Then choose `max_wal_size` large enough to avoid frequent requested checkpoints under normal load while preserving disk headroom and recovery objectives.

## 19. WAL Generation Rate

To measure how fast WAL is growing, compute **delta WAL bytes over a time interval**:

\[
\text{WAL rate}
= \frac{\Delta \text{wal\_bytes}}{\Delta t}
\]

Example:

```text
WAL bytes at 10:00 = 80 GB
WAL bytes at 10:05 = 92 GB

Delta = 12 GB / 300 seconds
Rate = 40 MB/s
```

These example figures use decimal units. On dashboards, clearly specify MB/s vs. MiB/s.

### Notes

- `pg_stat_wal` counters are cumulative since stats reset.
- If statistics reset between two samples, the delta will be negative or invalid.
- Compare two samples with clear timestamps.
- Do not divide current `wal_bytes` by uptime when trying to catch short bursts.

## 20. Measuring WAL Rate with pg_stat_wal

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

Capture results at two timestamps and compute deltas:

| Metric | Meaning |
|---|---|
| wal_records | Count of WAL records |
| wal_fpi | Count of full-page images |
| wal_bytes | Total WAL bytes generated |
| wal_buffers_full | Times WAL buffers filled up, forcing processes to assist flushing WAL buffers |
| stats_reset | Timestamp of statistics reset |

### wal_buffers_full

If this counter climbs rapidly, the workload is producing WAL faster than WAL buffers are drained/flushed. Do not blindly jump to increasing `wal_buffers`; inspect WAL write/flush latency, commit rates, storage, and workload first.

## 21. Measuring WAL Rate via LSN

Another approach is sampling LSNs at two timestamps:

```sql
SELECT pg_current_wal_lsn();
```

Then compute the difference:

```sql
SELECT pg_size_pretty(
    pg_wal_lsn_diff(
        '0/90000000'::pg_lsn,
        '0/80000000'::pg_lsn
    )::bigint
) AS wal_generated;
```

The LSNs in the example are hypothetical values illustrating subtraction; in operations, pass two real samples in newest-minus-oldest order.

### WAL Bytes vs. LSN Distance

LSN distance measures bytes in the WAL address space between two positions; `pg_stat_wal.wal_bytes` measures WAL bytes recorded by statistics. Both are useful in different ways and can differ slightly due to segment padding, timeline/restart context, and sampling alignment.

## 22. Measuring Checkpoint Statistics on PostgreSQL 16 and Earlier

In PostgreSQL 16 and earlier versions, many checkpoint metrics reside in `pg_stat_bgwriter`:

```sql
SELECT
    checkpoints_timed,
    checkpoints_req,
    checkpoint_write_time,
    checkpoint_sync_time,
    buffers_checkpoint,
    buffers_clean,
    maxwritten_clean,
    buffers_backend,
    buffers_backend_fsync,
    buffers_alloc,
    stats_reset
FROM pg_catalog.pg_stat_bgwriter;
```

### Interpretation

- `checkpoints_timed`: count of timed checkpoints.
- `checkpoints_req`: count of requested checkpoints.
- `checkpoint_write_time`: total time spent writing checkpoint buffers (milliseconds).
- `checkpoint_sync_time`: total time spent syncing checkpoint files (milliseconds).
- `buffers_checkpoint`: buffers written by the checkpointer.
- `buffers_clean`: buffers written by the background writer.
- `maxwritten_clean`: times bgwriter stopped due to hitting its per-round page limit.
- `buffers_backend`: buffers written directly by backends.
- `buffers_backend_fsync`: times a backend had to execute fsync itself.
- `buffers_alloc`: buffers allocated.

These counters are cumulative; compute deltas over time intervals and divide by elapsed time to get rates.

## 23. Measuring Checkpoint Statistics on PostgreSQL 17 and Later

Starting in PostgreSQL 17, checkpoint statistics moved to `pg_stat_checkpointer`, while `pg_stat_bgwriter` focuses on the background writer. On newer servers:

```sql
SELECT
    num_timed,
    num_requested,
    restartpoints_timed,
    restartpoints_req,
    restartpoints_done,
    write_time,
    sync_time,
    buffers_written,
    stats_reset
FROM pg_catalog.pg_stat_checkpointer;
```

And the background writer:

```sql
SELECT
    buffers_clean,
    maxwritten_clean,
    buffers_alloc,
    stats_reset
FROM pg_catalog.pg_stat_bgwriter;
```

### Do Not Run Queries for the Wrong Version

Columns like `checkpoints_timed`/`checkpoints_req` and `checkpoint_write_time`/`checkpoint_sync_time` are no longer in `pg_stat_bgwriter` in PG17 as they were previously. Dashboards must run version-specific queries per major version.

If a column is missing, inspect the schema:

```sql
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name IN (
      'pg_stat_checkpointer',
      'pg_stat_bgwriter',
      'pg_stat_wal'
  )
ORDER BY table_name, ordinal_position;
```

## 24. Checkpoint Frequency and Requested Checkpoint Ratio

On PostgreSQL 16 and earlier:

```sql
SELECT
    checkpoints_timed,
    checkpoints_req,
    round(
        100.0 * checkpoints_req
        / NULLIF(checkpoints_timed + checkpoints_req, 0),
        2
    ) AS requested_pct
FROM pg_catalog.pg_stat_bgwriter;
```

On PostgreSQL 17 and later:

```sql
SELECT
    num_timed,
    num_requested,
    round(
        100.0 * num_requested
        / NULLIF(num_timed + num_requested, 0),
        2
    ) AS requested_pct
FROM pg_catalog.pg_stat_checkpointer;
```

### Interpretation

A high share of requested checkpoints can indicate WAL generation is hitting `max_wal_size` ahead of the timed schedule. However, also factor in manual checkpoints and special maintenance events; a percentage alone does not prove misconfiguration.

More important are deltas per minute, checkpoint duration, and impact on I/O and latency.

## 25. Checkpoint Logging

Settings:

```sql
SHOW log_checkpoints;
SHOW checkpoint_warning;
```

`log_checkpoints=on` logs each checkpoint with details such as trigger reason, write/sync times, and buffers written depending on version. This is an invaluable source for spotting frequent checkpoints and measuring how long they take.

`checkpoint_warning` logs warnings if WAL-triggered checkpoints happen too close together within the configured window.

### Reading the Logs

A log entry typically shows:

- Whether the checkpoint started due to time or WAL request.
- Number of buffers written.
- Write time and sync time.
- Total duration.
- WAL distance or position details depending on version.

Log formats vary across versions. Use a major-version-aware log parser and preserve timestamps and instance identities in dashboards.

### Do Not Enable Logging Without Retention

With frequent checkpoints, `log_checkpoints` can emit many log lines. Configure log rotation/retention and alert on log volume.

## 26. pg_stat_archiver: Monitoring Archiving

If WAL archiving is enabled:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_catalog.pg_stat_archiver;
```

### Reading the Output

- `archived_count`: WAL segments archived successfully per stats.
- `failed_count`: failed archive attempts.
- `last_failed_wal`/`last_failed_time`: most recent failure.
- `last_archived_wal`/`last_archived_time`: most recent successful archive.

Track **delta failed_count** and elapsed time since the last successful archive. A single resolved transient failure differs greatly from a steadily rising `failed_count` with a frozen `last_archived_time`.

### Archive Backlog

`pg_stat_archiver` does not directly report how many WAL segments are queued for archiving. Combine:

- Count and size of files in `pg_wal`.
- `last_archived_time` and `failed_count`.
- Output/logs from `archive_command` or the archive library.
- Disk usage of the archive destination.

## 27. Slow or Failing Archive Commands

Check:

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
```

Common causes:

- Destination out of space.
- Expired credentials or tokens.
- Slow or failing network/object storage.
- Archive command timing out or exiting non-zero.
- Wrong permissions or path.
- Archive consumer unable to keep up with WAL generation rate.

### Consequences

If a WAL segment has not been archived successfully while archiving is enabled, PostgreSQL must keep that segment to retry. As the backlog grows, `pg_wal` expands toward disk exhaustion.

### Never Manually Delete WAL Files

Never delete files inside `pg_wal` using filesystem commands. PostgreSQL manages WAL segment lifecycles; manual deletion can break recovery/replication and prevent the cluster from starting.

## 28. Replication Slots Retaining WAL

A replication slot retains WAL needed by a standby or unconfirmed logical consumer. If the consumer lags or stops, the slot can hold many WAL segments.

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

Estimate WAL distance retained by slots:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS retained_wal_estimate
FROM pg_catalog.pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    restart_lsn
) DESC;
```

This estimates LSN distance, not an exact exclusive byte allocation per slot when multiple retention requirements overlap.

### Inactive Slots

An inactive slot still pins WAL even with no consumer connected. Before dropping a slot, verify whether the consumer can be recreated, whether a re-snapshot would be required, and who owns the slot.

## 29. max_slot_wal_keep_size

`max_slot_wal_keep_size` limits how much WAL replication slots may retain, enforced per checkpoint/version semantics. If exceeded, the slot can lose its ability to continue from old WAL and require reinitialization or re-snapshotting.

```sql
SHOW max_slot_wal_keep_size;
SHOW wal_keep_size;
```

### Trade-Offs

- Unlimited slot retention: a stalled consumer can grow `pg_wal` uncontrollably.
- Cap too low: slots get invalidated before consumers catch up.
- `wal_keep_size`: retains a minimum WAL cushion for standbys; it does not replace logical slots or archiving.

Design retention around consumer outage/recovery capability, disk headroom, and WAL generation rate.

## 30. Monitoring Standby Replay Lag

On the primary:

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(sent_lsn, replay_lsn)::bigint
    ) AS send_to_replay_bytes,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

### Distinctions

- `sent_lsn`: WAL sent by the primary.
- `write_lsn`: WAL written by the standby.
- `flush_lsn`: WAL flushed by the standby.
- `replay_lsn`: WAL replayed into database state on the standby.

A large send-to-replay gap shows the standby is slow to receive or replay. `replay_lag` is a timing statistic per view semantics, not a complete substitute for LSN distance.

### Note

`write_lag`, `flush_lag`, and `replay_lag` can be NULL when no suitable samples exist; never treat NULL as zero lag.

## 31. High WAL Generation vs. High WAL Retention Are Two Distinct Problems

| Observation | Possible Cause | Investigation Path |
|---|---|---|
| High wal_bytes/s, stable pg_wal size | Workload generates WAL fast while recycling/archiving keeps up | Optimize write workload, FPIs, checkpoints |
| Normal wal_bytes/s, growing pg_wal size | Archive/slot/standby retention | `pg_stat_archiver`, slots, replication |
| High wal_bytes/s, frequent requested checkpoints | `max_wal_size` small relative to generation rate | Checkpoint stats, `max_wal_size`, workload |
| Rising WAL archive failures | Destination/network/credentials | Archive logs, destination capacity |
| Growing slot retained distance | Consumer lag / inactive | Slot owner, consumer progress |
| Growing replica replay lag | Network, standby I/O/CPU, apply bottleneck | `pg_stat_replication`, standby metrics |

### Combined Scenario

Frequent checkpoints can inflate FPIs and WAL generation. Slow archiving or slots can simultaneously hold back WAL. When both happen together, `pg_wal` can explode rapidly: creating more log while recycling slower.

## 32. Inspecting pg_wal Disk Usage

On a server with appropriate privileges:

```sql
SELECT
    count(*) AS wal_files,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size
FROM pg_catalog.pg_ls_waldir();
```

`pg_ls_waldir()` returns WAL files and metadata. Execution requires restricted privileges; monitoring accounts may need an appropriate role/grant.

### Why a Query Alone Is Not Always Enough

- Files are actively created and recycled during sampling.
- Segment files can be pinned by multiple reasons simultaneously.
- `max_wal_size` is a soft limit.
- Total volume usage also includes archives, logs, data, and temp files.

Combine SQL metrics with OS/provider volume metrics. Never diagnose a checkpoint failure solely from the WAL file count.

## 33. WAL Directory and Disk Headroom

Monitor:

- Total `pg_wal` size.
- Free space on the volume hosting `pg_wal`.
- Archive destination capacity.
- WAL generation rate.
- Slot retained WAL distance.
- Archive failures/backlogs.
- Replica lag.

### Why Is Headroom Essential?

WAL can surge suddenly during bulk loads, index builds, mass UPDATE/DELETE operations, or when a replica or archiver stalls. If the volume fills up, PostgreSQL may become unable to write WAL and stop accepting writes.

### Alert on Growth Rate

A volume with 100 GB free while WAL grows at 20 GB/minute will hit trouble in minutes. Track both **absolute free bytes** and **estimated time-to-full** from recent growth rates.
## 34. wal_buffers and the WAL Writer

WAL records are written to WAL buffers before being flushed out to WAL segment files. `wal_buffers` controls shared memory dedicated to WAL buffers.

```sql
SHOW wal_buffers;
SHOW wal_writer_delay;
SHOW wal_writer_flush_after;
```

### wal_buffers

A value of `-1` lets PostgreSQL auto-size WAL buffers from `shared_buffers` per version rules. Too-small WAL buffers can force backends to assist flushing frequently; however, raising it excessively will not improve throughput if storage or WAL sync latency is the bottleneck.

### WAL Writer

The WAL writer writes WAL buffers out to WAL files on schedule. `wal_writer_delay` and `wal_writer_flush_after` govern flushing and batching behavior.

Never confuse the WAL writer with the checkpointer: the WAL writer writes the **WAL log**, whereas the checkpointer writes **data pages** during checkpoints.

## 35. synchronous_commit Does Not Reduce WAL Generation

```sql
SHOW synchronous_commit;
```

`synchronous_commit` governs commit acknowledgement and flush waiting, not how many WAL records are generated.

With `synchronous_commit=off`, PostgreSQL can confirm commits before the corresponding WAL records flush durably. The database remains consistent after a crash, yet transactions recently acknowledged to clients can be lost within the crash window.

### Do Not Use It as a Checkpoint Workaround

- Does not reduce heap or index changes.
- Does not clear archive backlogs.
- Does not eliminate checkpoints.
- Can lower commit latency in certain workloads while altering durability guarantees.

Use it only when the application accepts those semantics with a clear recovery/replay policy. Never toggle `synchronous_commit` to work around frequent checkpoints.

## 36. fsync and wal_sync_method

Inspect:

```sql
SHOW fsync;
SHOW wal_sync_method;
```

`fsync=on` is critical for durability. Disabling `fsync` can boost benchmark scores while gravely increasing the risk of data loss or corruption after an OS crash or power failure.

`wal_sync_method` selects the platform-appropriate WAL sync mechanism. Changing it must be grounded in OS, filesystem, and storage semantics plus controlled benchmarks.

**Never disable fsync in production to cope with high I/O.** If storage cannot keep up with fsync demand, address storage latency/capacity or throttle the workload.

## 37. wal_compression: Trading CPU for Fewer FPI Bytes

If `pg_stat_wal` shows high `wal_fpi` and WAL bytes spiking after each checkpoint, testing `wal_compression` in a representative environment can reduce written bytes.

### Measure Before and After

- WAL bytes per minute.
- FPI count.
- CPU utilization.
- WAL write/flush latency.
- Checkpoint write/sync times.
- Replica apply throughput.

### Results Cannot Be Deduced from Settings Alone

Compression saves I/O at the cost of CPU. If the server is already CPU-bound, overall throughput can degrade. If the workload dirties many pages with compressible FPIs, gains are clearer.

Never change multiple settings at once; when testing `wal_compression`, hold workloads and sample windows comparable.

## 38. checkpoint_flush_after

Setting:

```sql
SHOW checkpoint_flush_after;
```

On supported platforms, this parameter sets the write-byte threshold before prompting the OS to flush/writeback data files during a checkpoint. Its goal is avoiding huge dirty-data piles flushing at checkpoint end or pacing writeback smoothly.

Effectiveness varies across OS, filesystem, block devices, and storage caches. Do not apply a generic formula; check version/platform documentation and benchmark.

## 39. Checkpoint Write Time and Sync Time

On PG16 and earlier, read cumulative counters from `pg_stat_bgwriter`; on PG17+, read `write_time`/`sync_time` from `pg_stat_checkpointer`.

To track trends, compute deltas:

\[
\text{average checkpoint write ms}
= \frac{\Delta \text{checkpoint\_write\_time}}
{\Delta \text{checkpoints}}
\]

\[
\text{average checkpoint sync ms}
= \frac{\Delta \text{checkpoint\_sync\_time}}
{\Delta \text{checkpoints}}
\]

These are averages across the sample window; they do not reveal per-checkpoint tail latency.

### Interpretation

- Write time rising alongside `buffers_checkpoint`: many pages written or low storage throughput.
- Sync time spiking sharply: investigate fsync latency and storage flush behavior.
- Long checkpoint duration with low frequency: writes may be paced smoothly; check completion target and throughput.
- Checkpoint count climbing alongside requested count: inspect WAL rate and `max_wal_size`.

## 40. pg_stat_io and Per-Process I/O

PostgreSQL 16+ provides `pg_stat_io` to inspect I/O statistics by backend type, object, and context:

```sql
SELECT
    backend_type,
    object,
    context,
    sum(reads) AS reads,
    sum(writes) AS writes,
    sum(writebacks) AS writebacks,
    sum(fsyncs) AS fsyncs
FROM pg_catalog.pg_stat_io
GROUP BY backend_type, object, context
ORDER BY sum(writes) DESC;
```

### How to Use It

- Find process types driving heavy write activity.
- Compare checkpointer, background writer, client backends, and autovacuum workers where exposed by the view/version.
- Check reads/writes/fsyncs alongside I/O timings if enabled.
- Take deltas across sample windows since counters are cumulative.

### Limitations

`pg_stat_io` does not replace OS or cloud-provider metrics. It does not necessarily expose device queues, controller caches, cloud-volume throttling, or per-block latencies. Verify schema for your version because columns and backend contexts can evolve.

## 41. I/O Saturation at the Storage Layer

Checkpoints may simply be what exposes a storage limit. Measure at the OS/provider layer:

- Read/write IOPS.
- Read/write throughput in MB/s.
- Average and p95/p99 latency.
- Queue depth / outstanding requests.
- Cloud volume burst credits and throttling.
- fsync latency.
- Free disk space and volume expansion limits.

### Example

A volume is capped at 500 MB/s. Checkpoint writes consume 350 MB/s, WAL writes consume 100 MB/s, and foreground queries need 200 MB/s. Total demand exceeds capacity, queues build, and p99 query latency spikes.

### Do Not Just Increase max_wal_size

Raising `max_wal_size` can lower requested checkpoints, yet creates zero extra storage IOPS or throughput. When storage is continuously saturated, reduce write amplification, upgrade storage capacity, or throttle workloads.

## 42. Checkpoints and Crash Recovery Time

More recent checkpoints generally reduce the WAL needed for normal crash recovery. Yet overly frequent checkpoints add write overhead and can inflate FPI generation.

Less frequent checkpoints reduce write overhead at the cost of replaying more WAL after a crash. Replay duration also depends on storage/CPU speed, record counts, and recovery workload.

### Trade-Offs

| Adjustment | Potential Benefit | Cost / Risk |
|---|---|---|
| Increase `max_wal_size` | Fewer requested checkpoints | Higher WAL/disk headroom needed; recovery may replay more WAL |
| Increase `checkpoint_timeout` | Fewer timed checkpoints | Recovery span from checkpoint may lengthen |
| Increase `completion_target` | Smoother checkpoint write distribution | Writes span longer across the interval; storage must still keep up |
| Enable `wal_compression` | Fewer FPI bytes | Higher CPU usage |
| Reduce write workload | Less WAL and fewer data writes | May affect throughput or business latency |

Never tune checkpoints while ignoring **RTO (Recovery Time Objective)** and WAL retention capacity.

## 43. Checkpoints on Standbys: Restartpoints

A standby replaying WAL uses **restartpoints**. A restartpoint resembles a primary checkpoint in creating a recovery checkpoint during replay, yet it depends on checkpoint records received from the primary.

In PG17+, `pg_stat_checkpointer` exposes restartpoint counters on supported versions. In earlier versions, checkpoint/restartpoint stats appear differently.

### Why Does a Standby Still Need Heavy I/O?

- WAL replay modifies data pages.
- Restartpoints must flush dirty buffers.
- Read queries on the standby compete for I/O with replay and restartpoints.
- Replica lag can grow if storage falls behind WAL replay.

Do not focus solely on the primary; inspect disk, CPU, and read workloads on standbys whenever replay lag climbs.

## 44. Checkpoints and Base Backup / PITR

WAL archiving paired with base backups enables point-in-time recovery (PITR). Checkpoints and WAL retention interact as follows:

- Base backups require a consistent WAL span.
- Archives must keep continuous WAL from backup to recovery target.
- Replication slots can retain WAL for logical and physical consumers.
- Purging archive files too early breaks PITR capability.

### Principle

Never treat a checkpoint as a signal to delete WAL archives manually. Archive retention must follow backup catalogs, recovery windows, timelines, and data-protection policies.

## 45. How Do Frequent Checkpoints Affect Backups?

Checkpoints add data page writes; base backups read data files; archive/backup jobs copy WAL. Running frequent checkpoints, full backups, index builds, and mass updates concurrently puts multiple competing I/O streams onto storage.

### Scheduling

- Avoid overlapping heavy maintenance jobs unnecessarily.
- Monitor backup throughput alongside checkpoint logs.
- Ensure archive throughput exceeds average WAL generation with headroom for peaks.
- Watch replica lag during backups and maintenance.

Backups should never be skipped just to make checkpoint metrics look prettier; balance schedules around recovery objectives.

## 46. Operations That Typically Drive Rapid WAL Growth

Common sources:

- Mass UPDATE/DELETE statements.
- High-rate INSERTs into tables with many indexes.
- UPSERTs causing heavy heap and index updates.
- Index creation or rebuilds.
- Bulk loads and ETL jobs.
- Post-checkpoint FPIs when workloads touch many pages.
- Logical decoding/replication settings requiring extra WAL info.
- Metadata and page initialization changes.

### Not Every SQL Statement Has the Same WAL Cost

An UPDATE touching an unindexed column behaves very differently from an UPDATE modifying indexed columns and inserting new index entries. Tables with many secondary indexes generate much more WAL than heap-only updates.

To pinpoint the source, break down workloads by `application_name`, query patterns, table/index activity, and WAL bytes across the same time window.

## 47. Indexes and WAL Amplification

Every INSERT or UPDATE may have to maintain associated indexes. A table with a primary key, unique indexes, and several secondary indexes generates many extra page changes and WAL records.

### Example

```text
INSERT one row into a table with:
  heap page
  primary key index
  unique business key index
  5 secondary indexes

One logical row can cause multiple page changes
and WAL records across both the heap and indexes.
```

### How to Investigate

- Inspect index counts and sizes.
- Check whether indexes are actually used by query workloads.
- Use `EXPLAIN` to understand access paths.
- Measure WAL rate before and after on a clone or staging environment.

Never drop production indexes solely to shrink WAL. Indexes enforce uniqueness, back foreign keys, or protect query SLAs; every change must verify correctness and dependencies.

## 48. UPDATE Patterns and HOT

HOT updates reduce index maintenance when indexed columns remain unchanged and free space exists on the same page. If a workload constantly updates indexed columns, HOT ratios drop and WAL/index churn rises.

Inspect:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    CASE
        WHEN n_tup_upd > 0
        THEN round(
            100.0 * n_tup_hot_upd / n_tup_upd,
            2
        )
        ELSE 0
    END AS hot_update_pct
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_tup_upd DESC
LIMIT 20;
```

### Conditional Optimizations

- Avoid redundant or unused indexes.
- Review `fillfactor` on update-heavy tables.
- Avoid updating the same row repeatedly in one batch if business logic permits coalescing.
- Change schemas only after auditing query and index dependencies.

HOT reduces index churn where eligible; it does not eliminate WAL or dead tuple creation.

## 49. Bulk Loads and WAL

`COPY` into a logged table still generates WAL to protect durability and replication. Certain bulk-load patterns behave differently when targeting a newly created unlogged/unreplicated table under special cluster settings.

### Considerations

- `COPY` into an existing logged table: WAL and index/constraint work still run.
- Loading into `UNLOGGED` staging: reduces staging WAL, yet data is neither crash-safe nor replicated like logged tables.
- Creating indexes after loading a fresh table: can reduce per-row index maintenance, yet requires offline/cutover design and constraint checks.
- `wal_level=minimal`: fits only narrow cluster/recovery/replication conditions, never casual changes on a primary with standbys or logical replication.

### Do Not Equate COPY Speed with WAL-Free

`COPY` is an efficient load protocol, not WAL-free by default. Evaluate crash recovery, PITR, streaming replication, and logical decoding requirements before choosing a load path.

## 50. Manual CHECKPOINT vs. pg_switch_wal()

Two commonly confused commands:

```sql
CHECKPOINT;

SELECT pg_switch_wal();
```

**CHECKPOINT** asks PostgreSQL to perform a checkpoint. It can trigger heavy data-page I/O and is not a way to reduce WAL generation.

**pg_switch_wal()** requests advancing to the next WAL segment. Useful in archiving, backup, or testing workflows, yet not equivalent to a checkpoint.

### Do Not Use Either as a "Clean Up WAL" Button

A checkpoint does not delete WAL still pinned by archiving, slots, or standbys. `pg_switch_wal()` merely switches segments, giving the archiver more segments to process; calling it repeatedly creates small segments and extra archive churn.

Run these commands only for clear operational purposes.

## 51. Why Can max_wal_size Be Exceeded?

`max_wal_size` is a soft limit, not a filesystem quota. PostgreSQL can exceed it when:

- WAL generation surges rapidly between checkpoints.
- A checkpoint is in progress and takes time to complete.
- WAL segments remain pinned by archiving, replication slots, or `wal_keep_size`.
- Workload spikes exceed baseline.
- Backup/recovery requires retaining WAL.

### Separate Two Questions

1. Why is PostgreSQL requesting checkpoints early? Check WAL rate and checkpoint stats.
2. Why does `pg_wal` stay large after checkpoints? Check archiving, slots, standbys, and retention.

Never raise `max_wal_size` hoping to fix an archive backlog; this setting does not speed up archive consumers.

## 52. max_wal_size and Disk Capacity Planning

When considering raising `max_wal_size`:

1. Measure average and peak WAL generation rates.
2. Measure checkpoint duration and requested checkpoint frequency.
3. Calculate space required across checkpoint, backup, and replication windows.
4. Check `pg_wal` volume free space and growth rate.
5. Account for archive and slot retention separately.
6. Confirm recovery time objectives.
7. Increase incrementally in controlled steps and observe.

### Planning Example

If a workload produces 30 MB/s of WAL and you want roughly 10 minutes before WAL-size pressure requests a checkpoint, the corresponding WAL volume is roughly:

\[
30 \text{ MB/s} \times 600 \text{ s}
= 18,000 \text{ MB}
\]

This is only a rough initial estimate, not an exact `max_wal_size` formula. PostgreSQL also accounts for checkpoint timing, WAL segment accounting, peaks, retention, and disk headroom.

### Never Allocate the Entire Disk to max_wal_size

The volume also needs room for data growth, temp files, archive staging, logs, replication backlogs, and emergency headroom. Alert well before free space drops low.

## 53. Checkpoint Timeout and Recovery Objectives

Raising `checkpoint_timeout` can cut timed checkpoint frequency, yet keep in mind:

- Crash recovery must replay more WAL from the checkpoint.
- More dirty buffers can accumulate.
- Each checkpoint may have more pages to write.
- If WAL rate is high, `max_wal_size` can still trigger checkpoints earlier.

Choose `checkpoint_timeout` around both workload and recovery time objectives. Measure recovery on a clone/staging environment when RTO matters; never deduce recovery duration solely from checkpoint minutes.

## 54. Tuning checkpoint_completion_target

Workflow:

1. Check the current setting.
2. Enable/read checkpoint logs.
3. Measure checkpoint write/sync times and storage latency.
4. Determine whether writes are concentrating into bursts.
5. Adjust completion target if checkpoint pacing is the bottleneck.
6. Re-measure p95/p99 latency, write throughput, and checkpoint duration.

If storage is already saturated continuously, stretching checkpoints longer simply prolongs I/O contention. Completion target smooths timing; it does not add device capacity.

## 55. Tuning WAL Generation Before Raising Checkpoints

If `wal_bytes/s` is unusually high:

- Identify which applications or queries drive the writes.
- Inspect `UPDATE`/`UPSERT` patterns.
- Check indexes and HOT update percentages.
- Measure post-checkpoint FPI counts.
- Inspect bulk load and index build jobs.
- Review `wal_level` and replication/CDC needs.
- Check whether `wal_compression` helps shrink FPI bytes.

### Example

A job updating the same row 20 times in a single transaction can be rewritten to update the final state once if business semantics permit. This can reduce heap/index churn and WAL.

Do not coalesce updates if every intermediate change requires audit/event history or triggers distinct business side effects.

## 56. Throttling Write Workloads

When storage nears saturation:

- Break bulk updates into batches.
- Limit concurrency of ETL and import jobs.
- Avoid running multiple index builds or maintenance tasks simultaneously.
- Schedule backups and archive copies thoughtfully.
- Apply backpressure to writers when needed.
- Monitor queue depth and query latency.

Throttling reduces peak I/O while extending job runtime. Choose concurrency balancing total throughput and OLTP SLAs.

## 57. Checkpoints and Synchronous Replication

Synchronous replication affects commit acknowledgements and network/standby flush waits. Checkpoints remain data-page write operations on the primary; a primary checkpoint does not mean standbys have finished replaying.

### Distinguish Latencies

- Local WAL flush latency on the primary.
- Synchronous standby acknowledgement latency.
- Checkpoint write/sync duration.
- Standby replay lag.

An app experiencing high commit latency might be waiting on a synchronous standby even when checkpoint stats look normal. Conversely, checkpoint I/O can slow primary storage even with synchronous replication disabled.

## 58. Controlled WAL/Checkpoint Experiments

In a lab or staging environment, create a table:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_wal;

CREATE TABLE lesson_wal.write_demo (
    id BIGINT PRIMARY KEY,
    group_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO lesson_wal.write_demo (
    id, group_id, payload
)
SELECT
    g,
    g % 100,
    repeat('x', 500)
FROM generate_series(1, 500000) AS g;
```

Record baseline metrics from `pg_stat_wal`, the checkpoint view, disk I/O, and query latency.

Then run:

```sql
UPDATE lesson_wal.write_demo
SET payload = payload || '-changed',
    updated_at = clock_timestamp()
WHERE id % 2 = 0;
```

Observe:

- WAL bytes delta.
- `wal_fpi` delta.
- Checkpoint count delta.
- Checkpoint write/sync time delta.
- `pg_wal` directory size.
- Storage write throughput and latency.

This lab intentionally creates churn; run it on test data, never run this mass UPDATE on a production table just to test.

## 59. Comparing Frequent vs. Infrequent Checkpoints

For meaningful benchmarks:

1. Use the same data volume and query/write mix.
2. Keep concurrency, cache warmth, and storage class equivalent.
3. Measure across windows long enough to span multiple checkpoint cycles.
4. Record timed and requested checkpoint counts.
5. Measure WAL bytes, FPIs, disk I/O, and latency.
6. Measure crash recovery on a disposable clone if comparing RTO.

### Do Not Compare Throughput Alone

A setup with higher TPS that takes far longer to recover or blows past disk headroom for WAL retention may be unfit for production. Compare durability, availability, and recovery objectives together.

## 60. Never Change Multiple Settings Simultaneously

A tuning cycle might adjust:

- `max_wal_size`.
- `checkpoint_timeout`.
- `checkpoint_completion_target`.
- `wal_compression`.
- `wal_buffers`.
- Autovacuum cost/worker settings.
- Storage throughput/IOPS.

Changing everything at once makes it impossible to tell which change produced the effect. Establish a baseline, adjust one related group, observe long enough, and only then proceed.

## 61. Identifying the PostgreSQL Major Version

Before building dashboards or running stats queries:

```sql
SHOW server_version;
SHOW server_version_num;
```

Examples:

- PG16: checkpoint counters live in `pg_stat_bgwriter`.
- PG17+: checkpoint counters live in `pg_stat_checkpointer`; `pg_stat_bgwriter` has an updated schema.
- `pg_stat_io` was introduced in PG16.
- Certain slot/replication columns were added in different major versions.

Never copy a PG16 dashboard query onto PG17 without verifying columns.

## 62. Identifying Queries Generating Heavy WAL

When `pg_stat_statements` is installed and enabled on a version exposing WAL counters:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    wal_records,
    wal_fpi,
    wal_bytes,
    left(query, 160) AS query_preview
FROM pg_catalog.pg_stat_statements
ORDER BY wal_bytes DESC
LIMIT 20;
```

### Interpretation

- High total `wal_bytes` may come from a query called very frequently.
- WAL bytes per call flags queries with high cost per execution.
- High `wal_fpi` can point to queries touching many pages and emitting FPIs.
- Query text may be normalized with literals hidden depending on config.

### Limitations

`pg_stat_statements` does not replace cluster-level WAL metrics; counters can reset and cover only tracked query statements. Some background or internal activity is not attributed to user queries as expected.

## 63. WAL Bytes per Call

Example:

```sql
SELECT
    queryid,
    calls,
    pg_size_pretty(wal_bytes) AS total_wal,
    pg_size_pretty(
        (wal_bytes / GREATEST(calls, 1))::bigint
    ) AS wal_per_call,
    left(query, 120) AS query_preview
FROM pg_catalog.pg_stat_statements
WHERE calls > 0
ORDER BY wal_bytes / GREATEST(calls, 1) DESC
LIMIT 20;
```

This is a relative ranking; the query with the highest `wal_per_call` is not automatically the top optimization target. Weigh total bytes, call frequency, business criticality, and latency.

## 64. Snapshotting Metrics Over Time

A dashboard should capture time-series samples:

```text
timestamp
server_id / instance_id
pg_stat_wal.wal_bytes
pg_stat_wal.wal_fpi
checkpoint counters
checkpoint write/sync time
pg_wal directory bytes
archive failures
replication slot retained distance
replica replay lag
storage IOPS/throughput/latency
```

From samples, compute:

- WAL MB/s.
- FPI/s.
- Checkpoints/minute.
- Requested checkpoints/minute.
- Average checkpoint write/sync time per checkpoint.
- `pg_wal` bytes growth/minute.
- Replica replay lag trend.

### Never Record Only Instantaneous Values

Checkpoints and WAL are time-based phenomena. A single snapshot does not reveal rates, spikes, durations, or whether a backlog is growing or shrinking.

## 65. pg_stat_activity and Wait Events

When query latency spikes during checkpoints:

```sql
SELECT
    pid,
    backend_type,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 160) AS query_preview
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Wait events help distinguish:

- `WALWrite`/`WALSync`: processes waiting on WAL write/flush.
- `DataFileRead`/`DataFileWrite` or version-matching I/O waits: data file I/O.
- `Lock`: waiting on locks, not necessarily checkpoint I/O.
- Client waits: backend waiting on client/network.

Wait event names evolve across versions. Consult the `pg_wait_events` catalog when looking them up.

## 66. Checkpoints and WAL Wait Events

WAL-related wait events appear when backends wait for WAL buffers to be written or WAL to be synced. If many client backends wait on `WALWrite`/`WALSync`:

- Inspect WAL storage latency.
- Inspect the WAL writer and `wal_buffers_full`.
- Check commit rates and synchronous replication.
- Review `synchronous_commit` policy.
- Check for storage saturation.

Never assume checkpoints are the sole culprit. WAL flush latency can spike due to a slow WAL device or synchronous standby waits while checkpoint write times look completely normal.

## 67. Inspecting I/O via pg_stat_io

A more detailed query (PG16+; verify columns on your version):

```sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    writebacks,
    writeback_time,
    fsyncs,
    fsync_time,
    stats_reset
FROM pg_catalog.pg_stat_io
ORDER BY backend_type, object, context;
```

`read_time`, `write_time`, and `fsync_time` depend on `track_io_timing` configuration and may be 0 if timing collection is off. Enabling timing carries overhead; evaluate on a realistic workload first.

## 68. I/O Timings and track_io_timing

```sql
SHOW track_io_timing;
```

When `track_io_timing` is enabled, PostgreSQL collects I/O durations in certain stats views and `EXPLAIN`. This separates operation counts from wait times, though it can add overhead depending on platform.

### Usage

- Enable deliberately in appropriate environments.
- Compare before and after under identical workloads.
- Use `EXPLAIN (ANALYZE, BUFFERS)` on representative queries.
- Cross-check with OS/provider latency.

Never treat cumulative `read_time`/`write_time` in stats as the latency of a single request.

## 69. Checkpoint Logs and Metrics Must Correlate

If dashboards show requested checkpoints climbing:

1. Read `log_checkpoints` output to verify checkpoint type and timestamps.
2. Compare `wal_bytes` delta across the same window.
3. Check `max_wal_size` and `checkpoint_timeout`.
4. Inspect checkpoint write and sync times.
5. Compare storage latency and query p99.
6. Check archive and slot retention separately.

If requested counts climb while WAL rate is modest, look for manual `CHECKPOINT` calls, backup/maintenance jobs, stats resets, or version misinterpretation.

## 70. Suggested Dashboard Layout

| Category | Metrics | Question Answered |
|---|---|---|
| WAL generation | wal_bytes/s, wal_records/s, wal_fpi/s | How fast is WAL being generated? |
| WAL buffers | wal_buffers_full delta | Is there pressure on WAL buffers? |
| Checkpoints | timed/requested per minute | Are checkpoints frequent due to time or WAL? |
| Checkpoint I/O | write_time, sync_time, buffers_written | How long does checkpointer take and how much does it write? |
| Background writer | buffers_clean, maxwritten_clean, buffers_alloc | Is bgwriter preparing clean buffers fast enough? |
| Backend writes | buffers_backend (older versions) | Are backends forced to write buffers themselves? |
| WAL retention | pg_wal bytes, slot distance, archive failures | Why is WAL not recycling? |
| Replication | sent/write/flush/replay LSN, lag | Are standbys/consumers keeping up? |
| Storage | IOPS, MB/s, latency, queue depth | Is hardware saturated? |
| Application | commit latency, p95/p99, throughput | What impact do users feel? |

A good dashboard aligns these metrics on a single timeline and supports drilling down by server, role, and application.

## 71. Runbook: Checkpoints Happening Too Frequently

When checkpoint counts climb rapidly:

1. Compute per-minute deltas of timed and requested checkpoints.
2. Read checkpoint logs to confirm trigger reasons.
3. Measure WAL bytes/s and FPI/s.
4. Check `max_wal_size` and `checkpoint_timeout`.
5. Check checkpoint write and sync durations.
6. Correlate storage latency/queue depth with application p95/p99.
7. Look for overlapping bulk jobs, index builds, or mass updates.
8. Verify whether any scheduler/job invokes manual `CHECKPOINT`.
9. Adjust a single justified parameter, such as `max_wal_size` or `completion_target`.
10. Re-measure under equivalent load and verify RTO and disk headroom.

### Common Signals

- Requested checkpoints climbing: suspect WAL threshold hit early or manual requests.
- Timed checkpoints steady yet high I/O bursts: check `completion_target`, storage, and concurrent writers.
- WAL rate jumping alongside `wal_fpi`: inspect checkpoint frequency and touched pages.

## 72. Runbook: WAL Directory Growing Continuously

When `pg_wal` size grows:

1. Check WAL generation rate in `pg_stat_wal`.
2. Check `pg_stat_archiver`: `failed_count` and `last_archived_time`.
3. Check archive destination capacity, network, and credentials.
4. Check `pg_replication_slots`: `active`, `restart_lsn`, and retained distance.
5. Check `wal_keep_size` and `max_slot_wal_keep_size`.
6. Check primary/standby replay lag.
7. Compare WAL generation against archive and replication consumption.
8. Check volume free space and time-to-full.
9. Remediate consumers/archiving per owner and recovery policy.
10. Watch `pg_wal` shrink and recycle once retention blockers clear.

### Never Delete Files Directly

Never delete segments inside `pg_wal` from the shell. If disk space is urgently needed, clear the retention cause via PostgreSQL/archive/replication policy or expand the volume per runbook.

## 73. Runbook: Archive Failures

1. Read `pg_stat_archiver` and server logs.
2. Identify the most recently failed WAL file.
3. Check `archive_command` exit codes.
4. Check network, credentials, permissions, and destination.
5. Check whether the destination has enough free space.
6. Restore the archive service.
7. Confirm `failed_count` stops climbing and `last_archived_time` advances.
8. Ensure the entire WAL backlog drains.
9. Verify backup/PITR continuity.
10. Document outage duration and recovery impact.

### Never Skip Failed Files

Archives require a continuous WAL chain along the timeline. One missing segment can render a backup/PITR chain unusable for recovery targets past that point.

## 74. Runbook: Replication Slot Retaining WAL Too Long

1. Identify slot owner and slot type.
2. Check active/inactive status and consumer health.
3. Measure `restart_lsn` distance from current WAL LSN.
4. Inspect consumer logs, network, and apply throughput.
5. Check whether the slot is pinning `xmin` or `catalog_xmin`.
6. Evaluate disk headroom and `max_slot_wal_keep_size`.
7. Recover the consumer or plan a re-snapshot if needed.
8. Drop or recreate slots only after confirming with the owner and downstream recovery plan.
9. Monitor WAL recycling once the slot advances.
10. Set alerts when inactive duration or retained bytes exceed policy.

Never drop a slot simply because `active=false`; a logical consumer may need that slot to avoid losing changes.

## 75. Runbook: Checkpoint I/O Increasing Query Latency

1. Align checkpoint logs, checkpoint stats, and query latency on one timeline.
2. Inspect `write_time`/`sync_time` and `buffers_written`.
3. Inspect storage IOPS, throughput, latency, and queue depth.
4. Check background writer and backend writes.
5. Check for concurrent bulk loads, index builds, autovacuum, or backups.
6. Measure WAL rate and FPIs to assess write amplification.
7. Check whether `checkpoint_completion_target` is concentrating bursts.
8. Consider throttling batches/concurrency or upgrading storage capacity.
9. Adjust `max_wal_size`/checkpoint settings deliberately if metrics prove it is needed.
10. Re-measure p95/p99 and recovery duration.

Never assume raising `max_wal_size` fixes storage saturation; it mainly alters checkpoint frequency.

## 76. Runbook: Abnormal WAL Rate Spike After Deployment

1. Compare `wal_bytes/s` before and after deployment.
2. Identify queries or `application_name` driving increased WAL.
3. Compare `pg_stat_statements` WAL counters if available.
4. Inspect `UPDATE`/`UPSERT` behavior and affected row counts.
5. Check new indexes or recently executed migrations.
6. Check whether `wal_fpi` spikes align with checkpoint frequency.
7. Check triggers, audit tables, or outbox writes.
8. Compare workload input volume and concurrency.
9. Roll back or tune code if a confirmed regression exists and policy allows.
10. Reconcile data, replication, and backups after changes.

### Note

A deployment adding an index makes writes emit extra index-maintenance WAL. An audit trigger can multiply written rows. Measure impact on a clone or staging before jumping to conclusions.

## 77. Recovery When the pg_wal Volume Is Nearly Full

This is an emergency operational situation:

1. Confirm which volume is filling up and its growth rate.
2. Never delete WAL files manually.
3. Check archive failures and replication slot retention.
4. Identify which standby or consumer is pinning WAL.
5. Recover archiving or the consumer if possible.
6. Expand the volume per storage/platform procedure if needed.
7. Throttle non-essential write workloads to slow WAL generation.
8. Verify the database can still write WAL and stays healthy.
9. Watch archiving/replication catch up and WAL recycle.
10. Post-incident, verify backup/PITR and slot continuity.

Never restart repeatedly or run `CHECKPOINT` in a loop hoping to free WAL. If segments remain pinned by archiving or slots, checkpoints cannot delete them.

## 78. Checklist Before Increasing max_wal_size

- Have average and peak WAL generation rates been measured?
- Are requested checkpoints actually climbing?
- Or do timed checkpoints already dominate?
- What are checkpoint write/sync times and storage latency?
- Does `pg_wal` have enough disk headroom for the new target?
- Are archiving or replication slots currently pinning WAL?
- Does RTO permit sparser checkpoints?
- Have backup, PITR, and standby policies been reviewed?
- Was the change tested under an equivalent workload?
- Are dashboards and a rollback plan ready post-change?

If the real problem is an archive backlog or inactive slot, clear the retention blocker before increasing checkpoint size.

## 79. Checkpoint and WAL Operations Checklist

### WAL Generation

- `wal_bytes/s` and `wal_fpi/s`.
- Queries/applications producing heavy WAL.
- Index, trigger, and update patterns.
- WAL buffer pressure.

### Checkpoints

- Timed and requested counts per minute.
- Checkpoint write and sync times.
- Checkpoint buffers written.
- Checkpoint logs and completion target.

### Retention

- `pg_wal` directory size.
- Archive failures and backlog.
- Replication slot `restart_lsn` distance.
- `wal_keep_size` and `max_slot_wal_keep_size`.
- Replica replay lag.

### Storage and Application

- IOPS, throughput, latency, and queue depth.
- Free disk space and time-to-full.
- Commit latency and p95/p99.
- Concurrent ETL, index builds, backups, and autovacuum.

### Recovery

- RTO and RPO.
- Base backups and archive continuity.
- Standby catch-up capacity.
- Has the emergency runbook been rehearsed?

## 80. Easily Misunderstood Principles

**"COMMIT means the data page has been written to the data file."** False. WAL flush can satisfy commit durability; data pages are written later.

**"WAL flush is a checkpoint."** False. Flushing ensures WAL bytes are durable per policy; checkpoints write data pages and create recovery points.

**"max_wal_size is a hard limit."** False. It is a soft target that can be exceeded.

**"A large pg_wal means WAL generation is too high."** Not necessarily. Archive or replication retention may be the cause.

**"More checkpoints are always safer."** False. Frequent checkpoints drive up I/O and FPIs; balance against recovery time.

**"Sparse checkpoints are always better."** False. Recovery may have to replay far more WAL and dirty pages accumulate.

**"Raising checkpoint_timeout always reduces checkpoints."** False if `max_wal_size` is hit first.

**"Raising max_wal_size makes storage faster."** False. It can only reduce requested checkpoint frequency.

**"checkpoint_completion_target caps all I/O."** False. It schedules checkpoint writes, not the entire workload.

**"Background writer and checkpointer are the same process."** False. They have distinct purposes.

**"Larger wal_buffers is always better."** False. Inspect `wal_buffers_full`, WAL flush latency, and storage.

**"Disabling full_page_writes is a safe way to reduce FPIs."** False. It increases torn-page corruption risk after a crash.

**"synchronous_commit=off reduces WAL volume."** False. It changes commit flush acknowledgement semantics without omitting WAL records.

**"pg_switch_wal() creates a checkpoint."** False. It switches WAL segments.

**"CHECKPOINT deletes all old WAL."** False. Archiving, slots, and standbys may still require that WAL.

**"wal_compression always speeds things up."** False. It trades CPU for fewer FPI bytes.

**"Raising max_wal_size fixes archive failures."** False. You must fix the archive consumer or destination.

**"Dropping an inactive replication slot is harmless."** False. The consumer may lose continuity and need a full re-snapshot.

**"High checkpoint write_time always means slow storage."** False. It can also be high simply because the checkpointer wrote many buffers.

**"Low checkpoint sync_time means all I/O is fast."** False. Foreground queries or WAL I/O can still be bottlenecked.

**"One stats snapshot is enough to find rates."** False. You need delta samples with timestamps and `stats_reset`.

## 81. Practice Exercises

### Exercise 1 — What Is WAL?

Explain the Write-Ahead Log and why PostgreSQL must write WAL before data pages are durably persisted.

### Exercise 2 — WAL Flush and Checkpoints

A transaction commits and the client receives ACK, yet its heap page has not been written to the data file. Why can the database still recover after a crash?

### Exercise 3 — Distinguishing WAL Stages

Distinguish WAL generation, write, flush, archive, replay, and retention. Give an example where an archive backlog grows `pg_wal` even while WAL generation stays steady.

### Exercise 4 — WAL Segments

Explain segment files in `pg_wal`, segment recycling, and why the WAL file count does not depend solely on `wal_bytes/s`.

### Exercise 5 — Checkpoints

Describe dirty buffers, the checkpointer, checkpoint records, and redo points. How do checkpoints help crash recovery?

### Exercise 6 — Timed and Requested

Distinguish timed checkpoints from requested checkpoints. What events aside from hitting `max_wal_size` can trigger a requested checkpoint?

### Exercise 7 — max_wal_size

Why is `max_wal_size` a soft limit? List at least three reasons `pg_wal` can exceed its configured value.

### Exercise 8 — checkpoint_timeout

Explain the trade-offs of increasing `checkpoint_timeout`. Why can requested checkpoints still happen before timed checkpoints?

### Exercise 9 — checkpoint_completion_target

Compare targets of 0.5 and 0.9 in terms of how checkpoint writes are spread over time. Why does this setting not cap total I/O?

### Exercise 10 — FPI

Explain full-page images and torn-page protection. Why can the first modification after a checkpoint generate larger WAL?

### Exercise 11 — Frequent Checkpoints and WAL

A workload touches 500,000 pages per checkpoint cycle. Explain why frequent checkpoints can raise FPI count and WAL bytes.

### Exercise 12 — full_page_writes

Why should `full_page_writes` not be disabled just to cut WAL volume? State the risks after a crash or power failure.

### Exercise 13 — wal_compression

Explain the CPU vs. WAL-bytes trade-off when enabling `wal_compression`. Which metrics should be compared before and after?

### Exercise 14 — Checkpointer and bgwriter

Distinguish the checkpointer, background writer, and backend writes. Why does tuning bgwriter up not replace checkpoints?

### Exercise 15 — Checkpoint Write/Sync Time

A server shows high checkpoint `write_time` yet low `sync_time`. List hypotheses to check before concluding storage is slow.

### Exercise 16 — Checkpoint Stats PG16

Query `checkpoints_timed`, `checkpoints_req`, `checkpoint_write_time`, and `buffers_checkpoint` from `pg_stat_bgwriter`. Explain each metric.

### Exercise 17 — Checkpoint Stats PG17

Query `num_timed`, `num_requested`, `write_time`, `sync_time`, and `buffers_written` from `pg_stat_checkpointer`. Why can a PG16 dashboard not be used verbatim?

### Exercise 18 — WAL Stats

Query `wal_records`, `wal_fpi`, `wal_bytes`, `wal_buffers_full`, and `stats_reset` from `pg_stat_wal`. Which metric reflects WAL generation?

### Exercise 19 — Computing WAL Rate

`wal_bytes` increases from 120 GB to 150 GB over 10 minutes. Calculate the WAL rate in decimal MB/s. State what to check if `stats_reset` changed between the two samples.

### Exercise 20 — LSN Distance

Use `pg_current_wal_lsn` and `pg_wal_lsn_diff` to measure WAL bytes between two samples. Why is this an LSN address distance that need not match `pg_stat_wal.wal_bytes` delta byte-for-byte?

### Exercise 21 — Requested Checkpoint Ratio

An hour saw 40 timed checkpoints and 160 requested checkpoints. Compute the requested percentage. Why should you inspect logs before concluding `max_wal_size` is too low?

### Exercise 22 — Archive Stats

Query `pg_stat_archiver`. If `failed_count` climbs while `last_archived_time` stalls, build a checklist across destination, network, and credentials.

### Exercise 23 — Replication Slots

An inactive logical slot holds `restart_lsn` 80 GB behind current WAL LSN. Explain the disk risk and why you should not immediately drop the slot.

### Exercise 24 — wal_keep_size

Distinguish `wal_keep_size` from replication slot retention and archive retention. Why does one setting not replace the other two mechanisms?

### Exercise 25 — Replica Lag

Query `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn` on the primary. Explain which gap shows the standby is lagging in replay.

### Exercise 26 — pg_wal Directory

Use `pg_ls_waldir()` to count files and total size. Why must this be paired with OS free space and archive/slot metrics?

### Exercise 27 — pg_stat_io

On PG16+, group I/O stats by `backend_type`/`object`/`context`. State the limitations of this view compared to OS/provider storage metrics.

### Exercise 28 — WAL Writer

Distinguish `wal_buffers`, `wal_writer_delay`, `wal_writer_flush_after`, and the checkpointer. Why does increasing `wal_buffers` not automatically fix WAL storage latency?

### Exercise 29 — synchronous_commit

Explain why `synchronous_commit=off` can cut commit wait without reducing WAL generation. What is the durability risk?

### Exercise 30 — fsync

Explain why disabling `fsync` in production is not a valid fix for high I/O. State what to measure if fsync latency is high.

### Exercise 31 — Which Queries Generate WAL?

Use `pg_stat_statements` WAL counters if your version supports them to rank queries by `wal_bytes`. Distinguish total WAL from WAL per call.

### Exercise 32 — Index Amplification

A table has 8 indexes. Explain why INSERT/UPDATE generates more WAL than heap-only changes and how to evaluate unnecessary indexes.

### Exercise 33 — HOT Updates

Query `n_tup_upd` and `n_tup_hot_upd`. Why can updating an unindexed column reduce index churn under the right conditions?

### Exercise 34 — Bulk Loads

Compare `COPY` into an existing logged table versus `UNLOGGED` staging and building indexes after loading a new table. State durability and replication trade-offs.

### Exercise 35 — CHECKPOINT vs. pg_switch_wal

Explain how `CHECKPOINT` and `pg_switch_wal()` differ. Why can calling `pg_switch_wal` continuously increase archive work?

### Exercise 36 — Storage Saturation

A volume is capped at 500 MB/s; checkpoints use 350 MB/s, WAL uses 100 MB/s, and queries need 200 MB/s. Explain how queues/latency shift and propose ways to lower peak load.

### Exercise 37 — Tuning max_wal_size

Design a procedure to increase `max_wal_size` incorporating baseline measurement, disk headroom, requested checkpoint rate, archive/replication retention, and RTO.

### Exercise 38 — Runbook for pg_wal Growth

Write a runbook for rapid `pg_wal` growth: tracking `wal_bytes/s`, archive failures, replication slots, replica lag, free disk, and recovery steps.

### Exercise 39 — Frequent Checkpoints After Deployment

A deployment adds an audit trigger and a new index. WAL rate, requested checkpoints, and query p99 all climb. Identify the metrics to correlate and a safe rollback/tuning plan.

### Exercise 40 — Designing Production WAL/Checkpoints

A PostgreSQL primary has:

- 4 TB of data.
- OLTP at 5,000 transactions/second.
- Batch ETL generating 50 MB/s of WAL for 20 minutes.
- Two physical standbys and one logical replication slot.
- An archive destination that occasionally slows down for 5 minutes.
- Storage with bounded IOPS where p99 query latency is a strict SLA.
- A 15-minute Recovery Time Objective.

Design:

1. A monitoring dashboard covering WAL rate, FPIs, checkpoint counts, and write/sync times.
2. How to tell whether requested checkpoints stem from `max_wal_size` or manual operations.
3. A `max_wal_size`/`checkpoint_timeout`/`completion_target` policy matching workload and RTO.
4. Disk headroom for `pg_wal` when archiving lags and the slot pins WAL.
5. Alerts for WAL generation, archive failures, slot retained distance, and time-to-full.
6. An ETL throttling plan to protect OLTP latency.
7. How to evaluate `wal_compression` and `full_page_writes`.
8. Separating primary checkpoint I/O from standby replay I/O.
9. A runbook when archive/slot backlogs push the volume close to full.
10. How to benchmark and recovery-test before applying settings to production.

## Conclusion

**WAL protects PostgreSQL durability and recoverability.** Transaction commits can be acknowledged once the required WAL flushes, while data pages remain dirty in shared buffers. Checkpoints write required pages to data files and establish new recovery points to bound how much WAL must be replayed after a crash.

**Overly frequent checkpoints can drive up I/O and inflate WAL generation via full-page images.** Timed checkpoints follow `checkpoint_timeout`; requested checkpoints typically occur when WAL exceeds `max_wal_size`. `checkpoint_completion_target` spreads checkpoint writes, while `max_wal_size` paces checkpoint frequency by WAL volume. These settings must be chosen alongside disk headroom and recovery time objectives.

**WAL generation and WAL retention are two distinct concerns.** `pg_stat_wal` shows WAL created; `pg_stat_checkpointer`/`pg_stat_bgwriter` and checkpoint logs show checkpoint activity; `pg_stat_archiver`, replication slots, and standby LSNs reveal what is pinning WAL. If `pg_wal` grows, determine whether WAL is being created too fast or recycling/archiving is falling behind.

Finally, measure WAL rate, FPIs, checkpoint counts, write/sync times, storage latency, archive backlogs, and replica lag on the same timeline. Sound tuning typically combines cutting workload write amplification, appropriate checkpoint scheduling, sufficient storage capacity, and explicit retention policies. **Never disable durability protections or manually delete WAL just to make dashboards look cleaner; keeping WAL intact is keeping your database recoverable.**
