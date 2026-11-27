# GLOBAL, SESSION, Read-Only, and Dynamic System Variables

MySQL uses system variables to control the behavior of the server and individual connections. A variable can have GLOBAL scope, SESSION scope, or both; some variables are read-only at runtime, while others can be changed dynamically without restarting the server. Understanding scope and mutability helps administrators configure safely, avoid unintended effects on active connections, and know when settings must be persisted across restarts.

In the DATABASE_MYSQL module, this lesson focuses on reading variable values, distinguishing GLOBAL from SESSION, changing variables with SET, identifying dynamic versus startup-only variables, using SET PERSIST/SET PERSIST_ONLY, inspecting value sources, and managing configuration change privileges.

## 1. What Is a System Variable?

A system variable is a configuration parameter provided by MySQL to control server or session operations. For example:

- max_connections limits the number of concurrent connections the server accepts.
- sql_mode defines rules for SQL syntax and data handling.
- time_zone controls the time zone used in a session.
- sort_buffer_size affects session sort memory.
- read_only and super_read_only control write-restriction mode.

Variable values can come from compiled-in defaults, configuration files, command-line options, persisted configuration files, or runtime SET statements. When investigating an unexpected value, check both the current value and the source that set it.

System variables differ from user-defined variables. System variables have names like @@GLOBAL.max_connections and are managed by MySQL. User-defined variables are set per session using `@name` syntax and are not server configuration parameters.

## 2. Two Main Scopes: GLOBAL and SESSION

GLOBAL is server-wide scope. SESSION is the scope of a single current connection.

| Scope | Impact | Lifetime |
|---|---|---|
| GLOBAL | Server-wide value; usually the initial value for new sessions | Current runtime; may be lost after restart if not persisted |
| SESSION | Affects only the current connection | Until the session ends or is reset |

Some variables have both scopes. Some are GLOBAL-only, and some are SESSION-only. Do not assume that every variable can be read or set in both scopes.

Example of sql_mode having both GLOBAL and SESSION values:

~~~sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
~~~

The two values can differ because the current session may have set its own sql_mode. When a new connection is created, the session typically inherits its initial value from the GLOBAL variable at connection time.

## 3. Reading Variables with @@GLOBAL and @@SESSION

Explicit read syntax:

~~~sql
SELECT @@GLOBAL.max_connections;
SELECT @@GLOBAL.sql_mode;
SELECT @@SESSION.sql_mode;
~~~

If a variable has both scopes, you can use `@@variable_name` to read the SESSION value:

~~~sql
SELECT @@sql_mode;
~~~

To avoid ambiguity during diagnostics, prefer writing `@@GLOBAL` or `@@SESSION` explicitly. If a variable is GLOBAL-only, referencing `@@SESSION.variable_name` may return an error because the variable has no session scope.

## 4. Listing Variables with SHOW VARIABLES

SHOW VARIABLES displays variable values in SESSION scope by default:

~~~sql
SHOW VARIABLES;
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'time_zone';
~~~

To view GLOBAL values:

~~~sql
SHOW GLOBAL VARIABLES;
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'read_only';
~~~

SHOW SESSION VARIABLES explicitly indicates session scope:

~~~sql
SHOW SESSION VARIABLES LIKE 'sort_buffer_size';
~~~

When comparing configuration, query both scopes if the variable supports both GLOBAL and SESSION. A SESSION value differing from GLOBAL is not necessarily an error; it may have been intentionally set by the application or connection initialization.

## 5. Viewing Variables via Performance Schema

Performance Schema provides metadata tables to query system variables:

~~~sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.global_variables
WHERE VARIABLE_NAME IN (
    'max_connections',
    'sql_mode',
    'read_only'
);
~~~

SESSION values:

~~~sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.session_variables
WHERE VARIABLE_NAME IN (
    'sql_mode',
    'time_zone',
    'sort_buffer_size'
);
~~~

To find the configuration source and setting metadata, you can query `performance_schema.variables_info`:

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
    'sql_mode',
    'innodb_buffer_pool_size'
);
~~~

Metadata columns help investigate whether a variable came from defaults, a configuration file, the command line, persisted configuration, or was changed at runtime. Specific information and values depend on the MySQL version; verify the Performance Schema layout on the target server before automating reports.

## 6. GLOBAL-Only, SESSION-Only, and Dual-Scope Variables

Three scope categories:

| Category | Readable via | Settable via |
|---|---|---|
| GLOBAL-only | `@@GLOBAL` or SHOW GLOBAL VARIABLES | Only in GLOBAL scope if the variable allows modification |
| SESSION-only | `@@SESSION` or SHOW SESSION VARIABLES | Only in the current session if the variable allows modification |
| GLOBAL and SESSION | Both values can be read | Can be set in the corresponding scope if the variable allows modification |

For example, `max_connections` is a GLOBAL-only variable:

~~~sql
SELECT @@GLOBAL.max_connections;
~~~

The `sql_mode` variable has both GLOBAL and SESSION scopes:

~~~sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
~~~

When reading documentation for a variable, check three separate properties: scope, dynamicity, and required privileges. Scope answers where the variable exists; dynamicity answers whether it can be changed at runtime; privilege answers which accounts are permitted to change it.

## 7. Setting SESSION Variables with SET SESSION

SET SESSION changes the value for the current connection:

~~~sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;
~~~

Example setting the time zone for a session:

~~~sql
SET SESSION time_zone = '+07:00';

SELECT @@SESSION.time_zone;
~~~

SESSION changes do not affect other connections and are not automatically written to server configuration. When the session ends, its custom session value is gone.

This is the appropriate approach when a task requires custom behavior, such as exporting data in a specific time zone or running a report with a specific SQL mode. Applications using a connection pool must initialize or reset session state consistently when borrowing and returning connections.

## 8. Setting GLOBAL Variables with SET GLOBAL

SET GLOBAL changes the server-wide value at runtime:

~~~sql
SET GLOBAL max_connections = 300;

SELECT @@GLOBAL.max_connections;
~~~

GLOBAL changes typically affect new sessions or operations that reference the GLOBAL value directly. They do not automatically overwrite the SESSION copy already created in existing connections.

Example with sql_mode:

~~~sql
SET GLOBAL sql_mode =
    'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';
~~~

Existing connections may still retain the old SESSION sql_mode. For a current session to use the new value, execute SET SESSION explicitly or establish a new connection according to the application workflow.

SET GLOBAL does not persist the configuration permanently. If the server restarts, the value may revert to the previous startup configuration source unless a persistence mechanism is used or the configuration file is updated.

## 9. Distinguishing GLOBAL and SESSION Changes

Consider two connections, A and B:

1. A connects when GLOBAL sql_mode has value X; A's SESSION receives X.
2. B connects; B's SESSION also receives X.
3. The administrator runs SET GLOBAL sql_mode = Y.
4. Existing A and B may still keep SESSION sql_mode = X.
5. C connects newly after the change; C's SESSION receives Y.
6. A can independently run SET SESSION sql_mode = Z; that does not change B, C, or GLOBAL.

Diagram:

~~~mermaid
flowchart TD
    G[GLOBAL sql_mode = X] --> A[Session A receives X]
    G --> B[Session B receives X]
    G2[SET GLOBAL sql_mode = Y] --> NG[New session receives Y]
    A --> AS[SET SESSION sql_mode = Z]
    AS -. does not change .-> G2
    AS -. does not change .-> B
~~~

This model explains why a GLOBAL change does not necessarily alter the behavior of a running application immediately. When deploying session-sensitive changes, plan for reconnection or session resets.

## 10. What Is a Dynamic Variable?

A dynamic variable can be changed while the server is running without a restart, provided that:

- The variable supports the scope being set.
- The new value is within the allowed range.
- The account has the appropriate privileges.
- No runtime condition or other dependency prevents the change.

For example, `max_connections` is a dynamic GLOBAL variable:

~~~sql
SET GLOBAL max_connections = 400;
~~~

For example, `sort_buffer_size` supports both SESSION and GLOBAL scopes:

~~~sql
SET SESSION sort_buffer_size = 1048576;
~~~

Changing a dynamic variable does not mean the change is risk-free. Increasing a per-session buffer can multiply memory usage by the number of sessions actually executing operations that allocate that buffer. Increasing `max_connections` also increases the potential number of connections the server must serve and their associated memory.

Before making changes, read the variable description, min/max limits, units, scope, dynamic status, and resource impact.

## 11. Non-Dynamic and Read-Only Variables

A non-dynamic variable cannot be changed with a regular runtime SET statement. It typically needs to be configured at startup via an option file or command-line option. Some read-only variables only reflect server state and have no way to be configured to an arbitrary value.

Example reading version:

~~~sql
SELECT @@GLOBAL.version;
~~~

`version` is information provided by the server; you cannot use SET GLOBAL version to change the server version.

Do not conflate the concepts:

- Dynamic: can be changed at runtime depending on scope and privileges.
- Non-dynamic/static: must be configured at startup or via the persist-only mechanism if supported by the variable.
- Read-only: cannot be assigned via regular runtime SET statements.

A variable can be GLOBAL-only and non-dynamic; another variable can be GLOBAL-only yet dynamic. Scope and mutability are two independent properties.

## 12. Read-Only System Variables vs. Server read_only Mode

These are two distinct meanings:

1. A system variable marked as read-only means the value of that variable itself cannot be modified with a regular runtime SET statement.
2. MySQL's `read_only` variable is a server configuration toggle used to restrict client data-write operations.

`read_only` is a system variable that can be changed dynamically under appropriate conditions and privileges. `super_read_only` extends read-only mode and also restricts certain accounts with connection administration privileges that `read_only` may exempt.

Example checking the mode:

~~~sql
SELECT
    @@GLOBAL.read_only AS read_only_mode,
    @@GLOBAL.super_read_only AS super_read_only_mode;
~~~

Do not infer that the `read_only` variable itself is immutable. Also do not confuse the server being in read-only mode with the read-only mutability attribute of another configuration variable.

## 13. SET PERSIST: Changing Runtime and Saving for Subsequent Startups

MySQL 8.0.11 introduced persisted system variables. SET PERSIST changes a GLOBAL variable at runtime and saves the value to be reapplied when the server restarts:

~~~sql
SET PERSIST max_connections = 400;
~~~

Unlike SET GLOBAL:

- SET GLOBAL only changes runtime state.
- SET PERSIST changes runtime state and writes persisted configuration.

Persisted values are managed by MySQL in the `mysqld-auto.cnf` file inside the data directory. Do not edit this file manually; use SET PERSIST or RESET PERSIST so MySQL manages its contents and metadata.

SET PERSIST applies only to GLOBAL variables that can be persisted and are supported by the version. Certain variables, values, or special states cannot be persisted.

## 14. SET PERSIST_ONLY: Saving Configuration Without Changing Runtime

SET PERSIST_ONLY writes a value to persisted configuration without changing the current runtime value:

~~~sql
SET PERSIST_ONLY some_global_variable = some_value;
~~~

The illustrative syntax above uses placeholder names and values; replace them with an actual GLOBAL variable that supports persist-only and a valid value according to the running version's documentation.

SET PERSIST_ONLY is useful for variables that can only be configured at startup. After writing the persisted value, the currently running server continues using its existing value; the new value takes effect only after a restart.

Not every read-only variable can be persisted. Some status variables have no configuration meaning; some variables are excluded from the persisted variable mechanism. Check the supported list and privileges before executing.

## 15. RESET PERSIST and Reverting Saved Configuration

To remove a persisted setting:

~~~sql
RESET PERSIST max_connections;
~~~

This statement removes the saved value for the variable from persisted configuration. It does not automatically restore the current runtime value to its default; if the variable was modified via SET GLOBAL or SET PERSIST at runtime, the running value may remain until changed or restarted.

To remove all persisted system variable settings:

~~~sql
RESET PERSIST;
~~~

This is a broad-impact operation. Before using it, inspect existing persisted settings and remove only intended configurations. After removal, verify persisted metadata and plan a restart if you need runtime values to return to the remaining configuration sources.

You can view persisted variables via:

~~~sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
ORDER BY VARIABLE_NAME;
~~~

## 16. Configuration Sources and Precedence Order

A variable can be set by multiple sources:

- Compiled-in default values in MySQL.
- Option files such as my.cnf or my.ini.
- Command-line arguments when starting mysqld.
- Persisted configuration created by SET PERSIST or SET PERSIST_ONLY.
- Runtime SET GLOBAL statements.
- Runtime SET SESSION statements within a connection.

The current value is the result of startup initialization and runtime modifications. A session may have a value different from global due to a session override.

To investigate the source, use:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

VARIABLE_SOURCE and VARIABLE_PATH help identify the configuration source depending on the version. For a variable recently changed at runtime, metadata may reflect the source or the most recent set details. Do not infer which file a value came from based solely on a single row from SHOW VARIABLES.

## 17. Privileges Required to Modify System Variables

Reading variables typically requires appropriate query privileges on the server and Performance Schema. Modifying GLOBAL variables requires configuration administration privileges.

In MySQL 8.0, key dynamic privileges include:

- SYSTEM_VARIABLES_ADMIN: allows performing many system variable administration operations such as SET GLOBAL and SET PERSIST.
- PERSIST_RO_VARIABLES_ADMIN: allows persisting certain read-only variables using SET PERSIST_ONLY according to version rules.
- SUPER is a legacy privilege that has been decomposed into multiple dynamic privileges; do not grant broad SUPER just so an application can modify a single variable.

Some sensitive variables also have additional conditions or privileges. Specific privileges should be checked in the variable and MySQL version documentation. SET SESSION for one's own session generally does not require SYSTEM_VARIABLES_ADMIN, though it may still be restricted by variable type or special privileges.

Check privileges:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

Operational principles:

1. Only DBAs or configuration administration accounts may modify GLOBAL variables.
2. Do not grant system variable administration privileges to ordinary application accounts.
3. Grant only the minimum required dynamic privileges to operators.
4. Record who made the change, timestamp, old value, and new value.
5. Test changes in a staging environment before production.

## 18. Value Limits and Validation

Not every value is accepted. MySQL may reject a value when:

- The value is outside min/max bounds.
- The data type is invalid.
- An enum value is not in the supported list.
- The variable does not support the target scope.
- The variable is non-dynamic.
- The account lacks privileges.
- Another runtime condition or dependency is not satisfied.

Example setting a session value:

~~~sql
SET SESSION max_execution_time = 5000;
~~~

`max_execution_time` limits SELECT execution time in a session in milliseconds in supported versions. If you need to change it for all new sessions, consider GLOBAL after checking scope and policy.

Do not use a single bulk SET statement to change many variables in production without verifying each value and rollback capability. If one variable is unsupported or has an invalid scope, the entire statement may fail.

## 19. Checking Variables Before and After Changes

A safe workflow:

~~~sql
SELECT
    @@GLOBAL.max_connections AS global_before;

SET GLOBAL max_connections = 400;

SELECT
    @@GLOBAL.max_connections AS global_after;
~~~

If persistence is needed:

~~~sql
SET PERSIST max_connections = 400;

SELECT @@GLOBAL.max_connections;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

After making the change, verify:

- Whether the runtime value is correct.
- Whether new sessions receive the expected value.
- Whether existing sessions require reconnection or reset.
- Whether persisted configuration contains the expected value.
- Whether logs show configuration warnings or errors.
- Whether server resource usage increases unexpectedly.

Do not rely solely on the SET statement returning success. Read the variable back and monitor the impact under real workload.

## 20. Example: Managing sql_mode for an Application

Suppose the server needs to set the default SQL mode for new connections:

~~~sql
SELECT @@GLOBAL.sql_mode;

SET PERSIST sql_mode =
    'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

SELECT @@GLOBAL.sql_mode;
~~~

An existing session may still retain the old sql_mode. To check:

~~~sql
SELECT
    @@GLOBAL.sql_mode AS server_default,
    @@SESSION.sql_mode AS this_connection;
~~~

If the application needs the same SQL mode immediately on open connections, set SESSION in the connection initialization step or reconnect according to plan. Do not assume SET PERSIST has updated all existing sessions.

Before changing sql_mode, run the data and query test suite. Changing strictness can turn previously accepted INSERT/UPDATE warnings into errors.

## 21. SET_VAR Hint for a Single Statement

Some system variables can be set temporarily for a single statement using the SET_VAR optimizer hint if supported by the variable and version:

~~~sql
SELECT /*+ SET_VAR(sort_buffer_size = 262144) */
       customer_id, total_amount
FROM orders
ORDER BY total_amount DESC
LIMIT 100;
~~~

SET_VAR is not the same as SET SESSION: it applies within the scope of the hinted statement and does not become a persistent setting for the connection. Not every system variable is permitted with SET_VAR; check the supported list and verify whether the optimizer accepted the hint.

This is a narrow-scope tuning tool. Do not use hints to mask query design issues or missing indexes.

## 22. Distinguishing Runtime Configuration and Startup Configuration

| Need | Common Method | Effective When |
|---|---|---|
| Change current session | SET SESSION | Immediately in the session |
| Change server runtime | SET GLOBAL | Immediately at runtime; old sessions may keep their own values |
| Change runtime and survive restart | SET PERSIST | Immediately at runtime and on subsequent startups |
| Save only for next restart | SET PERSIST_ONLY | After restart |
| Configure from scratch on mysqld startup | Option file/command line | At server startup |
| Remove a persisted override | RESET PERSIST variable | Removes persisted value; runtime does not revert automatically |

Do not choose SET PERSIST merely out of convenience. For high-impact changes such as connection limits, buffer pool, logging, or replication, evaluate RAM, CPU, I/O, restart time, and rollback capability.

## 23. Runbook for Changing a GLOBAL Variable in Production

1. Identify the exact variable name and MySQL version.
2. Check scope, dynamic status, min/max, units, and privileges in the documentation.
3. Record current GLOBAL and SESSION values.
4. Check configuration sources in variables_info and persisted_variables if applicable.
5. Evaluate impact on RAM, CPU, I/O, connections, and workload.
6. Test in staging with data and load close to production.
7. Choose SET GLOBAL, SET PERSIST, or option file modification according to persistence requirements.
8. Read back runtime and persisted values.
9. Verify new sessions and existing sessions.
10. Monitor error logs, metrics, and latency after the change.
11. Document the operator, timestamp, and rollback plan.
12. If a restart is needed, execute during a maintenance window and verify after server startup.

## 24. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| SET GLOBAL returns access denied | Missing SYSTEM_VARIABLES_ADMIN or equivalent privilege | Check SHOW GRANTS and grant least privilege |
| SET SESSION reports variable does not exist in scope | GLOBAL-only variable | Use GLOBAL if permitted |
| SET GLOBAL reports variable is read only | Variable cannot be changed at runtime | Check startup-only/read-only status and SET PERSIST_ONLY if supported |
| Changed GLOBAL but old sessions did not change | Sessions already hold their own copy | Reconnect or run SET SESSION per plan |
| Value lost after restart | Only SET GLOBAL was used | Use SET PERSIST or an appropriate option file |
| SET PERSIST_ONLY did not change current value | Expected behavior | Restart in a maintenance window to apply |
| RESET PERSIST left runtime value unchanged | RESET only removes the persisted override | Use SET GLOBAL or restart to fall back to remaining config |
| SET statement rejected | Value out of range, wrong type, or non-dynamic variable | Check variable description and valid range |
| Application has inconsistent session state | Connection pool reuses sessions | Standardize connection initialization/reset steps |
| Confusing read-only variable with read_only mode | Two different concepts | Distinguish variable mutability from server write-restriction mode |

## 25. Hands-On Exercises

1. Use SHOW GLOBAL VARIABLES and SHOW SESSION VARIABLES to find sql_mode.
2. Read `@@GLOBAL.sql_mode` and `@@SESSION.sql_mode` on the same connection.
3. Open two connections; change SESSION sql_mode on connection A and confirm connection B is unchanged.
4. Change GLOBAL sql_mode in a test environment; confirm new sessions receive the new value while old sessions may retain the previous value.
5. Read max_connections and explain why it is a GLOBAL-only variable.
6. Try running SET SESSION max_connections in a test environment and observe the scope error.
7. Check `version` and explain why SET GLOBAL version is not possible.
8. Change a dynamic variable at runtime, read back the value, and restart the test environment to observe that the value is not persisted.
9. Use SET PERSIST on a GLOBAL variable that supports persistence; check performance_schema.persisted_variables.
10. Use SET PERSIST_ONLY on a variable documented as startup-only; verify runtime has not changed and the post-restart value changes.
11. Use RESET PERSIST to remove an override; distinguish persisted value from runtime value.
12. Query performance_schema.variables_info to view configuration sources.
13. Compare a read-only system variable with the server's read_only and super_read_only variables.
14. Write a runbook for changing max_connections or a buffer variable including resource assessment, post-change verification, and rollback plan.

You complete this lesson when you can read and set variables in the right scope, explain why GLOBAL does not automatically overwrite existing SESSIONs, distinguish dynamic from startup-only/read-only variables, use SET GLOBAL/SESSION/PERSIST/PERSIST_ONLY properly, and inspect configuration sources. Changing system variables is an operational action with broad impact; always verify scope, privileges, persistence, and resource impact before applying.
