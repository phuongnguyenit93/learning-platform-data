# Thread/Table Cache, open_files_limit, and OS Limits

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and solving relational database operational issues. When operating MySQL, limits on threads, table caches, and file descriptors directly affect the ability to accept connections, open tables, and sustain concurrent load. A configuration may run fine in a test environment yet fail when connection counts, table counts, partitions, or open files increase.

This lesson focuses on three related yet non-interchangeable resource groups:

- **Thread cache** retains threads that previously served connections for reuse, reducing thread creation overhead when connections arrive and disconnect frequently.
- **Table cache** retains table instances and table definitions to reduce table-opening overhead, metadata reads, and contention when many sessions access tables.
- **open_files_limit** and OS limits determine how many file descriptors the `mysqld` process can use.

The operational goal is to measure bottleneck symptoms accurately, understand effective server and OS limits, make controlled changes, and then verify via status variables, logs, and representative load. Never raise every variable to its maximum: oversized caches can consume RAM and file descriptors, increasing pressure on the system.

## 1. Resource Landscape of mysqld

MySQL Server manages connections, SQL statements, table metadata, data files, redo/undo, binary logs, temporary files, sockets, and many other file types. These resources have distinct limits:

| Resource | Role | Related Configuration or Limit |
|---|---|---|
| Connection-serving thread | Executes session work | `thread_cache_size`, `max_connections`, `thread_handling` |
| Table instance cache | Keeps open tables for reuse | `table_open_cache`, `table_open_cache_instances` |
| Table definition cache | Keeps table definitions in memory | `table_definition_cache` |
| File descriptors | Opens table files, logs, sockets, and internal files | `open_files_limit`, OS process limits |
| Concurrent connections | Number of clients accepted by the server | `max_connections`, resource limits |
| Memory | Threads, table metadata, buffers, sessions, and caches | RAM, MySQL configuration, workload |

No single variable controls everything. For example:

- Increasing `thread_cache_size` does not increase `max_connections`.
- Increasing `table_open_cache` does not automatically raise the OS file descriptor limit.
- Increasing `open_files_limit` does not automatically increase `table_open_cache`.
- `table_definition_cache` is not `table_open_cache`.
- The thread cache does not limit the number of concurrently running threads.

When investigating, identify the exact resource layer that is constrained before changing configuration.

## 2. How Does the Thread Cache Work?

In the default one-thread-per-connection model, a client connection is served by one server-side thread. When the client disconnects, the thread can be placed in the thread cache for reuse by a new connection. If the cache is full or disabled, the thread is freed; subsequent new connections may cause the server to create new threads.

The thread cache helps reduce thread creation and teardown overhead when applications have high connection churn. It does not keep client connections alive and is not a connection pool.

### 2.1. Distinguishing Thread Cache from Connection Pool

| Mechanism | Where It Lives | What Problem Does It Solve? |
|---|---|---|
| Connection pool | Application or proxy | Reuses client connections, limits open connections to the server |
| Thread cache | MySQL server | Reuses server threads after sessions close |
| `max_connections` | MySQL server | Limits concurrent client connections |
| Thread pool plugin | Specialized thread scheduling mechanism if installed and supported | Multiplexes many sessions onto a pool of worker threads |

If the application already uses a pool with a steady connection count, new thread creation may be low. In that case, increasing `thread_cache_size` may yield little noticeable benefit. If the application continuously opens and closes connections, the thread cache is more helpful.

### 2.2. thread_cache_size

`thread_cache_size` is the maximum number of threads MySQL retains to serve new connections. A value of 0 disables the cache. This variable has GLOBAL scope and can be changed while the server is running.

Check configuration:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_cache_size';
SHOW GLOBAL VARIABLES LIKE 'max_connections';
~~~

Check activity:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Connections',
    'Threads_created',
    'Threads_cached',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections'
);
~~~

Meaning of the metrics:

- **Threads_cached:** number of threads currently in the cache ready for reuse.
- **Threads_created:** total number of threads MySQL has created to handle connections since server startup.
- **Threads_connected:** number of currently open connections.
- **Threads_running:** number of threads not sleeping, actively executing work or waiting to run.
- **Connections:** number of connection attempts to the server since server startup.
- **Max_used_connections:** highest concurrent connection count since server startup.

`Threads_created` is a cumulative counter, not the number of currently running threads. `Threads_cached` is a point-in-time count, not the total number of threads ever cached.

### 2.3. Evaluating Thread Cache Demand

Take two status samples separated by a period with representative load. Compare the growth of `Threads_created` against the growth of `Connections`:

~~~text
delta_threads_created = new_Threads_created - old_Threads_created
delta_connections     = new_Connections - old_Connections

thread_creation_ratio = delta_threads_created / delta_connections
~~~

A high ratio during periods with many new connections can indicate the server frequently creates new threads. A low ratio indicates threads are being reused or connections remain steady. This is a diagnostic signal, not a universal pass/fail threshold.

Do not evaluate the thread cache from a single snapshot. Review:

- The application's connection open/close rate.
- Current open connections and peak connections reached.
- CPU usage and latency when creating connections.
- Average session lifetime.
- Connection pool or proxy behavior.

### 2.4. Choosing thread_cache_size

Select a value based on connection churn and resource capacity. You can start with a small-to-moderate value, observe during peak hours, and increase incrementally if `Threads_created` continues rising quickly relative to `Connections` and thread creation represents a measurable cost.

Example runtime change:

~~~sql
SET GLOBAL thread_cache_size = 64;
~~~

The value 64 only illustrates syntax, not a universal recommendation for every server. To keep it across restarts, save it in managed configuration or use SET PERSIST on supported versions after checking your environment's configuration policy.

Do not mechanically set `thread_cache_size` equal to `max_connections`. The cache only holds idle threads; sizing it larger than needed does not automatically make queries faster.

## 3. Table Cache and Table Definition Cache

MySQL must open tables and load table definitions when processing queries. To avoid repeating this work, the server maintains caches:

- **table_open_cache:** maximum number of table instances that can remain open in the table cache.
- **table_definition_cache:** maximum number of table definitions cached.
- **table_open_cache_instances:** splits the table cache into multiple instances to reduce internal contention when many threads access the cache concurrently.

A table instance and a table definition are two distinct object types. One table may have multiple open instances concurrently depending on session and server activity. A definition describes the table structure, not an open data file.

### 3.1. table_open_cache

`table_open_cache` limits the number of cached table instances. When queries access many tables and the cache is insufficient, MySQL may have to close some instances and reopen them when needed. Repeated open/close cycles increase metadata I/O, syscalls, and processing overhead.

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'table_open_cache';
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_tables',
    'Opened_tables',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows'
);
~~~

Status variables:

- **Open_tables:** number of table instances currently open.
- **Opened_tables:** total number of times tables have been opened since server startup.
- **Table_open_cache_hits:** number of hits finding a table instance in the cache.
- **Table_open_cache_misses:** number of misses requiring an open operation.
- **Table_open_cache_overflows:** number of times the cache hit its limit and the server had to handle cache overflow.

The names and availability of certain status variables may depend on version. If a variable does not exist, inspect the status list for the exact running MySQL version.

### 3.2. Reading Table Cache Metrics

`Open_tables` remaining close to `table_open_cache` for extended periods can indicate cache pressure, though it is not conclusive proof of under-sizing. Some tables may simply be actively held by multiple threads and not yet closable.

`Opened_tables` rising rapidly over a short interval can show that the server is repeatedly opening tables. Compare deltas over time rather than looking at cumulative totals since startup without considering uptime.

`Table_open_cache_misses` and `Table_open_cache_overflows` rising steadily under load strengthen the hypothesis of an undersized cache. Also check:

- Actual number of tables and partitions accessed by the workload.
- Number of concurrent sessions opening many tables.
- Whether DDL, FLUSH TABLES, or deployment operations are invalidating the cache.
- Whether `open_files_limit` and file descriptor limits are sufficient for the desired table cache size.

### 3.3. table_definition_cache

`table_definition_cache` holds table definition metadata to reduce the cost of reading and parsing table structures. It does not hold open table files and does not replace `table_open_cache`.

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'table_definition_cache';
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_table_definitions',
    'Opened_table_definitions'
);
~~~

`Open_table_definitions` represents the number of table definitions currently cached; `Opened_table_definitions` is the counter of definitions opened since server startup.

If the system has many tables or partitions, `table_definition_cache` may need to be large enough to avoid frequent metadata reloads. However, setting it too high also consumes memory. Some versions auto-size or compute defaults based on configuration; inspect the effective value rather than assuming a fixed default.

### 3.4. table_open_cache_instances

`table_open_cache_instances` partitions the cache into multiple instances to reduce contention on cache structures when many threads open tables concurrently. It helps on workloads with high concurrency and frequent table opens.

This variable is a startup configuration on common MySQL versions; check documentation for your exact version before changing it. Increasing the number of instances does not increase total `table_open_cache` correspondingly; it changes how the cache is partitioned and synchronized.

Do not increase instance count merely because `Open_tables` is high. Look for signs of contention, high concurrency, and actual improvement after making the change.

### 3.5. Example Multi-Table Workload

An accounting application may concurrently query:

- `invoices`, `invoice_items`, `customers`, `tax_rates`;
- `payments`, `payment_methods`, `refunds`;
- `accounts`, `journal_entries`, `cost_centers`;
- many historical tables per tenant or per month.

Each query can open multiple tables. When many sessions run simultaneously, demand for table instances grows. If tables are partitioned, the number of objects to open and manage can also grow according to the design.

Do not estimate `table_open_cache` solely by counting tables in the schema. Consider concurrently accessed tables, session counts, partitions, dynamic queries, and workload patterns.

## 4. File Descriptors and open_files_limit

The operating system grants file descriptors to a process to access files, sockets, pipes, and other I/O objects. In Linux, each process has a limit on the number of open file descriptors. MySQL needs file descriptors for many purposes:

- Table data and index files.
- Log files, binary logs, relay logs, and redo/undo depending on configuration.
- Temporary files and internal files.
- Client connection sockets.
- Other files managed by storage engines and the server.

`open_files_limit` is the file descriptor limit MySQL Server can use based on configuration and the OS limit granted to the process. It is neither the maximum number of tables nor the maximum number of data files under a naive one-table-equals-one-file calculation.

### 4.1. Checking MySQL Limits

~~~sql
SHOW GLOBAL VARIABLES LIKE 'open_files_limit';
SHOW GLOBAL VARIABLES LIKE 'table_open_cache';
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_files',
    'Opened_files'
);
~~~

- **Open_files:** number of file descriptors MySQL currently has open at sampling time.
- **Opened_files:** total number of files MySQL has opened since server startup.
- **open_files_limit:** effective limit MySQL can use per configuration/OS.

`Open_files` is the current count; `Opened_files` is a cumulative counter. `Opened_files` rising does not automatically mean the server is running out of file descriptors. Compare `Open_files` against `open_files_limit` and track the rate of change.

### 4.2. MySQL Cannot Exceed Operating System Limits

MySQL can request an `open_files_limit` at startup. The effective value depends on the limit actually granted to the `mysqld` process. If the service manager, container runtime, or OS enforces a lower limit, MySQL cannot elevate itself above the granted permission.

A large `open_files_limit` line in `my.cnf` does not prove the process actually received that limit. Always verify the runtime value and startup logs.

### 4.3. Why Are Table Cache and File Descriptors Related?

Opening more table instances often requires more file descriptors. Therefore, increasing `table_open_cache` can increase file descriptor demand. MySQL also needs descriptors for connections and other files, so you cannot dedicate the entire `open_files_limit` to the table cache.

If `open_files_limit` is low, `table_open_cache` may not reach its desired size, or the server may emit warnings or errors when opening files. Raising `table_open_cache` without raising OS limits may fail to produce the expected effect.

### 4.4. Do Not Infer File Descriptor Count Solely from Table Count

An InnoDB table may involve file-per-table tablespaces, shared tablespaces, redo, undo, or other storage structures depending on configuration. A partitioned table can add metadata and file requirements. A client connection typically uses a socket descriptor. Binary logs and relay logs also use file descriptors.

Consequently, capacity modeling must be based on the specific workload and deployment. Never use a "one table equals one descriptor" formula for production sizing.

## 5. File Descriptor Limits on Linux and systemd

On Linux, a process's limit is typically represented by `RLIMIT_NOFILE`. The logged-in user's shell `ulimit` value is not necessarily the limit the MySQL service receives.

### 5.1. Checking Shell Limits

~~~bash
ulimit -n
ulimit -Hn
~~~

The first command shows the soft limit; the second shows the hard limit of the current shell. If MySQL is started by systemd, cron, a container runtime, or a supervisor, an operator's shell may not reflect the limits of the `mysqld` process.

### 5.2. Checking the systemd Service

The service name may be `mysqld` or `mysql` depending on the distribution. Identify the exact service name before running commands:

~~~bash
sudo systemctl show mysqld --property=LimitNOFILE
~~~

You can check the limits of the running process:

~~~bash
pidof mysqld
cat /proc/<PID>/limits
~~~

In the output, find the `Max open files` line. This is the actual process limit, offering more direct diagnostic value than a terminal's `ulimit`.

### 5.3. Setting LimitNOFILE with a systemd Drop-In

Once you have confirmed the service limit is lower than needed, you can create an override for the exact service:

~~~bash
sudo systemctl edit mysqld
~~~

Illustrative drop-in content:

~~~ini
[Service]
LimitNOFILE=65535
~~~

After saving:

~~~bash
sudo systemctl daemon-reload
sudo systemctl show mysqld --property=LimitNOFILE
~~~

The value 65535 is an illustrative example only. Choose a limit based on RAM, connections, table cache, log files, storage engine, and host capacity. Applying the updated limit to the process usually requires restarting the service during a maintenance window.

### 5.4. Post-Restart Verification

After the service restarts:

1. Check service status.
2. Check `Max open files` in `/proc/<PID>/limits`.
3. Check `open_files_limit` inside MySQL.
4. Read the error log to confirm the server received the requested limit or logged warnings.
5. Monitor `Open_files` under real load.

Do not assume `systemctl daemon-reload` automatically updates the limit of a running `mysqld` process. A new drop-in takes effect when the service is restarted.

## 6. Containers and Orchestrated Environments

If MySQL runs inside a container, descriptor limits must be provided by the container runtime or configuration. Host `ulimit` values do not automatically prove the container receives the same limit.

Docker example:

~~~bash
docker run --ulimit nofile=65535:65535 ...
~~~

Docker Compose example:

~~~yaml
services:
  mysql:
    image: mysql:8.4
    ulimits:
      nofile:
        soft: 65535
        hard: 65535
~~~

This is an illustrative configuration. In an existing environment, preserve your system's exact image, service name, secrets, volumes, and deployment policies. Do not replace an entire production container config just to adjust a single limit.

With Kubernetes, do not assume there is a single standard `ulimit` field in a Pod spec that applies uniformly across all runtimes. Inspect node configuration, container runtime, security policies, and the cluster management platform. Verify the limit from inside the container and from the `mysqld` process itself.

## 7. MySQL on Windows

On Windows, process limits and service execution differ from Linux. MySQL typically reads configuration from `my.ini` and is managed by the Windows Service Control Manager. Do not apply `ulimit` or `systemd` commands to Windows.

Diagnostic steps:

1. Identify the exact Windows service running `mysqld`.
2. Verify the `my.ini` file actually used by the service.
3. Check `open_files_limit` and cache variables in the `[mysqld]` group.
4. Read the error log after startup.
5. Check effective values using SHOW GLOBAL VARIABLES and SHOW GLOBAL STATUS.
6. If startup options must change, edit the config for the exact instance and restart the service during a maintenance window.

Do not treat an `open_files_limit` entry in `my.ini` as proof that Windows granted that exact handle count. The server's effective value and logs are the basis for confirmation.

## 8. Relationship Between max_connections, table_open_cache, and open_files_limit

These three variables are resource-coupled:

- `max_connections` determines the maximum accepted client connections.
- `table_open_cache` determines the size of the table instance cache.
- `open_files_limit` caps the file descriptors the server can use.

When `max_connections` rises, the server may need extra resources for sessions, sockets, threads, table handles, and auxiliary operations. When `table_open_cache` rises, the server may need extra descriptors to keep more table instances open. Therefore, these settings must be evaluated together.

MySQL may compute or adjust the requested `open_files_limit` at startup based on other configuration variables and OS capabilities. Calculation details vary by version and platform; do not rely on a single fixed formula across all releases.

### 8.1. Example of an Imbalanced Configuration

Suppose the configuration requests:

~~~ini
[mysqld]
max_connections=800
table_open_cache=12000
open_files_limit=4096
~~~

If the OS only grants the process a few thousand descriptors, the requested table cache size may be infeasible. The server may lower effective limits or log warnings. High connection counts also consume other resources beyond file descriptors.

Inspect actual values after startup:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'table_open_cache',
    'table_definition_cache',
    'table_open_cache_instances',
    'open_files_limit',
    'thread_cache_size'
);
~~~

If effective values differ from configured values, investigate startup logs and service/OS limits before raising cache sizes further.

### 8.2. max_connections Is Not an Optimization Target

Setting `max_connections` too high can increase reserved memory, thread/session overhead, and file descriptor demand. A properly bounded connection pool is generally far easier to control than hundreds or thousands of clients opening unbounded connections.

Measure `Max_used_connections`, `Threads_connected`, `Threads_running`, timeout rates, and application queues. Increase `max_connections` only when there is genuine concurrency demand and the server has sufficient CPU, RAM, descriptors, and processing capacity.

### 8.3. Distinguishing open_files_limit and innodb_open_files

`open_files_limit` is a server/process-level file descriptor limit. `innodb_open_files` is an InnoDB-specific setting governing how many InnoDB data files InnoDB can keep open in certain tablespace configurations.

The two variables are resource-related but not synonymous. Increasing `innodb_open_files` does not bypass the process's descriptor limit; increasing `open_files_limit` does not automatically pick an appropriate `innodb_open_files` value.

## 9. Collecting a Baseline with SQL

Before making changes, record current configuration and status. Take at least two snapshots separated by a representative workload interval.

### 9.1. Configuration Snapshot

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'thread_cache_size',
    'table_open_cache',
    'table_open_cache_instances',
    'table_definition_cache',
    'open_files_limit',
    'innodb_open_files'
);
~~~

Record values, timestamp, uptime, MySQL version, and configuration source if the environment uses multiple option files or SET PERSIST.

### 9.2. Thread and Connection Snapshot

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Connections',
    'Threads_created',
    'Threads_cached',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Aborted_connects'
);
~~~

Read counters at the same point in time. If interval analysis is needed, store snapshots in a monitoring system or record results outside the database.

### 9.3. Table Cache and File Snapshot

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_tables',
    'Opened_tables',
    'Open_table_definitions',
    'Opened_table_definitions',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows',
    'Open_files',
    'Opened_files'
);
~~~

If your version does not provide a status variable from the list, omit that variable and use the remaining metrics. Never conclude a cache is undersized from a single metric alone.

### 9.4. Inspecting Files via Performance Schema

If Performance Schema is enabled and relevant instruments are active, you can view file instance counts by type:

~~~sql
SELECT
    EVENT_NAME,
    COUNT(*) AS file_instances,
    SUM(OPEN_COUNT) AS open_count
FROM performance_schema.file_instances
GROUP BY EVENT_NAME
ORDER BY open_count DESC;
~~~

View files with high cumulative I/O activity:

~~~sql
SELECT
    EVENT_NAME,
    FILE_NAME,
    COUNT_STAR,
    SUM_TIMER_WAIT
FROM performance_schema.file_summary_by_instance
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Performance Schema tables depend on enabled instruments and consumers. If results are empty, check collection configuration before concluding the server has no open files.

### 9.5. Checking Limits from the OS

On Linux, inspect the `mysqld` process directly:

~~~bash
pidof mysqld
cat /proc/<PID>/limits
ls /proc/<PID>/fd | wc -l
~~~

The first command finds the PID, the second displays soft/hard limits, and the third counts open descriptors in the process's `fd` directory. Execute with privileges sufficient to read process details.

You can check system-wide file handle usage:

~~~bash
cat /proc/sys/fs/file-nr
cat /proc/sys/fs/file-max
~~~

These are host-level metrics and do not replace `mysqld`'s own process limit. A host may still have plenty of file handles while the MySQL process hits its own `RLIMIT_NOFILE`.

## 10. Sizing and Tuning Procedure

Cache tuning is an iterative process of measuring, changing, and verifying. Adjust one variable group at a time so you know which change produced the impact.

### 10.1. Measuring Actual Load

Collect:

- Average and peak concurrent connections.
- New connections opened per second.
- Tables and partitions accessed within the same window.
- Sessions running queries that open multiple tables.
- Actual open file descriptors in the process.
- Available RAM and `mysqld` memory footprint.
- File-open errors, timeouts, connection refusals, and startup warnings.

Do not use total schema table count or configured `max_connections` as the sole proxy for load.

### 10.2. Tuning the Thread Cache

1. Take a snapshot of `Connections` and `Threads_created`.
2. Wait for an interval with representative load.
3. Take a second snapshot and calculate deltas.
4. Cross-check with connection pools, connection rate, and CPU.
5. If new threads are created frequently and that overhead is significant, increase `thread_cache_size` incrementally.
6. Repeat measurements after the change.

If connection pools hold long-lived connections, the thread cache may not be the bottleneck. Raising the cache in that scenario may simply retain extra idle threads without improving latency.

### 10.3. Tuning table_open_cache

1. Capture `Open_tables`, `Opened_tables`, `Table_open_cache_misses`, and `Table_open_cache_overflows`.
2. Measure deltas over a representative workload window.
3. Check `open_files_limit` and actual open descriptors.
4. If the cache is frequently insufficient and file descriptors have headroom, increase `table_open_cache` incrementally.
5. Monitor RAM, `Open_files`, misses/overflows, and latency.
6. If the effective value does not rise as requested, check startup logs and OS limits.

Do not raise `table_open_cache` beyond the server's file descriptor and memory capacity. A larger cache also does not guarantee faster queries if the bottleneck lies in data I/O, locks, or execution plans.

### 10.4. Tuning table_definition_cache

If the workload has very many tables or partitions, monitor `Open_table_definitions` and `Opened_table_definitions`. Consider raising the cache when metadata reloads occur frequently and sufficient memory is available.

Do not use cumulative `Opened_table_definitions` without computing deltas. DDL, restarts, and workload shifts affect how to interpret the numbers.

### 10.5. Tuning table_open_cache_instances

Only consider changing this when the workload has high concurrency and signs of contention on the table cache. This is a startup-configured variable in many MySQL releases; check dynamic scope in your running version.

Increasing the number of instances is not a fix for an undersized table cache. Distinguish contention from insufficient cache capacity.

### 10.6. Tuning open_files_limit

If `Open_files` approaches `open_files_limit` or startup logs report MySQL did not receive enough descriptors:

1. Check the actual process limit.
2. Check systemd, container runtime, or service manager settings.
3. Select a new target based on connections, table cache, logs, and internal files.
4. Raise the OS/service limit before or alongside changing MySQL configuration.
5. Configure `open_files_limit` at startup if needed.
6. Perform a planned restart and verify the effective value.

You cannot fix a running process's limit solely via `SET GLOBAL open_files_limit`. This is a startup configuration and must be handled at the proper OS/service layer.

## 11. Applying MySQL Configuration

### 11.1. Identifying Runtime vs. Startup Variables

Variables modifiable at runtime in common MySQL versions:

- `thread_cache_size`;
- `table_open_cache`;
- `table_definition_cache`;
- `max_connections`.

Variables such as `open_files_limit` and `table_open_cache_instances` typically require startup configuration. Mutability scope can vary by version; check documentation and variable metadata for your running release before planning.

### 11.2. Runtime Changes for Testing

Example:

~~~sql
SET GLOBAL thread_cache_size = 64;
SET GLOBAL table_open_cache = 4000;
SET GLOBAL table_definition_cache = 2000;
~~~

The numbers illustrate syntax only. Before running, determine values suited to your workload, version, RAM, and `open_files_limit`. GLOBAL changes typically affect new sessions or server-wide behavior depending on variable scope; existing sessions may retain some previously opened state.

### 11.3. Persisting Configuration Across Restarts

You can save options in the MySQL configuration file:

~~~ini
[mysqld]
thread_cache_size=64
table_open_cache=4000
table_definition_cache=2000
table_open_cache_instances=16
open_files_limit=65535
~~~

This is an illustrative example, not a generic production configuration. Values must be calculated for each specific server. On Linux the file is usually `my.cnf`; on Windows it is usually `my.ini`. Ensure you edit the exact file the service actually reads.

On supported versions, SET PERSIST can save certain dynamic variables across restarts:

~~~sql
SET PERSIST thread_cache_size = 64;
~~~

Do not use SET PERSIST for startup-only or read-only variables. Check configuration sources and config management policies to avoid conflicting configuration sources.

### 11.4. Safe Change Order

For a significant table cache increase, the sequence should be:

1. Estimate file descriptor and memory demand.
2. Check OS/service limits.
3. Raise OS/service limits if necessary.
4. Configure `open_files_limit` at startup.
5. Configure `table_open_cache` and related caches.
6. Restart within a maintenance window if startup-only variables changed.
7. Verify effective values and startup logs.
8. Run representative workloads and monitor status variables and resources.

Do not change multiple unrelated variables at once without a baseline. If a regression occurs, you must know which change caused it.

## 12. Reading Startup Logs and Detecting Capped Limits

At startup, MySQL may log messages about the maximum open files requested versus the maximum open files actually granted. If the actual value is lower than requested, investigate the OS or service manager.

Signs to investigate:

- MySQL fails to raise open files as requested.
- Runtime `open_files_limit` is lower than configured.
- Effective `table_open_cache` is lower than intended.
- The server logs warnings or errors when opening files.
- New connections are refused or queries cannot open tables.
- `Open_files` approaches the limit during peak hours.

Do not search only for a single fixed log string, as wording can change across versions. Read the full startup log around `mysqld` startup and cross-check with runtime variables.

## 13. Symptom-Based Diagnostics

| Symptom | Layer to Check First | Evidence to Gather |
|---|---|---|
| Many new threads during frequent connects | Thread cache / connection churn | Deltas of `Threads_created`, `Connections`, session lifetime |
| Too many connections | `max_connections` and pools | `Threads_connected`, `Max_used_connections`, application queues |
| Rapidly rising table cache misses/overflows | `table_open_cache` | `Open_tables`, delta `Opened_tables`, cache misses/overflows |
| Repeated table metadata reloads | `table_definition_cache` | `Open_table_definitions`, delta `Opened_table_definitions` |
| Too many open files | `open_files_limit` and OS | `Open_files`, `open_files_limit`, process limits, startup log |
| Table cache fails to reach requested size | OS descriptor limit or config | Runtime variables, startup log, service/container limits |
| RAM rises after enlarging caches | Cache sizing and concurrency | `mysqld` RSS, table instance count, session count |

### 13.1. Too Many Open Files

This message usually relates to descriptor limits at the process or system level. Check in order:

1. `Open_files` and `open_files_limit` inside MySQL.
2. `Max open files` in `/proc/<PID>/limits` on Linux.
3. systemd `LimitNOFILE` or container `ulimit` configuration.
4. Startup log to see how many descriptors the server requested and received.
5. Actual connections, table cache, log files, and workload.

Do not immediately shrink `table_open_cache` if the OS limit is low due to service configuration. Determine whether the load is reasonable before deciding whether to reduce the cache or raise the limit.

### 13.2. Too Many Connections

This is a connection limit, not a thread cache issue. Check `Max_used_connections`, `Threads_connected`, `max_connections`, pool sizes, and whether applications close connections properly.

Raising `max_connections` can mask a connection leak and put more pressure on the server. Fix pools, timeouts, and connection lifecycles before raising the limit if the root cause is applications holding connections unnecessarily.

### 13.3. Slow Table Opens or Cache Churn

If `Opened_tables` rises quickly alongside cache misses/overflows, check the number of tables/partitions accessed, session counts, and DDL activity. Then evaluate `table_open_cache` alongside `open_files_limit`.

If the cache is sufficient yet queries remain slow, shift focus to execution plans, I/O, locks, and metadata contention. Do not blame every slow query on the table cache.

## 14. Common Configuration Mistakes

1. **Raising every cache to high values:** can consume RAM and descriptors without guaranteeing higher throughput.
2. **Confusing thread cache with connection pool:** thread cache does not keep client connections alive.
3. **Confusing `thread_cache_size` with `max_connections`:** one reuses idle threads, the other limits concurrent connections.
4. **Confusing `table_open_cache` with `table_definition_cache`:** one manages table instances, the other manages definition metadata.
5. **Editing only `open_files_limit` in `my.cnf`:** the process may still be capped lower by systemd or containers.
6. **Checking only terminal `ulimit`:** `mysqld` may be launched by a service manager with different limits.
7. **Increasing `table_open_cache` while forgetting descriptors:** the server may fail to achieve the desired cache size.
8. **Reading cumulative counters as current counts:** `Opened_tables` and `Threads_created` must be analyzed using deltas.
9. **Increasing `max_connections` to cure a connection leak:** can worsen RAM, CPU, and descriptor pressure.
10. **Not reading startup logs:** runtime values can differ from values in configuration files.
11. **Running `FLUSH TABLES` to test the cache:** this can close/invalidate the table cache and skew normal workload measurements.
12. **Having no restart plan:** startup-only variables or OS limits require a restart to take effect.

## 15. Hands-On Exercise: Measuring Threads, Table Cache, and File Descriptors

Perform in a lab or staging environment. Never change OS limits or restart a production database solely to complete an exercise.

### 15.1. Recording Version and Configuration

~~~sql
SELECT VERSION() AS mysql_version;

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'thread_cache_size',
    'table_open_cache',
    'table_open_cache_instances',
    'table_definition_cache',
    'open_files_limit'
);
~~~

Save the output as a baseline.

### 15.2. Recording Initial Status

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Connections',
    'Threads_created',
    'Threads_cached',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Open_tables',
    'Opened_tables',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows',
    'Open_files',
    'Opened_files'
);
~~~

### 15.3. Creating a Lab Table Workload

~~~sql
CREATE DATABASE IF NOT EXISTS cache_lab;
USE cache_lab;

CREATE TABLE lab_a (
    id BIGINT NOT NULL PRIMARY KEY,
    value_text VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE lab_b (
    id BIGINT NOT NULL PRIMARY KEY,
    value_text VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

INSERT INTO lab_a (id, value_text)
VALUES (1, 'alpha'), (2, 'beta');

INSERT INTO lab_b (id, value_text)
VALUES (1, 'one'), (2, 'two');

SELECT a.id, a.value_text, b.value_text
FROM lab_a AS a
JOIN lab_b AS b
  ON b.id = a.id;
~~~

Repeat the query multiple times to generate table open and lookup activity. You can open several lab sessions to observe concurrency effects; do not spawn thousands of arbitrary connections on shared machines.

### 15.4. Comparing Status Over Time

Capture the status metrics from Section 15.2 again after a load interval. Compute deltas:

- `Threads_created` and `Connections` to evaluate thread creation.
- `Opened_tables`, `Table_open_cache_misses`, and `Table_open_cache_overflows` to evaluate cache churn.
- `Open_files` to evaluate currently open descriptors.

Do not compare raw counter totals between two servers with different uptimes without normalizing for time and workload.

### 15.5. Testing Thread Cache Changes in the Lab

If privileges and environment permit, record the old value and change it:

~~~sql
SET GLOBAL thread_cache_size = 32;
~~~

Create several short-lived connections in a controlled way, disconnect, and observe `Threads_cached` and `Threads_created`. Compare with your baseline. Restore the original value after the exercise.

### 15.6. Checking File Descriptors on Linux

On the lab host, find the `mysqld` PID and inspect:

~~~bash
pidof mysqld
cat /proc/<PID>/limits
ls /proc/<PID>/fd | wc -l
~~~

Cross-check `Max open files` with `open_files_limit` in MySQL. If the two values do not match, note which service manager or container runtime manages the process.

### 15.7. Cleaning Up Lab Tables

~~~sql
DROP DATABASE cache_lab;
~~~

Delete only the `cache_lab` database created by this exercise.

## 16. Runbook When Limits Need to Be Raised

When evidence shows the server is nearing file descriptor exhaustion or the table cache is undersized, follow this sequence:

1. **Confirm the symptoms:** collect status metrics, logs, and OS numbers from the same timeframe.
2. **Identify the process:** verify the exact PID, service name, container, and MySQL instance.
3. **Identify current limits:** check `open_files_limit`, process limits, and runtime limits.
4. **Estimate demand:** account for `max_connections`, table cache, logs, sockets, partitions, and internal files.
5. **Check RAM:** ensure the new table cache and session counts will not exceed host memory capacity.
6. **Plan the change:** record old/new values, rollback steps, and a restart window if required.
7. **Apply at the right layer:** OS/service/container before or alongside MySQL startup options.
8. **Perform a controlled restart:** verify service status and error logs.
9. **Verify effectiveness:** read back MySQL variables and OS process limits.
10. **Monitor post-change:** measure connection churn, cache misses/overflows, `Open_files`, RAM, and latency.
11. **Roll back on regression:** restore the old configuration per plan and confirm server stability.

## 17. Operational Checklist

### Before Making Changes

- [ ] Recorded MySQL version and uptime.
- [ ] Captured snapshots of GLOBAL variables and status metrics.
- [ ] Measured deltas of cumulative counters.
- [ ] Identified the exact process and service/container.
- [ ] Checked actual process file descriptor limits.
- [ ] Estimated RAM and descriptor requirements.
- [ ] Identified which variables are dynamic and which require a restart on the running version.
- [ ] Prepared a rollback plan and maintenance window.

### After Making Changes

- [ ] Service started successfully.
- [ ] Error log shows no unexpected limit warnings.
- [ ] Runtime `open_files_limit` and cache values match targets.
- [ ] OS process limit matches the plan.
- [ ] `Open_files` retains headroom under peak load.
- [ ] Table cache misses/overflows do not climb abnormally.
- [ ] `Threads_created` does not rise abnormally relative to `Connections`.
- [ ] RAM, CPU, and latency remain within target bounds.
- [ ] Configuration is saved in the canonical management source, not left as a temporary change only.

## 18. Principles to Remember

- `thread_cache_size` reuses server threads after sessions close; it is not a connection pool and does not cap concurrent connections.
- `max_connections`, `thread_cache_size`, and thread pools solve different problems.
- `table_open_cache` caches table instances; `table_definition_cache` caches table definitions.
- `table_open_cache_instances` reduces contention across cache instances; it does not increase total table cache capacity by itself.
- `open_files_limit` is the MySQL-side descriptor limit, but the effective value is governed by permissions and OS/service/container limits.
- `Open_files` is the current count; `Opened_files` is a cumulative counter.
- `Threads_cached` is the number of threads currently in the cache; `Threads_created` is the total number of threads created.
- `Opened_tables` and `Opened_table_definitions` must be read as deltas over time.
- Increasing `table_open_cache` raises descriptor demand; evaluate it alongside `open_files_limit` and `max_connections`.
- Shell `ulimit` does not prove a systemd service or container receives the same limit.
- On Linux, inspect process limits; on Windows, inspect the exact Windows service and `my.ini` file.
- Never use one fixed file descriptor formula across all versions, engines, and workloads.
- Increase caches only when status metrics and workload indicate a benefit; oversized caches consume RAM and handles.
- Startup-only variables must be configured in the proper source with a planned restart.
- Always verify runtime values, process limits, startup logs, and behavior under load after making changes.

Thread cache, table cache, and file descriptors are interconnected pieces of the same resource puzzle. Good operational design starts with data: measure connection churn, table cache misses, actual open file descriptors, and process limits; then adjust each layer according to workload, memory, and deployment platform. Only after effective values are verified post-restart and the workload remains stable is the new configuration complete.
