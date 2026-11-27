# Checking Version, Storage Engines, and Key Configuration Variables

## Objectives

After this lesson, you will be able to:

- Identify the version and distribution of the connected MySQL server, and distinguish it from the client version.
- Inspect the storage engines supported by the server, the default engine, and the actual engine of each table.
- Read key configuration variables related to connections, memory, transactions, character sets, logging, and replication.
- Distinguish global vs. session configuration variables, configuration variables vs. status counters, and safely gather information before changing configuration.

## 1. Why Inspect the Environment Before Starting Work?

Two servers both running MySQL can differ in version, distribution, storage engines, connection limits, memory, SQL mode, and transaction settings. These differences directly affect supported syntax, how data is stored, data integrity, performance, and recoverability.

Before creating schemas, running migrations, investigating slow queries, or deploying an application, record the actual environment. Do not infer configuration from the hostname, sample config files, port `3306`, or the client program's version. The server processing the queries is the source of truth to inspect.

In this lesson, the commands are primarily read-only inspections. You can run them with the MySQL client, MariaDB client, or a compatible administrative tool, provided your account has privileges to view the corresponding information.

## 2. Identifying the Server Version and Distribution

### 2.1. Querying from a Connection Session

After logging in to the server, run:

```sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@version_compile_os AS operating_system,
    @@version_compile_machine AS architecture;
```

- `VERSION()` returns the version string advertised by the server. This string usually helps identify MySQL, MariaDB, or a compatible distribution.
- `@@version_comment` provides a description of the server distribution or package.
- `@@version_compile_os` and `@@version_compile_machine` describe the OS and architecture used to compile the server on builds supporting these variables.

You can inspect the version variable group individually:

```sql
SHOW GLOBAL VARIABLES LIKE 'version%';
```

For example, `VERSION()` may return a string containing `8.0.x` on MySQL or `10.x-MariaDB` on MariaDB. These are illustrative examples only; record the exact verbatim output from the environment being inspected. Cloud services and custom distributions may include additional details.

### 2.2. Distinguishing Client and Server Versions

In a terminal, the following command displays the client version installed on the machine running the command:

```bash
mysql --version

# If the MariaDB client is installed:
mariadb --version
```

The command above does **not** ask a remote server for its version. The MySQL client can connect to MariaDB or a MySQL-protocol-compatible system; therefore, the output of `mysql --version` does not prove that the server is also MySQL.

When documenting an application environment, record two pieces of information separately: the client/driver version and the server version retrieved from an SQL query. When reporting bugs, provide both along with the operating system, distribution, and deployment model (bare metal, VM, container, or cloud service).

## 3. Checking Supported Storage Engines

A storage engine is the component responsible for storing and retrieving table data. MySQL's architecture allows different tables to use different engines, depending on which engines are installed and supported.

Run:

```sql
SHOW ENGINES;
```

The output usually includes columns such as `Engine`, `Support`, `Comment`, `Transactions`, `XA`, and `Savepoints` (columns may vary by version). The `Support` column indicates the engine's support status:

| Common Value | Meaning |
|---|---|
| `DEFAULT` | The server's default engine |
| `YES` | Engine is available and supported |
| `NO` | Engine is not supported in the current server build |
| `DISABLED` | Engine is present in the build but currently disabled |

Not every server provides the same list of engines. InnoDB is the standard transactional engine and is typically the default on modern MySQL. MariaDB may provide additional engines such as Aria. MyISAM, MEMORY, CSV, ARCHIVE, or NDB appear and are usable depending on distribution, configuration, and version.

You can also query via metadata:

```sql
SELECT
    ENGINE,
    SUPPORT,
    TRANSACTIONS,
    XA,
    SAVEPOINTS
FROM information_schema.ENGINES
ORDER BY ENGINE;
```

If an engine does not appear or is not supported, do not assume you can create tables using that engine. Check the documentation for the exact server version and configuration.

## 4. Checking the Default Engine and Per-Table Engines

### 4.1. Default Engine

Read the engine configured as the default for new tables:

```sql
SHOW GLOBAL VARIABLES LIKE 'default_storage_engine';
```

Or:

```sql
SELECT @@GLOBAL.default_storage_engine;
```

The `default_storage_engine` variable affects new table creation when the `CREATE TABLE` statement omits `ENGINE`. It does **not automatically convert** existing tables. Therefore, the current default engine is not enough to conclude which engine the entire database uses.

### 4.2. Viewing the Actual Engine of Tables

To list tables in the currently selected database:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

`TABLE_ROWS` may be an estimate, especially with InnoDB; do not use it as an exact row count for data reconciliation. `DATA_LENGTH` and `INDEX_LENGTH` report sizes as reported by the engine and may be calculated differently across engines.

To view the complete definition of a table, including engine, charset, collation, columns, indexes, and constraints:

```sql
SHOW CREATE TABLE orders\G
```

`\G` is the MySQL client's vertical output modifier; if your tool does not support it, use `SHOW CREATE TABLE orders;`.

### 4.3. Why Care About the Engine?

| Engine | Key Characteristics | Design Notes |
|---|---|---|
| InnoDB | Supports transactions, row-level locking, foreign keys, and crash recovery | Suitable for most OLTP applications needing integrity and concurrent updates |
| MyISAM | Legacy engine, does not support transactions in the way InnoDB provides; uses table-level locking | Requires careful consideration regarding integrity, concurrent writes, and recovery |
| MEMORY | Stores table data in memory; table data is lost when the server stops while table structure remains defined | Suitable only for temporary data that can be regenerated; must account for memory limits |
| CSV | Stores data in CSV format | Useful for certain simple data exchanges; lacks full capabilities of a transactional engine |
| ARCHIVE | Optimized for compressed archival storage and engine-appropriate retrieval | Check update, index, and query limitations per version |
| Aria (MariaDB) | MariaDB-specific engine with its own modes and recovery characteristics | Do not assume it is a direct drop-in replacement for InnoDB in transactional workloads |

Never choose an engine based solely on its name or a single speed benchmark. Consider transactions, foreign keys, locking granularity, read/write workload, crash recovery, backups, and operational supportability.

## 5. How to Read Configuration Variables

### 5.1. Listing and Filtering Variables

View all global variables:

```sql
SHOW GLOBAL VARIABLES;
```

Filter by prefix:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb%';
SHOW GLOBAL VARIABLES LIKE 'character_set%';
SHOW GLOBAL VARIABLES LIKE 'collation%';
SHOW GLOBAL VARIABLES LIKE 'log_%';
```

Inspect a specific variable:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
```

Some variables can be read directly using the `@@` expression:

```sql
SELECT
    @@GLOBAL.port AS server_port,
    @@GLOBAL.max_connections AS max_connections,
    @@GLOBAL.default_storage_engine AS default_engine,
    @@SESSION.sql_mode AS session_sql_mode;
```

If a variable does not exist in the current version or distribution, the query may return an error. When writing inspection scripts for multiple systems, query variables by group or handle optional variables rather than assuming every server shares the exact same variable set.

### 5.2. Distinguishing GLOBAL and SESSION

A variable can have global scope, session scope, or both, depending on the variable and version:

- **GLOBAL** is the server-level value. For variables that also have session scope, the global value is typically used as the initial value for new connections.
- **SESSION** is the value within the current connection. A session-level change usually affects only the open session and does not automatically alter other connections.
- Some variables are read-only or have only one scope; you cannot assume every variable can be modified at both levels.

Example viewing the SQL mode of the server and the current session:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Applications using a connection pool must pay attention to session state. If a connection modifies `sql_mode`, `time_zone`, or isolation level, that state may persist when the connection is returned to the pool and reused by another request, depending on how the pool manages connection resets.

### 5.3. Configuration Variables Differ from Operational Status

`SHOW VARIABLES` returns the current configuration. `SHOW STATUS` returns server operational counters or runtime status. These two groups answer different questions.

```sql
SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Questions';
SHOW GLOBAL STATUS LIKE 'Slow_queries';
```

For example, `max_connections` is a configuration limit; `Threads_connected` reports the current number of connections at the moment of sampling. To evaluate whether the limit needs to be increased, monitor trends and peak levels rather than looking at a single status snapshot.

## 6. Key Variable Groups to Inspect

Variable names, defaults, and mutability may vary across MySQL, MariaDB, and versions. The commands below are a starting point for inspection, not an optimal configuration set for every server.

### 6.1. Server Identity and Connectivity

```sql
SHOW GLOBAL VARIABLES LIKE 'port';
SHOW GLOBAL VARIABLES LIKE 'bind_address';
SHOW GLOBAL VARIABLES LIKE 'socket';
SHOW GLOBAL VARIABLES LIKE 'datadir';
SHOW GLOBAL VARIABLES LIKE 'hostname';
SHOW GLOBAL VARIABLES LIKE 'server_id';
```

- `port`: TCP port the server listens on, typically `3306` if unchanged.
- `bind_address`: network address the server listens on; its value affects reachability from other machines.
- `socket`: socket path on systems supporting Unix sockets.
- `datadir`: the server's data directory.
- `hostname`: hostname advertised by the server.
- `server_id`: server identifier, meaningful in binary-log-based replication setups.

Do not publicly expose network details, internal paths, or infrastructure configuration in widely shared logs if they are sensitive organizational data.

### 6.2. Connections and Packet Limits

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW GLOBAL VARIABLES LIKE 'connect_timeout';
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';
```

- `max_connections` limits the number of simultaneous connections permitted by the server. Setting it too high can increase memory and OS resource pressure.
- `max_allowed_packet` limits the packet size that client/server can handle in relevant contexts; too low a value can cause errors with large payloads.
- `connect_timeout` relates to the timeout during connection establishment.
- `wait_timeout` and `interactive_timeout` control idle connection timeouts by session type.

When investigating a "too many connections" error, compare the limit against actual active connections, each application's pool size, leaked connections, and connection hold times. Simply raising `max_connections` without accounting for memory can starve the server of resources.

### 6.3. Memory and InnoDB

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_instances';
SHOW GLOBAL VARIABLES LIKE 'innodb_log_buffer_size';
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW GLOBAL VARIABLES LIKE 'innodb_file_per_table';
```

- `innodb_buffer_pool_size` is the size of InnoDB's buffer pool, used to cache data and indexes. It must be balanced against RAM, other processes, and connection counts.
- `innodb_buffer_pool_instances` exists and carries meaning depending on version; some versions have changed or removed this configuration approach.
- `innodb_log_buffer_size` controls InnoDB's log buffer.
- `innodb_flush_log_at_trx_commit` affects how InnoDB flushes logs on commit, thereby impacting durability and performance.
- `innodb_file_per_table` controls how InnoDB organizes tablespaces per table in versions supporting this variable.

Do not adjust variables related to flushing, logs, or the buffer pool solely based on a generic tuning blog post. Determine durability requirements, available RAM, write workload, and the documentation for your exact version before tuning.

### 6.4. Transactions and SQL Behavior

```sql
SHOW GLOBAL VARIABLES LIKE 'transaction_isolation';
SHOW GLOBAL VARIABLES LIKE 'tx_isolation';
SHOW GLOBAL VARIABLES LIKE 'autocommit';
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
```

Some versions use the variable name `transaction_isolation`, while older versions or other distributions may provide a compatibility name such as `tx_isolation`. Check which variable actually exists.

- Isolation level determines isolation between transactions and affects concurrent read phenomena.
- `autocommit` sets the default auto-commit mode for a session; applications can still manage transactions explicitly.
- `sql_mode` enables SQL validation rules and behaviors such as handling invalid values, `GROUP BY` semantics, or strict mode. Differences in SQL mode can cause the same statement to behave differently.

Check both global and session values when an error occurs only in the application. Connections from an admin client may have a different session state from connections created by a framework or connection pool.

### 6.5. Character Set, Collation, and Time Zone

```sql
SHOW GLOBAL VARIABLES LIKE 'character_set%';
SHOW GLOBAL VARIABLES LIKE 'collation%';
SHOW GLOBAL VARIABLES LIKE 'time_zone';
SHOW GLOBAL VARIABLES LIKE 'system_time_zone';
```

- `character_set_server` and `collation_server` are server-level defaults for objects or connections that do not specify otherwise.
- `character_set_client`, `character_set_connection`, and `character_set_results` govern how the client sends, the server processes, and the server returns data in a session.
- `time_zone` can be `SYSTEM` or a configured time zone; `system_time_zone` reflects the system time zone detected by the server.

Server defaults do not prove every table uses the same charset/collation. Inspect databases and tables using `information_schema.SCHEMATA`, `information_schema.TABLES`, and `SHOW CREATE TABLE` when investigating Vietnamese text issues, string comparisons, or data transfers. Applications should explicitly define time zones to avoid time skew across environments.

### 6.6. Logging and Slow Query Monitoring

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error';
SHOW GLOBAL VARIABLES LIKE 'general_log';
SHOW GLOBAL VARIABLES LIKE 'general_log_file';
SHOW GLOBAL VARIABLES LIKE 'slow_query_log';
SHOW GLOBAL VARIABLES LIKE 'slow_query_log_file';
SHOW GLOBAL VARIABLES LIKE 'long_query_time';
```

- The error log records server events and errors.
- The general query log can record all connections and statements, but leaving it enabled continuously can generate heavy I/O and large log volumes.
- The slow query log records queries meeting the configured slowness criteria, helping identify queries needing optimization.
- `long_query_time` is the duration threshold for logging slow queries.

When enabling logs for investigation, account for disk space, access permissions, retention lifecycle, and sensitive data that might appear inside SQL statements. Prefer controlled monitoring procedures and disable or rotate logs according to operational policy.

### 6.7. Binary Log and Replication

```sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW GLOBAL VARIABLES LIKE 'expire_logs_days';
SHOW GLOBAL VARIABLES LIKE 'read_only';
SHOW GLOBAL VARIABLES LIKE 'super_read_only';
```

These variables may differ in name or support level across versions and distributions:

- `log_bin` indicates whether binary logging is enabled.
- `binlog_format` describes the binary log event recording format in versions that support it.
- Log expiration variables control binary log retention duration; variable names changed across certain version generations.
- `read_only` and `super_read_only` govern write restrictions on the server, commonly used on replicas or during maintenance. Exceptions and privilege rules may vary by version.

Never manually delete binary logs from the data directory. Log purging must follow SQL mechanisms and replication/backup policies to avoid starving replicas of needed events or breaking point-in-time recovery.

## 7. A Repeatable Environment Inspection Workflow

When onboarding a new MySQL environment or preparing to investigate an incident, follow this sequence:

1. **Identify the server:** collect `VERSION()`, `@@version_comment`, operating system, and architecture if available.
2. **Identify connectivity:** record port, bind address, socket, and relevant connection limits.
3. **Inspect engines:** run `SHOW ENGINES`, check `default_storage_engine`, and then list the actual engines of critical tables.
4. **Inspect session behavior:** capture SQL mode, isolation level, autocommit, charset, collation, and time zone at both global and session levels as needed.
5. **Inspect resources:** record connection limits, packet limits, buffer pool, and memory variables appropriate for the version.
6. **Inspect operations:** check error log, slow query log, binary log, read-only status, and related status counters.
7. **Save results with context:** include sampling timestamp, endpoint/environment, client/driver version, and privileges of the inspection account.

A concise starter inspection query set can look like:

```sql
-- 1. Server version
SELECT VERSION() AS server_version,
       @@version_comment AS distribution;

-- 2. Supported engines
SHOW ENGINES;

-- 3. Default engine
SHOW GLOBAL VARIABLES LIKE 'default_storage_engine';

-- 4. Engines of tables in the current database
SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;

-- 5. Commonly cross-checked variables
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW GLOBAL VARIABLES LIKE 'character_set_server';
SHOW GLOBAL VARIABLES LIKE 'collation_server';
SHOW GLOBAL VARIABLES LIKE 'time_zone';

-- 6. Selected status counters at inspection time
SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Slow_queries';
```

This is an initial baseline check, not a comprehensive configuration audit. If a variable is unsupported, note that fact and consult the documentation for the server in use; never substitute a guessed value.

## 8. Interpreting Results and Avoiding False Conclusions

| Observation | Valid Conclusion | What Cannot Be Concluded Yet |
|---|---|---|
| `VERSION()` returns a MySQL version string | The server advertises that corresponding MySQL version | Does not reveal edition, all enabled features, or workload configuration |
| `SHOW ENGINES` marks InnoDB as `DEFAULT` | InnoDB is the default engine for new tables when no engine is specified | Does not prove all existing tables currently use InnoDB |
| `max_connections = 300` | The configured limit is 300 connections at that variable's scope | Does not prove the server has enough RAM or the app actually needs 300 connections |
| `Threads_connected = 120` | There were 120 connections at the moment status was read | Does not tell whether this is a peak or indicates a connection leak |
| `slow_query_log = ON` | Slow query logging is enabled according to that variable | Does not guarantee the log file has free space or has been analyzed |
| `read_only = ON` | The server has read-only mode enabled according to that variable | Cannot infer every write operation is blocked across all versions and privileges |

In particular, do not equate configuration values with actual runtime health. For example, a large buffer pool does not by itself prove good performance; you must examine workload, hit rate, I/O, and latency. Having the slow query log enabled does not mean every slow query is logged if other thresholds or filters apply.

## 9. Safety When Collecting and Changing Configuration

The `SHOW` and `SELECT` commands in this lesson are primarily for inspection. Modifying variables is a separate administrative operation that may require high privileges and affect all connected applications.

Before changing a variable, verify:

- Does the variable exist and is it supported in the exact version?
- Does the variable have GLOBAL scope, SESSION scope, or both; is it dynamic?
- Will the new value affect active connections, transactions, durability, or replication?
- Does the change persist only at runtime or is it saved across restarts? Configuration persistence mechanisms differ by version and distribution.
- Do you have a baseline, a maintenance window, a rollback plan, and post-change monitoring?

For example, `SET GLOBAL max_connections = 300;` can change the runtime value if the variable allows it and the account holds sufficient privileges. This statement should not be run as an ad-hoc experiment in production; persisting changes across restarts must follow the configuration mechanism supported by the specific server.

When sharing inspection results, redact passwords, tokens, connection strings containing credentials, and business data. Some variables may reveal hostnames, network addresses, directory paths, or internal filenames; share only with authorized personnel.

## 10. Conclusion

Checking the version tells you which server you are working against; checking `SHOW ENGINES` and table metadata shows storage capabilities and the active engines; checking configuration variables helps you understand connection limits, memory, transactions, character sets, logging, and replication.

Always read configuration alongside runtime status and actual table metadata. Record the exact version, GLOBAL/SESSION scope, and sampling timestamp to avoid flawed comparisons across environments. This is the foundational step before designing schemas, optimizing queries, or modifying MySQL configuration in operations.
