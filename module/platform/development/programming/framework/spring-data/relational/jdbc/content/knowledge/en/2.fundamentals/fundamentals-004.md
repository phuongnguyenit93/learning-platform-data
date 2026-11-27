# DataSource, Connection Pool, and Database Access Costs

In an application using **Spring Data JDBC**, every data read or write ultimately passes through a JDBC connection to send SQL statements to a relational database. Understanding `DataSource`, connection pools, and the cost of each access explains why an apparently simple SQL query can still be slow, why an application runs out of connections under heavy request traffic, and why increasing the pool size does not always improve performance.

This lesson focuses on the fundamentals you need to know before using `CrudRepository`, `JdbcTemplate`, `JdbcClient`, and transactions in Spring Data JDBC.

## 1. From Repository Call to Database

A data access flow typically looks like this:

~~~text
HTTP request / job / message handler
          |
          v
       Service
          |
          +---- Spring Transaction Manager (if @Transactional is present)
          |
          v
Spring Data JDBC Repository / JdbcClient / JdbcTemplate
          |
          v
      DataSource
          |
          v
Connection pool (typically HikariCP in Spring Boot)
          |
          v
JDBC Driver (e.g., PostgreSQL JDBC Driver)
          |
          v
Database server
~~~

The components in the diagram handle distinct responsibilities:

| Component | Role | Key Point to Remember |
| --- | --- | --- |
| `DataSource` | API providing `java.sql.Connection` to data access code | It is the source of connections, not a connection itself. |
| `Connection` | JDBC communication session with the database, used to run SQL and manage transactions | When obtained from a pool, the returned object is usually a *proxy* wrapping the physical connection. |
| Connection pool | Retains and reuses physical connections; limits how many connections can be borrowed concurrently | A pool reduces connection creation overhead, but does not directly make SQL run faster. |
| JDBC Driver | Translates JDBC operations into the wire protocol of the DBMS | The driver depends on the database engine, such as PostgreSQL or MySQL. |
| `JdbcClient` / `JdbcTemplate` | Provides APIs for executing SQL, binding parameters, and managing JDBC resources | Usually acquires and releases connections according to Spring's transaction context. |
| Spring Data JDBC Repository | Maps aggregates and provides repository operations per the Spring Data model | Uses Spring JDBC infrastructure underneath; not a JPA/ORM with a persistence context. |

For example, calling `orderRepository.findById(42L)` may result in one or more SQL statements depending on the aggregate structure and how Spring Data JDBC loads data. Repositories make coding convenient, but **do not eliminate database communication costs**.

## 2. What Is a DataSource?

`javax.sql.DataSource` is the standard JDBC interface providing the core method:

~~~java
Connection connection = dataSource.getConnection();
~~~

`DataSource` decouples data access code from building URLs, configuring drivers, opening TCP sockets, and authenticating against the database. In Spring Boot, `spring.datasource.*` properties let the framework create and manage a `DataSource` shared by repositories, JDBC clients, and the transaction manager.

If a `DataSource` has no pooling, each connection request may have to establish a new physical session. With `HikariDataSource`, `getConnection()` normally **borrows** an existing connection from the pool; when needed and below the limit, the pool can open additional physical connections.

It is important to distinguish two layers:

- **Physical connection:** the actual session between the application process and the database, consuming resources on both sides.
- **Borrowed connection:** the `Connection` object held by code; with a connection pool, this is typically a wrapper/proxy representing that physical session.

As a result, an application can handle thousands of repository calls per minute while maintaining a much smaller number of physical connections.

### What Happens When Calling `close()`?

With a direct unpooled connection, `close()` normally closes the physical session. With a connection borrowed from HikariCP, `close()` normally **returns the connection to the pool** so another request can reuse it. The pool actually closes the physical connection when it expires, breaks, is evicted, or when the pool shuts down.

That does not make `close()` optional: forgetting to return connections exhausts the pool even while the database itself still has capacity to execute SQL.

When writing manual JDBC outside a Spring-managed transaction, use `try-with-resources`:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT COUNT(*) FROM orders WHERE customer_id = ?")) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long count = resultSet.getLong(1);
            // Use count.
        }
    }
}
~~~

In Spring business code, you should generally use `JdbcClient`, `JdbcTemplate`, or a Spring Data JDBC Repository so the framework handles borrowing/returning connections and participating in transactions. **Do not arbitrarily call `dataSource.getConnection()` inside a `@Transactional` method**: doing so does not automatically guarantee you get the connection bound to Spring's transaction. If you truly need low-level JDBC APIs inside a transaction, use Spring-supported helpers such as `DataSourceUtils`.

## 3. Connection Borrow and Return Lifecycle

Without an enclosing transaction, a data access operation typically proceeds in this sequence:

1. The repository or JDBC client requests a `Connection` through Spring JDBC infrastructure.
2. The pool looks for an idle connection. If none is free and growth is allowed, the pool may create a physical connection; if all are busy, the caller must wait.
3. The JDBC driver sends SQL and parameters to the database.
4. The database parses, plans/executes the SQL, and sends back results or affected row counts.
5. Spring maps the results to Java objects and closes JDBC resources.
6. The connection is returned to the pool for subsequent callers to borrow.

Illustration with a pool capped at three connections:

~~~text
Time T1
  Request A ---- borrows C1 ---- running SQL
  Request B ---- borrows C2 ---- running SQL
  Request C ---- borrows C3 ---- running SQL
  Request D ---- waits for an idle connection

Time T2
  Request B ---- returns C2
  Request D ---- borrows C2 ---- runs SQL
~~~

While waiting, Request D does not consume an extra database connection. If it waits longer than the pool's `connectionTimeout`, borrowing fails and the application receives an exception. That is **different** from a SQL statement that started running and exceeded an execution timeout.

### A Transaction Can Hold a Connection Longer Than One SQL Statement

With Spring JDBC and standard transaction managers, Spring binds a connection to the thread executing the transaction so multiple JDBC operations participate in that transaction. The connection is typically acquired when the transaction starts or on first actual use, depending on configuration. It is returned to the pool after the transaction completes.

~~~text
@Transactional starts
  |
  +-- UPDATE account A
  +-- UPDATE account B
  +-- COMMIT (or ROLLBACK)
  |
@Transactional ends -> returns connection
~~~

Benefit: related SQL statements share the same commit/rollback boundary. Trade-off: long-running transactions hold connections longer and can extend lock duration in the database.

## 4. Where Do Database Access Costs Come From?

The duration of a data access operation is more than just the time the database spends running the SQL statement:

| Time Component | Example Causes |
| --- | --- |
| Waiting for a connection from the pool | All connections are borrowed; some transactions hold connections too long. |
| Establishing a new connection | TCP handshake, TLS, authentication, session initialization, or DNS/network. |
| Sending requests and receiving results | Network latency, multiple round-trips, large result payloads. |
| SQL processing on the database | Parsing/planning, table/index scans, joins, sorting, aggregation, memory and disk I/O. |
| Waiting on resources and locks | Lock contention, uncommitted concurrent transactions, CPU/I/O limits. |
| Converting results to objects | Reading `ResultSet`, type conversions, entity/aggregate mapping. |
| Ending the transaction | Sending `COMMIT` or `ROLLBACK`, log synchronization per durability settings. |

You can visualize it as:

~~~text
Total operation time
  ≈ pool wait time
  + network transfer time
  + database execution/wait time
  + data mapping time
  + transaction overhead
~~~

This is a mental model, not a strict additive formula across every driver: some phases overlap, and operations may reuse a connection already bound to a transaction.

### Why Can Many Small Queries Be Expensive?

Suppose for illustration that one database round-trip takes 3 ms of network transfer and the SQL takes 2 ms to execute:

- One query: roughly `3 + 2 = 5 ms`, excluding pool wait/mapping.
- One hundred sequential queries: roughly `100 × 5 = 500 ms`.

These numbers are **for cost-addition illustration only**, not default speeds of JDBC or any particular DBMS.

A loop calling a repository for each item can generate dozens or hundreds of round-trips:

~~~java
for (Long orderId : orderIds) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    process(order);
}
~~~

When business rules permit, querying by a set of IDs, batching, or redesigning how aggregates are read saves far more round-trips than increasing the connection count. With Spring Data JDBC, loading a single aggregate containing child collections can also issue multiple SQL statements; observe the actual SQL executed instead of assuming every repository call translates to exactly one query.

### Distinguishing Latency from Throughput

- **Latency:** how long a single operation waits to produce a result. Users experience this as response time.
- **Throughput:** how many operations the system completes per unit of time.
- **Concurrency:** how many operations are running or waiting at the same point in time.

A larger pool lets more SQL statements run concurrently, but if the database is already saturated on CPU, I/O, or locks, latency can actually worsen due to contention. Adding connections does not increase database CPU or IOPS.

## 5. What Problems Does a Connection Pool Solve?

Without connection reuse, every request could incur the cost of opening a physical connection. A pool keeps connections ready to eliminate that overhead, reuses resources, and caps the number of connections opened against the database.

Three core metrics:

- **Active:** number of connections currently borrowed by the application.
- **Idle:** number of connections sitting in the pool available for use.
- **Pending:** number of callers currently waiting to borrow a connection (not physical connections).

Typically `active + idle = total` and `total ≤ maximumPoolSize`. When `active` hits the limit and no idle connections remain, new requests must wait until a connection is returned or a timeout occurs.

Pools also validate connection health, discard broken/expired connections, and spin up replacements. These features improve operational stability, though they do not replace handling connection drop errors or designing controlled retries in the application layer.

### Connection Pools Are Not Thread Pools

A server with 200 HTTP worker threads does not necessarily need 200 database connections. Many requests spend time validating input, serializing JSON, calling other services, or doing in-memory work. Conversely, 20 database connections does not mean the database can only execute 20 SQL queries per second: each connection can execute many SQL statements back-to-back.

Do not size your connection pool 1:1 with your HTTP thread count.

## 6. Configuring DataSource and HikariCP in Spring Boot

Applications with `spring-boot-starter-data-jdbc` and an appropriate JDBC driver usually have a `DataSource` auto-configured by Spring Boot; when HikariCP is on the classpath and not overridden, HikariCP is the common default pool.

PostgreSQL configuration example:

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/shop}
    username: ${DB_USER:shop_app}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: shop-jdbc-pool
      maximum-pool-size: 12
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
~~~

This is a **syntax example**, not optimal tuning for every system. `DB_PASSWORD` must be supplied from the environment or a proper secret manager; avoid committing real passwords to a repository. The Hikari durations above are in milliseconds.

| Hikari Setting | Effect | Accurate Understanding |
| --- | --- | --- |
| `maximum-pool-size` | Caps physical connections in one pool instance | Not a minimum connection count and not SQL queries per second. |
| `connection-timeout` | Max time to wait when borrowing a connection before failing | Does not limit SQL execution time on the database. |
| `minimum-idle` | Target number of idle connections the pool tries to maintain | If unset, Hikari typically acts as a fixed-size pool with idle target equal to max. |
| `idle-timeout` | How long an idle connection may remain before eviction when the pool is allowed to shrink | Mainly meaningful when `minimum-idle` is less than `maximum-pool-size`. |
| `max-lifetime` | Expected maximum lifetime of a physical connection | Should be shorter than database/proxy/network connection limits; does not forcibly close a borrowed connection. |
| `keepalive-time` | Periodically checks idle connections to reduce silent drops by infrastructure | Only use when needed and configure compatibly with `max-lifetime`. |
| `validation-timeout` | Time limit for checking whether a connection is still usable | Must be smaller than `connection-timeout`. |
| `leak-detection-threshold` | Logs a warning when a connection is held past the threshold | An investigation signal, not automatic reclamation; slow transactions can trigger false positives. |

Do not set every parameter just because Hikari exposes it. Start with a simple configuration, measure real workload behavior, and tune based on evidence. TCP connection creation timeout (driver/network), pool borrow timeout, SQL execution timeout, and transaction timeout are independent concepts; handle each according to your DBMS and driver.

### Transactions and SQL Statements Have Separate Timeouts

For example:

- `connection-timeout: 3000`: if a connection cannot be borrowed within roughly 3 seconds, Hikari throws an error.
- Driver `connectTimeout`: limits time to open a physical connection to the database, driver-dependent.
- `Statement.setQueryTimeout(...)`, template timeouts, or database-side `statement_timeout`: governs SQL execution time.
- `@Transactional(timeout = ...)`: declares a transaction time limit for Spring infrastructure, though enforcement/detection depends on the transaction manager and JDBC calls. Do not treat it as a guarantee that the database will always abort every overdue query immediately.

When analyzing logs, identify **which layer timed out** before deciding to enlarge the pool.

## 7. Sizing the Pool Based on Load and Database Limits

Pool sizing must balance three things: actual concurrent demand, database processing capacity, and the total connection limit across **all application instances**.

An initial estimate based on Little's Law:

~~~text
Average held connections
  ≈ connection borrows per second × average connection hold time (seconds)
~~~

For example, a system averaging 200 connection borrows/second, each held for 30 ms:

~~~text
200 × 0.030 = 6 average held connections
~~~

The number 6 **does not** mean you should set the pool size to 6. Traffic bursts, hold-time variance, long transactions, database CPU/IO, and latency targets all affect the required size. Treat this as a starting point for measurement and load testing.

Notice that you must use **connection hold time**, not total HTTP request duration if the request also performs non-database work.

### Calculating Limits Across Application Replicas

Suppose you have four replicas, each configured with `maximum-pool-size: 15`:

~~~text
Maximum connections the application can open = 4 × 15 = 60
~~~

If the database permits 80 connections, you still must reserve headroom for background jobs, migrations, admin tools, other services, and spare capacity. If the system has multiple pool types, sum all of them. Budget check formula:

~~~text
Sum (instance count of each service × maximumPoolSize of that service)
    + connections from other components
    + reserve headroom
  ≤ database allowed connection limit
~~~

When using a database-side proxy or pooler like PgBouncer, also account for that middle tier's policies and limits. An oversized pool on each replica can cause the database to exceed `max_connections` as soon as the application scales out.

### Why Can Increasing the Pool Make the System Slower?

Suppose a database has resources to run 12 heavy queries efficiently at once. Allowing 80 heavy queries concurrently can create queues on CPU, buffers, disk, or locks, making each query slower. Holding connections longer causes even more requests to wait on the pool, creating a negative feedback loop.

Therefore, sustainable throughput improvements usually start with reducing query execution time and connection hold time first, then tuning concurrency appropriately.

## 8. `@Transactional` and Connection Hold Time

In Spring Data JDBC, transactions are typically managed via an appropriate JDBC `PlatformTransactionManager`, such as `JdbcTransactionManager` or `DataSourceTransactionManager`. Calls from repositories or Spring JDBC within the same transaction participate in the Spring-managed commit/rollback boundary.

A money transfer service illustrating two `UPDATE` statements that must succeed or fail together:

~~~java
import java.math.BigDecimal;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcClient jdbcClient;

    public TransferService(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (fromId == toId || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer details");
        }

        int debited = jdbcClient.sql("""
                UPDATE account
                   SET balance = balance - :amount
                 WHERE id = :fromId AND balance >= :amount
                """)
                .param("amount", amount)
                .param("fromId", fromId)
                .update();
        if (debited != 1) {
            throw new IllegalStateException("Source account does not exist or insufficient funds");
        }

        int credited = jdbcClient.sql("""
                UPDATE account
                   SET balance = balance + :amount
                 WHERE id = :toId
                """)
                .param("amount", amount)
                .param("toId", toId)
                .update();
        if (credited != 1) {
            throw new IllegalStateException("Destination account does not exist");
        }
    }
}
~~~

This example assumes an `account(id, balance)` table using a monetary type with suitable precision, and that the service is invoked through a Spring bean so `@Transactional` takes effect. Checking the affected row count catches business errors. Per Spring's default rollback rule for unchecked exceptions, if the second operation fails, the prior change rolls back as well. Real-world money transfer systems also need concurrency control, safe deadlock/retry handling, auditing, and other business rules.

**Performance point:** a transaction like the one above typically holds the connection across both `UPDATE`s. This is necessary for atomicity, but transaction scope should stay short:

~~~java
// Avoid: holding a database transaction open while waiting on an external service.
@Transactional
public void placeOrder(OrderCommand command) {
    orderRepository.save(command.toOrder());
    externalPaymentClient.charge(command.payment()); // may take several seconds
}
~~~

In real designs, payments outside the database typically require separate steps, intermediate statuses, or an appropriate outbox/saga pattern. Do not put slow network calls inside a JDBC transaction merely for coding convenience.

Additional notes:

- `@Transactional(readOnly = true)` expresses read intent and may supply optimization hints; do not treat it as an authorization mechanism or a strict write block across every database.
- Spring-managed transactions are normally bound to the **current thread**. Switching to another thread or using asynchronous APIs can lose the transaction context.
- Calling another `@Transactional` method on the same object (`this`) can bypass the Spring proxy; transaction boundaries will not appear as expected.
- Spring Data JDBC does not hold an `EntityManager` or lazy-loading session like JPA. Even so, long transactions and the number of queries generated when loading/saving aggregates directly impact the pool.

## 9. How to Reduce Database Access Costs

Optimizing JDBC performance starts with round-trip count and SQL quality, and only then pool parameters.

### 9.1. Reduce Unnecessary SQL Statements

Instead of querying one record per ID inside a loop, consider set-based queries or read models designed for reporting screens:

~~~sql
SELECT id, customer_id, total_amount
FROM orders
WHERE id IN (?, ?, ?, ?);
~~~

Use JDBC bound parameters rather than concatenating input strings. If the ID list is large, batch it appropriately and respect database/driver parameter limits. With Spring Data JDBC, also understand that `save`/`saveAll` on aggregates may trigger multiple statements; the method name does not guarantee actual JDBC batching.

### 9.2. Fetch Only the Data You Need

`SELECT *` can transfer many columns unused by the feature. For list pages, use projections/DTOs or JDBC queries tailored to display data; limit rows and paginate where appropriate. Oversized result sets increase network, mapping, and memory overhead.

### 9.3. Design Indexes Around Filtering and Sorting

Example of a frequent query:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC
LIMIT 20;
~~~

In PostgreSQL, an index like this can support that query pattern:

~~~sql
CREATE INDEX idx_orders_customer_created
    ON orders (customer_id, created_at DESC);
~~~

Indexes carry storage and write-maintenance costs; do not add them by guesswork. Read execution plans with `EXPLAIN` (or `EXPLAIN ANALYZE` in an appropriate environment) to verify whether the database uses the index and where the query is slow. Note that `EXPLAIN ANALYZE` actually executes the statement; exercise particular caution with write operations.

### 9.4. Batch Similar Operations

`JdbcTemplate.batchUpdate(...)` can reduce JDBC call overhead and let the driver optimize transmission, depending on driver and configuration. Batching does not mean every database executes everything in a single atomic operation. Measure actual SQL, round-trips, lock duration, and batch sizes.

### 9.5. Keep Transactions Short, Release Resources Early

Include in a transaction only the steps requiring shared atomicity. Avoid large file processing, network calls, or waiting on user input inside transactions. With streamed large results, a connection may stay held until the stream is fully consumed and closed properly; consider pagination/chunking where appropriate.

## 10. Observing and Diagnosing Pool Bottlenecks

In Spring Boot, you can use Actuator/Micrometer to observe Hikari connection metrics when enabled. Common metric names include:

- `hikaricp.connections.active`: connections currently borrowed.
- `hikaricp.connections.idle`: idle connections.
- `hikaricp.connections.pending`: callers currently waiting.
- `hikaricp.connections.max`: maximum pool limit.
- `hikaricp.connections.acquire`: time spent borrowing a connection.
- `hikaricp.connections.usage`: time a connection is held.
- `hikaricp.connections.timeout`: count of connection borrow timeouts.

Exact names and availability depend on versions and metrics configuration. Cross-reference application metrics with database metrics: active sessions, slow queries, lock waits, CPU, I/O, and connection limits.

| Symptom | Hypothesis to Check | Useful Investigation Steps |
| --- | --- | --- |
| `active` near `max`, `pending` rising | Pool is saturated or transactions hold connections too long | Inspect `usage` time, slow SQL, transaction scope, and concurrency. |
| `acquire` increasing, connection timeouts occurring | Requests wait too long on the pool | Check query counts, hold durations, and database saturation before increasing max. |
| Slow SQL while `pending` is near 0 | Bottleneck may be execution plan, locks, network, or database | Analyze slow queries, `EXPLAIN`, CPU/I/O, and lock waits. |
| Database reports "too many connections" | Total pools across replicas/services exceed budget | Sum `replicas × maximumPoolSize` plus other connections. |
| `active` does not drop after traffic stops | Leaked connections or unfinished transactions/tasks | Search for manual JDBC missing `close()`, unclosed streams, hung transactions, and thread dumps if needed. |
| Timeouts increase after enlarging the pool | Database may be overloaded by higher concurrency | Compare SQL latency, lock waits, CPU, and throughput before/after. |

A Hikari error `"connection is not available, request timed out"` generally states that **a connection could not be borrowed in time**. It does not prove the database is dead, nor is it sufficient reason to raise `maximumPoolSize`.

### Order of Investigation When Requests Are Slow

1. Measure request latency and determine how much time is spent in data access.
2. Check pool wait times (`acquire`/`pending`) and connection hold times (`usage`).
3. Count SQL queries per request, looking for query loops and aggregate operations issuing many statements.
4. If SQL is slow, check execution plans, indexes, data read/written, locks, and database resources.
5. If the pool is frequently full, verify whether transactions are holding connections while doing non-database work.
6. After addressing major causes, load-test at realistic concurrency and tune the pool within the database's total connection budget.

## 11. Common Misconceptions

| Claim | Reality |
| --- | --- |
| "Every Repository call opens a new TCP connection." | With a pool, calls normally borrow an existing physical connection; multiple operations in a transaction can share one connection. |
| "Configuring 100 connections will make SQL 10x faster than 10 connections." | Pools raise max concurrency; single-query speed and database capacity still depend on other resources. |
| "`close()` destroys the physical connection so I shouldn't call it." | With a pool, `close()` normally returns the connection for reuse; skipping it can exhaust the pool. |
| "`connection-timeout` controls slow SQL." | That is the borrow wait timeout; SQL execution timeouts require separate mechanisms. |
| "Calling `saveAll` definitely sends a single SQL statement." | Spring Data JDBC may emit multiple SQL statements for multiple entities/aggregates; verify actual behavior and use explicit batching when needed. |
| "`@Transactional` makes everything faster in all cases." | Transactions guarantee consistency boundaries; if overly broad, they hold connections and locks longer, increasing contention. |
| "Running out of connections just means raising max pool size." | Identify slow SQL, long transactions, leaks, traffic spikes, or an under-provisioned database before tuning. |

## 12. Practice Scenario to Check Your Understanding

Suppose an application has 3 replicas, each using HikariCP with `maximum-pool-size: 10`. Each replica has 40 in-flight requests. The database permits a maximum of 60 connections system-wide.

**Question 1.** Must there be 120 database connections?

No. 40 in-flight requests on one replica does not mean all 40 are holding a connection. The maximum total physical connections the three pools can open per configuration is `3 × 10 = 30`, assuming no other pools exist.

**Question 2.** If 11 requests on the same replica need to run SQL simultaneously while all 10 connections are borrowed, what happens?

The 11th request must wait for a connection to be returned. If it waits longer than `connection-timeout`, it fails at the connection-borrow step.

**Question 3.** Why is keeping a transaction open during a 2-second payment API call dangerous?

A connection—and potentially database locks—remain held while the application waits on the network. Available connections drop; remaining requests must wait and risk timing out, even if the actual SQL executes very quickly.

**Question 4.** If an endpoint runs 150 small sequential SQL queries, what should you try before raising pool size?

Count and group queries by business need; consider set-based queries, projections, batching, indexes, and changing how aggregates are loaded to cut round-trips. Then re-measure SQL duration, connection usage, and pool wait times.

## Key Takeaways for Building Spring Data JDBC Applications

`DataSource` is where connections are obtained, the pool reuses physical connections, and Spring JDBC and Spring Data JDBC are the application layers executing data operations. A borrowed connection is a finite resource: return it promptly, keep transactions compact, and minimize repetitive queries. Optimizing the system requires looking together at **SQL statement count, execution time, connection hold time, pool wait time, and database capacity**.
