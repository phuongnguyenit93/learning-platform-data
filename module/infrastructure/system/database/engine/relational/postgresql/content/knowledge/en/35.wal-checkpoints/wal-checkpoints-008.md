# WAL Archiving and Continuity Verification in PostgreSQL

The Write-Ahead Log (WAL) is the foundation enabling PostgreSQL to recover from crashes, support streaming replication, and restore a database to a past point in time. However, WAL residing in a server's pg_wal directory does not automatically become long-term archival storage. Old segments can be reused once PostgreSQL no longer needs them for crash recovery, replication, or archiving.

**WAL archiving** is the process of copying completed WAL segments to a separate archive repository. When combined with a valid base backup and a continuous WAL chain starting from the required point, PostgreSQL can replay changes and recover to a chosen timestamp or WAL position. This is the foundation of **Point-in-Time Recovery (PITR)**.

~~~text
PostgreSQL primary
       |
       v
   pg_wal/
       |
       | WAL segment completes
       v
   archiver process
       |
       | archive_command / archive_library
       v
  WAL archive store
       |
       +----------------------+
                              |
Base backup -----------------+
                              |
                              v
                    PostgreSQL restore
                    + restore_command
                              |
                              v
                    Continuous WAL replay
                              |
                              v
                    Recovery target (PITR)
~~~

A reliable archive system requires more than a simple file-copy command. You must ensure the archive command reports success only after the segment is completely stored, never overwrites an existing file erroneously, preserves timeline history, monitors errors and backlogs, secures the archive store, and regularly tests restores.

This lesson belongs to the **WAL and checkpoints** chapter of the *Database Engine Relational PostgreSQL* module, focusing on archive configuration, WAL segment naming, timelines, continuity checking, recovery workflows, and backup/PITR operations.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain WAL archiving and its role in PITR.
2. Distinguish active WAL in pg_wal from archived segments.
3. Describe the roles of archive_mode, archive_command, archive_library, and archive_timeout.
4. Understand when the archiver processes a segment and why a partially filled segment may not be archived right away.
5. Write an idempotent archive command that is safe when PostgreSQL retries the same segment.
6. Explain the %p and %f placeholders and shell quoting.
7. Distinguish filesystem access permissions of the PostgreSQL OS process from SQL privileges of database roles.
8. Read WAL segment filenames and understand timeline ID, log ID, and segment ID.
9. Understand timeline history files and why they must be retained in the archive.
10. Monitor the archiver using pg_stat_archiver and .ready/.done statuses.
11. Distinguish WAL archiving from streaming replication, replication slots, and wal_keep_size.
12. Inspect segments, WAL records, and backups using pg_waldump and pg_verifybackup.
13. Determine the required WAL range from backup start to recovery target.
14. Identify gaps, missing files, corrupt files, wrong timelines, and permission errors.
15. Configure restore_command for archive recovery.
16. Set up PITR using recovery signals and recovery targets.
17. Design safe retention around backup chains, timelines, and RPO/RTO requirements.
18. Build periodic archive checks and repeatable restore drills.

## 2. What Problem Does WAL Archiving Solve?

PostgreSQL writes changes to WAL before the corresponding data pages are completely written to data files. When a server crashes, PostgreSQL reads required WAL to redo operations and bring the database to a consistent state.

### 2.1. Crash Recovery

WAL inside pg_wal enables recovery after a crash on the same cluster. This mechanism does not require archiving WAL to an external store.

### 2.2. Streaming Replication

The primary sends WAL over the replication protocol to a standby. The standby receives and replays WAL to keep up with the primary. This is a live stream typically requiring a connection to the primary or replication source.

### 2.3. WAL Archiving

The archiver copies completed WAL segments to archive storage. That store can be a separate filesystem, NAS, separate volume, object storage via an appropriate tool, or a backup system.

### 2.4. Point-in-Time Recovery

PITR combines:

- A consistent base backup.
- All required WAL starting from the point the backup needs.
- Subsequent WAL through the recovery target.
- Necessary timeline history files if recovery crosses a timeline switch.

During restore, PostgreSQL loads the base backup and replays WAL in order up to the target.

### 2.5. An Archive Is Not a Full Backup

Having only a WAL archive is insufficient to rebuild a database from scratch. You need a compatible base backup plus all required WAL from that backup.

## 3. Components in the Archiving Workflow

~~~text
Backend processes
      |
      | write WAL records
      v
WAL buffers -> WAL segment files in pg_wal
      |
      | segment closed / switched
      v
Archiver process
      |
      | archive_command or archive_library
      v
Archive destination
      |
      | retains multiple segments + timeline history
      v
Backup / PITR repository
      |
      | restore_command
      v
Recovery process
      |
      | continuous replay
      v
Recovery target
~~~

### 3.1. WAL Writer

Backends create WAL records when modifying data. The WAL writer writes WAL buffers out to WAL files on a schedule/condition.

### 3.2. Checkpointer

Checkpoints write dirty buffers and establish recovery points in WAL. A checkpoint does not mean archiving a segment immediately.

### 3.3. Archiver

The archiver processes completed WAL segments, invoking the configured command or library. PostgreSQL tracks status markers to know which segments have been archived successfully.

### 3.4. Archive Destination

This is where WAL copies are kept beyond the short segment lifecycle in pg_wal. It must be independent in capacity, permissions, durability, and retention.

### 3.5. Restore Process

During archive recovery, PostgreSQL invokes restore_command to fetch each required WAL file to a target path, then reads and replays it.

## 4. Enabling WAL Archiving

Core parameters in postgresql.conf:

~~~conf
wal_level = replica
archive_mode = on
archive_command = '/usr/local/bin/archive-wal "%p" "%f"'
archive_timeout = 300
~~~

This example targets a Linux environment with a tested archive script installed. Adjust paths, permissions, and archive storage to match your real infrastructure.

### 4.1. wal_level

To support PITR and standard replication features, set wal_level to replica or logical. The minimal level does not log enough WAL information for PITR or replication.

### 4.2. archive_mode

archive_mode enables archiving. Changing this parameter requires a server restart to take effect, not just a config reload.

### 4.3. archive_command

Defines the shell command the archiver runs for each file needing archiving. The command must return exit status 0 when the file has been archived successfully and non-zero on failure.

### 4.4. archive_library

PostgreSQL versions supporting archive modules can use archive_library instead of a shell command. The module must be installed and compatible with the server. Do not configure both archive mechanisms in conflicting ways; consult docs for your running version.

### 4.5. archive_timeout

Forces PostgreSQL to switch WAL segments after a period of eligible WAL activity, reducing how long a segment waits to fill before archiving. Too small a value can create many archived segments, increasing file count and overhead.

### 4.6. Checking Active Parameters

~~~sql
SHOW wal_level;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_library;
SHOW archive_timeout;
~~~

If the server does not recognize archive_library, you may be running an older version; omit that SHOW line and check parameters available in your version.

### 4.7. Checking Configuration Source

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'archive_mode',
    'archive_command',
    'archive_library',
    'archive_timeout'
)
ORDER BY name;
~~~

pending_restart identifies parameters that require a restart before changes take effect.

## 5. archive_mode: on vs. always

### 5.1. archive_mode = off

Does not archive WAL segments via the archiver, even if archive_command has a value set.

### 5.2. archive_mode = on

Archives WAL generated during normal primary operation. In standby/recovery mode, this setting does not re-archive segments being replayed.

### 5.3. archive_mode = always

Allows the archiver to run in recovery/standby mode as well, archiving received/replayed WAL under applicable rules. Useful when building an archive stream from a standby designated as an archive source.

### 5.4. Do Not Enable always Arbitrarily

If both a primary and a standby archive to the same destination, ensure file naming/timelines and write logic never conflict. Two servers must never overwrite each other's archive files.

### 5.5. archive_mode Requires a Restart

Switching from off to on/always or vice versa requires restarting PostgreSQL. Changing archive_command can usually be applied via reload.

## 6. archive_command and Placeholders

PostgreSQL substitutes placeholders inside the command:

| Placeholder | Meaning |
| --- | --- |
| %p | Full path to the source file in pg_wal |
| %f | Filename to archive, without path |
| %% | Literal percent character |

Example:

~~~conf
archive_command = 'cp "%p" "/srv/pgarchive/%f"'
~~~

### 6.1. %p

%p is the path to the WAL segment or timeline history file to archive, as seen from the PostgreSQL server's filesystem.

### 6.2. %f

%f is the filename, such as a WAL segment or timeline history file. Use it as the basename in the archive directory.

### 6.3. Quoting

The command runs via a shell. Paths containing spaces, quotes, or special characters must be quoted properly. Never interpolate user-supplied input into the command.

### 6.4. Operating System Permissions

The command runs under the OS account of the PostgreSQL server process. The archive directory must exist and grant write permissions to that service user; the archive destination must be mounted and accessible from the database host or container.

### 6.5. Exit Status

Exit 0 tells PostgreSQL that archiving succeeded. If the command returns 0 before data is durably persisted, the server may mark the segment archived even though the destination file is missing or incomplete.

## 7. Designing an Idempotent Archive Command

PostgreSQL can re-invoke the archive command for the same file after a prior failure or uncertain result. Therefore, the command must be **idempotent**: re-running it must never produce a corrupt file, overwrite different contents, or report success unless the archived copy is valid.

### 7.1. Simple Copy Example

~~~conf
archive_command = 'cp "%p" "/srv/pgarchive/%f"'
~~~

This illustrates syntax, yet production must handle pre-existing files, partial copies, permissions, and durability.

### 7.2. Rules When the Destination File Already Exists

- If the destination file is identical to the source, return success.
- If the destination file differs from the source, return an error and raise an alert; never overwrite silently.
- If the destination file does not exist yet, copy to a temporary file and publish atomically when possible.
- If copying fails, preserve failure status so PostgreSQL retries.

### 7.3. Sample Script on Linux

Create an administrative script /usr/local/bin/archive-wal:

~~~bash
#!/bin/sh
set -eu

src=$1
name=$2
archive_dir=/srv/pgarchive
dest="$archive_dir/$name"
tmp="$archive_dir/.$name.tmp"

if [ -f "$dest" ]; then
    cmp -s "$src" "$dest"
    exit $?
fi

rm -f "$tmp"
cp "$src" "$tmp"
mv "$tmp" "$dest"
~~~

Then configure:

~~~conf
archive_command = '/usr/local/bin/archive-wal "%p" "%f"'
~~~

This is a basic example for a controlled local filesystem. Production must consider filesystem semantics, permissions, races across multiple archivers, durability/fsync, quotas, monitoring, and crash recovery during power loss. For object storage, use a client/tool with proper upload completion, checksums, and publish semantics.

### 7.4. Why Copy to a Temporary File?

If you copy directly to the final filename and the process gets killed mid-copy, a partial destination file can remain. On retry, seeing that filename could be misread as complete. A temp file ensures the final name appears only after copying completes.

### 7.5. Why Compare When the File Already Exists?

PostgreSQL can retry the same segment. An existing file matching the source can be treated as success; an existing file differing from the source indicates archive collision or corruption and must fail for investigation.

### 7.6. Never Manually Delete Source Files

Never delete files in pg_wal or archive status files to "force a rerun." Fix the destination or command and let PostgreSQL's archiver retry automatically.

## 8. Archive Commands and Security

### 8.1. Archive Directory Permissions

Grant write access strictly to the PostgreSQL service account or designated helper identity. Never leave the archive directory world-writable or open to all users.

### 8.2. Command Injection

WAL filenames are generated by PostgreSQL in a deterministic format, yet archive_command still executes via a shell. Never splice user-supplied paths or strings into archive_command.

### 8.3. Credentials

Never embed plaintext access keys, passwords, or cloud tokens inside postgresql.conf when safer alternatives exist. Use managed identities/credential stores with tight file permissions.

### 8.4. Encryption at Rest

WAL can contain sensitive data changes. Protect archives with encryption-at-rest, TLS in transit, access controls, auditing, and proper retention.

### 8.5. Separate Failure Domains

An archive sitting on the same disk as the data directory gives no protection against disk or host loss. Use independent storage or a backup system with separate durability and replication.

## 9. archive_timeout and Archive Timing

WAL segments are typically archived when completed. On low-write workloads, the current segment can remain unfilled for a long time.

### 9.1. Why Is archive_timeout Needed?

Under light writes, a recent base backup may exist while the newest WAL segment stays open. archive_timeout forces a periodic switch so recent WAL enters the archive sooner.

### 9.2. Choosing a Value

~~~conf
archive_timeout = 300
~~~

This configures roughly a 5-minute timeout when eligible WAL activity occurs. Smaller values ship archived segments more frequently.

### 9.3. Not a Hard RPO Guarantee

Timeout does not guarantee a segment reaches archive storage in exactly that many seconds. The archive command, network, disk, cloud APIs, and backlogs can all introduce delay.

### 9.4. The Last Segment

When testing archiving in a lab, you can call pg_switch_wal() on the primary to close the current segment and make it ready for the archiver. This is an active test/maintenance switch, not something to call continuously in applications.

### 9.5. WAL Volume and File Count

Too short a timeout generates many padded partial segments, increasing object counts, metadata operations, and object-storage lifecycle costs.

## 10. WAL Segment Naming

A WAL segment name is typically 24 hex characters:

~~~text
TTTTTTTT LLLLLLLL SSSSSSSS
   |        |        |
   |        |        +-- Segment number within WAL log
   |        +----------- WAL log number
   +-------------------- Timeline ID
~~~

Example:

~~~text
00000001000000000000000A
~~~

### 10.1. Timeline ID

The first 8 characters are the timeline ID. When a recovery promotes or a new WAL branch begins, a new timeline appears.

### 10.2. Log ID

The middle 8 characters represent the log ID portion of the WAL address.

### 10.3. Segment Number

The last 8 characters are the segment number within the log.

### 10.4. Filenames Are Not Timestamps

You cannot deduce when a segment was created by reading the hex string like a timestamp. Mapping LSNs to segments requires knowing segment size and timeline context.

### 10.5. WAL Segment Size

Common segment size is 16 MiB, though it can be chosen at initdb/build depending on version. Inspect via:

~~~sql
SHOW wal_segment_size;
~~~

Never hardcode 16 MiB in continuity scripts if a cluster uses a different segment size.

## 11. From LSN to WAL Filename

PostgreSQL provides built-in functions:

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS wal_file;
~~~

### 11.1. pg_walfile_name

Returns the WAL segment name containing the given LSN. Useful for identifying segments holding backup start/stop or recovery targets.

### 11.2. pg_walfile_name_offset

~~~sql
SELECT *
FROM pg_walfile_name_offset(pg_current_wal_lsn());
~~~

Returns the segment name and byte offset within that segment.

### 11.3. pg_current_wal_lsn

On a primary, returns the current WAL position. On a standby, use receive/replay functions matching the server's role.

### 11.4. pg_wal_lsn_diff

~~~sql
SELECT pg_wal_lsn_diff(
    '0/5000000'::pg_lsn,
    '0/3000000'::pg_lsn
) AS bytes_between;
~~~

Calculates byte distance between two LSNs. Useful for sizing the WAL range to process, though it does not replace checking actual files.

### 11.5. Choosing LSNs in Backups

Backup metadata provides start/stop LSNs and required WAL filenames. Use those values to determine which segment range must be kept rather than picking the "latest" segment arbitrarily.

## 12. Timelines and History Files

A timeline is a WAL history branch. When a standby is promoted or recovery completes onto a new branch, PostgreSQL creates a new timeline so subsequent writes belong to that branch.

### 12.1. Why Do Timelines Exist?

After recovering to a point in time and allowing new writes, the new history forks from old WAL. Timeline IDs separate branches that may share identical LSN ranges yet hold completely different contents.

### 12.2. History File

When creating a new timeline, PostgreSQL writes a history file named like:

~~~text
00000002.history
~~~

This file records the parent timeline relationship and switchpoint. Recovery needs it to follow the right WAL chain.

### 12.3. History Files Must Be Archived

Keeping WAL segments without timeline history files can prevent restores from identifying the right WAL branch. Ensure your archive mechanism saves history files handed to the archiver by PostgreSQL.

### 12.4. Never Validate Multi-Timeline Continuity by Filename Sorting Alone

You cannot verify continuity across timelines merely by lexically sorting all filenames and expecting monotonically incrementing segment numbers. You must follow timeline ancestry and switchpoints in history files.

### 12.5. target_timeline

During recovery, target_timeline = 'latest' selects the newest timeline found per recovery rules. When restoring an older branch specifically, set the exact timeline ID and ensure the matching history file is present.

## 13. Checking Archiver Status with pg_stat_archiver

System view:

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

### 13.1. archived_count

Number of successful archive completions since the last stats reset. This is a counter, not the number of files currently stored in the archive.

### 13.2. last_archived_wal

Filename of the most recently archived WAL file.

### 13.3. last_archived_time

Timestamp of the most recent successful archive.

### 13.4. failed_count

Number of failed archive attempts recorded. A rising counter signals you must check logs and command output.

### 13.5. last_failed_wal and last_failed_time

Identify the most recent failed file and timestamp in statistics.

### 13.6. stats_reset

Timestamp when counters were last reset. Always factor in reset time when calculating rates or comparing intervals.

### 13.7. No Recent Archive Does Not Always Mean Failure

If the database generates no new WAL or segments have not switched yet, last_archived_time can look old while the archiver is completely healthy. Generate WAL activity and switch a segment in a controlled test to verify.

## 14. Checking archive_status

Inside pg_wal/archive_status, PostgreSQL maintains status files for segments:

- `.ready` file: segment is ready to be archived.
- `.done` file: archiver reported successful archiving.

Example:

~~~text
pg_wal/
  archive_status/
    00000001000000000000000A.ready
    000000010000000000000009.done
~~~

### 14.1. Ready Backlog

Many persistent `.ready` files indicate the archiver cannot keep up, the command is failing repeatedly, or the archive destination is unreachable.

### 14.2. Done Does Not Prove the File Still Exists in the Archive

`.done` means PostgreSQL received a success status from the archive mechanism. If someone later deletes the file at the destination, PostgreSQL will not detect that from `.done` files.

### 14.3. Never Edit archive_status Manually

Never delete `.ready` files, rename them to `.done`, or create fake markers to force PostgreSQL to skip archiving. Fix the root cause and let the archiver manage state.

### 14.4. Use Filesystem Monitoring

Monitor `.ready` count and oldest `.ready` file age, archive size, free disk space, command errors, and lag from WAL creation to archive completion.

## 15. Testing Archiving by Creating a New Segment

In a lab environment or an approved test window, on the primary:

~~~sql
SELECT pg_switch_wal();
~~~

Then inspect:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

### 15.1. Archiving Is Asynchronous

pg_switch_wal() requests a switch; the archiver processes it afterward. An immediate query may not yet reflect the new file.

### 15.2. Verify the Destination File

Confirm the new segment name exists at the destination, matches the source segment's size, and passes checksum/byte comparisons.

### 15.3. Check Logs

If failed_count increments, read PostgreSQL server logs and archive script output. Do not rely on a single SQL row alone.

### 15.4. Do Not Run Switch Too Frequently in Production

pg_switch_wal() forces segment boundaries. Calling it repeatedly increases WAL file churn, archive object counts, and overhead; treat it strictly as a controlled test/maintenance operation.

## 16. Distinguishing Archiving from Replication and Retention in pg_wal

These mechanisms relate to WAL yet solve different problems:

| Mechanism | Purpose | Replaces Archive Backup Chain? |
| --- | --- | --- |
| WAL archiving | Preserves segments beyond pg_wal's short lifecycle | No; it is a component of PITR |
| Streaming replication | Ships WAL to live standbys | No |
| Replication slot | Retains WAL needed by consumers | No |
| wal_keep_size | Keeps a cushion of WAL in pg_wal for standbys | No |
| archive_timeout | Forces segment switches by time | No |
| Base backup | Creates a consistent data snapshot to restore | Requires accompanying WAL |

### 16.1. Streaming Standbys Do Not Replace Archives

An online standby stays caught up with the primary, yet does not protect against replicated logical mistakes (like accidentally dropping a table) unless you have a WAL/base-backup history for PITR.

### 16.2. Replication Slots Are Not Archive Repositories

Slots retain WAL inside pg_wal when consumers lag or go offline. An abandoned slot can fill the disk. Slots do not replace an independent archive store.

### 16.3. wal_keep_size

wal_keep_size retains a minimum WAL cushion in pg_wal for replication needs. Once past that retention window, segments are recycled; never mistake it for PITR retention.

### 16.4. Archives and Standbys Can Work Together

A standby can archive received WAL when `archive_mode=always`, provided the destination avoids conflicts and keeps timeline/history intact.

## 17. Restore Command

When recovering from an archive, PostgreSQL uses restore_command to fetch needed WAL.

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
~~~

### 17.1. Placeholders

- %f: filename to fetch from the archive.
- %p: destination path where PostgreSQL wants the file placed.
- %%: literal percent character.

### 17.2. Exit Code

Return 0 when the file is retrieved successfully; return non-zero if the file does not exist or retrieval fails per command semantics. PostgreSQL may then check the next WAL source or finish recovery per recovery logic.

### 17.3. Never Return Success with an Empty File

If the command creates an empty destination file and returns 0, PostgreSQL will try reading it and recovery may fail. Report success only when the valid file was fetched completely.

### 17.4. Timeline History Files

restore_command must also retrieve `.history` files when recovery asks for them. Ensure the archive contains them and the command fetches them by filename.

### 17.5. Paths on the Restore Host

restore_command executes in the OS environment of the restoring server. Archive paths must be mounted and accessible from that restore host/container, not paths from a backup operator's workstation.

## 18. Base Backups and Required WAL

A PITR chain starts with a base backup. WAL must span from the point the backup needs to reach consistency all the way to the target.

### 18.1. Base Backup with pg_basebackup

Example creating a backup directory:

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -U backup_user \
  -D /backup/base_2026_11_14 \
  -Fp \
  -X stream \
  -P
~~~

-X stream tells pg_basebackup to stream WAL concurrently during the backup so the backup has the WAL required for consistency. Exact options depend on workflow and version.

### 18.2. Backup Start and Stop

Backup metadata and backup_label record start/end markers and required WAL. Preserve all metadata files generated by the backup tool.

### 18.3. Never Infer the Start Segment from Folder Timestamps

A backup folder name does not prove which first WAL segment is required. Always use backup_label, manifest, and LSN/timeline metadata.

### 18.4. WAL Predating Backup Completion May Be Needed

WAL generated while the backup ran (before the backup command finished) is needed to bring the backup to consistency. Never archive only segments timestamped after backup completion.

### 18.5. Base Backups and Archives Must Share Cluster History

Ensure backups and WAL belong to the same PostgreSQL cluster/system identifier and compatible timeline ancestry. An identically named WAL file from another cluster is not a valid substitute.

## 19. Verifying Backups with pg_verifybackup

PostgreSQL provides pg_verifybackup to validate a backup's manifest, checksums, and required WAL within supported version capabilities.

~~~bash
pg_verifybackup /backup/base_2026_11_14
~~~

### 19.1. Manifest

Backups include a manifest listing files and checksums per backup format. The tool verifies backup files match the manifest.

### 19.2. WAL Consistency

The tool can verify WAL accompanying the backup is valid and sufficient for backup consistency where supported. This is an important check before promoting a backup into retention.

### 19.3. Does Not Prove Future Archive Continuity

pg_verifybackup verifies the backup directory and WAL within its scope. It does not prove the archive store contains every segment from that backup to a future recovery target.

### 19.4. Versions

pg_verifybackup was introduced in PostgreSQL 13. Options and expanded checks vary by version; use a binary matching the backup/server major version and read `--help` for your installed tool.

### 19.5. Pair with Restore Drills

A backup passing verification still requires real restore drills, replaying archived WAL to a target and verifying application and data post-recovery.

## 20. Inspecting WAL with pg_waldump

pg_waldump reads and displays WAL records. It is a useful diagnostic utility to verify segments parse cleanly and inspect WAL at the record level.

~~~bash
pg_waldump \
  --path=/srv/pgarchive \
  --timeline=1 \
  --start=0/3000000 \
  --end=0/5000000
~~~

This example is illustrative; replace path, timeline, and LSNs with your cluster's actual values.

### 20.1. --path

Specifies the directory containing WAL segments to read.

### 20.2. --timeline

Selects the timeline ID matching the WAL stream you want to inspect.

### 20.3. --start and --end

Bounds the LSN range to read. Use these to examine a narrow range rather than scanning an entire archive.

### 20.4. Parse Errors

If a file is truncated, malformed, missing the next segment, or from an incompatible timeline, the tool will report an error. Record the error and verify the source file.

### 20.5. pg_waldump Does Not Replace Restores

pg_waldump parses WAL records; it does not prove all data files, extensions, configurations, and recovery chains will boot cleanly. Only a restore drill validates end-to-end recoverability.

## 21. Verifying Archive Continuity

An archive containing many WAL files is not automatically a continuous chain. You must determine the **required WAL range**, timeline, and needed segments.

### 21.1. Identify the Start Point

Obtain the backup start LSN, backup_label/manifest, and timeline of the base backup.

### 21.2. Identify the End Point

Choose the recovery target by LSN, time, name, or target recorded by your backup system. Map target LSN to a WAL filename using PostgreSQL functions in an environment with matching cluster metadata.

### 21.3. Enumerate Segments in the Range

For a single timeline and segment size, segment filenames must increment consecutively in WAL address order. Generate the expected list from start segment to end segment using segment-size-aware logic; never sort filenames across multiple timelines and compare strings naively.

### 21.4. Check Actual Files

For every required segment:

- File exists in archive storage.
- File is non-empty and matches expected size.
- Checksum or byte validation matches source/manifest if tracked.
- File is readable/parseable by appropriate tools.
- Not compressed/encrypted in a form restore_command cannot reverse.

### 21.5. Timeline Ancestry

If the target lies on a newer timeline, you must retain `.history` files and segments on parent timelines up to each switchpoint, then continue on child timelines. Use history metadata to build the chain.

### 21.6. Gaps

A single missing segment inside the required WAL span can prevent recovery from advancing past that point. A missing segment outside the range needed for a given backup/target does not necessarily break that specific chain.

### 21.7. Archives Do Not Need Every Segment Since Cluster Creation

Each base backup defines an earliest required WAL start point. Retention can purge older WAL once no retained backup still depends on it and policy permits.

## 22. Computing Segment Ranges by Segment Size

PostgreSQL provides functions mapping LSNs to WAL filenames. To build a verification list, first check:

~~~sql
SHOW wal_segment_size;
~~~

Then map:

~~~sql
SELECT
    pg_walfile_name('0/3000000'::pg_lsn) AS start_file,
    pg_walfile_name('0/5000000'::pg_lsn) AS end_file;
~~~

### 22.1. Why Not Slice LSN Strings Manually?

An LSN is a 64-bit address in two hex parts; segment names also depend on timeline and WAL segment size. Simple string-slicing scripts break when log IDs or segment numbers roll over.

### 22.2. Use PostgreSQL Functions

pg_walfile_name() and pg_walfile_name_offset() safely map LSNs when executed on a matching server.

### 22.3. Generate an Expected Manifest

An archive verification tool should take:

- System identifier / cluster identity.
- Segment size.
- Timeline history.
- Backup start LSN and required WAL.
- Recovery target LSN and timeline.

From those, compute the expected segment list and diff against the object inventory.

### 22.4. Do Not Treat Every Lexical Gap as an Error

Timeline switches, history files, segments from multiple clusters, or retention boundaries can keep filenames from forming one simple sequential string block. Always compare against the specific recovery chain.

## 23. Checking File Checksums and Integrity

### 23.1. File Size

Normal WAL segments have an exact size equal to `wal_segment_size`; history files are much smaller and do not match segment size. An unexpectedly short segment file demands investigation.

### 23.2. Hashes

You can compute checksums during archiving:

~~~bash
sha256sum /srv/pgarchive/00000001000000000000000A
~~~

Store checksums in an independent manifest or object metadata store. Hashes detect tampering or corruption, provided the checksums themselves are protected and verified against a trusted source.

### 23.3. Hashes Do Not Prove Continuity

A set of files with valid checksums can still be missing an intermediate segment. Per-object integrity and chain continuity are two separate checks.

### 23.4. Object Storage Checksums

Some object storage services have checksum/ETag semantics that vary with multipart uploads and encryption. Never assume an ETag is always a plain MD5 of file contents.

### 23.5. Verify After Upload

If an archive tool reports upload success without verifying the object is complete and readable, it may acknowledge prematurely. Rely on service-guaranteed upload completion, checksum validation, and read-after-write semantics.

## 24. Archive Gaps and Common Causes

### 24.1. Archive Command Returning Errors

The copy/upload command exits non-zero, the archiver retries, and segments stay pending. Inspect pg_stat_archiver, PostgreSQL logs, and script logs.

### 24.2. Out of Space

Archive filesystem or object quota fills up; commands fail. Monitor free space, quotas, object counts, and retention.

### 24.3. Lost Mount or Network

Mount point disappears or network storage becomes unreachable. Commands may accidentally write into an unmounted local directory; verify the mount before writing.

### 24.4. Permissions

The OS account running PostgreSQL lacks write/read permissions on the archive path, or cloud credentials expired.

### 24.5. Destination File Exists with Different Contents

An archive script checks only filename existence and returns success without comparing contents; this design flaw hides corruption or collisions.

### 24.6. Segments Deleted Too Early by Retention

A retention job deletes WAL still required by a retained backup. This is a classic cause of broken PITR; always tie retention to backup chains rather than blindly deleting files older than N days.

### 24.7. Missing Timeline History

WAL segments exist while `.history` files were deleted or never archived. Recovery may fail to reconstruct the timeline branch.

### 24.8. Missing Backup Metadata

Losing the manifest, backup_label, or LSN metadata makes identifying the required WAL range difficult. Keep metadata alongside backups.

### 24.9. Wrong Cluster

WAL from a different cluster gets pushed into the same archive prefix. Namespace archives by cluster/system identifier and verify provenance.

### 24.10. No Compatible Base Backup

The archive may be complete while no usable base backup remains; PITR is still impossible.

## 25. PITR: Recovering to a Point in Time

Suppose you have a base backup in /restore/cluster and archived WAL in /srv/pgarchive. On the restore server, configure recovery:

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
~~~

Create the appropriate signal file:

~~~bash
touch /restore/cluster/recovery.signal
~~~

Then start PostgreSQL so recovery reads the base backup and replays WAL.

### 25.1. recovery.signal

In PostgreSQL 12 and later, `recovery.signal` puts the server into archive recovery mode. `standby.signal` selects standby mode.

### 25.2. Recovery Target

Targets can be chosen by:

- recovery_target_time.
- recovery_target_lsn.
- recovery_target_name.
- recovery_target_xid.

Choose the appropriate target and ensure the WAL archive covers the entire chain up to that target.

### 25.3. recovery_target_action

Options include pause, promote, or shutdown depending on version and semantics. `pause` is useful when inspecting state right at the target before deciding to promote or continue.

### 25.4. recovery_target_inclusive

Controls whether the target record itself is included for certain target types. Verify exact semantics for your version and target choice.

### 25.5. recovery_target_timeline

Selects which timeline to replay, commonly `latest` or a specific timeline ID. Do not use `latest` if your procedure requires recovering onto an older branch.

## 26. PITR by LSN or Named Restore Point

### 26.1. Recovery by LSN

~~~conf
recovery_target_lsn = '0/5A0000F0'
recovery_target_action = 'pause'
~~~

LSNs are helpful when applications or backup orchestration recorded an exact WAL milestone.

### 26.2. Creating a Named Restore Point

On the primary, before a risky operation:

~~~sql
SELECT pg_create_restore_point('before_customer_migration');
~~~

PostgreSQL writes a named restore point into WAL. Record the returned LSN along with timestamp and deployment metadata.

### 26.3. Recovery by Name

~~~conf
recovery_target_name = 'before_customer_migration'
recovery_target_action = 'pause'
~~~

### 26.4. Restore Points Are Not Backups

A named restore point is merely a marker in WAL. You still need a base backup and continuous WAL to replay up to it.

### 26.5. Avoid Name Collisions

Use meaningful restore point names with timestamps or versions if needed, and log them in deployment/change records.

## 27. Timeline History and the Restore Chain

Suppose a primary runs on timeline 1, and a standby is promoted to timeline 2:

~~~text
Timeline 1:
  WAL ... A -- B -- C -- D
                     |
                     +---- promotion point
                              |
Timeline 2:                   +-- E -- F -- G

History file: 00000002.history
  parent timeline = 1
  switchpoint = WAL position at branch
~~~

### 27.1. Parent Segments

Recovery needs timeline 1 up to the switchpoint.

### 27.2. Child Segments

After the switchpoint, recovery continues along timeline 2.

### 27.3. History File

00000002.history records where timeline 2 branched from. Keep this file in the archive.

### 27.4. Multiple Promotions

A system can reach timeline 3, 4, and beyond. A recovery target on a newer branch requires the full history chain from the original timeline to the target timeline.

### 27.5. Never Delete Parent Timeline WAL Based Simply on File Age

An older backup or a target on another branch may still need parent timeline segments. Retention must respect ancestry and backup dependencies.

## 28. Archive Retention and Backup Lifecycle

You cannot define retention simply as "delete WAL older than 7 days" if a retained base backup requires WAL from before that cutoff.

### 28.1. Dependencies

Every base backup has a minimum span of required WAL. As long as that backup is kept, all segments in its chain must be kept per policy.

### 28.2. Backup-Driven Retention

A backup manager must track which backups remain valid, which have expired, and which WAL segments belong to retained backups.

### 28.3. pg_archivecleanup

PostgreSQL provides pg_archivecleanup to delete archived WAL older than a chosen WAL file boundary, commonly used in standby/archive cleanup workflows.

~~~bash
pg_archivecleanup /srv/pgarchive 000000010000000000000020
~~~

This illustrates syntax only; never run it directly without verifying retention boundaries and dependencies.

### 28.4. Do Not Use pg_archivecleanup as a General Retention Manager

This tool does not understand your full base backup inventory, PITR windows, object locks, multiple timelines, or compliance holds. Use dependency-aware orchestration.

### 28.5. WAL-G, pgBackRest, and Dedicated Backup Tools

Dedicated backup tools manage base backups, WAL archives, retention, and verification as a cohesive repository. Choose a tool with explicit dependency policies rather than writing the entire lifecycle from scratch when high reliability is required.

### 28.6. Object Lifecycle Rules

Object storage lifecycle rules must never expire WAL still required by backups. Synchronize retention rules between your backup manager and object storage policies.

## 29. RPO, RTO, and Archive Lag

### 29.1. RPO

Recovery Point Objective is the maximum data loss an organization tolerates over time. When relying solely on WAL archiving, RPO depends on the delay from WAL creation until the segment is durably stored and recoverable.

### 29.2. RTO

Recovery Time Objective is the target time to restore service. RTO depends on base backup size, restore speed, volume of WAL to replay, I/O, and post-recovery validation.

### 29.3. Archive Lag

The gap between current WAL and the latest successfully archived WAL. Measure by LSN/segment and timeline, not solely by timestamps.

### 29.4. Creating Many Archive Objects

Small segments or short timeouts increase object count and listing/retrieval overhead. Better RPO is never free.

### 29.5. Replay Time

A chain spanning many hours or days can take substantial time to replay. Taking base backups more often lowers RTO at the cost of extra backup overhead.

## 30. Monitoring and Alerting

A baseline monitoring suite should collect:

| Metric | Purpose |
| --- | --- |
| archived_count | Successful archive completions since reset |
| failed_count | Failed archive attempts |
| last_archived_wal/time | Latest archive progress |
| last_failed_wal/time | Most recent failure |
| .ready file count | Pending backlog |
| Oldest .ready file age | Processing latency |
| Archive storage free/quota | Exhaustion risk |
| WAL bytes generated | WAL production rate |
| Archive bytes uploaded | Archive throughput |
| Segment gap checker | Chain continuity |
| Backup verify status | Backup usability |
| Restore drill status/time | Actual recoverability |

### 30.1. Alert on failed_count Delta

Track increases in `failed_count` between scrapes; because it is a cumulative counter, compute deltas and account for stats resets.

### 30.2. Alert on Archive Age

If the workload has WAL activity yet `last_archived_time` grows stale, alert. Avoid false alarms when an idle database produces no changes.

### 30.3. Alert on Ready Backlog

Rising `.ready` counts or growing age of the oldest `.ready` file signals the archiver is falling behind.

### 30.4. Alert on Disk

A full archive destination causes archive failures; `pg_wal` can also swell because WAL cannot be archived/recycled or is pinned by replication slots.

### 30.5. Test Monitoring Regularly

Periodically generate a segment in a test environment, confirm it lands in the archive, and verify it can be read back.

## 31. Restore Drill Procedure

A restore drill should exercise the entire chain:

1. Select a base backup still within retention.
2. Retrieve its backup manifest/label, start LSN, timeline, and required WAL.
3. Determine the recovery target and timeline ancestry.
4. Inventory required WAL segments and `.history` files.
5. Verify object existence, size, checksums, and parseability.
6. Run pg_verifybackup on the backup where supported.
7. Spin up an isolated PostgreSQL restore instance.
8. Configure restore_command, target, and signal file.
9. Start PostgreSQL and watch recovery logs.
10. Verify PostgreSQL reaches the target or expected pause state.
11. Check schemas, row counts, transaction markers, and application data.
12. Record restore duration, WAL replay duration, errors, and outcome.
13. Tear down the test environment safely after saving the report.

### 31.1. Restore into an Isolated Environment

Never test-restore over a live production primary. Use a dedicated host/volume, isolated network, and separate port.

### 31.2. Application Verification

Seeing the database start is not enough. Run queries verifying business invariants, foreign keys, row counts, and application smoke tests.

### 31.3. Measure Real RTO

Record time spent fetching the base backup, copying/restoring files, replaying WAL, starting up, and validating the app. Use this data to tune RTO expectations.

### 31.4. Practice Failure Scenarios

Test a backup with missing WAL, a segment with a bad checksum, a missing `.history` file, and an unreachable archive command in the lab to validate alerts and runbooks.

### 31.5. Retain Evidence

Store backup ID, system identifier, timeline, target LSN/time, segment list, tool versions, logs, and test results.

## 32. Operational Procedure When Archiving Fails

When `failed_count` rises or `.ready` backlog persists:

### Step 1. Identify the Failing Segment

~~~sql
SELECT
    failed_count,
    last_failed_wal,
    last_failed_time,
    last_archived_wal,
    last_archived_time
FROM pg_stat_archiver;
~~~

### Step 2. Read Logs

Look for command exit status, permission denied, out of space, mount/network errors, expired credentials, or checksum mismatches.

### Step 3. Check Destination

Verify the archive directory, mount, or object bucket is correct, has free space, and is writable/readable.

### Step 4. Test the Script

Test the script with a safe test file in an isolated path, verifying exit code and destination contents. Never copy or delete live production WAL files to test.

### Step 5. Remediate

Fix permissions, mounts, credentials, quotas, or the command; reload config if `archive_command` changed.

### Step 6. Let the Archiver Retry

PostgreSQL will retry unarchived files automatically. Watch `.ready` counts, `failed_count`, and `last_archived_wal`.

### Step 7. Verify Continuity

Once the backlog drains, verify every segment across the needed range exists at the destination, not just the newest segment.

### Step 8. Assess pg_wal Pressure

If archiving stayed broken for long, WAL could not be recycled and `pg_wal` disk usage grew. Monitor disk and replication slots; never delete WAL via OS commands.

## 33. Changing and Reloading archive_command

After updating archive_command:

~~~sql
SELECT pg_reload_conf();
~~~

Verify:

~~~sql
SELECT name, setting, source, pending_restart
FROM pg_settings
WHERE name IN ('archive_command', 'archive_timeout', 'archive_mode');
~~~

### 33.1. archive_command

Usually takes effect after reload.

### 33.2. archive_mode

Requires restart; `pg_reload_conf()` will not turn archiving on if the server started with `archive_mode` off.

### 33.3. archive_timeout

Can be changed via reload depending on parameter/version behavior.

### 33.4. Check Server Logs

If the new command has bad quoting or paths, PostgreSQL logs will record the error. Never assume `pg_reload_conf()` returning true means every parameter took effect cleanly.

## 34. WAL Archiving and Cloud / Object Storage

When archiving to object storage, the command must upload the complete segment and return success only after the service confirms the upload succeeded.

### 34.1. Object Keys

Organize keys by cluster identity, timeline, year/month, or a stable prefix. Never change naming conventions in a way that prevents `restore_command` from locating files by `%f`.

### 34.2. Multipart Uploads

If using multipart uploads, ensure multipart completion succeeds before reporting success. An incomplete upload is not a valid archive file.

### 34.3. Checksums

Store appropriate checksums/metadata. Understand the service's checksum semantics, especially with multipart uploads and server-side encryption.

### 34.4. Retries

Upload clients must handle retries idempotently. An already-existing object must be verified to match contents.

### 34.5. Restore Latency

PITR may need to read thousands of segments. Evaluate list/get speeds, backup tool parallelism, egress, and caching.

### 34.6. Credentials

Use least-privilege IAM/service identities: write archive on primary, read archive on restore hosts; never share one admin key across all servers.

### 34.7. Immutable Retention

Object lock and versioning protect against accidental deletion or ransomware, though policies, costs, and restorability must be tested.

## 35. Compressing and Encrypting WAL Archives

### 35.1. Compression

WAL can be compressed to save storage depending on repetition and workload. The archive tool must record the compression format, and `restore_command`/tools must decompress before PostgreSQL reads the file.

### 35.2. Do Not Expect Arbitrary Extensions to Work Automatically

If archived files are compressed as `.gz`, PostgreSQL still expects the restore command to place the raw WAL file at `%p`; the command must decompress into that destination path.

Example:

~~~conf
restore_command = 'gzip -dc /srv/pgarchive/%f.gz > "%p"'
~~~

Use this only if your archive process actually stores every WAL segment gzipped under that exact naming scheme.

### 35.3. Encryption

Encrypting archives protects data at rest and in transit. Restore workflows must obtain valid keys/credentials and decrypt before PostgreSQL reads WAL.

### 35.4. Key Management

Never store the sole decryption key inside the same archive bucket without an independent backup. Losing the key means losing restorability even if every file remains intact.

### 35.5. Compression and Encryption Must Be Tested End-to-End

Test upload, checksums, download, decryption, decompression, WAL parsing, and full restore. A file that downloads cleanly yet decompresses corruptly is useless.

## 36. Verification via SQL and Shell

### 36.1. Archiver Status

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

### 36.2. Current WAL Location

~~~sql
SELECT
    pg_current_wal_lsn(),
    pg_walfile_name(pg_current_wal_lsn());
~~~

Run on primary. On standbys, use appropriate receive/replay functions.

### 36.3. Segment Size

~~~sql
SHOW wal_segment_size;
~~~

### 36.4. Switching in the Lab

~~~sql
SELECT pg_switch_wal();
~~~

### 36.5. Listing Archive Files

~~~bash
find /srv/pgarchive -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
~~~

This is a Linux example. For object storage, use the service's CLI/API inventory.

### 36.6. Checking Checksums

~~~bash
sha256sum /srv/pgarchive/00000001000000000000000A
~~~

### 36.7. Parsing WAL

~~~bash
pg_waldump --path=/srv/pgarchive --timeline=1
~~~

Restrict by LSN or time if the archive is large; verify segment naming and timeline before reading.

## 37. WAL Archives and Backup Tools

### 37.1. pg_basebackup

Creates physical base backups from a PostgreSQL server. Can stream WAL during backup with appropriate options.

### 37.2. pg_verifybackup

Verifies backup integrity against its manifest and supported WAL checks.

### 37.3. pg_waldump

Reads WAL records to diagnose segments and LSN ranges.

### 37.4. pg_archivecleanup

Cleans up archived WAL older than a boundary in certain workflows; ensure it never deletes dependencies of retained backups.

### 37.5. pgBackRest / WAL-G

Dedicated backup tools manage backup sets, WAL archives, retention, encryption, compression, and restores. Configure repositories and verify per tool and version documentation.

### 37.6. Do Not Mix Multiple Archive Managers

If two tools manage the same archive path/retention independently, one may delete or overwrite files the other still needs. Assign one clear owner for archive lifecycle.

## 38. Common Configuration Mistakes

### Mistake 1. archive_mode Still Off

`archive_command` is set, yet `archive_mode` was never enabled or the server was never restarted. Check `pg_settings.pending_restart`.

### Mistake 2. Unsuitable wal_level

Setting `wal_level` to `minimal` omits WAL needed for PITR and replication. Use `replica` or `logical` as required.

### Mistake 3. Using a Laptop Path

The archive command runs on the PostgreSQL server OS; it cannot see a developer's laptop filesystem unless mounted.

### Mistake 4. Destination Directory Does Not Exist

Commands fail repeatedly. Create the directory, mount, and set permissions before enabling archiving.

### Mistake 5. Exit Code Always 0

Script swallows copy/upload errors and returns success; PostgreSQL marks segments `.done` even though files are missing.

### Mistake 6. Unconditionally Returning Success When File Exists

The existing file may differ in content. Compare bytes/checksums before treating retries as successful.

### Mistake 7. Copying Directly to the Final Filename

A killed process can leave a half-written file behind. Use temp files + atomic publish or complete upload protocols.

### Mistake 8. Not Archiving Timeline History

Recovery across a timeline switch fails due to missing `.history` files.

### Mistake 9. Retention Purging WAL Too Early

A retained base backup loses segments needed to replay. Tie retention to dependencies.

### Mistake 10. Checking Only last_archived_wal

The newest file may archive cleanly while an intermediate segment is missing. Use a range continuity checker.

### Mistake 11. Checking Only failed_count

Zero failure increment does not prove all files in storage still exist and remain readable.

### Mistake 12. Confusing Archiving with Streaming Replication

A healthy standby does not prove the PITR archive chain is intact.

### Mistake 13. Confusing wal_keep_size with Archive Retention

`wal_keep_size` affects only WAL kept in `pg_wal` for replication; it does not build an archive repository.

### Mistake 14. Setting archive_timeout Too Low

Produces excessive partial segments and increases file/object overhead.

### Mistake 15. Never Testing Restores

Backups and archives are proven only when restored to a target and verified post-recovery.

### Mistake 16. Misreading Timeline IDs

Segments with the same log/segment numbers on different timelines hold different contents. Never swap files across timelines.

### Mistake 17. Missing System Identifier

Mixing archives from multiple clusters into one namespace risks restoring into the wrong cluster.

### Mistake 18. Checking File Size Only

A file of exact byte length can still be corrupt. Combine checksums, WAL parsing, and restore drills.

### Mistake 19. Hashes Without a Trusted Manifest

Checksums stored alongside files can be modified together with them; protect metadata/checksums independently.

### Mistake 20. Incomplete Object Uploads

Command returns success before multipart completion finishes; the object fails to read during restore.

### Mistake 21. restore_command Fails to Decompress/Decrypt

PostgreSQL receives compressed or encrypted bytes instead of raw WAL segments. The command must write raw valid WAL to `%p`.

### Mistake 22. restore_command Returns 0 When File Is Missing

Creating an empty or invalid file and returning 0 causes confusing recovery failures. Return non-zero when a file cannot be retrieved.

### Mistake 23. Using target_time Without Explicit Timezone

Recovery timestamps can be misinterpreted across timezones. Always specify explicit offsets and record the timezone.

### Mistake 24. Deleting WAL in pg_wal via OS Commands

Can destroy crash recovery/replication and break the cluster. Let PostgreSQL and WAL tools manage segments.

### Mistake 25. Placing Archives on the Same Data Disk

A disk/host failure wipes out both the database and the archive. Separate failure domains.

## 39. Practice Exercises

Exercises run against a PostgreSQL primary/standby and archive repository in a lab environment. Never modify archive settings or run restores on production just for practice.

### Exercise 1. WAL Archive

How does WAL archiving differ from crash recovery?

### Exercise 2. PITR

What are the two minimum components needed to recover a database to a point in time?

### Exercise 3. wal_level

Which `wal_level` values are typically required for PITR and streaming replication?

### Exercise 4. archive_mode

Does changing `archive_mode` require restarting PostgreSQL?

### Exercise 5. on vs. always

What is the main difference between `archive_mode=on` and `always`?

### Exercise 6. archive_command

What do `%p` and `%f` stand for?

### Exercise 7. Exit Code

Under what conditions should `archive_command` return 0?

### Exercise 8. Retries

Why must `archive_command` be idempotent?

### Exercise 9. Existing File

If the destination archive file already exists, what must be checked before returning success?

### Exercise 10. Temp File

Why should you copy/upload to a temporary file before publishing the final name?

### Exercise 11. archive_timeout

What is the purpose of `archive_timeout`?

### Exercise 12. WAL Segment Size

Write SQL to query the cluster's segment size.

### Exercise 13. WAL Filename

Write SQL to retrieve the WAL filename containing the current WAL LSN on the primary.

### Exercise 14. Segment Name

What components make up a WAL segment filename?

### Exercise 15. Timeline

What is a timeline history file used for?

### Exercise 16. pg_stat_archiver

Write a query showing success/failure counters and the most recent WAL/timestamps.

### Exercise 17. archive_status

What do `.ready` and `.done` files represent?

### Exercise 18. pg_switch_wal

Why can calling `pg_switch_wal` in a lab help verify the archiver?

### Exercise 19. Streaming

Why does a healthy streaming standby not prove the PITR archive chain is complete?

### Exercise 20. Replication Slot

Does a replication slot replace an archive repository?

### Exercise 21. restore_command

What do `%f` and `%p` mean in `restore_command`?

### Exercise 22. Base Backup

Why can a WAL archive not replace a base backup?

### Exercise 23. pg_verifybackup

What does this tool check, and what is an important limitation?

### Exercise 24. pg_waldump

What does `pg_waldump` help verify?

### Exercise 25. Continuity

List four steps to verify continuous WAL from a backup to a target.

### Exercise 26. Timeline Chain

When a target lies on timeline 2 forked from timeline 1, what must be retained?

### Exercise 27. Gap

What is the consequence of a missing segment within the required WAL range?

### Exercise 28. Checksum

Do file checksums prove the archive chain is continuous?

### Exercise 29. Retention

Why can you not simply delete all WAL older than 7 days?

### Exercise 30. pg_archivecleanup

What does this tool do, and why must it be used cautiously?

### Exercise 31. RPO

How does archive lag affect RPO?

### Exercise 32. RTO

How do base backup size and WAL replay length affect RTO?

### Exercise 33. failed_count

Write a query reading `last_failed_wal`, `failed_count`, and `last_archived_wal`.

### Exercise 34. Backlog

List two signals indicating the archiver is falling behind.

### Exercise 35. Archive Command Errors

Name four common causes of archive command failures.

### Exercise 36. Restore Signal

Which signal file does PostgreSQL 12+ use to start archive recovery?

### Exercise 37. Recovery Target

Name three types of recovery targets supported for PITR.

### Exercise 38. Restore Drill

List five key steps of a restore drill.

### Exercise 39. Archive Storage

Why should archives live in a different failure domain from the data directory?

### Exercise 40. End-to-End Design

Propose a workflow spanning base backups, WAL archiving, continuity checks, and periodic PITR testing.

## 40. Reference Solutions

### Exercises 1–2. Archiving and PITR

Crash recovery uses WAL within the live cluster lifecycle to recover after a crash. Archiving stores segments outside `pg_wal` for long-term recovery. PITR requires a valid base backup plus the required WAL chain up to the target.

### Exercises 3–5. Configuration

`wal_level=replica` or `logical` is generally required for PITR/replication. Changing `archive_mode` requires a restart. `on` archives WAL generated on a primary; `always` also archives WAL received/replayed in recovery/standby mode per its semantics.

### Exercises 6–10. Archive Command

`%p` is source path, `%f` is filename. Return 0 only once the file is completely and validly persisted. Idempotency is needed because PostgreSQL retries. If the destination file exists, compare contents/checksums. Temp + atomic publish prevents exposing partially copied files.

### Exercises 11–14. Segments

`archive_timeout` forces segment switches periodically to avoid waiting indefinitely for a segment to fill. Segment size:

~~~sql
SHOW wal_segment_size;
~~~

Current filename:

~~~sql
SELECT pg_walfile_name(pg_current_wal_lsn());
~~~

Segment names consist of timeline ID, log ID, and segment number.

### Exercise 15. Timeline

History files record which parent timeline a child timeline branched from and at what switchpoint; recovery needs them to pick the right WAL branch.

### Exercises 16–18. Monitoring

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

`.ready` means the segment is waiting to be archived; `.done` means the archive mechanism reported success. Calling `pg_switch_wal()` in a lab closes a segment so the archiver can process it, though archiving completes asynchronously.

### Exercises 19–20. Replication

A streaming standby does not retain full WAL history beyond retention and replicates logical mistakes. A replication slot holds WAL inside `pg_wal` for a consumer; it is not a PITR archive store.

### Exercises 21–24. Restore and Tools

`restore_command`: `%f` is the archive filename, `%p` is the destination path. A base backup provides the starting data-file state. `pg_verifybackup` validates the backup manifest/checksums and supported WAL; it does not prove future archive continuity. `pg_waldump` parses WAL records, helping spot damaged segments or inspect LSNs.

### Exercises 25–28. Continuity

Workflow: obtain backup start LSN/timeline; determine target LSN/timeline; build expected segment range and history ancestry; confirm all files exist with valid size/checksums; parse and test restore. For timeline 2, retain history files, timeline 1 WAL up to the switchpoint, and timeline 2 WAL from there to the target. A missing segment in the required range blocks recovery. Checksums verify per-object integrity, not gap-free continuity.

### Exercises 29–30. Retention

Retained backups may depend on WAL older than 7 days. `pg_archivecleanup` removes files prior to a boundary in fitting workflows, yet does not replace a backup manager tracking all backup and timeline dependencies.

### Exercises 31–32. RPO/RTO

Large archive lag risks losing more changes if the primary fails, increasing RPO. Large base backups and long WAL replay streams slow down restores, increasing RTO; more frequent backups reduce replay at higher backup cost.

### Exercises 33–35. Errors and Backlog

~~~sql
SELECT
    failed_count,
    last_failed_wal,
    last_failed_time,
    last_archived_wal,
    last_archived_time
FROM pg_stat_archiver;
~~~

Growing/aging `.ready` backlogs and increasing age of `last_archived_time` during WAL activity are two warning signals. Causes include permissions, disk full, mount/network failures, expired credentials, bad commands, or incomplete object uploads.

### Exercises 36–37. Recovery

PostgreSQL 12+ uses `recovery.signal` for archive recovery. Recovery targets can be time, LSN, named restore point, or transaction ID.

### Exercise 38. Restore Drill

Choose a backup; determine WAL/timeline range; verify backup and archive files; restore to an isolated host using `restore_command`/target; validate PostgreSQL and business data; record RTO and outcomes.

### Exercises 39–40. Design

Archiving to an independent failure domain protects against losing the database host or disk. A complete workflow schedules base backups, archives WAL continuously with an idempotent command, monitors backlogs/failures/disk, checks continuity against backup dependencies and timelines, enforces dependency-aware retention, and runs regular restore drills.

## 41. Quick Reference Table

| Need | Tool / Configuration |
| --- | --- |
| Enable archiving | archive_mode = on |
| Archive WAL via command | archive_command |
| Archive via module | archive_library if supported by version |
| Force segment switch | archive_timeout |
| View WAL level | SHOW wal_level |
| View segment size | SHOW wal_segment_size |
| Map LSN to file | pg_walfile_name(lsn) |
| Map LSN and offset | pg_walfile_name_offset(lsn) |
| Switch segment in lab | pg_switch_wal() |
| Monitor archive success/failure | pg_stat_archiver |
| Inspect pending segments | pg_wal/archive_status/*.ready |
| Fetch WAL during restore | restore_command |
| Verify base backup | pg_verifybackup |
| Parse WAL records | pg_waldump |
| Clean archive by boundary | pg_archivecleanup |
| Start archive recovery | recovery.signal |
| Start standby mode | standby.signal |
| Recover to timestamp | recovery_target_time |
| Recover to LSN | recovery_target_lsn |
| Recover to restore point | recovery_target_name |
| Select timeline | recovery_target_timeline |
| Check byte range | pg_wal_lsn_diff() |

## 42. Archive and Continuity Operations Checklist

1. `wal_level` is set to `replica` or `logical` as required.
2. `archive_mode` is enabled and a restart was performed so it took effect.
3. Either `archive_command` or `archive_library` is configured cleanly—just one appropriate mechanism.
4. Archive destination sits in an independent failure domain with quota/capacity headroom.
5. PostgreSQL OS identity has least-privilege permissions required.
6. Archive command returns success only when the file is completely stored.
7. Command is idempotent and verifies any pre-existing destination file matches contents.
8. Copies/uploads use temp + atomic publish or reliable object completion semantics.
9. Command has logging/monitoring and suitable timeouts/retries.
10. `archive_timeout` balances RPO against segment/object count.
11. `pg_stat_archiver` is scraped and alerted on counter deltas.
12. `.ready` file count and age are monitored.
13. Archive destination free space, quotas, and object counts are tracked.
14. Timeline history files are archived and retained.
15. Base backups retain manifest, label, LSN, and timeline metadata.
16. Every backup has an inventory of its required WAL.
17. Continuity checker respects segment size and timeline ancestry.
18. Integrity is checked via appropriate checksums, sizes, and parsing.
19. Standalone checksums are never treated as proof of continuity.
20. `pg_verifybackup` runs on base backups where version-supported.
21. `pg_waldump` is used diagnostically on required WAL spans.
22. `restore_command` retrieves exact files and returns accurate exit codes.
23. Compression/encryption is cleanly reversed before PostgreSQL reads WAL.
24. Retention respects dependencies of every retained base backup.
25. Object lifecycle policies never purge still-needed WAL.
26. Archives are not managed by conflicting tools simultaneously.
27. RPO/RTO are measured through actual restore drills.
28. Restore drills run in isolated environments.
29. Application data is validated post-recovery, not just server startup.
30. Runbooks for gaps, corruption, archiver failures, and disk pressure stay current.

## 43. Summary

WAL archiving preserves completed segments beyond the short lifecycle of `pg_wal` to enable PITR. A typical configuration uses `wal_level=replica`, `archive_mode=on`, a tested `archive_command` or archive library, and a fitting `archive_timeout`. Archive commands must be idempotent, return success only once data is completely stored, and safely handle pre-existing destination files.

Continuity verification starts from a **specific base backup**: identify start LSN/timeline, target LSN/timeline, generate the expected segment list, keep timeline history files, verify files exist and parse cleanly, and then test recovery. `pg_stat_archiver` shows recent progress and failures; `archive_status` shows pending vs. reported-done files; `pg_verifybackup` and `pg_waldump` inspect backups and WAL within their scopes.

No single SQL query proves an archive is complete. PITR readiness is proven only when a base backup restores across a continuous WAL chain to its target, PostgreSQL starts cleanly, and application data passes verification. Monitoring backlogs, enforcing dependency-aware retention, protecting timeline history, and practicing restore drills regularly are all essential operational practices.
