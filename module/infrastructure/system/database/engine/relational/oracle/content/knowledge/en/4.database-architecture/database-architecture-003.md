# User Processes, Server Processes, and Background Processes in Oracle Database Architecture

When an application sends an SQL statement to Oracle Database, the application program does not open and read data files directly on its own. Instead, a **user process** submits the request; an Oracle **server process** receives and executes the request; and **background processes** maintain shared duties such as writing redo, writing modified data blocks, checkpointing, monitoring, and recovery.

Properly distinguishing these three process types explains why a `COMMIT` operation can complete before data is written to datafiles, why thousands of connected sessions do not necessarily mean thousands of server processes, and why a background process stopping can affect the entire instance.

This lesson examines relational Oracle Database architecture (especially the common Linux/Unix model). Process names, process counts, and how they appear in the operating system may vary by version, configuration, Oracle RAC, multitenant, and OS-thread execution mode.

## 1. Placing the Three Process Types in the Architectural Picture

An **Oracle Database** has two essential conceptual parts:

- **Database**: the physical files storing data and recovery information, including datafiles, control files, and online redo log files; plus tempfiles and related files depending on configuration.
- **Database instance**: the **System Global Area (SGA)** and **background processes** that manage, access, write to, and recover the database.

When an application interacts with Oracle, **user processes** and **server processes** operate above the instance to handle SQL requests. In an Oracle RAC system, multiple instances can access the same database; each instance has its own SGA and set of background processes.

### 1.1. Architectural Overview Diagram

```text
             CLIENT MACHINE / APPLICATION SERVER
        +--------------------------------+
        |  User process                  |
        |  SQL*Plus / SQLcl / JDBC app   |
        +----------------+---------------+
                         |
                         | SQL request / result
                         | Oracle Net or local connection
                         v
             ORACLE DATABASE SERVER
        +--------------------------------+
        |  Server process                |
        |  - receives request            |
        |  - parse / execute / fetch     |
        |  - uses private PGA            |
        +----------------+---------------+
                         |
                         v
        +--------------------------------+
        | ORACLE INSTANCE                |
        |                                |
        |  SGA:                          |
        |  - Shared Pool                 |
        |  - Database Buffer Cache       |
        |  - Redo Log Buffer             |
        |                                |
        |  Background processes:         |
        |  DBWn, LGWR, CKPT, PMON,       |
        |  SMON, LREG, ARCn, ...         |
        +---------+--------------+-------+
                  |              |
                  v              v
              Datafiles      Online redo
              Control files  Archive logs
```

The diagram illustrates roles; it does not imply every user process always has its own server process. That depends on the **dedicated server**, **shared server**, or **Database Resident Connection Pooling (DRCP)** model.

### 1.2. Quick Comparison Table

| Criterion | User process | Server process | Background process |
| --- | --- | --- | --- |
| Typical location | Client machine or application server; may also run on the database server | On the Oracle Database server | Within the Oracle instance environment |
| Created/managed by | Operating system and client program | Oracle infrastructure when handling connections, depending on server mode | Initialized/managed by Oracle for instance tasks |
| Primary role | Submits SQL commands, receives results | Executes requests from client sessions | Performs shared, foundational, and maintenance work |
| Represents a fixed database user? | Not necessarily: one application can open many sessions | Dedicated usually serves one connection; shared/pooled can serve multiple sessions sequentially | No: performs instance-wide work |
| Primary memory | Client/application process memory | Private **PGA**, while accessing shared **SGA** | Private PGA and required SGA access |
| Examples | `sqlplus`, Java application | Dedicated server process, shared server process | `LGWR`, `DBW0`, `CKPT`, `PMON` |

**Core point:** the three process types represent three processing roles. A **database user**, a **database session**, and an **OS process** are distinct concepts.

## 2. User Process: The Request-Originating Side

### 2.1. What Is a User Process?

A **user process** is the client-side application execution process interacting with Oracle Database. When a user opens SQL*Plus and runs `SELECT ...`, the SQL*Plus program is an intuitive example. For a Java application, the JVM process running the service can act as the user process and send SQL via JDBC.

Typical responsibilities:

1. Collect user input or execute business logic.
2. Connect to Oracle via a driver/client library.
3. Send SQL statements, bind variables, input data, and transaction requests.
4. Receive result rows, error messages, or execution status.
5. Display data, process further, or return responses to another application layer.

A user process **does not read datafiles itself, does not write instance redo logs itself**, and does not directly run the SQL engine inside the Oracle server. SQL execution is delegated to a server process and database components.

### 2.2. One Application Can Create Many Sessions

For example, a Java service receives 200 concurrent HTTP requests. This service may:

- run inside **one JVM process**;
- maintain **one connection pool** with 20 Oracle connections;
- use each connection to communicate with one or more database sessions depending on the client/pooling mechanism in place.

Therefore, **200 HTTP requests ≠ 200 user processes ≠ 200 Oracle sessions ≠ 200 server processes**.

The actual number of concurrent connections is determined by connection pool configuration, workload, Oracle server mode, and resource limits.

### 2.3. Remote Client or Same Host?

A user process can run:

- **Remotely**, such as a Java backend on an application server connecting to `db01.example.com:1521` over Oracle Net.
- **Locally**, such as SQL*Plus running directly on the database server and connecting to the instance.

Client location only determines the communication path. Even on the same host, the SQL*Plus program is still a **user process**, while Oracle's server process still performs database-side execution.

## 3. Server Process: The SQL-Executing Side

### 3.1. What Does a Server Process Do?

A **server process** is the Oracle process serving requests from a client. Its main tasks include:

- Receiving requests from the user process over the established connection.
- Checking session context, privileges, and transaction state.
- **Parse SQL**: check syntax/semantics and locate or build an execution plan (along with associated structures in the shared pool).
- **Execute**: carry out the execution plan, accessing blocks in the database buffer cache or reading needed blocks from datafiles via Oracle's mechanisms.
- Perform DML operations, managing changes in the buffer cache, undo, and redo.
- **Fetch** and return result rows to the client, or return statement status/errors.

A server process is not a database user: it **executes under the session context and privileges of a database user**. In the shared server model, the same server process can sequentially serve requests belonging to different sessions.

### 3.2. How Does a Server Process Use PGA and SGA?

- **Program Global Area (PGA)**: private memory belonging to an Oracle process; holds work areas and state needed, for example, for sort/hash operations depending on the execution plan. Other processes do not access PGA as a shared common region.
- **SGA**: the instance's shared memory area; server processes access components such as the **shared pool**, **database buffer cache**, and **redo log buffer**.

An example of reading data:

```text
Server process
   |
   +-- Look up SQL/cursor in Shared Pool
   |
   +-- Look up target blocks in Database Buffer Cache
   |      |
   |      +-- Block found: read from cache
   |      |
   |      +-- Not found: perform appropriate I/O to retrieve block
   |
   +-- Process filter predicates, expressions, sorting...
   |
   +-- Return result rows to the user process
```

Not all queried data must pass through the buffer cache in the exact same way. Oracle can use access strategies such as **direct path read**, parallel execution, and other optimizations. The goal of the diagram is to distinguish roles, not restrict every execution plan to a single I/O path.

### 3.3. Dedicated Server: One Process Serving One Connection

In the **dedicated server** model, one client connection typically has **one dedicated server process** serving consecutive requests for the lifetime of the connection.

```text
User process A  <------>  Dedicated server A  ---+
                                                |
User process B  <------>  Dedicated server B  ---+--> SGA / Database
                                                |
User process C  <------>  Dedicated server C  ---+
```

The advantage is a straightforward execution path, well suited to many workloads and operations requiring a dedicated server process serving a session continuously. In return, if many connections remain open and idle, memory and resources consumed by server processes can grow significantly.

Normally, one dedicated connection uses one dedicated server process in Oracle; however, user process count, connection count, session count, and OS process count do not always match one-to-one across all drivers or pooling mechanisms.

### 3.4. Shared Server: Multiple Sessions Sharing a Pool of Server Processes

In the **shared server** model (also called Multi-Threaded Server in older documentation), Oracle uses **dispatcher processes** and **shared server processes**.

```text
Client A ----\
Client B -----+----> Dispatcher(s)
Client C ----/           |
                         v
                 Request queue in SGA
                         |
                  +------+------+
                  |             |
            Shared server S0  Shared server S1
                  |             |
                  +------+------+
                         |
                 Response / dispatcher
                         |
                       Client
```

A shared server handles one request for a session and can then serve a request from another session. This model fits scenarios with many concurrent sessions where not all sessions are continuously active. To preserve session state when requests are handled by different servers, the **UGA (User Global Area)** resides in the instance's shared memory—typically in the **large pool** if configured, or in the **shared pool** depending on configuration.

You should not assume shared server is always faster than dedicated. Shared server incurs dispatcher/queue overhead and requires evaluating workload characteristics, concurrency levels, feature compatibility requirements, and memory sizing.

### 3.5. Database Resident Connection Pooling (DRCP)

**DRCP** is an Oracle Database-side pooling mechanism allowing clients/connections to reuse a pool of server processes resident in the database according to pool policy. This is useful for many short-lived connections or applications using DRCP-compatible pooling.

Three concepts should be kept distinct:

- **Application connection pool**: application-side software holding and reusing connections (e.g., HikariCP in Java).
- **Shared server**: multiple sessions served through dispatchers and a pool of shared servers.
- **DRCP**: a database-side pool of server processes, supported and configured appropriately by the client.

They address similar connection-resource challenges, yet their mechanisms and configuration requirements differ. Do not call every form of "pool" shared server.

## 4. Background Process: The Instance's Background Processes

Oracle's **background processes** perform work that, if left to each server process independently, would make ensuring instance-wide consistency, recoverability, or performance difficult.

Some processes typically run continuously; others appear only when a feature is enabled or corresponding workload occurs. The exact list varies by release and configuration.

### 4.1. Core Background Processes

| Process | Full Name / Role | Primary Responsibility | Common Misconception |
| --- | --- | --- | --- |
| **DBWn**, commonly `DBW0` | Database Writer | Writes **dirty buffers** from the database buffer cache down to **datafiles**. Multiple database writers may exist. | Not the process that confirms every `COMMIT`. |
| **LGWR** | Log Writer | Writes **redo** data from the redo log buffer into **online redo log files**, especially when securing commits. | LGWR is not the process that writes data blocks directly to datafiles. |
| **CKPT** | Checkpoint | Coordinates/signals checkpoints; updates checkpoint information in the **control file** and datafile headers. | CKPT does **not** write all dirty data blocks itself; DBWn handles that. |
| **SMON** | System Monitor | Performs/coordinates instance-level recovery and cleanup tasks, including instance recovery work. | Not a server process running SQL statements on behalf of users. |
| **PMON** | Process Monitor | Monitors Oracle processes and assists with cleanup when user/server processes fail; may coordinate with cleanup helpers depending on release. | Should not be viewed as a tool that fixes application bugs. |

**DBWn naming:** the letter `n` represents the sequence number of the database writer; in live systems you may see `DBW0`, `DBW1`, etc. Documentation sometimes uses the general name **DBWR**. They refer to the same data-buffer writing function.

### 4.2. Other Frequently Encountered Background Processes

| Process | Role | When to Pay Attention? |
| --- | --- | --- |
| **ARCn** / `ARC0`, `ARC1` | Archiver: copies filled/archivable online redo logs into archived redo logs per the archive mechanism. | Backup/recovery, ARCHIVELOG mode, Data Guard. |
| **LREG** | Listener Registration: registers service/instance information with the listener. | When services are not yet recognized by the listener or Oracle Net connection errors occur. |
| **MMON**, **MMNL** | Collects/coordinates performance management data and various monitoring tasks. | Operations, performance diagnostics, appropriately licensed management features. |
| **RECO** | Recoverer: resolves in-doubt distributed transactions. | Distributed transactions or database links involved in transactions. |
| **CJQ0**, **Jnnn** | Job coordinator and job slaves. | When running scheduler jobs and background tasks. |
| **QMNC** and related processes | Queue coordination functions in appropriate configurations. | When using related queuing / Advanced Queuing mechanisms. |

Not every system has all of these processes. For example, **ARCn** and archiving depend on database configuration; processes for Data Guard, RAC, parallel query, ASM, or other features have their own specialized roles.

Processes named starting with `P...` are **parallel execution server processes** spawned by Oracle to execute SQL in parallel. They are SQL execution workers; do not automatically equate them with `LGWR` or `DBWn` simply because you see them in an OS process list.

### 4.3. Why Are Multiple Background Processes Needed?

Oracle separates work by role so individual clients do not have to decide when to write logs, checkpoint, or recover:

- **LGWR** optimizes redo writes and can group commit requests across multiple transactions (group commit).
- **DBWn** manages dirty buffer writes based on buffer cache/checkpoint conditions without blocking every transaction until datafiles are written.
- **CKPT** coordinates determining checkpoint progress and recording appropriate checkpoint information.
- **SMON/PMON** enable recovery or cleanup even after a user process has disappeared.
- **LREG** keeps the listener informed of the services advertised by the instance.

This design separates the **SQL execution path** from the **work needed for stable instance operation**.

## 5. Lifecycle of a SELECT Statement

Suppose a Java application calls:

```sql
SELECT employee_id, full_name
FROM   employees
WHERE  department_id = :dept_id;
```

Simplified processing flow:

1. **User process:** the application binds a value to `:dept_id` and sends the SQL via JDBC.
2. **Establishing the connection path:** Oracle Net and the listener help route the client to the appropriate database service and server process. In a normal connection path, **the listener is not an SQL-executing process** and does not sit in the execution path of every SQL statement after the connection is established.
3. **Server process:** receives the request, parses or reuses a cursor, verifies table privileges, and determines the data access method.
4. **SGA / storage:** the server process uses the shared pool, database buffer cache, or an appropriate read path to retrieve data.
5. **Server process:** evaluates filters, expressions, joins, or sorts if any; sends result rows to the client across one or more fetches.
6. **User process:** reads result rows and maps them into Java objects or displays them in the UI.

```text
JDBC application  -->  server process  -->  shared pool / data
      ^                    |
      +------ rows --------+
```

A standard `SELECT` statement **does not require LGWR to write a commit record for the read operation itself**. Background processes continue running for the instance as a whole and may serve many other tasks concurrently.

## 6. Lifecycle of UPDATE and COMMIT: How LGWR Differs from DBWn

Consider a simple transaction:

```sql
UPDATE accounts
SET    balance = balance - 100
WHERE  account_id = 101;

UPDATE accounts
SET    balance = balance + 100
WHERE  account_id = 202;

COMMIT;
```

Assuming the tables exist and the statements succeed, the underlying processing is as follows:

### 6.1. During UPDATE Execution

The **user process** sends the SQL. The **server process** checks privileges, locates the target rows, and updates the relevant database buffers; at the same time, Oracle generates **undo** information to support rollback and read consistency, as well as **redo** for recoverable changes.

Redo is generated within transaction processing and placed into the **redo log buffer** in the SGA; data modifications are managed in the relevant buffers. Generating redo/undo does not mean datafiles have already been written at the exact moment `UPDATE` runs.

### 6.2. During COMMIT Execution

Under standard synchronous commit mode, Oracle writes a commit record and **LGWR ensures the required redo has been written to online redo logs** before returning commit success. This is a key part of **durability**.

**DBWn may write dirty data buffers before or after commit time**, depending on buffer cache activity, checkpoints, and resources. Oracle enforces **write-ahead logging**: relevant redo must be appropriately secured before a dirty data block is written down to a datafile.

Therefore:

> **A successful `COMMIT` does not mean every data block has already been written by DBWn to a datafile.** With standard synchronous commit, recoverability relies on redo durably written by LGWR.

Oracle supports asynchronous/`NOWAIT` commit modes in certain situations; those modes have different durability characteristics. This lesson uses the default synchronous commit behavior as the primary model.

### 6.3. An Illustrative Timeline

```text
Time       User process / Server process           Background process / I/O
---------  --------------------------------------  ---------------------------------------
T1         Send UPDATE                             --
T2         Modify buffer, generate undo and redo   --
T3         Send COMMIT                             LGWR writes redo and commit record
T4         Receive "Commit complete"               Redo is durable under standard commit
T5         Read new data in another transaction    DBWn may write dirty buffers to datafile
T6         --                                      CKPT updates checkpoint info
```

Background steps can overlap; the timeline does not enforce a strict chronological ordering between every DBWn buffer write and every SQL statement. Its primary purpose is to distinguish **writing redo** from **writing datafiles**.

## 7. What Happens When a Process Fails?

### 7.1. User Process or Dedicated Server Process Is Disconnected

Suppose a user abruptly closes an application or the network drops. The database session may remain for a while until Oracle detects the disconnect or process failure.

Through session management, Oracle can:

- detect that the session/connection is no longer valid;
- reclaim associated resources and locks according to rules;
- roll back uncommitted transactions;
- clean up the session and process, involving appropriate monitoring/cleanup components.

You should not rely on closing a terminal window to guarantee whether a transaction was `COMMIT`ted or `ROLLBACK`ed. Transaction state depends on whether the corresponding statement actually completed.

### 7.2. Instance Crash

When an instance stops abnormally, recent changes may already exist in redo logs without having been fully written by DBWn to datafiles. When the instance restarts, Oracle uses information in redo/undo and checkpoint metadata to perform **instance recovery**.

Conceptual view:

```text
Before crash:
  Online redo log:  [changes durably recorded]
  Datafiles:        [may not yet contain all recent changes]

Restart:
  Read required checkpoint / redo information
      |
      +-- Roll forward changes from redo
      |
      +-- Roll back uncommitted transactions
      |
      +-- Restore database to a consistent state
```

Oracle manages this recovery through its instance recovery mechanism, involving appropriate processes such as SMON and recovery workers depending on configuration. This is also why a transaction's **COMMIT** does not need to wait for all datafiles to be updated immediately.

### 7.3. Essential Background Process Fails

Processes such as LGWR and DBWn play essential roles in safe instance operation. If a critical background process fails or can no longer function, Oracle may terminate the instance to protect consistency. This differs from a single user process losing its connection.

Do not conclude "seeing a process idle in a `top` snapshot means it is broken": many healthy background processes spend most of their time waiting on events until work arrives.

## 8. Session, Connection, Process, and Thread: Not Interchangeable

These concepts are related yet distinct:

| Concept | Description | Example |
| --- | --- | --- |
| **Connection** | Physical/logical communication channel between client and database service. | A TCP connection from an application to Oracle. |
| **Session** | Login and working state inside Oracle: user, privileges, transaction, NLS/context, etc. | A row corresponding to the session in `V$SESSION`. |
| **User process** | Client-side application process. | JVM, SQL*Plus. |
| **Server process** | Oracle process serving SQL statements for a session. | Dedicated server or shared server. |
| **Background process** | Process performing shared duties for the Oracle instance. | LGWR, DBW0. |
| **OS thread** | Operating system execution unit; Oracle can use multiple threads within one OS process depending on platform/configuration. | One process hosting multiple Oracle threads. |

In a simple dedicated model, one session is bound to one dedicated server process. In shared server or DRCP, that relationship is no longer one-to-one in that way.

On certain platforms/configurations, Oracle can run tasks as **threads** (for example when using threaded execution). Thus, when looking at Task Manager, `ps`, or `top`, do not equate the number of **OS PIDs** with the number of **Oracle sessions** or logical processes reported by Oracle.

### 8.1. Active, Inactive, and Waiting

In `V$SESSION`:

- `STATUS='ACTIVE'` indicates the session is currently executing a database call, though not necessarily consuming CPU; it may be **WAITING** on I/O, a lock, or another event.
- `STATUS='INACTIVE'` is typically a connected session with no database call currently executing.
- A server process can remain present or wait while the client is idle/not sending new statements.

You cannot determine a "broken process" solely from an `ACTIVE` or `INACTIVE` label or low instantaneous CPU. Wait times, wait events, execution progress, and workload must all be evaluated together.

## 9. Hands-On Observation Using Dynamic Performance Views

The following examples are **read-only queries**. The account needs appropriate privileges on `V$` views; insufficient privileges may result in `ORA-00942` or access errors. Do not grant broad administrative privileges solely to test a query.

### 9.1. Checking the Instance

```sql
SELECT instance_name,
       host_name,
       status
FROM   v$instance;
```

The returned row identifies the current instance. A CDB with multiple PDBs can share that instance; the instance name is not the name of each individual PDB.

### 9.2. Observing Sessions and Associated Server Processes

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.server,
       s.machine,
       s.program AS client_program,
       s.process AS client_os_process,
       p.spid    AS oracle_os_process,
       p.pname   AS oracle_process_name
FROM   v$session s
LEFT JOIN v$process p
       ON p.addr = s.paddr
WHERE  s.type = 'USER'
AND    s.username IS NOT NULL
ORDER  BY s.sid;
```

Notable columns:

- `SID` and `SERIAL#`: together help identify the session at query time.
- `USERNAME`: the session's database user; distinct from OS process names.
- `SERVER`: server type serving the session; possible values include `DEDICATED`, `SHARED`, `POOLED`, depending on configuration.
- `MACHINE` and `CLIENT_PROGRAM`: client information captured/reported by Oracle.
- `CLIENT_OS_PROCESS`: client-side process identifier provided by the session.
- `ORACLE_OS_PROCESS`: Oracle-side OS process ID via `V$PROCESS.SPID`.

**Note:** with shared/pooled servers, the association between a session and an Oracle server process can change over time as requests are processed. In threaded execution configurations, `SPID` alone may not uniquely identify an execution unit; Oracle also provides fields such as `STID`/`SOSID` depending on version and platform. Consult the column definitions for your release.

### 9.3. Viewing Present Oracle Processes and Background Processes

```sql
SELECT spid,
       pname,
       program
FROM   v$process
WHERE  pname IS NOT NULL
ORDER  BY pname;
```

`PNAME` helps identify many background processes with names such as `PMON`, `SMON`, `LGWR`, `DBW0`, `CKPT`, and `LREG`. Actual process names and counts differ across systems.

Process descriptions can be viewed from a dedicated view:

```sql
SELECT name,
       description
FROM   v$bgprocess
WHERE  name IN ('PMON', 'SMON', 'DBW0', 'LGWR', 'CKPT', 'LREG', 'ARC0')
ORDER  BY name;
```

`V$BGPROCESS` contains background process information/definitions; a row appearing there should not be taken as sole proof that the process is currently healthy. To verify live or failed processes, combine `V$PROCESS`, instance status, alert log, and OS tools.

### 9.4. Monitoring Session/Process Limits

```sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM   v$resource_limit
WHERE  resource_name IN ('processes', 'sessions')
ORDER  BY resource_name;
```

Purpose:

- `CURRENT_UTILIZATION`: resources currently in use at observation time.
- `MAX_UTILIZATION`: peak recorded over the corresponding statistics lifetime.
- `LIMIT_VALUE`: limit reported by Oracle for the resource.

If application connection counts grow too rapidly, these values help identify resource limits. Do not arbitrarily raise `PROCESSES` or `SESSIONS` parameters before understanding connection leaks, pooling, and memory impact.

### 9.5. One Way to Observe an Active Session

Open **two SQL*Plus windows** using a practice account with appropriate privileges.

Window A:

```sql
SELECT sys_context('USERENV', 'SID')         AS my_sid,
       sys_context('USERENV', 'SESSION_USER') AS my_user
FROM   dual;
```

Window B (using an account authorized to read `V$SESSION`):

```sql
SELECT sid,
       serial#,
       username,
       status,
       server,
       program
FROM   v$session
WHERE  sid = :sid_from_window_a;
```

In Window B, supply the actual SID value from Window A for the `:sid_from_window_a` bind variable using the input syntax supported by your tool. Try observing while A is running a query and while A is idle to see the session status change. Keep in mind: a very fast query will not easily be caught in the `ACTIVE` state by a single poll.

## 10. Relationship to Listener, RAC, and CDB/PDB

### 10.1. Listener Is Not an SQL-Executing Server Process

The **Oracle Net Listener** typically helps clients locate and establish connections to the appropriate database service/server. The listener may coordinate with related processes depending on dedicated/shared mode, RAC, and connection method.

Once a connection is established in the standard way, the **server process** is the unit that processes SQL. The listener does not replace a server process to parse `SELECT` or write transaction data.

In shared server architecture, **dispatchers** receive/forward client requests and place them on the queue for shared servers. A dispatcher is a process belonging to Oracle's shared server mechanism, distinct from both the listener and worker server processes.

### 10.2. Oracle RAC

With **Real Application Clusters (RAC)**, multiple **instances** can concurrently open/access one database:

```text
        Oracle RAC — one shared database
        +-------------------------------+
        |          Database             |
        |  Datafiles / Control / Redo   |
        +---------------+---------------+
                        ^
                +-------+-------+
                |               |
          Instance 1         Instance 2
          Separate SGA       Separate SGA
          LGWR/DBWn/...      LGWR/DBWn/...
          Server processes   Server processes
```

Each instance has its own background processes and memory to process workload. In RAC, Oracle also has processes for coordinating caches, locks, and resources across instances.

To inspect sessions/processes across the cluster, administrators can use **`GV$` views**, such as `GV$SESSION` and `GV$PROCESS`, which include `INST_ID` to distinguish instances.

### 10.3. Oracle Multitenant: CDB and PDB

In the **CDB/PDB** model, one CDB instance serves multiple **pluggable databases (PDBs)**:

- A PDB **does not automatically have a separate complete set of LGWR, DBWn, PMON, and SGA** like an independent instance.
- Clients typically connect to a PDB via the PDB's **database service**.
- Server processes execute SQL under the appropriate container/session context.
- Background processes belonging to the instance perform necessary work for the containers' data.

There are specialized deployment architectures or multitenant features with different process behavior; when analyzing a real system, verify against the exact version and configuration. In the foundational learning model, **a PDB is a logical database container, not an independent instance**.

## 11. Interpreting Performance and Operational Symptoms

| Symptom | Potentially Related To | Verify Before Concluding |
| --- | --- | --- |
| Very many open connections yet little SQL running | Connection pools, dedicated processes, idle sessions | `V$SESSION` / `V$PROCESS` counts, session states, pool configuration |
| Application reports hitting process/session limits | Server process count, connection leak, or limit settings | `V$RESOURCE_LIMIT`, `PROCESSES`, `SESSIONS`, pool, DRCP/shared server |
| `COMMIT` takes a long time | LGWR redo writes and storage, contention, or other causes | Relevant wait events, redo I/O, concurrent workload |
| Many dirty buffers exist | DML workload, DBWn write rate, checkpoint pressure | Buffer cache metrics, storage I/O, and appropriate diagnostics |
| Listener is running yet clients cannot reach service | Service registration, database/PDB state, or network policy | `LREG`, listener services, service name, logs |
| Application process terminated yet session remains in database | Disconnect detection timing, timeouts, cleanup | Session status, timeouts/client heartbeats, error history |
| Oracle server CPU busy while client does little | Running SQL, parallel execution, background workloads | `V$SESSION`, Oracle processes, SQL ID, jobs, wait events |

Do not blame every slow `COMMIT` on DBWn or every slow query on LGWR. An SQL statement can wait on CPU, I/O, locks, network, parsing, latches, log sync, and many other conditions. Distinguish whether a server process is **working**, **waiting on an event**, or **being scheduled**.

### 11.1. When to Consider Shared Server or DRCP?

Consider them when an application has **many concurrent connections**, mostly idle, inflating server processes and resource consumption. Measure the workload, test application/driver compatibility, and monitor corresponding queues/latencies.

An application with 20 connections reused efficiently in an application pool will not necessarily benefit from immediately switching to shared server. Changing connection models should be driven by **observed resource bottlenecks** rather than total user count.

### 11.2. Why User Processes Must Not Touch Datafiles

Database files are managed under Oracle's internal mechanisms; internal processes keep redo/undo, locking, caching, and checkpoints synchronized. An application must never write directly to datafiles like ordinary text files: doing so bypasses the database's consistency and recovery guarantees.

## 12. Common Misconceptions

**Misconception 1: "One database user is one OS process."**  
Incorrect. One database user can have multiple sessions; one application process can use multiple connections; one server process can serve multiple sessions over time in shared/pooled mode.

**Misconception 2: "DBWn writes datafiles immediately when a user issues COMMIT."**  
Incorrect. LGWR is the critical component for writing redo during synchronous commits. DBWn writes dirty buffers to datafiles based on database buffer cache/checkpoint activity.

**Misconception 3: "CKPT performs the dirty buffer writes."**  
Incorrect. CKPT coordinates checkpoints and updates checkpoint information; DBWn is responsible for writing data buffers from cache down to datafiles.

**Misconception 4: "The listener executes SQL statements."**  
Incorrect. The listener primarily handles connection establishment/routing. SQL is processed by a server process using the SGA and other Oracle components.

**Misconception 5: "Background processes only run when a client logs in."**  
Incorrect. Background processes are part of the instance, and many continue operating even when no application sessions are active.

**Misconception 6: "An INACTIVE session means disconnected."**  
Incorrect. It is usually a still-connected session not currently executing a database call.

**Misconception 7: "Each PDB has its own separate LGWR."**  
Incorrect in standard CDB/PDB architecture. PDBs share the instance and many instance components, including the set of background processes.

## 13. Self-Check Exercises

### Scenario 1: Java Application

A Java service has one JVM process using a connection pool with a maximum of 30 connections. When 200 HTTP requests arrive, the dev team claims there must be 200 dedicated server processes on Oracle. Is that claim necessarily true?

**Hint:** No. HTTP requests do not equate to Oracle connections/sessions/processes; the connection pool limits the connections opened by the application, and dedicated/shared/DRCP mode also determines how server processes are allocated.

### Scenario 2: COMMIT and Datafiles

An `UPDATE` transaction followed by `COMMIT` succeeds. A DBA observes that datafiles do not yet contain all new dirty blocks at that moment. Was the transaction unsafe?

**Hint:** Not enough evidence to conclude that. With standard synchronous commit, redo is durably written by LGWR for recovery; DBWn can write dirty buffers back to datafiles afterward.

### Scenario 3: Assigning Process Roles

Assign roles to these operations:

1. JDBC sends `SELECT`.
2. Oracle parses SQL, checks privileges, runs the execution plan.
3. Writes redo to the online redo log.
4. Writes dirty buffers to datafiles.
5. Updates checkpoint information.
6. Manages recovery tasks after an instance failure.

**Answer:** (1) user process; (2) server process; (3) LGWR; (4) DBWn; (5) CKPT; (6) the instance recovery mechanism, in which SMON and appropriate recovery processes play roles.

### Scenario 4: Shared Server

A system has 4,000 sessions, mostly idle, and uses shared server. Can we conclude there are 4,000 shared server OS processes?

**Hint:** No. Sessions share a pool of shared server processes, with dispatchers and queues distributing requests. Actual pool size depends on configuration and load.

### Scenario 5: Observing Data

In `V$SESSION`, a session has `STATUS='ACTIVE'`, yet process CPU does not rise. Is that necessarily abnormal?

**Hint:** No. The session may be waiting on I/O, locks, network, or another event. Check wait events and workload context to evaluate.

## 14. Oracle Documentation for Further Reading

- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): database/instance architecture, memory, processes, and background processes.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): definitions of `V$SESSION`, `V$PROCESS`, `V$BGPROCESS`, `V$RESOURCE_LIMIT`, and related parameters.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): instance administration, server configuration, recovery, and operations.
- [Oracle Database Net Services Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/): listener, services, dedicated/shared server connections.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): SQL execution and related performance aspects.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): Java clients, drivers, connections, and Oracle interaction mechanisms.

When analyzing an SQL request, trace it through: **user process submits request → server process executes using PGA/SGA → background processes maintain redo, datafiles, checkpoints, and instance → results return to client**. Clearly separating this processing flow helps you read system state, explain transactions, and pinpoint the right root-cause layer when incidents arise.
