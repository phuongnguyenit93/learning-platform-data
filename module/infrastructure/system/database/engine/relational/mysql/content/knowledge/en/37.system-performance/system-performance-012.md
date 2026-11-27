# Connection Counts, Application Pool Sizing, and Throughput Impact

Each MySQL connection is a stateful session: user, default schema, active transaction, isolation level, session variables, temporary tables, and other settings. Applications typically keep a pool of open connections in a **connection pool** for reuse rather than opening a new connection for every request.

Pool size directly governs how much work can concurrently acquire a connection to access the database. A pool that is too small forces requests to queue in the application even when MySQL still has capacity. A pool that is too large pushes too many queries into MySQL at once, increasing contention, memory pressure, context switching, and p95/p99 latency. Thus, adding connections does not equate to increasing throughput.

Separate three quantities:

- **Open connections**: sessions held open by applications, including idle connections in pools.
- **Concurrent active operations**: requests or transactions actively using a connection.
- **Throughput**: transactions or requests completed per unit of time.

This lesson is scoped to `DATABASE_MYSQL`: budgeting connections system-wide, sizing pools based on connection hold time and database capacity, measuring queueing/latency/throughput, handling connection churn and stale connections, and preventing pools from overloading MySQL during autoscaling or rolling deployments.

## 1. Connection, Session, and Request Are Three Different Concepts

When an application opens a connection to MySQL, the server creates a session. A session outlives a single SQL statement and holds private state.

An HTTP request may:
- Not touch the database at all.
- Run one or more queries on the same connection.
- Open a transaction spanning multiple queries.
- Call multiple services, holding a database connection for only a fraction of its duration.
- Hold a connection too long if code fails to close it properly.

Do not design around one connection held for an entire HTTP request lifecycle if the request also calls external HTTP APIs, processes files, or waits on user input. Connections should be borrowed only for the time actually needed for database work and returned to the pool immediately upon completion.

### 1.1. Connection Pools Reuse Sessions

Typical flow:

~~~text
HTTP request / worker
        |
        v
Application connection pool
   |       |        |
   v       v        v
 Conn A  Conn B   Conn C
   |       |        |
   +-------+--------+
           |
           v
       MySQL Server
           |
           v
      InnoDB / SQL
~~~

The pool manages:
- Opening new connections when needed and still below the limit.
- Handing idle connections to threads/requests.
- Returning connections to a reusable state.
- Closing idle or aged-out connections per policy.
- Waiting or rejecting requests when the pool is exhausted.

A pool is normally created once at the application/process level and shared. Never create a new pool per HTTP request, repository, or DAO.

### 1.2. One Connection Does Not Execute Multiple Independent Statements Simultaneously

In the standard client/server protocol, a single MySQL connection executes one command at a time. Multiple requests run concurrently by using different connections.

If a request must run multiple sequential queries inside one transaction, those queries generally share the same connection. Never borrow a second connection for each query within the same transaction without a clear reason; doing so breaks transaction boundaries and drains the pool.

## 2. How Does MySQL Manage Connections?

By default, MySQL uses a thread-per-connection model: each client connection is served by one server thread. The thread executes session commands, processes results, and waits for the next command.

That does not mean every connection occupies a CPU core at all times. Threads may be sleeping, waiting on the network, waiting on locks, or waiting on I/O. Still, many concurrent threads consume memory, management structures, CPU scheduling overhead, and OS resources.

### 2.1. The Thread Cache Is Not a Connection Pool

MySQL provides a thread cache to reuse server threads after clients disconnect. Common variables to check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_cache_size';
SHOW GLOBAL STATUS LIKE 'Threads_created';
SHOW GLOBAL STATUS LIKE 'Threads_cached';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
~~~

Distinguish them:

| Mechanism | What Does It Manage? | Effect |
|---|---|---|
| Application connection pool | Client connections/sessions to MySQL | Reuses connections, reducing repeated handshakes and authentication |
| MySQL thread cache | Server threads serving connections | Reduces thread creation/destruction cost during connection churn |
| MySQL `max_connections` | Concurrent client connections accepted | Sets a protective ceiling on the server |

The thread cache does not hold connections on the application side and does not reduce the count of open sessions. Raising `thread_cache_size` does not replace configuring an application connection pool.

### 2.2. Server-Side Thread Pool

Some MySQL distributions offer a thread pool solution to throttle the worker threads serving many connections. MySQL Enterprise Edition provides the Thread Pool plugin; other distributions may have their own implementations.

A server-side thread pool and an application-side connection pool operate at different layers:
- The application pool caps how many connections the application opens and how many operations can borrow a connection.
- The server thread pool schedules statement execution across connections inside MySQL.

Do not assume the thread pool plugin is available in every edition. Verify the version, edition, plugin availability, and vendor documentation before designing around it.

## 3. Why Does an Undersized Pool Reduce Throughput?

Suppose an application has 100 concurrent requests while the pool has only 5 connections. At most 5 requests can use a connection at one time; the rest wait at the pool.

If each operation holds a connection for 40 ms with no contention, one connection can theoretically serve about 25 operations/second. Five connections could serve roughly 125 operations/second under that simplified model. Reality also depends on query duration, transactions, locks, network, and application overhead.

Signs of an undersized pool:
- Active connections stay pinned near `maximumPoolSize`.
- Pending threads waiting for a connection climb.
- Connection acquisition latency is high.
- Connection acquisition timeouts occur while MySQL is not saturated.
- MySQL `Threads_running` and CPU still have plenty of headroom.
- Increasing the pool by one small step shrinks the queue without noticeably worsening DB latency.

Do not conclude the pool is too small just because `active = max`. Inspect connection hold time and MySQL capacity. If connections are held long because of slow transactions or queries, growing the pool may simply pile more concurrent work onto an already burdened database.

## 4. Why Can an Oversized Pool Reduce Throughput?

A large pool lets many operations enter MySQL simultaneously. Once the database hits CPU, I/O, lock, or memory limits, adding concurrency slows every operation down.

Impacts include:
- More threads competing for CPU and increasing context switching.
- More transactions holding row locks simultaneously.
- Higher pressure on the buffer pool and caches.
- Temporary tables and per-thread buffers driving up memory usage.
- Longer I/O queues.
- More deadlocks and lock waits.
- Rising p95/p99 tail latency even as throughput stagnates.
- Server approaching `max_connections`, leaving little room for administration.

For example, if a database steadily handles 400 transactions/second at concurrency 16, raising concurrency to 64 does not guarantee 1,600 transactions/second. Once resources saturate, throughput may plateau or drop while wait times surge.

### 4.1. Throughput and Latency Must Be Viewed Together

A healthy configuration satisfies all of these:
- Throughput meets targets.
- p95/p99 latency stays within SLO.
- Connection acquisition wait is low.
- The database retains headroom for bursts and background tasks.
- No abnormal surge in lock waits, deadlocks, or connection errors.

Watching only requests/second can hide a system building internal queues and returning responses more slowly.

## 5. System-Wide Connection Budgeting

`max_connections` is a server-wide limit, not a per-application limit. You must sum the pools across every process and replica connecting to the instance.

A simple budget:

\[
C_{app} = \sum_{i=1}^{n}(R_i \times P_i)
\]

Where:
- \(R_i\): maximum replicas of application \(i\).
- \(P_i\): maximum pool size of each replica \(i\).
- \(C_{app}\): total maximum connections across application pools.

The server budget must reserve capacity for:
- Primary applications.
- Workers and background jobs.
- Migrations and batch jobs.
- Monitoring/exporters.
- DBAs and emergency connections.
- Replication or internal services depending on topology.
- Bursts and rolling deployments.

Never set the sum of maximum pools equal to `max_connections`. Keep headroom and administrative access open when applications misbehave or pools saturate.

### 5.1. Pool Summation Example

Suppose a system has:
- 6 API replicas, each with a max pool of 12.
- 3 worker replicas, each with a max pool of 4.
- 2 batch jobs, each capable of using 3 connections.
- Monitoring and operational tools needing roughly 5 connections.

Expected maximum demand:

\[
6 \times 12 + 3 \times 4 + 2 \times 3 + 5 = 95
\]

If MySQL `max_connections` is 140, 45 slots remain for headroom, administration, miscellaneous tasks, and load shifts. However, this number is strictly a connection slot budget—it does not prove MySQL has enough CPU/memory to serve 95 concurrent operations.

### 5.2. Account for Rolling Deployments and Autoscaling

When a deployment runs old and new versions side by side temporarily, replica counts exceed the steady-state desired count. Autoscaling can also spin up replicas faster than expected.

For instance, 6 normal replicas with a rolling update temporarily adding 2 surge replicas:
- API pools: \(8 \times 12 = 96\) connections.
- Workers and batch jobs remain active.
- The total can exceed a budget calculated from 6 replicas.

Calculate using actual maximum replicas and surge replicas configured in your orchestrator, not just steady-state pod counts.

## 6. Reading MySQL Connection Limits and Status

Check limits:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_user_connections';
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'thread_cache_size';
~~~

Read status counters:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Threads_created',
    'Threads_cached',
    'Connections',
    'Max_used_connections',
    'Aborted_connects',
    'Connection_errors_max_connections'
);
~~~

Meaning:

| Variable | Meaning |
|---|---|
| `Threads_connected` | Currently open client threads/connections |
| `Threads_running` | Threads not sleeping; may include threads waiting on resources |
| `Threads_created` | Threads created by the server to handle connections |
| `Threads_cached` | Threads currently sitting in the thread cache |
| `Connections` | Client connection attempts recorded since server startup/status reset |
| `Max_used_connections` | Peak simultaneous connections since server startup/status reset |
| `Aborted_connects` | Failed connection attempts recorded by the server |
| `Connection_errors_max_connections` | Refused connections due to hitting `max_connections` |

Some status variables may differ by version or distribution. Verify with `SHOW GLOBAL STATUS` on the actual server.

### 6.1. `Threads_connected` Is Not Running Queries

Pooled connections can sit idle, so `Threads_connected` is usually higher than `Threads_running`. Nor is `Threads_running` equal to queries actively burning CPU: threads can be waiting on locks or I/O.

Also inspect the processlist, Performance Schema, and application pool metrics to see what connections are doing.

### 6.2. `Max_used_connections` Is a Peak, Not Current Usage

`Max_used_connections` shows peak simultaneous connections since startup/counter reset. A value near `max_connections` warns that the ceiling was approached at some point, though it does not tell you how many connections are open right now.

Capture periodic snapshots and correlate with deployments, batch jobs, or traffic bursts.

## 7. Calculating Connection Rate and Connection Churn

`Connections` is a cumulative counter. To calculate new connection attempts per second, take two snapshots:

\[
ConnectionRate = \frac{Connections_{t2} - Connections_{t1}}{t2-t1}
\]

For example, the counter increases by 1,200 over 60 seconds:

\[
ConnectionRate = \frac{1200}{60}=20
\]

That equals roughly 20 connection attempts per second during the measurement window.

Sustained high connection rates can indicate:
- The application is not using a pool, or pools are repeatedly created/destroyed.
- Pool connection lifetime is too short.
- Health checks open fresh connections continuously.
- Application processes restart frequently.
- Network errors force client reconnects.
- Many short-lived clients such as scripts or cron jobs.

Not every connection attempt succeeds; cross-check `Aborted_connects` and error counters.

### 7.1. `Threads_created` and Thread Cache

If `Threads_created` rises quickly relative to `Connections`, the server is frequently creating threads instead of reusing cached ones. This signals you to examine `thread_cache_size` and connection churn, though not to raise the cache endlessly.

The thread cache only reduces server thread creation overhead. An application connection pool is still essential to avoid repeated handshakes, authentication, and session setup.

## 8. Sizing Pools with Little's Law

Little's Law relates throughput, time spent in the system, and average work in progress:

\[
L = \lambda \times W
\]

Where:
- \(L\): average concurrent operations in the system.
- \(\lambda\): throughput (operations/second).
- \(W\): average time an operation spends in the system (seconds).

For a connection pool, if a transaction holds a connection for its database processing duration, average active connections can be estimated by:

\[
C_{active,avg} \approx TPS \times T_{hold}
\]

Example:
- Target 300 transactions/second.
- Each transaction holds a connection for an average of 40 ms = 0.04 seconds.

\[
C_{active,avg} \approx 300 \times 0.04 = 12
\]

On average, roughly 12 active connections are needed under the assumed workload and hold time.

This is a starting point for benchmarking, not a final formula for `maximumPoolSize`. Also account for:
- Bursts and arrival distributions.
- p95/p99 connection hold times.
- Ratio of long transactions.
- Query duration and lock wait time.
- MySQL CPU/I/O capacity.
- Replica and worker counts.
- Headroom for background jobs and incidents.

### 8.1. Use Connection Hold Time, Not Just SQL Time

If a request holds a connection for 2 seconds while running SQL for 50 ms and calling an external HTTP API for 1.5 seconds, the pool slot is occupied for nearly 2 seconds. That is an anti-pattern of holding connections too long.

Separate:
- Time waiting to acquire a connection.
- Time the connection is held.
- SQL execution time.
- Lock/I/O wait time.
- Application processing time outside the database.

Shortening connection hold time often increases capacity without enlarging the pool.

## 9. Benchmark Pool Size Instead of Guessing

A practical process:
1. Pick a representative workload and dataset close to production.
2. Record baseline throughput, p50/p95/p99, error rate, and DB resource usage.
3. Run with a small pool, e.g., 4 connections per replica.
4. Increase in controlled steps, e.g., 8, 12, 16.
5. Allow sufficient warm-up and steady-state duration per run.
6. Keep replica counts and traffic consistent.
7. Record application pool active/idle/pending/acquire wait metrics.
8. Record MySQL `Threads_connected`/`Threads_running`, CPU, I/O, lock waits, and memory.
9. Stop increasing when throughput stops improving or latency/errors climb.
10. Pick the configuration that meets SLOs with headroom, not necessarily the single highest peak TPS.

### 9.1. Example Benchmark Table

| Max Pool per Replica | Throughput | p95 Latency | Pending Acquire | DB CPU | Notes |
|---:|---:|---:|---:|---:|---|
| 4 | 180 TPS | 240 ms | High | 45% | Pool is likely limiting |
| 8 | 310 TPS | 170 ms | Low | 68% | Throughput improved |
| 12 | 350 TPS | 190 ms | Low | 82% | Approaching saturation zone |
| 20 | 355 TPS | 420 ms | Rising | 95% | Minimal throughput gain, latency degraded |

Numbers are illustrative only. Decisions must rest on actual measurements. In the example, pool 20 adds negligible throughput while sharply worsening p95 latency—a clear sign concurrency exceeded the database's efficient operating region.

## 10. Metrics to Monitor on Application Pools

A pool dashboard should include:

| Metric | Meaning | Warning Sign to Investigate |
|---|---|---|
| Total connections | Total connections managed by the pool | Abnormal spikes or pinned at maximum |
| Active connections | Connections currently borrowed | Constantly equal to maximum |
| Idle connections | Available ready connections | Sustained at 0 under high load |
| Pending/waiting threads | Requests waiting for a connection | Climbing and failing to drain |
| Acquire latency | Time spent obtaining a connection | Rising p95/p99 |
| Connection timeout count | Failures to acquire a connection on time | Sudden spikes |
| Usage/hold duration | How long connections are held | Much longer than SQL execution time |
| Creation/close rate | Connection creation and teardown rate | High churn |
| Leak detection | Connections held overly long | Repeated warnings |
| Validation failures | Connections no longer usable | Spikes after idle/network events |

Do not watch active connections alone. If active is high yet acquire wait is low and throughput is steady, the pool may be working well. If pending rises, acquire p95 climbs, and timeouts appear, the pool has become a bottleneck queue.

### 10.1. Pool Wait Differs from Query Latency

A request might spend:
- 100 ms waiting to acquire a connection.
- 20 ms executing SQL.
- 10 ms processing results.

If you measure only SQL latency, dashboards report 20 ms while the user waited 130 ms. Measure acquisition latency and end-to-end request latency separately.

## 11. Configuring HikariCP in Java Applications

HikariCP is a popular JDBC connection pool. Illustrative configuration example:

~~~java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(
    "jdbc:mysql://mysql.internal:3306/app_db?connectTimeout=5000&socketTimeout=30000"
);
config.setUsername("app_user");
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(12);
config.setMinimumIdle(4);

config.setConnectionTimeout(1500);
config.setValidationTimeout(1000);

config.setIdleTimeout(300000);
config.setMaxLifetime(1500000);

// Enable only if needed to prevent idle connections from being closed by network/server.
config.setKeepaliveTime(120000);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

Values in HikariCP are in milliseconds. This is an example only, not a universal config for every workload.

### 11.1. `maximumPoolSize`

Caps total connections managed by one pool. Must be sized considering replica counts and all other pools targeting the database.

Never set `maximumPoolSize` equal to MySQL `max_connections` because every replica maintains its own pool.

### 11.2. `minimumIdle`

Number of idle connections the pool tries to maintain. Higher values keep connections ready for bursts, yet hold more idle sessions on MySQL. Total `minimumIdle` across all replicas must also fit in the budget.

If a fixed-size pool is desired, setting `minimumIdle` equal to `maximumPoolSize` follows HikariCP guidance; measure the impact. There is no need to hold all connections open when traffic is sparse.

### 11.3. `connectionTimeout`

How long a thread waits to borrow a connection from the pool before timing out. This is not the TCP connect timeout to MySQL.

When a pool is exhausted, lowering `connectionTimeout` does not make the database faster; it simply fails requests sooner. Pick a value aligned with request deadlines and retry policies.

### 11.4. `connectTimeout` and `socketTimeout`

These are JDBC driver (Connector/J) parameters, distinct from pool timeouts:
- `connectTimeout`: limits network connection establishment time.
- `socketTimeout`: limits how long the driver waits for data on a socket.

Do not set `socketTimeout` too low or valid queries get cut off mid-flight. Align with SLOs, query durations, and retry behavior.

### 11.5. `idleTimeout`, `maxLifetime`, and `keepaliveTime`

- `idleTimeout`: allows the pool to retire excess idle connections after the configured period if the pool is allowed to shrink.
- `maxLifetime`: caps maximum connection age before graceful pool retirement; set it shorter than forced timeouts on the database/proxy/network.
- `keepaliveTime`: periodically validates/keeps alive idle connections when enabled and supported by the pool version.

Set `maxLifetime` lower than any connection age limit enforced by proxies or infrastructure. If MySQL `wait_timeout` closes idle sessions, configure appropriate `idleTimeout` or keepalive/validation; do not confuse `wait_timeout` with `maxLifetime` as they measure two different conditions.

### 11.6. Validation

With JDBC 4 drivers supporting `Connection.isValid()`, a separate test query is usually unnecessary. Use `connectionTestQuery` only when required by the driver or environment.

Validation catches stale connections, though overly frequent checks add round trips. Use the pool's native validation mechanism and monitor validation failures.

## 12. Borrowing and Returning Connections Properly

Java JDBC example:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT order_id, status FROM orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Process results quickly; do not hold the connection for non-DB work.
        }
    }
}
~~~

When `Connection` closes inside `try-with-resources`, the pool typically reclaims it rather than closing the underlying socket. Closing statements and result sets frees resources and avoids holding connections longer than necessary.

### 12.1. Do Not Hold Connections Across External Service Calls

Bad pattern:

~~~java
try (Connection connection = dataSource.getConnection()) {
    Order order = loadOrder(connection, orderId);
    PaymentResult result = paymentClient.charge(order); // Can wait long on network.
    updatePayment(connection, orderId, result);
}
~~~

In this example, the connection—and possibly a transaction—is held while calling the payment API. If the API slows down, the pool drains rapidly.

A better design defines clear business boundaries:
- Read data and finish a short transaction.
- Call external services using an appropriate workflow.
- Open a new transaction to record results if needed.
- Use idempotency/outbox/saga patterns when coordinating across multiple systems.

Do not split transactions arbitrarily if atomicity is required; design business workflows explicitly.

## 13. Long Transactions Drain Pools

A connection held inside a long transaction cannot serve other requests. Long transactions can also:
- Hold row locks.
- Hold associated metadata locks.
- Hold read views and slow down purge.
- Grow undo history.
- Increase deadlock probability.
- Tie up a connection even after the current query finishes.

Example:
1. Application opens a transaction.
2. `SELECT`/`UPDATE` several rows.
3. Waits for user confirmation.
4. Calls another API.
5. `COMMIT`s seconds later.

Throughout that span, the connection is occupied and locks may be held. Avoid waiting on users or external network calls inside transactions.

Monitor:
- Transaction age.
- Connection usage duration.
- Idle-in-transaction sessions.
- Rows locked and lock waits.
- Pool pending counts.

A larger pool may mask long transactions briefly, but never fixes the root cause.

## 14. Session State and State Leakage Between Requests

Connection pools reuse sessions. Thus, session state altered by an earlier request can affect a subsequent request if not reset.

States to watch:
- `autocommit`.
- Unfinished transactions.
- Transaction isolation level.
- `read_only`.
- `time_zone`.
- `sql_mode`.
- Default schema.
- User variables.
- Temporary tables.
- Session system variables.
- Prepared statements and session-level settings.

For example, one request runs:

~~~sql
SET time_zone = '+07:00';
SET @tenant_id = 42;
~~~

If the connection returns to the pool without resetting state, the next request may inherit the old timezone or user variable.

Rules:
- Avoid mutating session state when standard connection configuration suffices.
- If state must be changed, restore it before returning the connection.
- Always ensure transactions end with `COMMIT` or `ROLLBACK`.
- Use a pool with reset mechanics verified against your driver/version.
- Never assume all session variables, temporary tables, or user variables are automatically reset identically.

### 14.1. Connection Leaks

Leaks happen when an application borrows a connection and fails to return it, for example:
- Exceptions bypassing connection close logic.
- Unclosed `ResultSet`/`Statement` objects.
- Async tasks holding connections too long.
- Connections stored in fields or `ThreadLocal`.
- Transactions never terminated.

Use `try-with-resources`, pool leak detection in appropriate environments, and connection usage metrics. Leak detection is an investigative alert, not an automatic cure-all.

## 15. `wait_timeout` and Stale Connections

MySQL enforces idle timeouts on sessions. For noninteractive connections, `wait_timeout` is typically the variable to check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';
~~~

JDBC connections are normally noninteractive. If the server closes an idle connection due to timeout while the pool still considers it valid, the application may receive a communications link failure when borrowing that connection.

Mitigations:
- Align pool `idleTimeout` with `wait_timeout` and proxy/network timeouts.
- Use keepalive/validation when appropriate.
- Set `maxLifetime` lower than forced infrastructure connection age limits.
- Catch and handle connection errors along transaction boundaries.
- Never blindly retry a non-idempotent transaction without determining commit outcome.

### 15.1. Do Not Retry Blindly on Connection Loss

If a connection drops during `COMMIT`, the client may not know whether the server committed the transaction. Retrying the entire request could create duplicate orders or double payments.

Use idempotency keys, unique business keys, or transaction status lookups to resolve uncertain outcomes. A connection pool cannot resolve commit ambiguity.

## 16. Per-Connection Memory and Resources

Each connection carries session/thread management overhead and may allocate per-operation buffers. Some buffers are allocated when a query needs them, not necessarily all up front when the connection opens.

Key variables to understand:
- `thread_stack`.
- `net_buffer_length` and `max_allowed_packet`.
- `sort_buffer_size`.
- `join_buffer_size`.
- `read_buffer_size`.
- `read_rnd_buffer_size`.
- Temporary table limits and `TempTable` engine settings.
- Memory for prepared statements, sessions, and instrumentation.

Do not sum all buffer variables and multiply by `max_connections` as if that were actual steady-state RAM usage; yet do not ignore the risk, because many concurrent queries can allocate large buffers simultaneously.

### 16.1. `max_connections` Is Not Free

Raising `max_connections` allows more sessions, but does not magically add RAM, CPU, IOPS, or lock manager capacity. If an application opens thousands of connections while the database only processes a small fraction effectively, the server still pays overhead to manage the excess sessions.

Budget memory across:
- `mysqld` base memory.
- InnoDB buffer pool.
- Per-connection/session overhead.
- Per-query allocated buffers.
- Temporary tables under concurrency.
- Performance Schema and `sys` overhead.
- Replication, background threads, and plugins.
- OS page cache and other processes.

Benchmark with peak concurrency and representative query shapes.

## 17. `max_connections` and Per-Account Limits

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_user_connections';
~~~

Server-wide limits can be set via runtime config or appropriate startup options. Changing `max_connections` requires evaluating RAM, file descriptors, threads, and workload.

Per-account limits prevent one user from exhausting all connections:

~~~sql
ALTER USER 'app_user'@'%'
    WITH MAX_USER_CONNECTIONS 40;
~~~

Account limits do not replace system-wide pool budgeting. When multiple accounts exist, combined quotas can still exceed `max_connections`.

Some MySQL versions reserve administrative connections for appropriately privileged accounts when the server reaches its limit. Check privileges and version-specific docs; never treat emergency slots as application capacity.

### 17.1. When Hitting "Too many connections"

Do not just raise `max_connections` right away. Check:
1. Current `Threads_connected` and `Max_used_connections`.
2. Application pool active/idle/pending counts across every replica.
3. Actual replica count and rolling update surge.
4. Connection churn and `Aborted_connects`.
5. Idle sessions or long transactions.
6. Unusual clients or runaway jobs.
7. CPU, memory, I/O, and `Threads_running`.
8. Reserved connection budget for administration and monitoring.

To regain admin access, use the pre-prepared emergency account/endpoint. After the incident, fix the pool budget or leak rather than merely raising limits.

## 18. Proxies and Connection Multiplexing

A database proxy can route, load-balance, or manage backend connections. Some proxies such as ProxySQL can multiplex many frontend sessions onto fewer backend connections under specific conditions.

However, multiplexing is restricted when sessions require private state or active transactions, such as:
- Open transactions.
- Temporary tables.
- User variables.
- Session system variables.
- Prepared statements/session state depending on the proxy.
- Locks or cursor/session features requiring backend affinity.

MySQL Router primarily provides routing between clients and topology; do not assume it acts as a connection multiplexer.

When using a proxy:
- Account for both frontend and backend connections.
- Decide whether pooling lives at the application tier, proxy tier, or both.
- Verify session pinning/multiplexing rules.
- Measure backend connection counts and queues.
- Test transactions, prepared statements, and session variables.
- Never assume a proxy lets applications open unlimited pools.

## 19. Connection Pools and Autoscaling

Each new replica typically creates its own pool. When autoscaling adds replicas, total connections climb even before traffic grows proportionally.

Example:
- 4 replicas × max pool 20 = 80.
- Autoscaling to 10 replicas × max pool 20 = 200.
- Rolling update surging to 12 replicas = 240.

If MySQL only allocates 180 connections for application workloads, scaling out can cause replicas to fight over connections and trigger widespread errors.

Design practices:
- Include maximum replicas in capacity models.
- Size pools from the total budget, not per pod in isolation.
- Consider smaller pools for lower-priority workers.
- Cap scale-out speed if the database is the bottleneck.
- Use backpressure at the application tier.
- Monitor total pool connections summed across replicas.
- Implement circuit breakers or load shedding when the DB overloads.

Scaling the application does not automatically scale the database. Both tiers require matching capacity plans.

## 20. Inspecting Connections and Threads via Performance Schema

You can view foreground threads:

~~~sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
~~~

Some threads have `PROCESSLIST_ID` as `NULL` or belong to background workers. Do not sum every row in Performance Schema `threads` and call that client connections.

Combine with the processlist:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Or use a convenience view if the `sys` schema is available:

~~~sql
SELECT *
FROM sys.processlist
ORDER BY time DESC;
~~~

Exact view names and columns depend on `sys` schema version. Run `DESCRIBE`/`SHOW CREATE VIEW` before writing operational scripts.

## 21. Configuring and Observing Over Time Windows

Do not rely on a single snapshot. Sample metrics at multiple timestamps and compute deltas:

\[
ConnectionRate = \frac{\Delta Connections}{\Delta t}
\]

\[
ThreadCreationRate = \frac{\Delta ThreadsCreated}{\Delta t}
\]

\[
PeakConnectionUtilization =
\frac{MaxUsedConnections}{max\_connections}
\]

For example, peak utilization of 0.92 indicates the server once reached 92% of its ceiling. This warns you to examine peak windows and headroom, though it does not necessarily reflect current state.

If counters reset after a restart, never take deltas across the reset. Record uptime, `server_uuid`, and snapshot timestamps.

### 21.1. Two-Sided Combined Dashboard

A good dashboard pairs both sides:

| Application Pool | MySQL |
|---|---|
| Active/idle/total | `Threads_connected` |
| Pending borrowers | `Threads_running` |
| Acquire latency | Statement latency |
| Connection timeouts | `Connection_errors_max_connections` |
| Usage duration | Long transactions / lock waits |
| Create/close rate | `Connections`, `Threads_created` |
| Pool max across replicas | `max_connections`, `Max_used_connections` |

If application pending count is high while MySQL still has spare CPU and low `Threads_running`, the pool may be too small or connections are being held outside the DB. If MySQL CPU/locks/I/O are already saturated, enlarging the pool can worsen the outage.

## 22. Common Diagnostic Scenarios

### 22.1. Pool Timeouts While MySQL Has Not Reached `max_connections`

Possible causes:
- Max pool size is too small.
- Connection leaks.
- Long transactions.
- Requests holding connections during external service calls.
- Connections stuck on slow queries.
- Slow pool validation or connection creation.

How to handle:
1. Check active, idle, pending, and usage duration.
2. Locate threads holding connections.
3. Correlate query latency and transaction age.
4. Audit connection-closing code paths.
5. Increase pool size only after confirming the DB has spare capacity.

### 22.2. Too Many Connections

Possible causes:
- Sum of pools across replicas exceeds budget.
- Autoscaling/rolling deployment surge.
- No pooling or heavy connection churn.
- `minIdle` set too high.
- Ad-hoc jobs/scripts opening separate connections.
- Idle sessions not reclaimed.

How to handle:
1. Check `Threads_connected` and `Max_used_connections`.
2. Group connections by user/host.
3. Sum max pool sizes across all replicas.
4. Check connection rate and thread creation rate.
5. Restore admin access using a reserved emergency account.
6. Safely shrink pools/application scale or terminate verified-safe sessions.
7. Fix budgets and alerting.

### 22.3. Throughput Fails to Grow When Increasing Pool Size

The bottleneck has usually shifted to the database:
- CPU near saturation.
- High storage latency.
- Lock contention.
- Heavy scan queries.
- Long transactions.
- Buffer pool misses.
- I/O or network saturation.

Inspect statement digests, `EXPLAIN`, waits, InnoDB lock diagnostics, and OS metrics. Never keep enlarging the pool just to reduce pending counts if the DB is already overloaded.

### 22.4. High `Threads_connected` with Low `Threads_running`

Applications may be holding many idle connections in pools. This is not automatically an error if budget headroom exists, though it can:
- Consume connection slots.
- Increase session overhead.
- Shrink headroom for batch jobs and DBAs.
- Mask an overly high `minIdle`.

Evaluate actual connection needs, `idleTimeout`, and total replica counts.

### 22.5. Rapidly Rising `Threads_created`

Possibly caused by connection churn or an undersized `thread_cache_size`. Compare delta `Threads_created` against delta `Connections`, and inspect pool lifecycles and restarts. Do not confuse rising `Threads_created` with rising active queries.

## 23. Runbook for Choosing and Tuning Pool Size

1. Identify `max_connections` and connections reserved for non-application tasks.
2. List every application, worker, job, monitoring agent, and admin tool connecting to the instance.
3. Calculate maximum replicas, rolling surge, and autoscaling ceilings.
4. Sum pool max and `minimumIdle` across all replicas.
5. Measure throughput, p95/p99, connection hold time, and SQL execution time.
6. Use Little's Law to estimate average concurrency.
7. Benchmark multiple pool sizes in a representative environment.
8. Observe active, idle, pending, acquire latency, and timeouts.
9. Observe `Threads_connected`, `Threads_running`, CPU, memory, I/O, lock waits, and error counters.
10. Pick a max pool meeting SLOs with headroom rather than the largest possible connection count.
11. Set acquisition timeout based on request deadlines.
12. Align `idleTimeout`/`maxLifetime` with MySQL and proxy/network timeouts.
13. Test restarts, failovers, rolling deployments, and autoscaling.
14. Configure alerts well before hitting `max_connections`.
15. Document configuration, baselines, and rollback conditions.

## 24. Practice Exercises

### Exercise 1: Reading Connection Status

Run `SHOW GLOBAL STATUS` for `Threads_connected`, `Threads_running`, `Threads_created`, `Threads_cached`, `Connections`, and `Max_used_connections`. Open several extra sessions in the lab and observe changes.

### Exercise 2: Comparing Connections and the Thread Cache

Create a rapid connect/disconnect churn workload in the lab. Observe `Connections` and `Threads_created` before and after changing `thread_cache_size`. Explain why the thread cache does not replace an application pool.

### Exercise 3: Multi-Replica Budgeting

Suppose there are 8 API replicas, 4 worker replicas, and 2 batch jobs. Calculate maximum total connections across different pool sizes. Reserve budget for monitoring, DBAs, and rolling deployments.

### Exercise 4: Applying Little's Law

Measure throughput and average connection hold time. Compute average concurrency. Compare with actual active connections in the pool and explain any gap.

### Exercise 5: Benchmarking Pool Size

Run the same workload with max pool sizes 4, 8, 12, and 16. Record throughput, p95/p99, acquire waits, pending borrowers, DB CPU, and `Threads_running`. Choose the value that best fits SLOs.

### Exercise 6: Simulating Pool Exhaustion

In the lab, intentionally hold connections open for a long time. Observe pending borrowers and acquisition timeouts. Fix the code to return connections early and compare.

### Exercise 7: Simulating a Connection Leak

Create a code path that fails to close a connection in a test environment. Watch pool active count climb steadily. Fix it with `try-with-resources` and confirm pool recovery.

### Exercise 8: Session State Contamination

Borrow a connection, change `time_zone` and a user variable, return the connection, and borrow again. Check whether the state persists or is reset by the pool/driver. Design explicit cleanup.

### Exercise 9: Stale Connections

In the lab, set `wait_timeout` shorter than the pool's idle period. Observe stale connections and test validation/keepalive/`idleTimeout`. Never alter production timeouts for testing.

### Exercise 10: Rolling Deployment Budget

Calculate connections when old and new replicas run concurrently. Simulate scaling out and identify when total pools could exceed `max_connections`.

### Exercise 11: Per-User Connection Limits

Set `MAX_USER_CONNECTIONS` on a lab account. Open multiple sessions and observe the limit. Analyze the impact when multiple applications share the same account.

### Exercise 12: "Too many connections" Incident

Simulate combined pools exceeding the budget. Use status variables, processlist, and application metrics to pinpoint the connection source. Write a controlled recovery runbook.

## 25. Pre-Production Deployment Checklist

- [ ] Connection pool created at application/process scope, not per request.
- [ ] Connections held only during actual database operations.
- [ ] All `Connection`/`Statement`/`ResultSet` objects closed properly.
- [ ] Transactions always terminate with `COMMIT` or `ROLLBACK`.
- [ ] Connections never held while waiting on users or calling external services.
- [ ] Total max pools summed across all replicas and workers.
- [ ] Autoscaling ceiling and rolling deployment surge factored in.
- [ ] Total connection budget reserves headroom for DBAs, monitoring, and background tasks.
- [ ] Connection count, active operations, and throughput distinguished.
- [ ] Application pool distinguished from MySQL thread cache/thread pool.
- [ ] Active, idle, pending, acquire latency, and usage duration measured.
- [ ] `Threads_connected`, `Threads_running`, `Max_used_connections`, and connection errors monitored.
- [ ] Connection churn and `Threads_created` measured via deltas.
- [ ] Little's Law used as an initial estimate, not treated as a fixed formula.
- [ ] Pool size benchmarked with a representative workload.
- [ ] Throughput monitored alongside p95/p99 latency.
- [ ] `connectionTimeout` aligned with request deadlines.
- [ ] Pool timeout distinguished from JDBC `connectTimeout`/`socketTimeout`.
- [ ] `idleTimeout`/keepalive/`maxLifetime` synchronized with MySQL and proxy/network.
- [ ] Stale connections and validation behavior tested.
- [ ] Session state controlled when reusing connections.
- [ ] Per-connection memory and `max_connections` evaluated.
- [ ] Alerts set before hitting `max_connections`.
- [ ] Emergency admin account and "Too many connections" runbook prepared.
- [ ] Failover, restarts, scale-out, and rolling deployments tested.

## 26. Conclusion

A connection pool bounds and reuses MySQL sessions at the application tier. Too small a pool builds queues and hurts throughput; too large a pool saturates the database, worsening lock contention, memory pressure, and tail latency. Proper sizing must span all replicas, workers, and batch jobs, plus surges during autoscaling or rolling deployments.

Use Little's Law to estimate average concurrency from throughput and hold time, then benchmark multiple pool sizes on the same workload. Monitor both application pool metrics and MySQL status counters; distinguish open connections from active operations, pool wait from query latency, and thread cache from connection pools. Keep transactions short, close connections properly, sanitize session state, and align timeouts across the server, proxy, and network.

Never raise `max_connections` or pool sizes just to silence alerts. First identify the bottleneck, calculate the capacity budget, and preserve administrative headroom. A well-tuned configuration hits target throughput with healthy p95/p99 latency, low connection acquisition wait, and sufficient database headroom for bursts.

## Official References

- [MySQL 8.4 Reference Manual – Connection Interfaces](https://dev.mysql.com/doc/refman/8.4/en/connection-interfaces.html)
- [MySQL 8.4 Reference Manual – Server System Variables: max_connections](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_max_connections)
- [MySQL 8.4 Reference Manual – Server Status Variables](https://dev.mysql.com/doc/refman/8.4/en/server-status-variables.html)
- [MySQL 8.4 Reference Manual – Thread Information](https://dev.mysql.com/doc/refman/8.4/en/thread-information.html)
- [MySQL 8.4 Reference Manual – Thread Cache](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_thread_cache_size)
- [MySQL 8.4 Reference Manual – Limits on Number of Connections](https://dev.mysql.com/doc/refman/8.4/en/connection-interfaces.html#connection-interfaces-max-connections)
- [MySQL 8.4 Reference Manual – Account Resource Limits](https://dev.mysql.com/doc/refman/8.4/en/user-resources.html)
- [MySQL 8.4 Reference Manual – Performance Schema Threads Table](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-threads-table.html)
- [MySQL 8.4 Reference Manual – Performance Schema Connection Control](https://dev.mysql.com/doc/refman/8.4/en/connection-control.html)
- [HikariCP – Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [HikariCP – Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [MySQL Connector/J – Configuration Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html)
