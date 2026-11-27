# Backing Up the Database, Tablespaces, Datafiles, Control File, and SPFILE
An Oracle backup strategy must protect both the data and the metadata required to start and recover the database. Whole-database backups enable recovery after major failures; tablespace or datafile backups support narrower recovery scopes; the control file holds the database structure and recovery information; and the SPFILE stores instance startup parameters. Archived redo logs allow advancing data from the backup point to a target SCN or point in time.

Oracle Recovery Manager (RMAN) is the primary tool for managing backup and recovery. RMAN understands database structure, tracks backup metadata, supports online backups in ARCHIVELOG mode, validates backups, and automatically selects the backups and redo required during a restore. This lesson focuses on RMAN; user-managed examples are used only to explain file roles and special cases.

The content uses Oracle Database 19c as a baseline, covering:
- Components to back up and the role of each component.
- Full database, incremental, tablespace, and datafile backups.
- Control file, SPFILE, autobackup, and backup metadata.
- Archived redo log backups, FRA, and retention policies.
- RMAN channels, formats, tags, compression, and encryption.
- Backup verification, restore preview, validate, and crosscheck.
- Restoring and recovering the whole database, tablespaces, datafiles, control file, and SPFILE.
- CDB/PDB backups, operational strategies, common errors, and labs.

RMAN syntax, options, and capabilities may vary by release, edition, storage configuration, RAC, and CDB/PDB. Always verify against the RMAN Reference for your exact version and rehearse restores in an isolated environment before changing production.

## 1. Why back up multiple file types?

An Oracle database is not just a collection of datafiles. To recover a database, the related components must be protected:

| Component | Contents | Role during recovery |
| --- | --- | --- |
| Datafiles | Tables, indexes, undo, and database data | Primary data source to restore |
| Control files | Database structure, file names, checkpoints, redo history | Mount the database and coordinate recovery |
| SPFILE/PFILE | Instance startup parameters | Start the instance with the right configuration |
| Online redo logs | Most recent redo for each redo thread | Instance recovery and certain media recoveries |
| Archived redo logs | Archived copies of filled redo logs | Recover from backup to target SCN/time |
| Password file | Remote SYSDBA/SYSOPER authentication credentials | Administrative connections when needed |
| RMAN repository/catalog | Backup metadata, incarnations, files, and logs | Locate backups and plan restores |
| Wallet/keystore | Encryption keys and certificates depending on features | Open encrypted backups/databases or secure connections |

An RMAN database backup normally includes datafiles within the database scope. The control file and SPFILE must be protected explicitly or via control file autobackup. Archived redo logs must be backed up according to the recovery strategy. Online redo logs must not be backed up like ordinary active files; protect them using Oracle-supported mechanisms with proper multiplexing and/or standby.

### 1.1. Backup and recovery are a pair

A successful backup only proves that backup creation completed according to the tool. It does not prove that the database can be recovered within the required RTO/RPO.

A practical plan must answer:
- Is there a backup recent enough to meet the RPO?
- Are all archived redo logs available from the backup up to the target SCN?
- Is there a control file/SPFILE or recovery catalog to locate backups?
- Can the database be restored to a different host/storage?
- Are the required wallets/keys available to open encrypted backups?
- How long does restore/recover take?
- Who is authorized to execute the recovery and verify application functionality afterward?

## 2. RMAN and the repository

RMAN (Recovery Manager) is the Oracle utility used for backup, restore, recovery, and metadata management.

### 2.1. Connecting to RMAN

On a host with Oracle software and appropriate administrative privileges:

~~~bash
rman target /
~~~

Or connect to the target using credentials per security policy:

~~~bash
rman target sys@ORCL
~~~

Never put passwords directly on the command line, in scripts, or in shared logs. You can use a recovery catalog:

~~~bash
rman target / catalog rman_user@RCVCAT
~~~

### 2.2. Control file repository

If no recovery catalog is used, RMAN stores backup metadata in the target database's control file. The control file can reuse old records based on CONTROL_FILE_RECORD_KEEP_TIME and record section space limits.

Therefore, the control file must be backed up frequently. If the control file is lost and there is no recovery catalog, locating backups may require control file autobackup and the DBID.

### 2.3. Recovery catalog

A recovery catalog is a separate repository schema that retains RMAN metadata longer and can manage multiple target databases. It does not store datafile backups; backup pieces still reside on disk, tape, or a media manager.

A recovery catalog helps:
- Retain backup history longer than control file records.
- Manage multiple databases.
- Support certain restore/recovery operations when the control file is lost.
- Track incarnations and backup metadata.

The recovery catalog itself must also be backed up and protected. Do not treat the catalog as a replacement for control files or datafile backups.

### 2.4. Viewing RMAN configuration

In RMAN:

~~~text
SHOW ALL;
SHOW RETENTION POLICY;
SHOW CONTROLFILE AUTOBACKUP;
SHOW DEVICE TYPE;
SHOW CHANNEL;
~~~

Configuration is stored in the control file repository or recovery catalog depending on the environment. Before making changes, save the `SHOW ALL` output so you can restore the previous settings.

## 3. Whole-database backup

Whole-database backup is the foundation of a backup strategy. When the database is in ARCHIVELOG mode, RMAN can back it up while the database is open.

### 3.1. Basic database backup

~~~text
BACKUP DATABASE;
~~~

RMAN backs up the required database datafiles using the current device/configuration. By default, backups usually create backup sets unless AS COPY is specified.

You can attach a tag for easy identification:

~~~text
BACKUP DATABASE TAG 'WEEKLY_FULL';
~~~

A tag is a DBA-chosen label, not a unique backup ID. RMAN still uses the backup key, completion time, checkpoint SCN, and metadata to identify backups.

### 3.2. Backing up the database and archived logs

A commonly used command:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

This command instructs RMAN to back up the required archived redo logs along with the database. RMAN performs an archive log switch and backs up logs in the command's sequence to ensure the redo needed for the online backup is captured.

For higher reliability, check job output, backup lists, and archived log coverage after running. If the backup destination or FRA fills up, the job may fail midway; you must determine what completed and what needs to be rerun.

### 3.3. Including the current control file

~~~text
BACKUP DATABASE INCLUDE CURRENT CONTROLFILE;
~~~

This command includes the current control file in the backup set alongside the database. If CONTROLFILE AUTOBACKUP is enabled, RMAN may also create a separate autobackup afterward. Understand the actual output and configuration so you do not assume there is only one control file copy.

### 3.4. Full backup and level 0 incremental

In RMAN, a full backup and an incremental level 0 are not identical:
- A full backup can serve as a restore base, but cannot act as a parent for an incremental level 1.
- An incremental level 0 is the baseline for incremental level 1 backups.

Example:

~~~text
BACKUP INCREMENTAL LEVEL 0 DATABASE TAG 'L0_BASE';
~~~

If using an incremental strategy, retain the level 0 along with required level 1s and archived redo per the retention policy.

## 4. Incremental backup

An incremental backup stores only blocks that have changed since a lower-level incremental backup or corresponding reference point. It reduces backup duration and storage when the database is large and daily change volume is small.

### 4.1. Level 0

~~~text
BACKUP INCREMENTAL LEVEL 0 DATABASE;
~~~

Level 0 contains the blocks RMAN considers necessary to establish an incremental baseline. It is the starting point for a level 1 chain.

### 4.2. Level 1 differential

~~~text
BACKUP INCREMENTAL LEVEL 1 DATABASE;
~~~

By default, level 1 is differential: it backs up blocks changed since the most recent applicable level 1 or level 0 incremental backup.

### 4.3. Level 1 cumulative

~~~text
BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
~~~

Cumulative level 1 backs up blocks changed since the most recent level 0 backup. It is usually larger than differential across multiple runs, but can simplify the incremental chain needed during recovery.

### 4.4. Comparison

| Type | Block scope | Advantages | Trade-off |
| --- | --- | --- | --- |
| Full backup | Blocks needed for a full datafile backup | Simple restore management | Large time/storage footprint |
| Incremental level 0 | Incremental baseline | Acts as parent for level 1 | Often close to full in volume |
| Level 1 differential | Changes since latest level 1/level 0 | Smaller backups under many workloads | Restore may need multiple incrementals |
| Level 1 cumulative | Changes since latest level 0 | Fewer level 1s to apply | Each run can be larger |

### 4.5. Block Change Tracking

Block Change Tracking (BCT) helps RMAN identify changed blocks without scanning entire datafiles during incremental backups. Example:

~~~sql
ALTER DATABASE ENABLE BLOCK CHANGE TRACKING
USING FILE '/u03/oradata/ORCL/bct01.ctf';
~~~

Verification:

~~~sql
SELECT status, filename, bytes
FROM v$block_change_tracking;
~~~

BCT has overhead and requires a separate tracking file. If the file is lost, RMAN can continue incremental backups by reading more blocks; BCT is not sole recovery data needed to recover the database.

## 5. Backing up tablespaces

Tablespace backups help protect or restore a related group of datafiles. RMAN backs up the datafiles belonging to the tablespace.

### 5.1. Backing up a single tablespace

~~~text
BACKUP TABLESPACE users TAG 'USERS_WEEKLY';
~~~

Multiple tablespaces can be backed up:

~~~text
BACKUP TABLESPACE users, app_data, app_index;
~~~

Tablespace names must match the current database. Use `REPORT SCHEMA` to inspect the database structure before running.

### 5.2. Viewing tablespaces and datafiles

~~~sql
SELECT
    tablespace_name,
    file_id,
    file_name,
    bytes,
    status
FROM dba_data_files
ORDER BY tablespace_name, file_id;
~~~

In RMAN:

~~~text
REPORT SCHEMA;
~~~

`REPORT SCHEMA` is useful to see which datafiles belong to which tablespace and the file numbers recognized by RMAN.

### 5.3. When to back up individual tablespaces?

- One tablespace changes much faster than the rest.
- There is a requirement for scoped recovery.
- Separate backup/restore schedules are feasible.
- An extra backup is needed before major changes in a specific data area.

However, backing up one tablespace does not protect the entire database. SYSTEM, SYSAUX, undo, and business tablespaces with dependencies must be protected under an overall strategy.

### 5.4. Read-only tablespaces

Read-only tablespaces change rarely and can be backed up less frequently if policy allows. However, restorable backups and valid metadata must still be retained. When a tablespace transitions from READ ONLY to READ WRITE, update the backup schedule since data can change again.


## 6. Backing up datafiles

Individual datafile backups are useful when a file is large or needs its own backup schedule.

### 6.1. Backing up by file number

~~~text
BACKUP DATAFILE 4 TAG 'USERS_DF4';
~~~

Multiple files can be backed up:

~~~text
BACKUP DATAFILE 4, 5, 6;
~~~

Obtain the file number from V$DATAFILE/REPORT SCHEMA. Never guess a file number from the file name.

### 6.2. Backing up by file name

~~~text
BACKUP DATAFILE '/u02/oradata/ORCL/users01.dbf';
~~~

The file name must match the path recognized by the database/control file. When using ASM or OMF, the name may be an alias or ASM path; check `REPORT SCHEMA` first.

### 6.3. Backing up newly created datafiles

After adding a datafile or tablespace, check control file metadata and ensure the new file is included in the backup schedule. Control file autobackup preserves structural metadata changes, but does not replace backing up the contents of the new datafile.

~~~sql
SELECT
    file#,
    name,
    status,
    creation_change#
FROM v$datafile
ORDER BY file#;
~~~

### 6.4. Backing up a single datafile does not replace archived redo

Each datafile backup has its own checkpoint SCN. On restore, Oracle may need archived redo from the file's checkpoint up to the target SCN. Full log sequences must be kept for every required thread.

If you only back up datafile 4 and delete older archived logs needed for that file, a restore may fail to recover to the current point in time.

## 7. Backing up the control file

The control file is critical for mounting the database and identifying file structure. Losing the control file can prevent the database from mounting or opening properly.

### 7.1. Enabling control file autobackup

In RMAN:

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

When enabled, RMAN creates a control file autobackup after backup jobs and certain structural database changes per RMAN behavior. If the database uses an SPFILE, control file autobackup typically includes the SPFILE as well.

Autobackup allows restoring the control file even when the current control file repository is lost. Verify the autobackup format and location, especially when using FRA, custom disk formats, or a media manager.

### 7.2. Configuring the autobackup format

Disk example:

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP FORMAT
FOR DEVICE TYPE DISK TO '/backup/ORCL/<UNIQUE_RMAN_AUTOBACKUP_NAME>';
~~~

RMAN enforces a unique autobackup naming convention based on DBID/date/sequence. Ensure the directory exists, is writable, and is backed up to appropriate storage.

If you change the format, record the path for restores in case the control file is lost. When the control file is missing, RMAN has no current repository to know custom formats automatically unless the DBA specifies them.

### 7.3. Manually backing up the current control file

~~~text
BACKUP CURRENT CONTROLFILE TAG 'CONTROLFILE_MANUAL';
~~~

You can also back up the control file alongside the database:

~~~text
BACKUP DATABASE INCLUDE CURRENT CONTROLFILE;
~~~

Autobackup should still be configured per policy. Manual backups are useful before/after major structural changes or when a clearly tagged control file backup is needed.

### 7.4. Backing up the control file to trace

You can generate a script describing the control file structure:

~~~sql
ALTER DATABASE BACKUP CONTROLFILE TO TRACE
AS '/secure/backup/controlfile_create.sql' REUSE;
~~~

The trace file is a `CREATE CONTROLFILE` script, not a binary control file replacement for autobackup. It can assist in recreating the control file in certain scenarios, but must be protected and updated whenever the database structure changes.

### 7.5. Multiplexing control files

CONTROL_FILES can specify multiple control file copies across different storage locations. Multiplexing allows the database to stay available if one copy is damaged or lost, but it does not replace backing up the control file to an independent location.

## 8. Backing up the SPFILE

The SPFILE is the binary server parameter file holding instance configuration. Losing the SPFILE can prevent the database from starting with the desired configuration.

### 8.1. Backing up the SPFILE with RMAN

~~~text
BACKUP SPFILE TAG 'SPFILE_DAILY';
~~~

If CONTROLFILE AUTOBACKUP is on and the database uses an SPFILE, RMAN can include the SPFILE inside the control file autobackup. Backing up the SPFILE explicitly is still useful for clarity and easy retrieval.

### 8.2. Creating a text PFILE to save configuration

~~~sql
CREATE PFILE='/secure/backup/initORCL.ora' FROM SPFILE;
~~~

A PFILE is a text file that is easy to inspect and version-control. Protect the file because it may contain sensitive parameters such as wallet locations, audit destinations, encryption configuration, or environment details.

### 8.3. Restoring the SPFILE from autobackup

If the control file is intact and the database can mount, RMAN can restore the SPFILE from the repository. If both the control file and SPFILE are lost, start in NOMOUNT using a minimal temporary PFILE or use the DBID to locate the autobackup.

General example:

~~~text
STARTUP NOMOUNT;
RESTORE SPFILE FROM AUTOBACKUP;
SHUTDOWN IMMEDIATE;
STARTUP NOMOUNT;
~~~

The exact restore command depends on autobackup location, DBID, and recovery catalog. Without a control file or recovery catalog, use `SET DBID` before searching for autobackups and specify the format if needed.

### 8.4. Never edit a binary SPFILE with a text editor

To change parameters, use `ALTER SYSTEM SET` with the appropriate SCOPE, or create a PFILE and recreate the SPFILE following procedure. Never open a binary SPFILE in a text editor and never copy an SPFILE from another database without adjusting DB_NAME, control_files, memory, diagnostic, and storage settings.

## 9. Backing up archived redo logs

Archived redo logs are required to recover from a backup to a subsequent SCN or time.

### 9.1. Backing up all archived logs

~~~text
BACKUP ARCHIVELOG ALL TAG 'ARCH_DAILY';
~~~

### 9.2. Backing up archived logs not yet backed up

~~~text
BACKUP ARCHIVELOG ALL NOT BACKED UP 1 TIMES;
~~~

Use DEVICE TYPE DISK/SBT or configure channels to write to the appropriate media.

### 9.3. Backing up and deleting archived logs

Example:

~~~text
BACKUP ARCHIVELOG ALL DELETE INPUT TAG 'ARCH_BACKUP';
~~~

DELETE INPUT deletes the backed-up archived log inputs according to the command and device context. Understand which copies have been created and the multi-copy retention policy before using it. Never use DELETE INPUT as a substitute for a retention policy or delete logs before confirming the backup is safe.

`DELETE ALL INPUT` can be used in certain multi-copy backup strategies; verify RMAN syntax and the desired number of backup copies.

### 9.4. Archived logs by sequence/thread

In RAC, redo is separated by thread. Example:

~~~text
BACKUP ARCHIVELOG FROM SEQUENCE 120 UNTIL SEQUENCE 145 THREAD 1;
~~~

Specify the correct sequence and thread. Never assume sequences are continuous across the cluster without checking thread numbers.

### 9.5. Checking archive mode and destinations

~~~sql
ARCHIVE LOG LIST;
~~~

~~~sql
SELECT
    dest_id,
    status,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE';
~~~

If an archive destination fills up, the database can stall when it needs to archive redo logs to reuse log groups. Monitor the FRA, archive destinations, and backup jobs.

## 10. Fast Recovery Area (FRA)

The FRA is a storage location managed by Oracle for recovery-related files such as archived logs, flashback logs, control file autobackups, and RMAN backup pieces depending on configuration.

### 10.1. Configuring the FRA

Example:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest_size = 200G SCOPE=BOTH;
ALTER SYSTEM SET db_recovery_file_dest = '/u04/oracle/fra' SCOPE=BOTH;
~~~

The actual order must follow the release's parameter requirements; in some cases, set the size before setting the destination. Check current values:

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
~~~

### 10.2. Monitoring the FRA

~~~sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable,
    number_of_files
FROM v$recovery_file_dest;
~~~

Monitor utilization percentage, reclaimable files, and archived log growth rate. A full FRA can halt archiving and impact database availability.

### 10.3. The FRA is not an independent backup

If the FRA resides in the same storage failure domain as the database, a storage failure can destroy both datafiles and backups. For DR requirements, copy backups and archived logs to an independent storage system or site per policy.

## 11. RMAN channels, backup sets, and image copies

### 11.1. Channel

A channel is an RMAN session/process used to read and write backups. Channels can be configured for DISK or SBT (tape/media manager).

Example:

~~~text
CONFIGURE DEVICE TYPE DISK PARALLELISM 2;
CONFIGURE CHANNEL DEVICE TYPE DISK FORMAT '/backup/ORCL/backup_%d_%T_%U.bkp';
~~~

PARALLELISM automatically allocates multiple channels for the device type. When using a media manager, configure the SBT library and channel parameters according to the vendor's guide.

### 11.2. Backup set

A backup set is an RMAN format containing one or more backup pieces. A backup piece is a physical file on disk or tape. RMAN manages metadata to track which blocks/files each backup set contains.

Example:

~~~text
BACKUP AS BACKUPSET DATABASE;
~~~

Backup sets generally store only needed blocks and can be compressed and encrypted according to configuration.

### 11.3. Image copy

An image copy is a copy of a datafile or control file identical in format to the original file:

~~~text
BACKUP AS COPY DATABASE;
~~~

An image copy can be used with `SWITCH DATAFILE/TABLESPACE TO COPY` in certain workflows to switch directly to the copy. It typically occupies nearly as much space as the original file, but can reduce restore time since it does not require extracting a backup set in the usual way.

### 11.4. Compression

Example:

~~~text
BACKUP AS COMPRESSED BACKUPSET DATABASE;
~~~

Compression reduces storage usage but consumes CPU and can affect throughput. Choose the compression algorithm/level according to licensing, edition, release, and configuration. Measure backup duration, CPU, bytes, and restore time before rolling out broadly.

### 11.5. Encryption

RMAN can encrypt backup sets. You can use transparent encryption based on an Oracle keystore or password-based encryption per policy. Example enabling encryption for database backups in RMAN config:

~~~text
CONFIGURE ENCRYPTION FOR DATABASE ON;
~~~

In a password-based workflow, `SET ENCRYPTION` syntax must follow the RMAN Reference and the password must be managed separately. If the password or required keystore key is lost, encrypted backups may be unrecoverable.

Protect the keystore/wallet alongside backup metadata. Never store encryption passwords in scripts, source control, or the same backup directory without access controls.

## 12. Retention policy and managing old backups

The retention policy determines which backups must be retained to satisfy a recovery window or redundancy target.

### 12.1. Recovery window

Example retaining recoverability for 14 days:

~~~text
CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
~~~

### 12.2. Redundancy

Example retaining at least two valid backups per policy:

~~~text
CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

Recovery window and redundancy have different semantics. Choose based on RPO/RTO and storage capacity; do not pick arbitrarily.

### 12.3. REPORT OBSOLETE and DELETE OBSOLETE

~~~text
REPORT OBSOLETE;
~~~

After verifying:

~~~text
DELETE OBSOLETE;
~~~

Obsolete means a backup is no longer needed under the retention policy. RMAN does not necessarily delete obsolete backups immediately when a new backup completes.

### 12.4. CROSSCHECK and EXPIRED

~~~text
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK compares the repository against physical media. Backups not found are marked EXPIRED.

After verifying:

~~~text
LIST EXPIRED BACKUP;
DELETE EXPIRED BACKUP;
~~~

Distinguish between:
- EXPIRED: RMAN could not find the file/media at the recorded location during crosscheck.
- OBSOLETE: backup no longer needed under the retention policy.

Do not use `DELETE EXPIRED` to delete files that are still needed; this command primarily updates repository records when media no longer exists. Never delete backup files via the OS before understanding crosscheck and retention logic.

## 13. Sample backup schedule

The exact schedule depends on RPO/RTO, change volume, storage capacity, and backup duration. A reference model for an ARCHIVELOG database:

| Schedule | Example task | Goal |
| --- | --- | --- |
| Weekly | Incremental level 0 or full | Baseline |
| Daily | Incremental level 1 | Reduce backup volume |
| Every 15–60 minutes | Back up archived logs per workload | Shrink redo loss window |
| Daily | Control file/SPFILE autobackup | Protect metadata |
| Daily/weekly | Crosscheck and report | Verify repository/media |
| Monthly | Restore validation/restore drill | Prove recoverability |
| Periodic | Offsite copy and recovery test | Disaster recovery |

This is only a sample schedule. If a 5-minute RPO is required, backing up archived logs hourly will not suffice; design appropriate archiving, redo transport, and backups. RPO depends not only on backup intervals, but also on redo shipping, storage durability, and failover procedures.


## 14. Restoring and recovering the database

Restore copies datafiles/control files/SPFILE from backups to the required locations. Recover applies redo to advance files to the target SCN.

### 14.1. Complete database recovery

Example where all datafiles need to be restored and the current control file is still usable:

~~~text
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

These commands run in RMAN. If the database is already mounted, there is no need to run `STARTUP MOUNT` again.

RMAN selects the appropriate backups and applies archived/online redo according to the repository and target. Ensure sufficient media, passwords/keystore if backups are encrypted, and all required archive log sequences.

### 14.2. Restoring a single datafile

Example where file 4 is lost/corrupted and the database is in ARCHIVELOG mode:

~~~text
SQL 'ALTER DATABASE DATAFILE 4 OFFLINE';
RESTORE DATAFILE 4;
RECOVER DATAFILE 4;
SQL 'ALTER DATABASE DATAFILE 4 ONLINE';
~~~

Identify the file number/path, tablespace, and database state. Critical files such as SYSTEM/undo have offline restrictions and require different recovery procedures. Never take a file offline without understanding application impact.

### 14.3. Restoring a single tablespace

~~~text
SQL 'ALTER TABLESPACE users OFFLINE IMMEDIATE';
RESTORE TABLESPACE users;
RECOVER TABLESPACE users;
SQL 'ALTER TABLESPACE users ONLINE';
~~~

Adjust the example according to database mode, tablespace status, and dependencies. For SYSTEM, undo, or critical tablespaces, standard offline procedures do not apply.

### 14.4. Restoring the control file from autobackup

If the control file is lost and no recovery catalog is used, the DBID is needed to locate the autobackup. In RMAN:

~~~text
SET DBID 1234567890;
STARTUP NOMOUNT;
RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
~~~

The DBID in the example is just a placeholder. Retrieve the real DBID from backup logs, RMAN output, the database inventory, or metadata records. If the autobackup format was customized, specify the exact format/path.

After mounting, restore/recover the database per the scenario and open with RESETLOGS if the recovery path requires it.

### 14.5. Restoring the SPFILE from autobackup

When both the control file and SPFILE are lost, start in NOMOUNT using a minimal PFILE or use RMAN with the DBID to locate the autobackup:

~~~text
SET DBID 1234567890;
STARTUP FORCE NOMOUNT;
RESTORE SPFILE FROM AUTOBACKUP;
SHUTDOWN IMMEDIATE;
STARTUP NOMOUNT;
~~~

Exact syntax and PFILE/DBID/autobackup format requirements depend on the actual situation. After restoring the SPFILE, verify `CONTROL_FILES`, `DB_NAME`, `DB_UNIQUE_NAME`, memory, and storage path parameters before mounting.

### 14.6. Restoring the control file and OPEN RESETLOGS

If the control file is restored from a backup, the database typically requires media recovery using the backup control file procedure and `OPEN RESETLOGS`. `RESETLOGS` creates a new incarnation. Afterward:
- Back up the database immediately per policy.
- Verify the incarnation in RMAN.
- Continue backing up archived logs.
- Check standby/replication if applicable.
- Update recovery documentation.

Never run `OPEN RESETLOGS` arbitrarily for complete recovery with a current control file unless the recovery path requires it.

## 15. CDB/PDB backup and restore

In a multitenant architecture, a CDB contains the root, seed, and one or more PDBs. RMAN can back up the entire CDB or scope down to specific PDBs/tablespaces as needed.

### 15.1. Backing up the entire CDB

Connect RMAN to the CDB root:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

The whole-database backup command covers files belonging to the CDB scope per RMAN. Check RMAN reports and backup lists to verify PDBs and datafiles are covered.

### 15.2. Backing up a single PDB

Example:

~~~text
BACKUP PLUGGABLE DATABASE salespdb;
~~~

The PDB must be in a state and condition compatible with the operation. Connect to the CDB root per RMAN procedures and use the exact PDB name.

### 15.3. Backing up tablespaces inside a PDB

PDB/tablespace-scoped syntax depends on the RMAN version and container context. Use `REPORT SCHEMA`, consult the RMAN Reference, and confirm the tablespace name inside the target PDB before backing up. Avoid confusing identically named tablespaces across different PDBs.

### 15.4. Restoring/recovering a PDB

RMAN supports restoring and recovering a PDB and its datafiles. The procedure depends on PDB state, control file, root metadata, and recovery targets. Some operations require the PDB to be closed or in a specific state; use the official syntax for your release and test on a lab copy.

### 15.5. CDB/PDB backup strategy

- Back up the root, control file, and SPFILE on the CDB schedule.
- Protect archived redo for all relevant redo threads/containers.
- Back up individual PDBs separately if they have different RPO/RTO requirements.
- Verify plug/unplug, relocation, and file name conversion.
- Preserve DBID, DB_UNIQUE_NAME, PDB GUID, and required metadata.
- Test restoring a PDB without impacting other PDBs.

## 16. Database backup with RMAN: sample script

Simple example script for a daily disk backup:

~~~text
RUN {
  ALLOCATE CHANNEL c1 DEVICE TYPE DISK;
  BACKUP AS COMPRESSED BACKUPSET
    DATABASE
    TAG 'DAILY_DB';
  BACKUP ARCHIVELOG ALL NOT BACKED UP 1 TIMES
    TAG 'DAILY_ARCH';
  BACKUP CURRENT CONTROLFILE
    TAG 'DAILY_CONTROLFILE';
  BACKUP SPFILE
    TAG 'DAILY_SPFILE';
  RELEASE CHANNEL c1;
}
~~~

If `CONTROLFILE AUTOBACKUP` is enabled, additional control file backups may be created per policy. Customize the sample script for:
- Destination/format.
- Channel parallelism.
- Compression.
- Encryption.
- Archived log deletion policy.
- Retention policy.
- Error handling and monitoring.
- CDB/PDB scope.

Never embed passwords directly in scripts. Use a wallet/secret store or managed RMAN encryption mechanisms.

## 17. Checking backup quality

### 17.1. LIST BACKUP

~~~text
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF TABLESPACE users;
LIST BACKUP OF DATAFILE 4;
LIST BACKUP OF CONTROLFILE;
LIST BACKUP OF SPFILE;
LIST BACKUP OF ARCHIVELOG ALL;
~~~

`LIST` commands show which records exist in the RMAN repository and which backups are available according to metadata.

### 17.2. RESTORE PREVIEW

~~~text
RESTORE DATABASE PREVIEW;
RESTORE TABLESPACE users PREVIEW;
RESTORE DATAFILE 4 PREVIEW;
~~~

`PREVIEW` indicates which backups RMAN intends to use without actually restoring.

### 17.3. RESTORE VALIDATE

~~~text
RESTORE DATABASE VALIDATE;
RESTORE TABLESPACE users VALIDATE;
RESTORE DATAFILE 4 VALIDATE;
~~~

`VALIDATE` reads required backup pieces to verify readability and suitability per RMAN. It does not replace an actual restore to another host, opening the database, and verifying applications.

### 17.4. BACKUP VALIDATE

~~~text
BACKUP VALIDATE DATABASE;
~~~

`BACKUP VALIDATE` reads datafiles and checks blocks without writing normal backup pieces. It can generate substantial I/O; choose an appropriate window and scope.

### 17.5. Restore Drill

A restore drill should:
1. Use an independent host/storage.
2. Retrieve the control file/SPFILE and backup pieces.
3. Restore the keystore/wallet if needed.
4. Restore the database.
5. Apply archived redo to the target.
6. Open the database per recovery path.
7. Verify objects, row counts, and application smoke tests.
8. Measure actual durations.
9. Document issues and update the runbook.

## 18. Important Operational Considerations

### 18.1. RPO and RTO

- RPO: maximum acceptable data loss.
- RTO: maximum acceptable time to restore service.

A daily full backup may meet RTO yet fail RPO if archived redo is not protected frequently enough. Conversely, increasing backup frequency does not guarantee RTO if datafile restores take too long or media is missing.

### 18.2. Backup Retention and Offsite Copies

Retain backups per retention policy and copy them to another failure domain. If ransomware or operator error deletes backups on the same host as the database, backups sharing that storage may be lost too.

### 18.3. Backup Encryption

If backups are encrypted:
- Protect the wallet/keystore or password.
- Keep an independent backup of keys/keystore.
- Test restoring when the original host is gone.
- Document who is authorized to open backups.
- Never store backup passwords in the same backup directory.

### 18.4. Compression and Parallelism

Compression saves storage at the cost of CPU. Parallelism increases throughput but can overload storage or CPU. Measure against real workloads, monitor waits/I/O, and choose a sensible channel count.

### 18.5. Backups During Structural Database Changes

When adding/dropping datafiles, tablespaces, or renaming files, control file metadata changes. Control file autobackup and the RMAN repository help preserve metadata. Before major DDL operations, take a tagged backup or control file backup per change procedure.

### 18.6. Backing Up the Password File and Wallet

An RMAN database backup does not necessarily include external files such as the password file, listener config, wallets, TDE keystores, scripts, and external configs. Maintain a separate inventory of these files, protect them per policy, and test recovery on a separate host.

## 19. Common Errors

| Symptom | Possible Cause | Handling Approach |
| --- | --- | --- |
| RMAN cannot find backups | Different repository/control file, expired backup, or wrong DBID | Run `LIST`, `CATALOG START WITH`, verify catalog and DBID |
| ORA-19504 / ORA-27040 | Cannot create backup piece | Check path, permissions, free space, and storage |
| ORA-19809 / ORA-19804 | FRA quota exceeded / cannot reclaim space | Check FRA, backup/archive policy, and capacity |
| Database backup runs but misses archive logs | Incomplete archived log backup or destination error | Check thread/sequence coverage and alert log |
| Restore stops due to missing archived log | Required log sequence unavailable | Locate log backups, alternate media, or adjust target |
| Control file lost | Cannot mount using current control file | Restore from autobackup/recovery catalog; DBID needed if applicable |
| SPFILE lost | Instance cannot start with old configuration | Restore SPFILE or create temporary PFILE |
| Backup pieces marked `EXPIRED` | `CROSSCHECK` could not find media | Check storage/media manager before `DELETE EXPIRED` |
| `OBSOLETE` backups deleted | Retention policy misconfigured | Review `REPORT OBSOLETE` and adjust policy |
| Restore validate passes but DR fails | Control file, wallet, network, or app untested | Conduct full independent restore drill |
| Encrypted backup fails to restore | Missing password/keystore key | Restore the matching key/wallet and verify beforehand |
| Tablespace backup insufficient to restore | Missing archived redo or dependent files | Back up and retain required redo |
| New datafile lacks backup | Job scope/filter skipped new file | Run `REPORT SCHEMA` and update backup policy |
| PDB restored in wrong container | Confused tablespace/PDB name or connection context | Confirm CDB/PDB and RMAN scope |
| Backup too slow | Too few channels, slow storage, compression CPU | Measure throughput, CPU, waits, and channels |
| Backup succeeds but RPO missed | Archived log backup interval too long | Adjust archive backup/transport cadence |

## 20. Daily Backup Runbook

An operational runbook should include:

### Pre-Backup
- Confirm database is open and check `LOG_MODE`.
- Check FRA/archive destinations.
- Verify RMAN `SHOW ALL` and retention.
- Verify backup storage/media manager health.
- Review errors from the most recent backup job.
- Confirm control file autobackup and SPFILE protection.

### During Backup
- Run scheduled database/incremental backup.
- Back up archived redo logs.
- Back up control file/SPFILE or verify autobackup.
- Log tags, start/end times, bytes, and output logs.
- Monitor channels, throughput, errors, and storage.

### Post-Backup
- Run `LIST BACKUP SUMMARY`.
- Run `CROSSCHECK` per schedule.
- Run `RESTORE PREVIEW`/`VALIDATE` within scope.
- Run `REPORT OBSOLETE` before `DELETE OBSOLETE`.
- Confirm required archived logs were backed up.
- Report monitoring results per organizational process.
- Schedule restore drills.

Never mark a backup job successful from exit code alone if logs contain warnings/errors or archived logs/control files were skipped.

## 21. Lab: Backing Up Each Component with RMAN

Run in an Oracle lab with RMAN privileges and isolated storage.

### 21.1. Explore the Structure

In SQL*Plus:

~~~sql
SELECT name, open_mode, log_mode, current_scn
FROM v$database;

SELECT file#, name, status
FROM v$datafile
ORDER BY file#;

SELECT name
FROM v$tablespace
ORDER BY name;
~~~

In RMAN:

~~~text
REPORT SCHEMA;
SHOW ALL;
~~~

### 21.2. Whole-Database Backup

~~~text
BACKUP DATABASE TAG 'LAB_FULL';
~~~

If the lab is in ARCHIVELOG mode:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG TAG 'LAB_DB_ARCH';
~~~

### 21.3. Tablespace Backup

~~~text
BACKUP TABLESPACE USERS TAG 'LAB_USERS';
~~~

Replace `USERS` with an actual lab tablespace.

### 21.4. Datafile Backup

~~~text
BACKUP DATAFILE 4 TAG 'LAB_DF4';
~~~

Use only a file number confirmed from `REPORT SCHEMA`/`V$DATAFILE`.

### 21.5. Control File and SPFILE Backup

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
BACKUP CURRENT CONTROLFILE TAG 'LAB_CONTROLFILE';
BACKUP SPFILE TAG 'LAB_SPFILE';
~~~

Verify:

~~~text
LIST BACKUP OF CONTROLFILE;
LIST BACKUP OF SPFILE;
~~~

### 21.6. Archived Log Backup

~~~text
BACKUP ARCHIVELOG ALL TAG 'LAB_ARCH';
LIST BACKUP OF ARCHIVELOG ALL;
~~~

### 21.7. Validate

~~~text
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
RESTORE TABLESPACE USERS VALIDATE;
RESTORE DATAFILE 4 VALIDATE;
~~~

Record output and backup keys for the restore exercises.

## 22. Lab: Restoring in an Isolated Environment

Never restore over an active database. Use an auxiliary host/database or an isolated lab instance.

### 22.1. Restoring the Database

Using the lab backups:
- Prepare Oracle Home and storage.
- Prepare PFILE/SPFILE and control file.
- Connect to RMAN.
- Restore control file if needed.
- Mount the database.
- Restore the database.
- Recover the database to the target.
- Open per the recovery path.
- Verify datafiles and application.

### 22.2. Restoring a Tablespace/Datafile

Simulate losing one lab file:
- Take the file offline per database rules.
- Restore the datafile/tablespace from backup.
- Recover using archived redo.
- Bring the file/tablespace back online.
- Verify objects and data.

### 22.3. Restoring the Control File/SPFILE

Simulate using another lab database or clone:
- Start in `NOMOUNT`.
- Use the DBID and autobackup format if needed.
- Restore SPFILE/control file.
- Restart using the proper SPFILE.
- Mount, restore/recover datafiles.
- Open the database as required.

Never delete the sole control file or SPFILE of an active database for practice.

## 23. Practice Exercises

### Exercise 1 — Full Database Backup

Run `BACKUP DATABASE` and read `LIST BACKUP SUMMARY`. Record backup set, piece, tag, completion time, and checkpoint SCN.

### Exercise 2 — Level 0/Level 1

Take a level 0, run some DML, then take differential and cumulative level 1 backups. Compare bytes and backup durations.

### Exercise 3 — Tablespace Backup

Back up a lab tablespace. List the datafiles in that tablespace and inspect `RESTORE TABLESPACE PREVIEW`.

### Exercise 4 — Datafile Backup

Back up a single datafile. Record file number, checkpoint, and archived redo needed for recovery.

### Exercise 5 — Control File Autobackup

Enable `CONTROLFILE AUTOBACKUP`, run a backup, and locate the autobackup piece. Identify the DBID/format needed to restore if the control file is lost.

### Exercise 6 — SPFILE

Back up the SPFILE and create a text PFILE. Compare key parameters; never share secrets/credentials inside the PFILE.

### Exercise 7 — Archived Redo

Back up archived logs on an interval, check sequence/thread numbers, and test `RESTORE ARCHIVELOG PREVIEW`/`VALIDATE` per RMAN release.

### Exercise 8 — Retention

Set a recovery window in the lab, run `REPORT OBSOLETE`, and explain why each backup is retained or eligible for deletion.

### Exercise 9 — Compression/Encryption

Compare compressed and uncompressed backups. If a lab wallet/keystore is available, enable backup encryption and rehearse restoring with the matching key.

### Exercise 10 — Restore Drill

Recover the lab database in an independent environment. Record actual RTO, recovered SCN, archived logs used, errors encountered, and updates needed for the runbook.

## 24. Cleaning Up and Restoring the Lab Environment

- Confirm the lab database is `OPEN` and datafiles are `ONLINE`.
- Keep lab backups needed for restore exercises; delete via RMAN policy once finished.
- Do not delete archived logs still required for recovery.
- Revert any modified RMAN configuration back to pre-lab settings.
- Disable BCT or remove BCT files only when planned and no longer needed.
- Verify FRA still has free space.
- Do not delete backup pieces directly via OS while the RMAN repository still references them.
- Never delete the database's sole control file, SPFILE, or wallet.

## Summary

RMAN can back up the entire database, tablespaces, and datafiles; the control file and SPFILE are protected by explicit backups or control file autobackup; archived redo logs enable recovery from a backup checkpoint to a target SCN/time. Incremental level 0/1 balances storage and backup duration; backup sets, image copies, channels, compression, and encryption offer varied operational options.

Restore and recovery are two separate steps: `RESTORE` retrieves files from backup, and `RECOVER` applies redo. A database backup does not replace control file/SPFILE backups and archived logs. Individual tablespace/datafile backups also require redo coverage. Verify using `LIST`, `CROSSCHECK`, `RESTORE PREVIEW`, and `VALIDATE`, though only an independent restore drill proves end-to-end recoverability.

Build backup schedules around RPO/RTO, store backups in an independent failure domain, protect encryption keys, monitor FRA and archived log sequences, and maintain runbooks for both whole-database and component-level restores. Never judge success solely by backup job completion; the ultimate goal is recovering data and services within committed timeframes.

## Oracle Reference Documentation

- [Oracle Database Backup and Recovery User's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN strategies, database/tablespace/datafile backups, and restore/recovery.
- [Oracle Database Backup and Recovery Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/) — RMAN `BACKUP`, `RESTORE`, `RECOVER`, `CONFIGURE`, `LIST`, and `VALIDATE` syntax.
- [Oracle Database Administrator's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — control files, SPFILE, redo, archive mode, and database structure.
- [Oracle Database Reference — V$DATAFILE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAFILE.html) — datafile metadata.
- [Oracle Database Reference — V$RECOVERY_FILE_DEST (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RECOVERY_FILE_DEST.html) — Fast Recovery Area capacity and status.
- [Oracle Database Reference — V$BLOCK_CHANGE_TRACKING (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-BLOCK_CHANGE_TRACKING.html) — block change tracking status.
- [Oracle Database Backup and Recovery User's Guide — Multitenant Backup and Recovery (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — CDB and PDB backup/recovery per release.

When deploying on an Oracle release other than 19c, verify against the corresponding RMAN Reference and Backup and Recovery User's Guide, especially PDB backup syntax, autobackup formats, encrypted backups, retention, media managers, and control file restore/recovery.
