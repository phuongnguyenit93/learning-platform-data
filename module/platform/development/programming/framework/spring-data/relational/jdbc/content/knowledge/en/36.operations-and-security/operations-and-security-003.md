# Setting Timeouts for Connections, Queries, and Transactions

In an application using **Spring Data Relational JDBC (Spring Data JDBC)**, a request may wait to acquire a connection, execute one or more SQL statements, wait for locks held by another transaction, and complete a commit. Without appropriate limits, a request can hold threads and connections for too long, exhausting the connection pool and forcing other requests to wait.

Spring Boot, Spring Framework, JDBC drivers, and databases each provide timeout mechanisms, but each mechanism controls a different stage:

- **Connection acquisition timeout:** limits how long to wait to borrow a connection from the pool.
- **Connection establishment timeout:** limits how long the driver waits to connect to the database over the network.
- **Query/statement timeout:** limits how long a single SQL statement can execute.
- **Transaction timeout:** limits how long a transaction is allowed to remain active.
- **Database lock/statement timeout:** limits how long to wait on locks or execute on the database side.

No single timeout property automatically covers all stages. This lesson explains how to configure each layer, how Spring Data JDBC uses JDBC settings, how timeouts interact, and how to handle expirations.

## 1. Map of Timeout Types

A typical request flow:

~~~mermaid
flowchart TD
    Request["HTTP request"]
    Pool["Acquire connection from pool<br/>Hikari connectionTimeout"]
    Driver["Open connection to DB<br/>Driver connectTimeout"]
    Tx["Start transaction<br/>Transaction timeout"]
    SQL["Execute SQL statement<br/>Statement queryTimeout"]
    Lock["Wait for database lock<br/>DB lock_timeout"]
    Commit["Commit / rollback"]
    Response["Return response"]
    Request --> Pool --> Driver --> Tx --> SQL
    SQL --> Lock --> SQL
    SQL --> Commit --> Response
~~~

Timeouts can overlap. For example, if 3 seconds remain on the transaction timeout while query timeout is configured to 8 seconds, Spring can set the statement timeout to the **remaining time of the transaction**, so the SQL statement is not allowed to consume the full 8 seconds. Conversely, if there is no transaction timeout, the query timeout can act as the primary limit for the statement.

| Timeout type | What is bounded | Where usually configured |
|---|---|---|
| Connection pool wait | Time waiting for an idle connection | HikariCP |
| Network/driver connect | Time to open socket and log in to the database | JDBC driver |
| Query/statement | A single SQL statement | JdbcTemplate, JDBC Statement, driver |
| Transaction | A Spring-managed transaction | @Transactional, TransactionTemplate, Boot properties |
| Lock wait | Time waiting for a lock in the database | Database session/role/database configuration |

## 2. Timeout When Acquiring Connections from HikariCP

Spring Boot typically uses HikariCP when Hikari is on the classpath. HikariCP's **connectionTimeout** property is the maximum time a thread waits to **borrow a connection from the pool**.

When the pool has reached **maximumPoolSize** and no idle connection is available, a thread calling DataSource.getConnection() must wait. If connectionTimeout is exceeded, HikariCP throws an error rather than waiting indefinitely.

Example configuration:

~~~properties
spring.datasource.hikari.connection-timeout=2000
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.validation-timeout=1000
~~~

In this example:

- connection-timeout=2000 sets a maximum of 2,000 milliseconds (2 seconds) waiting for a connection from the pool.
- maximum-pool-size=20 caps the total number of idle and in-use connections.
- validation-timeout=1000 limits how long a connection liveness check can take; this value must be smaller than connection-timeout.

HikariCP defaults connectionTimeout to 30,000 ms. The minimum accepted value is 250 ms. HikariCP duration values use milliseconds.

### Connection Timeout Is Not Database Network Connect Time

The name connectionTimeout can be misleading. It primarily bounds waiting for a connection from the pool. When the pool needs to open a new physical connection, the JDBC driver has its own separate timeout for the network connection step.

PostgreSQL JDBC example:

~~~properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/orders?connectTimeout=3
~~~

pgJDBC's connectTimeout is specified in seconds and limits how long opening a socket to the server can take. The current driver default is 10 seconds; a value of 0 means unlimited.

MySQL Connector/J example:

~~~properties
spring.datasource.url=jdbc:mysql://db.example.internal:3306/orders?connectTimeout=3000
~~~

MySQL Connector/J's connectTimeout is specified in milliseconds; the default is 0, meaning unlimited.

Units and property names depend on the driver. Do not copy connectTimeout=3 from PostgreSQL to MySQL and assume it still means 3 seconds.

### Other Pool Properties That Are Not Query Timeouts

| HikariCP property | Meaning |
|---|---|
| connectionTimeout | Waiting to borrow a connection from the pool |
| validationTimeout | Maximum time to validate a connection |
| idleTimeout | How long a connection can sit idle before being eligible for removal |
| maxLifetime | Maximum lifetime of a connection in the pool |
| keepaliveTime | Interval to test/keep idle connections alive |
| maximumPoolSize | Maximum number of connections in the pool |

maxLifetime should be slightly shorter than any connection lifetime limit enforced by the database, proxy, or network infrastructure. It does not limit how long a query runs or how long a transaction stays open.

## 3. Timeouts for Queries and JDBC Statements

JDBC provides Statement.setQueryTimeout(int seconds). This is the statement execution time limit in seconds. If exceeded, the driver may cancel the query or report a timeout error; actual cancellation behavior depends on the JDBC driver and database.

Spring JdbcTemplate has a queryTimeout property:

~~~java
JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
jdbcTemplate.setQueryTimeout(5);
~~~

Here 5 means 5 seconds. The default for JdbcTemplate is -1, meaning no explicit timeout is passed to the JDBC driver and the driver's default applies.

### Configuring with Spring Boot

Spring Boot provides the property:

~~~properties
spring.jdbc.template.query-timeout=5s
~~~

This property sets the default query timeout for the Boot-configured JdbcTemplate. Duration suffixes such as ms, s, or m can be used; without a suffix, the unit is seconds.

Example:

~~~properties
# 5 seconds
spring.jdbc.template.query-timeout=5s

# 750 milliseconds
spring.jdbc.template.query-timeout=750ms
~~~

If the application uses NamedParameterJdbcTemplate, it usually delegates to a JdbcTemplate underneath. Spring Data JDBC uses JDBC abstractions such as NamedParameterJdbcOperations for many persistence operations, so this Boot property typically affects statements routed through the auto-configured template.

If the application manually constructs its own NamedParameterJdbcOperations, JdbcTemplate, or DataAccessStrategy, check the timeout configuration on the instance actually used by Spring Data JDBC. The property does not automatically configure Statements created directly via the raw JDBC API.

### Configuring a Timeout for an Individual Statement

When different limits are needed for specific custom queries, you can set the timeout on the statement:

~~~java
public List<Order> findSlowReport(
        JdbcTemplate jdbcTemplate,
        String status) {

    return jdbcTemplate.query(connection -> {
        PreparedStatement statement = connection.prepareStatement("""
            SELECT id, customer_id, status
            FROM orders
            WHERE status = ?
            """);
        statement.setString(1, status);
        statement.setQueryTimeout(3);
        return statement;
    }, (resultSet, rowNumber) -> new Order(
        resultSet.getLong("id"),
        resultSet.getLong("customer_id"),
        resultSet.getString("status")
    ));
}
~~~

This code illustrates setting a timeout on a specific PreparedStatement. In real applications, reuse RowMappers and constructors suited to the domain model. When using JdbcTemplate or Spring Data JDBC, prefer letting Spring manage connections and transactions rather than opening connections manually outside a transaction context.

## 4. Transaction Timeouts with @Transactional

A transaction can execute multiple SQL statements. Even if each SQL statement has a 5-second timeout, a transaction containing many statements can stay active for much longer than 5 seconds if you rely only on query timeout.

Spring lets you set a timeout on a transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(timeout = 10)
    public void confirmOrder(Long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.confirm();
        orders.save(order);
    }
}
~~~

timeout = 10 is measured in seconds. The transaction manager uses this value to bound the transaction; with a JDBC transaction manager, the remaining transaction time can be applied to statements created through the Spring JDBC infrastructure.

@Transactional timeout only applies to REQUIRED or REQUIRES_NEW propagation. If a method joins an existing REQUIRED transaction, the active transaction keeps its existing timeout; declaring a timeout on an inner method does not reset the outer transaction's timer.

### Default Transaction Timeout

You can configure a default timeout in Spring Boot:

~~~properties
spring.transaction.default-timeout=10s
~~~

This property sets the default timeout on the Boot-configured transaction manager if that transaction manager supports timeouts. A method annotated with @Transactional(timeout = ...) can declare its own timeout for use cases needing a different limit.

### Using TransactionTemplate

For programmatic transactions, you can configure the timeout on TransactionTemplate:

~~~java
TransactionTemplate transactionTemplate =
    new TransactionTemplate(transactionManager);

transactionTemplate.setTimeout(10);

transactionTemplate.execute(status -> {
    Order order = orders.findById(orderId).orElseThrow();
    order.confirm();
    orders.save(order);
    return null;
});
~~~

TransactionTemplate.setTimeout(10) also uses seconds. This is appropriate when a block of code needs an explicit transaction boundary without annotations.

### Transaction Timeout Is Not a Thread-Killing Timer

Transaction timeout does not arbitrarily stop every Java operation inside the method:

- It does not automatically cancel HTTP calls or non-database tasks.
- It does not guarantee stopping a long CPU loop.
- It only takes full effect with the transaction manager and participating resources.
- JDBC statements created outside a Spring-managed connection may not receive the remaining transaction timeout.

With JDBC, use JdbcTemplate, NamedParameterJdbcTemplate, repositories, or connections obtained through Spring's transaction-aware infrastructure so timeouts are applied properly.

## 5. Relationship Between Query Timeout and Transaction Timeout

Spring JDBC applies the remaining transaction timeout when creating statements inside a transaction. If less time remains on the transaction timeout than the query timeout configured on the template, the remaining transaction time is used.

Example:

~~~text
JdbcTemplate query timeout: 8 seconds
Transaction timeout:       5 seconds

Transaction starts
  Query 1 runs for 2 seconds
  Query 2 starts, ~3 seconds remain in transaction
  Query 2 receives timeout based on remaining time
~~~

This prevents every query within the same transaction from claiming the full query timeout when the transaction is already close to expiring.

| Query timeout | Transaction timeout | Expected behavior |
|---:|---:|---|
| 5 seconds | Not set | Statement uses the 5-second query timeout |
| 8 seconds | 4 seconds | Statements in the transaction are bounded by remaining transaction time |
| 3 seconds | 10 seconds | A statement may hit the query timeout before the transaction expires |
| Not set | 10 seconds | Spring can apply remaining transaction time to statements via Spring JDBC |

This is Spring JDBC's behavior with properly managed connections and statements. The specific driver and transaction manager still affect when expiration is detected and how statements are cancelled.

## 6. Database-Side Timeouts

Application-layer and driver-layer timeouts are not always enough. A database may continue executing a statement after the client times out, or a client may disconnect without the query being cancelled immediately. Database-side timeouts limit work directly on the server.

### PostgreSQL

PostgreSQL provides several useful parameters:

| Parameter | Meaning |
|---|---|
| statement_timeout | Limits total statement execution time |
| lock_timeout | Limits time spent waiting for locks |
| idle_in_transaction_session_timeout | Closes sessions that remain idle in a transaction too long |

These can be configured per database, role, or session. Example applied within a single transaction:

~~~sql
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
~~~

SET LOCAL takes effect for the current transaction. This is PostgreSQL-specific configuration; do not use this syntax on MySQL or other databases.

### MySQL

MySQL has its own mechanisms:

- innodb_lock_wait_timeout limits time spent waiting for InnoDB row locks.
- max_execution_time can limit execution time for certain SELECT statements.
- Connector/J provides connectTimeout and socketTimeout for network connections.

Each setting has its own scope and units. Read the documentation for your exact MySQL and Connector/J versions before choosing values.

### Driver Socket Timeout

Socket timeout limits how long reading data from a socket can block. It can detect hung network connections, but it is not the same as a query timeout:

- Query timeout controls statement execution time per JDBC.
- Socket timeout controls network read operations.
- Connection timeout controls connection establishment or pool waiting depending on the specific setting.

PostgreSQL JDBC example:

~~~properties
spring.datasource.url=jdbc:postgresql://db:5432/orders?connectTimeout=3&socketTimeout=12
~~~

In pgJDBC, connectTimeout and socketTimeout are in seconds. socketTimeout can close the connection when reading from the server takes too long; do not set it too low if the application runs valid queries returning large datasets or taking longer to stream.

MySQL Connector/J example:

~~~properties
spring.datasource.url=jdbc:mysql://db:3306/orders?connectTimeout=3000&socketTimeout=12000
~~~

In Connector/J, both properties are in milliseconds. Different units across drivers are a key reason to check driver documentation before copying configuration.

## 7. A Multi-Layer Timeout Configuration

Illustrative example for a Spring Boot application using HikariCP and Spring Data JDBC:

~~~properties
# Wait at most 2 seconds to acquire a connection from the Hikari pool
spring.datasource.hikari.connection-timeout=2000

# Validate connections for at most 1 second
spring.datasource.hikari.validation-timeout=1000

# Default 5-second timeout for each JDBC template statement
spring.jdbc.template.query-timeout=5s

# Default 10-second timeout for transactions
spring.transaction.default-timeout=10s
~~~

This example illustrates the configuration layers, not universal values for every application. Choose values based on API latency budgets, pool sizes, actual query durations, and business requirements.

You can set a specific timeout for an individual use case:

~~~java
@Transactional(timeout = 4)
public Order loadOrderForConfirmation(Long id) {
    return orders.findById(id).orElseThrow();
}
~~~

This method uses a 4-second transaction timeout, shorter than the 10-second default in the configuration above.

## 8. Designing Timeouts Around a Request Budget

Timeouts should be designed from the outermost limit inward. Suppose an API has a 5-second deadline:

| Layer | Illustrative limit | Goal |
|---|---:|---|
| HTTP/request deadline | 5 seconds | Avoid holding requests too long |
| Connection pool wait | 300 ms | Detect pool saturation early |
| Transaction | 3 seconds | Cap database work for the use case |
| Default query | 2 seconds | Stop an abnormally slow statement |
| Database lock wait | 500 ms | Avoid waiting on locks too long |

These numbers are only examples to illustrate budget ordering. Transaction timeout encompasses the time of statements participating in the transaction; do not add the values together into a simple sum.

Key principles:

- Inner timeouts should be smaller than the request deadline to leave time for rollback, logging, and returning a response.
- Connection pool timeout must be short enough that pool exhaustion does not tie up all request threads.
- Query timeout must be based on actual latency distributions, not set so low that valid queries are routinely cancelled.
- Transaction timeout should reflect the use-case length; avoid keeping transactions open while waiting on users, HTTP calls, or message brokers.
- Lock timeout can be shorter than statement timeout so transactions handle contention quickly.
- Socket timeout must account for transferring large results and network characteristics.

## 9. Timeouts, Retries, and Idempotency

A timeout does not prove the database failed to execute the operation. For example, a client sends an INSERT, the database executes it successfully, and the connection drops before the client receives the result. The application sees a timeout, yet the commit outcome is ambiguous.

Therefore:

- Never blindly retry non-idempotent write operations.
- Use an idempotency key or unique business key when a command can be resent.
- If a transaction timed out and rollback is confirmed, retries can be evaluated per business policy.
- For network errors after sending commit, verify state using a business key or reconciliation mechanism.
- Cap retry attempts and use backoff with jitter to avoid overloading the database further.

For example, a payment creation command must not be re-sent simply because the client missed the response. The system needs an idempotency key or a status lookup before executing again.

## 10. Connection Pool Exhaustion and Connection Hold Time

Pool exhaustion is usually a symptom of holding connections too long or having more concurrent requests than the database/pool can serve.

Common causes:

- Slow queries or missing indexes.
- Transactions containing non-database work.
- Code forgetting to close streams/result sets or manually managed connections.
- Pool size too small for actual concurrency.
- Database slowdown, lock contention, or increased network latency.
- Connection leaks.

HikariCP can configure leak detection to log connections held longer than a threshold:

~~~properties
spring.datasource.hikari.leak-detection-threshold=20000
~~~

The value is in milliseconds. Leak detection is a diagnostic tool, not a timeout mechanism that forcibly frees every connection in use. Do not set the threshold too low in production if it produces false positives.

Monitor these indicators:

- Active connections.
- Idle connections.
- Pending threads waiting for connections.
- Connection acquisition latency.
- Query latency and timeout counts.
- Transaction duration.
- Lock waits/deadlocks.

Increasing maximumPoolSize is not a default cure. A larger pool can push more concurrent queries onto an already saturated database and worsen latency.

## 11. Handling Timeout Errors in Spring

JDBC drivers typically throw SQLException or SQLTimeoutException. Spring translates many JDBC errors into the DataAccessException hierarchy.

Exceptions you may encounter:

| Situation | Common exception |
|---|---|
| Unable to borrow connection from pool | CannotGetJdbcConnectionException or DataAccessResourceFailureException |
| Query timed out | QueryTimeoutException or a DataAccessException subtype depending on driver |
| Transaction timed out | Exception from transaction manager or data access error when statement expires |
| Connection lost/socket timeout | DataAccessResourceFailureException or exception translated from SQLException |

Do not simply catch Exception and return an empty result. Distinguish retryable timeout errors, data errors, constraint errors, and business errors.

Example handling at the API layer:

~~~java
@RestControllerAdvice
public class DatabaseExceptionHandler {

    @ExceptionHandler(QueryTimeoutException.class)
    @ResponseStatus(HttpStatus.GATEWAY_TIMEOUT)
    public ApiError handleQueryTimeout(QueryTimeoutException exception) {
        return new ApiError(
            "DATABASE_QUERY_TIMEOUT",
            "The database query took too long. Please retry later."
        );
    }
}
~~~

HTTP 504 can be appropriate when the application fails to complete an operation due to a database dependency timeout. Some systems choose 503 for database overload or unavailability. Align error mappings with your API contract and gateway/load balancer.

Note that driver-specific exceptions may be translated into different subtypes. In production systems, log the exception chain and SQL state to pinpoint the exact cause.

## 12. Common Configuration Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking Hikari's connectionTimeout is network connect timeout | Driver may still wait long to open sockets | Configure driver connectTimeout separately |
| Setting only query timeout | A multi-query transaction can still stay open too long | Add a transaction timeout |
| Setting transaction timeout while opening raw JDBC connections manually | Statements may not receive remaining timeout | Use Spring-managed DataSource/connections |
| Confusing seconds and milliseconds | Timeouts far too short or too long | Check the unit of every property/driver |
| Setting socketTimeout too low | Valid queries or large result sets get cut off mid-stream | Choose based on read time and driver behavior |
| Assuming query timeout always cancels server statements immediately | Database may keep executing or cancellation depends on driver | Also configure database-side timeouts |
| Setting transaction timeout too short | Valid transactions routinely roll back | Measure latency and set a realistic budget |
| Holding transactions open during HTTP calls | Pool exhausts when external services slow down | Never keep transactions open while waiting on external systems |
| Increasing pool size to fix timeouts | Database may become more overloaded | Inspect queries, locks, and connection hold time |
| Retrying every timeout | Can duplicate writes or execute commands twice | Use idempotency and controlled retries |
| Assuming timeout always means rollback | Commit outcome can be unknown on network drop | Reconcile state using a business key |
| Confusing maxLifetime with query timeout | Connections retire without bounding running queries | Use the right timeout type for each stage |

## 13. Testing Timeouts

Timeouts should be tested across multiple layers:

### Testing Query Timeout

With databases supporting sleep statements, you can use an intentionally slow query in integration tests. PostgreSQL example:

~~~sql
SELECT pg_sleep(3);
~~~

Set the query timeout lower than the sleep duration and verify the application receives a timeout error. Use such statements only in a dedicated test database.

### Testing Transaction Timeout

Create a transactional use case with multiple statements or one slow statement. Set @Transactional(timeout = 1) and verify the transaction does not commit when the limit enforced by the transaction manager is exceeded.

Do not use Thread.sleep() as sole proof of transaction timeout: it only blocks the Java thread and does not necessarily make the transaction manager cancel non-JDBC work immediately.

### Testing Pool Acquisition Timeout

In an isolated test, configure a tiny pool, hold a connection in one transaction, and have another thread request a connection. Verify the second thread receives the configured timeout error. Ensure the test releases connections and does not affect other tests.

### Testing Driver/Network Timeout

Do not point normal test suites at an unresponsive database address because results depend on DNS, firewalls, and infrastructure. Use a dedicated integration environment or proxy/network fault injection to test connectTimeout and socketTimeout.

## 14. Configuration Workflow in a Spring Data JDBC Application

1. Define the request deadline and use-case latency budget.
2. Identify which pool the DataSource uses; if HikariCP, set connection acquisition timeout.
3. Set JDBC driver connect timeout to bound physical connection opening.
4. Configure spring.jdbc.template.query-timeout for statements going through the auto-configured template.
5. Set a default transaction timeout with spring.transaction.default-timeout if appropriate.
6. Use @Transactional(timeout = ...) for use cases with specific requirements.
7. Configure database-side statement_timeout/lock_timeout if server-side protection is needed.
8. Ensure timeouts across layers follow a logical order and do not conflict with the request deadline.
9. Monitor pool metrics, query latency, transaction duration, and timeout counts.
10. Test successful timeouts, rollbacks, and uncertain outcomes after network errors.

## 15. Practice Exercises

1. Build a Spring Data JDBC application using HikariCP and observe connection wait time when the pool has no idle connections left.
2. Set spring.datasource.hikari.connection-timeout=1000; simulate pool saturation and observe the error.
3. Set spring.jdbc.template.query-timeout=2s; run a test query taking longer than 2 seconds.
4. Write a service with @Transactional(timeout = 5) and execute multiple SQL statements inside one transaction.
5. Set a query timeout longer than the transaction timeout; observe statements being bounded by the remaining transaction time.
6. Configure spring.transaction.default-timeout=8s and override one method with @Transactional(timeout = 3).
7. Try connectTimeout on PostgreSQL and MySQL Connector/J; note the unit differences.
8. Using a PostgreSQL test container, try SET LOCAL statement_timeout and SET LOCAL lock_timeout.
9. Trigger a query timeout and verify the transaction rolls back when the error occurs.
10. Simulate a client disconnect after sending a write command; design a status check to prevent retries from creating duplicate data.
11. Observe Hikari active/idle/pending metrics and diagnose the cause of pool exhaustion.
12. Write an exception handler distinguishing query timeout, connection acquisition failure, and data errors.

## 16. Takeaways

Configuring timeouts for Spring Data JDBC must span multiple stages. Hikari connectionTimeout bounds waiting to borrow a connection from the pool; JDBC driver connectTimeout bounds opening a physical connection; JdbcTemplate query timeout bounds a single statement; transaction timeout bounds a Spring-managed transaction. Databases can also enforce statement timeouts and lock timeouts to protect server-side resources.

Spring Boot provides spring.datasource.hikari.connection-timeout, spring.jdbc.template.query-timeout, and spring.transaction.default-timeout. Individual use cases can specify timeouts via @Transactional(timeout = ...). Always check time units, the driver in use, and whether connections participate in Spring transactions. Combine timeouts with observability, error handling, and idempotency; timeouts limit waiting time, but do not by themselves prove a write operation failed to commit.

## References

- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework — Declarative Transaction Annotations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP)
- [PostgreSQL JDBC — Connection Parameters](https://jdbc.postgresql.org/documentation/use/)
- [MySQL Connector/J — Networking Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-networking.html)
