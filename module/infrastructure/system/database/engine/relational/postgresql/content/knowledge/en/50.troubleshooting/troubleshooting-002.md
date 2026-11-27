# Connection Exhaustion and Cascading Failures from Application Pools

A connection pool allows applications to reuse PostgreSQL connections instead of opening and closing a connection for every request. The pool also caps the number of sessions an application process can use concurrently. When configured properly, a pool reduces connection setup overhead and protects the database from sudden spikes in client count.

However, a pool can become a bottleneck. When every connection in the pool is busy, new requests must wait. If queries are slow, transactions hold connections for too long, or the application opens too many pools across many replicas, wait times climb. Request timeouts can trigger retries, retries amplify load, workers keep holding connections, and an initial issue can cascade into a system-wide outage.

This guide explains how to recognize pool exhaustion, distinguish application-side issues from PostgreSQL limits, find why connections are held too long, and resolve cascading failures. Examples use PostgreSQL and common Java configurations; parameter names in other pools may differ.

## 1. How Does a Connection Pool Work?

When an application needs database access, it requests a connection from the pool. If the pool has an idle connection, it hands that connection to the application. If all connections are in use and the pool has reached its maximum size, the request must wait until a connection is returned or the wait times out.

Basic flow:

1. A request or worker requests a connection.
2. The pool provides an idle connection or places the request in a wait queue.
3. The application executes SQL and processes results.
4. The application commits or rolls back the transaction.
5. The application closes the connection object; the pool returns the physical connection to the idle state for reuse.

In an application using a pool, calling close on a borrowed connection typically returns the connection to the pool rather than closing the PostgreSQL socket immediately. If code forgets to close the connection, the pool cannot tell the connection is no longer needed and treats it as still in use.

Pools commonly have these limits:

- **Maximum pool size:** the maximum number of connections the pool can manage.
- **Minimum idle:** the minimum number of idle connections the pool tries to maintain.
- **Connection acquisition timeout:** the maximum time a request waits to borrow a connection.
- **Idle timeout:** how long an idle connection can remain before being retired, depending on configuration and pool implementation.
- **Maximum lifetime:** the maximum lifetime of a physical connection before the pool replaces it.

These parameters solve different problems. Increasing maximum pool size raises the concurrency sent to the database, but also increases the number of PostgreSQL sessions and resource contention. Increasing connection acquisition timeout only makes requests wait longer; it adds no processing capacity to the database.

## 2. Two Places Where Connections Can Run Out

The phrase "running out of connections" usually refers to two different conditions. You must distinguish them before changing configuration.

### 2.1. The Application Pool Is Full

A pool may have exhausted its allowed connections even while PostgreSQL still has capacity to accept more. In this case, new requests queue inside the application.

Common symptoms:

- Application logs report timeouts when acquiring a connection from the pool.
- The pool's active connections equal maximum pool size.
- Pending or waiting requests increase.
- Connection acquisition wait time climbs while PostgreSQL has not reached `max_connections`.
- The database may still operate normally for other clients.

For example, logs may contain messages such as "Connection is not available, request timed out" or "Timeout waiting for connection from pool". Exact wording depends on the library.

In this scenario, increasing PostgreSQL's `max_connections` may not help, because the application is not opening additional connections to the server. You need to find why borrowed connections are not being returned or why query throughput is lower than incoming request rate.

### 2.2. PostgreSQL Has Reached Its Connection Limit

PostgreSQL limits concurrent clients with the `max_connections` setting, alongside slots reserved according to configuration and version. When no eligible slots remain, new connections are rejected. Applications may log errors like "too many connections" or fail to open a connection.

Symptoms:

- PostgreSQL logs indicate the connection limit has been reached.
- Multiple different applications or pools fail to connect at the same time.
- Total backends are near the configured limit.
- Normal administrative connections may also fail if no slots are reserved for them.

Causes can include a pool configured too large, an increase in replicas, multiple services connecting directly, background jobs opening separate connections, or connection leaks. A system with many small pools can still exceed the limit when summed across all replicas.

### 2.3. Distinguishing via Metrics

| Observation | Application Pool Full | PostgreSQL Out of Slots |
|---|---|---|
| Active connections in pool | At or near limit | May be at limit |
| Pending requests in pool | Usually increasing | May increase because new connections are rejected |
| PostgreSQL max_connections | May still have many free slots | Usable limit reached |
| Typical error | Timeout borrowing a connection | Too many connections / connection refused |
| Blast radius | May affect only one instance or service | May affect multiple applications |

Look at both pool metrics and PostgreSQL-side metrics. Looking at only one side can lead to misdiagnosis.

## 3. Common Causes of Pool Exhaustion

### 3.1. Slow Queries or Lock-Waiting Queries

A connection is held for the entire duration the application uses it. If SQL runs slowly, that connection cannot serve other requests during that time. If many requests run slow queries concurrently, the pool can fill up even without an increase in requests per second.

A query may also be waiting on a lock rather than consuming CPU. For instance, one transaction updates a row and stays open; other transactions needing to update the same row must wait. Each waiting request can still hold a connection from the pool.

Check query duration, wait events, locks, and execution plans. Increasing pool size while queries are slow can cause even more queries to contend for CPU, I/O, and locks.

### 3.2. Transactions Held Open Too Long

Transactions should wrap only the database work that requires consistency. If an application opens a transaction and then makes HTTP calls, reads files, waits for user input, or runs lengthy business logic, the connection can be held throughout that entire wait.

Example of a bad flow:

~~~text
Borrow connection
BEGIN
UPDATE inventory
Call payment service over HTTP
Wait 8 seconds for response
UPDATE orders
COMMIT
Return connection to pool
~~~

If the HTTP service is slow, both the transaction and the connection are held for a long time. Other transactions may have to wait on locks on `inventory`, filling the pool even faster.

Move processing that does not need to be inside the transaction outside of it. If business logic must coordinate the database and external services, consider intermediate states, an outbox pattern, or sagas instead of holding a database transaction open across a network call.

### 3.3. Connection Leaks in the Application

A connection leak occurs when the application borrows a connection and never returns it to the pool. Common scenarios:

- Not closing the connection in an exception branch.
- `ResultSet` or `Statement` keeping the connection alive longer than expected.
- Transactions not committed or rolled back during error handling.
- Asynchronous flows receiving a connection and failing to close it in callbacks.
- Code returning from a function before executing cleanup.
- A connection stored in a shared variable or cache outside the request scope.

In Java, try-with-resources ensures resources are closed even when exceptions occur:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id, status FROM orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Map the row to the application model.
        }
    }
}
~~~

If using Spring transaction management, let the framework manage transactions at service boundaries and avoid manually closing framework-managed connections. Ensure every success and failure path ends the transaction.

Leaks typically show up as active connections steadily rising over time while throughput does not rise proportionally. If the pool has leak detection, pool logs can print the stack trace where a connection was borrowed and held too long. This tool is helpful during investigation, though setting the threshold too low can trigger false alarms for legitimate long-running queries.

### 3.4. Pool Multiplied by Replica Count

Maximum pool size is usually a per-instance limit, not a system-wide limit. With multiple replicas, the maximum total connections is the sum of pools across all replicas and workers.

Example:

| Component | Instance Count | Max Pool per Instance | Total Maximum |
|---|---:|---:|---:|
| API service | 8 | 20 | 160 |
| Worker service | 4 | 12 | 48 |
| Scheduler | 2 | 5 | 10 |
| Total | 14 | | 218 |

If PostgreSQL has a budget of 180 connections for application workloads, this configuration can exceed the budget when all pools open their full capacity. This can happen after a scale-out event even though each instance kept its old configuration.

When planning, include migration jobs, administrative tasks, replication, monitoring, BI tools, and other services. Do not divide `max_connections` by a single pool while ignoring all other clients.

### 3.5. Retries and Timeouts Amplifying Load

A database issue can create a feedback loop:

1. Slow queries fill the pool.
2. Requests wait for a connection and time out.
3. Clients or gateways retry the requests.
4. Retries generate additional requests that also wait for connections.
5. Application workers, threads, and queues become saturated.
6. When the database partially recovers, a wave of concurrent retries floods in and fills the pool again.

This is a retry storm. It turns a localized issue into a cascading failure across APIs, workers, gateways, and dependent services.

Retries are only appropriate for transient errors and operations that are safe to retry. Limit retry attempts, use exponential backoff with jitter, enforce an overall request deadline, and avoid retrying simultaneously at multiple layers. A single request should not be retried at the client, gateway, service, and database wrapper without a shared budget.

## 4. Observing the Pool and PostgreSQL

Diagnostics should start with metrics rather than guessing configuration changes. Monitor both the application pool and PostgreSQL backends.

### 4.1. Key Application Pool Metrics

Metric names vary by library, but you should collect:

| Metric | Meaning | How to Read |
|---|---|---|
| Active connections | Connections currently borrowed by the application | Climbing to the limit indicates a busy pool |
| Idle connections | Connections ready for new requests | Staying at 0 for long periods can signal saturation |
| Pending / waiting threads | Requests waiting for a connection | Steady growth means demand exceeds connection capacity |
| Acquisition time | Time spent waiting to borrow a connection | Rising P95/P99 often precedes timeout errors |
| Usage duration | Time a connection is held | Increases point to slow queries or code holding connections |
| Timeout count | Connection borrow failures due to timeout | Increases indicate users may already be impacted |
| Connection creation / failure | Rate of connection creation and connect errors | Sudden spikes can indicate database or network instability |

Record metrics per application instance and pool name. System-wide aggregation alone can hide a single leaking or misconfigured replica.

### 4.2. Counting Connections on PostgreSQL

You can view backend counts by state:

~~~sql
SELECT
    state,
    count(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY connections DESC;
~~~

View connections by database, user, application, and state:

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, application_name, state
ORDER BY connections DESC;
~~~

Compare total client connections against configuration:

~~~sql
SHOW max_connections;

SELECT count(*) AS current_client_connections
FROM pg_stat_activity
WHERE backend_type = 'client backend';
~~~

`pg_stat_activity` provides one row per server process and shows its current state. The `application_name` column is useful if each service sets a distinct name in its connection string or driver configuration. If all applications share the same name, identifying connection sources is harder.

Key states to watch:

- **active:** backend is executing a statement.
- **idle:** backend is waiting for a new command with no open transaction.
- **idle in transaction:** a transaction is open, but no statement is currently executing.
- **idle in transaction (aborted):** a transaction encountered an error and has not yet ended with a rollback.

A large number of `idle` connections may simply mean pools keeping connections ready. A large number of `idle in transaction` sessions warrants investigation because unfinished transactions can hold locks and prevent vacuum from reclaiming old row versions.

### 4.3. Finding Long-Running Queries and Old Transactions

The following query lists active backends along with query duration:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND state IS DISTINCT FROM 'idle'
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
~~~

The `wait_event_type` and `wait_event` fields help distinguish backends waiting on locks, I/O, clients, or other events. `query_age` shows how long the current statement has been running; `transaction_age` shows how long the transaction has been open. A statement that just started inside an old transaction can still hold state and locks from earlier operations.

Find long idle transactions:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    now() - xact_start AS transaction_age,
    state,
    left(query, 500) AS last_query
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
~~~

Do not conclude a query is hung based solely on its age. Examine wait events, locks, execution plan, and the transaction's role before intervening.

### 4.4. Checking Limits and Timeout Settings

Commands to inspect server configuration:

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
SHOW statement_timeout;
SHOW lock_timeout;
SHOW idle_in_transaction_session_timeout;
SHOW idle_session_timeout;
~~~

`idle_session_timeout` is available in newer PostgreSQL versions; check documentation for your running version before relying on it. Timeout settings must fit the workload and client type. In particular, terminating idle sessions can affect applications using connection pools if the pool does not detect and evict connections closed by the server.

## 5. Finding the Root-Cause Chain of Pool Exhaustion

During an alert, align metrics along the same timeline. A single active-connections chart is not enough to distinguish slow queries, leaks, scale-outs, or retry storms.

| Symptom | What to Investigate |
|---|---|
| Active connections climb steadily over hours, long usage duration | Connection leak or code holding connections |
| Active climbs alongside query latency and lock wait events | Lock contention or long transactions |
| Connections jump immediately after replica count increases | Total pool across replicas exceeds budget |
| Pending threads and timeouts rise while DB still has slots | Pool too small or connections held too long |
| Multiple services simultaneously report too many connections | PostgreSQL reached limit or another client opened too many |
| Errors surge after a network blip, heavy request retries | Retry storm or reconnect storm |
| Idle in transaction count increases | Transactions not closed or app waiting externally while holding a transaction |

### 5.1. Viewing Blocking Locks

You can find blockers using the `pg_blocking_pids` function:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_for,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 300) AS blocked_query,
    left(blocker.query, 300) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
ORDER BY blocked.query_start;
~~~

A single blocker transaction can stall many other requests. Instead of looking only at waiting queries, identify the transaction holding the initial lock, its owning application/user, and how long it has been open.

### 5.2. Comparing Connection Hold Time with SQL Execution Time

If the pool reports usage duration and the application measures SQL execution time, compare the two metrics:

- SQL runs in 100 ms, but the connection is held for 10 seconds: the remaining time may be spent in application processing, waiting on another service over the network, or an overly broad transaction scope.
- SQL runs for 10 seconds and the connection is held for 10 seconds: optimize the query, indexes, locks, or database resources.
- SQL finished, yet the connection remains active in the pool: inspect code missing connection closure or unfinished transactions.

Not every pool reports connection hold time in the same way. You can instrument the data access layer or enable leak detection to collect stack traces when needed.

## 6. Designing Appropriately Bounded Pools

### 6.1. Calculating a System-Wide Connection Budget

Do not set maximum pool size independently for each service. Calculate the maximum total connections that can arise:

~~~text
Maximum total application connections
  = sum (service replicas × max pool per replica)
    + workers and background jobs
    + other direct clients
~~~

Then compare against PostgreSQL's client connection budget:

~~~text
Application pool budget
  = max_connections
    - reserved and administrative standby slots
    - connections for other workloads
    - operational headroom
~~~

For example, suppose the server has `max_connections` set to 300. Operations reserves 20 slots for administration and special tasks, 40 slots for other workloads, and wants to keep 30 slots of headroom. The remaining budget for applications is 210.

If there are 6 identical API replicas and no other pools, the average limit per replica must stay within 210/6, or 35 connections. If workers or schedulers also exist, subtract their share before dividing for the API.

This is an upper-bound calculation, not a recommendation to keep all those connections open at all times. PostgreSQL often achieves higher throughput with far fewer active queries than `max_connections`. Pool sizes should be tuned based on CPU capacity, I/O, query patterns, and actual concurrency.

### 6.2. A Larger Pool Does Not Mean Faster Execution

Every PostgreSQL backend consumes resources. When too many queries run concurrently, they compete for CPU, memory, I/O, cache, and locks. Increasing active query count can lengthen each individual query, causing connections to be held even longer and keeping the pool full.

Therefore, increasing maximum pool size can create a negative feedback loop:

~~~text
Larger pool
   |
   v
More concurrent queries
   |
   v
Higher CPU / I/O / lock contention
   |
   v
Slower queries, connections held longer
   |
   v
Pool remains exhausted
~~~

Try a smaller pool size or limit concurrency at the application layer if the database is already saturated. The goal is to maintain the concurrency level PostgreSQL handles efficiently, not to let every request open its own backend.

### 6.3. Setting Timeouts Across Layers

A request can wait at multiple points: application queue, pool, network connection, locks, and SQL execution. Define an overall deadline and allocate budgets per stage.

Common timeouts:

- **Pool acquisition timeout:** bounds how long a request waits to borrow a connection.
- **Connect timeout:** bounds how long establishing a new connection can take.
- **Statement timeout:** bounds SQL statement execution time in PostgreSQL.
- **Lock timeout:** bounds how long a statement waits to acquire a lock.
- **Idle in transaction timeout:** terminates sessions with transactions left idle too long.
- **Request deadline:** bounds the total time allowed for the entire request.

Timeout ordering must be intentional. For example, with a 5-second request deadline, do not set pool acquisition timeout to 30 seconds. If the client has already abandoned the request, the server may still keep executing the query and occupying a connection unless cancellation is propagated to the database.

PostgreSQL allows configuring `statement_timeout` and `lock_timeout` at the role or database level, or per session/transaction when managed by the application. Avoid setting overly low values globally across all workloads because legitimate reports or batch jobs may need more time.

### 6.4. HikariCP Configuration Example

For Java using HikariCP, an illustrative configuration:

~~~properties
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.validation-timeout=1000
spring.datasource.hikari.max-lifetime=1500000
spring.datasource.hikari.idle-timeout=300000
spring.datasource.hikari.pool-name=orders-api
~~~

These values are examples only; recalculate them based on your connection budget and workload timings. HikariCP manages connection lifecycles and exposes pool metrics through appropriate integrations. Avoid mistaking `connection-timeout` for SQL execution time: it is the wait time to acquire a connection from the pool.

`max-lifetime` should be lower than any connection lifetime limit imposed by a database proxy or network infrastructure, if present. `minimum-idle` determines how many idle connections are maintained; if set high across many replicas, the system can open a large burst of connections immediately during scale-out.

Leak detection can be enabled during investigations to pinpoint where connections are borrowed too long. Do not set an arbitrarily low threshold or treat those warnings as definitive proof of a leak, since legitimate queries slower than the threshold also trigger warnings.

## 7. Using PgBouncer When Managing Many Clients

PgBouncer is a connection pooler placed between applications and PostgreSQL. Applications connect to PgBouncer; PgBouncer manages a set of server connections to serve many client connections.

~~~text
API replicas / workers
        |
        | client connections
        v
    PgBouncer
        |
        | server connections
        v
    PostgreSQL
~~~

PgBouncer can reduce physical connections to PostgreSQL when there are many application clients. It is especially useful when a system has many replicas, many workers, or clients creating short-lived connections.

### 7.1. Pooling Modes

PgBouncer has three common modes:

| Mode | When Server Connection Is Returned | Characteristics |
|---|---|---|
| session | When client disconnects | Preserves session state; low sharing ratio |
| transaction | When transaction ends | Allows many clients to share fewer server connections |
| statement | After each statement | Each statement is its own transaction; unsuitable for many apps |

**Session pooling** keeps a server connection for the entire client session. This is more compatible with session-dependent features but reduces connection sharing.

**Transaction pooling** holds a server connection only for one transaction. Once the transaction commits or rolls back, the server connection can serve another client. This increases client multiplexing, but the application must not assume the next transaction will use the same backend server session.

With transaction pooling, watch out for session-level state such as arbitrary `SET` commands, temporary tables surviving across transactions, `LISTEN`, session advisory locks, and other connection-scoped features. Some capabilities around prepared statements depend on the PgBouncer version and configuration; verify compatibility before switching modes.

**Statement pooling** does not permit normal multi-statement transactions because the server connection may be returned after every statement. Use it only when the workload genuinely fits.

### 7.2. Illustrative PgBouncer Configuration

A conceptual configuration:

~~~ini
[databases]
app = host=postgres port=5432 dbname=app

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 30
reserve_pool_size = 5
reserve_pool_timeout = 3
~~~

These values merely illustrate syntax and separating client limits from the server pool. Actual pools are partitioned per database and user, so total server connections can be the sum of multiple pools. Account for all database/user combinations and any overrides rather than treating `default_pool_size` as a single global cap for all of PgBouncer.

`max_client_conn` caps client connections accepted by PgBouncer; `default_pool_size` controls server connections per configured pool; the reserve pool allows opening a bounded number of extra connections when needed. Increasing `max_client_conn` does not give PostgreSQL more processing power, since clients still share server connections.

### 7.3. Observing PgBouncer

Common administrative commands:

~~~sql
SHOW POOLS;
SHOW STATS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW CONFIG;
~~~

In `SHOW POOLS`, monitor clients waiting for a server connection, active servers, and idle servers. If client waits grow while the server pool is full, PgBouncer is queuing because no server connections are free. Examine query latency, pool size, and PostgreSQL load before increasing the pool.

PgBouncer adds another queue. If the application pool is waiting on PgBouncer, and PgBouncer is waiting on PostgreSQL, requests can pile up at two layers. Track acquisition time in the application and wait time in PgBouncer to see where the queue sits.

## 8. Resolving Cascading Failures in Order

When the pool is exhausted and errors are spreading, prioritize restoring serviceability and stopping new load from amplifying the incident. Do not simultaneously raise pool size, `max_connections`, and retry counts, as that makes it impossible to isolate the effect of each change.

### Step 1: Determine the Blast Radius

Identify which services are failing, when errors began, which replicas have full pools, and whether PostgreSQL has hit its connection limit. Correlate pool active, idle, pending, and timeout counts; backends by database, user, `application_name`, and state; query latency, lock waits, CPU, I/O, and connection count; replica, worker, and background job counts; and retry rates, request timeouts, and queue depth.

If only one service has a full pool while PostgreSQL has plenty of free slots, focus on that service's pool and code. If multiple services fail to connect at the same time, investigate limits or load on PostgreSQL and shared clients.

### Step 2: Stop Retry Storms and Non-Essential Load

Reduce automatic retries, apply backoff with jitter, and eliminate unbounded retries. Pause background jobs, batch processes, or consumers that can be deferred if they are competing for connections with critical requests.

If the API can reject early when the pool has no capacity left, apply controlled load shedding to fail fast instead of holding thousands of requests in queues. Application queues must be bounded; an unbounded queue just moves where memory and latency accumulate.

### Step 3: Reduce Concurrency at the Load Source

Scale down workers or replicas generating excessive queries. If you recently scaled out and total pools exceeded the budget, scale back or lower the maximum pool size on new instances. Do not enlarge the pool to try draining queues when the database is saturated.

Preserve capacity for critical operations and administration. You may temporarily disable a non-essential flow to let the database recover, then re-enable it in a controlled manner.

### Step 4: Find Queries or Transactions Holding Connections

Use `pg_stat_activity` and `pg_blocking_pids` to locate long-running queries, `idle in transaction` sessions, and blockers. Check application logs to match PID or `application_name` with specific requests or jobs if recorded.

If an abandoned transaction or cascading blocker is holding locks, contact the service owner to confirm whether it can be canceled. Never terminate a backend solely because its query has been running a long time; it could be a valid task performing critical work.

### Step 5: Selectively Free Connections

Once you have identified a blocking backend and have authorization to cancel it, use `pg_cancel_backend` to request canceling the running statement:

~~~sql
SELECT pg_cancel_backend(12345);
~~~

If the entire session must be ended, `pg_terminate_backend` disconnects it:

~~~sql
SELECT pg_terminate_backend(12345);
~~~

Replace the PID with the verified backend. Terminating a session rolls back uncommitted transactions and can cause requests to fail. Prefer canceling the query first if stopping the statement suffices; terminate the session only when freeing the session is required or cancellation is insufficient. Never run these commands in bulk by state without identifying owners and impact.

### Step 6: Restore Traffic Gradually

Once query latency, connection waits, and backend counts stabilize, re-enable workers and ramp traffic up in stages. Monitor pool pending counts, request latency, error rates, and PostgreSQL load after each step.

If all clients reconnect simultaneously, a reconnect storm can occur. Use backoff with jitter and avoid restarting all replicas at once. Pools generally recover on their own once connections are returned; restart applications only when the pool or client state is genuinely stuck and after assessing reconnect impact.

### Step 7: Document Root Cause and Preventive Actions

After service recovery, trace the chain of events: traffic shift, slow query, lock, leak, replica growth, pool configuration, or retries. Tie each cause to a verifiable change such as fixing transaction boundaries, adding an index, capping concurrency, reducing pool size, setting timeouts, or adding metrics.

## 9. Timeouts, Retries, and Backpressure

These three mechanisms must work together to keep the system stable when the database slows down.

### 9.1. Timeouts Must Have a Budget

Suppose a request has a 4-second deadline. You can allocate part to pool acquisition, part to SQL, and the remainder to application processing. If each layer sets a timeout longer than the upper layer's deadline, requests will continue consuming resources after the client has given up.

Illustrative example:

| Stage | Budget |
|---|---:|
| Pool wait | 500 ms |
| SQL execution and locks | 2,500 ms |
| Processing and returning response | 1,000 ms |
| Total deadline | 4,000 ms |

Numbers must reflect actual SLOs and latency distributions. A long-running reporting job should have its own deadline rather than sharing timeouts with interactive APIs.

### 9.2. Bounded Retries

Only retry errors likely to be transient and operations that are idempotent or protected against duplicate writes. For example, an order-creation request should not be blindly retried if the first attempt may have committed while the response was lost.

A retry policy typically includes:

- A small maximum number of attempts.
- Exponential backoff.
- Jitter so clients do not retry at the exact same instant.
- A total retry budget that fits within the request deadline.
- Error classification so configuration errors, constraint violations, or invalid SQL are not retried.

Do not immediately retry pool acquisition timeout errors within the same request if the pool is already saturated. Doing so only creates more contention for the scarce resource.

### 9.3. Backpressure and Bounded Queues

Backpressure slows down or rejects incoming work when downstream cannot keep up. For PostgreSQL, this can be applied at multiple layers:

- Limit concurrent requests allowed into the repository layer.
- Cap worker concurrency according to the database budget.
- Bound queue length and wait time.
- Use semaphores or separate bulkheads for heavy workloads.
- Prioritize critical requests and pause non-urgent batch jobs.

Bulkheads prevent one workload from exhausting connections needed by another. For instance, transactional APIs and reporting can use separate pools or concurrency limits, though their combined budget must still fit within PostgreSQL's capacity.

## 10. Testing and Rehearsing Pool Exhaustion Scenarios

Pool exhaustion should be reproduced in a bounded test environment—never try overloading production. A test can use a small pool and many concurrent workers:

~~~text
Pool maximum = 5
Worker count = 20
Each worker:
  1. Borrow connection
  2. Run a SQL statement with a controlled wait
  3. Return connection
Observe:
  - active connections
  - pending workers
  - acquisition time
  - timeout count
~~~

The test should verify:

- Active connections never exceed maximum pool size.
- Waiting workers receive a connection as soon as another worker returns one.
- When acquisition timeout expires, the application handles the error cleanly and does not hold threads indefinitely.
- Exceptions during queries still return the connection to the pool.
- Failed transactions are rolled back.
- Canceling the test leaves behind no unwanted sessions or transactions.

You can create an intentional leak test in an isolated environment to confirm leak detection works. Then add tests for exception paths and asynchronous callbacks to guarantee cleanup runs.

For testing PostgreSQL `max_connections`, use a dedicated instance with a low limit and controlled connections. Do not change `max_connections` on a shared server to simulate an outage. Remember that changing `max_connections` requires restarting PostgreSQL, so it is not an instant adjustment knob during a production incident.

## 11. Operations and Prevention Checklist

Before deploying a new pool configuration, verify:

- Total pool maximum across all replicas, workers, and services stays within the connection budget.
- Headroom exists for migrations, monitoring, administration, and other workloads.
- Pool acquisition timeout aligns with the request deadline.
- Connections and transactions are closed in both success and exception paths.
- Transactions do not wrap HTTP calls or unnecessary wait operations.
- Query latency, lock waits, and connection usage are monitored.
- Retries have limits, backoff, and jitter.
- Queues and concurrency are bounded.
- `application_name` distinguishes services.
- A procedure exists to inspect and cancel verified blockers.
- If using PgBouncer, pool mode is compatible with application session behavior.
- Dashboards and alerts cover active/idle/pending connections, acquisition latency, and timeouts.

Alerts should be set ahead of critical failure thresholds. For example, alerting when pending requests grow steadily or acquisition P95 rises for several minutes helps you intervene before the entire pool times out. Do not wait to alert only after PostgreSQL hits `max_connections`.

## 12. Principles for Maintaining Stability

A connection pool is a throttling mechanism for PostgreSQL access, not an infinite source of capacity. Pool configuration must be grounded in total replica count, query processing capacity, and the system-wide connection budget. When a pool fills up, determine whether connections are tied up by queries, locks, long transactions, leaks, or traffic spikes.

A resilient system caps concurrency, aligns timeouts to deadlines, budgets retries, enforces backpressure, and collects metrics from both applications and PostgreSQL. During an incident, shed load and stop retry storms first, identify blockers and selectively free sessions, and then restore traffic gradually. These practices prevent a single exhausted pool from bringing down the entire application and database.
