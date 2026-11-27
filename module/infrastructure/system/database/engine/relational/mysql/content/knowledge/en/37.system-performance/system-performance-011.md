# Thread Pool, Scheduling Mechanism, and Edition Requirements

A thread pool is a server-side mechanism that uses a pool of worker threads to process statements from many client connections. Instead of dedicating one execution thread permanently to each connection, MySQL Enterprise Thread Pool decouples connections from execution threads, routes statements into scheduling groups, and caps concurrency to match server resources. This mechanism can cut context-switching overhead and contention when a system handles a very large number of concurrent queries.

Edition eligibility is the first constraint to verify before designing around it: the MySQL Enterprise Thread Pool plugin is a commercial component of MySQL Enterprise Edition. MySQL Community Server uses the default one-thread-per-connection model and does not include this Enterprise plugin to enable simply by changing a system variable. This lesson focuses on the official MySQL plugin, its scheduling mechanics, and how to monitor and tune it.

## 1. What Problem Does the Thread Pool Solve?

In the default model, MySQL Server typically creates one worker thread per client connection. Under high connection and concurrent query counts, this model can increase:

- The number of threads and stack allocations to manage.
- Context-switching overhead across threads.
- Pressure on the operating system scheduler.
- CPU cache and memory contention.
- The number of concurrently running transactions, increasing contention on internal InnoDB resources.

A thread pool controls how many workers can execute statements simultaneously. Many connections can remain open, yet only a bounded set of workers are scheduled to run statements at a given moment. When a statement waits on I/O or locks, the thread pool can allow another worker in the same group to continue processing queued work.

The goal is throttling concurrency and improving throughput under high load. A thread pool does not make an inherently slow SQL query faster, does not replace indexes, does not eliminate lock contention, and does not speed up storage devices.

## 2. Edition Requirements and Support Scope

MySQL Enterprise Thread Pool is shipped as a server plugin in MySQL Enterprise Edition. This is a product requirement, not an option available on every MySQL installation.

| Environment | Thread Handling |
|---|---|
| MySQL Community Server | Default one-thread-per-connection model |
| MySQL Enterprise Edition with `thread_pool` plugin | Can use server-side thread pool model |
| MySQL Enterprise Edition where plugin is not loaded | Continues using current thread handling; plugin is inactive |
| MySQL-compatible products from other vendors | Must consult their own documentation; do not assume identical plugin or variable names as MySQL Enterprise |

Do not infer the edition solely from the version string returned by `VERSION()`. Check the installed package, product licensing, and whether the plugin library exists in the plugin directory.

You can check whether the plugin is active:

~~~sql
SELECT
    PLUGIN_NAME,
    PLUGIN_STATUS,
    PLUGIN_TYPE,
    PLUGIN_LIBRARY
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'thread_pool';
~~~

If no row is returned, the plugin is not registered or not present on the server. If a row appears but `PLUGIN_STATUS` is not `ACTIVE`, inspect the error log and plugin loading state.

Check thread handling:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_handling';
SHOW GLOBAL VARIABLES LIKE 'thread_pool%';
~~~

When the plugin loads successfully, `thread_handling` typically shows `loaded-dynamically`. The `thread_pool` variables appear only when the supporting plugin is loaded.

## 3. Thread Pool vs. Client Connection Pool

Both mechanisms share the word "pool", yet solve two different problems:

| Mechanism | Location | What It Manages | Goal |
|---|---|---|---|
| Client connection pool | Inside the application or connector | Reuses open connections | Cuts open/close connection overhead and caps connections from the app |
| MySQL Thread Pool | Inside MySQL Server | Schedules worker threads executing statements | Caps server-side concurrency and reduces overhead at high connection counts |

A connection pool lacks full visibility into backend execution capacity. A server thread pool does not replace client-side connection reuse. The two mechanisms are independent and can be used together.

For example, a service might keep 100 connections in a connection pool. The server still accepts those connections, while the thread pool allows only a subset of statements to execute concurrently across thread groups. Remaining statements wait their turn.

## 4. Architecture: Connections, Thread Groups, and Workers

The thread pool divides connections across multiple thread groups. Each group manages a set of connections and handles receiving statements, queuing them, and assigning workers.

Main components:

- Connection: a client session connected to MySQL.
- Thread group: a scheduling group managing a subset of connections.
- Listener thread: receives new statements from connections assigned to the group.
- Query worker thread: executes statements picked from a queue or dispatched directly.
- Background stall checker: monitors groups to detect stalled statements and prevent groups from staying blocked for long periods.
- Priority queues: high-priority and low-priority queues.

When a connection is established, the thread pool assigns it to a thread group via round-robin. Connections and execution threads no longer have a fixed one-to-one mapping. A worker can execute statements from different connections according to the scheduler.

## 5. How Connections Are Assigned to Thread Groups

Suppose `thread_pool_size` is set to 4. The thread pool has four groups with IDs 0 through 3. As new connections arrive, they are distributed in rotation:

~~~mermaid
flowchart TD
    C[Client connections] --> D[Thread pool dispatcher]
    D --> G0[Group 0]
    D --> G1[Group 1]
    D --> G2[Group 2]
    D --> G3[Group 3]
    G0 --> W0[Listener and query workers]
    G1 --> W1[Listener and query workers]
    G2 --> W2[Listener and query workers]
    G3 --> W3[Listener and query workers]
~~~

Round-robin distributes initial connections evenly across groups. It does not guarantee every group always has equal work: queries on connections assigned to one group can differ dramatically in duration and contention from another group.

`thread_pool_size` is the number of thread groups, not the maximum connection count and not a fixed worker count. A group can spawn additional workers when needed to handle stalled or blocked statements.

## 6. Listener Threads and the Path of a Statement

Each group has a listener thread to receive commands from connections assigned to that group. When a statement arrives, the group has two options:

1. If the group can execute immediately, the listener may begin executing the statement directly.
2. If the group is busy or the statement must wait, it is placed into the appropriate queue.

If the statement finishes quickly, the executing thread can return to the listener role. If the statement runs past the stall threshold, the thread pool can spawn or wake another worker so the group keeps accepting new statements.

Using the listener for direct execution when a group is idle avoids unnecessary worker creation under light loads. As load increases, the group expands workers within configured limits and scheduling rules.

## 7. Default Limit of One Short Running Statement per Group

The thread pool tries to keep at most one short statement executing at a time per group. This bounds concurrent statements and reduces context switching. However, a long or blocked statement should not hold a group idle indefinitely.

If a statement runs longer than the stall limit, the thread pool marks it as stalled. The group can then allow another statement to start, even while the earlier statement continues running.

If a thread blocks on a row lock, table lock, disk I/O, or another server-recognized wait, the thread pool can treat it as blocked and let another worker run. For waits not signaled through thread pool callbacks, the stall checker detects them via timeout.

Stalled does not mean the statement was cancelled, timed out, or rolled back. The older statement can keep running and consuming resources; the thread pool simply prevents it from blocking all other statements in the group from starting.

## 8. Two Priority Queues

The thread pool maintains a high-priority queue and a low-priority queue. When a worker picks work, it checks the high-priority queue first, then the low-priority queue.

Basic rules:

- The first statement of a transaction enters the low-priority queue.
- Subsequent statements in an active transaction may enter the high-priority queue.
- Statements for nontransactional engines or autocommit statements are treated as standalone transactions and typically enter the low-priority queue.
- `thread_pool_high_priority_connection` can be set to route all queued statements from a session into the high-priority queue.

Prioritizing follow-up statements inside an open transaction helps transactions finish, preventing newly arriving transactions from constantly cutting ahead and increasing contention. Still, if one session is given high priority indiscriminately, other sessions may wait longer.

## 9. Promoting Statements from Low Priority to High Priority

If a statement waits in the low-priority queue too long, the thread pool can promote it to the high-priority queue. `thread_pool_prio_kickup_timer` controls the wait duration before promotion.

In MySQL 8.4, the default is typically 1000 milliseconds. Each group caps promotions to at most one statement per 10 milliseconds, roughly 100 statements per second.

This mechanism prevents starvation for statements in the low-priority queue. If kickups happen too frequently, too many transactions may start before earlier transactions finish; with InnoDB, that can hurt performance through contention.

Check configuration:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_pool_prio_kickup_timer';
~~~

Do not lower the timer merely to prioritize one individual query. Inspect `PRIO_KICKUPS` over time alongside throughput and latency impacts on other workloads.

## 10. Stall Detection and `thread_pool_stall_limit`

`thread_pool_stall_limit` defines how long a statement may execute before being considered stalled. Its unit is roughly 10 milliseconds, not raw milliseconds.

In MySQL 8.4:

| Value | Corresponding Time |
|---:|---:|
| 4 | 40 ms |
| 6 (default) | 60 ms |
| 10 | 100 ms |
| 100 | 1 second |
| 600 (maximum) | 6 seconds |

A lower value lets the group open the next worker sooner, reducing the chance that a slow statement delays others. The trade-off is more statements marked stalled, leading to more threads and context switches.

A higher value reduces spawning extra workers under workloads with long queries, yet can force short queries to wait longer when a group runs a long statement.

This variable can be changed dynamically:

~~~sql
SET GLOBAL thread_pool_stall_limit = 10;
SELECT @@GLOBAL.thread_pool_stall_limit;
~~~

For example, setting 10 corresponds to roughly 100 ms. This is an illustrative value only; choose based on the statement latency distribution of your real workload and benchmark before applying.

## 11. Background Stall Checker

The thread pool runs a background thread that periodically inspects thread group state. If a group is occupied by a long-running statement or blocked without reporting wait callbacks, the stall checker marks the thread stalled and wakes or creates a worker to accept other statements.

This prevents all connections assigned to a group from getting stuck behind a query running for hours or a long-lived binary log dump thread.

The stall checker does not fix the root cause of long statements. If the workload has full table scans, lock waits, or slow I/O, you still must optimize queries, indexes, transactions, and storage separately.

## 12. Key Configuration Variables

Thread pool variables appear only when the plugin is loaded. Scopes and defaults can vary by version; the table below describes commonly used variables in MySQL 8.4.

| Variable | Meaning | Operational Notes |
|---|---|---|
| `thread_pool_size` | Number of thread groups | `GLOBAL`, non-dynamic; must be configured at startup |
| `thread_pool_stall_limit` | Threshold to mark a statement stalled | `GLOBAL`, dynamic; unit is 10 ms |
| `thread_pool_prio_kickup_timer` | Wait time before a low-priority statement is promoted | `GLOBAL`, dynamic; unit is milliseconds |
| `thread_pool_query_threads_per_group` | Maximum configured query workers per group | `GLOBAL`, dynamic |
| `thread_pool_high_priority_connection` | Routes a session's statements into the high-priority queue | `GLOBAL`/`SESSION`, dynamic |
| `thread_pool_max_active_query_threads` | Caps active query workers in a group | `GLOBAL`, dynamic; 0 uses default algorithm |
| `thread_pool_max_transactions_limit` | Transaction limit managed by the thread pool | `GLOBAL`; 0 usually disables this limit |
| `thread_pool_transaction_delay` | Delay before starting a new transaction | `GLOBAL`, dynamic |
| `thread_pool_algorithm` | Concurrency scheduling algorithm | `GLOBAL`; choice depends on workload |
| `thread_pool_max_unused_threads` | Caps idle unused sleeping threads | `GLOBAL`, dynamic |

Read actual values before changing anything:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_pool%';
~~~

Do not copy a configuration verbatim between two servers with different core counts, storage engines, workloads, or MySQL versions. Variables interact; changing one shifts concurrency and queue latency across the entire system.

## 13. `thread_pool_size`: Number of Thread Groups

`thread_pool_size` is the most important thread pool parameter because it sets the group count and influences how many statements can start executing concurrently.

In MySQL 8.4, the default is 16 with a typical range of 1 to 512. This variable is non-dynamic; changing it requires a server restart. In MySQL 9.7 documentation, the default is described as `MIN(VCPU/2, 16)`, so do not assume one fixed default across all release series.

Tuning starting guidelines in MySQL 8.4:

- For primarily InnoDB workloads, start testing near the number of physical CPU cores, up to 512.
- For primarily MyISAM workloads, use lower values, typically testing between 4 and 8.
- Measure throughput, p95/p99 latency, CPU, and queue behavior instead of looking only at connection counts.

These numbers are starting points for benchmarking, not guaranteed optimal formulas. Logical CPUs, container limits, NUMA, storage speed, and the short/long query mix all alter results.

## 14. `thread_pool_query_threads_per_group`

This variable controls how many query workers are permitted to be active in each group. The default is typically 1. Raising it can help when a group sees many long statements or long-waiting transactions that inflate response times for short queries.

Adding workers per group also increases concurrency and polling/scheduling overhead. If `thread_pool_size` is already large, raising query threads per group can allow too many simultaneous statements and increase contention.

MySQL 8.4 documentation suggests benchmarking with a value of 2 for this variable as a starting point, then measuring against the workload. Do not adopt that value without checking CPU, lock waits, and latency.

## 15. Throttling Transaction Count

Some InnoDB workloads lose throughput when too many transactions start simultaneously. The thread pool can throttle transactions using variables such as:

- `thread_pool_max_transactions_limit`: caps the number of transactions the thread pool permits.
- `thread_pool_transaction_delay`: delays starting new transactions.
- `thread_pool_longrun_trx_limit`: helper parameter for handling long-running transactions when transaction limits are active.

`thread_pool_max_transactions_limit` equal to 0 is the default with no transaction limit enforced. When set to a positive limit, a thread can remain bound to a transaction until it commits or rolls back. Hence, if transactions fail to finish, new connections may have to wait.

Transaction limiting is a concurrency control tool, not a fix for transactions left open too long. Before enabling it, measure transaction duration, connection counts, active transactions, and application commit/rollback behavior.

If limits block all normal connections, MySQL Enterprise Thread Pool supports privileged connections for accounts holding `TP_CONNECTION_ADMIN`. Privileged connections enter the Admin thread group and can adjust limits or resolve stuck transactions. Grant this privilege deliberately, never to routine application accounts.

## 16. Queue Priority by Transaction and Autocommit

Priority scheduling ties into transaction boundaries:

1. The first statement in a transaction enters the low-priority queue.
2. Once a transaction has started, subsequent statements in that transaction may enter the high-priority queue.
3. Under autocommit, each statement is its own transaction and typically enters low priority.
4. Statements on nontransactional engines are likewise treated as standalone statements.

This is why two identical queries may be queued differently depending on whether the session is inside a transaction. When designing applications, keep transactions short and commit/roll back explicitly to avoid holding resources while waiting on clients.

## 17. `thread_pool_high_priority_connection`

`thread_pool_high_priority_connection` lets you adjust queue routing for a session. When enabled, all queued statements from that session enter the high-priority queue.

Example:

~~~sql
SET SESSION thread_pool_high_priority_connection = 1;
SELECT @@SESSION.thread_pool_high_priority_connection;
~~~

The default is 0. When enabled, the session's statements can be processed ahead of statements in the low-priority queue. This can help an administrative connection or a latency-critical workload, yet broad use can starve ordinary sessions.

Never enable this variable for every connection in an application pool. If an application sets it at session scope, reset session state before reusing the connection.

## 18. Edition Requirements When Deploying the Plugin

Because the thread pool is a commercial MySQL Enterprise Edition plugin, deployment must begin by verifying the edition and plugin binary availability.

General steps:

1. Confirm the server is MySQL Enterprise Edition with valid licensing.
2. Check the plugin directory via `plugin_dir`.
3. Verify the `thread_pool` library exists in the plugin directory.
4. Configure `plugin-load-add` at startup.
5. Restart according to your maintenance plan.
6. Verify plugin status and monitoring tables.
7. Tune `thread_pool` variables only after confirming the plugin is `ACTIVE`.

Inspect the plugin directory:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'plugin_dir';
~~~

The base library name is `thread_pool`. The file extension depends on the OS: typically `.so` on Unix/Linux and `.dll` on Windows.

## 19. Loading the Plugin at Startup

Example configuration on Linux:

~~~ini
[mysqld]
plugin-load-add=thread_pool.so
~~~

Example on Windows:

~~~ini
[mysqld]
plugin-load-add=thread_pool.dll
~~~

Place the plugin file in the directory indicated by `plugin_dir` or configure `plugin_dir` at startup to match its location. Never copy a plugin binary from another MySQL build or OS without verifying ABI and version compatibility.

After restarting, verify:

~~~sql
SHOW PLUGINS;

SELECT PLUGIN_NAME, PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'thread_pool';

SHOW GLOBAL VARIABLES LIKE 'thread_handling';
~~~

The plugin must show status `ACTIVE`. If it fails to load, read the error log for causes such as missing library, wrong permissions, binary incompatibility, or an edition that does not support the plugin.

## 20. Monitoring with Performance Schema

In MySQL 8.4, thread pool monitoring tables live in Performance Schema and are loaded with the plugin:

| Table | Purpose |
|---|---|
| `performance_schema.tp_connections` | Information about connections managed by the thread pool |
| `performance_schema.tp_thread_group_state` | State snapshot for each thread group |
| `performance_schema.tp_thread_group_stats` | Activity counters by thread group |
| `performance_schema.tp_thread_state` | State and activity of each thread pool worker |

These tables exist only when the thread pool plugin is loaded and active. Data consists of snapshots or activity counters; they do not replace a time-series monitoring system. Older versions may use `INFORMATION_SCHEMA` tables for the thread pool; verify your version's documentation before writing monitoring tooling.

List available tables:

~~~sql
SHOW TABLES FROM performance_schema LIKE 'tp%';
~~~

## 21. Reading Statistics by Thread Group

`tp_thread_group_stats` provides one row per thread group. Useful columns:

- `TP_GROUP_ID`: ID of the group.
- `CONNECTIONS_STARTED` and `CONNECTIONS_CLOSED`: connections started/closed.
- `QUERIES_EXECUTED`: statements started executing; incremented when execution begins, not upon completion.
- `QUERIES_QUEUED`: statements placed in a queue; excludes statements executed immediately.
- `THREADS_STARTED`: threads created.
- `PRIO_KICKUPS`: statements promoted from the low queue to the high queue.
- `STALLED_QUERIES_EXECUTED`: statements marked stalled.
- `ROW_LOCK_WAITS`, `DISK_IO_WAITS`, `META_DATA_LOCK_WAITS`: wait counters by category.

Query:

~~~sql
SELECT
    TP_GROUP_ID,
    CONNECTIONS_STARTED,
    CONNECTIONS_CLOSED,
    QUERIES_EXECUTED,
    QUERIES_QUEUED,
    THREADS_STARTED,
    PRIO_KICKUPS,
    STALLED_QUERIES_EXECUTED,
    ROW_LOCK_WAITS,
    DISK_IO_WAITS,
    META_DATA_LOCK_WAITS
FROM performance_schema.tp_thread_group_stats
ORDER BY TP_GROUP_ID;
~~~

Rapidly rising `QUERIES_QUEUED` indicates groups frequently have to queue work. Rapidly rising `STALLED_QUERIES_EXECUTED` indicates many statements exceed the stall limit. Rising `ROW_LOCK_WAITS` or `DISK_IO_WAITS` points toward investigating locks or I/O rather than blindly adding workers.

## 22. Reading Worker States

`tp_thread_state` has one row per thread created by the thread pool. Notable columns:

- `TP_GROUP_ID` and `TP_THREAD_NUMBER` identify the group and thread.
- `TP_THREAD_TYPE` indicates the thread type such as query worker, listener worker, or timer worker.
- `STATE` describes whether the thread is polling, executing directly, handling queued work, sleeping as a consumer, or reserved.
- `WAIT_TYPE` indicates the wait category if the thread is blocked.
- `MARKED_STALLED` indicates whether the stall checker has flagged the thread as stalled.
- `EXEC_COUNT` and `ACCUMULATED_EXEC_TIME` report statement count and cumulative execution time.

Example:

~~~sql
SELECT
    TP_GROUP_ID,
    TP_THREAD_NUMBER,
    TP_THREAD_TYPE,
    STATE,
    WAIT_TYPE,
    MARKED_STALLED,
    EXEC_COUNT,
    ACCUMULATED_EXEC_TIME
FROM performance_schema.tp_thread_state
ORDER BY TP_GROUP_ID, TP_THREAD_NUMBER;
~~~

`WAIT_TYPE` can reveal whether a thread is waiting on row locks, metadata locks, disk I/O, group commit, or `fsync`. Combine these values with the process list, transactions, and lock metadata to locate root causes.

## 23. Comparing Metrics Over Time Intervals

Counters in `tp_thread_group_stats` are cumulative. A single snapshot shows totals since the plugin or server started, not the rate over the last minute.

Measurement procedure:

1. Capture a snapshot at time T1.
2. Wait a representative interval, such as 60 seconds during steady load.
3. Capture snapshot T2.
4. Compute `T2 - T1` deltas for `QUERIES_EXECUTED`, `QUERIES_QUEUED`, `STALLED_QUERIES_EXECUTED`, and wait counters.
5. Compare deltas against TPS, p95/p99 latency, CPU, I/O, and connection counts.

Example stalled statement ratio over totals:

~~~sql
SELECT
    SUM(STALLED_QUERIES_EXECUTED) /
    NULLIF(SUM(QUERIES_EXECUTED), 0) AS stalled_ratio
FROM performance_schema.tp_thread_group_stats;
~~~

This ratio uses cumulative counters since startup/statistics reset. When evaluating a specific time window, compute it from deltas between two snapshots to avoid blending long history with current load.

Do not use `TRUNCATE` to clear thread pool monitoring tables; these tables have operational restrictions and belong to the plugin.

## 24. Reading Status Variables Alongside Thread Pool Metrics

The thread pool should not be evaluated from a single table in isolation. Cross-check against status variables:

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_created';
SHOW GLOBAL STATUS LIKE 'Threads_cached';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
~~~

Meaning:

- `Threads_running`: threads actively executing statements at the moment of inspection.
- `Threads_connected`: currently open connections.
- `Threads_created`: threads created to handle connections per server statistics.
- `Threads_cached`: threads in the thread cache if thread caching is used.
- `Max_used_connections`: peak simultaneous connections since server startup or status reset.

With a thread pool, connections and query workers are no longer one-to-one. Therefore, do not treat `Threads_connected` as a direct proxy for executing workers.

## 25. Tuning by Workload

A practical tuning workflow:

1. Confirm edition, plugin status, and version.
2. Measure baselines before changing parameters: throughput, p95/p99 latency, CPU, I/O, `Threads_running`, queue, and wait counters.
3. Classify the workload: mostly short queries, mixed short/long, write-heavy transactions, or read-heavy.
4. Pick `thread_pool_size` based on physical cores and storage engine as a starting point.
5. Benchmark `thread_pool_query_threads_per_group` to balance group count against workers per group.
6. Tune `thread_pool_stall_limit` according to statement duration distribution.
7. Monitor `PRIO_KICKUPS` and evaluate `thread_pool_prio_kickup_timer` if queue aging happens too frequently.
8. Enable transaction limits/delays only after confirming transaction concurrency is the bottleneck.
9. Re-measure with the exact same query set and load level.
10. Document old settings, new settings, results, and rollback plan.

Do not change multiple variables at once. If throughput improves while p99 latency or lock waits degrade, evaluate the trade-off instead of looking only at TPS.

## 26. When Can a Thread Pool Help?

A thread pool is usually worth testing when:

- Client connection count is very high concurrently.
- `Threads_running` stays high with heavy context switching.
- The workload consists of many short statements where thread scheduling overhead is substantial.
- The server has many CPU cores yet performance degrades as concurrency climbs too high.
- InnoDB suffers contention from too many concurrently active transactions.

A thread pool may offer little visible benefit when:

- Connection and concurrency counts are already low.
- The workload is primarily bound by disk I/O or storage latency.
- Long queries, massive scans, or missing indexes are the main cause.
- Application-level lock contention already dominates response time.
- The server lacks the required edition/plugin.

The thread pool is a concurrency scheduling tool. It is not a cure-all for every type of MySQL slowdown.

## 27. Thread Pool and Connection Limits

`thread_pool_size` does not cap client connections. Connection counts remain governed by `max_connections` and other limits.

A server can have many `Sleep` connections while only a few statements execute. Conversely, if queues build up, client connections may stay open while statements wait for workers.

Therefore, when investigating connection timeouts or rising application latency, inspect all of:

- `Threads_connected` and `Max_used_connections`.
- `Threads_running`.
- `QUERIES_QUEUED` by thread group.
- `STALLED_QUERIES_EXECUTED`.
- OS CPU utilization and run queue.
- Lock waits, disk I/O waits, and statement durations.

Simply raising `max_connections` lets the server accept more connections without increasing statement execution capacity. In some scenarios, it even lengthens queues and raises memory usage.

## 28. Thread Pool Does Not Replace Query Optimization

If a query scans millions of rows due to a missing index, the thread pool does not make that work vanish. If transactions hold locks for long periods, other transactions still wait. If the buffer pool is undersized or storage is slow, workers still wait on I/O.

When queues grow, inspect:

- `EXPLAIN` or `EXPLAIN ANALYZE` for expensive queries.
- Rows examined and rows sent.
- Slow query logs and statement digests.
- Transaction age and lock waits.
- InnoDB buffer pool hit behavior and disk I/O.

Increase concurrency only after understanding the workload. More workers can sharply increase CPU, memory bandwidth, and storage contention.

## 29. Common Deployment and Operational Errors

| Symptom | Possible Cause | Remediation |
|---|---|---|
| `thread_pool` variables missing | Plugin not loaded or edition lacks the plugin | Check edition, plugin directory, `SHOW PLUGINS` |
| Plugin is not `ACTIVE` | Missing library, wrong suffix, or incompatibility | Read error log and check `plugin_dir` |
| Changing `thread_pool_size` via `SET GLOBAL` fails | Variable is non-dynamic | Configure at startup and restart per maintenance plan |
| Queues grow even though `Threads_connected` is modest | Some groups are busy or load is skewed | Inspect `tp_thread_group_stats` per group |
| Stalled queries climb | Statements exceed stall limit or block for long periods | Check queries, wait types, and `stall_limit` |
| `PRIO_KICKUPS` rises rapidly | Low-priority queue frequently requires promotion | Check transaction duration, queue pressure, and timer |
| Raising query threads worsens latency | Higher concurrency increases contention | Revert to prior config and benchmark step by step |
| Large connection pool yet throughput flatlines | Connection count does not equal executing workers | Check queues, active workers, and resource saturation |
| Using MariaDB variables on MySQL | Plugin and variable names differ across products | Use the manual and edition matching your server |
| Community Server fails to load `thread_pool` | Enterprise plugin is absent from the distribution | Use thread-per-connection, client pools, and other tuning; or evaluate Enterprise Edition |

## 30. Process for Deciding Whether to Enable Thread Pool

1. Identify the exact MySQL edition and version.
2. Check physical core count, RAM, storage, and workload type.
3. Collect baseline `Threads_running`, connection count, TPS, latency, and CPU.
4. Confirm whether the issue stems from concurrency/context switching or from queries, locks, or I/O.
5. If supported by your edition, test the plugin in staging with a representative workload.
6. Choose `thread_pool_size` and scheduling variables as an initial setup.
7. Observe queues, stalled queries, priority kickups, and wait counters.
8. Compare both throughput and p95/p99 latency before/after.
9. Check impact on low-priority sessions and long transactions.
10. Roll out to production per maintenance plan, documenting settings and rollback plans.

If the server lacks Enterprise Thread Pool, do not attempt to force it on by adding variable names to the option file. Choose edition-appropriate solutions: cap connections in the application, use connection pools, control concurrency at the service tier, optimize queries, and monitor existing thread metrics.

## 31. Practice Exercises

1. Explain the difference between a client connection pool and the MySQL server thread pool.
2. Check edition, plugin status, `plugin_dir`, and `thread_handling` on a MySQL server.
3. Explain why MySQL Community Server cannot enable MySQL Enterprise Thread Pool via `SET GLOBAL`.
4. Diagram the flow from connection to thread group, listener, queue, and query worker.
5. With `thread_pool_size = 4`, describe how incoming connections are distributed round-robin.
6. Explain why the thread pool tries to limit each group to one short executing statement at a time.
7. Describe what happens when a statement exceeds `thread_pool_stall_limit`.
8. Distinguish the high-priority queue from the low-priority queue; explain the role of transactions.
9. Change `thread_pool_high_priority_connection` in a test session and describe the risk of enabling it for all connections.
10. Calculate actual durations when `thread_pool_stall_limit = 10` and when `= 600`.
11. Use `tp_thread_group_stats` to inspect `QUERIES_QUEUED`, `STALLED_QUERIES_EXECUTED`, and `PRIO_KICKUPS`.
12. Use `tp_thread_state` to identify workers that are running, sleeping, or waiting on row locks.
13. Capture two snapshots 60 seconds apart and compute deltas for queue/stall counters.
14. Design a benchmark comparing `thread_pool_size` and `thread_pool_query_threads_per_group` on a mixed short/long workload.
15. Write a rollback runbook in case the thread pool increases p99 latency or causes queue buildup.

You have completed this lesson when you can explain the edition requirements of MySQL Enterprise Thread Pool, describe how connections are assigned to thread groups and how statements are picked from the two priority queues, understand stall detection, and read Performance Schema to evaluate scheduling effectiveness. Decide to enable and tune the thread pool based on workload characteristics and measured metrics, not connection counts alone.

## References

- MySQL 8.4 Reference Manual, MySQL Enterprise Thread Pool: https://dev.mysql.com/doc/refman/8.4/en/thread-pool.html
- MySQL 8.4 Reference Manual, Thread Pool Installation: https://dev.mysql.com/doc/refman/8.4/en/thread-pool-installation.html
- MySQL 8.4 Reference Manual, Thread Pool Operation: https://dev.mysql.com/doc/refman/8.4/en/thread-pool-operation.html
- MySQL 8.4 Reference Manual, Thread Pool Tuning: https://dev.mysql.com/doc/refman/8.4/en/thread-pool-tuning.html
- MySQL 8.4 Reference Manual, Performance Schema Thread Pool Tables: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-thread-pool-tables.html
- MySQL 8.4 Reference Manual, MySQL Enterprise Thread Pool FAQ: https://dev.mysql.com/doc/refman/8.4/en/faqs-thread-pool.html
