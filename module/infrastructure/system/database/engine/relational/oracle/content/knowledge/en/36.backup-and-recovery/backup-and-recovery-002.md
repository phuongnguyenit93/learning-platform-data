# Consistent Backups, Inconsistent Backups, and Crash Recovery

A database backup is only useful if it can be restored to a consistent data state. In Oracle, backups can be created when the database has been cleanly shut down or while the database remains open serving applications. These two cases have different characteristics: a **consistent backup** captures datafiles in a consistent state at a single SCN; an **inconsistent backup** may contain blocks/datafiles from different points in time and requires redo to bring them to the same state upon restore.

**Crash recovery** is the process by which Oracle automatically brings a database to a consistent state after an abnormal instance termination while the datafiles remain available. Oracle uses redo to roll forward necessary changes and undo to roll back uncommitted transactions. If a datafile is lost or damaged and must be retrieved from a backup, that is **media recovery**; it may require archived redo logs and online redo logs.

This lesson covers:
- SCNs, checkpoints, and consistency across datafiles.
- Consistent backups and inconsistent/fuzzy backups.
- Offline (closed) backups, online backups, and ARCHIVELOG/NOARCHIVELOG.
- RMAN online backups and user-managed hot backup mode.
- The roles of the control file, SPFILE, online redo, and archived redo.
- Crash/instance recovery versus media recovery.
- Rolling forward with redo and rolling back with undo.
- Observing recovery through dynamic performance views and the alert log.
- Restoring/recovering various backup types and OPEN/RESETLOGS conditions.
- Labs and backup/recovery operational procedures.

Examples use Oracle Database 19c. RMAN/SQL syntax and certain views may differ across releases, RAC configurations, CDB/PDB architectures, and storage types. Always consult the Backup and Recovery documentation for your exact release and practice restores in a lab environment before applying to production.

## 1. SCN, Checkpoints, and Consistency

### 1.1. What Is an SCN?

A System Change Number (SCN) is a logical sequential number Oracle uses to represent the order of changes in the database. SCNs are used in read consistency, redo, checkpoints, recovery, and defining points in time.

An SCN is not a wall-clock timestamp. It increases with database activity and serves as a logical marker for Oracle to identify a data state.

When we say a datafile is checkpointed to SCN X, it means the necessary changes up to that marker have been written per the checkpoint mechanism into the datafile and its corresponding header metadata. If a datafile has newer blocks or is not fully synchronized with other files, recovery may need redo to bring the files to a compatible state.

### 1.2. Checkpoints

A checkpoint is the mechanism by which Oracle drives the writing of dirty buffers from the buffer cache to datafiles and updates checkpoint information. Checkpoints help limit the amount of redo that must be applied during instance recovery.

A checkpoint does not mean all transactions were committed at that point, nor does it mean every block in the database contains data from the same transaction snapshot. Dirty blocks from uncommitted transactions can still be written to datafiles; undo allows Oracle to roll them back or provide read-consistent views.

Related checkpoint types:
- Thread checkpoint / instance checkpoint.
- Datafile checkpoint.
- Incremental checkpoint.
- Checkpoints during shutdown or log switches.

### 1.3. Datafile Headers and Checkpoint SCN

The datafile header stores file identification, checkpoint, resetlogs, and recovery status information. The control file also stores metadata about datafiles, checkpoints, and redo log history.

During normal database operation, datafiles can be at different checkpoint SCNs. This does not mean the database is corrupted: Oracle manages these differences through redo and checkpoint coordination. For the database to open consistently, Oracle must ensure files are recovered to a compatible state.

### 1.4. Consistent Database State

A consistent database state is one where datafiles are synchronized to a consistent point meeting recovery requirements, with no further redo needed to resolve discrepancies from a backup or crash before opening in the corresponding manner.

A **consistent whole database backup** is typically created after a clean database shutdown, when all datafiles have been checkpointed to a consistent state. If the complete set of files is restored from that backup with no other issues, no media recovery is required to roll forward to a common SCN.

An **inconsistent backup** may contain datafiles copied at different times while the database was open. It may contain fuzzy blocks and requires redo recovery before opening.

## 2. Consistent Backups

A consistent backup is a backup of a database that has been brought to a consistent state before copying.

### 2.1. Creating a Consistent Backup via Clean Shutdown

User-managed OS-level backup example:

~~~sql
SHUTDOWN IMMEDIATE;
~~~

After the instance stops cleanly, the database has completed transactions per shutdown immediate semantics, rolled back uncommitted transactions, and checkpointed datafiles. Once the database is closed, all datafiles, control files, and the SPFILE can be copied following a supported backup procedure.

You can create a consistent backup with RMAN while the database is in the MOUNT state after a clean shutdown:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

In RMAN:

~~~text
BACKUP DATABASE;
BACKUP CURRENT CONTROLFILE;
BACKUP SPFILE;
~~~

After the backup:

~~~sql
ALTER DATABASE OPEN;
~~~

A plan must be in place to protect the control file and SPFILE. If control file autobackup is configured, RMAN can automatically generate autobackups per policy; you must still verify actual backup pieces and restore capability.

### 2.2. Clean Shutdown Conditions

Shutdown modes to distinguish:
- SHUTDOWN NORMAL: waits for users to disconnect.
- SHUTDOWN TRANSACTIONAL: waits for active transactions to finish.
- SHUTDOWN IMMEDIATE: terminates sessions and rolls back uncommitted transactions before stopping.
- SHUTDOWN ABORT: stops the instance immediately without completing a clean checkpoint or shutdown recovery.

A backup taken after a successful SHUTDOWN NORMAL, TRANSACTIONAL, or IMMEDIATE can be a consistent backup. A backup taken after SHUTDOWN ABORT is not considered consistent merely because the instance stopped; upon startup, Oracle must perform crash/instance recovery.

### 2.3. Advantages and Limitations

Advantages:
- The set of datafiles is copied in a consistent state.
- Archived redo may not be needed to recover that consistent backup itself.
- Straightforward concept and procedure.
- Suitable for small databases, labs, or systems where downtime is acceptable.

Limitations:
- Requires downtime or a database maintenance window.
- Unsuitable for systems requiring high availability.
- Only restores to the state at backup time; subsequent transactions are absent from the backup without additional mechanisms.
- Requires backing up all necessary files and protecting them as a complete set.

A consistent backup does not replace a scheduled backup strategy, offsite copies, archived log backups, and restore testing if RPO/RTO requires recovering to a more recent point in time.

## 3. Inconsistent Backups and Fuzzy Datafiles

An inconsistent backup is a backup created while the database is open or when files are not guaranteed to be checkpointed simultaneously to a single consistent state.

### 3.1. Why Can an Online Backup Be Inconsistent?

While the database is open, sessions continue modifying blocks while the backup reads datafiles. One file may be copied before a transaction updates a block; another file may be copied after the transaction modifies a block. The copy may contain blocks belonging to multiple SCNs.

Oracle calls this state requiring recovery "fuzzy." Fuzzy does not mean the backup is corrupted. It means appropriate redo must be applied to bring the datafiles to a consistent state.

### 3.2. Timeline Example

~~~text
Time ---------------------------------------------------------->

T1: Backup starts copying datafile A
T2: Transaction modifies blocks A and B, generating redo
T3: Backup copies datafile B
T4: Transaction COMMITs
T5: Backup completes

Datafiles A and B may reflect different points in time.
Archived/online redo enables rolling forward to a consistent SCN.
~~~

In this example, the backup may have copied block A before the change while copying block B after the change. Recovery uses redo to apply the required changes, and then undo ensures uncommitted transactions do not appear as committed data.

### 3.3. Inconsistent Does Not Mean Unsafe

Oracle supports controlled online backups in ARCHIVELOG mode. RMAN tracks backup metadata and required redo. Upon restore, RMAN/Oracle performs recovery to bring the datafiles to a consistent point.

The critical requirement is protecting all necessary archived redo logs, the control file, backup pieces, and metadata. An online backup missing required redo may fail to recover to the desired target.

### 3.4. Backing Up One Datafile Does Not Mean Database-Wide Consistency

A single datafile backup may require redo starting from that file's own checkpoint. In a database with multiple datafiles, recovery must ensure all necessary files are compatible at the target SCN. Never inspect a single datafile header alone to conclude the entire database is consistent.

## 4. ARCHIVELOG and NOARCHIVELOG

The logging mode directly impacts online backup capability and post-incident recoverability.

### 4.1. ARCHIVELOG Mode

In ARCHIVELOG mode, Oracle saves filled redo log groups as archived redo logs before reusing those groups. Archived redo enables:
- Backing up the database while it remains open using supported procedures.
- Recovering datafiles from backups to a desired SCN/time within the range of available redo.
- Protecting data modified after the backup point.
- Performing point-in-time recovery and various media recovery scenarios.

Check status:

~~~sql
ARCHIVE LOG LIST;
~~~

Or:

~~~sql
SELECT
    log_mode,
    open_mode,
    current_scn
FROM v$database;
~~~

### 4.2. NOARCHIVELOG Mode

In NOARCHIVELOG mode, online redo logs are reused without saving archived copies via the archive log mechanism. Once an older log is overwritten, that redo is no longer available for standard media recovery.

Consequences:
- Cannot rely on open online backups under standard online backup workflows.
- Typically must perform a clean shutdown and back up the database in MOUNT mode.
- Recovery is limited to the most recent consistent backup and whatever redo remains usable.
- Losing a datafile may mean losing all changes made after the backup.

NOARCHIVELOG is only appropriate for certain databases whose data can be regenerated or that tolerate a large RPO. Never choose this mode solely to save archive disk space.

### 4.3. Enabling ARCHIVELOG Mode

Basic procedure example:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
ARCHIVE LOG LIST;
~~~

Before enabling:
- Determine the archive destination and capacity.
- Verify permissions and free space on the filesystem or FRA.
- Configure archived log backups.
- Monitor for a full archive destination.
- Test backups and restores.
- Plan for downtime since a restart/mount is required.

Switching to ARCHIVELOG mode does not automatically create a complete backup strategy. You must back up the database, control file, SPFILE, and archived redo logs.

## 5. RMAN Online Backups

RMAN is Oracle's recommended tool for backup and recovery. When a database is in ARCHIVELOG mode, RMAN can back up the database while it remains open.

### 5.1. Prerequisites for Online Backups

- Database is in ARCHIVELOG mode.
- Database and datafiles are in an appropriate state.
- Storage is available for backup pieces and archived logs.
- Control file/SPFILE are protected.
- Archive destination has sufficient free space.
- RMAN configuration and retention policy have been reviewed.
- Backup jobs have logging and monitoring.

### 5.2. Backing Up the Database Along with Archived Logs

Example in RMAN:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

This command instructs RMAN to back up the database and archived redo logs in the sequence required for the backup. Exact behavior regarding archive log switching and backup scope depends on RMAN configuration/version; check job output and the backup list afterward.

You can enable control file autobackup:

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

And back up the SPFILE/control file according to policy. Never rely solely on a job returning SUCCESS; verify actual backup pieces, archived log coverage, and restore validation.

### 5.3. RMAN Does Not Require BEGIN BACKUP Mode

RMAN online backups manage reading datafiles and tracking required metadata/redo through RMAN's own mechanisms. Do not run `ALTER TABLESPACE BEGIN BACKUP` before an RMAN backup. `BEGIN/END BACKUP` is a user-managed hot backup mechanism; misusing it can increase redo generation and cause confusion about backup state.

### 5.4. Checking Backups

In RMAN:

~~~text
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
REPORT NEED BACKUP;
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Meaning:
- `LIST` displays backups known to the repository.
- `REPORT NEED BACKUP` evaluates backup needs according to policy.
- `RESTORE PREVIEW` lists the backups required for a restore.
- `RESTORE DATABASE VALIDATE` checks readability of required backup pieces without performing an actual restore.

Validation helps catch certain readability issues, but it does not replace a full restore drill in an independent environment.

## 6. User-Managed Hot Backups and BEGIN/END BACKUP

Aside from RMAN, Oracle supports user-managed backups by copying datafiles at the OS level while the database is open. In this case, `BEGIN BACKUP`/`END BACKUP` must be used properly.

### 6.1. Requirements

- Database must be in ARCHIVELOG mode for standard online hot backups.
- A procedure for copying files and protecting the control file must exist.
- Necessary archived redo logs must be backed up.
- Backup mode must be ended properly.
- File copies and recovery must be tested before relying on them.

### 6.2. BEGIN BACKUP

Example for a single tablespace:

~~~sql
ALTER TABLESPACE users BEGIN BACKUP;
~~~

In backup mode, Oracle manages the datafile's checkpoint SCN appropriately for user-managed backups and changes how redo is written for blocks modified for the first time during the backup interval, including writing full block images when needed to handle fractured blocks.

This can significantly increase redo generation, especially when many blocks are updated during the backup window. `BEGIN BACKUP` does not freeze data and does not prevent applications from writing to the tablespace.

### 6.3. Copying the Datafile

Identify the exact datafiles of the tablespace:

~~~sql
SELECT
    file_id,
    file_name,
    tablespace_name
FROM dba_data_files
WHERE tablespace_name = 'USERS';
~~~

At the OS level, copy the exact files identified while `BEGIN BACKUP` is active:

~~~bash
cp /u02/oradata/ORCL/users01.dbf /backup/orcl/users01.dbf
~~~

This example illustrates a single file. With multiple datafiles, copy every file within the backup scope and record exact file names and paths.

### 6.4. END BACKUP

After copying finishes:

~~~sql
ALTER TABLESPACE users END BACKUP;
~~~

Check status:

~~~sql
SELECT
    file#,
    status,
    change#,
    time
FROM v$backup;
~~~

The file is no longer in backup mode once `END BACKUP` completes. Do not leave tablespaces in backup mode longer than necessary, as this can increase redo volume and cause operational issues.

### 6.5. Whole-Database Backup

`ALTER DATABASE BEGIN BACKUP`/`END BACKUP` can be used in certain legacy user-managed workflows, but you must weigh the scope, redo overhead, and release guidelines. Modern practice strongly favors RMAN; if forced to use user-managed backups, maintain an exact runbook for every datafile/tablespace, control file, and archived log.

### 6.6. If You Forget END BACKUP

Check `V$BACKUP` to detect files still marked `ACTIVE`. If the database crashes while files are in backup mode, Oracle may need to handle the backup state during startup/recovery. The DBA must determine which files are in backup mode, how the database is MOUNTed/OPENed, and execute `END BACKUP`/recovery following Oracle documentation for the specific scenario. Never run bulk commands or copy additional files before understanding the state.

## 7. Redo, Undo, and Recovery

### 7.1. What Is Redo?

Redo records describe the changes needed to reconstruct database blocks. Redo is written to the redo log buffer and then written by LGWR to the online redo logs. When a log group is archived in ARCHIVELOG mode, Oracle creates an archived redo log.

Redo is generated for data changes and other necessary changes, including undo protection information. Redo does not contain only committed transactions; redo for uncommitted transactions can also be recorded.

### 7.2. What Is Undo?

Undo stores information required to roll back transactions and provide read consistency. When a transaction modifies a row, Oracle generates an undo record describing how to restore the prior value.

During recovery:
- Redo rolls forward recorded changes to datafiles, including changes from uncommitted transactions.
- Undo rolls back uncommitted transactions so the database returns to a transactionally consistent state.

### 7.3. Why Roll Forward Uncommitted Transactions Too?

During a crash, datafiles may already contain some blocks from uncommitted transactions because DBWR wrote them to disk before the crash. Oracle must apply redo to ensure all modified blocks are properly reconstructed. Transaction recovery then uses undo to remove uncommitted changes.

If Oracle only rolled forward committed transactions, the database could be left with partially modified blocks or missing changes needed to keep related structures synchronized.

### 7.4. Illustration

~~~text
Before crash:
  Transaction A: UPDATE row 1, COMMIT
  Transaction B: UPDATE row 2, not yet COMMITted

Datafiles may already contain some blocks from A and B.
Redo logs contain redo for both A's and B's changes.

Crash recovery:
  1. Cache recovery: roll forward redo to reconstruct consistent blocks.
  2. Transaction recovery: use undo to roll back B.
  3. Database opens with A's changes committed, and B does not appear as committed data.
~~~

## 8. Crash Recovery and Instance Recovery

Crash recovery is commonly referred to as instance recovery: Oracle recovers the database after an abnormal instance termination while the required datafiles and redo remain available.

Causes include:
- Server power loss or OS crash.
- Oracle instance process failure.
- Shutdown abort.
- Instance termination.
- Failure of a RAC instance.

### 8.1. What Happens at Startup?

When the instance starts and mounts/opens the database, Oracle checks checkpoint and redo status. If needed, Oracle performs instance recovery before allowing normal database operations.

High-level flow:

~~~text
Instance failure / abnormal shutdown
               |
               v
        STARTUP / mount
               |
               v
   Read control file and datafile headers
               |
               v
   Determine checkpoint and redo position
               |
               v
       Cache recovery (redo)
               |
               v
 Transaction recovery (undo rollback)
               |
               v
        Open database normally
~~~

In many cases, the DBA simply starts the instance; Oracle automatically performs crash recovery. No datafile restore is needed if the files remain intact and sufficient redo exists.

### 8.2. Cache Recovery / Roll Forward

Oracle applies redo from the required checkpoint position to bring data blocks to a consistent state. The redo may reside in the online redo logs of the thread being recovered.

### 8.3. Transaction Recovery / Rollback

After rolling forward, Oracle identifies uncommitted transactions and rolls them back using undo. Rollback may continue in the background after the database is opened; sessions may observe transaction recovery/rollback activity during that time.

### 8.4. Crash Recovery Is Not Media Recovery

| Scenario | Recovery Type | Backup Restore Needed? |
| --- | --- | --- |
| Instance crash, datafiles and online redo intact | Instance/crash recovery | Usually no |
| Shutdown abort followed by startup | Instance/crash recovery | Usually no |
| Datafile deleted/corrupted | Media recovery | Usually requires file restore |
| Diskgroup containing datafile lost | Media recovery/storage recovery | Depends on redundancy and backups |
| Restoring an online backup | Media recovery | Yes, apply redo after restore |
| Restoring to a past SCN/time | Incomplete media recovery | Yes, followed by OPEN RESETLOGS |

If a datafile is lost, Oracle cannot rely on instance recovery alone to recreate it. It must be restored from backup and recovered using redo.

## 9. Checkpoints and Crash Recovery Duration

Checkpoints help reduce the amount of redo that must be applied during instance recovery. Infrequent/old checkpoints can cause recovery to process more redo; overly frequent checkpoints can increase I/O and degrade workload performance if misconfigured.

### 9.1. FAST_START_MTTR_TARGET

Oracle can use `FAST_START_MTTR_TARGET` to set a target duration (estimated) for instance recovery. Example:

~~~sql
SHOW PARAMETER fast_start_mttr_target;
~~~

View recovery information:

~~~sql
SELECT
    target_mttr,
    estimated_mttr,
    actual_redo_blks,
    target_redo_blks,
    optimal_logfile_size
FROM v$instance_recovery;
~~~

Column names and calculations depend on the release. The MTTR target is a goal for instance recovery, not a guarantee that every crash will open the database in that exact number of seconds; storage, redo volume, workload, and hardware issues can alter actual duration.

### 9.2. Do Not Force Checkpoints Continuously

Running `ALTER SYSTEM CHECKPOINT` continuously is not a general-purpose way to speed up recovery. It can cause I/O spikes and increase dirty-buffer write overhead. Tune MTTR and checkpoint policies according to workload, measure the impact, and follow Oracle recommendations.

## 10. Media Recovery After Restoring an Inconsistent Backup

Media recovery is required when datafiles are restored from backup and redo must be applied to synchronize them to a target SCN.

### 10.1. General Workflow

~~~text
Backup pieces + control file + archived redo
                   |
                   v
              RESTORE
                   |
                   v
       Datafiles return to backup state
                   |
                   v
               RECOVER
                   |
                   v
   Apply archived/online redo to target SCN
                   |
                   v
      Datafiles consistent at target SCN
                   |
                   v
                 OPEN
~~~

### 10.2. Restoring and Recovering with RMAN

Conceptual example for complete recovery using the current control file:

~~~text
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

In RMAN, restore/recover commands are run at the RMAN prompt; `STARTUP`/`ALTER DATABASE` can be executed via RMAN or SQL*Plus depending on the procedure.

Complete recovery applies redo up to the latest possible state based on available redo and the control file/repository. If all datafiles are fully recovered using the current control file, the database normally opens regularly.

### 10.3. Backup Control File

If the control file is also lost and must be restored from backup, Oracle may require recovery using a backup control file and opening with `RESETLOGS` after completing the appropriate procedure.

Example flow:

~~~text
STARTUP NOMOUNT;
RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN RESETLOGS;
~~~

This is a general illustration. When incomplete recovery or a backup control file is involved, you must verify the target SCN/time, redo availability, incarnation, and exact RMAN instructions. Never run `OPEN RESETLOGS` merely because you saw it in an example; `RESETLOGS` creates a new database incarnation and affects backup/recovery strategy.

### 10.4. Incomplete Recovery / Point-in-Time Recovery

If you need to return the database to a point before a logical error, use the appropriate RMAN `SET UNTIL SCN/TIME/SEQUENCE` command, then restore and recover. After incomplete recovery, the database typically must be opened with `RESETLOGS`.

RMAN command format example:

~~~text
RUN {
  SET UNTIL TIME "TO_DATE('2026-11-14 10:30:00',
                         'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Then open the database with `RESETLOGS` as required by the recovery path. The timestamp in the example is illustrative; select the correct timezone, target, and verify redo coverage.

## 11. Control File, SPFILE, and Redo Logs in Backups

### 11.1. Control File

The control file stores database structure, datafile/redo log names, checkpoint metadata, log history, and RMAN repository records if using a control file repository.

If the control file is lost:
- It can be restored from autobackup.
- Backups may need to be cataloged if the repository lacks metadata.
- Recovery may have to be performed using a backup control file.
- `OPEN RESETLOGS` is typically required after the appropriate control file restore procedure.

Maintaining multiple multiplexed control files does not replace control file backups; multiplexing protects against losing one copy due to a storage/file error.

### 11.2. SPFILE/PFILE

The SPFILE contains database startup parameters. Backing up the SPFILE helps restore instance configuration after a failure. RMAN can back up the SPFILE explicitly or alongside control file autobackups depending on configuration.

~~~text
BACKUP SPFILE;
~~~

If using a PFILE, store the configuration file in a protected, version-controlled location.

### 11.3. Online Redo Logs

Online redo logs are required for crash/instance recovery and may be needed during media recovery to the current state. Do not assume datafile backups alone are sufficient if necessary online redo and archived redo are unprotected.

Never copy active online redo log files as ordinary OS files to create a backup. Use Oracle-supported mechanisms and back up the control file and archived logs according to plan.

### 11.4. Archived Redo Logs

Archived logs form the redo chain needed to recover from a backup to a target SCN. If a single log is missing from the required chain, recovery may halt at an earlier SCN.

Protect archived logs by:
- Backing them up frequently.
- Retaining them per retention/recovery window policies.
- Monitoring the archive destination/FRA.
- Maintaining copies off-host/off-zone if required for DR.
- Running restore/validate checks.
- Avoiding manual deletion of archived logs before the RMAN repository is updated.

## 12. Checking Backup and Recovery Status

### 12.1. Database Mode and SCN

~~~sql
SELECT
    name,
    open_mode,
    log_mode,
    current_scn,
    checkpoint_change#
FROM v$database;
~~~

These columns show database identity, open mode, archive mode, and key SCN markers. They do not by themselves prove all backup pieces are valid.

### 12.2. Datafile Headers

~~~sql
SELECT
    file#,
    status,
    error,
    recover,
    fuzzy,
    checkpoint_change#,
    checkpoint_time
FROM v$datafile_header
ORDER BY file#;
~~~

The `RECOVER` and `FUZZY` columns help identify the recovery/fuzzy status of each datafile. Interpretation must account for the control file, open state, backup mode, and recovery context.

### 12.3. Datafile Metadata

~~~sql
SELECT
    file#,
    name,
    status,
    checkpoint_change#,
    checkpoint_time
FROM v$datafile
ORDER BY file#;
~~~

Compare datafile metadata with headers and recovery status. Do not use a single SCN difference to conclude the database is corrupted; checkpoints can differ during normal operation.

### 12.4. Files Requiring Media Recovery

~~~sql
SELECT
    file#,
    online,
    error,
    change#,
    time
FROM v$recover_file
ORDER BY file#;
~~~

`V$RECOVER_FILE` helps identify datafiles Oracle flags as needing media recovery. If the view returns no rows, that does not replace restore validation or backup testing.

### 12.5. User-Managed Backup Mode

~~~sql
SELECT
    file#,
    status,
    change#,
    time
FROM v$backup
ORDER BY file#;
~~~

`STATUS` can indicate whether a file is in backup mode. After a user-managed backup, verify that status is no longer `ACTIVE`. This view is not used to track RMAN backup mode.

### 12.6. Alert Log

The alert log records:
- Instance startup/shutdown.
- Crash recovery start/completion.
- Media recovery messages.
- Datafile errors.
- Archive log issues.
- Control file/redo problems.

When investigating slow startup after a crash, read the alert log from the time of failure until the database opens. Correlate timestamps with `V$INSTANCE_RECOVERY`, `V$SESSION`, and OS/storage metrics.

## 13. Crash Recovery in Practice

### 13.1. When the Instance Crashes but Files Remain Intact

If the instance terminates abnormally while datafiles, control files, and online redo logs remain intact:
1. Verify host and storage stability.
2. Inspect the alert log and OS errors.
3. Start the instance.
4. Oracle automatically detects that instance recovery is needed.
5. Oracle rolls forward redo and rolls back uncommitted transactions.
6. Confirm the database is OPEN and services are operational.
7. Check datafile status, alert log, and backup health.

Do not restore a backup simply because the database crashed. Unnecessary restores can revert data to an older point in time and lose valid post-backup transactions.

### 13.2. When Online Redo Is Lost or Corrupted

If online redo needed for crash recovery is lost or corrupted, the situation is much more complex. Recoverability depends on:
- Which redo group/member is affected.
- Current/active/inactive status.
- Remaining multiplexed members.
- Available archived logs.
- Control file state.
- Database mode and failure timing.

Do not drop/recreate redo log groups to bypass errors without determining the state first. Media recovery, incomplete recovery, or specialized disaster recovery procedures may be required.

### 13.3. RAC Instance Recovery

In RAC, if one instance fails, surviving instances can perform instance recovery for the failed instance's thread per RAC mechanisms. Global Cache Service and per-instance redo threads make the process more complex than single-instance recovery.

When investigating RAC:
- Identify the failed instance/thread.
- Review the alert log of every instance.
- Check redo threads and archive sequences.
- Check cluster/interconnect health.
- Consult the exact release's RAC tools/guides.

Do not apply single-instance commands verbatim to a RAC production environment.

## 14. Common Recovery Errors

| Error / Symptom | Common Meaning | Handling Approach |
| --- | --- | --- |
| ORA-01113 | Datafile needs media recovery | Identify file, restore if needed, then recover |
| ORA-01110 | Datafile information associated with an error | Read alongside the preceding ORA error to identify the file |
| ORA-01194 | File needs more recovery to be consistent | Apply additional redo up to the required SCN |
| ORA-01152 | File was not restored from a sufficiently old backup for recovery | Select a backup compatible with the target and redo |
| ORA-00279 | Recovery requires a specific change/redo sequence | Supply the archived log for the exact sequence/thread |
| ORA-00308 | Cannot open archived log | Check file/path/permissions and backup copies |
| ORA-00313 | Cannot open redo log member | Check redo group/member and storage |
| ORA-01157 | Cannot identify/lock datafile | Check file path, storage, and permissions |
| ORA-00205 | Error in identifying control file | Check `CONTROL_FILES` and control file copies |
| ORA-00257 | Archiver error, often due to full archive destination | Free/expand destination and resolve archiving |
| Slow startup after abort | Instance recovery must apply heavy redo/rollback | Monitor alert log, MTTR, and I/O |
| Datafile fuzzy after online backup | Backup requires redo recovery | Ensure required archived logs are available and recover |
| V$BACKUP still ACTIVE | File may still be in user-managed backup mode | Determine state and end backup mode properly |

Error codes often appear in chains. Always read the first message and the alert log; never act solely on the final error line.

## 15. Runbook: Distinguishing Instance Recovery and Media Recovery

When a database fails to open after an incident:

### Step 1: Identify the Incident Type
- Instance crashed while files remain intact?
- Datafile missing or corrupted?
- Control file lost?
- Online redo or archived log lost?
- Only one tablespace/file offline or the whole database?

### Step 2: Preserve Evidence
- Do not delete or overwrite damaged files.
- Save the alert log and OS/storage logs.
- Record timestamps, SCN, and thread/sequence if available.
- Confirm backup pieces and archived logs are intact.

### Step 3: Check Database State
- Instance status/open mode.
- Control file availability.
- Datafile header `RECOVER`/`FUZZY` flags.
- `V$RECOVER_FILE`.
- Online redo log status.
- Archived log coverage.

### Step 4: Choose the Recovery Path
- Crash only, files intact: start up and let automatic instance recovery run.
- Datafile missing/corrupt: restore the file and perform media recovery.
- Control file lost: restore control file, mount, restore/recover per backup control file procedure.
- Point-in-time recovery: choose target SCN/time and prepare for `OPEN RESETLOGS`.

### Step 5: Post-Recovery Verification
- Database OPEN in the proper mode.
- Datafiles ONLINE and no longer requiring recovery.
- Alert log free of recovery errors.
- Services and application smoke tests pass.
- New backup created for the post-`RESETLOGS` incarnation/state if applicable.
- Archive destinations and backup jobs operational.

Never open with `RESETLOGS` or delete redo/archive logs before determining the recovery target and verifying the backup strategy.

## 16. Lab: Comparing Consistent and Inconsistent Backups

This lab requires an isolated Oracle database with SYSDBA/RMAN privileges and backup storage. Do not run in production.

### 16.1. Observe the Initial State

~~~sql
SELECT
    name,
    open_mode,
    log_mode,
    current_scn
FROM v$database;

SELECT
    file#,
    status,
    recover,
    fuzzy,
    checkpoint_change#
FROM v$datafile_header
ORDER BY file#;
~~~

Record the log mode, current SCN, and datafile header state.

### 16.2. Create a Consistent Backup

Clean shutdown:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

In RMAN:

~~~text
BACKUP DATABASE;
BACKUP CURRENT CONTROLFILE;
BACKUP SPFILE;
LIST BACKUP SUMMARY;
~~~

Reopen the database:

~~~sql
ALTER DATABASE OPEN;
~~~

Record the backup timestamp, backup pieces, and protected control file/SPFILE. If the database is in NOARCHIVELOG, this clean shutdown/mount backup is the required procedure; verify with the RMAN guide for your release.

### 16.3. Create an Online Backup in ARCHIVELOG Mode

Verify:

~~~sql
ARCHIVE LOG LIST;
~~~

In RMAN:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG;
LIST BACKUP SUMMARY;
LIST BACKUP OF ARCHIVELOG ALL;
~~~

Record the database backup and archived logs. This is an inconsistent/online backup that may require redo for recovery; RMAN manages the backup metadata.

### 16.4. Compare

Record a comparison table:

| Attribute | Consistent Backup | Inconsistent / Online Backup |
| --- | --- | --- |
| Database open during backup | No, after clean shutdown | Can be open |
| Datafile checkpoints | Brought to a consistent state before backup | May differ / fuzzy |
| Redo required to recover | Usually not required for the consistent backup itself | Requires appropriate redo |
| Downtime | Required | Can be avoided |
| ARCHIVELOG | Not mandatory for consistent cold backup | Required for standard online backup |
| RPO | State at backup time | Can recover to a newer point if redo is available |

### 16.5. Restore Validation

In RMAN:

~~~text
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Observe which backup pieces are required. Note that validation does not restore files into the running database; it checks backup readability per the validate command.

## 17. Lab: Observing Crash Recovery

Perform this only in an isolated lab database that has backups and permission to stop the instance.

### 17.1. Record Baseline

~~~sql
SELECT
    name,
    open_mode,
    log_mode,
    current_scn
FROM v$database;

SELECT
    target_mttr,
    estimated_mttr,
    actual_redo_blks,
    target_redo_blks
FROM v$instance_recovery;
~~~

Note the alert log location and the status of the most recent backup.

### 17.2. Generate Lab Workload

Create a test table and run some DML across sessions. Commit part of the transactions; leave another transaction uncommitted in a lab session.

~~~sql
CREATE TABLE lab_crash_recovery (
    id NUMBER PRIMARY KEY,
    value NUMBER
);

INSERT INTO lab_crash_recovery VALUES (1, 100);
COMMIT;

UPDATE lab_crash_recovery
SET value = 200
WHERE id = 1;
-- This session has not COMMITted yet.
~~~

### 17.3. Execute Shutdown Abort in the Lab

From an authorized SYSDBA session:

~~~sql
SHUTDOWN ABORT;
~~~

This command simulates an abnormal termination. Run only in a lab database because all sessions are terminated and the next startup must perform instance recovery.

### 17.4. Start Up and Observe

~~~sql
STARTUP;
~~~

Watch the alert log to observe crash recovery. After the database opens:

~~~sql
SELECT * FROM lab_crash_recovery;
~~~

Committed changes must persist. Uncommitted transactions must be rolled back; the value `100` is retained instead of `200`.

Exact timings depend on checkpoints and redo timing, but transaction semantics must be preserved.

### 17.5. Lab Cleanup

~~~sql
DROP TABLE lab_crash_recovery PURGE;
~~~

If the instance fails to start or the lab encounters file/redo errors, stop and recover using the lab backup. Do not practice media recovery commands in production based on this exercise.

## 18. Practice Exercises

### Exercise 1 — SCN and Checkpoints

Query `V$DATABASE`, `V$DATAFILE`, and `V$DATAFILE_HEADER`. Explain checkpoint SCN, current SCN, and why header SCNs across datafiles are not always identical while a database is open.

### Exercise 2 — Clean Shutdown

Create a consistent backup after `SHUTDOWN IMMEDIATE`. Record the database state and explain why this backup may not require redo recovery.

### Exercise 3 — Shutdown Abort

Compare `SHUTDOWN IMMEDIATE` with `SHUTDOWN ABORT` in the lab. Observe the alert log and explain instance recovery.

### Exercise 4 — ARCHIVELOG

Check `LOG_MODE`. If the lab is in NOARCHIVELOG, plan the switch to ARCHIVELOG, configure the destination, and back up archived logs.

### Exercise 5 — RMAN Online Backup

Run `BACKUP DATABASE PLUS ARCHIVELOG` in the lab. Use `LIST BACKUP`, `RESTORE PREVIEW`, and `RESTORE VALIDATE` to verify.

### Exercise 6 — User-Managed Backup Mode

In a lab environment, execute `BEGIN BACKUP`, copy a datafile, execute `END BACKUP`, and inspect `V$BACKUP`. Record redo volume if monitoring tools are available.

### Exercise 7 — Redo and Undo

Create an uncommitted transaction and trigger crash recovery in the lab. Explain why Oracle must roll forward redo before rolling back with undo.

### Exercise 8 — Media Recovery

Using an isolated lab copy, simulate restoring a single datafile from an online backup and applying archived logs. Never perform this on production datafiles.

### Exercise 9 — Control File Backup

Enable `CONTROLFILE AUTOBACKUP` in the RMAN lab, inspect `LIST BACKUP`, and describe the control file restore procedure when the current control file is lost.

### Exercise 10 — Runbook

Write a runbook classifying instance crash, datafile loss, control file loss, and point-in-time recovery. For each scenario, specify backups, redo, target SCN, and `OPEN`/`RESETLOGS` conditions.

## 19. Cleaning Up and Restoring the Lab Environment

- Ensure all lab transactions are intentionally committed or rolled back.
- Drop all lab tables and objects.
- Restore any modified parameters or archive destinations.
- Confirm the database is OPEN and services are registered.
- Verify `V$BACKUP` has no user-managed files still `ACTIVE`.
- Confirm lab backup pieces/archived logs are retained or purged per policy.
- Do not delete archived logs needed for recovery of any shared database.
- Do not delete control files, online redo logs, or datafiles to create extra scenarios without an independent backup and restore plan.

## Summary

A consistent backup is typically created after a clean shutdown when datafiles have been checkpointed to a consistent state. An inconsistent/online backup is created while the database is open or files are copied at different times; datafiles may be fuzzy and require redo to recover to a consistent SCN. ARCHIVELOG mode enables online backups and media recovery to newer points in time; NOARCHIVELOG limits recoverability and usually requires consistent backups after a clean shutdown.

Crash recovery (instance recovery) occurs when an instance terminates abnormally while datafiles and redo remain available. Oracle automatically rolls forward with redo and rolls back uncommitted transactions with undo. Media recovery is different: when datafiles/control files are lost or restored from backup, the DBA must restore files and apply appropriate redo. Control files, SPFILE, online redo, and archived redo are all critical parts of a database protection strategy.

In operations, clearly identify backup types, SCNs/checkpoints, ARCHIVELOG mode, backup pieces, and redo coverage. Use RMAN to manage backups/restores, validate readability, and rehearse recovery. Never confuse crash recovery with backup restoration, never run `BEGIN/END BACKUP` before RMAN, and never `OPEN RESETLOGS` without first determining the recovery path. A backup is only trustworthy once it has been proven to restore and recover within required RPO/RTO targets.

## Oracle Reference Documentation

- [Oracle Database Backup and Recovery User's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN backup/recovery, consistent/inconsistent backups, instance recovery, and media recovery.
- [Oracle Database Backup and Recovery Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/) — RMAN commands, BACKUP, RESTORE, RECOVER, and validation.
- [Oracle Database Administrator's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — startup/shutdown, checkpoints, redo, and archive mode.
- [Oracle Database Reference — V$DATAFILE_HEADER (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAFILE_HEADER.html) — datafile header checkpoints and recovery flags.
- [Oracle Database Reference — V$RECOVER_FILE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RECOVER_FILE.html) — datafiles requiring media recovery.
- [Oracle Database Reference — V$BACKUP (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-BACKUP.html) — user-managed backup mode status.
- [Oracle Database Reference — V$INSTANCE_RECOVERY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-INSTANCE_RECOVERY.html) — checkpoint and MTTR recovery information.

When deploying on an Oracle release other than 19c, verify against the corresponding Backup and Recovery User's Guide, RMAN Reference, and Data Dictionary Reference, especially regarding backup mode, archived redo requirements, control file recovery, RESETLOGS, and RAC instance recovery.
