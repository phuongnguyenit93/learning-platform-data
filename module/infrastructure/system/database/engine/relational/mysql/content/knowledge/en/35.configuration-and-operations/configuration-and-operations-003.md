# SET GLOBAL, SET PERSIST, SET PERSIST_ONLY, and Post-Startup Configuration

MySQL provides multiple ways to change system variables: editing startup configuration, running SET GLOBAL, saving values with SET PERSIST, or staging values for the next startup with SET PERSIST_ONLY. Choosing the wrong method can cause settings to apply only temporarily, override file-managed configuration, or prevent the server from starting as expected.

This lesson explains the scope and mutability of system variables, differences among the three SET commands, how MySQL loads configuration after a restart, where persistent values are stored, required privileges, how to inspect configuration sources, and rollback procedures. Examples focus on operational settings such as max_connections, innodb_buffer_pool_size, and startup-only variables.

## 1. System Variables and Configuration Layers

System variables control the behavior of MySQL Server. For example:

- max_connections: limits the number of concurrent connections.
- innodb_buffer_pool_size: size of the InnoDB buffer pool.
- slow_query_log: enables or disables the slow query log.
- long_query_time: time threshold for logging slow queries.
- innodb_flush_method: selects InnoDB's file flushing method on supported operating systems.

The effective value of a variable can come from multiple places:

1. Compiled-in default values in MySQL.
2. Option files such as my.cnf or my.ini.
3. The MySQL-managed persistent file.
4. Command-line arguments when starting mysqld.
5. SET statements while the server is running.

These sources have different application times and precedence levels. You must distinguish the current in-memory value from the value that will be loaded when the server restarts.

### 1.1. Runtime Configuration vs. Startup Configuration

**Runtime configuration** refers to the values currently in effect inside the running MySQL process. They can be changed with SET GLOBAL or SET PERSIST if the variable allows dynamic modification.

**Startup configuration** refers to the values MySQL reads when starting up. They can come from option files, persisted configuration, or the command line. Some variables can only be configured at startup.

Example:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';

SET GLOBAL max_connections = 300;
~~~

The SET GLOBAL statement changes the runtime value. After a server restart, the value 300 will not automatically persist if no startup configuration source stores it.

### 1.2. Three Questions to Answer Before Making Changes

Before modifying a variable, determine:

1. Does the variable have GLOBAL scope, SESSION scope, or both?
2. Is the variable dynamic, or is it read only at startup?
3. Should the value take effect immediately, after a restart, or both?

These three questions determine whether to use SET GLOBAL, SET PERSIST, or SET PERSIST_ONLY.

## 2. GLOBAL and SESSION Scopes

A system variable can have GLOBAL scope, SESSION scope, or both.

| Scope | Meaning |
|---|---|
| GLOBAL | A shared server-wide value |
| SESSION | A value specific to a single connection |
| BOTH | Has both a global and a session value |

Read the global value:

~~~sql
SELECT
    @@GLOBAL.max_connections AS global_max_connections;

SHOW GLOBAL VARIABLES LIKE 'max_connections';
~~~

Read the session value:

~~~sql
SELECT @@SESSION.sql_mode;

SHOW SESSION VARIABLES LIKE 'sql_mode';
~~~

If a variable has both scopes, the session value is usually initialized from the global value when a new connection is created. Changing the global value does not automatically overwrite the session value of existing connections.

Example:

~~~sql
SET GLOBAL sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

New connections receive their default session value from the new global value. An existing connection may retain its previous session sql_mode until that session changes it or terminates.

### 2.1. Do Not Use SET GLOBAL to Change a Session

If you only want to change behavior in the current connection, use:

~~~sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

Or:

~~~sql
SET @@SESSION.sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

SET GLOBAL has server-wide impact and requires appropriate administrative privileges. Do not use it to adjust a test query that only needs a session-level change.

### 2.2. SET PERSIST Is Not a SESSION Command

SET PERSIST and SET PERSIST_ONLY store values at global scope for MySQL to use at startup. They are not used to persist custom settings for a single connection.

If a variable has both GLOBAL and SESSION scopes, explicitly choose SET SESSION when changing only the connection, and use SET PERSIST when changing global runtime and saving the value for the next startup.

## 3. Dynamic Variables and Read-Only Variables

Whether a system variable can be changed is determined by the variable's attributes, not merely whether the user has administrative privileges.

### 3.1. Dynamic Variables

Dynamic variables can be changed while the server is running. For example, max_connections and long_query_time can be changed at runtime.

~~~sql
SET GLOBAL max_connections = 300;
SET GLOBAL long_query_time = 2;
~~~

The change takes effect immediately according to the scope and rules of each variable. However, runtime changes via SET GLOBAL are not automatically written to persistent configuration.

### 3.2. Read-Only or Startup-Only Variables

Some variables can only be determined when the server starts. They cannot be changed with SET GLOBAL while the server is running.

For example, `innodb_flush_method` is a startup configuration variable on supported platforms and versions. To stage a new value for the next restart, you can use SET PERSIST_ONLY if the variable is persistable and the environment supports the chosen value.

~~~sql
SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT';
~~~

This is a syntax illustration, not a recommendation to apply O_DIRECT on every server. Valid flush methods depend on the operating system, filesystem, MySQL version, and storage setup. Consult your platform documentation before choosing a value.

### 3.3. Checking Variable Attributes and Sources

MySQL provides metadata in Performance Schema:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN (
    'max_connections',
    'innodb_buffer_pool_size',
    'innodb_flush_method'
);
~~~

VARIABLE_SOURCE indicates the configuration source recorded by MySQL, such as compiled default, option file, command line, persisted configuration, or dynamic change. VARIABLE_PATH may indicate the associated option file path. Metadata may vary depending on the version and actual source.

Do not assume a variable is dynamic solely from its name or because SHOW VARIABLES can read it. Check the exact variable's attributes in the Reference Manual and inspect metadata on the server.

## 4. SET GLOBAL: Runtime Changes

SET GLOBAL assigns a new value to a system variable at global scope if the variable permits dynamic modification.

Syntax:

~~~sql
SET GLOBAL variable_name = value;
~~~

Or:

~~~sql
SET @@GLOBAL.variable_name = value;
~~~

Example:

~~~sql
SET GLOBAL max_connections = 400;

SELECT @@GLOBAL.max_connections;
~~~

The new value takes effect in the running server. For variables with both GLOBAL and SESSION scopes, new connections receive the new global value as their initial session value; existing connections are not automatically overwritten.

### 4.1. SET GLOBAL Does Not Survive Restarts

SET GLOBAL changes runtime state only. Unless another startup configuration source stores the value, after a restart MySQL will load the value from the option file, persisted configuration, command line, or default.

It is an appropriate choice when:

- Testing a change in a staging environment.
- Making a temporary adjustment during incident mitigation.
- Measuring impact before deciding to store a change permanently.
- The value only needs to last for the current server lifecycle.

Once a change is validated and needs to survive restarts, update the permanent configuration source or use SET PERSIST according to operational policy.

### 4.2. SET GLOBAL Applies Only to Dynamic Variables

If a variable is read-only or startup-only, SET GLOBAL will fail. Administrative privileges do not make a startup-only variable dynamic.

Do not use SET GLOBAL to try forcing a change on a variable that does not support runtime modification. Check the variable documentation and use SET PERSIST_ONLY or an option file if appropriate.

### 4.3. Temporary Adjustment Example

~~~sql
-- Record the current value.
SELECT @@GLOBAL.long_query_time AS old_value;

-- Lower the threshold during investigation.
SET GLOBAL long_query_time = 1;

-- Verify the new value.
SELECT @@GLOBAL.long_query_time AS current_value;
~~~

When the investigation concludes, you can restore the recorded value using SET GLOBAL. Do not assume the old value was the MySQL default; it could have come from an option file or a persistent configuration.

## 5. SET PERSIST: Changing Runtime and Saving for Subsequent Startups

SET PERSIST performs two actions on a dynamically modifiable global variable:

1. Assigns the new value at runtime just like SET GLOBAL.
2. Writes the value to persistent configuration so MySQL reloads it on the next startup.

Syntax:

~~~sql
SET PERSIST variable_name = value;
~~~

Example:

~~~sql
SET PERSIST max_connections = 400;
~~~

After this statement, the running global value is changed and the value is also saved to the MySQL-managed persistent file.

### 5.1. When to Use SET PERSIST?

Use it when:

- The variable supports runtime modification.
- The new value has been tested and needs to survive restarts.
- Operational policy allows MySQL to manage persistent settings.
- You have recorded the current value and have a rollback plan.

SET PERSIST is convenient for controlled changes from SQL. However, if your organization manages configuration centrally using Ansible, Puppet, Chef, images, or a deployment system, consider updating the canonical configuration source instead of introducing a separate configuration source in `mysqld-auto.cnf`.

### 5.2. SET PERSIST Does Not Replace Load Testing

For example, increasing `max_connections` does not mean the server automatically gains more RAM for each connection. Each connection can consume memory based on workload and on-demand allocated buffers.

Before raising limits, check:

- Actual connection counts and peak concurrent connections.
- Connection pooling at the application tier.
- Baseline memory and per-connection memory.
- File descriptor limits and OS resources.
- CPU, storage, and workload capacity.

Persistent settings make changes long-lived; they do not prove the new value is safe.

### 5.3. SET PERSIST Is for GLOBAL Only

SET PERSIST does not store a per-connection SESSION value. When you need a session change, use SET SESSION. When you need a global change that survives restarts, use SET PERSIST.

### 5.4. The DEFAULT Value

You can use DEFAULT to reset a variable to the MySQL default value within the scope of the corresponding command:

~~~sql
SET GLOBAL max_connections = DEFAULT;
~~~

For persistent changes, distinguish between storing the DEFAULT value and removing a persistent override. If the goal is to completely remove an entry from persisted configuration so the server falls back to a lower-precedence source, use RESET PERSIST.

## 6. SET PERSIST_ONLY: Saving a Value Without Changing Runtime

SET PERSIST_ONLY writes a value to persistent configuration without modifying the running value. Only when MySQL restarts and loads persisted settings does the new value take effect.

Syntax:

~~~sql
SET PERSIST_ONLY variable_name = value;
~~~

Example:

~~~sql
SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT';
~~~

This is an example illustrating a startup-only variable. The value O_DIRECT is only an example choice on a supported platform; verify filesystem, storage device, MySQL version, and durability requirements before applying.

### 6.1. Distinguishing from SET PERSIST

| Statement | Changes runtime immediately | Writes persistent setting | Effective after restart |
|---|---:|---:|---:|
| SET GLOBAL | Yes, if dynamic | No | Not automatically preserved |
| SET PERSIST | Yes, if dynamic | Yes | Yes |
| SET PERSIST_ONLY | No | Yes | Yes |

SET PERSIST_ONLY can also be used with a dynamic variable when you want to stage configuration for a restart without altering current runtime behavior.

### 6.2. Why Is SET PERSIST_ONLY Needed?

Some variables cannot be changed while the server is running yet can still be written to persisted configuration. SET PERSIST_ONLY lets administrators stage a value for the next startup without editing option files directly.

This is the appropriate approach for persistable read-only variables. Not every system variable can be saved; MySQL has specific lists and rules for variables that cannot be persisted.

### 6.3. Checking Before Restarting

After SET PERSIST_ONLY, the runtime value remains the old value:

~~~sql
SELECT @@GLOBAL.innodb_flush_method;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'innodb_flush_method';
~~~

The first query reads the current value. The second query inspects the value saved for the next startup. The two results can differ before restarting.

## 7. Privileges Required to Modify System Variables

Modifying global configuration is an administrative operation. Do not grant these privileges to regular application accounts.

In MySQL 8.0, key dynamic privileges include:

| Privilege | Purpose |
|---|---|
| SYSTEM_VARIABLES_ADMIN | Allows SET GLOBAL and SET PERSIST/SET PERSIST_ONLY operations on non-read-only variables per MySQL rules |
| PERSIST_RO_VARIABLES_ADMIN | Allows persisting read-only variables with SET PERSIST_ONLY |
| SUPER | Legacy administrative privilege; deprecated, with many operations split into specialized dynamic privileges |

Specialized dynamic privileges were introduced in MySQL 8.0.14. SUPER still appears in some legacy compatibility guides but is deprecated; grant the minimum privilege needed for the exact operation required.

### 7.1. Granting SYSTEM_VARIABLES_ADMIN

Example granting to an operations account:

~~~sql
GRANT SYSTEM_VARIABLES_ADMIN ON *.* TO 'ops_config'@'localhost';
~~~

This privilege allows managing global variables within the scope supported by MySQL. It does not mean the account can change read-only variables with SET GLOBAL.

### 7.2. Granting PERSIST_RO_VARIABLES_ADMIN

If an account needs to persist read-only variables for the next startup:

~~~sql
GRANT PERSIST_RO_VARIABLES_ADMIN ON *.* TO 'ops_config'@'localhost';
~~~

This privilege serves the case of persisting read-only variables via SET PERSIST_ONLY. SYSTEM_VARIABLES_ADMIN is still required for SET GLOBAL and persisting non-read-only variables; SUPER is a legacy compatibility privilege that may satisfy certain administrative requirements. Grant only the minimum privileges operators genuinely need.

### 7.3. Checking Account Privileges

~~~sql
SHOW GRANTS FOR 'ops_config'@'localhost';
~~~

If a SET statement is rejected, check current privileges, variable scope, and dynamic/read-only attributes. Do not solve every privilege error by granting SUPER to the account.

### 7.4. Separating Application Accounts and Operational Accounts

Application accounts typically only need privileges on the schemas and data objects the application uses. Configuration operations accounts should be managed separately, with auditing, strong authentication, and approval workflows per organizational policy.

Do not attach SYSTEM_VARIABLES_ADMIN or PERSIST_RO_VARIABLES_ADMIN to an application connection account just to avoid a SET error in a deployment script.

## 8. Persisted Configuration and mysqld-auto.cnf

When running SET PERSIST or SET PERSIST_ONLY, MySQL writes values to a persistent configuration file named `mysqld-auto.cnf` in the data directory.

This is a JSON file managed automatically by MySQL. It contains persisted values along with associated metadata. It is read at server startup if persisted configuration is enabled.

### 8.1. Do Not Edit mysqld-auto.cnf Manually

Do not edit, reformat, partially delete, or create this file with a text editor. Use SET PERSIST, SET PERSIST_ONLY, and RESET PERSIST to manage its contents.

Direct editing can corrupt metadata, produce invalid JSON, or cause divergence between runtime and startup configuration. If backups are needed, follow the system's data directory backup and configuration management procedures.

### 8.2. Viewing Persisted Values

Performance Schema provides the `persisted_variables` table:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
ORDER BY VARIABLE_NAME;
~~~

Filter for a specific variable:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

This table reflects saved persistent values. It does not replace SHOW GLOBAL VARIABLES when you need the current runtime value.

### 8.3. Comparing Runtime and Persistent Values

~~~sql
SELECT @@GLOBAL.max_connections AS runtime_value;

SELECT VARIABLE_VALUE AS persisted_value
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

The two values may differ if SET PERSIST_ONLY was used, if runtime was later altered with SET GLOBAL, or if persisted configuration has not yet been loaded in the current process.

### 8.4. Inspecting Configuration Sources

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

The output helps investigate where the current value came from and who performed the most recent dynamic change when metadata is available. This is a useful tool for detecting configuration overrides between option files and persisted settings.

## 9. Which Configuration Wins After MySQL Starts?

MySQL loads configuration from multiple sources in order. For common sources, persisted settings are loaded after option files and before command-line options. Therefore:

- A value in `mysqld-auto.cnf` can override the same variable in `my.cnf`.
- A value passed directly on the command line takes higher precedence than a persisted setting.
- If there is no override, the server uses the value loaded from the option file or the default value.

You can visualize the typical precedence order from lowest to highest:

~~~text
Default value
    ↓
Option file (my.cnf / my.ini)
    ↓
Persisted configuration (mysqld-auto.cnf)
    ↓
mysqld command-line option
~~~

The exact order also depends on startup method and which configuration sources are provided. Check how the service or container launches mysqld before concluding which source is winning.

### 9.1. Example of Overridden Configuration

Suppose the option file contains:

~~~ini
[mysqld]
max_connections = 200
~~~

Then an administrator runs:

~~~sql
SET PERSIST max_connections = 400;
~~~

Runtime changes to 400 and persisted configuration stores 400. After a restart, persisted settings are loaded after the option file, so 400 remains in effect.

If the operations team later changes `my.cnf` to 250 without removing the persisted setting, 400 may still win. This is a form of configuration drift: the managed configuration file says 250, yet the server continues running with 400.

### 9.2. When to Use Option Files?

Prefer option files or centralized configuration management tools when:

- You want configuration to be version-controlled and reviewed.
- You need consistent application across multiple servers.
- You need reproducible environments from images or automation.
- Deployment processes require all startup changes to go through change management.

SET PERSIST is suitable for controlled administrative operations on a single server, but changes should be recorded in the organization's canonical configuration source if policy requires it.

### 9.3. Checking Which Option Files Are Read

You can use client or server option inspection to view which configuration files and option groups are read. For example, on a system with the MySQL client:

~~~bash
mysql --help
~~~

The top section of the client output shows the order of option files the client reads. Paths and how a service launches the server may differ from the client; inspect service configuration or mysqld arguments separately when investigating the server.

## 10. RESET PERSIST: Removing Saved Overrides

RESET PERSIST removes a value from persistent configuration. It is not equivalent to SET GLOBAL and does not automatically restore the current runtime value.

Syntax to remove a single variable:

~~~sql
RESET PERSIST max_connections;
~~~

To ignore the case where the variable is not present in persistent configuration:

~~~sql
RESET PERSIST IF EXISTS max_connections;
~~~

You can remove all persistent settings:

~~~sql
RESET PERSIST;
~~~

> RESET PERSIST does not remove a variable from option files or the command line. It only removes the override stored by MySQL in persisted configuration.

### 10.1. Runtime Does Not Revert Automatically

Suppose you ran:

~~~sql
SET PERSIST max_connections = 400;
~~~

And then ran:

~~~sql
RESET PERSIST max_connections;
~~~

The current runtime value may still be 400. RESET PERSIST only removes the persistent value. To change runtime immediately, run SET GLOBAL with the desired value:

~~~sql
SET GLOBAL max_connections = 200;
~~~

If the option file also sets 200, then after the next restart 200 will be loaded from the option file. If no configuration source sets a value, the server will use the remaining configuration source according to precedence order.

### 10.2. Removing All Persistent Settings Requires Caution

RESET PERSIST without a variable name deletes every persistent setting. This can cause many operational settings to disappear after the next restart.

Before using it, list `persisted_variables` and identify each override. In routine operations, prefer removing only the specific variable being changed rather than clearing everything.

### 10.3. Verifying After RESET PERSIST

~~~sql
RESET PERSIST IF EXISTS max_connections;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';

SELECT @@GLOBAL.max_connections;
~~~

The `persisted_variables` query returns no matching row if the override has been removed. The `@@GLOBAL.max_connections` value reflects runtime and may still hold the previously set value.

## 11. Restarting and Loading Persistent Settings

SET PERSIST_ONLY does not change runtime. For the saved value to take effect, MySQL must be restarted following the environment's operational procedure.

### 11.1. Role of persisted_globals_load

MySQL has a startup variable `persisted_globals_load` to control loading values from `mysqld-auto.cnf`. By default, persisted configuration is loaded at startup.

If you need to start the server while skipping persisted settings, you can use the startup option:

~~~bash
mysqld --persisted-globals-load=OFF
~~~

This is a recovery tool when a persisted setting causes startup problems or when diagnosing configuration. The actual way to pass the option must match your service manager, container entrypoint, or MySQL management system. Never start a second mysqld process against the same data directory.

### 11.2. Disabling Persistent Setting Loading Does Not Delete the File

When `persisted_globals_load` is turned off, MySQL ignores values in `mysqld-auto.cnf` when loading startup configuration. The file still exists; saved values are not automatically deleted.

After starting the server with persistent settings bypassed:

1. Connect using an appropriate administrative account.
2. Inspect `performance_schema.persisted_variables`.
3. Identify the variable causing the error or invalid configuration.
4. Use RESET PERSIST to remove the offending override or set a valid value.
5. Restart under normal configuration and verify.

Do not leave `persisted_globals_load=OFF` as a permanent workaround if the system relies on persistent configuration for startup values.

### 11.3. Post-Restart Verification Procedure

After the server starts:

~~~sql
SELECT @@GLOBAL.max_connections;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';

SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

The three queries respectively verify the runtime value, persisted value, and configuration source recorded by MySQL. If the runtime value differs from the persistent value, check command-line arguments, option files, persistability, and persistent configuration load status.

## 12. SET GLOBAL, SET PERSIST, and SET PERSIST_ONLY in Operations

Choose the statement based on the change goal:

| Goal | Appropriate Statement | Restart Needed? |
|---|---|---|
| Test a runtime change for a dynamic variable | SET GLOBAL | No |
| Change runtime and keep across restarts | SET PERSIST | No for runtime effect; restart to verify startup |
| Stage a value for the next startup | SET PERSIST_ONLY | Yes |
| Remove a persisted override | RESET PERSIST variable | No to clear file; restart to verify fallback source |
| Change only one connection | SET SESSION | No |
| Manage standard config across many servers | Option file/configuration management | Per variable requirement |

### 12.1. Example: Adjusting a Dynamic Variable and Saving Long-Term

Suppose after testing, the operations team decides to increase `max_connections` from 200 to 300:

~~~sql
-- Check current state.
SELECT @@GLOBAL.max_connections AS before_value;

-- Change runtime and save for future startups.
SET PERSIST max_connections = 300;

-- Verify runtime.
SELECT @@GLOBAL.max_connections AS runtime_value;

-- Verify persisted setting.
SELECT VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

After restarting during a change window, re-verify runtime and configuration source. Also monitor connection counts, memory usage, connection errors, and application latency.

### 12.2. Example: Staging a Startup-Only Variable

Suppose the operations team has verified platform compatibility and decided to change `innodb_flush_method` at the next restart:

~~~sql
-- The current value remains active in the running process.
SELECT @@GLOBAL.innodb_flush_method AS runtime_value;

-- Write the new value to persistent configuration only.
SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT';

-- Compare runtime with the saved value.
SELECT @@GLOBAL.innodb_flush_method AS current_runtime;

SELECT VARIABLE_VALUE AS next_startup_value
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'innodb_flush_method';
~~~

After verifying OS compatibility and scheduling a restart, the server will load the persistent value. If the value is unsupported on the platform, fix or remove the override before restarting normally.

### 12.3. Example: Rolling Back a Persistent Change

Suppose the initial value was 200, then SET PERSIST changed it to 300. If you decide to revert to 200 and keep the setting across restarts:

~~~sql
SET PERSIST max_connections = 200;
~~~

If you want to remove the persistent override and let the option file/default determine the startup value:

~~~sql
RESET PERSIST IF EXISTS max_connections;
SET GLOBAL max_connections = 200;
~~~

Runtime state and persistent state are two separate states. Verify both after a rollback.

## 13. MySQL Versions and Compatibility

SET PERSIST and SET PERSIST_ONLY were introduced in MySQL 8.0.11. Specialized dynamic privileges such as SYSTEM_VARIABLES_ADMIN and PERSIST_RO_VARIABLES_ADMIN have existed since MySQL 8.0.14.

| Capability | Version |
|---|---|
| SET PERSIST and SET PERSIST_ONLY | MySQL 8.0.11 and later |
| RESET PERSIST | MySQL 8.0.11 and later |
| SYSTEM_VARIABLES_ADMIN and PERSIST_RO_VARIABLES_ADMIN | MySQL 8.0.14 and later |
| performance_schema.persisted_variables | MySQL 8.0.11 and later |
| performance_schema.variables_info | MySQL 8.0.16 and later |

If your application or automation still supports MySQL 5.7, SET PERSIST/SET PERSIST_ONLY cannot be used on that version. Use option files or configuration management tools for startup values and SET GLOBAL for supported runtime changes.

### 13.1. Checking Version Before Execution

~~~sql
SELECT VERSION() AS mysql_version;
~~~

Do not check only the major version. Identify the exact minor release and read the documentation for the actual server version, as system variables can be added, renamed, deprecated, or have their dynamic attributes changed across releases.

### 13.2. Not All Variables Can Be Persisted

MySQL restricts which variables can be written to persisted configuration. Some variables depend on process state, paths, environment, or data directory initialization state and cannot be persisted in the usual way.

If SET PERSIST or SET PERSIST_ONLY rejects a variable, read the error message and the documentation for that variable. Do not attempt to bypass this by manually editing `mysqld-auto.cnf`.

## 14. Persistent Settings Do Not Automatically Replicate to Other Servers

Persistent configuration is local state for each MySQL Server instance. SET PERSIST and SET PERSIST_ONLY are not a configuration distribution mechanism for an entire replication topology.

If you have a primary and replicas:

- A runtime change on the primary does not guarantee that replicas share the same system variables.
- Values written to `mysqld-auto.cnf` on one node do not automatically appear on other nodes.
- Configuration must be applied individually on each instance according to its role and load requirements.
- Configuration management can be used to roll out the same change in a controlled manner.

For example, increasing `max_connections` on the primary does not mean replicas automatically increase theirs. Replicas may have different read workloads, different resource limits, or require separate values.

### 14.1. Maintaining a Per-Node Configuration Inventory

A simple operational table can record:

| Node | Role | Variable | Runtime | Persisted | Canonical Source |
|---|---|---|---:|---:|---|
| db-primary-1 | Primary | max_connections | 300 | 300 | Config management |
| db-replica-1 | Replica | max_connections | 250 | 250 | Config management |
| db-replica-2 | Replica | max_connections | 250 | 250 | Config management |

The values above are illustrative examples only. What matters is tracking runtime and persisted values separately, while knowing each node's canonical configuration source.

### 14.2. Coordinating Changes Across a Topology

Before deploying:

1. Determine whether the variable needs the same value on all nodes.
2. Determine which nodes should be changed first.
3. Check each node's individual resource limits.
4. Apply via configuration management tools or approved actions on each node.
5. Verify runtime, persisted values, and configuration sources after deployment.

Do not assume a SET PERSIST statement run on the primary will be sent via the binary log to replicas.

## 15. Common Errors and Troubleshooting

### 15.1. SET GLOBAL Reports Variable Is Not Dynamic

**Cause:** the variable is startup-only or read-only.

**Resolution:** verify whether the variable can be persisted. If permitted, use SET PERSIST_ONLY to stage the startup value; otherwise, update the option file or supported startup mechanism.

### 15.2. SET PERSIST Reports Access Denied

**Cause:** the account lacks SYSTEM_VARIABLES_ADMIN or an appropriate privilege.

**Resolution:** check SHOW GRANTS and grant the minimum dynamic privilege through administrative procedures. Do not reflexively grant SUPER.

### 15.3. SET PERSIST_ONLY on a Read-Only Variable Is Rejected

**Cause:** missing PERSIST_RO_VARIABLES_ADMIN, or the variable is not in the persistable set.

**Resolution:** check privileges and the variable's documentation. Not every read-only variable can be persisted.

### 15.4. Value After Restart Differs from SET PERSIST Value

**Possible causes include:**

- A command-line option overrides the persisted setting.
- Persisted configuration was not loaded.
- The value was cleared by RESET PERSIST or changed afterward.
- The service started a different instance or used a different data directory.
- The variable is not persistable under MySQL rules.

**Resolution:** check `@@GLOBAL.variable`, `performance_schema.persisted_variables`, `performance_schema.variables_info`, service arguments, and the data directory.

### 15.5. Edited my.cnf, Yet Server Retains the Old Value

**Cause:** a persisted setting in `mysqld-auto.cnf` is loaded after the option file and overrides the value in `my.cnf`.

**Resolution:** inspect `persisted_variables`. If you want the option file to become the authoritative source, use RESET PERSIST for that variable and restart, or update the persisted value according to policy.

### 15.6. RESET PERSIST Leaves Runtime Unchanged

**Cause:** RESET PERSIST only deletes saved configuration; it does not modify running variables.

**Resolution:** if runtime must change immediately, run SET GLOBAL with the desired value. Then inspect startup configuration sources to confirm the post-restart value.

### 15.7. SET PERSIST_ONLY Succeeds, Yet Current Behavior Is Unchanged

**Cause:** the statement only records the value for the next startup.

**Resolution:** inspect `persisted_variables` to confirm the saved value, schedule a restart, and verify after the server comes back up.

### 15.8. Server Fails to Start After Persisting a Value

**Cause:** invalid value, unsupported on the platform, or causes an initialization error.

**Recovery procedure:**

1. Use the system's controlled startup procedure.
2. If necessary, start with `persisted_globals_load=OFF` to bypass persisted settings.
3. Connect and inspect the saved values.
4. Run RESET PERSIST on the offending variable or set a valid value.
5. Restart in normal mode and verify.

Do not delete or manually edit `mysqld-auto.cnf` as your first troubleshooting step.

## 16. Safe Configuration Change Procedure

A system variable change should have clear before-state, change execution, verification, and rollback steps.

### 16.1. Before Making Changes

1. Identify the exact MySQL instance and version.
2. Read the variable documentation: scope, dynamic/read-only status, type, range, and default.
3. Record the current runtime value.
4. Check option files, persisted values, and command-line overrides.
5. Assess impact on CPU, RAM, disk, connections, and workload.
6. Identify the canonical configuration source and operator privileges.
7. Test on staging or a representative node when possible.

### 16.2. While Making Changes

Choose one method based on the goal:

- Runtime test: SET GLOBAL.
- Runtime change and preserve across restarts: SET PERSIST.
- Stage a startup-only value: SET PERSIST_ONLY.
- Synchronized management via canonical config: update option files/configuration management through the change process.

Record the statement, operator, timestamp, before/after values, and reason for change.

### 16.3. After Making Changes

~~~sql
SELECT
    @@GLOBAL.max_connections AS runtime_value;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';

SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

Then monitor:

- MySQL error log.
- Connection counts and refused connections.
- Memory usage and swap.
- CPU, I/O latency, and throughput.
- Query latency, lock waits, and connection pool health.
- Application behavior after configuration takes effect.

### 16.4. Rollback

Rollback must restore both runtime and startup sources:

- If only SET GLOBAL was used, reset the recorded runtime value.
- If SET PERSIST was used, re-persist the old value or run RESET PERSIST and set runtime per the canonical source.
- If SET PERSIST_ONLY was used, run RESET PERSIST on the new value before restarting or persist the old value.
- If an option file was used, restore the canonical config file and restart per procedure.

Do not just look at the current value and declare rollback complete. Verify the runtime value, persisted value, and configuration source after restart.

## 17. Practice: Managing max_connections Across States

This exercise demonstrates the difference between runtime and persistent settings. Perform it in a test environment with an appropriately privileged account; do not change production connection limits merely to complete an exercise.

### 17.1. Recording Current State

~~~sql
SELECT
    VERSION() AS mysql_version,
    @@GLOBAL.max_connections AS runtime_value;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';

SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

Record the runtime value, persisted value if present, and configuration source. If there is no persisted row, the variable may be coming from an option file, command line, or default.

### 17.2. Testing SET GLOBAL in a Lab Environment

~~~sql
SET GLOBAL max_connections = 250;

SELECT @@GLOBAL.max_connections;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Observe that runtime changes, while a persisted value is not automatically created or updated by SET GLOBAL.

### 17.3. Testing SET PERSIST

~~~sql
SET PERSIST max_connections = 280;

SELECT @@GLOBAL.max_connections;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Observe that both runtime and persisted values are updated. Record the change so you can roll it back after the exercise.

### 17.4. Testing RESET PERSIST

~~~sql
RESET PERSIST IF EXISTS max_connections;

SELECT @@GLOBAL.max_connections;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Confirm that the persisted row has been deleted while runtime may still hold the previously SET value. Use SET GLOBAL to return runtime to a value appropriate for the lab environment.

### 17.5. Practicing SET PERSIST_ONLY

Perform this part only if you have proper privileges, a compatible environment, and a startup-only variable chosen from the official documentation. Do not pick arbitrary values for variables that affect the data directory or startup capability.

~~~sql
SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT';

SELECT @@GLOBAL.innodb_flush_method;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'innodb_flush_method';
~~~

Verify that runtime has not changed while the persisted value has been written. Then remove the override if you do not plan to restart the lab with this setting:

~~~sql
RESET PERSIST IF EXISTS innodb_flush_method;
~~~

## 18. Exercises and Self-Check Questions

### 18.1. Choosing the Right Command

For each requirement, choose SET GLOBAL, SET PERSIST, SET PERSIST_ONLY, SET SESSION, or an option file:

1. Change `long_query_time` in the current session to investigate a query.
2. Increase `max_connections` immediately and preserve the value across restarts.
3. Stage a read-only variable for the next startup.
4. Test a dynamic value for 15 minutes and then revert.
5. Deploy the same configuration across 20 servers using a configuration management system.

### 18.2. Analyzing Post-Restart Values

An option file sets `max_connections = 200`. An administrator runs `SET PERSIST max_connections = 400`. Later, the option file is changed to 250 without deleting the persisted setting.

- Which value will likely take effect after a restart?
- Why does the option file change not win?
- What must be done for the option file to become the authoritative source?

### 18.3. Distinguishing Runtime and Persistent State

After running `SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT'`:

- Does the runtime value change immediately?
- Which table shows the saved value?
- When is the new value loaded?
- What must be checked before restarting?

### 18.4. Designing a Rollback

A SET PERSIST change causes increased connection errors in the application. Write a rollback procedure covering:

- The runtime value to restore.
- How to handle the persisted setting.
- How to verify the option file/command line.
- Which metrics to monitor after rollback.

### 18.5. Least Privilege

Explain why an account that only needs SET GLOBAL for a dynamic variable should not automatically be granted PERSIST_RO_VARIABLES_ADMIN or SUPER.

### 18.6. Self-Check Questions

1. How does SET GLOBAL differ from SET PERSIST?
2. Which state does SET PERSIST_ONLY change?
3. Why does SET GLOBAL not guarantee a value survives a restart?
4. How does changing the global value of a variable with both GLOBAL and SESSION scopes affect existing connections?
5. Can SET PERSIST be used to save a session variable?
6. Where is `mysqld-auto.cnf` stored and who manages its contents?
7. Why should you not edit `mysqld-auto.cnf` manually?
8. Does RESET PERSIST restore the runtime value?
9. Does a persisted setting take higher precedence than an option file?
10. Can a command-line option override a persisted setting?
11. Does `persisted_globals_load=OFF` delete `mysqld-auto.cnf`?
12. Why does running SET PERSIST on a primary not automatically configure replicas?
13. When should you use an option file instead of SET PERSIST?
14. What should be verified after a restart?

## 19. Pre-Change Checklist for System Variables

- [ ] Identified the exact MySQL instance and version.
- [ ] Read the variable documentation and confirmed GLOBAL/SESSION scope.
- [ ] Determined whether the variable is dynamic or read-only/startup-only.
- [ ] Checked data type, valid value range, and default value.
- [ ] Recorded the runtime value prior to making changes.
- [ ] Checked option files, `persisted_variables`, and command-line options.
- [ ] Identified the organization's canonical configuration source.
- [ ] Assessed impact on RAM, CPU, I/O, connections, and workload.
- [ ] Tested on staging or a representative node when possible.
- [ ] Used SET GLOBAL only for runtime changes.
- [ ] Used SET PERSIST when both runtime and persistent values are needed.
- [ ] Used SET PERSIST_ONLY for persistable startup changes.
- [ ] Verified appropriate SYSTEM_VARIABLES_ADMIN or PERSIST_RO_VARIABLES_ADMIN privileges.
- [ ] Did not grant SUPER more broadly than needed.
- [ ] Did not edit `mysqld-auto.cnf` manually.
- [ ] Checked `persisted_globals_load` and configuration precedence order.
- [ ] Determined how to apply changes on each node in the replication topology.
- [ ] Recorded the command, operator, timestamp, and reason for change.
- [ ] Prepared rollback for both runtime and persistent state.
- [ ] Verified runtime value, persisted value, and VARIABLE_SOURCE after the change.
- [ ] Checked error logs and metrics after restart.

## Conclusion

SET GLOBAL changes the runtime value of a dynamic global variable without automatically saving it across restarts. SET PERSIST both changes runtime and writes the value to persisted configuration. SET PERSIST_ONLY only writes the value for the next startup, making it suitable for startup-only variables or when delaying the effect. RESET PERSIST deletes saved overrides without automatically changing the runtime value.

MySQL stores persistent settings in `mysqld-auto.cnf` and loads them after option files and before command-line options. Consequently, administrators must track both runtime values and startup sources, grant least-privilege dynamic privileges, apply configuration individually per server, and maintain a recovery procedure if a value prevents the server from starting. Choosing the right statement is only the first step; a change is complete only after measuring its impact and verifying post-restart state.
