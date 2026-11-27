# Tuning Checkpoints, WAL, and Write Workloads in PostgreSQL

PostgreSQL writes data using Write-Ahead Logging (WAL): changes are logged to WAL before the corresponding data pages need to be written to data files. Periodic checkpoints establish recovery points and flush dirty buffers to storage. This mechanism lets PostgreSQL recover from crashes, while also creating a write workload consisting of WAL writes, data-page writes, checkpoint I/O, archive traffic, and replication traffic.

When checkpoints happen too frequently, storage can experience heavy write bursts, WAL volume can grow rapidly, and full-page images can inflate WAL size. When checkpoints land at bad times, application latency can spike. Conversely, raising WAL thresholds excessively without budgeting disk capacity can fill volumes, especially when replication slots or archiving retain WAL.

Tuning checkpoints, WAL, and write workloads must start with metrics: which checkpoints are happening, how much WAL is generated, whether backends are waiting on I/O or WAL flushes, whether storage has enough throughput, and which workloads generate the writes. Then adjust one parameter group at a time, benchmark on representative workloads, and verify both performance and durability.

This lesson explains PostgreSQL's write path, the checkpoint lifecycle, key WAL/checkpoint parameters, commit durability, synchronous replication, ways to reduce write amplification, and a safe tuning workflow for production.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the role of WAL in crash recovery and durability.
2. Distinguish WAL writes, data-page writes, commit flushes, and checkpoints.
3. Explain checkpoints triggered by time or WAL volume.
4. Understand the impact of `checkpoint_timeout`, `max_wal_size`, and `checkpoint_completion_target`.
5. Distinguish `min_wal_size`, `wal_keep_size`, and `max_slot_wal_keep_size`.
6. Read checkpoint statistics, `pg_stat_wal`, and I/O statistics.
7. Understand `full_page_writes`, full-page images, and `wal_compression`.
8. Evaluate `wal_buffers`, the WAL writer, and the background writer.
9. Distinguish `synchronous_commit` from synchronous replication.
10. Tune commit batching and transaction sizing.
11. Reduce write amplification from indexes, `UPDATE` patterns, and bulk workloads.
12. Monitor archive backlog, replication lag, and WAL retention.
13. Tune via baselines, benchmarks, and small incremental changes.
14. Handle checkpoint spikes, WAL growth, and storage saturation.
15. Design monitoring, alerting, and runbooks for write-heavy PostgreSQL.

## 2. Write Path Overview

When an application modifies a row, PostgreSQL does not necessarily write the data page containing that row straight to the data file. Instead, the database generates WAL records describing the change. WAL is written sequentially, while data pages are updated in shared buffers and flushed to storage on an appropriate schedule.

~~~text
Application transaction
        |
        v
Modify shared buffers
        |
        +---- Generate WAL records
        |          |
        |          v
        |      WAL buffers
        |          |
        |          v
        |      WAL files (pg_wal)
        |          |
        |          +---- Archive
        |          |
        |          +---- Replication stream
        |
        v
Dirty data pages
        |
        v
Checkpointer / background writer / backend writes
        |
        v
Data files on storage
~~~

### 2.1. WAL Precedes Data Pages

Write-Ahead Logging requires the relevant WAL records to be durably written before the corresponding data pages are flushed to storage. If the server crashes, PostgreSQL uses WAL to redo required changes starting from the latest applicable checkpoint.

### 2.2. Commit Does Not Mean Writing Every Data Page

With `synchronous_commit` defaulting to `on`, commit normally waits for the transaction's WAL to be flushed per durability policy. It does not wait for every modified data page to be written to table/index files. Checkpoints handle writing dirty buffers and advancing the recovery point.

### 2.3. Different Types of I/O

- WAL I/O: usually sequential, append-oriented, tied to commits/replication/archiving.
- Data-file I/O: writes table/index pages; checkpoints can generate large write volumes.
- Temporary I/O: sort/hash spills or temporary relations.
- Archive/replication I/O: shipping WAL to archive storage or replicas.

### 2.4. Why Tuning Must Look at Both

Raising WAL throughput does not guarantee data-page writes keep up. Increasing checkpoint frequency reduces accumulated dirty buffers yet increases write bursts and full-page images. Tuning must balance latency, throughput, recovery time, and disk capacity.

## 3. What Is WAL?

WAL is a stream of records describing changes needed to recover the database. WAL files reside in the `pg_wal` directory inside the data directory unless the deployment layout places storage elsewhere.

### 3.1. WAL Records

Operations such as `INSERT`, `UPDATE`, `DELETE`, index modifications, and certain catalog/metadata changes generate WAL. A single transaction can generate many WAL records before committing.

### 3.2. WAL Segments

WAL is split into segment files. Segment size is commonly 16 MB in standard builds, though you should never hard-code that assumption; check build/runtime settings or use PostgreSQL utilities.

### 3.3. LSN

Log Sequence Number (LSN) identifies a position in the WAL stream.

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            '0/0'::pg_lsn
        )::bigint
    ) AS approximate_position_from_start;
~~~

An LSN is a logical position in the WAL stream, not the number of bytes currently stored in `pg_wal`.

### 3.4. WAL and Backup/PITR

Archived WAL combined with a base backup enables point-in-time recovery (PITR). Streaming replication alone does not replace backups; replication propagates accidental deletes and logical data corruption too.

### 3.5. WAL and Replication

Physical standbys receive WAL for replay. Logical decoding reads WAL and translates it into logical changes. Logical replication requires `wal_level=logical` on the publisher; physical replication requires `wal_level=replica` or `logical`.

## 4. What Is a Checkpoint?

A checkpoint is a point in the WAL/recovery process where PostgreSQL guarantees all required dirty buffers have been written to data files and records a checkpoint record in WAL. After a crash, PostgreSQL can start redo from the appropriate checkpoint instead of replaying WAL from the beginning of history.

### 4.1. Dirty Buffers

When a transaction modifies a page in shared buffers, that page becomes dirty. It can be written to disk by the checkpointer, the background writer, or a backend process under certain conditions.

### 4.2. Checkpointer

The checkpointer performs checkpoint writes and syncs required files according to PostgreSQL's checkpoint procedure. A checkpoint can generate substantial data-file I/O.

### 4.3. Checkpoint Record

The checkpoint record stores recovery metadata in WAL. After a successful checkpoint, WAL prior to the checkpoint can be recycled/archived subject to backup, archive, replication slot, and other retention rules.

### 4.4. Timed Checkpoints

A checkpoint can start when `checkpoint_timeout` elapses since the previous checkpoint.

### 4.5. Requested Checkpoints

A checkpoint can also be requested when WAL volume approaches or exceeds `max_wal_size`. Manual checkpoints triggered by `CHECKPOINT` also appear in statistics.

### 4.6. A Checkpoint Is Not a Commit

Commit confirms a transaction per WAL durability policy. Checkpoints write dirty pages and establish a recovery point. A transaction can be durably committed long before its data pages are written by a checkpoint.

## 5. Checkpoint Lifecycle

~~~text
Writes accumulate
      |
      v
Dirty buffers + WAL generation
      |
      +---- checkpoint_timeout reached
      |
      +---- WAL reaches checkpoint pressure
      |
      v
Checkpoint begins
      |
      v
Dirty buffers written over checkpoint interval
      |
      v
Required files synced
      |
      v
Checkpoint record / completion
      |
      v
Old WAL eligible for recycle when other retention rules allow
~~~

### 5.1. Checkpoint Write Phase

PostgreSQL attempts to spread dirty page writes across a portion of the checkpoint interval to avoid dumping all I/O at once.

### 5.2. Checkpoint Sync Phase

Written files must be synced to satisfy durability requirements. Storage latency and filesystem behavior affect sync duration.

### 5.3. Checkpoints Can Cause Latency

If storage lacks throughput, checkpoint writes contend with application reads/writes. Backends may also have to write buffers themselves when shared buffers need space.

### 5.4. Too-Frequent Checkpoints

Continuous checkpoints can:
- Increase data-page write activity.
- Increase full-page images in WAL.
- Increase write amplification.
- Cause checkpoint I/O to contend with applications.
- Trigger frequent checkpoint warnings in logs.

### 5.5. Too-Infrequent Checkpoints

Spreading checkpoints further apart reduces checkpoint frequency and full-page-image overhead, yet:
- Requires retaining more WAL.
- Crash recovery may have to replay more WAL.
- Each checkpoint may take longer.
- Disk pressure increases if archives/slots hold WAL.

## 6. Key Checkpoint Parameters

| Parameter | Role | Common tuning direction |
| --- | --- | --- |
| `checkpoint_timeout` | Max interval between timed checkpoints | Increase if checkpoints are too frequent and recovery budget allows |
| `max_wal_size` | Soft WAL threshold triggering checkpoint pressure | Increase if requested checkpoints are excessive and disk allows |
| `min_wal_size` | Minimum WAL retained/recycled | Adjust for workload and WAL reuse |
| `checkpoint_completion_target` | Fraction of checkpoint interval used to complete checkpoint | Keep high enough to spread writes |
| `checkpoint_warning` | Threshold to warn on overly frequent checkpoints | Use to detect pressure |
| `log_checkpoints` | Logs checkpoint details | Enable for observation and analysis |

Defaults vary by PostgreSQL major version and package/provider. Read `SHOW` or `pg_settings` rather than assuming a universal default.

## 7. checkpoint_timeout

`checkpoint_timeout` caps the time between timed checkpoints. A common default is 5 minutes, though verify your specific version.

~~~sql
SHOW checkpoint_timeout;
~~~

### 7.1. Raising checkpoint_timeout

Reduces timed checkpoints and lowers full-page image frequency. In return, each checkpoint spans a longer WAL range and crash recovery may replay more WAL.

### 7.2. Lowering checkpoint_timeout

Can shorten WAL replay after a crash, yet triggers more frequent checkpoints, increasing data-page writes and full-page-image activity.

### 7.3. Do Not Tune checkpoint_timeout Alone

Checkpoints are also triggered by WAL volume. If `max_wal_size` is too low, raising `checkpoint_timeout` will not prevent requested checkpoints.

### 7.4. Recovery Budget

Choose `checkpoint_timeout` based on recovery time objectives (RTO), WAL generation rate, and storage capacity. Measure recovery duration in drills rather than guessing from the setting alone.

## 8. max_wal_size

`max_wal_size` is a soft threshold PostgreSQL uses to decide when to checkpoint due to WAL volume. It is not a hard cap on total `pg_wal` disk usage.

~~~sql
SHOW max_wal_size;
~~~

### 8.1. Raising max_wal_size

If logs/statistics show excessive requested checkpoints driven by WAL volume, raising `max_wal_size` makes checkpoints less frequent. Ensure adequate storage headroom and understand WAL retention from archiving/replication slots.

### 8.2. Lowering max_wal_size

Forces checkpoints sooner, limiting retained WAL under normal conditions while raising checkpoint frequency and FPI overhead. It is not a safe fix for a filling volume caused by slot or archive retention.

### 8.3. Why pg_wal Can Exceed max_wal_size

- Replication slots retaining WAL not yet confirmed by consumers.
- `wal_keep_size` requiring WAL retention for standbys.
- Failing or lagging `archive_command`.
- Workload bursts generating WAL faster than expected.
- Checkpoints/recycling not yet releasing segments.
- Backup/recovery processes requiring WAL.

### 8.4. Capacity Planning

Estimate `WAL generation rate × outage/retention duration`, plus burst headroom. Account separately for:
- Normal checkpoint working set.
- Physical/logical slot retention.
- Archive backlog.
- Backup/PITR retention.
- Temporary and maintenance headroom.

## 9. min_wal_size

`min_wal_size` is the minimum amount of WAL PostgreSQL tries to retain for reuse, avoiding constant creation/deletion of segments when WAL generation fluctuates.

~~~sql
SHOW min_wal_size;
~~~

### 9.1. Too Low

Can force PostgreSQL to allocate new WAL segment files whenever write load ramps back up. Impact depends on storage/filesystem and workload.

### 9.2. Too High

Retains more WAL segment files in `pg_wal` after they are no longer needed for recovery/retention, consuming disk capacity.

### 9.3. min_wal_size Is Not Archive Retention

It does not dictate how long WAL is kept in archives and does not replace backup retention policies.

## 10. checkpoint_completion_target

`checkpoint_completion_target` controls the fraction of the checkpoint interval PostgreSQL aims to use to finish checkpoint writes. Higher values spread writes out more evenly instead of front-loading them.

~~~sql
SHOW checkpoint_completion_target;
~~~

### 10.1. High Value

A value close to 1 reduces write bursts by spreading checkpoint I/O. Leave margin for other activity and observe actual behavior.

### 10.2. Low Value

Packs checkpoint writes into a shorter window, risking I/O spikes and higher latency.

### 10.3. Not a Global Write Throttle

This setting paces checkpoint writes; it does not throttle writes from applications, the WAL writer, the background writer, or backend processes.

## 11. checkpoint_warning and log_checkpoints

~~~sql
SHOW checkpoint_warning;
SHOW log_checkpoints;
~~~

### 11.1. checkpoint_warning

Logs a warning when requested checkpoints occur more frequently than the configured threshold. Helps identify when `max_wal_size` is too small for the WAL generation rate.

### 11.2. log_checkpoints

When enabled, PostgreSQL writes checkpoint statistics to server logs, including write/sync durations and buffer counts depending on version. Correlate logs with latency and storage metrics.

### 11.3. Logging Configuration

Enable `log_checkpoints` in environments needing checkpoint analysis. Ensure log retention, rotation, and volume are managed.

## 12. Full-Page Images and full_page_writes

After a checkpoint, the first modification to a data page may write a full-page image (FPI) to WAL to protect against torn-page writes in certain failure scenarios.

### 12.1. Why Full-Page Images Exist

A page write to storage may not be atomic. If a crash happens mid-write, the page can be torn. A full-page image in WAL lets PostgreSQL restore the page to a consistent state before replaying subsequent changes.

### 12.2. full_page_writes

~~~sql
SHOW full_page_writes;
~~~

In production, keep `full_page_writes=on`. Disabling it exposes the database to page corruption after crashes/power failures if storage does not guarantee atomic page writes.

### 12.3. Checkpoint Impact

After a checkpoint, the first modification to each page generates an FPI. Overly frequent checkpoints force the same hot pages to emit FPIs repeatedly in short intervals.

### 12.4. WAL Amplification

FPIs expand WAL bytes compared to delta-only records. Therefore, checkpoint tuning and WAL compression can substantially impact WAL volume.

### 12.5. Do Not Disable full_page_writes to Shrink WAL

Cutting WAL by disabling torn-page protection is a dangerous durability/recovery trade-off. Identify why FPIs are high and address it with safer measures.

## 13. wal_compression

`wal_compression` enables compressing full-page images in WAL on supported versions.

~~~sql
SHOW wal_compression;
~~~

Specific options depend on PostgreSQL version and build, potentially including `off`/`on` or supported algorithms like `pglz`, `lz4`, and `zstd`.

### 13.1. Benefits

Compressing FPIs reduces WAL bytes, archive bandwidth, and replication traffic, especially when FPIs make up a large share of WAL.

### 13.2. Costs

Compression consumes CPU. If CPU is already saturated, reducing disk/network bytes may not improve overall throughput.

### 13.3. Measure Before and After

Compare:
- `wal_bytes/sec`.
- `wal_fpi` / `wal_records`.
- CPU usage.
- WAL archive throughput.
- Replication lag.
- Commit latency.

### 13.4. Does Not Compress Every WAL Record

This setting targets full-page images; it does not turn the entire WAL stream into a generic compressed archive.

## 14. wal_level and Its Impact on WAL

Main levels:

| Level | Purpose |
| --- | --- |
| `minimal` | Reduces some WAL requirements in eligible modes; not for normal replication/archiving |
| `replica` | WAL for crash recovery, archiving, and physical replication |
| `logical` | Adds information needed for logical decoding |

### 14.1. Do Not Lower wal_level When Replication Is Needed

Physical standbys and WAL archiving require an appropriate level, usually `replica` or `logical`. Logical decoding requires `logical`.

### 14.2. logical Can Generate More WAL

`logical` level can increase WAL overhead due to extra information needed for logical decoding. Measure real workloads when switching from `replica` to `logical`.

### 14.3. Restart Requirement

`wal_level` requires a PostgreSQL restart. Check `pending_restart` and plan rolling/maintenance restarts around your HA topology.

## 15. wal_buffers

`wal_buffers` is shared memory used to buffer WAL records before writing them to WAL files.

~~~sql
SHOW wal_buffers;
~~~

### 15.1. Automatic Sizing

`-1` lets PostgreSQL auto-size based on `shared_buffers` up to version-specific caps. This is usually a solid starting point.

### 15.2. When to Adjust?

Consider adjusting only with evidence that WAL buffers frequently fill up or the WAL write path is bottlenecked. `pg_stat_wal` provides `wal_buffers_full` on supported versions.

### 15.3. Do Not Raise Just Because Write Volume Is High

`wal_buffers` does not make slow storage fast. If the bottleneck is fsync latency, disk throughput, or checkpoint writes, enlarging the buffer does not fix the root cause.

### 15.4. Inspection

~~~sql
SELECT
    wal_buffers,
    shared_buffers
FROM pg_settings
WHERE name IN ('wal_buffers', 'shared_buffers');
~~~

## 16. WAL Writer

The WAL writer background process periodically writes WAL buffers out to WAL files. Certain settings control write and flush cadence.

### 16.1. wal_writer_delay

~~~sql
SHOW wal_writer_delay;
~~~

Controls the sleep delay between WAL writer cycles. Lowering it writes WAL more frequently at higher I/O activity; raising it batches writes yet affects commit visibility delay when `synchronous_commit=off`.

### 16.2. wal_writer_flush_after

~~~sql
SHOW wal_writer_flush_after;
~~~

Controls how much WAL is written before the WAL writer forces a flush per this setting. Exact behavior depends on version/platform.

### 16.3. Do Not Tune Without Evidence

WAL writer defaults work well in most environments. Only tune after examining `wal_buffers_full`, WAL write/sync times, commit latency, and OS storage metrics.

## 17. Background Writer and Backend Writes

The background writer tries to write dirty buffers before backends need free slots in shared buffers. The checkpointer performs checkpoints; the background writer helps reduce synchronous writes backends must perform themselves.

### 17.1. bgwriter_lru_maxpages

Caps the pages the background writer attempts to write per round.

### 17.2. bgwriter_lru_multiplier

Scales estimated upcoming buffer demand from recent consumption.

### 17.3. bgwriter_delay

Controls the pause between background writer rounds.

### 17.4. buffers_backend

In versions exposing this counter, backend writes show when application backends had to write dirty buffers themselves. This signals whether the background writer and checkpoints are keeping up.

### 17.5. Do Not Confuse bgwriter with Checkpointer

The background writer does not replace checkpoints. Tuning bgwriter cannot resolve every checkpoint spike or WAL retention issue.

## 18. pg_stat_checkpointer and Checkpoint Statistics by Version

Statistics view names/schemas changed across major versions.

### 18.1. PostgreSQL 17 and Later

Checkpoint statistics were split into `pg_stat_checkpointer`. Inspect counters with:

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

Fields include timed/requested checkpoints, write/sync times, and buffers written depending on version.

### 18.2. Earlier Versions

Checkpoint counters reside in `pg_stat_bgwriter`:

~~~sql
SELECT *
FROM pg_stat_bgwriter;
~~~

Familiar counters include `checkpoints_timed`, `checkpoints_req`, `checkpoint_write_time`, `checkpoint_sync_time`, and `buffers_checkpoint`. Schema changed in PostgreSQL 17; never run old column queries on newer servers without checking.

### 18.3. Requested/Timed Ratio

If requested checkpoints are high relative to timed checkpoints, WAL volume is triggering checkpoints too frequently. Check `max_wal_size`, WAL rate, and logs.

### 18.4. Checkpoint Duration

High checkpoint write/sync times suggest slow storage, volume contention, or excessive checkpoint writes. Cross-check OS-level latency.

### 18.5. Stats Reset

Counters are cumulative since stats reset. Capture snapshots and compute deltas; if `stats_reset` changes, start a new series.

## 19. pg_stat_wal: Measuring WAL Generation and Write Behavior

`pg_stat_wal` is available starting in PostgreSQL 14. Check the schema on your running version:

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

Important counters include:
- `wal_records`: number of WAL records.
- `wal_fpi`: number of full-page images.
- `wal_bytes`: WAL bytes generated.
- `wal_buffers_full`: times WAL buffers filled in counted situations.
- `wal_write` and `wal_sync`: write/sync counts.
- `wal_write_time` and `wal_sync_time`: write/sync durations if timing tracking is enabled.
- `stats_reset`: timestamp of statistics reset.

### 19.1. WAL Bytes/Sec

Take two snapshots of `wal_bytes`:

\[
\text{WAL bytes/sec} =
\frac{\text{current wal\_bytes} - \text{previous wal\_bytes}}
{\text{elapsed seconds}}
\]

Do not compute deltas if `stats_reset` changed or counters reset.

### 19.2. FPI Ratio

Compare `wal_fpi` against `wal_records` and `wal_bytes`. A workload modifying many distinct pages after checkpoints produces high FPIs. Evaluate alongside checkpoint frequency and `wal_compression`.

### 19.3. wal_buffers_full

High counts must be weighed against total WAL records/bytes and commit latency. Never conclude from a single counter alone.

### 19.4. Timing Counters

If `wal_write_time`/`wal_sync_time` is zero, check timing collection settings for your version. Do not assume zero means storage has zero latency.

## 20. pg_stat_io: Observing I/O by Backend and Context

`pg_stat_io` was introduced in PostgreSQL 16. It provides I/O statistics by backend type, object, and context; exact columns depend on version.

~~~sql
SELECT *
FROM pg_stat_io;
~~~

### 20.1. Reading by Context

Context helps separate normal operations, bulk operations, and maintenance I/O per version semantics.

### 20.2. Backend Type

Inspect I/O from client backends, background writer, checkpointer, autovacuum, and other processes.

### 20.3. Does Not Replace OS Metrics

`pg_stat_io` gives a PostgreSQL-level view. Device latency, queue depth, saturation, and filesystem behavior still require host/provider metrics.

### 20.4. Sampling

Store snapshots, compute deltas, and track `stats_reset`. Avoid treating cumulative counters as instantaneous rates.

## 21. Wait Events Related to WAL and Checkpoints

`pg_stat_activity` exposes `wait_event_type` and `wait_event`.

~~~sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    application_name,
    clock_timestamp() - query_start AS query_age,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE wait_event_type IN ('IO', 'LWLock', 'Activity')
ORDER BY query_start NULLS LAST;
~~~

Exact wait event names vary across PostgreSQL versions. Some events relate to WAL write/sync, checkpoint write/sync, or buffer I/O.

### 21.1. WALWrite/WALSync

Backends may wait on WAL write or sync. If many commits wait simultaneously while the OS reports high storage latency, the WAL device may be the bottleneck.

### 21.2. Checkpoint Waits

Processes can wait on checkpoint-related activity or I/O. Combine checkpoint stats, logs, and disk metrics.

### 21.3. LWLock

An `LWLock` wait alone does not prove a WAL bottleneck. Identify the exact event name and correlate with workload.

### 21.4. Snapshot Sampling

Wait events change rapidly. Collect frequent samples or use tracing/monitoring to separate transient waits from sustained contention.

## 22. Commit Durability and synchronous_commit

`synchronous_commit` controls how much WAL durability is awaited when a transaction commits. It is distinct from `synchronous_standby_names`, though the two interact when synchronous replication is configured.

~~~sql
SHOW synchronous_commit;
~~~

### 22.1. on

For local commits, waits until the transaction's WAL is durably flushed to local storage. When synchronous standbys are configured, `on` typically waits for standby confirmation of WAL flush per synchronous replication semantics.

### 22.2. off

Does not wait for WAL flush before reporting commit success. The server still writes WAL in the background; a crash can lose recently acknowledged transactions within a short window, yet database consistency remains protected by PostgreSQL design.

Use only for reproducible data or where losing a few recent transactions is acceptable. Never use as a default for financial/critical data.

### 22.3. local

Waits for local WAL flush without waiting for remote synchronous standbys. Useful when local durability is required without remote wait latency.

### 22.4. remote_write

When synchronous standbys are configured, waits for the standby to write WAL to its OS, without necessarily flushing durably to standby storage. Protection depends on standby host/OS failure models.

### 22.5. remote_apply

Waits for the synchronous standby to replay the transaction so it becomes visible on the standby. Can add significant commit latency, yet fits designs needing read-after-write visibility on standbys.

### 22.6. Durability Trade-Offs

| Mode | Local flush | Remote acknowledgement | Remote replay |
| --- | --- | --- | --- |
| `off` | No wait | No wait | No wait |
| `local` | Yes | No wait | No wait |
| `on` | Yes | If sync standby configured, waits for remote flush | Not necessarily |
| `remote_write` | Yes | Waits for remote OS write | Not necessarily |
| `remote_apply` | Yes | Yes | Waits for replay |

This table is a high-level summary; verify exact semantics against your version's docs and synchronous standby configuration.

## 23. synchronous_standby_names and Replication

Synchronous replication requires configuring eligible standbys in `synchronous_standby_names`.

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

### 23.1. Commit Latency

The primary can wait for remote acknowledgement. Network latency, standby storage flush, and standby load all affect commit latency.

### 23.2. Availability Trade-Off

If no eligible synchronous standby is available, commits may block depending on configuration. Design quorum/priority and failover policies carefully.

### 23.3. Remote Apply

`remote_apply` adds replay time before commit confirmation. Use when applications require transactions to be visible on synchronous standbys immediately after commit.

### 23.4. Do Not Lower Durability to Mask Replication Lag

If synchronous commits are slow, investigate network, standby disk, and replication topology. Switching to `off` alters RPO without fixing the underlying bottleneck.

## 24. fsync, full_page_writes, and wal_sync_method

These settings directly govern durability.

### 24.1. fsync

~~~sql
SHOW fsync;
~~~

In production, keep `fsync=on`. Turning `fsync` off risks data loss or unrecoverable corruption after OS crashes/power failures. Never disable it to boost production throughput.

### 24.2. full_page_writes

Keep `on` in nearly all deployments. It protects against torn-page scenarios using full-page images.

### 24.3. wal_sync_method

Selects how PostgreSQL asks the OS to sync WAL. The default usually suits the platform. Only change after benchmarking on the exact filesystem, kernel, storage driver, and failure model.

### 24.4. Storage Must Honor Flush Semantics

Durability depends on PostgreSQL, OS, controller, hypervisor, cloud volume, and cache policy together. A storage layer claiming flushes are complete without actual persistence undermines durability.

### 24.5. pg_test_fsync

Use `pg_test_fsync` to benchmark fsync methods on a suitable test host. It is a benchmarking tool, not proof that `fsync` can be turned off.

## 25. wal_keep_size and Replication Slots

`wal_keep_size` specifies a minimum WAL volume PostgreSQL tries to retain for standbys under normal conditions. It is not a hard cap and does not replace replication slots.

~~~sql
SHOW wal_keep_size;
SHOW max_slot_wal_keep_size;
~~~

### 25.1. wal_keep_size

Helps standbys catch up after brief interruptions if segments remain available. If a standby lags too far behind, archives or a fresh base backup may be required.

### 25.2. Physical Replication Slots

A physical slot retains WAL needed by a standby. If the standby goes offline, the slot can hold WAL indefinitely and cause `pg_wal` to grow.

### 25.3. Logical Replication Slots

A logical slot retains WAL for decoding/subscribers. A stopped consumer can pin WAL and catalog history.

### 25.4. max_slot_wal_keep_size

Caps slot retention on supported versions. When exceeded, the slot may be invalidated or consumers unable to resume from their prior position depending on version/behavior. Have a resync plan.

### 25.5. Capacity Alerts

Monitor `active`, `restart_lsn`, `confirmed_flush_lsn`, `safe_wal_size` if available, retained WAL estimates, and volume free space.

## 26. Archiving and WAL Retention

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

### 26.1. Archive Backlog

If the archive command fails, WAL segments awaiting archiving cannot be recycled. Track `failed_count`, `last_failed_time`, and logs.

### 26.2. archive_timeout

`archive_timeout` forces a WAL segment switch after the configured duration during low-write workloads. Setting it too low creates many partially filled segments and increases archive storage/traffic.

### 26.3. Archive Destination

Check capacity, credentials, permissions, network, and lifecycle policies on archive storage. A full archive target can cause `pg_wal` to grow on the primary.

### 26.4. Backup Retention

WAL archive retention must cover the PITR window. Never delete archive segments to free disk without checking backup dependencies.

## 27. WAL Compression vs. Archive Compression

Distinguish two compression layers:
- `wal_compression` compresses full-page images inside WAL records.
- Archive tooling/providers can compress WAL segment files at rest.

In-WAL compression shrinks bytes before streaming/archiving; archive compression reduces storage/network at the archive layer per tool. Measure CPU and throughput at both layers.

## 28. Tuning Checkpoints and WAL by Symptom

| Symptom | Data to inspect | Investigation direction |
| --- | --- | --- |
| Frequent requested checkpoints | Checkpoint stats, `log_checkpoints`, WAL rate | `max_wal_size`, `checkpoint_timeout` |
| High checkpoint write time | Checkpoint stats, storage latency | Disk throughput, checkpoint pacing |
| Sudden spike in WAL bytes/sec | `pg_stat_wal`, workload changes | Bulk writes, indexes, FPI, logical level |
| `pg_wal` nearly full | Slots, archive, `wal_keep_size`, filesystem | Consumer/archive retention |
| High commit latency | WAL sync times, wait events, storage | fsync latency, synchronous replication |
| Rising backend writes | bgwriter/checkpointer stats, `pg_stat_io` | `shared_buffers`, bgwriter, storage |
| High FPI ratio | `wal_fpi`, checkpoint frequency | Checkpoint interval, `wal_compression` |
| Archive failures | `pg_stat_archiver`/logs | Archive target and command |
| Replica lag | `pg_stat_replication`/slots | Network, standby I/O, retention |
| Rising temporary writes | `pg_stat_database`, query stats | Sort/hash spills and query plans |

Never change a setting based on a single symptom alone. Gather a baseline and establish causality.

## 29. Reducing Write Amplification in Workloads

Not every write throughput issue is solved by checkpoint settings. SQL/schema design often yields larger gains.

### 29.1. Remove Unnecessary Indexes

Every `INSERT` updates associated indexes. `UPDATE`s on indexed columns also generate new index entries. Check index usage, constraints, and query plans before dropping indexes.

### 29.2. HOT Updates

A Heap-Only Tuple (HOT) update avoids creating new index entries when the update does not modify indexed columns and the page has sufficient free space. This reduces index write amplification.

### 29.3. Fillfactor

Lowering `fillfactor` on heavily updated tables leaves free space on pages to increase HOT update rates. The trade-off is larger table size; benchmark against your update pattern.

### 29.4. Avoid No-Op Updates

Only update rows that actually change. An `UPDATE` setting the exact same value can still generate new row versions/WAL and fire index/trigger work.

### 29.5. Update Fewer Columns

Avoid rewriting large payloads when only one small field changes. Structure SQL and application updates to minimize unnecessary churn.

### 29.6. Partition-Based Retention

For time-series/event data, detaching/dropping old partitions is far more efficient than `DELETE`ing millions of rows, reducing WAL, dead tuples, and vacuum load. Check foreign keys, publications, backups, and retention semantics.

## 30. Batch Writes and Transaction Sizing

Batching improves throughput by amortizing commit/fsync overhead.

### 30.1. Multi-Row INSERT

~~~sql
INSERT INTO app.events (event_id, event_type, created_at)
VALUES
    (1001, 'created', clock_timestamp()),
    (1002, 'updated', clock_timestamp()),
    (1003, 'deleted', clock_timestamp());
~~~

### 30.2. COPY

~~~sql
COPY app.events (event_id, event_type, created_at)
FROM STDIN WITH (FORMAT csv);
~~~

`COPY` is generally much more efficient for bulk loading than many single-row `INSERT` round trips. Logged tables still generate WAL.

### 30.3. Batch Transactions

Grouping multiple rows into one transaction cuts commit overhead, yet overly large transactions increase:
- Lock duration.
- WAL bursts.
- Rollback cost.
- Replication lag.
- Dead tuple/vacuum impact.
- Snapshot hold duration.

### 30.4. Benchmark Batch Size

Test multiple batch sizes with representative data and concurrency. Measure rows/sec, p95/p99 commit latency, WAL bytes/row, replication lag, and rollback duration.

### 30.5. Group Commit

PostgreSQL can group commits from concurrent transactions to share a WAL flush. Enabling `commit_delay` is unnecessary for group commit in most cases.

## 31. commit_delay and commit_siblings

`commit_delay` introduces a very brief delay before WAL flush to increase group commit opportunities when enough concurrent transactions are active. `commit_siblings` sets the minimum active transaction threshold for the delay to apply.

~~~sql
SHOW commit_delay;
SHOW commit_siblings;
~~~

### 31.1. When to Consider

Only in workloads with high concurrent commit volume and significant fsync overhead, after benchmarking. Under low concurrency, the delay purely adds latency.

### 31.2. Group Commit Already Works Automatically

PostgreSQL supports group commit natively. Raising `commit_delay` is not needed by default.

### 31.3. Measure p95/p99

If throughput rises slightly while tail latency spikes, the change may violate OLTP SLAs.

## 32. Unlogged Tables and Staging

Unlogged tables reduce WAL for table data in certain operations, yet they are not a general-purpose solution for write throughput.

### 32.1. Characteristics

Unlogged tables are not WAL-logged normally for table contents, do not replicate like logged tables, and are truncated after crash recovery per PostgreSQL semantics.

### 32.2. Use Cases

Use only for temporary, staging, or reconstructible data. Never use for business data requiring durability or physical standby consistency.

### 32.3. Indexes and Metadata

Understand how indexes, sequences, and metadata behave with unlogged relations in your version. Test recovery and failover behavior.

### 32.4. Converting to Logged

If staging data becomes permanent, plan conversion to logged tables and verify WAL/replication impact.

## 33. Bulk Loads and Maintenance

Bulk loading generates large WAL volumes and impacts checkpoints and replication.

### 33.1. Preparation

- Size disk for tables, indexes, WAL, and temporary files.
- Check replication/archive capacity.
- Pick batch/chunk sizes.
- Schedule outside peak application traffic.
- Establish backup/recovery points.

### 33.2. Index Strategy

For new or staging tables, loading data first and building indexes afterward can be faster than maintaining multiple indexes throughout the load. Preserve required constraints and cutover validation.

### 33.3. maintenance_work_mem

Affects maintenance operations such as index builds. Raising it can speed up builds, subject to concurrent jobs and memory budgets.

### 33.4. Autovacuum

Do not disable autovacuum cluster-wide to speed up bulk loads. If tuning per staging table, plan explicit vacuum/analyze and re-enable afterward.

### 33.5. ANALYZE After Load

Run `ANALYZE` so the planner has accurate statistics before production workloads hit newly loaded tables.

## 34. Impact of Checkpoints on Full-Page Images

WAL volume often spikes right after a checkpoint because the first modification to each page emits an FPI.

### 34.1. Workload Page Churn

If a workload touches many distinct pages after each checkpoint, FPI volume can be large. Repeatedly updating the same pages within a single interval requires an FPI only on the first modification after a checkpoint per version semantics.

### 34.2. Checkpoint Frequency

Overly frequent checkpoints repeat FPI generation on hot pages. Lengthening the checkpoint interval lowers FPI frequency while increasing WAL working set and recovery exposure.

### 34.3. Compression

`wal_compression` reduces FPI bytes at the cost of CPU.

### 34.4. Verification

Monitor `wal_fpi`, `wal_records`, `wal_bytes`, checkpoint counters, and CPU. Measure before and after changes.

## 35. Background Writer and shared_buffers

`shared_buffers` is PostgreSQL's page cache. Dirty pages must be written to storage on time. The background writer tries to clean buffers before backends need to reuse them.

### 35.1. Backend Writes

If backends frequently write dirty buffers themselves during query execution, latency can rise. This signals you to examine bgwriter/checkpointer behavior and I/O capacity.

### 35.2. bgwriter Tuning

Raising `bgwriter_lru_maxpages` or the multiplier cleans more buffers proactively, while raising background I/O and storage contention. Setting them too low pushes work onto backends.

### 35.3. shared_buffers

Raising `shared_buffers` can improve cache hit rates in some workloads, yet it does not directly fix checkpoint bottlenecks and increases memory footprint. Tune separately for RAM/OS cache/workload.

### 35.4. Do Not Look Only at buffers_clean

Cross-check `buffers_clean`, `buffers_backend`, `buffers_checkpoint` (where present), `maxwritten_clean`, `pg_stat_io`, and OS device metrics.

## 36. Checkpoint Pacing and Storage Throughput

Checkpoint writes require sustained storage throughput. `checkpoint_completion_target` spreads writes over the interval, yet if storage lacks throughput, checkpoints still drag out or cause contention.

### 36.1. Sequential WAL vs. Data-Page Writes

WAL writes are predominantly sequential; checkpoint data writes scatter across many relation files. Storage may show very different latencies for the two patterns.

### 36.2. Storage Latency

Monitor read/write latency, IOPS, throughput, and queue depth. Cloud volumes may have burst credits or throughput caps.

### 36.3. I/O Saturation

If a volume is already at its throughput cap, raising `max_wal_size` or completion target creates no extra physical capacity. Upgrade storage tier/IOPS, isolate workloads, or cut write amplification.

### 36.4. Filesystem Flush Behavior

WAL sync correctness depends on the OS/storage honoring flush requests. Never pick `wal_sync_method` solely from a synthetic benchmark.

## 37. Illustrative Configuration for a Write-Heavy Workload

This is a directional example for benchmarking, not a universal default for every cluster:

~~~conf
# WAL/recovery
wal_level = replica
archive_mode = on
archive_command = '...'
max_wal_size = 8GB
min_wal_size = 2GB

# Checkpoint pacing
checkpoint_timeout = 15min
checkpoint_completion_target = 0.9
checkpoint_warning = 30s
log_checkpoints = on

# WAL buffers and compression
wal_buffers = -1
wal_compression = on

# Durability
fsync = on
full_page_writes = on
synchronous_commit = on
~~~

### 37.1. Why Only an Example?

Tune `max_wal_size` to WAL rate and volume headroom; `checkpoint_timeout` to recovery budget; `wal_compression` to CPU/FPI ratio; and `synchronous_commit` to durability/RPO.

### 37.2. Replication Requirements

If using logical decoding, `wal_level` must be `logical`. If using synchronous standbys, configure `synchronous_standby_names` and test failover behavior.

### 37.3. Archive Command

The `archive_command` line above is a placeholder. Production must use a tested command/provider integration with proper escaping, credentials, and failure monitoring.

## 38. Checking Effective Settings

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'wal_buffers',
    'wal_compression',
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'checkpoint_warning',
    'max_wal_size',
    'min_wal_size',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'synchronous_commit',
    'fsync',
    'full_page_writes',
    'log_checkpoints'
)
ORDER BY name;
~~~

### 38.1. source

`source` reveals where the setting came from, such as configuration file, command line, database/user/session setting, or default.

### 38.2. pending_restart

If `true`, the setting requires a restart and has not yet taken effect in the running server process.

### 38.3. ALTER SYSTEM

`ALTER SYSTEM` writes settings to `postgresql.auto.conf`. In production environments using configuration management, maintain a single source of truth to prevent config drift.

### 38.4. Reload and Restart

Some settings only need a reload; others require a restart. Check `pg_settings.context` and `pending_restart`, then follow deployment procedures.

## 39. Monitoring Checkpoints

### 39.1. Checkpoint Stats

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

Use on PostgreSQL 17+ where this view is available. On earlier major versions, read checkpoint counters in `pg_stat_bgwriter`.

### 39.2. Checkpoint Logs

Enable `log_checkpoints` and analyze:
- Timed vs. requested.
- Buffers written.
- Write duration.
- Sync duration.
- WAL distance.
- Checkpoint frequency.

### 39.3. Requested Checkpoints

Rapidly rising requested checkpoints indicate `max_wal_size` is small relative to WAL generation. Check archive/slot retention and storage headroom before raising it.

### 39.4. Checkpoint Write/Sync Time

High write time suggests many buffers or limited storage throughput. High sync time points to flush/fsync latency or many files needing sync. Cross-check OS-level latency.

### 39.5. Computing Counter Deltas

Counters are cumulative since stats reset. Sample periodically and compute deltas; if `stats_reset` changes, start a new series.

## 40. Monitoring WAL Generation

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

### 40.1. WAL Bytes Rate

Compute `wal_bytes` delta divided by elapsed seconds.

### 40.2. WAL per Transaction

Compare `wal_bytes` delta against `xact_commit` delta from `pg_stat_database` to estimate WAL bytes/commit. This is a rough aggregate metric; one transaction can write far more data than another.

### 40.3. WAL per Row

In controlled benchmarks, divide `wal_bytes` delta by inserted/updated/deleted rows to compare schema/index designs.

### 40.4. FPI Rate

Track `wal_fpi` deltas. If FPIs spike after checkpoints, inspect checkpoint frequency and page churn.

### 40.5. WAL Writes/Syncs

Compare `wal_write`, `wal_sync`, `write_time`, and `sync_time` where available. Compute rates and averages; do not rely on averages alone if tail latency is an issue.

## 41. Monitoring Replication and Archiving

### 41.1. Physical Standbys

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

### 41.2. Slot Retention

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;
~~~

### 41.3. Archiving

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

### 41.4. Disk Impact

Replication lag or archive failures prevent WAL recycling. Monitor volume free space alongside WAL metrics.

### 41.5. Do Not Drop Slots to Treat Symptoms

Verify consumer ownership, recovery options, and resync cost before dropping a slot. A dropped slot can force a standby/CDC consumer to rebuild from scratch.

## 42. Monitoring I/O and Wait Events

### 42.1. pg_stat_io

On PostgreSQL 16+:

~~~sql
SELECT *
FROM pg_stat_io;
~~~

### 42.2. Activity Waits

~~~sql
SELECT
    backend_type,
    wait_event_type,
    wait_event,
    count(*) AS processes
FROM pg_stat_activity
WHERE wait_event IS NOT NULL
GROUP BY backend_type, wait_event_type, wait_event
ORDER BY processes DESC;
~~~

### 42.3. OS Metrics

On Linux, common tools include:

~~~bash
iostat -xz 1
vmstat 1
pidstat -d 1
~~~

Choose tools/flags suited to your platform and permissions. On managed services, use provider metrics.

### 42.4. Combine Layers

If PostgreSQL reports high sync time and the OS reports high device latency, storage is a strong suspect. If WAL bytes surge while storage latency looks normal, investigate workload or write amplification.

## 43. Benchmarking Tuning Changes

You cannot tune effectively simply by reading current settings.

### 43.1. Baseline

Record:
- TPS and rows/sec.
- p50/p95/p99 commit latency.
- WAL bytes/sec and bytes/transaction.
- Checkpoint count/duration.
- WAL write/sync timings.
- Device IOPS/throughput/latency.
- CPU/memory.
- Replication lag.
- Archive backlog.
- Disk free bytes.

### 43.2. Representative Workload

Use dataset, indexes, concurrency, transaction size, and read/write mix resembling production. Overly simplistic synthetic workloads can miss real bottlenecks.

### 43.3. One Change at a Time

Change one setting group, restart/reload properly, run the same test duration, and compare metrics. Never change checkpoints, WAL compression, `synchronous_commit`, and storage tier simultaneously and guess causality.

### 43.4. Measure Across Multiple Cycles

Run long enough to span multiple checkpoints, warm-up, and workload peaks. A 30-second test may miss checkpoint cycles entirely.

### 43.5. Verify Correctness

After benchmarking, confirm durability settings, replication health, backup/archive, and data consistency. High throughput is meaningless if it violates RPO requirements.

## 44. Ordered Tuning Sequence

A manageable sequence:

1. Verify storage latency/throughput and volume capacity.
2. Enable `log_checkpoints` and collect a checkpoint/WAL baseline.
3. Measure `wal_bytes/sec` and checkpoint frequency.
4. Determine whether requested checkpoints are excessive.
5. Adjust `max_wal_size` if storage headroom permits.
6. Evaluate `checkpoint_timeout` against your recovery budget.
7. Set `checkpoint_completion_target` appropriately to spread writes.
8. Measure FPI ratio and evaluate `wal_compression`.
9. Inspect `wal_buffers`/WAL writer only if counters show a bottleneck.
10. Inspect backend writes/background writer and `pg_stat_io`.
11. Evaluate commit latency and synchronous replication.
12. Reduce write amplification in schema/SQL/workloads.
13. Benchmark and verify failover/PITR after changes.

## 45. Tuning Checkpoints When Requested Checkpoints Are High

1. Confirm `checkpoints_req` or `num_requested` is rising rapidly.
2. Read `log_checkpoints` to confirm WAL-triggered checkpoints.
3. Measure WAL bytes/sec and peak WAL generation.
4. Check current `max_wal_size`.
5. Budget storage headroom and slot/archive retention.
6. Increase `max_wal_size` in a controlled step.
7. Keep `checkpoint_completion_target` at a suitable level.
8. Run the workload long enough to observe multiple cycles.
9. Compare requested/timed checkpoints, latency, and `pg_wal` size.
10. Check recovery time and backup/replication behavior.

Do not raise `max_wal_size` if `pg_wal` is already bloated from inactive slots or archive failures before fixing retention.

## 46. Tuning When Commit Latency Is High

1. Measure application p95/p99 commit latency.
2. Check `synchronous_commit` and `synchronous_standby_names`.
3. Read WAL sync times/counters.
4. Inspect `WALSync`/`WALWrite` wait events.
5. Check OS storage latency and fsync behavior.
6. Check synchronous standby network/flush/apply lag.
7. Distinguish local WAL bottlenecks from remote acknowledgement bottlenecks.
8. Check group commit and transaction batching.
9. Benchmark storage or synchronous policy in a safe environment.
10. Never change durability mode without RPO sign-off.

## 47. Tuning When WAL Spikes Abnormally

1. Measure `wal_bytes/sec`.
2. Compare transaction rate and write workload.
3. Check `wal_fpi` ratio.
4. Check checkpoint frequency.
5. Inspect indexes and update patterns.
6. Check logical decoding/replication workloads.
7. Check full-page image compression.
8. Check bulk loads, large updates, and deletes.
9. Check archive/slot retention to distinguish generation from retained size.
10. Optimize the workload or settings based on the WAL source.

## 48. Tuning When Backend Writes Are High

1. Inspect backend write counters appropriate to your version.
2. Check `pg_stat_io` and wait events.
3. Check `shared_buffers` and memory pressure.
4. Check bgwriter settings and `maxwritten_clean`.
5. Check checkpoint frequency/duration.
6. Check storage saturation.
7. Test incremental bgwriter adjustments if evidence supports it.
8. Measure backend latency and background I/O after changes.

## 49. Settings You Should Not Disable for Speed

| Setting | Reason to keep |
| --- | --- |
| `fsync=on` | Protects durability across OS/power failures |
| `full_page_writes=on` | Reduces torn-page corruption risk |
| Appropriate `wal_level` | Required for recovery, archiving, and replication |
| `archive_mode` when PITR is needed | Preserves WAL archive for recovery objectives |
| `synchronous_commit` aligned with RPO | Governs when commits are acknowledged |

### 49.1. fsync=off

Turning `fsync` off risks data loss or database corruption after a crash. Never use it in production to mask disk latency.

### 49.2. full_page_writes=off

Lowers WAL volume at the cost of weakening protection against torn-page writes. Never disable just to shrink FPIs.

### 49.3. synchronous_commit=off

Different trade-off: recently acknowledged transactions may be lost if the OS/server crashes before WAL flush, though it does not carry the same database corruption risk as `fsync=off`. Use only for workloads that tolerate losing recent commits.

### 49.4. wal_level=minimal

Never use when production architecture requires physical/logical replication or WAL archiving.

## 50. Checkpoints and Crash Recovery

Checkpoint frequency affects how much WAL must be replayed after a crash, while recovery time also depends on:
- WAL generation rate.
- Number of WAL segments since the checkpoint.
- Storage read throughput.
- Number of data pages needing redo.
- Shared buffers/cache state.
- Hardware/VM startup time.
- Recovery conflicts and replay behavior.

### 50.1. Do Not Infer Recovery Time Solely from max_wal_size

`max_wal_size` is a soft threshold, and retained WAL can be larger. Run crash-recovery drills in a representative environment.

### 50.2. Checkpoints Do Not Replace Backups

Checkpoints aid crash recovery of the current cluster. They do not provide an immutable history to recover accidentally deleted data or a destroyed database.

### 50.3. PITR

PITR requires base backups and continuous WAL archiving across your retention window. Measure restore/replay duration as part of RTO validation.

## 51. Checkpoints and Standby Restartpoints

Physical standbys also rely on restartpoints to manage recovery state while replaying WAL. Checkpoint settings and WAL retention affect restartpoint behavior.

### 51.1. Standby Lag

If standby replay lags, a primary slot retains WAL. Never tune checkpoints on the primary while ignoring standby disk/network/replay capacity.

### 51.2. Restartpoint Stats

Some checkpoint statistics views include restartpoint counters. Interpret according to your version.

### 51.3. Recovery Conflicts

Hot standby queries can conflict with WAL replay. Tuning `max_standby_streaming_delay`/`hot_standby_feedback` carries trade-offs across query availability, replay lag, and upstream bloat; do not mix with checkpoint tuning without measuring separately.

## 52. Impact of archive_timeout

`archive_timeout` forces PostgreSQL to switch to a new WAL segment after the configured interval during low-write workloads.

### 52.1. When Helpful

Reduces waiting time before a segment is archived in low-WAL workloads requiring archive freshness.

### 52.2. When Too Low

Creates many small/partially filled archive files, raising request, metadata, and storage overhead. Choose based on RPO, archive tooling, and storage behavior.

### 52.3. Does Not Replace Synchronous Replication

Archive freshness does not mean a standby has received/replayed WAL. Archiving and replication serve different goals.

## 53. Generating Less WAL Through Workload Design

### 53.1. Reduce Index Count

Every index adds write work. Evaluate query benefit, uniqueness, and constraint needs before removing indexes.

### 53.2. HOT-Friendly Schema

Avoid indexing frequently updated columns unnecessarily; pick an appropriate `fillfactor` to leave room for HOT updates.

### 53.3. Batch Changes

Group appropriate operations to cut round trips and commit overhead, while keeping transactions short enough to avoid lock/rollback/vacuum issues.

### 53.4. Avoid Rewriting Entire Rows

Update only changed columns and filter out rows whose values do not actually differ.

### 53.5. Partition Lifecycle

Drop/detach partitions on retention schedules instead of deleting row by row where the data model fits.

### 53.6. Bulk Imports

Use `COPY` and staging strategies; verify WAL/replication/backup impact. Logged data still requires WAL for durability.

## 54. Capacity Planning for WAL

Estimate retained WAL from generation rate and how long consumers can be disrupted.

~~~text
WAL retention budget
  = normal WAL working set
  + peak WAL rate x outage duration
  + archive/replication recovery margin
  + operational headroom
~~~

### 54.1. Peak Rate

Use peak/percentile WAL rates rather than low averages. Bulk loads and batch jobs create spikes.

### 54.2. Outage Duration

Choose a duration sufficient to detect, repair, and recover archive/standby/CDC consumers.

### 54.3. Disk Safety

Set warning/critical alerts well before the volume fills. If WAL lives on a dedicated volume, alert on that volume.

### 54.4. Slot Cap

`max_slot_wal_keep_size` protects disks yet invalidates stalled slots' ability to resume. Your runbook must include consumer resync procedures.

## 55. Changing Settings Safely

### 55.1. Check Context

`pg_settings.context` shows whether a setting requires a restart, reload, or can be set at session/user/database scope.

### 55.2. Check pending_restart

~~~sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_wal_size',
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'wal_compression',
    'wal_buffers'
)
ORDER BY name;
~~~

### 55.3. Change via Configuration Management

Keep one canonical configuration source, review changes, and document rationale/owner. Avoid ad hoc edits across multiple places that cause config drift.

### 55.4. Restart/Reload

Reload/restart according to your HA topology, rolling strategy, and maintenance policy. Settings requiring restarts need failover/availability planning.

### 55.5. Roll Back Settings

Record prior values and rollback steps. After reverting, observe at least one full checkpoint cycle and workload peak.

## 56. Recommended Monitoring Dashboard

| Panel | Metrics | Purpose |
| --- | --- | --- |
| WAL generation | `wal_bytes/sec`, `wal_records/sec` | Rate of WAL creation |
| FPI ratio | `wal_fpi`, `wal_records` | Full-page-image overhead |
| Checkpoint frequency | timed/requested checkpoints | Detect checkpoint pressure |
| Checkpoint duration | write/sync time | Storage/checkpoint latency |
| WAL directory | `pg_wal` bytes/files | Disk retention |
| Replication lag | sent/write/flush/replay LSN | Standby progress |
| Slot retention | `restart_lsn`, `confirmed_flush_lsn` | WAL pinned by consumers |
| Archive status | `archived_count`, `failed_count` | Archive health |
| Commit latency | p50/p95/p99 | Application durability path |
| Wait events | WAL/IO/checkpoint waits | Backend bottlenecks |
| Storage | IOPS, throughput, latency, queue | Device capacity |
| Backend writes | backend/checkpointer/bgwriter I/O | Dirty buffer behavior |

### 56.1. Alert Examples

- Requested checkpoints exceed baseline over multiple intervals.
- Checkpoint sync time spikes suddenly.
- WAL bytes/sec exceeds capacity budget.
- `pg_wal` volume free bytes drop below reserve.
- Archive `failed_count` rises.
- Inactive slot retains WAL too long.
- Replication lag exceeds RPO budget.
- p99 commit latency breaches SLA.
- Storage latency/queue depth exceeds baseline.

### 56.2. Contextual Alerts

Include in alerts: current value, baseline, delta/rate, affected volume, slot name, checkpoint count, database, timestamp, and dashboard link.

## 57. Troubleshooting: Checkpoints Happening Too Frequently

Possible causes:
- `max_wal_size` is too low for WAL generation.
- Bulk write workload.
- High FPI volume.
- Logical WAL overhead.
- Archive/slot retention growing `pg_wal` and masking pressure.
- Manual `CHECKPOINT` calls or maintenance jobs.

Remediation:
1. Inspect checkpoint stats and logs.
2. Compute WAL bytes/sec.
3. Separate timed vs. requested checkpoints.
4. Check `max_wal_size` and `checkpoint_timeout`.
5. Check `pg_wal`, slots, and archiving.
6. Increase `max_wal_size` if storage and recovery budgets allow.
7. Benchmark and measure checkpoint/commit latency.

## 58. Troubleshooting: pg_wal Growing Nearly Full

1. Measure `pg_wal` size and filesystem free space.
2. Check `pg_stat_archiver`.
3. Check `pg_replication_slots` and inactive consumers.
4. Check standby/logical subscriber lag.
5. Check `wal_keep_size` and `max_slot_wal_keep_size`.
6. Measure WAL generation rate.
7. Fix archive/consumer issues before dropping slots.
8. Expand the volume if needed to buy investigation time.
9. Never delete WAL segments manually.
10. Verify segment recycling resumes after resolving retention issues.

## 59. Troubleshooting: Rising Commit Latency

1. Measure p95/p99 commit latency.
2. Check `synchronous_commit`.
3. Check synchronous standby state.
4. Read WAL write/sync timings.
5. Check wait events.
6. Measure storage flush latency.
7. Check network latency to standbys.
8. Check group commit/transaction batching.
9. Never weaken durability mode without RPO approval.
10. Re-test with a representative workload.

## 60. Troubleshooting: Storage Write Latency Spikes During Checkpoints

1. Read checkpoint logs and write/sync times.
2. Correlate storage IOPS/throughput/queue depth.
3. Check `checkpoint_completion_target`.
4. Check `max_wal_size` and `checkpoint_timeout`.
5. Inspect backend writes and background writer.
6. Check concurrent bulk loads/index builds.
7. Calculate headroom before raising WAL thresholds.
8. Benchmark checkpoint pacing.
9. Consider upgrading storage throughput if device saturation is the cause.
10. Verify application latency after changes.

## 61. Common Anti-Patterns

| Anti-pattern | Consequence | Correct approach |
| --- | --- | --- |
| Lowering `max_wal_size` to stop `pg_wal` growth | More frequent checkpoints; does not fix slot/archive retention | Find why WAL is retained |
| Raising `max_wal_size` unbounded | Volume can fill; recovery/retention budget loses control | Compute WAL rate and disk headroom |
| Turning off `fsync` | Risk of data loss/corruption after crash | Keep durability and fix storage bottleneck |
| Turning off `full_page_writes` | Increases risk of torn-page damage | Keep protection; inspect FPI/`wal_compression` |
| Setting `synchronous_commit=off` globally | Unintended RPO relaxation | Apply selectively only for tolerable data |
| Confusing checkpoint with commit | Mistuning the wrong target | Separate WAL flushes from data-page writes |
| Looking only at `wal_bytes` | Blind to where WAL is pinned | Monitor `pg_wal`, slots, and archive |
| Looking only at `pg_wal` size | Blind to WAL generation rate | Use `pg_stat_wal` deltas |
| Raising `wal_buffers` without measuring | Fails to fix storage bottlenecks | Check `wal_buffers_full` and sync latency |
| Tuning bgwriter without benchmarking | Raises background I/O contention | Monitor backend writes and `pg_stat_io` |
| Tuning multiple settings at once | Cannot attribute what caused the outcome | Change one group at a time |
| Running short benchmarks | Misses checkpoint cycles | Test across multiple cycles |
| Ignoring p99 | Good throughput yet bad tail latency | Measure percentile latency |
| Ignoring replication lag | WAL retention and RPO exceed budget | Monitor standbys/slots |
| Ignoring archive failures | `pg_wal` can grow until disk fills | Alert on archive errors |
| Using unlogged tables for critical data | Data lost on crash and missing from replicas | Use only for reconstructible data |
| Oversized batch transactions | Locks, rollbacks, and WAL bursts | Benchmark batch sizes |
| Not recording old settings | Hard to roll back | Version configs and change logs |

## 62. PostgreSQL Practice Exercises

Run in lab/staging. Never disable `fsync`/`full_page_writes` or alter production durability settings just to experiment.

1. **WAL:** diagram write-ahead logging.
2. **Commit:** explain how commit flush differs from checkpoint.
3. **Dirty buffers:** generate an `UPDATE` workload and observe checkpoint behavior.
4. **LSN:** read `pg_current_wal_lsn()`.
5. **WAL delta:** compute bytes between two LSNs.
6. **WAL files:** measure `pg_wal` size using a supported method.
7. **wal_level:** read current `wal_level`.
8. **Replication:** identify the `wal_level` required for physical replication.
9. **Logical:** identify the `wal_level` required for logical decoding.
10. **Checkpoint timeout:** read `checkpoint_timeout`.
11. **Max WAL:** read `max_wal_size` and `min_wal_size`.
12. **Completion target:** read `checkpoint_completion_target`.
13. **Logging:** enable `log_checkpoints` in a lab.
14. **Checkpoint warning:** configure `checkpoint_warning` and inspect logs.
15. **Timed checkpoints:** collect checkpoint statistics.
16. **Requested checkpoints:** compare timed vs. requested counters.
17. **Version:** compare checkpoint stats on PostgreSQL 16 vs. 17+.
18. **WAL stats:** read `pg_stat_wal`.
19. **WAL rate:** compute `wal_bytes/sec` from two snapshots.
20. **FPI:** monitor `wal_fpi`.
21. **FPI ratio:** compare FPI against WAL records.
22. **Compression:** read `wal_compression`.
23. **WAL compression:** benchmark compression in a lab.
24. **wal_buffers:** read `wal_buffers` and `shared_buffers`.
25. **Buffer full:** monitor `wal_buffers_full`.
26. **WAL writer:** read `wal_writer_delay`.
27. **Flush after:** read `wal_writer_flush_after`.
28. **Background writer:** read `pg_stat_bgwriter`.
29. **pg_stat_io:** read I/O stats on PostgreSQL 16+.
30. **Backend writes:** observe backend write counters for your version.
31. **Checkpoint pacing:** test two `checkpoint_completion_target` values in a lab.
32. **Checkpoint interval:** test different `checkpoint_timeout` values.
33. **Max WAL:** vary `max_wal_size` and observe requested checkpoints.
34. **Recovery:** measure crash recovery time on lab snapshots.
35. **WAL retention:** create a physical replication slot and track retained WAL.
36. **Logical slot:** create a lab logical consumer and monitor `restart_lsn`.
37. **Archive:** read `pg_stat_archiver`.
38. **Archive failure:** simulate archive failure and observe `pg_wal` growth.
39. **wal_keep_size:** read the setting and explain its semantics.
40. **Slot cap:** study `max_slot_wal_keep_size` and invalidation risk.
41. **Wait events:** observe `WALWrite`/`WALSync` where shown by version.
42. **Checkpoint waits:** observe I/O/checkpoint wait events.
43. **Storage:** run `iostat` or provider metrics during workload tests.
44. **Commit latency:** measure p50/p95/p99 commit latency.
45. **synchronous_commit:** read the current mode.
46. **Commit off:** benchmark `synchronous_commit=off` strictly in a lab and evaluate the data-loss window.
47. **Local:** compare `local` vs. `on`.
48. **Remote write:** study `remote_write` semantics.
49. **Remote apply:** study `remote_apply` and visibility.
50. **Synchronous standby:** configure `synchronous_standby_names` in a lab.
51. **Replication latency:** measure network/flush/apply latency.
52. **fsync:** verify `fsync=on` and read documentation.
53. **Full page writes:** verify `full_page_writes=on`.
54. **Sync method:** run `pg_test_fsync` on a test host.
55. **Commit delay:** read `commit_delay`/`commit_siblings`.
56. **Group commit:** generate a concurrent commit workload and measure throughput.
57. **Batch insert:** compare single-row vs. multi-row `INSERT`.
58. **COPY:** benchmark `COPY` vs. `INSERT`.
59. **Batch size:** test multiple transaction batch sizes.
60. **WAL per row:** compute WAL bytes/inserted row in a controlled test.
61. **Index overhead:** benchmark inserts with varying index counts.
62. **HOT update:** create a HOT-friendly workload and check `n_tup_hot_upd`.
63. **Fillfactor:** benchmark two `fillfactor` values on a lab table.
64. **No-op update:** measure WAL when updating to the same value vs. skipping unchanged rows.
65. **Partition retention:** compare mass `DELETE` vs. dropping a partition.
66. **Unlogged:** create an unlogged staging table and observe crash/replication semantics in a lab.
67. **Bulk load:** measure WAL/checkpoint impact during large data imports.
68. **Maintenance:** benchmark index builds and `maintenance_work_mem`.
69. **Vacuum:** observe autovacuum during a write-heavy workload.
70. **WAL compression:** compare WAL bytes and CPU.
71. **Checkpoint alert:** build an alert for abnormal requested checkpoint spikes.
72. **WAL alert:** build an alert on WAL bytes/sec.
73. **Disk alert:** build an alert when `pg_wal` volume free space drops below reserve.
74. **Slot alert:** alert on inactive slots retaining WAL.
75. **Archive alert:** alert on rising archive `failed_count`.
76. **Runbook:** write a procedure for overly frequent checkpoints.
77. **Runbook:** write a procedure for high commit latency.
78. **Runbook:** write a procedure for `pg_wal` nearly full.
79. **Benchmark:** compare baseline and tuned configurations across multiple checkpoint cycles.
80. **Comprehensive design:** build a tuning plan for a write-heavy workload covering checkpoint/WAL capacity, durability, synchronous replication, SQL write amplification, monitoring, benchmarks, and rollback strategy.

## 63. Checkpoint, WAL, and Write Workload Tuning Checklist

### Baseline

- [ ] Measure TPS, rows/sec, and commit latency percentiles.
- [ ] Measure WAL bytes/sec and WAL bytes/transaction.
- [ ] Record timed/requested checkpoint counts.
- [ ] Record checkpoint write/sync durations.
- [ ] Measure FPI ratio.
- [ ] Measure replication lag and archive backlog.
- [ ] Measure storage IOPS, throughput, latency, and queue depth.
- [ ] Record filesystem free space and WAL retention.

### Checkpoint/WAL

- [ ] `checkpoint_timeout` matches recovery budget.
- [ ] `max_wal_size` matches WAL rate and disk headroom.
- [ ] `min_wal_size` matches WAL reuse.
- [ ] `checkpoint_completion_target` spreads writes sensibly.
- [ ] `log_checkpoints` enabled during investigation.
- [ ] `wal_compression` benchmarked.
- [ ] `wal_buffers` kept auto unless evidence justifies changing.
- [ ] Slots/archive/standby retention monitored.

### Durability

- [ ] `fsync` remains enabled.
- [ ] `full_page_writes` remains enabled.
- [ ] `wal_level` matches replication/archiving.
- [ ] `synchronous_commit` matches RPO.
- [ ] Synchronous standby policy tested.
- [ ] Storage flush semantics verified.

### Write Workload

- [ ] Indexes reviewed.
- [ ] HOT update opportunities examined.
- [ ] Fillfactor benchmarked.
- [ ] No-op updates eliminated where applicable.
- [ ] Batch sizes benchmarked.
- [ ] `COPY` used for bulk loads where appropriate.
- [ ] Partition retention evaluated.
- [ ] Transaction duration kept short.

### Change Control

- [ ] One setting group changed at a time.
- [ ] Tests span multiple checkpoint cycles.
- [ ] p95/p99 latency compared.
- [ ] WAL/disk/replication/backup health verified.
- [ ] Old values and rollback procedures documented.

## 64. Summary

Checkpoints, WAL, and write workloads form three interconnected parts of PostgreSQL's write path:

~~~text
APPLICATION WRITES
       |
       v
WAL RECORD GENERATION
       |
       v
WAL BUFFER / WAL FILE
       |
       +---- Commit durability / replication
       |
       v
DIRTY DATA PAGES
       |
       v
CHECKPOINT / BACKGROUND WRITER
       |
       v
DATA FILES
~~~

Key principles:

- **WAL flush and checkpoint are two distinct operations.** Commits can be durable before data pages are checkpointed.
- **Checkpoints can be triggered by time or WAL volume.** Separate timed vs. requested checkpoints before tuning.
- **`max_wal_size` is a soft threshold, not a hard cap.** Replication slots, archiving, and WAL retention can grow `pg_wal` beyond it.
- **`checkpoint_completion_target` paces checkpoint writes.** It does not increase physical storage throughput.
- **Full-page images protect against torn-page writes.** Keep `full_page_writes` enabled; consider `wal_compression` if FPIs dominate WAL and CPU has headroom.
- **Tune `wal_buffers` and background writer only when counters reveal a bottleneck.** They do not substitute for sufficiently fast storage.
- **`synchronous_commit` governs durability/acknowledgement.** Evaluate RPO before changing, especially for `off` or remote modes.
- **Never disable `fsync` or `full_page_writes` for production speed.** Address storage, write amplification, and checkpoint pressure instead.
- **SQL/schema design heavily influences WAL.** Cut unnecessary indexes, leverage HOT updates, avoid no-op updates, and pick sensible transaction batches.
- **Benchmarks must span multiple checkpoint cycles.** Measure throughput, p99 latency, WAL rate, checkpoint stats, replication, and recovery behavior.

Good tuning is not about minimizing WAL or making checkpoints as rare as possible. The goal is to maintain RPO-compliant durability, keep recovery within budget, smooth I/O steadily, prevent WAL volume from exhausting capacity, and serve write workloads with predictable latency.
