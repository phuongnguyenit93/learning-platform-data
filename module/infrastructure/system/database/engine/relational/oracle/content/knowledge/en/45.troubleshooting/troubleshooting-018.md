# Impact assessment before killing sessions, restarting, or changing parameters in Oracle Database

During an Oracle Database incident, actions such as terminating a session, restarting an instance, or changing a system parameter can resolve symptoms quickly, but they can also interrupt valid transactions, trigger prolonged rollbacks, drop large numbers of connections, or alter database-wide behavior. Before taking action, the DBA must identify the exact affected targets, root cause, blast radius, and rollback procedure if the outcome differs from expectations.

The three action groups have different scopes:

- **Kill/disconnect session:** affects a specific session and its transaction. Uncommitted transactions may need to roll back; locks may not be released immediately.
- **Restart:** may restart only a service, a RAC instance, a PDB, or the entire database. The scope determines how many sessions are disconnected, which workloads must reconnect, and whether failover is possible.
- **Parameter change:** may affect only the current session, new sessions, one instance, all instances, or a PDB; it may take effect immediately or require a restart.

Do not apply a broad-scoped action to treat an unidentified symptom. Collect evidence first, choose the smallest change that achieves the goal, monitor during execution, and verify afterward.

This lesson uses Oracle Database 19c as the baseline, covering single-instance, RAC, and multitenant environments. The examples assume the operator holds appropriate DBA privileges and has approval under the system's operational change process.

## 1. Pre-intervention impact assessment framework

### 1.1. Identify symptoms and objectives

Before running commands, describe the incident using observable facts:

- Which session is waiting or blocking other sessions?
- Which SQL is consuming abnormal CPU, I/O, TEMP, or undo?
- Is the database, an instance, a service, or only a single PDB unresponsive?
- When did the error start and which applications are affected?
- Are there open transactions or distributed transactions?
- Does the symptom appear on one instance or all instances?
- Were there recent changes in deployments, workloads, network, or parameters?

Then define the desired outcome, such as releasing a lock, stopping a runaway query, relocating a service to a healthy instance, applying a new parameter, or restoring service availability.

Do not use vague descriptions such as “the database is hung” as grounds for a restart. Identify the session, wait event, service, instance, and error scope first.

### 1.2. Determine the blast radius

Blast radius is the scope of users, transactions, and technical components that may be affected:

| Action | Typical scope | Expected impact |
| --- | --- | --- |
| Cancel a SQL statement | One statement/session | Statement stops; the transaction may remain open |
| Kill a session | One session | Connection is lost; uncommitted transaction rolls back |
| Disconnect a session | One session | Session is terminated according to the specified mode |
| Stop/start a service | Sessions using that service | Connections are dropped or redirected depending on configuration |
| Restart a RAC instance | All sessions on the instance | Sessions are lost; services may fail over |
| Restart a PDB | Sessions and workloads belonging to the PDB | PDB closes/opens; other PDBs in the CDB can keep running |
| Restart the database | Entire database and dependent services | All sessions are dropped; recovery/startup takes time |
| Change a session parameter | Current session | Only that session is affected |
| Change a dynamic system parameter | Instance/PDB/session scope depending on the parameter | Workload behavior may change immediately or for new sessions |
| Change a static parameter in SPFILE | After the appropriate restart | Requires downtime/restart for the applicable scope |

Actual scope depends on RAC, service, PDB, connection pool, Data Guard configuration, and parameter type. Do not assume restarting an instance automatically moves all clients to another instance.

### 1.3. Capture state before making changes

Save at minimum:
- Timestamp and incident/change ID.
- Database name, DB unique name, role, and open mode.
- Involved instance, service, and PDB.
- Session ID, serial number, and instance ID if acting on a session.
- SQL ID, module, action, machine, and client identifier.
- Transaction start time, undo used, and held locks.
- Wait event, blocker chain, and blocked sessions.
- Current parameter values, SPFILE values, and scope.
- CPU, memory, I/O, TEMP, UNDO, REDO, FRA, and application latency.
- Relevant alert log entries and error stacks.

Save outputs before killing, restarting, or changing parameters. Afterward, compare the same metrics to confirm whether the change resolved the actual cause.

### 1.4. Distinguish root-cause remediation from symptom relief

Examples:
- Killing a session blocking DDL may release the lock, but does not fix the transaction or application logic creating the blocker.
- Restarting an instance may clear hung sessions, but does not fix overloaded SQL or misconfiguration.
- Increasing SGA/PGA may reduce certain out-of-memory errors, but can starve the OS of RAM or pressure other instances.
- Raising process/session limits may allow more connections, but does not fix connection leaks or oversized pools.

Before acting, state the root-cause hypothesis and what evidence will confirm it.

## 2. Identifying database, instance, service, and role

### 2.1. Check database context

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode,
       log_mode,
       flashback_on
FROM   v$database;
~~~

These fields identify whether the database is primary or standby, its open mode, and its `ARCHIVELOG`/Flashback Database status. Do not restart or modify configuration before confirming whether you are operating on a primary, physical standby, or another environment.

### 2.2. Check instances

~~~sql
SELECT instance_name,
       host_name,
       instance_number,
       status,
       database_status,
       startup_time
FROM   v$instance;
~~~

In RAC, use `GV$INSTANCE` to view all instances:

~~~sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM   gv$instance
ORDER  BY inst_id;
~~~

Do not confuse instance names with `DB_UNIQUE_NAME` or service names. A RAC database has multiple instances but can expose the same service across multiple instances.

### 2.3. Check services

~~~sql
SELECT inst_id,
       name,
       network_name,
       con_id
FROM   gv$active_services
ORDER  BY inst_id, name;
~~~

Cross-check active services against Clusterware configuration and the endpoints used by applications. A service not running on the expected instance can cause connection failures or routing to another instance.

### 2.4. Check PDBs

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM   v$pdbs
ORDER  BY con_id;
~~~

If the error occurs only within one PDB, do not assume the entire CDB needs a restart. Check the service, PDB open mode, sessions, and parameters modifiable at the PDB scope.

### 2.5. Check Data Guard role

~~~sql
SELECT database_role,
       open_mode,
       protection_mode,
       switchover_status
FROM   v$database;
~~~

Before restarting primary/standby or changing redo-related parameters, check the Data Guard broker, transport/apply lag, and peer status. An action on a standby must not inadvertently disrupt the primary; an action on the primary must evaluate failover/standby impact.

## 3. Evaluating sessions before killing

### 3.1. Identify the exact session

In single-instance, `SID` can suffice to begin investigation, but it is not safe for durable session identification. A `SID` can be reused after a session ends. Always pair `SID` with `SERIAL#`.

In RAC, `INST_ID` is also required. A session is identified by at least:
- `INST_ID`.
- `SID`.
- `SERIAL#`.

Do not grab a `SID` from a monitoring dashboard and kill it much later without re-verifying; the session may have already ended and its `SID` reassigned.

### 3.2. Inspect user sessions and running SQL

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       type,
       service_name,
       module,
       action,
       client_identifier,
       machine,
       program,
       sql_id,
       prev_sql_id,
       sql_exec_start,
       event,
       wait_class,
       seconds_in_wait,
       blocking_instance,
       blocking_session,
       logon_time,
       last_call_et
FROM   gv$session
WHERE  type = 'USER'
ORDER  BY inst_id, sid;
~~~

Key fields to interpret:
- `USERNAME` and `SERVICE_NAME`: database account and service.
- `MODULE`/`ACTION`/`CLIENT_IDENTIFIER`: application or business workflow if instrumented.
- `MACHINE`/`PROGRAM`: client host or source process.
- `SQL_ID`/`PREV_SQL_ID`: current/most recent SQL.
- `EVENT`/`WAIT_CLASS`: what the session is doing or waiting on.
- `BLOCKING_INSTANCE`/`BLOCKING_SESSION`: direct blocker if identified by Oracle.
- `LOGON_TIME`: when the session connected.
- `LAST_CALL_ET`: elapsed time since the last call depending on session state; not always equivalent to transaction duration.

Do not conclude a session is “harmlessly idle” solely from `STATUS='INACTIVE'`. An inactive session can still hold an uncommitted transaction and locks.

### 3.3. Find blockers and waiters

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       blocking_instance,
       blocking_session,
       final_blocking_instance,
       final_blocking_session,
       sql_id,
       module,
       machine
FROM   gv$session
WHERE  blocking_session IS NOT NULL
   OR  final_blocking_session IS NOT NULL
ORDER  BY inst_id, sid;
~~~

`FINAL_BLOCKING_SESSION` helps look further up the blocking chain. If one session blocks many others, mistakenly killing a waiter instead of the blocker will not clear the queue.

Evaluate the entire chain:
1. Which sessions are waiting?
2. Which session is blocking directly?
3. Which session is the final blocker?
4. Does the blocker hold a legitimate business transaction?
5. Are there multiple blocking layers or a lock cycle?

### 3.4. Inspect locked objects

~~~sql
SELECT lo.inst_id,
       lo.session_id AS sid,
       s.serial#,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM   gv$locked_object lo
JOIN   dba_objects o
       ON o.object_id = lo.object_id
LEFT JOIN gv$session s
       ON s.inst_id = lo.inst_id
      AND s.sid = lo.session_id
ORDER  BY lo.inst_id, o.owner, o.object_name;
~~~

`LOCKED_MODE` is a numeric lock mode code. Consult the Oracle Database Reference to interpret the mode. A single session can hold multiple locks on multiple objects; confirm the object relevant to the incident before concluding.

### 3.5. Inspect enqueue locks

~~~sql
SELECT l.inst_id,
       s.sid,
       s.serial#,
       s.username,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block,
       s.event,
       s.sql_id,
       s.module
FROM   gv$lock l
JOIN   gv$session s
       ON s.inst_id = l.inst_id
      AND s.sid = l.sid
WHERE  l.request > 0
   OR  l.block = 1
ORDER  BY l.inst_id, l.block DESC, l.request DESC;
~~~

`ID1`/`ID2` depend on the enqueue type. Do not assume they are always `OBJECT_ID`. For `TX`, `TM`, and other lock types, decode them according to Oracle documentation and context.

### 3.6. Check open transactions

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.status,
       s.module,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec,
       t.xidusn,
       t.xidslot,
       t.xidsqn
FROM   gv$session s
JOIN   gv$transaction t
       ON t.inst_id = s.inst_id
      AND t.addr = s.taddr
ORDER  BY t.start_time;
~~~

`USED_UBLK` and `USED_UREC` indicate how much undo the transaction has used according to the view at query time. They help estimate rollback scale, though they do not predict exact rollback duration. Rollback speed depends on change volume, I/O, contention, redo, and recovery state.

### 3.7. Active transaction rollback progress

After a session is terminated, rollback may continue in the background. You can check fast-start transaction recovery progress when the view has rows:

~~~sql
SELECT xid,
       state,
       undoblocksdone,
       undoblockstotal,
       ROUND(
           100 * undoblocksdone / NULLIF(undoblockstotal, 0),
           2
       ) AS percent_done
FROM   v$fast_start_transactions;
~~~

Columns and states should be interpreted using the Oracle Database Reference. Not every rolling-back session appears in this view in the same way. Locks may remain held while rollback is still in progress.

### 3.8. Check distributed transactions

If a session involves a database link or distributed transaction, check in-doubt transaction state before killing or restarting:

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       advice,
       fail_time
FROM   dba_2pc_pending;
~~~

Do not unilaterally force-commit or force-rollback a distributed transaction simply because a session is waiting. Identify the coordinator, peer database, and the in-doubt transaction handling procedure.

## 4. Choosing how to handle a session

### 4.1. Prefer canceling the statement when appropriate

If only one SQL statement is runaway while the session should remain alive for the application to continue, consider SQL cancellation mechanisms supported by your release/driver and runbook. Stopping a statement does not necessarily terminate the session.

After canceling, verify:
- The statement has stopped.
- Whether the transaction remains open or has rolled back.
- Whether the session still holds locks.
- Whether the application can proceed or must roll back the transaction.
- Whether the connection pool marks the connection as invalid.

Do not assume canceling a statement automatically rolls back the entire transaction.

### 4.2. Killing a session with ALTER SYSTEM

Single-instance:

~~~sql
ALTER SYSTEM KILL SESSION '123,4567' IMMEDIATE;
~~~

RAC:

~~~sql
ALTER SYSTEM KILL SESSION '123,4567,@2' IMMEDIATE;
~~~

In the RAC example, `123` is `SID`, `4567` is `SERIAL#`, and `2` is `INST_ID`. Replace these placeholders with values just verified from `GV$SESSION`. Do not copy literal example values onto a live system.

`IMMEDIATE` instructs Oracle to terminate the session immediately under session-management rules. If the session cannot terminate immediately, Oracle may mark it for kill and return `ORA-00031`. Cleanup and rollback may continue afterward.

### 4.3. DISCONNECT SESSION

Oracle also supports:

~~~sql
ALTER SYSTEM DISCONNECT SESSION '123,4567' POST_TRANSACTION;
~~~

Or:

~~~sql
ALTER SYSTEM DISCONNECT SESSION '123,4567' IMMEDIATE;
~~~

- `POST_TRANSACTION` waits for the current transaction to complete before disconnecting.
- `IMMEDIATE` disconnects the session immediately via the disconnect mechanism.

`DISCONNECT SESSION` is commonly used to proactively terminate a session; choose the mode based on your objective and whether waiting for transaction completion is acceptable. In RAC, append `INST_ID` using supported syntax.

### 4.4. KILL SESSION does not mean the OS process vanishes immediately

Oracle manages sessions, server processes, and rollback. After a kill command:
- The session may display status `KILLED` for some time.
- The server process may still need cleanup.
- Uncommitted transactions must roll back.
- Locks may remain held until rollback/cleanup releases them.
- The client receives a connection/session terminated error.

Not seeing the session disappear immediately does not mean the command failed. Re-check `GV$SESSION`, transactions, and locks after a reasonable monitoring interval.

### 4.5. ORA-00031: session marked for kill

`ORA-00031` indicates the session has been marked for kill but could not terminate instantaneously. This can occur when the session is in a state requiring cleanup or rollback.

Do not repeatedly spam the kill command. Monitor:
- Whether the session still exists.
- Whether transaction rollback is progressing.
- Wait events and process state.
- Which objects still have locks held.
- Whether there is a distributed transaction or external call.

If cleanup remains stuck for an extended period, collect incident evidence and follow Oracle Support / DBA runbooks rather than immediately killing the OS process.

### 4.6. Avoid killing background processes

Do not kill background processes such as PMON, SMON, DBWn, LGWR, CKPT, ARCn, MMON, or internal processes just because they appear in session/process lists. These processes maintain database integrity and operation.

Filter user sessions using `TYPE='USER'`, `module`, `program`, `process`, and Oracle documentation. If you suspect a malfunctioning background process, use the alert log, trace files, and Oracle Support procedures instead of killing it directly.

### 4.7. Killing an OS process is a last resort

Do not use `taskkill`, `kill -9`, or OS-level termination as a substitute for `ALTER SYSTEM KILL SESSION`. Terminating an OS process externally forces Oracle to detect a dead process and perform recovery/rollback; choosing the wrong process can impact far more than one session.

Use OS-level termination only when required by a DBA/Oracle Support runbook, after verifying `PID`/`SPID` and instance, with proper authorization, and after evaluating recovery impact.

## 5. Evaluating transactions and kill consequences

### 5.1. Uncommitted transactions are not preserved

Killing a session is not an operation that “only releases locks.” If the session has an uncommitted transaction, Oracle must roll back all uncommitted changes to preserve atomicity.

Potential impacts include:
- Inserted rows are removed.
- Updates are undone.
- Deletes are restored.
- Locks remain held for the duration of the rollback.
- Undo/redo and I/O continue to be consumed.
- The application receives an error and may need to resubmit the request per policy.

If a transaction made millions of changes, rollback can take longer than the original SQL execution.

### 5.2. Estimate rollback scale

Use:
- Transaction start time.
- `USED_UBLK`/`USED_UREC`.
- Affected row counts and objects.
- Session wait events.
- Redo/undo generation.
- Fast-start transaction recovery metrics if present.

Do not use `USED_UBLK` to predict an exact wall-clock duration. Two transactions with the same number of undo blocks can roll back at very different speeds due to storage and contention.

### 5.3. Inactive sessions holding transactions

A session with `STATUS='INACTIVE'` may have executed DML and omitted `COMMIT` or `ROLLBACK`. It is not running SQL at the moment of inspection, yet it still holds an active transaction and locks.

In this case, contact the application owner before killing. The transaction may be part of a multi-minute business flow or require a controlled commit.

### 5.4. Connection pools may recreate sessions

When killing a session belonging to a pool:
- The pool may discard the broken connection.
- The application may open a new connection.
- In-flight requests may fail.
- Retry logic may re-run the operation.
- If the commit outcome is ambiguous, the operation risks duplicate submission.

Evaluate retry/idempotency behavior before killing application sessions. Clearing a blocker without addressing a pool leak or retry storm can cause new sessions to immediately recreate the same problem.

### 5.5. Questions to answer before killing a blocker

- Is this session the final blocker?
- Can the application be asked to commit or roll back gracefully?
- How long has the transaction been running and how much undo has it used?
- Is an important batch or ETL job involved?
- Does the session participate in a distributed transaction?
- How many blocked sessions exist and which services do they belong to?
- Will killing trigger a retry storm or duplicate requests?
- Is canceling the statement or throttling workload a lower-impact alternative?

If the owner or transaction purpose is still unknown, prioritize gathering context and coordinating rather than killing immediately.

## 6. Restarting: scoping it accurately

### 6.1. Restarting a service

A service is a logical connection endpoint for a workload. In RAC, a service can run on one or more instances according to its preferred/available instance configuration.

Restarting or relocating a service affects sessions using that service without restarting the whole database. However, currently connected sessions do not automatically move to another service/instance unless the client/driver/connection pool and HA setup support it.

Before stopping a service:
- Check how many clients/sessions use the service.
- Check preferred/available instances.
- Verify whether the service is shared by batch jobs, scheduler jobs, or other applications.
- Determine how clients reconnect.
- Check FAN/ONS/Application Continuity if used in the architecture.
- Drain workloads according to procedure.

### 6.2. Restarting a RAC instance

Restarting a single instance may be appropriate when a fault is isolated to one node or during rolling maintenance. Impacts:
- All sessions on that instance are disconnected.
- Uncommitted transactions require rollback.
- Services may relocate to surviving instances if configured.
- Surviving instances may have to absorb additional load.
- Caches, buffers, and workloads must warm up again.
- RAC interconnect traffic and service relocation may affect latency.

Check capacity on surviving instances before stopping a node. If both nodes are near CPU/memory saturation, shifting load can take down the entire cluster's serviceability.

### 6.3. Restarting a PDB

If an error is isolated to a single PDB, consider closing and opening that PDB per runbook:

~~~sql
ALTER PLUGGABLE DATABASE apppdb CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE apppdb OPEN;
~~~

Run these statements in the appropriate container with appropriate privileges. `CLOSE IMMEDIATE` disconnects the PDB's sessions; uncommitted transactions are handled as part of closing. Other PDBs in the CDB can continue operating, though they still share instance resources.

Before closing a PDB, check services, application pools, scheduler jobs, local users, and Data Guard/PDB states. Do not restart a PDB if the fault lies in the CDB root or at the instance level.

### 6.4. Restarting the entire database

Restarting the database has a much broader impact:
- Every session is disconnected.
- Uncommitted transactions are rolled back or recovered during startup.
- Service/listener registration must re-establish.
- Scheduler jobs may be interrupted.
- Connection pools must reconnect.
- Data Guard/replication/CDC pipelines may be impacted.
- Startup may require instance recovery.
- Applications need smoke testing before serving traffic.

Restart the whole database only when the root cause is identified or there is clear evidence that instance/database state requires a restart.

### 6.5. Restarting the host

Rebooting the host impacts the database instance, listener, agents, storage paths, monitoring, backups, and any other services on the same server. This is the largest blast radius among the options discussed.

Before rebooting a host, check:
- Whether multiple Oracle instances share the host.
- Whether ASM or Grid Infrastructure services are shared.
- Whether local/SCAN listeners run on the host.
- Whether application, backup, or monitoring agents reside there.
- Whether surviving RAC nodes have sufficient capacity.
- Whether Data Guard/standby is ready.
- Whether storage/network paths depend on the host.

Do not reboot a host to deal with a single session or a single SQL statement.

## 7. SHUTDOWN modes and impact levels

### 7.1. SHUTDOWN NORMAL

~~~sql
SHUTDOWN NORMAL;
~~~

Oracle waits for all connected users to disconnect on their own before closing the database. If sessions remain logged in, this command can wait indefinitely. Suitable when applications can be shut down cleanly and all users disconnect first.

### 7.2. SHUTDOWN TRANSACTIONAL

~~~sql
SHUTDOWN TRANSACTIONAL;
~~~

Oracle prevents new transactions from starting, waits for in-flight transactions to complete, then disconnects sessions and closes the database. This protects active transactions better, though it can still wait a long time if a transaction does not finish.

### 7.3. SHUTDOWN IMMEDIATE

~~~sql
SHUTDOWN IMMEDIATE;
~~~

Oracle does not wait for users to disconnect. Sessions are terminated and uncommitted transactions are rolled back; the database closes cleanly in a consistent state. This is the standard operational choice when a controlled shutdown is needed without waiting for clients to log off.

Shutdown duration can still be long due to rollback or I/O. Do not assume the database is hung just because the command does not return immediately.

### 7.4. SHUTDOWN ABORT

~~~sql
SHUTDOWN ABORT;
~~~

`ABORT` halts the instance immediately without performing a clean shutdown like `IMMEDIATE`. On the next startup, Oracle performs instance/crash recovery using redo and recovery metadata.

Use only when:
- Controlled shutdown modes cannot complete.
- A severe emergency requires halting the instance immediately.
- The DBA understands the instance recovery duration and impact.
- Directed by runbooks/Oracle Support or approved by the incident commander.

Do not use `ABORT` as a routine shortcut for fast shutdowns. It does not fix underlying faults and can delay how quickly the database becomes available again.

### 7.5. Comparing shutdown modes

| Mode | Waits for user disconnect | Waits for transactions | Disconnects sessions | Startup recovery |
| --- | --- | --- | --- | --- |
| NORMAL | Yes | Indirectly by waiting for users | Does not proactively disconnect | Clean shutdown |
| TRANSACTIONAL | Does not wait for voluntary disconnect | Yes | After transactions finish | Clean shutdown |
| IMMEDIATE | No | Does not wait for commit; rolls back uncommitted changes | Yes | Clean shutdown |
| ABORT | No | Does not wait for rollback before halting | Yes | Instance recovery required at startup |

Each mode has specific semantics documented in the Oracle SQL*Plus / Administrator's Guide. Always monitor the alert log and shutdown progress rather than judging solely by client disconnections.

## 8. Controlled restarts in RAC and Grid Infrastructure

### 8.1. Prefer SRVCTL for Clusterware-managed resources

For databases and services managed by Grid Infrastructure, use `SRVCTL` per runbook to stop/start the proper resources. Illustrative examples:

~~~bash
srvctl status database -db <db_unique_name>
srvctl status instance -db <db_unique_name> -instance <instance_name>
srvctl status service -db <db_unique_name>
~~~

Stopping an instance:

~~~bash
srvctl stop instance -db <db_unique_name> -instance <instance_name> -stopoption immediate
~~~

Restarting an instance:

~~~bash
srvctl start instance -db <db_unique_name> -instance <instance_name>
~~~

Syntax and options may vary by Grid Infrastructure release/RU. Check `srvctl` help and the Oracle Clusterware Administration Guide for your running environment.

### 8.2. Checking services before and after

Before stopping an instance:
- Check where services are running.
- Confirm services have available instances.
- Check client failover and connection pool behavior.
- Ensure surviving nodes have sufficient capacity.

After starting:
- Confirm the instance is `OPEN`.
- Confirm services are running on the expected instances.
- Check listener registration.
- Check session distribution.
- Check application health and error rates.

### 8.3. Never restart multiple RAC instances simultaneously without a plan

In RAC, restarting multiple instances simultaneously can take the entire database offline. When performing rolling maintenance, proceed sequentially:
1. Select an instance.
2. Drain/relocate services.
3. Verify workloads have moved.
4. Stop the instance.
5. Perform maintenance / start the instance.
6. Verify the instance and services are healthy.
7. Move to the next instance.

Only use a rolling procedure where supported for the specific patch or operation; do not assume every change can be applied rolling.

### 8.4. Listeners and services are distinct from the database

A listener can be restarted while the database instance remains up; database services may need to re-register afterward. If applications fail to connect, inspect the listener, service registration, and database state separately before restarting the entire database.

## 9. Restarts in Data Guard and multi-tier architectures

### 9.1. Primary and standby

Before restarting:
- Confirm the database role.
- Check transport lag and apply lag.
- Check redo destinations and broker state.
- Decide whether switchover/failover or only a restart is needed.
- Confirm the standby can absorb production workload if required by the plan.

Never restart both primary and standby at the same time without an approved DR/recovery plan.

### 9.2. Data Guard Broker

If using the broker, inspect configuration and database state with `DGMGRL` per runbook. Do not disable the broker or manually alter roles merely to clear alerts without checking redo transport/apply health.

After a restart, verify broker configuration, transport, apply status, and role transition readiness.

### 9.3. Downstream systems

A database restart can impact:
- GoldenGate/CDC.
- ETL jobs and data warehouses.
- Database links.
- Message consumers / outbox pollers.
- Scheduler / external jobs.
- Backups and monitoring.
- Application connection pools.

Record downstream checkpoints and replay capabilities. The database being open again does not mean all downstream pipelines are synchronized.

## 10. Changing parameters: determining scope and effect

### 10.1. Session parameters

`ALTER SESSION SET` modifies only the current session:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
~~~

Suitable for session-scoped settings such as NLS or supported optimizer/session controls. It does not affect other sessions.

In connection pools, sessions are reused. If you modify a session parameter, reset it before returning the connection or configure an initialization/reset hook.

### 10.2. System parameters

`ALTER SYSTEM SET` changes a parameter at system/instance scope according to the parameter's semantics and RAC/PDB layout. Do not use this statement when your goal is merely testing within one session.

General syntax example:

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = BOTH;
~~~

The value `500` is a syntax example only, not a recommendation. Determine appropriate sizing from workload metrics and application limits.

### 10.3. SCOPE=MEMORY

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = MEMORY;
~~~

Updates the parameter in instance memory for the applicable scope without writing to the SPFILE. After a restart, the value reverts to the previous persistent configuration.

Use this when testing a dynamic value in a controlled way with a rollback/evaluation plan. Do not use `MEMORY` for static parameters that cannot change dynamically at runtime.

### 10.4. SCOPE=SPFILE

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = SPFILE;
~~~

Writes the value to the SPFILE so it takes effect upon the next instance restart; does not alter current memory. Suitable for static parameters requiring a restart or when scheduling changes for the next startup.

If the database started from a PFILE, you cannot update an SPFILE this way; manage the PFILE according to change procedures.

### 10.5. SCOPE=BOTH

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = BOTH;
~~~

Writes to the SPFILE and updates memory immediately if the parameter supports dynamic modification. This is the standard approach for dynamic parameters when you want the change active now and persistent across restarts.

Do not assume every parameter supports `BOTH`. Check `ISSYS_MODIFIABLE` and any Oracle error messages.

### 10.6. Dynamic, deferred, and static

`V$PARAMETER` reports `ISSYS_MODIFIABLE`:
- `IMMEDIATE`: can be changed immediately at system scope as supported by the parameter.
- `DEFERRED`: changes take effect for new sessions according to parameter semantics.
- `FALSE`: cannot be changed dynamically at system scope; typically requires a restart to apply.

Additionally, `ISSES_MODIFIABLE` indicates whether the parameter can be modified at session scope, and `ISPDB_MODIFIABLE` indicates whether it can be modified at PDB scope. Check the appropriate columns and documentation for each parameter.

### 10.7. Static parameters cannot change immediately

If `ISSYS_MODIFIABLE='FALSE'`, running `ALTER SYSTEM SET ... SCOPE=BOTH` may fail with `ORA-02095` or a related error. Typically you must write to the SPFILE and schedule a restart:

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = SPFILE;
~~~

Do not retry with `SCOPE=MEMORY` once Oracle reports that the parameter cannot be modified dynamically.

## 11. Checking parameter values before changing

### 11.1. Runtime values

~~~sql
SELECT inst_id,
       name,
       value,
       isdefault,
       ismodified,
       isses_modifiable,
       issys_modifiable,
       ispdb_modifiable
FROM   gv$parameter
WHERE  name IN (
           'open_cursors',
           'processes',
           'sessions',
           'sga_target',
           'pga_aggregate_target',
           'optimizer_mode'
       )
ORDER  BY name, inst_id;
~~~

`GV$PARAMETER` shows current runtime values per instance. Some parameters may differ across RAC instances.

### 11.2. Values in SPFILE

~~~sql
SELECT sid,
       name,
       value,
       isspecified,
       update_comment
FROM   v$spparameter
WHERE  name IN (
           'open_cursors',
           'processes',
           'sessions',
           'sga_target',
           'pga_aggregate_target',
           'optimizer_mode'
       )
ORDER  BY name, sid;
~~~

`V$SPPARAMETER` shows persistent configuration. Runtime and SPFILE values can differ if `MEMORY` changes were applied or if `SPFILE` changes await a restart.

### 11.3. Capture pre-change state

Before changing a parameter, record:
- Name.
- Current value per instance.
- Value in the SPFILE.
- Scope/SID/PDB.
- `ISSYS_MODIFIABLE` and `ISPDB_MODIFIABLE`.
- Last modification time if available.
- Workload and baseline metrics.
- Rollback value.

Do not record only a single `SHOW PARAMETER` output if your RAC environment has instance-specific settings.

### 11.4. Check whether the parameter is modifiable in a PDB

Some parameters can be set at PDB scope, while others apply only at CDB/system scope. Check `ISPDB_MODIFIABLE` and the parameter documentation.

When connected to a PDB, verify `CON_NAME` before altering parameters. Do not run `ALTER SYSTEM` from the CDB root expecting to target a single PDB without specifying the proper container/scope.

### 11.5. Parameters in RAC

In RAC, a parameter may:
- Apply uniformly to all instances.
- Hold distinct values per instance.
- Be changed only in one instance's memory.
- Be saved in the SPFILE for a specific `SID` or for `SID='*'`.

Inspect both `GV$PARAMETER` and `V$SPPARAMETER` before making edits. Do not assume changing one instance updates the entire cluster.

## 12. Changing parameters in RAC and PDBs

### 12.1. SID='*' and specific SID

Set a shared parameter across instances in the SPFILE:

~~~sql
ALTER SYSTEM SET parameter_name = value
SCOPE = SPFILE SID = '*';
~~~

Set a parameter for one specific instance:

~~~sql
ALTER SYSTEM SET parameter_name = value
SCOPE = SPFILE SID = 'orcl2';
~~~

The `SID` value must be the exact instance name. Whether memory/runtime updates apply immediately depends on the parameter and statement; verify `GV$PARAMETER` after making the change or restarting.

### 12.2. Avoiding parameter drift across instances

If the same service can run on multiple instances whose parameters differ, sessions relocating between instances may exhibit inconsistent behavior. This can cause issues that appear only during load balancing or failover.

Document the reason for every instance-specific parameter. After a rolling restart, verify that each instance has the intended configuration.

### 12.3. PDB scope

Parameters permitting PDB modification can be set inside a PDB using appropriate syntax and privileges. Example while targeting a PDB:

~~~sql
ALTER SESSION SET CONTAINER = APPPDB;
ALTER SYSTEM SET parameter_name = value SCOPE = BOTH;
~~~

Do not apply this pattern to every parameter blindly. Verify `ISPDB_MODIFIABLE`, the PDB's open state, and the Oracle Multitenant Administrator's Guide. If a parameter can only be set at CDB level, running it inside a PDB will fail.

### 12.4. Post-change verification

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;
~~~

Then re-read `GV$PARAMETER`/`V$PARAMETER` and `V$SPPARAMETER` in the right container/instance. Verify both new sessions and existing sessions if the parameter has `DEFERRED` semantics.

## 13. Impact assessment by parameter category

### 13.1. Memory parameters

Examples:
- `SGA_TARGET`.
- `SGA_MAX_SIZE`.
- `PGA_AGGREGATE_TARGET`.
- `MEMORY_TARGET`.
- `MEMORY_MAX_TARGET`.
- `DB_CACHE_SIZE`.
- `SHARED_POOL_SIZE`.

Impacts:
- Contention for RAM with the OS and other processes.
- Changes in cache hit/miss ratios and workload latency.
- Multi-instance impact if RAC or multiple DBs share the host.
- Restart requirement for certain memory parameters or configurations.
- Risk of OOM kills or OS swapping if overallocated.

Before increasing memory parameters, check actual physical RAM, OS headroom, huge pages, AMM/ASMM mode, PGA usage, and container/VM limits. Never increase SGA solely because one query is slow without identifying its wait class.

### 13.2. Process/session parameters

Examples:
- `PROCESSES`.
- `SESSIONS`.
- `OPEN_CURSORS`.

Impacts:
- Restart required for parameters such as `PROCESSES`.
- Raising session/process limits increases potential memory and OS process consumption.
- A larger `OPEN_CURSORS` does not fix cursor leaks; it only raises the per-session open cursor cap.
- Overly large connection pools can still exhaust higher session limits.

Measure peak concurrent sessions, process counts, cursor usage, and pool configurations before raising limits.

### 13.3. Optimizer parameters

Examples:
- `OPTIMIZER_MODE`.
- `OPTIMIZER_FEATURES_ENABLE`.
- Other optimizer-related parameters.

Impacts:
- Execution plans may change.
- SQL latency may improve or regress per query.
- Bind peeking, adaptive behavior, and cursor sharing may be affected.
- System-wide changes can cause regressions across unrelated workloads.

Do not alter an optimizer parameter database-wide to fix a single query without inspecting SQL plans, statistics, bind values, and impact scope. Consider SQL Plan Management or statement-level approaches when appropriate.

### 13.4. Undo/redo parameters

Changes involving undo, redo, archiving, and recovery can affect transaction consistency, recovery windows, archive destinations, and recoverability.

Do not alter retention, undo tablespace settings, or archive behavior without evaluating:
- Long-running transactions.
- Flashback Query / Flashback Database requirements.
- Backup and archived redo policies.
- FRA capacity.
- Data Guard transport/apply.
- Recovery objectives (RPO/RTO).

### 13.5. Network and security parameters

Modifying listener/network encryption, timeouts, wallets, authentication, or security parameters can block clients from connecting. Check:
- JDBC/OCI driver compatibility.
- TLS/certificates/wallets.
- Connection pools.
- Listener endpoints.
- Client configs across all application nodes.
- Rollback path if older clients are incompatible.

### 13.6. Underscore / hidden parameters

Parameters starting with an underscore are typically hidden/undocumented parameters. Never change them simply because you found them in a forum thread or blog post.

Use them only when explicitly instructed by Oracle Support or official documentation for the exact scenario, with an SR/change record, specified values, and a rollback plan. Hidden parameters can change behavior across RUs and cause unpredictable side effects.

## 14. Safe parameter change workflow

### Step 1 — Record the current state

Save `GV$PARAMETER`, `V$SPPARAMETER`, `SHOW PARAMETER`, database role, instance/PDB, and baseline metrics.

### Step 2 — Confirm the objective

Clearly state:
- The symptom to resolve.
- Why this parameter is relevant.
- Expected behavioral change.
- Scope (session/instance/database/PDB).
- Whether it is dynamic or requires a restart.
- Potential impact on other workloads.

### Step 3 — Check documentation and modifiability

Check:
- `ISSYS_MODIFIABLE`.
- `ISSES_MODIFIABLE`.
- `ISPDB_MODIFIABLE`.
- Instance-specific behavior.
- `COMPATIBLE`/version restrictions.
- Licensing if the parameter enables a licensed option.

### Step 4 — Choose the scope

- `SESSION`: test in a single session when applicable.
- `MEMORY`: test at runtime without persisting.
- `SPFILE`: persist for the next restart.
- `BOTH`: runtime and persistent if dynamic.
- `SID`: target a specific instance or cluster-wide (`'*'`).
- `CONTAINER`: target the right CDB/PDB scope.

### Step 5 — Change one variable at a time

Do not change multiple parameters simultaneously if you need to know which change caused an improvement or regression. Use a change window and record the timestamp and operator.

### Step 6 — Observe immediately after the change

Monitor:
- Alert log.
- `ORA-` errors.
- Session/process counts.
- CPU/memory usage.
- Wait events.
- SQL plans/latency.
- Connection pools.
- Service/PDB availability.
- Data Guard/replication if applicable.

### Step 7 — Decide whether to keep or roll back

Compare metrics against baseline and pre-defined criteria. If expectations are not met, restore the prior value in the appropriate scope. If a static parameter was written to SPFILE, schedule a restart to apply the rollback value.

### Step 8 — Record the final configuration

Save runtime values, SPFILE values, instance/PDB, scope, timestamp, and change outcome. Update configuration management so future deployments do not overwrite the setting unintentionally.

## 15. Parameter and configuration rollback

### 15.1. Restoring runtime and persistent values

If the parameter was dynamic and set with `BOTH`:

~~~sql
ALTER SYSTEM SET parameter_name = old_value SCOPE = BOTH;
~~~

Use the recorded previous value rather than guessing defaults.

### 15.2. Restoring SPFILE for static parameters

~~~sql
ALTER SYSTEM SET parameter_name = old_value
SCOPE = SPFILE SID = '*';
~~~

Then restart the appropriate scope for the value to take effect. If only the SPFILE is updated without a restart, runtime values remain unchanged.

### 15.3. RESET parameter

You can remove an entry from the SPFILE to fall back to defaults or inherited values per parameter rules:

~~~sql
ALTER SYSTEM RESET parameter_name
SCOPE = SPFILE SID = '*';
~~~

`RESET` does not mean “restore the previous pre-change value” if an explicit value was previously configured. Use it only after checking inherited configuration and expected default behavior.

### 15.4. Rolling back session state

For session parameters, run `ALTER SESSION` to restore original values or close the session. With pools, ensure connections are reset before returning to the pool.

Do not reset only on the success code path; handle exceptions/finally blocks so session state never leaks into the next request.

## 16. Action selection matrix

| Symptom | First action to consider | Conditions to escalate |
| --- | --- | --- |
| One runaway SQL | Cancel statement if supported | SQL fails to stop, session causes severe impact, and transaction impact is understood |
| One session blocking many waiters | Identify final blocker and transaction | Owner cannot end it safely and impact is approved |
| Inactive session holding locks | Verify transaction and owner | Rollback/business impact has been evaluated |
| Service not accepting connections | Check listener, service, and PDB | Service/resource actually faulted and move/restart plan exists |
| One RAC instance failing | Drain/relocate services, restart instance | Node cannot recover or requires maintenance |
| One PDB failing | Check PDB/service/sessions | Fault is isolated to PDB and session/transaction impact is assessed |
| Entire database unstable | Collect alert/instance evidence | Clear justification for database restart and recovery plan ready |
| Parameter causing bad behavior | Test smallest supported scope | Scope, dynamic/static status, and rollback path confirmed |
| Static parameter needs change | Write SPFILE and schedule restart | Downtime/rolling strategy prepared if supported |
| Host/storage/network failure | Coordinate infrastructure and DBA teams | Host reboot per DR/maintenance runbook |

## 17. Real-world scenarios

### 17.1. DDL blocked by a long-running transaction

Scenario:
- `ALTER TABLE` is waiting on a lock.
- An application session is inactive yet holds an open transaction.
- Multiple requests queue behind the DDL or target object.

Handling:
1. Locate the direct blocker and final blocker.
2. Identify owner/module/client identifier.
3. Check transaction start time, undo blocks, and previous SQL.
4. Ask the application owner if it can commit or roll back gracefully.
5. If killing is required, document that the transaction will roll back and locks may not release instantaneously.
6. Monitor rollback progress and the blocker chain.
7. Re-run the DDL with a bounded timeout within a suitable window.

Never kill a waiter; identify the true blocker first.

### 17.2. One query consuming high CPU

Scenario:
- CPU usage spikes.
- One `SQL_ID` consumes significant DB time.
- Other sessions slow down.

Handling:
1. Identify the `SQL_ID`, plan, module, and number of concurrent sessions running it.
2. Determine whether the query is a legitimate batch job or runaway.
3. Inspect execution plan, bind values, and wait class.
4. If only the statement needs stopping, use a supported SQL cancel mechanism.
5. Kill the session only if session termination is required and transaction impact is assessed.
6. Monitor pool retries and new session creation.
7. Fix the SQL/plan/root cause after stabilization.

Never restart the database just because one SQL statement spikes CPU.

### 17.3. Session count hitting the limit

Scenario:
- Applications receive errors unable to open more sessions.
- Many sessions are `INACTIVE`.
- Connection pools may be oversized or leaking.

Handling:
1. Group sessions by username, service, module, and machine.
2. Compare against pool max sizes and replica counts.
3. Identify whether inactive sessions hold open transactions.
4. Fix connection leaks or pool sizing.
5. Kill sessions only after confirming stale connections and transaction impact.
6. Raise `PROCESSES`/`SESSIONS` only after calculating memory/process capacity and restart requirements.

Simply raising limits may only delay failure and increase overall load.

### 17.4. A RAC instance needs a restart

Scenario:
- One instance shows abnormal waits or errors.
- Surviving instances can host the services.

Handling:
1. Inspect `GV$INSTANCE`, `GV$ACTIVE_SERVICES`, and session distribution.
2. Check capacity on surviving instances.
3. Verify client failover and connection pool behavior.
4. Drain or relocate services per runbook.
5. Stop the instance using Clusterware tools.
6. Start the instance and verify open mode.
7. Check service placement, listener registration, and application health.
8. Monitor workload redistribution.

Never stop a second instance before the first instance and services are verified stable.

### 17.5. A static parameter must be changed

Scenario:
- Oracle reports the parameter cannot be modified dynamically.
- A new value is needed to support workload changes.

Handling:
1. Check `ISSYS_MODIFIABLE` and `V$SPPARAMETER`.
2. Determine whether the parameter applies cluster-wide or per instance.
3. Record current runtime and SPFILE values.
4. Verify memory/resource headroom and compatibility.
5. Set the new value in the SPFILE.
6. Schedule a restart for the appropriate scope.
7. After restarting, verify both runtime and SPFILE values.
8. Run smoke tests and compare workload metrics.
9. If a regression occurs, restore the old value and restart per plan.

## 18. Pre-change checklist for kills, restarts, and parameter changes

### Evidence

- [ ] Incident/change ID and start time recorded.
- [ ] Database, role, instance, service, and PDB identified.
- [ ] Involved sessions/SQL/parameters identified.
- [ ] Alert log, wait events, and metric baselines saved.
- [ ] Blocker chain identified if applicable.

### Transactions and data

- [ ] Open transactions checked.
- [ ] Undo/rollback impact estimated.
- [ ] Distributed transactions checked if present.
- [ ] Commit outcome and retry/idempotency assessed.
- [ ] Potential lock retention during rollback accounted for.

### Intervention scope

- [ ] Correct session/service/PDB/instance/database/host scope chosen.
- [ ] Session uniquely identified by `SID` + `SERIAL#` + `INST_ID`.
- [ ] Confirmed target session is not a background process.
- [ ] Service failover and RAC capacity verified.
- [ ] Restart impact on Data Guard/CDC/batch assessed.

### Parameters

- [ ] `GV$PARAMETER` and `V$SPPARAMETER` saved.
- [ ] Dynamic/static modifiability and session/system/PDB scope checked.
- [ ] `SCOPE` and `SID` explicitly defined.
- [ ] Rollback value documented.
- [ ] CPU/memory/optimizer/network/security impacts evaluated.
- [ ] Hidden parameters avoided unless officially instructed.

### Execution and verification

- [ ] Owner / incident commander approval obtained per procedure.
- [ ] Maintenance window or clear abort/stop criteria defined.
- [ ] Blockers, rollback, startup, and alert log monitored.
- [ ] Post-action session/service/instance/database state verified.
- [ ] Application reconnection and error rates checked.
- [ ] Runtime and SPFILE parameter values verified in the right scope.
- [ ] Results, timestamps, and next steps documented.

## 19. Practice labs

Perform these in a test database using two separate sessions and recoverable data. Never kill sessions, restart instances, or change parameters in production just to experiment.

### Lab 1 — Create a blocking transaction

Session A updates a row without committing. Session B updates the same row. Observe blocker/waiter details via `GV$SESSION`.

### Lab 2 — Identify the transaction

Join `GV$SESSION` with `GV$TRANSACTION`. Record `USED_UBLK`, `USED_UREC`, and `START_TIME` before ending the transaction.

### Lab 3 — Kill a session in a lab

Use the verified `SID`/`SERIAL#` to kill the test session. Observe `KILLED` state, rollback progress, and when the lock is released.

### Lab 4 — Disconnect POST_TRANSACTION

Start a test transaction and run `DISCONNECT SESSION POST_TRANSACTION`. Commit from the original session per the test procedure and observe the disconnect.

### Lab 5 — ORA-00031

In a controlled scenario, observe `session marked for kill` if triggered. Monitor cleanup instead of repeating the kill command.

### Lab 6 — DDL_LOCK_TIMEOUT

Hold a DML lock, set `DDL_LOCK_TIMEOUT=5` in another session, and attempt `ALTER TABLE`. Record the wait duration and outcome.

### Lab 7 — Shutdown modes

In a restartable test database, compare `NORMAL`, `TRANSACTIONAL`, and `IMMEDIATE`. Do not use `ABORT` unless specifically studying crash recovery.

### Lab 8 — PDB restart

Close and open a test PDB. Verify PDB sessions disconnect while CDB root and other PDBs remain operational as designed.

### Lab 9 — MEMORY parameter

Change a suitable dynamic parameter with `SCOPE=MEMORY`. Verify `GV$PARAMETER` changes while `V$SPPARAMETER` does not; restart the lab instance to observe the value reverting.

### Lab 10 — SPFILE parameter

Change a lab parameter with `SCOPE=SPFILE`. Confirm runtime is unchanged and SPFILE is updated; restart the lab instance and verify the runtime value.

### Lab 11 — BOTH parameter

Choose an allowed dynamic parameter and change it with `SCOPE=BOTH`. Confirm both runtime and SPFILE values.

### Lab 12 — Session parameters and pools

Modify NLS or timezone settings in a session. Return the connection to a test pool and borrow it again to observe lingering session state; implement a reset hook.

### Lab 13 — RAC scope

In a test RAC environment, compare `GV$PARAMETER` and `V$SPPARAMETER` using `SID='*'` vs. a specific `SID`. Never test parameter changes in production.

### Lab 14 — Write an incident runbook

Choose a blocker, runaway SQL, or static parameter scenario. Document required evidence, blast radius, planned commands, stop criteria, rollback steps, and validation checks.

## 20. Oracle reference documentation

- [Oracle Database 19c SQL Language Reference — ALTER SYSTEM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SYSTEM.html): changing parameters and terminating sessions.
- [Oracle Database 19c SQL Language Reference — ALTER SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SESSION.html): modifying session settings.
- [Oracle Database 19c Administrator's Guide — Starting Up and Shutting Down](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/starting-up-and-shutting-down.html): shutdown modes and startup procedures.
- [Oracle Database 19c Administrator's Guide — Managing Processes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-processes.html): session and process management.
- [Oracle Database 19c Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session state, SQL, blockers, and client metadata.
- [Oracle Database 19c Database Reference — V$TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html): transactions and undo usage.
- [Oracle Database 19c Database Reference — V$PARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PARAMETER.html): runtime parameter values and modifiability.
- [Oracle Database 19c Database Reference — V$SPPARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SPPARAMETER.html): parameter values in SPFILE.
- [Oracle Database 19c Database Reference — DDL_LOCK_TIMEOUT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DDL_LOCK_TIMEOUT.html): DDL lock wait timeout.
- [Oracle Real Application Clusters Administration and Deployment Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/): services, instances, and `SRVCTL`.
- [Oracle Database 19c Data Guard Broker Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/): inspecting and operating Data Guard configurations.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/): usage terms for licensed features.

Killing sessions, restarting, and changing parameters may all be necessary during incident response, yet each action carries distinct scope and consequences. Killing a session can trigger a long rollback and keep locks held until cleanup completes; restarting drops connections within the stopped scope and may require instance recovery; changing a parameter can affect one session, one instance, a PDB, or the entire database, immediately or after a restart. **Save evidence and configuration values before intervening, assess transactions and blast radius, choose the narrowest scope that meets the objective, and verify state and workload after the change.**
