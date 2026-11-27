# Replication Slots, WAL Retention, and Disk-Full Risk in PostgreSQL

Physical replication slots help PostgreSQL retain WAL segments that a standby may still need to continue streaming replication. This mechanism protects the standby from the primary recycling WAL too early when the replica disconnects or replays slowly.

In trade-off, a slot can retain WAL longer than expected. If a standby stops, loses network connectivity, fails to keep up with the primary, or is abandoned, the primary must keep the WAL segments needed by the slot. When high WAL volume is generated, the `pg_wal` directory can grow until it exhausts filesystem capacity.

The lesson **"Replication Slots, WAL Retention, and Disk-Full Risk"**, part of the **Physical Replication** chapter of the **Database Engine Relational PostgreSQL** module, explains:

- Physical replication slots and the role of `restart_lsn`.
- Why inactive slots still retain WAL.
- Differences between slot retention, `wal_keep_size`, `max_wal_size`, and WAL archiving.
- How to estimate required WAL retention and monitor disk usage.
- `max_slot_wal_keep_size`, slot invalidation, and standby recovery options.
- Procedures to create, use, inspect, and drop slots safely.
- How to troubleshoot rapid `pg_wal` growth or a nearly full filesystem.

> **Principle:** A replication slot is a WAL retention anchor on the primary, not a separate WAL storage location. Slots help a standby avoid missing WAL on reconnect, but an unconsumed slot can make the primary retain WAL indefinitely if no appropriate limit is set.

---

## 1. What is a replication slot?

A **replication slot** is persistent state managed by PostgreSQL to protect resources that a replication consumer still needs.

For physical replication, a slot retains WAL needed for a physical standby to resume receiving/replaying WAL after an interruption.

Slots are stored in cluster state and persist after a replication connection disconnects. Therefore, a slot can continue retaining WAL even when no standby is currently connected.

### 1.1. A slot does not store a copy of WAL

A replication slot is not a separate archive directory and does not store its own copy of WAL. It tracks progress/a horizon so PostgreSQL knows which WAL segments are not yet eligible to be recycled.

WAL remains inside the primary's `pg_wal` directory. A slot only affects the decision to retain or reuse those segments.

### 1.2. What problem does a slot solve?

Suppose the primary generates WAL continuously, while the standby loses network connectivity for 20 minutes.

- Without a slot: the primary may recycle older WAL segments per retention settings. When the standby returns, a segment it needs may already be gone.
- With a physical slot: the primary retains WAL starting from the position the slot still needs. The standby can resume streaming if the required WAL is still present and primary storage is sufficient.

Slots increase the chance a standby can reconnect without taking a new base backup.

## 2. Physical replication slots vs logical replication slots

PostgreSQL has two common slot types:

| Slot type | Consumer | Primary resources retained |
|---|---|---|
| Physical | Physical standby/replication client | WAL segments from restart LSN |
| Logical | Logical decoding/CDC consumer | WAL, transaction horizon, and catalog horizon per slot state |

This lesson focuses on **physical replication slots** in physical streaming replication.

Logical slots introduce additional concepts such as `catalog_xmin` and logical decoding progress. Do not extrapolate every logical slot detail to physical slots.

## 3. WAL flow in physical replication

A write transaction on the primary generates WAL. The WAL sender transmits WAL to the standby; the standby receives WAL, writes it to its WAL files, and the startup/recovery process replays it to update data pages.

~~~text
Application writes data
        |
        v
Primary generates WAL
        |
        v
WAL sender
        |
        | streaming replication
        v
Standby WAL receiver
        |
        v
WAL files on standby
        |
        v
Startup process replays WAL
        |
        v
Standby data state advances
~~~

The physical replication slot resides on the primary side and retains WAL the standby may need. It does not make the standby replay faster; it only ensures the primary does not discard WAL prematurely within the retention policy.

## 4. LSN and restart_lsn

**LSN (Log Sequence Number)** is a position in the WAL stream.

The most important field when analyzing a physical slot is `restart_lsn`:

- It represents the oldest WAL position the slot might still need.
- The primary must retain required WAL segments starting from this position.
- As the standby makes progress and the primary receives appropriate feedback, `restart_lsn` can advance.
- If the standby stops consuming WAL, `restart_lsn` can stall while the primary keeps generating WAL.

`restart_lsn` is not the standby's current replay LSN. The two values serve different purposes.

### 4.1. restart_lsn vs replay_lsn

| Value | Where observed | Meaning |
|---|---|---|
| `restart_lsn` | `pg_replication_slots` on primary | Oldest WAL the slot may still need |
| `pg_last_wal_receive_lsn()` | Standby | Latest WAL received via streaming |
| `pg_last_wal_replay_lsn()` | Standby | Latest WAL replayed |
| `flush_lsn` | `pg_stat_replication` on primary | WAL position flushed by standby per feedback |

Do not use `restart_lsn` as a substitute for replay progress. A slot can retain an older WAL span than the replay position due to replication restart/retention rules.

## 5. Why do slots retain WAL?

WAL is written as segment files. When an older segment is no longer needed, PostgreSQL can recycle or remove it per checkpoint, archive, and replication retention rules.

If a replication slot still needs WAL in a segment, PostgreSQL cannot recycle that segment merely because the standby is offline.

~~~text
WAL segments:
[0001] [0002] [0003] [0004] [0005] [0006]
   ^                       ^
   |                       |
restart_lsn             current WAL

The slot needs segments from restart_lsn onward.
The primary keeps generating WAL and retains the needed segments.
~~~

As the standby reports progress and the slot's `restart_lsn` advances, older WAL segments become eligible for recycling if no other mechanism needs them.

### 5.1. Slot retention does not mean keeping all WAL forever

A healthy slot normally advances alongside its consumer. As progress updates, older WAL is gradually released across checkpoints and other retention rules.

Risk arises when a slot fails to advance for an extended period.

## 6. Inactive slots still retain WAL

The `active` field in `pg_replication_slots` indicates whether a replication process is currently using the slot.

- `active = true`: a process is currently using the slot.
- `active = false`: no process is currently using the slot.

**Inactive does not mean the slot was dropped or stopped retaining WAL.**

A standby may disconnect for maintenance or a network outage. The slot must remain so the standby can reconnect. Therefore PostgreSQL preserves the slot state and required WAL, even when `active=false`.

### 6.1. Long-inactive slots are a signal to investigate

Possible causes:

- The standby has been shut down for days.
- The replica lost connectivity due to network/firewall issues.
- The standby server was decommissioned but its slot was left behind.
- The standby cannot replay due to disk full or recovery errors.
- A test slot was created and abandoned.
- A failover left the old consumer without reconnecting to the original primary.

Do not drop a slot solely because `active=false`. First identify the consumer and reconnect/rebuild plan.

## 7. What happens without a replication slot?

If a standby uses streaming replication without a slot, the primary lacks an equivalent persistent per-consumer retention point to hold WAL for that standby.

The primary may still keep a minimum amount of WAL via `wal_keep_size`, but if the standby stays offline longer than that WAL window, it may need WAL that has already been recycled.

In that case, the standby cannot resume from its old position using current streaming WAL. If the archive has complete WAL, it can fetch the missing gap from the archive; otherwise, the standby must be rebuilt/reseeded.

## 8. Comparing WAL retention mechanisms

The following settings are related but do not replace one another:

| Mechanism | Purpose | Scope |
|---|---|---|
| Physical replication slot | Retain WAL needed for a specific consumer | Per-slot |
| `wal_keep_size` | Retain a minimum amount of WAL for standbys | Global |
| `max_wal_size` | WAL threshold guiding checkpoints | Checkpoint policy |
| WAL archiving | Save WAL segments to an archive | Archive retention |
| Backup/recovery workflow | Protect recoverability | Backup policy |

### 8.1. wal_keep_size is not max_slot_wal_keep_size

`wal_keep_size` retains a minimum amount of WAL to assist standbys. It does not cap the amount of WAL an inactive replication slot can retain.

`max_slot_wal_keep_size` places a limit on the amount of WAL replication slots are allowed to retain via checkpoint policy.

### 8.2. max_wal_size is not a size limit for pg_wal

`max_wal_size` is a soft threshold used to trigger checkpoints. Replication slots, WAL archiving backlogs, `wal_keep_size`, and other requirements can cause `pg_wal` to grow larger than this value.

Do not set `max_wal_size` and treat it as a guarantee that the `pg_wal` directory cannot exceed that configured size.

## 9. max_slot_wal_keep_size

Parameter:

~~~sql
SHOW max_slot_wal_keep_size;
~~~

`max_slot_wal_keep_size` caps the amount of WAL that replication slots are allowed to retain, in MB.

- The default `-1` means unlimited.
- A finite value prevents slots from retaining excessive WAL.
- The limit is enforced in relation to checkpoints; do not treat it as an instantaneous exact byte limiter.
- When WAL needed by a slot is recycled due to this limit, the slot can be invalidated and the consumer can no longer resume from that slot.

Illustrative configuration example:

~~~text
max_slot_wal_keep_size = 20GB
~~~

Choose the value based on WAL generation rate, tolerated standby outage duration, catch-up duration, and filesystem capacity. Do not treat 20GB as a universal default.

## 10. Trade-offs of slot limits

| Policy | Benefit | Risk |
|---|---|---|
| Unlimited (`-1`) | Standby has a longer reconnect window if storage suffices | Abandoned slots can fill the disk |
| Low limit | Protects primary disk space | Slots can lose required WAL quickly |
| High limit | Allows more time for outages/catch-up | Must reserve more storage capacity |
| No slots | Lower risk of unbounded slot WAL retention | Standbys can lose WAL during outages |

A good limit balances **standby recoverability** with **primary storage safety**.

### 10.1. Limits do not replace monitoring

Even with `max_slot_wal_keep_size`, you still need alerts before a slot hits the threshold. Once a slot is lost, raising the limit afterward does not restore already recycled WAL segments.

## 11. wal_keep_size

~~~sql
SHOW wal_keep_size;
~~~

`wal_keep_size` specifies the minimum amount of WAL the primary keeps for standbys, in MB.

In older PostgreSQL versions, the corresponding parameter was `wal_keep_segments`, measured in number of segments. Check the exact setting for your major version.

`wal_keep_size` can help standbys without slots or serve as an extra retention layer. It is not a mechanism that confirms a standby has received WAL.

## 12. max_wal_size and checkpoints

~~~sql
SHOW max_wal_size;
SHOW checkpoint_timeout;
SHOW checkpoint_completion_target;
~~~

`max_wal_size` controls when PostgreSQL needs earlier checkpoints under heavy WAL generation. Checkpoints flush dirty pages and advance the recovery point.

A slot holding old WAL can prevent segments from being recycled even after a checkpoint finishes. Therefore:

- A completed checkpoint does not mean all old WAL segments are deleted.
- Increasing `max_wal_size` does not fix a long-pinned slot.
- Decreasing `max_wal_size` does not force PostgreSQL to delete WAL that a slot still needs.

## 13. WAL archiving can also retain WAL

If `archive_mode` is enabled and `archive_command` repeatedly fails, PostgreSQL retains WAL awaiting archiving instead of recycling it normally.

Thus, `pg_wal` growth is not necessarily caused by a replication slot.

Check all of:

- Slot retention.
- Standby lag.
- WAL archive failures.
- `wal_keep_size`.
- Backup/recovery processes.
- Disk usage and checkpoint activity.

### 13.1. pg_stat_archiver

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

If `failed_count` increases or `last_failed_time` updates continuously, inspect the archive destination, permissions, network, and archive command logs.

## 14. Listing replication slots

On the primary:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    xmin,
    catalog_xmin
FROM pg_replication_slots
ORDER BY slot_name;
~~~

For physical slots, the primary fields to watch for WAL retention are `slot_name`, `slot_type`, `active`, and `restart_lsn`.

Fields like `xmin`/`catalog_xmin` relate to tuple/catalog retention and may be NULL or irrelevant for physical slots in many cases.

### 14.1. Do not assume views have identical columns across versions

`pg_replication_slots` has gained columns across PostgreSQL versions. Use:

~~~text
\d+ pg_replication_slots
~~~

in `psql` to inspect the actual schema before writing monitoring queries using newer fields.

## 15. Estimating WAL retained by a slot

On the primary, you can estimate the distance from the current WAL position to `restart_lsn`:

~~~sql
SELECT
    slot_name,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS estimated_retained_wal
FROM pg_replication_slots
WHERE slot_type = 'physical'
  AND restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    restart_lsn
) DESC;
~~~

This is a **WAL distance estimate**, not an exact measurement of exclusive bytes held by each slot.

Multiple slots may pin overlapping segments; other mechanisms may also need the same WAL. Summing per-slot estimates can double-count shared segments.

## 16. Observing slot status on PostgreSQL versions supporting wal_status

Newer PostgreSQL versions may provide:

- `wal_status`: WAL retention state of the slot.
- `safe_wal_size`: amount of additional WAL that can be generated before the slot risks exceeding the limit.

Example on servers with these columns:

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

Common `wal_status` values:

| Status | General meaning |
|---|---|
| `reserved` | WAL needed for the slot is within retained bounds |
| `extended` | WAL is retained beyond normal threshold due to retention requirements |
| `unreserved` | Required WAL is no longer guaranteed across the next checkpoint |
| `lost` | Slot is no longer usable because required WAL has been lost |

Details and availability vary by version. Do not run this query on older servers whose view lacks these columns.

## 17. safe_wal_size

`safe_wal_size` is useful when `max_slot_wal_keep_size` is set to a finite value.

It indicates how much WAL can still be generated before the slot risks invalidation per the limit. When this value drops low, the primary may be close to exceeding WAL retention for the slot.

Alerts can be based on:

- Low `safe_wal_size`.
- `wal_status` transitioning to `unreserved`.
- Continuously growing retained WAL.
- Long-inactive slots.
- Low filesystem free space.

If `max_slot_wal_keep_size` is unlimited or the server cannot compute the value, `safe_wal_size` may be NULL.

## 18. Calculating the WAL generation rate

You can retrieve WAL bytes from `pg_stat_wal` on supported versions:

~~~sql
SELECT
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
~~~

Take two samples separated by a time interval:

~~~text
WAL rate = (new wal_bytes - old wal_bytes) / seconds
~~~

Example:

- First sample: 120 GB.
- Sample after 10 minutes: 126 GB.
- WAL generated: 6 GB.
- Average rate: 0.6 GB/min.

This is only a calculation example. Workloads can burst and rates vary by hour.

### 18.1. Do not treat counters across a reset as continuous

`pg_stat_wal.stats_reset` records the statistics reset time. If counters reset between two samples, subtraction yields wrong results. Track the reset timestamp alongside the counter.

## 19. Estimating required retention capacity

A simple planning formula:

~~~text
Required WAL budget
    ≈ peak WAL generation rate
      × maximum tolerated standby outage
      + catch-up allowance
      + safety margin
~~~

Illustrative example:

- Peak WAL rate: 0.6 GB/min.
- Standby outage to tolerate: 30 minutes.
- Catch-up/operational buffer: 10 GB.
- Safety margin: 25%.

Baseline WAL during the outage:

~~~text
0.6 GB/min × 30 min = 18 GB
~~~

Add the catch-up allowance and apply the safety margin:

~~~text
(18 GB + 10 GB) × 1.25 = 35 GB
~~~

You can start evaluating the limit around 35 GB in this example, while also factoring in WAL retention from archive backlogs, other slots, `wal_keep_size`, checkpoint behavior, and storage constraints.

### 19.1. Use peak rate rather than average rate alone

A batch workload can generate WAL at many times the average rate. Sizing solely on the average can cause a slot to hit its limit during a bulk load or index build.

## 20. Catch-up capacity matters too

When a standby reconnects, it must read old WAL while the primary continues generating new WAL at the same time.

If the standby replays faster than the WAL generation rate, lag shrinks. If the replay rate is lower than or close to the WAL generation rate, the standby may never catch up.

A realistic budget must consider:

- Outage duration.
- Peak WAL generation.
- Network throughput.
- Standby disk read/write throughput.
- Replay CPU.
- Query load on the standby.
- Ongoing WAL generation rate during catch-up.

Having enough disk space for a slot to retain WAL does not guarantee the standby can catch up in time.

## 21. Observing streaming replication on the primary

~~~sql
SELECT
    pid,
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

This view shows only currently active WAL sender connections. An inactive slot does not appear as a connection here.

Use `application_name` to correlate the replication connection with a specific standby.

## 22. Observing receive/replay on the standby

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
~~~

And:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

- Receive LSN indicates WAL received.
- Replay LSN indicates WAL applied.
- The gap between them can reflect a replay backlog.
- If `pg_stat_wal_receiver` has no row, the standby may not be streaming or may be fetching WAL from the archive.

Replay timestamps can look old when the primary has no new transactions. Compare LSNs and primary activity before concluding the standby is lagging.

## 23. Measuring pg_wal directory size

On the filesystem, check the actual size of the `pg_wal` directory using OS tools and volume monitoring.

You can inspect the WAL file list via SQL on supported versions:

~~~sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size
FROM pg_ls_waldir();
~~~

The `pg_ls_waldir()` function requires appropriate privileges. The result is a snapshot of the directory at query time.

### 23.1. Filesystem metrics remain the primary source for disk capacity

SQL functions do not replace filesystem metrics. Monitor total volume size, available space, inode/file count on platforms with inodes, I/O latency, and disk quotas/container ephemeral storage.

## 24. A combined monitoring query

On the primary, use a broadly compatible baseline query:

~~~sql
SELECT
    s.slot_name,
    s.slot_type,
    s.active,
    s.active_pid,
    s.restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            s.restart_lsn
        )::bigint
    ) AS estimated_wal_distance
FROM pg_replication_slots AS s
WHERE s.slot_type = 'physical'
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    s.restart_lsn
) DESC NULLS LAST;
~~~

This is a read-only monitoring query. Cross-reference the output with `pg_wal` directory size, archive status, and standby lag.

## 25. Creating a physical replication slot

You can create a slot manually:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
~~~

Slot names must be unique within the cluster. Physical slots are created on the primary.

Once created, a slot can start retaining WAL even before the standby connects. Therefore attach an owner, purpose, and lifecycle to the slot at creation time.

### 25.1. Do not create test slots and forget them

An unused test slot without a consumer can retain WAL. Follow naming conventions, record the corresponding standby, and drop the slot once confirmed no longer needed.

## 26. Using slots with pg_basebackup

You can use a slot when taking a base backup so WAL needed during the backup is not recycled by the primary too early.

If the slot was created beforehand:

~~~bash
pg_basebackup -h primary.example -D /var/lib/postgresql/standby -U replicator -X stream -R -S standby_a
~~~

Or ask `pg_basebackup` to create the slot:

~~~bash
pg_basebackup -h primary.example -D /var/lib/postgresql/standby -U replicator -X stream -R -C -S standby_a
~~~

- `-R` generates appropriate recovery/standby configuration for the backup.
- `-S` specifies the replication slot.
- `-C` requests creating the slot if it does not yet exist.

Verify syntax against your running `pg_basebackup` version. The role needs replication privileges and the primary must have sufficient `max_replication_slots`/`max_wal_senders`.

### 26.1. Slot name in standby configuration

When a standby uses a physical slot, `primary_slot_name` must point to the right slot:

~~~text
primary_slot_name = 'standby_a'
~~~

`pg_basebackup -R` can write the related configuration depending on options/version. Inspect the actual config file after the backup.

## 27. max_replication_slots and max_wal_senders

~~~sql
SHOW max_replication_slots;
SHOW max_wal_senders;
~~~

- `max_replication_slots` limits the number of slots that can be configured.
- `max_wal_senders` limits the number of WAL sender processes that can serve replication connections and certain WAL streaming tasks.

Size capacity for planned standbys, backup jobs, and consumers. Changing some settings requires restarting PostgreSQL; check the setting context on your actual version.

Increasing the maximum slot count does not automatically create slots, nor does it cap WAL volume per slot.

## 28. Slots persist after a standby disconnects

When a standby disconnects:

- The replication connection ends.
- The slot still exists.
- `active` becomes `false` if no other consumer uses it.
- `restart_lsn` may stop advancing.
- The primary continues generating WAL.
- WAL segments needed by the slot remain retained within the retention policy.

This is a critical feature for reconnects, yet also a common source of WAL growth.

## 29. When a slot is invalidated

If a slot WAL limit is configured and the slot needs more WAL than allowed, PostgreSQL may recycle old WAL required by the slot at a checkpoint. The slot can transition to `lost` on versions providing `wal_status`.

When a slot loses required WAL:

- The standby cannot resume from its old position via streaming WAL.
- Raising `max_slot_wal_keep_size` afterward does not restore lost segments.
- The consumer needs a complete alternative WAL source or must be reseeded/rebuilt.

### 29.1. Can it recover from the archive?

If the WAL archive contains **complete and continuous** segments that the standby still needs, the standby can fetch missing segments from the archive via `restore_command`, then resume streaming when appropriate.

If the archive is missing any required segment, you must rebuild the standby from a valid base backup.

## 30. Distinguishing a lost slot from a merely disconnected standby

| State | Meaning | Action |
|---|---|---|
| Slot inactive, WAL still retained | Consumer is offline but the slot may still be usable | Restore connection and monitor catch-up |
| Slot unreserved | Required WAL is no longer guaranteed past the next checkpoint | Urgently restore consumer or add retention/capacity |
| Slot lost | Required WAL has been removed | Archive recovery if WAL is complete, otherwise reseed standby |
| Slot active yet replay lag high | Consumer is connected but cannot keep up | Investigate network, disk, replay CPU, and query load |

Exact statuses depend on version. Do not look only at `active` to decide whether a slot is usable.

## 31. Dropping a physical replication slot safely

When a slot is no longer needed:

1. Identify the standby/consumer owner.
2. Confirm the standby has been decommissioned or switched to another slot.
3. Stop/disconnect the consumer if still active.
4. Verify no automation will reconnect using the old slot.
5. Drop the slot.
6. Monitor WAL recycling after checkpoints and filesystem usage.

Command:

~~~sql
SELECT pg_drop_replication_slot('standby_a');
~~~

PostgreSQL does not allow dropping an active slot. Stop the consumer cleanly first.

### 31.1. Does dropping a slot free WAL immediately?

Dropping a slot removes that slot's retention requirement. WAL files may still be needed by checkpoints, archiving, `wal_keep_size`, or other slots; filesystem usage does not necessarily drop at the exact moment the command runs.

## 32. Advancing a slot is a specialized operation

PostgreSQL provides the administrative function `pg_replication_slot_advance` on supported versions to move a slot position forward.

Advancing a physical slot can cause older WAL to no longer be retained for the consumer. If the standby still needs the skipped WAL span, it will not be able to resume normally from its old position.

Do not use advancing as a routine disk-cleanup operation. Use it only when confirmed that the consumer can skip that WAL span or will be reseeded/rebuilt from an appropriate source.

## 33. Responding when pg_wal grows rapidly

When the filesystem holding `pg_wal` grows rapidly:

1. Measure the growth rate and free space.
2. List physical/logical slots.
3. Find the slot with the oldest `restart_lsn`.
4. Check `active`/inactive status and owner.
5. Check standby receive/flush/replay lag.
6. Check archive failures.
7. Check `wal_keep_size` and slot WAL limits.
8. Check other backup/replication processes.
9. Assess the WAL generation workload.
10. Choose a safe way to release retention requirements.

Do not start by deleting files inside `pg_wal`.

## 34. Scenario: standby offline for days

Symptoms:

- Physical slot has `active=false`.
- `restart_lsn` does not change.
- Primary generates WAL steadily.
- Estimated WAL distance grows.
- `pg_wal` filesystem usage grows.

Response:

- Determine whether the standby still needs to be recovered.
- If needed, restore network/storage and let the standby reconnect.
- Confirm the slot is not lost and required WAL is still intact.
- Monitor standby catch-up rate.
- If the standby is retired, drop the slot after confirmation.
- If required WAL was lost, use a complete archive or rebuild.

## 35. Scenario: archive command failing alongside an inactive slot

Two causes can retain WAL simultaneously:

- A slot retaining WAL from `restart_lsn`.
- The archiver failing so unarchived WAL segments cannot be recycled.

Fixing only the slot may not release all WAL. Fixing only `archive_command` is also insufficient if the slot still pins old segments.

Monitor both `pg_replication_slots` and `pg_stat_archiver`. After recovery, watch filesystem growth rate and checkpoint behavior.

## 36. Scenario: standby active yet still lagging

If `active=true` yet lag keeps growing:

- Check network throughput and packet loss.
- Check standby disk write latency.
- Check replay CPU and I/O.
- Check query load on the hot standby.
- Check recovery conflicts.
- Compare sent/write/flush/replay LSNs.
- Check primary WAL generation rate.

Slots do not fix a slow consumer. They only hold WAL within available storage limits.

## 37. When the primary is nearly out of disk space

Prioritize actions by safety level:

**Step 1 — Identify the cause.** Measure filesystem usage, slot retention, archive backlog, WAL generation rate, and disk budget.

**Step 2 — Add capacity if possible.** Expanding the volume relieves immediate pressure without losing required WAL.

**Step 3 — Restore the consumer/archiver.** Allow the standby or archiver to advance so older WAL becomes eligible for recycling.

**Step 4 — Clean up genuinely unused slots.** Drop only after confirming the owner and rebuild/retire plan.

**Step 5 — Reduce WAL generation if needed.** Pause/reschedule heavy batch or write workloads if business rules allow.

Never manually delete WAL segments, never bulk-drop all slots indiscriminately, and never disable `fsync` to handle disk pressure.

## 38. Why is manually deleting WAL files so dangerous?

PostgreSQL relies on WAL for crash recovery, streaming replication, archive recovery/PITR, and backup/recovery workflows.

Deleting a segment still needed by the primary or a consumer can prevent the database from starting after a crash, stop a standby from continuing, or break the PITR WAL chain.

WAL lifecycle must be managed by PostgreSQL through checkpoint, archive, and replication slot APIs. Never delete files directly inside `pg_wal`.

## 39. How does disk full affect the primary?

When the filesystem holding the data directory or `pg_wal` runs out of space:

- PostgreSQL may fail to write new WAL.
- Write transactions/commits may fail.
- Checkpoint or archive operations may error.
- The server may hit a PANIC or stop accepting writes depending on where I/O fails.
- Restart/recovery may be difficult with no working space left.
- Archive/replication backlogs may worsen.

Do not wait for the filesystem to reach 100% before alerting. Alert on free bytes and growth rate so you have time to respond.

## 40. Monitoring: signals to alert on

| Metric | Why it matters |
|---|---|
| `pg_wal` filesystem used/free | Detects disk pressure |
| WAL generation rate | Forecasts time to limit |
| Slot inactive duration | Detects abandoned consumers |
| Slot `restart_lsn` distance | Estimates retained WAL |
| Slot `wal_status` | Detects `unreserved`/`lost` |
| `safe_wal_size` | Estimates remaining safety headroom |
| Standby flush/replay lag | Detects consumers falling behind |
| Archive `failed_count` | Detects WAL archive backlogs |
| Disk I/O latency | Identifies causes of slow catch-up |
| Checkpoint activity | Understands when WAL can be recycled |

### 40.1. Alert on forecast, not just percentage

If WAL grows by 2 GB per minute and the filesystem has 20 GB free, time remaining may only be around 10 minutes before hitting the theoretical limit. Factor in safety margins, bursts, and other files sharing the volume.

A useful alert estimates:

~~~text
Time to disk full
    ≈ available disk bytes / net growth bytes per second
~~~

This is an approximate forecast; growth rates can change quickly.

## 41. Example alert query for inactive slots and retention

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS estimated_wal_distance
FROM pg_replication_slots
WHERE slot_type = 'physical'
  AND NOT active
  AND restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    restart_lsn
) DESC;
~~~

This is a list to investigate, not a list to drop automatically.

A slot inactive for a few minutes may be normal maintenance. Alert based on duration, owner, WAL distance, and disk budget.

## 42. Identifying slot owners

Slot names should reflect the standby/consumer. Example:

| Slot name | Consumer | Owner | Purpose |
|---|---|---|---|
| `standby_hcm_01` | Standby HCM 01 | DBA on-call | Physical HA |
| `standby_dr_01` | Standby DR | DR team | Disaster recovery |
| `backup_stream_01` | Backup job | Backup service | WAL streaming during backup |

Maintain an inventory covering slot name/type, primary/standby pair, application name, owner/team, creation date, retention budget, last active time, and retirement procedure.

Never leave production slots without a clear owner.

## 43. Lab: creating a physical slot and observing

Run only on a lab primary.

Create the slot:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('lab_standby_slot');
~~~

Observe:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_replication_slots
WHERE slot_name = 'lab_standby_slot';
~~~

The slot may be inactive right after creation. It persists and can begin retaining required WAL.

In the lab, generate WAL with controlled repeated writes, then inspect `restart_lsn` and its distance from the current WAL position.

## 44. Lab: observing slot WAL retention when a standby disconnects

With a lab primary/standby configured with a slot:

1. Confirm the standby is streaming.
2. Check slot `active` and `restart_lsn`.
3. Stop the standby in a controlled way.
4. Write data on the primary to generate WAL.
5. Observe the slot transition to inactive.
6. Compare the current WAL LSN with `restart_lsn`.
7. Start the standby again.
8. Observe the standby receiving/replaying WAL and the slot advancing.

The goal is to see the slot persist when the consumer disconnects and the retention distance grow during offline time.

## 45. Lab: max_slot_wal_keep_size in an isolated environment

On a dedicated lab PostgreSQL instance:

1. Configure `max_slot_wal_keep_size` to a small lab-appropriate value.
2. Create a physical slot.
3. Leave the consumer offline.
4. Generate enough WAL to approach the limit.
5. Monitor `wal_status`/`safe_wal_size` if supported by the version.
6. Observe slot state across checkpoints.

Do not run this on production. Once a slot loses required WAL, the lab standby may need to be rebuilt.

### 45.1. Labs must have a disk budget

Even when testing small limits, keep a filesystem limit on the VM/container. Never run an unbounded workload to force a disk full.

## 46. Lab: checking an archive backlog

In a lab with `archive_command`:

1. Record `pg_stat_archiver`.
2. Temporarily make the archive destination unavailable.
3. Generate WAL.
4. Observe `failed_count` and `pg_wal` growth.
5. Restore the destination.
6. Confirm the archiver advances and WAL can be recycled once other retention requirements are also released.

Do not delete WAL files to make the lab "clean."

## 47. Recovering a standby when a slot is lost

If a slot is lost:

**Case A — Archive has complete WAL**

- Keep the standby as-is.
- Verify the continuous archive chain from the position the standby needs.
- Configure an appropriate `restore_command`.
- Let the standby retrieve missing WAL from the archive.
- Then verify streaming replication can resume.

**Case B — Archive lacks complete WAL**

- The standby cannot redo across the gap.
- Take a new base backup from the right primary.
- Rebuild the standby data directory per procedure.
- Create/use a new slot.
- Verify replication and monitoring after rebuild.

Never try to force a standby to continue by editing `restart_lsn` or creating fake WAL files.

## 48. Rebuilding a standby and slot lifecycle

A rebuild procedure:

1. Identify the current primary and timeline.
2. Confirm the old standby is no longer acting as primary/accepting writes.
3. Save needed logs/diagnostics.
4. Prepare the new standby data directory.
5. Create a new slot or verify the old slot can be reused.
6. Run `pg_basebackup` with the slot and recovery configuration.
7. Start the standby.
8. Verify `pg_is_in_recovery` and the WAL receiver.
9. Verify `replay_lsn` advances.
10. Drop the old slot only after confirming no consumer needs it.

Rebuilds consume time, network, and disk; plan capacity ahead of time.

## 49. Failover and replication slots

A physical slot is stored on the primary that created it. Do not assume that when a standby is promoted to primary, all slots on the old primary automatically appear and continue accurately on the new node.

Newer PostgreSQL versions add capabilities to synchronize failover slots in certain topologies/configurations, though this is a version-specific feature requiring separate configuration and verification.

After failover:

- Identify the new primary.
- Check the slot inventory on the new primary.
- Verify remaining standbys have appropriate slots.
- If valid slot state is absent, use the archive or reseed/rebuild per playbook.
- Prevent consumers from mistakenly reconnecting to the old primary.

## 50. Physical slots and hot_standby_feedback

`hot_standby_feedback` is a mechanism where the standby sends its snapshot horizon back to the primary to reduce recovery conflicts. It relates to tuple retention/cleanup horizons, not WAL retention via `restart_lsn`.

~~~sql
SHOW hot_standby_feedback;
~~~

A standby can both use a physical slot to retain WAL and enable `hot_standby_feedback` to reduce query cancellations. In that case, two separate impacts must be monitored:

- The slot retains WAL segments.
- Feedback can retain dead tuples on the primary.

Do not lump these two risks into a single disk metric.

## 51. Parameters and views to remember

| Component | Role |
|---|---|
| `max_replication_slots` | Maximum number of slots |
| `max_wal_senders` | Maximum number of WAL sender processes |
| `max_slot_wal_keep_size` | Cap on WAL retained by replication slots |
| `wal_keep_size` | Minimum WAL retention |
| `max_wal_size` | Soft checkpoint threshold |
| `archive_mode` | Enables WAL archiving |
| `archive_command` | Saves WAL segments to archive |
| `pg_replication_slots` | Slot inventory and restart LSN |
| `pg_stat_replication` | WAL sender/standby progress |
| `pg_stat_wal_receiver` | WAL receiver state on standby |
| `pg_stat_archiver` | Archive success/failure statistics |
| `pg_stat_wal` | WAL generation/write/sync statistics |

Whether a parameter requires reload or restart depends on its setting context. Check `pg_settings.context` and the documentation for your exact major version before making changes.

## 52. Troubleshooting: pg_wal grows despite low max_wal_size

Possible causes:

- A replication slot retaining old WAL.
- `archive_command` failing.
- `wal_keep_size` retaining extra WAL.
- Standby not advancing.
- Incomplete checkpoints or high WAL-generating workload.
- Another consumer/backup workflow still needing WAL.

How to investigate:

1. Check `pg_replication_slots`.
2. Compute WAL distance via `restart_lsn`.
3. Check `pg_stat_archiver`.
4. Check filesystem usage and WAL rate.
5. Inspect checkpoint/replication activity.
6. Identify which retention requirement is pinning segments.

Do not assume `max_wal_size` is a hard cap.

## 53. Troubleshooting: slot active yet restart_lsn not advancing

Check:

- Is the standby receiving WAL?
- Is `flush_lsn` advancing?
- Does the replication connection have wait events?
- Are there network interruptions?
- Does the standby have disk full/read-only filesystem?
- Is the slot actually being used by that connection?
- Is the consumer paused or experiencing a replay backlog?

Compare primary sent/write/flush/replay LSNs with standby receive/replay LSNs. `active` only indicates a process is using the slot, not that progress is healthy.

## 54. Troubleshooting: slot inactive with unknown owner

Do not drop immediately.

- Check the slot name and naming convention.
- Check standby inventories/configurations.
- Check `application_name`/replication connection history in logs.
- Cross-check owner teams per operational procedure.
- Check backup/DR workflows.
- Confirm the slot is no longer configured in `primary_slot_name`.

If the owner is still unknown, mark it for investigation and measure its retention impact; do not delete based on guesswork.

## 55. Troubleshooting: slot lost after checkpoint

If `wal_status` is `lost`:

- The slot no longer guarantees supplying needed WAL.
- Check whether the archive covers the segment gap.
- If sufficient, try recovering the standby via archive per procedure.
- If missing segments, rebuild the standby.
- Increase/adjust the budget for next time.
- Alert before `safe_wal_size` runs out.

Do not advance a slot or create a new slot and let an old standby resume without proper base state/WAL continuity.

## 56. Best practices

- Every physical slot must have a clear consumer and owner.
- Set `max_slot_wal_keep_size` based on peak WAL rate and outage objectives.
- Monitor `restart_lsn` distance and slot inactivity.
- Monitor `pg_wal` filesystem free space independently.
- Monitor archive failures.
- Ensure the archive holds complete WAL to recover if a slot is invalidated.
- Run `pg_basebackup`/physical backups per procedure.
- Verify the slot inventory after failover.
- Drop slots only after the consumer is retired or migrated.
- Never delete WAL files manually.
- Test slot loss/rebuild in a lab.
- Measure standby catch-up and rebuild times to establish RTO.

## 57. Checklist when operating replication slots

**Before creation**

1. Which standby does the slot serve?
2. Are primary/standby timelines and versions compatible?
3. Does `max_replication_slots` have capacity?
4. Is the disk budget sufficient for outage/catch-up?
5. Is WAL archiving working?
6. Are an owner and alerts assigned?

**During operation**

7. Is the slot active when expected?
8. Is `restart_lsn` advancing?
9. Is WAL distance within budget?
10. Are `safe_wal_size`/`wal_status` raising warnings?
11. Is standby flush/replay lag decreasing?
12. Is `pg_wal` free space sufficient?
13. Is archive `failed_count` increasing?

**When the standby is offline**

14. Is the outage within the retention objective?
15. Is WAL generation rate spiking?
16. Is the slot approaching the limit?
17. Can storage be expanded or the consumer restored?
18. Is the slot still usable after checkpoints?

**When retiring/rebuilding**

19. Did the owner confirm the consumer no longer uses the slot?
20. Was the standby switched to another slot or rebuilt?
21. Is an alternative archive/WAL path available?
22. Will dropping the slot release the retention requirement?
23. Were post-checkpoint status and filesystem usage verified?

## 58. Practice exercises

### Exercise 1 — Replication slot

What is a replication slot?

**Hint:** persistent state to retain resources needed by a consumer.

### Exercise 2 — Physical slot

What does a physical slot protect for a standby?

**Hint:** WAL segments needed to continue streaming.

### Exercise 3 — restart_lsn

What does `restart_lsn` represent?

**Hint:** oldest WAL position the slot may still need.

### Exercise 4 — Inactive slot

Does a slot with `active=false` still retain WAL?

**Hint:** yes, the slot still exists.

### Exercise 5 — Slot vs connection

Does a replication slot disappear when the connection disconnects?

**Hint:** no.

### Exercise 6 — Physical vs logical

State the primary resource difference between the two slot types.

**Hint:** physical retains WAL; logical also involves transaction/catalog horizons.

### Exercise 7 — wal_keep_size

What does this parameter do?

**Hint:** retains a minimum amount of WAL for standbys.

### Exercise 8 — max_slot_wal_keep_size

What does this parameter limit?

**Hint:** WAL retention by replication slots.

### Exercise 9 — max_wal_size

Is it a hard cap for `pg_wal`?

**Hint:** no, it is a soft checkpoint threshold.

### Exercise 10 — Archive backlog

What can repeated `archive_command` failures cause?

**Hint:** unarchived WAL remains retained, causing `pg_wal` to grow.

### Exercise 11 — WAL rate

How do you calculate the WAL generation rate from `pg_stat_wal`?

**Hint:** delta `wal_bytes` divided by delta time.

### Exercise 12 — Retention budget

List the factors in the slot sizing formula.

**Hint:** peak WAL rate, outage, catch-up, safety margin.

### Exercise 13 — Catch-up

Why is retaining enough WAL not enough to guarantee the standby catches up?

**Hint:** replay throughput must exceed the WAL generation rate.

### Exercise 14 — pg_replication_slots

What does this view show?

**Hint:** slot name/type/active/`restart_lsn`/status.

### Exercise 15 — pg_stat_replication

Does this view show an inactive slot as a connection?

**Hint:** no, only active WAL sender connections.

### Exercise 16 — Receive vs replay

Distinguish receive LSN and replay LSN.

**Hint:** WAL received vs WAL applied.

### Exercise 17 — wal_status

What does `lost` mean?

**Hint:** required WAL was lost, so the slot is no longer usable.

### Exercise 18 — safe_wal_size

What does it help forecast?

**Hint:** how much WAL can still be generated before the slot risks invalidation.

### Exercise 19 — Creating a slot

Write SQL to create a physical replication slot.

**Hint:** `pg_create_physical_replication_slot`.

### Exercise 20 — Dropping a slot

Write SQL to drop a slot confirmed no longer in use.

**Hint:** `pg_drop_replication_slot`.

### Exercise 21 — Active drop

Can an active slot be dropped?

**Hint:** must stop/disconnect the consumer first.

### Exercise 22 — pg_basebackup

What does the `-S` option specify?

**Hint:** replication slot.

### Exercise 23 — pg_basebackup -C

What does this option do when combined with `-S`?

**Hint:** requests creating the slot if it does not yet exist.

### Exercise 24 — primary_slot_name

What is this standby setting used for?

**Hint:** selects the physical slot on the primary.

### Exercise 25 — max_replication_slots

Does raising this setting automatically cap WAL retention?

**Hint:** no, it only increases slot count capacity.

### Exercise 26 — Disk usage

Which SQL function lists the WAL directory on supported versions?

**Hint:** `pg_ls_waldir`.

### Exercise 27 — WAL distance

Write an expression calculating bytes from current WAL LSN to `restart_lsn`.

**Hint:** `pg_wal_lsn_diff`.

### Exercise 28 — Long-inactive slot

List three common causes.

**Hint:** standby offline, decommissioned, network failure.

### Exercise 29 — Slot invalidation

Does raising `max_slot_wal_keep_size` after a slot becomes `lost` recover the WAL?

**Hint:** no.

### Exercise 30 — Archive fallback

When a slot is `lost`, what condition allows a standby to recover WAL from the archive?

**Hint:** archive has complete continuous WAL from the needed position.

### Exercise 31 — Rebuild

When the archive lacks required WAL, what is the remediation?

**Hint:** take a base backup/reseed the standby.

### Exercise 32 — Disk full

Why should `pg_wal` files never be deleted using filesystem commands?

**Hint:** breaks crash recovery/replication/PITR.

### Exercise 33 — max_wal_size

Why can `pg_wal` exceed `max_wal_size`?

**Hint:** slots, archiver, `wal_keep_size`, and other retention.

### Exercise 34 — WAL generation burst

Why can sizing by average rate be dangerous?

**Hint:** batch workloads have high peaks.

### Exercise 35 — Slot owner

Why maintain an owner inventory for each slot?

**Hint:** prevents accidental drops or forgotten retention.

### Exercise 36 — Failover

Do slots on the old primary automatically appear on the new primary?

**Hint:** not by default; depends on version/failover slot configuration.

### Exercise 37 — hot_standby_feedback

What resource other than WAL retention does it retain?

**Hint:** tuple versions/cleanup horizon.

### Exercise 38 — Monitoring

Name at least five metrics to alert on.

**Hint:** disk free, WAL rate, inactive duration, restart distance, `safe_wal_size`, archive failures, replay lag.

### Exercise 39 — Incident response

The primary is nearly out of disk space due to an inactive slot. State the handling order.

**Hint:** identify cause/owner, expand capacity, restore consumer or safely retire slot, never delete files.

### Exercise 40 — Retention design

A primary generates 0.5 GB WAL/min, needs to tolerate a 40-minute outage, has an 8 GB catch-up buffer, and a 20% safety margin. Compute an illustrative budget.

**Hint:** (0.5 × 40 + 8) × 1.2 = 33.6 GB.

## 59. Frequently asked questions

### Does a replication slot store its own WAL?

No. It stores state/a horizon so PostgreSQL keeps WAL segments in `pg_wal` while needed.

### Are inactive slots automatically deleted?

Normally no. A slot persists until dropped or handled by a specific mechanism/version-specific policy.

### Why is pg_wal growing even with no standby connected?

An inactive slot may retain WAL from an old `restart_lsn`. Archive failures or `wal_keep_size` can also retain WAL.

### Does max_wal_size enforce an absolute cap on pg_wal?

No. It is a soft checkpoint threshold; replication slots and archive backlogs can cause the directory to grow larger.

### Does wal_keep_size replace replication slots?

No. It retains a global minimum amount of WAL; slots provide per-consumer retention state.

### Is max_slot_wal_keep_size completely safe against disk full?

No. It helps cap slot retention per checkpoint policy, yet archive backlogs and other factors can still retain WAL. Monitor the filesystem.

### If a slot is lost, can raising the limit rescue it?

No. Recycled WAL segments do not reappear on their own. Use a complete archive or rebuild the standby.

### Can an inactive slot be dropped to free disk space?

Only after confirming the consumer no longer needs it. Dropping a slot can make the standby lose the ability to resume from its old WAL position.

### Does dropping a slot shrink pg_wal immediately?

Not necessarily. WAL may still be needed for archiving, checkpoints, `wal_keep_size`, or other slots. Recycling occurs per the PostgreSQL lifecycle.

### Should a slot be advanced when disk is nearly full?

Not as a general firefighting measure. Advancing can skip WAL needed by a standby; use it only with a clear consumer plan.

### How do I tell which slot holds the most WAL?

Compare the current WAL LSN with `restart_lsn` via `pg_wal_lsn_diff`; the result is an estimated WAL distance, not exact exclusive disk usage.

### Do physical slots retain dead tuples like logical slots?

The primary purpose of a physical slot is WAL retention. Tuple retention caused by `hot_standby_feedback` and xmin horizons is a separate concern to monitor independently.

### Can you use only a WAL archive without a physical slot?

Yes in some topologies if the standby can fetch all required WAL from the archive and retention/restore commands are properly designed. Ensure the archive is continuous and has adequate capacity.

### When must a standby be rebuilt?

When the standby lacks needed WAL and there is no complete archive to fill the gap, rebuild the standby from an appropriate base backup.

## 60. Summary

Key observation commands:

~~~sql
-- Slot inventory on primary.
SELECT
    slot_name,
    slot_type,
    active,
    active_pid,
    restart_lsn
FROM pg_replication_slots;

-- Estimated WAL distance per physical slot.
SELECT
    slot_name,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS wal_distance
FROM pg_replication_slots
WHERE slot_type = 'physical'
  AND restart_lsn IS NOT NULL;

-- Primary replication connections.
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;

-- Standby receive/replay.
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();

-- Archive status.
SELECT * FROM pg_stat_archiver;

-- WAL generation statistics.
SELECT wal_bytes, stats_reset
FROM pg_stat_wal;

-- Relevant settings.
SHOW max_replication_slots;
SHOW max_wal_senders;
SHOW max_slot_wal_keep_size;
SHOW wal_keep_size;
SHOW max_wal_size;
SHOW archive_mode;
SHOW archive_command;
~~~

Principles to remember:

1. **Physical replication slots retain WAL that a standby may still need**, based on `restart_lsn`.
2. A slot is retention state, not an independent copy of WAL.
3. Inactive slots persist and can retain WAL.
4. `restart_lsn` differs from receive/replay/flush LSN.
5. `max_slot_wal_keep_size` caps WAL retention by slots under checkpoint policy.
6. `wal_keep_size` retains a minimum amount of WAL; `max_wal_size` is a soft checkpoint threshold, not a hard cap.
7. Archive failures can also cause `pg_wal` to grow.
8. Use `pg_replication_slots`, `pg_stat_replication`, `pg_stat_archiver`, `pg_stat_wal`, and filesystem metrics to find root causes.
9. Estimate the retention budget using peak WAL rate × outage time, plus catch-up and safety margin.
10. Catch-up capacity must exceed the WAL generation rate for lag to decrease.
11. `safe_wal_size`/`wal_status` are useful on supported versions.
12. A lost slot is not recovered merely by raising the limit afterward.
13. If the archive has complete WAL, the standby can recover missing segments; otherwise, rebuild from a base backup.
14. Drop slots only after confirming the consumer is retired/migrated.
15. Advancing a slot can cause a standby to miss WAL; do not use it as routine disk cleanup.
16. Never manually delete WAL files.
17. Monitor disk free space, WAL growth rate, and time-to-full before the filesystem fills up.
18. Verify slot inventory after failover; do not assume slots automatically transfer to the new primary.
19. Separate WAL retention from tuple retention caused by `hot_standby_feedback`.
20. Restore/rebuild tests prove a standby can recover as planned.

Handling workflow:

~~~text
pg_wal growing rapidly / disk pressure
              |
              v
     Check filesystem + WAL rate
              |
              v
     Check pg_replication_slots
              |
              +--> Inactive slot / old restart_lsn?
              |          |
              |          v
              |     Identify owner/consumer
              |          |
              |          +--> Consumer still needed?
              |          |       |
              |          |       v
              |          |   Restore standby
              |          |
              |          +--> Retired?
              |                  |
              |                  v
              |              Drop slot safely
              |
              +--> Check archive failures
              |
              +--> Check wal_keep_size / checkpoints
              |
              v
       Monitor WAL recycling and free space
~~~

**Conclusion:** Replication slots allow a physical standby to resume from retained WAL after disconnecting, but an inactive slot or slow consumer can make the primary retain WAL until the filesystem runs out of space. Safe operations require **setting appropriate slot limits, measuring the WAL generation rate, tracking `restart_lsn` and `safe_wal_size`, monitoring archiving alongside disk capacity, and having a standby rebuild playbook when WAL is lost**. Never manually delete WAL files to free disk space.
