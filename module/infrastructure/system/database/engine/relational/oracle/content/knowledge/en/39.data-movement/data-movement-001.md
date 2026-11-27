# Distinguishing Physical Backup from Logical Data Export/Import

When protecting or moving an Oracle Database, two groups of tools are commonly used, but they solve different problems:

- **Physical backup** stores copies of the database's physical files, such as datafiles, control files, SPFILE, and archived redo logs. RMAN is the standard tool for creating, managing, validating, restoring, and recovering these copies.
- **Logical export/import** extracts object-level metadata and data into dump files or transfers them directly between two databases. Oracle Data Pump (expdp/impdp) is the primary tool for this task.

Physical backup is suitable for recovering a database or datafile after a failure, recovering to a target SCN/point in time, and building disaster recovery. Logical export/import is suitable for moving schemas/tables, copying a set of objects, upgrading, or selectively moving data between environments. A Data Pump dump does not replace an RMAN backup; an RMAN backup is also not as convenient as Data Pump when you only need to move a single schema to another database.

This lesson uses Oracle Database 19c as a baseline and covers:
- Concepts, scope, and objectives of physical backup and logical export.
- RMAN backup/recovery and Data Pump export/import.
- Consistency, SCN, transaction snapshots, and archived redo.
- Dump files, DIRECTORY objects, parfiles, workers, and job monitoring.
- Full database, schema, table, and metadata export/import.
- Filters, remapping, transforms, network links, and transportable tablespaces.
- Portability, character sets, endianness, versions, and dependencies.
- Security, performance, result verification, and combined strategies.
- Labs, troubleshooting, and a tool selection checklist.

Syntax, options, and limitations depend on the Oracle release, edition, platform, CDB/PDB, Data Pump client/server version, and storage. Always consult the documentation for your exact version and test export/import or restore in an isolated environment before deploying to production.

## 1. Two Perspectives on Oracle Data

### 1.1. Physical backup

Physical backup stores the file structures that Oracle uses to operate the database. With RMAN, backups can be:
- Backup sets containing the necessary database blocks.
- Image copies, which are copies of datafile/control file files managed by RMAN.
- Archived redo log backups to apply changes after the backup point in time.
- Control file and SPFILE backups for startup, structure identification, and recovery.

When restoring a physical backup, Oracle restores the files and then applies redo to bring the files to a consistent state. This is the primary path for media recovery, point-in-time recovery, and disaster recovery.

### 1.2. Logical export/import

Logical export reads metadata and data at the object level. Data Pump can export:
- A database or a set of schemas.
- One or more tables/partitions.
- Metadata only or data only.
- Objects selected using INCLUDE/EXCLUDE.
- Data filtered using QUERY in supported cases.

The output is typically one or more dump files (.dmp) along with a log file. During import, Data Pump creates objects and loads data into the target database. It does not restore control files, online redo logs, or the physical state of the instance.

### 1.3. Quick comparison

| Criterion | Physical backup | Logical export/import |
| --- | --- | --- |
| Primary tool | RMAN | Data Pump expdp/impdp |
| Unit | Datafile, control file, SPFILE, redo | Schema, table, partition, metadata |
| Output | Backup set or image copy | Dump file and log |
| Database recovery after storage loss | Yes, when sufficient backups and redo exist | No |
| Whole-database point-in-time recovery | Yes, via RMAN recovery | No |
| Moving a single schema/object | Possible, but not the most convenient way | Very suitable |
| Selective object filtering | Not by object semantics like Data Pump | Supports INCLUDE/EXCLUDE |
| Platform dependency | May have endian/storage dependencies | Usually more flexible |
| Rebuilding instance structure | Includes control file/SPFILE backup | No |
| Common goals | Disaster recovery, media recovery | Migration, refresh, object cloning, data movement |

### 1.4. Choosing by objective

- Loss of disk containing datafiles: use physical restore/recovery.
- Restoring the database to before a logical error: consider RMAN point-in-time recovery or an appropriate recovery technique; Data Pump only supports extracting/reloading objects within the exported scope.
- Moving a schema to another database: Data Pump is usually appropriate.
- Moving a few tables with a filter: Data Pump.
- Copying a database as-is to DR: RMAN duplicate/restore or a physical standby solution.
- Moving very large tablespaces with minimal downtime: consider transportable tablespaces or full transportable export/import.

## 2. Physical Backup with RMAN

RMAN understands database structure and backup metadata, so it can create online backups in ARCHIVELOG mode, incremental backups, control file/SPFILE backups, and validate restore capability.

### 2.1. Database backup

Connect:

~~~bash
rman target /
~~~

Back up the database:

~~~text
BACKUP DATABASE TAG 'WEEKLY_DB';
~~~

To collect the archived redo needed for an online backup:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG TAG 'WEEKLY_DB_ARCH';
~~~

The database must be in ARCHIVELOG mode for standard online backups. RMAN creates backup pieces and records metadata in the control file repository or recovery catalog.

### 2.2. Control file and SPFILE backup

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
BACKUP CURRENT CONTROLFILE TAG 'CONTROLFILE';
BACKUP SPFILE TAG 'SPFILE';
~~~

If control file autobackup is enabled and the database uses an SPFILE, autobackup usually protects both. You still need to verify actual backups and know where autobackups are stored.

### 2.3. Incremental backup

~~~text
BACKUP INCREMENTAL LEVEL 0 DATABASE TAG 'L0';
BACKUP INCREMENTAL LEVEL 1 DATABASE TAG 'L1_DIFF';
BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE TAG 'L1_CUM';
~~~

Level 0 serves as the baseline for level 1. Differential and cumulative backups trade off between backup size and the number of incrementals needed to apply during recovery.

### 2.4. Restore and recover

Restore copies files from backup to the required location; recover applies redo:

~~~text
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

The exact procedure depends on the current control file, backup control file, target SCN/time, redo availability, and incarnation. Do not OPEN RESETLOGS unless the recovery path requires it.

### 2.5. Strengths of physical backup

- Recovers the database/datafiles after file loss or corruption.
- Applies archived redo to recover beyond the backup point in time.
- Suitable for large databases and disaster recovery requirements.
- Supports automation of backup, retention, validation, and restore.
- Preserves physical state and database structure within the backup scope.

## 3. Logical Export/Import with Data Pump

Data Pump is the mechanism for moving objects and data at the logical layer. expdp runs export jobs; impdp runs import jobs. These clients control jobs running on the database server.

### 3.1. Data Pump architecture

A Data Pump job can include:
- A master process that coordinates the job.
- Worker processes that read/write metadata and data.
- A master table storing job state in the owning schema.
- A DIRECTORY object pointing to a folder on the database server.
- Dump files containing metadata/data.
- A log file recording progress and errors.

Data Pump usually performs dump file I/O on the database server, not in the current directory of the terminal running expdp. This is an important point when configuring DIRECTORY.

### 3.2. Creating a DIRECTORY object

The DBA creates a directory object pointing to a path on the server:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_dir AS '/u03/oracle/dpump';
GRANT READ, WRITE ON DIRECTORY dpump_dir TO app_owner;
~~~

The path must exist on the database host and the OS account running Oracle must have appropriate permissions. GRANT READ/WRITE on a DIRECTORY object is a database privilege; it does not automatically grant filesystem permissions.

Do not grant directory privileges broadly to all users. Dump files can contain sensitive data.

### 3.3. Checking the directory

~~~sql
SELECT directory_name, directory_path
FROM dba_directories
WHERE directory_name = 'DPUMP_DIR';
~~~

If using RAC, ensure the path is accessible from the node where job workers run or use appropriate shared storage. Check service placement and cluster configuration.

### 3.4. Simple export

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_owner_exp.log
~~~

The command above exports schema APP_OWNER into a dump file in the DPUMP_DIR directory object. The password is prompted interactively or retrieved from a secret mechanism; do not embed real passwords in shell history or scripts.

### 3.5. Simple import

~~~bash
impdp app_owner@TARGET schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_owner_imp.log
~~~

Import requires the dump file to be located in the target database's server directory. When transferring files from the source host to the target host, copy the files using a secure file transfer mechanism and verify checksums before importing.

## 4. Consistency and Snapshots of Logical Export

### 4.1. How does Data Pump read data?

Exporting table data requires reading rows from the database. While the export runs, applications may continue performing DML. Without snapshot control, tables are read at different points in time and may reflect business-inconsistent states.

Data Pump supports the FLASHBACK_SCN or FLASHBACK_TIME parameters to read data as of a consistent point when database/undo conditions permit.

### 4.2. FLASHBACK_SCN

Obtain the target SCN:

~~~sql
SELECT current_scn FROM v$database;
~~~

Use that same SCN for the export:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_owner_exp.log flashback_scn=123456789
~~~

Replace the SCN placeholder with the actual value. Undo retention and available undo must be sufficient to serve consistent reads back to that SCN. If the export runs for a long time and undo is overwritten, the job may encounter snapshot too old.

### 4.3. FLASHBACK_TIME

Data Pump also supports FLASHBACK_TIME in appropriate cases:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_owner_exp.log flashback_time="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Shell quoting syntax must be adjusted for Windows/Linux and the execution tool. Use an explicit timestamp/timezone; verify how the value is converted to an SCN and check undo coverage.

### 4.4. Consistency is not the same as a physical backup

FLASHBACK_SCN helps export logical data as of a snapshot. It does not turn a dump file into a physical backup, does not protect control files/SPFILE/redo, and does not provide crash recovery. It only controls the snapshot of exported data within the scope supported by Data Pump.

### 4.5. Exports and active transactions

Data Pump uses Oracle's read consistency mechanism. If you need a unified snapshot across multiple business-related tables, choose a single FLASHBACK_SCN for the entire job and ensure undo is retained long enough. For external tables, data outside the database, or objects that do not support flashback in the same way, design handling separately.

## 5. Exporting Full Database, Schemas, and Tables

### 5.1. Full database export

~~~bash
expdp system@ORCL full=YES directory=DPUMP_DIR dumpfile=full_%U.dmp logfile=full_exp.log parallel=4
~~~

FULL=YES exports metadata and data within the scope of a Data Pump full export. It is not equivalent to an RMAN whole database backup: certain instance configurations, physical files, redo history, password files, listeners, and wallets still must be managed separately.

Full export usually requires appropriate privileges such as DATAPUMP_EXP_FULL_DATABASE. Do not use SYSTEM/SYS for routine application tasks unless necessary; grant privileges matching the operational role.

### 5.2. Schema export

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_%U.dmp logfile=app_exp.log parallel=4
~~~

Multiple schemas can be exported:

~~~bash
expdp system@ORCL schemas=HR,SALES directory=DPUMP_DIR dumpfile=schemas_%U.dmp logfile=schemas_exp.log
~~~

### 5.3. Table export

~~~bash
expdp app_owner@ORCL tables=ORDERS,ORDER_ITEMS directory=DPUMP_DIR dumpfile=orders_%U.dmp logfile=orders_exp.log
~~~

Specific partitions can be exported, or appropriate table/partition syntax can be used. Check the Data Pump parameter reference for your exact version.

### 5.4. Metadata-only and data-only

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER content=METADATA_ONLY directory=DPUMP_DIR dumpfile=app_meta.dmp logfile=app_meta.log
~~~

~~~bash
expdp app_owner@ORCL tables=ORDERS content=DATA_ONLY directory=DPUMP_DIR dumpfile=orders_data.dmp logfile=orders_data.log
~~~

METADATA_ONLY exports object definitions; DATA_ONLY exports data within the selected scope. When importing data-only, the target must have a compatible structure.

### 5.5. INCLUDE and EXCLUDE

Include only certain object types:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER include=TABLE,INDEX directory=DPUMP_DIR dumpfile=app_objects.dmp logfile=app_objects.log
~~~

Exclude an object type:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER exclude=STATISTICS directory=DPUMP_DIR dumpfile=app_no_stats.dmp logfile=app_no_stats.log
~~~

Filters can use object paths and name expressions. Expression/quoting syntax depends on the shell; use a parfile for complex commands to avoid escaping errors.

## 6. Data Pump Parameter File (parfile)

When there are many parameters, using a parfile makes commands easier to read, manage, and reuse.

Example `app_export.par`:

~~~text
DIRECTORY=DPUMP_DIR
SCHEMAS=APP_OWNER
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_export.log
PARALLEL=4
FILESIZE=10G
COMPRESSION=ALL
FLASHBACK_SCN=123456789
METRICS=YES
LOGTIME=ALL
~~~

Run:

~~~bash
expdp app_owner@ORCL parfile=app_export.par
~~~

The parfile resides on the client machine and is read by the client process; the DIRECTORY path points to the server filesystem. Do not confuse these two locations.

Do not store passwords in parfiles. Manage parfiles containing sensitive filters/queries such as table structures or data conditions according to internal policy.

## 7. Dump Files, FILESIZE, and PARALLEL

### 7.1. Dump file template

~~~text
DUMPFILE=app_export_%U.dmp
~~~

%U allows Data Pump to create multiple files during a parallel export. FILESIZE limits the size of each dump file:

~~~text
FILESIZE=20G
~~~

Ensure there is enough free space for the entire dump set, log files, and temporary files.

### 7.2. PARALLEL

~~~text
PARALLEL=4
~~~

PARALLEL specifies the degree of worker parallelism. Increasing PARALLEL can improve throughput, but it also consumes CPU, I/O, memory, processes, and network. If storage or the source database is already busy, adding workers can slow down the production workload.

### 7.3. Dump files are not block-level backups

A dump file contains object metadata and row data exported by Data Pump. It is not a byte-for-byte copy of a datafile and cannot be attached to a control file like a datafile backup.

A dump file can be used to create objects in another database, but it cannot restore instance state, redo threads, or database checkpoints.

### 7.4. Checksums and file transfer

After transferring dump files:
- Compute checksums on the source.
- Copy all %U files completely.
- Recompute checksums on the destination.
- Compare the checksums.
- Keep export/import logs.
- Protect dump files and logs according to the retention policy.

A single missing file in the dump set can cause the import to fail or lose data.

## 8. Schema Import and Remapping

### 8.1. Importing a schema into a schema with the same name

~~~bash
impdp app_owner@TARGET schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner_%U.dmp logfile=app_import.log
~~~

The target schema/user must be created beforehand if required by the workflow. Check quotas, default tablespace, roles, and privileges.

### 8.2. REMAP_SCHEMA

Move a source schema into a different target schema:

~~~bash
impdp system@TARGET schemas=APP_OWNER remap_schema=APP_OWNER:APP_OWNER_TEST directory=DPUMP_DIR dumpfile=app_owner_%U.dmp logfile=app_test_import.log
~~~

Create the target user and grant appropriate quotas/privileges beforehand, or use an approved user creation procedure.

### 8.3. REMAP_TABLESPACE

Move objects from a source tablespace to a target tablespace:

~~~bash
impdp system@TARGET schemas=APP_OWNER remap_tablespace=APP_DATA:APP_DATA_NEW directory=DPUMP_DIR dumpfile=app_owner_%U.dmp logfile=app_remap_ts.log
~~~

Remapping only changes object mappings within the scope supported by Data Pump. Check LOB segments, partitions, indexes, and objects residing in multiple tablespaces.

### 8.4. TABLE_EXISTS_ACTION

When a table already exists, you can specify the behavior:

~~~bash
impdp app_owner@TARGET tables=ORDERS directory=DPUMP_DIR dumpfile=orders.dmp table_exists_action=APPEND logfile=orders_append.log
~~~

Common values:
- SKIP: skip existing tables.
- APPEND: insert rows into existing tables.
- TRUNCATE: delete existing rows and then load data.
- REPLACE: drop and recreate the table using metadata from the dump.

Choose based on data requirements. APPEND can create duplicates if keys are not controlled; TRUNCATE/REPLACE can cause target data loss. Check carefully before importing into production.

## 9. SQLFILE, CONTENT, and Pre-Import Checks

### 9.1. SQLFILE

You can ask Data Pump to generate an SQL file containing the intended DDL without executing the object import:

~~~bash
impdp system@TARGET schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp sqlfile=app_ddl_preview.sql logfile=app_sqlfile.log
~~~

SQLFILE is useful for reviewing DDL, tablespaces, storage clauses, and objects before deployment. The file is written to the server directory object by Data Pump.

### 9.2. CONTENT=METADATA_ONLY

~~~bash
impdp system@TARGET schemas=APP_OWNER content=METADATA_ONLY directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_metadata_import.log
~~~

### 9.3. CONTENT=DATA_ONLY

~~~bash
impdp app_owner@TARGET tables=ORDERS content=DATA_ONLY directory=DPUMP_DIR dumpfile=orders_data.dmp logfile=orders_data_import.log
~~~

The target table must exist and be compatible in columns, data types, partitions, and constraints. Verify sequence/trigger/identity behavior if the application depends on them.

### 9.4. Pre-import checks

- Read the export log and confirm the job completed.
- Review the dump file list and checksums.
- Use SQLFILE to inspect DDL.
- Check target database version/character set.
- Confirm user/schema/tablespace/quota.
- Check whether objects already exist and verify TABLE_EXISTS_ACTION.
- Check free space, TEMP, UNDO, and parallel capacity.
- Test on staging and compare row counts.

## 10. Data Pump Job Monitoring and Restart

### 10.1. Viewing jobs

~~~sql
SELECT
    owner_name,
    job_name,
    operation,
    job_mode,
    state,
    degree,
    attached_sessions
FROM dba_datapump_jobs
ORDER BY owner_name, job_name;
~~~

You can view workers:

~~~sql
SELECT
    owner_name,
    job_name,
    session_type,
    instance_id
FROM dba_datapump_sessions
ORDER BY owner_name, job_name;
~~~

### 10.2. Attaching to a job

If a job is still running or stopped:

~~~bash
impdp app_owner@TARGET attach=SYS_IMPORT_SCHEMA_01
~~~

The job name must be obtained from DBA_DATAPUMP_JOBS or the log. In interactive mode, you can use STATUS to check progress and STOP_JOB/START_JOB per Data Pump documentation.

### 10.3. Restartable jobs

A Data Pump job can be attached and resumed in many cases if the job state and dump set remain valid. Do not drop the master table or delete dump files while the job is incomplete. If a job fails, read the log and identify the failing worker/object before restarting.

### 10.4. Killing a job

Do not arbitrarily kill OS processes. Use Data Pump attach and documented job management commands. If an immediate stop is required, understand the impact on the master table, worker sessions, and cleanup.

## 11. Export/Import with NETWORK_LINK

Data Pump can transfer data directly from a source database to a target database over a database link without requiring intermediate dump files for standard data movement.

### 11.1. Creating a database link

Example link from the target database to the source:

~~~sql
CREATE DATABASE LINK source_link
CONNECT TO export_user IDENTIFIED BY "<SECRET>"
USING 'SOURCE_DB';
~~~

In production, do not hardcode real passwords in scripts or source control. Follow credential policies and least privilege. The database link must resolve the service and network properly.

### 11.2. Importing over a network link

~~~bash
impdp import_user@TARGET schemas=APP_OWNER network_link=SOURCE_LINK logfile=network_import.log
~~~

NETWORK_LINK reads objects/data from the source database over the link. Some options and object types are not supported in the same way as importing from dump files; check the Data Pump reference.

### 11.3. Trade-offs

Advantages:
- No need to stage large dump files.
- Useful for direct schema transfers.
- Can eliminate file copy steps.

Limitations:
- Depends on network throughput/latency.
- Places load on the source database and database link.
- Requires managing credentials and network security.
- Harder to decouple source load from target import.
- Restart/diagnostic capabilities differ from the dump file workflow.

## 12. Transportable Tablespaces and Full Transportable Export/Import

For very large datasets, Data Pump transportable features can reduce time because datafiles are copied physically while metadata is exported/imported logically.

### 12.1. Transportable tablespaces

Concept:
1. Place the tablespace in READ ONLY mode to ensure data stability.
2. Export tablespace metadata using Data Pump.
3. Copy datafiles to the target host/database.
4. Import metadata with TRANSPORT_DATAFILES.
5. Switch the tablespace back to READ WRITE as planned.

Example metadata export:

~~~bash
expdp system@ORCL tablespaces=APP_DATA directory=DPUMP_DIR dumpfile=app_ts_meta.dmp logfile=app_ts_exp.log transportable=ALWAYS
~~~

Import metadata along with the data file:

~~~bash
impdp system@TARGET directory=DPUMP_DIR dumpfile=app_ts_meta.dmp logfile=app_ts_imp.log transport_datafiles='/u02/oradata/TARGET/app_data01.dbf'
~~~

Verify syntax, self-contained requirements, and file copy procedures for your exact release. Run DBMS_TTS.TRANSPORT_SET_CHECK to determine whether the tablespace set is self-contained as required.

### 12.2. Full transportable export/import

Full transportable export/import combines Data Pump metadata with transportable datafiles for eligible tablespaces, while other components are handled through conventional Data Pump. This is a migration technique, not a replacement for physical backup.

### 12.3. Cross-platform transport

When moving datafiles between platforms with different endianness, RMAN CONVERT or another supported conversion mechanism may be needed. Check:
- Source/target platforms.
- Endian format.
- Character set.
- Database version.
- TDE encryption.
- ASM/OMF paths.
- Datafile compatibility.

## 13. Portability and Version Compatibility

### 13.1. Physical backup portability

Physical backups are usually tied to database/platform/file format. Some cross-platform cases require RMAN CONVERT or transportable technology. Do not copy datafiles between platforms with different endianness and open the database as if they were on the same platform.

### 13.2. Logical export portability

Data Pump is generally more flexible when moving schemas/objects across database versions and platforms. However, you still must check:
- Source/target versions and Data Pump compatibility.
- Character set and national character set.
- Data types and timezone file version.
- Whether object features/options exist on the target.
- SQL syntax/PLSQL package dependencies.
- Collation, identity, sequence, and partition behavior.

### 13.3. VERSION parameter

Data Pump supports VERSION to control metadata format/compatibility in certain export directions. For example:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_compat.dmp logfile=app_compat.log version=19.0
~~~

Valid values and downgrade capabilities depend on the release. VERSION does not turn a new feature into one supported on the target; objects using unsupported features can still fail during import.

### 13.4. Character set

Logical export/import converts data via Oracle's character set conversion capabilities. Check NLS_CHARACTERSET and NLS_NCHAR_CHARACTERSET in both databases, data with characters outside the BMP, CLOB/NCLOB, and column lengths. Conversion can cause character loss if the target cannot represent all source data.

## 14. Securing Dump Files and Backups

### 14.1. Dump files contain sensitive data

Dump files can contain business data, PII, and credentials inside metadata or DDL. Protect them like production data:
- Server directories with restricted OS permissions.
- DIRECTORY objects granted only to required users.
- Encrypt dumps if required by policy.
- Transfer files over secure channels.
- Store checksums and audit access.
- Delete temporary copies per retention policy.
- Never commit dumps to Git or send them via email/chat.

### 14.2. Data Pump encryption

Data Pump supports ENCRYPTION and ENCRYPTION_PASSWORD depending on version/licensing/configuration. Conceptual example in a parfile:

~~~text
ENCRYPTION=ALL
ENCRYPTION_PASSWORD=<SECRET_FROM_SECRET_STORE>
~~~

Actual syntax depends on release and mode. Avoid exposing passwords in process listings, shell history, or logs. Protect the password separately from the dump file; losing the password can make the dump unimportable.

### 14.3. RMAN backup encryption

RMAN can encrypt backup sets using transparent encryption based on a keystore or password-based encryption. You must back up and verify recovery of the keystore/password alongside the physical backup.

### 14.4. Access privileges

- Do not grant DATAPUMP_EXP_FULL_DATABASE/DATAPUMP_IMP_FULL_DATABASE broadly.
- Do not use SYSDBA for routine Data Pump operations unless needed.
- Grant READ/WRITE on DIRECTORY with narrow scope.
- Use dedicated migration accounts with expiration and auditing.
- Confirm the dump does not contain out-of-scope schemas/objects.

## 15. Performance and Capacity

### 15.1. RMAN

RMAN performance depends on:
- Number of channels and parallelism.
- Storage throughput and latency.
- Compression/encryption CPU overhead.
- Block Change Tracking for incrementals.
- Backup piece size and media manager.
- Archived log generation rate.
- Concurrent workload on the database.

### 15.2. Data Pump

Data Pump performance depends on:
- PARALLEL and worker count.
- Storage where dump files reside.
- Source/target I/O.
- Network if using NETWORK_LINK.
- Metadata dependencies and object count.
- Index creation, LOBs, partitions, and constraints.
- Undo/consistent read.
- TEMP, PGA, and CPU.

### 15.3. Do not increase PARALLEL arbitrarily

Adding workers can cause:
- I/O contention on source or target.
- CPU saturation.
- Process/session exhaustion.
- Many concurrent dump files and filesystem pressure.
- Increased network load.

Measure duration, throughput, CPU, I/O, and waits before and after. Choose a parallelism level suited to the migration window.

## 16. Verifying Completeness After Export/Import

### 16.1. Export log

Read the log to confirm:
- Job completed with success status.
- Objects were processed.
- Objects skipped or errored.
- All expected dump files were created.
- Warnings about privileges, unsupported objects, or metadata.

### 16.2. Import log

Check:
- Objects created successfully.
- Row data loaded.
- Constraints/indexes/triggers created.
- Invalid objects.
- Grants, synonyms, database links, and directory dependencies.
- Tablespace/quota/privilege errors.
- Version/character set errors.

### 16.3. Data reconciliation

You can compare row counts:

~~~sql
SELECT COUNT(*) FROM app_owner.orders;
~~~

For large datasets, row counts alone are insufficient. Compare by partition/date range, business aggregate checksums, key ranges, or reconciliation queries. Do not run COUNT(*) on very large tables during peak hours without assessing impact.

### 16.4. Object validity

~~~sql
SELECT owner, object_type, object_name, status
FROM dba_objects
WHERE owner = 'APP_OWNER'
  AND status <> 'VALID'
ORDER BY object_type, object_name;
~~~

Check invalid objects, compile according to dependencies, verify grants, and run application smoke tests.

### 16.5. Physical backup validation

RMAN:

~~~text
LIST BACKUP SUMMARY;
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Validation reads the required backup pieces, but it does not replace an independent restore drill and application verification.

## 17. When to Choose Which Tool?

| Requirement | Appropriate choice | Reason |
| --- | --- | --- |
| Loss of datafile or disk | RMAN restore/recover | Needs physical files and redo |
| Full database recovery after disaster | RMAN or physical standby | Preserves database state and recovers |
| Point-in-time recovery to SCN/time | RMAN point-in-time recovery | Applies redo up to target |
| Moving a schema to a new environment | Data Pump | Selects schema/objects |
| Moving a few tables with filters | Data Pump | Table selection and QUERY |
| Test data refresh | Data Pump or other clone/refresh solutions | Scope selection and consistency |
| Moving very large tablespaces | Transportable tablespaces | Datafile copy + metadata |
| Cloning an entire database | RMAN DUPLICATE/restore | Preserves database-level structure |
| Creating a dump for logical archival | Data Pump | Can import objects later |
| Protecting database for DR | RMAN + archive/standby strategy | Includes redo and recovery metadata |

Do not choose Data Pump just because dump files are easy to copy. If the goal is recovering from storage loss, dump files do not contain the full physical structure required. Likewise, do not choose RMAN just to move a filtered table when Data Pump solves it directly and flexibly.

## 18. Combining Physical and Logical Strategies

A production system typically needs both:

### 18.1. Physical backup as the recovery foundation

- Scheduled RMAN full or incremental backups.
- Sufficiently frequent archived redo log backups.
- Control file autobackup and SPFILE.
- Backup encryption/keystore protection.
- Offsite/immutable copies if required by policy.
- Restore validation and DR drills.

### 18.2. Logical export for migration and object recovery

- Export schemas/tables before major changes.
- Use FLASHBACK_SCN when a consistent snapshot is needed.
- Keep dump files and logs under short retention with access control.
- Import into staging before production.
- Reconcile data, grants, sequences, constraints, and object validity.

### 18.3. Example combined schedule

| Timing | Physical | Logical |
| --- | --- | --- |
| Daily | RMAN incremental + archived logs | Not necessarily running full schema export |
| Weekly | RMAN level 0/full and controlfile/SPFILE | Export critical schemas if needed |
| Before release | RMAN backup/tag per change plan | Export modified schemas/objects |
| Before migration | Full RMAN backup | Data Pump export or transportable |
| After migration | Back up target database | Import logs, reconciliation, and smoke test |
| Monthly | Physical restore drill | Test importing dump files into staging |

Actual schedules must align with RPO/RTO, data volume, migration cadence, and retention policies.

## 19. Common Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| ORA-39002 | Invalid Data Pump parameter/job | Read the log and verify parameter syntax |
| ORA-39070 | Unable to open log file | Check DIRECTORY object and OS permissions |
| ORA-39087 | Invalid DIRECTORY object | Verify directory name and privileges |
| ORA-31640 | Unable to open dump file | Check server path, file name, permissions |
| ORA-39151 | Table exists and was skipped | Choose an appropriate TABLE_EXISTS_ACTION |
| ORA-39126 | Data Pump worker encountered an error | Check prior worker errors and trace |
| ORA-01555 | Snapshot too old during consistent export | Evaluate UNDO, job duration, and FLASHBACK_SCN |
| ORA-39083 | Object creation failed | Read specific DDL/error, privileges/tablespace/version |
| Import missing objects | INCLUDE/EXCLUDE or limited export mode | Check parfile and export log |
| Import character errors | Character set conversion or data type | Compare NLS settings and data |
| RMAN cannot find backup | Different repository/control file or expired backup | LIST, CROSSCHECK, CATALOG, and DBID |
| RMAN restore missing redo | Archived log sequence missing | Locate log backup/other media or adjust target |
| RMAN backup slow | Channel/storage/CPU bottleneck | Measure throughput, I/O, compression, and parallelism |
| Data Pump job hangs long | Worker waiting on I/O, lock, network, or large object | Attach job, STATUS, inspect waits/sessions |
| Dump file transferred to target fails | Missing piece or copy corruption | Compare checksums and verify all %U files |

## 20. Lab: Physical Backup with RMAN

Perform this in a lab database with RMAN privileges and dedicated storage.

### 20.1. Check the database

~~~sql
SELECT name, open_mode, log_mode, current_scn
FROM v$database;
~~~

In RMAN:

~~~text
SHOW ALL;
REPORT SCHEMA;
~~~

### 20.2. Create a backup

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
BACKUP DATABASE PLUS ARCHIVELOG TAG 'LAB_PHYSICAL';
BACKUP SPFILE TAG 'LAB_SPFILE';
LIST BACKUP SUMMARY;
~~~

### 20.3. Validate

~~~text
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Record the backup key, piece, checkpoint SCN, and archived log coverage. Do not restore over an active shared lab database.

## 21. Lab: Logical Export/Import with Data Pump

### 21.1. Prepare the directory

DBA:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_lab AS '/u03/oracle/dpump_lab';
GRANT READ, WRITE ON DIRECTORY dpump_lab TO app_owner;
~~~

Ensure the folder exists on the server and the Oracle OS account has permissions.

### 21.2. Export schema

Create parfile `app_export.par`:

~~~text
DIRECTORY=DPUMP_LAB
SCHEMAS=APP_OWNER
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_exp.log
PARALLEL=2
METRICS=YES
LOGTIME=ALL
~~~

Run:

~~~bash
expdp app_owner@ORCL parfile=app_export.par
~~~

If a consistent snapshot is needed, add FLASHBACK_SCN with the recorded SCN and ensure appropriate undo retention.

### 21.3. Inspect dump metadata before import

~~~bash
impdp app_owner@TARGET directory=DPUMP_LAB dumpfile=app_owner_%U.dmp sqlfile=app_ddl.sql logfile=app_ddl.log
~~~

Read the DDL to identify tablespaces, quotas, grants, and dependencies.

### 21.4. Import into a new schema

~~~bash
impdp system@TARGET schemas=APP_OWNER remap_schema=APP_OWNER:APP_OWNER_TEST directory=DPUMP_LAB dumpfile=app_owner_%U.dmp logfile=app_test_imp.log
~~~

Create the target user and necessary tablespaces/quotas before importing per policy.

### 21.5. Verify

- Read the export/import logs.
- Check object counts and invalid objects.
- Compare row counts or run reconciliation queries.
- Check sequences, triggers, grants, and synonyms.
- Run application smoke tests in staging.

## 22. Practice Exercises

### Exercise 1 — Classify objectives

Given 8 scenarios: lost datafile, schema migration, database clone, filtering a subset of rows, PITR, moving a large tablespace, test refresh, and pre-release backup. Choose RMAN/Data Pump/transportable and explain.

### Exercise 2 — RMAN full backup

Create a backup of the database and archived logs. Record backup pieces, tag, checkpoint SCN, and timing.

### Exercise 3 — RMAN incremental

Create a level 0 backup, modify data, and run level 1 differential/cumulative. Compare sizes and restore chains.

### Exercise 4 — Data Pump schema export

Export a schema with PARALLEL and %U. Read the log, checksum the dump files, and record object counts.

### Exercise 5 — Snapshot consistency

Capture FLASHBACK_SCN, export the schema at that SCN, modify data in another session, and compare the dump when imported into a lab.

### Exercise 6 — Object filtering

Export selected tables using TABLES and use INCLUDE/EXCLUDE. Inspect SQLFILE before importing.

### Exercise 7 — Remap schema/tablespace

Import a schema to a new user and tablespace. Verify object ownership, quotas, and invalid objects.

### Exercise 8 — Network link

Create a lab database link, run an import over NETWORK_LINK, and measure network/source load compared to the dump file workflow.

### Exercise 9 — Transportable tablespace

Check for a self-contained set, export metadata, copy datafiles, and import the tablespace in an isolated environment. If cross-platform, determine whether endian conversion is required.

### Exercise 10 — Recovery/migration runbook

Write two independent runbooks: one for datafile loss using RMAN, and one for moving a schema using Data Pump. Document prerequisites, credentials, files, consistency points, validation, and rollback.

## 23. Pre-Execution Checklist

### Tool selection
- Is the goal disaster recovery or object migration?
- Do you need to recover the database to an SCN/time?
- Do you need the entire database, tablespaces, schemas, or a few tables?
- Is there a platform/version change requirement?

### Physical backup
- Database in ARCHIVELOG if online backup is needed.
- Backup datafiles, control file, SPFILE, and archived redo.
- Know the backup destination, DBID, and recovery catalog.
- Protect wallet/keystore if backups are encrypted.
- Validate backups and rehearse restores.

### Logical export/import
- DIRECTORY object points to the correct server path.
- OS permissions and database READ/WRITE grants are correct.
- Dump set has all pieces and matching checksums.
- FLASHBACK_SCN/TIME used when a consistent snapshot is needed.
- Target version/character set/tablespace/quota are appropriate.
- INCLUDE/EXCLUDE, REMAP, and TABLE_EXISTS_ACTION have been reviewed.
- Export/import logs and data reconciliation succeed.

### Post-operation
- Check database/object status.
- Verify row counts and business logic.
- Confirm grants, synonyms, sequences, triggers, and jobs.
- Protect/delete dump files according to retention.
- Update runbooks and backup schedules.

## 24. Cleaning Up the Lab Environment

- Stop Data Pump jobs using supported methods and only when needed.
- Delete only the lab dump/log files after confirming they are no longer needed.
- Revoke DIRECTORY privileges granted to lab users if no longer used.
- Drop lab database links/credentials according to policy.
- Drop lab schemas/tables in a controlled manner.
- Keep RMAN backups needed for restore exercises; delete via RMAN according to retention rather than deleting directly at the OS level while still referenced in the repository.
- Do not delete archived redo logs needed for shared databases.

## Summary

Physical backup and logical export/import solve two different goals. RMAN stores the physical files and redo needed to restore/recover a database, datafiles, and database state to an SCN/time. Data Pump exports object-level metadata and row data to move schemas/tables, filter data, refresh environments, or perform migrations. FLASHBACK_SCN/TIME helps Data Pump read a consistent logical snapshot, but it does not turn a dump file into a physical backup.

Choose RMAN when you need disaster recovery, media recovery, or point-in-time recovery. Choose Data Pump when you need selective object/data movement or schema transfers between databases. Transportable tablespaces combine metadata export with datafile copying for certain large workloads. In production, RMAN is typically used as the data protection foundation and Data Pump for migration/refresh; verify dumps, backups, consistency, versions, character sets, keys, and end-to-end restore/import before declaring success.

## Oracle References

- [Oracle Database Backup and Recovery User's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN backup, restore, recovery, and physical backup strategies.
- [Oracle Database Backup and Recovery Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/) — RMAN BACKUP, RESTORE, RECOVER syntax, and validation.
- [Oracle Database Utilities — Data Pump Export (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html) — expdp parameters, export modes, and dump files.
- [Oracle Database Utilities — Data Pump Import (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html) — impdp, remap, filters, and import modes.
- [Oracle Database Utilities (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/) — Data Pump, transportable tablespaces, and database utilities.
- [Oracle Database Reference — DBA_DATAPUMP_JOBS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DATAPUMP_JOBS.html) — monitoring Data Pump jobs.
- [Oracle Database Reference — DBA_DIRECTORIES (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DIRECTORIES.html) — directory objects and server paths.

When deploying on an Oracle release other than 19c, consult the Backup and Recovery User's Guide, Data Pump Export/Import Reference, and Database Utilities for that exact version, especially regarding FLASHBACK_SCN/TIME, VERSION, encryption, transportable tablespaces, PDB scope, and cross-platform limitations.
