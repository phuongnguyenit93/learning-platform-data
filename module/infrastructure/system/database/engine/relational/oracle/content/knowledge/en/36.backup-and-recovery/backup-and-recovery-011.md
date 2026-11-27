# Complete Recovery After Losing a Datafile or Storage Volume

When a datafile is lost, a disk holding datafiles fails, or a storage volume becomes inaccessible, Oracle Database may be unable to read part of the data required to operate. To return the database to a consistent state, the DBA must identify the damage scope, restore files from backups, and apply the necessary redo.

**Complete recovery** is the process of restoring files and applying redo changes to bring a file or database forward to the current point in time where all required redo remains intact. The goal is to preserve all committed transactions up to recovery completion, rather than intentionally rolling the database back to an older point. If a required redo segment is missing and no alternate backup/redo source exists, complete recovery cannot proceed across that gap; in that case, the DBA must consider incomplete recovery or another recovery strategy.

In Oracle, RMAN is the primary tool for restoring backups and recovering datafiles/databases. However, RMAN does not substitute for understanding file architecture, redo, control files, ASM, and instance state. The same "file inaccessible" error message can stem from a deleted datafile, a lost ASM disk group, a full filesystem, changed permissions, I/O faults, or block corruption. The right sequence of actions depends on which files are affected and what state the database is in.

## 1. Distinguishing Restore, Recovery, and Complete Recovery

Three terms frequently appear together but carry distinct meanings:

- **Restore:** retrieving a copy of a file from backup and placing it back into storage. A newly restored file typically contains data at an older SCN than the current database.
- **Recover:** applying redo (archived redo logs and potentially online redo logs) to the restored file or files needing synchronization, advancing them to the required SCN.
- **Open:** opening the database or bringing a datafile/tablespace back online once recovery completes and consistency requirements are satisfied.

High-level flow:

```text
Detect damaged/missing file
        |
        v
Identify file, tablespace, database state
        |
        v
Ensure storage/target path is ready
        |
        v
RESTORE from backup
        |
        v
RECOVER: apply required archived/online redo
        |
        v
Verify status and consistency
        |
        v
ONLINE file/tablespace or OPEN database
```

Restoring alone does not make a database consistent with its remaining files. A datafile restored from backup may carry an older checkpoint SCN. Recovery brings that file up to date with required changes.

### 1.1. Complete Recovery vs. Incomplete Recovery

| Characteristic | Complete Recovery | Incomplete Recovery |
|---|---|---|
| Goal | Recover to the present or the latest point where complete redo applies | Stop at a chosen past point in time, SCN, or log sequence |
| Redo | Requires an unbroken redo chain from backup to the recovery point | Requires redo up to the chosen stopping point |
| Data committed after stop point | Preserved if redo is complete and recovery reaches present | Absent from the database after reopening at the earlier point |
| Opening the database | Normally regular open when using current control file and complete recovery finishes | Typically requires `OPEN RESETLOGS` after incomplete recovery |
| Scenario | Datafile lost while complete backups and redo exist | Logical corruption, accidental deletion, or missing redo requiring rollback before incident |

Complete recovery does not mean "restore the latest backup and open the database." Even the newest backup can still be older than the time of the failure. Redo must be applied from the backup's checkpoint up to the target recovery point.

### 1.2. SCN and the Role of Redo

SCN (System Change Number) is the logical change sequence number managed by Oracle. Datafile headers store checkpoint SCNs and metadata needed to identify the file's state. The control file stores metadata on the database, datafiles, redo logs, and checkpoints. Redo logs record changes required to recover the database.

When a datafile is restored from backup, its header may record an older SCN. Oracle requires redo to advance the file to an SCN compatible with the database and sibling files. If a needed archived redo log has no surviving copy, recovery stops at that log.

A backup created while the database is open can be a fuzzy backup: datafiles were not necessarily copied at the exact same logical point in time. That does not make the backup unusable. RMAN tracks backup metadata, and recovery applies redo to bring all files to a consistent state.

## 2. Components Required for Complete Recovery

To recover a datafile or the entire database, understand the role of each component:

| Component | Role in Recovery |
|---|---|
| Datafile backup | Provides the baseline data copy to restore |
| Incremental backup | Can shorten the amount of redo to apply or update a datafile copy depending on backup strategy |
| Archived redo log | Stores archived redo needed to roll forward across corresponding log sequences |
| Online redo log | Contains most recent unarchived redo; may be needed in certain scenarios to recover to the present |
| Control file | Stores database structure, filenames, checkpoints, log history, and backup info if using control-file repository |
| SPFILE/PFILE | Supplies parameters to start the instance, including control file paths and essential settings |
| RMAN repository | Tracks backups, archived logs, datafiles, and recovery metadata |
| Storage/ASM/filesystem | Must be ready to receive restored files and provide Oracle access |

RMAN can obtain metadata from the control file or a recovery catalog. A recovery catalog is a centralized repository schema useful when managing multiple databases or retaining longer history than the control file. If the control file is lost, the recovery catalog helps retrieve metadata, though you still need a control file copy or autobackup and database identifiers.

### 2.1. Critical Requirement: ARCHIVELOG and Complete Redo

Complete media recovery of a datafile typically requires the database to be in `ARCHIVELOG` mode, along with suitable backups and all required redo. In `NOARCHIVELOG` mode, online redo is overwritten after log switches and no complete archived log chain exists to roll forward arbitrarily. In that case, the normal option is restoring the entire database from a consistent backup created while cleanly closed; you cannot rely on archived redo to complete media recovery to the present.

Check archive mode:

```sql
SELECT log_mode,
       open_mode,
       database_role
FROM v$database;
```

Check archive destinations and archival status per environment settings. Do not glance at a single archive directory and assume redo is complete; log sequences might reside in the FRA, ASM, backup pieces, or another backup device.

### 2.2. Backups Must Not Reside Solely on the Storage Being Protected

If all datafiles, control files, archived logs, and backups sit on the same disk group or storage array, losing that storage destroys both data and recoverability. A backup strategy requires copies in a separate failure domain—such as independent storage, backup appliances, or offsite locations per organizational policy.

ASM mirroring, RAID, replication, and snapshots improve fault tolerance, but do not replace independent backups. An accidental deletion, logical error, or cascading fault can propagate across synchronous mirrors.

## 3. Determining Incident Scope Before Restoring

Before running restore/recover commands, answer:

1. Which files are inaccessible: one datafile, multiple datafiles, the control file, online redo logs, a tempfile, or an entire disk group?
2. Which tablespace do the files belong to? Is it `SYSTEM`, `SYSAUX`, an undo tablespace, or an application tablespace?
3. Is the database `OPEN`, `MOUNT`, or `NOMOUNT`?
4. Can the datafile be taken offline individually, or must the database be shut down?
5. Does the original file still exist with I/O errors, or was the file deleted / device completely lost?
6. Which backups are usable and which redo sequences remain available?
7. Has target storage been repaired, recreated, or properly mounted?
8. Is there a standby database or storage copy that can assist?

### 3.1. Identifying Datafiles and Tablespaces

Commonly used views:

```sql
SELECT d.file#,
       d.name,
       d.status,
       d.enabled,
       t.name AS tablespace_name
FROM v$datafile d
JOIN v$tablespace t
  ON t.ts# = d.ts#
ORDER BY d.file#;
```

Check headers and recovery status:

```sql
SELECT file#,
       status,
       error,
       recover,
       fuzzy,
       checkpoint_change#,
       name
FROM v$datafile_header
ORDER BY file#;
```

```sql
SELECT file#,
       online_status,
       error,
       change#,
       time
FROM v$recover_file
ORDER BY file#;
```

These views indicate which files need recovery or have unreadable headers. If the instance cannot mount, some views cannot be queried; rely on the alert log, RMAN output, control file backups, storage diagnostics, and backup metadata.

### 3.2. Distinguishing Datafiles from Tempfiles

Tempfiles hold temporary data for sorts, hash joins, and other operations. Tempfiles are not recovered with archived redo like permanent datafiles. If a tempfile is lost, the DBA can normally recreate the tempfile or add a new tempfile to the temporary tablespace per standard procedure.

Example adding a tempfile:

```sql
ALTER TABLESPACE temp
  ADD TEMPFILE '/u02/oradata/DB1/temp02.dbf'
  SIZE 2G AUTOEXTEND ON NEXT 256M MAXSIZE 20G;
```

Path, size, and autoextend settings are examples only. Use real storage paths and sizing policies. Never run `RESTORE DATAFILE` on a tempfile as though it were a permanent datafile.

### 3.3. Checking Backups and Archived Redo with RMAN

Connect to RMAN:

```text
rman target /
```

Check schema and backups:

```rman
REPORT SCHEMA;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST ARCHIVELOG ALL;
```

Check a specific file:

```rman
LIST BACKUP OF DATAFILE 7;
LIST BACKUP OF ARCHIVELOG FROM SEQUENCE 1200;
```

Replace file numbers, sequences, and paths in examples with actual values from your database. Backups may reside on SBT/tape or other devices, so reconcile `LIST` and repository status against actual device accessibility.

## 4. Losing One Non-SYSTEM Datafile While the Database Remains Open

This is a common scenario: a datafile in an application tablespace is deleted or its storage fails while other critical datafiles remain healthy.

If the database is in `ARCHIVELOG`, the current control file remains usable, and required backups/redo are intact, you can take the affected datafile offline, restore it, and recover just that file. Other tablespaces can remain operational depending on file type, database state, and incident impact.

### 4.1. Example: Losing Datafile 7

Suppose datafile 7 in tablespace `USERS` is lost. Check first:

```sql
SELECT file#,
       name,
       status
FROM v$datafile
WHERE file# = 7;
```

If the database is still open and the datafile can be taken offline individually:

```sql
ALTER DATABASE DATAFILE 7 OFFLINE;
```

Then in RMAN:

```rman
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

Once recovery succeeds, bring the file online:

```sql
ALTER DATABASE DATAFILE 7 ONLINE;
```

If Oracle already marked the datafile offline due to an error or the offline command fails due to file state, check its exact status in the control file and handle accordingly. Never use `OFFLINE FOR DROP` when you intend to recover the file; that option signals intent to drop the file from the database and can compromise file recoverability.

### 4.2. Why Are Both RESTORE and RECOVER Needed?

Suppose the backup of datafile 7 was created at SCN 5,000,000. The database kept running and the datafile was lost at SCN 5,300,000. Restoring brings back the datafile as of SCN 5,000,000. Bringing it online immediately fails because its header does not match the database's current state.

`RECOVER DATAFILE 7` applies the redo needed to advance the file to the matching SCN. If continuous redo up to the present exists, this performs complete recovery of the datafile.

### 4.3. Taking an Entire Tablespace Offline When Needed

In some situations, the DBA may offline the entire tablespace rather than a single datafile:

```sql
ALTER TABLESPACE users OFFLINE IMMEDIATE;
```

Then:

```rman
RESTORE TABLESPACE users;
RECOVER TABLESPACE users;
```

Bring the tablespace online after completion:

```sql
ALTER TABLESPACE users ONLINE;
```

The tablespace-level approach works well when recovering multiple datafiles in the same tablespace or managing the whole tablespace state together. It does not apply to the `SYSTEM` tablespace; `SYSTEM` cannot be taken offline while the database is open.

### 4.4. Restoring a Datafile to a New Location

If the old path is no longer usable, specify a new path before restoring. RMAN example:

```rman
RUN {
  SET NEWNAME FOR DATAFILE 7 TO '/u03/oradata/DB1/users07.dbf';
  RESTORE DATAFILE 7;
  SWITCH DATAFILE 7;
  RECOVER DATAFILE 7;
}
```

`SET NEWNAME` sets the restore destination; `SWITCH DATAFILE` updates the repository/control file so the database uses the new file. The target directory must exist, Oracle must have write permissions, and disk space must suffice.

When using Oracle Managed Files (OMF) or ASM, use naming conventions matching your configuration and release, such as Oracle-generated names. Never mix filesystem paths with ASM aliases haphazardly. After switching, query `V$DATAFILE.NAME` to confirm the database points to the right location.

## 5. Losing a SYSTEM Datafile or Failures Requiring Database Shutdown

Datafiles in `SYSTEM` store the data dictionary needed for the database to operate. You cannot offline a `SYSTEM` datafile individually while the database is open. When this file is lost or severely damaged, the database normally must be shut down and started in `MOUNT` mode to restore/recover.

### 5.1. Sequence for Recovering a SYSTEM Datafile

Suppose datafile 1 belonging to `SYSTEM` is lost while the current control file remains intact and backups/redo are complete:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
```

In RMAN:

```rman
RESTORE DATAFILE 1;
RECOVER DATAFILE 1;
```

Once recovery completes:

```sql
ALTER DATABASE OPEN;
```

With a current control file and complete recovery, `RESETLOGS` is normally unnecessary. If RMAN or Oracle reports other files still need recovery, do not try to force the database open by ignoring errors; recover all required files first.

### 5.2. When Multiple Datafiles or the Entire Database Are Lost

If many datafiles are lost from a storage outage, the database may fail to open or be unable to run safely. In that case, restore and recover the whole database:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
```

```rman
RESTORE DATABASE;
RECOVER DATABASE;
```

After complete recovery succeeds using the current control file:

```sql
ALTER DATABASE OPEN;
```

`RESTORE DATABASE` retrieves required datafiles from backup; `RECOVER DATABASE` applies redo to synchronize them. If only a subset of files was lost, you can restore/recover just the affected files rather than every datafile. Command scope should match the damaged file list and recovery target.

### 5.3. Undo Tablespace Datafiles

Undo datafiles contain undo segments needed for read consistency, transaction rollback, and internal operations. Losing an undo datafile can have wider impact than losing a single application table, especially if the file holds active undo segments.

Do not treat an undo datafile like an ordinary application tablespace without checking active transactions and the active undo tablespace. If the database remains open, evaluate the file/tablespace and undo status; if the failure blocks mounting/opening, perform restore/recovery at the appropriate scope. Avoid dropping or recreating an undo tablespace without checking transactions and dependencies, as doing so can break rollback capability or prevent instance startup.

## 6. Losing an Entire Storage Volume or ASM Disk Group

When storage fails, the outage may affect more than one datafile. For instance, an ASM disk group holding multiple datafiles, control files, and online redo logs may dismount or become inaccessible. Distinguish physical device faults, ASM disk faults, disk group faults, filesystem errors, and path errors.

### 6.1. ASM Redundancy and Failure Groups

ASM can use `EXTERNAL`, `NORMAL`, or `HIGH` redundancy depending on disk group configuration. With `NORMAL`/`HIGH`, ASM maintains mirrored extents across failure groups to tolerate certain disk failures. When one disk fails while the disk group retains sufficient redundancy and surviving failure groups remain healthy, ASM can continue serving data or rebalance after disk replacement.

If the disk group remains online and files are still ASM-protected, the DBA may handle disk failure/rebalance per ASM procedures instead of restoring the entire database. If the entire disk group or all mirror copies are lost, ASM cannot reconstruct data on its own; restore storage and restore from backup.

ASM mirroring does not replace backups. It protects against certain hardware faults per configured redundancy, but does not protect against accidental deletion, logical corruption, software bugs, or cascading failures.

### 6.2. Inspecting Disk Groups

While the ASM instance and privileges remain accessible, inspect disk groups and disks:

```sql
SELECT name,
       state,
       type,
       total_mb,
       free_mb,
       usable_file_mb
FROM v$asm_diskgroup;
```

```sql
SELECT group_number,
       disk_number,
       name,
       path,
       mount_status,
       header_status,
       mode_status,
       state
FROM v$asm_disk
ORDER BY group_number, disk_number;
```

In RAC, query corresponding global views or check the ASM instance on the appropriate node. If the ASM instance will not start or a disk group will not mount, inspect the ASM alert log, OS/storage logs, and device status before attempting mount or recreate operations.

### 6.3. If Only One ASM Disk Fails

If the disk group retains enough redundancy, replace the failed disk and let ASM rebalance. Exact syntax depends on configuration and storage management. Conceptual example:

```sql
ALTER DISKGROUP DATA DROP DISK data_0003;
```

Once the new device is provisioned and visible to ASM:

```sql
ALTER DISKGROUP DATA ADD DISK '/dev/asm/data_new01';
```

These are illustrative examples, not commands to run directly on a live system. Verify exact disk paths, failure groups, redundancy, capacity, and rebalance state. Never drop a disk holding sole unmirrored data. If redundancy is insufficient, dropping a disk can cause data loss.

### 6.4. If a Disk Group Is Completely Lost

If a disk group containing datafiles is completely lost, the general sequence is:

1. Repair hardware or provision new storage.
2. Create/mount the target disk group or filesystem per design.
3. Ensure target directories/ASM destinations and permissions are ready.
4. Restore the control file if the control file was also lost.
5. Mount the database.
6. Catalog backups if the repository no longer recognizes backup pieces.
7. Restore required datafiles to the new storage.
8. Recover using complete archived/online redo.
9. Verify filenames, statuses, alert log, and open the database.

If the lost disk group also held the Fast Recovery Area, archived logs, or backup pieces, those copies may be gone too. Use backups from a separate failure domain. You cannot perform complete recovery simply by recreating an empty disk group; new storage only restores the container, not the data inside it.

## 7. When Control File or SPFILE Recovery Is Needed

Losing the control file differs from losing a datafile. The control file stores database structure and checkpoint/log metadata. If all multiplexed control file copies are lost, the database cannot mount using the current control file. Restore the control file from autobackup or an appropriate backup before restoring/recovering datafiles.

### 7.1. Restoring the Control File from Autobackup

When control file autobackup is enabled and the DBID is known, a typical sequence after losing the control file is:

```sql
STARTUP NOMOUNT;
```

In RMAN:

```rman
SET DBID 1234567890;
RESTORE CONTROLFILE FROM AUTOBACKUP;
```

Then mount the database:

```sql
ALTER DATABASE MOUNT;
```

If backup pieces are not discovered automatically, catalog the backup directory or specify the handle for your environment. After restoring a control file from backup, its repository and file records reflect an older point in time; re-cataloging newer backups/archived logs afterward may be needed.

### 7.2. Recovery Using a Backup Control File

When recovery uses a backup control file, Oracle typically requires opening the database with `RESETLOGS` after recovery finishes, even when redo was applied to the latest possible point. This is a crucial difference from complete recovery using a current control file.

General example:

```rman
RESTORE DATABASE;
RECOVER DATABASE;
```

Once backup control file recovery finishes per Oracle requirements:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

`RESETLOGS` creates a new incarnation and resets log sequences per Oracle mechanics. After opening, verify database/incarnation state and take a full backup per policy. Never run `OPEN RESETLOGS` merely because you saw it in another recovery guide; verify the actual control file type and recovery mode.

### 7.3. Lost SPFILE

If the SPFILE is lost while control files and datafiles remain, start using a matching PFILE or restore the SPFILE from autobackup if available. The SPFILE holds no business data, yet stores critical parameters such as `CONTROL_FILES`, `DB_NAME`, `DB_UNIQUE_NAME`, `DB_RECOVERY_FILE_DEST`, and ASM settings.

If restoring the SPFILE from autobackup, ensure parameters match new storage paths if storage changed. Do not start the database with parameters pointing to nonexistent control files or disk groups.

## 8. Common RMAN Commands in Complete Recovery

### 8.1. Checking and Previewing Restore Operations

```rman
REPORT SCHEMA;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF DATAFILE 7;
LIST ARCHIVELOG ALL;
```

Preview which files/backups RMAN plans to use:

```rman
RESTORE DATABASE PREVIEW;
```

Validate backup readability:

```rman
RESTORE DATABASE VALIDATE;
```

`PREVIEW` inspects backup selection based on the repository and current state. `VALIDATE` checks backup readability without restoring datafiles. Validation passing does not guarantee target storage has enough space or that all runtime issues are eliminated.

### 8.2. Restoring/Recovering a Single Datafile

```rman
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

### 8.3. Restoring/Recovering a Tablespace

```rman
RESTORE TABLESPACE USERS;
RECOVER TABLESPACE USERS;
```

### 8.4. Restoring/Recovering the Entire Database

```rman
RESTORE DATABASE;
RECOVER DATABASE;
```

### 8.5. Recovering When Backup Pieces Are Missing from the Repository

If backup pieces were copied from elsewhere or the repository lacks records, catalog the files into the RMAN repository. Filesystem example:

```rman
CATALOG START WITH '/backup/DB1/' NOPROMPT;
```

Only catalog trusted locations belonging to the right database and valid backup pieces. With SBT/tape, configure the media manager and channels properly. Never accidentally catalog backups from another database.

## 9. Corrupted Redo Logs Are Not the Same as Corrupted Datafiles

Online redo logs hold redo for the most recent transactions. Losing one member of a multiplexed redo log group differs from losing the entire group. If only one member fails while another healthy member remains, handle the bad member per Oracle instructions without restoring datafiles.

If an entire group holding needed redo is lost, recoverability depends on group status, archived logs, and checkpoint timing. Losing the current online redo log can make complete recovery to the present impossible if that log held the sole copy of required changes.

Never respond to redo log errors by restoring a datafile and skipping redo. Datafiles may hold uncommitted transactions or be unsynchronized with sibling files. Inspect the alert log and `V$LOG`, `V$LOGFILE`, and `V$ARCHIVED_LOG` to diagnose accurately.

Example querying redo log groups/members:

```sql
SELECT l.group#,
       l.thread#,
       l.sequence#,
       l.status,
       l.archived,
       f.member
FROM v$log l
JOIN v$logfile f
  ON f.group# = l.group#
ORDER BY l.thread#, l.group#, f.member;
```

Never use `CLEAR UNARCHIVED LOGFILE` as a routine fix. That command can discard redo needed for recovery and force a different recovery strategy. Use it only per Oracle guidance after understanding the impact and accepting data consequences.

## 10. Verifying Archived Redo Availability

Complete recovery requires an unbroken redo chain from the backup checkpoint to the target. One missing archived log can block recovery even if datafile backups are healthy.

Check archived logs:

```sql
SELECT thread#,
       sequence#,
       first_change#,
       next_change#,
       archived,
       deleted,
       status,
       name
FROM v$archived_log
ORDER BY thread#, sequence#;
```

In RAC, check every redo thread. Never inspect only thread 1 sequences when the database has multiple threads. Some archived logs may have multiple copies; confirm at least one copy is readable and known to RMAN.

RMAN can restore archived logs from backup when needed:

```rman
RESTORE ARCHIVELOG FROM SEQUENCE 1200 UNTIL SEQUENCE 1250 THREAD 1;
```

The example illustrates syntax for one thread; adjust sequence/thread for your actual recovery window and database. During `RECOVER`, RMAN can automatically restore archived logs from backups if channels and repository allow.

If a required log sequence is no longer in the archive destination, search archived log backups, standby copies, FRA, tape devices, and other replicas. Never manually skip a missing log and call the result complete recovery.

## 11. Recovering a Datafile to a Different Path When Old Storage Fails

When the original filesystem or disk group is unusable, restoring to a new path is part of the recovery plan. Update metadata so the database references the new file after restore.

### 11.1. Filesystem

Example:

```rman
RUN {
  SET NEWNAME FOR DATAFILE 7 TO '/u03/oradata/DB1/users07.dbf';
  RESTORE DATAFILE 7;
  SWITCH DATAFILE 7;
  RECOVER DATAFILE 7;
}
```

Then verify:

```sql
SELECT file#,
       name,
       status
FROM v$datafile
WHERE file# = 7;
```

### 11.2. ASM/OMF

With ASM, filenames typically look like `+DATA/DB1/DATAFILE/...` or are managed by Oracle Managed Files. When restoring to another disk group, confirm the target disk group is mounted, has enough `usable_file_mb`, and has suitable redundancy.

Conceptual example using an OMF destination:

```rman
RUN {
  SET NEWNAME FOR DATAFILE 7 TO '+DATA2';
  RESTORE DATAFILE 7;
  SWITCH DATAFILE 7;
  RECOVER DATAFILE 7;
}
```

Support for using a disk group name as an OMF destination and exact syntax depend on ASM/OMF configuration, Oracle version, and file state. Verify syntax on your running release before using in production.

## 12. Block Media Recovery When Only Certain Blocks Are Corrupted

Not every corruption requires restoring an entire datafile. If only specific blocks are corrupted and valid backups/redo exist, RMAN supports block media recovery to repair only the affected blocks.

Example:

```rman
RECOVER DATAFILE 7 BLOCK 12345;
```

Multiple blocks can be specified per RMAN syntax. Block media recovery does not replace fixing underlying storage that continues generating errors. If physical storage is unstable, fix storage before or alongside block recovery.

Check corruption using `V$DATABASE_BLOCK_CORRUPTION`:

```sql
SELECT file#,
       block#,
       blocks,
       corruption_type
FROM v$database_block_corruption
ORDER BY file#, block#;
```

RMAN can also validate datafiles or the database to detect block corruption. `VALIDATE CHECK LOGICAL` checks additional block-level logical consistency, though it consumes resources and should be scheduled carefully.

## 13. Handling a Database That Cannot MOUNT or OPEN

If the database fails to mount, determine whether the control file, SPFILE, ASM, and foundational files are available. You cannot run all SQL queries while an instance is unmounted.

General investigation sequence:

1. Read both database and ASM alert logs to find the *first* error, not just the final error.
2. Check whether the instance can start with a PFILE/SPFILE.
3. Verify whether control files exist and multiplexed copies are accessible.
4. Confirm ASM disk groups/filesystems holding control files and datafiles are mounted.
5. If control files are lost, restore the control file from autobackup/recovery catalog.
6. Mount the database and identify which files need restoring.
7. Restore datafiles to accessible locations.
8. Recover using continuous redo.
9. Open the database per the recovery mode performed.

If only a datafile is lost while the control file and instance remain healthy, shutting down the entire database may be unnecessary. If a `SYSTEM` file or the control file is lost, work at `MOUNT` or `NOMOUNT` in the proper order.

## 14. Post-Recovery Verification

RMAN finishing without error is a strong signal, not the entire verification process. After recovery, check the database, datafiles, tablespaces, alert log, and connected applications.

### 14.1. Check Database Status

```sql
SELECT name,
       open_mode,
       database_role,
       log_mode,
       resetlogs_change#,
       resetlogs_time
FROM v$database;
```

### 14.2. Check Datafiles and Headers

```sql
SELECT file#,
       name,
       status,
       enabled
FROM v$datafile
ORDER BY file#;
```

```sql
SELECT file#,
       status,
       error,
       recover,
       fuzzy,
       checkpoint_change#,
       name
FROM v$datafile_header
ORDER BY file#;
```

### 14.3. Check Files Still Needing Recovery

```sql
SELECT file#,
       online_status,
       error,
       change#,
       time
FROM v$recover_file;
```

After complete recovery within scope, no files should remain needing media recovery for a database about to open normally. If this view still lists files needing recovery, determine which files and why; never try to force them online.

### 14.4. Check Tablespaces

```sql
SELECT tablespace_name,
       status,
       contents
FROM dba_tablespaces
ORDER BY tablespace_name;
```

```sql
SELECT file_id,
       file_name,
       tablespace_name,
       status,
       online_status
FROM dba_data_files
ORDER BY file_id;
```

Confirm required tablespaces are online in the expected state. `SYSTEM` and critical tablespaces must be in the required state for normal database operation. An application tablespace may intentionally stay offline while storage repairs finish.

### 14.5. Post-Recovery Validation

Use RMAN to validate:

```rman
VALIDATE DATABASE;
```

Or run logical checks:

```rman
VALIDATE CHECK LOGICAL DATABASE;
```

These operations can generate significant I/O and CPU load on large databases. Pick an appropriate scope and timing. Check the alert log, OS/storage logs, backup status, and representative business queries once the database opens.

## 15. Scenarios Where Complete Recovery Is Not Possible

Complete recovery is only achievable when valid baseline data and all required redo exist. Situations that make it impossible include:

- No usable datafile backup exists, or all backup copies are corrupted.
- One or more required archived redo logs are lost with no surviving copy.
- The sole copy of a needed online redo log is lost.
- Storage holding both datafiles and backups/archived logs failed with no copy outside that failure domain.
- The database runs in `NOARCHIVELOG` with no suitable consistent backup to restore.
- Control file/repository cannot identify files and backups, and no metadata copy survives.

In these scenarios, the DBA must determine the latest achievable recovery point and acceptable data loss. Incomplete recovery, restoring from a standby, recovering storage replicas, or another disaster recovery path may be required. Never declare "complete recovery succeeded" if required redo was skipped.

## 16. Mistakes to Avoid

| Mistake | Potential Consequence | Correct Approach |
|---|---|---|
| Restoring a datafile and bringing it online immediately | File has an old checkpoint, inconsistent with database | Recover using redo before bringing online |
| Using `OPEN RESETLOGS` for every recovery | Unnecessary incarnation change or wrong workflow | Use only when recovery path requires it (e.g., incomplete recovery or backup control file) |
| Offlining `SYSTEM` while database is open | Not supported by Oracle | Shut down and `STARTUP MOUNT` to recover |
| Using `OFFLINE FOR DROP` when intending to recover the file | Signals intent to drop the file, complicating or breaking recovery | Use standard offline/recovery without drop flags |
| Checking archived logs for only one thread in RAC | Missing redo from other threads | Check sequences across every thread |
| Recreating an ASM disk group without verifying backups | Can destroy salvageable data | Capture state, verify devices and backups before altering storage |
| Treating ASM mirroring as a backup | Does not protect against logical errors or accidental deletions | Maintain independent backups |
| Restoring a tempfile like a permanent datafile | Wrong recovery mechanism | Recreate tempfile in the temporary tablespace |
| Ignoring control file or redo log damage | Database cannot mount/open or lacks redo | Identify file types before choosing a recovery path |
| Running sample RMAN commands without updating file#/paths | Restoring wrong file or overwriting unintended locations | Verify DBID, DB name, `file#`, path, and repository |

## 17. Standard Procedure When a Datafile or Storage Failure Occurs

An operational workflow can be structured as follows:

1. **Preserve state:** record incident time, alert log, OS/storage errors, ASM disk groups, and instance status.
2. **Determine scope:** list affected datafiles, tablespaces, control files, redo logs, and tempfiles.
3. **Assess continuity:** decide whether to offline one file, offline a tablespace, or shut down the database.
4. **Restore storage:** repair the filesystem, replace disks, mount disk groups, or prepare a new target location.
5. **Verify backups:** confirm datafile backups, incremental backups, control file, SPFILE, and archived redo are readable.
6. **Verify redo chain:** ensure continuous log sequences up to the complete recovery target across every thread in RAC.
7. **Select restore scope:** datafile, tablespace, or whole database based on damage extent.
8. **Restore:** restore backups into place, or use `SET NEWNAME` and `SWITCH` when relocating storage.
9. **Recover:** apply redo via RMAN up to the required target.
10. **Bring files/database online:** bring datafile/tablespace online or open the database matching the control file and recovery mode.
11. **Verify:** check datafile status, headers, `V$RECOVER_FILE`, alert log, and run validation when appropriate.
12. **Post-recovery backup:** take a fresh backup and confirm archived log/backup policies continue running.
13. **Post-incident review:** record actual RTO/RPO, restore duration, redo apply duration, storage bottlenecks, and gaps in backup strategy.

## 18. Practice Walkthrough: Losing a Datafile in the USERS Tablespace

Suppose database `DB1` is in `ARCHIVELOG`, open normally, and the current control file remains usable. Datafile 7 in tablespace `USERS` was deleted from the filesystem. RMAN has a backup of datafile 7 and complete archived redo up to the present.

### Step 1: Identify the File

```sql
SELECT d.file#,
       d.name,
       t.name AS tablespace_name
FROM v$datafile d
JOIN v$tablespace t
  ON t.ts# = d.ts#
WHERE d.file# = 7;
```

Confirm this is a `USERS` datafile, not `SYSTEM` or an active undo tablespace datafile.

### Step 2: Take the File Offline

```sql
ALTER DATABASE DATAFILE 7 OFFLINE;
```

If the file is already offline due to the error, inspect its state rather than blindly repeating commands.

### Step 3: Check Backups

```rman
LIST BACKUP OF DATAFILE 7;
LIST ARCHIVELOG ALL;
RESTORE DATAFILE 7 PREVIEW;
```

Ensure backups are accessible and required redo is intact.

### Step 4: Restore and Recover

```rman
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

RMAN restores the datafile from backup and applies required redo.

### Step 5: Bring the File Online

```sql
ALTER DATABASE DATAFILE 7 ONLINE;
```

### Step 6: Verify

```sql
SELECT file#,
       name,
       status
FROM v$datafile
WHERE file# = 7;
```

```sql
SELECT *
FROM v$recover_file
WHERE file# = 7;
```

Check the alert log and run representative business queries against the tablespace. Confirm subsequent backup jobs and archived log backups keep running.

## 19. Practice Walkthrough: Losing an Entire Disk Group Holding Datafiles

Suppose disk group `DATA` is completely lost, and the database cannot mount because all datafiles and control files resided in that disk group. Database backups and control file autobackups reside on independent storage `/backup/DB1`; archived redo from the backup up to the failure is also fully backed up.

Conceptual sequence:

1. Repair or provision new storage and create the target disk group per ASM design.
2. Restore the SPFILE or use a PFILE with matching ASM/control file parameters.
3. Start the instance in `NOMOUNT`.
4. Restore the control file from autobackup, using `DBID` if needed.
5. Mount the database.
6. Catalog backup pieces if the repository does not recognize the backup files.
7. Set newnames for datafiles to the new disk group, restore, and switch files.
8. Recover the database using complete archived/online redo.
9. Open the database per control file type and recovery path; since a backup control file was used, handle `RESETLOGS` per Oracle requirements.
10. Validate, inspect files, take a fresh database backup, and review storage protection strategy.

This is a disaster recovery scenario—do not execute it by blindly copying and pasting sample commands sequentially. Build an explicit plan for DBID, autobackup format, channels, ASM disk groups, newnames, archived logs, and backup device access.

## 20. Recovery, RTO, and RPO

Complete recovery is the technical capability to bring a database up to the present using redo. In operations, tie it to two metrics:

- **RPO (Recovery Point Objective):** the maximum data loss an organization accepts, measured by time or data point.
- **RTO (Recovery Time Objective):** the target time to restore service after an outage.

A strategy with daily backups but unprotected archived logs may fail near-zero RPO. A database with complete backups and redo whose restore takes many hours due to slow storage or network may still miss RTO.

To evaluate realistically, rehearse restore/recovery periodically, measuring backup read time, redo apply time, database open time, and application verification. A "backup completed successfully" log alone does not prove the full system can recover within committed timelines.

Complete recovery after datafile loss or storage failure coordinates backups, control files, redo, instance state, and storage infrastructure. The DBA must accurately identify lost file types, choose the right restore scope, apply all required redo, and verify post-recovery state. When continuous redo and valid backups are preserved, Oracle can return a datafile or database to a consistent state without intentionally discarding committed transactions after the backup.
