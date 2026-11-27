# Transactions Not Rolling Back, Connection Pool Exhaustion, and Hanging Queries in Spring Data JDBC

## 1. Three Frequently Confused Failure Categories

When a write request fails or takes too long, symptoms at the application layer can look alike: the request stalls, data ends up in an unexpected state, or other requests start queuing up.

However, these three failure categories have distinct root causes:

1. **Transaction fails to roll back:** SQL ran, yet changes were committed even though the use case failed.
2. **Connection pool exhaustion:** the application cannot acquire a JDBC connection from the pool to start database work.
3. **Hanging or slow queries:** the application already holds a connection, but the statement is waiting on locks, running slowly, transferring too much data, or hitting driver/network issues.

Before adjusting timeouts or increasing pool sizes, determine which phase the request is stuck in.

| Symptom | Where to check first |
|---|---|
| Data persists after service throws an error | Rollback rules, proxy, transaction manager |
| Hikari reports timeout acquiring a connection | Active/idle/pending connections, connection leaks, long transactions |
| SQL log shows statement started but never finished | Database locks, query plan, driver, and network |
| Multiple requests wait despite low DB query load | Pool acquisition, connections held too long, or blocked threads |
| Service succeeds yet partial data is missing | Transaction boundaries, multiple DataSources, or non-DB side effects |

## 2. Transaction Not Rolling Back: Check Rollback Rules First

By default in Spring transactions, a transaction is marked for rollback when a method exits with a RuntimeException or Error. Checked exceptions generally do not trigger rollback unless a rollback rule is declared.

Example:

~~~java
@Transactional
public void placeOrder(Order order) throws IOException {
    orders.save(order);

    throw new IOException("Unable to write auxiliary data");
}
~~~

In this example, IOException is a checked exception. Without an explicit rollback rule, the transaction may commit the changes to orders even though the method throws an exception to the caller.

If business logic requires checked exceptions to roll back as well:

~~~java
@Transactional(rollbackFor = IOException.class)
public void placeOrder(Order order) throws IOException {
    orders.save(order);

    throw new IOException("Unable to complete use case");
}
~~~

Multiple exception types can be listed:

~~~java
@Transactional(rollbackFor = {
        IOException.class,
        ImportValidationException.class
})
public void importOrders(...) throws IOException, ImportValidationException {
    // ...
}
~~~

Also check noRollbackFor settings. If an exception is listed in noRollbackFor, Spring can commit the transaction even when that exception escapes.

### 2.1. Exception caught and not rethrown

A common mistake is catching an exception to log it and then letting the method return normally:

~~~java
@Transactional
public void placeOrder(Order order) {
    orders.save(order);

    try {
        inventory.reserve(order.getProductId(), order.getQuantity());
    } catch (InventoryException ex) {
        log.error("Unable to reserve inventory", ex);
        // Method continues and finishes normally.
    }
}
~~~

If the exception did not mark the transaction rollback-only, the method finishes normally and the transaction may commit the order. As a result, the order exists even though inventory reservation failed.

If both operations must succeed together, rethrow an appropriate exception:

~~~java
@Transactional
public void placeOrder(Order order) {
    orders.save(order);

    try {
        inventory.reserve(order.getProductId(), order.getQuantity());
    } catch (InventoryException ex) {
        throw new OrderPlacementException(
                "Unable to create order",
                ex
        );
    }
}
~~~

If an exception was caught yet an operation participating in the transaction already marked it rollback-only, the outer transaction can throw UnexpectedRollbackException upon commit. Look for the original exception in logs rather than reacting only to the final exception.

## 3. Is @Transactional Actually Being Applied?

In default proxy mode, Spring applies the transaction interceptor when an external call passes through the bean proxy. Simply placing the annotation on a method does not guarantee the method runs inside a transaction.

### 3.1. Self-invocation bypasses the proxy

Example:

~~~java
@Service
public class ImportService {

    public void importAll(List<ImportRow> rows) {
        this.importChunk(rows);
    }

    @Transactional
    public void importChunk(List<ImportRow> rows) {
        // Write data.
    }
}
~~~

The call this.importChunk() happens within the same object, bypassing the Spring proxy. In proxy mode, the annotation on importChunk may not take effect.

Place the transaction annotation on the entry method invoked through the proxy:

~~~java
@Service
public class ImportService {

    @Transactional
    public void importAll(List<ImportRow> rows) {
        // Repository operations all run within this transaction.
    }
}
~~~

Or extract chunk processing into another bean if each chunk requires its own transaction:

~~~java
@Service
public class ImportCoordinator {

    private final ImportChunkService chunks;

    public ImportCoordinator(ImportChunkService chunks) {
        this.chunks = chunks;
    }

    public void importAll(List<ImportRow> rows) {
        for (List<ImportRow> chunk : split(rows, 500)) {
            chunks.importChunk(chunk);
        }
    }
}

@Service
public class ImportChunkService {

    @Transactional
    public void importChunk(List<ImportRow> chunk) {
        // Call through bean proxy opens or joins a transaction.
    }
}
~~~

### 3.2. Is the bean managed by Spring?

These scenarios can prevent the transaction interceptor from running as expected:

- The service was instantiated with new instead of being injected from the Spring context.
- The method was invoked during bean initialization before the proxy was ready.
- Transaction management is not enabled in plain Spring configuration.
- The annotation was placed on a method not intercepted under the active proxy/AOP configuration.
- The caller holds a reference to the target object rather than the proxy.

Verify the actual injected bean and the call path from controllers or other services. In standard Spring Boot apps, transaction auto-configuration is usually enabled; in plain Spring setups, configure transaction management and PlatformTransactionManager explicitly.

## 4. Do Multiple Repositories Truly Share the Same Transaction?

A JDBC transaction covers only operations participating in the same transaction manager and compatible resource—typically the same DataSource.

Example service:

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public CheckoutService(
            OrderRepository orders,
            InventoryRepository inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void checkout(Order order) {
        orders.save(order);
        inventory.reserve(order.getProductId(), order.getQuantity());
    }
}
~~~

If both repositories share the same DataSource and transaction manager, their operations normally participate in the transaction opened by checkout.

If they use two different DataSources or transaction managers, a single standard @Transactional does not create a distributed transaction across both databases.

When multiple transaction managers exist, specify the right manager explicitly:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void checkout(Order order) {
    // Repositories must use the resources managed by this manager.
}
~~~

If atomicity across multiple databases is required, use a proper distributed mechanism or design an outbox/saga workflow with compensating actions. Never assume two repositories injected into one service automatically roll back together.

### 4.1. Propagation can commit data independently

A method using Propagation.REQUIRES_NEW opens its own independent transaction. That transaction can commit even if the outer transaction rolls back.

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentAudit(AuditRecord record) {
    auditRepository.save(record);
}
~~~

If an audit record persists after the main use case rolls back, check the propagation setting of the audit-writing method. That may be intentional configuration rather than a missed rollback.

## 5. Connection Pool Exhaustion: Application Cannot Acquire Connections

A connection pool holds a set of JDBC connections for reuse. When a request needs database access, it borrows a connection from the pool. Once the operation completes and returns the connection, other requests can reuse it.

With HikariCP, if active connections reach maximumPoolSize and no idle connections remain, callers requesting a connection wait. Once connectionTimeout expires, the pool throws SQLException.

Common causes:

- Transactions holding connections for too long.
- Queries blocked by locks or running slowly.
- Code opening connections manually without closing them.
- Unclosed ResultSets, Statements, or streams.
- Making HTTP/email calls or waiting on external work while a transaction stays open.
- Concurrent request bursts exceeding database/pool capacity.
- Tasks holding a connection while waiting on another thread or resource.

### 5.1. Distinguishing connection acquisition timeout from SQL execution timeout

These timeout types measure different things:

| Timeout | What wait does it measure? | Common configuration |
|---|---|---|
| Connection acquisition timeout | Waiting for the pool to supply a connection | Hikari connectionTimeout |
| Query timeout | How long a JDBC statement may run | JdbcTemplate.setQueryTimeout or Statement.setQueryTimeout |
| Transaction timeout | Overall transaction time limit | @Transactional(timeout = ...) |
| Lock timeout | Time spent waiting for a database lock | Database-specific configuration |
| Network/socket timeout | Time waiting on network/driver I/O | Driver or network configuration |

If logs report failure to acquire a connection from the pool, increasing query timeout will not fix the root cause. If a statement is waiting on a database lock, increasing connectionTimeout only makes requests wait longer before failing.

## 6. Monitoring HikariCP and the Connection Pool

Spring Boot Actuator exposes DataSource metrics. JDBC gauges report active, idle, maximum, and minimum connection counts. HikariCP also exposes dedicated metrics under the hikaricp prefix.

When investigating pool exhaustion, monitor:

- Active connections: connections currently borrowed.
- Idle connections: connections available to borrow.
- Maximum connections: pool size limit.
- Pending borrowers: requests waiting for a connection.
- Connection acquisition time: time spent waiting to borrow a connection.
- Connection usage time: how long connections are held.

A telltale pattern:

~~~text
active connections = maximum pool size
idle connections   = 0
pending borrowers  > 0
~~~

If this state persists, new requests stall waiting for connections. Next, determine what the connection holders are doing: running slow queries, waiting on locks, keeping transactions open too long, or leaking unclosed resources.

### 6.1. Configuring HikariCP for diagnostics

Example configuration:

~~~properties
spring.datasource.hikari.connection-timeout=30000
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.leak-detection-threshold=20000
~~~

These values merely illustrate configuration syntax; they are not universal recommendations for every app.

- connection-timeout is the max wait time to obtain a connection from the pool.
- maximum-pool-size is the maximum number of connections the pool may retain.
- leak-detection-threshold instructs Hikari to log warnings when a connection stays out of the pool longer than the threshold.

Leak detection only warns that a connection appears held too long. It does not reclaim connections still in use by the application. A legitimate long-running query can also trigger warnings if the threshold is too low.

Set the leak threshold above normal connection hold times and enable it temporarily during diagnostics if logs become noisy.

### 6.2. Do not increase pool size blindly

Increasing maximumPoolSize can help when the pool is genuinely undersized for the workload, but it can also push higher concurrency onto the database and worsen lock contention.

Before enlarging the pool:

1. Measure active/idle/pending counts.
2. Measure connection hold times.
3. Identify slow queries or long transactions.
4. Check the database's connection limit.
5. Assess how much concurrency the database can actually sustain.
6. Adjust pool size only after gathering metrics.

Pool size is part of system-wide concurrency limits, not a magic performance dial.

## 7. Finding Connection Leaks in Code

When using JdbcTemplate or NamedParameterJdbcTemplate, Spring manages acquiring and releasing connections for standard JDBC operations.

When calling JDBC APIs directly, close resources properly:

~~~java
public List<Customer> loadCustomers(DataSource dataSource)
        throws SQLException {

    String sql = "SELECT id, name FROM customers";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql);
         ResultSet resultSet = statement.executeQuery()) {

        List<Customer> result = new ArrayList<>();

        while (resultSet.next()) {
            result.add(new Customer(
                    resultSet.getLong("id"),
                    resultSet.getString("name")
            ));
        }

        return result;
    }
}
~~~

Try-with-resources ensures ResultSet, Statement, and Connection are closed when leaving the block, even if an exception occurs.

Inside code participating in a Spring transaction, do not open independent connections if the work should share the transaction. Prefer JdbcTemplate or Spring-managed connection acquisition/release such as DataSourceUtils, following the transaction manager's contract.

### 7.1. Streams and large result sets

Some APIs return a Stream to read rows incrementally. A Stream can hold onto JDBC resources until closed.

Example:

~~~java
try (Stream<Order> orders = aggregateTemplate.streamAll(Order.class)) {
    orders.forEach(this::process);
}
~~~

If closing is omitted, the connection may stay borrowed long after the caller finishes processing rows. Always use try-with-resources with JDBC-backed streams.

### 7.2. Do not hold connections across external system calls

An example prone to pool exhaustion:

~~~java
@Transactional
public void register(Customer customer) {
    customers.save(customer);

    emailClient.sendWelcomeEmail(customer);
    paymentClient.verifyAccount(customer);
}
~~~

While HTTP calls wait for responses, the transaction may keep holding a database connection and locks. If external services slow down, many concurrent requests hold connections far longer than usual.

Keep transactions focused on atomic database operations. Write an outbox record inside the transaction and dispatch notifications from a worker after commit if reliable side effects are needed.

## 8. Hanging Queries: Connection Acquired, Statement Never Finishes

Once a connection is acquired, pinpoint where time is being spent:

1. The database is waiting on a lock.
2. The query is running with a poor execution plan.
3. The query scans or returns too many rows.
4. The JDBC driver is waiting on a network/database response.
5. The application is consuming the ResultSet slowly.
6. A transaction holds locks while waiting on another operation.

A query that appears frozen does not necessarily mean the database is unresponsive. It may simply be blocked waiting for another transaction to release a lock.

### 8.1. Lock wait

Example transaction A:

~~~sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;
-- Transaction A has not committed yet.
~~~

Transaction B:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;
~~~

Transaction B must wait for transaction A to release its lock on the inventory row. If A keeps the transaction open too long, B and other requests queue up blocked.

Common causes:

- Long-running open transactions.
- Updating multiple rows in inconsistent order across requests.
- Non-database calls occurring inside transactions.
- Queries locking broader row ranges than needed.
- Deadlocks among competing transactions.

### 8.2. Inspecting waiting queries in PostgreSQL

PostgreSQL provides pg_stat_activity and pg_blocking_pids to inspect active sessions and what blocks them.

Example:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS duration,
    query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
~~~

To find blocked sessions and their blockers:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity blocked
JOIN pg_stat_activity blocker
    ON blocker.pid = ANY(pg_blocking_pids(blocked.pid));
~~~

These queries are specific to PostgreSQL. Other databases have their own lock-diagnostic views and tools. Do not run PostgreSQL-specific SQL on MySQL or SQL Server without adapting it.

## 9. Setting Timeouts for Queries and Transactions

Never let requests wait indefinitely when a statement might block or run too long.

### 9.1. Query timeout with JdbcTemplate

JdbcTemplate supports setQueryTimeout, measured in seconds:

~~~java
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    JdbcTemplate jdbc = new JdbcTemplate(dataSource);
    jdbc.setQueryTimeout(5);
    return jdbc;
}
~~~

The default value is -1, meaning no explicit query timeout is passed to the JDBC driver. The driver is responsible for enforcing timeouts per the JDBC contract; verify actual behavior against your driver and database.

If a transaction already has a timeout, the remaining transaction time can override the timeout configured directly on JdbcTemplate.

### 9.2. Transaction timeout

You can configure a timeout for a use case:

~~~java
@Transactional(timeout = 10)
public void updateOrder(Long orderId) {
    // Database operations for the use case.
}
~~~

Transaction timeout bounds transaction duration as supported by the transaction manager. For JDBC, remaining time can be propagated to Spring-managed statements.

Transaction timeout is not the same as HikariCP connection acquisition timeout, nor does it replace database socket timeouts or lock timeouts.

### 9.3. Database-specific lock timeouts

Some databases support configuring maximum lock wait durations. For example, PostgreSQL provides lock_timeout and statement_timeout parameters.

These timeouts operate at distinct scopes:

- lock_timeout limits how long a statement waits for locks.
- statement_timeout limits how long a statement executes.
- JDBC query timeout passes a timeout request through the driver.
- transaction timeout applies to the overall transaction.

Do not set every timeout to the same number without considering how they interact. Design them so blocked operations fail within bounded time and the application can handle the resulting exceptions cleanly.

## 10. Reading Thread Dumps and Logs to Locate Where Execution Waits

When requests hang, thread dumps show which layer threads are stalled in.

Common indicators:

| Stack trace / symptom | Likely situation |
|---|---|
| Thread in HikariPool.getConnection | Waiting for the pool to supply a connection |
| Thread in PreparedStatement.execute or driver socket read | Connection acquired, waiting on statement/driver |
| Thread waiting on monitor/lock in app code | Likely blocked by internal synchronized/lock contention |
| Thread reading ResultSet or mapping many entities | Processing a large result set |
| Thread waiting on HTTP client inside an open transaction | Connection likely held during external service call |

A thread dump is only a single snapshot in time. Capture multiple dumps spaced slightly apart and correlate them with SQL logs, database sessions, and pool metrics.

A thread repeatedly parked at the same frame is much stronger evidence than a single isolated stack trace.

## 11. Distinguishing Deadlock, Lock Wait, and Slow Queries

| Failure type | Symptom | Investigation approach |
|---|---|---|
| Lock wait | Statement waits for another transaction to release a lock | Inspect blocking sessions and transaction durations |
| Deadlock | Database detects a wait cycle and aborts one transaction | Inspect SQLState/vendor code and deadlock reports |
| Slow query | Statement runs actively, burning CPU/I/O or scanning many rows | Inspect execution plan, indexes, and rows scanned |
| Connection pool starvation | Requests fail to acquire connections | Inspect active/idle/pending counts and connection usage time |
| Network/driver wait | Statement sent, client waits for response | Check driver logs, network timeouts, and database health |
| Slow result processing | Database returns rows, app takes long to read/map | Inspect rows returned, fetch size, mapping, and heap |

Do not try to fix deadlocks merely by increasing query timeouts. Deadlocks are lock-ordering conflicts that require consistent update ordering, shorter transactions, or bounded retries.

## 12. Common Pitfalls

| Symptom | Possible cause | Fix |
|---|---|---|
| Service throws checked exception yet data commits | Default rollback rules skip checked exceptions | Use rollbackFor when business rules require rollback |
| Exception caught and method completes normally | Transaction was not marked rollback-only | Rethrow exception or explicitly mark rollback |
| @Transactional has no effect on internal call | Self-invocation bypasses proxy | Place transaction on entry method or extract bean |
| Different repositories fail to roll back together | Different DataSources/transaction managers | Share resource or design distributed workflow |
| Audit record remains after rollback | Audit method uses REQUIRES_NEW | Clarify which data should commit independently |
| Hikari reports connection timeout | Pool ran out of idle connections | Inspect active, idle, pending, and connection hold times |
| Continuous leak detection warnings | Connections held too long or unclosed resources | Check acquire stack traces and close resources |
| Pool exhausted when streaming data | Unclosed Stream/ResultSet | Use try-with-resources |
| Requests wait despite idle database | Threads waiting on pool or external services | Inspect thread dumps and connection acquisition |
| Query timeout does not stop request | Timeout not applied at waiting layer or driver behaves differently | Distinguish pool/query/lock/socket timeouts and test driver |
| Increasing maximumPoolSize slows database further | Excessive concurrency and lock contention | Measure DB load, shorten transaction durations |
| Query hangs due to lock | Another transaction has not committed/rolled back | Find blocking session and shorten transactions |
| Random deadlocks occur | Transactions lock rows in differing orders | Standardize update ordering and add bounded retries |
| SQL is slow even without locks | Poor execution plan or missing index | Run EXPLAIN and measure rows scanned |
| Transaction holds connection while sending email | External I/O inside transaction | Move side effects post-commit or use outbox |

## 13. Step-by-Step Diagnostic Workflow

When receiving reports of "write request hanging" or "transaction not rolling back", follow these steps:

1. Identify which stage fails or stalls: before acquiring a connection, during SQL execution, while reading results, or during commit.
2. Capture full exceptions, including root causes, SQLState, and vendor error codes.
3. Inspect transaction boundaries, rollbackFor/noRollbackFor, self-invocation, and transaction managers.
4. Check pool metrics: active, idle, maximum, pending, and acquisition times.
5. Enable leak detection temporarily if unclosed connections are suspected.
6. Capture thread dumps to distinguish pool waits, driver waits, and ResultSet processing.
7. Inspect database sessions, lock waits, and blocking transactions.
8. Inspect execution plans, rows scanned/returned, and statement durations.
9. Configure query/transaction/lock timeouts suited to the use case and driver.
10. Re-run concurrent scenarios and confirm data, connections, and locks are released properly.

Record start/end timestamps, request IDs, transaction boundaries, and query fingerprints so application logs correlate cleanly with database sessions.

## 14. Practice Exercises

### Exercise 1 — Checked Exception Not Rolling Back

Create a service that saves an Order and throws IOException. Inspect the data afterward. Add rollbackFor and compare results.

### Exercise 2 — Swallowed Exception

Create a service that saves an Order, catches an exception from InventoryRepository, and does not rethrow. Confirm the transaction can commit. Then wrap it in a runtime exception and verify rollback.

### Exercise 3 — Self-Invocation

Create a service whose outer method calls an inner transactional method using this. Observe transaction behavior, then extract the method into another bean and compare.

### Exercise 4 — Small Connection Pool

Configure a small pool in a test environment and launch concurrent requests holding connections. Observe active, idle, pending counts, and connection acquisition timeouts.

### Exercise 5 — Connection Leak

Write JDBC code that opens a connection without closing it. Enable leakDetectionThreshold and observe warnings. Fix it with try-with-resources and re-run.

### Exercise 6 — Query Blocked by Lock

Open two transactions touching the same row. Keep the first transaction uncommitted, run an UPDATE in the second, and observe the lock wait in the database.

### Exercise 7 — Query Timeout

Set a query timeout on JdbcTemplate. Execute an intentionally slow query in a test database and observe the exception. Compare with HikariCP's connectionTimeout.

### Exercise 8 — Transaction Timeout

Set @Transactional(timeout = 5) on a multi-statement use case. Observe remaining time propagated to JDBC operations and compare with query timeout.

### Exercise 9 — PostgreSQL Lock Diagnostics

Run two transactions competing on the same row. Use pg_stat_activity and pg_blocking_pids to identify both blocked and blocking sessions.

### Exercise 10 — Pool Metrics and Concurrent Load

Enable Spring Boot Actuator/Micrometer and monitor jdbc.connections and Hikari metrics during a small load test. Compare connection usage times before and after moving an HTTP call outside the transaction.

## 15. Key Takeaways

- Transactions failing to roll back typically involve rollback rules, swallowed exceptions, proxy/self-invocation, or mismatched transaction managers/resources.
- Spring rolls back by default on RuntimeException and Error; checked exceptions require rollbackFor if business rules demand rollback.
- In proxy mode, self-invocation bypasses the transaction interceptor.
- Multiple repositories roll back together only when participating in the same transaction manager and compatible resource.
- Connection pool timeout measures time spent waiting to borrow a connection, not SQL execution time.
- Hikari leak detection only warns when connections are held past a threshold; it does not reclaim connections.
- Track active, idle, maximum, pending counts, and connection usage times to spot pool starvation.
- Use JdbcTemplate or try-with-resources to manage JDBC resources; close Streams when APIs hold open resources.
- Queries that already hold a connection yet hang may be waiting on locks, running slow queries, reading large results, or waiting on driver/network I/O.
- Distinguish query timeout, transaction timeout, lock timeout, socket timeout, and connection acquisition timeout.
- Do not increase pool sizes or timeouts before pinpointing where execution waits and why.
- Combine thread dumps, SQL logs, database session/lock views, and pool metrics to find root causes.

## References

- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [Spring Boot — SQL Databases and Connection Pools](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
