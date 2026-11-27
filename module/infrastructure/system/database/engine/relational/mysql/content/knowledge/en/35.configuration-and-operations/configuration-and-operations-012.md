# Determining Effective Configuration Instead of Reading Only One Config File

When MySQL runs with an unexpected configuration value, opening a single `my.cnf` or `my.ini` file is usually not enough to find the root cause. An instance can read multiple option files, receive extra arguments from the command line or OS service, load settings saved in `mysqld-auto.cnf`, and then be modified at runtime via `SET GLOBAL`. Each connection can also hold its own `SESSION` value.

Therefore, distinguish **declared values** from **effective values**. The effective value is the value the exact MySQL instance is actually using at inspection time, in the exact `GLOBAL` or `SESSION` scope. To explain why that value exists, trace the configuration source rather than reading only one file.

## 1. Sources That Can Supply Configuration to MySQL

A MySQL system variable can receive its value from multiple sources:

| Source | Role |
|---|---|
| Compiled-in defaults | Baseline values when no other configuration source overrides them |
| Option files (`my.cnf`, `my.ini`, and included files) | Startup configuration, typically in groups such as `[mysqld]` or `[server]` |
| `mysqld` command-line arguments | Values passed directly when the server process starts |
| `mysqld-auto.cnf` file | Settings saved via `SET PERSIST` or `SET PERSIST_ONLY` |
| `SET GLOBAL` | Dynamic changes to global values while the server is running |
| `SET SESSION` or application session initialization | Values specific to the current connection |

These sources have different scopes and application times. A line in a configuration file is just one input; it does not prove that the instance is currently using that value.

## 2. Confirming the Exact MySQL Instance Being Inspected

Before reading configuration, confirm the exact server, port, socket or named pipe, and data directory. A host can run multiple MySQL instances with different config files and ports.

Run these queries on the exact connection to the instance under investigation:

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS version_comment,
       @@hostname AS server_host,
       @@port AS server_port,
       @@datadir AS data_directory,
       @@basedir AS base_directory,
       @@server_uuid AS server_uuid;
```

Record these details at the time of inspection. If applications connect through a proxy, load balancer, or connection pool, identify which backend is actually serving the connection; repeated queries may land on different instances.

### Verifying the Service Process on the Operating System

On Windows, you can inspect the executable path and command line of the `mysqld` process:

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'mysqld.exe'" |
    Select-Object ProcessId, ExecutablePath, CommandLine
```

To see which service launched the process, inspect the service configuration using the actual service name:

```powershell
Get-CimInstance Win32_Service -Filter "Name = 'MySQL80'" |
    Select-Object Name, State, StartName, PathName
```

`PathName` can reveal whether the server uses `--defaults-file` or custom startup arguments. `MySQL80` is just an example; substitute the service name on the machine under inspection.

On Linux using systemd, check the running unit and service configuration contents:

```bash
systemctl status mysqld
systemctl cat mysqld
ps -ef | grep '[m]ysqld'
```

The unit name may be `mysql`, `mysqld`, or a custom name set by the package or administrator. Never assume every OS uses the same service name or the same option file paths.

## 3. Understanding How MySQL Reads Option Files

MySQL can read multiple option files in an order dependent on platform, installation method, and startup arguments. Files can contain multiple configuration groups; the server reads server-targeted groups, typically including `[mysqld]` and `[server]`. Reading only one of those files may miss a value set in another file or another group.

Directives inside an option file can also pull additional files into the read sequence:

```ini
[mysqld]
port = 3306
max_connections = 300

!include C:/mysql/conf/instance-extra.ini
!includedir C:/mysql/conf/conf.d
```

`!include` loads a specific file; `!includedir` loads option files inside the specified directory. During an investigation, follow all include files as well and determine which files the instance actually reads.

Certain options alter how option files are located:

- `--defaults-file=...`: requires using the specified option file instead of the default file chain.
- `--defaults-extra-file=...`: adds an option file to the reading process.
- `--no-defaults`: skips reading standard option files.

Options controlling defaults reading have strict position rules on the command line; in particular, `--defaults-file` must appear in the position MySQL requires, typically immediately after the program name. Use the actual process command line as the basis rather than guessing from common file locations.

You can ask the program to display options read from option files:

```bash
mysqld --print-defaults
```

Or use the `my_print_defaults` utility to read relevant groups:

```bash
my_print_defaults mysqld server
```

If the server was started with `--defaults-file` or `--defaults-extra-file`, pass that same option when checking. The output of these commands shows options parsed from files; it does not fully reflect runtime values from `SET GLOBAL`, session settings, or all persisted values.

`mysqld --verbose --help` helps inspect the list of options and defaults recognized by the binary. It is not a snapshot of runtime values from a running server. To know current values, query the instance itself via SQL.

## 4. Viewing Effective Global and Session Values

`SHOW GLOBAL VARIABLES` displays global values. `SHOW SESSION VARIABLES` displays the current connection's values for session-scoped variables:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';

SHOW SESSION VARIABLES LIKE 'time_zone';
SHOW SESSION VARIABLES LIKE 'sql_mode';
```

You can also access system variables directly:

```sql
SELECT @@GLOBAL.max_connections AS global_max_connections,
       @@GLOBAL.innodb_buffer_pool_size AS global_buffer_pool_size,
       @@SESSION.time_zone AS session_time_zone,
       @@SESSION.sql_mode AS session_sql_mode;
```

Scope should be stated explicitly:

- `@@GLOBAL.var_name` reads the global value.
- `@@SESSION.var_name` reads the current session's value if the variable supports session scope.
- `@@var_name` reads the session value if the variable has session scope; otherwise it reads the global value.
- `SHOW VARIABLES` defaults to session scope; use `SHOW GLOBAL VARIABLES` when you need the global value.

For example, `max_connections` is a global variable; `time_zone` can differ across connections. Running `SHOW VARIABLES LIKE 'time_zone'` from an admin account may return the admin connection's own session value, not necessarily the value used by the application's connection pool.

### Why Can GLOBAL and SESSION Differ?

`SET GLOBAL` changes the dynamic global value. For dual-scope variables, the new global value generally becomes the default for sessions created afterward; existing sessions keep their current session value until explicitly changed or the connection ends.

`SET SESSION` changes only the current connection:

```sql
SET SESSION time_zone = '+00:00';
SELECT @@GLOBAL.time_zone, @@SESSION.time_zone;
```

Therefore, when applications use a connection pool, inspect both connection initialization config and any `SET SESSION` statements executed when borrowing a connection. Session state can linger across reuses if the pool does not reset state.

## 5. Tracing Variable Sources with Performance Schema

Reading the current value tells you what MySQL is using; Performance Schema metadata helps uncover where the global value came from.

In MySQL 8.0, `performance_schema.variables_info` provides the configuration source and most recent change metadata for global system variables:

```sql
SELECT VARIABLE_NAME,
       VARIABLE_SOURCE,
       VARIABLE_PATH,
       SET_TIME,
       SET_USER,
       SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN (
    'max_connections',
    'innodb_buffer_pool_size',
    'slow_query_log',
    'time_zone'
)
ORDER BY VARIABLE_NAME;
```

Key columns:

- `VARIABLE_SOURCE`: source recorded by MySQL for the global value, such as compiled default, option file, command line, persisted setting, or dynamic change.
- `VARIABLE_PATH`: option file path when the source is a file and metadata is available.
- `SET_TIME`: timestamp when the variable was dynamically modified, if applicable.
- `SET_USER` and `SET_HOST`: account and host associated with the most recent dynamic change, if applicable.

Exact source values depend on version and setup. Read the returned data rather than assuming source names. If `VARIABLE_SOURCE` shows the variable came from an option file, `VARIABLE_PATH` identifies which file to inspect. If the variable was changed dynamically, the timestamp and account narrow down the investigation.

`performance_schema.persisted_variables` lists persisted variables:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
ORDER BY VARIABLE_NAME;
```

These two tables complement `SHOW VARIABLES`: one helps trace global value origins, while the other shows persisted settings. They do not replace checking session variables on the application's own connection.

## 6. Understanding `SET GLOBAL`, `SET PERSIST`, and `SET PERSIST_ONLY`

These three statements have distinct effects:

| Statement | Runtime Effect | Preserved Across Restarts |
|---|---|---|
| `SET GLOBAL` | Changes dynamic global value if permitted | No |
| `SET PERSIST` | Changes dynamic global value | Yes, written to `mysqld-auto.cnf` |
| `SET PERSIST_ONLY` | Does not change running value | Yes, applied when server restarts |

Example:

```sql
-- Runtime change only
SET GLOBAL max_connections = 400;

-- Change runtime and save for future startups
SET PERSIST max_connections = 400;

-- Save only for next startup, leave current runtime unchanged
SET PERSIST_ONLY max_connections = 500;
```

Examples illustrate syntax; choose values suited to RAM, connection count, workload, and variable limits on the real server. Not every variable can be modified dynamically or persisted. Read-only or startup-only variables may require `SET PERSIST_ONLY` if the variable supports persistence.

Persisted settings are written to `mysqld-auto.cnf` in the data directory. MySQL reads this file at startup and applies persisted values after processing option files and the command line; therefore they can override values declared in those sources. Never edit `mysqld-auto.cnf` directly; use SQL to modify or remove persisted settings.

You can check whether loading persisted settings is enabled:

```sql
SHOW GLOBAL VARIABLES LIKE 'persisted_globals_load';
```

If `persisted_globals_load` is disabled, the server skips loading persisted settings at startup. Check this variable when values in `mysqld-auto.cnf` fail to take effect as expected.

### Removing Persisted Settings

Remove one variable from the persisted list:

```sql
RESET PERSIST max_connections;
```

This statement removes the setting saved for future startups; it does not automatically change the active runtime value. If runtime must change immediately, run `SET GLOBAL` separately with the desired value.

To remove all persisted settings, MySQL provides `RESET PERSIST` without a variable name. This is a broad-impact operation; inspect the persisted list beforehand and run it only when you have clearly identified which settings should be removed.

Modifying system variables requires appropriate administrative privileges, typically `SYSTEM_VARIABLES_ADMIN`; some operations on read-only variables also require `PERSIST_RO_VARIABLES_ADMIN`. Exact privileges depend on variable type and command. Do not grant broad administrative privileges to applications merely so apps can alter server configuration.

## 7. Precedence Order and Explaining Conflicts

When multiple sources set the same variable, examine both read order and application timing. A helpful investigative model:

1. MySQL's compiled-in defaults form the initial baseline.
2. Option files are read according to the instance's rules and order; values processed later can override earlier ones.
3. Command-line arguments can override values from option files.
4. At startup, persisted settings in `mysqld-auto.cnf` are applied after option files and the command line, so they can override them.
5. Once the server is running, `SET GLOBAL` can change dynamic global values.
6. `SET SESSION` and application-side settings can make a single connection's value differ from global.

The exact option-file order depends on platform and startup arguments, so inspect the command line and the variable's `VARIABLE_SOURCE`/`VARIABLE_PATH` metadata. Use this model to guide where to look; never use it in place of runtime evidence.

Example: `my.ini` sets `max_connections = 300`, the service starts with `--max-connections=350`, yet `mysqld-auto.cnf` holds a persisted value of `400`. After startup, the global value may be `400`. If an administrator then runs `SET GLOBAL max_connections = 450`, the runtime value will be `450` until the server restarts or is changed again. To explain why, inspect the runtime value, `variables_info`, and `persisted_variables` together.

## 8. Troubleshooting Workflow When Configuration Differs from Expectations

Suppose operations changed `innodb_buffer_pool_size` in `my.ini`, yet after a restart the global value did not change. Follow this sequence:

1. **Confirm the instance:** query `@@hostname`, `@@port`, `@@datadir`, and `@@server_uuid` to ensure you are inspecting the right server.
2. **Inspect the process:** identify the service executable and command line, looking for `--defaults-file`, `--defaults-extra-file`, or `--no-defaults`.
3. **Identify actual option files:** run `mysqld --print-defaults` or `my_print_defaults` with the same defaults flags; trace `!include` and `!includedir`.
4. **Read runtime state:** execute `SHOW GLOBAL VARIABLES` or `SELECT @@GLOBAL...` on the exact instance.
5. **Trace the source:** inspect `performance_schema.variables_info` to see whether the variable came from a file, command line, persisted setting, or dynamic change.
6. **Check persisted settings:** inspect `performance_schema.persisted_variables` and `persisted_globals_load`.
7. **Check session state:** if the application still sees a different value, run queries on the application's own connection and check session/connection pool initialization statements.
8. **Adjust one source:** fix the exact identified source, restart if the variable is startup-only, and re-verify with SQL.

Do not edit multiple files simultaneously or delete `mysqld-auto.cnf` on a hunch. Doing so can obscure the conflicting source and wipe out other persisted settings.

## 9. Example Comparing GLOBAL and SESSION Across Two Connections

Suppose an administrator runs:

```sql
SET GLOBAL time_zone = '+00:00';
```

A new connection usually inherits its default session value from the new global value. However, previously opened application connections may still retain the old `time_zone`. Check from each connection:

```sql
SELECT CONNECTION_ID() AS connection_id,
       @@GLOBAL.time_zone AS global_time_zone,
       @@SESSION.time_zone AS session_time_zone;
```

If two connections return different `session_time_zone` values, inspect `SET SESSION` statements, driver settings, connection init SQL, and connection reuse in the pool. You cannot conclude the server ignored `SET GLOBAL` simply because an older connection still has an older session value.

## 10. Effective Configuration Verification Checklist

| Question | Evidence to Collect |
|---|---|
| Are you inspecting the right server? | `VERSION()`, `@@hostname`, `@@port`, `@@datadir`, `@@server_uuid` |
| With what arguments was the server started? | Process command line or service/unit configuration |
| Which option files are read? | `--defaults-file`, `--defaults-extra-file`, `mysqld --print-defaults`, include directives |
| What is the runtime global value? | `SHOW GLOBAL VARIABLES`, `@@GLOBAL.variable` |
| Where did the value come from? | `performance_schema.variables_info` |
| Are there persisted settings? | `performance_schema.persisted_variables`, `persisted_globals_load` |
| Does the app apply a session override? | `@@SESSION.variable` on the app's actual connection and pool config |
| Is it verified after the change? | Re-read runtime, source metadata, and verify after restart if needed |

## 11. Self-Check

1. Why is reading a single `my.ini` file insufficient to conclude what value MySQL is effectively using?
2. How does `--defaults-file` differ in purpose from `--defaults-extra-file`?
3. What does `mysqld --print-defaults` tell you, and what does it not tell you?
4. Why can `@@GLOBAL.time_zone` and `@@SESSION.time_zone` differ?
5. How do `SET GLOBAL`, `SET PERSIST`, and `SET PERSIST_ONLY` differ regarding runtime and restarts?
6. How does `performance_schema.variables_info` help trace configuration sources?
7. If a value in `mysqld-auto.cnf` overrides an option file, which table should you check to confirm?
8. When an application sees an old session value after `SET GLOBAL`, where should you investigate?
