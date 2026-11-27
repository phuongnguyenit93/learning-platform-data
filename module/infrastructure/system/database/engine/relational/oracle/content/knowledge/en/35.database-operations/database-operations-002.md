# SHUTDOWN NORMAL, TRANSACTIONAL, IMMEDIATE, and ABORT

Oracle Database provides several shutdown modes so DBAs can choose how to terminate instance activity. The four common modes are NORMAL, TRANSACTIONAL, IMMEDIATE, and ABORT. They differ in how they handle connected sessions, active transactions, incomplete SQL statements, and recovery work on restart.

Choosing the wrong shutdown mode can cause maintenance to wait indefinitely, interrupt application transactions, or force instance recovery on the next startup. Therefore, DBAs must understand the exact waiting behavior, rollback handling, and database state after each mode. Shutdown is also an operational action: it must be coordinated with applications, connection pools, schedulers, RAC/Clusterware, and Data Guard if used.

After this lesson, you will be able to:

- Distinguish the behavior of SHUTDOWN NORMAL, TRANSACTIONAL, IMMEDIATE, and ABORT.
- Choose a mode based on transaction preservation requirements and downtime constraints.
- Understand what happens to sessions, SQL statements, and uncommitted transactions.
- Explain why NORMAL/TRANSACTIONAL can wait for a long time.
- Distinguish rollback during immediate shutdown from instance recovery after abort.
- Connect with administrative privileges and execute shutdown using proper syntax.
- Inspect sessions, transactions, and instance state before shutting down.
- Monitor a waiting shutdown and handle blockers.
- Plan shutdown/startup for single instance, RAC, and CDB/PDB.
- Understand impacts on application services, scheduled jobs, listeners, and Data Guard.
- Diagnose common errors and build a controlled runbook.

> Examples use SQL*Plus/SQLcl and a standard Oracle instance. Privileges, detailed syntax, and the behavior of some options may depend on the release/platform. In RAC and Oracle Restart/Clusterware environments, use resource management tools such as SRVCTL according to your system runbook.

## 1. What Is Shutdown?

### 1.1. Instance and Database

An Oracle instance consists of the SGA and background processes. A database consists of physical files such as datafiles, control files, and online redo logs. During a clean shutdown, Oracle terminates instance activity, closes the database, dismounts the database from the instance, and stops the background processes.

Shutdown ABORT terminates the instance immediately without performing the full clean close sequence. The database will require instance recovery at the next startup.

### 1.2. Main States

An instance/database typically transitions through these states:

```text
STARTUP NOMOUNT
    |
    v
MOUNT
    |
    v
OPEN
    |
    v
SHUTDOWN
```

- NOMOUNT: the instance has started and read the parameter file; SGA/processes are created.
- MOUNT: the control file is opened and the database is mounted.
- OPEN: datafiles and online redo logs are opened; the database serves access according to its mode.
- SHUTDOWN: the instance has stopped.

### 1.3. Clean Shutdown vs. Abort

NORMAL, TRANSACTIONAL, and IMMEDIATE are clean shutdown modes: Oracle executes a sequence to conclude transactions/sessions according to the mode, then closes the database and stops the instance.

ABORT is an unclean shutdown: Oracle stops the instance without waiting for sessions, without rolling back open transactions like IMMEDIATE, and without closing the database through the normal sequence. Recovery will be performed at the subsequent startup.

### 1.4. Shutdown Does Not Mean Powering Off the Server

SHUTDOWN stops an Oracle instance. It does not shut down the OS, does not automatically stop all listeners, does not stop other instances on the host, and does not replace procedures for stopping applications/Clusterware/ASM.

If the host runs multiple databases or ASM, you must identify the exact target instance and dependency order before taking action.

## 2. SHUTDOWN Syntax

### 2.1. Basic Syntax

In SQL*Plus or SQLcl:

```sql
SHUTDOWN NORMAL
SHUTDOWN TRANSACTIONAL
SHUTDOWN IMMEDIATE
SHUTDOWN ABORT
```

If you enter SHUTDOWN without a mode, the default is NORMAL.

### 2.2. SHUTDOWN Is a Client Command

SHUTDOWN is a SQL*Plus/SQLcl command, not a SQL DML/DDL statement to run inside a PL/SQL block. Do not place it inside BEGIN ... END.

Example of an administrative connection on the host using OS authentication:

```sql
sqlplus / as sysdba
SHUTDOWN IMMEDIATE
```

Or connect via a DBA-granted administrative authentication method. Do not put the SYS password into scripts, shell history, or logs.

### 2.3. Required Privileges

Shutdown requires an administrative connection with appropriate privileges, usually SYSDBA or SYSOPER; other administrative privileges may be supported depending on the release. Use organization-issued accounts/privileges and follow access control policies.

Normal application accounts are not permitted to shut down an instance. Do not grant SYSDBA to an application just to perform operational tasks.

### 2.4. Do Not Confuse SHUTDOWN with ALTER DATABASE CLOSE

ALTER DATABASE CLOSE closes the database but does not necessarily stop the instance. SHUTDOWN ends both the database lifecycle and the instance. In your runbook, choose the exact operation for your goal: closing the database, transitioning states, or stopping the entire instance.

### 2.5. Identify the Instance Before Shutdown

After connecting, check:

```sql
SELECT
    instance_name,
    host_name,
    status,
    database_status,
    startup_time
FROM v$instance;

SELECT
    name,
    open_mode,
    database_role
FROM v$database;
```

On RAC, check across the cluster via GV$INSTANCE and use SRVCTL to identify the exact instance/resource to stop.

## 3. Comparing the Four Shutdown Modes

### 3.1. Overview Table

| Behavior | NORMAL | TRANSACTIONAL | IMMEDIATE | ABORT |
| --- | --- | --- | --- | --- |
| Prevents new connections | Yes | Yes | Yes | Instance stops immediately |
| Prevents new transactions | Not via a dedicated drain mechanism; connected sessions stay active | Yes | Yes | Does not wait |
| Waits for users to disconnect | Yes | No; after transactions finish Oracle disconnects clients | No | No |
| Waits for current transactions to finish | Waits for user/session to finish on its own | Yes | No; rolls back uncommitted transactions | No |
| Cancels running SQL | Not in an immediate way | Waits for transactions to complete | Yes | Stops processes/instance |
| Rolls back uncommitted transactions | Depends on user ending session and disconnect behavior | Transactions are completed by client before disconnect | Oracle rolls back | No clean rollback during shutdown |
| Clean shutdown | Yes | Yes | Yes | No |
| Instance recovery at next startup | Not needed due to shutdown mode | Not needed due to shutdown mode | Not needed due to shutdown mode | Yes |

### 3.2. Mnemonic

- NORMAL: wait for all users to leave the database on their own.
- TRANSACTIONAL: block new transactions, wait for current transactions to finish, then disconnect clients.
- IMMEDIATE: disconnect clients and roll back uncommitted transactions.
- ABORT: stop immediately, recover at the next startup.

### 3.3. Choosing Based on Operational Goal

| Goal | Typically Suitable Mode |
| --- | --- |
| Wait for applications to end all sessions cleanly on their own | NORMAL |
| Let active transactions complete without accepting new transactions | TRANSACTIONAL |
| Need to stop service within a reasonable time, accepting rollback of uncommitted transactions | IMMEDIATE |
| Instance cannot shut down cleanly or requires emergency stop | ABORT |

This is a selection guideline, not a replacement for a runbook. For applications with financial or distributed transactions, understand transaction boundaries and coordinate with the application owner before selecting a mode.

## 4. SHUTDOWN NORMAL

### 4.1. Behavior

NORMAL is the default mode if no mode is specified. Oracle prevents new connections and waits for all currently connected users to disconnect normally. The shutdown command only completes after all existing sessions leave the database.

Oracle does not automatically disconnect active users to finish shutdown as IMMEDIATE does. An idle session, a connection pool holding connections, or an application forgetting to close connections can make shutdown wait indefinitely.

### 4.2. Open Transactions

With NORMAL, sessions can continue operating and commit/roll back transactions according to application logic, then disconnect. Oracle waits for sessions to end rather than automatically rolling back all transactions upon receiving the shutdown command.

If a user does not disconnect, shutdown keeps waiting. Therefore, NORMAL is suitable when the DBA wants applications to close sessions naturally and can control when clients leave.

### 4.3. Example

```sql
SHUTDOWN NORMAL
```

If any user session remains connected, the command will not return the prompt yet. The DBA must identify remaining sessions and coordinate their disconnection.

### 4.4. When to Use?

- Lab environments or maintenance with few sessions.
- Systems with a clear connection draining process.
- Wanting applications to finish work and close sessions on their own.
- Downtime is not tightly constrained.

### 4.5. Risks

- Can wait a very long time due to idle sessions.
- Connection pools can hold open connections even without running SQL.
- Application background jobs/sessions may not disconnect automatically.
- DBAs might mistake shutdown for hanging when Oracle is simply waiting for clients.

If the maintenance window is limited, NORMAL is usually not a practical choice for systems with many hard-to-control sessions.

## 5. SHUTDOWN TRANSACTIONAL

### 5.1. Behavior

TRANSACTIONAL prevents users from starting new transactions and waits for currently active transactions to finish. Once a transaction finishes, Oracle disconnects the client/session and proceeds with shutdown.

The goal is to give active transactions an opportunity to commit or roll back per application logic while preventing new transactions from starting during the drain phase.

### 5.2. Differences from NORMAL

NORMAL waits for every session to disconnect, including sessions with no active transaction that still hold a connection.

TRANSACTIONAL focuses on transactions: it waits for current transactions to finish, then Oracle disconnects the clients. Idle sessions with no active transaction do not force waiting for the user to close the connection as in NORMAL.

### 5.3. Differences from IMMEDIATE

TRANSACTIONAL does not proactively roll back active transactions just to shut down quickly. It waits for transactions to finish. IMMEDIATE cancels running SQL and rolls back uncommitted transactions.

If a transaction runs for a long time or the application fails to end the transaction, TRANSACTIONAL can also wait a long time.

### 5.4. Example

```sql
SHUTDOWN TRANSACTIONAL
```

During the wait, applications cannot start new transactions. Already-started transactions must complete before their sessions are disconnected.

### 5.5. TRANSACTIONAL LOCAL in RAC

Some releases support the SHUTDOWN TRANSACTIONAL LOCAL option in RAC environments. The LOCAL option restricts waiting to transactions local to the instance being shut down, rather than waiting for all related transactions across other instances per standard TRANSACTIONAL semantics.

This is specialized syntax for RAC; check the Oracle RAC Administrator's Guide for your release and use SRVCTL/Clusterware runbooks if the instance is cluster-managed. Do not use LOCAL on a single-instance database as a separate mode.

### 5.6. When to Use?

- Wanting to stop accepting new transactions.
- Wanting current transactions to finish normally.
- Wanting to avoid rolling back a batch of active transactions.
- Able to accept a drain time depending on the longest transaction.

### 5.7. Risks

- Long batch/ETL transactions can prolong shutdown.
- Applications may retry and generate new requests if not notified of draining.
- Distributed/in-doubt transactions require special procedures.
- Not all clients may finish before the maintenance deadline.

## 6. SHUTDOWN IMMEDIATE

### 6.1. Behavior

IMMEDIATE prevents new connections and new transactions, terminates running SQL statements, disconnects user sessions, and rolls back uncommitted transactions. After handling rollbacks and closing the database, Oracle dismounts the database and stops the instance.

IMMEDIATE does not wait for users to disconnect on their own and does not wait for current transactions to commit like TRANSACTIONAL. This is the common mode for maintenance with a controlled downtime window.

### 6.2. Rolling Back Uncommitted Transactions

Suppose a session is executing:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Not yet COMMITted
```

If the DBA runs SHUTDOWN IMMEDIATE, the uncommitted transaction will be rolled back. Previously committed values are preserved; uncommitted changes do not become durable data.

Rollback can take time if the transaction modified many blocks or generated a large amount of undo. Therefore, IMMEDIATE does not mean the command always completes instantaneously.

### 6.3. Running SQL Statements

Oracle terminates currently executing SQL statements and processes the corresponding transactions per rollback rules. Applications may receive connection or statement errors; applications must handle failed requests and must not assume the operation committed.

### 6.4. Example

```sql
SHUTDOWN IMMEDIATE
```

When the command finishes, the database has closed cleanly following the immediate shutdown sequence. The next startup does not require instance recovery solely because of this shutdown mode.

### 6.5. When to Use?

- Maintenance with a well-defined time window.
- Wanting to stop sessions without waiting for clients to disconnect on their own.
- Accepting the rollback of uncommitted transactions.
- Needing a clean shutdown to patch, restart, or change configuration.

### 6.6. Risks

- Uncommitted transactions are rolled back.
- In-flight clients may receive errors and need idempotent retries.
- Large rollbacks can lengthen shutdown duration.
- Applications may have performed side effects outside the database; Oracle rollback does not automatically undo emails, HTTP calls, or file system operations.

### 6.7. IMMEDIATE Is Popular, but Not the Default for Every System

Before using it, drain traffic and notify applications. If business requirements dictate that active transactions must complete, TRANSACTIONAL may be more appropriate. If sessions must close following application logic, NORMAL may be more appropriate.

## 7. SHUTDOWN ABORT

### 7.1. Behavior

ABORT stops the instance immediately without waiting for users to disconnect, without waiting for transactions to end, without rolling back uncommitted transactions during the shutdown sequence, and without closing/dismounting the database via the clean shutdown procedure.

From a recovery perspective, this is similar to an instance crash or power loss. Oracle must perform instance recovery when the database is started again.

### 7.2. Example

```sql
SHUTDOWN ABORT
```

Use ABORT when other shutdown modes cannot complete within the required time or the instance is in a state where it cannot shut down normally. Do not use it as a daily method to stop services simply because it is fast.

### 7.3. What Happens to Uncommitted Transactions?

ABORT does not turn uncommitted transactions into committed ones. At the next startup, Oracle uses redo to restore changes needed for database consistency, then undoes uncommitted transactions per the recovery process.

Uncommitted transactions will not be treated as successful. A client may not know for sure whether its last statement committed if the connection dropped right at COMMIT time; the application must check the outcome via transaction ID/idempotency key before retrying the business operation.

### 7.4. Instance Recovery After ABORT

At startup, Oracle checks the database state and performs instance recovery if needed. At a high level:

1. Redo is applied to bring datafiles to a consistent state with the required redo.
2. Changes belonging to uncommitted transactions are undone per the recovery mechanism.
3. The database is brought to a state where it can be opened.

Recovery time depends on the amount of uncheckpointed redo, storage speed, recovery configuration, and instance state at abort time. Startup after ABORT can take longer than after a clean shutdown.

### 7.5. Does ABORT Corrupt the Database?

ABORT by itself does not mean the database is corrupted. Oracle is designed to recover from instance failure using redo/undo. However, abort generates recovery work, disrupts clients, and can lengthen the time to restore service.

Do not confuse instance recovery with media recovery. If a datafile/storage is physically damaged, instance recovery does not replace restoring/recovering from backup.

### 7.6. Difference from Killing Processes at the OS Level

If an abort is necessary, use the SHUTDOWN ABORT command through the Oracle administrative interface while the instance is still responsive. Do not arbitrarily run kill -9 or terminate Oracle processes; OS-level termination can make the situation harder to control and bypasses Oracle's administrative mechanisms.

If the instance is unresponsive, follow the appropriate incident recovery/Clusterware procedure and work with the responsible DBA.

### 7.7. When to Use?

- SHUTDOWN IMMEDIATE/NORMAL/TRANSACTIONAL cannot complete and the instance must be stopped.
- The instance is hung or unresponsive to normal shutdown commands.
- An operational incident requires an immediate stop per the incident runbook.
- The DBA has accepted that the subsequent startup will require instance recovery.

### 7.8. Risks

- Next startup requires instance recovery.
- Recovery duration is hard to predict without knowing how much redo needs processing.
- Clients lose connections abruptly; the outcome of the final transaction may require verification.
- Can increase total outage duration even though the abort command returns quickly.

## 8. Rollback, Checkpoints, and Recovery

### 8.1. Rollback Is Not the Same as Instance Recovery

Rollback is undoing the changes of an uncommitted transaction. Instance recovery is the process of restoring the database after an abnormal instance termination or unclean shutdown.

IMMEDIATE rolls back uncommitted transactions before completing a clean shutdown. ABORT stops before shutdown-sequence rollback; recovery handles uncommitted transactions at startup.

### 8.2. Checkpoints and Clean Shutdown

During a clean shutdown, Oracle closes the database sequentially and performs the operations required to ensure the database state can be reopened without needing instance recovery due to shutdown. Dirty buffers and metadata are handled per Oracle mechanisms.

ABORT does not wait for checkpoints/closing per the clean shutdown sequence. Therefore, redo and undo are used to recover after startup.

### 8.3. Committed Transactions

Commits are confirmed by Oracle according to redo durability semantics. After ABORT, redo recovery preserves committed transactions per the database's durability configuration. Do not treat uncommitted changes as saved just because the client sent DML.

### 8.4. Distributed Transactions

Distributed transactions can enter an in-doubt state if connectivity to a participant/coordinator is interrupted. Shutdown modes do not replace distributed transaction resolution procedures. DBAs must check DBA_2PC_PENDING/DBA_2PC_NEIGHBORS and use force commit/rollback procedures only with a business decision and appropriate coordinator information.

### 8.5. Startup After Each Mode

| Prior Mode | Instance Recovery Due to Shutdown Mode? | Notes |
| --- | --- | --- |
| NORMAL | No | Clean close |
| TRANSACTIONAL | No | Clean close after transactions complete |
| IMMEDIATE | No | Clean close after rolling back uncommitted transactions |
| ABORT | Yes | Oracle recovery at next startup |

Do not confuse recovery due to ABORT with media recovery due to missing/corrupted files.

## 9. Monitoring Sessions Before Shutdown

### 9.1. Listing User Sessions

DBAs can inspect connected user sessions:

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    machine,
    program,
    module,
    logon_time,
    event,
    sql_id,
    taddr
FROM v$session
WHERE type = 'USER'
ORDER BY username, logon_time;
```

IDLE sessions can still hold connections and make SHUTDOWN NORMAL wait. Check MACHINE, PROGRAM, and MODULE to identify the owner; do not kill a session solely because its status is INACTIVE.

### 9.2. Finding Sessions with Transactions

```sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.machine,
    s.program,
    s.sql_id,
    t.start_time,
    t.used_ublk,
    t.used_urec
FROM v$session s
JOIN v$transaction t
  ON t.addr = s.taddr
ORDER BY t.start_time;
```

USED_UBLK and USED_UREC provide information about undo usage, helping identify large transactions. They are not an exact measurement of rollback duration.

### 9.3. Blocker Sessions and Locks

```sql
SELECT
    sid,
    serial#,
    username,
    blocking_session,
    event,
    seconds_in_wait,
    sql_id,
    machine,
    program
FROM v$session
WHERE blocking_session IS NOT NULL;
```

This query finds sessions waiting on a blocker. A shutdown waiting for session disconnection/transaction completion will not necessarily always show a blocking_session; check both the session list and the transaction list together.

### 9.4. Checking Running Jobs

```sql
SELECT
    owner,
    job_name,
    session_id,
    running_instance,
    elapsed_time,
    cpu_used
FROM dba_scheduler_running_jobs
ORDER BY owner, job_name;
```

This view requires appropriate privileges. Running jobs may hold long transactions or create sessions that do not close automatically. Coordinate with the owner to stop/complete jobs properly.

### 9.5. Checking Sessions by Service/Module

```sql
SELECT
    service_name,
    module,
    action,
    COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY service_name, module, action
ORDER BY session_count DESC;
```

Module/action/service information is only useful if the application sets them consistently. Use it to identify still-connected connection pools or workloads.

## 10. Monitoring a Waiting Shutdown

### 10.1. SHUTDOWN NORMAL Waiting for User Disconnect

If the command keeps waiting, check:

- User sessions still connected.
- Connection pools holding idle connections.
- Scheduler/job sessions.
- Monitoring/backup/agents automatically reconnecting.
- Applications that have not drained traffic or still run health checks.

SHUTDOWN NORMAL is not bounded by a default WAIT n seconds timeout per session. The DBA must identify remaining sessions and coordinate closing them.

### 10.2. SHUTDOWN TRANSACTIONAL Waiting for Transactions

Check V$TRANSACTION and V$SESSION to find active transactions. Look for SQL_ID, module, machine, start time, and undo volume. Large batch transactions may need time to complete.

Do not conclude a transaction is hung just because it runs for a long time. Ask the application owner whether the transaction is still making progress and can commit/roll back per logic.

### 10.3. SHUTDOWN IMMEDIATE Waiting for Rollback

IMMEDIATE can take time when rolling back a large transaction. Monitor the alert log, sessions/processes, and undo activity using authorized DBA tools. Do not switch to ABORT just because rollback has not finished after a few seconds; weigh recovery risk and total outage.

### 10.4. Alert Log

The alert log records startup/shutdown events, critical errors, and many progress messages. It can be viewed using ADRCI or an appropriate view:

```sql
SELECT
    originating_timestamp,
    message_text
FROM v$diag_alert_ext
WHERE originating_timestamp > SYSTIMESTAMP - INTERVAL '2' HOUR
ORDER BY originating_timestamp;
```

View permissions and availability depend on configuration. The alert log is the primary source for confirming how far Oracle has progressed in shutdown/recovery.

### 10.5. Do Not Open Additional Application Connections While Draining

If applications, monitors, or pools keep reconnecting, NORMAL may never complete. Before shutdown, move services to maintenance/drain and block new traffic per infrastructure procedures.

## 11. Manually Killing Sessions: Use with Caution

### 11.1. ALTER SYSTEM KILL SESSION

A DBA can terminate a specific session:

```sql
ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
```

Replace sid and serial# with actual values from V$SESSION. This is a strong action: the session's uncommitted transaction is rolled back and the application may receive errors.

### 11.2. Do Not Kill Sessions Just Because SHUTDOWN NORMAL Is Waiting

If the goal is to let applications close sessions normally, notify the owner/pool first. Killing sessions can cause in-flight requests to fail, triggering retries and duplicate side effects in external systems.

### 11.3. KILL SESSION Is Not Instance ABORT

KILL SESSION affects one session. SHUTDOWN ABORT stops the entire instance. The two commands have completely different scopes and recovery consequences.

### 11.4. Session Marked for Kill

ALTER SYSTEM KILL SESSION may mark a session for termination and cleanup; the session might not disappear immediately if it is rolling back or waiting for resources. Check session status and alert/trace logs rather than repeating kill commands continuously.

### 11.5. OS Process Termination

Do not use kill -9 or taskkill to handle normal Oracle sessions. Use Oracle session management and shutdown commands. Only handle processes at the OS level per incident runbooks and DBA/Oracle Support guidance when the instance is unresponsive.

## 12. Shutdown in CDB and PDB

### 12.1. CDB Instance and Pluggable Databases

In multitenant architecture, the CDB instance manages the container database and PDBs. SHUTDOWN affects the instance/CDB, not a command that closes only a single PDB.

If the goal is to close one PDB while keeping the CDB instance running, use ALTER PLUGGABLE DATABASE:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;
ALTER PLUGGABLE DATABASE salespdb CLOSE IMMEDIATE;
```

PDB close modes and exact syntax depend on the release. Closing a PDB does not stop the listener or instance; other PDBs can continue operating.

### 12.2. Shutting Down the Entire CDB

When connected with administrative privileges to the CDB, SHUTDOWN NORMAL/TRANSACTIONAL/IMMEDIATE/ABORT affects the instance and the PDBs managed by that instance. Choose the mode based on CDB-wide transactions/sessions, not just one PDB.

### 12.3. PDBs Have Their Own Sessions

Before closing a PDB, check sessions in the corresponding container and coordinate application services connecting to that PDB. You can use CDB views such as CDB_PDBS/CDB_SERVICES or GV$SESSION with CON_ID to identify the container. Appropriate common user privileges are required.

### 12.4. PDB Close Is Not Equivalent to Instance Shutdown

| Operation | Scope |
| --- | --- |
| ALTER PLUGGABLE DATABASE ... CLOSE | Closes one or more PDBs |
| SHUTDOWN ... | Closes the CDB/database and stops the instance |

Do not shut down the entire CDB just to deploy an application in one PDB if the procedure only requires closing that PDB.

## 13. Shutdown in RAC and Oracle Clusterware

### 13.1. Instance as the Per-Node Unit

In RAC, multiple instances access the same database. Each instance has its own SGA/processes, while database files are shared. Shutting down one instance does not mean shutting down the entire database; remaining instances can continue serving.

### 13.2. Use SRVCTL for Clusterware-Managed Resources

For RAC/Oracle Restart, use SRVCTL to stop instances/databases/services via resource management. Illustrative example of stopping one instance:

```text
srvctl stop instance -db <db_unique_name> -instance <instance_name> -stopoption immediate
```

Or stopping the database resource:

```text
srvctl stop database -db <db_unique_name> -stopoption immediate
```

Exact options and syntax vary by release. Check srvctl help and the Clusterware Administrator's Guide for your running version before executing.

### 13.3. Why Should You Not Bypass Clusterware?

Clusterware tracks resource states, dependencies, services, and restart policies. If a DBA runs SQL*Plus shutdown directly while Clusterware still manages the resource, Clusterware may treat the resource as unexpectedly stopped and take action according to its policy.

Using SRVCTL informs Clusterware of the intentional stop and coordinates services/instances properly.

### 13.4. Shutting Down One Instance and Service Relocation

Before stopping a RAC instance:

- Identify services running on that instance.
- Drain or relocate services according to policy.
- Check remaining session counts and active transactions.
- Confirm remaining instances have sufficient capacity.
- Check FAN/ONS, connection pools, and load balancing.

If remaining instances lack sufficient resources, service relocation can overload other nodes.

### 13.5. Shutting Down the Entire RAC Database

If the entire database must be stopped, coordinate stopping services and stopping the database resource in the order managed by Clusterware. Do not run manual shutdowns in parallel on multiple instances unless required by the runbook; avoid race conditions between Clusterware and DBAs.

### 13.6. TRANSACTIONAL LOCAL

In RAC, TRANSACTIONAL LOCAL can be used when needing to shut down an instance and wait only for transactions local to that instance. Assess the impact of distributed transactions and service failover before using; do not assume transactions on another instance have no business relationship with the running work.

## 14. Listener, Services, and Connection Pools

### 14.1. Listener Is Not an Instance

The listener is a network process that accepts connections and forwards requests to database services. Shutting down an instance does not necessarily stop the listener. The listener can keep running and report the service as unavailable when the instance is stopped.

It is not necessary to stop the listener for every database shutdown. If maintenance involves the listener/network, that is a separate step in the runbook.

### 14.2. Database Services

A service is a logical connection name for a workload/PDB/role. In RAC, a service can run on one or more instances and is managed by Clusterware.

Before shutdown:

- Stop accepting new requests at the load balancer/API gateway.
- Drain or relocate services per design.
- Have connection pools stop borrowing new connections.
- Wait for running requests/transactions per SLA.
- Close idle connections per policy.

### 14.3. Connection Pools

Connection pools can hold many physical sessions even when there are no active requests. This is a common reason SHUTDOWN NORMAL waits for a long time. Pool configurations need proper drain/stop modes and timeouts for maintenance.

Do not only shut down web servers if batch workers, schedulers, or integration services still hold connections to the database.

### 14.4. FAN/ONS and Application Failover

In RAC, Fast Application Notification (FAN) and Oracle Notification Service (ONS) can publish service/instance events so connection pools handle failed connections and failover. Actual behavior depends on the driver/pool and configuration. Test failover/drain before using it for critical maintenance.

### 14.5. Stop Services First or Shutdown First?

The common order is to stop new traffic, drain/stop services, wait for requests/transactions per policy, and then shut down the instance. With RAC, service relocation may occur instead of a full stop. The exact order depends on application architecture and Clusterware.

## 15. Shutdown in Data Guard

### 15.1. Identify the Role

Before shutting down, check the database role and open mode:

```sql
SELECT
    name,
    database_role,
    open_mode,
    protection_mode,
    switchover_status
FROM v$database;
```

Distinguish PRIMARY, PHYSICAL STANDBY, LOGICAL STANDBY, or other supported roles. Do not apply a primary runbook to a standby without checking the role.

### 15.2. Shutting Down Primary

Shutting down the primary stops primary database service availability. The standby can continue applying already-received redo, but redo transport from the primary stops while the primary is down. After the primary returns, check transport/apply lag and archive gaps per the Data Guard runbook.

Shutdown does not automatically perform a switchover or failover.

### 15.3. Shutting Down Standby

Shutting down a standby pauses apply/redo processing on that standby. The primary can continue operating, but you must monitor transport destinations, archive retention, and catch-up capability when the standby returns.

### 15.4. Broker-Managed Configuration

If using Data Guard Broker, perform maintenance according to the organization's DGMGRL/Broker procedures. Check configuration status, transport/apply lag, and role transitions. Do not change roles or disable the broker just to run a simple shutdown command unless required.

### 15.5. Switchover/Failover Is a Different Procedure

Switchover/failover is a controlled or emergency role transition between primary and standby. SHUTDOWN only stops the instance/database. Do not use ABORT or IMMEDIATE in place of a role transition procedure.

## 16. Jobs, Backups, and Background Work

### 16.1. Scheduler Jobs

Job Scheduler jobs may be running when a shutdown is requested. Check DBA_SCHEDULER_RUNNING_JOBS and coordinate with job owners. Determine whether jobs can be safely stopped/retried or must finish.

### 16.2. DBMS_JOB and Job Queues

Legacy jobs via DBMS_JOB and job queue processes can also create active sessions. The JOB_QUEUE_PROCESSES parameter controls job queue workers depending on scope/release. Do not set it to 0 on production without understanding the impact on all jobs and having a plan to restore the value.

### 16.3. RMAN and Backups

Before shutdown, identify any running RMAN backup/restore, duplicate, block media recovery, or backup agents. Shutdown can interrupt jobs; incomplete backups must be flagged and handled per backup policy.

### 16.4. Data Pump and External Jobs

Data Pump jobs, external table processes, external jobs, or integration tasks may have external sessions/processes. Stopping the database does not automatically guarantee external processes have cleaned up properly. Track their job states and files/logs.

### 16.5. Background Processes

Oracle manages background processes such as DBWn, LGWR, CKPT, SMON, PMON, and ARCn itself. Do not kill these processes individually as a shutdown method. Use SHUTDOWN/SRVCTL so Oracle terminates the instance sequentially.

## 17. Pre-Shutdown Runbook

### 17.1. Verify the Correct Environment

Before running commands:

- Confirm database name, DB_UNIQUE_NAME, instance name, and host.
- Confirm single instance, RAC, Oracle Restart, or container.
- Confirm CDB/PDB and current container.
- Confirm database role if Data Guard is present.
- Verify maintenance window, owner, and approver.
- Confirm the correct environment (DEV/TEST/UAT/PROD).

A syntactically correct shutdown command run on the wrong instance is still a severe incident.

### 17.2. Verify Current State

```sql
SELECT instance_name, host_name, status, database_status, startup_time
FROM v$instance;

SELECT name, db_unique_name, open_mode, database_role
FROM v$database;
```

For RAC:

```sql
SELECT inst_id, instance_name, host_name, status
FROM gv$instance
ORDER BY inst_id;
```

### 17.3. Notify and Drain Traffic

Notify application owners, DBA on-call, monitoring, and users. Block new requests at the load balancer/API gateway, place services into maintenance or drain, stop new batches/jobs, and wait for in-flight requests per SLA.

Ensure health checks/monitoring do not recreate connections during SHUTDOWN NORMAL.

### 17.4. Check Sessions and Transactions

Run the V$SESSION, V$TRANSACTION, and DBA_SCHEDULER_RUNNING_JOBS queries from earlier sections. Identify:

- Application pool sessions.
- Transactions with large undo volume.
- Running batch/reporting/ETL workloads.
- Administrative/monitoring sessions that need to stay active.
- In-doubt distributed transactions.

Save outputs for audit/incident purposes if policy permits; mask sensitive information.

### 17.5. Check Backups and Data Guard

Verify running backups/restores/Data Pump jobs, archive destinations, and standby lag. For Data Guard, check role, transport/apply, and Broker procedures. For RAC, verify service relocation/capacity and remaining instances.

### 17.6. Choose the Mode and Communicate Consequences

Document why NORMAL, TRANSACTIONAL, IMMEDIATE, or ABORT was chosen. If IMMEDIATE, communicate that uncommitted transactions may be rolled back. If ABORT, communicate that the subsequent startup requires instance recovery and the outage may be longer.

### 17.7. Prepare Startup and Rollback Plan

Before maintenance, verify:

- SPFILE/PFILE and password file availability.
- Storage, ASM, listener, and Clusterware dependencies.
- Startup/verification procedures.
- Who is responsible for verifying application health.
- Contingency plan if startup or recovery does not complete.

## 18. Executing Shutdown by Scenario

### 18.1. NORMAL Scenario

1. Drain application traffic.
2. Have connection pools close physical connections.
3. Confirm session count drops to 0 or only necessary admin sessions remain.
4. Connect with a separate administrative session.
5. Run SHUTDOWN NORMAL.
6. Wait for the command to complete.
7. Confirm the instance has stopped and record the time.

If sessions remain, find the owners and handle via the application/pool. Do not automatically kill all sessions just to make the command finish.

### 18.2. TRANSACTIONAL Scenario

1. Block new requests/transactions at the application/service layer.
2. Run SHUTDOWN TRANSACTIONAL.
3. Monitor V$TRANSACTION/V$SESSION from a monitoring session or authorized monitoring tool.
4. Allow active transactions to complete.
5. Once transactions finish, Oracle disconnects clients and completes shutdown.

Do not start new transactions during draining. If a transaction makes no progress, coordinate with the owner to decide whether to keep waiting or switch approaches.

### 18.3. IMMEDIATE Scenario

1. Notify applications and block new traffic.
2. Confirm uncommitted transactions can be rolled back.
3. Run SHUTDOWN IMMEDIATE.
4. Monitor the alert log and rollback time if the command has not yet finished.
5. Wait for Oracle to close the database and stop the instance.
6. Confirm a clean shutdown before proceeding with maintenance.

Do not run ABORT immediately while IMMEDIATE is still rolling back without assessing impact and making an incident decision.

### 18.4. ABORT Scenario

1. Confirm the instance must be stopped and the emergency justification.
2. Assess that final client transactions may be in an indeterminate state for the caller.
3. Run SHUTDOWN ABORT via an administrative connection if the instance is still responsive.
4. Record the abort timestamp and alert/trace details.
5. Start back up per the recovery runbook when ready.
6. Monitor instance recovery and confirm database open.
7. Reconcile final business transactions using idempotency keys/request IDs.

ABORT is not a way to skip checks; it shifts work to recovery at the next startup.

## 19. Verifying the Instance Has Shut Down

### 19.1. SQL*Plus Output

With a clean shutdown, SQL*Plus typically displays messages for database closed, database dismounted, and instance shut down. Exact output may vary by client/version.

ABORT usually finishes quickly and does not display the same clean close sequence. Do not rely on a single line of output alone; check the alert log and process/resource state.

### 19.2. Reconnecting to Verify

After the instance has stopped, a V$INSTANCE query cannot run on that instance because there is no instance left to return results. Use OS processes/Clusterware/SRVCTL and the alert log to verify.

Example on RAC:

```text
srvctl status database -db <db_unique_name>
srvctl status instance -db <db_unique_name> -instance <instance_name>
```

Exact syntax depends on release. On single instance, check Oracle process status and the alert log per OS/runbook.

### 19.3. Checking Listener and Services

The listener may remain running after shutdown. Verify that services are no longer advertised by the stopped instance; on RAC, services may be running on another instance. Do not conclude an instance is still open simply because the listener process still exists.

### 19.4. Recording Timings

Record:

- Drain start time.
- Shutdown execution time.
- Session/transaction wait duration.
- Rollback duration if IMMEDIATE.
- Command completion time.
- Mode used.
- Number of remaining sessions/transactions at start time.

These metrics help improve maintenance windows and detect connection leaks.

## 20. Startup After Shutdown

### 20.1. Startup After Clean Shutdown

After NORMAL, TRANSACTIONAL, or IMMEDIATE, connect with an administrative session and run:

```sql
STARTUP
```

Oracle initializes the instance, mounts, and opens the database per the startup command. If the configuration requires startup mount or restricted, follow the corresponding runbook.

### 20.2. Startup After ABORT

After ABORT:

```sql
STARTUP
```

Oracle automatically performs instance recovery if needed during startup. Monitor the alert log for recovery progress and any errors. Do not run media recovery solely because the prior shutdown was ABORT; only use it if there is a separate file/media issue.

### 20.3. STARTUP FORCE

STARTUP FORCE is a combined command: if the instance is running, Oracle executes shutdown abort followed by startup. This is not a safer startup method and can trigger instance recovery. Use only when needed and with the understanding that a running instance will be aborted.

### 20.4. Checking State After Startup

```sql
SELECT
    instance_name,
    status,
    database_status,
    startup_time
FROM v$instance;

SELECT
    name,
    open_mode,
    database_role
FROM v$database;
```

Confirm database open mode, role, PDB state, service registration, background processes, and the alert log. For RAC, verify all instances/services are in the desired state.

### 20.5. Verifying Applications

After the database opens:

- Verify services register with the listener/Clusterware.
- Verify connection pools can reconnect.
- Run test transactions/read-only health checks.
- Check scheduler/job states.
- Check Data Guard transport/apply if applicable.
- Monitor error rates, latency, and wait events.

Only open traffic when application owners confirm the system is operating normally.

## 21. Common Errors During Shutdown/Startup

| Error/Symptom | Possible Cause | Resolution Direction |
| --- | --- | --- |
| ORA-01031: insufficient privileges | Session lacks appropriate administrative privileges | Connect with authorized privileges; do not arbitrarily elevate application privileges |
| ORA-01034: ORACLE not available | Instance not running or already shut down | Check ORACLE_SID, services, and instance status |
| ORA-01089: immediate shutdown in progress | Instance is in the middle of shutting down | Wait/check shutdown progress and alert log |
| ORA-01012: not logged on | Session was disconnected or instance stopped | Reconnect when the instance is ready |
| ORA-01033: initialization or shutdown in progress | Database is starting up/shutting down | Monitor the alert log; do not generate new application connections |
| SHUTDOWN NORMAL waits forever | Idle/pool/monitor sessions have not disconnected | Drain traffic, find session owners, and close connections properly |
| SHUTDOWN TRANSACTIONAL waits a long time | Long transaction not yet committed/rolled back | Check V$TRANSACTION, consult application owner, and monitor progress |
| SHUTDOWN IMMEDIATE waits a long time | Large transaction rollback or cleanup | Monitor undo/alert log; avoid aborting hastily |
| Startup after ABORT takes a long time | Instance recovery is running | Monitor alert log, I/O, and recovery progress |
| ORA-04031/ORA-04030 after startup | Memory pressure or allocation issue | Check SGA/PGA/OS; do not attribute solely to ABORT |
| ORA-01157/ORA-01110 on startup | Datafile inaccessible | Check storage/path/ASM and media recovery runbook |
| Service fails to register after startup | Listener/service/Clusterware not ready | Check LOCAL_LISTENER, service resources, and alert log |
| RAC instance restarts automatically | Clusterware restart policy/resource management | Use SRVCTL and inspect Clusterware logs |

### 21.1. ORA-01034 After Shutdown

After an instance stops, connecting to the database may return ORA-01034. This may be an expected state; verify whether maintenance is underway or the instance stopped unexpectedly before starting up.

### 21.2. ORA-01089 During Shutdown

ORA-01089 usually indicates an immediate shutdown is in progress. Applications should not continuously retry against an instance during shutdown. DBAs should check progress and the alert log to see whether shutdown is progressing or encountering errors.

### 21.3. Startup After ABORT Encounters File Errors

If startup reports an inaccessible datafile, that is a storage/file availability issue requiring separate handling. Instance recovery cannot repair a missing file or failed storage device. Check ASM/disk groups, mount points, and backups before deciding on media recovery.

## 22. Lab: Observing NORMAL and TRANSACTIONAL

Only perform on a lab database/dedicated instance that can be stopped. Do not run shutdown labs on shared development, UAT, or production. Two separate terminals/sessions and appropriate administrative privileges are required.

### 22.1. Prepare the Table

```sql
CREATE TABLE shutdown_lab (
    id NUMBER PRIMARY KEY,
    value_text VARCHAR2(100)
);

INSERT INTO shutdown_lab VALUES (1, 'before');
COMMIT;
```

### 22.2. Session A — Hold an Idle Connection

Connect as a lab user and leave session A open without disconnecting.

### 22.3. Session B — SHUTDOWN NORMAL

Connect with administrative privileges in terminal B and run:

```sql
SHUTDOWN NORMAL
```

The command will wait for session A to disconnect. Return to session A and run EXIT/LOGOFF. Then observe terminal B completing shutdown.

### 22.4. Start Back Up

```sql
STARTUP
```

Verify the instance is open again before the next exercise.

### 22.5. Session A — Open a Transaction

In session A:

```sql
UPDATE shutdown_lab
SET value_text = 'transactional-test'
WHERE id = 1;

-- Not yet COMMITted
```

### 22.6. Session B — SHUTDOWN TRANSACTIONAL

In terminal B, run:

```sql
SHUTDOWN TRANSACTIONAL
```

The command will wait for the open transaction. Return to session A and run COMMIT. Oracle disconnects the client after the transaction finishes and completes shutdown.

### 22.7. Start Up and Verify

```sql
STARTUP

SELECT * FROM shutdown_lab WHERE id = 1;
```

The committed value must remain after startup. The lab demonstrates that transactions are allowed to complete before the instance stops.

## 23. Lab: IMMEDIATE and ABORT

Run only on a dedicated lab instance. ABORT simulates an instance failure and forces startup recovery. Do not use it to test on shared databases or production.

### 23.1. Prepare an Uncommitted Transaction

After the instance has started up and the SHUTDOWN_LAB table exists, in session A:

```sql
UPDATE shutdown_lab
SET value_text = 'not-committed'
WHERE id = 1;

-- Do not COMMIT
```

### 23.2. Session B — SHUTDOWN IMMEDIATE

In administrative terminal B:

```sql
SHUTDOWN IMMEDIATE
```

Oracle disconnects session A and rolls back the uncommitted transaction. When the command completes, reconnect with an administrative account and run STARTUP.

### 23.3. Check After IMMEDIATE

```sql
SELECT id, value_text
FROM shutdown_lab
WHERE id = 1;
```

The value must be the value committed prior to the test transaction, not not-committed. Clean shutdown IMMEDIATE does not require instance recovery due to the shutdown mode.

### 23.4. Session A — Create a New Transaction for ABORT

In session A:

```sql
UPDATE shutdown_lab
SET value_text = 'abort-uncommitted'
WHERE id = 1;

-- Do not COMMIT
```

### 23.5. Session B — SHUTDOWN ABORT

In administrative terminal B:

```sql
SHUTDOWN ABORT
```

The instance stops immediately; session A loses its connection. Reconnect with an administrative connection and run STARTUP. Monitor the alert log to observe instance recovery.

### 23.6. Check After ABORT

```sql
SELECT id, value_text
FROM shutdown_lab
WHERE id = 1;
```

The uncommitted value is not retained as a successful transaction. Oracle recovery handles uncommitted changes. If deeper inspection is needed, check the alert log and recovery messages.

### 23.7. Key Takeaways

- IMMEDIATE rolls back uncommitted transactions during clean shutdown.
- ABORT stops before clean rollback; subsequent startup performs instance recovery.
- Neither mode turns uncommitted DML into committed data.
- A client losing connection right at COMMIT time may not know the outcome for sure; the application must verify via request ID/idempotency key.

## 24. Rules on Clients and Transaction Outcomes

### 24.1. Client Receiving an Error Does Not Mean the Transaction Rolled Back

If the network drops during COMMIT, the client might not receive a response even though the database committed successfully. This is an indeterminate outcome from the client's perspective and cannot be concluded from an application-side exception.

### 24.2. Use Idempotency Keys

For retryable business operations, generate a unique request ID and persist it alongside the business transaction. When the client reconnects, look up the request ID to determine whether the operation already committed before resubmitting.

### 24.3. Do Not Retry Blindly

A request that failed due to shutdown may have already produced side effects in services outside the database. Retrying without idempotency can create duplicate payments, emails, or orders. Design transactions/outboxes and idempotent consumers if the application has cross-system side effects.

### 24.4. Distributed Transactions

If a request uses a database link or XA/JTA, the transaction may require coordination from a transaction manager. DBAs should not force commit/rollback in-doubt transactions solely because an instance just shut down; coordinate with the application transaction coordinator and DBA per distributed transaction procedures.

## 25. Shutdown/Startup Operational Checklist

### 25.1. Before Shutdown

- [ ] Confirm DB_NAME, DB_UNIQUE_NAME, instance, host, and environment.
- [ ] Confirm single instance/RAC/Oracle Restart and CDB/PDB.
- [ ] Check database role if Data Guard is used.
- [ ] Have a maintenance window and notify stakeholders.
- [ ] Drain new requests, connection pools, and services.
- [ ] Check sessions, transactions, jobs, backups, and Data Pump.
- [ ] Identify long transactions and distributed transactions.
- [ ] Choose shutdown mode according to SLA and rollback requirements.
- [ ] Prepare startup commands, dependencies, and rollback plan.

### 25.2. During Shutdown

- [ ] Use the proper administrative connection and target instance.
- [ ] Monitor sessions/transactions if NORMAL/TRANSACTIONAL is waiting.
- [ ] Monitor rollback if IMMEDIATE takes a long time.
- [ ] If ABORT, log an incident and prepare for instance recovery.
- [ ] Do not kill OS processes arbitrarily.
- [ ] Do not allow applications/monitors to open new connections while draining.

### 25.3. After Shutdown

- [ ] Confirm the instance/resources have stopped.
- [ ] Check the alert log and shutdown completion time.
- [ ] With ABORT, note the recovery required at the next startup.
- [ ] Verify other services/listeners/instances are in the desired state.
- [ ] Record durations and any remaining sessions/transactions.

### 25.4. After Startup

- [ ] Verify V$INSTANCE and V$DATABASE.
- [ ] Check the alert log, recovery, and file availability.
- [ ] Verify PDB open state.
- [ ] Verify RAC instances/services and Clusterware status.
- [ ] Verify Data Guard transport/apply.
- [ ] Check scheduler, backups, and job states.
- [ ] Test application connections and health checks.
- [ ] Only reopen traffic when owners confirm system stability.

## 26. Self-Check Questions

1. Which mode does SHUTDOWN default to when no mode is specified?
2. Why can NORMAL wait indefinitely?
3. How does NORMAL handle idle sessions?
4. What does TRANSACTIONAL block and what does it wait for?
5. How does TRANSACTIONAL differ from NORMAL in how it disconnects clients?
6. How does TRANSACTIONAL differ from IMMEDIATE in handling uncommitted transactions?
7. Does IMMEDIATE wait for users to disconnect on their own?
8. Why can IMMEDIATE still take a long time?
9. How does ABORT differ from IMMEDIATE in rollback and closing the database?
10. Why does startup after ABORT require instance recovery?
11. How does instance recovery differ from media recovery?
12. Does ABORT automatically lose committed transactions?
13. Why might a client not know whether COMMIT succeeded when the connection drops?
14. How do idempotency keys help handle retries?
15. How do V$SESSION and V$TRANSACTION help identify blockers?
16. Why can an INACTIVE session still cause NORMAL to wait?
17. When should ALTER SYSTEM KILL SESSION be used?
18. Why should you not kill -9 Oracle processes?
19. How does SHUTDOWN CDB differ from CLOSE PDB?
20. Why should RAC use SRVCTL for Clusterware-managed resources?
21. What is the purpose of TRANSACTIONAL LOCAL in RAC?
22. Does the listener automatically stop when the database shuts down?
23. How do service draining and connection pools affect shutdown?
24. How does shutting down the primary affect Data Guard redo transport?
25. Why is switchover/failover a different procedure from shutdown?
26. What must be checked before stopping Scheduler/RMAN/Data Pump?
27. After ABORT, what should you inspect in the alert log?
28. What must be verified before reopening application traffic?

## 27. Mental Model

```text
SHUTDOWN REQUEST
       |
       +-- NORMAL
       |     Block new connections
       |     Wait for all users to disconnect
       |
       +-- TRANSACTIONAL
       |     Block new transactions
       |     Wait for current transactions to finish
       |     Disconnect clients afterward
       |
       +-- IMMEDIATE
       |     Block new connections/transactions
       |     Terminate running SQL
       |     Roll back uncommitted transactions
       |     Clean close
       |
       +-- ABORT
             Stop instance immediately
             No clean rollback/close
             Instance recovery at STARTUP
       |
       v
OPERATIONS
       |
       +-- Drain application/services
       +-- Check sessions and transactions
       +-- Monitor alert log and rollback
       +-- RAC -> SRVCTL / Clusterware
       +-- PDB -> ALTER PLUGGABLE DATABASE
       +-- Data Guard -> role/transport/apply checks
       |
       v
STARTUP AND VERIFY
       |
       +-- V$INSTANCE / V$DATABASE
       +-- Alert log / recovery
       +-- PDB / service / listener
       +-- Application health and idempotent retry
```

**Key takeaway:** NORMAL waits for users to disconnect on their own; TRANSACTIONAL waits for running transactions to complete before disconnecting clients; IMMEDIATE cancels statements and rolls back uncommitted transactions before a clean close; ABORT stops immediately and leaves instance recovery to the next startup. Choose the mode based on transaction semantics, maintenance deadlines, and RAC/CDB/Data Guard architecture; always drain applications and verify state after shutdown/startup.
