# Option Files, Command-Line Options, and Configuration Precedence

MySQL receives configuration from multiple sources: compiled-in defaults, option files, command-line options, and persisted system variable settings. When the server fails to start or a parameter has an unexpected value, you must determine exactly which files the program read, which groups it read, and which source wins when the same option appears multiple times.

Option files are typically `my.cnf` on Unix/Linux or `my.ini` on Windows. A file contains groups such as `[mysqld]`, `[client]`, and `[mysql]`; each program reads only the groups applicable to it. Command-line options can override values in a file. On MySQL 8.0, persisted system variables are stored in `mysqld-auto.cnf` and have their own precedence rules.

Understanding the configuration order helps prevent editing the wrong file, prevents old values from silently overriding new ones, and enables safe rollout of changes. This lesson focuses on how MySQL locates option files, syntax and groups, options that control file reading, precedence order, persisted variables, and configuration verification workflows.

## 1. MySQL Configuration Sources

A MySQL program can receive options from the following sources:

1. **Default values:** values used by the program when no configuration source sets that option.
2. **Option files:** configuration files containing groups and options, such as `my.cnf` or `my.ini`.
3. **Command-line options:** options passed when starting `mysqld`, `mysql`, or other client tools.
4. **Persisted system variables:** global system variables saved using `SET PERSIST`/`SET PERSIST_ONLY` on MySQL 8.0.
5. **Runtime settings:** system variable values changed using `SET GLOBAL` or `SET SESSION` while the server or client is running.

Not every option is a system variable. Some options only control how the program reads option files or client behavior; they cannot be changed via `SET GLOBAL`. Conversely, not every system variable can be changed at runtime or persisted.

## 2. What Is an Option File?

An option file is a text file containing grouped settings. The server and clients read the file at startup to retrieve options relevant to each program.

Example server configuration:

```ini
[mysqld]
max_connections=250
innodb_buffer_pool_size=2G
slow_query_log=ON
long_query_time=1
```

Example client configuration:

```ini
[client]
host=db.internal.example
port=3306
default-character-set=utf8mb4

[mysql]
prompt=\\u@\\h [\\d]> 
```

In an option file, option names are usually written without the `--` prefix. For example, the line `max_connections=250` corresponds to the command-line option `--max-connections=250`.

## 3. Where Does MySQL Look for Option Files?

Default paths depend on the operating system, packaging, installation directory, and specific program. On Unix/Linux, MySQL typically checks system configuration locations such as `/etc/my.cnf`, `/etc/mysql/my.cnf`, build-defined configuration directories, files in the home directory, or files relative to `MYSQL_HOME` for the server. On Windows, locations are usually relative to the Windows directory, drive root, MySQL installation directory, or data directory.

Do not guess which file is in effect based on name or location. Ask the MySQL program directly:

```bash
mysqld --verbose --help
```

The beginning of the output shows the option files and option groups the server expects to read. For the client:

```bash
mysql --help
```

The client output also displays the option file locations and the groups read. Exact syntax and paths may vary by version and distribution; the output from the deployed binary is the actual source of truth.

## 4. Identifying the Right Program and Group

An option file can contain configuration for multiple programs. Each program reads only the groups it supports.

| Group | Program that typically reads it |
| --- | --- |
| `[client]` | Many MySQL client programs |
| `[mysql]` | MySQL command-line client `mysql` |
| `[mysqld]` | MySQL server |
| `[server]` | Applicable server programs |
| `[mysqldump]` | `mysqldump` utility |
| `[mysqladmin]` | `mysqladmin` utility |

For example, `max_connections` belongs to server configuration and should be placed in `[mysqld]` or an appropriate server group. Putting it in `[mysql]` will not make the server pick up that value. Similarly, the client `default-character-set` is not a server configuration.

Some versions support version-suffixed groups such as `[mysqld-8.0]` or `[mysqld-8.4]`. Use version-specific groups only when the target binary actually reads them; verify the group list via `mysqld --verbose --help`.

## 5. Basic Option File Syntax

An option file typically consists of comments, group headers, and options:

```ini
# Server configuration
[mysqld]
port=3306
max_connections=250
skip-name-resolve

; Client defaults
[client]
port=3306
default-character-set=utf8mb4
```

Common rules:

- Lines starting with `#` or `;` are comments.
- A group begins with `[group_name]`.
- Options placed after a group header belong to that group until the next group header.
- In an option file, `--` is typically omitted before the option name.
- Boolean options can be written as `name`, `name=ON`, `name=TRUE`, or `name=1` depending on the option.
- Negated options can use forms like `skip-name-resolve` or `disable-...` if supported by the option.
- Values containing spaces must be quoted according to option file syntax.

Option names can use hyphens or underscores according to MySQL compatibility rules, but you should standardize on one style in the configuration repository for easier code review.

## 6. Boolean Options and Typed Values

Boolean examples:

```ini
[mysqld]
event-scheduler=ON
local-infile=OFF
```

Some options have negated forms:

```ini
[mysqld]
skip-name-resolve
```

Do not mechanically apply `skip-` to every option name. Check the specific option in the documentation for the running MySQL version.

Examples of numeric options and units:

```ini
[mysqld]
max_connections=250
innodb_buffer_pool_size=2G
tmp_table_size=64M
```

Values must be within the valid range for the variable. MySQL may reject invalid values, emit warnings, or adjust them according to each variable's rules. Do not assume all variables accept the same unit suffixes.

## 7. Including Other Configuration Files

An option file can include another file using the `!include` directive or include a directory using `!includedir` on supported platforms and versions.

Example:

```ini
!include /etc/mysql/conf.d/server-base.cnf
!includedir /etc/mysql/conf.d
```

These are directives for the option-file parser, not system variables. They are useful for splitting configuration by component, such as `server.cnf`, `innodb.cnf`, and `logging.cnf`.

When using `!includedir`, do not rely on filename ordering if the application requires one option to override another. File selection order within a directory may depend on the platform and implementation. Verify using `--print-defaults` output and actual runtime values.

## 8. Order of Reading Multiple Option Files

MySQL may read multiple option files in an order determined by the program and platform. When the same option appears in multiple files, the value read later typically overrides the value read earlier.

Illustrative example:

```ini
# Base configuration file read first
[mysqld]
max_connections=200
```

```ini
# Supplementary configuration file read later
[mysqld]
max_connections=300
```

If both files are read by the server in the order above, the final value from option files is `300`. However, do not conclude this solely from file contents; confirm which files are actually read and their order.

When an option appears multiple times within the same source, the later occurrence usually takes effect depending on how the parser handles that option. Some options may have cumulative or special behavior; do not apply the "last wins" rule to every list option without checking the documentation.

## 9. Command-Line Options Override Option Files

Options passed directly when starting a program generally take higher precedence than options read from a file.

For example, if the server is started with:

```bash
mysqld --defaults-file=/etc/mysql/my.cnf --max-connections=400
```

If the file contains `max_connections=250`, the `--max-connections=400` parameter on the command line overrides the file value for that startup.

This frequently happens when a service manager, container entrypoint, orchestration platform, or startup script passes additional parameters. Editing `my.cnf` without checking the command line may fail to change the runtime value as expected.

## 10. Options Controlling How Option Files Are Read

Certain special options determine which files MySQL reads. They generally must be placed at the beginning of the argument list, before regular options:

| Option | Effect |
| --- | --- |
| `--no-defaults` | Do not read any default option files |
| `--defaults-file=path` | Read only the specified option file instead of the default file set |
| `--defaults-extra-file=path` | Read the specified file in addition to default files according to program rules |
| `--defaults-group-suffix=suffix` | Also read groups with the specified suffix |
| `--print-defaults` | Print the options the program reads from option files and exit |

Example running the client with a custom configuration file:

```bash
mysql --defaults-file=/opt/app/mysql-client.cnf -u app_reader -p
```

Example bypassing default configuration for testing:

```bash
mysql --no-defaults -h 127.0.0.1 -P 3306 -u test_user -p
```

Place `--defaults-...` options before other options so the program applies them as expected. They are directives for the option parser, not settings that can be modified via `SET GLOBAL`.

## 11. Distinguishing defaults-file and defaults-extra-file

`--defaults-file` instructs the program to read the specified file instead of the default option files. This is how you isolate configuration for a specific instance or command.

`--defaults-extra-file` adds a file to the default option file reading process. It is suitable when you want to keep common system configuration and add specific options for a single run or application.

Example:

```bash
# Use only the specified file
mysqld --defaults-file=/etc/mysql/instance-a.cnf

# Read default configuration and add a custom file
mysql --defaults-extra-file=/opt/app/client-extra.cnf -u app_reader -p
```

Do not treat these two options as interchangeable. When investigating overridden configuration, verify the actual process command line and the list of files the program reads.

## 12. Group Suffixes for Multiple Configurations in the Same File

`--defaults-group-suffix` allows a program to read additional groups with a suffix. Example:

```ini
[client]
host=localhost
port=3306

[client_reporting]
host=report-db.internal.example
port=3307
```

Run:

```bash
mysql --defaults-group-suffix=_reporting -u report_user -p
```

The client reads the regular groups it supports and also reads the correspondingly suffixed groups, such as `[client_reporting]` and `[mysql_reporting]` if applicable. This feature is useful when the same binary needs to connect to multiple environments or instances without creating multiple separate files.

Do not place secrets in shared group suffixes or share files more broadly than necessary. Also verify the exact groups the program reads before expecting an option to take effect.

## 13. Printing Parsed Options with --print-defaults

`--print-defaults` displays the options a program retrieves from option files:

```bash
mysqld --print-defaults
mysql --print-defaults
```

This command is useful for discovering which files/groups are read and which options appear in the parser output. It does not prove that the running server successfully applied every value, nor does it reflect runtime changes made after server startup.

The output may contain sensitive information if the option file stores credentials or tokens. Do not paste the raw output into tickets, chats, or public logs; redact secrets before sharing.

## 14. Overall Precedence Order in MySQL 8.0

For system variables, you must consider option files, the command line, and persisted settings. A practical rule of thumb for MySQL 8.0 startup configuration is:

1. Compiled-in program defaults form the lowest baseline.
2. Option files supply configuration values.
3. Persisted system variable settings in `mysqld-auto.cnf` are loaded after option files and can override file values.
4. Command-line options take higher precedence than persisted settings.
5. After the server is running, valid runtime changes can alter current values depending on variable scope and user privileges.

The actual order also depends on the option type, version, and how the service is started. Specifically, `--no-defaults`, `--defaults-file`, and `--defaults-extra-file` alter the file-reading process itself. Check `VARIABLE_SOURCE` and runtime values rather than inferring solely from files.

## 15. How Do System Variables Differ from Startup Options?

Startup options are parameters a program accepts at startup. Many startup options correspond to system variables—for example, `--max-connections` controls the `max_connections` system variable.

Some options only control the program or the option parser and have no corresponding system variable. Therefore, you cannot find every option using `SHOW VARIABLES`.

System variables can have:

- **Global scope:** applies at the server level; can affect new sessions.
- **Session scope:** applies to the current connection/session.
- **Dynamic:** can be changed while the server is running.
- **Static:** requires changing startup configuration and restarting the server.

Check the scope and mutability in the documentation for each variable. `SET GLOBAL` does not mean every existing connection immediately receives the new session value; session variables may retain their own values.

## 16. Runtime Changes with SET GLOBAL

Example changing the maximum number of connections while the server is running:

```sql
SET GLOBAL max_connections = 300;

SHOW GLOBAL VARIABLES LIKE 'max_connections';
```

`SET GLOBAL` only changes the value in server memory. Upon restart, the value may revert to the startup configuration source if not persisted.

A session variable can be set independently for a connection:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
SELECT @@SESSION.sql_mode;
```

Do not confuse `SET SESSION` with a server-wide configuration change. Global changes generally require appropriate administrative privileges; MySQL 8.0 uses dynamic privileges such as `SYSTEM_VARIABLES_ADMIN` for many system variable management operations.

## 17. SET PERSIST and SET PERSIST_ONLY

MySQL 8.0 supports persisting certain global system variables across restarts:

```sql
SET PERSIST max_connections = 300;
```

`SET PERSIST` changes the runtime global value and writes the value to the persisted settings store so the server reloads it on subsequent startups.

`SET PERSIST_ONLY` saves the value for the next startup without changing the current runtime value. It is useful for variables that cannot be changed dynamically or when you want to stage a change to take effect after restart:

```sql
SET PERSIST_ONLY some_startup_variable = value;
```

The second example is only a syntax template; replace `some_startup_variable` and `value` with an actual variable and valid data type, and verify that the variable supports persistence in the running version.

Not every system variable can be persisted. The variable must have the appropriate scope/characteristics and must not belong to the group of variables disallowed from persistence. Check returned errors and variable documentation before incorporating into operational runbooks.

## 18. mysqld-auto.cnf and Managing Persisted Settings

Values saved via `SET PERSIST`/`SET PERSIST_ONLY` are written to the `mysqld-auto.cnf` file in the data directory. The server reads this file at startup if `persisted_globals_load` permits it.

Inspect persisted values:

```sql
SELECT *
FROM performance_schema.persisted_variables;
```

Remove a single persisted value:

```sql
RESET PERSIST max_connections;
```

Remove all persisted settings:

```sql
RESET PERSIST;
```

Do not edit `mysqld-auto.cnf` using a text editor or regular script while the server manages the file. Use `SET PERSIST`, `SET PERSIST_ONLY`, and `RESET PERSIST` to keep metadata consistent. If you need to disable loading persisted settings, check the `persisted_globals_load` variable and startup procedure for your version.

## 19. Identifying Value Sources with Performance Schema

On MySQL 8.0, `performance_schema.variables_info` helps investigate the source of global system variables:

```sql
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
    'slow_query_log'
);
```

The source and path columns help identify whether a value came from an option file, command line, persisted setting, or runtime operation depending on version and scenario. The table may contain `NULL` for certain fields when not applicable.

To view current values:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SELECT @@GLOBAL.max_connections;
```

Combining runtime values with configuration sources is a fast way to find out why a file says `250` while the server returns `400`.

## 20. Validating Configuration Before Restarting

Do not change production configuration and immediately restart without validating syntax and option names.

On MySQL 8.0.16 and later, you can use:

```bash
mysqld --validate-config
```

This command tells the server to check the configuration and exit; it does not replace test-starting in a staging environment. You can combine it with specifying a configuration file:

```bash
mysqld --defaults-file=/etc/mysql/my.cnf --validate-config
```

On Windows, enclose the `my.ini` path in quotes if the path contains spaces:

```powershell
mysqld.exe --defaults-file="C:\ProgramData\MySQL\MySQL Server 8.4\my.ini" --validate-config
```

If the server runs as a Windows service, check both the service configuration and the startup arguments passed to `mysqld.exe` by the service; they may provide options that override the file.

For versions that do not support `--validate-config`, use `mysqld --verbose --help` to verify recognized options/groups and test changes in a matching environment before deployment.

## 21. Example of a Grouped Server and Client Configuration

An illustrative file:

```ini
[mysqld]
port=3306
max_connections=250
innodb_buffer_pool_size=2G
slow_query_log=ON
long_query_time=1
character-set-server=utf8mb4
collation-server=utf8mb4_0900_ai_ci

[client]
port=3306
default-character-set=utf8mb4

[mysql]
prompt=\\u@\\h [\\d]> 
```

The server reads the server configuration group; the `mysql` command-line client reads the client group and its own group. If you put `max_connections` in `[client]`, the client will not pass it as a server configuration. If you put `default-character-set` in `[mysqld]`, it does not mean every client will automatically use that character set.

## 22. Example of Tracing an Overridden Value

Suppose `my.cnf` contains:

```ini
[mysqld]
max_connections=250
```

Yet runtime returns `400`:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
```

Investigate in order:

1. Check the process command line for `--max-connections=400`.
2. Run `mysqld --verbose --help` to determine which files and groups are read.
3. Use `mysqld --print-defaults` to see what options the parser extracts from files.
4. On MySQL 8.0, query `performance_schema.variables_info` to check the value source.
5. Check `performance_schema.persisted_variables` for a persisted value of `400`.
6. Check whether any post-startup `SET GLOBAL` operation or automation modified the value.

Do not edit the first file you find and restart repeatedly. Identify the winning source first, then update the right source and remove redundant settings that are no longer needed.

## 23. Security and Option File Management

Option files can contain usernames, passwords, TLS paths, or connection details. Some client tools can read credentials from option files; therefore:

- Grant file read permissions only to required OS accounts.
- Do not commit passwords or tokens into shared configuration repositories.
- Use a secrets manager or appropriate credential mechanism for production environments.
- Do not share raw `--print-defaults` output if it contains sensitive information.
- Do not place passwords on the command line, as they can be exposed via process listings, shell history, or monitoring systems.
- Separate client and server configurations using clear groups.
- Manage changes through version control, review, and rollout procedures.

An option file is not a secret encryption mechanism. If a file contains credentials, protect it using filesystem permissions and secret management practices.

## 24. Configuration Change Rollout Procedure

A safe operational procedure:

1. Define the objective, variable/option, and running MySQL version.
2. Identify the current source: option file, command line, persisted setting, or runtime.
3. Confirm whether the variable is dynamic or requires a restart; check scope and valid range.
4. Edit the right file/group or use `SET PERSIST` if that is the chosen mechanism.
5. Review the diff, file permissions, and any sensitive values.
6. Validate using `mysqld --validate-config` if supported by the version.
7. Test in staging or a canary instance with similar data/workload.
8. Deploy the change; if a restart is required, follow a controlled restart procedure and verify replication/cluster health.
9. Re-query `SHOW GLOBAL VARIABLES` and `variables_info` to confirm both value and source.
10. Monitor error logs, connections, latency, memory, and related metrics.
11. Document the effective configuration, reason for change, and rollback plan.

Do not change multiple unrelated parameters in the same rollout without a way to attribute issues if an incident occurs.

## 25. Common Errors and Misconceptions

| Misconception / Error | Reality | Resolution |
| --- | --- | --- |
| There is only one `my.cnf` file | MySQL may read multiple files in order | Use `--verbose --help` to list them |
| Every program reads every group | Each program reads applicable groups | Identify the group by binary |
| Placing an option anywhere in the file works | An option only belongs to the current group | Place it in `[mysqld]`, `[client]`, or the proper group |
| Editing the option file always wins | Command-line and persisted settings can override it | Check the runtime source |
| `--defaults-file` is the same as `--defaults-extra-file` | One replaces the default file set; the other adds a file | Choose the right one for your goal |
| `--no-defaults` disables all configuration sources | It ignores default option files, while command-line/runtime still apply | Distinguish the sources |
| `SET GLOBAL` survives restarts | Typically only changes runtime state | Use an option file or `SET PERSIST` if appropriate |
| All variables are dynamic | Some variables require a restart | Check variable metadata/documentation |
| `--print-defaults` guarantees the runtime value | It only prints options from files | Check `SHOW GLOBAL VARIABLES` and `variables_info` |
| `mysqld-auto.cnf` should be edited directly | It is a server-managed file | Use `SET PERSIST`/`RESET PERSIST` |
| `mysqld --validate-config` exists in all versions | Version-dependent; available since MySQL 8.0.16 | Check the version first |
| Option names don't care about client vs. server | The group determines which program receives the option | Group properly and verify with help output |

## 26. Hands-On Exercises

1. Run `mysqld --verbose --help` and record the option files and groups the server reads on your lab machine.
2. Run `mysql --help` and compare the file/group list with the server.
3. Create a lab option file with `[mysqld]`, `[client]`, and `[mysql]`; explain which program reads each group.
4. Put the same option in two sequentially read files; verify which value takes effect.
5. Start a client with `--defaults-file` and compare with `--defaults-extra-file`.
6. Use `--no-defaults` to run a client independently of option files; confirm command-line arguments still take effect.
7. Use `--defaults-group-suffix` to select a separate group for a reporting environment.
8. Run `--print-defaults`; identify the limitations of the output and redact any credentials before saving.
9. Change a dynamic global variable using `SET GLOBAL`; restart the lab and observe whether the value reverts.
10. Use `SET PERSIST` on a supported variable; inspect `performance_schema.persisted_variables`.
11. Use `RESET PERSIST` to clear the saved value; verify the value source after restart.
12. Query `performance_schema.variables_info` to find the source of `max_connections`.
13. On MySQL 8.0.16+, run `mysqld --validate-config`; test an invalid option in a lab file and record the error.
14. Write a rollout/rollback procedure for a change to `innodb_buffer_pool_size` or `max_connections` in a staging environment.

## 27. Key Takeaways

MySQL reads options from multiple sources. Option files contain groups such as `[mysqld]`, `[server]`, `[client]`, and `[mysql]`; each binary reads only its applicable groups. Paths and file order depend on platform and version, so use `mysqld --verbose --help` or `mysql --help` to confirm. In option files, options generally omit the `--` prefix; `!include`/`!includedir` can be used to split configuration where supported.

The `--no-defaults`, `--defaults-file`, `--defaults-extra-file`, and `--defaults-group-suffix` options control how files are read and should be placed at the start of the command line. Later-read files generally override earlier-read files; command-line options override option files. On MySQL 8.0, persisted system variables in `mysqld-auto.cnf` are loaded after option files; command-line options take precedence over persisted settings. `SET GLOBAL` changes runtime; `SET PERSIST` changes runtime and persists across restarts; `SET PERSIST_ONLY` persists only for the next restart. Use `--print-defaults`, `SHOW GLOBAL VARIABLES`, `performance_schema.variables_info`, `performance_schema.persisted_variables`, and `mysqld --validate-config` (MySQL 8.0.16+) to investigate. Always identify the winning source, check the version, protect credentials, test in staging, and have a rollback plan before deploying.
