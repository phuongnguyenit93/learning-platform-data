# Connection Pool: Borrow, Use, and Return

A Spring application can serve many requests concurrently, yet every JDBC query needs a `Connection` to the database. Creating a new physical connection for every operation usually incurs session setup, authentication, network, and database-side memory overhead. A **connection pool** manages a bounded set of connections so tasks can borrow, use, and return them without repeatedly opening and destroying physical connections.

This lesson focuses on the **borrow → use → return** cycle, the distinction between logical and physical connections, resource closing responsibilities, Spring's `DataSource` mechanism, its relationship with transactions, and how to recognize connection exhaustion. Java 17+ examples use HikariCP and H2.

## 1. From Direct Connections to a Connection Pool

The simplest JDBC access pattern:

```java
// Direct JDBC illustration; url, user, and password are already declared.
try (Connection con = DriverManager.getConnection(url, user, password)) {
    // Run SQL within the connection usage scope.
}
```

Each `DriverManager.getConnection` call typically establishes a physical connection to the DB. In an application with many small queries, repeating that process increases latency; the database also accepts only a finite number of concurrent sessions.

A pool holds reusable connections. When an idle, valid connection is available, borrowing is typically faster than creating a physical connection. If no idle connection is free and the limit has not been reached, the pool can open another. If capacity is exhausted, new borrow requests must wait, or fail after a timeout.

| Component | Responsibility |
| --- | --- |
| `javax.sql.DataSource` | Standard interface providing `Connection` via `getConnection()`; the interface itself does not guarantee a pool. |
| `HikariDataSource` | A `DataSource` implementation managing a connection pool, configuring limits, timeouts, validation, and shutdown. |
| Borrowed `Connection` | Handle granting connection usage rights within a work scope; should not be kept permanently in a shared field. |
| Physical connection | Actual JDBC session connected to the DB, reusable across multiple borrows. |
| `PreparedStatement` / `ResultSet` | Resources for an SQL execution; must be closed properly within the borrow lifecycle. |

A pool is a **resource reuse and limiting** mechanism, not a transaction: simply using a pool does not automatically put two SQL statements into the same transaction, nor does it make slow SQL run faster automatically.

## 2. The Borrow → Use → Return Cycle

```text
Thread/request calls DataSource.getConnection()
                    |
            +-------v--------+
            | Connection pool|
            | idle / active  |
            +-------+--------+
                    |
       +------------+-------------------------+
       |            |                         |
   Idle exists  Below max                 At max cap
       |            |                         |
   Issue handle May open physical         Wait up to
       |            |                  connectionTimeout
       +------------+                         |
                    v                  Returned / timeout
           Borrowed Connection
                    |
            Statement / ResultSet
                    |
              Work completed
                    |
            Connection.close()
                    |
         Return handle to pool
                    |
       Reset/validate/evict if needed
                    |
          Ready for next borrower
```

### Borrow

`DataSource.getConnection()` can be a **blocking/waiting** operation and can throw `SQLException`. Do not assume borrowing a connection is always instantaneous. Two separate borrows are also not guaranteed to receive the same physical connection.

A connection currently borrowed is normally counted as **active** even while Java code is doing other work and has not executed an SQL statement yet. Therefore, borrow close to when the DB is actually needed, use quickly, and return early.

### Use

While borrowed, the application can create `PreparedStatement`s, bind parameters, execute SQL, and read `ResultSet`s. A borrowed connection should not be shared arbitrarily across multiple requests or threads; transaction state and JDBC properties on the connection can interfere with each other.

With manual JDBC transaction management, the application is also responsible for deciding `commit`/`rollback` before returning the connection. With Spring-managed transactions, the transaction manager holds that authority.

### Return

When using a **pool-managed connection**, calling `connection.close()` usually **closes the logical handle and returns the borrow**, not always closing the real socket. The pool decides whether to retain or discard the physical connection based on state, lifetime, and validation results.

After `close()`, that handle's usage rights have expired; do not continue executing SQL on it or store it for later reuse. To perform a new task, call `getConnection()` again.

**Closing a borrowed handle differs from closing the pool itself.** `HikariDataSource.close()` stops the pool and is meant for when the application or owning component shuts down, not called after every request.

## 3. Closing Resources with try-with-resources

In direct JDBC, the common and safe pattern is:

```java
// Illustration inside an application that already has dataSource and productId.
String sql = "SELECT name FROM product WHERE id = ?";
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(sql)) {
    ps.setLong(1, productId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
```

This snippet does not run standalone because `dataSource`, `productId`, and the `product` table belong to the integrating application. `try-with-resources` guarantees calling `close()` on successfully opened objects when exiting the block, even if SQL throws an error. The closing order is `ResultSet`, then `PreparedStatement`, then `Connection`. If `getConnection()` throws an exception, there is no connection to return.

If using manual `try/finally`, you must account for every `return`, `throw`, errors between two statements, and exceptions during cleanup. Forgetting to release on an error path is a classic cause of **connection leaks**.

### `close()` Does Not Replace commit/rollback

With manual JDBC transaction control, control the transaction explicitly:

```java
// Illustrative snippet; performFirstWrite/performSecondWrite
// are application JDBC methods not defined here.
try (Connection con = dataSource.getConnection()) {
    con.setAutoCommit(false);
    try {
        performFirstWrite(con);
        performSecondWrite(con);
        con.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            con.rollback();
        } catch (SQLException rollbackFailure) {
            error.addSuppressed(rollbackFailure);
        }
        throw error;
    }
}
```

The pool may roll back unfinished work and restore some JDBC properties upon reclaiming the connection, depending on the implementation. However, **never rely on `close()` to decide whether a transaction succeeds or fails**; always commit/rollback per business logic or let the Spring transaction manager handle it.

## 4. Complete Example: Exhausting the Pool and Returning Connections

The example runs with **Java 17+, Maven, HikariCP 5.1.0, and in-memory H2**. The pool holds at most two physical connections. Holding two handles simultaneously forces the third borrow to wait and then time out. Once the two handles are closed, we can borrow a connection again and query data.

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>pool-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
            <version>5.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.13</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/PoolLifecycleDemo.java`:

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLTransientConnectionException;
import java.sql.Statement;

public class PoolLifecycleDemo {
    public static void main(String[] args) throws SQLException {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:h2:mem:pool_demo;DB_CLOSE_DELAY=-1");
        config.setUsername("sa");
        config.setPassword("");
        config.setPoolName("learning-pool");
        config.setMaximumPoolSize(2);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(1_000);

        try (HikariDataSource pool = new HikariDataSource(config)) {
            // Initialize data and then return the connection.
            try (Connection init = pool.getConnection();
                 Statement stmt = init.createStatement()) {
                stmt.executeUpdate(
                    "CREATE TABLE sample (id INT PRIMARY KEY, message VARCHAR(40))");
                stmt.executeUpdate(
                    "INSERT INTO sample(id, message) VALUES (1, 'hello')");
            }
            System.out.println("Initialized");

            // Two handles exist concurrently.
            try (Connection first = pool.getConnection();
                 Connection second = pool.getConnection()) {
                System.out.println("Borrowed 2 connections");
                try (Connection unexpected = pool.getConnection()) {
                    throw new AssertionError("Third borrow should not succeed");
                } catch (SQLTransientConnectionException expected) {
                    System.out.println("Third borrow timed out");
                }
            }
            System.out.println("Returned 2 connections");

            // Both handles were returned; can borrow again.
            try (Connection again = pool.getConnection();
                 PreparedStatement ps = again.prepareStatement(
                     "SELECT message FROM sample WHERE id = ?")) {
                ps.setInt(1, 1);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Missing sample row");
                    }
                    System.out.println(
                        "Borrow again: " + rs.getString("message"));
                }
            }
        }
        System.out.println("Pool closed");
    }
}
```

Run in the directory containing `pom.xml` with JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=PoolLifecycleDemo
```

Expected **stdout lines from `System.out`**:

```text
Initialized
Borrowed 2 connections
Third borrow timed out
Returned 2 connections
Borrow again: hello
Pool closed
```

HikariCP may print startup/shutdown logs or timeout warnings to **stderr**, which are not included in the stdout lines above.

Explanation:

1. The connection that initializes the table is returned immediately after creating the data.
2. Two connections `first` and `second` are being held; `maximumPoolSize = 2` forces the third `getConnection()` call to wait.
3. After `connectionTimeout = 1_000` milliseconds elapse, HikariCP throws `SQLTransientConnectionException`. That is an error waiting to **borrow** a connection; the third borrower's SQL statement has not even executed.
4. Exiting the block returns both handles; the next borrow reads the `hello` row.
5. `HikariDataSource.close()` in the outer block ends the pool's lifecycle.

Do not conclude that `first`, `second`, and `again` always use the same physical connection, or that the pool must reissue them in a fixed order. The pool may replace a connection when validation detects a fault or when it exceeds its lifetime.

## 5. Which Objects Are Long-Lived, Which Are Short-Lived?

Common mistake:

```java
// WRONG: storing Connection as a field of a shared repository.
class BadRepository {
    private final Connection connection;

    BadRepository(DataSource source) throws SQLException {
        this.connection = source.getConnection();
    }
}
```

This code permanently holds an active slot in the pool without a clear release boundary. If multiple requests use the same connection, they can collide on transactions, auto-commit, statements, and session state. The connection can also become broken after a DB restart.

The object that should be long-lived is **`DataSource`/the pool** (managed at application scope). The short-lived object is the **borrowed connection** (managed within the scope of SQL execution or a transaction). Services/repositories should hold `DataSource`, `JdbcTemplate`, or a repository abstraction, **not hold connections long-term**.

Another practical rule: do not borrow a connection and then call an HTTP service, wait for user input, sleep for a long time, or perform heavy CPU work while the connection sits idle. During that time, the pool still treats the connection as active and other requests may have to wait.

## 6. How Does Spring JDBC Manage Borrowing and Returning Automatically?

Spring's `JdbcTemplate` handles acquiring connections, creating statements, executing queries, closing JDBC resources, and translating exceptions. For typical repositories, you do not have to call `getConnection()`/`close()` directly.

This is an **integration snippet** for a Spring application that already has `JdbcTemplate` and a `product` table:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findName(long id) {
        return jdbc.queryForObject(
            "SELECT name FROM product WHERE id = ?",
            String.class,
            id
        );
    }
}
```

`JdbcTemplate` uses Spring's **transaction-aware** connection access mechanism based on `DataSourceUtils`. When no Spring-managed transaction is active, the connection is usually released as soon as the operation finishes. When a transaction is bound to the current thread, Spring must keep the connection until the transaction ends; an intermediate repository method returning **does not mean** the connection has been returned to the pool.

### `@Transactional` Boundaries

Example service combining two data operations:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders,
                        InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void place(long productId, int quantity) {
        orders.insertOrder(productId, quantity);
        inventory.decreaseStock(productId, quantity);
    }
}
```

This snippet **is not a standalone program**; the two repositories are application dependencies. If transaction management is enabled, the call goes through the Spring interceptor, and both repositories use the same matching `DataSource`/transaction manager, the typical flow is:

```text
Request → proxy of OrderService
          → start / join transaction
          → bind Connection to transaction (when needed)
          → orders.insertOrder() uses bound connection
          → inventory.decreaseStock() uses bound connection
          → COMMIT or ROLLBACK per outcome/rollback rules
          → release Connection to pool when transaction ends
```

Thus, the duration a connection is held can be as long as a substantial portion of the transaction, not just the duration of one SQL statement. Long transactions caused by network I/O, locks, or non-DB logic will easily exhaust the pool.

Several limitations to keep in mind:

- `@Transactional` in standard proxy mode does not open a new boundary when a method directly calls `this.otherMethod()` on the same bean.
- `REQUIRES_NEW` propagation may require a separate extra connection while the outer transaction still holds resources; pool exhaustion risk must be considered.
- Work offloaded to another thread does not automatically inherit the original thread's connection/transaction.
- Multiple `DataSource`s do not automatically form a single atomic transaction just because they appear together in a `@Transactional` method.

### When You Must Use Connection Manually in Spring

Instead of obtaining a connection directly from the pool in the middle of a Spring transaction, use `DataSourceUtils`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;

public final class CustomJdbcAccess {
    private final DataSource dataSource;

    public CustomJdbcAccess(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void markProcessed(long id) throws SQLException {
        Connection con = DataSourceUtils.getConnection(dataSource);
        try (PreparedStatement ps = con.prepareStatement(
                "UPDATE job SET processed = TRUE WHERE id = ?")) {
            ps.setLong(1, id);
            ps.executeUpdate();
        } finally {
            DataSourceUtils.releaseConnection(con, dataSource);
        }
    }
}
```

The class compiles when Spring JDBC is added, but needs a data source and a `job` table to run. `getConnection` recognizes a connection bound by Spring to the transaction, and `releaseConnection` avoids prematurely closing it while it still belongs to the transaction. `JdbcTemplate` is usually cleaner and less error-prone.

Avoid calling `dataSource.getConnection()` directly inside a Spring transaction and assuming that connection automatically joins the active transaction. It may be a different connection, running outside the expected commit/rollback boundary. `TransactionAwareDataSourceProxy` exists for certain legacy JDBC code needing the `DataSource` API, but there is no need to add it if using `JdbcTemplate` or `DataSourceUtils` properly.

## 7. How the Pool Handles State and Physical Connections Upon Return

Returning a handle to the pool is not simply flipping an `active` label to `idle`. The pool must ensure the connection is valid and JDBC states can be safely reused.

| State | Risk If Overlooked |
| --- | --- |
| `setAutoCommit(false)` still active | Next borrower might unintentionally run multiple statements without committing. |
| Isolation, read-only, schema/catalog changed | Subsequent statements run under an unexpected context. |
| Unfinished transaction | Could hold uncommitted changes/locks and cause state leakage. |
| Unclosed ResultSet/Statement | Accumulates cursors, driver resources, or database resources. |
| Dead physical connection due to network/DB restart | Next borrow could fail if not detected and replaced. |
| DB-specific session state like temp tables, session variables, advisory locks | Might not be fully reset by generic pool mechanisms. |

HikariCP tracks/restores several standard JDBC properties and has mechanisms to validate or evict broken connections. However, do not assume the pool knows every session state altered by DBMS-specific SQL. If the application creates such session state itself, clean it up explicitly or redesign.

With modern JDBC 4 drivers, HikariCP typically uses standard checks such as `Connection.isValid(...)` when needed; arbitrarily configuring `connectionTestQuery` is unnecessary by default. Connections reaching eviction age or found broken may be physically closed **upon return**, instead of returning to idle.

## 8. Pool Configuration and Timeouts

Some important HikariCP properties:

| Property | Effect | Notes |
| --- | --- | --- |
| `maximumPoolSize` | Maximum connections in one pool, including active and idle. | Bounds DB resources; setting too high can increase contention. |
| `minimumIdle` | Number of idle connections the pool tries to maintain. | HikariCP's default usually equals `maximumPoolSize`; can omit if a nearly fixed-size pool is desired. |
| `connectionTimeout` | Maximum time to wait for `getConnection()` when no handle is available. | Does not limit SQL execution time or overall transaction duration. |
| `idleTimeout` | Idle duration before considering removal of excess connections. | Primarily effective when `minimumIdle < maximumPoolSize`; eviction timing is not millisecond-exact. |
| `maxLifetime` | Maximum age of a physical connection before scheduled replacement. | Connections currently borrowed are normally not cut mid-operation just for reaching age. |
| `keepaliveTime` | Periodic keepalive check interval for idle connections when configured. | Does not replace TCP timeouts, DB settings, or monitoring. |
| `leakDetectionThreshold` | Threshold to log a warning when a connection is suspected of being held too long. | Does not automatically return connections; valid long transactions can also trigger warnings. |
| `autoCommit` | Default auto-commit mode of issued connections. | When a Spring transaction exists, the manager controls transaction state along its boundaries. |

For a **Spring Boot** application that already has the PostgreSQL JDBC driver, HikariCP, and matching auto-configuration, illustrative configuration:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: demo_user
    password: demo_password
    hikari:
      pool-name: application-pool
      maximum-pool-size: 12
      connection-timeout: 2000
```

This is not a ready-made production configuration: use secret management instead of sample passwords, configure driver/DB, and choose parameters based on real load. `spring.datasource.hikari.*` is a Spring Boot mechanism, not a namespace that exists automatically in every plain Spring Framework application.

### Sizing the Pool Based on Total DB Resources

Suppose there are 3 application instances, each capped at 12 connections. Potential total is **36 connections**, excluding migration processes, other services, background jobs, and admin connections. If the DB allows 40 connections, hitting the limit is very easy. Budget connections for the entire system first, then divide per instance.

Do not size the pool by taking the concurrent request count and setting connections equal to it; a request may not need the DB yet or may use a connection briefly. Conversely, a request with a long transaction can hold a connection for a long time despite little SQL. Measure connection hold time, waiting counts, throughput, DB CPU/IO, locks, and backend limits.

Example for **estimating the average**: if there are 100 DB tasks per second and each task holds a connection for an average of 50 ms, the average active count is roughly `100 × 0.05 = 5` in a steady system. This estimate does not reflect traffic spikes, hold-time distribution, or DB processing limits; you must measure and leave adequate headroom.

### Three Different Timeouts

1. **Borrow/connection timeout:** no `Connection` yet, `getConnection()` is waiting on the pool. HikariCP may throw `SQLTransientConnectionException`.
2. **Statement/query/socket timeout:** connection already borrowed; SQL, locks, or network stall, causing an SQLException during execution.
3. **Transaction/request timeout:** deadline of the Spring transaction, HTTP request, or business operation; does not automatically mean JDBC resources have already been released.

Increasing `connectionTimeout` only allows waiting longer; it does not increase pool capacity. Increasing `maximumPoolSize` when the DB is already saturated can worsen the incident.

## 9. Measuring Active, Idle, Total, Waiting, and Acquisition Time

Metrics worth observing:

- **Active:** connections currently borrowed, even if the thread is not executing SQL yet.
- **Idle:** connections available to borrow.
- **Total:** total physical connections managed by the pool at the time of measurement.
- **Waiting/pending:** number of threads waiting on `getConnection()`; when rising alongside active ≈ max, the pool may be saturated.
- **Acquisition time:** borrow wait duration; inspect percentiles, not just the average.
- **Usage/hold duration:** time from borrow to return; excessive duration can stem from transactions, locks, slow SQL, I/O, or leaks.
- **Timeout/errors:** distinguish failure to obtain a connection from SQL, network, or DB errors.

With `HikariDataSource`, you can take a snapshot using `HikariPoolMXBean`:

```java
// Illustrative snippet; pool is an active HikariDataSource.
var stats = pool.getHikariPoolMXBean();
System.out.println("active=" + stats.getActiveConnections());
System.out.println("idle=" + stats.getIdleConnections());
System.out.println("total=" + stats.getTotalConnections());
System.out.println("waiting=" + stats.getThreadsAwaitingConnection());
```

These numbers change continuously, so there is **no fixed stdout**. In real systems, export metrics to observability tools and correlate with query latency, transaction duration, deadlocks, and DB-side connection limits.

### Leak Detection Is Not an Automatic Closing Mechanism

`leakDetectionThreshold` logs a stack trace when a handle is held suspiciously long. It is a clue to investigate, not conclusive proof of a leak. A legitimate but long transaction can also exceed the threshold. The library does not automatically close the handle just because it emitted a leak warning.

An actual leak is usually code that borrows a connection but misses a release path—for example, a statement throws an exception and returns/throws before reaching `close()`. Check try-with-resources, finally blocks, and all exit paths before simply raising pool size.

## 10. Diagnosing Connection Borrow Timeouts

```text
getConnection() timeout
        |
        +-- active continuously hitting maximumPoolSize?
        |       +-- long connection hold duration:
        |       |     check transactions, SQL, locks, I/O inside transactions
        |       +-- handle forgotten to be released:
        |             check exception branches, leak logs, resource ownership
        |
        +-- waiting high but DB not saturated?
        |       +-- re-evaluate sizing and peak concurrency with data
        |
        +-- total below max yet still cannot issue?
                +-- check DB max connections, network, auth,
                    driver, validation, or ability to open new sessions
```

Do not immediately raise `maximumPoolSize`; a prolonged lock issue can cause even more connections to wait on each other. Improving queries, shortening transaction hold time, and fixing leaks are usually more effective.

## 11. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Forgetting `close()` on exception branches | Connection stays active long and pool runs out of slots. | Use `try-with-resources` or `finally` in direct JDBC. |
| Storing `Connection` as a singleton field | Slot leak, sharing transaction state across requests. | Store `DataSource`/`JdbcTemplate`; borrow per unit of work. |
| Calling `HikariDataSource.close()` after one query | Shuts down the entire pool. | Shut down the pool only when its owning component stops. |
| Assuming `Connection.close()` always closes the socket | Ignores reuse and logical handle lifecycle. | With pool-managed handles, close returns it; the pool decides physical handling. |
| Not closing statements/result sets | Leaks cursors or driver resources. | Close them inside try-with-resources. |
| Calling `DataSource.getConnection()` directly inside `@Transactional` | May receive a connection outside Spring's bound transaction. | Prefer `JdbcTemplate` or `DataSourceUtils`. |
| Thinking a returning repository method releases the connection despite an outer transaction | Misdiagnoses active counts. | Understand the transaction manager releases only when the transaction ends. |
| Leaving a transaction unfinished and just closing the handle | Transaction outcome depends on pool/driver, hard to control. | Explicitly commit/rollback or let Spring manage it. |
| Raising max pool size to fix slow SQL or locks | Can pile more load onto the DB. | Inspect queries, locks, and active hold duration. |
| Treating a leak log as certain proof of a leak | Misdiagnoses legitimate long transactions. | Cross-check stack traces, metrics, and release timing. |
| Holding a connection while making HTTP calls or sleeping | Occupies a slot while not using the DB. | Move non-DB I/O outside transactions/borrows. |

## 12. Operational Checklist

Before deploying or debugging a connection pool, ask yourself:

1. **Who owns the pool?** Is the pool created and shut down with the application lifecycle, or accidentally created/closed per request?
2. **Who owns the handle?** Is release guaranteed on every success, exception, and early-return path?
3. **Who owns the transaction?** Is it direct JDBC or the Spring transaction manager? Are the two management styles mixed?
4. **How long is a connection held?** Is it waiting on I/O, HTTP, locks, or non-DB operations while active?
5. **What happens when connections run out?** Are there sensible timeouts, accurate error reporting, and waiting metrics?
6. **Does the sum of connections across all instances fit DB limits?** Is there headroom left for other services?
7. **Is the pool observable?** Are active, idle, waiting, acquisition time, usage time, and DB error alerts tracked?
8. **Is there session state not automatically reset?** If so, who cleans it up before the next borrow?

**Remember:** `DataSource` is the connection supplier; `getConnection()` is borrowing; JDBC/transaction operations are using; `Connection.close()` on a pool-managed handle is normally returning; `HikariDataSource.close()` is shutting down the pool. In Spring, `JdbcTemplate` and the transaction manager coordinate borrowing/returning along proper transaction boundaries. A pool has only a finite number of connections, so performance depends on both **connection hold duration** and **the database's serving capacity**.

### References

- HikariCP — design and configuration options: https://github.com/brettwooldridge/HikariCP
- Spring Framework — JDBC `DataSource`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — `DataSourceUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Java SE 17 — `java.sql.Connection`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
