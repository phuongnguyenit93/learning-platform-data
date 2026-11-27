# STARTUP NOMOUNT, MOUNT, OPEN and When to Use Each State

Oracle Database starts up in stages. The three most common states are **NOMOUNT**, **MOUNT**, and **OPEN**. Each state indicates how far the instance has been initialized and how far the database has been opened:

- **NOMOUNT**: Oracle has initialized the instance from the parameter file, allocated the SGA, and started the required background processes. The control file is not yet open.
- **MOUNT**: The instance is running and the database has been attached to the instance by opening the control file. Datafiles and online redo logs are not yet open for normal database operations.
- **OPEN**: Oracle opens the required datafiles and online redo logs, checks consistency, and performs any necessary recovery. The database is ready for connections and operations appropriate to its open mode.

You can visualize the startup sequence as:

~~~text
SHUTDOWN
   |
   | STARTUP NOMOUNT
   v
NOMOUNT
   |
   | ALTER DATABASE MOUNT
   v
MOUNT
   |
   | ALTER DATABASE OPEN
   v
OPEN
~~~

Not every task requires the database to be in the OPEN state. Creating a database and certain control file operations require NOMOUNT; recovery or file configuration changes may require MOUNT; normal application activity requires OPEN. Choosing the wrong state can prevent a command from executing or increase operational risk.

This lesson explains the difference between an instance and a database, the conditions for each state, state transition commands, how to verify the current state, open modes, recovery, CDB/PDB, RAC, and common startup errors.

## 1. Instance and Database Are Two Different Concepts

To understand NOMOUNT, MOUNT, and OPEN, you first need to separate two components:

- **Instance** is the memory structures and running background processes that manage the database.
- **Database** is the set of physical files containing data and metadata, such as datafiles, control files, and online redo logs.

An instance can be running while the database is not yet mounted or opened.

### 1.1. What Does an Instance Consist Of?

When starting an instance, Oracle reads the initialization parameter file and creates the runtime environment, including:

- System Global Area (SGA).
- Background processes, such as DBWn, LGWR, CKPT, SMON, PMON, and other processes depending on configuration.
- Structures that manage memory, sessions, buffers, and transactions.
- Configuration information needed to proceed with attaching to the database.

An instance can exist in the NOMOUNT state without opening a control file.

### 1.2. What Files Make Up a Database?

Important files include:

| File | Role |
| --- | --- |
| Control file | Records database structure metadata, checkpoints, the list of datafiles/redo logs, and recovery information |
| Datafile | Contains database blocks, segments, tables, indexes, and other data |
| Online redo log | Records redo required for recovery and ensures consistency |
| Archived redo log | Saved copy of a filled redo log, used for media recovery and Data Guard |
| Parameter file | Contains parameters to initialize the instance; SPFILE/PFILE are not datafiles |

The control file is not where table contents are stored. Datafiles do not replace the control file. Online redo logs are also not a full copy of the database; they record the changes required for recovery.

### 1.3. A Running Instance Does Not Mean the Database Is Open

Three scenarios:

- NOMOUNT: the instance is running, the database is not mounted.
- MOUNT: the instance is running, the control file is open, the database is not open.
- OPEN: the database has been opened in an open mode.

Therefore, saying "Oracle processes are running" is not enough to conclude that applications can access data. You must check both the instance status and the database open mode.

## 2. The NOMOUNT State

NOMOUNT is the stage where the instance has been initialized but the database has not been mounted.

### 2.1. What Does Oracle Do in NOMOUNT?

When executing STARTUP NOMOUNT, Oracle typically performs the following tasks:

1. Locates and reads the SPFILE or PFILE.
2. Sets the initialization parameters.
3. Allocates the SGA.
4. Starts background processes.
5. Creates the instance and puts the instance into the STARTED state.
6. Does not open the control file yet.

At this point, Oracle has not read the control file to attach the database to the instance.

### 2.2. Conditions to Enter NOMOUNT

Requirements:
- Valid Oracle software and runtime environment.
- A connection with privileges to start the instance, typically SYSDBA or the corresponding administrative privilege.
- A valid and readable SPFILE/PFILE.
- Sufficiently valid initialization parameters.
- Required operating system resources such as memory, processes, and directory access permissions.

The control file does not need to be opened yet during the NOMOUNT stage. However, the CONTROL_FILES parameter is usually already declared in the parameter file so Oracle knows where the control files are located when transitioning to MOUNT.

### 2.3. Starting in NOMOUNT

If Oracle finds the default SPFILE:

~~~sql
STARTUP NOMOUNT;
~~~

Specifying a particular PFILE:

~~~sql
STARTUP NOMOUNT
PFILE='/u01/app/oracle/product/dbhome_1/dbs/initORCL.ora';
~~~

The path is only an example. On Windows or other environments, paths and filenames will differ.

If you need to check which SPFILE is in use after the instance starts:

~~~sql
SHOW PARAMETER spfile;
SHOW PARAMETER control_files;
~~~

If SPFILE is empty, the instance may have been started from a PFILE or another configuration mechanism. Verify the parameter source in the actual environment.

### 2.4. Tasks That Typically Require NOMOUNT

NOMOUNT is suitable for tasks that require an instance but do not yet require a control file:

- Creating a new database with CREATE DATABASE.
- Creating or recreating a control file using an appropriate administrative procedure.
- Certain restore/recovery preparation steps when the database cannot be mounted yet.
- Checking instance parameters and resources.
- Initializing the instance before transitioning to MOUNT.

For example, CREATE DATABASE is executed while the instance is in NOMOUNT:

~~~sql
CREATE DATABASE demo
    USER SYS IDENTIFIED BY "ExampleSysPassword"
    USER SYSTEM IDENTIFIED BY "ExampleSystemPassword"
    LOGFILE GROUP 1 ('/u02/oradata/demo/redo01.log') SIZE 100M
    DATAFILE '/u02/oradata/demo/system01.dbf' SIZE 700M
    SYSAUX DATAFILE '/u02/oradata/demo/sysaux01.dbf' SIZE 500M
    DEFAULT TEMPORARY TABLESPACE temp
        TEMPFILE '/u02/oradata/demo/temp01.dbf' SIZE 100M
    UNDO TABLESPACE undotbs1
        DATAFILE '/u02/oradata/demo/undo01.dbf' SIZE 200M;
~~~

This is a simplified illustrative example. Real database creation requires planning character sets, block sizes, redo groups, undo, temp, datafile layout, password file, archive mode, and security options. Do not run database creation commands on a system that already holds data.

### 2.5. What Cannot Be Done in NOMOUNT

In NOMOUNT:
- The database is not mounted.
- The control file is not open.
- You cannot query database metadata that requires the control file as if the database were mounted.
- You cannot open datafiles to access tables normally.
- You cannot serve normal SQL workloads.

For example, V$INSTANCE can show that the instance is STARTED:

~~~sql
SELECT instance_name,
       status,
       database_status
FROM v$instance;
~~~

V$DATABASE requires the database to be mounted. Querying this view while in NOMOUNT can produce an error because the database is not yet mounted.

## 3. The MOUNT State

MOUNT is the stage where the instance is running and the database control file has been opened.

### 3.1. What Does Oracle Do When Mounting?

When transitioning from NOMOUNT to MOUNT, Oracle:
1. Reads the CONTROL_FILES parameter.
2. Opens the configured control files.
3. Checks database identification and structure information in the control file.
4. Attaches the database to the instance.
5. Puts the instance into the MOUNTED state.

At this stage, Oracle knows the database structure, datafiles, and redo logs recorded in the control file. However, datafiles are not yet opened for data access in OPEN mode.

### 3.2. Conditions to MOUNT

Requirements:
- The instance has initialized successfully.
- CONTROL_FILES is configured properly.
- The required control files can be opened.
- The control file matches the database being mounted.
- Appropriate administrative privileges.

If the control file is missing, has an incorrect path, or is corrupted, the database may fail to mount. Do not manually create an empty control file as a replacement; you must restore or recreate it according to proper backups and recovery procedures.

### 3.3. Transitioning from NOMOUNT to MOUNT

When the instance is in NOMOUNT:

~~~sql
ALTER DATABASE MOUNT;
~~~

Or start directly to MOUNT from a shutdown state:

~~~sql
STARTUP MOUNT;
~~~

STARTUP MOUNT initializes the instance and then mounts the database. You do not need to run STARTUP NOMOUNT first if the instance is currently shut down.

### 3.4. Tasks That Typically Require MOUNT

MOUNT is suitable for administrative operations that require the control file without opening the database to users:

- Media recovery.
- Restoring/recovering the database with RMAN using the appropriate procedure.
- Enabling or disabling ARCHIVELOG.
- Certain datafile, tablespace, or redo log administrative operations.
- Renaming or handling file paths using supported procedures.
- Opening the database READ ONLY after mounting.
- Inspecting database metadata in the control file.

Example of enabling ARCHIVELOG:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
~~~

Only perform this when the archive destination, storage capacity, backup policy, and operational procedures are prepared. ARCHIVELOG is a configuration decision that affects storage and recovery; do not enable it arbitrarily on production without a plan.

### 3.5. What Cannot Be Done in MOUNT

In MOUNT:
- The control file is open.
- Datafiles are not open for normal database operations.
- Users cannot access tables as they can when OPEN.
- Queries requiring the full data dictionary may not succeed.
- The database is not yet ready for applications.

Some instance views remain accessible; views requiring an open database may be restricted. Always distinguish the instance state from the database open mode.

## 4. The OPEN State

OPEN is the state where the database has been opened for use according to the selected open mode.

### 4.1. What Does Oracle Do When Opening?

When transitioning from MOUNT to OPEN, Oracle performs the necessary steps to open the database, including:
1. Opening the required datafiles based on configuration and file state.
2. Opening online redo logs.
3. Checking consistency between control files, datafiles, and redo.
4. Performing instance recovery if the database needs recovery after an instance failure.
5. Placing the database into the requested open mode.

Internal details may vary by database type, role, configuration, and recovery state. If a required file is unavailable or required media recovery is incomplete, OPEN may fail.

### 4.2. Starting Directly to OPEN

Standard command:

~~~sql
STARTUP;
~~~

Equivalent to the intent of opening the database in its default mode, typically READ WRITE for a primary database:

~~~sql
STARTUP OPEN;
~~~

If the instance is currently MOUNT:

~~~sql
ALTER DATABASE OPEN;
~~~

### 4.3. Conditions to OPEN

Requirements:
- The database is MOUNTED.
- The control file is valid.
- Mandatory datafiles can be opened or are handled according to supported offline/recovery states.
- Required online redo logs are available.
- No unresolved recovery requirements remain.
- The database role and open mode permit the operation.
- Resetlogs/noresetlogs conditions match the recovery history.

If a datafile requires media recovery, Oracle may refuse to OPEN and require recovering the file or database. Do not repeat ALTER DATABASE OPEN hoping the error will disappear on its own.

### 4.4. OPEN READ WRITE

READ WRITE permits normal read/write operations according to privileges and object states:

~~~sql
ALTER DATABASE OPEN READ WRITE;
~~~

For a normal primary database, OPEN READ WRITE is the default open mode when running STARTUP without specifying READ ONLY.

### 4.5. OPEN READ ONLY

READ ONLY opens the database for read queries and disallows normal DML against database data:

~~~sql
STARTUP MOUNT;
ALTER DATABASE OPEN READ ONLY;
~~~

Or on an already MOUNTED instance:

~~~sql
ALTER DATABASE OPEN READ ONLY;
~~~

READ ONLY is useful for:
- Reporting.
- Analytical queries.
- Certain inspection or lookup activities.
- Supported standby/read-only configurations.

READ ONLY does not mean every operation in the database is impossible; certain administrative activities or temporary operations still have their own rules. Understand the limits of the open mode rather than treating it as a completely immutable sandbox.

### 4.6. OPEN RESTRICTED

Restricted session is a mode that limits who can connect, not a new NOMOUNT/MOUNT/OPEN state.

Starting restricted:

~~~sql
STARTUP RESTRICT;
~~~

Or enabling it when the database is already open:

~~~sql
ALTER SYSTEM ENABLE RESTRICTED SESSION;
~~~

Only users with the RESTRICTED SESSION privilege can connect in this mode. Used for maintenance, migrations, or tasks where normal users must be prevented from logging in.

Disabling restricted session:

~~~sql
ALTER SYSTEM DISABLE RESTRICTED SESSION;
~~~

Restricted session does not replace backups, maintenance windows, or connection pool controls. Some background jobs/services may continue running depending on configuration.

## 5. Comparing NOMOUNT, MOUNT, and OPEN

| Criterion | NOMOUNT | MOUNT | OPEN |
| --- | --- | --- | --- |
| Instance running | Yes | Yes | Yes |
| SGA/background processes | Initialized | Running | Running |
| Control file | Not open | Open | Open |
| Datafiles | Not open for database | Not open normally | Opened per database state |
| Online redo logs | Not open for database activity | Not open normally | Opened per database state |
| Normal table data access | No | No | Yes, per open mode/privileges |
| CREATE DATABASE | Can be executed | Not the appropriate stage | No |
| Media recovery | Some preparation steps | Many recovery operations require MOUNT | Some online recovery types may require OPEN |
| ARCHIVELOG mode change | No | Usually requires MOUNT | Not directly while OPEN |
| Normal application activity | No | No | Yes if READ WRITE and services are ready |

### 5.1. Remembering with Three Questions

- **NOMOUNT**: Has the instance been created yet?
- **MOUNT**: Has the control file been opened and the database attached?
- **OPEN**: Have datafiles/redo been opened so the database can serve operations?

This is a concise mnemonic when reading the alert log or troubleshooting startup issues.

## 6. State Transition Commands

### 6.1. From SHUTDOWN to NOMOUNT

~~~sql
STARTUP NOMOUNT;
~~~

Oracle reads the parameter file, creates the instance, and stops in the NOMOUNT state.

### 6.2. From NOMOUNT to MOUNT

~~~sql
ALTER DATABASE MOUNT;
~~~

Oracle opens the control file and attaches the database.

### 6.3. From MOUNT to OPEN

~~~sql
ALTER DATABASE OPEN;
~~~

Oracle opens the database in the default open mode appropriate for its database role and state.

### 6.4. Directly from SHUTDOWN to MOUNT

~~~sql
STARTUP MOUNT;
~~~

SQL*Plus performs the instance initialization steps and then mounts the database.

### 6.5. Directly from SHUTDOWN to OPEN

~~~sql
STARTUP;
~~~

This is the command commonly used when starting a database to serve applications.

### 6.6. From OPEN Back to MOUNT

Do not use ALTER DATABASE MOUNT while the database is OPEN. You must close the database, shut down the instance, and restart in MOUNT:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

If you only need to change between READ WRITE/READ ONLY, plan the transition through MOUNT according to Oracle requirements and the database role.

### 6.7. Do Not Run Repeated STARTUP on an Active Instance

If the instance is already running, STARTUP can return an error indicating the instance is already started. Check the state before running commands. Use ALTER DATABASE MOUNT/OPEN for valid transitions from the current state.

## 7. Checking Instance and Database State

Do not rely on a single "Connected" line or an existing process to conclude that the database is OPEN.

### 7.1. Checking the Instance

~~~sql
SELECT instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM v$instance;
~~~

Common values of V$INSTANCE.STATUS:
- STARTED: instance has started, corresponding to NOMOUNT.
- MOUNTED: database is mounted.
- OPEN: database is open.
- OPEN MIGRATE: database is open in the corresponding migration/upgrade mode.

The DATABASE_STATUS column provides database status information from the instance's perspective. Read it alongside STATUS and database information rather than using a single column as the conclusion.

### 7.2. Checking the Database Open Mode

Once the database is MOUNTED, query:

~~~sql
SELECT name,
       dbid,
       open_mode,
       database_role,
       controlfile_type
FROM v$database;
~~~

OPEN_MODE may indicate MOUNTED, READ WRITE, READ ONLY, or specialized states such as READ ONLY WITH APPLY in supported standby configurations.

If the database is in NOMOUNT, V$DATABASE cannot yet be queried as it is when mounted. This is why you need V$INSTANCE to verify the instance at the early stage.

### 7.3. Checking Key Parameters

~~~sql
SHOW PARAMETER spfile;
SHOW PARAMETER control_files;
SHOW PARAMETER db_name;
SHOW PARAMETER db_unique_name;
SHOW PARAMETER compatible;
~~~

These parameters help verify which configuration the instance is using and where the control files are located. Do not modify parameters on production without a change plan and a configuration backup.

### 7.4. Checking Datafiles and Redo Logs When MOUNT/OPEN

~~~sql
SELECT file#, name, status
FROM v$datafile
ORDER BY file#;
~~~

~~~sql
SELECT group#, member, status
FROM v$logfile
ORDER BY group#, member;
~~~

~~~sql
SELECT group#, sequence#, status, archived
FROM v$log
ORDER BY group#;
~~~

These views and columns reflect file/redo status; interpretation depends on the database open/mount state and file type. Also inspect the alert log if a file is unavailable or recovery is needed.

## 8. Conditions and Common Errors in NOMOUNT

NOMOUNT primarily depends on the parameter file, instance resources, and OS environment.

### 8.1. PFILE/SPFILE Not Found

Errors may include:
- ORA-01078: failure in processing system parameters.
- LRM-00109: could not open parameter file.

Check:
1. ORACLE_SID.
2. ORACLE_HOME.
3. SPFILE/PFILE path.
4. File read permissions.
5. Parameter syntax.
6. Whether the file is truncated or has incorrect encoding.

Example specifying PFILE explicitly:

~~~sql
STARTUP NOMOUNT
PFILE='/u01/app/oracle/product/dbhome_1/dbs/initORCL.ora';
~~~

Do not create a new SPFILE from a file of unknown origin without verifying the current configuration.

### 8.2. Insufficient OS Resources

NOMOUNT can fail if:
- There is insufficient memory to allocate the SGA.
- Process/thread limits are inappropriate.
- Shared memory or semaphores are insufficient on the corresponding platform.
- Filesystems containing audit/diagnostic or parameter files are unavailable.
- Environment variables are incorrect.

Check the alert log, trace files, OS logs, and resource limits. Do not blindly increase SGA_TARGET or PROCESSES based on guesswork; identify the actual error.

### 8.3. Incompatible Parameters

A parameter may have the wrong type, wrong value, or be incompatible with the version/COMPATIBLE setting. Check LRM/ORA errors in the alert log and consult version documentation. Change one parameter at a time in a controlled manner, keeping a backup of the PFILE/SPFILE before editing.

## 9. Conditions and Common Errors in MOUNT

MOUNT requires opening the control files declared in CONTROL_FILES.

### 9.1. Control File Missing or Inaccessible

Common errors may include ORA-00205, ORA-00210, or control file related messages. Possible causes include:
- Incorrect CONTROL_FILES path.
- Filesystem/ASM disk group not mounted.
- File deleted or renamed.
- Incorrect access permissions.
- Storage unavailable.
- Corrupted or out-of-sync control file.

Check:
- SHOW PARAMETER control_files.
- Alert log.
- ASM/disk group or filesystem status.
- Control file backups and multiplexed copies if available.

Do not arbitrarily copy an old control file into the production location. The control file stores structure and recovery information; restore/recreate it using the proper procedure.

### 9.2. Control File Does Not Match Database

The control file may belong to a different database or not match the datafiles/redo logs. Verify DBID, DB_NAME, DB_UNIQUE_NAME, and the backup source before mounting/opening. Do not try to bypass a mismatch by changing parameters to force the database open.

### 9.3. MOUNT Succeeds but a Datafile Is Missing

A successful MOUNT does not prove all datafiles are ready. The control file can be opened while a datafile is absent or requires recovery. These issues are usually detected during OPEN or during recovery procedures.

## 10. Conditions and Common Errors in OPEN

OPEN requires valid files and an appropriate recovery state.

### 10.1. Datafile Needs Media Recovery

A common error is:
- ORA-01113: file needs media recovery.
- ORA-01110: data file identification.

This means the datafile must be recovered using the appropriate backup/redo before opening. Do not treat OPEN as a fix command. Identify the file, check backups and archived redo, and use RMAN or a DBA-approved recovery procedure.

Illustrative example in an appropriate environment:

~~~sql
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

In production, prefer RMAN and a recovery procedure designed for the specific database/role. Do not run RECOVER DATABASE blindly without knowing the state of the control file, backups, and redo.

### 10.2. Missing Online Redo Log

If a required online redo log is unavailable or corrupted, the database may fail to open or require special recovery. Check V$LOG, V$LOGFILE, and the alert log. Do not manually delete redo log files while the database is using them.

### 10.3. Instance Recovery After a Crash

If an instance crashes or undergoes shutdown abort, Oracle typically performs instance recovery when opening the database using online redo to bring datafiles to a transaction-consistent state.

Instance recovery differs from media recovery:
- Instance recovery is usually performed automatically by Oracle during startup after an instance failure.
- Media recovery requires restoring lost/corrupted files from backup and applying appropriate redo.

Do not confuse a database undergoing crash recovery with a database requiring datafile restoration.

### 10.4. OPEN Rejected Because Database Is Not MOUNTED

If you run ALTER DATABASE OPEN while the instance is in NOMOUNT, you first need:

~~~sql
ALTER DATABASE MOUNT;
ALTER DATABASE OPEN;
~~~

If the error involves the control file, datafiles, or recovery, resolve the underlying cause instead of repeating OPEN.

## 11. OPEN RESETLOGS and NORESETLOGS

RESETLOGS is a critical recovery operation, not a regular option for "retrying opening the database."

### 11.1. When Is RESETLOGS Needed?

Certain recovery scenarios require OPEN RESETLOGS, typically including:
- Incomplete recovery to an earlier point in time/SCN/log.
- Recovery using a backup control file in scenarios that require resetlogs.
- A recovery procedure that creates a new database incarnation.

Command syntax example:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

Run only after recovery is complete and Oracle requires it or the recovery procedure specifies it. RESETLOGS creates a new incarnation and reinitializes the online redo log sequence according to Oracle semantics.

### 11.2. NORESETLOGS

~~~sql
ALTER DATABASE OPEN NORESETLOGS;
~~~

NORESETLOGS is used in appropriate complete recovery scenarios, with the current control file and when recovery conditions allow. You do not always need to explicitly specify NORESETLOGS; a normal OPEN is usually sufficient if default conditions are met.

### 11.3. Why Not Use RESETLOGS to Fix Every OPEN Error?

RESETLOGS alters incarnation history and affects backup/recovery strategy. If run at the wrong time, it can complicate using older backups and archived redo. After RESETLOGS, perform appropriate backups according to DBA policy.

Always check:
- Is recovery complete?
- Is the control file current or a backup?
- Is this an incomplete recovery?
- Does Oracle require RESETLOGS or NORESETLOGS?
- What is the backup plan after opening?

## 12. Startup Sequences in Operational Scenarios

### 12.1. Normal Database Startup

~~~sql
STARTUP;
~~~

Then verify:

~~~sql
SELECT status FROM v$instance;
SELECT open_mode, database_role FROM v$database;
~~~

Expect the instance to be OPEN and a normal primary database to be READ WRITE.

### 12.2. Only Needing Instance in NOMOUNT

~~~sql
STARTUP NOMOUNT;
~~~

Used when preparing CREATE DATABASE, handling parameters, or performing a recovery step that requires an unmounted instance. Do not leave an instance in NOMOUNT for long in an application environment because the database is not serving data access.

### 12.3. Starting for Recovery in MOUNT

~~~sql
STARTUP MOUNT;
~~~

After completing recovery/maintenance operations and verifying conditions:

~~~sql
ALTER DATABASE OPEN;
~~~

If recovery requires RESETLOGS, use that command only according to the recovery procedure.

### 12.4. Opening READ ONLY

~~~sql
STARTUP MOUNT;
ALTER DATABASE OPEN READ ONLY;
~~~

If the database is already OPEN READ WRITE, you cannot switch modes by calling STARTUP MOUNT on the running instance. Plan a shutdown and restart in MOUNT followed by OPEN READ ONLY, accounting for the impact on sessions and services.

### 12.5. Maintenance in Restricted Session

~~~sql
STARTUP RESTRICT;
~~~

Or when the database is already OPEN:

~~~sql
ALTER SYSTEM ENABLE RESTRICTED SESSION;
-- Perform maintenance work.
ALTER SYSTEM DISABLE RESTRICTED SESSION;
~~~

Check application users and background jobs before reopening normal access.

## 13. Shutdown and Its Relationship to Startup State

Shutdown takes the instance and database through closing, dismounting, and stopping processes. The shutdown mode affects active work and recovery at the next startup.

### 13.1. SHUTDOWN NORMAL

Waits for users to disconnect. Can wait a long time if sessions remain open.

### 13.2. SHUTDOWN TRANSACTIONAL

Waits for active transactions to finish, then closes the database according to command semantics.

### 13.3. SHUTDOWN IMMEDIATE

Disconnects sessions per the shutdown procedure, rolls back uncommitted transactions, and closes the database in a controlled manner. This is the common choice for maintenance when a proactive shutdown is needed.

~~~sql
SHUTDOWN IMMEDIATE;
~~~

### 13.4. SHUTDOWN ABORT

Stops the instance immediately without performing the normal closing procedure:

~~~sql
SHUTDOWN ABORT;
~~~

The next startup may require instance recovery. Only use when controlled shutdown methods are not feasible or as directed during troubleshooting. Do not use ABORT as the default shutdown method.

### 13.5. Restarting in the Required State After Shutdown

| Next Goal | Command |
| --- | --- |
| Serve normal applications | STARTUP |
| Prepare to create database | STARTUP NOMOUNT |
| Recovery/maintenance needing control file | STARTUP MOUNT |
| Open read-only | STARTUP MOUNT then ALTER DATABASE OPEN READ ONLY |

## 14. CDB and PDB in Multitenant Architecture

In Oracle multitenant, the CDB and PDBs have separate open lifecycles.

### 14.1. CDB OPEN Does Not Mean Every PDB Is OPEN

The CDB root can be OPEN while one or more PDBs remain MOUNTED. Therefore, checking V$DATABASE.OPEN_MODE of the CDB is not sufficient to conclude that applications in all PDBs are ready.

Check PDBs:

~~~sql
SHOW PDBS;
~~~

Or:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

### 14.2. Opening a PDB

When the CDB is OPEN:

~~~sql
ALTER PLUGGABLE DATABASE apppdb OPEN;
~~~

Open all permitted PDBs:

~~~sql
ALTER PLUGGABLE DATABASE ALL OPEN;
~~~

Only open the PDBs required by the operational plan and role. Some PDBs may be configured to open READ ONLY or restricted as required.

### 14.3. Saving PDB State Across Startups

You can save a PDB's open state:

~~~sql
ALTER PLUGGABLE DATABASE apppdb SAVE STATE;
~~~

This command allows Oracle to restore the saved PDB state on the next CDB startup according to the version's supported mechanism. Check PDB saved state and system startup policy before using.

### 14.4. Checking the Correct Container

When working with PDBs, check CON_NAME:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Do not confuse operations on the CDB root with operations on a PDB. A startup/mount/open database command usually controls the CDB at the database level; PDBs are opened/closed using ALTER PLUGGABLE DATABASE.

## 15. Oracle RAC and Data Guard

Startup states in HA environments involve additional factors such as instances, roles, and cluster coordination.

### 15.1. RAC: A Database with Multiple Instances

In RAC, multiple instances can mount/open the same database simultaneously. Each instance has its own state, while the database is a shared resource.

Check:

~~~sql
SELECT inst_id,
       instance_name,
       status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
~~~

One instance may be OPEN while another is STARTED/MOUNTED or not yet running. Do not look at just one instance to conclude the state of the entire cluster.

In Oracle Restart/RAC environments managed by Clusterware, use SRVCTL or standardized cluster tools to start/stop databases and instances. Avoid manual startup via SQL*Plus if doing so causes Clusterware resource states to diverge. SRVCTL syntax may vary by release; check help/documentation for the exact version.

### 15.2. Data Guard Physical Standby

A physical standby is usually mounted to apply redo. Depending on configuration and licensing, a standby can be opened READ ONLY while redo apply is active via Active Data Guard.

Check role and open mode:

~~~sql
SELECT database_role,
       open_mode,
       switchover_status
FROM v$database;
~~~

Do not apply primary OPEN READ WRITE procedures to a physical standby. The database role determines which open modes are valid.

### 15.3. Do Not Infer Role Solely from OPEN_MODE

READ ONLY could be a reporting database, a standby, or a specialized operational state. Examine DATABASE_ROLE together with OPEN_MODE. In Data Guard, opening a standby READ WRITE may require an activation/failover procedure and a role change; do not attempt it as a routine open operation.

## 16. Alert Log and Startup Diagnostics

The alert log is a primary source for understanding which stage Oracle reached and why startup failed.

### 16.1. Finding the Alert Log

You can view diagnostic locations via ADR:

~~~sql
SELECT name, value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Diag Alert', 'Default Trace File');
~~~

Depending on the version, you can use ADRCI to view the alert log:

~~~text
adrci
show homes
set homepath <ADR_HOME>
show alert -tail 100
~~~

The ADR home name must be the actual value from the environment; do not use the placeholder verbatim.

### 16.2. Reading Sequentially

During startup:
1. Check for parameter file reading errors.
2. Confirm the instance created the SGA and background processes.
3. Look for control file open messages.
4. Confirm the database mounted.
5. Look for datafile and redo log open messages.
6. Check recovery start/completion.
7. Confirm database open and open mode.
8. If an error occurs, read the ORA- errors preceding the final error to find the root cause.

Do not just grab the last ORA error from the client. The alert log usually includes file paths, processes, checkpoints, and recovery details.

### 16.3. Diagnosing by Stage

| Failure Stage | Cause Categories to Check |
| --- | --- |
| NOMOUNT | PFILE/SPFILE, parameters, memory, OS processes/shared memory |
| MOUNT | CONTROL_FILES, storage, file permissions, control file consistency |
| OPEN | Datafiles, online redo, checkpoints, recovery, database role |
| PDB OPEN | PDB files, PDB state, plugin compatibility, service/configuration |
| RAC instance start | Clusterware resources, ASM, network, instance-specific configuration |

## 17. Operational Safety When Changing Startup State

Startup and open mode are administrative operations that directly impact application availability.

Before executing:
- Identify DB_NAME and DB_UNIQUE_NAME.
- Identify the primary/standby role.
- Identify the instance and host being controlled.
- Verify that an appropriate backup and recovery plan exists.
- Check control files, datafiles, redo logs, and ASM/filesystem.
- Identify which applications/sessions will be affected.
- Check which PDBs and services need to be opened.
- Read the alert log and record the current state.
- Perform the change within a maintenance window if downtime is involved.
- Verify the state after each transition.

Do not run commands that change incarnation, recreate control files, or skip recovery without understanding the consequences. Do not delete database files using OS commands to "clear errors" while Oracle still manages those files.

## 18. Decision Flow for Choosing the Required State

You can choose the state based on the goal:

~~~text
What is the goal?
  |
  +-- Create database / prepare control file?
  |       |
  |       +-- STARTUP NOMOUNT
  |
  +-- Recovery / change ARCHIVELOG / control file operations?
  |       |
  |       +-- STARTUP MOUNT
  |
  +-- Applications need normal read/write?
  |       |
  |       +-- STARTUP or ALTER DATABASE OPEN READ WRITE
  |
  +-- Read-only reporting?
  |       |
  |       +-- MOUNT then OPEN READ ONLY
  |
  +-- Maintenance, restrict users?
          |
          +-- OPEN RESTRICTED
~~~

The diagram is an initial selection guide. Data Guard, RAC, recovery, and upgrade workflows have specific requirements; always verify role, version, and file status before running commands.

## 19. Comprehensive Practical Example: Staged Startup

### 19.1. Connect with Administrative Privileges

On the database server, for example:

~~~text
sqlplus / as sysdba
~~~

OS authentication connections depend on OS configuration and the OSDBA group. Remote connections may require a password file and appropriate network configuration.

### 19.2. Start in NOMOUNT

~~~sql
STARTUP NOMOUNT;
~~~

Check:

~~~sql
SELECT instance_name, status, startup_time
FROM v$instance;
~~~

Expect STATUS to be STARTED.

### 19.3. Transition to MOUNT

~~~sql
ALTER DATABASE MOUNT;
~~~

Check:

~~~sql
SELECT instance_name, status
FROM v$instance;

SELECT name, open_mode, database_role
FROM v$database;
~~~

Expect V$INSTANCE.STATUS to be MOUNTED and V$DATABASE.OPEN_MODE to be MOUNTED.

### 19.4. Transition to OPEN

~~~sql
ALTER DATABASE OPEN;
~~~

Check:

~~~sql
SELECT instance_name, status
FROM v$instance;

SELECT name, open_mode, database_role
FROM v$database;
~~~

For a normal primary database, expect STATUS to be OPEN and OPEN_MODE to be READ WRITE.

### 19.5. Read the Alert Log and Check Applications

After opening:
- Verify the alert log has no unresolved startup/recovery errors.
- Check tablespaces/datafiles and PDBs.
- Verify services are registered and the listener can route connections.
- Perform application health checks.
- Confirm users have privileges and required objects are in a valid state.

An OPEN database does not guarantee all applications are working; services, PDBs, listeners, jobs, credentials, and external dependencies must also be ready.

## 20. Common Misconceptions

**NOMOUNT means the database is open but has no users.** Incorrect. The instance is running, but the control file is not open and the database is not mounted.

**MOUNT means datafiles are ready for SELECT.** Incorrect. The control file is open; the database is not yet OPEN for normal data access.

**OPEN is just another name for MOUNT.** Incorrect. OPEN opens datafiles/online redo and puts the database into an open mode.

**A running instance means applications can connect.** Incorrect. The instance could be only in NOMOUNT or MOUNT.

**STARTUP MOUNT requires running STARTUP NOMOUNT first.** Not required. STARTUP MOUNT initializes the instance and mounts the database if it is shut down.

**You can run ALTER DATABASE MOUNT when the database is OPEN.** Not in the normal state transition flow. You must shut down and then start in MOUNT.

**V$DATABASE can always be queried in NOMOUNT.** Incorrect. The database is not yet mounted, so views requiring database metadata may be inaccessible.

**A successful MOUNT means all datafiles are good.** Incorrect. The control file is open; datafile errors may only appear during OPEN or recovery.

**OPEN READ ONLY is the same as restricted session.** Incorrect. READ ONLY restricts data writes; restricted session restricts who can log in.

**RESETLOGS is a way to retry OPEN when encountering errors.** Incorrect. RESETLOGS is part of a recovery procedure and creates a new incarnation.

**Instance recovery and media recovery are the same.** Incorrect. Instance recovery usually runs automatically after a crash; media recovery requires restoring files from backup and applying redo.

**CDB OPEN means all PDBs are OPEN.** Incorrect. Check V$PDBS or SHOW PDBS.

**OPEN READ WRITE is always right for every database role.** Incorrect. Physical standbys and other roles have specific rules.

**RAC only requires checking one instance.** Incorrect. Each instance has its own state; check GV$INSTANCE and Clusterware status.

**The alert log only contains errors, not startup info.** Incorrect. The alert log records startup, mount, open, recovery events, and diagnostic info.

## 21. Self-Practice Exercises

1. Distinguish between an instance and a database in Oracle.
2. List the main components of an instance.
3. What types of metadata does the control file contain?
4. Explain what happens during STARTUP NOMOUNT.
5. Why can't tables be accessed in NOMOUNT?
6. Name two administrative tasks suited for NOMOUNT.
7. Start an instance specifying a PFILE path.
8. Explain the role of CONTROL_FILES.
9. Describe the steps Oracle performs during MOUNT.
10. Write the command to transition from NOMOUNT to MOUNT.
11. Why is MOUNT not ready for applications?
12. List tasks that typically require the database to be in MOUNT.
13. Write a safe conceptual sequence to enable ARCHIVELOG.
14. Describe the main steps during OPEN.
15. Distinguish between OPEN READ WRITE and OPEN READ ONLY.
16. How does restricted session differ from READ ONLY?
17. Write commands to enable and disable restricted session.
18. Use V$INSTANCE to verify state.
19. Use V$DATABASE to verify OPEN_MODE and DATABASE_ROLE.
20. Why might V$DATABASE not be queryable in NOMOUNT?
21. List causes that make MOUNT fail.
22. Distinguish control file errors from datafile errors.
23. What condition does ORA-01113 usually indicate?
24. Distinguish instance recovery from media recovery.
25. When might OPEN RESETLOGS be required?
26. Why shouldn't RESETLOGS be used to try to open the database?
27. Explain why CDB OPEN does not guarantee PDB OPEN.
28. Write commands to open a PDB and save the PDB's state.
29. In RAC, why is it necessary to check each INST_ID?
30. Design a startup runbook from SHUTDOWN to OPEN, including file checks, recovery, alert log, and health checks.

**NOMOUNT initializes the instance, MOUNT opens the control file and attaches the database, and OPEN opens datafiles/redo so the database serves according to its open mode.** Choose the state based on your administrative objective, verify identity/role and files before transitioning, confirm results using V$INSTANCE and V$DATABASE, and read the alert log when errors occur. In particular, do not use OPEN RESETLOGS as a routine retry method; it affects recovery history and must follow proper procedures.
