# ARCHIVELOG, NOARCHIVELOG, and Data Protection Planning

Oracle Database records data changes to online redo logs before the corresponding data blocks are written to datafiles. The redo mechanism enables the database to recover after an instance failure. When the database runs in ARCHIVELOG mode, Oracle saves copies of filled online redo logs to archived redo logs before the redo group can be reused. Archived redo logs allow changes to be reapplied after a backup and enable recovering the database to a desired point in time as long as the required redo is intact.

Two primary operating modes:

- **ARCHIVELOG:** saves archived redo logs; supports media recovery to a point newer than the backup, online backup with RMAN, and architectures such as Data Guard.
- **NOARCHIVELOG:** does not save archived redo logs; recovery capability after datafile loss is limited to the most recent consistent backup. To back up the database in the standard way, the database must be shut down cleanly.

Choosing a mode is not just a technical parameter. It determines RPO/RTO, backup frequency, storage capacity, operational procedures, Data Guard capability, and the acceptable level of data loss.

## 1. Redo, Online Redo Log, and Archived Redo Log

When a transaction modifies data, Oracle generates redo records describing the changes needed for recovery. LGWR writes redo from the redo log buffer to the online redo log.

Overview diagram:

~~~text
Application modifies data
          |
          v
     Redo records
          |
          v
     Redo log buffer
          |
          | LGWR writes
          v
    Online redo log
          |
          | log switch / log full
          v
    Archived redo log
          |
          v
   Backup / off-site storage
~~~

### 1.1 Online Redo Log

Online redo logs are a set of log groups (redo log groups) that Oracle uses cyclically to write redo. Each group can have multiple members, which are identical copies of the same redo group.

- LGWR writes redo into the current group.
- When the group is full or a log switch occurs, Oracle switches to another group.
- The old group becomes eligible for reuse only after a checkpoint and, in ARCHIVELOG mode, after it has been archived.

### 1.2 Archived Redo Log

An archived redo log is a copy of a completed online redo log group that has been archived. ARCn or the corresponding archiving mechanism writes the copy to the archive destination.

Archived redo logs are typically identified by:

- Thread number.
- Sequence number.
- Resetlogs ID/incarnation.
- First change number (SCN).
- Next change number (SCN).

A database can have multiple redo threads in RAC. Do not look only at the sequence number while ignoring the thread and incarnation when managing archive logs.

### 1.3 Redo Log Members vs. Archived Redo Logs

Multiplexing online redo logs with multiple members protects against losing a single redo member file. These are concurrent copies of the same redo log group.

An archived redo log, on the other hand, is a stored copy of a completed group. Multiplexing redo logs does not replace archive log backups, and archive log backups do not replace multiplexing online redo logs.

## 2. ARCHIVELOG Mode

In ARCHIVELOG mode, Oracle must archive a redo log group before that group can be reused. Archived redo logs preserve a continuous redo history so it can be applied to datafiles after restoring a backup.

### 2.1 Benefits

- Can back up datafiles while the database remains open using appropriate RMAN procedures.
- Can recover datafiles after media failure using backups plus archived redo logs.
- Can recover to a point in time before an error occurred (point-in-time recovery) if sufficient backups and redo exist.
- Serves as the foundation for physical standby/Data Guard.
- Supports frequent backup strategies without shutting down the database for every full backup.

### 2.2 Costs and Operational Responsibilities

- Archived redo logs are generated continuously and require storage capacity.
- Archived redo logs must be backed up and retention must be managed.
- A full archive destination can prevent log groups from being reused and cause the database to slow down or stall redo-writing processes.
- Archive lag, destination status, FRA, and ARCn errors must be monitored.
- Sequences needed for recovery/standby must be retained.

ARCHIVELOG mode provides superior recovery capability, but it also requires disciplined storage management and monitoring procedures.

## 3. NOARCHIVELOG Mode

In NOARCHIVELOG mode, Oracle does not save completed online redo logs as archived redo logs. Online redo logs are still used to record redo and perform instance recovery when a crash occurs, but historical redo is not retained completely for media recovery after datafile loss.

### 3.1 Consequences of Losing a Datafile

Suppose the database received a consistent backup on Sunday. From Sunday to Wednesday, many new transactions occur.

- If the database runs in ARCHIVELOG mode and has complete backups along with archived redo logs, you can restore Sunday's backup and apply redo up to a point near the incident.
- If the database runs in NOARCHIVELOG mode, after losing a datafile, you can generally only restore to the state of the most recent consistent backup. Changes made after the backup may be lost.

### 3.2 Backups in NOARCHIVELOG

With RMAN, to take a consistent database backup in NOARCHIVELOG mode, the database must be shut down cleanly and placed in MOUNT state, not open READ WRITE during a standard database backup.

The typical procedure is:

1. Stop the application and database with SHUTDOWN IMMEDIATE.
2. Start the database in MOUNT mode.
3. Run an RMAN backup of the database and required control file.
4. Reopen the database.

A physical OS-level copy must also be a consistent cold backup, meaning all required files are copied after the database has been shut down consistently. Do not arbitrarily copy a few datafiles while the database is open and treat that as a valid backup.

### 3.3 When Is NOARCHIVELOG Acceptable?

- Lab databases that can be completely recreated.
- Development/test environments that do not contain critical data.
- Temporary databases whose data is reloaded from another source.
- Small systems with an RPO that allows losing all changes since the last backup and a downtime window for backups.

Do not choose NOARCHIVELOG for production systems that require recovery close to the time of failure or require Data Guard.

## 4. Comparing ARCHIVELOG and NOARCHIVELOG

| Criterion | ARCHIVELOG | NOARCHIVELOG |
|---|---|---|
| Archived redo logs | Yes | Does not create new archive logs |
| Instance recovery | Yes, using online redo | Yes, using online redo |
| Media recovery after backup | Can apply archived redo | Limited to consistent backups |
| Point-in-time recovery | Possible, if sufficient backups/redo exist | No archived redo chain to roll forward to an arbitrary point |
| Online RMAN backup | Supports backup procedures while the database is open | Consistent database backup generally requires the database to be closed and MOUNTED |
| Data Guard physical standby | Foundational requirement | Not suitable |
| Archive storage space | Requires sizing and monitoring | Does not generate new archive logs |
| Operations | More complex; requires archive backup/purging | Simpler, but poor RPO |
| Suitable use cases | Production and systems requiring strong recovery | Lab/dev or regenerable data |

## 5. Checking the Current Mode

### 5.1 Querying V$DATABASE

~~~sql
SELECT name,
       open_mode,
       log_mode,
       database_role,
       force_logging,
       current_scn
FROM v$database;
~~~

LOG_MODE indicates ARCHIVELOG or NOARCHIVELOG.

### 5.2 Using ARCHIVE LOG LIST

In SQL*Plus or SQLcl:

~~~sql
ARCHIVE LOG LIST;
~~~

This command displays information such as:

- Database log mode.
- Automatic archival.
- Archive destination.
- Oldest online log sequence.
- Next log sequence.
- Current log sequence.

ARCHIVE LOG LIST is a client tool command, not a standard SQL SELECT statement.

### 5.3 Checking Redo Log Groups and Members

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes,
       members,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

View members:

~~~sql
SELECT group#,
       type,
       member,
       status
FROM v$logfile
ORDER BY group#, member;
~~~

The statuses CURRENT, ACTIVE, INACTIVE, and UNUSED have different meanings in the redo log lifecycle. Do not delete or rename a redo log member that is currently in use by the database.

## 6. Switching from NOARCHIVELOG to ARCHIVELOG

Changing the log mode requires the database to be in MOUNT state, not OPEN. This is a maintenance operation that requires a planned downtime window.

### 6.1 Basic Procedure on a Single Instance

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
~~~

Then verify:

~~~sql
SELECT log_mode
FROM v$database;
~~~

And:

~~~sql
ARCHIVE LOG LIST;
~~~

### 6.2 Configuring the Archive Destination Before Switching

Before enabling ARCHIVELOG, you must define where archives are stored. For example, using the Fast Recovery Area (FRA):

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST =
    '/u03/oracle/fra'
    SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE =
    200G
    SCOPE = BOTH;
~~~

The 200G capacity is only an example. It must be sized based on redo generation rate, backup duration, retention, Data Guard lag, and the duration during which purging may not be possible.

You can configure LOG_ARCHIVE_DEST_1 to use the FRA:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=USE_DB_RECOVERY_FILE_DEST'
    SCOPE = BOTH;

ALTER SYSTEM SET LOG_ARCHIVE_DEST_STATE_1 =
    'ENABLE'
    SCOPE = BOTH;
~~~

If using a dedicated filesystem:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=/u04/oracle/arch'
    SCOPE = BOTH;
~~~

The path must exist, be stably mounted, and be writable by the Oracle software owner. For production configurations, verify whether the parameter can be changed online or requires a restart in the specific version.

### 6.3 Taking a Full Backup After Switching Modes

After enabling ARCHIVELOG, take a new full backup to establish a clear backup baseline for the new mode:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Verify that the backup completes, archived redo logs are backed up, and the control file/SPFILE are protected. Do not assume that a successful ALTER DATABASE ARCHIVELOG alone constitutes a backup plan.

## 7. Switching from ARCHIVELOG to NOARCHIVELOG

This change reduces recovery capability. Perform it only after approval and acceptance of the corresponding RPO.

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE NOARCHIVELOG;
ALTER DATABASE OPEN;
~~~

Verify:

~~~sql
SELECT log_mode
FROM v$database;
~~~

After switching, take a new consistent backup following the NOARCHIVELOG procedure. Do not continue relying on the previous online backup schedule as if the recovery mode were unchanged.

## 8. Changing ARCHIVELOG in RAC

In Oracle RAC, each instance has its own redo thread. Switching the log mode requires stopping the instances and performing the operation in the database mount state according to the version's RAC procedure.

Overview procedure:

1. Stop the database using Clusterware/SRVCTL per the runbook.
2. Ensure no instances still have the database open.
3. Start one instance in MOUNT mode.
4. Switch to ARCHIVELOG or NOARCHIVELOG.
5. Open the database.
6. Start the remaining instances.
7. Verify archive destinations for all threads.
8. Confirm that sequences from each thread are being archived.

Do not run ALTER DATABASE ARCHIVELOG while other RAC instances still have the database open.

## 9. Configuring Archive Destinations

Oracle can store archived redo logs in multiple destinations. Common parameters include:

- LOG_ARCHIVE_DEST_n: defines the destination.
- LOG_ARCHIVE_DEST_STATE_n: ENABLE/DEFER/ALTERNATE depending on configuration.
- LOG_ARCHIVE_MIN_SUCCEED_DEST: minimum number of destinations that must succeed in archiving under the applicable configuration.
- LOG_ARCHIVE_FORMAT: filename format in traditional filesystem configurations; keep version and Oracle Managed Files/FRA behavior in mind.
- DB_RECOVERY_FILE_DEST: FRA location.
- DB_RECOVERY_FILE_DEST_SIZE: FRA size limit.

Example local destination:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=/u04/oracle/arch VALID_FOR=(ALL_LOGFILES,ALL_ROLES) DB_UNIQUE_NAME=ORCL'
    SCOPE = BOTH;
~~~

Example remote service destination in Data Guard:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_2 =
    'SERVICE=STBY ASYNC VALID_FOR=(ONLINE_LOGFILES,PRIMARY_ROLE) DB_UNIQUE_NAME=STBY'
    SCOPE = BOTH;
~~~

Attributes such as VALID_FOR, DB_UNIQUE_NAME, SERVICE, ASYNC/SYNC, and broker settings must match the Data Guard design. Do not copy example strings verbatim into production.

### 9.1 ENABLE and DEFER

You can enable or defer a destination using:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_STATE_2 = ENABLE SCOPE = BOTH;
~~~

Or:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_STATE_2 = DEFER SCOPE = BOTH;
~~~

DEFER can stop sending/archiving to the corresponding destination. If the destination is a standby, monitor transport lag and ensure there is a plan to recover missing sequences.

### 9.2 Multiple Destinations Do Not Replace Independent Backups

Sending archives to two filesystems on the same storage array does not protect well against a cluster-wide storage failure. A local destination and an off-site/immutable backup serve different purposes.

## 10. Fast Recovery Area (FRA)

The Fast Recovery Area is an Oracle-managed storage area for recovery-related files. Depending on configuration, the FRA can contain:

- Archived redo logs.
- Flashback logs.
- RMAN backup pieces.
- Control file autobackups.
- Certain other recovery files.

The FRA is not an independent backup if it resides on the same storage system as the database. Backups must be copied to a separate storage/failure domain.

### 10.1 Configuring the FRA

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST =
    '/u03/oracle/fra'
    SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE =
    200G
    SCOPE = BOTH;
~~~

DB_RECOVERY_FILE_DEST_SIZE is the Oracle-managed capacity limit for the FRA, not necessarily equal to the physical free space on the filesystem.

### 10.2 Monitoring the FRA

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

Calculate usage percentage:

~~~sql
SELECT name,
       ROUND(space_used * 100 / NULLIF(space_limit, 0), 2) AS pct_used,
       ROUND(space_reclaimable * 100 /
             NULLIF(space_limit, 0), 2) AS pct_reclaimable
FROM v$recovery_file_dest;
~~~

SPACE_RECLAIMABLE is the portion Oracle estimates can be reclaimed according to file management rules; it is not a guarantee that every byte can be deleted immediately.

### 10.3 When the FRA Approaches Capacity

Symptoms may include:

- The archive destination can no longer write new files.
- Log switches slow down or fail to complete.
- The database raises errors related to inability to archive.
- RMAN backups cannot write additional pieces.
- Flashback logs cannot continue as required.

Do not delete archive files via the OS to free space while the database still manages those files. Use RMAN and an appropriate deletion policy.

## 11. Monitoring Archive Destinations

### 11.1 V$ARCHIVE_DEST

~~~sql
SELECT dest_id,
       status,
       binding,
       target,
       destination,
       error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

### 11.2 V$ARCHIVE_DEST_STATUS

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

Column names may vary between releases. Check dictionary view metadata before using generic monitoring scripts.

### 11.3 V$ARCHIVED_LOG

~~~sql
SELECT thread#,
       sequence#,
       first_change#,
       next_change#,
       completion_time,
       archived,
       applied,
       deleted,
       name
FROM v$archived_log
ORDER BY thread#, sequence#;
~~~

V$ARCHIVED_LOG can contain multiple records for the same thread/sequence because of multiple copies/destinations or backup/restore history. Do not count records as if every row always represents a unique archive log.

### 11.4 V$LOG_HISTORY

~~~sql
SELECT thread#,
       sequence#,
       first_change#,
       first_time
FROM v$log_history
ORDER BY first_time DESC;
~~~

This view is useful for reviewing log switch history by thread within the retained metadata window.

## 12. Calculating Archived Redo Generation Rate

Archive volume depends on workload. A system might generate little redo at night but spike sharply during batch imports or transaction processing.

You can estimate from archived logs:

~~~sql
SELECT TRUNC(completion_time, 'HH24') AS archive_hour,
       thread#,
       COUNT(DISTINCT sequence#) AS log_count
FROM v$archived_log
WHERE completion_time >= SYSDATE - 1
  AND name IS NOT NULL
GROUP BY TRUNC(completion_time, 'HH24'), thread#
ORDER BY archive_hour, thread#;
~~~

To estimate bytes, you can use V$ARCHIVED_LOG.BLOCKS and BLOCK_SIZE if your version includes these columns:

~~~sql
SELECT TRUNC(completion_time, 'HH24') AS archive_hour,
       thread#,
       SUM(blocks * block_size) AS archived_bytes
FROM v$archived_log
WHERE completion_time >= SYSDATE - 1
  AND name IS NOT NULL
GROUP BY TRUNC(completion_time, 'HH24'), thread#
ORDER BY archive_hour, thread#;
~~~

Records may represent multiple copies of the same sequence. When calculating actual disk usage, filter by the appropriate destination/copy or cross-check with the file inventory; do not double-count all records.

### 12.1 Capacity Estimation

A rough estimation formula:

~~~text
Required archive capacity
  ≈ peak redo generation per hour
    × hours to retain locally
    + safety margin
~~~

If archives are backed up every 4 hours but must be retained locally for 48 hours to support standby lag or recovery, capacity must cover at least that duration at a reasonable peak redo rate.

Do not use only average daily redo. Account for peak workloads, batch windows, and scenarios where archive backups are interrupted.

## 13. Log Switches and Archive Logs

Oracle switches redo log groups when a log fills or on command. For example:

~~~sql
ALTER SYSTEM SWITCH LOGFILE;
~~~

This command requests a log switch in the appropriate instance/session. In some situations, you can use:

~~~sql
ALTER SYSTEM ARCHIVE LOG CURRENT;
~~~

The ARCHIVE LOG CURRENT command requests archiving of the current redo log; exact behavior regarding switches and threads depends on the environment/version. In RAC, understand its impact across redo threads.

Do not run log switches continuously just to "force archiving" without a valid reason. Excessive log switching can increase overhead and create many small archive files.

### 13.1 Slow Archive Process

If ARCn cannot keep up:

- Redo log groups may not yet be reusable.
- The database may wait on log file switch/archive completion.
- Log switch-related waits may appear.

Check:

- Is the archive destination writable?
- Does the filesystem/FRA still have free space?
- Is the network destination/standby reachable?
- Are there errors in ARCn processes or the alert log?
- Is the log switch frequency too high?
- Can storage throughput keep up?

## 14. How a Full Archive Destination Affects the Database

In ARCHIVELOG mode, a redo log group cannot be reused until it has been successfully archived according to mandatory destination requirements.

If the archive destination becomes full:

1. ARCn cannot write archived logs.
2. Older redo log groups have not been archived yet.
3. As the other groups fill up one by one, the database runs out of groups eligible for reuse.
4. Log switches may hang or the database may stop writing redo.

Error messages may include ORA-00257 (archiver error) or destination-specific errors.

### 14.1 Safe Remediation

- Check V$RECOVERY_FILE_DEST.
- Check V$ARCHIVE_DEST_STATUS and ERROR.
- Verify actual storage space and quotas.
- Expand capacity or fix the destination issue.
- Back up archive logs with RMAN.
- Delete archive logs only through RMAN according to the deletion policy.
- Confirm that the archive process resumes normal operation.

Do not delete archive files needed by standby or recovery using filesystem commands.

## 15. RMAN and Backup Strategy

RMAN (Recovery Manager) is Oracle's tool for backing up, restoring, and recovering databases. RMAN understands database structure and backup metadata, managing backup sets, image copies, archived redo logs, and control files.

A backup strategy must define:

- Full/level 0 backup frequency.
- Incremental backup frequency.
- Archived redo log backup frequency.
- Control file and SPFILE backups.
- Retention policy.
- Archive log deletion policy.
- Off-site copies.
- Encryption and access control.
- Restore validation and drills.

### 15.1 Full Backup and Incremental Level 0

RMAN can create a full backup or an incremental level 0 backup. Level 0 serves as the baseline for an incremental backup chain; it differs in certain management aspects from a standard BACKUP DATABASE command.

Example:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Or:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 0 DATABASE PLUS ARCHIVELOG;
~~~

### 15.2 Incremental Level 1

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE PLUS ARCHIVELOG;
~~~

Level 1 can be differential or cumulative depending on configuration/command. Differential level 1 contains blocks changed since the most recent level 0 or level 1 backup; cumulative level 1 contains changes since the most recent level 0 backup.

Cumulative example:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
~~~

Chain design must balance backup duration, storage space, and restore time.

### 15.3 Backing Up Archived Redo Logs

~~~text
RMAN> BACKUP ARCHIVELOG ALL;
~~~

Or combined:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

PLUS ARCHIVELOG typically performs steps to archive the current log and back up related archived logs to support a consistent backup. Inspect RMAN output and policies to confirm that the required sequences were backed up.

### 15.4 Control File and SPFILE

Control file autobackup should be enabled:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

The control file stores critical metadata about the database and backups. The SPFILE stores instance configuration. Both must be protected to recover from the loss of the control file or server.

### 15.5 Backups Are Not Just Datafiles

A recoverable backup set may require:

- Datafile backups/image copies.
- Archived redo logs.
- Control file or control file autobackup.
- SPFILE.
- Password file and relevant connection/cluster configurations.
- Keystore/TDE keys if the database uses encryption.
- RMAN catalog if using a recovery catalog.
- Scripts/runbooks and inventory.

Do not store all secrets in the same uncontrolled backup directory.

## 16. Retention Policy and Archive Log Deletion Policy

The RMAN retention policy defines which backups must be kept to meet a recovery window or redundancy target.

Recovery window example:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
~~~

Redundancy example:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

The two policies express different goals:

- Recovery window: keep enough backups to recover to any point within the specified time frame, according to RMAN rules.
- Redundancy: keep the configured number of backup copies.

### 16.1 Archive Log Deletion Policy

Example allowing archived logs to be deleted only after being backed up at least once to disk:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
     TO BACKED UP 1 TIMES TO DEVICE TYPE DISK;
~~~

In Data Guard, you can configure a policy to wait until logs are shipped or applied on standby:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
     TO APPLIED ON ALL STANDBY;
~~~

Exact syntax and options depend on the version, number of standbys, and operational requirements. An APPLIED ON ALL STANDBY policy can cause archive logs to be retained longer if a standby lags or goes down; capacity must be planned accordingly.

### 16.2 BACKUP ARCHIVELOG ... DELETE INPUT

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

RMAN backs up the archive logs and deletes input copies according to applicable rules. Do not use this command without verifying:

- The backup completed successfully.
- The deletion policy is appropriate.
- Standby has received/applied logs if required.
- Sequences needed for recovery still have a copy.
- The backup can be read/restored.

DELETE INPUT and DELETE ALL INPUT have different deletion scopes for copies across multiple destinations. Read the RMAN documentation carefully before using them.

### 16.3 Do Not Delete Archives via the OS

If you delete files directly with rm/del/PowerShell, the RMAN repository and database may still think the files exist. Conversely, the database may end up missing archives needed for recovery or standby.

Use RMAN CROSSCHECK, DELETE EXPIRED, and DELETE ARCHIVELOG according to file management procedures. Do not run DELETE EXPIRED as a substitute for backups or to delete needed files.

## 17. Backup Consistency

A backup must be sufficiently consistent to be restored and recovered.

### 17.1 Online Backups in ARCHIVELOG

In ARCHIVELOG mode, RMAN supports backing up while the database is open using appropriate procedures. Archived redo logs are used to recover datafile backups to a consistent state.

Example:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Do not copy open datafiles with the OS and assume the result is a consistent backup. If using user-managed backups, you must follow the BEGIN BACKUP/END BACKUP procedure and back up the corresponding archived redo logs; RMAN is generally the simpler and safer choice.

### 17.2 Offline Consistent Backups in NOARCHIVELOG

In NOARCHIVELOG, the database must be shut down cleanly, mounted, and not open when taking a standard consistent RMAN database backup.

Example procedure:

~~~text
SQL> SHUTDOWN IMMEDIATE;
SQL> STARTUP MOUNT;

RMAN> BACKUP DATABASE;
RMAN> BACKUP CURRENT CONTROLFILE;
RMAN> BACKUP SPFILE;

SQL> ALTER DATABASE OPEN;
~~~

Depending on configuration, RMAN may automatically back up the control file/SPFILE via autobackup. Check output and configuration so you do not create uncontrolled redundant copies.

## 18. Media Recovery in ARCHIVELOG

Media recovery applies redo to bring restored datafiles to a consistent state.

Scenario of losing a single datafile:

1. Identify the corrupted/missing datafile.
2. Restore the datafile from backup.
3. Apply required archived redo logs.
4. Open the database or bring the tablespace/datafile online as appropriate.

Overview example:

~~~text
RMAN> RESTORE DATAFILE 7;
RMAN> RECOVER DATAFILE 7;
~~~

If the database remains open and conditions allow, recovery can be performed at the datafile/tablespace level without shutting down the entire database. Specifics depend on failure type, tablespace, and configuration.

### 18.1 Full Database Restore/Recover

~~~text
RMAN> STARTUP MOUNT;
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
RMAN> ALTER DATABASE OPEN;
~~~

This is the framework for complete recovery with an intact control file and suitable backups. If using a backup control file or performing incomplete recovery, OPEN RESETLOGS may be required per the rules.

### 18.2 Complete Recovery and Incomplete Recovery

- Complete recovery: applies all redo up to the current state or desired recovery point without skipping required redo.
- Incomplete recovery: stops at a time/SCN/sequence before the present, such as before a user accidentally deleted data.

Incomplete recovery generally requires OPEN RESETLOGS after recovery finishes.

## 19. Point-in-Time Recovery (PITR)

PITR recovers the database to a point in time prior to the present. It is useful when:

- A transaction accidentally deletes data.
- A batch job performs mass incorrect writes.
- A deployment causes irreversible data changes.
- Logical corruption is discovered later.

Prerequisites:

- A valid backup taken prior to the target recovery time.
- Complete archived redo logs from the backup up to the target time.
- Required control file/SPFILE and configuration.
- Required keystore if the database uses TDE.

RMAN overview example:

~~~text
RMAN> RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 10:30:00',
             'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

This example illustrates syntax only. The target time must be determined according to the database's timezone and clock. If the database uses CDB/PDB or Data Guard, select the appropriate PITR type and scope.

### 19.1 RESETLOGS Creates a New Incarnation

After incomplete recovery and OPEN RESETLOGS, the database starts a new incarnation. Backups and archived redo logs belonging to the old incarnation may still be needed for other recovery operations, so they must be managed via RMAN metadata.

After PITR, create a new backup according to your defined strategy to establish a recovery baseline for the current incarnation.

### 19.2 PITR Is Not Flashback Database

Flashback Database uses flashback logs to rewind the database to an earlier point within retention limits. PITR uses backups and redo recovery. The two mechanisms complement each other but do not completely replace one another.

Flashback Database requires configuration and FRA space; it also does not replace independent backups.

## 20. Data Guard and ARCHIVELOG

Physical standby/Data Guard relies on redo transport and redo apply to maintain a database replica. ARCHIVELOG is the foundation of this process.

Components:

- Primary database generates redo.
- Log transport sends redo to the standby.
- Standby receives redo via standby redo logs or archived logs depending on the mode.
- Redo Apply applies redo to update the standby.

### 20.1 Standby Redo Logs

Standby redo logs (SRLs) receive redo from the primary during real-time apply or transport. SRLs should be configured with sufficient groups/sizes per thread according to Oracle rules for Data Guard architecture.

Do not confuse SRLs with archived redo logs. SRLs receive redo on the standby; archived redo logs are completed logs archived for retention/apply.

### 20.2 Monitoring Archive Gaps

On the standby:

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

If this view returns rows, there may be an archive gap requiring remediation. Having no rows does not by itself prove every aspect of Data Guard is healthy; check transport/apply lag and broker status as well.

### 20.3 Monitoring Data Guard Lag

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN (
    'transport lag',
    'apply lag',
    'apply finish time'
);
~~~

V$DATAGUARD_STATS is meaningful in the appropriate database role. Also check V$ARCHIVE_DEST_STATUS, V$MANAGED_STANDBY, or the corresponding view for your release.

### 20.4 Deletion Policy Must Account for Standby

If archives are deleted before the standby receives/applies them, gaps can occur and slow down or halt recovery. RMAN deletion policies must reflect standby requirements.

Do not delete archive logs solely because a local backup succeeded if the Data Guard policy requires the standby to apply them first.

## 21. RAC and Redo Threads

In RAC, each instance has its own redo thread. Therefore:

- Archive logs must be managed for every thread.
- Sequence numbers can overlap across threads.
- Backups/recovery must retain sufficient archives for all required threads.
- Monitoring should group by THREAD# and INST_ID when appropriate.

Example:

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       archived
FROM v$log
ORDER BY thread#, sequence#;
~~~

To view archived logs:

~~~sql
SELECT thread#,
       sequence#,
       completion_time,
       name
FROM v$archived_log
WHERE name IS NOT NULL
ORDER BY thread#, sequence#;
~~~

Sequence 500 on thread 1 is not the same log as sequence 500 on thread 2. When handling gaps or backups, always track the thread.

## 22. Force Logging and Supplemental Logging

### 22.1 FORCE LOGGING

FORCE LOGGING instructs the database to generate redo for operations that might otherwise be performed as NOLOGGING in certain cases.

Check:

~~~sql
SELECT force_logging
FROM v$database;
~~~

Enable at the database level:

~~~sql
ALTER DATABASE FORCE LOGGING;
~~~

FORCE LOGGING is commonly considered in Data Guard environments to reduce the risk of missing data on the standby due to NOLOGGING operations. It can increase redo generation and I/O.

### 22.2 Supplemental Logging

Supplemental logging adds extra redo information required by certain solutions such as logical replication/LogMiner/GoldenGate. It is not the same as ARCHIVELOG mode and does not replace backups.

Check:

~~~sql
SELECT supplemental_log_data_min,
       supplemental_log_data_pk,
       supplemental_log_data_ui,
       supplemental_log_data_fk,
       supplemental_log_data_all
FROM v$database;
~~~

Enable supplemental logging only according to replication/audit requirements and the relevant product documentation.

## 23. Designing a Data Protection Plan

A solid plan must start from business requirements:

- **RPO (Recovery Point Objective):** what is the maximum acceptable data loss in terms of time?
- **RTO (Recovery Time Objective):** how quickly must the database be operational again?
- Retention: how long must backups be kept?
- Failure domain: must it survive file, disk, server, site failure, or ransomware?
- Data sensitivity: do backups contain sensitive data?
- Recovery scope: do you need to recover a datafile, tablespace, database, PDB, or an entire site?

### 23.1 RPO and Log Mode

| Requirement | Design Direction |
|---|---|
| Acceptable to lose all changes since last backup | NOARCHIVELOG may be considered for suitable environments |
| Acceptable to lose a few hours of data | ARCHIVELOG + periodic archive backups meeting RPO |
| Need recovery close to time of failure | ARCHIVELOG + continuous archive backup/transport and monitoring |
| Need a DR site | ARCHIVELOG + Data Guard or equivalent DR solution |
| Need fast recovery after human error | Backups + archived redo; consider Flashback if required |

Actual RPO also depends on archive backup frequency, redo transport, archive destinations, and restore capability.

### 23.2 RTO and Backup Architecture

RTO depends on:

- Database size.
- Backup read speed.
- Number of incremental backups.
- RMAN parallelism capability.
- Redo apply speed.
- Time to restore control file/SPFILE/keystore.
- Validation and application startup time.

Simply having backups does not guarantee fast recovery. Restore/recover times must be measured on representative data volumes.

## 24. The 3-2-1 Backup Model and Immutable Copies

A commonly used principle:

- Maintain at least 3 copies of data/backups.
- Store on at least 2 different media types or failure domains.
- Keep at least 1 copy off-site.

Against ransomware and accidental deletion:

- Use immutable/object-lock backups if supported by policy and platform.
- Separate database admin privileges from backup deletion privileges.
- Do not use the same credentials for the database and the backup repository.
- Maintain an offline or air-gapped copy if required.
- Audit the backup catalog and inventory.

These are design principles and do not replace RPO/RTO targets or restore testing.

## 25. Backing Up the Control File, SPFILE, and Metadata

The control file stores metadata about datafiles, redo logs, checkpoints, and backup history. The SPFILE stores instance configuration.

In RMAN:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Back up SPFILE:

~~~text
RMAN> BACKUP SPFILE;
~~~

Back up current control file:

~~~text
RMAN> BACKUP CURRENT CONTROLFILE;
~~~

If the control file is lost, the DBID may be required to restore the control file autobackup. Record the DBID, database name, DB_UNIQUE_NAME, and connection details in the recovery runbook.

### 25.1 Recovery Catalog

An RMAN recovery catalog is a separate repository storing backup metadata. It is useful when control file records are lost or when managing multiple databases. The catalog does not replace backup files and must be backed up and kept available separately.

If not using a catalog, the control file repository has its own retention and record limits. Ensure control file autobackups are protected.

## 26. Verifying Backups and Recovery Drills

A successful backup job only proves that the backup command completed according to its output. It does not prove the database can be recovered within the RTO.

Verification steps:

- Review RMAN LIST BACKUP.
- CROSSCHECK backups/archives against the repository.
- Run RESTORE VALIDATE or VALIDATE as needed.
- Verify archived log sequence continuity.
- Restore to an isolated environment.
- Recover to a target point in time.
- Open the database and run smoke tests.
- Measure actual elapsed time.

Example:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> RESTORE DATABASE VALIDATE;
~~~

RESTORE VALIDATE verifies readability of the required backups within the command scope, but does not replace a full restore/recover/open test.

### 26.1 Checking Archived Log Sequences

Track sequences by thread and SCN. A missing archive gap can prevent recovery from advancing past the required point.

### 26.2 Restore Drills

Schedule drills for:

- Full database restore.
- Single datafile restore.
- Point-in-time recovery.
- Control file restore.
- Keystore recovery if using TDE.
- Switchover/failover if using Data Guard.

Each drill should record elapsed time, manual steps, encountered errors, and time until the application is operational again.

## 27. Example Backup Plan for Production

Hypothetical example:

- Maximum RPO of 15 minutes.
- Target RTO of 2 hours.
- 2 TB database.
- Data Guard standby present.
- Weekly full/level 0 backup and daily incremental backups.
- Archived redo logs backed up every 15 minutes or based on space/redo rate.

An illustrative schedule:

| Task | Example Frequency | Objective |
|---|---|---|
| Level 0/full baseline | Weekly | Restore baseline |
| Level 1 incremental | Daily | Reduce backup duration |
| Archived log backup | 15 minutes or suitable threshold | Reduce redo loss if backup repository fails |
| Control file autobackup | After backup/structural changes per RMAN | Protect metadata |
| Off-site/immutable copy | Based on backup repository RPO | Protect against site loss/ransomware |
| Restore validate | Daily/weekly per policy | Detect corrupted backups |
| Full restore drill | Per DR schedule | Validate actual RTO |

This is only an example. A real schedule must be based on redo generation rate, storage, batch windows, retention, Data Guard lag, and business-approved RPO/RTO.

## 28. NOARCHIVELOG Backup Plan for Regenerable Environments

If an environment genuinely accepts NOARCHIVELOG:

1. Define the downtime window.
2. Stop data-writing applications.
3. Shut down the database with SHUTDOWN IMMEDIATE.
4. Start up in MOUNT mode.
5. Take a consistent RMAN backup.
6. Back up the control file/SPFILE.
7. Copy backups off-host.
8. Open the database.
9. Start applications only after verification.
10. Drill restoring to the most recent backup.

If the database cannot be stopped long enough, NOARCHIVELOG may not meet operational requirements.

## 29. Common Incidents

| Symptom | Possible Cause | Investigation Path |
|---|---|---|
| ORA-00257 archiver error | Archive destination full or unwritable | V$ARCHIVE_DEST_STATUS, FRA, filesystem |
| Log switch waiting | Archive/checkpoint incomplete or group cannot be reused | V$LOG, V$ARCHIVE_DEST, alert log |
| FRA nearly full | Archives/backups/flashback retaining space | V$RECOVERY_FILE_DEST, RMAN retention |
| RMAN cannot find archive | Sequence not backed up, deleted, or missing metadata | LIST/CROSSCHECK, V$ARCHIVED_LOG |
| Recovery stops at sequence | Archive gap or missing file | Thread/sequence/SCN and backups |
| Standby lag increasing | Network, transport, apply, or archive gap | V$DATAGUARD_STATS, V$ARCHIVE_DEST_STATUS |
| Restore cannot open database | Missing redo, control file, or inconsistent backup | RMAN output, alert log, incarnation |
| NOARCHIVELOG fails to back up while OPEN | Mode requires consistent closed backup | Clean shutdown, MOUNT, then back up |
| Must OPEN RESETLOGS after PITR | Incomplete recovery creates a new incarnation | RMAN catalog/incarnation and new backup |
| Archive logs deleted outside RMAN | Repository out of sync with filesystem | CROSSCHECK and recovery impact assessment |

## 30. Common Mistakes

| Mistake | Consequence | Correct Approach |
|---|---|---|
| Thinking ARCHIVELOG alone is a backup | Archives may reside on the same disk and be lost with the database | Back up archives to another failure domain |
| Thinking online redo and archived redo are the same | Loss of redo history required for media recovery | Distinguish redo groups, members, and archives |
| Using NOARCHIVELOG for production needing PITR | Cannot apply archive chain after backup | Choose ARCHIVELOG and design backups |
| Switching mode while database is OPEN | Command requires MOUNT state | Shutdown, startup mount, alter mode |
| Not backing up after enabling ARCHIVELOG | Lack of a clear backup baseline | Create a full/level 0 backup after conversion |
| Deleting archives via OS | Loss of sequences needed by RMAN/standby | Use RMAN deletion policy |
| Deleting archives immediately after local backup | Standby may not have applied them yet | Configure deletion policy for Data Guard |
| Sizing FRA too small | Archives cannot be written; log switches are impacted | Size for peak redo and retention |
| Measuring only average redo | Cannot survive batch peaks | Use peak generation and safety margin |
| Not backing up control file/SPFILE | Difficult to recover configuration/metadata | Enable autobackup and store in runbook |
| Running only RESTORE VALIDATE | Does not prove open/recover succeeds | Perform restore drills |
| Ignoring TDE keys | Restored datafiles cannot be decrypted | Back up/restore keystore alongside database |
| Confusing sequences across RAC threads | Missing or mistakenly deleting archives | Track THREAD# + SEQUENCE# |
| Switching to NOARCHIVELOG while keeping online backup schedule | Backup jobs may become invalid | Redesign cold backup procedures |
| Treating Flashback as a backup | FRA/flashback logs can be lost with storage | Maintain independent backups |

## 31. Self-Check Practice Exercises

Run these exercises only in a lab database or an environment approved by the DBA.

### Exercise 1 — Check Log Mode

Use V$DATABASE and ARCHIVE LOG LIST. Record LOG_MODE, archive destination, and current sequence.

### Exercise 2 — Inspect Redo Log Groups

Query V$LOG and V$LOGFILE. Identify the current group, thread, member count, and status.

### Exercise 3 — Switch to ARCHIVELOG

In a lab, perform a clean shutdown, startup mount, ALTER DATABASE ARCHIVELOG, and then open. Confirm the mode and take a baseline backup.

### Exercise 4 — Generate Archive Logs

Execute some transactions, switch logs in the lab, view V$ARCHIVED_LOG, and identify the thread/sequence.

### Exercise 5 — Configure the FRA

Set DB_RECOVERY_FILE_DEST and SIZE in the lab. Query V$RECOVERY_FILE_DEST and monitor usage after a backup.

### Exercise 6 — Back Up Database Plus Archives

Use RMAN BACKUP DATABASE PLUS ARCHIVELOG. Read the output, LIST BACKUP, and confirm that archive logs were backed up.

### Exercise 7 — Incremental Backups

Create a level 0 backup, modify data, and create level 1 differential and cumulative backups. Compare sizes and restore chains.

### Exercise 8 — Deletion Policy

In a lab without standby, configure a backup count policy. Test BACKUP ARCHIVELOG ALL DELETE INPUT and inspect RMAN metadata.

### Exercise 9 — Media Recovery

In an isolated environment, simulate losing a datafile, then restore and recover using archived redo.

### Exercise 10 — PITR

Create data, take a backup, make an erroneous change, and recover to a time before the change. Confirm OPEN RESETLOGS and the new incarnation.

### Exercise 11 — Archive Stats/Monitoring

Monitor V$ARCHIVE_DEST_STATUS, V$RECOVERY_FILE_DEST, and V$ARCHIVED_LOG. Simulate an unavailable destination in the lab.

### Exercise 12 — Data Guard/RAC Review

Read thread/sequence and archive gap views on an available environment. Build a checklist for archive synchronization, standby redo logs, and deletion policy.

## 32. Data Protection Checklist

**Mode**

- Has LOG_MODE been verified?
- Do RPO/RTO require ARCHIVELOG?
- Is Data Guard or PITR in use?
- Does NOARCHIVELOG genuinely tolerate losing data after the last backup?

**Redo/Archive**

- Are online redo logs properly multiplexed?
- Do archive destinations have sufficient capacity and redundancy?
- Are all RAC threads monitored?
- Has peak archive log generation been measured?
- Does the FRA have threshold alerting?

**RMAN**

- Are full/level 0 and incremental backups properly scheduled?
- Are archived redo logs backed up frequently enough?
- Are control file autobackup and SPFILE protected?
- Are retention and deletion policies clearly defined?
- Are archives never deleted via the OS?

**DR/Recovery**

- Are off-site/immutable copies maintained?
- Is the keystore backed up if TDE is used?
- Are the DBID and restore runbook documented?
- Has restore validate been run?
- Have restore/recover/open drills been performed?
- Has actual RTO been measured?

**Data Guard/RAC**

- Are transport/apply lags monitored?
- Are standby redo logs configured?
- Are archive gaps handled?
- Does the deletion policy wait for standby as required?
- Are keys and backups synchronized after rotation?

## 33. Key Takeaways

| Concept | Key Point |
|---|---|
| Redo | Change information used for recovery |
| Online redo log | Log groups currently written cyclically by LGWR |
| Redo log member | Copy of a member within the same group |
| Archived redo log | Copy of a completed redo log group |
| ARCHIVELOG | Retains redo history, supporting media recovery/PITR |
| NOARCHIVELOG | Does not archive new redo; media recovery is limited |
| LOG_MODE | Current status in V$DATABASE |
| ARCHIVE LOG LIST | Displays mode and archive information from SQL*Plus/SQLcl |
| FRA | Oracle-managed area for recovery files |
| RMAN | Backs up, restores, and recovers databases |
| Level 0 | Baseline for an incremental backup strategy |
| Level 1 | Backs up blocks changed since baseline/previous backup |
| Retention policy | Defines which backups must be retained |
| Deletion policy | Defines when archive logs become eligible for deletion |
| CROSSCHECK | Reconciles repository metadata with physical files |
| Media recovery | Restores backup and applies redo |
| PITR | Recovers to a prior point in time/SCN |
| RESETLOGS | Opens the database after certain incomplete recoveries, creating a new incarnation |
| Data Guard | Transports and applies redo to a standby |
| Standby redo log | Receives redo on the standby |
| FORCE LOGGING | Forces redo generation for operations that could be NOLOGGING within scope |
| RPO | Maximum acceptable data loss |
| RTO | Target time to restore service |
| Restore drill | Actual restore/recover rehearsal |

ARCHIVELOG preserves the redo needed to recover a database beyond its last backup and serves as the foundation for Data Guard; NOARCHIVELOG is suitable only when the organization accepts recovering to the most recent consistent backup and has a downtime window. Regardless of the mode chosen, a data protection plan must include datafile backups, control files, SPFILE, archive logs where applicable, TDE keystores, off-site copies, and restore drills. Monitor archive destinations/FRA, manage retention with RMAN, and never delete archive logs directly at the operating system level. RPO/RTO targets are only validated once restore/recovery drills have been executed and actual elapsed times measured.
