# Too Many Connections, Connection Leaks, and Exhausted Application Pools

Java applications connecting to MySQL typically use a connection pool to reuse connections. Under rising load, a failure can surface in two places: MySQL rejects new connections with `Too many connections` (error 1040), or the application cannot acquire a connection from its pool within the wait timeout and reports a pool timeout. These two errors are related yet distinct. MySQL may still have free slots while the application pool is exhausted; conversely, a pool may have room while MySQL has already hit `max_connections`.

Root causes usually lie in the system-wide connection budget, connections held too long, slow queries/transactions, connection leaks, or pool sizing mismatched to database capacity. Immediately raising `max_connections` or increasing pool size may just shift the bottleneck to another tier and overload MySQL further.

This lesson focuses on MySQL 8.0, JDBC, and HikariCP in Spring Boot applications. Configuration examples are illustrative; tune them according to instance counts, workloads, infrastructure limits, and actual library versions.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish MySQL `Too many connections` from pool acquisition timeouts.
- Calculate the connection budget across all application instances, workers, and operational tools.
- Read `max_connections`, `max_user_connections`, and the process list to locate connection sources.
- Analyze HikariCP active, idle, pending, and connection usage metrics.
- Identify connection leaks, long-running transactions, and connections held across external service calls.
- Troubleshoot safely in order, avoiding reckless session kills or unmeasured limit increases.
- Design tests for pool exhaustion, leaks, and concurrent load.

## 1. Two Distinct Types of Connection Exhaustion

Each application usually maintains its own pool. The pool manages physical connections from the application to MySQL. Each request needing database access borrows a connection; when finished and resources are closed, the connection returns to the pool for reuse.

```text
Request A ----+                       +---- MySQL
Request B ----+---- HikariCP pool ----+---- max_connections
Request C ----+                       +---- account limits
                  active / idle
                  pending / total
```

| Scenario | Typical Symptom | Where Is the Problem? |
|---|---|---|
| MySQL out of client connection slots | Error 1040 `Too many connections` | Total server sessions hit limit or account hit its own limit |
| Application pool out of idle connections | Hikari reports `Connection is not available, request timed out` | Requests wait on the pool; all connections are likely checked out |
| MySQL rejects a specific account | Error 1226 `ER_USER_LIMIT_REACHED` or resource limit exceeded message | Account hit `MAX_USER_CONNECTIONS` or global user limit |
| Old connection closed without pool noticing | `Communications link failure`, connection validation fails | Idle timeout, proxy, firewall, or network left connection stale |

Pool exhaustion can happen while MySQL still has plenty of available slots: a pool with `maximumPoolSize=10` where all 10 connections are held forces the 11th request to wait. Conversely, MySQL can run out of slots due to other applications or tools even when one individual pool has not reached its cap.

## 2. System-Wide Connection Budget

`max_connections` caps concurrent client connections on a MySQL server. You must sum potential connections across all applications, not just a single JVM.

Example system:

| Component | Max Instances | Max Pool per Instance | Total Connection Potential |
|---|---:|---:|---:|
| API service | 6 | 20 | 120 |
| Background worker | 3 | 10 | 30 |
| Scheduler | 2 | 5 | 10 |
| Migration, monitoring, and admin | — | — | 20 |
| **Expected Total** | | | **180** |

If MySQL sets `max_connections=220`, the system has roughly 40 connections of headroom under this setup. Calculate using maximum autoscaled replica counts, every `DataSource`/pool inside each process, parallel jobs, backup tools, migrations, and operational sessions. If a pod runs two pools, sum both.

The budget must satisfy:

\[
\sum (\text{max instances} \times \text{max pool per instance})
 + \text{non-application connections}
 < \text{max\_connections}
\]

The margin provides headroom for rolling deployments, admin access, bursts, and unlisted components. Never size total pools equal to `max_connections`: when a rollout spins up new instances before old ones shut down, connection counts can exceed projections.

### 2.1. Pool Size Is Not Concurrent Request Count

`maximumPoolSize` is the maximum number of connections a pool can maintain, combining active and idle connections. It is not the HTTP thread count, nor the number of requests the system should execute concurrently.

If 100 requests arrive simultaneously while the pool has 20 connections, at most 20 requests use the database concurrently through that pool; the rest wait or hit application-tier limits. This can serve as intentional backpressure. Raising the pool to 100 forces MySQL to handle more concurrent queries, and overall throughput may drop due to CPU, I/O, buffer pool, or lock contention.

Choose pool size through load testing while measuring database latency and throughput. Never rely on a rigid formula based solely on application server CPU count.

### 2.2. Per-Account Limits

Besides the server-wide limit, MySQL supports per-account connection limits. `max_user_connections` sets the default per-user limit; individual accounts can also have a dedicated `MAX_USER_CONNECTIONS` resource limit.

Check configuration:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'max_connections',
  'max_user_connections'
);
```

Check an account's limit:

```sql
SHOW CREATE USER 'app_user'@'10.%';
```

Example creating an account with a dedicated limit:

```sql
CREATE USER 'app_worker'@'10.%'
  IDENTIFIED BY '<secret-from-secret-manager>'
  WITH MAX_USER_CONNECTIONS 30;
```

Per-account limits prevent one service from starving the rest of the server. However, if the limit is too low relative to replica count and pool size, that service will hit errors even when MySQL overall has free slots. Size limits based on max instance count and real pool totals.

## 3. Diagnosing from the MySQL Side

When error 1040 occurs, inspect limits, current connections, peak usage, and session sources.

### 3.1. Checking Status and Variables

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connections',
  'Connection_errors_max_connections',
  'Aborted_connects',
  'Aborted_clients'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'max_connections',
  'max_user_connections',
  'wait_timeout',
  'interactive_timeout'
);
```

Key metric meanings:

- `Threads_connected`: number of currently open client connections at observation time.
- `Threads_running`: number of threads actively executing rather than sitting idle.
- `Max_used_connections`: peak concurrent connections since server startup or last status reset.
- `Connections`: total connection attempts to the server since startup or status reset; not current connections.
- `Connection_errors_max_connections`: number of connection attempts rejected due to reaching max connections.
- `Aborted_connects` and `Aborted_clients`: counts of failed connects or improperly closed client sessions; read alongside error logs and network status.

If `Max_used_connections` regularly approaches `max_connections`, headroom is tight. If `Threads_connected` is high while `Threads_running` is low, many sessions are idle or held in pools. That alone is not enough to prove a leak.

### 3.2. Inspecting the Process List

```sql
SHOW FULL PROCESSLIST;
```

Or query details:

```sql
SELECT
  ID,
  USER,
  HOST,
  DB,
  COMMAND,
  TIME,
  STATE,
  LEFT(INFO, 200) AS SQL_TEXT
FROM information_schema.PROCESSLIST
ORDER BY TIME DESC;
```

Count connections by user, host, and state:

```sql
SELECT
  USER,
  HOST,
  COMMAND,
  COUNT(*) AS connection_count,
  MAX(TIME) AS longest_time_seconds
FROM information_schema.PROCESSLIST
GROUP BY USER, HOST, COMMAND
ORDER BY connection_count DESC;
```

`COMMAND='Sleep'` means the session is not executing a statement at that moment. Some number of `Sleep` connections is normal because pools keep idle connections warm for reuse. However, a `Sleep` session can still hold an open transaction and row locks if the application ran DML without committing or rolling back. Inspect InnoDB transactions:

```sql
SELECT
  t.trx_mysql_thread_id AS connection_id,
  p.USER,
  p.HOST,
  p.COMMAND,
  p.TIME AS process_time_seconds,
  t.trx_started,
  t.trx_state,
  t.trx_rows_locked,
  t.trx_rows_modified
FROM information_schema.innodb_trx AS t
LEFT JOIN information_schema.PROCESSLIST AS p
  ON p.ID = t.trx_mysql_thread_id
ORDER BY t.trx_started;
```

Compare `Sleep` session counts against total pool capacity and idle timeouts; never kill all `Sleep` sessions simply because they appear in the process list.

The `PROCESS` privilege may be required to view other users' sessions. If you only see the current account's connections, use a monitoring account granted appropriate privileges per policy.

### 3.3. Distinguishing Normal Pool Idle from Leaks

A long-running `Sleep` connection may simply be a normal idle connection in a pool. Stronger signs of a leak include:

- Pool reports `active` pinned near `maximumPoolSize`, `idle` at 0, and `pending` climbing.
- Connection usage time stretches abnormally and does not drop after requests complete.
- Leak detection logs repeatedly report the same code path or stack trace.
- Application threads hold connections while waiting on HTTP calls, queues, files, or application locks.
- Session counts per user/host creep upward after each request burst without returning to baseline.

Correlate timestamps across Hikari metrics, application logs, process list, and transaction ages. `COMMAND='Sleep'` or `Threads_connected` alone is insufficient to declare a leak.

## 4. Diagnosing from HikariCP

HikariCP manages physical connections and lends them to application code. Key metrics include:

| Metric | Meaning | Warning Sign to Investigate |
|---|---|---|
| `active` | Connections currently borrowed by the application | Continuously equals max pool size |
| `idle` | Free connections waiting in the pool | Drops to 0 while `pending` climbs |
| `pending` | Threads waiting to borrow a connection | Sustained increase or climbing with load |
| `total` | Total connections currently in the pool | Hits `maximumPoolSize` |
| Acquire time | Wait time to borrow a connection | Spikes sharply before pool timeouts |
| Usage time | Duration a connection stays borrowed | Longer than expected SQL execution time |

Common interpretations:

- `active=max`, `idle=0`, `pending>0`: pool is exhausted inside the application. Look for held connections, slow queries, or long transactions.
- `active` low, `idle` high, yet new connections fail with 1040: check server-wide connection budget and other clients.
- `active` climbs steadily over time: possible leak or code holding connections too long; inspect stack traces and lifecycle.
- `total` below max while `getConnection()` still errors: pool cannot open new connections due to MySQL rejections, account limits, DNS, TLS, or network issues.

### 4.1. Example Configuration

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
      keepalive-time: 300000
      leak-detection-threshold: 30000
```

Values above are examples only. `connection-timeout` caps wait time to borrow a connection from the pool; it is not a query timeout. `max-lifetime` retires connections by age; `keepalive-time` periodically validates idle connections when supported. Both must align with idle/lifetime timeouts on MySQL, proxies, and networks.

`leak-detection-threshold` makes Hikari log a warning when a connection stays borrowed beyond the threshold. It does not close the connection or roll back transactions. A legitimate slow query or long transaction can also trigger this warning, so examine the borrow stack trace and compare usage time.

### 4.2. What Does `Connection.close()` Mean in a Pool?

For a connection borrowed from HikariCP, calling `Connection.close()` normally returns the connection to the pool for reuse rather than closing the underlying socket immediately. Failing to call `close()` leaves the connection marked active and can exhaust the pool.

Use try-with-resources:

```java
String sql = "SELECT id, status FROM orders WHERE customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String status = resultSet.getString("status");
            // Process data.
        }
    }
}
```

Closing `ResultSet`, `Statement`, and `Connection` at proper scopes lets the driver and pool release resources cleanly. With Spring Data JPA or `JdbcTemplate`, usually let the framework manage connections; never manually close a connection managed by a transaction manager.

## 5. Connection Leaks and Transactions Holding Connections Too Long

A connection leak occurs when code borrows a connection and never returns it to the pool. Other scenarios are not strictly forgotten `close()` calls yet still exhaust the pool: connections held too long inside a transaction, unclosed result streams, or requests waiting on external services while a transaction stays open.

### 5.1. Code Patterns Prone to Leaks

Failing to close a connection on exception:

```java
Connection connection = dataSource.getConnection();
PreparedStatement statement = connection.prepareStatement(sql);
ResultSet resultSet = statement.executeQuery();

// If an exception occurs before close, the connection can remain held.
```

The right pattern uses try-with-resources as shown earlier or delegates lifecycle management to the framework.

### 5.2. Never Hold a Transaction While Calling External Services

Poor design example:

```java
@Transactional
public void placeOrder(OrderCommand command) {
    orderRepository.save(command.toEntity());
    paymentClient.authorize(command.payment()); // HTTP call inside transaction
    notificationClient.send(command);           // External service call
}
```

The transaction holds a connection and locks for the entire HTTP wait even when MySQL is doing no work. If the external service slows down, many concurrent requests hold connections simultaneously and exhaust the pool.

Redesign transactions to be short, wrapping only the database operations requiring atomicity. Use an outbox or proper workflow/saga to coordinate external services; never stretch a DB transaction across multiple network calls.

### 5.3. Streams and Cursors

JPA/Hibernate streams or JDBC `ResultSet`s can hold a connection open throughout iteration. If an application returns a stream outward and processes it slowly or forgets to close it, the connection never returns to the pool.

Close streams explicitly:

```java
try (Stream<Order> orders = repository.streamPendingOrders()) {
    orders.forEach(this::processOrder);
}
```

With Spring Data JPA, streams must run inside an active transaction and close before the transaction ends. When processing large volumes, consider keyset pagination or chunking to bound connection hold times and persistence context size.

## 6. Troubleshooting Too Many Connections

When production reports error 1040, prioritize restoring administrative access and reducing sources creating new connections.

### 6.1. Response Procedure

1. **Confirm scope:** distinguish MySQL error 1040 from application pool acquisition timeouts. Record timestamps, endpoints, users, and affected hosts.
2. **Use the reserved admin channel:** if configured, MySQL 8.0.14 and later allow an extra administrative connection for accounts with `CONNECTION_ADMIN` when `max_connections` is reached. Keep admin credentials separate and test availability before incidents.
3. **Preserve evidence:** read status, variables, process list, transaction ages, and error log before killing sessions.
4. **Identify connection consumers:** group by user/host/command and compare with instance counts and pool capacities.
5. **Shed load safely:** pause non-essential workers/batches, cap concurrency, or throttle traffic at the gateway. Do not scale out application instances if every new instance opens another pool.
6. **Terminate sessions selectively:** end only sessions confirmed as runaway or unneeded; assess rollback and business impact first.
7. **Restore the budget:** adjust pools, instance counts, or MySQL limits based on measured capacity; keep headroom for admin and operational tasks.
8. **Verify:** monitor connection counts, pending counts, error 1040, latency, transactions, and replica lag after stabilization.

### 6.2. Selective Session Termination

After confirming the exact session, you can run:

```sql
KILL CONNECTION 12345;
```

`KILL CONNECTION` terminates the session. If it holds an uncommitted InnoDB transaction, the server rolls it back; rollback can take time and generate I/O load. `KILL QUERY` stops only the running statement while leaving the connection open.

Never kill all `Sleep` sessions: most may be legitimate idle pool connections. Mass killing strips pools of connections, forcing them to reconnect all at once and triggering a new connection storm. Never kill a session solely for high `TIME`; inspect user, host, transaction, query, and owner first.

### 6.3. Should You Increase `max_connections`?

`max_connections` can be changed dynamically in MySQL. Example:

```sql
SET GLOBAL max_connections = 250;
```

The command above merely illustrates an administrative action; proper system privileges and resource evaluation are required beforehand. Changes via `SET GLOBAL` do not automatically persist across restarts; durable settings must be managed in configuration files or version-supported persistence mechanisms.

Before increasing it, evaluate:

- Memory cost per connection and per-session buffers/resources.
- Thread counts, CPU scheduling, and context switching.
- Storage, buffer pool, and query workload capacity.
- Total pool capacity across all services at maximum autoscaling.
- `max_user_connections` and per-account resource limits.
- Headroom reserved for admin, backup, monitoring, and migrations.

Raising the limit can help weather a brief spike, but it does not fix connection leaks or long-held transactions. If the server lacks resources, more connections can worsen latency and error rates.

## 7. Preventing Pool Exhaustion

### 7.1. Close Resources on Every Path

- Use try-with-resources for JDBC connections, statements, and result sets.
- Never store connections in singleton fields or pass connections across layers with unclear ownership.
- With transaction managers, let the framework open and close connections per transaction.
- Close streams/cursors and never return them outside transaction boundaries without an explicit design.
- Audit exception paths, timeout paths, and cancellation paths; resources must close even when errors occur.

### 7.2. Keep Transactions Short

- Open transactions only when starting the database work requiring consistency.
- Never make HTTP calls, send emails, wait on queues, or process files inside a transaction.
- Avoid reading huge datasets and processing them slowly while holding a connection.
- Use batching/chunking and commit at sensible business boundaries.
- Watch for long transactions via `information_schema.innodb_trx` and the process list.

### 7.3. Apply Backpressure

A pool is a database concurrency limiter, not an unbounded queue. When incoming requests exceed DB capacity:

- Cap worker counts and executor queues.
- Apply rate limiting or load shedding at the gateway.
- Align connection acquisition timeouts with request deadlines.
- Avoid aggressive retries while the pool is already exhausted.
- Isolate read/write workloads or background jobs as needed while still accounting for total budget per MySQL server.

Never put an unbounded queue in front of thousands of waiting requests. Huge queues only inflate wait times and memory usage; fail fast or shed load early when capacity is exceeded.

## 8. Testing Connection Leaks and Pool Exhaustion

Tests must run against an isolated MySQL test instance with a small pool size. Never intentionally exhaust connections in production.

### 8.1. Testing Pool Exhaustion with a Latch

Test configuration:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 1
      minimum-idle: 1
      connection-timeout: 500
```

Scenario:

1. Thread A borrows the sole connection and holds it after signaling a `CountDownLatch`.
2. Thread B awaits the latch, then requests a second connection.
3. Verify Thread B receives a pool acquisition timeout near the configured threshold; no SQL from Thread B reaches MySQL.
4. Thread A closes its connection in `finally`.
5. Request a fresh connection and verify the pool serves it successfully.

Use latches/barriers to coordinate ordering. Avoid long `Thread.sleep()` calls that make test timing flaky.

### 8.2. Testing Leak Detection

Create a test fixture that intentionally holds a connection longer than `leak-detection-threshold`, verify Hikari logs a warning, and verify the stack trace points to the borrow site. Then close the connection and verify the pool recovers.

Leak detection only warns about long-held connections; tests must also verify actual release. A valid long-running query can also trip the threshold, so distinguish leaks from legitimate usage time.

### 8.3. Testing MySQL `max_connections`

If you need to test error 1040, use a dedicated MySQL test server with low `max_connections` and a test account. Open connections up to the limit in a controlled way, verify the next connection is rejected, and close all connections during cleanup. Never run this test on shared servers or environments with real data.

Also test `MAX_USER_CONNECTIONS` limits if applications have per-account resource caps. Distinguish server-wide 1040 errors from account-limit errors via exceptions, error logs, and server status.

### 8.4. Full-System Load Testing

Simulate maximum application replicas and all pools running concurrently. Measure:

- Total open connections on MySQL.
- Hikari active/idle/pending per instance.
- Acquire latency and request p95/p99.
- `Threads_running`, CPU, I/O, lock waits, and query latency.
- Connection counts during rolling deployments and autoscaling.

Tests must verify the system retains admin/monitoring headroom and never exceeds account or server limits at maximum scale.

## 9. Quick Diagnostic Table

| Symptom | Possible Cause | Next Check |
|---|---|---|
| MySQL returns error 1040 | Server hit `max_connections` | Inspect `Threads_connected`, `Max_used_connections`, process list, and `Connection_errors_max_connections` |
| Hikari pool timeout while MySQL has free slots | Pool exhausted by held active connections | Inspect active/idle/pending, usage time, leak warnings, and transactions |
| Only one service gets rejected | `MAX_USER_CONNECTIONS` or oversized service pool | `SHOW CREATE USER`, group process list by user/host |
| Many `Sleep` sessions from one host | Pool holding idle connections or unretired connections | Compare with instance counts and pool size; check `wait_timeout`, `maxLifetime` |
| `active` climbs continuously per request | Connection leak or unclosed transactions | Leak stack traces, code paths, `innodb_trx`, application thread dumps |
| Pool exhausted alongside high `Threads_running` | Slow queries, lock contention, or DB overload | Process list, slow queries, lock waits, and execution plans |
| Errors after deploy/autoscaling | Total pool capacity exceeded budget | Sum max replicas, DataSource counts, and rolling deploy surge |
| New connections keep arriving after killing sessions | Pools reconnecting closed connections | Stop mass killing; address load source and let pools stabilize |

## 10. Practice Exercise

An application cluster runs 8 API pods, each using HikariCP `maximumPoolSize=25`, plus 4 worker pods each using a max pool of 10 connections. MySQL is set to `max_connections=240`. During peak hours:

- API pods intermittently report `Connection is not available, request timed out`.
- MySQL occasionally returns error 1040.
- The process list shows many `Sleep` sessions from API pods and several long-running transactions from workers.
- During a rolling deployment, errors spike sharply.

Investigate and propose changes:

1. Calculate total current pool capacity across 8 API and 4 worker pods.
2. Compare that total against `max_connections=240`; how much room remains for monitoring, migrations, and admin?
3. If a rolling deployment temporarily spins up 3 extra API pods and 2 extra worker pods, what is the peak potential connection count?
4. Write the statements to inspect `Threads_connected`, `Max_used_connections`, `Connection_errors_max_connections`, and the process list grouped by user/host.
5. Distinguish normal pool `Sleep` sessions from a connection leak.
6. Which Hikari metrics must you collect from each pod to identify which pool is exhausted?
7. Explain why long transactions on workers can cause API pool timeouts even if both services use separate accounts.
8. Propose ways to reduce concurrency and throttle workers while preserving administrative headroom.
9. When should `max_connections` be raised, and which resources must be checked beforehand?
10. Design tests for pool exhaustion, leak detection, and server-wide 1040 in an isolated test environment.

A solid plan accounts for peak instance counts during rollouts, every pool per process, account limits, and non-application connections. Define post-change verification criteria: zero 1040 errors, `pending` back at baseline, stable acquire latency, and MySQL free of overload.

## 11. Common Misconceptions

- **Looking only at `max_connections`:** a pool can run dry long before MySQL hits its server limit.
- **Looking only at Hikari:** other services, migrations, and admin tools also consume MySQL connections.
- **Killing all `Sleep` sessions:** idle connections may be intentionally pooled resources; mass killing triggers a reconnect storm.
- **Increasing pool size to cure pool timeouts:** if the DB is already saturated, higher concurrency slows queries further.
- **Raising `max_connections` without measuring resources:** every connection costs memory and scheduling overhead; a higher limit does not mean the server can handle it.
- **Treating leak detection as auto-cleanup:** Hikari only logs warnings for long-held connections; code must still close resources.
- **Assuming `Connection.close()` always closes the socket:** inside a pool, it normally returns the connection to the pool.
- **Holding transactions during HTTP calls:** keeps connections and locks pinned while the database sits idle.
- **Forgetting rolling deployments:** temporary pod counts can exceed steady-state replica counts.
- **Aggressive retries when a pool is exhausted:** retries amplify pressure on both the pool and MySQL.

## Conclusion

`Too many connections` is a MySQL or account limit; pool exhaustion means the application has no idle connections left to serve requests. To resolve both properly, sum pool capacities across all instances, inspect server status and the process list, correlate Hikari active/idle/pending metrics, and hunt down long-held connections or slow queries/transactions. Close resources cleanly, keep transactions short, apply backpressure, and reserve operational headroom. Only raise `max_connections` after evaluating host resources and the system-wide connection budget.
