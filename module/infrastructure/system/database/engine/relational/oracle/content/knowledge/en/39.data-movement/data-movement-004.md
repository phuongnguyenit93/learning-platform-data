# Exporting and Importing by Database, Schema, Table, or Tablespace

Oracle Database provides several ways to move data between environments, schemas, or databases. For logical data export and import needs, the standard tool is **Oracle Data Pump**, consisting of two command-line utilities: **expdp** (export) and **impdp** (import). Data Pump lets you select scope by full database, schema, table, or tablespace, filter objects, remap schemas/tablespaces, and monitor progress.

Another option is **transportable tablespaces**, where the DBA moves metadata using Data Pump and transfers the tablespace datafiles to the target database. This differs from conventional logical export/import and carries strict requirements regarding tablespace self-containment, platform, endian format, and version.

The key is choosing the right method:

- Logical export/import is appropriate when moving objects and data, with optional filtering or remapping.
- Transportable tablespaces are appropriate when moving large data volumes by transferring datafiles, reducing the time needed to unload/load millions of rows.
- RMAN backup/restore is appropriate for database/datafile-level backup and recovery; it is not the same as Data Pump export/import.

## 1. What Is Data Pump?

Data Pump is the mechanism Oracle uses to unload metadata and data from a database into dump files, and then load them into another database or the current database. Data Pump runs as database server processes; the expdp/impdp client submits requests and monitors the job.

Export flow:

~~~text
Source database
      |
      | expdp creates job
      v
Data Pump server process
      |
      | reads metadata and data
      v
Oracle DIRECTORY object
      |
      v
Dump file (.dmp) + log file
~~~

Import flow:

~~~text
Dump file (.dmp)
      |
      v
Oracle DIRECTORY object
      |
      | impdp creates job
      v
Data Pump server process
      |
      | creates objects and loads data
      v
Target database
~~~

A dump file is not an Oracle datafile. It is a logical export format containing metadata and/or data matching the selected scope, filters, and options. You cannot mount a DMP file as a datafile or use it directly in place of an RMAN backup.

Data Pump can write one or multiple dump files and supports parallel workers, compression, encryption, metadata filters, data filters, remapping, and many other features depending on version.

## 2. Data Pump vs. Legacy exp/imp Utilities

Oracle previously provided the traditional export/import utilities exp and imp. They use an older export format and have different limitations compared to Data Pump.

| Criterion | Data Pump: expdp/impdp | Legacy export/import: exp/imp |
|---|---|---|
| Mechanism | Server-side jobs and worker processes | Traditional export/import utilities |
| Dump format | Data Pump dump file | Conventional export dump |
| Parallelism | Supports PARALLEL | More limited capability |
| Schema/tablespace remapping | Many supported options | Different and more limited capabilities |
| Metadata/data filtering | Supports INCLUDE, EXCLUDE, QUERY, and many filters | More limited |
| Job monitoring | Has Data Pump job views and ATTACH | Not the same mechanism |
| Transportable workflow | Integrates well with transportable tablespaces | Not the primary tool for modern workflows |

Do not use expdp to read dumps created by legacy exp or vice versa. If you receive an export file from a legacy system, determine which tool and version created the file before choosing the import utility.

## 3. DIRECTORY Objects and File Locations

Data Pump reads/writes dump files on the database server machine via an Oracle DIRECTORY object. The directory where expdp is invoked on the client machine is not automatically where the dump file is created.

The DBA creates the directory on the OS, then creates the DIRECTORY object:

~~~sql
CREATE OR REPLACE DIRECTORY dp_dir AS '/u02/oradata/dpump';
~~~

On Windows, the path might be:

~~~sql
CREATE OR REPLACE DIRECTORY dp_dir AS 'D:\oracle\dpump';
~~~

The path must exist on the database server or storage accessible by server processes. The Oracle software owner needs read/write permissions at the operating system level.

Then grant privileges on the DIRECTORY object:

~~~sql
GRANT READ, WRITE ON DIRECTORY dp_dir TO app_user;
~~~

READ/WRITE on a DIRECTORY is an Oracle object privilege; it does not automatically grant filesystem read/write permissions to the Oracle software owner. Both privilege layers must be correct.

### Checking the DIRECTORY object

~~~sql
SELECT directory_name,
       directory_path
  FROM dba_directories
 WHERE directory_name = 'DP_DIR';
~~~

View privileges:

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege
  FROM dba_tab_privs
 WHERE table_name = 'DP_DIR'
 ORDER BY grantee, privilege;
~~~

DIRECTORY names are typically stored in uppercase unless created with an identifier enclosed in double quotes.

### Where are the files?

Example parameters:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=orders_%U.dmp
LOGFILE=orders_export.log
~~~

Files are written to the path pointed to by DIRECTORY DP_DIR on the database server. When moving files to a target database, copy them to a readable server-side directory and create a corresponding DIRECTORY object on the target database.

## 4. Main Export/Import Modes

Data Pump supports common export scopes:

| Mode | Parameter | Scope |
|---|---|---|
| Full database | FULL=YES | Exports all objects within the database/container scope to which the job connects and has access |
| Schema | SCHEMAS | Exports one or more schemas |
| Table | TABLES | Exports one or more tables and related objects per selected metadata |
| Tablespace | TABLESPACES | Exports tables located in one or more tablespaces within Data Pump's scope |
| Transportable tablespaces | TRANSPORT_TABLESPACES | Exports metadata to move tablespaces along with datafiles via the transportable method |

These modes are not strictly interchangeable. Specifically, TABLESPACES=... is a type of logical export scoped by tablespace; TRANSPORT_TABLESPACES=... is a datafile-movement workflow with its own requirements.

## 5. Full Database Export: FULL=YES

Full export is suitable when you need metadata and data across the entire database supported by Data Pump. Example:

~~~text
expdp system@ORCL FULL=YES DIRECTORY=DP_DIR DUMPFILE=full_%U.dmp LOGFILE=full_export.log PARALLEL=4
~~~

The command will prompt for a password if the connect string does not include one. Do not place real passwords on the command line, in committed scripts, or in CI/CD logs.

You can use a parameter file to make commands readable and avoid exposing details in shell history:

~~~text
FULL=YES
DIRECTORY=DP_DIR
DUMPFILE=full_%U.dmp
LOGFILE=full_export.log
PARALLEL=4
FILESIZE=20G
LOGTIME=ALL
METRICS=YES
~~~

Run:

~~~text
expdp system@ORCL PARFILE=full_export.par
~~~

FULL=YES requires appropriate Data Pump full export privileges, typically the DATAPUMP_EXP_FULL_DATABASE role. Do not use SYSDBA for routine exports unless there is a specific requirement and guidance.

### Full export is not a physical backup

FULL=YES exports object metadata and logical data within Data Pump's capabilities. It does not create a byte-for-byte copy of all datafiles, control files, and online redo. Therefore, a full export does not replace an RMAN backup.

Certain special components or states have their own rules, and you should not assume everything at the instance level is exported. For example, Data Pump does not replace backing up listener configuration, password files, wallets, OS scripts, external files, or configurations outside the database.

### Full database import

~~~text
impdp system@TARGET FULL=YES DIRECTORY=DP_DIR DUMPFILE=full_%U.dmp LOGFILE=full_import.log
~~~

Full import can create or load many types of objects and users. Plan tablespaces, users, privileges, database links, directories, jobs, and dependent objects before running. Running a full import into a database that already contains data can cause conflicts or unexpected object changes.

Do not treat FULL=YES as a safe production sync method without confirming whether the target database is empty or serving an active workload.

## 6. Schema Export/Import: SCHEMAS

Schema mode is a common way to move an application or a group of objects owned by a user.

Export a single schema:

~~~text
expdp app_owner@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_owner_%U.dmp LOGFILE=app_owner_export.log PARALLEL=2
~~~

Multiple schemas can be exported:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER,APP_REPORT DIRECTORY=DP_DIR DUMPFILE=apps_%U.dmp LOGFILE=apps_export.log
~~~

Exporting a user's own schema can usually be performed with the owner's appropriate privileges. Exporting another schema requires appropriate Data Pump privileges, such as DATAPUMP_EXP_FULL_DATABASE depending on the operation scope.

### What does schema mode include?

Data Pump can export schema objects such as:

- Tables and table data.
- Indexes.
- Constraints.
- Views and materialized views.
- Sequences.
- Procedures, functions, and packages.
- Triggers.
- Synonyms.
- Grants and certain related metadata.
- Other objects supported in the release.

Do not assume every dependency outside the schema is exported automatically. For example, objects referencing other users/schemas, database links, external files, or directories must be checked separately.

### Importing a schema

~~~text
impdp system@TARGET SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_owner_%U.dmp LOGFILE=app_owner_import.log
~~~

If the target schema does not exist yet, a full export or schema import does not always create the user the way operators expect if appropriate metadata/privileges are missing. Prepare the user, default tablespace, quotas, profile, and authentication in the target database beforehand.

### Remapping a schema

If you want to import APP_OWNER as APP_OWNER_TEST:

~~~text
impdp system@TARGET DIRECTORY=DP_DIR DUMPFILE=app_owner_%U.dmp LOGFILE=app_test_import.log REMAP_SCHEMA=APP_OWNER:APP_OWNER_TEST
~~~

REMAP_SCHEMA changes the schema owner of imported objects within the supported scope. It does not automatically fix hardcoded strings in source code, dynamic SQL, external configuration, or data containing schema names. After remapping, verify synonyms, grants, database links, jobs, and the application.

## 7. Table Export/Import: TABLES

Table mode is suitable when you only need one or a few specific tables:

~~~text
expdp app_owner@ORCL TABLES=ORDERS,ORDER_ITEMS DIRECTORY=DP_DIR DUMPFILE=orders_tables.dmp LOGFILE=orders_tables_export.log
~~~

You can specify tables belonging to another schema using `owner.table` syntax when the account has privileges:

~~~text
expdp system@ORCL TABLES=APP_OWNER.ORDERS,APP_OWNER.ORDER_ITEMS DIRECTORY=DP_DIR DUMPFILE=orders.dmp LOGFILE=orders_export.log
~~~

Table mode can include table metadata, data, and certain dependent objects as handled by Data Pump. However, do not assume every object the application needs is exported alongside a table. Identify related objects:

- Indexes and constraints.
- Triggers.
- Grants on the table.
- Sequences used to generate keys.
- Views or packages referencing the table.
- Types, synonyms, and dependent objects.
- Partitions/subpartitions if the table is partitioned.

### Importing a table

~~~text
impdp app_owner@TARGET TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders_tables.dmp LOGFILE=orders_import.log
~~~

If the table already exists, decide how to handle it using TABLE_EXISTS_ACTION:

| Value | General behavior |
|---|---|
| SKIP | Skips the existing table |
| APPEND | Appends data into the existing table |
| TRUNCATE | Deletes existing data via TRUNCATE and reloads |
| REPLACE | Drops the existing table and recreates it from the dump before loading |

Example:

~~~text
impdp app_owner@TARGET TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders_tables.dmp TABLE_EXISTS_ACTION=APPEND LOGFILE=orders_append.log
~~~

APPEND can create duplicate records or unique constraint violations if data already exists. TRUNCATE and REPLACE can destroy existing data or objects. Choose them only after confirming target data, backups, and a rollback plan.

## 8. Tablespace Export/Import: TABLESPACES

TABLESPACES mode is a logical export scoped to the specified tablespaces. Example:

~~~text
expdp system@ORCL TABLESPACES=USERS,APP_DATA DIRECTORY=DP_DIR DUMPFILE=ts_export_%U.dmp LOGFILE=ts_export.log
~~~

This mode selects tables located in the listed tablespaces and exports metadata/data via Data Pump. It does not move physical datafiles intact like transportable tablespaces.

Import:

~~~text
impdp system@TARGET TABLESPACES=USERS,APP_DATA DIRECTORY=DP_DIR DUMPFILE=ts_export_%U.dmp LOGFILE=ts_import.log
~~~

TABLESPACES mode may require corresponding Data Pump full database privileges when accessing objects outside the current schema. Check privileges and the actual object scope.

### TABLESPACES vs. TRANSPORT_TABLESPACES

This is a critical distinction:

- TABLESPACES=APP_DATA selects objects/data inside the tablespace for logical export.
- TRANSPORT_TABLESPACES=APP_DATA exports metadata for moving the tablespace while the datafiles are copied separately.

If the goal is moving very large data volumes and avoiding row-by-row unload/load, evaluate transportable tablespaces. Do not simply change TABLESPACES to TRANSPORT_TABLESPACES while skipping the datafile procedure.

## 9. Filtering Objects with INCLUDE and EXCLUDE

Data Pump supports INCLUDE and EXCLUDE to select or omit object metadata by object type and name.

Example exporting only tables and indexes of a schema:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_selected.dmp LOGFILE=app_selected.log INCLUDE=TABLE,INDEX
~~~

Example excluding statistics:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_no_stats.dmp LOGFILE=app_no_stats.log EXCLUDE=STATISTICS
~~~

You can use object paths and name conditions:

~~~text
INCLUDE=TABLE:"LIKE 'ORD_%'"
~~~

When passing expressions with quotes, special characters, or shell quoting, syntax must be written properly for the shell in use. Parameter files are usually easier to control than long command lines.

Do not use INCLUDE/EXCLUDE arbitrarily: omitting constraints, sequences, triggers, or packages can leave imported data unable to function properly.

### INCLUDE and EXCLUDE are not used together

Usually choose one of the two filtering approaches for a job. Consult the Data Pump documentation for your exact release regarding object paths and filter rules, especially when combining multiple filters.

## 10. Filtering Data with QUERY

QUERY lets you filter exported rows using an SQL condition for a table. Example exporting only orders since the start of the year:

~~~text
expdp app_owner@ORCL TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders_2026.dmp LOGFILE=orders_2026.log QUERY=ORDERS:"WHERE ORDER_DATE >= DATE '2026-01-01'"
~~~

The condition must be valid for the table and data types. When using multiple tables, configure query filters for the exact objects and aliases. Test quoting syntax in your actual shell.

QUERY filters the data in the dump, so import will only contain the selected rows. Do not use it if you need a complete copy for backup or recovery.

### Consistency during export

Data Pump export normally reads data using read consistency. For workloads undergoing continuous updates, you can specify FLASHBACK_SCN or FLASHBACK_TIME to export data as of a consistent point if undo/flashback conditions and privileges allow.

Example:

~~~text
expdp app_owner@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_consistent.dmp LOGFILE=app_consistent.log FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 01:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Or using a recorded SCN:

~~~text
FLASHBACK_SCN=123456789
~~~

FLASHBACK_TIME/SCN does not guarantee that objects outside the export scope share the same state. If undo is insufficient to reconstruct the snapshot, the export can fail with snapshot too old or related errors. For applications with transactions spanning multiple schemas, plan overall data consistency and pause/freeze writes if required by business rules.

## 11. Remapping Tablespaces and Datafiles

When importing into a target database, source tablespaces may not exist or you may want a different storage layout. You can use REMAP_TABLESPACE:

~~~text
impdp system@TARGET SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_owner.dmp LOGFILE=app_remap_ts.log REMAP_TABLESPACE=APP_DATA:APP_DATA_NEW
~~~

If multiple mappings are needed, specify multiple REMAP_TABLESPACE parameters. Verify imported objects and confirm target tablespaces already exist or can be created.

### REMAP_DATAFILE

In some workflows, REMAP_DATAFILE is used to change datafile names/paths referenced in import metadata. It does not replace storage planning and does not move datafile contents like transportable tablespaces.

Example parameter that may be needed when importing metadata containing source file path references:

~~~text
REMAP_DATAFILE='/u01/oradata/src/users01.dbf':'/u02/oradata/dst/users01.dbf'
~~~

Syntax depends on shell and version. Use this only when metadata contains datafile paths requiring remapping; for normal logical schema imports, REMAP_TABLESPACE is typically what to consider first.

## 12. TRANSFORM and Metadata Import

Data Pump provides the TRANSFORM parameter to modify certain metadata attributes during import. Example:

~~~text
impdp system@TARGET SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_owner.dmp LOGFILE=app_transform.log TRANSFORM=SEGMENT_ATTRIBUTES:N
~~~

SEGMENT_ATTRIBUTES:N can omit certain segment attributes such as storage clauses and tablespaces in metadata within supported scope. Understand exactly which objects the transform applies to in your version.

Commonly encountered transforms include:

- SEGMENT_ATTRIBUTES.
- STORAGE.
- OID.
- PCTSPACE.
- TABLESPACE or other transforms depending on version.

Do not apply TRANSFORM=SEGMENT_ATTRIBUTES:N if you need to preserve physical storage attributes or want objects placed in the exact source tablespaces. Verify metadata and storage results after import.

## 13. PARALLEL, Dump File Templates, and FILESIZE

For large datasets, Data Pump can use multiple workers to increase throughput:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_%U.dmp LOGFILE=app_parallel.log PARALLEL=4 FILESIZE=10G
~~~

%U is a placeholder allowing Data Pump to generate multiple sequentially numbered dump files. When using parallel export, enough dump files must be available for workers to write concurrently.

Corresponding import:

~~~text
impdp system@TARGET SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_%U.dmp LOGFILE=app_parallel_import.log PARALLEL=4
~~~

PARALLEL does not guarantee linear speedup. Bottlenecks can come from:

- CPU.
- Storage throughput/IOPS.
- Network if using a network link.
- Number of dump files and file placement.
- Database Resource Manager.
- Object dependencies and import steps that must run sequentially.
- Index builds or constraint validation.

Do not set PARALLEL excessively high on production without benchmark testing. Using many workers can place heavy load on the database and storage.

### FILESIZE

FILESIZE limits the size of each dump file. When the limit is reached, Data Pump switches to the next file if the template allows. If the dump file specifies a single fixed name without room for additional files, the job can fail when no space remains to write.

Ensure filesystem/ASM capacity and quotas are sufficient for the entire dump set, not just one file.

## 14. Compression and Encryption

Data Pump supports compression to reduce dump size and encryption to protect exported data. Features, licensing requirements, and compression levels depend on version/edition.

Example:

~~~text
expdp system@ORCL FULL=YES DIRECTORY=DP_DIR DUMPFILE=full_%U.dmp LOGFILE=full_secure.log COMPRESSION=ALL ENCRYPTION=ALL ENCRYPTION_MODE=PASSWORD
~~~

With password encryption mode, protect the password independently and pass it to import through a secure procedure. Do not write passwords into committed parameter files or logs.

Compression consumes CPU. Encryption can affect throughput and requires key management. Measure in an equivalent environment and verify feature usage rights under your license.

Not every COMPRESSION/ENCRYPTION value is available in every release or edition. Read the documentation for your exact version and confirm entitlement before applying.

## 15. Network Import with NETWORK_LINK

Data Pump can import directly from a source database over a database link without creating intermediate dump files in certain scenarios:

~~~text
impdp app_user@TARGET NETWORK_LINK=SRC_LINK SCHEMAS=APP_OWNER LOGFILE=network_import.log
~~~

NETWORK_LINK references an existing database link in the target database connecting to the source database. Check:

- The database link points to the correct source.
- Credentials and network route.
- Version and compatibility.
- Privileges on source objects.
- Bandwidth and latency.
- Workload impact on both source and target.

NETWORK_LINK is not a way to bypass security controls. Database links store or use authentication credentials; they must be protected, audited, and revoked per policy. For large datasets, network import can place sustained load on the network and source database.

## 16. Transportable Tablespaces

Transportable tablespaces move tablespace datafiles instead of unloading/loading rows individually. Data Pump exports the necessary metadata; the DBA copies datafiles to the target database and then imports the metadata.

General workflow:

~~~text
Source database
   |
   | check self-contained
   v
Tablespace set
   |
   | switch to READ ONLY per procedure
   v
Export metadata via expdp TRANSPORT_TABLESPACES
   |
   | copy datafiles to target
   v
Target database
   |
   | impdp TRANSPORT_DATAFILES
   v
Tablespace attached to target database
~~~

### Checking self-containment

A transportable tablespace set must be self-contained: objects in the transported tablespaces must not have dependencies outside the set according to Oracle's transportable rules.

You can check using DBMS_TTS:

~~~sql
BEGIN
  DBMS_TTS.TRANSPORT_SET_CHECK(
    ts_list          => 'APP_DATA,APP_INDEX',
    incl_constraints => TRUE,
    full_check       => TRUE
  );
END;
/

SELECT *
  FROM transport_set_violations;
~~~

If TRANSPORT_SET_VIOLATIONS returns rows, resolve the dependencies or expand the tablespace set as required. Dependencies may involve indexes, partitions, constraints, or objects located outside the tablespace.

### Setting tablespaces to READ ONLY

In the traditional workflow, tablespaces must be set to READ ONLY to ensure datafiles do not change while being copied:

~~~sql
ALTER TABLESPACE app_data READ ONLY;
ALTER TABLESPACE app_index READ ONLY;
~~~

This change affects applications writing data. Schedule a migration window and confirm no active transactions need to write to these tablespaces.

### Exporting metadata

~~~text
expdp system@SOURCE DIRECTORY=DP_DIR DUMPFILE=app_transport.dmp LOGFILE=app_transport_export.log TRANSPORT_TABLESPACES=APP_DATA,APP_INDEX
~~~

Depending on version and transport mode, additional options such as VERSION, TRANSPORT_FULL_CHECK, or related parameters may be needed. Consult Oracle documentation for your exact release.

### Copying datafiles

Copy the tablespace datafiles to a storage location accessible by the target database. You can use OS tools, storage replication, or an approved file transfer method. Ensure file copies finish completely and checksums/sizes are verified before importing.

### Importing metadata and attaching datafiles

~~~text
impdp system@TARGET DIRECTORY=DP_DIR DUMPFILE=app_transport.dmp LOGFILE=app_transport_import.log TRANSPORT_DATAFILES='/u02/oradata/app_data01.dbf','/u02/oradata/app_index01.dbf'
~~~

Paths must be the actual locations on the target database. If datafiles are copied to ASM or renamed, plan the path mapping accordingly.

After importing and confirming success, you can switch the tablespaces to READ WRITE in the target database:

~~~sql
ALTER TABLESPACE app_data READ WRITE;
ALTER TABLESPACE app_index READ WRITE;
~~~

Never open READ WRITE on both source and target simultaneously if both databases access the same datafile copy. Transportable workflows must manage file ownership and cutover timing explicitly.

## 17. Transportable Tablespaces and Different Endianness/Platforms

Transportable tablespaces between two platforms may require endian format conversion. Check platforms:

~~~sql
SELECT platform_name,
       endian_format
  FROM v$transportable_platform
 ORDER BY platform_name;
~~~

Check the database platform:

~~~sql
SELECT platform_name
  FROM v$database;
~~~

If endianness differs, datafiles must be converted using an Oracle-supported method, commonly RMAN CONVERT or an equivalent transportable tablespace conversion workflow. Do not simply copy files and import if formats are incompatible.

RMAN skeleton example:

~~~text
RMAN> CONVERT TABLESPACE app_data
  TO PLATFORM 'Linux x86 64-bit'
  FORMAT '/stage/converted/%U';
~~~

Exact syntax and conversion steps depend on source/target platforms, Oracle release, and file locations. Follow the transportable tablespaces documentation for your exact version and verify conversion results before importing.

### Version compatibility

Source and target databases must satisfy Data Pump and transportable tablespace compatibility requirements. The VERSION parameter can help export metadata for a target version in some cases, but it does not make new features or unsupported data types natively compatible with an older database.

Check:

- Oracle release and patch level.
- Character set and national character set.
- Time zone file version.
- Platform and endianness.
- Database compatibility setting.
- Data types, options, and components in use.

Do not begin transport without confirming the source/target compatibility matrix.

## 18. Consistency and Export Point in Time

When exporting data actively updated by applications, determine consistency requirements:

- Export using Data Pump's consistent snapshot mechanisms.
- Use FLASHBACK_SCN or FLASHBACK_TIME when a common point in time is needed.
- Ensure undo retention and undo space are sufficient to reconstruct the snapshot.
- With multiple business-related schemas, align on a single SCN if cross-schema consistency is required.
- With transportable tablespaces, control READ ONLY state and datafile copy timing.

A successfully created dump file does not automatically guarantee systems outside the database are at the same point in time. For example, attachments in object storage or message queues can change independently. Migrations should document external dependencies.

### FLASHBACK_SCN

Example:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_scn.dmp LOGFILE=app_scn.log FLASHBACK_SCN=123456789
~~~

The SCN must be determined beforehand and within the supported undo/flashback window. If the export runs long, allocate enough undo retention.

### FLASHBACK_TIME

~~~text
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 01:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Data Pump converts the timestamp into an appropriate SCN. Standardize timezones and avoid ambiguous times during daylight saving transitions or across hosts with different timezones.

## 19. Monitoring Data Pump Jobs

Data Pump jobs can run for a long time. Monitor them via:

- Direct output of expdp/impdp.
- The log file in DIRECTORY.
- ATTACH to reconnect to the job.
- Data dictionary views.

### ATTACHing to a job

If a terminal closes while the job keeps running:

~~~text
impdp system@TARGET ATTACH=SYS_IMPORT_SCHEMA_01
~~~

Obtain the job name from initial output or DBA_DATAPUMP_JOBS. Once attached, use interactive commands such as STATUS, STOP_JOB, START_JOB, or EXIT_CLIENT as needed.

Do not confuse EXIT_CLIENT with STOP_JOB. EXIT_CLIENT only detaches the client; the job continues running on the server. STOP_JOB stops the job in the specified mode and may require START_JOB to resume.

### Viewing jobs

~~~sql
SELECT owner_name,
       job_name,
       operation,
       job_mode,
       state,
       degree,
       attached_sessions
  FROM dba_datapump_jobs
 ORDER BY owner_name, job_name;
~~~

### Viewing Data Pump sessions

~~~sql
SELECT owner_name,
       job_name,
       instance_id,
       session_type,
       saddr
  FROM dba_datapump_sessions
 ORDER BY owner_name, job_name;
~~~

Some views/columns depend on version and access privileges. DBAs can use DBA_DATAPUMP_JOBS, DBA_DATAPUMP_SESSIONS, or GV$SESSION to identify associated workers/sessions.

## 20. Logs, METRICS, and Error Control

Always specify LOGFILE:

~~~text
LOGFILE=app_export.log
LOGTIME=ALL
METRICS=YES
~~~

LOGTIME adds timestamps to logs in supported modes; METRICS adds object/data processing metrics. Logs are vital evidence for troubleshooting and confirming which objects were imported.

A job can complete with warnings or skipped objects. Read the entire log and summarize:

- Job status.
- Exported/imported objects.
- Skipped or failed objects.
- ORA- errors and timestamps.
- Row counts loaded.
- Duration of each phase.
- Applied tablespace/schema remapping.

Do not rely solely on the shell exit code or the line "successfully completed" if the log still contains object errors requiring attention.

## 21. Common Data Pump Errors

| Error code | Typical meaning | What to check |
|---|---|---|
| ORA-39002 | Invalid operation | Check accompanying errors, mode, and parameters |
| ORA-39070 | Unable to open log file | DIRECTORY object, OS permissions, path, and disk space |
| ORA-39087 | Invalid DIRECTORY object | DIRECTORY name, privileges, and container |
| ORA-31640 | Unable to open dump file for reading | File existence, server path, OS permissions, mount, and filename |
| ORA-31693 | Table data object load/unload failed | Check subsequent errors, table, data types, space, and constraints |
| ORA-39151 | Table exists and was skipped per import behavior | TABLE_EXISTS_ACTION and target object state |
| ORA-39126 | Worker encountered unexpected error | Check error stack, worker trace, and root error |
| ORA-01031 | Insufficient privileges | DIRECTORY, Data Pump roles, object privileges, and create object rights |
| ORA-01653 / ORA-01654 | Unable to extend segment/index | Tablespace free space, autoextend, quota |
| ORA-01555 | Snapshot too old | Undo retention/size and export duration |

Error codes are only the starting point. Read surrounding lines in the log to find the root error and specific object.

## 22. Required Privileges for Data Pump

Required privileges depend on mode and object scope:

- Users typically need CREATE SESSION to connect.
- Users need READ/WRITE on the corresponding DIRECTORY object.
- Exporting one's own schema can be done with owner privileges and read access to schema objects.
- Exporting/importing another user's schema or objects requires appropriate privileges.
- Full database export/import typically requires DATAPUMP_EXP_FULL_DATABASE or DATAPUMP_IMP_FULL_DATABASE respectively.
- Creating users, tablespaces, or special objects may require additional administrative privileges.

Do not grant DBA solely to run expdp/impdp. Identify the exact mode, owners, objects, directories, and operations, and grant least privilege.

Checking roles:

~~~sql
SELECT grantee,
       granted_role
  FROM dba_role_privs
 WHERE grantee IN ('APP_USER', 'SYSTEM')
 ORDER BY grantee, granted_role;
~~~

For definer-rights PL/SQL or certain special operations, privileges via roles do not replace direct grants under Oracle rules. However, Data Pump jobs run under the appropriate user/job session context; review each mode's requirements instead of mechanically applying PL/SQL rules.

## 23. Securing Dump Files

Dump files can contain sensitive data, application structure metadata, usernames, grants, and configuration details. Protect dumps like a database copy:

- Restrict filesystem and DIRECTORY object permissions.
- Never place dumps in a web root or public folder.
- Encrypt dumps when data requires protection.
- Encrypt file transfer channels and verify source/destination.
- Store encryption passwords/keys separately from dumps.
- Define retention and secure deletion procedures.
- Never send dumps over email or public sharing services.
- Never put database passwords into PARFILEs or shell history.
- Delete temporary files once complete and authorized.

A user with READ on a DIRECTORY can read files in that directory through Oracle mechanisms; do not grant READ/WRITE broadly to PUBLIC or all schemas.

## 24. Planning Import into the Target Database

Before importing, prepare:

1. Target database created and in the appropriate state.
2. Correct target PDB/service.
3. DIRECTORY object pointing to the dump files.
4. Target users/schemas and authentication.
5. Tablespaces, datafiles, and quotas.
6. Character set and compatibility.
7. Required roles/object privileges.
8. Sequences, database links, directories, external files, and cross-schema dependencies.
9. Datafile space, TEMP, UNDO, and redo capacity.
10. Plan for handling existing objects.
11. Rollback plan and post-import testing.

Do not run a large import into an active production database serving applications without evaluating locks, redo, undo, storage, CPU, and DDL impact.

## 25. Example Schema Migration Workflow

Suppose you need to move schema APP_OWNER from a source database to a target database.

### Step 1: check source

- Confirm schemas and objects.
- Identify cross-schema dependencies.
- Determine SCN/time if consistency is required.
- Check dump storage capacity and DIRECTORY.
- Confirm export privileges.

### Step 2: export schema

Create a parameter file:

~~~text
SCHEMAS=APP_OWNER
DIRECTORY=DP_DIR
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_export.log
PARALLEL=4
FILESIZE=10G
LOGTIME=ALL
METRICS=YES
~~~

Run:

~~~text
expdp system@SOURCE PARFILE=app_owner_export.par
~~~

### Step 3: transfer dump

Copy all dump pieces and retained logs to staging/target over a protected channel. Verify file counts, sizes, and checksums if required by procedure.

### Step 4: prepare target

- Create or verify APP_OWNER.
- Create tablespaces and quotas.
- Create a DIRECTORY object pointing to the dump location on the target server.
- Grant READ/WRITE on DIRECTORY.
- Check compatibility.

### Step 5: import

~~~text
impdp system@TARGET PARFILE=app_owner_import.par
~~~

Example parameter file:

~~~text
SCHEMAS=APP_OWNER
DIRECTORY=DP_DIR
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_import.log
PARALLEL=4
LOGTIME=ALL
METRICS=YES
~~~

If changing schema or tablespace, add REMAP_SCHEMA/REMAP_TABLESPACE per confirmed mapping.

### Step 6: post-import verification

- Read logs and resolve any object errors.
- Check invalid objects.
- Check row counts and key business totals.
- Check indexes/constraints/triggers.
- Check sequences and next sequence values.
- Check grants, roles, synonyms, and database links.
- Check scheduler jobs and external dependencies.
- Run application smoke tests.
- Verify connection services and users are correct.

Example checking invalid objects:

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
  FROM dba_objects
 WHERE owner = 'APP_OWNER'
   AND status = 'INVALID'
 ORDER BY object_type, object_name;
~~~

Do not compare only total row counts. Check business totals, primary keys, referential integrity, and data in critical tables.

## 26. Example Table Migration Workflow

If you only need to move a table:

Export:

~~~text
expdp app_owner@SOURCE TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders.dmp LOGFILE=orders_export.log
~~~

Import:

~~~text
impdp app_owner@TARGET TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders.dmp LOGFILE=orders_import.log TABLE_EXISTS_ACTION=SKIP
~~~

If the table already exists, choose SKIP, APPEND, TRUNCATE, or REPLACE based on the objective. Before importing, check:

- Does the target table have the same structure as the source?
- Is there existing data that must be preserved?
- Are indexes and constraints being imported?
- Will triggers fire during data load?
- Do sequences need synchronization?
- Are there parent/child tables that must move together?
- Could foreign keys or triggers create side effects?

If consistent data across multiple related tables is needed, consider a schema export or a shared SCN instead of exporting individual tables at different times.

## 27. When to Choose Which Mode?

| Need | Usually appropriate choice | Reason |
|---|---|---|
| Moving nearly all database objects | FULL=YES | Broad coverage; requires matching privileges and target planning |
| Moving an application by schema | SCHEMAS | Keeps objects by owner, easy to remap schema |
| Moving a few tables | TABLES | Reduces scope, suitable for selective data exchange |
| Logically exporting tables in specific tablespaces | TABLESPACES | Selects objects by tablespace location |
| Moving large data volumes via datafiles | TRANSPORT_TABLESPACES | Avoids row-by-row unload/load, subject to transportable conditions |
| Importing directly from source database | NETWORK_LINK | Can avoid intermediate dumps; depends on network and database link |
| Exporting only rows matching a condition | QUERY | Filters data in the dump |
| Exporting only certain object types | INCLUDE/EXCLUDE | Filters metadata by object path |

The final choice should consider RTO, RPO, volume, downtime, compatibility, consistency, dependencies, and rollback capability.

## 28. Common Mistakes

**Confusing DIRECTORY objects with client folders:** Data Pump server reads/writes paths on the database server. Check the right host and filesystem permissions.

**Using FULL=YES like an RMAN backup:** Data Pump is a logical export; it does not copy all physical database files.

**Confusing TABLESPACES with TRANSPORT_TABLESPACES:** one mode performs a logical export, while the other transfers datafiles and metadata.

**Copying only one dump piece:** when using %U/PARALLEL, transfer all dump pieces completely.

**Importing into a schema with existing data without choosing TABLE_EXISTS_ACTION:** it may skip, append, truncate, or replace according to default/option behavior; decide explicitly.

**Using REMAP_SCHEMA while forgetting dependencies:** hardcoded schema names, database links, jobs, and external configurations may still point to the source.

**Setting PARALLEL too high:** can cause I/O, CPU, and TEMP pressure.

**Omitting FLASHBACK_SCN/TIME when a common snapshot is needed:** tables exported at different times may fail business consistency requirements.

**Not checking DIRECTORY privileges:** a user may connect to the database yet the job fails to open dump/log files.

**Not reading the import log:** a job can finish while some objects were skipped or failed.

**Not verifying sequences and constraints:** data may import completely while the application fails on subsequent writes.

**Not securing dumps:** dump files can contain sensitive data equivalent to a database copy.

## 29. Pre- and Post-Export/Import Checklist

### Before export

- [ ] Determine mode: FULL, SCHEMAS, TABLES, TABLESPACES, or TRANSPORT_TABLESPACES.
- [ ] Identify source database/PDB and service.
- [ ] Confirm owner and Data Pump privileges.
- [ ] Confirm DIRECTORY and OS permissions.
- [ ] Define dump file naming, FILESIZE, and PARALLEL.
- [ ] Evaluate consistency and FLASHBACK_SCN/TIME.
- [ ] Check free space and encryption/compression.
- [ ] Document dependencies outside export scope.

### Before import

- [ ] Confirm all dump pieces are present and readable.
- [ ] Confirm target database/PDB/service.
- [ ] Prepare users, roles, tablespaces, and quotas.
- [ ] Grant READ/WRITE on DIRECTORY.
- [ ] Verify compatibility, character set, and version.
- [ ] Choose REMAP_SCHEMA/REMAP_TABLESPACE if needed.
- [ ] Determine TABLE_EXISTS_ACTION and object conflicts.
- [ ] Prepare rollback and change window.

### After import

- [ ] Read the entire log and all errors.
- [ ] Check invalid objects.
- [ ] Verify row counts and business metrics.
- [ ] Check indexes, constraints, triggers, and sequences.
- [ ] Check grants, synonyms, jobs, and database links.
- [ ] Check external dependencies.
- [ ] Run smoke tests and verify application connections.
- [ ] Retain dumps, logs, checksums, and evidence per retention policy.

## 30. Conclusion

Oracle Data Pump provides export/import modes by database, schema, table, and tablespace. FULL=YES fits broad scope; SCHEMAS fits applications grouped by owner; TABLES fits specific tables; TABLESPACES selects data by tablespace. Distinguish TABLESPACES from TRANSPORT_TABLESPACES: transportable tablespaces transfer datafiles along with metadata and require self-contained checks, READ ONLY state, platform/endian checks, and compatibility.

A safe movement workflow must prepare server-side DIRECTORY objects, Data Pump and filesystem privileges, dump pieces, consistency, storage, users/schemas, tablespaces, remapping, and dependencies. After import, read logs, check objects, data, sequences, constraints, grants, jobs, and run smoke tests. Dump files must be protected like sensitive data; Data Pump export/import is a logical movement mechanism and does not replace RMAN backup/restore.
