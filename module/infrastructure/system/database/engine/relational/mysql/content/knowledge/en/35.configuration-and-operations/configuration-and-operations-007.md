# Managing max_connections, Timeouts, and Session Resource Limits

MySQL needs to limit the number of concurrent connections and how long a session is permitted to wait in order to protect server resources. If max_connections is too low, applications may encounter error 1040 during traffic spikes. If set too high without accounting for memory, threads, file descriptors, and connection pools, the server can exhaust resources before reaching the connection threshold. Timeouts that are too short drop valid connections; timeouts that are too long can keep idle sessions, open transactions, or locks alive longer than necessary.

Connection management must therefore look simultaneously at the MySQL server, database accounts, application connection pools, and OS limits. Variables such as max_connections, max_user_connections, wait_timeout, connect_timeout, net_read_timeout, net_write_timeout, max_execution_time, and per-account resource limits address different scenarios; they cannot all be replaced by a single timeout number.

In the DATABASE_MYSQL module, the goal is to calculate a connection budget, select timeouts by wait type, enforce per-account resource limits, monitor utilization, and apply configuration changes in a controlled manner. Examples target MySQL 8.0; variables introduced in specific minor releases are noted explicitly to avoid misapplying them to older servers.

## Objectives

After this lesson, you will be able to:

- Distinguish total concurrent connections from per-account connection limits.
- Read and change max_connections at runtime and in persistent configuration.
- Calculate a connection budget from application instance counts, pool sizes, and background workloads.
- Understand the impact of each connection on threads, memory, file descriptors, and scheduling.
- Distinguish handshake timeout, idle timeout, network read/write timeout, and query timeout.
- Manage wait_timeout, interactive_timeout, connect_timeout, net_read_timeout, and net_write_timeout.
- Use per-account resource limits: MAX_USER_CONNECTIONS, MAX_CONNECTIONS_PER_HOUR, MAX_QUERIES_PER_HOUR, and MAX_UPDATES_PER_HOUR.
- Distinguish metadata lock wait timeouts, InnoDB row lock wait timeouts, and SELECT execution time limits.
- Identify buffers allocated per session or per operation.
- Monitor connection saturation using status variables, Performance Schema, and the process list.
- Configure connection pools to avoid connection storms and stale connections.
- Change configuration properly using SET GLOBAL, SET PERSIST, and option files.
- Handle Too many connections errors and design an administrative access path when the server nears connection exhaustion.

## 1. Map of Connection Limits and Timeouts

A MySQL connection passes through several stages. Each stage has its own type of limit:

| Stage | Common Limit | Meaning |
|---|---|---|
| Client opens connection and handshake | connect_timeout | Server waits for client to send connect packet/complete initial handshake |
| Total concurrent server sessions | max_connections | Ceiling on total concurrent client connections |
| Concurrent sessions per account | max_user_connections, MAX_USER_CONNECTIONS | Connection limit for a single account |
| Connected yet idle session | wait_timeout, interactive_timeout | Closes sessions with no activity within the configured period |
| Client sending data | net_read_timeout | Server waits for more data from the client |
| Server sending results | net_write_timeout | Server waits to write data to the client |
| SELECT statement executing | max_execution_time | Execution time limit for read-only SELECT, in milliseconds |
| Waiting for metadata lock | lock_wait_timeout | Wait time limit for metadata locks |
| Waiting for InnoDB row lock | innodb_lock_wait_timeout | Wait time limit for InnoDB row locks |

Do not use wait_timeout to solve a slow-running SELECT query. Do not use max_execution_time to fix a handshake error. Identify the exact stage where the session is waiting before changing a variable.

~~~mermaid
flowchart TD
    A[Application opens connection] --> B{Server has connection capacity?}
    B -- No --> X[Error 1040: Too many connections]
    B -- Yes --> C[Handshake]
    C --> D{Handshake completes in time?}
    D -- No --> Y[connect_timeout]
    D -- Yes --> E[Authenticated session]
    E --> F{Session idle?}
    F -- Yes --> G[wait_timeout / interactive_timeout]
    F -- No --> H[Client sends request]
    H --> I{Network transfer stalls?}
    I -- Client to server --> J[net_read_timeout]
    I -- Server to client --> K[net_write_timeout]
    I -- No --> L[Statement executes]
    L --> M{SELECT exceeds execution limit?}
    M -- Yes --> N[max_execution_time]
    M -- No --> O[Result returned]
~~~

## 2. max_connections: Server-Wide Limit

`max_connections` is the maximum number of concurrent client connections MySQL server accepts. It is a server-wide total limit applying across all applications and accounts connecting to that instance.

Once the threshold is reached, new connections typically receive:

~~~text
ERROR 1040 (HY000): Too many connections
~~~

`max_connections` is neither the application's concurrent request count nor the number of queries executing in parallel. A session may be running a query, waiting on a lock, or sleeping in `Sleep` state. All of them occupy a connection until disconnected.

### 2.1. Checking Current Values

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
~~~

- `max_connections`: current ceiling on concurrent connections.
- `Max_used_connections`: highest concurrent connection count observed since server startup or the relevant status reset.
- `Threads_connected`: number of currently connected sessions at sampling time.
- `Threads_running`: number of threads not in sleep state; not synonymous with CPU core count or CPU-bound queries.

Utilization at sampling time can be estimated as:

~~~text
connection_utilization = Threads_connected / max_connections
peak_utilization       = Max_used_connections / max_connections
~~~

Do not look at only a single snapshot. Record values over time, during peak hours, after deployments, and while batch jobs run.

### 2.2. Runtime Changes

If the variable supports dynamic changes and the account has system variable administration privileges:

~~~sql
SET GLOBAL max_connections = 300;

SHOW GLOBAL VARIABLES LIKE 'max_connections';
~~~

This change applies to the running server but does not automatically persist across restarts. The effective value may be capped by OS capabilities or build configuration; always read the variable back after changing it.

### 2.3. Saving Configuration Across Restarts

You can store it in the MySQL option file under `[mysqld]`:

~~~ini
[mysqld]
max_connections = 300
~~~

Or on MySQL 8.0, use SET PERSIST if the variable permits persistence:

~~~sql
SET PERSIST max_connections = 300;
~~~

SET PERSIST updates the global runtime variable and saves the value durably in MySQL-managed configuration. SET PERSIST_ONLY writes only the durable value to apply on server restart without changing the current runtime value.

~~~sql
SET PERSIST_ONLY max_connections = 350;
~~~

Do not edit `mysqld-auto.cnf` directly; use SET PERSIST/RESET PERSIST so MySQL manages persisted configuration. Before persisting, verify that the change fits the memory budget, OS limits, and deployment configuration.

### 2.4. Reserved Administrative Connection

MySQL reserves an extra connection for accounts with appropriate administrative privileges to help troubleshoot when normal connections have hit `max_connections`. Starting in MySQL 8.0.14, the `CONNECTION_ADMIN` privilege is used for this mechanism; older versions may use `SUPER` under the legacy mechanism.

Do not grant `CONNECTION_ADMIN` to ordinary application accounts. Maintain a dedicated operational account with strong authentication and least-privilege access. Some deployments may configure a dedicated administrative interface via `admin_address`/`admin_port`; this is an additional deployment option and does not replace privilege control.

## 3. Calculating a Connection Budget Before Raising Limits

Do not set `max_connections` by picking an arbitrary large number. Calculate potential open connections across all components:

~~~text
total_pool_connections =
    sum(application_instances * pool_max_size)
  + background_workers
  + scheduled_jobs
  + migration_and_reporting_clients
  + monitoring_and_admin_connections
~~~

Example:

| Component | Instances | Max Pool per Instance | Total |
|---|---:|---:|---:|
| API service | 6 | 20 | 120 |
| Worker service | 3 | 8 | 24 |
| Reporting | 1 | 10 | 10 |
| Scheduler | 1 | 4 | 4 |
| Migration/monitoring/admin | — | — | 12 |
| **Total potential open** | | | **170** |

If the server setting is 180, headroom is only 10 connections. A rolling deployment can run old and new instances concurrently, temporarily pushing pools above estimates. Count the maximum number of instances during deploys/autoscaling, not just steady-state instance counts.

### 3.1. Leaving Headroom

A realistic budget should leave room for:

- Administrative and monitoring connections.
- Migrations, backup clients, and emergency tasks.
- Temporary replica additions or autoscaling.
- Reconnection retries after network incidents.
- Short-lived client bursts above expectations.

Headroom is not a fixed percentage applicable to every system. Choose it based on peak usage, burst levels, and server capacity.

### 3.2. Connection Pooling

Applications typically use pools to reuse long-lived connections instead of opening/closing a TCP connection per request. Pools should configure:

- `maximumPoolSize`: maximum connections per instance.
- `minimumIdle`: idle connections maintained if supported by the pool.
- `connectionTimeout`: how long a request waits to borrow a connection from the pool; this is a pool timeout, distinct from MySQL's `connect_timeout`.
- `idleTimeout`: how long the pool retains an idle connection before retiring it.
- `maxLifetime` or `maxIdleTime`: connection lifetime so the pool proactively refreshes connections.
- Validation/keepalive: checking or keeping connections alive per driver/pool.

Align connection lifetime or keepalive with `wait_timeout`, proxies/load balancers, and network policies. The pool should proactively retire connections before the server or a middlebox closes them, and validate connections on checkout if supported by the driver.

### 3.3. Avoiding Connection Storms

When the database restarts or experiences network loss, hundreds of instances may reconnect simultaneously. Use exponential backoff with jitter, cap retries, and use pool startup ramp-up. Do not let every web request open a new connection on its own after error 1040; aggressive retries worsen overload.

## 4. What Resource Costs Does a Connection Have?

Each connection requires session state, a thread or worker execution context, a socket, metadata, and some memory. MySQL typically uses a one-thread-per-connection model in standard configurations. Large buffers are not necessarily allocated in full at connect time, but can be allocated when the session executes corresponding operations.

Common resource consumers:

| Resource | Impact |
|---|---|
| Thread/session state | Scales with connection count |
| Stack and baseline memory | Scales per thread/connection |
| Sort/join/read buffers | Can be allocated per session or per operation |
| Internal temporary tables | Increases with queries requiring materialization |
| File descriptors/sockets | Each connection needs a socket; server also opens files/tables |
| CPU scheduling | Too many runnable threads increase context switching and CPU contention |
| Transactions/locks | Sessions holding open transactions can hold row locks, metadata locks, or undo history longer |

Therefore, raising `max_connections` does not grant the server additional CPU or RAM. Before increasing it, measure peak memory, thread counts, query concurrency, file descriptors, and OS limits.

### 4.1. Do Not Add Every Buffer as If Always Allocated

Variables like `sort_buffer_size`, `join_buffer_size`, `read_buffer_size`, and `read_rnd_buffer_size` can incur costs per session or per operation. A query with multiple joins/sorts can require far more buffer memory than a session sitting in `Sleep`.

Do not multiply every buffer by `max_connections` and treat that as exact RAM usage. Yet do not assume buffers cannot stack either: many sessions running heavy queries simultaneously can create severe memory pressure. Use Performance Schema, process metrics, and real workloads to measure.

## 5. Per-Account Connection Limits

`max_connections` limits the entire server. `max_user_connections` limits concurrent connections for a single MySQL account. An account is identified by the user and host pair—for instance, `'api_user'@'10.%'` is distinct from `'api_user'@'localhost'`.

### 5.1. Global Per-Account Limit

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_user_connections';

SET GLOBAL max_user_connections = 30;
~~~

A value of 0 means no global per-account concurrency limit is enforced. When set to a positive number, this limit applies to each account unless overridden by the account's own resource options.

### 5.2. Custom Limits via ALTER USER

MySQL allows setting resource limits on individual accounts:

- `MAX_USER_CONNECTIONS`: maximum concurrent connections for the account.
- `MAX_CONNECTIONS_PER_HOUR`: maximum connections opened per hour.
- `MAX_QUERIES_PER_HOUR`: maximum queries per hour.
- `MAX_UPDATES_PER_HOUR`: maximum update statements per hour.

Example:

~~~sql
ALTER USER 'api_user'@'10.%'
    WITH
        MAX_USER_CONNECTIONS 20
        MAX_CONNECTIONS_PER_HOUR 5000
        MAX_QUERIES_PER_HOUR 20000
        MAX_UPDATES_PER_HOUR 5000;
~~~

The values above are examples only. Choose quotas based on workload and service capacity. Hourly limits are usage quotas over a one-hour window for the account, not smooth per-second rate limiting; applications still need dedicated rate limiting.

Inspect account details:

~~~sql
SHOW CREATE USER 'api_user'@'10.%';
SHOW GRANTS FOR 'api_user'@'10.%';
~~~

### 5.3. When to Use Each Limit

| Limit | What Does It Protect? | Target Example |
|---|---|---|
| `max_connections` | Server total | Prevent all clients combined from taking unlimited connections |
| `max_user_connections` | One account | Prevent one service from exhausting the pool |
| `MAX_CONNECTIONS_PER_HOUR` | Hourly connection creation rate | Catch clients reconnecting continuously |
| `MAX_QUERIES_PER_HOUR` | Hourly query count | Throttle quota-bound account workloads |
| `MAX_UPDATES_PER_HOUR` | Hourly update count | Restrict reporting/batch accounts per policy |

Account quotas do not replace data access privileges. An account with low quotas can still read or modify unauthorized data if granted overly broad SQL privileges.

## 6. connect_timeout: Handshake Timeout

`connect_timeout` is the number of seconds the server waits for a connect packet from the client before treating the handshake as invalid/incomplete. It governs the initial phase of a connection before the session is used normally.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'connect_timeout';

SET GLOBAL connect_timeout = 15;
~~~

If clients connect over high-latency networks or slow proxies, too low a value can cause connection errors. If set too high, half-open connections can hold resources longer. Tune based on observed latency and `Aborted_connects` logs.

`connect_timeout` is not the time an application waits to borrow a connection from a pool, nor is it the driver's TCP connect timeout. Drivers usually have separate settings for TCP/socket connect and handshake.

## 7. wait_timeout and interactive_timeout

`wait_timeout` limits the number of seconds the server waits for subsequent activity on a noninteractive connection before closing it. It is an idle session timeout, not a maximum query execution time.

`interactive_timeout` applies to interactive connections. When a connection is established with the client interactive flag, its initial session `wait_timeout` is copied from `interactive_timeout`; for noninteractive connections, it is copied from global `wait_timeout`. Once the session exists, you can inspect its actual session value.

### 7.1. Checking Global and Session Values

~~~sql
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';

SELECT
    @@GLOBAL.wait_timeout AS global_wait_timeout,
    @@SESSION.wait_timeout AS this_session_wait_timeout,
    @@GLOBAL.interactive_timeout AS global_interactive_timeout;
~~~

Do not assume every session uses the same timeout solely from the global value. Each session holds its own value and can modify it.

### 7.2. Changing Timeouts

~~~sql
SET GLOBAL wait_timeout = 900;
SET SESSION wait_timeout = 900;
~~~

SET GLOBAL changes the default for sessions created afterward; it does not automatically alter `@@SESSION.wait_timeout` on existing connections. SET SESSION changes only the current session.

To persist:

~~~sql
SET PERSIST wait_timeout = 900;
SET PERSIST interactive_timeout = 900;
~~~

Do not set the timeout shorter than valid idle periods in a connection pool. When the server closes a connection due to idle timeout, the pool may still believe the connection is alive until the next checkout. Pool configuration must detect and evict stale connections.

### 7.3. Idle Transactions Are More Dangerous Than Idle Sessions

A `Sleep` session may still hold an open transaction. Long-open transactions can hold row locks, retain metadata locks, or block purge from cleaning up old undo history. Monitor `trx_started`, transaction state, and transaction age rather than looking only at `Command = Sleep`.

Since MySQL 8.0.24, the variables `idle_transaction_timeout`, `idle_write_transaction_timeout`, and `idle_readonly_transaction_timeout` exist to close sessions idle inside transactions within their respective scopes. Use them only after verifying your version and understanding that terminating a session causes application errors requiring transaction rollback/retry at the application tier. A value of 0 disables the corresponding limit.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'idle%transaction%timeout';
~~~

Do not use these variables as a substitute for closing transactions properly in application code. They are a safeguard against forgotten transactions.

## 8. net_read_timeout and net_write_timeout

These two variables govern data transfer over a connection:

- `net_read_timeout`: seconds the server waits for additional data from the client before aborting a read.
- `net_write_timeout`: seconds the server waits to write a block of data to the client before aborting a write.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'net_read_timeout';
SHOW GLOBAL VARIABLES LIKE 'net_write_timeout';
~~~

Common scenarios:

- Client uploads a large payload or sends requests slowly: inspect `net_read_timeout`.
- Client receives a large result set over a slow or congested network: inspect `net_write_timeout`.
- Client loses network connectivity mid-transfer: check both server error logs and driver exceptions.

These are not idle timeouts. A session sending no statements is governed by `wait_timeout`; a session actively transferring data is governed by the appropriate network timeout.

Do not raise timeouts indefinitely to mask slow clients. Check bandwidth, payload size, result set size, proxy timeouts, and the client's ability to consume data.

## 9. max_execution_time: Limiting SELECT Execution Duration

`max_execution_time` sets an execution time limit in milliseconds for read-only SELECT statements. A value of 0 disables this limit.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_execution_time';

SET SESSION max_execution_time = 2000;
~~~

The session limit applies to eligible SELECTs executed in that session. You can set a per-statement limit using an optimizer hint:

~~~sql
SELECT /*+ MAX_EXECUTION_TIME(1500) */
       order_id, created_at
FROM orders
WHERE customer_id = 1001;
~~~

The hint value is in milliseconds. Hints are useful when only a specific reporting query needs its own limit without changing every query in the session.

### 9.1. Limits and Scope

- `max_execution_time` applies to read-only SELECT statements; it is not a general timeout for all DML.
- It does not bound the time spent waiting to acquire a connection from a pool.
- It does not replace `lock_wait_timeout` or `innodb_lock_wait_timeout`.
- It does not govern network transmission time for a result set after the server finishes processing the way `net_write_timeout` does.
- Certain SELECTs inside stored programs or special contexts may not be affected the same way as regular client queries; check documentation for your exact version and test in staging.

When a query is stopped by this limit, applications must handle the interrupted-statement error and never assume partial results are complete.

## 10. Lock Wait Timeouts Differ from Session Timeouts

A query may stall not because it is computing, but because it is waiting for a lock. Two lock timeouts must be distinguished:

| Variable | Lock Type | Unit | Purpose |
|---|---|---|---|
| `lock_wait_timeout` | Metadata lock (MDL) | Seconds | Limits wait time for metadata locks |
| `innodb_lock_wait_timeout` | InnoDB row lock | Seconds | Limits wait time for row locks |
| `max_execution_time` | Read-only SELECT execution | Milliseconds | Limits SELECT execution time |

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'lock_wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'innodb_lock_wait_timeout';
~~~

A DDL statement like `ALTER TABLE` can wait on a metadata lock because another transaction is using the table. Increasing `max_execution_time` does not solve MDL waits. Similarly, an `UPDATE` waiting on an InnoDB row lock is not governed by `wait_timeout` because the session is active and waiting on a lock, not idle.

When encountering lock wait errors:

1. Identify the lock type and the session holding the lock.
2. Inspect transaction age, SQL statement, and session state.
3. Check for long-running transactions or forgotten commits/rollbacks.
4. Consider shortening transactions and standardizing resource access order.
5. Only adjust timeouts after understanding impacts on correctness and retries.

## 11. Per-Session Buffers and Memory Limits

A connection does not have a single simple per-session memory limit covering all allocations. MySQL has multiple variables controlling buffers by operation type; some are allocated on demand and may be freed when the operation finishes or the session closes.

| Variable | Common Role | Approach |
|---|---|---|
| `sort_buffer_size` | Buffer for sort operations | Do not raise globally without measuring sort workloads |
| `join_buffer_size` | Buffer for joins without suitable indexes | Fix indexes/query shapes first; raise selectively |
| `read_buffer_size` | Sequential read buffer | Evaluate scan workload and memory impact |
| `read_rnd_buffer_size` | Post-sort ordered read buffer | Measure workloads with filesort/read-random |
| `tmp_table_size` | Size limit for internal in-memory temporary tables per version | Check TempTable behavior for your MySQL minor version |
| `max_heap_table_size` | Size limit for MEMORY tables and certain internal temp table paths per version | Do not confuse with limits for all JSON/documents |
| `max_allowed_packet` | Maximum permitted packet/message size | Size for actual payloads and protocol protection |

Some buffers can be allocated multiple times within a single query or across many concurrent queries. Never increase `join_buffer_size` or `sort_buffer_size` simply because one query is slow; check EXPLAIN, indexes, and rows examined first.

### 11.1. Internal Temporary Tables

Queries with GROUP BY, DISTINCT, UNION, ORDER BY, or materialization may require internal temporary tables. Depending on the MySQL version and data types, temporary tables may use TempTable or another engine, and may spill to disk when exceeding limits.

In MySQL 8.0.28+, `tmp_table_size` applies a limit per internal in-memory TempTable. `temptable_max_ram` controls the server-level RAM budget of the TempTable engine. These are two separate layers: a per-temp-table cap and a shared RAM budget. Check the actual variables before applying, as minor releases introduced behavior changes.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_ram';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_mmap';
~~~

Do not multiply `tmp_table_size` by the connection count and assume the server will consume exactly that much RAM; not every session creates an internal temp table simultaneously. Still, workloads with many concurrent materializing queries can cause memory or disk pressure.

### 11.2. max_allowed_packet Is Not a Session Memory Cap

`max_allowed_packet` limits the size of a single packet/message accepted by client or server, such as a large payload or large result column. It does not cap the total memory a session can consume.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
~~~

If you raise this variable, simultaneously control request body sizes, blob/document sizes, row counts, and transfer times. Do not rely on the packet limit as your sole protection policy.

## 12. Thread Cache, File Descriptors, and OS Limits

`thread_cache_size` controls how many threads the server keeps cached for reuse when new connections arrive. It can reduce thread creation overhead under high connection churn, though it does not limit concurrent connections.

`open_files_limit`, `table_open_cache`, and OS file descriptor limits affect how many files, tables, and sockets the server can manage. Increasing `max_connections` may require checking these limits.

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'thread_cache_size',
    'open_files_limit',
    'table_open_cache',
    'back_log'
);
~~~

`back_log` relates to the queue of connections waiting to be accepted at the server/OS layer; it does not replace `max_connections`. The OS may impose separate limits on backlog, file descriptors, processes/threads, and memory.

When increasing connections:

1. Check OS file descriptor and service manager limits.
2. Check the effective `open_files_limit` received by MySQL.
3. Check memory and thread count at peak load.
4. Check `table_open_cache` and table-opening workload.
5. Check connection churn and thread cache effectiveness.
6. Increase in steps and monitor after each change.

## 13. Observing Connection Utilization

### 13.1. Key Status Variables

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connection_errors_max_connections',
    'Aborted_connects',
    'Connections',
    'Threads_created',
    'Uptime'
);
~~~

| Status | How to Read |
|---|---|
| `Threads_connected` | Currently connected sessions |
| `Threads_running` | Threads not in sleeping state |
| `Max_used_connections` | Peak connection count since the relevant reset |
| `Connection_errors_max_connections` | Connections refused due to reaching `max_connections` |
| `Aborted_connects` | Connections that failed during connect/authentication |
| `Connections` | Total connection attempts received by server since the relevant reset |
| `Threads_created` | Number of server threads created |

Compare counter deltas over time rather than looking only at cumulative totals. For instance, `Connections` rising rapidly while `Threads_connected` stays low can indicate connection churn and ineffective pooling.

### 13.2. Inspecting Sessions and Transactions

~~~sql
SHOW FULL PROCESSLIST;
~~~

Look for sessions:

- Sleeping for a long time while still holding a transaction.
- Running the same query for too long.
- Waiting on metadata locks or row locks.
- Belonging to an account occupying most connections.
- Originating from unrecognized hosts or applications.

You can inspect `sys.processlist` or Performance Schema tables such as `performance_schema.threads` and `performance_schema.events_statements_current` if appropriate instruments are enabled. Do not enable all instruments in production without evaluating overhead.

### 13.3. Finding Accounts Holding Many Connections

~~~sql
SELECT
    USER,
    SUBSTRING_INDEX(HOST, ':', 1) AS client_host,
    COUNT(*) AS connection_count
FROM performance_schema.processlist
GROUP BY USER, SUBSTRING_INDEX(HOST, ':', 1)
ORDER BY connection_count DESC;
~~~

This query helps identify connection consumers by user/host. On MySQL 8.0.22+, prefer Performance Schema `processlist`; `INFORMATION_SCHEMA.PROCESSLIST` has been deprecated since that release. Appropriate privileges are required to see all sessions of other users. In proxied environments, the displayed host may be the proxy rather than the application instance.

### 13.4. Monitoring Query Digests

Performance Schema can aggregate statements by digest to identify queries generating load or running long. Combine:

- Execution count.
- Total time and average time.
- Rows examined / rows sent.
- Lock time and errors.
- Concurrent connections from the service generating the workload.

The goal is to find why connections are held open—such as queries missing indexes or transactions waiting on locks—rather than merely raising connection limits to accommodate a larger queue.

## 14. Handling Too Many Connections

When receiving error 1040, do not start by immediately raising `max_connections`. Gather evidence and free connections safely:

1. Check `Threads_connected`, `Max_used_connections`, and `Connection_errors_max_connections`.
2. Inspect `SHOW FULL PROCESSLIST` to find accounts/hosts holding connections.
3. Separate `Sleep` sessions, long-running queries, lock-waiting sessions, and idle transactions.
4. Check pool sizes across all application instances, including instances mid-rolling-deploy.
5. Check for connection leaks, retry storms, and applications failing to return connections to the pool.
6. Use an account with `CONNECTION_ADMIN` or the reserved administrative channel if needed.
7. Terminate sessions only after identifying the owner and transaction impact.
8. If raising `max_connections`, check memory/OS headroom first.
9. Tune pools, timeouts, or bottleneck queries.
10. Re-check counters after mitigation.

### 14.1. KILL QUERY and KILL CONNECTION

~~~sql
KILL QUERY 12345;
KILL CONNECTION 12345;
~~~

`KILL QUERY` requests stopping the current statement while keeping the session open. `KILL CONNECTION` closes the entire connection; any uncommitted transaction in that session is rolled back when the connection ends. Never kill a session solely because its state is `Sleep` without checking its transaction and owner.

### 14.2. Retrying After Error 1040

Applications should:

- Retry with backoff and jitter.
- Cap total retries and wait duration.
- Never open a new connection on every unbounded retry.
- Return controlled errors when the pool cannot acquire a connection.
- Emit metrics for pool active/idle/pending counts and checkout wait times.

If every request retries immediately, the server suffers a reconnect storm and error 1040 persists longer.

## 15. Controlled Configuration Changes

A configuration change should include a baseline, target, scope, rollback method, and verification metrics:

1. Record current global/session variables.
2. Determine whether the variable is dynamic and persistable.
3. Estimate impact across all sessions/instances.
4. Test in staging with comparable workload.
5. Apply runtime changes using SET GLOBAL/SET SESSION or SET PERSIST appropriately.
6. Verify values with SHOW VARIABLES.
7. Monitor connections, memory, threads, latency, and errors.
8. If targets are not met, roll back to the old value and clean up any persisted value.
9. Record the reason, timestamp, operator, and outcome.

### 15.1. Distinguishing Configuration Commands

| Command | Runtime Impact | After Restart |
|---|---|---|
| `SET GLOBAL var = value` | Changes global runtime | Lost unless another durable config exists |
| `SET SESSION var = value` | Changes current session | Does not apply to other sessions |
| `SET PERSIST var = value` | Changes global runtime | Saved to survive restarts |
| `SET PERSIST_ONLY var = value` | Does not change current runtime | Saved to apply on restart |
| Option file `[mysqld]` | Takes effect when server reads config | Effective after restart |

Not every variable is dynamic or persistable. Some variables can only be set at startup. Always check documentation for your exact version and `SYSTEM_VARIABLES_ADMIN` privileges (or legacy compatible admin privileges) before making changes.

### 15.2. Rolling Back a Persisted Value

If SET PERSIST was used, clean up the persisted setting during rollback so the next restart does not re-enable the unwanted value:

~~~sql
RESET PERSIST IF EXISTS max_connections;
~~~

Then set the runtime value or option file to the desired configuration. If the option file also sets the same variable, ensure there are no conflicting configuration sources.

## 16. Environment-Based Configuration Examples

There is no single optimal timeout suite for all workloads. An OLTP API, batch loader, and reporting service behave differently. The table below illustrates how to reason during design:

| Workload Group | Connections/Pool | Idle Timeout | Query Timeout | Notes |
|---|---|---|---|---|
| OLTP API | Small pool, total capped across instances | Matches pool connection retention cycle | Per-endpoint SELECT limit if suitable | Prefer short queries and short transactions |
| Worker queue | Pool sized to worker concurrency | Matches gaps between jobs | Per job SLA | Back off when database is overloaded |
| Reporting | Dedicated small pool | Do not hold unnecessary idle sessions | Explicit SELECT limit | Use replicas/warehouse for heavy workloads |
| Migration/admin | Limited connections, manually controlled | Per tool | Per operation | Maintain a reserved admin account |

Illustrative starting option-file configuration, to be tuned via capacity testing:

~~~ini
[mysqld]
max_connections = 300
max_user_connections = 40
wait_timeout = 900
interactive_timeout = 1800
connect_timeout = 15
net_read_timeout = 60
net_write_timeout = 60
max_execution_time = 3000
~~~

This is an illustrative example, not a recommendation to copy verbatim. Here `max_user_connections` caps each account; accounts with custom resource options may have separate limits. Timeouts must align with clients, proxies, query SLAs, and batch sizes.

## 17. Common Design Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Raising `max_connections` to cure all timeout errors | Increases memory/thread pressure without fixing root cause | Classify errors by handshake, idle, network, query, or lock |
| Setting large pool max sizes on every instance | Total pool exceeds server capacity | Sum pools across the entire fleet and rolling deployments |
| Setting `wait_timeout` shorter than pool idle cycle | Pool holds connections already closed by server | Configure pool recycle/keepalive and validation |
| Using `connect_timeout` to bound pool checkout | Wrong layer timeout; does not control pool queue | Use pool/driver-specific timeouts |
| Raising `net_read_timeout` to cure slow queries | Does not solve execution or lock waits | Check query plans and lock diagnostics |
| Using `max_execution_time` for `UPDATE` | Variable does not apply as assumed | Manage DML via transactions, lock timeouts, and app deadlines |
| Raising `join_buffer_size` globally | Concurrent queries can consume huge RAM | Fix indexes/queries first; tune selectively |
| Leaving accounts uncapped | One service exhausts all connections | Set `MAX_USER_CONNECTIONS` per account |
| Retrying 1040 immediately | Creates a connection storm | Exponential backoff with jitter |
| Killing `Sleep` sessions blindly | Can roll back transactions or break business logic | Check transaction age and owner first |
| Checking `SHOW PROCESSLIST` only once | Misses brief spikes or connection churn | Collect metrics over time |
| Persisting config yet forgetting rollback | Bad value returns after restart | Manage SET PERSIST and RESET PERSIST alongside change records |

## 18. Runbook for Investigating Connection Saturation

When connection utilization alerts fire:

**Step 1 — Confirm Utilization**

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Connection_errors_max_connections';
~~~

**Step 2 — Find Accounts and Hosts Holding Sessions**

~~~sql
SELECT USER, HOST, COUNT(*) AS sessions
FROM performance_schema.processlist
GROUP BY USER, HOST
ORDER BY sessions DESC;
~~~

**Step 3 — Classify Sessions**

~~~sql
SHOW FULL PROCESSLIST;
~~~

Record the number of `Sleep` sessions, running queries, lock-waiting sessions, and sessions belonging to key accounts.

**Step 4 — Cross-Check Application Pools**

Check active, idle, pending checkouts, timeouts, connection creation rates, and pool sizes across all instances. Reconcile against MySQL session counts by account/host.

**Step 5 — Free Capacity and Recover**

Prioritize fixing leaks, reducing pool bursts, pausing non-essential batches, or resolving bottleneck queries/transactions. Kill sessions only after assessing impact. If raising `max_connections` temporarily, check memory/OS headroom first and set a deadline to re-evaluate.

**Step 6 — Prevent Recurrence**

Add alerts for peak connections, `Connection_errors_max_connections`, pending pool requests, idle transaction age, and connection churn. Document pool budgets and account limits in deployment configuration.

## 19. Hands-On Exercises

Perform in a MySQL lab; do not modify production limits for exercises:

1. Read `max_connections`, `max_user_connections`, `Threads_connected`, `Threads_running`, and `Max_used_connections`.
2. Simulate multiple sessions and observe `Threads_connected` rising/falling.
3. Calculate a connection budget across three services with different instance counts and pool sizes.
4. Set `MAX_USER_CONNECTIONS` for a lab account; open connections until hitting the limit and observe the error.
5. Check `SHOW CREATE USER` to confirm account quotas.
6. Compare global `wait_timeout` with `@@SESSION.wait_timeout` in two sessions opened before and after changing global.
7. In the current session, run `SET SESSION wait_timeout`; confirm the other session is unchanged.
8. Create one interactive client and one noninteractive client; compare initial `wait_timeout` values from `interactive_timeout`/`wait_timeout`.
9. Read `connect_timeout`, `net_read_timeout`, and `net_write_timeout`; describe which phase each variable protects.
10. Use `max_execution_time` or an optimizer hint to bound a SELECT in the lab.
11. Compare `lock_wait_timeout`, `innodb_lock_wait_timeout`, and `max_execution_time` using three separate scenarios.
12. Observe a long-open transaction in `Sleep` state; inspect transaction age and why looking only at process command is insufficient.
13. Inspect session buffer variables and describe which operations trigger their allocation.
14. Monitor `Connection_errors_max_connections`, `Connections`, and `Threads_created` over a time window to detect connection churn.
15. Test SET GLOBAL and SET PERSIST on a dynamic variable in the lab; verify runtime and persisted values.
16. Use RESET PERSIST to remove a persisted override and verify configuration after a simulated/actual lab restart.
17. Write a runbook for handling error 1040 including measurement, classification, session release, and retry-storm prevention.
18. Design a pool budget for API, worker, reporting, and admin workloads, accounting for rolling deployments and headroom.

## 20. Principles to Remember

- `max_connections` is the server-wide concurrent connection ceiling; `max_user_connections` and `MAX_USER_CONNECTIONS` limit per account.
- Accounts are identified by user and host; the same username with two host patterns can be two distinct accounts.
- Raising `max_connections` increases potential consumption of threads, memory, sockets, and file descriptors; measure capacity first.
- Pool sizes must be summed across all instances, workers, schedulers, migrations, and monitoring.
- `connect_timeout` protects handshakes; `wait_timeout`/`interactive_timeout` govern idle sessions.
- `net_read_timeout` and `net_write_timeout` protect network data transfer, not query execution duration.
- `max_execution_time` limits read-only SELECT statements in milliseconds.
- `lock_wait_timeout` is for metadata locks; `innodb_lock_wait_timeout` is for InnoDB row locks.
- New global variables do not automatically update session variables on existing connections.
- SET GLOBAL is runtime-only; SET PERSIST saves configuration across restarts; SET SESSION affects only the current session.
- Per-session/per-operation buffers can stack when many heavy queries run concurrently.
- `thread_cache_size` is not a connection count limit.
- Monitor `Threads_connected`, `Threads_running`, `Max_used_connections`, and `Connection_errors_max_connections` over time.
- Never retry error 1040 infinitely; use backoff, jitter, and total retry caps.
- Inspect transactions before killing a `Sleep` session.
- Choose timeouts matching the exact wait stage and workload SLA rather than using one global timeout for every problem.
