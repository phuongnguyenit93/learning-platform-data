# Fast Recovery Area, Archived Logs, and Space Pressure in Oracle

## 1. Role of the Fast Recovery Area

The **Fast Recovery Area (FRA)** is a storage area managed by Oracle Database for backup and recovery files. The FRA helps the database centrally manage recovery files, track space usage, identify reclaimable files, and automatically free eligible files when space is needed for new recovery files.

File types commonly placed in the FRA:

- Archived redo logs.
- RMAN backup pieces and image copies.
- Flashback logs.
- Control file autobackups and SPFILE autobackups.
- Datafile copies.
- Other Oracle-managed recovery files, including foreign archived logs in appropriate configurations.

The FRA is typically placed on a filesystem or an Oracle ASM disk group. For example, ASM disk group +RECO or a dedicated directory on storage designed for recovery.

The FRA is not an independent backup and does not replace an off-host backup strategy. If the database, FRA, and only backup all reside on the same storage array or failure domain, a storage failure can destroy both the data and the ability to recover.

## 2. Two Core Configuration Parameters

Oracle uses two primary initialization parameters:

| Parameter | Meaning |
| --- | --- |
| DB_RECOVERY_FILE_DEST | FRA location, which can be a filesystem path or an ASM disk group |
| DB_RECOVERY_FILE_DEST_SIZE | FRA capacity limit that Oracle is permitted to use |

Example:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 200G
SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '+RECO'
SCOPE = BOTH;
~~~

Oracle requires configuring the FRA size before configuring the FRA location. The value 200G is only an example; choose capacity based on workload, retention, and actual storage capacity.

Verify:

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
~~~

Or:

~~~sql
SELECT name,
       value
FROM v$parameter
WHERE name IN (
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'db_flashback_retention_target'
)
ORDER BY name;
~~~

### 2.1. DB_RECOVERY_FILE_DEST_SIZE Is a Quota, Not Physical Capacity

DB_RECOVERY_FILE_DEST_SIZE is the limit Oracle uses to manage the FRA. It does not create additional space on the filesystem or ASM.

For example:

- An ASM disk group has 500 GB remaining.
- The FRA is configured with a 200 GB quota.
- Oracle manages recovery files within the 200 GB FRA limit.

If the quota is raised to 400 GB while ASM only has 50 GB physically free, the database can still encounter out-of-space errors at the storage layer. Increasing the parameter does not substitute for expanding the disk group or filesystem.

Conversely, do not set the quota equal to the entire physical capacity. Leave room for online redo logs, datafiles, control files, other archive destinations, other workloads sharing the same disk group, and storage overhead.

### 2.2. Choosing the FRA Location

Example using a filesystem:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 200G
SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '/u03/oracle/fra'
SCOPE = BOTH;
~~~

Example using ASM:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 500G
SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '+RECO'
SCOPE = BOTH;
~~~

In RAC, the FRA location must be shared storage accessible by all instances according to RAC architecture. Do not place the FRA in a local directory visible to only one node if the database needs to access files from other nodes.

### 2.3. Moving the FRA Location

Changing DB_RECOVERY_FILE_DEST should not be treated as a simple file move operation. Existing files, the RMAN repository, archived log destinations, Data Guard, and accessibility across all instances must all be considered.

Before changing the location:

1. Identify which files currently reside in the FRA.
2. Check whether backups/recovery still need those files.
3. Prepare the target storage and access permissions.
4. Build a transition plan according to Oracle documentation for your running version and architecture.
5. Verify RMAN, archive destinations, and Data Guard after switching.

Do not arbitrarily copy or delete files in the FRA with OS commands and assume the repository has been updated.

## 3. How Does the FRA Relate to ARCHIVELOG?

FRA and ARCHIVELOG mode are two distinct concepts:

- ARCHIVELOG mode specifies that Oracle preserves archived redo log copies when online redo logs are archived.
- FRA is a storage area that can hold archived redo logs along with other backup/recovery files.

A database can be in ARCHIVELOG mode while writing archived logs to a destination outside the FRA. Conversely, configuring an FRA does not automatically prove archived logs are being written into the FRA; check LOG_ARCHIVE_DEST_n.

### 3.1. Checking Archive Mode

~~~sql
SELECT name,
       log_mode,
       open_mode,
       database_role
FROM v$database;
~~~

Or in SQL*Plus:

~~~text
ARCHIVE LOG LIST
~~~

If the database is in NOARCHIVELOG mode, old online redo logs can be reused after checkpoints through normal operations without archived copies. This limits point-in-time recovery and online backup options.

### 3.2. Enabling ARCHIVELOG Mode

General procedure during a maintenance window:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
ARCHIVE LOG LIST;
~~~

This operation requires downtime and must be accompanied by a plan for backups, archive destinations, storage capacity, and recovery testing. Do not toggle archive mode on production just to test a command.

### 3.3. Directing Archived Logs to the FRA

To use the FRA as a local archive destination:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=USE_DB_RECOVERY_FILE_DEST'
SCOPE = BOTH;
~~~

USE_DB_RECOVERY_FILE_DEST instructs Oracle to use the configured FRA. Verify:

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Do not modify a LOG_ARCHIVE_DEST_n serving Data Guard or a mandatory destination without understanding the current configuration. A database can have multiple local/remote archive destinations with different roles.

### 3.4. Archived Redo Log Flow

~~~text
Online Redo Log
      |
      | redo log switch / archive
      v
ARCn process
      |
      v
LOG_ARCHIVE_DEST_n
      |
      +---- LOCATION=USE_DB_RECOVERY_FILE_DEST
      |              |
      |              v
      |             FRA
      |
      +---- other filesystem / ASM destination
      |
      +---- SERVICE=... (remote Data Guard destination)
                     |
                     v
                Standby database

Archived log
      |
      v
RMAN backup / apply at standby / retention policy
      |
      v
Eligible for deletion when all configured requirements are met
~~~

Archived logs are part of the recovery chain. Do not delete them merely because files are old or have been copied to another directory.

## 4. Why Are Archived Logs Important?

Archived redo logs store redo archived from online redo logs. They are used to:

- Recover datafiles after restoring backups.
- Recover the database to a target time or SCN.
- Perform media recovery.
- Ship redo to physical standbys in Data Guard.
- Support backup/recovery and certain maintenance operations.

If a database runs in ARCHIVELOG mode and the archive destination cannot be written to, Oracle cannot archive required online redo logs. Redo logs can then no longer be reused normally, and the database may be severely impacted.

### 4.1. Archive Logs Are Generated by Redo Thread and Sequence

In a single-instance database, there is usually one redo thread. RAC has multiple redo threads, with each instance having its own thread.

Identifying archived logs must consider at least:

- DBID/database identity.
- RESETLOGS incarnation.
- THREAD#.
- SEQUENCE#.
- SCN range and timestamps.

Do not look solely at SEQUENCE# while ignoring THREAD# or RESETLOGS_CHANGE#. Sequence numbers can repeat across threads or incarnations.

### 4.2. Log Switches and Archiving

When online redo logs switch, ARCn processes archive eligible redo logs. You can monitor:

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

Archived log details:

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       completion_time,
       archived,
       deleted,
       status,
       name
FROM v$archived_log
WHERE completion_time >= SYSDATE - 1
ORDER BY completion_time DESC;
~~~

V$ARCHIVED_LOG can contain multiple records for the same thread/sequence due to multiple destinations, copies, or registrations. When analyzing, consider DEST_ID, NAME, REGISTRAR, STANDBY_DEST, and status appropriately rather than assuming each sequence has only one row.

### 4.3. Archive Log Generation Rate

To estimate hourly redo/archive generation volume:

~~~sql
SELECT TO_CHAR(completion_time, 'YYYY-MM-DD HH24') AS archive_hour,
       COUNT(*) AS log_count,
       ROUND(SUM(blocks * block_size) / 1024 / 1024, 2) AS size_mb
FROM v$archived_log
WHERE completion_time >= SYSDATE - 2
  AND name IS NOT NULL
GROUP BY TO_CHAR(completion_time, 'YYYY-MM-DD HH24')
ORDER BY archive_hour;
~~~

Some environments may have multiple copies of the same sequence in the view. Summing every row can double-count the figures. For accurate reporting, filter by the relevant destination/registrar or aggregate by thread, sequence, and managed copy.

To view log size by unique thread/sequence, you can start with:

~~~sql
SELECT thread#,
       sequence#,
       MAX(blocks * block_size) AS bytes_per_sequence,
       MAX(completion_time) AS completion_time
FROM v$archived_log
WHERE completion_time >= SYSDATE - 2
  AND name IS NOT NULL
GROUP BY thread#, sequence#
ORDER BY completion_time;
~~~

These are estimates based on records visible in the control file; record retention time and repository configuration affect results.

## 5. How Does the FRA Manage Space?

Oracle tracks files in the FRA and classifies them by whether they are still needed for recovery. When more space is needed, Oracle can reclaim eligible files according to retention and deletion policies.

Key points:

- Files currently needed for recovery cannot be deleted arbitrarily.
- Backups still required by the retention policy are not obsolete files.
- Archived logs that have not met the archivelog deletion policy are not eligible for deletion under that policy.
- Flashback logs retained for flashback retention or guaranteed restore points can occupy space for extended periods.
- Files marked KEEP or having special retention requirements may not be reclaimable like ordinary backups.

### 5.1. SPACE_USED and SPACE_RECLAIMABLE

V$RECOVERY_FILE_DEST provides overview metrics:

| Column | Meaning |
| --- | --- |
| NAME | FRA location |
| SPACE_LIMIT | FRA limit |
| SPACE_USED | Recovery file space currently accounted for in the FRA |
| SPACE_RECLAIMABLE | Space Oracle estimates can be reclaimed |
| NUMBER_OF_FILES | Number of files in the FRA |

SPACE_RECLAIMABLE is an estimate based on current state/policies, not a guarantee that every byte will be freed immediately. Also review file types, RMAN policies, Data Guard, and restore points.

### 5.2. Checking Total Capacity

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files,
       ROUND(space_used / NULLIF(space_limit, 0) * 100, 2)
           AS pct_used,
       ROUND(space_reclaimable / NULLIF(space_limit, 0) * 100, 2)
           AS pct_reclaimable
FROM v$recovery_file_dest;
~~~

Illustrative example:

| Metric | Value |
| --- | ---: |
| SPACE_LIMIT | 200 GB |
| SPACE_USED | 185 GB |
| SPACE_RECLAIMABLE | 30 GB |
| PCT_USED | 92.5% |
| PCT_RECLAIMABLE | 15% |

Do not add SPACE_USED and SPACE_RECLAIMABLE together; the reclaimable portion is a subset of the used space, not an additional space pool.

### 5.3. Checking by File Type

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

File groups may include:

- CONTROL FILE.
- REDO LOG.
- ARCHIVED LOG.
- BACKUP PIECE.
- IMAGE COPY.
- FLASHBACK LOG.
- FOREIGN ARCHIVED LOG.

Group names and metrics depend on existing file types. This view helps determine which file type consumes the most space and which portion is potentially reclaimable.

### 5.4. FRA Space Differs from Storage Space

Monitor all of the following simultaneously:

1. FRA quota (SPACE_LIMIT).
2. FRA usage (SPACE_USED).
3. Reclaimable space (SPACE_RECLAIMABLE).
4. Actual free space on the filesystem or ASM.
5. Usage of the disk group or mount point if shared with other workloads.

For ASM:

~~~sql
SELECT name,
       total_mb,
       free_mb,
       usable_file_mb
FROM v$asm_diskgroup_stat;
~~~

This view requires appropriate privileges and is typically queried in ASM environments. USABLE_FILE_MB reflects usable space after accounting for disk group redundancy; do not look solely at FREE_MB to conclude how many more files can fit.

## 6. Retention Policy and Archived Log Deletion Policy

These two policies are frequently confused.

### 6.1. RMAN Retention Policy

The retention policy defines which backups remain necessary to meet recovery objectives.

Two common forms:

- REDUNDANCY n: retain the number of backups required by the configured redundancy level.
- RECOVERY WINDOW OF n DAYS: retain backups required to recover to any point within an n-day window.

Example:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
~~~

Or:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

The two policies are different ways of expressing retention objectives. Only one active retention policy applies; do not treat the two examples as automatically stacking layers.

### 6.2. REPORT OBSOLETE and DELETE OBSOLETE

View backups no longer needed per the retention policy:

~~~text
RMAN> REPORT OBSOLETE;
~~~

After confirmation:

~~~text
RMAN> DELETE OBSOLETE;
~~~

DELETE OBSOLETE removes backups/copies that RMAN determines are no longer needed under the retention policy. It is not a substitute for configuring an archived log deletion policy.

### 6.3. Archived Log Deletion Policy

The archived log deletion policy determines when archived redo logs become eligible for deletion by RMAN and FRA space management mechanisms.

Example allowing archived log deletion only after being backed up at least once to disk:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO BACKED UP 1 TIMES TO DEVICE TYPE DISK;
~~~

If backing up to tape/SBT:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO BACKED UP 1 TIMES TO DEVICE TYPE SBT;
~~~

The chosen device type must match the actual backup architecture. Do not configure a BACKED UP TO SBT policy if there is no process backing up archived logs to SBT.

### 6.4. Data Guard and the Applied Condition

In Data Guard environments, the primary may need to retain archived logs until standbys have received or applied the logs per operational requirements.

Example configuration requiring logs to be applied on all standbys:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO APPLIED ON ALL STANDBY;
~~~

The actual condition must match your topology, database roles, which standbys are mandatory to protect, and operational policy. If a standby lags or loses connectivity, logs may continue to be retained and FRA usage will grow.

Do not blindly apply an APPLIED ON ALL STANDBY template if there are optional standbys, temporarily stopped standbys, or cascaded architectures with different deletion requirements. Consult RMAN documentation and your Data Guard design before choosing.

### 6.5. Backing Up Archived Logs and DELETE INPUT

A common task:

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

RMAN backs up the archived logs and then deletes the backed-up input copies according to DELETE INPUT semantics and the deletion policy.

If an archived log has multiple copies across archive destinations:

- DELETE INPUT deletes the input copy that was backed up.
- DELETE ALL INPUT requests deleting all input copies of the backed-up archived logs, subject to applicable conditions and policies.

DELETE ALL INPUT has a broader impact. Use it only after confirming that all copies are no longer needed for recovery/standby and that the policy protects your requirements properly.

### 6.6. Retention Policy Is Not Deletion Policy

| Configuration | Question Answered |
| --- | --- |
| RMAN retention policy | Which backups are still required to satisfy the recovery window/redundancy? |
| Archivelog deletion policy | Are archived logs eligible for deletion yet, e.g., backed up or applied on standby? |
| Flashback retention target | Over what time range does Oracle attempt to maintain flashback capability? |
| Guaranteed restore point | Flashback logs that must be retained to guarantee flashback to that restore point |

A backup may be obsolete while related archived logs are still needed by a standby. Conversely, archived logs may already be backed up while the database backup must still be retained per the retention policy. Evaluate each policy against recovery objectives.

## 7. Common RMAN Commands for Managing the FRA

### 7.1. Viewing Configuration

~~~text
RMAN> SHOW ALL;
~~~

Pay attention to:

- RETENTION POLICY.
- ARCHIVELOG DELETION POLICY.
- CONTROLFILE AUTOBACKUP.
- DEFAULT DEVICE TYPE.
- CHANNEL configuration.
- BACKUP OPTIMIZATION.

### 7.2. Listing Backups and Archived Logs

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
RMAN> LIST ARCHIVELOG ALL;
~~~

These commands help identify backup sets, archived logs, and repository status.

### 7.3. Crosscheck

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK reconciles records in the RMAN repository with physical files that are actually accessible. Files that no longer exist or cannot be found may be marked EXPIRED.

CROSSCHECK does not delete valid files occupying space. Nor does it automatically back up missing files.

### 7.4. Delete Expired

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

DELETE EXPIRED removes expired records from the repository after RMAN confirms the files are no longer present. This command generally does not free disk space for files still sitting on storage, because expired files are files RMAN cannot find.

### 7.5. Delete Obsolete

~~~text
RMAN> REPORT OBSOLETE;
RMAN> DELETE OBSOLETE;
~~~

Delete only after reviewing the list and confirming the retention policy aligns with recovery goals.

### 7.6. Backing Up Database and Archived Logs

Example:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

This command illustrates backing up the database along with archived logs. An actual backup schedule must be designed around RPO, RTO, capacity, throughput, incremental strategy, and backup storage location.

Periodic archived log backup:

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

Before using DELETE INPUT, confirm the backup finished, the device type is right, the deletion policy is appropriate, and standby has received/applied logs as required.

### 7.7. Do Not Substitute OS Delete for RMAN

Do not delete files inside the FRA using rm, del, or file manager operations. Deleting outside RMAN can leave the control file/RMAN repository believing the files still exist, making backup/recovery harder to control and leaving stale records.

Use RMAN to manage backups and archived logs. If a file must be handled with storage tools in an exceptional situation, follow a DBA-approved procedure and synchronize metadata/repository per Oracle documentation.

## 8. Flashback Logs and Restore Points Retaining FRA Space

### 8.1. Flashback Database

Flashback Database uses flashback logs to rewind the database to an earlier point in time without restoring all datafiles and applying all archived redo logs as in traditional media recovery.

Related components:

- DB_FLASHBACK_RETENTION_TARGET: flashback retention target in minutes.
- Flashback logs: store information needed for Flashback Database.
- FRA: where Oracle stores flashback logs when configured via the FRA mechanism.

Check:

~~~sql
SHOW PARAMETER db_flashback_retention_target;

SELECT flashback_on,
       log_mode
FROM v$database;
~~~

DB_FLASHBACK_RETENTION_TARGET is a target, not a guarantee that Oracle will always keep that exact number of minutes. Actual capability depends on flashback log generation rate and FRA space.

### 8.2. Guaranteed Restore Points

A guaranteed restore point ensures the database can flash back to that restore point, provided operational conditions and required files remain intact. Oracle must retain the flashback logs required for the guaranteed restore point; therefore, restore points can prevent the FRA from reclaiming substantial space.

Check:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time;
~~~

Look for restore points with:

~~~text
GUARANTEE_FLASHBACK_DATABASE = YES
~~~

If a guaranteed restore point was created for an upgrade, migration, or major change, there must be a clear owner and end time. When rollback capability is no longer needed, the DBA can drop the restore point following an approved procedure:

~~~sql
DROP RESTORE POINT before_upgrade;
~~~

Do not drop a guaranteed restore point solely to reclaim space before confirming the system has passed the rollback window.

### 8.3. Checking Flashback Log Usage

~~~sql
SELECT oldest_flashback_scn,
       oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
FROM v$flashback_database_log;
~~~

These columns show the oldest flashback log age, retention target, current size, and estimated size. Values vary with workload and Flashback Database state.

### 8.4. Flashback Logs and Archived Logs Are Different File Types

Deleting archived logs does not free flashback logs. If FLASHBACK LOG consumes most of the FRA, investigate the retention target, guaranteed restore points, and flashback-generating workload.

Similarly, lowering DB_FLASHBACK_RETENTION_TARGET does not mean flashback logs are deleted immediately; Oracle must evaluate reclaimability and restore point requirements.

## 9. Control File Autobackups and Other Recovery Files

RMAN can automatically back up the control file and SPFILE after backups or structural database changes if control file autobackup is enabled:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Control file autobackups are vital when recovering a control file or rebuilding a database. Do not delete them just because they are small or old.

Check configuration:

~~~text
RMAN> SHOW CONTROLFILE AUTOBACKUP;
~~~

The FRA can hold backup pieces, image copies, control files, SPFILEs, flashback logs, and archived logs. When diagnosing a full FRA, always break down usage by file type before deleting anything.

## 10. Monitoring the FRA and Archive Destinations

### 10.1. FRA Dashboard

~~~sql
SELECT name,
       ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
       ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
       ROUND(space_reclaimable / 1024 / 1024 / 1024, 2)
           AS reclaimable_gb,
       ROUND(
           space_used / NULLIF(space_limit, 0) * 100,
           2
       ) AS pct_used,
       number_of_files
FROM v$recovery_file_dest;
~~~

Tracking trends over time matters more than a single point-in-time snapshot. If the FRA grows steadily every day without files being reclaimed, find which policy or workload is holding the files.

### 10.2. File Breakdown

~~~sql
SELECT file_type,
       ROUND(percent_space_used, 2) AS pct_used,
       ROUND(percent_space_reclaimable, 2) AS pct_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

If ARCHIVED LOG occupies the majority, investigate backups and Data Guard. If FLASHBACK LOG dominates, check flashback retention/restore points. If BACKUP PIECE consumes a lot, check RMAN retention and backup schedules.

### 10.3. Checking Archive Destinations

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

ERROR may contain the latest error associated with the destination. Check STATUS, TARGET, and DESTINATION as well; do not look at only one destination.

### 10.4. Archive Destination Status

~~~sql
SELECT dest_id,
       status,
       type,
       database_mode,
       recovery_mode,
       destination,
       archived_thread#,
       archived_seq#,
       applied_thread#,
       applied_seq#,
       error
FROM v$archive_dest_status
ORDER BY dest_id;
~~~

Some columns may be NULL or not meaningful for local destinations. For remote standbys, compare archived and applied sequences by thread along with transport/apply status.

### 10.5. Data Guard Lag

On the standby, you can check:

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

Increasing lag can prevent archived logs from becoming eligible for deletion under an APPLIED ON STANDBY policy. Investigate network, redo transport, managed recovery process, and apply errors.

### 10.6. Alert Log

Search for FRA and archive warnings:

~~~sql
SELECT originating_timestamp,
       message_text
FROM v$diag_alert_ext
WHERE originating_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
  AND (
      message_text LIKE '%ORA-198%'
      OR message_text LIKE '%ORA-00257%'
      OR message_text LIKE '%ORA-160%'
  )
ORDER BY originating_timestamp DESC;
~~~

This view requires appropriate privileges. You can use ADRCI or management tools to read the alert log if the account lacks query access to the view.

## 11. FRA Space Pressure: Symptoms and Causes

### 11.1. Common Errors

| Error Code | Common Meaning |
| --- | --- |
| ORA-19815 | Warning that FRA usage is nearing/at its configured limit |
| ORA-19809 | Limit exceeded for recovery file destination |
| ORA-19804 | Oracle cannot reclaim required space from the FRA |
| ORA-00257 | Archiver error; archive destination must be resolved before database impact worsens |
| ORA-16014 | Cannot archive log because no suitable/available destination exists |
| ORA-16038 | An online redo log cannot be archived |

Actual messages depend on database state, destinations, FRA quota, and storage space. Read the full alert log and error stack rather than looking only at the first error code.

### 11.2. Common Causes

1. RMAN backup jobs fail or the backup schedule is not running.
2. Archived logs are generated faster than backup/deletion throughput.
3. Archivelog deletion policy requires backups, but logs have not been backed up yet.
4. Data Guard standby has not received or applied redo.
5. Guaranteed restore points are retaining flashback logs.
6. Flashback retention target is large relative to FRA capacity.
7. Backup retention is too long or KEEP backups exist.
8. Multiple copies of archived logs are stored inside the FRA.
9. FRA quota is too small for peak redo and backup overlap.
10. Filesystem/ASM disk group ran out of space even though FRA quota still had headroom.
11. Another archive destination failed, causing archive operations to fail.
12. A bulk DML workload generated abnormally high redo volume.

### 11.3. Why Can a Full FRA Stall Database Progress?

In ARCHIVELOG mode, Oracle must archive an online redo log before reusing it. If archived logs cannot be written because the destination is full or failing, subsequent redo log switches can be blocked. The database may raise archive errors and new transactions may be impacted.

Not every full FRA case halts the database immediately. Impact depends on log groups, archive destinations, switch state, and mandatory/optional configuration. Nevertheless, it must be treated as a high-priority operational incident.

## 12. Remediation Workflow When the FRA Grows Rapidly or Nears Capacity

### Step 1. Verify Quota and Actual Storage

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

Cross-check filesystem/ASM space. Determine whether the issue is the FRA quota or physical storage.

### Step 2. Identify Which File Type Consumes the Most Space

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

Do not delete files before knowing which category they belong to and which policy is retaining them.

### Step 3. Check RMAN Configuration and Recent Jobs

~~~text
RMAN> SHOW ALL;
RMAN> REPORT OBSOLETE;
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

Check scheduler/backup logs to determine whether backups failed, hung, or cannot keep pace with archived log generation.

### Step 4. Check Archive Destinations

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error
FROM v$archive_dest
WHERE status <> 'INACTIVE';
~~~

If a destination is in error, fix the storage/network/permission root cause rather than merely raising the quota.

### Step 5. Check Data Guard

On primary and standby, inspect transport/apply lag, missing sequences, and managed recovery. If the deletion policy waits for APPLIED ON STANDBY, unapplied logs are a valid reason for Oracle to keep the files.

### Step 6. Check Guaranteed Restore Points and Flashback

~~~sql
SELECT name,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time;
~~~

If a restore point is still needed for rollback, keep it. If the change window is complete and the system owner confirms rollback is no longer needed, drop it per procedure.

### Step 7. Reclaim Obsolete Backups with RMAN

~~~text
RMAN> REPORT OBSOLETE;
~~~

After verifying the retention policy:

~~~text
RMAN> DELETE OBSOLETE;
~~~

Do not skip the REPORT step. If the retention policy is misconfigured, DELETE OBSOLETE can delete backups required for recovery objectives.

### Step 8. Back Up Archived Logs and Delete Eligible Inputs

If logs have not been backed up yet:

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

Execute only when the backup destination is healthy, the backup completes, and the archivelog deletion policy is appropriate. In Data Guard, ensure logs are applied as required.

### Step 9. Crosscheck When the Repository Has Stale Records

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

This synchronizes the repository with physical files. It is not a substitute for backups and does not delete valid files occupying space.

### Step 10. Increase FRA Quota or Expand Storage When Needed

If workload and retention are valid, quota is too small, and underlying storage still has free capacity:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 300G
SCOPE = BOTH;
~~~

If physical storage is insufficient, expand the filesystem/ASM per infrastructure procedures prior to or alongside increasing the quota. Never set the quota beyond actual storage capacity.

### Step 11. Monitor After Remediation

Re-run queries for FRA usage, file type breakdown, archive destinations, and the alert log. Confirm:

- FRA usage decreases or grows at the expected rate.
- Archive destinations return to valid state.
- New archived logs continue archiving cleanly.
- Backup jobs succeed.
- Standby continues receiving/applying redo.
- No new recovery errors appear.

## 13. Dangerous Actions to Avoid

### 13.1. Do Not Delete Archived Logs via the OS

Do not use rm or del to remove archived log files inside the FRA. Doing so can desynchronize the RMAN repository from actual files. If files were already lost outside RMAN, run crosscheck and assess recovery impact.

### 13.2. Do Not Delete All Archived Logs Just to Free Space

Archived logs may be the only way to recover a backup to a needed point in time or let a standby catch up with the primary. Never run bulk deletions without verifying backups, retention, and Data Guard.

### 13.3. Do Not Use DELETE FORCE as a Default Firefighting Measure

FORCE can bypass normal checks/policies. Use it only when the DBA fully understands the files, recovery requirements, and repository impact. Never put FORCE into a cron/scheduled job just to keep the FRA empty.

### 13.4. Do Not Disable ARCHIVELOG to Bypass FRA Errors

Switching to NOARCHIVELOG alters recovery capability. It is not a standard space-management method and may require taking a new consistent backup afterward.

### 13.5. Do Not Drop Guaranteed Restore Points Arbitrarily

A guaranteed restore point may be the only rollback option for a major change. Dropping it before confirming completion can eliminate the ability to return to the prior state.

### 13.6. Do Not Cut Retention Just Because a Chart Is Red

Reducing retention can forfeit the ability to recover to points required by the business. Before changing it, review RPO, RTO, audit requirements, off-FRA backups, and Data Guard capabilities.

## 14. Capacity Planning for the FRA

The FRA needs enough space for recovery files during peak loads and overlap windows between backups. Do not simply multiply database size by a fixed factor.

### 14.1. Components to Estimate

1. Archived redo logs generated during peak periods.
2. Time archived logs must be retained before backup/apply makes them eligible for deletion.
3. Full/incremental backup sizes and number of overlapping backup sets.
4. Flashback log generation based on workload and retention target.
5. Existing guaranteed restore points.
6. Image copies/datafile copies and control file/SPFILE autobackups.
7. Space needed by concurrently running backup operations.
8. Headroom for large batches, index rebuilds, bulk loads, or standby outages.

### 14.2. Initial Estimation Model

~~~text
FRA capacity
  >= archived redo required during retention/backup lag
   + backup pieces retained in FRA
   + flashback logs retained
   + guaranteed restore point requirement
   + image copies and control-file backups
   + concurrent backup/maintenance overlap
   + operational safety margin
~~~

Components may interact. For example, archived logs already backed up and eligible for deletion do not need to be added separately across the entire retention window as an extra permanent copy. Model according to actual lifecycles rather than double-counting.

### 14.3. Estimating Archived Logs

If redo/archive averages 80 GB/day and logs may need to be kept for 2.5 days before backups and standby apply complete:

~~~text
80 GB/day × 2.5 days = 200 GB
~~~

This covers only expected archived logs during that window. Use daily/hourly peaks and seasonal highs instead of relying solely on long-term averages.

### 14.4. Estimating Flashback

Flashback log generation depends on data modification rates, workload, and retention time. Use actual numbers from V$FLASHBACK_DATABASE_LOG, FRA usage, and monitoring during high-load periods.

Guaranteed restore points can significantly increase retained flashback log volume. Factor restore point lifetime into capacity planning.

### 14.5. Headroom

Do not design the FRA to run continuously near 100%. Maintain buffer capacity for:

- Bulk DML surges.
- Large full or incremental backups.
- Temporary standby disconnects.
- Slow backup destinations.
- DBA incident response time.

Alert thresholds should sit well below the point where archiving could stall. Depending on the system, alert on FRA percentage, GB/hour growth rate, and estimated hours until full.

### 14.6. Trend Monitoring

Periodically record:

- SPACE_LIMIT.
- SPACE_USED.
- SPACE_RECLAIMABLE.
- File type usage.
- Archived log generation per hour/day.
- RMAN backup duration and throughput.
- Data Guard transport/apply lag.
- Flashback log size and restore point age.

An FRA at 70% utilization growing at 10% per hour is more dangerous than an FRA steady at 90% with genuine reclaimable space.

## 15. Operational Design Example

Suppose an OLTP database:

- Runs in ARCHIVELOG mode.
- Has a primary and a physical standby.
- Runs daily database backups.
- Backs up archived logs hourly.
- Requires standby to apply redo before logs are deleted.
- Has Flashback Database enabled with a 24-hour target.

A policy configuration might include:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 500G
SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '+RECO'
SCOPE = BOTH;

ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=USE_DB_RECOVERY_FILE_DEST'
SCOPE = BOTH;

ALTER SYSTEM SET DB_FLASHBACK_RETENTION_TARGET = 1440
SCOPE = BOTH;
~~~

In RMAN:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY TO APPLIED ON ALL STANDBY;
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Backup jobs:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

This example illustrates how components fit together, not a template to apply verbatim to every system. If database backups reside in the FRA, factor backup pieces into the quota. If there are multiple standbys, optional standbys, or SBT backups, design the deletion policy to match the topology.

## 16. FRA and Archived Log Operations Checklist

1. **Is the FRA configured properly?** Check DB_RECOVERY_FILE_DEST and DB_RECOVERY_FILE_DEST_SIZE.
2. **Does the quota fit physical storage?** Cross-check filesystem/ASM usable capacity.
3. **Are archived logs going into the FRA?** Check LOG_ARCHIVE_DEST_n and USE_DB_RECOVERY_FILE_DEST.
4. **Is the database in ARCHIVELOG mode?** Check V$DATABASE.
5. **Which file type is growing the FRA?** Inspect V$FLASH_RECOVERY_AREA_USAGE.
6. **Are there reclaimable files?** Check SPACE_RECLAIMABLE, without treating it as a guarantee.
7. **Does the RMAN retention policy match RPO/RTO?** Check SHOW ALL and REPORT OBSOLETE.
8. **Is the archived log deletion policy correct?** Verify backup count/device and Data Guard apply requirements.
9. **Are backup jobs running reliably?** Check logs, duration, throughput, and errors.
10. **Is the standby lagging?** Check V$ARCHIVE_DEST_STATUS and V$DATAGUARD_STATS.
11. **Are there guaranteed restore points?** Check V$RESTORE_POINT.
12. **Are flashback logs consuming excessive space?** Check V$FLASHBACK_DATABASE_LOG.
13. **Is control file autobackup enabled?** Check RMAN SHOW ALL.
14. **Does the repository have stale records?** Run CROSSCHECK and handle EXPIRED items.
15. **Are there obsolete backups?** Run REPORT OBSOLETE before DELETE OBSOLETE.
16. **Are backed-up archive logs eligible for deletion?** Verify deletion policy before DELETE INPUT.
17. **Are files ever deleted outside RMAN?** Avoid direct filesystem operations on the FRA.
18. **Is there headroom for peak workloads?** Monitor GB/hour growth and hours remaining until full.
19. **Are backups stored outside the failure domain?** The FRA does not replace off-host/off-site backups.
20. **Has restore capability been tested?** Backups only have value when restore/recovery procedures are tested.

## 17. Self-Check Questions

**Question 1.** What is the Fast Recovery Area and what file types can it hold?

**Question 2.** How does DB_RECOVERY_FILE_DEST differ from DB_RECOVERY_FILE_DEST_SIZE?

**Question 3.** Why is DB_RECOVERY_FILE_DEST_SIZE not physical capacity?

**Question 4.** Does configuring an FRA automatically route all archived logs into it?

**Question 5.** How does ARCHIVELOG mode differ from the FRA?

**Question 6.** Why can a full archive destination affect redo log reuse?

**Question 7.** Which metrics does V$RECOVERY_FILE_DEST provide?

**Question 8.** Is SPACE_RECLAIMABLE guaranteed to be freed immediately?

**Question 9.** What is V$FLASH_RECOVERY_AREA_USAGE used for?

**Question 10.** How do the RMAN retention policy and archivelog deletion policy differ?

**Question 11.** What does REPORT OBSOLETE do?

**Question 12.** How does CROSSCHECK differ from DELETE EXPIRED?

**Question 13.** How does DELETE INPUT differ from DELETE ALL INPUT?

**Question 14.** Why can Data Guard standby lag cause archived logs to accumulate?

**Question 15.** How do guaranteed restore points affect the FRA?

**Question 16.** Does DB_FLASHBACK_RETENTION_TARGET guarantee retaining the full duration?

**Question 17.** Why should you avoid deleting FRA files using OS commands?

**Question 18.** What situations do ORA-19809 and ORA-19804 typically indicate?

**Question 19.** Why doesn't raising the FRA quota solve the issue when ASM is already full?

**Question 20.** Which components must be factored into FRA capacity planning?

<details>
<summary>Answer Hints</summary>

1. An Oracle-managed area for backup/recovery that can hold archived logs, backup pieces, image copies, flashback logs, control file/SPFILE autobackups, and other recovery files.
2. DEST is the location; DEST_SIZE is the quota.
3. It caps Oracle's managed allocation; it does not add filesystem/ASM capacity.
4. No. An archive destination must be configured to use the FRA, e.g., LOCATION=USE_DB_RECOVERY_FILE_DEST.
5. ARCHIVELOG is the mode for writing archived redo; FRA is a storage area for recovery files.
6. Online redo logs must be archived before reuse; archive failures can block log switches/reuse.
7. Name, space limit, used, reclaimable, and number of files.
8. No. It is an estimate based on current policies/state.
9. Breaks down space used and reclaimable space by file type.
10. Retention policy defines which backups are still needed; deletion policy defines when archived logs are eligible for deletion.
11. Lists backups/copies that are obsolete under the retention policy.
12. CROSSCHECK reconciles the repository with actual files; DELETE EXPIRED removes records already identified as expired.
13. DELETE INPUT deletes the backed-up input copy; DELETE ALL INPUT deletes all input copies of backed-up logs subject to applicable conditions.
14. The policy may require logs to be applied before deletion; a slow standby keeps logs retained.
15. Retains the flashback logs required to guarantee flashback to the restore point, reducing reclaimable space.
16. No. It is a target; actual retention depends on workload and available space.
17. The repository can become out of sync with actual files, complicating backup/recovery.
18. ORA-19809 indicates the recovery destination size limit was exceeded; ORA-19804 indicates Oracle could not reclaim needed space.
19. Because raising a quota does not create additional physical storage capacity.
20. Archived redo, backup retention/overlap, flashback, restore points, image copies, control file backups, and a safety margin.

</details>

## 18. Official Oracle Documentation

1. [Oracle Database 19c Backup and Recovery User's Guide — Managing the Fast Recovery Area](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/): FRA configuration, space management, and recovery files.
2. [Oracle Database 19c Backup and Recovery User's Guide — Configuring the Recovery Area](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/configuring-rman-client-basic.html): RMAN and recovery area configuration components.
3. [Oracle Database 19c Reference — DB_RECOVERY_FILE_DEST](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DB_RECOVERY_FILE_DEST.html): FRA location parameter.
4. [Oracle Database 19c Reference — DB_RECOVERY_FILE_DEST_SIZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DB_RECOVERY_FILE_DEST_SIZE.html): FRA size limit.
5. [Oracle Database 19c Reference — V$RECOVERY_FILE_DEST](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RECOVERY_FILE_DEST.html): total FRA capacity.
6. [Oracle Database 19c Reference — V$FLASH_RECOVERY_AREA_USAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-FLASH_RECOVERY_AREA_USAGE.html): space usage by file type.
7. [Oracle Database 19c Backup and Recovery User's Guide — Archived Redo Log Deletion Policy](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/configuring-rman-client-basic.html): retention/deletion policy configuration and archived log management.
8. [Oracle Database 19c Backup and Recovery Reference — BACKUP](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/BACKUP.html): backing up databases and archived redo logs.
9. [Oracle Database 19c Backup and Recovery Reference — DELETE](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/DELETE.html): DELETE OBSOLETE, EXPIRED, and archived logs.
10. [Oracle Database 19c Backup and Recovery User's Guide — Flashback Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/using-flasback-database-restore-points.html): flashback logs and restore points.
11. [Oracle Database 19c Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/): redo transport, apply, and standby operations.
12. [Oracle Database 19c Reference — V$ARCHIVED_LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ARCHIVED_LOG.html): archived redo log details.
13. [Oracle Database 19c Reference — V$ARCHIVE_DEST_STATUS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ARCHIVE_DEST_STATUS.html): archive destination status.

**Principle to remember:** The FRA is an Oracle-managed area for recovery files; DB_RECOVERY_FILE_DEST_SIZE is a quota rather than physical capacity. Archived logs should only be deleted once backup, recovery retention, and Data Guard requirements are satisfied. Flashback logs and guaranteed restore points can also hold space long term. When the FRA comes under pressure, classify files, inspect RMAN policies, archive destinations, standby lag, and restore points before reclaiming space or increasing the quota. Never delete FRA files via the operating system, and always keep backups in an independent failure domain.
