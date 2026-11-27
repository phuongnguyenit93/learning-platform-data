# Stuck Recovery, Archive Failures, and Broken WAL Chains

PostgreSQL uses the Write-Ahead Log (WAL) to guarantee write durability and ship changes to standbys. When restoring from a base backup, PostgreSQL must read and replay a continuous chain of WAL up to the recovery target. If a segment was never archived, became corrupted, belongs to the wrong timeline, or cannot be downloaded, recovery can stall before reaching the target.

A database cluster can appear "stuck" for very different reasons: a standby is normally waiting for new WAL, PITR reached its recovery target and paused intentionally, a restore command repeatedly fails, an archive is missing a segment, or storage has run out of space. Identify the exact state before intervening. Deleting WAL, promoting a standby, or repeatedly restarting without knowing the root cause can destroy recoverability.

## 1. How WAL, Archiving, and Recovery Relate

WAL records low-level changes so PostgreSQL can redo operations after a crash or restore from backup. WAL is divided into segments named by timeline, log ID, and segment number. Segment size is typically 16 MB in default builds, though it can differ if chosen at cluster initialization; never hardcode that size in inspection scripts.

Distinguish three operations:

- **WAL generation:** the primary creates WAL as transactions and internal operations modify data.
- **WAL archiving:** PostgreSQL copies completed WAL segments to a durable archive repository.
- **WAL replay:** PostgreSQL reads WAL and reapplies changes to the data directory during crash recovery, archive recovery, or standby recovery.

A typical PITR (Point-in-Time Recovery) flow requires a base backup and all required WAL from the backup start point up to the target. If a single segment is missing in the middle of the chain, PostgreSQL cannot skip over it and continue as if the data were intact.

~~~mermaid
flowchart TD
    A[Consistent base backup] --> B[Next WAL segment]
    B --> C[Subsequent WAL segment]
    C --> D[WAL segment ...]
    D --> E[WAL containing recovery target]
    E --> F[Database recovered to target]
    C --> X[Missing or corrupted segment]
    X --> Y[Recovery cannot continue past the gap]
~~~

Archiving and replication are related but do not replace each other. A standby can fetch WAL via streaming replication, archive recovery, or fall back between both depending on configuration. Backup archives serve long-term recovery; streaming replication primarily keeps standbys caught up with an active primary.

### Key Concepts to Distinguish

| Component | Role |
|---|---|
| Base backup | Consistent physical copy serving as the starting point for recovery |
| WAL segment | File unit holding a sequence of WAL records |
| WAL archive | Repository storing completed segments, normally outside the data directory |
| Timeline | Branch of WAL history; a new timeline typically appears after promotion or completing a recovery branch |
| `restore_command` | Command PostgreSQL calls to retrieve a needed file from the archive |
| `archive_command` | Command PostgreSQL calls to transfer a completed segment to the archive |
| recovery target | Timestamp, transaction, or WAL position where PITR should stop |

## 2. Distinguishing a Standby Waiting for WAL from a Broken Recovery

Not every long-lasting recovery state is an error. An active standby may have replayed all available WAL and simply be waiting for the primary to send more. If the primary produces no new transactions, the replay LSN can remain unchanged for long periods while the system is completely healthy.

A PITR run can also pause intentionally upon reaching its recovery target. With `recovery_target_action = 'pause'`, PostgreSQL halts replay at the target so operators can inspect data before promoting. That state differs completely from missing WAL.

First determine what mode the instance is in:

~~~sql
SELECT
    pg_is_in_recovery() AS is_in_recovery,
    pg_is_wal_replay_paused() AS replay_is_paused,
    pg_last_wal_receive_lsn() AS last_received_lsn,
    pg_last_wal_replay_lsn() AS last_replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_time;
~~~

Interpretation:

- `pg_is_in_recovery() = false`: the instance is running as a primary after recovery finished or after promotion.
- `pg_is_in_recovery() = true`: the instance is still in recovery/standby mode.
- `pg_is_wal_replay_paused() = true`: replay is paused. Check recovery targets and logs before resuming.
- `last_received_lsn` differs from `last_replayed_lsn`: the standby received WAL that still awaits replay.
- Both LSNs remain stationary: the standby may simply be waiting on WAL sources, not necessarily broken.

`pg_last_xact_replay_timestamp()` reflects only the timestamp of the last replayed transaction. If the primary has no new transactions, this value ages even while the standby is fully caught up. Compare LSNs, receiver state, and logs instead of relying on a single timestamp.

On a standby using streaming replication, inspect the WAL receiver state:

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

If the view returns no rows, the receiver may not have started, lost connectivity, is unconfigured, or the instance is currently reading only from the archive. Check `primary_conninfo`, `restore_command`, and PostgreSQL logs.

On the primary, inspect connected standbys:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_stat_replication;
~~~

A standby will not appear in this view if it is not currently connected. This view also does not tell you whether backup archives are complete.

## 3. Archive and Restore Configuration

### `archive_mode` and `archive_command`

On the primary, WAL archiving is typically enabled with configuration similar to:

~~~conf
archive_mode = on
archive_command = '/usr/local/bin/archive-wal "%p" "%f"'
archive_timeout = 60s
~~~

This is an illustrative example. `archive_mode` must be enabled in a version-appropriate way and normally requires restarting PostgreSQL; changes to `archive_command` can be applied via configuration reload. `archive_timeout` forces switching to a new segment after the configured interval when WAL activity exists, ensuring segments archive sooner. It does not generate new WAL when the database is completely idle.

PostgreSQL substitutes `%p` with the source WAL file path and `%f` with the WAL filename. The archive script must:

1. Run under PostgreSQL's OS user account.
2. Read the source file and write to the archive repository.
3. Return exit code `0` only after the file is durably stored.
4. Be idempotent on retries without corrupting archives or overwriting files with different contents.
5. Log clearly enough to trace permission, capacity, network, or storage service errors.

If a file with the same name already exists at the archive destination, the script should verify identical contents before treating the retry as a success. If contents differ, fail and investigate—never overwrite blindly. With object storage, return success only after upload finishes and the storage service confirms durability at your required level.

PostgreSQL retries archiving any segment whose previous command returned non-zero. Hence, the archive command must be safe to re-run. A command returning `0` when the file was not actually saved tricks PostgreSQL into marking the segment archived, creating an unrecoverable gap later.

`archive_mode = always` can be used when WAL received or replayed during recovery/standby must also be archived, if supported by your operators and architecture. Account for timelines, filenames, and potential collisions when multiple instances write to the same archive. Never enable this mode simply to work around an undiagnosed archive error.

### `restore_command`

During archive recovery, PostgreSQL retrieves individual WAL segments by filename. `restore_command` has the form:

~~~conf
restore_command = '/usr/local/bin/restore-wal "%f" "%p"'
~~~

PostgreSQL replaces `%f` with the requested filename and `%p` with the target path where the command must write the file. The script must return `0` once the file is fully downloaded and written to `%p`, and return non-zero when the file does not exist or the transfer fails.

Simple example when the archive stores gzip-compressed files:

~~~conf
restore_command = 'gzip -dc /srv/pg-archive/%f.gz > "%p"'
~~~

This example works only if archived filenames genuinely match the WAL name plus `.gz`, PostgreSQL can read that repository, and the command returns non-zero when files are missing or corrupted. For object storage, use an authenticated script/CLI and check exit codes; avoid embedding credentials directly in command lines or logs.

Never write a `restore_command` that returns `0` when a file does not exist. If a script creates an empty file or exits `0` despite download failure, PostgreSQL tries reading an invalid file and recovery fails in harder-to-diagnose ways.

In standby mode, if `restore_command` cannot find the next WAL segment, PostgreSQL tries streaming replication when `primary_conninfo` is configured. If streaming has no new data either, the standby waits or checks the archive again according to its recovery loop. Therefore, log entries noting the archive lacks the next segment are sometimes normal; inspect receiver state and replay progress together.

## 4. Reading WAL Archiver Status

`pg_stat_archiver` is the starting point for spotting archive failures:

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

Meaningful fields:

- `archived_count`: segments archived successfully since stats reset.
- `last_archived_wal` and `last_archived_time`: most recently archived segment and timestamp.
- `failed_count`: failed archive attempts since stats reset.
- `last_failed_wal` and `last_failed_time`: most recent failed segment and timestamp.
- `stats_reset`: when counters were reset.

Do not look solely at absolute `failed_count`. Sample over time to verify whether failures keep climbing and whether `last_archived_time` is advancing. An old resolved failure looks very different from ongoing archive failures.

On the PostgreSQL host, you can inspect the archive queue inside the internal directory `pg_wal/archive_status`:

- `.ready` files represent segments waiting to be archived.
- `.done` files represent segments already archived.

A growing `.ready` backlog indicates the archiver is falling behind. Never manually edit, rename, or delete these status files. They are internal metadata managed by PostgreSQL; tampering with them makes archive state diverge from what is actually stored.

If `pg_stat_archiver` is stalled, inspect PostgreSQL logs and archive script errors. Common causes include:

- Archive target out of disk space, quota, or object count.
- Network outage, DNS failure, expired TLS, or unreachable object storage.
- PostgreSQL OS account lacking read permissions on WAL or write permissions at destination.
- Wrong path, bucket/prefix name, or broken mount configuration.
- Script errors in placeholders, quoting, or special characters in filenames.
- Archive command returning non-zero even after writing the file, causing endless retries.
- File with the same name already existing with different content or retry logic failing.
- Upload throughput trailing behind WAL generation rate, lengthening the queue.

### Why Archive Failures Can Fill `pg_wal`

PostgreSQL must retain unarchived WAL so it can keep retrying. During prolonged archive failures, unarchived segments pile up in `pg_wal`. Replication slots or lagging standbys can also retain needed WAL. WAL footprint can thus grow until the filesystem fills and impacts database availability.

`max_wal_size` is a soft management/checkpoint target, not a hard limit guaranteeing `pg_wal` cannot exceed that size. Never delete segments in `pg_wal` to free space. First restore archiving or resolve WAL retention blockers while ensuring sufficient space for PostgreSQL to run and drain the archive queue.

## 5. Handling Archive Failures in Order

When `failed_count` climbs or `.ready` files pile up, follow this sequence.

### Step 1: Identify the Latest Error

Read PostgreSQL logs around `last_failed_time` and look up the segment in `last_failed_wal`. Read the archive script's own logs if it maintains any. Capture the exact OS error or storage service error rather than merely noting "archive failed".

### Step 2: Verify Permissions and Storage Destination

Verify under the exact OS user running PostgreSQL:

- Does the archive directory exist and is it mounted properly?
- Does the account have read permission on source WAL and write permission at the destination?
- Does the filesystem or bucket have free space and quota?
- Are DNS, routing, proxies, TLS, and external service credentials working?
- Are there object size limits, request rate limits, or timeouts?

Test manually with a separate dummy test file—never take an active WAL segment managed by PostgreSQL to test uploading and then move or delete it.

### Step 3: Verify Idempotency on Retries

If the destination file already exists, compare checksums or bytes against the source file. If contents match identically, the archive script can treat the retry as successful. If contents differ, halt writes and investigate timeline, path, backup source, or improper archive sharing.

Never modify existing WAL files by renaming or recompressing them directly inside the archive without updating the restore command and metadata. The archive must preserve an unambiguous mapping between the segment name PostgreSQL asks for and the recoverable file content.

### Step 4: Fix and Monitor the Queue

Fix destination, permission, or script bugs; then watch `pg_stat_archiver` to confirm `last_archived_wal` advances and `.ready` counts drop. Compare archived WAL filenames against the required segment sequence. Consider the issue resolved only once archiving succeeds continuously and archived files can be read back.

If the `pg_wal` filesystem is nearly full, prioritize restoring archiving and safely expanding capacity per operational procedures. Never arbitrarily stop PostgreSQL or delete WAL, as that can prevent standbys or backups from continuing.

## 6. Detecting and Resolving Missing WAL

Missing WAL typically surfaces in logs showing a requested segment cannot be found, cannot be downloaded, or contains invalid WAL data. Causes go beyond deleted files: PostgreSQL may be searching the wrong timeline, an archive prefix may have changed, compressed files may not decompress cleanly, the base backup may not match the archive, or `restore_command` may point to the wrong repository.

### Conditions Required for PITR to Succeed

A PITR flow requires:

1. A complete and valid base backup.
2. Required WAL to bring the backup to a consistent state.
3. Every contiguous WAL segment from backup start up to the recovery target.
4. Needed timeline history files if recovering across a promotion or timeline switch.
5. A `restore_command` that downloads the exact requested file intact and returns proper exit codes.
6. A recovery target inside the time or LSN range actually covered by the backup and WAL.

An archive containing the start and end segments yet missing a segment in the middle is still unusable. PostgreSQL cannot reconstruct lost changes from subsequent segments.

### Distinguishing a Missing File from an Uncreated File

If a standby follows a primary, the next segment might not exist yet simply because the primary has not generated enough WAL to close the segment. Waiting is normal here. `archive_timeout` helps archive segments sooner when activity exists, though it cannot create WAL data that does not exist.

If PITR targets a specific timestamp, verify that timestamp falls within archived WAL coverage. If the target is later than the last available WAL, recovery cannot reach it. If earlier, you may have picked the wrong timezone, timestamp, or timeline.

### Checking WAL Naming and Continuity

WAL filenames encode timeline ID, log ID, and segment ID. Compare the exact filenames PostgreSQL requests against the archive listing, including `.history` timeline history files. Never assume two adjacent files compare solely by timestamp or trailing digits once timelines switch.

When needed, inspect archive file metadata and checksums via your archive storage tooling. For compressed files, verify clean decompression and reasonable file size. `pg_waldump` can inspect WAL contents at a low level, provided you use a version matching the PostgreSQL version and WAL format; it is not a tool to fabricate or patch missing segments.

If you find a file with the same name from another backup, never drop it in blindly. Verify cluster origin, timeline, checksums, and compatibility with the base backup being restored. Two distinct clusters can produce identical WAL filenames with completely different contents.

## 7. Timelines and History Files

PostgreSQL starts a new timeline whenever a recovery branch completes—for instance, when a standby is promoted. Timelines separate WAL history branches diverging from a common branch point.

When PITR or a standby must follow a new timeline, timeline history files may be required alongside WAL segments. A `.history` file describes the relationship between a new timeline and its parent timeline plus the branch LSN. If a history file is missing or configuration selects the wrong timeline, PostgreSQL may fail to find the right WAL branch even when plenty of segments exist in the archive.

`recovery_target_timeline` controls the target timeline. Common values are `current`, `latest`, or a specific numeric timeline ID; verify behavior and defaults in documentation for your running PostgreSQL version. For a standby expected to follow the newest branch, `latest` is typically appropriate when the topology requires it.

A common mistake is copying WAL only from the current primary while forgetting older branch history, or mixing archives from multiple clusters into one prefix without partitioning by cluster/timeline. Organize archives by cluster identifier and explicit retention rules. WAL filenames are not globally unique across clusters.

## 8. Recovery Configuration on PostgreSQL 12 and Later

Starting with PostgreSQL 12, recovery parameters live in PostgreSQL configuration (such as `postgresql.conf` or included files), while recovery startup mode is signaled by files in the data directory:

- `recovery.signal`: requests archive recovery / PITR.
- `standby.signal`: requests standby mode.

Older PostgreSQL versions used `recovery.conf`; never apply modern signal-file instructions to older servers.

Illustrative configuration for archive recovery to a point in time:

~~~conf
restore_command = '/usr/local/bin/restore-wal "%f" "%p"'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

This is illustrative only. The target time must include an explicit timezone and fall within available WAL data. Choose `recovery_target_action` based on intent:

- `pause`: pause replay at target so data can be verified.
- `promote`: automatically promote upon reaching target.
- `shutdown`: stop the server upon reaching target.

If `recovery.signal` is present and the recovery target cannot be reached due to missing WAL, changing `recovery_target_action` will not fix the data gap. You must restore the proper archive or select an earlier valid target approved by the data owner.

Before startup, verify `PGDATA` is correct, the base backup matches the intended cluster, file ownership is right, and the proper signal file is in place. Never leave conflicting old and new recovery configurations side by side.

## 9. Diagnosing Stuck Recovery

Investigate starting from the first error in the logs, not just the last line. Logs reveal whether PostgreSQL is restoring from archive, waiting for the next segment, trying streaming, paused at a target, or failing to read WAL.

### Step 1: Determine Mode and State

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_is_wal_replay_paused(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
~~~

If the instance is not in recovery, the issue may have happened post-promotion or during primary operation. If replay is paused, verify whether pausing at the target was intentional. If the standby is in recovery and LSNs do not advance, check WAL sources.

### Step 2: Read Logs and Classify Root Cause

| Symptom | Where to Investigate |
|---|---|
| Restore command returns error or file not found | Path, permissions, credentials, filename, archive store, and exit codes |
| Requested segment does not exist | WAL continuity, timeline, retention, and matching base backup |
| Decompression error or invalid WAL | Corrupted file, truncated transfer, wrong compression tool, or wrong cluster |
| Waiting for next WAL | Standby may be at the end of the archive; check streaming and primary |
| Replay paused at recovery target | Verify target and `recovery_target_action`; may be the intended state |
| PVC pending or volume attach failure | StorageClass, CSI, quota, zone, and Kubernetes events |
| Disk full or I/O error | `PGDATA`/`pg_wal` capacity, storage backend, and WAL backlog |
| WAL receiver disconnected | `primary_conninfo`, DNS, network, TLS, credentials, and replication slot |

### Step 3: Verify `restore_command` Independently

Test the script under PostgreSQL's exact OS account using a WAL file known to exist in the archive. Verify:

- The script receives the exact filename and output path.
- Output is written completely to the path PostgreSQL passes via `%p`.
- Exit code is `0` on successful download.
- Exit code is non-zero when the file does not exist or data is corrupt.
- The script does not log credentials or sensitive data.
- The downloaded file matches the stored archive's checksum and size.

Never test by overwriting files actively being recovered by PostgreSQL. Use a separate copy or isolated recovery environment.

### Step 4: Check Alternative WAL Sources

If the standby is configured with both archive and streaming, inspect `pg_stat_wal_receiver`, `primary_conninfo`, network connectivity, and primary health. On the primary, check `pg_stat_replication` and replication slots if used. A slot can retain WAL so a standby catches up; a missing slot or purged WAL can force rebuilding the standby from a new backup.

If required WAL no longer exists in the archive, on the primary, on another replica, or in an independent backup copy, no SQL command can recreate the lost WAL records. Re-evaluate backups, targets, and rebuilding the standby.

## 10. Recovering from Archive Failures or Missing Segments

The safe order of actions depends on the instance's role.

### Case A: Primary Is Healthy, `archive_command` Is Failing

1. Keep the primary running if it is stable and has disk headroom; avoid unnecessary restarts.
2. Identify `last_failed_wal` and the actual error.
3. Restore permissions, disk space, network, or credentials on the archive target.
4. Fix the archive script for safe retries and content verification on existing files.
5. Watch `pg_stat_archiver` and `.ready` counts until the queue drains.
6. Test reading back both the newest segment and older segments from the archive.
7. Verify backup policy and retention still cover retained base backups.

If an archive skipped a file because a broken script returned `0` falsely, PostgreSQL may already have marked that file done. Identify the exact missing segment, restore it from a trusted copy if available, and validate the WAL chain before considering the archive healthy.

### Case B: Standby Is Not Receiving WAL

1. Determine whether the standby is waiting on archive or streaming.
2. Check receiver status and logs for connection errors or requested segments.
3. Verify whether the primary still holds the needed WAL and whether a replication slot retains it.
4. Check whether the archive holds that segment and matching timeline history.
5. Restore connectivity or place verified valid files into the right archive via controlled procedures.
6. Confirm receive LSN and replay LSN advance and replication lag decreases.

Never delete a replication slot or WAL just to reclaim space before checking whether the standby still needs them. Dropping a slot can allow needed WAL to be purged and prevent the standby from catching up.

### Case C: PITR Stopped Due to Missing WAL

1. Record the chosen base backup, backup timestamp, and recovery target.
2. Identify the first missing segment and the timeline PostgreSQL is following.
3. Search for that segment in the primary archive, archive replicas, object version history, or off-site copies.
4. Verify the recovered file belongs to the right cluster and timeline, has the proper size, and is readable.
5. Place the file in the repository read by `restore_command` or adjust the restore script to pull from the right source.
6. Restart recovery per tested procedure; confirm PostgreSQL advances past the missing segment and reaches the target.
7. Validate business data before promoting and opening traffic.

If the missing segment cannot be recovered anywhere, choose another base backup with a complete WAL chain or an earlier recovery target within recoverable bounds. That is a data-loss decision requiring data owner and DBA approval. Never skip a segment just to "get the database started".

## 11. Pausing, Resuming, and Promoting at the Right Time

If `pg_is_wal_replay_paused()` returns `true`, check logs and the recovery target. If PostgreSQL paused upon reaching the target and operators want to continue replaying past it, run:

~~~sql
SELECT pg_wal_replay_resume();
~~~

This resumes WAL application. It can advance the database past the chosen PITR point, so use it only when continuing recovery is genuinely intended.

Once the target is reached, data is verified, and you want to turn the instance into an independent primary, promote it via the procedure supported by PostgreSQL or your operator. Use `pg_promote()` on supported versions or the operator's promote command. In operator-managed environments, trigger promotion via the operator's custom resource or API if documented; manual promotion can desynchronize operator state from database state.

Never promote a standby merely because it is waiting for WAL. First decide whether losing unshipped transactions from the primary is acceptable, confirm the old primary cannot accept writes, and verify fencing. Premature promotion can create split-brain divergent write branches.

## 12. Retention and Safe WAL Cleanup

Archive retention must be anchored to the oldest retained base backup and all PITR/standby needs. Restoring from a base backup requires contiguous WAL starting from the WAL point required by that backup through the end of the recovery window. Deleting one segment in the middle invalidates that backup's recoverability.

Before cleaning archives, verify:

- Active base backups and the starting timestamp/LSN of WAL each requires.
- Committed PITR retention windows.
- Standbys or replicas that might still need WAL.
- Relevant timeline history files.
- Whether archive copies are verified in independent storage.
- Organizational legal holds, retention rules, and deletion policies.

`pg_archivecleanup` can be helpful in standby-dedicated archive setups, though it removes WAL older than a specified cutoff file. Never run it on a shared archive repository serving multiple base backups or multiple clusters without calculating the exact safe watermark. Never manually delete files in `pg_wal` or `pg_wal/archive_status`.

Protect WAL archives from accidental deletion, overwrites, and collisions from other clusters. Partition by cluster and enforce restricted write permissions, versioning, or immutable retention where data protection requires it.

## 13. Runbook Example: Archive Failures Causing Standby Lag

Suppose the primary continues accepting writes while a standby falls further behind. The DBA notices `failed_count` rising in `pg_stat_archiver` and the filesystem holding `pg_wal` filling up.

**On the primary**, check:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;

SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_stat_replication;
~~~

Results show recent archive failures and the standby's replay LSN trailing behind sent LSN. Next, the operator inspects archive command logs and discovers expired object-storage credentials.

Resolution steps:

1. Confirm the primary still has enough headroom to keep running while fixing the error.
2. Rotate credentials through the secret manager without leaking secrets into command history.
3. Test the upload script with an independent test file.
4. Verify retries for `.ready` segments will not overwrite differing contents.
5. Watch `pg_stat_archiver` until `last_archived_time` updates and the queue shrinks.
6. Confirm the standby receiver reconnects and receive/replay LSNs advance.
7. Verify fresh backups and execute a scheduled restore drill.

If a segment was falsely marked archived while missing from object storage, locate that exact segment and recover a valid copy. Never consider the incident closed merely because newer segments start archiving again.

## 14. Runbook Example: PITR Stopping on a Missing Segment

Suppose a restore uses a base backup from early in the month targeting a timestamp mid-month. Logs show `restore_command` cannot fetch a required segment.

Resolution sequence:

1. Identify the exact WAL filename PostgreSQL requests, including timeline ID.
2. Verify the target time and timezone match recovery requirements.
3. Search for that file in the primary archive, archive replicas, object version history, and off-site copies.
4. If found, compare checksums against a trusted source, confirm matching cluster/timeline, and restore it.
5. If compressed, verify clean decompression and ensure `restore_command` writes the right target file.
6. If the file exists nowhere, locate another base backup or an earlier target whose WAL chain is intact.
7. After recovery succeeds, verify business data, database roles, extensions, and permissions before opening application traffic.

Never substitute a missing file with an arbitrary segment of matching size from an unknown source. WAL is a logically chained sequence of records; wrong data can crash recovery or leave the database in an untrustworthy state.

## 15. Common Troubleshooting Mistakes

**Deleting WAL inside `pg_wal` to free disk space.** This breaks recovery, replication, or archive retries. Fix the cause of WAL retention and expand storage per procedure.

**Treating every `restore_command` “not found” as a fatal error.** A standby may ask for a segment not yet created or while switching to streaming. Read logs alongside receiver status and LSNs.

**Assuming `kubectl get pods` showing Running means PostgreSQL is ready.** A Running pod does not guarantee the database finished replaying WAL, became primary, or is ready for traffic.

**Ignoring timeline history.** WAL files may exist yet belong to a different history branch. Verify timelines and `.history` files.

**Returning exit code 0 before upload finishes.** PostgreSQL assumes the segment is archived and will not retry as intended. Report success only after durable storage is confirmed.

**Testing restore under a different OS account than PostgreSQL.** Succeeding as an admin user does not prove the PostgreSQL process has permission to read the archive or write target files.

**Promoting a standby just to escape a wait state.** Promotion forks a new data branch and accepts losing unshipped WAL. Verify the old primary is fenced and obtain RPO approval first.

**Purging archives purely by file age.** An old file may still be required by a retained base backup. Retention must factor in backups, WAL ranges, timelines, and PITR requirements.

## 16. Operations and Recovery Checklist

- [ ] Identified whether the instance is primary, standby, PITR recovery, or crash recovery.
- [ ] Checked `pg_is_in_recovery()` and replay pause status.
- [ ] Compared receive LSN, replay LSN, and WAL receiver status.
- [ ] Read the first error in logs and recorded the requested segment/timeline.
- [ ] Checked `pg_stat_archiver`, last archive time, and latest failure.
- [ ] Checked `.ready` file count, `pg_wal` size, and archive filesystem capacity.
- [ ] Verified `archive_command`/`restore_command` under PostgreSQL's exact OS account.
- [ ] Checked WAL filenames, timeline history, checksums, and decompression.
- [ ] Verified the base backup is valid and WAL is contiguous up to target.
- [ ] Checked replication slots and streaming sources if a standby needs WAL.
- [ ] Avoided deleting WAL, archive status files, PVCs, or CRs before assessing impact.
- [ ] Resumed or promoted only after verifying the recovery target and data-loss risk.
- [ ] After recovery, verified business data, replication, backups, and alerts.

A PostgreSQL system recovers reliably when base backups, WAL archives, timeline history, and restore commands are managed as a single cohesive chain. When recovery stalls, pinpoint the exact segment and state PostgreSQL is waiting on, restore valid WAL sources, or adjust the recovery target via authorized data decisions. No promotion, restart, or file deletion can replace a missing WAL chain.
