# Monitoring WAL, Archiving, Replication Slots, and Replication Lag in PostgreSQL

PostgreSQL uses the Write-Ahead Log (WAL) to recover databases after crashes and stream changes from primary to standby. In production, seeing a standby report `streaming` is not enough to declare the system safe. WAL can be generated faster than it can be shipped or replayed; archiving can stall silently; replication slots can retain excessive WAL; the `pg_wal` filesystem can fill up; and lag metrics can mislead operators during quiet write periods.

WAL monitoring must answer four questions: how fast is the primary generating WAL, how far has WAL archiving progressed, how much WAL are replication consumers retaining, and what position has each standby received, written, flushed, and replayed? These questions are related yet distinct. WAL archiving serves backups/PITR and recovery after disruptions; replication slots retain WAL needed by consumers; streaming replication transfers WAL directly; and lag measures distance between positions in the WAL stream.

This lesson belongs to the **Monitoring** chapter of the *Database Engine Relational PostgreSQL* module. We will move from WAL and archiving internals to catalog views, SQL queries, metrics, alerts, capacity planning, troubleshooting, and hands-on operational labs. Column and function names can vary across major versions; examples target modern PostgreSQL and should be verified against the manual for your deployed release.

> **Operational principle:** Monitor WAL generation, archive progress, slot retention, and replication progress independently. Never rely on a single “replication lag” number to represent all layers.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe WAL's role in crash recovery, replication, and PITR.
2. Distinguish WAL generated, written, flushed, sent, received, and replayed.
3. Understand segment files, timeline history, and archive status files.
4. Configure and monitor WAL archiving via `archive_mode`, `archive_command`, or `archive_library`.
5. Explain the roles of `archive_timeout` and `pg_switch_wal()`.
6. Read metrics in `pg_stat_archiver`.
7. Distinguish archive failures, archive backlogs, and WAL retention.
8. Inspect the archive queue via the archive status directory where supported.
9. Distinguish physical and logical replication slots.
10. Read `restart_lsn`, `confirmed_flush_lsn`, `catalog_xmin`, and slot statuses.
11. Estimate how much WAL a slot retains.
12. Understand the effects of `max_slot_wal_keep_size`, `wal_keep_size`, and `max_wal_size`.
13. Monitor WAL senders via `pg_stat_replication`.
14. Monitor WAL receivers via `pg_stat_wal_receiver`.
15. Measure sent/write/flush/replay gaps in bytes.
16. Interpret lag time fields and their limitations.
17. Estimate WAL generation rates using `pg_stat_wal`.
18. Monitor logical replication consumers and slot inactivity.
19. Design alerts for archiving, slots, disk capacity, and replication lag.
20. Troubleshoot failing archive commands, slot WAL retention, standby lag, and growing WAL disks.
21. Establish retention policies for archives and replication slots.
22. Conduct labs measuring WAL, checking archiving, and simulating slot backlogs.
23. Build dashboards and runbooks for WAL monitoring in production.

## 2. What Is WAL and Why Monitor It?

WAL records the changes required for PostgreSQL to recover a database after a crash. Before modified data pages are flushed to data files, corresponding WAL records must be durably persisted per durability policy. Upon restart, recovery replays WAL to bring data files back to a consistent state.

WAL also powers:
- Physical streaming replication.
- WAL archiving and Point-in-Time Recovery (PITR).
- Logical decoding and logical replication.
- Certain backup, recovery, and replication tooling workflows.

### 2.1. WAL generation

Every data-modifying transaction generates WAL records. WAL volume depends on workload, index updates, full-page images, checkpoint timing, bulk operations, `wal_level`, `wal_compression`, and many other factors.

### 2.2. WAL segments

WAL is stored as segment files inside `pg_wal`. Segment size is fixed at cluster initialization—commonly 16 MB, though clusters can be initialized with other sizes. Do not hardcode segment size in monitoring without confirming your cluster's setting.

### 2.3. WAL LSN

A Log Sequence Number (LSN) represents a byte offset within the WAL stream. LSNs allow comparing progress between primary and standby within the same timeline and stream.

On the primary:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_flush_lsn() AS flushed_lsn;
```

### 2.4. WAL is not a human-readable row audit log

WAL is an internal binary format built for recovery and replication. Do not parse raw WAL files as a business audit log. Logical decoding or application audit events are far better suited for business-level change tracking.

### 2.5. Why WAL needs dedicated monitoring

WAL is a fast-growing resource that directly impacts availability:
- Broken archiving can prevent WAL recycling.
- Forgotten replication slots can pin WAL indefinitely.
- Slow standbys can accumulate large backlogs.
- A full WAL disk can halt writes on the primary.
- Missing archive segments can break PITR or standby recovery.

## 3. WAL States to Distinguish

A WAL record or segment progresses through several milestones:

```text
Primary transaction
      |
      v
 WAL generated
      |
      +---- local write / flush
      |
      +---- WAL sender ----> standby receive
      |                         |
      |                         v
      |                      write
      |                         |
      |                         v
      |                      flush
      |                         |
      |                         v
      |                      replay
      |
      +---- completed segment ----> archive
```

- **Generated:** WAL records produced by backends and background operations.
- **Written:** WAL bytes written to the OS; written is not necessarily durable.
- **Flushed:** WAL flushed to stable storage per OS/storage durability semantics.
- **Sent:** WAL sender has transmitted WAL over the network toward a standby.
- **Received:** standby received WAL over the network; received does not guarantee written or flushed.
- **Written/Flushed on standby:** standby wrote and flushed WAL to its storage.
- **Replayed:** recovery process applied WAL changes to standby data files.
- **Archived:** a completed segment has been transferred successfully to the archive destination.

Archiving operates on completed segment files rather than uploading each individual transaction commit separately.

## 4. Common LSN Positions and Functions

On the primary:

| Function | Meaning |
|---|---|
| `pg_current_wal_lsn()` | Current WAL write/insert position |
| `pg_current_wal_insert_lsn()` | Current WAL insert position |
| `pg_current_wal_flush_lsn()` | Current WAL flush position |
| `pg_wal_lsn_diff(a, b)` | Byte difference between two LSNs |

On a standby:

| Function | Meaning |
|---|---|
| `pg_last_wal_receive_lsn()` | Latest received WAL LSN |
| `pg_last_wal_replay_lsn()` | Latest replayed WAL LSN |
| `pg_last_xact_replay_timestamp()` | Timestamp of the last replayed transaction |
| `pg_is_in_recovery()` | Indicates whether the instance is in recovery/standby mode |

### 4.1. LSN comparisons are valid only within the same history

When a failover starts a new timeline, never compare LSNs across divergent histories while ignoring timeline IDs. LSN measures stream position, whereas timeline identifies the history branch.

### 4.2. LSN difference in bytes

```sql
SELECT
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        '0/5000000'
    ) AS bytes_since_position;
```

The result is a byte distance (returned as `numeric`). Use real LSNs from the same cluster and timeline.

### 4.3. NULL must be handled explicitly

Receive and replay functions can return NULL if a standby has not yet received/replayed WAL or no matching transaction exists. Monitoring must represent “no data” separately instead of coercing NULL to zero.

## 5. WAL Directory and Archive Status

Inside the data directory, PostgreSQL manages:
- `pg_wal`: active WAL segments, recycled segments, and related status data.
- `pg_wal/archive_status`: status markers indicating segments needing archiving or already archived.
- Timeline history files and recovery metadata files.

### 5.1. .ready and .done

Once a segment becomes eligible for archiving, PostgreSQL creates a `.ready` marker in `archive_status`. After the archive command or library reports success, PostgreSQL renames the marker to `.done`.

`.ready` indicates a file awaits archiver processing; `.done` indicates archiving succeeded per PostgreSQL's confirmation.

### 5.2. Never delete status markers manually

Never delete `.ready` files or rename them to `.done` manually to “clear a backlog.” Doing so can make PostgreSQL skip archiving required segments or archive inconsistently. Resolve the underlying issue through the archive mechanism and retention policy.

### 5.3. Archive destinations

Destinations can be local filesystems, network filesystems, object storage, or backup systems. Ensure:
- WAL filenames cannot overwrite silently.
- Uploads follow atomic/immutable semantics appropriate for the store.
- Success is reported only once the archived object is durably committed.
- Access permissions and credentials do not expire unexpectedly.
- Capacity, request failures, and upload latency are monitored.

## 6. How Does WAL Archiving Work?

When archiving is enabled, PostgreSQL's archiver process ships completed WAL segments to the archive destination.

Key parameters:
- `archive_mode`
- `archive_command` or `archive_library`
- `archive_timeout`

### 6.1. archive_mode

Common values:
- `off`: WAL archiving disabled.
- `on`: archives WAL generated on the primary.
- `always`: also archives WAL received while in recovery/standby mode, useful for certain cascading or backup topologies.

Changing `archive_mode` requires a server restart. Check `pg_settings.context` and the manual for your major version.

### 6.2. archive_command

`archive_command` is a shell command invoked by PostgreSQL with placeholders:
- `%p`: path to the source WAL file.
- `%f`: filename of the WAL segment to archive.

Illustrative filesystem destination example:

```conf
archive_mode = on
archive_command = '/usr/local/bin/archive-wal "%p" "%f"'
archive_timeout = '60s'
```

`/usr/local/bin/archive-wal` is an operator-supplied script example. It should accept the source path and filename, copy/upload the complete file, verify success, and return exit code 0 only when the archived object is durably available.

### 6.3. Archive commands must be idempotent

PostgreSQL may re-run the command if a previous attempt failed or a process was interrupted. Scripts must handle cases where the destination file already exists:
- If the destination file is byte-for-byte identical to the source, it may return success.
- If the destination file differs in content, fail loudly and preserve evidence.
- Never silently overwrite a differing archived object.
- On filesystems, copy to a temporary file and atomically rename within the same filesystem.
- On object storage, use atomic upload/commit semantics and verify object completeness.

### 6.4. Never return success prematurely

If a script merely enqueues an upload in the background and immediately exits 0, PostgreSQL marks the segment archived before transfer finishes. If the background worker crashes, the archive ends up missing a segment while the database believes it succeeded.

### 6.5. archive_library

Modern PostgreSQL versions support `archive_library` as an alternative to `archive_command`, providing archiving via a loadable extension/module. Do not configure both mechanisms incompatibly against version rules; consult version documentation and verify effective state.

### 6.6. Archive commands run as the PostgreSQL OS user

The script needs read permission on WAL files and write permission on the archive destination. Grant only least privilege. Protect credentials and avoid leaking secrets in command-line arguments or logs.

## 7. archive_timeout and WAL Segment Switches

The archiver processes only completed segments. On low-traffic systems, the current segment can remain open for a long time, delaying new archive objects even without errors.

### 7.1. archive_timeout

`archive_timeout` forces PostgreSQL to switch segments after the specified period whenever WAL activity has occurred, ensuring timely archiving on sparse workloads.

```conf
archive_timeout = '60s'
```

### 7.2. Timeout is not an upload deadline

`archive_timeout` does not guarantee an archived object appears in exactly 60 seconds. Archiving also depends on segment completion, process scheduling, destination throughput, and retries.

### 7.3. Partially filled archived segments

Forced switches produce many partially filled archive segments, raising object counts and storage overhead. Tune `archive_timeout` around RPO/PITR freshness, storage cost, and archive system capacity.

### 7.4. pg_switch_wal()

On a primary, you can manually force a switch to a new WAL segment:

```sql
SELECT pg_switch_wal();
```

Useful in labs or right after batch jobs to test archiving flows. It is not a substitute for monitoring and should not be scheduled on a tight loop in production.

### 7.5. Switching segments does not guarantee archive success

After calling `pg_switch_wal()`, inspect `pg_stat_archiver`, the archive destination, and `.ready`/`.done` markers. Do not assume success solely from the LSN returned by the function.

## 8. Monitoring with pg_stat_archiver

`pg_stat_archiver` exposes archiver statistics on the instance.

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

- `archived_count`: successful archives since last stats reset; this is a cumulative counter, not pending WAL files.
- `last_archived_wal`: filename of the most recently archived WAL segment.
- `last_archived_time`: timestamp of the last successful archive; an older timestamp during idle workloads is not automatically an error.
- `failed_count`: number of failed archive command/library attempts. Track the counter delta, not just raw totals.
- `last_failed_wal` and `last_failed_time`: most recent segment that failed archiving and when it failed.
- `stats_reset`: timestamp of last stats reset; exporters must track this to avoid negative deltas or false alerts.

### 8.1. pg_stat_archiver does not measure exact backlog

This view does not directly report `.ready` file counts, pending bytes, or the age of the oldest waiting segment. Combine it with archive status directory checks, filesystem/object-storage metrics, and WAL positions.

## 9. Counting Archive Backlog

On PostgreSQL versions providing `pg_ls_archive_statusdir()`, you can inspect status files:

```sql
SELECT
    count(*) FILTER (WHERE name LIKE '%.ready') AS ready_files,
    count(*) FILTER (WHERE name LIKE '%.done') AS done_files
FROM pg_ls_archive_statusdir();
```

Function availability and permissions depend on major version. Check the manual and role privileges before using this in an exporter.

### 9.1. Ready count and ready age

Steadily rising `.ready` files indicate the archiver cannot keep up, the destination is slow, or commands are failing. One `.ready` file lingering for a long time can be worse than many new files queued during a brief burst. Track the age of the oldest `.ready` file where possible.

### 9.2. Done count

`.done` files are not a backlog. They mark segments already archived and managed by PostgreSQL. Never alert on `.done` file counts alone.

### 9.3. Counting files from the OS

When using an OS exporter, read `pg_wal/archive_status` with appropriate read-only permissions and inspect status files only. Never modify or delete files while scraping.

## 10. Archive Freshness and Archive Gaps

Archive freshness measures elapsed time since the latest WAL segment was archived. Archive gap measures the distance between current WAL and the latest archive progress.

If the primary generates no new WAL, an older `last_archived_time` is normal. Compare against recent WAL generation, when the current segment opened, the `.ready` queue, and backup/PITR SLAs.

WAL filenames encode timeline and segment position. To detect gaps, use tools or code that understand WAL filename/timeline structure rather than naive lexicographic string sorting.

After promotion, PostgreSQL creates a new timeline and history file. Archive storage must retain both WAL segments and timeline history files so recovery can follow the proper branch. A gap can still exist in the middle due to a missing segment even if newer objects exist. Archive validation must verify continuity from the base backup all the way to the recovery target.

## 11. WAL Archives and PITR

WAL archiving enables replaying WAL from a base backup forward to a target point in time.

A complete recovery set requires:
- A valid base backup.
- Continuous WAL segments from backup start through recovery target.
- Relevant timeline history files.
- A working `restore_command` and archive access.
- Required backup metadata and encryption keys.

### 11.1. restore_command

Illustrative example:

```conf
restore_command = 'cp /srv/pg-archive/%f "%p"'
```

In production, the command must return non-zero when a file is absent, quote paths safely, and connect to the real archive store. With object storage, use the corresponding restore helper.

### 11.2. Archive completeness

An archive holding millions of objects can still be missing one small WAL segment. Periodic restore drills are the only way to verify true continuity.

### 11.3. Archive retention

Never delete archived WAL solely because a standby has replayed it. PITR retention must respect retained base backup sets, recovery windows, replicas/standbys needing WAL, legal/compliance retention, and archive lifecycle policies.

### 11.4. Archives and replication slots are independent

Archiving stores WAL externally for recovery and backups; slots prevent PostgreSQL from recycling WAL still needed by consumers. A healthy archive will not automatically let a connected standby catch up if slot/streaming configuration is broken; an active slot does not replace a PITR archive.

## 12. What Are Replication Slots?

A replication slot is primary-side state that retains WAL required by a replication consumer. Slots let consumers reconnect after disruptions without losing retained WAL.

Two main types:
- Physical replication slots.
- Logical replication slots.

### 12.1. Physical slots

Used by physical standbys or physical WAL consumers. `restart_lsn` records the earliest WAL position still required by the slot.

### 12.2. Logical slots

Used by logical decoding and logical replication. Logical slots track decoding/consumer progress and can retain both WAL and required catalog tuples.

### 12.3. Active vs. inactive slots

An active slot is currently in use by a connected consumer. An inactive slot still retains WAL. Long-inactive slots pose major disk growth risks.

### 12.4. Slots are not data copies

A slot is purely metadata and a retention pin. It holds no table rows, is not a backup, and does not archive WAL.

## 13. Creating and Managing Physical Replication Slots

Create a slot:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

Inspect slots:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Drop a slot only after confirming the consumer no longer needs it:

```sql
SELECT pg_drop_replication_slot('standby_a_slot');
```

Never drop an active slot or one still needed by a consumer. Confirm the standby has moved to another slot or has been decommissioned/rebuilt.

Name slots after clusters/consumers and maintain an inventory of owners and creation timestamps to prevent orphaned slots after consumer decommissioning. `pg_basebackup` has options to create replication slots during backups; verify slot creation, ensure standbys configure matching `primary_slot_name`, and never leave temporary slots inactive indefinitely.

Each physical standby should have its own dedicated slot when using physical slots. Multiple consumers must never share one slot.

## 14. Inspecting Replication Slots

Broadly compatible query:

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    catalog_xmin
FROM pg_replication_slots
ORDER BY slot_name;
```

Some columns may be NULL or unused depending on slot type.

- `restart_lsn`: WAL prior to this position may no longer be needed by this slot. If it lags far behind current WAL, the slot is retaining substantial WAL.
- `confirmed_flush_lsn`: especially relevant for logical slots; shows the position confirmed processed by the consumer. Do not interpret it as a physical standby replay position.
- `catalog_xmin`: logical slots can retain catalog tuples required for decoding. An old value can hinder vacuum cleanup and cause catalog bloat.
- `active`: `false` does not mean harmless. An inactive slot keeps pinning WAL until its consumer reconnects or the slot is cleaned up per policy.

Modern PostgreSQL versions may expose additional columns such as `wal_status`, `safe_wal_size`, `inactive_since`, or `invalidation_reason`. Verify the `pg_replication_slots` schema on your major version before writing exporters or queries referencing them.

## 15. Estimating WAL Retained by a Slot

On the primary, estimate the byte distance between current WAL and each slot's restart position:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    CASE
        WHEN restart_lsn IS NOT NULL
        THEN pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
    END AS retained_wal_bytes
FROM pg_replication_slots
ORDER BY retained_wal_bytes DESC NULLS LAST;
```

### 15.1. This is an LSN-based estimate

LSN distance does not equal exact filesystem bytes consumed. WAL segments are retained on segment boundaries, alongside preallocated/recycled files and other retention constraints.

### 15.2. Multiple slots can pin overlapping WAL ranges

Do not sum `retained_wal_bytes` across all slots to estimate `pg_wal` disk usage. Multiple slots often pin the same segments. Find the oldest required WAL position to understand the true retention floor.

### 15.3. Long-inactive slots

An inactive slot with an aging `restart_lsn` demands investigation. Check the consumer owner, last connection time, decommission status, and reseed options.

### 15.4. Logical slots and catalog retention

Besides WAL bytes, logical slots can pin `catalog_xmin`. Monitor transaction ID age and vacuum pressure in addition to disk usage.

## 16. Limiting WAL Retention

Key settings:
- `max_slot_wal_keep_size`
- `wal_keep_size`
- `max_wal_size`
- `min_wal_size`
- `max_replication_slots`
- `max_wal_senders`

### 16.1. max_slot_wal_keep_size

Caps how much WAL replication slots may force the server to keep. If a slot falls past this limit, PostgreSQL can recycle needed WAL and invalidate the slot for that consumer.

`-1` disables this cap, allowing a forgotten slot to grow `pg_wal` until disk exhaustion.

### 16.2. wal_keep_size

Retains a minimum amount of WAL so lagging standbys might catch up. It is not a hard upper cap and does not replace replication slots or archiving.

### 16.3. max_wal_size

A soft target for WAL volume between checkpoints under normal conditions. It does not stop `pg_wal` from exceeding this value when archiving or replication slots pin WAL.

### 16.4. min_wal_size

Controls how many WAL files PostgreSQL retains for reuse. It is not the minimum filesystem size required for `pg_wal`.

### 16.5. max_replication_slots and max_wal_senders

Provision enough capacity for all physical/logical consumers, backup clients, and expected connections. Insufficient slots or senders block new consumers from connecting.

### 16.6. Do not size limits from disk size alone

Account for peak WAL generation rates, expected standby/consumer offline windows, archive outage tolerance, disk headroom, reseed duration, recovery SLAs, slot count, and consumer types.

## 17. Slot Invalidation and Consumers Losing WAL

If PostgreSQL recycles WAL still needed by a slot, that consumer can no longer resume from its old position.

### 17.1. wal_status

On supported versions, `wal_status` reports states such as `reserved`, `extended`, `unreserved`, or `lost`. Exact semantics depend on version; `lost` indicates required WAL is gone and the slot can no longer resume normally.

### 17.2. safe_wal_size

Some versions expose `safe_wal_size`, estimating how much additional WAL can be generated before a slot risks crossing retention limits. Do not treat it as an exact time forecast since WAL generation rates fluctuate.

### 17.3. When a consumer cannot catch up

Once required WAL has been recycled, recover according to consumer type:
- Physical standby: reseed/rebuild from a base backup if missing WAL cannot be supplied.
- Logical subscriber: inspect slot state, consistency, and resnapshot/reinitialize using your tooling.
- Backup/PITR: fetch missing segments from the WAL archive if continuity is intact.

### 17.4. Never create a new slot to mask the failure

Creating a new slot at current WAL does not recover lost WAL. It simply starts retention from the new position; the consumer must be reinitialized to preserve data consistency.

## 18. Physical vs. Logical Slots: Key Differences

| Criterion | Physical Slot | Logical Slot |
|---|---|---|
| Consumer | Physical standby / WAL receiver | Logical decoding / subscriber |
| Retention position | `restart_lsn` | `restart_lsn` and `confirmed_flush_lsn` |
| Data format | Physical WAL | Logical changes decoded from WAL |
| Catalog retention | Does not hold `catalog_xmin` like logical slots | Can hold `catalog_xmin` |
| Consumer recovery | Catch up or reseed standby | Resume decoding or resnapshot |
| Use cases | HA/DR standbys | CDC, logical replication, integrations |

Logical slots retain WAL even when subscribers stop. If a consumer stays down while the slot remains, WAL accumulates. An aging `catalog_xmin` blocks catalog tuple cleanup and demands XID age and vacuum monitoring.

Failover-slot and primary/standby slot synchronization capabilities vary by major version. If you rely on logical slots across failovers, check feature support and configuration for your exact PostgreSQL version and tooling.

## 19. WAL Senders and pg_stat_replication

On the primary, `pg_stat_replication` lists directly connected standbys.

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
    replay_lag,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
```

- `state`: can be `startup`, `catchup`, `streaming`, etc.; healthy replication normally stays in `streaming`.
- `sent_lsn`: last WAL position sent over this connection.
- `write_lsn`: last position acknowledged written to OS by the standby.
- `flush_lsn`: last position acknowledged flushed by the standby.
- `replay_lsn`: last position replayed on the standby.
- `sync_state`: `async`, `potential`, `sync`, or `quorum` per configuration.

This view shows direct replication connections to the primary. Downstream standbys in cascading topologies do not appear as direct connections on the root primary.

## 20. Computing WAL Gaps Between Primary and Standby

Example on the primary:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS sent_to_write_bytes,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS write_to_flush_bytes,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS flush_to_replay_bytes,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS current_to_replay_bytes
FROM pg_stat_replication
WHERE state = 'streaming'
ORDER BY application_name;
```

- **Sent-to-write gap:** reflects network, receiver, or standby write pressure. If climbing steadily, inspect network throughput, receiver health, and standby I/O.
- **Write-to-flush gap:** reflects standby flush/storage latency—especially critical with synchronous commit `on`.
- **Flush-to-replay gap:** reflects recovery/replay bottlenecks, CPU/I/O contention, or hot standby query conflicts.
- **Current-to-replay gap:** total byte distance from primary current WAL to standby replay; useful as byte lag, though it does not directly give catch-up time.

Some LSNs may be NULL during startup or disconnected states. Monitoring should separate `no data`, `not streaming`, and `zero lag`.

## 21. Standby-Side Monitoring with pg_stat_wal_receiver

On a standby:

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

- `status`: receiver state such as `streaming` or other connection state. Zero rows means no active receiver connection existed at query time.
- `written_lsn` and `flushed_lsn`: track how far the WAL receiver has written and flushed.
- `last_msg_receipt_time`: detects receivers no longer receiving status messages; correlate with network and primary state.
- `latest_end_lsn`: latest WAL position reported by the sender.
- When the receiver disconnects, inspect logs, `primary_conninfo`, credentials, TLS, `pg_hba.conf`, network, and slot configuration.

## 22. Replay Lag and Timestamp Lag

On a standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_at,
    CASE
        WHEN pg_last_xact_replay_timestamp() IS NULL THEN NULL
        ELSE clock_timestamp() - pg_last_xact_replay_timestamp()
    END AS age_of_last_replayed_transaction;
```

### 22.1. Age is not absolute replication lag

If the primary commits no new transactions for 30 minutes, the standby's replay timestamp appears 30 minutes old even when the standby is completely caught up.

### 22.2. Clock skew

Timestamps between primary and standby can be skewed by clock drift. Synchronize clocks and never rely solely on timestamp age to make failover decisions.

### 22.3. Pair LSN gap with WAL generation rate

Byte lag paired with WAL bytes/second gives a better sense of catch-up time. Even then, replay throughput can differ from generation rate, so measure replay throughput directly.

### 22.4. Heartbeat transactions

A heartbeat table updated periodically on the primary lets standbys read a timestamp or sequence to measure end-to-end visibility. Heartbeats generate real WAL, so choose a sensible cadence and never let them replace LSN monitoring.

## 23. WAL Generation Rate with pg_stat_wal

Modern PostgreSQL versions provide `pg_stat_wal`:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
```

- `wal_bytes`: total WAL bytes generated since the last statistics reset. Compute deltas between two scrapes to estimate WAL generation rate.
- `wal_records` and `wal_fpi`: WAL record and full-page image counts.
- `wal_buffers_full`: counter of WAL buffer full events; interpret alongside workload and version.
- `wal_write` and `wal_sync`: WAL write and sync call counters per PostgreSQL stats.
- `wal_write_time`/`wal_sync_time`: timings populated when WAL timing statistics are enabled per configuration and version.

Exporters should sample at regular intervals:

```text
wal_rate_bytes_per_second =
    (wal_bytes_now - wal_bytes_previous)
    / elapsed_seconds
```

If `stats_reset` changes or counters drop, reset the baseline instead of reporting a negative rate.

## 24. Estimating Catch-Up Time

A simple approximation:

```text
estimated_catchup_seconds =
    outstanding_wal_bytes
    / effective_replay_bytes_per_second
```

This is strictly an approximation. Measure outstanding WAL bytes, standby receive throughput, standby replay throughput, ongoing primary WAL generation rate during catch-up, and network/storage contention.

If generation rate exceeds replay rate, the standby cannot catch up while workload continues generating WAL faster than replay processes it. Scale capacity or reduce the workload/lag source. When generation rate is below replay rate, the standby shrinks its backlog.

Measure receive and replay separately. A standby can receive WAL quickly while replaying slowly; watching network throughput alone misses recovery bottlenecks.

Never enforce one fixed byte threshold across every cluster. 100 MB of lag means very different things at 1 MB/s vs. 500 MB/s. Alerts should combine bytes, estimated catch-up time, and SLAs.

## 25. Logical Replication Monitoring

Logical replication uses different views than physical replication.

### 25.1. pg_stat_subscription

On the subscriber, this view displays worker/subscription states and LSN progress per version.

```sql
SELECT *
FROM pg_stat_subscription;
```

### 25.2. pg_stat_subscription_stats

Some versions expose subscription error counters such as apply errors and sync errors. Check the schema for your version.

### 25.3. Logical slots on the publisher

On the publisher, inspect `pg_replication_slots` for `active` state, `restart_lsn`, `confirmed_flush_lsn`, and `catalog_xmin`.

### 25.4. Logical lag differs from physical replay lag

Logical subscribers apply changes per table and publication semantics. Do not compare `confirmed_flush_lsn` directly against physical `replay_lsn` as the same metric.

### 25.5. Long-running transactions

Logical decoding may need to retain WAL starting from an uncommitted transaction's start position. A long-open transaction can stall `restart_lsn` advancement and grow WAL retention.

## 26. How Do Archiving and Slot Retention Interact?

WAL can be retained for multiple reasons:
- Not yet archived successfully.
- Needed by a physical replication slot.
- Needed by a logical replication slot.
- Retained under `wal_keep_size`.
- Needed by an active backup or recovery operation.
- Not yet recyclable under current checkpoint/recovery state.

A single consumer with an old restart position can pin segments that every other consumer has already processed. Inspect every slot and archive status to find the retention bottleneck.

If archiving fails while a slot is also inactive, WAL retention climbs rapidly. Alert on both archive failures and slot retained bytes.

When WAL is pinned by slots or archiving, `max_wal_size` is not a hard ceiling. The filesystem can still fill up.

Monitor filesystem free bytes/inodes and total `pg_wal` size using OS metrics or `pg_ls_waldir()` where supported and permitted. Never delete files in `pg_wal` via OS commands.

## 27. Inspecting WAL Files via SQL

On versions supporting `pg_ls_waldir()` with appropriate privileges:

```sql
SELECT
    count(*) AS wal_file_count,
    sum(size) AS wal_file_bytes,
    max(modification) AS newest_file_time,
    min(modification) AS oldest_file_time
FROM pg_ls_waldir();
```

This does not reflect full filesystem usage. The WAL directory holds non-segment files too, and filesystem allocation can differ from logical file sizes. Cross-check OS filesystem metrics.

Listing huge directories repeatedly adds overhead. Use reasonable exporter intervals and restricted privileges. Because `pg_wal` also holds status files, history files, and internal metadata, do not assume every entry is an archiveable segment.

## 28. WAL Monitoring Dashboard

A practical dashboard should include these panel groups:

**WAL generation**
- WAL bytes/sec.
- WAL records/sec.
- Full-page images/sec.
- WAL write/sync counters and latency.

**Archive**
- `archived_count` rate.
- `failed_count` rate.
- Last archived timestamp.
- Last failed WAL and timestamp.
- `.ready` file count and oldest `.ready` age.
- Archive destination upload failures and latency.
- Archive storage capacity.

**Replication slots**
- Active and inactive slot counts.
- Retained WAL bytes per slot.
- Oldest `restart_lsn`.
- Logical `catalog_xmin` age.
- Slot `wal_status` and `safe_wal_size` where supported.
- Slot owner and consumer identity.

**Physical replication**
- Standby `state` and `sync_state`.
- Sent-to-write, write-to-flush, and flush-to-replay gaps.
- Current-to-replay bytes.
- Receiver last message receipt time.
- Estimated catch-up time.

**Capacity**
- `pg_wal` filesystem bytes and inodes.
- Archive storage bytes and object counts.
- WAL generation forecast.
- Remaining slot headroom.

Tag every metric with cluster ID, node name, role, PostgreSQL major version, and standby `application_name`. Never mix metrics across clusters.

`wal_bytes`, `archived_count`, and `failed_count` are counters. Ready files, retained bytes, free disk, and lag bytes are gauges. Exporters must distinguish them to compute rates accurately.

## 29. Alerting: Archiving

Suggested alerts:

| Alert | Reference Condition | Meaning |
|---|---|---|
| Archive failures increasing | `failed_count` delta rising | Archive command, library, or destination failing |
| Archive stalled | Active WAL generation while last archive ages | Archiver is falling behind |
| Ready backlog growing | `.ready` count or oldest age climbing steadily | Archive queue is backed up |
| Archive destination unavailable | Object store or filesystem errors | WAL is not leaving the instance |
| Archive freshness SLA missed | Archive age breaches recovery objective | PITR recovery window at risk |
| Archive storage low | Free space below safety headroom | Archiving may soon fail |

When no new WAL is generated, emitting no new archive files is normal. Correlate with WAL generation and segment switches to verify whether archivable work exists.

A single transient archive failure can recover on retry. Alert on consecutive failures, file age, and backlog growth to suppress noise without ignoring critical failures.

## 30. Alerting: Replication Slots and WAL Disk

| Alert | Reference Condition | Meaning |
|---|---|---|
| Inactive slot too long | Slot inactive past policy window | Consumer may be abandoned |
| Retained WAL high | Retained bytes exceed budget | Slot is pinning heavy WAL |
| Slot near invalidation | Low `safe_wal_size` where available | WAL nearing retention limit |
| Slot lost | `wal_status` reports `lost` | Consumer likely needs reseed |
| Catalog xmin old | `catalog_xmin` aging excessively | Vacuum and catalog bloat risk |
| pg_wal disk high | Disk usage exceeds threshold | Primary risks running out of disk |
| WAL disk growth rapid | Growth rate exceeds forecast | Archive, slot, or standby backlog |

Do not alert merely on total slot counts. Map each `slot_name` to a consumer owner and type so responders know whom to page. A slot may go inactive temporarily during planned maintenance; base alerts on expected schedules and retention budgets.

Configure multi-tier disk alerts—for example, warning at 30% headroom and critical at 10% headroom or when estimated time-to-full drops below a safe margin. Tune values around actual WAL rates and operational response time.

## 31. Alerting: Replication Lag

Signals to monitor:
- Current byte lag.
- Lag growth rate.
- Receive/write/flush/replay gaps.
- Receiver last message age.
- Estimated catch-up time.
- Synchronous standby state/quorum.
- Application read-after-write SLAs.

Byte thresholds can catch large backlogs, provided they scale with WAL generation rate and storage capacity. Estimated catch-up time can be even more actionable than raw bytes if replay throughput is steady and measurable.

If the system requires synchronous durability, alert immediately whenever synchronous standbys drop below quorum or `sync_state` shifts unexpectedly. That can stall commits or violate durability policies.

Missing WAL receiver rows or stale last-message timestamps suggest connection failure. Check standby role and planned maintenance windows.

## 32. Capacity Planning for WAL and Archiving

Capacity forecasting requires:
1. Measuring peak and average WAL generation rates.
2. Measuring archive upload throughput and latency.
3. Defining tolerable archive outage duration.
4. Defining tolerable standby offline windows.
5. Calculating slot retention budgets.
6. Reserving capacity for backup/restore traffic and workload bursts.
7. Maintaining filesystem headroom for checkpoints and recovery.
8. Factoring in storage scaling speed and alert lead times.

### 32.1. Storage sizing example

Suppose peak WAL generation is 20 MB/s and the system must tolerate a 30-minute archive outage:

```text
20 MB/s × 30 × 60 s = 36,000 MB
approximately 36 GB of generated WAL
```

This is purely a baseline from an assumed peak rate. Add headroom, slot retention, concurrent consumers, and segment rounding overhead.

### 32.2. Archive destination capacity

Archives often retain weeks or months of WAL for PITR. Forecast using average WAL generation, retention days, compression ratios, and backup lifecycles.

### 32.3. WAL compression

Compression in archive tools or object storage cuts storage footprint, while adding CPU overhead and impacting throughput and restore speed. Never assume a fixed compression ratio.

### 32.4. Growth bursts

Index rebuilds, bulk loads, mass updates, and post-checkpoint full-page images can spike WAL generation sharply. Size around peak bursts and duration rather than daily averages.

## 33. Troubleshooting: Archive Failures

Symptoms:
- `failed_count` rising.
- `last_failed_wal`/`last_failed_time` updating.
- `.ready` files lingering.
- `pg_wal` growing.
- Logs reporting archive command failures.

Check in order:
1. PostgreSQL logs and exact command exit codes.
2. Is the archive destination reachable?
3. Are disk or object quotas exhausted?
4. Are OS permissions and credentials valid?
5. Are script paths and `%p`/`%f` quoting correct?
6. Does a differing file with the same name already exist at the destination?
7. Have TLS certificates or API credentials expired?
8. Is the archive tool hitting timeouts or rate limits?
9. Is the script returning 0 before upload completion?
10. Is storage or network latency exceeding budgets?

Fix the underlying issue, let PostgreSQL's retry loop run naturally, and verify `archived_count` climbs, `last_archived_wal` advances, and the `.ready` queue shrinks. Never delete marker files to force state.

When the command reports success, verify the destination object has the expected size/content and is readable. PostgreSQL archive success reflects only the exit status of the command or library.

Never run OS commands to delete files inside `pg_wal`. PostgreSQL manages WAL lifecycle; deleting segments breaks recovery.

## 34. Troubleshooting: Continuously Growing WAL Disk

Trace retention causes across categories:

**Archiving**
- Are archive commands failing?
- Is the `.ready` backlog growing?
- Are destination quotas or network paths failing?

**Replication slots**
- Is a slot inactive?
- Is `restart_lsn` lagging?
- Was a consumer decommissioned without dropping its slot?
- Is a long-running transaction stalling a logical slot?

**Standbys**
- Is a WAL receiver disconnected?
- Are network, write, flush, or replay lags climbing?
- Does the standby lack capacity?

**Configuration**
- Is `max_slot_wal_keep_size = -1`?
- Is `wal_keep_size` very large?
- Was `max_wal_size` mistaken for a hard cap?

Once the cause is isolated, restore archiving or the consumer, reconnect the standby, reseed consumers if WAL was lost, drop confirmed orphaned slots only after owner verification, or adjust retention limits aligned with RPO and capacity.

## 35. Troubleshooting: Rising Replication Lag

- **Sent-to-write climbing:** check network bandwidth, packet loss, receiver scheduling, and standby write throughput.
- **Write-to-flush climbing:** check standby storage latency, `fsync` performance, and I/O contention.
- **Flush-to-replay climbing:** check replay CPU/I/O bottlenecks, checkpoint activity, and hot standby query conflicts.
- **Receiver disconnected:** check `pg_stat_wal_receiver`, logs, `primary_conninfo`, authentication, TLS, `pg_hba.conf`, DNS, and slot status.
- **Lag climbs only during peak load:** compare WAL generation rate against receive/replay throughput. If generation persistently exceeds capacity, scale standby/network/storage or throttle write load.

## 36. Troubleshooting: Slot Retaining WAL While Consumer Is Inactive

1. List slot name, type, active state, and `restart_lsn`.
2. Identify the slot owner and consumer.
3. Check consumer logs and connection status.
4. Estimate retained WAL bytes.
5. Inspect `catalog_xmin` if it is a logical slot.
6. Confirm whether the consumer still needs the slot.
7. If the consumer needs the data, restore it before touching the slot.
8. If orphaned, get owner sign-off before dropping.
9. Drop the slot via an audited change process.
10. Monitor `pg_wal` afterward; WAL recycles according to checkpoints and remaining retention rules rather than shrinking instantaneously.

## 37. Troubleshooting: Stale Archive Freshness Without Errors

Check:
- Has new WAL activity occurred?
- Has the current segment switched yet?
- Is `archive_timeout` configured appropriately?
- Are any `.ready` files queued?
- Is `last_archived_time` old simply because the workload is idle?
- Did a timeline change or alternate archive path occur?

If the workload is idle with no closed segments pending, stale freshness is expected. If PITR monitoring requires regular archive heartbeats, generate controlled WAL activity/segment switches or run periodic archive restore checks.

## 38. Troubleshooting: Lost Slot or Standby Unable to Catch Up

Check slot status and logs. If `wal_status` reports `lost` or a receiver requests WAL that has already been recycled, the consumer cannot resume simply by reconnecting.

For physical standbys, supply missing WAL from the archive if `restore_command` is configured and archive continuity is intact; otherwise rebuild the standby from a base backup.

For logical consumers, evaluate resnapshot and reinitialization procedures. Never merely create a new slot and stream from current LSN, as all changes in between will be silently skipped.

To prevent recurrence, configure slot retention caps, monitor `safe_wal_size` where available, alert on inactive slots, and size retention for planned consumer outages.

## 39. Troubleshooting: Logical Slot Causing Catalog Bloat

Inspect `catalog_xmin` on the slot, long-running transactions, consumer progress (`confirmed_flush_lsn`), logical decoding worker state, vacuum activity, and transaction ID age.

If the slot is obsolete, confirm with its owner before dropping. If the consumer is still needed, restore progress or reinitialize using your replication tool. Do not blindly tune down vacuum thresholds to fight catalog bloat caused by a pinned slot.

## 40. Archiving on Standbys and Cascading Topologies

A standby can be configured to archive received WAL depending on topology goals and PostgreSQL version.

### 40.1. archive_mode=always

`always` enables archiving while in recovery/standby mode, useful in cascading or dedicated backup-offload topologies.

### 40.2. Archive destination must be designed safely

If both primary and standby archive to the same destination, handle timelines, file identity, and duplicate segments safely. Prefer archive systems that understand WAL/timelines and enforce immutable/idempotent semantics.

### 40.3. Standby archiving does not replace primary archiving policy

Define the authoritative archive source, failover behavior, and how WAL continuity is preserved across timeline switches.

### 40.4. Monitor archiving on the right node

`pg_stat_archiver` tracks statistics per instance. Scrape both primaries and archive-enabled standbys, tagging metrics by node and role so counters never get mixed.

## 41. Archive Cleanup and Retention

Archive cleanup must coordinate with backup catalogs and recovery windows.

- Never purge strictly by file age. An older WAL segment may still be required by a retained base backup.
- Use backup catalog tools that understand which WAL segments each backup set requires. Archive lifecycle rules must align with backup retention and WAL dependencies.
- `pg_archivecleanup` can be used in specific standby/archive cleanup workflows to remove WAL files older than a safe point. Do not use it as a global PITR retention manager without accounting for all retained base backups.
- Object storage lifecycle expiration must match backup retention and recovery objectives. Test restores from objects still inside the retention window.
- Never delete required timeline history files during cleanup. Recovery relies on them to identify timelines and follow the correct branch.

## 42. Archive Verification and Restore Drills

A healthy archive must be proven via real recovery tests.

Periodic drill procedure:
1. Select a base backup.
2. Choose a recovery target.
3. Provision an isolated restore environment.
4. Configure `restore_command`.
5. Restore the base backup.
6. Replay WAL up to the target.
7. Verify PostgreSQL startup and consistency.
8. Run smoke queries and application validation checks.
9. Record restore duration and any WAL gaps.
10. Remediate archive/backup issues if segments are missing or RTO is exceeded.

An existing file can still be truncated, corrupted, or missing its decryption key. Restore drills test both readability and continuity. `pg_stat_archiver` reporting success never proves a specific base backup has continuous WAL available to restore.

## 43. Monitoring WAL Write/Sync Latency

`pg_stat_wal` provides counters and timings when timing tracking is enabled.

```sql
SELECT
    wal_bytes,
    wal_records,
    wal_fpi,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
```

Timing fields may require `track_wal_io_timing` or equivalent configuration per version. Timing adds minor overhead; benchmark on real workloads.

Divide timing deltas by operation deltas for averages, while relying on OS/storage metrics or tracing to reveal tail latency. One slow sync can spike commit p99 while the average looks fine.

Newer PostgreSQL versions include `pg_stat_io` for I/O stats by backend, object, and context. Use it where supported and understand how WAL I/O maps, without letting it replace `pg_stat_wal` or OS metrics.

## 44. Checkpoints, Full-Page Images, and WAL Bursts

WAL generation can surge right after checkpoints because the first modification to each page writes a full-page image to WAL when `full_page_writes` and WAL settings apply.

Rising `wal_fpi` indicates more full-page images. Compare with `wal_records` and `wal_bytes`.

Checkpoint frequency and `checkpoint_timeout`/`max_wal_size` influence WAL volume, I/O, and FPI rates. Adjust checkpoint settings around workload patterns and crash recovery objectives.

`full_page_writes` is critical protection against torn pages and corruption. Never disable it casually to shrink archive volume.

Bulk loads, index rebuilds, large updates, and vacuum operations can trigger WAL bursts. Plan maintenance windows and watch archive/standby throughput during these events.

## 45. Security and Monitoring Permissions

Some views and functions require elevated privileges or monitoring roles.

- Use predefined monitoring roles rather than granting superuser to exporters unnecessarily.
- Functions such as `pg_ls_waldir()` and `pg_ls_archive_statusdir()` carry restricted permissions. Grant only what is needed and avoid exposing filesystem metadata to application roles.
- Never place cloud credentials or passwords in command text or logs. Use secret stores, service identities, or properly permissioned passfiles.
- Enforce TLS, encryption at rest, access controls, and immutable retention where required by business policy. Monitoring should alert on auth failures and encryption key expiration.

## 46. Lab: Inspecting WAL Positions

In a PostgreSQL lab, run on the primary:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
```

Run on the standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

Create a lab table and insert moderate data on the primary. Watch LSNs advance, record primary and standby LSNs at matching timestamps, and compute the byte gap using `pg_wal_lsn_diff()`.

Stop writing and watch timestamp lag grow. Note why an aging replay timestamp does not necessarily mean the standby is lagging.

## 47. Lab: Testing Archiving

Run only in a lab with an isolated archive destination.

1. Enable `archive_mode` (restarting as required).
2. Configure `archive_command` or `archive_library` targeting the lab destination.
3. Set a suitable `archive_timeout`.
4. Generate WAL activity.
5. Run on the primary:

```sql
SELECT pg_switch_wal();
```

6. Inspect the archiver:

```sql
SELECT *
FROM pg_stat_archiver;
```

7. Use `pg_ls_archive_statusdir()` if supported by your version, or inspect the filesystem via OS tools.
8. Confirm `.ready` clears and the archived object appears.
9. In the lab, make the destination unwritable; observe `failed_count`/`last_failed_wal`, logs, and `.ready` backlog growth.
10. Restore destination writability and confirm the archiver retries successfully.

## 48. Lab: Creating a Physical Replication Slot

On the lab primary:

```sql
SELECT *
FROM pg_create_physical_replication_slot('lab_standby_slot');
```

Inspect:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_replication_slots;
```

Configure `primary_slot_name` on the standby and verify `pg_stat_wal_receiver` displays that slot.

On the primary, check `active` and `restart_lsn`. Run write workloads and watch the slot position advance alongside the consumer.

Stop the standby cleanly in the lab, generate WAL on the primary, and observe `active=false` alongside rising retained WAL bytes. Restart the standby and verify catch-up while required WAL remains available. Avoid setting tiny limits that cause unintended slot invalidation in this lab.

## 49. Lab: Logical Slots and Consumer Lag

In a separate lab supporting logical decoding:
1. Create a publication/subscription or logical slot.
2. Run row-modifying workloads.
3. Inspect `pg_replication_slots`.
4. Stop the consumer.
5. Watch `restart_lsn`, `confirmed_flush_lsn`, and `catalog_xmin`.
6. Restart the consumer and confirm progress resumes.
7. Document the impact when a consumer stays down for an extended period.

Never create test logical slots in production without an owner and cleanup plan; slots can retain WAL and catalog tuples.

## 50. Lab: Measuring WAL Generation Rate

Sample `pg_stat_wal` twice over a fixed interval:

```sql
SELECT
    clock_timestamp() AS sampled_at,
    wal_bytes,
    wal_records,
    wal_fpi,
    stats_reset
FROM pg_stat_wal;
```

Compute byte deltas divided by elapsed seconds externally or in your monitoring system. If `stats_reset` changes, reset the baseline.

Compare idle, steady insert, and bulk update workloads in the lab. Record WAL bytes/sec, replication lag, and archive rate. Use a disposable cluster, bounded workload, and isolated storage—never benchmark on production.

## 51. Lab: Building Trend-Based Alerts

Create test dashboard/alert rules for:
- Rising archive `failed_count`.
- Growing `.ready` queue.
- Inactive slot retaining WAL past policy.
- Retained bytes exceeding budget.
- Growing standby sent-to-write gap.
- Growing flush-to-replay gap.
- Shrinking `pg_wal` disk headroom.
- Disconnected receiver.
- Synchronous standby failing quorum.

Simulate an idle period, a maintenance window, and a WAL burst to verify alerts distinguish idle states from genuine stalls.

Alerts must identify cluster, node, slot/archive file, metric, current value, threshold, and runbook link. Avoid generic “replication unhealthy” alerts.

## 52. Runbook: Archive Stalled

**Symptoms:** `failed_count` rising, `.ready` backlog growing, `pg_wal` growing.

1. Inspect PostgreSQL logs and archive command exit errors.
2. Check destination reachability, network, quotas, and permissions.
3. Identify the first WAL file stuck in the queue.
4. Check whether a conflicting or corrupted object already exists at the destination.
5. Fix the archive script or configuration through change control.
6. Verify the archiver retries and `archived_count` rises.
7. Verify the `.ready` backlog shrinks.
8. Verify archived objects are readable.
9. Assess PITR gaps and backup restore risk.
10. Monitor disk headroom until WAL recycles.

Never delete `.ready` markers or WAL segments to relieve disk pressure.

## 53. Runbook: Slot Retaining Excessive WAL

**Symptoms:** retained bytes climbing, slot inactive for a long time, `pg_wal` nearing capacity.

1. Identify slot name, type, and owner.
2. Check `active` state and last consumer connection.
3. Confirm whether the consumer still needs to resume from `restart_lsn`.
4. Estimate bytes and time remaining until disk exhaustion.
5. Restore the consumer if WAL is intact and data is needed.
6. If WAL was already lost, plan a reseed or resnapshot.
7. If orphaned, get owner sign-off and decommission cleanly.
8. Drop the slot through an audited procedure.
9. Monitor WAL recycling and filesystem recovery.
10. Configure retention limits and alerts to prevent recurrence.

Never drop a slot actively serving a consumer or solely because `active=false`.

## 54. Runbook: Rising Standby Lag

1. Identify standby `application_name` and `state`.
2. Verify receiver connection and last message timestamp.
3. Measure sent-to-write, write-to-flush, and flush-to-replay gaps.
4. Compare WAL generation rate with receive and replay throughput.
5. Check network RTT, bandwidth, and packet loss.
6. Check standby disk latency, CPU, and I/O.
7. Check hot standby query conflicts.
8. Check slot status and WAL retention.
9. Determine whether enough WAL remains to catch up or if a reseed is needed.
10. Assess failover eligibility and RPO if the primary fails.

## 55. Runbook: pg_wal Filesystem Nearly Full

1. Check free bytes/inodes and current growth rate.
2. Check archive failures and `.ready` backlog.
3. Check replication slots and oldest `restart_lsn`.
4. Check disconnected standbys and consumers.
5. Check for WAL generation bursts.
6. Identify the largest source of WAL retention.
7. Restore archiving/consumers or handle confirmed orphaned slots safely.
8. If needed, expand the filesystem per platform procedure.
9. Never delete WAL files manually.
10. Confirm WAL usage stabilizes and disk headroom recovers.

Do not simply raise `max_wal_size`. If WAL is pinned by slots or archiving, increasing `max_wal_size` can worsen filesystem pressure without fixing the root cause. Never drop all slots at once; each slot may belong to a critical standby or CDC consumer.

## 56. Best Practices

- Keep archive destinations independent of primary storage.
- Make archive commands idempotent and atomic per destination semantics.
- Return success only after the archived object is durably committed.
- Monitor both `pg_stat_archiver` and `.ready` backlogs.
- Evaluate archive freshness alongside WAL activity.
- Maintain base backups and regular PITR restore drills.
- Assign each standby/consumer its own dedicated slot where needed.
- Maintain an inventory of slot owners, purposes, and decommission workflows.
- Monitor inactive slots, retained bytes, and `catalog_xmin`.
- Size `max_slot_wal_keep_size` around storage capacity and recovery policy.
- Remember `max_wal_size` is a soft target, not a disk cap.
- Track sent/write/flush/replay gaps separately.
- Never rely on timestamp lag alone during idle periods.
- Measure both WAL generation rates and replay throughput.
- Alert on trends, age, and disk headroom.
- Never manually delete files inside `pg_wal` or `archive_status`.
- Verify monitoring view schemas and versions before deploying exporters.
- Keep monitoring credentials at least privilege.
- Standardize labels across PostgreSQL, DCS, backup, and infrastructure monitoring.

## 57. Common Misconceptions

### 57.1. “Zero errors in pg_stat_archiver means the archive is complete”

False. Archiver statistics do not prove continuous WAL exists for any specific base backup. Verify queues, object storage, and restore drills.

### 57.2. “archived_count is the number of files currently stored”

False. It is a cumulative counter of successful archives since the last stats reset.

### 57.3. “An old last_archived_time means archiving is broken”

Not necessarily. The primary may not have generated new WAL segments, or the current segment may not have switched yet.

### 57.4. “An inactive replication slot consumes no resources”

False. Inactive slots continue retaining WAL and catalog tuples.

### 57.5. “max_wal_size sets the hard maximum size of pg_wal”

False. Slot and archive retention can push WAL usage well past `max_wal_size`.

### 57.6. “wal_keep_size replaces replication slots”

False. It retains a minimum floor of WAL without guaranteeing long-offline consumers can catch up.

### 57.7. “A streaming standby means replay has caught up”

False. Received, written, flushed, and replayed LSNs can diverge significantly.

### 57.8. “Replay timestamp is exact replication lag”

False. Idle write periods and clock skew make last-transaction age misleading.

### 57.9. “Dropping a slot only deletes metadata”

False. It can allow needed WAL to be recycled, forcing the consumer to reseed or resnapshot.

### 57.10. “Successful archiving means the standby received the WAL”

False. Archiving and streaming replication are separate pipelines.

## 58. Quick Reference Table

| Need | View / Function / Parameter |
|---|---|
| Current WAL position | `pg_current_wal_lsn()` |
| Primary WAL flush | `pg_current_wal_flush_lsn()` |
| WAL bytes generated | `pg_stat_wal.wal_bytes` |
| Archive success/failure | `pg_stat_archiver` |
| Archive mode | `archive_mode` |
| Archive command | `archive_command` |
| Archive library | `archive_library` |
| Segment switch timeout | `archive_timeout` |
| Force segment switch (primary) | `pg_switch_wal()` |
| Archive status queue | `pg_ls_archive_statusdir()` if version supported |
| WAL directory listing | `pg_ls_waldir()` if version supported |
| Slot inventory | `pg_replication_slots` |
| Slot oldest WAL | `restart_lsn` |
| Logical consumer progress | `confirmed_flush_lsn` |
| Logical catalog retention | `catalog_xmin` |
| Slot WAL status | `wal_status`, version-dependent |
| Slot headroom | `safe_wal_size`, version-dependent |
| Primary standby status | `pg_stat_replication` |
| Standby receiver | `pg_stat_wal_receiver` |
| Standby receive position | `pg_last_wal_receive_lsn()` |
| Standby replay position | `pg_last_wal_replay_lsn()` |
| LSN byte difference | `pg_wal_lsn_diff()` |
| Logical subscriber workers | `pg_stat_subscription` |
| Slot retention limit | `max_slot_wal_keep_size` |
| Minimum WAL retention | `wal_keep_size` |
| Checkpoint WAL target | `max_wal_size` |

## 59. Official Reference Documentation

- [PostgreSQL 18 — WAL Internals](https://www.postgresql.org/docs/18/wal-internals.html): WAL files, records, and segment layout.
- [PostgreSQL 18 — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/18/continuous-archiving.html): archive setup, `restore_command`, and PITR.
- [PostgreSQL 18 — WAL Configuration](https://www.postgresql.org/docs/18/runtime-config-wal.html): `archive_mode`, `archive_command`, `archive_timeout`, and WAL parameters.
- [PostgreSQL 18 — Replication Configuration](https://www.postgresql.org/docs/18/runtime-config-replication.html): WAL senders, replication slots, and retention settings.
- [PostgreSQL 18 — Monitoring Statistics](https://www.postgresql.org/docs/18/monitoring-stats.html): `pg_stat_archiver`, `pg_stat_wal`, `pg_stat_replication`, `pg_stat_wal_receiver`, and other views.
- [PostgreSQL 18 — Administrative Functions](https://www.postgresql.org/docs/18/functions-admin.html): WAL, replication slot, and filesystem inspection functions.
- [PostgreSQL 18 — Logical Decoding](https://www.postgresql.org/docs/18/logicaldecoding.html): logical slots and decoding.
- [PostgreSQL 18 — Replication](https://www.postgresql.org/docs/18/high-availability.html): physical and logical replication overview.

Views, columns, and functions can differ across major versions. Before deploying exporters or production queries, verify the manual for your exact version and required permissions.

## 60. Summary

WAL monitoring must cover the entire lifecycle from generation through archiving and replay. Each WAL mechanism addresses a distinct need: archiving supports PITR and backups, replication slots pin WAL for consumers, streaming delivers WAL live, and LSN/lag metrics track node progress.

1. **WAL positions:** distinguish generated, sent, received, written, flushed, and replayed.
2. **Archiving:** track `pg_stat_archiver`, `.ready` backlogs, archive freshness, and restore drills. Archive success does not prove PITR completeness on its own.
3. **Replication slots:** monitor `active` state, `restart_lsn`, retained bytes, and `catalog_xmin`. Inactive slots still retain WAL.
4. **Retention:** `max_slot_wal_keep_size`, `wal_keep_size`, and `max_wal_size` carry distinct semantics. `max_wal_size` is not a hard cap on `pg_wal`.
5. **Replication lag:** measure sent-to-write, write-to-flush, and flush-to-replay gaps separately. Combine bytes, WAL rates, and catch-up throughput.
6. **Alerts:** alert on archive failures/backlogs, slot retention, receiver disconnects, sync state changes, WAL disk headroom, and lag growth.
7. **Recovery:** never manually delete WAL or status files; if a slot loses needed WAL, the consumer must be reseeded or resnapshotted.
8. **PITR:** maintain base backups, WAL continuity, archive retention, and regular restore drills.

A strong WAL dashboard lets operators answer immediately: how fast is WAL being generated, what is pinning WAL, is archiving continuous, which stage (receive, write, flush, or replay) is slowing standbys down, and how long remains before storage hits critical thresholds.
