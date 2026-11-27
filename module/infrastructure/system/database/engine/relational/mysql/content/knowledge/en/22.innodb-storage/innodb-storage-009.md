# Temporary Tablespaces, Undo Tablespaces, and Space Management

This lesson belongs to the **InnoDB Storage** chapter of the **DATABASE_MYSQL** module. The module aims to help you master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. Both temporary tablespaces and undo tablespaces consume disk space, yet they serve different purposes. To properly address growing InnoDB files, you must determine whether the file stores session temporary data, rollback segments for temporary tables, or undo logs supporting MVCC for regular tables.

After this lesson, you will be able to distinguish between session temporary tablespaces, global temporary tablespaces, and undo tablespaces; understand the roles of undo logs, rollback segments, and purge; monitor capacity with INFORMATION_SCHEMA; identify long-running transactions that grow the history list; configure temporary tablespace limits and automatic undo tablespace truncation; and resolve space issues without manually deleting InnoDB files.

## 1. Three Tablespace Types to Distinguish

In InnoDB, the terms "temporary" and "undo" can be confusing because both involve data that is not permanent business table records.

There are three main components:

1. **Session temporary tablespace:** stores user-created temporary tables and on-disk internal temporary tables created by the optimizer.
2. **Global temporary tablespace:** typically the **ibtmp1** file, storing rollback segments for modifications to user-created temporary tables.
3. **Undo tablespace:** stores undo logs for transactions operating on regular tables, supporting rollback and consistent reads/MVCC.

| Component | Purpose | Typical data | Space lifecycle |
|---|---|---|---|
| Session temporary tablespace | Stores per-session temporary tables and optimizer internal temp tables | Intermediate results, application-created temp tables | When a session disconnects, the tablespace is truncated and returned to the pool |
| Global temporary tablespace (ibtmp1) | Stores rollback segments for changes to user-created temporary tables | Undo for INSERT/UPDATE/DELETE on temporary tables | Recreated on normal server startup; file can autoextend |
| Undo tablespace | Stores undo logs for regular tables | Older data versions, rollback information | Can grow with workload; can be truncated once undo is no longer used by active transactions/read views |

Key point to remember: ibtmp1 is not where all on-disk temporary tables reside. Session temporary tables and optimizer internal temporary tables use session temporary tablespaces; the global temporary tablespace primarily stores rollback segments for changes to user-created temporary tables.

## 2. Session Temporary Tablespaces

A session temporary tablespace is an InnoDB tablespace allocated to a session when the session needs to create temporary tables on disk.

It stores:

- Temporary tables created by users with CREATE TEMPORARY TABLE.
- On-disk internal temporary tables created by the optimizer during query processing.

In MySQL 9.7, InnoDB is always used as the storage engine for on-disk internal temporary tables.

### The Session Temporary Tablespace Pool

At server startup, InnoDB creates an initial pool of 10 session temporary tablespaces. When a session first needs an on-disk temporary table, InnoDB allocates a tablespace from the pool.

A single session can be allocated up to two tablespaces:

- One tablespace for user-created temporary tables.
- One tablespace for internal temporary tables created by the optimizer.

When a session disconnects, its session temporary tablespaces are truncated and returned to the pool. The pool can expand automatically when needed, though the number of tablespaces in the pool does not automatically shrink while the server is running.

This means:

- A session creating a large temporary table can cause a session temporary tablespace file to grow.
- When the session closes, the tablespace is truncated and returned to the pool for reuse.
- The number of files in the pool does not necessarily disappear after sessions close.
- A normal server shutdown removes the pool; the pool is recreated when the server starts.

Session temporary tablespace files typically have the .ibt extension and reside in the default #innodb_temp directory beneath the data directory.

### Configuring the Location

The innodb_temp_tablespaces_dir variable specifies where InnoDB creates the session temporary tablespace pool.

Checking:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_temp_tablespaces_dir';
~~~

In MySQL 9.7:

| Attribute | Value |
|---|---|
| Scope | GLOBAL |
| Dynamic | No |
| Default | #innodb_temp |

This is a startup-only variable. To change the location, configure it in the option file and restart the server following operational procedures. Do not move or delete files in this directory while the server is running.

## 3. Global Temporary Tablespace (ibtmp1)

The global temporary tablespace is InnoDB's shared temporary tablespace. The default file is typically ibtmp1.

It stores rollback segments for modifications to user-created temporary tables. For example, when a session runs INSERT, UPDATE, or DELETE on an InnoDB temporary table, the corresponding undo logs are placed in a rollback segment of the global temporary tablespace.

These undo logs are only needed for rollback while the server is running; they do not require redo logging for crash recovery like undo logs of regular tables.

### Lifecycle of ibtmp1

Under default configuration:

- The ibtmp1 file is created when MySQL starts up.
- The file has an initial size slightly larger than 12 MB.
- The file autoextends when more space is needed.
- On normal server shutdown, the global temporary tablespace is removed.
- On server restart, the tablespace is created fresh.
- If the server stops abnormally, the file may remain on the filesystem; on the next startup, MySQL handles recreating it per startup procedures.

Do not delete ibtmp1 while the server is running. If you need to reclaim space from a bloated global temporary tablespace file, the standard approach is to schedule a MySQL restart during an appropriate maintenance window.

### Checking Configuration and Size

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_temp_data_file_path';

SELECT
    FILE_NAME,
    TABLESPACE_NAME,
    INITIAL_SIZE,
    TOTAL_EXTENTS * EXTENT_SIZE AS total_size_bytes,
    DATA_FREE,
    MAXIMUM_SIZE
FROM INFORMATION_SCHEMA.FILES
WHERE TABLESPACE_NAME = 'innodb_temporary';
~~~

The default value of innodb_temp_data_file_path is:

~~~text
ibtmp1:12M:autoextend
~~~

A maximum limit can be configured, for example:

~~~ini
[mysqld]
innodb_temp_data_file_path=ibtmp1:12M:autoextend:max:2G
~~~

In this example, the file starts at roughly 12 MB, is allowed to autoextend, and has a 2 GB cap. This setting requires a server restart.

Setting a limit does not automatically make queries needing large temporary space succeed. If the file hits the limit, operations needing more space may fail because the tablespace cannot expand. Choose the limit based on disk capacity and real workload; do not set it so low that queries fail frequently.

## 4. Temporary Tables, Internal Temporary Tables, and tmpdir Are Not the Same

There are several kinds of temporary files in MySQL. Not every file containing "tmp" belongs to InnoDB temporary tablespaces.

| Component | Used for | Configuration / Observation |
|---|---|---|
| User-created temporary table | Temporary tables created by an application in a session | CREATE TEMPORARY TABLE, INNODB_TEMP_TABLE_INFO |
| Internal temporary table | Intermediate tables created by the optimizer, e.g., some GROUP BY, DISTINCT, UNION, window operations | INNODB_SESSION_TEMP_TABLESPACES |
| Session temporary tablespace | .ibt files allocated to sessions to store on-disk temporary tables | innodb_temp_tablespaces_dir |
| Global temporary tablespace | Rollback segments for changes on user-created temporary tables | ibtmp1, innodb_temp_data_file_path |
| tmpdir | MySQL's general temporary directory for certain operations | tmpdir variable |
| innodb_tmpdir | Temporary sort file directory for certain online ALTER TABLE rebuilds | innodb_tmpdir variable |

In particular, innodb_tmpdir is not where session temporary tablespaces or ibtmp1 reside. It is used for temporary sort files during online ALTER TABLE operations that rebuild tables. Do not change innodb_tmpdir expecting to relocate all InnoDB temporary tables.

## 5. What Are Undo Logs and Undo Tablespaces?

An undo log is a collection of undo records associated with a read/write transaction. An undo record holds the information needed to reverse the transaction's latest change to a clustered index record.

Undo logs serve two critical purposes:

1. **Rollback:** if a transaction is rolled back, InnoDB uses undo records to undo the transaction's changes.
2. **Consistent read/MVCC:** if a transaction needs to see an older version of data per its read view, InnoDB uses undo records to reconstruct the earlier version.

Undo logs are organized in the hierarchy:

~~~text
Undo record
    ↓
Undo log segment
    ↓
Rollback segment
    ↓
Undo tablespace
~~~

Rollback segments reside inside undo tablespaces or the global temporary tablespace.

### Undo Log vs. Redo Log

| Log type | Primary purpose |
|---|---|
| Undo log | Undoing changes and reconstructing older versions for consistent reads |
| Redo log | Recovering written changes via crash recovery mechanisms |

Undo is not a database backup. Redo does not replace undo. The two log types play distinct roles in transactions and recovery.

### Undo for Regular Tables vs. Temporary Tables

InnoDB allocates separate undo logs by operation type:

- INSERT on regular tables.
- UPDATE/DELETE on regular tables.
- INSERT on user-created temporary tables.
- UPDATE/DELETE on user-created temporary tables.

Undo for regular tables is allocated from rollback segments in undo tablespaces. Undo for user-created temporary tables is allocated from rollback segments in the global temporary tablespace.

This explains why a workload creating and modifying many temporary tables can grow ibtmp1, whereas a heavy UPDATE/DELETE workload on business tables can grow undo tablespaces.

## 6. Why Do Undo Tablespaces Grow in Size?

Undo tablespaces grow when a workload generates many undo records and InnoDB cannot release them yet.

Common causes:

- Large-volume UPDATE/DELETE transactions.
- Long-running transactions that have not yet COMMITted or ROLLBACKed.
- Sessions holding idle transactions still left open.
- Transactions using consistent reads that hold onto an old read view.
- A write workload generating data faster than purge can clean up unneeded undo.
- Batch jobs running too long without splitting into appropriately sized transactions.

### Long Transactions Retain Older Versions

Suppose Session A starts a transaction at the REPEATABLE READ isolation level and establishes a read view. While A stays open, Session B repeatedly runs UPDATEs and COMMITs data.

Session A must continue seeing versions consistent with its old read view. Therefore, InnoDB must retain the undo needed to reconstruct older versions for A.

If Session A stays open for a long time, purge cannot remove undo records still needed by that read view. The undo tablespace can continue growing.

A read-only transaction can also hold a read view and increase the history list, even though that transaction produces no new undo records itself.

### History List Length

History list length is a metric indicating purge lag in the TRANSACTIONS section of SHOW ENGINE INNODB STATUS.

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Look for the section:

~~~text
------------
TRANSACTIONS
------------
...
History list length 20
~~~

Do not use a single fixed number as an alert threshold for every system. Observe trends over time, growth rate, write volume, age of the oldest transaction, and remaining free disk space.

A steadily climbing value may indicate that purge cannot keep up or an old read view is pinning undo.

## 7. How Does Purge Free Undo?

Purge is InnoDB's background process that cleans up undo log records no longer needed for rollback or MVCC.

For example, deleting a row with DELETE does not mean the row and index records are physically removed immediately. InnoDB marks the change and keeps the required undo. Once no active transaction or read view needs the older version, purge can process delete-marked records and free the corresponding undo.

Conceptual flow:

~~~text
UPDATE / DELETE
      ↓
Create undo record
      ↓
COMMIT
      ↓
Undo may still be needed for old read views
      ↓
Old read views finish
      ↓
Purge processes history list
      ↓
Unneeded undo records are freed
      ↓
Rollback segment can be reused or truncated
~~~

Purge cannot delete undo that an active transaction still needs to read an older version. Thus, increasing purge threads alone cannot resolve an old transaction holding a read view.

When the history list grows, inspect both long-running transactions and purge capacity; do not simply increase purge configuration settings mechanically.

## 8. Default Undo Tablespaces and Storage Location

When initializing a MySQL instance, InnoDB creates two default undo tablespaces:

| Tablespace name | Default filename |
|---|---|
| innodb_undo_001 | undo_001 |
| innodb_undo_002 | undo_002 |

These two tablespaces are created at instance initialization because rollback segments must exist before the server accepts SQL statements. Having two active undo tablespaces is also the minimum prerequisite for automatic truncation.

The innodb_undo_directory variable determines where default undo tablespaces and user-created undo tablespaces are placed if no explicit path is specified.

Checking:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_undo_directory';
~~~

If the variable is not configured, default undo tablespaces reside inside the data directory.

In MySQL 9.7, innodb_undo_directory has GLOBAL scope and is non-dynamic. Changing its location is a structured configuration/restart task; do not move undo files while the server is running.

### Viewing Existing Undo Files

~~~sql
SELECT
    TABLESPACE_NAME,
    FILE_NAME,
    FILE_TYPE
FROM INFORMATION_SCHEMA.FILES
WHERE FILE_TYPE = 'UNDO LOG'
ORDER BY TABLESPACE_NAME;
~~~

An instance supports up to 127 undo tablespaces, including the two default tablespaces. Additional undo tablespaces can be created to spread space or reduce individual tablespace sizes, though workload and I/O must be evaluated before changing.

## 9. Monitoring Session Temporary Tablespaces

MySQL provides the INFORMATION_SCHEMA.INNODB_SESSION_TEMP_TABLESPACES metadata table to observe session temporary tablespaces.

~~~sql
SELECT
    ID,
    SPACE,
    PATH,
    SIZE,
    STATE,
    PURPOSE
FROM INFORMATION_SCHEMA.INNODB_SESSION_TEMP_TABLESPACES
ORDER BY SIZE DESC;
~~~

Key columns:

| Column | Meaning |
|---|---|
| ID | Process/session ID |
| SPACE | Tablespace ID |
| PATH | File path |
| SIZE | Size in bytes |
| STATE | ACTIVE or INACTIVE |
| PURPOSE | Purpose of tablespace usage |

ACTIVE indicates the tablespace is currently in use by a session; INACTIVE indicates it sits in the pool awaiting reuse.

You can cross-reference with the processlist:

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    INFO
FROM INFORMATION_SCHEMA.PROCESSLIST
ORDER BY TIME DESC;
~~~

To view active InnoDB user-created temporary tables:

~~~sql
SELECT *
FROM INFORMATION_SCHEMA.INNODB_TEMP_TABLE_INFO;
~~~

The INNODB_TEMP_TABLE_INFO table only provides information about active user-created temporary tables in the instance. Internal temporary tables created by the optimizer are tracked via session temporary tablespace metadata and do not necessarily appear in this table.

## 10. Monitoring Temporary and Undo Tablespace Sizes

The INFORMATION_SCHEMA.FILES table provides metadata for InnoDB tablespace files.

### Global Temporary Tablespace

~~~sql
SELECT
    FILE_NAME,
    TABLESPACE_NAME,
    INITIAL_SIZE,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE,
    MAXIMUM_SIZE
FROM INFORMATION_SCHEMA.FILES
WHERE TABLESPACE_NAME = 'innodb_temporary';
~~~

### Undo Tablespaces

~~~sql
SELECT
    FILE_NAME,
    TABLESPACE_NAME,
    INITIAL_SIZE,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE,
    MAXIMUM_SIZE
FROM INFORMATION_SCHEMA.FILES
WHERE FILE_TYPE = 'UNDO LOG'
ORDER BY TABLESPACE_NAME;
~~~

### Undo Tablespace Status

~~~sql
SELECT
    NAME,
    STATE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM INFORMATION_SCHEMA.INNODB_TABLESPACES
WHERE NAME LIKE 'innodb_undo_%'
ORDER BY NAME;
~~~

When reading these figures:

- FILE_SIZE indicates the tablespace file size.
- ALLOCATED_SIZE indicates allocated space according to InnoDB metadata.
- DATA_FREE represents free space inside the file per INFORMATION_SCHEMA.FILES metadata.
- File size on the filesystem can exceed the amount of data actively in use.

Do not conclude a file is leaking simply because its size did not drop immediately after a workload finished. Tablespaces can retain free regions for reuse; returning space to the filesystem is a separate step.

## 11. Managing the Global Temporary Tablespace

The innodb_temp_data_file_path variable specifies the name, relative location, size, and attributes of global temporary tablespace data files.

Checking:

~~~sql
SELECT @@GLOBAL.innodb_temp_data_file_path;
~~~

Example configuration with a cap:

~~~ini
[mysqld]
innodb_temp_data_file_path=ibtmp1:12M:autoextend:max:2G
~~~

Attributes:

- Filename: ibtmp1.
- Initial size: 12M.
- autoextend: allows the file to grow automatically when space runs short.
- max:2G: caps maximum file size.

This variable is GLOBAL and non-dynamic. Configuration changes require a server restart.

### When ibtmp1 Has Grown Very Large

Before restarting:

1. Check which file is growing and inspect filesystem capacity.
2. Check sessions currently creating large temporary tables.
3. Check queries with GROUP BY, DISTINCT, ORDER BY, UNION, or window operations generating large intermediate data.
4. Check which sessions hold temporary tables open for a long time.
5. Check whether workloads are running online DDL.
6. Schedule a restart if reclaiming space from the global temporary tablespace file is needed.

A normal restart recreates the global temporary tablespace per configuration. Restarting is not a substitute for fixing queries or bounding workloads that repeatedly drive growth.

Do not delete ibtmp1 with filesystem commands while MySQL is running.

## 12. Automatic Undo Tablespace Truncation

MySQL supports automatically truncating undo tablespaces when a file exceeds a configured threshold.

Two primary variables:

| Variable | Meaning | Characteristics |
|---|---|---|
| innodb_undo_log_truncate | Enables/disables automatic undo tablespace truncation | GLOBAL, dynamic, defaults to ON in MySQL 9.7 |
| innodb_max_undo_log_size | Size threshold for considering truncation | GLOBAL, dynamic, defaults to 1 GiB |

Checking:

~~~sql
SELECT
    @@GLOBAL.innodb_undo_log_truncate,
    @@GLOBAL.innodb_max_undo_log_size;
~~~

Enabling automatic truncation:

~~~sql
SET GLOBAL innodb_undo_log_truncate = ON;
~~~

Setting a 1 GiB threshold:

~~~sql
SET GLOBAL innodb_max_undo_log_size = 1073741824;
~~~

This is an example setting, not a recommended value for every workload. Choose the threshold based on disk space, undo generation rate, transaction duration, and purge capacity.

### Minimum Prerequisites

Automatic truncation requires at least two active undo tablespaces. MySQL creates two default undo tablespaces when initializing an instance.

When an undo tablespace exceeds the threshold:

1. InnoDB marks the selected tablespace for truncation.
2. Rollback segments in the selected tablespace stop accepting new transactions.
3. Active transactions currently using those rollback segments are allowed to finish.
4. Purge frees undo logs no longer needed.
5. Once rollback segments are freed, the tablespace is truncated back to 16 MB.
6. Rollback segments are reactivated to serve new transactions.

This process does not remove undo still needed by running transactions or old read views.

### Monitoring Truncation Activity

~~~sql
SELECT
    NAME,
    SUBSYSTEM,
    COMMENT
FROM INFORMATION_SCHEMA.INNODB_METRICS
WHERE NAME LIKE '%truncate%';
~~~

How often purge checks tablespaces for truncation is governed by innodb_purge_rseg_truncate_frequency. The default value is 128. Only consider changing it after confirming purge is falling behind and understanding load impact.

## 13. Manual Undo Tablespace Truncation

You can proactively take an undo tablespace offline so purge frees its rollback segments and truncates the file.

However, manual truncation requires at least **three active undo tablespaces**:

- Two tablespaces must remain active to maintain the prerequisite supporting automatic truncation.
- A third tablespace is set inactive to be truncated.

Conceptual workflow:

~~~sql
ALTER UNDO TABLESPACE undo_user_01 SET INACTIVE;
~~~

Monitoring status:

~~~sql
SELECT
    NAME,
    STATE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM INFORMATION_SCHEMA.INNODB_TABLESPACES
WHERE NAME = 'undo_user_01';
~~~

Once the state transitions to empty, it can be reactivated:

~~~sql
ALTER UNDO TABLESPACE undo_user_01 SET ACTIVE;
~~~

Or, if it is a user-created undo tablespace intended for removal:

~~~sql
DROP UNDO TABLESPACE undo_user_01;
~~~

The default undo tablespaces innodb_undo_001 and innodb_undo_002 cannot be DROPped. An undo tablespace can only be DROPped when it is in the empty state.

This is an administrative operation that affects rollback segment allocation. Do not run it casually in production. Before executing, verify active tablespace count, transactions using rollback segments, purge status, I/O load, and recoverability.

## 14. Why Can Undo Truncation Affect Performance?

When an undo tablespace is deactivated for truncation, its rollback segments temporarily stop accepting new transactions. The remaining active undo tablespaces must absorb the load.

This can cause a slight performance impact depending on:

- Number of remaining active undo tablespaces.
- Number of concurrent transactions.
- Amount of existing undo logs.
- Undo tablespace size.
- I/O throughput.
- Long transactions still using rollback segments.
- Overall server load.

Automatic truncation does not mean the file shrinks the instant it crosses the threshold. InnoDB must wait for transactions to finish and purge to free undo first.

If a file grows large because a long transaction holds a read view, increasing how often purge checks cannot bypass that read view. You must address the root cause holding undo first.

## 15. Investigation Workflow When Undo Tablespaces Keep Growing

### Step 1: Check History List Length

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Record History list length and compare across multiple timestamps.

### Step 2: Find Old Transactions

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_rows_modified,
    trx_rows_locked,
    trx_query
FROM INFORMATION_SCHEMA.INNODB_TRX
ORDER BY trx_started;
~~~

Look for transactions with long lifetimes, many modified rows, or idle states that remain unfinished.

### Step 3: Inspect the Session and Application Owning the Transaction

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    INFO
FROM INFORMATION_SCHEMA.PROCESSLIST
ORDER BY TIME DESC;
~~~

Match trx_mysql_thread_id with PROCESSLIST.ID. Identify the application, job, or connection pool holding the transaction.

### Step 4: Inspect Undo Tablespaces

~~~sql
SELECT
    TABLESPACE_NAME,
    FILE_NAME,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE
FROM INFORMATION_SCHEMA.FILES
WHERE FILE_TYPE = 'UNDO LOG'
ORDER BY allocated_bytes DESC;
~~~

### Step 5: Resolve the Old Transaction

Prefer asking the application to complete COMMIT/ROLLBACK per business logic. If a session must be KILLed, understand that rolling back a large transaction can take time and continue generating I/O load.

Do not delete undo files or alter tablespace metadata using filesystem commands.

### Step 6: Observe Purge Catching Up

After the old transaction ends, monitor History list length and undo capacity over time. Purge may need time to free undo no longer in use.

### Step 7: Verify the Truncation Mechanism

Check innodb_undo_log_truncate, innodb_max_undo_log_size, the number of active undo tablespaces, and state in INNODB_TABLESPACES.

If the underlying cause of growth persists, truncation only frees space temporarily and the file may grow again.

## 16. Distinguishing File Size from Space Still Needed by Active Data

A large tablespace file does not mean all data inside it is still in use.

Distinguish three states:

1. **Undo still needed:** a transaction or read view still needs older versions; purge cannot free it yet.
2. **Undo freed, free space inside tablespace:** empty regions can be reused for new undo.
3. **Tablespace truncated:** the file is shrunk to return space to the filesystem.

For example, after a heavy UPDATE wave, transactions finish and purge catches up. The undo file may still retain a large size while having ample internal free space. Without truncation, filesystem usage may not drop yet.

Similarly, session temporary tablespaces can be truncated when sessions disconnect and returned to the pool; the global temporary tablespace has a mechanism to reclaim the file on normal server restart.

Never use rm, del, or filesystem tools to delete .ibu, .ibt, or ibtmp1 files while MySQL is running. InnoDB requires metadata and tablespace files to stay consistent for operation and recovery.

## 17. Practice Lab: Observing Temporary Tablespaces

This lab uses two sessions to observe session temporary tablespaces and the global temporary tablespace.

### Step 1: Session A Creates a Temporary Table

~~~sql
CREATE TEMPORARY TABLE tmp_session_report (
    id INT NOT NULL PRIMARY KEY,
    payload VARCHAR(200) NOT NULL
) ENGINE=InnoDB;

INSERT INTO tmp_session_report (id, payload)
VALUES
    (1, REPEAT('A', 100)),
    (2, REPEAT('B', 100)),
    (3, REPEAT('C', 100));

SELECT * FROM tmp_session_report;
~~~

The temporary table is visible only within Session A. Other sessions cannot SELECT directly from this table.

### Step 2: Session B Inspects Session Temporary Tablespace Metadata

~~~sql
SELECT
    ID,
    SPACE,
    PATH,
    SIZE,
    STATE,
    PURPOSE
FROM INFORMATION_SCHEMA.INNODB_SESSION_TEMP_TABLESPACES
ORDER BY SIZE DESC;
~~~

Find the session ID corresponding to Session A and observe PATH, SIZE, STATE, and PURPOSE.

### Step 3: Inspect Active User-Created Temporary Tables

~~~sql
SELECT *
FROM INFORMATION_SCHEMA.INNODB_TEMP_TABLE_INFO;
~~~

Correlate the temporary table information with the session temporary tablespace.

### Step 4: Inspect the Global Temporary Tablespace

~~~sql
SELECT
    FILE_NAME,
    TABLESPACE_NAME,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE
FROM INFORMATION_SCHEMA.FILES
WHERE TABLESPACE_NAME = 'innodb_temporary';
~~~

Sizes may not change noticeably with a small dataset. The goal is to inspect metadata and distinguish global files from session files.

### Step 5: Close Session A

In Session A:

~~~sql
DROP TEMPORARY TABLE tmp_session_report;
~~~

Then close Session A's connection. The session temporary tablespace is truncated and returned to the pool. Re-check metadata in Session B; the file may now appear in the INACTIVE state.

## 18. Practice Lab: Observing Undo and Purge

This lab creates an old read view in Session A, then updates and commits data from Session B to observe the history list.

Run only in a dedicated test environment; do not use production business tables.

### Step 1: Create Data

~~~sql
CREATE DATABASE IF NOT EXISTS innodb_space_lab;
USE innodb_space_lab;

CREATE TABLE undo_probe (
    id INT NOT NULL PRIMARY KEY,
    value_num INT NOT NULL
) ENGINE=InnoDB;

INSERT INTO undo_probe (id, value_num)
VALUES
    (1, 10),
    (2, 20),
    (3, 30),
    (4, 40),
    (5, 50);
~~~

### Step 2: Session A Holds a Consistent Read View

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT *
FROM undo_probe
ORDER BY id;
~~~

Keep this transaction open while performing the next step.

### Step 3: Session B Updates and Commits

~~~sql
USE innodb_space_lab;

UPDATE undo_probe
SET value_num = value_num + 100
WHERE id BETWEEN 1 AND 5;

COMMIT;

SELECT *
FROM undo_probe
ORDER BY id;
~~~

Session B sees the new values. Session A can still see the old version according to its established read view.

### Step 4: Observe the History List

In another administrative session:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Find History list length in the TRANSACTIONS section. Actual values depend on workload, purge, and sampling timing; no specific target number is required for this small lab dataset.

### Step 5: End the Old Read View

In Session A:

~~~sql
COMMIT;
~~~

Then continue observing SHOW ENGINE INNODB STATUS. Once no read view needs the old versions, purge can free the corresponding undo. History list length does not necessarily drop instantaneously.

### Step 6: Inspect Undo Tablespaces

~~~sql
SELECT
    TABLESPACE_NAME,
    FILE_NAME,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE
FROM INFORMATION_SCHEMA.FILES
WHERE FILE_TYPE = 'UNDO LOG';
~~~

With a small dataset, file sizes may not change noticeably. What matters is understanding the relationship among old transactions, undo, history list, and purge.

### Cleanup

~~~sql
DROP DATABASE innodb_space_lab;
~~~

Drop only the lab database just created. Ensure Session A has COMMITted or ROLLBACKed before cleaning up.

## 19. Common Errors and How to Handle Them

| Symptom | Cause | How to handle |
|---|---|---|
| ibtmp1 grows continuously | Heavy temporary table modifications or workloads creating large temporary data | Inspect sessions, queries, and innodb_temp_data_file_path cap |
| Session .ibt file grows | Session creates large temporary tables or internal temporary tables | Inspect INNODB_SESSION_TEMP_TABLESPACES, queries, and sessions holding files |
| Session closed yet file remains in directory | Tablespace was truncated and returned to pool; pool does not auto-shrink file count | Check STATE and SIZE instead of waiting for the file to disappear |
| Undo tablespace grows | Heavy UPDATE/DELETE or long transactions pinning undo | Inspect INNODB_TRX, History list length, and purge |
| History list length climbs steadily | Purge cannot keep up or old read views retain older versions | Identify old transactions and write workloads |
| Transactions committed yet undo file did not shrink | Undo was freed internally, but the file has not been truncated yet | Check auto-truncate settings and tablespace state |
| innodb_undo_log_truncate enabled yet file did not shrink | Fewer than two active tablespaces, undo still in use, or purge has not freed it yet | Check transactions, active tablespaces, and truncate threshold |
| Manual truncate reports unable to deactivate | Fewer than three active undo tablespaces or unsuitable state | Check tablespace count and follow the manual truncation procedure |
| Restarted yet temporary file grows again | Workload continues producing large temporary data | Fix queries, bound sessions, and monitor space usage |
| Server fails to start after moving undo files | Files are not in a known directory or metadata mismatches | Restore proper path/configuration per InnoDB recovery procedures |
| Online ALTER creates unexpected temporary files | innodb_tmpdir/tmpdir differs from InnoDB temporary tablespaces | Identify file type and the corresponding configuration variable |

## 20. Temporary and Undo Tablespace Operations Checklist

- [ ] Distinguished session temporary tablespaces, global temporary tablespaces, and undo tablespaces.
- [ ] Understood that ibtmp1 stores rollback segments for changes to user-created temporary tables.
- [ ] Understood that on-disk internal temporary tables use InnoDB in MySQL 9.7.
- [ ] Understood that session temporary tablespaces are truncated and returned to the pool when a session disconnects.
- [ ] Checked INNODB_SESSION_TEMP_TABLESPACES and INNODB_TEMP_TABLE_INFO.
- [ ] Checked file sizes using INFORMATION_SCHEMA.FILES.
- [ ] Distinguished innodb_tmpdir from innodb_temp_tablespaces_dir and innodb_temp_data_file_path.
- [ ] Noted that innodb_temp_data_file_path and innodb_temp_tablespaces_dir are startup-only.
- [ ] Understood that undo logs serve rollback and MVCC consistent reads.
- [ ] Monitored History list length and oldest transactions.
- [ ] Checked INFORMATION_SCHEMA.INNODB_TRX when undo grows.
- [ ] Understood that purge only frees undo no longer used by active transactions/read views.
- [ ] Identified the two default undo tablespaces and innodb_undo_directory location.
- [ ] Checked innodb_undo_log_truncate and innodb_max_undo_log_size.
- [ ] Verified at least two active undo tablespaces exist for automatic truncation.
- [ ] Perform manual truncation only when the minimum of three active tablespaces is met.
- [ ] Never manually delete .ibu, .ibt, or ibtmp1 files while the server is running.
- [ ] Distinguished internal free space from space returned to the filesystem.
- [ ] Planned a restart if reclaiming global temporary tablespace file size is required.
- [ ] Configured alerts for filesystem capacity and tablespace growth trends.

## 21. Principles to Remember

1. Session temporary tablespaces store user-created temporary tables and on-disk internal temporary tables.
2. The global temporary tablespace ibtmp1 stores rollback segments for modifications on user-created temporary tables.
3. Undo tablespaces store undo logs for transactions operating on regular tables.
4. Undo logs serve rollback and MVCC consistent reads; redo logs serve crash recovery.
5. Long transactions and old read views can pin undo, causing History list length to grow.
6. Purge only frees undo no longer used by any transaction or read view.
7. Session temporary tablespaces are truncated and returned to the pool when a session disconnects; the pool does not reduce its file count while the server runs.
8. ibtmp1 autoextends by default and is typically recreated to reclaim space after a normal shutdown/restart.
9. innodb_tmpdir is for temporary sort files of certain online ALTER TABLE operations, not session temporary tablespaces.
10. MySQL 9.7 creates two default undo tablespaces: innodb_undo_001 and innodb_undo_002.
11. Automatic undo truncation requires at least two active undo tablespaces; manual truncation requires at least three.
12. Never delete tablespace files manually; use metadata, configuration, and proper administrative commands.

## Official References

Behaviors in this article were verified against the **MySQL 9.7 Reference Manual** as of **November 19, 2026**:

1. [Temporary Tablespaces](https://dev.mysql.com/doc/refman/9.7/en/innodb-temporary-tablespace.html): session temporary tablespaces, global temporary tablespaces, file lifecycles, and size inspection.
2. [Undo Tablespaces](https://dev.mysql.com/doc/refman/9.7/en/innodb-undo-tablespaces.html): default undo tablespaces, storage location, adding/dropping tablespaces, automatic and manual truncation.
3. [Undo Logs](https://dev.mysql.com/doc/refman/9.7/en/innodb-undo-logs.html): undo logs, undo segments, rollback segments, and the role of undo for regular/temporary tables.
4. [InnoDB Multi-Versioning](https://dev.mysql.com/doc/refman/9.7/en/innodb-multi-versioning.html): MVCC, older row versions, purge, and the impact of long-running transactions.
5. [Purge Configuration](https://dev.mysql.com/doc/refman/9.7/en/innodb-purge-configuration.html): History list length, purge lag, long transactions, and purge configuration.
6. [InnoDB Startup Options and System Variables](https://dev.mysql.com/doc/refman/9.7/en/innodb-parameters.html): innodb_temp_tablespaces_dir, innodb_temp_data_file_path, innodb_tmpdir, innodb_undo_directory, and undo truncation variables.
7. [INFORMATION_SCHEMA FILES Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-files-table.html): tablespace file metadata, FILE_TYPE, size, and free space.
8. [INNODB_SESSION_TEMP_TABLESPACES](https://dev.mysql.com/doc/refman/9.7/en/information-schema-innodb-session-temp-tablespaces-table.html): tracking session temporary tablespaces by session, path, size, and state.
9. [INNODB_TEMP_TABLE_INFO](https://dev.mysql.com/doc/refman/9.7/en/information-schema-innodb-temp-table-info-table.html): metadata of active InnoDB user-created temporary tables.
