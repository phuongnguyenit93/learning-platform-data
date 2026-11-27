# DIRECTORY Objects, Privileges, and Dump/Log Locations

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Data Movement  
> **Objective:** Understand how DIRECTORY objects map database names to server paths; distinguish Oracle DIRECTORY privileges from operating-system account filesystem permissions; configure READ/WRITE privileges for Data Pump, UTL_FILE, and external tables; determine the exact locations of dump, log, and parameter files; handle differences across client/server, PDB, and RAC; protect dumps/logs and build a pre-export/import verification workflow.

## 1. What Is a DIRECTORY Object?

An Oracle DIRECTORY object is a database object used to map a logical name to a directory path on a filesystem accessible by the database server.

Example:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_stage
AS '/u02/oracle/exports';
~~~

Once created, database-side tools can reference the name DPUMP_STAGE instead of repeating the operating system path in every operation.

DIRECTORY objects are commonly used by:

- Oracle Data Pump Export and Import.
- The DBMS_DATAPUMP package.
- UTL_FILE for reading/writing text or data files programmatically.
- BFILE for referencing binary files external to the database.
- External tables and certain Oracle utilities that read files on the server.

Key point: A DIRECTORY object is only a name mapping and a privilege check point in the database. It does not automatically create a directory on the OS, does not automatically grant filesystem permissions, and does not transfer files from the client machine to the database server.

### 1.1. Distinguishing three types of locations

| Component | Where is it? | Who accesses it? |
|---|---|---|
| DIRECTORY object | Metadata inside Oracle Database | Oracle resolves the name and checks privileges |
| Directory path | Filesystem accessible by the database server | Oracle server processes under Oracle's OS account |
| expdp/impdp parameter file | Machine running the client command | Read by the client-side expdp/impdp process |

Example:

- DIRECTORY object DPUMP_STAGE points to /u02/oracle/exports on the database host.
- Data Pump dump file ORDERS_01.DMP is created in that server directory.
- File PARFILE=export_orders.par is typically read from the machine running the expdp command, unless a different client path is specified.
- Running expdp from a laptop does not mean the dump file is created on the laptop.

This is a common reason operators look for dump files on the wrong machine or grant filesystem permissions to the wrong account.

### 1.2. A DIRECTORY object is not a tablespace or datafile

A DIRECTORY object does not store database data in tablespace structures. It is not:

- A tablespace.
- A datafile or tempfile.
- A redo log or archived redo log.
- A schema containing tables.
- A local directory on a client application host.
- An independently restorable backup.

Dump files can contain exported metadata and data, but the dump location is managed through the DIRECTORY object and its underlying filesystem/storage.

## 2. Two Privilege Layers Must Both Be Correct

For Oracle to read or write files via a DIRECTORY object, two independent privilege layers must usually be satisfied:

1. **Oracle directory privilege:** the user executing the operation is granted READ or WRITE on the DIRECTORY object.
2. **Operating-system permission:** the OS account running Oracle Database has permissions to traverse the directories and read/write files at the target path.

Example granting privileges in Oracle:

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_export;
~~~

On Linux, the directory must also allow Oracle's OS account to access it. For example, the database installation account is often oracle, though you must verify the actual service account:

~~~bash
ls -ld /u02/oracle/exports
namei -l /u02/oracle/exports
df -h /u02/oracle/exports
~~~

If the database service runs under a different account, permissions must match that account. On Windows, inspect NTFS permissions for the account running the Oracle Database service.

### 2.1. Having Oracle privilege but lacking OS permission

Suppose APP_EXPORT has READ and WRITE on DPUMP_STAGE, but Oracle's OS account lacks write permission to /u02/oracle/exports.

When Data Pump export creates a dump file or log, the operation can fail with a filesystem error. Grants inside Oracle cannot bypass operating system permissions.

Common causes:

- The directory does not exist yet.
- A parent directory lacks execute/traverse permission.
- Incorrect owner/group/mode.
- Filesystem mounted read-only.
- Disconnected NFS mount or incorrect credential mapping.
- Out of disk space or quota.
- SELinux/AppArmor policy blocking access.
- Path differs across hosts in a cluster.

### 2.2. Having OS permission but lacking Oracle privilege

Conversely, Oracle's OS account has filesystem write permission, but APP_EXPORT lacks WRITE on the DIRECTORY object. Oracle still denies the operation according to the database privilege model.

Do not resolve errors by granting broader OS permissions to all users or granting READ/WRITE on the directory to PUBLIC. Identify the executing principal and grant the exact object privilege.

### 2.3. What do READ and WRITE mean?

| Privilege | Primary capability |
|---|---|
| READ | Read files in the directory through supported Oracle features |
| WRITE | Create/write files in the directory through supported Oracle features |

Examples with Data Pump:

- Export dump file: requires WRITE.
- Export log file: requires WRITE.
- Import dump file: requires READ.
- Import log file: requires WRITE.
- SQLFILE output: requires WRITE.
- UTL_FILE reading files: requires READ.
- UTL_FILE creating/writing files: requires WRITE.
- BFILE reading binary files: requires READ.

For a dedicated Data Pump operational account, both READ and WRITE can be granted on the target directory. If an account only performs imports or exports, grant the minimum required for its actual function.

## 3. Creating and Managing DIRECTORY Objects

### 3.1. Creating a directory

Example:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_stage
AS '/u02/oracle/exports';
~~~

CREATE DIRECTORY requires an appropriate system privilege, typically CREATE ANY DIRECTORY. This privilege is powerful because it allows creating or changing directory mappings in the database; only DBAs or authorized principals should hold it.

The command above does not create /u02/oracle/exports on the OS. The folder must be prepared beforehand with appropriate permissions.

### 3.2. Granting privileges to users

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_export;
~~~

If separating import and export users:

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_import;
~~~

In environments requiring least privilege, you can create a separate directory for the import flow needing only READ on dumps and WRITE for logs; the export account needs WRITE for dumps/logs. Test privilege behavior with the actual executing account rather than relying on unclear roles.

### 3.3. Revoking privileges

~~~sql
REVOKE READ, WRITE
ON DIRECTORY dpump_stage
FROM app_export;
~~~

Revoking privileges does not delete existing files on the filesystem. It only changes that principal's ability to use the DIRECTORY object.

### 3.4. Dropping a DIRECTORY object

~~~sql
DROP DIRECTORY dpump_stage;
~~~

DROP DIRECTORY removes the object mapping in the database; it does not delete the OS folder or the files inside it.

Before dropping, locate any jobs, packages, external tables, BFILE references, and Data Pump scripts using the directory. Dropping it can cause dependent workflows to fail.

### 3.5. Changing a directory's path

Example:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_stage
AS '/u03/new_exports';
~~~

This change redirects all consumers of DPUMP_STAGE to the new path. Old dump files remain at the old path; Oracle does not move them automatically.

Before changing:

1. List dependent consumers and jobs.
2. Verify the new path exists on the database host.
3. Verify owner/group/permissions, mounts, and free space.
4. Check RAC node visibility if applicable.
5. Plan file movement if needed.
6. Execute the change and verify with a test export/import.
7. Record the old mapping for rollback if old data has not been deleted.

Do not use CREATE OR REPLACE DIRECTORY to point to an unprepared path and then troubleshoot why jobs fail to run.

## 4. Inspecting DIRECTORY Metadata and Privileges

### 4.1. Viewing directory objects

From an account with appropriate privileges:

~~~sql
SELECT owner,
       directory_name,
       directory_path
FROM dba_directories
ORDER BY directory_name;
~~~

From the object scope visible to a user:

~~~sql
SELECT directory_name,
       directory_path
FROM all_directories
ORDER BY directory_name;
~~~

USER_DIRECTORIES or equivalent views may be available depending on release and privileges. Do not assume directory objects appear only in the schema that ran the command; directory metadata follows different rules than regular tables/views.

### 4.2. Viewing privileges on a directory

DBAs can check object grants:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM dba_tab_privs
WHERE table_name = 'DPUMP_STAGE'
ORDER BY grantee, privilege;
~~~

Directory privileges are represented in object privilege metadata according to release rules. Cross-check object name, grantee, privilege, and grantable; do not just check which roles a user holds.

### 4.3. Identifying the container in CDB/PDB

In multitenant environments, know which container the directory object is created and used in:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id,
       sys_context('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

In the CDB root, a DBA can inspect:

~~~sql
SELECT con_id,
       owner,
       directory_name,
       directory_path
FROM cdb_directories
ORDER BY con_id, directory_name;
~~~

Match CON_ID to the PDB needing export/import. Do not create a directory in root and assume every PDB has the same object mapping and grants.

Directory objects can be managed at container scope depending on configuration/release. Execute DDL and grants in the exact target container; verify metadata and privileges directly inside the PDB to which the Data Pump job will connect.

## 5. Data Pump: Dump Files and Log Files Reside on the Server

Data Pump Export and Import are typically run using the utilities:

- expdp: Data Pump Export.
- impdp: Data Pump Import.

Data Pump processing is performed by database server processes. Dump and log files are written/read on the database server filesystem according to the DIRECTORY object.

### 5.1. Simple export

Example exporting the SALES schema:

~~~bash
expdp app_export@APP_PDB \
  DIRECTORY=DPUMP_STAGE \
  DUMPFILE=sales_export.dmp \
  LOGFILE=sales_export.log \
  SCHEMAS=SALES
~~~

Assuming DPUMP_STAGE points to /u02/oracle/exports, the dump and log will be created in that server directory, provided both Oracle privileges and OS permissions allow it.

The command above is a structural example. Connection details, password, service, and schema must be replaced with environment values; never put plaintext passwords in command history or shared scripts.

### 5.2. Export with multiple dump files

For large datasets or PARALLEL, dumps can be split into multiple files:

~~~bash
expdp app_export@APP_PDB \
  DIRECTORY=DPUMP_STAGE \
  DUMPFILE=sales_%U.dmp \
  LOGFILE=sales_export.log \
  SCHEMAS=SALES \
  PARALLEL=4 \
  FILESIZE=10G \
  LOGTIME=ALL \
  METRICS=YES
~~~

%U is a substitution variable allowing Data Pump to generate multi-part filenames. FILESIZE limits the size of each dump file per configuration. PARALLEL controls job parallelism; consider CPU, I/O, storage, and file counts.

Increasing PARALLEL does not always speed up export. If storage or network is already saturated, more workers can slow down other workloads.

### 5.3. Importing a schema

~~~bash
impdp app_import@APP_PDB \
  DIRECTORY=DPUMP_STAGE \
  DUMPFILE=sales_%U.dmp \
  LOGFILE=sales_import.log \
  SCHEMAS=SALES \
  REMAP_SCHEMA=SALES:SALES_TEST
~~~

Import reads dump files from the server-side directory and writes the log on the server. Target schemas, tablespaces, quotas, object ownership, grants, and dependencies must be prepared as required.

REMAP_SCHEMA only changes schema mapping during import; it does not automatically create users, quotas, tablespaces, or guarantee that all objects will be created successfully.

### 5.4. The Directory parameter

The DIRECTORY parameter specifies the default directory object for a Data Pump job's files. DUMPFILE, LOGFILE, and related output files are resolved relative to that specified directory unless another supported directory specification syntax is used.

Example:

~~~text
DIRECTORY=DPUMP_STAGE
DUMPFILE=orders_%U.dmp
LOGFILE=orders_export.log
~~~

The directory object name must exist in the container to which the job connects. The user running the job must hold the required privileges on that directory.

### 5.5. Log files as operational evidence

LOGFILE records export/import progress, processed objects, warnings, and errors. Always generate a log for important jobs.

You can add:

- LOGTIME=ALL to record timestamps on each message.
- METRICS=YES to log object/operation metrics on supported versions.
- A meaningful job name for easy ATTACH/monitoring.
- Capture expdp/impdp exit codes and store logs in a run management location.

NOLOGFILE=YES removes a critical source of operational evidence. Use it only with justification and when an alternative logging/monitoring system is in place.

## 6. Distinguishing Server-Side Dump/Log Files from Client-Side PARFILEs

This distinction is critical when running Data Pump from an administrative workstation.

Example:

~~~bash
expdp app_export@APP_PDB parfile=./export_sales.par
~~~

The export_sales.par file is read by the expdp program on the machine running the command. Inside the file, you might have:

~~~text
DIRECTORY=DPUMP_STAGE
DUMPFILE=sales_%U.dmp
LOGFILE=sales_export.log
SCHEMAS=SALES
PARALLEL=4
LOGTIME=ALL
METRICS=YES
~~~

Meanwhile:

- PARFILE: client-side configuration file.
- DUMPFILE: database server-side dump file.
- LOGFILE: database server-side log file.
- SQLFILE: database server-side DDL output file.
- DIRECTORY: directory object name resolved by the database server.

Do not put a client path into DIRECTORY if that path does not exist on the database server. Likewise, do not look for dump files in the client directory simply because expdp was invoked from there.

### 6.1. Credentials and the command line

Avoid passing passwords directly after a slash on the command line if shell history, process listings, or automation logs could capture them. Use an organization-approved authentication mechanism, Oracle wallet/secure external password store, or appropriate interactive prompting.

Parameter files can also contain sensitive information. Protect read permissions, retention, and storage locations.

## 7. What Privileges Does Data Pump Need?

Required privileges depend on the export/import mode and the objects being processed.

### 7.1. Directory privileges

Example granting privileges to an export account:

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_export;
~~~

And an import account:

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_import;
~~~

READ/WRITE on a DIRECTORY does not grant SELECT on table SALES.ORDERS, and SELECT on the table does not automatically grant permission to write dump files.

### 7.2. Schema mode and data privileges

A user can export their own schema under appropriate Data Pump conditions. Exporting/importing the full database or other schemas may require corresponding privileged roles.

Common Data Pump roles:

- DATAPUMP_EXP_FULL_DATABASE: additional privileges for exporting outside the user's own schema or full database within the role's scope.
- DATAPUMP_IMP_FULL_DATABASE: additional privileges for importing the full database or objects/schemas outside the user's normal scope.

Do not grant these roles just to resolve a directory error. Identify the export/import mode, object owners, and actually required privileges.

### 7.3. Separating privileges by responsibility

A clean model might be:

| Principal | Required privileges |
|---|---|
| DBA managing directories | CREATE ANY DIRECTORY per assignment |
| Export account | READ/WRITE on export directory and privileges to export authorized data |
| Import account | READ/WRITE on import directory and privileges to import into target |
| Application runtime | No Data Pump privileges unless it performs export/import itself |
| Oracle OS account | Filesystem permissions on the server path |

Do not grant CREATE ANY DIRECTORY to application runtime accounts. This privilege allows creating or altering mappings to arbitrary paths and expands the database server's file access reach.

## 8. File Locations on the Server Filesystem

### 8.1. Preparing the directory

On Linux/Unix, the DBA or system administrator creates the path and assigns the proper owner/group/mode before creating the DIRECTORY object.

Illustrative example:

~~~bash
mkdir -p /u02/oracle/exports
chown oracle:oinstall /u02/oracle/exports
chmod 750 /u02/oracle/exports
ls -ld /u02/oracle/exports
df -h /u02/oracle/exports
~~~

The commands above modify the filesystem; run them only under change procedures and substitute the actual environment account/group. Do not assume the owner is always oracle:oinstall.

For Oracle to access it, every parent directory along the path needs appropriate traverse permissions. Also check mount options, quotas, ACLs, and security policies.

### 8.2. Checking files and capacity

~~~bash
ls -lh /u02/oracle/exports
df -h /u02/oracle/exports
du -sh /u02/oracle/exports
~~~

For large files, monitor space while the job runs. Reserve capacity for dumps, logs, temporary files, concurrent jobs, and import outputs.

### 8.3. NFS and shared filesystems

If the path resides on NFS:

- Check the mount on the database host.
- Confirm export/mount permissions.
- Check UID/GID mapping for Oracle's OS account.
- Verify network stability.
- Check throughput and latency.
- Determine behavior if the NFS server loses connectivity.
- Confirm all RAC nodes running Data Pump see the same data.

A directory object does not mount NFS and does not make a path exist on the server. It only stores a mapping to the path.

### 8.4. Do not use arbitrary directories

Avoid placing dumps in:

- Oracle Home.
- Datafile/redo log directories.
- Diagnostic trace directories without dedicated quotas.
- The root filesystem.
- Application folders with broad write permissions.
- Temporary paths subject to automatic cleanup.
- Shared paths lacking access control.

Create a dedicated staging area with its own quotas, monitoring, retention, and access controls.

## 9. Oracle RAC: Paths Must Be Visible from Worker Nodes

In RAC, the Data Pump master process and worker processes can be distributed across instances depending on configuration. If a directory path exists only on one node's local filesystem, workers running on another node may fail to find files or write to a different path.

Recommendations:

- Use a supported shared filesystem mounted consistently across all nodes participating in the job.
- Confirm the same directory object path is visible from every node.
- Check OS permissions on each node.
- If using a local filesystem, consider confining the job to an appropriate instance using Data Pump configuration such as CLUSTER=NO per release and topology.
- Measure the impact of PARALLEL and storage throughput.

Example:

~~~text
DIRECTORY=DPUMP_STAGE
CLUSTER=NO
PARALLEL=2
DUMPFILE=orders_%U.dmp
LOGFILE=orders_export.log
~~~

CLUSTER=NO prevents a Data Pump job from distributing workers across the cluster according to supported release behavior. It does not automatically guarantee all paths and services are right; check the instance/service where the job launches.

Do not use identically named local paths across nodes if their actual contents differ. A multi-piece dump file must be assembled completely for import.

## 10. CDB/PDB and DIRECTORY Objects

In multitenant architectures, connect to the exact PDB before running Data Pump for schemas/objects in that PDB.

Example check:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id,
       sys_context('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

View directory metadata from the CDB root when authorized:

~~~sql
SELECT con_id,
       owner,
       directory_name,
       directory_path
FROM cdb_directories
ORDER BY con_id, directory_name;
~~~

Directory objects can have different container scopes. Confirm the object and grants exist in the exact container to which the user connects.

A Data Pump job connecting to a PDB service sees directory objects defined in the appropriate scope per multitenant rules. Do not infer from a query run in root that a PDB already has usage privileges.

## 11. Data Pump Import/Export with Multiple Directories

Some jobs need to separate where dumps are read from and where logs/outputs are written. Data Pump supports specifying directory objects via parameter syntax supported by the release; consult the Data Pump Utilities Guide for parameter file syntax.

The simplest pattern is using one staging directory with READ/WRITE and placing dumps/logs there. When separation is needed:

- Input dumps reside in an area where the import account only has READ.
- Log outputs reside in an area where operators have READ/WRITE.
- SQLFILE output resides in a separate DDL inspection area.
- Backup archives are moved to different storage per policy.

Keep the design simple if separation is unnecessary. Every additional directory introduces extra grants, paths, mounts, capacity, and dependencies to manage.

### 11.1. SQLFILE

IMPDP can generate an SQL file containing the DDL the job intends to execute instead of executing that DDL:

~~~bash
impdp app_import@APP_PDB \
  DIRECTORY=DPUMP_STAGE \
  DUMPFILE=sales_export.dmp \
  SQLFILE=sales_preview.sql \
  SCHEMAS=SALES
~~~

SQLFILE is written on the database server according to the DIRECTORY object. It is useful for reviewing DDL before import, though it does not replace actual import testing.

Protect SQLFILE as sensitive metadata: it can contain schema names, objects, structures, and deployment details.

### 11.2. Network mode

Data Pump can use NETWORK_LINK to import directly from a source database over a database link without requiring intermediate dump files for the data stream.

Conceptual example:

~~~text
impdp app_import@TARGET_PDB
  NETWORK_LINK=SOURCE_LINK
  SCHEMAS=SALES
  LOGFILE=network_import.log
  DIRECTORY=DPUMP_STAGE
~~~

NETWORK_LINK changes the data source, yet the log file still requires a server-side location and appropriate DIRECTORY privileges. Remote privileges, network, version compatibility, and capacity are needed on both databases.

## 12. UTL_FILE and BFILE Also Use DIRECTORY Objects

DIRECTORY objects do not serve Data Pump alone.

### 12.1. UTL_FILE

UTL_FILE allows PL/SQL to read/write text files or files in modes supported by the package.

Conceptual example:

~~~sql
DECLARE
    l_file UTL_FILE.FILE_TYPE;
BEGIN
    l_file := UTL_FILE.FOPEN(
        location     => 'APP_LOG_DIR',
        filename     => 'job_status.txt',
        open_mode    => 'w',
        max_linesize => 32767
    );

    UTL_FILE.PUT_LINE(l_file, 'Job completed');
    UTL_FILE.FCLOSE(l_file);
END;
/
~~~

The executing user/schema needs appropriate DIRECTORY privileges and Oracle's OS account must be able to write the file. Close the file in both success and exception paths; production code should include an exception handler calling FCLOSE if the handle is open.

Do not concatenate arbitrary user input into filenames. Whitelist filenames or generate names under controlled rules to prevent unintended file overwrites.

### 12.2. BFILE

BFILE is a locator to an external binary file outside the database, accessed in read-only mode via a DIRECTORY object.

Example creating a locator:

~~~sql
SELECT BFILENAME('APP_MEDIA_DIR', 'image_001.bin')
FROM dual;
~~~

BFILE does not store file contents inside the database and does not allow Oracle to write contents back to the file via the BFILE mechanism. The consumer needs READ privilege on the directory and Oracle's OS account must be able to read the file.

### 12.3. External tables

External tables allow SQL to read data from external files outside the database using an appropriate access driver, such as ORACLE_LOADER or ORACLE_DATAPUMP.

Simple example:

~~~sql
CREATE TABLE ext_orders (
    order_id      NUMBER,
    customer_id   NUMBER,
    status        VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY ext_data_dir
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        FIELDS TERMINATED BY ','
        MISSING FIELD VALUES ARE NULL
    )
    LOCATION ('orders.csv')
)
REJECT LIMIT UNLIMITED;
~~~

External tables do not store data like standard heap tables. Queries read files at the server location; directory privileges and OS access still must be correct.

For untrusted files, check format, encoding, delimiters, line endings, record length, and reject files. Do not set REJECT LIMIT UNLIMITED unconditionally if data errors must be caught early.

## 13. Protecting Dump Files and Logs

Dump files can contain business data, personal information, schema structures, metadata, and sensitive content. Broad DIRECTORY privileges can increase data exposure risk.

### 13.1. Filesystem permissions

Use dedicated owner/group settings and restrict read permissions to required operators and service accounts. Avoid chmod 777 or directories writable by all OS users.

Check:

- Directory owner/group/mode.
- ACLs.
- NFS export permissions.
- SELinux/AppArmor.
- Storage encryption.
- Quotas and retention.
- File deletion permissions.
- Access auditing.

### 13.2. Encryption

If dumps contain sensitive data, evaluate Data Pump encryption per supported features and licensing, or encrypt storage/files per policy.

When using encryption, protect passwords/keystores separately from dump files. An encrypted backup whose key is lost may be unrecoverable.

Do not record encryption passwords in source control, shell history, logs, or tickets. Test restoring from an encrypted copy before broad adoption.

### 13.3. Retention and cleanup

Define a clear lifecycle:

- Job owner.
- Creation date and export scope.
- Backup/dump purpose.
- Retention period.
- Authorized readers.
- Offsite/immutable copy if required.
- Deletion criteria.
- Cleanup logs and evidence.

Do not delete dump files immediately after import if they are the only copy satisfying a recovery/compliance requirement. Do not treat Data Pump dumps as a replacement for full-database RMAN backups.

### 13.4. Logs also require protection

Logs can contain object names, SQL/error text, paths, and operational details. Restrict access permissions and retention according to policy.

Do not disable logging just to avoid a file-write error. Fix the permissions/path/capacity or design proper logging.

## 14. Common Errors

| Symptom | Possible cause | What to check |
|---|---|---|
| ORA-39002 invalid operation | Invalid job parameter or operation | Read the full Data Pump error stack |
| ORA-39070 unable to open log file | Missing WRITE, wrong path, or unwritable filesystem | DIRECTORY grant, OS permissions, disk |
| ORA-39087 directory name invalid | DIRECTORY object does not exist or wrong name | DBA_DIRECTORIES, container, and spelling |
| ORA-29283 invalid file operation | UTL_FILE/file access failure | Directory grant, OS permissions, filename, path |
| ORA-29289 directory access denied | Missing appropriate DIRECTORY privilege | Check READ/WRITE grants for the principal |
| ORA-31640 unable to open dump file | Dump missing/unreadable | Server path, READ grant, mount, filename |
| ORA-31641 unable to create dump file | Cannot create dump output | WRITE grant, OS permissions, disk/quota |
| OS permission denied | Oracle OS account lacks permissions | Owner/group/mode/ACL/SELinux |
| No space left on device | Filesystem or quota exhausted | df, quota, storage alerts |
| File not found even though client sees it | File exists only on client, not on server | Move file to the granted server path |
| RAC worker cannot see file | Local path exists on only one node | Shared mount or CLUSTER=NO |
| Job runs in wrong PDB | Connected to wrong service/container | CON_NAME, CON_ID, and service |
| Dump file exists but import fails | Missing dump part, version/privilege/object dependency | Export/import logs, file set, and metadata |

Always read the full error stack. ORA-390xx is often an outer wrapper error; the root cause may lie in ORA-01031, ORA-29283, or underlying OS messages further down.

## 15. Runbook: Preparing a Directory for Data Pump

### Step 1 — Identify the environment

Record the database, DB_UNIQUE_NAME, PDB, service, host/instance, Oracle release, and account running Data Pump.

~~~sql
SELECT name, db_unique_name, database_role, open_mode
FROM v$database;

SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

### Step 2 — Determine the server path

Select a server-side path based on capacity, backup/retention, and security. Confirm the path exists on the database host and on all relevant nodes if RAC.

### Step 3 — Check OS permissions

Use an appropriate administrative OS account to inspect directory owner, group, mode, mount, ACLs, free space, and read/write capability for the Oracle service account.

### Step 4 — Create the DIRECTORY object

~~~sql
CREATE OR REPLACE DIRECTORY dpump_stage
AS '/u02/oracle/exports';
~~~

Execute using a principal granted CREATE ANY DIRECTORY per change policy.

### Step 5 — Grant least privilege

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_export;
~~~

Grant only to authorized users/roles and verify using the exact account running Data Pump.

### Step 6 — Verify metadata

~~~sql
SELECT directory_name, directory_path
FROM all_directories
WHERE directory_name = 'DPUMP_STAGE';
~~~

If metadata is correct yet the job still fails, continue checking OS permissions, path mounts, and the container.

### Step 7 — Run a small test

Export a small test schema/table, generating a log and dump. Confirm files appear at the server path, have reasonable sizes, and the log ends with success.

### Step 8 — Test import

Import into a test schema/PDB. Verify objects, row counts, grants, and business results. Do not use a production target for an initial test.

### Step 9 — Record evidence

Document directory DDL, grants, path, OS owner/mode, test logs, file sizes, timestamp, and operator. Do not record passwords or keys.

## 16. Runbook: Data Pump Job Failed Due to Directory/File Issues

1. Save all expdp/impdp output and logs if available.
2. Identify the job name, owner, service/PDB, and directory object.
3. Query ALL_DIRECTORIES/DBA_DIRECTORIES to confirm the mapping.
4. Query directory grants to confirm READ/WRITE.
5. Verify Oracle's OS account can traverse/read/write the path.
6. Confirm the file exists on the database server with the exact filename and case matching the filesystem.
7. Check mounts, ACLs, SELinux, quotas, and free space.
8. With RAC, check the path on every node where workers can run.
9. With import, confirm every dump file part is present and readable.
10. Fix the root cause and rerun via a new job or ATTACH per runbook.
11. Inspect logs, row counts, object status, and data after the job.
12. Record the root cause, downtime, and preventive actions.

Do not delete the job master table, dump files, or logs before confirming job state and resume/attach capability.

## 17. Version and Deployment Considerations

- Data Pump parameters and options can vary across Oracle releases.
- Directory objects in CDB/PDB must be created/granted in the correct container.
- RAC requires paths used by workers to be accessible on the participating nodes.
- ASM and filesystems are not interchangeable in every workflow; confirm which storage types are supported by the feature.
- NFS, cloud filesystems, and object storage may require dedicated integration/tooling.
- Data Pump encryption and certain features require specific options/licenses.
- PDB clone/plug/unplug or migration may require adjusting directory mappings for the target host.
- Oracle Database service accounts and permission models differ between Linux/Unix and Windows.

Always consult the SQL Language Reference, Data Pump Utilities Guide, and platform documentation for your exact release; never copy a command verbatim from another environment without checking.

## 18. Practice Labs

Perform these in a lab with dedicated directories and non-sensitive data.

### Lab 1 — Create a directory object

Create a server path, create DPUMP_STAGE, and query ALL_DIRECTORIES to confirm the mapping.

### Lab 2 — Missing Oracle privilege

Create a test user without READ/WRITE, attempt Data Pump or UTL_FILE, and record the error. Grant the proper privilege and retry.

### Lab 3 — Missing OS permission

In the lab, modify permissions so the Oracle service account cannot write. Observe the error and restore proper permissions. Do not test on production paths.

### Lab 4 — Export and log

Export a test schema using DUMPFILE and LOGFILE. Confirm the file locations on the database server.

### Lab 5 — Parameter file

Run expdp using a PARFILE located on the client. Compare the PARFILE path with the server-side directory used for dumps/logs.

### Lab 6 — Multi-file export

Use %U, PARALLEL, and FILESIZE. Check the number of dump parts and import all files completely.

### Lab 7 — Import into another schema

Use REMAP_SCHEMA in a lab PDB. Verify user, quotas, tablespaces, and grants.

### Lab 8 — PDB scope

Create a directory object in a test PDB, query CDB_DIRECTORIES from root, and identify CON_ID. Connect to the wrong PDB and observe the difference.

### Lab 9 — RAC visibility

If a RAC lab is available, test a shared filesystem versus a local path. Compare cluster-wide jobs with CLUSTER=NO per release support.

### Lab 10 — UTL_FILE

Create a text file via UTL_FILE, read it back in the lab, and handle exceptions/file closing.

### Lab 11 — External table

Create an external table reading a CSV, test READ privileges, OS permissions, and reject behavior.

### Lab 12 — SQLFILE

Use IMPDP SQLFILE to generate a DDL preview, read the log, and review the output before an actual import.

## 19. Pre-Export/Import Checklist

- [ ] Confirm the exact database, DB_UNIQUE_NAME, service, and PDB.
- [ ] Confirm the DIRECTORY object exists in the correct container.
- [ ] Confirm the directory path is a database server-side path.
- [ ] Confirm Oracle's OS account has proper traverse/read/write permissions.
- [ ] Check mounts, ACLs, filesystem quotas, and free space.
- [ ] Grant least-privilege READ/WRITE DIRECTORY privileges to the job account.
- [ ] Confirm required schema or full database export/import privileges.
- [ ] Identify DUMPFILE and LOGFILE locations.
- [ ] Confirm PARFILE resides on the client machine.
- [ ] With RAC, confirm the path is shared or cluster scope is restricted by design.
- [ ] With PDBs, confirm CON_NAME/CON_ID.
- [ ] Use an appropriate DUMPFILE pattern when using PARALLEL or multiple parts.
- [ ] Include LOGFILE and save exit status/evidence.
- [ ] Check dump encryption and credentials/keys if data is sensitive.
- [ ] Check retention and read/delete permissions on dump files.
- [ ] Test export/import on a small dataset before running in production.
- [ ] After import, verify objects, row counts, grants, and business correctness.
- [ ] Do not delete files or drop directory objects while dependent consumers/jobs remain.

## 20. Key Takeaways

- A DIRECTORY object maps a logical name in the database to a folder on the server filesystem.
- CREATE DIRECTORY does not automatically create OS directories or grant filesystem permissions.
- Data Pump dump/log files reside on the database server; PARFILE is read by the expdp/impdp client.
- Oracle READ/WRITE privileges and OS account permissions are two independent conditions; both must be valid.
- Export requires write permission for dumps/logs; import requires reading dumps and writing logs/output.
- Directory privileges do not grant SELECT on tables; data privileges and file privileges are separate layers.
- CREATE ANY DIRECTORY is a powerful administrative privilege; do not grant it to application runtime accounts.
- DROP DIRECTORY only removes the mapping in the database, not the OS folder or files.
- Changing a directory object's path affects all consumers and does not move existing files automatically.
- In RAC, workers must see the same path; use a shared filesystem or appropriate job configuration such as CLUSTER=NO when needed.
- In CDB/PDB, create and grant directories in the exact container and verify CON_ID.
- UTL_FILE, BFILE, and external tables also rely on DIRECTORY objects and OS permissions.
- Dump files can contain sensitive data; protect filesystems, encryption keys, logs, retention, and delete permissions.
- Data Pump export/import requires both directory privileges and appropriate data/schema privileges.
- Do not confuse client paths with server paths; do not look for dump files on the machine running expdp if DIRECTORY points to a server path.
- Always keep logs, check exit status, and verify data after import.

### Recommended Oracle documentation

- [Oracle Database SQL Language Reference — CREATE DIRECTORY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-DIRECTORY.html) — Creating, replacing, and managing DIRECTORY objects.
- [Oracle Database Utilities — Data Pump Export and Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/) — DIRECTORY, DUMPFILE, LOGFILE, PARFILE, parallelism, export/import modes, and security.
- [Oracle Database PL/SQL Packages and Types Reference — UTL_FILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_FILE.html) — File access via DIRECTORY objects.
- [Oracle Database SecureFiles and Large Objects Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/) — BFILE and external file locators.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Multitenant administration and directory metadata.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — DBA_DIRECTORIES, ALL_DIRECTORIES, and CDB_DIRECTORIES.

Directory object behavior, Data Pump parameters, RAC worker placement, PDB scope and encryption options vary by Oracle release and platform. Confirm the exact release documentation and OS service identity; test file access, export, import and recovery in a non-production environment before production use.
