# Reading Architecture from the Right Dynamic Performance Views

An Oracle Database architecture diagram typically includes the **instance**, **SGA**, **PGA**, **server processes**, **background processes**, **CDB/PDB**, **datafiles**, **redo logs**, and application **sessions**. When facing a running Oracle Database, how do you verify that those components actually exist, how they relate to each other, and what state they are in?

Oracle provides **dynamic performance views**, commonly called **V$ views** (and **GV$ views** for multi-instance environments). These are windows into Oracle's runtime state. This lesson walks through reading architecture from the right views using `SELECT` statements, explaining the limits of each result, and assembling them into a complete system picture.

The goal is not to memorize dozens of view names. What matters is building a systematic way of asking: **which component do I want to observe → which view applies → which columns are evidence → what can and cannot be concluded?**

## 1. The Architectural Picture to Verify

~~~mermaid
flowchart TD
    A["Application / SQL client"] --> B["Oracle Net service and session"]
    B --> C["Server process"]
    C <--> D["SGA: shared pool, buffer cache, redo buffer"]
    C <--> E["PGA: process-private memory"]
    C --> F["SQL cursors / execution plans"]
    D <--> G["Table and index data blocks"]
    G <--> H["Tablespace / datafile"]
    D --> I["Redo log buffer"]
    I --> J["LGWR → online redo log"]
    K["DBWn, CKPT, SMON, PMON..."] --> D
    K --> H
    C --> L["Container: CDB root or PDB"]
~~~

This diagram is a conceptual model of **one Oracle instance**. Oracle RAC has multiple instances accessing a shared database; Oracle multitenant can host multiple PDBs. Not every arrow corresponds to a separate process or view, and not every SQL read requires reading physical datafiles.

| Architectural Question | Relevant View | Common Evidence Read |
|---|---|---|
| Which instance is serving the session? | `V$INSTANCE`; RAC: `GV$INSTANCE` | `INSTANCE_NAME`, `HOST_NAME`, `STATUS`, `STARTUP_TIME` |
| What is the database and its role? | `V$DATABASE` | `NAME`, `CDB`, `OPEN_MODE`, `DATABASE_ROLE` |
| Which containers/PDBs exist? | `V$CONTAINERS`, `V$PDBS` | `CON_ID`, `NAME`, `OPEN_MODE` |
| How is the SGA allocated? | `V$SGAINFO`, `V$SGASTAT` | Memory area names, `BYTES`, `POOL` |
| How much PGA is being consumed? | `V$PGASTAT` | `NAME`, `VALUE`, `UNIT` |
| Which process serves an application session? | `V$SESSION`, `V$PROCESS` | `SID`, `SERIAL#`, `PADDR`, `ADDR`, `SPID` |
| Which background process types exist? | `V$BGPROCESS` | `NAME`, `DESCRIPTION` |
| Which tablespace does a datafile belong to? | `V$DATAFILE`, `V$TABLESPACE` | `TS#`, `CON_ID`, `NAME` |
| Where are redo logs and control files? | `V$LOG`, `V$LOGFILE`, `V$CONTROLFILE` | `GROUP#`, `STATUS`, `MEMBER`, `NAME` |
| Which SQLs are cached/recorded? | `V$SQLAREA`, `V$SESSION` | `SQL_ID`, `EXECUTIONS`, `BUFFER_GETS`, `DISK_READS` |
| What is overall read/write activity? | `V$SYSSTAT` | Statistic name and cumulative value |
| Which configuration parameters are active? | `V$SYSTEM_PARAMETER` | `NAME`, `DISPLAY_VALUE` |

These views reflect **state or statistics Oracle currently holds at query time**. They are not a physical dump of the entire database, nor are they meant to record every historical event.

## 2. Preparing a Safe Observation Session

The queries in this lesson are **read-only**. They are suitable for inspecting a practice database or an environment authorized for monitoring. Accessing some V$ views requires specialized privileges; an account granted only business table reads may not be able to query system views.

Connect using SQL*Plus, SQLcl, SQL Developer, or an appropriate SQL tool. In SQL*Plus/SQLcl you can configure formatting:

~~~sql
SET LINESIZE 220
SET PAGESIZE 100
COLUMN instance_name FORMAT A20
COLUMN host_name FORMAT A30
COLUMN name FORMAT A28
COLUMN open_mode FORMAT A18
COLUMN status FORMAT A14
~~~

First, confirm **where you are**. The following query does not require privileges on a V$ view:

~~~sql
SELECT USER AS session_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

`USER` returns the session's database user. `CON_NAME` indicates whether you are in `CDB$ROOT` or a PDB if the system uses multitenant. `SERVICE_NAME` helps identify the connection service. These outputs matter because some dynamic performance views **have different result scopes between root and a PDB**.

### 2.1 If View Queries Are Denied

Examples:

~~~text
ORA-00942: table or view does not exist
ORA-01031: insufficient privileges
~~~

These errors can indicate **missing metadata read privileges**, not proof that the view does not exist or that the database is broken. In Oracle, public names like `V$INSTANCE` are typically synonyms to underlying objects such as `V_$INSTANCE`; queryability depends on account privileges, roles, and how the tool runs SQL. Ask an administrator to grant **the necessary view access within your job scope** or share authorized query results. Do not use `SYSDBA` as an application's default account, and do not grant broad privileges to a practice account.

### 2.2 How Do `V$` and `GV$` Differ?

- `V$...`: observes dynamic components within the connected instance's context; some views show database-level data while still carrying container scoping.
- `GV$...`: *global* variant of many views, typically including an `INST_ID` column to distinguish instances in multi-instance setups such as RAC.

Example:

~~~sql
SELECT instance_name, host_name, status, startup_time
FROM v$instance;
~~~

In a RAC system, if authorized:

~~~sql
SELECT inst_id, instance_name, host_name, status, startup_time
FROM gv$instance
ORDER BY inst_id;
~~~

One row from `V$INSTANCE` does not mean a RAC cluster has only one instance. Conversely, on a non-RAC system, `GV$INSTANCE` usually shows only one instance. You do not need `GV$` for every example when your goal is only observing the current instance.

## 3. Starting with Instance, Database, and Container

Three concepts are often lumped together under the word "Oracle": **instance** (memory and processes), **database** (managed dataset/files), and **container/PDB** (data scope in multitenant architecture).

### 3.1 Is the Instance Opening the Database?

~~~sql
SELECT instance_name,
       host_name,
       version,
       status,
       database_status,
       startup_time
FROM v$instance;
~~~

| Column | Interpretation |
|---|---|
| `INSTANCE_NAME` | Name of the instance serving the session |
| `HOST_NAME` | Host machine running the instance |
| `VERSION` | Engine version reported by the instance |
| `STATUS` | States such as `STARTED`, `MOUNTED`, `OPEN` |
| `DATABASE_STATUS` | Operational status info such as `ACTIVE` |
| `STARTUP_TIME` | Most recent recorded instance startup time |

An example result:

~~~text
INSTANCE_NAME   HOST_NAME      STATUS   DATABASE_STATUS
-------------   -------------  -------  ---------------
orcl1           db-node-01     OPEN     ACTIVE
~~~

Valid conclusion: instance `orcl1` on host `db-node-01` is in the `OPEN` state. **You cannot yet conclude** that every PDB is open, every service is registered with the listener, or external applications can connect successfully.

### 3.2 What Role and Mode Is the Database In?

~~~sql
SELECT name,
       db_unique_name,
       cdb,
       open_mode,
       database_role,
       log_mode
FROM v$database;
~~~

| Column | How to Read |
|---|---|
| `NAME` | Database name |
| `DB_UNIQUE_NAME` | Unique database identifier, useful for distinguishing databases in Data Guard |
| `CDB` | `YES` if a multitenant CDB; `NO` in legacy non-CDB architecture |
| `OPEN_MODE` | `READ WRITE`, `READ ONLY`, `MOUNTED`, etc. |
| `DATABASE_ROLE` | E.g., `PRIMARY` or `PHYSICAL STANDBY` |
| `LOG_MODE` | `ARCHIVELOG` or `NOARCHIVELOG` |

If `OPEN_MODE = READ WRITE` and `DATABASE_ROLE = PRIMARY`, that is evidence the database is open for normal writes at the database level. It is **not enough** to confirm a specific PDB is `READ WRITE`. In Data Guard, standby databases hold different states/roles by design; do not treat every `READ ONLY` result as an incident.

When a database is started only to `NOMOUNT`, information depending on control files or the database may not yet be queryable. Check `V$INSTANCE.STATUS` first and match it against the startup stage.

### 3.3 Observing the List of Containers and PDBs

Only when `V$DATABASE.CDB = YES` and the session has appropriate observation privileges:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$containers
ORDER BY con_id;
~~~

When connected to `CDB$ROOT`, the query can show `CDB$ROOT`, `PDB$SEED`, and application PDBs. A dedicated way to view PDBs:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;
~~~

**Illustrative** example:

~~~text
CON_ID  NAME       OPEN_MODE   RESTRICTED
------  ---------  ----------  ----------
2       PDB$SEED   READ ONLY   NO
3       APPPDB     READ WRITE  NO
4       REPORTPDB  MOUNTED     NO
~~~

`PDB$SEED` is the template PDB, usually `READ ONLY`. `APPPDB` is open for read/write. `REPORTPDB` is only `MOUNTED`, so it cannot yet be used as an open application PDB. In a session connected directly to a PDB, visibility in some views may be scoped to that single container; to understand the entire CDB, observe from root with appropriate privileges.

### 3.4 Reading the `CON_ID` Column in Context

Many V$ views include a `CON_ID` column:

- `CON_ID = 0` typically represents data applying to the whole CDB or data not partitioned by container (also seen in non-CDBs).
- `CON_ID = 1` typically represents `CDB$ROOT`.
- Other values bind to specific containers; look up names in `V$CONTAINERS` rather than guessing PDB names by number.

Do not blindly add rows with `CON_ID = 0` to per-PDB rows and claim it is the system total: they can reflect **different scopes**, causing double-counting.

## 4. Observing SGA and PGA Memory

**SGA (System Global Area)** is instance-level shared memory, including components such as the shared pool, database buffer cache, and redo log buffer. **PGA (Program Global Area)** is private memory serving Oracle processes (e.g., sort/hash work areas, execution state), not a shared pool working like the SGA.

### 4.1 Identifying SGA Components

~~~sql
SELECT name,
       ROUND(bytes / 1024 / 1024, 1) AS size_mb,
       resizeable
FROM v$sgainfo
WHERE name IN (
    'Maximum SGA Size',
    'Buffer Cache Size',
    'Shared Pool Size',
    'Redo Buffers',
    'Large Pool Size',
    'Java Pool Size'
)
ORDER BY name;
~~~

Commonly seen items:

| Item | Architectural Reading Hint |
|---|---|
| `Buffer Cache Size` | Instance space used to cache many data blocks |
| `Shared Pool Size` | Shared space holding SQL/PLSQL structures and metadata |
| `Redo Buffers` | Redo buffer before LGWR writes to online redo logs |
| `Large Pool Size` | Memory area serving activities configured to use the large pool |
| `Java Pool Size` | Memory area for in-database Java components if used |
| `Maximum SGA Size` | Indicator of maximum configured/bounded SGA size for the instance |

**Do not arbitrarily sum rows in `V$SGAINFO`** to compute total SGA: some rows represent aggregate totals, limits, or overlapping scopes. Memory areas can auto-resize under dynamic memory management.

To view finer allocations inside pools:

~~~sql
SELECT NVL(pool, '(other)') AS pool_name,
       ROUND(SUM(bytes) / 1024 / 1024, 1) AS allocated_mb
FROM v$sgastat
GROUP BY pool
ORDER BY pool_name;
~~~

`V$SGASTAT` reports allocation statistics by component/pool inside the SGA. It does not equate to "every byte currently used by one SQL statement", nor is it a direct measure of free disk space.

### 4.2 Viewing PGA at the Instance Level

~~~sql
SELECT name,
       value,
       unit
FROM v$pgastat
WHERE name IN (
    'total PGA allocated',
    'total PGA inuse',
    'aggregate PGA target parameter',
    'over allocation count'
)
ORDER BY name;
~~~

`VALUE` must be interpreted alongside `UNIT`. For example, some rows are in **bytes**, while `over allocation count` is a **count**, so you must never divide every value by `1024 × 1024` and treat it as MB.

- `total PGA allocated` reflects total PGA allocated per instance stats.
- `total PGA inuse` is closer to PGA actively in use.
- `aggregate PGA target parameter` reflects the PGA management target, **not** an absolute guarantee that PGA can never exceed that value.
- `over allocation count` helps identify times Oracle had to allocate PGA beyond the target under certain conditions; check timestamps and related stats.

A slow session cannot be diagnosed as "insufficient PGA" from a single number in `V$PGASTAT`. Correlate it with queries, work areas, durations, and actual workload.

### 4.3 Comparing Memory Configuration with Runtime Observation

~~~sql
SELECT name, display_value
FROM v$system_parameter
WHERE name IN (
    'memory_target',
    'sga_target',
    'sga_max_size',
    'pga_aggregate_target',
    'db_block_size'
)
ORDER BY name;
~~~

`V$SYSTEM_PARAMETER` shows active system parameter values within your observable scope. **Configuration** parameters like `SGA_TARGET` are inputs/rules governing memory; **runtime** statistics in `V$SGAINFO`, `V$SGASTAT`, and `V$PGASTAT` are different perspectives. Never substitute one group for the other. In multitenant environments, the effective scope of certain parameters also depends on the container.

## 5. Observing Sessions, Server Processes, and Background Processes

When an application opens a connection to Oracle, it creates a **logical session**. Server processes execute SQL work according to the active connection model. In **dedicated server** mode, each user session typically pairs with a dedicated server process; in **shared server**, session-to-process relationships are more complex, so never equate session count with process count.

### 5.1 Observing User Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       service_name,
       machine,
       program,
       con_id
FROM v$session
WHERE type = 'USER'
ORDER BY sid
FETCH FIRST 30 ROWS ONLY;
~~~

| Column | What It Helps Understand |
|---|---|
| `SID`, `SERIAL#` | Session identifiers within the instance at observation time; SIDs can be reused |
| `USERNAME` | Database user; may be blank for certain sessions |
| `STATUS` | `ACTIVE` or `INACTIVE` per session state |
| `SERVICE_NAME` | Service used by the session |
| `MACHINE`, `PROGRAM` | Client info sent/recorded by Oracle; helps locate the application |
| `CON_ID` | Container associated with the session in multitenant environments |

`ACTIVE` does not mean a session is continuously consuming CPU; it may be waiting on I/O, locks, network, or other resources. `INACTIVE` does not imply a broken connection: many applications keep connections idle in a pool and use them only when requests arrive. `MACHINE`/`PROGRAM` are useful metadata, not tamper-proof identity proof.

### 5.2 Joining Sessions to Processes

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status AS session_status,
       s.machine,
       s.program AS client_program,
       p.spid AS os_process_id,
       p.program AS oracle_process_program
FROM v$session s
LEFT JOIN v$process p
       ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY s.sid
FETCH FIRST 30 ROWS ONLY;
~~~

`V$SESSION.PADDR` points to the process structure address; `V$PROCESS.ADDR` joins the two views, and `SPID` typically indicates the OS process ID. This answers: **which Oracle process is serving a session?**

Limitations to keep in mind:

- In RAC, `SID` only has meaning within its respective instance; include `INST_ID` when querying `GV$...`.
- In shared server/dispatcher or pooled architectures, a session does not maintain a fixed one-to-one dedicated process relationship at every instant.
- `SPID` may map differently to actual execution units in certain environments or OS configurations; verify when investigating.
- `FETCH FIRST 30 ROWS ONLY` only samples 30 rows by `SID`, not total connection count.

To count sessions by status:

~~~sql
SELECT type, status, COUNT(*) AS session_count
FROM v$session
GROUP BY type, status
ORDER BY type, status;
~~~

This count is **as of the instant of the SELECT**. Never use a single snapshot to conclude peak capacity, connection spikes, or daily load trends.

### 5.3 Finding Background Process Names in the Architecture

~~~sql
SELECT name, description
FROM v$bgprocess
WHERE name IS NOT NULL
ORDER BY name
FETCH FIRST 40 ROWS ONLY;
~~~

Process groups you may encounter:

| Process | General Role |
|---|---|
| `DBWn` | Writes dirty database blocks from buffer cache to datafiles per Oracle mechanisms |
| `LGWR` | Writes redo from redo log buffer to online redo logs |
| `CKPT` | Coordinates checkpoint info and updates required checkpoint metadata |
| `SMON` | Supports system recovery and maintenance duties |
| `PMON` | Supports monitoring and cleaning up process/session resources when needed |
| `ARCn` | Archiver in configurations and states where archived redo logs are saved |

Exact process names, counts, and assignments depend on Oracle version, configuration, and enabled features. `V$BGPROCESS` provides descriptions of background processes known to Oracle; **merely appearing in this view is not proof that the process is currently active or generating load**. To verify a live running process, cross-reference `V$PROCESS` and OS tools within authorized boundaries.

## 6. Reading the Storage Layer: Tablespaces, Datafiles, Tempfiles, Redo, Control Files

At the logical layer, Oracle stores table/index segments inside tablespaces; tablespaces map to datafiles. The instance operates through the buffer cache and I/O mechanisms—not simply "one SQL row equals one file".

### 6.1 Which Tablespace Does a Datafile Belong To?

~~~sql
SELECT d.con_id,
       t.name AS tablespace_name,
       d.file#,
       d.name AS datafile_name,
       d.status
FROM v$datafile d
JOIN v$tablespace t
  ON t.ts# = d.ts#
 AND t.con_id = d.con_id
ORDER BY d.con_id, t.name, d.file#;
~~~

The query shows the **datafile → tablespace** relationship, adding `CON_ID` when the database is a CDB. Reading the columns:

- `TABLESPACE_NAME`: logical storage space name.
- `FILE#`: datafile identifier number within the database.
- `DATAFILE_NAME`: file name/path or Oracle ASM storage identifier.
- `STATUS`: datafile status from the view's perspective.
- `CON_ID`: container scope of the datafile inside the CDB.

ASM files typically have names like `+DATA/...`, which are not regular files you can open directly with a file manager. Table data also lives inside **segments/extents/blocks**; this query **does not tell you which block holds a specific row** or which blocks an SQL statement will actually read.

Across different versions, configurations, and container scopes, output from `V$TABLESPACE` and `V$DATAFILE` can vary. If join results look unexpected, check privileges, container, and `CON_ID`; avoid omitting the container join condition in a multi-PDB CDB.

### 6.2 Tempfiles and Temporary Space

~~~sql
SELECT con_id, file#, name, status
FROM v$tempfile
ORDER BY con_id, file#;
~~~

Tempfiles belong to temporary storage, commonly serving operations such as sorts/hashes that spill from memory and other TEMP uses. A tempfile being present does not mean a query is currently spilling to disk; it is evidence of **configured storage structure**, not an operation trace.

### 6.3 Control Files: Database Metadata

~~~sql
SELECT name, status
FROM v$controlfile;
~~~

The **control file** contains critical metadata Oracle needs to identify and manage the database (e.g., file layout, checkpoint info). `V$CONTROLFILE` reveals which control files Oracle recognizes; paths in the output may expose infrastructure details that should be protected when sharing logs or screenshots.

### 6.4 Online Redo Logs and Redo Log Members

~~~sql
SELECT group#,
       thread#,
       ROUND(bytes / 1024 / 1024, 1) AS size_mb,
       members,
       status,
       archived
FROM v$log
ORDER BY thread#, group#;
~~~

~~~sql
SELECT group#, type, member, status
FROM v$logfile
ORDER BY group#, member;
~~~

`V$LOG` describes **redo log groups** and group statuses. `V$LOGFILE` shows each physical **member** belonging to a group. One group can have multiple members when multiplexed. Common statuses such as `CURRENT`, `ACTIVE`, and `INACTIVE` describe the group lifecycle and must not be naively interpreted as "which file is broken".

Connecting to architecture:

~~~mermaid
flowchart LR
    A["DML modifies data block"] --> B["Redo log buffer in SGA"]
    B --> C["LGWR"]
    C --> D["Online redo log group"]
    D --> E["Member 1"]
    D --> F["Member 2 if configured"]
    A --> G["Dirty buffer"]
    G --> H["DBWn"]
    H --> I["Datafile"]
~~~

**Standard `COMMIT` requires ensuring relevant redo is durably written**, while DBWn can write dirty data blocks to datafiles at a different time. Therefore you cannot infer from `V$DATAFILE` that a recently committed transaction immediately wrote every data block to disk. These views show redo/datafile **structure**, not a list of every change per transaction.

## 7. Connecting Architecture to SQL Execution

When a client sends SQL, Oracle checks/parses it, potentially reuses a cursor in the shared pool, optimizes a data access plan, executes, and returns results. You can observe **in-memory SQL/cursors** and **session state** with appropriate views, provided you understand scope and timing limits.

### 7.1 SQL Cursors Recorded by Oracle

~~~sql
SELECT sql_id,
       executions,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sqlarea
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Column meanings:

| Column | How to Understand It |
|---|---|
| `SQL_ID` | SQL identifier linking to sessions, plans, and statistics |
| `EXECUTIONS` | Execution count recorded for the cursor/SQL within view scope |
| `BUFFER_GETS` | Total recorded logical block gets, not equal to disk reads |
| `DISK_READS` | Disk reads recorded for the SQL; does not mean each read hit a spinning physical disk |
| `ROWS_PROCESSED` | Rows processed per SQL stats; not synonymous with rows returned by an API |

`V$SQLAREA` aggregates statistics for SQL cursors currently tracked by Oracle; SQLs can age out of the shared pool, be re-parsed, or have multiple child cursors. **Never** treat `EXECUTIONS` as total runs since the database was created; nor is high `BUFFER_GETS` alone enough to conclude an SQL statement has a bug.

To inspect a specific `SQL_ID` once found, filter using a bind variable (SQL*Plus/SQLcl):

~~~sql
VARIABLE target_sql_id VARCHAR2(13)
EXEC :target_sql_id := 'replace_with_sql_id'

SELECT sql_id, executions, buffer_gets, disk_reads, rows_processed
FROM v$sqlarea
WHERE sql_id = :target_sql_id;
~~~

`VARIABLE` and `EXEC` are SQL*Plus/SQLcl tool commands; in Java applications, use JDBC bind variables rather than copying those two commands verbatim. An `SQL_ID` no longer in the shared pool may not appear in `V$SQLAREA` even though the SQL ran previously.

### 7.2 What Is a Session Doing or Waiting On?

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       wait_class,
       state
FROM v$session
WHERE type = 'USER'
ORDER BY sid
FETCH FIRST 30 ROWS ONLY;
~~~

`SQL_ID` can indicate the SQL currently associated with a session at observation time. `EVENT` and `WAIT_CLASS` help identify what Oracle records the session waiting on, such as I/O or locks. However:

- A brief snapshot can easily miss fast-running SQLs.
- An `ACTIVE` session can still be waiting; `STATUS` is not a CPU chart.
- `EVENT` and `STATE` must be read in context; a recorded wait event does not prove it is the primary bottleneck of the whole request.
- In applications using connection pools, a single HTTP request may run multiple SQL operations; one session at one instant is only one piece of evidence.

To analyze slow SQL reliably, combine timings, execution plans, bind values, runtime statistics, and measurements over the same observation window. Dynamic performance views help **ask questions** and pick targets for deeper investigation, rather than automatically producing a complete causal trace.

### 7.3 Instance-Level Read/Write Counters

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size'
)
ORDER BY name;
~~~

`V$SYSSTAT` holds statistic counters **scoped to the view's instance/container**, many accumulating since instance startup. To measure load change, capture **two timestamps** within the same observation window and compare deltas, while still interpreting each statistic accurately.

Example:

~~~text
T1: physical reads = 1,000,000
T2: physical reads = 1,012,000
Delta = 12,000 (in Oracle's statistic units)
~~~

You cannot conclude "request X hit the disk 12,000 times" if the numbers were collected at the instance level serving many sessions. Nor do these counters directly report latency or network bytes transferred for an API.

## 8. Querying the Architecture Map Step by Step

Once you understand individual views, you can combine steps into an inspection sequence. Every query is a **scoped observation**, not a configuration-altering command.

**Stage 1 — Identify where you are**

~~~sql
SELECT USER, SYS_CONTEXT('USERENV','CON_NAME') AS con_name
FROM dual;

SELECT instance_name, host_name, status
FROM v$instance;

SELECT name, cdb, open_mode, database_role
FROM v$database;
~~~

**Stage 2 — Identify containers if CDB**

~~~sql
-- Applicable only when CDB = YES and session holds appropriate privileges:
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
~~~

**Stage 3 — Read memory and processes**

~~~sql
SELECT name, ROUND(bytes / 1024 / 1024, 1) AS size_mb
FROM v$sgainfo
WHERE name IN ('Shared Pool Size', 'Buffer Cache Size', 'Redo Buffers');

SELECT name, value, unit
FROM v$pgastat
WHERE name IN ('total PGA allocated', 'total PGA inuse');

SELECT type, status, COUNT(*) AS sessions
FROM v$session
GROUP BY type, status;
~~~

**Stage 4 — Read locations of core files**

~~~sql
SELECT file#, name, status
FROM v$datafile
ORDER BY file#;

SELECT group#, thread#, status, archived
FROM v$log
ORDER BY thread#, group#;

SELECT group#, member
FROM v$logfile
ORDER BY group#, member;
~~~

**Stage 5 — Connect SQL workload to counters**

~~~sql
SELECT sql_id, executions, buffer_gets, disk_reads
FROM v$sqlarea
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 5 ROWS ONLY;
~~~

When recording results in a report, always include **timestamp**, **instance**, **container**, **database role**, and **query privileges/scope**. Two snapshots from different PDBs or different instances cannot be compared directly as if they were the exact same object.

## 9. Interpreting Real-World Scenarios

### Scenario A: Instance `OPEN` Yet Application Cannot Reach PDB

Observation:

~~~text
V$INSTANCE.STATUS      = OPEN
V$DATABASE.CDB         = YES
V$DATABASE.OPEN_MODE   = READ WRITE
V$PDBS: APPPDB         = MOUNTED
~~~

The instance and CDB are open, yet `APPPDB` is not yet open for normal operations. If the application connects to this PDB's service, check the PDB status and service registration next. These dynamic performance views **do not replace** checking the listener from the OS via `lsnrctl status` / `lsnrctl services` or testing an actual connection from the client machine.

### Scenario B: Sessions Increase Yet Processes Do Not Increase Proportionally

`V$SESSION` shows many sessions while process counts from `V$PROCESS` do not rise one-to-one. This can match shared server, multiplexing configurations, or how Oracle manages sessions/processes. Do not rush to assume the view is wrong or processes are leaking. First inspect the connection model and the instance/container scope of the metrics.

### Scenario C: `V$SGAINFO` Shows Large Buffer Cache Size Yet SQL Still Has Physical Reads

The buffer cache reduces datafile reads in suitable cases; it is not a guarantee that every needed block is always in cache. Cache size, working set, I/O strategy, query patterns, and data state all affect results. Inspect `V$SQLAREA` or related stats over the same time window before concluding.

### Scenario D: Redo Log Group Is `CURRENT` Yet Datafiles Do Not Change Immediately

`V$LOG` describes redo log groups; it does not show when every dirty data block has been written by DBWn to datafiles. Oracle uses write-ahead logging and recovery to decouple redo write timing from block write timing. Inspecting file metadata is not a direct gauge of a specific transaction's commit progress.

### Scenario E: Two People Query `V$SESSION` and Get Different Counts

Check whether they are connected to **the same instance**, in **the same container**, using identical filter predicates, and observing at **the same time**. Sessions arrive and depart continuously; connection pools create or close sessions. A single count discrepancy is not proof the database is malfunctioning.

## 10. Reasoning Boundaries to Remember

| Observed Result | Do Not Immediately Conclude |
|---|---|
| `V$INSTANCE.STATUS = OPEN` | All PDBs and services are reachable from clients |
| `V$DATABASE.OPEN_MODE = READ WRITE` | Every user has `INSERT` privilege or every PDB is `READ WRITE` |
| Large SGA in `V$SGAINFO` | All queries will avoid physical I/O |
| Many `ACTIVE` rows in `V$SESSION` | All sessions are burning CPU and the system is overloaded |
| One process row in `V$PROCESS` | Exactly one dedicated session always belongs to that process |
| Datafiles listed in `V$DATAFILE` | Exactly which block holds a given row or SQL data |
| `CURRENT` in `V$LOG` | All datafiles are synced after the most recent commit |
| SQL with high `DISK_READS` | That SQL is definitely the sole cause of a slow HTTP request |
| High `V$SYSSTAT.VALUE` | Load of 1 request without measuring time bounds and scope |
| `V$SERVICES` lists a service | Listeners from every network can reach that service |

Dynamic performance views are observation instruments, not automated conclusion engines. Statistics may be tracked per cursor or instance lifetime, reset on instance restart, change when cache entries age out, or vary in scope across CDB/PDB. Taking two timestamps, verifying scope, and cross-checking evidence across the relevant layers is far more reliable.

## 11. Practice Exercise: Diagramming a Live Oracle System

In an environment where observation is permitted, record the following facts:

1. Instance/host name and `STATUS` from `V$INSTANCE`. If RAC, record `INST_ID` from `GV$INSTANCE`.
2. Database name, `DATABASE_ROLE`, `OPEN_MODE`, and `CDB` from `V$DATABASE`.
3. Current container from `SYS_CONTEXT`. If CDB, list PDBs and `OPEN_MODE` from `V$PDBS` or `V$CONTAINERS`.
4. Buffer cache, shared pool, and redo buffers sizes from `V$SGAINFO`; PGA allocated/inuse from `V$PGASTAT`.
5. User session count, background session count, and several example `SID`s and associated process names from `V$SESSION` and `V$PROCESS`.
6. One tablespace with its datafile, one redo log group with its members, and control file path(s) from `V$DATAFILE`, `V$TABLESPACE`, `V$LOG`, `V$LOGFILE`, `V$CONTROLFILE`.
7. One `SQL_ID` present in `V$SQLAREA`; state `EXECUTIONS`, `BUFFER_GETS`, `DISK_READS`, and why one row cannot be treated as metrics solely for a single HTTP request.

From those observations, sketch:

~~~text
Database: <name>  |  Role: <role>  |  CDB: <YES/NO>
  Instance: <instance_name>@<host>  |  Status: <status>
    SGA: shared pool / buffer cache / redo buffers
    PGA: allocated / inuse
    Server processes <-> User sessions <-> SQL cursors
    Background processes: LGWR, DBWn, ...
  Container:
    Root (if CDB)
    PDB A: <open_mode>
    PDB B: <open_mode>
  Storage:
    Tablespace -> datafile
    Online redo group -> member(s)
    Control file(s)
~~~

Finally, answer using **view evidence**:

- Why do we say the SGA belongs to the instance while datafiles belong to the database storage layer?
- When `V$SESSION` shows a connection to a PDB, what evidence confirms the container?
- Why must `V$SQLAREA`, `V$SYSSTAT`, and `V$SESSION` be distinguished when analyzing workload?
- Can V$ views prove the listener is reachable from any arbitrary client host? If not, which layer must also be checked?
- If a PDB is `MOUNTED` while the CDB is `OPEN`, how should the diagram represent that?

## 12. Summary: From View Names to Architectural Literacy

Reading Oracle architecture via dynamic performance views bridges **system concepts** and **observable facts**:

~~~text
V$INSTANCE / GV$INSTANCE  -> instance, host, status, RAC
V$DATABASE               -> database, role, open mode, CDB
V$CONTAINERS / V$PDBS     -> containers and PDB status
V$SGAINFO / V$SGASTAT     -> shared SGA memory
V$PGASTAT                -> PGA memory
V$SESSION / V$PROCESS     -> logical connections and execution processes
V$BGPROCESS              -> background process groups
V$TABLESPACE / V$DATAFILE -> data organization on datafiles
V$LOG / V$LOGFILE        -> online redo log groups and members
V$CONTROLFILE            -> database control files
V$SQLAREA / V$SYSSTAT    -> SQL and workload statistics
V$SYSTEM_PARAMETER       -> active system configuration
~~~

A strong outcome from this exercise is an **architecture diagram anchored in live data**—including instance name, database, PDBs, process/session paths, memory regions, and storage files. When moving on to incident or performance analysis, always keep the same discipline: **pick the right view for the right layer, verify instance/container scope and timing, and draw only conclusions that the evidence genuinely supports**.
