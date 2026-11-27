# Data Pump: expdp, impdp, and Server-Side Processing

Oracle Data Pump is Oracle Database's logical data export and import toolset. The two commonly used utilities are `expdp` for export and `impdp` for import. DBAs use Data Pump to move schemas, tables, metadata, data, or parts of a database between environments; create extracts for testing; and transfer data between compatible Oracle versions.

A critical operational point of Data Pump is that **reading and writing data are performed primarily by processes on the database server**. The machine running the `expdp` or `impdp` command only initiates and controls the job. Therefore, dump file and log file paths are resolved on the database server via a `DIRECTORY` object, not in the current working directory of the terminal running the utility.

## 1. How Does Data Pump Work?

### 1.1. The two utilities expdp and impdp

| Utility | Role | Data direction |
|---|---|---|
| `expdp` | Exports data and metadata from the database to dump files or transfers directly over a database link. | Source database → dump set or target database. |
| `impdp` | Imports data and metadata from dump files or reads directly from a source database over a database link. | Dump set or source database → target database. |

Data Pump is a logical data movement tool. It exports database objects and data within a selected scope; it is not a physical backup that replaces RMAN. RMAN protects and recovers datafiles, control files, and archived redo logs using physical backup/recovery mechanisms. Data Pump is appropriate when you need to select schemas/tables, rename schemas, change tablespaces, or recreate objects in another database.

### 1.2. Server-side processing

When running `expdp` or `impdp`, the client connects to the database and requests the creation of a Data Pump job. The database creates a master table to track job metadata and state, and then coordinates Data Pump server processes/workers to read, write, transform, and load data.

```text
Machine running expdp / impdp
       |
       |  Oracle Net connection, sends parameters and control commands
       v
Oracle Database instance
       |
       +---- Master table / job metadata
       |
       +---- Data Pump master process
       |
       +---- Worker processes
       |          |
       |          +---- Read/write tables and metadata
       |          +---- Parallel processing when configured
       |
       v
DIRECTORY object on the database server
       |
       +---- Dump file(s)
       +---- Log file
       +---- SQLFILE or related files
```

The client can run on a DBA workstation, application host, or separate management host. Dump files and log files are still read/written at the server-side location pointed to by the `DIRECTORY` object. This is an important distinction compared to using `scp`, `cp`, or a client tool that writes files locally on its own machine.

### 1.3. What resides on the client and what resides on the server

| Component | Where it is processed or stored |
|---|---|
| `expdp`/`impdp` executable | Machine running the utility; requires a compatible Oracle client. |
| Database connection and job parameters | Sent by the client to the database server. |
| Parameter file (`PARFILE`) | Read by the client utility from the machine running the command. |
| Data Pump master table and workers | Database server. |
| Dump file (`DUMPFILE`) | Filesystem or storage accessed by the database server through the directory object. |
| Log file (`LOGFILE`) | Directory on the database server. |
| DDL file from `SQLFILE` | Directory on the database server. |

For example, if a DBA runs `expdp` from a laptop and the database server runs on Linux, `DIRECTORY=DP_DIR` still points to the Linux directory on the server. The laptop's `C:\temp` folder does not automatically become the dump file destination just because the command was run from Windows.

## 2. Preparing the DIRECTORY Object

### 2.1. What is a directory object?

Oracle uses a database directory object to map a logical name to a filesystem path on the database server. For example, a DBA creates `DP_DIR` pointing to `/u01/dpump`:

```sql
CREATE DIRECTORY dp_dir AS '/u01/dpump';
```

`CREATE DIRECTORY` only creates metadata in the database; it does not automatically create the folder on the operating system. The DBA or system administrator must create the directory and grant read/write permissions to the OS account running Oracle Database.

You can check directory objects:

```sql
SELECT directory_name, directory_path
FROM dba_directories
WHERE directory_name = 'DP_DIR';
```

Directory object names are typically stored in uppercase unless created with a quoted identifier.

### 2.2. Granting READ and WRITE privileges

The user running Data Pump needs privileges on the directory object. For example:

```sql
GRANT READ, WRITE ON DIRECTORY dp_dir TO app_migration;
```

`READ` allows reading files in the directory; `WRITE` allows creating or writing files. Export usually requires privileges to write dump/log files; import requires reading dumps and writing logs. If `SQLFILE` is used, Data Pump needs to write the SQL file into the directory.

Database privileges on a directory object and OS filesystem permissions are two separate layers:

- `GRANT READ, WRITE ON DIRECTORY` allows the database user to use the directory through Oracle.
- Filesystem permissions must allow the OS account running the database to read or write the actual directory.

If either layer lacks permissions, the job can fail with a file access error even if the other layer is configured properly.

### 2.3. Creating the directory and setting OS permissions

On Linux, for example, a system administrator creates the directory and grants permissions to the Oracle software owner:

```bash
mkdir -p /u01/dpump
chown oracle:oinstall /u01/dpump
chmod 750 /u01/dpump
```

The actual user/group names and permissions must follow server security standards. Do not use `777` permissions just to work around a Data Pump error. If the directory resides on NFS, an object storage gateway, or a shared filesystem, verify mounts, access permissions, free space, quotas, and accessibility from every instance that may run workers.

### 2.4. Default directory DATA_PUMP_DIR

Oracle often provides the `DATA_PUMP_DIR` directory object in supported installations. You can inspect it:

```sql
SELECT directory_name, directory_path
FROM dba_directories
WHERE directory_name = 'DATA_PUMP_DIR';
```

Do not assume the path or privileges of `DATA_PUMP_DIR` are identical across environments. Verify the server-side path, space, and grants before using it. In production systems, purpose-specific directories with restricted privileges are usually easier to govern.

## 3. Export and Import Modes

Data Pump supports multiple job scopes. Choosing the right mode limits the data moved and reduces processing time.

| Mode | Parameter | Scope |
|---|---|---|
| Full database | `FULL=YES` | Exports/imports at the database scope according to privileges and supported objects. |
| Schema | `SCHEMAS=...` | One or more schemas. |
| Table | `TABLES=...` | One or more tables; partitions can be specified as needed. |
| Tablespace | `TABLESPACES=...` | Objects belonging to the selected tablespace scope. |
| Transportable | `TRANSPORTABLE=...` and related options | Moves tablespaces using the transportable mechanism, subject to compatibility and self-contained conditions. |

Example schema export:

```text
SCHEMAS=APP
```

Export specific tables:

```text
TABLES=APP.CUSTOMERS,APP.ORDERS
```

Full database export:

```text
FULL=YES
```

Full export requires appropriate Data Pump privileges, typically involving the `DATAPUMP_EXP_FULL_DATABASE` role; full import may require `DATAPUMP_IMP_FULL_DATABASE`. Exact privileges depend on the operation, objects, and version. Do not grant broad roles just to bypass an uninvestigated privilege error.

A user can export their own schema within their ownership and required privileges. When exporting another schema, another user's tables, or performing a full export, verify the corresponding roles and grants.

### 3.1. Selecting export/import content

The `CONTENT` parameter determines what content is included:

| Value | Meaning |
|---|---|
| `ALL` | Metadata and data. This is the common default. |
| `DATA_ONLY` | Data only, without creating object metadata. |
| `METADATA_ONLY` | Metadata only, without loading table data. |

Example exporting structure only:

```text
CONTENT=METADATA_ONLY
```

Exporting data only:

```text
CONTENT=DATA_ONLY
```

When importing `DATA_ONLY`, the target tables and required structures must already exist or be prepared appropriately. When importing `METADATA_ONLY`, table data is not loaded.

### 3.2. Estimating size and time

Data Pump can estimate size before exporting:

```text
ESTIMATE_ONLY=YES
ESTIMATE=BLOCKS
```

Or using statistics:

```text
ESTIMATE=STATISTICS
```

An estimate is not a guarantee of the final dump size. Compression, metadata, LOB data, data distribution, and dump file layout can make the actual size differ. Leave a buffer and monitor filesystem space while the job runs.

## 4. Using expdp to Export

### 4.1. Basic syntax

A typical schema export command looks like:

```bash
expdp app_migration@ORCLPDB \
  SCHEMAS=APP \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_export_%U.dmp \
  LOGFILE=app_export.log
```

After entering the command, the client may prompt for a password if a secure authentication mechanism is not configured. Avoid placing passwords directly on the command line because they can appear in process lists, shell history, or management tool logs. Use interactive prompts, an external password store, or an organization-approved credential method.

In the example:

- `SCHEMAS=APP` selects the schema to export.
- `DIRECTORY=DP_DIR` specifies the directory object on the database server.
- `DUMPFILE=app_export_%U.dmp` sets the dump file naming pattern; `%U` allows Data Pump to generate multiple files when needed.
- `LOGFILE=app_export.log` creates the log in the server-side directory.

### 4.2. Exporting specific tables

```bash
expdp app_migration@ORCLPDB \
  TABLES=APP.CUSTOMERS,APP.ORDERS \
  DIRECTORY=DP_DIR \
  DUMPFILE=customer_orders_%U.dmp \
  LOGFILE=customer_orders_export.log
```

You can export specific table partitions or subpartitions when you need to extract a subset of data. Confirm `TABLES` syntax for your objects and version. Exporting a table can pull in dependent metadata; do not assume the dump contains only a single table completely isolated from related objects.

### 4.3. Using PARFILE to manage parameters

When there are many parameters, use a parameter file for readability and to save job configuration. Example `app_export.par` on the machine running the client utility:

```text
DIRECTORY=DP_DIR
DUMPFILE=app_export_%U.dmp
LOGFILE=app_export.log
JOB_NAME=APP_EXPORT_JOB
SCHEMAS=APP
PARALLEL=4
FILESIZE=10G
METRICS=YES
LOGTIME=ALL
```

Run:

```bash
expdp app_migration@ORCLPDB PARFILE=app_export.par
```

`PARFILE` is read by the client on the machine running `expdp`; meanwhile, `DUMPFILE` and `LOGFILE` still reside in the server-side directory. Do not put real passwords in a parfile if the file may be stored in source control, shared folders, or deployment logs.

### 4.4. Splitting dumps into multiple files

For large datasets, use `%U` along with `PARALLEL` and `FILESIZE`:

```text
DUMPFILE=app_export_%U.dmp
PARALLEL=4
FILESIZE=10G
```

`%U` enables sequential file naming, such as `app_export_01.dmp`, `app_export_02.dmp`. `FILESIZE` caps the size of each individual dump file as configured. `PARALLEL` sets the maximum number of requested workers; actual throughput depends on CPU, I/O, storage, and database processing capacity.

A dump set can consist of multiple files. When importing, all files belonging to the dump set must be provided. A missing file can prevent the job from reading the complete dataset.

### 4.5. Filtering objects and data

`INCLUDE` and `EXCLUDE` allow selecting or omitting specific object types. Do not use both parameters simultaneously in the same job.

Example exporting only tables and indexes:

```text
INCLUDE=TABLE
INCLUDE=INDEX
```

Example excluding optimizer statistics:

```text
EXCLUDE=STATISTICS
```

To filter rows in a table, you can use `QUERY`. Example in a parfile:

```text
TABLES=APP.ORDERS
QUERY=APP.ORDERS:"WHERE ORDER_DATE >= DATE '2026-01-01'"
```

`QUERY` filters exported data; specify the schema and table clearly when multiple tables share a name or the job includes multiple tables. The condition must match the data types and Oracle SQL syntax. When using special characters, quotes, or shell quoting, test the parfile in a non-production environment first.

### 4.6. Consistent point-in-time export

When data changes during an export, a consistent logical snapshot may be required. Data Pump supports `FLASHBACK_SCN` or `FLASHBACK_TIME` in appropriate cases.

Example:

```text
FLASHBACK_SCN=123456789012
```

The export reads data as of the chosen SCN if flashback conditions and undo retention allow. Choose a valid SCN, ensure sufficient undo, and check job duration. If undo is insufficient, the job can fail with snapshot/undo errors. Avoid choosing an overly old SCN without evaluating consistent read capability.

## 5. Using impdp to Import

### 5.1. Importing a schema from a dump file

Example importing schema `APP` into a target database:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_export_%U.dmp \
  LOGFILE=app_import.log \
  SCHEMAS=APP
```

The dump file must be placed in the target database's server-side directory, not merely on the client machine running `impdp`. If the files are on another host, transfer them to storage accessible by the target database or use `NETWORK_LINK` to read directly from the source database.

### 5.2. Remapping schemas

When moving a source schema to a different name on the target:

```text
REMAP_SCHEMA=APP:APP_TEST
```

Example:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_export_%U.dmp \
  LOGFILE=app_test_import.log \
  REMAP_SCHEMA=APP:APP_TEST
```

`REMAP_SCHEMA` maps the source owner to the target owner. The target user should already exist or be created via an appropriate procedure; Data Pump does not always create users and grant all login privileges required by the application. Check tablespaces, quotas, roles, grants, database links, directories, and object dependencies after importing.

### 5.3. Remapping tablespaces

`REMAP_TABLESPACE` maps segments from a source tablespace to a target tablespace:

```text
REMAP_TABLESPACE=APP_DATA:APP_DATA_TEST
REMAP_TABLESPACE=APP_INDEX:APP_INDEX_TEST
```

This is useful when the target database has a different storage layout. Create the target tablespaces and verify size, autoextend, encryption, quotas, and naming standards before importing. Certain objects or special import modes have specific rules; do not assume every tablespace reference is remapped identically.

### 5.4. Handling existing tables

When a target table already exists, `TABLE_EXISTS_ACTION` determines how data is imported:

| Value | Behavior |
|---|---|
| `SKIP` | Skips existing tables. This is the common default. |
| `APPEND` | Loads additional rows into existing tables. |
| `TRUNCATE` | Deletes existing rows via truncate and then loads new data. |
| `REPLACE` | Drops the existing table, recreates it from dump metadata, and loads data. |

Example:

```text
TABLE_EXISTS_ACTION=APPEND
```

Choosing the wrong action can create duplicate data, wipe existing data, or lose schema changes on the target. `TRUNCATE` and `REPLACE` destroy data/objects; verify backups, scope, and approvals before using them. Behavior can depend on the import type and other parameters.

### 5.5. Importing metadata or data only

Create objects only:

```text
CONTENT=METADATA_ONLY
```

Load data rows only:

```text
CONTENT=DATA_ONLY
```

These modes are useful when you need to deploy the schema first and load data later, or when tables have already been created by migration scripts. Ensure constraints, indexes, triggers, and sequences match the import order and application requirements.

### 5.6. Previewing DDL with SQLFILE

`SQLFILE` instructs `impdp` to write the planned DDL statements to a file instead of executing them. Example:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_export_%U.dmp \
  SQLFILE=app_preview.sql \
  SCHEMAS=APP
```

The `app_preview.sql` file is written to the server-side directory. You can use it to preview objects, owners, tablespaces, and DDL before the actual import. `SQLFILE` is not a full dry-run import: it does not load data and does not prove that every import step will succeed.

## 6. Direct Movement Over NETWORK_LINK

Data Pump can read data directly from the source database over a database link without creating intermediate dump files. Example importing a schema from a source database:

```bash
impdp app_migration@TARGETPDB \
  NETWORK_LINK=SOURCE_LINK \
  SCHEMAS=APP \
  LOGFILE=network_import.log \
  DIRECTORY=DP_DIR
```

`SOURCE_LINK` is a database link created in the target database pointing to the source database. The job runs on the target database; data is read over the database link connection. The log is still written to the target database's server-side directory. There is no dump file in this example.

Preparation points:

- The database link must connect to the correct source service.
- The user accessed via the database link must have privileges to read the objects and metadata to export.
- The network between the two databases must be stable and have adequate bandwidth.
- Versions, character sets, data types, and features must be compatible.
- Load on both source and target must be evaluated; network import is not resource-free.

`NETWORK_LINK` can be useful when you do not want to manage dump files, but it does not replace a backup plan. If the connection drops or the dataset is large, evaluate restartability and runtime. For critical migrations, dump files can be easier to control, inspect, and hand off.

## 7. Compatibility and Migration Scenarios

### 7.1. Across Oracle versions

When exporting from a newer version to an older version, verify dump metadata and feature compatibility. The `VERSION` parameter can constrain the metadata version generated by Data Pump:

```text
VERSION=19.0
```

The value must match the target version and Oracle documentation. `VERSION` does not convert a new feature into an old one; objects or attributes unsupported by the target version may fail to export/import. Test on a clone and inspect warning logs.

### 7.2. Transportable tablespaces

Transportable tablespaces allow moving tablespace datafiles along with metadata instead of exporting all rows conventionally. This can be fast for large datasets, but it requires a self-contained tablespace set, platform/endian compatibility or an appropriate conversion step, and strict adherence to the read-only/export/copy/import sequence.

This is a specialized migration technique; do not treat `TRANSPORTABLE=ALWAYS` as a simple drop-in parameter for schema export. Verify self-contained conditions, datafiles, endianness, encryption, and versions before deployment.

### 7.3. Moving encrypted data

If the source data uses TDE, consider both tablespace/column encryption and dump file encryption. Data Pump may require a keystore or export/import password matching the encryption mode. When moving to another database, plan TDE key transfer through a secure procedure if data or dumps must be decrypted at the target.

Do not place keystore passwords, encryption passwords, or key material into broadly readable parfiles. Store credentials in a secret manager and test importing with the exact planned encryption mechanism.

## 8. Monitoring and Controlling Data Pump Jobs

### 8.1. Setting JOB_NAME and LOGTIME/METRICS

Naming a job helps DBAs identify and attach to it when needed:

```text
JOB_NAME=APP_EXPORT_20261114
LOGTIME=ALL
METRICS=YES
STATUS=60
```

- `JOB_NAME` names the Data Pump job.
- `LOGTIME=ALL` adds timestamps to log messages on supported versions.
- `METRICS=YES` adds processing statistics to the log.
- `STATUS=60` displays status periodically at the specified second interval while the client waits.

Display and logging parameters can vary across versions. Use `HELP=Y` or version documentation to confirm supported parameters.

### 8.2. Attaching to a running job

If the client closes or loses connection, the server-side job may continue running. A DBA can reconnect and attach using the job name:

```bash
expdp app_migration@ORCLPDB ATTACH=APP_EXPORT_20261114
```

Or for import:

```bash
impdp app_migration@TARGETPDB ATTACH=APP_IMPORT_20261114
```

In interactive command mode, you can check status:

```text
Export> STATUS
```

Exiting the client with `EXIT_CLIENT` detaches the client from the job; it does not stop the job. Distinguish client detach from stopping or killing a job.

### 8.3. Stopping and resuming a job

In interactive mode, Data Pump supports control commands such as:

```text
Export> STOP_JOB=IMMEDIATE
```

After the job stops, you can reattach and run:

```text
Export> START_JOB
```

`STOP_JOB=IMMEDIATE` stops the job immediately; the job can usually be restarted if metadata and required files remain intact. `STOP_JOB` is not a job deletion operation. Before stopping, inspect workers, current state, storage space, and application impact.

`KILL_JOB` terminates and removes the job via Data Pump; this is a stronger option and may prevent resuming the job. Do not use it when you only want to pause for maintenance.

### 8.4. Monitoring via the data dictionary

Useful views:

```sql
SELECT owner_name, job_name, operation, job_mode,
       state, degree, attached_sessions, datapump_sessions
FROM dba_datapump_jobs
ORDER BY owner_name, job_name;
```

```sql
SELECT owner_name, job_name, instance_id, saddr, session_type
FROM dba_datapump_sessions
ORDER BY owner_name, job_name;
```

`DBA_DATAPUMP_JOBS` and `DBA_DATAPUMP_SESSIONS` show jobs, states, and associated sessions. Column names may differ across versions; check the actual data dictionary if a query does not match.

You can monitor progress through `V$SESSION_LONGOPS` during certain processing phases:

```sql
SELECT
    sid,
    serial#,
    opname,
    sofar,
    totalwork,
    units,
    elapsed_seconds,
    time_remaining
FROM v$session_longops
WHERE opname LIKE 'SYS_EXPORT%'
   OR opname LIKE 'SYS_IMPORT%'
ORDER BY start_time DESC;
```

`V$SESSION_LONGOPS` does not necessarily display complete progress for every phase or object type. Combine logs, interactive `STATUS`, Data Pump views, and storage/CPU/I/O monitoring for evaluation.

### 8.5. Job master table

Data Pump creates a master table in the job-owning schema to store state and control metadata. When the job completes successfully, the master table is normally cleaned up by Data Pump. For stopped or failed jobs, metadata may remain to support attach/resume.

Do not manually drop the master table without understanding the job state. Dropping it mistakenly can break resumability or complicate cleanup. Use `ATTACH`, `STATUS`, `STOP_JOB`, `START_JOB`, or `KILL_JOB` according to your goal.

## 9. Data Pump in RAC Environments

In Oracle RAC, Data Pump can use multiple instances when cluster and storage configuration allow. If a directory path exists on only one node, workers running on other nodes may fail to access dump/log files.

Items to verify:

- The directory object points to a shared filesystem or storage accessible by all participating nodes.
- OS permissions for the Oracle owner are consistent across nodes.
- Dump files and log files are not on a local filesystem visible to only one node if the job can distribute across nodes.
- `PARALLEL` and `CLUSTER` are chosen based on storage capacity and operational goals.

If only one node can access the directory, consider `CLUSTER=NO` to confine the job to the connected instance in supported cases. However, this is no substitute for proper shared storage design. Confirm syntax, services, and behavior on your specific RAC version.

## 10. Security When Running Data Pump

### 10.1. Principle of least privilege

- Grant `READ`/`WRITE` on only the required directory objects.
- Grant privileges to export/import other schemas or the full database only when there is a clear assignment.
- Do not grant `DATAPUMP_EXP_FULL_DATABASE` or `DATAPUMP_IMP_FULL_DATABASE` routinely.
- Protect the server-side filesystem; prevent unrelated OS users from reading dump files.
- Place logs and dumps in storage with appropriate retention and access controls.
- Review grants, roles, and owners after import.

Dump files can contain sensitive data in readable or decryptable form depending on configuration. Protect dumps like production data unless properly masked or encrypted.

### 10.2. Encrypting dump files

Data Pump supports dump file encryption via `ENCRYPTION` modes depending on version and configuration. Illustrative example:

```text
ENCRYPTION=ALL
ENCRYPTION_MODE=PASSWORD
ENCRYPTION_PASSWORD=<secret>
```

Options can include encrypting data, metadata, or the entire dump; modes can be password-based, transparent, or dual depending on the version. Check version documentation before choosing. Do not put real passwords on the command line or in long-lived parfiles. Passwords should be handled via a secret manager and remain retrievable for the backup's valid lifetime.

If using transparent encryption based on TDE, importing depends on the keystore and associated keys. If using password mode, losing the password makes the dump impossible to decrypt. Therefore, credentials are an integral part of the backup/restore process, not secondary information.

### 10.3. Protecting login credentials

Avoid writing `username/password@service` with real passwords in shell history, scripts, or schedules. Safer alternatives depending on the environment include:

- Letting the utility prompt for the password interactively.
- Using Oracle Secure External Password Store or a managed wallet mechanism.
- Using dedicated service accounts and a secret manager integrated with the scheduler.
- Restricting read permissions on parfiles, scripts, logs, and working directories.

Do not place credentials inside `PARFILE` just to bundle all parameters into one file. A parfile should contain job configuration; secrets require a separate lifecycle and access control.

## 11. Common Errors and Troubleshooting

| Error or symptom | Possible cause | Resolution |
|---|---|---|
| `ORA-39002: invalid operation` | Invalid Data Pump parameter or operation in the current context. | Read the full log, check syntax and privileges. |
| `ORA-39070: Unable to open the log file` | Directory object, database privilege, or OS permission issue; filesystem unavailable. | Check `DBA_DIRECTORIES`, grants, and OS permissions on the database server. |
| `ORA-39087: directory name ... is invalid` | Directory object does not exist or name is incorrect. | Verify the directory name and current container. |
| `ORA-29283: invalid file operation` | Oracle server process cannot open/write the file at the path. | Check server-side path, mounts, OS permissions, space, and SELinux/ACLs if present. |
| `ORA-31640` / `ORA-27037` | Dump file cannot be read or does not exist where the server sees it. | Confirm the file is in the server-side directory with exact name and read permission. |
| `ORA-31684` | Object already exists during import. | Review log and choose `TABLE_EXISTS_ACTION` or handle the object per plan. |
| `ORA-39151` | Object skipped because it already exists or due to import policy. | Confirm import action and target object. |
| Job slow or showing no clear progress | I/O, CPU, network, locks, LOBs, or worker resource contention. | Check `STATUS`, log, `V$SESSION_LONGOPS`, storage, and wait events. |
| Import missing data | Missing dump piece, incorrect filter, or job failed mid-run. | Check dump set, log, `QUERY/INCLUDE/EXCLUDE` parameters, and job status. |
| Import privilege errors | Target user lacks quota, object privileges, or create object privileges. | Identify the specific object and grant least-privilege permissions. |

The root error message usually appears before summary `ORA-390xx` errors. Reading the entire log and identifying the first error makes root-cause analysis more accurate.

## 12. Sample Migration Workflow

Suppose you need to move schema `APP` from a source database to a test PDB, change the owner to `APP_TEST`, and move segments to tablespace `APP_DATA_TEST`.

### 12.1. Preparing source and target

On the source:

- Confirm schemas, objects, sizes, LOBs, and dependencies.
- Choose a consistent data point in time or schedule downtime if needed.
- Confirm the export user has required privileges.

On the target:

- Create target tablespaces and user `APP_TEST` per administrative procedure.
- Create a directory object pointing to server-side storage.
- Grant directory privileges to the migration user.
- Check version, character set, quotas, grants, and free space.

### 12.2. Export

Create `app_export.par` on the machine running the client:

```text
DIRECTORY=DP_DIR
DUMPFILE=app_migration_%U.dmp
LOGFILE=app_migration_export.log
JOB_NAME=APP_MIGRATION_EXPORT
SCHEMAS=APP
PARALLEL=4
FILESIZE=10G
LOGTIME=ALL
METRICS=YES
```

Run:

```bash
expdp app_migration@SOURCEPDB PARFILE=app_export.par
```

Wait for the job to complete and inspect the log. Then transfer all dump pieces from source server-side storage to a location readable by the target database. Verify all files, sizes, and checksums before importing.

### 12.3. Previewing DDL

On the target, use `SQLFILE` to generate a DDL preview:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  SQLFILE=app_migration_preview.sql \
  REMAP_SCHEMA=APP:APP_TEST \
  REMAP_TABLESPACE=APP_DATA:APP_DATA_TEST
```

Read the preview file on server-side storage and confirm owners, tablespaces, objects, and planned DDL statements. This is a metadata check step; no data has been loaded yet.

### 12.4. Import

After approval, run the import:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  LOGFILE=app_migration_import.log \
  JOB_NAME=APP_MIGRATION_IMPORT \
  REMAP_SCHEMA=APP:APP_TEST \
  REMAP_TABLESPACE=APP_DATA:APP_DATA_TEST \
  LOGTIME=ALL \
  METRICS=YES
```

If re-importing into a schema that already contains tables, specify `TABLE_EXISTS_ACTION` based on the goal. Do not add `REPLACE` or `TRUNCATE` simply to silence object-exists errors.

### 12.5. Post-import verification

- Read the log and identify every error, warning, or skipped object.
- Compare object lists, row counts, and business data with the source against agreed criteria.
- Check invalid objects and recompile per procedure.
- Check indexes, constraints, triggers, sequences, grants, roles, synonyms, and database links.
- Verify the target user has appropriate quotas and least-privilege permissions.
- Run application smoke tests on the target PDB.
- Retain dumps, logs, and checksums per approved retention policy.

## 13. Good Operational Practices

- Always remember `DIRECTORY` is a server-side directory object; `PARFILE` is a client-side file.
- Verify the database service and container before running export/import.
- Use `PARFILE` for jobs with many parameters, but do not store passwords inside it.
- Use `JOB_NAME`, `LOGTIME`, and `METRICS` for easier monitoring and investigation.
- Use `%U`, `PARALLEL`, and `FILESIZE` when multiple dump pieces are needed; ensure the import has all files.
- Estimate size and check filesystem capacity and bandwidth before running large jobs.
- Choose `CONTENT`, `SCHEMAS`, `TABLES`, `INCLUDE`, `EXCLUDE`, and `QUERY` to match the required scope.
- Use `SQLFILE` to preview DDL when an import has broad impact.
- Use `ATTACH` to manage server-side jobs; distinguish detach, stop, resume, and kill.
- In RAC, confirm directory storage is accessible by workers on all participating nodes.
- Protect dump files, logs, and credentials; encrypt dumps when sensitive data requires protection.
- Read full logs and validate data after import; do not treat exit code as the sole proof.

## Conclusion

Data Pump `expdp` and `impdp` are flexible tools for logical data movement. The client initiates and controls the job, while the database server performs the work and accesses dump/log files through directory objects. Understanding the client/server boundary, database privileges, and filesystem permissions is the first requirement for avoiding path and file access errors. By combining the right export/import modes, parfiles, filters, remapping, job monitoring, security controls, and post-import verification, DBAs can move schemas or data between environments in a controlled and traceable way.
