# ALTER SYSTEM, ALTER SESSION, and Restart Requirements in Oracle

Oracle Database allows configuration changes at multiple scopes. The **ALTER SESSION** statement changes settings for the current session. The **ALTER SYSTEM** statement changes parameters or state at the instance/database scope depending on privileges and operation type. Some parameters can be changed while the database is running; others are written only to the SPFILE and take effect after a restart.

When changing an initialization parameter, four things must be determined:

1. Does the change apply to the current session, new sessions, the current instance, or all instances?
2. Is the parameter dynamic or static?
3. Does the value only need to take effect in memory, be saved to the SPFILE, or both?
4. Does the instance/database need a restart, or do services/cluster resources need changes?

Not every change requires a restart. Conversely, attempting to change a static parameter with ALTER SYSTEM while the instance is running will be rejected. Using the wrong SCOPE can also cause a change to be only temporary or fail to persist across the next restart.

This lesson belongs to the **Operations** topic of *Database Engine Relational Oracle*. Its content focuses on:

- Differences between ALTER SYSTEM and ALTER SESSION.
- Session, instance, database, RAC, and CDB/PDB scopes.
- Dynamic/static parameters and ISSYS_MODIFIABLE.
- SCOPE=MEMORY, SCOPE=SPFILE, SCOPE=BOTH.
- SID, DEFERRED, RESET, and PFILE/SPFILE configuration.
- Determining whether a parameter requires a restart.
- Checking configuration via V$PARAMETER and V$SPPARAMETER.
- Safe change, verification, rollback, and maintenance procedures.
- SQL lab exercises in a lab schema/database.

## 1. Two Configuration Layers: Session and System

Oracle maintains configuration values at multiple scopes. You can visualize this as:

~~~text
Initialization parameter in SPFILE/PFILE
                 |
                 v
         Instance runtime value
                 |
                 v
       Session-level override
                 |
                 v
       Current SQL operation
~~~

The SPFILE/PFILE provides configuration values when the instance starts. The instance loads those values into memory. Some parameters allow individual sessions to override them via ALTER SESSION. Session changes do not automatically write back to the instance or SPFILE.

### ALTER SESSION

ALTER SESSION changes attributes or parameters for the currently connected session. For example:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
ALTER SESSION SET CURRENT_SCHEMA = SALES;
ALTER SESSION SET optimizer_mode = ALL_ROWS;
~~~

This change does not affect other sessions, does not update the system value, and does not persist after the session ends.

### ALTER SYSTEM

ALTER SYSTEM changes parameters at the system/instance scope or performs system administrative operations. For example:

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = BOTH;
~~~

The command above requests changing OPEN_CURSORS in memory and writing it to the SPFILE, provided the parameter allows dynamic modification and the instance uses an SPFILE. The actual scope also depends on SID/container and parameter type.

### Not Everything in ALTER SYSTEM Is an Initialization Parameter

ALTER SYSTEM also has other operational commands, such as:

~~~sql
ALTER SYSTEM CHECKPOINT;
ALTER SYSTEM SWITCH LOGFILE;
ALTER SYSTEM ENABLE RESTRICTED SESSION;
~~~

These commands perform administrative actions, not initialization parameter value changes. Therefore, the concept of SCOPE=MEMORY/SPFILE/BOTH applies only to the ALTER SYSTEM SET parameter syntax, not to every ALTER SYSTEM statement.

## 2. ALTER SESSION: Changes for the Current Session

ALTER SESSION is commonly used to adjust how a session interprets data, optimizes SQL, handles formatting, time, or execution behavior within a single connection.

### Basic Syntax

~~~sql
ALTER SESSION SET parameter_name = value;
~~~

Not every initialization parameter can be set at the session level. You must check the ISSES_MODIFIABLE attribute or parameter documentation.

### NLS Examples

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
~~~

NLS parameters affect data conversion/display within the session. Applications should pass proper datatypes and use explicit format models rather than relying on the default NLS_DATE_FORMAT.

### Optimizer Examples

~~~sql
ALTER SESSION SET optimizer_mode = ALL_ROWS;
ALTER SESSION SET optimizer_index_cost_adj = 50;
~~~

The second example should only be used if the parameter can be set in a session in the running version. Do not change global optimizer parameters just to force a single query; prioritize checking plans, statistics, and SQL-specific controls first.

### CURRENT_SCHEMA Example

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES;
~~~

CURRENT_SCHEMA changes the default schema used when resolving unqualified object names. It does not grant additional privileges on the SALES schema. The user must still have the required privileges to access objects.

### Time Zone Example

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';
~~~

The session time zone affects certain operations with TIMESTAMP WITH LOCAL TIME ZONE and related functions. It does not change DBTIMEZONE or the OS time zone.

### Example Enabling Execution Statistics

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

STATISTICS_LEVEL can cause Oracle to collect additional runtime statistics/advisory data depending on the level. Use it selectively in a diagnostic session; consider overhead and restore the initial value after testing.

### Viewing Session Values

~~~sql
SELECT name, value
FROM v$ses_optimizer_env
WHERE sid = SYS_CONTEXT('USERENV', 'SID')
ORDER BY name;
~~~

V$SES_OPTIMIZER_ENV focuses on the session's optimizer environment, not a list of all session parameters. For initialization parameters, V$PARAMETER reflects current instance values; some session-modifiable values can be observed via session-specific views or release-appropriate queries.

### Session Pools and Resetting Configuration

Applications using connection pools typically reuse sessions. If request A sets CURRENT_SCHEMA, NLS_DATE_FORMAT, TIME_ZONE, or an optimizer setting and returns the connection to the pool without resetting it, request B may receive a session with leftover state.

Pool design should:

- Set session state explicitly when checking out a connection.
- Reset state when returning a connection to the pool or use callbacks/init SQL.
- Not assume a fresh session for every request.
- Not set session-specific settings via ALTER SYSTEM to fix a single request's bug.

## 3. ALTER SYSTEM SET: Changing Initialization Parameters

ALTER SYSTEM SET is used to change the value of an initialization parameter at the instance/system scope.

### General Syntax

~~~sql
ALTER SYSTEM SET parameter_name = value
    [COMMENT = 'text']
    [DEFERRED]
    [SCOPE = MEMORY | SPFILE | BOTH]
    [SID = '*' | 'instance_name']
    [CONTAINER = CURRENT | ALL];
~~~

Not every clause exists in every Oracle release or applies to every parameter type. Follow the syntax in the documentation for your actual version.

### Example Changing a Dynamic Parameter

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = BOTH;
~~~

If OPEN_CURSORS allows dynamic modification, the new value takes effect in the current instance and is written to the SPFILE to persist across restarts. Sessions that already have open cursors will not be closed simply because the new limit changed; the parameter governs the per-session cursor limit.

### COMMENT

~~~sql
ALTER SYSTEM SET open_cursors = 500
    SCOPE = SPFILE
    COMMENT = 'Change ticket CHG-1042';
~~~

COMMENT can store a description alongside the entry in the SPFILE to help DBAs identify the reason for the change. Record the change ticket ID and purpose; do not record passwords or secrets.

### Changing Multiple Parameters

Multiple separate ALTER SYSTEM SET statements can be executed. Each statement succeeds or fails independently; do not treat a series of statements as a transaction that can be rolled back with ROLLBACK. The SPFILE is a configuration file, not a transactional table.

Before changing multiple parameters, save a configuration snapshot and determine the restart order/conditions. If a statement fails mid-way, compare runtime and SPFILE values to see which parts were applied.

## 4. SCOPE=MEMORY, SPFILE, and BOTH

SCOPE determines where the change is applied.

| SCOPE | Impact | After Restart |
| --- | --- | --- |
| MEMORY | Changes the runtime value in the current instance's memory, if the parameter allows | Lost; the instance reloads the value from the configuration file |
| SPFILE | Writes the value to the SPFILE, does not change current runtime | Takes effect when the instance restarts |
| BOTH | Changes runtime and writes to the SPFILE | Continues to take effect after restart |

### SCOPE=MEMORY

~~~sql
ALTER SYSTEM SET open_cursors = 600 SCOPE = MEMORY;
~~~

The change applies only in instance memory. It is useful for testing a dynamic value without persisting it. On restart, the value from the SPFILE/PFILE is reloaded.

### SCOPE=SPFILE

~~~sql
ALTER SYSTEM SET open_cursors = 600 SCOPE = SPFILE;
~~~

The command writes only to the SPFILE. V$PARAMETER may continue showing the old runtime value until an appropriate restart. V$SPPARAMETER shows the value stored in the SPFILE.

### SCOPE=BOTH

~~~sql
ALTER SYSTEM SET open_cursors = 600 SCOPE = BOTH;
~~~

The command applies the runtime change and saves it to the SPFILE. This is the common approach for dynamic parameters when you want the change to take effect immediately and persist across restarts.

### Static Parameters Can Only Be Set in SPFILE

Parameters that cannot be modified dynamically while the instance is running typically require:

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = SPFILE;
~~~

Then restart the instance for the new value to take effect. Do not use SCOPE=BOTH for static parameters.

### When Started with a PFILE

If the instance was started with a PFILE instead of an SPFILE, operations requesting an SPFILE write may fail with an error such as ORA-32001. In this configuration, SCOPE=MEMORY can apply dynamic runtime changes; to persist across restarts, the DBA must edit the PFILE used at startup or switch to an SPFILE per procedure.

### Do Not Rely on the Default SCOPE

The default SCOPE may depend on whether the instance uses an SPFILE/PFILE and the parameter type. In production scripts, specify SCOPE explicitly so readers know whether the change is runtime-only, persistent-only, or both.

## 5. Dynamic and Static Initialization Parameters

Not every initialization parameter can be modified while the instance is running. Oracle describes modifiability using the ISSYS_MODIFIABLE attribute in V$PARAMETER:

| ISSYS_MODIFIABLE | Meaning |
| --- | --- |
| IMMEDIATE | Can be changed with ALTER SYSTEM while the instance is running; the change takes effect immediately per parameter semantics. |
| DEFERRED | Can be changed while the instance is running, but applies only to sessions starting after the change. |
| FALSE | Cannot be changed dynamically; the value must be written to the SPFILE/PFILE and restarted to take effect. |

Some parameters also have ISSES_MODIFIABLE indicating whether ALTER SESSION can be used. This is a different attribute from ISSYS_MODIFIABLE.

### Checking Specific Parameters

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isses_modifiable,
       isinstance_modifiable,
       ispdb_modifiable,
       isdefault,
       ismodified,
       isadjusted
FROM v$parameter
WHERE name IN (
    'open_cursors',
    'processes',
    'sessions',
    'sga_target',
    'memory_target',
    'db_block_size',
    'optimizer_mode'
)
ORDER BY name;
~~~

Do not guess static/dynamic status from the name or experience from a different version. Check the exact database release, platform, and parameter.

### Dynamic Parameter Example

OPEN_CURSORS is usually a dynamically modifiable parameter:

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = BOTH;
~~~

Then check V$PARAMETER and V$SPPARAMETER to confirm runtime/persistent values.

### Static Parameter Example

PROCESSES is an example of a parameter that usually requires a restart to change:

~~~sql
ALTER SYSTEM SET processes = 800 SCOPE = SPFILE;
~~~

The new value is loaded only when the instance restarts. Changing PROCESSES can affect SESSIONS configuration, process limits, memory, and applications; you must perform capacity calculations before modifying it.

### ORA-02095

When attempting to modify a non-dynamically-modifiable parameter via ALTER SYSTEM SET with SCOPE=MEMORY or BOTH, Oracle may return ORA-02095: specified initialization parameter cannot be modified. Check ISSYS_MODIFIABLE; if FALSE, write to SPFILE and schedule a restart.

### Modifiable Does Not Mean It Should Be Modified

A parameter with ISSYS_MODIFIABLE=IMMEDIATE can still impact the entire instance, shared pool, memory, optimizer, or active sessions. Modifiability does not mean risk-free. Read the parameter documentation and measure impact before adjusting.

## 6. DEFERRED: Changes Apply Only to New Sessions

A parameter with ISSYS_MODIFIABLE=DEFERRED can be modified while the instance is running, but the new value applies to sessions that start after the change. Existing sessions continue using the old value.

Illustrative example with a parameter that supports deferred modification:

~~~sql
ALTER SYSTEM SET parameter_name = value DEFERRED SCOPE = BOTH;
~~~

Do not run this example verbatim because parameter_name/value are placeholders. Check ISSYS_MODIFIABLE and the specific parameter documentation before using DEFERRED.

### Why Do Deferred Parameters Exist?

Some settings are read or fixed when a session initializes. Changing them mid-lifecycle of a session could cause inconsistent behavior. Oracle therefore allows changing the default for future sessions without forcing active sessions to change state mid-flight.

### How to Verify

1. Open session A.
2. The DBA changes a parameter that supports DEFERRED.
3. Session A continues using the value it received when initialized.
4. Open session B after the change.
5. Session B receives the new value per parameter behavior.

To verify, use views/session instrumentation appropriate for that parameter; do not assume V$PARAMETER always displays every session-level effective value.

### DEFERRED Is Not a Restart

DEFERRED means new sessions, not a new instance. If a parameter has ISSYS_MODIFIABLE=DEFERRED, the change can take effect for new sessions without restarting the instance. If ISSYS_MODIFIABLE=FALSE, a restart is required; adding the DEFERRED keyword does not turn a static parameter into a dynamic one.

## 7. When Is a Restart Required?

A parameter requires a restart when Oracle marks ISSYS_MODIFIABLE=FALSE or the parameter documentation states that changes take effect only at startup. In that case:

1. Write the new value to the SPFILE using SCOPE=SPFILE.
2. Verify the saved value in V$SPPARAMETER.
3. Choose a maintenance window and determine downtime impact.
4. Shut down/start up the instance per operational procedures.
5. Verify the runtime value after startup.
6. Check the alert log, services, PDBs, application connections, and workloads.

### Example Preparing a Static Parameter Change

~~~sql
ALTER SYSTEM SET processes = 800 SCOPE = SPFILE;

SELECT name, value, isspecified
FROM v$spparameter
WHERE name = 'processes';
~~~

V$SPPARAMETER reflects the value stored in the SPFILE. If the instance uses a PFILE, the SPFILE write command may fail; you must identify the actual startup file.

### Restarting the Instance

In a directly managed single-instance environment:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP;
~~~

This operation disrupts connections. SHUTDOWN IMMEDIATE waits for necessary operations per Oracle semantics, rolls back uncommitted transactions, and closes the database. Before running it, obtain approval, verify backup/recovery readiness, and notify application owners.

### Oracle RAC / Grid Infrastructure

For RAC or databases managed by Clusterware/Oracle Restart, use SRVCTL per your environment's procedures to stop/start the database or instances. Do not arbitrarily run SQL*Plus STARTUP/SHUTDOWN on a Clusterware-managed instance if it bypasses operational procedures.

Example SRVCTL syntax varies by release:

~~~text
srvctl stop instance -db <db_unique_name> -instance <instance_name>
srvctl start instance -db <db_unique_name> -instance <instance_name>
~~~

Confirm exact syntax with srvctl help on the active Oracle Home. For rolling changes, consider that parameters may differ between instances and check the impact on service placement.

### Restart the Database or Only Restart a PDB?

In multitenant, some parameters can be set at the PDB scope; others are meaningful only at the CDB/instance scope. Do not assume a static parameter in a PDB always requires restarting the entire CDB or can always be applied by closing/opening the PDB. Check ISPDB_MODIFIABLE, container scope, and parameter documentation.

## 8. SID and Multi-Instance Configuration (RAC)

In Oracle RAC, multiple instances open the same database together. The SPFILE can contain default values applying to all instances as well as values specific to each SID.

### SID='*'

~~~sql
ALTER SYSTEM SET open_cursors = 600
    SCOPE = SPFILE
    SID = '*';
~~~

SID='*' specifies a shared value for instances, unless an instance-specific configuration takes precedence per Oracle rules.

### Per-Instance SID

~~~sql
ALTER SYSTEM SET open_cursors = 700
    SCOPE = SPFILE
    SID = 'orcl2';
~~~

Example setting a specific value for instance ORCL2. The SID name must match the actual instance name; do not use a service name or DB_UNIQUE_NAME if they are not the SID.

### Viewing SPFILE Entries by SID

~~~sql
SELECT sid,
       name,
       value,
       isspecified
FROM v$spparameter
WHERE name = 'open_cursors'
ORDER BY sid;
~~~

### Viewing the Current Instance

~~~sql
SELECT instance_name,
       host_name,
       version,
       status
FROM v$instance;
~~~

### RAC and Runtime Propagation

Changing a parameter on one instance does not mean every instance has received the same runtime value. You must check each instance, determine whether the parameter is modifiable at the instance scope, and use SID/Clusterware properly. For static parameters, the SPFILE value can be written first and applied as each instance restarts.

### Rolling Restart

Some changes can be rolled out instance-by-instance in RAC to minimize downtime; others require all instances to stop or follow a special sequence. Do not assume every static parameter is rolling-compatible. Check Oracle documentation, RAC rolling patch/upgrade guidance, and application service behavior.

## 9. PFILE and SPFILE

Oracle has two common initialization file formats:

- **PFILE:** a text file editable with an OS text editor, typically named init.ora.
- **SPFILE:** a binary server parameter file managed by Oracle; use ALTER SYSTEM SET to update entries.

At startup, Oracle reads either a PFILE or SPFILE to create the instance. SPFILE is typically preferred if present in the default location and configured for the environment.

### Identify Which SPFILE the Instance Uses

~~~sql
SHOW PARAMETER spfile;

SELECT value
FROM v$parameter
WHERE name = 'spfile';
~~~

If VALUE is non-empty, the instance was started from an SPFILE. If empty, the instance was typically started from a PFILE or another configuration source per platform mechanisms.

### Create PFILE from SPFILE

~~~sql
CREATE PFILE = '/tmp/initORCL.ora' FROM SPFILE;
~~~

The PFILE is created on the database server's filesystem, not on the client machine. It is a useful text copy for inspecting/saving a configuration snapshot; protect the file if it contains sensitive information.

### Create SPFILE from PFILE

~~~sql
CREATE SPFILE FROM PFILE = '/tmp/initORCL.ora';
~~~

The command creates an SPFILE from the PFILE at the default location if no path is specified. Requires SYSDBA privilege and must adhere to instance state/deployment setup. In RAC, the shared SPFILE is typically placed on ASM/shared storage per Clusterware configuration.

### Start Up with an Explicit PFILE

~~~sql
STARTUP PFILE = '/tmp/initORCL.ora';
~~~

The PFILE path is server-side. If you need to start from a specific configuration file, verify the file exists, has read permissions, and contains valid parameters before stopping the instance.

### Why Does SCOPE=SPFILE Fail?

If the instance was not started with an SPFILE, ALTER SYSTEM SET ... SCOPE=SPFILE may return ORA-32001. In that case:

1. Confirm the startup source using SHOW PARAMETER SPFILE.
2. If the procedure requires an SPFILE, create an SPFILE from a PFILE per plan.
3. If continuing to use a PFILE, edit the PFILE used at startup via a controlled OS process.
4. Do not assume editing an arbitrary init.ora file will affect the instance if the instance is reading a different file.

### Configuration Version Management

Before important changes, export a PFILE snapshot or save an SPFILE backup per DBA procedures. Record the timestamp, database/instance, change ticket, and operator. Do not put passwords or secrets into source code repositories.

## 10. Checking Runtime Values and SPFILE Values

V$PARAMETER reflects current parameter values in the instance. V$SPPARAMETER reflects entries stored in the SPFILE. The two values may differ if SCOPE=SPFILE or SCOPE=MEMORY was recently used.

### Comparing Both Sources

~~~sql
SELECT p.name,
       p.value AS runtime_value,
       s.value AS spfile_value,
       p.issys_modifiable,
       p.isses_modifiable,
       p.isdefault,
       p.ismodified
FROM v$parameter p
LEFT JOIN v$spparameter s
  ON s.name = p.name
 AND s.sid IN ('*', (SELECT instance_name FROM v$instance))
WHERE p.name IN (
    'open_cursors',
    'processes',
    'sessions',
    'sga_target',
    'memory_target'
)
ORDER BY p.name;
~~~

In RAC, there may be multiple entries for the same parameter by SID. The query above merely illustrates comparison; multiple SIDs/default overrides must be handled explicitly.

### Viewing All Parameters

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isses_modifiable,
       isinstance_modifiable,
       ispdb_modifiable,
       isdefault,
       ismodified,
       isadjusted
FROM v$parameter
ORDER BY name;
~~~

### Finding Static Parameters

~~~sql
SELECT name, value, issys_modifiable
FROM v$parameter
WHERE issys_modifiable = 'FALSE'
ORDER BY name;
~~~

The list varies by release and platform. Use this query for discovery; do not treat it as an exhaustive list of every parameter with restart requirements in every situation.

### Finding Session-Modifiable Parameters

~~~sql
SELECT name, value, isses_modifiable
FROM v$parameter
WHERE isses_modifiable = 'TRUE'
ORDER BY name;
~~~

A parameter that is session-modifiable is not necessarily modifiable via ALTER SYSTEM, or vice versa. Choose the statement matching the exact scope you need to change.

### Viewing Valid Values

Some parameters have a list of valid values in V$PARAMETER_VALID_VALUES:

~~~sql
SELECT name, value, isdefault
FROM v$parameter_valid_values
WHERE name = 'optimizer_mode'
ORDER BY value;
~~~

Not every parameter has an enumerated set of values; some accept numbers, strings, paths, or expressions. Parameter documentation is the authoritative source.

## 11. ALTER SYSTEM RESET and Restoring Default Values

ALTER SYSTEM RESET removes a parameter's entry from the SPFILE so Oracle uses the default value or inherited configuration value on the next startup. It is not a data rollback command and typically does not change the runtime value immediately.

### Resetting an Entry in the SPFILE

~~~sql
ALTER SYSTEM RESET open_cursors
    SCOPE = SPFILE
    SID = '*';
~~~

In RAC, SID identifies which entry to remove; SID='*' removes the shared default entry, while a specific instance SID can target a per-instance override. Inspect V$SPPARAMETER beforehand to avoid accidentally deleting configuration.

### Reset Does Not Mean Setting a Fixed Number

After a reset, Oracle uses the default or value determined by parameter precedence/configuration for that release and instance. Default values can vary by memory sizing, platform, CDB/PDB, and version. Check V$PARAMETER after restarting.

### Restoring from a Snapshot

If you saved a PFILE or SPFILE snapshot, you can restore old entries per plan. Do not replace the entire SPFILE with an old snapshot if other unrecorded changes were made after the snapshot timestamp.

## 12. CDB/PDB: Container-Scoped Parameters

In multitenant architecture, some initialization parameters can be set individually for a PDB, while others only make sense at the CDB/instance scope. V$PARAMETER includes the ISPDB_MODIFIABLE column to indicate PDB modifiability.

### Checking PDB Modifiability

~~~sql
SELECT name,
       value,
       ispdb_modifiable,
       issys_modifiable
FROM v$parameter
WHERE name IN (
    'open_cursors',
    'sessions',
    'optimizer_mode',
    'nls_date_format'
)
ORDER BY name;
~~~

### Changing a Parameter in the Current Container

For parameters supporting PDB scope, syntax can use CONTAINER=CURRENT when executed from the appropriate container:

~~~sql
ALTER SYSTEM SET parameter_name = value
    CONTAINER = CURRENT;
~~~

This example shows general syntax; do not run placeholders. SCOPE, CONTAINER, and parameter availability rules vary by release. Verify ISPDB_MODIFIABLE, common/local privileges, and documentation before making changes.

### Changing for All Containers

From the CDB root, some parameters can be set with CONTAINER=ALL to apply at the common scope per multitenant rules:

~~~sql
ALTER SYSTEM SET parameter_name = value
    CONTAINER = ALL;
~~~

Not every parameter supports CONTAINER=ALL. Do not use ALL if you only intend to target one PDB. Check V$PARAMETER/parameter documentation and the current container before executing.

### Session-Level in a PDB

ALTER SESSION modifies only the currently connected session. If the session is in a PDB, the session change persists only for that session; it does not change the parameter value for other sessions in the PDB or CDB.

### Persisting PDB State

Some PDB parameter changes are persisted by multitenant mechanisms and can survive closing/opening the PDB; do not infer that every parameter requires a CDB restart. Determine scope and restart requirements from the specific parameter, PDB state, and version.

## 13. Other ALTER SYSTEM Operations

ALTER SYSTEM also provides operational commands that do not change initialization parameters. These commands have their own semantics and risks; SCOPE=MEMORY/SPFILE/BOTH does not apply to them.

### CHECKPOINT

~~~sql
ALTER SYSTEM CHECKPOINT;
~~~

Requests Oracle to perform a checkpoint. A checkpoint writes dirty buffers via DBWR mechanisms and updates checkpoint information. Do not use this command as a cure-all for I/O issues or a substitute for checkpoint/redo tuning.

### SWITCH LOGFILE

~~~sql
ALTER SYSTEM SWITCH LOGFILE;
~~~

Requests the instance to switch to the next online redo log group. This is commonly used in labs or certain administrative procedures; do not run it repeatedly in production because it can cause excessive log switches and increase archive/checkpoint pressure.

### ARCHIVE LOG CURRENT

~~~sql
ALTER SYSTEM ARCHIVE LOG CURRENT;
~~~

In ARCHIVELOG mode, this command requests archiving the current online redo log per database semantics. Distinguish it from SWITCH LOGFILE and monitor archive destination status. Do not use it to replace archived redo backups or restore verification.

### Restricted Session

~~~sql
ALTER SYSTEM ENABLE RESTRICTED SESSION;
ALTER SYSTEM DISABLE RESTRICTED SESSION;
~~~

Restricted session limits new logins by ordinary users based on privileges. It can be a maintenance step, though it does not automatically terminate already-connected sessions. Identify existing sessions and application services clearly before enabling it.

### Kill or Disconnect Session

~~~sql
ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
~~~

In RAC, syntax can include the instance ID depending on release:

~~~sql
ALTER SYSTEM KILL SESSION 'sid,serial#,@inst_id' IMMEDIATE;
~~~

KILL SESSION requires appropriate privileges and accurate SID/SERIAL# information. The session may need time for cleanup/rollback; a KILLED status does not mean all resources are released immediately.

DISCONNECT SESSION can be used when disconnecting a session with POST_TRANSACTION or IMMEDIATE options:

~~~sql
ALTER SYSTEM DISCONNECT SESSION 'sid,serial#' POST_TRANSACTION;
~~~

Before killing/disconnecting, identify the user, module, SQL_ID, transaction, blocker/waiter, and business impact. Do not use it to handle a slow session without knowing what it is doing.

### FLUSH SHARED_POOL

~~~sql
ALTER SYSTEM FLUSH SHARED_POOL;
~~~

Flushing the shared pool can evict many cursors/objects from cache, leading to hard parses and subsequent CPU spikes. Do not run it arbitrarily on production to "refresh a plan." If a specific SQL statement needs handling, use appropriate cursor/plan management methods with a rollback plan.

### ALTER SYSTEM SET EVENTS

Some event/trace operations may use ALTER SYSTEM SET EVENTS or DBMS_MONITOR, but the syntax and scope are highly specialized. Do not copy event strings from forums into production. Prefer supported tracing tools, limit sessions and duration, and turn off events after collection.

## 14. ALTER SESSION for Diagnostics and Execution Control

ALTER SESSION is useful for bounded experimentation within a single session without changing instance-wide configuration.

### Enabling SQL Trace for a Session

~~~sql
ALTER SESSION SET sql_trace = TRUE;

-- Run the SQL statement under investigation.

ALTER SESSION SET sql_trace = FALSE;
~~~

In production, DBMS_MONITOR can provide ways to enable tracing by session/client/module; control bind capture and trace storage locations because traces may contain sensitive data.

### Setting a Trace File Identifier

~~~sql
ALTER SESSION SET tracefile_identifier = 'ROW473_DIAG';
~~~

This value helps identify the session's trace file in the ADR trace directory. It does not change the trace destination location.

### Enabling Parallel Query/DML for a Session

~~~sql
ALTER SESSION ENABLE PARALLEL QUERY;
ALTER SESSION ENABLE PARALLEL DML;
~~~

These commands allow the session to use certain forms of parallel execution when plans/hints/resource policies allow. Parallel DML also has transaction and object prerequisites. Do not enable them just to speed up a single query without checking CPU, PX server availability, I/O, and contention.

### Disabling Parallel Query/DML in a Session

~~~sql
ALTER SESSION DISABLE PARALLEL QUERY;
ALTER SESSION DISABLE PARALLEL DML;
~~~

### Temporarily Changing the Optimizer Environment

~~~sql
ALTER SESSION SET optimizer_mode = ALL_ROWS;
ALTER SESSION SET optimizer_dynamic_sampling = 4;
~~~

Session-level optimizer changes are helpful for diagnosing plans in labs or test sessions. Do not turn a session test into a system-wide change without measuring workload impact.

### Setting the Current Schema

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORTING;
~~~

CURRENT_SCHEMA affects only unqualified name resolution. It does not grant privileges and does not change SESSION_USER.

## 15. Safe Parameter Change Workflow

A configuration change should be treated as a controlled change:

1. Identify the issue and relevant parameter; do not make changes based on guesswork.
2. Read parameter documentation for the exact Oracle release, platform, and architecture.
3. Check ISSYS_MODIFIABLE, ISSES_MODIFIABLE, ISINSTANCE_MODIFIABLE, and ISPDB_MODIFIABLE.
4. Record runtime value, SPFILE value, default, instance, container, and session.
5. Check dependencies, OS limits, memory/process capacity, application pools, and RAC/Data Guard.
6. Save a PFILE/SPFILE snapshot or record the previous value and change ticket.
7. Choose appropriate SCOPE, SID, CONTAINER, and DEFERRED options.
8. If static, write SCOPE=SPFILE and schedule a restart per procedure.
9. Verify runtime/SPFILE values and the alert log after the change.
10. Measure workload, error rates, and resources; verify services/PDBs/instances.
11. If regression occurs, restore the previous value using the proper scope and restart if needed.
12. Record results, operator, timestamp, and audit reference.

### Before Running ALTER SYSTEM SET

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isses_modifiable,
       isinstance_modifiable,
       ispdb_modifiable,
       isdefault,
       ismodified
FROM v$parameter
WHERE name = 'open_cursors';

SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE name = 'open_cursors';

SELECT instance_name, host_name, status
FROM v$instance;

SHOW PARAMETER spfile;
SHOW CON_NAME;
~~~

These queries provide a starting point. In RAC, query from each instance or use GV$ views to inspect across the cluster; in a CDB, confirm the container.

### Choosing Scope by Goal

| Goal | Approach |
| --- | --- |
| Test in a single session | ALTER SESSION if the parameter is session-modifiable. |
| Temporary runtime change on the instance | ALTER SYSTEM SET ... SCOPE=MEMORY. |
| Save for the next startup | ALTER SYSTEM SET ... SCOPE=SPFILE. |
| Dynamic change immediately and persisted | ALTER SYSTEM SET ... SCOPE=BOTH. |
| Parameter applies to new sessions | Use DEFERRED if the parameter supports it. |
| Static parameter | SCOPE=SPFILE and restart. |
| One instance in RAC | Specific SID matching instance name. |
| Shared value in RAC | SID='*' per SPFILE configuration. |
| One PDB | CONTAINER=CURRENT if the parameter allows. |
| All PDBs in a CDB | CONTAINER=ALL if the parameter allows and scope is appropriate. |

## 16. Rolling Back Configuration Changes

Rolling back configuration requires knowing where the original change took effect.

### If Only MEMORY Was Changed

If SCOPE=MEMORY was used, you can set the old runtime value back:

~~~sql
ALTER SYSTEM SET open_cursors = 300 SCOPE = MEMORY;
~~~

Upon restart, the SPFILE/PFILE value remains the persistent configuration source.

### If BOTH Was Changed

You must restore both runtime and SPFILE:

~~~sql
ALTER SYSTEM SET open_cursors = 300 SCOPE = BOTH;
~~~

Setting only MEMORY would cause the new value to return on the next startup.

### If SPFILE Was Changed for a Dynamic Parameter

The runtime value has not changed yet; you can write the old value back to the SPFILE:

~~~sql
ALTER SYSTEM SET open_cursors = 300 SCOPE = SPFILE;
~~~

Or reset the entry if you want to revert to default:

~~~sql
ALTER SYSTEM RESET open_cursors SCOPE = SPFILE SID = '*';
~~~

### If the Parameter Is Static

Write the old value to the SPFILE and restart per the maintenance plan. You cannot restore the runtime effect of a static parameter using only ALTER SESSION or SCOPE=MEMORY.

### No Transaction Rollback for ALTER SYSTEM

ROLLBACK does not undo ALTER SYSTEM SET. Save the pre-change value and use ALTER SYSTEM SET/RESET for intentional restoration.

## 17. Common Errors and How to Handle Them

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-02095: specified initialization parameter cannot be modified | Parameter does not support dynamic modification or invalid modification method | Check ISSYS_MODIFIABLE; if FALSE, write SCOPE=SPFILE and schedule a restart. |
| ORA-02096: parameter cannot be modified with this option | SCOPE/DEFERRED or clause incompatible with parameter | Read parameter documentation and use supported options. |
| ORA-32001: write to SPFILE requested but no SPFILE is in use | Instance started with a PFILE or not using an SPFILE | Check SHOW PARAMETER SPFILE; edit the right PFILE or migrate to an SPFILE. |
| ORA-32017: failure in updating SPFILE | Unable to write SPFILE or configuration/path issue | Check permissions, SPFILE status, ASM/filesystem, and alert log. |
| ORA-00093: specified value must be between ... | Value out of range or invalid format | Check V$PARAMETER_VALID_VALUES and parameter documentation. |
| ORA-01031: insufficient privileges | User lacks ALTER SYSTEM or required administrative privilege | Use an operational account granted appropriate least privilege. |
| ORA-01078 on startup | Oracle cannot process one or more initialization parameters | Check alert log and PFILE/SPFILE; fix bad values before restarting. |
| ORA-32004 on startup | Obsolete/deprecated parameter in configuration file | Identify the warned parameter, check release docs, and remove/replace per plan. |
| Runtime value differs from SPFILE value | Used SCOPE=SPFILE or MEMORY, or SID override exists | Compare V$PARAMETER and V$SPPARAMETER; check SID/container. |
| Value changed but old session does not see it | Parameter uses DEFERRED or session has its own override | Check ISSYS_MODIFIABLE/ISSES_MODIFIABLE and open a new session to test. |
| Change disappears after restart | Only used SCOPE=MEMORY or edited the wrong PFILE | Write persistent value with SPFILE or update the actual startup PFILE. |
| SPFILE changed but not yet in effect | Used SCOPE=SPFILE for dynamic/static parameter without restarting or opening a new session | Check ISSYS_MODIFIABLE and restart/open a new session as required. |
| One RAC instance has a different value | Per-SID entry or unsynchronized runtime | Check GV$PARAMETER, V$SPPARAMETER, and each instance. |
| PDB receives a different value from CDB root | Parameter has PDB scope or container override | Check ISPDB_MODIFIABLE, CONTAINER clause, and current container. |
| Session pool has wrong NLS/schema | Previous session state was not reset | Set/reset session state on connection checkout/checkin. |

### Short Diagnostic Workflow

1. Identify the parameter and desired value.
2. Check V$PARAMETER for runtime value and ISSYS_MODIFIABLE.
3. Check ISSES_MODIFIABLE, ISINSTANCE_MODIFIABLE, and ISPDB_MODIFIABLE.
4. Check V$SPPARAMETER for persistent value and SID entries.
5. Check actual SPFILE/PFILE, container, instance, and privileges.
6. Read the alert log if startup or parameter processing failed.
7. Determine whether the change requires a new session or a restart.
8. Verify after the change using both the data dictionary and workload.

## 18. Lab Exercise: ALTER SESSION and ALTER SYSTEM

Perform in a lab database with appropriate privileges. Do not perform restart steps or static parameter changes on production or shared databases.

### Step 1: Identify Session and Instance

~~~sql
SHOW USER;
SHOW CON_NAME;
SHOW PARAMETER spfile;

SELECT instance_name, host_name, status
FROM v$instance;

SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Record the user, schema, container, instance, and startup source.

### Step 2: Test ALTER SESSION

~~~sql
SELECT SYSDATE FROM dual;

ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

SELECT SYSDATE FROM dual;
~~~

Only the date format in the current session changes. Open a second session and run SELECT SYSDATE to verify the other session is unaffected.

### Step 3: Test CURRENT_SCHEMA

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES;

SELECT sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Try accessing a SALES object that the current user has privileges on. If privileges are missing, CURRENT_SCHEMA does not grant permissions in place of GRANT.

Return to the original schema by setting back the value recorded before the test.

### Step 4: Inspect a Dynamic Parameter

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isses_modifiable,
       isinstance_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE name = 'open_cursors';

SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE name = 'open_cursors';
~~~

Record both runtime and SPFILE values before making changes.

### Step 5: Change Runtime in the Lab

If OPEN_CURSORS allows dynamic modification and the account has privileges:

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = MEMORY;
~~~

Check:

~~~sql
SELECT name, value, issys_modifiable
FROM v$parameter
WHERE name = 'open_cursors';
~~~

SCOPE=MEMORY applies only at runtime. Do not leave test changes behind; restore the previously recorded value:

~~~sql
ALTER SYSTEM SET open_cursors = <previous_value> SCOPE = MEMORY;
~~~

Replace the placeholder with the actual old value. Do not run angle brackets verbatim.

### Step 6: Observe SPFILE Scope

In a lab database using an SPFILE, write another test value:

~~~sql
ALTER SYSTEM SET open_cursors = 550 SCOPE = SPFILE;
~~~

Compare:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'open_cursors';

SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE name = 'open_cursors';
~~~

The runtime value may still be the old value while the SPFILE value is already 550. Before restarting, restore the SPFILE to the old value:

~~~sql
ALTER SYSTEM SET open_cursors = <previous_value> SCOPE = SPFILE;
~~~

If not restored, the test value will be loaded on the next restart. Do not perform this step if you are unsure of the old value or if the SPFILE is shared with another instance.

### Step 7: Inspect a Parameter Requiring Restart

~~~sql
SELECT name,
       value,
       issys_modifiable
FROM v$parameter
WHERE name = 'processes';
~~~

In a lab, you can plan changing PROCESSES with SCOPE=SPFILE. Do not restart the database just to complete an exercise if there is no maintenance window; the goal is to recognize static parameters and their application workflow.

~~~sql
ALTER SYSTEM SET processes = 600 SCOPE = SPFILE;
~~~

Then check V$SPPARAMETER and restore the old value before the next startup if you do not intend to apply it:

~~~sql
ALTER SYSTEM SET processes = <previous_value> SCOPE = SPFILE;
~~~

### Step 8: Clean Up Session State

Close the lab session or reset NLS_DATE_FORMAT/CURRENT_SCHEMA to the recorded values. In pooled applications, verify the session state reset callback.

## 19. Self-Check Questions

1. **What scope does ALTER SESSION change?** Only the current session.
2. **What scope does ALTER SYSTEM SET change?** Instance/system runtime and/or SPFILE depending on SCOPE, SID, and container.
3. **Does SCOPE=MEMORY persist after a restart?** No.
4. **Does SCOPE=SPFILE change runtime immediately?** No; the value takes effect at the appropriate startup.
5. **What does SCOPE=BOTH do?** Changes runtime and writes the persistent value to the SPFILE if the parameter supports it.
6. **What does a dynamic parameter mean?** It can be modified while the instance is running at the IMMEDIATE or DEFERRED level.
7. **How can a static parameter be changed?** Write to SPFILE/PFILE and restart to apply.
8. **What does ISSYS_MODIFIABLE=IMMEDIATE mean?** The system parameter change takes effect immediately per parameter semantics.
9. **What does ISSYS_MODIFIABLE=DEFERRED mean?** The new value applies to sessions starting after the change.
10. **What is ISSES_MODIFIABLE used for?** Indicates whether the parameter can be changed via ALTER SESSION.
11. **What does V$PARAMETER reflect?** Runtime values in the instance.
12. **What does V$SPPARAMETER reflect?** Entries stored in the SPFILE.
13. **How does PFILE differ from SPFILE?** PFILE is a text file; SPFILE is a server parameter file managed by Oracle.
14. **What does ORA-32001 usually mean?** A write to SPFILE was requested, but the instance is not using an SPFILE.
15. **What does ORA-02095 usually mean?** The parameter cannot be dynamically modified in the requested manner.
16. **When is SID='*' used?** Sets a shared value for instances in SPFILE/RAC per configuration.
17. **When is SID='instance_name' used?** Sets a specific override for one instance in RAC.
18. **What does CONTAINER=CURRENT/ALL do?** Specifies the PDB/container scope for parameters supporting multitenant.
19. **Does ALTER SYSTEM RESET change runtime immediately?** Usually it removes the SPFILE entry; runtime does not change solely from reset.
20. **Can ALTER SYSTEM be rolled back with SQL ROLLBACK?** No; you must set the value back or reset the configuration.
21. **Why do connection pools need to reset ALTER SESSION state?** Sessions are reused and may retain NLS/schema/optimizer settings from a previous request.
22. **Can every static parameter be rolling-restarted?** No; check documentation and specific architectural requirements.
23. **Why compare V$PARAMETER and V$SPPARAMETER?** To detect differences between runtime and persistent values.

ALTER SESSION is used for local changes within a single connection; ALTER SYSTEM SET manages values at the instance/database scope and can write persistent configuration. ISSYS_MODIFIABLE, ISSES_MODIFIABLE, ISINSTANCE_MODIFIABLE, and ISPDB_MODIFIABLE determine at which scopes a parameter can be changed. SCOPE=MEMORY changes only runtime, SPFILE saves only for subsequent startups, and BOTH does both. Static parameters require writing configuration and restarting; deferred parameters apply to new sessions. Always verify runtime/SPFILE values, SID/container, alert log, and workload after changes, and prepare rollback values before modifying production.
