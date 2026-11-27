# Replication Lag, Abandoned Slots, and Standby Missing WAL

Streaming replication lets PostgreSQL maintain a standby by sending and replaying WAL from the primary. Under normal operation, the standby receives new WAL records, writes them to local storage, and replays them to update data pages. If the network slows down, the standby cannot replay WAL fast enough, a replication slot retains WAL too long, or required segments have already been removed, the standby can lag behind or lose the ability to keep synchronizing.

Three related yet distinct scenarios often arise:

- **Replication lag:** the standby still receives WAL, but its receive, write, flush, or replay position trails behind the primary.
- **Abandoned replication slot:** a slot no longer has an active consumer yet continues retaining WAL, potentially growing `pg_wal` until disk fills up.
- **Standby missing WAL:** the standby requests a segment that the primary no longer retains in `pg_wal`; if the archive does not hold that segment either, the standby cannot resume recovery from its current position.

Proper investigation identifies the last WAL position processed by each component, which slot is retaining WAL, whether missing segments still exist in the archive, and whether the standby can catch up without rebuilding. Never manually delete files in `pg_wal` and never drop a slot without identifying its owning consumer.

## 1. How PostgreSQL Ships and Replays WAL

WAL (Write-Ahead Logging) records changes required for crash recovery and standby synchronization. In physical streaming replication, the main data flow consists of:

1. Backends on the primary generate WAL as transactions modify data.
2. The WAL sender reads WAL records and transmits them over the replication connection.
3. The WAL receiver on the standby receives data, writes it to local WAL segments, and flushes as required.
4. The startup process on the standby reads received WAL and replays it to update data pages.
5. The standby reports written, flushed, and replayed WAL positions so the primary tracks progress.

High-level diagram:

```text
Application writes
    |
    v
  PRIMARY
    |
    | WAL sender
    v
Network / replication connection
    |
    v
  STANDBY
    | WAL receiver
    v
WAL on standby disk
    | startup / recovery process
    v
Replay into data pages
    |
    v
Read queries on standby
```

Receiving WAL and replaying WAL are two separate stages. A standby may receive and flush nearly up to the primary yet lag in replay due to I/O, CPU, recovery conflicts, or read workloads. Conversely, the WAL receiver may stop receiving new data due to network or primary issues, stalling both receive and replay together.

## 2. Distinguishing Types of Replication Lag

In PostgreSQL, "lag" can refer to several distinct gaps. Distinguish them before changing configuration.

| Stage | Meaning | Potential Issues |
|---|---|---|
| Send | How far the primary has sent WAL | WAL sender, network, or standby not receiving fast enough |
| Write | How far the WAL receiver has written data | Standby disk write speed or buffering |
| Flush | How far WAL has been durably flushed | I/O, fsync, storage latency |
| Replay | How far the standby has applied WAL | CPU, I/O, recovery conflicts, large transactions |

LSNs (Log Sequence Numbers) mark positions in the WAL stream. Comparing LSNs determines the gap in bytes. Time lag and byte lag are not fully interchangeable: WAL generation rates fluctuate, and a small byte gap during a burst of heavy primary WAL generation can still correspond to noticeable time lag, or vice versa.

## 3. Checking Standby Progress from the Primary

On the primary, `pg_stat_replication` displays the status of directly connected standbys:

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

Key columns:

- `state`: WAL shipping state; typically `streaming` when a standby is streaming normally.
- `sync_state`: synchronization mode such as `sync`, `async`, or states tied to synchronous replication settings.
- `sent_lsn`: last WAL position sent.
- `write_lsn`: position written on standby.
- `flush_lsn`: position flushed on standby.
- `replay_lsn`: position replayed on standby.
- `write_lag`, `flush_lag`, `replay_lag`: recent lag intervals estimated from standby feedback; may be `NULL` when there are no recent transactions or suitable samples.

### Measuring WAL Distance in Bytes

You can compute the distance between the primary's current WAL position and each standby position:

```sql
SELECT
    application_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)::bigint
    ) AS not_yet_sent,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn)::bigint
    ) AS not_yet_written,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn)::bigint
    ) AS not_yet_flushed,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint
    ) AS not_yet_replayed
FROM pg_stat_replication;
```

These values represent LSN byte distances at query time, not time lag. If any LSN is `NULL`, the subtraction result is also `NULL`. Only compare LSNs belonging to the same timeline/WAL stream with a valid relationship.

### Pinpointing Which Stage Is Lagging

- `sent_lsn` far behind `pg_current_wal_lsn()`: primary is not sending fast enough or feedback has not updated; check WAL sender, network, and connection state.
- `write_lsn` behind `sent_lsn`: standby is not receiving or writing WAL fast enough.
- `flush_lsn` behind `write_lsn`: standby flush/storage may be the bottleneck.
- `replay_lsn` behind `flush_lsn`: standby receives WAL yet cannot replay fast enough; check recovery process, CPU, I/O, and conflicts.

Never draw conclusions from a single sample. Collect multiple samples over time to see whether the gap is widening, shrinking, or steady.

## 4. Checking the WAL Receiver on the Standby

On the standby, `pg_stat_wal_receiver` reports the state of the WAL receiving connection:

```sql
SELECT *
FROM pg_stat_wal_receiver;
```

Useful columns typically include receiver status, PID, source host/port, `slot_name`, latest received LSN, and last message timestamp. View columns can vary across PostgreSQL versions; run `SELECT *` to inspect actual fields before building fixed dashboards.

You can also inspect LSN helper functions on the standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_at;
```

`pg_last_wal_receive_lsn()` reflects the latest WAL location received, while `pg_last_wal_replay_lsn()` reflects the latest replayed location. The gap between the two reveals the replay backlog. If the WAL receiver is not running or has not received WAL, values may be `NULL` or fail to advance.

### Why `now() - pg_last_xact_replay_timestamp()` Can Mislead

This measures time elapsed since the last replayed transaction, not an absolute lag measurement in every scenario. When the primary has no new transactions, the timestamp ages even though the standby is completely caught up. Before any transaction is replayed, it may return `NULL`. On low-write workloads, use heartbeat transactions or combine LSN differences with WAL generation rate for reliable freshness tracking.

## 5. Distinguishing Network Lag from Replay Lag

If the WAL receiver maintains a stable connection and `received_lsn` advances while `replayed_lsn` stalls, the bottleneck lies after reception. Check:

- Whether standby CPU is saturated.
- Whether storage read/write latency or throughput is abnormal.
- Whether large transactions or bulk loads are running on the primary.
- Whether recovery conflicts occur with long-running queries on a hot standby.
- Whether checkpoints, autovacuum, or maintenance tasks compete for I/O.
- Whether recovery processes show progress in logs and metrics.

If both receive and replay stall, check:

- Network connectivity and packet loss.
- DNS, firewalls, routing, and TLS.
- Whether the WAL sender is still running.
- `primary_conninfo` and authentication credentials.
- Whether the primary restarted, failed over, or changed endpoints.
- Whether the replication slot still exists and retains required WAL.

Do not blindly raise `max_wal_senders` or `work_mem`. Identify the bottlenecked stage and measure relevant resources first.

## 6. What Are Replication Slots Used For?

A replication slot tells the primary from which WAL position a consumer still needs data. Slots prevent required WAL from being recycled prematurely before the consumer receives it.

There are two main types:

- **Physical replication slot:** typically used by physical standbys. It retains WAL needed so the standby can resume streaming from its confirmed position.
- **Logical replication slot:** used for logical decoding or logical replication. Beyond WAL, the slot can also retain catalog state needed by the consumer.

A slot does not ship data by itself. It only tracks position and governs WAL retention. A consumer must connect and advance for the slot to move forward.

### Creating a Physical Slot

Example creating a standby slot on the primary:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

The standby must reference the slot via `primary_slot_name` in its recovery configuration. Slot names must match and belong strictly to the intended consumer.

### Logical Slots

Logical slots are typically created by logical replication subscriptions or CDC connectors. A logical slot retains WAL until the consumer confirms processing up to that position. If a connector stops running while the slot remains, WAL continues accumulating.

A logical slot can also pin `catalog_xmin`, preventing vacuum from removing old catalog row versions. Hence, an abandoned logical slot impacts both WAL disk usage and catalog vacuum cleanup.

## 7. Finding Abandoned or Consumerless Slots

On the primary, inspect all slots:

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn,
    xmin,
    catalog_xmin,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
```

Columns like `wal_status` and `safe_wal_size` exist in newer PostgreSQL versions; omit them if your running version lacks them. `confirmed_flush_lsn` is primarily relevant for logical slots. `restart_lsn` is the earliest WAL position the slot still requires.

Signs that warrant investigation:

- `active = false` for an extended duration.
- The slot belongs to a decommissioned standby or connector.
- `restart_lsn` lags far behind current WAL.
- `wal_status` indicates extended WAL retention, unreserved status, or `lost` depending on version.
- `safe_wal_size` approaches `0` when slot WAL limits are configured.
- Old `xmin` or `catalog_xmin` persists, blocking vacuum from reclaiming obsolete versions.

`active = false` alone does not prove a slot is orphaned. A consumer might be paused for maintenance, or a standby intentionally shut down. Cross-check slot names against cluster inventory, `primary_slot_name` configs, subscriptions, CDC connectors, deployment schedules, and service owners before making changes.

### Estimating WAL Retained by a Slot

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS wal_distance
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;
```

This reports LSN distance from the slot to current WAL, not necessarily exact filesystem bytes inside `pg_wal`. WAL segments follow lifecycles tied to checkpoints, archiving, and other slots; check actual filesystem and `pg_wal` directory usage as well.

## 8. Why Do Abandoned Slots Fill the Disk?

The primary can only recycle or remove a WAL segment once it is no longer needed for crash recovery, archiving, and any WAL-retaining consumers. A slot with an old `restart_lsn` forces PostgreSQL to keep far more segments than normal workload requires.

Example:

1. A CDC connector creates a logical slot to stream WAL.
2. The connector is removed from infrastructure, yet the slot remains.
3. With no consumer advancing progress, `restart_lsn` stays frozen.
4. Applications keep writing data, continuously generating WAL.
5. The primary retains WAL because the slot still requires old segments.
6. `pg_wal` grows until it fills the filesystem.

If the filesystem holding `pg_wal` fills completely, PostgreSQL cannot write new WAL and risks halting or shutting down. Every slot must have a clear owner, progress SLA, lag alerts, and a decommissioning procedure.

### `max_slot_wal_keep_size`

`max_slot_wal_keep_size` caps how much WAL a replication slot may retain across checkpoints. `-1` imposes no limit under this setting; a slot can retain WAL indefinitely until the consumer advances or the slot is handled. A finite cap bounds disk exhaustion risk, but risks invalidating the slot if a consumer falls too far behind and required WAL is removed.

When a slot can no longer guarantee required WAL, PostgreSQL marks its status as `lost` on supported versions. The consumer can no longer simply resume from the old slot; determine whether missing WAL can come from the archive or whether the consumer/standby must be rebuilt.

### `wal_keep_size`

`wal_keep_size` directs the primary to retain a minimum volume of WAL in `pg_wal` to help lagging standbys over a bounded window. It is not a hard cap on total WAL retained and does not replace replication slots. If a standby stays offline too long or WAL generation exceeds that volume, older segments can still be recycled.

## 9. Settings Affecting WAL Retention

Review these parameters together:

| Parameter | Role | Risk if Misconfigured |
|---|---|---|
| `wal_level` | WAL detail level, e.g., `replica` or `logical` | Insufficient detail for required replication/decoding |
| `max_wal_senders` | Maximum concurrent WAL senders | Too few connections for standbys or consumers |
| `max_replication_slots` | Maximum replication slots | Unable to create new slots once limit is reached |
| `wal_keep_size` | Minimum WAL retained for standbys | Too low causes offline standbys to lose needed segments |
| `max_slot_wal_keep_size` | Cap on WAL retained by slots at checkpoints | Too low can strip needed WAL from a lagging slot |
| `archive_mode` | Enables WAL archiving | Disabled or broken leaves no backup WAL source |
| `archive_command` | Command saving segments to archive | Prolonged failures stall archiving and accumulate WAL |
| `primary_slot_name` | Slot used by standby on primary | Wrong name or missing slot breaks streaming |
| `restore_command` | Fetches WAL from archive during recovery | Broken command or missing archive segments stalls recovery |
| `primary_conninfo` | Connection details to primary | Wrong endpoint, role, or auth stops receiver connecting |

Some parameters require a PostgreSQL restart, while others reload or take effect dynamically. Inspect `context` and `pending_restart` in `pg_settings` on your running version rather than assuming every change applies immediately.

```sql
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
    'archive_mode',
    'archive_command'
)
ORDER BY name;
```

## 10. Checking the Archive and Retrieving Old WAL

The WAL archive stores completed segments for recovery or feeding a standby when streaming no longer has required segments in `pg_wal`. An archive helps only if segments were archived successfully and have not been purged by retention policies.

On the primary, check archiver status:

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

If `failed_count` rises, `last_failed_wal` stays stuck, or the archive shows no new segments, check `archive_command` logs, write permissions, archive capacity, and network/storage errors.

### `restore_command` on the Standby

A standby uses `restore_command` to retrieve WAL segments from the archive during recovery. Conceptual configuration example:

```conf
restore_command = 'cp /wal-archive/%f %p'
```

This only illustrates a filesystem-backed archive accessible to the standby. In production, archives often live in object storage or a backup tool, using the appropriate restore binary. The command must exit `0` when the file is retrieved and return a non-zero exit code when the file does not exist; never use a command that reports success when it failed to restore the segment.

The archive must preserve an unbroken WAL chain from the required checkpoint/base backup through the current position. Isolated segments cannot bridge a missing gap in the middle.

### Do Not Purge Archives Simply by Age

An old segment may still be needed by a lagging standby or backup/PITR window. Archive cleanup policies must account for base backups, recovery windows, and WAL positions of all dependent standbys/consumers. Never run `pg_archivecleanup` against a shared archive without knowing the exact scope and safe cutoff.

## 11. Detecting When a Standby Requests Removed WAL

A typical log error looks like:

```text
FATAL:  could not receive data from WAL stream:
ERROR:  requested WAL segment ... has already been removed
```

This indicates the standby needs a segment the primary can no longer serve over the current streaming connection. Possible causes include:

- The standby was offline longer than WAL retention lasted.
- No slot was configured, or the slot was dropped.
- The slot exceeded `max_slot_wal_keep_size` and lost guaranteed WAL.
- A slot was recreated at a newer position while the standby still needed older WAL.
- The WAL archive is missing segments or retention purged the needed segment.
- After a failover, the standby is following an old timeline or pointing at the wrong primary.

Do not jump to rebuilding solely from one log line. First identify the exact segment, timeline, slot, and archive state. If the archive holds a complete unbroken WAL chain, the standby can resume recovery via `restore_command`. If the needed segment exists nowhere, the standby cannot replay across the gap and normally must be rebuilt from a suitable base backup.

## 12. Investigation Workflow When Replication Lag Climbs

Follow these steps in order to pinpoint the bottleneck:

1. Confirm which node is primary and which is standby; verify current timelines and endpoints.
2. On the primary, sample `pg_stat_replication` and send/write/flush/replay LSNs.
3. On the standby, sample `pg_stat_wal_receiver`, received LSN, and replayed LSN.
4. Determine whether the growing gap sits at send, write, flush, or replay.
5. Check PostgreSQL logs on both nodes for connection, authentication, WAL segment, or recovery conflict errors.
6. Measure CPU, memory, storage latency, throughput, network, and workload on the standby.
7. Check slots, `restart_lsn`, retained WAL, `wal_status`, and `safe_wal_size` if available.
8. Check `pg_stat_archiver` and WAL archive accessibility.
9. Assess lag against business SLAs and synchronous/asynchronous replication status.
10. Apply a root-cause-targeted action, then take multiple samples to confirm progress recovers.

### Checking Hot Standby Conflicts

Long-running queries on a standby can conflict with WAL replay, especially when the primary cleans up row versions or alters schemas. Inspect conflict statistics:

```sql
SELECT *
FROM pg_stat_database_conflicts;
```

Conflict counters identify queries canceled during recovery. `hot_standby_feedback` reduces some conflicts by sending `xmin` feedback to the primary, though it can force the primary to keep dead tuples longer and increase table bloat. This is a trade-off, not a default toggle for every lag issue.

## 13. Procedure for Handling Abandoned Replication Slots

An abandoned slot must be handled carefully because it could be the sole WAL anchor for a temporarily paused consumer.

### Step 1: Identify the Owner

Cross-reference `slot_name`, `slot_type`, `database`, `active`, `active_pid`, and `restart_lsn` against:

- Physical standby inventory and `primary_slot_name` configs.
- Logical subscriptions on subscriber nodes.
- CDC connectors and their configured slot names.
- Backup systems or logical decoding tools.
- Recent maintenance, migration, and decommissioning schedules.

Verify in configuration management records rather than guessing ownership from the slot name alone. A slot might belong to a consumer managed outside the core database administration team.

### Step 2: Confirm the Consumer Is Permanently Retired

Verify the application or connector has been retired with no recovery plan and downstream data needs are reconciled. For logical slots, evaluate `catalog_xmin` impact as well. For physical slots, check whether the standby received a fresh base backup and switched to a different slot.

### Step 3: Assess Space and Risk

Estimate WAL retained by the slot, WAL generation rate, and remaining disk headroom. If `pg_wal` is nearly full, prioritize your incident disk-space playbook while still verifying which slot can be safely released. Never manually delete WAL segments.

### Step 4: Drop the Slot Safely

An inactive slot can be dropped via SQL:

```sql
SELECT pg_drop_replication_slot('retired_cdc_slot');
```

This fails if the slot is active. Do not force it by killing processes before verifying the consumer and downstream impact. If the slot belongs to a subscription, manage it through the subscription lifecycle; manually dropping a slot while a subscription remains active can break the subscriber or force a full resync.

### Step 5: Confirm WAL Is Reclaimed

Dropping a slot does not always shrink filesystem usage immediately. PostgreSQL may only recycle or remove segments after a checkpoint and once no other WAL retention requirements hold them. Monitor `pg_replication_slots`, `pg_stat_archiver`, checkpoints, and `pg_wal` usage over time.

## 14. When Can a Standby Catch Up Without Rebuilding?

A standby can continue without a fresh base backup if every required WAL segment from its current position up to the present WAL position can be supplied continuously. Possible sources include:

- WAL still present in `pg_wal` on the primary.
- WAL retained by a valid replication slot.
- Complete WAL segments in the archive with a working `restore_command` on the standby.
- Another WAL source designed to serve recovery for that exact timeline.

If a segment in the middle is missing and no archive or backup contains it, recovery cannot skip across the gap. Creating a new slot at the current LSN cannot recreate lost historical WAL.

### Checking the Archive Before Rebuilding

1. Record the exact segment name and timeline from the standby logs.
2. Locate the segment in the archive and verify checksums/sizes if your archive process supports it.
3. Confirm surrounding segments form an unbroken sequence.
4. Test that `restore_command` on the standby can fetch from the archive.
5. Watch recovery logs to confirm the standby retrieves segments and advances replay.
6. Once caught up, confirm streaming resumes and the slot status is healthy.

Never rename segments or alter WAL contents manually. WAL must be restored intact from a valid source.

## 15. Rebuilding a Standby with a Base Backup

If required WAL is lost and the archive cannot supply it, standard recovery is rebuilding the standby from a base backup of the current primary. Because this replaces the standby's data directory, stop the right instance cleanly and ensure the backup comes from the right primary and timeline.

### Preparation

- Confirm the current primary, address, cluster, and timeline.
- Verify sufficient disk space for the base backup.
- Verify replication privileges for the backup role.
- Identify which physical slot to use; check whether an old slot can be reused or a new one should be created.
- Verify `wal_level`, `max_wal_senders`, `max_replication_slots`, and retention settings.
- Stop the standby per runbook and back up or move aside the old data directory if needed for investigation.
- Ensure the target `-D` directory is empty and matches the instance's data directory.

### Example Using `pg_basebackup`

Creating a new slot named `standby_b_slot`:

```bash
pg_basebackup \
  -h primary.internal \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/data \
  -Fp \
  -Xs \
  -P \
  -R \
  -C \
  -S standby_b_slot
```

Options:

- `-D`: target directory for the base backup; must fit the installation layout and normally be empty.
- `-Fp`: plain directory format.
- `-Xs`: stream WAL during the base backup.
- `-P`: show progress.
- `-R`: write standby configuration, including `standby.signal` and connection info in `postgresql.auto.conf`.
- `-C`: create the replication slot named by `-S`.
- `-S`: replication slot name.

If the slot already exists and is confirmed for this standby, omit `-C` and pass `-S` to attach to the existing slot. Do not pass `-C` if the slot name already exists, as creation will fail. Verify flags against your `pg_basebackup` version and backup strategy.

### Starting Up and Verifying

After the backup finishes, start the standby and watch the logs. Confirm:

- `pg_is_in_recovery()` returns `true`.
- `pg_stat_wal_receiver` shows an active receiver.
- The primary displays the standby in `pg_stat_replication`.
- `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn` advance.
- The slot is actively used and `restart_lsn` advances.
- The standby no longer reports missing WAL or authentication/network errors.
- Read queries on the standby return valid results within acceptable lag bounds.

Never promote a standby just to test whether it works. Promotion alters role/timeline and can cause split-brain if the old primary is still accepting writes.

## 16. Distinguishing Missing WAL from Timeline Divergence

Missing WAL and timeline divergence are different problems. Missing WAL means the standby lacks a WAL segment needed to replay. Timeline divergence occurs when two nodes have divergent WAL histories—typically after one node was promoted while another remained on an older timeline.

After a failover, the new primary advances to a new timeline. An old node cannot simply rejoin as a standby if it committed divergent transactions after the branch point. Evaluate `pg_rewind` or rebuilding from a base backup.

### Role of `pg_rewind`

`pg_rewind` synchronizes a diverged node's data directory with a new source node after failover by identifying and reverting diverged blocks. It is not a general fix for replacing a missing WAL segment along a single continuous timeline.

Key prerequisites typically include:

- The target must have been shut down cleanly before running.
- `full_page_writes` must be enabled as required.
- The cluster must have data checksums enabled at `initdb` or `wal_log_hints` enabled as required.
- WAL needed to locate diverged changes must still be accessible.
- Source and target must share a compatible cluster history/timeline ancestry.

Check documentation for your exact version and run `pg_rewind --dry-run` where supported before executing. If prerequisites are not met, take a fresh base backup instead. After rewinding, reconfigure the standby and verify streaming before returning it to service.

## 17. Preventing Orphaned Slots and Missing WAL

### Slot Lifecycle Management

Track administrative metadata for every slot outside PostgreSQL:

- Slot name and slot type.
- Owner/team and consumer system.
- Associated primary/database.
- Creation date, purpose, and expected lifetime.
- Runbooks for pausing, migrating, and decommissioning.
- Lag/WAL retention thresholds and alerts.

When retiring a standby or connector, tear down the subscription/consumer per procedure, verify it is no longer used, and only then drop the slot. Never leave slots lingering "just in case" without an owner and space limits.

### Setting Intentional Retention Bounds

Choose `max_slot_wal_keep_size` based on WAL generation rate, acceptable consumer outage duration, and filesystem capacity. Set too low, standbys/connectors lose WAL before recovery; left unbounded, a dead consumer can fill the disk.

`wal_keep_size` should likewise match expected offline windows for slotless standbys. However, it does not guarantee catch-up after extended outages. Archives and base backups remain core components of the recovery strategy.

### Monitoring the Archive

Monitor `pg_stat_archiver`, `archive_command` failures, time since last successful archive, archive storage capacity, and actual restore viability. Having an archive that has never been restore-tested does not prove recovery works.

### Tracking WAL Generation Rate

Take two LSN samples separated by an interval to estimate WAL generation velocity:

```sql
SELECT pg_current_wal_lsn();
```

If two samples `L1` and `L2` are `T` seconds apart, average generation is roughly `pg_wal_lsn_diff(L2, L1) / T` bytes/sec. Plan retention around peak rates rather than daily averages. WAL generation spikes during bulk loads, index builds, vacuums, large updates, and peak transactional bursts.

## 18. Capacity and Lag Monitoring and Alerting

Key metrics for dashboards:

| Group | Metrics | Alert When |
|---|---|---|
| Replication | Send/write/flush/replay LSN gaps | Gap grows continuously or breaches SLA |
| Receiver | `status`, last message received time | Receiver stopped or stalled abnormally |
| Slot | `active`, `restart_lsn`, `wal_status` | Slot inactive long, WAL gap growing, status `lost` |
| Slot capacity | `safe_wal_size` | Remaining safe WAL approaches `0` |
| WAL | `pg_wal` filesystem usage | Usage crosses operational threshold |
| Archive | `failed_count`, `last_archived_time` | Archiving failing or stalled |
| Standby | Replay timestamp, conflicts, recovery state | Replay lagging or high query cancellations |
| Host | Free disk, I/O latency, CPU, network | Near disk exhaustion or resource saturation |

Do not apply one static threshold to every cluster. High-WAL-velocity systems need different byte and time thresholds than low-write systems. Alerts should incorporate trends and time-to-threshold projections.

### Estimating Time Remaining Before Disk Full

If `pg_wal` has `F` free bytes and net WAL growth is `R` bytes/sec, rough time remaining is `F / R`. This is only a simple estimate: segments recycle after checkpoints, archiving can catch up or stall, and multiple slots/backups jointly govern retention. Use multi-sample trends and real filesystem monitoring.

## 19. Troubleshooting Rapid `pg_wal` Growth

When `pg_wal` grows abnormally:

1. Identify which filesystem is growing and how much free space remains.
2. Query `pg_replication_slots` to find the slot retaining the oldest WAL.
3. Identify owners and consumer states for every slot.
4. Check `pg_stat_replication`, `pg_stat_wal_receiver`, and LSNs.
5. Check `pg_stat_archiver` to see if archiving is failing.
6. Check WAL generation rate and recently deployed workloads.
7. If a valid consumer is lagging, restore the consumer or standby so the slot advances.
8. If a slot is confirmed retired, drop it via approved procedures.
9. Monitor checkpoints, WAL recycling, and disk usage afterward.

Never delete `.wal` files inside `pg_wal`, rename segments, or run `rm` to free space. PostgreSQL tracks WAL via internal metadata; manually deleting files can destroy crash recovery and replication.

If the filesystem is nearly full and the database risks halting, follow your organization's incident runbook to expand storage or handle verified consumers/slots. Never drop random slots just to shrink disk usage.

## 20. Common Misconceptions

### `active = false` Does Not Automatically Mean an Orphaned Slot

A standby may be down for planned maintenance, a connector paused, or a consumer scheduled intermittently. Check owner and operations schedules before dropping.

### An Old Replay Timestamp Does Not Always Mean Lag

If the primary sees no new transactions, the replay timestamp stops advancing. Use LSNs and heartbeats to distinguish an idle primary from a lagging standby.

### Slot Existence Does Not Guarantee Required WAL Is Still Present

A slot can exceed `max_slot_wal_keep_size` and lose needed WAL. Check `wal_status` and logs, not merely whether the slot row exists.

### `wal_keep_size` Is Not a Quota

It is a minimum WAL floor retained for standbys, not a maximum cap on `pg_wal` size. Slots, archiving, checkpoints, and other factors control actual disk usage.

### Having an Archive Does Not Guarantee Recovery Succeeds

An archive may miss a segment, follow a different timeline, hit permissions issues, or lack a matching base backup. Verify contiguous WAL chains and run periodic restore drills.

### Creating a New Slot Does Not Recover Old WAL

A new slot begins retaining WAL from the point of creation. It cannot resurrect already-deleted segments. If a standby needs earlier WAL, it must come from the archive or a fresh base backup.

## 21. Standby Missing WAL Runbook

When logs report that a requested WAL segment has already been removed, use this runbook:

**Identification Phase**

1. Record the segment name, timeline, and error timestamp from logs.
2. Identify the current primary and the failing standby.
3. On the primary, inspect the slot used by the standby and WAL retention state.
4. Check whether the archive holds the missing segment and the contiguous sequence needed.
5. Verify whether timelines diverged after a failover.

**Recovery Phase**

6. If the archive is complete, fix/verify `restore_command` and let the standby continue recovery.
7. If WAL is missing yet timelines have not diverged, plan a fresh base backup.
8. If timelines diverged, evaluate `pg_rewind` prerequisites; if unmet, take a fresh base backup.
9. Create or attach the proper slot for the consumer with retention sized for expected catch-up.
10. Start the standby and monitor logs, receiver, sender, and replay.

**Verification Phase**

11. Confirm the standby is streaming and LSNs advance.
12. Confirm lag drops within operational bounds.
13. Confirm archiving and slot tracking update normally.
14. Document root cause, outage duration, and preventive changes.

## 22. Practice Exercises

### Exercise 1: Observing Send/Write/Flush/Replay

Set up a primary and standby in a test environment. Insert data on the primary, sample `pg_stat_replication`, and compare all four LSNs. Observe a case where the standby receives WAL quickly yet replays slowly.

### Exercise 2: Creating a Physical Replication Slot

Create a physical slot for a standby, configure `primary_slot_name`, start the standby, and confirm the slot becomes active. Stop the standby cleanly and observe `restart_lsn` and WAL usage.

### Exercise 3: Simulating an Inactive Slot

In a test cluster, create a slot and stop its consumer. Track `pg_replication_slots`, `pg_wal_lsn_diff`, and filesystem usage. Determine when alerting should fire.

### Exercise 4: Observing the Archiver

Enable WAL archiving in a lab, run a write workload, and inspect `pg_stat_archiver`. Simulate an archive command failure and then restore it; review logs and archive catch-up time.

### Exercise 5: Restoring WAL from Archive

Configure a test standby with `restore_command`. Temporarily break streaming while keeping the archive intact, then restore connectivity and verify the standby pulls segments from the archive as needed.

### Exercise 6: Simulating Missing WAL

Strictly in a disposable lab environment, configure small retention and leave a standby offline until the slot no longer retains needed WAL. Observe the log error when segments disappear; never perform this experiment on a cluster holding important data.

### Exercise 7: Rebuilding a Standby

Use `pg_basebackup -R -X stream` to provision a new standby. Inspect slot, receiver, sender, replay LSN, and recovery state after startup.

### Exercise 8: Distinguishing Lag from an Idle Primary

Leave the primary idle with no transactions for a period. Compare replay timestamps against LSNs and heartbeats. Explain why an old timestamp alone cannot prove replica lag.

## 23. Review Questions

**1. What are the stages of replication lag?**

Send, write, flush, and replay. Each stage reflects one segment of WAL transport and application from primary to standby.

**2. Why can a standby receive WAL yet still lag?**

The WAL receiver may write faster than the startup process can replay. CPU, I/O, huge transactions, or recovery conflicts can expand the replay backlog.

**3. What does a physical replication slot retain?**

It retains WAL starting from the position a physical consumer still needs to continue streaming, subject to configured retention limits.

**4. Why can an inactive slot fill the disk?**

If a slot fails to advance, its stale `restart_lsn` forces PostgreSQL to retain all WAL segments from that point onward. New WAL keeps generating until the filesystem fills.

**5. Does `wal_keep_size` replace replication slots?**

No. It keeps a minimum amount of WAL for standbys without tracking per-consumer progress like a slot and does not guarantee catch-up after long outages.

**6. How does `max_slot_wal_keep_size` help, and what risk does it carry?**

It caps WAL retained for slots at checkpoints to protect disk space. If a consumer falls behind beyond that cap, the slot can lose needed WAL and require archive recovery or a rebuild.

**7. When can a standby resume without rebuilding?**

When all required WAL can still be supplied continuously from `pg_wal`, a valid slot, or the archive via `restore_command`.

**8. Why does creating a new slot not fix already-deleted WAL?**

A new slot only starts retaining WAL from its creation position; it cannot recreate deleted historical segments. The standby still needs older WAL from an archive or a fresh base backup.

**9. When is `pg_rewind` used?**

When a target node has diverged from a new source after failover and satisfies `pg_rewind` prerequisites. It is not a tool for filling a missing WAL segment on a continuous timeline.

**10. Why must WAL files never be deleted manually?**

PostgreSQL manages WAL for crash recovery, archiving, and replication. Deleting files outside PostgreSQL's lifecycle can break recovery and prevent the cluster from starting or synchronizing.

## 24. PostgreSQL References

- PostgreSQL Documentation — Monitoring Database Activity: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — Replication Progress Reporting: https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW
- PostgreSQL Documentation — Replication Slots: https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS
- PostgreSQL Documentation — Runtime WAL Configuration: https://www.postgresql.org/docs/current/runtime-config-wal.html
- PostgreSQL Documentation — Archive Recovery Settings: https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-ARCHIVE-RECOVERY
- PostgreSQL Documentation — Continuous Archiving and Point-in-Time Recovery: https://www.postgresql.org/docs/current/continuous-archiving.html
- PostgreSQL Documentation — `pg_basebackup`: https://www.postgresql.org/docs/current/app-pgbasebackup.html
- PostgreSQL Documentation — `pg_rewind`: https://www.postgresql.org/docs/current/app-pgrewind.html
- PostgreSQL Documentation — Warm Standby and Streaming Replication: https://www.postgresql.org/docs/current/warm-standby.html
- PostgreSQL Documentation — Hot Standby: https://www.postgresql.org/docs/current/hot-standby.html

Replication lag, abandoned slots, and standbys missing WAL must all be handled based on exact WAL positions and consumer roles. Tracking send/write/flush/replay separately, governing slot ownership and lifecycles, bounding retention deliberately, auditing archives, and rehearsing standby rebuilds reduce the risk of losing synchronization or filling disks. Once required segments are gone, only a complete archive or a fresh base backup can restore a valid WAL chain.
