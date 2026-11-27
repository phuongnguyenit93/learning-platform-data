# Distinguishing Crash Recovery, Archive Recovery, and Standby Replay in PostgreSQL

PostgreSQL uses Write-Ahead Logging (WAL) to recover data after failures, restore from backups, and synchronize standby servers. All three scenarios involve reading and replaying WAL records, but their goals, WAL sources, server states, and how recovery ends differ.

Three concepts to distinguish:

- **Crash recovery**: PostgreSQL recovers itself after an unclean server shutdown. Upon restart, it reads the necessary WAL in the data directory to bring the database back to the most recent consistent state recorded by WAL.
- **Archive recovery**: PostgreSQL starts from a base backup and replays WAL fetched from the archive, typically to recover to a desired point in time, transaction, or LSN (Point-in-Time Recovery — PITR).
- **Standby replay**: a standby server continuously receives WAL from the primary via streaming replication and/or the WAL archive, then replays it to stay caught up with the primary. It typically remains in recovery mode so it is ready for read-only queries or promotion during failover.

All three share the WAL redo foundation, but they are not the same operational procedure.

The lesson **“Distinguishing Crash Recovery, Archive Recovery, and Standby Replay”**, part of the **WAL and Checkpoints** chapter of the **Database Engine Relational PostgreSQL** module, explains WAL sources, checkpoints/redo, timelines, signal files, PITR targets, streaming replication, hot standby, commit synchronization, monitoring, and hands-on labs.

> **Mnemonic:** Crash recovery recovers a server that just crashed; archive recovery restores a backup using the WAL archive; standby replay keeps a secondary server continuously applying WAL to follow the primary. Standby replay and archive recovery can both use the WAL archive, but their purposes and lifecycles differ.

---

## 1. All Three Are Based on WAL

When a transaction modifies data, PostgreSQL generates WAL records. Data pages may not be flushed to table files immediately, but WAL allows redoing the necessary changes after a crash.

~~~text
Transaction
    |
    v
WAL records
    |
    v
WAL buffers
    |
    v
WAL segment files
    |
    +--> Crash recovery
    |
    +--> Archive recovery / PITR
    |
    +--> Standby replay
~~~

A WAL record can describe heap operations, index operations, transaction commits, checkpoints, and other necessary changes.

### 1.1. Recovery Is Not “Undoing Individual SQL Statements”

PostgreSQL primarily uses WAL to **redo** logged changes during recovery. It does not operate by reading logs and executing reverse SQL statements to undo operations.

MVCC and transaction status determine which tuple versions are visible. Operations from uncommitted transactions do not become committed business data just because part of their WAL was redone.

## 2. Checkpoints Establish the Redo Starting Point

A checkpoint writes dirty data pages according to WAL rules and records the checkpoint record/state. During crash recovery, PostgreSQL can begin redo from the required position based on the most recent checkpoint.

~~~text
WAL timeline:
---- WAL ---- [checkpoint] ---- WAL ---- WAL ---- crash
                   |
                   +--> recovery starts redo from the relevant position
~~~

Checkpoints reduce the amount of WAL that needs to be replayed after a crash. They do not replace the WAL archive and are not a backup.

### 2.1. A Checkpoint Is Not a Commit Boundary

A transaction may already be durably committed via WAL prior to a checkpoint. Checkpoints only reduce the amount of redo needed during recovery; they are not a condition for confirming a transaction.

## 3. Comparing the Three Recovery Types

| Criterion | Crash recovery | Archive recovery / PITR | Standby replay |
|---|---|---|---|
| Scenario | Unclean server shutdown | Restore from base backup | Secondary server following primary |
| Goal | Bring current data directory to a consistent state | Restore backup to a WAL/transaction point | Continuously apply WAL to keep up with primary |
| WAL source | Primarily required WAL in pg_wal | WAL archive, possibly combined with local WAL | Streaming replication and/or archive |
| Trigger / start | Server restart automatically detects crash | Restore base backup and configure recovery | Prepare standby from base backup |
| Signal file PG 12+ | No separate signal file needed | recovery.signal | standby.signal |
| State during process | Startup recovery | Archive recovery | Recovery/standby mode |
| Completion | Server opens for normal traffic | Reaches target or end of WAL per config, then executes chosen action | Typically keeps running and replaying WAL |
| Final role | Recovered primary | Standalone recovered instance or promoted primary | Standby ready for reads/failover |

**Key point:** Both archive recovery and standby replay can use the WAL archive. The difference lies in the recovery intent and whether the server remains in standby mode or exits recovery to operate independently.

## 4. What Is Crash Recovery?

Crash recovery occurs when PostgreSQL restarts after an unclean shutdown, such as:

- Server power loss.
- Operating system crash.
- PostgreSQL process killed unexpectedly.
- Server stopped in immediate mode.
- Kernel or storage failure preventing normal shutdown completion.

PostgreSQL detects that the data directory lacks a clean shutdown checkpoint state and automatically runs recovery.

### 4.1. Crash Recovery Does Not Require Creating recovery.signal

In a normal restart after a crash, PostgreSQL automatically detects that recovery is required. You do not need to create `recovery.signal` or `standby.signal` to trigger crash recovery.

### 4.2. The WAL Source Is Primarily Existing pg_wal

PostgreSQL uses the required WAL in the data directory, typically from the most recent checkpoint up to the end of valid readable WAL.

If required WAL segments are missing or corrupted, recovery may fail to complete. The WAL archive can be part of an advanced recovery procedure, but automatic crash recovery is not synonymous with PITR from a base backup.

## 5. How Does Crash Recovery Work?

~~~text
PostgreSQL stops abnormally
          |
          v
Server starts up
          |
          v
Reads control/checkpoint state
          |
          v
Determines redo start LSN
          |
          v
Reads WAL in pg_wal
          |
          v
Redoes necessary changes
          |
          v
Restores transaction/visibility state
          |
          v
Database reaches consistent state
          |
          v
Opens connections for normal operation
~~~

This is a conceptual diagram. Startup and transaction state recovery involve additional internal details.

## 6. Why Does Crash Recovery Redo WAL for Uncommitted Transactions?

A transaction may have generated WAL records for some changes before crashing without writing a commit record.

PostgreSQL can redo those page-level changes to restore a physically consistent state. However, an uncommitted transaction is still not considered a committed business transaction.

Tuple versions are identified by transaction IDs/status and MVCC visibility. Recovery does not turn uncommitted transactions into valid data merely because redo ran.

### 6.1. No Traditional SQL-Statement Undo

PostgreSQL relies on MVCC, transaction status, and subsequent cleanup mechanisms. After recovery, row versions not belonging to committed transactions are not visible as committed data; VACUUM can later reclaim them when safe.

## 7. Clean Shutdown and Crash Recovery

Shutdown modes via pg_ctl:

~~~bash
pg_ctl stop -m smart
pg_ctl stop -m fast
pg_ctl stop -m immediate
~~~

- `smart`: waits for clients to disconnect; clean shutdown.
- `fast`: disconnects clients, rolls back active transactions, and performs a clean shutdown.
- `immediate`: stops immediately, skipping clean shutdown; the next startup requires crash recovery.

An abruptly killed service can also require crash recovery.

Do not use immediate mode as the routine production shutdown method.

## 8. What Is Archive Recovery?

**Archive recovery** is the process where PostgreSQL restores from a **base backup** by replaying archived WAL.

A common use case is **Point-in-Time Recovery (PITR)**:

- A user accidentally drops a table.
- A migration corrupts data.
- An erroneous business transaction is committed.
- The database must be recovered to just before a specific time/event.

Instead of reverting solely to an old base backup, PostgreSQL replays WAL from the backup up to the desired target.

~~~text
Base backup at T0
      |
      v
WAL archive: T0 -> T1 -> T2 -> T3 -> T4
      |
      v
Replay to target T3
      |
      v
Recover database at T3
~~~

Archive recovery typically produces a **standalone recovered instance**. When the target is reached and the action is promote, the instance exits recovery and operates as a new primary on a new timeline.

## 9. Base Backup and WAL Archive Are Two Distinct Components

A base backup contains the initial physical state of the cluster at a point in time. The WAL archive contains the WAL segments needed to advance the database from the backup state to the desired time.

~~~text
Base backup
   +
Continuous WAL archive
   =
PITR capability across the covered window
~~~

Having only a WAL archive without a matching base backup is insufficient to rebuild a complete cluster.

Having only a base backup without the required WAL prevents replaying past the backup consistency point.

### 9.1. The WAL Archive Must Be Continuous

PITR requires an unbroken chain of WAL from the base backup to the recovery target. If a required segment is missing, recovery will stop because redo cannot proceed across the gap.

Verify archive_command, archive logs, checksum/backup validation, and retention policies.

## 10. Configuring WAL Archiving

On the primary, configuration typically involves:

~~~sql
SHOW wal_level;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
~~~

A conceptual example:

~~~text
wal_level = replica
archive_mode = on
archive_command = '... copy %p to archive location using %f ...'
~~~

`%p` is the source WAL file path and `%f` is the filename. The exact `archive_command` depends on OS, storage, and archive protection requirements.

### 10.1. Archive Command Must Be Safe on Retry

PostgreSQL may re-invoke `archive_command` if a previous archive attempt fails. The command must execute idempotently, avoid accidentally overwriting a valid archived file, and return the proper exit status.

Do not use an untested sample copy command in production. Handle temporary files, atomic renames, checksums, permissions, and storage errors properly.

## 11. Base Backups with pg_basebackup

A physical base backup can be created using `pg_basebackup` with appropriate options.

Conceptual example:

~~~bash
pg_basebackup -h primary.example -D /backup/base -U replicator -X stream -P
~~~

Parameters and authentication depend on the deployment. Backups should be stored with appropriate retention and verified with restore tests.

### 11.1. A Backup Is Not an Archive

- A base backup provides a physical snapshot.
- The WAL archive provides the subsequent stream of changes.
- PITR requires both along with a continuous WAL chain.

## 12. Starting Archive Recovery in PostgreSQL 12+

Since PostgreSQL 12, recovery configuration is no longer placed in `recovery.conf`. Instead, signal files are used:

~~~text
recovery.signal
~~~

To perform archive recovery/PITR:

1. Restore the base backup into a separate data directory.
2. Configure `restore_command` to retrieve WAL from the archive.
3. Set a recovery target if you want to stop at a specific point.
4. Create the `recovery.signal` file.
5. Start PostgreSQL.
6. Monitor logs and recovery progress.
7. Once the target is reached, execute the configured action.

**Do not create `recovery.signal` inside a running production data directory.** This is a restore workflow performed in a separately prepared data directory.

### 12.1. recovery.signal and standby.signal

- `recovery.signal`: requests archive recovery.
- `standby.signal`: requests running as a standby server.

These two files represent different startup intents. Use the appropriate signal file for your goal. In PostgreSQL 12+, if `standby.signal` exists, the server enters standby mode; avoid placing both arbitrarily since standby mode takes precedence in startup behavior.

## 13. restore_command

`restore_command` tells PostgreSQL how to fetch a WAL file from the archive.

Conceptual configuration example:

~~~text
restore_command = 'restore-tool %f %p'
~~~

Where:

- `%f`: filename of the WAL file to retrieve.
- `%p`: destination path where PostgreSQL wants the file restored.

The command must return success when the file is retrieved successfully and failure when it cannot provide the file. PostgreSQL may invoke the command multiple times for different filenames.

### 13.1. Restore Command Must Handle Missing Files Gracefully

Once available archive WAL has been replayed, the server may request a segment that has not been archived yet. The command must properly return a "file not found" failure status rather than returning success with an empty or invalid file.

## 14. Recovery Targets

Archive recovery can stop at a specified target:

| Target | Meaning |
|---|---|
| `recovery_target_time` | Timestamp |
| `recovery_target_xid` | Transaction ID |
| `recovery_target_lsn` | LSN |
| `recovery_target_name` | Named restore point |
| `recovery_target = 'immediate'` | Stop as soon as a consistent state is reached |

Conceptual configuration example:

~~~text
recovery_target_time = '2026-11-14 09:30:00+07'
recovery_target_action = 'pause'
~~~

Timestamps must include an explicit timezone to avoid time ambiguity. Targets are interpreted according to PostgreSQL semantics; pinpoint the exact commit time of the event.

### 14.1. recovery_target_inclusive

This parameter controls whether the target transaction/record itself is included according to target semantics. The default is typically true. When recovering before or after a specific transaction, understand inclusive behavior and test on a restored copy.

### 14.2. recovery_target_timeline

You can choose a specific timeline or `latest` to follow the latest applicable timeline. Timeline history files help PostgreSQL determine WAL branching relationships after promotions/PITR.

Do not rely on `latest` as an automatic guarantee of picking the "right business history"; verify timeline and backup lineage.

## 15. recovery_target_action

When the recovery target is reached, `recovery_target_action` controls the action taken:

- `pause`: pauses recovery at the target so the DBA can inspect the state.
- `promote`: promotes the instance to operate as an independent server.
- `shutdown`: shuts down the server at the target as configured.

The default value is typically promote. Target/action settings should be verified against your PostgreSQL version.

### 15.1. pause Is Useful When Inspecting PITR

You can pause at the target, inspect the recovered data, and then continue or promote based on your decision. Do not leave a server paused indefinitely while neglecting monitoring, storage, or operations.

## 16. Named Restore Points

On the primary before an event you want to mark:

~~~sql
SELECT pg_create_restore_point('before_sensitive_migration');
~~~

This function creates a named restore point and returns an LSN. During archive recovery, you can specify:

~~~text
recovery_target_name = 'before_sensitive_migration'
~~~

A restore point does not automatically create a base backup or guarantee that the WAL archive has saved every segment. It only marks a position in the WAL stream.

### 16.1. Using Restore Points Before Risky Operations

A major migration procedure can create a restore point before executing. However, you still need a valid base backup, continuous WAL archiving, and restore testing.

## 17. What Is a Timeline?

Every WAL history belongs to a **timeline**. Timeline IDs help PostgreSQL manage branching histories created when a recovery is promoted or a standby is promoted.

~~~text
Timeline 1
   |
   +---- WAL ---- WAL ---- WAL
                         |
                         | promote/PITR
                         v
                    Timeline 2
                         |
                         +---- WAL ---- WAL
~~~

After promotion, the new server starts writing WAL on a new timeline. A history file describes where the new timeline branched from the previous timeline.

### 17.1. Why Do Timelines Matter?

A cluster may have multiple WAL branches due to failovers/PITR. A restore must select the correct timeline so it does not replay the wrong branch of history.

## 18. Archive Recovery Is Not Always PITR

Archive recovery can replay WAL to bring a base backup to the latest available point, without necessarily stopping at a chosen timestamp.

PITR is a specific use case of archive recovery in which the DBA sets a recovery target to avoid a bad event or recover to a desired state.

- **Archive recovery** describes the source/method of replaying from the archive.
- **PITR** describes the goal of recovering to a specific point in history.

## 19. What Is Standby Replay?

Standby replay is the process by which a PostgreSQL standby continuously applies WAL generated by the primary.

WAL can arrive from:

- Streaming replication via the WAL receiver.
- The WAL archive via `restore_command`.
- WAL already present in `pg_wal`.

A standby typically stays in recovery mode and keeps waiting for additional WAL. Unlike PITR, which recovers independently to a target and promotes, standby replay aims to **stay caught up with the primary long-term**.

~~~text
Primary
   |
   | WAL stream
   v
Standby WAL receiver
   |
   v
WAL files / receive position
   |
   v
Startup process replays WAL
   |
   v
Standby data state approaches primary
~~~

## 20. Preparing a Standby from a Base Backup

A physical standby is usually created from a base backup of the primary:

~~~bash
pg_basebackup -h primary.example -D /var/lib/postgresql/standby -U replicator -X stream -P -R
~~~

`-R` instructs `pg_basebackup` to generate the standby configuration, typically including `standby.signal` and connection settings in `postgresql.auto.conf`, depending on version/tool behavior.

Afterward, configure authentication, `primary_conninfo`, replication slots if used, WAL archive `restore_command`, and storage/network settings.

### 20.1. A Standby Must Start from a Valid Base Backup

Do not simply copy a running data directory using ordinary file-copy tools. Use `pg_basebackup` or a supported physical backup method to ensure consistency.

## 21. standby.signal

On PostgreSQL 12+, the file:

~~~text
standby.signal
~~~

instructs the server to run in standby mode.

In standby mode, PostgreSQL continues recovery/WAL replay and waits for more WAL from the primary/archive. If `primary_conninfo` is configured, walreceiver can connect to receive streaming WAL.

### 21.1. standby.signal Differs from recovery.signal

| File | Intent |
|---|---|
| `recovery.signal` | Archive recovery/PITR |
| `standby.signal` | Continuous standby mode |

Do not create signal files arbitrarily on a running cluster. These files are read at startup.

## 22. primary_conninfo and walreceiver

A standby typically requires `primary_conninfo`:

~~~text
primary_conninfo = 'host=primary.example port=5432 user=replicator application_name=standby_a'
~~~

This configuration holds connection details for the primary. Protect passwords/secrets using appropriate credential mechanisms; never commit secrets to source control.

Walreceiver is the process that receives WAL from the primary. It writes WAL to the standby's WAL area, after which the startup process/recovery machinery replays the records.

### 22.1. Receive Differs from Replay

WAL may already be received and written on the standby before it has been replayed to data pages. Therefore, receive LSN and replay LSN are two distinct checkpoints of progress.

## 23. Streaming Replication and Archive Fallback

A standby can use `restore_command` to fetch WAL from the archive when needed, then switch to streaming from the primary to stay current.

~~~text
Standby startup
      |
      v
Check local WAL
      |
      v
Try archive WAL if needed
      |
      v
Connect to primary for streaming
      |
      v
Continuous replay
~~~

The exact order of WAL lookup and retries depends on startup/recovery state. The key point is that archive and streaming complement each other; the archive helps a standby catch up when WAL segments are no longer on the primary but are still archived.

## 24. hot_standby

If `hot_standby` is enabled and recovery reaches a consistent state, the standby can serve read-only queries while continuing to replay WAL.

~~~sql
SHOW hot_standby;

SELECT
    current_database(),
    pg_is_in_recovery();
~~~

On a replaying standby, `pg_is_in_recovery()` returns true.

### 24.1. Read-Only Does Not Mean Conflict-Free

Standby queries can conflict with WAL replay — for example, when recovery needs to clean up row versions still needed by a standby query. PostgreSQL has recovery conflict mechanisms and may cancel queries depending on configuration/policy.

Hot standby is a read-only query mode, not a second writable primary.

## 25. Standby Replay and Promotion

When failover is needed, a standby can be promoted to become the new primary.

~~~sql
SELECT pg_promote();
~~~

or by using the appropriate management tool / `pg_ctl`.

After promotion:

- The server exits standby recovery mode.
- It begins accepting writes in the primary role.
- It creates a new timeline.
- It no longer replays WAL from the old primary as an ordinary standby.

Promotion is a failover decision; fencing/STONITH or an equivalent safeguard must be in place to ensure the old primary cannot continue accepting writes and cause split brain.

## 26. pg_is_in_recovery

~~~sql
SELECT pg_is_in_recovery();
~~~

This function returns true when the server is in recovery mode (including standby mode). It returns false when the server is operating normally after recovery/promotion.

This is a useful check for health checks and applications needing to distinguish primary from standby.

Do not rely solely on this function to select the primary in complex failover systems; combine it with a cluster manager, routing, and fencing.

## 27. Tracking WAL Receive and Replay LSN

On the standby:

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
~~~

- `pg_last_wal_receive_lsn()`: most recent WAL position received via streaming replication.
- `pg_last_wal_replay_lsn()`: most recent WAL position replayed.
- `pg_last_xact_replay_timestamp()`: timestamp of the last replayed transaction based on corresponding metadata.

### 27.1. Replay Timestamp Has Limitations

If the primary has no new transactions, the replay timestamp can look stale even when the standby is completely caught up. Do not rely on this timestamp alone to judge lag; compare LSNs and primary/standby state.

## 28. Inspecting walreceiver

On the standby:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

This view shows WAL receiver status, upstream source, slot, receive LSN, and related details depending on version.

If the view returns no rows, the standby may not be streaming at that moment; it could be replaying from the archive, disconnected from the primary, or not in standby mode.

## 29. Inspecting Primary Replication State

On the primary:

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
    replay_lsn
FROM pg_stat_replication;
~~~

This is the primary's view of connected WAL sender processes.

A standby may receive WAL quickly yet replay slowly. Compare sent/write/flush/replay LSNs to distinguish network, receiver, flush, and replay lag.

## 30. Synchronous Replication and Commit Timing

Standby replay and synchronous replication are related but not identical.

The primary can configure `synchronous_standby_names`, and transactions use `synchronous_commit`:

- `remote_write`: waits for the standby to write WAL to the OS.
- `on`: waits for the standby to flush WAL per sync policy.
- `remote_apply`: waits for the standby to replay/apply the transaction.
- `local`: waits only for local flush.
- `off`: may return success before local flush.

`remote_apply` is the level that ensures a transaction has been applied on the selected synchronous standby before the primary returns commit success. It does not mean every replica in the topology has replayed it.

### 30.1. An Async Standby Can Lose Recent WAL on Failover

If the primary acknowledges commits without waiting for the standby to receive/flush them, the standby may lag behind. Promoting that standby immediately after a primary crash can lose those recent transactions.

RPO depends on sync mode, topology, network, and failover policy.

## 31. Crash Recovery and Standby Replay Use the Same Redo Machinery

Both use WAL redo to update pages according to WAL history.

Key differences:

- Crash recovery runs after an unclean shutdown and typically finishes so the server can operate normally.
- Standby replay stays in recovery mode, continuously receiving WAL and keeping the server in standby state.
- A standby can be promoted to become a primary.

This is a difference in **lifecycle and intent**, not a completely different redo algorithm.

## 32. Archive Recovery and Standby Replay Both Use restore_command

A standby can fetch WAL from the archive via `restore_command`. A PITR restore also fetches WAL from the archive.

However:

- PITR typically stops at a target and promotes/pauses/shuts down.
- A standby keeps waiting for new WAL and retains `standby.signal`.
- A standby can combine archive restore with streaming replication.

Do not distinguish the two scenarios solely by checking whether `restore_command` is configured.

## 33. recovery_target_time and Transaction Boundaries

Example:

~~~text
recovery_target_time = '2026-11-14 09:30:00+07'
recovery_target_action = 'pause'
~~~

Target time is compared against transaction commit timestamps according to PostgreSQL semantics. If multiple transactions commit close to the target, verify the data after recovery rather than assuming the target corresponds to a single SQL statement.

You can use `recovery_target_xid` or a named restore point if you need a more exact reference point.

## 34. recovery_target_timeline and History Files

When a standby is promoted, PostgreSQL creates a new timeline and a corresponding history file. PITR can select a timeline according to configuration.

`recovery_target_timeline = 'latest'` follows the latest timeline reachable via available history files.

This is useful in environments with multiple failovers, provided the archive contains all required WAL and `.history` files.

### 34.1. Do Not Delete History Files Arbitrarily

Timeline history files identify WAL branches and fork points. Missing them can cause recovery to pick the wrong branch or fail to follow the desired timeline.

## 35. Recovery Consistency and Control Data

PostgreSQL uses the control file/checkpoint state to determine cluster state and the recovery starting point.

Tool:

~~~bash
pg_controldata /path/to/data_directory
~~~

allows viewing control metadata such as checkpoint location, timeline, and cluster state depending on version.

Never edit the control file with a hex editor or manually alter the checkpoint LSN. This is critical cluster metadata.

## 36. Log Messages During Recovery

During startup, logs may include messages such as:

- Database system was interrupted.
- Starting crash recovery.
- Redo starts at LSN.
- Redo done at LSN.
- Consistent recovery state reached.
- Entering standby mode.
- Started streaming WAL from primary.
- Recovery paused/reached target.
- Database system is ready to accept connections.

Exact messages vary by version and recovery path. Use logs alongside `pg_is_in_recovery()` and LSN metrics to determine which phase the server is in.

## 37. PITR and Archive Gaps

If `restore_command` cannot locate a required WAL segment:

- Archive recovery may halt.
- Logs clearly record the failure to retrieve the WAL file.
- The database cannot advance past the missing WAL point.
- Targets located after the gap cannot be reached from that backup/archive set.

Never bypass the error by creating an empty WAL file with the same name. Either recover the missing segment from an archive replica/backup or choose a valid target before the gap.

## 38. Archive Command Failures and pg_wal Growth

If `archive_command` fails repeatedly, PostgreSQL retains unarchived WAL rather than recycling it normally, causing `pg_wal` to grow.

Monitor:

- Archive failures in logs.
- `pg_stat_archiver` on versions providing the view.
- Filesystem free space.
- WAL generation rate.
- Archive destination connectivity/permissions.
- `archive_timeout` and workload segment switching.

Never manually delete unarchived WAL via filesystem commands to free disk space.

## 39. pg_stat_archiver

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

This view shows successful/failed archive counts and details of the most recent events. It does not prove that the archive repository has proper retention, replication, and restore validation.

If `failed_count` increases, inspect `archive_command` logs and the archive destination.

## 40. archive_timeout

~~~sql
SHOW archive_timeout;
~~~

This parameter forces a WAL segment switch at a configured interval so WAL is archived more frequently, even when a segment is not yet full.

It affects archive frequency/archive latency for some workloads, but it does not make archiving synchronous with commits or guarantee a transaction is archived before `COMMIT` returns.

## 41. Backup Verification and Restore Testing

A backup completing without errors is not enough to prove recoverability.

Best practices:

- Verify backup completion.
- Validate manifest/backup integrity with an appropriate tool, such as `pg_verifybackup` for compatible backups.
- Verify WAL archive continuity.
- Perform a test restore of the base backup.
- Test replaying to a target.
- Validate application data and constraints.
- Measure restore/replay duration.
- Document achieved RPO/RTO.

Only a **restore test** proves that the backup + WAL + recovery workflow actually works.

## 42. Lab: Observing Crash Recovery via Immediate Shutdown

Only perform this on an isolated PostgreSQL lab instance, never on a shared cluster.

Create a table:

~~~sql
CREATE TABLE recovery_lab (
    id BIGINT PRIMARY KEY,
    note TEXT
);

INSERT INTO recovery_lab VALUES (1, 'before restart');
~~~

Then use `pg_ctl`/the lab service manager to stop the server in immediate mode and restart it.

Inspect the startup logs: PostgreSQL detects the unclean shutdown and runs crash recovery.

Verify:

~~~sql
SELECT *
FROM recovery_lab;
~~~

Committed data should remain intact according to the durability/storage setup.

### 42.1. Do Not Cut Power on Real Machines

Crash simulations should run inside an isolated VM/container/test cluster. Never kill storage or power off a production machine to test WAL recovery.

## 43. Lab: Archive Recovery/PITR

In an isolated lab, set up:

1. Appropriate `wal_level` and `archive_mode`.
2. `archive_command` storing WAL in a durable archive location.
3. Take a base backup.
4. Execute several transactions with recorded timestamps/restore points.
5. Execute an erroneous transaction to simulate an event to avoid.
6. Restore the base backup to a new data directory.
7. Configure `restore_command`.
8. Place `recovery.signal` and set a target before the erroneous transaction.
9. Start the restored instance.
10. Verify the recovered data.

Do not overwrite the primary data directory in the lab. Ensure the WAL archive contains all segments from the backup through the target.

## 44. Lab: Standby Replay

Across two PostgreSQL lab instances:

**Primary:**

- Enable required replication settings.
- Create a replication role and matching `pg_hba` rule.
- Set `wal_level=replica` or higher.
- Configure `max_wal_senders` and a slot if used.

**Standby:**

- Take a base backup with `pg_basebackup`.
- Use `-R` or configure `standby.signal` + `primary_conninfo`.
- Start the standby.
- Query `pg_is_in_recovery()`.
- Insert rows on the primary and observe them appear on the standby after replay.

On the standby:

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
~~~

By default, a standby is read-only while in recovery.

## 45. Lab: Pausing and Resuming Replay

In a standby lab environment:

~~~sql
SELECT pg_wal_replay_pause();
~~~

Observe that the replay LSN stops advancing while the primary continues generating WAL.

Then run:

~~~sql
SELECT pg_wal_replay_resume();
~~~

Replay resumes once WAL is available.

Only pause replay in a lab or during intentional maintenance; it increases standby lag and can retain WAL or impact failover readiness.

## 46. Lab: Promoting a Standby

On the lab standby:

~~~sql
SELECT pg_promote();
~~~

After promotion:

~~~sql
SELECT pg_is_in_recovery();
~~~

The result switches to false once promotion completes and the server operates as a primary.

Check the timeline/history and write capability. In production, fence the old primary and update routing/cluster manager to prevent split brain.

## 47. Choosing the Right Recovery Type for Each Scenario

| Incident / Need | Appropriate approach |
|---|---|
| PostgreSQL process/host crashed, data directory intact | Crash recovery |
| Need to restore database before an erroneous DELETE | Base backup + archive recovery/PITR |
| Need a secondary database continuously following primary | Physical standby replay |
| Primary lost, need to shift traffic to standby | Promote standby per failover procedure |
| Need to restore one table/subset of rows from an old backup | Restore separately, then export/import data |
| Missing WAL segment needed for PITR | Locate archived segment or pick an earlier valid target |

Do not use crash recovery to fix a committed logical data error; crash recovery preserves committed transactions according to database history.

## 48. RPO and RTO

- **RPO (Recovery Point Objective):** maximum tolerable amount of data loss.
- **RTO (Recovery Time Objective):** maximum tolerable time to restore service.

| Method | RPO depends on | RTO depends on |
|---|---|---|
| Crash recovery | Durable WAL remaining on storage | Startup, redo volume, I/O |
| Archive recovery/PITR | Archive continuity and reachable target | Restoring base backup + WAL replay |
| Standby replay | Sync/async replication lag and failover state | Promotion, fencing, routing |

An async standby can lose commits not yet received/replayed if the primary crashes. Synchronous replication with an appropriate policy can lower RPO at the cost of higher commit latency and dependency on standby availability.

## 49. Synchronous Replication Is Not an Archive Backup

A synchronous standby is an online server receiving WAL. A WAL archive is a repository storing WAL segments for backup/PITR.

They address different failure modes:

- A standby supports fast failover.
- An archive supports PITR and historical recovery.
- Base backup + archive enable recovery if both primary/standby are corrupted or if you must roll back prior to a logical error.

A production system typically needs both backup/archive and standby replicas, along with restore testing.

## 50. Common Misconceptions

### 50.1. Crash Recovery Means Restoring from Backup

False. Crash recovery uses the current data directory and required WAL to recover after an unclean shutdown.

### 50.2. Archive Recovery and Standby Replay Are the Same Thing

False. Both can use a WAL archive, but PITR typically ends at a target; a standby stays in recovery and continues receiving WAL.

### 50.3. Only a WAL Archive Is Needed, Without a Base Backup

False. Rebuilding a cluster requires a valid base backup.

### 50.4. Having a Base Backup Is Enough for PITR

False. A continuous WAL chain from the backup to the target is required.

### 50.5. If a Standby Received WAL, It Has Replayed It

False. Receive LSN and replay LSN are different.

### 50.6. hot_standby Allows Writes on a Replica

False. Queries on a hot standby are read-only during recovery.

### 50.7. pg_last_xact_replay_timestamp Always Measures Lag Accurately

False. If the primary is idle, the last replay timestamp can look old even when the standby is caught up.

### 50.8. recovery.signal Is Used for Every Recovery Type

False. Crash recovery is automatic; `recovery.signal` is for archive recovery; `standby.signal` is for standby mode.

### 50.9. Promote Only Flips a Flag

False. Promotion exits recovery, creates a new timeline, and changes the server role; fencing and routing updates are required.

### 50.10. A Successful Archive Command Means Backups Are Restorable

False. You must verify archive continuity, base backups, timelines, and run restore tests.

### 50.11. archive_timeout Equals Synchronous Commit

False. It affects segment switching/archive frequency, not archiving before COMMIT returns.

### 50.12. synchronous_commit=on Means Every Standby Has Replayed

False. `on` waits for remote flush on the synchronous standby per policy; `remote_apply` waits for apply/replay.

### 50.13. Manually Deleting WAL Files Fixes an Archive Backlog

False. Doing so can destroy WAL required for crash recovery, replication, or PITR and break the cluster.

## 51. Recovery Operations Checklist

**Crash recovery**

1. Determine whether shutdown was clean or immediate/crash.
2. Preserve the data directory and WAL intact.
3. Inspect startup logs.
4. Identify redo start/end LSNs and checkpoints.
5. Check for storage/filesystem errors.
6. Confirm the server is consistent and accepting connections.

**Archive recovery/PITR**

7. Is an appropriate base backup available?
8. Are all WAL segments from the backup to the target available?
9. Are the archive repository and timeline history files intact?
10. Can `restore_command` retrieve the files properly?
11. Are the target time/XID/LSN/name timezone and semantics clear?
12. Has `recovery_target_action` been explicitly chosen?
13. Is the restore running on a separate data directory/host?
14. Has application data been validated after recovery?

**Standby replay**

15. Is the standby base backup valid?
16. Are `standby.signal` and `primary_conninfo` configured correctly?
17. Is the WAL receiver connected?
18. Are receive/replay LSNs advancing?
19. Is `hot_standby` enabled if read-only queries are needed?
20. Are there recovery conflicts?
21. Does the sync/async mode match RPO requirements?
22. Does promotion have safe fencing/routing?

**Disaster recovery**

23. Have backups + WAL archives undergone restore testing?
24. Have actual RPO/RTO been measured?
25. Are archive failures and disk capacity monitored?
26. Is there a reviewed failover/PITR playbook?

## 52. Practice Exercises

### Exercise 1 — Crash recovery

When does PostgreSQL automatically run crash recovery?

**Hint:** after an unclean shutdown/crash.

### Exercise 2 — Archive recovery

What two foundational data components does archive recovery require?

**Hint:** a base backup and a continuous WAL archive.

### Exercise 3 — Standby replay

What is the primary goal of standby replay?

**Hint:** continuously applying WAL to follow the primary.

### Exercise 4 — WAL redo

Why do all three recovery types involve WAL redo?

**Hint:** WAL describes the changes that need to be applied.

### Exercise 5 — Checkpoint

How does a checkpoint help recovery?

**Hint:** determines redo start and reduces the amount of WAL to replay.

### Exercise 6 — Crash transaction

Can WAL records of an uncommitted transaction be redone?

**Hint:** physical changes can be redone; the transaction remains uncommitted/not visible.

### Exercise 7 — Clean shutdown

How does `pg_ctl` immediate differ from fast?

**Hint:** immediate is not a clean shutdown and requires crash recovery.

### Exercise 8 — recovery.signal

Which mode does this file request?

**Hint:** archive recovery.

### Exercise 9 — standby.signal

Which mode does this file request?

**Hint:** standby.

### Exercise 10 — PostgreSQL 12

Since PostgreSQL 12, what replaced `recovery.conf`?

**Hint:** signal files and recovery parameters in postgresql.conf/auto.conf.

### Exercise 11 — restore_command

What are the two key placeholders?

**Hint:** %f and %p.

### Exercise 12 — PITR

What does `recovery_target_time` do?

**Hint:** stops replay at the target time.

### Exercise 13 — Target action

Name the three `recovery_target_action` values.

**Hint:** pause, promote, shutdown.

### Exercise 14 — Restore point

Which function creates a named restore point?

**Hint:** pg_create_restore_point.

### Exercise 15 — Timeline

Why does promotion create a new timeline?

**Hint:** to start a new WAL history branch.

### Exercise 16 — History file

What is a timeline history file used for?

**Hint:** describes fork points and timeline relationships.

### Exercise 17 — Base backup

Why can't a WAL archive replace a base backup?

**Hint:** WAL only describes changes; it cannot build an entire cluster from scratch.

### Exercise 18 — Archive gap

What happens if a required WAL segment is missing?

**Hint:** recovery cannot replay past the gap.

### Exercise 19 — Standby receive

Which function returns the receive LSN?

**Hint:** pg_last_wal_receive_lsn.

### Exercise 20 — Standby replay

Which function returns the replay LSN?

**Hint:** pg_last_wal_replay_lsn.

### Exercise 21 — Recovery state

Which function checks whether the server is in recovery?

**Hint:** pg_is_in_recovery.

### Exercise 22 — WAL receiver

Which view monitors the WAL receiver?

**Hint:** pg_stat_wal_receiver.

### Exercise 23 — Primary view

Which view monitors WAL sender/standby progress from the primary?

**Hint:** pg_stat_replication.

### Exercise 24 — hot_standby

What kind of queries does hot standby allow?

**Hint:** read-only.

### Exercise 25 — Recovery conflict

Why can a query on a standby be canceled?

**Hint:** conflict with WAL replay/cleanup.

### Exercise 26 — Promotion

Which function can promote a standby?

**Hint:** pg_promote.

### Exercise 27 — Split brain

Why is fencing the old primary necessary before or during promotion?

**Hint:** to prevent two primaries from accepting writes.

### Exercise 28 — Sync replication

How do `remote_write`, `on`, and `remote_apply` differ?

**Hint:** standby write, flush, and apply.

### Exercise 29 — Async replication

What can be lost when failing over to an async standby?

**Hint:** commits not yet received/replayed.

### Exercise 30 — Archive timeout

Does `archive_timeout` force `COMMIT` to wait for archiving?

**Hint:** no.

### Exercise 31 — Archive failure

Why can `pg_wal` grow when `archive_command` fails?

**Hint:** unarchived WAL is not recycled normally.

### Exercise 32 — pg_stat_archiver

Name three useful metrics.

**Hint:** archived_count, failed_count, last_failed_wal/time.

### Exercise 33 — Restore verification

Why are restore tests necessary?

**Hint:** a completed backup does not prove it is restorable.

### Exercise 34 — pg_verifybackup

What does this tool help verify?

**Hint:** the integrity of a compatible base backup.

### Exercise 35 — RPO

What does RPO represent?

**Hint:** maximum tolerable data loss.

### Exercise 36 — RTO

What does RTO represent?

**Hint:** target recovery time.

### Exercise 37 — PITR lab

List the main steps to restore a base backup to just before an erroneous transaction.

**Hint:** restore, restore_command, recovery.signal, target, replay.

### Exercise 38 — Standby lab

How do you check how far a standby has replayed?

**Hint:** compare receive/replay LSNs.

### Exercise 39 — Recovery target timeline

Why are history files needed when recovering after multiple promotions?

**Hint:** to select the correct WAL branch.

### Exercise 40 — Choosing recovery

A DBA needs to restore the database to before a committed `DROP TABLE` statement. Which method should they choose?

**Hint:** PITR from a base backup and WAL archive.

## 53. Frequently Asked Questions

### Does crash recovery require a base backup?

Not under normal circumstances. It recovers the current data directory using required WAL after a crash. If the data directory is corrupted or lost, a backup/restore is needed.

### Is archive recovery always PITR?

No. Archive recovery describes replaying from an archive; PITR is the use case of stopping at a specific target.

### Does standby replay use the WAL archive?

It can. A standby can combine archive restore with streaming replication.

### How do recovery.signal and standby.signal differ?

`recovery.signal` requests archive recovery; `standby.signal` requests continuous standby mode.

### Once a standby receives WAL, is new data immediately readable?

Not necessarily. WAL must be replayed; the receive LSN can be ahead of the replay LSN.

### Does hot_standby allow INSERT/UPDATE on a standby?

No. Queries on a hot standby are read-only during recovery.

### Does promotion stop the server from replaying the old primary?

After promotion, the server moves to a new timeline and operates as a primary. Rejoining requires an appropriate procedure such as `pg_rewind` or a rebuild depending on state/timeline.

### Does synchronous_commit=on wait for standby replay?

Not in the sense of apply. It waits for remote flush on the synchronous standby; `remote_apply` waits for replay/apply.

### Can archived WAL replace a backup?

No. A valid base backup plus a continuous WAL chain are required.

### Does archive_timeout guarantee every transaction is archived when COMMIT returns?

No. Segment archiving and commit acknowledgment are separate processes.

### What happens if a WAL segment is missing?

Recovery cannot replay past that gap. You must retrieve the segment or select a valid target prior to the gap.

### Does pg_last_xact_replay_timestamp measure absolute lag?

No. An idle primary can make the timestamp look stale even when the standby is caught up. Compare LSNs and primary/standby state.

### Can I trigger crash recovery manually by creating recovery.signal?

No need. Crash recovery is detected automatically by PostgreSQL. `recovery.signal` is for archive recovery.

### Is a completed backup guaranteed to restore successfully?

No. You must verify integrity, WAL continuity, and perform restore tests.

## 54. Summary

Key functions/views/files:

~~~sql
-- Is the server in recovery/standby?
SELECT pg_is_in_recovery();

-- On standby: receive and replay progress.
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();

-- On standby: receiver state.
SELECT * FROM pg_stat_wal_receiver;

-- On primary: standby progress.
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;

-- Archive health.
SELECT * FROM pg_stat_archiver;

-- Create a restore point before an important change.
SELECT pg_create_restore_point('before_migration');

-- Promote standby per failover procedure.
SELECT pg_promote();

-- Pause/resume standby replay in lab.
SELECT pg_wal_replay_pause();
SELECT pg_wal_replay_resume();
~~~

Key principles to remember:

1. **Crash recovery** runs automatically after an unclean shutdown, using required WAL in the data directory.
2. **Archive recovery** starts from a base backup and replays archived WAL; PITR involves choosing a recovery target.
3. **Standby replay** continuously applies WAL so the standby follows the primary, typically via streaming and/or archive.
4. All three use WAL redo, but differ in goal, WAL source, signal file, and lifecycle.
5. Checkpoints help determine the redo start point; they do not replace base backups or WAL archives.
6. Uncommitted transactions do not become committed simply because their WAL records were redone.
7. PostgreSQL 12+ uses `recovery.signal` for archive recovery and `standby.signal` for standby mode.
8. PITR requires a valid base backup and a continuous WAL chain.
9. Recovery targets can be based on time, XID, LSN, or named restore points.
10. Timeline/history files are critical after promote/PITR.
11. Standby receive LSN and replay LSN are two distinct progress indicators.
12. Hot standby enables read-only queries during recovery and can encounter recovery conflicts.
13. Promotion creates a new primary/timeline and requires fencing to prevent split brain.
14. `synchronous_commit=on` waits for remote flush under the synchronous replication policy; `remote_apply` waits for replay.
15. An async standby can miss recent commits during failover.
16. WAL archives and synchronous standbys solve different failure modes; production typically needs both.
17. `archive_command` failures can cause `pg_wal` growth; never delete WAL manually.
18. Backups must be verified and restore-tested; RPO/RTO must be measured in practice.

Decision diagram:

~~~text
Does PostgreSQL need recovery?
        |
        +--> Did the server just crash with data directory intact?
        |          |
        |          v
        |      Crash recovery
        |      Local WAL + checkpoint
        |
        +--> Need to restore a backup to a point in time?
        |          |
        |          v
        |      Archive recovery / PITR
        |      Base backup + WAL archive
        |      recovery.signal + target
        |
        +--> Need a secondary server continuously following primary?
                   |
                   v
               Standby replay
               standby.signal
               Streaming/archive WAL
                   |
                   +--> Read-only hot standby
                   |
                   +--> Promote on failover
~~~

**Conclusion:** Crash recovery, archive recovery, and standby replay all rely on WAL, yet serve three distinct purposes: **recovering a server after a crash, restoring a backup to a historical point, and keeping a standby synchronized with its primary**. Proper backup/failover design requires distinguishing WAL sources, signal files, timelines, targets, and acknowledgment semantics; only by combining base backups, continuous archiving, monitored standbys, and restore/failover testing does a system achieve a reliable recovery process.
