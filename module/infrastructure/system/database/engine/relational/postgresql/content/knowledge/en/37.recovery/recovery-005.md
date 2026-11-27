# Point-in-Time Recovery from Base Backup and WAL in PostgreSQL

Point-in-Time Recovery (PITR) enables PostgreSQL to recover a cluster to a specific point in time, WAL position, or transaction boundary after a base backup has been taken. This is a critical technique when rolling back to a state prior to an accidental operation, application bug, unintended data deletion, or logical data corruption incident.

PITR combines two components:

- **Base backup:** a consistent physical copy of the PostgreSQL cluster, providing the starting point for recovery.
- **WAL archive:** a continuous sequence of Write-Ahead Log segments following the required start point of the base backup, enabling replay of changes up to the recovery target.

~~~text
             Active PostgreSQL Server
                       |
             +---------+---------+
             |                   |
             v                   v
        Base backup           WAL archive
        (data files)       (continuous segments)
             |                   |
             +---------+---------+
                       |
                       v
               Restore to cluster
                       |
                       v
               recovery.signal
               restore_command
                       |
                       v
                Replay WAL records
                       |
                       v
                 Recovery target
                 (time / LSN / XID
                  / restore point)
                       |
                       v
               Pause or promote
                       |
                       v
                Recovered database
~~~

A standalone base backup only returns the database to a consistent state as of the backup window. The WAL archive advances from that state to the desired recovery point. If a segment is missing within the required WAL range, the timeline is wrong, or backup metadata is lost, PostgreSQL may fail to complete recovery to the target.

This lesson belongs to the **Recovery** chapter of the *Database Engine Relational PostgreSQL* module, focusing on the recovery chain, archive recovery configuration, target selection, timelines, PITR workflow, result verification, and running restore drills.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain PITR and distinguish it from crash recovery, standby recovery, and logical restore.
2. Describe the relationship between a base backup, WAL segments, and a recovery target.
3. Determine the WAL required to recover a specific base backup.
4. Explain why the WAL archive must be continuous from the backup's required point to the target.
5. Restore a physical base backup into a separate PostgreSQL data directory.
6. Configure `restore_command` to retrieve WAL from an archive.
7. Distinguish `recovery.signal` and `standby.signal` in PostgreSQL 12 and later.
8. Recognize `recovery.conf` in older PostgreSQL versions.
9. Choose a recovery target by time, LSN, transaction ID, or named restore point.
10. Use `recovery_target_inclusive`, `recovery_target_action`, and `recovery_target_timeline`.
11. Understand timeline history and recovering across timeline switches.
12. Diagnose missing WAL, corrupted files, wrong timezones, wrong timelines, and wrong backups.
13. Verify a base backup with `pg_verifybackup` and inspect WAL with `pg_waldump`.
14. Verify database state after recovery completes.
15. Understand how promotion creates a new timeline and affects subsequent archiving.
16. Evaluate RPO, RTO, retention, and archive lag.
17. Build repeatable restore drills and PITR runbooks.

## 2. What Problem Does PITR Solve?

PITR lets you recover data to a state prior to an event. For example:

- A migration accidentally ran `DROP TABLE` at 10:35.
- A batch job erroneously updated millions of rows at 14:20.
- An application wrote bad data during a specific time window.
- An accidental deletion committed and replicated to the standby.
- You need to stand up a copy of the database as of just before a business change.

### 2.1. Recovery Target Example

Suppose:

| Time | Event |
| --- | --- |
| 02:00 | Base backup completed |
| 09:00 | Application operating normally |
| 10:34 | Data is still valid |
| 10:35 | Migration accidentally drops a table |
| 10:40 | Incident is detected |

If the WAL archive is complete from the base backup past 10:35, you can restore the base backup and replay WAL to 10:34:59 or a safe point prior to the erroneous operation.

### 2.2. PITR Does Not Undo a Single Transaction In Place

PITR recovers an entire cluster to a historical point. It is not an undo-transaction command on a live primary. You normally need an isolated restore environment, inspect the data, and then decide how to bring recovered data back into service.

### 2.3. PITR Protects Against Logical Errors

Streaming standbys replay both WAL-valid operations and business-erroneous operations alike. PITR allows rewinding before the erroneous operation was replayed.

### 2.4. PITR Does Not Replace Backups

WAL does not contain the full database state at a given point in time. A valid base backup is required as the starting point.

### 2.5. PITR Cannot Rewind Before the Base Backup

Recovery can only replay forward from the base backup state. To recover a point prior to existing backups, you must have an older base backup and corresponding WAL.

## 3. Types of Recovery to Distinguish

| Mechanism | Goal | Primary Data Source |
| --- | --- | --- |
| Crash recovery | Return cluster to a consistent state after crash | WAL in `pg_wal` |
| Archive recovery | Replay WAL fetched from archive | Base backup + `restore_command` |
| Standby recovery | Follow primary to serve as standby | Streaming WAL, archive, or both |
| PITR | Stop replay at a historical target | Base backup + WAL chain + target |
| Logical restore | Recreate objects/data from dump | `pg_dump`/`pg_restore` or SQL |

### 3.1. Crash Recovery

After a crash, PostgreSQL automatically reads required WAL inside the data directory to redo WAL-logged changes. You do not need to create `recovery.signal` for normal crash recovery.

### 3.2. Archive Recovery

When restoring from a base backup and needing WAL outside `pg_wal`, PostgreSQL uses `restore_command` to fetch each file.

### 3.3. Standby Mode

Standby mode keeps the server in continuous recovery, normally reading WAL from the primary via streaming replication and optionally using an archive as a fallback source.

### 3.4. PITR

PITR sets a recovery target. Once PostgreSQL replays up to the target, the next action depends on `recovery_target_action`.

### 3.5. Logical Restore

Logical restore rebuilds schema/data via SQL. It does not use physical WAL replay to roll a cluster back to an LSN.

## 4. Recovery Chain Architecture

A recovery chain requires the following components:

1. An intact base backup.
2. Backup metadata, including `backup_label` and tablespace information.
3. The first WAL segment required by the base backup.
4. All subsequent WAL in exact order up to the target.
5. Timeline history files if timeline branches exist.
6. A `restore_command` capable of retrieving the files.
7. Compatible PostgreSQL version, extension binaries, and environment.

~~~text
Base backup
  |
  | backup start LSN
  v
WAL segment A
  |
  v
WAL segment B
  |
  v
WAL segment C
  |
  +---- Timeline history / branch if any
  |
  v
WAL segment D
  |
  v
Recovery target
  |
  v
Recovery ends at selected point
~~~

### 4.1. The Base Backup Defines the Starting Point

Backup metadata tells PostgreSQL where to start and which WAL is required to bring the backup to a consistent state.

### 4.2. WAL Must Be Continuous

PostgreSQL cannot skip a missing required WAL segment in the middle and continue from a newer segment. A missing segment within the required range can halt or fail recovery.

### 4.3. An Archive May Hold Multiple Clusters

If sharing a repository across multiple clusters, namespace by cluster identity and avoid mixing WAL files that share filenames yet belong to different clusters.

### 4.4. The Recovery Target Must Be Reachable

The target must lie after the base backup's consistency point and not beyond accessible WAL. If the target lies outside the available archive, recovery cannot reach that target.

### 4.5. Do Not Rely Solely on File Timestamps

WAL filenames are not timestamps. Use LSNs, timeline history, and backup metadata to determine the chain.

## 5. Preparing the Base Backup

An example of creating a physical base backup:

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backup/base_2026_11_14 \
  -F plain \
  -X stream \
  -P \
  -v
~~~

### 5.1. Plain Format

Plain format creates a directory tree resembling a PostgreSQL data directory. This format is convenient for restoring and running `pg_verifybackup`.

### 5.2. Tar Format

Tar format packages base data, WAL, and tablespaces into tar archives. Each piece must be extracted to its proper location before starting the server.

### 5.3. WAL Stream

The `-X stream` option collects required WAL while copying data files. This ensures the base backup contains the WAL needed to reach consistency even while the server continues accepting writes.

### 5.4. WAL Fetch

`-X fetch` retrieves WAL after data copying completes. The server must retain the required segments long enough until fetching finishes.

### 5.5. WAL None

`-X none` does not collect WAL with the command. Use it only if another archive/retention workflow guarantees all WAL needed for the backup is available.

### 5.6. WAL Bundled with Backup vs. WAL Archive

WAL streamed with a base backup enables that backup to recover to consistency. To perform PITR to a point after the backup finished, continuous WAL after the backup is still required.

### 5.7. Backup Metadata

Preserve `backup_label`, `tablespace_map`, `backup_manifest`, and all metadata generated by the backup tool. Do not edit these files manually.

## 6. Verifying the Base Backup Before Restore

### 6.1. Verifying the Backup Manifest

For a plain-format backup with a manifest:

~~~bash
pg_verifybackup /backup/base_2026_11_14
~~~

The tool validates backup files against the manifest and performs WAL checks supported by the version.

### 6.2. Limitations of pg_verifybackup

A passing verification does not prove the external WAL archive is continuous up to any future recovery target. Nor does it verify DNS, secrets, extension packages, or application configs on the restore host.

### 6.3. Checking Backup Metadata

~~~bash
ls -l /backup/base_2026_11_14/backup_label
ls -l /backup/base_2026_11_14/backup_manifest
~~~

Exact files depend on version and backup method. Never fabricate a fake file if one is missing.

### 6.4. Checking Tablespaces

Cross-check `tablespace_map`, symlinks inside `pg_tblspc`, and tablespace storage locations. A backup missing a tablespace may fail to start.

### 6.5. Checking Version

Physical backups are normally restored with the same PostgreSQL major version. Ensure extension binaries, shared libraries, and OS dependencies are compatible.

### 6.6. Recording the System Identifier

Match the cluster identity of the backup against the WAL archive. Never combine WAL from a different cluster even if segment names appear to match.

## 7. Determining Required WAL from the Backup

A base backup has a WAL starting point. PostgreSQL uses backup metadata to know where to begin replaying.

### 7.1. Backup Start LSN

The backup label contains information required for recovery, including checkpoint/start details per the version's format.

### 7.2. Backup Stop

When a backup finishes, PostgreSQL may require additional WAL to make the copy consistent. Retain the WAL segment range determined by the backup protocol.

### 7.3. First WAL Segment

Do not pick the first segment by looking at backup creation dates or file timestamps. Rely on LSN/backup metadata and PostgreSQL functions mapping LSN to filenames.

### 7.4. pg_walfile_name

On a primary, you can map an LSN to a segment:

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;
~~~

### 7.5. pg_walfile_name_offset

~~~sql
SELECT *
FROM pg_walfile_name_offset(pg_current_wal_lsn());
~~~

This function returns the segment filename and byte offset within the segment.

### 7.6. Segment Size

~~~sql
SHOW wal_segment_size;
~~~

The common size is 16 MiB, though it can differ by cluster/build. Do not hard-code segment size when writing your own continuity checker.

## 8. The WAL Archive Must Be Continuous

An archive repository containing thousands of files can still miss the exact single segment recovery requires.

### 8.1. Determining the Range to Retain

For each backup:

- Retrieve backup start/required WAL metadata.
- Determine the recovery target.
- Map start and target LSNs to WAL segments.
- Build the expected segment list using segment size and timeline ancestry.
- Verify every file in the archive.

### 8.2. You Do Not Need All WAL Since Cluster Initialization

Retention can prune older WAL once no retained base backup depends on them and the committed PITR window no longer needs them.

### 8.3. A Gap Outside the Required Range

A missing file outside the required range of a given backup/target does not necessarily break that chain.

### 8.4. A Gap Inside the Required Range

If PostgreSQL needs segments A, B, C and the archive is missing B, recovery cannot replay from A and jump straight to C.

### 8.5. Checking Files

For each required segment, verify:

- Exact filename matching timeline and WAL address.
- File exists.
- Valid size, normally equal to `wal_segment_size`.
- Valid checksum/byte integrity if a manifest exists.
- File is readable/parseable.
- File can be decrypted/decompressed back into raw WAL if the archive applies transforms.

### 8.6. Checksums Do Not Prove Continuity

A valid checksum confirms a single file's contents match a trusted checksum. It does not prove the list has no missing segments.

## 9. Timelines and Timeline History

A timeline is a branch of WAL history. When recovery promotes or a standby is promoted, PostgreSQL can create a new timeline.

### 9.1. Timeline 1 and Timeline 2

~~~text
Timeline 1:
  WAL A ---- WAL B ---- WAL C ---- WAL D
                              |
                              +-- fork point
                                     |
Timeline 2:                          +---- WAL E ---- WAL F
~~~

Timeline 2 branches off a point on timeline 1 and then maintains its own WAL history.

### 9.2. History Files

When a new timeline is created, PostgreSQL creates a file named like:

~~~text
00000002.history
~~~

The history file describes the parent timeline, switchpoint, and related metadata so recovery can reconstruct the proper branch.

### 9.3. Preserving History Files

WAL segments of a child timeline may exist, yet if the history file is lost, PostgreSQL may fail to determine the required timeline ancestry.

### 9.4. Recovering Across Branches

If the target lies on timeline 2, recovery needs timeline 1 WAL up to the fork point and timeline 2 WAL after the fork point, along with the necessary history files.

### 9.5. recovery_target_timeline

You can choose `latest` or a specific timeline ID. `latest` is convenient when following the newest branch; a specific timeline fits when recovering onto a known historical branch.

### 9.6. Do Not Sort Multi-Timeline Files to Check Continuity

Files sharing the same log/segment numbers across different timelines are not interchangeable. Build the chain using history ancestry and the target timeline.

## 10. restore_command

During archive recovery, PostgreSQL invokes `restore_command` to fetch required files from the archive.

Example with a filesystem archive:

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
~~~

### 10.1. Placeholder %f

The filename to retrieve from the archive, which may be a WAL segment or a timeline history file.

### 10.2. Placeholder %p

The destination path where PostgreSQL expects the command to write the file.

### 10.3. Placeholder %%

A literal percent sign character in the command.

### 10.4. Success Exit Code

The command returns 0 only when the file is retrieved completely and placed at the destination path.

### 10.5. File Does Not Exist

If the file does not exist in the archive, the command returns non-zero. Never create an empty file and return 0.

### 10.6. Compressed Archives

If the archive stores gzip-compressed files:

~~~conf
restore_command = 'gzip -dc /srv/pgarchive/%f.gz > "%p"'
~~~

Use this only when the archive tool actually stores segments as gzip with the matching naming convention. The command must return an error if decompression fails.

### 10.7. Encrypted Archives

If WAL is encrypted, `restore_command` must download and decrypt using a valid key before PostgreSQL reads the file. Ensure keys do not depend solely on the archive repository itself.

### 10.8. Access Permissions

`restore_command` runs under the OS identity of the PostgreSQL process on the restore host. That user needs read permission on the archive and write permission on the destination path.

### 10.9. Do Not Use Paths Local Only to a Backup Operator Machine

Paths must be accessible from the host/container running PostgreSQL restore, such as a mounted volume or an object storage client.

## 11. recovery.signal and standby.signal

Starting with PostgreSQL 12, recovery settings are placed in `postgresql.conf` or an included config file; the legacy `recovery.conf` file is no longer used.

### 11.1. recovery.signal

Create `recovery.signal` inside PGDATA to instruct the server to start archive recovery.

~~~bash
touch /restore/pgdata/recovery.signal
~~~

### 11.2. standby.signal

`standby.signal` instructs the server to start in standby mode, normally continuing to receive WAL from a primary.

### 11.3. Differences

| Signal File | Purpose |
| --- | --- |
| `recovery.signal` | Archive recovery/PITR |
| `standby.signal` | Standby mode |

### 11.4. Avoid Leaving the Wrong Signal File

If you want standalone PITR to a target, verify no unintended `standby.signal` remains. If you want to build a standby, follow standby procedures with appropriate `primary_conninfo`/slot settings.

### 11.5. PostgreSQL 11 and Earlier

Older versions use `recovery.conf` for recovery settings and `standby_mode` for standby behavior. Consult the documentation for that exact major version.

### 11.6. Do Not Create recovery.conf on PostgreSQL 12+

PostgreSQL 12 and later do not use `recovery.conf`. Creating that file does not replace `recovery.signal` and current recovery configuration parameters.

## 12. Recovery Targets

PITR can stop at one of the following target types:

| Parameter | Meaning |
| --- | --- |
| `recovery_target_time` | Timestamp target |
| `recovery_target_lsn` | WAL position |
| `recovery_target_name` | Named restore point |
| `recovery_target_xid` | Transaction ID |

Select only one primary target per recovery run. The target must be reachable from the available base backup and WAL chain.

### 12.1. Time-Based Recovery

~~~conf
recovery_target_time = '2026-11-14 10:34:59+07'
~~~

Use an explicit timezone offset to avoid confusion between local time and UTC.

### 12.2. LSN-Based Recovery

~~~conf
recovery_target_lsn = '0/5A0000F0'
~~~

LSN fits when you have recorded an exact WAL position from the application, backup metadata, or a restore point.

### 12.3. Named Restore Point Recovery

~~~conf
recovery_target_name = 'before_customer_migration'
~~~

This target must have been created earlier using `pg_create_restore_point` and be present in the WAL chain.

### 12.4. Transaction ID Recovery

~~~conf
recovery_target_xid = '1234567'
~~~

Useful once the offending transaction ID has been identified. Understand transaction IDs and commit timing in cluster context.

### 12.5. Unreachable Target

If the target precedes the base backup's consistency point or lies beyond the last accessible WAL, recovery cannot reach the requested target. Read the logs to see how far PostgreSQL replayed and why it stopped.

## 13. recovery_target_time

This parameter instructs PostgreSQL to stop when replay reaches the corresponding transaction commit timestamp.

### 13.1. Use an Explicit Timezone

~~~conf
recovery_target_time = '2026-11-14 10:34:59+07'
~~~

Never omit the timezone if backup and restore environments have different default timezones.

### 13.2. Transaction Boundaries

PostgreSQL replays transactions according to WAL/commit semantics. A transaction is never split in half to keep only part of its committed changes.

### 13.3. Targeting Prior to an Error

If a bad statement committed at 10:35:00, pick a target before that commit, such as `10:34:59+07`, then verify actual data afterward.

### 13.4. Do Not Use Incident Detection Time

Detection time can be much later than when data was corrupted. Find the commit time of the erroneous transaction or a known-safe window.

### 13.5. Time Precision

Choose precision matching timestamps/commit records. If higher precision is required, use an LSN or a previously recorded named restore point.

## 14. recovery_target_lsn

An LSN identifies a position in WAL.

### 14.1. LSN Format

LSNs are normally displayed as two hexadecimal parts, e.g., `0/5A0000F0`.

### 14.2. Getting the Current LSN

On the primary:

~~~sql
SELECT pg_current_wal_lsn();
~~~

### 14.3. Getting the Filename from an LSN

~~~sql
SELECT pg_walfile_name('0/5A0000F0'::pg_lsn);
~~~

### 14.4. Comparing LSNs

~~~sql
SELECT
    pg_wal_lsn_diff(
        '0/5A0000F0'::pg_lsn,
        '0/59000000'::pg_lsn
    ) AS bytes_between;
~~~

### 14.5. LSN Is Not a Timestamp

Do not convert LSNs into dates/times via simple arithmetic. WAL generation rate varies with workload.

### 14.6. Record LSNs Alongside Events

If you need an exact recovery milestone before deployment, capture the LSN from a restore point or release workflow and store it with the change record.

## 15. Named Restore Points

Before a critical operation, you can record a marker in WAL:

~~~sql
SELECT pg_create_restore_point('before_customer_migration');
~~~

### 15.1. Result

The function returns the LSN of the restore point. Save the LSN, name, timestamp, operator, and associated change/ticket.

### 15.2. Recovering by Name

~~~conf
recovery_target_name = 'before_customer_migration'
recovery_target_action = 'pause'
~~~

### 15.3. A Restore Point Is Not a Base Backup

A restore point is only a marker inside WAL. A base backup and continuous WAL chain from that backup to the marker are still required.

### 15.4. Unique Names

Choose meaningful names and avoid reusing ambiguous names. Including a release ID or date/time in the name helps.

### 15.5. Create Restore Points on the Primary

This function must be called on the server actively writing WAL per workflow. Do not assume running a query on a standby creates a marker on the primary.

## 16. recovery_target_xid

Recovery can stop by transaction ID:

~~~conf
recovery_target_xid = '1234567'
recovery_target_action = 'pause'
~~~

### 16.1. Identifying the Transaction

The transaction ID can come from logs, auditing, extensions, or application metadata depending on the system. A direct mapping from user action to XID is not always available.

### 16.2. Transaction Commit

XID recovery targets correspond to transaction records in WAL. Review inclusive/exclusive semantics and inspect post-recovery results.

### 16.3. XID Wraparound

Transaction IDs have a lifecycle/wraparound. Record an XID alongside timestamp, cluster, and context; never treat a bare XID number as a permanent global identifier.

### 16.4. Use Time or LSN When Clearer

If the XID was not captured reliably, `recovery_target_time` or LSN can be easier to determine and verify.

## 17. recovery_target_inclusive

This parameter determines whether the target event itself is included per recovery semantics.

~~~conf
recovery_target_inclusive = false
~~~

### 17.1. true

The typical default is `true`: the target event is included according to the target type's rules.

### 17.2. false

Stops prior to the target event according to recovery target semantics.

### 17.3. Not a Partial Transaction Rollback

Inclusive does not slice a committed transaction in half. PostgreSQL preserves transaction consistency during replay.

### 17.4. Verify Actual Target State

Especially with time targets, verify that the offending transaction was excluded from the result while valid preceding transactions remain intact.

### 17.5. Version Semantics

Read documentation for the exact PostgreSQL version and target type in use. Do not assume identical inclusive semantics across all target types without checking.

## 18. recovery_target_action

Upon reaching the target, PostgreSQL can take one of these actions:

| Value | Behavior |
| --- | --- |
| `pause` | Pause replay at target |
| `promote` | Promote server after reaching target |
| `shutdown` | Shut down server after reaching target |

Example:

~~~conf
recovery_target_action = 'pause'
~~~

### 18.1. pause

Useful when inspecting data at the target before promoting. The server does not become a writable primary until recovery is ended/promoted properly.

### 18.2. promote

The server automatically promotes once the target is reached, ending recovery and starting a new timeline branch.

### 18.3. shutdown

The server shuts down when the target is reached. Useful in inspection/automation workflows requiring a stop at the target.

### 18.4. Choosing an Action

During restore drills or logical error recovery, `pause` usually lets you verify first. Once committed to making the recovered cluster primary, promote per runbook.

### 18.5. Do Not Confuse Pause with Application Success

Pause only indicates recovery stopped at the target. You must still verify schemas, data, and business invariants before shifting traffic.

## 19. recovery_target_timeline

Selects which timeline recovery will follow:

~~~conf
recovery_target_timeline = 'latest'
~~~

### 19.1. latest

Allows PostgreSQL to follow the newest timeline identifiable from history files in the archive.

### 19.2. Specific Timeline ID

~~~conf
recovery_target_timeline = '2'
~~~

Selects a known branch, preventing accidentally following a newer timeline unrelated to the recovery goal.

### 19.3. Timeline History

When the target timeline is a child branch, PostgreSQL needs history files and parent timeline WAL up to the fork point.

### 19.4. Latest Is Not Always the Desired Branch

An archive may contain a newer branch from another failover. When recovering an incident from an older history, determine the exact timeline before restoring.

### 19.5. Do Not Mix Multiple Clusters

A timeline ID is not a global cluster identifier. Combine system identifier, backup metadata, and timeline history.

## 20. PITR on PostgreSQL 12 and Newer: Sample Configuration

Suppose:

- Plain base backup has been restored to `/restore/pgdata`.
- WAL archive is at `/srv/pgarchive`.
- Need to recover to 10:34:59 Vietnam time on 2026-11-14.

Add to server configuration:

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
recovery_target_time = '2026-11-14 10:34:59+07'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
~~~

Create the signal file:

~~~bash
touch /restore/pgdata/recovery.signal
~~~

Start the restore server:

~~~bash
pg_ctl -D /restore/pgdata start
~~~

### 20.1. Verify the Correct Data Directory

Confirm PGDATA is a dedicated restore copy, not a data directory actively serving production.

### 20.2. Verify Archive Access

Test fetching a sample file under the same OS user that PostgreSQL runs as. Ensure `restore_command` can read the file and write the destination path.

### 20.3. Verify Timezone

The target time includes the `+07` offset. This avoids depending on the restore host's default timezone.

### 20.4. Read the Logs

Monitor logs to confirm PostgreSQL locates WAL, replays continuously, and reaches the target.

### 20.5. Paused State

When the target is reached, the server pauses replay. Verify data before promoting.

## 21. Step-by-Step PITR Procedure

### Step 1. Identify the Incident

Record the time of the erroneous operation, transaction type, affected objects, and the last known-good timestamp. Use application logs, audit logs, and deployment records to pinpoint the target.

### Step 2. Select the Base Backup

Select a valid, verified base backup whose consistency point precedes the target. A base backup closer to the target reduces WAL replay, though one may not always be available.

### Step 3. Inspect Backup Metadata

Record the backup ID, server/system identifier, major version, start/stop LSN, timeline, tablespace paths, and manifest.

### Step 4. Determine the WAL Range

From backup metadata and target, construct the list of required WAL segments, including history files if timeline switches occurred.

### Step 5. Verify Archive Continuity

Confirm every required file exists, has valid size/checksums, and is readable. If a segment is missing, check for alternate copies or another backup chain.

### Step 6. Prepare the Restore Environment

Provision a separate host/VM/container and volume. Install the matching PostgreSQL major version, extension binaries, locales, and dependencies.

### Step 7. Restore the Base Backup

For plain format, place backup files into an empty PGDATA. For tar format, extract base, WAL, and tablespaces into their proper paths.

### Step 8. Restore Configuration Outside PGDATA

Prepare `postgresql.conf`, `pg_hba.conf`, SSL certificates, secrets, archive paths, and required extension settings.

### Step 9. Configure Recovery

Set `restore_command`, target time/LSN/name/XID, timeline, and action. On PostgreSQL 12+, create `recovery.signal`.

### Step 10. Start Recovery

Start PostgreSQL and monitor logs. Do not open application traffic before confirming recovery reached the target and data is valid.

### Step 11. Verify

Check database list, schemas, row counts, business markers, constraints, and representative queries.

### Step 12. Promote Once Decided

If using the recovered instance as primary, end recovery/promote per the chosen action. Record the new timeline and reconfigure archiving/replication.

### Step 13. Cut Over Services

Update applications, connection strings, DNS/proxies, and write routing. Prevent the old primary and new primary from both accepting write traffic.

### Step 14. Save Evidence

Document target, backup ID, timeline, WAL range, logs, recovery duration, validation results, and operational decisions.

## 22. Incident Example: Accidental Table Drop

Suppose table `orders` was accidentally dropped at 10:35:

~~~sql
DROP TABLE app.orders;
~~~

The command committed and the incident was discovered at 10:40.

### 22.1. Identify the Target

Locate the transaction commit time in audit/application logs. Choose a timestamp immediately before commit, e.g., `10:34:59+07`.

### 22.2. Restore Into a Separate Cluster

Do not run PITR directly on the live primary. Restore the base backup onto an isolated instance.

### 22.3. Replay Until Before DROP

~~~conf
recovery_target_time = '2026-11-14 10:34:59+07'
recovery_target_action = 'pause'
~~~

### 22.4. Verify the Table

~~~sql
SELECT to_regclass('app.orders');
SELECT count(*) FROM app.orders;
~~~

Compare the data against business records and the incident timestamp.

### 22.5. Extract Needed Data

You can export the `orders` table from the recovered cluster and import it into the current primary if only a single object needs recovery. Handle sequences, foreign keys, triggers, dependent objects, and changes created after the target.

### 22.6. Full Cluster Recovery

If you decide to adopt the entire cluster at the target, promote the recovered instance and switch applications over per failover procedures. Changes after the target will no longer exist in the new cluster.

### 22.7. Object Recovery vs. Cluster PITR

PITR recovers the whole cluster. If only one table is needed, the PITR cluster can serve as an export source to minimize disruption to other production data.

## 23. Partial Data Recovery After PITR

PITR always replays the entire cluster up to the target. Afterward, you can extract a subset of data from the recovered instance.

### 23.1. Exporting the Table

~~~bash
pg_dump -h restore-host -U app_reader \
  -d appdb -t app.orders \
  -Fc -f /tmp/orders_before_error.dump
~~~

### 23.2. Restoring the Object

~~~bash
pg_restore -h current-primary -U restore_operator \
  -d appdb --clean --if-exists \
  /tmp/orders_before_error.dump
~~~

This is an illustrative example; `--clean` can drop existing objects, so review dependencies and test on an appropriate environment first.

### 23.3. Import Into Staging First

For critical data, restore the dump into a staging database/schema, compare, and perform a controlled merge rather than overwriting directly.

### 23.4. Sequences

Sequence state is not always synchronized as expected when exporting a single table. Verify sequence ownership, current values, and data after importing.

### 23.5. Foreign Keys and Dependent Objects

A table may depend on types, functions, triggers, sequences, and foreign keys. Ensure related objects exist and are compatible.

### 23.6. Data Created After Target

When copying an older table back into the current primary, decide how to handle rows created/modified after the target. A merge may be needed instead of a full replacement.

## 24. Recovery Targets and Transaction Semantics

PITR operates on WAL and transaction commit semantics.

### 24.1. Uncommitted Transactions Are Not Recovered

Transactions uncommitted at the target are not treated as completed transactions in the recovered database.

### 24.2. Never Split a Transaction in Two

PostgreSQL guarantees transaction consistency. It cannot keep the first half of a committed transaction and discard the second half at an arbitrary point mid-transaction.

### 24.3. Target Time Is Commit Time

Recovery target time corresponds to transaction commit timestamps in WAL. The moment a statement began running or an application sent a request may differ from when the transaction committed.

### 24.4. Finding the Exact Time

Use audit logs, application logs, deployment timelines, transaction logs, and restore points if available. Never rely solely on WAL file timestamps.

### 24.5. Inclusive

`recovery_target_inclusive` governs whether the target event is included per target semantics. Inspect actual data after recovery to confirm the bad operation was excluded.

## 25. Ending Recovery and Promoting

When the recovery target is reached, PostgreSQL can pause, promote, or shut down depending on configuration.

### 25.1. Promote

If promoting, the server exits recovery and begins operating as a new primary.

### 25.2. pg_promote

In some workflows, you can promote via SQL:

~~~sql
SELECT pg_promote();
~~~

Call this only after verifying the target and explicitly deciding to make this cluster writable.

### 25.3. New Timeline

Promotion starts a new timeline so new WAL is never confused with the previous timeline's history. A history file is written describing the branch relationship.

### 25.4. Archiving After Promotion

Ensure `archive_command` works on the new primary and archives WAL/timeline history for the new branch. Check archive destinations and avoid collisions with the old primary.

### 25.5. Never Allow Two Primaries to Write Simultaneously

Before shifting traffic, fence or disable writes on the old primary. Split-brain creates two data branches that cannot be automatically merged.

### 25.6. Shifting Replication

Standbys must be reconfigured/rebuilt to follow the new timeline and new primary. Check replication slots, connection info, and WAL availability.

## 26. PITR on PostgreSQL 11 and Older

PostgreSQL 11 and earlier versions use `recovery.conf` to configure archive recovery.

Legacy example:

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
recovery_target_time = '2026-11-14 10:34:59+07'
recovery_target_action = 'pause'
~~~

### 26.1. recovery.conf

`recovery.conf` resides in the data directory and holds recovery parameters in older versions.

### 26.2. standby_mode

Older versions use `standby_mode` inside `recovery.conf` to configure standby behavior.

### 26.3. Changes in PostgreSQL 12

Starting in PostgreSQL 12, `recovery.conf` was removed; recovery parameters moved into regular configuration and use `recovery.signal`/`standby.signal`.

### 26.4. Do Not Mix Syntaxes

Read documentation for the exact major version. A `recovery.conf` file from an old cluster is not a valid PITR configuration for PostgreSQL 12+.

## 27. Monitoring Recovery Progress

### 27.1. Server Logs

Logs are the primary source showing which WAL PostgreSQL is requesting, how far replay has progressed, whether the target was reached, or whether recovery stopped due to a missing file.

### 27.2. Recovery State

~~~sql
SELECT pg_is_in_recovery();
~~~

Returns `true` while the server is in recovery/standby mode; after promotion completes recovery, it normally returns `false`.

### 27.3. Replay LSN

On a standby or recovering instance:

~~~sql
SELECT pg_last_wal_replay_lsn();
~~~

Shows the most recent WAL position replayed.

### 27.4. Receive LSN

~~~sql
SELECT pg_last_wal_receive_lsn();
~~~

Useful on a standby receiving WAL via streaming; not a substitute for archive completeness checks.

### 27.5. Replay Timestamp

~~~sql
SELECT pg_last_xact_replay_timestamp();
~~~

Reports the timestamp of the last replayed transaction per statistics. If the database has no new transactions, the timestamp may look old even when standby/recovery is healthy.

### 27.6. Pause State

On supported versions, you can check pause status using recovery pause status functions. Consult your version's docs and never confuse paused replay with a promoted server.

## 28. Using pg_waldump for WAL Diagnostics

`pg_waldump` reads WAL records and can help determine whether segments are parseable.

~~~bash
pg_waldump \
  --path=/srv/pgarchive \
  --timeline=1 \
  --start=0/3000000 \
  --end=0/5000000
~~~

### 28.1. Selecting the Timeline

Choose the timeline matching the chain under inspection.

### 28.2. Selecting the LSN Range

Bound start/end to reduce output volume and focus on the suspect range.

### 28.3. Corrupted Files

Parse errors may indicate a truncated, corrupted, wrong-version file, or missing adjacent segments. Verify the source before concluding.

### 28.4. Does Not Prove a Full Restore

`pg_waldump` does not verify data files, tablespace mappings, extension libraries, or application behavior. It is solely a WAL diagnostic tool.

## 29. pg_verifybackup and Its Limitations

~~~bash
pg_verifybackup /restore/base_backup
~~~

### 29.1. Verifying the Base Backup

Verifies backup files against the manifest and checks supported by the tool version.

### 29.2. Does Not Verify Unlimited Future WAL Archives

Do not treat a passing result as proof that all WAL from the backup to a future target time are present.

### 29.3. Does Not Replace a Restore Test

A verified backup can still fail to start if configs, tablespaces, extensions, or the restore environment are misconfigured.

### 29.4. Tar Format

`pg_verifybackup` is designed for plain-format backups; tar backups require extraction/verification workflows suitable for the version and tool.

## 30. PITR and Retention

Retention must know which WAL range each base backup depends on.

### 30.1. Retained Backups

If a base backup is still retained by policy, the WAL needed to restore that backup must remain available.

### 30.2. PITR Window

If the organization commits to recovering to any point within 14 days, retain enough base backups and WAL to cover that entire window.

### 30.3. Never Delete Solely by File Age

Deleting all WAL older than 7 days can destroy the recoverability of a 10-day-old base backup still inside retention.

### 30.4. pg_archivecleanup

`pg_archivecleanup` can prune a WAL archive relative to a boundary file in certain workflows. It does not automatically track every base backup, target time, timeline branch, or compliance policy.

### 30.5. Backup Managers

Tools such as pgBackRest or WAL-G manage backup catalogs, WAL archives, and retention dependencies. There should be a single clear owner for repository lifecycle management.

### 30.6. Object Lifecycle Rules

Cloud lifecycle rules must never delete segments still required by the backup manager. Align policies between object storage and the backup catalog.

## 31. RPO, RTO, and Recovery Duration

### 31.1. RPO

Recovery Point Objective is the maximum data loss the organization tolerates. For PITR, RPO depends on WAL archive lag, continuity, and file readability.

### 31.2. RTO

Recovery Time Objective is the target time to restore the system. RTO depends on:

- Time to fetch/copy the base backup.
- Disk/network speed.
- Volume of WAL to replay.
- Number of segments and archive retrieval latency.
- Startup and extension initialization.
- Data/application verification time.

### 31.3. Closer Base Backups

More recent base backups reduce the WAL to replay, potentially lowering RTO at the expense of higher backup storage and system load.

### 31.4. Archive Lag

High archive lag pushes the newest recoverable target further back. Monitoring that checks only `last_archived_time` must be combined with WAL activity and LSN.

### 31.5. Measure via Restore Drills

RTO should not be estimated solely from raw disk read speed. Measure the entire restore and application validation workflow on a production-like environment.

## 32. Monitoring PITR Readiness

Metrics to track:

| Metric | Meaning |
| --- | --- |
| Base backup age | Age of the latest base backup |
| Backup verify status | Backup verification outcome |
| Backup duration/size | Backup time and size |
| WAL archived count | Successful archive count |
| WAL archive failures | Archive errors |
| Last archived WAL/time | Most recent archive progress |
| Ready backlog | Segments awaiting archiving |
| Archive storage capacity | Storage usage/quota |
| WAL continuity status | Gaps in required ranges |
| Timeline history inventory | Completeness of history files |
| Restore drill age | Time since last restore drill |
| Measured RTO | Actual observed recovery time |

### 32.1. pg_stat_archiver

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

### 32.2. Archive Status

Count/age `.ready` files in `pg_wal/archive_status` to detect backlogs. Never modify these marker files manually.

### 32.3. Base Backup Inventory

Maintain a backup catalog recording backup ID, timestamp, start/stop LSN, timeline, version, manifest, and WAL dependencies.

### 32.4. Continuity Checker

Verify every retained backup up through the committed policy target windows. Do not check only the newest segment.

### 32.5. Restore Drill Alerts

Alert if too much time passes without a successful restore drill, even if backup jobs still report success.

## 33. Reasons PITR Fails

### Failure 1. No Suitable Base Backup

A WAL archive cannot substitute for data files. Pick a valid base backup with a consistency point prior to the target.

### Failure 2. Missing WAL Segment

A required segment was deleted by retention or failed archiving. Locate an alternate copy or another base backup with a valid required range.

### Failure 3. Wrong Timeline

Segments with identical log/segment numbers on different timelines are not interchangeable. Check history files and target timeline.

### Failure 4. Missing History File

Recovery cannot reconstruct the ancestry of a child timeline. Restore the history file from the archive/backup repository.

### Failure 5. Wrong System Identifier

The backup and WAL belong to different clusters. Check provenance and repository namespacing.

### Failure 6. Broken restore_command

The command has wrong paths, wrong placeholders, missing permissions, or returns improper exit codes.

### Failure 7. restore_command Reports Success on an Empty File

PostgreSQL attempts to parse an invalid file. Return 0 only after downloading a complete, valid file.

### Failure 8. Compressed or Encrypted WAL

The command fails to decompress/decrypt before handing the file to PostgreSQL.

### Failure 9. Wrong Target Timezone

Recovery stops at an unexpected point. Use explicit offsets and verify transaction commit times.

### Failure 10. Target Before Backup Consistency Point

Replay cannot go backward. An older base backup is required.

### Failure 11. Target Beyond Last Available WAL

The archive lacks WAL up to the target. Recover missing files or choose an earlier target.

### Failure 12. Major Version Mismatch

Physical backups are not a direct major-version upgrade format. Restore on the same major version or use a supported upgrade workflow.

### Failure 13. Wrong Tablespace Path

Relation files cannot be found. Restore/map tablespaces before starting.

### Failure 14. Missing Extension Library

Catalog objects exist, yet the server cannot load the required shared library. Install the matching package/version.

### Failure 15. Missing Config Outside PGDATA

The server cannot read SSL, hba, ident, or include files. Restore administrative configs/secrets from backup.

### Failure 16. Insufficient Disk Space

Restore/extraction/WAL replay requires substantial space. Verify headroom before starting.

### Failure 17. Backup Altered After Verification

Files passed verification earlier but were corrupted during copying/storage. Re-verify after transfer and use immutability/checksums.

### Failure 18. Checking Only pg_stat_archiver

A success counter does not prove every archived object still exists. Perform inventory and continuity checks.

### Failure 19. Promoting Too Early

Promoting the cluster to primary before confirming target/data can complicate returning to recovery.

### Failure 20. Split-Brain

The old primary continues accepting writes after the recovered primary is promoted. Use fencing and traffic routing so only one writer exists.

## 34. Emergency PITR Runbook

1. Pause or isolate the faulty write source if doing so does not destroy evidence.
2. Record the offending time/transaction and last known-good timestamp.
3. Identify cluster identity, PostgreSQL version, and current timeline.
4. Select a valid base backup with a consistency point before the target.
5. Verify manifest, tablespaces, and backup metadata.
6. Determine the required WAL range from backup to target.
7. Verify all WAL segments and timeline history files.
8. Provision an isolated restore host/volume.
9. Restore the base backup and configure tablespaces.
10. Restore external configs, secrets, and extension packages.
11. Configure `restore_command` and recovery target.
12. Create `recovery.signal` on PostgreSQL 12+.
13. Start the server and monitor logs.
14. Confirm recovery reached the exact target.
15. Verify schemas, data, and business invariants.
16. Decide between exporting objects vs. promoting the whole cluster.
17. If promoting, fence the old primary and establish a new timeline/replication plan.
18. Verify WAL archiving on the new primary.
19. Shift traffic in a controlled manner.
20. Record outcomes, RTO, intentional data loss, and post-incident lessons.

## 35. Periodic Restore Drills

A restore drill is a practical exercise proving backups and PITR actually work.

### 35.1. Choosing a Backup

Pick a base backup within retention, not just the newest one.

### 35.2. Choosing a Target

Pick a timestamp/LSN with available WAL archive coverage, plus a restore point if the system creates them.

### 35.3. Pre-Checks

Verify the base backup, inventory the WAL range, history files, checksums, and extension/config dependencies.

### 35.4. Isolated Restore

Provision an isolated environment, restore data files, and configure `restore_command`/recovery target.

### 35.5. Replay

Monitor logs, measure replay speed, and confirm the target is reached.

### 35.6. Application Validation

Run validation queries, smoke tests, and business invariants.

### 35.7. Timing Measurements

Record download, extraction, startup, replay, validation durations, and total RTO.

### 35.8. Preserving Evidence

Save backup ID, target, timeline, WAL range, tool versions, logs, and results.

### 35.9. Testing Failure Cases

In a lab, simulate missing segments, checksum mismatches, missing history files, and broken `restore_command` to test alerts and runbooks.

### 35.10. Updating Procedures

Refine runbooks, retention, and capacity based on drill findings.

## 36. PITR and Security

### 36.1. WAL Can Contain Sensitive Data

WAL reflects data modifications. Protect the archive like production data.

### 36.2. Encryption at Rest and in Transit

Encrypt archive storage and transfers. Manage keys separately with backup/rotation and clear access controls.

### 36.3. Immutable Backups

Object locks/versioning or immutable repositories guard against accidental deletion and ransomware, provided you test restoring under actual lock policies.

### 36.4. Least Privilege

Archive writers only need write access to the designated prefix; restore hosts only need read access. Avoid shared admin credentials.

### 36.5. Auditing

Log who created backups, who modified retention, who deleted objects, and who ran restores.

### 36.6. Separating Failure Domains

Base backups and WAL archives must be isolated from single disk/host/region failures. Maintain at least one copy in an independent failure domain per policy.

## 37. Common Misconceptions

### Mistake 1. Having a Base Backup Is Enough for PITR

A base backup is only the starting point. Continuous WAL up to the target is required.

### Mistake 2. Having Many WAL Files Means a Complete Archive

A single segment in the middle may be missing. Always check the required range.

### Mistake 3. WAL Stream in pg_basebackup Replaces Archiving Forever

Streaming with a base backup only guarantees the WAL needed for that backup, not an ongoing continuous history afterward.

### Mistake 4. A Healthy Standby Means PITR Protection

A standby will replay accidental deletions as well. Backups and WAL history are needed to rewind prior to errors.

### Mistake 5. WAL Filenames Contain Timestamps

Segment names encode timeline/log/segment IDs, not creation times.

### Mistake 6. Segments with the Same Number on Different Timelines Are Identical

Different timelines hold different WAL histories. Never substitute files based solely on log/segment numbers.

### Mistake 7. Passing Checksums Proves Continuity

Checksums verify file integrity; they do not detect missing segments without an expected inventory.

### Mistake 8. pg_verifybackup Verifies the Entire Archive

The tool checks the backup within its supported scope; it does not prove future WAL archives are complete.

### Mistake 9. recovery.signal Is the Same as standby.signal

`recovery.signal` requests archive recovery; `standby.signal` requests standby mode.

### Mistake 10. recovery.conf Works on PostgreSQL 12+

Starting in PostgreSQL 12, `recovery.conf` was removed.

### Mistake 11. Target Time Is Statement Start Time

Recovery target time is based on commit timestamps. Transaction start and commit times can differ.

### Mistake 12. PITR Can Stop Mid-Transaction

PostgreSQL maintains transaction consistency and never recovers half of a committed transaction.

### Mistake 13. Target Time Does Not Need a Timezone

Host timezones can skew targets. Always specify an explicit offset.

### Mistake 14. You Can Restore Prior to the Base Backup

WAL only replays forward. An older base backup is needed to recover to an earlier point.

### Mistake 15. promote Does Not Create a New Timeline

Promotion starts a new timeline branch to distinguish subsequent WAL.

### Mistake 16. Both Old and New Primaries Can Accept Writes Together

That creates split-brain. Fencing and traffic routing are mandatory.

### Mistake 17. pg_stat_archiver archived_count Equals Current Archive File Count

It is a success counter since stats reset, not a live repository inventory.

### Mistake 18. Deleting WAL Purely by Age in Days Is Safe

Older WAL may still be a dependency of a retained base backup.

### Mistake 19. Restored Server Starting Means Data Is Correct

You must verify business invariants, schemas, and data at the target.

### Mistake 20. PITR Is the Best Way to Fix a Single Table Directly

PITR recovers the entire cluster. Use a PITR instance as an export source for one object.

## 38. Practice Exercises

These exercises use a PostgreSQL lab and a dedicated archive repository. Never run overwriting restores on production.

### Exercise 1. PITR

What is PITR, and what problem does it solve?

### Exercise 2. Two Components

What are the two minimum components of a recovery chain?

### Exercise 3. Base Backup

Why cannot a WAL archive replace a base backup?

### Exercise 4. WAL Continuity

What happens if a required segment in the middle of the chain is missing?

### Exercise 5. Crash Recovery

How does crash recovery differ from PITR?

### Exercise 6. Logical Restore

Give a case where `pg_dump` should be used instead of PITR.

### Exercise 7. Backup Metadata

Name three files/metadata items that must be kept with a base backup.

### Exercise 8. pg_verifybackup

What does this tool check?

### Exercise 9. WAL Segment Size

Write SQL to query the WAL segment size.

### Exercise 10. LSN Filename

Write SQL to map the current WAL LSN to a filename.

### Exercise 11. restore_command

What do `%f` and `%p` mean?

### Exercise 12. Exit Codes

When should `restore_command` return non-zero?

### Exercise 13. recovery.signal

What does this file do on PostgreSQL 12+?

### Exercise 14. standby.signal

How does it differ from `recovery.signal`?

### Exercise 15. recovery.conf

Which PostgreSQL major versions still used `recovery.conf`?

### Exercise 16. recovery_target_time

Write an example target time with timezone offset `+07`.

### Exercise 17. recovery_target_lsn

When is an LSN target appropriate?

### Exercise 18. Restore Points

Write SQL to create a named restore point.

### Exercise 19. recovery_target_xid

What does targeting by XID mean?

### Exercise 20. Inclusive

What does `recovery_target_inclusive` control?

### Exercise 21. Action

Name the three values of `recovery_target_action`.

### Exercise 22. Timeline

Why are timeline history files needed?

### Exercise 23. Timeline Target

When should `recovery_target_timeline` be set to a specific ID?

### Exercise 24. PITR Before an Incident

An erroneous operation committed at 10:35. What principle guides target time selection?

### Exercise 25. Target Before Backup

Can PITR go before the base backup's consistency point?

### Exercise 26. Target After Last WAL

Under what condition is a target unreachable?

### Exercise 27. Promotion

What happens to the timeline after promotion?

### Exercise 28. Split-Brain

Why must the old primary be fenced before switching traffic?

### Exercise 29. pg_waldump

What does this tool help diagnose?

### Exercise 30. Archive Status

Which counters/filenames can `pg_stat_archiver` report?

### Exercise 31. Retention

Why should WAL not be deleted solely based on file age?

### Exercise 32. RPO

How does archive lag affect RPO?

### Exercise 33. RTO

Name four factors affecting RTO.

### Exercise 34. Partial Recovery

If only one table is needed, what can you do after PITR of a separate cluster?

### Exercise 35. Tablespaces

Why check tablespace mappings before starting a restore?

### Exercise 36. Version

Can a PostgreSQL 15 physical backup be restored directly with PostgreSQL 16?

### Exercise 37. Restore Drill

List at least five steps in a restore drill.

### Exercise 38. Integrity

Does a file checksum prove WAL continuity?

### Exercise 39. Recovery Validation

Name four types of checks after the target is reached.

### Exercise 40. Runbook

Propose a PITR workflow from error detection through service cutover.

## 39. Reference Solutions

### Exercises 1–5. Concepts

PITR recovers a cluster to a time/LSN/transaction target using a base backup and WAL. A base backup holds data files; WAL only holds change history and cannot build a database from scratch. Missing a required segment prevents recovery from replaying across the gap. Crash recovery handles crashes on the current cluster; PITR rebuilds from a backup and stops at a historical target.

### Exercises 6–8. Backups

`pg_dump` fits backing up a single table/schema or migrating logical objects. Required metadata includes `backup_label`, `backup_manifest`, and `tablespace_map` when generated. `pg_verifybackup` validates backup files against the manifest and runs version-supported WAL checks; it does not prove the archive chain to arbitrary targets.

### Exercises 9–12. WAL and restore_command

~~~sql
SHOW wal_segment_size;
~~~

~~~sql
SELECT pg_walfile_name(pg_current_wal_lsn());
~~~

`%f` is the archive filename to fetch; `%p` is the destination path. The command returns non-zero when the file does not exist or cannot be retrieved/decrypted/decompressed validly.

### Exercises 13–15. Signals and Versions

`recovery.signal` requests archive recovery; `standby.signal` requests standby mode. PostgreSQL 11 and older used `recovery.conf`; PostgreSQL 12+ uses regular config and signal files.

### Exercises 16–20. Targets

~~~conf
recovery_target_time = '2026-11-14 10:34:59+07'
~~~

LSN fits when an exact WAL position is needed. Named restore point:

~~~sql
SELECT pg_create_restore_point('before_migration');
~~~

XID targets stop by transaction ID. `recovery_target_inclusive` determines whether the target event is included per target semantics.

### Exercises 21–23. Actions and Timelines

Actions include `pause`, `promote`, and `shutdown`. Timeline history files record branch relationships and switchpoints. Pick a specific timeline ID when recovering a known historical branch rather than following `latest`.

### Exercises 24–26. Selecting Targets

Pick a point just prior to the offending transaction's commit, use an explicit timezone, and verify post-recovery. PITR cannot precede the base backup's consistency point. A target is unreachable if required WAL after the backup is missing or the target lies beyond the last accessible WAL.

### Exercises 27–28. Promotion

Promotion ends recovery and starts a new timeline. Fencing the old primary prevents two servers from accepting writes and causing split-brain.

### Exercises 29–30. Tools

`pg_waldump` reads/parses WAL records. `pg_stat_archiver` reports `archived_count`, `failed_count`, `last_archived_wal`/`time`, and `last_failed_wal`/`time`.

### Exercises 31–33. Retention and Objectives

Old WAL may still be a dependency of a retained base backup. High archive lag increases potential unrecoverable recent changes, impacting RPO. RTO is influenced by backup size, network/disk throughput, WAL replay volume, tablespace extraction, and application validation.

### Exercises 34–36. Partial Recovery and Versions

Restore a separate cluster to the target, then `pg_dump` the needed table and import it into staging/production in a controlled way. Wrong tablespace paths prevent the server from finding relation files. Physical backups do not restore directly across major versions; use the same major version or an upgrade workflow.

### Exercises 37–39. Drills and Validation

A restore drill covers selecting a backup, verifying, checking the WAL range, isolated restore, replaying to target, validating server and business data, and recording RTO. Checksums only confirm file integrity, not absence of gaps. After reaching the target, verify schemas, row counts/business markers, constraints, and application queries.

### Exercise 40. Runbook

Identify incident/target; pick backup; construct WAL/timeline range; verify files; restore to isolated host; configure `restore_command` and `recovery.signal`; replay; confirm target; validate data; decide between object export vs. promote; fence old primary; configure new archive/replication; shift traffic and save report.

## 40. Quick Reference Table

| Need | Tool/setting |
| --- | --- |
| Create physical base backup | `pg_basebackup` |
| Verify backup manifest | `pg_verifybackup` |
| Fetch WAL from archive | `restore_command` |
| Start archive recovery | `recovery.signal` |
| Start standby mode | `standby.signal` |
| Time-based recovery | `recovery_target_time` |
| LSN-based recovery | `recovery_target_lsn` |
| Restore-point recovery | `recovery_target_name` |
| Transaction-based recovery | `recovery_target_xid` |
| Include/exclude target event | `recovery_target_inclusive` |
| Select timeline | `recovery_target_timeline` |
| Action upon reaching target | `recovery_target_action` |
| Create restore point | `pg_create_restore_point()` |
| Get current LSN | `pg_current_wal_lsn()` |
| Map LSN to WAL file | `pg_walfile_name()` |
| Map LSN and offset | `pg_walfile_name_offset()` |
| Compute LSN difference | `pg_wal_lsn_diff()` |
| Check recovery status | `pg_is_in_recovery()` |
| Replay LSN | `pg_last_wal_replay_lsn()` |
| Receive LSN | `pg_last_wal_receive_lsn()` |
| Check archive stats | `pg_stat_archiver` |
| Read WAL records | `pg_waldump` |
| Check segment size | `SHOW wal_segment_size` |
| Promote server | `pg_promote()` |

## 41. PITR Readiness Checklist

1. Valid base backup exists within retention.
2. Backup includes metadata/manifest and system identifier.
3. Base backup belongs to a PostgreSQL major version compatible with the restore server.
4. `backup_label` and needed tablespace metadata are present.
5. All tablespaces are backed up and properly mapped.
6. Extension binaries and OS dependencies can be installed on the restore host.
7. First WAL segment required by the base backup is available.
8. Complete continuous WAL exists up to the recovery target.
9. Timeline history files exist for every branch traversed.
10. WAL belongs to the exact cluster identity.
11. Archive objects have valid checksums/sizes.
12. WAL files are readable/parseable and decryptable/decompressable.
13. `restore_command` works under PostgreSQL's OS identity.
14. `restore_command` returns proper exit codes when files exist/do not exist.
15. `recovery.signal` is created for PostgreSQL 12+ archive recovery.
16. No unintended `standby.signal` exists during standalone PITR.
17. Recovery target has an explicit timezone if time-based.
18. Target lies after the backup consistency point.
19. Target lies within the accessible WAL range.
20. Timeline matches the intended recovery branch.
21. `recovery_target_action` fits the validation step.
22. Restore runs on a separate host/volume.
23. Disk space suffices for data, tablespaces, and WAL replay.
24. External configs, SSL, secrets, and extensions are prepared.
25. Server logs are monitored during recovery.
26. After reaching the target, schemas and business data are verified.
27. Promotion occurs only once decided to make the recovered cluster primary.
28. Old primary is fenced before shifting traffic.
29. WAL archiving and replication are configured for the new timeline.
30. Restore drills run periodically and measure actual RPO/RTO.

## 42. Summary

PITR recovers PostgreSQL by loading a **base backup** and replaying a **continuous WAL chain** up to a recovery target. The base backup supplies data files; WAL supplies change history; timeline history selects the right branch after promotion/failover. Missing a base backup, required WAL segment, or history file can prevent recovery from reaching the target.

On PostgreSQL 12 and newer, configure archive recovery via `restore_command` and recovery parameters in server configuration, then create `recovery.signal`. Choose targets by time, LSN, named restore point, or XID; carefully set inclusive, action, and timeline options. For PostgreSQL 11 and earlier, use `recovery.conf` per that version's documentation.

Once the target is reached, inspect data and business invariants before promoting. Promotion starts a new timeline; fence the old primary and reconfigure archiving/replication to avoid split-brain. When only one table is needed, use the PITR instance as an export source instead of replacing the entire cluster.

A PITR workflow is only trustworthy when base backups are verified, WAL dependencies are checked per backup, `restore_command` works, the timeline chain is complete, and end-to-end restore drills pass. Monitoring archive lag, enforcing dependency-aware retention, measuring real RPO/RTO, and drilling regularly turn backups into provable recoverability.
