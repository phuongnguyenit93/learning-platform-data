# Backing Up Archived Redo Logs and Their Relationship to Recoverability

Archived redo logs are a critical component of an Oracle Database backup and recovery strategy. When a database runs in ARCHIVELOG mode, Oracle copies filled online redo logs before switching and reusing log groups, producing archived redo logs. These files record the sequence of database changes by redo thread and sequence, enabling recovery of a datafile backup forward to a point in time after the backup was created.

A datafile backup without the required archived redo logs may only recover the database to an older SCN. Conversely, keeping archived redo logs without a suitable datafile backup is also insufficient to rebuild the database after storage loss. Recoverability depends on an unbroken chain consisting of datafile/control file backups, archived redo logs, any online redo logs still required, and protected backup metadata.

This lesson focuses on how archived redo logs are generated, backed up, retained, and used during recovery. It also explains RMAN `BACKUP ARCHIVELOG`, `BACKUP DATABASE PLUS ARCHIVELOG`, deletion policies, the Fast Recovery Area, RAC redo threads, and Data Guard.

After this lesson, you will be able to:

- Distinguish between online redo logs and archived redo logs.
- Understand ARCHIVELOG/NOARCHIVELOG modes and their impact on online backups.
- Read archived log thread, sequence, SCN, and timestamps.
- Explain why archived redo log backups determine the effective recovery window.
- Use RMAN to back up archived logs separately or alongside database backups.
- Understand DELETE INPUT, DELETE ALL INPUT, backup optimization, and archived log deletion policies.
- Monitor archived log destinations, the FRA, and the risk of archive destinations filling up.
- Identify the log sequence chain needed to recover a datafile/database to an SCN or point in time.
- Understand differences between complete recovery, incomplete recovery, and OPEN RESETLOGS.
- Handle archived logs in RAC and Data Guard environments.
- Verify backups with LIST, CROSSCHECK, VALIDATE, and restore rehearsals.
- Establish retention, offsite copies, backup protection, and recovery runbooks.

> RMAN syntax, deletion policies, and views may vary by Oracle release, CDB/PDB configuration, RAC, and Data Guard. Examples use common RMAN/SQL*Plus commands; verify against the documentation for your exact release before deploying to production.

## 1. Online redo logs and archived redo logs

### 1.1. Online redo logs

Oracle writes redo records describing database changes into the redo log buffer in the SGA. LGWR writes the redo buffer out to the online redo log files. Online redo logs are organized into groups; each group has one or more members for multiplexing to reduce the risk of log loss from a single member failure.

When a log group fills up, Oracle performs a log switch to another group. The newly filled log group becomes inactive once conditions allow and can be reused after the associated checkpoint/recovery requirements are met.

### 1.2. Archived redo logs

In ARCHIVELOG mode, before an online redo log group is reused, ARCn or the appropriate archival mechanism copies the contents of the filled redo log into an archived redo log. The archive file retains the redo records for a thread/sequence range so it can be used during media recovery.

An archived log is a saved copy of completed redo for a single online log sequence. It is not a copy of a datafile and does not contain a full database image.

### 1.3. Archived log creation flow

```text
SESSION modifies data
       |
       v
REDO LOG BUFFER
       |
       v
LGWR writes ONLINE REDO LOG
       |
       v
LOG SWITCH
       |
       v
ARCn / ARCHIVAL
       |
       v
ARCHIVED REDO LOG
       |
       +--> Back up with RMAN
       +--> Ship to standby (Data Guard)
       +--> Retain in FRA / archive destination
       |
       v
RESTORE + RECOVER datafile/database
```

### 1.4. Online redo and archived logs have distinct roles

| Component | Role |
| --- | --- |
| Online redo log | Records current redo for instance recovery and durability |
| Archived redo log | Stores closed redo sequences for media recovery, backups, and standby |
| Datafile backup | Provides the baseline data copy to restore |
| Control file / recovery catalog | Stores database, backup, and redo history metadata needed by RMAN |

An archive log cannot replace a datafile backup. Nor can an older datafile backup replace a required archive log if the recovery target lies past that backup's checkpoint.

## 2. ARCHIVELOG and NOARCHIVELOG

### 2.1. ARCHIVELOG mode

ARCHIVELOG mode allows Oracle to save archived redo logs before online redo logs are reused. This is the mode normally required for production databases because it supports:

- Online datafile/database backups via RMAN procedures.
- Media recovery to a specific SCN or point in time.
- Recovering a lost/corrupted datafile to the latest point with available redo.
- Data Guard redo transport and apply.
- Point-in-time recovery within the range of available backups and logs.

ARCHIVELOG mode does not create backups by itself. It only produces archived redo logs; the DBA must still back up and protect those files.

### 2.2. NOARCHIVELOG mode

In NOARCHIVELOG mode, online redo logs are not archived before being reused. When a log group is reused, older redo is overwritten, leaving no redo chain for media recovery from an old backup to a newer point in time.

Typically, a NOARCHIVELOG database requires cold/consistent backups taken while the database is cleanly shut down. You cannot rely on an inconsistent online datafile copy plus archived redo logs to recover as in ARCHIVELOG mode.

### 2.3. Comparison

| Capability | ARCHIVELOG | NOARCHIVELOG |
| --- | --- | --- |
| Archive online redo on log switch | Yes | No |
| Online backup via standard RMAN workflow | Yes, with required redo | Not as a standard consistent hot backup |
| Media recovery to a point after backup | Yes, if backups and redo are complete | Very limited |
| Data Guard redo transport | Supported in standard configurations | Does not meet standard standby redo protection requirements |
| Storage/archive management overhead | Higher | Lower |
| Best suited for | Production requiring recoverability | Lab/dev or regenerable data where losing changes after a cold backup is acceptable |

### 2.4. Checking log mode

In SQL*Plus:

```sql
ARCHIVE LOG LIST
```

Or:

```sql
SELECT name, log_mode, open_mode, database_role
FROM v$database;
```

`ARCHIVE LOG LIST` displays the log mode, archival destination, and current sequence from the instance perspective. `V$DATABASE` provides `LOG_MODE` and database status.

### 2.5. Switching to ARCHIVELOG

Changing log mode requires the database to be in MOUNT mode and typically an exclusive mount; perform it during a maintenance window per runbook:

```sql
SHUTDOWN IMMEDIATE
STARTUP MOUNT
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
ARCHIVE LOG LIST
```

Ensure the archive destination is configured and has sufficient space before opening the database. In RAC, follow the cluster-wide log mode change procedure and shut down/mount instances per RAC guidelines; do not run commands arbitrarily on a single instance.

### 2.6. Switching back to NOARCHIVELOG

This decision reduces recoverability. Only perform it if business requirements accept the risk, a consistent cold backup exists, and Data Guard/online backups no longer depend on it:

```sql
SHUTDOWN IMMEDIATE
STARTUP MOUNT
ALTER DATABASE NOARCHIVELOG;
ALTER DATABASE OPEN;
ARCHIVE LOG LIST
```

Never switch to NOARCHIVELOG as a temporary workaround for a full FRA. Fix the archive destination, backup jobs, and deletion policy instead.

## 3. Redo thread, sequence, and SCN

### 3.1. Sequence number

Each time a redo thread switches to another online redo log group, the sequence number increments. Archived logs are identified primarily by DBID/database, thread number, and sequence number, along with resetlogs/incarnation context.

Sequence numbers help the DBA determine log order and detect gaps in the redo stream. A sequence number alone is not enough to identify an archived log in RAC because each thread maintains its own sequence numbering.

### 3.2. Thread

Single-instance databases usually have one redo thread. In RAC, each instance typically has its own redo thread. Archived logs from all required threads must be present for consistent RAC database recovery.

Example:

| Thread | Sequence | Meaning |
| ---: | ---: | --- |
| 1 | 120 | Log sequence 120 of thread 1 |
| 2 | 95 | Log sequence 95 of thread 2 |

Do not compare sequence numbers across two threads as if they formed a single monotonically increasing series.

### 3.3. SCN

SCN (System Change Number) is Oracle's logical timestamp used to order database changes. Each archived log has `FIRST_CHANGE#` and `NEXT_CHANGE#` describing the SCN range it covers.

To recover to a target SCN, Oracle needs continuous redo from the datafile backup checkpoint up to the target. Sequence is a file unit; SCN defines the logical recovery boundaries.

### 3.4. FIRST_CHANGE# and NEXT_CHANGE#

In V$ARCHIVED_LOG:

- FIRST_CHANGE#: the first SCN of the redo contained in the archived log.
- NEXT_CHANGE#: the SCN immediately following the log's redo range per metadata.
- FIRST_TIME/NEXT_TIME: the corresponding timestamps per metadata.

Logs must cover a contiguous SCN range for each relevant thread. Do not check only min/max sequence numbers; a missing sequence in the middle still creates a recovery gap.

### 3.5. RESETLOGS and incarnations

After incomplete recovery or certain database reopen operations, `OPEN RESETLOGS` creates a new incarnation and starts a new redo branch. Archive logs from old and new incarnations may have overlapping sequence numbers; `RESETLOGS_CHANGE#`/`RESETLOGS_TIME` or RMAN incarnation metadata must be considered.

RMAN manages incarnations and backup metadata; avoid manually deleting files based only on file names or sequence numbers without checking incarnation.

## 4. Configuring archive destinations

### 4.1. LOG_ARCHIVE_DEST_n

`LOG_ARCHIVE_DEST_1`, `LOG_ARCHIVE_DEST_2`, and related parameters define where Oracle writes archived redo logs or ships redo to remote destinations. A destination can be a local filesystem, ASM disk group, or remote service depending on configuration.

Example local destination configuration:

```sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
  'LOCATION=/u02/arch VALID_FOR=(ALL_LOGFILES,ALL_ROLES)'
  SCOPE=BOTH;
```

The path is an example only. The directory or ASM destination must exist, have proper permissions, have enough space, and be managed by storage policy.

### 4.2. LOG_ARCHIVE_DEST_STATE_n

This parameter enables or disables the corresponding destination. Before changing state, understand whether the destination serves a standby, mandatory archival, or recovery requirement. Accidentally disabling a destination can break redo transport or archival.

### 4.3. LOG_ARCHIVE_FORMAT

`LOG_ARCHIVE_FORMAT` specifies the file naming pattern for archived logs in a filesystem destination using supported substitution variables. File names normally include thread, sequence, and resetlogs ID to avoid ambiguity.

When using the FRA or ASM, Oracle/RMAN manages naming and metadata through its own mechanisms. Do not manually rename archived logs managed by RMAN or Data Guard.

### 4.4. USE_DB_RECOVERY_FILE_DEST

You can designate the FRA as an archive destination:

```sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
  'LOCATION=USE_DB_RECOVERY_FILE_DEST'
  SCOPE=BOTH;
```

The FRA must be configured via `DB_RECOVERY_FILE_DEST` and `DB_RECOVERY_FILE_DEST_SIZE`. The FRA manages multiple recovery file types, not just archived redo logs.

### 4.5. Checking archive destinations

```sql
SELECT
    dest_id,
    status,
    target,
    destination,
    error,
    valid_now,
    db_unique_name
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

`V$ARCHIVE_DEST_STATUS` provides more detailed runtime status for destinations. Check `ERROR`, `STATUS`, and the relevant recovery/transport fields.

## 5. Generating and monitoring archived redo logs

### 5.1. Log switch

You can trigger a log switch:

```sql
ALTER SYSTEM SWITCH LOGFILE;
```

This requests switching to another log group; in ARCHIVELOG mode, the filled log will be archived by Oracle's archival mechanism. `SWITCH LOGFILE` does not guarantee that archiving has completed by the moment the command returns in every situation.

### 5.2. ARCHIVE LOG CURRENT

The command:

```sql
ALTER SYSTEM ARCHIVE LOG CURRENT;
```

requests archiving current redo up to the present point. This command is commonly used in backup/recovery runbooks to ensure recent redo is archived. In RAC, syntax/scope may apply across all threads depending on release; follow the proper cluster procedure.

### 5.3. Checking archived logs

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    first_time,
    next_time,
    archived,
    applied,
    deleted,
    status,
    name
FROM v$archived_log
ORDER BY thread#, sequence#, recid;
```

`V$ARCHIVED_LOG` may contain multiple rows for the same thread/sequence due to multiple destinations, copies, or registrations. Do not count rows as unique sequences.

### 5.4. Checking log history

```sql
SELECT
    thread#,
    sequence#,
    first_time,
    first_change#
FROM v$log_history
ORDER BY thread#, sequence#;
```

`V$LOG_HISTORY` contains log switch history per control file metadata; record retention duration depends on control file record management. A recovery catalog can retain history longer when synchronized.

### 5.5. Checking online redo groups

```sql
SELECT
    thread#,
    group#,
    sequence#,
    bytes,
    members,
    archived,
    status
FROM v$log
ORDER BY thread#, group#;
```

A `CURRENT` log group is not yet a completed archived log. Never delete or move online redo logs to free space in an archive destination.

## 6. RMAN and backing up archived redo logs

### 6.1. Why use RMAN?

Recovery Manager (RMAN) understands database structure, datafiles, control files, redo threads, sequences, and incarnations. RMAN records backup metadata, tracks which archived logs have been backed up, and supports restoring/recovering by SCN or time.

OS-level file copying can create an extra copy, but it does not automatically populate metadata in the RMAN repository. If copied files need to enter RMAN inventory, they must be properly cataloged and verified as valid.

### 6.2. Connecting to RMAN

Example connecting to the target database:

```text
rman target /
```

Or use a connection secured per DBA policy. Never write passwords directly into command history or scripts.

### 6.3. Backing up all archived logs

Basic command:

```sql
BACKUP ARCHIVELOG ALL;
```

RMAN backs up existing archived logs and writes backup pieces using the configured device/channels. If backups are meant for recovery, ensure all required logs have been archived and included in the backup set.

### 6.4. Backing up with format and tag

```sql
BACKUP
  ARCHIVELOG ALL
  FORMAT '/backup/rman/arch_%d_%T_%s_%p.bkp'
  TAG 'ARCHIVE_DAILY';
```

`FORMAT` shows an example disk backup path. In production, use a destination with adequate capacity, access controls, monitoring, and failure isolation from the archive source. `TAG` helps identify backups in `LIST`/`REPORT`.

### 6.5. Backing up a sequence range

Archived logs can be backed up by sequence/thread when resolving gaps or specific needs:

```sql
BACKUP ARCHIVELOG
  FROM SEQUENCE 100
  UNTIL SEQUENCE 120
  THREAD 1;
```

Verify that the sequence/thread exists and belongs to the right database and incarnation. In RAC, repeat or adjust for each required thread.

### 6.6. Backing up logs not backed up a specified number of times

Backup optimization can filter logs by backup count:

```sql
BACKUP ARCHIVELOG ALL
  NOT BACKED UP 1 TIMES;
```

The scope of "already backed up" depends on device type and RMAN configuration. Check `CONFIGURE BACKUP OPTIMIZATION`, backup history, and independent copy requirements before using this in jobs.

### 6.7. Backing up archived logs to tape/SBT

Example:

```sql
BACKUP DEVICE TYPE SBT
  ARCHIVELOG ALL
  TAG 'ARCH_TO_TAPE';
```

SBT requires the media management library, channels, and vendor tape/cloud configuration. This example command does not replace vendor configuration. Verify that backup pieces were written successfully and catalog/metadata were updated.

### 6.8. Scheduled archived log backups

A typical job includes:

1. Verify that the archive destination is active.
2. Back up newly generated archived logs.
3. Inspect RMAN output and backup pieces.
4. Confirm copies reached separate storage/FRA per policy.
5. Only then allow input deletion per the deletion policy.
6. Log the job, sequence numbers, sizes, and any errors.

Never run a scheduled archive deletion job independently of the backup job without verifying backup completion.

## 7. BACKUP DATABASE PLUS ARCHIVELOG

### 7.1. Purpose

`BACKUP DATABASE PLUS ARCHIVELOG` combines datafile backups with the archived redo logs needed to recover an online backup. This is the standard pattern for databases in ARCHIVELOG mode.

Example:

```sql
BACKUP DATABASE PLUS ARCHIVELOG;
```

RMAN coordinates archiving the current log and backing up archived logs around the database backup so the redo needed to recover the online backup is captured. Exact behavior may vary by configuration/channels/devices.

### 7.2. Why are archive logs needed around backup time?

An online backup reads different datafiles at different times. Meanwhile, the database continues accepting changes. Redo records those changes; on restore, RMAN needs continuous redo to bring the restored datafiles to a consistent state.

If you only take an online datafile backup without keeping the necessary archived redo logs, the backup may not be recoverable to a consistent state.

### 7.3. Backing up database and archive logs separately

Jobs can be separated:

```sql
BACKUP DATABASE;
BACKUP ARCHIVELOG ALL;
```

However, you must carefully design ordering, log switches, and time coverage so the required redo chain is backed up. `PLUS ARCHIVELOG` lets RMAN coordinate the workflow in a single clear command.

### 7.4. Control file and SPFILE backups

RMAN can automatically back up the control file when backing up the database/archivelogs depending on autobackup settings; enable it explicitly:

```sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

The control file holds critical database and backup metadata. If the control file is lost, autobackup enables restoring the control file and cataloging backups. SPFILE autobackup is equally important for restoring startup parameters.

### 7.5. Incremental backups

Incremental backups store blocks changed since a reference level/SCN. Archived redo logs are still needed to recover incremental backups to the target and replay changes past the checkpoint. Incrementals do not replace all archived redo logs needed for recovery.

Example:

```sql
BACKUP INCREMENTAL LEVEL 0 DATABASE PLUS ARCHIVELOG;
BACKUP INCREMENTAL LEVEL 1 DATABASE PLUS ARCHIVELOG;
```

Design level 0/1, cumulative/differential, and archived log backups around your organization's retention and recovery objectives.

## 8. DELETE INPUT and archived log deletion

### 8.1. DELETE INPUT

Example:

```sql
BACKUP ARCHIVELOG ALL DELETE INPUT;
```

`DELETE INPUT` instructs RMAN to delete the successfully backed-up input archived logs after backup completion, within the copy/input scope processed by RMAN. It is not a command to "delete every archive log across all destinations."

### 8.2. DELETE ALL INPUT

```sql
BACKUP ARCHIVELOG ALL DELETE ALL INPUT;
```

`DELETE ALL INPUT` deletes all archived log copies matching the input specification after a successful backup. Exercise particular caution if multiple copies of the same archived log exist across destinations.

### 8.3. When to use it?

Only use `DELETE INPUT`/`DELETE ALL INPUT` when:

- The archived log backup has completed and been verified.
- Backup pieces reside on storage independent of the archive source.
- The deletion policy permits deletion.
- Data Guard standbys have received/applied logs as required.
- Retention and recovery window requirements remain satisfied.

### 8.4. Why avoid manual deletion?

Deleting files at the OS level can leave the RMAN repository marking files as `AVAILABLE` even though the files are gone. Recovery catalog/control file metadata and the filesystem fall out of sync; subsequent restores/recoveries may fail when those logs are needed.

Use RMAN `DELETE`/`CROSSCHECK` per procedure to update metadata and manage files safely.

### 8.5. Backup optimization

`CONFIGURE BACKUP OPTIMIZATION ON` lets RMAN skip backing up files that already have enough copies per its logic and device type. This helps avoid redundant archived log backups, but you must understand device types, copy counts, and backup piece status.

Do not enable backup optimization and assume every log automatically has an offsite copy. Verify the policy and `LIST BACKUP` results.

### 8.6. Deletion policy

`RMAN ARCHIVELOG DELETION POLICY` specifies when archived logs become eligible for deletion. For instance, a policy can require logs to be backed up a certain number of times to a given device type or applied on standby databases. This policy interacts with `DELETE INPUT`, `DELETE ARCHIVELOG`, and FRA space reclamation.

A deletion policy does not replace the retention policy for whole-database backups; the two policies serve different purposes.

## 9. Configuring the archived log deletion policy

### 9.1. Backup-based deletion policy

Example requiring archive logs to be backed up at least once to disk before deletion:

```sql
CONFIGURE ARCHIVELOG DELETION POLICY
  TO BACKED UP 1 TIMES TO DEVICE TYPE DISK;
```

If backups go to SBT/tape, specify the device type matching your strategy. Do not set the policy solely around today's backup job; account for recovery requirements and offsite copies.

### 9.2. Data Guard deletion policy

In Data Guard, you can configure the deletion policy so archived logs are not deleted before being shipped or applied on standbys as required:

```sql
CONFIGURE ARCHIVELOG DELETION POLICY
  TO APPLIED ON ALL STANDBY;
```

The exact policy depends on the number of standbys, roles, transport/apply mode, and release. Options exist for shipped vs. applied; understand each option's exact condition before deploying.

### 9.3. Why is a policy needed?

If logs are deleted before a standby receives/applies them, the standby may suffer an archive gap and stop applying redo from the current stream unless another copy is found. If logs are deleted before backup, primary recovery may also lose needed redo segments.

### 9.4. Viewing the current policy

In RMAN:

```text
SHOW ARCHIVELOG DELETION POLICY;
SHOW ALL;
```

Record RMAN configuration output in the runbook. A policy may be inherited from prior settings; never assume a new database shares the same default policy as another.

### 9.5. Changing the policy requires system-wide review

Before changing the policy:

- Identify all standbys and role transitions.
- Confirm backup devices and required copy counts.
- Review archive retention and recovery windows.
- Calculate archive destination and FRA capacity.
- Verify backup jobs complete on schedule.
- Test deletion in a lab or with appropriate `REPORT`/preview checks.

Never disable the policy just to free FRA space without diagnosing why logs are not yet eligible for deletion.

## 10. Fast Recovery Area (FRA)

### 10.1. What is the FRA?

The Fast Recovery Area is an Oracle-managed storage area for backup and recovery files, which can include archived redo logs, backup pieces, image copies, flashback logs, and multiplexed copies of control files and online redo logs depending on configuration.

The FRA manages capacity and file reclamation according to retention/deletion policies. The FRA does not replace offsite backups or ransomware-resistant copies.

### 10.2. FRA parameters

| Parameter | Role |
| --- | --- |
| DB_RECOVERY_FILE_DEST | FRA location |
| DB_RECOVERY_FILE_DEST_SIZE | FRA capacity quota |

Verification:

```sql
SHOW PARAMETER db_recovery_file_dest
SHOW PARAMETER db_recovery_file_dest_size
```

### 10.3. Monitoring the FRA

```sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable,
    number_of_files
FROM v$recovery_file_dest;

SELECT
    file_type,
    percent_space_used,
    percent_space_reclaimable,
    number_of_files
FROM v$flash_recovery_area_usage;
```

View/column names may vary slightly by release; `V$RECOVERY_FILE_DEST` is the primary summary view. Always cross-check actual ASM/filesystem free space.

### 10.4. FRA full

When the FRA runs out of space, Oracle can no longer store new recovery files and archiving may stall. Common errors include `ORA-19809` and `ORA-19804`. If the archive destination fills and redo cannot be archived, the database can stall when a log switch is needed.

### 10.5. Handling a full FRA

1. Check `space_limit`, `space_used`, and `space_reclaimable`.
2. Check for archived logs not yet backed up or not yet applied on standby.
3. Check for failed or slow backup jobs.
4. Review retention and deletion policies.
5. Back up archived logs to storage with sufficient capacity.
6. Use RMAN to delete files eligible under policy.
7. Increase FRA size or add storage if the host/ASM has physical capacity.

Never manually delete files inside the FRA to "quickly free space." Doing so can corrupt metadata and break recovery chains.

### 10.6. Increasing DB_RECOVERY_FILE_DEST_SIZE

You can raise the FRA quota if underlying storage has free physical capacity:

```sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 200G
  SCOPE=BOTH;
```

This value is illustrative. `DB_RECOVERY_FILE_DEST_SIZE` is a management quota and does not create physical disk space. Confirm filesystem/ASM capacity and competing workloads before increasing it.

## 11. Retention policy vs. archived log deletion policy

### 11.1. Two different policies

The RMAN retention policy defines which backups are still needed to meet a recovery window or redundancy target. The archived log deletion policy defines when archived redo logs become eligible for deletion from archive destinations/FRA.

Do not conflate the two policies:

| Policy | Question it answers |
| --- | --- |
| Backup retention policy | Which backups are still required to recover to the stated target? |
| Archived log deletion policy | Which archived logs are eligible for deletion per backup/standby rules? |

### 11.2. Recovery window

Example retention policy configuration:

```sql
CONFIGURE RETENTION POLICY
  TO RECOVERY WINDOW OF 7 DAYS;
```

A 7-day recovery window instructs RMAN to keep enough backups to recover the database to any point within that window, based on available backups and redo. It does not mean every archived log older than 7 days is automatically deleted immediately.

### 11.3. Redundancy

You can configure a backup copy count:

```sql
CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
```

Redundancy 2 retains the number of backups required by RMAN logic. This is not the same as independent offsite archived log copy counts and does not replace Data Guard requirements.

### 11.4. REPORT OBSOLETE and DELETE OBSOLETE

Before deleting obsolete backups, inspect the report:

```sql
REPORT OBSOLETE;
```

After verifying the retention policy, you can run:

```sql
DELETE OBSOLETE;
```

`DELETE OBSOLETE` applies to backups RMAN determines are no longer needed under the retention policy. Do not use it as a blanket command to clear unbacked-up archived logs; archived log deletion policies and file status must still be understood.

### 11.5. Backed-up archived logs are not always immediately deletable

An archived log may have been backed up once yet still be needed for:

- The current recovery window.
- A Data Guard standby that has not yet applied it.
- Restoring an older datafile backup.
- Point-in-time recovery or cloning/duplication.
- An unverified offsite backup copy.

Backup success alone is not the sole criterion for deletion. The deletion policy must reflect actual recovery requirements.

### 11.6. REPORT NEED BACKUP

RMAN can report databases/datafiles needing backup for a recovery window:

```sql
REPORT NEED BACKUP RECOVERY WINDOW OF 7 DAYS DATABASE;
```

The output identifies datafiles lacking a backup recent enough for the window. It does not replace restore testing or verifying the archived log chain.

## 12. Backup metadata and protecting the recovery catalog

### 12.1. Control file repository

Without a dedicated recovery catalog, RMAN stores backup metadata in the control file. The control file has finite record capacity; older metadata may be reused via record management.

`CONTROL_FILE_RECORD_KEEP_TIME` influences how long reusable records are retained, but does not replace control file backups and does not guarantee indefinite metadata retention.

### 12.2. Recovery catalog

A recovery catalog is a separate repository schema that stores RMAN metadata long-term and manages multiple target databases. In large environments, a catalog retains backup history much longer than the control file.

The recovery catalog itself must be backed up and protected. Losing the catalog does not necessarily destroy backup pieces, but can make locating/restoring metadata harder; control file autobackup and catalog resync strategies are vital.

### 12.3. Control file autobackup

Recommended configuration:

```sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

RMAN automatically creates an autobackup of the control file (and SPFILE when an SPFILE is used) after appropriate backup operations. Set an explicit format if storing in an independent location:

```sql
CONFIGURE CONTROLFILE AUTOBACKUP FORMAT
  FOR DEVICE TYPE DISK TO '/backup/rman/cf_%F';
```

The path is an example. Ensure the format/path matches the device type and control file restore runbook when the database is not yet mounted.

### 12.4. Backup metadata and cataloging

When backup pieces are copied via storage replication or OS tools, RMAN may not know the new locations. After copying, catalog the files into the repository under the matching database/incarnation:

```sql
CATALOG START WITH '/backup/received/';
```

`CATALOG` only registers files in an RMAN-recognized backup format; it does not verify that all contents are restorable. Perform validation separately.

### 12.5. Protecting the DBID and backup info

When the control file is completely lost, the DBID and autobackup format/location may be needed to restore the control file. Store the DBID, `DB_NAME`, `DB_UNIQUE_NAME`, incarnations, and restore instructions outside the database host according to security policy.

## 13. The archived redo chain required for recovery

### 13.1. Datafile backups have checkpoint SCNs

Every datafile backup has a checkpoint SCN/metadata indicating the point at which the datafile was backed up. To recover to a newer target SCN, Oracle requires continuous redo from the necessary checkpoint up to the target.

Example:

```text
Datafile backup checkpoint SCN: 1000
Archived log A: SCN 1000 - 1100
Archived log B: SCN 1100 - 1200
Archived log C: SCN 1200 - 1300
Target recovery SCN: 1250

=> Requires continuous redo covering from the checkpoint to SCN 1250.
```

This is a conceptual example; actual recovery evaluates each datafile's checkpoint, redo threads, and database metadata.

### 13.2. Continuity matters more than file count

Having 100 archived logs does not guarantee the recovery chain is complete. If a single required sequence is missing between two logs, recovery will stop at the gap. Another copy of that missing sequence can restore continuity.

### 13.3. Threads in RAC

In RAC, each thread writes its own redo. Database recovery requires redo from every thread that recorded changes in the required SCN range. A sequence gap in one thread can halt recovery even if other threads have all logs.

### 13.4. Incarnation

After `OPEN RESETLOGS`, the database creates a new redo branch. A recovery target in the new incarnation generally cannot use sequences from an older incarnation based solely on file names. RMAN manages incarnation metadata and selects the matching logs.

### 13.5. Existing online redo logs

Current online redo logs may contain unarchived redo. In certain recovery paths, Oracle may use online redo logs or current redo to complete recovery. Never delete or move online redo logs as a substitute for archived log backups.

### 13.6. Checking SCN ranges

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    name,
    status,
    deleted
FROM v$archived_log
WHERE resetlogs_change# = (
    SELECT resetlogs_change# FROM v$database
)
ORDER BY thread#, first_change#;
```

This view reflects the current incarnation. To investigate an older recovery target, inspect incarnations and corresponding backup metadata rather than filtering only the current incarnation.

## 14. Restoring and recovering with RMAN

### 14.1. RESTORE vs. RECOVER

`RESTORE` copies backup datafiles/control files back to the database locations. `RECOVER` applies incremental backups and redo (archived/online) to bring datafiles to the target consistency point.

A database whose restore succeeded without sufficient redo may still fail to open at the requested target.

### 14.2. Complete database restore/recover

In scenarios where datafiles need restoration and sufficient backups/logs exist:

```sql
RUN {
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

This is a conceptual pattern; database state, control file, and datafiles must be prepared for the scenario. RMAN may request specific archived logs to proceed.

### 14.3. Restoring/recovering a single datafile

Example recovering datafile 7:

```sql
RUN {
  RESTORE DATAFILE 7;
  RECOVER DATAFILE 7;
}
```

After recovery succeeds and database state permits, bring the datafile online per runbook. Never perform `OFFLINE`/`ONLINE` arbitrarily on `SYSTEM` or critical datafiles.

### 14.4. Automatic archived log restoration

When RMAN recovers a datafile or database, it can automatically restore required archived logs from backups if the repository knows the backup pieces and devices are available. If logs are not found, inspect backup pieces, catalog, channels, incarnation, and thread/sequence.

### 14.5. Restoring archived logs explicitly

Example:

```sql
RESTORE ARCHIVELOG
  FROM SEQUENCE 100
  UNTIL SEQUENCE 120
  THREAD 1;
```

The default restore path follows RMAN/log destination configuration. You can use `SET ARCHIVELOG DESTINATION` inside a `RUN` block to restore to a suitable staging location, then catalog or apply per the recovery runbook.

### 14.6. Previewing before restore

RMAN supports `PREVIEW` to display required backups without performing the restore:

```sql
RESTORE DATABASE PREVIEW;
```

Use `PREVIEW` to verify backup selection before executing the actual restore in the prepared recovery environment.

## 15. Complete recovery vs. incomplete recovery

### 15.1. Complete recovery

Complete recovery applies all required redo to bring the database/datafiles to the latest possible state using available redo and recovery targets. When complete backups and continuous logs are available, recovery can preserve all committed transactions within the redo range.

### 15.2. Incomplete recovery

Incomplete recovery stops at a target earlier than the current point, such as:

- A specific SCN.
- A specific timestamp.
- A specific log sequence.
- A restore point.

Changes after the target will not exist in the recovered database. After incomplete database recovery, `OPEN RESETLOGS` is typically required to create a new incarnation.

### 15.3. Point-in-time recovery by SCN

RMAN example:

```sql
RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

After recovery completes, open the database per procedure, typically:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

The SCN is an illustrative number. Before proceeding, verify the target SCN, incarnation, suitable backups, and data loss impact after the target.

### 15.4. Point-in-time recovery by time

Example:

```sql
RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 10:00:00',
             'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

The target timestamp must be interpreted according to the environment's timezone/clock and RMAN semantics. For critical transactions, an SCN or restore point provides a more exact boundary than a timestamp.

### 15.5. OPEN RESETLOGS

`OPEN RESETLOGS` creates a new incarnation and resets the redo sequence branch. Afterward:

- Confirm database open mode and role.
- Check backup/archivelog destinations.
- Take a fresh baseline database backup.
- Synchronize recovery catalog/incarnation metadata.
- Check Data Guard/standbys and role/flashback procedures if applicable.

Never use `RESETLOGS` after a normal complete recovery unless the recovery scenario requires it.

## 16. Archived redo logs in RAC

### 16.1. Each instance has a redo thread

In RAC, each instance normally writes to its own redo thread. When an instance switches logs, the resulting archived log belongs to that thread. Database-wide backup/recovery must account for all threads holding needed redo.

### 16.2. Checking threads

```sql
SELECT
    thread#,
    enabled,
    status,
    instance
FROM v$thread
ORDER BY thread#;
```

In RAC, you can inspect cluster-wide instance/thread states using `GV$INSTANCE` and related views. Disabled threads still retain sequence/archived log history in the control file.

### 16.3. Checking sequences by thread

```sql
SELECT
    thread#,
    MAX(sequence#) AS max_archived_sequence,
    MAX(next_change#) AS max_next_scn
FROM v$archived_log
WHERE archived = 'YES'
  AND deleted = 'NO'
GROUP BY thread#
ORDER BY thread#;
```

Querying max sequence only shows the upper bound; it does not prove there are no gaps. Verify continuous sequences and SCNs, as well as the actual backup pieces containing the logs.

### 16.4. Backing up archive logs in RAC

RMAN connected to the target database can back up archived logs across threads per configuration. If archived logs reside on a local filesystem visible only to the node that created them, channels running on other nodes will not be able to access those files.

Common deployment approaches:

- Use ASM/shared storage so all instances/channels see the same archive files.
- Use a properly mounted shared filesystem across nodes.
- Configure channel/node affinity and archive destinations per supported architecture.

Never assume a local path on node 1 exists on node 2.

### 16.5. Recovery and thread gaps

When restoring a RAC database, RMAN/Oracle needs redo from every relevant thread. If a single archived log from thread 2 is missing, recovery can stall even if thread 1 has every sequence. Locate alternate copies, backup pieces, standbys, or older archive destinations to recover the missing sequence.

### 16.6. Threads and incarnations

After `RESETLOGS`, sequences restart in the new incarnation. When handling archive files from multiple nodes or old backups, identify them by DBID, thread, sequence, and resetlogs metadata—not file name alone.

## 17. Archived redo logs and Data Guard

### 17.1. Redo transport

Data Guard ships redo from the primary to standbys. Redo can be transmitted over the network according to the transport mode and stored/applied on the standby. Archived logs are key units for transport/apply and gap resolution.

### 17.2. Standby redo logs

Standby redo logs (SRLs) enable a standby to receive the redo stream, especially for real-time apply. SRLs are not the same as archived logs; once redo is archived on the standby, the archived log can be applied or retained per policy.

### 17.3. Transport and apply

Distinguish between:

- Shipped: redo/archive has been sent to the standby.
- Received: standby has received the log/redo.
- Applied: redo has been applied to the standby database.

A log being shipped does not guarantee it has been applied. Deletion policies must match the requirement that standbys apply logs before deleting them on the primary.

### 17.4. Checking Data Guard archive destinations

```sql
SELECT
    dest_id,
    status,
    target,
    destination,
    error,
    recovery_mode,
    synchronization_status
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

Columns may vary by release/role. Check `V$ARCHIVE_DEST`, `V$ARCHIVE_DEST_STATUS`, and Data Guard Broker status when using Broker.

### 17.5. Checking applied logs on the standby

On the standby, you can query:

```sql
SELECT
    thread#,
    sequence#,
    first_time,
    next_time,
    applied,
    name
FROM v$archived_log
ORDER BY thread#, sequence#;
```

Values of `APPLIED` may have different semantics depending on role and view; verify against release documentation. Cross-check with the managed recovery process, apply lag, and Broker output.

### 17.6. Archive gaps

An archive gap occurs when a standby lacks one or more redo logs needed to continue applying. Oracle can automatically request/fetch logs from the primary if transport/configuration allows. If the logs are no longer on the primary, the DBA must locate alternate backups/archive copies or resolve the gap per the Data Guard runbook.

### 17.7. Deletion policy in Data Guard

Do not delete archived logs on the primary simply because they were backed up if standbys have not yet received/applied them per policy. `TO APPLIED ON ALL STANDBY` is commonly used when waiting for all standbys to apply, though you must evaluate all standbys and role transition states.

If a standby goes offline for an extended period, an apply-waiting policy can force the primary to retain logs longer and grow the FRA. That is a signal to address the standby, retention, or capacity—not a reason to blindly disable the policy.

### 17.8. After failover/switchover

After a role transition, identify which database is the new primary, the new thread/sequence, and which archived logs are still needed by the old primary/new standby. Check incarnations, transport destinations, apply states, and deletion policies. Never delete logs based solely on old roles.

## 18. Missing archived logs and recovery gaps

### 18.1. Symptoms

Recovery can halt due to a missing required archived log, RMAN reporting it cannot find a log/backup piece, or a standby reporting an archive gap. The database cannot advance to the target if a mandatory redo segment is missing.

### 18.2. Finding the missing sequence

Check metadata by thread and sequence:

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    name,
    status,
    deleted
FROM v$archived_log
WHERE thread# = 1
  AND sequence# BETWEEN 100 AND 120
ORDER BY sequence#, recid;
```

Multiple rows for the same sequence can represent multiple copies. Verify physical file existence and backup metadata rather than relying solely on an `AVAILABLE` status.

### 18.3. Finding backups containing the archived log

In RMAN:

```text
LIST BACKUP OF ARCHIVELOG
  FROM SEQUENCE 100
  UNTIL SEQUENCE 120;
```

Adjust thread selection syntax per your release. Verify that backup pieces exist and the device is readable.

### 18.4. Alternate sources

If an archive file is missing from the primary destination, check:

- Copies at other archive destinations.
- Backup sets on disk/tape/cloud.
- The FRA or managed storage snapshots.
- Standby databases/archive destinations.
- Backups from other RAC nodes/shared storage.
- Offsite copies properly cataloged with matching DBID/incarnation.

Never fabricate dummy files or rename a log of a different sequence to fill a gap.

### 18.5. If the missing log cannot be recovered

If no copy of the mandatory redo exists, recovery may only be possible up to an SCN prior to the gap, or another disaster recovery option must be used. Assess data loss, business transactions, and restore points; never skip logs to force a database open in an inconsistent state.

### 18.6. Recovering to before the gap

In some cases, you may perform incomplete recovery to an SCN/time prior to the missing log, followed by `OPEN RESETLOGS`. This discards all changes after the target, including valid transactions. Obtain business/data-loss sign-off and take a fresh backup afterward.

## 19. Verifying archived log backups

### 19.1. LIST ARCHIVELOG

In RMAN:

```text
LIST ARCHIVELOG ALL;
LIST BACKUP OF ARCHIVELOG ALL;
```

These two commands show different views: known archived log files vs. backup sets containing archived logs. Inspect both when investigating.

### 19.2. CROSSCHECK ARCHIVELOG

```text
CROSSCHECK ARCHIVELOG ALL;
```

`CROSSCHECK` compares RMAN metadata with physical file existence on storage/media. Missing files are marked `EXPIRED` in the repository.

### 19.3. DELETE EXPIRED

After crosschecking and confirming files are genuinely gone:

```text
DELETE EXPIRED ARCHIVELOG ALL;
```

This cleans metadata for files marked `EXPIRED`; it does not recover lost files. Never run it to hide storage failures or remove records for files that are still needed.

### 19.4. VALIDATE

RMAN can verify backup readability:

```text
RESTORE ARCHIVELOG
  FROM SEQUENCE 100
  UNTIL SEQUENCE 110
  THREAD 1
  VALIDATE;
```

Check release-specific syntax and backup devices. `VALIDATE` reads and verifies backup data without creating restored files for production.

### 19.5. Restore rehearsal

Validation does not replace restore testing. A readable backup set can still lack a control file, catalog metadata, encryption wallet, media library/channel, or subsequent archived logs. Periodically restore archived logs and recover a cloned database in an isolated environment.

### 19.6. Checking backup pieces

Confirm:

- Backup pieces exist on storage.
- The RMAN repository recognizes the pieces.
- Pieces are not truncated or corrupted.
- The encryption wallet/key is available.
- Compression/media management is compatible.
- Complete datafile backups and redo exist up to the target.
- Control file/SPFILE metadata is available.

## 20. Protecting archived redo logs and backups

### 20.1. Independent storage

Do not keep the sole copy of archived logs on the same volume as datafiles/online redo logs if a single storage failure could destroy everything. Archived log backups should have copies on independent storage and follow an offsite strategy.

### 20.2. Immutable/offline copies

Ransomware or administrative mistakes can destroy both the database and backups simultaneously if they share credentials or storage. Use immutable/object lock, offline tape, or a privilege-separated repository to protect backups per policy.

### 20.3. Encryption

Archived redo logs can contain sensitive data inside redo records. Protect them in transit and at rest; consider RMAN backup encryption and protect the wallet/keystore. If encrypted backups lose their wallet/key, they become unusable.

### 20.4. Compression

RMAN can use backup compression to reduce storage and network usage. Compression consumes CPU and its effectiveness depends on the data. Measure throughput, CPU, and restore duration; do not pick compression levels based solely on size.

### 20.5. Checksums and corruption detection

Oracle/RMAN provide checksum and validation mechanisms to detect block/backup corruption. Enable and use supported checks and review validation output. A file existing on the filesystem does not guarantee its backup contents are valid.

### 20.6. Backup access control

Restrict who can read or delete backups, the FRA, and archived logs. Separate database administration privileges from backup deletion privileges where possible; audit `DELETE`, crosscheck, and RMAN configuration changes.

## 21. Monitoring and archive alerting

### 21.1. Archive destination status

Monitor periodically:

```sql
SELECT
    dest_id,
    status,
    binding,
    target,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

`STATUS`/`ERROR` helps detect failed destinations. Destinations can be `LOCAL` or `SERVICE` depending on configuration. Monitor both destination and transport status.

### 21.2. Archive processes

```sql
SELECT *
FROM v$archive_processes;
```

This view provides archiver process information depending on release. Cross-check the alert log and archive destinations if archivers stop making progress.

### 21.3. Log switch rate

You can aggregate hourly log switches:

```sql
SELECT
    TRUNC(first_time, 'HH24') AS hour_start,
    thread#,
    COUNT(*) AS switches
FROM v$log_history
WHERE first_time >= SYSDATE - 1
GROUP BY TRUNC(first_time, 'HH24'), thread#
ORDER BY hour_start, thread#;
```

Overly frequent log switches can generate many archive files and increase archiver/backup overhead. High frequency is not automatically an error; compare redo generation, log file sizing, and workload.

### 21.4. FRA usage

```sql
SELECT
    ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
    ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
    ROUND(space_reclaimable / 1024 / 1024 / 1024, 2) AS reclaimable_gb,
    number_of_files
FROM v$recovery_file_dest;
```

Set alerts before the FRA reaches its limit, using percentage used and growth rate. Thresholds should reflect peak archive generation and DBA response time.

### 21.5. Archive generation rate

Estimate archive generation per interval using archived log sizes:

```sql
SELECT
    TRUNC(first_time, 'HH24') AS hour_start,
    thread#,
    COUNT(*) AS log_count,
    ROUND(SUM(blocks * block_size) / 1024 / 1024, 1) AS archive_mb
FROM v$archived_log
WHERE first_time >= SYSDATE - 1
  AND name IS NOT NULL
GROUP BY TRUNC(first_time, 'HH24'), thread#
ORDER BY hour_start, thread#;
```

A single sequence can have multiple rows/copies in `V$ARCHIVED_LOG`; summing directly can double-count. For accurate reporting, filter to one destination/copy or deduplicate by `DBID`, `RESETLOGS_ID`, `THREAD#`, and `SEQUENCE#`.

### 21.6. Archive destination full alerts

Configure alerts for:

- Destination `STATUS` not `VALID` or reporting an `ERROR`.
- Rapid FRA usage growth with low reclaimable space.
- Archived log backup jobs failing to finish within SLA.
- Archive generation exceeding expected capacity.
- Standby apply lag or archive gaps.
- No recent backup/offsite copy within the defined window.

Alerts should identify the database, instance, destination, error, and linked runbook.

## 22. Common errors and troubleshooting

| Error/symptom | Possible cause | Troubleshooting direction |
| --- | --- | --- |
| ORA-00257 archiver error | Archive destination full or unwritable | Check destination/FRA, back up logs, free space per RMAN policy |
| ORA-19809 | FRA exceeded DB_RECOVERY_FILE_DEST_SIZE | Check reclaimable space, backup/deletion policy, increase quota if storage allows |
| ORA-19804 | Cannot reclaim enough FRA space | Identify non-reclaimable files, backup/archive backlog, storage capacity |
| ORA-16014 | Log sequence not archived to required destination | Check LOG_ARCHIVE_DEST, destination state, and storage/network errors |
| ORA-16038 | Log cannot be archived | Check destination, permissions, free space, and alert log |
| ORA-00308 | Cannot open archived log | Locate file in another destination/backup, check path and permissions |
| ORA-00279/ORA-00289 | Recovery requires specific redo/archived log | Identify thread/sequence/SCN, restore log from matching incarnation |
| RMAN-06025 | No matching archived log backup found | Check LIST BACKUP, devices, catalog, and retention |
| RMAN-06054 | Recovery requires archived log unknown to repository | Locate archive file, catalog properly, or verify recovery target |
| Standby archive gap | Standby missing sequence/thread | Locate and ship missing logs, check transport/apply |
| Backup job reports success but restore lacks logs | Backup selection/retention did not cover chain | Inspect backup metadata, sequence/thread coverage, and run restore tests |
| Low FRA reclaimable space | Logs not backed up/applied or held by policy | Check deletion policy, standbys, and backup SLA |

### 22.1. ORA-00257

When the archiver cannot write archive logs, Oracle may halt further transactions when a log switch is needed and no log group can be archived. Resolution:

1. Connect using an appropriate administrative method; in some situations only administrative connections succeed.
2. Inspect the alert log, `V$ARCHIVE_DEST`, and `V$RECOVERY_FILE_DEST`.
3. Determine whether the destination is full, permissions are wrong, a mount failed, or remote networking failed.
4. Back up needed archived logs to other storage.
5. Delete eligible files via RMAN according to the deletion policy.
6. Confirm the archiver resumes and the database continues log switching.

Never delete archive files manually to restore service.

### 22.2. ORA-19809 and ORA-19804

These errors typically indicate the FRA has exhausted its quota or cannot reclaim eligible files. Inspect which file types consume space and review retention policies. You can increase `DB_RECOVERY_FILE_DEST_SIZE` if physical storage has free capacity, though that will not help if the underlying volume is physically full.

### 22.3. ORA-00308

Recovery or an archival process cannot open an archived log at the specified path. Check:

- Does the file exist?
- Was the file manually renamed, moved, or deleted?
- Are permissions, ownership, mounts, or ASM disk groups correct?
- Is there a copy at another destination or inside a backup set?
- Does RMAN/control file metadata point to the correct file?

### 22.4. RMAN-06025 and RMAN-06054

Verify the database DBID, incarnation, thread, and sequence. Run `LIST BACKUP OF ARCHIVELOG`, `LIST INCARNATION`, and `CROSSCHECK` as appropriate. If valid files exist outside the repository, `CATALOG` them and retry restore/recover.

If no copy of the required log exists, identify a recovery target prior to the gap and evaluate data loss. Never force recovery past mandatory redo.

## 23. Archived redo log backup runbook

### 23.1. Before running the job

- [ ] Database is in ARCHIVELOG mode.
- [ ] Archive destination is active and has free space.
- [ ] RMAN target/recovery catalog is reachable.
- [ ] Backup devices/channels are ready.
- [ ] Retention and archived log deletion policies are verified.
- [ ] Standby transport/apply state checked if applicable.
- [ ] Backup storage is independent of the archive source.

### 23.2. Running the backup

A basic job pattern:

```sql
BACKUP ARCHIVELOG ALL
  TAG 'ARCHIVE_DAILY';
```

Or within a database backup job:

```sql
BACKUP DATABASE PLUS ARCHIVELOG
  TAG 'DB_FULL_PLUS_ARCH';
```

Actual commands must match channel, device, compression, encryption, and storage policies.

### 23.3. Verifying the backup

```text
LIST BACKUP OF ARCHIVELOG ALL;
REPORT OBSOLETE;
```

Verify thread/sequence coverage, timestamps, tags, backup pieces, and job status. Confirm job logs contain no overlooked warnings or errors.

### 23.4. Cleanup

Once the deletion policy is verified and the backup has completed:

```sql
BACKUP ARCHIVELOG ALL DELETE INPUT;
```

Or run `DELETE` per policy/runbook. Never use `DELETE ALL INPUT` without confirming all copies may be safely removed.

### 23.5. Record keeping

Log:

- Job start and end times.
- DBID, DB_UNIQUE_NAME, and incarnation.
- Threads/sequences backed up.
- Backup pieces, devices, and tags.
- Archive/backup sizes.
- Validation results.
- Number of files deleted and policy applied.
- Errors, retries, and operator name.

## 24. Recovery runbook requiring archived redo logs

### 24.1. Define the recovery objective

Before restore/recover, determine:

- Does the whole database or only a datafile need recovery?
- Is the target current/latest, an SCN, a timestamp, or a restore point?
- Which incarnation is the database currently in?
- Can a Data Guard standby supply redo?
- How much data loss and downtime do RPO/RTO permit?

### 24.2. Verify the backup chain

Identify suitable datafile backups, control file/SPFILE, incremental backups, and archived logs from checkpoint to target. Verify thread/sequence/SCN continuity.

### 24.3. Verify readability

Use RMAN `PREVIEW`/`VALIDATE` as appropriate. Confirm media managers, wallets, password files, storage mounts, and permissions. Do not start a large restore before knowing where all backup pieces reside.

### 24.4. Execute restore/recover

Run in the recovery environment per runbook:

```sql
RUN {
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

For incomplete recovery, set the target before `RESTORE`/`RECOVER` and prepare for `OPEN RESETLOGS` per the scenario. Never mix complete recovery commands with an incomplete target.

### 24.5. Verify the database after recovery

- Check the alert log and recovery messages.
- Confirm database open mode and role.
- Check datafile status and read/write access.
- Run business checks and data reconciliation.
- Take fresh backups after `RESETLOGS` if performed.
- Check Data Guard/standbys and archive destinations.

## 25. Lab: backing up archived redo logs with RMAN

Run only on a lab database with RMAN privileges and dedicated storage. Adjust paths for your OS/ASM setup.

### 25.1. Check log mode

In SQL*Plus:

```sql
ARCHIVE LOG LIST
SELECT log_mode FROM v$database;
```

If the database is in `NOARCHIVELOG`, do not switch mode on a shared database solely for a lab. Use an isolated lab instance.

### 25.2. Generate a new archived log

```sql
ALTER SYSTEM SWITCH LOGFILE;
ALTER SYSTEM ARCHIVE LOG CURRENT;
```

Wait for the archive process to finish and inspect `V$ARCHIVED_LOG`.

### 25.3. Back up logs

In RMAN:

```text
BACKUP ARCHIVELOG ALL
  FORMAT '/backup/lab/arch_%d_%T_%s_%p.bkp'
  TAG 'LAB_ARCH';
```

The path is an example; create the directory and grant permissions before running.

### 25.4. Inspect backups

```text
LIST BACKUP OF ARCHIVELOG ALL;
```

Identify threads, sequences, start/end SCNs, and written backup pieces.

### 25.5. Validate

```text
RESTORE ARCHIVELOG ALL VALIDATE;
```

If syntax/selection differs in your release, use `RESTORE ARCHIVELOG` with an explicit range and `VALIDATE` per release documentation.

### 25.6. Back up and delete input in the lab

After verifying backup pieces and the deletion policy:

```text
BACKUP ARCHIVELOG ALL DELETE INPUT;
```

Verify that source files were deleted within the input scope and that the RMAN repository reflects the updated state. Never run this command on production just for testing.

## 26. Lab: inspecting the recovery chain and gaps

### 26.1. Inspect archives by thread/sequence

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    first_time,
    next_time,
    name
FROM v$archived_log
WHERE name IS NOT NULL
ORDER BY thread#, sequence#;
```

### 26.2. Inspect backup metadata

```text
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
LIST INCARNATION;
```

Cross-check datafile backups and archive backups within the same incarnation.

### 26.3. Test restore preview

```text
RESTORE DATABASE PREVIEW;
```

Observe which backup pieces and archived logs RMAN plans to use. `PREVIEW` does not replace a restore test.

### 26.4. Safely simulate an archive gap

Never delete production archived logs. In a clone/lab, you can create a controlled missing archive copy or metadata test to observe how recovery reports a missing log. Note which thread/sequence RMAN requests and locate the required backup source.

### 26.5. Recover a cloned instance

Restore/recover a cloned database into an isolated location per runbook. Confirm the database opens and data matches the target SCN. The lab is complete when there is evidence the log chain was applied and a test application can read the data.

## 27. Best practices

1. **Use ARCHIVELOG for production needing media recovery.** ARCHIVELOG mode alone is not a backup.
2. **Back up datafiles and archived redo logs as a single recovery chain.** Continuous redo from checkpoint to target is mandatory.
3. **Monitor both thread and sequence.** RAC has multiple redo threads; never check only the highest sequence.
4. **Account for SCN and incarnation.** File names and sequence numbers alone are insufficient to determine which recovery branch a log belongs to.
5. **Use RMAN as the primary tool.** Manage metadata, backup selection, restores, and policy-based deletion through RMAN.
6. **Use PLUS ARCHIVELOG for online database backups.** Understand log switches and redo coverage around datafile backups.
7. **Back up the control file and SPFILE.** Enable control file autobackup and protect metadata required for restores.
8. **Separate retention policy from deletion policy.** One governs which backups to keep; the other governs when archived logs may be deleted.
9. **Avoid manual deletion.** Use RMAN `CROSSCHECK`/`DELETE` per runbook.
10. **Maintain independent/offsite copies.** Never keep the sole backup in the same failure domain as the database.
11. **Monitor the FRA before it fills up.** Track space used, reclaimable space, archive generation, and backup backlogs.
12. **Respect Data Guard apply.** Never delete logs before standbys receive/apply them per policy.
13. **Validate and test restores regularly.** Backup job success does not prove recovery success.
14. **Protect encryption wallets.** Encrypted backups are useless if keys are lost.
15. **Control backup deletion privileges.** Enforce separation of duties, auditing, and immutable/offline copies.
16. **Define clear recovery objectives.** RPO/RTO dictate retention, archive storage, and backup frequency.
17. **Monitor the alert log.** Address `ORA-00257`, `ORA-19809`, and archive gaps before they impact production.
18. **Build runbooks tailored to release and topology.** RAC, CDB/PDB, ASM, and Data Guard each have distinct requirements.

## 28. Self-check questions

1. How do online redo logs and archived redo logs differ?
2. Why are archived logs created only after a log switch/archival operation?
3. What recovery capabilities does ARCHIVELOG mode enable?
4. How does NOARCHIVELOG mode limit online backups?
5. What roles do thread, sequence, and SCN play?
6. Why does RAC require archived redo from multiple threads?
7. What do `FIRST_CHANGE#` and `NEXT_CHANGE#` describe?
8. Why does a maximum sequence number not prove a log chain has no gaps?
9. What is the significance of `RESETLOGS` creating a new incarnation?
10. What does RMAN `BACKUP ARCHIVELOG ALL` do?
11. How does `BACKUP DATABASE PLUS ARCHIVELOG` support online backups?
12. Why do online datafile backups require archived redo logs?
13. How does `DELETE INPUT` differ from `DELETE ALL INPUT`?
14. Why should archived logs not be deleted via the OS?
15. How does backup optimization affect archived log backups?
16. How does a retention policy differ from an archived log deletion policy?
17. What does the deletion policy `TO APPLIED ON ALL STANDBY` protect against?
18. What types of recovery files can the FRA contain?
19. What issues do `ORA-19809` and `ORA-19804` typically indicate?
20. Why does increasing `DB_RECOVERY_FILE_DEST_SIZE` not create additional physical storage?
21. How does control file autobackup help when the control file is lost?
22. How does a recovery catalog differ from metadata inside the control file?
23. How does `RESTORE` differ from `RECOVER`?
24. How does complete recovery differ from incomplete recovery?
25. When is `OPEN RESETLOGS` required?
26. How can you locate a missing archived log?
27. Why can a single missing sequence block recovery even when all other sequences are available?
28. How do `shipped` and `applied` differ in Data Guard?
29. How does `VALIDATE` differ from a restore rehearsal?
30. What should you verify before allowing RMAN `DELETE INPUT`?

## 29. Mental model summary

```text
DATAFILE BACKUP
     |
     |  checkpoint SCN
     v
ARCHIVED REDO LOG CHAIN
     |
     +-- Thread 1: sequence / SCN
     +-- Thread 2: sequence / SCN (RAC)
     +-- Incarnation / RESETLOGS branch
     |
     v
RMAN BACKUP AND RETENTION
     |
     +-- BACKUP ARCHIVELOG
     +-- BACKUP DATABASE PLUS ARCHIVELOG
     +-- Control file / SPFILE autobackup
     +-- Retention policy
     +-- Archived log deletion policy
     |
     v
PROTECTED STORAGE
     |
     +-- FRA / archive destination
     +-- Independent backup repository
     +-- Offsite / immutable copy
     +-- Encryption wallet and metadata
     |
     v
RESTORE + RECOVER
     |
     +-- Complete recovery
     +-- Incomplete / PITR
     +-- RAC thread continuity
     +-- Data Guard gap resolution
     |
     v
VALIDATE + RESTORE TEST
```

**Key takeaway:** Archived redo logs bridge a datafile backup to the target recovery point. Recoverability depends on a baseline backup, continuous redo by SCN/thread/incarnation, and sufficient metadata to locate the right files. Use RMAN to back up, verify, and delete according to policy; maintain independent copies, monitor the FRA and Data Guard, and regularly rehearse restore/recover operations.
