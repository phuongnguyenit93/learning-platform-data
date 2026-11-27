# RMAN Repository, Control File, and Recovery Catalog

Recovery Manager (RMAN) is the Oracle Database tool used for backup, recovery, and managing backup lifecycles. When RMAN executes a backup or restore command, it needs to know which datafiles the database has, which backups have been created, where backup pieces are located, which archived redo logs are available, and which incarnation the database is currently in. This collection of metadata is called the **RMAN repository**.

The RMAN repository can be stored in the target database's control file or in a recovery catalog located in another database. The control file is always a core component of the database and can store the repository without installing a recovery catalog. A recovery catalog is an optional additional metadata store, useful when longer history is required, when managing multiple databases centrally, or when using stored scripts.

It is critical to distinguish metadata from backup data. The repository records which backups were created and where they reside; the actual data blocks remain inside backup pieces on disk, tape, or the corresponding storage device. Having a repository without the backup pieces means you cannot recover data from those backups. Conversely, if backup pieces still exist while metadata is lost, they can be registered back into the repository using `CATALOG` commands in appropriate cases.

## 1. What Information Does the RMAN Repository Store?

The repository is the information source RMAN uses to plan and execute backups, restores, and recoveries, as well as to check backup status. Metadata typically includes:

- Database identity such as DBID, database name, and incarnation information.
- Database structure: datafiles, tablespaces, control files, and redo logs relevant to backup/recovery.
- Backup sets, backup pieces, image copies, backup type, tags, start/completion times, and backup status.
- Backed-up datafiles and archived redo logs, checkpoint SCNs, and information required to determine recoverability.
- Location, handle name, and device type holding backup pieces.
- Persistent RMAN configuration such as retention policy, default device type, channels, compression, encryption, and control file autobackup.
- Structural changes to the database and information needed to track backups across those changes.

Some metadata has different lifecycles and storage behavior depending on the repository in use. The control file has record sections with reuse capabilities; a recovery catalog can retain longer history and centralize information across multiple target databases.

### The Repository Does Not Store Backup Contents

Consider an example command:

```rman
BACKUP DATABASE PLUS ARCHIVELOG;
```

RMAN reads the database structure, creates backup sets/pieces on the configured device, and writes metadata describing the outcome to the repository. The repository can tell you which handle a backup piece has, which backup set it belongs to, and when it was created. The actual blocks of datafiles and archived redo logs are stored inside the backup pieces, not embedded inside the control file or recovery catalog.

Therefore, three layers must be protected simultaneously:

1. **Backup data**: backup pieces, image copies, and archived redo logs on storage devices.
2. **Control file**: contains database structure and the local RMAN repository, and is essential for mount, restore, and recovery.
3. **Recovery catalog (if used)**: holds additional metadata in a separate database and requires its own backup/recovery plan.

## 2. Two Places to Store the RMAN Repository

```text
                         RMAN client
                              |
                    target connection
                              |
                              v
                     Target database
                              |
                    +---------+---------+
                    |                   |
                    v                   v
             Control file          Datafiles / redo
             RMAN repository       Database contents
                    |
                    | resynchronization
                    v
             Recovery catalog database
             (optional, separate DB)
                    |
                    v
             Catalog schema / RC_* metadata

Backup data files are stored separately on disk, tape or another device.
```

### 2.1. Control File Repository

When RMAN connects to a target database without specifying a recovery catalog, RMAN uses the target's control file as the repository. This mode is commonly referred to as **NOCATALOG**.

The control file stores records of backups, archived redo logs, database structure, and RMAN configuration. When RMAN creates a backup, corresponding records are written to the control file. During a restore, RMAN reads this metadata to locate suitable backups and determine the next steps.

Advantages:

- No need to deploy an additional database solely to store RMAN metadata.
- Simple configuration and operations; RMAN can back up/restore directly using the control file.
- Suitable for standalone databases or environments that do not need long-term centralized RMAN history.

Limitations:

- Record space in the control file is finite and certain records can be reused per control file management rules.
- Older backup history may become incomplete if records are overwritten or purged from the repository.
- If all control files are lost without a recovery catalog, locating backups for recovery relies heavily on control file autobackups, DBID, and accessible backup information.
- No convenient central store for managing metadata across multiple target databases.

### 2.2. Recovery Catalog Repository

A recovery catalog is a dedicated schema residing in a separate Oracle Database from the target database. This schema contains RMAN tables, views, and metadata. RMAN connects simultaneously to both the target database and the catalog database to record, query, and synchronize the repository.

A recovery catalog is typically useful when:

- You need to retain backup history longer than records can be retained in the control file.
- Managing backups for multiple target databases from one place.
- You want centralized reporting on backups, archived logs, incarnations, and RMAN configuration.
- You need to use stored scripts kept in the recovery catalog.
- You want an additional metadata source when the target's control file is lost or damaged.

The recovery catalog does not contain datafiles or backup pieces. It stores metadata about those backups and their locations. During recovery, RMAN still needs access to the actual backup data and still needs a suitable control file to mount the database and perform recovery.

### 2.3. RMAN Can Be Used Without a Recovery Catalog

A recovery catalog is optional. A database can use RMAN in NOCATALOG mode and store metadata in the control file. If a recovery catalog is deployed later, you can create the catalog, connect to both target and catalog, and register the database to synchronize metadata.

Using a recovery catalog does not make the control file unnecessary. Oracle still uses the control file to operate the database, and it remains an essential component of restore/recovery. The recovery catalog simply adds an independent metadata store.

## 3. The Control File and Its Role in RMAN

The control file is a small but critical binary file in Oracle Database. It stores metadata describing the database structure and state needed for Oracle to mount, open, and recover the database.

Key information stored in the control file includes:

- Database name, DBID, and database creation information.
- Names and locations of datafiles and online redo log files.
- Checkpoints and synchronization information required for instance recovery and media recovery.
- Information on backups, archived redo logs, and RMAN repository records.
- Information related to database incarnations and certain structural changes.

If all copies of the control file are lost, the database cannot mount normally until the control file is restored or recreated via an appropriate procedure. Therefore, the control file must be multiplexed, backed up, and stored on devices independent of primary database files whenever possible.

### 3.1. Checking Active Control Files

```sql
SHOW PARAMETER control_files;

SELECT name, status
FROM v$controlfile;
```

`CONTROL_FILES` shows the list of control file paths used by the instance. Oracle maintains multiplexed control files with identical contents. When writing to the control file, Oracle writes to all configured copies; losing one copy can be handled by restoring from a healthy copy per operational procedure, but multiplexing should never be treated as a substitute for backups.

### 3.2. Control File Autobackup

RMAN can automatically back up the control file. When enabled, RMAN creates a control file autobackup according to its rules after backup operations and qualifying structural changes to the database. If the database uses an SPFILE, the autobackup can also include the SPFILE to assist instance startup if startup configuration is lost as well.

Enable control file autobackup:

```rman
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

You can specify a format for autobackups on disk:

```rman
CONFIGURE CONTROLFILE AUTOBACKUP FORMAT FOR DEVICE TYPE DISK
  TO '/backup/oracle/%F';
```

`%F` is a substitution variable that formats a recognizable control file autobackup name, including DBID and sequence information per RMAN conventions. The path above is an example; choose an actual storage location and ensure write permissions, capacity, and accessibility during disaster recovery.

You can explicitly create a control file backup:

```rman
BACKUP CURRENT CONTROLFILE;
```

Control file autobackup is especially valuable when the control file is lost and the database cannot be mounted. In NOCATALOG mode, RMAN may need the DBID to locate the autobackup when no control file or catalog connection is available.

### 3.3. `CONTROL_FILE_RECORD_KEEP_TIME`

The control file has record sections used to store backup and archived log information. Some sections use a circular reuse mechanism: older records can be overwritten when space is needed. The `CONTROL_FILE_RECORD_KEEP_TIME` parameter sets the minimum number of days Oracle attempts to keep reusable records before they become eligible for overwrite.

Check the parameter:

```sql
SHOW PARAMETER control_file_record_keep_time;
```

Do not mistake this parameter for an RMAN retention policy or a guarantee that every record will strictly persist for the configured number of days. It governs record lifecycle inside the control file; the retention policy determines which backups must be kept to meet recovery requirements. The two mechanisms serve different purposes.

If a recovery catalog is used, metadata resynchronized to the catalog remains stored there even if older records in the control file are later reused. This is one reason a recovery catalog is helpful for long-term history. However, the catalog must be properly synchronized and backed up.

You can inspect the status of record sections:

```sql
SELECT
    type,
    record_size,
    records_total,
    records_used,
    first_index,
    last_index
FROM v$controlfile_record_section
ORDER BY type;
```

Pay particular attention to sections related to backups and archived logs when investigating why older metadata is no longer present in the control file.

### 3.4. Snapshot Control File

A snapshot control file is a consistent copy of the control file that RMAN uses during certain backup operations to read metadata without interference from concurrent updates to the active control file. This is distinct from a control file autobackup.

- **Snapshot control file**: a working copy used so RMAN can read metadata consistently.
- **Control file autobackup**: a saved backup of the control file that can be restored when needed.
- **Current control file**: the file Oracle uses to mount and run the database.

Do not confuse the snapshot control file with an independent backup that replaces a control file protection strategy.

## 4. Recovery Catalog: Components and Benefits

### 4.1. Deployment Structure

A recovery catalog deployment typically consists of:

1. A separate Oracle Database to host the catalog schema.
2. A dedicated database user/schema as the recovery catalog owner.
3. Appropriate tablespace and quota for the catalog schema.
4. Network connectivity and Oracle Net service from the RMAN client to the catalog database.
5. Connectivity from the RMAN client to the target database.

Separate the catalog database from the target database so metadata does not depend entirely on the very database being protected. The catalog database itself also needs its own backup, security, monitoring, and recovery testing strategy.

Do not use a regular application schema as the recovery catalog owner. Create a dedicated user, restrict access privileges, and protect catalog credentials like a critical operational asset.

### 4.2. Centralized Metadata for Multiple Target Databases

One recovery catalog can manage metadata for multiple registered databases. Each database is identified by its DBID; in Data Guard environments or related multi-database configurations, identifiers such as `DB_UNIQUE_NAME` must also be managed per Oracle configuration and release.

A centralized model allows DBAs to inspect backups across multiple databases through one catalog, generate reports, and apply unified operational workflows. However, permissions and retention policies must still be tailored to each database.

### 4.3. Long-Term History and Stored Scripts

The control file has record limits and can reuse old records. Because the recovery catalog is stored in tables inside the catalog database, it is well suited for retaining metadata longer, provided the catalog is resynchronized and storage capacity is properly managed.

The recovery catalog also supports RMAN stored scripts. For example, you can store a shared backup script that DBAs run on an operational schedule. If you do not use a recovery catalog, you can store RMAN commands in OS command files or a configuration management system; do not confuse external script files with stored scripts inside the catalog.

## 5. Creating and Registering a Recovery Catalog

The steps below illustrate an environment prepared by a DBA. Replace service names, users, passwords, tablespaces, and privilege policies according to your actual system.

### 5.1. Preparing the Catalog Database and Schema

The DBA creates a dedicated user on the catalog database, grants the `RECOVERY_CATALOG_OWNER` role per Oracle documentation, and configures a default tablespace and quota. General example:

```sql
CREATE USER rman_catalog
  IDENTIFIED BY "<strong-password>"
  DEFAULT TABLESPACE rman_catalog_ts
  QUOTA UNLIMITED ON rman_catalog_ts;

GRANT RECOVERY_CATALOG_OWNER TO rman_catalog;
```

This is a structural example, not a complete deployment script for every release. The tablespace must already exist; passwords must be managed securely; schema creation and role grants must be performed by an authorized DBA. In production, consider finite quotas and a tablespace expansion procedure rather than granting unlimited space.

### 5.2. Creating the Catalog

Connect RMAN to the catalog database as the owner user:

```text
rman catalog rman_catalog@RCAT
```

After authenticating, create the catalog objects:

```rman
CREATE CATALOG;
```

To specify a tablespace other than the schema's default tablespace, use `CREATE CATALOG TABLESPACE ...` syntax compatible with your RMAN version.

The catalog creation command builds metadata structures inside the schema. It does not back up the target database and does not automatically register all databases in your environment.

### 5.3. Connecting to Target and Catalog

RMAN needs to connect to both the target database and the recovery catalog:

```text
rman target sys@ORCL catalog rman_catalog@RCAT
```

In environments with appropriate OS authentication, you can connect to the target using `target /` and specify the catalog separately. The target account needs `SYSDBA` or appropriate RMAN connection privileges per release and security policy. Never put production passwords directly into command history or shared documentation.

### 5.4. Registering the Target Database

Once connected to both target and catalog, execute:

```rman
REGISTER DATABASE;
```

RMAN registers the current database in the catalog and synchronizes required metadata from the control file. You can verify the registered database using:

```rman
LIST INCARNATION OF DATABASE;
```

Or query catalog views using the schema owner, for example:

```sql
SELECT db_key, dbid, name
FROM rc_database
ORDER BY name;
```

Column and view names may vary across catalog versions; consult the data dictionary for your exact release when building automated reports.

### 5.5. Upgrading the Catalog Schema

When using a newer RMAN client or database version, you may need to upgrade the recovery catalog schema for compatibility. RMAN may prompt you to run `UPGRADE CATALOG` when it detects an older schema.

Before upgrading:

- Check the compatibility matrix among the RMAN client, target database, and catalog database.
- Back up the recovery catalog database.
- Verify which versions the target databases and management tools are running.
- Perform the upgrade during an appropriate maintenance window and verify afterward.

Never assume every RMAN version is compatible with every catalog version simply because a connection succeeds. Follow Oracle's compatibility documentation for the running versions.

## 6. Resynchronization: Syncing the Control File with the Recovery Catalog

When using a recovery catalog, the target's control file remains where Oracle records operational state and serves as a primary information source for RMAN. The recovery catalog must be synchronized to receive new changes. This process is called **resynchronization**.

RMAN performs automatic resync during appropriate operations, such as after backups or when metadata updates are needed. A DBA can also trigger manual synchronization:

```rman
RESYNC CATALOG;
```

Resync copies repository changes from the target control file into the recovery catalog. If the control file reuses older records before the catalog receives them, some history may not be captured completely in the catalog. Therefore, connecting to the catalog regularly and letting RMAN resync during normal operations is important.

### 6.1. Resync Is Not a Backup

`RESYNC CATALOG` only synchronizes metadata. It does not copy datafiles, backup pieces, or archived redo logs to the catalog database. Nor does it replace control file backups or backups of the catalog database itself.

### 6.2. When the Catalog Is Unreachable

If the recovery catalog database is temporarily unavailable, RMAN can still operate using the control file repository when connecting in NOCATALOG mode, provided the required information remains in the control file. Once the catalog returns, reconnect to target and catalog and run a resync to update metadata.

The ability to continue specific operations depends on the command being run, available repository metadata, backup devices, and database state. Do not ignore prolonged catalog outages: control file records have their own lifecycle and can be reused.

## 7. Where Is RMAN Configuration Stored?

Persistent RMAN configuration includes settings such as:

- Retention policy.
- Default device type.
- Channels and parallelism.
- Backup optimization.
- Compression and encryption.
- Control file autobackup.
- Snapshot control file name.
- Tape/SBT configuration if used.

When not using a recovery catalog, RMAN configuration is stored in the target control file. When using a recovery catalog, configuration is stored in the catalog and managed with its repository.

View current configuration:

```rman
SHOW ALL;
```

Example configuring retention policy and control file autobackup:

```rman
CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

The retention policy defines which backups must be kept to meet recovery goals. For example, `RECOVERY WINDOW OF 7 DAYS` requires keeping sufficient backups and redo to recover to points in time within a seven-day window, subject to the backup and archived log chain. It does not simply delete every file older than seven days.

You can also choose a redundancy-based policy, such as retaining a required number of most recent backups. The right policy depends on RPO, RTO, storage capacity, and organizational audit requirements.

## 8. Maintaining Metadata and Distinguishing Backup States

Repository management requires distinguishing between backups that still exist, backups that are missing, and backups no longer needed under the retention policy.

### 8.1. Listing Backups

```rman
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
REPORT SCHEMA;
LIST INCARNATION OF DATABASE;
```

`LIST` commands read repository metadata to display backups known to RMAN. `REPORT SCHEMA` displays the datafile/tablespace structure recorded by RMAN.

### 8.2. Crosscheck: Reconciling Metadata with Storage Devices

Over time, backup pieces may be moved, manually deleted, lost to storage errors, or become unreachable. The repository may still mark those backups as available. `CROSSCHECK` verifies the physical presence of backups on the corresponding device and updates their status in the repository.

```rman
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
```

If RMAN cannot find a recorded file, its backup status can be changed to `EXPIRED`. Crosscheck does not delete backup files; it updates metadata based on check results.

### 8.3. Expired and Obsolete Are Not the Same

| Status / Concept | Meaning | Common Handling |
|---|---|---|
| `EXPIRED` | Repository records the backup, but crosscheck cannot find the corresponding file on the device | Verify whether the file was moved or the device disconnected; then consider `DELETE EXPIRED` to clean up records |
| `OBSOLETE` | Backup is no longer needed to satisfy the current retention policy | Review with `REPORT OBSOLETE`; after confirming, use `DELETE OBSOLETE` per procedure |
| `AVAILABLE` | RMAN currently records the backup as accessible as of the latest check | Still requires scheduled readability checks and actual restore testing |

`EXPIRED` indicates RMAN cannot find the file at its known location; `OBSOLETE` relates to the backup retention policy. A backup can be available yet obsolete; an expired backup may not yet be obsolete under the retention policy. These two states are not interchangeable.

### 8.4. Cleaning Up Expired Records

After verifying that files truly no longer exist on the device and there is no plan to restore them, expired records can be cleaned up:

```rman
DELETE EXPIRED BACKUP;
DELETE EXPIRED ARCHIVELOG ALL;
```

These commands remove repository metadata for objects marked expired. Since RMAN determined the files do not exist at the checked location, the operation primarily cleans up the repository; still, carefully verify scope before running.

### 8.5. Deleting Obsolete Backups

Preview backups no longer needed under the retention policy:

```rman
REPORT OBSOLETE;
```

After reviewing the policy and retention requirements, you can delete them:

```rman
DELETE OBSOLETE;
```

Unlike `DELETE EXPIRED`, `DELETE OBSOLETE` can delete physical backup pieces from the device and update the repository. Do not run this command if the retention policy does not accurately reflect recovery requirements, legal holds, or organizational retention periods.

### 8.6. Registering Existing Backup Files Back into the Repository

If backup pieces still exist on disk while metadata is missing from the repository, RMAN can catalog those files to recognize them again, provided the files are in an RMAN-supported format and scope.

```rman
CATALOG START WITH '/backup/oracle/' NOPROMPT;
```

Or catalog a specific backup piece:

```rman
CATALOG BACKUPPIECE '/backup/oracle/backup_piece_01.bkp';
```

The `CATALOG` command adds file metadata to the repository; it does not create a new backup and does not alter backup piece contents. Before cataloging a directory, verify it holds backups for the correct target database and avoid cataloging unrelated files.

## 9. Views Used to Inspect the Repository

RMAN commands like `LIST`, `REPORT`, and `SHOW` are usually the most convenient interface for inspecting the repository. When monitoring or writing SQL reports, you can query dynamic performance views on the target or recovery catalog views in the catalog schema.

### 9.1. Target Database Views

Commonly used views:

| View | Contents |
|---|---|
| `V$DATABASE` | DBID, database name, incarnation, and database status |
| `V$CONTROLFILE` | List of configured control files |
| `V$CONTROLFILE_RECORD_SECTION` | Records used / total in each section of the control file |
| `V$BACKUP_SET` | Backup set metadata |
| `V$BACKUP_PIECE` | Backup piece metadata and handles |
| `V$BACKUP_DATAFILE` | Datafile information recorded in backups |
| `V$ARCHIVED_LOG` | Archived redo log metadata |
| `V$RMAN_CONFIGURATION` | Persistent RMAN configuration |

Example querying DBID and database name:

```sql
SELECT dbid, name, open_mode, database_role
FROM v$database;
```

View recent backup sets:

```sql
SELECT
    set_stamp,
    set_count,
    backup_type,
    incremental_level,
    pieces,
    start_time,
    completion_time
FROM v$backup_set
ORDER BY completion_time DESC;
```

View backup pieces and status:

```sql
SELECT
    set_stamp,
    set_count,
    piece#,
    handle,
    status,
    start_time,
    completion_time
FROM v$backup_piece
ORDER BY completion_time DESC;
```

Displayed columns and query capabilities depend on release, privileges, and backup type. Do not assume all columns have identical semantics across releases; check the data dictionary for your database version.

### 9.2. Recovery Catalog Views

When connected to the catalog schema, `RC_*` views can be queried for centralized metadata. For example:

```sql
SELECT db_key, dbid, name
FROM rc_database
ORDER BY name;
```

Common catalog views include `RC_DATABASE`, `RC_BACKUP_SET`, `RC_BACKUP_PIECE`, `RC_BACKUP_DATAFILE`, `RC_ARCHIVED_LOG`, and RMAN configuration views. Confirm view and column names against your recovery catalog version.

Never update underlying recovery catalog tables or views directly using DML. Use RMAN commands such as `REGISTER`, `RESYNC`, `CHANGE`, `CATALOG`, `CROSSCHECK`, and `DELETE` so the repository stays consistent per RMAN rules.

## 10. Recovering from a Lost Control File

Losing the control file is a serious incident because the database needs it to mount. If control file autobackup was enabled and backups are stored in an accessible location, RMAN can restore the control file first and then proceed with database restore/recovery.

General workflow in a NOCATALOG environment:

```rman
STARTUP NOMOUNT;
SET DBID 1234567890;
RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
```

`1234567890` is an illustrative DBID and must be replaced with the actual DBID. Without a control file and without a recovery catalog connection, the DBID allows RMAN to identify the correct autobackup. The DBID can be recorded in database configuration records, backup logs, or operational documentation.

After restoring the control file and mounting the database, RMAN can read the repository from the restored control file to locate recorded backups. If recovery requires a backup control file, opening the database typically requires `OPEN RESETLOGS` once recovery completes per Oracle rules for that scenario:

```rman
ALTER DATABASE OPEN RESETLOGS;
```

Do not apply `OPEN RESETLOGS` mechanically to every restore/recovery scenario. The recovery type, use of a backup control file, recovery point, and Oracle messages determine how to open the database. In particular, incomplete recovery or recovery with a backup control file typically creates a new incarnation and requires `OPEN RESETLOGS`.

If a recovery catalog is available, RMAN can use catalog metadata to find backups even when the current control file is lost. However, the database still needs a restored control file to mount and perform recovery steps.

### 10.1. Why Protect Control File Autobackups?

If you only back up datafiles without a usable control file backup, the DBA may have to manually rebuild the control file from trace or documented structural details. This process is complex and error-prone. Control file autobackups preserve the database structure and metadata needed to start a restore.

Periodically verify:

- Whether control file autobackups are actually created after backups.
- Whether autobackups are stored in an independent location accessible when the database is down.
- Whether the autobackup format is documented and the DBID is stored in operational records.
- Whether control file backups are retained in line with retention and disaster recovery requirements.
- Whether control file restore and database recovery drills are actually practiced.

## 11. Protecting the Recovery Catalog

The recovery catalog contains high-value operational metadata. If the catalog database is lost, the target control file may still retain partial metadata, but long-term history or stored scripts could be lost. Therefore, the catalog database must be protected like a critical production database.

Key principles:

1. Host the catalog in a database independent of the target databases it protects.
2. Back up the catalog database regularly and test restoring the catalog itself.
3. Monitor tablespace capacity, metadata growth, and catalog database health.
4. Restrict access to the schema owner; do not share catalog credentials widely.
5. Document service names, DBIDs, RMAN versions, and connection procedures in secure operational runbooks.
6. Verify resynchronization after maintenance windows, version upgrades, or network interruptions.
7. Test target recovery procedures when the catalog database is unavailable.

Never store all backup pieces in the same place as the recovery catalog database and consider that safe redundancy. Backup data, control files, and the catalog must be protected against independent failure domains such as server loss, storage failure, zone outage, or accidental deletion.

## 12. Common Scenarios and Handling Approaches

### 12.1. RMAN Cannot Find a Backup Even Though Files Still Exist

Causes may include metadata being reused out of the control file, an unsynchronized catalog, or backups copied from another device without being cataloged into the current repository.

Handling approach:

1. Verify the backup files are intact and belong to the right target database.
2. Check the DBID, incarnation, and backup location.
3. Check `LIST BACKUP` and which repository RMAN is using.
4. If files are valid but lack metadata, consider `CATALOG BACKUPPIECE` or `CATALOG START WITH`.
5. Test reading and restoring in a test environment when criticality permits.

Never insert records directly into repository tables with SQL to force RMAN to recognize a backup.

### 12.2. Backups Marked EXPIRED

`EXPIRED` usually means crosscheck could not find the file at the location recorded in the repository. Storage may be temporarily unmounted, tape not loaded, paths changed, or files genuinely deleted.

Before cleaning up records, check the storage device and paths. If files were only temporarily inaccessible, restore storage connectivity and crosscheck again. Only use `DELETE EXPIRED` after confirming records should be removed.

### 12.3. Backup History Missing from the Control File

Older records may have been reused per record section mechanics and `CONTROL_FILE_RECORD_KEEP_TIME`. If a catalog was previously resynchronized, check metadata in the catalog. Without a catalog, verify whether backup files still exist and can be re-cataloged.

Increasing `CONTROL_FILE_RECORD_KEEP_TIME` can retain records longer in the control file, but it does not replace a recovery catalog for long-term history nor does it replace control file backups.

### 12.4. Recovery Catalog Unreachable

Check the catalog database listener/service, network connectivity, credentials, schema status, and tablespaces. If backups must run while the catalog is temporarily unavailable, the DBA can evaluate using the control file repository via a NOCATALOG connection, depending on the commands and current state.

Once the catalog is back online, connect properly to target and catalog and run a resync. Note the outage duration to determine whether any metadata may no longer be present in the control file.

### 12.5. Catalog Schema Needs Upgrading

Check the versions of the RMAN client, target database, and catalog schema. Back up the catalog database before running `UPGRADE CATALOG`; after upgrading, verify database registration, resync, and key `LIST`/`REPORT` commands.

## 13. Sample Operational Workflow

An RMAN workflow with a recovery catalog can be structured as follows:

```text
Before backup
    |
    +--> Verify target and catalog connectivity
    +--> Check storage, channels, and free space
    +--> Review RMAN configuration / retention policy
    |
    v
Run database and archived log backup
    |
    +--> RMAN writes backup pieces to storage
    +--> RMAN updates repository in control file
    +--> RMAN resyncs metadata to recovery catalog
    |
    v
Verify results
    |
    +--> LIST BACKUP / REPORT OBSOLETE
    +--> Check backup piece status
    +--> Save logs and operational metrics
    |
    v
Periodic maintenance
    |
    +--> CROSSCHECK BACKUP / ARCHIVELOG
    +--> Handle EXPIRED after verification
    +--> DELETE OBSOLETE per approved policy
    +--> Back up recovery catalog database
    +--> Rehearse restore/recovery
```

Example of a simple RMAN session:

```rman
SHOW ALL;
REPORT SCHEMA;
BACKUP DATABASE PLUS ARCHIVELOG;
LIST BACKUP SUMMARY;
CROSSCHECK BACKUP;
REPORT OBSOLETE;
```

Cleanup commands should be separated into operational steps with proper review and approval, especially in environments with long-term retention requirements. Avoid embedding `DELETE OBSOLETE` into every backup job if the retention policy has not been validated through a restore drill.

## 14. Testing Recoverability

Successful backups and complete metadata do not guarantee the database can definitely be recovered. Periodically execute restore/recovery in a controlled test or rehearsal environment.

A test should verify:

- Required backup pieces and archived redo logs are accessible.
- Backups can be located from the control file repository or recovery catalog.
- Control file can be restored from autobackup when needed.
- Database can be mounted and datafiles restored.
- Sufficient archived redo logs exist to recover to the desired point.
- Clear understanding of when the database must be opened with `RESETLOGS`.
- Post-recovery application and data validation against business criteria.
- Execution duration meets RTO and recovered data point meets RPO.

Document drill results, per-step timings, backups used, gaps identified, and corrective actions. This provides real operational proof of recoverability, far more valuable than merely seeing `AVAILABLE` in the repository.

## 15. Key Takeaways

- The RMAN repository is metadata describing the database, backups, archived logs, incarnations, and RMAN configuration; it does not contain datafile backup contents.
- The control file is the default repository and is always required for database operations. RMAN can operate in NOCATALOG mode.
- A recovery catalog is an optional metadata store in a separate database; it supports long-term history, multi-target management, and stored scripts.
- When using a catalog, RMAN synchronizes metadata from the control file to the catalog via resynchronization. `RESYNC CATALOG` only syncs metadata; it does not back up data.
- Control file autobackup helps recover the control file during incidents; enable it, store it safely, and rehearse restoring it.
- `CONTROL_FILE_RECORD_KEEP_TIME` controls record lifecycle in the control file; it differs from the RMAN retention policy.
- `EXPIRED` means RMAN could not find the file during crosscheck; `OBSOLETE` means the backup is no longer needed under the retention policy.
- `CATALOG` can register valid backup files back into the repository when metadata is missing.
- The recovery catalog database must also be backed up, monitored, and recovery-tested.
- A backup strategy can only be trusted after a successful restore/recovery drill.

Designing a solid RMAN repository means treating both metadata and backup data as one unified system: control files protected, recovery catalog deployed when needed, repository synchronized, backups verified, and restore procedures practiced regularly.
